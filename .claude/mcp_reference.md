# UEFN Toolbelt — MCP Commands, Patterns & Key Files

## MCP Bridge Commands (from Claude Code → UEFN)

When the listener is running, Claude Code can call these directly:

| Command | Params | What it does |
|---|---|---|
| `ping` | — | Health check + command list |
| `get_log` | `last_n=50` | Return last N lines from the MCP command log ring |
| `run_tool` | `tool_name`, `kwargs={}` | Run registered tools; `mcp_start/stop/restart` remain local-only |
| `list_tools` | `category=""` | List all registered tools |
| `describe_tool` | `tool_name` | Full manifest entry for one tool (name, description, parameters, tags) |
| `batch_exec` | `commands=[{command, params}]` | Multiple commands in one tick |
| `undo` | — | Undo last action |
| `redo` | — | Redo last undone action |
| `history` | `tail=30` | Recent command history with timing |
| `get_all_actors` | `class_filter=""` | Snapshot entire level |
| `get_selected_actors` | — | Currently selected viewport actors |
| `spawn_actor` | `asset_path`, `location`, `rotation`, `label` | Spawn actor |
| `delete_actors` | `actor_paths=[...]` | Delete by path or label |
| `set_actor_transform` | `actor_path`, `location`, `rotation`, `scale` | Move/rotate/scale |
| `set_actor_property` | `actor_path`, `property_name`, `value` | Set a single editor property on an actor |
| `get_actor_properties` | `actor_path`, `properties=[...]` | Read editor properties |
| `list_assets` | `directory`, `recursive`, `class_filter` | List Content Browser assets |
| `get_asset_info` | `asset_path` | Asset metadata |
| `get_selected_assets` | — | Currently selected Content Browser assets |
| `rename_asset` | `old_path`, `new_path` | Rename/move |
| `duplicate_asset` | `source_path`, `dest_path` | Duplicate |
| `delete_asset` | `asset_path` | Delete |
| `does_asset_exist` | `asset_path` | Check if an asset exists |
| `save_asset` | `asset_path` | Save |
| `import_asset` | `source_file`, `destination_path`, `replace_existing=True` | Import external file (FBX, PNG, etc.) into Content Browser |
| `search_assets` | `class_name`, `directory` | Asset Registry search |
| `save_current_level` | — | Save level |
| `get_level_info` | — | World name + actor count |
| `get_viewport_camera` | — | Camera loc + rot |
| `set_viewport_camera` | `location`, `rotation` | Move viewport camera |
| `create_material_instance` | `parent_path`, `instance_name`, `destination`, `scalar_params`, `vector_params` | Create MI |

---

## External HTTP Client (no MCP required)

`client.py` at the project root gives trusted same-user Python automation
authenticated access to UEFN. It reads the rotating session handoff
automatically:

```python
from client import ToolbeltClient

ue = ToolbeltClient()               # loads Saved/UEFN_Toolbelt/mcp_session.json
ue.ping()
ue.run_tool("material_apply_preset", preset="chrome")
ue.batch([
    {"command": "run_tool", "params": {"tool_name": "snapshot_save"}},
    {"command": "run_tool", "params": {"tool_name": "scatter_hism",
                                       "kwargs": {"count": 200, "radius": 3000}}},
])
```

Unauthenticated raw HTTP, browser origins, CORS preflight, non-loopback hosts,
and requests without the current bearer session are rejected before body
parsing. The handoff is same-user privileged material, not a sandbox boundary.
Arbitrary remote Python is unavailable; use registered commands or UEFN's local
Python console. Listener lifecycle and the self-managing integration suite are
local-only.

If Epic's **UEFN MCP Toolsets** beta is enabled and the listener command says
Toolbelt is not registered, Quirk #36 suppressed `init_unreal.py`. Recover once
for the current editor session before starting the listener:

```python
import UEFN_Toolbelt as tb; tb.register(); tb.run("mcp_start")
```

---

## Common Patterns Claude Should Know

### Safe destructive ops — always dry_run first
```python
tb.run("ref_delete_orphans", scan_path="", dry_run=True)   # preview
tb.run("ref_delete_orphans", scan_path="", dry_run=False)  # execute
```

### Undo safety — all actor ops are wrapped in transactions
```python
# If something goes wrong after a bulk op:
# UEFN menu: Edit → Undo (or Ctrl+Z)
# Via MCP: ue.run("undo")
```

### Checking what's selected
```python
# Via tb.run (inside UEFN):
tb.run("verse_list_devices")   # lists all devices (works regardless of selection)

# Via MCP (from Claude Code):
# get_selected_actors() → snapshot of viewport selection
# get_selected_assets() → Content Browser selection
```

### Material instance — always call update after params
```python
# This is handled automatically by toolbelt tools
# For local UEFN-console material scripting, remember:
# MaterialEditingLibrary.update_material_instance(mi)  ← never skip
```

### Large batch ops — use progress-aware tools
```python
# For 500+ actors, prefer HISM scatter over props
tb.run("scatter_hism", ...)    # one draw call
# not
tb.run("scatter_props", ...)   # N actors
```

---

## Key File Locations

| File | Purpose |
|---|---|
| `init_unreal.py` (repo root — copy to `Content/Python/`) | Generic submodule loader, auto-runs on editor start. Scans `Content/Python/` for packages with `register()` and calls them. Not Toolbelt-specific — do not overwrite an existing `init_unreal.py`; merge only the discovery loop instead. |
| `Content/Python/UEFN_Toolbelt/__init__.py` | Package root. Contains `__version__`, `register()`, `load_custom_plugins()`, `run()`, `config`. **`__version__`** is the single source of truth — bump it here when shipping a release. Propagates to audit logs, reload messages, and manifests automatically. |
| `Content/Python/UEFN_Toolbelt/core/config.py` | Persistent config system. `get_config().get/set/reset()`. Reads/writes `Saved/UEFN_Toolbelt/config.json` — survives `install.py` updates. |
| `Content/Python/UEFN_Toolbelt/tools/` | All tool modules |
| `Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py` | HTTP listener (runs inside UEFN) |
| `mcp_server.py` | External FastMCP bridge (Claude Code connects to this) |
| `client.py` | Stdlib-only HTTP client for non-MCP external scripts |
| `install.py` | One-command community installer — copies Toolbelt into any UEFN project, handles `init_unreal.py` safely |
| `deploy.bat` | Dev workflow tool — deploy + PySide6 check + prints hot-reload command. Use this for active development. |
| `prepare_launch.bat` | Host-side pre-validation helper — stashes every project `.py`, writes a recoverable manifest, and verifies zero remain before Launch Session, Push Changes, or publishing. Run Python audits first. |
| `restore_after_launch.bat` | Restores the exact manifest after remote validation; collision-checks instead of overwriting files created while the stash was active. |
| `.mcp.json` | Claude Code MCP server config — already configured |
| `docs/uefn_python_capabilities.md` | Full UEFN Python API surface reference |
| Epic UE5.7 Python API (https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/?application_version=5.7) | **Primary API reference** — check here first for correct class/method names. UEFN omits some standard UE5 APIs: `KismetMaterialLibrary` is absent, `/FortniteGame/` asset paths are blocked, some editor factories may not be exposed. |
| Epic UE4.27 Python API (https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/?application_version=4.27) | **Last resort only — UEFN is NOT UE4.27.** Some classes were more thoroughly documented in 4.27 before Epic restructured their docs. If a class or method is absent from the 5.7 reference, try 4.27 for an older doc entry. Always cross-check against `tb.run("api_inspect", name="ClassName")` — that queries the live UEFN runtime, which is authoritative. |
| `Content/Python/UEFN_Toolbelt/core/theme.py` | **Single source of truth for all UI colors.** Edit `PALETTE` here to change the platform's appearance everywhere. |
| `Content/Python/UEFN_Toolbelt/core/base_window.py` | `ToolbeltWindow` base class — subclass instead of `QMainWindow` for any tool window. Auto-applies theme + Slate tick. |
| `docs/ui_style_guide.md` | **UI Style Guide — MANDATORY** for all windowed tools and plugins. Color palette, `ToolbeltWindow` API, widget recipes. Read this before writing any PySide6 UI. |
| `docs/UEFN_QUIRKS.md` | **Critical reading for tool authors** — non-obvious UEFN Python behaviors. Key quirks: #2 Main Thread Lock, #19 V2 Device Property Wall, #23 `/Game/` mount + disk path detection, #31 PySide6 window crash pattern, #32 pak-heavy Asset Registry scans, #37 `TextRenderActor` publish blockers, #41 keyword-only `unreal.*` structs, and #42 project-Python remote validation. |
| `docs/CHANGELOG.md` | Version history — all notable changes by release. |
| `docs/plugin_dev_guide.md` | Plugin authorship guide — security model, audit format, version stamp |
| `tests/smoke_test.py` | 5-layer health check — run `tb.smoke_test()` |
| `TOOL_STATUS.md` | **Authoritative test coverage doc.** Tool count, per-tool verification status (🟡/🟠/🔴), integration test batch history, disabled tools, and roadmap. Always update when adding tools. AI agents should check this before assuming a tool is tested. |
| `ARCHITECTURE.md` | **System design reference.** Directory map, subsystem descriptions, data flow, execution constraints, and extension points. Read before making structural changes or adding new subsystems. |
| `Saved/UEFN_Toolbelt/plugin_audit.json` | Security audit of all loaded custom plugins — includes `toolbelt_version`, SHA-256 hashes, timestamps |
| `Saved/UEFN_Toolbelt/` | All tool outputs (screenshots, snapshots, stubs, exports) |
