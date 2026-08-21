"""
Silent-startup-failure detection.
==============================================================================
On UEFN 42.00, enabling Project Settings → Beta Access → "UEFN MCP Toolsets"
stops the project's init_unreal.py from running. Epic's Toolsets plugins
force-enable Python before the project's script paths are registered, so only
their own start-up scripts are scanned. Confirmed by diffing editor logs across
boots: with the flag off the project script runs; with it on it never appears.

Nothing raises. Toolbelt simply never starts — tool count 1 instead of 361, and
every tb.run() answers "Unknown tool". That reads as a Toolbelt bug and is not
one, so the smoke test has to be able to name it.
"""

from __future__ import annotations

import importlib

import pytest

import UEFN_Toolbelt as tb

smoke_test = importlib.import_module("UEFN_Toolbelt.smoke_test")


@pytest.fixture(autouse=True)
def _clear():
    smoke_test._results.clear()
    yield
    smoke_test._results.clear()
    tb._STARTUP_RAN = False


def test_startup_flag_is_false_until_register_runs(monkeypatch):
    monkeypatch.setattr(tb, "_STARTUP_RAN", False)
    assert tb.startup_ran() is False


def test_register_sets_the_startup_flag(monkeypatch):
    """
    register() is what init_unreal.py calls. register_all_tools() is NOT — the
    smoke test calls that itself, so keying off it would always look healthy.
    """
    monkeypatch.setattr(tb, "_STARTUP_RAN", False)
    monkeypatch.setattr(tb, "register_all_tools", lambda: None)
    monkeypatch.setattr(tb, "load_custom_plugins", lambda: None)
    monkeypatch.setattr(tb, "_schedule_menu", lambda: None)

    tb.register()

    assert tb.startup_ran() is True


def test_register_all_tools_alone_does_not_set_the_flag(monkeypatch):
    """The distinction the whole check rests on."""
    monkeypatch.setattr(tb, "_STARTUP_RAN", False)
    tb.register_all_tools()
    assert tb.startup_ran() is False


def test_smoke_test_reports_a_missing_auto_start(monkeypatch):
    monkeypatch.setattr(tb, "_STARTUP_RAN", False)
    emitted: list[str] = []
    monkeypatch.setattr(smoke_test, "_out", lambda msg, *a, **k: emitted.append(msg))

    smoke_test._layer_toolbelt()

    result = [r for r in smoke_test._results
              if r["name"] == "init_unreal.py auto-start"]
    assert result and result[0]["passed"] is False
    assert any("UEFN MCP Toolsets" in m for m in emitted), \
        "the report must name the setting responsible"
    assert any("tb.register()" in m for m in emitted), \
        "the report must give the workaround"


def test_smoke_test_passes_when_auto_start_worked(monkeypatch):
    monkeypatch.setattr(tb, "_STARTUP_RAN", True)
    smoke_test._layer_toolbelt()

    result = [r for r in smoke_test._results
              if r["name"] == "init_unreal.py auto-start"]
    assert result and result[0]["passed"] is True


# ── tb.run() must name the unregistered state, not blame the tool name ────────
#
# Added 2026-08-21 after a live session on Device_API_Mapping where every call
# answered:
#     {'reason': 'unknown_tool', 'tool': 'ref_audit_broken', 'did_you_mean': []}
# The tool existed, was deployed, and its bytecode was current. Quirk #36 had
# simply stopped init_unreal.py from running, so the registry held one tool.
# Diagnosing it took a filesystem audit; the registry had the answer all along.

def test_is_fully_registered_true_when_tools_package_imported():
    """Guards against the predicate being vacuously false in the real case."""
    import UEFN_Toolbelt.tools  # noqa: F401 — the condition under test
    from UEFN_Toolbelt.registry import get_registry
    assert get_registry().is_fully_registered() is True


def test_unregistered_registry_reports_not_registered(fresh_registry, monkeypatch):
    """With UEFN_Toolbelt.tools absent, a miss is a startup failure, not a typo."""
    import sys as _sys

    # NB: `from UEFN_Toolbelt import registry` yields the ToolRegistry singleton,
    # not the module — the package rebinds the name. Patch sys.modules directly.
    monkeypatch.delitem(_sys.modules, "UEFN_Toolbelt.tools", raising=False)

    res = fresh_registry.execute("ref_audit_broken")
    assert res["status"] == "error"
    assert res["reason"] == "not_registered", res
    assert res["quirk"] == 36
    assert "tb.register()" in res["fix"]
    # The message must not send the user looking for a misspelling.
    assert "did_you_mean" not in res


def test_registered_registry_still_reports_unknown_tool(fresh_registry):
    """The new branch must not swallow genuine typos once startup has run."""
    import UEFN_Toolbelt.tools  # noqa: F401
    res = fresh_registry.execute("ref_audit_brokenn")
    assert res["reason"] == "unknown_tool", res
