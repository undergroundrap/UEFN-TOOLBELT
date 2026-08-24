Run the drift check and report the result. If it fails, identify which file has the stale reference and fix it.

```bash
python scripts/drift_check.py
```

The ground truth is `Content/Python/UEFN_Toolbelt/__init__.py`:
- `__version__` — current release version
- `__tool_count__` — registered-tool count
- `__category_count__` — registered category count

`scripts/drift_check.py::SCAN_FILES` is the authoritative coverage list. It
includes user docs, `llms.txt`, contributor guidance, agent workflows, Claude
commands/rules, UI text, and the other hardcoded context surfaces.

If PASS: report the current version, tool count, and category count.
If FAIL: read the failing file and fix only drift that belongs to the currently
authorized scope, then re-run until PASS. Preserve historical release claims;
do not rewrite an old version merely to make the scanner green.

Stop with the correction uncommitted. Passing drift does not authorize a
commit, push, tag, GitHub Release, or social publication.
