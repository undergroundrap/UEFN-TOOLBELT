"""
UEFN TOOLBELT — level_snapshot.py
=========================================
Non-destructive level state capture — save, restore, diff, and compare
actor transforms at any point during your editing session.

What it captures per actor:
  - Label (world outliner name)
  - Class name
  - Location (X, Y, Z)
  - Rotation (Pitch, Yaw, Roll)
  - Scale (X, Y, Z)
  - Actor tags
  - Visibility (hidden in editor?)

What it does NOT capture:
  - Material overrides (use material_master presets for that)
  - Verse device property values (use verse_export_report for that)
  - Asset references / content (snapshots are transform-only by design)

Use cases:
  - "Checkpoint" before running a destructive bulk op — restore if unhappy
  - Track what changed between two editing sessions (diff)
  - Share a level layout with another creator (export/import JSON)
  - Auto-save on a naming convention (every hour while working)

Storage:
  Saved/UEFN_Toolbelt/snapshots/<name>.json
  Each file is human-readable JSON — can be opened in any text editor.

Restore safety:
  snapshot_restore wraps in undo_transaction() so Ctrl+Z rolls back the restore.
  Actors that exist in the snapshot but not the current level are skipped with
  a warning (they were deleted). Actors in the current level not in the snapshot
  are untouched.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import unreal

from UEFN_Toolbelt.core import undo_transaction, with_progress
from UEFN_Toolbelt.registry import register_tool

# ─── Storage ──────────────────────────────────────────────────────────────────

_SAVED      = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
_SNAP_DIR   = os.path.join(_SAVED, "snapshots")


def _ensure_dir() -> None:
    os.makedirs(_SNAP_DIR, exist_ok=True)


def _snap_path(name: str) -> str:
    safe = name.replace(" ", "_").replace("/", "-")
    return os.path.join(_SNAP_DIR, f"{safe}.json")


# ─── Actor serialization ──────────────────────────────────────────────────────

def _serialize_actor(actor: unreal.Actor) -> dict[str, Any]:
    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    scl = actor.get_actor_scale3d()

    try:
        tags = [str(t) for t in actor.get_editor_property("tags")]
    except Exception:
        tags = []

    try:
        hidden = bool(actor.get_editor_property("b_hidden"))
    except Exception:
        hidden = False

    return {
        "label":    actor.get_actor_label(),
        "class":    actor.get_class().get_name(),
        "location": {"x": loc.x, "y": loc.y, "z": loc.z},
        "rotation": {"pitch": rot.pitch, "yaw": rot.yaw, "roll": rot.roll},
        "scale":    {"x": scl.x, "y": scl.y, "z": scl.z},
        "tags":     tags,
        "hidden":   hidden,
    }


def _deserialize_transform(data: dict[str, Any]) -> tuple[
    unreal.Vector, unreal.Rotator, unreal.Vector
]:
    loc = data["location"]
    rot = data["rotation"]
    scl = data["scale"]
    return (
        unreal.Vector(loc["x"], loc["y"], loc["z"]),
        unreal.Rotator(rot["pitch"], rot["yaw"], rot["roll"]),
        unreal.Vector(scl["x"], scl["y"], scl["z"]),
    )


# ─── Label-based actor lookup ─────────────────────────────────────────────────

def _build_actor_map() -> dict[str, list[unreal.Actor]]:
    """Map actor label → [actors] (list because labels are not guaranteed unique)."""
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    label_map: dict[str, list[unreal.Actor]] = {}
    for actor in sub.get_all_level_actors():
        label = actor.get_actor_label()
        label_map.setdefault(label, []).append(actor)
    return label_map


# ─── Diff logic ───────────────────────────────────────────────────────────────

_MOVE_THRESHOLD_CM = 1.0   # smaller = stricter match for "moved"
_ROT_THRESHOLD_DEG = 0.1


def _vec_close(a: dict, b: dict, threshold: float) -> bool:
    return all(abs(a[k] - b[k]) <= threshold for k in ("x", "y", "z"))


def _rot_close(a: dict, b: dict, threshold: float) -> bool:
    return all(abs(a[k] - b[k]) <= threshold for k in ("pitch", "yaw", "roll"))


def _diff_snapshots(
    snap_a: dict[str, Any],
    snap_b: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare two snapshots. Returns lists of:
      - added   (in B, not in A)
      - removed (in A, not in B)
      - moved   (in both, transform changed)
      - renamed (same class + similar location, different label)
    """
    a_by_label = {e["label"]: e for e in snap_a["actors"]}
    b_by_label = {e["label"]: e for e in snap_b["actors"]}

    a_labels = set(a_by_label)
    b_labels = set(b_by_label)

    added   = [b_by_label[l] for l in b_labels - a_labels]
    removed = [a_by_label[l] for l in a_labels - b_labels]
    moved   = []

    for label in a_labels & b_labels:
        ea, eb = a_by_label[label], b_by_label[label]
        loc_changed = not _vec_close(ea["location"], eb["location"], _MOVE_THRESHOLD_CM)
        rot_changed = not _rot_close(ea["rotation"], eb["rotation"], _ROT_THRESHOLD_DEG)
        scl_changed = not _vec_close(ea["scale"],    eb["scale"],    0.001)
        if loc_changed or rot_changed or scl_changed:
            moved.append({
                "label": label,
                "location_changed": loc_changed,
                "rotation_changed": rot_changed,
                "scale_changed":    scl_changed,
                "before": {
                    "location": ea["location"],
                    "rotation": ea["rotation"],
                    "scale":    ea["scale"],
                },
                "after": {
                    "location": eb["location"],
                    "rotation": eb["rotation"],
                    "scale":    eb["scale"],
                },
            })

    return {
        "snapshot_a": snap_a["name"],
        "snapshot_b": snap_b["name"],
        "added_count":   len(added),
        "removed_count": len(removed),
        "moved_count":   len(moved),
        "added":   added,
        "removed": removed,
        "moved":   moved,
    }


# ─── Tool implementations ──────────────────────────────────────────────────────

def _do_save(name: str, scope: str, class_filter: str) -> dict:
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    if scope == "selection":
        actors = sub.get_selected_level_actors()
    else:
        actors = sub.get_all_level_actors()

    if class_filter:
        actors = [a for a in actors if class_filter.lower() in a.get_class().get_name().lower()]

    if not actors:
        unreal.log_warning("[Snapshot] No actors to snapshot.")
        return {"status": "error", "message": "No actors to snapshot."}

    serialized = []
    for actor in actors:
        try:
            serialized.append(_serialize_actor(actor))
        except Exception as e:
            unreal.log_warning(f"[Snapshot] Skipping {actor.get_actor_label()}: {e}")

    snapshot = {
        "name":         name,
        "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%S"),
        "actor_count":  len(serialized),
        "scope":        scope,
        "class_filter": class_filter or "all",
        "actors":       serialized,
    }

    _ensure_dir()
    path = _snap_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    unreal.log(f"[Snapshot] ✓ Saved '{name}' — {len(serialized)} actors → {path}")
    return {"status": "ok", "name": name, "actor_count": len(serialized), "path": path}


def _do_restore(name: str, restore_location: bool,
                restore_rotation: bool, restore_scale: bool,
                restore_visibility: bool) -> dict:
    path = _snap_path(name)
    if not os.path.exists(path):
        unreal.log_warning(f"[Snapshot] Snapshot '{name}' not found at {path}")
        return {"status": "error", "message": f"Snapshot '{name}' not found."}

    with open(path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    actors = snapshot.get("actors", [])
    label_map = _build_actor_map()

    restored = 0
    skipped  = 0

    with undo_transaction(f"Restore Snapshot: {name}"):
        with with_progress(actors, f"Restoring '{name}'…") as gen:
            for entry in gen:
                label = entry["label"]
                matches = label_map.get(label, [])

                if not matches:
                    skipped += 1
                    continue

                # If multiple actors share a label, find the closest by current position
                if len(matches) > 1:
                    snap_loc = entry["location"]
                    sv = unreal.Vector(snap_loc["x"], snap_loc["y"], snap_loc["z"])
                    matches.sort(key=lambda a: (a.get_actor_location() - sv).length())

                actor = matches[0]
                loc, rot, scl = _deserialize_transform(entry)

                if restore_location:
                    actor.set_actor_location(loc, sweep=False, teleport=True)
                if restore_rotation:
                    actor.set_actor_rotation(rot, teleport_physics=True)
                if restore_scale:
                    actor.set_actor_scale3d(scl)
                if restore_visibility:
                    try:
                        actor.set_editor_property("b_hidden", entry.get("hidden", False))
                    except Exception:
                        pass

                restored += 1

    unreal.log(
        f"[Snapshot] ✓ Restored '{name}' — "
        f"{restored} actors restored, {skipped} not found in level."
    )
    if skipped:
        unreal.log(
            f"[Snapshot]   {skipped} actors from the snapshot were not found "
            "(deleted or renamed since the snapshot was taken)."
        )
    return {"status": "ok", "name": name, "restored": restored, "skipped": skipped}


# ─── Registered tools ──────────────────────────────────────────────────────────

@register_tool(
    name="snapshot_save",
    category="Level Snapshot",
    description="Save a named JSON snapshot of actor transforms in the current level",
    icon="📸",
    tags=["snapshot", "backup", "save", "transforms"],
    example='tb.run("snapshot_save", name="before_scatter")',
)
def snapshot_save(
    name: str = "",
    scope: str = "all",
    class_filter: str = "",
**kwargs,
) -> dict:
    """
    Capture actor transforms and save them to a named snapshot.

    Args:
        name:         Snapshot name. If empty, auto-names as 'snap_YYYYMMDD_HHMMSS'.
        scope:        "all" = entire level. "selection" = only selected actors.
        class_filter: Only snapshot actors whose class name contains this string.
                      E.g. "StaticMeshActor", "BP_MyDevice". Empty = all classes.

    Returns:
        dict: {"status", "name", "actor_count", "path"}
    """
    if not name:
        name = time.strftime("snap_%Y%m%d_%H%M%S")
    return _do_save(name, scope, class_filter)


@register_tool(
    name="snapshot_restore",
    category="Level Snapshot",
    description="Restore actor transforms from a named snapshot (fully undoable)",
    icon="↩",
    tags=["snapshot", "restore", "undo", "transforms"],
)
def snapshot_restore(
    name: str = "",
    restore_location: bool = True,
    restore_rotation: bool = True,
    restore_scale: bool = True,
    restore_visibility: bool = False,
**kwargs,
) -> dict:
    """
    Restore actor transforms from a saved snapshot.
    Actors not found in the current level are skipped with a warning.
    The entire restore is wrapped in undo_transaction() — one Ctrl+Z reverts it.

    Args:
        name:               Snapshot name to restore from.
        restore_location:   Move actors back to saved locations.
        restore_rotation:   Reset rotations to saved values.
        restore_scale:      Reset scales to saved values.
        restore_visibility: Also restore hidden/visible state.

    Returns:
        dict: {"status", "name", "restored", "skipped"}
    """
    if not name:
        unreal.log_warning(
            "[Snapshot] Provide a snapshot name. "
            "Run snapshot_list to see available snapshots."
        )
        return {"status": "error", "message": "No snapshot name provided."}
    return _do_restore(name, restore_location, restore_rotation,
                       restore_scale, restore_visibility)


@register_tool(
    name="snapshot_list",
    category="Level Snapshot",
    description="List all saved snapshots with actor count and timestamp",
    icon="📋",
    tags=["snapshot", "list"],
)
def snapshot_list(**kwargs) -> dict:
    """
    Print all saved snapshots in Saved/UEFN_Toolbelt/snapshots/.

    Returns:
        dict: {"status", "count", "snapshots": [{"name", "timestamp", "actor_count", "scope"}]}
    """
    _ensure_dir()
    files = [f for f in os.listdir(_SNAP_DIR) if f.endswith(".json")]

    if not files:
        unreal.log("[Snapshot] No snapshots saved yet. Run snapshot_save first.")
        return {"status": "ok", "count": 0, "snapshots": []}

    unreal.log(f"\n[Snapshot] {len(files)} saved snapshots:\n")
    files.sort()
    records = []

    for fname in files:
        fpath = os.path.join(_SNAP_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            unreal.log(
                f"  📸  {data['name']:30s}  "
                f"{data['timestamp']}  "
                f"{data['actor_count']:4d} actors  "
                f"scope={data.get('scope','all')}"
            )
            records.append({
                "name":        data["name"],
                "timestamp":   data["timestamp"],
                "actor_count": data["actor_count"],
                "scope":       data.get("scope", "all"),
            })
        except Exception as e:
            unreal.log(f"  ✗  {fname}  (could not read: {e})")

    unreal.log("")
    return {"status": "ok", "count": len(records), "snapshots": records}


@register_tool(
    name="snapshot_diff",
    category="Level Snapshot",
    description="Compare two snapshots — see what actors were added, removed, or moved",
    icon="⇄",
    tags=["snapshot", "diff", "compare"],
)
def snapshot_diff(name_a: str = "", name_b: str = "", **kwargs) -> dict:
    """
    Diff two snapshots and print what changed.

    Args:
        name_a: Earlier/baseline snapshot name.
        name_b: Later/current snapshot name.

    Returns:
        dict: full diff result with added, removed, moved lists and counts.
    """
    if not name_a or not name_b:
        unreal.log_warning(
            "[Snapshot] Provide two snapshot names. "
            "Example: tb.run('snapshot_diff', name_a='before', name_b='after')"
        )
        return {"status": "error", "message": "Two snapshot names required."}

    path_a, path_b = _snap_path(name_a), _snap_path(name_b)
    for path, name in ((path_a, name_a), (path_b, name_b)):
        if not os.path.exists(path):
            unreal.log_warning(f"[Snapshot] Snapshot '{name}' not found at {path}")
            return {"status": "error", "message": f"Snapshot '{name}' not found."}

    with open(path_a, "r", encoding="utf-8") as f:
        snap_a = json.load(f)
    with open(path_b, "r", encoding="utf-8") as f:
        snap_b = json.load(f)

    diff = _diff_snapshots(snap_a, snap_b)

    unreal.log(f"\n[Snapshot] Diff: '{diff['snapshot_a']}' → '{diff['snapshot_b']}'")
    unreal.log(f"  ➕ Added:   {diff['added_count']} actors")
    unreal.log(f"  ➖ Removed: {diff['removed_count']} actors")
    unreal.log(f"  ↔ Moved:   {diff['moved_count']} actors\n")

    if diff["added"]:
        unreal.log("  Added actors:")
        for a in diff["added"][:20]:
            unreal.log(f"    + {a['label']}  [{a['class']}]")

    if diff["removed"]:
        unreal.log("  Removed actors:")
        for a in diff["removed"][:20]:
            unreal.log(f"    - {a['label']}  [{a['class']}]")

    if diff["moved"]:
        unreal.log("  Moved actors:")
        for m in diff["moved"][:20]:
            changes = []
            if m["location_changed"]: changes.append("loc")
            if m["rotation_changed"]: changes.append("rot")
            if m["scale_changed"]:    changes.append("scale")
            unreal.log(f"    ↔ {m['label']}  ({', '.join(changes)})")

    if diff["added_count"] + diff["removed_count"] + diff["moved_count"] == 0:
        unreal.log("  ✓ No differences found — snapshots are identical.")

    diff["status"] = "ok"
    return diff


@register_tool(
    name="snapshot_delete",
    category="Level Snapshot",
    description="Delete a saved snapshot by name",
    icon="🗑",
    tags=["snapshot", "delete"],
)
def snapshot_delete(name: str = "", **kwargs) -> dict:
    """
    Delete a single snapshot file.

    Returns:
        dict: {"status", "name"}
    """
    if not name:
        unreal.log_warning("[Snapshot] Provide a snapshot name to delete.")
        return {"status": "error", "message": "No snapshot name provided."}

    path = _snap_path(name)
    if not os.path.exists(path):
        unreal.log_warning(f"[Snapshot] Snapshot '{name}' not found.")
        return {"status": "error", "message": f"Snapshot '{name}' not found."}

    os.remove(path)
    unreal.log(f"[Snapshot] ✓ Deleted snapshot '{name}'.")
    return {"status": "ok", "name": name}


@register_tool(
    name="snapshot_export",
    category="Level Snapshot",
    description="Copy a snapshot JSON to a custom file path for sharing",
    icon="📤",
    tags=["snapshot", "export", "share"],
)
def snapshot_export(name: str = "", export_path: str = "", **kwargs) -> dict:
    """
    Export a snapshot to any file path (for sharing with other creators).

    Args:
        name:        Snapshot to export.
        export_path: Full OS path for the output file (e.g. 'C:/Shared/my_snap.json').
                     Defaults to the project Saved folder if empty.
    """
    if not name:
        unreal.log_warning("[Snapshot] Provide a snapshot name to export.")
        return {"status": "error", "message": "No snapshot name provided."}

    src = _snap_path(name)
    if not os.path.exists(src):
        unreal.log_warning(f"[Snapshot] Snapshot '{name}' not found.")
        return {"status": "error", "message": f"Snapshot '{name}' not found."}

    if not export_path:
        export_path = os.path.join(_SAVED, f"{name}_export.json")

    import shutil
    shutil.copy2(src, export_path)
    unreal.log(f"[Snapshot] ✓ Exported '{name}' → {export_path}")
    return {"status": "ok", "name": name, "path": export_path}


@register_tool(
    name="snapshot_import",
    category="Level Snapshot",
    description="Import a snapshot JSON from an external path",
    icon="📥",
    tags=["snapshot", "import", "share"],
)
def snapshot_import(import_path: str = "", name: str = "", **kwargs) -> dict:
    """
    Import a snapshot JSON from any file path.

    Args:
        import_path: Full OS path to the .json snapshot file.
        name:        Override name to save the snapshot as. If empty, uses the
                     name field stored inside the file.
    """
    if not import_path or not os.path.exists(import_path):
        unreal.log_warning(f"[Snapshot] File not found: '{import_path}'")
        return {"status": "error", "message": f"File not found: '{import_path}'"}

    with open(import_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    snap_name = name or data.get("name", "imported_snapshot")
    _ensure_dir()
    dest = _snap_path(snap_name)

    import shutil
    shutil.copy2(import_path, dest)
    unreal.log(
        f"[Snapshot] ✓ Imported '{snap_name}' "
        f"({data.get('actor_count', '?')} actors) → {dest}"
    )
    return {"status": "ok", "name": snap_name, "actor_count": data.get("actor_count", 0), "path": dest}


@register_tool(
    name="snapshot_compare_live",
    category="Level Snapshot",
    description="Compare a saved snapshot against the current live level state",
    icon="🔍",
    tags=["snapshot", "diff", "live", "compare"],
)
def snapshot_compare_live(name: str = "", **kwargs) -> dict:
    """
    Diff a saved snapshot against the current level — no second snapshot needed.

    Equivalent to: save a temp snapshot of the current state, then diff it
    against the named snapshot.

    Args:
        name: Snapshot to compare the current level against.

    Returns:
        dict: full diff result (same shape as snapshot_diff) with status key.
    """
    if not name:
        unreal.log_warning(
            "[Snapshot] Provide a snapshot name to compare against. "
            "Example: tb.run('snapshot_compare_live', name='before_bulk_op')"
        )
        return {"status": "error", "message": "No snapshot name provided."}

    temp_name = f"_live_compare_{time.strftime('%H%M%S')}"
    _do_save(temp_name, "all", "")

    path_saved = _snap_path(name)
    path_live  = _snap_path(temp_name)

    if not os.path.exists(path_saved):
        unreal.log_warning(f"[Snapshot] Snapshot '{name}' not found.")
        try:
            os.remove(path_live)
        except Exception:
            pass
        return {"status": "error", "message": f"Snapshot '{name}' not found."}

    with open(path_saved, "r", encoding="utf-8") as f:
        snap_saved = json.load(f)
    with open(path_live, "r", encoding="utf-8") as f:
        snap_live = json.load(f)

    # Rename for display
    snap_live["name"] = "current level"
    diff = _diff_snapshots(snap_saved, snap_live)
    diff["snapshot_b"] = "current level"

    unreal.log(f"\n[Snapshot] Live diff: '{name}' vs current level")
    unreal.log(f"  ➕ Added since snapshot:   {diff['added_count']}")
    unreal.log(f"  ➖ Removed since snapshot: {diff['removed_count']}")
    unreal.log(f"  ↔ Moved since snapshot:   {diff['moved_count']}\n")

    if diff["moved"]:
        unreal.log("  Moved actors:")
        for m in diff["moved"][:30]:
            changes = []
            if m["location_changed"]: changes.append("loc")
            if m["rotation_changed"]: changes.append("rot")
            if m["scale_changed"]:    changes.append("scale")
            unreal.log(f"    ↔ {m['label']}  ({', '.join(changes)})")

    if diff["added_count"] + diff["removed_count"] + diff["moved_count"] == 0:
        unreal.log(f"  ✓ No changes since '{name}' was saved.")

    # Clean up temp snapshot
    try:
        os.remove(path_live)
    except Exception:
        pass

    diff["status"] = "ok"
    return diff
