"""Shared YAML mapping loader; service schemas remain service-specific."""

from pathlib import Path

import yaml


def load_yaml_mapping(path):
    config_path = Path(path)
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to read configuration {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping")
    return data
