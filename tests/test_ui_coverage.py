"""
UI reachability ratchet.
==============================================================================
The dashboard builds its tabs from hand-written functions, not from the tool
registry, so calling @register_tool does NOT make a tool clickable. Three Epic
MCP tools shipped registered-but-unreachable before this check existed — the
version strings were all current, drift_check passed, and the tools were still
invisible to every user.

44% of tools are UI-invisible today and much of that is deliberate (MCP/CLI-only
utilities), so this cannot be a "every tool needs a button" check — that would be
permanently red, and a permanently red check is one people stop reading. It is a
ratchet instead: the number may fall, never rise.
"""

from __future__ import annotations

import importlib.util

import pytest

SPEC = importlib.util.spec_from_file_location("drift_check", "scripts/drift_check.py")


@pytest.fixture
def dc():
    mod = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(mod)
    return mod


def test_baseline_matches_reality(dc):
    """The committed baseline must equal the real count, or the ratchet is noise."""
    assert dc.check_ui_coverage() == [], (
        "UI coverage changed — either surface the new tools or move "
        "_UI_INVISIBLE_BASELINE deliberately"
    )


def test_a_newly_unreachable_tool_fails(dc, monkeypatch):
    monkeypatch.setattr(dc, "_UI_INVISIBLE_BASELINE", dc._UI_INVISIBLE_BASELINE - 1)
    findings = dc.check_ui_coverage()
    assert len(findings) == 1
    assert findings[0]["type"] == "ui reachability"
    # The report has to name the tools, or nobody can act on it.
    assert "Unreachable:" in findings[0]["content"]


def test_improved_coverage_asks_for_the_baseline_to_be_lowered(dc, monkeypatch):
    """Without this the ratchet only ever loosens and never tightens."""
    monkeypatch.setattr(dc, "_UI_INVISIBLE_BASELINE", dc._UI_INVISIBLE_BASELINE + 1)
    findings = dc.check_ui_coverage()
    assert len(findings) == 1
    assert "lower _UI_INVISIBLE_BASELINE" in findings[0]["content"]


def test_the_epic_mcp_tools_are_reachable(dc):
    """Regression guard for the specific bug that motivated this check."""
    tools = dc._registered_tools()
    for name in ("epic_mcp_status", "epic_mcp_register", "epic_mcp_unregister"):
        assert name in tools, f"{name} is not registered"

    from pathlib import Path
    surfaces = "".join(
        (Path(dc.ROOT) / rel).read_text(encoding="utf-8") for rel in dc._UI_SURFACES
    )
    for name in ("epic_mcp_status", "epic_mcp_register"):
        assert f'"{name}"' in surfaces, f"{name} is registered but unreachable in the UI"


def test_tool_parser_finds_every_registered_tool(dc):
    """If the AST parser silently under-counts, the ratchet reads as an improvement."""
    import UEFN_Toolbelt as tb

    assert len(dc._registered_tools()) == tb.__tool_count__
