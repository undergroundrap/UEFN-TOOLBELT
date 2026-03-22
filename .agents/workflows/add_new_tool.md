---
description: How to add a new UEFN Toolbelt tool with automated verification
---

Follow these steps to add a new tool to the UEFN Toolbelt and ensure it is properly verified.

## 1. Consult the High-Fidelity Schema
Before writing logic, consult `docs/api_level_classes_schema.json` to find the exact property names and methods for your target UEFN classes (e.g., `BuildingProp`). This is the **Source of Truth** for the project.

## 2. Create the Tool Logic
Create or edit a `.py` file in `Content/Python/UEFN_Toolbelt/tools/`.

```python
import unreal
from UEFN_Toolbelt.registry import register_tool

@register_tool(
    name="my_new_tool",
    category="Utilities",
    description="Brief description of what it does",
    icon="🔧"
)
def my_new_tool(**kwargs):
    # Your logic here
    unreal.log("Tool executed!")
```

## 2. Add Integration Test
Open `Content/Python/UEFN_Toolbelt/tools/integration_test.py` and add a verification case.

```python
def _test_my_new_tool() -> None:
    _header("X. My New Tool")
    import UEFN_Toolbelt as tb
    
    # 1. Setup (Spawn fixture)
    actor = _spawn_fixture()
    _select_fixture([actor])
    
    try:
        # 2. Run
        tb.run("my_new_tool")
        
        # 3. Verify (Check property or state)
        passed = True # Your logic here
        _record("Category", "Name", passed)
    except Exception as e:
        _record("Category", "Name", False, str(e))
```

// turbo
## 3. Deploy and Verify
Run the "Nuclear Reload" to see your new tool in action immediately without restarting UEFN.

1. Run `deploy.bat` to sync files.
2. Paste this into the UEFN Python console:
```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_integration_test")
```

## 4. Update Health Dashboard
Mark your tool as **[A]** (Automated Verified) in `TOOL_STATUS.md`.
