import unreal
from ..registry import register_tool
from ..core import log_info, log_error, undo_transaction

MOODS = {
    "Star Wars": {
        "SunIntensity": 10.0,
        "SunColor": [1.0, 0.9, 0.8],
        "FogDensity": 0.05,
        "SkyBloom": 0.5,
        "ColorGrading": "Warm"
    },
    "Cyberpunk": {
        "SunIntensity": 2.0,
        "SunColor": [0.5, 0.0, 1.0], # Purple sun
        "FogDensity": 0.2,
        "SkyBloom": 2.0,
        "ColorGrading": "Contrast"
    },
    "Vibrant": {
        "SunIntensity": 12.0,
        "SunColor": [1.0, 1.0, 1.0],
        "FogDensity": 0.01,
        "SkyBloom": 0.1,
        "ColorGrading": "Saturated"
    }
}

@register_tool(
    name="light_cinematic_preset",
    category="Lighting",
    description="Applies a cinematic mood preset to the level's lighting actors.",
    tags=["light", "cinematic", "mood", "preset", "atmosphere"]
)
def run_light_cinematic_preset(mood: str = "Star Wars", **kwargs):
    """
    Finds standard lighting actors and applies preset values.
    """
    if mood not in MOODS:
        log_error(f"Mood not found: {mood}. Available: {list(MOODS.keys())}")
        return

    data = MOODS[mood]
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    
    with undo_transaction(f"Apply Cinematic Mood: {mood}"):
        # Find Directional Light
        for actor in all_actors:
            if isinstance(actor, unreal.DirectionalLight):
                comp = actor.light_component
                comp.set_intensity(data["SunIntensity"])
                color = unreal.LinearColor(data["SunColor"][0], data["SunColor"][1], data["SunColor"][2], 1.0)
                comp.set_light_color(color)
                log_info(f"✓ Adjusted Directional Light for {mood}")
            
            # Find Exponential Height Fog
            elif isinstance(actor, unreal.ExponentialHeightFog):
                comp = actor.get_component_by_class(unreal.ExponentialHeightFogComponent)
                if comp:
                    comp.set_fog_density(data["FogDensity"])
                    log_info(f"✓ Adjusted Fog for {mood}")

@register_tool(
    name="light_randomize_sky",
    category="Lighting",
    description="Randomizes the sun orientation and sky colors for look-dev.",
    tags=["light", "sky", "random", "lookdev"]
)
def run_light_randomize_sky(**kwargs):
    """
    Randomizes sun rotation.
    """
    import random
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    
    with undo_transaction("Randomize Sky"):
        for actor in all_actors:
            if isinstance(actor, unreal.DirectionalLight):
                new_rot = unreal.Rotator(random.uniform(-90, -10), random.uniform(0, 360), 0)
                actor.set_actor_rotation(new_rot, True)
                log_info(f"✓ New Sun Orientation: {new_rot}")
                break
