## What does this PR do?
<!-- One paragraph summary -->

## Type of change
- [ ] Bug fix
- [ ] New tool (core contribution)
- [ ] Community plugin listing (registry.json entry)
- [ ] Docs update
- [ ] Refactor / perf

## Testing
- [ ] Static gates passed: Ruff, mypy, pytest, and `scripts/drift_check.py`
- [ ] Ran `deploy.bat` before live UEFN testing
- [ ] Tested in live UEFN with the change-appropriate reload/restart path
- [ ] New module: used a full UEFN restart instead of nuclear reload (or N/A)
- [ ] Docs/static-only change: live UEFN is N/A and the reason is stated below (or N/A)
- [ ] CI passes (auto-checked on push)

**Live verification or N/A reason:**
<!-- Name the project, exact command/action, and observed result. -->

**Hard refresh bundle used to test:**
```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
```

## Screenshots / output log
<!-- Paste UEFN Output Log snippet or screenshot showing it works -->

## Launch Session / publishing validation (when exercised)
- [ ] Ran `publish_audit` before staging Python
- [ ] Ran `prepare_launch.bat`, waited for the remote result, then ran `restore_after_launch.bat`
- [ ] Confirmed zero `TextRenderActor` blockers and zero remaining project `.py` files

## Checklist
- [ ] Commit message follows `type(scope): lowercase description` format
- [ ] No hardcoded `/Game/` project paths; path logic uses the canonical core resolvers
- [ ] No positional `unreal.*` struct construction
- [ ] Tools return `{"status": "ok", ...}` dicts (not `None`)
- [ ] No `time.sleep()` on the main thread
