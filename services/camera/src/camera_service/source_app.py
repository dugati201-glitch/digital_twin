"""Pi-only HTTP MJPEG service. No video decode or encode."""

import asyncio

from aiohttp import web

from .mjpeg import UsbJpegSource

SOURCES = web.AppKey("sources", list)


async def health(request):
    cameras = [{"id": source.device, "device": source.location,
                "ready": source.ready(),
                "url": f"/cameras/{source.device}/video_feed"}
               for source in request.app[SOURCES]]
    ready = all(camera["ready"] for camera in cameras)
    return web.json_response({"status": "ready" if ready else "unavailable",
                              "cameras": cameras}, status=200 if ready else 503)


async def stream(request):
    camera_id = request.match_info.get("camera_id")
    source = next((s for s in request.app[SOURCES]
                   if camera_id is None or s.device == camera_id), None)
    if source is None:
        raise web.HTTPNotFound(text="Unknown camera")
    if not source.ready():
        raise web.HTTPServiceUnavailable(text="Camera unavailable")
    response = web.StreamResponse(headers={
        "Content-Type": "multipart/x-mixed-replace; boundary=frame",
        "Cache-Control": "no-store",
    })
    await response.prepare(request)
    sequence = -1
    try:
        while True:
            result = await source.wait_frame(sequence)
            if result is None:
                break
            sequence, jpeg, _ = result
            payload = (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
            await asyncio.wait_for(response.write(payload), source.config.stale_seconds)
    except (ConnectionError, asyncio.TimeoutError, RuntimeError):
        pass
    return response


def create_source_app(config, sources=None):
    app = web.Application()
    app[SOURCES] = sources if sources is not None else [
        UsbJpegSource(config, camera) for camera in config.cameras]
    app.router.add_get("/health", health)
    app.router.add_get("/video_feed", stream)
    app.router.add_get("/cameras/{camera_id}/video_feed", stream)

    async def startup(app):
        for source in app[SOURCES]:
            source.start()

    async def cleanup(app):
        await asyncio.gather(*(source.stop() for source in app[SOURCES]))

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app
