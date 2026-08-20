"""
Safety invariants for reference_auditor.
==============================================================================
UEFN 42.00 (UE 6.0) removed EditorAssetLibrary.find_package_referencers. The
old helper swallowed the AttributeError and returned [], which every orphan
check reads as "nothing references this asset, safe to delete". With
ref_delete_orphans(dry_run=False) that answer deletes the user's project.

These tests pin the invariant that made that possible:
    a failed reference lookup must NEVER be indistinguishable from zero refs.
"""

from __future__ import annotations

import importlib

import pytest

ra = importlib.import_module("UEFN_Toolbelt.tools.reference_auditor")


@pytest.fixture
def no_reference_api(monkeypatch):
    """Simulate an engine build with no reference-lookup API at all."""
    import unreal

    class _AssetLibWithoutRefs:
        """EditorAssetLibrary as of 42.00 — no find_package_referencers."""

    class _RegistryWithoutRefs:
        """Asset Registry with no get_referencers fallback either."""

    class _RegistryHelpers:
        @staticmethod
        def get_asset_registry():
            return _RegistryWithoutRefs()

    monkeypatch.setattr(unreal, "EditorAssetLibrary", _AssetLibWithoutRefs)
    monkeypatch.setattr(unreal, "AssetRegistryHelpers", _RegistryHelpers)

    monkeypatch.setattr(ra, "_REF_LOOKUP", None)
    monkeypatch.setattr(ra, "_REF_LOOKUP_PROBED", False)
    yield
    ra._REF_LOOKUP = None
    ra._REF_LOOKUP_PROBED = False


# ── The invariant ─────────────────────────────────────────────────────────────

def test_missing_api_raises_instead_of_returning_empty(no_reference_api):
    """[] means 'zero referencers'. A dead API must not be able to say that."""
    assert ra.reference_lookup_available() is False
    with pytest.raises(ra.ReferenceLookupUnavailable):
        ra._get_referencers("/Project/Meshes/SM_Anything")


def test_delete_orphans_refuses_rather_than_deleting(no_reference_api):
    """The data-loss path. Must refuse even when explicitly told not to dry-run."""
    result = ra.ref_delete_orphans(scan_path="/Project", dry_run=False)
    assert result["status"] == "error"
    assert result["reason"] == "reference_api_unavailable"
    assert result["deleted"] == 0


def test_orphan_and_texture_audits_refuse(no_reference_api):
    """Both feed the delete decision, so neither may report a bogus zero."""
    for tool in (ra.ref_audit_orphans, ra.ref_audit_unused_textures):
        result = tool(scan_path="/Project")
        assert result["status"] == "error", tool.__name__
        assert result["reason"] == "reference_api_unavailable", tool.__name__


# ── Graceful degradation of the parts that still work ─────────────────────────

def test_referencer_count_is_soft_for_display_only(no_reference_api):
    """The redirector scan prints a count but never deletes on it — None, not 0."""
    assert ra._count_referencers_soft("/Project/Meshes/SM_Anything") is None


def test_full_report_degrades_per_section(no_reference_api, monkeypatch):
    """Read-only, so it still reports what it can and marks the rest unavailable."""
    monkeypatch.setattr(ra, "_list_all_assets", lambda _p: [])
    monkeypatch.setattr(ra, "_ensure_dir", lambda: None)
    monkeypatch.setattr(ra, "_REPORT_PATH", str(__import__("tempfile").mkstemp()[1]))

    report = ra._full_report("/Project", [])
    assert report["reference_lookup_available"] is False
    assert report["summary"]["orphaned_assets"] == "unavailable"
    assert report["summary"]["unused_textures"] == "unavailable"
    # Sections that never needed reference lookup still produce real numbers.
    assert isinstance(report["summary"]["redirectors"], int)
    assert isinstance(report["summary"]["duplicate_names"], int)


# ── The working path still works ──────────────────────────────────────────────

def test_legacy_api_is_used_when_present(monkeypatch):
    """Pre-42.00 builds keep the original code path."""
    import unreal

    class _AssetLibWithRefs:
        @staticmethod
        def find_package_referencers(path):
            return ["/Project/Materials/M_User"]

    monkeypatch.setattr(unreal, "EditorAssetLibrary", _AssetLibWithRefs)
    monkeypatch.setattr(ra, "_REF_LOOKUP", None)
    monkeypatch.setattr(ra, "_REF_LOOKUP_PROBED", False)

    assert ra.reference_lookup_available() is True
    assert ra._get_referencers("/Project/Meshes/SM_X") == ["/Project/Materials/M_User"]

    ra._REF_LOOKUP = None
    ra._REF_LOOKUP_PROBED = False


def test_asset_registry_fallback_is_used_when_legacy_is_gone(monkeypatch):
    """UE 6.0 path — the Toolbelt keeps working instead of just failing safely."""
    import unreal

    class _AssetLibWithoutRefs:
        pass

    class _Registry:
        @staticmethod
        def get_referencers(package_name, options=None):
            assert "." not in package_name, "must be a package name, not an object path"
            return ["/Project/Materials/M_User"]

    class _RegistryHelpers:
        @staticmethod
        def get_asset_registry():
            return _Registry()

    monkeypatch.setattr(unreal, "EditorAssetLibrary", _AssetLibWithoutRefs)
    monkeypatch.setattr(unreal, "AssetRegistryHelpers", _RegistryHelpers)
    monkeypatch.setattr(ra, "_REF_LOOKUP", None)
    monkeypatch.setattr(ra, "_REF_LOOKUP_PROBED", False)

    assert ra.reference_lookup_available() is True
    assert ra._get_referencers("/Project/Meshes/SM_X.SM_X") == ["/Project/Materials/M_User"]

    ra._REF_LOOKUP = None
    ra._REF_LOOKUP_PROBED = False


# ── A present-but-unusable API must not be trusted ────────────────────────────

def test_fallback_with_a_wrong_signature_counts_as_unavailable(monkeypatch):
    """
    get_referencers exists but rejects our arguments. Attribute presence alone
    would mark the strategy usable, the guard would pass, and the scan would then
    raise from inside its loop -- surfacing None instead of a clean refusal.
    """
    import unreal

    class _AssetLibWithoutRefs:
        pass

    class _RegistryWithWrongSignature:
        @staticmethod
        def get_referencers(*args, **kwargs):
            raise TypeError("get_referencers(): incompatible arguments")

    class _RegistryHelpers:
        @staticmethod
        def get_asset_registry():
            return _RegistryWithWrongSignature()

    monkeypatch.setattr(unreal, "EditorAssetLibrary", _AssetLibWithoutRefs)
    monkeypatch.setattr(unreal, "AssetRegistryHelpers", _RegistryHelpers)
    monkeypatch.setattr(ra, "_REF_LOOKUP", None)
    monkeypatch.setattr(ra, "_REF_LOOKUP_PROBED", False)

    assert ra.reference_lookup_available() is False

    result = ra.ref_delete_orphans(scan_path="/Project", dry_run=False)
    assert result["status"] == "error"
    assert result["deleted"] == 0

    ra._REF_LOOKUP = None
    ra._REF_LOOKUP_PROBED = False


def test_a_missing_probe_asset_does_not_disqualify_a_working_api(monkeypatch):
    """
    The probe path is synthetic. An API that raises 'asset not found' for it is
    still a working API and must be kept -- otherwise the validator would reject
    every healthy build.
    """
    import unreal

    class _AssetLibWithoutRefs:
        pass

    class _RegistryStrictAboutPaths:
        @staticmethod
        def get_referencers(package_name, options=None):
            if package_name == "/Engine/Transient":
                raise RuntimeError("asset not found")
            return ["/Project/Materials/M_User"]

    class _RegistryHelpers:
        @staticmethod
        def get_asset_registry():
            return _RegistryStrictAboutPaths()

    monkeypatch.setattr(unreal, "EditorAssetLibrary", _AssetLibWithoutRefs)
    monkeypatch.setattr(unreal, "AssetRegistryHelpers", _RegistryHelpers)
    monkeypatch.setattr(ra, "_REF_LOOKUP", None)
    monkeypatch.setattr(ra, "_REF_LOOKUP_PROBED", False)

    assert ra.reference_lookup_available() is True
    assert ra._get_referencers("/Project/Meshes/SM_X") == ["/Project/Materials/M_User"]

    ra._REF_LOOKUP = None
    ra._REF_LOOKUP_PROBED = False


# ── Reference-tree roots must never be classified as orphans ──────────────────
# Found on a live UEFN 42.00 project: GameFeatureData (the .uplugin descriptor
# asset) and the default HLOD layer both report 0 package referencers, because
# what points at them is configuration, not another package. The old skip list
# covered maps and blueprints only, so ref_delete_orphans(dry_run=False) would
# have deleted the descriptor and broken the project.

def test_project_descriptor_class_is_protected():
    assert "GameFeatureData" in ra.ROOT_ASSET_CLASSES
    assert "HLODLayer" in ra.ROOT_ASSET_CLASSES


def test_mount_root_packages_are_protected_but_content_is_not():
    assert ra._is_root_level_package("/MyProject/GameFeatureData") is True
    assert ra._is_root_level_package("/MyProject/MyProject_DefaultHLODLayer") is True
    assert ra._is_root_level_package("/MyProject/Meshes/SM_Rock") is False
    assert ra._is_root_level_package("/MyProject/Organized/Materials/M_Wall") is False


def test_zero_referencer_descriptor_is_not_reported_as_an_orphan(monkeypatch):
    monkeypatch.setattr(ra, "_list_all_assets", lambda *a, **k: [
        "/MyProject/GameFeatureData",
        "/MyProject/Meshes/SM_Unused",
    ])
    monkeypatch.setattr(ra, "_get_asset_class_name",
                        lambda p: "GameFeatureData" if "GameFeature" in p else "StaticMesh")
    monkeypatch.setattr(ra, "_get_referencers", lambda p: [])

    orphans = ra._scan_orphans("/MyProject", [])

    paths = [o["path"] for o in orphans]
    assert "/MyProject/GameFeatureData" not in paths
    assert "/MyProject/Meshes/SM_Unused" in paths, "genuine orphans must still be found"


def test_delete_refuses_a_root_asset_even_if_the_scan_hands_it_over(monkeypatch):
    """
    Defence in depth. Deletion is permanent, so a regression in _scan_orphans
    must not be enough on its own to destroy the project.
    """
    monkeypatch.setattr(ra, "_scan_orphans", lambda *a, **k: [
        {"path": "/MyProject/GameFeatureData", "class": "GameFeatureData"},
        {"path": "/MyProject/Meshes/SM_Unused", "class": "StaticMesh"},
    ])

    deleted: list[str] = []

    class _Lib:
        @staticmethod
        def delete_asset(path):
            deleted.append(path)
            return True

    import unreal
    monkeypatch.setattr(unreal, "EditorAssetLibrary", _Lib)

    ra._delete_orphans("/MyProject", False, [])

    assert "/MyProject/GameFeatureData" not in deleted, "deleted the project descriptor"
    assert deleted == ["/MyProject/Meshes/SM_Unused"]


# ── Unscannable paths must not reach the lookup ───────────────────────────────

def test_level_subobjects_and_verse_digest_paths_are_not_scannable():
    assert ra._is_scannable_asset("/P/Meshes/SM_Rock.SM_Rock") is True
    # One-file-per-actor sub-objects: thousands of them, all one package.
    assert ra._is_scannable_asset(
        "/P/Lvl.Lvl:PersistentLevel.ActorFolder_UID_063C9727") is False
    # UEFN 42.00 Verse digest — EditorAssetSubsystem logs an error on lookup.
    assert ra._is_scannable_asset("/P/$Digest") is False


def test_unscannable_paths_are_never_looked_up(monkeypatch):
    """
    Regression guard for two live 42.00 symptoms: an editor error logged per
    $Digest lookup, and 3455 level sub-objects reported as 'protected', which
    made the audit read as though it had skipped the whole project.
    """
    monkeypatch.setattr(ra, "_list_all_assets", lambda *a, **k: [
        "/P/Lvl.Lvl:PersistentLevel.ActorFolder_UID_1",
        "/P/Lvl.Lvl:PersistentLevel.ActorFolder_UID_2",
        "/P/$Digest",
        "/P/Meshes/SM_Unused.SM_Unused",
    ])
    monkeypatch.setattr(ra, "_get_asset_class_name", lambda p: "StaticMesh")

    looked_up: list[str] = []

    def _spy(path):
        looked_up.append(path)
        return []

    monkeypatch.setattr(ra, "_get_referencers", _spy)

    orphans = ra._scan_orphans("/P", [])

    assert looked_up == ["/P/Meshes/SM_Unused.SM_Unused"]
    assert [o["path"] for o in orphans] == ["/P/Meshes/SM_Unused.SM_Unused"]
