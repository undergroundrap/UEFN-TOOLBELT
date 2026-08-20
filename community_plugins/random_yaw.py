"""
random_yaw — UEFN Toolbelt Community Plugin
============================================
Randomizes only the yaw (Z-axis rotation) of selected actors.
Useful for natural prop placement where you want random facing
directions without touching pitch or roll.

Author: Ocean Bennett (https://github.com/undergroundrap)
Version: 1.0.0
License: AGPL-3.0
"""

MIN_TOOLBELT_VERSION = "1.5.3"

import random

import unreal

from UEFN_Toolbelt.registry import register_tool


@register_tool(
    name="random_yaw",
    category="Community",
    description="Randomize only the yaw (Z rotation) of selected actors. "
                "Preserves pitch and roll — ideal for natural prop variation.",
    tags=["randomize", "rotation", "props", "quick"],
)
def run(yaw_range: float = 360.0, **kwargs) -> dict:
    """
    Args:
        yaw_range: Total arc to randomize within (default 360 = fully random).
                   Use 45 to limit to ±22.5° from current facing.
    """
    actors = unreal.EditorLevelLibrary.get_selected_level_actors()
    if not actors:
        return {"status": "error", "error": "No actors selected."}

    half = yaw_range / 2.0
    count = 0
    with unreal.ScopedEditorTransaction("random_yaw") as _:
        for actor in actors:
            rot = actor.get_actor_rotation()
            new_yaw = rot.yaw + random.uniform(-half, half)
            actor.set_actor_rotation(
                unreal.Rotator(rot.pitch, new_yaw, rot.roll),
                teleport_physics=True,
            )
            count += 1

    return {"status": "ok", "count": count, "yaw_range": yaw_range}
