"""HTTP signaling and WebRTC camera service."""

import argparse
import asyncio
import json
import logging
import os
import inspect
import time
import secrets
from pathlib import Path

from aiohttp import web
from aiortc import (
    RTCConfiguration,
    RTCPeerConnection,
    RTCSessionDescription,
)
import cv2

from digital_twin_common.logging import configure_logging

from .capture import Camera
from .codec import configure_vp8_threads
from .config import Config
from .track import CameraVideoTrack
from .mjpeg import RemoteJpegSource

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")

CONFIG_KEY = web.AppKey("config", Config)
CAMERAS_KEY = web.AppKey("cameras", list)
PEERS_KEY = web.AppKey("peers", set)
PEER_FACTORY_KEY = web.AppKey("peer_factory", object)
SESSIONS_KEY = web.AppKey("sessions", dict)
REAPER_KEY = web.AppKey("reaper", object)


def _default_peer_factory():
    # The LAN demo intentionally avoids the default public STUN lookup.
    return RTCPeerConnection(RTCConfiguration(iceServers=[]))


async def _index(request):
    return web.FileResponse(STATIC_DIR / "index.html")


async def _client_javascript(request):
    return web.FileResponse(STATIC_DIR / "client.js",
                            headers={"Cache-Control": "no-store"})


async def _health(request):
    cameras = request.app[CAMERAS_KEY]
    camera_status = [
        {"device": camera.device, "ready": camera.ready(),
         **(camera.stats() if hasattr(camera, "stats") else {})}
        for camera in cameras
    ]
    ready = bool(camera_status) and all(item["ready"] for item in camera_status)
    return web.json_response(
        {
            "status": "ready" if ready else "unavailable",
            "cameras": camera_status,
            "peers": len(request.app[PEERS_KEY]),
        },
        status=200 if ready else 503,
    )


async def _discard_peer(app, peer):
    if peer not in app[PEERS_KEY]:
        return
    app[PEERS_KEY].discard(peer)
    for session_id, entry in list(app[SESSIONS_KEY].items()):
        if entry[0] is peer:
            del app[SESSIONS_KEY][session_id]
    await peer.close()


async def _session(request):
    session_id = request.match_info["session_id"]
    entry = request.app[SESSIONS_KEY].get(session_id)
    if entry is None:
        raise web.HTTPNotFound()
    if request.method == "DELETE":
        await _discard_peer(request.app, entry[0])
    else:
        request.app[SESSIONS_KEY][session_id] = (entry[0], time.monotonic())
    return web.Response(status=204)


async def _offer(request):
    app = request.app
    config = app[CONFIG_KEY]
    cameras = app[CAMERAS_KEY]

    if not cameras or not all(camera.ready() for camera in cameras):
        return web.json_response({"error": "Camera unavailable"}, status=503)
    if len(app[PEERS_KEY]) >= config.max_peers:
        return web.json_response({"error": "Peer limit reached"}, status=503)

    try:
        params = await request.json()
        if type(params) is not dict or set(params) != {"sdp", "type"}:
            raise ValueError("body must contain only sdp and type")
        if type(params["sdp"]) is not str or params["type"] != "offer":
            raise ValueError("invalid WebRTC offer")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return web.json_response({"error": str(exc) or "Invalid JSON offer"}, status=400)

    peer = app[PEER_FACTORY_KEY]()
    app[PEERS_KEY].add(peer)
    session_id = secrets.token_urlsafe(24)
    app[SESSIONS_KEY][session_id] = (peer, time.monotonic())
    for camera in cameras:
        peer.addTrack(CameraVideoTrack(camera))

    @peer.on("connectionstatechange")
    async def on_connectionstatechange():
        log.info("WebRTC peer state: %s", peer.connectionState)
        if peer.connectionState in ("failed", "closed", "disconnected"):
            await _discard_peer(app, peer)

    try:
        await peer.setRemoteDescription(
            RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        )
        answer = await peer.createAnswer()
        await peer.setLocalDescription(answer)
    except Exception as exc:
        log.warning("Rejected WebRTC offer: %s", exc)
        await _discard_peer(app, peer)
        return web.json_response({"error": "Invalid WebRTC offer"}, status=400)

    return web.json_response({
        "session_id": session_id,
        "sdp": peer.localDescription.sdp,
        "type": peer.localDescription.type,
    })


async def _startup(app):
    configure_vp8_threads(app[CONFIG_KEY].vp8_threads)
    cv2.setNumThreads(app[CONFIG_KEY].opencv_threads)
    for camera in app[CAMERAS_KEY]:
        camera.start()
    async def reap():
        while True:
            await asyncio.sleep(2)
            timeout = getattr(app[CONFIG_KEY], "peer_timeout_seconds", 20)
            for peer, touched in list(app[SESSIONS_KEY].values()):
                if time.monotonic() - touched > timeout:
                    await _discard_peer(app, peer)
    app[REAPER_KEY] = asyncio.create_task(reap())


async def _cleanup(app):
    app[REAPER_KEY].cancel()
    await asyncio.gather(app[REAPER_KEY], return_exceptions=True)
    peers = list(app[PEERS_KEY])
    if peers:
        await asyncio.gather(*(peer.close() for peer in peers),
                             return_exceptions=True)
        app[PEERS_KEY].clear()
    for camera in app[CAMERAS_KEY]:
        result = camera.stop()
        if inspect.isawaitable(result):
            await result


def create_app(config, cameras=None, peer_factory=None):
    app = web.Application(client_max_size=64 * 1024)
    app[CONFIG_KEY] = config
    app[CAMERAS_KEY] = (
        list(cameras)
        if cameras is not None
        else ([RemoteJpegSource(config, camera) for camera in config.cameras]
              if getattr(config, "role", None) == "server"
              else [Camera(config, device) for device in config.devices])
    )
    app[PEERS_KEY] = set()
    app[SESSIONS_KEY] = {}
    app[PEER_FACTORY_KEY] = peer_factory or _default_peer_factory
    app.router.add_get("/", _index)
    app.router.add_get("/client.js", _client_javascript)
    app.router.add_get("/health", _health)
    app.router.add_post("/offer", _offer)
    app.router.add_post("/sessions/{session_id}", _session)
    app.router.add_delete("/sessions/{session_id}", _session)
    app.on_startup.append(_startup)
    app.on_cleanup.append(_cleanup)
    return app


def main():
    parser = argparse.ArgumentParser(description="Camera WebRTC service")
    parser.add_argument("--config", default=os.getenv("CAMERA_CONFIG_FILE"),
                        help="YAML configuration path (or set CAMERA_CONFIG_FILE)")
    parser.add_argument("--log-config", default=os.getenv("LOG_CONFIG_FILE"),
                        help="Logging YAML path (or set LOG_CONFIG_FILE)")
    args = parser.parse_args()
    if not args.config:
        parser.error("Provide --config or CAMERA_CONFIG_FILE")
    if not args.log_config:
        parser.error("Provide --log-config or LOG_CONFIG_FILE")
    try:
        config = Config.from_yaml(args.config)
        configure_logging(args.log_config)
    except ValueError as exc:
        parser.error(str(exc))

    log.info("HTTP signaling listening on %s:%s", config.host, config.port)
    web.run_app(
        create_app(config),
        host=config.host,
        port=config.port,
        print=None,
        access_log=log,
    )


if __name__ == "__main__":
    main()
