"""
storage.py - Saves notes to a markdown file and keeps a JSON index for the UI.
"""

import json
import os
from datetime import datetime

from log_setup import get_logger

log = get_logger("storage")

NOTES_DIR = os.path.join(os.path.expanduser("~"), "VoiceNotes")
MD_PATH = os.path.join(NOTES_DIR, "notes.md")
INDEX_PATH = os.path.join(NOTES_DIR, "index.json")


def ensure_dirs():
    os.makedirs(NOTES_DIR, exist_ok=True)
    if not os.path.exists(MD_PATH):
        with open(MD_PATH, "w", encoding="utf-8") as f:
            f.write("# Voice Notes\n\n")
    if not os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_index():
    ensure_dirs()
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_note(text: str, title: str = None):
    """Appends a note to the markdown file and updates the index. Returns the note dict."""
    ensure_dirs()
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    note_id = now.strftime("%Y%m%d%H%M%S%f")
    title = title or now.strftime("Note - %b %d, %I:%M %p")

    try:
        # Append to markdown
        with open(MD_PATH, "a", encoding="utf-8") as f:
            f.write(f"## {title}\n")
            f.write(f"*{timestamp}*\n\n")
            f.write(f"{text.strip()}\n\n---\n\n")

        # Update index
        index = load_index()
        note = {"id": note_id, "title": title, "timestamp": timestamp, "text": text.strip()}
        index.insert(0, note)  # newest first
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except Exception as e:
        log.error("Failed to save note '%s': %s", title, e, exc_info=True)
        raise

    log.info("Saved note '%s' (%d chars).", title, len(text.strip()))
    return note


def get_notes_dir():
    ensure_dirs()
    return NOTES_DIR
