Run a full pre-publish audit. Check everything before the user submits their island to Fortnite.

Tell the user to run this in the UEFN Python console (MCP or direct):

```python
result = tb.run("publish_audit")
print(result)
```

The tool checks:
- Actor budget (Fortnite island limits)
- Required devices (spawn pads, end game device)
- Light count
- Rogue actors (editor-only objects that will break at runtime)
- Verse build status (must be SUCCESS)
- Unsaved changes
- Asset redirectors
- Level name (must not be "Untitled")
- Memory budget

It returns `ready` / `warnings` / `blocked` with a score and ordered next steps.

After the user pastes the result, diagnose any `blocked` issues first, then `warnings`.
For Verse errors: run `tb.run("verse_patch_errors")` and fix the build.
For unsaved assets: run `tb.run("save_all_dirty")`.
For redirectors: run `tb.run("ref_fix_redirectors", scan_path="/Game", dry_run=False)`.
