from __future__ import annotations

import os
import sys

ENV_WORKERS = "PDFTOOLKIT_WORKERS"
MAX_WORKERS = 8
MEM_FRACTION = 0.6

BYTES_PER_PIXEL = 7.5
PROCESS_BASE_BYTES = 150 * 1024 * 1024
HARD_MAX_PIXELS = 250_000_000


def cpu_count() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:
        return max(1, os.cpu_count() or 1)


def available_memory() -> int | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class _Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = _Mem()
            st.dwLength = ctypes.sizeof(_Mem)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullAvailPhys)
            return None
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="ascii") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) * 1024
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")
    except Exception:
        return None


def render_pixel_limit() -> int:
    avail = available_memory()
    if not avail:
        return HARD_MAX_PIXELS
    fit = int((avail * 0.85 - PROCESS_BASE_BYTES) / BYTES_PER_PIXEL)
    return max(10_000_000, min(HARD_MAX_PIXELS, fit))


def choose_workers(jobs: int, bytes_per_job: int = 0, *, min_jobs: int = 2, isolate: bool = False) -> int:
    if jobs < 1:
        return 0
    env = os.environ.get(ENV_WORKERS, "").strip()
    if env.isdigit():
        n = int(env)
        if n <= 1:
            return 0
        n = min(n, 64)
    else:
        cpu = cpu_count()
        if cpu < 2:
            return 0
        n = min(cpu if cpu <= 2 else cpu - 1, MAX_WORKERS)
        if bytes_per_job > 0:
            avail = available_memory()
            if avail:
                n = min(n, max(1, int(avail * MEM_FRACTION) // bytes_per_job))
    n = min(n, jobs)
    if isolate:
        return max(n, 1)
    return n if (n >= 2 and jobs >= min_jobs) else 0
