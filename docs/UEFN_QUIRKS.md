# 🧩 UEFN Technical Quirks & "Deep Lore"

This document records the non-obvious, often undocumented behaviors of the UEFN Python and Verse APIs discovered during the development of the Toolbelt.

---

## 1. The "Invisibility" of Verse Classes (Breakthrough: Phase 19)

### The Problem
When a Verse device is placed in a level, the UEFN Python API (`actor.get_class()`) often identifies it only as a generic **`VerseDevice_C`**. The link to the user's specific script (e.g., `hello_world_device`) is frequently hidden from `dir()` and `get_editor_property()`.

### The "Named Auto-Link" Solution
The Toolbelt implements a fuzzy resolution fallback. If the API returns a generic class, the tool normalizes the **Actor Label** (e.g., `"hello world device"` -> `"hello_world_device"`) and matches it against the project's Verse schema (`.digest` files). 
**Takeaway**: Keeping your Outliner labels consistent with your Verse class names is the key to robust Python automation.

---

## 2. The "Main Thread Lock" 

### The Problem
UEFN runs the Python interpreter on the same thread as the editor's main render loop. Using `time.sleep()` or long synchronous loops will **freeze the entire editor**.

### The "Ghost File" Quirk
If you trigger an engine action that takes time (like saving a file or taking a high-res screenshot), you **cannot** wait for that file's existence in the same Python block. Unreal needs to "tick" to actually write the file, but it cannot tick because Python is still blocking the thread.
**Takeaway**: Trigger the action and exit. Use a UI callback or a later execution block to verify the result.

---

## 3. Circular Imports in Tool Registration

### The Problem
Adding diagnostic or helper tools that need to call the main `registry` or `core` can easily trigger circular imports because `tools/__init__.py` imports everything.

### The Solution: `diagnostics.py` Pattern
Keep diagnostic tools in a separate file (`diagnostics.py`) and import them directly in the top-level `__init__.py` rather than the `tools/` subpackage. This decouples the "Health and Debug" layer from the "Operational" layer.

---

## 4. `inspect.getmembers()` SystemError

### The Problem
Running `inspect.getmembers()` on certain `unreal.*` objects (especially Blueprints or Verse devices) can trigger a `SystemError: error return without exception set` within the Python C-API. This is likely due to a malformed `getattr` implementation on the engine side.

### The Solution
Use a safe combination of `dir(obj)` and a `try-except` wrapped `getattr(obj, name)` for all property audits.

---

## 5. Asset Registry Path Sensitivity

### The Problem
Searching for assets in `/Game` works for standard content, but project-specific Verse assets often live in a virtual path like `/ProjectName/_Verse`.

### The Solution
Always audit the **Asset Registry** using a recursive filter on the project root package (e.g., `/TOOL_TEST`) to find the true `VerseClass` assets.

---

## 6. The "Invalid Flags" Selection Warning

### The Problem
`LogActorLevelEditorSelection: Warning: SelectActor: The requested operation could not be completed because the actor has invalid flags.`
This happens when you spawn an actor (e.g., a Cube or a Teleporter) and immediately try to select it before the engine has finished registering its object flags (like `RF_Transactional`).

### The Solution
Wrap your spawning and selection in a **`ScopedEditorTransaction`**. This forces the engine to treat the operation as a single undoable unit and ensures flags are correctly updated before the transaction closes.

---

## 7. `get_editor_property` vs. `getattr()`

### The Problem
Traditional Unreal Python advice says to use `actor.get_editor_property("PropertyName")`. However, for many Verse-driven properties, this will raise an `Exception` because the properties aren't technically marked as "Editor Properties" in the C++ sense.

### The Solution
Use **`getattr(actor, "PropertyName")`** or `dir(actor)` first. Many Verse properties are reflected into the Python object's dictionary even if they aren't part of the formal Editor Property system.

---

## 8. Virtual Packaging: The `_Verse` Folder

### The Problem
Verse code doesn't live in the standard `/Game/` path. It lives in a virtual project-specific package like `/YourProjectName/_Verse`.

### The Solution
When using the `AssetRegistry`, always search specifically in the project root. The `_Verse` folder is where you'll find the `VerseClass` definitions and "task" objects (like `on_begin` callbacks).

---

## 9. The "Ghost" Subsystem Quirk

### The Problem
Some subsystems like `EditorActorSubsystem` can return `None` if accessed too early in the `init_unreal.py` startup sequence.

### The Solution
Use `unreal.get_editor_subsystem(unreal.EditorActorSubsystem)` as a late-initialization call inside your tool's function, rather than storing it as a global module-level variable.

---

## 10. Dashboard v2: The `_title` Signature Bug

### The Problem
When migrating large dashboard classes to a dynamic **`builder()`** pattern, a subtle `NameError` can occur if the internal helper functions (like `_build_header`) attempt to access `self._title` before it is defined by the builder context. 

### The Solution
Ensure your dashboard builder pattern explicitly passes the **`title`** variable into the component builders, rather than relying on class state. The Toolbelt now uses a `builder(R, title)` pattern to avoid this initialization race condition.

---

## 11. Deprecation: `EditorLevelLibrary` vs. `EditorActorSubsystem`

### The Problem
Many UEFN tutorials from 2024-2025 use `unreal.EditorLevelLibrary.get_selected_level_actors()`. In the 2026 update, this is often marked as legacy or behaves inconsistently with Verse actors.

### The Solution
Always migrate to **`unreal.EditorActorSubsystem`**. It provides better world-context awareness and handles the "Dirty State" and "Undo Transactions" more reliably for Verse-backed devices.

---

## 12. Dashboard Responsiveness: The `slate_post_tick` Pattern

### The Problem
Because Python and UEFN share the same thread, a PySide6 window will normally "freeze" (become non-interactive) as soon as it's opened, as the editor loop isn't letting the Qt event loop run.

### The Solution
The Toolbelt uses `unreal.register_slate_post_tick_callback` to hook into the engine's frame-end. Each frame, we call `QApplication.processEvents()`. This allows the UI to stay 60fps responsive without threading, which is the only stable way to run Qt in UEFN.

As of v1.5.1, this pattern is encapsulated in `core/base_window.ToolbeltWindow.show_in_uefn()`.
Any tool window that subclasses `ToolbeltWindow` gets the Slate tick driver automatically —
just call `win.show_in_uefn()` instead of `win.show()`. See `docs/ui_style_guide.md`.

---

## 13. Menu Persistence & "Ghost Entries"

### The Problem
Menues created via `unreal.ToolMenus` are stored in the editor's memory. If you reload your script and re-register the menu, you may end up with duplicate "Toolbelt" entries or "Ghost" buttons that point to deleted Python objects.

### The Solution
The Toolbelt's `_build_menu` logic first searches for the existing `Toolbelt` menu entry and **clears its children** before rebuilding. This ensures that `tb.reload()` always results in a fresh, single menu entry.

---

## 14. `unreal.ScopedSlowTask` vs. Python Loops

### The Problem
A long Python loop (e.g., modifying 500 actors) will trigger Windows to think the app is "Not Responding" and show a white overlay, as the message pump is blocked.

### The Solution
Wrap heavy loops in `unreal.ScopedSlowTask`. This not only provides a native UI progress bar but also keeps the editor's heartbeat alive. 
**Crucial Quirk**: You must call `task.enter_progress_frame()` manually inside your loop to advance the bar and process the "Cancel" button state.

---

## 15. The `init_unreal.py` Cold-Boot Requirement

### The Problem
UEFN only scans and executes `init_unreal.py` when the project first loads.

### The Solution
While you can "Nuclear Reload" the Toolbelt modules while the editor is open, changes to the **Top Menu Bar structure** (adding new top-level categories) usually require a full project restart to be correctly picked up by the Slate menu system.

---

## 16. The MCP Return Loop: Tools Must Return Dicts

### The Problem
A tool that returns `None` (or a bare primitive like `int`, `str`, or a live `unreal.*` object) breaks the MCP return loop. When Claude Code calls a tool via the bridge, the response body is `{"success": true, "result": null}` — the AI has no signal and cannot act on the result.

Even worse, `unreal.*` objects are not JSON-serializable at all and will cause the bridge's `_serialize()` function to silently discard them. The tool "works" locally but fails silently under automation.

### The Rule
Every `@register_tool` function must return a `dict` with at minimum a `"status"` key:

```python
# ✅ Correct — readable by any MCP caller
return {"status": "ok", "placed": len(actors)}
return {"status": "error", "placed": 0}

# ❌ Wrong — breaks MCP
return          # None
return count    # bare int
return actor    # unreal object — not serializable
```

### Why It Propagates Through the Full Stack
The complete chain is: `tool()` → `registry.execute()` → `_serialize(result)` → JSON body → Claude Code reads `result` field. Every link must be JSON-compatible for the agent to read a real signal. This is why the Phase 21 refactor converted every remaining `None`-returning tool to structured dicts.

---

## 18. Mesh Reduction is Not Available in UEFN Python

### The Problem
Calling `StaticMeshEditorSubsystem.set_lods_with_notification()` from Python in UEFN causes an **`EXCEPTION_ACCESS_VIOLATION` crash at address `0x0`** — a C++ null-pointer dereference inside the mesh reduction pipeline. Python `try/except` cannot catch this. The editor closes immediately with no recovery.

The root cause: UEFN's sandboxed Python environment does not load the mesh reduction plugin (Simplygon or UE's built-in Quadratic Error Metrics reducer). The `StaticMeshEditorSubsystem` is accessible and appears healthy, but its internal reduction interface pointer is null. Any call that reaches it crashes the engine.

### What Is Safe
- `mesh_sub.get_lod_count(mesh)` — safe, reads metadata only
- `mesh.get_editor_property("body_setup")` — safe
- `lod_audit_folder` — safe, read-only
- `lod_set_collision_folder` — safe, sets a property flag only

### What Crashes
- `set_lods_with_notification()` — crashes unconditionally
- Any call that invokes the mesh reduction / simplification pipeline

### The Solution
Auto-LOD generation must be done manually in the Static Mesh Editor (double-click mesh → LODs tab → Auto Generate), or in a full UE5 desktop editor session where the mesh reduction plugin is loaded. The Toolbelt's `lod_auto_generate_*` and `memory_autofix_lods` tools return a clear error message instead of crashing.

If Epic exposes the mesh reduction pipeline in a future UEFN Python update, re-enable `_apply_lods` in `lod_tools.py`.

---

## 19. The V2 Device Property Wall (Discovered: March 2026)

### The Problem
Fortnite V2 Creative devices (Timer Device, Capture Area, Score Manager, Guard Spawner, etc.)
appear in the Python layer with specific class names like `FortCreativeTimerDevice`, but their
underlying Blueprint is a Verse-compiled class (e.g., `Device_Timer_V2_C`).

Their **game-logic settings** — countdown duration, score targets, team assignments, channel
numbers, enabled state — are stored as Verse `@editable` properties inside the Verse runtime.
They are **not** UPROPERTYs and cannot be accessed via `get_editor_property` or
`set_editor_property`. Both will raise:

```
Failed to find property 'bIsEnabled' for attribute 'bIsEnabled' on 'Device_Timer_V2_C'
```

`getattr()` also fails for these — they are not reflected into the Python object dictionary.

### What IS accessible via Python on V2 devices
- **Base class properties**: `allow_highlight`, `net_priority`, `net_dormancy`, `actor_guid`, etc.
- **State enums**: `client_current_state` → e.g., `TimerDeviceState.ENABLED`
- **Methods** (discovered via `api_crawl_selection` — always crawl first):
  - `FortCreativeTimerDevice`: `timer_pause`, `timer_resume`, `timer_set_state`,
    `timer_clear_handles` (no-arg). `timer_start(tracked_player)` requires a live
    player reference — **editor-only sessions cannot call it**.
  - `FortCreativeTimerObjective`: `blueprint_pause`, `blueprint_stop`, `on_reset`,
    `moderator_set_timer_complete` (no-arg). Read state via `get_is_started()`,
    `get_is_paused()`, `is_timer_active()`.
  - **Rule**: methods requiring `player`/`agent` args are runtime-only. Calling them
    from the editor Python session raises `required argument not found`.
- **Transforms**: location, rotation, scale — always accessible

### What is NOT accessible
- Countdown duration, score-to-win, team index, channel assignments
- Any setting you would configure via the device's Properties panel in the UEFN editor UI

### The Two Correct Approaches

**Option A — Method invocation** (for runtime control):
```python
# No-arg methods work from the editor session:
tb.run("device_call_method", class_filter="TimerObjective", method="blueprint_pause")
tb.run("device_call_method", class_filter="TimerObjective", method="blueprint_stop")
tb.run("device_call_method", class_filter="TimerDevice",   method="timer_pause")

# Read state (returns value in results list):
tb.run("device_call_method", class_filter="TimerObjective", method="is_timer_active")

# Methods requiring a player/agent ref WILL FAIL from the editor:
# timer_start(tracked_player) — runtime only, call from Verse instead
```
Always run `api_crawl_selection` on a device first to discover its real method list.

**Option B — Verse code generation** (for initial configuration):
Claude generates a Verse `creative_device` that holds `@editable` references to the target
devices and sets their properties at `on_begin`. This is the architecturally correct solution —
UEFN's design intent is that device configuration happens in Verse, not Python.

```verse
MyGameManager := class(creative_device):
    @editable TimerDevice : timer_device = timer_device{}

    OnBegin<override>()<suspends> : void =
        TimerDevice.SetDuration(120.0)
        TimerDevice.Enable()
```

### The Crash Companion
During introspection of V2 devices, **never use PySide6 progress bars** (`with_progress`)
alongside heavy `get_editor_property` reflection. The Qt Slate tick fires during iteration
and can dereference null C++ pointers on Verse-backed objects, causing
`EXCEPTION_ACCESS_VIOLATION`. Use plain `unreal.log()` for progress reporting instead.

---

## 20. AssetData Deprecated Properties — The Silent Skip Bug

### The Problem
In UEFN 40.00, several `unreal.AssetData` properties are deprecated and raise or return
garbage when accessed:

- `asset.object_path` → deprecated, should use `asset.get_full_name()`
- `asset.asset_class` → deprecated, should use `asset.asset_class_path`

If your Asset Registry loop wraps ALL property reads in one `try/except: continue` block,
the deprecated property throws on every single asset and your loop silently processes nothing.
This is especially treacherous because the scan reports a correct total count — it just
identifies 0 matches.

**The failure pattern:**
```python
# ❌ One except block skips the entire asset when any optional field is deprecated
for asset in assets:
    try:
        name = str(asset.asset_name)
        path = str(asset.object_path)     # ← throws DeprecationWarning/error
        cls  = str(asset.asset_class)     # ← also deprecated
    except Exception:
        continue   # ← silently drops all 24,926 assets
```

### The Solution
Make `asset_name` the only required field. Wrap each optional deprecated property
individually and use the new API with a fallback:

```python
# ✅ Only skip if the essential field is unavailable
for asset in assets:
    try:
        asset_name = str(asset.asset_name)
    except Exception:
        continue

    try:
        object_path = asset.get_full_name()   # replaces object_path
    except Exception:
        object_path = asset_name

    try:
        class_name = str(asset.asset_class_path)  # replaces asset_class
    except Exception:
        class_name = "Unknown"
```

**Discovered:** During `device_catalog_scan` first run (March 2026). Tool reported
24,926 assets scanned, 0 devices found — until the try/except was split. After fix:
**4,698 devices across 35 categories**.

---

## 21. Verse Compiler Is Lenient With Unknown Identifiers

### The Discovery
When testing `verse_patch_errors`, a file containing `nonexistent_device_type` and calls
to `FakeDevice.DoesNotExist()` and `UndeclaredVariable.Enable()` **compiled successfully**
(`VerseBuild: SUCCESS`). No errors, no warnings.

### Why
Verse's compiler creates **stub types** for unknown identifiers rather than failing
immediately. If a type is not resolvable from the `using` declarations, Verse treats it
as an opaque/unknown type and defers the error — or silently accepts it if no downstream
type constraint is violated.

This means the Verse type checker only errors on:
- **Known type violations** — assigning `"string"` to `int`, `999` to `logic`
- **Wrong argument counts/types on known types** — calling `timer_device.Start(999, "x")`
- **Syntax errors** — missing colons, wrong indentation, malformed expressions
- **Missing `using` for types you actually use** — if Verse can't find the module

### What Does NOT cause errors (surprisingly)
```verse
# These compile fine — Verse stubs unknown identifiers silently
@editable
FakeDevice : nonexistent_device_type = nonexistent_device_type{}

OnBegin<override>()<suspends> : void =
    FakeDevice.DoesNotExist()       # compiles — FakeDevice is unknown type
    UndeclaredVariable.Enable()     # compiles — UndeclaredVariable is stubbed
```

### What DOES cause errors (reliable test targets)
```verse
# These fail against known Verse types:
var Score : int = "this is not an int"    # type mismatch
var Flag  : logic = 999                   # type mismatch
MyTimer.Start(999, "wrong", false)        # wrong args on known timer_device type
```

### Addendum: Editor Build vs. Push Changes (discovered March 22, 2026)
Further testing confirmed that **`Build Verse Code` (editor mode) is even more permissive
than listed above.** Calling `.Subscribe()` on `GetElapsedTime()` — which returns `float`,
not an event — compiled with `VerseBuild: SUCCESS`. No error, no warning.

The editor-mode build does **not** run full type checking. It performs:
1. Syntax parsing
2. Package registration / UObject type generation
3. Linking of known modules

Full type checking — including method-not-found, wrong-argument-count on known types, and
cross-module type violations — only runs during **Push Changes** (the full publish pipeline).

**This means `verse_patch_errors` targets the Push Changes log, not editor builds.**
The error loop is designed for the real compiler, not the editor's fast-registration pass.

### Implication for `verse_patch_errors`
When Claude generates Verse with wrong device type names, the code may silently compile
in editor mode but fail at Push Changes time. Always verify generated type names against
the Verse schema rather than relying on editor build errors to catch them.

**Takeaway:** `VerseBuild: SUCCESS` in editor mode only guarantees syntax + package
registration. Full type correctness is only verified at Push Changes.

---

## 22. Chaining Heavy Operations Crashes the Engine (EXCEPTION_ACCESS_VIOLATION)

### The Discovery
Running multiple heavy Unreal operations back-to-back in a single Python execution block
caused `EXCEPTION_ACCESS_VIOLATION writing address 0x0000000000000000` — a hard editor crash.

The sequence that triggered it:
1. `scaffold_generate` (56 folder creates via Asset Registry)
2. `organize_assets` (Asset Registry move operations)
3. `rename_enforce_conventions` (more Asset Registry writes)
4. `arena_generate` (actor spawning immediately after)

Steps 1-3 flood the Asset Registry with state changes. When step 4 tries to spawn
actors before the engine has yielded and processed those changes, a null pointer
dereference in the render thread kills the process.

### The Rule
**Only pure Python file writes are safe to chain after scaffold_generate.**
Any Unreal C++ API call chained in the same Python execution will crash.

- Safe to chain with scaffold: `verse_write_file`, `verse_gen_game_skeleton` (file ops)
- Must be separate calls: `organize_assets`, `rename_enforce_conventions`,
  `snapshot_save`, `arena_generate`, any actor spawn or Asset Registry operation

### The Fix
Split the workflow across multiple tb.run() calls:

```python
# Call 1 -- scaffold + Verse file writes only (safe)
tb.run("project_setup", project_name="MyGame")

# [engine yields after Python call returns]

# Call 2 -- Asset Registry operations (separate)
tb.run("organize_assets", folder="/Game/")

# [engine yields]

# Call 3 -- more Asset Registry ops (separate)
tb.run("rename_enforce_conventions", scan_path="/Game/")

# [engine yields]

# Call 4 -- actor spawning (must be last)
tb.run("arena_generate", size="medium")
```

**Why:** `scaffold_generate` floods the Asset Registry with 50+ folder creates.
Any Unreal C++ call made before the engine ticks and flushes that state hits a
null pointer in the Asset Registry internals. Each `tb.run()` call returns to the
main thread, allowing a tick to occur before the next Python block runs.

**Takeaway:** After any bulk Asset Registry operation, every subsequent Unreal API
call must be its own `tb.run()` — never chained in the same Python execution block.

### Known unsafe tools on large projects
`rename_enforce_conventions` calls `load_asset()` on every asset in the scan path
recursively. On projects with hundreds of Blueprints and device actors this bulk load
crashes the engine. Safe only on fresh projects with few assets. Always run with
`dry_run=True` first to check the scope before committing.

---

## 17. `_serialize()` Swallows Unreal Objects Silently

### The Problem
The MCP bridge's `_serialize()` helper converts tool return values to JSON. If a tool returns a live `unreal.Actor` or any `unreal.*` object, `_serialize()` catches the `TypeError` internally and returns `null` — no error is raised, no log line is printed. The tool appears to succeed but the AI gets nothing.

### The Solution
Never return raw `unreal.*` objects from registered tools. Extract the data you need (labels, paths, counts, properties) into plain Python types before returning:

```python
# ❌ Returns an unserializable object
return actor

# ✅ Extract what you actually need
return {"status": "ok", "label": actor.get_actor_label(), "path": actor.get_path_name()}
```

---

## 23. `/Game/` Mount Point Is Invisible in the Content Browser (Discovered: March 2026)

### The Problem
In UEFN, `unreal.Paths.project_content_dir()` returns the **FortniteGame engine content path**
(`C:/Program Files/Epic Games/Fortnite/FortniteGame/Content`), not the user's project content
directory. Similarly, the internal `/Game/` mount point exists and accepts `duplicate_asset()`
calls — assets created there return `True` from `does_asset_exist()` — but **they never appear
in the Content Browser**. The Content Browser only shows the project's named mount point
(e.g. `/Device_API_Mapping/`).

### The Root Cause
UEFN runs as a plugin inside FortniteGame. `project_content_dir()` resolves relative to the
engine, not the user's island project. The `/Game/` mount is technically valid but maps to an
internal path that isn't surfaced in the browser UI.

### ⚠️ The Plugin Mount Trap (Critical — Causes Silent Mislocation)

Even after excluding known engine mounts, **Epic plugin mounts sort alphabetically before user
project mounts**. Taking the first non-engine mount is wrong:

```
/ACLPlugin/          ← Epic Animation Compression Library — sorts BEFORE user project
/AnimationWarping/   ← Another Epic plugin
/Device_API_Mapping/ ← actual user project ← you want this
```

Taking `candidates[0]` would return `/ACLPlugin/` — the import succeeds, reports no error,
but the asset lands in a plugin mount the Content Browser never shows. **This is silent data
loss from the user's perspective.**

Known Epic plugin mounts to exclude (not exhaustive — new ones appear with engine updates):
`ACLPlugin`, `AnimationLocomotionLibrary`, `AnimationWarping`, `CommonUI`, `GameplayAbilities`,
`GameplayTasks`, `GameplayMessageRouter`, `StructUtils`, `Chooser`, `UIExtension`,
`ModularGameplay`, `ModularGameplayActors`, `DataRegistry`, `SmartObjects`,
`StateTreeEditorModule`, `GameFeatures`, `ReplicationGraph`, `PhysicsControl`,
`Niagara`, `EnhancedInput`, `ControlRig`, `ModelingEditorAssets`, `QualityAssistEd`

### The Canonical Solution — "Most Paths" Detection

**Do not take the first alphabetical mount. Count cached paths per mount and take the largest.**
The user's project always has hundreds or thousands of content paths. Every Epic plugin has
fewer than ~50. This is reliable regardless of what plugins are installed:

```python
_SKIP_MOUNTS = frozenset({
    # Engine / runtime
    "Engine", "FortniteGame", "FortniteGame.com", "Fortnite", "Paper2D", "Script",
    # Epic editor plugins (add more as discovered — never remove entries)
    "QualityAssistEd", "Niagara", "EnhancedInput", "ModelingEditorAssets", "ControlRig",
    "ACLPlugin", "AnimationLocomotionLibrary", "AnimationWarping", "CommonUI",
    "GameplayAbilities", "GameplayTasks", "GameplayMessageRouter", "StructUtils",
    "Chooser", "UIExtension", "ModularGameplay", "ModularGameplayActors",
    "DataRegistry", "SmartObjects", "StateTreeEditorModule", "GameFeatures",
    "ReplicationGraph", "PhysicsControl",
})

def _detect_project_mount() -> str:
    """Return the user's project Content Browser mount — the mount with the most paths."""
    try:
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        counts: dict = {}
        for p in ar.get_all_cached_paths():
            root = p.strip("/").split("/")[0]
            if root and root not in _SKIP_MOUNTS:
                counts[root] = counts.get(root, 0) + 1
        if counts:
            return max(counts, key=counts.get)   # user project wins every time
    except Exception:
        pass
    return "Game"
```

### Fallback: User-Driven Detection (Most Reliable of All)

When a tool lets the user select assets before acting, derive the mount from the first asset
path the user provides. This is 100% reliable and requires no heuristic:

```python
# When user adds an asset from CB selection:
pkg = asset_data.package_name          # e.g. "/Device_API_Mapping/Meshes/SM_Wall"
mount = pkg.strip("/").split("/")[0]   # → "Device_API_Mapping"
self._dest.setText(f"/{mount}/Migrated/")
```

Use this approach in any windowed tool where the user provides assets before the destination
is needed (see `prefab_migrator.py` for a reference implementation).

### Getting the Project Content Dir on Disk

For disk-level operations (e.g. `shutil.copy2`), never use `project_content_dir()`.
Use `project_dir()` + `"/Content"` instead:

```python
# ❌ Returns FortniteGame engine path — wrong for user project files
src = unreal.Paths.project_content_dir()

# ✅ Returns user project Content dir on disk
project_root = unreal.Paths.convert_relative_path_to_full(
    unreal.Paths.project_dir()
).rstrip("/\\")
src = project_root + "/Content"
```

### Asset Path Rules

```python
# ❌ Wrong — imports succeed but asset is invisible in Content Browser
unreal.EditorAssetLibrary.duplicate_asset(src, "/Game/Migrated/SM_Wall")

# ✅ Correct — asset appears in CB under Migrated folder
mount = _detect_project_mount()        # e.g. "Device_API_Mapping"
unreal.EditorAssetLibrary.duplicate_asset(src, f"/{mount}/Migrated/SM_Wall")
```

`AssetData.package_name` always returns the project-mount form — never `/Game/`:
```
/Device_API_Mapping/Meshes/SM_Wall   ← what UEFN returns
/Game/Meshes/SM_Wall                 ← what UE5 docs show — WRONG in UEFN
```
Never force-prepend `/Game/` to paths from `get_selected_asset_data()` or the Asset Registry.

### Quick Reference — What NOT to Use

| API | Problem | Use instead |
|---|---|---|
| `Paths.project_content_dir()` | Returns FortniteGame engine path | `Paths.project_dir() + "/Content"` |
| `Paths.get_project_file_path()` | Returns `FortniteGame.uproject` | Asset Registry mount detection |
| `candidates[0]` (first alpha mount) | Picks ACLPlugin or similar before user project | `max(counts, key=counts.get)` |
| `/Game/` as asset destination | Assets invisible in Content Browser | `_detect_project_mount()` |

---

## 24. Loading Asset Objects in Audit/Scan Tools Causes EXCEPTION_ACCESS_VIOLATION (Discovered: March 2026)

### The Problem

Any tool that calls `asset_data.get_asset()` or loads a full asset object (texture, mesh,
material) during a bulk scan will randomly crash the editor with:

```
Unhandled Exception: EXCEPTION_ACCESS_VIOLATION writing address 0x0000000000000000
```

No Python traceback. No Output Log entry. The crash bypasses all `try/except` blocks
because it happens at the C++ level inside Unreal's asset system — Python never gets
a chance to catch it.

### How We Discovered It

Building the `level_health_report` tool, the first implementation called
`memory_scan_textures` and `lod_audit_folder` internally. Both tools load actual asset
objects to inspect texture dimensions and mesh LOD counts. The result was a repeatable
hard crash with `EXCEPTION_ACCESS_VIOLATION` — no log, no traceback, just the editor gone.

The crash only appeared after a few seconds (when the asset loading actually happened),
which initially looked like a threading issue. It was not — it was the asset object
loading itself hitting a null internal pointer.

### The Rule

**Audit and scan tools must use Asset Registry metadata only. Never call `get_asset()`
during a bulk scan.**

| Safe | Unsafe |
|---|---|
| `asset_data.package_name` | `asset_data.get_asset()` |
| `asset_data.asset_class_path` | `unreal.load_asset(path)` |
| `ar.get_assets(filter)` | `mesh.get_num_lods()` on a loaded object |
| `ar.get_all_cached_paths()` | `texture.get_editor_property("CompressionSettings")` |
| `actor.get_actor_location()` | Iterating loaded objects in a scan loop |

### The Fix Pattern

```python
# ❌ Crashes — loads asset object in a scan loop
for asset_data in ar.get_assets(filt):
    obj = asset_data.get_asset()          # ← null pointer risk
    lod_count = obj.get_num_lods()        # ← crash happens here

# ✅ Safe — reads metadata only, never loads
for asset_data in ar.get_assets(filt):
    name = str(asset_data.package_name)   # metadata only
    cls  = str(asset_data.asset_class_path.asset_name)
```

### Where This Applies

- Any tool that scans the entire project (LOD audit, memory scan, texture scan)
- Any "health check" or "report" tool that aggregates data across many assets
- Tools that check properties only available on loaded objects (texture size, LOD count,
  collision settings, material parameters)

For those properties, either: (a) accept that you can't read them safely in a bulk scan,
or (b) limit the scan to a small explicit selection the user has already loaded in the CB.

### Canonical Implementation

`level_health.py` — all five audit runners use AR metadata only, zero `get_asset()` calls.
This is the reference pattern for any future audit/scan tool.

---

## 25. PySide6 Windows Defined Inside Tool Functions Can Hard-Crash With No Log (Discovered: March 2026)

### The Problem

A `ToolbeltWindow` subclass defined **inside** a `@register_tool` function can cause an
immediate hard crash (no Output Log, no crash report) when `show_in_uefn()` is called —
even when structurally identical code works in other windowed tools.

The crash is silent: no Python traceback, no `EXCEPTION_ACCESS_VIOLATION` report, just
the editor process disappearing. `try/except` cannot catch it.

### What We Tried

During development of `level_health_open`, every standard approach was attempted:
- Removing `QThread` / `QApplication.processEvents()` — still crashed
- Replacing custom `paintEvent` (QPainter) — still crashed
- Removing `QScrollArea`, `QFrame.Shape.HLine`, emoji — still crashed
- Using `QFrame` vs `QWidget` as central widget — still crashed
- Matching the exact layout pattern from working windows (`verse_device_graph.py`) — still crashed

The headless version (`level_health_report`) runs the same audit logic without a window
and works perfectly every time.

### The Working Pattern (All Other Windows)

Windows defined at **module level** (outside any function) work reliably:

```python
# module level — works
class MyWindow(ToolbeltWindow):
    def __init__(self): ...

@register_tool(name="my_tool_open", ...)
def run_my_tool_open(**kwargs) -> dict:
    win = MyWindow()
    win.show_in_uefn()
    return {"status": "ok"}
```

### The Failing Pattern

Windows defined **inside** the tool function are the common factor in all crashes:

```python
@register_tool(name="my_tool_open", ...)
def run_my_tool_open(**kwargs) -> dict:
    class MyWindow(ToolbeltWindow):   # ← defined inside function
        def __init__(self): ...
    win = MyWindow()
    win.show_in_uefn()                # ← crashes here, no log
```

### Current Status

Root cause is unknown. Qt's metaclass system may behave differently for classes
created inside a function scope on repeated calls (hot-reload creates a new class
object each time). This may interact badly with PySide6's C++ type registry in
UEFN's embedded Python.

### The Rule

**Define all `ToolbeltWindow` subclasses at module level, never inside a function.**
If a tool's window crashes with no log despite correct code, move the class definition
outside the tool function.

For tools where the window cannot be made stable, fall back to a headless implementation
that logs output to the Output Log — this is always safe and MCP/AI-friendly.

---

## 26. Nuclear Reload Can Cause EXCEPTION_ACCESS_VIOLATION When Adding New Modules (Discovered: March 2026)

### The Problem

The nuclear reload command:

```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); ...
```

forcibly removes all `UEFN_Toolbelt` modules from `sys.modules`, which triggers Python's
garbage collector to destroy module-level objects. If any of those objects have registered
callbacks on the Unreal **C++ side** (Slate tick drivers, HTTP listeners, timer handles),
those C++ registrations remain live even after the Python objects are freed.

When Unreal fires one of those stale callbacks after GC, it writes to a freed Python object
— producing an `EXCEPTION_ACCESS_VIOLATION writing address 0x0000000000000000` with no
Python traceback and no way to catch it with `try/except`.

### When It Happens

This crash is most likely to occur when:

1. **Adding a new module** — the first nuclear reload after a new `from . import my_tool`
   is added to `tools/__init__.py`. The new module set increases the number of registered
   objects exposed to Unreal C++.
2. **A window is open** — any tool window with a Slate tick driver still registered when
   `sys.modules.pop` fires.
3. **MCP bridge is running** — the HTTP listener has a socket callback registered with
   Unreal's tick system.

### The Crash Signature

```
EXCEPTION_ACCESS_VIOLATION writing address 0x0000000000000000
```

Stack pattern: `UnrealEditorFortnite` frames → `python311` frames → `UnrealEditorFortnite`
frames → `user32` → `kernel32` → `ntdll`. The Python frames in the middle confirm execution
was inside Python when the stale C++ callback fired.

### The Fix

**Use a full UEFN restart instead of nuclear reload when adding a new module to the registry.**

Nuclear reload is safe for iterating on existing tools (re-registering the same module
objects the C++ side already knows about). It becomes unstable when the set of registered
Python objects changes — particularly on the first reload after adding a new module.

```
✅ Safe: nuclear reload while iterating on an existing tool (same module, same callbacks)
✅ Safe: nuclear reload when no windows are open and MCP bridge is stopped
⚠️ Risky: nuclear reload after adding a new module to tools/__init__.py
❌ Don't: nuclear reload with a PySide6 window open (Slate tick still registered)
❌ Don't: nuclear reload while mcp_start is running (socket callback still registered)
```

### Workflow

When adding a new tool module:
1. Edit the source files
2. **Restart UEFN** (File → Restart Editor, or close and reopen)
3. Test after the fresh cold boot — module objects are registered cleanly from the start
4. Only switch back to nuclear reload for further iteration once the module is stable

### Why Nuclear Reload Works at All

Nuclear reload works reliably for existing modules because: the same module-level objects
are re-created with the same IDs, and Unreal's C++ side re-registers them without
accumulating stale handles. The hazard window is only during the gap between `sys.modules.pop`
(Python objects freed) and the re-import (new objects registered).

---

## 27. Hard UEFN Restart Clears Stale State That Nuclear Reload Cannot (Discovered: March 2026)

### The Problem

Nuclear reload (`sys.modules.pop`) refreshes Python module code but **does not reset UEFN's internal C++ state**. After a crash, a project switch, or a series of failed hot-reloads, the engine can accumulate:

- Stale C++ object references pointing at freed Python objects
- Partially-registered Slate tick callbacks from a previous session
- Cached module-level globals that survived the `sys.modules` purge (e.g. class objects held by `Shiboken` or `unreal` internals)
- Actor/subsystem handles from a previous level that are no longer valid

These stale states can cause:
- `Abort signal received` crashes with a deep `python311` + `Shiboken` stack (no clear error message)
- Tools silently returning stale data from a previous project
- Nuclear reload appearing to succeed but tests still running old code
- `NameError: name 'tb' is not defined` after switching projects (Python environment was reset)

### The Fix

**When in doubt, do a hard UEFN restart.** This is the single most reliable debug step:

1. Close UEFN completely (File → Exit, or kill the process)
2. Reopen UEFN and load your project
3. Import fresh — do NOT use nuclear reload after a restart:

```python
import UEFN_Toolbelt as tb; tb.register_all_tools()
```

### When to Hard Restart (not just nuclear reload)

| Situation | Use |
|---|---|
| Added a new `.py` module to `tools/` | Hard restart (Quirk #26) |
| Switched to a different UEFN project | Hard restart (`tb` is undefined) |
| Editor crashed or aborted mid-run | Hard restart (stale C++ state) |
| Nuclear reload ran but old code is still executing | Hard restart |
| `Shiboken` in crash stack | Hard restart |
| Changed `init_unreal.py` | Hard restart |
| Iterating on an existing tool | Nuclear reload is fine |

### Rule of Thumb

> Nuclear reload fixes **code**. Hard restart fixes **state**.
> If nuclear reload isn't working, the problem is state — restart UEFN.

---

## 28. `execute_console_command` Crashes UEFN When Called From a Qt Signal Handler (Discovered: March 2026)

### The Problem

Calling `unreal.SystemLibrary.execute_console_command(world, "CAMERA ALIGN")` (or any console command) **directly from inside a PySide6 signal handler** (e.g. a node's `clicked` signal, a button's `pressed` signal, or any other Qt callback) causes a **hard UEFN crash** — no Python traceback, the editor process terminates.

This happens because `execute_console_command` triggers the engine's full command-dispatch pipeline synchronously. When Qt is in the middle of dispatching a signal, the engine's command pipeline re-enters the Slate/input stack in a way that violates internal ordering assumptions, causing an access violation or stack corruption.

The crash is not obvious: it doesn't produce a Python exception. UEFN just disappears. Wrapping the call in `try/except` does **not** help because the crash happens at the C++ level before any Python error can be raised.

### Affected APIs

Any API that triggers an internal engine dispatch synchronously can exhibit this pattern:
- `unreal.SystemLibrary.execute_console_command()`
- `unreal.EditorLevelLibrary.set_level_viewport_camera_info()` — causes camera roll corruption (separate but related)
- Potentially any API that modifies Slate/viewport state

### The Fix — Defer via `register_slate_pre_tick_callback`

Defer the console command to the next Unreal tick. The Slate pre-tick fires on the main editor thread, outside of Qt's signal dispatch, so the engine command pipeline has no re-entrancy conflict:

```python
def _on_node_clicked(self, nd: DeviceNode) -> None:
    # Select the actor synchronously — this is safe
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    sub.set_actor_selection_state(nd.actor, True)

    # ❌ CRASHES — do NOT call execute_console_command directly here
    # unreal.SystemLibrary.execute_console_command(world, "CAMERA ALIGN")

    # ✅ SAFE — defer to next Slate tick
    _fired = False
    def _align(dt: float) -> None:
        nonlocal _fired
        if _fired:
            return
        _fired = True
        try:
            unreal.SystemLibrary.execute_console_command(
                unreal.EditorLevelLibrary.get_editor_world(), "CAMERA ALIGN"
            )
        except Exception:
            pass
        finally:
            unreal.unregister_slate_pre_tick_callback(_handle)
    _handle = unreal.register_slate_pre_tick_callback(_align)
```

The `_fired` guard prevents double-fire if for any reason the callback fires before `_handle` is assigned (extremely unlikely but defensive).

### Why `register_slate_pre_tick_callback` (not post-tick)

Pre-tick fires at the beginning of each frame, before Slate processes input. This ensures the camera command runs in a clean frame context. Post-tick fires after Slate, which introduces one extra frame of delay and can cause visible "snap" artifacts.

### Where This Pattern Is Used in Toolbelt

- `tools/verse_device_graph.py` — `_on_node_clicked` snaps the UEFN viewport to the clicked device actor
- `tools/viewport_tools.py` — `_camera_align_to_actors()` helper used by all spawn tools with `focus=True`

### Rule of Thumb

> Any `execute_console_command` call that originates from a Qt signal (button click, combo change, timer tick, etc.) **must** be deferred via `register_slate_pre_tick_callback`. The same applies to any engine API that touches Slate or viewport state.

---

## Quirk #29 — Verse Device Graph Hard Crash Clears on Full UEFN Restart (Discovered: March 2026)

If `verse_graph_open` hard-crashes UEFN and the crash persists after nuclear reload, **do a full UEFN restart**. This is a specific instance of Quirk #27.

The graph window creates multiple Slate tick callbacks, Qt timers, and PySide6 widgets. After a crash or a project switch, stale C++ references from the previous session can make even a freshly-deployed version of the file crash on open. Nuclear reload purges the Python module but cannot clean up those C++ handles — only a full restart does.

After restart, use the full import form:
```python
import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("verse_graph_open")
```

---

## 30. Claude Code Agent Worktrees Showing as a Third Repo in VS Code

**What you see:** VS Code Source Control shows a third repository entry (e.g. `agent-ae5015a9`) alongside `UEFN-TOOLBELT` and `verse-book`. It has modified files inside it and no sync/push button visible on the main repo.

**Why it happens:** When Claude Code runs a task using the `isolation: "worktree"` agent mode, it creates a temporary git worktree at `.claude/worktrees/<agent-id>/`. This is a fully functional git branch isolated from your working copy. If the agent makes no changes, the worktree is cleaned up automatically. If it does make changes (or the task is interrupted), the directory is left behind. VS Code detects any directory containing a `.git` file as a repo and surfaces it in Source Control.

**How to fix it:**

```bash
# List all worktrees — the stale one will show a branch like worktree-agent-xxxxx
git worktree list

# Remove it (--force needed if it has uncommitted changes)
git worktree remove --force .claude/worktrees/agent-ae5015a9
```

Or remove all leftover agent worktrees at once:
```bash
git worktree prune
```

**Already handled:** `.claude/worktrees/` is in `.gitignore` so worktree directories never accidentally get committed. But you still need to `git worktree remove` to delete the directory from disk and make VS Code stop showing it.

**This is a Claude Code behavior, not a VS Code or UEFN quirk.** It only appears when agent-mode tasks run. Regular Claude Code sessions (no `isolation: "worktree"`) never create these.

