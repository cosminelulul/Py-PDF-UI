from __future__ import annotations

import errno
import os


class TaskError(Exception):

    def __init__(self, key: str, **kw):
        super().__init__(key)
        self.key, self.kw = key, kw

    def __reduce__(self):
        return (_rebuild_task_error, (self.key, self.kw))


def _rebuild_task_error(key, kw):
    return TaskError(key, **kw)


class Cancelled(BaseException):
    pass


def check_cancel(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def _base(e: OSError) -> str:
    fn = getattr(e, "filename", None)
    return os.path.basename(str(fn)) if fn else ""


def describe(e: BaseException) -> tuple[str, dict]:
    if isinstance(e, TaskError):
        return e.key, e.kw
    if isinstance(e, MemoryError):
        return "e_memory", {}
    if isinstance(e, PermissionError):
        return "e_perm", {}
    if isinstance(e, FileNotFoundError):
        return "e_missing", {"name": _base(e)}
    if isinstance(e, OSError) and e.errno == errno.ENOSPC:
        return "e_disk", {}
    if type(e).__name__ == "BrokenProcessPool":
        return "e_worker", {}
    text = " ".join(str(e).split()) or type(e).__name__
    return "error", {"e": text[:300]}
