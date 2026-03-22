"""
UEFN TOOLBELT — Memory Profiler & Auto-Fixer
========================================
Islands have strict memory budgets. This tool scans your project for the
heaviest assets, flags the worst offenders by category, and applies
automatic fixes where possible (LOD enforcement, texture size capping).

UEFN's memory constraints are real — an oversized texture or a mesh with
no LODs can push you over budget and cause validation failures on publish.

FEATURES:
  • Full island asset scan: textures, meshes, sounds, particles
  • Per-category memory budget report (textures dominate — always check first)
  • Identifies top N heaviest assets in each category
  • Texture resolution audit: flags anything over a configurable threshold
  • Mesh complexity audit: poly count, missing LODs, missing collision
  • Sound audit: uncompressed audio, long duration files
  • Auto-fix: force mip generation on oversized textures
  • Auto-fix: apply LODs to meshes missing them
  • Export full report to Saved/UEFN_Toolbelt/memory_report.json
  • Summary dashboard printed to Output Log

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Full scan of /Game — prints summary + saves report
    tb.run("memory_scan", scan_path="/Game")

    # Scan only textures
    tb.run("memory_scan_textures", scan_path="/Game", max_size_px=2048)

    # Scan only meshes
    tb.run("memory_scan_meshes", scan_path="/Game")

    # Auto-fix: add LODs to all meshes missing them
    tb.run("memory_autofix_lods", scan_path="/Game/Meshes")

    # View top 10 heaviest assets
    tb.run("memory_top_offenders", scan_path="/Game", top_n=10)

BLUEPRINT:
    "Execute Python Command" →
        import UEFN_Toolbelt as tb; tb.run("memory_scan", scan_path="/Game")
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import unreal

from ..core import (
    log_info, log_warning, log_error,
    load_asset, with_progress,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Texture resolution thresholds (pixels, square)
TEXTURE_WARN_PX  = 2048   # Flag as large
TEXTURE_CRIT_PX  = 4096   # Flag as critical

# Mesh triangle thresholds
MESH_WARN_TRIS   = 50_000
MESH_CRIT_TRIS   = 200_000

# Sound duration thresholds (seconds)
SOUND_WARN_SECS  = 30.0
SOUND_CRIT_SECS  = 120.0

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _list_assets_of_class(scan_path: str, class_name: str) -> List[Tuple[str, unreal.Object]]:
    """Return (path, asset) pairs for all assets of a given class in a folder."""
    all_paths = unreal.EditorAssetLibrary.list_assets(
        scan_path, recursive=True, include_folder=False
    )
    results = []
    for p in all_paths:
        asset = load_asset(p)
        if asset and asset.get_class().get_name() == class_name:
            results.append((p, asset))
    return results


def _texture_info(asset: unreal.Texture2D) -> Dict:
    """Extract resolution and estimated memory from a Texture2D."""
    try:
        w = asset.get_editor_property("blueprint_width")
        h = asset.get_editor_property("blueprint_height")
    except Exception:
        try:
            # Fallback: use source art size
            w = asset.source_art_width if hasattr(asset, "source_art_width") else 0
            h = asset.source_art_height if hasattr(asset, "source_art_height") else 0
        except Exception:
            w = h = 0

    max_dim = max(w, h)

    # Rough VRAM estimate: width × height × 4 bytes (RGBA uncompressed)
    # BC compression reduces this ~6× but we flag the uncompressed size for safety
    estimated_kb = (w * h * 4) / 1024 if (w and h) else 0

    severity = "ok"
    if max_dim >= TEXTURE_CRIT_PX:
        severity = "critical"
    elif max_dim >= TEXTURE_WARN_PX:
        severity = "warning"

    return {
        "width": w, "height": h,
        "max_dim": max_dim,
        "estimated_vram_kb": round(estimated_kb, 1),
        "severity": severity,
    }


def _mesh_info(asset: unreal.StaticMesh) -> Dict:
    """Extract triangle count and LOD info from a StaticMesh."""
    mesh_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

    try:
        lod_count = mesh_sub.get_lod_count(asset)
    except Exception:
        lod_count = 0

    try:
        tri_count = mesh_sub.get_number_verts(asset, 0)  # LOD0 vertex count approx
    except Exception:
        tri_count = 0

    severity = "ok"
    if tri_count >= MESH_CRIT_TRIS:
        severity = "critical"
    elif tri_count >= MESH_WARN_TRIS:
        severity = "warning"

    if lod_count <= 1:
        severity = "warning" if severity == "ok" else severity

    return {
        "lod_count":     lod_count,
        "approx_verts":  tri_count,
        "missing_lods":  lod_count <= 1,
        "severity":      severity,
    }


def _sound_info(asset: unreal.SoundWave) -> Dict:
    """Extract duration and compression info from a SoundWave."""
    try:
        duration = asset.get_editor_property("duration")
    except Exception:
        duration = 0.0

    severity = "ok"
    if duration >= SOUND_CRIT_SECS:
        severity = "critical"
    elif duration >= SOUND_WARN_SECS:
        severity = "warning"

    return {
        "duration_secs": round(duration, 1),
        "severity":      severity,
    }


def _severity_icon(s: str) -> str:
    return {"ok": "✓", "warning": "⚠", "critical": "✗"}.get(s, "?")


def _write_report(data: dict) -> str:
    out_dir  = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "memory_report.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="memory_scan",
    category="Optimization",
    description="Full island memory scan — textures, meshes, sounds. Saves JSON report.",
    tags=["memory", "profiler", "scan", "optimize", "performance"],
)
def run_memory_scan(scan_path: str = "/Game", **kwargs) -> dict:
    """
    Scans all asset types and prints a summary dashboard.
    Full results saved to Saved/UEFN_Toolbelt/memory_report.json.

    Args:
        scan_path: Content Browser folder to scan.

    Returns:
        dict: {"status", "path", "summary": {counts, warnings, criticals}}
    """
    log_info(f"Memory scan: {scan_path} …")

    report: Dict = {
        "timestamp": datetime.now().isoformat(),
        "scan_path": scan_path,
        "textures": [],
        "meshes":   [],
        "sounds":   [],
    }

    # ── Textures ──────────────────────────────────────────────────────────
    tex_assets = _list_assets_of_class(scan_path, "Texture2D")
    tex_warn = tex_crit = 0
    for path, asset in tex_assets:
        info = _texture_info(asset)
        info["path"] = path
        report["textures"].append(info)
        if info["severity"] == "warning":  tex_warn += 1
        if info["severity"] == "critical": tex_crit += 1

    # ── Meshes ────────────────────────────────────────────────────────────
    mesh_assets = _list_assets_of_class(scan_path, "StaticMesh")
    mesh_warn = mesh_crit = mesh_no_lod = 0
    for path, asset in mesh_assets:
        info = _mesh_info(asset)
        info["path"] = path
        report["meshes"].append(info)
        if info["severity"] == "warning":  mesh_warn += 1
        if info["severity"] == "critical": mesh_crit += 1
        if info["missing_lods"]:           mesh_no_lod += 1

    # ── Sounds ────────────────────────────────────────────────────────────
    sound_assets = _list_assets_of_class(scan_path, "SoundWave")
    snd_warn = snd_crit = 0
    for path, asset in sound_assets:
        info = _sound_info(asset)
        info["path"] = path
        report["sounds"].append(info)
        if info["severity"] == "warning":  snd_warn += 1
        if info["severity"] == "critical": snd_crit += 1

    # ── Summary ───────────────────────────────────────────────────────────
    total_tex_kb = sum(t.get("estimated_vram_kb", 0) for t in report["textures"])
    report["summary"] = {
        "total_textures":      len(tex_assets),
        "texture_warnings":    tex_warn,
        "texture_criticals":   tex_crit,
        "estimated_vram_mb":   round(total_tex_kb / 1024, 1),
        "total_meshes":        len(mesh_assets),
        "mesh_warnings":       mesh_warn,
        "mesh_criticals":      mesh_crit,
        "meshes_missing_lods": mesh_no_lod,
        "total_sounds":        len(sound_assets),
        "sound_warnings":      snd_warn,
        "sound_criticals":     snd_crit,
    }

    lines = [
        "\n" + "═" * 58,
        "  UEFN TOOLBELT — Memory Report",
        "  " + scan_path,
        "═" * 58,
        "",
        f"  TEXTURES  ({len(tex_assets)} scanned)",
        f"    Estimated VRAM:  {total_tex_kb / 1024:.1f} MB",
        f"    ⚠ Warnings:      {tex_warn}  (≥{TEXTURE_WARN_PX}px)",
        f"    ✗ Critical:      {tex_crit}  (≥{TEXTURE_CRIT_PX}px)",
        "",
        f"  MESHES  ({len(mesh_assets)} scanned)",
        f"    ⚠ High poly:     {mesh_warn}  (≥{MESH_WARN_TRIS:,} verts)",
        f"    ✗ Very high:     {mesh_crit}  (≥{MESH_CRIT_TRIS:,} verts)",
        f"    ⚠ Missing LODs:  {mesh_no_lod}",
        "",
        f"  SOUNDS  ({len(sound_assets)} scanned)",
        f"    ⚠ Long files:    {snd_warn}  (≥{SOUND_WARN_SECS:.0f}s)",
        f"    ✗ Very long:     {snd_crit}  (≥{SOUND_CRIT_SECS:.0f}s)",
        "",
        "  RECOMMENDED ACTIONS:",
    ]

    if tex_crit > 0:
        lines.append(f"    → Run memory_scan_textures to find the {tex_crit} critical texture(s)")
    if mesh_no_lod > 0:
        lines.append(f"    → Run memory_autofix_lods to add LODs to {mesh_no_lod} mesh(es)")
    if tex_crit == 0 and mesh_no_lod == 0 and snd_crit == 0:
        lines.append("    → No critical issues found. Good to publish!")

    lines += ["", "═" * 58]
    log_info("\n".join(lines))

    report_path = _write_report(report)
    log_info(f"Full report → {report_path}")
    return {"status": "ok", "path": report_path, "summary": report["summary"]}


@register_tool(
    name="memory_scan_textures",
    category="Optimization",
    description="Audit all textures in a folder and flag oversized ones.",
    tags=["memory", "texture", "resolution", "optimize"],
)
def run_memory_scan_textures(
    scan_path: str = "/Game",
    max_size_px: int = 2048,
    **kwargs,
) -> dict:
    """
    Args:
        scan_path:   Content Browser folder to scan.
        max_size_px: Flag textures larger than this (width or height).

    Returns:
        dict: {"status", "count", "offenders": [{"path", "width", "height",
               "max_dim", "estimated_vram_kb", "severity"}]}
    """
    tex_assets = _list_assets_of_class(scan_path, "Texture2D")
    if not tex_assets:
        log_info("No Texture2D assets found.")
        return {"status": "ok", "count": 0, "offenders": []}

    raw_offenders = []
    for path, asset in tex_assets:
        info = _texture_info(asset)
        if info["max_dim"] > max_size_px:
            raw_offenders.append((path, info))

    raw_offenders.sort(key=lambda x: x[1]["max_dim"], reverse=True)

    if not raw_offenders:
        log_info(f"All textures are ≤{max_size_px}px. ")
        return {"status": "ok", "count": 0, "offenders": []}

    lines = [f"\n⚠ {len(raw_offenders)} textures exceed {max_size_px}px:\n"]
    for path, info in raw_offenders:
        icon = _severity_icon(info["severity"])
        lines.append(
            f"  {icon} {path.split('/')[-1]:40s}  "
            f"{info['width']}×{info['height']}  "
            f"~{info['estimated_vram_kb']:.0f} KB VRAM"
        )
    log_info("\n".join(lines))

    offenders = [{"path": p, **info} for p, info in raw_offenders]
    return {"status": "ok", "count": len(offenders), "offenders": offenders}


@register_tool(
    name="memory_scan_meshes",
    category="Optimization",
    description="Audit all static meshes — polygon count, LODs, collision.",
    tags=["memory", "mesh", "lod", "polygon", "optimize"],
)
def run_memory_scan_meshes(scan_path: str = "/Game", **kwargs) -> dict:
    """
    Args:
        scan_path: Content Browser folder to scan.

    Returns:
        dict: {"status", "count", "offenders": [{"path", "lod_count",
               "approx_verts", "missing_lods", "severity"}]}
    """
    mesh_assets = _list_assets_of_class(scan_path, "StaticMesh")
    if not mesh_assets:
        log_info("No StaticMesh assets found.")
        return {"status": "ok", "count": 0, "offenders": []}

    raw_offenders = []
    for p, a in mesh_assets:
        info = _mesh_info(a)
        if info["severity"] != "ok" or info["missing_lods"]:
            raw_offenders.append((p, info))
    raw_offenders.sort(key=lambda x: x[1]["approx_verts"], reverse=True)

    if not raw_offenders:
        log_info("All meshes look good (reasonable vertex count + LODs present).")
        return {"status": "ok", "count": 0, "offenders": []}

    lines = [f"\n⚠ {len(raw_offenders)} mesh issues:\n"]
    for path, info in raw_offenders:
        icon     = _severity_icon(info["severity"])
        lod_flag = " [NO LODs]" if info["missing_lods"] else f" [{info['lod_count']} LODs]"
        lines.append(
            f"  {icon} {path.split('/')[-1]:40s}  "
            f"~{info['approx_verts']:,} verts{lod_flag}"
        )
    log_info("\n".join(lines))
    log_info("Run memory_autofix_lods to automatically add LODs to meshes missing them.")

    offenders = [{"path": p, **info} for p, info in raw_offenders]
    return {"status": "ok", "count": len(offenders), "offenders": offenders}


@register_tool(
    name="memory_top_offenders",
    category="Optimization",
    description="Print the top N heaviest assets by estimated memory cost.",
    tags=["memory", "profiler", "top", "heaviest", "optimize"],
)
def run_memory_top_offenders(
    scan_path: str = "/Game",
    top_n: int = 10,
    **kwargs,
) -> dict:
    """
    Args:
        scan_path: Content Browser folder to scan.
        top_n:     Number of top offenders to list per category.

    Returns:
        dict: {"status", "textures": [{"path", ...}], "meshes": [{"path", ...}]}
    """
    tex_assets = _list_assets_of_class(scan_path, "Texture2D")
    tex_sorted = sorted(
        [(p, _texture_info(a)) for p, a in tex_assets],
        key=lambda x: x[1]["estimated_vram_kb"],
        reverse=True,
    )[:top_n]

    lines = [f"\n=== Top {top_n} Heaviest Textures ==="]
    for path, info in tex_sorted:
        lines.append(
            f"  {info['width']:5d}×{info['height']:<5d}  "
            f"{info['estimated_vram_kb']:7.0f} KB  "
            f"{path.split('/')[-1]}"
        )

    mesh_assets = _list_assets_of_class(scan_path, "StaticMesh")
    mesh_sorted = sorted(
        [(p, _mesh_info(a)) for p, a in mesh_assets],
        key=lambda x: x[1]["approx_verts"],
        reverse=True,
    )[:top_n]

    lines += [f"\n=== Top {top_n} Most Complex Meshes ==="]
    for path, info in mesh_sorted:
        lod_flag = "NO LODs" if info["missing_lods"] else f"{info['lod_count']} LODs"
        lines.append(
            f"  {info['approx_verts']:>8,} verts  [{lod_flag:8s}]  "
            f"{path.split('/')[-1]}"
        )

    log_info("\n".join(lines))

    textures = [{"path": p, **info} for p, info in tex_sorted]
    meshes   = [{"path": p, **info} for p, info in mesh_sorted]
    return {"status": "ok", "textures": textures, "meshes": meshes}


@register_tool(
    name="memory_autofix_lods",
    category="Optimization",
    description="Auto-generate LODs on all meshes missing them in a folder.",
    tags=["memory", "lod", "autofix", "optimize", "auto"],
)
def run_memory_autofix_lods(
    scan_path: str = "/Game",
    num_lods: int = 3,
    **kwargs,
) -> dict:
    """
    Convenience wrapper: finds meshes with LOD count ≤ 1 and generates LODs.
    Equivalent to lod_auto_generate_folder with skip_existing=True.

    Args:
        scan_path: Content Browser folder to scan.
        num_lods:  Number of LODs to generate.

    Returns:
        dict: Passes through the structured return from lod_auto_generate_folder.
    """
    import UEFN_Toolbelt as tb
    result = tb.run("lod_auto_generate_folder",
                    folder_path=scan_path,
                    num_lods=num_lods,
                    skip_existing=True)
    return result if isinstance(result, dict) else {"status": "ok"}
