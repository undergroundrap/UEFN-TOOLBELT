# UEFN Toolbelt — Tool Status & Testing

UEFN Toolbelt contains **362 tools across 35+ modules**. Because many tools actively modify the viewport, spawn actors, or depend on specific Content Browser selections, **the `integration_test.py` suite uses temporary fixtures to automate verification of context-dependent tools.**

### Phase 21 — Complete AI Return Loop
As of Phase 21, **every registered tool returns a structured `dict`** — `{"status": "ok"/"error", ...}`. Zero `None` returns remain anywhere in the codebase. This means AI agents using the MCP bridge can act on results programmatically: no log parsing, no guessing. The `describe_tool` MCP command was also added for per-tool manifest lookup.

### UEFN 42.00 / UE 6.0 — Engine API Status (2026-08-20)

UEFN force-updates in lockstep with the live Fortnite build, so 42.00 is not
optional for anyone. It runs **UE 6.0**, not UE 5.x, and removes 13 `unreal.*`
symbols the Toolbelt used.

**Twelve tools are non-functional on 42.00 and refuse cleanly** rather than raising
part-way through their work. They return
`{"status": "error", "reason": "engine_api_unavailable", "missing_apis": [...]}`:

| Tools | Missing API |
|---|---|
| `geometry_weld_edges`, `geometry_fill_holes`, `geometry_compute_normals`, `geometry_generate_lightmap_uvs`, `geometry_boolean_union/subtract/intersect`, `geometry_remove_degenerate` | `GeometryScriptLibrary_*` |
| `blueprint_inspect`, `blueprint_compile_folder` | `EditorBlueprintLibrary` |
| `input_create_action` | `InputActionFactory` |
| `system_optimize_background_cpu` | `EditorPerformanceSettings` |
| `align_to_surface` | `EditorLevelLibrary.snap_objects_to_floor` |

These are declared `__optional_unreal_apis__` in their modules, so the smoke test
reports them as *absent and handled* rather than as failures. **Layer 2 is green
on 42.00** — 88/88, first green at the 2.3.4 release.

**Reference lookup** (`ref_audit_orphans`, `ref_audit_unused_textures`,
`ref_delete_orphans`) works on 42.00 via the UE 6.0 Asset Registry. Verified live:
real per-asset referencer counts, not empty lists.

**Known issue — not a Toolbelt defect.** Enabling Project Settings → Beta Access →
UEFN MCP Toolsets stops the project's `init_unreal.py` from running, so Toolbelt
never auto-starts. See README "Known Issue" and UEFN_QUIRKS.md #36. Detected by
`tb.startup_ran()` and smoke test Layer 3. Reported to Epic.

### ⚠️ Architectural Constraints
*   **Main Thread Lock**: UEFN Python runs on the main render thread. Operations like `time.sleep` in wait loops will **deadlock** the engine, preventing async tasks (like screenshot saves) from completing. Verification logic should avoid blocking waits.
*   **Hot-Reloading**: Use "Nuclear Reload" to clear `sys.modules` cache. **Mandatory**: Must call `tb.register_all_tools()` after reloading to rebuild the registry.

This document outlines the current testing status of the toolbelt and categorizes which tools are verified by the automated smoke test, and which require manual verification.

## 🟡 Automated Verification Status: **187 / 362 Tools (52% Coverage)**
Integration suite has **116 test sections written**, all run live. The suite
records 189 individual checks; **189/189 passed on UEFN 42.00** (build 25d3daa,
2026-08-23). Batches 9 and 10 below are now marked from that run rather than
from intent - the rows still unchecked are the ones the suite genuinely does not
exercise.

**Read the split, not the total.** Of the 189, **162 verify a real outcome** and
**27 are execution-only** — they assert the tool did not raise and nothing more.
The suite prints both figures on every run. Treating the total as coverage is
what let Quirk #41 (wrong rotator axis) sit inside a green run, and what let
`material_bulk_swap` report success for a swap that changed nothing.

> **Coverage gap:** 75 tools were added after v1.6.0 (zones, stamps, actor org, proximity placement, advanced alignment, signs, audio, post-process, level health, config, lighting extended, world state). Batch 9 integration tests ran green live on 2026-08-21 (180/180), 2026-08-22 (183/183), and 2026-08-23 (189/189).
>
> **Modules still outside the integration suite:** `niagara_tools` (4), `pcg_tools` (4), `geometry_tools` (5), `movie_render_tools` (3), `activity_log_tools` (3) — registered and live-tested by hand, but nothing in the suite exercises them, so treat them as unverified. `viewport_tools` left this list once its showflag and bookmark tools got sections. `curve_tools` got its first coverage on 2026-08-23 (`curve_create` only) — and that section immediately caught a real bug, which is the argument for shrinking this list further.

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

**Current Integration Coverage (362 tools — 116 sections written, all run live; 162 of 189 checks verify a real outcome):**

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
- All 362 tools register into the registry with valid metadata
- Safe tools execute end-to-end and return correct results
- MCP bridge, PySide6, and Verse infrastructure all functional

**What the API Capability Crawler proves:**
- Read-only introspection works on live actors
- Property maps, method lists, and component hierarchies are accessible
- JSON output is valid and machine-readable for AI analysis

**What the automated integration test (116 live sections, 189 checks, 189/189 — 162 verified, 27 execution-only) proves:**
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

### **Batch 9: v1.6.0+ Expansion — passing live on UEFN 42.00 (2026-08-23)**
- [x] **Zone Tools**: `zone_spawn`, `zone_list`, `zone_select_contents`, `zone_snap_to_selection`, `zone_fill_scatter`
- [x] **Stamp Tools**: `stamp_save`, `stamp_place`, `stamp_list`, `stamp_info`, `stamp_delete`, `stamp_export`, `stamp_import`
- [x] **Actor Org**: `actor_move_to_folder`, `actor_folder_list`, `actor_select_by_folder`, `actor_select_by_class`, `actor_match_transform`, `actor_move_to_root`, `actor_attach_to_parent`, `actor_detach`
- [x] **Proximity Placement**: `actor_place_next_to`, `actor_chain_place`, `actor_duplicate_offset`, `actor_copy_to_positions`, `actor_cluster_to_folder`, `actor_replace_class`
- [x] **Advanced Alignment**: `align_to_reference`, `distribute_with_gap`, `rotate_around_pivot`, `match_spacing`, `align_to_surface`, `align_to_grid_two_points`
- [x] **Sign Tools**: `sign_spawn_bulk`, `sign_list`, `sign_batch_edit`, `sign_batch_rename`, `sign_batch_set_text`, `label_attach`, `sign_clear`
- [x] **Post-Process & World**: `postprocess_spawn`, `postprocess_set`, `postprocess_preset`, `world_settings_set`
- [x] **Audio**: `audio_place`, `audio_list`, `audio_set_volume`, `audio_set_radius`
- [x] **Level Health**: `level_health_report`, `rogue_actor_scan`
- [x] **Config**: `config_list`, `config_set`, `config_get`, `config_reset`
- [x] **Lighting Extended**: `light_place`, `light_list`, `light_set`, `sky_set_time`
- [x] **World State**: `world_state_export`, `device_catalog_scan`
- [ ] **Activity Log**: `toolbelt_activity_log`, `toolbelt_activity_stats`, `toolbelt_activity_clear`, `publish_audit` — manually verified live 2026-03-25

Every checked group above ran green in the 189/189 live run on 2026-08-23. The
unchecked rows are the honest remainder — they are written but the suite does
not exercise them, so treat them as unverified rather than passing.

### **Batch 10: v1.9.6 Team Workflow + AI Quality — passing live on UEFN 42.00 (2026-08-23), two gaps noted**
- [x] **Visibility**: `actor_hide`, `actor_show`, `actor_isolate`, `actor_show_all`, `actor_lock`, `actor_unlock`
  - [ ] `folder_hide` / `folder_show` — **not exercised by the suite.** The actor-level pair is covered; the folder-level pair is not.
- [x] **Viewport Bookmarks**: `viewport_showflag`, `viewport_bookmark_save`, `viewport_bookmark_list`, `viewport_bookmark_jump`
- [x] **Selection Sets**: `selection_save`, `selection_restore`, `selection_list`
- [x] **Project Admin**: `save_all_dirty`
  - [ ] `mesh_merge_selection` — **not exercised by the suite.** The merge API may be sandboxed in UEFN, so a fixture cannot prove the success path.

**Depth improvements verified live 2026-03-25 (existing tools enhanced, no new tools):**
- `world_state_export` — captures `folder`, `parent`, `bounds`, `asset_path` per actor + `summary.class_counts` / `summary.folder_map`; 2888/3404 actors in test level have `asset_path` populated
- `verse_patch_errors` — classifies errors into `error_type` + `fix_hint` + groups by file in `errors_by_file`; `error_type_summary` at top level
- `plugin_export_manifest` — manifest now includes `example` call string per tool (added to 13 key tools)
- `selection_restore` — duplicate-label bug fixed (first match per label only)
- `get_folder_path()` None bug fixed in `world_state_export` (root actors now store `""` not `"None"`)

The Visibility, Viewport, SelectionSets and ProjectAdmin sections all appear in
the live output; the two unchecked members above are the exceptions.

### **Batch 11: Verse Template Library (manually verified live 2026-03-29)**
- [x] `verse_template_list` — returns 6 templates with descriptions and device lists
- [x] `verse_template_get` — returns full Verse source + `devices_needed` + `next_step` for named template
- [x] `verse_template_deploy` — delegates to `verse_write_file`; writes template to Verse source dir
- [x] `verse_build_status` — returns `SUCCESS`/`FAILED`/`UNKNOWN` + ISO timestamp + staleness flag

### **Batch 12: Cooker Optimizer (pending live UEFN test)**
- [ ] `cooker_scan` — returns actor counts by type and editor-only status
- [ ] `cooker_mark_batch` — marks N% of scanned actors as editor-only, with dry_run support
- [ ] `cooker_unmark_all` — clears editor-only on all scanned actors
- [ ] `cooker_mark_selection` — marks/clears editor-only on viewport selection
- [ ] `cooker_open` — PySide6 window with scan, batch controls, and cook feedback/confidence

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

---

## Batch 12 — 42.00 Compatibility & Data-Loss Fixes (live-verified 2026-08-20)

Verified in a live UEFN 42.00 editor on a real project, not a template level.

**Data-loss fixes — each reproduced before the fix and confirmed after:**

| Tool | Defect | Verification |
|---|---|---|
| `ref_delete_orphans` | Classified every asset as orphaned once `find_package_referencers` was removed; separately would delete `GameFeatureData`, the project's `.uplugin` descriptor | Live audit: 3473 assets scanned, 3455 sub-objects skipped, 3 roots protected, 13 real orphans found |
| `organize_smart_categorize` | Deleted the source asset when a rename failed and counted it as "moved" | No `delete_asset` call remains in the module |
| `arena_generate` | Wrote team materials to `/Game/`, i.e. Epic's Fortnite install | Resolves to `/<ProjectMount>/UEFN_Toolbelt/Materials/` |
| `align_to_surface` | Returned `status: ok` after snapping nothing on 42.00 | Refuses via `missing_unreal_apis()` |

**Write-destination fixes (9 tools)** — all previously defaulted to `/Game/`,
creating assets the project cannot reference: `curve_create`,
`text_render_texture`, `text_voxelize_3d`, `mesh_merge_selection`, `import_fbx`,
`organize_assets`, `create_material_instance` (MCP), `anim_create_montage`,
`input_create_action`, `organize_smart_categorize`.

Live-verified via `curve_create` → `/Device_API_Mapping/Curves/CM_PathTest`.
All nine share an identical edit shape through `core.resolve_content_path()`.

**New tools (3):** `epic_mcp_status`, `epic_mcp_register`, `epic_mcp_unregister` —
registered live, reachable from the MCP dashboard tab and the editor menu.

**Dashboard fixes** — confirmed by live inspection: Setup Status showed a stale
"MCP bridge: Not running" while the listener was up; the verse-book check looked
in the wrong directory and then counted the wrong subdirectory.

### Still unverified

- **The 42 read-path `/Game/` defaults are now fixed** (see Batch 13), but the
  migrated scan-path tools have not been individually exercised in a live
  editor — only the shared `resolve_scan_path()` helper and a representative
  sample have.
- ~~Integration test has not been run since these changes.~~ Run live on
  2026-08-21: **180/180**. It found two real breaks the smoke test could not
  see — a UE 6.0 return-shape change in `material_save_preset`, and a modal
  dialog in `material_apply_preset` — plus one of its own assertions that had
  been passing by asserting the broken state.
- **Epic MCP end-to-end.** Registration into the Toolset Registry is confirmed;
  an external MCP client calling `toolbelt_list_tools` through it is not, and is
  blocked by the 42.00 startup-order bug above.

---

## Batch 13 — `/Game/` scan-path migration (2026-08-21)

The last 42 parameters defaulting to `/Game/` were migrated. In UEFN `/Game/` is
Epic's Fortnite install, so every one of these scanned the wrong content tree —
returning empty or irrelevant results, and risking the Quirk #32 pak-scan crash.

| Kind | Count | Resolver |
|---|---|---|
| Scan paths — where a tool *looks* | 39 | `core.resolve_scan_path()` |
| Write paths — `project_scaffold` `base`, which *creates* folders | 3 | `core.resolve_content_path()` |

Modules touched: `animation_tools`, `asset_tagger`, `audio_design_tools`,
`blueprint_tools`, `curve_tools`, `datatable_tools`, `enhanced_input_tools`,
`lod_tools`, `mcp_bridge`, `project_scaffold`, `skeletal_mesh_tools`,
`sound_asset_tools`, `texture_tools`.

**Explicit arguments are unaffected for scan paths.** `resolve_scan_path()` only
fills in an empty value and passes anything else through, so a caller naming
`/Engine/BasicShapes` or a specific folder behaves exactly as before. The three
`project_scaffold` parameters *are* rewritten off `/Game/`, deliberately — you
cannot scaffold folders into Epic's install.

`_GAME_PATH_DEFAULT_BASELINE` is now **0**: a new `/Game/` default fails
`drift_check` outright rather than being absorbed by a ratchet.

### Not yet verified live

The scan-path migration was mechanical and shares one helper, which is unit
tested and was verified live earlier today. The migrated tools have **not** each
been run individually in the editor. The failure mode if a migration is wrong is a tool
scanning the project root instead of a subfolder — visible, not destructive.
