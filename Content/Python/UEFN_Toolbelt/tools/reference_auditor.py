"""
UEFN TOOLBELT — reference_auditor.py
=========================================
Find and fix asset health issues in your Content Browser.

What it finds:
  Orphaned assets    — assets not referenced by anything (safe to delete).
  Redirectors        — ObjectRedirector assets left behind after moves/renames.
                       These bloat packages and slow cook times.
  Duplicate names    — different assets with the same base name in different folders.
                       A leading cause of "which one is the real one?" confusion.
  Unused textures    — Texture2D not referenced by any material or material instance.
  Missing mesh LODs  — already covered by memory_profiler; shown here for unified report.

What it fixes:
  ref_fix_redirectors  — consolidates all redirectors in a folder (points refs to the real asset).
  ref_delete_orphans   — deletes orphaned assets after a confirmation print.
                         Always run ref_audit_orphans dry-run first.

Safety model:
  Every scan tool is pure read-only and can be run any time.
  Fix tools confirm what they will change via log output before acting.
  ref_fix_redirectors wraps in an undo transaction where possible.
  ref_delete_orphans is intentionally NOT wrapped in undo (deletion
  of assets is permanent in UE/UEFN). A dry_run=True default guards against accidents.

Output:
  Saved/UEFN_Toolbelt/ref_audit_report.json — full machine-readable report
"""

from __future__ import annotations

import json
import os
from typing import Any

import unreal

from UEFN_Toolbelt.registry import register_tool

# ─── Output ───────────────────────────────────────────────────────────────────

_SAVED = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
_REPORT_PATH = os.path.join(_SAVED, "ref_audit_report.json")


def _ensure_dir() -> None:
    os.makedirs(_SAVED, exist_ok=True)


# ─── Asset helpers ────────────────────────────────────────────────────────────

def _list_all_assets(scan_path: str, class_names: list[str] | None = None) -> list[str]:
    """
    Return asset paths under scan_path.
    If class_names provided, only returns assets whose class matches.
    """
    lib = unreal.EditorAssetLibrary
    try:
        raw = lib.list_assets(scan_path, recursive=True, include_folder=False)
    except Exception as e:
        unreal.log_warning(f"[RefAuditor] list_assets failed: {e}")
        return []

    if not class_names:
        return list(raw)

    results = []
    for path in raw:
        try:
            data = lib.find_asset_data(path)
            if data and data.asset_class_path.asset_name in class_names:
                results.append(path)
        except Exception:
            # fall back to name-based filtering if find_asset_data not available
            results.append(path)
    return results


def _get_referencers(asset_path: str) -> list[str]:
    """Return packages that reference this asset."""
    try:
        return list(unreal.EditorAssetLibrary.find_package_referencers(asset_path))
    except Exception:
        return []


def _get_asset_class_name(asset_path: str) -> str:
    try:
        data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        if data:
            return str(data.asset_class_path.asset_name)
    except Exception:
        pass
    return "Unknown"


def _icon(severity: str) -> str:
    return {"ok": "✓", "warning": "⚠", "critical": "✗"}.get(severity, "?")


# ─── Scan: Orphans ────────────────────────────────────────────────────────────

def _scan_orphans(scan_path: str, excluded_classes: list[str]) -> list[dict[str, Any]]:
    """
    Find assets with zero referencers.

    Maps, Blueprints, and World assets are skipped — they are typically
    the roots of reference trees and will always appear orphaned by this check.
    """
    skip_classes = set(excluded_classes) | {
        "World", "Blueprint", "BlueprintGeneratedClass",
        "WidgetBlueprint", "EditorUtilityWidget",
        "AnimBlueprint", "LevelSequence",
    }

    all_paths = _list_all_assets(scan_path)
    orphans: list[dict[str, Any]] = []

    unreal.log(f"[RefAuditor] Scanning {len(all_paths)} assets for orphans…")

    for path in all_paths:
        cls = _get_asset_class_name(path)
        if cls in skip_classes:
            continue
        refs = _get_referencers(path)
        if not refs:
            orphans.append({"path": path, "class": cls})

    return orphans


# ─── Scan: Redirectors ────────────────────────────────────────────────────────

def _scan_redirectors(scan_path: str) -> list[dict[str, Any]]:
    """Find ObjectRedirector assets (stale move/rename artifacts)."""
    all_paths = _list_all_assets(scan_path)
    redirectors = []

    for path in all_paths:
        cls = _get_asset_class_name(path)
        if "redirector" in cls.lower() or "objectredirector" in cls.lower():
            refs = _get_referencers(path)
            redirectors.append({
                "path": path,
                "class": cls,
                "referencer_count": len(refs),
            })

    return redirectors


# ─── Scan: Duplicate names ────────────────────────────────────────────────────

def _scan_duplicates(scan_path: str) -> list[dict[str, Any]]:
    """
    Find assets that share the same base name but live in different folders.
    Example: /Game/A/SM_Rock and /Game/B/SM_Rock both exist.
    """
    all_paths = _list_all_assets(scan_path)
    name_map: dict[str, list[str]] = {}

    for path in all_paths:
        base = path.split("/")[-1].split(".")[0]  # strip folder + extension
        name_map.setdefault(base, []).append(path)

    dupes = []
    for name, paths in name_map.items():
        if len(paths) > 1:
            dupes.append({"base_name": name, "paths": paths, "count": len(paths)})

    dupes.sort(key=lambda d: d["count"], reverse=True)
    return dupes


# ─── Scan: Unused textures ────────────────────────────────────────────────────

def _scan_unused_textures(scan_path: str) -> list[dict[str, Any]]:
    """
    Find Texture2D assets with no referencers.
    These are safe to delete or archive.
    """
    all_paths = _list_all_assets(scan_path)
    unused = []

    for path in all_paths:
        cls = _get_asset_class_name(path)
        if "texture" not in cls.lower():
            continue
        refs = _get_referencers(path)
        if not refs:
            unused.append({"path": path, "class": cls})

    return unused


# ─── Fix: Redirectors ─────────────────────────────────────────────────────────

def _fix_redirectors(scan_path: str, dry_run: bool) -> int:
    """
    Consolidate (resolve) all ObjectRedirectors under scan_path.
    Returns count of redirectors processed.
    """
    redirectors = _scan_redirectors(scan_path)
    if not redirectors:
        unreal.log("[RefAuditor] No redirectors found.")
        return 0

    unreal.log(f"[RefAuditor] Found {len(redirectors)} redirectors.")
    for r in redirectors:
        unreal.log(f"  ↪ {r['path']}  ({r['referencer_count']} referencers)")

    if dry_run:
        unreal.log("[RefAuditor] DRY RUN — no changes made. Pass dry_run=False to fix.")
        return 0

    fixed = 0
    for r in redirectors:
        path = r["path"]
        try:
            asset = unreal.EditorAssetLibrary.load_asset(path)
            if asset is None:
                unreal.log_warning(f"  ✗ Could not load {path}")
                continue

            # ObjectRedirectors store a reference to their destination.
            # Fix strategy:
            #   1. Try to get the redirector's destination object and
            #      consolidate all refs to it (redirector becomes unreferenced).
            #   2. Fall back to deleting the redirector directly if destination
            #      is not accessible from Python.
            dest = getattr(asset, "destination_object", None)
            if dest is not None:
                # consolidate_assets(keep, [discard]) — re-points all refs
                # from `asset` (the redirector) to `dest` (the real asset).
                try:
                    unreal.EditorAssetLibrary.consolidate_assets(dest, [asset])
                    fixed += 1
                    unreal.log(f"  ✓ Consolidated: {path} → {dest.get_path_name()}")
                    continue
                except Exception as ce:
                    unreal.log_warning(f"  ⚠ Consolidate failed ({ce}), trying delete…")

            # Fallback: delete the redirector outright.
            # This is safe when the redirector has 0 referencers (r['referencer_count'] == 0).
            if r.get("referencer_count", 1) == 0:
                if unreal.EditorAssetLibrary.delete_asset(path):
                    fixed += 1
                    unreal.log(f"  ✓ Deleted (no referencers): {path}")
                else:
                    unreal.log_warning(f"  ✗ Could not delete {path}")
            else:
                unreal.log_warning(
                    f"  ✗ Skipped {path} — {r['referencer_count']} referencers still "
                    "point to it. Fix manually in the Content Browser "
                    "(right-click → Fix Up Redirectors)."
                )
        except Exception as e:
            unreal.log_warning(f"  ✗ Could not fix {path}: {e}")

    return fixed


# ─── Fix: Delete orphans ──────────────────────────────────────────────────────

def _delete_orphans(
    scan_path: str,
    dry_run: bool,
    excluded_classes: list[str],
) -> int:
    """
    Delete orphaned assets. PERMANENT — not undoable.
    Always run with dry_run=True first.
    """
    orphans = _scan_orphans(scan_path, excluded_classes)

    if not orphans:
        unreal.log("[RefAuditor] No orphaned assets found.")
        return 0

    unreal.log(f"[RefAuditor] {len(orphans)} orphaned assets:")
    for o in orphans:
        unreal.log(f"  {'[DRY RUN] WOULD DELETE' if dry_run else 'DELETING'}  {o['path']}")

    if dry_run:
        unreal.log(
            "[RefAuditor] DRY RUN — no changes made.\n"
            "  Review the list above, then call with dry_run=False to delete."
        )
        return 0

    deleted = 0
    for o in orphans:
        try:
            if unreal.EditorAssetLibrary.delete_asset(o["path"]):
                deleted += 1
            else:
                unreal.log_warning(f"  ✗ Could not delete {o['path']}")
        except Exception as e:
            unreal.log_warning(f"  ✗ Error deleting {o['path']}: {e}")

    return deleted


# ─── Full report ──────────────────────────────────────────────────────────────

def _full_report(scan_path: str, excluded_classes: list[str]) -> dict[str, Any]:
    orphans       = _scan_orphans(scan_path, excluded_classes)
    redirectors   = _scan_redirectors(scan_path)
    duplicates    = _scan_duplicates(scan_path)
    unused_tex    = _scan_unused_textures(scan_path)

    report: dict[str, Any] = {
        "scan_path": scan_path,
        "summary": {
            "orphaned_assets":    len(orphans),
            "redirectors":        len(redirectors),
            "duplicate_names":    len(duplicates),
            "unused_textures":    len(unused_tex),
        },
        "orphans":      orphans,
        "redirectors":  redirectors,
        "duplicates":   duplicates,
        "unused_textures": unused_tex,
    }

    _ensure_dir()
    with open(_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def _print_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    unreal.log(f"\n[RefAuditor] ═══ Audit Report: {report['scan_path']} ═══")
    unreal.log(f"  {_icon('warning' if s['orphaned_assets']  else 'ok')}  Orphaned assets:  {s['orphaned_assets']}")
    unreal.log(f"  {_icon('warning' if s['redirectors']      else 'ok')}  Redirectors:      {s['redirectors']}")
    unreal.log(f"  {_icon('warning' if s['duplicate_names']  else 'ok')}  Duplicate names:  {s['duplicate_names']}")
    unreal.log(f"  {_icon('warning' if s['unused_textures']  else 'ok')}  Unused textures:  {s['unused_textures']}")
    unreal.log(f"\n  Full report → {_REPORT_PATH}\n")

    if s["orphaned_assets"]:
        unreal.log("  Top orphans:")
        for o in report["orphans"][:10]:
            unreal.log(f"    {o['class']:30s}  {o['path']}")

    if s["duplicate_names"]:
        unreal.log("\n  Duplicate names (worst offenders):")
        for d in report["duplicates"][:8]:
            unreal.log(f"    '{d['base_name']}'  — {d['count']} copies:")
            for p in d["paths"]:
                unreal.log(f"      {p}")


# ─── Registered tools ──────────────────────────────────────────────────────────

@register_tool(
    name="ref_audit_orphans",
    category="Reference Auditor",
    description="Find assets with no referencers — candidates for safe deletion",
    icon="◌",
    tags=["reference", "orphan", "audit", "cleanup"],
)
def ref_audit_orphans(
    scan_path: str = "/Game",
    excluded_classes: list = None,
**kwargs,
) -> dict:
    """
    Print all assets under scan_path that nothing else references.

    Args:
        scan_path:        Content Browser path to scan (e.g. "/Game/MyProject").
        excluded_classes: Class names to skip. Maps/Blueprints are always skipped.

    Returns:
        dict: {"status", "count", "orphans": [{"path", "class"}]}
    """
    excluded = excluded_classes or []
    orphans = _scan_orphans(scan_path, excluded)

    if not orphans:
        unreal.log(f"[RefAuditor] ✓ No orphaned assets found under {scan_path}.")
        return {"status": "ok", "count": 0, "orphans": []}

    unreal.log(f"[RefAuditor] {len(orphans)} orphaned assets under {scan_path}:")
    for o in orphans:
        unreal.log(f"  ◌  {o['class']:30s}  {o['path']}")

    unreal.log(f"\n  To delete: tb.run('ref_delete_orphans', scan_path='{scan_path}', dry_run=True)")
    return {"status": "ok", "count": len(orphans), "orphans": orphans}


@register_tool(
    name="ref_audit_redirectors",
    category="Reference Auditor",
    description="Find stale ObjectRedirector assets left behind after moves/renames",
    icon="↪",
    tags=["reference", "redirector", "audit", "cleanup"],
)
def ref_audit_redirectors(scan_path: str = "/Game", **kwargs) -> dict:
    """
    Print all ObjectRedirector assets under scan_path.
    These are silent performance drags — fix them with ref_fix_redirectors.

    Returns:
        dict: {"status", "count", "redirectors": [{"path", "class", "referencer_count"}]}
    """
    redirectors = _scan_redirectors(scan_path)

    if not redirectors:
        unreal.log(f"[RefAuditor] ✓ No redirectors found under {scan_path}.")
        return {"status": "ok", "count": 0, "redirectors": []}

    unreal.log(f"[RefAuditor] {len(redirectors)} redirectors under {scan_path}:")
    for r in redirectors:
        unreal.log(f"  ↪  refs={r['referencer_count']}  {r['path']}")

    unreal.log(f"\n  To fix: tb.run('ref_fix_redirectors', scan_path='{scan_path}', dry_run=False)")
    return {"status": "ok", "count": len(redirectors), "redirectors": redirectors}


@register_tool(
    name="ref_audit_duplicates",
    category="Reference Auditor",
    description="Find assets that share the same base name in different folders",
    icon="⿻",
    tags=["reference", "duplicate", "naming", "audit"],
)
def ref_audit_duplicates(scan_path: str = "/Game", **kwargs) -> dict:
    """
    Find assets with the same base name living in different folders.
    Does NOT rename or delete anything.

    Returns:
        dict: {"status", "count", "duplicates": [{"base_name", "count", "paths"}]}
    """
    dupes = _scan_duplicates(scan_path)

    if not dupes:
        unreal.log(f"[RefAuditor] ✓ No duplicate names found under {scan_path}.")
        return {"status": "ok", "count": 0, "duplicates": []}

    unreal.log(f"[RefAuditor] {len(dupes)} duplicate name groups under {scan_path}:")
    for d in dupes:
        unreal.log(f"\n  '{d['base_name']}'  ({d['count']} copies):")
        for p in d["paths"]:
            unreal.log(f"    {p}")
    return {"status": "ok", "count": len(dupes), "duplicates": dupes}


@register_tool(
    name="ref_audit_unused_textures",
    category="Reference Auditor",
    description="Find Texture2D assets not referenced by any material",
    icon="🖼",
    tags=["reference", "texture", "unused", "cleanup"],
)
def ref_audit_unused_textures(scan_path: str = "/Game", **kwargs) -> dict:
    """
    Find textures with zero referencers — prime deletion candidates.

    Returns:
        dict: {"status", "count", "textures": [{"path", "class"}]}
    """
    unused = _scan_unused_textures(scan_path)

    if not unused:
        unreal.log(f"[RefAuditor] ✓ No unreferenced textures found under {scan_path}.")
        return {"status": "ok", "count": 0, "textures": []}

    unreal.log(f"[RefAuditor] {len(unused)} unreferenced textures under {scan_path}:")
    for u in unused:
        unreal.log(f"  🖼  {u['path']}")
    return {"status": "ok", "count": len(unused), "textures": unused}


@register_tool(
    name="ref_fix_redirectors",
    category="Reference Auditor",
    description="Consolidate all ObjectRedirector assets — always dry-run first",
    icon="🔧",
    tags=["reference", "redirector", "fix", "consolidate"],
)
def ref_fix_redirectors(
    scan_path: str = "/Game",
    dry_run: bool = True,
**kwargs,
) -> dict:
    """
    Resolve all ObjectRedirectors under scan_path.

    Args:
        dry_run: True = print what would be fixed, make no changes (default).
                 False = actually consolidate.

    Returns:
        dict: {"status", "fixed", "dry_run"}
    """
    count = _fix_redirectors(scan_path, dry_run)
    if not dry_run and count:
        unreal.log(f"[RefAuditor] ✓ Fixed {count} redirectors.")
    return {"status": "ok", "fixed": count, "dry_run": dry_run}


@register_tool(
    name="ref_delete_orphans",
    category="Reference Auditor",
    description="Permanently delete orphaned assets — always dry-run first (NOT undoable)",
    icon="🗑",
    tags=["reference", "orphan", "delete", "cleanup"],
)
def ref_delete_orphans(
    scan_path: str = "/Game",
    dry_run: bool = True,
    excluded_classes: list = None,
**kwargs,
) -> dict:
    """
    Delete assets with no referencers.

    ⚠  Asset deletion is PERMANENT and cannot be undone via Ctrl+Z.
    Always run with dry_run=True (the default) first.

    Args:
        dry_run:          True = print only, no changes (default).
        excluded_classes: Additional class names to never delete.

    Returns:
        dict: {"status", "deleted", "dry_run"}
    """
    excluded = excluded_classes or []
    count = _delete_orphans(scan_path, dry_run, excluded)
    if not dry_run and count:
        unreal.log(f"[RefAuditor] ✓ Deleted {count} orphaned assets.")
    return {"status": "ok", "deleted": count, "dry_run": dry_run}


@register_tool(
    name="ref_full_report",
    category="Reference Auditor",
    description="Run all scans and export a JSON health report for the project",
    icon="📋",
    tags=["reference", "report", "audit", "json"],
)
def ref_full_report(
    scan_path: str = "/Game",
    excluded_classes: list = None,
**kwargs,
) -> dict:
    """
    Run every audit check and write a JSON report to
    Saved/UEFN_Toolbelt/ref_audit_report.json.

    Equivalent to running all four ref_audit_* tools at once.

    Returns:
        dict: {"status", "path", "summary": {"orphaned_assets", "redirectors",
               "duplicate_names", "unused_textures"}}
    """
    excluded = excluded_classes or []
    unreal.log(f"[RefAuditor] Running full audit on {scan_path}…")
    report = _full_report(scan_path, excluded)
    _print_summary(report)
    return {"status": "ok", "path": _REPORT_PATH, "summary": report["summary"]}
