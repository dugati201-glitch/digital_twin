# Camera service

OpenCV V4L2 capture, JPEG encoding, and Flask MJPEG endpoints served by Waitress. One capture thread opens the device and shares the latest encoded frame with all clients. Slow clients skip frames rather than accumulating a capture queue.

**Status:** initial implementation; physical camera compatibility and Raspberry Pi 3B performance still require validation.

## Run locally

From the repository root, on a development machine with available OpenCV wheels:

```bash
python3 -m venv services/camera/.venv
services/camera/.venv/bin/pip install -e shared -e 'services/camera[opencv]'
services/camera/.venv/bin/digital-twin-camera --config services/camera/config.yaml --log-config config/logging.yaml
```

For Raspberry Pi OS, especially 32-bit installations, use the system OpenCV package instead of building a pip wheel:

```bash
sudo apt-get install python3-venv python3-opencv
python3 -m venv --system-site-packages services/camera/.venv
services/camera/.venv/bin/pip install -e shared -e services/camera
services/camera/.venv/bin/digital-twin-camera --config services/camera/config.yaml --log-config config/logging.yaml
```

Python 3.9 or newer is required. The default backend supports V4L2 devices such as USB webcams; CSI cameras requiring libcamera/Picamera2 need a separate capture implementation.

## Configuration

Settings are stored in [config.yaml](config.yaml), separate from Python code. The committed file contains the initial Pi 3B profile. Copy it to a deployment-specific file and edit that file for each device. Local `config.local.yaml` files are ignored by Git.

Python only reads the YAML, validates its keys and types, and constructs the immutable `Config` object. All fields are required; missing fields, unknown fields, invalid types, or invalid values fail startup before camera access or HTTP binding. There are no operational defaults in Python and no per-setting environment overrides.

Select the file explicitly:

```bash
services/camera/.venv/bin/digital-twin-camera --config services/camera/config.yaml --log-config config/logging.yaml
```

Alternatively, use `CAMERA_CONFIG_FILE`:

```bash
CAMERA_CONFIG_FILE=services/camera/config.yaml LOG_CONFIG_FILE=config/logging.yaml services/camera/.venv/bin/digital-twin-camera
```

`--config` takes precedence over `CAMERA_CONFIG_FILE`. Relative paths are resolved from the working directory. Configuration changes require a service restart.

The initial profile uses `/dev/video0`, HTTP `0.0.0.0:5000`, 640×480, 15 FPS, JPEG quality 75, and four stream clients. Resolution and FPS are configurable positive values; measure Pi load before increasing them. Other settings cover retry/stale intervals, capture backend (`v4l2` or `auto`), driver buffer size, OpenCV threads, capture shutdown timeout, HTTP spare threads, HTTP output buffer size. `auto` does not add native libcamera support.

MJPEG format, HTTP status codes, JPEG quality range, and endpoint paths are protocol/API constants. Installation paths, service user, and systemd timeout are deployment settings in the unit file. Keep `TimeoutStopSec` longer than YAML `shutdown_seconds`.

Camera properties are requests to the driver. Rejected properties are logged; output frames are resized to the configured resolution. Driver capture resolution may still be higher, so measure CPU usage on the target device.

## HTTP endpoints

- `GET /video_feed`: MJPEG stream; returns 503 if the camera is unavailable or the stream client limit is reached.
- `GET /health`: JSON readiness, 200 for a fresh frame and 503 otherwise.

```html
<img src="http://<PI_IP>:5000/video_feed" alt="Live camera">
```

The service retries camera open/read failures every two seconds. Frames older than five seconds are unavailable. Existing streams close if no fresh frame arrives within that interval; the client must reconnect. Camera access and encoding happen once per frame, not once per client.

HTTP has no authentication or TLS in this initial implementation. Deploy on the intended local network. HTTPS Web interfaces need a compatible HTTPS video endpoint, typically through a reverse proxy with response buffering disabled.

## systemd deployment

The unit assumes the repository is installed at `/opt/digital_twin`, with the camera virtual environment at `/opt/digital_twin/services/camera/.venv`. Adjust paths if using another installation location. Create the service user and YAML configuration file:

```bash
sudo useradd --system --user-group --no-create-home --groups video digital-twin
sudo install -d /etc/digital-twin
sudo install -m 0644 services/camera/config.yaml /etc/digital-twin/camera.yaml
sudo install -m 0644 config/logging.yaml /etc/digital-twin/logging.yaml
sudo install -m 0644 deploy/systemd/digital-twin-camera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now digital-twin-camera.service
sudo journalctl -u digital-twin-camera.service -f
```

Ensure the service user can read the installation and execute its virtual environment. Do not place it under a home directory with this unit: `ProtectHome=true` blocks access. The user needs access to the camera through the `video` group. SIGINT/SIGTERM stops capture; systemd terminates the process if a driver blocks shutdown beyond ten seconds.

## Tests

```bash
services/camera/.venv/bin/python -m unittest discover -s services/camera/tests -v
```

Tests use injected camera frames to verify JPEG output, client limits, cleanup, reconnect, stale-frame handling, and YAML configuration validation. They do not replace testing on the physical Pi and camera.

See [Components](../../docs/03-components.md) and [Deployment](../../docs/deployment.md).

## Shared logging

Logging initialization and YAML loading are provided by the `digital-twin-common` package in `shared/`. Camera configuration contains only camera and HTTP settings. Logging settings live separately in [config/logging.yaml](../../config/logging.yaml).

Provide `--log-config` or `LOG_CONFIG_FILE`; the CLI option takes precedence. Missing or invalid logging configuration fails startup. The shared profile sends timestamp, level, module name, process ID, and message to stdout. systemd collects output in journald. Changing the logging YAML requires a service restart. Module code uses `logging.getLogger(__name__)`; it does not configure handlers or formatting.
