import unreal
from ..registry import register_tool
from ..core import log_info, log_error, undo_transaction

@register_tool(
    name="select_in_radius",
    category="Selection",
    description="Selects all actors of a specific class within a radius of the current selection.",
    tags=["selection", "radius", "proximity", "filter"]
)
def run_select_in_radius(radius: float = 1000.0, actor_class_name: str = "StaticMeshActor", **kwargs):
    """
    Selects actors within a radius of the existing selection (or world origin).
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = actor_sub.get_selected_level_actors()
    
    # Use selection center or 0,0,0
    center = unreal.Vector(0, 0, 0)
    if selected:
        for a in selected:
            center += a.get_actor_location()
        center /= len(selected)

    # Resolve target class (dynamic lookup in unreal module)
    target_cls = getattr(unreal, actor_class_name, None)
    
    all_actors = actor_sub.get_all_level_actors()
    to_select = []
    
    for actor in all_actors:
        # Match by Python type if possible
        if target_cls and isinstance(actor, target_cls):
            match = True
        # Fallback to name matching (for UEFN specifics like FortStaticMeshActor)
        elif actor_class_name.lower() in actor.get_class().get_name().lower():
            match = True
        else:
            match = False
            
        if not match:
            continue
        
        dist = (actor.get_actor_location() - center).length()
        if dist <= radius:
            to_select.append(actor)

    if to_select:
        actor_sub.set_selected_level_actors(to_select)
        log_info(f"Selected {len(to_select)} actors of class {actor_class_name} within {radius} units.")
    else:
        log_info("No matching actors found in radius.")

@register_tool(
    name="select_by_property",
    category="Selection",
    description="Selects actors where a property matches a specific value.",
    tags=["selection", "filter", "property", "query"]
)
def run_select_by_property(prop_name: str = "Actor Label", value: str = "", match_case: bool = False, **kwargs):
    """
    Filters current selection or all actors by property value.
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = actor_sub.get_selected_level_actors()
    candidates = selected if selected else actor_sub.get_all_level_actors()
    
    to_select = []
    for actor in candidates:
        # Try to get property
        try:
            # Special case for Label
            if prop_name.lower() in ["actor label", "label"]:
                actual_val = actor.get_actor_label()
            else:
                actual_val = actor.get_editor_property(prop_name)
            
            # Compare
            s_val = str(actual_val)
            t_val = str(value)
            
            if not match_case:
                s_val = s_val.lower()
                t_val = t_val.lower()
                
            if t_val in s_val:
                to_select.append(actor)
        except Exception:
            continue

    if to_select:
        actor_sub.set_selected_level_actors(to_select)
        log_info(f"Filtered to {len(to_select)} actors matching '{prop_name}={value}'.")
    else:
        log_info("No actors matched the property criteria.")

@register_tool(
    name="select_by_verse_tag",
    category="Selection",
    description="Selects actors that have a specific Verse tag.",
    tags=["selection", "verse", "tag", "filter"]
)
def run_select_by_verse_tag(tag_name: str = "", **kwargs):
    """
    Selects actors with matching tags.
    """
    if not tag_name:
        log_error("Tag name is required.")
        return

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    
    to_select = []
    for actor in all_actors:
        # Actor.tags is a string array in UEFN
        if tag_name in actor.tags:
            to_select.append(actor)

    if to_select:
        actor_sub.set_selected_level_actors(to_select)
        log_info(f"Selected {len(to_select)} actors with tag '{tag_name}'.")
    else:
        log_info(f"No actors found with tag '{tag_name}'.")
