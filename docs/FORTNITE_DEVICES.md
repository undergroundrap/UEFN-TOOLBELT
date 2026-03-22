# Fortnite Creative Devices — Automation Reference

> **What this document covers**: The common Fortnite Creative devices (trigger volumes,
> spawn pads, team settings, etc.) that every UEFN level uses. These appear as
> `FortCreativeDeviceProp` to the Python layer — their real API is in Verse.
>
> **How to use this document**:
> 1. Find your device type below
> 2. Use `tb.run("verse_select_by_class", class_name="...")` to select it in the viewport
> 3. Use `tb.run("verse_bulk_set_property", property_name="...", value=...)` to configure it
> 4. Use `tb.run("api_verse_get_schema", class_name="...")` for the live schema

---

## The Python ↔ Verse Bridge Problem

When you place a **Trigger Device**, **Team Settings Device**, or any other Creative device,
UEFN's Python API sees it as `FortCreativeDeviceProp` — a generic shell.

```python
# What you want:
actor.get_editor_property("is_enabled")   # ← works for FortPlayerStartCreative
# What you get on devices:
# Exception: Failed to find editor property 'is_enabled' on FortCreativeDeviceProp
```

**The solution** — two access paths:

```python
# Path 1: getattr() bypasses the editor property system
val = getattr(actor, "is_enabled", None)

# Path 2: Use Toolbelt tools that handle this automatically
tb.run("verse_bulk_set_property", property_name="is_enabled", value=True)
tb.run("verse_export_report")   # dumps all properties from all devices to JSON
```

---

## Device Classes & Their Verse Names

| Device Name (in editor) | Verse class (approx.) | What it does |
|:---|:---|:---|
| Trigger Device | `trigger_device` | Fires events when players enter/exit |
| Item Spawner | `item_spawner_device` | Spawns items/weapons at location |
| Team Settings | `team_settings_and_inventory_device` | Per-team HP, shield, loadout |
| Player Spawner | `player_spawner_device` | Custom spawn logic |
| Capture Area | `capture_area_device` | Zone control scoring |
| Countdown Timer | `countdown_timer_device` | Countdown clock |
| HUD Message | `hud_message_device` | On-screen text messages |
| Barrier Device | `barrier_device` | Force field / one-way wall |
| Teleporter | `teleporter_device` | Point-to-point teleport |
| Class Designer | `class_designer_device` | Player class / loadout |
| Score Manager | `score_manager_device` | Track and display score |
| Round Settings | `round_settings_device` | Multi-round game logic |
| VFX Spawner | `vfx_spawner_device` | Play particle effects |
| Audio Player | `audio_player_device` | Trigger sounds |
| Guard Spawner | `guard_spawner_device` | NPC guard wave spawning |
| Creature Spawner | `creature_spawner_device` | NPC creature waves |
| Billboard | `billboard_device` | In-world image display |
| Spawn Pad | `spawn_pad_device` | Visual spawn indicator |

> **Note**: Verse class names are normalized from actor labels by the "Named Auto-Link" system.
> If your actor label is "My Trigger", the resolved class name is `my_trigger`.

---

## Common Device Properties via Python

These properties exist on nearly every Fortnite Creative device and are accessible
via `getattr()` or `tb.run("verse_bulk_set_property", ...)`:

| Property | Type | What it controls |
|:---|:---|:---|
| `is_enabled` | `bool` | Device active/inactive |
| `visible_in_game` | `bool` | Device mesh visibility during gameplay |
| `visible_during_phase` | enum | When device is visible (always/pregame/game) |
| `team` | `int` | Which team this device belongs to (0=all) |
| `channel` | `int` | Event channel for device-to-device wiring |

---

## Trigger Device

The most common device for game logic. Fires events on player enter/exit.

```verse
# Typical Verse class structure (what verse_gen_game_skeleton outputs):
trigger_device := class<creative_device>:
    # @editable properties
    on_player_enters_event : listenable(player) = external {}
    on_player_exits_event : listenable(player) = external {}
    is_enabled : logic = true
    team : int = 0

    OnBegin<override>()<suspends>:void=
        spawn{ ListenForTrigger() }

    ListenForTrigger()<suspends>:void=
        Player := on_player_enters_event.Await()
        # do something with Player
```

**Python automation:**
```python
# Find all trigger devices in level
triggers = tb.run("verse_select_by_class", class_name="trigger_device")

# Enable only triggers tagged as "active_zone"
for actor in unreal.EditorActorSubsystem().get_selected_level_actors():
    label = actor.get_actor_label().lower()
    if "active" in label:
        actor.__dict__  # getattr access
```

---

## Team Settings Device

Controls per-team configuration: max HP, starting shield, weapons, HUD color.

**Key `@editable` properties** (accessible via `getattr`):
- `team_index` — which team (1=Red, 2=Blue, 0=all)
- `max_health` — player max health points
- `starting_shield` — starting shield value
- `spawn_inventory` — weapon loadout configuration
- `allow_team_damage` — friendly fire toggle
- `respawn_enabled` — team respawn toggle
- `respawn_delay` — seconds before respawn

**Python automation:**
```python
# Set all team devices to 200 HP via Toolbelt
tb.run("verse_select_by_class", class_name="team_settings_and_inventory_device")
tb.run("verse_bulk_set_property", property_name="max_health", value=200.0)
```

---

## Score Manager Device

Tracks score and drives HUD scoreboard.

**Key properties:**
- `score_increment` — points per event
- `max_score` — win condition score
- `auto_win` — trigger win when max_score reached
- `channel` — which event channel increments score
- `team` — which team this tracks

---

## Guard / Creature Spawner Device

Spawns AI enemies in waves.

**Key properties:**
- `enabled_at_game_start` — auto-spawn on game start
- `max_guards` / `max_creatures` — concurrent enemy cap
- `spawn_delay` — seconds between spawns
- `alert_range` — aggro detection radius
- `respawn_guards` / `respawn_creatures` — respawn after death
- `patrol_path` — linked spline for patrol route

**Automation pattern — generate patrol:**
```python
# 1. Select a spline actor in the viewport
# 2. Export spline as Verse patrol code
tb.run("spline_to_verse_patrol")
# → Outputs full Verse patrol AI skeleton with the spline points embedded
```

---

## Teleporter Device

Point-to-point instant travel.

**Key properties:**
- `is_enabled` — active/inactive
- `target_teleporter` — destination device reference
- `teleport_channel` — channel-based triggering
- `activation_method` — `PLAYER_ENTER` or `CHANNEL_ACTIVATED`
- `team` — which team can use it

**C++ group system (exposed to Python as `FortCreativeTeleporter`):**

| Property | Type | What it controls |
|:---|:---|:---|
| `knob_teleporter_group` | `FortCreativeTeleporterGroup` | Which group this teleporter *belongs to* (receives) |
| `knob_target_teleporter_group` | `FortCreativeTeleporterGroup` | Which group this teleporter *sends to* |
| `teleport_to_when_received` | `FortGameplayReceiverMessageComponent` | Channel-message trigger (the "Receive Channel" knob in C++) |

**`FortCreativeTeleporterGroup` — full 27-value enum:**
```
GROUP_A=0  GROUP_B=1  GROUP_C=2  GROUP_D=3  GROUP_E=4  GROUP_F=5
GROUP_G=6  GROUP_H=7  GROUP_I=8  GROUP_J=9  GROUP_K=10 GROUP_L=11
GROUP_M=12 GROUP_N=13 GROUP_O=14 GROUP_P=15 GROUP_Q=16 GROUP_R=17
GROUP_S=18 GROUP_T=19 GROUP_U=20 GROUP_V=21 GROUP_W=22 GROUP_X=23
GROUP_Y=24 GROUP_Z=25 GROUP_NONE=26
```

26 active groups (A–Z). A teleporter with `knob_teleporter_group=GROUP_A` receives any
player sent by a teleporter with `knob_target_teleporter_group=GROUP_A`. Multiple
teleporters can share a group — creating **random destination pools**.

**Configuring a teleporter network via Python:**
```python
teleporters = [a for a in unreal.EditorActorSubsystem().get_all_level_actors()
               if "Teleporter" in a.get_class().get_name()]

# First half sends to GROUP_A, second half receives GROUP_A
mid = len(teleporters) // 2
for t in teleporters[:mid]:
    t.set_editor_property("knob_target_teleporter_group", 0)  # GROUP_A
for t in teleporters[mid:]:
    t.set_editor_property("knob_teleporter_group", 0)  # GROUP_A
```

---

## Audio Mixer Device (`CreativeAudioMixerDevice`)

The only audio device with a Python-writable volume fader. This is not the same as the
basic Audio Player — the Audio Mixer controls overall sound mix via a bus system.

**Key C++ properties (from `unreal.pyi`):**

| Property | Type | Access | What it controls |
|:---|:---|:---|:---|
| `fader_value` | `float` | **Read-Write** | Volume level (0.0 = silent, 1.0 = full) |
| `activate_in_edit_mode` | `bool` | Read-Write | Play audio during editor preview |
| `activate_on_game_start` | `bool` | Read-Write | Auto-activate on game begin |
| `can_be_heard_by` | `enum` | Read-Write | Team filter (all teams, specific team) |
| `bus` | `SoundControlBus` | Read-Only | Connected audio control bus |
| `mix` | `SoundControlBusMix` | Read-Only | The bus mix applied |

```python
# Set all audio mixers to 80% volume
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    cls = a.get_class().get_name()
    if "AudioMixer" in cls:
        a.set_editor_property("fader_value", 0.8)
        a.set_editor_property("activate_on_game_start", True)
```

---

## Item Spawner Device

Spawns weapons, consumables, and trap items.

**Key properties:**
- `grant_immediately` — spawn on game start vs trigger
- `respawn_time` — seconds until item reappears after pickup
- `spawn_limit` — max items spawned per game
- `item_definition` — which item to spawn (set in editor)
- `team` — team restriction

---

## Capture Area Device

Zone control — teams score by holding the zone.

**Key properties:**
- `capture_time` — seconds to capture
- `score_per_second` — passive score rate while held
- `team` — which team starts controlling it
- `requires_players_count` — min players to hold
- `reset_on_game_start` — reset control state each round

---

## Countdown Timer Device

**Key properties:**
- `start_time_seconds` — timer start value
- `count_direction` — `UP` or `DOWN`
- `auto_start` — start on game begin
- `channel` — channel triggered when timer expires

**Runtime client state (readable from Python during Play mode):**

| Property | Type | What it shows |
|:---|:---|:---|
| `client_current_state` | `TimerDeviceState` | Current operational state |
| `client_current_time` | `int32` | Current timer value in seconds |
| `client_show_on_hud` | `bool` | Whether timer is on HUD now |
| `client_current_secondary_text` | `str` | Secondary display label |
| `server_display_update_rate` | `float` | How often display is pushed (writable) |

**`TimerDeviceState` values:** `ACTIVATED`, `COMPLETED`, `DISABLED`, `ENABLED`, `PAUSED`

```python
# Read live timer state (use during Simulate/Play mode)
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if "Timer" in a.get_class().get_name():
        state = getattr(a, "client_current_state", None)
        time_val = getattr(a, "client_current_time", None)
        print(f"Timer: {state} @ {time_val}s")
```

---

## Device Wiring — The Channel System

Creative devices communicate via **channels** (integers 1–255). A device can:
- **Transmit** on a channel when an event occurs (e.g., timer expires → channel 3)
- **Receive** on a channel to trigger an action (e.g., channel 3 → spawn enemies)

**From Python, you can read/set channels:**
```python
# Get current channel for an actor
channel = getattr(actor, "channel", None)

# Set channel for all selected devices
tb.run("verse_bulk_set_property", property_name="channel", value=5)
```

**Standard channel conventions** (common in competitive maps):
- Channel 1 — Game start
- Channel 2 — Round start / round end
- Channel 3 — Team 1 score event
- Channel 4 — Team 2 score event
- Channel 10+ — Map-specific logic

---

## Verse Code Generation — Quick Reference

The Toolbelt can generate Verse stubs for any device pattern:

```python
# Full game manager skeleton (OnBegin, Round logic, Scoring)
tb.run("verse_gen_game_skeleton", device_name="game_manager")

# @editable declarations from currently selected devices
tb.run("verse_gen_device_declarations")

# Elimination event handler
tb.run("verse_gen_elimination_handler", device_name="elim_handler")

# Zone-based scoring tracker
tb.run("verse_gen_scoring_tracker", device_name="zone_scorer")

# Prop spawn trigger
tb.run("verse_gen_prop_spawner", device_name="prop_trigger")

# Patrol AI from selected spline
tb.run("spline_to_verse_patrol")

# Zone boundary helper
tb.run("spline_to_verse_zone_boundary")
```

---

## Export → Inspect → Automate Workflow

```python
# Step 1: Export all device properties to JSON for inspection
tb.run("verse_export_report", output_path="Saved/UEFN_Toolbelt/device_audit.json")

# Step 2: Read the JSON to understand your level's device config
# (open in VS Code — it's a structured map of all devices + their properties)

# Step 3: Use verse_select_by_class to target specific device types
tb.run("verse_select_by_class", class_name="score_manager_device")

# Step 4: Bulk configure them
tb.run("verse_bulk_set_property", property_name="max_score", value=25)

# Step 5: Save the level
tb.run("save_current_level")
```

---

## `CreativeBlueprintLibrary` — Island-Level Python API

A static library accessible as `unreal.CreativeBlueprintLibrary`. No instance needed.
These are Epic's officially bridged Blueprint Function Library methods for Creative automation.

| Method | Returns | What it does |
|:---|:---|:---|
| `get_creative_island_code()` | `str` | Published island code (e.g. `"1234-5678-9012"`) |
| `get_gravity_z()` | `float` | Current gravity in cm/s² (default: -980.0) |
| `is_actor_locked(actor)` | `bool` | True if locked via Lock Device |
| `get_minigame_stats_comp(actor)` | `MinigameStatsComponent` | Returns scoring stats component |
| `get_creative_island_matchmaking_max_players()` | `int` | Matchmaking player cap |
| `get_all_creative_island_actors()` | `Array[Actor]` | All actors on island |
| `try_get_creative_island_code(out_code)` | `bool` | Non-raising code check |

```python
lib = unreal.CreativeBlueprintLibrary

# Read island metadata
code = lib.get_creative_island_code()
gravity = lib.get_gravity_z()
max_players = lib.get_creative_island_matchmaking_max_players()

print(f"Island: {code} | Gravity: {gravity} cm/s² | Max players: {max_players}")

# Check if specific actor is locked
for a in unreal.EditorActorSubsystem().get_selected_level_actors():
    locked = lib.is_actor_locked(a)
    print(f"{a.get_actor_label()}: locked={locked}")
```

> **Zero-gravity detection**: `get_gravity_z() == 0.0` reliably identifies zero-G maps.
> The default is -980.0 (Earth-like). Many custom Fortnite experiences use 0 or positive values.

---

## `execute_python` — Direct Device Access

When the MCP bridge is running, Claude Code can run arbitrary Python in UEFN
to access device properties that no tool exposes:

```python
# Via MCP — inspect a specific device by label
ue.execute_python("""
target = None
for a in actor_sub.get_all_level_actors():
    if "score_manager" in a.get_actor_label().lower():
        target = a
        break

if target:
    props = {}
    for name in dir(target):
        try:
            val = getattr(target, name)
            if not callable(val):
                props[name] = str(val)
        except Exception:
            pass
    print(props)
""")
```

---

*Part of the UEFN Toolbelt schema documentation suite.*
*For C++ actor properties: see [DEVICE_API_MAP.md](DEVICE_API_MAP.md)*
*For technical quirks: see [UEFN_QUIRKS.md](UEFN_QUIRKS.md)*
