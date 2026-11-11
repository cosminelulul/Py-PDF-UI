from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from PIL import ImageTk

from . import colors
from .uiperf import FRAME_MS, Throttle

WHEEL_LOGICAL_PX = 208
MARKER_R = 8


def _mode_hex(color) -> str:
    return color if isinstance(color, str) else color[1 if ctk.get_appearance_mode() == "Dark" else 0]


class ColorPicker(ctk.CTkToplevel):
    def __init__(self, master, *, tr, palette: dict, fonts: tuple, initial: str, on_apply, icon: Path | None = None):
        super().__init__(master)
        self.withdraw()
        self._tr = tr
        self._pal = palette
        self._on_apply = on_apply
        self._base, self._small, self._bold, self._title = fonts
        self._done = False
        self._invalid: set[str] = set()
        self._photo = None
        self._exact: tuple[int, int, int] | None = None

        try:
            scale = float(self._get_window_scaling())
        except Exception:
            scale = 1.0
        self._size = max(120, int(WHEEL_LOGICAL_PX * scale))
        self._c = self._size / 2
        self._radius = self._c - 1

        rgb = colors.parse_hex(initial) or colors.parse_hex(colors.DEFAULT_ACCENT_LIGHT)
        self._current_hex = colors.to_hex(rgb)
        self._h, self._s, self._v = colors.rgb_to_hsv(rgb)
        self._rgb = rgb
        self._exact = rgb

        self.title(tr("o_accent"))
        self.resizable(False, False)
        self.configure(fg_color=palette["surface"])
        if icon is not None and icon.exists():
            self.after(250, lambda: self._set_icon(icon))

        self._build()
        self._wheel_move = Throttle(self, FRAME_MS, self._wheel_at)
        self._bright_move = Throttle(self, FRAME_MS, self._set_brightness)
        self._refresh("init")

        self.bind("<Escape>", lambda e: self.cancel())
        self.bind("<Return>", lambda e: self.apply())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.transient(master)
        self._center(master)
        self.deiconify()
        self.after(80, self._modal)

    def _set_icon(self, icon: Path):
        try:
            self.iconbitmap(str(icon))
        except tk.TclError:
            pass

    def _center(self, master):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = master.winfo_rootx() + max(0, (master.winfo_width() - w) // 2)
        y = master.winfo_rooty() + max(0, (master.winfo_height() - h) // 3)
        self.geometry(f"+{x}+{y}")

    def _modal(self):
        try:
            self.grab_set()
            self.focus_force()
            self.hex_entry.focus_set()
            self.hex_entry.select_range(0, "end")
        except tk.TclError:
            pass

    def _entry(self, parent, width):
        return ctk.CTkEntry(parent, width=width, height=34, corner_radius=8, border_width=1,
                            border_color=self._pal["border"], fg_color=self._pal["surface2"],
                            text_color=self._pal["text"], font=self._base, justify="center")

    def _button(self, parent, key, command, primary=False):
        pal = self._pal
        if primary:
            style = dict(fg_color=pal["accent"], hover_color=pal["accent_hover"], text_color=pal["on_accent"],
                         border_width=0)
        else:
            style = dict(fg_color=pal["surface2"], hover_color=pal["hover"], text_color=pal["text"],
                         border_width=1, border_color=pal["border"])
        return ctk.CTkButton(parent, text=self._tr(key), height=36, width=96, corner_radius=9, font=self._base,
                             command=command, **style)

    def _build(self):
        pal = self._pal
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=22, pady=20)

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="n")
        self.canvas = tk.Canvas(left, width=self._size, height=self._size, highlightthickness=0, bd=0,
                                bg=_mode_hex(pal["surface"]), cursor="crosshair")
        self.canvas.pack()
        self._img_id = self.canvas.create_image(0, 0, anchor="nw")
        self._ring_out = self.canvas.create_oval(0, 0, 1, 1, outline="#FFFFFF", width=3)
        self._ring_in = self.canvas.create_oval(0, 0, 1, 1, outline="#000000", width=1)
        self.canvas.bind("<ButtonPress-1>", lambda e: self._wheel_move(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self._wheel_move(e.x, e.y))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._wheel_move.flush())

        ctk.CTkLabel(left, text=self._tr("c_bright"), font=self._small, text_color=pal["muted"], anchor="w").pack(
            fill="x", pady=(12, 2))
        self.bright = ctk.CTkSlider(left, from_=0, to=100, height=16, command=lambda v: self._bright_move(v),
                                    progress_color=pal["accent"], button_color=pal["accent"],
                                    button_hover_color=pal["accent_hover"], fg_color=pal["border"])
        self.bright.pack(fill="x")
        self.bright.bind("<ButtonRelease-1>", lambda e: self._bright_move.flush(), add="+")

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="n", padx=(22, 0))

        sw = ctk.CTkFrame(right, fg_color="transparent")
        sw.pack(fill="x")
        for col, (key, attr) in enumerate((("c_current", "old_sw"), ("c_new", "new_sw"))):
            cell = ctk.CTkFrame(sw, fg_color="transparent")
            cell.grid(row=0, column=col, padx=(0, 10) if col == 0 else 0, sticky="ew")
            ctk.CTkLabel(cell, text=self._tr(key), font=self._small, text_color=pal["muted"], anchor="w").pack(fill="x")
            box = ctk.CTkFrame(cell, width=100, height=44, corner_radius=10, border_width=1,
                               border_color=pal["border"], fg_color=self._current_hex)
            box.pack()
            box.pack_propagate(False)
            setattr(self, attr, box)

        ctk.CTkLabel(right, text=self._tr("c_hex"), font=self._small, text_color=pal["muted"], anchor="w").pack(
            fill="x", pady=(16, 2))
        self.hex_entry = self._entry(right, 210)
        self.hex_entry.pack(fill="x")
        self.hex_entry.bind("<KeyRelease>", lambda e: self._on_hex_typed(), add="+")
        self.hex_entry.bind("<FocusOut>", lambda e: self._normalize(), add="+")

        chans = ctk.CTkFrame(right, fg_color="transparent")
        chans.pack(fill="x", pady=(12, 0))
        self.chan: dict[str, ctk.CTkEntry] = {}
        for col, name in enumerate("RGB"):
            cell = ctk.CTkFrame(chans, fg_color="transparent")
            cell.grid(row=0, column=col, padx=(0, 8) if col < 2 else 0)
            ctk.CTkLabel(cell, text=name, font=self._small, text_color=pal["muted"], anchor="w").pack(fill="x")
            e = self._entry(cell, 62)
            e.pack()
            e.bind("<KeyRelease>", lambda ev, n=name: self._on_channel_typed(n), add="+")
            e.bind("<FocusOut>", lambda ev: self._normalize(), add="+")
            e.bind("<Up>", lambda ev, n=name: self._nudge(n, +1, ev))
            e.bind("<Down>", lambda ev, n=name: self._nudge(n, -1, ev))
            self.chan[name] = e

        self.hint = ctk.CTkLabel(right, text=self._tr("c_hint"), font=self._small, text_color=pal["muted"],
                                 anchor="w", justify="left", wraplength=214)
        self.hint.pack(fill="x", pady=(12, 0))

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.grid(row=1, column=0, columnspan=2, sticky="e", pady=(20, 0))
        self._button(btns, "c_reset", self.reset).pack(side="left", padx=(0, 8))
        self._button(btns, "c_cancel", self.cancel).pack(side="left", padx=(0, 8))
        self._button(btns, "c_apply", self.apply, primary=True).pack(side="left")

    def _wheel_at(self, x, y):
        self._h, self._s = colors.point_to_hs(x, y, self._c, self._c, self._radius)
        self._exact = None
        self._refresh("wheel")

    def _set_brightness(self, value):
        self._v = max(0.0, min(1.0, float(value) / 100))
        self._exact = None
        self._refresh("bright")

    def _set_rgb(self, rgb, source):
        self._exact = tuple(rgb)
        h, s, v = colors.rgb_to_hsv(rgb)
        if v > 0:
            self._v = v
            if s > 0:
                self._h = h
            self._s = s
        else:
            self._v = 0.0
        self._refresh(source)

    def _refresh(self, source: str):
        self._rgb = self._exact or colors.hsv_to_rgb(self._h, self._s, self._v)
        hexval = colors.to_hex(self._rgb)
        self.new_sw.configure(fg_color=hexval)
        if source in ("init", "bright", "wheel", "hex", "rgb", "reset", "nudge"):
            self._draw_wheel()
        self._place_marker()
        if source != "bright" and abs(self.bright.get() - self._v * 100) > 0.5:
            self.bright.set(self._v * 100)
        if source != "hex":
            self._set_text(self.hex_entry, hexval)
        if source not in ("rgb",):
            for name, value in zip("RGB", self._rgb):
                self._set_text(self.chan[name], str(value))

    def _draw_wheel(self):
        self._photo = ImageTk.PhotoImage(colors.wheel_image(self._size, self._v))
        self.canvas.itemconfigure(self._img_id, image=self._photo)

    def _place_marker(self):
        x, y = colors.hs_to_point(self._h, self._s, self._c, self._c, self._radius)
        for item, r in ((self._ring_out, MARKER_R), (self._ring_in, MARKER_R - 2)):
            self.canvas.coords(item, x - r, y - r, x + r, y + r)

    @staticmethod
    def _set_text(entry, text):
        if entry.get() != text:
            entry.delete(0, "end")
            entry.insert(0, text)

    def _mark(self, key: str, entry, ok: bool):
        if ok:
            self._invalid.discard(key)
        else:
            self._invalid.add(key)
        entry.configure(border_color=self._pal["border"] if ok else self._pal["danger"])
        self._update_hint()

    def _update_hint(self):
        bad = bool(self._invalid)
        self.hint.configure(text=self._tr("c_invalid" if bad else "c_hint"),
                            text_color=self._pal["danger"] if bad else self._pal["muted"])

    def _on_hex_typed(self):
        rgb = colors.parse_color(self.hex_entry.get())
        for name in "RGB":
            self._mark(name, self.chan[name], True)
        self._mark("hex", self.hex_entry, rgb is not None)
        if rgb is not None and rgb != self._rgb:
            self._set_rgb(rgb, "hex")

    def _on_channel_typed(self, name: str):
        vals = {n: colors.parse_channel(self.chan[n].get()) for n in "RGB"}
        self._mark("hex", self.hex_entry, True)
        for n, v in vals.items():
            self._mark(n, self.chan[n], v is not None)
        if all(v is not None for v in vals.values()):
            rgb = (vals["R"], vals["G"], vals["B"])
            if rgb != self._rgb:
                self._set_rgb(rgb, "rgb")
                self._set_text(self.hex_entry, colors.to_hex(rgb))

    def _nudge(self, name: str, direction: int, event):
        step = 10 if (event.state & 0x1) else 1
        cur = colors.parse_channel(self.chan[name].get())
        cur = self._rgb["RGB".index(name)] if cur is None else cur
        new = max(0, min(255, cur + direction * step))
        rgb = list(self._rgb)
        rgb["RGB".index(name)] = new
        for n in "RGB":
            self._mark(n, self.chan[n], True)
        self._mark("hex", self.hex_entry, True)
        self._set_rgb(tuple(rgb), "nudge")
        return "break"

    def _normalize(self):
        if self._done or self._invalid:
            return
        self._set_text(self.hex_entry, colors.to_hex(self._rgb))
        for name, value in zip("RGB", self._rgb):
            self._set_text(self.chan[name], str(value))

    def reset(self):
        for key, entry in (("hex", self.hex_entry), *self.chan.items()):
            self._mark(key, entry, True)
        self._set_rgb(colors.parse_hex(colors.DEFAULT_ACCENT_LIGHT), "reset")

    def value(self) -> str:
        return colors.canonical_accent(colors.to_hex(self._rgb))

    def apply(self):
        if self._done:
            return
        if self._invalid:
            self.bell()
            return
        self._finish()
        self._on_apply(self.value())

    def cancel(self):
        if not self._done:
            self._finish()

    def _finish(self):
        self._done = True
        self._wheel_move.cancel()
        self._bright_move.cancel()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
