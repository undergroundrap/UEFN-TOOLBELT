"""
Contract tests for the ToolRegistry.
==============================================================================
The registry is the platform contract: every one of the 358 tools, the dashboard,
the MCP bridge, and the exported manifest all read through it. A regression here
breaks everything downstream, so it gets the most coverage.
"""

from __future__ import annotations

import pytest


def _tool(**over):
    """Build a well-formed tool function + registration kwargs."""
    def run(**kwargs):
        return {"status": "ok", "echo": kwargs}

    kwargs = {
        "name": "demo_tool",
        "fn": run,
        "category": "Utilities",
        "description": "A demo tool",
    }
    kwargs.update(over)
    return kwargs


# ── Registration ──────────────────────────────────────────────────────────────

def test_register_then_lookup(fresh_registry):
    fresh_registry.register(**_tool())
    assert "demo_tool" in fresh_registry
    assert len(fresh_registry) == 1


def test_len_and_contains_reflect_registrations(fresh_registry):
    assert len(fresh_registry) == 0
    assert "nope" not in fresh_registry
    for i in range(3):
        fresh_registry.register(**_tool(name=f"tool_{i}"))
    assert len(fresh_registry) == 3


def test_categories_are_deduplicated_and_sorted(fresh_registry):
    fresh_registry.register(**_tool(name="a", category="Zebra"))
    fresh_registry.register(**_tool(name="b", category="Alpha"))
    fresh_registry.register(**_tool(name="c", category="Alpha"))
    assert fresh_registry.categories() == ["Alpha", "Zebra"]


# ── Execution + error containment ─────────────────────────────────────────────

def test_execute_passes_kwargs_and_returns_result(fresh_registry):
    fresh_registry.register(**_tool())
    result = fresh_registry.execute("demo_tool", count=5, label="x")
    assert result == {"status": "ok", "echo": {"count": 5, "label": "x"}}


def test_execute_unknown_tool_returns_structured_error(fresh_registry):
    """
    These two tests used to assert `is None`, pinning the bug in place.

    Returning None for both "no such tool" and "the tool raised" is
    indistinguishable from a tool that ran and returned nothing — an MCP client
    cannot tell them apart, and the dashboard rendered it as a green tick
    because its handler treats None as success. A misspelled tool name looked
    like a clean run.
    """
    res = fresh_registry.execute("does_not_exist")
    assert isinstance(res, dict)
    assert res["status"] == "error"
    assert res["reason"] == "unknown_tool"
    assert res["tool"] == "does_not_exist"


def test_unknown_tool_suggests_close_matches(fresh_registry):
    """362 tools makes a typo likely; the caller should be pointed at the fix."""
    fresh_registry.register(**_tool(name="scatter_props"))
    res = fresh_registry.execute("scatter_prop")
    assert "scatter_props" in res["did_you_mean"]


def test_execute_contains_exceptions(fresh_registry):
    """A raising tool must never propagate — it would crash the editor session."""
    def boom(**kwargs):
        raise RuntimeError("tool exploded")

    fresh_registry.register(**_tool(name="boom", fn=boom))
    res = fresh_registry.execute("boom")
    assert res["status"] == "error"                    # contained, not raised
    assert res["reason"] == "exception"
    assert "tool exploded" in res["message"]           # says what actually failed
    assert "boom" in fresh_registry                    # registry still usable
    assert fresh_registry.execute("boom", again=True)["status"] == "error"


# ── list_tools / manifest shape ───────────────────────────────────────────────

def test_list_tools_filters_by_category(fresh_registry):
    fresh_registry.register(**_tool(name="a", category="Alpha"))
    fresh_registry.register(**_tool(name="b", category="Beta"))
    names = {t["name"] for t in fresh_registry.list_tools(category="Alpha")}
    assert names == {"a"}
    assert len(fresh_registry.list_tools()) == 2


def test_list_tools_preserves_tags_as_a_list(fresh_registry):
    """
    Regression guard: list_tools() was annotated `list[dict[str, str]]` while
    actually returning a list for `tags`. MCP clients and the Plugin Hub read
    this dict, so the value must stay a real list.
    """
    fresh_registry.register(**_tool(tags=["mesh", "bulk"]))
    entry = fresh_registry.list_tools()[0]
    assert entry["tags"] == ["mesh", "bulk"]
    assert isinstance(entry["tags"], list)


def test_search_matches_name_and_description(fresh_registry):
    fresh_registry.register(**_tool(name="scatter_props", description="Poisson scatter"))
    fresh_registry.register(**_tool(name="light_place", description="Spawn a light"))
    assert {t["name"] for t in fresh_registry.search("scatter")} == {"scatter_props"}
    assert {t["name"] for t in fresh_registry.search("light")} == {"light_place"}


def test_to_manifest_includes_parameter_schema(fresh_registry):
    """The manifest is what AI agents read to call tools — params must be described."""
    def run(folder_path: str = "/Game", num_lods: int = 4, **kwargs):
        return {"status": "ok"}

    fresh_registry.register(**_tool(name="lod_demo", fn=run))
    manifest = fresh_registry.to_manifest()
    assert "lod_demo" in manifest
    params = manifest["lod_demo"]["parameters"]
    assert "folder_path" in params
    assert "num_lods" in params
    assert params["num_lods"]["default"] == 4


# ── Validation rules ──────────────────────────────────────────────────────────

def test_validate_accepts_a_well_formed_tool(fresh_registry):
    fresh_registry.register(**_tool())
    assert fresh_registry.validate() == []


@pytest.mark.parametrize(
    "override, expected_fragment",
    [
        ({"description": ""}, "Missing description"),
        ({"category": ""}, "Missing category"),
        ({"name": "Bad_Name"}, "snake_case"),
    ],
)
def test_validate_flags_malformed_tools(fresh_registry, override, expected_fragment):
    fresh_registry.register(**_tool(**override))
    errors = fresh_registry.validate()
    assert any(expected_fragment in e for e in errors), errors


def test_validate_requires_kwargs_in_signature(fresh_registry):
    """Tools are dispatched with **kwargs; a fixed signature breaks MCP calls."""
    def no_kwargs(a, b):
        return a + b

    fresh_registry.register(**_tool(name="rigid", fn=no_kwargs))
    errors = fresh_registry.validate()
    assert any("**kwargs" in e for e in errors), errors


def test_validate_reports_unknown_tool_name(fresh_registry):
    errors = fresh_registry.validate(tool_name="ghost")
    assert any("not found" in e for e in errors), errors
