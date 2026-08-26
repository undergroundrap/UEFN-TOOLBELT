Generate the exact deploy + test sequence for the current change.

Read the files that were most recently modified to determine the change type, then output the precise UEFN console commands needed.

## Change type → required test

| Change | Test sequence |
|---|---|
| Tool-only change | `deploy.bat` → nuclear reload → `tb.run("tool_name")` |
| New module added to `tools/__init__.py` | `deploy.bat` → **full UEFN restart** → `tb.register_all_tools()` → `tb.run("tool_name")` |
| PySide6 window / dashboard UI | `deploy.bat` → **full UEFN restart** → open window, interact |
| `core/` module change | `deploy.bat` → nuclear reload → `tb.run("toolbelt_smoke_test")` |
| MCP bridge change | `deploy.bat` → **full UEFN restart** → `tb.run("mcp_start")` → authenticated external ping |
| Launch Session / Push Changes / publish | run `publish_audit` while Python is loaded → `prepare_launch.bat` → wait for remote validation → `restore_after_launch.bat` |

## Nuclear reload (paste into UEFN Python console)

```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
```

Replace `tb.launch_qt()` with `tb.run("your_tool_name")` for tool-only changes.

## Required static gates

```bash
python -m ruff check .
python -m mypy
python -m pytest
python scripts/drift_check.py
```

## Stop boundary

After UEFN confirms the behavior and the static gates pass, report the exact
evidence and leave the complete worktree uncommitted with an empty index for
independent review.

A successful test does not authorize staging, committing, pushing, tagging,
creating a GitHub Release, or posting to social media. Each later action needs a
separate explicit owner go signal. Stage only reviewed paths after commit is
authorized; never stage the whole repository.
