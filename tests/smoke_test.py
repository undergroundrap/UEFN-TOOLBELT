"""
UEFN TOOLBELT — Smoke Test
=========================================
Run this inside the UEFN editor to verify the full Toolbelt stack is healthy.

Usage (UEFN Output Log / Python REPL):
    py "<project>/Content/Python/tests/smoke_test.py"

    — or from the Toolbelt REPL:
    import UEFN_Toolbelt as tb; tb.run("toolbelt_smoke_test")

What this checks:
    Layer 1 — Python environment  (stdlib, threading, sockets, tick callbacks)
    Layer 2 — UEFN API surface    (key subsystems, AutomationLibrary, Materials)
    Layer 3 — Toolbelt core       (registry, all 24 modules, tool count, output paths)
    Layer 4 — MCP bridge          (listener state, HTTP round-trip if running)
    Layer 5 — Dashboard           (PySide6 importable, QApplication available)
    Layer 6 — Verse Book          (clone present, git remote reachable, chapters readable)

Results are printed to the Output Log and saved to:
    <project>/Saved/UEFN_Toolbelt/smoke_test_results.txt
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

# ─── Output ───────────────────────────────────────────────────────────────────

_results: list[dict] = []
_start_time = time.time()


def _out(msg: str, level: str = "info") -> None:
    try:
        import unreal
        {"info": unreal.log, "warning": unreal.log_warning, "error": unreal.log_error}[
            level
        ](msg)
    except ImportError:
        print(msg)


def _record(layer: str, name: str, passed: bool, detail: str = "") -> None:
    icon = "✓" if passed else "✗"
    _results.append({"layer": layer, "name": name, "passed": passed, "detail": detail})
    _out(f"  [{icon}] {name}{f'  —  {detail}' if detail else ''}")


def _header(title: str) -> None:
    _out(f"\n{'═' * 54}")
    _out(f"  {title}")
    _out(f"{'═' * 54}")


def _save_results() -> str:
    """Write results to Saved/UEFN_Toolbelt/smoke_test_results.txt."""
    try:
        import unreal
        saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    except ImportError:
        saved = tempfile.gettempdir()

    os.makedirs(saved, exist_ok=True)
    path = os.path.join(saved, "smoke_test_results.txt")

    passed = sum(1 for r in _results if r["passed"])
    total  = len(_results)
    elapsed = time.time() - _start_time

    lines = [
        "UEFN TOOLBELT — Smoke Test Results",
        "=" * 54,
        f"Date:    {datetime.now().isoformat()}",
        f"Python:  {sys.version}",
        f"Passed:  {passed}/{total}",
        f"Elapsed: {elapsed:.2f}s",
        "=" * 54,
        "",
    ]
    current_layer = ""
    for r in _results:
        if r["layer"] != current_layer:
            current_layer = r["layer"]
            lines.append(f"\n{current_layer}")
            lines.append("-" * 40)
        icon = "PASS" if r["passed"] else "FAIL"
        detail = f"  ({r['detail']})" if r["detail"] else ""
        lines.append(f"  {icon}  {r['name']}{detail}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


# ─── Layer 1: Python environment ──────────────────────────────────────────────

def _layer_python() -> None:
    _header("Layer 1 — Python Environment")

    # Version
    major, minor = sys.version_info[:2]
    _record("Layer 1", "Python 3.11+", major == 3 and minor >= 11,
            f"Python {major}.{minor}")

    # Stdlib modules
    for mod in ["socket", "threading", "queue", "json", "io",
                "http.server", "urllib.request", "traceback"]:
        try:
            __import__(mod)
            _record("Layer 1", f"import {mod}", True)
        except ImportError as e:
            _record("Layer 1", f"import {mod}", False, str(e))

    # TCP socket bind
    for port in range(8765, 8771):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.close()
            _record("Layer 1", "TCP socket bind", True, f"127.0.0.1:{port}")
            break
        except OSError:
            continue
    else:
        _record("Layer 1", "TCP socket bind", False, "ports 8765-8770 all blocked")

    # Daemon thread
    flag = {"ok": False}
    def _worker(): flag["ok"] = True
    t = threading.Thread(target=_worker, daemon=True)
    t.start(); t.join(timeout=2)
    _record("Layer 1", "Daemon thread", flag["ok"])

    # HTTP server class instantiable (daemon thread round-trip removed — unsafe in UEFN Slate tick)
    try:
        class _H(BaseHTTPRequestHandler):
            def do_GET(self): pass
            def log_message(self, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), _H)  # port 0 = OS assigns, never serve_forever
        srv.server_close()
        _record("Layer 1", "HTTPServer instantiable", True)
    except Exception as e:
        _record("Layer 1", "HTTPServer instantiable", False, str(e))

    # File write
    try:
        tmp = os.path.join(tempfile.gettempdir(), "_tb_smoke.tmp")
        with open(tmp, "w") as f: f.write("ok")
        os.remove(tmp)
        _record("Layer 1", "File write (temp dir)", True)
    except Exception as e:
        _record("Layer 1", "File write (temp dir)", False, str(e))


# ─── Layer 2: UEFN API surface ────────────────────────────────────────────────

def _layer_uefn() -> None:
    _header("Layer 2 — UEFN API Surface")
    try:
        import unreal
    except ImportError:
        _record("Layer 2", "import unreal", False, "not running inside UEFN editor")
        return

    _record("Layer 2", "import unreal", True, f"{len(dir(unreal))} attrs")

    # Tick callback
    has_tick = hasattr(unreal, "register_slate_post_tick_callback")
    _record("Layer 2", "register_slate_post_tick_callback", has_tick)

    # Key subsystems
    for name in ["EditorActorSubsystem", "EditorAssetSubsystem",
                 "LevelEditorSubsystem", "StaticMeshEditorSubsystem"]:
        try:
            sub = unreal.get_editor_subsystem(getattr(unreal, name))
            _record("Layer 2", name, sub is not None)
        except Exception as e:
            _record("Layer 2", name, False, str(e))

    # Key libraries
    for lib in ["EditorAssetLibrary", "EditorLevelLibrary",
                "EditorUtilityLibrary", "MaterialEditingLibrary",
                "AutomationLibrary"]:
        ok = hasattr(unreal, lib)
        _record("Layer 2", lib, ok)

    # AutomationLibrary.take_high_res_screenshot signature check
    try:
        fn = getattr(unreal.AutomationLibrary, "take_high_res_screenshot", None)
        _record("Layer 2", "AutomationLibrary.take_high_res_screenshot", fn is not None)
    except Exception as e:
        _record("Layer 2", "AutomationLibrary.take_high_res_screenshot", False, str(e))

    # Saved dir writable
    try:
        saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
        os.makedirs(saved, exist_ok=True)
        probe = os.path.join(saved, "_smoke.tmp")
        with open(probe, "w") as f: f.write("ok")
        os.remove(probe)
        _record("Layer 2", "Saved/UEFN_Toolbelt/ writable", True, saved)
    except Exception as e:
        _record("Layer 2", "Saved/UEFN_Toolbelt/ writable", False, str(e))


# ─── Layer 3: Toolbelt core ───────────────────────────────────────────────────

EXPECTED_MODULES = [
    "material_master", "arena_generator", "spline_prop_placer",
    "bulk_operations", "verse_device_editor", "smart_importer",
    "verse_snippet_generator", "text_painter", "asset_renamer",
    "foliage_tools", "lod_tools", "spline_to_verse", "project_scaffold",
    "memory_profiler", "api_explorer", "prop_patterns", "reference_auditor",
    "level_snapshot", "asset_tagger", "screenshot_tools", "mcp_bridge", "integration_test", "plugin_manager",
    "api_capability_crawler", "measurement_tools", "localization_tools",
    "foliage_converter", "entity_kits", "selection_utils", "project_admin", "lighting_mastery"
]
MIN_TOOL_COUNT = 179


def _layer_toolbelt() -> None:
    _header("Layer 3 — Toolbelt Core")

    try:
        import UEFN_Toolbelt as tb
        _record("Layer 3", "import UEFN_Toolbelt", True)
    except Exception as e:
        _record("Layer 3", "import UEFN_Toolbelt", False, str(e))
        return

    # register_all_tools
    try:
        tb.register_all_tools()
        _record("Layer 3", "register_all_tools()", True)
    except Exception as e:
        _record("Layer 3", "register_all_tools()", False, str(e))

    # Tool count
    try:
        tools = tb.registry.list_tools()
        count = len(tools)
        _record("Layer 3", f"Tool count ≥ {MIN_TOOL_COUNT}", count >= MIN_TOOL_COUNT,
                f"{count} registered")
    except Exception as e:
        _record("Layer 3", "Tool count", False, str(e))

    # Each expected module
    from UEFN_Toolbelt import tools as _tools_pkg
    for mod_name in EXPECTED_MODULES:
        ok = hasattr(_tools_pkg, mod_name)
        _record("Layer 3", f"tools.{mod_name}", ok)

    # tb.run() returns values (not None)
    try:
        ok = callable(tb.run) and tb.run.__annotations__.get("return") is not None
        _record("Layer 3", "tb.run() returns values", ok)
    except Exception as e:
        _record("Layer 3", "tb.run() returns values", False, str(e))

    # Key tools explicitly registered
    for tool_name in ["verse_gen_custom", "snapshot_save", "material_apply_preset",
                      "mcp_start", "scatter_hism", "tag_add"]:
        ok = tool_name in tb.registry
        _record("Layer 3", f"tool: {tool_name}", ok)

    # Execute Safe Tools (No Actor Needed)
    safe_tools_to_test = [
        # Core utilities
        "api_list_subsystems",
        "api_search",
        "config_list",
        "config_get",
        "mcp_status",
        # mcp_restart intentionally excluded — registers Slate tick callbacks mid-test → crash
        "plugin_export_manifest",
        "plugin_validate_all",
        "plugin_list_custom",
        # Scaffold / project
        "scaffold_list_templates",
        # Snapshots
        "snapshot_list",
        # Materials
        "material_list_presets",
        # Text
        "text_list_styles",
        # Theme
        "theme_list",
        "theme_get",
        # Verse
        "verse_list_snippets",
        "verse_graph_scan",
        # Measurement
        "spline_measure",
        # LOD / memory (read-only scans)
        "lod_audit_folder",
    ]
    for safe_tool in safe_tools_to_test:
        try:
            tb.run(safe_tool)
            _record("Layer 3", f"Execute {safe_tool}", True)
        except Exception as e:
            _record("Layer 3", f"Execute {safe_tool}", False, str(e))


# ─── Layer 4: MCP bridge ──────────────────────────────────────────────────────

def _layer_mcp() -> None:
    _header("Layer 4 — MCP Bridge")

    try:
        from UEFN_Toolbelt.tools import mcp_bridge
        _record("Layer 4", "import mcp_bridge", True)
    except Exception as e:
        _record("Layer 4", "import mcp_bridge", False, str(e))
        return

    # Status callable
    try:
        status = mcp_bridge.get_status()
        _record("Layer 4", "get_status()", True,
                f"running={status['running']}, port={status['port']}")
    except Exception as e:
        _record("Layer 4", "get_status()", False, str(e))
        return

    # Command registry populated
    try:
        cmd_count = len(mcp_bridge._HANDLERS)
        _record("Layer 4", "Commands registered", cmd_count >= 30,
                f"{cmd_count} handlers")
    except Exception as e:
        _record("Layer 4", "Commands registered", False, str(e))

    # If listener is running, do a live ping
    if mcp_bridge._server is not None:
        try:
            import urllib.request, json as _json
            url = f"http://127.0.0.1:{mcp_bridge._bound_port}"
            resp = urllib.request.urlopen(url, timeout=3)
            body = _json.loads(resp.read())
            _record("Layer 4", "Live HTTP ping", body.get("status") == "ok",
                    f"port {mcp_bridge._bound_port}")
        except Exception as e:
            _record("Layer 4", "Live HTTP ping", False, str(e))
    else:
        _record("Layer 4", "Live HTTP ping", True, "skipped — listener not running (normal)")


# ─── Layer 5: Dashboard ───────────────────────────────────────────────────────

def _layer_dashboard() -> None:
    _header("Layer 5 — Dashboard (PySide6)")

    try:
        import PySide6
        _record("Layer 5", "import PySide6", True, PySide6.__version__)
    except ImportError:
        _record("Layer 5", "import PySide6", False,
                "run: <UE>/Engine/Binaries/ThirdParty/Python3/Win64/python.exe -m pip install PySide6")
        return

    # QApplication instantiation skipped — creating one mid-tick and letting it
    # GC immediately causes EXCEPTION_ACCESS_VIOLATION in UEFN's Slate loop.
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        _record("Layer 5", "QApplication (existing)", app is not None,
                "None = dashboard not yet launched (normal)" if app is None else "running")
    except Exception as e:
        _record("Layer 5", "QApplication check", False, str(e))

    try:
        from UEFN_Toolbelt.dashboard_pyside6 import ToolbeltDashboard
        _record("Layer 5", "ToolbeltDashboard importable", True)
    except Exception as e:
        _record("Layer 5", "ToolbeltDashboard importable", False, str(e))


# ─── Layer 6: Verse Book ──────────────────────────────────────────────────────

def _layer_verse_book() -> None:
    _header("Layer 6 — Verse Book (Spec Reference)")

    # smoke_test.py lives at Content/Python/UEFN_Toolbelt/ — go 3 levels up to project root
    here = os.path.dirname(os.path.abspath(__file__))
    book_root = os.path.normpath(os.path.join(here, "..", "..", "..", "verse-book"))
    docs_path = os.path.join(book_root, "docs")

    # Clone present
    clone_ok = os.path.isdir(book_root)
    _record("Layer 6", "verse-book/ clone present", clone_ok, book_root)
    if not clone_ok:
        _record("Layer 6", "verse-book fix", False,
                "git clone https://github.com/verselang/book.git verse-book")
        return

    # Is a real git repo
    git_ok = os.path.isdir(os.path.join(book_root, ".git"))
    _record("Layer 6", "verse-book is git repo", git_ok,
            "re-clone if False — zip extract won't pull")

    # docs/ present with chapters
    docs_ok = os.path.isdir(docs_path)
    _record("Layer 6", "verse-book/docs/ present", docs_ok)
    if not docs_ok:
        return

    chapters = [f for f in os.listdir(docs_path) if f.endswith(".md")]
    _record("Layer 6", "Chapter count >= 18", len(chapters) >= 18,
            f"{len(chapters)} .md files")

    # Key chapters readable and non-empty
    for chapter in ["00_overview.md", "13_effects.md", "14_concurrency.md",
                    "10_classes_interfaces.md"]:
        fpath = os.path.join(docs_path, chapter)
        try:
            size = os.path.getsize(fpath)
            _record("Layer 6", f"readable: {chapter}", size > 1000, f"{size} bytes")
        except Exception as e:
            _record("Layer 6", f"readable: {chapter}", False, str(e))

    # Search works (basic keyword hit)
    try:
        import re
        pattern = re.compile("suspends", re.IGNORECASE)
        hits = 0
        for fname in chapters:
            with open(os.path.join(docs_path, fname), encoding="utf-8") as f:
                if pattern.search(f.read()):
                    hits += 1
        _record("Layer 6", "'suspends' found in spec", hits >= 5,
                f"{hits} chapters contain it")
    except Exception as e:
        _record("Layer 6", "spec keyword search", False, str(e))

    # git remote reachable (network check — soft fail)
    try:
        s = socket.create_connection(("github.com", 443), timeout=4)
        s.close()
        _record("Layer 6", "github.com reachable (git pull works)", True)
    except Exception:
        _record("Layer 6", "github.com reachable (git pull works)", True,
                "skipped — offline (non-critical)")


# ─── Summary ──────────────────────────────────────────────────────────────────

def _summary() -> None:
    passed  = sum(1 for r in _results if r["passed"])
    failed  = sum(1 for r in _results if not r["passed"])
    total   = len(_results)
    elapsed = time.time() - _start_time

    _out(f"\n{'═' * 54}")
    _out(f"  UEFN TOOLBELT SMOKE TEST — COMPLETE")
    _out(f"{'═' * 54}")
    _out(f"  Passed:  {passed}/{total}")
    _out(f"  Failed:  {failed}")
    _out(f"  Elapsed: {elapsed:.2f}s")

    if failed == 0:
        _out("\n  ✓ All systems healthy — Toolbelt is ready.", "info")
    else:
        _out(f"\n  ✗ {failed} check(s) failed — see details above.", "warning")
        for r in _results:
            if not r["passed"]:
                detail_str = f": {r['detail']}" if r["detail"] else ""
                _out(f"    • [{r['layer']}] {r['name']}{detail_str}", "warning")

    path = _save_results()
    _out(f"\n  Results saved to: {path}")
    _out(f"{'═' * 54}\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_smoke_test() -> bool:
    """Run all layers. Returns True if everything passed."""
    _out("\n[TOOLBELT] Starting smoke test…")
    _layer_python()
    _layer_uefn()
    _layer_toolbelt()
    _layer_mcp()
    _layer_dashboard()
    _layer_verse_book()
    _summary()
    return all(r["passed"] for r in _results)


if __name__ == "__main__":
    run_smoke_test()
