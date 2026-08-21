"""
Engine-API preflight guards.
==============================================================================
UEFN 42.00 (UE 6.0) removed GeometryScript, EditorBlueprintLibrary,
InputActionFactory and EditorPerformanceSettings. Twelve tools depend on them.

Before these guards those tools surfaced a raw AttributeError from somewhere
inside their own loop, which reads to a user like "I did something wrong"
rather than "this engine build cannot do this". These tests pin the refusal
contract so the message stays specific and machine-readable for MCP clients.
"""

from __future__ import annotations

import importlib
import types

import pytest

core = importlib.import_module("UEFN_Toolbelt.core")
geometry_tools = importlib.import_module("UEFN_Toolbelt.tools.geometry_tools")


@pytest.fixture
def engine(monkeypatch):
    """Swap core's `unreal` for a namespace with an exactly-known API surface."""
    def _build(**attrs):
        fake = types.SimpleNamespace(
            log_warning=lambda *a, **k: None,
            log=lambda *a, **k: None,
            log_error=lambda *a, **k: None,
            **attrs,
        )
        monkeypatch.setattr(core, "unreal", fake)
        return fake
    return _build


# ── Detection ─────────────────────────────────────────────────────────────────

def test_detects_a_missing_class(engine):
    engine()
    assert core.missing_unreal_apis("GeometryScriptLibrary_MeshRepairFunctions") == [
        "GeometryScriptLibrary_MeshRepairFunctions"
    ]


def test_detects_a_missing_method_on_a_present_class(engine):
    engine(EditorAssetLibrary=types.SimpleNamespace(does_asset_exist=lambda p: True))
    assert core.missing_unreal_apis("EditorAssetLibrary.find_package_referencers") == [
        "EditorAssetLibrary.find_package_referencers"
    ]
    assert core.missing_unreal_apis("EditorAssetLibrary.does_asset_exist") == []


def test_reports_nothing_when_the_api_is_intact(engine):
    engine(InputActionFactory=object, EditorPerformanceSettings=object)
    assert core.missing_unreal_apis("InputActionFactory", "EditorPerformanceSettings") == []


def test_only_the_absent_names_are_reported(engine):
    engine(InputActionFactory=object)
    assert core.missing_unreal_apis(
        "InputActionFactory", "EditorPerformanceSettings"
    ) == ["EditorPerformanceSettings"]


# ── Refusal contract ──────────────────────────────────────────────────────────

def test_refusal_payload_is_machine_readable(engine):
    engine()
    result = core.api_unavailable("geometry_weld_edges", ["GeometryScriptLibrary_X"])
    assert result["status"] == "error"
    assert result["reason"] == "engine_api_unavailable"
    assert result["missing_apis"] == ["GeometryScriptLibrary_X"]
    # The message has to name the tool and the API, or it is not actionable.
    assert "geometry_weld_edges" in result["message"]
    assert "GeometryScriptLibrary_X" in result["message"]


# ── Wiring: a real guarded tool refuses instead of raising ────────────────────

def test_guarded_tool_refuses_before_touching_the_selection(monkeypatch):
    """
    The guard must run before any editor work. If it did not, the tool would
    partially execute and then die on AttributeError mid-loop.
    """
    monkeypatch.setattr(
        geometry_tools, "missing_unreal_apis",
        lambda *names: ["GeometryScriptLibrary_StaticMeshFunctions"],
    )

    def _should_never_run(*a, **k):
        raise AssertionError("tool did work despite a missing engine API")

    monkeypatch.setattr(geometry_tools, "_load_static_mesh", _should_never_run)

    result = geometry_tools.run_geometry_weld_edges()
    assert result["status"] == "error"
    assert result["reason"] == "engine_api_unavailable"


def test_guarded_tool_proceeds_when_the_api_is_present(monkeypatch):
    """The guard must not become an unconditional refusal."""
    monkeypatch.setattr(geometry_tools, "missing_unreal_apis", lambda *names: [])

    try:
        result = geometry_tools.run_geometry_weld_edges()
    except Exception:
        # Downstream editor work is out of scope here; reaching it is the point.
        return

    assert not (isinstance(result, dict)
                and result.get("reason") == "engine_api_unavailable"),         "guard refused even though every required API was present"


# ── UE 6.0 removed factory attributes ────────────────────────────────────────
#
# UEFN 42.00 raised, on every Materials tool:
#     AttributeError: 'MaterialInstanceConstantFactoryNew' object has no
#     attribute 'initial_parent'
# Ten tools down at once, and only in the editor — nothing here could import
# `unreal` to find out. A static check is the only guard available.

def test_no_code_sets_initial_parent_on_a_factory():
    """Assign the parent with MaterialEditingLibrary.set_material_instance_parent.

    Parsed rather than grepped: the fix's own docstring quotes the AttributeError
    verbatim, and a text search flags that as a violation. The check has to look
    at what the code DOES.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "Content" / "Python" / "UEFN_Toolbelt"
    offenders: list[str] = []

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # factory.initial_parent = x
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and t.attr == "initial_parent":
                        offenders.append(f"{path.relative_to(root)}:{node.lineno}")
            # factory.set_editor_property("initial_parent", x)
            elif isinstance(node, ast.Call):
                fn = node.func
                if (isinstance(fn, ast.Attribute) and fn.attr == "set_editor_property"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == "initial_parent"):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")

    assert not offenders, (
        "initial_parent was removed from the factory in UE 6.0 and raises "
        f"AttributeError in UEFN 42.00: {offenders}"
    )
