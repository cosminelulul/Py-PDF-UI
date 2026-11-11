from __future__ import annotations

import io
import math
import os
import re
from contextlib import suppress
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.errors import FileNotDecryptedError

from .errors import Cancelled, TaskError, check_cancel
from .files import claim_unique, discard, human, make_unique_dir, new_output, part_path
from .images import RATE_DEFAULT, prepare_job
from .pages import parse_pages
from .pdfium_util import PDFIUM_LOCK, cached_doc, close_cache, page_sizes
from .pdfwriter import ImagePdfWriter
from .runner import run_jobs
from .sysinfo import BYTES_PER_PIXEL, PROCESS_BASE_BYTES, choose_workers, render_pixel_limit

LEVELS = {"light": (85, 2600), "balanced": (70, 1700), "strong": (50, 1200)}
MIN_GAIN_RATIO = 0.99
PNG_COMPRESS_LEVEL = 1


def open_reader(path: Path) -> PdfReader:
    if not path.exists():
        raise FileNotFoundError(2, "No such file", str(path))
    try:
        reader = PdfReader(str(path))
        len(reader.pages)
    except FileNotDecryptedError as e:
        raise TaskError("e_encrypted", name=path.name) from e
    except MemoryError:
        raise
    except Exception as e:
        raise TaskError("e_pdf", name=path.name) from e
    return reader


def render_page_job(job, progress=None) -> bool:
    path, idx, final, scale = job[0], job[1], Path(job[2]), job[3]
    tmp = part_path(final)
    try:
        with PDFIUM_LOCK:
            page = cached_doc(path)[idx]
            bm = None
            try:
                bm = page.render(scale=scale)
                pil = bm.to_pil()
                if bm.mode == pil.mode:
                    pil = pil.copy()
            finally:
                if bm is not None:
                    bm.close()
                page.close()
        pil.save(tmp, format="PNG", compress_level=PNG_COMPRESS_LEVEL)
        os.replace(tmp, final)
        return True
    except BaseException:
        discard(tmp, final)
        raise


def task_pdf_to_png(files, o, report, cancel=None):
    scale = o["dpi"] / 72
    limit = render_pixel_limit()
    plans, total, max_px = [], 0, 0
    for f in files:
        check_cancel(cancel)
        sizes = page_sizes(f)
        if not sizes:
            raise TaskError("e_pdf", name=f.name)
        for i, (w, h) in enumerate(sizes):
            pw, ph = math.ceil(max(w, 1) * scale), math.ceil(max(h, 1) * scale)
            if pw * ph > limit:
                raise TaskError("e_toobig", name=f.name, page=i + 1, w=pw, h=ph, mp=limit // 1_000_000)
            max_px = max(max_px, pw * ph)
        plans.append((f, len(sizes)))
        total += len(sizes)

    jobs, dirs, out_dir = [], [], files[0].parent
    try:
        for f, n in plans:
            if n == 1:
                out_dir, names = f.parent, [f"{f.stem}.png"]
            else:
                out_dir = make_unique_dir(f.parent / f.stem)
                dirs.append(out_dir)
                names = [f"{f.stem}_{i + 1:03d}.png" for i in range(n)]
            for i, name in enumerate(names):
                jobs.append((str(f), i, str(claim_unique(out_dir / name)), scale, f.name, n))
    except BaseException:
        _cleanup(jobs, set(), dirs)
        raise

    done_idx: set[int] = set()

    def on_result(i, _res):
        done_idx.add(i)
        report(len(done_idx) / total, f"{jobs[i][4]}  ·  {jobs[i][1] + 1}/{jobs[i][5]}")

    workers = choose_workers(len(jobs), int(max_px * BYTES_PER_PIXEL) + PROCESS_BASE_BYTES, min_jobs=3)
    try:
        run_jobs(render_page_job, jobs, workers=workers, on_result=on_result, cancel=cancel)
    except BaseException:
        _cleanup(jobs, done_idx, dirs)
        raise
    finally:
        close_cache()
    return "d_png", {"n": total}, out_dir


def _cleanup(jobs, done_idx, dirs) -> None:
    for i, job in enumerate(jobs):
        if i not in done_idx:
            discard(Path(job[2]), part_path(Path(job[2])))
    for d in dirs:
        with suppress(OSError):
            d.rmdir()


def task_img_to_pdf(files, o, report, cancel=None):
    rate = int(o.get("img_rate", RATE_DEFAULT))
    jobs = [(str(f), rate) for f in files]
    px = 0
    for f in files:
        try:
            with Image.open(f) as im:
                px = max(px, im.width * im.height)
        except Exception:
            pass
    plain_jpeg = rate == 0 and all(f.suffix.lower() in (".jpg", ".jpeg") for f in files)
    workers = 0 if plain_jpeg else choose_workers(len(jobs), int(px * 8) + PROCESS_BASE_BYTES, min_jobs=4)

    final = claim_unique(files[0].parent / f"{o['name']}.pdf")
    tmp = part_path(final)
    try:
        with ImagePdfWriter(tmp) as pdf:
            def on_result(i, prepared):
                pdf.add_page(prepared)
                report((i + 1) / len(files), files[i].name)

            run_jobs(prepare_job, jobs, workers=workers, on_result=on_result, cancel=cancel, ordered=True)
            pdf.finish()
        os.replace(tmp, final)
    except BaseException:
        discard(tmp, final)
        raise
    return "d_file", {"name": final.name}, final.parent


def task_merge(files, o, report, cancel=None):
    with new_output(files[0].parent / f"{o['name']}.pdf") as (final, tmp), PdfWriter() as w:
        for i, f in enumerate(files):
            check_cancel(cancel)
            w.append(open_reader(f))
            report((i + 1) / len(files), f.name)
        check_cancel(cancel)
        w.write(tmp)
    return "d_file", {"name": final.name}, final.parent


def task_split(files, o, report, cancel=None):
    mode, arg = o["split_mode"], o["split_arg"].strip()
    step = 0
    if mode == "every":
        if not arg.isdigit() or int(arg) < 1:
            raise TaskError("e_num")
        step = int(arg)
    elif mode == "ranges" and not arg:
        raise TaskError("e_empty")
    created, out_dir = 0, files[0].parent
    for fi, f in enumerate(files):
        reader = open_reader(f)
        n = len(reader.pages)
        if mode == "each":
            groups = [[i] for i in range(n)]
        elif mode == "every":
            groups = [list(range(a, min(a + step, n))) for a in range(0, n, step)]
        else:
            groups = [parse_pages(t, n, f.name) for t in re.split(r"[,;]+", arg) if t.strip()]
        out_dir = make_unique_dir(f.parent / f"{f.stem}_split")
        w = len(str(n))
        try:
            for gi, g in enumerate(groups):
                check_cancel(cancel)
                a, b = g[0] + 1, g[-1] + 1
                label = f"{a:0{w}d}" if a == b else f"{a:0{w}d}-{b:0{w}d}"
                with new_output(out_dir / f"{f.stem}_{label}.pdf") as (_final, tmp), PdfWriter() as writer:
                    writer.append(reader, pages=g)
                    writer.write(tmp)
                created += 1
                report((fi + (gi + 1) / len(groups)) / len(files), f"{f.name}  ·  {label}")
        except BaseException:
            with suppress(OSError):
                out_dir.rmdir()
            raise
    return "d_split", {"n": created}, out_dir


def task_remove(files, o, report, cancel=None):
    spec = o["pages"].strip()
    if not spec:
        raise TaskError("e_empty")
    out_dir = files[0].parent
    for i, f in enumerate(files):
        check_cancel(cancel)
        reader = open_reader(f)
        n = len(reader.pages)
        drop = set(parse_pages(spec, n, f.name))
        keep = [k for k in range(n) if k not in drop]
        if not keep:
            raise TaskError("e_all", name=f.name)
        with new_output(f.with_name(f"{f.stem}_edited.pdf")) as (final, tmp), PdfWriter() as w:
            w.append(reader, pages=keep)
            w.write(tmp)
        out_dir = final.parent
        report((i + 1) / len(files), f.name)
    return "d_remove", {"n": len(files)}, out_dir


def _recompress_images(page, quality: int, max_side: int, seen: set) -> None:
    for img in page.images:
        ref = getattr(img, "indirect_reference", None)
        key = getattr(ref, "idnum", None)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        try:
            if len(img.data) < 20_000:
                continue
            pil = img.image
            if pil.mode == "CMYK":
                pil = pil.convert("RGB")
            if pil.mode not in ("RGB", "L"):
                continue
            scale = min(1.0, max_side / max(pil.size))
            if scale < 1:
                pil = pil.resize((round(pil.width * scale), round(pil.height * scale)), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            pil.save(buf, "JPEG", quality=quality, optimize=True)
            if buf.tell() < len(img.data):
                img.replace(pil, quality=quality)
        except Exception:
            continue


def compress_file_job(job, progress):
    src, final, quality, max_side, name = Path(job[0]), Path(job[1]), job[2], job[3], job[4]
    tmp = part_path(final)
    src_size = src.stat().st_size
    w = PdfWriter(clone_from=open_reader(src))
    try:
        n = len(w.pages)
        seen: set = set()
        for pi, page in enumerate(w.pages):
            _recompress_images(page, quality, max_side, seen)
            page.compress_content_streams()
            progress((pi + 1) / n, f"{name}  ·  {pi + 1}/{n}")
        if hasattr(w, "compress_identical_objects"):
            w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
        w.write(tmp)
    except BaseException:
        discard(tmp, final)
        raise
    finally:
        w.close()
    dst = tmp.stat().st_size
    try:
        ok = len(PdfReader(str(tmp)).pages) == n
    except Exception:
        ok = False
    if not ok or dst > src_size * MIN_GAIN_RATIO:
        discard(tmp, final)
        return src_size, src_size, False
    os.replace(tmp, final)
    return src_size, dst, True


def task_compress(files, o, report, cancel=None):
    quality, max_side = LEVELS[o["level"]]
    jobs: list = []
    try:
        for f in files:
            final = claim_unique(f.with_name(f"{f.stem}_compressed.pdf"))
            jobs.append((str(f), str(final), quality, max_side, f.name))
    except BaseException:
        _cleanup_files(jobs, set())
        raise

    n = len(jobs)
    frac = [0.0] * n
    state = {"before": 0, "after": 0, "out": files[0].parent, "kept": 0}
    done_idx: set[int] = set()

    def on_progress(i, fr, text):
        frac[i] = fr
        report(sum(frac) / n, text)

    def on_result(i, res):
        done_idx.add(i)
        frac[i] = 1.0
        state["before"] += res[0]
        state["after"] += res[1]
        if res[2]:
            state["kept"] += 1
            state["out"] = Path(jobs[i][1]).parent
        report(sum(frac) / n, files[i].name)

    biggest = max(f.stat().st_size for f in files)
    workers = choose_workers(n, PROCESS_BASE_BYTES + 4 * biggest, isolate=True)
    try:
        run_jobs(compress_file_job, jobs, workers=workers, on_result=on_result, on_progress=on_progress, cancel=cancel)
    except BaseException:
        _cleanup_files(jobs, done_idx)
        raise
    before, after = state["before"], state["after"]
    if not state["kept"]:
        return "d_nogain", {}, state["out"]
    pct = max(1, round(100 * (1 - after / before))) if before else 0
    return "d_compress", {"a": human(before), "b": human(after), "p": pct}, state["out"]


def _cleanup_files(jobs, done_idx) -> None:
    for i, job in enumerate(jobs):
        if i not in done_idx:
            discard(Path(job[1]), part_path(Path(job[1])))


TASKS = {"pdf2png": task_pdf_to_png, "img2pdf": task_img_to_pdf, "merge": task_merge,
         "split": task_split, "remove": task_remove, "compress": task_compress}

__all__ = ["TASKS", "LEVELS", "TaskError", "Cancelled", "open_reader"]
