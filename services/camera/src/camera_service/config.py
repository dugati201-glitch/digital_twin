"""Load and validate camera WebRTC service configuration from YAML."""

from dataclasses import dataclass, fields
import math

from digital_twin_common.config import load_yaml_mapping


@dataclass(frozen=True)
class Config:
    devices: list[str]
    host: str
    port: int
    width: int
    height: int
    fps: int
    max_peers: int
    retry_seconds: float
    stale_seconds: float
    backend: str
    capture_buffer_size: int
    opencv_threads: int
    shutdown_seconds: float
    vp8_threads: int = 2

    def __post_init__(self):
        if (type(self.devices) is not list or not self.devices
                or any(type(device) is not str or not device for device in self.devices)):
            raise ValueError("devices must be a non-empty list of strings")
        if len(set(self.devices)) != len(self.devices):
            raise ValueError("devices must not contain duplicates")

        expected_types = {
            "host": str,
            "port": int,
            "width": int,
            "height": int,
            "fps": int,
            "max_peers": int,
            "retry_seconds": (int, float),
            "stale_seconds": (int, float),
            "backend": str,
            "capture_buffer_size": int,
            "opencv_threads": int,
            "shutdown_seconds": (int, float),
            "vp8_threads": int,
        }
        for name, expected in expected_types.items():
            value = getattr(self, name)
            allowed = expected if isinstance(expected, tuple) else (expected,)
            if type(value) not in allowed:
                type_name = "number" if isinstance(expected, tuple) else expected.__name__
                raise ValueError(f"{name} must be {type_name}")

        if not self.host:
            raise ValueError("HTTP host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("HTTP port must be between 1 and 65535")
        if self.width < 1 or self.height < 1 or self.fps < 1:
            raise ValueError("Resolution and FPS must be positive")
        for name in ("max_peers", "capture_buffer_size", "opencv_threads",
                     "vp8_threads"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.vp8_threads > 4:
            raise ValueError("vp8_threads must not exceed 4")
        if self.backend not in ("v4l2", "auto"):
            raise ValueError("Camera backend must be v4l2 or auto")
        for name in ("retry_seconds", "stale_seconds", "shutdown_seconds"):
            value = getattr(self, name)
            if not 0 < value < math.inf:
                raise ValueError(f"{name} must be finite and positive")

    @classmethod
    def from_yaml(cls, path):
        data = load_yaml_mapping(path)
        # Keep deployed configuration files from before this option compatible.
        data.setdefault("vp8_threads", 2)
        expected = {field.name for field in fields(cls)}
        missing = expected - data.keys()
        unknown = data.keys() - expected
        if missing or unknown:
            raise ValueError(f"Invalid configuration keys: missing={sorted(missing)}, "
                             f"unknown={sorted(unknown, key=str)}")
        return cls(**data)
