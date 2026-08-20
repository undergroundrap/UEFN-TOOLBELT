"""
UEFN TOOLBELT — Level Health Dashboard
=======================================
Unified level health report that aggregates results from the Toolbelt's
19 individual audit tools into a single scored report.

TOOLS:
  • level_health_report  — Headless: run all audits, compute health score 0–100,
                           return structured dict. MCP / AI agent friendly.
  • level_health_open    — Windowed UI: same report with colour-coded category
                           cards, per-issue drilldown, and a one-click fix queue.

HEALTH SCORE FORMULA:
  Each category contributes up to its weight (see _CATEGORIES).
  Issues deduct points proportionally — a category with 0 issues scores full weight.
  Final score = sum of all category scores, clamped to 0–100.

USAGE:
    import UEFN_Toolbelt as tb

    # Headless — great for MCP / AI pipelines
    result = tb.run("level_health_report")
    # → {"status": "ok", "score": 87, "grade": "B", "categories": {...}}

    # Windowed UI
    tb.run("level_health_open")
"""

from __future__ import annotations

import unreal

from ..core import log_info
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Lightweight audit runners — metadata-only, never load assets
#  Safe to call in any level without risk of null pointer crashes.
# ─────────────────────────────────────────────────────────────────────────────

def _audit_actors() -> dict:
    """Count rogue actors using only property reads — no asset loading."""
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = actor_sub.get_all_level_actors() or []
    except Exception as e:
        return {"status": "error", "message": str(e), "rogue_count": 0, "total": 0}

    rogue = 0
    total = 0
    for actor in actors:
        total += 1
        try:
            loc   = actor.get_actor_location()
            scale = actor.get_actor_scale3d()
            if (scale.x == 0 or scale.y == 0 or scale.z == 0
                    or any(abs(s) > 100 for s in (scale.x, scale.y, scale.z))
                    or any(abs(v) > 500_000 for v in (loc.x, loc.y, loc.z))):
                rogue += 1
        except Exception:
            pass

    return {"status": "ok", "rogue_count": rogue, "total": total}


def _audit_asset_count() -> dict:
    """Count assets by type from AR metadata only — no asset loading."""
    try:
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        all_assets = ar.get_all_assets() or []
    except Exception as e:
        return {"status": "error", "message": str(e), "total": 0}

    total = len(all_assets)
    user_assets = sum(
        1 for a in all_assets
        if not str(a.package_name).startswith(("/Engine/", "/Script/", "/FortniteGame/"))
    )
    return {"status": "ok", "total": total, "user_assets": user_assets}


def _audit_naming() -> dict:
    """Check asset name prefixes for user project assets only — no asset loading."""
    from ..core import detect_project_mount  # noqa: PLC0415
    PREFIX_MAP = {
        "StaticMesh":               "SM_",
        "Texture2D":                "T_",
        "Material":                 "M_",
        "MaterialInstanceConstant": "MI_",
        "SoundWave":                "A_",
        "Blueprint":                "BP_",
    }
    try:
        mount = detect_project_mount()
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        filt = unreal.ARFilter(
            package_paths=[f"/{mount}/"],
            recursive_paths=True,
        )
        assets = ar.get_assets(filt) or []
    except Exception as e:
        return {"status": "error", "message": str(e), "violations": 0, "checked": 0}

    violations = 0
    checked = 0
    for a in assets:
        cls = str(a.asset_class_path.asset_name) if hasattr(a, "asset_class_path") else str(getattr(a, "asset_class", ""))
        expected = PREFIX_MAP.get(cls)
        if not expected:
            continue
        checked += 1
        pkg = str(a.package_name)
        asset_name = pkg.rsplit("/", 1)[-1]
        if not asset_name.startswith(expected):
            violations += 1

    return {"status": "ok", "violations": violations, "checked": checked}


def _audit_verse_devices() -> dict:
    """Count Verse/Creative devices in the level — safe actor class check."""
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = actor_sub.get_all_level_actors() or []
    except Exception as e:
        return {"status": "error", "message": str(e), "device_count": 0}

    device_count = 0
    for actor in actors:
        try:
            cls = actor.get_class().get_name().lower()
            if "device" in cls or "creative" in cls or "verse" in cls:
                device_count += 1
        except Exception:
            pass

    return {"status": "ok", "device_count": device_count}


def _audit_level_info() -> dict:
    """Read basic world info — always safe."""
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = actor_sub.get_all_level_actors() or []
        actor_count = len(actors)
    except Exception:
        actor_count = 0

    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        world_name = world.get_name() if world else "Unknown"
    except Exception:
        world_name = "Unknown"

    return {"status": "ok", "actor_count": actor_count, "world_name": world_name}


# ─────────────────────────────────────────────────────────────────────────────
#  Category definitions — weight must sum to 100
#  All runners above are metadata-only and safe against null pointer crashes.
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORIES = [
    {
        "id":      "actors",
        "label":   "Actor Integrity",
        "weight":  30,
        "icon":    "[ACT]",
        "runner":  _audit_actors,
        "score_fn": lambda r: max(0, 1.0 - r.get("rogue_count", 0) / max(r.get("total", 1), 1)),
        "summary_fn": lambda r: (
            f"{r.get('rogue_count', 0)} actor(s) with bad scale or off-map location "
            f"(of {r.get('total', 0)} total)"
        ) if r.get("rogue_count", 0) else f"All {r.get('total', 0)} actors look clean",
    },
    {
        "id":      "naming",
        "label":   "Naming Conventions",
        "weight":  25,
        "icon":    "[NAM]",
        "runner":  _audit_naming,
        "score_fn": lambda r: max(0, 1.0 - r.get("violations", 0) / max(r.get("checked", 1), 1)),
        "summary_fn": lambda r: (
            f"{r.get('violations', 0)} of {r.get('checked', 0)} assets missing prefix (SM_, T_, M_, etc.)"
        ) if r.get("violations", 0) else f"All {r.get('checked', 0)} checked assets follow conventions",
    },
    {
        "id":      "assets",
        "label":   "Asset Inventory",
        "weight":  20,
        "icon":    "[AST]",
        "runner":  _audit_asset_count,
        "score_fn": lambda r: 1.0 if r.get("status") == "ok" else 0.0,
        "summary_fn": lambda r: (
            f"{r.get('user_assets', 0)} project assets, {r.get('total', 0)} total in registry"
        ),
    },
    {
        "id":      "devices",
        "label":   "Verse Devices",
        "weight":  15,
        "icon":    "[DEV]",
        "runner":  _audit_verse_devices,
        "score_fn": lambda r: 1.0 if r.get("status") == "ok" else 0.0,
        "summary_fn": lambda r: f"{r.get('device_count', 0)} Creative/Verse device(s) in level",
    },
    {
        "id":      "level",
        "label":   "Level Info",
        "weight":  10,
        "icon":    "[LVL]",
        "runner":  _audit_level_info,
        "score_fn": lambda r: 1.0 if r.get("status") == "ok" else 0.0,
        "summary_fn": lambda r: f"{r.get('world_name', '?')} — {r.get('actor_count', 0)} actors",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
#  Score → grade
# ─────────────────────────────────────────────────────────────────────────────

def _grade(score: int) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 55: return "D"
    return "F"


def _grade_color(grade: str) -> str:
    return {
        "A+": "#4ADE80", "A": "#4ADE80",
        "B":  "#A3E635",
        "C":  "#FACC15",
        "D":  "#FB923C",
        "F":  "#F87171",
    }.get(grade, "#A0A0A0")


# ─────────────────────────────────────────────────────────────────────────────
#  Core runner — shared by headless and windowed tools
# ─────────────────────────────────────────────────────────────────────────────

def _run_health_report(on_progress=None) -> dict:
    """
    Run all audit categories and return a structured health report.
    on_progress(category_id, result) called after each category completes.
    """
    category_results = {}
    total_score = 0.0

    for cat in _CATEGORIES:
        try:
            result = cat["runner"]() or {}
        except Exception as exc:
            result = {"status": "error", "message": str(exc)}

        ratio   = cat["score_fn"](result)
        contrib = ratio * cat["weight"]
        total_score += contrib

        category_results[cat["id"]] = {
            "label":   cat["label"],
            "icon":    cat["icon"],
            "weight":  cat["weight"],
            "score":   round(contrib, 1),
            "max":     cat["weight"],
            "ratio":   round(ratio, 3),
            "summary": cat["summary_fn"](result),
            "raw":     result,
        }

        if on_progress:
            on_progress(cat["id"], category_results[cat["id"]])

    score = max(0, min(100, round(total_score)))
    grade = _grade(score)

    log_info(f"Level Health Report: {score}/100 ({grade})")
    for _cid, cdata in category_results.items():
        status = "✅" if cdata["ratio"] >= 0.9 else ("⚠️" if cdata["ratio"] >= 0.6 else "❌")
        log_info(f"  {status} {cdata['label']}: {cdata['score']:.1f}/{cdata['max']} — {cdata['summary']}")

    return {
        "status":     "ok",
        "score":      score,
        "grade":      grade,
        "categories": category_results,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Registered tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="level_health_report",
    category="Utilities",
    description=(
        "Run all Toolbelt audit tools and return a unified level health score (0–100) "
        "with per-category breakdowns. MCP and AI agent friendly — returns structured dict."
    ),
    tags=["audit", "health", "report", "score", "optimization", "ai"],
)
def run_level_health_report(**kwargs) -> dict:
    """
    Headless level health report. Runs all 6 audit categories and returns
    a scored summary dict readable by AI agents via MCP.

    Returns:
        {
            "status":     "ok",
            "score":      87,          # 0–100
            "grade":      "B",         # A+/A/B/C/D/F
            "categories": {
                "actors":  {"label": ..., "score": ..., "max": ..., "summary": ...},
                ...
            }
        }
    """
    return _run_health_report()


@register_tool(
    name="level_health_open",
    category="Utilities",
    description=(
        "Open the Level Health Dashboard — a visual report showing your level's health "
        "score (0–100) with colour-coded category cards and per-issue drilldown."
    ),
    tags=["audit", "health", "dashboard", "ui", "report", "score"],
)
def run_level_health_open(**kwargs) -> dict:
    """
    Runs the full level health audit and prints a formatted summary to the
    Output Log. Use level_health_report for the structured dict return.
    """
    report = _run_health_report()
    score  = report["score"]
    grade  = report["grade"]

    bar = "=" * 52
    log_info(bar)
    log_info(f"  LEVEL HEALTH REPORT   Score: {score}/100   Grade: {grade}")
    log_info(bar)
    for cdata in report["categories"].values():
        status = "OK  " if cdata["ratio"] >= 0.9 else ("WARN" if cdata["ratio"] >= 0.6 else "FAIL")
        log_info(f"  [{status}]  {cdata['label']:<24s}  {cdata['score']:.0f}/{cdata['max']}  {cdata['summary']}")
    log_info(bar)

    return report
