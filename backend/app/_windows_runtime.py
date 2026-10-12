"""Windows only: make sure an up-to-date Microsoft C++ runtime is the one loaded into the process.

The transcription runtime (ctranslate2) crashes the whole process while loading a model if Windows
resolves `msvcp140.dll` to an old system copy (older than 14.40). The `msvc-runtime` package ships
a current copy into the virtual environment; loading it first means later imports reuse it.
This must run before any other native extension is imported.
"""

import ctypes
import os
import sys
from pathlib import Path


def preload_msvc_runtime() -> bool:
    """Load the virtual environment's msvcp140.dll if there is one. Returns whether it was loaded."""
    if os.name != "nt":
        return False
    candidate = Path(sys.prefix) / "Scripts" / "msvcp140.dll"
    if not candidate.is_file():
        return False
    try:
        ctypes.WinDLL(str(candidate))
    except OSError:
        return False
    return True
