"""
UEFN TOOLBELT — Blueprint Tools
==================================
Tools for listing, inspecting, and compiling Blueprint assets.

What Python CAN do:
  • List all Blueprint assets in a folder
  • Inspect variables, functions, and parent class of a Blueprint
  • Audit Blueprints for compile errors
  • Compile all Blueprints in a folder

What Python CANNOT do:
  • Edit Blueprint graph nodes (graph editing is UI-only)
  • Create new Blueprint classes from scratch via Python
  • Call Blueprint functions at game runtime (editor-only)
  • Modify Blueprint pin connections

API: EditorBlueprintLibrary, AssetRegistry, EditorAssetLibrary
"""

from __future__ import annotations

import unreal

from ..core import api_unavailable, log_error, log_info, log_warning, missing_unreal_apis
from ..registry import register_tool

# unreal.* names this module uses but does not require.
# Removed in UEFN 42.00 (UE 6.0). Guarded by missing_unreal_apis().
__optional_unreal_apis__ = (
    "EditorBlueprintLibrary",
)


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="blueprint_list",
    category="Blueprints",
    description=(
        "List all Blueprint assets in a Content Browser folder. "
        "Returns asset paths, native parent class, and Blueprint type for each. "
        "Use this to inventory all custom Blueprints in the project."
    ),
    tags=["blueprint", "list", "assets", "scan"],
    example='tb.run("blueprint_list", scan_path="/Game/Blueprints")',
)
def run_blueprint_list(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=["Blueprint"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        results = []
        for a in assets:
            results.append({
                "name": str(a.asset_name),
                "path": str(a.package_name),
                "parent_class": str(a.get_tag_value("NativeParentClass") or "unknown"),
                "blueprint_type": str(a.get_tag_value("BlueprintType") or "unknown"),
            })
        log_info(f"[blueprint_list] {len(results)} Blueprint(s) in {scan_path}")
        return {"status": "ok", "count": len(results), "blueprints": results}
    except Exception as e:
        log_error(f"[blueprint_list] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="blueprint_inspect",
    category="Blueprints",
    description=(
        "Inspect a Blueprint asset — returns variables, functions, and parent class. "
        "Useful for auditing Blueprint APIs before AI-driven device integration. "
        "Returns up to 50 variables and all readable function names."
    ),
    tags=["blueprint", "inspect", "variables", "functions", "class"],
    example='tb.run("blueprint_inspect", asset_path="/Game/Blueprints/BP_MyDevice")',
)
def run_blueprint_inspect(asset_path: str = "", **kwargs) -> dict:
    _missing = missing_unreal_apis("EditorBlueprintLibrary")
    if _missing:
        return api_unavailable("blueprint_inspect", _missing)
    if not asset_path:
        return {"status": "error", "message": "asset_path is required."}
    try:
        bp = unreal.EditorAssetLibrary.load_asset(asset_path)
        if bp is None:
            return {"status": "error", "message": f"Could not load asset at '{asset_path}'."}
        if not isinstance(bp, unreal.Blueprint):
            return {"status": "error", "message": f"Asset at '{asset_path}' is not a Blueprint."}

        parent_class = "unknown"
        try:
            pc = bp.get_editor_property("parent_class")
            parent_class = str(pc) if pc else "unknown"
        except Exception:
            pass

        variables = []
        try:
            vars_list = unreal.EditorBlueprintLibrary.get_blueprint_variables(bp)
            for v in (vars_list or [])[:50]:
                try:
                    variables.append(str(v.variable_name))
                except Exception:
                    try:
                        variables.append(str(v))
                    except Exception:
                        pass
        except Exception as ex:
            log_warning(f"[blueprint_inspect] Could not read variables: {ex}")

        functions = []
        try:
            func_list = unreal.EditorBlueprintLibrary.get_blueprint_function_names(bp)
            functions = [str(f) for f in (func_list or [])]
        except Exception as ex:
            log_warning(f"[blueprint_inspect] Could not read functions: {ex}")

        log_info(f"[blueprint_inspect] {asset_path}: {len(variables)} vars, {len(functions)} funcs")
        return {
            "status": "ok",
            "asset_path": asset_path,
            "parent_class": parent_class,
            "variable_count": len(variables),
            "variables": variables,
            "function_count": len(functions),
            "functions": functions,
        }
    except Exception as e:
        log_error(f"[blueprint_inspect] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="blueprint_audit",
    category="Blueprints",
    description=(
        "Audit all Blueprint assets in a folder for compilation issues. "
        "Loads each Blueprint and checks its compile status property. "
        "Returns a health report — run blueprint_compile_folder to fix issues."
    ),
    tags=["blueprint", "audit", "compile", "health"],
    example='tb.run("blueprint_audit", scan_path="/Game/Blueprints")',
)
def run_blueprint_audit(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=["Blueprint"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        issues = []
        clean = []

        for a in assets:
            name = str(a.asset_name)
            path = str(a.package_name)
            try:
                bp = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if not isinstance(bp, unreal.Blueprint):
                    issues.append({"name": name, "path": path, "issue": "Not a Blueprint"})
                    continue
                status = "unknown"
                try:
                    status = str(bp.get_editor_property("status"))
                except Exception:
                    pass
                if "error" in status.lower():
                    issues.append({"name": name, "path": path, "issue": f"Compile status: {status}"})
                else:
                    clean.append(name)
            except Exception as ex:
                issues.append({"name": name, "path": path, "issue": f"Failed to load: {ex}"})

        log_info(f"[blueprint_audit] {len(clean)} clean, {len(issues)} issues in {scan_path}")
        return {
            "status": "ok",
            "total": len(assets),
            "clean": len(clean),
            "issues": len(issues),
            "issue_list": issues,
        }
    except Exception as e:
        log_error(f"[blueprint_audit] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="blueprint_compile_folder",
    category="Blueprints",
    description=(
        "Compile all Blueprint assets in a folder using EditorBlueprintLibrary. "
        "Always dry_run=True first — compiling many Blueprints can be slow. "
        "Run blueprint_audit first to identify which Blueprints need fixing."
    ),
    tags=["blueprint", "compile", "batch", "fix"],
    example='tb.run("blueprint_compile_folder", scan_path="/Game/Blueprints", dry_run=False)',
)
def run_blueprint_compile_folder(
    scan_path: str = "/Game/",
    dry_run: bool = True,
    max_assets: int = 50,
    **kwargs,
) -> dict:
    _missing = missing_unreal_apis("EditorBlueprintLibrary")
    if _missing:
        return api_unavailable("blueprint_compile_folder", _missing)
    try:
        filt = unreal.ARFilter(
            class_names=["Blueprint"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_assets]
        compiled = []
        errors = []

        for a in assets:
            name = str(a.asset_name)
            try:
                if not dry_run:
                    bp = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                    if isinstance(bp, unreal.Blueprint):
                        unreal.EditorBlueprintLibrary.compile_blueprint(bp)
                compiled.append(name)
            except Exception as ex:
                errors.append({"name": name, "error": str(ex)})

        action = "Would compile" if dry_run else "Compiled"
        log_info(f"[blueprint_compile_folder] {action} {len(compiled)} Blueprint(s) in {scan_path}")
        return {
            "status": "ok",
            "dry_run": dry_run,
            "compiled": len(compiled),
            "errors": errors,
            "names": compiled,
        }
    except Exception as e:
        log_error(f"[blueprint_compile_folder] {e}")
        return {"status": "error", "message": str(e)}
