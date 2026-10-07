"""Load and validate service configuration from YAML."""

from dataclasses import dataclass, fields
from digital_twin_common.config import load_yaml_mapping


@dataclass(frozen=True)
class Config:
    device: str
    host: str
    port: int
    width: int
    height: int
    fps: int
    quality: int
    max_clients: int
    retry_seconds: float
    stale_seconds: float
    backend: str
    capture_buffer_size: int
    opencv_threads: int
    shutdown_seconds: float
    http_spare_threads: int
    http_output_buffer_bytes: int

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if field.type is float:
                valid = type(value) in (int, float)
            else:
                valid = type(value) is field.type
            if not valid:
                raise ValueError(f"{field.name} must be {field.type.__name__}")
        if not self.device or not self.host:
            raise ValueError("Camera device and HTTP host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("HTTP port must be between 1 and 65535")
        if self.width < 1 or self.height < 1 or self.fps < 1:
            raise ValueError("Resolution and FPS must be positive")
        if not 1 <= self.quality <= 100:
            raise ValueError("JPEG quality must be between 1 and 100")
        for name in ("max_clients", "capture_buffer_size", "opencv_threads",
                     "http_spare_threads", "http_output_buffer_bytes"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.backend not in ("v4l2", "auto"):
            raise ValueError("Camera backend must be v4l2 or auto")
        if not 0 < self.shutdown_seconds < float('inf'):
            raise ValueError("Shutdown interval must be finite and positive")
        if not (0 < self.retry_seconds < float('inf') and 0 < self.stale_seconds < float('inf')):
            raise ValueError("Retry and stale intervals must be finite and positive")

    @classmethod
    def from_yaml(cls, path):
        data = load_yaml_mapping(path)
        expected = {field.name for field in fields(cls)}
        missing = expected - data.keys()
        unknown = data.keys() - expected
        if missing or unknown:
            raise ValueError(f"Invalid configuration keys: missing={sorted(missing)}, "
                             f"unknown={sorted(unknown, key=str)}")
        return cls(**data)
