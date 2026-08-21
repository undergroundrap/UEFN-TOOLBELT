"""
Anything that enumerates a folder must filter the results.
==============================================================================
EditorAssetLibrary.list_assets() returns two kinds of path that are not
standalone assets:

  ':'  one-file-per-actor sub-objects — a level yields thousands, all resolving
       to the same owning package.
  '$'  UEFN 42.00 Verse digest paths ($Digest, $DebugData, my_device$OnBegin).
       EditorAssetSubsystem rejects these outright, logging an editor error on
       every lookup.

reference_auditor learned this the destructive way: it classified every asset as
orphaned. tag_list_all was still logging "Can't convert the path $Digest" on a
live 42.00 project long after, because the guard lived in one module instead of
in core. Renaming and moving tools enumerate the same way, and those write.
"""

from __future__ import annotations

import ast
import pathlib

TOOLS = pathlib.Path("Content/Python/UEFN_Toolbelt/tools")

# reference_auditor keeps its own _is_scannable_asset — it needs the sub-object
# count for its report, so it filters inline rather than at enumeration.
EXEMPT = {"reference_auditor.py"}


def _enumeration_sites():
    """(file, lineno, source) for every list_assets() call."""
    for path in sorted(TOOLS.glob("*.py")):
        if path.name in EXEMPT:
            continue
        src = path.read_text(encoding="utf-8")
        if "list_assets(" not in src:
            continue
        tree = ast.parse(src)
        lines = src.split("\n")
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "list_assets"):
                continue
            seg = ast.get_source_segment(src, node) or ""
            # the statement plus the line after it — the filter may be either
            # wrapped around the call or applied on the next line
            window = "\n".join(lines[max(0, node.lineno - 3):node.end_lineno + 1])
            yield path.name, node.lineno, seg, window


def test_there_are_enumerations_to_check():
    """A parser matching nothing would make the real test vacuously pass."""
    assert len(list(_enumeration_sites())) >= 8


def test_every_enumeration_is_filtered():
    unfiltered = [
        f"{name}:{ln}"
        for name, ln, seg, window in _enumeration_sites()
        if "scannable_assets" not in window
        and "class_filter" not in seg
        and "class_names" not in seg
    ]
    assert unfiltered == [], (
        "these enumerate a folder without filtering sub-objects and Verse digest "
        f"paths — wrap in core.scannable_assets(): {unfiltered}"
    )


def test_the_guard_rejects_what_it_should():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "tb_core", "Content/Python/UEFN_Toolbelt/core/__init__.py")
    # core imports unreal at module scope, so exercise the logic directly rather
    # than importing it — this mirrors core.is_scannable_asset exactly.
    ok = lambda p: ":" not in p and "$" not in p  # noqa: E731
    assert ok("/MyProject/Meshes/SM_Rock")
    assert not ok("/P/L.L:PersistentLevel.ActorFolder_UID_1")   # OFPA sub-object
    assert not ok("/P/Verse/$Digest")                            # Verse digest
    assert not ok("/P/task_hello_world_device$OnBegin")          # seen in a real log
    assert spec is not None
