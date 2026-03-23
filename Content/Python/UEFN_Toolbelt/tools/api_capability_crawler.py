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


def _is_valid(obj) -> bool:
    """Check if an Unreal object is safe to access (non-null C++ pointer)."""
    try:
        return obj is not None and bool(obj)
    except Exception:
        return False


def _introspect_object(obj: unreal.Object) -> Dict[str, Any]:
    """
    Use Python reflection to determine what properties are exposed
    on a given Unreal Object.

    Safe version: no component recursion, validates objects before access,
    skips callables that could dereference null C++ pointers.
    """
    if not _is_valid(obj):
        return {"class": "Invalid", "properties": {}, "methods": []}

    schema: Dict[str, Any] = {
        "class": type(obj).__name__,
        "properties": {},
        "methods": [],
    }

    # Only probe get_editor_property — never call getattr on unknown attrs
    # as shiboken can dereference null C++ pointers and crash the editor.
    _skips = frozenset({
        "set_editor_property", "get_editor_property", "set_editor_properties",
        "get_class", "get_components_by_class", "get_outer", "get_typed_outer",
        "get_world", "get_level", "static_class",
    })

    # 1. Collect method names via dir() — callable check only, no invocation
    for attr in dir(obj):
        if attr.startswith("_") or attr in _skips:
            continue
        try:
            val = getattr(obj, attr)
            if callable(val):
                schema["methods"].append(attr)
        except Exception:
            pass

    # 2. Probe editor properties — the only safe reflection path in UEFN
    for attr in list(schema["methods"]):
        pass  # methods already collected above

    # Probe known-safe property names via get_editor_property
    for attr in dir(obj):
        if attr.startswith("_") or attr in _skips or attr in schema["methods"]:
            continue
        try:
            val = obj.get_editor_property(attr)
            if not _is_valid(val) and val is not None:
                continue
            val_type = type(val).__name__ if val is not None else "Any"
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
                "example_value": rep,
            }
        except Exception as e:
            err = str(e)
            if "not found" not in err.lower() and "cannot" not in err.lower():
                schema["properties"][attr] = {
                    "type": "Unknown/Restricted",
                    "readable": False,
                    "error": err[:120],
                }

    return schema


@register_tool(
    name="api_crawl_selection",
    category="API Explorer",
    description="Deep introspect selected actors, components, and properties to JSON.",
    tags=["crawler", "fuzz", "reflection", "deep scan", "capabilities"],
)
def crawl_selection(**kwargs) -> dict:
    """
    Reads the deeply nested exposed properties of the currently selected
    actor(s) and writes a comprehensive JSON graph to disk.
    Invaluable for Verse devs trying to reverse-engineer Fortnite devices.
    """
    actors = core.require_selection()
    if not actors:
        return {"status": "error", "message": "No actors selected.", "path": ""}

    core.log_info(f"Crawling capabilities for {len(actors)} actor(s)...")

    report = {
        "scan_target": "selection",
        "actor_count": len(actors),
        "data": {}
    }

    for actor in actors:
        label = actor.get_actor_label()
        unreal.log(f"[TOOLBELT] Crawling: {label}")
        report["data"][label] = _introspect_object(actor)

    # Save to disk
    import unreal
    saved_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved_dir, exist_ok=True)
    out_path = os.path.join(saved_dir, "api_selection_crawl.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    core.log_info(f"✓ Selection crawl saved: {out_path}")
    return {"status": "ok", "path": out_path, "count": len(actors)}


def _sync_to_repo(src_path: str, filename: str) -> str:
    """
    Helper to copy a generated file from the Saved/ directory to the project's docs/ 
    folder for Git tracking and AI context.
    """
    import shutil
    try:
        # Find project root
        curr = os.path.abspath(__file__)
        project_root = None
        while curr and os.path.dirname(curr) != curr:
            curr = os.path.dirname(curr)
            if os.path.basename(curr) == "Content":
                project_root = os.path.dirname(curr)
                break
        
        if not project_root:
            import unreal
            project_root = unreal.Paths.project_dir()
            
        repo_docs = os.path.join(project_root, "docs")
        os.makedirs(repo_docs, exist_ok=True)
        dst_path = os.path.join(repo_docs, filename)
        
        shutil.copy2(src_path, dst_path)
        return dst_path
    except Exception as e:
        core.log_warning(f"Schema Sync: Failed to copy {filename} to project docs: {e}")
        return ""


@register_tool(
    name="api_crawl_level_classes",
    category="API Explorer",
    description="Headless map of all unique classes (and exposed properties) in the current level.",
    tags=["crawler", "fuzz", "level", "deep scan", "capabilities"],
)
def crawl_level_classes(**kwargs) -> dict:
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
        return {"status": "error", "message": "No actors in the level.", "path": ""}

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

    # Sort to scan alphabetically — no progress bar (PySide6 ticking during
    # heavy reflection can dereference null C++ pointers and crash the editor)
    sorted_classes = sorted(list(class_map.keys()))
    for i, cls_name in enumerate(sorted_classes):
        actor = class_map[cls_name]
        unreal.log(f"[TOOLBELT] Crawling {i+1}/{len(sorted_classes)}: {cls_name}")
        report["classes"][cls_name] = _introspect_object(actor)

    # Save to disk
    saved_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved_dir, exist_ok=True)
    out_path = os.path.join(saved_dir, "api_level_classes_schema.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    core.log_info(f"✓ Level class schema saved: {out_path}")

    # Sync to repo docs for AI context
    repo_path = _sync_to_repo(out_path, "api_level_classes_schema.json")
    if repo_path:
        core.log_info(f"✓ Auto-synced to repo: {repo_path}")

    return {"status": "ok", "path": out_path, "unique_classes": len(class_map), "total_actors": len(all_actors)}


@register_tool(
    name="api_sync_master",
    category="API Explorer",
    description="The Ultimate One-Click Sync: Combines Level Crawling + Verse Schema IQ and updates docs/DEVICE_API_MAP.md.",
    tags=["sync", "docs", "master", "capabilities", "automation"],
)
def api_sync_master(**kwargs) -> dict:
    """
    Unifies all Toolbelt intelligence into one command.
    1. Scans live actors for Python API methods.
    2. Scans Verse digests for Schema properties/events.
    3. Merges and updates DEVICE_API_MAP.md automatically.
    """
    from .verse_schema import _parser as verse_parser

    # 1. Run Level Crawler
    core.log_info("Step 1/3: Crawling live level actors...")
    crawl_result = crawl_level_classes()
    level_schema_path = crawl_result.get("path", "") if isinstance(crawl_result, dict) else crawl_result
    if not level_schema_path or not os.path.exists(level_schema_path):
        return {"status": "error", "message": "Failed to crawl level classes."}
        
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
    return {"status": "ok", "path": doc_path}


@register_tool(
    name="world_state_export",
    category="API Explorer",
    description="Export the full live state of every actor in the level — transforms + readable device properties — to a single JSON Claude can reason about.",
    tags=["world", "state", "export", "ai", "automation", "snapshot"],
)
def world_state_export(**kwargs) -> dict:
    """
    Captures the complete live state of the level as a machine-readable JSON:
      - Every actor's label, class, location, rotation, scale, tags, visibility
      - Every readable editor property on each actor (device settings, channel
        assignments, game rules, etc.)

    This is the AI read layer — Claude loads this file to understand exactly
    what is in the level and how every device is currently configured before
    deciding what actions to take.

    Output: Saved/UEFN_Toolbelt/world_state.json
    Also auto-synced to docs/world_state.json for git tracking.
    """
    from datetime import datetime

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    if not all_actors:
        return {"status": "error", "message": "No actors in the level.", "count": 0}

    unreal.log(f"[TOOLBELT] world_state_export: capturing {len(all_actors)} actors...")

    actors_out = []
    for actor in all_actors:
        if not _is_valid(actor):
            continue

        # --- Transform ---
        try:
            loc = actor.get_actor_location()
            location = {"x": round(loc.x, 2), "y": round(loc.y, 2), "z": round(loc.z, 2)}
        except Exception:
            location = {}

        try:
            rot = actor.get_actor_rotation()
            rotation = {"pitch": round(rot.pitch, 2), "yaw": round(rot.yaw, 2), "roll": round(rot.roll, 2)}
        except Exception:
            rotation = {}

        try:
            sc = actor.get_actor_scale3d()
            scale = {"x": round(sc.x, 3), "y": round(sc.y, 3), "z": round(sc.z, 3)}
        except Exception:
            scale = {}

        # --- Tags ---
        try:
            tags = [str(t) for t in actor.tags] if actor.tags else []
        except Exception:
            tags = []

        # --- Visibility ---
        try:
            hidden = actor.is_hidden_ed()
        except Exception:
            hidden = False

        # --- Device properties (readable primitives only) ---
        props = {}
        for attr in dir(actor):
            if attr.startswith("_"):
                continue
            try:
                val = actor.get_editor_property(attr)
                if isinstance(val, (int, float, str, bool)):
                    props[attr] = val
                elif isinstance(val, unreal.EnumBase):
                    props[attr] = str(val)
                elif isinstance(val, unreal.Name):
                    props[attr] = str(val)
                elif isinstance(val, unreal.Vector):
                    props[attr] = {"x": round(val.x, 2), "y": round(val.y, 2), "z": round(val.z, 2)}
                elif isinstance(val, unreal.Rotator):
                    props[attr] = {"pitch": round(val.pitch, 2), "yaw": round(val.yaw, 2), "roll": round(val.roll, 2)}
            except Exception:
                pass

        actors_out.append({
            "label": actor.get_actor_label(),
            "class": type(actor).__name__,
            "location": location,
            "rotation": rotation,
            "scale": scale,
            "hidden": hidden,
            "tags": tags,
            "properties": props,
        })

    state = {
        "exported_at": datetime.now().isoformat(),
        "actor_count": len(actors_out),
        "actors": actors_out,
    }

    saved_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved_dir, exist_ok=True)
    out_path = os.path.join(saved_dir, "world_state.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    unreal.log(f"[TOOLBELT] ✓ World state saved: {out_path}")

    repo_path = _sync_to_repo(out_path, "world_state.json")
    if repo_path:
        unreal.log(f"[TOOLBELT] ✓ Auto-synced to repo: {repo_path}")

    return {"status": "ok", "path": out_path, "count": len(actors_out)}
