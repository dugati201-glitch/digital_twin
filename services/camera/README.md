# Camera service

OpenCV/V4L2 camera capture with WebRTC video provided by `aiortc`. An `aiohttp` server provides the browser demo, readiness endpoint, and one-shot HTTP offer/answer signaling. Video frames are carried only by WebRTC.

**Status:** implemented and covered by simulated-camera WebRTC negotiation tests. USB camera compatibility was validated with the previous capture path; WebRTC CPU, temperature, sustained FPS, bitrate, and latency still require measurement on the Raspberry Pi 3B.

## Demo contract

- `GET /`: browser demo with a Start/Stop control and one `video` element per camera.
- `GET /health`: JSON readiness; HTTP 200 only when every configured camera has a fresh frame.
- `POST /offer`: accepts `{"sdp": "...", "type": "offer"}` and returns an SDP answer.
- The browser is the offerer and waits for ICE gathering before the request.
- The LAN demo uses `RTCConfiguration(iceServers=[])`, no STUN/TURN, no trickle ICE, and one peer by default.
- Video uses WebRTC/SRTP. HTTP carries HTML, JavaScript, health, and signaling only.

The initial profile targets one camera at 640x480, 30 FPS. Capture and WebRTC tracks use latest-frame behavior: intermediate frames are dropped instead of queued when a consumer falls behind. Add `/dev/video1` to `devices` for the future two-camera benchmark; 2 x 30 FPS is not a guaranteed Pi 3B capability.

## Install and run

Python 3.10 or newer is required by the selected current `aiortc` release.

On a development machine:

```bash
python3 -m venv services/camera/.venv
services/camera/.venv/bin/python -m pip install -e shared -e 'services/camera[opencv]'
services/camera/.venv/bin/digital-twin-camera \
  --config services/camera/config.yaml \
  --log-config config/logging.yaml
```

On Raspberry Pi OS, use the system OpenCV package to avoid building OpenCV:

```bash
sudo apt-get install python3-venv python3-opencv
python3 -m venv --system-site-packages services/camera/.venv
services/camera/.venv/bin/python -m pip install -e shared -e services/camera
services/camera/.venv/bin/digital-twin-camera \
  --config services/camera/config.yaml \
  --log-config config/logging.yaml
```

`aiortc` depends on PyAV and cryptographic media packages. Installation availability depends on the Pi OS Python version and architecture; verify `python3 --version` and `uname -m` on the target. A 64-bit current Raspberry Pi OS installation has the simplest dependency path. Do not assume a development-machine wheel is usable on the Pi.

Open the service from a computer on the same LAN:

```text
http://<PI_IP>:5000/
```

Click **Start** to create the peer connection. The old `/video_feed` endpoint no longer exists.

## Configuration

Settings are stored in [config.yaml](config.yaml). All fields are required and unknown fields fail startup.

| Field | Purpose |
| --- | --- |
| `devices` | Ordered Linux camera device list; one WebRTC video track per device |
| `host` / `port` | HTTP demo, health, and signaling listener |
| `width` / `height` / `fps` | Requested capture profile |
| `max_peers` | Maximum simultaneous browser peer connections |
| `retry_seconds` | Delay before reopening a failed camera |
| `stale_seconds` | Maximum frame age and frame wait timeout |
| `backend` | OpenCV `v4l2` or `auto` backend |
| `capture_buffer_size` | Requested driver buffer count |
| `opencv_threads` | OpenCV worker thread limit |
| `shutdown_seconds` | Camera capture thread join timeout |

Driver properties are requests. Rejected values are logged, and frames are resized to the configured output size when needed. Configuration changes require a service restart.

## systemd deployment

The unit assumes the repository is installed at `/opt/digital_twin` and the virtual environment is at `/opt/digital_twin/services/camera/.venv`.

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

When upgrading from the MJPEG implementation, reinstall both the Python package and `/etc/digital-twin/camera.yaml` before restarting. The old YAML schema is intentionally rejected.

## Tests

```bash
services/camera/.venv/bin/python -m unittest discover -s services/camera/tests -v
```

Tests cover raw-frame capture, resize, stale frames, reopen after failure, YAML validation, video-track timestamps, HTTP validation, peer limits, SDP negotiation, ICE/DTLS connection, WebRTC frame delivery, and cleanup. Hardware performance still needs target testing.

Logging initialization and YAML loading come from `digital-twin-common` in `shared/`. Logging settings remain in [config/logging.yaml](../../config/logging.yaml).

See [Camera WebRTC integration](../../docs/04-camera-webrtc.md), [Components](../../docs/03-components.md), and [Deployment](../../docs/deployment.md).
