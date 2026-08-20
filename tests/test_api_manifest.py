"""
Tests for the UEFN API dependency manifest and its runtime probe.
==============================================================================
This is the engine-upgrade tripwire. UEFN force-updates in lockstep with the
live Fortnite build, so every user gets a new engine whether they schedule it or
not. These tests make sure the manifest stays truthful and that the probe
actually reports a removed API instead of passing silently.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import types

import pytest

# NOTE: `from UEFN_Toolbelt import smoke_test` returns the tb.smoke_test() *function* —
# the package root re-exports a callable that shadows this submodule's name.
# import_module resolves the real module.
smoke_test = importlib.import_module("UEFN_Toolbelt.smoke_test")


@pytest.fixture
def manifest(repo_root):
    path = repo_root / "Content" / "Python" / "UEFN_Toolbelt" / "api_dependencies.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ── Manifest freshness + shape ────────────────────────────────────────────────

def test_manifest_is_up_to_date(repo_root):
    """Regenerating must be a no-op — otherwise the probe checks a stale API set."""
    proc = subprocess.run(
        [sys.executable, "scripts/gen_api_manifest.py", "--check"],
        cwd=repo_root, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_manifest_ships_inside_the_package(repo_root):
    """
    install.py copies only Content/Python/UEFN_Toolbelt. A manifest anywhere else
    (e.g. docs/) would never reach an end user's editor, so the probe would be
    dead code for exactly the people who need it.
    """
    assert (repo_root / "Content" / "Python" / "UEFN_Toolbelt" / "api_dependencies.json").exists()


def test_manifest_covers_the_core_apis(manifest):
    symbols = manifest["symbols"]
    for expected in ["EditorAssetLibrary", "EditorActorSubsystem", "Vector",
                     "Rotator", "Paths", "ScopedEditorTransaction"]:
        assert expected in symbols, f"{expected} missing from manifest"
    assert manifest["symbol_count"] > 100


def test_manifest_records_method_level_detail(manifest):
    """Symbol presence is not enough — renamed methods must be caught too."""
    assert "does_asset_exist" in manifest["symbols"]["EditorAssetLibrary"]["attributes"]


def test_manifest_attributes_exclude_docstring_noise(manifest):
    """AST parsing must not pick up `unreal.pyi` / `unreal.py` from prose."""
    assert "pyi" not in manifest["symbols"]
    assert "py" not in manifest["symbols"]


def test_every_symbol_records_a_consumer(manifest):
    """`used_by` is what turns a failure into an actionable fix."""
    for name, info in manifest["symbols"].items():
        assert info["used_by"], f"{name} has no recorded consumer"


# ── The probe itself ──────────────────────────────────────────────────────────

def _fake_unreal_with(symbols: dict) -> types.ModuleType:
    mod = types.ModuleType("unreal")
    for name, attrs in symbols.items():
        holder = type(name, (), dict.fromkeys(attrs, staticmethod(lambda *a, **k: None)))
        setattr(mod, name, holder)
    return mod


@pytest.fixture(autouse=True)
def _clear_results():
    smoke_test._results.clear()
    yield
    smoke_test._results.clear()


def _find(name):
    return [r for r in smoke_test._results if r["name"] == name]


def test_probe_passes_when_every_symbol_is_present(manifest):
    fake = _fake_unreal_with(
        {n: i["attributes"] for n, i in manifest["symbols"].items()}
    )
    smoke_test._probe_api_dependencies(fake)

    assert _find("All required unreal.* symbols present")[0]["passed"] is True
    assert _find("All required unreal.* methods present")[0]["passed"] is True


def test_probe_detects_a_removed_symbol(manifest):
    """Simulates a UEFN release dropping a class the Toolbelt depends on."""
    symbols = {n: i["attributes"] for n, i in manifest["symbols"].items()}
    symbols.pop("EditorAssetLibrary")

    smoke_test._probe_api_dependencies(_fake_unreal_with(symbols))

    result = _find("All required unreal.* symbols present")[0]
    assert result["passed"] is False
    assert "1 MISSING" in result["detail"]


def test_probe_detects_a_renamed_method(manifest):
    """Simulates a method rename — the class survives, the call site breaks."""
    symbols = {n: list(i["attributes"]) for n, i in manifest["symbols"].items()}
    symbols["EditorAssetLibrary"].remove("does_asset_exist")

    smoke_test._probe_api_dependencies(_fake_unreal_with(symbols))

    assert _find("All required unreal.* symbols present")[0]["passed"] is True
    result = _find("All required unreal.* methods present")[0]
    assert result["passed"] is False
    assert "1 MISSING" in result["detail"]


def test_probe_reports_missing_manifest_without_raising(monkeypatch, tmp_path):
    """A broken install must degrade to a failed check, not crash the editor."""
    monkeypatch.setattr(smoke_test, "__file__", str(tmp_path / "smoke_test.py"))
    smoke_test._probe_api_dependencies(types.ModuleType("unreal"))

    result = _find("api_dependencies.json")[0]
    assert result["passed"] is False
    assert "gen_api_manifest" in result["detail"]


# ── Per-attribute attribution ─────────────────────────────────────────────────
# Regression guard. The first version of this manifest recorded `used_by` only at
# the symbol level, and the probe printed that list for a missing *method*. On
# UEFN 42.00 that reported `EditorLevelLibrary.snap_objects_to_floor` as breaking
# 29 modules when it breaks exactly one — turning a two-file fix into a apparent
# platform-wide outage during triage.

def test_attributes_are_a_mapping_with_their_own_used_by(manifest):
    for name, info in manifest["symbols"].items():
        attrs = info["attributes"]
        assert isinstance(attrs, dict), f"{name}.attributes must be a mapping"
        for attr, meta in attrs.items():
            assert meta.get("used_by"), f"{name}.{attr} has no recorded caller"


def test_attribute_callers_are_a_subset_of_class_callers(manifest):
    """A method cannot be called from a file that never touches its class."""
    for name, info in manifest["symbols"].items():
        class_users = set(info["used_by"])
        for attr, meta in info["attributes"].items():
            extra = set(meta["used_by"]) - class_users
            assert not extra, f"{name}.{attr} claims callers outside the class: {extra}"


def test_attribution_is_actually_narrower_somewhere(manifest):
    """
    Proves the per-attribute lists are real and not just copies of the class list.
    Without this, the bug could silently return by having the generator fill every
    attribute with the symbol's full consumer list again.
    """
    narrower = [
        f"{name}.{attr}"
        for name, info in manifest["symbols"].items()
        for attr, meta in info["attributes"].items()
        if len(meta["used_by"]) < len(info["used_by"])
    ]
    assert narrower, "no attribute is narrower than its class — attribution is not real"


def test_probe_reports_only_the_methods_own_callers(manifest, monkeypatch):
    """End-to-end: the log line names the method's callers, not the class's."""
    symbols = {n: list(i["attributes"]) for n, i in manifest["symbols"].items()}

    # Pick a method whose caller list is strictly narrower than its class's.
    target_sym, target_attr = next(
        (n, a)
        for n, i in manifest["symbols"].items()
        for a, meta in i["attributes"].items()
        if len(meta["used_by"]) < len(i["used_by"])
    )
    expected = manifest["symbols"][target_sym]["attributes"][target_attr]["used_by"]
    class_wide = manifest["symbols"][target_sym]["used_by"]

    symbols[target_sym].remove(target_attr)

    emitted: list[str] = []
    monkeypatch.setattr(smoke_test, "_out", lambda msg, *a, **k: emitted.append(msg))

    smoke_test._probe_api_dependencies(_fake_unreal_with(symbols))

    line = next(m for m in emitted if f"{target_sym}.{target_attr}" in m)
    assert expected[0] in line
    # The whole point: it must not have widened to every consumer of the class.
    assert f"+{len(class_wide) - 4} more" not in line


# ── Optional APIs ─────────────────────────────────────────────────────────────
# A health check that is permanently red for problems the code already handles is
# a check people learn to ignore. Modules declare `__optional_unreal_apis__` for
# names they guard; the probe reports those as handled rather than failing.

def test_guarded_engine_apis_are_marked_optional(manifest):
    """The APIs UEFN 42.00 removed are all guarded, so none may be required."""
    for name in ("GeometryScriptLibrary_StaticMeshFunctions", "EditorBlueprintLibrary",
                 "InputActionFactory", "EditorPerformanceSettings", "PCGSubsystem"):
        assert manifest["symbols"][name]["optional"] is True, f"{name} must be optional"


def test_epic_mcp_symbols_are_optional(manifest):
    """Epic's ToolsetRegistry is Experimental — absent on most users' machines."""
    for name in ("ToolsetDefinition", "ToolsetRegistry"):
        assert manifest["symbols"][name]["optional"] is True


def test_core_apis_are_still_required(manifest):
    """The opt-out must not leak onto APIs nothing guards."""
    for name in ("EditorAssetLibrary", "EditorActorSubsystem", "Vector", "Paths"):
        assert manifest["symbols"][name]["optional"] is False, f"{name} must stay required"


def test_probe_does_not_fail_on_a_missing_optional_symbol(manifest):
    """The whole point: an absent-but-guarded API keeps the check green."""
    symbols = {n: i["attributes"] for n, i in manifest["symbols"].items()}
    symbols.pop("GeometryScriptLibrary_StaticMeshFunctions")

    smoke_test._probe_api_dependencies(_fake_unreal_with(symbols))

    assert _find("All required unreal.* symbols present")[0]["passed"] is True
    handled = _find("Optional unreal.* APIs absent (handled)")
    assert handled and handled[0]["passed"] is True


def test_probe_still_fails_on_a_missing_required_symbol(manifest):
    """Guard against the opt-out swallowing a genuine regression."""
    symbols = {n: i["attributes"] for n, i in manifest["symbols"].items()}
    symbols.pop("EditorAssetLibrary")

    smoke_test._probe_api_dependencies(_fake_unreal_with(symbols))

    assert _find("All required unreal.* symbols present")[0]["passed"] is False
