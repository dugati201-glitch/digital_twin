# Gateway service

A Python service that communicates with the microcontroller over UART and bridges telemetry and commands through an external MQTT broker. This service implements Task 1 and the bridge logic of Task 3.

**Status:** not implemented. `src/` is reserved for application code.

## Responsibilities

- Open and manage the configured UART connection.
- Receive, validate, and decode sensor frames before publishing telemetry over MQTT.
- Receive MQTT commands, validate them, and encode UART frames for the microcontroller.
- Manage connection lifecycles and release the serial port on shutdown.

The broker runs on a separate server. Its hostname, port, TLS requirements, credentials, topic permissions, and WebSockets endpoint must be confirmed before integration. The service does not process video or deploy the broker. Frame and payload specifications must be agreed with the firmware and Web interface before implementation.

See [Containers](../../docs/02-containers.md), [Components](../../docs/03-components.md), and [Deployment](../../docs/deployment.md).
