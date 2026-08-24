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
For changes to existing pure tool modules, this command clears the
`sys.modules` cache and re-registers all tools:
```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools()
```

If the change added a new module to `tools/__init__.py`, or touched a PySide6
window with persistent callbacks, do a full UEFN restart instead. Nuclear reload
is unsafe for those cases; see Quirks #26 and #38.

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
Check the Output Log for `INTEGRATION TEST COMPLETE — Passed: N/N`. The v2.4.1
baseline on UEFN 42.00 is 116 sections and 190/190 checks: 163 verify a real
outcome and 27 are execution-only. Read the split, not only the headline total,
and see `TOOL_STATUS.md` for the authoritative current evidence.

## 6. If remote validation is next

Run every Python-based audit before staging. Then use:

```text
publish_audit while Python is loaded
prepare_launch.bat
Launch Session / Push Changes / publish; wait for the remote result
restore_after_launch.bat
```

Do not restart or hot-reload Toolbelt while the Python stash is active.
