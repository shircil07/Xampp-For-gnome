"""Per-user preferences in ~/.config/xampp-panel/settings.json."""

import json
import os
from pathlib import Path

from . import fsutil

DEFAULTS = {"tray": False}


def config_path(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "xampp-panel" / "settings.json"


def load(path=None) -> dict:
    try:
        data = json.loads(Path(path or config_path()).read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {key: type(default)(data.get(key, default)) for key, default in DEFAULTS.items()}


def save(data: dict, path=None) -> None:
    path = Path(path or config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {key: data.get(key, default) for key, default in DEFAULTS.items()}
    fsutil.atomic_write(path, json.dumps(clean, indent=2) + "\n", mode=0o600)
