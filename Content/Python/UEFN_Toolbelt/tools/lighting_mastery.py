"""
UEFN TOOLBELT — Lighting Toolkit
=================================
Spawn, modify, and audit lights in the level. All mutating ops wrapped
in ScopedEditorTransaction for full Ctrl-Z undo support.

OPERATIONS:
  light_place            — Spawn a point/spot/rect/directional/sky light at camera
  light_set              — Set intensity, color, radius on selected lights
  sky_set_time           — Simulate time-of-day by pitching the directional light
  light_list             — Audit all lights in the level
  light_cinematic_preset — Apply a named mood preset (Star Wars / Cyberpunk / Vibrant)
  light_randomize_sky    — Randomise sun orientation for look-dev

USAGE:
    import UEFN_Toolbelt as tb

    tb.run("light_place", light_type="point", intensity=2000, color="#FFD580")
    tb.run("light_set", intensity=5000, color="#FF8040")
    tb.run("sky_set_time", hour=18.0)
    tb.run("light_list")
    tb.run("light_cinematic_preset", mood="Cyberpunk")
"""

from __future__ import annotations

import math
import random
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
        return unreal.Vector(0.0, 0.0, 200.0)


def _hex_to_linear(hex_color: str) -> unreal.LinearColor:
    """Convert #RRGGBB or RRGGBB hex string to LinearColor (0-1 range, gamma-corrected)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return unreal.LinearColor(r, g, b, 1.0)
    return unreal.LinearColor(1.0, 1.0, 1.0, 1.0)


def _get_light_comp(actor: unreal.Actor):
    """Return the first light component found on actor, or None."""
    for cls in (unreal.PointLightComponent, unreal.SpotLightComponent,
                unreal.RectLightComponent, unreal.DirectionalLightComponent):
        comp = actor.get_component_by_class(cls)
        if comp:
            return comp
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="light_place",
    category="Lighting",
    description=(
        "Spawn a light actor at the current camera position. "
        "light_type: point | spot | rect | directional | sky"
    ),
    tags=["light", "spawn", "place", "point", "spot", "rect"]
)
def light_place(light_type: str = "point", intensity: float = 1000.0,
                color: str = "#FFFFFF", attenuation: float = 1000.0,
                label: str = "", folder: str = "Lights", **kwargs) -> dict:
    cls_map = {
        "point":       unreal.PointLight,
        "spot":        unreal.SpotLight,
        "rect":        unreal.RectLight,
        "directional": unreal.DirectionalLight,
        "sky":         unreal.SkyLight,
    }
    key = light_type.lower().strip()
    if key not in cls_map:
        return {"status": "error", "message": f"Unknown light_type '{light_type}'. Use: {list(cls_map)}"}

    loc = _cam()
    with undo_transaction(f"Place {light_type} light"):
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            cls_map[key].static_class(), loc
        )
        if actor is None:
            return {"status": "error", "message": "spawn_actor_from_class returned None"}

        actor_label = label or f"{key.capitalize()}Light"
        actor.set_actor_label(actor_label)
        if folder:
            actor.set_folder_path(folder)

        # SkyLight has no intensity/color component accessible this way
        if key != "sky":
            comp = _get_light_comp(actor)
            if comp:
                comp.set_intensity(float(intensity))
                comp.set_light_color(_hex_to_linear(color))
                if key in ("point", "spot", "rect"):
                    try:
                        comp.set_editor_property("attenuation_radius", float(attenuation))
                    except Exception:
                        pass

    log_info(f"[LIGHTING] Placed {key} light '{actor_label}' at {loc}")
    return {
        "status": "ok",
        "light_type": key,
        "label": actor_label,
        "location": [loc.x, loc.y, loc.z],
        "intensity": intensity,
        "color": color,
    }


@register_tool(
    name="light_set",
    category="Lighting",
    description=(
        "Set intensity, color, and/or attenuation radius on all selected light actors. "
        "Only the params you pass are changed — omit any to leave it untouched."
    ),
    tags=["light", "set", "intensity", "color", "bulk"]
)
def light_set(intensity=None, color: str = "", attenuation=None, **kwargs) -> dict:
    selected = list(_actor_sub().get_selected_level_actors() or [])
    if not selected:
        return {"status": "error", "message": "No actors selected."}

    linear_color = _hex_to_linear(color) if color else None
    changed, skipped = [], []

    with undo_transaction("Set Light Properties"):
        for actor in selected:
            comp = _get_light_comp(actor)
            if comp is None:
                skipped.append(actor.get_actor_label())
                continue
            if intensity is not None:
                comp.set_intensity(float(intensity))
            if linear_color is not None:
                comp.set_light_color(linear_color)
            if attenuation is not None:
                try:
                    comp.set_editor_property("attenuation_radius", float(attenuation))
                except Exception:
                    pass
            changed.append(actor.get_actor_label())

    log_info(f"[LIGHTING] Modified {len(changed)} lights, skipped {len(skipped)}")
    return {
        "status": "ok",
        "changed": len(changed),
        "skipped": len(skipped),
        "labels": changed,
    }


@register_tool(
    name="sky_set_time",
    category="Lighting",
    description=(
        "Simulate time-of-day by adjusting the directional light's pitch. "
        "hour: 0-24 (6=sunrise, 12=noon, 18=sunset, 0/24=midnight)."
    ),
    tags=["light", "sky", "sun", "time", "day", "atmosphere"]
)
def sky_set_time(hour: float = 12.0, **kwargs) -> dict:
    hour = max(0.0, min(24.0, float(hour)))

    # Elevation: sun rises at 6, peaks at 12, sets at 18
    if 6.0 <= hour <= 18.0:
        t = (hour - 6.0) / 12.0            # 0 at dawn, 1 at noon via sin
        elevation = math.sin(t * math.pi) * 90.0
    else:
        # Night — sun below horizon
        if hour < 6.0:
            t = hour / 6.0
        else:
            t = (hour - 18.0) / 6.0
        elevation = -(t * 20.0 + 5.0)      # -5° to -25° below horizon

    # In UE, negative pitch = downward-facing = sun coming from above
    pitch = -elevation
    yaw = (hour / 24.0) * 360.0

    all_actors = list(_actor_sub().get_all_level_actors() or [])
    found = False
    with undo_transaction(f"Set Time of Day {hour:.1f}h"):
        for actor in all_actors:
            if isinstance(actor, unreal.DirectionalLight):
                cur = actor.get_actor_rotation()
                actor.set_actor_rotation(unreal.Rotator(pitch, yaw, cur.roll), False)
                found = True
                log_info(f"[LIGHTING] Sun → hour={hour:.1f}  pitch={pitch:.1f}  yaw={yaw:.1f}")
                break

    if not found:
        return {"status": "error", "message": "No DirectionalLight in level."}
    return {"status": "ok", "hour": hour, "pitch": pitch, "yaw": yaw}


@register_tool(
    name="light_list",
    category="Lighting",
    description="List all light actors in the level with their type, label, and location.",
    tags=["light", "list", "audit"]
)
def light_list(**kwargs) -> dict:
    light_classes = (
        unreal.PointLight, unreal.SpotLight, unreal.RectLight,
        unreal.DirectionalLight, unreal.SkyLight,
    )
    all_actors = list(_actor_sub().get_all_level_actors() or [])
    lights = []
    for actor in all_actors:
        for lc in light_classes:
            if isinstance(actor, lc):
                loc = actor.get_actor_location()
                entry = {
                    "label": actor.get_actor_label(),
                    "type":  type(actor).__name__,
                    "location": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
                }
                comp = _get_light_comp(actor)
                if comp:
                    try:
                        entry["intensity"] = comp.get_editor_property("intensity")
                    except Exception:
                        pass
                lights.append(entry)
                break

    log_info(f"[LIGHTING] Found {len(lights)} lights in level")
    for l in lights:
        log_info(f"  {l['type']:25s}  {l['label']}")
    return {"status": "ok", "count": len(lights), "lights": lights}


# ─────────────────────────────────────────────────────────────────────────────
#  Original tools (preserved + cleaned)
# ─────────────────────────────────────────────────────────────────────────────

MOODS = {
    "Star Wars":  {"SunIntensity": 10.0, "SunColor": [1.0, 0.9, 0.8], "FogDensity": 0.05},
    "Cyberpunk":  {"SunIntensity":  2.0, "SunColor": [0.5, 0.0, 1.0], "FogDensity": 0.20},
    "Vibrant":    {"SunIntensity": 12.0, "SunColor": [1.0, 1.0, 1.0], "FogDensity": 0.01},
}


@register_tool(
    name="light_cinematic_preset",
    category="Lighting",
    description="Apply a named mood preset to the level's directional light and fog. Moods: Star Wars, Cyberpunk, Vibrant.",
    tags=["light", "cinematic", "mood", "preset", "atmosphere"]
)
def run_light_cinematic_preset(mood: str = "Star Wars", **kwargs) -> dict:
    if mood not in MOODS:
        return {"status": "error", "message": f"Unknown mood '{mood}'. Available: {list(MOODS)}"}
    data = MOODS[mood]
    all_actors = list(_actor_sub().get_all_level_actors() or [])
    with undo_transaction(f"Apply Cinematic Mood: {mood}"):
        for actor in all_actors:
            if isinstance(actor, unreal.DirectionalLight):
                comp = actor.light_component
                comp.set_intensity(data["SunIntensity"])
                r, g, b = data["SunColor"]
                comp.set_light_color(unreal.LinearColor(r, g, b, 1.0))
                log_info(f"[LIGHTING] Directional light → {mood}")
            elif isinstance(actor, unreal.ExponentialHeightFog):
                comp = actor.get_component_by_class(unreal.ExponentialHeightFogComponent)
                if comp:
                    comp.set_fog_density(data["FogDensity"])
                    log_info(f"[LIGHTING] Fog density → {data['FogDensity']}")
    return {"status": "ok", "mood": mood}


@register_tool(
    name="light_randomize_sky",
    category="Lighting",
    description="Randomise sun orientation and pitch for quick look-dev iterations.",
    tags=["light", "sky", "random", "lookdev"]
)
def run_light_randomize_sky(**kwargs) -> dict:
    all_actors = list(_actor_sub().get_all_level_actors() or [])
    with undo_transaction("Randomize Sky"):
        for actor in all_actors:
            if isinstance(actor, unreal.DirectionalLight):
                new_rot = unreal.Rotator(
                    random.uniform(-90, -10),
                    random.uniform(0, 360),
                    0.0
                )
                actor.set_actor_rotation(new_rot, True)
                log_info(f"[LIGHTING] Sun → pitch={new_rot.pitch:.1f}  yaw={new_rot.yaw:.1f}")
                return {"status": "ok", "pitch": new_rot.pitch, "yaw": new_rot.yaw}
    return {"status": "ok", "pitch": None, "yaw": None}
