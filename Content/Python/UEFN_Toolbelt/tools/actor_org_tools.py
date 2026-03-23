"""
UEFN TOOLBELT — Actor Organization Toolkit
===========================================
Parenting, folder management, and selection helpers for the World Outliner.
Every mutating operation is wrapped in a ScopedEditorTransaction for full undo support.

OPERATIONS:
  actor_attach_to_parent   — Maya-style: last selected becomes parent of all others
  actor_detach             — Detach all selected actors from their parent
  actor_move_to_folder     — Move selected actors into a named World Outliner folder
  actor_move_to_root       — Move selected actors to the root (no folder)
  actor_rename_folder      — Rename / move all actors from one folder path to another
  actor_select_by_folder   — Select all actors in a named folder
  actor_select_same_folder — Expand selection to all actors sharing the first actor's folder
  actor_select_by_class    — Select all level actors whose class name contains a filter string
  actor_folder_list        — List all World Outliner folders with per-folder actor counts
  actor_match_transform    — Copy transform from the first selected actor to all others

USAGE:
    import UEFN_Toolbelt as tb

    tb.run("actor_attach_to_parent")
    tb.run("actor_detach")
    tb.run("actor_move_to_folder", folder_name="Gameplay/Triggers")
    tb.run("actor_move_to_root")
    tb.run("actor_rename_folder", old_folder="Props", new_folder="Props/Static", dry_run=False)
    tb.run("actor_select_by_folder", folder_name="Gameplay/Triggers")
    tb.run("actor_select_same_folder")
    tb.run("actor_select_by_class", class_filter="TimerDevice")
    tb.run("actor_folder_list")
    tb.run("actor_match_transform", copy_location=True, copy_rotation=True, copy_scale=False)
"""

from __future__ import annotations

import unreal
from typing import List, Optional, Tuple

from ..core import log_info, log_error, log_warning
from ..registry import register_tool


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _actor_sub() -> unreal.EditorActorSubsystem:
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _get_selected() -> List[unreal.Actor]:
    selected = _actor_sub().get_selected_level_actors() or []
    return list(selected)


def _get_all_level_actors() -> List[unreal.Actor]:
    actors = _actor_sub().get_all_level_actors() or []
    return list(actors)


def _actor_folder(actor: unreal.Actor) -> str:
    """Return the actor's World Outliner folder path, or '' for root."""
    try:
        path = actor.get_folder_path()
        # get_folder_path returns an FName; convert to str and strip 'None' sentinel
        result = str(path) if path else ""
        return result if result.lower() not in ("none", "null") else ""
    except Exception:
        return ""


def _attach(child: unreal.Actor, parent: unreal.Actor) -> None:
    """Attach child to parent, keeping world-space transform. Handles API variation."""
    try:
        child.attach_to_actor(
            parent,
            "",
            unreal.AttachmentRule.KEEP_WORLD,
            unreal.AttachmentRule.KEEP_WORLD,
            unreal.AttachmentRule.KEEP_WORLD,
            False,
        )
    except (AttributeError, TypeError):
        # Fallback: integer enum values — KEEP_WORLD = 1
        child.attach_to_actor(parent, "", 1, 1, 1, False)


def _detach(actor: unreal.Actor) -> None:
    """Detach actor from its parent, keeping world-space transform. Handles API variation."""
    try:
        actor.detach_from_actor(
            unreal.DetachmentRule.KEEP_WORLD,
            unreal.DetachmentRule.KEEP_WORLD,
            unreal.DetachmentRule.KEEP_WORLD,
        )
    except (AttributeError, TypeError):
        # Fallback: integer enum values — KEEP_WORLD = 1
        actor.detach_from_actor(1, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="actor_attach_to_parent",
    category="Actor Organization",
    description=(
        "Maya-style parent: the LAST selected actor becomes the parent, "
        "all other selected actors become its children. Preserves world transforms."
    ),
    tags=["attach", "parent", "hierarchy", "selection", "maya"],
)
def actor_attach_to_parent(**kwargs) -> dict:
    """
    Attach selected actors to the last selected actor as children.

    Selection order matters: the final actor in the selection list is treated
    as the parent. All preceding actors are re-parented to it. World-space
    transforms are preserved (KEEP_WORLD attachment rule).

    Returns:
        dict: {"status", "attached": int, "parent_label": str}
    """
    selected = _get_selected()
    if len(selected) < 2:
        msg = "actor_attach_to_parent: select at least 2 actors (children … parent)."
        log_warning(msg)
        return {"status": "error", "message": msg}

    parent = selected[-1]
    children = selected[:-1]
    parent_label = parent.get_actor_label()

    attached = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Attach to Parent") as _t:
        for child in children:
            try:
                _attach(child, parent)
                attached += 1
                log_info(f"  Attached '{child.get_actor_label()}' → '{parent_label}'")
            except Exception as e:
                log_error(f"  Failed to attach '{child.get_actor_label()}': {e}")

    log_info(f"actor_attach_to_parent: {attached} actor(s) attached to '{parent_label}'.")
    return {"status": "ok", "attached": attached, "parent_label": parent_label}


@register_tool(
    name="actor_detach",
    category="Actor Organization",
    description="Detach all selected actors from their current parent. Preserves world transforms.",
    tags=["detach", "parent", "hierarchy", "selection"],
)
def actor_detach(**kwargs) -> dict:
    """
    Detach each selected actor from its parent actor.

    World-space location, rotation, and scale are preserved after detachment.
    Actors that have no parent are silently skipped.

    Returns:
        dict: {"status", "detached": int}
    """
    selected = _get_selected()
    if not selected:
        msg = "actor_detach: nothing selected."
        log_warning(msg)
        return {"status": "error", "message": msg}

    detached = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Detach Actors") as _t:
        for actor in selected:
            try:
                _detach(actor)
                detached += 1
                log_info(f"  Detached '{actor.get_actor_label()}'")
            except Exception as e:
                log_error(f"  Failed to detach '{actor.get_actor_label()}': {e}")

    log_info(f"actor_detach: {detached} actor(s) detached.")
    return {"status": "ok", "detached": detached}


@register_tool(
    name="actor_move_to_folder",
    category="Actor Organization",
    description="Move all selected actors into a named World Outliner folder (created automatically).",
    tags=["folder", "organize", "outliner", "selection"],
)
def actor_move_to_folder(folder_name: str = "Folder", **kwargs) -> dict:
    """
    Move selected actors into the specified World Outliner folder.

    The folder is created automatically if it does not exist — Unreal's
    set_folder_path API handles creation transparently.

    Args:
        folder_name: Slash-separated path, e.g. "Gameplay/Triggers". Required.

    Returns:
        dict: {"status", "moved": int, "folder": str}
    """
    if not folder_name or not folder_name.strip():
        return {"status": "error", "message": "folder_name is required."}

    folder_name = folder_name.strip()
    selected = _get_selected()
    if not selected:
        msg = "actor_move_to_folder: nothing selected."
        log_warning(msg)
        return {"status": "error", "message": msg}

    moved = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Move Actors to Folder") as _t:
        for actor in selected:
            try:
                actor.set_folder_path(folder_name)
                moved += 1
            except Exception as e:
                log_error(f"  Failed to move '{actor.get_actor_label()}' to '{folder_name}': {e}")

    log_info(f"actor_move_to_folder: {moved} actor(s) moved to '{folder_name}'.")
    return {"status": "ok", "moved": moved, "folder": folder_name}


@register_tool(
    name="actor_move_to_root",
    category="Actor Organization",
    description="Move all selected actors out of any World Outliner folder to the root level.",
    tags=["folder", "organize", "outliner", "root", "selection"],
)
def actor_move_to_root(**kwargs) -> dict:
    """
    Remove selected actors from their current folder and place them at root.

    Passing an empty string to set_folder_path moves the actor to the top-level
    (unfoldered) position in the World Outliner.

    Returns:
        dict: {"status", "moved": int}
    """
    selected = _get_selected()
    if not selected:
        msg = "actor_move_to_root: nothing selected."
        log_warning(msg)
        return {"status": "error", "message": msg}

    moved = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Move Actors to Root") as _t:
        for actor in selected:
            try:
                actor.set_folder_path("")
                moved += 1
            except Exception as e:
                log_error(f"  Failed to move '{actor.get_actor_label()}' to root: {e}")

    log_info(f"actor_move_to_root: {moved} actor(s) moved to root.")
    return {"status": "ok", "moved": moved}


@register_tool(
    name="actor_rename_folder",
    category="Actor Organization",
    description=(
        "Move all actors currently in old_folder to new_folder. "
        "Supports dry_run to preview without making changes."
    ),
    tags=["folder", "rename", "organize", "outliner"],
)
def actor_rename_folder(
    old_folder: str = "",
    new_folder: str = "",
    dry_run: bool = False,
    **kwargs,
) -> dict:
    """
    Rename a World Outliner folder by re-pathing every actor inside it.

    All actors whose folder path exactly matches old_folder are moved to new_folder.
    Actors in sub-folders of old_folder are NOT affected (use a trailing slash pattern
    or run multiple times for nested moves).

    Args:
        old_folder: Exact folder path to match, e.g. "Props".
        new_folder: Destination folder path, e.g. "Props/Static".
        dry_run:    If True, report what would change without modifying anything.

    Returns:
        dict: {"status", "moved": int, "dry_run": bool}
    """
    if not old_folder.strip():
        return {"status": "error", "message": "old_folder is required."}
    if not new_folder.strip():
        return {"status": "error", "message": "new_folder is required."}

    old_folder = old_folder.strip()
    new_folder = new_folder.strip()

    all_actors = _get_all_level_actors()
    targets = [a for a in all_actors if _actor_folder(a) == old_folder]

    if not targets:
        log_info(f"actor_rename_folder: no actors found in folder '{old_folder}'.")
        return {"status": "ok", "moved": 0, "dry_run": dry_run}

    if dry_run:
        labels = [a.get_actor_label() for a in targets]
        log_info(
            f"actor_rename_folder (dry_run): would move {len(targets)} actor(s) "
            f"from '{old_folder}' → '{new_folder}': {labels}"
        )
        return {"status": "ok", "moved": len(targets), "dry_run": True}

    moved = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Rename Folder") as _t:
        for actor in targets:
            try:
                actor.set_folder_path(new_folder)
                moved += 1
            except Exception as e:
                log_error(f"  Failed to re-path '{actor.get_actor_label()}': {e}")

    log_info(
        f"actor_rename_folder: {moved} actor(s) moved from '{old_folder}' → '{new_folder}'."
    )
    return {"status": "ok", "moved": moved, "dry_run": False}


@register_tool(
    name="actor_select_by_folder",
    category="Actor Organization",
    description="Select all actors whose World Outliner folder exactly matches folder_name.",
    tags=["select", "folder", "outliner"],
)
def actor_select_by_folder(folder_name: str = "", **kwargs) -> dict:
    """
    Select every actor that lives in the specified World Outliner folder.

    The match is exact — "Props" does not match "Props/Static". Pass an empty
    string to select all root-level (unfoldered) actors.

    Args:
        folder_name: Folder path to match. Empty string selects root actors.

    Returns:
        dict: {"status", "selected": int, "folder": str}
    """
    folder_name = folder_name.strip()
    all_actors = _get_all_level_actors()
    matches = [a for a in all_actors if _actor_folder(a) == folder_name]

    if not matches:
        msg = f"actor_select_by_folder: no actors found in folder '{folder_name}'."
        log_warning(msg)
        return {"status": "ok", "selected": 0, "folder": folder_name}

    _actor_sub().set_selected_level_actors(matches)
    log_info(
        f"actor_select_by_folder: selected {len(matches)} actor(s) in '{folder_name}'."
    )
    return {"status": "ok", "selected": len(matches), "folder": folder_name}


@register_tool(
    name="actor_select_same_folder",
    category="Actor Organization",
    description=(
        "Expand the selection to all actors that share the same World Outliner folder "
        "as the first currently selected actor."
    ),
    tags=["select", "folder", "outliner", "expand"],
)
def actor_select_same_folder(**kwargs) -> dict:
    """
    Select all actors in the same folder as the first currently selected actor.

    The first actor in the active selection determines the target folder. All level
    actors whose folder path matches that folder are then selected (replacing the
    current selection).

    Returns:
        dict: {"status", "selected": int, "folder": str}
    """
    selected = _get_selected()
    if not selected:
        msg = "actor_select_same_folder: nothing selected — select at least one actor first."
        log_warning(msg)
        return {"status": "error", "message": msg}

    folder = _actor_folder(selected[0])
    all_actors = _get_all_level_actors()
    matches = [a for a in all_actors if _actor_folder(a) == folder]

    _actor_sub().set_selected_level_actors(matches)
    folder_display = folder if folder else "(root)"
    log_info(
        f"actor_select_same_folder: selected {len(matches)} actor(s) in '{folder_display}'."
    )
    return {"status": "ok", "selected": len(matches), "folder": folder_display}


@register_tool(
    name="actor_select_by_class",
    category="Actor Organization",
    description="Select all level actors whose class name contains the given filter string (case-insensitive).",
    tags=["select", "class", "filter"],
)
def actor_select_by_class(class_filter: str = "", **kwargs) -> dict:
    """
    Select all actors in the level whose class name matches a substring filter.

    The comparison is case-insensitive. For example, class_filter="timer" will
    match actors of class TimerDevice, TimerActor, etc.

    Args:
        class_filter: Substring to match against each actor's class name.

    Returns:
        dict: {"status", "selected": int}
    """
    if not class_filter.strip():
        return {"status": "error", "message": "class_filter is required."}

    needle = class_filter.strip().lower()
    all_actors = _get_all_level_actors()
    matches = [
        a for a in all_actors
        if needle in a.get_class().get_name().lower()
    ]

    if not matches:
        log_info(f"actor_select_by_class: no actors found with class containing '{class_filter}'.")
        return {"status": "ok", "selected": 0}

    _actor_sub().set_selected_level_actors(matches)
    log_info(
        f"actor_select_by_class: selected {len(matches)} actor(s) "
        f"matching class filter '{class_filter}'."
    )
    return {"status": "ok", "selected": len(matches)}


@register_tool(
    name="actor_folder_list",
    category="Actor Organization",
    description="List all World Outliner folders with actor counts. Root actors are listed under '(root)'.",
    tags=["folder", "outliner", "list", "audit"],
)
def actor_folder_list(**kwargs) -> dict:
    """
    Scan all level actors and build a folder → count map.

    Actors not assigned to any folder are counted under the key "(root)".
    This gives a quick overview of how the World Outliner is organised without
    needing to open the editor UI.

    Returns:
        dict: {
            "status",
            "folders": {"FolderName": count, ...},
            "total_actors": int
        }
    """
    all_actors = _get_all_level_actors()
    folder_counts: dict = {}

    for actor in all_actors:
        folder = _actor_folder(actor)
        key = folder if folder else "(root)"
        folder_counts[key] = folder_counts.get(key, 0) + 1

    # Sort by folder name for readability
    sorted_folders = dict(sorted(folder_counts.items()))

    log_info(
        f"actor_folder_list: {len(sorted_folders)} folder(s), "
        f"{len(all_actors)} total actor(s)."
    )
    for folder, count in sorted_folders.items():
        log_info(f"  {folder}: {count}")

    return {
        "status": "ok",
        "folders": sorted_folders,
        "total_actors": len(all_actors),
    }


@register_tool(
    name="actor_match_transform",
    category="Actor Organization",
    description=(
        "Copy the transform of the first selected actor to all other selected actors. "
        "Independently toggle location, rotation, and scale copying."
    ),
    tags=["transform", "match", "copy", "align", "selection"],
)
def actor_match_transform(
    copy_location: bool = True,
    copy_rotation: bool = True,
    copy_scale: bool = False,
    **kwargs,
) -> dict:
    """
    Match transform components from the first selected actor to all others.

    The first actor in the selection is the source. All remaining selected actors
    have the chosen transform components overwritten with the source values.

    Args:
        copy_location: If True, copy world-space XYZ location.
        copy_rotation: If True, copy world-space pitch/yaw/roll rotation.
        copy_scale:    If True, copy world-space scale (default False to avoid
                       accidentally flattening procedural scale variation).

    Returns:
        dict: {"status", "applied": int}
    """
    selected = _get_selected()
    if len(selected) < 2:
        msg = "actor_match_transform: select at least 2 actors (source + targets)."
        log_warning(msg)
        return {"status": "error", "message": msg}

    source = selected[0]
    targets = selected[1:]

    src_loc = source.get_actor_location()
    src_rot = source.get_actor_rotation()
    src_scale = source.get_actor_scale3d()

    applied = 0
    with unreal.ScopedEditorTransaction("Toolbelt: Match Transform") as _t:
        for actor in targets:
            try:
                loc = src_loc if copy_location else actor.get_actor_location()
                rot = src_rot if copy_rotation else actor.get_actor_rotation()
                scale = src_scale if copy_scale else actor.get_actor_scale3d()
                actor.set_actor_location_and_rotation(loc, rot, False, False)
                actor.set_actor_scale3d(scale)
                applied += 1
            except Exception as e:
                log_error(f"  Failed to match transform on '{actor.get_actor_label()}': {e}")

    log_info(
        f"actor_match_transform: transform applied to {applied} actor(s) "
        f"(loc={copy_location}, rot={copy_rotation}, scale={copy_scale})."
    )
    return {"status": "ok", "applied": applied}
