"""Exercise arena placement math without simulating editor or mesh behavior."""

from __future__ import annotations

import math
from contextlib import nullcontext
from dataclasses import dataclass
from itertools import combinations

import pytest

from UEFN_Toolbelt.tools import arena_generator as ag

EXPECTED_COUNTS = {
    "small": (80, 144, 4, 8),
    "medium": (192, 280, 9, 12),
    "large": (384, 480, 16, 20),
}


@dataclass(frozen=True)
class _Vector:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True, kw_only=True)
class _Rotation:
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0


@dataclass
class _Actor:
    location: _Vector
    rotation: _Rotation
    scale: _Vector
    label: str = ""
    folder: str = ""

    def set_actor_label(self, label):
        self.label = label

    def set_folder_path(self, folder):
        self.folder = folder


@pytest.fixture(params=tuple(EXPECTED_COUNTS))
def preset(request):
    return ag.ARENA_PRESETS[request.param]


@pytest.fixture(params=(_Vector(), _Vector(100000, 100000, 60000)),
                ids=("zero-origin", "translated-origin"))
def origin(request):
    return request.param


@pytest.fixture
def placements(monkeypatch):
    actors = []

    def spawn(mesh, location, rotation=None, scale=None):
        actor = _Actor(location, rotation or _Rotation(), scale or _Vector(1, 1, 1))
        actors.append(actor)
        return actor

    monkeypatch.setattr(ag.unreal, "Vector", _Vector)
    monkeypatch.setattr(ag.unreal, "Rotator", _Rotation)
    monkeypatch.setattr(ag, "spawn_static_mesh_actor", spawn)
    monkeypatch.setattr(ag, "_resolve_mesh", lambda name: "/Engine/BasicShapes/Cube")
    monkeypatch.setattr(ag, "undo_transaction", lambda label: nullcontext())
    return actors


def _point(actor, origin):
    # Trig round-off must not disguise two pads occupying the same position.
    return tuple(round(getattr(actor.location, axis) - getattr(origin, axis), 6)
                 for axis in ("x", "y", "z"))


def test_wall_positions_are_unique(preset, origin, placements):
    placed = []
    red, blue = ag._place_walls(preset, origin, placed)

    assert len(placed) == EXPECTED_COUNTS[preset.name][1]
    assert len({_point(actor, origin) for actor in placed}) == len(placed)
    assert len(red) == len(blue) == len(placed) // 2
    assert {id(actor) for actor in red + blue} == {id(actor) for actor in placed}


def test_perimeter_is_symmetric_and_outside_floor(preset, origin, placements):
    placed = []
    ag._place_walls(preset, origin, placed)
    points = {_point(actor, origin) for actor in placed}
    half_x = preset.floor_tiles_x * preset.tile_size / 2
    half_y = preset.floor_tiles_y * preset.tile_size / 2
    half_tile = preset.tile_size / 2

    assert {(-x, y, z) for x, y, z in points} == points
    assert {(x, -y, z) for x, y, z in points} == points
    for actor in placed:
        x, y, z = _point(actor, origin)
        side = actor.label.split("_")[1]
        assert actor.folder == "/Arena/Walls"
        assert actor.scale == _Vector(preset.tile_size / 100,
                                      preset.tile_size / 100, preset.tile_size / 100)
        assert actor.rotation == _Rotation(yaw=90 if side in ("E", "W") else 0)
        assert z >= half_tile
        if side in ("N", "S"):
            assert abs(y) - half_tile == half_y
            assert abs(x) + half_tile <= half_x
        else:
            assert abs(x) - half_tile == half_x
            assert abs(y) + half_tile <= half_y


def test_wall_tile_volumes_do_not_overlap(preset, origin, placements):
    placed = []
    ag._place_walls(preset, origin, placed)

    # The configured grid cells (including cube fallbacks) may touch, never
    # interpenetrate. This also catches offset corner overlaps, not only duplicates.
    for first, second in combinations(placed, 2):
        separations = (abs(getattr(first.location, axis) - getattr(second.location, axis))
                       for axis in ("x", "y", "z"))
        assert any(distance >= preset.tile_size - 1e-6 for distance in separations), (
            first.label, second.label
        )


def test_spawn_positions_are_unique_within_each_team(preset, origin, placements):
    placed = []
    teams = ag._place_spawns(preset, origin, placed)

    assert len(placed) == EXPECTED_COUNTS[preset.name][3]
    for actors in teams:
        assert len(actors) == preset.spawn_count
        assert len({_point(actor, origin) for actor in actors}) == preset.spawn_count


def test_spawn_clusters_have_mirrored_centers_and_ellipses(preset, origin, placements):
    placed = []
    red, blue = ag._place_spawns(preset, origin, placed)
    red_points = {_point(actor, origin) for actor in red}
    blue_points = {_point(actor, origin) for actor in blue}
    center_x = preset.floor_tiles_x * preset.tile_size * 0.3
    radius_x = preset.spawn_spread * 0.4

    assert {(-x, y, z) for x, y, z in red_points} == blue_points
    for team, sign, actors in (("Red", 1, red), ("Blue", -1, blue)):
        points = [_point(actor, origin) for actor in actors]
        assert sum(x for x, _, _ in points) / len(points) == pytest.approx(sign * center_x)
        assert sum(y for _, y, _ in points) / len(points) == pytest.approx(0, abs=1e-6)
        assert {(x, -y, z) for x, y, z in points} == set(points)
        for actor, (x, y, z) in zip(actors, points, strict=True):
            assert sign * x > 0
            assert z == 5
            assert ((x - sign * center_x) / radius_x) ** 2 + (
                y / preset.spawn_spread
            ) ** 2 == pytest.approx(1, abs=1e-8)
            assert actor.folder == f"/Arena/Spawns/{team}"
            assert actor.scale == _Vector(1, 1, 1)


@pytest.mark.parametrize("apply_team_colors", (False, True))
def test_generate_preserves_counts_labels_and_color_option(
    preset, origin, placements, monkeypatch, apply_team_colors
):
    colored = []
    monkeypatch.setattr(ag, "_apply_team_colors", lambda red, blue: colored.append((red, blue)))

    result = ag.run_generate(
        size=preset.name,
        origin=(origin.x, origin.y, origin.z),
        apply_team_colors=apply_team_colors,
    )

    floor, walls, platform, spawns = EXPECTED_COUNTS[preset.name]
    assert result == {"status": "ok", "placed": floor + walls + platform + spawns,
                      "red_spawns": spawns // 2, "blue_spawns": spawns // 2}
    assert len(placements) == result["placed"]
    assert len({actor.label for actor in placements}) == len(placements)
    assert len({_point(actor, origin) for actor in placements}) == len(placements)
    for prefix, expected in (("Floor_", floor), ("Wall_", walls),
                             ("Platform_", platform), ("SpawnPad_", spawns)):
        assert sum(actor.label.startswith(prefix) for actor in placements) == expected
    assert len(colored) == int(apply_team_colors)
    if colored:
        assert all(len(team) == (walls + spawns) // 2 for team in colored[0])
    assert all(math.isfinite(value) for actor in placements
               for value in (actor.location.x, actor.location.y, actor.location.z))
