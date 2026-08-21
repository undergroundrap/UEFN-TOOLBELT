"""
UEFN TOOLBELT — Animation Tools
=================================
Tools for inspecting and creating animation assets.

What Python CAN do:
  • List AnimSequence, AnimMontage, BlendSpace, Skeleton assets
  • Inspect skeleton, frame count, play length per sequence
  • Create new AnimMontage assets from an existing skeleton

What Python CANNOT do:
  • Edit AnimGraph Blueprint state machines (Blueprint-only)
  • Modify per-frame curve data or pose data programmatically
  • Create AnimBlueprints from scratch via Python
  • Stack emitter editing (architecture is Blueprint-only)

API: AnimGraph (97 classes), AnimGraphRuntime (152 classes)
"""

from __future__ import annotations

import unreal

from ..core import log_error, log_info, resolve_content_path, resolve_scan_path
from ..registry import register_tool


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="anim_list_skeletons",
    category="Animation",
    description=(
        "List all Skeleton assets in the project. Skeletons define the bone "
        "hierarchy shared by SkeletalMeshes, AnimSequences, and AnimMontages. "
        "Every animation asset is bound to exactly one Skeleton."
    ),
    tags=["animation", "skeleton", "bones", "rig", "list"],
    example='tb.run("anim_list_skeletons", search_path="/Game/")',
)
def run_anim_list_skeletons(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["Skeleton"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = [{"name": str(a.asset_name), "path": str(a.package_name)} for a in assets]
        log_info(f"[anim_list_skeletons] {len(results)} Skeleton assets in {search_path}")
        return {"status": "ok", "count": len(results), "skeletons": results}
    except Exception as e:
        log_error(f"[anim_list_skeletons] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="anim_list_sequences",
    category="Animation",
    description=(
        "List all AnimSequence assets in a path. Returns name, path, "
        "skeleton name, frame count, and play length in seconds."
    ),
    tags=["animation", "sequence", "list", "anim", "skeletal"],
    example='tb.run("anim_list_sequences", search_path="/Game/Characters/")',
)
def run_anim_list_sequences(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["AnimSequence"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = []
        for a in assets:
            entry = {"name": str(a.asset_name), "path": str(a.package_name)}
            try:
                loaded = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if loaded:
                    if hasattr(loaded, "get_play_length"):
                        entry["duration_sec"] = round(loaded.get_play_length(), 3)
                    skel = loaded.get_editor_property("skeleton") if hasattr(loaded, "get_editor_property") else None
                    entry["skeleton"] = skel.get_name() if skel else None
            except Exception:
                pass
            results.append(entry)
        log_info(f"[anim_list_sequences] {len(results)} AnimSequences in {search_path}")
        return {"status": "ok", "count": len(results), "sequences": results}
    except Exception as e:
        log_error(f"[anim_list_sequences] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="anim_list_montages",
    category="Animation",
    description=(
        "List all AnimMontage assets in a path. Montages compose sequences "
        "into sections and slots — used for triggered actions like attacks, "
        "hit reactions, and emotes."
    ),
    tags=["animation", "montage", "list", "anim", "sections"],
    example='tb.run("anim_list_montages", search_path="/Game/")',
)
def run_anim_list_montages(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["AnimMontage"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = []
        for a in assets:
            entry = {"name": str(a.asset_name), "path": str(a.package_name)}
            try:
                loaded = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if loaded and hasattr(loaded, "get_play_length"):
                    entry["duration_sec"] = round(loaded.get_play_length(), 3)
            except Exception:
                pass
            results.append(entry)
        log_info(f"[anim_list_montages] {len(results)} AnimMontages in {search_path}")
        return {"status": "ok", "count": len(results), "montages": results}
    except Exception as e:
        log_error(f"[anim_list_montages] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="anim_list_blend_spaces",
    category="Animation",
    description=(
        "List all BlendSpace and BlendSpace1D assets in a path. "
        "BlendSpaces interpolate between multiple AnimSequences along 1 or 2 "
        "axes — used for locomotion (walk/run/sprint by speed)."
    ),
    tags=["animation", "blendspace", "blend", "locomotion", "list"],
    example='tb.run("anim_list_blend_spaces", search_path="/Game/")',
)
def run_anim_list_blend_spaces(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["BlendSpace", "BlendSpace1D"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = [
            {"name": str(a.asset_name), "path": str(a.package_name), "class": str(a.asset_class)}
            for a in assets
        ]
        log_info(f"[anim_list_blend_spaces] {len(results)} BlendSpaces in {search_path}")
        return {"status": "ok", "count": len(results), "blend_spaces": results}
    except Exception as e:
        log_error(f"[anim_list_blend_spaces] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="anim_create_montage",
    category="Animation",
    description=(
        "Create a new AnimMontage asset linked to the skeleton of an existing "
        "AnimSequence. The montage will be empty — add sections and slots via "
        "the Animation Editor UI or Verse."
    ),
    tags=["animation", "montage", "create", "new", "anim"],
    example='tb.run("anim_create_montage", sequence_path="/Game/Anims/AS_Walk", destination="/Game/Anims/", name="AM_Walk")',
)
def run_anim_create_montage(
    sequence_path: str = "",
    destination: str = "",
    name: str = "",
    **kwargs,
) -> dict:
    destination = resolve_content_path(destination, "Animations")
    if not sequence_path:
        return {"status": "error", "message": "sequence_path is required."}
    try:
        seq = unreal.EditorAssetLibrary.load_asset(sequence_path)
        if seq is None:
            return {"status": "error", "message": f"Sequence not found: {sequence_path}"}

        skeleton = seq.get_editor_property("skeleton") if hasattr(seq, "get_editor_property") else None
        if skeleton is None:
            return {"status": "error", "message": "Could not read skeleton from sequence."}

        montage_name = name or f"AM_{seq.get_name()}"
        factory = unreal.AnimMontageFactory()
        factory.set_editor_property("target_skeleton", skeleton)

        montage = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            montage_name, destination, unreal.AnimMontage, factory
        )
        if montage is None:
            return {"status": "error", "message": f"Failed to create montage '{montage_name}'"}

        path = f"{destination.rstrip('/')}/{montage_name}"
        unreal.EditorAssetLibrary.save_asset(path)
        log_info(f"[anim_create_montage] Created: {path}")
        return {"status": "ok", "path": path, "name": montage_name, "skeleton": skeleton.get_name()}
    except Exception as e:
        log_error(f"[anim_create_montage] {e}")
        return {"status": "error", "message": str(e)}
