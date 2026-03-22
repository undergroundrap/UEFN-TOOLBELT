# UEFN Python API — Capabilities Reference

**Maintained by UEFN Toolbelt** · Verified against UEFN 40.00 (March 2026)

This document maps the Python surface area exposed by UEFN so you know exactly what the
Toolbelt can automate, what's read-only, and what doesn't exist yet.

> UEFN exposes **37,276 Python-accessible types** — 4.3× more than standard UE5.
> Python is **editor-only**. Gameplay logic lives in Verse. These two facts define everything.

---

## Quick Reference — What's Scriptable

| Domain | Power | Toolbelt Coverage | Key Classes |
|---|---|---|---|
| Asset Pipeline | Full | asset_renamer, smart_importer, reference_auditor, asset_tagger | `EditorAssetLibrary` (62), `EditorAssetSubsystem` (66) |
| Actors & Levels | Full | bulk_operations, prop_patterns, foliage_tools, level_snapshot | `EditorActorSubsystem` (45), `LevelEditorSubsystem` (49) |
| Materials | Full | material_master | `MaterialEditingLibrary` (89) |
| Static Meshes | Full | lod_tools, memory_profiler | `StaticMeshEditorSubsystem` (87) |
| Geometry Scripting | Full | — future module | `GeometryScriptingCore` (46 classes, 145+ ops) |
| PCG | Full | — future module | `PCG` (597 types) |
| Screenshots | Full | screenshot_tools | `AutomationLibrary` (58) |
| Movie Render | Full | — future module | `MovieRenderPipelineCore` (145 classes) |
| Sequencer | High | sequencer_tools | `SequencerScripting`, `MovieScene` (86) |
| Measurement | High | measurement_tools | `EditorActorSubsystem`, `Vector` math |
| Localization | High | localization_tools | `TextRenderActor`, `AssetTools` |
| Niagara VFX | High | — future module | `Niagara` (260 types) |
| Audio / MetaSound | High | — future module | `AudioMixer`, `MetasoundEngine` |
| Animation | Good | — future module | `AnimGraph` (97), `AnimGraphRuntime` (152) |
| Enhanced Input | Good | — future module | `EnhancedInput` (75 types) |
| Import / Interchange | Good | smart_importer | `InterchangeImport` (73) |
| Fortnite Classes | Read-only | verse_device_editor (inspection) | 28,850 types — mostly locked |

---

## Asset Pipeline

**Full read/write access.** This is where Python earns its keep in UEFN.

### CRUD
```python
EditorAssetLibrary.load_asset(path)
EditorAssetLibrary.save_asset(path)
EditorAssetLibrary.delete_asset(path)
EditorAssetLibrary.rename_asset(old, new)
EditorAssetLibrary.duplicate_asset(src, dst)
EditorAssetLibrary.list_assets(dir, recursive=True)
EditorAssetLibrary.find_package_referencers_for_asset(path)  # dependency graph
EditorAssetLibrary.consolidate_assets(keep, [discard])       # merge duplicates
```

### Batch
```python
EditorAssetLibrary.save_directory(path)
EditorAssetLibrary.delete_directory(path)
EditorAssetLibrary.rename_directory(old, new)
EditorAssetLibrary.checkout_directory(path)   # source control
EditorAssetLibrary.import_asset_tasks([task]) # FBX / glTF / ABC / USD
```

### Metadata & Tags
```python
EditorAssetLibrary.set_metadata_tag(asset, Name("key"), "value")
EditorAssetLibrary.get_metadata_tag_values(asset, Name("key"))
EditorAssetLibrary.find_asset_data(path)  # → AssetData (class, tags, package info)
```

**Toolbelt tools:** `rename_dry_run`, `rename_enforce_conventions`, `ref_audit_orphans`,
`ref_fix_redirectors`, `tag_add`, `tag_search`, `import_fbx`, `import_fbx_folder`, `organize_assets`

---

## Actors & Levels

**Full spawn / destroy / transform / query.** Every actor type that UEFN allows placement of.

### Spawning & Destruction
```python
EditorLevelLibrary.spawn_actor_from_object(asset, location, rotation)
EditorLevelLibrary.spawn_actor_from_class(cls, location, rotation)
EditorActorSubsystem.duplicate_actors([actors], offset)
EditorActorSubsystem.destroy_actor(actor)
```

### Transform
```python
actor.set_actor_location(Vector, sweep=False, teleport=False)
actor.set_actor_rotation(Rotator, teleport=False)
actor.set_actor_scale3d(Vector)
actor.get_actor_location() / get_actor_rotation() / get_actor_scale3d()
```

### Query & Filter
```python
EditorActorSubsystem.get_all_level_actors()
EditorActorSubsystem.get_selected_level_actors()
EditorFilterLibrary.by_class(actors, cls)
EditorFilterLibrary.by_tag(actors, tag)
EditorFilterLibrary.by_actor_label(actors, label_pattern)
```

### Level Management
```python
EditorLevelLibrary.save_current_level()
EditorLevelLibrary.load_level(path)
EditorLevelLibrary.get_level_viewport_camera_info()       # → (location, rotation)
EditorLevelLibrary.set_level_viewport_camera_info(loc, rot)
LevelEditorSubsystem.add_level_to_world(path)             # streaming
LevelEditorSubsystem.set_current_level_by_name(name)
```

**Toolbelt tools:** `bulk_align`, `bulk_distribute`, `bulk_randomize`, `bulk_mirror`,
`bulk_snap_to_grid`, `bulk_stack`, `snapshot_save`, `snapshot_restore`, `pattern_grid`,
`pattern_circle`, `pattern_spiral`, `scatter_props`, `scatter_hism`, `scatter_along_path`

---

## Materials

**89 methods.** Full node graph construction, MI parameter control, compile & validate.

### Build a Material from Scratch
```python
mat = AssetToolsHelpers.get_asset_tools().create_asset(
    "M_MyMat", "/Game/Materials", unreal.Material, unreal.MaterialFactoryNew()
)
expr = MaterialEditingLibrary.create_material_expression(
    mat, unreal.MaterialExpressionConstant3Vector, -300, 0
)
MaterialEditingLibrary.connect_material_property(
    expr, "RGB", unreal.MaterialProperty.MP_BASE_COLOR
)
MaterialEditingLibrary.recompile_material(mat)
```

### Material Instances
```python
# IMPORTANT: call update_material_instance(mi) after every param change
MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi, "Roughness", 0.1)
MaterialEditingLibrary.set_material_instance_vector_parameter_value(mi, "Color", color)
MaterialEditingLibrary.set_material_instance_texture_parameter_value(mi, "Tex", tex)
MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(mi, "UseEmissive", True)
MaterialEditingLibrary.update_material_instance(mi)  # ← never skip this
```

### Limits
- Cannot edit HLSL shader code directly
- Cannot create new expression types (use the ~200 built-in node classes)

**Toolbelt tools:** `material_apply_preset` (17 presets), `material_randomize_colors`,
`material_gradient_painter`, `material_team_color_split`, `material_glow_pulse`,
`material_color_harmony`, `material_bulk_swap`

---

## Static Meshes

**87 methods.** LODs, collisions, UVs, Nanite, vertex data, statistics.

### LODs
```python
StaticMeshEditorSubsystem.set_lods(mesh, lod_options)   # auto-generate
StaticMeshEditorSubsystem.import_lod(mesh, lod_index, filepath)
StaticMeshEditorSubsystem.set_lod_screen_sizes(mesh, [0.5, 0.2, 0.05])
StaticMeshEditorSubsystem.get_lod_count(mesh)
```

### Collisions
```python
StaticMeshEditorSubsystem.add_simple_collisions(mesh, ShapeType.BOX)
StaticMeshEditorSubsystem.set_convex_decomposition_collisions(mesh, hull_count, max_verts, precision)
StaticMeshEditorSubsystem.remove_collisions(mesh)
```

### UVs
```python
StaticMeshEditorSubsystem.generate_planar_uv_channel(mesh, channel, size, pos, rotation)
StaticMeshEditorSubsystem.generate_box_uv_channel(mesh, channel, size, pos)
StaticMeshEditorSubsystem.add_uv_channel(mesh)
StaticMeshEditorSubsystem.remove_uv_channel(mesh, channel)
```

### Other
```python
StaticMeshEditorSubsystem.enable_nanite(mesh, True)
StaticMeshEditorSubsystem.get_number_verts(mesh, lod=0)
StaticMeshEditorSubsystem.has_vertex_colors(mesh)
```

**Toolbelt tools:** `lod_auto_generate_selection`, `lod_auto_generate_folder`,
`lod_set_collision_folder`, `lod_audit_folder`, `memory_scan_meshes`, `memory_autofix_lods`

---

## Geometry Scripting

**`GeometryScriptingCore` — 46 classes, 83 enums, 145 structs.** Full programmatic mesh editing.
Not yet in the Toolbelt — next major module.

### Mesh I/O
```python
GeometryScript_AssetUtils.copy_mesh_from_static_mesh(mesh, options)
GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dyn_mesh, static_mesh)
```

### Boolean Operations
```python
GeometryScript_MeshBooleans.apply_mesh_boolean(mesh_a, transform_a, mesh_b, transform_b, BooleanOperation.UNION)
GeometryScript_MeshBooleans.apply_mesh_plane_cut(mesh, plane_origin, plane_normal)
GeometryScript_MeshBooleans.compute_mesh_convex_hull(mesh)
```

### Repair & Cleanup
```python
GeometryScript_Repair.fill_holes(mesh)
GeometryScript_Repair.resolve_t_junctions(mesh)
GeometryScript_Repair.weld_edges(mesh, tolerance)
GeometryScript_Repair.remove_degenerate_triangles(mesh)
```

### UV Baking
```python
GeometryScript_UVs.layout_uvs(mesh, channel, options)
GeometryScript_UVs.generate_lightmap_uvs(mesh, options)
GeometryScript_Bake.bake_render_capture_to_texture(mesh, targets, settings)  # normals, AO, curvature
```

---

## PCG — Procedural Content Generation

**`PCG` — 372 classes, 152 enums, 73 structs (597 total).** Trigger and read PCG graphs from Python.
Not yet in the Toolbelt — next major module.

```python
# Trigger a PCG graph on an actor
pcg_comp = actor.get_component_by_class(unreal.PCGComponent)
pcg_comp.generate(force=True)
output = pcg_comp.get_generated_graph_output()

# PCG data types available for inspection
# PCGPointData, PCGSurfaceData, PCGVolumeData, PCGSplineData, PCGLandscapeData
```

**Point generation modes:** grid, sphere surface, from mesh, from spline
**Attribute ops:** 40+ `PCGAttribute*` classes — remap, filter, noise, boolean

---

## Screenshots & Automation

**`AutomationLibrary` — 58 methods.** High-res capture, automation screenshots, visual regression.

```python
# High-res viewport capture (confirmed working in UEFN 40.00)
AutomationLibrary.take_high_res_screenshot(
    res_x=1920, res_y=1080,
    filename="shot.png",
    camera=None,              # None = current viewport camera
    capture_hdr=False,
    force_game_view=False,
)

# Visual regression
AutomationLibrary.take_automation_screenshot(name, latent_action_info)
AutomationLibrary.compare_image_against_reference(image_path, tolerance)

# UEFN-specific
# ScreenshotActor, FortCreativeCaptureScreenshotHUD
```

**Toolbelt tools:** `screenshot_take`, `screenshot_focus_selection`,
`screenshot_timed_series`, `screenshot_open_folder`

---

## Movie Render Pipeline

**`MovieRenderPipelineCore` — 145 classes, 30 enums, 35 structs.** Batch cinematic rendering.
Not yet in the Toolbelt — planned.

```python
job = unreal.MoviePipelineExecutorJob()
job.sequence = unreal.SoftObjectPath("/Game/Sequences/MySeq")
config = unreal.MoviePipelineOutputSetting()
config.output_resolution = unreal.IntPoint(3840, 2160)
pipeline = unreal.MovieGraphPipeline()
pipeline.initialize(job, config)
# State: pipeline.get_pipeline_state() → Rendering / Paused / Finished
```

---

## Sequencer & Cinematics

**`SequencerScripting` (38), `MovieScene` (86), `MovieSceneTracks` (119), `LevelSequence` (18)**

```python
# Create and populate a Level Sequence
seq = AssetTools.create_asset("LS_Cinematic", "/Game/", unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
binding = seq.add_possessable(actor)
track = binding.add_track(unreal.MovieScene3DTransformTrack)
section = track.add_section()
section.set_range(0, 240)  # frames
# Take Recorder
TakeRecorderBlueprintLibrary.start_recording(actors, settings)
```

---

## Niagara VFX

**`Niagara` — 260 types (124 classes, 76 enums, 60 structs)**

```python
# Spawn and control — yes
NiagaraFunctionLibrary.spawn_system_at_location(world, system, location)
component.set_variable_float("Lifetime", 2.0)
component.set_variable_linear_color("Color", color)
NiagaraDataChannelLibrary.read_from_niagara_data_channel(world, channel, request)

# Edit emitter internals — no (stack architecture is Blueprint-only)
```

---

## Audio / MetaSound

**`AudioMixer` (36), `MetasoundEngine` (24), `MetasoundEditor` (37), `Synthesis` (126)**

```python
# Asset management
sound_wave = EditorAssetLibrary.load_asset("/Game/Audio/MySound")
# MetaSound config (via editor properties)
metasound.set_editor_property("bAutoPlay", True)
# Rhythm-synchronized
QuartzSubsystem.create_clock(world, clock_name, clock_settings)
# Analysis
AudioSynesthesia  # 38 types for spectral / onset / loudness analysis
```

---

## Fortnite-Specific Classes — Know the Limits

**28,850 types** in the UEFN namespace. The reality: **read-heavy, write-minimal.**

| What | Status | How |
|---|---|---|
| Actor transforms | Write | `set_actor_location()`, `set_actor_rotation()` |
| Actor visibility | Write | `set_actor_hidden_in_game()` |
| Editor properties | Limited write | `set_editor_property(name, value)` — exposed props only |
| Component queries | Read | `get_components_by_class()` |
| Weapons / items / abilities | Read | Inspection only |
| AI hot spots | Write | `assign_to_hotspot()`, `set_goal_actor()` |
| Inventory | Read | No modification |
| Combat stats | Read | No modification |
| Verse functions | None | Can inspect Verse classes, cannot call them |
| Match control | None | Can't start/stop/end matches |

### Breakdown by Game Mode

| Namespace | Class Count | What you can do |
|---|---|---|
| Core Fortnite (Fort*) | 9,333 | Inspect weapons, items, abilities, world state |
| Creative | 212 | Inspect Creative devices and island data |
| LEGO / Juno | 1,044 | Read buildings, world, NPC configs |
| Rocket Racing / DelMar | 667 | Read vehicles, tracks, cosmetics |
| Festival / Sparks | 340 | Read music systems, playlists |
| AI | 806 | Read AI state + limited hot spot write |
| FortniteEditor | 325 | Asset validation, bulk editing — most useful |

**Toolbelt tools:** `verse_list_devices`, `verse_bulk_set_property`, `verse_export_report`,
`verse_graph_open`, `verse_graph_scan`, `verse_graph_export`

---

## What's Stripped from UEFN

204 classes present in standard UE5 that don't exist in UEFN:

| Category | Count | Why Removed |
|---|---|---|
| ChaosVehicle* (vehicle physics) | 47 | UEFN uses DelMar* instead |
| Datasmith / CAD / BIM | 38 | Not applicable to game dev |
| MediaPlate | 8 | Standard MediaAssets works |
| Google PAD | 6 | Android-only |
| Resonance Audio | 5 | Replaced by UEFN AudioMixer pipeline |
| Location Services | 5 | Not applicable |
| Mobile Patching | 3 | UEFN handles deployment |
| Niagara Factory | 1 | Niagara module itself works fine |
| Other niche plugins | 91 | Out of scope |

---

## What the Toolbelt Already Automates

Things that would take hours manually, now one click:

- **Naming conventions** — scan and fix prefix violations across all of `/Game` (`rename_enforce_conventions`)
- **LOD pipeline** — auto-generate LODs for every mesh in a folder (`lod_auto_generate_folder`)
- **Material templating** — 17 presets, gradients, team splits, glow, pattern, color harmony — all non-destructive MIs
- **Orphan cleanup** — find unreferenced assets and delete safely (`ref_audit_orphans`, `ref_delete_orphans`)
- **Redirector fix** — consolidate stale ObjectRedirectors from renames/moves (`ref_fix_redirectors`)
- **Prop layouts** — grid, circle, spiral, arc, wave, helix, radial rings in seconds
- **Measurement** — precise point-to-point distance and player travel time estimates
- **Localization** — bulk-export/import level text manifest for global map support
- **Level snapshots** — save/restore/diff actor transforms as JSON checkpoints
- **Asset tagging** — searchable metadata on any Content Browser asset
- **MCP bridge** — let Claude Code directly control UEFN: spawn, move, run any of the 168 registered tools

---

## The Dividing Line

```
Python  →  editor tools, content pipelines, asset management, debugging, inspection
Verse   →  game logic, player progression, gameplay systems, runtime behavior
```

They don't overlap. Python can't run at game runtime. Verse can't touch Content Browser assets.
Build pipelines and tooling in Python. Build game systems in Verse.
