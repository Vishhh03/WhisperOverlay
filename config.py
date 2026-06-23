"""
config.py - Loads user-editable settings from config.json.

If config.json doesn't exist yet, it's created with sensible defaults on
first run. Just edit the JSON file directly and restart the app to apply
changes - no code editing needed.
"""

import json
import os
from log_setup import get_logger

log = get_logger("config")

CONFIG_DIR = os.path.join(os.path.expanduser("~"), "VoiceNotes")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "hotkey_listen": "ctrl+alt+r",
    "hotkey_notes_window": "ctrl+alt+n",
    "hotkey_typing": "ctrl+alt+t",

    "model_size": "small",
    "device": "cuda",
    "compute_type": "float16",
    "chunk_seconds": 1.5,
    "overlap_seconds": 0.5,
    "vad_filter": False,
    "silence_rms_threshold": 0.003,
    "hallucination_logprob_threshold": -0.5,

    "overlay_position": "bottom_center",
    "overlay_font_family": "Segoe UI",
    "overlay_font_size": 28,
    "overlay_text_color": "#FFFFFF",
    "overlay_background_opacity": 0.55,
    "overlay_margin_bottom": 80,
    "overlay_max_width_ratio": 0.7,
    "overlay_idle_hide_ms": 3000,

    "subtitle_max_line_chars": 90,
    "subtitle_min_chars_before_break": 20,
    "subtitle_base_display_ms": 1200,
    "subtitle_ms_per_char": 50,
    "subtitle_max_display_ms": 6000,
}


def _write_defaults_with_comments():
    """Writes config.json plus a sibling config.README.md explaining each
    field, since plain JSON can't hold comments."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, indent=2)

    readme_path = os.path.join(CONFIG_DIR, "config.README.md")
    if not os.path.exists(readme_path):
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(CONFIG_README)

    log.info("Created default config at %s", CONFIG_PATH)


def load():
    """Loads config.json, creating it with defaults if missing. Missing
    keys (e.g. after an app update adds new settings) are backfilled from
    DEFAULTS automatically."""
    if not os.path.exists(CONFIG_PATH):
        _write_defaults_with_comments()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("config.json is invalid (%s), falling back to defaults.", e)
        return dict(DEFAULTS)

    merged = dict(DEFAULTS)
    merged.update(user_cfg)

    # backfill any new keys into the file on disk so the user sees them
    if merged.keys() != user_cfg.keys():
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
        except OSError:
            pass

    return merged


def get_config_path():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    return CONFIG_PATH


CONFIG_README = """# Voice Notes - Config Reference

Edit `config.json` in this folder, then restart the app for changes to apply.

| Key                          | What it does                                                              |
|-------------------------------|----------------------------------------------------------------------------|
| hotkey_listen                | Global hotkey to start/stop listening (e.g. "ctrl+alt+r")                 |
| hotkey_notes_window           | Global hotkey to open the notes/settings window                          |
| hotkey_typing                | Global hotkey to start/stop typing-mode (types directly into focused app) |
| model_size                   | Whisper model size: "base" (fastest), "small" (balanced), "medium" (best) |
| device                       | "cuda" for GPU, "cpu" to force CPU                                        |
| compute_type                 | "float16" for GPU, "int8" for CPU                                         |
| chunk_seconds                | How often (in seconds) new text appears while speaking                    |
| overlap_seconds              | How much audio context carries between chunks                             |
| vad_filter                   | true = skip silent portions (needs onnxruntime working); false = simpler  |
| silence_rms_threshold         | 0.0-1.0, higher = more aggressive at ignoring quiet/background audio      |
| hallucination_logprob_threshold | Drops short low-confidence text (e.g. random "thank you"). More negative = stricter filtering |
| overlay_position             | Where the subtitle overlay sits: "bottom_center" or "top_center"          |
| overlay_font_family          | Font used for the subtitle text                                           |
| overlay_font_size            | Font size in points                                                       |
| overlay_text_color           | Hex color for the subtitle text                                           |
| overlay_background_opacity   | 0.0 (invisible) to 1.0 (solid) backing behind the text for readability    |
| overlay_margin_bottom        | Pixels from the bottom of the screen (only used if position is bottom)    |
| overlay_max_width_ratio      | Max overlay width as a fraction of screen width (0.0-1.0)                 |
| overlay_idle_hide_ms          | Fallback display time (ms) for non-subtitle messages like "Loading..."   |
| subtitle_max_line_chars        | Max characters per subtitle line before a forced break                   |
| subtitle_min_chars_before_break | Won't break a line shorter than this, even at a sentence end             |
| subtitle_base_display_ms       | Minimum time (ms) any subtitle line stays on screen                      |
| subtitle_ms_per_char            | Extra display time (ms) added per character, so longer lines stay longer |
| subtitle_max_display_ms        | Hard cap (ms) on how long a single line can stay displayed                |

Hotkey format examples: "ctrl+alt+r", "ctrl+shift+space", "f9"
"""
