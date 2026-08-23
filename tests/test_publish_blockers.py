"""Remote-validation blockers must be visible before a creator clicks Launch."""

from __future__ import annotations

import ast
from contextlib import nullcontext
from pathlib import Path

import pytest

from UEFN_Toolbelt.tools import publish_audit, sign_tools


class _TextActor:
    def __init__(self, label: str, folder: str = ""):
        self.label = label
        self.folder = folder

    def get_actor_label(self):
        return self.label

    def get_folder_path(self):
        return self.folder


class _OtherActor:
    pass


def test_publish_audit_hard_fails_on_text_render_actors(monkeypatch):
    monkeypatch.setattr(publish_audit.unreal, "TextRenderActor", _TextActor)
    result = publish_audit._check_disallowed_text_actors([
        _TextActor("Label_A"), _OtherActor(), _TextActor("Grid_B2")
    ])
    assert result["pass"] is False
    assert result["severity"] == "fail"
    assert result["count"] == 2
    assert result["labels"] == ["Label_A", "Grid_B2"]
    assert "all_text_actors=True" in result["note"]


def test_publish_audit_passes_only_when_no_text_render_actor_exists(monkeypatch):
    monkeypatch.setattr(publish_audit.unreal, "TextRenderActor", _TextActor)
    result = publish_audit._check_disallowed_text_actors([_OtherActor()])
    assert result == {
        "pass": True,
        "count": 0,
        "labels": [],
        "severity": "ok",
        "note": "No TextRenderActors — remote validation safe ✓",
    }


def test_sign_clear_explicit_all_scope_removes_every_text_actor(monkeypatch):
    actors = [_TextActor("A", "One"), _OtherActor(), _TextActor("B", "Two")]

    class _ActorSubsystem:
        def get_all_level_actors(self):
            return list(actors)

        def destroy_actor(self, actor):
            actors.remove(actor)
            return True

    actor_subsystem = _ActorSubsystem()
    monkeypatch.setattr(sign_tools.unreal, "TextRenderActor", _TextActor)
    monkeypatch.setattr(sign_tools.unreal, "EditorActorSubsystem", object())
    monkeypatch.setattr(sign_tools.unreal, "get_editor_subsystem", lambda _kind: actor_subsystem)
    monkeypatch.setattr(sign_tools.unreal, "ScopedEditorTransaction", lambda _name: nullcontext())

    result = sign_tools.run_sign_clear(all_text_actors=True, dry_run=False)
    assert result["status"] == "ok"
    assert result["deleted"] == 2
    assert result["attempted"] == 2
    assert result["all_text_actors"] is True
    assert actors == [_OtherActor()] or (
        len(actors) == 1 and isinstance(actors[0], _OtherActor)
    )


def test_every_text_spawner_calls_publish_warning_and_returns_cleanup():
    expected = {
        "text_painter.py": [
            "run_text_place", "run_text_label_selection",
            "run_text_paint_grid", "run_text_color_cycle",
        ],
        "sign_tools.py": ["run_sign_spawn_bulk", "run_label_attach"],
    }
    tools = Path("Content/Python/UEFN_Toolbelt/tools")
    for filename, functions in expected.items():
        source = (tools / filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
        function_nodes = {
            node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        for function in functions:
            assert function in function_nodes
            calls = [
                node.func.id
                for node in ast.walk(function_nodes[function])
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            ]
            assert "_warn_publish_blocker" in calls, function
            assert "_publish_blocker_result" in calls, function


def test_integration_suite_cleans_labels_and_localization_actor_through_checked_path():
    source = Path(
        "Content/Python/UEFN_Toolbelt/tools/integration_test.py"
    ).read_text(encoding="utf-8")
    assert 'tb.run("sign_clear", all_text_actors=True, dry_run=False)' in source
    assert "remaining_text = [" in source
    assert "actor_sub.destroy_actor(txt_actor)" in source
    assert "folder=test_folder" in source
    assert "txt_actor.destroy_actor()" not in source
