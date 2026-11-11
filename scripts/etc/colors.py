from __future__ import annotations

import colorsys
import math
import re
from functools import lru_cache
from typing import NamedTuple

from PIL import Image, ImageChops, ImageDraw

DEFAULT_ACCENT_LIGHT = "#3B5BDB"
SURFACE_LIGHT = "#FFFFFF"
SURFACE_DARK = "#1C1D21"
INK = "#16181D"
MAX_INPUT_LEN = 48
MIN_CONTRAST = 3.0

_HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})", re.ASCII)
_N = r"(\d{1,3})"
_SEP = r"\s*[,;\s]\s*"
_TRIPLET = re.compile(
    rf"rgb\s*\(\s*{_N}{_SEP}{_N}{_SEP}{_N}\s*\)|{_N}{_SEP}{_N}{_SEP}{_N}", re.ASCII | re.IGNORECASE
)
_CHANNEL = re.compile(r"\d{1,3}", re.ASCII)


class Accent(NamedTuple):
    main: tuple[str, str]
    hover: tuple[str, str]
    soft: tuple[str, str]
    on: tuple[str, str]
    on_disabled: tuple[str, str]


DEFAULT_PALETTE = Accent(
    main=("#3B5BDB", "#5B7CFA"),
    hover=("#2F4AC0", "#7490FF"),
    soft=("#E7ECFF", "#252C4D"),
    on=("#FFFFFF", "#FFFFFF"),
    on_disabled=("#C9D3FF", "#C9D3FF"),
)


def parse_hex(text: str) -> tuple[int, int, int] | None:
    if not isinstance(text, str) or len(text) > MAX_INPUT_LEN:
        return None
    m = _HEX.fullmatch(text.strip())
    if not m:
        return None
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def parse_channel(text: str) -> int | None:
    if not isinstance(text, str) or len(text) > MAX_INPUT_LEN:
        return None
    t = text.strip()
    if not _CHANNEL.fullmatch(t):
        return None
    v = int(t)
    return v if 0 <= v <= 255 else None


def parse_triplet(text: str) -> tuple[int, int, int] | None:
    if not isinstance(text, str) or len(text) > MAX_INPUT_LEN:
        return None
    m = _TRIPLET.fullmatch(text.strip())
    if not m:
        return None
    parts = [g for g in m.groups() if g is not None]
    r, g, b = (int(v) for v in parts)
    return (r, g, b) if max(r, g, b) <= 255 else None


def parse_color(text: str) -> tuple[int, int, int] | None:
    return parse_hex(text) or parse_triplet(text)


def to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def normalize_hex(text) -> str | None:
    rgb = parse_hex(text) if isinstance(text, str) else None
    return to_hex(rgb) if rgb else None


def canonical_accent(text) -> str:
    h = normalize_hex(text)
    return "" if h is None or h == DEFAULT_ACCENT_LIGHT else h


def mix_hex(a: str, b: str, t: float) -> str:
    ca, cb = parse_hex(a), parse_hex(b)
    if ca is None or cb is None:
        raise ValueError(f"culoare invalidă: {a!r} / {b!r}")
    return to_hex(tuple(round(x + (y - x) * t) for x, y in zip(ca, cb)))


def luminance(color: str) -> float:
    rgb = parse_hex(color)
    if rgb is None:
        raise ValueError(f"culoare invalidă: {color!r}")
    lin = [(v / 255) / 12.92 if v / 255 <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(color: str, background: str, minimum: float = MIN_CONTRAST) -> str:
    if contrast_ratio(color, background) >= minimum:
        return color
    target = "#000000" if luminance(background) > 0.5 else "#FFFFFF"
    out = color
    for step in range(1, 26):
        out = mix_hex(color, target, step * 0.04)
        if contrast_ratio(out, background) >= minimum:
            return out
    return target


def readable_on(fill: str) -> str:
    return "#FFFFFF" if contrast_ratio("#FFFFFF", fill) >= contrast_ratio(INK, fill) else INK


def derive_accent(value: str) -> Accent:
    base = normalize_hex(value) if value else None
    if base is None or base == DEFAULT_ACCENT_LIGHT:
        return DEFAULT_PALETTE
    light = ensure_contrast(base, SURFACE_LIGHT)
    dark = ensure_contrast(mix_hex(light, "#FFFFFF", 0.18), SURFACE_DARK)
    on_light, on_dark = readable_on(light), readable_on(dark)
    return Accent(
        main=(light, dark),
        hover=(mix_hex(light, "#000000", 0.15), mix_hex(dark, "#FFFFFF", 0.15)),
        soft=(mix_hex(light, SURFACE_LIGHT, 0.88), mix_hex(SURFACE_DARK, dark, 0.16)),
        on=(on_light, on_dark),
        on_disabled=(mix_hex(light, on_light, 0.7), mix_hex(dark, on_dark, 0.7)),
    )


def rgb_to_hsv(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(*(v / 255 for v in rgb))


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return round(r * 255), round(g * 255), round(b * 255)


def point_to_hs(x: float, y: float, cx: float, cy: float, radius: float) -> tuple[float, float]:
    dx, dy = x - cx, cy - y
    dist = math.hypot(dx, dy)
    hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
    return hue, min(1.0, dist / radius) if radius > 0 else 0.0


def hs_to_point(h: float, s: float, cx: float, cy: float, radius: float) -> tuple[float, float]:
    ang = h * 2 * math.pi
    return cx + math.cos(ang) * s * radius, cy - math.sin(ang) * s * radius


@lru_cache(maxsize=4)
def _base_wheel(size: int) -> Image.Image:
    half = size / 2
    hue, sat = bytearray(size * size), bytearray(size * size)
    two_pi = 2 * math.pi
    xs = [(px + 0.5) - half for px in range(size)]
    i = 0
    for py in range(size):
        dy = half - (py + 0.5)
        for dx in xs:
            dist = math.hypot(dx, dy) / half
            hue[i] = int(((math.atan2(dy, dx) / two_pi) % 1.0) * 255)
            sat[i] = 255 if dist >= 1.0 else int(dist * 255)
            i += 1
    channels = (
        Image.frombytes("L", (size, size), bytes(hue)),
        Image.frombytes("L", (size, size), bytes(sat)),
        Image.new("L", (size, size), 255),
    )
    img = Image.merge("HSV", channels).convert("RGBA")
    edge = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(edge).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    img.putalpha(edge.resize((size, size), Image.Resampling.LANCZOS))
    return img


def wheel_image(size: int, value: float = 1.0) -> Image.Image:
    size = max(32, min(int(size), 1024))
    base = _base_wheel(size)
    v = max(0.0, min(1.0, value))
    if v >= 0.999:
        return base.copy()
    shade = Image.new("RGB", (size, size), (round(255 * v),) * 3)
    out = ImageChops.multiply(base.convert("RGB"), shade).convert("RGBA")
    out.putalpha(base.getchannel("A"))
    return out
