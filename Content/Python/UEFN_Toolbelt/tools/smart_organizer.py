"""
UEFN TOOLBELT — Smart Auto-Organizer
========================================
Advanced heuristic-based asset organizer.
Scans a folder, detects asset classes, parses asset names for keywords, and automatically
sorts them into an intelligent /Type/Category folder structure.

FEATURES:
  • No external UI required — Native Toolbelt integration
  • Guesses categories by tokenizing names (e.g., "SM_PineTree" -> /Meshes/Trees)
  • Safe dry-run preview mode
  • Filter options to include unused assets or keep only referenced items

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Preview what would happen
    tb.run("organize_smart_categorize", scan_path="/Game/Imported", organized_root="/Game/MyLevel", dry_run=True)

    # Actually execute
    tb.run("organize_smart_categorize", scan_path="/Game/Imported", organized_root="/Game/MyLevel", dry_run=False)
"""

from __future__ import annotations

import unreal
import re
from collections import deque
from typing import Optional, List, Dict, Set, Tuple, Any

from ..core import log_info, log_warning, log_error, with_progress, load_asset
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Mappings & Heuristics
# ─────────────────────────────────────────────────────────────────────────────

CLASS_TO_TYPE: Dict[str, str] = {
    # Textures
    "Texture2D": "Textures",
    "TextureCube": "Textures",
    "TextureRenderTarget2D": "Textures",
    # Sounds
    "SoundWave": "Sounds",
    "SoundCue": "Sounds",
    "MetaSoundSource": "Sounds",
    "MetaSoundPatch": "Sounds",
    # Meshes
    "StaticMesh": "Meshes",
    "SkeletalMesh": "Meshes",
    # Materials
    "Material": "Materials",
    "MaterialInstanceConstant": "MaterialInstances",
    "MaterialInstance": "MaterialInstances",
    "MaterialFunction": "MaterialFunctions",
    "MaterialFunctionMaterialLayer": "MaterialFunctions",
    "MaterialParameterCollection": "MaterialParameterCollections",
    # Blueprints
    "Blueprint": "Blueprints",
    "AnimBlueprint": "Blueprints",
    "WidgetBlueprint": "WidgetBlueprints",
    # Niagara & VFX
    "NiagaraSystem": "Niagara",
    "NiagaraEmitter": "Niagara",
    # Animation
    "AnimSequence": "Animations",
    "AnimMontage": "Animations",
    "BlendSpace": "Animations",
    "Skeleton": "Animations",
    "PhysicsAsset": "Animations",
    # Data
    "CurveFloat": "Data",
    "CurveVector": "Data",
    "CurveLinearColor": "Data",
    "DataTable": "Data",
    "PrimaryDataAsset": "Data",
    # Sequences
    "LevelSequence": "LevelSequences",
    "DataLayerAsset": "WorldPartition",
}

CATEGORY_RULES: List[Tuple[str, Set[str]]] = [
    ("Trees", {"tree", "trees", "oak", "pine", "birch", "branch", "stump", "log"}),
    ("Foliage", {"grass", "bush", "fern", "leaf", "shrub", "plant", "ivy", "flower"}),
    ("Rocks", {"rock", "rocks", "stone", "cliff", "boulder", "ore", "pebble"}),
    ("Terrain", {"terrain", "landscape", "ground", "soil", "mud", "sand", "snow", "dirt"}),
    ("Buildings", {"house", "building", "wall", "roof", "door", "window", "tower", "castle"}),
    ("Props", {"prop", "barrel", "crate", "bench", "table", "chair", "lamp", "fence"}),
    ("Roads", {"road", "path", "trail", "bridge", "stairs", "step", "ramp"}),
    ("Water", {"water", "river", "lake", "ocean", "pond", "shore", "wave", "foam"}),
    ("Characters", {"character", "npc", "enemy", "player", "creature", "monster", "humanoid"}),
    ("Weapons", {"weapon", "sword", "bow", "gun", "rifle", "shield", "arrow", "axe"}),
    ("VFX", {"fx", "vfx", "effect", "impact", "explosion", "smoke", "fire", "spark", "dust"}),
    ("UI", {"ui", "widget", "icon", "hud", "menu", "button", "cursor"}),
    ("Music", {"music", "theme", "track", "song", "score"}),
    ("Ambience", {"ambient", "ambience", "wind", "birds", "rain", "waterfall", "forest"}),
    ("SFX", {"sfx", "footstep", "hit", "pickup", "jump", "attack", "swing"}),
    ("Functions", {"function", "functions"}),
    ("Cinematics", {"sequence", "cinematic", "intro", "outro", "cutscene"}),
]

# ─────────────────────────────────────────────────────────────────────────────
#  Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_folder_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_ ]+", "", name or "")
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or "Misc"

def _tokenize_name(name: str) -> List[str]:
    base = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    base = re.sub(r"[_\-\.]+", " ", base)
    return [t.lower() for t in base.split() if t.strip()]

def _guess_category(asset_name: str, asset_type: str) -> str:
    toks = set(_tokenize_name(asset_name))
    for category, keys in CATEGORY_RULES:
        if toks.intersection(keys):
            return category

    # Fallbacks based on type
    if asset_type == "Sounds": return "General"
    if asset_type in ["Textures", "Materials", "MaterialInstances"]: return "Surface"
    if asset_type == "MaterialFunctions": return "Functions"
    if asset_type == "MaterialParameterCollections": return "GlobalParameters"
    if asset_type == "Meshes": return "Props"
    if asset_type == "Blueprints": return "Gameplay"
    if asset_type == "WidgetBlueprints": return "UI"
    if asset_type == "Niagara": return "VFX"
    if asset_type == "Animations": return "Characters"
    if asset_type == "Data": return "General"
    if asset_type == "LevelSequences": return "Cinematics"
    if asset_type == "WorldPartition": return "DataLayers"
    return "Misc"

def _get_current_level_referenced_packages() -> Set[str]:
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        world_path = str(world.get_path_name()).split(".")[0]
    except Exception:
        return set()

    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    visited = set()
    queue = deque([world_path])

    try:
        dep_options = unreal.AssetRegistryDependencyOptions(
            include_soft_package_references=True,
            include_hard_package_references=True,
            include_searchable_names=False,
            include_soft_management_references=True,
            include_hard_management_references=True
        )
    except Exception:
        dep_options = None

    while queue:
        pkg = queue.popleft()
        if not pkg or pkg in visited:
            continue
            
        visited.add(pkg)
        try:
            deps = ar.get_dependencies(pkg, dep_options) if dep_options else ar.get_dependencies(pkg)
            for dep in (deps or []):
                dep_str = str(dep)
                if dep_str and dep_str not in visited:
                    queue.append(dep_str)
        except Exception:
            pass

    return visited

# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="organize_smart_categorize",
    category="Project",
    description="Scan a folder and automatically organize assets functionally (e.g. Meshes/Trees) via smart keyword detection.",
    tags=["organize", "smart", "category", "folder", "heuristic"]
)
def run_smart_categorize(
    scan_path: str = "/Game",
    organized_root: str = "/Game/Organized",
    dry_run: bool = True,
    include_unused: bool = True,
    **kwargs
) -> dict:
    """
    Scans a folder path, detects the asset type, guesses a functional category using regex keywords on the asset name,
    and moves them to a structured destination.
    
    Example: 
      `T_Log_01` -> /Game/Organized/Textures/Trees/T_Log_01
      
    Args:
        scan_path:      Folder to scan for messy assets.
        organized_root: Target baseline folder for the organized assets.
        dry_run:        If True, only prints out the planned moves.
        include_unused: If False, ignores assets that aren't hooked into the current level.
    """
    eal = unreal.EditorAssetLibrary
    if not eal.does_directory_exist(scan_path):
        log_error(f"Scan path does not exist: {scan_path}")
        return {"status": "error", "moved": 0, "failed": 0, "dry_run": dry_run}

    log_info(f"Scanning {scan_path} for smart organization...")
    asset_paths = eal.list_assets(scan_path, recursive=True, include_folder=False)

    if not asset_paths:
        log_info("No assets found.")
        return {"status": "ok", "moved": 0, "failed": 0, "dry_run": dry_run}

    level_refs = None
    if not include_unused:
        log_info("Collating level dependencies (this may take a moment)...")
        level_refs = _get_current_level_referenced_packages()

    plan: List[Dict[str, Any]] = []
    skipped = 0

    for path in asset_paths:
        package_name = path.rsplit(".", 1)[0]
        
        if not include_unused and level_refs and package_name not in level_refs:
            skipped += 1
            continue
            
        if package_name.startswith(organized_root):
            skipped += 1
            continue

        asset_data = eal.find_asset_data(path)
        if not asset_data:
            skipped += 1
            continue

        asset_name = str(asset_data.asset_name)
        class_name = str(asset_data.asset_class_path.asset_name)
        asset_type = CLASS_TO_TYPE.get(class_name, "Other")

        if asset_type == "Other":
            skipped += 1
            continue

        category = _guess_category(asset_name, asset_type)
        dest_dir = f"{organized_root}/{_sanitize_folder_name(asset_type)}/{_sanitize_folder_name(category)}"
        target_path = f"{dest_dir}/{asset_name}.{asset_name}"

        if eal.does_asset_exist(target_path):
            skipped += 1
            continue

        plan.append({
            "source": path,
            "dest_dir": dest_dir,
            "target": target_path,
            "type": asset_type,
            "category": category,
            "name": asset_name
        })

    if not plan:
        log_info(f"No valid assets remaining to organize. (Skipped {skipped})")
        return {"status": "ok", "moved": 0, "failed": 0, "dry_run": dry_run}

    log_info(f"{'[DRY RUN] ' if dry_run else ''}Found {len(plan)} assets to smartly group (Skipped: {skipped}).")

    # Print the first 10 for preview
    for row in plan[:10]:
        log_info(f"  {row['name']:30s} -> {row['dest_dir']}")
    if len(plan) > 10:
        log_info(f"  ... plus {len(plan) - 10} more.")

    if dry_run:
        log_info("\nDry run complete. Pass dry_run=False to execute moves.")
        return {"status": "ok", "moved": 0, "failed": 0, "planned": len(plan), "dry_run": True}

    moved = 0
    failed = 0

    with with_progress(plan, f"Organizing smartly: {organized_root}") as bar:
        for row in bar:
            # We must ensure directory exists, although unreal.EditorAssetLibrary.rename_asset automatically creates directories!
            # It's perfectly safe to just call rename_asset.
            try:
                success = eal.rename_asset(row["source"], row["target"])
                if success:
                    moved += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                log_warning(f"Failed to move {row['name']}: {e}")

    log_info(f"Smart Organization complete. Moved: {moved}, Failed: {failed}.")
    return {"status": "ok", "moved": moved, "failed": failed, "dry_run": False}
