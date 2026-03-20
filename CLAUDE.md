# UEFN Toolbelt — Claude Code Context

> This file is automatically loaded by Claude Code when you open this project.
> It gives Claude full knowledge of the UEFN Toolbelt so you can use natural language
> to control UEFN without looking up tool names or parameters.

---

## What This Project Is

**UEFN Toolbelt** is a comprehensive Python automation framework for Unreal Editor for Fortnite (UEFN 40.00+, March 2026).
It runs inside the editor and exposes 117+ tools through:
- A persistent top-menu entry (`Toolbelt ▾`) in the UEFN editor bar
- An 11-tab PySide6 dark-themed dashboard (`tb.launch_qt()`)
- An MCP HTTP bridge so Claude Code can control UEFN directly
- A Python client library (`client.py`) for non-MCP scripts

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
5. **Path format** — asset paths start with `/Game/` and use forward slashes.
   Actors are addressed by path name or label.
6. **Vectors/Rotators** — `unreal.Vector(x, y, z)` · `unreal.Rotator(pitch, yaw, roll)`
   Pitch = tilt up/down · Yaw = rotate left/right · Roll = spin

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

- Run any of the 117+ toolbelt tools by name
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
```

---

## Complete Tool Reference

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

### Foliage / Scatter

| Tool | Key Params | What it does |
|---|---|---|
| `scatter_props` | `asset_path`, `count`, `radius`, `folder="Scatter"` | Individual actor scatter |
| `scatter_hism` | `asset_path`, `count`, `radius`, `folder="Scatter"` | HISM (use for 100+) |
| `scatter_along_path` | `asset_path`, `points`, `count_per_point=3` | Along path points |
| `scatter_export_manifest` | — | Export scatter data to JSON |
| `scatter_clear` | `folder="Scatter"` | Remove all scattered actors |

---

### LOD & Optimization

| Tool | Key Params | What it does |
|---|---|---|
| `lod_auto_generate_selection` | `num_lods=4` | LODs for selected actors' meshes |
| `lod_auto_generate_folder` | `folder="/Game/"`, `num_lods=4` | Batch LOD for entire folder |
| `lod_set_collision_folder` | `folder="/Game/"`, `complexity="simple"` | Batch collision setup |
| `lod_audit_folder` | `folder="/Game/"` | Audit for missing LODs / collision |
| `memory_scan` | `scan_path="/Game/"` | Full project scan (textures + meshes) |
| `memory_scan_textures` | `scan_path`, `warn_px=2048`, `crit_px=4096` | Find oversized textures |
| `memory_scan_meshes` | `scan_path`, `warn_tris=50000` | Find high-poly meshes |
| `memory_top_offenders` | `limit=20`, `scan_path="/Game/"` | Heaviest assets ranked |
| `memory_autofix_lods` | `scan_path="/Game/"` | Auto-generate missing LODs |

```python
tb.run("lod_auto_generate_folder", folder="/Game/Meshes", num_lods=3)
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
| `text_place` | `text`, `location`, `color="#FFFFFF"`, `world_size=100.0` | Place 3D text actor |
| `text_label_selection` | `color`, `world_size` | Label each selected actor with its name |
| `text_paint_grid` | `cols=4`, `rows=4`, `cell_size=2000.0` | A1–D4 coordinate grid |
| `text_color_cycle` | — | Row of team/color labels |
| `text_save_style` | `name`, `color`, `size` | Save a named text style |
| `text_list_styles` | — | Print saved styles |
| `text_clear_folder` | — | Delete all toolbelt text actors |

---

### Verse Tools

| Tool | Key Params | What it does |
|---|---|---|
| `verse_list_devices` | — | Enumerate all Creative devices in level |
| `verse_bulk_set_property` | `property_name`, `value` | Set UPROPERTY on selection |
| `verse_select_by_name` | `name_contains` | Select devices matching label |
| `verse_select_by_class` | `class_name` | Select devices by class |
| `verse_export_report` | `output_path` | JSON export of all device properties |
| `verse_gen_game_skeleton` | `device_name` | Full game manager Verse stub |
| `verse_gen_device_declarations` | — | `@editable` declarations from selection |
| `verse_gen_elimination_handler` | `device_name` | Elimination event handler |
| `verse_gen_scoring_tracker` | `device_name` | Zone scoring tracker |
| `verse_gen_prop_spawner` | `device_name` | Trigger-controlled prop spawn stub |
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

```python
tb.run("api_export_full")
# → Saved/UEFN_Toolbelt/stubs/unreal.pyi
# Add to .vscode/settings.json: "python.analysis.extraPaths": ["Saved/UEFN_Toolbelt/stubs"]
```

---

### Plugin Management

| Tool | Key Params | What it does |
|---|---|---|
| `plugin_validate_all` | — | Validate all registered tools against schema |
| `plugin_list_custom` | — | List all loaded third-party tools from `Saved/UEFN_Toolbelt/Custom_Plugins` |

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
| `execute_python` | `code` | Run Python in UEFN (pre-populated: `unreal`, `actor_sub`, `asset_sub`, `level_sub`, `tb`) |
| `run_tool` | `tool_name`, `kwargs={}` | Run any of the 117+ toolbelt tools |
| `list_tools` | `category=""` | List all registered tools |
| `batch_exec` | `commands=[{command, params}]` | Multiple commands in one tick |
| `undo` | — | Undo last action |
| `redo` | — | Redo last undone action |
| `history` | `tail=30` | Recent command history with timing |
| `get_all_actors` | `class_filter=""` | Snapshot entire level |
| `get_selected_actors` | — | Currently selected actors |
| `spawn_actor` | `asset_path`, `location`, `rotation`, `label` | Spawn actor |
| `delete_actors` | `actor_paths=[...]` | Delete by path or label |
| `set_actor_transform` | `actor_path`, `location`, `rotation`, `scale` | Move/rotate/scale |
| `get_actor_properties` | `actor_path`, `properties=[...]` | Read editor properties |
| `list_assets` | `directory`, `recursive`, `class_filter` | List Content Browser assets |
| `get_asset_info` | `asset_path` | Asset metadata |
| `rename_asset` | `old_path`, `new_path` | Rename/move |
| `duplicate_asset` | `source_path`, `dest_path` | Duplicate |
| `delete_asset` | `asset_path` | Delete |
| `save_asset` | `asset_path` | Save |
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
| `Content/Python/init_unreal.py` | Auto-runs on editor start, registers all tools, injects Toolbelt menu |
| `Content/Python/UEFN_Toolbelt/tools/` | All 21 tool modules |
| `Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py` | HTTP listener (runs inside UEFN) |
| `mcp_server.py` | External FastMCP bridge (Claude Code connects to this) |
| `client.py` | Stdlib-only HTTP client for non-MCP external scripts |
| `.mcp.json` | Claude Code MCP server config — already configured |
| `docs/uefn_python_capabilities.md` | Full UEFN Python API surface reference |
| `tests/smoke_test.py` | 5-layer health check — run `tb.smoke_test()` |
| `Saved/UEFN_Toolbelt/` | All tool outputs (screenshots, snapshots, stubs, exports) |
