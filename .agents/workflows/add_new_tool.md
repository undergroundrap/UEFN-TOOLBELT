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
from ..core import log_info, log_warning, get_selected_actors
from ..registry import register_tool

@register_tool(
    name="my_new_tool",
    category="Utilities",
    description="Brief description of what it does.",
    tags=["utilities", "example"],
)
def run_my_new_tool(**kwargs) -> dict:
    """
    Args:
        (no required args for this example)

    Returns:
        dict: {"status", "count"}
    """
    actors = get_selected_actors()
    if not actors:
        log_warning("Select at least one actor.")
        return {"status": "error", "count": 0}

    # Your logic here
    count = len(actors)
    log_info(f"Tool executed on {count} actors.")
    return {"status": "ok", "count": count}
```

### Return Contract (Mandatory)

Every registered tool **must** return a `dict` with at minimum a `"status"` key.

```python
# ✅ Correct
return {"status": "ok", "count": count}
return {"status": "error", "count": 0}

# ❌ Wrong — breaks MCP callers and AI agents
return          # bare None
return count    # bare primitive
```

AI agents calling tools via MCP read the return dict directly from the JSON response.
If you return `None`, the agent has no signal — it cannot confirm success or act on results.

## 3. Add Integration Test
Open `Content/Python/UEFN_Toolbelt/tools/integration_test.py` and add a verification case.

```python
def _test_my_new_tool() -> None:
    _header("X. My New Tool")
    import UEFN_Toolbelt as tb

    # 1. Setup (Spawn fixture)
    actor = _spawn_fixture()
    _select_fixture([actor])

    try:
        # 2. Run — always capture the return dict
        result = tb.run("my_new_tool")

        # 3. Verify — check status key AND domain keys
        passed = (result.get("status") == "ok" and result.get("count", 0) > 0)
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

## 4. Bump the tool count and run drift check
In `Content/Python/UEFN_Toolbelt/__init__.py`, increment `__tool_count__` by the number of new `@register_tool` entries you added. If you added a new category, increment `__category_count__` too. Both values are read by `scripts/drift_check.py` as the single source of truth.

```bash
python scripts/drift_check.py
```

This must pass (`PASS — No drift found`) before committing. If it fails, fix the stale references it reports.

## 5. Update Health Dashboard
Mark your tool as **[A]** (Automated Verified) in `TOOL_STATUS.md`.
