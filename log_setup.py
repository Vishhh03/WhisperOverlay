"""
log_setup.py - Centralized logging configuration.

Logs go to ~/VoiceNotes/logs/voice-notes.log (rotating, so it doesn't grow
forever) and also print to console when running from a terminal.

Usage in any module:
    from log_setup import get_logger
    log = get_logger(__name__)
    log.info("something happened")
    log.error("something broke: %s", e)
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.expanduser("~"), "VoiceNotes", "logs")
LOG_PATH = os.path.join(LOG_DIR, "voice-notes.log")

_initialized = False


def _init_logging():
    global _initialized
    if _initialized:
        return
    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger("voicenotes")
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler: 2MB per file, keep 3 backups (~8MB max total)
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Console handler: only INFO and above, so debug noise doesn't spam the terminal
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    _initialized = True
    root.info("=" * 60)
    root.info("Logging started. Log file: %s", LOG_PATH)


def get_logger(name: str) -> logging.Logger:
    _init_logging()
    return logging.getLogger(f"voicenotes.{name}")


def get_log_path() -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    return LOG_PATH
