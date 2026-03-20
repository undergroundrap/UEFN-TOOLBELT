"""
UEFN TOOLBELT — prop_patterns.py
=========================================
Geometric prop placement — where foliage_tools gives organic scatter,
prop_patterns gives precision geometry.

Patterns (8 types):
  grid         — N×M rectangular grid
  circle       — evenly-spaced ring at a fixed radius
  arc          — partial ring between two angles
  spiral       — Archimedean spiral (radius grows with angle)
  line         — evenly spaced between two world points
  wave         — sine-wave path along an axis
  helix        — 3D screw (circle + vertical rise per turn)
  radial_rows  — concentric rings (dartboard / bullseye layout)

Rotation modes (all patterns support all modes):
  world_up     — no rotation, Z stays up (default)
  face_center  — each prop yaws toward the pattern center point
  face_tangent — each prop yaws along its path direction
  random       — independent random yaw per prop

Scale modes:
  uniform      — same scale everywhere
  random       — random scale within [scale_min, scale_max]
  gradient     — linearly interpolate scale from first to last actor

Preview mode:
  Pass preview=True to spawn a 1×1×1 cube marker at each point so you
  can inspect the layout before committing to an expensive mesh. All
  preview actors are tagged [PREVIEW] and cleared by pattern_clear(preview_only=True).

All operations are wrapped in undo_transaction() — one Ctrl+Z removes the batch.
"""

from __future__ import annotations

import math
import random as _random
from typing import List, Tuple

import unreal

from UEFN_Toolbelt.core import (
    undo_transaction,
    with_progress,
    spawn_static_mesh_actor,
    get_selected_actors,
)
from UEFN_Toolbelt.registry import register_tool

# ─── Constants ─────────────────────────────────────────────────────────────────

_PREVIEW_MESH   = "/Engine/BasicShapes/Sphere"
_FALLBACK_MESH  = "/Engine/BasicShapes/Cube"
_PREVIEW_TAG    = "TOOLBELT_PATTERN_PREVIEW"
_PATTERN_TAG    = "TOOLBELT_PATTERN"

_ACTOR_TAG_PROP = "tags"  # unreal.Actor editor property for actor tags

# ─── Math helpers ──────────────────────────────────────────────────────────────

Vec3 = Tuple[float, float, float]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vec_len(v: Vec3) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _yaw_toward(origin: Vec3, target: Vec3) -> float:
    """Return yaw angle (degrees) so origin faces target."""
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    return math.degrees(math.atan2(dy, dx))


def _tangent_yaw(prev: Vec3, nxt: Vec3) -> float:
    """Yaw along the direction from prev → nxt."""
    dx = nxt[0] - prev[0]
    dy = nxt[1] - prev[1]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


# ─── Rotation + scale resolvers ───────────────────────────────────────────────

def _resolve_rotation(
    idx: int,
    total: int,
    pos: Vec3,
    center: Vec3,
    prev_pos: Vec3 | None,
    next_pos: Vec3 | None,
    rotation_mode: str,
    rng: _random.Random,
    base_yaw: float = 0.0,
) -> unreal.Rotator:
    mode = rotation_mode.lower()
    if mode == "face_center":
        yaw = _yaw_toward(pos, center)
    elif mode == "face_tangent":
        p = prev_pos if prev_pos else pos
        n = next_pos if next_pos else pos
        yaw = _tangent_yaw(p, n)
    elif mode == "random":
        yaw = rng.uniform(0.0, 360.0)
    else:  # world_up
        yaw = base_yaw
    return unreal.Rotator(0.0, yaw, 0.0)


def _resolve_scale(
    idx: int,
    total: int,
    scale_mode: str,
    scale: float,
    scale_min: float,
    scale_max: float,
    rng: _random.Random,
) -> unreal.Vector:
    mode = scale_mode.lower()
    if mode == "random":
        s = rng.uniform(scale_min, scale_max)
    elif mode == "gradient":
        s = _lerp(scale_min, scale_max, idx / max(total - 1, 1))
    else:  # uniform
        s = scale
    return unreal.Vector(s, s, s)


# ─── Core spawn helper ─────────────────────────────────────────────────────────

def _spawn_pattern(
    points: List[Vec3],
    center: Vec3,
    mesh_path: str,
    rotation_mode: str,
    scale_mode: str,
    scale: float,
    scale_min: float,
    scale_max: float,
    preview: bool,
    seed: int,
    label: str,
) -> int:
    """
    Spawn actors at every point in `points`.
    Returns count of spawned actors.
    """
    rng = _random.Random(seed)
    use_mesh = _PREVIEW_MESH if preview else (mesh_path or _FALLBACK_MESH)
    tag = _PREVIEW_TAG if preview else _PATTERN_TAG
    total = len(points)
    spawned = 0

    with undo_transaction(label):
        with with_progress(list(range(total)), f"Spawning {label}…") as gen:
            for idx in gen:
                pos = points[idx]
                prev_p = points[idx - 1] if idx > 0 else None
                next_p = points[idx + 1] if idx < total - 1 else None

                rot = _resolve_rotation(
                    idx, total, pos, center, prev_p, next_p,
                    rotation_mode, rng,
                )
                scl = _resolve_scale(
                    idx, total, scale_mode, scale, scale_min, scale_max, rng,
                )

                loc = unreal.Vector(pos[0], pos[1], pos[2])
                actor = spawn_static_mesh_actor(use_mesh, loc, rot, scl)
                if actor:
                    try:
                        existing = list(actor.get_editor_property(_ACTOR_TAG_PROP))
                        existing.append(unreal.Name(tag))
                        actor.set_editor_property(_ACTOR_TAG_PROP, existing)
                    except Exception:
                        pass
                    spawned += 1

    mode_str = "[PREVIEW] " if preview else ""
    unreal.log(f"[Patterns] {mode_str}✓ {label}: {spawned}/{total} actors spawned.")
    if preview:
        unreal.log(f"[Patterns]   Run again with preview=False to place the real mesh.")
    return spawned


# ─── Pattern point generators ──────────────────────────────────────────────────

def _points_grid(
    cols: int, rows: int, spacing_x: float, spacing_y: float,
    origin: Vec3, center_origin: bool,
) -> Tuple[List[Vec3], Vec3]:
    offset_x = (cols - 1) * spacing_x / 2.0 if center_origin else 0.0
    offset_y = (rows - 1) * spacing_y / 2.0 if center_origin else 0.0
    pts = []
    for row in range(rows):
        for col in range(cols):
            x = origin[0] + col * spacing_x - offset_x
            y = origin[1] + row * spacing_y - offset_y
            z = origin[2]
            pts.append((x, y, z))
    cx = origin[0] + (cols - 1) * spacing_x / 2.0 - offset_x
    cy = origin[1] + (rows - 1) * spacing_y / 2.0 - offset_y
    return pts, (cx, cy, origin[2])


def _points_circle(
    count: int, radius: float, origin: Vec3, start_angle_deg: float,
) -> Tuple[List[Vec3], Vec3]:
    pts = []
    for i in range(count):
        angle = math.radians(start_angle_deg + 360.0 * i / count)
        x = origin[0] + radius * math.cos(angle)
        y = origin[1] + radius * math.sin(angle)
        pts.append((x, y, origin[2]))
    return pts, origin


def _points_arc(
    count: int, radius: float, origin: Vec3,
    start_angle_deg: float, end_angle_deg: float,
) -> Tuple[List[Vec3], Vec3]:
    pts = []
    for i in range(count):
        t = i / max(count - 1, 1)
        angle = math.radians(_lerp(start_angle_deg, end_angle_deg, t))
        x = origin[0] + radius * math.cos(angle)
        y = origin[1] + radius * math.sin(angle)
        pts.append((x, y, origin[2]))
    return pts, origin


def _points_spiral(
    count: int, turns: float, radius_start: float, radius_end: float,
    origin: Vec3, start_angle_deg: float,
) -> Tuple[List[Vec3], Vec3]:
    pts = []
    for i in range(count):
        t = i / max(count - 1, 1)
        angle = math.radians(start_angle_deg) + t * turns * 2.0 * math.pi
        r = _lerp(radius_start, radius_end, t)
        x = origin[0] + r * math.cos(angle)
        y = origin[1] + r * math.sin(angle)
        pts.append((x, y, origin[2]))
    return pts, origin


def _points_line(
    count: int, start: Vec3, end: Vec3,
) -> Tuple[List[Vec3], Vec3]:
    pts = []
    for i in range(count):
        t = i / max(count - 1, 1)
        pts.append((
            _lerp(start[0], end[0], t),
            _lerp(start[1], end[1], t),
            _lerp(start[2], end[2], t),
        ))
    center = (
        (start[0] + end[0]) / 2.0,
        (start[1] + end[1]) / 2.0,
        (start[2] + end[2]) / 2.0,
    )
    return pts, center


def _points_wave(
    count: int, length: float, amplitude: float, frequency: float,
    origin: Vec3, axis: str,
) -> Tuple[List[Vec3], Vec3]:
    pts = []
    axis = axis.upper()
    for i in range(count):
        t = i / max(count - 1, 1)
        d = t * length
        offset = amplitude * math.sin(frequency * t * 2.0 * math.pi)
        if axis == "X":
            pts.append((origin[0] + d, origin[1] + offset, origin[2]))
        elif axis == "Y":
            pts.append((origin[0] + offset, origin[1] + d, origin[2]))
        else:  # Z
            pts.append((origin[0] + offset, origin[1], origin[2] + d))
    cx = origin[0] + length / 2.0 if axis == "X" else origin[0]
    cy = origin[1] + length / 2.0 if axis == "Y" else origin[1]
    return pts, (cx, cy, origin[2])


def _points_helix(
    count: int, radius: float, turns: float, rise_per_turn: float,
    origin: Vec3, start_angle_deg: float,
) -> Tuple[List[Vec3], Vec3]:
    pts = []
    for i in range(count):
        t = i / max(count - 1, 1)
        angle = math.radians(start_angle_deg) + t * turns * 2.0 * math.pi
        x = origin[0] + radius * math.cos(angle)
        y = origin[1] + radius * math.sin(angle)
        z = origin[2] + t * turns * rise_per_turn
        pts.append((x, y, z))
    return pts, origin


def _points_radial_rows(
    rings: int, props_per_ring: int, radius_step: float,
    origin: Vec3, start_angle_deg: float, include_center: bool,
) -> Tuple[List[Vec3], Vec3]:
    pts = []
    if include_center:
        pts.append(origin)
    for ring in range(1, rings + 1):
        r = ring * radius_step
        count = props_per_ring * ring  # more props on outer rings
        for i in range(count):
            angle = math.radians(start_angle_deg + 360.0 * i / count)
            x = origin[0] + r * math.cos(angle)
            y = origin[1] + r * math.sin(angle)
            pts.append((x, y, origin[2]))
    return pts, origin


# ─── Tool wrappers ─────────────────────────────────────────────────────────────

def _get_origin() -> Vec3:
    """Return centroid of selection, or world origin if nothing selected."""
    actors = get_selected_actors()
    if not actors:
        return (0.0, 0.0, 0.0)
    locs = [a.get_actor_location() for a in actors]
    n = len(locs)
    return (
        sum(v.x for v in locs) / n,
        sum(v.y for v in locs) / n,
        sum(v.z for v in locs) / n,
    )


# ─── Registered tools ──────────────────────────────────────────────────────────

@register_tool(
    name="pattern_grid",
    category="Prop Patterns",
    description="Spawn a mesh in a precise N×M rectangular grid",
    icon="▦",
    tags=["pattern", "grid", "placement", "procedural"],
)
def pattern_grid(
    mesh_path: str = _FALLBACK_MESH,
    cols: int = 5,
    rows: int = 5,
    spacing_x: float = 200.0,
    spacing_y: float = 200.0,
    origin: tuple = (0.0, 0.0, 0.0),
    center_origin: bool = True,
    rotation_mode: str = "world_up",
    scale: float = 1.0,
    scale_mode: str = "uniform",
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    preview: bool = False,
    seed: int = 42,
) -> None:
    """
    Place a mesh in a rectangular N×M grid.

    Args:
        mesh_path:    Content path to the StaticMesh asset.
        cols:         Number of columns (X axis).
        rows:         Number of rows (Y axis).
        spacing_x:   Distance (cm) between columns.
        spacing_y:   Distance (cm) between rows.
        origin:       World location (x, y, z) of grid anchor.
                      Defaults to centroid of current selection if (0,0,0) passed
                      and something is selected.
        center_origin: If True, the grid is centered on origin.
                       If False, origin is the bottom-left corner.
        rotation_mode: "world_up" | "face_center" | "random"
        scale:        Uniform scale (used when scale_mode="uniform").
        scale_mode:   "uniform" | "random" | "gradient"
        scale_min/max: Range for random/gradient scale.
        preview:      Spawn sphere markers; use pattern_clear to remove.
        seed:         RNG seed for deterministic results.
    """
    if origin == (0.0, 0.0, 0.0):
        sel_origin = _get_origin()
        if any(abs(v) > 1.0 for v in sel_origin):
            origin = sel_origin

    pts, center = _points_grid(cols, rows, spacing_x, spacing_y, origin, center_origin)
    _spawn_pattern(pts, center, mesh_path, rotation_mode, scale_mode,
                   scale, scale_min, scale_max, preview, seed,
                   f"Grid {cols}×{rows}")


@register_tool(
    name="pattern_circle",
    category="Prop Patterns",
    description="Arrange a mesh in an evenly-spaced ring at a set radius",
    icon="◯",
    tags=["pattern", "circle", "ring", "placement"],
)
def pattern_circle(
    mesh_path: str = _FALLBACK_MESH,
    count: int = 12,
    radius: float = 1000.0,
    origin: tuple = (0.0, 0.0, 0.0),
    start_angle_deg: float = 0.0,
    rotation_mode: str = "face_center",
    scale: float = 1.0,
    scale_mode: str = "uniform",
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    preview: bool = False,
    seed: int = 42,
) -> None:
    """
    Place props evenly spaced around a full 360° circle.

    Args:
        count:           Number of props in the ring.
        radius:          Ring radius in cm.
        start_angle_deg: Rotation offset for the entire ring (0 = +X axis).
        rotation_mode:   "world_up" | "face_center" | "face_tangent" | "random"
    """
    if origin == (0.0, 0.0, 0.0):
        sel_origin = _get_origin()
        if any(abs(v) > 1.0 for v in sel_origin):
            origin = sel_origin

    pts, center = _points_circle(count, radius, origin, start_angle_deg)
    _spawn_pattern(pts, center, mesh_path, rotation_mode, scale_mode,
                   scale, scale_min, scale_max, preview, seed,
                   f"Circle r={radius:.0f} n={count}")


@register_tool(
    name="pattern_arc",
    category="Prop Patterns",
    description="Place props along a partial arc between two angles",
    icon="◔",
    tags=["pattern", "arc", "placement", "curve"],
)
def pattern_arc(
    mesh_path: str = _FALLBACK_MESH,
    count: int = 8,
    radius: float = 1000.0,
    origin: tuple = (0.0, 0.0, 0.0),
    start_angle_deg: float = 0.0,
    end_angle_deg: float = 180.0,
    rotation_mode: str = "face_tangent",
    scale: float = 1.0,
    scale_mode: str = "uniform",
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    preview: bool = False,
    seed: int = 42,
) -> None:
    """
    Place props along a partial arc.

    Args:
        start_angle_deg / end_angle_deg: Arc sweep range in degrees.
            0° = +X, 90° = +Y, 180° = -X, 270° = -Y.
    """
    if origin == (0.0, 0.0, 0.0):
        sel_origin = _get_origin()
        if any(abs(v) > 1.0 for v in sel_origin):
            origin = sel_origin

    pts, center = _points_arc(count, radius, origin, start_angle_deg, end_angle_deg)
    _spawn_pattern(pts, center, mesh_path, rotation_mode, scale_mode,
                   scale, scale_min, scale_max, preview, seed,
                   f"Arc {start_angle_deg:.0f}°→{end_angle_deg:.0f}° r={radius:.0f}")


@register_tool(
    name="pattern_spiral",
    category="Prop Patterns",
    description="Spawn props along an Archimedean spiral (radius grows with angle)",
    icon="🌀",
    tags=["pattern", "spiral", "placement", "procedural"],
)
def pattern_spiral(
    mesh_path: str = _FALLBACK_MESH,
    count: int = 24,
    turns: float = 3.0,
    radius_start: float = 100.0,
    radius_end: float = 2000.0,
    origin: tuple = (0.0, 0.0, 0.0),
    start_angle_deg: float = 0.0,
    rotation_mode: str = "face_tangent",
    scale: float = 1.0,
    scale_mode: str = "gradient",
    scale_min: float = 0.5,
    scale_max: float = 1.5,
    preview: bool = False,
    seed: int = 42,
) -> None:
    """
    Place props along an Archimedean spiral.

    Args:
        turns:        Number of full rotations.
        radius_start: Radius at the center of the spiral (cm).
        radius_end:   Radius at the outer edge (cm).
    """
    if origin == (0.0, 0.0, 0.0):
        sel_origin = _get_origin()
        if any(abs(v) > 1.0 for v in sel_origin):
            origin = sel_origin

    pts, center = _points_spiral(count, turns, radius_start, radius_end,
                                  origin, start_angle_deg)
    _spawn_pattern(pts, center, mesh_path, rotation_mode, scale_mode,
                   scale, scale_min, scale_max, preview, seed,
                   f"Spiral {turns:.1f} turns")


@register_tool(
    name="pattern_line",
    category="Prop Patterns",
    description="Evenly space a mesh between two world points",
    icon="╌",
    tags=["pattern", "line", "placement", "distribute"],
)
def pattern_line(
    mesh_path: str = _FALLBACK_MESH,
    count: int = 10,
    start: tuple = (0.0, 0.0, 0.0),
    end: tuple = (2000.0, 0.0, 0.0),
    rotation_mode: str = "face_tangent",
    scale: float = 1.0,
    scale_mode: str = "uniform",
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    preview: bool = False,
    seed: int = 42,
) -> None:
    """
    Place props in a straight line from `start` to `end`.
    Both endpoints are included.
    """
    pts, center = _points_line(count, start, end)
    _spawn_pattern(pts, center, mesh_path, rotation_mode, scale_mode,
                   scale, scale_min, scale_max, preview, seed,
                   f"Line n={count}")


@register_tool(
    name="pattern_wave",
    category="Prop Patterns",
    description="Place props along a sine-wave path on X, Y, or Z axis",
    icon="〜",
    tags=["pattern", "wave", "sine", "placement"],
)
def pattern_wave(
    mesh_path: str = _FALLBACK_MESH,
    count: int = 16,
    length: float = 3000.0,
    amplitude: float = 400.0,
    frequency: float = 2.0,
    origin: tuple = (0.0, 0.0, 0.0),
    axis: str = "X",
    rotation_mode: str = "face_tangent",
    scale: float = 1.0,
    scale_mode: str = "uniform",
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    preview: bool = False,
    seed: int = 42,
) -> None:
    """
    Place props along a sine wave.

    Args:
        length:    Total path length in cm.
        amplitude: Wave height/width in cm.
        frequency: Number of full sine cycles across the length.
        axis:      Primary direction of travel: "X", "Y", or "Z".
    """
    if origin == (0.0, 0.0, 0.0):
        sel_origin = _get_origin()
        if any(abs(v) > 1.0 for v in sel_origin):
            origin = sel_origin

    pts, center = _points_wave(count, length, amplitude, frequency, origin, axis)
    _spawn_pattern(pts, center, mesh_path, rotation_mode, scale_mode,
                   scale, scale_min, scale_max, preview, seed,
                   f"Wave axis={axis} freq={frequency:.1f}")


@register_tool(
    name="pattern_helix",
    category="Prop Patterns",
    description="Spawn props along a 3D helix (spiral staircase layout)",
    icon="🔃",
    tags=["pattern", "helix", "3d", "spiral", "placement"],
)
def pattern_helix(
    mesh_path: str = _FALLBACK_MESH,
    count: int = 24,
    radius: float = 600.0,
    turns: float = 2.0,
    rise_per_turn: float = 1000.0,
    origin: tuple = (0.0, 0.0, 0.0),
    start_angle_deg: float = 0.0,
    rotation_mode: str = "face_tangent",
    scale: float = 1.0,
    scale_mode: str = "uniform",
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    preview: bool = False,
    seed: int = 42,
) -> None:
    """
    Place props along a 3D helix (corkscrew / spiral staircase).

    Args:
        radius:        Helix radius in cm.
        turns:         Number of full rotations.
        rise_per_turn: Height gained per full 360° turn (cm).
    """
    if origin == (0.0, 0.0, 0.0):
        sel_origin = _get_origin()
        if any(abs(v) > 1.0 for v in sel_origin):
            origin = sel_origin

    pts, center = _points_helix(count, radius, turns, rise_per_turn,
                                 origin, start_angle_deg)
    _spawn_pattern(pts, center, mesh_path, rotation_mode, scale_mode,
                   scale, scale_min, scale_max, preview, seed,
                   f"Helix {turns:.1f} turns r={radius:.0f}")


@register_tool(
    name="pattern_radial_rows",
    category="Prop Patterns",
    description="Concentric rings — like a dartboard or stadium layout",
    icon="◎",
    tags=["pattern", "radial", "concentric", "rings", "placement"],
)
def pattern_radial_rows(
    mesh_path: str = _FALLBACK_MESH,
    rings: int = 3,
    props_per_ring: int = 6,
    radius_step: float = 600.0,
    origin: tuple = (0.0, 0.0, 0.0),
    start_angle_deg: float = 0.0,
    include_center: bool = True,
    rotation_mode: str = "face_center",
    scale: float = 1.0,
    scale_mode: str = "uniform",
    scale_min: float = 0.8,
    scale_max: float = 1.2,
    preview: bool = False,
    seed: int = 42,
) -> None:
    """
    Place props in concentric rings with increasing density on outer rings.

    Args:
        rings:          Number of concentric rings (not counting center).
        props_per_ring: Base count. Ring N gets props_per_ring × N props,
                        so outer rings are naturally denser.
        radius_step:    Distance (cm) between rings.
        include_center: If True, spawn one prop at the exact center.
    """
    if origin == (0.0, 0.0, 0.0):
        sel_origin = _get_origin()
        if any(abs(v) > 1.0 for v in sel_origin):
            origin = sel_origin

    pts, center = _points_radial_rows(rings, props_per_ring, radius_step,
                                       origin, start_angle_deg, include_center)
    total = len(pts)
    _spawn_pattern(pts, center, mesh_path, rotation_mode, scale_mode,
                   scale, scale_min, scale_max, preview, seed,
                   f"Radial rows {rings} rings ({total} props)")


@register_tool(
    name="pattern_clear",
    category="Prop Patterns",
    description="Delete actors spawned by prop_patterns tools",
    icon="✕",
    tags=["pattern", "clear", "delete", "cleanup"],
)
def pattern_clear(preview_only: bool = False) -> None:
    """
    Delete pattern actors from the level.

    Args:
        preview_only: If True, delete only preview marker spheres.
                      If False, delete all Toolbelt pattern actors
                      (both preview and real spawns).
    """
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_subsystem.get_all_level_actors()

    target_tags = [_PREVIEW_TAG] if preview_only else [_PREVIEW_TAG, _PATTERN_TAG]
    to_delete = []

    for actor in all_actors:
        try:
            tags = [str(t) for t in actor.get_editor_property(_ACTOR_TAG_PROP)]
            if any(t in target_tags for t in tags):
                to_delete.append(actor)
        except Exception:
            pass

    if not to_delete:
        label = "preview" if preview_only else "pattern"
        unreal.log(f"[Patterns] No {label} actors found to clear.")
        return

    with undo_transaction("Clear Pattern Actors"):
        for actor in to_delete:
            actor_subsystem.destroy_actor(actor)

    label = "preview" if preview_only else "all pattern"
    unreal.log(f"[Patterns] ✓ Cleared {len(to_delete)} {label} actors.")
