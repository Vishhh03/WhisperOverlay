"""
notes_window.py - The notes list/editor window, opened on demand (not the
main app window anymore - the main UI is the subtitle overlay in overlay.py).
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox

import storage
import config as config_module
from log_setup import get_logger, get_log_path

log = get_logger("notes_window")


class NotesWindow:
    """Wraps a single Toplevel that can be shown/hidden repeatedly rather
    than recreated each time."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.window = None

    def show(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self._refresh_notes_list()
            return

        self.window = tk.Toplevel(self.root)
        self.window.title("Voice Notes")
        self.window.geometry("480x460")
        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)
        self._build_ui()
        self._refresh_notes_list()

    def _build_ui(self):
        top = ttk.Frame(self.window, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Saved Notes", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text="Open Notes Folder", command=self._open_notes_folder).pack(side="right")
        ttk.Button(top, text="Open Config", command=self._open_config).pack(side="right", padx=(0, 6))

        list_frame = ttk.Frame(self.window, padding=10)
        list_frame.pack(fill="both", expand=True)

        self.notes_listbox = tk.Listbox(list_frame)
        self.notes_listbox.pack(fill="both", expand=True)
        self.notes_listbox.bind("<<ListboxSelect>>", self._on_note_selected)

        bottom = ttk.Frame(self.window, padding=10)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Open Log File", command=self._open_log).pack(side="left")
        ttk.Label(bottom, text="Edit config.json then restart the app to apply changes.",
                  foreground="#666").pack(side="right")

    def _refresh_notes_list(self):
        self.notes_listbox.delete(0, tk.END)
        self._notes_cache = storage.load_index()
        for note in self._notes_cache:
            self.notes_listbox.insert(tk.END, f"{note['timestamp']}  -  {note['title']}")

    def _on_note_selected(self, _event):
        sel = self.notes_listbox.curselection()
        if not sel:
            return
        note = self._notes_cache[sel[0]]
        messagebox.showinfo(note["title"], note["text"])

    def _open_notes_folder(self):
        os.startfile(storage.get_notes_dir())

    def _open_config(self):
        os.startfile(config_module.get_config_path())

    def _open_log(self):
        os.startfile(get_log_path())
