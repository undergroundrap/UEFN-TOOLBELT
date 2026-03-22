"""
UEFN TOOLBELT — Foliage & Scatter Tools
========================================
Procedural prop and foliage placement tools. The community has been asking
for this since day one of the Python update — placing rocks, trees, debris, or
any prop naturally across a map used to require hours of manual drag-and-drop.

APPROACH:
  Two placement modes are available:

  1. StaticMesh Scatter (always works)
     Spawns individual StaticMeshActors grouped under a folder. Each one is
     a real level actor — selectable, moveable, undoable. Slightly heavier
     than foliage instances but fully compatible with all UEFN workflows.

  2. Hierarchical Instanced Scatter (performant)
     Spawns a single actor with a HierarchicalInstancedStaticMeshComponent
     (HISM) holding thousands of instances in one draw call. Best for dense
     coverage (grass, pebbles, debris fields). The whole cluster undoes as
     one actor.

FEATURES:
  • Scatter N props in a radius with deterministic seeding (reproducible results)
  • Surface-conform: trace downward to snap instances to the terrain
  • Controlled density: set radius, count, min-separation, scale/rot variance
  • Cluster scatter: drop multiple clusters across a path or spline
  • Seed-based "nature noise" placement using Poisson-disk-style rejection
  • Clear scatter by folder — fast batch delete
  • Export scatter manifest (positions, rotations) to JSON for external tools
  • Full undo on every operation

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Scatter 200 rocks in a 5000cm radius around the origin
    tb.run("scatter_props",
           mesh_path="/Game/MyAssets/SM_Rock",
           count=200,
           radius=5000.0,
           center=(0, 0, 0),
           seed=42)

    # Dense foliage using HISM (one actor, thousands of instances)
    tb.run("scatter_hism",
           mesh_path="/Game/MyAssets/SM_Grass",
           count=2000,
           radius=8000.0,
           center=(0, 0, 0))

    # Scatter along a path of points (e.g., extracted from a spline)
    tb.run("scatter_along_path",
           mesh_path="/Game/MyAssets/SM_Tree",
           path_points=[(0,0,0),(1000,500,0),(2000,200,0)],
           spread=400.0,
           count_per_point=5)

    # Delete all scatter actors in a named folder
    tb.run("scatter_clear", folder="Scatter_Rocks")

    # Export scatter positions to JSON
    tb.run("scatter_export_manifest", folder="Scatter_Rocks")

BLUEPRINT:
    "Execute Python Command" →
        import UEFN_Toolbelt as tb; tb.run("scatter_props", mesh_path="/Game/Assets/SM_Rock", count=100, radius=3000.0)
"""

from __future__ import annotations

import json
import math
import os
import random
from typing import List, Optional, Tuple

import unreal

from ..core import (
    undo_transaction, log_info, log_warning, log_error,
    load_asset, spawn_static_mesh_actor, with_progress,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_SCATTER_FOLDER = "ToolbeltScatter"

# ─────────────────────────────────────────────────────────────────────────────
#  Placement math
# ─────────────────────────────────────────────────────────────────────────────

def _poisson_disk_2d(
    count: int,
    radius: float,
    min_dist: float,
    rng: random.Random,
) -> List[Tuple[float, float]]:
    """
    Generate `count` 2D points within a circle of `radius` using
    rejection sampling with a minimum separation of `min_dist`.

    Falls back to pure random if min_dist constraints can't be met
    after 30 attempts per point (prevents infinite loops on dense fills).
    """
    points: List[Tuple[float, float]] = []
    max_attempts = 30

    for _ in range(count):
        for attempt in range(max_attempts):
            # Random point inside circle
            angle = rng.uniform(0, math.tau)
            r     = math.sqrt(rng.uniform(0, 1)) * radius
            x, y  = r * math.cos(angle), r * math.sin(angle)

            # Check minimum separation from all existing points
            if all(
                math.hypot(x - px, y - py) >= min_dist
                for px, py in points
            ):
                points.append((x, y))
                break
        else:
            # Could not satisfy min_dist — place anyway (graceful degradation)
            angle = rng.uniform(0, math.tau)
            r     = math.sqrt(rng.uniform(0, 1)) * radius
            points.append((r * math.cos(angle), r * math.sin(angle)))

    return points


def _surface_z(world_x: float, world_y: float, start_z: float = 50000.0) -> float:
    """
    Attempt a line trace downward to find the surface Z under (x, y).
    Returns start_z (passes through) if no hit is found.

    Note: unreal.SystemLibrary.line_trace_single requires a world context
    object. In editor context this may not be available — the function
    catches the failure gracefully and returns the fallback value.
    """
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        hit_result = unreal.HitResult()
        start = unreal.Vector(world_x, world_y, start_z)
        end   = unreal.Vector(world_x, world_y, -50000.0)
        hit   = unreal.SystemLibrary.line_trace_single(
            world_object=world,
            start=start,
            end=end,
            trace_channel=unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
            trace_complex=False,
            actors_to_ignore=[],
            draw_debug_type=unreal.DrawDebugTrace.NONE,
            out_hit=hit_result,
            ignore_self=True,
        )
        if hit:
            return hit_result.location.z
    except Exception:
        pass
    return 0.0  # fallback: place at Z=0


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="scatter_props",
    category="Procedural",
    description="Scatter StaticMesh props in a radius with natural-looking Poisson distribution.",
    tags=["scatter", "foliage", "props", "procedural", "random", "place"],
)
def run_scatter_props(
    mesh_path: str = "/Engine/BasicShapes/Sphere",
    count: int = 50,
    radius: float = 3000.0,
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    min_separation: float = 0.0,      # 0 = no minimum (pure random)
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    rot_yaw_range: float = 360.0,     # max random yaw deviation
    snap_to_surface: bool = False,    # trace downward to land on terrain
    seed: int = 0,                    # 0 = truly random; any other = deterministic
    folder: str = DEFAULT_SCATTER_FOLDER,
    **kwargs,
) -> dict:
    """
    Args:
        mesh_path:        Content path to the static mesh.
        count:            Number of instances to place.
        radius:           Scatter circle radius in cm.
        center:           (x, y, z) world center of the scatter circle.
        min_separation:   Minimum distance between any two instances (cm).
                          Set to 0 for pure random (faster on large counts).
        scale_min/max:    Uniform random scale range.
        rot_yaw_range:    Max random yaw rotation (degrees). Use 360 for full spin.
        snap_to_surface:  If True, trace downward to land instances on terrain/meshes.
        seed:             Random seed. Same seed + same params = same scatter every time.
        folder:           World Outliner folder name.
    """
    rng = random.Random(seed if seed != 0 else None)
    cx, cy, cz = center

    # Generate 2D distribution
    if min_separation > 0:
        points = _poisson_disk_2d(count, radius, min_separation, rng)
    else:
        points = [
            (math.sqrt(rng.random()) * radius * math.cos(a),
             math.sqrt(rng.random()) * radius * math.sin(a))
            for a in (rng.uniform(0, math.tau) for _ in range(count))
        ]

    log_info(f"Scattering {len(points)} instances of '{mesh_path.split('/')[-1]}'…")

    placed = 0
    with undo_transaction(f"Scatter Props: {count}× {mesh_path.split('/')[-1]}"):
        for i, (ox, oy) in enumerate(points):
            world_x = cx + ox
            world_y = cy + oy
            world_z = _surface_z(world_x, world_y) if snap_to_surface else cz

            loc = unreal.Vector(world_x, world_y, world_z)
            rot = unreal.Rotator(0, rng.uniform(-rot_yaw_range / 2, rot_yaw_range / 2), 0)
            s   = rng.uniform(scale_min, scale_max)
            scale = unreal.Vector(s, s, s)

            actor = spawn_static_mesh_actor(mesh_path, loc, rotation=rot, scale=scale)
            if actor:
                actor.set_folder_path(f"/{folder}")
                actor.set_actor_label(f"Scatter_{i:04d}")
                placed += 1

    log_info(f"Scatter complete: {placed} actors placed in '/{folder}'.")
    return {"status": "ok", "placed": placed, "folder": folder}


@register_tool(
    name="scatter_hism",
    category="Procedural",
    description="Scatter thousands of instances in one draw call using HISM (GPU-instanced).",
    tags=["scatter", "hism", "instanced", "foliage", "performant", "dense"],
)
def run_scatter_hism(
    mesh_path: str = "/Engine/BasicShapes/Sphere",
    count: int = 500,
    radius: float = 5000.0,
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale_min: float = 0.7,
    scale_max: float = 1.3,
    rot_yaw_range: float = 360.0,
    seed: int = 0,
    folder: str = DEFAULT_SCATTER_FOLDER,
    **kwargs,
) -> dict:
    """
    Places all instances inside a single actor with a
    HierarchicalInstancedStaticMeshComponent — one draw call, GPU-instanced,
    ideal for grass, pebbles, debris fields.

    The entire cluster undoes as one actor.

    Args:
        mesh_path:   Content path to the static mesh.
        count:       Total number of instances.
        radius:      Scatter circle radius in cm.
        center:      (x, y, z) world center.
        scale_min/max: Random scale range.
        rot_yaw_range: Max random yaw (degrees).
        seed:        Deterministic seed (0 = random).
        folder:      World Outliner folder.
    """
    mesh = load_asset(mesh_path)
    if not isinstance(mesh, unreal.StaticMesh):
        log_error(f"scatter_hism: '{mesh_path}' is not a valid StaticMesh.")
        return {"status": "error", "count": 0, "folder": folder}

    rng  = random.Random(seed if seed != 0 else None)
    cx, cy, cz = center

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    log_info(f"HISM scatter: {count} instances of '{mesh_path.split('/')[-1]}'…")

    with undo_transaction(f"Scatter HISM: {count}× {mesh_path.split('/')[-1]}"):
        # Spawn a plain Actor to host our HISM component
        host_actor = actor_sub.spawn_actor_from_class(
            unreal.Actor,
            unreal.Vector(cx, cy, cz),
            unreal.Rotator(0, 0, 0),
        )
        if host_actor is None:
            log_error("scatter_hism: failed to spawn host actor.")
            return {"status": "error", "count": 0, "folder": folder}

        host_actor.set_folder_path(f"/{folder}")
        host_actor.set_actor_label(f"HISM_Scatter_{mesh_path.split('/')[-1]}")

        # Attach component via Constructor
        hism = unreal.HierarchicalInstancedStaticMeshComponent(host_actor)
        hism.set_static_mesh(mesh)

        # Add all instances
        for _ in range(count):
            angle = rng.uniform(0, math.tau)
            r     = math.sqrt(rng.random()) * radius
            x, y  = cx + r * math.cos(angle), cy + r * math.sin(angle)
            yaw   = rng.uniform(-rot_yaw_range / 2, rot_yaw_range / 2)
            s     = rng.uniform(scale_min, scale_max)

            transform = unreal.Transform(
                location=unreal.Vector(x, y, cz),
                rotation=unreal.Rotator(0, yaw, 0),
                scale=unreal.Vector(s, s, s),
            )
            hism.add_instance(transform)

    log_info(f"HISM scatter complete: {count} instances in one actor.")
    return {"status": "ok", "count": count, "folder": folder}


@register_tool(
    name="scatter_along_path",
    category="Procedural",
    description="Scatter props along a list of world-space path points with spread.",
    tags=["scatter", "path", "spline", "cluster", "props"],
)
def run_scatter_along_path(
    mesh_path: str = "/Engine/BasicShapes/Cube",
    path_points: Optional[List[Tuple[float, float, float]]] = None,
    spread: float = 300.0,
    count_per_point: int = 3,
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    seed: int = 0,
    folder: str = DEFAULT_SCATTER_FOLDER,
    **kwargs,
) -> dict:
    """
    Drops a cluster of `count_per_point` instances around each point in
    `path_points`. Pair with spline_to_verse.py to get path points from
    an actual spline actor.

    Args:
        mesh_path:        Content path to static mesh.
        path_points:      List of (x, y, z) world positions.
        spread:           Random offset radius per cluster.
        count_per_point:  Instances per path point.
        scale_min/max:    Random scale range.
        seed:             Deterministic seed.
        folder:           World Outliner folder.
    """
    if not path_points:
        log_warning("scatter_along_path: no path_points provided.")
        return {"status": "error", "placed": 0}

    rng = random.Random(seed if seed != 0 else None)
    total = len(path_points) * count_per_point
    log_info(f"Scattering {total} props along {len(path_points)} path points…")

    with undo_transaction(f"Scatter Along Path: {total}×"):
        for pi, (px, py, pz) in enumerate(path_points):
            for ci in range(count_per_point):
                angle = rng.uniform(0, math.tau)
                r     = rng.uniform(0, spread)
                x, y  = px + r * math.cos(angle), py + r * math.sin(angle)
                yaw   = rng.uniform(0, 360)
                s     = rng.uniform(scale_min, scale_max)

                actor = spawn_static_mesh_actor(
                    mesh_path,
                    unreal.Vector(x, y, pz),
                    rotation=unreal.Rotator(0, yaw, 0),
                    scale=unreal.Vector(s, s, s),
                )
                if actor:
                    actor.set_folder_path(f"/{folder}")
                    actor.set_actor_label(f"PathScatter_{pi:03d}_{ci}")

    log_info(f"Path scatter complete: {total} props placed.")
    return {"status": "ok", "placed": total}


@register_tool(
    name="scatter_clear",
    category="Procedural",
    description="Delete all scatter actors in a named World Outliner folder (undoable).",
    tags=["scatter", "clear", "delete", "cleanup"],
)
def run_scatter_clear(folder: str = DEFAULT_SCATTER_FOLDER, **kwargs) -> dict:
    """
    Returns:
        dict: {"status", "deleted", "folder"}
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()

    to_delete = [
        a for a in all_actors
        if folder in str(a.get_folder_path() or "")
    ]

    if not to_delete:
        log_info(f"No actors found in folder '/{folder}'.")
        return {"status": "ok", "deleted": 0, "folder": folder}

    with undo_transaction(f"Scatter: Clear {folder}"):
        actor_sub.destroy_actors(to_delete)

    log_info(f"Cleared {len(to_delete)} scatter actors from '/{folder}'.")
    return {"status": "ok", "deleted": len(to_delete), "folder": folder}


@register_tool(
    name="scatter_export_manifest",
    category="Procedural",
    description="Export positions/rotations of all scatter actors in a folder to JSON.",
    tags=["scatter", "export", "manifest", "json"],
)
def run_scatter_export_manifest(folder: str = DEFAULT_SCATTER_FOLDER, **kwargs) -> dict:
    """
    Exports a JSON manifest of every actor in the scatter folder.
    Useful for recreating a scatter in another level or sharing with teammates.

    Returns:
        dict: {"status", "path", "count"}
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = [
        a for a in actor_sub.get_all_level_actors()
        if folder in (a.get_folder_path() or "")
    ]

    if not actors:
        log_info(f"No actors found in '/{folder}'.")
        return {"status": "ok", "path": "", "count": 0}

    records = []
    for a in actors:
        loc = a.get_actor_location()
        rot = a.get_actor_rotation()
        sc  = a.get_actor_scale3d()
        records.append({
            "label":    a.get_actor_label(),
            "class":    a.get_class().get_name(),
            "location": {"x": loc.x, "y": loc.y, "z": loc.z},
            "rotation": {"pitch": rot.pitch, "yaw": rot.yaw, "roll": rot.roll},
            "scale":    {"x": sc.x, "y": sc.y, "z": sc.z},
        })

    out_dir  = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    out_path = os.path.join(out_dir, f"scatter_manifest_{folder}.json")
    os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w") as f:
        json.dump({"folder": folder, "count": len(records), "instances": records},
                  f, indent=2)

    log_info(f"Manifest exported: {len(records)} actors → {out_path}")
    return {"status": "ok", "path": out_path, "count": len(records)}
