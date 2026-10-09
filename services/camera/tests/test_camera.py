import asyncio
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from aiohttp.test_utils import AioHTTPTestCase
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
import cv2
import numpy as np
import yaml

from camera_service.app import create_app
from camera_service.capture import Camera
from camera_service.config import Config
from camera_service.track import CameraVideoTrack, VIDEO_TIME_BASE


def settings(**overrides):
    base = Config.from_yaml(Path(__file__).resolve().parents[1] / "config.yaml")
    return replace(base, **overrides)


class FakeCapture:
    def __init__(self, fail=False):
        self.fail = fail
        self.released = threading.Event()

    def isOpened(self):
        return True

    def set(self, key, value):
        return True

    def read(self):
        return (False, None) if self.fail else (
            True,
            np.zeros((24, 32, 3), dtype=np.uint8),
        )

    def release(self):
        self.released.set()


class FakeCamera:
    def __init__(self, device="/dev/video-test", ready=True):
        self.device = device
        self._ready = ready
        self.started = False
        self.stopped = False
        self.sequence = 0

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def ready(self):
        return self.started and self._ready

    def wait_frame(self, sequence):
        time.sleep(0.01)
        self.sequence = max(self.sequence + 1, sequence + 1)
        return self.sequence, np.zeros((48, 64, 3), dtype=np.uint8)


class CameraTests(unittest.TestCase):
    def test_capture_resizes_and_stops(self):
        config = settings(width=64, height=48)
        capture = FakeCapture()
        camera = Camera(config, config.devices[0], lambda: capture)
        camera.start()
        try:
            result = camera.wait_frame(-1)
            self.assertIsNotNone(result)
            self.assertEqual(result[1].shape[:2], (48, 64))
            self.assertTrue(camera.ready())
        finally:
            camera.stop()
        self.assertTrue(capture.released.is_set())
        self.assertFalse(camera._thread.is_alive())

    def test_failed_capture_reopens(self):
        config = settings(retry_seconds=0.01, stale_seconds=0.5)
        failed, recovered = FakeCapture(fail=True), FakeCapture()
        captures = iter([failed, recovered])
        camera = Camera(config, config.devices[0], lambda: next(captures))
        camera.start()
        try:
            self.assertIsNotNone(camera.wait_frame(-1))
            self.assertTrue(failed.released.is_set())
        finally:
            camera.stop()
        self.assertTrue(recovered.released.is_set())

    def test_unavailable_and_stale_frames(self):
        config = settings(stale_seconds=0.01)
        camera = Camera(config, config.devices[0])
        self.assertFalse(camera.ready())
        with camera._condition:
            camera._frame = np.zeros((1, 1, 3), dtype=np.uint8)
            camera._sequence = 1
            camera._updated = time.monotonic() - 1
        self.assertIsNone(camera.wait_frame(-1))
        self.assertFalse(camera.ready())

    def test_yaml_overrides_and_invalid_files(self):
        source = Path(__file__).resolve().parents[1] / "config.yaml"
        data = yaml.safe_load(source.read_text())
        data.update(devices=["/dev/video0", "/dev/video1"], width=1280,
                    height=720, fps=30, backend="auto")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "camera.yaml"
            path.write_text(yaml.safe_dump(data))
            config = Config.from_yaml(path)
            self.assertEqual(config.devices, ["/dev/video0", "/dev/video1"])
            self.assertEqual((config.width, config.height, config.fps), (1280, 720, 30))
            self.assertEqual(config.backend, "auto")
            invalid = [
                "",
                "[]",
                "[",
                yaml.safe_dump({**data, "fps": True}),
                yaml.safe_dump({**data, "port": "5000"}),
                yaml.safe_dump({**data, "extra": 1}),
                yaml.safe_dump({key: value for key, value in data.items()
                                if key != "devices"}),
            ]
            for content in invalid:
                path.write_text(content)
                with self.subTest(content=content), self.assertRaises(ValueError):
                    Config.from_yaml(path)
            with self.assertRaises(ValueError):
                Config.from_yaml(Path(directory) / "missing.yaml")

    def test_invalid_configuration(self):
        invalid = [
            dict(devices=[]),
            dict(devices=["/dev/video0", "/dev/video0"]),
            dict(devices=[""]),
            dict(fps=0),
            dict(width=0),
            dict(port=65536),
            dict(retry_seconds=float("nan")),
            dict(max_peers=0),
            dict(backend="unknown"),
            dict(shutdown_seconds=0),
        ]
        for overrides in invalid:
            with self.subTest(settings=overrides), self.assertRaises(ValueError):
                settings(**overrides)


class TrackTests(unittest.IsolatedAsyncioTestCase):
    async def test_track_converts_latest_bgr_frame(self):
        camera = FakeCamera()
        camera.start()
        track = CameraVideoTrack(camera, fps=30)
        first = await track.recv()
        second = await track.recv()
        self.assertEqual((first.width, first.height), (64, 48))
        self.assertEqual(first.time_base, VIDEO_TIME_BASE)
        self.assertGreater(second.pts, first.pts)
        track.stop()


class WebAppTests(AioHTTPTestCase):
    async def get_application(self):
        self.camera = FakeCamera()
        self.config = settings(devices=[self.camera.device], max_peers=1)
        return create_app(self.config, cameras=[self.camera])

    async def test_demo_page_health_and_offer(self):
        index = await self.client.get("/")
        self.assertEqual(index.status, 200)
        self.assertIn("Digital Twin WebRTC camera", await index.text())

        health = await self.client.get("/health")
        self.assertEqual(health.status, 200)
        health_body = await health.json()
        self.assertEqual(health_body["cameras"],
                         [{"device": self.camera.device, "ready": True}])

        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        received_frame = asyncio.get_running_loop().create_future()

        @peer.on("track")
        def on_track(track):
            async def receive_one():
                try:
                    frame = await track.recv()
                    if not received_frame.done():
                        received_frame.set_result(frame)
                except Exception as exc:
                    if not received_frame.done():
                        received_frame.set_exception(exc)

            asyncio.create_task(receive_one())

        try:
            peer.addTransceiver("video", direction="recvonly")
            offer = await peer.createOffer()
            await peer.setLocalDescription(offer)
            response = await self.client.post("/offer", json={
                "sdp": peer.localDescription.sdp,
                "type": peer.localDescription.type,
            })
            self.assertEqual(response.status, 200)
            answer = await response.json()
            self.assertEqual(answer["type"], "answer")
            self.assertIn("m=video", answer["sdp"])
            await peer.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            )
            frame = await asyncio.wait_for(received_frame, timeout=5)
            self.assertEqual((frame.width, frame.height), (64, 48))

            limited = await self.client.post("/offer", json={
                "sdp": peer.localDescription.sdp,
                "type": peer.localDescription.type,
            })
            self.assertEqual(limited.status, 503)
        finally:
            await peer.close()

    async def test_rejects_invalid_offer(self):
        response = await self.client.post("/offer", json={"type": "offer"})
        self.assertEqual(response.status, 400)

    async def test_cleanup_stops_camera(self):
        self.assertTrue(self.camera.started)

    async def asyncTearDown(self):
        camera = self.camera
        await super().asyncTearDown()
        self.assertTrue(camera.stopped)


if __name__ == "__main__":
    unittest.main()
