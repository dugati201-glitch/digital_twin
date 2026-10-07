import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

import cv2
import numpy as np

from camera_service.app import create_app
from camera_service.capture import Camera
from camera_service.config import Config


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
        return (False, None) if self.fail else (True, np.zeros((24, 32, 3), dtype=np.uint8))

    def release(self):
        self.released.set()


class CameraTests(unittest.TestCase):
    def test_capture_resize_stream_limit_and_cleanup(self):
        config = settings(width=64, height=48, max_clients=1)
        capture = FakeCapture()
        camera = Camera(config, lambda: capture)
        camera.start()
        try:
            result = camera.wait_frame(-1)
            self.assertIsNotNone(result)
            image = cv2.imdecode(np.frombuffer(result[1], dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertEqual(image.shape[:2], (48, 64))
            app = create_app(camera, config)
            with app.test_client() as client:
                self.assertEqual(client.get('/health').status_code, 200)
                response = client.get('/video_feed', buffered=False)
                self.assertIn(b'Content-Type: image/jpeg', next(response.response))
                self.assertEqual(client.get('/video_feed').status_code, 503)
                response.close()
                second = client.get('/video_feed', buffered=False)
                self.assertEqual(second.status_code, 200)
                second.close()
        finally:
            camera.stop()
        self.assertTrue(capture.released.is_set())
        self.assertFalse(camera._thread.is_alive())

    def test_failed_capture_reopens(self):
        config = settings(retry_seconds=0.01, stale_seconds=0.5)
        failed, recovered = FakeCapture(fail=True), FakeCapture()
        captures = iter([failed, recovered])
        camera = Camera(config, lambda: next(captures))
        camera.start()
        try:
            self.assertIsNotNone(camera.wait_frame(-1))
            self.assertTrue(failed.released.is_set())
        finally:
            camera.stop()
        self.assertTrue(recovered.released.is_set())

    def test_unavailable_and_stale_frames(self):
        config = settings(stale_seconds=0.01)
        camera = Camera(config)
        client = create_app(camera, config).test_client()
        self.assertEqual(client.get('/health').status_code, 503)
        self.assertEqual(client.get('/video_feed').status_code, 503)
        with camera._condition:
            camera._jpeg = b'old'
            camera._sequence = 1
            camera._updated = time.monotonic() - 1
        self.assertIsNone(camera.wait_frame(-1))
        self.assertFalse(camera.ready())

    def test_yaml_overrides_and_invalid_files(self):
        source = Path(__file__).resolve().parents[1] / "config.yaml"
        data = yaml.safe_load(source.read_text())
        data.update(width=1280, height=720, fps=30, backend="auto")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "camera.yaml"
            path.write_text(yaml.safe_dump(data))
            config = Config.from_yaml(path)
            self.assertEqual((config.width, config.height, config.fps), (1280, 720, 30))
            self.assertEqual(config.backend, "auto")
            for content in ["", "[]", "[", yaml.safe_dump({**data, "fps": True}),
                            yaml.safe_dump({**data, "port": "5000"}),
                            yaml.safe_dump({**data, "extra": 1}),
                            yaml.safe_dump({k: v for k, v in data.items() if k != "device"})]:
                path.write_text(content)
                with self.subTest(content=content), self.assertRaises(ValueError):
                    Config.from_yaml(path)
            with self.assertRaises(ValueError):
                Config.from_yaml(Path(directory) / "missing.yaml")

    def test_invalid_configuration(self):
        for overrides in [dict(fps=0), dict(width=0), dict(port=65536),
                         dict(retry_seconds=float('nan')), dict(max_clients=0),
                         dict(backend='unknown'), dict(shutdown_seconds=0),
                         dict(http_spare_threads=0)]:
            with self.subTest(settings=overrides), self.assertRaises(ValueError):
                settings(**overrides)


if __name__ == '__main__':
    unittest.main()
