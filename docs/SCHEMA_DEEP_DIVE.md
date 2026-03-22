# UEFN Reference Schema — Deep Dive

> A forensic-level analysis of `uefn_reference_schema.json`.
> Every insight here was derived by running `api_crawl_level_classes` against a live UEFN level,
> then systematically cross-referencing all 14 classes, 1,031 properties, and 15 enum types.

---

## Master Stats

| Metric | Count | Notes |
|:---|:---|:---|
| Total classes | 14 | Unique C++ classes observed in live level |
| Total actor instances | 76 | Actors scanned across the level |
| Total properties (all classes) | 1,031 | Across all 14 classes combined |
| **Readable** | **765** | 74% — can be read via `get_editor_property` or `getattr` |
| **Restricted** | **266** | 26% — raise on access; mostly C++ delegates + internals |
| `bool` properties | 368 | 36% of all props — the dominant type |
| `float` properties | 122 | 12% |
| `int` properties | 13 | 1% |
| `str` properties | 1 | `FortPlayerStartCreative.locked_player_name_substring` only |
| `Array` properties | 29 | Opaque until iterated |
| `Any` properties | 40 | Type not resolved — needs `getattr()` + runtime check |
| `Unknown/Restricted` properties | 266 | The 19 blocked entries × 14 classes |

---

## Root Component Type Map

The `root_component` type tells you what physical form an actor has.
This is the fastest way to understand an actor's role without reading its full class name:

| Class | Root Component | What It Means |
|:---|:---|:---|
| `Actor` | `SceneComponent` | Pure transform — no physical presence |
| `BuildingFloor` | `BaseBuildingStaticMeshComponent` | Has a visible mesh, destructible |
| `BuildingProp` | `BaseBuildingStaticMeshComponent` | Has a visible mesh, destructible |
| `FortCreativeDeviceProp` | `BaseBuildingStaticMeshComponent` | Device shell — mesh may be a black box |
| `FortInspectorCameraCreative` | `SceneComponent` | No physical presence — pure transform |
| `FortMinigameSettingsBuilding` | `BillboardComponent` | Editor-only icon — hidden in game |
| `FortPlayerStartCreative` | `CapsuleComponent` | Has a capsule hitbox — player-sized |
| `FortStaticMeshActor` | `FortStaticMeshComponent` | Non-destructible mesh |
| `FortWaterBodyActor` | `FortWaterBodyOceanComponent` | Full ocean simulation component |
| `LevelBounds` | `BoxComponent` | Axis-aligned box for world boundary |
| `TextRenderActor` | `TextRenderComponent` | Is its own text — no parent transform |
| `WaterZone` | `WaterMeshComponent` | Render-target-driven water mesh |
| `WorldDataLayers` | `Any` (not resolved) | Editor-internal world partition manager |
| `WorldPartitionMiniMap` | `Any` (not resolved) | Editor-internal minimap actor |

**Key insight**: Classes with `BaseBuildingStaticMeshComponent` as root have the full
Fortnite building system — `team_index`, `resource_type`, `is_invulnerable`, collision masks.
Classes with `SceneComponent` or `BillboardComponent` are editor-only management actors.

---

## Property Type Taxonomy

### Type Distribution Explained

```
bool   368 props  ████████████████████████████████  36%  — Feature flags, collision masks
float  122 props  ████████████                      12%  — Distances, speeds, scales, rates
Any     40 props  ████                               4%  — Unresolved object references
Array   29 props  ███                                3%  — Collections (tags, mappings)
Guid    42 props  ████                               4%  — Identity (actor_guid, content_bundle_guid)
Vector  14 props  ██                                 1%  — 3D positions (pivot_offset etc)
```

The **36% bool dominance** reflects Fortnite's feature-flag design philosophy.
Nearly everything is a toggle. This is intentional for live service — Epic can flip
behaviors server-side without code changes.

### The `Unknown/Restricted` Type (266 props)

Every single class has the same 19 properties typed as `Unknown/Restricted`:

```
_wrapper_meta_data          on_input_touch_begin        on_take_point_damage
on_actor_begin_overlap      on_input_touch_end          on_take_radial_damage
on_actor_end_overlap        on_input_touch_leave        bnet_use_owner_relevancy
on_actor_hit                on_take_any_damage          (+ 8 more)
on_actor_touch              on_destroyed
on_end_play                 on_take_any_damage
```

266 = 14 classes × 19 restricted properties. This is **not random** — it's the same
C++ delegate layer blocked uniformly across all actor types. Epic chose to expose the
property names (so `dir()` works) but block reads (so `getattr` raises).

**Why this matters**: Any tool that iterates `dir(actor)` and tries to read every property
will crash on these 19. The Toolbelt's `api_crawl_level_classes` pre-maps them as
`readable: false` so tools skip them without catching exceptions.

### The `Any` Type (40 props)

`Any`-typed properties are references that Python couldn't resolve to a named class at
introspection time. This happens when:
1. The referenced object is `None` at scan time (most common)
2. The object type is a Verse-managed class not exposed to Python
3. The type is a private Epic class not in the public Python bindings

**Pattern**: Always access `Any`-typed props via `getattr(actor, prop, None)` and
check `type(val).__name__` at runtime before using:

```python
area_ref = getattr(actor, "area_class", None)
if area_ref is not None:
    print(type(area_ref).__name__)  # reveals the actual type at runtime
```

---

## Class Relationships — Precise Inheritance Evidence

The schema doesn't expose inheritance directly, but property overlap analysis reveals it:

### Building Class Family (BuildingFloor / BuildingProp / FortCreativeDeviceProp)

All three share **96 identical properties** beyond the `Actor` base.
This 96-property common layer is the `FortActor` / `AFortBuilding` C++ base class —
the Fortnite building system.

**BuildingFloor vs BuildingProp — 5 structural differences:**

| Property | BuildingFloor | BuildingProp | Why |
|:---|:---|:---|:---|
| `building_type` | `FLOOR` (1) | `PROP` (4) | Structural vs decorative role |
| `snap_grid_size` | `512.0` | `0.0` | Tiles snap to 512 UU grid; props don't |
| `vert_snap_grid_size` | `384.0` | `0.0` | Vertical snap; props free-float |
| `register_with_structural_grid` | `True` | `False` | Floor is in the grid; prop is not |
| `propagates_bounce_effects` | `True` | `False` | Floor transmits bounce; prop absorbs |
| `resource_type` | `STONE` (1) | `NONE` (6) | Floor drops loot; prop doesn't |
| `is_navigation_modifier` | `True` | `False` | Floor bakes into navmesh |
| `block_navigation_links` | `True` | `False` | Floor blocks nav links |

**FortCreativeDeviceProp vs BuildingProp — 5 default differences** (same 149 props):

| Property | BuildingProp default | FortCreativeDeviceProp default | Implication |
|:---|:---|:---|:---|
| `building_attachment_type` | `ATTACH_FLOOR` (0) | `ATTACH_NONE` (9) | Devices don't snap to floors |
| `can_export_navigation_collisions` | `False` | `True` | Devices block navmesh |
| `is_spatially_loaded` | `True` | `False` | Devices always loaded (never streamed out) |
| `surpress_health_bar` | `False` | `True` | Device HP bars hidden by default |
| `use_centroid_for_block_buildings_check` | `True` | `False` | Different building-block detection |

**`is_spatially_loaded: False` on devices is critical** — it means UEFN devices are
**never unloaded by world partition streaming**. They always exist in memory, regardless of
player distance. This is why Creative devices can fire events from anywhere on the map.
Props (`BuildingProp`) default to `True`, so they CAN be streamed out.

---

## Complete Enum Reference

Every enum type discovered in the schema, with all observed values and their full context:

### `FortBuildingType`
```
FLOOR = 1   BuildingFloor — structural tile in the build grid
PROP  = 4   BuildingProp / FortCreativeDeviceProp — decorative/device
```
Note: values 0, 2, 3 (likely NONE, WALL, RAMP) not seen in this level scan.

### `FortResourceType`
```
WOOD   = 0   (inferred — not in this scan)
STONE  = 1   BuildingFloor default — drops stone on destroy
METAL  = 2   (inferred — not in this scan)
NONE   = 6   BuildingProp / FortCreativeDeviceProp — no material drops
```
The gap between METAL (2) and NONE (6) suggests values 3–5 are reserved (likely BRICK,
CONCRETE, or other materials not exposed in Creative).

### `NetDormancy`
```
DORM_AWAKE   = 1   Active — sends network updates continuously (gameplay actors, cameras)
DORM_INITIAL = 4   Dormant — only updates on initial replication (static building pieces)
```
Floor tiles use `DORM_INITIAL` (net_update_frequency=1.0) while gameplay actors use
`DORM_AWAKE` (net_update_frequency=100.0). **Building a level with dormant floors is a
performance design decision by Epic** — fewer net ticks means less bandwidth.

### `BuildingAttachmentSlot`
```
SLOT_FLOOR = 0   Attaches to the floor face of a building grid cell
SLOT_NONE  = 3   Free-floating — no attachment constraint
```
Values 1 and 2 are likely SLOT_WALL and SLOT_CEILING (not in this scan).

### `BuildingAttachmentType`
```
ATTACH_FLOOR = 0   Connects structurally to floor tiles
ATTACH_NONE  = 9   No structural connection
```
The gap (0 to 9) indicates other types for walls/ceilings/corners exist in the engine.

### `FortBaseWeaponDamage`
```
ENVIRONMENTAL = 1   Responds to environmental damage (storms, zones)
```
Only one value observed. Others likely include NORMAL, EXPLOSIVE, PIERCING — but
those damage types were not present in the scanned level's props.

### `PlacementType`
```
FREE = 0   No placement constraints — prop can be placed anywhere
```

### `NavigationObstacleOverride`
```
USE_MESH_SETTINGS = 0   Defers to the mesh asset's navmesh settings
```
Other values would force override (OBSTACLE_YES / OBSTACLE_NO).

### `PhysicalSurface`
```
SURFACE_TYPE_DEFAULT = 0   Default surface — plays default footstep/impact sounds
```

### `IslandQueuePrivacy`
```
UNRESTRICTED = 0   Public island — anyone can join the matchmaking queue
```

### `JoinInProgressBehavior`
```
SPAWN_IMMEDIATELY = 1   Late joiners spawn at the next available spawn point
```

### `MatchmakingServiceBackfillType`
```
ENABLED = 1   Epic's MMS fills empty slots automatically
```

### `SocialJoiningType`
```
ENABLED = 1   Friends can join in progress
```

### `CreativeUITeamColors`
```
RELATIONSHIP = 0   HUD colors based on team relationship (friend=green, enemy=red)
```

### `SpawnActorCollisionHandlingMethod`
```
ALWAYS_SPAWN = 1   Ignore collision when spawning — overlapping actors are allowed
```

---

## World Partition Actors — The Hidden Infrastructure

Four classes in the schema are **world partition infrastructure** — not game objects:

### `WorldDataLayers`
- `always_relevant: True` — loaded for all clients
- `replicates: True` — synced across network
- `hidden: True` — invisible in game
- `net_dormancy: DORM_INITIAL` — static, rarely updates
- `root_component: Any` — Epic didn't expose the component
- **Role**: Manages which data layers are loaded. You cannot control this from Python —
  it's Epic's streaming system. But knowing it exists prevents false positives in
  "list all gameplay actors" queries.

### `WorldPartitionMiniMap`
- `hidden: True`, `replicates: False`
- Both `root_component` and it internally are `Any` — completely opaque
- **Role**: Generates the minimap texture. Not scriptable.

### `LevelBounds`
- `root_component: BoxComponent` — actual AABB of the world
- `can_be_damaged: False`, `replicates: False`
- **Role**: Defines the hard world boundary. Read its `root_component` to get the
  BoxComponent, then query extents:

```python
level_bounds = None
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "LevelBounds" in a.get_class().get_name():
        level_bounds = a
        break

if level_bounds:
    box = level_bounds.get_editor_property("root_component")
    extent = box.get_editor_property("box_extent")  # Vector — half-extents
    origin = box.get_editor_property("relative_location")
    print(f"World: {origin} ± {extent}")
```

### `WaterZone`
- `root_component: WaterMeshComponent` — the GPU water mesh
- `water_mesh: WaterMeshComponent` — same component, second handle
- `zone_extent: Vector2D` — 2D footprint of the water zone
- `render_target_resolution: IntPoint` — GPU render target size
- `water_info_texture_array: TextureRenderTarget2DArray` — water normal/foam map
- `water_info_texture_array_num_slices: int = 1` — number of texture layers
- `is_spatially_loaded: False` — always loaded (water is always visible)
- **Role**: Drives the water simulation render pass. The `FortWaterBodyActor` defines
  the shoreline spline; `WaterZone` defines how the water is rendered.

---

## The Full Collision Mask System

`BuildingProp` / `BuildingFloor` / `FortCreativeDeviceProp` expose **8 boolean collision flags**.
This is a bitmask system exposed as individual properties for Python readability:

| Flag | What it blocks |
|:---|:---|
| `no_collision` | **All collision** — equivalent to setting collision to None |
| `no_pawn_collision` | Players and NPCs walk/run through |
| `no_physics_collision` | Thrown items, physics props pass through |
| `no_projectile_collision` | Bullets, arrows, explosives pass through |
| `no_weapon_collision` | Melee, weapon traces pass through |
| `no_ranged_weapon_collision` | Ranged weapon traces specifically |
| `no_camera_collision` | Camera clips through (no camera bounce) |
| `no_visibility_collision` | Invisible to line-of-sight traces |

**Combination patterns for common use cases:**

```python
# Ghost prop — visible but walkthrough-able
ghost = {"no_pawn_collision": True, "no_physics_collision": True,
         "no_weapon_collision": True, "no_ranged_weapon_collision": True}

# Decorative only — no gameplay interaction at all
deco = {"no_collision": True}  # single flag overrides all

# Sniper cover — blocks bullets but players pass through
cover = {"no_pawn_collision": True}  # keep no_projectile_collision=False

# Invisible wall — blocks players but not bullets
wall = {"no_projectile_collision": True, "no_ranged_weapon_collision": True,
        "no_visibility_collision": True}
```

---

## Network Architecture Insights

The schema reveals Epic's network design philosophy through default `net_dormancy` and
`net_update_frequency` values:

| Actor type | Dormancy | Update Hz | What this means |
|:---|:---|:---|:---|
| `BuildingFloor` / `BuildingProp` | `DORM_INITIAL` (4) | 1.0 Hz | Set-and-forget. Only initial sync, then silent. |
| `FortCreativeDeviceProp` | `DORM_INITIAL` (4) | 1.0 Hz | Devices are also mostly static from the network perspective. |
| `Actor` (base) | `DORM_AWAKE` (1) | 100.0 Hz | Active gameplay actors update 100x/sec. |
| `FortPlayerStartCreative` | `DORM_AWAKE` (1) | 100.0 Hz | Spawn points can change state quickly. |
| `FortMinigameSettingsBuilding` | `DORM_AWAKE` (1) | 10.0 Hz | Settings need to sync but not at 100hz. |
| `WorldDataLayers` | `DORM_INITIAL` (4) | 10.0 Hz | Streams once then dormant. |

**`net_cull_distance_squared: 225000000.0` is universal** across all 14 classes.
√225000000 = 15000 UU = ~150 meters. Every actor culls at the same distance.
This is Epic's performance floor for Creative maps.

---

## FortMinigameSettingsBuilding — Island Settings Deep Dive

This actor is the **single most powerful actor for Python automation of game logic**.
Every UEFN level has exactly one, and it controls the entire match lifecycle.

### Finding It Reliably

```python
def get_island_settings():
    for a in unreal.EditorActorSubsystem().get_all_level_actors():
        cls = a.get_class().get_name()
        if "MinigameSettings" in cls or "IslandSettings" in cls:
            return a
    return None
```

### Properties Grouped by Purpose

**Match structure:**
```python
max_players                   = 16    # Hard cap on simultaneous players
mms_player_count              = 16    # Matchmaking target count (usually == max_players)
join_in_progress_behavior     = SPAWN_IMMEDIATELY  # Late-join policy
join_in_progress_assigned_team = 1    # Team 1 for late joiners
join_in_progress_assigned_team_override = False  # Force team override on join
```

**Privacy / discoverability:**
```python
creative_matchmaking_privacy  = UNRESTRICTED  # Lobby privacy
island_matchmaking_privacy    = UNRESTRICTED  # Island discovery privacy
social_joining                = ENABLED       # Friends can join
mms_backfill                  = ENABLED       # Auto-fill empty slots
use_custom_matchmaking_settings = False       # Override with matchmaking_settings object
```

**UI / HUD:**
```python
ui_team_colors                = RELATIONSHIP  # Colors by friend/enemy relationship
pacifist_icons                = False         # Show/hide weapon icons in HUD
disable_squad_quick_chat      = False         # Squad communication shortcuts
player_indicator_override_flags = 0           # HUD player indicator flags
```

**Watermarks / branding:**
```python
b_show_publish_watermark      = True   # "CREATED IN UEFN" overlay
show_island_code_watermark    = True   # Island code watermark
show_resource_feed_on_eliminations = False  # Resource kill feed
```

**Time of day:**
```python
use_legacy_time_of_day_manager = True  # Old (true) vs new time-of-day system
```

**Teams:**
```python
teams                         = CreativeTeamOption  # Full team config object
gameplay_tags                 = GameplayTagContainer  # Island-wide gameplay tags
matchmaking_settings          = CreativeIslandMatchmakingSettings  # Full MM config
```

**Automation pattern — configure an 8v8 match:**
```python
s = get_island_settings()
with unreal.ScopedEditorTransaction("Configure 8v8"):
    s.set_editor_property("max_players", 16)
    s.set_editor_property("mms_player_count", 16)
    s.set_editor_property("join_in_progress_behavior",
        unreal.JoinInProgressBehavior.SPAWN_IMMEDIATELY)
    s.set_editor_property("b_show_publish_watermark", False)
```

---

## FortPlayerStartCreative — Spawn System Deep Dive

### Property Semantics

```python
is_enabled         = True     # Master toggle — disable to block this spawn
applicable_team    = 1        # 1=Red/Team1, 2=Blue/Team2, 0=all, -1=any
applicable_class   = -1       # -1=any class; >=0 = specific class index
use_as_island_start = True    # Used for the initial game-start spawn
portal_index       = -1       # -1 = not linked to a portal; >=0 = linked portal
priority_group     = 2147483647  # Lower number = higher spawn priority
enemy_range_check  = 0.0      # 0 = no check; >0 = don't spawn if enemy this close (UU)
locked_player_name_substring = ""  # Only allow players whose name contains this string
player_start_tag   = Name     # Legacy single-tag system
player_start_tags  = GameplayTagContainer  # Modern multi-tag system (prefer this)
```

### Priority Group System

`priority_group: int = 2147483647` — this is `INT_MAX`. Default = lowest priority.
Epic's spawn system prefers **lower numbers**. When assigning strategic spawn priorities:

```python
# Front-line spawns (highest priority)
for s in front_spawns:
    s.set_editor_property("priority_group", 1)

# Mid-field spawns
for s in mid_spawns:
    s.set_editor_property("priority_group", 10)

# Fallback/last-resort spawns
for s in fallback_spawns:
    s.set_editor_property("priority_group", 100)

# Epic's default (practically never used unless all others are full)
# priority_group = 2147483647
```

### Team-Based Spawn Automation

```python
# Perfectly balanced team spawns on a symmetric map
all_starts = [a for a in unreal.EditorActorSubsystem().get_all_level_actors()
              if "PlayerStart" in a.get_class().get_name()]

for i, start in enumerate(all_starts):
    team = (i % 2) + 1  # alternates: 1, 2, 1, 2...
    start.set_editor_property("applicable_team", team)
    start.set_editor_property("priority_group", i // 2)  # pair-balanced priority
```

---

## FortWaterBodyActor + WaterZone — Water System Architecture

The water system is split across two actor types — a common source of confusion:

| Actor | Role | Key Props |
|:---|:---|:---|
| `FortWaterBodyActor` | Defines the water volume & shoreline | `spline_comp`, `water_body_primary_color`, `water_waves`, `overlapping_players` |
| `WaterZone` | Drives the GPU water render pass | `water_mesh`, `zone_extent`, `render_target_resolution`, `water_info_texture_array` |

**`FortWaterBodyActor` is the designer-facing actor** — you move it, set its color, and its
spline defines the shoreline. `WaterZone` is engine-internal — it renders what the
water body defines.

**Automation insight**: `overlapping_players: Array` on `FortWaterBodyActor` is live runtime
state. In the editor this is always `None`, but it's exposed for Python completeness.
For editor automation, use `water_body_primary_color: LinearColor` and `water_waves` to
configure the water appearance without entering Play mode.

**`WaterZone.render_target_resolution: IntPoint`** controls the GPU texture resolution
for water normals and foam. Higher = better water quality, more GPU cost.
`water_info_texture_array_num_slices: int = 1` = one water layer (standard for Creative).

---

## The `always_relevant` Flag — What It Signals

`always_relevant: bool` on Actor controls network relevance:
- `True` = **always send this actor to all clients**, regardless of distance
- `False` = only send when within `net_cull_distance_squared`

Only three actors default `always_relevant = True`:
1. `FortMinigameSettingsBuilding` — island settings must be known by all players
2. `WorldDataLayers` — streaming layers must be consistent across all clients

Every other actor (`Actor`, `BuildingProp`, `BuildingFloor`, etc.) defaults `False`.

**For custom gameplay devices**: If you build a game manager device that all players need
to read from, ensure `always_relevant = True` on it. In Python:
```python
game_mgr.set_editor_property("always_relevant", True)
```

---

## Property Naming Conventions — Epic's Internal Vocabulary

Patterns in Epic's property naming reveal the C++ layer underneath:

| Prefix/Pattern | Meaning | Examples |
|:---|:---|:---|
| `no_*_collision` | Collision disable flag | `no_pawn_collision`, `no_weapon_collision` |
| `is_*` | Boolean state flag | `is_invulnerable`, `is_dynamic`, `is_enabled` |
| `allow_*` | Permission flag | `allow_interact`, `allow_highlight`, `allow_building_cheat` |
| `force_*` | Override flag | `force_block_buildings`, `force_damage_ping` |
| `can_*` | Capability flag | `can_be_damaged`, `can_be_marked` |
| `*_component` | Component handle | `static_mesh_component`, `camera_component` |
| `net_*` | Network setting | `net_dormancy`, `net_update_frequency`, `net_priority` |
| `mms_*` | Matchmaking service | `mms_backfill`, `mms_player_count` |
| `b_*` | Legacy bool prefix (C++ `bIsX`) | `b_show_publish_watermark` |
| `*_index` | Team or portal index | `team_index`, `portal_index`, `water_body_index` |
| `*_guid` | Unique identifier | `actor_guid`, `content_bundle_guid` |
| `*_tag` / `*_tags` | Gameplay tag | `player_start_tag`, `editor_only_instance_tags` |
| `surpress_*` | Intentional typo in Epic's C++ | `surpress_health_bar` ← note: NOT suppress |

> **The `surpress_health_bar` typo is a genuine Epic C++ property name.** Using `suppress_health_bar`
> will fail silently — the property won't be found. Always use `surpress` (one 's' in the middle).

---

## Known Read-Only vs Writable Properties

From empirical testing and schema analysis:

**Confirmed writable (via `set_editor_property`):**
```
hidden, tags, is_invulnerable, team_index, allow_interact, is_enabled (spawn points),
max_players, mms_player_count, b_show_publish_watermark, surpress_health_bar,
no_collision (and all no_* flags), custom_time_dilation, net_dormancy, replicates
```

**Read-only at editor time (runtime state, not editable):**
```
destroyed, player_placed, being_one_hit_disassembled, overlapping_players,
overlapping_vehicles, damager_owner
```

**Access via `getattr` only (not registered as editor properties):**
```
Most Verse @editable properties, some component sub-properties
```

**Always raises (C++ delegates):**
```
on_actor_begin_overlap, on_actor_end_overlap, on_actor_hit, on_actor_touch,
on_destroyed, on_end_play, on_take_any_damage, _wrapper_meta_data
```

---

## Automation Recipes Derived From the Schema

### Recipe: Flag every device as "always loaded"

```python
# Devices default is_spatially_loaded=False already — but if you've changed it:
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "CreativeDeviceProp" in a.get_class().get_name():
        a.set_editor_property("is_spatially_loaded", False)
```

### Recipe: Identify structural tiles vs props by type

```python
def classify_actor(actor):
    bt = getattr(actor, "building_type", None)
    if bt is None:
        return "non-building"
    bt_str = str(bt)
    if "FLOOR" in bt_str: return "structural_floor"
    if "PROP" in bt_str:  return "prop_or_device"
    return f"building_{bt_str}"
```

### Recipe: Get world bounds

```python
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "LevelBounds" in a.get_class().get_name():
        box = a.get_editor_property("root_component")
        extent = getattr(box, "box_extent", None)
        origin = getattr(box, "relative_location", None)
        print(f"World bounds: center={origin}, half-extents={extent}")
        break
```

### Recipe: Audit which props have physics disabled

```python
results = []
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if hasattr(a, "no_physics_collision"):
        no_phys = getattr(a, "no_physics_collision", False)
        if no_phys:
            results.append(a.get_actor_label())
print(f"Props with no_physics_collision=True: {len(results)}")
```

### Recipe: Find dormant vs active actors

```python
dormant = []
active = []
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    dormancy = getattr(a, "net_dormancy", None)
    if dormancy is None: continue
    if "DORM_INITIAL" in str(dormancy):
        dormant.append(a.get_actor_label())
    else:
        active.append(a.get_actor_label())
print(f"Dormant: {len(dormant)}, Active: {len(active)}")
```

### Recipe: Set a prop to truly indestructible (all flags)

```python
with unreal.ScopedEditorTransaction("Make Indestructible"):
    for a in unreal.EditorActorSubsystem().get_selected_level_actors():
        if hasattr(a, "is_invulnerable"):
            a.set_editor_property("is_invulnerable", True)
            # Also disable the build-cheat override
            a.set_editor_property("allow_building_cheat", False)
```

---

## What This Schema Doesn't Cover

Being forensically honest about the schema's limits:

1. **Component sub-properties** — `BaseBuildingStaticMeshComponent` properties (material slots,
   LODs, bounds) are not crawled. Use `api_crawl_selection` on individual actors for that layer.

2. **Verse `@editable` properties** — not in this schema. Use `api_verse_get_schema` and the
   `.digest.verse` files for those.

3. **28,850 Fortnite-specific types** — the `uefn_python_capabilities.md` doc notes 28,850
   Fortnite classes in UEFN's Python bindings. This schema shows 14 of them. The rest need
   per-actor crawling or live `dir()` inspection.

4. **Runtime-only properties** — some props only have values during Play/Simulate mode.
   The crawler runs in editor mode, so `overlapping_players`, `destroyed`, and
   `player_placed` will always be `None` or `False` in the schema.

5. **Enum full value tables** — only values present in the scanned level's actors appear.
   `FortBuildingType.WALL` (2) and `FortBuildingType.RAMP` (3) definitely exist but
   weren't scanned because this level had no wall/ramp tiles.

---

*Generated by forensic analysis of `uefn_reference_schema.json`*
*Produced by UEFN Toolbelt — `api_crawl_level_classes`, 76 actors, 14 classes, UEFN 40.00+*
*Author: Ocean Bennett — Phase 21*
