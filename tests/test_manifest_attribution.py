"""
The manifest must see attributes reached through a local variable.

UEFN 42.00 removed MaterialInstanceConstantFactoryNew.initial_parent and took
all ten Materials tools down with it. The engine-upgrade tripwire in
smoke_test._probe_api_dependencies never flagged it, because the manifest never
listed the attribute, because the generator only recorded `unreal.X.Y` chains
and the code read:

    factory = unreal.MaterialInstanceConstantFactoryNew()
    factory.initial_parent = parent

The receiver was a local, so the attribute was invisible. The tripwire was
structurally blind to the exact class of break it exists to catch.

Closing that gap added 50 previously untracked attributes across the codebase.
These tests pin the behaviour and, just as importantly, pin what must NOT be
attributed — a manifest containing fictional attributes would report phantom
engine breaks and get ignored, which is how a health check dies.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _visitor():
    spec = importlib.util.spec_from_file_location(
        "_genapi", REPO / "scripts" / "gen_api_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._UnrealVisitor


def _scan(src: str) -> dict[str, list[str]]:
    v = _visitor()()
    v.visit(ast.parse(src))
    return {k: sorted(a) for k, a in v.symbols.items()}


def test_attribute_via_local_is_attributed_to_its_class():
    """The regression that motivated all of this."""
    found = _scan(
        "import unreal\n"
        "def make():\n"
        "    factory = unreal.MaterialInstanceConstantFactoryNew()\n"
        "    factory.initial_parent = None\n"
    )
    assert found["MaterialInstanceConstantFactoryNew"] == ["initial_parent"]


def test_direct_chain_still_works():
    found = _scan("import unreal\nunreal.EditorAssetLibrary.load_asset('/X')\n")
    assert "load_asset" in found["EditorAssetLibrary"]


def test_snake_case_callee_is_not_treated_as_a_class():
    """unreal.load_asset() returns an object whose class is not knowable here.
    Guessing would put fictional attributes in the manifest."""
    found = _scan(
        "import unreal\n"
        "def f():\n"
        "    obj = unreal.load_asset('/X')\n"
        "    obj.some_method()\n"
    )
    assert found.get("load_asset", []) == []
    assert not any("some_method" in a for a in found.values())


def test_rebinding_a_name_stops_attribution():
    """Once the variable holds something else, its attributes are not ours."""
    found = _scan(
        "import unreal\n"
        "def f():\n"
        "    x = unreal.ARFilter()\n"
        "    x.class_names = []\n"
        "    x = 5\n"
        "    x.bogus\n"
    )
    assert found["ARFilter"] == ["class_names"]
    assert not any("bogus" in a for a in found.values())


def test_scopes_do_not_cross_attribute():
    """A name reused for a different type elsewhere must not contaminate."""
    found = _scan(
        "import unreal\n"
        "def a():\n"
        "    task = unreal.AssetImportTask()\n"
        "    task.filename = 'x'\n"
        "def b():\n"
        "    task = 'not a task'\n"
        "    task.upper()\n"
    )
    assert found["AssetImportTask"] == ["filename"]
    assert not any("upper" in a for a in found.values())


def test_untracked_local_contributes_nothing():
    """Locals from ordinary calls are ignored entirely."""
    found = _scan(
        "import unreal\n"
        "def f():\n"
        "    mi = create_material_instance('a', 'b', 'c')\n"
        "    mi.anything\n"
    )
    assert not any("anything" in a for a in found.values())
