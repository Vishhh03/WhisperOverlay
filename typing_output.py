"""
typing_output.py - Types transcribed text into whatever window/app
currently has keyboard focus, using simulated keystrokes (via the
`keyboard` library's write() function).

This lets you dictate directly into any text field, editor, browser, or
chat box - wherever your cursor is - rather than only seeing text in the
subtitle overlay.
"""

import keyboard
from log_setup import get_logger

log = get_logger("typing_output")


class TypingOutput:
    def __init__(self):
        self._is_first_chunk_of_session = True

    def reset_session(self):
        """Call this when a new typing session starts, so we don't add a
        leading space before the very first word."""
        self._is_first_chunk_of_session = True

    def type_text(self, text: str):
        """Types the given text at the current cursor position. Adds a
        leading space before each chunk after the first, so consecutive
        chunks don't run together without spacing."""
        text = text.strip()
        if not text:
            return

        try:
            if self._is_first_chunk_of_session:
                keyboard.write(text)
                self._is_first_chunk_of_session = False
            else:
                keyboard.write(" " + text)
            log.debug("Typed chunk (%d chars): %r", len(text), text)
        except Exception as e:
            log.error("Failed to type text via keyboard.write(): %s", e, exc_info=True)
