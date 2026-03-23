"""
UEFN TOOLBELT — Verse Device Bulk Editor
========================================
Edit properties on multiple Verse devices at once — bypasses the tedious
one-by-one click workflow that creators hate.

FEATURES:
  • List all Verse device actors in the current level
  • Filter by class name or label substring
  • Bulk-set any property (by property name string) on all matching devices
  • Export device property report to a JSON file
  • Select all devices of a given type in the viewport
  • Full undo on all property changes

USAGE:
    import UEFN_Toolbelt as tb

    # List all Verse devices
    tb.run("verse_list_devices")

    # Set "bIsEnabled" to False on all selected devices
    tb.run("verse_bulk_set_property",
           property_name="bIsEnabled",
           value=False)

    # Select all devices whose label contains "Trigger"
    tb.run("verse_select_by_name", name_filter="Trigger")

    # Export report of all device properties to Saved folder
    tb.run("verse_export_report")

NOTES:
  • Verse device classes are typically subclasses of
    unreal.FortAthenaDevice or similar Fortnite-specific classes.
  • This tool uses unreal.Actor.set_editor_property() which works on any
    UPROPERTY exposed to Blueprint/Python.
  • Some Fortnite device properties may be read-only in-editor — the tool
    logs a clear warning if a set fails rather than crashing.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import unreal

from ..core import (
    undo_transaction, get_selected_actors, require_selection,
    log_info, log_warning, log_error,
)
from ..registry import register_tool
from .. import schema_utils

# Fallback property list used when the reference schema has no entry for a class.
# Covers the most common shared Verse/Creative device properties.
_FALLBACK_PROPS = [
    "bIsEnabled", "bVisible", "bCanBeActivated",
    "TeamIndex", "MaxPlayers", "RespawnTime",
    "bAutoActivate", "ActivationDelay", "Health",
    "bShowActivationEffect", "InteractText",
]

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Common Verse/Fortnite device class name fragments to detect device actors.
# UEFN device actors typically have class names containing these strings.
_DEVICE_HINTS = [
    "Device", "FortAthena", "FortCreative", "FortniteDevice",
    "Beacon", "Trigger", "Timer", "SpawnPad", "Zone", "Tracker",
    "Mutator", "Button", "Chest", "Ammo", "Barrier",
]


def _is_verse_device(actor: unreal.Actor) -> bool:
    """Check whether an actor is a Verse/Creative device.

    Detection order (most → least reliable):
    1. Class path contains '_Verse.' — definitive Verse-compiled device
       (Quirk #5: Verse assets live in virtual /ProjectName/_Verse paths)
    2. Class path contains 'FortCreative' or 'FortniteGame' — engine devices
    3. Class name substring hints — broad fallback for BP/C++ devices
    """
    cls = actor.get_class()
    path = cls.get_path_name()
    class_name = cls.get_name()

    # Path-based detection is authoritative (Quirks #1 and #5)
    if "_Verse." in path or "/FortCreative/" in path or "/FortniteGame/" in path:
        return True

    return any(hint in class_name for hint in _DEVICE_HINTS)


def _get_all_devices() -> List[unreal.Actor]:
    """Return all device-like actors in the current level."""
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    return [a for a in all_actors if _is_verse_device(a)]


def _get_actor_properties(actor: unreal.Actor) -> Dict[str, Any]:
    """
    Read all discoverable properties from an actor.

    Property discovery order (most to least authoritative):
    1. Reference schema — look up the class in uefn_reference_schema.json
       and iterate its declared properties.
    2. Project-level schema — try api_level_classes_schema.json via
       schema_utils (same get_class_info call, falls through automatically).
    3. Fallback list — the hardcoded _FALLBACK_PROPS baseline when the class
       is unknown to any schema.

    Uses getattr instead of get_editor_property throughout (Quirk #7).
    """
    class_name = actor.get_class().get_name()

    # Try schema-driven discovery first
    schema_props = schema_utils.discover_properties(class_name)
    if schema_props:
        prop_names = list(schema_props.keys())
    else:
        prop_names = _FALLBACK_PROPS

    result: Dict[str, Any] = {}
    for prop in prop_names:
        # Quirk #7: use getattr — get_editor_property raises on Verse-driven props
        try:
            val = getattr(actor, prop, None)
            if val is not None:
                result[prop] = val
        except Exception:
            pass  # Property inaccessible on this actor type
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="verse_list_devices",
    category="Verse Helpers",
    description="List all Verse/Creative device actors in the current level.",
    tags=["verse", "device", "list", "enumerate"],
)
def run_list_devices(name_filter: str = "", **kwargs) -> dict:
    """
    Args:
        name_filter: Optional substring to filter by actor label.

    Returns:
        dict: {"status": "ok", "count": int, "devices": [{"label", "class", "location"}]}
    """
    devices = _get_all_devices()

    if name_filter:
        devices = [d for d in devices if name_filter.lower() in d.get_actor_label().lower()]

    if not devices:
        log_info("No Verse/Creative devices found in current level.")
        return {"status": "ok", "count": 0, "devices": []}

    records = []
    lines = [f"\n=== Verse Devices ({len(devices)}) ==="]
    for d in devices:
        class_name = d.get_class().get_name()
        label = d.get_actor_label()
        loc = d.get_actor_location()
        lines.append(f"  [{class_name:40s}]  '{label}'  @ ({loc.x:.0f}, {loc.y:.0f}, {loc.z:.0f})")
        records.append({"label": label, "class": class_name,
                        "location": {"x": loc.x, "y": loc.y, "z": loc.z}})
    lines.append("")
    log_info("\n".join(lines))
    return {"status": "ok", "count": len(devices), "devices": records}


@register_tool(
    name="verse_bulk_set_property",
    category="Verse Helpers",
    description="Set a property on all selected Verse device actors at once.",
    tags=["verse", "device", "property", "bulk", "edit"],
)
def run_bulk_set_property(
    property_name: str = "bIsEnabled",
    value: Any = True,
    use_all_devices: bool = False,
    **kwargs,
) -> dict:
    """
    Args:
        property_name:   The UPROPERTY name to set (e.g. "bIsEnabled", "TeamIndex").
        value:           The value to assign.
        use_all_devices: If True, apply to ALL devices in the level (not just selection).

    Returns:
        dict: {"status": "ok", "success": int, "failed": int}
    """
    if use_all_devices:
        actors = _get_all_devices()
        if not actors:
            log_warning("No Verse devices found in the level.")
            return {"status": "error", "message": "No Verse devices found."}
    else:
        actors = require_selection()
        if actors is None:
            return {"status": "error", "message": "No actors selected."}

    log_info(f"Setting '{property_name}' = {value!r} on {len(actors)} actor(s)…")

    success = failed = 0
    with undo_transaction(f"Verse Device Editor: Set {property_name}"):
        for actor in actors:
            # SCHEMA HARDENING: Validate property via reference schema
            cls_name = actor.get_class().get_name()
            validation = schema_utils.validate_property(cls_name, property_name)

            if validation["exists"]:
                meta = validation["meta"]
                if not meta.get("readable", True):
                    log_warning(f"  '{actor.get_actor_label()}': property '{property_name}' is MARKED READ-ONLY in schema.")
                    failed += 1
                    continue

                # Type hint for UX
                expected_type = meta.get("type", "Any")
                if expected_type != "Any" and type(value).__name__ != expected_type.lower():
                    log_info(f"  Note: Expected {expected_type}, received {type(value).__name__} for {property_name}")

            try:
                actor.set_editor_property(property_name, value)
                success += 1
            except Exception as e:
                log_warning(f"  '{actor.get_actor_label()}': could not set '{property_name}' — {e}")
                failed += 1

    log_info(f"Done. {success} succeeded, {failed} failed.")
    return {"status": "ok", "success": success, "failed": failed}


@register_tool(
    name="verse_select_by_name",
    category="Verse Helpers",
    description="Select all Verse device actors whose label contains a filter string.",
    tags=["verse", "device", "select", "filter"],
)
def run_select_by_name(name_filter: str = "Trigger", **kwargs) -> dict:
    """
    Args:
        name_filter: Case-insensitive substring to match actor labels.

    Returns:
        dict: {"status": "ok", "count": int, "labels": [str]}
    """
    devices = _get_all_devices()
    matched = [d for d in devices if name_filter.lower() in d.get_actor_label().lower()]

    if not matched:
        log_info(f"No devices found matching '{name_filter}'.")
        return {"status": "ok", "count": 0, "labels": []}

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor_sub.set_selected_level_actors(matched)
    labels = [d.get_actor_label() for d in matched]
    log_info(f"Selected {len(matched)} devices matching '{name_filter}'.")
    return {"status": "ok", "count": len(matched), "labels": labels}


@register_tool(
    name="verse_select_by_class",
    category="Verse Helpers",
    description="Select all Verse device actors of a given class name substring.",
    tags=["verse", "device", "select", "class"],
)
def run_select_by_class(class_filter: str = "SpawnPad", **kwargs) -> dict:
    """
    Args:
        class_filter: Case-insensitive substring of the actor's class name.

    Returns:
        dict: {"status": "ok", "count": int, "labels": [str]}
    """
    devices = _get_all_devices()
    matched = [d for d in devices if class_filter.lower() in d.get_class().get_name().lower()]

    if not matched:
        log_info(f"No devices found with class matching '{class_filter}'.")
        return {"status": "ok", "count": 0, "labels": []}

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor_sub.set_selected_level_actors(matched)
    labels = [d.get_actor_label() for d in matched]
    log_info(f"Selected {len(matched)} devices of class '{class_filter}'.")
    return {"status": "ok", "count": len(matched), "labels": labels}


@register_tool(
    name="verse_export_report",
    category="Verse Helpers",
    description="Export a JSON report of all Verse device properties to the Saved folder.",
    tags=["verse", "device", "export", "report", "json"],
)
def run_export_report(**kwargs) -> dict:
    """
    Writes a JSON file to:
        {ProjectSaved}/UEFN_Toolbelt/verse_device_report.json

    Returns:
        dict: {"status": "ok", "path": str, "count": int}
    """
    devices = _get_all_devices()
    if not devices:
        log_info("No Verse devices found to export.")
        return {"status": "ok", "path": "", "count": 0}

    report = []
    for d in devices:
        entry = {
            "label":      d.get_actor_label(),
            "class":      d.get_class().get_name(),
            "location":   {"x": d.get_actor_location().x,
                           "y": d.get_actor_location().y,
                           "z": d.get_actor_location().z},
            "properties": _get_actor_properties(d),
        }
        report.append(entry)

    out_dir  = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    out_path = os.path.join(out_dir, "verse_device_report.json")
    os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    log_info(f"Exported {len(report)} device records → {out_path}")
    return {"status": "ok", "path": out_path, "count": len(report)}


@register_tool(
    name="device_call_method",
    category="Verse Helpers",
    description=(
        "Call an exposed Python method on every actor matching a class or label filter. "
        "The V2 device runtime control layer — start/stop/pause timers, enable/disable "
        "capture areas, trigger spawners, etc."
    ),
    tags=["device", "method", "call", "runtime", "timer", "ai", "automation"],
)
def device_call_method(
    method: str = "",
    class_filter: str = "",
    label_filter: str = "",
    actor_path: str = "",
    method_args: list = None,
    **kwargs,
) -> dict:
    """
    Call ``method`` on every actor that matches at least one filter.
    Uses getattr() — the only reliable call path for V2 Verse device methods.

    Args:
        method:       The method name to call (e.g. "timer_start", "timer_pause",
                      "timer_resume", "timer_set_state", "timer_clear_handles").
        class_filter: Case-insensitive substring of actor class name.
        label_filter: Case-insensitive substring of actor label.
        actor_path:   Exact actor path or label for single-actor targeting.
        method_args:  Optional list of positional arguments to pass to the method.

    Returns:
        {
          "status": "ok",
          "matched": int,
          "success": int,
          "failed": int,
          "results": [{"label", "class", "result", "error"}]
        }

    Common V2 device methods discovered via api_crawl_selection:
        timer_start, timer_pause, timer_resume, timer_set_state, timer_clear_handles
        (run api_crawl_selection on any device to discover its full method list)

    Examples:
        tb.run("device_call_method", class_filter="Timer", method="timer_start")
        tb.run("device_call_method", label_filter="CaptureArea_1", method="Enable")
    """
    if not method:
        return {"status": "error", "message": "method is required."}
    if not any([class_filter, label_filter, actor_path]):
        return {"status": "error",
                "message": "Provide at least one filter: class_filter, label_filter, or actor_path."}

    args = method_args or []

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()

    matched = []
    for actor in all_actors:
        try:
            cls_name = type(actor).__name__
            label    = actor.get_actor_label()
            path     = actor.get_path_name()
        except Exception:
            continue

        if actor_path and (actor_path == path or actor_path == label):
            matched.append(actor)
            continue

        passes_class = (not class_filter) or (class_filter.lower() in cls_name.lower())
        passes_label = (not label_filter) or (label_filter.lower() in label.lower())
        if passes_class and passes_label:
            matched.append(actor)

    if not matched:
        return {"status": "ok", "matched": 0, "success": 0, "failed": 0, "results": [],
                "message": "No actors matched the given filters."}

    log_info(f"[device_call_method] {len(matched)} actor(s) matched. Calling '{method}'...")

    results = []
    success = failed = 0

    for actor in matched:
        cls_name = type(actor).__name__
        label    = actor.get_actor_label()
        fn = getattr(actor, method, None)
        if fn is None or not callable(fn):
            log_warning(f"  '{label}': method '{method}' not found on {cls_name}.")
            results.append({"label": label, "class": cls_name,
                            "result": "failed", "error": f"method '{method}' not found"})
            failed += 1
            continue
        try:
            fn(*args)
            results.append({"label": label, "class": cls_name, "result": "ok", "error": None})
            success += 1
        except Exception as e:
            err = str(e)[:160]
            log_warning(f"  '{label}': '{method}' raised — {err}")
            results.append({"label": label, "class": cls_name, "result": "failed", "error": err})
            failed += 1

    log_info(f"[device_call_method] done — {success} ok, {failed} failed.")
    return {"status": "ok", "matched": len(matched),
            "success": success, "failed": failed, "results": results}


@register_tool(
    name="device_set_property",
    category="Verse Helpers",
    description=(
        "Set a property on every actor matching a class, label, or path filter. "
        "The AI write layer — lets Claude configure any device in the level by name."
    ),
    tags=["device", "property", "set", "write", "ai", "automation", "bulk"],
)
def device_set_property(
    property_name: str = "",
    value: Any = None,
    class_filter: str = "",
    label_filter: str = "",
    actor_path: str = "",
    dry_run: bool = False,
    **kwargs,
) -> dict:
    """
    Set ``property_name`` = ``value`` on every actor that matches at least one
    filter. All three filters are optional and stack (AND logic when combined).

    Args:
        property_name: The UPROPERTY name to set (e.g. "time_limit", "bIsEnabled").
        value:         The value to assign. Passed directly to set_editor_property.
        class_filter:  Case-insensitive substring of the actor class name.
                       e.g. "Timer" matches FortCreativeTimerDevice.
        label_filter:  Case-insensitive substring of the actor label.
                       e.g. "Score" matches "ScoreManager_1".
        actor_path:    Exact actor path name or label for single-actor targeting.
        dry_run:       If True, report what would change without making changes.

    Returns:
        {
          "status": "ok",
          "matched": int,        # actors that passed the filter
          "success": int,        # properties successfully set
          "failed": int,         # properties that raised an error
          "skipped": int,        # read-only per schema
          "dry_run": bool,
          "results": [           # per-actor detail for AI to read
            {"label": str, "class": str, "result": "ok"|"failed"|"skipped"|"dry_run",
             "error": str|None}
          ]
        }

    Examples:
        # Set all timer devices to 120 seconds
        tb.run("device_set_property",
               class_filter="Timer", property_name="time_limit", value=120)

        # Disable a specific score manager by label
        tb.run("device_set_property",
               label_filter="ScoreManager_1", property_name="bIsEnabled", value=False)

        # Preview what would change before committing
        tb.run("device_set_property",
               class_filter="CaptureArea", property_name="TeamIndex",
               value=1, dry_run=True)
    """
    if not property_name:
        return {"status": "error", "message": "property_name is required."}
    if value is None and not dry_run:
        return {"status": "error", "message": "value is required (or pass dry_run=True to preview)."}
    if not any([class_filter, label_filter, actor_path]):
        return {"status": "error",
                "message": "Provide at least one filter: class_filter, label_filter, or actor_path."}

    # --- Gather all level actors ---
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()

    # --- Apply filters ---
    matched = []
    for actor in all_actors:
        try:
            cls_name = type(actor).__name__
            label    = actor.get_actor_label()
            path     = actor.get_path_name()
        except Exception:
            continue

        if actor_path and (actor_path == path or actor_path == label):
            matched.append(actor)
            continue

        passes_class = (not class_filter) or (class_filter.lower() in cls_name.lower())
        passes_label = (not label_filter) or (label_filter.lower() in label.lower())

        if passes_class and passes_label:
            matched.append(actor)

    if not matched:
        return {"status": "ok", "matched": 0, "success": 0, "failed": 0,
                "skipped": 0, "dry_run": dry_run, "results": [],
                "message": "No actors matched the given filters."}

    log_info(f"[device_set_property] {len(matched)} actor(s) matched. "
             f"Setting '{property_name}' = {value!r}"
             + (" [DRY RUN]" if dry_run else ""))

    results = []
    success = failed = skipped = 0

    with undo_transaction(f"device_set_property: {property_name}"):
        for actor in matched:
            cls_name = type(actor).__name__
            label    = actor.get_actor_label()

            if dry_run:
                results.append({"label": label, "class": cls_name,
                                 "result": "dry_run", "error": None})
                continue

            # Schema read-only check (non-blocking — just a warning)
            validation = schema_utils.validate_property(cls_name, property_name)
            if validation.get("exists") and not validation.get("meta", {}).get("readable", True):
                log_warning(f"  '{label}': '{property_name}' is marked read-only in schema — skipping.")
                results.append({"label": label, "class": cls_name,
                                 "result": "skipped", "error": "read-only per schema"})
                skipped += 1
                continue

            try:
                actor.set_editor_property(property_name, value)
                results.append({"label": label, "class": cls_name,
                                 "result": "ok", "error": None})
                success += 1
            except Exception as e:
                err = str(e)[:160]
                log_warning(f"  '{label}': failed to set '{property_name}' — {err}")
                results.append({"label": label, "class": cls_name,
                                 "result": "failed", "error": err})
                failed += 1

    log_info(f"[device_set_property] done — {success} ok, {failed} failed, "
             f"{skipped} skipped, {len(matched)} matched.")
    return {
        "status": "ok",
        "matched": len(matched),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "dry_run": dry_run,
        "results": results,
    }
