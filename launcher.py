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
  2. Hot-reloads all toolbelt modules (safe to run repeatedly during development)
  3. Registers all 21 tool modules (138 tools)
  4. Opens the PySide6 tabbed dashboard (falls back gracefully if PySide6 missing)

Install PySide6 (one-time, run OUTSIDE UEFN in a regular terminal):
  & "C:\\Program Files\\Epic Games\\Fortnite\\Engine\\Binaries\\ThirdParty\\Python3\\Win64\\python.exe" -m pip install PySide6

Compatible with UEFN Python 3.11 experimental (v40.00+, March 2026)
API ground truth: Built-in API Explorer: tb.run("api_export_full") for IDE autocomplete stubs.
"""

import sys
import os
import importlib
import unreal

# ── 1. Path setup ─────────────────────────────────────────────────────────────

_CONTENT_DIR  = unreal.Paths.project_content_dir()
_PYTHON_ROOT  = os.path.join(_CONTENT_DIR, "Python")

if _PYTHON_ROOT not in sys.path:
    sys.path.insert(0, _PYTHON_ROOT)

# ── 2. Hot-reload every module (safe to run repeatedly while developing) ───────

_ALL_MODULES = [
    # Core
    "UEFN_Toolbelt",
    "UEFN_Toolbelt.core",
    "UEFN_Toolbelt.registry",
    "UEFN_Toolbelt.tools",
    "UEFN_Toolbelt.dashboard_pyside6",
    # Tools
    "UEFN_Toolbelt.tools.material_master",
    "UEFN_Toolbelt.tools.arena_generator",
    "UEFN_Toolbelt.tools.spline_prop_placer",
    "UEFN_Toolbelt.tools.bulk_operations",
    "UEFN_Toolbelt.tools.verse_device_editor",
    "UEFN_Toolbelt.tools.smart_importer",
    "UEFN_Toolbelt.tools.verse_snippet_generator",
    "UEFN_Toolbelt.tools.text_painter",
    "UEFN_Toolbelt.tools.asset_renamer",
    "UEFN_Toolbelt.tools.foliage_tools",
    "UEFN_Toolbelt.tools.lod_tools",
    "UEFN_Toolbelt.tools.spline_to_verse",
    "UEFN_Toolbelt.tools.project_scaffold",
    "UEFN_Toolbelt.tools.memory_profiler",
    "UEFN_Toolbelt.tools.api_explorer",
    "UEFN_Toolbelt.tools.prop_patterns",
    "UEFN_Toolbelt.tools.reference_auditor",
    "UEFN_Toolbelt.tools.level_snapshot",
    "UEFN_Toolbelt.tools.asset_tagger",
    "UEFN_Toolbelt.tools.screenshot_tools",
    "UEFN_Toolbelt.tools.mcp_bridge",
]

for _mod in _ALL_MODULES:
    if _mod in sys.modules:
        try:
            importlib.reload(sys.modules[_mod])
        except Exception as _e:
            unreal.log_warning(f"[TOOLBELT] Reload skipped for {_mod}: {_e}")

# ── 3. Launch ─────────────────────────────────────────────────────────────────

try:
    import UEFN_Toolbelt as _tb
    _tb.launch()  # registers all tools → opens Qt dashboard
except Exception as _err:
    unreal.log_error(f"[TOOLBELT] Launch failed: {_err}")
    raise
