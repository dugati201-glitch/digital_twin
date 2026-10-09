"""aiortc video track backed by the latest OpenCV camera frame."""

import asyncio
from fractions import Fraction

from aiortc import VideoStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame

VIDEO_CLOCK_RATE = 90_000
VIDEO_TIME_BASE = Fraction(1, VIDEO_CLOCK_RATE)


class CameraVideoTrack(VideoStreamTrack):
    def __init__(self, camera, fps):
        super().__init__()
        self.camera = camera
        self._sequence = -1
        self._origin_sequence = None
        self._pts_step = max(1, round(VIDEO_CLOCK_RATE / fps))

    async def recv(self):
        result = await asyncio.to_thread(self.camera.wait_frame, self._sequence)
        if result is None:
            raise MediaStreamError

        self._sequence, image = result
        if self._origin_sequence is None:
            self._origin_sequence = self._sequence
        frame = VideoFrame.from_ndarray(image, format="bgr24")
        frame.pts = (self._sequence - self._origin_sequence) * self._pts_step
        frame.time_base = VIDEO_TIME_BASE
        return frame
