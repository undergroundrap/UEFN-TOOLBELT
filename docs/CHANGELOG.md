# UEFN Toolbelt — Changelog

All notable changes to this project are documented here.
Format: `## [version] — date` · Types: `feat` · `fix` · `refactor` · `docs` · `perf` · `test`

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
