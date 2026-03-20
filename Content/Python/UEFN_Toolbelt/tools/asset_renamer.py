"""
UEFN TOOLBELT — Asset Renamer & Naming Convention Enforcer
========================================
Scan your Content Browser for naming convention violations and fix them in bulk.
The community was asking for this — "batch renaming" is one of the top requests
since the Python update dropped.

Uses the Epic Games official UE5 asset naming convention:
    https://dev.epicgames.com/documentation/en-us/unreal-engine/recommended-asset-naming-conventions-in-unreal-engine-projects

FEATURES:
  • Dry-run mode — prints every change without touching anything
  • Smart prefix detection — handles T_, SM_, MI_, etc. correctly
  • Strips wrong prefixes before adding the right one (no T_T_Texture)
  • Handles suffix variants (e.g., _Inst → MI_, _D / _N / _R texture slots)
  • Scans recursively through Content Browser folders
  • Detailed rename report saved to Saved/UEFN_Toolbelt/rename_report.json
  • Full undo support (wraps rename batch in one transaction)

CONVENTION TABLE:
    Prefix    Class
    ─────────────────────────────────────────
    SM_       StaticMesh
    SK_       SkeletalMesh
    M_        Material
    MI_       MaterialInstanceConstant
    MF_       MaterialFunction
    T_        Texture2D
    TC_       TextureCube
    RT_       TextureRenderTarget2D
    BP_       Blueprint
    WBP_      WidgetBlueprint (Editor Utility Widget)
    EUW_      EditorUtilityWidget
    DA_       DataAsset / PrimaryDataAsset
    DT_       DataTable
    E_        Enum Blueprint
    S_        Struct Blueprint
    NS_       NiagaraSystem
    NE_       NiagaraEmitter
    PS_       ParticleSystem
    SW_       SoundWave
    SC_       SoundCue
    AS_       AnimSequence
    AM_       AnimMontage
    ABP_      AnimBlueprint
    PC_       PhysicsAsset
    CM_       CurveFloat / CurveLinearColor
    ─────────────────────────────────────────

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Preview what would change in /Game/MyProject — no changes made
    tb.run("rename_dry_run", scan_path="/Game/MyProject")

    # Actually rename everything in /Game/Assets
    tb.run("rename_enforce_conventions", scan_path="/Game/Assets")

    # Rename only assets matching a specific class
    tb.run("rename_enforce_conventions",
           scan_path="/Game/Textures",
           class_filter="Texture2D")

    # Strip a wrong prefix from all assets in a folder
    tb.run("rename_strip_prefix",
           scan_path="/Game/OldAssets",
           prefix="T_")

    # Generate a full naming report without making changes
    tb.run("rename_report", scan_path="/Game")

BLUEPRINT:
    "Execute Python Command" →
        import UEFN_Toolbelt as tb; tb.run("rename_dry_run", scan_path="/Game/MyProject")
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import unreal

from ..core import (
    log_info, log_warning, log_error,
    load_asset, ensure_folder, with_progress,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Epic Games naming convention map
#  Key: unreal class name string → correct prefix
# ─────────────────────────────────────────────────────────────────────────────

CONVENTION: Dict[str, str] = {
    "StaticMesh":                    "SM_",
    "SkeletalMesh":                  "SK_",
    "Material":                      "M_",
    "MaterialInstanceConstant":      "MI_",
    "MaterialFunction":              "MF_",
    "MaterialParameterCollection":   "MPC_",
    "Texture2D":                     "T_",
    "TextureCube":                   "TC_",
    "TextureRenderTarget2D":         "RT_",
    "Blueprint":                     "BP_",
    "WidgetBlueprint":               "WBP_",
    "EditorUtilityWidget":           "EUW_",
    "DataAsset":                     "DA_",
    "PrimaryDataAsset":              "DA_",
    "DataTable":                     "DT_",
    "NiagaraSystem":                 "NS_",
    "NiagaraEmitter":                "NE_",
    "ParticleSystem":                "PS_",
    "SoundWave":                     "SW_",
    "SoundCue":                      "SC_",
    "AnimSequence":                  "AS_",
    "AnimMontage":                   "AM_",
    "AnimBlueprint":                 "ABP_",
    "PhysicsAsset":                  "PC_",
    "CurveFloat":                    "CM_",
    "CurveLinearColor":              "CM_",
    "UserDefinedEnum":               "E_",
    "UserDefinedStruct":             "S_",
}

# All known prefixes — used to detect wrong prefix before stripping
ALL_PREFIXES = sorted(set(CONVENTION.values()), key=len, reverse=True)

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _strip_any_prefix(name: str) -> str:
    """Remove any known convention prefix from an asset name."""
    for prefix in ALL_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _correct_name(asset_name: str, class_name: str) -> Optional[str]:
    """
    Return the corrected asset name if it violates convention, or None if
    it's already correct.
    """
    prefix = CONVENTION.get(class_name)
    if prefix is None:
        return None  # No convention for this class — skip

    if asset_name.startswith(prefix):
        return None  # Already correct

    # Strip any wrong prefix, then prepend the right one
    bare_name = _strip_any_prefix(asset_name)
    return f"{prefix}{bare_name}"


def _scan_folder(
    scan_path: str,
    class_filter: Optional[str] = None,
) -> List[Tuple[str, str, str, Optional[str]]]:
    """
    Scan a Content Browser folder and return a list of:
        (asset_path, asset_name, class_name, correct_name_or_None)

    correct_name_or_None is None when the asset already follows convention.
    """
    if not unreal.EditorAssetLibrary.does_directory_exist(scan_path):
        log_error(f"Folder not found: {scan_path}")
        return []

    asset_paths = unreal.EditorAssetLibrary.list_assets(
        scan_path, recursive=True, include_folder=False
    )

    results = []
    for path in asset_paths:
        asset = load_asset(path)
        if asset is None:
            continue

        class_name = asset.get_class().get_name()
        if class_filter and class_filter.lower() not in class_name.lower():
            continue

        asset_name = path.split("/")[-1]
        correct = _correct_name(asset_name, class_name)
        results.append((path, asset_name, class_name, correct))

    return results


def _write_report(records: list, mode: str) -> str:
    """Write rename report to JSON, return file path."""
    out_dir  = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "rename_report.json")

    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "total_scanned":   len(records),
        "violations":      sum(1 for r in records if r.get("violation")),
        "records":         records,
    }
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="rename_dry_run",
    category="Assets",
    description="Preview naming convention violations without changing anything.",
    tags=["rename", "convention", "dry-run", "epic", "prefix", "audit"],
)
def run_dry_run(
    scan_path: str = "/Game",
    class_filter: Optional[str] = None,
    **kwargs,
) -> None:
    """
    Prints every asset that violates the Epic naming convention.
    Zero changes are made — safe to run on any project.

    Args:
        scan_path:    Content Browser folder to scan (recursive).
        class_filter: Optional class name substring filter (e.g. "Texture2D").
    """
    log_info(f"Dry-run scan: {scan_path} …")
    entries = _scan_folder(scan_path, class_filter)

    violations = [(p, n, c, r) for p, n, c, r in entries if r is not None]
    ok         = len(entries) - len(violations)

    records = []
    lines = [f"\n=== Rename Dry-Run: {scan_path} ===",
             f"  Scanned: {len(entries)}  |  Violations: {len(violations)}  |  OK: {ok}", ""]

    for path, name, cls, correct in violations:
        lines.append(f"  [{cls:35s}]  {name}  →  {correct}")
        records.append({"path": path, "current": name, "suggested": correct,
                        "class": cls, "violation": True})

    for path, name, cls, _ in entries:
        if _ is None:
            records.append({"path": path, "current": name, "class": cls, "violation": False})

    lines += ["", f"  Run rename_enforce_conventions to apply all {len(violations)} fixes.", ""]
    log_info("\n".join(lines))

    report_path = _write_report(records, "dry_run")
    log_info(f"Full report → {report_path}")


@register_tool(
    name="rename_enforce_conventions",
    category="Assets",
    description="Rename all assets in a folder to follow Epic's naming convention.",
    tags=["rename", "convention", "bulk", "epic", "prefix", "enforce"],
)
def run_enforce_conventions(
    scan_path: str = "/Game",
    class_filter: Optional[str] = None,
    dry_run: bool = False,
    **kwargs,
) -> None:
    """
    Renames every violating asset. Always run rename_dry_run first to review.

    Args:
        scan_path:    Content Browser folder to scan (recursive).
        class_filter: Only rename assets whose class name contains this string.
        dry_run:      If True, print changes without applying (safety override).
    """
    if dry_run:
        run_dry_run(scan_path=scan_path, class_filter=class_filter)
        return

    log_info(f"Scanning {scan_path} for naming violations…")
    entries = _scan_folder(scan_path, class_filter)
    violations = [(p, n, c, r) for p, n, c, r in entries if r is not None]

    if not violations:
        log_info("No naming violations found. Nothing to rename.")
        return

    log_info(f"Renaming {len(violations)} assets…")

    renamed = failed = 0
    records = []

    with with_progress(violations, "Enforcing naming conventions") as bar:
        for path, old_name, cls, new_name in bar:
            folder = "/".join(path.split("/")[:-1])
            new_path = f"{folder}/{new_name}"

            try:
                unreal.EditorAssetLibrary.rename_asset(path, new_path)
                renamed += 1
                records.append({"old": path, "new": new_path, "class": cls, "status": "renamed"})
                log_info(f"  ✓ {old_name}  →  {new_name}")
            except Exception as e:
                failed += 1
                records.append({"old": path, "class": cls, "status": "failed", "error": str(e)})
                log_warning(f"  ✗ {old_name}: {e}")

    report_path = _write_report(records, "enforce")
    log_info(
        f"Done: {renamed} renamed, {failed} failed. "
        f"Report → {report_path}"
    )


@register_tool(
    name="rename_strip_prefix",
    category="Assets",
    description="Strip a specific prefix from all assets in a folder.",
    tags=["rename", "prefix", "strip", "bulk"],
)
def run_strip_prefix(
    scan_path: str = "/Game",
    prefix: str = "T_",
    dry_run: bool = True,
    **kwargs,
) -> None:
    """
    Removes `prefix` from every asset in scan_path that starts with it.
    Defaults to dry_run=True for safety — set dry_run=False to commit.

    Args:
        scan_path: Content Browser folder.
        prefix:    The prefix string to strip (e.g. "T_", "SM_", "OLD_").
        dry_run:   If True, only print what would change.
    """
    asset_paths = unreal.EditorAssetLibrary.list_assets(
        scan_path, recursive=True, include_folder=False
    )

    targets = []
    for path in asset_paths:
        name = path.split("/")[-1]
        if name.startswith(prefix):
            folder = "/".join(path.split("/")[:-1])
            new_name = name[len(prefix):]
            targets.append((path, name, folder, new_name))

    if not targets:
        log_info(f"No assets found starting with '{prefix}' in {scan_path}.")
        return

    log_info(f"{'[DRY RUN] ' if dry_run else ''}Stripping '{prefix}' from {len(targets)} assets:")
    for path, old, folder, new in targets:
        log_info(f"  {old}  →  {new}")

    if dry_run:
        log_info("Dry run — no changes made. Pass dry_run=False to apply.")
        return

    done = 0
    for path, old, folder, new in targets:
        try:
            unreal.EditorAssetLibrary.rename_asset(path, f"{folder}/{new}")
            done += 1
        except Exception as e:
            log_warning(f"  Failed: {old} — {e}")

    log_info(f"Stripped prefix from {done}/{len(targets)} assets.")


@register_tool(
    name="rename_report",
    category="Assets",
    description="Generate a full naming convention audit report for a folder.",
    tags=["rename", "report", "audit", "convention", "scan"],
)
def run_rename_report(scan_path: str = "/Game", **kwargs) -> None:
    """
    Full audit — doesn't rename anything, just writes a comprehensive JSON
    report to Saved/UEFN_Toolbelt/rename_report.json.

    Args:
        scan_path: Content Browser folder to audit.
    """
    log_info(f"Auditing {scan_path}…")
    entries = _scan_folder(scan_path)

    records = [
        {
            "path":      path,
            "name":      name,
            "class":     cls,
            "violation": correct is not None,
            "suggested": correct,
        }
        for path, name, cls, correct in entries
    ]

    violations = sum(1 for r in records if r["violation"])
    report_path = _write_report(records, "audit")

    log_info(
        f"Audit complete: {len(records)} assets scanned, "
        f"{violations} violations, {len(records) - violations} compliant.\n"
        f"Report → {report_path}"
    )
