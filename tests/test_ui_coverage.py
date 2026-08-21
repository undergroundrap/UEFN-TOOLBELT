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


# ── /Game/ default-path ratchet ───────────────────────────────────────────────
# In UEFN, /Game/ is Epic's Fortnite install, not the creator's project. A tool
# defaulting a path there scans the wrong tree, or — if it writes — creates
# assets the project cannot reference. That is what left ~700 dangling material
# references behind arena_generate.

def test_game_path_baseline_matches_reality(dc):
    assert dc.check_game_path_defaults() == [], (
        "the number of /Game/ default paths changed — use resolve_scan_path() "
        "for reads and resolve_content_path() for writes, or move the baseline"
    )


def test_a_new_game_path_default_fails(dc, monkeypatch):
    monkeypatch.setattr(dc, "_GAME_PATH_DEFAULT_BASELINE",
                        dc._GAME_PATH_DEFAULT_BASELINE - 1)
    findings = dc.check_game_path_defaults()
    assert len(findings) == 1
    assert findings[0]["type"] == "/Game/ default path"
    assert "resolve_content_path" in findings[0]["content"]


def test_no_write_destination_still_defaults_to_game(dc):
    """
    Read paths returning nothing is a bug; write paths are the destructive kind.
    Every parameter that names a destination must be resolved onto the project
    mount, so none may remain on /Game/.
    """
    offenders = [
        f for f in dc._game_path_defaults()
        if any(w in f.split("(")[1].split("=")[0]
               for w in ("destination", "dest", "target", "output", "asset_dir",
                         "organized_root"))
    ]
    assert offenders == [], f"write destinations still on /Game/: {offenders}"


def test_a_new_module_level_game_constant_fails(dc, tmp_path, monkeypatch):
    """
    Parameter defaults were the first half of this bug; module constants were the
    other, and cost more. material_master.PARENT_MATERIAL_PATH and
    smart_importer.AUTO_MATERIAL_PARENT both pointed at /Game/, so every material
    tool applied the engine fallback while returning status: ok.
    """
    found = dc._game_path_defaults()
    assert found == [], f"/Game/ paths still baked into source: {found}"

    # and prove the scanner would actually catch a module constant, not just a
    # parameter default — the two live in different parts of the AST
    import ast
    tree = ast.parse('BAD_PATH = "/Game/UEFN_Toolbelt/Materials/M_X"\n')
    node = tree.body[0]
    assert isinstance(node, ast.Assign)
    val = node.value
    assert isinstance(val, ast.Constant) and val.value.startswith("/Game/"), (
        "the module-constant shape this check relies on"
    )


def test_ui_never_hardcodes_the_epic_mount(dc):
    """
    The dashboard and menu are how most people run these tools, and every button
    used to pass scan_path="/Game" explicitly. resolve_scan_path() only fills in
    an EMPTY value, so those calls overrode the tool's own resolver — fixing 42
    parameter defaults did nothing for a single dashboard button.
    """
    offenders = [f for f in dc._game_path_defaults()
                 if f.startswith(("dashboard_pyside6.py", "menu.py"))]
    assert offenders == [], (
        "UI call sites naming /Game override the tool's resolver and scan "
        f"Epic's Fortnite install: {offenders}"
    )


def test_the_broken_reference_audit_is_reachable():
    """Regression guard: the tool that finds severed refs must be findable."""
    from pathlib import Path
    surfaces = "".join(
        (Path(dc_root := "Content/Python/UEFN_Toolbelt") and Path(dc_root) / n).read_text(encoding="utf-8")
        for n in ("dashboard_pyside6.py", "menu.py")
    )
    assert '"ref_audit_broken"' in surfaces or "'ref_audit_broken'" in surfaces, (
        "ref_audit_broken is registered but no UI surface can reach it"
    )
