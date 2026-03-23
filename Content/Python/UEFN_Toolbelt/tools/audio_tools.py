"""
UEFN TOOLBELT — Audio Placement Tools
======================================
Spawn and configure AmbientSound actors in the level. These are standard
Unreal AmbientSound actors (not Fortnite music devices) — fully Python-accessible.

NOTE: To assign a sound asset, provide your project's asset path e.g.
      "/Game/Audio/MyAmbience". Leave blank to place the actor first,
      then assign the sound manually in the Details panel.

OPERATIONS:
  audio_place       — Spawn an AmbientSound actor at the camera position
  audio_set_volume  — Set volume multiplier on selected AmbientSound actors
  audio_set_radius  — Set attenuation override radius on selected sounds
  audio_list        — List all AmbientSound actors in the level

USAGE:
    import UEFN_Toolbelt as tb

    tb.run("audio_place", label="ForestAmb", volume=0.8)
    tb.run("audio_place", asset_path="/Game/Audio/A_ForestLoop", radius=2000.0)
    tb.run("audio_set_volume", volume=0.5)
    tb.run("audio_set_radius", radius=3000.0)
    tb.run("audio_list")
"""

from __future__ import annotations

import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning, undo_transaction


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _actor_sub() -> unreal.EditorActorSubsystem:
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _cam() -> unreal.Vector:
    try:
        loc, _ = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
        return loc
    except Exception:
        return unreal.Vector(0.0, 0.0, 0.0)


def _get_audio_comp(actor: unreal.Actor):
    try:
        return actor.get_component_by_class(unreal.AudioComponent)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="audio_place",
    category="Audio",
    description=(
        "Spawn an AmbientSound actor at the camera position. "
        "Optionally assign a sound asset from /Game/... and set volume/radius."
    ),
    tags=["audio", "sound", "ambient", "place", "spawn"]
)
def audio_place(asset_path: str = "", label: str = "AmbientSound",
                folder: str = "Audio", volume: float = 1.0,
                radius: float = 0.0, **kwargs) -> dict:
    loc = _cam()
    with undo_transaction("Place Ambient Sound"):
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.AmbientSound.static_class(), loc
        )
        if actor is None:
            return {"status": "error", "message": "spawn_actor_from_class returned None for AmbientSound."}

        actor.set_actor_label(label)
        if folder:
            actor.set_folder_path(folder)

        audio_comp = _get_audio_comp(actor)
        if audio_comp is None:
            log_warning("[AUDIO] AmbientSound spawned but AudioComponent not found — set sound manually.")
        else:
            # Assign sound asset if provided
            if asset_path:
                try:
                    sound_asset = unreal.load_asset(asset_path)
                    if sound_asset:
                        audio_comp.set_sound(sound_asset)
                        log_info(f"[AUDIO] Assigned sound: {asset_path}")
                    else:
                        log_warning(f"[AUDIO] Could not load asset: {asset_path}")
                except Exception as e:
                    log_warning(f"[AUDIO] set_sound failed: {e}")

            # Volume
            try:
                audio_comp.set_volume_multiplier(float(volume))
            except Exception as e:
                log_warning(f"[AUDIO] set_volume_multiplier failed: {e}")

            # Attenuation radius override
            if radius > 0.0:
                try:
                    audio_comp.set_editor_property("override_attenuation", True)
                    attn = audio_comp.get_editor_property("attenuation_overrides")
                    attn.set_editor_property("falloff_distance", float(radius))
                    audio_comp.set_editor_property("attenuation_overrides", attn)
                    log_info(f"[AUDIO] Attenuation radius → {radius}")
                except Exception as e:
                    log_warning(f"[AUDIO] Could not set attenuation radius: {e}")

    log_info(f"[AUDIO] Placed '{label}' at {loc}")
    return {
        "status": "ok",
        "label": label,
        "location": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
        "asset_path": asset_path,
        "volume": volume,
        "radius": radius,
    }


@register_tool(
    name="audio_set_volume",
    category="Audio",
    description="Set the volume multiplier on all selected AmbientSound actors.",
    tags=["audio", "volume", "bulk", "set"]
)
def audio_set_volume(volume: float = 1.0, **kwargs) -> dict:
    selected = list(_actor_sub().get_selected_level_actors() or [])
    if not selected:
        return {"status": "error", "message": "No actors selected."}

    changed, skipped = [], []
    with undo_transaction("Set Audio Volume"):
        for actor in selected:
            if not isinstance(actor, unreal.AmbientSound):
                skipped.append(actor.get_actor_label())
                continue
            comp = _get_audio_comp(actor)
            if comp is None:
                skipped.append(actor.get_actor_label())
                continue
            try:
                comp.set_volume_multiplier(float(volume))
                changed.append(actor.get_actor_label())
            except Exception as e:
                log_warning(f"[AUDIO] {actor.get_actor_label()}: {e}")
                skipped.append(actor.get_actor_label())

    log_info(f"[AUDIO] Volume={volume} → {len(changed)} sounds, skipped {len(skipped)}")
    return {"status": "ok", "volume": float(volume), "changed": len(changed),
            "skipped": len(skipped), "labels": changed}


@register_tool(
    name="audio_set_radius",
    category="Audio",
    description=(
        "Override the attenuation falloff radius on selected AmbientSound actors. "
        "Sets override_attenuation=True and applies falloff_distance."
    ),
    tags=["audio", "attenuation", "radius", "falloff", "bulk"]
)
def audio_set_radius(radius: float = 2000.0, **kwargs) -> dict:
    selected = list(_actor_sub().get_selected_level_actors() or [])
    if not selected:
        return {"status": "error", "message": "No actors selected."}

    changed, skipped = [], []
    with undo_transaction("Set Audio Radius"):
        for actor in selected:
            if not isinstance(actor, unreal.AmbientSound):
                skipped.append(actor.get_actor_label())
                continue
            comp = _get_audio_comp(actor)
            if comp is None:
                skipped.append(actor.get_actor_label())
                continue
            try:
                comp.set_editor_property("override_attenuation", True)
                attn = comp.get_editor_property("attenuation_overrides")
                attn.set_editor_property("falloff_distance", float(radius))
                comp.set_editor_property("attenuation_overrides", attn)
                changed.append(actor.get_actor_label())
            except Exception as e:
                log_warning(f"[AUDIO] {actor.get_actor_label()} radius failed: {e}")
                skipped.append(actor.get_actor_label())

    log_info(f"[AUDIO] Radius={radius} → {len(changed)} sounds, skipped {len(skipped)}")
    return {"status": "ok", "radius": float(radius), "changed": len(changed),
            "skipped": len(skipped), "labels": changed}


@register_tool(
    name="audio_list",
    category="Audio",
    description="List all AmbientSound actors in the level with their label, location, and folder.",
    tags=["audio", "list", "audit"]
)
def audio_list(**kwargs) -> dict:
    all_actors = list(_actor_sub().get_all_level_actors() or [])
    sounds = []
    for actor in all_actors:
        if isinstance(actor, unreal.AmbientSound):
            loc = actor.get_actor_location()
            entry = {
                "label":    actor.get_actor_label(),
                "folder":   str(actor.get_folder_path()),
                "location": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
            }
            comp = _get_audio_comp(actor)
            if comp:
                try:
                    sound = comp.get_editor_property("sound")
                    entry["asset"] = sound.get_path_name() if sound else ""
                except Exception:
                    entry["asset"] = ""
                try:
                    entry["volume"] = comp.get_editor_property("volume_multiplier")
                except Exception:
                    pass
            sounds.append(entry)

    log_info(f"[AUDIO] Found {len(sounds)} AmbientSound actors")
    for s in sounds:
        log_info(f"  {s['label']:30s}  vol={s.get('volume', '?')}")
    return {"status": "ok", "count": len(sounds), "sounds": sounds}
