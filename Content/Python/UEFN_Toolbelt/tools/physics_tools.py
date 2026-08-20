"""
UEFN TOOLBELT — Physics Tools
==============================
Batch-enable or disable simulated physics on selected StaticMesh actors.
Mirrors the "Add Physics" workflow from Fortnite Tools Mode, fully scriptable.

OPERATIONS:
  physics_add    — Enable Simulate Physics on selected StaticMesh actors
  physics_remove — Disable Simulate Physics on selected StaticMesh actors
  physics_list   — Audit selected actors — report which have physics enabled

USAGE:
    import UEFN_Toolbelt as tb

    tb.run("physics_add")                  # enable on selection
    tb.run("physics_remove")               # disable on selection
    tb.run("physics_list")                 # audit without changing anything

NOTE:
  Physics simulation is an editor-side property. In Fortnite gameplay, the
  FortPhysics component governs runtime physics. Setting Simulate Physics here
  configures the StaticMeshComponent's editor default — equivalent to checking
  "Simulate Physics" in the actor's Details panel.

  Only StaticMesh actors are supported. Blueprint actors, devices, and lights
  are skipped with a warning. All operations are wrapped in a ScopedEditorTransaction
  (Ctrl+Z to undo).
"""

import unreal

from ..core import get_selected_actors, log_info, log_warning
from ..registry import register_tool


def _get_mesh_component(actor):
    """Return the first StaticMeshComponent on an actor, or None."""
    try:
        return actor.get_component_by_class(unreal.StaticMeshComponent)
    except Exception:
        return None


# ── physics_add ───────────────────────────────────────────────────────────────

@register_tool(
    name="physics_add",
    category="Physics",
    description=(
        "Enable Simulate Physics on all selected StaticMesh actors. "
        "Equivalent to Fortnite Tools Mode 'Add Physics'. Fully undoable."
    ),
    tags=["physics", "simulate", "bulk", "selection"],
    example='tb.run("physics_add")',
)
def run_physics_add(**kwargs) -> dict:
    """
    Returns:
        dict: {"status", "enabled", "skipped", "actors"}
    """
    actors = get_selected_actors()
    if not actors:
        log_warning("[physics_add] No actors selected.")
        return {"status": "error", "message": "No actors selected.", "enabled": 0}

    enabled = []
    skipped = []

    with unreal.ScopedEditorTransaction("Toolbelt: physics_add"):
        for actor in actors:
            comp = _get_mesh_component(actor)
            if comp is None:
                skipped.append(actor.get_actor_label())
                continue
            try:
                comp.set_simulate_physics(True)
                enabled.append(actor.get_actor_label())
            except Exception as e:
                log_warning(f"[physics_add] Skipped {actor.get_actor_label()}: {e}")
                skipped.append(actor.get_actor_label())

    log_info(f"[physics_add] Enabled: {len(enabled)}, Skipped: {len(skipped)}")
    return {
        "status": "ok",
        "enabled": len(enabled),
        "skipped": len(skipped),
        "actors": enabled,
        "skipped_actors": skipped,
    }


# ── physics_remove ────────────────────────────────────────────────────────────

@register_tool(
    name="physics_remove",
    category="Physics",
    description=(
        "Disable Simulate Physics on all selected StaticMesh actors. "
        "Equivalent to Fortnite Tools Mode 'Remove Physics'. Fully undoable."
    ),
    tags=["physics", "simulate", "bulk", "selection"],
    example='tb.run("physics_remove")',
)
def run_physics_remove(**kwargs) -> dict:
    """
    Returns:
        dict: {"status", "disabled", "skipped", "actors"}
    """
    actors = get_selected_actors()
    if not actors:
        log_warning("[physics_remove] No actors selected.")
        return {"status": "error", "message": "No actors selected.", "disabled": 0}

    disabled = []
    skipped = []

    with unreal.ScopedEditorTransaction("Toolbelt: physics_remove"):
        for actor in actors:
            comp = _get_mesh_component(actor)
            if comp is None:
                skipped.append(actor.get_actor_label())
                continue
            try:
                comp.set_simulate_physics(False)
                disabled.append(actor.get_actor_label())
            except Exception as e:
                log_warning(f"[physics_remove] Skipped {actor.get_actor_label()}: {e}")
                skipped.append(actor.get_actor_label())

    log_info(f"[physics_remove] Disabled: {len(disabled)}, Skipped: {len(skipped)}")
    return {
        "status": "ok",
        "disabled": len(disabled),
        "skipped": len(skipped),
        "actors": disabled,
        "skipped_actors": skipped,
    }


# ── physics_list ──────────────────────────────────────────────────────────────

@register_tool(
    name="physics_list",
    category="Physics",
    description=(
        "Audit selected actors — report which are physics-capable (have a StaticMeshComponent) "
        "vs which will be skipped by physics_add/physics_remove. Read-only, no changes made. "
        "Note: UEFN sandboxes the physics state read — use the Details panel to see current state."
    ),
    tags=["physics", "simulate", "audit", "selection"],
    example='tb.run("physics_list")',
)
def run_physics_list(**kwargs) -> dict:
    """
    Returns:
        dict: {"status", "total", "capable", "not_capable", "actors"}
    """
    actors = get_selected_actors()
    if not actors:
        log_warning("[physics_list] No actors selected.")
        return {"status": "error", "message": "No actors selected.", "total": 0}

    results = []
    for actor in actors:
        comp = _get_mesh_component(actor)
        results.append({
            "label": actor.get_actor_label(),
            "physics_capable": comp is not None,
        })

    capable     = [r for r in results if r["physics_capable"]]
    not_capable = [r for r in results if not r["physics_capable"]]

    log_info(f"[physics_list] {len(capable)} capable / {len(not_capable)} not capable / {len(results)} total")
    return {
        "status": "ok",
        "total": len(results),
        "capable": len(capable),
        "not_capable": len(not_capable),
        "actors": results,
        "note": "UEFN sandboxes physics state reads — current on/off state is visible in the Details panel only.",
    }
