"""
UEFN TOOLBELT — Plugin Management Tools
========================================
Helps developers validate their own Custom Plugins.
"""

import json
import os

import unreal
from UEFN_Toolbelt.registry import register_tool, get_registry
from UEFN_Toolbelt import core

@register_tool(
    name="plugin_validate_all",
    category="Utilities",
    description="Validate all registered tools against the Toolbelt schema requirements.",
    tags=["plugin", "validate", "developer", "debug"],
)
def validate_all(**kwargs) -> dict:
    """Check all registered tools for schema and description requirements."""
    reg = get_registry()
    errors = reg.validate()
    if not errors:
        core.log_info("✓ All registered tools passed schema validation.")
    else:
        core.log_warning("Found validation errors:")
        for err in errors:
            core.log_warning(err)
    return {"status": "ok" if not errors else "error", "error_count": len(errors), "errors": errors}


@register_tool(
    name="plugin_list_custom",
    category="Utilities",
    description="List all currently loaded third-party custom plugins.",
    tags=["plugin", "list", "developer"],
)
def list_custom(**kwargs) -> dict:
    """List tools that were loaded from the Saved/UEFN_Toolbelt/Custom_Plugins directory."""
    custom_tools = []
    reg = get_registry()
    for name, entry in reg._tools.items():
        source_path = entry.source.replace("\\", "/")
        if "Custom_Plugins" in source_path:
            custom_tools.append(name)

    if not custom_tools:
        core.log_info("No custom plugins found in Saved/UEFN_Toolbelt/Custom_Plugins.")
    else:
        core.log_info(f"Loaded Custom Plugins ({len(custom_tools)}):")
        for name in custom_tools:
            core.log_info(f"  • {name}")
    return {"status": "ok", "count": len(custom_tools), "plugins": custom_tools}


@register_tool(
    name="plugin_export_manifest",
    category="Utilities",
    description="Export a full JSON manifest of all registered tools with signatures and parameters — for AI-agent and automation use.",
    tags=["plugin", "manifest", "export", "developer", "ai", "automation"],
)
def export_manifest(**kwargs) -> dict:
    """
    Introspects every registered tool via inspect.signature and writes
    tool_manifest.json to Saved/UEFN_Toolbelt/.

    The manifest is machine-readable: each tool entry includes its
    category, description, tags, and a parameters block with type,
    required, and default for every non-**kwargs argument.

    Returns:
        dict: {"status": "ok", "path": str, "tool_count": int}
    """
    reg = get_registry()
    manifest = reg.to_manifest()

    out_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "tool_manifest.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    core.log_info(f"Tool manifest exported → {out_path}")
    core.log_info(f"  {len(manifest)} tools · categories: {sorted({v['category'] for v in manifest.values()})}")
    return {"status": "ok", "path": out_path, "tool_count": len(manifest)}
