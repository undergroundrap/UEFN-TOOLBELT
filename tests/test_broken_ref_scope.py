"""
What ref_audit_broken can and cannot see.

On Device_API_Mapping it returned 0 broken across 3405 actors. That reads as
"the island is clean" and does not mean it: a slot is only judged when the
actor's CLASS DEFAULT fills it, and a plain StaticMeshActor takes its mesh
per-instance. For those, a severed mesh and a mesh that was never set are the
same null, so the check skips them.

The first version had the opposite failure — it flagged any empty
StaticMeshComponent and called 13 healthy actors broken on a 93-actor level.
The CDO comparison fixed that but narrowed the scope, and the scope was invisible
in the result. These tests pin both halves so the number stays honest.
"""

from __future__ import annotations

import importlib

ra = importlib.import_module("UEFN_Toolbelt.tools.reference_auditor")


class _Comp:
    def __init__(self, name: str, mesh: object | None, editor_only: bool = False):
        self._name, self._mesh, self._eo = name, mesh, editor_only

    def get_name(self) -> str:
        return self._name

    def get_editor_property(self, prop: str):
        if prop == "is_editor_only":
            return self._eo
        if prop == "static_mesh":
            return self._mesh
        raise KeyError(prop)


class _Mesh:
    def __init__(self, path: str):
        self._p = path

    def get_path_name(self) -> str:
        return self._p


class _Actor:
    """Duck-typed actor: instance components plus the class default's."""

    def __init__(self, instance: list[_Comp], default: list[_Comp]):
        self._i, self._d = instance, default

    def get_components_by_class(self, _cls):
        return self._i

    def get_class(self):
        outer = self

        class _Cls:
            @staticmethod
            def get_default_object():
                class _CDO:
                    @staticmethod
                    def get_components_by_class(_c):
                        return outer._d
                return _CDO()
        return _Cls()


def test_severed_reference_is_flagged():
    """CDO ships a mesh, the instance has none — the reference was severed."""
    mesh = _Mesh("/X/Meshes/SM_Wall.SM_Wall")
    actor = _Actor([_Comp("Body", None)], [_Comp("Body", mesh)])
    slots, comparable = ra._empty_slots(actor)
    assert comparable == 1
    assert len(slots) == 1
    assert slots[0]["component"] == "Body"
    assert "SM_Wall" in slots[0]["expected"]


def test_per_instance_mesh_is_out_of_scope_not_clean():
    """The blind spot, stated as a fact rather than left to look like a pass.

    A StaticMeshActor's CDO has no mesh, so a null instance mesh is unjudgeable.
    It must not be flagged, and it must not count toward comparable_slots —
    otherwise "0 broken" would borrow credibility from actors never checked.
    """
    actor = _Actor([_Comp("StaticMeshComponent0", None)],
                   [_Comp("StaticMeshComponent0", None)])
    slots, comparable = ra._empty_slots(actor)
    assert slots == []
    assert comparable == 0


def test_healthy_actor_is_comparable_and_clean():
    """In scope and intact — this is what a real negative looks like."""
    mesh = _Mesh("/X/Meshes/SM_Door.SM_Door")
    actor = _Actor([_Comp("Body", mesh)], [_Comp("Body", mesh)])
    slots, comparable = ra._empty_slots(actor)
    assert slots == []
    assert comparable == 1


def test_editor_only_component_is_never_flagged():
    """Regression on the 13 false positives: editor-side visualisation."""
    mesh = _Mesh("/X/Meshes/SM_Gizmo.SM_Gizmo")
    actor = _Actor([_Comp("EditorOnlyBillboard", None, editor_only=True)],
                   [_Comp("EditorOnlyBillboard", mesh)])
    slots, comparable = ra._empty_slots(actor)
    assert slots == []
    # Skipped, therefore not judged, therefore not comparable.
    assert comparable == 0


# ── Dependency-based detection ────────────────────────────────────────────────
#
# The CDO comparison scored comparable_slots 0 on a real 3405-actor island, so
# it detects nothing there. The asset registry's dependency table is built from
# the saved package and still names an asset after that asset is deleted, which
# is the only place the severed path survives.

class _Pkg:
    def __init__(self, name: str):
        self._n = name

    def get_name(self) -> str:
        return self._n


class _PkgActor:
    def __init__(self, label: str, package: str):
        self._l, self._p = label, package

    def get_actor_label(self) -> str:
        return self._l

    def get_package(self):
        return _Pkg(self._p)


def _with_deps(monkeypatch, deps: dict[str, list[str]], exists: set[str], raiser=False):
    """Install a fake dependency lookup, mount, and asset-existence oracle."""
    import unreal

    monkeypatch.setattr(ra, "detect_project_mount", lambda: "Game", raising=False)
    monkeypatch.setattr(ra, "_DEP_LOOKUP_PROBED", True, raising=False)
    monkeypatch.setattr(ra, "_DEP_LOOKUP", lambda pkg: deps.get(pkg, []), raising=False)

    def _exists(path):
        if raiser:
            raise RuntimeError("registry unavailable")
        return path in exists

    monkeypatch.setattr(unreal.EditorAssetLibrary, "does_asset_exist", _exists,
                        raising=False)


def test_missing_dependency_is_named_with_its_referrer(monkeypatch):
    _with_deps(
        monkeypatch,
        deps={"/Game/L/A_0": ["/Game/Meshes/SM_Gone", "/Game/Meshes/SM_Here"]},
        exists={"/Game/Meshes/SM_Here"},
    )
    missing, checked, pkgs, unver = ra._missing_dependencies([_PkgActor("Wall_01", "/Game/L/A_0")], {})
    assert checked == 2 and pkgs == 1
    assert list(missing) == ["/Game/Meshes/SM_Gone"]
    assert missing["/Game/Meshes/SM_Gone"] == {"Wall_01"}


def test_script_and_transient_deps_are_not_counted(monkeypatch):
    """They are not assets, so they can never be missing — and must not inflate
    dependencies_checked, which exists to say how much was really examined."""
    _with_deps(
        monkeypatch,
        deps={"/Game/L/A_0": ["/Script/Engine", "/Engine/Transient", "/Verse/X"]},
        exists=set(),
    )
    missing, checked, _, unver = ra._missing_dependencies([_PkgActor("A", "/Game/L/A_0")], {})
    assert missing == {} and checked == 0


def test_unanswerable_existence_never_reports_missing(monkeypatch):
    """"Couldn't tell" must not become "it's gone" — this tool drives repairs."""
    _with_deps(monkeypatch, deps={"/Game/L/A_0": ["/Game/Meshes/SM_X"]},
               exists=set(), raiser=True)
    missing, checked, _, unver = ra._missing_dependencies([_PkgActor("A", "/Game/L/A_0")], {})
    assert missing == {}
    assert checked == 1


def test_one_package_per_actor_is_deduplicated(monkeypatch):
    """Under OFPA each actor has its own package; shared ones must not double-count."""
    _with_deps(monkeypatch, deps={"/Game/L/A_0": ["/Game/Meshes/SM_Gone"]}, exists=set())
    actors = [_PkgActor("A", "/Game/L/A_0"), _PkgActor("B", "/Game/L/A_0")]
    missing, checked, pkgs, unver = ra._missing_dependencies(actors, {})
    assert pkgs == 1 and checked == 1
    assert missing["/Game/Meshes/SM_Gone"] == {"A"}


def test_no_dependency_lookup_reports_zero_not_clean(monkeypatch):
    """Unavailable API must yield 0 checked so status falls to inconclusive."""
    monkeypatch.setattr(ra, "_DEP_LOOKUP_PROBED", True, raising=False)
    monkeypatch.setattr(ra, "_DEP_LOOKUP", None, raising=False)
    missing, checked, pkgs, unver = ra._missing_dependencies([_PkgActor("A", "/Game/L/A_0")], {})
    assert (missing, checked, pkgs, unver) == ({}, 0, 0, 0)


def test_other_mounts_are_unverifiable_not_missing(monkeypatch):
    """The 383-false-positive case, pinned.

    On Device_API_Mapping the first dependency version reported 383 missing
    assets, every one Epic plugin content that plainly exists — Teleporters and
    Item Spawners working in the level. does_asset_exist cannot browse those
    mounts and returns False for "cannot see" exactly as for "not there".

    Anything outside the project mount must be counted, never accused.
    """
    _with_deps(
        monkeypatch,
        deps={"/Game/L/A_0": [
            "/CreativeCoreDevices/Device_Teleporter_V2",
            "/CRD_Water/Blueprints/Device_Water_V2",
            "/Game/Meshes/SM_Gone",
        ]},
        exists=set(),          # nothing "exists" — the harshest possible oracle
    )
    missing, checked, _, unver = ra._missing_dependencies(
        [_PkgActor("Teleporter", "/Game/L/A_0")], {})

    assert unver == 2, "Epic mounts must be counted as unverifiable"
    assert checked == 1, "only the project-mount dependency is judged"
    assert list(missing) == ["/Game/Meshes/SM_Gone"], (
        f"reported Epic content as missing: {sorted(missing)}"
    )


def test_ofpa_actor_packages_are_unverifiable_not_missing(monkeypatch):
    """The 8-false-positive case, pinned with paths from the live log.

    /__ExternalActors__/ is where the level's own actors are stored under OFPA —
    packages_checked was 3394 because that IS the actor package set. A dependency
    on one is an inter-actor reference, resolved by World Partition's actor
    descriptors. One of these was referenced by 179 actors that were working
    fine; had it truly been missing, the island would have been visibly broken.
    """
    _with_deps(
        monkeypatch,
        deps={"/Game/L/A_0": [
            "/Game/__ExternalActors__/L/A/GO/HJW5TJWA4NTOFM8XME22M9",
            "/Game/__ExternalObjects__/L/C/M0/34O2SSTF9J8VE86XN351XC",
            "/Game/Organized/Meshes/SM_Severed",
        ]},
        exists=set(),
    )
    missing, checked, _, unver = ra._missing_dependencies(
        [_PkgActor("Cove Stone Wall C", "/Game/L/A_0")], {})

    assert unver == 2, "OFPA containers must be counted, not accused"
    assert checked == 1
    assert list(missing) == ["/Game/Organized/Meshes/SM_Severed"], (
        f"reported an actor container as a missing asset: {sorted(missing)}"
    )
