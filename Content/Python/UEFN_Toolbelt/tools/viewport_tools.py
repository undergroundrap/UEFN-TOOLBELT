"""
UEFN TOOLBELT — Viewport Navigation Tools
========================================
Teleport the viewport camera to any world coordinate or actor instantly.

The UEFN assistant will tell you: "you cannot jump to coordinates directly,
place a temp prop, press F…" — these tools do it in one command.

Use cases:
  • Jump to a known spawn coordinate after placing something programmatically
  • Focus on a named actor by label
  • Return to a saved camera position
  • Quickly orbit between key locations in a large map
"""

from __future__ import annotations

import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning


def _get_camera() -> tuple:
    """Return (location, rotation) of the current viewport camera."""
    return unreal.EditorLevelLibrary.get_level_viewport_camera_info()


def _set_camera(location: unreal.Vector, rotation: unreal.Rotator) -> None:
    unreal.EditorLevelLibrary.set_level_viewport_camera_info(location, rotation)


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="viewport_goto",
    category="Viewport",
    description=(
        "Instantly move the viewport camera to any world coordinate. "
        "One command replaces the UEFN 'place a temp prop + press F' workaround."
    ),
    tags=["viewport", "camera", "navigate", "goto", "coordinates", "teleport"],
)
def run_viewport_goto(
    x: float = 0.0,
    y: float = 0.0,
    z: float = 500.0,
    pitch: float = -20.0,
    yaw: float = 0.0,
    **kwargs,
) -> dict:
    """
    Teleport the viewport camera to the given world coordinates.

    Args:
        x:     World X coordinate (default 0)
        y:     World Y coordinate (default 0)
        z:     World Z coordinate (default 500 — slightly above ground)
        pitch: Camera pitch angle in degrees (default -20 — looking slightly down)
        yaw:   Camera yaw (compass heading) in degrees (default 0 — facing +X)
    """
    try:
        loc = unreal.Vector(x, y, z)
        rot = unreal.Rotator(pitch, yaw, 0)
        _set_camera(loc, rot)
        log_info(f"viewport_goto: camera moved to ({x}, {y}, {z}) pitch={pitch} yaw={yaw}")
        return {
            "status": "ok",
            "location": [x, y, z],
            "rotation": {"pitch": pitch, "yaw": yaw},
        }
    except Exception as e:
        log_error(f"viewport_goto failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="viewport_focus_actor",
    category="Viewport",
    description=(
        "Select and focus the viewport camera on any actor by name. "
        "Partial label match supported — e.g. 'Cube' finds 'SM_Cube_001'."
    ),
    tags=["viewport", "camera", "focus", "actor", "select", "navigate"],
)
def run_viewport_focus_actor(
    label: str = "",
    **kwargs,
) -> dict:
    """
    Find an actor by label (partial match), select it, and move the camera to it.
    Uses UEFN's native 'Move Camera to Object' viewport command — no roll corruption.

    Args:
        label: Partial actor label to search for (case-insensitive)
    """
    if not label:
        return {"status": "error", "error": "label is required. Provide a partial actor name to search for."}

    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = actor_sub.get_all_level_actors()
        matches = [a for a in all_actors if label.lower() in a.get_actor_label().lower()]

        if not matches:
            return {"status": "error", "error": f"No actor found matching '{label}'. Check the label in the World Outliner."}

        target = matches[0]
        loc = target.get_actor_location()

        # Select the actor — required for the native camera command to know the target
        actor_sub.set_selected_level_actors([target])

        # Use UEFN's native "Move Camera to Object" command.
        # This is the same operation as Camera Movement > Move Camera to Object in the
        # viewport menu. No manual rotation math, no roll corruption.
        world = unreal.EditorLevelLibrary.get_editor_world()
        unreal.SystemLibrary.execute_console_command(world, "CAMERA ALIGN")

        log_info(f"viewport_focus_actor: focused on '{target.get_actor_label()}' at ({loc.x:.0f}, {loc.y:.0f}, {loc.z:.0f})")
        return {
            "status": "ok",
            "actor": target.get_actor_label(),
            "location": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
            "matches_found": len(matches),
        }
    except Exception as e:
        log_error(f"viewport_focus_actor failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="viewport_move_to_camera",
    category="Viewport",
    description=(
        "Move selected actors to the current camera position. "
        "Navigate to a spot in the viewport, then run this to place your selection there."
    ),
    tags=["viewport", "camera", "move", "placement", "teleport"],
)
def run_viewport_move_to_camera(**kwargs) -> dict:
    """
    Move all selected actors to the current viewport camera position.
    Workflow: fly to where you want something → select it → run this tool.
    """
    try:
        loc, _rot = _get_camera()
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = actor_sub.get_selected_level_actors()
        if not actors:
            return {"status": "error", "error": "No actors selected. Select the actors you want to move, then run this."}

        with unreal.ScopedEditorTransaction("Move Selection to Camera"):
            for actor in actors:
                actor.set_actor_location(loc, False, True)

        log_info(f"viewport_move_to_camera: moved {len(actors)} actor(s) to ({loc.x:.0f}, {loc.y:.0f}, {loc.z:.0f})")
        return {
            "status": "ok",
            "actors_moved": len(actors),
            "location": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
        }
    except Exception as e:
        log_error(f"viewport_move_to_camera failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="viewport_camera_get",
    category="Viewport",
    description="Return the current viewport camera location and rotation — useful for saving a position to return to.",
    tags=["viewport", "camera", "get", "position", "save"],
)
def run_viewport_camera_get(**kwargs) -> dict:
    """Return the current viewport camera position and rotation."""
    try:
        loc, rot = _get_camera()
        return {
            "status": "ok",
            "location": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
            "rotation": {"pitch": round(rot.pitch, 1), "yaw": round(rot.yaw, 1), "roll": round(rot.roll, 1)},
            "tip": "Use viewport_goto with these values to return here later.",
        }
    except Exception as e:
        log_error(f"viewport_camera_get failed: {e}")
        return {"status": "error", "error": str(e)}


# ── Show flag presets ──────────────────────────────────────────────────────────

_SHOWFLAG_PRESETS = {
    "clean":         ["ShowFlag.TextRenders 0", "ShowFlag.BillboardSprites 0", "ShowFlag.Decals 0"],
    "no_text":       ["ShowFlag.TextRenders 0"],
    "no_icons":      ["ShowFlag.BillboardSprites 0"],
    "geometry_only": ["ShowFlag.TextRenders 0", "ShowFlag.BillboardSprites 0",
                      "ShowFlag.Decals 0", "ShowFlag.Particles 0"],
    "reset":         ["ShowFlag.TextRenders 1", "ShowFlag.BillboardSprites 1",
                      "ShowFlag.Decals 1", "ShowFlag.Particles 1"],
}


@register_tool(
    name="viewport_showflag",
    category="Viewport",
    description=(
        "Apply a viewport show-flag preset to instantly declutter the editor view. "
        "Presets: clean | no_text | no_icons | geometry_only | reset"
    ),
    tags=["viewport", "showflag", "visibility", "display", "clean", "preset"],
)
def run_viewport_showflag(preset: str = "clean", **kwargs) -> dict:
    """
    Toggle UEFN viewport show flags using a named preset.

    Args:
        preset: 'clean'         — hide text, device icons, decals
                'no_text'       — hide only 3D text renders
                'no_icons'      — hide only device billboard icons
                'geometry_only' — hide text, icons, decals, particles
                'reset'         — restore all hidden categories
                'list'          — return available presets (no change)
    """
    if preset == "list":
        return {"status": "ok", "presets": list(_SHOWFLAG_PRESETS.keys())}
    commands = _SHOWFLAG_PRESETS.get(preset)
    if commands is None:
        return {
            "status": "error",
            "error": f"Unknown preset '{preset}'. Available: {list(_SHOWFLAG_PRESETS.keys())}",
        }
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        applied = []
        for cmd in commands:
            unreal.SystemLibrary.execute_console_command(world, cmd)
            applied.append(cmd)
        log_info(f"viewport_showflag: applied preset '{preset}' ({len(applied)} flags)")
        return {"status": "ok", "preset": preset, "commands_applied": applied}
    except Exception as e:
        log_error(f"viewport_showflag failed: {e}")
        return {"status": "error", "error": str(e)}


# ── Viewport bookmarks ─────────────────────────────────────────────────────────

def _bookmarks_path() -> str:
    import os
    saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved, exist_ok=True)
    return os.path.join(saved, "viewport_bookmarks.json")


def _load_bookmarks() -> dict:
    import json, os
    p = _bookmarks_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_bookmarks(data: dict) -> None:
    import json
    with open(_bookmarks_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@register_tool(
    name="viewport_bookmark_save",
    category="Viewport",
    description=(
        "Save the current viewport camera position as a named bookmark. "
        "Jump back any time with viewport_bookmark_jump."
    ),
    tags=["viewport", "camera", "bookmark", "save", "position", "navigate"],
)
def run_viewport_bookmark_save(name: str = "", **kwargs) -> dict:
    """
    Save the current viewport camera position as a named bookmark.

    Args:
        name: Bookmark name, e.g. 'spawn_area', 'boss_room', 'overview'
    """
    if not name:
        return {"status": "error", "error": "name is required. Example: 'spawn_area' or 'overview'"}
    try:
        loc, rot = _get_camera()
        bookmarks = _load_bookmarks()
        bookmarks[name] = {
            "x": round(loc.x, 1), "y": round(loc.y, 1), "z": round(loc.z, 1),
            "pitch": round(rot.pitch, 1), "yaw": round(rot.yaw, 1),
        }
        _save_bookmarks(bookmarks)
        log_info(f"viewport_bookmark_save: saved '{name}'")
        return {
            "status": "ok",
            "name": name,
            "location": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
            "rotation": {"pitch": round(rot.pitch, 1), "yaw": round(rot.yaw, 1)},
            "total_bookmarks": len(bookmarks),
        }
    except Exception as e:
        log_error(f"viewport_bookmark_save failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="viewport_bookmark_jump",
    category="Viewport",
    description=(
        "Jump the viewport camera to a saved named bookmark. "
        "Use viewport_bookmark_list to see all saved bookmarks."
    ),
    tags=["viewport", "camera", "bookmark", "jump", "navigate", "goto"],
)
def run_viewport_bookmark_jump(name: str = "", **kwargs) -> dict:
    """
    Teleport the viewport camera to a previously saved bookmark.

    Args:
        name: Bookmark name saved with viewport_bookmark_save
    """
    if not name:
        return {"status": "error", "error": "name is required."}
    try:
        bookmarks = _load_bookmarks()
        if name not in bookmarks:
            available = list(bookmarks.keys())
            return {
                "status": "error",
                "error": f"Bookmark '{name}' not found.",
                "available": available,
            }
        bm = bookmarks[name]
        loc = unreal.Vector(bm["x"], bm["y"], bm["z"])
        rot = unreal.Rotator(bm["pitch"], bm["yaw"], 0)
        _set_camera(loc, rot)
        log_info(f"viewport_bookmark_jump: jumped to '{name}'")
        return {
            "status": "ok",
            "name": name,
            "location": [bm["x"], bm["y"], bm["z"]],
            "rotation": {"pitch": bm["pitch"], "yaw": bm["yaw"]},
        }
    except Exception as e:
        log_error(f"viewport_bookmark_jump failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="viewport_bookmark_list",
    category="Viewport",
    description="List all saved viewport camera bookmarks with their coordinates.",
    tags=["viewport", "camera", "bookmark", "list", "navigate"],
)
def run_viewport_bookmark_list(**kwargs) -> dict:
    """Return all saved viewport bookmarks."""
    try:
        bookmarks = _load_bookmarks()
        return {
            "status": "ok",
            "count": len(bookmarks),
            "bookmarks": {
                name: {"location": [bm["x"], bm["y"], bm["z"]],
                       "rotation": {"pitch": bm["pitch"], "yaw": bm["yaw"]}}
                for name, bm in bookmarks.items()
            },
            "tip": "Use viewport_bookmark_jump with a name to teleport to any saved position.",
        }
    except Exception as e:
        log_error(f"viewport_bookmark_list failed: {e}")
        return {"status": "error", "error": str(e)}
