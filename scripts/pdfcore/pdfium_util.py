from __future__ import annotations

import threading
from contextlib import suppress
from pathlib import Path

import pypdfium2 as pdfium

from .errors import TaskError

PDFIUM_LOCK = threading.RLock()
_cache: dict = {"path": None, "doc": None}


def open_pdf(path) -> pdfium.PdfDocument:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(2, "No such file", str(p))
    try:
        return pdfium.PdfDocument(str(p))
    except pdfium.PdfiumError as e:
        raise TaskError("e_encrypted" if "password" in str(e).lower() else "e_pdf", name=p.name) from e


def count_pages(path) -> int:
    with PDFIUM_LOCK:
        doc = open_pdf(path)
        try:
            return len(doc)
        finally:
            doc.close()


def page_sizes(path) -> list[tuple[float, float]]:
    with PDFIUM_LOCK:
        doc = open_pdf(path)
        try:
            return [doc.get_page_size(i) for i in range(len(doc))]
        finally:
            doc.close()


def cached_doc(path: str) -> pdfium.PdfDocument:
    if _cache["path"] != path:
        close_cache()
        _cache["doc"] = open_pdf(path)
        _cache["path"] = path
    return _cache["doc"]


def close_cache() -> None:
    with PDFIUM_LOCK:
        doc, _cache["doc"], _cache["path"] = _cache["doc"], None, None
        if doc is not None:
            with suppress(Exception):
                doc.close()
