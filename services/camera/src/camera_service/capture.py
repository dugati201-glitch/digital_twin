"""A single capture thread sharing the latest JPEG with all clients."""

import logging
import threading
import time

import cv2

log = logging.getLogger(__name__)


class Camera:
    def __init__(self, config, capture_factory=None):
        self.config = config
        backend = cv2.CAP_V4L2 if config.backend == "v4l2" else cv2.CAP_ANY
        self._factory = capture_factory or (lambda: cv2.VideoCapture(config.device, backend))
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread = None
        self._jpeg = None
        self._sequence = 0
        self._updated = 0.0

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Camera already started")
        cv2.setNumThreads(self.config.opencv_threads)
        self._thread = threading.Thread(target=self._run, name="camera-capture", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self._condition:
            self._jpeg = None
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=self.config.shutdown_seconds)
            if self._thread.is_alive():
                log.warning("Camera driver is still blocking; process shutdown will terminate capture")

    def ready(self):
        with self._condition:
            return self._fresh()

    def _fresh(self):
        return (not self._stop.is_set() and self._jpeg is not None
                and time.monotonic() - self._updated < self.config.stale_seconds)

    def wait_frame(self, sequence):
        with self._condition:
            self._condition.wait_for(
                lambda: self._stop.is_set() or (self._sequence != sequence and self._fresh()),
                timeout=self.config.stale_seconds,
            )
            if self._fresh() and self._sequence != sequence:
                return self._sequence, self._jpeg
            return None

    def _run(self):
        while not self._stop.is_set():
            cap = None
            try:
                cap = self._factory()
                if not cap.isOpened():
                    raise RuntimeError("Unable to open camera")
                for key, value in [(cv2.CAP_PROP_FRAME_WIDTH, self.config.width),
                                   (cv2.CAP_PROP_FRAME_HEIGHT, self.config.height),
                                   (cv2.CAP_PROP_FPS, self.config.fps),
                                   (cv2.CAP_PROP_BUFFERSIZE, self.config.capture_buffer_size)]:
                    if not cap.set(key, value):
                        log.warning("Camera rejected property %s=%s", key, value)
                log.info("Camera opened: %s; requested %sx%s at %s FPS", self.config.device,
                         self.config.width, self.config.height, self.config.fps)
                while not self._stop.is_set():
                    started = time.monotonic()
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        raise RuntimeError("Camera frame read failed")
                    if frame.shape[:2] != (self.config.height, self.config.width):
                        frame = cv2.resize(frame, (self.config.width, self.config.height))
                    ok, encoded = cv2.imencode('.jpg', frame,
                                              [cv2.IMWRITE_JPEG_QUALITY, self.config.quality])
                    if not ok:
                        raise RuntimeError("JPEG encoding failed")
                    with self._condition:
                        if self._stop.is_set():
                            break
                        self._jpeg = encoded.tobytes()
                        self._sequence += 1
                        self._updated = time.monotonic()
                        self._condition.notify_all()
                    self._stop.wait(max(0, 1 / self.config.fps - (time.monotonic() - started)))
            except Exception:
                log.exception("Capture failed; retrying in %s seconds", self.config.retry_seconds)
            finally:
                if cap is not None:
                    cap.release()
                with self._condition:
                    self._jpeg = None
                    self._condition.notify_all()
            self._stop.wait(self.config.retry_seconds)
