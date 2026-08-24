"""The Launch Session workaround must move every .py and restore without overwrites."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "session_python.ps1"
PREPARE = REPO / "prepare_launch.bat"
RESTORE = REPO / "restore_after_launch.bat"
DEPLOY = REPO / "deploy.bat"
GIT_ATTRIBUTES = REPO / ".gitattributes"
POWERSHELL = shutil.which("powershell")


def test_workflow_source_keeps_stash_outside_project_and_refuses_collisions():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "SessionPythonStash" in source
    assert "Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.py' -Force" in source
    assert "Get-PythonFiles $ProjectPath" in source
    assert "Restore collision; project file already exists" in source
    assert "Prepare verification failed" in source
    assert "Restore verification failed" in source
    assert "manifest.json" in source
    assert "Remove-Item -LiteralPath $StashPath -Recurse -Force" in source
    assert "-Action prepare" in PREPARE.read_text(encoding="utf-8")
    assert "-Action restore" in RESTORE.read_text(encoding="utf-8")


def test_deploy_does_not_copy_python_bearing_dev_folders():
    source = DEPLOY.read_text(encoding="utf-8", errors="replace").lower()
    assert '"%~dp0tests"' not in source
    assert "/xf *.py *.pyc" in source
    assert "prepare_launch.bat" in source
    assert "*.uefnproject" in source
    assert "setlocal disabledelayedexpansion" in source
    assert "syntax passing != working in the editor" in source
    assert "*.bat text eol=crlf" in GIT_ATTRIBUTES.read_text(encoding="utf-8")


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_prepare_restore_round_trip_and_collision_preflight(tmp_path):
    projects = tmp_path / "Fortnite Projects"
    project = projects / "P"
    stash_base = tmp_path / "local" / "stash"
    (project / "Content" / "Python" / "pkg").mkdir(parents=True)
    (project / "Content" / "hidden_pkg").mkdir()
    (project / "manifest.json").mkdir()
    (project / "tests").mkdir()
    (project / "P.uefnproject").write_text("{}", encoding="utf-8")
    (project / "Content" / "Python" / "init.py").write_text("init", encoding="utf-8")
    (project / "Content" / "Python" / "pkg" / "tool.py").write_text("tool", encoding="utf-8")
    (project / "tests" / "test_one.py").write_text("test", encoding="utf-8")
    hidden_python = project / "Content" / "hidden_pkg" / "hidden.py"
    hidden_python.write_text("hidden", encoding="utf-8")
    (project / "manifest.json" / "tool.py").write_text("manifest path", encoding="utf-8")
    (project / "keep.txt").write_text("keep", encoding="utf-8")
    subprocess.run(["attrib", "+H", str(project / "Content" / "hidden_pkg")], check=True)

    base = [
        POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
        "-Project", str(project), "-ProjectsRoot", str(projects),
        "-StashRoot", str(stash_base),
    ]
    prepared = subprocess.run(
        [*base, "-Action", "prepare"], capture_output=True, text=True, check=False
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    assert list(project.rglob("*.py")) == []
    assert (project / "keep.txt").read_text(encoding="utf-8") == "keep"
    active_stash = stash_base / "P"
    assert len(list(active_stash.rglob("*.py"))) == 5

    second_prepare = subprocess.run(
        [*base, "-Action", "prepare"], capture_output=True, text=True, check=False
    )
    assert second_prepare.returncode != 0
    assert "active Python stash" in second_prepare.stdout + second_prepare.stderr

    collision = project / "tests" / "test_one.py"
    collision.write_text("new", encoding="utf-8")
    blocked = subprocess.run(
        [*base, "-Action", "restore"], capture_output=True, text=True, check=False
    )
    assert blocked.returncode != 0
    assert "Restore collision" in blocked.stdout + blocked.stderr
    assert len(list(active_stash.rglob("*.py"))) == 5
    assert list(project.rglob("*.py")) == [collision]

    collision.unlink()
    restored = subprocess.run(
        [*base, "-Action", "restore"], capture_output=True, text=True, check=False
    )
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert sorted(p.relative_to(project).as_posix() for p in project.rglob("*.py")) == [
        "Content/Python/init.py",
        "Content/Python/pkg/tool.py",
        "Content/hidden_pkg/hidden.py",
        "manifest.json/tool.py",
        "tests/test_one.py",
    ]
    assert not active_stash.exists()


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_prepare_failure_rolls_back_and_removes_orphan_stash(tmp_path):
    projects = tmp_path / "Fortnite Projects"
    project = projects / "P"
    stash_base = tmp_path / "local" / "stash"
    project.mkdir(parents=True)
    (project / "P.uefnproject").write_text("{}", encoding="utf-8")
    first = project / "a.py"
    locked = project / "z.py"
    first.write_text("first", encoding="utf-8")
    locked.write_text("locked", encoding="utf-8")

    command = [
        POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
        "-Project", str(project), "-ProjectsRoot", str(projects),
        "-StashRoot", str(stash_base), "-Action", "prepare",
    ]
    with locked.open("r", encoding="utf-8"):
        failed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert failed.returncode != 0
    assert "rolled back" in (failed.stdout + failed.stderr)
    assert first.read_text(encoding="utf-8") == "first"
    assert locked.read_text(encoding="utf-8") == "locked"
    assert not (stash_base / "P").exists()


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_recovers_an_interrupted_preparing_manifest(tmp_path):
    projects = tmp_path / "Fortnite Projects"
    project = projects / "P"
    stash_base = tmp_path / "local" / "stash"
    stash = stash_base / "P"
    data = stash / "files"
    project.mkdir(parents=True)
    data.mkdir(parents=True)
    (project / "P.uefnproject").write_text("{}", encoding="utf-8")
    (data / "moved.py").write_text("moved", encoding="utf-8")
    (project / "not_moved.py").write_text("not moved", encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "state": "preparing",
        "project_path": str(project.resolve()),
        "prepared_at": "2026-08-23T00:00:00Z",
        "file_count": 2,
        "relative_files": ["moved.py", "not_moved.py"],
    }
    (stash / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    restored = subprocess.run([
        POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
        "-Project", str(project), "-ProjectsRoot", str(projects),
        "-StashRoot", str(stash_base), "-Action", "restore",
    ], capture_output=True, text=True, check=False)

    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert (project / "moved.py").read_text(encoding="utf-8") == "moved"
    assert (project / "not_moved.py").read_text(encoding="utf-8") == "not moved"
    assert not stash.exists()


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_resumes_after_interruption_mid_restore(tmp_path):
    projects = tmp_path / "Fortnite Projects"
    project = projects / "P"
    stash_base = tmp_path / "local" / "stash"
    stash = stash_base / "P"
    data = stash / "files"
    project.mkdir(parents=True)
    data.mkdir(parents=True)
    (project / "P.uefnproject").write_text("{}", encoding="utf-8")
    (project / "already_restored.py").write_text("restored", encoding="utf-8")
    (data / "still_stashed.py").write_text("stashed", encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "state": "restoring",
        "project_path": str(project.resolve()),
        "prepared_at": "2026-08-23T00:00:00Z",
        "file_count": 2,
        "relative_files": ["already_restored.py", "still_stashed.py"],
    }
    (stash / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    restored = subprocess.run([
        POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
        "-Project", str(project), "-ProjectsRoot", str(projects),
        "-StashRoot", str(stash_base), "-Action", "restore",
    ], capture_output=True, text=True, check=False)

    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert (project / "already_restored.py").read_text(encoding="utf-8") == "restored"
    assert (project / "still_stashed.py").read_text(encoding="utf-8") == "stashed"
    assert not stash.exists()
