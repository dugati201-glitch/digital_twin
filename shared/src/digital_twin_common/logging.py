"""Process-wide logging configuration shared by all Python services."""

import logging.config

from .config import load_yaml_mapping


def configure_logging(path):
    config = load_yaml_mapping(path)
    if config.get("version") != 1 or isinstance(config.get("version"), bool):
        raise ValueError("Logging configuration requires version: 1")
    if config.get("disable_existing_loggers") is not False:
        raise ValueError("Logging configuration requires disable_existing_loggers: false")
    if not isinstance(config.get("root"), dict) or not config["root"].get("handlers"):
        raise ValueError("Logging configuration requires root handlers")
    try:
        logging.config.dictConfig(config)
    except (ValueError, TypeError, AttributeError, ImportError) as exc:
        raise ValueError(f"Invalid logging configuration: {exc}") from exc
