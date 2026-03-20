# UEFN Toolbelt — Tool Status & Testing

UEFN Toolbelt contains 117+ tools across 21 modules. Because many tools actively modify the viewport, spawn actors, or depend on specific Content Browser selections, **they cannot all be automatically executed in a single smoke test.**

This document outlines the current testing status of the toolbelt and categorizes which tools are verified by the automated smoke test, and which require manual verification.

## 🟢 Layer 3 Execution Verified (Safe Tools)
These tools do not require any actors to be selected or a specific level to be open. They are executed automatically during the `smoke_test.py` run to verify that the toolbelt execution pipeline is fully functional end-to-end.

*   `api_list_subsystems` (API Explorer)
*   `verse_list_snippets` (Verse Helpers)
*   `scaffold_list_templates` (Project)
*   `mcp_status` (MCP Bridge)
*   `snapshot_list` (Level Snapshot)
*   `material_list_presets` (Materials)
*   `text_list_styles` (Text & Signs)

*The smoke test verifies these tools complete execution without throwing exceptions.*

## 🟡 Requires Manual Verification (Level State Dependent)
These tools require a live level, but do not necessarily need actors to be selected. They spawn new actors or modify the environment globally.

*   `arena_generate`
*   `text_wait_and_print`
*   `text_paint_grid`
*   `pattern_*` (Grid, Circle, Arc, Spiral, etc.)
*   `mcp_start` / `mcp_stop`

## 🟠 Requires Manual Verification (Actor Selection Dependent)
These tools **must** have valid actors selected in the UEFN viewport to function. Running them without a selection will result in a graceful warning, but testing their actual logic requires a human.

*   `material_apply_preset`
*   `material_bulk_swap`
*   `bulk_align` / `bulk_distribute` / `bulk_randomize`
*   `spline_place_props` (requires a Spline actor)
*   `text_label_selection`
*   `verse_gen_device_declarations`
*   `screenshot_focus_selection`

## 🔴 Requires Manual Verification (Content Browser Dependent)
These tools require specific assets (Static Meshes, Textures, Folders) to be selected in the Content Browser or exist at a specific path.

*   `lod_auto_generate_folder`
*   `smart_importer` tools
*   `rename_enforce_conventions`
*   `tag_add` / `tag_remove`
*   `memory_scan_textures`

---

## Contributing & Testing Protocol

If you are contributing a new tool or modifying an existing one:

1.  **If it's a "Safe Tool"**: Please ensure it handles empty states gracefully (e.g., if there are no snapshots, `snapshot_list` should just print "0 snapshots" and exit cleanly). You can add it to the execution list in `tests/smoke_test.py`.
2.  **If it requires context**: You must manually verify the tool in a throwaway UEFN project before submitting a PR.
3.  **Always run `smoke_test.py`** before committing to ensure you haven't broken the registry or layer imports.
