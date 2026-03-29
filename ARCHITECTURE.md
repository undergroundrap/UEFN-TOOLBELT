# UEFN Toolbelt — Architecture

> How the system is built, how the parts connect, and where to look when extending it.

---

## Overview

UEFN Toolbelt is a **Python automation framework** that runs inside the Unreal Editor for Fortnite (UEFN) process. It exposes 269 editor tools through four surfaces:

| Surface | Entry point | Who uses it |
|---|---|---|
| Editor menu | `Toolbelt ▾` (top bar) | Humans — quick single-click runs |
| PySide6 dashboard | `tb.launch_qt()` | Humans — tabbed GUI, search, params |
| MCP HTTP bridge | `tb.run("mcp_start")` | AI agents — Claude Code controls UEFN |
| Python client | `client.py` | External scripts, Go tools, curl |

Everything routes through a single **`ToolRegistry`** singleton. There is one place where tools are registered, one place where they execute, and one structured return contract (`{"status": "ok"/"error", ...}`).

---

## Directory Map

```
UEFN-TOOLBELT/
│
├── Content/Python/UEFN_Toolbelt/    ← The Python package (deployed into any UEFN project)
│   ├── __init__.py                  ← Package root: __version__, register(), run(), config
│   ├── registry.py                  ← @register_tool decorator + ToolRegistry singleton
│   ├── menu.py                      ← Builds the "Toolbelt ▾" top-bar menu via Slate
│   ├── schema_utils.py              ← Reference schema query helpers
│   ├── dashboard_pyside6.py         ← 26-tab PySide6 dashboard (the primary UI)
│   ├── core/                        ← Shared utilities, no tool registrations here
│   │   ├── __init__.py              ← Re-exports: log_info, get_selected_actors, …
│   │   ├── base_window.py           ← ToolbeltWindow — subclass for all tool windows
│   │   ├── config.py                ← Persistent config (Saved/UEFN_Toolbelt/config.json)
│   │   └── theme.py                 ← PALETTE — single source of truth for UI colors
│   ├── tools/                       ← One module per feature domain
│   │   ├── __init__.py              ← Imports every module → decorators fire → tools register
│   │   ├── actor_org_tools.py
│   │   ├── advanced_alignment.py
│   │   ├── api_capability_crawler.py
│   │   ├── arena_generator.py
│   │   ├── asset_tagger.py
│   │   ├── audio_tools.py
│   │   ├── bulk_ops.py
│   │   ├── device_tools.py
│   │   ├── foliage_tools.py
│   │   ├── integration_test.py      ← 163-test full regression suite
│   │   ├── level_snapshot.py
│   │   ├── light_tools.py
│   │   ├── localization_tools.py
│   │   ├── lod_tools.py
│   │   ├── material_tools.py
│   │   ├── mcp_bridge.py            ← HTTP listener (Slate-tick dispatched)
│   │   ├── memory_tools.py
│   │   ├── pattern_tools.py
│   │   ├── plugin_tools.py
│   │   ├── postprocess_tools.py
│   │   ├── prefab_stamp.py
│   │   ├── proximity_placement.py
│   │   ├── ref_auditor.py
│   │   ├── rename_tools.py
│   │   ├── scaffold_tools.py
│   │   ├── scatter_tools.py
│   │   ├── screenshot_tools.py
│   │   ├── sign_tools.py
│   │   ├── sim_device_proxy.py
│   │   ├── smart_importer.py
│   │   ├── spline_tools.py
│   │   ├── system_build.py
│   │   ├── text_tools.py
│   │   ├── verse_device_graph.py    ← Interactive blueprint-style device graph
│   │   ├── verse_schema.py
│   │   ├── verse_tools.py
│   │   ├── world_settings.py
│   │   └── zone_tools.py
│   └── diagnostics.py               ← Health check tools (smoke test)
│
├── tests/
│   └── smoke_test.py                ← 6-layer health check (no UEFN required for layers 1-3)
│
├── community_plugins/               ← Example/reference custom plugins
│   ├── spawn_at_each_selected.py
│   └── verse_gen_checkpoint.py
│
├── docs/
│   ├── CHANGELOG.md
│   ├── UEFN_QUIRKS.md               ← Critical non-obvious UEFN Python behaviors
│   ├── ui_style_guide.md            ← Mandatory for any PySide6 UI
│   ├── PIPELINE.md                  ← 6-phase AI game-build pipeline
│   ├── plugin_dev_guide.md
│   ├── uefn_reference_schema.json   ← 1.6 MB baseline UEFN class schema (The Gospel)
│   └── api_level_classes_schema.json  ← Project-specific schema (git-ignored, generated)
│
├── init_unreal.py                   ← Generic loader — copy to Content/Python/
├── install.py                       ← One-command installer for any UEFN project
├── deploy.bat                       ← Dev workflow: deploy + PySide6 check + reload hint
├── mcp_server.py                    ← External FastMCP bridge (Claude Code connects here)
├── client.py                        ← Stdlib HTTP client for non-MCP external access
├── registry.json                    ← Plugin Hub index (community plugins listed here)
├── CLAUDE.md                        ← Auto-loaded by Claude Code — full codebase context
└── ARCHITECTURE.md                  ← This file
```

---

## Core Subsystems

### 1. Registry (`registry.py`)

The single source of truth for all tool metadata and execution.

```
@register_tool(name, category, description, tags) decorator
    └── adds ToolInfo to ToolRegistry._tools dict

ToolRegistry.execute(tool_id, **kwargs)
    └── looks up ToolInfo by name
    └── calls tool_fn(**kwargs)
    └── returns structured dict

ToolRegistry.list_tools() → [{name, category, description, tags}, ...]
ToolRegistry.categories() → [str, ...]
```

**Contract:** Every registered function must:
- Accept `**kwargs` (registry always passes kwargs)
- Return `{"status": "ok"/"error", ...}` — never `None`
- Be importable without side effects (registration happens at import time)

### 2. Tool Modules (`tools/`)

Each file is a **feature domain** — one file owns one area (lighting, scatter, verse, etc.).

Registration happens automatically: `tools/__init__.py` imports every module, which causes every `@register_tool` decorator to fire and add the tool to the registry singleton.

**Adding a tool:**
1. Create or edit the relevant domain file
2. Add `@register_tool(...)` + function
3. If new file: add `from . import my_module` to `tools/__init__.py`

### 3. Core Utilities (`core/`)

Shared helpers that tools call. No tool registrations live here. Key exports:

| Export | What it does |
|---|---|
| `get_selected_actors()` | Returns `[unreal.Actor]` from the editor selection |
| `actors_bounding_box(actors)` | Returns `(center, extent)` vectors |
| `undo_transaction(label)` | Context manager — wraps mutations in `ScopedEditorTransaction` |
| `log_info/warning/error(msg)` | Unified logging to the UEFN Output Log |
| `with_progress(label)` | Progress dialog context manager |
| `detect_project_mount()` | Returns the correct Content Browser mount point (never `/Game/`) |
| `get_config()` | Returns the persistent config singleton |
| `activity_log.record(tool_id, status, duration_ms, error)` | Called automatically by `registry.execute()` — logs every tool call to the ring buffer and `activity_log.json` |
| `activity_log.get_log(last_n)` | Returns newest-first entries from the rolling log |
| `activity_log.get_stats()` | Aggregate stats: total calls, error rate, slowest, most-called |

### 4. Dashboard (`dashboard_pyside6.py`)

A 26-tab PySide6 floating window. Each tab maps to a tool category.

- Built with `ToolbeltWindow` (subclasses `QMainWindow`, auto-applies theme, handles Slate tick)
- Tab content is generated dynamically from `registry.list_tools()` — no hardcoded tool lists
- Search bar filters across all 296 tools in real time
- All colors come from `core/theme.py` — never hardcoded in the dashboard

**Theming:** Edit `core/theme.py` → `PALETTE` dict to change the platform's appearance everywhere. The dashboard, all tool windows, and the Plugin Hub all read from this one dict.

### 5. MCP Bridge (`tools/mcp_bridge.py` + `mcp_server.py`)

Two-layer architecture:

```
Claude Code (external process)
    │  HTTP POST to http://127.0.0.1:8765
    ▼
mcp_server.py  (FastMCP — runs outside UEFN, always on)
    │  Forwards commands via HTTP to the in-editor listener
    ▼
mcp_bridge.py  (runs inside UEFN, Slate-tick dispatched)
    │  Executes on UEFN's main thread (required for all unreal.* calls)
    ▼
ToolRegistry.execute(tool_name, **kwargs)
```

The Slate-tick dispatch is critical — UEFN's main thread lock means all `unreal.*` API calls must happen on the editor's main thread. The MCP bridge queues commands and executes them in `register_slate_pre_tick_callback` callbacks.

### 6. Custom Plugin System

Users drop `.py` files into `Saved/UEFN_Toolbelt/Custom_Plugins/`. On editor start, `load_custom_plugins()` in `__init__.py` runs them through four security gates before loading:

1. **File size ≤ 50 KB** — blocks obfuscated payloads
2. **AST import scan** — blocks `subprocess`, `socket`, `ctypes`, network libs without executing
3. **API version check** — warns if plugin requires a newer Toolbelt version
4. **SHA-256 hash** — fingerprint logged to `plugin_audit.json`

Loaded plugins appear in the dashboard automatically alongside built-in tools.

### 7. Schema System

Two schemas give Claude and tools structured knowledge of the UEFN world:

| Schema | File | What it is |
|---|---|---|
| Reference Schema | `docs/uefn_reference_schema.json` | 1.6 MB baseline — all core UEFN/Fortnite classes. Static, ships with the repo. |
| Level Schema | `docs/api_level_classes_schema.json` | Project-specific — generated by "Sync Level Schema" in the dashboard. Git-ignored. |

`schema_utils.py` provides `validate_property()`, `discover_properties()`, `list_classes()`, and `get_class_info()` for querying both schemas at runtime.

---

## Data Flow — Tool Execution

```
User clicks dashboard button  ─┐
tb.run("scatter_hism", ...)   ─┤
MCP bridge command            ─┘
        │
        ▼
  ToolRegistry.execute("scatter_hism", count=500, radius=4000)
        │
        ▼
  scatter_tools.scatter_hism(count=500, radius=4000)
        │
        ├── get_selected_actors()          ← core utility
        ├── with undo_transaction(...)      ← wrapped for Ctrl+Z
        ├── unreal.HierarchicalInstancedStaticMeshComponent(...)
        └── return {"status": "ok", "count": 500, "folder": "Scatter"}
        │
        ▼
  Caller reads structured dict
  MCP returns JSON to Claude Code
  Dashboard shows status in the log panel
```

---

## Execution Environment Constraints

These are the hardest constraints. Violating them causes silent failures or crashes.

| Constraint | Rule |
|---|---|
| **Main thread** | All `unreal.*` calls must happen on the editor main thread. MCP bridge handles this via Slate tick. Never `time.sleep()` while waiting for async ops — deadlock. |
| **No pip** | Only stdlib and `unreal` in the editor. PySide6 installed separately to UE's Python. |
| **Asset paths** | UEFN mounts at project name, not `/Game/`. Use `detect_project_mount()`. Never hardcode `/Game/`. |
| **V2 devices** | `set_editor_property` fails silently on V2 Fortnite Creative devices (Timer, Score Manager, etc.) — these use Verse `@editable` props. Use `device_call_method` or generate Verse instead. |
| **Hot reload** | Nuclear reload fixes code. Hard restart fixes stale C++ state. After a crash or project switch, always do a full UEFN restart. |
| **New modules** | Adding a new `.py` file requires a full UEFN restart — not nuclear reload. Reload + new module = `EXCEPTION_ACCESS_VIOLATION` (Quirk #26). |

Full details: `docs/UEFN_QUIRKS.md`

---

## Extension Points

### Adding a tool (fastest path)
```python
# Content/Python/UEFN_Toolbelt/tools/my_domain.py
from ..registry import register_tool

@register_tool(name="my_tool", category="My Category", description="Does X.", tags=["x"])
def my_tool(count: int = 10, **kwargs) -> dict:
    import unreal
    # ... logic ...
    return {"status": "ok", "count": count}
```
Then add `from . import my_domain` to `tools/__init__.py`.

### Adding a tool window (with UI)
1. Subclass `ToolbeltWindow` from `core/base_window.py`
2. Define the class at **module level** — never inside the tool function (hot-reload creates duplicate class names → Qt crash)
3. Use only colors from `core/theme.py` → `PALETTE`
4. Reference implementation: `tools/verse_device_graph.py`

### Adding a community plugin (no fork)
1. Create a `.py` with `@register_tool`-decorated functions
2. Drop it in `[Project]/Saved/UEFN_Toolbelt/Custom_Plugins/`
3. It auto-loads and appears in the dashboard
4. To list it publicly: add entry to `registry.json`, open a PR

---

## Testing

| Test | Command | What it covers | Safe level |
|---|---|---|---|
| Syntax | `python -c "import ast; ..."` | Python parse errors | Any machine, no UEFN |
| Smoke test | `tb.run("toolbelt_smoke_test")` | 6-layer health check: env, API, registry, MCP, PySide6, Verse | Production project — read-only |
| Integration test | `tb.run("toolbelt_integration_test")` | 163 tools exercised end-to-end, partial results flushed after every test | **Template level only** — creates/deletes actors |

**Rule:** Never commit without a live UEFN test. Syntax passing ≠ working in the editor.

---

## License

Copyright © 2026 **Ocean Bennett**. Licensed under AGPL-3.0 with visible attribution requirement.
Forks and derivative works must be open source and credit the original.
Commercial integration requires a separate license — contact Ocean Bennett.

Full terms: [`LICENSE`](LICENSE)
