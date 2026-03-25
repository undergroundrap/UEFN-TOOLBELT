import os
import unreal
from ..registry import register_tool
from ..core import log_info, log_error, undo_transaction

@register_tool(
    name="select_in_radius",
    category="Selection",
    description="Selects all actors of a specific class within a radius of the current selection.",
    tags=["selection", "radius", "proximity", "filter"]
)
def run_select_in_radius(radius: float = 1000.0, actor_class_name: str = "StaticMeshActor", **kwargs) -> dict:
    """
    Selects actors within a radius of the existing selection (or world origin).

    Returns:
        dict: {"status", "count", "labels": [str]}
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
        labels = [a.get_actor_label() for a in to_select]
        log_info(f"Selected {len(to_select)} actors of class {actor_class_name} within {radius} units.")
        return {"status": "ok", "count": len(to_select), "labels": labels}

    log_info("No matching actors found in radius.")
    return {"status": "ok", "count": 0, "labels": []}

@register_tool(
    name="select_by_property",
    category="Selection",
    description="Selects actors where a property matches a specific value.",
    tags=["selection", "filter", "property", "query"]
)
def run_select_by_property(prop_name: str = "Actor Label", value: str = "", match_case: bool = False, **kwargs) -> dict:
    """
    Filters current selection or all actors by property value.

    Returns:
        dict: {"status", "count", "labels": [str]}
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = actor_sub.get_selected_level_actors()
    candidates = selected if selected else actor_sub.get_all_level_actors()

    to_select = []
    for actor in candidates:
        try:
            # Special case for Label
            if prop_name.lower() in ["actor label", "label"]:
                actual_val = actor.get_actor_label()
            else:
                # Quirk #7: get_editor_property raises on Verse-driven properties
                # that aren't tagged as editor properties. getattr is safe for all.
                actual_val = getattr(actor, prop_name, None)
                if actual_val is None:
                    continue

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
        labels = [a.get_actor_label() for a in to_select]
        log_info(f"Filtered to {len(to_select)} actors matching '{prop_name}={value}'.")
        return {"status": "ok", "count": len(to_select), "labels": labels}

    log_info("No actors matched the property criteria.")
    return {"status": "ok", "count": 0, "labels": []}

@register_tool(
    name="select_by_verse_tag",
    category="Selection",
    description="Selects actors that have a specific Verse tag.",
    tags=["selection", "verse", "tag", "filter"]
)
def run_select_by_verse_tag(tag_name: str = "", **kwargs) -> dict:
    """
    Selects actors with matching tags.

    Returns:
        dict: {"status", "count", "labels": [str]}
    """
    if not tag_name:
        log_error("Tag name is required.")
        return {"status": "error", "message": "Tag name is required."}

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()

    to_select = []
    for actor in all_actors:
        try:
            # actor.tags is a string array in UEFN; some actor types may not
            # expose it — guard to avoid AttributeError on non-standard actors.
            if tag_name in actor.tags:
                to_select.append(actor)
        except Exception:
            continue

    if to_select:
        actor_sub.set_selected_level_actors(to_select)
        labels = [a.get_actor_label() for a in to_select]
        log_info(f"Selected {len(to_select)} actors with tag '{tag_name}'.")
        return {"status": "ok", "count": len(to_select), "labels": labels}

    log_info(f"No actors found with tag '{tag_name}'.")
    return {"status": "ok", "count": 0, "labels": []}


# ── Named selection sets ───────────────────────────────────────────────────────
# Save the current selection as a named set (labels → JSON).
# Restore it any time — even after a restart — by re-selecting matching labels.

def _sets_path() -> str:
    saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved, exist_ok=True)
    return os.path.join(saved, "selection_sets.json")


def _load_sets() -> dict:
    import json as _json
    p = _sets_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return _json.load(f)
        except Exception:
            pass
    return {}


def _save_sets(data: dict) -> None:
    import json as _json
    with open(_sets_path(), "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2)


@register_tool(
    name="selection_save",
    category="Selection",
    description=(
        "Save the current viewport selection as a named set. "
        "Restore it any time with selection_restore — survives restarts."
    ),
    tags=["selection", "save", "set", "named", "team", "restore"],
)
def run_selection_save(name: str = "", **kwargs) -> dict:
    """
    Save the current actor selection under a name.

    Args:
        name: Set name, e.g. 'arena_props', 'player_spawns', 'my_section'
    """
    if not name:
        return {"status": "error", "error": "name is required. Example: 'arena_props' or 'my_section'"}
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = actor_sub.get_selected_level_actors()
    if not actors:
        return {"status": "error", "error": "No actors selected."}
    labels = [a.get_actor_label() for a in actors]
    sets = _load_sets()
    sets[name] = labels
    _save_sets(sets)
    log_info(f"selection_save: saved '{name}' ({len(labels)} actors)")
    return {"status": "ok", "name": name, "count": len(labels), "labels": labels}


@register_tool(
    name="selection_restore",
    category="Selection",
    description=(
        "Restore a previously saved named selection set. "
        "Matches actors by label — works across restarts."
    ),
    tags=["selection", "restore", "set", "named", "team"],
)
def run_selection_restore(name: str = "", **kwargs) -> dict:
    """
    Re-select all actors matching a saved selection set by label.

    Args:
        name: Set name saved with selection_save
    """
    if not name:
        return {"status": "error", "error": "name is required."}
    sets = _load_sets()
    if name not in sets:
        return {"status": "error", "error": f"Selection set '{name}' not found.", "available": list(sets.keys())}
    target_labels = {lbl.lower() for lbl in sets[name]}
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    # Match first occurrence per label — avoids duplicate-label actors in the level
    seen = set()
    matched = []
    for a in all_actors:
        lbl = a.get_actor_label().lower()
        if lbl in target_labels and lbl not in seen:
            matched.append(a)
            seen.add(lbl)
    if matched:
        actor_sub.set_selected_level_actors(matched)
    missing = len(target_labels) - len(matched)
    log_info(f"selection_restore: restored '{name}' — {len(matched)} matched, {missing} not found")
    return {
        "status": "ok",
        "name": name,
        "matched": len(matched),
        "missing": missing,
        "labels": [a.get_actor_label() for a in matched],
    }


@register_tool(
    name="selection_list",
    category="Selection",
    description="List all saved named selection sets with their actor counts.",
    tags=["selection", "list", "set", "named", "team"],
)
def run_selection_list(**kwargs) -> dict:
    """Return all saved selection sets."""
    sets = _load_sets()
    return {
        "status": "ok",
        "count": len(sets),
        "sets": {name: {"actors": len(labels), "labels": labels} for name, labels in sets.items()},
        "tip": "Use selection_restore with a name to re-select any saved set.",
    }
