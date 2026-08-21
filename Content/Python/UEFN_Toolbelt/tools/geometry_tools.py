"""
UEFN TOOLBELT — Geometry Scripting Tools
========================================
Mesh operations on StaticMesh assets using GeometryScriptingCore.

The workflow for all geometry ops:
  1. Load static mesh asset
  2. Copy mesh data into a DynamicMesh object
  3. Apply the operation (boolean, repair, UV gen, etc.)
  4. Copy the result back to the static mesh asset
  5. Save the asset

What Python CAN do via GeometryScriptingCore:
  • Boolean union / subtract / intersect on meshes
  • Repair: fill holes, weld edges, remove degenerate triangles
  • UV operations: auto UV, lightmap UV generation
  • Normal recomputation
  • Convex hull generation

What Python CANNOT do:
  • Create NaniteDisplacedMesh assets
  • Edit procedural mesh components at runtime (Verse-only)
  • Access geometry in BSP brushes

API: unreal.GeometryScriptLibrary_* function libraries
"""

from __future__ import annotations

import unreal

from ..core import api_unavailable, log_error, log_info, log_warning, missing_unreal_apis
from ..registry import register_tool

# unreal.* names this module uses but does not require.
# Removed in UEFN 42.00 (UE 6.0). Every tool here gates on
# missing_unreal_apis() and returns a structured refusal instead of failing.
__optional_unreal_apis__ = (
    "GeometryScriptLibrary_StaticMeshFunctions",
    "GeometryScriptLibrary_MeshRepairFunctions",
    "GeometryScriptLibrary_MeshNormalsFunctions",
    "GeometryScriptLibrary_MeshUVFunctions",
    "GeometryScriptLibrary_MeshBooleanFunctions",
    "GeometryScriptMeshBooleanOperation",
    "GeometryScriptMeshWeldEdgesOptions",
    "GeometryScriptRecomputeNormalsOptions",
    "GeometryScriptRemoveSmallComponentsOptions",
    "GeometryScriptLODType",
    "GeometryScriptLODType.MAXIMUM_AVAILABLE",
    # Attribute-level: the options class exists, this field does not.
    "GeometryScriptRepackUVsOptions.target_resolution",
)


def _load_static_mesh(actor: unreal.Actor):
    """
    Return the first StaticMesh asset found on an actor, or None.
    Works on bare StaticMeshActors AND Blueprint actors that contain
    a StaticMeshComponent internally.
    """
    try:
        # Fast path: bare StaticMeshActor has direct property
        if isinstance(actor, unreal.StaticMeshActor):
            comp = actor.static_mesh_component
            if comp:
                mesh = comp.get_static_mesh()
                if mesh:
                    return mesh
        # Fallback: any actor that has a StaticMeshComponent with a mesh assigned
        comps = actor.get_components_by_class(unreal.StaticMeshComponent)
        for comp in comps:
            mesh = comp.get_static_mesh()
            if mesh:
                return mesh
    except Exception:
        pass
    return None


def _get_dyn_mesh():
    """Create a new DynamicMesh object."""
    return unreal.DynamicMesh()


def _selected_static_mesh_actors():
    """Return all currently selected level actors."""
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return list(actor_sub.get_selected_level_actors())


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="geometry_weld_edges",
    category="Geometry",
    description=(
        "Weld open edges on selected StaticMesh actors to fix gaps and cracks. "
        "Saves the modified mesh assets in place."
    ),
    tags=["geometry", "mesh", "weld", "repair", "edges"],
)
def run_geometry_weld_edges(
    tolerance: float = 0.1,
    dry_run: bool = True,
    **kwargs,
) -> dict:
    """
    Weld coincident vertices on selected static mesh actors.

    Args:
        tolerance: Maximum distance between vertices to weld (default 0.1 cm)
        dry_run:   If True, only reports what would change without saving (default True)
    """
    _missing = missing_unreal_apis("GeometryScriptLibrary_StaticMeshFunctions", "GeometryScriptLibrary_MeshRepairFunctions")
    if _missing:
        return api_unavailable("geometry_weld_edges", _missing)
    actors = _selected_static_mesh_actors()
    if not actors:
        return {"status": "error", "error": "No actors selected. Select any actor with a static mesh in the viewport first."}

    results = []
    for actor in actors:
        mesh = _load_static_mesh(actor)
        if mesh is None:
            results.append({"actor": actor.get_actor_label(), "status": "skipped", "reason": "no static mesh"})
            continue
        try:
            dyn = _get_dyn_mesh()
            opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
            unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
                static_mesh_asset=mesh,
                target_mesh=dyn,
                asset_options=opts,
                lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
            )
            weld_opts = unreal.GeometryScriptMeshWeldEdgesOptions()
            weld_opts.tolerance = tolerance
            unreal.GeometryScriptLibrary_MeshRepairFunctions.weld_mesh_edges(dyn, weld_opts)

            if not dry_run:
                write_opts = unreal.GeometryScriptCopyMeshToAssetOptions()
                unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_to_static_mesh(
                    from_dynamic_mesh=dyn,
                    to_static_mesh_asset=mesh,
                    options=write_opts,
                    lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
                )
                unreal.EditorAssetLibrary.save_loaded_asset(mesh)

            results.append({"actor": actor.get_actor_label(), "status": "ok", "mesh": mesh.get_name()})
        except Exception as e:
            log_warning(f"geometry_weld_edges failed on {actor.get_actor_label()}: {e}")
            results.append({"actor": actor.get_actor_label(), "status": "error", "error": str(e)})

    log_info(f"geometry_weld_edges: processed {len(results)} mesh(es), dry_run={dry_run}")
    return {"status": "ok", "dry_run": dry_run, "tolerance": tolerance, "results": results}


@register_tool(
    name="geometry_fill_holes",
    category="Geometry",
    description=(
        "Fill open holes in selected StaticMesh actors. "
        "Useful for fixing imported meshes with missing faces."
    ),
    tags=["geometry", "mesh", "repair", "holes", "fill"],
)
def run_geometry_fill_holes(
    dry_run: bool = True,
    **kwargs,
) -> dict:
    """
    Fill all open boundary loops (holes) in selected static meshes.

    Args:
        dry_run: If True, only reports without saving (default True)
    """
    _missing = missing_unreal_apis("GeometryScriptLibrary_StaticMeshFunctions", "GeometryScriptLibrary_MeshRepairFunctions")
    if _missing:
        return api_unavailable("geometry_fill_holes", _missing)
    actors = _selected_static_mesh_actors()
    if not actors:
        return {"status": "error", "error": "No actors selected. Select any actor with a static mesh in the viewport first."}

    results = []
    for actor in actors:
        mesh = _load_static_mesh(actor)
        if mesh is None:
            results.append({"actor": actor.get_actor_label(), "status": "skipped"})
            continue
        try:
            dyn = _get_dyn_mesh()
            opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
            unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
                static_mesh_asset=mesh,
                target_mesh=dyn,
                asset_options=opts,
                lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
            )
            fill_opts = unreal.GeometryScriptFillHolesOptions()
            unreal.GeometryScriptLibrary_MeshRepairFunctions.fill_all_mesh_holes(dyn, fill_opts)

            if not dry_run:
                write_opts = unreal.GeometryScriptCopyMeshToAssetOptions()
                unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_to_static_mesh(
                    from_dynamic_mesh=dyn,
                    to_static_mesh_asset=mesh,
                    options=write_opts,
                    lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
                )
                unreal.EditorAssetLibrary.save_loaded_asset(mesh)

            results.append({"actor": actor.get_actor_label(), "status": "ok", "mesh": mesh.get_name()})
        except Exception as e:
            log_warning(f"geometry_fill_holes failed on {actor.get_actor_label()}: {e}")
            results.append({"actor": actor.get_actor_label(), "status": "error", "error": str(e)})

    return {"status": "ok", "dry_run": dry_run, "results": results}


@register_tool(
    name="geometry_compute_normals",
    category="Geometry",
    description=(
        "Recompute vertex normals on selected StaticMesh actors. "
        "Fixes shading artefacts from bad normals on imported meshes."
    ),
    tags=["geometry", "mesh", "normals", "shading", "repair"],
)
def run_geometry_compute_normals(
    angle_threshold_deg: float = 60.0,
    dry_run: bool = True,
    **kwargs,
) -> dict:
    """
    Recompute normals on selected static meshes.

    Args:
        angle_threshold_deg: Angle (degrees) above which an edge is treated as hard (default 60)
        dry_run:             If True, only reports without saving
    """
    _missing = missing_unreal_apis("GeometryScriptLibrary_StaticMeshFunctions", "GeometryScriptLibrary_MeshNormalsFunctions")
    if _missing:
        return api_unavailable("geometry_compute_normals", _missing)
    actors = _selected_static_mesh_actors()
    if not actors:
        return {"status": "error", "error": "No actors selected. Select any actor with a static mesh in the viewport first."}

    results = []
    for actor in actors:
        mesh = _load_static_mesh(actor)
        if mesh is None:
            results.append({"actor": actor.get_actor_label(), "status": "skipped"})
            continue
        try:
            dyn = _get_dyn_mesh()
            opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
            unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
                static_mesh_asset=mesh,
                target_mesh=dyn,
                asset_options=opts,
                lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
            )
            normal_opts = unreal.GeometryScriptRecomputeNormalsOptions()
            normal_opts.angle_threshold_deg = angle_threshold_deg
            unreal.GeometryScriptLibrary_MeshNormalsFunctions.recompute_normals(dyn, normal_opts)

            if not dry_run:
                write_opts = unreal.GeometryScriptCopyMeshToAssetOptions()
                unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_to_static_mesh(
                    from_dynamic_mesh=dyn,
                    to_static_mesh_asset=mesh,
                    options=write_opts,
                    lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
                )
                unreal.EditorAssetLibrary.save_loaded_asset(mesh)

            results.append({"actor": actor.get_actor_label(), "status": "ok"})
        except Exception as e:
            log_warning(f"geometry_compute_normals failed on {actor.get_actor_label()}: {e}")
            results.append({"actor": actor.get_actor_label(), "status": "error", "error": str(e)})

    return {"status": "ok", "dry_run": dry_run, "angle_threshold_deg": angle_threshold_deg, "results": results}


@register_tool(
    name="geometry_generate_lightmap_uvs",
    category="Geometry",
    description=(
        "Auto-generate lightmap UVs (UV channel 1) on selected StaticMesh actors. "
        "Required for Lumen / baked lighting to work correctly on custom meshes."
    ),
    tags=["geometry", "mesh", "uv", "lightmap", "bake"],
)
def run_geometry_generate_lightmap_uvs(
    lightmap_resolution: int = 64,
    uv_channel: int = 1,
    dry_run: bool = True,
    **kwargs,
) -> dict:
    """
    Generate lightmap UVs on selected static meshes.

    Args:
        lightmap_resolution: Target texel resolution (default 64)
        uv_channel:          UV channel to write to (default 1 — standard lightmap channel)
        dry_run:             If True, only reports without saving
    """
    _missing = missing_unreal_apis("GeometryScriptLibrary_StaticMeshFunctions", "GeometryScriptLibrary_MeshUVFunctions")
    if _missing:
        return api_unavailable("geometry_generate_lightmap_uvs", _missing)
    actors = _selected_static_mesh_actors()
    if not actors:
        return {"status": "error", "error": "No actors selected. Select any actor with a static mesh in the viewport first."}

    results = []
    for actor in actors:
        mesh = _load_static_mesh(actor)
        if mesh is None:
            results.append({"actor": actor.get_actor_label(), "status": "skipped"})
            continue
        try:
            dyn = _get_dyn_mesh()
            opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
            unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
                static_mesh_asset=mesh,
                target_mesh=dyn,
                asset_options=opts,
                lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
            )
            uv_opts = unreal.GeometryScriptRepackUVsOptions()
            uv_opts.target_resolution = lightmap_resolution
            unreal.GeometryScriptLibrary_MeshUVFunctions.repack_mesh_uvs(
                target_mesh=dyn,
                uv_channel=uv_channel,
                repack_options=uv_opts,
            )

            if not dry_run:
                write_opts = unreal.GeometryScriptCopyMeshToAssetOptions()
                unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_to_static_mesh(
                    from_dynamic_mesh=dyn,
                    to_static_mesh_asset=mesh,
                    options=write_opts,
                    lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
                )
                unreal.EditorAssetLibrary.save_loaded_asset(mesh)

            results.append({"actor": actor.get_actor_label(), "status": "ok", "uv_channel": uv_channel})
        except Exception as e:
            log_warning(f"geometry_generate_lightmap_uvs failed on {actor.get_actor_label()}: {e}")
            results.append({"actor": actor.get_actor_label(), "status": "error", "error": str(e)})

    return {"status": "ok", "dry_run": dry_run, "lightmap_resolution": lightmap_resolution, "results": results}


@register_tool(
    name="geometry_boolean_union",
    category="Geometry",
    description=(
        "Boolean union: merge the first two selected StaticMesh actors into one mesh. "
        "Saves the result into the first actor's mesh asset. Always dry_run=True first."
    ),
    tags=["geometry", "mesh", "boolean", "union", "merge", "csg"],
)
def run_geometry_boolean_union(
    dry_run: bool = True,
    **kwargs,
) -> dict:
    """
    Boolean union the first two selected StaticMeshActors.
    The result is written back into the first actor's mesh asset.

    Args:
        dry_run: If True, only validates without modifying assets (default True)
    """
    _missing = missing_unreal_apis("GeometryScriptLibrary_StaticMeshFunctions", "GeometryScriptLibrary_MeshBooleanFunctions")
    if _missing:
        return api_unavailable("geometry_boolean_union", _missing)
    actors = _selected_static_mesh_actors()
    if len(actors) < 2:
        return {"status": "error", "error": "Select exactly 2 StaticMeshActors — first is the target, second is the cutter."}

    actor_a, actor_b = actors[0], actors[1]
    mesh_a = _load_static_mesh(actor_a)
    mesh_b = _load_static_mesh(actor_b)

    if mesh_a is None or mesh_b is None:
        return {"status": "error", "error": "One or both actors have no static mesh."}

    if dry_run:
        return {
            "status": "ok",
            "dry_run": True,
            "target": actor_a.get_actor_label(),
            "cutter": actor_b.get_actor_label(),
            "message": "Set dry_run=False to apply. Result written into first actor's mesh asset.",
        }

    try:
        dyn_a = _get_dyn_mesh()
        dyn_b = _get_dyn_mesh()
        copy_opts = unreal.GeometryScriptCopyMeshFromAssetOptions()

        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
            static_mesh_asset=mesh_a, target_mesh=dyn_a,
            asset_options=copy_opts, lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )
        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
            static_mesh_asset=mesh_b, target_mesh=dyn_b,
            asset_options=copy_opts, lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )

        bool_opts = unreal.GeometryScriptMeshBooleanOptions()
        transform_b = actor_b.get_actor_transform()
        transform_a = actor_a.get_actor_transform()

        unreal.GeometryScriptLibrary_MeshBooleanFunctions.apply_mesh_boolean(
            target_mesh=dyn_a,
            target_transform=transform_a,
            tool_mesh=dyn_b,
            tool_transform=transform_b,
            operation=unreal.GeometryScriptMeshBooleanOperation.UNION,
            options=bool_opts,
        )

        write_opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_to_static_mesh(
            from_dynamic_mesh=dyn_a,
            to_static_mesh_asset=mesh_a,
            options=write_opts,
            lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )
        unreal.EditorAssetLibrary.save_loaded_asset(mesh_a)

        log_info(f"geometry_boolean_union: {actor_a.get_actor_label()} ∪ {actor_b.get_actor_label()} → saved.")
        return {
            "status": "ok",
            "dry_run": False,
            "target": actor_a.get_actor_label(),
            "cutter": actor_b.get_actor_label(),
            "saved_mesh": mesh_a.get_name(),
        }
    except Exception as e:
        log_error(f"geometry_boolean_union failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="geometry_boolean_subtract",
    category="Geometry",
    description=(
        "Boolean subtract: cut the second selected actor's shape out of the first. "
        "Saves the result into the first actor's mesh asset. Always dry_run=True first."
    ),
    tags=["geometry", "mesh", "boolean", "subtract", "cut", "csg"],
)
def run_geometry_boolean_subtract(dry_run: bool = True, **kwargs) -> dict:
    _missing = missing_unreal_apis("GeometryScriptLibrary_StaticMeshFunctions", "GeometryScriptLibrary_MeshBooleanFunctions")
    if _missing:
        return api_unavailable("geometry_boolean_subtract", _missing)
    actors = _selected_static_mesh_actors()
    if len(actors) < 2:
        return {"status": "error", "error": "Select exactly 2 StaticMeshActors — first is the target, second is the cutter."}

    actor_a, actor_b = actors[0], actors[1]
    mesh_a = _load_static_mesh(actor_a)
    mesh_b = _load_static_mesh(actor_b)
    if mesh_a is None or mesh_b is None:
        return {"status": "error", "error": "One or both actors have no static mesh."}

    if dry_run:
        return {
            "status": "ok", "dry_run": True,
            "target": actor_a.get_actor_label(), "cutter": actor_b.get_actor_label(),
            "message": "Set dry_run=False to apply. Cuts second mesh out of first.",
        }

    try:
        dyn_a, dyn_b = _get_dyn_mesh(), _get_dyn_mesh()
        copy_opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
            static_mesh_asset=mesh_a, target_mesh=dyn_a, asset_options=copy_opts,
            lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )
        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
            static_mesh_asset=mesh_b, target_mesh=dyn_b, asset_options=copy_opts,
            lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )
        unreal.GeometryScriptLibrary_MeshBooleanFunctions.apply_mesh_boolean(
            target_mesh=dyn_a, target_transform=actor_a.get_actor_transform(),
            tool_mesh=dyn_b, tool_transform=actor_b.get_actor_transform(),
            operation=unreal.GeometryScriptMeshBooleanOperation.SUBTRACT,
            options=unreal.GeometryScriptMeshBooleanOptions(),
        )
        write_opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_to_static_mesh(
            from_dynamic_mesh=dyn_a, to_static_mesh_asset=mesh_a,
            options=write_opts, lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )
        unreal.EditorAssetLibrary.save_loaded_asset(mesh_a)
        log_info(f"geometry_boolean_subtract: {actor_a.get_actor_label()} − {actor_b.get_actor_label()} → saved.")
        return {"status": "ok", "dry_run": False, "saved_mesh": mesh_a.get_name()}
    except Exception as e:
        log_error(f"geometry_boolean_subtract failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="geometry_boolean_intersect",
    category="Geometry",
    description=(
        "Boolean intersect: keep only the volume shared by both selected actors. "
        "Saves the result into the first actor's mesh asset. Always dry_run=True first."
    ),
    tags=["geometry", "mesh", "boolean", "intersect", "csg", "overlap"],
)
def run_geometry_boolean_intersect(dry_run: bool = True, **kwargs) -> dict:
    _missing = missing_unreal_apis("GeometryScriptLibrary_StaticMeshFunctions", "GeometryScriptLibrary_MeshBooleanFunctions")
    if _missing:
        return api_unavailable("geometry_boolean_intersect", _missing)
    actors = _selected_static_mesh_actors()
    if len(actors) < 2:
        return {"status": "error", "error": "Select exactly 2 StaticMeshActors."}

    actor_a, actor_b = actors[0], actors[1]
    mesh_a = _load_static_mesh(actor_a)
    mesh_b = _load_static_mesh(actor_b)
    if mesh_a is None or mesh_b is None:
        return {"status": "error", "error": "One or both actors have no static mesh."}

    if dry_run:
        return {
            "status": "ok", "dry_run": True,
            "target": actor_a.get_actor_label(), "cutter": actor_b.get_actor_label(),
            "message": "Set dry_run=False to apply. Keeps only the shared volume.",
        }

    try:
        dyn_a, dyn_b = _get_dyn_mesh(), _get_dyn_mesh()
        copy_opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
            static_mesh_asset=mesh_a, target_mesh=dyn_a, asset_options=copy_opts,
            lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )
        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
            static_mesh_asset=mesh_b, target_mesh=dyn_b, asset_options=copy_opts,
            lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )
        unreal.GeometryScriptLibrary_MeshBooleanFunctions.apply_mesh_boolean(
            target_mesh=dyn_a, target_transform=actor_a.get_actor_transform(),
            tool_mesh=dyn_b, tool_transform=actor_b.get_actor_transform(),
            operation=unreal.GeometryScriptMeshBooleanOperation.INTERSECT,
            options=unreal.GeometryScriptMeshBooleanOptions(),
        )
        write_opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_to_static_mesh(
            from_dynamic_mesh=dyn_a, to_static_mesh_asset=mesh_a,
            options=write_opts, lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
        )
        unreal.EditorAssetLibrary.save_loaded_asset(mesh_a)
        log_info(f"geometry_boolean_intersect: {actor_a.get_actor_label()} ∩ {actor_b.get_actor_label()} → saved.")
        return {"status": "ok", "dry_run": False, "saved_mesh": mesh_a.get_name()}
    except Exception as e:
        log_error(f"geometry_boolean_intersect failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="geometry_remove_degenerate",
    category="Geometry",
    description=(
        "Remove degenerate triangles (zero-area or near-zero-area faces) from "
        "selected StaticMesh actors. Fixes invisible collision and lighting artifacts."
    ),
    tags=["geometry", "mesh", "repair", "degenerate", "triangles", "cleanup"],
)
def run_geometry_remove_degenerate(min_area: float = 0.0001, dry_run: bool = True, **kwargs) -> dict:
    _missing = missing_unreal_apis("GeometryScriptLibrary_StaticMeshFunctions", "GeometryScriptLibrary_MeshRepairFunctions")
    if _missing:
        return api_unavailable("geometry_remove_degenerate", _missing)
    actors = _selected_static_mesh_actors()
    if not actors:
        return {"status": "error", "error": "No StaticMeshActors selected."}

    if dry_run:
        meshes = [a.get_actor_label() for a in actors if _load_static_mesh(a)]
        return {
            "status": "ok", "dry_run": True, "actors": meshes,
            "message": f"Set dry_run=False to remove degenerate triangles (min_area={min_area}) from {len(meshes)} mesh(es).",
        }

    repaired = []
    failed   = []
    for actor in actors:
        mesh = _load_static_mesh(actor)
        if mesh is None:
            continue
        try:
            dyn = _get_dyn_mesh()
            copy_opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
            unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_from_static_mesh(
                static_mesh_asset=mesh, target_mesh=dyn, asset_options=copy_opts,
                lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
            )
            repair_opts = unreal.GeometryScriptRemoveSmallComponentsOptions()
            repair_opts.set_editor_property("min_triangle_area_threshold", min_area)
            unreal.GeometryScriptLibrary_MeshRepairFunctions.remove_small_components(
                target_mesh=dyn, options=repair_opts,
            )
            write_opts = unreal.GeometryScriptCopyMeshToAssetOptions()
            unreal.GeometryScriptLibrary_StaticMeshFunctions.copy_mesh_to_static_mesh(
                from_dynamic_mesh=dyn, to_static_mesh_asset=mesh,
                options=write_opts, lod_type=unreal.GeometryScriptLODType.MAXIMUM_AVAILABLE,
            )
            unreal.EditorAssetLibrary.save_loaded_asset(mesh)
            repaired.append(mesh.get_name())
        except Exception as e:
            failed.append({"mesh": mesh.get_name(), "error": str(e)})
            log_error(f"geometry_remove_degenerate failed on {mesh.get_name()}: {e}")

    log_info(f"geometry_remove_degenerate: {len(repaired)} repaired, {len(failed)} failed.")
    return {"status": "ok", "dry_run": False, "repaired": repaired, "failed": failed}
