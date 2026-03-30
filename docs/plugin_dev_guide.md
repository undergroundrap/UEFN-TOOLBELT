# UEFN Toolbelt Custom Plugin Guide

Welcome to the ultimate leverage. 

Because UEFN Toolbelt provides a **Native PySide6 UI**, **Undo-Safety**, **MCP (Claude) Integration**, and massive API helpers, you should never have to build a standalone python script with hardcoded paths ever again.

By writing a **Custom Plugin**, you can add your own completely custom tools to the Toolbelt's interactive dashboard in seconds. When you drop your plugin file into the right folder, the Toolbelt will automatically load it, render a customized UI button for it, map it for AI to use via MCP, and handle error logging.

---

## 🔍 Before You Write a Plugin — Check What Already Exists

UEFN Toolbelt ships with 355 built-in tools across 54 categories. Before writing a plugin,
spend two minutes confirming the capability doesn't already exist.

**Quick registry search (paste into UEFN console):**
```python
import UEFN_Toolbelt as tb
for t in tb.registry.list_tools():
    if "rename" in t["name"] or "rename" in t.get("description","").lower():
        print(t["name"], "—", t["description"])
```

**Or export the full manifest and search it:**
```python
tb.run("plugin_export_manifest")
# → Saved/UEFN_Toolbelt/tool_manifest.json — search name, description, tags
```

If a built-in tool does 80% of what you need, open a PR to extend it with a new parameter
instead of shipping a separate plugin. Keeps the ecosystem lean.

---

## 🚀 The 60-Second Plugin

1. Navigate to: `[Your UE Project]/Saved/UEFN_Toolbelt/Custom_Plugins/`
   *(If the `Custom_Plugins` folder doesn't exist yet, simply create it)*.
2. Create a new `.py` file, for example: `my_first_plugin.py`
3. Paste the following skeleton code and save it:

```python
# Declare the minimum Toolbelt version your plugin requires.
# If a user has an older version, they'll see a warning in the Output Log.
MIN_TOOLBELT_VERSION = "1.5.3"

from UEFN_Toolbelt.registry import register_tool
from UEFN_Toolbelt import core

@register_tool(
    name="my_custom_renamer",
    category="My Custom Tools",
    description="Renames all selected actors to have a cool prefix.",
    tags=["rename", "custom", "fun"],
    author="John Doe",
    version="1.0.0",
    url="https://github.com/johndoe/my_custom_renamer",
    last_updated="2026-03-22"
)
def run(**kwargs) -> dict:

    # 1. Ask the toolbelt core for the current viewport selection
    actors = core.require_selection()
    if not actors:
        # Always return a dict — even on early exit
        return {"status": "error", "renamed": 0}

    # 2. Wrap everything in an undo transaction!
    with core.undo_transaction("Apply Cool Prefix"):
        count = 0
        for i, actor in enumerate(actors):
            old_name = actor.get_actor_label()
            new_name = f"Cool_{old_name}_{i}"
            actor.set_actor_label(new_name)
            count += 1

        # 3. Trigger a green toast notification in the UI
        core.notify(f"Success! Renamed {count} actors.")

    # 4. Return a structured dict — AI agents and MCP callers read this directly
    return {"status": "ok", "renamed": count}
```

4. Switch back to UEFN. You don't even need to restart! Just close the Dashboard and re-open it via `Toolbelt ▾ -> Open Dashboard`. 
5. You will see a brand new **"My Custom Tools"** tab containing a clickable button for your tool.

---

## 📦 The Structured Return Contract

Every registered tool — including your custom plugin — **must return a `dict`**. This is not just a style guide; it's the contract that makes every tool readable by AI agents via the MCP bridge.

### Why It Matters

When your tool runs via `tb.run("my_custom_renamer")` in the REPL, the return value is just for you. But when an AI agent calls your tool through the MCP bridge, the return dict is serialized to JSON and sent back — it's how the AI knows what happened without parsing log output.

### The Pattern

```python
# ✅ Good — machine-readable
return {"status": "ok", "renamed": count, "folder": folder_name}

# ✅ Good — error case
return {"status": "error", "renamed": 0}

# ❌ Bad — returns None; AI has no idea what happened
return

# ❌ Bad — returns a primitive; not extensible
return count
```

### Standard Keys

| Key | Required | Value |
|---|---|---|
| `"status"` | **Always** | `"ok"` or `"error"` |
| Domain keys | When useful | Counts, paths, lists of names |

**Tip:** Include a `"count"` key for any tool that creates/modifies/deletes things, and a `"path"` key for any tool that writes a file. These are the fields AI agents query most.

---

## 🩺 Validating Your Plugin

If your tool doesn't show up, or you want to make sure you followed our schema correctly, use the built-in validators:

1. Open the Toolbelt Dashboard.
2. Go to the **Utilities** tab.
3. Click **plugin_validate_all**.
4. Check the **Output Log** in UEFN. It will flag if your plugin name has spaces in it, if you forgot a description, or if your function signature doesn't correctly accept `**kwargs`.

To see a list of all currently loaded third-party plugins, click **plugin_list_custom**.

---

## 🤖 AI & MCP Integration

Once the Toolbelt's MCP bridge is running (`tb.run("mcp_start")`), every registered tool — including your custom plugin — is instantly callable from Claude Code (or any MCP client) by name.

### Discovering Your Plugin via MCP

```bash
# From Claude Code, after connecting to the bridge:
# Ask it to describe your tool's parameter contract:
describe_tool my_custom_renamer
# Returns: name, description, tags, params with types/defaults

# Run it directly:
run_tool my_custom_renamer
```

### Exporting the Full Manifest

To give an AI agent a complete picture of all registered tools (including yours):

```python
# Inside UEFN:
tb.run("plugin_export_manifest")
# → Saves Saved/UEFN_Toolbelt/tool_manifest.json
# AI can load this file to discover every tool, every param, every default
```

### Using `describe_tool` Programmatically

From inside another plugin, you can look up any tool's manifest entry:

```python
import UEFN_Toolbelt as tb
manifest = tb.registry.to_manifest()
my_params = manifest.get("my_custom_renamer", {})
print(my_params)  # → {"name": ..., "description": ..., "parameters": {...}}
```

---

## 🤝 Distributing Your Plugin

Because custom plugins live in `Saved/UEFN_Toolbelt/Custom_Plugins/`, they are safely outside of the core Toolbelt installation (`Content/Python/UEFN_Toolbelt/`). You can update the Toolbelt without ever losing your custom tools.

### Path A — List in the Online Plugin Hub (recommended)

The Plugin Hub tab in the dashboard fetches a live registry from GitHub. Any developer can get their tool listed in under 5 minutes:

1. **Host your `.py` file** anywhere with a raw GitHub URL (your own repo works).
2. **Fork** `undergroundrap/UEFN-TOOLBELT`.
3. **Add an entry** to `registry.json` at the repo root:

```json
{
  "id": "my_cool_tool",
  "name": "My Cool Tool",
  "version": "1.0.0",
  "author": "Your Name",
  "author_url": "https://github.com/yourhandle",
  "type": "community",
  "description": "One sentence on what it does.",
  "category": "Gameplay",
  "tags": ["verse", "gameplay"],
  "url": "https://github.com/yourhandle/yourrepo/blob/main/my_cool_tool.py",
  "download_url": "https://raw.githubusercontent.com/yourhandle/yourrepo/main/my_cool_tool.py",
  "min_toolbelt_version": "1.5.3",
  "size_kb": 10
}
```

4. **Open a Pull Request** — once merged, your tool appears in every user's Plugin Hub on next Refresh.

Users install it with one click: the dashboard downloads the raw `.py` into their `Custom_Plugins/` folder. The four-gate security scanner runs automatically on load.

> **`download_url` rules:** must be a raw GitHub URL pointing to a single `.py` file ≤ 50 KB.
> No zips, no installers, no subfolders.

### Path B — Contribute to the Core Toolbelt

If you think your tool belongs in the 355 built-in tools:
1. Fork the UEFN-TOOLBELT repository.
2. Move your `.py` file into `Content/Python/UEFN_Toolbelt/tools/`.
3. Import it in `tools/__init__.py`.
4. Submit a Pull Request — we review for quality, security, and fit.

---

## 🎨 UI Style Requirements

If your plugin opens a PySide6 window, **it must match the dashboard theme exactly.**
Every window in the Toolbelt — built by Ocean, by the community, or generated by an AI —
must look and feel identical. This is what makes the platform feel professional.

**The short version — subclass `ToolbeltWindow`:**

```python
from PySide6.QtWidgets import QVBoxLayout, QLabel
from UEFN_Toolbelt.core.base_window import ToolbeltWindow

class MyPluginWindow(ToolbeltWindow):
    def __init__(self):
        super().__init__(title="My Plugin")   # theme + Slate tick automatic
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Hello from My Plugin!"))
        self.central.setLayout(layout)

# Open it — show_in_uefn() handles the Slate tick driver automatically
win = MyPluginWindow()
win.show_in_uefn()
```

`ToolbeltWindow` handles **everything automatically**: the dark theme, the Slate tick driver,
window sizing, and proper cleanup. You never need to manually call
`register_slate_post_tick_callback` or copy-paste QSS strings.

> **Do NOT** subclass `QMainWindow` directly, copy inline QSS, or wire up the Slate tick
> yourself — this leads to drift from the platform theme and invisible windows.

**Full palette, color rules, widget recipes, and the "what NOT to do" list are in
`docs/ui_style_guide.md`.** Read it once — it has copy-paste snippets for every widget type.

---

## ⚠️ Detecting the Project Mount Point (Read This Before Touching Any Path)

This is the single most common mistake plugin authors make in UEFN. Get it wrong and your
tool silently writes assets somewhere the user can never find them.

### Why `/Game/` is wrong

UEFN runs as a plugin inside FortniteGame. The `/Game/` mount exists and accepts asset
operations without error — but **it is invisible in the Content Browser**. Any asset you
write there disappears from the user's perspective.

### Why "first alphabetical non-engine mount" is also wrong

Epic ships dozens of plugin mounts alongside every UEFN project. Many sort alphabetically
**before** the user's actual project:

```
/ACLPlugin/          ← Epic Animation Compression Library — comes first alphabetically
/AnimationWarping/   ← another Epic plugin
/Device_API_Mapping/ ← the actual user project   ← YOU WANT THIS
```

Picking `candidates[0]` returns `ACLPlugin`. The import succeeds, reports no error, the
user's asset is written to a plugin folder they cannot see. Silent data loss.

### The canonical pattern — one import, done

This is already solved in `core/__init__.py`. **Never reimplement it in your plugin.**
Just import it:

```python
from UEFN_Toolbelt.core import detect_project_mount

mount = detect_project_mount()          # e.g. "BRCosmetics" or "Device_API_Mapping"
dest  = f"/{mount}/MyPlugin/Textures/"
```

That's it. `detect_project_mount()` counts Asset Registry paths per mount and returns the
one with the most — the user's project always has hundreds of paths, every Epic plugin has
fewer than ~50. The full `PLUGIN_MOUNTS` blocklist is maintained in `core/__init__.py`
and shared by every tool and the SafetyGate.

### Other APIs to never use for this purpose

| API | Why it's wrong |
|---|---|
| `unreal.Paths.project_content_dir()` | Returns FortniteGame engine path, not user project |
| `unreal.Paths.get_project_file_path()` | Returns `FortniteGame.uproject` in UEFN |
| `candidates[0]` after filtering engine mounts | Picks plugin mount alphabetically before user project |

### Getting the project Content dir on disk

For tools that copy files on disk (cross-project migration, etc.):

```python
# ❌ Wrong — returns engine content dir
src = unreal.Paths.project_content_dir()

# ✅ Correct
project_root = unreal.Paths.convert_relative_path_to_full(
    unreal.Paths.project_dir()
).rstrip("/\\")
src = project_root + "/Content"
```

Full technical breakdown: `docs/UEFN_QUIRKS.md` Quirk #23.
Canonical implementation: `core/__init__.py` → `detect_project_mount()` and `PLUGIN_MOUNTS`.

---

## ⚠️ Never Load Asset Objects in Scan or Audit Plugins

If your plugin scans many assets (audit tools, health checks, batch reporters), **never call
`asset_data.get_asset()` or `unreal.load_asset()` inside a scan loop.** This causes a hard
editor crash — `EXCEPTION_ACCESS_VIOLATION` — with no Python traceback and no Output Log.
`try/except` cannot catch it.

```python
# ❌ Crashes the editor — loads asset object in a loop
for asset_data in ar.get_assets(filt):
    obj = asset_data.get_asset()        # null pointer risk
    lod_count = obj.get_num_lods()      # crash

# ✅ Safe — reads AR metadata only
for asset_data in ar.get_assets(filt):
    name = str(asset_data.package_name)
    cls  = str(asset_data.asset_class_path.asset_name)
```

Full breakdown: `docs/UEFN_QUIRKS.md` Quirk #24.
Reference implementation: `tools/level_health.py` — all audit runners are metadata-only.

---

## 🔒 Security Model

The Toolbelt applies **four security gates** to every custom plugin:

### Gate 1 — File Size Limit
Files larger than 50 KB are rejected. This blocks obfuscated payloads and minified blobs that could hide malicious behavior.

### Gate 2 — AST Import Scanner (Pre-Execution)
Before your plugin file is ever *executed*, the loader parses it using Python's `ast` module and checks for dangerous imports. The following modules are **blocked**:

> `subprocess`, `shutil`, `ctypes`, `socket`, `http`, `urllib`, `requests`, `webbrowser`, `smtplib`, `ftplib`, `xmlrpc`, `multiprocessing`, `signal`, `_thread`

If your plugin imports any of these, the loader will print a `[SECURITY]` error in the Output Log and **refuse to load it**.

### Gate 3 — Namespace Protection (Registration)
Custom plugins **cannot** overwrite core Toolbelt tools. If your plugin tries to register a tool with the same name as a built-in tool (e.g., `toolbelt_smoke_test`), the registry will reject it with a `[SECURITY]` warning.

### Gate 4 — SHA-256 Integrity Hash + Audit Log
Every loaded plugin's SHA-256 hash is computed and written to `Saved/UEFN_Toolbelt/plugin_audit.json` with a timestamp. If a plugin changes between sessions, the hash changes — making tampering instantly detectable.

The audit file also records `toolbelt_version` — both at the file level (which platform release ran this scan) and per plugin entry (which version of the Toolbelt loaded that specific plugin). This means when you share a plugin with someone, the audit file carries provenance: anyone can see exactly what version it was built and verified against.

```json
{
  "toolbelt_version": "1.2.0",
  "scan_time": "2026-03-22T14:30:00",
  "plugins": [
    {
      "plugin": "my_custom_renamer",
      "status": "LOADED",
      "toolbelt_version": "1.2.0",
      "sha256": "a3f9c2...",
      "size_kb": 2.4,
      "loaded_at": "2026-03-22T14:30:00"
    }
  ]
}
```

### Gate 5 — The Global Safety Gate (`core.safety_gate`)
As of Phase 15, every plugin has access to the **Safety Gate**. All Toolbelt "Write" operations are now forced to pass through this gate to ensure they only touch assets in `/Game/` and never accidentally corrupt Epic or Fortnite internal assets.

**Recommended for Plugin Devs:**
Always validate your target path at the start of your plugin's `run()` function:
```python
from UEFN_Toolbelt.core.safety_gate import SafetyGate
# This will log an error and raise PermissionError if unsafe
SafetyGate.enforce_safety(target_asset_path) 
```


---

## ✅ Testing Your Plugin Before Sharing

**Never share or commit a plugin you haven't tested live in UEFN.** Syntax checks don't catch editor runtime failures.

### Minimum test checklist

1. Drop your `.py` file into `Saved/UEFN_Toolbelt/Custom_Plugins/`
2. Reload the Toolbelt in the UEFN Python console:
   ```python
   import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
   ```
3. Confirm your tool appears in the Plugin Hub tab and in the sidebar search
4. Run your tool — verify it does what it's supposed to, with and without a selection
5. Run the smoke test to confirm you haven't broken anything:
   ```python
   tb.run("toolbelt_smoke_test")
   ```
6. Check `Saved/UEFN_Toolbelt/plugin_audit.json` — your plugin's SHA-256 hash should be listed with `"status": "LOADED"`

If all six pass, your plugin is ready to share.
