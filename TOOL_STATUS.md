# UEFN Toolbelt — Tool Status & Testing

UEFN Toolbelt contains **287 tools across 35+ modules**. Because many tools actively modify the viewport, spawn actors, or depend on specific Content Browser selections, **the `integration_test.py` suite uses temporary fixtures to automate verification of context-dependent tools.**

### Phase 21 — Complete AI Return Loop
As of Phase 21, **every registered tool returns a structured `dict`** — `{"status": "ok"/"error", ...}`. Zero `None` returns remain anywhere in the codebase. This means AI agents using the MCP bridge can act on results programmatically: no log parsing, no guessing. The `describe_tool` MCP command was also added for per-tool manifest lookup.

### ⚠️ Architectural Constraints
*   **Main Thread Lock**: UEFN Python runs on the main render thread. Operations like `time.sleep` in wait loops will **deadlock** the engine, preventing async tasks (like screenshot saves) from completing. Verification logic should avoid blocking waits.
*   **Hot-Reloading**: Use "Nuclear Reload" to clear `sys.modules` cache. **Mandatory**: Must call `tb.register_all_tools()` after reloading to rebuild the registry.

This document outlines the current testing status of the toolbelt and categorizes which tools are verified by the automated smoke test, and which require manual verification.

## 🟡 Automated Verification Status: **186 / 287 Tools (69% Coverage)**
Integration suite has **115 test sections written** (103 verified live + 12 Batch 9 written, pending live UEFN run).

> **Coverage gap:** 75 tools were added after v1.6.0 (zones, stamps, actor org, proximity placement, advanced alignment, signs, audio, post-process, level health, config, lighting extended, world state). Batch 9 integration tests are written and syntax-checked — pending one live UEFN run to confirm green.
>
> **New modules (2026-03-25, pending integration tests):** `niagara_tools` (4), `pcg_tools` (4), `geometry_tools` (5), `movie_render_tools` (3), `viewport_tools` (3), `activity_log_tools` (3) — 22 tools registered, live-tested manually, not yet in the integration suite.

---

## ⛔ Disabled Tools (Known UEFN Crashes)
These tools are registered but intentionally disabled at runtime. Do not attempt to re-enable without resolving the upstream crash.

| Tool | Module | Reason | Quirk |
|---|---|---|---|
| `lod_auto_generate_selection` | `lod_optimizer` | UEFN mesh reduction crash | UEFN_QUIRKS.md #18 |
| `lod_auto_generate_folder` | `lod_optimizer` | UEFN mesh reduction crash | UEFN_QUIRKS.md #18 |

---

## 🟢 Layer 3 Execution Verified (Safe Tools)
These tools do not require any actors to be selected or a specific level to be open. They are executed automatically during the `smoke_test.py` run to verify that the toolbelt execution pipeline is fully functional end-to-end.

*   `api_list_subsystems` (API Explorer)
*   `verse_list_snippets` (Verse Helpers)
*   `scaffold_list_templates` (Project)
*   `mcp_status` (MCP Bridge)
*   `snapshot_list` (Level Snapshot)
*   `material_list_presets` (Materials)
*   `text_list_styles` (Text & Signs)
*   `plugin_validate_all` (Plugin Manager)
*   `plugin_list_custom` (Plugin Manager)
*   `plugin_export_manifest` (Plugin Manager)
*   `config_list` (Config)
*   `stamp_list` (Prefab Stamp)
*   `zone_list` (Zone Tools)
*   `sign_list` (Sign Tools)
*   `entity_list_kits` (Entity Kit)
*   `actor_folder_list` (Actor Org)
*   `audio_list` (Audio Tools)
*   `light_list` (Lighting)

*The smoke test verifies these tools complete execution without throwing exceptions.*

---

## 🛑 Priority Community Verification (Not Covered by Smoke Test)

The automated `smoke_test.py` covers all API discovery, registry loading, and the 🟢 Layer 3 "Safe" tools above. It **cannot** verify the tools that require actual viewport actors or Content Browser selections.

**These core tools are the highest priority for community tracking.**

To contribute: Test a tool against the latest UEFN version. Ensure it works via the PySide6 UI **AND** via the Claude MCP connection, and submit a PR checking the box with today's date and your GitHub username.

---

### 🟡 Requires Manual Verification (Level State Dependent)
These tools require a live level. They spawn new actors or modify the environment globally.

| Tool | UI Verified | AI Verified (MCP) | Tested By | Date |
|---|---|---|---|---|
| `arena_generate` | [A] | [A] | AI | 2026-03-21 |
| `text_wait_and_print` | [A] | [A] | AI | 2026-03-20 |
| `text_paint_grid` | [A] | [A] | AI | 2026-03-20 |
| `pattern_*` (Grid, Circle, Arc, etc.) | [A] | [A] | AI | 2026-03-20 |
| `mcp_start` / `mcp_stop` | [A] | [A] | AI | 2026-03-21 |
| `api_crawl_level_classes` | [A] | [A] | AI | 2026-03-20 |
| `material_glow_pulse_preview` | [A] | [A] | AI | 2026-03-20 |
| `material_team_color_split` | [A] | [A] | AI | 2026-03-20 |
| `material_gradient_painter` | [A] | [A] | AI | 2026-03-20 |
| `import_image_url` | [A] | [A] | AI | 2026-03-22 |
| `import_image_clip` | [A] | [A] | AI | 2026-03-22 |
| `procedural_wire` | [A] | [A] | AI | 2026-03-22 |
| `procedural_scatter` | [A] | [A] | AI | 2026-03-22 |
| `text_voxelize_3d` | [A] | [A] | AI | 2026-03-22 |
| `text_render_tex` | [A] | [A] | AI | 2026-03-22 |
| `material_pattern_painter` | [A] | [A] | AI | 2026-03-20 |
| `text_color_cycle` | [A] | [A] | AI | 2026-03-20 |
| `text_export_manifest` | [A] | [A] | AI | 2026-03-22 |
| `text_apply_translation` | [A] | [A] | AI | 2026-03-22 |
| `zone_spawn` | [ ] | [ ] | — | — |
| `zone_resize_to_selection` | [ ] | [ ] | — | — |
| `zone_snap_to_selection` | [ ] | [ ] | — | — |
| `zone_select_contents` | [ ] | [ ] | — | — |
| `zone_move_contents` | [ ] | [ ] | — | — |
| `zone_fill_scatter` | [ ] | [ ] | — | — |
| `postprocess_spawn` | [ ] | [ ] | — | — |
| `postprocess_set` | [ ] | [ ] | — | — |
| `postprocess_preset` | [ ] | [ ] | — | — |
| `world_settings_set` | [ ] | [ ] | — | — |
| `audio_place` | [ ] | [ ] | — | — |
| `audio_set_volume` | [ ] | [ ] | — | — |
| `audio_set_radius` | [ ] | [ ] | — | — |
| `light_place` | [ ] | [ ] | — | — |
| `light_set` | [ ] | [ ] | — | — |
| `sky_set_time` | [ ] | [ ] | — | — |
| `light_cinematic_preset` | [ ] | [ ] | — | — |
| `light_randomize_sky` | [ ] | [ ] | — | — |
| `world_state_export` | [ ] | [ ] | — | — |
| `device_catalog_scan` | [ ] | [ ] | — | — |
| `level_health_report` | [ ] | [ ] | — | — |
| `rogue_actor_scan` | [ ] | [ ] | — | — |
| `stamp_save` | [ ] | [ ] | — | — |
| `stamp_place` | [ ] | [ ] | — | — |
| `stamp_delete` | [ ] | [ ] | — | — |
| `stamp_export` | [ ] | [ ] | — | — |
| `stamp_import` | [ ] | [ ] | — | — |
| `sign_spawn_bulk` | [ ] | [ ] | — | — |
| `actor_duplicate_offset` | [ ] | [ ] | — | — |
| `actor_copy_to_positions` | [ ] | [ ] | — | — |
| `actor_cluster_to_folder` | [ ] | [ ] | — | — |

---

### 🟠 Requires Manual Verification (Actor Selection Dependent)

| Tool | UI Verified | AI Verified (MCP) | Tested By | Date |
|---|---|---|---|---|
| `pattern_grid` / `circle` | [A] | [A] | AI | 2026-03-20 |
| `pattern_line` / `arc` | [A] | [A] | AI | 2026-03-20 |
| `pattern_spiral` / `wave` | [A] | [A] | AI | 2026-03-20 |
| `bulk_align` / `distribute` / `randomize` | [A] | [A] | AI | 2026-03-20 |
| `bulk_snap_to_grid` | [A] | [A] | AI | 2026-03-20 |
| `bulk_stack` / `reset` | [A] | [A] | AI | 2026-03-20 |
| `bulk_face_camera` | [A] | [A] | AI | 2026-03-20 |
| `bulk_mirror` | [A] | [A] | AI | 2026-03-20 |
| `bulk_normalize_scale` | [A] | [A] | AI | 2026-03-20 |
| `spline_place_props` | [A] | [A] | AI | 2026-03-20 |
| `text_label_selection` | [A] | [A] | AI | 2026-03-20 |
| `text_place` | [A] | [A] | AI | 2026-03-20 |
| `verse_gen_device_declarations` | [A] | [A] | AI | 2026-03-20 |
| `verse_gen_custom` / `verse_gen_game_skeleton` | [A] | [A] | AI | 2026-03-20 |
| `verse_list_devices` / `verse_export_report` | [A] | [A] | AI | 2026-03-20 |
| `verse_bulk_set_property` | [A] | [A] | AI | 2026-03-20 |
| `spline_to_verse_points` / `patrol` | [A] | [A] | AI | 2026-03-20 |
| `spline_to_verse_zone_boundary` / `export` | [A] | [A] | AI | 2026-03-20 |
| `screenshot_focus_selection` | [A] | [A] | AI | 2026-03-20 |
| `screenshot_timed_series` | [A] | [A] | AI | 2026-03-20 |
| `api_crawl_selection` | [A] | [A] | AI | 2026-03-20 |
| `material_randomize_colors` | [A] | [A] | AI | 2026-03-20 |
| `material_bulk_swap` | [A] | [A] | AI | 2026-03-20 |
| `pattern_helix` | [A] | [A] | AI | 2026-03-20 |
| `pattern_radial_rows` | [A] | [A] | AI | 2026-03-20 |
| `scatter_along_path` | [A] | [A] | AI | 2026-03-20 |
| `measure_distance` | [A] | [A] | AI | 2026-03-22 |
| `measure_travel_time` | [A] | [A] | AI | 2026-03-22 |
| `spline_measure` | [A] | [A] | AI | 2026-03-22 |
| `align_to_reference` | [ ] | [ ] | — | — |
| `distribute_with_gap` | [ ] | [ ] | — | — |
| `rotate_around_pivot` | [ ] | [ ] | — | — |
| `align_to_surface` | [ ] | [ ] | — | — |
| `match_spacing` | [ ] | [ ] | — | — |
| `align_to_grid_two_points` | [ ] | [ ] | — | — |
| `actor_attach_to_parent` | [ ] | [ ] | — | — |
| `actor_detach` | [ ] | [ ] | — | — |
| `actor_move_to_folder` | [ ] | [ ] | — | — |
| `actor_move_to_root` | [ ] | [ ] | — | — |
| `actor_rename_folder` | [ ] | [ ] | — | — |
| `actor_select_by_folder` | [ ] | [ ] | — | — |
| `actor_select_same_folder` | [ ] | [ ] | — | — |
| `actor_select_by_class` | [ ] | [ ] | — | — |
| `actor_match_transform` | [ ] | [ ] | — | — |
| `actor_place_next_to` | [ ] | [ ] | — | — |
| `actor_chain_place` | [ ] | [ ] | — | — |
| `actor_replace_class` | [ ] | [ ] | — | — |
| `sign_batch_edit` | [ ] | [ ] | — | — |
| `sign_batch_set_text` | [ ] | [ ] | — | — |
| `sign_batch_rename` | [ ] | [ ] | — | — |
| `sign_clear` | [ ] | [ ] | — | — |
| `label_attach` | [ ] | [ ] | — | — |
| `stamp_info` | [ ] | [ ] | — | — |
| `config_set` / `config_get` / `config_reset` | [ ] | [ ] | — | — |

---

### 🔴 Requires Manual Verification (Content Browser Dependent)

| Tool | UI Verified | AI Verified (MCP) | Tested By | Date |
|---|---|---|---|---|
| ~~`lod_auto_generate_folder`~~ | ⛔ DISABLED | ⛔ DISABLED | — | Quirk #18 |
| `smart_importer` tools (`organize_assets`) | [A] | [A] | AI | 2026-03-21 |
| `rename_dry_run` | [A] | [A] | AI | 2026-03-20 |
| `rename_enforce_conventions` | [A] | [A] | AI | 2026-03-20 |
| `rename_strip_prefix` | [A] | [A] | AI | 2026-03-20 |
| `rename_report` | [A] | [A] | AI | 2026-03-20 |
| `tag_add` / `tag_remove` | [A] | [A] | AI | 2026-03-20 |
| `tag_show` / `tag_search` / `tag_export` | [A] | [A] | AI | 2026-03-20 |
| `memory_scan` | [A] | [A] | AI | 2026-03-20 |
| `memory_scan_textures` | [A] | [A] | AI | 2026-03-20 |
| `memory_scan_meshes` | [A] | [A] | AI | 2026-03-20 |
| `memory_top_offenders` | [A] | [A] | AI | 2026-03-20 |
| `memory_autofix_lods` | [A] | [A] | AI | 2026-03-20 |

---

## Layer 7: Automated Integration Test (Context-Aware)
The `toolbelt_integration_test` tool bridges the gap between pure code checks and manual verification. It programmatically:
1. Spawns fixture actors (cubes/spheres)
2. Selects them using `EditorActorSubsystem`
3. Executes tools against that selection
4. Verifies the result (properties, file outputs)
5. Cleans up with a single `undo_transaction`

**Current Integration Coverage (287 tools — 115 sections written, 103 live-verified):**

> ✅ = Confirmed passing in live UEFN
> 🔵 = Written + syntax-checked, pending first live run (Batch 9)

- ✅ **Materials:** `material_apply_preset`, `material_randomize_colors`, `material_bulk_swap`, `material_gradient_painter`, `material_team_color_split`, `material_pattern_painter`, `material_glow_pulse_preview`
- ✅ **Bulk Ops:** `align`, `distribute`, `randomize`, `snap`, `stack`, `reset`, `bulk_mirror`, `bulk_normalize_scale`, `bulk_face_camera`
- ✅ **Patterns:** `grid`, `circle`, `line`, `arc`, `spiral`, `wave`, `pattern_helix`, `pattern_radial_rows`
- ✅ **Scatter:** `scatter_props`, `scatter_hism`, `scatter_clear`, `scatter_along_path`
- ✅ **Splines:** `spline_place_props`, `spline_clear_props`
- ✅ **Snapshots:** `snapshot_save`, `snapshot_delete`, `snapshot_export`, `snapshot_import`, `snapshot_diff`, `snapshot_compare_live`, `snapshot_restore`
- ✅ **Crawler:** `api_crawl_level_classes`, `api_crawl_selection`
- ✅ **Assets:** `rename_dry_run`
- ✅ **Optimization:** `memory_scan`
- ✅ **Reference Auditor:** `ref_audit_orphans`, `ref_audit_redirectors`, `ref_audit_duplicates`, `ref_audit_unused_textures`, `ref_full_report`
- ✅ **Project Structure:** `scaffold_preview`, `scaffold_generate`, `scaffold_save_template`, `scaffold_delete_template`
- ✅ **Text Painter:** `text_place`, `text_paint_grid`, `text_save_style`, `text_clear_folder`, `text_color_cycle`, `text_label_selection`
- ✅ **Tagger:** `tag_add`, `tag_remove`, `tag_show`, `tag_search`, `tag_list_all`, `tag_export`
- ✅ **Verse:** `verse_list_snippets`, `verse_gen_device_declarations`, `verse_gen_custom`, `verse_list_devices`, `verse_bulk_set_property`, `verse_export_report`
- ✅ **Splines (Verse):** `spline_to_verse_points`, `spline_to_verse_patrol`, `spline_to_verse_zone_boundary`, `spline_export_json`
- ✅ **Screenshot:** `screenshot_take`, `screenshot_focus_selection`, `screenshot_timed_series`, `screenshot_open_folder`
- ✅ **LODs:** `lod_set_collision_folder`, `lod_audit_folder` *(lod_auto_generate_* disabled — Quirk #18)*
- ✅ **Optimization:** `memory_scan_textures`, `memory_scan_meshes`, `memory_top_offenders`, `memory_autofix_lods`
- ✅ **Arena:** `arena_generate`
- ✅ **Scatter Advanced:** `scatter_along_path`, `scatter_export_manifest`
- ✅ **Asset Admin:** `rename_enforce_conventions`, `rename_strip_prefix`, `organize_assets`
- ✅ **Bridge Control:** `mcp_start`, `mcp_stop`
- ✅ **Measurement:** `measure_distance`, `measure_travel_time`, `spline_measure`
- ✅ **Localization:** `text_export_manifest`, `text_apply_translation`
- 🔵 **Zone Tools (Batch 9):** `zone_spawn`, `zone_list`, `zone_select_contents`, `zone_snap_to_selection`, `zone_fill_scatter`
- 🔵 **Stamp Tools (Batch 9):** `stamp_save`, `stamp_place`, `stamp_list`, `stamp_info`, `stamp_delete`, `stamp_export`, `stamp_import`
- 🔵 **Actor Org (Batch 9):** `actor_move_to_folder`, `actor_folder_list`, `actor_select_by_folder`, `actor_select_by_class`, `actor_match_transform`, `actor_move_to_root`, `actor_attach_to_parent`, `actor_detach`
- 🔵 **Proximity Placement (Batch 9):** `actor_place_next_to`, `actor_chain_place`, `actor_duplicate_offset`, `actor_copy_to_positions`, `actor_cluster_to_folder`, `actor_replace_class` (dry_run)
- 🔵 **Advanced Alignment (Batch 9):** `align_to_reference`, `distribute_with_gap`, `rotate_around_pivot`, `match_spacing`, `align_to_surface`, `align_to_grid_two_points`
- 🔵 **Sign Tools (Batch 9):** `sign_spawn_bulk`, `sign_list`, `sign_batch_edit`, `sign_batch_rename`, `sign_batch_set_text`, `label_attach`, `sign_clear`
- 🔵 **Post-Process & World (Batch 9):** `postprocess_spawn`, `postprocess_set`, `postprocess_preset`, `world_settings_set`
- 🔵 **Audio (Batch 9):** `audio_place`, `audio_list`, `audio_set_volume`, `audio_set_radius`
- 🔵 **Level Health (Batch 9):** `level_health_report`, `rogue_actor_scan`
- 🔵 **Config (Batch 9):** `config_list`, `config_set`, `config_get`, `config_reset`
- 🔵 **Lighting Extended (Batch 9):** `light_place`, `light_list`, `light_set`, `sky_set_time`
- 🔵 **World State (Batch 9):** `world_state_export`, `device_catalog_scan`

---

## What the Tests Actually Prove (and Don't)

**What the smoke test proves:**
- All modules import and register without errors
- All 287 tools register into the registry with valid metadata
- Safe tools execute end-to-end and return correct results
- MCP bridge, PySide6, and Verse infrastructure all functional

**What the API Capability Crawler proves:**
- Read-only introspection works on live actors
- Property maps, method lists, and component hierarchies are accessible
- JSON output is valid and machine-readable for AI analysis

**What the automated integration test (103 live sections + 12 pending) proves:**
- **Viewport Control:** The system can successfully spawn, select, and destroy actors programmatically.
- **Context-Aware Tools:** Selection-dependent tools (Bulk Ops, Materials) are confirmed to function on live actors.
- **File System Integrity:** Screenshots, Snapshots, and Crawler JSONs are successfully written/read.
- **Automation Parity:** The vast majority of manual testing burden is eliminated. If this test passes, you have high confidence that core tool logic is sound.

**What still requires manual testing:**
- **Visual Fidelity:** While the test confirms a material *changed*, only a human can verify it looks "correct".
- **Complex Hierarchies:** Tools that depend on deeply nested Fortnite-specific components.
- **User Experience:** The "feel" of tool interactions and UI responsiveness.

> [!IMPORTANT]
> The `toolbelt_integration_test` is the single most important tool for ensuring the project remains stable as we add more features. **Always run this test before submitting a Pull Request.**
>
> To run Batch 9 tests live: `tb.run("toolbelt_integration_test")` — look for the zone, stamp, actor_org, proximity, advanced_alignment, sign, postprocess, audio, level_health, config, lighting, and world_state sections in the output.

---

## 🗺️ Automation Roadmap

### **Batch 3–8: Core Foundation (COMPLETE — 103 sections)**
All materials, bulk ops, patterns, scatter, splines, snapshots, crawler, assets, optimization, reference auditor, project structure, text, tagger, Verse, screenshot, LOD, arena, measurement, localization, and MCP bridge.

### **Batch 9: v1.6.0+ Expansion (115 sections written — pending live run)**
- [ ] **Zone Tools**: `zone_spawn`, `zone_list`, `zone_select_contents`, `zone_snap_to_selection`, `zone_fill_scatter`
- [ ] **Stamp Tools**: `stamp_save`, `stamp_place`, `stamp_list`, `stamp_info`, `stamp_delete`, `stamp_export`, `stamp_import`
- [ ] **Actor Org**: `actor_move_to_folder`, `actor_folder_list`, `actor_select_by_folder`, `actor_select_by_class`, `actor_match_transform`, `actor_move_to_root`, `actor_attach_to_parent`, `actor_detach`
- [ ] **Proximity Placement**: `actor_place_next_to`, `actor_chain_place`, `actor_duplicate_offset`, `actor_copy_to_positions`, `actor_cluster_to_folder`, `actor_replace_class`
- [ ] **Advanced Alignment**: `align_to_reference`, `distribute_with_gap`, `rotate_around_pivot`, `match_spacing`, `align_to_surface`, `align_to_grid_two_points`
- [ ] **Sign Tools**: `sign_spawn_bulk`, `sign_list`, `sign_batch_edit`, `sign_batch_rename`, `sign_batch_set_text`, `label_attach`, `sign_clear`
- [ ] **Post-Process & World**: `postprocess_spawn`, `postprocess_set`, `postprocess_preset`, `world_settings_set`
- [ ] **Audio**: `audio_place`, `audio_list`, `audio_set_volume`, `audio_set_radius`
- [ ] **Level Health**: `level_health_report`, `rogue_actor_scan`
- [ ] **Config**: `config_list`, `config_set`, `config_get`, `config_reset`
- [ ] **Lighting Extended**: `light_place`, `light_list`, `light_set`, `sky_set_time`
- [ ] **World State**: `world_state_export`, `device_catalog_scan`
- [ ] **Activity Log (Batch 10):** `toolbelt_activity_log`, `toolbelt_activity_stats`, `toolbelt_activity_clear`, `publish_audit` — manually verified live 2026-03-25

**To complete Batch 9:** run `tb.run("toolbelt_integration_test")` in UEFN on a clean template level. Mark each section above with `[x]` after confirming it passes.

### **Batch 20–21: AI-Agent Readiness (COMPLETE)**
- [x] **Tool Manifest**: `plugin_export_manifest` — full parameter signatures for all tools
- [x] **Structured Returns**: 100% `{"status": "ok"/"error", ...}` — zero `None` returns
- [x] **`describe_tool` MCP Command**: Per-tool manifest lookup
- [x] **Milestone**: All registered tools AI-agent ready

---

## Contributing & Testing Protocol

If you are contributing a new tool or modifying an existing one:

1. **Check existing tools first** — run the fast grep from `CONTRIBUTING.md` Step 1 before writing anything new. The biggest category of waste is building what already exists.
2. **If it's a "Safe Tool"**: Ensure it handles empty states gracefully. Add it to the smoke_test execution list and to the Layer 3 table above.
3. **If it requires context**: Manually verify in a throwaway UEFN project before submitting a PR. Add a row to the appropriate 🟡/🟠/🔴 table above.
4. **Always run `smoke_test.py`** before committing to ensure you haven't broken the registry or layer imports.
5. **Update this file** when adding tools — tool count, coverage percentage, and the appropriate verification table. This doc is the authoritative source of truth for what's tested and what isn't.
