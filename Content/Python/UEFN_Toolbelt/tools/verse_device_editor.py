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
    """Heuristic check: is this actor likely a Verse/Creative device?"""
    class_name = actor.get_class().get_name()
    return any(hint in class_name for hint in _DEVICE_HINTS)


def _get_all_devices() -> List[unreal.Actor]:
    """Return all device-like actors in the current level."""
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    return [a for a in all_actors if _is_verse_device(a)]


def _get_actor_properties(actor: unreal.Actor) -> Dict[str, Any]:
    """
    Try to read common property names from an actor.
    Returns a dict of {prop_name: value}.
    """
    common_props = [
        "bIsEnabled", "bVisible", "bCanBeActivated",
        "TeamIndex", "MaxPlayers", "RespawnTime",
        "bAutoActivate", "ActivationDelay", "Health",
        "bShowActivationEffect", "InteractText",
    ]
    result: Dict[str, Any] = {}
    for prop in common_props:
        try:
            val = actor.get_editor_property(prop)
            result[prop] = val
        except Exception:
            pass  # Property doesn't exist on this actor type
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
def run_list_devices(name_filter: str = "", **kwargs) -> None:
    """
    Args:
        name_filter: Optional substring to filter by actor label.
    """
    devices = _get_all_devices()

    if name_filter:
        devices = [d for d in devices if name_filter.lower() in d.get_actor_label().lower()]

    if not devices:
        log_info("No Verse/Creative devices found in current level.")
        return

    lines = [f"\n=== Verse Devices ({len(devices)}) ==="]
    for d in devices:
        class_name = d.get_class().get_name()
        label = d.get_actor_label()
        loc = d.get_actor_location()
        lines.append(f"  [{class_name:40s}]  '{label}'  @ ({loc.x:.0f}, {loc.y:.0f}, {loc.z:.0f})")
    lines.append("")
    log_info("\n".join(lines))


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
) -> None:
    """
    Args:
        property_name:   The UPROPERTY name to set (e.g. "bIsEnabled", "TeamIndex").
        value:           The value to assign.
        use_all_devices: If True, apply to ALL devices in the level (not just selection).
    """
    if use_all_devices:
        actors = _get_all_devices()
        if not actors:
            log_warning("No Verse devices found in the level.")
            return
    else:
        actors = require_selection()
        if actors is None:
            return

    log_info(f"Setting '{property_name}' = {value!r} on {len(actors)} actor(s)…")

    success = failed = 0
    with undo_transaction(f"Verse Device Editor: Set {property_name}"):
        for actor in actors:
            try:
                actor.set_editor_property(property_name, value)
                success += 1
            except Exception as e:
                log_warning(f"  '{actor.get_actor_label()}': could not set '{property_name}' — {e}")
                failed += 1

    log_info(f"Done. {success} succeeded, {failed} failed.")


@register_tool(
    name="verse_select_by_name",
    category="Verse Helpers",
    description="Select all Verse device actors whose label contains a filter string.",
    tags=["verse", "device", "select", "filter"],
)
def run_select_by_name(name_filter: str = "Trigger", **kwargs) -> None:
    """
    Args:
        name_filter: Case-insensitive substring to match actor labels.
    """
    devices = _get_all_devices()
    matched = [d for d in devices if name_filter.lower() in d.get_actor_label().lower()]

    if not matched:
        log_info(f"No devices found matching '{name_filter}'.")
        return

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor_sub.set_selected_level_actors(matched)
    log_info(f"Selected {len(matched)} devices matching '{name_filter}'.")


@register_tool(
    name="verse_select_by_class",
    category="Verse Helpers",
    description="Select all Verse device actors of a given class name substring.",
    tags=["verse", "device", "select", "class"],
)
def run_select_by_class(class_filter: str = "SpawnPad", **kwargs) -> None:
    """
    Args:
        class_filter: Case-insensitive substring of the actor's class name.
    """
    devices = _get_all_devices()
    matched = [d for d in devices if class_filter.lower() in d.get_class().get_name().lower()]

    if not matched:
        log_info(f"No devices found with class matching '{class_filter}'.")
        return

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor_sub.set_selected_level_actors(matched)
    log_info(f"Selected {len(matched)} devices of class '{class_filter}'.")


@register_tool(
    name="verse_export_report",
    category="Verse Helpers",
    description="Export a JSON report of all Verse device properties to the Saved folder.",
    tags=["verse", "device", "export", "report", "json"],
)
def run_export_report(**kwargs) -> None:
    """
    Writes a JSON file to:
        {ProjectSaved}/UEFN_Toolbelt/verse_device_report.json
    """
    devices = _get_all_devices()
    if not devices:
        log_info("No Verse devices found to export.")
        return

    report = []
    for d in devices:
        entry = {
            "label":    d.get_actor_label(),
            "class":    d.get_class().get_name(),
            "location": {"x": d.get_actor_location().x,
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
