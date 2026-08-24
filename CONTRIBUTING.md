# Contributing to UEFN Toolbelt

Anyone with this repo and Claude Code can iterate on UEFN Toolbelt on the first try.
CLAUDE.md is auto-loaded by Claude Code — it gives you full codebase context, all tool names, every UEFN quirk, and the exact testing workflow without reading hours of history.

---

## The 5-Step Contributor Loop

```
1. CHECK EXISTING TOOLS
   Run this from the repo root — no UEFN needed:

   grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
     | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort

   That lists every registered tool name. Filter it:
   ... | grep scatter      ← check if scatter tools exist
   ... | grep align        ← check if alignment tools exist

   If a tool already does 80% of what you want — extend it with a param.
   Don't create a new tool for the remaining 20%.

2. WRITE YOUR TOOL
   Create:  Content/Python/UEFN_Toolbelt/tools/my_tool.py
   Register: from . import my_tool  ← add to tools/__init__.py
   Follow the tool design rules below.

3. SYNTAX CHECK (fast gate, no UEFN needed)
   python -c "
   import ast
   with open('Content/Python/UEFN_Toolbelt/tools/my_tool.py', encoding='utf-8') as f:
       ast.parse(f.read())
   print('OK')
   "

4. DEPLOY + LIVE TEST IN UEFN (required — syntax passing ≠ working)
   Run deploy.bat first. The repo and UEFN project are separate trees.

   If you edited an existing module, paste into the UEFN Python console:
   import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("my_tool_name")

   When does `tb` already exist vs. when do you need to import?
   • Same project, same session → `tb` is already defined, nuclear reload refreshes it
   • Switched to a different project → Python environment resets, `tb` is gone — run the full import above
   • Fresh UEFN launch → same as above, always import first
   • Rule of thumb: if you see `NameError: name 'tb' is not defined`, just run the full line above

   ⚠️ If you added a NEW module (new .py file): after deploy.bat, do a full UEFN
   restart instead of nuclear reload, import Toolbelt fresh, register all tools,
   and run the new tool. Nuclear reload + new module = EXCEPTION_ACCESS_VIOLATION.
   See UEFN_QUIRKS.md Quirk #26.

5. DOCUMENT AND HAND OFF FOR REVIEW
   • Add your tool to .claude/tool_tables.md under its category
   • Add a row to the Tool Reference in README.md
   • Bump __tool_count__, and __category_count__ when adding a category
   • Do not bump __version__; the maintainer does that in an authorized release session
   • Leave agent-authored work uncommitted for independent review
   • When the owner later authorizes a commit, use: feat(scope): concise description
```

---

## Tool Design Rules

### Minimum viable tool
```python
from ..registry import register_tool

@register_tool(
    name="my_tool",
    category="My Category",
    description="One sentence — shown in dashboard and manifest.",
    tags=["keyword1", "keyword2"],
)
def my_tool(**kwargs) -> dict:
    import unreal
    # ... your logic ...
    return {"status": "ok", "result": "..."}
```

### Hard rules

| Rule | Why |
|---|---|
| Always return a `dict` with `"status": "ok"` or `"status": "error"` | MCP callers read structured results — no `None` returns |
| Accept `**kwargs` even if you use no params | Registry calls every tool this way |
| Wrap actor mutations in `ScopedEditorTransaction` | Gives users Ctrl+Z undo |
| Never call `unreal.get_asset()` inside a loop | Use Asset Registry batch queries instead |
| Use `detect_project_mount()` for asset paths, never hardcode `/Game/` | UEFN mounts at project name, not `/Game/` — see Quirk #23 |
| Window classes must be module-level, not defined inside the tool function | Hot-reload creates duplicate class names → Qt crash |
| All PySide6 windows must subclass `ToolbeltWindow` from `core/base_window.py` | Consistent theme + Slate tick handling |
| No `subprocess`, `socket`, `ctypes`, or network imports | Blocked by the plugin security scanner |

### Parameter declaration (for manifest + dashboard)
Parameters are declared via **Python default values** — `plugin_export_manifest`
reads them with `inspect.signature()` at export time. Do not pass `parameters=`
to `@register_tool`; it is unsupported and raises `TypeError`. Optional
`example=` metadata is supported for a concrete manifest call such as
`tb.run("my_tool", count=10)` and must agree with the function signature.

```python
@register_tool(
    name="my_tool",
    category="My Category",
    description="Does the thing.",
    tags=["thing"],
)
def my_tool(count: int = 10, folder: str = "", dry_run: bool = True, **kwargs) -> dict:
    ...
```

---

## UEFN Quirks Quick-Reference

| Quirk | Rule |
|---|---|
| **#2 — Main Thread Lock** | All `unreal.*` calls must be on the main thread. Never `time.sleep()` while waiting for async ops — you'll deadlock the engine. |
| **#19 — V2 Device Property Wall** | V2 Creative devices (Timer, Score Manager, etc.) store game-logic settings as Verse `@editable` props. `set_editor_property` fails silently. Use `device_call_method` or generate Verse code instead. |
| **#23 — /Game/ Mount** | UEFN mounts at project name, not `/Game/`. Use `detect_project_mount()` for all asset path operations. Never force-prepend `/Game/`. |
| **#24 — Async Screenshot Deadlock** | `take_high_res_screenshot` is queued. File won't appear while Python is running. Trigger and exit — file lands ~1 second after console returns. |
| **#25 — Slate Tick Required** | Long-running Python blocks the editor UI. Use `register_slate_pre_tick_callback` for deferred work. |
| **#26 — Nuclear Reload + New Module = Crash** | `sys.modules.pop` frees Python objects while stale C++ callbacks still point at them. Adding a new `.py` file to tools? **Full UEFN restart**, not nuclear reload. |
| **#27 — Hard Restart Clears State Nuclear Reload Cannot** | Nuclear reload fixes **code**. Hard restart fixes **state**. After a crash, project switch, or `Shiboken` abort — close UEFN completely and reopen. `tb` is undefined after switching projects; always import fresh. |
| **#37 — TextRenderActor Blocks Publishing** | Every placed `TextRenderActor` is disallowed remotely. Run `publish_audit` and remove all instances before submission. |
| **#41 — Struct Positional Order Is Unsafe** | Build `unreal.*` structs with keyword arguments. `Rotator` is `(roll, pitch, yaw)` and `Color` follows C++ `B,G,R,A` field order. |
| **#42 — Project Python Fails Remote Validation** | Before Launch Session, Push Changes, or publishing, run `prepare_launch.bat`; after remote validation completes, run `restore_after_launch.bat`. `.urcignore` is not enough. |

Full details: `docs/UEFN_QUIRKS.md`

---

## PR Guidelines

1. **One tool or fix per PR** — keeps review tractable
2. **Must include live test confirmation** — paste Output Log snippet in the PR description showing the tool ran without errors in UEFN
3. **Follow scoped commit format**: `feat(scope): concise description` (lowercase, no "Phase:", no Title Case)
4. **Update docs**: `.claude/tool_tables.md` category table + README Tool Reference row + `TOOL_STATUS.md`
5. **Update counts, not the release version**: core tools update `__tool_count__` and, when needed, `__category_count__`; community PRs do not change `__version__` or add a release changelog heading. The maintainer handles those in a separately authorized release session.
6. **Keep publication gates separate**: implementation does not authorize commit; commit does not authorize push; push does not authorize tags, Releases, or social posts.

---

## Community Plugins (No Fork Required)

If you want to ship a tool without touching the core repo:

1. Create a `.py` file with a `@register_tool` decorated function
2. Drop it in `[YourProject]/Saved/UEFN_Toolbelt/Custom_Plugins/`
3. It auto-loads on editor start and appears in the Dashboard

**Security gates your plugin passes automatically:**
- File size ≤ 50 KB
- No blocked imports (`subprocess`, `socket`, `ctypes`, network libs)
- SHA-256 hash logged to `plugin_audit.json`

To list a plugin in the in-app Plugin Hub: add an entry to `registry.json` with `"type": "community"` and open a PR.

Full guide: `docs/plugin_dev_guide.md`

---

## Key Files

| File | What it is |
|---|---|
| `CLAUDE.md` | **Auto-loaded by Claude Code.** Full tool inventory, UEFN rules, testing workflow. Always update when adding tools. |
| `Content/Python/UEFN_Toolbelt/__init__.py` | Package root — `__version__`, `register()`, `run()` |
| `Content/Python/UEFN_Toolbelt/tools/__init__.py` | Import every tool module here so decorators fire |
| `Content/Python/UEFN_Toolbelt/registry.py` | `@register_tool` decorator + `ToolRegistry` singleton |
| `Content/Python/UEFN_Toolbelt/core/base_window.py` | `ToolbeltWindow` — subclass for all PySide6 windows |
| `Content/Python/UEFN_Toolbelt/core/theme.py` | Color palette — single source of truth for UI colors |
| `docs/ui_style_guide.md` | **Mandatory reading** before writing any windowed UI |
| `docs/UEFN_QUIRKS.md` | Non-obvious UEFN Python behaviors — read before your first tool |
| `ARCHITECTURE.md` | System design, directory map, subsystems, data flow — read before structural changes |
| `docs/CHANGELOG.md` | Version history — add your entry here |
| `tests/smoke_test.py` | 5-layer health check — `tb.run("toolbelt_smoke_test")` |

---

## Getting Started with Claude Code

```bash
git clone https://github.com/undergroundrap/UEFN-TOOLBELT
cd UEFN-TOOLBELT
claude  # Claude Code auto-loads CLAUDE.md — full codebase context, instant
```

Claude Code will know every tool, every UEFN quirk, the exact test commands, and the commit format — without any further setup. This is intentional. CLAUDE.md is the contributor onboarding system.
