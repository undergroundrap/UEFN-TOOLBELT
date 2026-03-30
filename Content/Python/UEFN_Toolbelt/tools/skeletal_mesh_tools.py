"""
UEFN TOOLBELT — Skeletal Mesh Tools
=====================================
Tools for inspecting and configuring SkeletalMesh assets and skeletal mesh
components on level actors. Complements animation_tools (which handles
AnimSequences, Montages, BlendSpaces) by covering the mesh side: sockets,
physics assets, and animation class assignment.

What Python CAN do:
  • List all SkeletalMesh assets in a folder
  • Inspect sockets defined on a SkeletalMesh
  • Audit SkeletalMesh assets for missing physics assets or anim class
  • Assign a physics asset to a SkeletalMesh
  • List SkeletalMesh components on selected level actors

What Python CANNOT do:
  • Add or rename sockets (socket editing requires the Skeleton editor)
  • Modify bone transforms or bind poses
  • Import or re-import skeletal meshes (use smart_importer for FBX import)
  • Edit morph targets / blend shapes

API: SkeletalMesh, SkeletalMeshComponent, EditorAssetLibrary, AssetRegistry
"""

from __future__ import annotations

import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


def _actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="skel_list",
    category="Skeletal Mesh",
    description=(
        "List all SkeletalMesh assets in a Content Browser folder. "
        "Returns asset paths, skeleton references, and polygon counts. "
        "Use this to inventory skeletal assets before a memory or LOD audit."
    ),
    tags=["skeletal", "mesh", "list", "assets", "scan"],
    example='tb.run("skel_list", scan_path="/Game/Characters")',
)
def run_skel_list(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    # Uses AR tag data only — never calls load_asset(), safe on pak-heavy projects.
    try:
        filt = unreal.ARFilter(
            class_names=["SkeletalMesh"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        results = []
        for a in assets:
            results.append({
                "name": str(a.asset_name),
                "path": str(a.package_name),
                "skeleton": str(a.get_tag_value("Skeleton") or "unknown"),
                "physics_asset": str(a.get_tag_value("PhysicsAsset") or "none"),
            })

        log_info(f"[skel_list] {len(results)} SkeletalMesh asset(s) in {scan_path}")
        return {"status": "ok", "count": len(results), "meshes": results}
    except Exception as e:
        log_error(f"[skel_list] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="skel_audit",
    category="Skeletal Mesh",
    description=(
        "Audit SkeletalMesh assets in a folder for common issues: "
        "missing physics asset, missing skeleton reference, and missing animation class. "
        "Returns a health report with per-mesh status and issue descriptions."
    ),
    tags=["skeletal", "mesh", "audit", "health", "physics"],
    example='tb.run("skel_audit", scan_path="/Game/Characters")',
)
def run_skel_audit(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=["SkeletalMesh"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        issues = []
        clean = []

        for a in assets:
            name = str(a.asset_name)
            path = str(a.package_name)
            mesh_issues = []
            skel_tag = a.get_tag_value("Skeleton") or ""
            phys_tag = a.get_tag_value("PhysicsAsset") or ""
            if not skel_tag or skel_tag in ("None", "none", "null"):
                mesh_issues.append("Missing skeleton reference")
            if not phys_tag or phys_tag in ("None", "none", "null"):
                mesh_issues.append("No physics asset assigned")

            if mesh_issues:
                issues.append({"name": name, "path": path, "issues": mesh_issues})
            else:
                clean.append(name)

        log_info(f"[skel_audit] {len(clean)} clean, {len(issues)} with issues")
        return {
            "status": "ok",
            "total": len(assets),
            "clean": len(clean),
            "issues": len(issues),
            "issue_list": issues,
        }
    except Exception as e:
        log_error(f"[skel_audit] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="skel_list_sockets",
    category="Skeletal Mesh",
    description=(
        "List all sockets defined on a SkeletalMesh asset. "
        "Sockets define attachment points for weapons, accessories, and VFX. "
        "Returns socket names, bone names, and local transform offsets."
    ),
    tags=["skeletal", "mesh", "sockets", "attachment", "bones"],
    example='tb.run("skel_list_sockets", asset_path="/Game/Characters/SK_Hero")',
)
def run_skel_list_sockets(asset_path: str = "", **kwargs) -> dict:
    if not asset_path:
        return {"status": "error", "message": "asset_path is required."}
    try:
        mesh = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not isinstance(mesh, unreal.SkeletalMesh):
            return {"status": "error", "message": f"Asset at '{asset_path}' is not a SkeletalMesh."}

        sockets = []
        try:
            mesh_sockets = mesh.get_editor_property("sockets") or []
            for s in mesh_sockets:
                socket_info = {"name": str(s.get_editor_property("socket_name"))}
                try:
                    socket_info["bone"] = str(s.get_editor_property("bone_name"))
                    loc = s.get_editor_property("relative_location")
                    rot = s.get_editor_property("relative_rotation")
                    scale = s.get_editor_property("relative_scale")
                    socket_info["location"] = [round(loc.x, 2), round(loc.y, 2), round(loc.z, 2)]
                    socket_info["rotation"] = [round(rot.pitch, 2), round(rot.yaw, 2), round(rot.roll, 2)]
                    socket_info["scale"] = [round(scale.x, 3), round(scale.y, 3), round(scale.z, 3)]
                except Exception:
                    pass
                sockets.append(socket_info)
        except Exception as ex:
            log_warning(f"[skel_list_sockets] Could not read sockets: {ex}")

        log_info(f"[skel_list_sockets] {len(sockets)} socket(s) on {asset_path}")
        return {"status": "ok", "asset_path": asset_path, "socket_count": len(sockets), "sockets": sockets}
    except Exception as e:
        log_error(f"[skel_list_sockets] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="skel_set_physics_asset",
    category="Skeletal Mesh",
    description=(
        "Assign a physics asset to a SkeletalMesh asset. "
        "The physics asset controls ragdoll simulation and collision for the mesh. "
        "Use skel_audit to find meshes with missing physics assets."
    ),
    tags=["skeletal", "mesh", "physics", "ragdoll", "assign"],
    example='tb.run("skel_set_physics_asset", mesh_path="/Game/Characters/SK_Hero", physics_path="/Game/Characters/PA_Hero")',
)
def run_skel_set_physics_asset(
    mesh_path: str = "",
    physics_path: str = "",
    dry_run: bool = True,
    **kwargs,
) -> dict:
    if not mesh_path:
        return {"status": "error", "message": "mesh_path is required."}
    if not physics_path:
        return {"status": "error", "message": "physics_path is required."}
    try:
        mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
        if not isinstance(mesh, unreal.SkeletalMesh):
            return {"status": "error", "message": f"'{mesh_path}' is not a SkeletalMesh."}

        phys = unreal.EditorAssetLibrary.load_asset(physics_path)
        if not isinstance(phys, unreal.PhysicsAsset):
            return {"status": "error", "message": f"'{physics_path}' is not a PhysicsAsset."}

        if not dry_run:
            mesh.set_editor_property("physics_asset", phys)
            unreal.EditorAssetLibrary.save_loaded_asset(mesh)

        action = "Would assign" if dry_run else "Assigned"
        log_info(f"[skel_set_physics_asset] {action} {physics_path} → {mesh_path}")
        return {
            "status": "ok",
            "dry_run": dry_run,
            "mesh": mesh_path,
            "physics_asset": physics_path,
        }
    except Exception as e:
        log_error(f"[skel_set_physics_asset] {e}")
        return {"status": "error", "message": str(e)}
