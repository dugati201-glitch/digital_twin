# Digital Twin Edge Gateway

A Raspberry Pi 3B gateway connecting physical experiment equipment to a Web Digital Twin. The Pi receives measurements and sends commands over UART, provides a camera stream, and connects to an external MQTT broker for real-time communication with the Web interface.

## Status

The camera service implements WebRTC video using `aiortc`, HTTP offer/answer signaling, a browser demo, configuration validation, tests, and a systemd unit. WebRTC performance validation on Raspberry Pi 3B is pending. Gateway code and update logic have not been implemented.

## Services

| Service | Responsibility |
| --- | --- |
| Gateway | Python service for UART communication and MQTT bridging |
| Camera | Python service for OpenCV capture, HTTP signaling, and WebRTC video using `aiortc` |

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

Start with [docs/README.md](docs/README.md). Gateway `src/` contains a `.gitkeep` placeholder; camera source is in `services/camera/src/camera_service/`. The gateway unit and update script remain placeholders. The camera unit requires the installation paths and service account documented in services/camera/README.md.

Documentation under `docs/` is written in Vietnamese. Comments, configuration files, scripts, and README files outside `docs/` use English.
