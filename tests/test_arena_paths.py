"""
Arena asset paths must resolve against the user's project mount.
==============================================================================
Regression guard. These were hardcoded under /Game/, which in UEFN is Epic's
Fortnite install (FortniteGame/Content), not the creator's project — see
UEFN_QUIRKS.md #23. Mesh lookups could therefore never resolve and every arena
silently fell back, while the team-material WRITES landed somewhere the project
cannot reference, leaving each coloured actor pointing at a dangling material.
"""

from __future__ import annotations

import pytest

from UEFN_Toolbelt.tools import arena_generator as ag


@pytest.fixture
def mounted(monkeypatch):
    monkeypatch.setattr(ag, "detect_project_mount", lambda: "MyIsland")


def test_asset_paths_use_the_project_mount(mounted):
    path = ag._project_asset_path("UEFN_Toolbelt/Meshes", "SM_Floor_Tile")
    assert path == "/MyIsland/UEFN_Toolbelt/Meshes/SM_Floor_Tile"
    assert not path.startswith("/Game/")


def test_team_material_paths_are_written_into_the_project(mounted):
    for path in (ag._mat_red_path(), ag._mat_blue_path()):
        assert path.startswith("/MyIsland/"), f"{path} would be unreferenceable"


def test_mesh_constants_are_names_not_paths():
    """If these regain a '/' prefix, _resolve_mesh would double-prefix them."""
    for name in (ag.MESH_FLOOR, ag.MESH_WALL, ag.MESH_PLATFORM, ag.MESH_SPAWN_PAD):
        assert "/" not in name, f"{name} must be a bare asset name"


def test_resolve_mesh_looks_under_the_project_mount(mounted, monkeypatch):
    checked: list[str] = []

    class _Lib:
        @staticmethod
        def does_asset_exist(path):
            checked.append(path)
            return True

    import unreal
    monkeypatch.setattr(unreal, "EditorAssetLibrary", _Lib)

    assert ag._resolve_mesh(ag.MESH_FLOOR) == "/MyIsland/UEFN_Toolbelt/Meshes/SM_Floor_Tile"
    assert checked == ["/MyIsland/UEFN_Toolbelt/Meshes/SM_Floor_Tile"]


def test_resolve_mesh_falls_back_when_the_asset_is_absent(mounted, monkeypatch):
    class _Lib:
        @staticmethod
        def does_asset_exist(path):
            return False

    import unreal
    monkeypatch.setattr(unreal, "EditorAssetLibrary", _Lib)
    monkeypatch.setattr(ag, "get_config",
                        lambda: type("C", (), {"get": staticmethod(lambda k: "/Engine/BasicShapes/Cube")})())

    assert ag._resolve_mesh(ag.MESH_WALL) == "/Engine/BasicShapes/Cube"
