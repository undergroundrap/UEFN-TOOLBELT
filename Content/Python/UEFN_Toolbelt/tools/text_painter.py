"""
UEFN TOOLBELT — Text Painter
========================================
Place colored, styled 3D text anywhere in your UEFN level using
unreal.TextRenderActor. Each text object is a real UE actor — it shows up
in World Outliner, persists with the level, supports undo, and can be styled
independently.

"Make it an asset": Every text configuration you create can be saved as a
named style preset (JSON) in Saved/UEFN_Toolbelt/text_styles.json and
reused across levels or shared with your team.

FEATURES:
  • Place a single styled text actor at any world location
  • Auto-label selected actors with their own names (zone tagging in seconds)
  • Drop title cards at specific map coordinates with one call
  • Cycle through a color palette across multiple text actors
  • Paint a text grid — e.g., numbered grid tiles "A1…H8" across a map area
  • Billboard text (always faces camera via rotation lock hint)
  • Save / load named text style presets (color, size, alignment, spacing)
  • Batch-delete all text actors in a named folder
  • Full undo on every operation

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Place a single title card
    tb.run("text_place",
           text="RED BASE",
           color="#FF2200",
           location=(3200, 0, 300),
           world_size=150.0)

    # Auto-label every selected actor with its own name
    tb.run("text_label_selection",
           offset_z=200.0,
           color="#00FFCC",
           world_size=60.0)

    # Paint a zone-title grid (e.g., A1..D4 across a 4×4 map grid)
    tb.run("text_paint_grid",
           cols=4, rows=4,
           origin=(0, 0, 10),
           cell_size=2000.0)

    # Save current style as a preset
    tb.run("text_save_style",
           style_name="ZoneTitle",
           color="#FFDD00", world_size=120.0,
           h_align="center", v_align="center")

    # Apply saved style when placing
    tb.run("text_place",
           text="SPAWN ZONE",
           style="ZoneTitle",
           location=(0, 0, 400))

BLUEPRINT:
    "Execute Python Command" →
        import UEFN_Toolbelt as tb; tb.run("text_place", text="GAME START", color="#FFFFFF", location=(0,0,200))

HOW TextRenderActor WORKS IN UEFN:
    - It is a standard UE Actor with a TextRenderComponent attached.
    - Text is 3D geometry rendered in world space — visible from any camera angle.
    - TextRenderColor uses FColor (0-255 integers per channel).
    - world_size controls the font height in Unreal Units (1 UU ≈ 1 cm).
    - Does NOT require any external texture or material beyond the default
      text render material already built into the engine.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import unreal

from ..core import (
    undo_transaction, get_selected_actors, require_selection,
    log_info, log_warning, log_error, color_from_hex,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────────────────────────

STYLES_FILE = os.path.join(
    unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "text_styles.json"
)

TEXT_FOLDER = "ToolbeltText"

# ─────────────────────────────────────────────────────────────────────────────
#  Default style
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_STYLE: Dict[str, Any] = {
    "color":        "#FFFFFF",
    "world_size":   100.0,
    "h_align":      "center",   # "left", "center", "right"
    "v_align":      "center",   # "top", "center", "bottom"
    "x_scale":      1.0,
    "y_scale":      1.0,
    "horiz_spacing": 0.0,
    "vert_spacing":  0.0,
}

# Palette used when cycling colors across multiple text actors
COLOR_PALETTE = [
    "#FF2200", "#FF8800", "#FFDD00", "#44FF44",
    "#00CCFF", "#4488FF", "#AA44FF", "#FF44AA",
    "#FFFFFF", "#AAAAAA",
]

# ─────────────────────────────────────────────────────────────────────────────
#  Alignment enum maps
# ─────────────────────────────────────────────────────────────────────────────

try:
    _H_ALIGN = {
        "left":   unreal.TextRenderHorizontalAlignment.ETRA_LEFT,
        "center": unreal.TextRenderHorizontalAlignment.ETRA_CENTER,
        "right":  unreal.TextRenderHorizontalAlignment.ETRA_RIGHT,
    }
    _V_ALIGN = {
        "top":    unreal.TextRenderVerticalAlignment.ETRVA_TOP,
        "center": unreal.TextRenderVerticalAlignment.ETRVA_CENTER,
        "bottom": unreal.TextRenderVerticalAlignment.ETRVA_BOTTOM,
    }
except AttributeError:
    # UEFN exposes these as integers rather than named enums
    _H_ALIGN = {"left": 0, "center": 1, "right": 2}
    _V_ALIGN = {"top": 0, "center": 1, "bottom": 2}

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_styles() -> Dict[str, Any]:
    if not os.path.exists(STYLES_FILE):
        return {}
    try:
        with open(STYLES_FILE) as f:
            return json.load(f)
    except Exception as e:
        log_error(f"text_painter: could not read styles file: {e}")
        return {}


def _save_styles(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STYLES_FILE), exist_ok=True)
    with open(STYLES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _resolve_style(style_name: Optional[str], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a final style dict by layering: defaults → saved preset → call-time overrides.
    """
    base = dict(DEFAULT_STYLE)
    if style_name:
        saved = _load_styles().get(style_name)
        if saved:
            base.update(saved)
        else:
            log_warning(f"text_painter: style '{style_name}' not found, using defaults.")
    base.update({k: v for k, v in overrides.items() if v is not None})
    return base


def _hex_to_fcolor(hex_str: str) -> unreal.Color:
    """Convert '#RRGGBB' or '#RRGGBBAA' to unreal.Color (0-255 per channel)."""
    h = hex_str.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    a = int(h[6:8], 16) if len(h) >= 8 else 255
    return unreal.Color(r=r, g=g, b=b, a=a)


def _spawn_text_actor(
    text: str,
    location: unreal.Vector,
    rotation: unreal.Rotator,
    style: Dict[str, Any],
    label: str = "TextActor",
    folder: str = TEXT_FOLDER,
) -> Optional[unreal.TextRenderActor]:
    """
    Core spawn function. Creates a TextRenderActor and applies all style properties.
    Returns the actor or None on failure.
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor: unreal.TextRenderActor = actor_sub.spawn_actor_from_class(
        unreal.TextRenderActor, location, rotation
    )
    if actor is None:
        log_error("text_painter: spawn_actor_from_class returned None.")
        return None

    trc = actor.text_render  # TextRenderComponent

    # Text content — set_editor_property ensures dirty flag + undo capture
    trc.set_editor_property("text", text)

    # Color (FColor, 0-255)
    fcolor = _hex_to_fcolor(style.get("color", "#FFFFFF"))
    trc.set_editor_property("text_render_color", fcolor)

    # Font size
    trc.set_editor_property("world_size", float(style.get("world_size", 100.0)))

    # Alignment
    h_key = style.get("h_align", "center")
    v_key = style.get("v_align", "center")
    trc.set_editor_property(
        "horizontal_alignment",
        _H_ALIGN.get(h_key, _H_ALIGN["center"]),
    )
    trc.set_editor_property(
        "vertical_alignment",
        _V_ALIGN.get(v_key, _V_ALIGN["center"]),
    )

    # Scale and spacing
    trc.set_editor_property("x_scale",             float(style.get("x_scale", 1.0)))
    trc.set_editor_property("y_scale",             float(style.get("y_scale", 1.0)))
    trc.set_editor_property("horiz_spacing_adjust", float(style.get("horiz_spacing", 0.0)))
    trc.set_editor_property("vert_spacing_adjust",  float(style.get("vert_spacing", 0.0)))

    # World Outliner organisation
    actor.set_actor_label(label)
    actor.set_folder_path(f"/{folder}")

    return actor


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="text_place",
    category="Text & Signs",
    description="Place a single styled 3D text actor at a world location.",
    shortcut="Ctrl+Alt+T",
    tags=["text", "place", "sign", "label", "3d"],
)
def run_text_place(
    text: str = "TOOLBELT",
    location: Tuple[float, float, float] = (0.0, 0.0, 200.0),
    rotation_yaw: float = 0.0,
    color: Optional[str] = None,
    world_size: Optional[float] = None,
    h_align: Optional[str] = None,
    v_align: Optional[str] = None,
    style: Optional[str] = None,
    folder: str = TEXT_FOLDER,
    **kwargs,
) -> Optional[unreal.TextRenderActor]:
    """
    Args:
        text:         The string to display in world space.
        location:     (x, y, z) world position in cm.
        rotation_yaw: Yaw rotation in degrees (0 = faces +X direction).
        color:        Hex color override, e.g. "#FF2200". Overrides style.
        world_size:   Font height in UU (cm). Overrides style.
        h_align:      "left", "center", or "right". Overrides style.
        v_align:      "top", "center", or "bottom". Overrides style.
        style:        Named style preset to load as base.
        folder:       World Outliner folder for the actor.

    Returns:
        The spawned TextRenderActor (useful if calling from another tool).
    """
    style_data = _resolve_style(style, {
        "color": color,
        "world_size": world_size,
        "h_align": h_align,
        "v_align": v_align,
    })

    loc = unreal.Vector(*location)
    rot = unreal.Rotator(0, rotation_yaw, 0)
    safe_label = f"Text_{text[:20].replace(' ', '_')}"

    with undo_transaction(f"Text Painter: Place '{text}'"):
        actor = _spawn_text_actor(text, loc, rot, style_data, label=safe_label, folder=folder)

    if actor:
        log_info(f"Placed text '{text}' at {location}.")
    return actor


@register_tool(
    name="text_label_selection",
    category="Text & Signs",
    description="Auto-label every selected actor with its own name, floating above it.",
    tags=["text", "label", "selection", "auto", "name"],
)
def run_text_label_selection(
    offset_z: float = 200.0,
    color: str = "#00FFCC",
    world_size: float = 60.0,
    style: Optional[str] = None,
    rotation_yaw: float = 0.0,
    **kwargs,
) -> None:
    """
    Great for zone tagging, debugging actor layouts, or creating a visual
    reference of your level's actor names.

    Args:
        offset_z:     Height above the actor's origin to place the text (cm).
        color:        Hex color for all label text.
        world_size:   Font size in UU.
        style:        Named style preset (color/size overridden if also specified).
        rotation_yaw: Yaw for all label actors.
    """
    actors = require_selection()
    if actors is None:
        return

    style_data = _resolve_style(style, {"color": color, "world_size": world_size})
    rot = unreal.Rotator(0, rotation_yaw, 0)

    log_info(f"Labeling {len(actors)} actors…")

    with undo_transaction("Text Painter: Label Selection"):
        for actor in actors:
            loc = actor.get_actor_location()
            label_loc = unreal.Vector(loc.x, loc.y, loc.z + offset_z)
            label_text = actor.get_actor_label()
            _spawn_text_actor(
                label_text, label_loc, rot, style_data,
                label=f"Label_{label_text}",
                folder=f"{TEXT_FOLDER}/Labels",
            )

    log_info(f"Placed {len(actors)} label actors.")


@register_tool(
    name="text_paint_grid",
    category="Text & Signs",
    description="Paint a coordinate grid of text labels across a map area (A1, B2, ...).",
    tags=["text", "grid", "map", "coordinate", "zone"],
)
def run_text_paint_grid(
    cols: int = 4,
    rows: int = 4,
    origin: Tuple[float, float, float] = (0.0, 0.0, 10.0),
    cell_size: float = 2000.0,
    color: str = "#FFDD00",
    world_size: float = 100.0,
    style: Optional[str] = None,
    rotation_yaw: float = 0.0,
    **kwargs,
) -> None:
    """
    Generates grid labels like A1, A2 … D4 spaced evenly from origin.
    Useful for callout zones on competitive maps.

    Args:
        cols:       Number of columns (letters: A, B, C...).
        rows:       Number of rows (numbers: 1, 2, 3...).
        origin:     (x, y, z) world position of the A1 corner.
        cell_size:  Spacing between grid cells in cm.
        color:      Hex color for all grid text.
        world_size: Font size in UU.
        style:      Named style preset.
        rotation_yaw: Yaw rotation for all text actors.
    """
    if cols > 26:
        log_error("text_paint_grid: max 26 columns (A–Z).")
        return

    style_data = _resolve_style(style, {"color": color, "world_size": world_size})
    rot = unreal.Rotator(0, rotation_yaw, 0)
    ox, oy, oz = origin

    log_info(f"Painting {cols}×{rows} grid from {origin}…")

    with undo_transaction(f"Text Painter: Grid {cols}×{rows}"):
        for c in range(cols):
            col_letter = chr(ord("A") + c)
            for r in range(rows):
                cell_name = f"{col_letter}{r + 1}"
                loc = unreal.Vector(
                    ox + c * cell_size + cell_size / 2,
                    oy + r * cell_size + cell_size / 2,
                    oz,
                )
                _spawn_text_actor(
                    cell_name, loc, rot, style_data,
                    label=f"GridLabel_{cell_name}",
                    folder=f"{TEXT_FOLDER}/Grid",
                )

    log_info(f"Grid complete: {cols * rows} zone labels placed.")


@register_tool(
    name="text_color_cycle",
    category="Text & Signs",
    description="Place multiple text actors cycling through a color palette.",
    tags=["text", "color", "cycle", "palette", "multi"],
)
def run_text_color_cycle(
    texts: Optional[List[str]] = None,
    start_location: Tuple[float, float, float] = (0.0, 0.0, 200.0),
    spacing_x: float = 800.0,
    world_size: float = 100.0,
    rotation_yaw: float = 0.0,
    **kwargs,
) -> None:
    """
    Place a row of text actors, each one a different color from the palette.
    Useful for team labels, callout banners, or quick color reference.

    Args:
        texts:          List of strings to place. Defaults to color name labels.
        start_location: (x, y, z) of the first text actor.
        spacing_x:      Gap between each actor along X axis.
        world_size:     Font size in UU.
        rotation_yaw:   Yaw rotation for all actors.
    """
    if texts is None:
        texts = ["RED", "ORANGE", "YELLOW", "GREEN",
                 "CYAN",  "BLUE",   "PURPLE", "PINK"]

    rot = unreal.Rotator(0, rotation_yaw, 0)
    ox, oy, oz = start_location

    log_info(f"Placing {len(texts)} color-cycled text actors…")

    with undo_transaction("Text Painter: Color Cycle"):
        for i, t in enumerate(texts):
            hex_color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
            style_data = _resolve_style(None, {"color": hex_color, "world_size": world_size})
            loc = unreal.Vector(ox + i * spacing_x, oy, oz)
            _spawn_text_actor(
                t, loc, rot, style_data,
                label=f"ColorText_{i}_{t}",
                folder=f"{TEXT_FOLDER}/ColorCycle",
            )

    log_info("Color cycle complete.")


@register_tool(
    name="text_save_style",
    category="Text & Signs",
    description="Save a named text style preset for reuse across levels.",
    tags=["text", "style", "preset", "save"],
)
def run_text_save_style(
    style_name: str = "MyStyle",
    color: str = "#FFFFFF",
    world_size: float = 100.0,
    h_align: str = "center",
    v_align: str = "center",
    x_scale: float = 1.0,
    y_scale: float = 1.0,
    horiz_spacing: float = 0.0,
    vert_spacing: float = 0.0,
    **kwargs,
) -> None:
    """
    Save a style preset to Saved/UEFN_Toolbelt/text_styles.json.
    Load it later with  style="MyStyle"  in any text_* tool.

    Args:
        style_name:     Key to save under.
        color:          Hex color string.
        world_size:     Font size in UU.
        h_align:        "left", "center", or "right".
        v_align:        "top", "center", or "bottom".
        x_scale/y_scale: Font stretch.
        horiz/vert_spacing: Letter/line spacing adjust.
    """
    styles = _load_styles()
    styles[style_name] = {
        "color":         color,
        "world_size":    world_size,
        "h_align":       h_align,
        "v_align":       v_align,
        "x_scale":       x_scale,
        "y_scale":       y_scale,
        "horiz_spacing": horiz_spacing,
        "vert_spacing":  vert_spacing,
    }
    _save_styles(styles)
    log_info(f"Text style '{style_name}' saved → {STYLES_FILE}")


@register_tool(
    name="text_list_styles",
    category="Text & Signs",
    description="Print all saved text style presets.",
    tags=["text", "style", "list"],
)
def run_text_list_styles(**kwargs) -> None:
    styles = _load_styles()
    if not styles:
        log_info("No saved text styles yet. Use text_save_style to create one.")
        return
    lines = ["\n=== Text Painter — Saved Styles ==="]
    for name, s in styles.items():
        lines.append(
            f"  {name:20s}  color={s.get('color','?'):8s}  "
            f"size={s.get('world_size',100):5.0f}  "
            f"align={s.get('h_align','center')}/{s.get('v_align','center')}"
        )
    log_info("\n".join(lines))


@register_tool(
    name="text_clear_folder",
    category="Text & Signs",
    description="Delete all TextRenderActors in the Toolbelt text folder (undoable).",
    tags=["text", "clear", "delete", "cleanup"],
)
def run_text_clear_folder(folder: str = TEXT_FOLDER, **kwargs) -> None:
    """
    Args:
        folder: World Outliner folder to clear (default: ToolbeltText).
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()

    to_delete = [
        a for a in all_actors
        if (isinstance(a, unreal.TextRenderActor) and
            folder in (a.get_folder_path() or ""))
    ]

    if not to_delete:
        log_info(f"No text actors found in folder '/{folder}'.")
        return

    with undo_transaction(f"Text Painter: Clear {folder}"):
        actor_sub.destroy_actors(to_delete)

    log_info(f"Deleted {len(to_delete)} text actors from '/{folder}'.")
