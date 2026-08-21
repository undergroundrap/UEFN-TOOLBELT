"""
Epic Unreal MCP integration — exposes Toolbelt through the Toolset Registry.
==============================================================================
UEFN 42.00 ships Epic's official Unreal MCP alongside a `ToolsetRegistry`
plugin. A toolset is a Blueprint Function Library whose static methods carry
`meta=(AICallable)`; the registry discovers them and Unreal MCP wraps each one
as an MCP tool for any connected client.

Rather than emit 361 UFunctions — one per Toolbelt tool, each needing UE-mappable
parameter annotations — this exposes three meta-tools that mirror the shape Epic
already uses in tool-search mode (`list_toolsets` / `describe_toolset` /
`call_tool`):

    toolbelt_list_tools(category)              -> JSON index
    toolbelt_describe_tool(tool_name)          -> JSON signature
    toolbelt_run_tool(tool_name, arguments_json) -> JSON result

An agent discovers the catalogue and calls into it, without Toolbelt having to
express every tool's signature in UE's type system. Adding a Toolbelt tool
requires no change here.

SAFETY
------
Every symbol this module touches is optional. `ToolsetRegistry` is an
Experimental plugin and the UEFN MCP toolset sits behind a beta-access flag, so
on most users' machines some or all of it is absent. Nothing here runs at import
time: the toolset class is built lazily inside `register()`, because applying
`@unreal.uclass()` to a missing base class would raise during
`import UEFN_Toolbelt` and take all 361 tools down with it.

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

# Built once by _build_toolset_class(); None until then, or if unavailable.
_TOOLSET_CLASS: Any = None
_REGISTERED = False

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


def _raise_if_refusal(tool_name: str, result: Any) -> None:
    """
    Translate a Toolbelt refusal into a raised error.

    Toolbelt tools report failure by returning {"status": "error", ...} — the
    structured refusals that guard removed engine APIs and unavailable reference
    lookups. Epic's registry signals failure by exception, so a refusal returned
    as a value would reach the agent looking like a success.
    """
    if isinstance(result, dict) and result.get("status") == "error":
        raise RuntimeError(
            f"{tool_name}: {result.get('message') or result.get('reason') or 'failed'}")


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
        """UEFN Toolbelt — 361 level-design, asset and Verse tools."""

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
            reg = _toolbelt_registry()
            tools = reg.list_tools(category or None)
            return _dump({
                "count": len(tools),
                "categories": reg.categories(),
                "tools": [
                    {"name": t.get("name"),
                     "category": t.get("category"),
                     "description": t.get("description")}
                    for t in tools
                ],
            })

        @toolset_registry.tool_call
        @staticmethod
        def toolbelt_describe_tool(tool_name: str) -> str:
            """Full signature for one Toolbelt tool: parameters, types, defaults.

            Args:
                tool_name: Exact tool name, e.g. "light_place".

            Returns:
                JSON manifest entry for the tool.
            """
            manifest = _toolbelt_registry().to_manifest()
            for entry in manifest.get("tools", []):
                if entry.get("name") == tool_name:
                    return _dump(entry)
            known = [t.get("name") for t in _toolbelt_registry().list_tools()]
            raise RuntimeError(
                f"Unknown Toolbelt tool: {tool_name!r}. "
                f"{len(known)} tools available — call toolbelt_list_tools to see them.")

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
            raw = (arguments_json or "").strip()
            try:
                kwargs = json.loads(raw) if raw else {}
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"arguments_json is not valid JSON: {e}. "
                    f'Pass a JSON object such as {{"intensity": 3000}}.') from e
            if not isinstance(kwargs, dict):
                raise RuntimeError(
                    f"arguments_json must be a JSON object, got {type(kwargs).__name__}.")

            # execute_strict, not execute: execute() returns None for both a
            # crash and a tool that legitimately returns nothing, which would
            # report failures to the agent as success.
            result = _toolbelt_registry().execute_strict(tool_name, **kwargs)
            _raise_if_refusal(tool_name, result)
            return _dump({"tool": tool_name, "result": result})

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

    The stash outlives a Toolbelt hot-reload, so its presence means some earlier
    incarnation got a successful register_toolset_class through — it is only
    written on the success path.

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
    Register the Toolbelt toolset with Epic's registry.

    Safe to call when Epic's MCP is absent — reports why and changes nothing.
    Safe to call repeatedly; re-registers cleanly across a Toolbelt hot-reload.
    """
    global _REGISTERED

    state = availability()
    if not state["available"]:
        log_info(f"[EpicMCP] Not registering: {state['reason']}")
        return {"status": "skipped", "registered": False, "reason": state["reason"]}

    try:
        toolset = _build_toolset_class()
    except Exception as e:
        log_warning(f"[EpicMCP] Could not define the toolset class: {e}")
        return {"status": "error", "registered": False, "reason": str(e)}

    # Already registered — leave it alone. register_all_tools() runs again on
    # every smoke test and hot-reload, and churning unregister/register would
    # briefly drop the toolset out from under a connected client.
    if _REGISTERED and getattr(unreal, _STASH_ATTR, None) is toolset:
        _stash(toolset)
        return {"status": "ok", "registered": True, "already_registered": True,
                "toolset": TOOLSET_NAME, "tools_exposed": len(_toolbelt_registry())}

    # Registered earlier this session, before a hot-reload wiped our reference.
    # The name cannot be claimed twice and cannot be released, and UE has already
    # re-instanced the class in place, so the live registration serves the new
    # code. Adopt it rather than provoking two warnings by asking again.
    if registered_earlier_this_session():
        _REGISTERED = True
        _stash(toolset)
        log_info(f"[EpicMCP] Toolset '{TOOLSET_NAME}' already registered this session; "
                 f"UE re-instanced the class, so it serves the reloaded code.")
        return {"status": "ok", "registered": True, "already_registered": True,
                "registration_confirmed": False,
                "toolset": TOOLSET_NAME, "tools_exposed": len(_toolbelt_registry())}

    try:
        unreal.ToolsetRegistry.register_toolset_class(toolset)
    except Exception as e:
        log_warning(f"[EpicMCP] Registration failed: {e}")
        return {"status": "error", "registered": False, "reason": str(e)}

    # Epic's registry LOGS "Unable to register" and returns normally when the
    # name is taken — it does not raise. A call that did not throw is therefore
    # no evidence at all that registration happened, so confirm it.
    # register_toolset_class did not raise. That is the strongest signal Python
    # gets on this build: the query API cannot confirm success, and it cannot
    # report failure either. Claiming a failure we have no evidence for is just
    # the previous bug pointed the other way.
    confirmed = _is_registered(toolset) is True
    _REGISTERED = True
    _stash(toolset)

    note = "" if confirmed else (
        " (unconfirmed — this build's registry cannot be queried from Python; "
        "look for 'LogToolsetRegistry: Registering Toolset' in the editor log)")
    log_info(f"[EpicMCP] Registered toolset '{TOOLSET_NAME}'{note} "
             f"— 3 meta-tools fronting {len(_toolbelt_registry())} Toolbelt tools.")
    return {"status": "ok", "registered": True,
            "registration_confirmed": confirmed,
            "already_registered": False,
            "toolset": TOOLSET_NAME, "tools_exposed": len(_toolbelt_registry())}


def unregister() -> dict[str, Any]:
    """Remove the Toolbelt toolset from Epic's registry."""
    global _REGISTERED

    if _TOOLSET_CLASS is None:
        return {"status": "skipped", "registered": False, "reason": "never registered"}
    try:
        unreal.ToolsetRegistry.unregister_toolset_class(_TOOLSET_CLASS)
    except Exception as e:
        return {"status": "error", "reason": str(e)}
    _REGISTERED = False
    try:
        if getattr(unreal, _STASH_ATTR, None) is _TOOLSET_CLASS:
            delattr(unreal, _STASH_ATTR)
    except Exception:
        pass
    return {"status": "ok", "registered": False}


def status() -> dict[str, Any]:
    """
    Current integration state — for smoke tests and the dashboard.

    `registered` is read back from the registry, not from our own bookkeeping.
    A module-level flag only records what we believed at the time we set it; it
    cannot know about a registration dropped underneath us, and reporting a
    stale belief as current state is the failure this integration already hit
    once. `_REGISTERED` is only a fallback for when the registry will not answer.
    """
    state = availability()

    toolset = _TOOLSET_CLASS or getattr(unreal, _STASH_ATTR, None)
    live = _is_registered(toolset) if toolset is not None else False

    return {
        "status": "ok",
        "epic_mcp_available": state["available"],
        "reason": state["reason"],
        "registered": _REGISTERED if live is None else live,
        "registration_confirmed": live is not None,
        "toolset": TOOLSET_NAME,
        "meta_tools": ["toolbelt_list_tools", "toolbelt_describe_tool", "toolbelt_run_tool"],
    }
