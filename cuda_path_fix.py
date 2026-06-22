"""
cuda_path_fix.py - Ensures CTranslate2 (faster-whisper's backend) can find
the cuDNN/cuBLAS DLLs it needs at import/load time, by pointing it at the
copies already bundled inside torch's own install (torch/lib/).

Why this exists:
CTranslate2 loads cuDNN/cuBLAS as native DLLs at runtime. torch already
ships its own cudnn 8.x DLLs inside site-packages/torch/lib/. Earlier we
tried installing a SEPARATE nvidia-cudnn-cu12 pip package and pointing
CTranslate2 at that instead - this caused a DLL version conflict
(WinError 127: "The specified procedure could not be found") because two
different cudnn 8.x builds ended up fighting for the same DLL names when
torch's own import triggered its bundled cudnn to load first. The fix is
to NOT install a separate cudnn package at all, and instead make sure
torch/lib/ (which CTranslate2 doesn't always search by default on Windows)
is explicitly on PATH and registered as a DLL search directory.

This must be imported BEFORE `faster_whisper` (and therefore before
`engine.py`) anywhere in the app, since the native libs are loaded at
import time, not just when a model is actually instantiated.
"""

import os
import sys


def _find_torch_lib_dir() -> str | None:
    """Find the torch/lib directory inside the current venv's site-packages."""
    venv_site = os.path.join(sys.prefix, "Lib", "site-packages")
    candidate = os.path.join(venv_site, "torch", "lib")
    if os.path.isdir(candidate):
        return candidate

    # Fallback: scan sys.path in case site-packages resolution differs
    for p in sys.path:
        candidate = os.path.join(p, "torch", "lib")
        if os.path.isdir(candidate):
            return candidate
    return None


def apply():
    if sys.platform != "win32":
        return []  # only Windows needs this DLL-path workaround

    torch_lib = _find_torch_lib_dir()
    if torch_lib is None:
        return []

    if torch_lib not in os.environ.get("PATH", ""):
        os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")

    try:
        os.add_dll_directory(torch_lib)
    except (AttributeError, OSError):
        pass

    return [torch_lib]
