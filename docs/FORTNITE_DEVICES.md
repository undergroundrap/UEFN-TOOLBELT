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

**Pairing teleporters via Python:**
```python
# Select two teleporter actors, get their labels
teleporters = [a for a in selected if "Teleporter" in a.get_class().get_name()]
# They wire to each other via their Verse @editable references in UEFN editor
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
