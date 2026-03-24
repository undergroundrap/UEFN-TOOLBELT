# UEFN Toolbelt — Claude Code Context

> This file is automatically loaded by Claude Code when you open this project.
> It gives Claude full knowledge of the UEFN Toolbelt so you can use natural language
> to control UEFN without looking up tool names or parameters.

---

## ⚠️ MANDATORY: Test in UEFN Before Every Commit

**Never commit code that hasn't been verified live in the UEFN editor.**
This is the single most important rule in this project. Syntax checks and unit tests catch Python errors but cannot catch UEFN runtime failures (wrong unreal API calls, Slate tick issues, editor crashes, invisible windows, etc.).

### When to ask the user to test

| Change type | Required test |
|---|---|
| New tool or tool modification | `tb.run("tool_name")` in UEFN Python console |
| Dashboard UI change (new tab, widget, layout) | Nuclear reload + visual inspect in UEFN |
| Theme / styling change | Nuclear reload + switch themes in Appearance tab |
| MCP bridge change | `tb.run("mcp_start")` + ping from Claude Code |
| `core/` module change | Nuclear reload + `tb.run("toolbelt_smoke_test")` |
| `install.py` / `deploy.bat` change | Run the script end-to-end |
| Any change touching PySide6 windows | Open the window, interact with it |

### Two-phase validation workflow

Every code change goes through two phases before committing:

**Phase 1 — Syntax check (run immediately, outside UEFN):**
```python
python -c "
import ast
files = ['Content/Python/UEFN_Toolbelt/tools/your_tool.py']
for f in files:
    with open(f, encoding='utf-8') as fh: ast.parse(fh.read())
    print(f'OK  {f}')
"
```
Catches Python syntax errors instantly without needing UEFN open. Always do this first — it's the fast gate.

**Phase 2 — Live UEFN test (required before every commit):**
Ask the user to run the appropriate bundle below. Syntax passing ≠ working in the editor.

### The hard refresh bundle (paste into UEFN Python console)

> ⚠️ **Nuclear reload is unsafe when adding a NEW module to `tools/__init__.py`.**
> It can cause `EXCEPTION_ACCESS_VIOLATION` as stale C++ callbacks fire against freed Python objects.
> **Use a full UEFN restart instead** when first introducing a new tool module.
> Nuclear reload is safe for iterating on existing tools. See `docs/UEFN_QUIRKS.md` Quirk #26.
>
> 🔁 **Nuclear reload fixes code. Hard restart fixes state.**
> After a crash, a project switch, or a `Shiboken` abort — close UEFN completely and reopen.
> `tb` is undefined after switching projects; always import fresh after a restart. See Quirk #27.

```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
```

Always ask the user to run this after UI or core changes. After a tool-only change, a simpler reload is enough:

```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("tool_name")
```

**Only commit after the user confirms it works in the live editor.**

---

## ⚠️ MANDATORY: Check the Registry Before Adding Any Tool

**Never build a new tool without first auditing what already exists.**
With 244 registered tools, the risk of duplicating or fragmenting existing functionality is high.
A new tool that overlaps an existing one wastes time, inflates the count, and confuses users.

### Pre-build checklist — required before writing a single line of tool code

**Step 0 — Full tool list in 5 seconds (no UEFN needed, run from repo root):**
```bash
grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
  | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort
```
This dumps every registered tool name alphabetically. Search the output before writing anything. This is the authoritative list — faster and more complete than reading CLAUDE.md tables.

To filter by keyword:
```bash
grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
  | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort | grep scatter
```

1. **Search the registry by keyword (UEFN console):**
   ```python
   for t in tb.registry.list_tools():
       if "scatter" in t["name"] or "scatter" in t.get("description","").lower():
           print(t["name"], "—", t["description"])
   ```

2. **Check the manifest for related tools:**
   ```python
   tb.run("plugin_export_manifest")
   # Read Saved/UEFN_Toolbelt/tool_manifest.json — search by name, category, and tags
   ```

3. **Read the CLAUDE.md tool tables** — every tool family has a table in this file.
   Search for the capability you want to add before writing anything.

4. **Ask: can an existing tool be extended with a new param?**
   Adding `dry_run=True` or `scope="selection"` to an existing tool is always better
   than a second tool that does 90% of the same thing.

### The rule

> If a tool already does it — extend it, don't duplicate it.
> If a tool does 80% of it — extend it with the missing 20%.
> Only create a new `@register_tool` when the capability is genuinely new.

This keeps the tool count honest, the dashboard scannable, and the MCP manifest small enough for AI agents to reason over.

---

## What This Project Is

**UEFN Toolbelt** is a comprehensive Python automation framework for Unreal Editor for Fortnite (UEFN 40.00+, March 2026).
It runs inside the editor and exposes 244 tools through:
- A persistent top-menu entry (`Toolbelt ▾`) in the UEFN editor bar
- An 18-tab PySide6 dark-themed dashboard (`tb.launch_qt()`)
- An MCP HTTP bridge so Claude Code can control UEFN directly
- A Python client library (`client.py`) for non-MCP scripts

## UI Consistency Rule (Enforced)

> **Any PySide6 window opened by any tool, plugin, or AI-generated feature MUST match the
> dashboard theme exactly.**
> Read `docs/ui_style_guide.md` before writing any windowed UI.
> The short version:
> 1. Subclass `ToolbeltWindow` from `core/base_window.py` — theme + Slate tick are automatic
> 2. **Window title format is mandatory:** `"UEFN Toolbelt — Tool Name"`. Always. Help dialogs: `"UEFN Toolbelt — Tool Name Help"`. Sub-dialogs: `"UEFN Toolbelt — Action Name"`. Never omit the prefix — every OS title bar and taskbar entry must read as Toolbelt.
> 3. Only use hex values from the palette in that guide — no purple, no navy, no off-whites
> 3. **NEVER add `make_topbar()` unless it carries multiple real toolbar buttons** (scan, export, filter, etc.). The OS title bar set via `title=` already shows the window name. A topbar whose only content is a title label + stretch (even with one small utility button like `?`) is redundant visual noise — remove it. This applies to main windows AND sub-dialogs (help, edit, confirm). If in doubt: does removing the topbar lose any functionality? If no → remove it.
> 4. **Every tool window must have a `?` help button** that opens a `_HelpDialog(ToolbeltWindow)`. No exceptions. If the window has a topbar → `?` goes last on the right. If no topbar → `?` goes in the bottom action row right-aligned. See `docs/ui_style_guide.md` for the exact pattern.
> 5. For read-only text areas (help dialogs, logs): always set `editor.setLineWrapMode(QTextEdit.NoWrap)` — otherwise separator lines and fixed-width content wrap and break the layout.
> 6. Reference implementation: `tools/verse_device_graph.py` (main window has topbar with 8+ toolbar buttons — that earns it)

---

## High-Fidelity Schema (The Gospel)
The project uses a **Hybrid Schema** model for AI context:
- **Reference Schema**: `docs/uefn_reference_schema.json` (The Gospel). A 1.6MB baseline reference for all core UEFN/Fortnite classes.
- **Project-Specific Schema**: `docs/api_level_classes_schema.json` (The Brain). Generated by clicking the **"Sync Level Schema"** button in the dashboard. This file is git-ignored and contains your unique level context.
- **Workflow**: Consult the **Live Schema** first for project-specific Verse devices, and the **Reference Schema** for standard UEFN properties.
- **Update**: Use the Dashboard button whenever you add new Verse devices to sync the AI's understanding instantly.

## Tool Manifest (Phase 20 — AI-Agent Readiness)
Run `tb.run("plugin_export_manifest")` to generate `Saved/UEFN_Toolbelt/tool_manifest.json`.
This file contains every registered tool with its full Python parameter signatures:
```json
{
  "verse_list_devices": {
    "name": "verse_list_devices",
    "category": "Verse Helpers",
    "description": "List all Verse/Creative device actors in the current level.",
    "parameters": {
      "name_filter": {"type": "str", "required": false, "default": ""}
    }
  }
}
```
All 244 tools (100%) return `{"status": "ok"/"error", ...}` structured dicts as of Phase 21. Zero `None` returns remain in the codebase — MCP callers can read every result directly without parsing log output.

**Schema utility functions** (`schema_utils.py`):
- `schema_utils.validate_property(class_name, prop)` — check if a property exists and is writable
- `schema_utils.discover_properties(class_name)` — return all schema-known properties for a class
- `schema_utils.list_classes()` — return all class names in the reference schema
- `schema_utils.get_class_info(class_name)` — full class definition dict

**Author:** Ocean Bennett · **License:** AGPL-3.0

---

## UEFN Python — Critical Rules

1. **Editor-only** — Python runs in the editor, not at game runtime. Use Verse for gameplay.
2. **Main thread** — all `unreal.*` calls must happen on the main editor thread.
   The MCP bridge handles this automatically via Slate tick dispatch.
3. **No pip inside UEFN** — only stdlib and `unreal` are available in the editor.
   PySide6 is installed separately to UE's embedded Python.
4. **Save explicitly** — asset changes aren't saved automatically.
   Always call `save_asset(path)` or `save_current_level()`.
5. **Path format** — asset paths use forward slashes. In standard UE5 docs paths start with `/Game/`, but **in UEFN the Content Browser mount point is the project name** (e.g. `/Device_API_Mapping/`). `AssetData.package_name` returns the project-mount form. Never force-prepend `/Game/` to paths from the Asset Registry or Content Browser selection. `unreal.Paths.project_content_dir()` returns the FortniteGame engine path — use `unreal.Paths.project_dir() + "/Content"` instead. See `docs/UEFN_QUIRKS.md` Quirk #23.

   **Detecting the project mount point** — never take the first alphabetical non-engine mount. Epic plugin mounts (`ACLPlugin`, `AnimationWarping`, etc.) sort before user project mounts. Always use the **"most paths" approach** — the user's project has far more content than any plugin:
   ```python
   counts = {}
   for p in unreal.AssetRegistryHelpers.get_asset_registry().get_all_cached_paths():
       root = p.strip("/").split("/")[0]
       if root and root not in _SKIP_MOUNTS:
           counts[root] = counts.get(root, 0) + 1
   mount = max(counts, key=counts.get) if counts else "Game"
   ```
   Canonical implementation: `core/__init__.py` → `detect_project_mount()`. Import it with `from ..core import detect_project_mount`. Never reimplement this per-tool.
6. **Vectors/Rotators** — `unreal.Vector(x, y, z)` · `unreal.Rotator(pitch, yaw, roll)`
   Pitch = tilt up/down · Yaw = rotate left/right · Roll = spin

---

## Git Etiquette (High Priority)

> **STOP — did you test in UEFN?**
> See the "MANDATORY: Test in UEFN Before Every Commit" section at the top of this file.
> No exceptions. Syntax passing ≠ working. Only commit after the user confirms it works live.

- **Format**: `type: concise description`
- **Casing**: All lowercase. NO "Phase:", NO "Update:", NO Title Case.
- **Types**:
  - `feat`: New tools or capabilities
  - `docs`: Documentation, README, CLAUDE.md, Walkthroughs
  - `fix`: Bug fixes, registration errors, pathing issues
  - `refactor`: Internal code structure, no behavior changes
  - `test`: Updates to integration/smoke tests
  - `perf`: Performance optimizations (CPU/Memory)
- **Example**: `docs: updated readme and 8 pillars`

---

## The Industrialization Pipeline — How Claude Builds a Full Game

> Full reference: **[docs/PIPELINE.md](docs/PIPELINE.md)** — read this before starting any
> autonomous build task. It has every tool, every phase, Claude's execution script, and
> the recursive error loop in detail.

The 6-phase pipeline for autonomous UEFN game development:

```
PHASE 0 — SETUP                   ✅
  scaffold_generate                → folder structure from template
  organize_assets                  → sort loose assets by type

PHASE 1 — RECONNAISSANCE          ✅
  world_state_export               → every actor in the level (transforms + properties)
  device_catalog_scan              → 4,698 Creative devices available to place
  api_crawl_level_classes          → Python property schema for every class in level
  verse_find_project_path          → locate the correct Verse source directory

PHASE 2 — DESIGN                  ✅ (Claude reasoning, no tool calls)
  Read world_state.json + device_catalog.json
  Select game mode, devices, win condition, round flow

PHASE 3 — PLACEMENT               ✅
  spawn_actor (MCP)                → place devices from catalog asset paths
  set_actor_transform (MCP)        → position them
  device_set_property              → configure base-class properties
  device_call_method               → call V2 runtime methods

PHASE 4 — CODE GENERATION         ✅
  verse_gen_game_skeleton          → full creative_device Verse stub
  verse_gen_device_declarations    → @editable refs from live level actors
  verse_write_file                 → deploy to project Verse source directory
  [PROVEN: 6187 bytes, VerseBuild SUCCESS, first attempt — March 22 2026]

PHASE 5 — BUILD + FIX LOOP        ✅ (one human click per iteration)
  [User clicks Build Verse]
  verse_patch_errors               → errors + file content → Claude fixes → redeploy
  LOOP until build_status == "SUCCESS"
  system_build_verse               → ⏳ waiting for Epic Python compiler API (headless)

PHASE 6 — VERIFY                  ✅
  world_state_export               → confirm level matches design intent
  snapshot_save                    → checkpoint before publishing

KNOWN HARD LIMITS (Epic must unlock):
  ✗ V2 device game-logic properties (duration, score, team index) — Verse @editable only
  ✗ Verse compiler trigger from Python — subprocess approach unreliable in sandbox
  ✗ Session launch/stop from Python — no API exposed
```

**Claude's quick-start execution script:**
```python
tb.run("device_catalog_scan")        # Phase 1: full device palette
tb.run("world_state_export")         # Phase 1: current level state
# [Phase 2: Claude reasons and designs]
tb.run("verse_write_file", filename="game_manager.verse", content=verse, overwrite=True)
# [Phase 5: User clicks Build Verse]
result = tb.run("verse_patch_errors")  # read errors + file content
# [Claude fixes → verse_write_file → repeat until SUCCESS]
tb.run("snapshot_save", name="v1")   # Phase 6: checkpoint
```

---

## Controlling UEFN from Claude Code (MCP Bridge)

### First-time setup

```bash
pip install mcp   # once, outside UEFN
```

`.mcp.json` is already in this repo — Claude Code picks it up automatically.

### Start the listener in UEFN

```python
import UEFN_Toolbelt as tb; tb.run("mcp_start")
# Output Log: [MCP] ✓ Listener running on http://127.0.0.1:8765
```

Then restart Claude Code — it connects automatically.

### What Claude Code can now do

- Run any of the 244 registered tools by name
- Spawn, move, delete actors
- List/rename/import/tag assets
- Take screenshots, save level snapshots
- Execute arbitrary Python inside UEFN with full `unreal.*` access
- Read and write actor/asset properties

---

## Building Custom Plugins

Users can create third-party tools without forking this repository.
1. Create a `.py` file with a `@register_tool` decorated function.
2. Place it in `[Project]/Saved/UEFN_Toolbelt/Custom_Plugins/`.
3. It will auto-load on start and show up in the Dashboard.
See `docs/plugin_dev_guide.md` for full details. You can generate plugins for the user directly into this folder when requested!

**Security:** Every plugin passes through a four-gate security model:
1. **File size limit** — rejects files > 50 KB (blocks obfuscated payloads)
2. **AST import scanner** — parses source without executing; blocks `subprocess`, `socket`, `ctypes`, network libs
3. **Namespace protection** — custom plugins cannot overwrite core Toolbelt tools
4. **SHA-256 integrity hash** — every loaded plugin's fingerprint is written to `plugin_audit.json`

---

## Running Tools — The Main Interface

```python
import UEFN_Toolbelt as tb

# Basic
tb.run("tool_name")
tb.run("tool_name", param1=value1, param2=value2)

# Health check
tb.smoke_test()

# List everything available
for t in tb.registry.list_tools():
    print(f"{t['category']:20s} {t['name']}")

### **The "Nuclear Reload" Command**
If you have modified the Toolbelt source code, run this in the UEFN console to refresh everything without a restart.

> **When does `tb` already exist vs. when do you need to import?**
> - Same project, same session → `tb` is already defined; nuclear reload refreshes it
> - Switched to a different project → Python environment resets; `tb` is gone — run the full import line
> - Fresh UEFN launch → always import first
> - Rule of thumb: `NameError: name 'tb' is not defined` → run the full reload line below

```python
# Standard — reload + open dashboard
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()

# Iterating on the Verse Device Graph window
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("verse_graph_open")

# Reload + run integration tests (use a clean template level)
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_integration_test")

# Reload + smoke test only
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_smoke_test")

# Reload only (no UI — useful when testing tools that don't need the dashboard)
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools()
```
> [!IMPORTANT]
> Always include `tb.register_all_tools()` after a pop, otherwise the tool registry will be empty!

---

## ⚠️ V2 Device Property Wall — Critical for AI Autonomy

Fortnite V2 Creative devices (Timer Device, Capture Area, Score Manager, Guard Spawner, etc.)
store their game-logic settings as Verse `@editable` properties — **not UPROPERTYs**.
`get_editor_property`, `set_editor_property`, and `getattr` all fail silently or raise exceptions.

**DO NOT attempt to set these via `device_set_property`:**
- Countdown duration, score-to-win, team index, channel assignments, enabled state
- Anything configurable in the device's Properties panel in the UEFN editor

**What Python CAN do on V2 devices:**
- Read base-class props: `actor_guid`, `allow_highlight`, `client_current_state`, `net_priority`
- Call methods: `timer_start()`, `timer_pause()`, `timer_resume()`, `timer_set_state()`
- Move/delete/spawn (transforms always work)

**How to configure V2 devices programmatically (two paths):**

1. **Method calls** — `tb.run("device_call_method", class_filter="Timer", method="timer_start")`
2. **Verse code** — generate a `creative_device` with `@editable` refs that configures at `OnBegin`:
   ```verse
   @editable TimerDevice : timer_device = timer_device{}
   OnBegin<override>()<suspends> : void =
       TimerDevice.SetDuration(120.0)
       TimerDevice.Enable()
   ```
   Use `verse_gen_game_skeleton` to scaffold — Claude fills in the configuration block.

Full technical breakdown: `docs/UEFN_QUIRKS.md` Quirk #19, `docs/FORTNITE_DEVICES.md`.

---

## ⚠️ Development Quirks & "Main Thread Lock"

UEFN's Python execution environment has a critical architectural quirk: **The Main Thread Lock**.

### **Async Operations (Like Screenshots)**
If you call an asynchronous Unreal API (e.g., `unreal.AutomationLibrary.take_high_res_screenshot` or anything that says "queued"):
*   **The Problem**: The operation will NOT finish as long as your Python script is running. 
*   **The "Wait" Trap**: If you use `time.sleep()` to wait for a file, you are **deadlocking the engine**. Unreal needs the main thread to be free (yielded) to process its frame and write the file.
*   **The Fix**: Do not wait for files in the same script. Trigger the action, verify the request was sent, and exit. The file will appear ~1 second after the user's console command finishes.

### Common Pitfalls
- **ModuleNotFoundError on new projects**: UEFN only scans `Content/Python` on startup. If you deploy to a new project while the editor is open, restart UEFN.
- **Hot Reload vs Restart**: Use the "Nuclear Reload" for code changes, but a full restart for `init_unreal.py` changes.

### **Hot-Reloading (sys.modules)**
UEFN does not natively reload modified Python modules. Use the **"Nuclear Reload"** (provided in `README.md`) to clear `sys.modules` and force a fresh import of Toolbelt logic.

---

### Lighting

| Tool | Key Params | What it does |
|---|---|---|
| `light_place` | `light_type="point\|spot\|rect\|directional\|sky"`, `intensity`, `color="#RRGGBB"`, `attenuation` | Spawn light at camera position |
| `light_set` | `intensity`, `color`, `attenuation` | Batch-set on selected lights — only provided params change |
| `sky_set_time` | `hour=0-24` | Simulate time-of-day by pitching the DirectionalLight |
| `light_list` | — | Audit all lights — type, label, location, intensity |
| `light_cinematic_preset` | `mood="Star Wars\|Cyberpunk\|Vibrant"` | Apply mood preset to directional light + fog |
| `light_randomize_sky` | — | Randomise sun pitch/yaw for look-dev |

### Post-Process & World

| Tool | Key Params | What it does |
|---|---|---|
| `postprocess_spawn` | `unbounded=True` | Find or create a global PostProcessVolume (no duplicates) |
| `postprocess_set` | `bloom`, `exposure`, `contrast`, `vignette`, `saturation` | Set any PPV params — omit to leave unchanged |
| `postprocess_preset` | `preset="cinematic\|night\|vibrant\|bleach\|horror\|fantasy\|reset"` | Apply named visual preset |
| `world_settings_set` | `gravity`, `time_dilation` | Change gravity (cm/s²) and time dilation world-wide |

### Audio

| Tool | Key Params | What it does |
|---|---|---|
| `audio_place` | `asset_path=""`, `label`, `volume=1.0`, `radius=0.0`, `folder="Audio"` | Spawn AmbientSound at camera. Leave asset_path blank to assign manually |
| `audio_set_volume` | `volume=1.0` | Batch-set volume multiplier on selected AmbientSounds |
| `audio_set_radius` | `radius=2000.0` | Override attenuation falloff radius on selected sounds |
| `audio_list` | — | Audit all AmbientSound actors — label, asset, volume, folder |

```python
tb.run("light_place", light_type="spot", intensity=3000, color="#80C0FF", attenuation=1500)
tb.run("sky_set_time", hour=7.5)
tb.run("postprocess_preset", preset="night")
tb.run("audio_place", asset_path="/Game/Audio/A_WindLoop", volume=0.6, radius=3000)
```

---

### Materials

| Tool | Key Params | What it does |
|---|---|---|
| `material_apply_preset` | `preset="chrome"` | Apply named preset to selected actors |
| `material_list_presets` | — | Print all 17 built-in + custom presets |
| `material_randomize_colors` | `hue_range=360` | Random HSV color per actor |
| `material_gradient_painter` | `axis="X"`, `color_a`, `color_b` | World-space gradient across selection |
| `material_team_color_split` | `axis="X"` | Auto Red/Blue by world midpoint |
| `material_pattern_painter` | `pattern="checker"` | Checkerboard / stripe alternation |
| `material_glow_pulse_preview` | `intensity=5.0` | Set emissive peak for preview |
| `material_color_harmony` | `mode="complementary"` | Complementary/triadic/analogous palettes |
| `material_save_preset` | `name="MyPreset"` | Save current params as named preset |
| `material_bulk_swap` | `old_path`, `new_path`, `scope="selection"` | Replace material slot across actors |

**Built-in presets:** `chrome`, `gold`, `neon`, `hologram`, `lava`, `ice`, `concrete`,
`wood_oak`, `metal_rust`, `glass`, `team_red`, `team_blue`, `team_green`, `team_yellow`,
`glow_pulse`, `scanlines`, `iridescent`

```python
tb.run("material_apply_preset", preset="neon")
tb.run("material_gradient_painter", axis="X", color_a="#FF0000", color_b="#0000FF")
tb.run("material_bulk_swap",
       old_path="/Game/Materials/M_Old",
       new_path="/Game/Materials/M_New",
       scope="selection")   # or scope="all"
```

---

### Procedural / Layout

| Tool | Key Params | What it does |
|---|---|---|
| `arena_generate` | `size="medium"`, `apply_team_colors=True` | Symmetrical arena |
| `spline_place_props` | `count=20`, `align_to_tangent=True` | Props along selected spline |
| `spline_clear_props` | `folder="SplineProps"` | Delete spline-placed props |
| `scatter_props` | `asset_path`, `count=50`, `radius=2000.0` | Poisson-disk scatter |
| `scatter_hism` | `asset_path`, `count=500`, `radius=4000.0` | HISM scatter (one draw call) |
| `scatter_along_path` | `asset_path`, `points=[...]` | Drop clusters along path |
| `scatter_clear` | `folder="Scatter"` | Delete scattered actors |
| `scatter_export_manifest` | `folder="Scatter"` | Export positions to JSON |

```python
tb.run("arena_generate", size="large", apply_team_colors=True)
tb.run("scatter_hism", asset_path="/Game/Meshes/SM_Rock", count=300, radius=5000.0)
```

### Measurement

| Tool | Key Params | What it does |
|---|---|---|
| `measure_distance` | — | Total 3D distance between selection |
| `measure_travel_time` | `speed_type="Run"` | Estimated travel time in seconds |
| `spline_measure` | — | Precise spline world-length |

### Localization

| Tool | Key Params | What it does |
|---|---|---|
| `text_export_manifest` | `format="csv"` | Harvest level text for translation |
| `text_apply_translation` | `manifest_path` | Update actors from translated file |

---

### Prop Patterns

| Tool | Key Params | What it does |
|---|---|---|
| `pattern_grid` | `asset_path`, `rows=5`, `cols=5`, `spacing=200.0` | N×M grid |
| `pattern_circle` | `asset_path`, `count=12`, `radius=1000.0` | Evenly-spaced ring |
| `pattern_arc` | `asset_path`, `count=8`, `radius=800.0`, `angle_start=0`, `angle_end=180` | Partial arc |
| `pattern_spiral` | `asset_path`, `count=24`, `turns=3` | Archimedean spiral |
| `pattern_line` | `asset_path`, `count=10`, `start=[0,0,0]`, `end=[2000,0,0]` | Line between two points |
| `pattern_wave` | `asset_path`, `count=20`, `amplitude=200.0` | Sine wave |
| `pattern_helix` | `asset_path`, `count=30`, `height=1000.0`, `radius=400.0` | 3D corkscrew |
| `pattern_radial_rows` | `asset_path`, `rings=4`, `count_per_ring=8` | Concentric rings |
| `pattern_clear` | `preview_only=True` | Remove preview markers or all pattern actors |

```python
tb.run("pattern_circle", asset_path="/Engine/BasicShapes/Cube", count=16, radius=1500.0)
tb.run("pattern_helix", asset_path="/Game/Meshes/SM_Column",
       count=24, height=800.0, radius=300.0)
```

---

### Bulk Operations

| Tool | Key Params | What it does |
|---|---|---|
| `bulk_align` | `axis="X"` | Align selection on axis |
| `bulk_distribute` | `axis="X"` | Space selection evenly |
| `bulk_randomize` | `rot_range=360.0`, `scale_min=0.8`, `scale_max=1.2` | Randomize rot/scale |
| `bulk_snap_to_grid` | `grid=100.0` | Snap locations to world grid |
| `bulk_reset` | — | Zero rotation, reset scale to 1 |
| `bulk_mirror` | `axis="X"` | Mirror across axis |
| `bulk_normalize` | — | Normalize all scales to 1 |
| `bulk_stack` | `axis="Z"`, `gap=0.0` | Stack actors vertically |

```python
tb.run("bulk_align", axis="Z")
tb.run("bulk_snap_to_grid", grid=50.0)
tb.run("bulk_randomize", rot_range=360.0, randomize_rot=True, randomize_scale=True,
       scale_min=0.8, scale_max=1.4)
```

---

### Advanced Alignment

| Tool | Key Params | What it does |
|---|---|---|
| `align_to_reference` | `axis="Z"`, `reference="first\|last"` | Snap axis to first or last selected actor's position |
| `distribute_with_gap` | `axis="X"`, `gap=0.0` | Exact cm gap between bounding boxes (not pivot-to-pivot) |
| `rotate_around_pivot` | `angle_deg=90`, `axis="Z"`, `pivot="center\|first"` | Orbit selection around center-of-bounds or first actor |
| `align_to_surface` | `offset_z=0.0` | Snap selection to floor with optional Z offset |
| `match_spacing` | `axis="X"` | Even pivot spacing between first and last (endpoints fixed) |
| `align_to_grid_two_points` | `grid_size=100.0` | Local grid from two anchor actors, snap rest to it |

---

### Actor Organization

| Tool | Key Params | What it does |
|---|---|---|
| `actor_attach_to_parent` | — | Last selected becomes parent of all others (Maya-style) |
| `actor_detach` | — | Detach selection from parent, preserve world transforms |
| `actor_move_to_folder` | `folder_name` | Move selection to named World Outliner folder |
| `actor_move_to_root` | — | Strip folder from selection, move to root |
| `actor_rename_folder` | `old_folder`, `new_folder`, `dry_run=False` | Re-path all actors from one folder to another |
| `actor_select_by_folder` | `folder_name` | Select all actors in a named folder |
| `actor_select_same_folder` | — | Expand selection to all actors sharing the first actor's folder |
| `actor_select_by_class` | `class_filter` | Select all level actors whose class name contains filter |
| `actor_folder_list` | — | Full folder map with actor counts — great for auditing level structure |
| `actor_match_transform` | `copy_location=True`, `copy_rotation=True`, `copy_scale=False` | Copy transform from first selected to all others |

---

### Zone Tools

Zone actors can be any box-shaped actor: the cube markers spawned by `zone_spawn`, Creative Mutator Zone devices placed manually, or any actor you designate as a zone.
**Convention:** select the zone actor first, then other actors when running resize/snap tools.

| Tool | Key Params | What it does |
|---|---|---|
| `zone_spawn` | `width=1000`, `depth=1000`, `height=500`, `label="Zone"` | Spawn a visible cube zone marker at camera position, placed in the "Zones" folder |
| `zone_resize_to_selection` | `padding=50.0` | Resize zone to exactly contain all other selected actors (+ padding cm on each side) |
| `zone_snap_to_selection` | — | Move zone center to match combined selection bounds without resizing |
| `zone_select_contents` | `expand=0.0` | Select every level actor whose pivot is inside the zone's bounds |
| `zone_move_contents` | `offset_x`, `offset_y`, `offset_z` | Move zone + all actors inside it as a unit by a world-space offset |
| `zone_fill_scatter` | `asset_path`, `count=20`, `seed=42`, `min_spacing=0`, `folder="ZoneFill"` | Randomly scatter copies of an asset throughout the zone volume |
| `zone_list` | — | List all actors in the "Zones" folder with center, width, depth, height |

```python
tb.run("zone_spawn", width=4000, depth=4000, height=800, label="ArenaCenter")
# select zone, then select your props:
tb.run("zone_resize_to_selection", padding=200)
tb.run("zone_select_contents")                          # select everything inside
tb.run("zone_move_contents", offset_x=5000)             # move zone + contents together
tb.run("zone_fill_scatter", asset_path="/Engine/BasicShapes/Cube", count=50, min_spacing=300)
```

---

### Proximity & Relative Placement

| Tool | Key Params | What it does |
|---|---|---|
| `actor_place_next_to` | `direction="+X"`, `gap=0.0`, `align="center"` | Move last selected actor flush against the first on the specified face. direction: +X/-X/+Y/-Y/+Z/-Z |
| `actor_chain_place` | `axis="X"`, `gap=0.0` | Arrange selected actors end-to-end along an axis using bounds — each min face touches the previous max face |
| `actor_duplicate_offset` | `count=3`, `offset_x=300`, `offset_y=0`, `offset_z=0`, `folder=""` | Duplicate selected actor N times with cumulative offset — stamp rows/arrays without copy-paste |
| `actor_replace_class` | `old_class_filter`, `new_asset_path`, `dry_run=True`, `scope="level"` | Replace every actor matching old_class_filter with a fresh instance of new_asset_path. Always dry_run=True first |
| `actor_cluster_to_folder` | `radius=800.0`, `folder_prefix="Cluster"`, `min_cluster_size=2`, `base_folder=""` | Greedy XY-proximity clustering — groups nearby actors into World Outliner subfolders |
| `actor_copy_to_positions` | `positions=[[x,y,z],...]`, `folder="Stamps"`, `copy_rotation=True`, `copy_scale=True` | Stamp copies of the selected actor at every position in the list |

```python
# Place second prop flush against the first on +X face, 20cm gap, Y/Z centered
tb.run("actor_place_next_to", direction="+X", gap=20.0, align="center")

# Build a wall — select all wall pieces, chain them end-to-end on Y axis
tb.run("actor_chain_place", axis="Y", gap=0.0)

# Stamp 10 copies of a prop, 500cm apart on X
tb.run("actor_duplicate_offset", count=10, offset_x=500.0)

# Swap all SM_OldCrate actors with new asset (dry run first)
tb.run("actor_replace_class", old_class_filter="OldCrate",
       new_asset_path="/Game/Props/SM_NewCrate", dry_run=True)
tb.run("actor_replace_class", old_class_filter="OldCrate",
       new_asset_path="/Game/Props/SM_NewCrate", dry_run=False)

# Auto-cluster all selected actors by 1000cm proximity into folders
tb.run("actor_cluster_to_folder", radius=1000.0, folder_prefix="Island", min_cluster_size=3)

# Copy a tree prop to 50 specific coordinates
tb.run("actor_copy_to_positions",
       positions=[[0,0,0],[500,200,0],[1000,-100,50]], folder="Trees")
```

---

### Level Stamps

Save a group of placed actors as a reusable named stamp (JSON on disk), then re-place
it anywhere with optional yaw rotation and uniform scale. Full undo via `ScopedEditorTransaction`.
Only StaticMesh actors are captured — Blueprint/device actors are skipped with a warning.

**Not the same as `prefab_migrate_open`** — that tool exports `.uasset` files between projects.
Stamps are for level layout: cookie-cut a prop cluster and re-stamp it 10× across your map.

| Tool | Key Params | What it does |
|---|---|---|
| `stamp_save` | `name` | Save selected StaticMesh actors as a named stamp to `Saved/UEFN_Toolbelt/stamps/{name}.json` |
| `stamp_place` | `name`, `location=[x,y,z]`, `yaw_offset=0.0`, `scale_factor=1.0`, `folder="Stamps"` | Place stamp at camera position (or given location). Rotates all offsets + rotations by yaw_offset |
| `stamp_list` | — | List all saved stamps with actor counts |
| `stamp_info` | `name` | Print actor names, mesh paths, and relative offsets |
| `stamp_delete` | `name` | Delete a saved stamp |
| `stamp_export` | `name`, `output_path=""` | Export a stamp to a portable JSON file — defaults to `~/Desktop/stamps/{name}.json`. Share with other creators. |
| `stamp_import` | `file_path`, `name_override=""`, `overwrite=False` | Import a stamp from a JSON file into your local library. Works across projects. |

```python
# Save selected actors as "guard_post"
tb.run("stamp_save", name="guard_post")

# Place at camera position
tb.run("stamp_place", name="guard_post")

# Place at specific location, rotated 180° and scaled up
tb.run("stamp_place", name="guard_post", location=[8000, 4000, 0],
       yaw_offset=180.0, scale_factor=2.0)

# Place 4 copies at compass points — instant symmetric layout
for angle, x, y in [(0, 5000, 0), (90, 0, 5000), (180, -5000, 0), (270, 0, -5000)]:
    tb.run("stamp_place", name="guard_post", location=[x, y, 0], yaw_offset=angle)

tb.run("stamp_list")
tb.run("stamp_info",   name="guard_post")
tb.run("stamp_delete", name="guard_post")
```

---

### Foliage / Scatter

| Tool | Key Params | What it does |
|---|---|---|
| `scatter_props` | `asset_path`, `count`, `radius`, `center`, `folder="Scatter"` | Individual actor scatter at center |
| `scatter_hism` | `asset_path`, `count`, `radius`, `center`, `folder="Scatter"` | HISM (use for 100+) at center |
| `scatter_avoid` | `asset_path`, `count`, `radius`, `center`, `avoid_class`, `avoid_radius` | Poisson scatter — skips positions within avoid_radius of matching actors |
| `scatter_road_edge` | `asset_path`, `points=[[x,y,z],...]`, `edge_offset`, `spread` | Props along both shoulders of a path. Pass waypoints or select SplineActor |
| `scatter_along_path` | `asset_path`, `points`, `count_per_point=3` | Along path points |
| `scatter_export_manifest` | — | Export scatter data to JSON |
| `scatter_clear` | `folder="Scatter"` | Remove all scattered actors |
| `foliage_convert_selected_to_actor` | — | Convert meshes to foliage actors |
| `foliage_audit_brushes` | — | List all foliage type meshes |
| `entity_spawn_kit` | `kit_name` | Spawn pre-made device clusters |
| `entity_list_kits` | — | View all available quick-spawn kits |

---

### LOD & Optimization

| Tool | Key Params | What it does |
|---|---|---|
| `lod_auto_generate_selection` | `num_lods=4` | ⚠️ Disabled — UEFN mesh reduction crash (UEFN_QUIRKS.md #18) |
| `lod_auto_generate_folder` | `folder="/Game/"`, `num_lods=4` | ⚠️ Disabled — UEFN mesh reduction crash (UEFN_QUIRKS.md #18) |
| `lod_set_collision_folder` | `folder="/Game/"`, `complexity="simple"` | Batch collision setup |
| `lod_audit_folder` | `folder="/Game/"` | Audit for missing LODs / collision |
| `memory_scan` | `scan_path="/Game/"` | Full project scan (textures + meshes) |
| `memory_scan_textures` | `scan_path`, `warn_px=2048`, `crit_px=4096` | Find oversized textures |
| `memory_scan_meshes` | `scan_path`, `warn_tris=50000` | Find high-poly meshes |
| `memory_top_offenders` | `limit=20`, `scan_path="/Game/"` | Heaviest assets ranked |
| `memory_autofix_lods` | `scan_path="/Game/"` | Auto-generate missing LODs |

```python
# lod_auto_generate_folder is disabled in UEFN — use lod_audit_folder to find meshes, add LODs manually in Static Mesh Editor
tb.run("lod_audit_folder", folder_path="/Game/Meshes")
tb.run("memory_top_offenders", limit=10)
```

---

### Asset Management

| Tool | Key Params | What it does |
|---|---|---|
| `rename_dry_run` | `scan_path="/Game/"` | Preview naming violations |
| `rename_enforce_conventions` | `scan_path="/Game/"` | Fix naming convention violations |
| `rename_strip_prefix` | `prefix="Old_"`, `folder="/Game/"` | Strip a prefix from all assets |
| `rename_report` | `scan_path="/Game/"` | Export full naming audit JSON |
| `import_fbx` | `file_path`, `destination="/Game/"` | Import single FBX |
| `import_fbx_folder` | `folder_path`, `destination="/Game/"` | Batch import folder |
| `organize_assets` | `folder="/Game/"` | Sort by asset type into subfolders |
| `ui_icon_import_open` | — | Open the UI Icon Importer — paste any image from clipboard (browser, Figma, Photoshop), auto-imports with TC_UserInterface2D · NoMipmaps · TextureGroup_UI. File browse and drag-drop also supported |
| `prefab_migrate_open` | — | Open the Prefab Asset Migrator window — copy assets with full dependency closure (meshes, materials, textures) within the project or to disk for cross-project import |
| `prefab_parse_refs` | `t3d_text` | Parse T3D clipboard text (Ctrl+C in viewport) and return all asset references |
| `prefab_resolve_deps` | `asset_paths=[...]` | Resolve full dependency tree for a list of asset package paths |
| `prefab_export_to_disk` | `asset_paths=[...]`, `destination`, `flatten=False`, `dry_run=True` | Export assets + deps to disk path or duplicate within project |

**Epic naming prefixes:** `SM_` mesh · `T_` texture · `M_` material · `MI_` mat instance ·
`SK_` skeletal · `BP_` blueprint · `A_` audio · `P_` particle

---

### Reference Auditor

| Tool | Key Params | What it does |
|---|---|---|
| `ref_audit_orphans` | `scan_path="/Game/"` | Assets with no referencers |
| `ref_audit_redirectors` | `scan_path="/Game/"` | Stale ObjectRedirectors |
| `ref_audit_duplicates` | `scan_path="/Game/"` | Assets sharing the same base name |
| `ref_audit_unused_textures` | `scan_path="/Game/"` | Textures with no material refs |
| `ref_fix_redirectors` | `scan_path`, `dry_run=True` | Consolidate redirectors |
| `ref_delete_orphans` | `scan_path`, `dry_run=True` | Delete unreferenced assets |
| `ref_full_report` | `scan_path="/Game/"` | All scans → JSON health report |

```python
# Always dry_run first
tb.run("ref_fix_redirectors", scan_path="/Game", dry_run=True)
tb.run("ref_fix_redirectors", scan_path="/Game", dry_run=False)
```

---

### Level Snapshot

| Tool | Key Params | What it does |
|---|---|---|
| `snapshot_save` | `name=""`, `scope="all"` | Save actor transforms to JSON |
| `snapshot_restore` | `name` | Restore transforms from snapshot |
| `snapshot_list` | — | Print all saved snapshots |
| `snapshot_diff` | `name_a`, `name_b` | Diff two snapshots |
| `snapshot_compare_live` | `name` | Compare snapshot vs current live level |
| `snapshot_export` | `name`, `path` | Export snapshot to external path |
| `snapshot_delete` | `name` | Delete a snapshot |

```python
tb.run("snapshot_save", name="before_scatter")
# ... do work ...
tb.run("snapshot_compare_live", name="before_scatter")
tb.run("snapshot_restore", name="before_scatter")
```

---

### Asset Tagger

All tags use the `TB:` namespace prefix to avoid collisions.

| Tool | Key Params | What it does |
|---|---|---|
| `tag_add` | `key`, `value` | Tag selected CB assets |
| `tag_remove` | `key` | Remove tag key from selected assets |
| `tag_show` | — | Print tags on selected assets |
| `tag_search` | `key`, `value=""`, `folder="/Game/"` | Find assets by tag |
| `tag_list_all` | `folder="/Game/"` | All tag keys with asset counts |
| `tag_export` | `folder="/Game/"` | Export tag index to JSON |

```python
tb.run("tag_add", key="biome", value="desert")
tb.run("tag_search", key="biome", value="desert", folder="/Game/Props")
```

---

### Screenshot

Output: `Saved/UEFN_Toolbelt/screenshots/{name}_{YYYYMMDD_HHMMSS}_{W}x{H}.png`

| Tool | Key Params | What it does |
|---|---|---|
| `screenshot_take` | `width=1920`, `height=1080`, `name="shot"` | Viewport capture |
| `screenshot_focus_selection` | `width=1920`, `height=1080` | Auto-frame selection + capture |
| `screenshot_timed_series` | `count=5`, `interval=2.0`, `width=1920` | Timed burst |
| `screenshot_open_folder` | — | Print output path |

```python
tb.run("screenshot_take", width=3840, height=2160, name="hero_4k")
tb.run("screenshot_focus_selection", width=1920, height=1080, name="prop_focus")
```

---

### Text & Signs

| Tool | Key Params | What it does |
|---|---|---|
| `text_place` | `text`, `location`, `color="#FFFFFF"`, `world_size=100.0` | Place a single 3D text actor |
| `text_label_selection` | `color`, `world_size` | Label each selected actor with its name |
| `text_paint_grid` | `cols=4`, `rows=4`, `cell_size=2000.0` | A1–D4 coordinate grid |
| `text_color_cycle` | — | Row of team/color labels |
| `text_save_style` | `name`, `color`, `size` | Save a named text style |
| `text_list_styles` | — | Print saved styles |
| `text_clear_folder` | — | Delete all toolbelt text actors |
| `sign_spawn_bulk` | `count`, `text`, `prefix`, `location`, `layout="row_x\|row_y\|grid"`, `spacing`, `cols`, `color`, `world_size` | Spawn N TextRenderActor signs in a row/grid. **Not Billboard devices.** |
| `sign_batch_edit` | `text`, `color`, `world_size` | Edit selected signs — only fields you pass are changed |
| `sign_batch_set_text` | `texts=[...]` | Assign individual text to each selected sign in order |
| `sign_batch_rename` | `prefix`, `start=1`, `sync_text=False` | Rename selected signs sequentially |
| `sign_list` | `folder=""` | List all TextRenderActors with their text |
| `sign_clear` | `folder="Signs"`, `dry_run=False` | Delete signs in folder |
| `label_attach` | `offset_z=150`, `yaw=0`, `color`, `world_size`, `use_actor_name=True` | Spawn floating label above each selected actor, parented so it follows. Great for NPC name tags. |

---

### Verse Tools

| Tool | Key Params | What it does |
|---|---|---|
| `verse_list_devices` | — | Enumerate all Creative devices in level |
| `verse_bulk_set_property` | `property_name`, `value` | Set UPROPERTY on selection |
| `device_set_property` | `property_name`, `value`, `class_filter=""`, `label_filter=""`, `actor_path=""`, `dry_run=False` | **AI write layer** — set any base-class property on matched actors. Returns per-actor report. |
| `device_call_method` | `method`, `class_filter=""`, `label_filter=""`, `actor_path=""`, `method_args=[]` | **V2 runtime control** — call any exposed method on matched actors (timer_start, timer_pause, timer_resume, Enable, Disable, etc.) |
| `verse_select_by_name` | `name_contains` | Select devices matching label |
| `verse_select_by_class` | `class_name` | Select devices by class |
| `verse_export_report` | `output_path` | JSON export of all device properties |
| `verse_graph_open` | `verse_path=""` | Interactive device graph — blueprint-style category columns, **minimap** overlay (colored dots + blue viewport rect, click/drag to navigate), **category filter** dropdown, **Focus** button, **?** Help dialog, comment/note boxes, hover highlight, edge toggles, ● Live sync, write-back |
| `verse_graph_scan` | `verse_path=""` | Headless scan → full adjacency dict (MCP-friendly) |
| `verse_graph_export` | `verse_path`, `output_path` | Export device graph to JSON |
| `verse_gen_game_skeleton` | `device_name` | Full game manager Verse stub |
| `verse_gen_device_declarations` | — | `@editable` declarations from selection |
| `verse_gen_elimination_handler` | `device_name` | Elimination event handler |
| `verse_gen_scoring_tracker` | `device_name` | Zone scoring tracker |
| `verse_gen_prop_spawner` | `device_name` | Trigger-controlled prop spawn stub |
| `verse_find_project_path` | — | Auto-detect the project's Verse source directory |
| `verse_write_file` | `filename`, `content`, `subdir=""`, `overwrite=False` | **AI deploy layer** — write generated Verse directly into the project's Verse source directory, ready for compilation |
| `verse_gen_custom` | `filename`, `code`, `description` | Write arbitrary Verse to snippets folder |
| `system_build_verse` | — | Trigger Verse compilation + parse errors back as structured JSON |
| `system_get_last_build_log` | — | Read last 100 lines of the UEFN log for error analysis |
| `verse_patch_errors` | `verse_file=""` | **Phase 5 error loop** — reads build log, extracts errors with file/line/message, returns full content of every erroring .verse file so Claude can fix and redeploy in one shot |
| `spline_to_verse_points` | `sample_count=0` | Spline → Verse `vector3` array |
| `spline_to_verse_patrol` | — | Full patrol AI skeleton from spline |
| `spline_to_verse_zone_boundary` | — | Zone boundary + IsPointInZone helper |
| `spline_export_json` | — | Spline points to JSON |

---

### Project Scaffold

| Tool | Key Params | What it does |
|---|---|---|
| `scaffold_list_templates` | — | Print all templates |
| `scaffold_preview` | `template`, `project_name` | Preview without changes |
| `scaffold_generate` | `template`, `project_name` | Create full folder tree |
| `scaffold_save_template` | `template_name`, `folders=[...]` | Save custom template |
| `scaffold_organize_loose` | `project_name`, `dry_run=True` | Move loose /Game assets |

**Templates:** `uefn_standard` · `competitive_map` · `solo_dev` · `verse_heavy`

```python
tb.run("scaffold_preview", template="uefn_standard", project_name="MyIsland")
tb.run("scaffold_generate", template="uefn_standard", project_name="MyIsland")
```

---

### API Explorer

| Tool | Key Params | What it does |
|---|---|---|
| `api_search` | `query`, `category="all"` | Fuzzy-search across live unreal module |
| `api_inspect` | `name` | Full signature + docs for any class/function |
| `api_generate_stubs` | `class_name=""` | Write `.pyi` for one class or all |
| `api_list_subsystems` | — | Every `*Subsystem` in this UEFN build |
| `api_export_full` | — | Full `unreal.pyi` for IDE autocomplete |
| `api_crawl_selection` | — | Deep-scan properties of selected actors to JSON |
| `api_crawl_level_classes` | — | Headless dump of exposed properties for every class in the level |
| `api_sync_master` | — | One-click: level crawl + Verse schema merge → `docs/DEVICE_API_MAP.md` |
| `world_state_export` | — | Full live state of every actor (transforms + all readable device properties) → `world_state.json` — the AI read layer |
| `device_catalog_scan` | `extra_paths=[]`, `save_to_docs=True` | Scan Asset Registry for every Creative device Blueprint in Fortnite — not just what's placed. Builds Claude's complete device palette → `device_catalog.json` |

```python
tb.run("api_export_full")
# → Saved/UEFN_Toolbelt/stubs/unreal.pyi
# Add to .vscode/settings.json: "python.analysis.extraPaths": ["Saved/UEFN_Toolbelt/stubs"]
```

---

### Config

Persistent user settings stored in `Saved/UEFN_Toolbelt/config.json`. Survives `install.py` updates. Never edit `config.json` directly — use these tools.

| Tool | Key Params | What it does |
|---|---|---|
| `config_list` | — | Show all keys — current value + whether it's a custom or default |
| `config_get` | `key` | Read one key (e.g. `"arena.fallback_mesh"`) |
| `config_set` | `key`, `value` | Persist a value (auto-converts type to match default) |
| `config_reset` | `key` or `"all"` | Remove override — key falls back to built-in default |

```python
tb.run("config_list")
tb.run("config_set", key="scatter.default_folder", value="MyScatter")
tb.run("config_set", key="arena.fallback_mesh", value="/Game/Meshes/SM_MyFloor")
tb.run("config_reset", key="all")   # wipe all customisations
```

**Configurable keys and their defaults:**

| Key | Default |
|---|---|
| `arena.fallback_mesh` | `/Engine/BasicShapes/Cube` |
| `scatter.default_folder` | `Scatter` |
| `scatter.default_radius` | `2000.0` |
| `scatter.default_count` | `50` |
| `text.default_folder` | `ToolbeltText` |
| `text.default_color` | `#FFFFFF` |
| `text.default_size` | `100.0` |
| `screenshot.default_width` | `1920` |
| `screenshot.default_height` | `1080` |
| `screenshot.default_name` | `shot` |
| `snapshot.default_scope` | `all` |
| `verse.project_path` | `""` |

---

### Plugin Management

| Tool | Key Params | What it does |
|---|---|---|
| `level_health_report` | `scan_path="/Game"` | Run all 6 audit categories (actors, memory, assets, naming, LODs, performance) and return a unified health score 0–100 with grade (A+…F). MCP/AI friendly — structured dict return. |
| `level_health_open` | — | Open the Level Health Dashboard window — colour-coded category cards, per-issue drilldown, live audit progress. |
| `plugin_validate_all` | — | Validate all registered tools against schema |
| `plugin_list_custom` | — | List all loaded third-party tools from `Saved/UEFN_Toolbelt/Custom_Plugins` |
| `plugin_export_manifest` | — | Export `tool_manifest.json` — machine-readable index of all 244 tools with full parameter signatures (name, type, required, default) for AI-agent and automation use |

**Online Plugin Hub** — the Plugin Hub dashboard tab fetches `registry.json` live from GitHub.
- **Core Tools** (green/BUILT-IN): 10 flagship modules by Ocean Bennett, already built in
- **Community Plugins** (blue/Install): third-party `.py` files, one-click download into `Custom_Plugins/`
- Registry: `https://raw.githubusercontent.com/undergroundrap/UEFN-TOOLBELT/main/registry.json`
- To list a plugin: add an entry to `registry.json` with `"type": "community"` and open a PR

---

### Entities / Environmental / Generative / Pipeline

Low-frequency tools — check these exist before re-implementing similar functionality.

| Tool | Category | What it does |
|---|---|---|
| `entity_spawn_kit` | Entities | Spawn a pre-configured Standard Kit of Creative devices |
| `entity_list_kits` | Entities | List all available Standard Kits |
| `foliage_convert_selected_to_actor` | Environmental | Convert selected StaticMeshActors into Foliage Actors |
| `foliage_audit_brushes` | Environmental | Audit all foliage brushes and return mesh paths |
| `text_render_texture` | Generative | Render a text string into a transparent Texture2D asset |
| `text_voxelize_3d` | Generative | Voxelize text into a 3D StaticMesh using procedural cubes |
| `import_image_from_clipboard` | Pipeline | Import the current Windows Clipboard image as Texture2D |
| `import_image_from_url` | Pipeline | Download an image from URL into the Content Browser |

---

### Project Admin / Selection / Sequencer / Simulation / System

| Tool | Category | What it does |
|---|---|---|
| `project_setup` | Project Admin | One-command setup: scaffold + Verse game manager skeleton |
| `system_backup_project` | Project Admin | Timestamped .zip backup of the Content folder |
| `system_perf_audit` | Project Admin | Fast performance check of the current level |
| `select_by_property` | Selection | Select actors where a property matches a value |
| `select_by_verse_tag` | Selection | Select actors with a specific Verse tag |
| `select_in_radius` | Selection | Select all actors of a class within a radius |
| `seq_actor_to_spline` | Sequencer | Animate an actor along a spline in the Sequencer |
| `seq_batch_keyframe` | Sequencer | Add transform keyframes for all selected actors at current time |
| `sim_generate_proxy` | Simulation | Generate a Python simulation proxy for a Verse device |
| `sim_trigger_method` | Simulation | Trigger a discoverable method on a Verse device |
| `system_build_verse` | System | Trigger Verse compilation + parse errors as structured JSON |
| `system_get_last_build_log` | System | Read last 100 lines of UEFN log for error analysis |
| `system_optimize_background_cpu` | System | Disable UEFN sleep when alt-tabbed (max Python/AI speed) |
| `verse_patch_errors` | System | AI error loop: extract build errors + file content for Claude to fix |
| `toolbelt_integration_test` | Tests | ⚠️ Invasive full automation — use in clean template level only |

---

### MCP Bridge

| Tool | Key Params | What it does |
|---|---|---|
| `mcp_start` | `port=0` | Start HTTP listener (auto-detects port) |
| `mcp_stop` | — | Stop listener |
| `mcp_restart` | `port=0` | Restart after hot-reload |
| `mcp_status` | — | Print port, state, command count |

---

## MCP Bridge Commands (from Claude Code → UEFN)

When the listener is running, Claude Code can call these directly:

| Command | Params | What it does |
|---|---|---|
| `ping` | — | Health check + command list |
| `get_log` | `last_n=50` | Return last N lines from the MCP command log ring |
| `execute_python` | `code` | Run Python in UEFN (pre-populated: `unreal`, `actor_sub`, `asset_sub`, `level_sub`, `tb`) |
| `run_tool` | `tool_name`, `kwargs={}` | Run any of the 244 registered tools |
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

`client.py` at the project root gives any Python script, Go tool, or curl access to UEFN:

```python
from client import ToolbeltClient

ue = ToolbeltClient()               # connects to 127.0.0.1:8765
ue.ping()
ue.run_tool("material_apply_preset", preset="chrome")
ue.batch([
    {"command": "run_tool", "params": {"tool_name": "snapshot_save"}},
    {"command": "run_tool", "params": {"tool_name": "scatter_hism",
                                       "kwargs": {"count": 200, "radius": 3000}}},
])
```

Or with curl:
```bash
curl -X POST http://127.0.0.1:8765 \
  -H "Content-Type: application/json" \
  -d '{"command": "run_tool", "params": {"tool_name": "material_apply_preset", "kwargs": {"preset": "gold"}}}'
```

---

## Common Patterns Claude Should Know

### Safe destructive ops — always dry_run first
```python
tb.run("ref_delete_orphans", scan_path="/Game", dry_run=True)   # preview
tb.run("ref_delete_orphans", scan_path="/Game", dry_run=False)  # execute
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
# If writing raw execute_python, remember:
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
| `.mcp.json` | Claude Code MCP server config — already configured |
| `docs/uefn_python_capabilities.md` | Full UEFN Python API surface reference |
| Epic UE5.7 Python API (https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/?application_version=5.7) | **Official API reference** -- check here first for correct class/method names. UEFN omits some standard UE5 APIs: `KismetMaterialLibrary` is absent, `/FortniteGame/` asset paths are blocked, some editor factories may not be exposed. |
| `Content/Python/UEFN_Toolbelt/core/theme.py` | **Single source of truth for all UI colors.** Edit `PALETTE` here to change the platform's appearance everywhere. |
| `Content/Python/UEFN_Toolbelt/core/base_window.py` | `ToolbeltWindow` base class — subclass instead of `QMainWindow` for any tool window. Auto-applies theme + Slate tick. |
| `docs/ui_style_guide.md` | **UI Style Guide — MANDATORY** for all windowed tools and plugins. Color palette, `ToolbeltWindow` API, widget recipes. Read this before writing any PySide6 UI. |
| `docs/UEFN_QUIRKS.md` | **Critical reading for tool authors** — non-obvious UEFN Python behaviors. Key quirks: #2 Main Thread Lock, #19 V2 Device Property Wall, #23 `/Game/` mount invisible in CB + correct project mount detection. Any tool that touches assets, paths, or the Content Browser should consult this first. |
| `docs/CHANGELOG.md` | Version history — all notable changes by release. |
| `docs/plugin_dev_guide.md` | Plugin authorship guide — security model, audit format, version stamp |
| `tests/smoke_test.py` | 5-layer health check — run `tb.smoke_test()` |
| `TOOL_STATUS.md` | **Authoritative test coverage doc.** Tool count, per-tool verification status (🟡/🟠/🔴), integration test batch history, disabled tools, and roadmap. Always update when adding tools. AI agents should check this before assuming a tool is tested. |
| `Saved/UEFN_Toolbelt/plugin_audit.json` | Security audit of all loaded custom plugins — includes `toolbelt_version`, SHA-256 hashes, timestamps |
| `Saved/UEFN_Toolbelt/` | All tool outputs (screenshots, snapshots, stubs, exports) |
