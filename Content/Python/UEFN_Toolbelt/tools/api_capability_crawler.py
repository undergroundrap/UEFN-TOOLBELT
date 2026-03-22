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


@register_tool(
    name="api_sync_master",
    category="API Explorer",
    description="The Ultimate One-Click Sync: Combines Level Crawling + Verse Schema IQ and updates docs/DEVICE_API_MAP.md.",
    tags=["sync", "docs", "master", "capabilities", "automation"],
)
def api_sync_master(**kwargs) -> str:
    """
    Unifies all Toolbelt intelligence into one command.
    1. Scans live actors for Python API methods.
    2. Scans Verse digests for Schema properties/events.
    3. Merges and updates DEVICE_API_MAP.md automatically.
    """
    from .verse_schema import _parser as verse_parser
    
    # 1. Run Level Crawler
    core.log_info("Step 1/3: Crawling live level actors...")
    level_schema_path = crawl_level_classes()
    if not level_schema_path or not os.path.exists(level_schema_path):
        return "Failed to crawl level classes."
        
    with open(level_schema_path, 'r', encoding='utf-8') as f:
        level_data = json.load(f)
    
    # 2. Refresh Verse Schema
    core.log_info("Step 2/3: Refreshing Verse Schema IQ from digests...")
    verse_parser.load_digests()
    
    # 3. Merge and Document
    core.log_info("Step 3/3: Merging data and updating DEVICE_API_MAP.md...")
    
    md_content = [
        "# Fortnite Device API Map (Master Sync)",
        "",
        "This document is a unified map of Python-exposed methods and Verse-exposed properties.",
        "Generated automatically by `api_sync_master`.",
        "",
        "| Class | Source | Key Methods / Properties / Events |",
        "| :--- | :--- | :--- |"
    ]
    
    all_classes = sorted(list(set(list(level_data["classes"].keys()) + list(verse_parser.device_schemas.keys()))))
    
    for cls in all_classes:
        level_info = level_data["classes"].get(cls)
        verse_info = verse_parser.device_schemas.get(cls)
        
        source = []
        if level_info: source.append("Live")
        if verse_info: source.append("Verse")
        
        # Collect top items
        items = []
        if level_info:
            # Add top 3 methods
            methods = [m for m in level_info.get("methods", []) if not m.startswith("get_") and not m.startswith("set_")]
            items.extend(methods[:3])
            
        if verse_info:
            # Add top 3 properties/events
            props = list(verse_info.get("properties", {}).keys())[:2]
            events = verse_info.get("events", [])[:1]
            items.extend(props)
            items.extend(events)
            
        entry = ", ".join([f"`{i}`" for i in items]) or "*(Introspecting...)*"
        md_content.append(f"| `{cls}` | {[' + '.join(source)]} | {entry} |")

    md_content.append("\n---\n*Last Sync: Generated by UEFN Toolbelt Master Sync Tool*")
    
    # Write to project docs (Self-resolving path for UEFN project structures)
    curr = os.path.abspath(__file__)
    project_root = None
    while curr and os.path.dirname(curr) != curr:
        curr = os.path.dirname(curr)
        if os.path.basename(curr) == "Content":
            project_root = os.path.dirname(curr)
            break
    
    if not project_root:
        project_root = unreal.Paths.project_dir()
    doc_path = os.path.join(project_root, "docs", "DEVICE_API_MAP.md")
    os.makedirs(os.path.dirname(doc_path), exist_ok=True)
    
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_content))
        
    core.log_info(f"✓ Master Sync Complete! Document updated: {doc_path}")
    return doc_path
