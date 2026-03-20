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
