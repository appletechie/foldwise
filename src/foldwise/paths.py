"""Where foldwise keeps its config and state. FOLDWISE_HOME puts both under one folder (tests, portable installs)."""
import os
from pathlib import Path

from platformdirs import user_config_path, user_data_path

APP = "foldwise"


def _home() -> Path | None:
    value = os.environ.get("FOLDWISE_HOME")
    return Path(value) if value else None


def config_file() -> Path:
    base = _home()
    return (base / "config" if base else user_config_path(APP)) / "taxonomy.yaml"


def state_dir() -> Path:
    base = _home()
    d = base / "state" if base else user_data_path(APP)
    d.mkdir(parents=True, exist_ok=True)
    return d


def sub(name: str) -> Path:
    d = state_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d
