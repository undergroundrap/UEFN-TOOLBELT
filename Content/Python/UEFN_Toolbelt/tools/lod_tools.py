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
    """
    Apply auto-generated LODs to one mesh. Returns True on success.

    NOTE: set_lods_with_notification calls into the mesh reduction C++ pipeline
    (Simplygon / built-in reducer). In UEFN's sandboxed Python environment this
    plugin is not loaded — calling it causes an EXCEPTION_ACCESS_VIOLATION crash
    at address 0x0 that Python cannot catch. This function is therefore disabled
    in UEFN. Use lod_audit_folder to identify meshes that need LODs, then add
    them manually via the Static Mesh Editor.
    """
    log_error(
        "[LOD Tools] Auto-LOD generation is not available in UEFN's Python environment.\n"
        "  The mesh reduction plugin (Simplygon / built-in reducer) is not loaded in UEFN,\n"
        "  and calling it causes an engine crash (C++ null-pointer in reduction pipeline).\n"
        "  Use lod_audit_folder to find meshes missing LODs, then add LODs manually\n"
        "  in the Static Mesh Editor (double-click mesh → LODs tab → Auto Generate)."
    )
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
) -> dict:
    """
    Args:
        num_lods: Number of additional LODs to generate (1–7 recommended).
        quality:  Reduction aggressiveness. 0.0 = maximum reduction, 1.0 = minimal.

    Returns:
        dict: {"status", "done", "failed"}
    """
    actors = get_selected_actors()
    if not actors:
        log_warning("Select actors in the viewport first.")
        return {"status": "error", "done": 0, "failed": 0}

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
        return {"status": "error", "done": 0, "failed": 0}

    log_info(f"Generating {num_lods} LODs on {len(targets)} unique meshes…")
    done = failed = 0

    with with_progress(targets, "Generating LODs") as bar:
        for path, mesh in bar:
            if _apply_lods(mesh, path, num_lods, quality):
                done += 1
            else:
                failed += 1

    log_info(f"LOD generation: {done} succeeded, {failed} failed.")
    return {"status": "ok", "done": done, "failed": failed}


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
) -> dict:
    """
    Args:
        folder_path:    Content Browser folder to scan.
        num_lods:       LODs to generate.
        quality:        Reduction aggressiveness (0.0–1.0).
        skip_existing:  Skip meshes that already have LODs.

    Returns:
        dict: {"status", "done", "failed"}
    """
    targets = _get_meshes_in_folder(folder_path)
    if not targets:
        log_info("No static meshes found.")
        return {"status": "ok", "done": 0, "failed": 0}

    if skip_existing:
        mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if mesh_sub is None:
            log_error("StaticMeshEditorSubsystem unavailable — cannot check existing LODs. Proceeding without skip.")
        else:
            targets = [(p, m) for p, m in targets if mesh_sub.get_lod_count(m) <= 1]
            log_info(f"Skipping meshes with existing LODs — {len(targets)} to process.")

    if not targets:
        log_info("All meshes already have LODs.")
        return {"status": "ok", "done": 0, "failed": 0}

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
    return {"status": "ok", "done": done, "failed": failed}


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
) -> dict:
    """
    Args:
        folder_path: Content Browser folder to scan.
        complexity:  One of: "default", "simple", "complex", "complex_as_simple",
                     "simple_and_complex".

    Returns:
        dict: {"status", "done", "total"}
    """
    if complexity not in _COLLISION_MAP:
        log_error(f"Unknown complexity '{complexity}'. Choose from: {list(_COLLISION_MAP.keys())}")
        return {"status": "error", "done": 0, "total": 0}

    flag = _COLLISION_MAP[complexity]
    targets = _get_meshes_in_folder(folder_path)
    if not targets:
        return {"status": "ok", "done": 0, "total": 0}

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
    return {"status": "ok", "done": done, "total": len(targets)}


@register_tool(
    name="lod_audit_folder",
    category="Assets",
    description="Audit static meshes in a folder — report which have no LODs or collision.",
    tags=["lod", "audit", "report", "mesh", "collision"],
)
def run_lod_audit_folder(
    folder_path: str = "/Game",
    **kwargs,
) -> dict:
    """
    Prints a report and saves JSON to Saved/UEFN_Toolbelt/lod_audit.json.
    Does NOT modify any assets.

    Args:
        folder_path: Content Browser folder to audit.

    Returns:
        dict: {"status", "path", "no_lod_count", "no_collision_count", "records"}
    """
    targets = _get_meshes_in_folder(folder_path)
    if not targets:
        return {"status": "ok", "path": "", "no_lod_count": 0, "no_collision_count": 0, "records": []}

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
    return {
        "status": "ok",
        "path": out_path,
        "no_lod_count": len(no_lod),
        "no_collision_count": len(no_collision),
        "records": records,
    }


# ── Nanite Tools ───────────────────────────────────────────────────────────────

@register_tool(
    name="nanite_audit",
    category="Static Meshes",
    description=(
        "Audit all StaticMesh assets in a folder for Nanite status. "
        "Returns meshes with Nanite enabled vs disabled and vertex counts. "
        "Use this to decide which high-poly meshes benefit most from Nanite."
    ),
    tags=["nanite", "mesh", "audit", "lod", "performance"],
    example='tb.run("nanite_audit", scan_path="/Game/Meshes")',
)
def run_nanite_audit(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    # Uses AR tag data only — never calls load_asset(), safe on pak-heavy projects.
    try:
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        filt = unreal.ARFilter(
            class_names=["StaticMesh"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = ar.get_assets(filt)[:max_results]
        enabled = []
        disabled = []
        for a in assets:
            name = str(a.asset_name)
            path = str(a.package_name)
            # NaniteSettings.Enabled is cached as an AR tag in UE5
            nanite_tag = a.get_tag_value("NaniteEnabled") or a.get_tag_value("bNaniteEnabled") or ""
            is_enabled = nanite_tag.lower() in ("true", "1", "yes")
            entry = {"name": name, "path": path}
            (enabled if is_enabled else disabled).append(entry)

        log_info(f"[nanite_audit] {len(enabled)} enabled, {len(disabled)} disabled in {scan_path}")
        return {
            "status": "ok",
            "total": len(enabled) + len(disabled),
            "nanite_enabled": len(enabled),
            "nanite_disabled": len(disabled),
            "enabled": enabled,
            "disabled": disabled,
            "tip": "Nanite tag may not be cached in AR — use nanite_enable_folder dry_run=True to check per-mesh.",
        }
    except Exception as e:
        log_error(f"[nanite_audit] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="nanite_enable_folder",
    category="Static Meshes",
    description=(
        "Enable or disable Nanite on all StaticMesh assets in a Content Browser folder. "
        "Nanite works best for high-polygon hero assets. Skip low-poly or tiling meshes. "
        "Always dry_run=True first to preview which meshes will be affected."
    ),
    tags=["nanite", "mesh", "enable", "batch", "lod"],
    example='tb.run("nanite_enable_folder", scan_path="/Game/Meshes/Props", enable=True, dry_run=False)',
)
def run_nanite_enable_folder(
    scan_path: str = "/Game/",
    enable: bool = True,
    dry_run: bool = True,
    **kwargs,
) -> dict:
    try:
        mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if mesh_sub is None:
            return {"status": "error", "message": "StaticMeshEditorSubsystem not available."}

        meshes = _get_meshes_in_folder(scan_path)
        changed = []
        skipped = []

        for asset_path in meshes:
            mesh = _get_mesh_from_path(asset_path)
            if mesh is None:
                continue
            try:
                nanite_settings = mesh.get_editor_property("nanite_settings")
                current = nanite_settings.get_editor_property("enabled") if nanite_settings else False
                if current == enable:
                    skipped.append(mesh.get_name())
                    continue
                if not dry_run:
                    mesh_sub.enable_nanite(mesh, enable)
                    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
                changed.append(mesh.get_name())
            except Exception as ex:
                log_warning(f"[nanite_enable_folder] {asset_path}: {ex}")

        action = "Would set" if dry_run else "Set"
        state = "enabled" if enable else "disabled"
        log_info(f"[nanite_enable_folder] {action} Nanite {state} on {len(changed)} meshes")
        return {
            "status": "ok",
            "dry_run": dry_run,
            "nanite_enabled": enable,
            "changed": len(changed),
            "skipped": len(skipped),
            "meshes": changed,
        }
    except Exception as e:
        log_error(f"[nanite_enable_folder] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="nanite_enable_selection",
    category="Static Meshes",
    description=(
        "Enable or disable Nanite on the StaticMesh assets used by all selected level actors. "
        "Select actors in the viewport, then call this tool. "
        "Saves each modified mesh asset immediately."
    ),
    tags=["nanite", "mesh", "enable", "selection"],
    example='tb.run("nanite_enable_selection", enable=True)',
)
def run_nanite_enable_selection(enable: bool = True, dry_run: bool = False, **kwargs) -> dict:
    try:
        mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if mesh_sub is None:
            return {"status": "error", "message": "StaticMeshEditorSubsystem not available."}

        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
        if not actors:
            return {"status": "error", "message": "No actors selected. Select actors in the viewport first."}

        smc_class = unreal.StaticMeshComponent.static_class()
        changed = []
        seen = set()
        for actor in actors:
            for comp in actor.get_components_by_class(smc_class):
                mesh = comp.get_editor_property("static_mesh")
                if mesh is None or mesh.get_path_name() in seen:
                    continue
                seen.add(mesh.get_path_name())
                try:
                    if not dry_run:
                        mesh_sub.enable_nanite(mesh, enable)
                        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
                    changed.append(mesh.get_name())
                except Exception as ex:
                    log_warning(f"[nanite_enable_selection] {mesh.get_name()}: {ex}")

        action = "Would set" if dry_run else "Set"
        state = "enabled" if enable else "disabled"
        log_info(f"[nanite_enable_selection] {action} Nanite {state} on {len(changed)} meshes")
        return {"status": "ok", "dry_run": dry_run, "nanite_enabled": enable, "changed": len(changed), "meshes": changed}
    except Exception as e:
        log_error(f"[nanite_enable_selection] {e}")
        return {"status": "error", "message": str(e)}


# ── UV Channel Tools ───────────────────────────────────────────────────────────

@register_tool(
    name="uv_list_channels",
    category="Static Meshes",
    description=(
        "List all UV channels on the StaticMesh assets used by selected actors. "
        "Returns UV channel count per mesh. "
        "Channel 0 is typically diffuse UV. Channel 1 is the lightmap UV."
    ),
    tags=["uv", "channels", "mesh", "list", "lightmap"],
    example='tb.run("uv_list_channels")',
)
def run_uv_list_channels(**kwargs) -> dict:
    try:
        mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
        if not actors:
            return {"status": "error", "message": "No actors selected."}

        smc_class = unreal.StaticMeshComponent.static_class()
        results = []
        seen = set()
        for actor in actors:
            for comp in actor.get_components_by_class(smc_class):
                mesh = comp.get_editor_property("static_mesh")
                if mesh is None or mesh.get_path_name() in seen:
                    continue
                seen.add(mesh.get_path_name())
                try:
                    num_uvs = mesh_sub.get_num_uv_channels(mesh, 0) if mesh_sub else None
                    results.append({"name": mesh.get_name(), "uv_channels": num_uvs})
                except Exception as ex:
                    results.append({"name": mesh.get_name(), "uv_channels": None, "error": str(ex)})

        return {"status": "ok", "count": len(results), "meshes": results}
    except Exception as e:
        log_error(f"[uv_list_channels] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="uv_generate_planar",
    category="Static Meshes",
    description=(
        "Generate planar UVs on a UV channel for the selected actors' StaticMesh assets. "
        "Planar projection is best for flat surfaces: floors, walls, decals. "
        "Saves modified mesh assets automatically."
    ),
    tags=["uv", "generate", "planar", "mesh", "channel"],
    example='tb.run("uv_generate_planar", channel=0, size=100.0)',
)
def run_uv_generate_planar(
    channel: int = 0,
    size: float = 100.0,
    dry_run: bool = False,
    **kwargs,
) -> dict:
    try:
        mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
        if not actors:
            return {"status": "error", "message": "No actors selected."}

        smc_class = unreal.StaticMeshComponent.static_class()
        changed = []
        seen = set()
        for actor in actors:
            for comp in actor.get_components_by_class(smc_class):
                mesh = comp.get_editor_property("static_mesh")
                if mesh is None or mesh.get_path_name() in seen:
                    continue
                seen.add(mesh.get_path_name())
                try:
                    if not dry_run and mesh_sub:
                        mesh_sub.generate_planar_uv_channel(
                            mesh, 0, channel,
                            unreal.Vector(0, 0, 0),
                            unreal.Rotator(0, 0, 0),
                            unreal.Vector2D(size, size),
                        )
                        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
                    changed.append(mesh.get_name())
                except Exception as ex:
                    log_warning(f"[uv_generate_planar] {mesh.get_name()}: {ex}")

        action = "Would generate" if dry_run else "Generated"
        log_info(f"[uv_generate_planar] {action} planar UV ch{channel} on {len(changed)} meshes")
        return {"status": "ok", "dry_run": dry_run, "channel": channel, "size": size, "changed": len(changed), "meshes": changed}
    except Exception as e:
        log_error(f"[uv_generate_planar] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="uv_generate_box",
    category="Static Meshes",
    description=(
        "Generate box (triplanar) UVs on a UV channel for the selected actors' StaticMesh assets. "
        "Box projection works well for blocky props, buildings, and any mesh without a natural unwrap. "
        "Saves modified mesh assets automatically."
    ),
    tags=["uv", "generate", "box", "triplanar", "mesh"],
    example='tb.run("uv_generate_box", channel=0, size=100.0)',
)
def run_uv_generate_box(
    channel: int = 0,
    size: float = 100.0,
    dry_run: bool = False,
    **kwargs,
) -> dict:
    try:
        mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
        if not actors:
            return {"status": "error", "message": "No actors selected."}

        smc_class = unreal.StaticMeshComponent.static_class()
        changed = []
        seen = set()
        for actor in actors:
            for comp in actor.get_components_by_class(smc_class):
                mesh = comp.get_editor_property("static_mesh")
                if mesh is None or mesh.get_path_name() in seen:
                    continue
                seen.add(mesh.get_path_name())
                try:
                    if not dry_run and mesh_sub:
                        mesh_sub.generate_box_uv_channel(
                            mesh, 0, channel,
                            unreal.Vector(0, 0, 0),
                            unreal.Rotator(0, 0, 0),
                            unreal.Vector(size, size, size),
                        )
                        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
                    changed.append(mesh.get_name())
                except Exception as ex:
                    log_warning(f"[uv_generate_box] {mesh.get_name()}: {ex}")

        action = "Would generate" if dry_run else "Generated"
        log_info(f"[uv_generate_box] {action} box UV ch{channel} on {len(changed)} meshes")
        return {"status": "ok", "dry_run": dry_run, "channel": channel, "size": size, "changed": len(changed), "meshes": changed}
    except Exception as e:
        log_error(f"[uv_generate_box] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="uv_add_channel",
    category="Static Meshes",
    description=(
        "Add a new empty UV channel to the selected actors' StaticMesh assets. "
        "Adds after the last existing channel. Useful before running "
        "geometry_generate_lightmap_uvs on meshes that only have channel 0."
    ),
    tags=["uv", "channel", "add", "mesh", "lightmap"],
    example='tb.run("uv_add_channel")',
)
def run_uv_add_channel(dry_run: bool = False, **kwargs) -> dict:
    try:
        mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
        if not actors:
            return {"status": "error", "message": "No actors selected."}

        smc_class = unreal.StaticMeshComponent.static_class()
        changed = []
        seen = set()
        for actor in actors:
            for comp in actor.get_components_by_class(smc_class):
                mesh = comp.get_editor_property("static_mesh")
                if mesh is None or mesh.get_path_name() in seen:
                    continue
                seen.add(mesh.get_path_name())
                try:
                    if not dry_run and mesh_sub:
                        mesh_sub.add_uv_channel(mesh, 0)
                        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
                    changed.append(mesh.get_name())
                except Exception as ex:
                    log_warning(f"[uv_add_channel] {mesh.get_name()}: {ex}")

        action = "Would add" if dry_run else "Added"
        log_info(f"[uv_add_channel] {action} UV channel on {len(changed)} meshes")
        return {"status": "ok", "dry_run": dry_run, "changed": len(changed), "meshes": changed}
    except Exception as e:
        log_error(f"[uv_add_channel] {e}")
        return {"status": "error", "message": str(e)}
