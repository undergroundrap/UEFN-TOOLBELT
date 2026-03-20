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
"""

from typing import Any

from .registry import ToolRegistry, get_registry, register_tool
from . import core

# Singleton registry shared across all imports
registry: ToolRegistry = get_registry()


def register_all_tools() -> None:
    """Import every tool module so their @register_tool decorators fire."""
    from . import tools as _tools  # noqa: F401 — triggers all sub-imports
    from . import dashboard_pyside6 as _dash  # noqa: F401 — registers launch_qt tool
    import unreal
    unreal.log(f"[TOOLBELT] {len(registry)} tools registered across {len(registry.categories())} categories.")


def load_custom_plugins() -> None:
    """Load user-provided tools from Saved/UEFN_Toolbelt/Custom_Plugins."""
    import os, sys, glob, importlib, ast, unreal
    custom_plugins_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "Custom_Plugins")
    if not os.path.exists(custom_plugins_dir):
        return
        
    if custom_plugins_dir not in sys.path:
        sys.path.insert(0, custom_plugins_dir)

    # Dangerous modules that third-party plugins should never need
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

    valid_count = 0
    for p in glob.glob(os.path.join(custom_plugins_dir, "*.py")):
        module_name = os.path.splitext(os.path.basename(p))[0]
        
        # Pre-screen: AST security scan before execution
        violations = _scan_plugin(p)
        if violations:
            unreal.log_error(f"[SECURITY] Plugin '{module_name}.py' blocked — dangerous imports detected:")
            for v in violations:
                unreal.log_error(f"  • {v}")
            continue
        
        try:
            importlib.import_module(module_name)
            valid_count += 1
        except Exception as e:
            unreal.log_error(f"[TOOLBELT] Failed to load plugin {module_name}.py: {e}")
            
    if valid_count > 0:
        unreal.log(f"[TOOLBELT] Loaded {valid_count} custom plugins.")


def launch_qt() -> None:
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


def run(tool_name: str, **kwargs) -> Any:
    """Execute a registered tool by name. Returns the tool's return value."""
    return registry.execute(tool_name, **kwargs)


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
