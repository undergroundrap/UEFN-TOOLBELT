"""
UEFN TOOLBELT — Procedural Geometry
========================================
Consolidated tools for mathematically generating procedural actors in the world.

FEATURES:
  • Volumetric Scattering: Spawn hundreds of random assets inside cubic or spherical zones.
  • Hanging Wires: Draw physics-sagging procedural cables or cylinder strips between 2 actors.
"""

from __future__ import annotations

import math
import random
import unreal

from ..core import log_info, log_error, log_warning, with_progress
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Wire Math
# ─────────────────────────────────────────────────────────────────────────────

def _vec_sub(a: unreal.Vector, b: unreal.Vector) -> unreal.Vector:
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)

def _vec_len(v: unreal.Vector) -> float:
    return math.sqrt(v.x**2 + v.y**2 + v.z**2)

def _get_wire_curve_points(p0: unreal.Vector, p2: unreal.Vector, segments: int, sag: float) -> list[unreal.Vector]:
    pts = []
    sag = abs(sag)
    for i in range(segments + 1):
        t = float(i) / float(segments)
        bx, by, bz = p0.x + (p2.x - p0.x)*t, p0.y + (p2.y - p0.y)*t, p0.z + (p2.z - p0.z)*t
        gravity = 4.0 * t * (1.0 - t) * sag
        pts.append(unreal.Vector(bx, by, bz - gravity))
    return pts

# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="procedural_wire_create",
    category="Procedural",
    description="Draws a procedural, sagging wire/cable between exactly two selected actors.",
    tags=["wire", "cable", "procedural", "connect", "geometry"]
)
def run_procedural_wire_create(
    segments: int = 16,
    sag_amount: float = 120.0,
    thickness: float = 0.1,
    mesh_path: str = "/Engine/BasicShapes/Cylinder.Cylinder",
    **kwargs
) -> dict:
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = actor_sub.get_selected_level_actors()
    if len(selected) != 2:
        log_error("You must have exactly 2 actors selected in the Viewport to draw a wire between them.")
        return {"status": "error", "message": "Requires exactly 2 selected actors."}

    p0 = selected[0].get_actor_location()
    p2 = selected[1].get_actor_location()

    mesh_obj = unreal.load_asset(mesh_path)
    if not mesh_obj or not isinstance(mesh_obj, unreal.StaticMesh):
        log_error(f"Fallback geometry mesh not found: {mesh_path}")
        return {"status": "error", "message": f"Mesh not found: {mesh_path}"}

    bounds = mesh_obj.get_bounds().box_extent.x * 2.0
    if bounds <= 0.01: bounds = 1.0

    points = _get_wire_curve_points(p0, p2, max(2, segments), sag_amount)
    spawned = []

    with unreal.ScopedEditorTransaction("Procedural Wire (Segments)"):
        with with_progress(range(segments), "Drawing Wire Segments...") as bar:
            for i in bar:
                c0 = points[i]
                c1 = points[i+1]
                direction = _vec_sub(c1, c0)
                length = _vec_len(direction)

                if length <= 0.01: continue

                center = unreal.Vector((c0.x + c1.x)*0.5, (c0.y + c1.y)*0.5, (c0.z + c1.z)*0.5)
                rot = unreal.MathLibrary.make_rot_from_x(direction)

                a = actor_sub.spawn_actor_from_class(unreal.StaticMeshActor, center, rot)
                if a:
                    a.static_mesh_component.set_static_mesh(mesh_obj)
                    a.set_actor_scale3d(unreal.Vector(length / bounds, thickness, thickness))
                    # Group them together in the outliner
                    a.set_folder_path("ProceduralWires")
                    spawned.append(a)
                    
    log_info(f"Successfully drew a wire using {len(spawned)} procedural cylinders.")
    return {"status": "ok", "segments_created": len(spawned)}


@register_tool(
    name="procedural_volume_scatter",
    category="Procedural",
    description="Scatters a massive amount of random meshes within a spherical or cubic boundary.",
    tags=["scatter", "volume", "random", "mesh", "geometry"]
)
def run_procedural_volume_scatter(
    count: int = 50,
    radius: float = 1000.0,
    shape: str = "sphere",
    asset_path: str = "/Engine/BasicShapes/Cube.Cube",
    scale_min: float = 0.5,
    scale_max: float = 1.5,
    **kwargs
) -> dict:
    if count <= 0 or radius <= 0:
        log_error("count and radius must both be greater than 0.")
        return {"status": "error", "message": "Invalid spawn limits: count and radius must be > 0."}

    asset_obj = unreal.load_asset(asset_path)
    if not asset_obj:
        log_error(f"Asset not found: {asset_path}")
        return {"status": "error", "message": f"Asset not found: {asset_path}"}
        
    # Attempt to center around currently selected actor, otherwise absolute zero
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = actor_sub.get_selected_level_actors()
    center = selected[0].get_actor_location() if selected else unreal.Vector(0, 0, 0)

    spawned = 0
    with unreal.ScopedEditorTransaction(f"Volume Scatter {count}"):
        with with_progress(range(count), "Scattering Assets...") as bar:
            for _ in bar:
                # Calculate deterministic random offset
                if shape.lower() == "cube":
                    off = unreal.Vector(
                        random.uniform(-radius, radius),
                        random.uniform(-radius, radius),
                        random.uniform(-radius, radius)
                    )
                else:  # Sphere
                    dx = random.uniform(-1.0, 1.0)
                    dy = random.uniform(-1.0, 1.0)
                    dz = random.uniform(-1.0, 1.0)
                    length = math.sqrt(dx*dx + dy*dy + dz*dz) or 1.0
                    dist = (random.random() ** (1.0/3.0)) * radius
                    off = unreal.Vector((dx/length)*dist, (dy/length)*dist, (dz/length)*dist)

                loc = unreal.Vector(center.x + off.x, center.y + off.y, center.z + off.z)
                sc = random.uniform(scale_min, scale_max)

                a = actor_sub.spawn_actor_from_class(unreal.StaticMeshActor, loc, unreal.Rotator(0, 0, 0))
                if a:
                    a.static_mesh_component.set_static_mesh(asset_obj)
                    a.set_actor_scale3d(unreal.Vector(sc, sc, sc))
                    a.set_folder_path("ProceduralScatter")
                    spawned += 1
                    
    log_info(f"Successfully scattered {spawned} meshes into the {shape} volume.")
    return {"status": "ok", "count": spawned}
