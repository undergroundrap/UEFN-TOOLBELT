"""
UEFN TOOLBELT — Zone Tools
============================
Spawn, resize, query, and populate zone volumes in the level.
Works with any box-shaped actor as a zone reference — spawn your own marker cubes
or use existing actors (Mutator Zones, Trigger Volumes, box meshes, etc.) as the zone.

CONVENTION: "zone actor" = the first selected actor when running zone_resize_to_selection,
zone_select_contents, zone_move_contents, and zone_fill_scatter. Everything else in the
selection (or all level actors) is treated as contents.

OPERATIONS:
  zone_spawn               — Spawn a visible cube zone marker at camera position
  zone_resize_to_selection — Resize the zone actor to exactly contain all other selected actors
  zone_snap_to_selection   — Move zone center to match selection bounds (no resize)
  zone_select_contents     — Select all level actors whose pivot is inside the zone's bounds
  zone_move_contents       — Move zone + all actors inside it by a world-space offset
  zone_fill_scatter        — Fill zone volume with scattered copies of an asset
  zone_list                — List every actor in the "Zones" folder with bounds info

USAGE:
    import UEFN_Toolbelt as tb

    tb.run("zone_spawn", width=3000, depth=3000, height=600, label="PlayZone")
    # select zone actor first, then other actors:
    tb.run("zone_resize_to_selection", padding=100.0)
    tb.run("zone_snap_to_selection")
    # select zone actor only:
    tb.run("zone_select_contents")
    tb.run("zone_move_contents", offset_x=1000)
    tb.run("zone_fill_scatter", asset_path="/Engine/BasicShapes/Cube", count=30, seed=42)
    tb.run("zone_list")
"""

from __future__ import annotations

import math
import random
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
    return list(_actor_sub().get_selected_level_actors() or [])


def _get_all_level_actors() -> List[unreal.Actor]:
    return list(_actor_sub().get_all_level_actors() or [])


def _cam_loc() -> unreal.Vector:
    try:
        loc, _ = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
        return loc
    except Exception:
        return unreal.Vector(0, 0, 0)


def _get_actor_bounds(actor: unreal.Actor) -> Tuple[unreal.Vector, unreal.Vector]:
    """Return (world_center, half_extents) for the actor's bounding box."""
    return actor.get_actor_bounds(False)


def _vec_add(a: unreal.Vector, b: unreal.Vector) -> unreal.Vector:
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def _vec_sub(a: unreal.Vector, b: unreal.Vector) -> unreal.Vector:
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def _combined_bounds(actors: List[unreal.Actor]) -> Tuple[unreal.Vector, unreal.Vector]:
    """Compute the combined bounding box of a list of actors.
    Returns (center, half_extents)."""
    mins = [float("inf")] * 3
    maxs = [float("-inf")] * 3
    for a in actors:
        c, e = _get_actor_bounds(a)
        mins[0] = min(mins[0], c.x - e.x)
        mins[1] = min(mins[1], c.y - e.y)
        mins[2] = min(mins[2], c.z - e.z)
        maxs[0] = max(maxs[0], c.x + e.x)
        maxs[1] = max(maxs[1], c.y + e.y)
        maxs[2] = max(maxs[2], c.z + e.z)
    cx = (mins[0] + maxs[0]) / 2
    cy = (mins[1] + maxs[1]) / 2
    cz = (mins[2] + maxs[2]) / 2
    ex = (maxs[0] - mins[0]) / 2
    ey = (maxs[1] - mins[1]) / 2
    ez = (maxs[2] - mins[2]) / 2
    return unreal.Vector(cx, cy, cz), unreal.Vector(ex, ey, ez)


def _point_in_bounds(
    point: unreal.Vector,
    center: unreal.Vector,
    half_ext: unreal.Vector,
    expand: float = 0.0,
) -> bool:
    return (
        abs(point.x - center.x) <= half_ext.x + expand
        and abs(point.y - center.y) <= half_ext.y + expand
        and abs(point.z - center.z) <= half_ext.z + expand
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="zone_spawn",
    category="Zone Tools",
    description=(
        "Spawn a visible cube zone marker at the camera position. "
        "Use with zone_resize_to_selection, zone_select_contents, etc. "
        "width/depth/height are in cm."
    ),
    tags=["zone", "spawn", "volume", "mutator"],
    example='tb.run("zone_spawn", width=4000, depth=4000, height=800, label="ArenaCenter")',
)
def zone_spawn(
    width: float = 1000.0,
    depth: float = 1000.0,
    height: float = 500.0,
    label: str = "Zone",
    focus: bool = False,
    **kwargs,
) -> dict:
    origin = _cam_loc()

    # Spawn cube mesh as zone marker
    cube_mesh = unreal.load_object(None, "/Engine/BasicShapes/Cube.Cube")
    if not cube_mesh:
        return {"status": "error", "message": "Could not load /Engine/BasicShapes/Cube"}

    with unreal.ScopedEditorTransaction("zone_spawn"):
        actor = unreal.EditorLevelLibrary.spawn_actor_from_object(cube_mesh, origin)
        if not actor:
            return {"status": "error", "message": "spawn_actor_from_object returned None"}

        # Cube default is 100x100x100 cm — scale to desired size
        actor.set_actor_scale3d(unreal.Vector(width / 100.0, depth / 100.0, height / 100.0))
        actor.set_actor_label(label)
        actor.set_folder_path("Zones")

    log_info(f"[ZONE] Spawned '{label}' at {origin.x:.0f},{origin.y:.0f},{origin.z:.0f} "
             f"({width:.0f}×{depth:.0f}×{height:.0f} cm)")
    if focus:
        try:
            unreal.get_editor_subsystem(unreal.EditorActorSubsystem).set_selected_level_actors([actor])
            unreal.SystemLibrary.execute_console_command(
                unreal.EditorLevelLibrary.get_editor_world(), "CAMERA ALIGN"
            )
        except Exception:
            pass
    return {
        "status": "ok",
        "label": label,
        "width": width,
        "depth": depth,
        "height": height,
        "location": [origin.x, origin.y, origin.z],
    }


@register_tool(
    name="zone_resize_to_selection",
    category="Zone Tools",
    description=(
        "Select a zone actor first, then select all actors you want it to contain. "
        "Resizes and repositions the zone to exactly fit all other selected actors. "
        "padding adds cm of extra space on all sides."
    ),
    tags=["zone", "resize", "bounds", "fit"],
)
def zone_resize_to_selection(padding: float = 50.0, **kwargs) -> dict:
    selected = _get_selected()
    if len(selected) < 2:
        return {"status": "error", "message": "Select the zone actor first, then the actors it should contain (2+ actors required)."}

    zone = selected[0]
    contents = selected[1:]

    center, half_ext = _combined_bounds(contents)
    # Add padding
    half_ext = unreal.Vector(
        half_ext.x + padding,
        half_ext.y + padding,
        half_ext.z + padding,
    )
    # Width/Depth/Height from half_extents (cube mesh is 100cm at scale 1.0)
    new_scale = unreal.Vector(
        (half_ext.x * 2) / 100.0,
        (half_ext.y * 2) / 100.0,
        (half_ext.z * 2) / 100.0,
    )

    with unreal.ScopedEditorTransaction("zone_resize_to_selection"):
        zone.set_actor_location(center, False, True)
        zone.set_actor_scale3d(new_scale)

    w = half_ext.x * 2
    d = half_ext.y * 2
    h = half_ext.z * 2
    log_info(f"[ZONE] '{zone.get_actor_label()}' resized to {w:.0f}×{d:.0f}×{h:.0f} cm, covering {len(contents)} actors")
    return {
        "status": "ok",
        "zone": zone.get_actor_label(),
        "actors_covered": len(contents),
        "width": w,
        "depth": d,
        "height": h,
        "center": [center.x, center.y, center.z],
    }


@register_tool(
    name="zone_snap_to_selection",
    category="Zone Tools",
    description=(
        "Select a zone actor first, then the actors to center it on. "
        "Moves the zone center to match the combined bounds center WITHOUT resizing. "
        "Useful for repositioning a zone while keeping its current size."
    ),
    tags=["zone", "snap", "center", "move"],
)
def zone_snap_to_selection(**kwargs) -> dict:
    selected = _get_selected()
    if len(selected) < 2:
        return {"status": "error", "message": "Select zone actor first, then at least one target actor."}

    zone = selected[0]
    contents = selected[1:]
    center, _ = _combined_bounds(contents)

    with unreal.ScopedEditorTransaction("zone_snap_to_selection"):
        zone.set_actor_location(center, False, True)

    log_info(f"[ZONE] '{zone.get_actor_label()}' snapped to center {center.x:.0f},{center.y:.0f},{center.z:.0f}")
    return {
        "status": "ok",
        "zone": zone.get_actor_label(),
        "new_center": [center.x, center.y, center.z],
    }


@register_tool(
    name="zone_select_contents",
    category="Zone Tools",
    description=(
        "Select a zone actor in the viewport, then run this tool. "
        "Finds and selects every level actor whose pivot point falls inside the zone's bounds. "
        "expand adds extra cm to the detection radius on all sides."
    ),
    tags=["zone", "select", "contents", "inside"],
)
def zone_select_contents(expand: float = 0.0, **kwargs) -> dict:
    selected = _get_selected()
    if not selected:
        return {"status": "error", "message": "Select a zone actor first."}

    zone = selected[0]
    zone_center, zone_ext = _get_actor_bounds(zone)

    all_actors = _get_all_level_actors()
    inside = [
        a for a in all_actors
        if a != zone and _point_in_bounds(a.get_actor_location(), zone_center, zone_ext, expand)
    ]

    _actor_sub().set_selected_level_actors(inside)

    log_info(f"[ZONE] '{zone.get_actor_label()}' contains {len(inside)} actors")
    return {
        "status": "ok",
        "zone": zone.get_actor_label(),
        "actors_found": len(inside),
        "actor_labels": [a.get_actor_label() for a in inside],
    }


@register_tool(
    name="zone_move_contents",
    category="Zone Tools",
    description=(
        "Select a zone actor, then run this tool to move the zone AND all actors "
        "whose pivot is inside it by the given world-space offset (cm). "
        "Keeps the zone and its contents locked together."
    ),
    tags=["zone", "move", "offset", "translate"],
)
def zone_move_contents(
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    **kwargs,
) -> dict:
    selected = _get_selected()
    if not selected:
        return {"status": "error", "message": "Select a zone actor first."}

    zone = selected[0]
    zone_center, zone_ext = _get_actor_bounds(zone)
    delta = unreal.Vector(offset_x, offset_y, offset_z)

    all_actors = _get_all_level_actors()
    inside = [
        a for a in all_actors
        if a != zone and _point_in_bounds(a.get_actor_location(), zone_center, zone_ext)
    ]

    with unreal.ScopedEditorTransaction("zone_move_contents"):
        # Move the zone
        z_loc = zone.get_actor_location()
        zone.set_actor_location(_vec_add(z_loc, delta), False, True)
        # Move all contents
        for actor in inside:
            loc = actor.get_actor_location()
            actor.set_actor_location(_vec_add(loc, delta), False, True)

    total = len(inside) + 1  # zone + contents
    log_info(f"[ZONE] Moved '{zone.get_actor_label()}' + {len(inside)} actors by ({offset_x:.0f},{offset_y:.0f},{offset_z:.0f})")
    return {
        "status": "ok",
        "zone": zone.get_actor_label(),
        "actors_moved": total,
        "offset": [offset_x, offset_y, offset_z],
    }


@register_tool(
    name="zone_fill_scatter",
    category="Zone Tools",
    description=(
        "Select a zone actor, then scatter copies of an asset randomly inside its volume. "
        "Uses Poisson-disk-style placement to avoid clumping. "
        "asset_path must be a Content Browser path like /Engine/BasicShapes/Cube."
    ),
    tags=["zone", "fill", "scatter", "procedural"],
)
def zone_fill_scatter(
    asset_path: str = "/Engine/BasicShapes/Cube",
    count: int = 20,
    seed: int = 42,
    min_spacing: float = 0.0,
    folder: str = "ZoneFill",
    **kwargs,
) -> dict:
    selected = _get_selected()
    if not selected:
        return {"status": "error", "message": "Select a zone actor first."}

    zone = selected[0]
    zone_center, zone_ext = _get_actor_bounds(zone)

    mesh = unreal.load_object(None, asset_path)
    if not mesh:
        return {"status": "error", "message": f"Asset not found: {asset_path}"}

    rng = random.Random(seed)

    def _random_in_zone() -> unreal.Vector:
        return unreal.Vector(
            zone_center.x + rng.uniform(-zone_ext.x, zone_ext.x),
            zone_center.y + rng.uniform(-zone_ext.y, zone_ext.y),
            zone_center.z + rng.uniform(-zone_ext.z, zone_ext.z),
        )

    placed_locs: List[unreal.Vector] = []
    spawned = 0
    attempts = 0
    max_attempts = count * 20

    with unreal.ScopedEditorTransaction("zone_fill_scatter"):
        while spawned < count and attempts < max_attempts:
            attempts += 1
            candidate = _random_in_zone()
            # Check min_spacing
            if min_spacing > 0:
                too_close = any(
                    math.sqrt(
                        (candidate.x - p.x) ** 2
                        + (candidate.y - p.y) ** 2
                        + (candidate.z - p.z) ** 2
                    ) < min_spacing
                    for p in placed_locs
                )
                if too_close:
                    continue

            actor = unreal.EditorLevelLibrary.spawn_actor_from_object(mesh, candidate)
            if actor:
                actor.set_folder_path(folder)
                placed_locs.append(candidate)
                spawned += 1

    log_info(f"[ZONE] Filled '{zone.get_actor_label()}' with {spawned} actors")
    return {
        "status": "ok",
        "zone": zone.get_actor_label(),
        "spawned": spawned,
        "requested": count,
        "folder": folder,
    }


@register_tool(
    name="zone_list",
    category="Zone Tools",
    description=(
        "List all actors in the 'Zones' World Outliner folder with their bounds, "
        "center position, and dimensions in cm."
    ),
    tags=["zone", "list", "audit"],
)
def zone_list(**kwargs) -> dict:
    all_actors = _get_all_level_actors()
    zones = []
    for actor in all_actors:
        folder = str(actor.get_folder_path())
        if folder == "Zones" or actor.get_actor_label().lower().startswith("zone"):
            center, ext = _get_actor_bounds(actor)
            zones.append({
                "label": actor.get_actor_label(),
                "folder": folder,
                "center": [round(center.x), round(center.y), round(center.z)],
                "width":  round(ext.x * 2),
                "depth":  round(ext.y * 2),
                "height": round(ext.z * 2),
            })

    for z in zones:
        log_info(
            f"[ZONE] {z['label']:30s}  "
            f"{z['width']}×{z['depth']}×{z['height']} cm  "
            f"@ ({z['center'][0]},{z['center'][1]},{z['center'][2]})"
        )

    if not zones:
        log_info("[ZONE] No zone actors found. Spawn one with zone_spawn or name an actor 'Zone...'")

    return {"status": "ok", "count": len(zones), "zones": zones}
