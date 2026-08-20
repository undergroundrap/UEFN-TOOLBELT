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
    description="Report whether Epic's official Unreal MCP toolset registry is available",
    icon="🔌",
    tags=["mcp", "epic", "toolset", "status"],
)
def run_epic_mcp_status(**kwargs) -> dict:
    """
    Show whether this build exposes Epic's Toolset Registry, and whether the
    Toolbelt toolset is currently registered with it.

    Returns:
        dict: {"epic_mcp_available", "reason", "registered", "toolset",
               "meta_tools"}
    """
    return epic_toolset.status()


@register_tool(
    name="epic_mcp_register",
    category="MCP Bridge",
    description="Register Toolbelt's tools with Epic's official Unreal MCP toolset registry",
    icon="🔗",
    tags=["mcp", "epic", "toolset", "register"],
)
def run_epic_mcp_register(**kwargs) -> dict:
    """
    Expose Toolbelt to any MCP client connected to the editor.

    Registers three meta-tools — toolbelt_list_tools, toolbelt_describe_tool
    and toolbelt_run_tool — which front the whole Toolbelt catalogue. This runs
    automatically on register_all_tools(); call it directly to re-register after
    changing beta-access settings.

    Reports {"status": "skipped"} rather than failing when Epic's registry is
    absent, which is the normal case on a build without the Experimental
    ToolsetRegistry plugin enabled.

    Returns:
        dict: {"status", "registered", ...}
    """
    return epic_toolset.register()


@register_tool(
    name="epic_mcp_unregister",
    category="MCP Bridge",
    description="Remove Toolbelt's toolset from Epic's Unreal MCP registry",
    icon="🔌",
    tags=["mcp", "epic", "toolset", "unregister"],
)
def run_epic_mcp_unregister(**kwargs) -> dict:
    """
    Withdraw the Toolbelt toolset so connected MCP clients no longer see it.

    Returns:
        dict: {"status", "registered"}
    """
    return epic_toolset.unregister()
