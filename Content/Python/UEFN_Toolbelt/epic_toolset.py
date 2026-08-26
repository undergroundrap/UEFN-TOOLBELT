"""
Epic Unreal MCP integration — in-process Toolset Registry adapter.
==================================================================
UEFN 42.00 ships Epic's official Unreal MCP alongside a `ToolsetRegistry`
plugin. A toolset is a Blueprint Function Library whose static methods carry
`meta=(AICallable)`. Submitting that class to the in-editor registry does not
prove that Epic's external creator-facing MCP policy lists, describes, or calls
it; those states require separate external evidence.

Rather than emit 362 UFunctions — one per Toolbelt tool, each needing UE-mappable
parameter annotations — this exposes three meta-tools that mirror the shape Epic
already uses in tool-search mode (`list_toolsets` / `describe_toolset` /
`call_tool`):

    toolbelt_list_tools(category)              -> JSON index
    toolbelt_describe_tool(tool_name)          -> JSON signature
    toolbelt_run_tool(tool_name, arguments_json) -> JSON result

The generated class can list, describe, and run the catalogue in process
without Toolbelt having to express every tool's signature in UE's type system.
Whether Epic's external MCP discovers that class is separate evidence. Adding a
Toolbelt tool requires no change here.

SAFETY
------
Every symbol this module touches is optional. `ToolsetRegistry` is an
Experimental plugin and the UEFN MCP toolset sits behind a beta-access flag, so
on most users' machines some or all of it is absent. Nothing here runs at import
time: the toolset class is built lazily inside `register()`, because applying
`@unreal.uclass()` to a missing base class would raise during
`import UEFN_Toolbelt` and take all 362 tools down with it.

Reference: Engine/Plugins/Experimental/ToolsetRegistry/Content/Python/toolset_registry
"""

from __future__ import annotations

import json
from typing import Any

import unreal

from .core import log_info, log_warning

# unreal.* names this module uses but does not require.
# Epic's ToolsetRegistry is an Experimental plugin behind a beta-access flag.
# Absent on most machines; availability() checks before anything touches it.
__optional_unreal_apis__ = (
    "ToolsetDefinition",
    "ToolsetRegistry",
    "uclass",
)

TOOLSET_NAME = "UEFN_Toolbelt"
META_TOOLS = (
    "toolbelt_list_tools",
    "toolbelt_describe_tool",
    "toolbelt_run_tool",
)

REGISTRATION_NOT_ATTEMPTED = "not_attempted"
REGISTRATION_RETURNED = "returned_without_exception"
REGISTRATION_RAISED = "raised"
REGISTRATION_ADOPTED = "adopted_from_current_editor_session"
CONFIRMATION_CONFIRMED = "confirmed"
CONFIRMATION_UNKNOWN = "unknown"
CONTRACT_NOT_TESTED = "not_tested"
CONTRACT_PASSED = "passed"
CONTRACT_FAILED = "failed"

# Built once by _build_toolset_class(); None until then, or if unavailable.
_TOOLSET_CLASS: Any = None
_REGISTERED = False
_REGISTRATION_ATTEMPT = REGISTRATION_NOT_ATTEMPTED
_IN_PROCESS_CONFIRMATION = CONFIRMATION_UNKNOWN
_INTERNAL_CONTRACTS = {
    "list": CONTRACT_NOT_TESTED,
    "describe": CONTRACT_NOT_TESTED,
    "run": CONTRACT_NOT_TESTED,
}

# Where the live toolset class is parked so it survives a Toolbelt hot-reload.
#
# The documented reload — the one deploy.bat prints — pops every UEFN_Toolbelt
# module out of sys.modules. That destroys this module's reference to the class
# while Epic's registry goes on holding the NAME, so the next register() builds a
# fresh class, the registry rejects it as a duplicate, and there is nothing left
# to hand unregister_toolset_class(). The `unreal` module is not popped by that
# reload, so a reference parked there outlives it and the stale registration can
# be cleaned up properly.
_STASH_ATTR = "_uefn_toolbelt_toolset_class"


# ─── Availability ─────────────────────────────────────────────────────────────

def availability() -> dict[str, Any]:
    """
    Report whether this build can host a Toolbelt toolset, and why not if it
    cannot. Callers should treat a False result as ordinary, not as an error —
    the registry is Experimental and gated behind beta access.
    """
    if not hasattr(unreal, "ToolsetDefinition"):
        return {"available": False,
                "reason": "unreal.ToolsetDefinition is not exposed in this build "
                          "(ToolsetRegistry plugin missing or disabled)."}

    registry = getattr(unreal, "ToolsetRegistry", None)
    if registry is None:
        return {"available": False,
                "reason": "unreal.ToolsetRegistry is not exposed in this build."}

    try:
        import toolset_registry  # noqa: F401
    except Exception as e:
        return {"available": False,
                "reason": f"Epic's toolset_registry Python module is not importable: {e}"}

    try:
        if not registry.is_available():
            return {"available": False,
                    "reason": "ToolsetRegistry reports unavailable. Enable the UEFN MCP "
                              "toolset under Project Settings → Beta Access, then restart."}
    except Exception as e:
        return {"available": False, "reason": f"ToolsetRegistry.is_available() failed: {e}"}

    return {"available": True, "reason": ""}


# ─── Payload helpers ──────────────────────────────────────────────────────────

def _dump(payload: Any) -> str:
    """
    Serialise a tool result for the MCP transport.

    The registry parses tool output with json.loads, so every tool must return
    a JSON string. `default=str` keeps unreal.Vector, Name, Path and friends from
    turning a working tool into a serialisation crash — they arrive at the agent
    as their repr, which is readable, rather than as an error.
    """
    return json.dumps(payload, default=str)


def _toolbelt_registry():
    from .registry import get_registry
    return get_registry()


def _state_payload(
    *,
    status_value: str,
    registry_available: bool,
    reason: str = "",
) -> dict[str, Any]:
    """Return the stable Session A truth schema without external inference."""
    return {
        "status": status_value,
        "toolset_registry_available": registry_available,
        "reason": reason,
        "toolset": TOOLSET_NAME,
        "meta_tools": list(META_TOOLS),
        "registration_attempt": _REGISTRATION_ATTEMPT,
        "in_process_registration_record": (
            "present" if _REGISTERED else "absent"
        ),
        "in_process_registry_confirmation": _IN_PROCESS_CONFIRMATION,
        "internal_meta_tools": dict(_INTERNAL_CONTRACTS),
        "external_official_mcp": {
            "listable": CONTRACT_NOT_TESTED,
            "describable": CONTRACT_NOT_TESTED,
            "callable": CONTRACT_NOT_TESTED,
        },
    }


def _set_internal_contract(name: str, outcome: str) -> None:
    _INTERNAL_CONTRACTS[name] = outcome


def _contract_failure(contract: str, error: Exception, tool_name: str = "") -> str:
    """Return an explicit JSON failure that survives Epic's decorator wrapper."""
    payload = {
        "status": "error",
        "contract": contract,
        "error": f"{type(error).__name__}: {error}",
    }
    if tool_name:
        payload["tool"] = tool_name
    return _dump(payload)


def _raise_if_refusal(tool_name: str, result: Any) -> None:
    """
    Translate a Toolbelt refusal into a raised error.

    Toolbelt tools report failure by returning {"status": "error", ...} — the
    structured refusals that guard removed engine APIs and unavailable reference
    lookups. Epic's registry signals failure by exception, so a refusal returned
    as a value would reach the agent looking like a success.
    """
    refusal_statuses = {"error", "blocked", "denied", "refused", "skipped", "unavailable"}
    if (isinstance(result, dict)
            and str(result.get("status", "")).lower() in refusal_statuses):
        raise RuntimeError(
            f"{tool_name}: {result.get('message') or result.get('reason') or 'failed'}")


def _list_tools(category: str) -> str:
    """Execute and record the direct in-process list contract."""
    try:
        reg = _toolbelt_registry()
        tools = reg.list_tools(category or None)
        payload = {
            "count": len(tools),
            "categories": reg.categories(),
            "tools": [
                {
                    "name": tool.get("name"),
                    "category": tool.get("category"),
                    "description": tool.get("description"),
                }
                for tool in tools
            ],
        }
        encoded = _dump(payload)
    except Exception as error:
        _set_internal_contract("list", CONTRACT_FAILED)
        return _contract_failure("list", error)
    _set_internal_contract("list", CONTRACT_PASSED)
    return encoded


def _describe_tool(tool_name: str) -> str:
    """Execute and record the direct in-process describe contract."""
    try:
        manifest = _toolbelt_registry().to_manifest()
        if tool_name not in manifest:
            raise RuntimeError(
                f"Unknown Toolbelt tool: {tool_name!r}. "
                f"{len(manifest)} tools available — call toolbelt_list_tools to see them."
            )
        encoded = _dump(manifest[tool_name])
    except Exception as error:
        _set_internal_contract("describe", CONTRACT_FAILED)
        return _contract_failure("describe", error, tool_name)
    _set_internal_contract("describe", CONTRACT_PASSED)
    return encoded


def _run_tool(tool_name: str, arguments_json: str) -> str:
    """Execute and record the direct in-process run contract."""
    try:
        raw = (arguments_json or "").strip()
        try:
            kwargs = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"arguments_json is not valid JSON: {e}. "
                f'Pass a JSON object such as {{"intensity": 3000}}.'
            ) from e
        if not isinstance(kwargs, dict):
            raise RuntimeError(
                f"arguments_json must be a JSON object, got {type(kwargs).__name__}."
            )

        result = _toolbelt_registry().execute_strict(tool_name, **kwargs)
        _raise_if_refusal(tool_name, result)
        encoded = _dump({"tool": tool_name, "result": result})
    except Exception as error:
        _set_internal_contract("run", CONTRACT_FAILED)
        return _contract_failure("run", error, tool_name)
    _set_internal_contract("run", CONTRACT_PASSED)
    return encoded


# ─── Toolset definition ───────────────────────────────────────────────────────

def _build_toolset_class() -> Any:
    """
    Define the toolset class against the live engine.

    Deliberately not at module scope: `@unreal.uclass()` over a missing
    `unreal.ToolsetDefinition` raises at import, which would break the package
    for every user who does not have the Experimental plugin enabled.
    """
    global _TOOLSET_CLASS
    if _TOOLSET_CLASS is not None:
        return _TOOLSET_CLASS

    import toolset_registry

    @unreal.uclass()
    class UEFNToolbeltToolset(unreal.ToolsetDefinition):
        """UEFN Toolbelt — 362 level-design, asset and Verse tools."""

        @toolset_registry.tool_call
        @staticmethod
        def toolbelt_list_tools(category: str) -> str:
            """List Toolbelt tools. Pass an empty category for all of them.

            Args:
                category: Category to filter by, e.g. "Lighting". Empty for all.

            Returns:
                JSON: {"count", "categories", "tools":[{"name","category",
                "description"}]}
            """
            return _list_tools(category)

        @toolset_registry.tool_call
        @staticmethod
        def toolbelt_describe_tool(tool_name: str) -> str:
            """Full signature for one Toolbelt tool: parameters, types, defaults.

            Args:
                tool_name: Exact tool name, e.g. "light_place".

            Returns:
                JSON manifest entry for the tool.
            """
            return _describe_tool(tool_name)

        @toolset_registry.tool_call
        @staticmethod
        def toolbelt_run_tool(tool_name: str, arguments_json: str) -> str:
            """Run a Toolbelt tool and return its result as JSON.

            Args:
                tool_name: Exact tool name, e.g. "light_place".
                arguments_json: JSON object of keyword arguments. Empty for none.

            Returns:
                JSON: {"tool", "result"}.
            """
            return _run_tool(tool_name, arguments_json)

    # Without this the class carries a qualname of
    # "_build_toolset_class.<locals>.UEFNToolbeltToolset", an artefact of being
    # defined inside a function to keep @unreal.uclass() off the import path.
    UEFNToolbeltToolset.__qualname__ = "UEFNToolbeltToolset"

    _TOOLSET_CLASS = UEFNToolbeltToolset
    return _TOOLSET_CLASS


# ─── Registration ─────────────────────────────────────────────────────────────

def _stash(toolset: Any) -> None:
    """Park the live class where a Toolbelt hot-reload cannot destroy it."""
    try:
        setattr(unreal, _STASH_ATTR, toolset)
    except Exception:
        pass  # Losing the stash costs a restart, never correctness.


def registered_earlier_this_session() -> bool:
    """
    Did a previous load of this module already register the toolset?

    The stash outlives a Toolbelt hot-reload, so its presence means an earlier
    incarnation received a non-raising return from register_toolset_class and
    retained the class. It is an adoption signal, not external exposure proof.

    This matters because on UEFN 42.00 a toolset name can be claimed exactly once
    per editor session. Re-registering is refused ("already registered"), and
    unregister_toolset_class does not release it: called on the stashed class it
    returns without error while the name stays held, the same identity problem
    the query API has.

    Re-registering is also unnecessary. The editor logs "Re-instancing
    UEFNToolbeltToolset after reload — 1 class changed": UE swaps the UClass
    implementation by name, so the existing registration already dispatches into
    the freshly loaded code.
    """
    return getattr(unreal, _STASH_ATTR, None) is not None


def _is_registered(toolset: Any) -> bool | None:
    """
    Is this toolset class currently registered?

    Returns True only on a positive confirmation, otherwise None for "cannot
    tell". It never returns False.

    That is not defensiveness, it is what this build does. On UEFN 42.00 every
    query answers False for a Python-defined toolset even in the same tick the
    registry logs "Registering Toolset UEFN_Toolbelt.epic_toolset.
    UEFNToolbeltToolset" for that exact class — checked live against
    is_toolset_class_registered and is_toolset_registered with the qualified,
    short and friendly names. A False from an API that always says False is not
    evidence of anything, and treating it as one made register() report a
    failure for a registration that had just succeeded.

    Kept as a positive-only signal so it starts working for free if Epic fixes
    the query side.
    """
    registry = getattr(unreal, "ToolsetRegistry", None)
    if registry is None:
        return None
    try:
        if registry.is_toolset_class_registered(toolset):
            return True
    except Exception:
        pass
    return None


def register() -> dict[str, Any]:
    """
    Attempt an in-process Toolbelt toolset registration.

    Safe to call when Epic's MCP is absent — reports why and changes nothing.
    Safe to call repeatedly; adopts the current editor-session registration
    across a Toolbelt hot-reload. No branch claims external official-MCP
    listability, describability, or callability.
    """
    global _IN_PROCESS_CONFIRMATION, _REGISTERED, _REGISTRATION_ATTEMPT

    state = availability()
    if not state["available"]:
        _REGISTERED = False
        _REGISTRATION_ATTEMPT = REGISTRATION_NOT_ATTEMPTED
        _IN_PROCESS_CONFIRMATION = CONFIRMATION_UNKNOWN
        log_info(f"[EpicMCP] In-process registration not attempted: {state['reason']}")
        return _state_payload(
            status_value="skipped",
            registry_available=False,
            reason=state["reason"],
        )

    try:
        toolset = _build_toolset_class()
    except Exception as e:
        _REGISTERED = False
        _REGISTRATION_ATTEMPT = REGISTRATION_NOT_ATTEMPTED
        _IN_PROCESS_CONFIRMATION = CONFIRMATION_UNKNOWN
        log_warning(f"[EpicMCP] Could not define the toolset class: {e}")
        return _state_payload(
            status_value="error",
            registry_available=True,
            reason=str(e),
        )

    # Already registered — leave it alone. register_all_tools() runs again on
    # every smoke test and hot-reload, and churning unregister/register would
    # unnecessarily disturb the in-process registry entry.
    if _REGISTERED and getattr(unreal, _STASH_ATTR, None) is toolset:
        _REGISTRATION_ATTEMPT = REGISTRATION_ADOPTED
        if _is_registered(toolset) is True:
            _IN_PROCESS_CONFIRMATION = CONFIRMATION_CONFIRMED
        else:
            _IN_PROCESS_CONFIRMATION = CONFIRMATION_UNKNOWN
        _stash(toolset)
        return _state_payload(status_value="ok", registry_available=True)

    # Registered earlier this session, before a hot-reload wiped our reference.
    # The name cannot be claimed twice and cannot be released, and UE has already
    # re-instanced the class in place, so the live registration serves the new
    # code. Adopt it rather than provoking two warnings by asking again.
    if registered_earlier_this_session():
        _REGISTERED = True
        _REGISTRATION_ATTEMPT = REGISTRATION_ADOPTED
        if _is_registered(toolset) is True:
            _IN_PROCESS_CONFIRMATION = CONFIRMATION_CONFIRMED
        else:
            _IN_PROCESS_CONFIRMATION = CONFIRMATION_UNKNOWN
        _stash(toolset)
        log_info(
            f"[EpicMCP] Adopted the in-process '{TOOLSET_NAME}' class from this "
            "editor session. External official-MCP states remain not_tested."
        )
        return _state_payload(status_value="ok", registry_available=True)

    try:
        unreal.ToolsetRegistry.register_toolset_class(toolset)
    except Exception as e:
        _REGISTERED = False
        _REGISTRATION_ATTEMPT = REGISTRATION_RAISED
        _IN_PROCESS_CONFIRMATION = CONFIRMATION_UNKNOWN
        log_warning(f"[EpicMCP] Registration failed: {e}")
        return _state_payload(
            status_value="error",
            registry_available=True,
            reason=str(e),
        )

    # Epic's registry LOGS "Unable to register" and returns normally when the
    # name is taken — it does not raise. A call that did not throw is therefore
    # no evidence at all that registration happened, so confirm it.
    # register_toolset_class did not raise. That is the strongest signal Python
    # gets on this build: the query API cannot confirm success, and it cannot
    # report failure either. Claiming a failure we have no evidence for is just
    # the previous bug pointed the other way.
    confirmed = _is_registered(toolset) is True
    _REGISTERED = True
    _REGISTRATION_ATTEMPT = REGISTRATION_RETURNED
    _IN_PROCESS_CONFIRMATION = (
        CONFIRMATION_CONFIRMED if confirmed else CONFIRMATION_UNKNOWN
    )
    _stash(toolset)

    confirmation = "confirmed in-process" if confirmed else "not confirmed in-process"
    log_info(
        f"[EpicMCP] Registration call for '{TOOLSET_NAME}' returned without "
        f"exception ({confirmation}). External official-MCP states remain not_tested."
    )
    return _state_payload(status_value="ok", registry_available=True)


def unregister() -> dict[str, Any]:
    """Request in-process removal without claiming external state."""
    global _IN_PROCESS_CONFIRMATION, _REGISTERED

    state = availability()
    toolset = _TOOLSET_CLASS or getattr(unreal, _STASH_ATTR, None)
    if toolset is None:
        _REGISTERED = False
        _IN_PROCESS_CONFIRMATION = CONFIRMATION_UNKNOWN
        return _state_payload(
            status_value="skipped",
            registry_available=state["available"],
            reason="no in-process Toolbelt class reference is present",
        )
    try:
        unreal.ToolsetRegistry.unregister_toolset_class(toolset)
    except Exception as e:
        return _state_payload(
            status_value="error",
            registry_available=state["available"],
            reason=str(e),
        )
    _REGISTERED = False
    _IN_PROCESS_CONFIRMATION = CONFIRMATION_UNKNOWN
    try:
        if getattr(unreal, _STASH_ATTR, None) is toolset:
            delattr(unreal, _STASH_ATTR)
    except Exception:
        pass
    return _state_payload(
        status_value="ok",
        registry_available=state["available"],
    )


def status() -> dict[str, Any]:
    """
    Return the stable internal/external integration truth schema.

    A positive live-class query confirms only the in-process registry state.
    Missing or false query evidence remains unknown, and no local observation
    changes an external official-MCP state from ``not_tested``.
    """
    global _IN_PROCESS_CONFIRMATION, _REGISTERED
    state = availability()

    toolset = _TOOLSET_CLASS or getattr(unreal, _STASH_ATTR, None)
    if toolset is not None and _is_registered(toolset) is True:
        _REGISTERED = True
        _IN_PROCESS_CONFIRMATION = CONFIRMATION_CONFIRMED

    return _state_payload(
        status_value="ok",
        registry_available=state["available"],
        reason=state["reason"],
    )
