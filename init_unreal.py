"""
init_unreal.py — Generic Python Package Loader for UEFN / Unreal Engine
========================================================================
Copy this file to:  [YourProject]/Content/Python/init_unreal.py

Unreal Engine automatically executes any file named exactly "init_unreal.py"
inside Content/Python/ every time the editor starts.

This file is intentionally generic — it knows nothing about UEFN Toolbelt
or any other specific package. It simply:

  1. Adds Content/Python/ to sys.path so packages are importable.
  2. Scans for any sub-directory that is a Python package (has __init__.py).
  3. Calls package.register() on each one that exposes it.

To make your own package auto-load, add a register() function to its
__init__.py. The loader will call it on every editor startup.

Example:
    # MyTool/__init__.py
    def register() -> None:
        import unreal
        unreal.log("[MyTool] loaded")
        # ... register tools, menus, etc.
"""

import sys
import os
import importlib
import unreal

# ── 1. Path setup ─────────────────────────────────────────────────────────────

# __file__ is Content/Python/init_unreal.py — its directory IS the Python dir.
# unreal.Paths.project_content_dir() returns the FortniteGame engine path in UEFN
# (Quirk #23) and must not be used here.
_PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))

if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

# ── 2. Discover and load all packages with a register() function ──────────────

_loaded: list = []
_failed: list = []

try:
    _entries = os.listdir(_PYTHON_DIR)
except OSError:
    _entries = []

for _name in sorted(_entries):
    _pkg_path = os.path.join(_PYTHON_DIR, _name)
    # Must be a directory with an __init__.py (i.e. a proper Python package)
    if not os.path.isdir(_pkg_path):
        continue
    if not os.path.exists(os.path.join(_pkg_path, "__init__.py")):
        continue
    try:
        _mod = importlib.import_module(_name)
        if callable(getattr(_mod, "register", None)):
            _mod.register()
            _loaded.append(_name)
        # Packages without register() are silently skipped — they may be
        # libraries or utilities that don't need an init hook.
    except Exception as _e:
        _failed.append(_name)
        unreal.log_error(f"[LOADER] Failed to load '{_name}': {_e}")

# ── 3. Summary ────────────────────────────────────────────────────────────────

if _loaded:
    unreal.log(f"[LOADER] ✓ {len(_loaded)} package(s) registered: {', '.join(_loaded)}")
if _failed:
    unreal.log_warning(f"[LOADER] {len(_failed)} package(s) failed: {', '.join(_failed)}")
if not _loaded and not _failed:
    unreal.log("[LOADER] No packages with register() found in Content/Python/.")
