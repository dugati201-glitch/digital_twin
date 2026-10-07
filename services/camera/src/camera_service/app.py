"""Flask endpoints and a single-process Waitress server."""

import argparse
import os
import logging
import signal
import threading

from flask import Flask, Response, jsonify
from waitress import create_server

from digital_twin_common.logging import configure_logging

from .capture import Camera
from .config import Config


def create_app(camera, config):
    app = Flask(__name__)
    slots = threading.BoundedSemaphore(config.max_clients)

    @app.get('/health')
    def health():
        ready = camera.ready()
        return jsonify(status='ready' if ready else 'unavailable'), 200 if ready else 503

    @app.get('/video_feed')
    def video_feed():
        if not camera.ready():
            return jsonify(error='Camera unavailable'), 503
        if not slots.acquire(blocking=False):
            return jsonify(error='Stream client limit reached'), 503
        # Cleanup is idempotent and also runs if the iterable is never started.
        release_lock = threading.Lock()
        released = False

        def release():
            nonlocal released
            with release_lock:
                if not released:
                    released = True
                    slots.release()

        def stream():
            sequence = -1
            try:
                while True:
                    result = camera.wait_frame(sequence)
                    if result is None:
                        return
                    sequence, jpeg = result
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                           + str(len(jpeg)).encode('ascii') + b'\r\n\r\n' + jpeg + b'\r\n')
            finally:
                release()

        response = Response(stream(), content_type='multipart/x-mixed-replace; boundary=frame')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Accel-Buffering'] = 'no'
        response.call_on_close(release)
        return response

    return app


def main():
    parser = argparse.ArgumentParser(description="Camera HTTP MJPEG service")
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
    camera = Camera(config)
    server = create_server(create_app(camera, config), host=config.host, port=config.port,
                           threads=config.max_clients + config.http_spare_threads,
                           outbuf_high_watermark=config.http_output_buffer_bytes)

    def shutdown(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        camera.start()
        logging.getLogger(__name__).info('HTTP listening on %s:%s', config.host, config.port)
        server.run()
    finally:
        camera.stop()
        server.close()


if __name__ == '__main__':
    main()
