"""
UEFN TOOLBELT — Package Root
========================================
Public API:
    import UEFN_Toolbelt as tb
    tb.register_all_tools()   # called automatically by init_unreal.py
    tb.launch_qt()            # open PySide6 tabbed dashboard (recommended)
    tb.launch()               # fallback: UMG widget or text list
    tb.run("tool_name")              # execute any tool by name
    tb.run("toolbelt_smoke_test")    # run the 6-layer health check
    tb.registry               # access the ToolRegistry directly

Generic loader contract:
    init_unreal.py calls tb.register() on every package that exposes it.
    register() handles tool loading, custom plugins, and menu scheduling.
"""

from typing import Any

from .registry import ToolRegistry, get_registry, register_tool
from . import core
from .core.config import get_config

# tb.config — persistent user settings, survives install.py updates
# Lives at Saved/UEFN_Toolbelt/config.json
config = get_config()

# ── Version ───────────────────────────────────────────────────────────────────
# Single source of truth — used in audit logs, reload messages, and manifests.
# Bump this when shipping a release so plugin_audit.json records which version
# of the platform each plugin was loaded against.
__version__ = "1.9.7"

# Total registered tools — update alongside __version__ when adding/removing tools.
# Checked by scripts/drift_check.py to catch stale counts across docs and UI.
__tool_count__ = 291

# Total tool categories — update when adding a new category to any tool module.
# Shown in the reload message: "269 tools registered across 42 categories."
# Checked by scripts/drift_check.py to catch stale category counts across docs.
__category_count__ = 43

# API contract version — plugins declare MIN_TOOLBELT_VERSION = "x.y.z" to
# signal the oldest platform release they support. Checked at load time.
TOOLBELT_API_VERSION = __version__

# Singleton registry shared across all imports
registry: ToolRegistry = get_registry()


def register() -> None:
    """
    Generic loader entry point — called by init_unreal.py on editor startup.
    Registers all tools, loads custom plugins, and schedules the editor menu.
    Any Python package placed in Content/Python/ that exposes this function
    will be picked up automatically by the generic loader.
    """
    import unreal
    register_all_tools()
    load_custom_plugins()
    unreal.log("[TOOLBELT] ✓ All tools registered.")
    unreal.log("[TOOLBELT]   Run 'toolbelt_integration_test' in a clean level to verify.")
    _schedule_menu()


def _schedule_menu() -> None:
    """
    Defer menu building to the first editor tick.
    init_unreal.py runs before Slate is constructed — ToolMenus.get()
    must not be called until the menu bar exists.
    """
    import unreal
    _registered = False

    def _on_tick(dt: float) -> None:
        nonlocal _registered
        if _registered:
            return
        _registered = True
        try:
            from .menu import build_toolbelt_menu
            build_toolbelt_menu()
        except Exception as _e:
            unreal.log_warning(f"[TOOLBELT] Menu registration failed: {_e}")
        finally:
            unreal.unregister_slate_pre_tick_callback(_handle)

    _handle = unreal.register_slate_pre_tick_callback(_on_tick)


def register_all_tools() -> None:
    """Import every tool module so their @register_tool decorators fire."""
    from . import tools as _tools  # noqa: F401 — triggers all sub-imports
    from . import diagnostics as _diag  # noqa: F401 — registers debug tools
    from . import dashboard_pyside6 as _dash  # noqa: F401 — registers launch_qt tool
    import unreal
    unreal.log(f"[TOOLBELT] {len(registry)} tools registered across {len(registry.categories())} categories.")


def load_custom_plugins() -> None:
    """Load user-provided tools from Saved/UEFN_Toolbelt/Custom_Plugins."""
    import os, sys, glob, importlib, ast, hashlib, json, unreal
    from datetime import datetime
    custom_plugins_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "Custom_Plugins")
    if not os.path.exists(custom_plugins_dir):
        return
        
    if custom_plugins_dir not in sys.path:
        sys.path.insert(0, custom_plugins_dir)

    # ── Security Config ──────────────────────────────────────────────────────
    MAX_PLUGIN_SIZE_KB = 50   # Reject files larger than 50 KB (likely obfuscated)

    _BLOCKED_IMPORTS = frozenset({
        "subprocess", "shutil", "ctypes", "socket", "http",
        "urllib", "requests", "webbrowser", "smtplib", "ftplib",
        "xmlrpc", "multiprocessing", "signal", "_thread",
    })

    def _scan_plugin(filepath: str) -> list:
        """Parse a .py file via AST (without executing it) and flag dangerous imports."""
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=filepath)
            except SyntaxError as e:
                return [f"SyntaxError: {e}"]
        
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split(".")[0]
                    if root_module in _BLOCKED_IMPORTS:
                        violations.append(f"Blocked import: '{alias.name}' (line {node.lineno})")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_module = node.module.split(".")[0]
                    if root_module in _BLOCKED_IMPORTS:
                        violations.append(f"Blocked import: 'from {node.module}' (line {node.lineno})")
        return violations

    def _sha256(filepath: str) -> str:
        """Compute the SHA-256 hash of a file for integrity verification."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ── Audit Log ────────────────────────────────────────────────────────────
    saved_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved_dir, exist_ok=True)
    audit_path = os.path.join(saved_dir, "plugin_audit.json")
    audit_log = []

    valid_count = 0
    for p in glob.glob(os.path.join(custom_plugins_dir, "*.py")):
        module_name = os.path.splitext(os.path.basename(p))[0]
        file_size_kb = os.path.getsize(p) / 1024.0

        # Gate 1: File size limit
        if file_size_kb > MAX_PLUGIN_SIZE_KB:
            unreal.log_error(f"[SECURITY] Plugin '{module_name}.py' blocked — {file_size_kb:.1f} KB exceeds {MAX_PLUGIN_SIZE_KB} KB limit.")
            audit_log.append({"plugin": module_name, "status": "BLOCKED_SIZE", "size_kb": round(file_size_kb, 1)})
            continue

        # Gate 2: AST import scan (pre-execution)
        violations = _scan_plugin(p)
        if violations:
            unreal.log_error(f"[SECURITY] Plugin '{module_name}.py' blocked — dangerous imports detected:")
            for v in violations:
                unreal.log_error(f"  • {v}")
            audit_log.append({"plugin": module_name, "status": "BLOCKED_IMPORTS", "violations": violations})
            continue

        # Gate 2.5: API version compatibility check
        import re as _re
        with open(p, "r", encoding="utf-8") as _vf:
            _src = _vf.read()
        _ver_match = _re.search(r'^MIN_TOOLBELT_VERSION\s*=\s*["\']([^"\']+)["\']', _src, _re.MULTILINE)
        if _ver_match:
            _required = _ver_match.group(1)
            def _ver_tuple(v):
                try: return tuple(int(x) for x in v.split("."))
                except: return (0,)
            if _ver_tuple(_required) > _ver_tuple(__version__):
                unreal.log_warning(
                    f"[TOOLBELT] ⚠ Plugin '{module_name}' requires Toolbelt v{_required} "
                    f"but platform is v{__version__}. Loading anyway — some features may not work. "
                    f"Update UEFN Toolbelt to silence this warning."
                )

        # Gate 3: SHA-256 integrity hash
        file_hash = _sha256(p)
        
        try:
            importlib.import_module(module_name)
            valid_count += 1
            unreal.log(f"[TOOLBELT] ✓ Plugin loaded: {module_name} (SHA-256: {file_hash[:12]}…)")
            audit_log.append({
                "plugin": module_name,
                "status": "LOADED",
                "toolbelt_version": __version__,
                "sha256": file_hash,
                "size_kb": round(file_size_kb, 1),
                "loaded_at": datetime.now().isoformat(),
            })
        except Exception as e:
            unreal.log_error(f"[TOOLBELT] Failed to load plugin {module_name}.py: {e}")
            audit_log.append({"plugin": module_name, "status": "LOAD_ERROR", "error": str(e)})

    # Write the audit log — toolbelt_version stamps which platform release
    # loaded these plugins, so shared audit files carry provenance.
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump({
            "toolbelt_version": __version__,
            "scan_time": datetime.now().isoformat(),
            "plugins": audit_log,
        }, f, indent=2)

    if valid_count > 0:
        unreal.log(f"[TOOLBELT] Loaded {valid_count} custom plugins. Audit log: {audit_path}")


def launch_qt(**kwargs) -> None:
    """
    Open the PySide6 tabbed dashboard (recommended).
    Dark-themed floating window — no Blueprint setup required.
    Falls back gracefully if PySide6 is not installed.
    """
    from .dashboard_pyside6 import launch_dashboard
    launch_dashboard()


def launch() -> None:
    """
    Primary entry-point called by launcher.py.
    Registers all tools, then tries to open the Qt dashboard.
    Falls back to the EUW Blueprint widget, then to text-mode tool list.
    """
    register_all_tools()
    launch_qt()


def run(tool_id: str, **kwargs) -> Any:
    """Execute a registered tool by name. Returns the tool's return value."""
    return registry.execute(tool_id, **kwargs)


# ── Blueprint / EUW fallback ──────────────────────────────────────────────────

_WIDGET_BP_PATH = "/Game/UEFN_Toolbelt/Blueprints/WBP_ToolbeltDashboard.WBP_ToolbeltDashboard_C"


def _try_open_widget() -> None:
    """Try to open the EUW Blueprint dashboard as a fallback."""
    import unreal
    try:
        widget_class = unreal.load_class(None, _WIDGET_BP_PATH)
        if widget_class:
            euw = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem)
            euw.spawn_and_register_tab(widget_class.get_default_object())
            core.log_info("[TOOLBELT] Blueprint dashboard opened.")
        else:
            _print_tool_list()
    except Exception:
        _print_tool_list()


@register_tool(
    name="toolbelt_smoke_test",
    category="Utilities",
    description="Run the full 6-layer smoke test and print results to the Output Log.",
    tags=["smoke", "test", "health", "debug"],
)
def smoke_test(**kwargs) -> bool:
    """
    Run the full Toolbelt smoke test (6 layers: Python env, UEFN API,
    Toolbelt core, MCP bridge, PySide6 dashboard, Verse Book spec).
    Results printed to Output Log and saved to Saved/UEFN_Toolbelt/smoke_test_results.txt.
    Returns True if all checks pass.
    """
    import sys, os
    _CONTENT_PYTHON = os.path.join(__file__, "..", "..", "..")
    test_path = os.path.normpath(os.path.join(_CONTENT_PYTHON, "..", "tests", "smoke_test.py"))
    if test_path not in sys.path:
        sys.path.insert(0, os.path.dirname(test_path))
    import importlib.util
    spec = importlib.util.spec_from_file_location("smoke_test", test_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_smoke_test()


def _print_tool_list() -> None:
    """Fallback: print registered tools to the Output Log."""
    import unreal
    lines = ["", "=" * 60, "  UEFN TOOLBELT — Available Tools", "=" * 60]
    for info in registry.list_tools():
        lines.append(f"  • {info['name']:36s}  {info['description']}")
    lines += [
        "=" * 60,
        "  Usage:  import UEFN_Toolbelt as tb; tb.run('tool_name')",
        "  Qt UI:  import UEFN_Toolbelt as tb; tb.launch_qt()",
        "=" * 60,
        "",
    ]
    unreal.log("\n".join(lines))
    

def reload() -> None:
    """Reload all Toolbelt modules and the registry."""
    import importlib
    import unreal
    from . import registry
    from . import core
    from . import tools
    import os
    
    # 1. Reload core and registry
    importlib.reload(core)
    importlib.reload(registry)
    
    # 2. Reset the registry singleton
    reg = registry.get_registry()
    reg._tools.clear()
    
    # 3. Reload all tool modules in the tools package
    tools_pkg_path = os.path.dirname(tools.__file__)
    for f in os.listdir(tools_pkg_path):
        if f.endswith(".py") and f != "__init__.py":
            mod_name = f[:-3]
            try:
                submod = getattr(tools, mod_name, None)
                if submod:
                    importlib.reload(submod)
            except Exception as e:
                unreal.log_warning(f"[TOOLBELT] Reload failed for {mod_name}: {e}")
                
    # 4. Finally, reload the tools/__init__.py to re-run all registrations
    importlib.reload(tools)
    unreal.log(f"[TOOLBELT] ↻ All modules reloaded and registry rebuilt. (v{__version__})")
