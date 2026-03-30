---
description: How to run UEFN Toolbelt smoke and integration tests
---

Follow these steps to verify that the UEFN Toolbelt is fully functional inside the Unreal Editor for Fortnite.

## 1. Deploy Changes
Ensure your latest code is synced to the UEFN project's `Content/Python` directory.
```powershell
.\deploy.bat
```

## 2. Open UEFN Python Console
1. Open your UEFN project.
2. In the menu bar, go to **Window -> Output Log**.
3. At the bottom of the Output Log, change the command type from "Cmd" to **Python**.

## 3. Run the "Nuclear Reload"
This command clears the `sys.modules` cache and re-registers all tools without requiring an editor restart.
```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools()
```

## 4. Execute the Smoke Test (Layer 1-6)
Checks the registry, module health, and "safe" tools.
```python
import UEFN_Toolbelt as tb; tb.run("toolbelt_smoke_test")
```

## 5. Execute the Integration Test (Layer 7)
**[WARNING: INVASIVE]** Spawns and deletes actors in the live viewport. Best run in a blank "Test Template" level.
```python
import UEFN_Toolbelt as tb; tb.run("toolbelt_integration_test")
```
Check the Output Log for `INTEGRATION TEST COMPLETE — Passed: N/N`. See `TOOL_STATUS.md` for the current verified count (103+ live sections as of v2.2.0).
