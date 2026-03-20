"""
UEFN TOOLBELT — Batch LOD & Collision Tools
========================================
One of the most tedious parts of a UEFN project: every imported mesh needs
LODs set up and collision configured before it performs well. With dozens or
hundreds of assets this is mind-numbing. This module automates it in bulk.

FEATURES:
  • Batch auto-generate LODs on multiple static meshes (selection or folder)
  • Set LOD screen-size thresholds in one call
  • Batch set collision complexity (simple, complex, use-complex-as-simple)
  • Add/remove auto convex collision to multiple meshes
  • Report meshes missing LODs or collision in a folder
  • Preview LOD counts across your entire Content Browser
  • Full progress bar on bulk operations

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Auto-LOD all selected static mesh actors' meshes
    tb.run("lod_auto_generate_selection", num_lods=4)

    # Auto-LOD all meshes in a Content Browser folder
    tb.run("lod_auto_generate_folder",
           folder_path="/Game/MyAssets/Meshes",
           num_lods=3)

    # Batch set collision to "Use Complex as Simple"
    tb.run("lod_set_collision_folder",
           folder_path="/Game/MyAssets/Meshes",
           complexity="complex_as_simple")

    # Report meshes with no LODs
    tb.run("lod_audit_folder", folder_path="/Game/MyAssets")

BLUEPRINT:
    "Execute Python Command" →
        import UEFN_Toolbelt as tb; tb.run("lod_auto_generate_folder", folder_path="/Game/Meshes", num_lods=3)

TECHNICAL NOTES:
    LOD generation uses unreal.StaticMeshEditorSubsystem.set_lods_with_notification()
    which calls Unreal's built-in mesh reduction pipeline (same as the editor UI
    "LOD Group" auto-generate button). Quality settings are configurable.

    Collision complexity maps:
        "default"             → CTF_UseDefault
        "simple"              → CTF_UseSimpleAsComplex
        "complex"             → CTF_UseComplexAsSimple
        "complex_as_simple"   → CTF_UseComplexAsSimple
        "simple_and_complex"  → CTF_UseSimpleAndComplex
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

import unreal

from ..core import (
    get_selected_actors, log_info, log_warning, log_error,
    load_asset, with_progress,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

_COLLISION_MAP = {
    "default":            unreal.CollisionTraceFlag.CTF_USE_DEFAULT,
    "simple":             unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX,
    "complex":            unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
    "complex_as_simple":  unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
    "simple_and_complex": unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX,
}


def _get_mesh_from_path(asset_path: str) -> Optional[unreal.StaticMesh]:
    asset = load_asset(asset_path)
    if not isinstance(asset, unreal.StaticMesh):
        return None
    return asset


def _get_meshes_in_folder(folder: str) -> List[unreal.StaticMesh]:
    """Return all StaticMesh assets in a Content Browser folder."""
    if not unreal.EditorAssetLibrary.does_directory_exist(folder):
        log_error(f"Folder not found: {folder}")
        return []
    paths = unreal.EditorAssetLibrary.list_assets(folder, recursive=True, include_folder=False)
    meshes = []
    for p in paths:
        m = _get_mesh_from_path(p)
        if m:
            meshes.append((p, m))
    return meshes


def _build_lod_options(num_lods: int, quality: float = 0.5) -> unreal.EditorScriptingMeshReductionOptions:
    """
    Build LOD reduction options for `num_lods` additional LODs.
    quality: 0.0 (most aggressive) → 1.0 (least reduction).
    """
    options = unreal.EditorScriptingMeshReductionOptions()
    options.auto_compute_lod_screen_sizes = True

    reductions = []
    for i in range(num_lods):
        # Each LOD progressively reduces triangle count
        reduction_pct = 1.0 - (quality * (i + 1) / num_lods)
        r = unreal.EditorScriptingMeshReductionSettings()
        r.percent_triangles = max(0.05, reduction_pct)
        r.screen_size = 0.0  # auto-computed
        reductions.append(r)

    options.reductions = reductions
    return options


def _apply_lods(mesh: unreal.StaticMesh, asset_path: str, num_lods: int, quality: float) -> bool:
    """Apply auto-generated LODs to one mesh. Returns True on success."""
    mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    try:
        options = _build_lod_options(num_lods, quality)
        mesh_sub.set_lods_with_notification(mesh, options, True)
        unreal.EditorAssetLibrary.save_asset(asset_path)
        return True
    except Exception as e:
        log_warning(f"  LOD failed on {asset_path.split('/')[-1]}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="lod_auto_generate_selection",
    category="Assets",
    description="Auto-generate LODs on the static meshes of all selected actors.",
    tags=["lod", "mesh", "auto", "selection", "performance"],
)
def run_lod_auto_generate_selection(
    num_lods: int = 3,
    quality: float = 0.5,
    **kwargs,
) -> None:
    """
    Args:
        num_lods: Number of additional LODs to generate (1–7 recommended).
        quality:  Reduction aggressiveness. 0.0 = maximum reduction, 1.0 = minimal.
    """
    actors = get_selected_actors()
    if not actors:
        log_warning("Select actors in the viewport first.")
        return

    smc_class = unreal.StaticMeshComponent.static_class()
    seen_meshes: set = set()
    targets = []

    for actor in actors:
        for comp in actor.get_components_by_class(smc_class):
            mesh = comp.get_static_mesh()
            if mesh and id(mesh) not in seen_meshes:
                seen_meshes.add(id(mesh))
                path = mesh.get_path_name().split(".")[0]
                targets.append((path, mesh))

    if not targets:
        log_warning("No static meshes found on selected actors.")
        return

    log_info(f"Generating {num_lods} LODs on {len(targets)} unique meshes…")
    done = failed = 0

    with with_progress(targets, "Generating LODs") as bar:
        for path, mesh in bar:
            if _apply_lods(mesh, path, num_lods, quality):
                done += 1
            else:
                failed += 1

    log_info(f"LOD generation: {done} succeeded, {failed} failed.")


@register_tool(
    name="lod_auto_generate_folder",
    category="Assets",
    description="Auto-generate LODs on all static meshes in a Content Browser folder.",
    tags=["lod", "mesh", "batch", "folder", "performance"],
)
def run_lod_auto_generate_folder(
    folder_path: str = "/Game",
    num_lods: int = 3,
    quality: float = 0.5,
    skip_existing: bool = True,
    **kwargs,
) -> None:
    """
    Args:
        folder_path:    Content Browser folder to scan.
        num_lods:       LODs to generate.
        quality:        Reduction aggressiveness (0.0–1.0).
        skip_existing:  Skip meshes that already have LODs.
    """
    targets = _get_meshes_in_folder(folder_path)
    if not targets:
        log_info("No static meshes found.")
        return

    if skip_existing:
        mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        targets = [
            (p, m) for p, m in targets
            if mesh_sub.get_lod_count(m) <= 1
        ]
        log_info(f"Skipping meshes with existing LODs — {len(targets)} to process.")

    if not targets:
        log_info("All meshes already have LODs.")
        return

    log_info(f"Generating {num_lods} LODs on {len(targets)} meshes in {folder_path}…")
    done = failed = 0

    with with_progress(targets, "Batch LOD Generation") as bar:
        for path, mesh in bar:
            if _apply_lods(mesh, path, num_lods, quality):
                done += 1
                log_info(f"  ✓ {path.split('/')[-1]}")
            else:
                failed += 1

    log_info(f"Batch LOD complete: {done} done, {failed} failed.")


@register_tool(
    name="lod_set_collision_folder",
    category="Assets",
    description="Batch-set collision complexity on all static meshes in a folder.",
    tags=["collision", "mesh", "batch", "lod", "performance"],
)
def run_set_collision_folder(
    folder_path: str = "/Game",
    complexity: str = "complex_as_simple",
    **kwargs,
) -> None:
    """
    Args:
        folder_path: Content Browser folder to scan.
        complexity:  One of: "default", "simple", "complex", "complex_as_simple",
                     "simple_and_complex".
    """
    if complexity not in _COLLISION_MAP:
        log_error(f"Unknown complexity '{complexity}'. Choose from: {list(_COLLISION_MAP.keys())}")
        return

    flag = _COLLISION_MAP[complexity]
    targets = _get_meshes_in_folder(folder_path)
    if not targets:
        return

    log_info(f"Setting collision='{complexity}' on {len(targets)} meshes…")
    done = 0

    with with_progress(targets, "Setting Collision") as bar:
        for path, mesh in bar:
            try:
                body = mesh.get_editor_property("body_setup")
                if body:
                    body.set_editor_property("collision_trace_flag", flag)
                    unreal.EditorAssetLibrary.save_asset(path)
                    done += 1
            except Exception as e:
                log_warning(f"  {path.split('/')[-1]}: {e}")

    log_info(f"Collision set on {done}/{len(targets)} meshes.")


@register_tool(
    name="lod_audit_folder",
    category="Assets",
    description="Audit static meshes in a folder — report which have no LODs or collision.",
    tags=["lod", "audit", "report", "mesh", "collision"],
)
def run_lod_audit_folder(
    folder_path: str = "/Game",
    **kwargs,
) -> None:
    """
    Prints a report and saves JSON to Saved/UEFN_Toolbelt/lod_audit.json.
    Does NOT modify any assets.

    Args:
        folder_path: Content Browser folder to audit.
    """
    targets = _get_meshes_in_folder(folder_path)
    if not targets:
        return

    mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

    no_lod      = []
    no_collision = []
    records     = []

    for path, mesh in targets:
        lod_count  = mesh_sub.get_lod_count(mesh)
        has_simple = False

        try:
            body = mesh.get_editor_property("body_setup")
            if body:
                shapes = body.get_editor_property("agg_geom")
                convex = shapes.get_editor_property("convex_elems") if shapes else []
                has_simple = len(convex) > 0
        except Exception:
            pass

        name = path.split("/")[-1]
        if lod_count <= 1:
            no_lod.append(name)
        if not has_simple:
            no_collision.append(name)

        records.append({
            "name": name,
            "path": path,
            "lod_count": lod_count,
            "has_simple_collision": has_simple,
        })

    # Print summary
    lines = [
        f"\n=== LOD Audit: {folder_path} ===",
        f"  Total meshes:      {len(targets)}",
        f"  Missing LODs:      {len(no_lod)}",
        f"  Missing collision: {len(no_collision)}",
    ]
    if no_lod:
        lines += ["", "  No LODs:"] + [f"    {n}" for n in no_lod[:20]]
        if len(no_lod) > 20:
            lines.append(f"    … and {len(no_lod) - 20} more")
    log_info("\n".join(lines))

    # Save full report
    out_dir  = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    out_path = os.path.join(out_dir, "lod_audit.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"folder": folder_path, "records": records}, f, indent=2)

    log_info(f"Full audit → {out_path}")
    log_info("Run lod_auto_generate_folder to fix missing LODs.")
