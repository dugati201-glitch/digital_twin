# Digital Twin Edge Gateway

A Raspberry Pi 3B gateway connecting physical experiment equipment to a Web Digital Twin. The Pi receives measurements and sends commands over UART, provides a camera stream, and connects to an external MQTT broker for real-time communication with the Web interface.

## Status

The camera service implements WebRTC video using `aiortc`, HTTP offer/answer signaling, a browser demo, configuration validation, tests, and a systemd unit. Pi tests showed high VP8 CPU load and stutter with multiple viewers. The new agreed design moves encoding to an Ubuntu PC: Pi serves camera-native MJPEG over HTTP, PC ingests it and serves aiortc/WebRTC. This split is implemented with two-camera HTTP-to-WebRTC tests; hardware benchmarking remains pending. The Pi unit runs MJPEG capture and a separate PC unit runs WebRTC. Gateway code and update logic have not been implemented.

## Services

| Service | Responsibility |
| --- | --- |
| Gateway | Python service for UART communication and MQTT bridging |
| Camera | Pi MJPEG stream copy + PC HTTP ingest/aiortc WebRTC server |

The MQTT broker runs on an external server and is not deployed by this repository. Its implementation and connection settings have not been confirmed. ESP32/STM32 firmware and the Web interface are also outside this repository.

## Structure

```text
digital_twin/
├── README.md
├── docs/
│   ├── README.md
│   ├── 01-context.md
│   ├── 02-containers.md
│   ├── 03-components.md
│   ├── 04-camera-webrtc.md
│   └── deployment.md
├── config/
│   └── logging.yaml
├── shared/                       # Shared Python package and tests
├── services/
│   ├── gateway/
│   │   ├── README.md
│   │   └── src/
│   └── camera/
│       ├── README.md
│       ├── src/
│       ├── tests/
│       ├── pyproject.toml
│       └── config.yaml
├── deploy/
│   └── systemd/
│       ├── digital-twin-gateway.service
│       └── digital-twin-camera.service
└── scripts/
    └── update.sh
```

Start with [docs/README.md](docs/README.md). Gateway `src/` contains a `.gitkeep` placeholder; camera source is in `services/camera/src/camera_service/`. The gateway unit and update script remain placeholders. The two camera units require installation paths and service accounts documented in services/camera/README.md.

Documentation under `docs/` is written in Vietnamese. Comments, configuration files, scripts, and README files outside `docs/` use English.
