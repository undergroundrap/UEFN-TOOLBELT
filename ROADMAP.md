# UEFN Toolbelt — Roadmap

> This is a living document. Items move between phases as priorities shift.
> Current version: **v1.5.3** · Current phase: **21**

---

## ✅ Completed

### Phase 21 — AI-Agent Readiness + Plugin Ecosystem (v1.5.x)
- Online Plugin Hub with live `registry.json` fetch from GitHub
- Core/community plugin split with BUILT-IN badges and one-click install
- `describe_toolbelt_tool` MCP command — full parameter schema for any tool
- Theme switcher system (`core/theme.py`) — 6 themes, live subscriber pattern
- Setup Status health panel in Quick Actions tab
- Two-phase validation workflow (syntax check + live UEFN test before commit)
- GitHub CI — syntax check all Python files + registry validation on every PR
- Issue templates, PR template, CONTRIBUTING.md, CHANGELOG.md
- Attributions: ImmatureGamer (verse device graph), Kirch (MCP server concept)

### Phase 20 — Structured Returns + Tool Manifest
- All 25+ core tools return `{"status", "count", "data"}` dicts
- `plugin_export_manifest` — machine-readable tool index for AI agents
- `schema_utils.py` — `validate_property`, `discover_properties`, `list_classes`

### Phase 19 — Platform Expansion (165 → 171 tools)
- `selection_utils`, `project_admin`, `lighting_mastery`
- `sequencer_tools`, `sim_device_proxy`, `config_tools`
- Verse Device Graph — force-directed node visualization, architecture health score

---

## 🔄 In Progress / Next Up

### Phase 22 — Community Plugin Growth
- Seed 3–5 real community plugins in `registry.json` with working download URLs
- Plugin Hub search/filter bar
- Plugin ratings or "verified" badge for trusted authors
- Auto-check `min_toolbelt_version` against installed version before install

### Phase 23 — Background Job Queue
- Long-running tools (`memory_scan`, `ref_full_report`, `lod_auto_generate_folder`) run in background thread with progress indicator in dashboard
- Job history panel — see what ran, how long it took, re-run from history

### Phase 24 — Verse Intelligence
- Parse actual `.verse` source files to map device bindings
- Cross-reference Verse device declarations with level actor graph
- Detect orphaned `@editable` references (declared but never wired)
- Generate Verse migration guides when UEFN API changes

---

## 🔭 Future

### AI Co-Pilot Mode
- Claude Code suggests tools based on what's selected in the viewport
- "Smart suggestions" sidebar: detects high-poly meshes → suggests `lod_auto_generate`, detects orphans → suggests `ref_delete_orphans`
- AI writes and validates Verse snippets using live device graph context

### Cloud Snapshot Sync
- Save/restore level snapshots to a cloud store (GitHub Gist or custom endpoint)
- Share snapshots with teammates — restore someone else's layout in your project

### Version-Aware Registry
- Registry entries specify `min_toolbelt_version` and `max_toolbelt_version`
- Dashboard only shows plugins compatible with the user's installed version
- Automatic deprecation warnings for plugins targeting old APIs

### UEFN Asset Marketplace Bridge
- Browse and import assets from Fab directly inside the Toolbelt dashboard
- Tag imported assets automatically with source, date, and license metadata

---

## How to Influence the Roadmap

- **Vote on features** — react with 👍 on GitHub issues to signal priority
- **Submit a plugin** — community plugins drive demand for new platform features
- **Open a discussion** — use GitHub Discussions for bigger ideas before filing an issue

The roadmap reflects what builds the most value for UEFN developers.
Moat comes from depth (tools that do more) and breadth (community that contributes).
