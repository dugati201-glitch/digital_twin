# Gateway service

A C service using `libmosquitto` that communicates with the API Server through an external MQTT broker (`mqtt.mysignage.vn`) and bridges telemetry and commands according to the SRS v1.8 / MQTT guide v2.2 specification.

**Status:** implemented in C (`src/main.c`, `src/protocol.c`, `src/state.c`).

## Responsibilities

- Connect to MQTT broker `mqtt.mysignage.vn:1883` (configurable via `-h`, `-p`, or env `MQTT_BROKER_HOST`).
- Publish telemetry over MQTT to `lab/kit/{kit_code}/telemetry` at **2 Hz (500 ms)** while the kit is `in-use`.
- Publish periodic heartbeat to `lab/kit/{kit_code}/heartbeat` every **5.0 s** while the kit is `in-use` to sustain the server's 30-second watchdog.
- Subscribe to command topics `lab/kit/{kit_code}/cmd/+`:
  - `cmd/reset`: actions `start`, `stop`, `calib` (empty payload deprecated).
  - `cmd/power`: actions `on`, `off` for the AC coil power supply (does not shut down the kit).
  - `cmd/voltage`: discrete voltage levels `0, 3, 6, 9, 12` V.
  - `cmd/scale`: Tesla meter scale enum `"1.999"`, `"19.99"`, `"199.9"` mT.
  - `cmd/ruler`: absolute ruler position `0..300` mm.
  - `cmd/shutdown`: admin action to power off the kit and exit cleanly.
- Do not process or expect switch K (deprecated).
- Reflect actual physical states through 2 Hz telemetry; immediate telemetry feedback is sent upon valid commands.
- Provide solenoid physics simulation fallback when hardware is running in standalone mode.

## Build and Execution

### Prerequisites

```bash
sudo apt-get update
sudo apt-get install -y gcc make libmosquitto-dev
```

### Build

```bash
cd services/gateway
make
```
The executable binary will be created at `bin/gateway_client`.

### Unit Tests

```bash
make test
```

### Run

```bash
# Default (mqtt.mysignage.vn, kit KIT-001)
./bin/gateway_client

# With custom parameters
./bin/gateway_client -h mqtt.mysignage.vn -p 1883 -k KIT-001
```

See [Containers](../../docs/02-containers.md), [Components](../../docs/03-components.md), and [Deployment](../../docs/deployment.md).
