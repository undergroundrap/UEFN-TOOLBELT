# UEFN Toolbelt — Changelog

All notable changes to this project are documented here.
Format: `## [version] — date` · Types: `feat` · `fix` · `refactor` · `docs` · `perf` · `test`

---

## [1.9.6] — 2026-03-25

### feat: team workflow tools — visibility, selection sets, bookmarks, merge (270 → 287 tools)

**New module: `actor_visibility.py` (8 tools)**
- `actor_hide` / `actor_show` — hide or restore selected actors in the viewport
- `actor_isolate` — hide everything except selection; focus on your section
- `actor_show_all` — restore visibility for every hidden actor in the level
- `folder_hide` / `folder_show` — toggle visibility of an entire World Outliner folder
- `actor_lock` / `actor_unlock` — prevent accidental viewport moves on final-placed assets

**`viewport_tools.py` additions (4 tools)**
- `viewport_showflag` — apply named show-flag preset (clean / no_text / no_icons / geometry_only / reset)
- `viewport_bookmark_save` / `viewport_bookmark_jump` / `viewport_bookmark_list` — named persistent camera bookmarks; survive restarts

**`selection_utils.py` additions (3 tools)**
- `selection_save` / `selection_restore` / `selection_list` — save named actor selections to JSON; restore by label match across restarts

**`project_admin.py` addition (1 tool)**
- `save_all_dirty` — save all unsaved assets and the current map in one call; no dialog

**`bulk_operations.py` addition (1 tool)**
- `mesh_merge_selection` — merge selected StaticMesh actors into a single mesh asset (one draw call); graceful error if UEFN sandboxes the API

**Also in this release:**
- `viewport_move_to_camera` — move selected actors to current camera position (sprint-placed workflows)
- `CAMERA ALIGN` deferred-tick fix in Verse Device Graph node clicks
- UEFN_QUIRKS.md: Quirk #28 (execute_console_command crash from Qt signal), Quirk #29 (verse graph crash clears on UEFN restart)

---

### feat: 6 new tool modules + focus=True viewport snap for all spawn tools (250 → 269 tools)

**New modules (19 tools):**
- `niagara_tools.py` — VFX control: `niagara_spawn_system`, `niagara_list_systems`, `niagara_bulk_set_parameter`, `niagara_clear_systems`
- `pcg_tools.py` — PCG graph control: `pcg_execute_graph`, `pcg_set_seed`, `pcg_randomize_seed`, `pcg_refresh_all`
- `geometry_tools.py` — GeometryScript mesh ops (all default `dry_run=True`): `geometry_weld_edges`, `geometry_fix_normals`, `geometry_recalc_uvs`, `geometry_boolean_union`, `geometry_decimate`
- `movie_render_tools.py` — Sequencer pipeline: `movie_render_queue_sequence`, `movie_render_apply_preset`, `movie_render_status`
- `viewport_tools.py` — Camera navigation: `viewport_goto`, `viewport_focus_actor`, `viewport_camera_get`
- `activity_log_tools.py` — Tool call monitoring: `toolbelt_activity_log`, `toolbelt_activity_stats`, `toolbelt_activity_clear`

**`focus=True` — viewport snap on all spawn tools:**
- Added to `pattern_grid/circle/arc/spiral/line/wave/helix/radial_rows`, `zone_spawn`, `scatter_props`, `scatter_hism`, `stamp_place`
- Uses UEFN's native `CAMERA ALIGN` console command (select actors → CAMERA ALIGN) — zero roll corruption
- All spawn tools now return `"center": [x,y,z]` in their result dict
- Default `False` (preserves viewport state when using the dashboard; set `True` when running from console or MCP)

**viewport_focus_actor fix:**
- Replaced manual `set_level_viewport_camera_info` with `CAMERA ALIGN` — eliminates the persistent camera roll corruption introduced in UEFN's viewport API

**drift_check.py — category count tracking:**
- Now reads `__category_count__` from `__init__.py` alongside `__version__` and `__tool_count__`
- Added `_CATEGORY_COUNT_PATTERN` scanner — catches stale category counts across all 12 scanned files

---

## [1.9.6] — 2026-03-24

### feat: rolling activity log — system monitor for every tool call (247 → 250 tools)
- New module `core/activity_log.py` — records every `tb.run()` call automatically
  - In-memory ring buffer (`deque(maxlen=500)`) + JSON persistence to `Saved/UEFN_Toolbelt/activity_log.json`
  - Per-entry fields: `tool`, `status` (ok/error), `duration_ms`, `timestamp`, `error` (truncated traceback tail)
  - Pre-loads from disk on first access — survives hot-reload
- Wired into `registry.execute()` at the chokepoint — zero boilerplate for tool authors
  - `time.perf_counter()` timing wraps every tool call
  - Lazy import (`from .core.activity_log import record`) — never crashes a successful run
- 3 new registered tools:
  - `toolbelt_activity_log` — view last N entries, newest first (default 50)
  - `toolbelt_activity_stats` — aggregate stats: total, ok/error counts, error rate, slowest, most-called, last 5 errors
  - `toolbelt_activity_clear` — wipe buffer + disk file before benchmarking or fresh test runs
- Use cases: AI agent health monitoring, performance bottleneck detection, error pattern analysis

---

## [1.9.6] — 2026-03-24

### feat: publish_audit — Fortnite island publish-readiness checker
- New tool: `publish_audit` in `tools/publish_audit.py`
- 9-layer fast audit in one call (no actor mutations, fully read-only):
  1. Actor count vs configurable budget limit (default 2000)
  2. Required devices present — spawn pads and any custom class list
  3. Light count budget warning (default >50)
  4. Rogue actors — zero/extreme scale, off-map, at-origin
  5. Verse build status — reads last build log for SUCCESS/FAILED
  6. Unsaved level detection
  7. Stale ObjectRedirector count (quick Asset Registry scan)
  8. Level name sanity — not "Untitled" or default
  9. Memory report freshness — references cached memory_report.json if <2h old
- Returns `{"status": "ready"|"warnings"|"blocked", "score": 0-100, "checks": {...},
  "blocked_by": [...], "next_steps": [...]}` — fully MCP-ready
- Saves report to `Saved/UEFN_Toolbelt/publish_audit.json` after every run
- Does NOT duplicate existing tools (memory_scan, rogue_actor_scan, ref_full_report,
  level_health_report) — calls fresh inline checks and references their cached output

---

## [1.9.4] — 2026-03-24

### fix: theme switcher now updates the full dashboard
- Replaced ~84 hardcoded hex values in `dashboard_pyside6.py` with `_color('token')`
  calls so every inline `setStyleSheet` responds to `set_theme()` live
- Added two new PALETTE tokens: `text_bright` and `text_dim`, with correct values
  for all 6 themes (toolbelt_dark, midnight, ocean, nord, forest, daylight)
- Dark theme output is pixel-identical to before — token values match old hardcoded hex exactly
- Theme switcher now fully functional: switching to `daylight`, `ocean`, `midnight`,
  `nord`, or `forest` updates the entire dashboard, not just cascade-controlled widgets

### fix: audit pass 3 — defensive improvements
- `screenshot_timed_series`: log prominent warning when `interval_sec > 0` (editor
  will freeze during series; recommend `interval_sec=0` for burst mode)
- `base_window`: Slate tick exceptions now surface in Output Log instead of silent pass
- `mcp_server`: `UEFN_MCP_PORT` env var parse wrapped in try/except with range check;
  falls back to 8765 instead of crashing on invalid input
- `mcp_server`: stale tool count 171 → 246 in docstring

### docs: ARCHITECTURE.md — system design reference
- New top-level document: directory map, subsystem descriptions, data flow diagram,
  execution environment constraints, extension points for contributors

---

## [1.9.3] — 2026-03-24

### fix: zero None returns — Phase 21 guarantee enforced across all tools
- `screenshot_timed_series` — returned `None`; now returns `{"status": "ok", "count", "folder"}`
- `sim_generate_proxy` — returned `None` on success/no-selection; now returns structured dict
- `sim_trigger_method` — returned `None` on all paths; now returns `{"status": "ok/error", ...}`
- `import_fbx` — returned `None` on all paths; now returns `{"status": "ok/error", "imported", "count"}`
- `import_fbx_folder` — same fix; returns count of imported assets
- `organize_assets` — same fix; returns `{"status": "ok", "moved", "total", "target"}`
- `system_build_verse` and `system_get_last_build_log` — added missing `**kwargs`
- `api_verse_get_schema` and `api_verse_refresh_schemas` — added missing `**kwargs` + `= ""` default

### docs: ARCHITECTURE.md — system design reference
- New top-level document covering: directory map, subsystem descriptions, data flow,
  execution environment constraints, and extension points
- Added to Key Files table in CLAUDE.md and CONTRIBUTING.md

### docs: README version badge bump 1.9.1 → 1.9.2

---

## [1.9.2] — 2026-03-24

### feat: stamp_export / stamp_import — cross-project stamp sharing
- `stamp_export` — copy a saved stamp to a portable JSON file (defaults to `~/Desktop/stamps/`)
- `stamp_import` — import a stamp from any JSON file into the local library with optional name override and overwrite control
- Verified live: export → file on Desktop, import → appears in `stamp_list`

### test: batch 9 integration tests — 163/163 passing
- 12 new test sections covering 75 tools added after v1.6.0:
  zones, stamps, actor org, proximity placement, advanced alignment, signs,
  post-process, audio, level health, config, lighting extended, world state
- Incremental result flushing: partial results now written after every test record,
  so a mid-run crash leaves a diagnostic file instead of nothing
- Fixed wrong return key assertions: `world_state_export` (`count` not `actor_count`),
  `device_catalog_scan` (`devices_found` not `device_count`)
- `sky_set_time` and `world_settings_set` marked as expected-limited on bare template levels

### feat: MCP dashboard live status indicator
- MCP tab now shows live `● RUNNING port 8765` / `● NOT RUNNING` label
- Status auto-refreshes whenever the MCP tab is navigated to
- Start/Stop/Restart buttons update status immediately after running

### feat: verse tab — check build errors button
- Added `▶ Check Build Errors` button at top of Build Intelligence group
- Calls `verse_patch_errors` — reads build log, extracts errors with file/line context,
  returns full content of every erroring .verse file for Claude to fix in one shot

### feat: community plugins — 2 new genuine gap-fillers
- `spawn_at_each_selected` — stamp any asset at every selected actor's position
  (place lights above torches, markers at spawn pads, etc.)
- `verse_gen_checkpoint` — generate a full Verse checkpoint/progression system
  (sequential triggers, per-player progress, win condition, optional reset-on-elim)

### fix: parameters= kwarg not valid in @register_tool
- Removed `parameters={}` from all `@register_tool` decorators (not a supported argument)
- Manifest builds from `inspect.signature()` on the function — type annotations + defaults
- Fixed in `prefab_stamp.py` and both community plugins; documented in CONTRIBUTING.md

### docs: quirk #27 — hard restart vs nuclear reload
- Nuclear reload fixes code. Hard restart fixes state.
- Added to `UEFN_QUIRKS.md`, `CLAUDE.md`, and `CONTRIBUTING.md` with decision table
- Covers: Shiboken crashes, project switches, stale C++ handles, `tb` undefined errors

### docs: TOOL_STATUS.md rebuilt from scratch
- Updated from 171 → 246 tools, 76% coverage
- Full Batch 9 coverage map (🔵 written/pending → ✅ live-verified after 163/163)
- Disabled tools table (lod_auto_generate_* — Quirk #18)
- CLAUDE.md and CONTRIBUTING.md now reference TOOL_STATUS.md as authoritative coverage doc

### docs: smoke test vs integration test explained everywhere
- README, CLAUDE.md, CONTRIBUTING.md all now clearly explain what each test does,
  when to run it, safety rules, and the comparison table
- Dashboard setup status threshold updated from 171 → 240

### docs: tb import rule — when to import vs when tb already exists
- Added to CLAUDE.md Nuclear Reload section and CONTRIBUTING.md Step 4
- Rule: same project/session = tb exists; switched projects or fresh launch = import fresh

### docs: ai-native onboarding — CONTRIBUTING.md and README
- CONTRIBUTING.md: 5-step contributor loop, mandatory "check existing tools first" as Step 1,
  fast grep command to audit all 247 tool names before writing anything new
- README: AI-native pioneer pitch, CLAUDE.md auto-loading as a first-of-its-kind feature

---

## [1.9.1] — 2026-03-24

### feat: level stamp system — save and re-place actor groups

**New tools (`stamp_save`, `stamp_place`, `stamp_list`, `stamp_info`, `stamp_delete`):**
- `stamp_save` — capture any selection of StaticMesh actors as a named stamp; records relative transforms, mesh asset paths, rotations, and scales to `Saved/UEFN_Toolbelt/stamps/{name}.json`
- `stamp_place` — re-spawn a saved stamp at the viewport camera (or explicit location). Optional `yaw_offset` rotates all actor positions and rotations around the stamp center. Optional `scale_factor` multiplies all offsets and scales uniformly
- `stamp_list` / `stamp_info` / `stamp_delete` — manage saved stamps
- New **Stamps** category in the registry (38 categories total)
- Full undo support via `ScopedEditorTransaction`; new actors auto-selected after placement
- Blueprint/device actors are skipped with a warning (can't be reliably re-spawned from path)
- Stamp files survive hot-reloads, editor restarts, and Toolbelt updates — stored in `Saved/` not `Content/`
- Distinct from `prefab_migrate_open` (asset migration between projects) — stamps are for level layout reuse
- Documented in CLAUDE.md with compass-point placement example

### docs: quirk #26 — nuclear reload crash when adding new modules

- Documented `EXCEPTION_ACCESS_VIOLATION` caused by `sys.modules.pop` freeing Python objects
  while stale Unreal C++ callbacks (Slate tick, MCP socket) still point at them
- Crash signature, when it happens, and the safe workflow (full restart for new modules,
  nuclear reload only for iterating on existing tools)
- Added warning to CLAUDE.md nuclear reload section with cross-reference to Quirk #26

---

## [1.9.0] — 2026-03-24

### feat: level health dashboard — unified audit score

**New tools (`level_health_report`, `level_health_open`):**
- `level_health_report` — headless: runs all 6 audit categories and returns a 0–100 health score with A+…F grade. Fully structured dict return — MCP/AI agent friendly.
- `level_health_open` — windowed UI: animated score ring, colour-coded category cards (green/yellow/red), per-issue summary text, live audit progress, and a console log pane.
- Six audit categories: Actor Integrity, Memory & Textures, Asset References, Naming Conventions, LOD & Collision, Performance — each scored proportionally and weighted.
- Aggregates results from 6 existing audit tools (`rogue_actor_scan`, `memory_scan_textures`, `ref_audit_orphans`, `rename_dry_run`, `lod_audit_folder`, `system_perf_audit`) — no duplicated logic.
- Audit runs on a background QThread so the UI stays responsive during scan.
- Added to dashboard Flagship Tools quick bar.
- Added `level_health_report` and `level_health_open` to CLAUDE.md Utilities table.

---

## [1.8.5] — 2026-03-24

### feat: ui icon importer — clipboard-first texture import

**New flagship tool (`ui_icon_import_open`):**
- Copy any image from a browser, Figma, Photoshop, or Paint and paste it with Ctrl+V directly into the window — imports as a UEFN texture in one step
- Three input paths: clipboard paste (Ctrl+V), click-to-browse file dialog, drag-and-drop image files
- Five texture presets covering all common UEFN UI needs: UI Icon (TC_UserInterface2D · NoMipmaps), Sprite/2D, Thumbnail, Normal Map, Default/Mipmapped
- Auto-detects project mount point for default destination (`/[Mount]/UI/Icons/`)
- Auto-prefixes `T_` on filenames per Epic naming convention
- Applies `post_edit_change()` + saves asset after settings — texture is fully configured on import
- Syncs Content Browser and selects the imported asset automatically
- `?` help dialog covers all presets, input methods, and the "why no mipmaps for UI" rationale
- Added to dashboard Flagship Tools quick bar

---

## [1.8.4] — 2026-03-24

### feat: prefab asset migrator — dependency-aware asset migration tool

**New flagship tool (`prefab_migrate_open`):**
- Walks the full Asset Registry dependency graph from seed assets — meshes pull in materials, materials pull in textures, nothing gets silently dropped
- Three ways to add assets: Content Browser selection, viewport actor selection (extracts mesh/BP paths from placed actors), manual path entry
- Two export modes: same-project copy via `EditorAssetLibrary.duplicate_asset()`, cross-project disk copy via `shutil.copy2` on raw `.uasset` files — auto-detected from destination path
- Flatten folder structure option — copies everything to one flat destination folder, no unwanted parent tree
- Dry run mode — full preview of what would be copied before committing
- Destination auto-fills from project mount point on first asset add (fixes UEFN `/Game/` invisibility quirk)
- `?` help button opens themed reference dialog covering workflows, options, and known limitations
- Added to dashboard Flagship Tools quick bar alongside Verse Device Graph

**UEFN path quirks fixed:**
- `unreal.Paths.project_content_dir()` returns FortniteGame engine path — fixed to use Asset Registry mount detection
- `/Game/` mount is invisible in Content Browser — tool uses project-named mount (e.g. `/Device_API_Mapping/`) derived from first asset added
- `AssetData.package_name` returns project-mount paths, not `/Game/` — dep resolver updated to handle any mount prefix

### fix: help dialog topbar redundancy + line wrap
- Removed redundant `make_topbar` from help dialogs in both prefab migrator and verse device graph — OS title bar already identifies the window
- Added `QTextEdit.NoWrap` to all read-only help/reference text areas — prevents separator lines from splitting across lines

### docs: ui style guide + CLAUDE.md — mandatory `?` help button rule
- Every tool window must have a `?` help button — codified as mandatory in `docs/ui_style_guide.md` with exact placement rules and copy-paste pattern
- `make_topbar` rule strengthened: no topbar unless it carries multiple real toolbar buttons, applies to sub-dialogs too
- Added `NoWrap` recipe for read-only text areas to style guide
- `docs/UEFN_QUIRKS.md` Quirk #23: `/Game/` mount invisible in Content Browser — full breakdown with correct detection pattern
- `CLAUDE.md` path format rule updated to reference Quirk #23

---

## [1.8.3] — 2026-03-23

### feat: verse device graph — minimap, category filter, focus button, help dialog, node tooltips

**Minimap (bottom-right canvas overlay):**
- Custom `QWidget` overlay — draws every node as a 3×3 colored dot matching its category color
- No scene re-render — edges never bleed into the thumbnail
- Blue viewport outline updates live as you pan/zoom the main canvas
- Click to teleport view, drag to pan — delta-based drag prevents jump-on-click jank
- Stays pinned to bottom-right corner via `scrollContentsBy` override (fixes vanish-on-drag)
- Updates correctly after Live mode rescans and Re-Layout

**Category filter dropdown:**
- Toolbar `QComboBox` populated after every SCAN with all unique device categories
- Selecting a category hides all other nodes and their edges instantly
- Search and category stack — filter to "Timer" then search within it
- Previous selection restored across rescans; "All Categories" resets

**Focus button:**
- Select any node, click Focus → view centres and zooms to that node
- Useful for navigating to a search result buried in a large graph

**Help dialog (`?` button):**
- Themed `_HelpDialog(ToolbeltWindow)` — scrollable reference window matching dashboard style
- Covers: purpose, why it was made, typical workflow, badge guide, edge types, tips, attribution
- Documents minimap, category filter, Focus, comment boxes, layout persistence, write-back

**Node badge tooltips:**
- `_make_node_tooltip(nd)` module-level function — every node shows a tooltip explaining
  cluster ID, VS badge, error (red !) and warning (yellow !) badges with full context

**Minimap vanish fix:**
- Root cause: `QWidget::scroll()` physically moves viewport child widgets during `ScrollHandDrag`
- Fix: `_GraphView.scrollContentsBy` override re-pins minimap to corner after every scroll tick

---

## [1.8.2] — 2026-03-23

### feat: verse device graph — blueprint-style grouped layout + comment boxes

**Grouped layout (default on SCAN):**
- Nodes now arranged in labelled category columns instead of the previous scattered circle
- Categories sorted by size (largest first), then alphabetically — related devices stay together
- Coloured header labels above each column match the node accent colour
- Multi-column overflow when a category exceeds 10 nodes
- Re-Layout button still runs animated Fruchterman-Reingold physics for freeform exploration

**Comment / note boxes (+ Note button):**
- Draggable, resizable annotation boxes — Blueprint-style, sit behind all nodes (z = −2)
- Semi-transparent coloured fill with a tinted header bar
- Double-click **header** → rename title (`QInputDialog.getText`)
- Double-click **body** → multi-line note content (`QInputDialog.getMultiLineText`)
- Body shows `"double-click to add notes…"` hint when empty; wraps text automatically
- Right-click context menu: 7 colour presets + Delete
- Resize by dragging the bottom-right corner handle
- Survive every scene rebuild (live sync, re-scan) via `to_dict()` snapshot in `_rebuild_scene`

---

## [1.8.1] — 2026-03-23

### feat: verse device graph — write-back, wiring codegen, search + physics fixes

**Write-back from property panel:**
- PROPERTIES section added to the side panel — Label and Folder fields, pre-filled on node select
- "Apply Changes" button pushes rename (`set_actor_label`) and folder move (`set_folder_path`) to the live level
- Disabled with hint for Verse-only devices that have no live actor
- Inline status feedback in panel and status bar on success or error

**Gen Wiring codegen:**
- "Gen Wiring" toolbar button generates a full `creative_device` Verse stub from the current graph
- Produces `@editable` device refs + `OnBegin` subscriptions + handler stubs
- Copy to clipboard + Write to project via `verse_write_file`
- Context-aware empty state: distinct messages for "no path set" vs "no connections found"
- Path field placeholder: `"Verse project path — required for wiring scan"`

**Search + physics fixes:**
- Search now syncs edge visibility (edges hide if either endpoint is filtered out)
- Physics sim skips hidden nodes — no more ghost jitter from invisible actors
- Selected node clears from panel when filtered out by search

**Dashboard + UI polish:**
- Spinbox minimum width enforced at 90px — no more number clipping against arrows
- Removed `::up-arrow`/`::down-arrow` CSS — prevented crash in UEFN's embedded Qt
- Dashboard title: removed `⬡` prefix
- All tool windows now use canonical TB icon (blue hexagon, white "TB") via `make_toolbelt_icon()`
- Flagship Tools group added to Quick Actions tab (Verse Graph, World State, Device Catalog)
- `ToolbeltWindow` title format documented: `"UEFN Toolbelt — Tool Name"`

---

## [1.8.0] — 2026-03-23

### feat: lighting, post-process, audio foundation (217 → 229 tools)

**Expanded `lighting_mastery.py` — 4 new tools:**
- `light_place`: Spawn point/spot/rect/directional/sky light at camera. Sets intensity, hex color, attenuation radius.
- `light_set`: Batch-set intensity, color, attenuation on selected lights. Only provided params are changed.
- `sky_set_time`: Simulate time-of-day (0–24h) by pitching the DirectionalLight using elevation math.
- `light_list`: Audit all light actors in the level — type, label, location, intensity.

**New `postprocess_tools.py` — 4 new tools:**
- `postprocess_spawn`: Find or create a global (infinite-extent) PostProcessVolume. No duplicates.
- `postprocess_set`: Set bloom, exposure, contrast, vignette, saturation on the level's PPV.
- `postprocess_preset`: Apply a named visual preset: `cinematic`, `night`, `vibrant`, `bleach`, `horror`, `fantasy`, `reset`.
- `world_settings_set`: Change gravity (cm/s²) and time dilation world-wide.

**New `audio_tools.py` — 4 new tools:**
- `audio_place`: Spawn AmbientSound at camera. Optionally assign `/Game/...` sound asset, set volume and radius.
- `audio_set_volume`: Batch-set volume multiplier on selected AmbientSound actors.
- `audio_set_radius`: Override attenuation falloff radius on selected sounds.
- `audio_list`: Audit all AmbientSound actors — label, folder, asset, volume.

**Fixed:**
- `register_tool()` decorator: removed invalid `parameters={}` kwarg from all new tools.
- `lighting_mastery.py`: refactored to match project patterns — `_actor_sub()` helper, `log_info/error`, `undo_transaction`.

---

## [1.7.0] — 2026-03-23

### feat: zone tools, proximity placement, auto-cluster, class replace (204 → 217 tools)

**New modules — 13 new tools (204 → 217):**

- **`zone_tools.py`** (7 tools) — Full zone lifecycle management.
  `zone_spawn`: spawn a visible cube zone marker at the camera position with configurable
  width/depth/height. `zone_resize_to_selection`: resize and reposition a zone actor to
  exactly contain all other selected actors (with optional padding). `zone_snap_to_selection`:
  move zone center to match combined bounds without resizing. `zone_select_contents`: select
  every level actor whose pivot falls inside the zone bounds (with optional expand).
  `zone_move_contents`: move zone + all actors inside it by a world-space offset as a unit.
  `zone_fill_scatter`: fill zone volume with scattered copies of an asset using Poisson-style
  min-spacing. `zone_list`: list all zone actors with their dimensions and world position.
  Works with any box-shaped actor as the zone reference — mutator zone devices, trigger
  volumes, or our spawned cube markers.

- **`proximity_tools.py`** (6 tools) — Relative placement and batch automation.
  `actor_place_next_to`: move the last selected actor flush against the first on any face
  (+X/-X/+Y/-Y/+Z/-Z) with optional gap and center-alignment. Uses world bounds for accuracy.
  `actor_chain_place`: arrange selected actors end-to-end along an axis — each actor's min
  face touches the previous actor's max face (great for walls, corridors, fences).
  `actor_duplicate_offset`: duplicate selected actors N times with exact cumulative offset —
  stamp arrays, rows, and grids without manual copy-paste.
  `actor_replace_class`: replace every actor whose class/label matches a filter with a fresh
  instance of a new asset — preserves transform, label, folder. Always `dry_run=True` first.
  `actor_cluster_to_folder`: greedy XY-proximity clustering — groups nearby actors into World
  Outliner subfolders automatically (great for cleaning up large levels).
  `actor_copy_to_positions`: stamp copies of a selected actor at every position in a
  `[[x,y,z],...]` list — batch placement from generated coordinates.

**Dashboard improvements:**
- Zone Spawner group added to Procedural tab — spawn, fill, resize, snap, select, move
- Proximity & Duplication group added to Bulk Ops tab — place next to, chain, duplicate
  offset, replace class (dry run + execute), auto-cluster

---

## [1.6.0] — 2026-03-23

### feat: actor organization, advanced alignment, sign tools, PCG scatter, camera-spawn

**New modules — 33 new tools (171 → 204):**

- **`sign_tools.py`** (7 tools) — TextRenderActor signs, NOT Fortnite Billboard devices.
  `sign_spawn_bulk`: spawn N signs in row/column/grid at camera. `sign_batch_edit`: change
  text/color/size on all selected signs at once. `sign_batch_set_text`: assign individual
  strings per sign. `sign_batch_rename`: sequential rename with optional text sync.
  `sign_list` / `sign_clear`: audit and cleanup. `label_attach`: floating text label above
  selected actor, parented so it follows — perfect for NPC name tags. Supports yaw rotation.

- **`actor_org_tools.py`** (10 tools) — Full actor organization suite.
  `actor_attach_to_parent`: last-selected becomes parent, Maya-style. `actor_detach`: detach
  preserving world transforms. `actor_move_to_folder` / `actor_move_to_root`: one-click folder
  management. `actor_rename_folder`: re-path all actors in a folder. `actor_select_by_folder` /
  `actor_select_same_folder` / `actor_select_by_class`: selection helpers. `actor_folder_list`:
  full folder map with actor counts. `actor_match_transform`: copy loc/rot/scale from first
  selected to all others.

- **`advanced_alignment.py`** (6 tools) — Beyond the basic bulk_align/bulk_distribute.
  `align_to_reference`: snap axis to first/last selected actor's position.
  `distribute_with_gap`: exact cm gap between bounding boxes (not pivot-to-pivot).
  `rotate_around_pivot`: orbit selection around center-of-bounds or first actor.
  `align_to_surface`: snap_objects_to_floor with Z offset. `match_spacing`: even pivot
  spacing between endpoints. `align_to_grid_two_points`: local grid from two anchor actors.

- **`foliage_tools.py`** additions (2 tools) — PCG-style scatter.
  `scatter_avoid`: Poisson scatter with obstacle rejection (avoid_class / avoid_radius filters).
  `scatter_road_edge`: place props along both shoulders of a path defined by waypoints or
  SplineActor — resamples at spacing intervals, offsets perpendicular to tangent.

**Dashboard improvements:**
- All spawn/scatter/pattern buttons now read viewport camera position at click time
- Fixed `lambda s=s:` bug: PySide6 `clicked(bool)` signal was overriding loop variable
- Fixed pattern buttons: was passing `center=` but tools expect `origin=`
- PCG Scatter group added to Procedural tab
- Advanced Alignment + Actor Organization groups added to Bulk Ops tab
- Sign Spawner, Sign Batch Edit, Floating Label Attach groups added to Text tab

**Fixes:**
- `scatter_avoid` with no filter was treating all 2000 level actors as obstacles — now
  requires at least one filter to be set
- `scatter_road_edge` rewritten to accept `points=[[x,y,z],...]` waypoint list — no
  SplineActor required
- Arena buttons: `apply_team_colors=True` was landing as `size` arg due to signal bool —
  fixed with `lambda *_, s=s:`
- `sign_tools` naming: all tools renamed from `billboard_*` to `sign_*` to avoid confusion
  with Fortnite Billboard devices (V2, not Python-controllable)

---

## [1.5.3] — 2026-03-22

### feat: online plugin hub, describe_tool mcp command, attribution

- **Plugin Hub tab** — "Browse Online Hub" section fetches `registry.json` live from GitHub.
  Core tools (BUILT-IN badge, green cards, by Ocean Bennett) and Community Plugins (Install button)
  render as separate sections. Cache-busted with `?t=<timestamp>` on every refresh.
- **`registry.json`** (new) — GitHub-hosted community plugin index. 10 core tool entries,
  community plugin entry format documented. PRs welcome to add third-party tools.
- **`describe_toolbelt_tool`** MCP command — returns full parameter schema for any single tool
  without loading the entire `tool_manifest.json`. AI agents use this before calling
  `run_toolbelt_tool()` to verify parameter names, types, and defaults.
- **Attributions** — ImmatureGamer (verse device graph concept) and Kirch/@KirchCreator
  (MCP server concept) credited in source, README, and About tab.
- **docs**: `README.md` Plugin Hub & Community Ecosystem section; `plugin_dev_guide.md`
  Path A (registry listing) vs Path B (core PR) distribution guide; `CLAUDE.md` updated.

---

## [1.5.2] — 2026-03-22

### feat: setup status panel, coverage improvements, pyside6 multi-drive detection

- **Setup Status panel** — First-run health badge in Quick Actions tab. Five checks:
  PySide6 (✓/✗), tool registry count ≥ 171 (✓/✗), MCP bridge bound port (✓/⚠),
  config file (✓/✗), verse-book (✓/⚠). Shows on every dashboard open.
- **`install.py`** — PySide6 auto-detect now scans C/D/E drives and known Game Pass paths
  instead of hardcoded `C:\Program Files`. `_find_ue_python()` and `_ensure_pyside6()`
  added. Install flow is now 3 clearly labeled steps.
- **`deploy.bat`** — PySide6 check loops over C/D/E drives. Added
  `!! TEST IN UEFN BEFORE COMMITTING !!` banner at end of deploy.
- **`list_untested.py`** — Fixed repo root path (was resolving to `Content/` not repo root).
  Broad string literal detection catches tools listed in test arrays, not just `run("name")`
  calls. CI exit codes added (0 = full coverage, 1 = gaps). Coverage improved 69% → 78%.
- **Two-phase validation workflow** documented in `CLAUDE.md`, `plugin_dev_guide.md`,
  `deploy.bat`, and persistent memory: Phase 1 = `ast.parse()` syntax check; Phase 2 = live
  UEFN test with hard refresh bundle before every commit.

---

## [1.5.1] — 2026-03-22

### refactor: theme system — single source of truth for all UI colors

- **`core/theme.py`** (new) — `PALETTE` dict is now the one place to change any color
  platform-wide. `QSS` is built dynamically from `PALETTE` so editing a token value
  automatically updates every widget in every window without any other changes.
- **`core/base_window.py`** (new) — `ToolbeltWindow(QMainWindow)` base class.
  Subclass instead of `QMainWindow` directly to get:
  - Dashboard QSS applied automatically
  - Slate tick driver via `show_in_uefn()` (required in UEFN)
  - `self.P` palette dict, `self.hex(token)`, and widget factory helpers
    (`make_topbar`, `make_btn`, `make_label`, `make_divider`, `make_text_area`,
    `make_hbar`, `set_hbar_value`, `make_scroll_panel`)
- **`dashboard_pyside6.py`** — `_QSS` now imported from `core/theme.py` instead of
  defined inline. No behavior change; backward-compatible.
- **`tools/verse_device_graph.py`** — `_DeviceGraphWindow` now subclasses
  `ToolbeltWindow`. Removed 45 lines of manual boilerplate (`_DASH_QSS` import block,
  `_P` dict, Slate tick registration). `_P` rebuilt from `PALETTE` for
  `QGraphicsItem` usage.
- **`core/__init__.py`** — re-exports `PALETTE`, `QSS`, `theme_color`.
- **`docs/ui_style_guide.md`** — fully rewritten to document the new architecture,
  `ToolbeltWindow` API, palette tokens, QGraphicsScene theming, and AI agent rules.

---

## [1.5.0] — 2026-03-22

### feat: verse device graph (verse_graph_open / scan / export)

Three new MCP-callable tools for visualising Verse/Creative device architecture:

- **`verse_graph_open`** — Opens a PySide6 force-directed node graph window.
  Devices are nodes; `@editable` references are edges. Animated Fruchterman-Reingold
  layout, cluster detection (Union-Find), and an Architecture Health Score (0–100).
- **`verse_graph_scan`** — Headless scan. Returns full adjacency dict so Claude Code
  can reason about island architecture without a UI.
- **`verse_graph_export`** — Exports the full graph as JSON.

Config key `verse.project_path` added so users set their Verse folder once.

### docs: ui style guide

- **`docs/ui_style_guide.md`** (new) — Canonical color palette, QSS import pattern,
  Slate tick driver, widget recipes, "what NOT to do" list, AI agent rules.
- **`CLAUDE.md`** — "UI Consistency Rule" section added near top; key file table updated.
- **`docs/plugin_dev_guide.md`** — UI Style Requirements section added with copy-paste
  snippets for plugin authors.

---

## [1.4.0] — 2026-03-21

### feat: 165 tools — selection utilities, project admin, lighting mastery, sequencer, sim proxy, config tools

Six new tool modules added in Phase 19:

- **`selection_utils`** — Smart selection by class, material, tag, proximity, bounding box.
- **`project_admin`** — Project health report, folder audits, cleanup workflows.
- **`lighting_mastery`** — Batch lightmap resolution, light channel manager, stationary light audit.
- **`sequencer_tools`** — Level sequence helpers, track export, timing utilities.
- **`sim_device_proxy`** — Read Verse simulation device state without entering PIE.
- **`config_tools`** — Dashboard-accessible `config_get` / `config_set` / `config_list` / `config_reset`.

### docs: schema deep dive and explorer updates

- `docs/SCHEMA_DEEP_DIVE.md` — Full type taxonomy, network architecture, enum tables.
- `docs/SCHEMA_EXPLORER.md` — Updated with 19-class tutorial level analysis.

---

## [1.3.0] — 2026-03-20

### feat: Phase 18 — AI-agent readiness (structured returns, tool manifest)

- All 25+ core tools updated to return `{"status", "count", "data"}` structured dicts.
  MCP callers can read results directly without parsing log output.
- **`plugin_export_manifest`** tool — generates `Saved/UEFN_Toolbelt/tool_manifest.json`
  with full parameter signatures for all registered tools.
- `schema_utils.py` added — `validate_property`, `discover_properties`, `list_classes`,
  `get_class_info` for schema-aware tool development.

---

## [1.2.0] — 2026-03-18

### feat: custom plugin system with four-gate security model

- Custom plugins auto-load from `Saved/UEFN_Toolbelt/Custom_Plugins/`.
- Four security gates: file size limit (50 KB), AST import scanner, namespace
  protection, SHA-256 integrity hash written to `plugin_audit.json`.
- `docs/plugin_dev_guide.md` published.

---

## [1.1.0] — 2026-03-15

### feat: MCP bridge + PySide6 dashboard

- `tools/mcp_bridge.py` — HTTP listener on port 8765. Claude Code connects via `.mcp.json`.
- `dashboard_pyside6.py` — 18-tab dark-theme Qt dashboard (`tb.launch_qt()`).
- Slate post-tick pattern documented in `docs/UEFN_QUIRKS.md`.

---

## [1.0.0] — 2026-03-10

### feat: initial release — 140 tools across 20 categories

Core tool categories: Materials, Procedural/Layout, Bulk Operations, Foliage,
LOD/Optimization, Asset Management, Reference Auditor, Level Snapshot, Asset Tagger,
Screenshot, Text/Signs, Verse Tools, Project Scaffold, API Explorer, Plugin Management.
