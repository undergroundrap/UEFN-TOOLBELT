"""
UEFN TOOLBELT — Actor Visibility & Lock Tools
==============================================
Hide, isolate, reveal, and lock actors from Python.
Built for fast-moving teams working in crowded shared levels.

Use cases:
  • Isolate your section while teammates work elsewhere
  • Fold away Zones/Signs/Devices while placing props
  • Lock final assets so they can't be dragged out of place
  • One command to restore everything when done
"""

from __future__ import annotations

import unreal
from ..registry import register_tool
from ..core import log_info, log_error


def _sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


# ── Visibility ─────────────────────────────────────────────────────────────────

@register_tool(
    name="actor_hide",
    category="Visibility",
    description=(
        "Hide selected actors in the editor viewport without deleting them. "
        "Reversible — use actor_show or actor_show_all to restore."
    ),
    tags=["visibility", "hide", "actor", "selection", "editor"],
)
def run_actor_hide(**kwargs) -> dict:
    """Hide all currently selected actors in the editor viewport."""
    try:
        sub = _sub()
        actors = sub.get_selected_level_actors()
        if not actors:
            return {"status": "error", "error": "No actors selected."}
        with unreal.ScopedEditorTransaction("Hide Actors"):
            for a in actors:
                a.set_is_temporarily_hidden_in_editor(True)
        log_info(f"actor_hide: hid {len(actors)} actor(s)")
        return {
            "status": "ok",
            "hidden": len(actors),
            "labels": [a.get_actor_label() for a in actors],
            "tip": "Run actor_show_all to restore all hidden actors at once.",
        }
    except Exception as e:
        log_error(f"actor_hide failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="actor_show",
    category="Visibility",
    description=(
        "Unhide currently selected actors. "
        "Use actor_show_all to restore every hidden actor in the level at once."
    ),
    tags=["visibility", "show", "unhide", "actor", "selection"],
)
def run_actor_show(**kwargs) -> dict:
    """Make the currently selected hidden actors visible again."""
    try:
        sub = _sub()
        actors = sub.get_selected_level_actors()
        if not actors:
            return {"status": "error", "error": "No actors selected."}
        with unreal.ScopedEditorTransaction("Show Actors"):
            for a in actors:
                a.set_is_temporarily_hidden_in_editor(False)
        log_info(f"actor_show: showed {len(actors)} actor(s)")
        return {"status": "ok", "shown": len(actors), "labels": [a.get_actor_label() for a in actors]}
    except Exception as e:
        log_error(f"actor_show failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="actor_isolate",
    category="Visibility",
    description=(
        "Hide every actor in the level EXCEPT the current selection. "
        "Focus on exactly your section. Run actor_show_all when done."
    ),
    tags=["visibility", "isolate", "hide", "section", "focus"],
)
def run_actor_isolate(**kwargs) -> dict:
    """
    Hide all level actors except those currently selected.
    Workflow: select what you want to see → actor_isolate → work → actor_show_all.
    """
    try:
        sub = _sub()
        selected = sub.get_selected_level_actors()
        if not selected:
            return {
                "status": "error",
                "error": "No actors selected. Select what you want to KEEP visible, then run this.",
            }
        keep = {id(a) for a in selected}
        all_actors = sub.get_all_level_actors()
        to_hide = [a for a in all_actors if id(a) not in keep]
        with unreal.ScopedEditorTransaction("Isolate Selection"):
            for a in to_hide:
                a.set_is_temporarily_hidden_in_editor(True)
        log_info(f"actor_isolate: {len(selected)} visible, {len(to_hide)} hidden")
        return {
            "status": "ok",
            "visible": len(selected),
            "hidden": len(to_hide),
            "tip": "Run actor_show_all to restore full level visibility.",
        }
    except Exception as e:
        log_error(f"actor_isolate failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="actor_show_all",
    category="Visibility",
    description=(
        "Restore visibility for every hidden actor in the level. "
        "The universal undo for actor_hide, actor_isolate, and folder_hide."
    ),
    tags=["visibility", "show", "restore", "unhide", "all", "reset"],
)
def run_actor_show_all(**kwargs) -> dict:
    """Un-hide every actor in the level — the global 'get everything back' command."""
    try:
        sub = _sub()
        restored = 0
        with unreal.ScopedEditorTransaction("Show All Actors"):
            for a in sub.get_all_level_actors():
                try:
                    if a.is_temporarily_hidden_in_editor():
                        a.set_is_temporarily_hidden_in_editor(False)
                        restored += 1
                except Exception:
                    continue
        log_info(f"actor_show_all: restored {restored} actor(s)")
        return {"status": "ok", "restored": restored}
    except Exception as e:
        log_error(f"actor_show_all failed: {e}")
        return {"status": "error", "error": str(e)}


# ── Folder visibility ──────────────────────────────────────────────────────────

@register_tool(
    name="folder_hide",
    category="Visibility",
    description=(
        "Hide all actors in a named World Outliner folder. "
        "Pair with folder_show or actor_show_all to restore."
    ),
    tags=["visibility", "hide", "folder", "outliner", "section"],
)
def run_folder_hide(folder_name: str = "", **kwargs) -> dict:
    """
    Hide all actors whose World Outliner folder path starts with folder_name.

    Args:
        folder_name: Folder path, e.g. 'Zones', 'Props/Trees', 'Devices'
    """
    if not folder_name:
        return {"status": "error", "error": "folder_name is required. Example: 'Zones' or 'Props/Trees'"}
    try:
        sub = _sub()
        target = folder_name.strip("/").lower()
        hidden = 0
        with unreal.ScopedEditorTransaction(f"Hide Folder: {folder_name}"):
            for a in sub.get_all_level_actors():
                try:
                    fp = str(a.get_folder_path()).strip("/").lower()
                    if fp == target or fp.startswith(target + "/"):
                        a.set_is_temporarily_hidden_in_editor(True)
                        hidden += 1
                except Exception:
                    continue
        log_info(f"folder_hide: hid {hidden} actor(s) in '{folder_name}'")
        return {"status": "ok", "hidden": hidden, "folder": folder_name}
    except Exception as e:
        log_error(f"folder_hide failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="folder_show",
    category="Visibility",
    description="Restore visibility for all actors in a named World Outliner folder.",
    tags=["visibility", "show", "folder", "outliner", "restore"],
)
def run_folder_show(folder_name: str = "", **kwargs) -> dict:
    """
    Un-hide all actors whose World Outliner folder path starts with folder_name.

    Args:
        folder_name: Folder path, e.g. 'Zones', 'Props/Trees', 'Devices'
    """
    if not folder_name:
        return {"status": "error", "error": "folder_name is required."}
    try:
        sub = _sub()
        target = folder_name.strip("/").lower()
        shown = 0
        with unreal.ScopedEditorTransaction(f"Show Folder: {folder_name}"):
            for a in sub.get_all_level_actors():
                try:
                    fp = str(a.get_folder_path()).strip("/").lower()
                    if fp == target or fp.startswith(target + "/"):
                        a.set_is_temporarily_hidden_in_editor(False)
                        shown += 1
                except Exception:
                    continue
        log_info(f"folder_show: showed {shown} actor(s) in '{folder_name}'")
        return {"status": "ok", "shown": shown, "folder": folder_name}
    except Exception as e:
        log_error(f"folder_show failed: {e}")
        return {"status": "error", "error": str(e)}


# ── Actor locking ──────────────────────────────────────────────────────────────

@register_tool(
    name="actor_lock",
    category="Visibility",
    description=(
        "Lock selected actors in place — prevents accidental moves, rotations, "
        "and scale changes in the viewport. Use actor_unlock to reverse."
    ),
    tags=["lock", "freeze", "protect", "actor", "placement"],
)
def run_actor_lock(**kwargs) -> dict:
    """Lock selected actors so they cannot be dragged or transformed in the viewport."""
    try:
        sub = _sub()
        actors = sub.get_selected_level_actors()
        if not actors:
            return {"status": "error", "error": "No actors selected."}
        locked = failed = 0
        errors = []
        with unreal.ScopedEditorTransaction("Lock Actors"):
            for a in actors:
                # Try bLockLocation first, then bLocked (UEFN property name varies by build)
                success = False
                for prop in ("bLockLocation", "bLocked"):
                    try:
                        a.set_editor_property(prop, True)
                        locked += 1
                        success = True
                        break
                    except Exception:
                        continue
                if not success:
                    failed += 1
                    errors.append(a.get_actor_label())
        if errors:
            log_info(f"actor_lock: locked {locked}, failed {failed} — UEFN may sandbox bLockLocation on: {errors}")
        else:
            log_info(f"actor_lock: locked {locked}")
        return {
            "status": "ok",
            "locked": locked,
            "failed": failed,
            "labels": [a.get_actor_label() for a in actors],
        }
    except Exception as e:
        log_error(f"actor_lock failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="actor_unlock",
    category="Visibility",
    description="Unlock selected actors — restores full move/rotate/scale in the viewport.",
    tags=["lock", "unlock", "actor", "selection", "transform"],
)
def run_actor_unlock(**kwargs) -> dict:
    """Unlock selected actors so they can be transformed freely in the viewport again."""
    try:
        sub = _sub()
        actors = sub.get_selected_level_actors()
        if not actors:
            return {"status": "error", "error": "No actors selected."}
        unlocked = failed = 0
        with unreal.ScopedEditorTransaction("Unlock Actors"):
            for a in actors:
                success = False
                for prop in ("bLockLocation", "bLocked"):
                    try:
                        a.set_editor_property(prop, False)
                        unlocked += 1
                        success = True
                        break
                    except Exception:
                        continue
                if not success:
                    failed += 1
        log_info(f"actor_unlock: unlocked {unlocked}, failed {failed}")
        return {"status": "ok", "unlocked": unlocked, "failed": failed}
    except Exception as e:
        log_error(f"actor_unlock failed: {e}")
        return {"status": "error", "error": str(e)}
