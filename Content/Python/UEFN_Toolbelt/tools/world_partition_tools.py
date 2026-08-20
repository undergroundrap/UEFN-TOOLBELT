"""
UEFN TOOLBELT — World Partition & Data Layer Tools
=====================================================
Tools for managing World Partition streaming and Data Layers.

World Partition enables large open-world levels with automatic actor streaming.
Data Layers allow runtime toggling of sets of actors (day/night, seasonal
content, difficulty-gated areas, etc.).

What Python CAN do:
  • Check if World Partition is enabled for the current level
  • List all Data Layers
  • Create new Data Layers
  • Assign selected actors to a Data Layer
  • Toggle Data Layer initial load/visibility states

What Python CANNOT do:
  • Modify World Partition grid size or streaming distances (editor UI only)
  • Trigger runtime data layer streaming from Python (game-world subsystem)
  • Convert an existing level to World Partition without the editor dialog
  • Edit HLOD layer settings programmatically

API: DataLayerEditorSubsystem, WorldPartition, LevelEditorSubsystem
"""

from __future__ import annotations

import unreal

from ..core import log_error, log_info, log_warning
from ..registry import register_tool


def _actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="world_partition_status",
    category="World Partition",
    description=(
        "Check if World Partition is enabled for the current level. "
        "Returns the world name and partition state. "
        "World Partition is required before Data Layers can be used."
    ),
    tags=["world", "partition", "streaming", "status", "check"],
    example='tb.run("world_partition_status")',
)
def run_world_partition_status(**kwargs) -> dict:
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        if world is None:
            return {"status": "error", "message": "No editor world loaded."}

        wp = None
        try:
            wp = world.get_editor_property("world_partition")
        except Exception:
            pass

        enabled = wp is not None
        log_info(f"[world_partition_status] World Partition enabled: {enabled}")
        return {
            "status": "ok",
            "world_name": world.get_name(),
            "world_partition_enabled": enabled,
            "tip": (
                "World Partition is active — use data_layer_list to see content layers."
                if enabled else
                "World Partition is not enabled. Enable it via World Settings → World Partition."
            ),
        }
    except Exception as e:
        log_error(f"[world_partition_status] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="data_layer_list",
    category="World Partition",
    description=(
        "List all Data Layers in the current level with their load/visibility states. "
        "Data Layers group actors that can be streamed in/out at runtime."
    ),
    tags=["data", "layer", "world", "partition", "list", "streaming"],
    example='tb.run("data_layer_list")',
)
def run_data_layer_list(**kwargs) -> dict:
    try:
        subsystem = unreal.get_editor_subsystem(unreal.DataLayerEditorSubsystem)
        if subsystem is None:
            return {"status": "error", "message": "DataLayerEditorSubsystem not available in this UEFN build."}

        layers = subsystem.get_all_data_layers()
        results = []
        for layer in (layers or []):
            entry = {}
            try:
                entry["name"]               = layer.get_editor_property("data_layer_label")
                entry["initially_loaded"]   = layer.get_editor_property("is_initially_loaded")
                entry["initially_visible"]  = layer.get_editor_property("is_initially_visible")
                entry["is_dynamic"]         = layer.get_editor_property("is_dynamic_layer")
            except Exception:
                entry["name"] = str(layer)
            results.append(entry)

        log_info(f"[data_layer_list] {len(results)} data layers")
        return {"status": "ok", "count": len(results), "layers": results}
    except Exception as e:
        log_error(f"[data_layer_list] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="data_layer_create",
    category="World Partition",
    description=(
        "Create a new Data Layer in the current level. "
        "Set initially_loaded=False for content that should only stream in at runtime."
    ),
    tags=["data", "layer", "create", "world", "partition", "new"],
    example='tb.run("data_layer_create", name="NightTimeContent", initially_loaded=False)',
)
def run_data_layer_create(
    name: str = "NewDataLayer",
    initially_loaded: bool = True,
    initially_visible: bool = True,
    **kwargs,
) -> dict:
    try:
        subsystem = unreal.get_editor_subsystem(unreal.DataLayerEditorSubsystem)
        if subsystem is None:
            return {"status": "error", "message": "DataLayerEditorSubsystem not available in this UEFN build."}

        params = unreal.DataLayerCreationParameters()
        layer = subsystem.create_data_layer_instance(params)
        if layer is None:
            return {"status": "error", "message": "Failed to create Data Layer."}

        try:
            layer.set_editor_property("data_layer_label",    name)
            layer.set_editor_property("is_initially_loaded",  initially_loaded)
            layer.set_editor_property("is_initially_visible", initially_visible)
        except Exception as pe:
            log_warning(f"[data_layer_create] Could not set properties: {pe}")

        log_info(f"[data_layer_create] Created: {name}")
        return {
            "status": "ok",
            "name": name,
            "initially_loaded": initially_loaded,
            "initially_visible": initially_visible,
        }
    except Exception as e:
        log_error(f"[data_layer_create] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="data_layer_assign_selection",
    category="World Partition",
    description=(
        "Assign all currently selected level actors to a named Data Layer. "
        "Select actors in the viewport first, then call this tool."
    ),
    tags=["data", "layer", "assign", "actors", "world", "partition", "selection"],
    example='tb.run("data_layer_assign_selection", layer_name="NightTimeContent")',
)
def run_data_layer_assign_selection(layer_name: str = "", **kwargs) -> dict:
    if not layer_name:
        return {"status": "error", "message": "layer_name is required. Run data_layer_list to see available layers."}
    try:
        subsystem = unreal.get_editor_subsystem(unreal.DataLayerEditorSubsystem)
        if subsystem is None:
            return {"status": "error", "message": "DataLayerEditorSubsystem not available in this UEFN build."}

        selected = _actor_sub().get_selected_level_actors()
        if not selected:
            return {"status": "error", "message": "No actors selected. Select actors in the viewport first."}

        target_layer = None
        for layer in (subsystem.get_all_data_layers() or []):
            try:
                if layer.get_editor_property("data_layer_label") == layer_name:
                    target_layer = layer
                    break
            except Exception:
                pass

        if target_layer is None:
            return {
                "status": "error",
                "message": f"Data Layer '{layer_name}' not found. Run data_layer_list to see available layers.",
            }

        assigned = 0
        failed   = []
        for actor in selected:
            try:
                subsystem.add_actor_to_data_layer(actor, target_layer)
                assigned += 1
            except Exception as ae:
                failed.append(actor.get_actor_label())
                log_warning(f"[data_layer_assign] Could not assign {actor.get_actor_label()}: {ae}")

        log_info(f"[data_layer_assign_selection] {assigned}/{len(selected)} assigned to '{layer_name}'")
        return {
            "status": "ok",
            "assigned": assigned,
            "total": len(selected),
            "failed": failed,
            "layer": layer_name,
        }
    except Exception as e:
        log_error(f"[data_layer_assign_selection] {e}")
        return {"status": "error", "message": str(e)}
