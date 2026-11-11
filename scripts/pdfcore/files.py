from __future__ import annotations

import os
import re
from contextlib import contextmanager, suppress
from pathlib import Path

IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif", ".gif"}
PDF_EXT = {".pdf"}


def natural_key(p: Path) -> list:
    return [int(t) if i % 2 else t.lower() for i, t in enumerate(re.split(r"(\d+)", p.name))]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(name: str, default: str, max_len: int = 120) -> str:
    s = _BAD_CHARS.sub("_", name.strip())[:max_len].strip(" .")
    if not s:
        return default
    if s.split(".")[0].upper() in _RESERVED:
        s = "_" + s
    return s


def _candidates(path: Path):
    yield path
    for i in range(1, 100_000):
        yield path.with_name(f"{path.stem}_{i}{path.suffix}")
    raise OSError(f"Nu găsesc un nume liber pentru {path.name}")


def claim_unique(path: Path) -> Path:
    for cand in _candidates(path):
        try:
            os.close(os.open(cand, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
            return cand
        except OSError:
            if cand.exists():
                continue
            raise
    raise AssertionError("unreachable")


def make_unique_dir(path: Path) -> Path:
    for cand in _candidates(path):
        try:
            cand.mkdir()
            return cand
        except FileExistsError:
            continue
    raise AssertionError("unreachable")


def part_path(final: Path) -> Path:
    return final.with_name(final.name + ".part")


def discard(*paths: Path) -> None:
    for p in paths:
        with suppress(OSError):
            p.unlink()


@contextmanager
def new_output(preferred: Path):
    final = claim_unique(preferred)
    tmp = part_path(final)
    try:
        yield final, tmp
        os.replace(tmp, final)
    except BaseException:
        discard(tmp, final)
        raise
