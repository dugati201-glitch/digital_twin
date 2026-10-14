# Camera: Raspberry Pi → Ubuntu PC → browser

Implemented split pipeline for two USB cameras. The Pi uses FFmpeg V4L2 MJPEG stream copy (no JPEG decode/re-encode and no VP8). The PC ingests each HTTP MJPEG source once, decodes JPEG and uses aiortc to send two video tracks to the browser. LAN and ZeroTier are network options; SSH is only for administration.

Simulated tests verify two independent HTTP sources through real WebRTC frame delivery, reconnect, freshness and peer cleanup. Actual USB/FFmpeg performance and ZeroTier ICE still require hardware testing.

## Configuration

- Pi: `capture.yaml`, role `capture`, port 5001, camera IDs and Linux device paths.
- PC: `server.yaml` (also `config.yaml`), role `server`, port 5000, camera IDs and HTTP source URLs.
- `legacy.yaml`: old combined implementation configuration, retained for regression tests. It is not accepted by the new CLI.

IDs must match the intended sources. Do not assume `/dev/video1` is a second camera: many USB cameras also expose metadata nodes. The example `/dev/video2` must be checked. Prefer stable `/dev/v4l/by-id/...-video-index0` paths when available.

## Raspberry Pi setup

From `/opt/digital_twin`, after updating the repository:

```bash
sudo systemctl stop digital-twin-camera
sudo apt update
sudo apt install -y ffmpeg v4l-utils python3-venv
python3 -m venv services/camera/.venv
services/camera/.venv/bin/python -m pip install -e shared -e services/camera
v4l2-ctl --list-devices
ls -l /dev/v4l/by-id/
nano services/camera/capture.yaml
```

Check each actual camera node with `v4l2-ctl --device=/dev/videoX --list-formats-ext`. Both must support MJPG at the requested 640x480, 15 FPS. Edit `capture.yaml` accordingly.

Run manually first (keep this process running while testing):

```bash
services/camera/.venv/bin/digital-twin-camera \
  --config services/camera/capture.yaml --log-config config/logging.yaml
```

In another terminal:

```bash
curl http://localhost:5001/health
```

Both cameras should report ready. Source URLs:

```text
http://PI_IP:5001/cameras/camera1/video_feed
http://PI_IP:5001/cameras/camera2/video_feed
```

`/video_feed` is an alias for the first camera. A missing camera returns 503; an unknown ID returns 404. Camera failure triggers FFmpeg reopen with backoff. Slow HTTP consumers time out instead of blocking capture.

## Ubuntu PC setup

From the repository root on the PC:

```bash
python3 -m venv services/camera/.venv
services/camera/.venv/bin/python -m pip install -e shared -e 'services/camera[server]'
nano services/camera/server.yaml
```

Set both source URLs to the Pi's LAN IP for the initial test, or ZeroTier IP `10.147.19.87` when using the virtual network.

```bash
curl http://10.147.19.87:5001/health
services/camera/.venv/bin/digital-twin-camera \
  --config services/camera/server.yaml --log-config config/logging.yaml
```

Open `http://localhost:5000/` on the PC and click Start. Two labeled videos appear. Another authorized ZeroTier device can try `http://10.147.19.29:5000/`. Opening HTTP alone does not prove ICE media works; verify video separately.

The PC must remain running. `max_peers: 3` permits three browsers but is not a performance guarantee. Each camera/peer still has its own VP8 encoder on the PC. `vp8_threads` configures workers per encoder, not camera capture on the Pi.

## systemd

Both templates assume `/opt/digital_twin` and a `digital-twin` service account. On each host, ensure the account exists; on Pi it also needs group `video`:

```bash
sudo useradd --system --user-group --no-create-home digital-twin
sudo install -d /etc/digital-twin
sudo install -m 0644 config/logging.yaml /etc/digital-twin/logging.yaml
```

Skip `useradd` if the account already exists. Pi, after stopping the manually launched capture:

```bash
sudo usermod -aG video digital-twin
sudo install -m 0644 services/camera/capture.yaml /etc/digital-twin/camera-capture.yaml
sudo install -m 0644 deploy/systemd/digital-twin-camera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now digital-twin-camera
sudo journalctl -u digital-twin-camera -f
```

PC, if the repo is installed at `/opt/digital_twin`, after stopping the manual server:

```bash
sudo install -m 0644 services/camera/server.yaml /etc/digital-twin/camera-server.yaml
sudo install -m 0644 deploy/systemd/digital-twin-camera-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now digital-twin-camera-server
sudo journalctl -u digital-twin-camera-server -f
```

For a PC checkout under `/home`, running manually is simplest. The template uses `ProtectHome=true`; changing only its executable path to `/home/...` will not work. Deploy under `/opt` for this unit, or adapt its access policy deliberately.

The old `/etc/digital-twin/camera.yaml` is no longer used by the updated Pi unit. Restart after changing `/etc/digital-twin/camera-capture.yaml` or `camera-server.yaml` on the respective host. HTTP endpoints are unauthenticated demo endpoints: expose only to the intended LAN/authorized virtual network.

## PC endpoints and lifecycle

`GET /`, `GET /client.js`, `GET /health`, `POST /offer` serve demo/signaling. `/offer` returns SDP plus a random session token. The browser POSTs `/sessions/{token}` every 5 seconds; DELETE closes the peer on Stop/tab exit. Abandoned sessions expire after `peer_timeout_seconds` (20 seconds by default). ICE failed/disconnected/closed peers are also reclaimed.

HTTP ingest reconnects on source errors or read timeouts; stale sources make health/offer unavailable. Latest frames are shared without a per-viewer ingest queue. Timestamps use monotonic PC receive time, not camera hardware capture time.

## Tests

```bash
services/camera/.venv/bin/python -m unittest discover -s services/camera/tests -v
```

See [design](../../docs/04-camera-webrtc.md) and [deployment](../../docs/deployment.md).
