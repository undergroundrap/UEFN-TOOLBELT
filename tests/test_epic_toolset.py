"""Epic Toolset Registry integration truth and internal meta-tool contracts."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from UEFN_Toolbelt import epic_toolset as et

_SCHEMA_KEYS = {
    "status",
    "toolset_registry_available",
    "reason",
    "toolset",
    "meta_tools",
    "registration_attempt",
    "in_process_registration_record",
    "in_process_registry_confirmation",
    "internal_meta_tools",
    "external_official_mcp",
}
_REGISTRATION_OUTCOMES = {
    "not_attempted",
    "returned_without_exception",
    "raised",
    "adopted_from_current_editor_session",
}
_CONTRACT_OUTCOMES = {"not_tested", "passed", "failed"}
_EXTERNAL_NOT_TESTED = {
    "listable": "not_tested",
    "describable": "not_tested",
    "callable": "not_tested",
}


def _assert_truth_schema(result):
    assert set(result) == _SCHEMA_KEYS
    assert result["toolset"] == "UEFN_Toolbelt"
    assert result["meta_tools"] == list(et.META_TOOLS)
    assert result["registration_attempt"] in _REGISTRATION_OUTCOMES
    assert result["in_process_registration_record"] in {"present", "absent"}
    assert result["in_process_registry_confirmation"] in {"confirmed", "unknown"}
    assert set(result["internal_meta_tools"]) == {"list", "describe", "run"}
    assert set(result["internal_meta_tools"].values()) <= _CONTRACT_OUTCOMES
    assert result["external_official_mcp"] == _EXTERNAL_NOT_TESTED


@pytest.fixture(autouse=True)
def _reset():
    """Reset module and cross-reload state between cases."""
    import unreal

    def clean():
        et._TOOLSET_CLASS = None
        et._REGISTERED = False
        et._REGISTRATION_ATTEMPT = et.REGISTRATION_NOT_ATTEMPTED
        et._IN_PROCESS_CONFIRMATION = et.CONFIRMATION_UNKNOWN
        et._INTERNAL_CONTRACTS.update({
            "list": et.CONTRACT_NOT_TESTED,
            "describe": et.CONTRACT_NOT_TESTED,
            "run": et.CONTRACT_NOT_TESTED,
        })
        setattr(unreal, et._STASH_ATTR, None)

    clean()
    yield
    clean()


class _Toolset:
    """Stand-in for the generated UClass."""

    __module__ = "UEFN_Toolbelt.epic_toolset"
    __name__ = "UEFNToolbeltToolset"


def _registry(*, class_registered=False, register_error=None):
    class Registry:
        registered_calls: list = []
        unregistered_calls: list = []

        @staticmethod
        def is_available():
            return True

        @staticmethod
        def is_toolset_class_registered(cls):
            return class_registered

        @staticmethod
        def register_toolset_class(cls):
            Registry.registered_calls.append(cls)
            if register_error is not None:
                raise register_error

        @staticmethod
        def unregister_toolset_class(cls):
            Registry.unregistered_calls.append(cls)

    return Registry


def _prepare_registration(monkeypatch, registry):
    import unreal

    monkeypatch.setattr(unreal, "ToolsetRegistry", registry)
    monkeypatch.setattr(et, "_build_toolset_class", lambda: _Toolset)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})


def test_absent_registry_is_not_attempted_and_uses_stable_schema():
    result = et.register()

    _assert_truth_schema(result)
    assert result["status"] == "skipped"
    assert result["toolset_registry_available"] is False
    assert result["registration_attempt"] == "not_attempted"
    assert result["in_process_registration_record"] == "absent"


def test_status_is_safe_without_epic_toolset_registry():
    state = et.status()

    _assert_truth_schema(state)
    assert state["status"] == "ok"
    assert state["toolset_registry_available"] is False


def test_class_definition_failure_does_not_claim_a_registration_attempt(monkeypatch):
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})
    monkeypatch.setattr(
        et,
        "_build_toolset_class",
        lambda: (_ for _ in ()).throw(RuntimeError("definition failed")),
    )

    result = et.register()

    _assert_truth_schema(result)
    assert result["status"] == "error"
    assert result["registration_attempt"] == "not_attempted"
    assert "definition failed" in result["reason"]


def test_registration_exception_is_recorded_as_raised(monkeypatch):
    registry = _registry(register_error=RuntimeError("registry rejected"))
    _prepare_registration(monkeypatch, registry)

    result = et.register()

    _assert_truth_schema(result)
    assert result["status"] == "error"
    assert result["registration_attempt"] == "raised"
    assert result["in_process_registry_confirmation"] == "unknown"
    assert result["in_process_registration_record"] == "absent"


@pytest.mark.parametrize("confirmed", (False, True))
def test_returned_registration_records_only_positive_in_process_confirmation(
    monkeypatch, confirmed
):
    registry = _registry(class_registered=confirmed)
    _prepare_registration(monkeypatch, registry)

    result = et.register()

    _assert_truth_schema(result)
    assert result["status"] == "ok"
    assert result["registration_attempt"] == "returned_without_exception"
    assert result["in_process_registration_record"] == "present"
    expected = "confirmed" if confirmed else "unknown"
    assert result["in_process_registry_confirmation"] == expected
    assert registry.registered_calls == [_Toolset]


def test_module_bookkeeping_never_implies_external_availability(monkeypatch):
    import unreal

    registry = _registry(class_registered=False)
    _prepare_registration(monkeypatch, registry)
    monkeypatch.setattr(et, "_REGISTERED", True)
    monkeypatch.setattr(unreal, et._STASH_ATTR, _Toolset, raising=False)

    result = et.register()

    _assert_truth_schema(result)
    assert result["registration_attempt"] == "adopted_from_current_editor_session"
    assert result["in_process_registry_confirmation"] == "unknown"
    assert registry.registered_calls == []


def test_reload_stash_is_adopted_without_external_inference(monkeypatch):
    import unreal

    stale = type(
        "UEFNToolbeltToolset",
        (),
        {"__module__": "UEFN_Toolbelt.epic_toolset"},
    )
    monkeypatch.setattr(unreal, et._STASH_ATTR, stale, raising=False)
    registry = _registry(class_registered=False)
    _prepare_registration(monkeypatch, registry)

    result = et.register()

    _assert_truth_schema(result)
    assert result["registration_attempt"] == "adopted_from_current_editor_session"
    assert result["in_process_registry_confirmation"] == "unknown"
    assert registry.registered_calls == []
    assert getattr(unreal, et._STASH_ATTR) is _Toolset


def test_status_confirms_only_a_positive_live_class_query(monkeypatch):
    import unreal

    monkeypatch.setattr(et, "_TOOLSET_CLASS", _Toolset)
    monkeypatch.setattr(et, "_REGISTERED", True)
    monkeypatch.setattr(unreal, "ToolsetRegistry", _registry(class_registered=True))
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    state = et.status()

    _assert_truth_schema(state)
    assert state["in_process_registry_confirmation"] == "confirmed"


def test_status_keeps_failed_or_false_confirmation_unknown(monkeypatch):
    import unreal

    class BrokenRegistry:
        @staticmethod
        def is_toolset_class_registered(cls):
            raise RuntimeError("query unavailable")

    monkeypatch.setattr(et, "_TOOLSET_CLASS", _Toolset)
    monkeypatch.setattr(et, "_REGISTERED", True)
    monkeypatch.setattr(unreal, "ToolsetRegistry", BrokenRegistry)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    state = et.status()

    _assert_truth_schema(state)
    assert state["in_process_registry_confirmation"] == "unknown"
    monkeypatch.setattr(unreal, "ToolsetRegistry", _registry(class_registered=False))
    assert et.status()["in_process_registry_confirmation"] == "unknown"


def test_unregister_branches_keep_the_same_truth_schema(monkeypatch):
    import unreal

    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})
    absent = et.unregister()
    _assert_truth_schema(absent)
    assert absent["status"] == "skipped"

    registry = _registry(class_registered=True)
    monkeypatch.setattr(unreal, "ToolsetRegistry", registry)
    monkeypatch.setattr(et, "_TOOLSET_CLASS", _Toolset)
    monkeypatch.setattr(et, "_REGISTERED", True)
    monkeypatch.setattr(unreal, et._STASH_ATTR, _Toolset, raising=False)
    removed = et.unregister()
    _assert_truth_schema(removed)
    assert removed["status"] == "ok"
    assert removed["in_process_registration_record"] == "absent"
    assert registry.unregistered_calls == [_Toolset]


class _MetaRegistry:
    def __init__(self):
        self.calls = []
        self.tools = [
            {
                "name": "alpha_tool",
                "category": "Alpha",
                "description": "Alpha description",
            },
            {
                "name": "beta_tool",
                "category": "Beta",
                "description": "Beta description",
            },
        ]
        self.manifest = {
            "alpha_tool": {
                "name": "alpha_tool",
                "category": "Alpha",
                "description": "Alpha description",
                "tags": ["alpha", "proof"],
                "parameters": {
                    "value": {"type": "int", "required": False, "default": 1}
                },
                "example": 'tb.run("alpha_tool", value=2)',
                "icon": "A",
            },
            "beta_tool": {
                "name": "beta_tool",
                "category": "Beta",
                "description": "Beta description",
                "tags": [],
                "parameters": {},
            },
        }
        self.results = {
            "alpha_tool": {"status": "ok", "value": 1},
            "refusal_tool": {"status": "error", "reason": "refused by contract"},
            "blocked_tool": {"status": "blocked", "message": "blocked by guard"},
        }

    def list_tools(self, category=None):
        if category:
            return [tool for tool in self.tools if tool["category"] == category]
        return list(self.tools)

    def categories(self):
        return ["Alpha", "Beta"]

    def to_manifest(self):
        return dict(self.manifest)

    def execute_strict(self, tool_name, **kwargs):
        self.calls.append((tool_name, kwargs))
        if tool_name == "raising_tool":
            raise ValueError("tool exploded")
        if tool_name not in self.results:
            raise KeyError(f"Unknown tool: '{tool_name}'")
        return self.results[tool_name]


def _generated_class(monkeypatch, registry):
    import unreal

    fake_module = types.SimpleNamespace(tool_call=lambda fn: fn)
    monkeypatch.setitem(sys.modules, "toolset_registry", fake_module)
    monkeypatch.setattr(unreal, "ToolsetDefinition", object, raising=False)
    monkeypatch.setattr(unreal, "uclass", lambda: (lambda cls: cls), raising=False)
    monkeypatch.setattr(et, "_toolbelt_registry", lambda: registry)
    et._TOOLSET_CLASS = None
    return et._build_toolset_class()


def test_list_contract_lists_all_and_filters_exact_category(monkeypatch):
    registry = _MetaRegistry()
    toolset = _generated_class(monkeypatch, registry)

    all_payload = json.loads(toolset.toolbelt_list_tools(""))
    filtered = json.loads(toolset.toolbelt_list_tools("Alpha"))

    assert all_payload["count"] == len(all_payload["tools"]) == 2
    assert all_payload["categories"] == ["Alpha", "Beta"]
    assert all(
        set(tool) == {"name", "category", "description"}
        for tool in all_payload["tools"]
    )
    assert filtered["count"] == len(filtered["tools"]) == 1
    assert filtered["tools"][0]["category"] == "Alpha"
    assert et.status()["internal_meta_tools"]["list"] == "passed"


def test_list_contract_records_failure(monkeypatch):
    registry = _MetaRegistry()
    registry.list_tools = lambda category=None: (_ for _ in ()).throw(
        RuntimeError("list failed")
    )
    toolset = _generated_class(monkeypatch, registry)

    failure = json.loads(toolset.toolbelt_list_tools(""))

    assert failure["status"] == "error"
    assert failure["contract"] == "list"
    assert "list failed" in failure["error"]
    assert et.status()["internal_meta_tools"]["list"] == "failed"


def test_describe_uses_flat_manifest_and_preserves_optional_example(monkeypatch):
    registry = _MetaRegistry()
    toolset = _generated_class(monkeypatch, registry)

    described = json.loads(toolset.toolbelt_describe_tool("alpha_tool"))

    for field in ("name", "category", "description", "tags", "parameters", "example"):
        assert described[field] == registry.manifest["alpha_tool"][field]
    assert et.status()["internal_meta_tools"]["describe"] == "passed"


def test_unknown_describe_fails_explicitly_and_names_the_tool(monkeypatch):
    toolset = _generated_class(monkeypatch, _MetaRegistry())

    failure = json.loads(toolset.toolbelt_describe_tool("missing_tool"))

    assert failure["status"] == "error"
    assert failure["contract"] == "describe"
    assert failure["tool"] == "missing_tool"
    assert "missing_tool" in failure["error"]
    assert et.status()["internal_meta_tools"]["describe"] == "failed"


@pytest.mark.parametrize("arguments", ("", "{}"))
def test_run_accepts_empty_object_inputs(monkeypatch, arguments):
    registry = _MetaRegistry()
    toolset = _generated_class(monkeypatch, registry)

    payload = json.loads(toolset.toolbelt_run_tool("alpha_tool", arguments))

    assert payload == {
        "tool": "alpha_tool",
        "result": {"status": "ok", "value": 1},
    }
    assert registry.calls[-1] == ("alpha_tool", {})
    assert et.status()["internal_meta_tools"]["run"] == "passed"


@pytest.mark.parametrize(
    ("tool_name", "arguments", "error"),
    (
        ("alpha_tool", "{not-json", "not valid JSON"),
        ("alpha_tool", "[]", "must be a JSON object"),
        ("unknown_tool", "{}", "unknown_tool"),
        ("raising_tool", "{}", "tool exploded"),
        ("refusal_tool", "{}", "refused by contract"),
        ("blocked_tool", "{}", "blocked by guard"),
    ),
)
def test_run_failure_contracts_are_explicit(monkeypatch, tool_name, arguments, error):
    toolset = _generated_class(monkeypatch, _MetaRegistry())

    failure = json.loads(toolset.toolbelt_run_tool(tool_name, arguments))

    assert failure["status"] == "error"
    assert failure["contract"] == "run"
    assert failure["tool"] == tool_name
    assert error in failure["error"]
    assert "result" not in failure
    assert et.status()["internal_meta_tools"]["run"] == "failed"


def test_internal_successes_never_change_external_states(monkeypatch):
    registry = _MetaRegistry()
    toolset = _generated_class(monkeypatch, registry)

    toolset.toolbelt_list_tools("")
    toolset.toolbelt_describe_tool("alpha_tool")
    toolset.toolbelt_run_tool("alpha_tool", "{}")
    state = et.status()

    assert state["internal_meta_tools"] == {
        "list": "passed",
        "describe": "passed",
        "run": "passed",
    }
    assert state["external_official_mcp"] == _EXTERNAL_NOT_TESTED


def test_dashboard_copy_separates_internal_and_external_truth():
    from UEFN_Toolbelt import dashboard_pyside6 as dashboard

    state = et.status()
    text, _color = dashboard._format_epic_toolset_status(state)

    assert "Registration attempt: not_attempted" in text
    assert "In-process confirmation: unknown" in text
    assert "list=not_tested, describe=not_tested, run=not_tested" in text
    assert "listable=not_tested, describable=not_tested, callable=not_tested" in text
    assert "do not prove external exposure" in text
    assert "expose the whole Toolbelt catalogue" not in text


def test_direct_user_surfaces_do_not_claim_external_exposure():
    root = Path(__file__).resolve().parents[1]
    surfaces = {
        relative: (root / relative).read_text(encoding="utf-8")
        for relative in (
            "Content/Python/UEFN_Toolbelt/epic_toolset.py",
            "Content/Python/UEFN_Toolbelt/tools/epic_mcp_tools.py",
            "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py",
            "Content/Python/UEFN_Toolbelt/menu.py",
            ".claude/tool_tables.md",
        )
    }
    combined = "\n".join(surfaces.values())

    assert "Expose Toolbelt to any MCP client" not in combined
    assert "expose the whole Toolbelt catalogue to any" not in combined
    assert "Expose every Toolbelt tool to any MCP client" not in combined
    assert "external official-MCP" in combined
    assert "Attempt In-Process Registration" in surfaces[
        "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py"
    ]
