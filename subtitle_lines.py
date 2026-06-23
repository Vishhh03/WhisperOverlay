"""
subtitle_lines.py - Groups a stream of incoming transcribed text chunks into
subtitle-style lines, similar to how movie/YouTube subtitles are segmented:
break on natural sentence/clause boundaries first, fall back to a max
character length if the speaker runs on without pausing.

This sits between the raw engine output (small chunks every ~2.5s) and the
overlay display (which should show one coherent line/phrase at a time, not
a raw rolling window of words).
"""

"""
subtitle_lines.py - Groups a stream of incoming transcribed text chunks into
subtitle-style lines, similar to how movie/YouTube subtitles are segmented.

Design: every new chunk of text is shown immediately (low latency is the
whole point of a live overlay) - the current line just keeps growing on
screen as you talk. Sentence/clause-boundary detection is used ONLY to
decide when the CURRENT line is "done" and the NEXT line should start
fresh, not to gate whether anything is displayed at all.
"""

import re
from log_setup import get_logger

log = get_logger("subtitle_lines")

# Natural break points, checked in order of preference (strong punctuation
# first).
SENTENCE_END_RE = re.compile(r'[.!?]+(?:\s|$)')
CLAUSE_BREAK_RE = re.compile(r'[,;:]+\s')


class SubtitleLineBuffer:
    def __init__(self, cfg: dict):
        self.max_line_chars = int(cfg.get("subtitle_max_line_chars", 90))
        self.min_chars_before_break = int(cfg.get("subtitle_min_chars_before_break", 20))
        self.base_display_ms = int(cfg.get("subtitle_base_display_ms", 1200))
        self.ms_per_char = float(cfg.get("subtitle_ms_per_char", 50))
        self.max_display_ms = int(cfg.get("subtitle_max_display_ms", 6000))

        self._buffer = ""

    def add_text(self, new_text: str) -> str:
        """Feed in a new transcribed chunk. Always returns the current
        full in-progress line text immediately, INCLUDING the just-added
        text, so the caller can display it right away with no delay.

        If this update also crossed a natural break point, the buffer is
        trimmed back down to just the remainder after that break - so the
        NEXT call starts the next line fresh - but we still return the
        complete pre-trim text for this call, so the just-finished line
        is shown in full one last time before the next line begins."""
        new_text = new_text.strip()
        if not new_text:
            return self._buffer

        self._buffer = (self._buffer + " " + new_text).strip() if self._buffer else new_text
        current_display_text = self._buffer

        self._maybe_cut_for_next_line()

        return current_display_text

    def _maybe_cut_for_next_line(self):
        """Checks if the buffer has crossed a natural break point. If so,
        trims the buffer down to just the text AFTER that break, so the
        next add_text() call starts building the next line. Does not
        return anything - this only affects internal state for next time."""
        if len(self._buffer) < self.min_chars_before_break:
            return  # too short to justify starting a new line yet

        sentence_matches = list(SENTENCE_END_RE.finditer(self._buffer))
        if sentence_matches:
            cut_at = sentence_matches[-1].end()
            # Only cut if there's meaningful content before the break
            if cut_at >= self.min_chars_before_break:
                self._buffer = self._buffer[cut_at:].strip()
                return

        if len(self._buffer) >= self.max_line_chars:
            clause_matches = list(CLAUSE_BREAK_RE.finditer(self._buffer))
            usable_clause_breaks = [m for m in clause_matches if m.end() >= self.min_chars_before_break]
            if usable_clause_breaks:
                cut_at = usable_clause_breaks[-1].end()
            else:
                cut_at = self._buffer.rfind(" ", 0, self.max_line_chars)
                if cut_at <= 0:
                    cut_at = self.max_line_chars

            self._buffer = self._buffer[cut_at:].strip()

    def flush(self):
        """Force out whatever's left in the buffer (e.g. when listening
        stops). Returns the line, or None if buffer is empty."""
        if not self._buffer.strip():
            return None
        line = self._buffer.strip()
        self._buffer = ""
        return line

    def display_duration_ms(self, line: str) -> int:
        """How long this line should stay on screen, scaled by length so
        longer lines get more reading time, within sane bounds."""
        duration = self.base_display_ms + int(len(line) * self.ms_per_char)
        return min(duration, self.max_display_ms)

    def reset(self):
        self._buffer = ""
