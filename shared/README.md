# Shared Python utilities

`digital-twin-common` contains service-independent code:

- `config.load_yaml_mapping(path)`: read a YAML mapping without service-specific defaults.
- `logging.configure_logging(path)`: initialize process-wide logging using a standard Python `dictConfig` YAML file.

Camera capture, HTTP endpoints, and camera schema validation remain in `services/camera/`. Shared code does not import service packages. Each service installs this package into its own virtual environment and configures logging once at startup. Modules use `logging.getLogger(__name__)` and do not create their own handlers.

The shared logging profile is in `config/logging.yaml`. It defines level, format, date format, and output handlers. Console output is collected by systemd/journald. Module loggers, including third-party loggers, remain enabled; logger levels can be configured through the standard `loggers` section.

Logging configuration is trusted deployment configuration: Python `dictConfig` may instantiate classes specified in the file. It must not come from an untrusted HTTP request.

Run shared tests from the repository root:

```bash
services/camera/.venv/bin/python -m unittest discover -s shared/tests -v
```
