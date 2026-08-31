"""
UEFN TOOLBELT — launcher.py
========================================
Paste ONE of these into the UEFN Python REPL (Tools → Execute Python Script):

  Option A — preferred (portable, works on any machine):
    exec(open(unreal.Paths.project_content_dir() + "Python/launcher.py").read())

  Option B — if Option A fails (use your actual Windows path, raw string required):
    exec(open(r"C:\\Users\\YOURNAME\\Documents\\Fortnite Projects\\YOURPROJECT\\Content\\Python\\launcher.py").read())

  Note: Relative paths often fail in UEFN. Always use an absolute path or
  unreal.Paths.project_content_dir() — do NOT use a bare relative string.

The launcher:
  1. Adds Content/Python/ to sys.path
  2. Clears all cached Toolbelt modules (safe nuclear reload)
  3. Registers all 362 tools
  4. Opens the PySide6 tabbed dashboard (falls back gracefully if PySide6 missing)

Install PySide6 (one-time, run OUTSIDE UEFN in a regular terminal):
  & "C:\\Program Files\\Epic Games\\Fortnite\\Engine\\Binaries\\ThirdParty\\Python3\\Win64\\python.exe" -m pip install PySide6

Compatible with UEFN Python 3.11 experimental (v40.00+, March 2026)
API ground truth: Built-in API Explorer: tb.run("api_export_full") for IDE autocomplete stubs.
"""

import os
import sys

import unreal

# ── 1. Path setup ─────────────────────────────────────────────────────────────

_CONTENT_DIR = unreal.Paths.project_content_dir()
_PYTHON_ROOT = os.path.join(_CONTENT_DIR, "Python")

if _PYTHON_ROOT not in sys.path:
    sys.path.insert(0, _PYTHON_ROOT)

# ── 2. Nuclear reload — clears all cached modules so every import is fresh ───
#
# Safe to run repeatedly during development. The hardcoded module list approach
# was removed in v2.2.0 — it was brittle (missed new modules) and caused stale
# reload bugs. The sys.modules pop pattern is authoritative and always complete.
#
# ⚠️ If this was the FIRST time deploying a new module (new entry in
# tools/__init__.py), do a full UEFN restart instead — nuclear reload can
# crash on brand-new modules. See docs/UEFN_QUIRKS.md Quirk #26.

[sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]

# ── 3. Launch ─────────────────────────────────────────────────────────────────

try:
    import UEFN_Toolbelt as _tb
    _tb.launch()  # register_all_tools() → opens Qt dashboard
except Exception as _err:
    unreal.log_error(f"[TOOLBELT] Launch failed: {_err}")
    raise
