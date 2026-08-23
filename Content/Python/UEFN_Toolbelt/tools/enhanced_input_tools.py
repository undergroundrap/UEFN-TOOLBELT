"""
UEFN TOOLBELT — Enhanced Input Tools
======================================
Tools for UEFN's Enhanced Input system (UE5 input framework).

Enhanced Input replaces the legacy Input settings with a graph-based
Action → MappingContext → Trigger/Modifier pipeline.

What Python CAN do:
  • List all InputAction and InputMappingContext assets
  • Inspect action value types (bool, axis1d, axis2d, axis3d)
  • Inspect context key bindings (action → key → triggers)
  • Create new InputAction assets

What Python CANNOT do:
  • Add Trigger/Modifier nodes programmatically (graph-only in Blueprint)
  • Bind contexts to a PlayerController at runtime (game-world only)
  • Modify key bindings in an existing context (property is read-only via Python)

API: unreal.EnhancedInput — 75 types
"""

from __future__ import annotations

import unreal

from ..core import (
    api_unavailable,
    log_error,
    log_info,
    missing_unreal_apis,
    resolve_content_path,
    resolve_scan_path,
    save_asset,
)
from ..registry import register_tool

# unreal.* names this module uses but does not require.
# Removed in UEFN 42.00 (UE 6.0). Guarded by missing_unreal_apis().
__optional_unreal_apis__ = (
    "InputActionFactory",
)


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="input_list_actions",
    category="Enhanced Input",
    description=(
        "List all InputAction assets in the project. InputActions represent "
        "game verbs (Jump, Fire, Move) decoupled from physical keys. "
        "Returns name, path, and value type per action."
    ),
    tags=["input", "enhanced", "action", "list", "enumerate"],
    example='tb.run("input_list_actions", search_path="/Game/")',
)
def run_input_list_actions(search_path: str = "", **kwargs) -> dict:
    """List all InputAction assets under search_path."""
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["InputAction"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = []
        for a in assets:
            entry = {"name": str(a.asset_name), "path": str(a.package_name)}
            try:
                loaded = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if loaded:
                    vt = loaded.get_editor_property("value_type")
                    entry["value_type"] = str(vt) if vt is not None else "unknown"
            except Exception:
                pass
            results.append(entry)
        log_info(f"[input_list_actions] {len(results)} InputAction assets in {search_path}")
        return {"status": "ok", "count": len(results), "actions": results}
    except Exception as e:
        log_error(f"[input_list_actions] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="input_list_contexts",
    category="Enhanced Input",
    description=(
        "List all InputMappingContext assets in the project. "
        "Contexts bind InputActions to physical keys/buttons and are "
        "added/removed at runtime to switch control schemes."
    ),
    tags=["input", "enhanced", "mapping", "context", "list"],
    example='tb.run("input_list_contexts", search_path="/Game/")',
)
def run_input_list_contexts(search_path: str = "", **kwargs) -> dict:
    """List all InputMappingContext assets under search_path."""
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["InputMappingContext"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = [{"name": str(a.asset_name), "path": str(a.package_name)} for a in assets]
        log_info(f"[input_list_contexts] {len(results)} InputMappingContext assets in {search_path}")
        return {"status": "ok", "count": len(results), "contexts": results}
    except Exception as e:
        log_error(f"[input_list_contexts] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="input_inspect_context",
    category="Enhanced Input",
    description=(
        "Inspect an InputMappingContext asset — returns all key mappings: "
        "which InputAction each key/button triggers."
    ),
    tags=["input", "enhanced", "inspect", "context", "mappings", "keys", "bindings"],
    example='tb.run("input_inspect_context", context_path="/Game/Input/IMC_Default")',
)
def run_input_inspect_context(context_path: str = "", **kwargs) -> dict:
    """Inspect an InputMappingContext's key bindings."""
    if not context_path:
        return {"status": "error", "message": "context_path is required."}
    try:
        asset = unreal.EditorAssetLibrary.load_asset(context_path)
        if asset is None:
            return {"status": "error", "message": f"Asset not found: {context_path}"}

        mappings_raw = asset.get_editor_property("mappings")
        result_mappings = []
        for m in (mappings_raw or []):
            entry = {}
            try:
                action = m.get_editor_property("action")
                entry["action"] = action.get_name() if action else "None"
            except Exception:
                entry["action"] = "?"
            try:
                key = m.get_editor_property("key")
                entry["key"] = str(key.key_name) if key else "None"
            except Exception:
                entry["key"] = "?"
            result_mappings.append(entry)

        log_info(f"[input_inspect_context] {len(result_mappings)} mappings in {context_path}")
        return {
            "status": "ok",
            "path": context_path,
            "mapping_count": len(result_mappings),
            "mappings": result_mappings,
        }
    except Exception as e:
        log_error(f"[input_inspect_context] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="input_create_action",
    category="Enhanced Input",
    description=(
        "Create a new InputAction asset. "
        "value_type options: 'bool' (button press), 'axis1d' (trigger/scroll), "
        "'axis2d' (thumbstick XY), 'axis3d' (motion/spatial)."
    ),
    tags=["input", "enhanced", "create", "action", "new"],
    example='tb.run("input_create_action", name="IA_Jump", destination="/Game/Input/", value_type="bool")',
)
def run_input_create_action(
    name: str = "IA_NewAction",
    destination: str = "",
    value_type: str = "bool",
    **kwargs,
) -> dict:
    """Create a new InputAction asset at destination."""
    destination = resolve_content_path(destination, "Input")
    _missing = missing_unreal_apis("InputActionFactory")
    if _missing:
        return api_unavailable("input_create_action", _missing)
    try:
        factory = unreal.InputActionFactory()
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, destination, unreal.InputAction, factory
        )
        if asset is None:
            return {"status": "error", "message": f"Failed to create InputAction '{name}' at {destination}"}

        type_map = {
            "bool":   unreal.InputActionValueType.BOOLEAN,
            "axis1d": unreal.InputActionValueType.AXIS1D,
            "axis2d": unreal.InputActionValueType.AXIS2D,
            "axis3d": unreal.InputActionValueType.AXIS3D,
        }
        vt = type_map.get(value_type.lower())
        if vt is not None:
            asset.set_editor_property("value_type", vt)

        path = f"{destination.rstrip('/')}/{name}"
        saved = save_asset(path)
        log_info(f"[input_create_action] Created: {path} (value_type={value_type})")
        return {
            "status": "ok" if saved else "partial",
            "path": path,
            "name": name,
            "saved": saved,
            "value_type": value_type,
        }
    except Exception as e:
        log_error(f"[input_create_action] {e}")
        return {"status": "error", "message": str(e)}
