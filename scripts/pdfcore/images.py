from __future__ import annotations

import io
import zlib
from pathlib import Path

from PIL import Image, ImageOps

from .errors import TaskError
from .pdfwriter import Prepared

RATE_DEFAULT = 70
_ROTATE = {3: 180, 6: 90, 8: 270}
_ORIENT_TAG = 0x0112
_HIGH_BIT_MODES = {"I", "I;16", "I;16L", "I;16B", "I;16N"}


def rate_to_quality(rate: int) -> int | None:
    rate = max(0, min(100, int(rate)))
    return None if rate == 0 else 95 - (65 * rate) // 100


def _short(e: BaseException) -> str:
    return " ".join(str(e).split())[:160] or type(e).__name__


def prepare_image(path: str, rate: int) -> Prepared:
    quality = rate_to_quality(rate)
    try:
        with Image.open(path) as im:
            return _prepare(im, path, quality)
    except (TaskError, MemoryError):
        raise
    except Exception as e:
        raise TaskError("e_image", name=Path(path).name, e=_short(e)) from e


def _jpeg_bytes(im: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _prepare(im: Image.Image, path: str, quality: int | None) -> Prepared:
    fmt, mode = im.format, im.mode
    orient = im.getexif().get(_ORIENT_TAG, 1)

    if fmt == "JPEG" and mode in ("RGB", "L") and orient in (0, 1, 3, 6, 8):
        raw = Path(path).read_bytes()
        data = raw
        if quality is not None:
            im.load()
            smaller = _jpeg_bytes(im, quality)
            if len(smaller) < len(raw):
                data = smaller
        return Prepared("jpeg", data, im.width, im.height, mode == "L", _ROTATE.get(orient, 0))

    if 2 <= orient <= 8:
        im = ImageOps.exif_transpose(im)
    mode = im.mode
    if mode in _HIGH_BIT_MODES:
        im = im.point(lambda p: p * (1 / 256)).convert("L")
    elif mode in ("RGBA", "LA", "PA", "RGBa", "La") or (mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, "white")
        flat.paste(rgba, mask=rgba.getchannel("A"))
        im = flat
    elif mode == "1":
        im = im.convert("L")
    elif mode != "L":
        im = im.convert("RGB")

    q = quality if quality is not None else (95 if fmt == "JPEG" else None)
    if q is None:
        return Prepared("flate", zlib.compress(im.tobytes(), 6), im.width, im.height, im.mode == "L", 0)
    return Prepared("jpeg", _jpeg_bytes(im, q), im.width, im.height, im.mode == "L", 0)


def prepare_job(job, progress=None) -> Prepared:
    return prepare_image(job[0], job[1])
