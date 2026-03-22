"""
UEFN TOOLBELT — Arena Generator
========================================
Instant symmetrical Red vs Blue arenas. What used to take an hour of manual
prop placement now runs in seconds.

FEATURES:
  • Configurable arena size (small / medium / large)
  • Symmetrical left/right layout (floor, perimeter walls, platform)
  • Red spawn cluster (X+) and Blue spawn cluster (X-)
  • Center elevated platform
  • Customizable mesh paths (point to any UEFN/Fortnite content)
  • Optional team-material auto-apply (integrates with Material Master)
  • Full undo — one Ctrl+Z removes the entire arena
  • Smart actor labeling and folder grouping in World Outliner

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Quick default arena
    tb.run("arena_generate")

    # Custom size, centered at 0,0,0
    tb.run("arena_generate", size="large", origin=(0, 0, 0), apply_team_colors=True)

    # Generate without team colors
    tb.run("arena_generate", size="small", apply_team_colors=False)

BLUEPRINT:
    "Execute Python Command" →  import UEFN_Toolbelt as tb; tb.run("arena_generate", size="medium")

MESH PATHS:
    Change the MESH_* constants below to use your own UEFN/Fortnite assets.
    The defaults are placeholder paths — replace them with actual Content Browser paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import unreal

from ..core import (
    undo_transaction, log_info, log_warning, log_error,
    spawn_static_mesh_actor, load_asset, ensure_folder, get_config,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Configurable mesh paths — replace with your project's asset paths
# ─────────────────────────────────────────────────────────────────────────────

# A simple 1×1×1 unit floor tile / cube mesh.
MESH_FLOOR     = "/Game/UEFN_Toolbelt/Meshes/SM_Floor_Tile"
MESH_WALL      = "/Game/UEFN_Toolbelt/Meshes/SM_Wall_Panel"
MESH_PLATFORM  = "/Game/UEFN_Toolbelt/Meshes/SM_Platform"
MESH_SPAWN_PAD = "/Game/UEFN_Toolbelt/Meshes/SM_SpawnPad"

# Fallback: use Engine primitives if custom meshes are missing
MESH_FALLBACK  = "/Engine/BasicShapes/Cube"

# ─────────────────────────────────────────────────────────────────────────────
#  Arena size presets
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArenaConfig:
    """All dimensional parameters for a single arena preset."""
    name: str
    # Floor
    floor_tiles_x: int      # number of tiles along X (Red → Blue axis)
    floor_tiles_y: int      # number of tiles along Y (width)
    tile_size: float        # world units per tile
    # Walls
    wall_height: int        # tiles tall
    # Platform
    platform_tiles: int     # tiles × tiles (always square, centered)
    platform_z: float       # height above floor
    # Spawns
    spawn_count: int        # per team
    spawn_spread: float     # radius of spawn cluster


ARENA_PRESETS = {
    "small": ArenaConfig(
        name="small",
        floor_tiles_x=10, floor_tiles_y=8,
        tile_size=400.0,
        wall_height=4,
        platform_tiles=2, platform_z=400.0,
        spawn_count=4, spawn_spread=600.0,
    ),
    "medium": ArenaConfig(
        name="medium",
        floor_tiles_x=16, floor_tiles_y=12,
        tile_size=400.0,
        wall_height=5,
        platform_tiles=3, platform_z=400.0,
        spawn_count=6, spawn_spread=900.0,
    ),
    "large": ArenaConfig(
        name="large",
        floor_tiles_x=24, floor_tiles_y=16,
        tile_size=400.0,
        wall_height=6,
        platform_tiles=4, platform_z=400.0,
        spawn_count=10, spawn_spread=1200.0,
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_mesh(preferred: str) -> str:
    """Use preferred mesh, fall back to config fallback if it doesn't exist."""
    if unreal.EditorAssetLibrary.does_asset_exist(preferred):
        return preferred
    fallback = get_config().get("arena.fallback_mesh")
    log_warning(f"Mesh not found: '{preferred}' — using fallback '{fallback}'. "
                f"Set a custom fallback: tb.run('config_set', key='arena.fallback_mesh', value='/Game/YourMesh')")
    return fallback


def _place_floor(
    cfg: ArenaConfig,
    origin: unreal.Vector,
    placed: List[unreal.Actor],
) -> None:
    mesh = _resolve_mesh(MESH_FLOOR)
    scale = unreal.Vector(cfg.tile_size / 100.0, cfg.tile_size / 100.0, 1.0)
    half_x = (cfg.floor_tiles_x * cfg.tile_size) / 2.0
    half_y = (cfg.floor_tiles_y * cfg.tile_size) / 2.0

    for xi in range(cfg.floor_tiles_x):
        for yi in range(cfg.floor_tiles_y):
            loc = unreal.Vector(
                origin.x - half_x + xi * cfg.tile_size + cfg.tile_size / 2,
                origin.y - half_y + yi * cfg.tile_size + cfg.tile_size / 2,
                origin.z,
            )
            actor = spawn_static_mesh_actor(mesh, loc, scale=scale)
            if actor:
                actor.set_folder_path("/Arena/Floor")
                actor.set_actor_label(f"Floor_{xi}_{yi}")
                placed.append(actor)


def _place_walls(
    cfg: ArenaConfig,
    origin: unreal.Vector,
    placed: List[unreal.Actor],
) -> None:
    mesh = _resolve_mesh(MESH_WALL)
    half_x = (cfg.floor_tiles_x * cfg.tile_size) / 2.0
    half_y = (cfg.floor_tiles_y * cfg.tile_size) / 2.0
    ts = cfg.tile_size
    wall_scale_h = unreal.Vector(ts / 100.0, ts / 100.0, ts / 100.0)

    def place_wall_row(start_x, start_y, count, step_x, step_y, rot_yaw, prefix):
        for i in range(count):
            for h in range(cfg.wall_height):
                loc = unreal.Vector(
                    origin.x + start_x + i * step_x,
                    origin.y + start_y + i * step_y,
                    origin.z + ts / 2 + h * ts,
                )
                actor = spawn_static_mesh_actor(
                    mesh, loc,
                    rotation=unreal.Rotator(0, rot_yaw, 0),
                    scale=wall_scale_h,
                )
                if actor:
                    actor.set_folder_path("/Arena/Walls")
                    actor.set_actor_label(f"Wall_{prefix}_{i}_{h}")
                    placed.append(actor)

    # North / South walls (along X axis)
    place_wall_row(-half_x, -half_y, cfg.floor_tiles_x, ts, 0, 0, "S")
    place_wall_row(-half_x,  half_y, cfg.floor_tiles_x, ts, 0, 0, "N")
    # East / West walls (along Y axis)
    place_wall_row(-half_x, -half_y, cfg.floor_tiles_y, 0, ts, 90, "W")
    place_wall_row( half_x, -half_y, cfg.floor_tiles_y, 0, ts, 90, "E")


def _place_center_platform(
    cfg: ArenaConfig,
    origin: unreal.Vector,
    placed: List[unreal.Actor],
) -> None:
    mesh = _resolve_mesh(MESH_PLATFORM)
    pt = cfg.platform_tiles
    ts = cfg.tile_size
    half_pt = (pt * ts) / 2.0

    for xi in range(pt):
        for yi in range(pt):
            loc = unreal.Vector(
                origin.x - half_pt + xi * ts + ts / 2,
                origin.y - half_pt + yi * ts + ts / 2,
                origin.z + cfg.platform_z,
            )
            actor = spawn_static_mesh_actor(
                mesh, loc,
                scale=unreal.Vector(ts / 100.0, ts / 100.0, 1.0),
            )
            if actor:
                actor.set_folder_path("/Arena/Platform")
                actor.set_actor_label(f"Platform_{xi}_{yi}")
                placed.append(actor)


def _place_spawns(
    cfg: ArenaConfig,
    origin: unreal.Vector,
    placed: List[unreal.Actor],
) -> List[Tuple[List[unreal.Actor], List[unreal.Actor]]]:
    """Place Red and Blue spawn pads. Returns (red_actors, blue_actors)."""
    import math
    mesh = _resolve_mesh(MESH_SPAWN_PAD)
    half_x = (cfg.floor_tiles_x * cfg.tile_size) / 2.0

    red_actors: List[unreal.Actor]  = []
    blue_actors: List[unreal.Actor] = []

    for team, sign, team_actors in [("Red", 1, red_actors), ("Blue", -1, blue_actors)]:
        for i in range(cfg.spawn_count):
            angle = (i / cfg.spawn_count) * math.tau
            sx = math.cos(angle) * cfg.spawn_spread * 0.4
            sy = math.sin(angle) * cfg.spawn_spread
            loc = unreal.Vector(
                origin.x + sign * (half_x * 0.6 + abs(sx)),
                origin.y + sy,
                origin.z + 5.0,  # slightly above floor
            )
            actor = spawn_static_mesh_actor(mesh, loc)
            if actor:
                actor.set_folder_path(f"/Arena/Spawns/{team}")
                actor.set_actor_label(f"SpawnPad_{team}_{i}")
                placed.append(actor)
                team_actors.append(actor)

    return red_actors, blue_actors


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tool
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="arena_generate",
    category="Procedural",
    description="Generate a symmetrical Red vs Blue arena instantly.",
    shortcut="Ctrl+Alt+A",
    tags=["arena", "generate", "red", "blue", "procedural", "spawn"],
)
def run_generate(
    size: str = "medium",
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    apply_team_colors: bool = True,
    **kwargs,
) -> dict:
    """
    Args:
        size:              "small", "medium", or "large".
        origin:            (x, y, z) world position for the arena center.
        apply_team_colors: If True, auto-apply team_red/team_blue material presets
                           to the respective spawn pads (requires Material Master).
    """
    if size not in ARENA_PRESETS:
        log_error(f"Unknown arena size '{size}'. Choose from: {list(ARENA_PRESETS.keys())}")
        return {"status": "error", "placed": 0, "red_spawns": 0, "blue_spawns": 0}

    cfg = ARENA_PRESETS[size]
    origin_vec = unreal.Vector(*origin)
    all_placed: List[unreal.Actor] = []

    log_info(f"Generating '{size}' arena at {origin}…")

    with undo_transaction(f"Arena Generator: {size.capitalize()} Arena"):
        _place_floor(cfg, origin_vec, all_placed)
        _place_walls(cfg, origin_vec, all_placed)
        _place_center_platform(cfg, origin_vec, all_placed)
        red_actors, blue_actors = _place_spawns(cfg, origin_vec, all_placed)

    log_info(
        f"Arena generated: {len(all_placed)} actors placed "
        f"({len(red_actors)} Red spawns, {len(blue_actors)} Blue spawns)."
    )

    # Optional: apply team colors via Material Master
    if apply_team_colors and (red_actors or blue_actors):
        try:
            from ..core import get_selected_actors
            import UEFN_Toolbelt as tb

            # Apply red to red spawn actors
            if red_actors:
                unreal.get_editor_subsystem(unreal.EditorActorSubsystem) \
                    .set_selected_level_actors(red_actors)
                tb.run("material_apply_preset", preset="team_red")

            # Apply blue to blue spawn actors
            if blue_actors:
                unreal.get_editor_subsystem(unreal.EditorActorSubsystem) \
                    .set_selected_level_actors(blue_actors)
                tb.run("material_apply_preset", preset="team_blue")

        except Exception as e:
            log_warning(f"Team color auto-apply skipped: {e}")

    # Restore empty selection
    unreal.get_editor_subsystem(unreal.EditorActorSubsystem).set_selected_level_actors([])
    log_info("Arena generation complete. Undo with Ctrl+Z to remove everything.")
    return {"status": "ok", "placed": len(all_placed), "red_spawns": len(red_actors), "blue_spawns": len(blue_actors)}
