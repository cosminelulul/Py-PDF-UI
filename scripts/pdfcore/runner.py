from __future__ import annotations

import multiprocessing as mp
import os
import queue as _queue
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from contextlib import suppress
from typing import NamedTuple

from .errors import TaskError, check_cancel, describe


class _Failure(NamedTuple):
    key: str
    kw: dict


_Q = None
_IDX = -1


def _lower_priority() -> None:
    try:
        if sys.platform == "win32":
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00004000)
        else:
            os.nice(5)
    except Exception:
        pass


def _init_worker(q) -> None:
    global _Q
    _Q = q
    _lower_priority()


def _worker_progress(frac: float, text: str) -> None:
    if _Q is not None:
        with suppress(Exception):
            _Q.put_nowait((_IDX, float(frac), str(text)))


def _entry(func, idx, job):
    global _IDX
    _IDX = idx
    try:
        return func(job, _worker_progress)
    except Exception as e:
        key, kw = describe(e)
        return _Failure(key, kw)


def run_jobs(func, jobs, *, workers: int, on_result, on_progress=None, cancel=None,
             ordered: bool = False, window: int | None = None) -> None:
    jobs = list(jobs)
    if not jobs:
        return
    if workers <= 0:
        _run_inline(func, jobs, on_result, on_progress, cancel)
    else:
        _run_pool(func, jobs, workers, on_result, on_progress, cancel, ordered, window)


def _run_inline(func, jobs, on_result, on_progress, cancel) -> None:
    for i, job in enumerate(jobs):
        check_cancel(cancel)

        def progress(frac, text, i=i):
            if on_progress:
                on_progress(i, frac, text)
            check_cancel(cancel)

        try:
            res = func(job, progress)
        except TaskError:
            raise
        except Exception as e:
            key, kw = describe(e)
            raise TaskError(key, **kw) from e
        on_result(i, res)


def _drain(q, on_progress) -> None:
    while True:
        try:
            idx, frac, text = q.get_nowait()
        except _queue.Empty:
            return
        except (OSError, EOFError, ValueError):
            return
        if on_progress:
            on_progress(idx, frac, text)


def _abort(ex) -> None:
    procs = list((getattr(ex, "_processes", None) or {}).values())
    with suppress(Exception):
        ex.shutdown(wait=False, cancel_futures=True)
    for p in procs:
        with suppress(Exception):
            p.terminate()
    for p in procs:
        with suppress(Exception):
            p.join(timeout=3)


def _run_pool(func, jobs, workers, on_result, on_progress, cancel, ordered, window) -> None:
    n = len(jobs)
    window = max(window or workers * 3, workers)
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    ex = ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=_init_worker, initargs=(q,))
    pending: dict = {}
    ready: dict = {}
    next_submit = next_emit = finished = 0
    try:
        while finished < n:
            check_cancel(cancel)
            base = next_emit if ordered else finished
            while next_submit < n and next_submit - base < window:
                pending[ex.submit(_entry, func, next_submit, jobs[next_submit])] = next_submit
                next_submit += 1
            done, _ = wait(list(pending), timeout=0.05, return_when=FIRST_COMPLETED)
            _drain(q, on_progress)
            for fut in done:
                idx = pending.pop(fut)
                try:
                    res = fut.result()
                except BrokenProcessPool as e:
                    raise TaskError("e_worker") from e
                if isinstance(res, _Failure):
                    raise TaskError(res.key, **res.kw)
                finished += 1
                if ordered:
                    ready[idx] = res
                    while next_emit in ready:
                        on_result(next_emit, ready.pop(next_emit))
                        next_emit += 1
                else:
                    on_result(idx, res)
        ex.shutdown(wait=True)
    except BaseException:
        _abort(ex)
        raise
    finally:
        try:
            q.close()
            q.cancel_join_thread()
        except Exception:
            pass
