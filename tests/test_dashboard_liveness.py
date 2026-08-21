"""
Dashboard status widgets must show live state, not startup state.
==============================================================================
The Quick Actions "Setup Status" block reported `MCP bridge: Not running` while
the MCP tab simultaneously showed `RUNNING — port 8765 — AI client connected`.
Both read the same `mcp_bridge._bound_port`; the difference was staleness. Quick
Actions rendered its rows once when the tab was built and never again, so a
listener started afterwards never showed up.

These are AST tests. PySide6 is installed into UE's embedded Python, not the dev
environment, so the dashboard cannot be imported here — this pins the structure
that makes liveness possible, not the rendering itself. The rendering still needs
a live editor check per CLAUDE.md.
"""

from __future__ import annotations

import ast
import io

import pytest

SRC_PATH = "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py"


@pytest.fixture(scope="module")
def src() -> str:
    return open(SRC_PATH, encoding="utf-8").read()


@pytest.fixture(scope="module")
def tree(src):
    return ast.parse(src)


def _fn(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def test_status_computation_is_separate_from_rendering(src, tree):
    """
    If computing the checks and building the widgets are the same function, the
    rows can only ever reflect the moment the tab was built.
    """
    fn = _fn(tree, "_setup_status_checks")
    body = ast.get_source_segment(src, fn)
    assert any(isinstance(s, ast.Return) for s in ast.walk(fn)), \
        "_setup_status_checks must return the rows"
    assert "addWidget" not in body, \
        "_setup_status_checks must not build widgets — that is what froze it"


def test_setup_status_registers_a_refresh_callback(src):
    fn_src = ast.get_source_segment(src, _fn(ast.parse(src), "_build_setup_status"))
    assert 'setProperty("refresh_fn"' in fn_src, \
        "Setup Status must register refresh_fn or it will never update"


def test_navigation_sweeps_for_refresh_callbacks_generically(src, tree):
    """
    A per-tab special case is how Quick Actions was missed — the MCP tab had one
    and nothing else did. Navigation must sweep, so a new live widget is picked
    up without touching this function.
    """
    fn_src = ast.get_source_segment(src, _fn(tree, "_select_category"))
    assert 'property("refresh_fn")' in fn_src, "navigation must sweep for refresh_fn"
    assert "_mcp_refresh_fn" not in fn_src, \
        "the MCP special case should be gone — one mechanism, not two"


def test_no_stale_mcp_special_case_remains(src):
    assert "mcp_refresh_fn" not in src, \
        "the old single-tab refresh hook is superseded by the generic sweep"


def test_live_widgets_register_themselves(src):
    """Every widget showing state that can change while open must opt in."""
    assert src.count('setProperty("refresh_fn"') >= 3, (
        "expected Setup Status, the MCP listener indicator and the Epic MCP "
        "indicator to all register as live"
    )
