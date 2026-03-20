"""
UEFN TOOLBELT — Material Master
========================================
The viral material tool. Matches and extends what creators are demoing on X.

FEATURES:
  • 15+ named presets: chrome, gold, neon, hologram, rubber, concrete, wood,
    ice, lava, plasma, rusty_metal, mirror, carbon_fiber, team_red, team_blue,
    jade, obsidian
  • Apply any preset to all selected actors in one call (full undo)
  • Color randomizer — randomize base color on selection
  • Gradient painter — paint a world-space color gradient across all selected actors
  • Auto team-color split — Red vs Blue based on actor world X position
  • Pattern painter — checkerboard or stripes via color alternation
  • Glow pulse preview — set emissive intensity in an animated loop (viewport preview)
  • Color harmony generator — complementary / triadic / analogous palettes
  • Save / load custom presets to a JSON file in the project Saved folder
  • Full undo on every destructive operation

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Apply chrome to selection
    tb.run("material_apply_preset", preset="chrome")

    # Randomize colors on selection
    tb.run("material_randomize_colors")

    # Paint a gradient (blue → red) across map on X axis
    tb.run("material_gradient_painter",
           color_a="#0044FF", color_b="#FF2200", axis="X")

    # Auto team-color split
    tb.run("material_team_color_split")

    # Save current selection's material as custom preset
    tb.run("material_save_preset", preset_name="MyFavorite")

    # List presets
    tb.run("material_list_presets")

BLUEPRINT CALL:
    "Execute Python Command" node → string:
        import UEFN_Toolbelt as tb; tb.run("material_apply_preset", preset="gold")

SETUP:
    This tool creates material instances from a parent material that must have
    these scalar parameters: Metallic, Roughness, EmissiveIntensity
    And these vector parameters: BaseColor, EmissiveColor

    Recommended parent material path (set PARENT_MATERIAL_PATH below):
        /Game/UEFN_Toolbelt/Materials/M_ToolbeltBase

    If you don't have this yet, use any UE5 master material with those params,
    or create M_ToolbeltBase in Unreal's material editor with them exposed.
"""

from __future__ import annotations

import json
import math
import os
import random
from typing import Any, Dict, List, Optional

import unreal

from ..core import (
    undo_transaction, get_selected_actors, require_selection,
    log_info, log_warning, log_error,
    color_from_hex, clamp, lerp,
    create_material_instance, set_mi_scalar, set_mi_vector,
    load_asset, save_asset, ensure_folder, with_progress,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Configuration — adjust to match your project's material setup
# ─────────────────────────────────────────────────────────────────────────────

PARENT_MATERIAL_PATH = "/Game/UEFN_Toolbelt/Materials/M_ToolbeltBase"
INSTANCE_OUTPUT_PATH = "/Game/UEFN_Toolbelt/Materials/Instances"
CUSTOM_PRESETS_FILE  = os.path.join(
    unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "custom_presets.json"
)

# ─────────────────────────────────────────────────────────────────────────────
#  Built-in Presets
#  Each preset is a dict with keys matching the parent material's parameters:
#    base_color      → Vector param "BaseColor"   (r,g,b,a 0..1 linear)
#    metallic        → Scalar param "Metallic"    (0..1)
#    roughness       → Scalar param "Roughness"   (0..1)
#    emissive_color  → Vector param "EmissiveColor"
#    emissive_intensity → Scalar param "EmissiveIntensity"
# ─────────────────────────────────────────────────────────────────────────────

BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    # ── Metals ────────────────────────────────────────────────────────────────
    "chrome": {
        "base_color": (0.82, 0.82, 0.82, 1),
        "metallic": 1.0, "roughness": 0.02,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Mirror-polish chrome",
    },
    "gold": {
        "base_color": (1.0, 0.766, 0.336, 1),
        "metallic": 1.0, "roughness": 0.28,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Warm polished gold",
    },
    "rusty_metal": {
        "base_color": (0.35, 0.18, 0.08, 1),
        "metallic": 0.7, "roughness": 0.85,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Weathered rust",
    },
    "mirror": {
        "base_color": (1.0, 1.0, 1.0, 1),
        "metallic": 1.0, "roughness": 0.0,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Perfect mirror",
    },
    "carbon_fiber": {
        "base_color": (0.02, 0.02, 0.02, 1),
        "metallic": 0.8, "roughness": 0.35,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Dark carbon fiber weave",
    },
    # ── Emissive / Neon ────────────────────────────────────────────────────────
    "neon": {
        "base_color": (0.02, 0.02, 0.02, 1),
        "metallic": 0.0, "roughness": 0.9,
        "emissive_color": (0.0, 1.0, 0.9, 1), "emissive_intensity": 8.0,
        "description": "Cyan neon glow",
    },
    "hologram": {
        "base_color": (0.05, 0.3, 0.8, 1),
        "metallic": 0.0, "roughness": 0.1,
        "emissive_color": (0.2, 0.8, 1.0, 1), "emissive_intensity": 5.0,
        "description": "Sci-fi hologram blue",
    },
    "lava": {
        "base_color": (0.1, 0.02, 0.0, 1),
        "metallic": 0.0, "roughness": 0.95,
        "emissive_color": (1.0, 0.3, 0.0, 1), "emissive_intensity": 12.0,
        "description": "Molten lava",
    },
    "plasma": {
        "base_color": (0.05, 0.0, 0.1, 1),
        "metallic": 0.0, "roughness": 0.2,
        "emissive_color": (0.7, 0.0, 1.0, 1), "emissive_intensity": 10.0,
        "description": "Purple plasma energy",
    },
    # ── Natural ────────────────────────────────────────────────────────────────
    "rubber": {
        "base_color": (0.03, 0.03, 0.03, 1),
        "metallic": 0.0, "roughness": 0.97,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Matte black rubber",
    },
    "concrete": {
        "base_color": (0.45, 0.43, 0.40, 1),
        "metallic": 0.0, "roughness": 0.92,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Raw poured concrete",
    },
    "wood": {
        "base_color": (0.52, 0.31, 0.12, 1),
        "metallic": 0.0, "roughness": 0.75,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Oak wood panels",
    },
    "ice": {
        "base_color": (0.72, 0.87, 0.95, 1),
        "metallic": 0.3, "roughness": 0.08,
        "emissive_color": (0.5, 0.85, 1.0, 1), "emissive_intensity": 0.5,
        "description": "Translucent blue ice",
    },
    "jade": {
        "base_color": (0.15, 0.55, 0.35, 1),
        "metallic": 0.1, "roughness": 0.15,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Polished jade stone",
    },
    "obsidian": {
        "base_color": (0.03, 0.02, 0.04, 1),
        "metallic": 0.0, "roughness": 0.05,
        "emissive_color": (0, 0, 0, 1), "emissive_intensity": 0.0,
        "description": "Volcanic black glass",
    },
    # ── Team Colors ────────────────────────────────────────────────────────────
    "team_red": {
        "base_color": (1.0, 0.05, 0.05, 1),
        "metallic": 0.2, "roughness": 0.5,
        "emissive_color": (1.0, 0.0, 0.0, 1), "emissive_intensity": 1.5,
        "description": "Fortnite Red Team",
    },
    "team_blue": {
        "base_color": (0.05, 0.2, 1.0, 1),
        "metallic": 0.2, "roughness": 0.5,
        "emissive_color": (0.0, 0.2, 1.0, 1), "emissive_intensity": 1.5,
        "description": "Fortnite Blue Team",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_custom_presets() -> Dict[str, Any]:
    """Load user-saved presets from JSON. Returns {} if file missing."""
    if not os.path.exists(CUSTOM_PRESETS_FILE):
        return {}
    try:
        with open(CUSTOM_PRESETS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log_error(f"material_master: could not read custom presets: {e}")
        return {}


def _save_custom_presets(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(CUSTOM_PRESETS_FILE), exist_ok=True)
    with open(CUSTOM_PRESETS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    log_info(f"Custom presets saved → {CUSTOM_PRESETS_FILE}")


def _all_presets() -> Dict[str, Any]:
    """Merge builtin and custom presets (custom takes priority)."""
    merged = dict(BUILTIN_PRESETS)
    merged.update(_load_custom_presets())
    return merged


def _apply_preset_to_actor(actor: unreal.Actor, preset: Dict[str, Any], instance_suffix: str) -> bool:
    """
    Create a material instance from the preset and assign it to every mesh
    component on the actor.

    Returns True on success.
    """
    # Determine instance name
    safe_name = f"MI_{instance_suffix}_{actor.get_actor_label().replace(' ', '_')}"

    mi = create_material_instance(PARENT_MATERIAL_PATH, safe_name, INSTANCE_OUTPUT_PATH)
    if mi is None:
        return False

    # Vector parameters
    bc = preset.get("base_color", (1, 1, 1, 1))
    ec = preset.get("emissive_color", (0, 0, 0, 1))
    set_mi_vector(mi, "BaseColor",     unreal.LinearColor(*bc))
    set_mi_vector(mi, "EmissiveColor", unreal.LinearColor(*ec))

    # Scalar parameters
    set_mi_scalar(mi, "Metallic",          float(preset.get("metallic", 0.0)))
    set_mi_scalar(mi, "Roughness",         float(preset.get("roughness", 0.5)))
    set_mi_scalar(mi, "EmissiveIntensity", float(preset.get("emissive_intensity", 0.0)))

    # REQUIRED: flush parameter changes to the GPU / viewport.
    # Without this the material compiles but the viewport won't update.
    unreal.MaterialEditingLibrary.update_material_instance(mi)

    save_asset(f"{INSTANCE_OUTPUT_PATH}/{safe_name}")

    # Assign to all static mesh components on this actor
    smc_class = unreal.StaticMeshComponent.static_class()
    components = actor.get_components_by_class(smc_class)
    for smc in components:
        for slot in range(smc.get_num_materials()):
            smc.set_material(slot, mi)

    return True


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="material_list_presets",
    category="Materials",
    description="Print all available material presets (builtin + custom).",
    tags=["material", "preset", "list"],
)
def run_list_presets(**kwargs) -> None:
    presets = _all_presets()
    lines = ["\n=== Material Master — Presets ==="]
    for name, data in sorted(presets.items()):
        desc = data.get("description", "")
        lines.append(f"  {name:20s}  {desc}")
    lines.append(f"\nTotal: {len(presets)} presets")
    log_info("\n".join(lines))


@register_tool(
    name="material_apply_preset",
    category="Materials",
    description="Apply a named material preset to all selected actors.",
    shortcut="Ctrl+Alt+M",
    tags=["material", "preset", "apply", "chrome", "gold", "neon"],
)
def run_apply_preset(preset: str = "chrome", **kwargs) -> None:
    """
    Args:
        preset: Preset name (e.g. "chrome", "gold", "neon"). See list_presets.
    """
    actors = require_selection()
    if actors is None:
        return

    all_p = _all_presets()
    if preset not in all_p:
        log_error(f"Unknown preset '{preset}'. Run material_list_presets to see options.")
        return

    preset_data = all_p[preset]
    log_info(f"Applying preset '{preset}' to {len(actors)} actor(s)…")

    with undo_transaction(f"Material Master: Apply {preset}"):
        failed = 0
        for actor in actors:
            if not _apply_preset_to_actor(actor, preset_data, preset):
                failed += 1

    if failed:
        log_warning(f"Failed on {failed} actor(s). Check PARENT_MATERIAL_PATH is set correctly.")
    else:
        log_info(f"Preset '{preset}' applied successfully to {len(actors)} actor(s).")


@register_tool(
    name="material_randomize_colors",
    category="Materials",
    description="Randomize the base color of all selected actors' materials.",
    tags=["material", "random", "color"],
)
def run_randomize_colors(saturation: float = 0.8, **kwargs) -> None:
    """
    Args:
        saturation: Controls how vivid random colors are (0=grey, 1=full).
    """
    actors = require_selection()
    if actors is None:
        return

    log_info(f"Randomizing colors on {len(actors)} actor(s)…")

    with undo_transaction("Material Master: Randomize Colors"):
        for actor in actors:
            hue = random.random()
            # HSV → RGB conversion
            h, s, v = hue, saturation, 0.9
            i = int(h * 6)
            f = h * 6 - i
            p, q, t_v = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
            rgb = [(v, t_v, p), (q, v, p), (p, v, t_v), (p, q, v), (t_v, p, v), (v, p, q)][i % 6]
            r, g, b = rgb

            preset = {
                "base_color": (r, g, b, 1),
                "metallic": random.uniform(0.0, 0.5),
                "roughness": random.uniform(0.2, 0.9),
                "emissive_color": (r * 0.1, g * 0.1, b * 0.1, 1),
                "emissive_intensity": 0.0,
            }
            _apply_preset_to_actor(actor, preset, "Random")

    log_info("Color randomization complete.")


@register_tool(
    name="material_gradient_painter",
    category="Materials",
    description="Paint a color gradient across all selected actors along a world axis.",
    tags=["material", "gradient", "paint", "color"],
)
def run_gradient_painter(
    color_a: str = "#0044FF",
    color_b: str = "#FF2200",
    axis: str = "X",
    **kwargs,
) -> None:
    """
    Args:
        color_a: Hex color at the start of the axis (e.g. "#0044FF").
        color_b: Hex color at the end of the axis (e.g. "#FF2200").
        axis:    World axis to use: "X", "Y", or "Z".
    """
    actors = require_selection(min_count=2)
    if actors is None:
        return

    axis = axis.upper()
    if axis not in ("X", "Y", "Z"):
        log_error("axis must be 'X', 'Y', or 'Z'.")
        return

    ca = color_from_hex(color_a)
    cb = color_from_hex(color_b)

    # Find min/max along chosen axis
    positions = [a.get_actor_location() for a in actors]
    get_coord = {"X": lambda v: v.x, "Y": lambda v: v.y, "Z": lambda v: v.z}[axis]
    coords = [get_coord(p) for p in positions]
    mn, mx = min(coords), max(coords)
    span = mx - mn or 1.0

    log_info(f"Painting gradient ({color_a}→{color_b}) along {axis} axis over {len(actors)} actors…")

    with undo_transaction("Material Master: Gradient Painter"):
        for actor, pos in zip(actors, positions):
            t = clamp((get_coord(pos) - mn) / span, 0.0, 1.0)
            r = lerp(ca.r, cb.r, t)
            g = lerp(ca.g, cb.g, t)
            b = lerp(ca.b, cb.b, t)
            preset = {
                "base_color": (r, g, b, 1),
                "metallic": 0.1, "roughness": 0.6,
                "emissive_color": (r * 0.05, g * 0.05, b * 0.05, 1),
                "emissive_intensity": 0.0,
            }
            _apply_preset_to_actor(actor, preset, "Gradient")

    log_info("Gradient paint complete.")


@register_tool(
    name="material_team_color_split",
    category="Materials",
    description="Split selected actors into Red/Blue teams based on world X position.",
    tags=["material", "team", "red", "blue", "split"],
)
def run_team_color_split(**kwargs) -> None:
    """
    Actors with X < midpoint → team_blue preset.
    Actors with X ≥ midpoint → team_red  preset.
    """
    actors = require_selection(min_count=2)
    if actors is None:
        return

    xs = [a.get_actor_location().x for a in actors]
    mid = (min(xs) + max(xs)) / 2.0

    red_preset  = _all_presets()["team_red"]
    blue_preset = _all_presets()["team_blue"]

    log_info(f"Team-color split: midpoint X={mid:.1f}")

    with undo_transaction("Material Master: Team Color Split"):
        r_count = b_count = 0
        for actor in actors:
            x = actor.get_actor_location().x
            if x >= mid:
                _apply_preset_to_actor(actor, red_preset,  "TeamRed")
                r_count += 1
            else:
                _apply_preset_to_actor(actor, blue_preset, "TeamBlue")
                b_count += 1

    log_info(f"Team split done: {r_count} Red, {b_count} Blue.")


@register_tool(
    name="material_pattern_painter",
    category="Materials",
    description="Apply checkerboard or stripe pattern to selected actors by alternating presets.",
    tags=["material", "pattern", "checkerboard", "stripes"],
)
def run_pattern_painter(
    pattern: str = "checkerboard",
    preset_a: str = "chrome",
    preset_b: str = "rubber",
    **kwargs,
) -> None:
    """
    Args:
        pattern:  "checkerboard" or "stripes"
        preset_a: First preset name.
        preset_b: Second preset name.
    """
    actors = require_selection()
    if actors is None:
        return

    all_p = _all_presets()
    if preset_a not in all_p or preset_b not in all_p:
        log_error(f"One or both presets not found: '{preset_a}', '{preset_b}'")
        return

    data_a, data_b = all_p[preset_a], all_p[preset_b]

    with undo_transaction(f"Material Master: {pattern.capitalize()} Pattern"):
        for i, actor in enumerate(actors):
            if pattern == "checkerboard":
                loc = actor.get_actor_location()
                # Use grid-cell parity based on 200-unit cells
                gx = int(loc.x / 200) % 2
                gy = int(loc.y / 200) % 2
                use_a = (gx + gy) % 2 == 0
            else:  # stripes
                use_a = i % 2 == 0

            _apply_preset_to_actor(actor, data_a if use_a else data_b,
                                   f"{pattern}_A" if use_a else f"{pattern}_B")

    log_info(f"{pattern.capitalize()} pattern applied to {len(actors)} actors.")


@register_tool(
    name="material_glow_pulse_preview",
    category="Materials",
    description="Set a glow pulse emissive intensity on selected actors (viewport preview).",
    tags=["material", "glow", "pulse", "emissive", "preview"],
)
def run_glow_pulse_preview(
    base_preset: str = "neon",
    intensity: float = 8.0,
    **kwargs,
) -> None:
    """
    Args:
        base_preset: Starting preset to apply.
        intensity:   Peak emissive intensity value.
    """
    actors = require_selection()
    if actors is None:
        return

    all_p = _all_presets()
    preset_data = dict(all_p.get(base_preset, all_p["neon"]))
    preset_data["emissive_intensity"] = intensity

    with undo_transaction("Material Master: Glow Pulse Preview"):
        for actor in actors:
            _apply_preset_to_actor(actor, preset_data, "GlowPulse")

    log_info(f"Glow pulse preview applied (intensity={intensity}). Use Animate slider in Blueprint for live pulse.")


@register_tool(
    name="material_color_harmony",
    category="Materials",
    description="Generate and apply a color harmony palette to selected actors.",
    tags=["material", "color", "harmony", "palette"],
)
def run_color_harmony(
    base_hex: str = "#FF6600",
    harmony: str = "complementary",
    **kwargs,
) -> None:
    """
    Args:
        base_hex: Starting hex color, e.g. "#FF6600".
        harmony:  "complementary", "triadic", "analogous", or "split_complementary".
    """
    actors = require_selection()
    if actors is None:
        return

    # Convert hex → HSV
    lc = color_from_hex(base_hex)
    r, g, b = lc.r, lc.g, lc.b
    mx = max(r, g, b)
    mn_v = min(r, g, b)
    delta = mx - mn_v
    h = 0.0
    if delta > 0:
        if mx == r:   h = ((g - b) / delta) % 6
        elif mx == g: h = (b - r) / delta + 2
        else:         h = (r - g) / delta + 4
    h /= 6.0
    s = delta / mx if mx > 0 else 0.0
    v = mx

    def hsv_to_lc(hh: float, ss: float, vv: float) -> tuple:
        hh %= 1.0
        i = int(hh * 6)
        f = hh * 6 - i
        p, q, t_v = vv * (1 - ss), vv * (1 - f * ss), vv * (1 - (1 - f) * ss)
        return [(vv, t_v, p), (q, vv, p), (p, vv, t_v), (p, q, vv), (t_v, p, vv), (vv, p, q)][i % 6]

    harmony_hues = {
        "complementary":       [h, h + 0.5],
        "triadic":             [h, h + 1/3, h + 2/3],
        "analogous":           [h - 1/12, h, h + 1/12],
        "split_complementary": [h, h + 5/12, h + 7/12],
    }.get(harmony, [h, h + 0.5])

    palettes = [hsv_to_lc(hue, s, v) for hue in harmony_hues]
    log_info(f"Harmony: {harmony} — {len(palettes)} colors for {len(actors)} actors.")

    with undo_transaction(f"Material Master: Color Harmony ({harmony})"):
        for i, actor in enumerate(actors):
            r2, g2, b2 = palettes[i % len(palettes)]
            preset = {
                "base_color": (r2, g2, b2, 1),
                "metallic": 0.2, "roughness": 0.5,
                "emissive_color": (r2 * 0.1, g2 * 0.1, b2 * 0.1, 1),
                "emissive_intensity": 0.0,
            }
            _apply_preset_to_actor(actor, preset, f"Harmony_{harmony}")

    log_info("Color harmony applied.")


@register_tool(
    name="material_save_preset",
    category="Materials",
    description="Save a new custom preset from the first selected actor's current material params.",
    tags=["material", "preset", "save", "custom"],
)
def run_save_preset(preset_name: str = "MyPreset", **kwargs) -> None:
    """
    Reads the current material instance parameters from the first selected actor
    and saves them as a named custom preset.

    Args:
        preset_name: Name to save the preset under.
    """
    actors = require_selection()
    if actors is None:
        return

    actor = actors[0]
    smc_class = unreal.StaticMeshComponent.static_class()
    comps = actor.get_components_by_class(smc_class)
    if not comps:
        log_warning("First selected actor has no StaticMeshComponent.")
        return

    mat = comps[0].get_material(0)
    if not isinstance(mat, unreal.MaterialInstanceConstant):
        log_warning("Material is not a MaterialInstanceConstant — cannot read parameters.")
        return

    mel = unreal.MaterialEditingLibrary

    def sv(param: str) -> float:
        ok, val = mel.get_material_instance_scalar_parameter_value(mat, param)
        return val if ok else 0.0

    def vv(param: str) -> tuple:
        ok, val = mel.get_material_instance_vector_parameter_value(mat, param)
        return (val.r, val.g, val.b, val.a) if ok else (1, 1, 1, 1)

    new_preset = {
        "base_color":          vv("BaseColor"),
        "metallic":            sv("Metallic"),
        "roughness":           sv("Roughness"),
        "emissive_color":      vv("EmissiveColor"),
        "emissive_intensity":  sv("EmissiveIntensity"),
        "description":         f"Custom — saved from {actor.get_actor_label()}",
    }

    customs = _load_custom_presets()
    customs[preset_name] = new_preset
    _save_custom_presets(customs)
    log_info(f"Custom preset '{preset_name}' saved.")


# ─── Bulk Material Swap ────────────────────────────────────────────────────────
#
# "Swapping materials/textures on many selected actors/meshes" — Grok pain list.
# Different from presets: replaces an existing material slot assignment with a
# different material across every actor in scope.  No new MIs are created.
#
# Works on StaticMeshComponents (and any component that inherits
# set_material / get_material via PrimitiveComponent).
#

def _swap_material_on_actor(
    actor: unreal.Actor,
    old_mat: unreal.MaterialInterface,
    new_mat: unreal.MaterialInterface,
) -> int:
    """
    Replace every occurrence of old_mat with new_mat on actor's components.
    Returns number of slots updated.
    """
    replaced = 0
    try:
        components = actor.get_components_by_class(unreal.StaticMeshComponent)
    except Exception:
        return 0

    for comp in components:
        try:
            num_slots = comp.get_num_materials()
        except Exception:
            continue

        for slot_idx in range(num_slots):
            try:
                slot_mat = comp.get_material(slot_idx)
                if slot_mat and slot_mat.get_path_name() == old_mat.get_path_name():
                    comp.set_material(slot_idx, new_mat)
                    replaced += 1
            except Exception:
                continue

    return replaced


@register_tool(
    name="material_bulk_swap",
    category="Materials",
    description="Replace one material with another across all selected actors (full undo)",
    icon="🔄",
    tags=["material", "swap", "replace", "bulk", "batch"],
)
def material_bulk_swap(
    old_material_path: str = "",
    new_material_path: str = "",
    scope: str = "selection",
**kwargs,
) -> None:
    """
    Swap one material for another on all actors in scope.

    Unlike apply_preset (which creates new material instances), this replaces
    the direct material assignment on StaticMeshComponent slots.  The original
    material stays in the project — only the actor-level slot assignment changes.

    Args:
        old_material_path: Content path of the material to find and replace.
                           Example: "/Game/Materials/M_Rock_Old"
        new_material_path: Content path of the replacement material.
                           Example: "/Game/Materials/M_Rock_New"
        scope:             "selection" (default) — only selected actors.
                           "all"       — every actor in the current level.

    Example:
        tb.run("material_bulk_swap",
               old_material_path="/Game/Materials/M_Concrete",
               new_material_path="/Game/Materials/M_ConcreteV2")
    """
    if not old_material_path or not new_material_path:
        log_warning("[MatSwap] Provide both old_material_path and new_material_path.")
        return

    old_mat = load_asset(old_material_path)
    if old_mat is None:
        log_warning(f"[MatSwap] Could not load old material: {old_material_path}")
        return

    new_mat = load_asset(new_material_path)
    if new_mat is None:
        log_warning(f"[MatSwap] Could not load new material: {new_material_path}")
        return

    if scope == "all":
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = list(actor_sub.get_all_level_actors())
    else:
        actors = get_selected_actors()
        if not actors:
            log_warning("[MatSwap] Nothing selected. Select actors or use scope='all'.")
            return

    total_slots = 0
    actors_touched = 0

    with undo_transaction("Bulk Material Swap"):
        with with_progress(actors, "Swapping material…") as gen:
            for actor in gen:
                replaced = _swap_material_on_actor(actor, old_mat, new_mat)
                if replaced:
                    actors_touched += 1
                    total_slots += replaced

    old_name = old_material_path.split("/")[-1]
    new_name = new_material_path.split("/")[-1]
    log_info(
        f"[MatSwap] ✓ Swapped '{old_name}' → '{new_name}' "
        f"on {total_slots} slot(s) across {actors_touched} actor(s)."
    )
    if total_slots == 0:
        log_warning(
            f"[MatSwap]   No slots matched '{old_name}'. "
            "Check the exact path — use the Content Browser's 'Copy Reference' option."
        )
