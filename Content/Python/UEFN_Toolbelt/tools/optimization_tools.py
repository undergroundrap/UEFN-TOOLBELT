"""
UEFN TOOLBELT — Optimization Tools
========================================
Three targeted optimization tools that close the gap with competing launchers
while fitting cleanly into the Toolbelt architecture.

TOOLS:
  • rogue_actor_scan     — Find actors with common problems (extreme scale,
                           unnamed, at origin, bad transforms). Read-only audit.
  • convert_to_hism      — Merge selected StaticMeshActors that share the same
                           mesh into a single HISM actor (one draw call).
  • material_parent_audit — Report how material instances are distributed across
                            parent materials in a folder. Flags orphaned MIs.

USAGE:
    import UEFN_Toolbelt as tb

    # Scan entire level for rogue actors
    tb.run("rogue_actor_scan")

    # Preview what would be merged (dry run)
    tb.run("convert_to_hism", dry_run=True)

    # Actually merge selected StaticMeshActors into HISM
    tb.run("convert_to_hism", dry_run=False, folder="Optimized")

    # Audit MI parents in a folder
    tb.run("material_parent_audit", scan_path="/Game/Materials")
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Tuple

import unreal

from ..core import (
    get_selected_actors, log_info, log_warning, log_error,
    load_asset, save_asset, undo_transaction, with_progress,
)
from ..registry import register_tool


# ─────────────────────────────────────────────────────────────────────────────
#  rogue_actor_scan
# ─────────────────────────────────────────────────────────────────────────────

_ROGUE_CHECKS = {
    "extreme_scale":    "Scale component > 100 or < 0.01 (likely import error)",
    "negative_scale":   "One or more scale axes are negative (mirror artifact)",
    "at_origin":        "Actor is at exactly (0, 0, 0) — likely unplaced",
    "unnamed":          "Actor label matches its class name (never renamed)",
    "extreme_location": "Actor is > 500,000 cm from world origin (off-map)",
    "zero_scale":       "Scale component is 0 — actor is invisible",
}


def _check_actor(actor) -> List[str]:
    issues = []
    try:
        loc   = actor.get_actor_location()
        scale = actor.get_actor_scale3d()
        label = actor.get_actor_label()
        cn    = actor.get_class().get_name()

        sx, sy, sz = scale.x, scale.y, scale.z

        if any(s == 0.0 for s in (sx, sy, sz)):
            issues.append("zero_scale")
        if any(s < 0 for s in (sx, sy, sz)):
            issues.append("negative_scale")
        if any(abs(s) > 100 for s in (sx, sy, sz)):
            issues.append("extreme_scale")
        if loc.x == 0.0 and loc.y == 0.0 and loc.z == 0.0:
            issues.append("at_origin")
        if any(abs(v) > 500_000 for v in (loc.x, loc.y, loc.z)):
            issues.append("extreme_location")
        if label.replace(" ", "").lower() in cn.replace("_C", "").lower():
            issues.append("unnamed")
    except Exception:
        pass
    return issues


@register_tool(
    name="rogue_actor_scan",
    category="Optimization",
    description="Scan all level actors for common problems: extreme scale, at-origin placement, unnamed actors, off-map transforms.",
    tags=["audit", "optimization", "actors", "scan", "health", "rogue"],
)
def run_rogue_actor_scan(
    scope: str = "level",
    **kwargs,
) -> dict:
    """
    Scan actors for problems that hurt performance or indicate mistakes.

    Args:
        scope: "level" scans all actors. "selection" scans selected only.

    Returns:
        dict with per-issue counts and a list of offending actors.
    """
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if scope == "selection":
            actors = get_selected_actors()
        else:
            actors = actor_sub.get_all_level_actors()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

    rogues: List[Dict] = []
    issue_counts: Dict[str, int] = {k: 0 for k in _ROGUE_CHECKS}

    for actor in actors:
        issues = _check_actor(actor)
        if issues:
            try:
                label = actor.get_actor_label()
                cn    = actor.get_class().get_name()
            except Exception:
                label, cn = "?", "?"
            rogues.append({
                "label":  label,
                "class":  cn,
                "issues": issues,
                "descriptions": [_ROGUE_CHECKS[i] for i in issues],
            })
            for iss in issues:
                issue_counts[iss] = issue_counts.get(iss, 0) + 1

    total = len(rogues)
    if total:
        log_warning(f"rogue_actor_scan: {total} actor(s) with issues found.")
        for name, count in issue_counts.items():
            if count:
                log_info(f"  {name}: {count}")
        for r in rogues[:20]:   # cap log output
            log_info(f"  [{r['label']}] → {', '.join(r['issues'])}")
        if total > 20:
            log_info(f"  … and {total - 20} more.")
    else:
        log_info("rogue_actor_scan: no issues found — level looks clean.")

    return {
        "status":       "ok",
        "total_scanned": len(list(actors)) if hasattr(actors, "__len__") else "?",
        "rogue_count":  total,
        "issue_counts": issue_counts,
        "rogues":       rogues,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  convert_to_hism
# ─────────────────────────────────────────────────────────────────────────────

def _get_static_mesh_from_actor(actor) -> object:
    """Return the StaticMesh asset from a StaticMeshActor, or None."""
    try:
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        if comp:
            return comp.get_static_mesh()
    except Exception:
        pass
    return None


@register_tool(
    name="convert_to_hism",
    category="Optimization",
    description="Merge selected StaticMeshActors that share the same mesh into a single HISM actor (one draw call). dry_run=True previews without changes.",
    tags=["hism", "optimization", "instanced", "merge", "draw-call", "performance"],
)
def run_convert_to_hism(
    dry_run: bool = True,
    min_count: int = 2,
    folder: str = "Optimized",
    **kwargs,
) -> dict:
    """
    Find selected StaticMeshActors that share the same mesh and merge each
    group into one HierarchicalInstancedStaticMeshComponent actor.

    Args:
        dry_run:   True (default) = report only, no changes.
        min_count: Only merge groups with at least this many actors (default 2).
        folder:    World Outliner folder for the new HISM actors.

    Returns:
        dict with groups found and actors merged.
    """
    actors = get_selected_actors()
    if not actors:
        return {"status": "error", "message": "No actors selected."}

    # Group StaticMeshActors by their mesh asset path
    groups: Dict[str, Dict] = {}
    skipped = 0
    for actor in actors:
        if not isinstance(actor, unreal.StaticMeshActor):
            skipped += 1
            continue
        mesh = _get_static_mesh_from_actor(actor)
        if mesh is None:
            skipped += 1
            continue
        mesh_path = mesh.get_path_name()
        if mesh_path not in groups:
            groups[mesh_path] = {"mesh": mesh, "mesh_name": mesh_path.split("/")[-1], "actors": []}
        groups[mesh_path]["actors"].append(actor)

    # Only keep groups meeting the minimum count
    mergeable = {k: v for k, v in groups.items() if len(v["actors"]) >= min_count}

    if not mergeable:
        msg = (
            f"No mergeable groups found (need {min_count}+ actors sharing a mesh). "
            f"Skipped {skipped} non-StaticMeshActors."
        )
        log_info(f"convert_to_hism: {msg}")
        return {"status": "ok", "message": msg, "groups_found": 0, "merged": 0}

    # Report
    total_actors = sum(len(g["actors"]) for g in mergeable.values())
    log_info(f"convert_to_hism: {len(mergeable)} group(s), {total_actors} actor(s) → {len(mergeable)} HISM actor(s)")
    for mp, g in mergeable.items():
        log_info(f"  {g['mesh_name']}: {len(g['actors'])} actors")

    if dry_run:
        log_info("convert_to_hism: DRY RUN — no changes made. Set dry_run=False to execute.")
        return {
            "status":       "ok",
            "dry_run":      True,
            "groups_found": len(mergeable),
            "total_actors": total_actors,
            "groups":       [{"mesh": g["mesh_name"], "count": len(g["actors"])} for g in mergeable.values()],
        }

    # Execute merge
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    merged_actors = 0
    hism_actors_created = 0

    with undo_transaction(f"Convert to HISM: {len(mergeable)} group(s)"):
        for mesh_path, g in mergeable.items():
            mesh   = g["mesh"]
            actors_in_group = g["actors"]

            # Use first actor's location as host origin
            first_loc = actors_in_group[0].get_actor_location()

            # Spawn a plain Actor to host the HISM component
            host = actor_sub.spawn_actor_from_class(
                unreal.Actor,
                first_loc,
                unreal.Rotator(0, 0, 0),
            )
            if host is None:
                log_error(f"convert_to_hism: failed to spawn host for {g['mesh_name']}")
                continue

            label = f"HISM_{g['mesh_name'].replace('.', '_')}"
            host.set_actor_label(label)
            try:
                host.set_folder_path(unreal.Name(folder))
            except Exception:
                pass

            # Attach HISM component
            hism = unreal.HierarchicalInstancedStaticMeshComponent(host)
            hism.set_static_mesh(mesh)

            # Add one instance per original actor
            for src in actors_in_group:
                try:
                    t = unreal.Transform(
                        location=src.get_actor_location(),
                        rotation=src.get_actor_rotation(),
                        scale=src.get_actor_scale3d(),
                    )
                    hism.add_instance(t)
                    merged_actors += 1
                except Exception as exc:
                    log_warning(f"convert_to_hism: skipped instance — {exc}")

            # Delete the originals
            for src in actors_in_group:
                try:
                    actor_sub.destroy_actor(src)
                except Exception:
                    pass

            hism_actors_created += 1
            log_info(f"  ✓ {label}: {len(actors_in_group)} actors → 1 HISM")

    log_info(f"convert_to_hism: done — {merged_actors} actors merged into {hism_actors_created} HISM actor(s).")
    return {
        "status":             "ok",
        "dry_run":            False,
        "groups_merged":      hism_actors_created,
        "actors_merged":      merged_actors,
        "draw_calls_saved":   merged_actors - hism_actors_created,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  material_parent_audit
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="material_parent_audit",
    category="Optimization",
    description="Audit material instances in a folder — group by parent, flag orphaned MIs with no valid parent, report consolidation opportunities.",
    tags=["material", "optimization", "audit", "instances", "parent", "consolidate"],
)
def run_material_parent_audit(
    scan_path: str = "/Game",
    **kwargs,
) -> dict:
    """
    Scan a Content Browser folder for MaterialInstanceConstant assets.
    Groups them by parent material and reports consolidation opportunities
    (many MIs pointing to different parents that could share one).

    Args:
        scan_path: Content Browser path to scan (default "/Game").

    Returns:
        dict with parent groups, orphan count, and consolidation suggestions.
    """
    try:
        asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()
        filter_obj = unreal.ARFilter(
            class_names=["MaterialInstanceConstant"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = asset_reg.get_assets(filter_obj)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

    if not assets:
        return {"status": "ok", "message": f"No material instances found in {scan_path}.", "total": 0}

    mel = unreal.MaterialEditingLibrary
    parent_groups: Dict[str, List[str]] = {}
    orphans: List[str] = []

    for asset_data in assets:
        try:
            mi = asset_data.get_asset()
            if not isinstance(mi, unreal.MaterialInstanceConstant):
                continue
            mi_path = mi.get_path_name()
            parent  = mi.parent
            if parent is None:
                orphans.append(mi_path)
                continue
            parent_path = parent.get_path_name()
            if parent_path not in parent_groups:
                parent_groups[parent_path] = []
            parent_groups[parent_path].append(mi_path)
        except Exception:
            continue

    total_mis   = sum(len(v) for v in parent_groups.values()) + len(orphans)
    total_parents = len(parent_groups)

    # Consolidation suggestion: parents used by only 1 MI are candidates for merging
    single_use = [p for p, mis in parent_groups.items() if len(mis) == 1]
    multi_use  = {p: mis for p, mis in parent_groups.items() if len(mis) > 1}

    log_info(f"material_parent_audit: {total_mis} MIs across {total_parents} parent(s) in {scan_path}")
    if orphans:
        log_warning(f"  Orphans (no parent): {len(orphans)}")
        for o in orphans[:5]:
            log_warning(f"    {o.split('/')[-1]}")
    log_info(f"  Parents with 1 MI (consolidation candidates): {len(single_use)}")
    log_info(f"  Parents with 2+ MIs (well shared): {len(multi_use)}")
    for parent, mis in sorted(multi_use.items(), key=lambda x: -len(x[1]))[:5]:
        log_info(f"    {parent.split('/')[-1]}: {len(mis)} MIs")

    return {
        "status":             "ok",
        "scan_path":          scan_path,
        "total_mis":          total_mis,
        "total_parents":      total_parents,
        "orphaned_mis":       len(orphans),
        "orphan_paths":       orphans,
        "single_use_parents": len(single_use),
        "multi_use_parents":  len(multi_use),
        "parent_groups": {
            p: {"mi_count": len(mis), "mis": mis}
            for p, mis in sorted(parent_groups.items(), key=lambda x: -len(x[1]))
        },
    }
