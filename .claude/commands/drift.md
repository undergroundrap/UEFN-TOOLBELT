Run the drift check and report the result. If it fails, identify which file has the stale reference and fix it.

```bash
python scripts/drift_check.py
```

The ground truth is `Content/Python/UEFN_Toolbelt/__init__.py`:
- `__version__` — must match in README, CLAUDE.md, ARCHITECTURE.md, TOOL_STATUS.md, mcp_server.py, docs/CHANGELOG.md, llms.txt
- `__tool_count__` — must match in all the same files
- `__category_count__` — must match in all the same files

If PASS: report the current version, tool count, and category count.
If FAIL: read the failing file, find the stale number, fix it with Edit, then re-run until PASS.
