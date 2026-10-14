import asyncio
from dataclasses import replace
import time
import sys
from unittest.mock import patch
import unittest

from aiohttp import ClientSession
from aiohttp.test_utils import TestServer
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
import cv2
import numpy as np

from camera_service.app import create_app
from camera_service.mjpeg import JpegParser, LatestSource, RemoteJpegSource, UsbJpegSource
from camera_service.source_app import create_source_app
from camera_service.split_config import SplitConfig
from camera_service.track import CameraVideoTrack


class SimulatedUsb(LatestSource):
    async def run(self):
        color = (0, 0, 240) if self.device == 'camera1' else (0, 240, 0)
        _, encoded = cv2.imencode('.jpg', np.full((48, 64, 3), color, dtype=np.uint8))
        while True:
            await self.publish(encoded.tobytes())
            await asyncio.sleep(1 / 15)


class ConfigAndParserTests(unittest.TestCase):
    def test_capture_command_copies_mjpeg(self):
        config = SplitConfig('capture', [{'id': 'camera1', 'device': '/dev/video0'}])
        command = UsbJpegSource(config, config.cameras[0]).command()
        self.assertEqual(command[command.index('-input_format') + 1], 'mjpeg')
        self.assertEqual(command[command.index('-c:v') + 1], 'copy')

    def test_fragmented_jpegs_and_limit(self):
        parser = JpegParser(16)
        jpeg = b'\xff\xd8abc\xff\xd9'
        self.assertEqual(parser.feed(b'header\xff'), [])
        self.assertEqual(parser.feed(b'\xd8abc\xff'), [])
        self.assertEqual(parser.feed(b'\xd9' + jpeg), [jpeg, jpeg])
        with self.assertRaises(ValueError):
            parser.feed(b'\xff\xd8' + b'a' * 17)

    def test_invalid_config(self):
        base = SplitConfig('server', [{'id': 'camera1', 'url': 'http://pi:5001/video_feed'}])
        for changes in ({'fps': True}, {'role': 'bad'}, {'cameras': []},
                        {'stale_seconds': float('nan')}, {'port': 70000},
                        {'cameras': [{'id': 'a', 'url': 'file:///tmp/video'}]},
                        {'cameras': [base.cameras[0], base.cameras[0]]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(base, **changes)


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_with_live_mjpeg_request(self):
        config = SplitConfig('capture', [{'id': 'camera1', 'device': '/dev/video0'}])
        source = SimulatedUsb(config, config.cameras[0])
        pi = TestServer(create_source_app(config, [source]))
        await pi.start_server()
        try:
            await asyncio.wait_for(source.wait_frame(-1), 1)
            async with ClientSession() as client:
                async with client.get(pi.make_url('/video_feed')) as response:
                    self.assertEqual(response.status, 200)
                    await asyncio.wait_for(response.content.read(100), 1)
                    await asyncio.wait_for(pi.close(), 1)
                    self.assertTrue(source.closed)
                    self.assertTrue(source.task.done())
        finally:
            await pi.close()

    async def test_stats_measure_publish_rate_and_staleness(self):
        config = SplitConfig('capture', [{'id': 'camera1', 'device': '/dev/video0'}],
                             stale_seconds=1)
        source = LatestSource(config, config.cameras[0])
        with patch('camera_service.mjpeg.time.monotonic', return_value=10.0):
            await source.publish(b'a' * 1000)
        with patch('camera_service.mjpeg.time.monotonic', return_value=10.1):
            await source.publish(b'a' * 1000)
            self.assertEqual(source.stats()['fps'], 10.0)
            self.assertEqual(source.stats()['data_mbps'], 0.08)
        with patch('camera_service.mjpeg.time.monotonic', return_value=12.0):
            self.assertEqual(source.stats()['fps'], 0.0)
            self.assertFalse(source.ready())

    async def test_track_waits_for_ingest_recovery(self):
        config = SplitConfig('server', [{'id': 'camera1', 'url': 'http://pi/video_feed'}],
                             stale_seconds=0.02)
        source = LatestSource(config, config.cameras[0])
        track = CameraVideoTrack(source)
        waiting = asyncio.create_task(track.recv())
        try:
            await asyncio.sleep(0.07)
            self.assertFalse(waiting.done())
            await source.publish(np.zeros((48, 64, 3), dtype=np.uint8))
            frame = await asyncio.wait_for(waiting, 1)
            self.assertEqual((frame.width, frame.height), (64, 48))
        finally:
            track.stop()
            await source.stop()
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)

    async def test_capture_subprocess_streams_and_stops(self):
        config = SplitConfig('capture', [{'id': 'camera1', 'device': '/dev/video0'}],
                             stale_seconds=1)
        source = UsbJpegSource(config, config.cameras[0])
        original_spawn = asyncio.create_subprocess_exec
        processes = []

        async def spawn(*args, **kwargs):
            process = await original_spawn(
                sys.executable, '-u', '-c',
                "import sys,time; sys.stdout.buffer.write(bytes.fromhex('ffd8616263ffd9')); sys.stdout.flush(); time.sleep(30)",
                **kwargs)
            processes.append(process)
            return process

        with patch('camera_service.mjpeg.asyncio.create_subprocess_exec', spawn):
            source.start()
            try:
                frame = await source.wait_frame(-1)
                self.assertIsNotNone(frame)
                self.assertEqual(frame[1], bytes.fromhex('ffd8616263ffd9'))
            finally:
                await source.stop()
        self.assertIsNotNone(processes[0].returncode)
        self.assertFalse(source.ready())

    async def test_two_camera_http_to_webrtc_and_session_cleanup(self):
        capture = SplitConfig('capture', [
            {'id': 'camera1', 'device': '/dev/video0'},
            {'id': 'camera2', 'device': '/dev/video2'},
        ], stale_seconds=1)
        sources = [SimulatedUsb(capture, c) for c in capture.cameras]
        pi = TestServer(create_source_app(capture, sources))
        await pi.start_server()
        pc_config = SplitConfig('server', [
            {'id': c['id'], 'url': str(pi.make_url('/cameras/' + c['id'] + '/video_feed'))}
            for c in capture.cameras
        ], stale_seconds=1, max_peers=1, peer_timeout_seconds=1)
        pc = TestServer(create_app(pc_config))
        await pc.start_server()
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        received = []
        tasks = []

        @peer.on('track')
        def on_track(track):
            async def receive():
                frame = await track.recv()
                received.append(frame.to_ndarray(format='bgr24'))
            tasks.append(asyncio.create_task(receive()))

        try:
            async with ClientSession() as client:
                for _ in range(100):
                    async with client.get(pc.make_url('/health')) as response:
                        if response.status == 200:
                            break
                    await asyncio.sleep(0.02)
                else:
                    self.fail('PC did not receive both HTTP MJPEG sources')
                for _ in range(2):
                    peer.addTransceiver('video', direction='recvonly')
                await peer.setLocalDescription(await peer.createOffer())
                offer = {'sdp': peer.localDescription.sdp, 'type': 'offer'}
                async with client.post(pc.make_url('/offer'), json=offer) as response:
                    self.assertEqual(response.status, 200)
                    answer = await response.json()
                await peer.setRemoteDescription(RTCSessionDescription(
                    sdp=answer['sdp'], type=answer['type']))
                for _ in range(100):
                    if len(received) == 2:
                        break
                    await asyncio.sleep(0.02)
                self.assertEqual(len(received), 2)
                means = [image.mean(axis=(0, 1)) for image in received]
                self.assertTrue(any(mean[2] > 180 and mean[1] < 50 for mean in means))
                self.assertTrue(any(mean[1] > 180 and mean[2] < 50 for mean in means))
                async with client.post(pc.make_url('/offer'), json=offer) as response:
                    self.assertEqual(response.status, 503)
                session = '/sessions/' + answer['session_id']
                async with client.post(pc.make_url(session)) as response:
                    self.assertEqual(response.status, 204)
                async with client.delete(pc.make_url(session)) as response:
                    self.assertEqual(response.status, 204)
                async with client.get(pc.make_url('/health')) as response:
                    self.assertEqual((await response.json())['peers'], 0)
                # A negotiated peer that never finishes connecting expires.
                async with client.post(pc.make_url('/offer'), json=offer) as response:
                    self.assertEqual(response.status, 200)
                await asyncio.sleep(2.2)
                async with client.get(pc.make_url('/health')) as response:
                    self.assertEqual((await response.json())['peers'], 0)
        finally:
            await peer.close()
            await asyncio.gather(*tasks, return_exceptions=True)
            await pc.close()
            await pi.close()
        self.assertTrue(all(source.closed for source in sources))

    async def test_ingest_recovers_from_unavailable_source_and_stale(self):
        capture = SplitConfig('capture', [{'id': 'camera1', 'device': '/dev/video0'}],
                              stale_seconds=0.1)
        source = LatestSource(capture, capture.cameras[0])
        source.start = lambda: None
        pi = TestServer(create_source_app(capture, [source]))
        await pi.start_server()
        config = SplitConfig('server', [{'id': 'camera1', 'url': str(pi.make_url('/video_feed'))}],
                             retry_seconds=0.01, stale_seconds=0.1)
        remote = RemoteJpegSource(config, config.cameras[0])
        remote.start()
        try:
            await asyncio.sleep(0.03)
            self.assertFalse(remote.ready())
            _, jpeg = cv2.imencode('.jpg', np.zeros((48, 64, 3), dtype=np.uint8))
            await source.publish(jpeg.tobytes())
            for _ in range(100):
                if remote.ready():
                    break
                await asyncio.sleep(0.005)
            self.assertTrue(remote.ready())
            await asyncio.sleep(0.2)
            self.assertFalse(remote.ready())
            await source.publish(jpeg.tobytes())
            for _ in range(100):
                if remote.ready():
                    break
                await asyncio.sleep(0.005)
            self.assertTrue(remote.ready())
        finally:
            await remote.stop()
            await pi.close()


if __name__ == '__main__':
    unittest.main()
