from __future__ import annotations

import json
import os
from contextlib import suppress
from pathlib import Path

from . import paths
from .colors import canonical_accent

DEFAULTS = {"lang": "ro", "size": 14, "dark": True, "folder": "", "img_rate": 70, "accent": ""}
MAX_SETTINGS_BYTES = 64 * 1024


def _read_json(p: Path | None):
    try:
        if p is None or not p.is_file() or p.stat().st_size > MAX_SETTINGS_BYTES:
            return None
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _int_in(value, lo: int, hi: int, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return min(max(int(value), lo), hi)
    except (TypeError, ValueError, OverflowError):
        return default


def load_settings(valid_langs) -> dict:
    raw = _read_json(paths.config_path())
    if raw is None:
        raw = _read_json(paths.legacy_config_path())
    cfg = dict(DEFAULTS)
    if isinstance(raw, dict):
        cfg.update({k: raw[k] for k in DEFAULTS if k in raw})
    cfg["lang"] = cfg["lang"] if cfg["lang"] in valid_langs else DEFAULTS["lang"]
    cfg["size"] = _int_in(cfg["size"], 11, 20, DEFAULTS["size"])
    cfg["dark"] = cfg["dark"] if isinstance(cfg["dark"], bool) else DEFAULTS["dark"]
    cfg["img_rate"] = _int_in(cfg["img_rate"], 0, 100, DEFAULTS["img_rate"])
    cfg["accent"] = canonical_accent(cfg["accent"])
    folder = cfg["folder"] if isinstance(cfg["folder"], str) else ""
    try:
        cfg["folder"] = folder if folder and Path(folder).is_dir() else ""
    except (OSError, ValueError):
        cfg["folder"] = ""
    return cfg


def save_settings(cfg: dict) -> bool:
    target = paths.config_path()
    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), "utf-8")
        os.replace(tmp, target)
        return True
    except OSError:
        with suppress(OSError):
            tmp.unlink()
        return False
