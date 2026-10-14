"""Latest-frame sources without queued media; Pi uses FFmpeg stream copy."""

import asyncio
import logging
import time

import aiohttp

log = logging.getLogger(__name__)


class JpegParser:
    """Split an FFmpeg MJPEG byte stream, with a hard memory bound."""

    def __init__(self, limit):
        self.limit = limit
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(b"\xff\xd8")
            if start < 0:
                self.buffer[:] = self.buffer[-1:]
                break
            if start:
                del self.buffer[:start]
            end = self.buffer.find(b"\xff\xd9", 2)
            if end < 0:
                if len(self.buffer) > self.limit:
                    raise ValueError("JPEG exceeds max_frame_bytes")
                break
            if end + 2 > self.limit:
                raise ValueError("JPEG exceeds max_frame_bytes")
            frames.append(bytes(self.buffer[:end + 2]))
            del self.buffer[:end + 2]
        return frames


class LatestSource:
    def __init__(self, config, camera):
        self.config = config
        self.device = camera["id"]
        self.location = camera.get("device", camera.get("url"))
        self.sequence = 0
        self.frame = None
        self.updated = 0.0
        self.condition = asyncio.Condition()
        self.task = None
        self.closed = False

    def ready(self):
        return (not self.closed and self.frame is not None
                and time.monotonic() - self.updated < self.config.stale_seconds)

    async def publish(self, frame):
        async with self.condition:
            self.frame = frame
            self.updated = time.monotonic()
            self.sequence += 1
            self.condition.notify_all()

    async def wait_frame(self, sequence):
        async with self.condition:
            try:
                await asyncio.wait_for(self.condition.wait_for(
                    lambda: self.closed or (self.sequence != sequence and self.ready())
                ), self.config.stale_seconds)
            except asyncio.TimeoutError:
                return None
            if not self.ready():
                return None
            return self.sequence, self.frame, self.updated

    def start(self):
        self.task = asyncio.create_task(self.run(), name=f"camera-{self.device}")

    async def stop(self):
        self.closed = True
        async with self.condition:
            self.condition.notify_all()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


class UsbJpegSource(LatestSource):
    def command(self):
        return [self.config.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning",
                "-f", "v4l2", "-input_format", "mjpeg",
                "-video_size", f"{self.config.width}x{self.config.height}",
                "-framerate", str(self.config.fps), "-i", self.location,
                "-an", "-c:v", "copy", "-f", "mjpeg", "pipe:1"]

    async def run(self):
        while not self.closed:
            process = None
            try:
                # stderr inherits journald/terminal; it cannot fill a pipe.
                process = await asyncio.create_subprocess_exec(
                    *self.command(), stdout=asyncio.subprocess.PIPE)
                parser = JpegParser(self.config.max_frame_bytes)
                log.info("MJPEG stream copy started for %s (%s)", self.device, self.location)
                while True:
                    chunk = await asyncio.wait_for(process.stdout.read(65536),
                                                   self.config.stale_seconds)
                    if not chunk:
                        raise RuntimeError("FFmpeg capture exited")
                    for jpeg in parser.feed(chunk):
                        await self.publish(jpeg)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Capture %s: %s; retrying", self.device, exc)
            finally:
                self.frame = None
                if process:
                    if process.returncode is None:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                    try:
                        await asyncio.wait_for(process.wait(), self.config.shutdown_seconds)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
            await asyncio.sleep(self.config.retry_seconds)


class RemoteJpegSource(LatestSource):
    async def run(self):
        # These imports are PC-only: capture on the Pi needs no OpenCV/aiortc.
        import cv2
        import numpy as np

        timeout = aiohttp.ClientTimeout(total=None, sock_connect=5,
                                       sock_read=self.config.stale_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while not self.closed:
                try:
                    async with session.get(self.location) as response:
                        response.raise_for_status()
                        if not response.headers.get("Content-Type", "").lower().startswith("multipart/"):
                            raise ValueError("source is not HTTP multipart MJPEG")
                        parser = JpegParser(self.config.max_frame_bytes)
                        async for chunk in response.content.iter_chunked(65536):
                            frames = parser.feed(chunk)
                            if not frames:
                                continue
                            # Decode only the newest JPEG in this chunk.
                            image = await asyncio.to_thread(
                                cv2.imdecode, np.frombuffer(frames[-1], dtype=np.uint8),
                                cv2.IMREAD_COLOR)
                            if image is None:
                                raise ValueError("invalid JPEG from source")
                            await self.publish(image)
                        raise RuntimeError("MJPEG source disconnected")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("Ingest %s: %s; retrying", self.device, exc)
                finally:
                    self.frame = None
                await asyncio.sleep(self.config.retry_seconds)
