from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PyPDF UI"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent.parent


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "pypdf-UI"


def config_path() -> Path:
    return config_dir() / "settings.json"


def legacy_config_path() -> Path | None:
    return None if is_frozen() else resource_dir() / "settings.json"


def default_folder() -> Path:
    base = Path(sys.executable).parent if is_frozen() else resource_dir()
    return base if os.access(base, os.W_OK) else Path.home()
