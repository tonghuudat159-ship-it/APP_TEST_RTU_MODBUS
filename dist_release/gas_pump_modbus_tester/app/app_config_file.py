"""JSON config file loading and CLI-argument merge helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigFileError(ValueError):
    """Raised when an app config file cannot be loaded."""


def load_config_file(path: str | Path) -> dict:
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigFileError(f"failed to read config file {config_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigFileError(f"invalid JSON in config file {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigFileError(f"config file {config_path} must contain a JSON object")
    return data


def merge_config_with_args(
    config: dict,
    args,
    provided_options: set[str] | None = None,
) -> None:
    """Merge JSON config defaults into argparse namespace in place.

    `provided_options` contains normalized argparse attribute names explicitly
    provided on the command line. Those values always win over config defaults.
    """
    provided_options = provided_options or set()
    mapping: dict[str, tuple[str, Any]] = {
        "port": ("port", None),
        "baudrate": ("baudrate", int),
        "timeout": ("timeout", float),
        "slave_id": ("slave", int),
        "debug": ("debug", bool),
        "capture_txt": ("capture_txt", None),
        "capture_jsonl": ("capture_jsonl", None),
        "default_report_json": ("out", None),
        "default_report_txt": ("txt", None),
    }
    for config_key, (arg_name, caster) in mapping.items():
        if config_key not in config or not hasattr(args, arg_name):
            continue
        if arg_name in provided_options:
            continue
        value = config[config_key]
        if caster is not None:
            value = caster(value)
        setattr(args, arg_name, value)
