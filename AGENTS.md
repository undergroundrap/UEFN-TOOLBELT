# UEFN Toolbelt — Agent Guide

> For AI agents working with this codebase. Read this before making any changes.

## What this repo is

Python automation framework for Unreal Editor for Fortnite (UEFN).
362 tools, 55 categories, PySide6 dashboard, and Toolbelt's own custom bridge.
An MCP-compatible AI connects to that bridge via `.mcp.json` (pre-configured).
The bridge is Toolbelt's own authenticated, same-user loopback HTTP listener — not
Epic's official UEFN MCP server, which Toolbelt is not reachable through.

## Non-negotiable rules

1. **Never commit without a live UEFN test.** Syntax passing ≠ working in the editor.
2. **Always run `deploy.bat` before testing.** Repo and UEFN project are separate directories.
3. **Run `python scripts/drift_check.py` before every commit.** Must return PASS.
4. **Bump `__tool_count__` and `__category_count__`** in `Content/Python/UEFN_Toolbelt/__init__.py` when adding tools.
5. **Full UEFN restart required** when adding a new module to `tools/__init__.py`. Nuclear reload crashes. See `docs/UEFN_QUIRKS.md` Quirk #26.
6. **All tool functions must return `{"status": "ok"/"error", ...}`** — never None, never a bare primitive.

7. **Never build an `unreal.*` struct with positional args.** Their order follows
   the C++ field declaration, not the order the docs describe them in.
   Confirmed live on UEFN 42.00:

   ```python
   unreal.Rotator(10, 20, 30)   # roll=10  pitch=20  yaw=30   (NOT pitch,yaw,roll)
   unreal.Color(10, 20, 30)     # r=30     g=20      b=10     (FColor is B,G,R,A)
   ```

   `unreal.Rotator(0, yaw, 0)` sets *pitch* and nothing raises, so props tilt
   instead of turning. `unreal.Color(r, g, b, 255)` swaps red and blue. 31
   Rotator sites and one Color site were wrong this way before it was caught.
   Use keyword args: `unreal.Rotator(roll=0, pitch=0, yaw=yaw)`.
   `tests/test_rotator_argument_order.py` fails the build if this returns.
   See `docs/UEFN_QUIRKS.md` Quirk #41.
8. **Check the registry before building anything** — 362 tools exist. Search first:
   ```bash
   grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
     | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort | grep <keyword>
   ```
9. **Project `.py` files block remote validation.** Before Launch Session, Push
   Changes, or publishing on UEFN 42.00, run `prepare_launch.bat`; after the
   upload completes, run `restore_after_launch.bat`. `.urcignore` does not gate
   Valkyrie staging. See `docs/UEFN_QUIRKS.md` Quirk #42.
10. **Keep owner authorization gates separate.** Implementation, independent
    review, commit, push, tag, GitHub Release, and social publication are
    distinct actions. Authorization for one never implies the next. Leave work
    uncommitted for review unless the owner explicitly authorizes the exact
    commit; never move an existing tag.
11. **Cold-start from `WORKORDER.md`.** It is the sole pointer allowed to name
    the current issued Work Order and authorized session. Files under
    `docs/work-orders/proposed/` are planning only and never grant implementation
    authority. If either current field says `NONE`, stop at the corresponding
    owner gate.

## Key files for agents

| File | What to read for |
|---|---|
| `WORKORDER.md` | Current issued Work Order, authorized session, base, and exact gate; `NONE` means stop |
| `CLAUDE.md` | Full project context, mandatory rules, all tool tables |
| `SECURITY.md` | Current trust boundary; custom MCP remains experimental pending WO-001 |
| `docs/audits/2026-08-24-uefn-42-official-mcp-audit.md` | Accepted official-MCP, coexistence, security, and repository-truth evidence |
| `docs/work-orders/README.md` | Work Order states, required contents, and gate sequence |
| `docs/UEFN_QUIRKS.md` | Non-obvious UEFN Python behaviors — read before touching any API |
| `docs/PIPELINE.md` | 6-phase autonomous game-building pipeline |
| `docs/ui_style_guide.md` | Mandatory for any PySide6 window work |
| `TOOL_STATUS.md` | Per-tool test coverage — check before assuming a tool is tested |
| `ARCHITECTURE.md` | System design, directory map, data flow |
| `scripts/drift_check.py` | Run this — validates version/count consistency across docs and agent context |
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
[user confirms output]              → leave the complete change uncommitted
[independent review accepts]         → owner may authorize the exact commit
[owner separately authorizes push]  → push and monitor CI to completion
```

For Launch Session / Push Changes validation:

```
prepare_launch.bat                  → verify zero project .py files
[Launch Session or Push Changes]    → wait for remote validation
restore_after_launch.bat            → restore the manifest exactly
```
