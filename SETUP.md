# Voice Notes — Setup Guide (Windows, using uv)

A small app that lets you press **Ctrl+Alt+R** anywhere on your PC to start/stop
voice transcription, see the live text in a window, edit it, and save it to a
markdown file + an in-app notes list.

This project uses **uv** instead of pip/venv — it's faster and shares a global
package cache across all your projects, so a multi-GB package like torch
doesn't get duplicated on disk every time you start something new.

## 1. Install uv (one-time, system-wide)

In PowerShell:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
Restart your terminal afterward. Verify:
```powershell
uv --version
```

## 2. Create the project environment

From inside the `voice-notes` folder:
```powershell
cd path\to\voice-notes
uv venv
```
This creates a `.venv` folder. Activate it:
```powershell
.venv\Scripts\activate
```
Your prompt should now show `(voice-notes)` or similar at the start.

## 3. Install torch with CUDA support

The CUDA build of torch isn't on the default index, so it's configured in
`pyproject.toml` under `[tool.uv.index]`. Just run:
```powershell
uv sync
```
This reads `pyproject.toml`, pulls torch from the PyTorch CUDA index, and
everything else from the normal PyPI index — all in one command, using your
shared uv cache so repeat installs across projects are near-instant.

> If `uv sync` has trouble resolving torch+CUDA on your system, fall back to
> installing it directly first, then syncing the rest:
> ```powershell
> uv pip install torch --index-url https://download.pytorch.org/whl/cu121
> uv sync
> ```

## 4. Run the app

```powershell
uv run app.py
```
(`uv run` automatically uses the project's `.venv` — no need to manually
activate it every time, though activating still works fine too.)

A small window opens. Press **Ctrl+Alt+R** from anywhere (even while gaming
or coding) to start listening — speak naturally, text will appear in the
window every ~2-3 seconds as you talk. Press the hotkey again to stop.

- **Save Note** — saves the current transcript to `~/VoiceNotes/notes.md`
  and adds it to the in-app list below.
- **Clear** — wipes the current transcript without saving.
- **Open Notes Folder** — opens `~/VoiceNotes` in File Explorer.
- Closing the window (X) minimizes it to the system tray instead of quitting —
  right-click the tray icon to show the window again or fully quit.

> Note: `keyboard` sometimes needs the app to run with admin privileges on
> Windows to register global hotkeys reliably. If the hotkey doesn't trigger
> anywhere, try running your terminal as Administrator.

## Notes on performance

- First run will download the `small` Whisper model (~500MB) automatically —
  needs internet the first time only. This is a separate cache from uv's
  package cache (Whisper models live under `~/.cache/huggingface` by default).
- Default config uses GPU (`small` model, float16) — should use well under
  1GB VRAM, leaving plenty of room for coding/gaming.
- If you ever run this without a GPU available, it automatically falls back
  to CPU (int8) — slower, but still works.
- Latency is "near real-time" — you'll see text appear every ~2-3 seconds,
  not character-by-character. This is the tradeoff for a much simpler install
  than the NeMo/Nemotron route.

## Tuning

In `engine.py`:
- `MODEL_SIZE`: try `"base"` for faster/lighter, `"medium"` for more accurate
  but slower and heavier.
- `CHUNK_SECONDS`: lower = more frequent updates (more responsive feel) but
  more GPU work; higher = less frequent but more efficient.

In `app.py`:
- `HOTKEY`: change `"ctrl+alt+r"` to whatever combo you prefer.

## Why this is more efficient than venv+pip

- **Shared cache**: uv stores every downloaded/built package once in a global
  cache (`%LOCALAPPDATA%\uv\cache` by default). New projects that need the
  same torch version link to that cache instead of re-downloading or
  duplicating the files on disk.
- **Faster resolves and installs**: uv's resolver is written in Rust and is
  significantly faster than pip's.
- **Lockfile included**: `uv sync` will also generate a `uv.lock` file the
  first time you run it, pinning exact resolved versions for reproducibility
  — useful if you ever set this up on another machine.
- Future ML side-projects in other folders can reuse the same uv cache —
  just `uv venv` + `uv sync` in the new folder, no manual cache management
  needed.
