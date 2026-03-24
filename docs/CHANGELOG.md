# UEFN Toolbelt — Changelog

All notable changes to this project are documented here.
Format: `## [version] — date` · Types: `feat` · `fix` · `refactor` · `docs` · `perf` · `test`

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
