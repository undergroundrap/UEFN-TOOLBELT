"""
UEFN TOOLBELT — API Capability Crawler
========================================
Headless reflection and debugging crawler for UEFN.
Because UEFN locks down many internal properties, Epic's documentation is often
incomplete. This tool brute-forces introspection on live level actors to map
out exactly what variables are exposed to Python in the current patch.
"""

import os
import json
import unreal
from typing import Any, Dict, List, Set
from .. import core
from ..registry import register_tool


def _introspect_object(obj: unreal.Object) -> Dict[str, Any]:
    """
    Use Python reflection to brute-force determine what properties are exposed
    on a given Unreal Object.

    Returns a detailed schema dictionary.
    """
    schema: Dict[str, Any] = {
        "class": type(obj).__name__,
        "properties": {},
        "methods": [],
        "components": {}
    }

    # Safe attributes to skip
    _skips = {"set_editor_property", "get_editor_property", "set_editor_properties",
              "get_class", "get_components_by_class"}

    # 1. Map properties and methods via `dir()`
    for attr in dir(obj):
        if attr.startswith("__") or attr in _skips:
            continue
            
        try:
            val = getattr(obj, attr)
            if callable(val):
                schema["methods"].append(attr)
                continue
        except Exception:
            # If getattr fails natively, it's heavily protected.
            pass

        # 2. Test if it's an editor property (Data variable)
        try:
            val = obj.get_editor_property(attr)
            val_type = type(val).__name__ if val is not None else "Any"
            
            # Simple serialization of value for primitives
            rep = None
            if isinstance(val, (int, float, str, bool)):
                rep = val
            elif isinstance(val, unreal.EnumBase):
                rep = str(val)
            elif isinstance(val, unreal.Name):
                rep = str(val)
            elif isinstance(val, unreal.Vector):
                rep = {"x": round(val.x, 3), "y": round(val.y, 3), "z": round(val.z, 3)}
            
            schema["properties"][attr] = {
                "type": val_type,
                "readable": True,
                "example_value": rep
            }
        except Exception as e:
            err = str(e)
            if "not found" not in err.lower():
                # It is a property, but might fail to read (e.g., array without index)
                schema["properties"][attr] = {
                    "type": "Unknown/Restricted",
                    "readable": False,
                    "error": err
                }

    # 3. If it's an Actor, walk its Component Hierarchy
    if isinstance(obj, unreal.Actor):
        try:
            components = obj.get_components_by_class(unreal.ActorComponent)
            for c in components:
                # Recursively introspect components
                c_name = c.get_name()
                schema["components"][c_name] = _introspect_object(c)
        except Exception as e:
            schema["components"]["_error"] = str(e)

    return schema


@register_tool(
    name="api_crawl_selection",
    category="API Explorer",
    description="Deep introspect selected actors, components, and properties to JSON.",
    tags=["crawler", "fuzz", "reflection", "deep scan", "capabilities"],
)
def crawl_selection(**kwargs) -> str:
    """
    Reads the deeply nested exposed properties of the currently selected
    actor(s) and writes a comprehensive JSON graph to disk.
    Invaluable for Verse devs trying to reverse-engineer Fortnite devices.
    """
    actors = core.require_selection()
    if not actors:
        return ""

    core.log_info(f"Crawling capabilities for {len(actors)} actor(s)...")
    
    report = {
        "scan_target": "selection",
        "actor_count": len(actors),
        "data": {}
    }

    with core.with_progress(actors, "Deep-Scanning Actors") as bars:
        for actor in bars:
            label = actor.get_actor_label()
            report["data"][label] = _introspect_object(actor)

    # Save to disk
    import unreal
    saved_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved_dir, exist_ok=True)
    out_path = os.path.join(saved_dir, "api_selection_crawl.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    core.log_info(f"✓ Selection crawl saved: {out_path}")
    return out_path


@register_tool(
    name="api_crawl_level_classes",
    category="API Explorer",
    description="Headless map of all unique classes (and exposed properties) in the current level.",
    tags=["crawler", "fuzz", "level", "deep scan", "capabilities"],
)
def crawl_level_classes(**kwargs) -> str:
    """
    Headlessly scans every actor in the map. Aggregates them by Class.
    Runs deep introspection on exactly one instance of each class.
    Generates a master schema of what properties exist on the Fortnite devices
    used in your level.
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    if not all_actors:
        core.log_warning("No actors in the level.")
        return ""

    class_map: Dict[str, unreal.Actor] = {}
    for a in all_actors:
        cls_name = type(a).__name__
        if cls_name not in class_map:
            class_map[cls_name] = a

    core.log_info(f"Found {len(all_actors)} total actors, distilling to {len(class_map)} unique classes...")

    report = {
        "scan_target": "level_unique_classes",
        "total_actors": len(all_actors),
        "unique_classes": len(class_map),
        "classes": {}
    }

    # Sort to scan alphabetically
    sorted_classes = sorted(list(class_map.keys()))
    
    with core.with_progress(sorted_classes, "Crawling Class Schemas") as bars:
        for cls_name in bars:
            actor = class_map[cls_name]
            report["classes"][cls_name] = _introspect_object(actor)

    # Save to disk
    saved_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved_dir, exist_ok=True)
    out_path = os.path.join(saved_dir, "api_level_classes_schema.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    core.log_info(f"✓ Level class schema saved: {out_path}")
    return out_path
