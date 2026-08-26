# UEFN Toolbelt — Claude Code Context

> This file is automatically loaded by Claude Code when you open this project.
> It gives Claude full knowledge of the UEFN Toolbelt so you can use natural language
> to control UEFN without looking up tool names or parameters.

<!-- last full audit: v2.4.1 — 2026-08-23 -->

---

## ⚠️ MANDATORY: Test in UEFN Before Every Commit

**Never commit code that hasn't been verified live in the UEFN editor.**
This is the single most important rule in this project. Syntax checks and unit tests catch Python errors but cannot catch UEFN runtime failures (wrong unreal API calls, Slate tick issues, editor crashes, invisible windows, etc.).

### When to ask the user to test

> **Every test starts with `deploy.bat`.** Without it, UEFN is running old code.

| Change type | Required test |
|---|---|
| Any code change | **`deploy.bat` first**, then the appropriate step below |
| New tool or tool modification | `deploy.bat` → nuclear reload → `tb.run("tool_name")` |
| Dashboard UI change (new tab, widget, layout) | `deploy.bat` → **full UEFN restart** → visual inspect |
| Theme / styling change | `deploy.bat` → **full UEFN restart** → switch themes in Appearance tab |
| `verse_device_graph.py` or `dashboard_pyside6.py` | `deploy.bat` → **full UEFN restart** (nuclear reload will crash) |
| MCP bridge change | `deploy.bat` → **full UEFN restart** → `tb.run("mcp_start")` + authenticated external ping |
| `core/` module change | `deploy.bat` → nuclear reload → `tb.run("toolbelt_smoke_test")` |
| `install.py` / `deploy.bat` change | Run the script end-to-end |
| Launch Session / Push Changes / publish | `prepare_launch.bat` → upload → `restore_after_launch.bat` |
| Any change touching PySide6 windows | `deploy.bat` → **full UEFN restart** → open window, interact |

> **UEFN 42.00 upload rule:** the `VKCreateUGC` role rejects every `.py` anywhere
> under the project root. `.urcignore` does not affect Valkyrie module staging,
> and Fortnite may open before the remote failure arrives. Always run
> `prepare_launch.bat` before Launch Session / Push Changes / publish and
> `restore_after_launch.bat` after validation. See Quirk #42.

### Two-phase validation workflow

Every code change goes through two phases before committing:

**Phase 1 — Static gates (run immediately, outside UEFN):**

One-time setup: `python -m pip install -r requirements-dev.txt`

```bash
python -m ruff check . && python -m mypy && python -m pytest && python scripts/drift_check.py
```

This is the fast gate — it needs no editor and runs in about a second. It is the
same set CI enforces on every PR (`.github/workflows/ci.yml`):

| Gate | Catches |
|---|---|
| `ruff check .` | undefined names, unused imports, bugbear traps, import order |
| `mypy` | type errors in the typed island (`registry.py`, `core/`, `scripts/`) |
| `pytest` | registry/config contracts, repo integrity, API-manifest freshness |
| `scripts/drift_check.py` | stale version / tool-count / category-count references |

`pytest` runs outside UEFN because `tests/conftest.py` installs a fake `unreal`
module. That covers pure-Python logic only — it proves nothing about editor
behaviour, which is what Phase 2 is for.

**If you added or removed any `unreal.*` call**, regenerate the API dependency
manifest or CI will fail:
```bash
python scripts/gen_api_manifest.py
```

**Ruff config notes** (see `pyproject.toml` for the full rationale): `ruff format`
is deliberately not used — it would destroy the hand-aligned assignment columns.
`E741`/`SIM102`/`SIM108`/`SIM117` are ignored as *ratchet targets*: they are real
pre-existing violations left alone because fixing them restructures control flow,
which requires a live UEFN test. Fix them in a separate, tested PR.

When you add a new tool, bump `__tool_count__` in
`Content/Python/UEFN_Toolbelt/__init__.py`, and bump `__category_count__` if the
category is new. Do **not** bump `__version__` during an ordinary implementation
or community PR: version changes belong to a separately authorized release
session. All three constants are read by `drift_check.py` as ground truth.

**Phase 2 — Deploy + live UEFN test (required before every commit):**

> **⚠️ ALWAYS run `deploy.bat` before testing in UEFN.**
> The repo and the UEFN project are separate directories. Editing files in the repo does nothing
> until you deploy. `deploy.bat` copies everything to your Fortnite Projects folder and prints
> the correct hot-reload command. Never skip this step.

```bat
deploy.bat
```

Then paste the hot-reload command it prints into the UEFN Python console. Syntax passing ≠ working in the editor.

### The hard refresh bundle (paste into UEFN Python console)

> ⚠️ **Nuclear reload is unsafe when adding a NEW module to `tools/__init__.py`.**
> It can cause `EXCEPTION_ACCESS_VIOLATION` as stale C++ callbacks fire against freed Python objects.
> **Use a full UEFN restart instead** when first introducing a new tool module.
> Nuclear reload is safe for iterating on existing tools. See `docs/UEFN_QUIRKS.md` Quirk #26.
>
> ⚠️ **Nuclear reload is also unsafe for modules with active Qt windows or Slate tick callbacks**
> (e.g. `verse_device_graph.py`, `dashboard_pyside6.py`). If UEFN hard-crashes after a nuclear
> reload, close UEFN completely, run `deploy.bat` again, restart UEFN, then do a clean import.
> Nuclear reload is only safe for pure tool modules with no persistent window state.
>
> 🔁 **Nuclear reload fixes code. Hard restart fixes state.**
> After a crash, a project switch, or a `Shiboken` abort — close UEFN completely and reopen.
> `tb` is undefined after switching projects; always import fresh after a restart. See Quirk #27.

```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
```

Always ask the user to run this after UI or core changes. After a tool-only change, a simpler reload is enough:

```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("tool_name")
```

**Only commit after the user confirms it works in the live editor.**

### Review and publication authority gates

Passing tests or receiving live confirmation does not authorize distribution:

1. Implementation stops with the complete worktree uncommitted for independent
   review unless the owner explicitly authorized a different boundary.
2. After independent acceptance, the owner separately authorizes the exact
   commit. Stage only the reviewed paths; never stage the whole repository.
3. A commit does not authorize a push. Push only after a separate owner go
   signal, then inspect every required CI job through a terminal conclusion.
4. A push does not authorize a tag. A tag does not authorize a GitHub Release.
5. A GitHub Release does not authorize a social announcement. Each public action
   requires its own explicit owner approval.

Never move an existing release tag to include later documentation or fixes.
Follow-up work belongs on `main` and, when warranted, in a later version.

### Repository Work Order memory

Cold-start every repository task from [`WORKORDER.md`](WORKORDER.md) after this
file. It is the sole authority pointer allowed to name the current issued Work
Order and authorized session. A roadmap entry, audit finding, chat instruction
quoted as background, or file under `docs/work-orders/proposed/` is not a go
signal. If the current issued Work Order or authorized session is `NONE`, stop
at that owner gate.

Detailed state definitions and mandates live in
[`docs/work-orders/`](docs/work-orders/README.md). Proposed mandates always say
`AUTHORIZATION: NOT AUTHORIZED`; normally at most one mandate is issued. Moving
a file does not combine implementation, independent review, commit, push, tag,
GitHub Release, repository-description, or social-publication authority.

Security-sensitive work must also cold-start from [`SECURITY.md`](SECURITY.md).
The accepted official-MCP inventory, autonomous/manual execution ledger, live
evidence, evidence gaps, and cleanup state are preserved in the
[`2026-08-24 UEFN 42.00 audit`](docs/audits/2026-08-24-uefn-42-official-mcp-audit.md).

---

## ⚠️ MANDATORY: Check the Registry Before Adding Any Tool

**Never build a new tool without first auditing what already exists.**
With 362 registered tools, the risk of duplicating or fragmenting existing functionality is high.
A new tool that overlaps an existing one wastes time, inflates the count, and confuses users.

### Pre-build checklist — required before writing a single line of tool code

**Step 0 — Full tool list in 5 seconds (no UEFN needed, run from repo root):**
```bash
grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
  | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort
```
This dumps every registered tool name alphabetically. Search the output before writing anything. This is the authoritative list — faster and more complete than reading CLAUDE.md tables.

To filter by keyword:
```bash
grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
  | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort | grep scatter
```

1. **Search the registry by keyword (UEFN console):**
   ```python
   for t in tb.registry.list_tools():
       if "scatter" in t["name"] or "scatter" in t.get("description","").lower():
           print(t["name"], "—", t["description"])
   ```

2. **Check the manifest for related tools:**
   ```python
   tb.run("plugin_export_manifest")
   # Read Saved/UEFN_Toolbelt/tool_manifest.json — search by name, category, and tags
   ```

3. **Read the CLAUDE.md tool tables** — every tool family has a table in this file.
   Search for the capability you want to add before writing anything.

4. **Ask: can an existing tool be extended with a new param?**
   Adding `dry_run=True` or `scope="selection"` to an existing tool is always better
   than a second tool that does 90% of the same thing.

### The rule

> If a tool already does it — extend it, don't duplicate it.
> If a tool does 80% of it — extend it with the missing 20%.
> Only create a new `@register_tool` when the capability is genuinely new.

This keeps the tool count honest, the dashboard scannable, and the MCP manifest small enough for AI agents to reason over.

---

## What This Project Is

**UEFN Toolbelt** is a comprehensive Python automation framework for Unreal Editor for Fortnite (UEFN 40.00+, March 2026).
It covers ~97% of the UEFN Python API surface (the remaining 3% is locked by Epic — heightmap editing,
Blueprint graph nodes, Verse compiler trigger, match control, session launch/stop, and V2 device game-logic properties have no Python API yet).
It runs inside the editor and exposes 362 tools through:
- A persistent top-menu entry (`Toolbelt ▾`) in the UEFN editor bar
- A 26-tab PySide6 dark-themed dashboard (`tb.launch_qt()`)
- An MCP HTTP bridge so Claude Code can control UEFN directly
- A Python client library (`client.py`) for non-MCP scripts

## UI Consistency Rule (Enforced)

> **Any PySide6 window opened by any tool, plugin, or AI-generated feature MUST match the
> dashboard theme exactly.**
> Read `docs/ui_style_guide.md` before writing any windowed UI.
> The short version:
> 1. Subclass `ToolbeltWindow` from `core/base_window.py` — theme + Slate tick are automatic
> 2. **Window title format is mandatory:** `"UEFN Toolbelt — Tool Name"`. Always. Help dialogs: `"UEFN Toolbelt — Tool Name Help"`. Sub-dialogs: `"UEFN Toolbelt — Action Name"`. Never omit the prefix — every OS title bar and taskbar entry must read as Toolbelt.
> 3. Only use hex values from the palette in that guide — no purple, no navy, no off-whites
> 3. **NEVER add `make_topbar()` unless it carries multiple real toolbar buttons** (scan, export, filter, etc.). The OS title bar set via `title=` already shows the window name. A topbar whose only content is a title label + stretch (even with one small utility button like `?`) is redundant visual noise — remove it. This applies to main windows AND sub-dialogs (help, edit, confirm). If in doubt: does removing the topbar lose any functionality? If no → remove it.
> 4. **Every tool window must have a `?` help button** that opens a `_HelpDialog(ToolbeltWindow)`. No exceptions. If the window has a topbar → `?` goes last on the right. If no topbar → `?` goes in the bottom action row right-aligned. See `docs/ui_style_guide.md` for the exact pattern.
> 5. For read-only text areas (help dialogs, logs): always set `editor.setLineWrapMode(QTextEdit.NoWrap)` — otherwise separator lines and fixed-width content wrap and break the layout.
> 6. Reference implementation: `tools/verse_device_graph.py` (main window has topbar with 8+ toolbar buttons — that earns it)
> 7. **`run_*` functions that open windows MUST use this exact pattern — no exceptions:**
>    ```python
>    from PySide6.QtWidgets import QApplication
>    QApplication.instance() or QApplication([])   # BEFORE _build_*()
>    if _win is None or not _win.isVisible():
>        _win = _build_my_window()
>        _win.show_in_uefn()                       # not show()
>    else:
>        _win.raise_(); _win.activateWindow()
>    ```
>    Missing the `QApplication` guard crashes UEFN (access violation before any widget can be created). Using plain `show()` instead of `show_in_uefn()` leaves the window without a Slate tick — unresponsive or unstable outside the dashboard. See `docs/UEFN_QUIRKS.md` Quirk #31 and `tools/smart_organizer.py` → `run_organize_open` for the reference implementation.

---

## High-Fidelity Schema (The Gospel)
The project uses a **Hybrid Schema** model for AI context:
- **Reference Schema**: `docs/uefn_reference_schema.json` (The Gospel). A 1.6MB baseline reference for all core UEFN/Fortnite classes.
- **Project-Specific Schema**: `docs/api_level_classes_schema.json` (The Brain). Generated by clicking the **"Sync Level Schema"** button in the dashboard. This file is git-ignored and contains your unique level context.
- **Workflow**: Consult the **Live Schema** first for project-specific Verse devices, and the **Reference Schema** for standard UEFN properties.
- **Update**: Use the Dashboard button whenever you add new Verse devices to sync the AI's understanding instantly.

## Tool Manifest (Phase 20 — AI-Agent Readiness)
Run `tb.run("plugin_export_manifest")` to generate `Saved/UEFN_Toolbelt/tool_manifest.json`.
This file contains every registered tool with its full Python parameter signatures and a concrete `example` call string:
```json
{
  "verse_write_file": {
    "name": "verse_write_file",
    "category": "Verse Helpers",
    "description": "Write Verse code directly into the project's Verse source directory...",
    "parameters": {
      "filename": {"type": "str", "required": false, "default": ""},
      "content":  {"type": "str", "required": false, "default": ""},
      "overwrite": {"type": "bool", "required": false, "default": false}
    },
    "example": "tb.run(\"verse_write_file\", filename=\"game_manager.verse\", content=verse_code, overwrite=True)"
  }
}
```
All 362 tools (100%) return `{"status": "ok"/"error", ...}` structured dicts as of Phase 21. Zero `None` returns remain in the codebase — MCP callers can read every result directly without parsing log output.

**Schema utility functions** (`schema_utils.py`):
- `schema_utils.validate_property(class_name, prop)` — check if a property exists and is writable
- `schema_utils.discover_properties(class_name)` — return all schema-known properties for a class
- `schema_utils.list_classes()` — return all class names in the reference schema
- `schema_utils.get_class_info(class_name)` — full class definition dict

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
5. **Path format** — asset paths use forward slashes. In standard UE5 docs paths start with `/Game/`, but **in UEFN the Content Browser mount point is the project name** (e.g. `/Device_API_Mapping/`). `AssetData.package_name` returns the project-mount form. Never force-prepend `/Game/` to paths from the Asset Registry or Content Browser selection. **All three `Paths` disk functions are wrong in UEFN:** `project_content_dir()` → FortniteGame engine path; `project_dir()` → `../../../FortniteGame/` (relative engine dir); `project_saved_dir()` → editor-level saved dir, not project. **The only reliable method is to walk up from `__file__`** — every tool lives inside `[Project]/Content/Python/...` so walking up until you hit a folder named `Content` gives the real content dir. See `docs/UEFN_QUIRKS.md` Quirk #23.

   **Detecting the project mount point** — never take the first alphabetical non-engine mount. Epic plugin mounts (`ACLPlugin`, `AnimationWarping`, etc.) sort before user project mounts. Always use the **"most paths" approach** — the user's project has far more content than any plugin:
   ```python
   counts = {}
   for p in unreal.AssetRegistryHelpers.get_asset_registry().get_all_cached_paths():
       root = p.strip("/").split("/")[0]
       if root and root not in _SKIP_MOUNTS:
           counts[root] = counts.get(root, 0) + 1
   mount = max(counts, key=counts.get) if counts else "Game"
   ```
   Canonical implementation: `core/__init__.py` → `detect_project_mount()`. Import it with `from ..core import detect_project_mount`. Never reimplement this per-tool.
6. **Vectors/Rotators** — `unreal.Vector(x, y, z)` · `unreal.Rotator(roll=, pitch=, yaw=)` **keyword args only**
   Pitch = tilt up/down · Yaw = rotate left/right · Roll = spin

   **Positional args are (roll, pitch, yaw), NOT (pitch, yaw, roll).** The
   constructor follows the C++ FRotator field order. `unreal.Rotator(0, yaw, 0)`
   sets *pitch*, not yaw, and nothing raises. Confirmed live on UEFN 42.00:
   `unreal.Rotator(10, 20, 30)` gives `roll=10 pitch=20 yaw=30`.

   The same applies to `unreal.Color` - FColor is declared (B, G, R, A), so
   `unreal.Color(r, g, b, 255)` swaps red and blue. `unreal.Vector` (X, Y, Z)
   and `unreal.LinearColor` (R, G, B, A) are declared as expected and are safe.

   Rule: any `unreal.*` struct built positionally is a bet on C++ field order.
   Use keyword args. See `docs/UEFN_QUIRKS.md` Quirk #41 and
   `tests/test_rotator_argument_order.py`, which fails the build if this returns.

---

## Git Etiquette (High Priority)

> **STOP — did you test in UEFN?**
> See the "MANDATORY: Test in UEFN Before Every Commit" section at the top of this file.
> No exceptions. Syntax passing ≠ working. Only commit after the user confirms it works live.

- **Format**: `type(scope): concise description` — Conventional Commits **with a
  scope**. This is enforced by the `commit-msg` hook in the machine-wide
  `core.hooksPath`; a commit without a scope is rejected.
- **Scope**: the area touched — `mcp`, `refauditor`, `dashboard`, `drift`,
  `arena`, `organizer`, `docs`, `ci`, `tests`. Lowercase, one word where possible.
- **Casing**: All lowercase. NO "Phase:", NO "Update:", NO Title Case.
- **Types**:
  - `feat`: New tools or capabilities
  - `docs`: Documentation, README, CLAUDE.md, Walkthroughs
  - `fix`: Bug fixes, registration errors, pathing issues
  - `refactor`: Internal code structure, no behavior changes
  - `test`: Updates to integration/smoke tests
  - `perf`: Performance optimizations (CPU/Memory)
- **Example**: `docs(readme): update the 8 pillars section`
- **Live-verification trailer (enforced)**: any commit touching
  `Content/Python/` must carry one of:
  ```
  Verified-Live: <what you ran in UEFN and what you saw>
  Live-Verification: not-required — <reason>
  ```
  A `pre-push` hook blocks the push otherwise. It cannot check UEFN itself — it
  forces the claim to be made rather than skipped. Local tests passing is not
  evidence: the material tools were green while every one of them applied the
  wrong material. Bypass with `git push --no-verify` only when you mean it.
- **Note**: commits before v2.3.7 use the older unscoped `type: description`
  form. History is not being rewritten — the scope requirement applies going
  forward.

---

## The Industrialization Pipeline — How Claude Builds a Full Game

> Full reference: **[docs/PIPELINE.md](docs/PIPELINE.md)** — read this before starting any
> autonomous build task. It has every tool, every phase, Claude's execution script, and
> the recursive error loop in detail.

The 6-phase pipeline for autonomous UEFN game development:

```
PHASE 0 — SETUP                   ✅
  scaffold_generate                → folder structure from template
  organize_assets                  → sort loose assets by type

PHASE 1 — RECONNAISSANCE          ✅
  world_state_export               → every actor in the level (transforms + properties)
  device_catalog_scan              → 4,698 Creative devices available to place
  api_crawl_level_classes          → Python property schema for every class in level
  verse_find_project_path          → locate the correct Verse source directory

PHASE 2 — DESIGN                  ✅ (Claude reasoning, no tool calls)
  Read world_state.json + device_catalog.json
  Select game mode, devices, win condition, round flow

PHASE 3 — PLACEMENT               ✅
  spawn_actor (MCP)                → place devices from catalog asset paths
  set_actor_transform (MCP)        → position them
  device_set_property              → configure base-class properties
  device_call_method               → call V2 runtime methods

PHASE 4 — CODE GENERATION         ✅
  verse_gen_game_skeleton          → full creative_device Verse stub
  verse_gen_device_declarations    → @editable refs from live level actors
  verse_write_file                 → deploy to project Verse source directory
  [PROVEN: 6187 bytes, VerseBuild SUCCESS, first attempt — March 22 2026]

PHASE 5 — BUILD + FIX LOOP        ✅ (one human click per iteration)
  [User clicks Build Verse]
  verse_patch_errors               → errors + file content → Claude fixes → redeploy
  LOOP until build_status == "SUCCESS"
  system_build_verse               → ⏳ waiting for Epic Python compiler API (headless)

PHASE 6 — VERIFY                  ✅
  world_state_export               → confirm level matches design intent
  snapshot_save                    → checkpoint before publishing

KNOWN HARD LIMITS (Epic must unlock):
  ✗ V2 device game-logic properties (duration, score, team index) — Verse @editable only
  ✗ Verse compiler trigger from Python — subprocess approach unreliable in sandbox
  ✗ Session launch/stop from Python — no API exposed
```

**Claude's quick-start execution script:**
```python
tb.run("device_catalog_scan")        # Phase 1: full device palette
tb.run("world_state_export")         # Phase 1: current level state
# [Phase 2: Claude reasons and designs]
tb.run("verse_write_file", filename="game_manager.verse", content=verse, overwrite=True)
# [Phase 5: User clicks Build Verse]
result = tb.run("verse_patch_errors")  # read errors + file content
# [Claude fixes → verse_write_file → repeat until SUCCESS]
tb.run("snapshot_save", name="v1")   # Phase 6: checkpoint
```

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

When Epic's **UEFN MCP Toolsets** beta is enabled, Quirk #36 may prevent
`init_unreal.py` from registering Toolbelt at startup. If `mcp_start` reports
only one loaded tool, recover once for that editor session and then start it:

```python
import UEFN_Toolbelt as tb; tb.register(); tb.run("mcp_start")
```

Then restart Claude Code — it connects automatically.

The listener accepts only authenticated same-user loopback POSTs. It rotates a
session secret on every restart, hands it to `mcp_server.py` through the local
`Saved/UEFN_Toolbelt/mcp_session.json` file, rejects browser origins/CORS, and
never returns or logs the secret. If Slate queued dispatch cannot register, the
listener fails closed and does not start.

### What Claude Code can now do

- Run registered tools by name (`mcp_start`, `mcp_stop`, and `mcp_restart`
  remain local-only lifecycle controls)
- Spawn, move, delete actors
- List/rename/import/tag assets
- Take screenshots, save level snapshots
- Read and write actor/asset properties

Arbitrary remote Python is unavailable through the Toolbelt bridge. Use a
registered command for remote automation or the local UEFN Python console for
deliberate in-editor scripting.

---

## Building Custom Plugins

Users can create third-party tools without forking this repository.
1. Create a `.py` file with a `@register_tool` decorated function.
2. Place it in `[Project]/Saved/UEFN_Toolbelt/Custom_Plugins/`.
3. It will auto-load on start and show up in the Dashboard.
See `docs/plugin_dev_guide.md` for full details. You can generate plugins for the user directly into this folder when requested!

**Security:** Every plugin passes through a four-gate security model:
1. **File size limit** — rejects files > 50 KB (blocks obfuscated payloads)
2. **AST import scanner** — parses source without executing; blocks `subprocess`, `socket`, `ctypes`, network libs
3. **Namespace protection** — custom plugins cannot overwrite core Toolbelt tools
4. **SHA-256 integrity hash** — every loaded plugin's fingerprint is written to `plugin_audit.json`

---

## Running Tools — The Main Interface

> [!WARNING]
> **`import UEFN_Toolbelt as tb` alone does NOT register any tools.**
> A bare import only loads the package root — the registry is empty until you call
> `tb.register_all_tools()`. If `tb.run("anything")` returns "Unknown tool", this is why.
> Always use one of the nuclear reload one-liners below, or call `tb.register_all_tools()`
> explicitly after any fresh import.

```python
import UEFN_Toolbelt as tb
tb.register_all_tools()   # ← required — registers all 362 tools

# Basic
tb.run("tool_name")
tb.run("tool_name", param1=value1, param2=value2)

# Health check
tb.smoke_test()

# List everything available
for t in tb.registry.list_tools():
    print(f"{t['category']:20s} {t['name']}")

### **The "Nuclear Reload" Command**
If you have modified the Toolbelt source code, run this in the UEFN console to refresh everything without a restart.

> **When does `tb` already exist vs. when do you need to import?**
> - Same project, same session → `tb` is already defined; nuclear reload refreshes it
> - Switched to a different project → Python environment resets; `tb` is gone — run the full import line
> - Fresh UEFN launch → always import first
> - Rule of thumb: `NameError: name 'tb' is not defined` → run the full reload line below

```python
# Standard — reload + open dashboard
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()

# Iterating on the Verse Device Graph window
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("verse_graph_open")

# Reload + run integration tests (use a clean template level)
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_integration_test")

# Reload + smoke test only
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_smoke_test")

# Reload only (no UI — useful when testing tools that don't need the dashboard)
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools()
```
> [!IMPORTANT]
> Always include `tb.register_all_tools()` after a pop, otherwise the tool registry will be empty!

---

## Testing: Smoke Test vs Integration Test

Two separate test systems. Know which is which before running either.

### Smoke Test — `tb.run("toolbelt_smoke_test")`
**What it proves:** All 362 tools *registered* correctly. The registry loaded, all modules imported, and a set of "safe" tools ran end-to-end without exceptions.
**What it does NOT prove:** That tools produce correct output on real actors. It cannot test anything selection-dependent or level-state-dependent.
**Safe to run:** Anywhere, any project, any time. ~5 seconds.
**Run after:** Every code change, before committing.

### Integration Test — `tb.run("toolbelt_integration_test")`
**What it proves:** tools *work* in a live UEFN editor. The harness spawns real actor fixtures, runs each tool against them, verifies the result (property changed, actor count correct, file written), and cleans up.
**Coverage:** 116 test sections, **190 checks, 190/190 live on UEFN 42.00** — materials, bulk ops, patterns, scatter, zones, stamps, actor org, proximity, alignment, signs, post-process, audio, lighting, world state, and more.

> **Read the split, not the total.** 163 of the 190 verify a real outcome; **27
> are execution-only** — they prove the tool ran without raising, nothing more.
> The suite prints both on every run. A check that cannot fail is not coverage:
> counting all of them as one number is what let Quirk #41 (wrong rotator axis)
> sit inside a fully green run. When you add a check, assert on a returned
> value or re-read the state — `_record(..., True)` is a last resort and must
> pass `verified=False`.
**⚠️ INVASIVE — only run in a blank template level.** It spawns and deletes actors. Never run in a production project.
**Run after:** Before any PR. After adding a new tool. After major refactors. ~70 seconds.

```
Results: Saved/UEFN_Toolbelt/integration_test_results.txt
```
If the editor crashes mid-run, the file contains partial results up to the last completed test — check it to find which section caused the crash.

| | Smoke Test | Integration Test |
|---|---|---|
| Tests registration? | ✅ All 362 tools | ✅ |
| Tests live execution? | Partial (safe tools only) | ✅ 190 checks on real actors (163 verified, 27 execution-only) |
| Safe in production? | ✅ Yes | ❌ Blank level only |
| Runtime | ~5s | ~70s |
| Run when? | After every change | Before every PR |

---

## ⚠️ V2 Device Property Wall — Critical for AI Autonomy

Fortnite V2 Creative devices (Timer Device, Capture Area, Score Manager, Guard Spawner, etc.)
store their game-logic settings as Verse `@editable` properties — **not UPROPERTYs**.
`get_editor_property`, `set_editor_property`, and `getattr` all fail silently or raise exceptions.

**DO NOT attempt to set these via `device_set_property`:**
- Countdown duration, score-to-win, team index, channel assignments, enabled state
- Anything configurable in the device's Properties panel in the UEFN editor

**What Python CAN do on V2 devices:**
- Read base-class props: `actor_guid`, `allow_highlight`, `client_current_state`, `net_priority`
- Call methods: `timer_start()`, `timer_pause()`, `timer_resume()`, `timer_set_state()`
- Move/delete/spawn (transforms always work)

**How to configure V2 devices programmatically (two paths):**

1. **Method calls** — `tb.run("device_call_method", class_filter="Timer", method="timer_start")`
2. **Verse code** — generate a `creative_device` with `@editable` refs that configures at `OnBegin`:
   ```verse
   @editable TimerDevice : timer_device = timer_device{}
   OnBegin<override>()<suspends> : void =
       TimerDevice.SetDuration(120.0)
       TimerDevice.Enable()
   ```
   Use `verse_gen_game_skeleton` to scaffold — Claude fills in the configuration block.

Full technical breakdown: `docs/UEFN_QUIRKS.md` Quirk #19, `docs/FORTNITE_DEVICES.md`.

---

## ⚠️ Development Quirks & "Main Thread Lock"

UEFN's Python execution environment has a critical architectural quirk: **The Main Thread Lock**.

### **Async Operations (Like Screenshots)**
If you call an asynchronous Unreal API (e.g., `unreal.AutomationLibrary.take_high_res_screenshot` or anything that says "queued"):
*   **The Problem**: The operation will NOT finish as long as your Python script is running. 
*   **The "Wait" Trap**: If you use `time.sleep()` to wait for a file, you are **deadlocking the engine**. Unreal needs the main thread to be free (yielded) to process its frame and write the file.
*   **The Fix**: Do not wait for files in the same script. Trigger the action, verify the request was sent, and exit. The file will appear ~1 second after the user's console command finishes.

### Common Pitfalls
- **ModuleNotFoundError on new projects**: UEFN only scans `Content/Python` on startup. If you deploy to a new project while the editor is open, restart UEFN.
- **Hot Reload vs Restart**: Use the "Nuclear Reload" for code changes, but a full restart for `init_unreal.py` changes.

### **Hot-Reloading (sys.modules)**
UEFN does not natively reload modified Python modules. Use the **"Nuclear Reload"** (provided in `README.md`) to clear `sys.modules` and force a fresh import of Toolbelt logic.

---


---

## Compact Instructions

When compacting this conversation, always preserve:
- Current `__version__` and `__tool_count__` and `__category_count__` values from `Content/Python/UEFN_Toolbelt/__init__.py`
- Names and registration names of any tools added or modified this session
- Any UEFN quirk numbers encountered and the root cause discovered
- Exact Python syntax errors and their fixes
- Which tools were confirmed working in live UEFN (user pasted log output)
- Whether `deploy.bat` was run and whether the nuclear reload was done
- Any Epic API limitations newly discovered
- Current git branch and last commit hash

Never drop: tool counts, version numbers, live test confirmations, or quirk numbers.
Always include full code snippets for any newly added `@register_tool` functions.

---

@./.claude/tool_tables.md

---

@./.claude/mcp_reference.md
