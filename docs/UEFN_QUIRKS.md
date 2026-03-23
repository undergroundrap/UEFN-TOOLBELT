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
