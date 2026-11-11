from __future__ import annotations

import time
import tkinter as tk

FRAME_MS = 15
SLOW_FRAME_MS = 16 
SETTLE_MS = 70


def ease_inout(t: float) -> float:
    return t * t * (3 - 2 * t)


class Throttle:
    def __init__(self, widget, interval_ms: int, fn):
        self._widget = widget
        self._interval = max(1, interval_ms) / 1000
        self._fn = fn
        self._last = 0.0
        self._job = None
        self._args = None

    def __call__(self, *args):
        self._args = args
        if self._job is not None:
            return
        wait = self._last + self._interval - time.perf_counter()
        if wait <= 0:
            self._fire()
        else:
            self._job = self._widget.after(max(1, int(wait * 1000)), self._fire)

    def _fire(self):
        self._job = None
        args, self._args = self._args, None
        self._last = time.perf_counter()
        if args is not None:
            self._fn(*args)

    def flush(self):
        self.cancel(keep_args=True)
        self._fire()

    def cancel(self, keep_args: bool = False):
        if self._job is not None:
            try:
                self._widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if not keep_args:
            self._args = None


class ResizeGovernor:
    def __init__(self, window, on_begin, on_end, tick_ms: int = 24, settle_ms: int = SETTLE_MS,
                 armed: bool = True):
        self._window = window
        self._on_begin = on_begin
        self._on_end = on_end
        self._tick_ms = min(max(tick_ms, FRAME_MS), SLOW_FRAME_MS)
        self._settle = settle_ms / 1000
        self._size: tuple[int, int] | None = None
        self._last = 0.0
        self._job = None
        self.active = False
        self._armed = False
        window.bind("<Configure>", self._on_configure, add="+")
        if armed:
            self.arm()

    def arm(self):
        self._size = (self._window.winfo_width(), self._window.winfo_height())
        self._armed = True

    def _on_configure(self, event):
        if event.widget is not self._window:
            return
        size = (event.width, event.height)
        if size == self._size:
            return
        self._size = size
        if not self._armed or not self._window.winfo_ismapped():
            return
        self._last = time.perf_counter()
        if not self.active:
            self.active = True
            self._call(self._on_begin)
            self._job = self._window.after(self._tick_ms, self._tick)

    def _tick(self):
        self._job = None
        if time.perf_counter() - self._last >= self._settle:
            self.finish()
        else:
            self._job = self._window.after(self._tick_ms, self._tick)

    def finish(self):
        if not self.active:
            return
        self.active = False
        if self._job is not None:
            try:
                self._window.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        self._call(self._on_end)

    @staticmethod
    def _call(fn):
        try:
            fn()
        except tk.TclError:
            pass


class ScrollableWidthLock:
    def __init__(self, scrollable):
        self._canvas = getattr(scrollable, "_parent_canvas", None)
        self._fit = getattr(scrollable, "_fit_frame_dimensions_to_canvas", None)
        self.locked = False

    @property
    def supported(self) -> bool:
        return self._canvas is not None and callable(self._fit)

    def lock(self):
        if self.locked or not self.supported:
            return
        self._canvas.bind("<Configure>", lambda e: None)
        self.locked = True

    def unlock(self):
        if not self.locked:
            return
        self.locked = False
        self._canvas.bind("<Configure>", self._fit)
        self._fit(None)
