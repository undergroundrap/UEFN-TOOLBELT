# UEFN Toolbelt — Tool Reference Tables

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

> **`focus=True` — always use it when spawning via MCP or the Python console.**
> All scatter, pattern, zone, and stamp tools accept `focus=True`. When set, the viewport
> jumps to an overhead view of the spawn center immediately after placement — no manual
> navigation, no "where did it spawn?" hunting. Default is `False` to preserve existing
> viewport state when running tools from the dashboard.

| Tool | Key Params | What it does |
|---|---|---|
| `arena_generate` | `size="medium"`, `apply_team_colors=True` | Symmetrical arena |
| `spline_place_props` | `count=20`, `align_to_tangent=True` | Props along selected spline |
| `spline_clear_props` | `folder="SplineProps"` | Delete spline-placed props |
| `scatter_props` | `asset_path`, `count=50`, `radius=2000.0`, **`focus=False`** | Poisson-disk scatter |
| `scatter_hism` | `asset_path`, `count=500`, `radius=4000.0`, **`focus=False`** | HISM scatter (one draw call) |
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
| `pattern_grid` | `asset_path`, `rows=5`, `cols=5`, `spacing=200.0`, **`focus=False`** | N×M grid |
| `pattern_circle` | `asset_path`, `count=12`, `radius=1000.0`, **`focus=False`** | Evenly-spaced ring |
| `pattern_arc` | `asset_path`, `count=8`, `radius=800.0`, `angle_start=0`, `angle_end=180`, **`focus=False`** | Partial arc |
| `pattern_spiral` | `asset_path`, `count=24`, `turns=3`, **`focus=False`** | Archimedean spiral |
| `pattern_line` | `asset_path`, `count=10`, `start=[0,0,0]`, `end=[2000,0,0]`, **`focus=False`** | Line between two points |
| `pattern_wave` | `asset_path`, `count=20`, `amplitude=200.0`, **`focus=False`** | Sine wave |
| `pattern_helix` | `asset_path`, `count=30`, `height=1000.0`, `radius=400.0`, **`focus=False`** | 3D corkscrew |
| `pattern_radial_rows` | `asset_path`, `rings=4`, `count_per_ring=8`, **`focus=False`** | Concentric rings |
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
| `mesh_merge_selection` | `dest_path="/Game/UEFN_Toolbelt/Merged"`, `asset_name="MergedMesh"`, `replace_originals=False` | Merge selected StaticMesh actors into one asset — one draw call. Note: API may be sandboxed in UEFN; returns clear error if so |

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
| `zone_spawn` | `width=1000`, `depth=1000`, `height=500`, `label="Zone"`, **`focus=False`** | Spawn a visible cube zone marker at camera position, placed in the "Zones" folder |
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
| `stamp_place` | `name`, `location=[x,y,z]`, `yaw_offset=0.0`, `scale_factor=1.0`, `folder="Stamps"`, **`focus=False`** | Place stamp at camera position (or given location). Rotates all offsets + rotations by yaw_offset |
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
for angle, x, y in [(0, 5000, 0), (90, 0, 5000), (180, -5000, 0), (287, 0, -5000)]:
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

### DataTable

| Tool | Key Params | What it does |
|---|---|---|
| `datatable_list` | `scan_path`, `max_results=200` | List all DataTable assets — returns path, row struct, row count |
| `datatable_row_names` | `asset_path` | List all row names in a DataTable |
| `datatable_inspect` | `asset_path` | Row struct name, row count, first 10 row names |
| `datatable_export` | `asset_path`, `output_path=""` | Export row names + metadata to JSON |
| `datatable_audit` | `scan_path`, `min_rows=1` | Health check — empty tables, missing struct, low row count |

### Textures

| Tool | Key Params | What it does |
|---|---|---|
| `texture_audit` | `scan_path`, `max_results=200` | List compression, texture group, sRGB, size for all Texture2D assets |
| `texture_set_compression` | `scan_path`, `compression="TC_DEFAULT"`, `dry_run=True` | Batch-set TextureCompressionSettings |
| `texture_set_group` | `scan_path`, `group="world"`, `dry_run=True` | Batch-set TextureGroup (LOD group) |
| `texture_set_srgb` | `scan_path`, `srgb=True`, `dry_run=True` | Batch-set sRGB flag |
| `texture_apply_preset` | `scan_path`, `preset="game"`, `dry_run=True` | Apply named preset: `game`, `ui`, `normal`, `mask`, `hdr`, `icon`, `grayscale` |

### Skeletal Mesh

| Tool | Key Params | What it does |
|---|---|---|
| `skel_list` | `scan_path`, `max_results=200` | List all SkeletalMesh assets — skeleton ref, physics asset |
| `skel_audit` | `scan_path`, `max_results=200` | Audit for missing skeleton ref or physics asset |
| `skel_list_sockets` | `asset_path` | List all sockets on a SkeletalMesh — name, bone, transform |
| `skel_set_physics_asset` | `mesh_path`, `physics_path`, `dry_run=True` | Assign a PhysicsAsset to a SkeletalMesh |

### Curves

| Tool | Key Params | What it does |
|---|---|---|
| `curve_list` | `scan_path`, `curve_type="all"`, `max_results=200` | List CurveFloat/CurveVector/CurveLinearColor assets. Filter: `float`, `vector`, `color` |
| `curve_inspect` | `asset_path` | Read all key time/value pairs from a CurveFloat |
| `curve_export` | `scan_path`, `output_path=""` | Export all curves in a folder to JSON |
| `curve_create` | `name="CM_NewCurve"`, `destination="/Game/Curves/"` | Create a new empty CurveFloat asset |

### Blueprints

| Tool | Key Params | What it does |
|---|---|---|
| `blueprint_list` | `scan_path`, `max_results=200` | List all Blueprint assets — parent class, Blueprint type |
| `blueprint_inspect` | `asset_path` | Variables, functions, and parent class of one Blueprint |
| `blueprint_audit` | `scan_path`, `max_results=200` | Check compile status — returns issue list |
| `blueprint_compile_folder` | `scan_path`, `dry_run=True`, `max_assets=50` | Compile all Blueprints in a folder |

### Landscape

| Tool | Key Params | What it does |
|---|---|---|
| `landscape_list` | — | List all Landscape actors in level — label, material, component count |
| `landscape_audit` | `warn_components=256` | Check for missing material or high component count |
| `landscape_info` | `label=""` | Detailed info on one landscape — section size, quads, render props |
| `landscape_set_material` | `material_path`, `label=""`, `dry_run=True` | Assign a material to a Landscape actor |

### Sound Assets

| Tool | Key Params | What it does |
|---|---|---|
| `sound_asset_list` | `scan_path`, `sound_type="all"`, `max_results=200` | List SoundWave/SoundCue assets — duration, channels, sample rate. Filter: `wave`, `cue` |
| `sound_asset_audit` | `scan_path`, `warn_duration_sec=60` | Find SoundWaves missing SoundClass or over duration threshold |
| `sound_attenuation_list` | `scan_path`, `max_results=200` | List all SoundAttenuation assets |
| `sound_class_list` | `scan_path`, `max_results=200` | List all SoundClass assets |

---

### Physics

Note: UEFN sandboxes `BodyInstance.bSimulatePhysics` reads — write path works, read path does not (see UEFN_QUIRKS.md Quirk #34).

| Tool | Key Params | What it does |
|---|---|---|
| `physics_add` | — | Enable Simulate Physics on selected StaticMesh actors. Fully undoable. |
| `physics_remove` | — | Disable Simulate Physics on selected StaticMesh actors. Fully undoable. |
| `physics_list` | — | Audit selection — report which actors are physics-capable (have a StaticMeshComponent). Cannot read current on/off state (UEFN sandbox). |

```python
tb.run("physics_add")     # enable on selection
tb.run("physics_remove")  # disable on selection
tb.run("physics_list")    # check which actors can have physics
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

### Viewport Navigation

> **Always use these instead of the UEFN assistant's "place a temp prop + press F" workaround.**
> All tools use UEFN's native `CAMERA ALIGN` command — no camera roll corruption.

| Tool | Key Params | What it does |
|---|---|---|
| `viewport_goto` | `x`, `y`, `z`, `pitch=-20`, `yaw=0` | Instantly teleport viewport camera to any world coordinate |
| `viewport_focus_actor` | `label` | Find actor by partial label match, select it, snap camera to it |
| `viewport_move_to_camera` | — | Move selected actors to current camera position — fly to a spot, then place things there |
| `viewport_camera_get` | — | Return current camera location + rotation (save/restore positions) |
| `viewport_showflag` | `preset="clean\|no_text\|no_icons\|geometry_only\|reset"` | Toggle UEFN viewport show flags — declutter the view instantly for screenshots or reviews |
| `viewport_bookmark_save` | `name` | Save current camera position as a named bookmark (persists across restarts) |
| `viewport_bookmark_jump` | `name` | Teleport camera to a saved named bookmark |
| `viewport_bookmark_list` | — | List all saved bookmarks with coordinates |

```python
tb.run("viewport_goto", x=5000, y=-2000, z=800)
tb.run("viewport_focus_actor", label="Cube")
tb.run("viewport_move_to_camera")
tb.run("viewport_showflag", preset="clean")         # hide text, device icons, decals
tb.run("viewport_showflag", preset="reset")         # restore everything
tb.run("viewport_bookmark_save", name="spawn_area")
tb.run("viewport_bookmark_jump", name="spawn_area")
tb.run("viewport_bookmark_list")
```

---

### Visibility & Lock

Tools for working in crowded shared levels — isolate your section, hide whole folders, lock final assets.

| Tool | Key Params | What it does |
|---|---|---|
| `actor_hide` | — | Hide selected actors in the viewport (non-destructive, reversible) |
| `actor_show` | — | Unhide currently selected actors |
| `actor_isolate` | — | Hide everything EXCEPT the current selection — focus mode |
| `actor_show_all` | — | Restore visibility for every hidden actor in the level |
| `folder_hide` | `folder_name` | Hide all actors in a World Outliner folder, e.g. `'Zones'` |
| `folder_show` | `folder_name` | Restore visibility for all actors in a folder |
| `actor_lock` | — | Lock selected actors — prevents accidental viewport moves/rotates/scales |
| `actor_unlock` | — | Unlock selected actors |

```python
tb.run("actor_isolate")                      # focus on what you have selected
tb.run("actor_show_all")                     # restore everything
tb.run("folder_hide", folder_name="Zones")   # fold away zones while placing props
tb.run("folder_show", folder_name="Zones")   # bring them back
tb.run("actor_lock")                         # lock final-placed assets
```

---

### Selection Sets

Save named groups of actors to disk. Restore them any time — even after restart.

| Tool | Key Params | What it does |
|---|---|---|
| `selection_save` | `name` | Save current viewport selection as a named set |
| `selection_restore` | `name` | Re-select all actors matching a saved set (matched by label) |
| `selection_list` | — | List all saved selection sets |

```python
tb.run("selection_save", name="arena_props")
tb.run("selection_save", name="player_spawns")
tb.run("selection_restore", name="arena_props")   # works after restart
tb.run("selection_list")
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
| `verse_patch_errors` | `verse_file=""` | **Phase 5 error loop** — reads build log, extracts errors with `file/line/col/message` + `error_type` (undefined_identifier, type_mismatch, missing_override, syntax_error, etc.) + `fix_hint` per error. Returns `errors_by_file` dict and `error_type_summary` for at-a-glance categorisation. Full content of every erroring .verse file included so Claude can fix and redeploy in one shot. |
| `verse_build_status` | `stale_threshold_sec=300` | **Lightweight build check** — reads the latest log, returns `SUCCESS`/`FAILED`/`UNKNOWN`, ISO timestamp, staleness flag, and error count. Call this after telling the user to click Build Verse to detect whether a fresh build has happened. Much lighter than `verse_patch_errors`. |
| `verse_template_list` | — | List all 6 battle-tested Verse game templates — `game_skeleton`, `elimination_scoring`, `zone_capture`, `round_flow`, `item_spawner_cycle`, `countdown_race`. Claude reads this first to pick the right template for the game mode it is building. |
| `verse_template_get` | `name` | Return full Verse source for a named template + `devices_needed` list + `next_step` instructions. Claude fills device labels from `world_state_export` then deploys. |
| `verse_template_deploy` | `name`, `filename`, `custom_source=""`, `overwrite=False` | Write a template (raw or Claude-edited) directly to the Verse source directory. Shortcut for `verse_template_get` + `verse_write_file` in one call. |
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
| `world_state_export` | — | Full live state of every actor → `world_state.json`. Per-actor: `label`, `class`, `folder` (World Outliner path), `parent` (attach parent label), `location/rotation/scale`, `bounds` (center+extent), `asset_path` (StaticMesh package path), `hidden`, `tags`, `properties`. Top-level `summary` block has `class_counts` and `folder_map` sorted by frequency — Claude reads the summary first for level structure, then drills into actors. |
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
| `plugin_export_manifest` | — | Export `tool_manifest.json` — machine-readable index of all 358 tools with full parameter signatures (name, type, required, default) + `example` call string for AI-agent and automation use |

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
| `save_all_dirty` | Project Admin | Save every unsaved asset and map in one call — no dialog. Run before switching levels or at end of session |
| `system_perf_audit` | Project Admin | Fast performance check of the current level |
| `publish_audit` | Project Admin | **Fortnite publish-readiness audit** — actor budget, required devices, lights, rogue actors, Verse build status, unsaved changes, redirectors, level name, memory. Returns `ready`/`warnings`/`blocked` with score and ordered next steps. |
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
| `toolbelt_activity_log` | System | Rolling log of all tool calls — name, status, duration, timestamp, error |
| `toolbelt_activity_stats` | System | Aggregate stats: total calls, error rate, slowest tool, most called |
| `toolbelt_activity_clear` | System | Wipe the in-memory log and activity_log.json |
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

