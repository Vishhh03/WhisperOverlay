"""
app.py - Voice Notes app entry point.

The main UI is a minimal subtitle-style overlay (overlay.py) that appears
near the bottom of the screen showing live transcribed text while you
speak - like video subtitles. There's no main window by default.

- Global hotkey (configurable, default Ctrl+Alt+R) toggles listening on/off.
- While listening, the overlay shows live transcript text.
- When you stop, the full transcript of that session is auto-saved as a note.
- A second hotkey (default Ctrl+Alt+N) or the tray icon opens the notes
  list / settings info window when you want it.
- All settings live in config.json (see config.py) - edit that file and
  restart the app, no code changes needed.
"""

import cuda_path_fix
cuda_path_fix.apply()  # must run before importing engine.py / faster_whisper

import threading
import time
import tkinter as tk
from tkinter import messagebox
import keyboard
import pystray
from PIL import Image, ImageDraw

import config as config_module
from engine import TranscriptionEngine
from overlay import SubtitleOverlay
from notes_window import NotesWindow
from subtitle_lines import SubtitleLineBuffer
import storage
from log_setup import get_logger, get_log_path

log = get_logger("app")


def make_tray_image(color):
    img = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), fill=color)
    return img


class VoiceNotesApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.withdraw()  # no main window - overlay + tray only

        self.cfg = config_module.load()
        log.info("Loaded config from %s", config_module.get_config_path())

        self.overlay = SubtitleOverlay(root, self.cfg)
        self.notes_window = NotesWindow(root)
        self.engine = TranscriptionEngine(on_text=self._on_text, on_status=self._on_status, cfg=self.cfg)
        self.subtitle_buffer = SubtitleLineBuffer(self.cfg)

        self.session_text_parts = []
        self.tray_icon = None
        self._last_toggle_time = 0.0

        self._register_hotkeys()
        self._start_tray()

    # ---------- Engine callbacks ----------
    def _on_text(self, text):
        self.root.after(0, self._handle_new_text, text)

    def _handle_new_text(self, text):
        self.session_text_parts.append(text)

        finalized_line = self.subtitle_buffer.add_text(text)
        if finalized_line:
            duration_ms = self.subtitle_buffer.display_duration_ms(finalized_line)
            self.overlay.show_text(finalized_line, duration_ms=duration_ms)
        # If no line was finalized yet, we're still accumulating - the
        # overlay keeps showing whatever the last finalized line was,
        # rather than flickering with every small chunk update.

    def _on_status(self, status):
        self.root.after(0, self._update_status, status)

    def _update_status(self, status):
        log.debug("Status changed to: %s", status)
        if status == "listening":
            self._set_tray_icon("green")
        elif status in ("stopped", "idle"):
            self._set_tray_icon("gray")
            self.overlay.hide()
        elif status == "loading":
            self._set_tray_icon("orange")
            self.overlay.show_text("Loading model...", duration_ms=None)
        elif status.startswith("error"):
            self._set_tray_icon("red")
            log.error("Engine reported error status: %s", status)
            self.overlay.hide()
            messagebox.showerror("Voice Notes - Error", f"{status}\n\nFull log: {get_log_path()}")

    # ---------- Actions ----------
    def toggle_listening(self):
        now = time.monotonic()
        if now - self._last_toggle_time < 0.75:
            log.debug("Ignoring duplicate toggle within debounce window.")
            return
        self._last_toggle_time = now

        if self.engine.is_listening():
            log.info("Toggling listening OFF.")
            self.engine.stop()
            self._flush_subtitle_buffer()
            self._save_session_if_any()
        else:
            log.info("Toggling listening ON.")
            self.session_text_parts = []
            self.subtitle_buffer.reset()
            threading.Thread(target=self.engine.start, daemon=True).start()

    def _flush_subtitle_buffer(self):
        remaining = self.subtitle_buffer.flush()
        if remaining:
            duration_ms = self.subtitle_buffer.display_duration_ms(remaining)
            self.overlay.show_text(remaining, duration_ms=duration_ms)

    def _save_session_if_any(self):
        full_text = " ".join(self.session_text_parts).strip()
        self.session_text_parts = []
        if not full_text:
            log.debug("Session ended with no text, nothing to save.")
            return
        storage.save_note(full_text)
        log.info("Auto-saved session note (%d chars).", len(full_text))

    def show_notes_window(self):
        self.notes_window.show()

    # ---------- Hotkeys ----------
    def _register_hotkeys(self):
        listen_key = self.cfg.get("hotkey_listen", "ctrl+alt+r")
        notes_key = self.cfg.get("hotkey_notes_window", "ctrl+alt+n")

        try:
            keyboard.add_hotkey(listen_key, lambda: self.root.after(0, self.toggle_listening))
            log.info("Registered listen hotkey: %s", listen_key)
        except Exception as e:
            log.error("Failed to register listen hotkey '%s': %s", listen_key, e, exc_info=True)
            messagebox.showwarning(
                "Voice Notes - Hotkey",
                f"Couldn't register the listen hotkey ({listen_key}).\n"
                f"Try running the terminal as Administrator, or change "
                f"hotkey_listen in config.json.\n\nDetails logged to: {get_log_path()}",
            )

        try:
            keyboard.add_hotkey(notes_key, lambda: self.root.after(0, self.show_notes_window))
            log.info("Registered notes-window hotkey: %s", notes_key)
        except Exception as e:
            log.error("Failed to register notes hotkey '%s': %s", notes_key, e, exc_info=True)

    # ---------- Tray ----------
    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Toggle Listening", lambda: self.root.after(0, self.toggle_listening), default=True),
            pystray.MenuItem("Show Notes / Settings", lambda: self.root.after(0, self.show_notes_window)),
            pystray.MenuItem("Quit", self._quit_app),
        )
        self.tray_icon = pystray.Icon("voice_notes", make_tray_image("gray"), "Voice Notes", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _set_tray_icon(self, color):
        if self.tray_icon:
            self.tray_icon.icon = make_tray_image(color)

    def _quit_app(self, *_args):
        log.info("Quitting app.")
        self.engine.stop()
        self._save_session_if_any()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)


def main():
    log.info("Voice Notes app starting.")
    root = tk.Tk()
    app = VoiceNotesApp(root)
    try:
        root.mainloop()
    finally:
        log.info("Voice Notes app exited.")


if __name__ == "__main__":
    main()
