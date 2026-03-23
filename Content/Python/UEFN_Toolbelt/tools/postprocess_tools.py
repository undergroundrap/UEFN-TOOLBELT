"""
UEFN TOOLBELT — Post-Process & World Settings
==============================================
Spawn and configure PostProcessVolumes, apply visual presets, and tweak
world-level parameters (gravity, time dilation, fog).

OPERATIONS:
  postprocess_spawn   — Spawn or find a global (infinite-extent) PostProcessVolume
  postprocess_set     — Set bloom, exposure, contrast, vignette, saturation on the PPV
  postprocess_preset  — Apply a named visual preset (cinematic, night, vibrant, etc.)
  world_settings_set  — Change world-level params: gravity, time dilation

USAGE:
    import UEFN_Toolbelt as tb

    tb.run("postprocess_spawn")
    tb.run("postprocess_set", bloom=2.0, exposure=-1.0, vignette=0.4)
    tb.run("postprocess_preset", preset="cinematic")
    tb.run("world_settings_set", gravity=-490.0)  # half gravity
"""

from __future__ import annotations

import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning, undo_transaction


# ─────────────────────────────────────────────────────────────────────────────
#  Presets
# ─────────────────────────────────────────────────────────────────────────────

_PRESETS: dict[str, dict] = {
    "cinematic": {"bloom": 0.675, "exposure": -1.0, "contrast": 1.2, "vignette": 0.4, "saturation": 1.1},
    "night":     {"bloom": 3.0,   "exposure": -3.0, "contrast": 1.5, "vignette": 0.8, "saturation": 0.5},
    "vibrant":   {"bloom": 0.2,   "exposure":  0.5, "contrast": 1.0, "vignette": 0.0, "saturation": 1.6},
    "bleach":    {"bloom": 0.1,   "exposure":  0.0, "contrast": 1.4, "vignette": 0.2, "saturation": 0.3},
    "horror":    {"bloom": 1.5,   "exposure": -2.0, "contrast": 1.8, "vignette": 0.9, "saturation": 0.1},
    "fantasy":   {"bloom": 1.8,   "exposure":  0.3, "contrast": 0.9, "vignette": 0.2, "saturation": 1.4},
    "reset":     {"bloom": 0.675, "exposure":  0.0, "contrast": 1.0, "vignette": 0.0, "saturation": 1.0},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _actor_sub() -> unreal.EditorActorSubsystem:
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _find_ppv() -> unreal.PostProcessVolume | None:
    """Return the first PostProcessVolume in the level, or None."""
    for actor in (_actor_sub().get_all_level_actors() or []):
        if isinstance(actor, unreal.PostProcessVolume):
            return actor
    return None


def _apply_settings(ppv: unreal.PostProcessVolume,
                    bloom=None, exposure=None,
                    contrast=None, vignette=None, saturation=None) -> dict:
    """
    Write PostProcessSettings fields on a PPV.
    Returns dict of what was applied.
    """
    applied = {}
    try:
        s = ppv.get_editor_property("settings")

        if bloom is not None:
            try:
                s.set_editor_property("override_bloom_intensity", True)
                s.set_editor_property("bloom_intensity", float(bloom))
            except Exception:
                s.override_bloom_intensity = True
                s.bloom_intensity = float(bloom)
            applied["bloom"] = float(bloom)

        if exposure is not None:
            # exposure_compensation is the EV bias
            try:
                s.set_editor_property("override_auto_exposure_bias", True)
                s.set_editor_property("auto_exposure_bias", float(exposure))
            except Exception:
                s.override_auto_exposure_bias = True
                s.auto_exposure_bias = float(exposure)
            applied["exposure"] = float(exposure)

        if contrast is not None:
            try:
                s.set_editor_property("override_color_contrast", True)
                s.set_editor_property("color_contrast", unreal.Vector4(
                    float(contrast), float(contrast), float(contrast), float(contrast)
                ))
            except Exception:
                pass
            applied["contrast"] = float(contrast)

        if vignette is not None:
            try:
                s.set_editor_property("override_vignette_intensity", True)
                s.set_editor_property("vignette_intensity", float(vignette))
            except Exception:
                s.override_vignette_intensity = True
                s.vignette_intensity = float(vignette)
            applied["vignette"] = float(vignette)

        if saturation is not None:
            try:
                s.set_editor_property("override_color_saturation", True)
                s.set_editor_property("color_saturation", unreal.Vector4(
                    float(saturation), float(saturation), float(saturation), float(saturation)
                ))
            except Exception:
                pass
            applied["saturation"] = float(saturation)

        ppv.set_editor_property("settings", s)

    except Exception as e:
        log_error(f"[POSTPROCESS] Failed to apply settings: {e}")

    return applied


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="postprocess_spawn",
    category="Post-Process",
    description=(
        "Spawn a global (infinite-extent) PostProcessVolume. "
        "If one already exists it is returned without creating a duplicate."
    ),
    tags=["postprocess", "spawn", "volume", "global"]
)
def postprocess_spawn(unbounded: bool = True, **kwargs) -> dict:
    existing = _find_ppv()
    if existing:
        log_info(f"[POSTPROCESS] Found existing PPV: '{existing.get_actor_label()}'")
        return {"status": "ok", "action": "found", "label": existing.get_actor_label()}

    with undo_transaction("Spawn PostProcessVolume"):
        ppv = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.PostProcessVolume.static_class(),
            unreal.Vector(0.0, 0.0, 0.0)
        )
        if ppv is None:
            return {"status": "error", "message": "Failed to spawn PostProcessVolume."}

        ppv.set_actor_label("GlobalPostProcess")
        if unbounded:
            # Try both property name variants used across UE builds
            for prop in ("unbound", "is_unbounded", "bUnbound"):
                try:
                    ppv.set_editor_property(prop, True)
                    break
                except Exception:
                    pass

    log_info("[POSTPROCESS] Spawned global PostProcessVolume")
    return {"status": "ok", "action": "spawned", "label": "GlobalPostProcess"}


@register_tool(
    name="postprocess_set",
    category="Post-Process",
    description=(
        "Set post-process parameters on the first PostProcessVolume in the level. "
        "Only params you provide are changed. Run postprocess_spawn first if none exists."
    ),
    tags=["postprocess", "bloom", "exposure", "vignette", "saturation", "contrast"]
)
def postprocess_set(bloom=None, exposure=None, contrast=None,
                    vignette=None, saturation=None, **kwargs) -> dict:
    ppv = _find_ppv()
    if ppv is None:
        return {"status": "error", "message": "No PostProcessVolume in level. Run postprocess_spawn first."}

    with undo_transaction("Set Post-Process"):
        applied = _apply_settings(ppv, bloom=bloom, exposure=exposure,
                                   contrast=contrast, vignette=vignette,
                                   saturation=saturation)

    if not applied:
        return {"status": "error", "message": "No parameters were applied. Check UEFN log for details."}

    log_info(f"[POSTPROCESS] Applied: {applied}")
    return {"status": "ok", "applied": applied, "ppv": ppv.get_actor_label()}


@register_tool(
    name="postprocess_preset",
    category="Post-Process",
    description=(
        "Apply a named visual preset to the level's PostProcessVolume. "
        "Presets: cinematic, night, vibrant, bleach, horror, fantasy, reset."
    ),
    tags=["postprocess", "preset", "mood", "visual", "cinematic"]
)
def postprocess_preset(preset: str = "cinematic", **kwargs) -> dict:
    key = preset.lower().strip()
    if key not in _PRESETS:
        return {"status": "error", "message": f"Unknown preset '{preset}'. Available: {list(_PRESETS)}"}

    ppv = _find_ppv()
    if ppv is None:
        # Auto-spawn one
        postprocess_spawn()
        ppv = _find_ppv()
    if ppv is None:
        return {"status": "error", "message": "Could not find or create PostProcessVolume."}

    p = _PRESETS[key]
    with undo_transaction(f"PostProcess Preset: {key}"):
        applied = _apply_settings(ppv, bloom=p["bloom"], exposure=p["exposure"],
                                   contrast=p["contrast"], vignette=p["vignette"],
                                   saturation=p["saturation"])

    log_info(f"[POSTPROCESS] Preset '{key}' applied → {applied}")
    return {"status": "ok", "preset": key, "applied": applied}


@register_tool(
    name="world_settings_set",
    category="Post-Process",
    description=(
        "Change world-level parameters. "
        "gravity: Z acceleration in cm/s² (default -980). "
        "time_dilation: multiplier (1.0 = normal, 0.5 = half speed)."
    ),
    tags=["world", "gravity", "time", "dilation", "settings"]
)
def world_settings_set(gravity=None, time_dilation=None, **kwargs) -> dict:
    if gravity is None and time_dilation is None:
        return {"status": "error", "message": "Provide at least one of: gravity, time_dilation"}

    # WorldSettings is a special actor — find it in the level
    all_actors = list(_actor_sub().get_all_level_actors() or [])
    ws = None
    for actor in all_actors:
        if isinstance(actor, unreal.WorldSettings):
            ws = actor
            break

    if ws is None:
        # Fallback: try via world object
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            ws = world.get_world_settings()
        except Exception:
            pass

    if ws is None:
        return {"status": "error", "message": "Could not find WorldSettings actor."}

    applied = {}
    with undo_transaction("World Settings"):
        if gravity is not None:
            try:
                ws.set_editor_property("default_gravity_z", float(gravity))
                applied["gravity"] = float(gravity)
            except Exception as e:
                log_warning(f"[WORLD] Could not set gravity: {e}")

        if time_dilation is not None:
            try:
                ws.set_editor_property("default_world_gravity_z", float(gravity))
            except Exception:
                pass
            try:
                # TimeDilation is on the world itself, not WorldSettings in all builds
                world = unreal.EditorLevelLibrary.get_editor_world()
                world.set_editor_property("world_settings", ws)
            except Exception:
                pass
            # Direct approach
            try:
                ws.set_editor_property("time_dilation", float(time_dilation))
                applied["time_dilation"] = float(time_dilation)
            except Exception as e:
                log_warning(f"[WORLD] Could not set time_dilation: {e}")

    if not applied:
        return {"status": "error", "message": "No settings applied — check UEFN log for property name errors."}

    log_info(f"[WORLD] Applied: {applied}")
    return {"status": "ok", "applied": applied}
