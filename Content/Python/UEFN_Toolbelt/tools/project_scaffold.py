"""
UEFN TOOLBELT — Project Scaffold Generator
========================================
One-click professional Content Browser structure for any UEFN project.
Folder chaos is one of the top creator gripes — this kills it at project start.

Grok said it perfectly: "People will love it — folder organization is one of the
top 'gripes' in asset-heavy Fortnite projects."

FEATURES:
  • Four built-in preset templates:
      - uefn_standard    Full Epic-recommended structure for production projects
      - competitive_map  Streamlined layout for competitive/arena maps
      - solo_dev         Minimal fast-start structure for solo creators
      - verse_heavy      Optimised for Verse-heavy projects with deep module trees
  • Custom project name/prefix applied to every path
  • Dry-run mode — prints every folder that would be created, zero changes
  • Skip-existing safety: never clobbers work already in place
  • Save any structure as a named JSON template to reuse or share with team
  • Load a template from JSON and generate its folder tree
  • Auto-organise: move loose assets in /Game root into the new structure
  • Progress bar on large trees
  • Detailed creation log saved to Saved/UEFN_Toolbelt/scaffold_log.json

NOTE ON UNDO:
  Folder creation is a filesystem operation — it cannot be rolled back by
  ScopedEditorTransaction. The tool is intentionally non-destructive:
  it only CREATES folders, never deletes or moves anything without explicit
  opt-in. Use dry_run=True to preview before committing.

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Preview the full standard structure — zero changes
    tb.run("scaffold_preview", template="uefn_standard", project_name="MyIsland")

    # Generate the standard structure under /Game/MyIsland
    tb.run("scaffold_generate", template="uefn_standard", project_name="MyIsland")

    # Generate a competitive map structure
    tb.run("scaffold_generate", template="competitive_map", project_name="Arena_01")

    # Save your current custom structure as a reusable team template
    tb.run("scaffold_save_template",
           template_name="StudioDefault",
           folders=[
               "Maps/MainIsland",
               "Materials/Master",
               "Materials/Instances",
               "Meshes/Props",
               "Verse/Modules",
           ])

    # Generate from a saved custom template
    tb.run("scaffold_generate", template="StudioDefault", project_name="NewProject")

    # List all available templates (built-in + saved)
    tb.run("scaffold_list_templates")

    # Auto-organize loose assets already sitting in /Game root
    tb.run("scaffold_organize_loose", project_name="MyIsland")

BLUEPRINT:
    "Execute Python Command" →
        import UEFN_Toolbelt as tb; tb.run("scaffold_generate", template="uefn_standard", project_name="MyProject")
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import unreal

from ..core import (
    log_info, log_warning, log_error,
    load_asset, with_progress,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Template storage
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES_FILE = os.path.join(
    unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "scaffold_templates.json"
)

# ─────────────────────────────────────────────────────────────────────────────
#  Built-in structure templates
#  Each entry is a list of folder paths relative to the project root.
#  Use {project} as a placeholder — it gets replaced with project_name.
# ─────────────────────────────────────────────────────────────────────────────

BUILTIN_TEMPLATES: Dict[str, List[str]] = {

    # ── Full production structure (Epic-recommended + community best practices)
    "uefn_standard": [
        "_Dev",
        "_Dev/Sandbox",
        "_Dev/TestLevels",
        "Maps",
        "Maps/MainIsland",
        "Maps/SubLevels",
        "Maps/Backups",
        "Materials",
        "Materials/Master",
        "Materials/Instances",
        "Materials/Presets",
        "Materials/Functions",
        "Meshes",
        "Meshes/Props",
        "Meshes/Props/Small",
        "Meshes/Props/Large",
        "Meshes/Buildings",
        "Meshes/Buildings/Walls",
        "Meshes/Buildings/Floors",
        "Meshes/Buildings/Roofs",
        "Meshes/Nature",
        "Meshes/Nature/Trees",
        "Meshes/Nature/Rocks",
        "Meshes/Nature/Ground",
        "Meshes/Weapons",
        "Meshes/Characters",
        "Blueprints",
        "Blueprints/Devices",
        "Blueprints/Utilities",
        "Blueprints/UI",
        "Verse",
        "Verse/Modules",
        "Verse/Generated",
        "Verse/Shared",
        "Audio",
        "Audio/Music",
        "Audio/SFX",
        "Audio/Ambience",
        "Audio/UI",
        "UI",
        "UI/Widgets",
        "UI/HUD",
        "UI/Menus",
        "UI/Icons",
        "FX",
        "FX/Niagara",
        "FX/Particles",
        "FX/Decals",
        "Textures",
        "Textures/Base",
        "Textures/Normal",
        "Textures/Atlases",
        "Textures/UI",
        "DataTables",
        "DataTables/Items",
        "DataTables/Config",
    ],

    # ── Streamlined layout for competitive / arena maps
    "competitive_map": [
        "_Dev",
        "Maps",
        "Maps/Arena",
        "Maps/TestArena",
        "Materials",
        "Materials/TeamRed",
        "Materials/TeamBlue",
        "Materials/Neutral",
        "Materials/Instances",
        "Meshes",
        "Meshes/Arena",
        "Meshes/Arena/Floor",
        "Meshes/Arena/Walls",
        "Meshes/Arena/Cover",
        "Meshes/Arena/Spawns",
        "Meshes/Props",
        "Blueprints",
        "Blueprints/Devices",
        "Verse",
        "Verse/GameLogic",
        "Verse/Scoring",
        "Verse/Teams",
        "Audio",
        "Audio/SFX",
        "Audio/Music",
        "FX",
        "FX/Niagara",
    ],

    # ── Minimal fast-start for solo creators
    "solo_dev": [
        "_WIP",
        "Maps",
        "Materials",
        "Materials/Instances",
        "Meshes",
        "Meshes/Props",
        "Blueprints",
        "Verse",
        "Audio",
        "FX",
        "Textures",
    ],

    # ── Deep Verse project structure
    "verse_heavy": [
        "_Dev",
        "Maps",
        "Maps/Main",
        "Maps/TestLevels",
        "Materials",
        "Materials/Instances",
        "Meshes",
        "Meshes/Props",
        "Blueprints",
        "Blueprints/Devices",
        "Verse",
        "Verse/Core",
        "Verse/Core/GameState",
        "Verse/Core/PlayerSystems",
        "Verse/Core/Teams",
        "Verse/Devices",
        "Verse/Devices/Scoring",
        "Verse/Devices/Spawning",
        "Verse/Devices/UI",
        "Verse/Data",
        "Verse/Data/Tables",
        "Verse/Data/Configs",
        "Verse/Generated",
        "Verse/Shared",
        "Verse/Tests",
        "Audio",
        "Audio/SFX",
        "UI",
        "UI/Widgets",
        "FX",
        "DataTables",
    ],
}

# Maps asset class names to destination sub-folder names (for auto-organize)
_ASSET_FOLDER_MAP = {
    "StaticMesh":                "Meshes/Props",
    "SkeletalMesh":              "Meshes/Characters",
    "Material":                  "Materials/Master",
    "MaterialInstanceConstant":  "Materials/Instances",
    "Texture2D":                 "Textures/Base",
    "SoundWave":                 "Audio/SFX",
    "SoundCue":                  "Audio/SFX",
    "Blueprint":                 "Blueprints",
    "WidgetBlueprint":           "UI/Widgets",
    "NiagaraSystem":             "FX/Niagara",
    "ParticleSystem":            "FX/Particles",
    "DataTable":                 "DataTables",
    "AnimSequence":              "Meshes/Characters",
}

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_custom_templates() -> Dict[str, List[str]]:
    if not os.path.exists(TEMPLATES_FILE):
        return {}
    try:
        with open(TEMPLATES_FILE) as f:
            return json.load(f)
    except Exception as e:
        log_error(f"scaffold: could not read templates file: {e}")
        return {}


def _save_custom_templates(data: Dict[str, List[str]]) -> None:
    os.makedirs(os.path.dirname(TEMPLATES_FILE), exist_ok=True)
    with open(TEMPLATES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _all_templates() -> Dict[str, List[str]]:
    merged = dict(BUILTIN_TEMPLATES)
    merged.update(_load_custom_templates())
    return merged


def _resolve_paths(folders: List[str], project_name: str, base: str) -> List[str]:
    """Build full /Game/ content paths from relative folder list."""
    root = f"{base}/{project_name}" if project_name else base
    return [f"{root}/{f}" for f in folders]


def _create_folder(path: str) -> str:
    """
    Create a single Content Browser folder.
    Returns "created", "exists", or "failed".
    """
    if unreal.EditorAssetLibrary.does_directory_exist(path):
        return "exists"
    try:
        ok = unreal.EditorAssetLibrary.make_directory(path)
        return "created" if ok else "failed"
    except Exception as e:
        log_warning(f"  Could not create '{path}': {e}")
        return "failed"


def _write_log(records: list, project_name: str) -> str:
    out_dir  = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "scaffold_log.json")
    entry = {
        "timestamp":    datetime.now().isoformat(),
        "project_name": project_name,
        "records":      records,
    }
    existing = []
    if os.path.exists(path):
        try:
            with open(path) as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.append(entry)
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    return path


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="scaffold_list_templates",
    category="Project",
    description="List all available project scaffold templates (built-in + saved).",
    tags=["scaffold", "folder", "template", "list", "project"],
)
def run_list_templates(**kwargs) -> dict:
    """
    Returns:
        dict: {"status", "count", "templates": {name: {"folder_count", "source"}}}
    """
    templates = _all_templates()
    lines = ["\n=== Scaffold Templates ==="]
    result_templates = {}
    for name, folders in templates.items():
        source = "built-in" if name in BUILTIN_TEMPLATES else "custom"
        lines.append(f"  {name:20s}  ({len(folders)} folders)  [{source}]")
        result_templates[name] = {"folder_count": len(folders), "source": source}
    lines.append(
        "\nUsage: tb.run('scaffold_generate', template='<name>', project_name='MyProject')"
    )
    log_info("\n".join(lines))
    return {"status": "ok", "count": len(templates), "templates": result_templates}


@register_tool(
    name="scaffold_preview",
    category="Project",
    description="Preview a scaffold template — prints every folder that would be created.",
    tags=["scaffold", "folder", "preview", "dry-run", "project"],
)
def run_scaffold_preview(
    template: str = "uefn_standard",
    project_name: str = "MyProject",
    base: str = "/Game",
    **kwargs,
) -> dict:
    """
    Zero-change preview. Shows exactly what scaffold_generate would create.

    Args:
        template:     Template name. See scaffold_list_templates for options.
        project_name: Your project/island name (used as the root subfolder).
        base:         Content Browser base path (default: /Game).
    """
    all_t = _all_templates()
    if template not in all_t:
        log_error(f"Unknown template '{template}'. Run scaffold_list_templates to see options.")
        return {"status": "error", "paths": [], "new_count": 0, "exists_count": 0}

    paths = _resolve_paths(all_t[template], project_name, base)
    root  = f"{base}/{project_name}" if project_name else base

    lines = [
        f"\n=== Scaffold Preview: '{template}' → {root} ===",
        f"  {len(paths)} folders would be created:\n",
    ]

    for path in paths:
        exists = unreal.EditorAssetLibrary.does_directory_exist(path)
        status = "  (already exists — will skip)" if exists else ""
        lines.append(f"  {path}{status}")

    new_count = sum(
        1 for p in paths
        if not unreal.EditorAssetLibrary.does_directory_exist(p)
    )
    lines.append(f"\n  New folders: {new_count}  |  Already existing: {len(paths) - new_count}")
    lines.append("  Run scaffold_generate to create.")

    log_info("\n".join(lines))
    return {"status": "ok", "paths": paths, "new_count": new_count,
            "exists_count": len(paths) - new_count}


@register_tool(
    name="scaffold_generate",
    category="Project",
    description="Generate a professional Content Browser folder structure from a template.",
    shortcut="Ctrl+Alt+P",
    tags=["scaffold", "folder", "generate", "structure", "project", "organize"],
)
def run_scaffold_generate(
    template: str = "uefn_standard",
    project_name: str = "MyProject",
    base: str = "/Game",
    **kwargs,
) -> dict:
    """
    Creates the full folder tree for the chosen template.
    Existing folders are silently skipped — nothing is overwritten or deleted.

    Args:
        template:     Template name. Run scaffold_list_templates to see all options.
        project_name: Your project/island name (becomes the root subfolder).
        base:         Content Browser base path (default: /Game).

    Example results:
        /Game/MyProject/
        /Game/MyProject/Maps/
        /Game/MyProject/Maps/MainIsland/
        /Game/MyProject/Materials/Master/
        ...
    """
    all_t = _all_templates()
    if template not in all_t:
        log_error(f"Unknown template '{template}'. Run scaffold_list_templates.")
        return {"status": "error", "created": 0, "skipped": 0, "failed": 0, "log_path": ""}

    paths   = _resolve_paths(all_t[template], project_name, base)
    root    = f"{base}/{project_name}" if project_name else base

    log_info(f"Generating '{template}' structure under {root} ({len(paths)} folders)…")

    records    = []
    created    = 0
    skipped    = 0
    failed     = 0

    # Note: folder creation is a filesystem op — not wrapped in ScopedEditorTransaction
    # because folder creation cannot be undone via the transaction system.
    # The tool is safe: it only creates, never deletes.
    with with_progress(paths, f"Creating folder structure: {project_name}") as bar:
        for path in bar:
            status = _create_folder(path)
            records.append({"path": path, "status": status})
            if status == "created":
                created += 1
                log_info(f"  ✓ {path}")
            elif status == "exists":
                skipped += 1
            else:
                failed += 1

    log_path = _write_log(records, project_name)
    log_info(
        f"\nScaffold complete for '{project_name}':\n"
        f"  Created: {created}  |  Already existed: {skipped}  |  Failed: {failed}\n"
        f"  Log → {log_path}\n"
        f"  Refresh Content Browser: right-click any folder → Refresh"
    )
    return {"status": "ok", "created": created, "skipped": skipped,
            "failed": failed, "log_path": log_path}


@register_tool(
    name="scaffold_save_template",
    category="Project",
    description="Save a custom folder list as a named reusable scaffold template.",
    tags=["scaffold", "template", "save", "custom", "project"],
)
def run_scaffold_save_template(
    template_name: str = "MyTemplate",
    folders: Optional[List[str]] = None,
    **kwargs,
) -> dict:
    """
    Save a list of relative folder paths as a named template.
    The template is stored in Saved/UEFN_Toolbelt/scaffold_templates.json
    and can be shared with teammates by copying that file.

    Args:
        template_name: Key to save the template under.
        folders:       List of relative paths, e.g. ["Maps/Main", "Materials/Master"].

    Example:
        tb.run("scaffold_save_template",
               template_name="StudioDefault",
               folders=[
                   "Maps/MainIsland",
                   "Materials/Master",
                   "Materials/Instances",
                   "Meshes/Props",
                   "Verse/Modules",
                   "Audio/SFX",
               ])
    """
    if not folders:
        log_error("scaffold_save_template: 'folders' list is required.")
        return {"status": "error", "name": template_name, "folder_count": 0}

    if template_name in BUILTIN_TEMPLATES:
        log_error(f"'{template_name}' is a built-in template name — choose a different name.")
        return {"status": "error", "name": template_name, "folder_count": 0}

    customs = _load_custom_templates()
    customs[template_name] = folders
    _save_custom_templates(customs)
    log_info(f"Template '{template_name}' saved ({len(folders)} folders) → {TEMPLATES_FILE}")
    return {"status": "ok", "name": template_name, "folder_count": len(folders)}


@register_tool(
    name="scaffold_delete_template",
    category="Project",
    description="Delete a saved custom scaffold template by name.",
    tags=["scaffold", "template", "delete", "custom"],
)
def run_scaffold_delete_template(template_name: str = "", **kwargs) -> dict:
    """
    Args:
        template_name: Name of the custom template to remove.
                       Built-in templates cannot be deleted.
    """
    if not template_name:
        log_error("scaffold_delete_template: template_name is required.")
        return {"status": "error", "name": template_name}

    if template_name in BUILTIN_TEMPLATES:
        log_error(f"'{template_name}' is a built-in template — cannot be deleted.")
        return {"status": "error", "name": template_name}

    customs = _load_custom_templates()
    if template_name not in customs:
        log_warning(f"Template '{template_name}' not found.")
        return {"status": "error", "name": template_name}

    del customs[template_name]
    _save_custom_templates(customs)
    log_info(f"Template '{template_name}' deleted.")
    return {"status": "ok", "name": template_name}


@register_tool(
    name="scaffold_organize_loose",
    category="Project",
    description="Move loose assets from /Game root into the project's folder structure.",
    tags=["scaffold", "organize", "loose", "assets", "move", "project"],
)
def run_scaffold_organize_loose(
    project_name: str = "MyProject",
    base: str = "/Game",
    dry_run: bool = True,
    **kwargs,
) -> dict:
    """
    Scans /Game (top level only, not recursive) for assets sitting loose
    in the root and moves them into the appropriate subfolder of your project.

    Folder mapping (by asset class):
        StaticMesh           → Meshes/Props
        Material             → Materials/Master
        MaterialInstance     → Materials/Instances
        Texture2D            → Textures/Base
        SoundWave/SoundCue   → Audio/SFX
        Blueprint            → Blueprints
        NiagaraSystem        → FX/Niagara
        DataTable            → DataTables

    Defaults to dry_run=True — always preview before committing moves.

    Args:
        project_name: The root subfolder (must already exist from scaffold_generate).
        base:         Content Browser base (default: /Game).
        dry_run:      If True, print moves without executing them.
    """
    root = f"{base}/{project_name}"

    if not unreal.EditorAssetLibrary.does_directory_exist(root):
        log_error(
            f"Project root '{root}' does not exist. "
            f"Run scaffold_generate first."
        )
        return {"status": "error", "moved": 0, "failed": 0, "dry_run": dry_run}

    # Scan only the immediate /Game level (not recursive) for loose assets
    loose_paths = unreal.EditorAssetLibrary.list_assets(
        base, recursive=False, include_folder=False
    )

    if not loose_paths:
        log_info("No loose assets found in /Game root.")
        return {"status": "ok", "moved": 0, "failed": 0, "dry_run": dry_run}

    moves: list[tuple[str, str]] = []
    unmatched: list[str] = []

    for asset_path in loose_paths:
        asset = load_asset(asset_path)
        if asset is None:
            continue
        class_name = asset.get_class().get_name()
        dest_sub   = _ASSET_FOLDER_MAP.get(class_name)
        if dest_sub:
            asset_name = asset_path.split("/")[-1]
            dest_path  = f"{root}/{dest_sub}/{asset_name}"
            moves.append((asset_path, dest_path))
        else:
            unmatched.append(f"{asset_path.split('/')[-1]}  [{class_name}]")

    if not moves:
        log_info("No loose assets matched a destination folder.")
        return {"status": "ok", "moved": 0, "failed": 0, "dry_run": dry_run}

    prefix = "[DRY RUN] " if dry_run else ""
    log_info(f"{prefix}Found {len(moves)} loose assets to organize:")
    for src, dst in moves:
        log_info(f"  {src.split('/')[-1]}  →  {dst}")

    if unmatched:
        log_info(f"  Skipped (no mapping): {', '.join(unmatched)}")

    if dry_run:
        log_info("Dry run — no changes made. Pass dry_run=False to execute moves.")
        return {"status": "ok", "moved": len(moves), "failed": 0, "dry_run": True}

    done = failed = 0
    for src, dst in moves:
        try:
            unreal.EditorAssetLibrary.rename_asset(src, dst)
            done += 1
        except Exception as e:
            log_warning(f"  Failed to move {src.split('/')[-1]}: {e}")
            failed += 1

    log_info(f"Organized {done} assets, {failed} failed.")
    return {"status": "ok", "moved": done, "failed": failed, "dry_run": False}
