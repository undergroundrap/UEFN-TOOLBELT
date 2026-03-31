---
paths:
  - "Content/Python/UEFN_Toolbelt/tools/**"
  - "Content/Python/UEFN_Toolbelt/__init__.py"
  - "Content/Python/UEFN_Toolbelt/tools/__init__.py"
---

# Tool Authoring Rules (active when editing tool files)

## Before writing any new tool

1. Search for duplicates first — 358 tools exist, check before building:
   ```bash
   grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
     | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort | grep <keyword>
   ```

2. If a tool already does it — extend it, don't duplicate it.

## Return contract (mandatory)

Every `@register_tool` function MUST return a dict with a `"status"` key:
```python
return {"status": "ok", ...}    # success
return {"status": "error", ...} # failure
```
Never return `None`, a bare primitive, or a live `unreal.*` object.

## After adding a new tool

1. Bump `__tool_count__` in `Content/Python/UEFN_Toolbelt/__init__.py`
2. If it's a new category, bump `__category_count__` too
3. Run drift check — must pass before committing:
   ```bash
   python scripts/drift_check.py
   ```
4. If adding a new module to `tools/__init__.py` → **full UEFN restart required** (not nuclear reload). See UEFN_QUIRKS.md Quirk #26.

## Pak-safe patterns

- List/audit tools: use AR tag reads only, never `load_asset()` in a loop
- Always add `max_results=200` cap to any tool that scans the Asset Registry
- Mount detection: always use `from ..core import detect_project_mount` — never reimplement

## UI rules (any tool that opens a window)

- Subclass `ToolbeltWindow` from `core/base_window.py` — never `QMainWindow` directly
- Window title format: `"UEFN Toolbelt — Tool Name"` — always, no exceptions
- Guard pattern mandatory in every `run_*` that opens a window:
  ```python
  QApplication.instance() or QApplication([])
  if _win is None or not _win.isVisible():
      _win = _build_window()
      _win.show_in_uefn()
  else:
      _win.raise_(); _win.activateWindow()
  ```
- Every tool window needs a `?` help button
- Read `docs/ui_style_guide.md` before writing any PySide6 UI
