"""
UEFN TOOLBELT — Niagara VFX Tools
========================================
Spawn and control Niagara particle systems from Python.

What Python CAN do:
  • Spawn NiagaraSystem assets at any world location
  • Set float / vector / color / bool parameters on live components
  • List and audit all Niagara actors in the level
  • Bulk-clear Niagara actors by folder

What Python CANNOT do:
  • Edit emitter internals / stacks — Blueprint-only architecture
  • Create new Niagara assets from scratch
  • Modify emitter graphs or spawn modules

API reference: unreal.NiagaraFunctionLibrary, unreal.NiagaraComponent
"""

from __future__ import annotations

import unreal

from ..core import log_error, log_info, log_warning, undo_transaction
from ..registry import register_tool


def _get_world():
    return unreal.EditorLevelLibrary.get_editor_world()


def _get_niagara_components(actor: unreal.Actor):
    """Return all NiagaraComponents on an actor."""
    try:
        return actor.get_components_by_class(unreal.NiagaraComponent)
    except Exception:
        return []


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="niagara_spawn_system",
    category="VFX",
    description=(
        "Spawn a Niagara particle system at the camera position (or a given location). "
        "Provide the Content Browser asset path to the NiagaraSystem asset."
    ),
    tags=["niagara", "vfx", "particle", "spawn", "fx"],
)
def run_niagara_spawn_system(
    asset_path: str = "",
    location: list = None,
    auto_activate: bool = True,
    folder: str = "VFX",
    label: str = "",
    **kwargs,
) -> dict:
    """
    Spawn a NiagaraSystem actor at the camera position or a given world location.

    Args:
        asset_path:    Content Browser path to a NiagaraSystem asset.
                       e.g. "/Game/VFX/NS_Explosion"
        location:      [x, y, z] world location. Defaults to current camera position.
        auto_activate: Whether the system starts playing immediately (default True).
        folder:        World Outliner folder to place the actor in.
        label:         Optional actor label override.
    """
    if not asset_path:
        return {"status": "error", "error": "asset_path is required. Provide the Content Browser path to a NiagaraSystem asset."}

    try:
        system = unreal.EditorAssetLibrary.load_asset(asset_path)
        if system is None:
            return {"status": "error", "error": f"Asset not found: {asset_path}"}
        if not isinstance(system, unreal.NiagaraSystem):
            return {"status": "error", "error": f"Asset is not a NiagaraSystem: {asset_path}"}
    except Exception as e:
        return {"status": "error", "error": f"Failed to load asset: {e}"}

    # Resolve spawn location
    if location:
        loc = unreal.Vector(*location)
    else:
        try:
            _cam = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            _vp_client = unreal.EditorLevelLibrary.get_editor_world()
            # Fall back to camera via viewport
            view_loc = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
            loc = view_loc[0] if view_loc else unreal.Vector(0, 0, 0)
        except Exception:
            loc = unreal.Vector(0, 0, 0)

    try:
        world = _get_world()
        # Spawning was also outside a transaction, so the new actor could not be
        # undone either.
        with undo_transaction("Spawn Niagara System"):
            actor = unreal.NiagaraFunctionLibrary.spawn_system_at_location(
                world_context_object=world,
                system_template=system,
                location=loc,
                rotation=unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0),
                scale=unreal.Vector(1, 1, 1),
                auto_destroy=False,
                auto_activate=auto_activate,
                pooling_method=unreal.NCPoolMethod.NONE,
                pre_cull_check=True,
            )

            if actor is None:
                return {"status": "error",
                        "error": "spawn_system_at_location returned None. "
                                 "Check asset path and world context."}

            if label:
                actor.set_actor_label(label)
            if folder:
                actor.set_folder_path(folder)

        log_info(f"Spawned Niagara system: {asset_path} at {loc}")
        return {
            "status": "ok",
            "actor_label": actor.get_actor_label(),
            "location": [loc.x, loc.y, loc.z],
            "asset": asset_path,
        }
    except Exception as e:
        log_error(f"niagara_spawn_system failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="niagara_list_systems",
    category="VFX",
    description="List all Niagara particle system actors in the current level — label, asset, location, active state.",
    tags=["niagara", "vfx", "list", "audit", "particle"],
)
def run_niagara_list_systems(**kwargs) -> dict:
    """Audit all Niagara actors in the level."""
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = actor_sub.get_all_level_actors()
        results = []

        for actor in all_actors:
            comps = _get_niagara_components(actor)
            if not comps:
                continue
            for comp in comps:
                try:
                    asset = comp.get_asset()
                    asset_name = asset.get_name() if asset else "None"
                    loc = actor.get_actor_location()
                    results.append({
                        "label":   actor.get_actor_label(),
                        "asset":   asset_name,
                        "active":  comp.is_active(),
                        "folder":  str(actor.get_folder_path()),
                        "location": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
                    })
                except Exception:
                    results.append({"label": actor.get_actor_label(), "asset": "unknown"})

        log_info(f"Found {len(results)} Niagara system actor(s).")
        return {"status": "ok", "count": len(results), "systems": results}
    except Exception as e:
        log_error(f"niagara_list_systems failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="niagara_bulk_set_parameter",
    category="VFX",
    description=(
        "Set a parameter on all Niagara components attached to selected actors. "
        "Supports float, bool, and linear color (hex string) parameter types."
    ),
    tags=["niagara", "vfx", "parameter", "bulk", "set"],
)
def run_niagara_bulk_set_parameter(
    parameter_name: str = "",
    float_value: float = None,
    bool_value: bool = None,
    color_hex: str = "",
    **kwargs,
) -> dict:
    """
    Set a named parameter on Niagara components of selected actors.

    Args:
        parameter_name: The exact Niagara parameter name (e.g. "User.Lifetime")
        float_value:    Value to set if the parameter is a float
        bool_value:     Value to set if the parameter is a bool
        color_hex:      "#RRGGBB" hex string if the parameter is a LinearColor
    """
    if not parameter_name:
        return {"status": "error", "error": "parameter_name is required."}

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = list(actor_sub.get_selected_level_actors())
    if not selected:
        return {"status": "error", "error": "No actors selected. Select actors with Niagara components first."}

    updated = 0
    skipped = 0

    for actor in selected:
        comps = _get_niagara_components(actor)
        if not comps:
            skipped += 1
            continue
        for comp in comps:
            try:
                if float_value is not None:
                    comp.set_variable_float(parameter_name, float_value)
                    updated += 1
                elif bool_value is not None:
                    comp.set_variable_bool(parameter_name, bool_value)
                    updated += 1
                elif color_hex:
                    from ..core import color_from_hex
                    color = color_from_hex(color_hex)
                    comp.set_variable_linear_color(parameter_name, color)
                    updated += 1
                else:
                    return {"status": "error", "error": "Provide float_value, bool_value, or color_hex."}
            except Exception as e:
                log_warning(f"Failed to set param on {actor.get_actor_label()}: {e}")
                skipped += 1

    # skipped counts both actors with no Niagara component and components whose
    # set_variable_* raised. Either way, 0 updated means the parameter was not
    # set anywhere - which is not "ok" just because nothing raised out here.
    if skipped and not updated:
        log_error(
            f"niagara_bulk_set_parameter: 0 component(s) updated, {skipped} "
            f"skipped - '{parameter_name}' was not set on anything. Check the "
            f"parameter name against the system's exposed User. parameters."
        )
        status = "error"
    elif skipped:
        log_warning(
            f"niagara_bulk_set_parameter: {updated} updated, {skipped} skipped."
        )
        status = "partial"
    else:
        status = "ok"

    log_info(f"niagara_bulk_set_parameter: {updated} component(s) updated, {skipped} skipped.")
    return {
        "status": status,
        "parameter": parameter_name,
        "updated": updated,
        "skipped": skipped,
    }


@register_tool(
    name="niagara_clear_systems",
    category="VFX",
    description="Delete all Niagara system actors in a named World Outliner folder.",
    tags=["niagara", "vfx", "clear", "delete", "cleanup"],
)
def run_niagara_clear_systems(
    folder: str = "VFX",
    dry_run: bool = True,
    **kwargs,
) -> dict:
    """
    Delete Niagara actors placed in a specific folder.

    Args:
        folder:  World Outliner folder name to scan (default "VFX")
        dry_run: If True, only reports what would be deleted (default True — always preview first)
    """
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = actor_sub.get_all_level_actors()
        targets = []
        deleted = 0

        # mcp_reference.md promises "all actor ops are wrapped in transactions".
        # This one deleted actors outside any transaction, so Ctrl+Z could not
        # bring them back.
        with undo_transaction(f"Clear Niagara Systems in '{folder}'"):
            for actor in all_actors:
                if str(actor.get_folder_path()) == folder:
                    comps = _get_niagara_components(actor)
                    if comps:
                        targets.append(actor.get_actor_label())
                        if not dry_run:
                            if actor_sub.destroy_actor(actor):
                                deleted += 1
                            else:
                                log_warning(
                                    f"niagara_clear_systems: '{actor.get_actor_label()}' "
                                    f"could not be deleted."
                                )

        count = len(targets) if dry_run else deleted
        log_info(f"niagara_clear_systems: {'would delete' if dry_run else 'deleted'} {count} actor(s) from '{folder}'.")
        return {
            "status": "ok" if dry_run or deleted == len(targets) else (
                "partial" if deleted else "error"),
            "dry_run": dry_run,
            "folder": folder,
            "count": count,
            "attempted": len(targets),
            "actors": targets,
        }
    except Exception as e:
        log_error(f"niagara_clear_systems failed: {e}")
        return {"status": "error", "error": str(e)}
