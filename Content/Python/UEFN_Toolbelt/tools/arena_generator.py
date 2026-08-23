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

import unreal

from ..core import (
    detect_project_mount,
    get_config,
    log_error,
    log_info,
    log_warning,
    save_asset,
    spawn_static_mesh_actor,
    undo_transaction,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Configurable mesh paths — replace with your project's asset paths
# ─────────────────────────────────────────────────────────────────────────────

# A simple 1×1×1 unit floor tile / cube mesh.
# Asset NAMES, not paths. The mount is resolved at call time -- see
# _project_asset_path() for why a hardcoded /Game/ prefix was wrong.
MESH_FLOOR     = "SM_Floor_Tile"
MESH_WALL      = "SM_Wall_Panel"
MESH_PLATFORM  = "SM_Platform"
MESH_SPAWN_PAD = "SM_SpawnPad"

_MESH_SUBPATH = "UEFN_Toolbelt/Meshes"
_MAT_SUBPATH  = "UEFN_Toolbelt/Materials"


def _project_asset_path(subpath: str, name: str) -> str:
    """
    Build a path under the USER'S project mount, e.g. /MyIsland/UEFN_Toolbelt/...

    In UEFN, /Game/ does not mean the creator's project -- it resolves to Epic's
    Fortnite install under FortniteGame/Content (UEFN_QUIRKS.md #23). Reads from a
    hardcoded /Game/ path therefore never resolve, and writes land somewhere the
    project cannot reference, leaving every actor that uses the asset pointing at
    a dangling reference.

    Resolved at call time, not import time: mount detection needs a live editor.
    """
    return f"/{detect_project_mount()}/{subpath}/{name}"

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

def _resolve_mesh(name: str) -> str:
    """Use the bundled mesh if present, else the configured fallback."""
    preferred = _project_asset_path(_MESH_SUBPATH, name)
    if unreal.EditorAssetLibrary.does_asset_exist(preferred):
        return preferred
    fallback = get_config().get("arena.fallback_mesh")
    log_warning(f"Mesh not found: '{preferred}' — using fallback '{fallback}'. "
                f"Set a custom fallback: tb.run('config_set', key='arena.fallback_mesh', value='/YourProject/YourMesh')")
    return fallback


def _place_floor(
    cfg: ArenaConfig,
    origin: unreal.Vector,
    placed: list[unreal.Actor],
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
    placed: list[unreal.Actor],
) -> tuple[list[unreal.Actor], list[unreal.Actor]]:
    """Place perimeter walls. Returns (red_wall_actors, blue_wall_actors)."""
    mesh = _resolve_mesh(MESH_WALL)
    half_x = (cfg.floor_tiles_x * cfg.tile_size) / 2.0
    half_y = (cfg.floor_tiles_y * cfg.tile_size) / 2.0
    ts = cfg.tile_size
    wall_scale_h = unreal.Vector(ts / 100.0, ts / 100.0, ts / 100.0)

    red_walls: list[unreal.Actor] = []
    blue_walls: list[unreal.Actor] = []

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
                    rotation=unreal.Rotator(roll=0, pitch=0, yaw=rot_yaw),
                    scale=wall_scale_h,
                )
                if actor:
                    actor.set_folder_path("/Arena/Walls")
                    actor.set_actor_label(f"Wall_{prefix}_{i}_{h}")
                    placed.append(actor)
                    if loc.x >= origin.x:
                        red_walls.append(actor)
                    else:
                        blue_walls.append(actor)

    # North / South walls (along X axis)
    place_wall_row(-half_x, -half_y, cfg.floor_tiles_x, ts, 0, 0, "S")
    place_wall_row(-half_x,  half_y, cfg.floor_tiles_x, ts, 0, 0, "N")
    # East / West walls (along Y axis)
    place_wall_row(-half_x, -half_y, cfg.floor_tiles_y, 0, ts, 90, "W")
    place_wall_row( half_x, -half_y, cfg.floor_tiles_y, 0, ts, 90, "E")

    return red_walls, blue_walls


def _place_center_platform(
    cfg: ArenaConfig,
    origin: unreal.Vector,
    placed: list[unreal.Actor],
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
    placed: list[unreal.Actor],
) -> list[tuple[list[unreal.Actor], list[unreal.Actor]]]:
    """Place Red and Blue spawn pads. Returns (red_actors, blue_actors)."""
    import math
    mesh = _resolve_mesh(MESH_SPAWN_PAD)
    half_x = (cfg.floor_tiles_x * cfg.tile_size) / 2.0

    red_actors: list[unreal.Actor]  = []
    blue_actors: list[unreal.Actor] = []

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
#  Direct color fallback (no M_ToolbeltBase required)
# ─────────────────────────────────────────────────────────────────────────────

# Where auto-generated team materials are stored. Created once on first arena
# spawn, reused on every subsequent call. These are WRITES, so a wrong mount does
# not just fail to find something -- it produces assets the project cannot
# reference. Resolved per call against the project mount.

def _mat_red_path() -> str:
    return _project_asset_path(_MAT_SUBPATH, "M_Arena_TeamRed")


def _mat_blue_path() -> str:
    return _project_asset_path(_MAT_SUBPATH, "M_Arena_TeamBlue")


def _create_flat_color_material(asset_path: str, r: float, g: float, b: float):
    """
    Create a new simple unlit flat-color Material asset at asset_path.
    Uses MaterialEditingLibrary -- no custom parent material required.
    Returns the created/loaded material, or None on failure.
    """
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        return unreal.load_asset(asset_path)

    folder, name = asset_path.rsplit("/", 1)
    try:
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        mat = asset_tools.create_asset(
            name, folder, unreal.Material, unreal.MaterialFactoryNew()
        )
        if mat is None:
            return None

        mel = unreal.MaterialEditingLibrary
        # Add a Constant4Vector for the flat color
        color_expr = mel.create_material_expression(
            mat, unreal.MaterialExpressionConstant4Vector, -300, 0
        )
        color_expr.constant = unreal.LinearColor(r, g, b, 1.0)
        # Wire it to Base Color
        mel.connect_material_property(
            color_expr, "", unreal.MaterialProperty.MP_BASE_COLOR
        )
        mel.recompile_material(mat)
        save_asset(asset_path)
        log_info(f"[Arena] Created material: {asset_path}")
        return mat
    except Exception as e:
        log_warning(f"[Arena] Could not create material at {asset_path}: {e}")
        return None


def _get_team_materials():
    """
    Return (red_mat, blue_mat). Creates them on first call if they don't exist.
    Falls back to WorldGridMaterial for blue if creation fails.
    """
    red_mat  = _create_flat_color_material(_mat_red_path(),  1.0, 0.05, 0.05)
    blue_mat = _create_flat_color_material(_mat_blue_path(), 0.05, 0.2,  1.0)

    # Last resort for blue: WorldGridMaterial always exists
    if blue_mat is None:
        blue_mat = unreal.load_asset("/Engine/EngineMaterials/WorldGridMaterial")

    return red_mat, blue_mat


def _set_material_on_actors(actors: list[unreal.Actor], mat) -> int:
    """Apply mat to every material slot on every StaticMeshComponent in actors list."""
    colored = 0
    for actor in actors:
        try:
            comps = actor.get_components_by_class(unreal.StaticMeshComponent)
            for comp in comps:
                for slot in range(comp.get_num_materials()):
                    comp.set_material(slot, mat)
                colored += 1
        except Exception:
            pass
    return colored


def _apply_team_colors(
    red_actors: list[unreal.Actor],
    blue_actors: list[unreal.Actor],
) -> None:
    """
    Apply solid red/blue materials to the given actor lists.
    Creates <ProjectMount>/UEFN_Toolbelt/Materials/M_Arena_TeamRed|Blue on first run,
    then reuses them. No custom parent material (M_ToolbeltBase) required.
    """
    red_mat, blue_mat = _get_team_materials()

    if red_mat and red_actors:
        n = _set_material_on_actors(red_actors, red_mat)
        log_info(f"[Arena] Applied red to {n} components.")

    if blue_mat and blue_actors:
        n = _set_material_on_actors(blue_actors, blue_mat)
        log_info(f"[Arena] Applied blue to {n} components.")

    unreal.get_editor_subsystem(unreal.EditorActorSubsystem).set_selected_level_actors([])


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
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
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
    all_placed: list[unreal.Actor] = []

    log_info(f"Generating '{size}' arena at {origin}…")

    with undo_transaction(f"Arena Generator: {size.capitalize()} Arena"):
        _place_floor(cfg, origin_vec, all_placed)
        red_walls, blue_walls = _place_walls(cfg, origin_vec, all_placed)
        _place_center_platform(cfg, origin_vec, all_placed)
        red_spawns, blue_spawns = _place_spawns(cfg, origin_vec, all_placed)

    red_actors  = red_walls  + red_spawns
    blue_actors = blue_walls + blue_spawns

    log_info(
        f"Arena generated: {len(all_placed)} actors placed "
        f"({len(red_spawns)} Red spawns, {len(blue_spawns)} Blue spawns)."
    )

    # Apply team colors to WALLS + SPAWN PADS (not just pads)
    if apply_team_colors and (red_actors or blue_actors):
        try:
            _apply_team_colors(red_actors, blue_actors)
        except Exception as e:
            log_warning(f"Team color auto-apply skipped: {e}")
    log_info("Arena generation complete. Undo with Ctrl+Z to remove everything.")
    return {"status": "ok", "placed": len(all_placed), "red_spawns": len(red_spawns), "blue_spawns": len(blue_spawns)}
