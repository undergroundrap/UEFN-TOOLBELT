"""
The deploy stamp: which build is actually running in this project.

Two live test runs were lost in one session to a project sitting silently on a
40-minute-old build. The editor said nothing — the results just looked wrong in
ways that read as code bugs, and finding out took comparing file mtimes across
projects on disk.

deploy.bat writes _build_stamp.json into the DESTINATION after copying, so the
stamp describes what was deployed rather than what the repo contains. Every
startup log and every hard_reload now carries it.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import UEFN_Toolbelt as tb

REPO = Path(__file__).resolve().parents[1]
STAMP = Path(tb.__file__).parent / "_build_stamp.json"


def _reload_pkg():
    """build_info reads from disk each call, so no reload is needed — but keep
    the import fresh if a future change caches it."""
    return importlib.import_module("UEFN_Toolbelt")


def test_missing_stamp_reports_unknown_rather_than_raising():
    """A hand-copied install has no stamp. That must degrade, not explode."""
    assert not STAMP.exists(), "repo should never carry a stamp (see .gitignore)"
    info = tb.build_info()
    assert info == {"commit": "unknown", "deployed_at": "unknown",
                    "project": "unknown"}


def test_stamp_is_read_when_present(tmp_path, monkeypatch):
    STAMP.write_text(json.dumps({
        "commit": "abc1234",
        "deployed_at": "2026-08-21T18:30:00",
        "project": "Device_API_Mapping",
    }), encoding="utf-8")
    try:
        info = tb.build_info()
        assert info["commit"] == "abc1234"
        assert info["project"] == "Device_API_Mapping"
        assert "abc1234" in tb.build_line()
        assert "Device_API_Mapping" in tb.build_line()
    finally:
        STAMP.unlink()


def test_malformed_stamp_degrades_quietly():
    """A truncated write must not take the whole package down on import."""
    STAMP.write_text("{not json", encoding="utf-8")
    try:
        assert tb.build_info()["commit"] == "unknown"
    finally:
        STAMP.unlink()


def test_dirty_working_tree_is_visible_in_the_commit_field():
    """deploy.bat appends +dirty. A stamp that hides local edits is worse than
    no stamp: it claims a provenance the files do not have."""
    STAMP.write_text(json.dumps({"commit": "abc1234+dirty"}), encoding="utf-8")
    try:
        assert tb.build_info()["commit"].endswith("+dirty")
    finally:
        STAMP.unlink()


def test_deploy_script_still_writes_the_stamp():
    """Guards the other half: build_info is useless if deploy stops stamping."""
    text = (REPO / "deploy.bat").read_text(encoding="utf-8", errors="replace")
    assert "_build_stamp.json" in text, "deploy.bat no longer writes the stamp"
    assert "rev-parse --short HEAD" in text, "stamp no longer records the commit"
    assert "STAMP_FILE" in text
    # Written after the copy, or it would describe the wrong tree.
    assert text.index("Copying UEFN_Toolbelt package") < text.index("_build_stamp.json")


def test_build_info_is_not_a_registered_tool():
    """It has to answer when the registry is empty — the Quirk #36 case it
    exists to diagnose — so it must not depend on registration."""
    from UEFN_Toolbelt.registry import get_registry

    names = [t["name"] for t in get_registry().list_tools()]
    assert "build_info" not in names
    assert callable(tb.build_info)
