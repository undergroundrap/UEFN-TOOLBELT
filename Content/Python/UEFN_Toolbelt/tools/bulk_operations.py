"""
UEFN TOOLBELT — Bulk Operations Toolkit
========================================
Selection-based transforms. Every operation supports full undo.

OPERATIONS:
  align_actors         — Snap all selected actors to one axis of the first selected
  distribute_evenly    — Space actors evenly between the two extremes
  randomize_transforms — Apply random location / rotation / scale within ranges
  snap_to_grid         — Snap locations to a grid step
  reset_transforms     — Zero rotation & scale to (1,1,1) on selection
  stack_actors         — Stack actors vertically (Z) with no gaps
  mirror_selection     — Mirror selection across X, Y, or Z axis
  face_camera          — Rotate all selected actors to face the editor camera
  normalize_scale      — Set all selected actors to a uniform target scale

USAGE:
    import UEFN_Toolbelt as tb

    tb.run("bulk_align",        axis="Z")             # align all to first actor's Z
    tb.run("bulk_distribute",   axis="X")             # space evenly along X
    tb.run("bulk_randomize",    rot_range=180.0)      # random full yaw spin
    tb.run("bulk_snap_to_grid", grid=100.0)           # snap to 100cm grid
    tb.run("bulk_reset")                              # zero rot, scale=1
    tb.run("bulk_stack",        gap=0.0)              # stack on Z, no gap
    tb.run("bulk_mirror",       axis="X")             # mirror across X
    tb.run("bulk_normalize_scale", target_scale=1.0) # uniform scale all
    tb.run("bulk_face_camera")                        # yaw actors toward viewport cam
"""

from __future__ import annotations

import math
import random
from typing import List

import unreal

from ..core import (
    undo_transaction, require_selection, get_selected_actors,
    log_info, log_warning, log_error,
    actors_bounding_box, clamp,
)
from ..registry import register_tool


# ─────────────────────────────────────────────────────────────────────────────
#  Alignment
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_align",
    category="Bulk Ops",
    description="Align all selected actors to the first actor's position on one axis.",
    tags=["align", "snap", "bulk", "selection"],
)
def run_align(axis: str = "Z", **kwargs) -> dict:
    """
    Args:
        axis: "X", "Y", or "Z" — which axis to align on.
    """
    actors = require_selection(min_count=2)
    if actors is None:
        return {"count": 0}

    axis = axis.upper()
    if axis not in ("X", "Y", "Z"):
        log_error("axis must be 'X', 'Y', or 'Z'.")
        return {"count": 0}

    ref_loc = actors[0].get_actor_location()
    ref_val = getattr(ref_loc, axis.lower())

    log_info(f"Aligning {len(actors)-1} actors to {axis}={ref_val:.1f}…")

    with undo_transaction(f"Bulk Ops: Align {axis}"):
        for actor in actors[1:]:
            loc = actor.get_actor_location()
            new_loc = unreal.Vector(
                ref_val if axis == "X" else loc.x,
                ref_val if axis == "Y" else loc.y,
                ref_val if axis == "Z" else loc.z,
            )
            actor.set_actor_location(new_loc, False, False)

    log_info("Alignment complete.")
    return {"count": len(actors) - 1, "axis": axis, "value": ref_val}


# ─────────────────────────────────────────────────────────────────────────────
#  Distribution
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_distribute",
    category="Bulk Ops",
    description="Space selected actors evenly between the two extremes along an axis.",
    tags=["distribute", "space", "even", "bulk", "selection"],
)
def run_distribute(axis: str = "X", **kwargs) -> dict:
    """
    Args:
        axis: "X", "Y", or "Z".
    """
    actors = require_selection(min_count=3)
    if actors is None:
        return {"count": 0}

    axis = axis.upper()
    get = {"X": lambda a: a.get_actor_location().x,
           "Y": lambda a: a.get_actor_location().y,
           "Z": lambda a: a.get_actor_location().z}.get(axis)
    if get is None:
        log_error("axis must be 'X', 'Y', or 'Z'.")
        return {"count": 0}

    # Sort by current position along the axis
    sorted_actors = sorted(actors, key=get)
    lo = get(sorted_actors[0])
    hi = get(sorted_actors[-1])
    span = hi - lo
    step = span / (len(sorted_actors) - 1)

    log_info(f"Distributing {len(actors)} actors along {axis} ({lo:.1f}→{hi:.1f})…")

    with undo_transaction(f"Bulk Ops: Distribute {axis}"):
        for i, actor in enumerate(sorted_actors):
            loc = actor.get_actor_location()
            new_val = lo + i * step
            new_loc = unreal.Vector(
                new_val if axis == "X" else loc.x,
                new_val if axis == "Y" else loc.y,
                new_val if axis == "Z" else loc.z,
            )
            actor.set_actor_location(new_loc, False, False)

    log_info("Distribution complete.")
    return {"count": len(actors), "axis": axis, "span": span, "step": step}


# ─────────────────────────────────────────────────────────────────────────────
#  Randomize Transforms
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_randomize",
    category="Bulk Ops",
    description="Apply random location / rotation / scale offsets to selected actors.",
    tags=["randomize", "random", "transform", "bulk"],
)
def run_randomize(
    loc_range: float = 0.0,      # max random XY offset in cm
    loc_z_range: float = 0.0,    # max random Z offset in cm
    rot_range: float = 360.0,    # max random yaw degrees
    pitch_range: float = 0.0,    # max random pitch degrees
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    randomize_loc: bool = False,
    randomize_rot: bool = True,
    randomize_scale: bool = True,
    **kwargs,
) -> dict:
    """
    Args:
        loc_range:      Max XY location offset (0 = no location change).
        loc_z_range:    Max Z location offset.
        rot_range:      Max yaw rotation offset in degrees.
        pitch_range:    Max pitch rotation offset in degrees.
        scale_min/max:  Uniform scale range.
        randomize_*:    Toggle which transforms to randomize.
    """
    actors = require_selection()
    if actors is None:
        return {"count": 0}

    log_info(f"Randomizing transforms on {len(actors)} actors…")

    def rnd(r: float) -> float:
        return random.uniform(-r, r) if r > 0 else 0.0

    with undo_transaction("Bulk Ops: Randomize Transforms"):
        for actor in actors:
            if randomize_loc and (loc_range > 0 or loc_z_range > 0):
                loc = actor.get_actor_location()
                new_loc = unreal.Vector(
                    loc.x + rnd(loc_range),
                    loc.y + rnd(loc_range),
                    loc.z + rnd(loc_z_range),
                )
                actor.set_actor_location(new_loc, False, False)

            if randomize_rot and (rot_range > 0 or pitch_range > 0):
                rot = actor.get_actor_rotation()
                new_rot = unreal.Rotator(
                    rot.pitch + rnd(pitch_range),
                    rot.yaw   + rnd(rot_range),
                    rot.roll,
                )
                actor.set_actor_rotation(new_rot, False)

            if randomize_scale and scale_min != scale_max:
                s = random.uniform(scale_min, scale_max)
                actor.set_actor_scale3d(unreal.Vector(s, s, s))

    log_info("Randomize complete.")
    return {"count": len(actors)}


# ─────────────────────────────────────────────────────────────────────────────
#  Snap to Grid
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_snap_to_grid",
    category="Bulk Ops",
    description="Snap all selected actors' locations to a world grid.",
    tags=["snap", "grid", "align", "bulk"],
)
def run_snap_to_grid(grid: float = 100.0, **kwargs) -> dict:
    """
    Args:
        grid: Grid step size in cm (e.g., 100 for 1-meter grid).
    """
    actors = require_selection()
    if actors is None:
        return {"count": 0}

    if grid <= 0:
        log_error("grid must be positive.")
        return {"count": 0}

    def snap(v: float) -> float:
        return round(v / grid) * grid

    with undo_transaction(f"Bulk Ops: Snap to Grid ({grid}cm)"):
        for actor in actors:
            loc = actor.get_actor_location()
            actor.set_actor_location(
                unreal.Vector(snap(loc.x), snap(loc.y), snap(loc.z)),
                False, False,
            )

    log_info(f"Snapped {len(actors)} actors to {grid}cm grid.")
    return {"count": len(actors), "grid": grid}


# ─────────────────────────────────────────────────────────────────────────────
#  Reset Transforms
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_reset",
    category="Bulk Ops",
    description="Reset rotation to (0,0,0) and scale to (1,1,1) on all selected actors.",
    tags=["reset", "transform", "zero", "bulk"],
)
def run_reset(reset_rotation: bool = True, reset_scale: bool = True, **kwargs) -> dict:
    actors = require_selection()
    if actors is None:
        return {"count": 0}

    with undo_transaction("Bulk Ops: Reset Transforms"):
        for actor in actors:
            if reset_rotation:
                actor.set_actor_rotation(unreal.Rotator(0, 0, 0), False)
            if reset_scale:
                actor.set_actor_scale3d(unreal.Vector(1, 1, 1))

    log_info(f"Reset {len(actors)} actors.")
    return {"count": len(actors)}


# ─────────────────────────────────────────────────────────────────────────────
#  Stack Actors
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_stack",
    category="Bulk Ops",
    description="Stack selected actors vertically (Z) on top of each other.",
    tags=["stack", "vertical", "z", "bulk"],
)
def run_stack(gap: float = 0.0, **kwargs) -> dict:
    """
    Args:
        gap: Extra space (cm) between each stacked actor.
    """
    actors = require_selection(min_count=2)
    if actors is None:
        return {"count": 0}

    # Sort by current Z position
    sorted_actors = sorted(actors, key=lambda a: a.get_actor_location().z)
    base_z = sorted_actors[0].get_actor_location().z
    current_z = base_z

    with undo_transaction("Bulk Ops: Stack Actors"):
        for actor in sorted_actors:
            loc = actor.get_actor_location()
            # Approximate height from bounding box
            origin, box_extent = actor.get_actor_bounds(False)
            height = box_extent.z * 2
            
            # SCHEMA HARDENING: Account for pivot_offset (discovered in schema)
            # pivot_offset is relative to the actor origin. Use getattr — get_editor_property
            # raises on Verse-driven properties that aren't tagged as editor properties.
            try:
                pivot = getattr(actor, "pivot_offset", unreal.Vector(0, 0, 0))
            except Exception:
                pivot = unreal.Vector(0, 0, 0)
            
            actor.set_actor_location(
                unreal.Vector(loc.x, loc.y, current_z + box_extent.z - pivot.z),
                False, False,
            )
            current_z += height + gap

    log_info(f"Stacked {len(actors)} actors.")
    return {"count": len(actors), "gap": gap}


# ─────────────────────────────────────────────────────────────────────────────
#  Mirror Selection
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_mirror",
    category="Bulk Ops",
    description="Mirror selected actors across an axis (reflects position about center).",
    tags=["mirror", "flip", "symmetry", "bulk"],
)
def run_mirror(axis: str = "X", **kwargs) -> dict:
    """
    Args:
        axis: "X", "Y", or "Z" — axis to mirror across.
    """
    actors = require_selection(min_count=1)
    if actors is None:
        return {"count": 0}

    axis = axis.upper()

    # Find center of selection
    mn, mx = actors_bounding_box(actors)
    center = unreal.Vector((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, (mn.z + mx.z) / 2)

    with undo_transaction(f"Bulk Ops: Mirror {axis}"):
        for actor in actors:
            loc = actor.get_actor_location()
            new_loc = unreal.Vector(
                2 * center.x - loc.x if axis == "X" else loc.x,
                2 * center.y - loc.y if axis == "Y" else loc.y,
                2 * center.z - loc.z if axis == "Z" else loc.z,
            )
            actor.set_actor_location(new_loc, False, False)

            # Mirror rotation yaw for X/Y mirrors
            rot = actor.get_actor_rotation()
            if axis == "X":
                actor.set_actor_rotation(unreal.Rotator(rot.pitch, -rot.yaw, rot.roll), False)
            elif axis == "Y":
                actor.set_actor_rotation(unreal.Rotator(rot.pitch, 180 - rot.yaw, rot.roll), False)

    log_info(f"Mirrored {len(actors)} actors across {axis}.")
    return {"count": len(actors), "axis": axis}


# ─────────────────────────────────────────────────────────────────────────────
#  Normalize Scale
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_normalize_scale",
    category="Bulk Ops",
    description="Set all selected actors to a uniform target scale.",
    tags=["scale", "normalize", "uniform", "bulk"],
)
def run_normalize_scale(target_scale: float = 1.0, **kwargs) -> dict:
    """
    Args:
        target_scale: Uniform scale value to apply to all selected actors.
    """
    actors = require_selection()
    if actors is None:
        return {"count": 0}

    s = unreal.Vector(target_scale, target_scale, target_scale)

    with undo_transaction(f"Bulk Ops: Normalize Scale → {target_scale}"):
        for actor in actors:
            actor.set_actor_scale3d(s)

    log_info(f"Set scale={target_scale} on {len(actors)} actors.")
    return {"count": len(actors), "target_scale": target_scale}


# ─────────────────────────────────────────────────────────────────────────────
#  Face Camera
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="bulk_face_camera",
    category="Bulk Ops",
    description="Rotate all selected actors to face the editor viewport camera (yaw only).",
    tags=["face", "camera", "rotate", "look", "bulk"],
)
def run_face_camera(**kwargs) -> dict:
    actors = require_selection()
    if actors is None:
        return {"count": 0}

    cam_loc, _ = unreal.EditorLevelLibrary.get_level_viewport_camera_info()

    with undo_transaction("Bulk Ops: Face Camera"):
        for actor in actors:
            loc = actor.get_actor_location()
            dx = cam_loc.x - loc.x
            dy = cam_loc.y - loc.y
            yaw = math.degrees(math.atan2(dy, dx))
            actor.set_actor_rotation(unreal.Rotator(0, yaw, 0), False)

    log_info(f"Rotated {len(actors)} actors to face camera.")
    return {"count": len(actors)}


@register_tool(
    name="mesh_merge_selection",
    category="Bulk Ops",
    description=(
        "Merge all selected StaticMesh actors into a single mesh asset — "
        "one draw call instead of N. Saves to /Game/UEFN_Toolbelt/Merged/ by default."
    ),
    tags=["merge", "static mesh", "optimization", "draw call", "bulk", "performance"],
)
def run_mesh_merge_selection(
    dest_path: str = "/Game/UEFN_Toolbelt/Merged",
    asset_name: str = "MergedMesh",
    replace_originals: bool = False,
    **kwargs,
) -> dict:
    """
    Merge selected StaticMesh actors into one combined StaticMesh asset.

    Args:
        dest_path:         Content Browser folder for the new asset (default /Game/UEFN_Toolbelt/Merged)
        asset_name:        Name of the resulting mesh asset (default MergedMesh)
        replace_originals: If True, delete source actors after merge (default False — keep originals)

    Note:
        Requires UnrealEditor-MeshMergeUtilities. If UEFN sandboxes this API,
        the tool returns a clear error — no harm done.
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = actor_sub.get_selected_level_actors()
    mesh_actors = [a for a in actors if isinstance(a, unreal.StaticMeshActor)]
    if not mesh_actors:
        return {"status": "error", "error": "No StaticMesh actors selected. Select the meshes you want to merge."}

    try:
        merge_options = unreal.MeshMergingSettings()
        merge_options.pivot_point_at_zero = False
        merge_options.merge_physics_data = False

        result = unreal.EditorLevelLibrary.merge_static_mesh_actors(
            mesh_actors,
            merge_options,
            dest_path,
            asset_name,
            True,    # spawn merged actor in level
            replace_originals,
        )

        if result:
            log_info(f"mesh_merge_selection: merged {len(mesh_actors)} meshes → {dest_path}/{asset_name}")
            return {
                "status": "ok",
                "source_actors": len(mesh_actors),
                "asset_path": f"{dest_path}/{asset_name}",
                "originals_replaced": replace_originals,
            }
        return {"status": "error", "error": "Merge returned no result — check Output Log."}
    except AttributeError as e:
        return {
            "status": "error",
            "error": f"merge_static_mesh_actors not available in this UEFN build: {e}",
            "tip": "This API may be sandboxed. Use scatter_hism for identical-mesh batching instead.",
        }
    except Exception as e:
        log_error(f"mesh_merge_selection failed: {e}")
        return {"status": "error", "error": str(e)}
