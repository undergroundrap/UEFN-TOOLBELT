Run a full pre-publish audit while Toolbelt Python is still present. Check
everything before the user submits their island to Fortnite.

## 1. Audit and clean while Python is loaded

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
- Every placed `TextRenderActor` (hard publish blocker)

It returns `ready` / `warnings` / `blocked` with a score and ordered next steps.

After the user pastes the result, diagnose any `blocked` issues first, then `warnings`.
For Verse errors: run `tb.run("verse_patch_errors")` and fix the build.
For unsaved assets: run `tb.run("save_all_dirty")`.
For redirectors: run `tb.run("ref_fix_redirectors", scan_path="", dry_run=False)`.
For any `TextRenderActor`: run
`tb.run("sign_clear", all_text_actors=True, dry_run=False)`, save the level,
and re-run `publish_audit` until no text actors remain.

Do not stage Python yet: `publish_audit` and its cleanup commands require the
Toolbelt package to remain in the project.

## 2. Prepare the project for remote validation

Only after the audit is clear enough to submit, run this from the Toolbelt repo:

```bat
prepare_launch.bat
```

The helper must report zero `.py` files under the selected UEFN project. UEFN
42.00 rejects every project `.py` for the standard `VKCreateUGC` role;
`.urcignore` does not control Valkyrie staging.

## 3. Launch, push, or publish

Start Launch Session, Push Changes, or publishing in UEFN. Wait for the remote
validation/upload result. Fortnite opening is not proof that remote validation
passed.

Do **not** restart UEFN, hot-reload Toolbelt, deploy again, or create replacement
Python files while the stash is active.

## 4. Restore development Python

After remote validation finishes—success or failure—run:

```bat
restore_after_launch.bat
```

If preparation or restoration reports a collision or incomplete recovery, stop
and preserve the LocalAppData stash. Do not overwrite destinations manually.
