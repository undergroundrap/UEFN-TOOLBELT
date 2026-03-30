"""
UEFN TOOLBELT — Curve Asset Tools
===================================
Tools for listing, inspecting, and exporting Curve assets (CurveFloat,
CurveVector, CurveLinearColor). Curves are used throughout UEFN for animation
timelines, material parameter ramps, audio envelopes, and gameplay value curves.

What Python CAN do:
  • List all curve assets (CurveFloat / CurveVector / CurveLinearColor) in a folder
  • Inspect the keys and values of a curve asset
  • Export curve data to JSON for external editing or documentation
  • Create a new CurveFloat asset

What Python CANNOT do:
  • Edit keys in an existing curve asset via Python (set_editor_property is
    not exposed for CurveBase key arrays in UEFN)
  • Create CurveVector / CurveLinearColor assets (no factory exposed)
  • Apply curves to Sequencer tracks directly from Python

API: EditorAssetLibrary, AssetRegistry, CurveFloat, CurveFloatFactory
"""

from __future__ import annotations

import json
import os

import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


_CURVE_CLASSES = ["CurveFloat", "CurveVector", "CurveLinearColor"]


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="curve_list",
    category="Curves",
    description=(
        "List all Curve assets (CurveFloat, CurveVector, CurveLinearColor) in a folder. "
        "Returns asset paths and curve class type for each curve found. "
        "Use curve_type to filter: 'float', 'vector', 'color', or 'all'."
    ),
    tags=["curve", "list", "assets", "animation", "scan"],
    example='tb.run("curve_list", scan_path="/Game/Curves", curve_type="float")',
)
def run_curve_list(scan_path: str = "/Game/", curve_type: str = "all", max_results: int = 200, **kwargs) -> dict:
    try:
        type_map = {
            "float":  ["CurveFloat"],
            "vector": ["CurveVector"],
            "color":  ["CurveLinearColor"],
            "all":    _CURVE_CLASSES,
        }
        class_filter = type_map.get(curve_type.lower(), _CURVE_CLASSES)

        filt = unreal.ARFilter(
            class_names=class_filter,
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        results = [
            {
                "name": str(a.asset_name),
                "path": str(a.package_name),
                "type": str(a.asset_class),
            }
            for a in assets
        ]
        log_info(f"[curve_list] {len(results)} curve(s) in {scan_path}")
        return {"status": "ok", "count": len(results), "curves": results}
    except Exception as e:
        log_error(f"[curve_list] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="curve_inspect",
    category="Curves",
    description=(
        "Inspect the keys and values of a CurveFloat asset. "
        "Returns all key time/value pairs sorted by time. "
        "Useful for reviewing balance curves, animation ramps, or audio envelopes."
    ),
    tags=["curve", "inspect", "keys", "values", "float"],
    example='tb.run("curve_inspect", asset_path="/Game/Curves/CM_DamageFalloff")',
)
def run_curve_inspect(asset_path: str = "", **kwargs) -> dict:
    if not asset_path:
        return {"status": "error", "message": "asset_path is required."}
    try:
        curve = unreal.EditorAssetLibrary.load_asset(asset_path)
        if curve is None:
            return {"status": "error", "message": f"Could not load asset at '{asset_path}'."}

        keys = []
        curve_class = type(curve).__name__

        if isinstance(curve, unreal.CurveFloat):
            try:
                float_curve = curve.get_editor_property("float_curve")
                for key in (float_curve.get_editor_property("keys") or []):
                    try:
                        keys.append({
                            "time": round(key.get_editor_property("time"), 6),
                            "value": round(key.get_editor_property("value"), 6),
                            "interp": str(key.get_editor_property("interp_mode")),
                        })
                    except Exception:
                        pass
            except Exception as ex:
                log_warning(f"[curve_inspect] Could not read CurveFloat keys: {ex}")

        elif isinstance(curve, unreal.CurveLinearColor):
            try:
                for channel_name in ("r", "g", "b", "a"):
                    try:
                        ch_curve = curve.get_editor_property(f"float_curves") or []
                        break
                    except Exception:
                        pass
            except Exception:
                pass
            keys = [{"note": "CurveLinearColor key reading not exposed via Python — use curve_export for JSON dump"}]
        else:
            keys = [{"note": f"{curve_class} key reading not fully exposed via Python — use curve_export for JSON dump"}]

        log_info(f"[curve_inspect] {len(keys)} key(s) in {asset_path}")
        return {
            "status": "ok",
            "asset_path": asset_path,
            "curve_type": curve_class,
            "key_count": len(keys),
            "keys": keys,
        }
    except Exception as e:
        log_error(f"[curve_inspect] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="curve_export",
    category="Curves",
    description=(
        "Export all Curve assets in a folder to a single JSON file on disk. "
        "Output saved to Saved/UEFN_Toolbelt/curves/curve_export.json. "
        "Includes asset paths, class types, and any readable key data."
    ),
    tags=["curve", "export", "json", "data"],
    example='tb.run("curve_export", scan_path="/Game/Curves")',
)
def run_curve_export(scan_path: str = "/Game/", output_path: str = "", **kwargs) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=_CURVE_CLASSES,
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)
        export_data = []

        for a in assets:
            entry = {
                "name": str(a.asset_name),
                "path": str(a.package_name),
                "type": str(a.asset_class),
                "keys": [],
            }
            try:
                curve = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if isinstance(curve, unreal.CurveFloat):
                    float_curve = curve.get_editor_property("float_curve")
                    for key in (float_curve.get_editor_property("keys") or []):
                        try:
                            entry["keys"].append({
                                "time": round(key.get_editor_property("time"), 6),
                                "value": round(key.get_editor_property("value"), 6),
                            })
                        except Exception:
                            pass
            except Exception as ex:
                entry["error"] = str(ex)
            export_data.append(entry)

        if not output_path:
            saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "curves")
            os.makedirs(saved, exist_ok=True)
            output_path = os.path.join(saved, "curve_export.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"scan_path": scan_path, "count": len(export_data), "curves": export_data}, f, indent=2)

        log_info(f"[curve_export] {len(export_data)} curves exported → {output_path}")
        return {"status": "ok", "count": len(export_data), "output_path": output_path}
    except Exception as e:
        log_error(f"[curve_export] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="curve_create",
    category="Curves",
    description=(
        "Create a new CurveFloat asset in the Content Browser. "
        "The asset is created empty — open it in the Curve Editor to add keys. "
        "Name should follow the CM_ prefix convention (e.g. CM_DamageFalloff)."
    ),
    tags=["curve", "create", "float", "new", "asset"],
    example='tb.run("curve_create", name="CM_DamageFalloff", destination="/Game/Curves")',
)
def run_curve_create(
    name: str = "CM_NewCurve",
    destination: str = "/Game/Curves/",
    **kwargs,
) -> dict:
    if not name:
        return {"status": "error", "message": "name is required."}
    try:
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        factory = unreal.CurveFloatFactory()
        dest = destination.rstrip("/")
        new_asset = asset_tools.create_asset(name, dest, unreal.CurveFloat, factory)
        if new_asset is None:
            return {"status": "error", "message": f"Failed to create CurveFloat '{name}' at '{destination}'."}

        unreal.EditorAssetLibrary.save_loaded_asset(new_asset)
        path = f"{dest}/{name}"
        log_info(f"[curve_create] Created CurveFloat: {path}")
        return {"status": "ok", "name": name, "path": path, "tip": "Open in Curve Editor to add keys."}
    except Exception as e:
        log_error(f"[curve_create] {e}")
        return {"status": "error", "message": str(e)}
