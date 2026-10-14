"""Role-aware command with lightweight imports on Raspberry Pi."""

import argparse
import logging
import os
import shutil

from aiohttp import web
from digital_twin_common.logging import configure_logging

from .split_config import SplitConfig


def main():
    parser = argparse.ArgumentParser(description="Pi MJPEG capture or PC WebRTC server")
    parser.add_argument("--config", default=os.getenv("CAMERA_CONFIG_FILE"))
    parser.add_argument("--log-config", default=os.getenv("LOG_CONFIG_FILE"))
    args = parser.parse_args()
    if not args.config or not args.log_config:
        parser.error("Provide --config and --log-config (or environment variables)")
    try:
        config = SplitConfig.from_yaml(args.config)
        configure_logging(args.log_config)
    except ValueError as exc:
        parser.error(str(exc))
    if config.role == "capture":
        if not shutil.which(config.ffmpeg):
            parser.error("FFmpeg not found; install it with sudo apt install ffmpeg")
        from .source_app import create_source_app
        app = create_source_app(config)
    else:
        from .app import create_app
        app = create_app(config)
    logging.getLogger(__name__).info("Camera %s HTTP on %s:%s", config.role,
                                     config.host, config.port)
    web.run_app(app, host=config.host, port=config.port, print=None,
                shutdown_timeout=config.shutdown_seconds)
