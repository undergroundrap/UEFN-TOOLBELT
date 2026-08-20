"""
UEFN TOOLBELT — publish_audit.py
===================================
Fortnite island publish-readiness checker.

Runs a fast 9-layer audit and returns a go/no-go decision with an ordered
action list — so creators know exactly what to fix before hitting "Publish"
and waiting 10 minutes to find out it failed.

What this does NOT duplicate (existing tools handle these):
  - Deep memory profiling        → memory_scan / memory_top_offenders
  - Full asset reference audit   → ref_full_report
  - Detailed rogue actor report  → rogue_actor_scan
  - LOD / collision audit        → lod_audit_folder
  - Level health score           → level_health_report
  - Verse error details          → verse_patch_errors

What this ADDS (not covered elsewhere):
  1. Actor count vs Fortnite budget limit
  2. Required device presence (spawn pads, etc.)
  3. Light count budget warning
  4. Quick rogue actor pass (inline, no sub-tool call)
  5. Verse build status from last log (pass/fail summary only)
  6. Unsaved level detection
  7. Stale redirector count (quick Asset Registry scan)
  8. Level name sanity (not "Untitled")
  9. Memory report freshness reference (reads cached memory_report.json)

MCP usage:
    tb.run("publish_audit")
    tb.run("publish_audit", actor_limit=3000, required_devices="SpawnPadDevice,EndGameDevice")
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

import unreal

from ..core import log_info
from ..registry import register_tool

# ── Defaults ──────────────────────────────────────────────────────────────────

_ACTOR_LIMIT_DEFAULT    = 2000
_LIGHT_WARN_DEFAULT     = 50
_MEMORY_WARN_MB_DEFAULT = 400.0
_MEMORY_CRIT_MB_DEFAULT = 512.0


# ── Individual check helpers ──────────────────────────────────────────────────

def _check_actor_count(actors: list, limit: int) -> dict:
    count    = len(actors)
    passed   = count <= limit
    severity = "ok" if passed else ("warn" if count <= int(limit * 1.1) else "fail")
    return {
        "pass":     passed,
        "value":    count,
        "limit":    limit,
        "severity": severity,
        "note":     f"{count} actors ✓" if passed
                    else f"{count} actors (limit {limit}) — reduce before publishing",
    }


def _check_required_devices(req_list: list[str], actors: list) -> dict:
    missing = [
        req for req in req_list
        if not any(req.lower() in a.get_class().get_name().lower() for a in actors)
    ]
    return {
        "pass":     not missing,
        "missing":  missing,
        "severity": "fail" if missing else "ok",
        "note":     "All required devices present ✓" if not missing
                    else f"Missing required devices: {missing}",
    }


def _check_lights(actors: list, warn_limit: int) -> dict:
    count    = sum(1 for a in actors if "Light" in a.get_class().get_name())
    passed   = count <= warn_limit
    severity = "ok" if passed else "warn"
    return {
        "pass":     passed,
        "value":    count,
        "limit":    warn_limit,
        "severity": severity,
        "note":     f"{count} lights ✓" if passed
                    else f"{count} lights (>{warn_limit} may impact performance)",
    }


# Engine-managed system actors that legitimately sit at origin — skip them
_SYSTEM_ACTOR_CLASSES = frozenset({
    "WorldDataLayers", "WorldPartitionMiniMap", "WorldPartitionReplay",
    "GlobalPostProcess", "WorldSettings", "WorldPartitionEditorCell",
    "Brush",
})


def _check_rogue_actors(actors: list) -> dict:
    rogues = []
    for a in actors:
        try:
            cls = a.get_class().get_name()
            if any(s in cls for s in _SYSTEM_ACTOR_CLASSES):
                continue
            loc   = a.get_actor_location()
            scale = a.get_actor_scale3d()
            issues = []
            if scale.x == 0 or scale.y == 0 or scale.z == 0:
                issues.append("zero scale")
            if abs(scale.x) > 100 or abs(scale.y) > 100 or abs(scale.z) > 100:
                issues.append("extreme scale")
            if abs(loc.x) > 500_000 or abs(loc.y) > 500_000:
                issues.append("off-map")
            if loc.x == 0 and loc.y == 0 and loc.z == 0:
                issues.append("at origin")
            if issues:
                rogues.append({"label": a.get_actor_label(), "issues": issues})
        except Exception:
            pass
    return {
        "pass":     not rogues,
        "count":    len(rogues),
        "rogues":   rogues[:10],
        "severity": "warn" if rogues else "ok",
        "note":     "No rogue actors ✓" if not rogues
                    else f"{len(rogues)} actors with scale/location issues — run rogue_actor_scan for details",
    }


def _check_verse_build(project_saved_dir: str) -> dict:
    log_dir = os.path.normpath(os.path.join(project_saved_dir, "..", "Logs"))
    try:
        if not os.path.isdir(log_dir):
            return {"pass": None, "status": "UNKNOWN", "severity": "warn",
                    "note": "Log directory not found — run a Verse build first"}
        logs = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".log")]
        if not logs:
            return {"pass": None, "status": "UNKNOWN", "severity": "warn",
                    "note": "No build log found — run a Verse build first"}
        latest = max(logs, key=os.path.getmtime)
        with open(latest, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if re.search(
            r"VerseBuild.*SUCCESS|LogSolLoadCompiler.*finished.*SUCCESS",
            content, re.IGNORECASE
        ):
            return {"pass": True, "status": "SUCCESS", "severity": "ok",
                    "note": "Verse build SUCCESS ✓"}
        if re.search(
            r"VerseBuild.*(?:FAIL|ERROR)|LogSolLoadCompiler.*finished.*(?:FAIL|ERROR)",
            content, re.IGNORECASE
        ):
            return {"pass": False, "status": "FAILED", "severity": "fail",
                    "note": "Verse build FAILED — run verse_patch_errors to see issues"}
        return {"pass": None, "status": "UNKNOWN", "severity": "warn",
                "note": "Verse build status unknown — click Build Verse first"}
    except Exception as e:
        return {"pass": None, "status": "UNKNOWN", "severity": "warn",
                "note": f"Could not read build log: {e}"}


def _check_unsaved(world) -> dict:
    dirty = False
    try:
        if hasattr(world, "is_dirty"):
            dirty = world.is_dirty()
        if not dirty:
            pkg = world.get_outer() if hasattr(world, "get_outer") else None
            if pkg and hasattr(pkg, "is_dirty"):
                dirty = pkg.is_dirty()
    except Exception:
        pass
    return {
        "pass":     not dirty,
        "dirty":    dirty,
        "severity": "warn" if dirty else "ok",
        "note":     "Level has unsaved changes — save before publishing"
                    if dirty else "Level saved ✓",
    }


def _check_redirectors() -> dict:
    try:
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        f  = unreal.ARFilter(
            class_names=["ObjectRedirector"],
            package_paths=["/Game"],
            recursive_paths=True,
        )
        count = len(ar.get_assets(f))
        return {
            "pass":     count == 0,
            "count":    count,
            "severity": "warn" if count > 0 else "ok",
            "note":     "No stale redirectors ✓" if count == 0
                        else f"{count} stale redirectors — run ref_fix_redirectors",
        }
    except Exception as e:
        return {"pass": True, "count": 0, "severity": "ok",
                "note": f"Redirector check skipped: {e}"}


def _check_level_name(world) -> dict:
    name      = world.get_name() if hasattr(world, "get_name") else ""
    bad_names = {"untitled", "newlevel", "default", "template", "testlevel", ""}
    passed    = name.lower() not in bad_names
    return {
        "pass":     passed,
        "name":     name,
        "severity": "warn" if not passed else "ok",
        "note":     f"Level name: '{name}' ✓" if passed
                    else f"Level is named '{name}' — rename before publishing",
    }


def _check_memory(toolbelt_saved_dir: str, warn_mb: float, crit_mb: float) -> dict:
    report_path = os.path.join(toolbelt_saved_dir, "memory_report.json")
    if not os.path.exists(report_path):
        return {"pass": None, "severity": "warn",
                "note": "No memory report — run memory_scan for full analysis"}
    try:
        age_h = (datetime.now().timestamp() - os.path.getmtime(report_path)) / 3600
        if age_h > 2:
            return {"pass": None, "severity": "warn",
                    "note": f"Memory report is {age_h:.1f}h old — re-run memory_scan"}
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
        est_mb = (data.get("summary", {}).get("estimated_vram_mb")
                  or data.get("estimated_vram_mb", 0))
        severity = "ok" if est_mb < warn_mb else ("warn" if est_mb < crit_mb else "fail")
        return {
            "pass":         est_mb < crit_mb,
            "estimated_mb": round(float(est_mb), 1),
            "warn_mb":      warn_mb,
            "crit_mb":      crit_mb,
            "severity":     severity,
            "note":         f"Est. VRAM ~{est_mb:.0f} MB ✓" if est_mb < warn_mb
                            else f"Est. VRAM ~{est_mb:.0f} MB (warn >{warn_mb:.0f} MB)"
                            if est_mb < crit_mb
                            else f"Est. VRAM ~{est_mb:.0f} MB — OVER limit ({crit_mb:.0f} MB)",
        }
    except Exception as e:
        return {"pass": None, "severity": "warn",
                "note": f"Could not read memory report: {e}"}


# ── Registered tool ───────────────────────────────────────────────────────────

@register_tool(
    name="publish_audit",
    category="Project Admin",
    description=(
        "Full Fortnite publish-readiness audit — actor budget, required devices, "
        "lights, rogue actors, Verse build status, unsaved changes, redirectors, "
        "level name, and memory. Returns go/no-go with ordered next steps."
    ),
    tags=["publish", "audit", "validate", "health", "fortnite", "readiness", "checklist", "ai"],
)
def publish_audit(
    actor_limit: int = 2000,
    light_warn: int = 50,
    memory_warn_mb: float = 400.0,
    memory_crit_mb: float = 512.0,
    required_devices: str = "SpawnPadDevice",
    **kwargs,
) -> dict:
    """
    Run a full publish-readiness audit on the current UEFN island.

    Checks 9 layers in one fast pass without spawning actors or modifying anything:
      1. actor_count     — total actors vs budget limit
      2. required_devices — spawn pads (and any others you specify)
      3. lights          — light count warning
      4. rogue_actors    — zero/extreme scale, off-map, at-origin actors
      5. verse_build     — last Verse build log SUCCESS / FAILED / UNKNOWN
      6. unsaved_level   — level has unsaved changes
      7. redirectors     — stale ObjectRedirectors in the project
      8. level_name      — world name not "Untitled" or default
      9. memory          — references cached memory_report.json if < 2h old

    Args:
        actor_limit:      Max actors before FAIL (default 2000).
        light_warn:       Light count above which to WARN (default 50).
        memory_warn_mb:   Est. VRAM above which to WARN (default 400 MB).
        memory_crit_mb:   Est. VRAM above which to FAIL (default 512 MB).
        required_devices: Comma-separated class name fragments that MUST be
                          present in the level (default "SpawnPadDevice").
                          Example: "SpawnPadDevice,EndGameDevice"

    Returns:
        {
          "status":      "ready" | "warnings" | "blocked",
          "score":       0-100,
          "checks":      {name: {"pass", "severity", "note", ...}},
          "blocked_by":  [str],   # check names with severity=="fail"
          "next_steps":  [str],   # ordered action list (fails first, then warns)
          "summary":     str,
          "report_path": str,     # JSON saved to Saved/UEFN_Toolbelt/publish_audit.json
        }

    Example:
        tb.run("publish_audit")
        tb.run("publish_audit", required_devices="SpawnPadDevice,EndGameDevice",
               actor_limit=3000)
    """
    toolbelt_saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(toolbelt_saved, exist_ok=True)

    sub     = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors  = sub.get_all_level_actors()
    world   = unreal.EditorLevelLibrary.get_editor_world()
    req_list = [r.strip() for r in required_devices.split(",") if r.strip()]

    # ── Run all 9 checks ──────────────────────────────────────────────────
    checks = {
        "actor_count":      _check_actor_count(actors, actor_limit),
        "required_devices": _check_required_devices(req_list, actors),
        "lights":           _check_lights(actors, light_warn),
        "rogue_actors":     _check_rogue_actors(actors),
        "verse_build":      _check_verse_build(unreal.Paths.project_saved_dir()),
        "unsaved_level":    _check_unsaved(world),
        "redirectors":      _check_redirectors(),
        "level_name":       _check_level_name(world),
        "memory":           _check_memory(toolbelt_saved, memory_warn_mb, memory_crit_mb),
    }

    # ── Scoring ───────────────────────────────────────────────────────────
    total   = len(checks)
    passed  = sum(1 for c in checks.values() if c.get("pass") is True)
    warned  = sum(1 for c in checks.values() if c.get("severity") == "warn")
    failed  = sum(1 for c in checks.values() if c.get("severity") == "fail")
    unknown = sum(1 for c in checks.values() if c.get("pass") is None)

    score  = max(0, round(100 * (passed / total) - (warned * 5) - (failed * 20)))
    status = "blocked" if failed > 0 else ("warnings" if warned > 0 or unknown > 0 else "ready")

    blocked_by = [n for n, c in checks.items() if c.get("severity") == "fail"]

    next_steps = []
    for sev in ("fail", "warn"):
        for c in checks.values():
            if c.get("severity") == sev and c.get("pass") is not True:
                next_steps.append(c["note"])

    icon    = {"ready": "✅", "warnings": "⚠️", "blocked": "🚫"}[status]
    summary = (
        f"{icon} {status.upper()} — {score}/100  "
        f"({passed} passed · {warned} warnings · {failed} blocked · {unknown} unknown)"
    )

    log_info(f"[publish_audit] {summary}")
    for step in next_steps:
        log_info(f"  → {step}")

    report = {
        "status":     status,
        "score":      score,
        "checks":     checks,
        "blocked_by": blocked_by,
        "next_steps": next_steps,
        "summary":    summary,
        "run_at":     datetime.now().isoformat(),
    }

    report_path = os.path.join(toolbelt_saved, "publish_audit.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    except Exception:
        pass

    report["report_path"] = report_path
    return report
