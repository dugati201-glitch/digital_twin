"""Validated configuration for the Pi MJPEG source and PC server."""

from dataclasses import dataclass, fields
import math
from urllib.parse import urlsplit

from digital_twin_common.config import load_yaml_mapping


@dataclass(frozen=True)
class SplitConfig:
    role: str
    cameras: list[dict]
    host: str = "0.0.0.0"
    port: int = 5000
    width: int = 640
    height: int = 480
    fps: int = 15
    max_peers: int = 3
    vp8_threads: int = 2
    opencv_threads: int = 1
    retry_seconds: float = 2.0
    stale_seconds: float = 5.0
    shutdown_seconds: float = 3.0
    peer_timeout_seconds: float = 20.0
    max_frame_bytes: int = 4 * 1024 * 1024
    ffmpeg: str = "ffmpeg"

    def __post_init__(self):
        if self.role not in ("capture", "server"):
            raise ValueError("role must be capture or server")
        for name in ("host", "ffmpeg"):
            if type(getattr(self, name)) is not str or not getattr(self, name):
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("port", "width", "height", "fps", "max_peers",
                     "vp8_threads", "opencv_threads", "max_frame_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.port > 65535 or self.vp8_threads > 4:
            raise ValueError("port must be <=65535 and vp8_threads <=4")
        for name in ("retry_seconds", "stale_seconds", "shutdown_seconds",
                     "peer_timeout_seconds"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if type(self.cameras) is not list or not self.cameras:
            raise ValueError("cameras must be a non-empty list")
        location = "device" if self.role == "capture" else "url"
        ids, locations = set(), set()
        for camera in self.cameras:
            if type(camera) is not dict or set(camera) != {"id", location}:
                raise ValueError(f"each camera requires only id and {location}")
            camera_id, address = camera["id"], camera[location]
            if (type(camera_id) is not str or not camera_id
                    or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in camera_id)):
                raise ValueError("camera id must contain letters, digits, - or _")
            if type(address) is not str or not address:
                raise ValueError(f"{location} must be a non-empty string")
            if location == "url":
                parsed = urlsplit(address)
                if parsed.scheme not in ("http", "https") or not parsed.hostname:
                    raise ValueError("camera url must be HTTP or HTTPS")
            elif not address.startswith("/dev/"):
                raise ValueError("camera device must be a /dev/ path")
            if camera_id in ids or address in locations:
                raise ValueError("camera ids and locations must be unique")
            ids.add(camera_id)
            locations.add(address)

    @classmethod
    def from_yaml(cls, path):
        data = load_yaml_mapping(path)
        unknown = data.keys() - {field.name for field in fields(cls)}
        if unknown or not {"role", "cameras"} <= data.keys():
            raise ValueError(f"configuration requires role/cameras; unknown={sorted(unknown)}")
        return cls(**data)
