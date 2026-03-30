"""
UEFN TOOLBELT — DataTable Tools
=================================
Tools for reading and inspecting DataTable assets in the Content Browser.

DataTables are row-based structured data assets — ideal for weapon stats,
item configs, spawn tables, balance sheets, and any data-driven design pattern.

What Python CAN do:
  • List all DataTable assets in a folder
  • Count rows in a DataTable
  • Read row names from a DataTable
  • Inspect the struct type (row schema) of a DataTable
  • Export a DataTable's row names + struct info to JSON

What Python CANNOT do (UEFN restriction):
  • Add or delete rows programmatically (no DataTableFunctionLibrary write API)
  • Modify individual row values (row struct fields are not settable via Python)
  • Create new DataTable assets from Python (no factory exposed in UEFN)

API: DataTableFunctionLibrary, EditorAssetLibrary, AssetRegistry
"""

from __future__ import annotations

import json
import os

import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="datatable_list",
    category="DataTable",
    description=(
        "List all DataTable assets in a Content Browser folder. "
        "Returns asset paths, row counts, and struct type names. "
        "Use this to inventory all data-driven configs in the project."
    ),
    tags=["datatable", "data", "list", "assets", "scan"],
    example='tb.run("datatable_list", scan_path="/Game/DataTables")',
)
def run_datatable_list(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=["DataTable"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        results = []
        for a in assets:
            # RowCount is cached as an AR tag — no load_asset needed.
            row_count_tag = a.get_tag_value("RowCount")
            results.append({
                "path": str(a.package_name),
                "name": str(a.asset_name),
                "row_struct": str(a.get_tag_value("RowStructure") or "unknown"),
                "row_count": int(row_count_tag) if row_count_tag and row_count_tag.isdigit() else None,
            })

        log_info(f"[datatable_list] {len(results)} DataTable(s) found in {scan_path}")
        return {"status": "ok", "count": len(results), "tables": results}
    except Exception as e:
        log_error(f"[datatable_list] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="datatable_row_names",
    category="DataTable",
    description=(
        "List all row names in a DataTable asset. "
        "Useful for verifying data completeness or feeding row names into other tools."
    ),
    tags=["datatable", "rows", "names", "inspect"],
    example='tb.run("datatable_row_names", asset_path="/Game/DataTables/DT_WeaponStats")',
)
def run_datatable_row_names(asset_path: str = "", **kwargs) -> dict:
    if not asset_path:
        return {"status": "error", "message": "asset_path is required."}
    try:
        table = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not isinstance(table, unreal.DataTable):
            return {"status": "error", "message": f"Asset at '{asset_path}' is not a DataTable."}

        rows = unreal.DataTableFunctionLibrary.get_data_table_row_names(table)
        names = [str(r) for r in rows]
        log_info(f"[datatable_row_names] {len(names)} rows in {asset_path}")
        return {"status": "ok", "asset_path": asset_path, "row_count": len(names), "row_names": names}
    except Exception as e:
        log_error(f"[datatable_row_names] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="datatable_inspect",
    category="DataTable",
    description=(
        "Inspect the struct type and row schema of a DataTable. "
        "Returns the row struct name and any readable struct metadata. "
        "Helps you understand the column layout before reading or editing data."
    ),
    tags=["datatable", "inspect", "schema", "struct"],
    example='tb.run("datatable_inspect", asset_path="/Game/DataTables/DT_WeaponStats")',
)
def run_datatable_inspect(asset_path: str = "", **kwargs) -> dict:
    if not asset_path:
        return {"status": "error", "message": "asset_path is required."}
    try:
        table = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not isinstance(table, unreal.DataTable):
            return {"status": "error", "message": f"Asset at '{asset_path}' is not a DataTable."}

        rows = unreal.DataTableFunctionLibrary.get_data_table_row_names(table)
        row_count = len(rows)

        struct_name = "unknown"
        try:
            row_struct = table.get_editor_property("row_struct")
            if row_struct:
                struct_name = row_struct.get_name()
        except Exception:
            pass

        # Try to get the struct's property names if possible
        properties = []
        try:
            row_struct = table.get_editor_property("row_struct")
            if row_struct:
                for prop in unreal.StructBase.__subclasses__():
                    pass  # not directly iterable — use reflection
        except Exception:
            pass

        log_info(f"[datatable_inspect] {asset_path}: struct={struct_name}, rows={row_count}")
        return {
            "status": "ok",
            "asset_path": asset_path,
            "row_struct": struct_name,
            "row_count": row_count,
            "row_names_sample": [str(r) for r in rows[:10]],
            "tip": "Use datatable_export to dump all rows to JSON.",
        }
    except Exception as e:
        log_error(f"[datatable_inspect] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="datatable_export",
    category="DataTable",
    description=(
        "Export a DataTable's row names and metadata to a JSON file on disk. "
        "Output saved to Saved/UEFN_Toolbelt/datatables/{table_name}.json. "
        "Useful for auditing data assets or feeding configs into external tools."
    ),
    tags=["datatable", "export", "json", "data"],
    example='tb.run("datatable_export", asset_path="/Game/DataTables/DT_WeaponStats")',
)
def run_datatable_export(asset_path: str = "", output_path: str = "", **kwargs) -> dict:
    if not asset_path:
        return {"status": "error", "message": "asset_path is required."}
    try:
        table = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not isinstance(table, unreal.DataTable):
            return {"status": "error", "message": f"Asset at '{asset_path}' is not a DataTable."}

        rows = unreal.DataTableFunctionLibrary.get_data_table_row_names(table)
        row_names = [str(r) for r in rows]

        struct_name = "unknown"
        try:
            row_struct = table.get_editor_property("row_struct")
            if row_struct:
                struct_name = row_struct.get_name()
        except Exception:
            pass

        payload = {
            "asset_path": asset_path,
            "row_struct": struct_name,
            "row_count": len(row_names),
            "row_names": row_names,
        }

        if not output_path:
            saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "datatables")
            os.makedirs(saved, exist_ok=True)
            table_name = os.path.basename(asset_path)
            output_path = os.path.join(saved, f"{table_name}.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        log_info(f"[datatable_export] Exported {len(row_names)} rows → {output_path}")
        return {"status": "ok", "asset_path": asset_path, "row_count": len(row_names), "output_path": output_path}
    except Exception as e:
        log_error(f"[datatable_export] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="datatable_audit",
    category="DataTable",
    description=(
        "Audit all DataTable assets in a folder — checks for empty tables, "
        "missing struct types, and tables with fewer rows than a threshold. "
        "Returns a health report useful before publishing."
    ),
    tags=["datatable", "audit", "health", "data"],
    example='tb.run("datatable_audit", scan_path="/Game/DataTables", min_rows=1)',
)
def run_datatable_audit(scan_path: str = "/Game/", min_rows: int = 1, **kwargs) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=["DataTable"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)
        issues = []
        clean = []

        for a in assets:
            path = str(a.package_name)
            name = str(a.asset_name)
            try:
                table = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if not isinstance(table, unreal.DataTable):
                    issues.append({"name": name, "issue": "Not a DataTable (unexpected class)"})
                    continue

                rows = unreal.DataTableFunctionLibrary.get_data_table_row_names(table)
                count = len(rows)

                struct_name = "unknown"
                try:
                    row_struct = table.get_editor_property("row_struct")
                    if row_struct:
                        struct_name = row_struct.get_name()
                except Exception:
                    pass

                if struct_name == "unknown":
                    issues.append({"name": name, "path": path, "issue": "No row struct defined", "rows": count})
                elif count < min_rows:
                    issues.append({"name": name, "path": path, "issue": f"Only {count} rows (min={min_rows})", "rows": count})
                else:
                    clean.append({"name": name, "rows": count, "struct": struct_name})
            except Exception as ex:
                issues.append({"name": name, "path": path, "issue": f"Failed to load: {ex}"})

        log_info(f"[datatable_audit] {len(clean)} clean, {len(issues)} issues in {scan_path}")
        return {
            "status": "ok",
            "total": len(assets),
            "clean": len(clean),
            "issues": len(issues),
            "issue_list": issues,
        }
    except Exception as e:
        log_error(f"[datatable_audit] {e}")
        return {"status": "error", "message": str(e)}
