"""
UEFN TOOLBELT — Spline Prop Placer
========================================
Instance props along any selected spline actor with full control over
count, spacing, rotation, scale randomization, and offset.

FEATURES:
  • Select a Spline Actor → pick a mesh → place N instances evenly
  • Spacing mode: count-based OR distance-based (every N units)
  • Per-instance random yaw rotation (optionally align to spline tangent)
  • Random scale within a range
  • XYZ offset from spline (e.g., float props above the curve)
  • Full undo — one Ctrl+Z removes all placed props
  • Groups placed actors under a named folder in World Outliner

USAGE:
    import UEFN_Toolbelt as tb

    # Place 20 trees along selected spline
    tb.run("spline_place_props",
           mesh_path="/Game/MyAssets/SM_Tree",
           count=20,
           align_to_tangent=True,
           scale_min=0.8, scale_max=1.2)

    # Distance-based: one prop every 300 units
    tb.run("spline_place_props",
           mesh_path="/Game/MyAssets/SM_Rock",
           spacing_mode="distance",
           spacing_distance=300.0)

BLUEPRINT:
    "Execute Python Command" →
        import UEFN_Toolbelt as tb; tb.run("spline_place_props", mesh_path="/Game/MyAssets/SM_Lamp", count=30)

REQUIREMENTS:
    • One spline actor must be selected in the viewport.
    • The actor must have a SplineComponent (e.g., a Blueprint with a spline, or a
      landscape spline — any actor with unreal.SplineComponent attached).
"""

from __future__ import annotations

import math
import random
from typing import List, Optional

import unreal

from ..core import (
    undo_transaction, require_selection, log_info, log_warning, log_error,
    spawn_static_mesh_actor,
)
from ..registry import register_tool


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_spline_component(actor: unreal.Actor) -> Optional[unreal.SplineComponent]:
    """Find the first SplineComponent on an actor, or None."""
    comps = actor.get_components_by_class(unreal.SplineComponent.static_class())
    if comps:
        return comps[0]
    return None


def _get_spline_actor() -> Optional[tuple[unreal.Actor, unreal.SplineComponent]]:
    """
    Validate that exactly one spline actor is selected.
    Returns (actor, spline_component) or None.
    """
    from ..core import get_selected_actors
    actors = get_selected_actors()
    if not actors:
        log_warning("Select a Spline Actor in the viewport first.")
        return None

    for actor in actors:
        spline = _find_spline_component(actor)
        if spline:
            return actor, spline

    log_warning("None of the selected actors have a SplineComponent.")
    return None


def _distances_from_count(spline: unreal.SplineComponent, count: int) -> List[float]:
    """Return evenly spaced distances along the spline for a given count."""
    total = spline.get_spline_length()
    if count <= 1:
        return [0.0]
    return [total * i / (count - 1) for i in range(count)]


def _distances_from_spacing(spline: unreal.SplineComponent, spacing: float) -> List[float]:
    """Return distances spaced every `spacing` units along the spline."""
    total = spline.get_spline_length()
    if spacing <= 0:
        spacing = 100.0
    distances = []
    d = 0.0
    while d <= total:
        distances.append(d)
        d += spacing
    return distances


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tool
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="spline_place_props",
    category="Procedural",
    description="Place instanced props along a selected spline actor.",
    shortcut="Ctrl+Alt+S",
    tags=["spline", "prop", "place", "instance", "scatter", "procedural"],
)
def run_place_props(
    mesh_path: str = "/Engine/BasicShapes/Cube",
    count: int = 10,
    spacing_mode: str = "count",       # "count" or "distance"
    spacing_distance: float = 300.0,
    align_to_tangent: bool = True,
    random_yaw: float = 0.0,           # degrees; 0 = no randomization
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    scale_min: float = 1.0,
    scale_max: float = 1.0,
    folder_name: str = "SplineProps",
    **kwargs,
) -> None:
    """
    Args:
        mesh_path:        Content path to the static mesh to instance.
        count:            Number of props when spacing_mode="count".
        spacing_mode:     "count" = N evenly spaced props; "distance" = one per N units.
        spacing_distance: Distance between props in "distance" mode (cm).
        align_to_tangent: Rotate each prop to face the spline's forward direction.
        random_yaw:       Max random yaw offset in degrees (adds variety).
        offset_x/y/z:     World-space offset applied to every prop location (cm).
        scale_min/max:    Random uniform scale range applied to each prop.
        folder_name:      World Outliner folder for the placed actors.
    """
    result = _get_spline_actor()
    if result is None:
        return

    actor, spline = result
    log_info(f"Placing props along spline on '{actor.get_actor_label()}'…")

    # Compute distances
    if spacing_mode == "distance":
        distances = _distances_from_spacing(spline, spacing_distance)
    else:
        distances = _distances_from_count(spline, count)

    if not distances:
        log_error("No distances computed — check count/spacing values.")
        return

    placed: List[unreal.Actor] = []
    offset_vec = unreal.Vector(offset_x, offset_y, offset_z)
    cs = unreal.SplineCoordinateSpace.WORLD

    with undo_transaction(f"Spline Prop Placer: {len(distances)} × {mesh_path.split('/')[-1]}"):
        for i, dist in enumerate(distances):
            # Location
            loc = spline.get_location_at_distance_along_spline(dist, cs)
            loc = unreal.Vector(loc.x + offset_x, loc.y + offset_y, loc.z + offset_z)

            # Rotation
            if align_to_tangent:
                tangent = spline.get_tangent_at_distance_along_spline(dist, cs)
                # Convert tangent to rotator
                rot = unreal.MathLibrary.make_rot_from_x(tangent)
            else:
                rot = unreal.Rotator(0, 0, 0)

            if random_yaw > 0:
                rot = unreal.Rotator(rot.pitch, rot.yaw + random.uniform(-random_yaw, random_yaw), rot.roll)

            # Scale
            s = random.uniform(scale_min, scale_max)
            scale = unreal.Vector(s, s, s)

            prop = spawn_static_mesh_actor(mesh_path, loc, rotation=rot, scale=scale)
            if prop:
                prop.set_folder_path(f"/{folder_name}")
                prop.set_actor_label(f"{folder_name}_{i:03d}")
                placed.append(prop)

    log_info(f"Placed {len(placed)} props along spline. Undo with Ctrl+Z.")


@register_tool(
    name="spline_clear_props",
    category="Procedural",
    description="Delete all actors in the SplineProps folder (undoable).",
    tags=["spline", "prop", "clear", "delete"],
)
def run_clear_props(folder_name: str = "SplineProps", **kwargs) -> None:
    """
    Args:
        folder_name: World Outliner folder to clear.
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()

    to_delete = [
        a for a in all_actors
        if a.get_folder_path() == f"/{folder_name}"
    ]

    if not to_delete:
        log_info(f"No actors found in folder '/{folder_name}'.")
        return

    with undo_transaction(f"Spline Prop Placer: Clear {folder_name}"):
        actor_sub.destroy_actors(to_delete)

    log_info(f"Deleted {len(to_delete)} actors from '/{folder_name}'.")
