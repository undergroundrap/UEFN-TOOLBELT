"""
UEFN TOOLBELT -- AI Project Setup Workflow
===========================================
One command. Folder structure + Verse game manager. Ready to build.

What it does (safe to chain -- no Unreal API calls after scaffold):
  1. Scaffold -- creates the professional Content Browser folder tree
  2. Verse    -- generates a game manager skeleton and deploys it

What it does NOT do (must be separate calls -- engine needs to yield first):
  - organize_assets      (Asset Registry moves)
  - rename_enforce_conventions  (Asset Registry renames)
  - arena_generate       (actor spawning)
  - snapshot_save        (level actor iteration)

Chaining Unreal API calls after scaffold_generate causes EXCEPTION_ACCESS_VIOLATION
(Quirk #22). These must be run as separate tb.run() calls after the engine yields.

FULL WORKFLOW (copy-paste sequence):

    import UEFN_Toolbelt as tb

    # 1. Scaffold + Verse (safe to chain)
    tb.run("project_setup", project_name="MyGame")

    # 2. Organize loose assets (separate call)
    tb.run("organize_assets", folder="/Game/")

    # 3. Fix naming (separate call)
    tb.run("rename_enforce_conventions", scan_path="/Game/")

    # 4. Spawn the arena layout (separate call)
    tb.run("arena_generate", size="medium")

    # 5. Build Verse (one click in UEFN)
    # 6. tb.run("verse_patch_errors")
"""

from __future__ import annotations

import os
from typing import Any

from ..core import log_info, log_warning
from ..registry import get_registry, register_tool


def _run(tool_name: str, **kwargs) -> dict[str, Any]:
    """Call a registered tool by name. Returns {} on failure."""
    try:
        result = get_registry().execute(tool_name, **kwargs)
        return result if isinstance(result, dict) else {"status": "ok"}
    except Exception as exc:
        log_warning(f"[project_setup] step '{tool_name}' raised: {exc}")
        return {"status": "error", "message": str(exc)}


@register_tool(
    name="project_setup",
    category="Project Admin",
    description=(
        "One-command project setup: scaffold folder structure + deploy Verse "
        "game manager skeleton. Safe to run on any UEFN project."
    ),
    tags=[
        "setup", "workflow", "scaffold", "verse", "ai",
        "automation", "onboarding", "new project", "first run",
    ],
)
def project_setup(
    project_name: str = "MyGame",
    template: str = "uefn_standard",
    dry_run: bool = False,
    **kwargs,
) -> dict:
    """
    Scaffold the project folder structure and deploy a Verse game manager.
    Safe to chain -- only Content Browser folder creates and file writes.

    Run organize_assets, rename_enforce_conventions, and arena_generate as
    separate tb.run() calls AFTER this returns (Quirk #22).

    Args:
        project_name: Your project/game name. e.g. "BattleArena"
        template:     uefn_standard (default), competitive_map, solo_dev, verse_heavy
        dry_run:      Preview scaffold without changes. Verse step is skipped.

    Returns:
        {
          "status":       "ok" | "partial",
          "project_name": str,
          "steps":        [{"step", "status", "detail"}, ...],
          "verse_path":   str or None,
          "next_steps":   [str, ...]
        }
    """
    steps = []
    verse_path = None

    log_info(f"[project_setup] '{project_name}' -- template={template}")

    # -- Step 1: Scaffold -------------------------------------------------
    if dry_run:
        r = _run("scaffold_preview", template=template, project_name=project_name)
        steps.append({
            "step": "scaffold_preview",
            "status": r.get("status", "ok"),
            "detail": f"Preview only. Template: {template}. Run with dry_run=False to apply.",
        })
        return {
            "status": "ok",
            "project_name": project_name,
            "steps": steps,
            "verse_path": None,
            "next_steps": [f"tb.run('project_setup', project_name='{project_name}')"],
        }

    r = _run("scaffold_generate", template=template, project_name=project_name)
    steps.append({
        "step": "scaffold_generate",
        "status": r.get("status", "ok"),
        "detail": "Folder tree created in Content Browser.",
    })

    # -- Step 2: Generate Verse skeleton (pure Python file write) ----------
    parts = project_name.replace("-", "_").split("_")
    device_name = "".join(w[0].upper() + w[1:] for w in parts if w) + "Manager"
    r = _run("verse_gen_game_skeleton", device_name=device_name)
    snippet_path = r.get("path", "")
    steps.append({
        "step": "verse_gen_game_skeleton",
        "status": r.get("status", "ok"),
        "detail": f"Skeleton written for class '{device_name}'.",
    })

    # -- Step 3: Deploy Verse file (pure Python file write) ---------------
    if snippet_path and os.path.isfile(snippet_path):
        try:
            with open(snippet_path, encoding="utf-8") as f:
                verse_content = f.read()
            filename = device_name.lower() + "_manager.verse"
            r = _run("verse_write_file",
                     filename=filename,
                     content=verse_content,
                     overwrite=False)
            verse_path = r.get("path", "")
            steps.append({
                "step": "verse_write_file",
                "status": r.get("status", "ok"),
                "detail": f"Deployed -> {verse_path}",
            })
        except Exception as exc:
            steps.append({"step": "verse_write_file", "status": "error", "detail": str(exc)})
    else:
        steps.append({"step": "verse_write_file", "status": "skipped",
                      "detail": "Snippet path missing."})

    # -- Summary ----------------------------------------------------------
    failed = [s for s in steps if s["status"] == "error"]
    overall = "ok" if not failed else "partial"

    next_steps = [
        "tb.run('organize_assets', folder='/Game/')",
        "tb.run('rename_enforce_conventions', scan_path='/Game/')",
        "tb.run('arena_generate', size='medium')",
        "Verse menu -> Build Verse Code",
        "tb.run('verse_patch_errors')",
    ]

    for s in steps:
        icon = "OK" if s["status"] == "ok" else ("!!" if s["status"] == "error" else "--")
        log_info(f"  [{icon}] {s['step']}: {s['detail']}")
    log_info(f"[project_setup] done -- {len(steps)} steps, {len(failed)} failed")
    log_info("Next: " + " | ".join(next_steps[:3]))

    return {
        "status": overall,
        "project_name": project_name,
        "steps": steps,
        "verse_path": verse_path,
        "next_steps": next_steps,
    }
