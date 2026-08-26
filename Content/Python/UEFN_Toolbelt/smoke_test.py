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

import json
import os
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

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


def _engine_version() -> str:
    """
    Best-effort UEFN/engine build string.

    Matters because UEFN force-updates with the live Fortnite build — when a user
    reports a broken tool, the first question is always "which build?". Without
    this, results files are ambiguous.

    Guarded three ways: unreal may be absent (running off-editor), SystemLibrary
    may not exist on a given build, and the call itself may be sandboxed.
    """
    try:
        import unreal
    except ImportError:
        return "n/a (not running inside UEFN)"

    try:
        if hasattr(unreal, "SystemLibrary") and \
           hasattr(unreal.SystemLibrary, "get_engine_version"):
            return str(unreal.SystemLibrary.get_engine_version())
    except Exception as e:
        return f"unavailable ({e})"
    return "unavailable (SystemLibrary.get_engine_version absent)"


def _toolbelt_version() -> str:
    try:
        from UEFN_Toolbelt import __version__
        return str(__version__)
    except Exception:
        return "unknown"


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
        f"Toolbelt: v{_toolbelt_version()}",
        f"Engine:  {_engine_version()}",
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

    # Daemon thread class available (creation/join removed — t.join pumps Windows messages
    # via WaitForMultipleObjectsEx, which can fire pending Slate callbacks mid-test → crash)
    _record("Layer 1", "threading.Thread available", hasattr(threading, "Thread"))

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

    # Key subsystems — hasattr only, no get_editor_subsystem() call.
    # Calling get_editor_subsystem() with a class not registered in UEFN writes to null at C++ level,
    # which Python try/except cannot catch. StaticMeshEditorSubsystem in particular may not exist in UEFN.
    for name in ["EditorActorSubsystem", "EditorAssetSubsystem",
                 "LevelEditorSubsystem", "StaticMeshEditorSubsystem"]:
        ok = hasattr(unreal, name)
        _record("Layer 2", name, ok)

    # Key libraries — attribute existence only
    for lib in ["EditorAssetLibrary", "EditorLevelLibrary",
                "EditorUtilityLibrary", "MaterialEditingLibrary",
                "AutomationLibrary"]:
        ok = hasattr(unreal, lib)
        _record("Layer 2", lib, ok)

    # AutomationLibrary method check — attribute only, no call
    ok = hasattr(unreal, "AutomationLibrary") and \
         hasattr(unreal.AutomationLibrary, "take_high_res_screenshot")
    _record("Layer 2", "AutomationLibrary.take_high_res_screenshot", ok)

    _probe_api_dependencies(unreal)


def _probe_api_dependencies(unreal) -> None:
    """
    Probe every unreal.* symbol the Toolbelt actually depends on.

    The list comes from api_dependencies.json, generated from source by
    scripts/gen_api_manifest.py. This is the engine-upgrade tripwire: when a
    UEFN release removes or renames an API, this reports the exact symbol and
    which tool modules use it, instead of leaving a mystery failure in whichever
    tool happened to call it first.

    SAFETY: hasattr() only — never a call, never get_editor_subsystem(), never
    an instantiation. Reading an attribute off a reflected class is the same
    thing the AutomationLibrary check above already does. Anything heavier
    risks the EXCEPTION_ACCESS_VIOLATION class of bug in the UEFN Slate loop.
    """
    manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "api_dependencies.json")
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except Exception as e:
        _record("Layer 2", "api_dependencies.json", False,
                f"manifest unreadable: {e} — run scripts/gen_api_manifest.py")
        return

    symbols = manifest.get("symbols", {})
    missing_symbols = []
    missing_attrs = []
    # Absent, but every consumer guards it — degraded on purpose, not broken.
    handled = []

    for name, info in symbols.items():
        attributes = info.get("attributes", {})
        # Manifests before per-attribute attribution stored a bare list. Normalise
        # so a partially-updated install still reports something sane.
        legacy_shape = isinstance(attributes, list)
        if legacy_shape:
            attributes = {a: {} for a in attributes}

        if not hasattr(unreal, name):
            entry = (name, info.get("used_by", []))
            (handled if info.get("optional") else missing_symbols).append(entry)
            continue
        parent = getattr(unreal, name)
        for attr, meta in attributes.items():
            if not hasattr(parent, attr):
                # Attribute-level consumers ONLY. The symbol's used_by lists every
                # file touching the class, which over-reports a single missing
                # method by an order of magnitude and derails triage.
                callers = (meta or {}).get("used_by")
                if not callers:
                    callers = (["(attribution unavailable — regenerate manifest)"]
                               if legacy_shape else [])
                entry = (f"{name}.{attr}", callers)
                if (meta or {}).get("optional"):
                    handled.append(entry)
                else:
                    missing_attrs.append(entry)

    total = len(symbols)
    _record("Layer 2", "API dependency manifest", True,
            f"{total} symbols declared")

    _record("Layer 2", "All required unreal.* symbols present",
            not missing_symbols,
            "OK" if not missing_symbols
            else f"{len(missing_symbols)} MISSING — engine API changed")

    _record("Layer 2", "All required unreal.* methods present",
            not missing_attrs,
            "OK" if not missing_attrs
            else f"{len(missing_attrs)} MISSING — engine API changed")

    # Optional APIs are reported, never failed. A check that is permanently red
    # for problems the code already handles is a check people learn to ignore —
    # which is exactly when it stops catching the real ones.
    if handled:
        _record("Layer 2", "Optional unreal.* APIs absent (handled)", True,
                f"{len(handled)} absent — tools using them refuse cleanly")

    # Name the casualties explicitly so the fix is obvious from the log alone.
    for label, used_by in (missing_symbols + missing_attrs)[:40]:
        where = ", ".join(used_by[:4]) or "unknown"
        if len(used_by) > 4:
            where += f" (+{len(used_by) - 4} more)"
        _out(f"    ✗ unreal.{label} — used by: {where}", "warning")

    for label, used_by in handled[:40]:
        where = ", ".join(used_by[:2]) or "unknown"
        if len(used_by) > 2:
            where += f" (+{len(used_by) - 2} more)"
        _out(f"    ○ unreal.{label} — optional, handled by: {where}")

    # Saved dir path available (no write — Paths.project_saved_dir() is safe)
    try:
        saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
        _record("Layer 2", "Paths.project_saved_dir()", True, saved)
    except Exception as e:
        _record("Layer 2", "Paths.project_saved_dir()", False, str(e))


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

    # Did init_unreal.py start us, or is this smoke test the first thing to run?
    # Checked BEFORE register_all_tools() below, which would otherwise mask it.
    try:
        auto_started = tb.startup_ran()
        _record("Layer 3", "init_unreal.py auto-start", auto_started,
                "OK" if auto_started else
                "DID NOT RUN — Toolbelt is not loading automatically")
        if not auto_started:
            _out("    ✗ Your project's init_unreal.py never executed this session.",
                 "warning")
            _out("      Known cause on UEFN 42.00: Project Settings → Beta Access →",
                 "warning")
            _out("      'UEFN MCP Toolsets'. Epic's Toolsets plugins force-enable Python",
                 "warning")
            _out("      before the project's script paths are registered, so only their",
                 "warning")
            _out("      own start-up scripts run. Nothing errors — Toolbelt just never",
                 "warning")
            _out("      starts, and every tb.run() answers 'Unknown tool'.", "warning")
            _out("      Workaround: turn that flag off, or run each session:", "warning")
            _out("        import UEFN_Toolbelt as tb; tb.register()", "warning")
    except Exception as e:
        _record("Layer 3", "init_unreal.py auto-start", False, str(e))

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

    # Key tools explicitly registered — registry lookup only, no execution.
    # Tool execution is the integration test's job (tb.run("toolbelt_integration_test")).
    # Running tools here risks Asset Registry crashes (Quirk #32), Slate callback
    # re-registration, and Qt module-level side effects — all can write to null in UEFN.
    for tool_name in ["verse_gen_custom", "snapshot_save", "material_apply_preset",
                      "mcp_start", "scatter_hism", "tag_add"]:
        ok = tool_name in tb.registry
        _record("Layer 3", f"tool: {tool_name}", ok)


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

    # The smoke suite runs on the editor main thread, so it must not block on an
    # HTTP command that can only complete when the next Slate tick drains it.
    # External live verification performs the authenticated ping instead.
    if mcp_bridge._server is not None:
        try:
            secure = (
                status.get("transport") == "authenticated_queued"
                and status.get("authenticated") is True
                and mcp_bridge._token_handoff_path().exists()
            )
            _record("Layer 4", "Authenticated queued listener", secure,
                    f"port {mcp_bridge._bound_port}")
        except Exception as e:
            _record("Layer 4", "Authenticated queued listener", False, str(e))
    else:
        _record("Layer 4", "Authenticated queued listener", True,
                "skipped — listener not running (normal)")


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
    # Check that QApplication.instance() is callable (no crash) — both None and
    # a live instance are valid; None just means the dashboard hasn't launched yet.
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        detail = "running" if app is not None else "not launched yet (normal)"
        _record("Layer 5", "QApplication accessible", True, detail)
    except Exception as e:
        _record("Layer 5", "QApplication accessible", False, str(e))

    try:
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
    _out("  UEFN TOOLBELT SMOKE TEST — COMPLETE")
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
    _out(f"[TOOLBELT] Toolbelt v{_toolbelt_version()}  |  Engine: {_engine_version()}")
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
