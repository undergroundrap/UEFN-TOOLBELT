"""
UEFN TOOLBELT — Smart Importer & Organizer
========================================
Drop an FBX (or folder of FBXs) → auto-import, create organized folders,
apply a base material, and optionally place in the level. Everything the
vanilla "Import" dialog does in 10 clicks, done in one command.

FEATURES:
  • Import single FBX or all FBXs in a folder
  • Auto-create Content Browser folder structure based on asset type:
      /Game/Imported/[SessionDate]/Meshes/
      /Game/Imported/[SessionDate]/Materials/
  • Apply a basic material instance to every imported mesh automatically
  • Place imported meshes into the level at world origin (optional)
  • Generate a JSON import log saved to Saved/UEFN_Toolbelt/
  • Batch import with a progress bar
  • Handles import options: combine meshes, build LODs, auto-generate collision

USAGE:
    import UEFN_Toolbelt as tb

    # Import one file
    tb.run("import_fbx", file_path="C:/MyAssets/tree.fbx")

    # Import entire folder
    tb.run("import_fbx_folder",
           folder_path="C:/MyAssets/Props/",
           place_in_level=True,
           apply_material=True)

    # Organize existing /Game/Imports — sort into sub-folders by type
    tb.run("organize_assets",
           source_path="/Game/Imports",
           target_base="/Game/Organized")

BLUEPRINT:
    "Execute Python Command" →
        import UEFN_Toolbelt as tb; tb.run("import_fbx", file_path="C:/path/to/mesh.fbx")
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List, Optional

import unreal

from ..core import (
    log_info, log_warning, log_error,
    ensure_folder, load_asset, create_material_instance,
    spawn_static_mesh_actor, with_progress,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Base path where imports land in the Content Browser
IMPORT_BASE_PATH = "/Game/Imported"

# Parent material to apply to newly imported meshes
AUTO_MATERIAL_PARENT = "/Game/UEFN_Toolbelt/Materials/M_ToolbeltBase"

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _session_path() -> str:
    """Return a date-stamped sub-path, e.g. /Game/Imported/2024-01-15"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return f"{IMPORT_BASE_PATH}/{date_str}"


def _build_import_task(
    file_path: str,
    dest_path: str,
    dest_name: str,
    combine_meshes: bool = False,
    build_lods: bool = False,
) -> unreal.AssetImportTask:
    """Construct an AssetImportTask for a single FBX file."""
    task = unreal.AssetImportTask()
    task.filename         = file_path
    task.destination_path = dest_path
    task.destination_name = dest_name
    task.replace_existing = True
    task.automated        = True   # no dialog prompts
    task.save             = False  # we save explicitly after

    # FBX-specific import options
    options = unreal.FbxImportUI()
    options.import_mesh      = True
    options.import_textures  = True
    options.import_materials = False  # we apply our own material
    options.import_as_skeletal = False
    options.static_mesh_import_data.combine_meshes = combine_meshes
    options.static_mesh_import_data.build_adjacency_buffer = False
    options.static_mesh_import_data.build_reversed_index_buffer = True
    options.static_mesh_import_data.generate_lightmap_uvs = True
    task.options = options

    return task


def _run_import_tasks(tasks: List[unreal.AssetImportTask]) -> List[str]:
    """Execute import tasks and return list of imported asset paths."""
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    imported = []
    for task in tasks:
        if task.imported_object_paths:
            imported.extend(task.imported_object_paths)
    return imported


def _apply_auto_material(mesh_path: str) -> None:
    """Create and apply a material instance to a static mesh."""
    try:
        mesh = load_asset(mesh_path)
        if not isinstance(mesh, unreal.StaticMesh):
            return

        asset_name = mesh_path.split("/")[-1]
        mi = create_material_instance(
            AUTO_MATERIAL_PARENT,
            f"MI_Auto_{asset_name}",
            _session_path() + "/Materials",
        )
        if mi is None:
            return

        mesh.set_material(0, mi)
        unreal.EditorAssetLibrary.save_asset(mesh_path)
        log_info(f"  Applied auto-material to {asset_name}")
    except Exception as e:
        log_warning(f"  Auto-material apply failed for {mesh_path}: {e}")


def _write_import_log(records: list) -> None:
    out_dir  = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "import_log.json")
    try:
        existing = []
        if os.path.exists(log_path):
            with open(log_path) as f:
                existing = json.load(f)
    except Exception:
        existing = []

    existing.extend(records)
    with open(log_path, "w") as f:
        json.dump(existing, f, indent=2)
    log_info(f"Import log updated → {log_path}")


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="import_fbx",
    category="Assets",
    description="Import a single FBX file into the Content Browser with auto-setup.",
    tags=["import", "fbx", "mesh", "asset"],
)
def run_import_fbx(
    file_path: str = "",
    dest_path: str = "",
    apply_material: bool = True,
    place_in_level: bool = False,
    combine_meshes: bool = False,
    **kwargs,
) -> None:
    """
    Args:
        file_path:       Absolute OS path to the .fbx file.
        dest_path:       Content Browser destination folder (auto-generated if blank).
        apply_material:  Assign auto-generated material instance after import.
        place_in_level:  Spawn the imported mesh at world origin after import.
        combine_meshes:  Merge all sub-meshes in the FBX into one.
    """
    if not file_path:
        log_error("import_fbx: file_path is required.")
        return

    file_path = os.path.normpath(file_path)
    if not os.path.isfile(file_path):
        log_error(f"File not found: {file_path}")
        return

    if not file_path.lower().endswith(".fbx"):
        log_warning("import_fbx: expected an .fbx file.")

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    session   = dest_path or (_session_path() + "/Meshes")
    ensure_folder(session)

    log_info(f"Importing {base_name}.fbx → {session}")
    task = _build_import_task(file_path, session, base_name, combine_meshes)
    imported = _run_import_tasks([task])

    if not imported:
        log_error(f"Import failed for {file_path}. Check the Output Log for FBX errors.")
        return

    log_info(f"  Imported: {imported}")

    if apply_material:
        for path in imported:
            _apply_auto_material(path)

    if place_in_level:
        for path in imported:
            asset = load_asset(path)
            if isinstance(asset, unreal.StaticMesh):
                spawn_static_mesh_actor(path, unreal.Vector(0, 0, 0))
                log_info(f"  Placed '{base_name}' at world origin.")

    _write_import_log([{
        "timestamp": datetime.now().isoformat(),
        "source": file_path,
        "imported": imported,
    }])

    log_info(f"Import complete: {base_name}")


@register_tool(
    name="import_fbx_folder",
    category="Assets",
    description="Import all FBX files from a folder with auto-organization.",
    tags=["import", "fbx", "batch", "folder", "bulk"],
)
def run_import_fbx_folder(
    folder_path: str = "",
    dest_base: str = "",
    apply_material: bool = True,
    place_in_level: bool = False,
    combine_meshes: bool = False,
    **kwargs,
) -> None:
    """
    Args:
        folder_path:  Absolute OS path to the folder containing .fbx files.
        dest_base:    Content Browser base folder (auto-generated if blank).
        apply_material: Assign auto-generated materials after import.
        place_in_level: Spawn all imported meshes at world origin.
        combine_meshes: Merge sub-meshes per FBX.
    """
    if not folder_path:
        log_error("import_fbx_folder: folder_path is required.")
        return

    folder_path = os.path.normpath(folder_path)
    if not os.path.isdir(folder_path):
        log_error(f"Folder not found: {folder_path}")
        return

    fbx_files = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(".fbx")
    ]

    if not fbx_files:
        log_info(f"No .fbx files found in {folder_path}")
        return

    log_info(f"Found {len(fbx_files)} FBX files. Starting batch import…")
    session = dest_base or (_session_path() + "/Meshes")
    ensure_folder(session)

    tasks = []
    for fp in fbx_files:
        name = os.path.splitext(os.path.basename(fp))[0]
        tasks.append(_build_import_task(fp, session, name, combine_meshes))

    all_imported = _run_import_tasks(tasks)
    log_info(f"  Imported {len(all_imported)} assets.")

    if apply_material:
        for path in all_imported:
            _apply_auto_material(path)

    if place_in_level:
        step = 200.0
        for i, path in enumerate(all_imported):
            asset = load_asset(path)
            if isinstance(asset, unreal.StaticMesh):
                loc = unreal.Vector(i * step, 0, 0)
                spawn_static_mesh_actor(path, loc)

    _write_import_log([{
        "timestamp": datetime.now().isoformat(),
        "source": folder_path,
        "imported": all_imported,
    }])

    log_info(f"Batch import complete: {len(all_imported)} assets.")


@register_tool(
    name="organize_assets",
    category="Assets",
    description="Sort assets in a Content Browser folder into typed sub-folders.",
    tags=["organize", "sort", "content", "browser", "assets"],
)
def run_organize_assets(
    source_path: str = "/Game/Imports",
    target_base: str = "/Game/Organized",
    **kwargs,
) -> None:
    """
    Moves assets from source_path into target_base/Meshes, target_base/Materials,
    target_base/Textures, etc., based on asset class.

    Args:
        source_path: Content Browser folder to scan.
        target_base: Destination base folder.
    """
    if not unreal.EditorAssetLibrary.does_directory_exist(source_path):
        log_error(f"Source folder does not exist: {source_path}")
        return

    asset_paths = unreal.EditorAssetLibrary.list_assets(
        source_path, recursive=True, include_folder=False
    )

    if not asset_paths:
        log_info(f"No assets found in {source_path}")
        return

    type_map = {
        "StaticMesh":             "Meshes",
        "SkeletalMesh":           "SkeletalMeshes",
        "Material":               "Materials",
        "MaterialInstanceConstant": "Materials",
        "Texture2D":              "Textures",
        "SoundWave":              "Audio",
        "Blueprint":              "Blueprints",
        "AnimSequence":           "Animations",
        "AnimMontage":            "Animations",
    }

    moved = 0
    log_info(f"Organizing {len(asset_paths)} assets from {source_path}…")

    for asset_path in asset_paths:
        asset = load_asset(asset_path)
        if asset is None:
            continue

        class_name = asset.get_class().get_name()
        sub_folder = type_map.get(class_name, "Misc")
        target_folder = f"{target_base}/{sub_folder}"
        ensure_folder(target_folder)

        asset_name = asset_path.split("/")[-1]
        new_path = f"{target_folder}/{asset_name}"

        try:
            unreal.EditorAssetLibrary.rename_asset(asset_path, new_path)
            moved += 1
        except Exception as e:
            log_warning(f"  Could not move {asset_name}: {e}")

    log_info(f"Organize complete: {moved} assets moved to {target_base}/")
