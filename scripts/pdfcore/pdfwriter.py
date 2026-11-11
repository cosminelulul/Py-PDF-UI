from __future__ import annotations

from typing import NamedTuple

DPI = 100.0
MAX_PAGE_PT = 14400.0


class Prepared(NamedTuple):
    kind: str
    data: bytes
    w: int
    h: int
    gray: bool
    rotate: int


class ImagePdfWriter:
    def __init__(self, path):
        self._f = open(path, "wb")
        self._f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        self._off: dict[int, int] = {}
        self._kids: list[int] = []
        self._next = 3

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._f.close()

    def _obj(self, num: int, body: bytes) -> None:
        self._off[num] = self._f.tell()
        self._f.write(b"%d 0 obj\n" % num + body + b"\nendobj\n")

    def _stream(self, num: int, entries: str, data: bytes) -> None:
        self._off[num] = self._f.tell()
        self._f.write(f"{num} 0 obj\n<< {entries} /Length {len(data)} >>\nstream\n".encode("ascii"))
        self._f.write(data)
        self._f.write(b"\nendstream\nendobj\n")

    def add_page(self, p: Prepared) -> None:
        dpi = max(DPI, max(p.w, p.h) * 72.0 / MAX_PAGE_PT)
        wpt, hpt = p.w * 72.0 / dpi, p.h * 72.0 / dpi
        img, content, page = self._next, self._next + 1, self._next + 2
        self._next += 3
        filt = "/DCTDecode" if p.kind == "jpeg" else "/FlateDecode"
        cs = "/DeviceGray" if p.gray else "/DeviceRGB"
        self._stream(img, f"/Type /XObject /Subtype /Image /Width {p.w} /Height {p.h} "
                          f"/ColorSpace {cs} /BitsPerComponent 8 /Filter {filt}", p.data)
        self._stream(content, "", f"q {wpt:.3f} 0 0 {hpt:.3f} 0 0 cm /Im0 Do Q".encode("ascii"))
        rot = f" /Rotate {p.rotate}" if p.rotate else ""
        self._obj(page, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {wpt:.3f} {hpt:.3f}] "
                         f"/Resources << /XObject << /Im0 {img} 0 R >> /ProcSet [/PDF /ImageB /ImageC] >> "
                         f"/Contents {content} 0 R{rot} >>").encode("ascii"))
        self._kids.append(page)

    def finish(self) -> None:
        kids = " ".join(f"{k} 0 R" for k in self._kids)
        self._obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(self._kids)} >>".encode("ascii"))
        self._obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
        xref, size = self._f.tell(), self._next
        out = [b"xref\n", b"0 %d\n" % size, b"0000000000 65535 f \n"]
        out += [b"%010d 00000 n \n" % self._off[n] for n in range(1, size)]
        out.append(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref))
        self._f.write(b"".join(out))
