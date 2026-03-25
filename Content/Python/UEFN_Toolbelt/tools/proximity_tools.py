"""
UEFN TOOLBELT — Proximity & Relative Placement Tools
=====================================================
Move, duplicate, and arrange actors relative to each other using world-space bounds.
All operations are wrapped in ScopedEditorTransaction for full undo support.

OPERATIONS:
  actor_place_next_to    — Move last selected actor flush against the first (face-to-face with gap)
  actor_chain_place      — Arrange selected actors end-to-end along an axis using bounds
  actor_duplicate_offset — Duplicate selected actor(s) N times with exact cumulative offset
  actor_replace_class    — Replace all actors of a class with copies of a different asset
  actor_cluster_to_folder — Auto-group nearby actors into World Outliner subfolders
  actor_copy_to_positions — Duplicate selected actor at each position in a list

USAGE:
    import UEFN_Toolbelt as tb

    # Place second actor flush against the first on the +X face with 10 cm gap
    tb.run("actor_place_next_to", direction="+X", gap=10.0, align="center")

    # Stack selected actors end-to-end along Y axis
    tb.run("actor_chain_place", axis="Y", gap=5.0)

    # Duplicate selected actor 4 more times, 300 cm apart on X
    tb.run("actor_duplicate_offset", count=4, offset_x=300.0)

    # Replace all SM_OldRock actors with a new mesh (dry_run first!)
    tb.run("actor_replace_class", old_class_filter="OldRock",
           new_asset_path="/Game/Meshes/SM_NewRock", dry_run=True)
    tb.run("actor_replace_class", old_class_filter="OldRock",
           new_asset_path="/Game/Meshes/SM_NewRock", dry_run=False)

    # Auto-cluster all selected actors into folders by proximity
    tb.run("actor_cluster_to_folder", radius=800.0, folder_prefix="Zone", min_cluster_size=2)

    # Stamp selected actor at every position in a list
    tb.run("actor_copy_to_positions",
           positions=[[0,0,0],[500,0,0],[1000,0,100]],
           folder="Stamps")
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
    return list(_actor_sub().get_selected_level_actors() or [])


def _get_all_level_actors() -> List[unreal.Actor]:
    return list(_actor_sub().get_all_level_actors() or [])


def _get_bounds(actor: unreal.Actor) -> Tuple[unreal.Vector, unreal.Vector]:
    """Return (world_center, half_extents)."""
    return actor.get_actor_bounds(False)


def _axis_idx(axis: str) -> int:
    return {"X": 0, "Y": 1, "Z": 2}[axis.upper()]


def _vec_component(v: unreal.Vector, axis: str) -> float:
    return (v.x, v.y, v.z)[_axis_idx(axis)]


def _vec_set_component(v: unreal.Vector, axis: str, value: float) -> unreal.Vector:
    vals = [v.x, v.y, v.z]
    vals[_axis_idx(axis)] = value
    return unreal.Vector(*vals)


def _mesh_from_actor(actor: unreal.Actor):
    """Try to extract the static mesh object from a StaticMeshActor."""
    try:
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        if comp:
            return comp.get_editor_property("static_mesh")
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="actor_place_next_to",
    category="Proximity Tools",
    description=(
        "Select exactly two actors. Moves the LAST selected actor flush against the FIRST "
        "on the specified face. direction: '+X'/'-X'/'+Y'/'-Y'/'+Z'/'-Z'. "
        "gap adds cm of space between the bounds. "
        "align: 'center' centers the mover on the reference's bounds center; 'keep' keeps current Y/Z."
    ),
    tags=["placement", "adjacent", "next to", "snap", "face"],
)
def actor_place_next_to(
    direction: str = "+X",
    gap: float = 0.0,
    align: str = "center",
    **kwargs,
) -> dict:
    selected = _get_selected()
    if len(selected) < 2:
        return {"status": "error", "message": "Select exactly 2 actors — reference first, mover last."}

    reference = selected[0]
    mover = selected[-1]

    ref_center, ref_ext = _get_bounds(reference)
    mov_center, mov_ext = _get_bounds(mover)
    # Offset from mover's pivot to its bounds center
    mov_pivot = mover.get_actor_location()
    pivot_to_bounds = unreal.Vector(
        mov_pivot.x - mov_center.x,
        mov_pivot.y - mov_center.y,
        mov_pivot.z - mov_center.z,
    )

    direction = direction.strip()
    sign = 1.0 if direction.startswith("+") else -1.0
    axis = direction[-1].upper()

    # Face position of reference on that side
    ref_face = _vec_component(ref_center, axis) + sign * _vec_component(ref_ext, axis)
    # Desired bounds center of mover
    new_center_on_axis = ref_face + sign * (_vec_component(mov_ext, axis) + gap)

    # Build new pivot location
    new_pivot = mover.get_actor_location()
    # Primary axis: place bounds face
    new_pivot = _vec_set_component(new_pivot, axis,
                                   new_center_on_axis + _vec_component(pivot_to_bounds, axis))

    if align == "center":
        # Align other axes to reference bounds center
        for other_axis in ("X", "Y", "Z"):
            if other_axis == axis:
                continue
            ref_c = _vec_component(ref_center, other_axis)
            pb = _vec_component(pivot_to_bounds, other_axis)
            new_pivot = _vec_set_component(new_pivot, other_axis, ref_c + pb)

    with unreal.ScopedEditorTransaction("actor_place_next_to"):
        mover.set_actor_location(new_pivot, False, True)

    log_info(f"[PROXIMITY] '{mover.get_actor_label()}' placed {direction} of '{reference.get_actor_label()}' (gap={gap} cm)")
    return {
        "status": "ok",
        "reference": reference.get_actor_label(),
        "moved": mover.get_actor_label(),
        "direction": direction,
        "gap": gap,
    }


@register_tool(
    name="actor_chain_place",
    category="Proximity Tools",
    description=(
        "Arrange all selected actors end-to-end along an axis using their bounds — "
        "each actor's min face touches the previous actor's max face (plus optional gap). "
        "The first actor stays in place; all others are repositioned. "
        "Great for walls, corridors, fences, and rows of objects."
    ),
    tags=["chain", "end-to-end", "arrange", "row", "wall"],
)
def actor_chain_place(
    axis: str = "X",
    gap: float = 0.0,
    **kwargs,
) -> dict:
    selected = _get_selected()
    if len(selected) < 2:
        return {"status": "error", "message": "Select 2 or more actors to chain."}

    axis = axis.upper()

    # Sort actors by their current position on the axis
    actors = sorted(selected, key=lambda a: _vec_component(a.get_actor_location(), axis))

    with unreal.ScopedEditorTransaction("actor_chain_place"):
        first_center, first_ext = _get_bounds(actors[0])
        cursor = _vec_component(first_center, axis) + _vec_component(first_ext, axis)

        for actor in actors[1:]:
            act_center, act_ext = _get_bounds(actor)
            act_pivot = actor.get_actor_location()
            pivot_to_bounds_on_axis = _vec_component(act_pivot, axis) - _vec_component(act_center, axis)

            half = _vec_component(act_ext, axis)
            new_bounds_center_on_axis = cursor + gap + half
            new_pivot_on_axis = new_bounds_center_on_axis + pivot_to_bounds_on_axis

            new_loc = _vec_set_component(act_pivot, axis, new_pivot_on_axis)
            actor.set_actor_location(new_loc, False, True)
            cursor = new_bounds_center_on_axis + half

    log_info(f"[PROXIMITY] Chained {len(actors)} actors along {axis} axis with {gap} cm gap")
    return {
        "status": "ok",
        "actors_chained": len(actors),
        "axis": axis,
        "gap": gap,
    }


@register_tool(
    name="actor_duplicate_offset",
    category="Proximity Tools",
    description=(
        "Duplicate the selected actor(s) 'count' times, each copy offset from the previous "
        "by (offset_x, offset_y, offset_z) cm. "
        "Preserves rotation and scale. Works with StaticMeshActors."
    ),
    tags=["duplicate", "copy", "offset", "array", "repeat"],
)
def actor_duplicate_offset(
    count: int = 3,
    offset_x: float = 300.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    folder: str = "",
    **kwargs,
) -> dict:
    selected = _get_selected()
    if not selected:
        return {"status": "error", "message": "Select at least one actor to duplicate."}

    delta = unreal.Vector(offset_x, offset_y, offset_z)
    total_spawned = 0
    new_actors = []

    with unreal.ScopedEditorTransaction("actor_duplicate_offset"):
        for source in selected:
            mesh = _mesh_from_actor(source)
            if not mesh:
                log_warning(f"[PROXIMITY] '{source.get_actor_label()}' — not a StaticMeshActor, skipping")
                continue

            rot = source.get_actor_rotation()
            scale = source.get_actor_scale3d()
            base_loc = source.get_actor_location()
            src_folder = str(source.get_folder_path())
            dest_folder = folder or src_folder

            for i in range(1, count + 1):
                new_loc = unreal.Vector(
                    base_loc.x + delta.x * i,
                    base_loc.y + delta.y * i,
                    base_loc.z + delta.z * i,
                )
                new_actor = unreal.EditorLevelLibrary.spawn_actor_from_object(mesh, new_loc, rot)
                if new_actor:
                    new_actor.set_actor_scale3d(scale)
                    if dest_folder:
                        new_actor.set_folder_path(dest_folder)
                    new_actors.append(new_actor)
                    total_spawned += 1

    if new_actors:
        _actor_sub().set_selected_level_actors(new_actors)

    log_info(f"[PROXIMITY] Duplicated {len(selected)} actors × {count} = {total_spawned} new actors")
    return {
        "status": "ok",
        "source_count": len(selected),
        "copies_per_source": count,
        "total_spawned": total_spawned,
        "offset": [offset_x, offset_y, offset_z],
    }


@register_tool(
    name="actor_replace_class",
    category="Proximity Tools",
    description=(
        "Replace every actor in the level whose class name contains old_class_filter "
        "with a fresh instance of new_asset_path. Preserves transform, label, and folder. "
        "Always dry_run=True first to preview what will be replaced."
    ),
    tags=["replace", "swap", "class", "batch", "asset"],
)
def actor_replace_class(
    old_class_filter: str = "",
    new_asset_path: str = "",
    dry_run: bool = True,
    scope: str = "level",
    **kwargs,
) -> dict:
    if not old_class_filter:
        return {"status": "error", "message": "old_class_filter is required."}
    if not new_asset_path:
        return {"status": "error", "message": "new_asset_path is required."}

    filt = old_class_filter.lower()

    if scope == "selection":
        candidates = _get_selected()
    else:
        candidates = _get_all_level_actors()

    matches = [a for a in candidates if filt in type(a).__name__.lower() or filt in a.get_actor_label().lower()]

    if dry_run:
        labels = [a.get_actor_label() for a in matches]
        log_info(f"[REPLACE DRY RUN] Would replace {len(matches)} actors: {labels[:10]}{'...' if len(labels) > 10 else ''}")
        return {
            "status": "ok",
            "dry_run": True,
            "would_replace": len(matches),
            "labels": labels,
        }

    new_mesh = unreal.load_object(None, new_asset_path)
    if not new_mesh:
        return {"status": "error", "message": f"Asset not found: {new_asset_path}"}

    replaced = 0
    failed = 0
    with unreal.ScopedEditorTransaction("actor_replace_class"):
        for actor in matches:
            loc = actor.get_actor_location()
            rot = actor.get_actor_rotation()
            scale = actor.get_actor_scale3d()
            label = actor.get_actor_label()
            folder = str(actor.get_folder_path())

            _actor_sub().destroy_actor(actor)

            new_actor = unreal.EditorLevelLibrary.spawn_actor_from_object(new_mesh, loc, rot)
            if new_actor:
                new_actor.set_actor_scale3d(scale)
                new_actor.set_actor_label(label)
                if folder:
                    new_actor.set_folder_path(folder)
                replaced += 1
            else:
                log_warning(f"[REPLACE] Failed to respawn '{label}'")
                failed += 1

    log_info(f"[REPLACE] Replaced {replaced} actors with '{new_asset_path}' ({failed} failed)")
    return {
        "status": "ok",
        "replaced": replaced,
        "failed": failed,
        "new_asset": new_asset_path,
    }


@register_tool(
    name="actor_cluster_to_folder",
    category="Proximity Tools",
    description=(
        "Scan selected actors (or all level actors if nothing is selected) and "
        "group nearby actors into World Outliner subfolders based on XY proximity. "
        "Actors closer than 'radius' cm to a cluster seed get grouped together. "
        "Clusters smaller than min_cluster_size are left ungrouped."
    ),
    tags=["cluster", "group", "folder", "organize", "proximity"],
)
def actor_cluster_to_folder(
    radius: float = 800.0,
    folder_prefix: str = "Cluster",
    min_cluster_size: int = 2,
    base_folder: str = "",
    **kwargs,
) -> dict:
    selected = _get_selected()
    actors = selected if selected else _get_all_level_actors()

    if not actors:
        return {"status": "error", "message": "No actors found."}

    # Simple greedy XY-proximity clustering
    unclustered = list(range(len(actors)))
    clusters = []

    while unclustered:
        seed_idx = unclustered.pop(0)
        seed_loc = actors[seed_idx].get_actor_location()
        cluster = [seed_idx]

        still_unclustered = []
        for i in unclustered:
            loc = actors[i].get_actor_location()
            dist = math.sqrt((loc.x - seed_loc.x) ** 2 + (loc.y - seed_loc.y) ** 2)
            if dist <= radius:
                cluster.append(i)
            else:
                still_unclustered.append(i)
        unclustered = still_unclustered

        if len(cluster) >= min_cluster_size:
            clusters.append(cluster)

    # Assign folders
    clustered_count = 0
    with unreal.ScopedEditorTransaction("actor_cluster_to_folder"):
        for i, cluster in enumerate(clusters):
            folder_name = f"{base_folder}/{folder_prefix}_{i+1:02d}" if base_folder else f"{folder_prefix}_{i+1:02d}"
            for idx in cluster:
                actors[idx].set_folder_path(folder_name)
                clustered_count += 1

    log_info(f"[CLUSTER] {len(actors)} actors → {len(clusters)} clusters, {clustered_count} actors grouped")
    return {
        "status": "ok",
        "total_actors": len(actors),
        "clusters_formed": len(clusters),
        "actors_grouped": clustered_count,
        "radius": radius,
        "folder_prefix": folder_prefix,
    }


@register_tool(
    name="actor_copy_to_positions",
    category="Proximity Tools",
    description=(
        "Select one actor, then stamp copies of it at every position in the 'positions' list. "
        "Positions are [[x,y,z], [x,y,z], ...] in world cm. "
        "Preserves rotation and scale of the source actor. Works with StaticMeshActors."
    ),
    tags=["stamp", "copy", "positions", "batch", "spawn"],
    example='tb.run("actor_copy_to_positions", positions=[[0,0,0],[500,200,0],[1000,-100,50]], folder="Trees")',
)
def actor_copy_to_positions(
    positions: list = None,
    folder: str = "Stamps",
    copy_rotation: bool = True,
    copy_scale: bool = True,
    **kwargs,
) -> dict:
    if not positions:
        return {"status": "error", "message": "positions list is required, e.g. [[0,0,0],[500,0,0]]"}

    selected = _get_selected()
    if not selected:
        return {"status": "error", "message": "Select a source actor to copy."}

    source = selected[0]
    mesh = _mesh_from_actor(source)
    if not mesh:
        return {"status": "error", "message": f"'{source.get_actor_label()}' is not a StaticMeshActor."}

    rot = source.get_actor_rotation() if copy_rotation else unreal.Rotator(0, 0, 0)
    scale = source.get_actor_scale3d() if copy_scale else unreal.Vector(1, 1, 1)
    spawned = 0
    new_actors = []

    with unreal.ScopedEditorTransaction("actor_copy_to_positions"):
        for pos in positions:
            try:
                loc = unreal.Vector(float(pos[0]), float(pos[1]), float(pos[2]))
            except (IndexError, TypeError, ValueError) as e:
                log_warning(f"[STAMP] Invalid position {pos}: {e}")
                continue
            actor = unreal.EditorLevelLibrary.spawn_actor_from_object(mesh, loc, rot)
            if actor:
                if copy_scale:
                    actor.set_actor_scale3d(scale)
                if folder:
                    actor.set_folder_path(folder)
                new_actors.append(actor)
                spawned += 1

    if new_actors:
        _actor_sub().set_selected_level_actors(new_actors)

    log_info(f"[STAMP] Copied '{source.get_actor_label()}' to {spawned}/{len(positions)} positions")
    return {
        "status": "ok",
        "source": source.get_actor_label(),
        "positions_provided": len(positions),
        "spawned": spawned,
        "folder": folder,
    }
