"""
UEFN TOOLBELT — PCG (Procedural Content Generation) Tools
========================================
Control PCG graphs from Python — trigger generation, change seeds,
inspect output, and refresh all graphs in the level.

PCG in UEFN works via PCGComponent attached to actors. You place a
PCG Graph asset on an actor in the editor, then Python can:
  • List all PCG-enabled actors and their graph assets
  • Force-regenerate graphs (same as clicking "Generate" in the panel)
  • Change the random seed for variation
  • Refresh all graphs at once (great after batch property changes)

PCG data types (readable): PCGPointData, PCGSurfaceData, PCGVolumeData,
PCGSplineData, PCGLandscapeData — output inspection only.

API reference: unreal.PCGComponent, unreal.PCGSubsystem
"""

from __future__ import annotations

import unreal

from ..core import log_error, log_info, log_warning
from ..registry import register_tool

# unreal.* names this module uses but does not require.
# Absent in UEFN 42.00 (UE 6.0). Probed with hasattr before use.
__optional_unreal_apis__ = (
    "PCGSubsystem",
)


def _get_pcg_component(actor: unreal.Actor):
    """Return the first PCGComponent on an actor, or None."""
    try:
        comps = actor.get_components_by_class(unreal.PCGComponent)
        return comps[0] if comps else None
    except Exception:
        return None


def _all_pcg_actors():
    """Return all level actors that have a PCGComponent."""
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    results = []
    for actor in actor_sub.get_all_level_actors():
        comp = _get_pcg_component(actor)
        if comp:
            results.append((actor, comp))
    return results


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="pcg_list_graphs",
    category="Procedural",
    description=(
        "List all actors in the level that have a PCG Component — "
        "shows actor label, PCG graph asset name, seed, and generation state."
    ),
    tags=["pcg", "procedural", "list", "audit", "graph"],
)
def run_pcg_list_graphs(**kwargs) -> dict:
    """Audit all PCG-enabled actors in the current level."""
    try:
        pairs = _all_pcg_actors()
        results = []
        for actor, comp in pairs:
            try:
                graph = comp.get_graph()
                graph_name = graph.get_name() if graph else "None"
                loc = actor.get_actor_location()
                results.append({
                    "label":      actor.get_actor_label(),
                    "graph":      graph_name,
                    "folder":     str(actor.get_folder_path()),
                    "location":   [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
                })
            except Exception as e:
                results.append({"label": actor.get_actor_label(), "error": str(e)})

        log_info(f"pcg_list_graphs: found {len(results)} PCG actor(s).")
        return {"status": "ok", "count": len(results), "graphs": results}
    except Exception as e:
        log_error(f"pcg_list_graphs failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="pcg_execute_graph",
    category="Procedural",
    description=(
        "Force-regenerate the PCG graph on selected actors (or all PCG actors if nothing selected). "
        "Equivalent to clicking 'Generate' in the PCG Component panel."
    ),
    tags=["pcg", "procedural", "generate", "execute", "refresh"],
)
def run_pcg_execute_graph(
    scope: str = "selection",
    force: bool = True,
    **kwargs,
) -> dict:
    """
    Trigger PCG graph generation.

    Args:
        scope: "selection" (default) or "all" — which actors to target
        force: If True, regenerates even if the graph is already up to date (default True)
    """
    try:
        if scope == "all":
            pairs = _all_pcg_actors()
        else:
            actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            selected = list(actor_sub.get_selected_level_actors())
            if not selected:
                return {"status": "error", "error": "No actors selected. Select PCG actors or use scope='all'."}
            pairs = [(a, _get_pcg_component(a)) for a in selected]
            pairs = [(a, c) for a, c in pairs if c is not None]

        if not pairs:
            return {"status": "error", "error": "No PCG components found on target actors."}

        executed = 0
        skipped = 0
        for actor, comp in pairs:
            try:
                comp.generate(force)
                executed += 1
                log_info(f"  PCG generate: {actor.get_actor_label()}")
            except Exception as e:
                log_warning(f"  PCG generate failed on {actor.get_actor_label()}: {e}")
                skipped += 1

        return {
            "status": "ok",
            "scope": scope,
            "executed": executed,
            "skipped": skipped,
        }
    except Exception as e:
        log_error(f"pcg_execute_graph failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="pcg_set_seed",
    category="Procedural",
    description=(
        "Change the random seed on selected PCG actors. "
        "Each unique seed produces a different procedural output — great for variation."
    ),
    tags=["pcg", "procedural", "seed", "random", "variation"],
)
def run_pcg_set_seed(
    seed: int = 42,
    regenerate: bool = True,
    **kwargs,
) -> dict:
    """
    Set a new random seed on selected actors' PCG components.

    Args:
        seed:        New integer seed value (default 42)
        regenerate:  If True, immediately regenerates after changing seed (default True)
    """
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        selected = list(actor_sub.get_selected_level_actors())
        if not selected:
            return {"status": "error", "error": "No actors selected."}

        updated = 0
        skipped = 0
        for actor in selected:
            comp = _get_pcg_component(actor)
            if comp is None:
                skipped += 1
                continue
            try:
                comp.set_editor_property("seed", seed)
                if regenerate:
                    comp.generate(True)
                updated += 1
            except Exception as e:
                log_warning(f"  seed set failed on {actor.get_actor_label()}: {e}")
                skipped += 1

        return {
            "status": "ok",
            "seed": seed,
            "updated": updated,
            "skipped": skipped,
            "regenerated": regenerate,
        }
    except Exception as e:
        log_error(f"pcg_set_seed failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="pcg_refresh_all",
    category="Procedural",
    description=(
        "Refresh (regenerate) every PCG graph in the current level. "
        "Use after bulk property changes to bring all procedural output up to date."
    ),
    tags=["pcg", "procedural", "refresh", "regenerate", "all"],
)
def run_pcg_refresh_all(**kwargs) -> dict:
    """Force-regenerate all PCG components in the level."""
    try:
        # Try via PCGSubsystem first (cleanest API)
        try:
            _world = unreal.EditorLevelLibrary.get_editor_world()
            pcg_sub = unreal.get_engine_subsystem(unreal.PCGSubsystem) if hasattr(unreal, "PCGSubsystem") else None
            if pcg_sub:
                pcg_sub.refresh_runtime_dirty_components()
                log_info("pcg_refresh_all: refreshed via PCGSubsystem.")
                return {"status": "ok", "method": "PCGSubsystem", "message": "All dirty PCG components refreshed."}
        except Exception:
            pass

        # Fallback: iterate all PCG actors manually
        pairs = _all_pcg_actors()
        if not pairs:
            return {"status": "ok", "count": 0, "message": "No PCG actors found in level."}

        for actor, comp in pairs:
            try:
                comp.generate(True)
            except Exception as e:
                log_warning(f"  refresh failed on {actor.get_actor_label()}: {e}")

        log_info(f"pcg_refresh_all: regenerated {len(pairs)} PCG actor(s).")
        return {"status": "ok", "method": "manual", "count": len(pairs)}
    except Exception as e:
        log_error(f"pcg_refresh_all failed: {e}")
        return {"status": "error", "error": str(e)}
