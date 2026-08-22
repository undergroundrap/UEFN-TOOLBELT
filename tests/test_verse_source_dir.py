"""The Verse source directory must come from the project, not from a guess.

UEFN 41+ stopped compiling `<project>/Verse/`. The resolver used to look there
first and, when it was missing, CREATE it and return it. So `verse_write_file`
wrote a .verse file into a directory the compiler ignores, reported success,
and the Phase 5 build loop then waited on a build that could never contain the
code. Nothing raised at any point, and creating the folder made the mistake
look deliberate to whoever opened the project next.

Verified against a real UEFN 42.00 project on 2026-08-21: no `Verse/` directory
existed, the `.code-workspace` declared `<project>/Content`, and the project's
only .verse file lived there.

The package entry is selected by path containment rather than list position,
so it keeps working if Epic reorders or renames the workspace folders.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path


def _mod():
    return importlib.import_module("UEFN_Toolbelt.tools.verse_snippet_generator")


def _workspace(root: Path, package: Path) -> None:
    """Write a .code-workspace shaped like a real one: the package folder plus
    the read-only digest folders that live outside the project."""
    (root / "PROJ.code-workspace").write_text(json.dumps({
        "folders": [
            {"name": "/u@fortnite.com/PROJ (PROJ)", "path": str(package)},
            {"name": "/u@fortnite.com/PROJ (PROJ/Assets)",
             "path": str(root.parent / "AppData" / "Digests" / "PROJ-Assets")},
            {"name": "vproject (read-only)",
             "path": str(root.parent / "AppData" / "vproject")},
        ]
    }), encoding="utf-8")


def test_the_workspace_package_dir_wins(tmp_path, monkeypatch):
    root = tmp_path / "PROJ"
    content = root / "Content"
    content.mkdir(parents=True)
    for outside in ("AppData/Digests/PROJ-Assets", "AppData/vproject"):
        (tmp_path / outside).mkdir(parents=True, exist_ok=True)
    _workspace(root, content)

    mod = _mod()
    monkeypatch.setattr(mod, "_find_uefn_project_root", lambda: str(root))
    assert mod._verse_dir_from_workspace(str(root)) == str(content.resolve())


def test_folders_outside_the_project_are_never_chosen(tmp_path, monkeypatch):
    """The digest and vproject entries live under AppData. Selecting by
    containment rejects them without relying on list order or folder names."""
    root = tmp_path / "PROJ"
    root.mkdir(parents=True)
    outside = tmp_path / "AppData" / "Digests" / "PROJ-Assets"
    outside.mkdir(parents=True)

    (root / "PROJ.code-workspace").write_text(json.dumps({
        "folders": [
            {"name": "/u@fortnite.com/PROJ (PROJ/Assets)", "path": str(outside)},
        ]
    }), encoding="utf-8")

    mod = _mod()
    assert mod._verse_dir_from_workspace(str(root)) == ""


def test_a_missing_verse_dir_is_never_created(tmp_path, monkeypatch):
    """The regression itself. The old resolver ran os.makedirs here."""
    root = tmp_path / "PROJ"
    content = root / "Content"
    content.mkdir(parents=True)

    mod = _mod()
    monkeypatch.setattr(mod, "_find_uefn_project_root", lambda: str(root))
    monkeypatch.setattr(mod, "_verse_dir_from_workspace", lambda _root: "")

    path, source = mod._resolve_verse_dir()

    assert not (root / "Verse").exists(), (
        "a Verse/ directory was created — UEFN 41+ does not compile it, so "
        "anything written there is silently never built"
    )
    assert path == str(content)
    assert source == "content"


def test_an_existing_legacy_verse_dir_is_still_honoured(tmp_path, monkeypatch):
    """Pre-41 projects that really do have one keep working."""
    root = tmp_path / "PROJ"
    legacy = root / "Verse"
    legacy.mkdir(parents=True)
    (root / "Content").mkdir()

    mod = _mod()
    monkeypatch.setattr(mod, "_find_uefn_project_root", lambda: str(root))
    monkeypatch.setattr(mod, "_verse_dir_from_workspace", lambda _root: "")

    path, source = mod._resolve_verse_dir()
    assert path == str(legacy)
    assert source == "legacy"


def test_there_is_only_one_resolver():
    """run_verse_find_project_path carried a second copy of this search that
    had already drifted — it still created the uncompiled directory. Two copies
    of a path resolver is one too many."""
    src = (Path(__file__).resolve().parents[1] / "Content" / "Python"
           / "UEFN_Toolbelt" / "tools" / "verse_snippet_generator.py"
           ).read_text(encoding="utf-8")
    assert src.count("def _resolve_verse_dir") == 1
    assert "os.makedirs(standard" not in src, (
        "the create-a-dead-directory fallback is back"
    )
