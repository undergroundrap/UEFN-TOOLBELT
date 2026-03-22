# UEFN Toolbelt Custom Plugin Guide

Welcome to the ultimate leverage. 

Because UEFN Toolbelt provides a **Native PySide6 UI**, **Undo-Safety**, **MCP (Claude) Integration**, and massive API helpers, you should never have to build a standalone python script with hardcoded paths ever again.

By writing a **Custom Plugin**, you can add your own completely custom tools to the Toolbelt's interactive dashboard in seconds. When you drop your plugin file into the right folder, the Toolbelt will automatically load it, render a customized UI button for it, map it for AI to use via MCP, and handle error logging.

---

## 🚀 The 60-Second Plugin

1. Navigate to: `[Your UE Project]/Saved/UEFN_Toolbelt/Custom_Plugins/`
   *(If the `Custom_Plugins` folder doesn't exist yet, simply create it)*.
2. Create a new `.py` file, for example: `my_first_plugin.py`
3. Paste the following skeleton code and save it:

```python
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
def run(**kwargs):

    # 1. Ask the toolbelt core for the current viewport selection
    actors = core.require_selection()
    if not actors:
        return
        
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
```

4. Switch back to UEFN. You don't even need to restart! Just close the Dashboard and re-open it via `Toolbelt ▾ -> Open Dashboard`. 
5. You will see a brand new **"My Custom Tools"** tab containing a clickable button for your tool.

---

## 🩺 Validating Your Plugin

If your tool doesn't show up, or you want to make sure you followed our schema correctly, use the built-in validators:

1. Open the Toolbelt Dashboard.
2. Go to the **Utilities** tab.
3. Click **plugin_validate_all**.
4. Check the **Output Log** in UEFN. It will flag if your plugin name has spaces in it, if you forgot a description, or if your function signature doesn't correctly accept `**kwargs`.

To see a list of all currently loaded third-party plugins, click **plugin_list_custom**.

---

## 🤝 Distributing Your Plugin

Because custom plugins live in `Saved/UEFN_Toolbelt/Custom_Plugins/`, they are safely outside of the core Toolbelt installation (`Content/Python/UEFN_Toolbelt/`). 

This means you can update the Toolbelt without ever losing your custom tools.

**Want to share your tool with the world?**
If you think your tool is awesome enough to be part of the official Toolbelt suite:
1. Fork the UEFN-TOOLBELT repository.
2. Move your `.py` file into the primary `Content/Python/UEFN_Toolbelt/tools/` directory.
3. Import your file in `tools/__init__.py`.
4. Submit a Pull Request! We love community additions.

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
