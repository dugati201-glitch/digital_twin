"""aiortc video track backed by the latest OpenCV camera frame."""

import asyncio
from fractions import Fraction

from aiortc import VideoStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame

VIDEO_CLOCK_RATE = 90_000
VIDEO_TIME_BASE = Fraction(1, VIDEO_CLOCK_RATE)


class CameraVideoTrack(VideoStreamTrack):
    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self._sequence = -1
        self._origin_time = None
        self._last_pts = -1

    async def recv(self):
        result = await asyncio.to_thread(self.camera.wait_frame, self._sequence)
        if result is None:
            raise MediaStreamError

        self._sequence, image, captured_at = result
        if self._origin_time is None:
            self._origin_time = captured_at
        pts = round((captured_at - self._origin_time) * VIDEO_CLOCK_RATE)
        # Clock resolution and synthetic test cameras can produce equal times.
        self._last_pts = max(self._last_pts + 1, pts)
        frame = VideoFrame.from_ndarray(image, format="bgr24")
        frame.pts = self._last_pts
        frame.time_base = VIDEO_TIME_BASE
        return frame
