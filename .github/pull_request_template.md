## What does this PR do?
<!-- One paragraph summary -->

## Type of change
- [ ] Bug fix
- [ ] New tool (core contribution)
- [ ] Community plugin listing (registry.json entry)
- [ ] Docs update
- [ ] Refactor / perf

## Testing
- [ ] Phase 1 — syntax check passed: `python -c "import ast; ast.parse(open('path/to/file.py', encoding='utf-8').read())"`
- [ ] Phase 2 — tested in live UEFN editor with hard refresh bundle
- [ ] CI passes (auto-checked on push)

**Hard refresh bundle used to test:**
```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
```

## Screenshots / output log
<!-- Paste UEFN Output Log snippet or screenshot showing it works -->

## Checklist
- [ ] Commit message follows `type: lowercase description` format
- [ ] No hardcoded file paths (using `unreal.Paths.*`)
- [ ] Tools return `{"status": "ok", ...}` dicts (not `None`)
- [ ] No `time.sleep()` on the main thread
