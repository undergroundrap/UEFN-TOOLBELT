Generate the exact deploy + test sequence for the current change.

Read the files that were most recently modified to determine the change type, then output the precise UEFN console commands needed.

## Change type → required test

| Change | Test sequence |
|---|---|
| Tool-only change | `deploy.bat` → nuclear reload → `tb.run("tool_name")` |
| New module added to `tools/__init__.py` | `deploy.bat` → **full UEFN restart** → `tb.register_all_tools()` → `tb.run("tool_name")` |
| PySide6 window / dashboard UI | `deploy.bat` → **full UEFN restart** → open window, interact |
| `core/` module change | `deploy.bat` → nuclear reload → `tb.run("toolbelt_smoke_test")` |
| MCP bridge change | `deploy.bat` → `tb.run("mcp_start")` |

## Nuclear reload (paste into UEFN Python console)

```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
```

Replace `tb.launch_qt()` with `tb.run("your_tool_name")` for tool-only changes.

## After UEFN confirms it works

```bash
python scripts/drift_check.py
git add -A
git commit -m "feat: <description>"
git push origin main
```

**Never commit before the user confirms it works in the live editor.**
