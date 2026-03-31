# UEFN Toolbelt — Agent Guide

> For AI agents working with this codebase. Read this before making any changes.

## What this repo is

Python automation framework for Unreal Editor for Fortnite (UEFN).
358 tools, 55 categories, MCP HTTP bridge, PySide6 dashboard.
Any MCP-compatible AI connects via `.mcp.json` (pre-configured).

## Non-negotiable rules

1. **Never commit without a live UEFN test.** Syntax passing ≠ working in the editor.
2. **Always run `deploy.bat` before testing.** Repo and UEFN project are separate directories.
3. **Run `python scripts/drift_check.py` before every commit.** Must return PASS.
4. **Bump `__tool_count__` and `__category_count__`** in `Content/Python/UEFN_Toolbelt/__init__.py` when adding tools.
5. **Full UEFN restart required** when adding a new module to `tools/__init__.py`. Nuclear reload crashes. See `docs/UEFN_QUIRKS.md` Quirk #26.
6. **All tool functions must return `{"status": "ok"/"error", ...}`** — never None, never a bare primitive.
7. **Check the registry before building anything** — 358 tools exist. Search first:
   ```bash
   grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
     | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort | grep <keyword>
   ```

## Key files for agents

| File | What to read for |
|---|---|
| `CLAUDE.md` | Full project context, mandatory rules, all tool tables |
| `docs/UEFN_QUIRKS.md` | Non-obvious UEFN Python behaviors — read before touching any API |
| `docs/PIPELINE.md` | 6-phase autonomous game-building pipeline |
| `docs/ui_style_guide.md` | Mandatory for any PySide6 window work |
| `TOOL_STATUS.md` | Per-tool test coverage — check before assuming a tool is tested |
| `ARCHITECTURE.md` | System design, directory map, data flow |
| `scripts/drift_check.py` | Run this — validates version/count consistency across all docs |
| `.agents/workflows/` | Step-by-step workflows: `add_new_tool.md`, `run_tests.md` |

## Specialized agents in this repo

See `.claude/agents/` for focused agent definitions:
- **`verse-deployer`** — Verse codegen + error fix loop (Phases 5–7 of the pipeline)
- **`tool-developer`** — Builds new tools: registry audit → write → drift check → test instructions

## Quick orientation

```bash
# See every registered tool name
grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
  | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort

# Validate codebase consistency
python scripts/drift_check.py

# Syntax check a tool file
python -c "import ast; ast.parse(open('Content/Python/UEFN_Toolbelt/tools/your_tool.py').read()); print('OK')"
```

## Deploy + test workflow

```
deploy.bat                          → sync repo → UEFN project
[nuclear reload in UEFN console]    → hot-reload modules
tb.run("tool_name")                 → test live
[user confirms output]              → commit
```
