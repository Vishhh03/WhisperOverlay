"""
subtitle_lines.py - Groups a stream of incoming transcribed text chunks into
subtitle-style lines, similar to how movie/YouTube subtitles are segmented:
break on natural sentence/clause boundaries first, fall back to a max
character length if the speaker runs on without pausing.

This sits between the raw engine output (small chunks every ~2.5s) and the
overlay display (which should show one coherent line/phrase at a time, not
a raw rolling window of words).
"""

import re
from log_setup import get_logger

log = get_logger("subtitle_lines")

# Natural break points, checked in order of preference (strong punctuation
# first). A break is only taken if the buffer is already reasonably long,
# so we don't finalize a line after just one or two words.
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

    def add_text(self, new_text: str):
        """Feed in a new transcribed chunk. Returns a finalized line (str)
        if a natural break point was reached, or None if we're still
        accumulating the current line."""
        new_text = new_text.strip()
        if not new_text:
            return None

        self._buffer = (self._buffer + " " + new_text).strip() if self._buffer else new_text

        return self._try_finalize_line()

    def _try_finalize_line(self):
        if len(self._buffer) < self.min_chars_before_break:
            return None  # too short to make a satisfying subtitle line yet

        # Prefer breaking at the LAST sentence-ending punctuation found,
        # so we keep as much complete content in this line as possible.
        sentence_matches = list(SENTENCE_END_RE.finditer(self._buffer))
        if sentence_matches:
            cut_at = sentence_matches[-1].end()
            line = self._buffer[:cut_at].strip()
            remainder = self._buffer[cut_at:].strip()
            self._buffer = remainder
            return line

        # No sentence end yet - if we've exceeded the max line length,
        # fall back to breaking at the last clause punctuation (comma etc)
        # if one exists past the minimum, otherwise hard-cut at a word
        # boundary so we at least don't split mid-word.
        if len(self._buffer) >= self.max_line_chars:
            clause_matches = list(CLAUSE_BREAK_RE.finditer(self._buffer))
            usable_clause_breaks = [m for m in clause_matches if m.end() >= self.min_chars_before_break]
            if usable_clause_breaks:
                cut_at = usable_clause_breaks[-1].end()
            else:
                # Hard cut at the last space before max_line_chars
                cut_at = self._buffer.rfind(" ", 0, self.max_line_chars)
                if cut_at <= 0:
                    cut_at = self.max_line_chars  # single very long word, just cut

            line = self._buffer[:cut_at].strip()
            remainder = self._buffer[cut_at:].strip()
            self._buffer = remainder
            return line

        return None  # still accumulating, no break yet

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
