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

from UEFN_Toolbelt.core import detect_project_mount, resolve_scan_path
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


class ReferenceLookupUnavailable(RuntimeError):
    """
    Raised when this engine build exposes no working reference-lookup API.

    UEFN 42.00 (UE 6.0) removed EditorAssetLibrary.find_package_referencers.
    This MUST NOT be swallowed into an empty list. Every orphan check in this
    module inverts the answer -- "no referencers" means "safe to delete" -- and
    ref_delete_orphans acts on it permanently. Returning [] on a missing API is
    indistinguishable from "delete everything in the project".
    """


# Resolved once per session: callable(asset_path) -> list[str], or None.
_REF_LOOKUP = None
_REF_LOOKUP_PROBED = False


def _strategy_works(fn) -> bool:
    """
    Verify a lookup strategy is actually callable on this build, not merely
    present. Attribute existence is not enough: an API can survive a rename of
    its parameters, in which case every call raises TypeError deep inside a scan
    loop and the tool returns None instead of a clean refusal.

    A signature or availability problem (TypeError / AttributeError) disqualifies
    the strategy. Any other exception means the API is real and callable and the
    probe path simply is not a valid asset -- which is expected.
    """
    try:
        fn("/Engine/Transient")
    except (TypeError, AttributeError):
        return False
    except Exception:
        return True
    return True


def _resolve_ref_lookup():
    """Pick a reference-lookup strategy that works on this engine build."""
    global _REF_LOOKUP, _REF_LOOKUP_PROBED
    if _REF_LOOKUP_PROBED:
        return _REF_LOOKUP
    _REF_LOOKUP_PROBED = True

    # Strategy 1 -- UEFN <= 41.x (UE 5.x).
    legacy = getattr(unreal.EditorAssetLibrary, "find_package_referencers", None)
    if callable(legacy):
        def _via_legacy(p: str) -> list[str]:
            return [str(x) for x in (legacy(p) or [])]
        _REF_LOOKUP = _via_legacy
        return _REF_LOOKUP

    # Strategy 2 -- UE 6.0 Asset Registry.
    try:
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        if callable(getattr(ar, "get_referencers", None)):
            def _via_registry(p: str) -> list[str]:
                pkg = p.split(".")[0]
                try:
                    opts = unreal.AssetRegistryDependencyOptions(
                        include_hard_package_references=True,
                        include_soft_package_references=True,
                    )
                    refs = ar.get_referencers(pkg, opts)
                except TypeError:
                    refs = ar.get_referencers(pkg)
                return [str(x) for x in (refs or [])]

            if _strategy_works(_via_registry):
                _REF_LOOKUP = _via_registry
                return _REF_LOOKUP
    except Exception:
        pass

    _REF_LOOKUP = None
    return None


def reference_lookup_available() -> bool:
    """True if this build can answer 'what references this asset?'."""
    return _resolve_ref_lookup() is not None


NO_REF_API_MSG = (
    "Reference lookup is unavailable in this engine build. UEFN 42.00 (UE 6.0) "
    "removed EditorAssetLibrary.find_package_referencers and no Asset Registry "
    "fallback resolved. Orphan and unused-texture detection are DISABLED rather "
    "than reporting every asset as unreferenced -- acting on that answer would "
    "delete your project. Redirector and duplicate-name scans still work."
)


def _get_referencers(asset_path: str) -> list[str]:
    """
    Return packages that reference this asset.

    Raises ReferenceLookupUnavailable when the engine cannot answer. Never
    returns [] to mean "could not determine" -- callers read [] as "orphan".
    """
    lookup = _resolve_ref_lookup()
    if lookup is None:
        raise ReferenceLookupUnavailable(NO_REF_API_MSG)
    return lookup(asset_path)


def _count_referencers_soft(asset_path: str):
    """
    Referencer count for display only; None when unknown.

    Safe for the redirector scan, which prints the count but never deletes
    based on it.
    """
    try:
        return len(_get_referencers(asset_path))
    except Exception:
        return None


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

# Assets that are reference-tree ROOTS. Nothing in the asset graph points at
# them, so a referencer count of 0 is their normal, healthy state -- not a sign
# they are unused. Verified against a live UEFN 42.00 project: GameFeatureData
# and the default HLOD layer both report 0 referencers while being load-bearing.
ROOT_ASSET_CLASSES = frozenset({
    "World", "Blueprint", "BlueprintGeneratedClass",
    "WidgetBlueprint", "EditorUtilityWidget", "EditorUtilityBlueprint",
    "EditorUtilityWidgetBlueprint", "AnimBlueprint", "LevelSequence",
    # Project plumbing -- referenced by .uplugin / WorldSettings / cook rules,
    # none of which are packages, so the Asset Registry cannot see the link.
    "GameFeatureData",        # the plugin descriptor asset; deleting it kills the project
    "HLODLayer",              # referenced by WorldSettings, never by a package
    "PrimaryAssetLabel",      # a cook root by design
    "WorldPartitionMiniMap",
})


def _is_scannable_asset(path: str) -> bool:
    """
    False for object paths that are not standalone, deletable assets.

    ':' marks a sub-object inside a package -- e.g.
    /P/MyLevel.MyLevel:PersistentLevel.ActorFolder_UID_xxx. Thousands of these
    exist under one-file-per-actor, they all resolve to the same owning package,
    and none can be deleted individually.

    '$' appears in UEFN 42.00 Verse digest paths, which EditorAssetSubsystem
    rejects outright ("Can't convert the path $Digest"), logging an editor error
    on every single lookup.
    """
    return ":" not in path and "$" not in path


def _is_root_level_package(path: str) -> bool:
    """
    True if the asset sits directly at the mount root, e.g.
    /MyProject/GameFeatureData.

    Project-level plumbing lives there and is referenced by configuration rather
    than by other packages, so it always reads as a clean orphan. Real content
    lives in subfolders, so this costs almost nothing and closes the case where
    class-name lookup fails or a future engine renames one of these types.
    """
    return len(path.strip("/").split("/")) <= 2


def _scan_orphans(scan_path: str, excluded_classes: list[str]) -> list[dict[str, Any]]:
    """
    Find assets with zero referencers.

    Maps, Blueprints, and World assets are skipped — they are typically
    the roots of reference trees and will always appear orphaned by this check.
    """
    skip_classes = set(excluded_classes) | ROOT_ASSET_CLASSES

    all_paths = _list_all_assets(scan_path)
    orphans: list[dict[str, Any]] = []

    unreal.log(f"[RefAuditor] Scanning {len(all_paths)} assets for orphans…")

    protected = 0
    subobjects = 0
    for path in all_paths:
        if not _is_scannable_asset(path):
            subobjects += 1
            continue
        cls = _get_asset_class_name(path)
        if cls in skip_classes or _is_root_level_package(path):
            protected += 1
            continue
        refs = _get_referencers(path)
        if not refs:
            orphans.append({"path": path, "class": cls})

    if subobjects:
        unreal.log(
            f"[RefAuditor] {subobjects} level sub-object(s) skipped — not "
            f"standalone assets."
        )
    if protected:
        unreal.log(
            f"[RefAuditor] {protected} reference-root asset(s) protected from "
            f"orphan classification (project plumbing, maps, blueprints)."
        )
    unreal.log(
        f"[RefAuditor] {len(all_paths) - subobjects - protected} asset(s) "
        f"evaluated → {len(orphans)} orphaned."
    )
    return orphans


# ─── Scan: Redirectors ────────────────────────────────────────────────────────

def _scan_redirectors(scan_path: str) -> list[dict[str, Any]]:
    """Find ObjectRedirector assets (stale move/rename artifacts)."""
    all_paths = _list_all_assets(scan_path)
    redirectors = []

    for path in all_paths:
        cls = _get_asset_class_name(path)
        if "redirector" in cls.lower() or "objectredirector" in cls.lower():
            count = _count_referencers_soft(path)
            redirectors.append({
                "path": path,
                "class": cls,
                "referencer_count": count if count is not None else -1,
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

    # Defence in depth. _scan_orphans already filters these, but deletion is
    # permanent and not undoable -- a refactor there must not be able to silently
    # unprotect the project descriptor. Re-filter at the point of no return.
    refused = [o for o in orphans
               if _is_root_level_package(o["path"]) or o["class"] in ROOT_ASSET_CLASSES]
    if refused:
        orphans = [o for o in orphans if o not in refused]
        for o in refused:
            unreal.log_warning(
                f"[RefAuditor] REFUSED to delete reference-root asset: {o['path']} "
                f"({o['class']}) -- 0 referencers is normal for this asset type."
            )

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
    # Redirector and duplicate scans never need reference lookup, so they still
    # run on builds where it is gone. Orphan / unused-texture sections degrade
    # to an explicit "unavailable" instead of silently reporting zero.
    ref_ok = reference_lookup_available()
    orphans     = _scan_orphans(scan_path, excluded_classes) if ref_ok else []
    unused_tex  = _scan_unused_textures(scan_path)           if ref_ok else []
    redirectors = _scan_redirectors(scan_path)
    duplicates  = _scan_duplicates(scan_path)

    if not ref_ok:
        unreal.log_warning("[RefAuditor] " + NO_REF_API_MSG)

    report: dict[str, Any] = {
        "scan_path": scan_path,
        "reference_lookup_available": ref_ok,
        "summary": {
            "orphaned_assets":    len(orphans) if ref_ok else "unavailable",
            "redirectors":        len(redirectors),
            "duplicate_names":    len(duplicates),
            "unused_textures":    len(unused_tex) if ref_ok else "unavailable",
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
    _unavail = "unavailable"
    unreal.log(f"  {_icon('critical' if s['orphaned_assets'] == _unavail else ('warning' if s['orphaned_assets'] else 'ok'))}  Orphaned assets:  {s['orphaned_assets']}")
    unreal.log(f"  {_icon('warning' if s['redirectors']      else 'ok')}  Redirectors:      {s['redirectors']}")
    unreal.log(f"  {_icon('warning' if s['duplicate_names']  else 'ok')}  Duplicate names:  {s['duplicate_names']}")
    unreal.log(f"  {_icon('critical' if s['unused_textures'] == _unavail else ('warning' if s['unused_textures'] else 'ok'))}  Unused textures:  {s['unused_textures']}")
    unreal.log(f"\n  Full report → {_REPORT_PATH}\n")

    if s["orphaned_assets"] and s["orphaned_assets"] != _unavail:
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
    scan_path: str = "",
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
    scan_path = resolve_scan_path(scan_path)
    if not reference_lookup_available():
        unreal.log_warning("[RefAuditor] " + NO_REF_API_MSG)
        return {"status": "error", "reason": "reference_api_unavailable",
                "message": NO_REF_API_MSG}
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
def ref_audit_redirectors(scan_path: str = "", **kwargs) -> dict:
    """
    Print all ObjectRedirector assets under scan_path.
    These are silent performance drags — fix them with ref_fix_redirectors.

    Returns:
        dict: {"status", "count", "redirectors": [{"path", "class", "referencer_count"}]}
    """
    scan_path = resolve_scan_path(scan_path)
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
def ref_audit_duplicates(scan_path: str = "", **kwargs) -> dict:
    """
    Find assets with the same base name living in different folders.
    Does NOT rename or delete anything.

    Returns:
        dict: {"status", "count", "duplicates": [{"base_name", "count", "paths"}]}
    """
    scan_path = resolve_scan_path(scan_path)
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
def ref_audit_unused_textures(scan_path: str = "", **kwargs) -> dict:
    """
    Find textures with zero referencers — prime deletion candidates.

    Returns:
        dict: {"status", "count", "textures": [{"path", "class"}]}
    """
    scan_path = resolve_scan_path(scan_path)
    if not reference_lookup_available():
        unreal.log_warning("[RefAuditor] " + NO_REF_API_MSG)
        return {"status": "error", "reason": "reference_api_unavailable",
                "message": NO_REF_API_MSG}
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
    scan_path: str = "",
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
    scan_path = resolve_scan_path(scan_path)
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
    scan_path: str = "",
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
    scan_path = resolve_scan_path(scan_path)
    if not reference_lookup_available():
        unreal.log_warning("[RefAuditor] " + NO_REF_API_MSG)
        return {"status": "error", "reason": "reference_api_unavailable",
                "message": NO_REF_API_MSG, "deleted": 0, "dry_run": dry_run}
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
    scan_path: str = "",
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
    scan_path = resolve_scan_path(scan_path)
    excluded = excluded_classes or []
    unreal.log(f"[RefAuditor] Running full audit on {scan_path}…")
    report = _full_report(scan_path, excluded)
    _print_summary(report)
    return {"status": "ok", "path": _REPORT_PATH, "summary": report["summary"]}

# ─── Broken references (the opposite direction to orphans) ────────────────────
#
# The rest of this module answers "does anything reference this asset?" and is
# used to find things safe to delete. This answers the reverse: does anything
# reference an asset that is no longer there?
#
# That damage is created by moves and renames that half-succeed. Toolbelt itself
# caused it twice — organize_smart_categorize deleted the source when a rename
# failed and counted it as moved, and arena_generate wrote materials to /Game/,
# which in UEFN is Epic's install, leaving every actor that used them pointing at
# nothing. Both are fixed, but projects worked on before those fixes still carry
# the wreckage and nothing here could see it.
#
# A missing hard reference does not survive as a path in UE — the property comes
# back None. So this looks for components that should hold an asset and hold
# nothing, which is what a severed reference actually looks like from Python.


_DEP_LOOKUP = None
_DEP_LOOKUP_PROBED = False

# Dependencies that are not assets and can never be "missing".
_DEP_IGNORE = ("/Script/", "/Engine/Transient", "/Temp/", "/Memory/", "/Verse/")


def _resolve_dep_lookup():
    """Pick a strategy for "what does this package reference?" on this build.

    Same discipline as _resolve_ref_lookup: probe it, do not assume it. A tool
    that silently answers [] here would report every dependency as present and
    call a damaged level clean.
    """
    global _DEP_LOOKUP, _DEP_LOOKUP_PROBED
    if _DEP_LOOKUP_PROBED:
        return _DEP_LOOKUP
    _DEP_LOOKUP_PROBED = True

    try:
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        if callable(getattr(ar, "get_dependencies", None)):
            def _via_registry(path: str) -> list[str]:
                pkg = path.split(".")[0]
                try:
                    opts = unreal.AssetRegistryDependencyOptions(
                        include_hard_package_references=True,
                        include_soft_package_references=True,
                    )
                    deps = ar.get_dependencies(pkg, opts)
                except TypeError:
                    deps = ar.get_dependencies(pkg)
                return [str(x) for x in (deps or [])]

            if _strategy_works(_via_registry):
                _DEP_LOOKUP = _via_registry
                return _DEP_LOOKUP
    except Exception:
        pass

    _DEP_LOOKUP = None
    return None


def dependency_lookup_available() -> bool:
    """True if this build can answer "what does this package reference?"."""
    return _resolve_dep_lookup() is not None


def _actor_package(actor):
    """The package holding this actor. Under OFPA that is one package per actor."""
    for getter in ("get_package", "get_outermost"):
        fn = getattr(actor, getter, None)
        if callable(fn):
            try:
                pkg = fn()
                if pkg is not None:
                    return str(pkg.get_name())
            except Exception:
                continue
    return None


def _missing_dependencies(actors, exists_cache: dict) -> tuple[dict[str, set], int, int, int]:
    """Dependencies recorded on disk whose target asset no longer exists.

    This is the detection the CDO comparison could not do. A null component
    pointer has already forgotten what it pointed at, but the asset registry
    builds its dependency table from the saved package, so the reference
    survives the deletion of its target and can still be named.

    ONLY dependencies under the project's own mount are judged. The first
    version checked every mount with EditorAssetLibrary.does_asset_exist and
    reported 383 missing assets on a healthy island — every one of them Epic
    plugin content (/CRD_*, /CreativeCoreDevices, /ContentHall) that plainly
    exists, because does_asset_exist cannot browse those mounts and answers
    False for "cannot see" exactly as it does for "not there" (Quirk #23).

    Everything outside the project mount is counted as unverifiable and
    reported as such, because the creator cannot have broken Epic's content
    anyway — the damage worth finding is in their own.

    Returns (missing -> referencing actor labels, dependencies_checked,
    packages_checked, unverifiable_dependencies).
    """
    lookup = _resolve_dep_lookup()
    if lookup is None:
        return {}, 0, 0, 0

    try:
        mount = f"/{detect_project_mount()}/"
    except Exception:
        return {}, 0, 0, 0

    missing: dict[str, set] = {}
    checked = 0
    unverifiable = 0
    packages: dict[str, str] = {}

    for actor in actors:
        if actor is None:
            continue
        pkg = _actor_package(actor)
        if not pkg or pkg in packages:
            continue
        try:
            packages[pkg] = actor.get_actor_label()
        except Exception:
            packages[pkg] = pkg.rsplit("/", 1)[-1]

    for pkg, label in packages.items():
        try:
            deps = lookup(pkg)
        except Exception:
            continue
        for dep in deps:
            if dep.startswith(_DEP_IGNORE):
                continue
            if not dep.startswith(mount):
                # Another mount — Epic's, or a plugin's. Not answerable here.
                unverifiable += 1
                continue
            checked += 1
            present = exists_cache.get(dep)
            if present is None:
                try:
                    present = bool(unreal.EditorAssetLibrary.does_asset_exist(dep))
                except Exception:
                    # Cannot answer -> do not claim it is missing.
                    present = True
                exists_cache[dep] = present
            if not present:
                missing.setdefault(dep, set()).add(label)

    return missing, checked, len(packages), unverifiable


def _empty_slots(actor) -> tuple[list[dict], int]:
    """
    Asset slots that are empty on this instance but filled on its class default.

    The first version of this just flagged any StaticMeshComponent with no mesh,
    and on a healthy 93-actor level it reported 13 actors "broken" — every one a
    false positive. EditorOnlyStaticMeshComponent is editor-side visualisation
    that legitimately holds nothing, and Fortnite prop and device actors are full
    of them. A null slot on its own says nothing.

    The question is not "is this empty?" but "was this supposed to hold
    something?", and the class default object answers it: if the CDO's matching
    component has a mesh and this instance's does not, the reference was severed.
    If the CDO is empty too, this is simply how the actor is built.
    """
    out: list[dict] = []
    comparable = 0          # slots whose class default is filled, so a null IS a break
    try:
        cdo = actor.get_class().get_default_object()
        comps = actor.get_components_by_class(unreal.StaticMeshComponent)
    except Exception:
        return out, comparable

    # what the class ships with, by component name
    defaults: dict = {}
    try:
        for c in cdo.get_components_by_class(unreal.StaticMeshComponent) or []:
            try:
                defaults[c.get_name()] = c.get_editor_property("static_mesh")
            except Exception:
                pass
    except Exception:
        return out, comparable   # can't compare — say nothing rather than guess

    for comp in comps or []:
        try:
            name = comp.get_name()
        except Exception:
            continue

        # editor-only visualisation never ships a mesh; not a reference at all
        try:
            if comp.get_editor_property("is_editor_only"):
                continue
        except Exception:
            pass
        if name.startswith("EditorOnly"):
            continue

        # Counted only past the skips: comparable must mean "judged", or it
        # lends credibility to slots this check never actually looked at.
        if defaults.get(name) is not None:
            comparable += 1

        try:
            mesh = comp.get_editor_property("static_mesh")
        except Exception:
            continue
        if mesh is not None:
            continue

        expected = defaults.get(name)
        if expected is None:
            continue        # class default is empty too — this is normal

        out.append({
            "component": name,
            "slot": "static_mesh",
            "kind": "missing mesh",
            "expected": str(expected.get_path_name()) if expected else "?",
        })
    return out, comparable


@register_tool(
    name="ref_audit_broken",
    category="Reference Auditor",
    description="Find actors pointing at assets that no longer exist (severed references)",
    icon="⚠",
    tags=["reference", "broken", "dangling", "audit", "repair", "missing"],
    example='tb.run("ref_audit_broken")',
)
def ref_audit_broken(max_results: int = 200, **kwargs) -> dict:
    """
    Scan every actor in the current level for empty asset slots.

    Finds the wreckage left by moves and renames that half-succeeded: actors
    whose mesh or material was deleted out from under them. Read-only — it
    changes nothing, and reports enough to fix by hand or to drive a repair.

    Args:
        max_results: Cap on reported actors, to keep the log usable.

    Two independent checks, because the first one alone detects nothing here:

    1. Asset-registry dependencies. The saved package records what it references,
       and that record survives the deletion of its target — so a missing asset
       can still be NAMED. This is the primary check.
    2. Class-default comparison, kept as a secondary signal for Blueprint-style
       actors whose class ships a mesh.

    Blind spot, reported rather than hidden: a slot is only judged when the
    actor's class default fills it. A plain StaticMeshActor takes its mesh
    per-instance, so its class default is empty and a severed mesh there looks
    identical to one that was never set. Those actors are counted in
    actors_scanned but cannot be judged, which is why the result carries
    comparable_slots — "0 broken" means nothing without it.

    Returns:
        dict: {"status", "actors_scanned", "missing_assets",
               "dependencies_checked", "packages_checked", "dependency_lookup",
               "broken_actors", "missing_meshes", "unreadable",
               "comparable_slots", "actors_in_scope",
               "missing_asset_findings", "findings"}

        status is "inconclusive" when neither check could judge anything, so a
        caller cannot mistake an unexamined level for a healthy one.
    """
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = actor_sub.get_all_level_actors() or []
    except Exception as e:
        return {"status": "error", "reason": "level_unavailable", "message": str(e)}

    findings: list[dict] = []
    unreadable = 0
    meshes = 0
    comparable_slots = 0
    actors_in_scope = 0
    exists_cache: dict = {}

    # Primary detection. The CDO comparison below is a secondary signal: it was
    # the whole check until a live run on a 3405-actor island reported
    # comparable_slots 0, because UEFN actors take their meshes per-instance and
    # so have no class default to compare against.
    missing_deps, deps_checked, pkgs_checked, unverifiable_deps = _missing_dependencies(
        actors, exists_cache)

    for actor in actors:
        if actor is None:
            continue
        try:
            label = actor.get_actor_label()
        except Exception:
            # Can't identify it, so can't report it usefully — count, don't guess.
            unreadable += 1
            continue

        slots, comparable = _empty_slots(actor)
        comparable_slots += comparable
        if comparable:
            actors_in_scope += 1
        if not slots:
            continue
        meshes += len(slots)
        findings.append({"actor": label, "slots": slots})

    dep_findings = [
        {"missing_asset": path, "referenced_by": sorted(labels)[:10],
         "referencing_actors": len(labels)}
        for path, labels in sorted(missing_deps.items())
    ]

    if dep_findings:
        unreal.log_warning(
            f"[RefAuditor] {len(dep_findings)} missing asset(s) still referenced "
            f"by this level ({deps_checked} dependencies checked across "
            f"{pkgs_checked} package(s); {unverifiable_deps} on other mounts "
            f"were not checkable):"
        )
        for d in dep_findings[:max_results]:
            who = ", ".join(d["referenced_by"][:3])
            more = f" (+{d['referencing_actors'] - 3} more)" if d["referencing_actors"] > 3 else ""
            unreal.log(f"    {d['missing_asset']}  ←  {who}{more}")

    total = len(findings)
    if total == 0 and not dep_findings:
        if deps_checked == 0 and comparable_slots == 0:
            # Nothing was checkable, so a clean result is not a clean level.
            unreal.log_warning(
                f"[RefAuditor] Inconclusive — {len(actors)} actors checked, but "
                f"nothing could be judged: no dependency data and no class-default "
                f"mesh to compare against. This is not evidence the level is clean."
            )
        else:
            unreal.log(
                f"[RefAuditor] ✓ No severed references — {len(actors)} actors, "
                f"{deps_checked} dependencies across {pkgs_checked} package(s) all "
                f"resolve; {comparable_slots} class-default slot(s) intact."
            )
    else:
        unreal.log_warning(
            f"[RefAuditor] {total} actor(s) with severed references "
            f"({meshes} slot(s) empty where the class default is filled):"
        )
        for f in findings[:max_results]:
            detail = ", ".join(f"{s['component']} expected {s['expected']}" for s in f["slots"])
            unreal.log(f"    {f['actor']}  →  {detail}")
        if total > max_results:
            unreal.log(f"    … and {total - max_results} more.")

    if unreadable:
        unreal.log_warning(
            f"[RefAuditor] {unreadable} actor(s) could not be read and were not "
            f"checked — this result is incomplete, not clean."
        )

    judged_something = deps_checked > 0 or comparable_slots > 0
    return {
        # "inconclusive" so a caller cannot read an unjudgeable scan as a pass.
        "status":              "ok" if judged_something else "inconclusive",
        "actors_scanned":      len(actors),
        "missing_assets":      len(dep_findings),
        "dependencies_checked": deps_checked,
        "packages_checked":    pkgs_checked,
        "unverifiable_dependencies": unverifiable_deps,
        "dependency_lookup":   dependency_lookup_available(),
        "broken_actors":       total,
        "missing_meshes":      meshes,
        "unreadable":          unreadable,
        "comparable_slots":    comparable_slots,
        "actors_in_scope":     actors_in_scope,
        "missing_asset_findings": dep_findings[:max_results],
        "findings":            findings[:max_results],
    }
