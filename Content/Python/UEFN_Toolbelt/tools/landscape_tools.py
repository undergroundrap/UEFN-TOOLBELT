"""
UEFN TOOLBELT — Landscape Tools
==================================
Tools for inspecting and auditing Landscape actors in the level.

What Python CAN do:
  • List all Landscape actors in the current level
  • Inspect material, component count, section size, and render properties
  • Audit landscapes for missing materials or high component counts
  • Assign a material to a Landscape actor

What Python CANNOT do:
  • Edit heightmap data (height/weight painting is editor UI only)
  • Add or remove landscape layers programmatically
  • Import heightmaps from external files via Python
  • Create new Landscape actors (no factory exposed in UEFN Python)

API: EditorActorSubsystem, Landscape, LandscapeProxy, LandscapeComponent
"""

from __future__ import annotations

import unreal

from ..core import log_error, log_info
from ..registry import register_tool


def _actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _get_landscapes():
    """Return all Landscape and LandscapeProxy actors in the current level."""
    all_actors = _actor_sub().get_all_level_actors()
    result = []
    for a in (all_actors or []):
        try:
            if isinstance(a, (unreal.Landscape, unreal.LandscapeProxy)):
                result.append(a)
        except Exception:
            pass
    return result


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="landscape_list",
    category="Landscape",
    description=(
        "List all Landscape actors in the current level. "
        "Returns label, location, assigned material, and component count for each. "
        "Use before landscape_audit to see how many landscapes are in the map."
    ),
    tags=["landscape", "list", "level", "terrain", "scan"],
    example='tb.run("landscape_list")',
)
def run_landscape_list(**kwargs) -> dict:
    try:
        landscapes = _get_landscapes()
        results = []
        for a in landscapes:
            entry = {
                "label": str(a.get_actor_label()),
                "class": type(a).__name__,
            }
            try:
                loc = a.get_actor_location()
                entry["location"] = [round(loc.x), round(loc.y), round(loc.z)]
            except Exception:
                pass
            try:
                mat = a.get_editor_property("landscape_material")
                entry["material"] = str(mat.get_path_name()) if mat else "none"
            except Exception:
                entry["material"] = "unknown"
            try:
                comps = a.get_components_by_class(unreal.LandscapeComponent)
                entry["component_count"] = len(comps) if comps else 0
            except Exception:
                entry["component_count"] = 0
            results.append(entry)

        log_info(f"[landscape_list] {len(results)} landscape actor(s) in level")
        return {"status": "ok", "count": len(results), "landscapes": results}
    except Exception as e:
        log_error(f"[landscape_list] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="landscape_audit",
    category="Landscape",
    description=(
        "Audit all Landscape actors in the level for common issues: "
        "missing material or very high component count (performance risk). "
        "Returns a health report with per-landscape status and issue descriptions."
    ),
    tags=["landscape", "audit", "material", "performance", "health"],
    example='tb.run("landscape_audit", warn_components=256)',
)
def run_landscape_audit(warn_components: int = 256, **kwargs) -> dict:
    try:
        landscapes = _get_landscapes()
        issues = []
        clean = []

        for a in landscapes:
            label = str(a.get_actor_label())
            ls_issues = []

            try:
                mat = a.get_editor_property("landscape_material")
                if not mat:
                    ls_issues.append("No landscape material assigned")
            except Exception:
                pass

            try:
                comps = a.get_components_by_class(unreal.LandscapeComponent)
                count = len(comps) if comps else 0
                if count > warn_components:
                    ls_issues.append(f"High component count: {count} (warn={warn_components})")
            except Exception:
                pass

            if ls_issues:
                issues.append({"label": label, "issues": ls_issues})
            else:
                clean.append(label)

        log_info(f"[landscape_audit] {len(clean)} clean, {len(issues)} with issues")
        return {
            "status": "ok",
            "total": len(landscapes),
            "clean": len(clean),
            "issues": len(issues),
            "issue_list": issues,
        }
    except Exception as e:
        log_error(f"[landscape_audit] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="landscape_info",
    category="Landscape",
    description=(
        "Get detailed info on a Landscape actor: material, component count, "
        "section size, quads per section, and render properties. "
        "Specify label to target a specific landscape, or leave blank for first found."
    ),
    tags=["landscape", "info", "inspect", "components", "sections"],
    example='tb.run("landscape_info", label="Landscape")',
)
def run_landscape_info(label: str = "", **kwargs) -> dict:
    try:
        landscapes = _get_landscapes()
        target = None
        for a in landscapes:
            if not label or label.lower() in str(a.get_actor_label()).lower():
                target = a
                break

        if target is None:
            return {"status": "error", "message": f"No Landscape actor found{' matching ' + repr(label) if label else ''}."}

        info = {
            "label": str(target.get_actor_label()),
            "class": type(target).__name__,
        }

        try:
            loc = target.get_actor_location()
            info["location"] = [round(loc.x), round(loc.y), round(loc.z)]
        except Exception:
            pass

        for prop in ("landscape_material", "component_size_quads", "num_subcomponents",
                     "subsection_size_quads", "static_lighting_resolution"):
            try:
                val = target.get_editor_property(prop)
                info[prop] = str(val) if val is not None else "unknown"
            except Exception:
                pass

        try:
            comps = target.get_components_by_class(unreal.LandscapeComponent)
            info["component_count"] = len(comps) if comps else 0
        except Exception:
            pass

        log_info(f"[landscape_info] {info['label']}: {info.get('component_count', '?')} components")
        return {"status": "ok", **info}
    except Exception as e:
        log_error(f"[landscape_info] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="landscape_set_material",
    category="Landscape",
    description=(
        "Assign a material to a Landscape actor. "
        "Use label to target a specific landscape (leave blank for first found). "
        "Always dry_run=True first — this modifies the landscape material slot."
    ),
    tags=["landscape", "material", "assign", "set"],
    example='tb.run("landscape_set_material", material_path="/Game/Materials/M_Terrain", dry_run=False)',
)
def run_landscape_set_material(
    material_path: str = "",
    label: str = "",
    dry_run: bool = True,
    **kwargs,
) -> dict:
    if not material_path:
        return {"status": "error", "message": "material_path is required."}
    try:
        landscapes = _get_landscapes()
        target = None
        for a in landscapes:
            if not label or label.lower() in str(a.get_actor_label()).lower():
                target = a
                break

        if target is None:
            return {"status": "error", "message": f"No Landscape actor found{' matching ' + repr(label) if label else ''}."}

        mat = unreal.EditorAssetLibrary.load_asset(material_path)
        if mat is None:
            return {"status": "error", "message": f"Could not load material at '{material_path}'."}

        ls_label = str(target.get_actor_label())
        if not dry_run:
            target.set_editor_property("landscape_material", mat)

        action = "Would assign" if dry_run else "Assigned"
        log_info(f"[landscape_set_material] {action} {material_path} → {ls_label}")
        return {
            "status": "ok",
            "dry_run": dry_run,
            "landscape": ls_label,
            "material": material_path,
        }
    except Exception as e:
        log_error(f"[landscape_set_material] {e}")
        return {"status": "error", "message": str(e)}
