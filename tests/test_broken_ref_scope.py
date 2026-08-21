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
