Build a new UEFN Toolbelt tool named "$ARGUMENTS". Follow the tool-developer agent workflow exactly:

1. **Duplicate audit** — search the registry first:
   ```bash
   grep -rh 'name="' Content/Python/UEFN_Toolbelt/tools/ --include="*.py" \
     | grep -o 'name="[^"]*"' | sed 's/name="//;s/"//' | sort | grep -i "$ARGUMENTS"
   ```
   If a tool already covers this — say so and stop. Extend instead of duplicate.

2. **Find the right module** — read 2-3 related tool files to match the exact code style before writing anything.

3. **Write the tool** — follow the return contract: `{"status": "ok"/"error", ...}`. Never None. Wrap mutations in `unreal.ScopedEditorTransaction`. Use `get_selected_actors()` from `..core`. Log with `log_info`/`log_warning`.

4. **Register the module** (if new file) — add import to `Content/Python/UEFN_Toolbelt/tools/__init__.py`.

5. **Bump counts** in `Content/Python/UEFN_Toolbelt/__init__.py`:
   - `__tool_count__` += number of new `@register_tool` entries
   - `__category_count__` += 1 if new category
   - `__version__` patch bump

6. **Drift check**:
   ```bash
   python scripts/drift_check.py
   ```
   Must return PASS.

7. **Syntax check**:
   ```bash
   python -c "import ast; ast.parse(open('Content/Python/UEFN_Toolbelt/tools/<file>.py', encoding='utf-8').read()); print('OK')"
   ```

8. **Give exact UEFN test instructions**:
   - Run `deploy.bat`
   - If new module: full UEFN restart (not nuclear reload — Quirk #26)
   - Otherwise: nuclear reload then `tb.run("your_new_tool")`
   - Confirm output matches expected return dict before committing
