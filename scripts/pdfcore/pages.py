from __future__ import annotations

import re

from .errors import TaskError


def parse_pages(spec: str, n: int, name: str) -> list[int]:
    out: set[int] = set()
    for tok in re.split(r"[,;\s]+", spec.strip()):
        if not tok:
            continue
        m = re.fullmatch(r"(\d*)-(\d*)|(\d+)", tok)
        if not m:
            raise TaskError("e_range", spec=tok, name=name)
        if m.group(3):
            a = b = int(m.group(3))
        else:
            a, b = int(m.group(1) or 1), int(m.group(2) or n)
        if a < 1 or b > n or a > b:
            raise TaskError("e_range", spec=tok, name=name)
        out.update(range(a - 1, b))
    if not out:
        raise TaskError("e_empty")
    return sorted(out)
