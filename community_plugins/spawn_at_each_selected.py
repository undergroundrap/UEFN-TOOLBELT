"""
spawn_at_each_selected — UEFN Toolbelt Community Plugin
========================================================
Stamps a second asset at the world position of every selected actor.

Use cases:
  • Place a light above every torch prop
  • Drop markers at every spawn pad
  • Attach a sign above every chest
  • Duplicate one device to match all positions of another

Author: Ocean Bennett (https://github.com/undergroundrap)
Version: 1.0.0
License: AGPL-3.0
"""

MIN_TOOLBELT_VERSION = "1.9.0"

import unreal
from UEFN_Toolbelt.registry import register_tool


@register_tool(
    name="spawn_at_each_selected",
    category="Community",
    description="Stamp any asset at the position of every selected actor. "
                "Useful for placing lights above props, markers at spawn pads, etc.",
    tags=["spawn", "stamp", "position", "batch", "community"],
)
def spawn_at_each_selected(asset_path: str = "", offset_x: float = 0.0,
                            offset_y: float = 0.0, offset_z: float = 0.0,
                            copy_rotation: bool = False,
                            folder: str = "Stamps", **kwargs) -> dict:
    if not asset_path:
        return {"status": "error", "error": "asset_path is required."}

    actors = unreal.EditorLevelLibrary.get_selected_level_actors()
    if not actors:
        return {"status": "error", "error": "No actors selected."}

    mesh = unreal.load_asset(asset_path)
    if mesh is None:
        return {"status": "error", "error": f"Could not load asset: {asset_path}"}

    offset = unreal.Vector(offset_x, offset_y, offset_z)
    spawned = 0

    with unreal.ScopedEditorTransaction("spawn_at_each_selected") as _:
        for actor in actors:
            loc = actor.get_actor_location() + offset
            rot = actor.get_actor_rotation() if copy_rotation else unreal.Rotator(0, 0, 0)
            new_actor = unreal.EditorLevelLibrary.spawn_actor_from_object(mesh, loc, rot)
            if new_actor:
                new_actor.set_folder_path(folder)
                spawned += 1

    return {"status": "ok", "spawned": spawned, "source_count": len(actors), "folder": folder}
