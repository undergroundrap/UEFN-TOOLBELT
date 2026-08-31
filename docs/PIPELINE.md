# The UEFN Industrialization Pipeline
### Autonomous Game Development with Claude + UEFN Toolbelt

> **Vision:** A complete UEFN Fortnite Creative game — scaffolded, populated, coded,
> compiled, and verified — driven entirely by Claude with one human in the loop only
> where Epic's API currently requires it (the Verse compiler trigger).
>
> **Author:** Ocean Bennett · March 2026
> **Status:** Phases 0–4 fully operational. Phase 5 loop requires one manual click.
> Phase 5 becomes fully headless when Epic exposes a Python compiler API.

---

## The Big Picture

```
CONCEPT
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 0 — PROJECT SETUP                                        │
│  scaffold_generate · organize_assets                            │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1 — RECONNAISSANCE                          ← READ       │
│  world_state_export · device_catalog_scan                       │
│  "What's in this level?" + "What can I place?"                  │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2 — DESIGN                                  ← REASON     │
│  Claude reasons about the game concept                          │
│  Selects devices from catalog · Plans layout                    │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3 — PLACEMENT                               ← BUILD      │
│  MCP spawn_actor · set_actor_transform                          │
│  Places devices from catalog asset paths                        │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 4 — CODE GENERATION                         ← WRITE      │
│  verse_gen_game_skeleton · verse_write_file                     │
│  Full wired creative_device Verse file deployed                 │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 5 — BUILD + FIX LOOP              ← THE RECURSIVE PART  │
│                                                                 │
│  [click Build Verse]  ──→  verse_patch_errors                   │
│         ▲                        │                              │
│         │                        ▼                              │
│         │              errors? ──→ Claude reads errors + file   │
│         │                        │                              │
│         │                        ▼                              │
│         └──── verse_write_file (overwrite=True)                 │
│                                                                 │
│  LOOP until build_status == "SUCCESS"                           │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 6 — VERIFY + CHECKPOINT             ← CONFIRM           │
│  world_state_export · snapshot_save                             │
│  Confirms level matches design intent · Creates rollback point  │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
PLAYABLE GAME
```

---

## Phase 0 — Project Setup

**Goal:** Clean slate. Correct folder structure. No loose assets.

| Tool | Params | What it does |
|---|---|---|
| `scaffold_generate` | `template="uefn_standard"`, `project_name` | Creates full `/Game/` folder tree |
| `scaffold_list_templates` | — | Preview available templates |
| `organize_assets` | `folder=""` | Sorts loose assets into typed subfolders |
| `rename_enforce_conventions` | `scan_path=""` | Fixes naming convention violations |

```python
tb.run("scaffold_generate", template="uefn_standard", project_name="MyGame")
tb.run("organize_assets", folder="")
```

**Claude should do this once per new project before anything else.**

---

## Phase 1 — Reconnaissance

**Goal:** Claude builds a complete picture of the level and the full device palette.

### 1a. Read the level

```python
tb.run("world_state_export")
# → docs/world_state.json
# Every actor: label, class, location, rotation, scale, tags, all readable properties
```

**What Claude gets:** A JSON of every actor in the level — 521 actors in the
Device_API_Mapping reference level. Claude knows exact device labels, positions, and
all accessible Python-readable properties.

### 1b. Read the full device palette

```python
tb.run("device_catalog_scan")
# → docs/device_catalog.json
# 4,698 Creative device Blueprints across 35 categories
# (First documented on March 22, 2026 by Ocean Bennett)
```

**What Claude gets:** Every device that EXISTS in Fortnite Creative, not just what's
placed. Claude can now propose what a level SHOULD have, not just work with what's there.

**Why both matter:**
- `world_state_export` = reactive intelligence (work with what exists)
- `device_catalog_scan` = generative intelligence (design from scratch)

Together they give Claude the complete read layer.

---

## Phase 2 — Design

**Goal:** Claude reasons about the game concept and selects devices.

This phase is pure Claude reasoning — no tool calls. Claude reads the outputs of Phase 1
and answers:

1. What game mode fits the devices in the level? (capture, elimination, race, survival...)
2. What devices from the catalog are missing but needed?
3. What is the round flow? (start → objective → win condition → end)
4. Where should devices be placed? (use location data from world_state.json)
5. What Verse events need to be wired? (capture events, timer expiry, button presses...)

**Claude's design checklist:**
```
□ Game mode identified
□ Win condition defined (timer, score, objective)
□ Device list finalized (from catalog + existing level)
□ Round flow mapped (OnBegin → events → EndRound)
□ Verse types confirmed for each device
□ @editable slot names decided (match actor labels from world_state)
```

---

## Phase 3 — Placement

**Goal:** Place devices from the catalog into the level via MCP.

The catalog gives Claude the exact asset paths. The MCP bridge handles spawning.

```python
# Via authenticated same-user MCP (requires mcp_start to be running):
# spawn_actor uses the asset path from device_catalog.json

# Example — place a Score Manager at world origin:
# ue.run("spawn_actor",
#         asset_path="/Game/Athena/Devices/BP_ScoreManager_C",
#         location=[0, 0, 0],
#         label="ScoreManager_1")

# Position it:
# ue.run("set_actor_transform",
#         actor_path="ScoreManager_1",
#         location=[500, 0, 100])
```

**Claude's placement workflow:**
1. Read `device_catalog.json` → find asset path for needed device
2. Call MCP `spawn_actor` with that path
3. Call MCP `set_actor_transform` to position it
4. Re-run `world_state_export` to confirm placement

**Note:** Placement works today via MCP. The `spawn_actor` command accepts any valid
asset path from the Content Browser. The catalog gives Claude those paths.

---

## Phase 4 — Code Generation

**Goal:** Generate a complete, wired Verse `creative_device` and deploy it.

```python
# Step 1: Generate skeleton based on devices found in world_state.json
tb.run("verse_gen_game_skeleton", device_name="MyGameManager")
# → Saved/UEFN_Toolbelt/snippets/game_systems/MyGameManager.verse

# Step 2: OR — Claude generates directly from world_state data
# (Claude reads world_state.json, writes the full Verse manually)

# Step 3: Deploy to project
tb.run("verse_write_file",
       filename="my_game_manager.verse",
       content=verse_code,
       overwrite=True)
# → Project/Verse/my_game_manager.verse
```

**What the generated file contains:**
- `@editable` declarations for every device (matched to real actor labels)
- `OnBegin<override>()` that wires all events
- Async watchers for objective loops (`WatchCaptureArea`, `WatchCreatureWaves`, etc.)
- Event handlers for buttons, timers, player interactions
- `EndRound()` that stops all devices cleanly

**Proven result:** `device_api_game_manager.verse` — 6,187 bytes, 21 `@editable` refs,
full event wiring — compiled `VerseBuild: SUCCESS` on first attempt. March 22, 2026.

---

## Phase 5 — Build + Fix Loop

**Goal:** Verse compiles clean. Claude fixes its own errors recursively.

This is the industrialization core. The loop runs until `build_status == "SUCCESS"`.

### The Loop

```
ITERATION 1:
  User: [clicks Verse → Build Verse Code]
  Claude: tb.run("verse_patch_errors")
  → {"build_status": "FAILED", "error_count": 3, "errors": [...], "files": {...}}
  Claude: reads errors + file content → generates fix → calls verse_write_file(overwrite=True)

ITERATION 2:
  User: [clicks Build Verse again]
  Claude: tb.run("verse_patch_errors")
  → {"build_status": "FAILED", "error_count": 1, "errors": [...], "files": {...}}
  Claude: fixes remaining error → verse_write_file(overwrite=True)

ITERATION 3:
  User: [clicks Build Verse]
  Claude: tb.run("verse_patch_errors")
  → {"build_status": "SUCCESS", "error_count": 0}
  Claude: "Build succeeded. Moving to Phase 6."
```

### verse_patch_errors — what it returns

```python
result = tb.run("verse_patch_errors")

# result["build_status"]  → "SUCCESS" | "FAILED" | "UNKNOWN"
# result["error_count"]   → int
# result["errors"]        → [{"file", "line", "col", "message"}, ...]
# result["files"]         → {"game_manager.verse": "...full content..."}
# result["next_step"]     → plain-English instruction for Claude
```

### Common Verse errors Claude will encounter and fix

| Error | Cause | Fix |
|---|---|---|
| `identifier 'X' not found` | Wrong Verse type name for a device | Look up correct type in Verse schema |
| `no overload of 'Subscribe' takes 1 argument` | Wrong event handler signature | Add correct agent/player param |
| `'X' is not a member of 'Y'` | Method doesn't exist on that device type | Check api_crawl_selection for real methods |
| `expected expression` | Syntax error in generated code | Fix indentation or missing brace |
| `type mismatch` | Passing wrong type to a method | Cast or use correct type |

### When Epic unlocks the compiler

```python
# TODAY: user clicks Build Verse (one human action per iteration)

# FUTURE (if Epic exposes an in-editor Python API):
tb.run("system_build_verse")   # would trigger the compiler from Python
result = tb.run("verse_patch_errors")
# → fully headless loop, zero human clicks
```

---

## Phase 6 — Verify + Checkpoint

**Goal:** Confirm the level matches design intent. Create a rollback point.

```python
# Verify level state matches what was designed
tb.run("world_state_export")
# → Read docs/world_state.json — confirm all devices are present and positioned

# Save a checkpoint before publishing
tb.run("snapshot_save", name="post_build_v1")
# → Can restore this exact state with snapshot_restore("post_build_v1")

# Compare against initial state
tb.run("snapshot_diff", name_a="before_build", name_b="post_build_v1")
```

---

## Publish Boundary — Audit, Stage, Validate, Restore

The six automation phases end before UEFN remote validation. Keep Toolbelt
Python loaded long enough to run the publish audit and cleanup:

```python
result = tb.run("publish_audit")
print(result)
tb.run("sign_clear", all_text_actors=True, dry_run=False)  # if blocked
tb.run("save_all_dirty")
```

After `publish_audit` has no blockers, use the host-side validation workflow:

```text
prepare_launch.bat
Launch Session / Push Changes / publish; wait for the remote result
restore_after_launch.bat
```

UEFN 42.00 rejects every project `.py` for the standard `VKCreateUGC` role,
and `.urcignore` does not affect Valkyrie staging. Fortnite opening is not proof
that remote validation passed. Do not restart, hot-reload, or deploy Toolbelt
while the Python stash is active. See `docs/UEFN_QUIRKS.md` Quirks #37 and #42.

---

## Full Pipeline — Claude's Execution Script

When asked to build a game from scratch, Claude should execute this sequence:

```python
# ── PHASE 0: Setup ──────────────────────────────────────────────
tb.run("scaffold_generate", template="uefn_standard", project_name="MyGame")
tb.run("organize_assets", folder="")

# ── PHASE 1: Reconnaissance ─────────────────────────────────────
tb.run("device_catalog_scan")     # load docs/device_catalog.json
tb.run("world_state_export")      # load docs/world_state.json

# ── PHASE 2: Design ─────────────────────────────────────────────
# [Claude reads both JSONs, reasons about game concept, selects devices]

# ── PHASE 3: Placement (via MCP) ────────────────────────────────
# ue.run("spawn_actor", asset_path=..., location=..., label=...)
# ue.run("set_actor_transform", actor_path=..., location=...)
tb.run("world_state_export")      # confirm placement

# ── PHASE 4: Code Generation ─────────────────────────────────────
tb.run("verse_write_file", filename="game_manager.verse",
       content=generated_verse, overwrite=True)

# ── PHASE 5: Build + Fix Loop ────────────────────────────────────
# [User clicks Build Verse]
# LOOP:
result = tb.run("verse_patch_errors")
while result["build_status"] != "SUCCESS":
    # Claude fixes result["files"] based on result["errors"]
    tb.run("verse_write_file", filename=..., content=fixed, overwrite=True)
    # [User clicks Build Verse]
    result = tb.run("verse_patch_errors")

# ── PHASE 6: Verify ──────────────────────────────────────────────
tb.run("world_state_export")
tb.run("snapshot_save", name="release_v1")
```

The Python sequence stops here. Follow the Publish Boundary above before any
Launch Session, Push Changes, or island submission.

---

## Tool Status Map

| Phase | Tool | Status | Notes |
|---|---|---|---|
| 0 | `scaffold_generate` | ✅ | All 4 templates working |
| 0 | `organize_assets` | ✅ | — |
| 1 | `world_state_export` | ✅ | 521 actors, proven |
| 1 | `device_catalog_scan` | ✅ | 4,698 devices, proven |
| 2 | *(Claude reasoning)* | ✅ | No tool needed |
| 3 | MCP `spawn_actor` | ✅ | Requires `mcp_start` |
| 3 | MCP `set_actor_transform` | ✅ | Requires `mcp_start` |
| 4 | `verse_gen_game_skeleton` | ✅ | — |
| 4 | `verse_write_file` | ✅ | Path fix confirmed |
| 5 | `[Build Verse click]` | ⚠️ | 1 human action per iteration |
| 5 | `verse_patch_errors` | ✅ | Full error + file content return |
| 5 | `system_build_verse` | ⏳ | No in-editor Python compiler API. Epic's official UEFN MCP server compiles Verse on its own surface |
| 6 | `world_state_export` | ✅ | Re-run for verification |
| 6 | `snapshot_save` | ✅ | — |

---

## The Remaining Human Build Step

Inside the build/fix loop, the remaining human action is **clicking Build Verse**.
Launch Session, Push Changes, and publishing are separate editor-driven actions
after the automation pipeline; the host helpers only make their staged project
validation-safe.

Epic's UEFN Python sandbox does not expose a `BuildVerseCode()` function. From Python,
the Verse compiler is reachable only through the editor UI (Verse menu → Build Verse
Code) or the desktop `UnrealEditor-Cmd.exe` with `-run=VerseBuilder`, which requires a
separate process outside the sandboxed Python environment.

This is a limit of the in-editor Python surface, not of UEFN 42.00. Epic's official
UEFN MCP server writes and compiles Verse on its own surface (Epic's 42.00 ecosystem
release notes and Epic's UEFN MCP documentation page). Reaching it means using that
server, not Toolbelt's Python API and not Toolbelt's custom bridge.

`system_build_verse` attempts the subprocess approach but this is not reliable inside
the UEFN sandbox. `verse_patch_errors` is designed to work regardless — it reads whatever
build output exists in the log directory after the user's manual click.

**When Epic adds a Python `BuildVerseCode` API:** change one line in `system_build.py`
and the entire pipeline becomes fully headless. Every other piece is already in place.

---

## The Numbers That Matter

| Metric | Value | Date |
|---|---|---|
| Level actors readable by Claude | 521 | March 2026 |
| Fortnite Creative devices catalogued | 4,698 | March 2026 (first ever) |
| Generated Verse file size | 6,187 bytes | March 2026 |
| Compile attempts to SUCCESS | 1 | March 2026 |
| Human clicks required (current) | 1 per build iteration | — |
| Human clicks required (future) | 0 | When Epic unlocks compiler |

---

*UEFN Toolbelt — Built by Ocean Bennett · 2026 · [AGPL-3.0](../LICENSE)*
*Full technical breakdown: [AI_AUTONOMY.md](AI_AUTONOMY.md)*
*All discovered API quirks: [UEFN_QUIRKS.md](UEFN_QUIRKS.md)*
