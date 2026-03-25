"""
UEFN TOOLBELT — Level Stamp System
=====================================
Save groups of placed actors as named stamps and re-spawn them anywhere in the level.
Stamps capture relative transforms, mesh paths, rotations, and scales — every
placement is a fully undo-able transaction.

NOT the same as prefab_migrator (which exports .uasset files between projects).
This is for level layout: save a cluster of props, stamp it 10 times across your map.

OPERATIONS:
  stamp_save    — Save selected StaticMesh actors as a named stamp
  stamp_place   — Spawn a saved stamp at the viewport camera (or given location)
  stamp_list    — List all saved stamps with actor counts
  stamp_info    — Print actors / meshes / offsets for a stamp
  stamp_delete  — Delete a saved stamp

STORAGE:
  Saved/UEFN_Toolbelt/stamps/{name}.json

USAGE:
    import UEFN_Toolbelt as tb

    # 1. Select some actors in the viewport, then save as a stamp
    tb.run("stamp_save", name="guard_post")

    # 2. Place it at the camera position
    tb.run("stamp_place", name="guard_post")

    # 3. Place at a specific world location with 90° yaw and 1.5× scale
    tb.run("stamp_place", name="guard_post", location=[5000, 3000, 0],
           yaw_offset=90.0, scale_factor=1.5)

    # Stamp 4 copies at compass points — instant symmetric layout
    for angle, x, y in [(0, 5000, 0), (90, 0, 5000), (180, -5000, 0), (270, 0, -5000)]:
        tb.run("stamp_place", name="guard_post", location=[x, y, 0], yaw_offset=angle)

    # Management
    tb.run("stamp_list")
    tb.run("stamp_info",   name="guard_post")
    tb.run("stamp_delete", name="guard_post")

NOTES:
  • Only StaticMesh actors are captured. Blueprint/device actors are skipped with
    a warning — they cannot be reliably re-spawned from a saved asset path.
  • Stamps survive hot-reloads and editor restarts (JSON on disk).
  • yaw_offset rotates every actor's position AND rotation around the stamp center.
  • scale_factor multiplies both relative offsets AND each actor's scale.
"""

from __future__ import annotations

import json
import math
import os
from typing import List, Optional

import unreal

from ..core import log_info, log_warning, log_error
from ..registry import register_tool


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stamp_dir() -> str:
    d = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "stamps")
    os.makedirs(d, exist_ok=True)
    return d


def _stamp_path(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in "_- ").strip().replace(" ", "_")
    return os.path.join(_stamp_dir(), f"{safe}.json")


def _actor_sub() -> unreal.EditorActorSubsystem:
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _get_selected() -> List[unreal.Actor]:
    return list(_actor_sub().get_selected_level_actors() or [])


def _mesh_path(actor: unreal.Actor) -> Optional[str]:
    """Return the clean asset path for the actor's static mesh, or None."""
    try:
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        if comp:
            mesh = comp.get_editor_property("static_mesh")
            if mesh:
                raw = str(mesh.get_path_name())
                # Strip .AssetName suffix: /Game/SM_Rock.SM_Rock → /Game/SM_Rock
                return raw.split(".")[0]
    except Exception:
        pass
    return None


def _camera_location() -> unreal.Vector:
    """Return viewport camera location, fallback to origin."""
    try:
        vp = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        loc, _ = vp.get_level_viewport_camera_info()
        return loc
    except Exception:
        return unreal.Vector(0, 0, 0)


def _rotate_offset(x: float, y: float, yaw_deg: float):
    """Rotate (x, y) offset by yaw_deg around Z (degrees)."""
    rad = math.radians(yaw_deg)
    rx = x * math.cos(rad) - y * math.sin(rad)
    ry = x * math.sin(rad) + y * math.cos(rad)
    return rx, ry


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="stamp_save",
    category="Stamps",
    description=(
        "Save selected StaticMesh actors as a named stamp. "
        "Records relative transforms and mesh asset paths. "
        "Saved to Saved/UEFN_Toolbelt/stamps/{name}.json. "
        "Use stamp_place to re-spawn it anywhere. "
        "Not the same as prefab_migrate_open (which moves .uasset files between projects)."
    ),
    tags=["stamp", "save", "group", "reuse", "layout"],
)
def stamp_save(
    name: str = "",
    **kwargs,
) -> dict:
    if not name:
        return {"status": "error", "message": "name is required — e.g. stamp_save(name='guard_post')"}

    selected = _get_selected()
    if not selected:
        return {"status": "error", "message": "Select actors to save as a stamp."}

    entries = []
    skipped = []

    for actor in selected:
        path = _mesh_path(actor)
        if not path:
            skipped.append(actor.get_actor_label())
            log_warning(f"[STAMP] '{actor.get_actor_label()}' — not a StaticMeshActor, skipping")
            continue
        loc = actor.get_actor_location()
        rot = actor.get_actor_rotation()
        sc  = actor.get_actor_scale3d()
        entries.append({
            "label":    actor.get_actor_label(),
            "mesh":     path,
            "location": [loc.x, loc.y, loc.z],
            "rotation": [rot.pitch, rot.yaw, rot.roll],
            "scale":    [sc.x, sc.y, sc.z],
            "folder":   str(actor.get_folder_path()),
        })

    if not entries:
        return {
            "status":  "error",
            "message": "No StaticMesh actors in selection. Stamps support StaticMesh actors only.",
            "skipped": skipped,
        }

    # Centroid of all actor locations
    cx = sum(e["location"][0] for e in entries) / len(entries)
    cy = sum(e["location"][1] for e in entries) / len(entries)
    cz = sum(e["location"][2] for e in entries) / len(entries)

    # Store relative offsets; drop absolute location
    for e in entries:
        e["rel"] = [
            e["location"][0] - cx,
            e["location"][1] - cy,
            e["location"][2] - cz,
        ]
        del e["location"]

    stamp = {
        "name":        name,
        "actor_count": len(entries),
        "actors":      entries,
    }

    out_path = _stamp_path(name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(stamp, f, indent=2)

    log_info(f"[STAMP] Saved '{name}' — {len(entries)} actors → {out_path}")
    if skipped:
        log_warning(f"[STAMP] Skipped {len(skipped)} non-StaticMesh actor(s): {', '.join(skipped)}")

    return {
        "status":         "ok",
        "name":           name,
        "actors_saved":   len(entries),
        "actors_skipped": len(skipped),
        "path":           out_path,
    }


@register_tool(
    name="stamp_place",
    category="Stamps",
    description=(
        "Spawn a saved stamp at the viewport camera position (or given location=[x,y,z]). "
        "yaw_offset rotates the whole group around Z in degrees. "
        "scale_factor uniformly rescales all actors and offsets. "
        "New actors are placed in 'folder' and selected after placement."
    ),
    tags=["stamp", "place", "spawn", "layout", "instance"],
    example='tb.run("stamp_place", name="guard_post", location=[8000, 4000, 0], yaw_offset=180.0, scale_factor=1.5)',
)
def stamp_place(
    name: str = "",
    location: list = None,
    yaw_offset: float = 0.0,
    scale_factor: float = 1.0,
    folder: str = "Stamps",
    focus: bool = False,
    **kwargs,
) -> dict:
    if not name:
        return {"status": "error", "message": "name is required — e.g. stamp_place(name='guard_post')"}

    fp = _stamp_path(name)
    if not os.path.exists(fp):
        return {
            "status":  "error",
            "message": f"No stamp named '{name}' found. Run stamp_list to see available stamps.",
        }

    with open(fp, encoding="utf-8") as f:
        stamp = json.load(f)

    if location:
        center = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
    else:
        center = _camera_location()

    total      = len(stamp.get("actors", []))
    spawned    = 0
    new_actors = []

    with unreal.ScopedEditorTransaction(f"stamp_place:{name}"):
        for entry in stamp.get("actors", []):
            rx, ry = _rotate_offset(entry["rel"][0], entry["rel"][1], yaw_offset)
            rz = entry["rel"][2]

            world_loc = unreal.Vector(
                center.x + rx * scale_factor,
                center.y + ry * scale_factor,
                center.z + rz * scale_factor,
            )

            mesh = unreal.load_asset(entry["mesh"])
            if not mesh:
                log_warning(f"[STAMP] Could not load '{entry['mesh']}' — skipping '{entry['label']}'")
                continue

            world_rot = unreal.Rotator(
                entry["rotation"][0],
                entry["rotation"][1] + yaw_offset,
                entry["rotation"][2],
            )

            actor = unreal.EditorLevelLibrary.spawn_actor_from_object(mesh, world_loc, world_rot)
            if not actor:
                log_warning(f"[STAMP] spawn failed for '{entry['label']}'")
                continue

            sx, sy, sz = entry["scale"]
            actor.set_actor_scale3d(unreal.Vector(
                sx * scale_factor,
                sy * scale_factor,
                sz * scale_factor,
            ))
            actor.set_actor_label(entry["label"])
            if folder:
                actor.set_folder_path(folder)
            new_actors.append(actor)
            spawned += 1

    if new_actors:
        _actor_sub().set_selected_level_actors(new_actors)

    log_info(
        f"[STAMP] Placed '{name}' — {spawned}/{total} actors at "
        f"[{center.x:.0f}, {center.y:.0f}, {center.z:.0f}] "
        f"yaw={yaw_offset}° scale={scale_factor}×"
    )
    if focus and new_actors:
        try:
            # new_actors already selected above — call native camera command
            unreal.SystemLibrary.execute_console_command(
                unreal.EditorLevelLibrary.get_editor_world(), "CAMERA ALIGN"
            )
        except Exception:
            pass
    return {
        "status":         "ok",
        "name":           name,
        "actors_stamped": spawned,
        "actors_total":   total,
        "location":       [center.x, center.y, center.z],
        "yaw_offset":     yaw_offset,
        "scale_factor":   scale_factor,
        "folder":         folder,
    }


@register_tool(
    name="stamp_list",
    category="Stamps",
    description="List all saved stamps with their actor counts.",
    tags=["stamp", "list", "browse"],
)
def stamp_list(**kwargs) -> dict:
    d = _stamp_dir()
    stamps = []
    for fname in sorted(os.listdir(d)):
        if not fname.endswith(".json"):
            continue
        fp = os.path.join(d, fname)
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            stamps.append({
                "name":        data.get("name", fname[:-5]),
                "actor_count": data.get("actor_count", 0),
            })
        except Exception:
            stamps.append({"name": fname[:-5], "actor_count": "?"})

    if stamps:
        log_info(f"[STAMP] {len(stamps)} saved stamp(s):")
        for s in stamps:
            log_info(f"  • {s['name']}  ({s['actor_count']} actors)")
    else:
        log_info("[STAMP] No stamps saved yet. Select actors, then run stamp_save.")

    return {"status": "ok", "count": len(stamps), "stamps": stamps}


@register_tool(
    name="stamp_info",
    category="Stamps",
    description="Print the actor list, mesh paths, and relative offsets for a saved stamp.",
    tags=["stamp", "info", "inspect", "preview"],
)
def stamp_info(
    name: str = "",
    **kwargs,
) -> dict:
    if not name:
        return {"status": "error", "message": "name is required."}

    fp = _stamp_path(name)
    if not os.path.exists(fp):
        return {"status": "error", "message": f"No stamp named '{name}' found."}

    with open(fp, encoding="utf-8") as f:
        stamp = json.load(f)

    log_info(f"[STAMP] '{name}' — {stamp.get('actor_count', 0)} actor(s):")
    for a in stamp.get("actors", []):
        mesh_short = a["mesh"].rsplit("/", 1)[-1]
        rel = a["rel"]
        log_info(
            f"  {a['label']:<30s}  mesh={mesh_short:<30s}  "
            f"rel=[{rel[0]:+.0f}, {rel[1]:+.0f}, {rel[2]:+.0f}]"
        )

    return {"status": "ok", "stamp": stamp}


@register_tool(
    name="stamp_delete",
    category="Stamps",
    description="Delete a saved stamp by name.",
    tags=["stamp", "delete", "remove"],
)
def stamp_delete(
    name: str = "",
    **kwargs,
) -> dict:
    if not name:
        return {"status": "error", "message": "name is required."}

    fp = _stamp_path(name)
    if not os.path.exists(fp):
        return {"status": "error", "message": f"No stamp named '{name}' found."}

    os.remove(fp)
    log_info(f"[STAMP] Deleted stamp '{name}'")
    return {"status": "ok", "deleted": name}


@register_tool(
    name="stamp_export",
    category="Stamps",
    description="Export a saved stamp to a portable JSON file so it can be shared or imported into another project.",
    tags=["stamp", "export", "share", "portable"],
)
def stamp_export(name: str = "", output_path: str = "", **kwargs) -> dict:
    if not name:
        return {"status": "error", "message": "name is required."}

    src = _stamp_path(name)
    if not os.path.exists(src):
        return {"status": "error", "message": f"No stamp named '{name}' found."}

    if not output_path:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "stamps")
        os.makedirs(desktop, exist_ok=True)
        safe = "".join(c for c in name if c.isalnum() or c in "_- ").strip().replace(" ", "_")
        output_path = os.path.join(desktop, f"{safe}.json")

    import shutil
    shutil.copy2(src, output_path)
    log_info(f"[STAMP] Exported '{name}' → {output_path}")
    return {"status": "ok", "name": name, "output_path": output_path}


@register_tool(
    name="stamp_import",
    category="Stamps",
    description="Import a stamp from a portable JSON file (e.g. shared by another creator). Adds it to your local stamp library.",
    tags=["stamp", "import", "share", "portable"],
)
def stamp_import(file_path: str = "", name_override: str = "",
                 overwrite: bool = False, **kwargs) -> dict:
    if not file_path:
        return {"status": "error", "message": "file_path is required."}
    if not os.path.exists(file_path):
        return {"status": "error", "message": f"File not found: {file_path}"}

    with open(file_path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            return {"status": "error", "message": f"Invalid stamp JSON: {e}"}

    # Validate minimal stamp structure
    if "actors" not in data or "name" not in data:
        return {"status": "error", "message": "File does not appear to be a valid stamp (missing 'name' or 'actors')."}

    name = name_override.strip() or data.get("name", "imported_stamp")
    if name_override:
        data["name"] = name

    dest = _stamp_path(name)
    if os.path.exists(dest) and not overwrite:
        return {
            "status": "error",
            "message": f"Stamp '{name}' already exists. Pass overwrite=True to replace it.",
        }

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    actor_count = data.get("actor_count", len(data.get("actors", [])))
    log_info(f"[STAMP] Imported '{name}' ({actor_count} actors) from {file_path}")
    return {"status": "ok", "name": name, "actor_count": actor_count, "path": dest}
