"""
UEFN TOOLBELT — Sign Tools
========================================
Bulk-spawn, batch-edit, and manage TextRenderActor signs and labels
in your UEFN level without touching every actor manually.

NOTE: These are TextRenderActors, NOT Fortnite Billboard devices.
TextRenderActors give full Python control over text, color, and size.
UEFN 42.00 remote validation rejects them. They are editor visualization only
and must be removed before Launch Session or publishing.

FEATURES:
  • Spawn N signs in a row, column, or grid at camera / any location
  • Auto-number labels  (Sign_01, Sign_02 …)
  • batch_edit — change text / color / size on every selected sign at once
  • batch_rename — sequential rename of selected signs
  • batch_set_text_list — assign individual text strings to each selected sign
  • clear — delete all signs in a named folder

USAGE:
    tb.run("sign_spawn_bulk", count=6, text="ZONE", spacing=400.0)
    tb.run("sign_batch_edit", color="#FF4400", world_size=120.0)
    tb.run("sign_batch_set_text", texts=["RED BASE","BLUE BASE","MID"])
    tb.run("sign_batch_rename", prefix="Sign", start=1)
    tb.run("sign_clear")
"""

from __future__ import annotations

import unreal

from ..core import log_error, log_info, log_warning
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

SIGN_FOLDER = "Signs"
_PUBLISH_BLOCKER_CLEANUP = 'tb.run("sign_clear", all_text_actors=True, dry_run=False)'

try:
    _H_ALIGN = {
        "left":   unreal.HorizTextAligment.EHTA_LEFT,
        "center": unreal.HorizTextAligment.EHTA_CENTER,
        "right":  unreal.HorizTextAligment.EHTA_RIGHT,
    }
    _V_ALIGN = {
        "top":    unreal.VerticalTextAligment.EVRTA_TEXT_TOP,
        "center": unreal.VerticalTextAligment.EVRTA_TEXT_CENTER,
        "bottom": unreal.VerticalTextAligment.EVRTA_TEXT_BOTTOM,
    }
except AttributeError:
    _H_ALIGN = {"left": "EHTA_Left", "center": "EHTA_Center", "right": "EHTA_Right"}
    _V_ALIGN = {"top": "EVRTA_TextTop", "center": "EVRTA_TextCenter", "bottom": "EVRTA_TextBottom"}

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _warn_publish_blocker(tool_name: str) -> None:
    log_warning(
        f"[{tool_name}] PUBLISH BLOCKER: TextRenderActor is disallowed by UEFN "
        f"remote validation. Remove these actors before Launch Session or publishing: "
        f"{_PUBLISH_BLOCKER_CLEANUP}"
    )


def _publish_blocker_result() -> dict[str, str]:
    return {
        "publish_blocker": "TextRenderActor",
        "cleanup": _PUBLISH_BLOCKER_CLEANUP,
    }

def _hex_to_fcolor(hex_str: str) -> unreal.Color:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    # Keyword args, not positional. FColor is declared (B, G, R, A) in C++ and
    # unreal's positional constructors follow field order - the same trap as
    # Quirk #41 - so unreal.Color(r, g, b, 255) can swap red and blue. Naming
    # them is correct under either order.
    return unreal.Color(r=r, g=g, b=b, a=255)


def _spawn_sign(
    text: str,
    location: unreal.Vector,
    yaw: float,
    color: str,
    world_size: float,
    h_align: str,
    v_align: str,
    label: str,
    folder: str,
) -> unreal.TextRenderActor | None:
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    rot = unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw)
    actor: unreal.TextRenderActor = actor_sub.spawn_actor_from_class(
        unreal.TextRenderActor, location, rot
    )
    if actor is None:
        log_error(f"sign_tools: failed to spawn actor at {location}")
        return None

    trc = actor.text_render
    trc.set_editor_property("text", text)
    trc.set_editor_property("text_render_color", _hex_to_fcolor(color))
    trc.set_editor_property("world_size", float(world_size))
    trc.set_editor_property("horizontal_alignment", _H_ALIGN.get(h_align, _H_ALIGN["center"]))
    trc.set_editor_property("vertical_alignment",   _V_ALIGN.get(v_align, _V_ALIGN["center"]))

    actor.set_actor_label(label)
    actor.set_folder_path(f"/{folder}")
    return actor


def _apply_style_to_actor(
    actor: unreal.TextRenderActor,
    text:       str | None,
    color:      str | None,
    world_size: float | None,
    h_align:    str | None,
    v_align:    str | None,
) -> None:
    trc = actor.text_render
    if text is not None:
        trc.set_editor_property("text", text)
    if color is not None:
        trc.set_editor_property("text_render_color", _hex_to_fcolor(color))
    if world_size is not None:
        trc.set_editor_property("world_size", float(world_size))
    if h_align is not None:
        trc.set_editor_property("horizontal_alignment", _H_ALIGN.get(h_align, _H_ALIGN["center"]))
    if v_align is not None:
        trc.set_editor_property("vertical_alignment", _V_ALIGN.get(v_align, _V_ALIGN["center"]))


def _get_selected_signs() -> list[unreal.TextRenderActor]:
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected  = actor_sub.get_selected_level_actors() or []
    return [a for a in selected if isinstance(a, unreal.TextRenderActor)]


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="sign_spawn_bulk",
    category="Text & Signs",
    description=(
        "Spawn N TextRenderActor signs in a row, column, or grid. PUBLISH BLOCKER: "
        "remove them before Launch Session or publishing. "
        "All signs get auto-numbered labels and share the same style. "
        "Omit location to spawn at world origin; use the dashboard to spawn at camera."
    ),
    tags=["billboard", "sign", "text", "bulk", "spawn", "label"],
)
def run_sign_spawn_bulk(
    count:      int   = 6,
    text:       str   = "SIGN",
    prefix:     str   = "Sign",
    location:   tuple[float, float, float] = (0.0, 0.0, 200.0),
    layout:     str   = "row_x",     # row_x | row_y | grid
    spacing:    float = 400.0,
    cols:       int   = 4,            # used when layout="grid"
    yaw:        float = 0.0,
    color:      str   = "#FFFFFF",
    world_size: float = 100.0,
    h_align:    str   = "center",
    v_align:    str   = "center",
    folder:     str   = SIGN_FOLDER,
    **kwargs,
) -> dict:
    """
    Spawn multiple billboards with one command.

    Args:
        count:      Number of billboards to spawn.
        text:       Default text on every sign (override per-sign with sign_batch_set_text).
        prefix:     Label prefix — labels become prefix_01, prefix_02, etc.
        location:   (x, y, z) world anchor for the first billboard.
        layout:     "row_x"  → equally spaced along X axis
                    "row_y"  → equally spaced along Y axis
                    "grid"   → grid of <cols> columns, expanding in X then Y
        spacing:    Distance between billboard centres (cm).
        cols:       Columns per row when layout="grid".
        yaw:        Rotation of each billboard (degrees). 0 = faces +X direction.
        color:      Hex color string e.g. "#FF4400".
        world_size: Font size in world units (cm).
        h_align:    "left" | "center" | "right"
        v_align:    "top"  | "center" | "bottom"
        folder:     World Outliner folder name.

    Returns:
        {"status", "spawned", "folder", "labels"}
    """
    _warn_publish_blocker("sign_spawn_bulk")
    ox, oy, oz = location
    labels: list[str] = []

    with unreal.ScopedEditorTransaction("Billboard Spawn Bulk") as _t:
        for i in range(count):
            if layout == "row_x":
                wx, wy, wz = ox + i * spacing, oy, oz
            elif layout == "row_y":
                wx, wy, wz = ox, oy + i * spacing, oz
            else:  # grid
                col = i % cols
                row = i // cols
                wx, wy, wz = ox + col * spacing, oy + row * spacing, oz

            label = f"{prefix}_{i + 1:02d}"
            actor = _spawn_sign(text, unreal.Vector(wx, wy, wz), yaw,
                                     color, world_size, h_align, v_align, label, folder)
            if actor:
                labels.append(label)

    log_info(f"[sign_spawn_bulk] Spawned {len(labels)} signs in folder '{folder}'.")
    return {
        "status": "ok",
        "spawned": len(labels),
        "folder": folder,
        "labels": labels,
        **_publish_blocker_result(),
    }


@register_tool(
    name="sign_batch_edit",
    category="Text & Signs",
    description=(
        "Edit text, color, and/or size on all currently selected billboards at once. "
        "Only the fields you provide are changed — omit a field to leave it untouched."
    ),
    tags=["billboard", "sign", "text", "batch", "edit", "color", "size"],
)
def run_sign_batch_edit(
    text:       str | None   = None,
    color:      str | None   = None,
    world_size: float | None = None,
    h_align:    str | None   = None,
    v_align:    str | None   = None,
    **kwargs,
) -> dict:
    """
    Batch-edit all selected TextRenderActor billboards.

    Select the signs you want to change in the viewport, then call this tool.
    Only the arguments you supply are applied — unspecified fields are left alone.

    Args:
        text:       New text for every selected billboard.
        color:      New hex color e.g. "#00FF88".
        world_size: New font size (cm).
        h_align:    "left" | "center" | "right"
        v_align:    "top"  | "center" | "bottom"

    Returns:
        {"status", "edited", "skipped"}
    """
    signs = _get_selected_signs()
    if not signs:
        log_warning("[sign_batch_edit] No signs selected.")
        return {"status": "error", "message": "No signs selected. Select signs in the viewport first."}

    if all(v is None for v in (text, color, world_size, h_align, v_align)):
        return {"status": "error", "message": "No fields provided. Pass at least one of: text, color, world_size, h_align, v_align."}

    edited = 0
    with unreal.ScopedEditorTransaction("Billboard Batch Edit") as _t:
        for actor in signs:
            try:
                _apply_style_to_actor(actor, text, color, world_size, h_align, v_align)
                edited += 1
            except Exception as e:
                log_warning(f"[sign_batch_edit] Skipped {actor.get_actor_label()}: {e}")

    log_info("[sign_batch_edit] Edited signs.")
    return {"status": "ok", "edited": edited, "skipped": len(signs) - edited}


@register_tool(
    name="sign_batch_set_text",
    category="Text & Signs",
    description=(
        "Assign individual text strings to each selected billboard in order. "
        "Select 3 signs, pass texts=['RED BASE','BLUE BASE','MID'] — each gets its own text."
    ),
    tags=["billboard", "sign", "text", "batch", "set", "individual"],
)
def run_sign_batch_set_text(
    texts: list[str] = None,
    **kwargs,
) -> dict:
    """
    Set individual text on each selected billboard in selection order.

    Args:
        texts: List of strings — one per selected billboard.
               Extra texts are ignored; if fewer than selected, remaining signs unchanged.

    Returns:
        {"status", "assigned", "total_selected"}
    """
    if not texts:
        return {"status": "error", "message": "Pass texts=[...] with one string per sign."}

    signs = _get_selected_signs()
    if not signs:
        return {"status": "error", "message": "No signs selected. Select signs in the viewport first."}

    assigned = 0
    with unreal.ScopedEditorTransaction("Billboard Batch Set Text") as _t:
        for actor, new_text in zip(signs, texts, strict=False):
            try:
                actor.text_render.set_editor_property("text", new_text)
                assigned += 1
            except Exception as e:
                log_warning(f"[sign_batch_set_text] Skipped {actor.get_actor_label()}: {e}")

    log_info(f"[sign_batch_set_text] Assigned {assigned} texts to {len(signs)} selected signs.")
    return {"status": "ok", "assigned": assigned, "total_selected": len(signs)}


@register_tool(
    name="sign_batch_rename",
    category="Text & Signs",
    description=(
        "Sequentially rename all selected billboards: prefix_01, prefix_02, etc. "
        "Optionally sync the visible text to match the label."
    ),
    tags=["billboard", "sign", "rename", "batch", "label"],
)
def run_sign_batch_rename(
    prefix:     str  = "Sign",
    start:      int  = 1,
    sync_text:  bool = False,
    **kwargs,
) -> dict:
    """
    Rename selected billboards sequentially.

    Args:
        prefix:    Label prefix e.g. "Zone" → Zone_01, Zone_02 …
        start:     Starting index (default 1).
        sync_text: If True, also update the visible text to match the new label.

    Returns:
        {"status", "renamed"}
    """
    signs = _get_selected_signs()
    if not signs:
        return {"status": "error", "message": "No signs selected."}

    renamed = 0
    text_failures = 0
    with unreal.ScopedEditorTransaction("Billboard Batch Rename") as _t:
        for i, actor in enumerate(signs):
            new_label = f"{prefix}_{start + i:02d}"
            actor.set_actor_label(new_label)
            if sync_text:
                try:
                    actor.text_render.set_editor_property("text", new_label)
                except Exception as e:
                    text_failures += 1
                    log_warning(
                        f"[sign_batch_rename] '{new_label}' was renamed but its "
                        f"displayed text could not be updated: {e}"
                    )
            renamed += 1

    log_info(f"[sign_batch_rename] Renamed {renamed} signs with prefix '{prefix}'.")
    return {"status": "ok", "renamed": renamed}


@register_tool(
    name="sign_list",
    category="Text & Signs",
    description="List all billboards in a folder (or all TextRenderActors in the level) with their current text.",
    tags=["billboard", "sign", "list", "audit"],
)
def run_sign_list(
    folder: str = "",
    **kwargs,
) -> dict:
    """
    Return a summary of all TextRenderActors in the level (or filtered by folder).

    Args:
        folder: World Outliner folder name to filter by. Empty = list all.

    Returns:
        {"status", "count", "billboards": [{"label", "text", "location", "folder"}]}
    """
    actor_sub  = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors() or []

    results = []
    for actor in all_actors:
        if not isinstance(actor, unreal.TextRenderActor):
            continue
        actor_folder = str(actor.get_folder_path()).strip("/")
        if folder and folder.lower() not in actor_folder.lower():
            continue
        try:
            text = str(actor.text_render.get_editor_property("text"))
        except Exception:
            text = "<error>"
        loc = actor.get_actor_location()
        results.append({
            "label":    actor.get_actor_label(),
            "text":     text,
            "location": (round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)),
            "folder":   actor_folder,
        })

    log_info(f"[sign_list] Found {len(results)} sign(s).")
    return {"status": "ok", "count": len(results), "billboards": results}


@register_tool(
    name="sign_clear",
    category="Text & Signs",
    description=(
        "Delete TextRenderActors in a named folder, or pass all_text_actors=True "
        "to remove every publish-blocking TextRenderActor from the level."
    ),
    tags=["billboard", "sign", "clear", "delete"],
)
def run_sign_clear(
    folder: str = SIGN_FOLDER,
    dry_run: bool = False,
    all_text_actors: bool = False,
    **kwargs,
) -> dict:
    """
    Delete all TextRenderActors inside a given World Outliner folder.

    Args:
        folder:          Folder name to clear (default: "Signs").
        dry_run:         If True, report what would be deleted without deleting.
        all_text_actors: If True, ignore folder and delete every TextRenderActor.

    Returns:
        {"status", "deleted", "dry_run"}
    """
    actor_sub  = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors() or []

    targets = [a for a in all_actors if isinstance(a, unreal.TextRenderActor) and (
        all_text_actors or folder.lower() in str(a.get_folder_path()).lower()
    )]
    scope = "the level" if all_text_actors else f"'{folder}'"

    if dry_run:
        log_info(f"[sign_clear] DRY RUN — would delete {len(targets)} signs from {scope}.")
        return {"status": "ok", "deleted": 0, "would_delete": len(targets),
                "dry_run": True, "all_text_actors": all_text_actors}

    if not targets and all_text_actors:
        log_info("[sign_clear] No publish-blocking TextRenderActors remain in the level.")
        return {"status": "ok", "deleted": 0, "attempted": 0,
                "dry_run": False, "all_text_actors": True}

    deleted = 0
    with unreal.ScopedEditorTransaction("Billboard Clear") as _t:
        for actor in targets:
            # destroy_actor reports failure by returning False. Reporting
            # len(targets) meant a sign that survived was still counted deleted.
            if actor_sub.destroy_actor(actor):
                deleted += 1
            else:
                log_warning(
                    f"[sign_clear] '{actor.get_actor_label()}' could not be "
                    f"deleted - it may be locked or in a read-only sublevel."
                )

    if deleted == 0:
        log_error(f"[sign_clear] Deleted 0 of {len(targets)} signs in {scope}.")
        return {"status": "error", "deleted": 0, "attempted": len(targets),
                "dry_run": False, "all_text_actors": all_text_actors,
                "reason": "nothing_deleted"}
    log_info(f"[sign_clear] Deleted {deleted} of {len(targets)} signs from {scope}.")
    return {"status": "ok" if deleted == len(targets) else "partial",
            "deleted": deleted, "attempted": len(targets), "dry_run": False,
            "all_text_actors": all_text_actors}


@register_tool(
    name="label_attach",
    category="Text & Signs",
    description=(
        "Spawn a floating TextRenderActor label above each selected actor. PUBLISH BLOCKER: "
        "remove labels before Launch Session or publishing. The label "
        "moves with the actor. Perfect for NPC name tags, device markers, and prop labels. "
        "Label text defaults to the actor's own name."
    ),
    tags=["label", "attach", "npc", "tag", "sign", "text", "floating", "overhead"],
)
def run_label_attach(
    text:           str   = "",
    offset_z:       float = 150.0,
    yaw:            float = 0.0,
    color:          str   = "#FFFFFF",
    world_size:     float = 60.0,
    use_actor_name: bool  = True,
    folder:         str   = "Labels",
    **kwargs,
) -> dict:
    """
    Attach a floating text label above every selected actor.

    The label is parented to the actor so it moves/rotates with it in the editor.

    Args:
        text:           Text to show. If empty and use_actor_name=True, uses actor label.
        offset_z:       Height above the actor's top bound (cm).
        yaw:            Rotation of the label in degrees (0 = faces +X, 90 = faces +Y).
        color:          Hex color string e.g. "#00FFCC".
        world_size:     Font size in world units (cm).
        use_actor_name: If True, each label shows its actor's own name (ignores text arg).
        folder:         World Outliner folder for the label actors.

    Returns:
        {"status", "attached", "skipped"}
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected  = actor_sub.get_selected_level_actors() or []

    if not selected:
        return {"status": "error", "message": "No actors selected. Select actors in the viewport first."}

    _warn_publish_blocker("label_attach")
    attached = skipped = 0

    with unreal.ScopedEditorTransaction("Label Attach") as _t:
        for parent in selected:
            # Skip existing TextRenderActors — don't label a label
            if isinstance(parent, unreal.TextRenderActor):
                skipped += 1
                continue

            try:
                loc = parent.get_actor_location()

                # Place label above the actor's bounding box top
                try:
                    origin_v, extent_v = parent.get_actor_bounds(False)
                    top_z = origin_v.z + extent_v.z + offset_z
                except Exception:
                    top_z = loc.z + offset_z

                label_text = parent.get_actor_label() if use_actor_name else (text or parent.get_actor_label())
                actor_label = f"Label_{parent.get_actor_label()}"

                label_actor = _spawn_sign(
                    label_text,
                    unreal.Vector(loc.x, loc.y, top_z),
                    yaw,
                    color, world_size,
                    "center", "center",
                    actor_label, folder,
                )

                if label_actor is None:
                    skipped += 1
                    continue

                # Attach label to parent so it follows it
                try:
                    r = unreal.AttachmentRule
                    label_actor.attach_to_actor(parent, "", r.KEEP_WORLD, r.KEEP_RELATIVE, r.KEEP_RELATIVE, False)
                except Exception as attach_err:
                    log_warning(f"[label_attach] attach_to_actor failed on {parent.get_actor_label()}: {attach_err} — label placed but not parented")

                attached += 1

            except Exception as e:
                log_warning(f"[label_attach] Failed on {parent.get_actor_label()}: {e}")
                skipped += 1

    log_info(f"[label_attach] Attached {attached} labels, skipped {skipped}.")
    return {
        "status": "ok",
        "attached": attached,
        "skipped": skipped,
        "folder": folder,
        **_publish_blocker_result(),
    }
