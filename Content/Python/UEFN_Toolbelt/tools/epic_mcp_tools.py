"""
Epic Unreal MCP — Toolbelt tools for the official Toolset Registry integration.
==============================================================================
Thin @register_tool wrappers around epic_toolset, so the integration is
inspectable and controllable from the dashboard, the console and the existing
MCP bridge — not only from package internals.

The heavy lifting, and every guard, lives in UEFN_Toolbelt/epic_toolset.py.
"""

from __future__ import annotations

from .. import epic_toolset
from ..registry import register_tool


@register_tool(
    name="epic_mcp_status",
    category="MCP Bridge",
    description="Report separate in-process Toolset Registry and external official-MCP evidence",
    icon="🔌",
    tags=["mcp", "epic", "toolset", "status"],
)
def run_epic_mcp_status(**kwargs) -> dict:
    """
    Show the local registration attempt, positive-only in-process confirmation,
    internal meta-tool contract evidence, and the separate external official-MCP
    state. WO-002 recorded that external result as `failed`, bounded by
    `UE::ValkyrieToolset::ToolsetPolicy`. In-process registration success never
    proves external exposure.

    Returns:
        dict: Stable truth schema containing ``registration_attempt``,
              ``in_process_registry_confirmation``, ``internal_meta_tools``,
              and ``external_official_mcp``.
    """
    return epic_toolset.status()


@register_tool(
    name="epic_mcp_register",
    category="MCP Bridge",
    description="Attempt Toolbelt registration with the in-process Epic Toolset Registry",
    icon="🔗",
    tags=["mcp", "epic", "toolset", "register"],
)
def run_epic_mcp_register(**kwargs) -> dict:
    """
    Submit Toolbelt's generated class to the in-process registry.

    Registers three meta-tools — toolbelt_list_tools, toolbelt_describe_tool
    and toolbelt_run_tool — which front the whole Toolbelt catalogue. This runs
    automatically on register_all_tools(); call it directly to re-register after
    changing beta-access settings.

    A returned registration call or positive in-process confirmation does not
    prove external official-MCP listability, describability, or callability.

    Reports {"status": "skipped"} rather than failing when Epic's registry is
    absent, which is the normal case on a build without the Experimental
    ToolsetRegistry plugin enabled.

    Returns:
        dict: The same stable internal/external truth schema as
              ``epic_mcp_status``.
    """
    return epic_toolset.register()


@register_tool(
    name="epic_mcp_unregister",
    category="MCP Bridge",
    description="Request removal of Toolbelt's class from the in-process registry",
    icon="🔌",
    tags=["mcp", "epic", "toolset", "unregister"],
)
def run_epic_mcp_unregister(**kwargs) -> dict:
    """
    Request in-process removal without claiming any external client state.

    Returns:
        dict: The stable internal/external truth schema.
    """
    return epic_toolset.unregister()
