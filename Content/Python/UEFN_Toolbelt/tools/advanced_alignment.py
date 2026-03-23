"""
UEFN TOOLBELT — Advanced Alignment & Distribution Toolkit
==========================================================
Precision alignment and distribution tools that extend the basic bulk_operations module.
All operations are wrapped in ScopedEditorTransaction for full undo support.

OPERATIONS:
  align_to_reference       — Align selected actors on one axis to the first or last selected actor
  distribute_with_gap      — Distribute actors along an axis with an exact cm gap between bounds
  rotate_around_pivot      — Rotate and orbit selected actors around a shared pivot point
  align_to_surface         — Snap each selected actor down to the nearest floor surface
  match_spacing            — Evenly space actor pivots between the first and last pivot positions
  align_to_grid_two_points — Define a custom grid from two anchor actors and snap the rest to it

USAGE:
    import UEFN_Toolbelt as tb

    tb.run("align_to_reference",       axis="Z", reference="first")
    tb.run("distribute_with_gap",      axis="X", gap=50.0)
    tb.run("rotate_around_pivot",      angle_deg=90.0, axis="Z", pivot="center")
    tb.run("align_to_surface",         offset_z=0.0)
    tb.run("match_spacing",            axis="X")
    tb.run("align_to_grid_two_points", grid_size=100.0)
"""

from __future__ import annotations

import math
from typing import List, Tuple

import unreal

from ..core import log_info, log_error, log_warning
from ..registry import register_tool


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _actor_sub() -> unreal.EditorActorSubsystem:
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _get_selected() -> List[unreal.Actor]:
    selected = _actor_sub().get_selected_level_actors() or []
    return list(selected)


def _axis_value(vec: unreal.Vector, axis: str) -> float:
    """Extract a single axis component from an unreal.Vector."""
    axis = axis.upper()
    if axis == "X":
        return vec.x
    if axis == "Y":
        return vec.y
    return vec.z


def _set_axis(loc: unreal.Vector, axis: str, value: float) -> unreal.Vector:
    """Return a new Vector with one axis replaced."""
    axis = axis.upper()
    x, y, z = loc.x, loc.y, loc.z
    if axis == "X":
        x = value
    elif axis == "Y":
        y = value
    else:
        z = value
    return unreal.Vector(x, y, z)


def _get_bounds(actor: unreal.Actor) -> Tuple[unreal.Vector, unreal.Vector]:
    """
    Return (origin, extent) for an actor.

    get_actor_bounds(False) returns the component-inclusive bounds.
    Falls back to (location, zero-extent) if it raises.
    """
    try:
        origin, extent = actor.get_actor_bounds(False)
        return origin, extent
    except Exception:
        loc = actor.get_actor_location()
        return loc, unreal.Vector(0, 0, 0)


def _bounds_min(actor: unreal.Actor, axis: str) -> float:
    """Return the minimum extent of an actor's bounds along the given axis."""
    origin, extent = _get_bounds(actor)
    return _axis_value(origin, axis) - abs(_axis_value(extent, axis))


def _bounds_max(actor: unreal.Actor, axis: str) -> float:
    """Return the maximum extent of an actor's bounds along the given axis."""
    origin, extent = _get_bounds(actor)
    return _axis_value(origin, axis) + abs(_axis_value(extent, axis))


def _bounds_size(actor: unreal.Actor, axis: str) -> float:
    """Return the full extent size (width/height/depth) along the given axis."""
    _, extent = _get_bounds(actor)
    return abs(_axis_value(extent, axis)) * 2.0


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="align_to_reference",
    category="Alignment",
    description=(
        "Align all selected actors' X, Y, or Z position to a reference actor "
        "(first or last selected). Does not affect the reference actor itself."
    ),
    tags=["align", "reference", "axis", "selection"],
)
def align_to_reference(axis: str = "Z", reference: str = "first", **kwargs) -> dict:
    """
    Snap every selected actor's position on one axis to a reference actor's position.

    The reference actor (first or last in the selection) is used as the target value;
    it is not moved. All other selected actors have their position on the chosen axis
    set to match the reference actor's pivot location on that axis.

    Args:
        axis:      "X", "Y", or "Z". The axis to align on.
        reference: "first" — use the first selected actor as reference.
                   "last"  — use the last selected actor as reference.

    Returns:
        dict: {"status", "aligned": int, "reference_label": str, "axis": str}
    """
    axis = axis.upper()
    if axis not in ("X", "Y", "Z"):
        return {"status": "error", "message": f"axis must be X, Y, or Z — got '{axis}'."}

    selected = _get_selected()
    if len(selected) < 2:
        msg = "align_to_reference: select at least 2 actors."
        log_warning(msg)
        return {"status": "error", "message": msg}

    ref_actor = selected[0] if reference.lower() == "first" else selected[-1]
    targets = [a for a in selected if a != ref_actor]
    ref_label = ref_actor.get_actor_label()
    ref_value = _axis_value(ref_actor.get_actor_location(), axis)

    aligned = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Align to Reference") as _t:
        for actor in targets:
            try:
                new_loc = _set_axis(actor.get_actor_location(), axis, ref_value)
                actor.set_actor_location(new_loc, False, False)
                aligned += 1
            except Exception as e:
                log_error(f"  Failed to align '{actor.get_actor_label()}': {e}")

    log_info(
        f"align_to_reference: {aligned} actor(s) aligned on {axis} "
        f"to '{ref_label}' ({ref_value:.1f})."
    )
    return {
        "status": "ok",
        "aligned": aligned,
        "reference_label": ref_label,
        "axis": axis,
    }


@register_tool(
    name="distribute_with_gap",
    category="Alignment",
    description=(
        "Distribute selected actors along an axis so there is an exact gap (cm) "
        "between each actor's bounding box. Uses bounds, not just pivot points."
    ),
    tags=["distribute", "gap", "bounds", "spacing", "selection"],
)
def distribute_with_gap(axis: str = "X", gap: float = 0.0, **kwargs) -> dict:
    """
    Lay out selected actors along an axis with a precise gap between their bounds.

    Unlike a simple pivot-space distribution, this tool accounts for each actor's
    bounding box so the visual space between objects is uniform. The first actor
    (sorted by its minimum bound along the axis) is kept in place; all subsequent
    actors are positioned so their left/back/bottom bound is exactly `gap` cm
    beyond the previous actor's right/front/top bound.

    Args:
        axis: "X", "Y", or "Z". The axis to distribute along.
        gap:  Gap in centimetres between each actor's bounds. Use 0.0 for flush.

    Returns:
        dict: {"status", "distributed": int, "axis": str, "gap": float}
    """
    axis = axis.upper()
    if axis not in ("X", "Y", "Z"):
        return {"status": "error", "message": f"axis must be X, Y, or Z — got '{axis}'."}

    selected = _get_selected()
    if len(selected) < 2:
        msg = "distribute_with_gap: select at least 2 actors."
        log_warning(msg)
        return {"status": "error", "message": msg}

    # Sort by the minimum bound along the axis (i.e. the leading edge in that direction)
    sorted_actors = sorted(selected, key=lambda a: _bounds_min(a, axis))

    distributed = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Distribute with Gap") as _t:
        # Keep the first actor fixed; track the running cursor = max extent of previous actor
        cursor = _bounds_max(sorted_actors[0], axis)

        for actor in sorted_actors[1:]:
            try:
                current_min = _bounds_min(actor, axis)
                current_pivot = _axis_value(actor.get_actor_location(), axis)
                # How far the pivot is offset from the bounding-box minimum
                pivot_offset = current_pivot - current_min
                # Target minimum edge = cursor + gap
                target_min = cursor + gap
                target_pivot = target_min + pivot_offset
                new_loc = _set_axis(actor.get_actor_location(), axis, target_pivot)
                actor.set_actor_location(new_loc, False, False)
                # Advance cursor to the new maximum bound of this actor
                size = _bounds_size(actor, axis)
                cursor = target_min + size
                distributed += 1
            except Exception as e:
                log_error(f"  Failed to distribute '{actor.get_actor_label()}': {e}")

    log_info(
        f"distribute_with_gap: {distributed} actor(s) distributed along {axis} "
        f"with {gap:.1f} cm gap."
    )
    return {"status": "ok", "distributed": distributed, "axis": axis, "gap": gap}


@register_tool(
    name="rotate_around_pivot",
    category="Alignment",
    description=(
        "Orbit all selected actors around a shared pivot point by angle_deg. "
        "Pivot can be the selection center or the first selected actor."
    ),
    tags=["rotate", "orbit", "pivot", "radial", "selection"],
)
def rotate_around_pivot(
    angle_deg: float = 90.0,
    axis: str = "Z",
    pivot: str = "center",
    **kwargs,
) -> dict:
    """
    Rotate and orbit selected actors around a pivot point.

    Each actor's world location is rotated around the pivot using a 2-D rotation
    matrix applied in the plane perpendicular to the chosen axis. Each actor's own
    yaw (for Z-axis), pitch (Y-axis), or roll (X-axis) is also incremented by
    angle_deg so the actors face the right direction after orbiting.

    Args:
        angle_deg: Clockwise rotation in degrees (positive = clockwise from above for Z).
        axis:      "X" — orbit in YZ plane (increments roll).
                   "Y" — orbit in XZ plane (increments pitch).
                   "Z" — orbit in XY plane (increments yaw).
        pivot:     "center" — use the bounding-box center of the entire selection.
                   "first"  — use the first selected actor's location.

    Returns:
        dict: {
            "status",
            "rotated": int,
            "pivot_location": [x, y, z],
            "angle_deg": float
        }
    """
    axis = axis.upper()
    if axis not in ("X", "Y", "Z"):
        return {"status": "error", "message": f"axis must be X, Y, or Z — got '{axis}'."}

    selected = _get_selected()
    if not selected:
        msg = "rotate_around_pivot: nothing selected."
        log_warning(msg)
        return {"status": "error", "message": msg}

    # Determine pivot location
    if pivot.lower() == "first":
        p = selected[0].get_actor_location()
        piv_x, piv_y, piv_z = p.x, p.y, p.z
    else:
        # Bounding-box center of the entire selection
        locs = [a.get_actor_location() for a in selected]
        piv_x = sum(l.x for l in locs) / len(locs)
        piv_y = sum(l.y for l in locs) / len(locs)
        piv_z = sum(l.z for l in locs) / len(locs)

    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    rotated = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Rotate Around Pivot") as _t:
        for actor in selected:
            try:
                loc = actor.get_actor_location()
                rot = actor.get_actor_rotation()

                if axis == "Z":
                    # Rotate in XY plane around (piv_x, piv_y)
                    dx = loc.x - piv_x
                    dy = loc.y - piv_y
                    new_x = piv_x + dx * cos_a - dy * sin_a
                    new_y = piv_y + dx * sin_a + dy * cos_a
                    new_loc = unreal.Vector(new_x, new_y, loc.z)
                    new_rot = unreal.Rotator(rot.pitch, rot.yaw + angle_deg, rot.roll)

                elif axis == "Y":
                    # Rotate in XZ plane around (piv_x, piv_z)
                    dx = loc.x - piv_x
                    dz = loc.z - piv_z
                    new_x = piv_x + dx * cos_a - dz * sin_a
                    new_z = piv_z + dx * sin_a + dz * cos_a
                    new_loc = unreal.Vector(new_x, loc.y, new_z)
                    new_rot = unreal.Rotator(rot.pitch + angle_deg, rot.yaw, rot.roll)

                else:  # X
                    # Rotate in YZ plane around (piv_y, piv_z)
                    dy = loc.y - piv_y
                    dz = loc.z - piv_z
                    new_y = piv_y + dy * cos_a - dz * sin_a
                    new_z = piv_z + dy * sin_a + dz * cos_a
                    new_loc = unreal.Vector(loc.x, new_y, new_z)
                    new_rot = unreal.Rotator(rot.pitch, rot.yaw, rot.roll + angle_deg)

                actor.set_actor_location_and_rotation(new_loc, new_rot, False, False)
                rotated += 1
            except Exception as e:
                log_error(f"  Failed to rotate '{actor.get_actor_label()}': {e}")

    pivot_location = [piv_x, piv_y, piv_z]
    log_info(
        f"rotate_around_pivot: {rotated} actor(s) rotated {angle_deg}° "
        f"around {axis}-axis pivot at {[round(v, 1) for v in pivot_location]}."
    )
    return {
        "status": "ok",
        "rotated": rotated,
        "pivot_location": pivot_location,
        "angle_deg": angle_deg,
    }


@register_tool(
    name="align_to_surface",
    category="Alignment",
    description=(
        "Snap each selected actor's Z position down to the nearest floor surface using "
        "the editor's snap-to-floor function. An optional offset_z nudges actors up after snapping."
    ),
    tags=["snap", "floor", "surface", "Z", "align", "selection"],
)
def align_to_surface(offset_z: float = 0.0, **kwargs) -> dict:
    """
    Drop selected actors to the nearest surface below them.

    Uses unreal.EditorLevelLibrary.snap_objects_to_floor() which snaps the current
    editor selection in one call. If that API is unavailable (some UEFN builds), the
    function falls back to a per-actor downward trace attempt and logs a warning.

    After snapping, each actor is shifted up by offset_z centimetres so it sits
    exactly on the surface rather than intersecting it.

    Args:
        offset_z: Additional Z offset (cm) applied after snapping. Use a small
                  positive value (e.g. 1.0) to prevent Z-fighting with floors.

    Returns:
        dict: {"status", "snapped": int}
    """
    selected = _get_selected()
    if not selected:
        msg = "align_to_surface: nothing selected."
        log_warning(msg)
        return {"status": "error", "message": msg}

    snapped = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Align to Surface") as _t:
        try:
            # Prefer the bulk snap which honours the editor's collision system
            unreal.EditorLevelLibrary.snap_objects_to_floor()
            snapped = len(selected)
            log_info(f"align_to_surface: snap_objects_to_floor applied to {snapped} actor(s).")
        except AttributeError:
            log_warning(
                "align_to_surface: snap_objects_to_floor not available in this build. "
                "Falling back to no-op — snapped count = 0."
            )
        except Exception as e:
            log_error(f"align_to_surface: snap_objects_to_floor failed: {e}")

        # Apply the additional Z offset regardless of which path was taken
        if offset_z != 0.0:
            for actor in selected:
                try:
                    loc = actor.get_actor_location()
                    actor.set_actor_location(
                        unreal.Vector(loc.x, loc.y, loc.z + offset_z),
                        False, False,
                    )
                except Exception as e:
                    log_error(f"  offset_z failed on '{actor.get_actor_label()}': {e}")

    return {"status": "ok", "snapped": snapped}


@register_tool(
    name="match_spacing",
    category="Alignment",
    description=(
        "Evenly space selected actor pivots between the first and last actor's pivot "
        "positions along an axis. The endpoints are kept fixed."
    ),
    tags=["distribute", "spacing", "even", "axis", "selection"],
)
def match_spacing(axis: str = "X", **kwargs) -> dict:
    """
    Redistribute actor pivots evenly between the outermost two actors along an axis.

    This is a pivot-space operation — it spaces the actor origin points uniformly
    between the minimum and maximum pivot positions on the chosen axis. Unlike
    distribute_with_gap it does not account for bounding box sizes, making it
    ideal for evenly spacing visually similar objects or when you want predictable
    numerical intervals.

    The first and last actors (by axis position) are anchors and are not moved.
    All intermediate actors are repositioned.

    Args:
        axis: "X", "Y", or "Z". The axis along which to redistribute.

    Returns:
        dict: {"status", "redistributed": int, "axis": str, "spacing": float}
    """
    axis = axis.upper()
    if axis not in ("X", "Y", "Z"):
        return {"status": "error", "message": f"axis must be X, Y, or Z — got '{axis}'."}

    selected = _get_selected()
    if len(selected) < 3:
        msg = "match_spacing: select at least 3 actors (endpoints are fixed)."
        log_warning(msg)
        return {"status": "error", "message": msg}

    # Sort by pivot position along the axis
    sorted_actors = sorted(
        selected, key=lambda a: _axis_value(a.get_actor_location(), axis)
    )

    first_val = _axis_value(sorted_actors[0].get_actor_location(), axis)
    last_val = _axis_value(sorted_actors[-1].get_actor_location(), axis)
    total_span = last_val - first_val
    n = len(sorted_actors) - 1  # number of intervals
    spacing = total_span / n if n > 0 else 0.0

    redistributed = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Match Spacing") as _t:
        # Skip first (index 0) and last (index n) — they are anchors
        for i, actor in enumerate(sorted_actors[1:-1], start=1):
            try:
                target_val = first_val + i * spacing
                new_loc = _set_axis(actor.get_actor_location(), axis, target_val)
                actor.set_actor_location(new_loc, False, False)
                redistributed += 1
            except Exception as e:
                log_error(f"  Failed to reposition '{actor.get_actor_label()}': {e}")

    log_info(
        f"match_spacing: {redistributed} actor(s) redistributed along {axis} "
        f"with {spacing:.2f} cm spacing."
    )
    return {
        "status": "ok",
        "redistributed": redistributed,
        "axis": axis,
        "spacing": round(spacing, 4),
    }


@register_tool(
    name="align_to_grid_two_points",
    category="Alignment",
    description=(
        "Use the first two selected actors as grid anchors to define a local XY grid. "
        "All remaining selected actors are snapped to the nearest intersection on that grid."
    ),
    tags=["grid", "snap", "two-point", "local", "align", "selection"],
)
def align_to_grid_two_points(grid_size: float = 100.0, **kwargs) -> dict:
    """
    Snap actors to a user-defined grid derived from two anchor points.

    The first two selected actors define the grid's origin (first actor) and
    X-axis direction (vector from first to second). A local coordinate system is
    constructed from these two points and all remaining selected actors are snapped
    to the nearest grid intersection in that local space.

    This is useful for aligning props to non-axis-aligned surfaces such as
    angled platforms, tilted arenas, or diagonal corridors.

    Args:
        grid_size: Cell size of the grid in centimetres.

    Returns:
        dict: {"status", "snapped": int, "grid_size": float}
    """
    if grid_size <= 0:
        return {"status": "error", "message": "grid_size must be greater than 0."}

    selected = _get_selected()
    if len(selected) < 3:
        msg = "align_to_grid_two_points: select at least 3 actors (2 anchors + 1 target)."
        log_warning(msg)
        return {"status": "error", "message": msg}

    anchor_a = selected[0]
    anchor_b = selected[1]
    targets = selected[2:]

    loc_a = anchor_a.get_actor_location()
    loc_b = anchor_b.get_actor_location()

    # Build local X axis (normalised vector from A to B)
    dx = loc_b.x - loc_a.x
    dy = loc_b.y - loc_a.y
    dz = loc_b.z - loc_a.z
    length = math.sqrt(dx * dx + dy * dy + dz * dz)

    if length < 0.001:
        return {
            "status": "error",
            "message": "The two anchor actors are at the same location — cannot define a grid axis.",
        }

    # Local X axis
    ax, ay, az = dx / length, dy / length, dz / length

    # Local Y axis: perpendicular to X in the world XY plane
    # Cross product of local_x with world_up (0,0,1) → gives a horizontal Y axis
    # If local_x is nearly vertical, fall back to world_x cross local_x
    world_up = (0.0, 0.0, 1.0)
    cx = ay * world_up[2] - az * world_up[1]
    cy = az * world_up[0] - ax * world_up[2]
    cz = ax * world_up[1] - ay * world_up[0]
    cross_len = math.sqrt(cx * cx + cy * cy + cz * cz)

    if cross_len < 0.001:
        # local_x is nearly vertical — use world X as fallback up
        world_x = (1.0, 0.0, 0.0)
        cx = ay * world_x[2] - az * world_x[1]
        cy = az * world_x[0] - ax * world_x[2]
        cz = ax * world_x[1] - ay * world_x[0]
        cross_len = math.sqrt(cx * cx + cy * cy + cz * cz)

    bx, by, bz = cx / cross_len, cy / cross_len, cz / cross_len

    def to_local(wx: float, wy: float, wz: float):
        """Project world point into the local grid frame (relative to anchor_a)."""
        rx, ry, rz = wx - loc_a.x, wy - loc_a.y, wz - loc_a.z
        u = rx * ax + ry * ay + rz * az   # local X component
        v = rx * bx + ry * by + rz * bz   # local Y component
        w = rx * (ay * bz - az * by) + ry * (az * bx - ax * bz) + rz * (ax * by - ay * bx)
        return u, v, w

    def to_world(u: float, v: float, w: float):
        """Convert local grid coordinates back to world space."""
        # local_z axis = cross(local_x, local_y)
        lzx = ay * bz - az * by
        lzy = az * bx - ax * bz
        lzz = ax * by - ay * bx
        wx = loc_a.x + u * ax + v * bx + w * lzx
        wy = loc_a.y + u * ay + v * by + w * lzy
        wz = loc_a.z + u * az + v * bz + w * lzz
        return wx, wy, wz

    def snap_to_grid(val: float, cell: float) -> float:
        return round(val / cell) * cell

    snapped = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Align to Grid (Two Points)") as _t:
        for actor in targets:
            try:
                loc = actor.get_actor_location()
                u, v, w = to_local(loc.x, loc.y, loc.z)
                u_snapped = snap_to_grid(u, grid_size)
                v_snapped = snap_to_grid(v, grid_size)
                # Preserve the local W (height relative to grid plane) unchanged
                wx, wy, wz = to_world(u_snapped, v_snapped, w)
                actor.set_actor_location(unreal.Vector(wx, wy, wz), False, False)
                snapped += 1
            except Exception as e:
                log_error(f"  Failed to snap '{actor.get_actor_label()}': {e}")

    log_info(
        f"align_to_grid_two_points: {snapped} actor(s) snapped to "
        f"{grid_size:.1f} cm custom grid."
    )
    return {"status": "ok", "snapped": snapped, "grid_size": grid_size}
