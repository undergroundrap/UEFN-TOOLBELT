# UEFN Reference Schema — Deep Dive

> Forensic analysis of two real UEFN level scans:
> - **`uefn_reference_schema.json`** — original scan, 76 actors, 14 classes
> - **`uefn_tutorial_schema.json`** — Epic's tutorial level, 318 actors, 19 classes
>
> Run `api_crawl_level_classes` in any level to generate your own. Findings from both scans
> are combined here — the tutorial scan added 5 new classes, 3 new enum values, and corrected
> several assumptions from the first scan.

---

## Master Stats

| Metric | Scan 1 (own level) | Scan 2 (tutorial level) |
|:---|:---|:---|
| Actor instances scanned | 76 | 318 |
| Unique C++ classes | 14 | 19 |
| Total properties | 1,031 | ~1,400 (est.) |
| New enum values discovered | 15 types, partial values | +WALL, +ROOF, +STAIRS, +CONTAINER, +METAL, +WOOD, +DORM_DORMANT_ALL, +SLOT_WALL, +ATTACH_WALL, +FORCE_ENABLED |
| New device C++ classes | 0 | FortCreativeTeleporter, FortCreativeLockDevice |
| New building classes | BuildingFloor only | +Wall, +Roof, +Stairs, +Deco, +PropWall |
| `bool` properties | 368 | dominant type (36%+) |
| `str` properties | 1 | 1 (same — only `locked_player_name_substring`) |

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
WALL      = 0   BuildingWall — structural wall tile
FLOOR     = 1   BuildingFloor — structural floor tile
PROP      = 4   BuildingProp / FortCreativeDeviceProp — free prop or device
STAIRS    = 5   BuildingStairs — staircase tile
ROOF      = 6   BuildingRoof — roof tile
CONTAINER = 9   BuildingDeco — decorative attachment (attaches to walls)
```
Values confirmed across both scans. RAMP (likely 3) and others still not seen.

### `FortResourceType`
```
WOOD  = 0   Confirmed — BuildingFloor in tutorial level defaults to WOOD
STONE = 1   BuildingRoof, BuildingWall defaults
METAL = 2   Confirmed — seen in tutorial level
NONE  = 6   BuildingProp / FortCreativeDeviceProp — no material drops
```
The gap between METAL (2) and NONE (6) suggests values 3–5 are reserved (likely BRICK,
CONCRETE, or other materials not used in Creative). `resource_type` is **instance-specific** —
not a class default. The same `BuildingFloor` class can be WOOD, STONE, or METAL depending
on which material theme the level designer chose.

### `NetDormancy`
```
DORM_AWAKE        = 1   Active — sends updates continuously (gameplay actors, cameras, spawn points)
DORM_DORMANT_ALL  = 2   Fully dormant — NEVER sends unsolicited updates to any client
DORM_INITIAL      = 4   Dormant after first replication (static building tiles)
```
**This is one of the most architecturally significant findings from the tutorial scan.**
All Creative devices — `FortCreativeDeviceProp`, `FortCreativeTeleporter`, `FortCreativeLockDevice`,
`BuildingProp_SwitchDevice`, `FortPlaysetRoot` — use `DORM_DORMANT_ALL`.

This means **Creative devices never push network state changes through the C++ actor system**.
All device state propagation happens through Verse's own network layer (`listenable`, `signalable`,
channel events). The C++ actor is purely a shell — Verse owns the device's network lifecycle entirely.

Dormancy summary by actor type:
| Actor type | Dormancy | Implication |
|:---|:---|:---|
| Creative devices | `DORM_DORMANT_ALL` | Verse owns all state sync |
| Building tiles (Floor/Wall/Roof) | `DORM_INITIAL` | Static after first sync |
| Gameplay actors (spawn points, cameras) | `DORM_AWAKE` | Active state changes |

### `BuildingAttachmentSlot`
```
SLOT_FLOOR = 0   Attaches to the floor face
SLOT_WALL  = 1   Attaches to the wall face (confirmed — BuildingDeco, BuildingPropWall)
SLOT_NONE  = 3   Free-floating — no attachment constraint
```
Value 2 is likely SLOT_CEILING (not yet seen in any scan).

### `BuildingAttachmentType`
```
ATTACH_FLOOR = 0   Connects structurally to floor tiles
ATTACH_WALL  = 1   Connects to wall tiles (confirmed — BuildingDeco, BuildingPropWall)
ATTACH_NONE  = 9   No structural connection
```
The gap (1 to 9) indicates types for ceilings/corners/etc. exist but weren't seen in scans.

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
FORCE_ENABLED     = 1   Always blocks navmesh regardless of mesh settings
```
`FORCE_ENABLED` is used by `FortCreativeLockDevice` and `BuildingProp_SwitchDevice` — both
devices that players physically interact with. Epic hard-codes navmesh blocking on these so
NPCs never path through a locked door or interactive switch.

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

5. **Enum full value tables** — only values present in scanned levels appear. RAMP is still
   unconfirmed across both scans. Running the crawl on a Fortnite BR-style build level with
   ramps would fill this gap.

---

## Tutorial Level Scan — New Class Findings

### `FortCreativeTeleporter` — Teleporter Device

The only Creative device with **C++-level teleporter group logic** exposed to Python.

| Property | Type | Value | Notes |
|:---|:---|:---|:---|
| `knob_teleporter_group` | `FortCreativeTeleporterGroup` | `GROUP_NONE` (26) | Which group this teleporter belongs to |
| `knob_target_teleporter_group` | `FortCreativeTeleporterGroup` | `GROUP_F` (5) | Which group it teleports players to |
| `teleport_to_when_received` | `FortGameplayReceiverMessageComponent` | `None` | Channel-based trigger (the "Receive Channel" knob) |
| `teleporter_ability` | `BlueprintGeneratedClass` | `None` | Blueprint class run on teleport — Epic override hook |

**`FortCreativeTeleporterGroup` enum — full table (confirmed from `unreal.pyi`):**
```
GROUP_A    = 0     GROUP_J    = 9     GROUP_S    = 18
GROUP_B    = 1     GROUP_K    = 10    GROUP_T    = 19
GROUP_C    = 2     GROUP_L    = 11    GROUP_U    = 20
GROUP_D    = 3     GROUP_M    = 12    GROUP_V    = 21
GROUP_E    = 4     GROUP_N    = 13    GROUP_W    = 22
GROUP_F    = 5     GROUP_O    = 14    GROUP_X    = 23
GROUP_G    = 6     GROUP_P    = 15    GROUP_Y    = 24
GROUP_H    = 7     GROUP_Q    = 16    GROUP_Z    = 25
GROUP_I    = 8     GROUP_R    = 17    GROUP_NONE = 26
```
26 active groups (A–Z) + GROUP_NONE. This enables truly large-scale teleporter meshes —
a single level could have 26 independent teleporter networks, each with many-to-many routing.
The many-to-many group design: a teleporter with `knob_teleporter_group=GROUP_A` will
receive any player sent by a teleporter whose `knob_target_teleporter_group=GROUP_A`.
Multiple teleporters can share the same group — creating random destination pools.

**`teleport_to_when_received`** proves the channel system is wired directly into the C++
teleporter class. When a channel event fires, this component handles the trigger — the
same component type (`FortGameplayReceiverMessageComponent`) used in the broader messaging
system.

**Automation — configure a teleporter network:**
```python
# Find all teleporters and assign groups
teleporters = [a for a in unreal.EditorActorSubsystem().get_all_level_actors()
               if "Teleporter" in a.get_class().get_name()]

# Pair: first half sends to group A, second half receives group A
mid = len(teleporters) // 2
for i, t in enumerate(teleporters[:mid]):
    # GROUP_A = 0
    t.set_editor_property("knob_target_teleporter_group", 0)
for t in teleporters[mid:]:
    t.set_editor_property("knob_teleporter_group", 0)
```

**Teleporter default differences vs `FortCreativeDeviceProp`:**
- `net_update_frequency: 5.0` (vs 1.0) — teleporters update 5x more often
- `allow_hostile_blueprint_interaction: True` — NPCs can trigger teleporters
- `allow_custom_material: False` — skin can't be overridden

---

### `FortCreativeLockDevice` — Lock Device

C++ properties beyond `FortCreativeDeviceProp` (confirmed from `unreal.pyi`):

| Property | Type | Notes |
|:---|:---|:---|
| `cached_local_controller` | `FortPlayerController` | Runtime reference to the player who owns the lock |
| `on_local_pawn_inventory_changed` | `LocalPawnInventoryChanged` | **MulticastDelegate** — bind Python callbacks to inventory events |

**`on_local_pawn_inventory_changed` is a MulticastDelegate** — meaning it has `add_callable()`:
```python
lock_device = ...  # find your lock device actor
def on_inventory_change(*args):
    print(f"Lock inventory changed: {args}")

delegate = getattr(lock_device, "on_local_pawn_inventory_changed", None)
if delegate is not None:
    delegate.add_callable(on_inventory_change)
```
This is one of the few Creative devices that exposes a Python-bindable event delegate at the C++ level.

**Key default differences vs generic device:**
- `navigation_obstacle_override: FORCE_ENABLED` — always blocks navmesh (NPCs can't path through locked doors)
- `block_navigation_links: True` — also blocks nav links specifically
- `enable_auto_lod_generation: True` — gets LODs unlike generic devices

---

### `BuildingDeco` — Decorative Attachment

Decorations are structurally distinct from props — they attach to **walls** (`ATTACH_WALL`),
not floors, and are typed as `CONTAINER` (9), not `PROP` (4).

**Unique property (only class with this):**
```
cast_shadow: bool = False   — decorations default to no shadow (performance optimization)
```

**Key characteristics vs `BuildingProp`:**
- `building_type: CONTAINER` (9) — not a free prop, it's a container/attachment
- `building_attachment_type: ATTACH_WALL` — snaps to wall faces
- `building_attachment_slot: SLOT_NONE` — free within the wall attachment
- `no_camera_collision: True` — camera clips through decorations
- `destroy_on_player_building_placement: True` — deco is removed when a player builds over it
- `cast_shadow: False` — no shadow by default

**Automation — enable shadows on all deco:**
```python
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "BuildingDeco" in a.get_class().get_name():
        a.set_editor_property("cast_shadow", True)
```

---

### The Full Building Family (confirmed)

All building tile types now confirmed with their `FortBuildingType` values and
distinguishing defaults:

| Class | Type Int | Attachment | Snap Grid | Resource | Nav Modifier |
|:---|:---|:---|:---|:---|:---|
| `BuildingWall` | WALL=0 | ATTACH_NONE / SLOT_WALL | 512 | STONE | `False` |
| `BuildingFloor` | FLOOR=1 | ATTACH_FLOOR / SLOT_FLOOR | 512 / 384 | WOOD | `True` |
| `BuildingProp` | PROP=4 | ATTACH_FLOOR / SLOT_NONE | 0 | NONE | `False` |
| `BuildingStairs` | STAIRS=5 | ATTACH_NONE / SLOT_NONE | 512 | STONE | `False` |
| `BuildingRoof` | ROOF=6 | ATTACH_NONE / SLOT_NONE | 512 | STONE | `False` |
| `BuildingDeco` | CONTAINER=9 | ATTACH_WALL / SLOT_NONE | 0 | NONE | `False` |
| `BuildingPropWall` | PROP=4 | ATTACH_WALL / SLOT_WALL | 0 | NONE | `False` |
| `FortCreativeDeviceProp` | PROP=4 | ATTACH_NONE / SLOT_NONE | 0 | NONE | `False` |

**`BuildingStairs` unique quirk**: `death_particle_socket_name = "Destruction"` — the only
building type with a named VFX socket. When stairs are destroyed, the engine looks for a
socket named `"Destruction"` on the mesh to emit the death particle. Other tiles use a
default destroy location.

---

### `BlockingVolume` — Invisible Blocker

One extra property beyond `Actor`:
```
brush_component: BrushComponent = None   — the BSP brush defining the volume shape
```
`BlockingVolume` is a BSP-based invisible collision volume. `can_be_damaged: False`,
`replicates: False`. Used for out-of-bounds walls, invisible floors, and kill zones.

**Automation — find all blocking volumes:**
```python
blockers = [a for a in unreal.EditorActorSubsystem().get_all_level_actors()
            if "BlockingVolume" in a.get_class().get_name()]
print(f"Found {len(blockers)} blocking volumes")
```

---

### `FortPlaysetRoot` — Playset Container

Zero unique properties beyond `Actor`. Its role is organizational — it's the root actor
of a "Playset" (a pre-built Creative content bundle). All props in the playset are
children of this root.

Key characteristics:
- `net_dormancy: DORM_DORMANT_ALL` — playset container never pushes state
- `replicates: False` — pure editor organizational actor
- No physical presence (root_component = SceneComponent)

---

---

## PYI Stub Analysis — Device C++ Properties

> Source: `unreal.pyi` generated by `api_export_full` — 37,227 classes, 367 MB.
> This section documents findings from mining device-specific classes directly from
> the compiled type stubs, going beyond what any level scan can reveal.

---

### `FortCreativeTimerDevice` — Runtime Client State

The timer device exposes **6 client-replicated properties** readable from Python at runtime.
These are prefixed `client_` — a convention in Epic's C++ indicating client-side replicated state:

| Property | Type | Access | Notes |
|:---|:---|:---|:---|
| `client_current_state` | `TimerDeviceState` | Read-Only | Current operational state of the timer |
| `client_current_time` | `int32` | Read-Only | Current timer value in seconds |
| `client_current_secondary_text` | `str` | Read-Only | Secondary display text (e.g. round label) |
| `client_show_on_hud` | `bool` | Read-Only | Whether timer is currently shown on HUD |
| `client_timer_text_style` | `enum` | Read-Only | Display style of the timer text |
| `server_display_update_rate` | `float` | Read-Write | How often server pushes display updates |

**`TimerDeviceState` enum:**
```
ACTIVATED  — Timer is running
COMPLETED  — Timer reached zero / end condition
DISABLED   — Timer is off / not started
ENABLED    — Timer is active but not yet started (armed)
PAUSED     — Timer was running, now paused
```

**Reading live timer state from Python:**
```python
timer = None
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "Timer" in a.get_class().get_name() and "Creative" in a.get_class().get_name():
        timer = a
        break

if timer:
    state = getattr(timer, "client_current_state", None)
    time_val = getattr(timer, "client_current_time", None)
    on_hud = getattr(timer, "client_show_on_hud", None)
    print(f"Timer: state={state}, time={time_val}s, hud={on_hud}")
```

> **Note**: `client_*` properties are runtime state — they will be `None` or default values
> in editor mode. They are most useful when polled during Play/Simulate mode or via
> `execute_python` through the MCP bridge while a test session is running.

---

### `CreativeAudioMixerDevice` — Python Volume Control

The only Creative audio device with a directly writable `fader_value`:

| Property | Type | Access | Notes |
|:---|:---|:---|:---|
| `fader_value` | `float` | **Read-Write** | Volume fader level (0.0–1.0) |
| `activate_in_edit_mode` | `bool` | Read-Write | Play audio during editor sessions |
| `activate_on_game_start` | `bool` | Read-Write | Auto-activate when game begins |
| `bus` | `SoundControlBus` | Read-Only | Connected audio control bus |
| `can_be_heard_by` | `enum` | Read-Write | Team filter for who hears this audio |
| `mix` | `SoundControlBusMix` | Read-Only | The bus mix applied |

**`fader_value` is writable** — this means Python can control volume at runtime:
```python
# Find audio mixer devices and adjust volume
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    cls = a.get_class().get_name()
    if "AudioMixer" in cls or "Audio" in cls:
        # Set to 80% volume
        a.set_editor_property("fader_value", 0.8)
        # Enable playback during editor previewing
        a.set_editor_property("activate_in_edit_mode", True)
```

---

### `DelMarActorMover` — Racing / Spline Movement System

Epic's racing island plugin (`DelMar` = their internal racing project codename). This actor
moves another actor along a spline with configurable looping behavior.

| Property | Type | Access | Notes |
|:---|:---|:---|:---|
| `managed_actor` | `Actor` | **Read-Only** | The actor being moved |
| `movement_spline` | `SplineComponent` | **Read-Only** | The spline path to follow |
| `movement_type` | `DelMarSplineMovementType` | **Read-Write** | Loop behavior |

**`DelMarSplineMovementType` enum:**
```
ONE_SHOT   — Travel once from start to end, stop
PING_PONG  — Travel A→B→A→B indefinitely (reverses at each end)
REPEAT     — Travel A→B, teleport back to A, repeat
```

**Reading a mover's configuration:**
```python
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "ActorMover" in a.get_class().get_name():
        mtype = getattr(a, "movement_type", None)
        spline = getattr(a, "movement_spline", None)
        target = getattr(a, "managed_actor", None)
        print(f"Mover: type={mtype}, target={target}, spline={spline}")
```

**Changing movement type via Python:**
```python
# Find a mover and set it to PING_PONG
mover = ...
mover.set_editor_property("movement_type",
    unreal.DelMarSplineMovementType.PING_PONG)
```

> The `DelMar` prefix reveals this came from an internal Epic racing game project.
> These classes are in public UEFN bindings, meaning Epic ships this for island creators
> to build racing/moving platform experiences.

---

### `FortCreativeSplineControlPoint` — Spline Architecture

Each spline in UEFN has associated `FortCreativeSplineControlPoint` actors that store
per-point metadata beyond the raw spline coordinates:

| Property | Type | Notes |
|:---|:---|:---|
| `spline_index` | `int` | Index of this point in the owning spline |
| `owning_spline_prop` | `Actor` | Back-reference to the spline actor that owns this point |
| `initialized_from_owning_spline_prop` | `bool` | Whether position was initialized from the spline actor |
| `copied_from` | `Actor` | If this point was copied, original source actor |
| `copied_from_cut` | `bool` | Whether the copy was a cut (true) or duplicate (false) |

**These actors are created automatically** when you place spline actors in UEFN. They're usually
invisible and managed by the editor, but Python can read them to get metadata about each point's
lineage and index without parsing the spline component directly:

```python
# Get all spline control points for a specific spline
target_spline_label = "My Patrol Path"
control_points = []

for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "SplineControlPoint" in a.get_class().get_name():
        owner = getattr(a, "owning_spline_prop", None)
        if owner and target_spline_label in owner.get_actor_label():
            idx = getattr(a, "spline_index", -1)
            control_points.append((idx, a))

control_points.sort(key=lambda x: x[0])
print(f"Found {len(control_points)} control points")
```

---

### `LinkCodeMutatorDevice` — Island Link Code System

A low-profile device that applies rule mutators when players enter via link code:

| Property | Type | Notes |
|:---|:---|:---|
| `mutators_to_apply` | `Array[str]` | List of mutator name strings to activate |

**This is the only device with an `Array[str]` property directly writable from Python.**
The mutators correspond to named game rule overrides (time limits, damage modifiers, etc.)
that activate when the island is accessed via a specific link code.

```python
# Read current mutators on a link code device
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "LinkCode" in a.get_class().get_name() or "Mutator" in a.get_class().get_name():
        mutators = getattr(a, "mutators_to_apply", [])
        print(f"Active mutators: {list(mutators)}")
```

---

### `CreativeBlueprintLibrary` — High-Value Utility Methods

The most powerful static library accessible from Python in UEFN. All methods are
callable via `unreal.CreativeBlueprintLibrary.method_name()`:

| Method | Returns | What It Does |
|:---|:---|:---|
| `get_creative_island_code()` | `str` | Returns the published island code (e.g. "1234-5678-9012") |
| `get_gravity_z()` | `float` | Returns current gravity (default: -980.0 cm/s²) |
| `is_actor_locked(actor)` | `bool` | True if actor is locked via Lock Device |
| `get_minigame_stats_comp(actor)` | `MinigameStatsComponent` | Returns the stats component for scoring actors |
| `get_creative_island_matchmaking_max_players()` | `int` | Max players allowed for matchmaking |
| `get_all_creative_island_actors()` | `Array[Actor]` | All actors on the creative island |
| `try_get_creative_island_code(out_code)` | `bool` | Non-raising version of `get_creative_island_code` |

**Key usage patterns:**
```python
lib = unreal.CreativeBlueprintLibrary

# Get published island code
code = lib.get_creative_island_code()
print(f"Island: {code}")

# Check gravity (useful for zero-G map detection)
g = lib.get_gravity_z()
print(f"Gravity: {g} cm/s²")  # -980.0 = normal, 0 = zero-G

# Check if an actor is currently locked
actor = ...
if lib.is_actor_locked(actor):
    print("Actor is locked by a Lock Device")

# Get max players for matchmaking
max_p = lib.get_creative_island_matchmaking_max_players()
print(f"Matchmaking allows up to {max_p} players")
```

> `CreativeBlueprintLibrary` is a **static library** — no instance needed. These are
> Blueprint Function Library methods bridged to Python. They are the cleanest API surface
> Epic provides for reading island-level metadata from Python.

---

### `CreativeBudget` — Resource Budget Tracking

Tracks the Creative island resource budget (actors, memory, polygons):

| Method | Returns | Notes |
|:---|:---|:---|
| `get_actor_count()` | `int` | Current actor count toward budget |
| `get_actor_budget()` | `int` | Max allowed actors |
| `get_memory_used_kb()` | `float` | Memory used in KB |
| `get_memory_budget_kb()` | `float` | Memory budget in KB |
| `is_over_budget()` | `bool` | True if any budget exceeded |

```python
budget = unreal.CreativeBudget.get_default_object()
# Or via CreativeBlueprintLibrary if CreativeBudget is not directly accessible
actors_used = budget.get_actor_count() if budget else None
```

> **Budget awareness** is critical for published islands. Epic rejects islands that
> exceed budget limits. Use this API to build automated budget-checking tools before publishing.

---

### `CreativeRegisteredPlayerGroups` — Persistent Player Group Enum

```
GROUP_0  = 0    GROUP_4  = 4
GROUP_1  = 1    GROUP_5  = 5
GROUP_2  = 2    GROUP_6  = 6
GROUP_3  = 3    GROUP_7  = 7
```
8 persistent player groups (0–7). These map to the "Registered Player" system where players
can be assigned to named groups for custom game logic (e.g., "VIPs", "spectators", "team captains").
Accessible via device knobs that reference player group assignments.

---

### Class Inheritance Map — Confirmed from PYI

The pyi stubs confirm the full inheritance chain for Creative device classes:

```
UObject
  └── Actor
        └── FortActor
              └── AFortBuilding
                    ├── BuildingProp
                    │     ├── FortCreativeDeviceProp
                    │     │     ├── FortCreativeTeleporter
                    │     │     ├── FortCreativeTimerDevice
                    │     │     ├── FortCreativeLockDevice
                    │     │     ├── CreativeAudioMixerDevice
                    │     │     ├── LinkCodeMutatorDevice
                    │     │     └── BuildingProp_SwitchDevice
                    │     └── BuildingPropWall
                    ├── BuildingFloor
                    ├── BuildingWall
                    ├── BuildingStairs
                    ├── BuildingRoof
                    └── BuildingDeco

DelMarActorMover
  └── Actor (separate tree — racing plugin)

FortCreativeSplineControlPoint
  └── Actor (separate tree — spline metadata)
```

**Why `FortCreativeDeviceProp` inherits `BuildingProp`**: Every Creative device IS a prop
from the game engine's perspective — it has a mesh, collision, building attachment system,
and resource type. Epic uses this inheritance so devices get all building system benefits
(destruction system, collision flags, team coloring, snap grid) for free.

---

*Generated from two UEFN level scans: `uefn_reference_schema.json` (14 classes) and `uefn_tutorial_schema.json` (19 classes)*
*PYI section: `unreal.pyi` from `api_export_full` — 37,227 classes, UEFN 40.00+*
*UEFN 40.00+ — Toolbelt `api_crawl_level_classes`*
*Author: Ocean Bennett — Phase 21*
