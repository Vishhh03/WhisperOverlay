"""
overlay.py - A minimal, borderless, click-through subtitle overlay.

Shows live transcript text as large, clean, centered text near the bottom
of the screen, like a video subtitle. No buttons, no borders, no window
chrome - just text with a soft dark backing for readability. Only visible
while actively listening. Click-through on Windows, so it never intercepts
mouse input from whatever's behind it (games, other windows, etc).
"""

import sys
import tkinter as tk
from log_setup import get_logger

log = get_logger("overlay")

DEFAULT_IDLE_HIDE_MS = 3000  # how long text stays on screen with no new speech before fading out

# --- Windows click-through support ------------------------------------
# Tkinter has no built-in way to make a window click-through. On Windows,
# this requires setting the WS_EX_LAYERED + WS_EX_TRANSPARENT extended
# window styles via the Win32 API, which we reach via ctypes since there's
# no pure-Python/tkinter equivalent.
if sys.platform == "win32":
    import ctypes

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020

    def _make_window_click_through(hwnd: int):
        try:
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception as e:
            log.warning("Failed to set click-through window style: %s", e)
else:
    def _make_window_click_through(hwnd: int):
        pass  # only implemented for Windows; overlay is still visible elsewhere, just not click-through


class SubtitleOverlay:
    def __init__(self, root: tk.Tk, cfg: dict):
        self.cfg = cfg
        self._idle_after_id = None
        self.idle_hide_ms = int(cfg.get("overlay_idle_hide_ms", DEFAULT_IDLE_HIDE_MS))

        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)       # no title bar / borders
        self.window.attributes("-topmost", True)
        self.window.config(bg="black")

        # Transparent-ish background: tkinter doesn't support true per-pixel
        # alpha on a Toplevel easily cross-platform, so we use a near-black
        # backing with -alpha as a soft readability scrim instead of pure
        # transparency. This keeps text legible over any background.
        opacity = float(self.cfg.get("overlay_background_opacity", 0.55))
        self.window.attributes("-alpha", max(0.0, min(1.0, opacity + 0.0)))

        font_family = self.cfg.get("overlay_font_family", "Segoe UI")
        font_size = int(self.cfg.get("overlay_font_size", 28))

        self.label = tk.Label(
            self.window,
            text="",
            font=(font_family, font_size, "normal"),
            fg=self.cfg.get("overlay_text_color", "#FFFFFF"),
            bg="black",
            wraplength=self._compute_max_width(),
            justify="center",
            padx=24,
            pady=14,
        )
        self.label.pack()

        self._position_window()
        self._apply_click_through()

    def _apply_click_through(self):
        if sys.platform != "win32":
            return
        try:
            hwnd = self.window.winfo_id()
            # Toplevel's winfo_id() returns the child window handle; the
            # actual top-level frame is its parent in some Tk builds, but on
            # most modern Tk/Windows builds this hwnd is already correct.
            # We resolve the real top-level ancestor via GetAncestor to be safe.
            GA_ROOT = 2
            root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
            _make_window_click_through(root_hwnd if root_hwnd else hwnd)
        except Exception as e:
            log.warning("Could not apply click-through styling: %s", e)

    def _compute_max_width(self) -> int:
        screen_w = self.window.winfo_screenwidth()
        ratio = float(self.cfg.get("overlay_max_width_ratio", 0.7))
        return int(screen_w * ratio)

    def _position_window(self):
        self.window.update_idletasks()
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        win_w = self.window.winfo_reqwidth()
        win_h = self.window.winfo_reqheight()

        x = (screen_w - win_w) // 2
        position = self.cfg.get("overlay_position", "bottom_center")
        if position == "top_center":
            y = 60
        else:  # bottom_center (default)
            margin = int(self.cfg.get("overlay_margin_bottom", 80))
            y = screen_h - win_h - margin

        self.window.geometry(f"+{x}+{y}")

    def show_text(self, text: str, duration_ms: int = None):
        """Sets the overlay text, shows the window, and re-centers it
        (since text length changes the window size).

        duration_ms: how long this specific line should stay visible
        before auto-hiding. If None, uses the default idle_hide_ms. Pass
        a large/explicit value for calculated subtitle-line durations, or
        None for persistent status messages like "Loading model..."."""
        self.label.config(text=text)
        self.window.deiconify()
        self._position_window()
        self._apply_click_through()
        effective_duration = duration_ms if duration_ms is not None else self.idle_hide_ms
        self._reset_idle_timer(effective_duration)

    def hide(self):
        self.window.withdraw()
        self._cancel_idle_timer()

    def _reset_idle_timer(self, duration_ms: int):
        self._cancel_idle_timer()
        self._idle_after_id = self.window.after(duration_ms, self._on_idle_timeout)

    def _cancel_idle_timer(self):
        if self._idle_after_id is not None:
            try:
                self.window.after_cancel(self._idle_after_id)
            except tk.TclError:
                pass
            self._idle_after_id = None

    def _on_idle_timeout(self):
        log.debug("Subtitle line display duration elapsed, hiding overlay text.")
        self.label.config(text="")
        self.window.withdraw()
