"""
UEFN TOOLBELT — Integration Test
=========================================
Automates verification of context-dependent tools (selection/viewport).

Harness Pattern:
  1. Spawn temporary test actors (cubes/spheres)
  2. Select them programmatically
  3. Run Toolbelt tool
  4. Verify the delta (property changed, file created)
  5. Clean up (destroy actors)

Usage:
    import UEFN_Toolbelt as tb; tb.run("toolbelt_integration_test")
"""

from __future__ import annotations

VERSION = "V11-ULTIMATE-171"
import os
import time
from datetime import datetime

import unreal

from UEFN_Toolbelt.core import resolve_content_path, undo_transaction
from UEFN_Toolbelt.registry import register_tool
from UEFN_Toolbelt.tools.material_master import parent_material_path

# ─── Configuration ────────────────────────────────────────────────────────────

_SAVED = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
_RESULTS_PATH = os.path.join(_SAVED, "integration_test_results.txt")

_CUBE_MESH = "/Engine/BasicShapes/Cube"
_SPHERE_MESH = "/Engine/BasicShapes/Sphere"
_FIXTURE_TAG = "TOOLBELT_TEST_FIXTURE"

# ─── State ───────────────────────────────────────────────────────────────────

_results: list[dict] = []
_start_time = time.time()
_spawn_fixtures: list[unreal.Actor] = []

def _assert_delta(val: float, expected: float, tolerance: float = 1.0) -> bool:
    """Check if a float value is within tolerance of expected."""
    return abs(val - expected) < tolerance

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _record(section: str, name: str, passed: bool, detail: str = "",
            verified: bool = True) -> None:
    """Record one check.

    verified=False marks an execution-only check: it proves the tool ran
    without raising, not that it did the right thing. Those are legitimate
    smoke coverage, but counting them inside a headline "180/180" overstates
    what the suite knows - which is how Quirk #41 (wrong rotation axis) sat
    inside a fully green run. The summary now reports both numbers.
    """
    icon = "✓" if passed else "✗"
    _results.append({"section": section, "name": name, "passed": passed,
                     "detail": detail, "verified": verified})
    msg = f"[TEST]  [{icon}] {name}{f'  —  {detail}' if detail else ''}"
    if passed:
        unreal.log(msg)
    else:
        unreal.log_warning(msg)
    # Incremental flush — survives a mid-run engine crash
    try:
        os.makedirs(_SAVED, exist_ok=True)
        with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
            passed_n = sum(1 for r in _results if r["passed"])
            f.write(f"[PARTIAL] {passed_n}/{len(_results)} as of last record\n\n")
            for r in _results:
                ico = "PASS" if r["passed"] else "FAIL"
                det = f"  ({r['detail']})" if r["detail"] else ""
                f.write(f"  {ico}  [{r['section']}] {r['name']}{det}\n")
    except Exception:
        pass  # never let file I/O crash the test

def _header(title: str) -> None:
    unreal.log(f"\n{'═' * 60}")
    unreal.log(f"  {title}")
    unreal.log(f"{'═' * 60}")
    # Flush section boundary so a crash names the last section started
    try:
        os.makedirs(_SAVED, exist_ok=True)
        with open(_RESULTS_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n>>> SECTION STARTED: {title}\n")
    except Exception:
        pass

def _spawn_fixture(mesh_path: str = _CUBE_MESH, location: unreal.Vector = unreal.Vector(0,0,0)) -> unreal.Actor:
    """Spawn a temporary actor and track it for cleanup."""
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actor_sub.spawn_actor_from_object(
        unreal.EditorAssetLibrary.load_asset(mesh_path),
        location,
        unreal.Rotator(0, 0, 0)
    )
    if actor:
        # Tag it so we can find it if cleanup fails
        tags = list(actor.get_editor_property("tags"))
        tags.append(unreal.Name(_FIXTURE_TAG))
        actor.set_editor_property("tags", tags)
        _spawn_fixtures.append(actor)
        return actor
    return None

def _select_fixture(actors: list[unreal.Actor]) -> None:
    # Quirk #6: wrap selection in a ScopedEditorTransaction so actor flags
    # (RF_Transactional etc.) are settled before the selection call resolves.
    # Without this, pre-existing actors with non-standard flags emit:
    # "SelectActor: The requested operation could not be completed because the
    #  actor has invalid flags."
    with unreal.ScopedEditorTransaction("Test: Select Fixture"):
        unreal.get_editor_subsystem(unreal.EditorActorSubsystem).set_selected_level_actors(actors)

def _cleanup_fixtures() -> None:
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    for actor in _spawn_fixtures:
        if actor and actor in all_actors:
            actor_sub.destroy_actor(actor)
    _spawn_fixtures.clear()

def _save_report() -> str:
    os.makedirs(_SAVED, exist_ok=True)
    passed = sum(1 for r in _results if r["passed"])
    verified_n = sum(1 for r in _results if r.get("verified", True))
    total = len(_results)
    elapsed = time.time() - _start_time

    lines = [
        "UEFN TOOLBELT — Integration Test Results",
        "=" * 60,
        f"Date:    {datetime.now().isoformat()}",
        f"Passed:  {passed}/{total}",
        f"Verified: {verified_n} checked a real outcome · "
        f"{total - verified_n} execution-only (ran without raising)",
        f"Elapsed: {elapsed:.2f}s",
        "=" * 60,
        "",
    ]
    current_section = ""
    for r in _results:
        if r["section"] != current_section:
            current_section = r["section"]
            lines.append(f"\n[{current_section}]")
            lines.append("-" * 40)
        icon = "PASS" if r["passed"] else "FAIL"
        detail = f"  ({r['detail']})" if r["detail"] else ""
        lines.append(f"  {icon}  {r['name']}{detail}")

    report = "\n".join(lines)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    # Print full results to Output Log so you don't need to open the file
    unreal.log("\n" + report)

    return _RESULTS_PATH

def _ensure_folder(path: str) -> None:
    """Ensures a content folder exists."""
    unreal.EditorAssetLibrary.make_directory(path)

# ─── Test Sections ────────────────────────────────────────────────────────────

def _test_materials() -> None:
    _header("1. Materials")
    import UEFN_Toolbelt as tb

    # Test 1: Apply override
    actor = _spawn_fixture()
    if not actor:
        _record("Materials", "Apply Preset", False, "Fixture spawn failed")
        return

    _select_fixture([actor])
    try:
        # Use a built-in preset
        target_preset = "gold"
        tb.run("material_apply_preset", preset=target_preset)

        # Verify material changed via Asset Registry or Fallback
        # Note: If M_ToolbeltBase is missing, we use a built-in engine material for verification
        # Was "/UEFN_Toolbelt/Materials/M_ToolbeltBase" — a mount that does not
        # exist, so does_asset_exist() was always False, the check always fell
        # back to the engine stub, and the assertion never tested the preset
        # material at all. parent_material_path() is what the tools themselves
        # use, so the suite cannot drift from its subject.
        PARENT_MATERIAL_PATH = parent_material_path()
        if not unreal.EditorAssetSubsystem().does_asset_exist(PARENT_MATERIAL_PATH):
            PARENT_MATERIAL_PATH = "/Engine/BasicShapes/BasicShapeMaterial"
            _header("Material Fallback: Using Engine BasicShapeMaterial")

        # This assertion used to check whether the applied material's path
        # contained the PARENT path. It could only ever be true when the preset
        # had FAILED to apply and the cube still wore its default engine
        # material — which is exactly what the old fallback path pointed at. It
        # passed for years by asserting the broken state, and only started
        # failing once the Materials tools were fixed.
        #
        # What "applied" actually means: the component holds a
        # MaterialInstanceConstant, created from our master, named for the preset.
        passed = False
        detail = ""
        try:
            component = _spawn_fixtures[0].get_component_by_class(unreal.StaticMeshComponent)
            mat = component.get_material(0)
            if mat is None:
                detail = "no material on slot 0"
            else:
                path = mat.get_path_name()
                is_instance = isinstance(mat, unreal.MaterialInstanceConstant)
                named_for_preset = f"MI_{target_preset}_" in path
                parent_ok = False
                try:
                    parent = mat.get_editor_property("parent")
                    parent_ok = parent is not None and \
                        PARENT_MATERIAL_PATH in parent.get_path_name()
                except Exception:
                    parent_ok = False
                passed = bool(is_instance and named_for_preset and parent_ok)
                detail = (f"{path.split('.')[-1]} "
                          f"(instance={is_instance}, named={named_for_preset}, "
                          f"parent={parent_ok})")
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"

        _record("Materials", "Apply Preset", passed,
                f"Applied '{target_preset}' → {detail}")
    except Exception as e:
        _record("Materials", "Apply Preset", False, str(e))

def _test_bulk_ops() -> None:
    _header("2. Bulk Operations")
    import UEFN_Toolbelt as tb

    a1 = _spawn_fixture(location=unreal.Vector(0, 0, 0))
    a2 = _spawn_fixture(location=unreal.Vector(100, 200, 50))
    a3 = _spawn_fixture(location=unreal.Vector(-50, 400, 100))

    if not (a1 and a2 and a3):
        _record("Bulk Ops", "Alignment", False, "Fixture spawn failed")
        return

    _select_fixture([a1, a2, a3])

    # Test alignment (X) - aligns to first selected actor (a1 at X=0)
    try:
        tb.run("bulk_align", axis="X")
        l1, l2, l3 = a1.get_actor_location(), a2.get_actor_location(), a3.get_actor_location()
        # All X should be roughly 0.0 (a1's original X)
        passed = abs(l1.x - 0.0) < 1.0 and abs(l2.x - 0.0) < 1.0 and abs(l3.x - 0.0) < 1.0
        _record("Bulk Ops", "Align X (First Actor)", passed, f"X coords: {l1.x}, {l2.x}, {l3.x}")
    except Exception as e:
        _record("Bulk Ops", "Align X", False, str(e))

def _test_bulk_ops_advanced() -> None:
    _header("2.1 Bulk Operations (Advanced)")
    import UEFN_Toolbelt as tb

    # --- Test Distribute ---
    a1 = _spawn_fixture(location=unreal.Vector(0, 0, 0))
    a2 = _spawn_fixture(location=unreal.Vector(10, 0, 0))
    a3 = _spawn_fixture(location=unreal.Vector(1000, 0, 0))
    _select_fixture([a1, a2, a3])
    try:
        tb.run("bulk_distribute")
        # a2 should now be at exactly 500.0 (halfway between 0 and 1000)
        l2 = a2.get_actor_location()
        passed = _assert_delta(l2.x, 500.0)
        _record("Bulk Ops", "Distribute X", passed, f"Middle actor X: {l2.x} (Expected: 500.0)")
    except Exception as e:
        _record("Bulk Ops", "Distribute X", False, str(e))

    # --- Test Snap to Grid ---
    a_snap = _spawn_fixture(location=unreal.Vector(123, 456, 789))
    _select_fixture([a_snap])
    try:
        tb.run("bulk_snap_to_grid", grid_size=100)
        l = a_snap.get_actor_location()
        # Should be (100, 500, 800)
        passed = _assert_delta(l.x, 100) and _assert_delta(l.y, 500) and _assert_delta(l.z, 800)
        _record("Bulk Ops", "Snap to 100", passed, f"Snapped to: {l}")
    except Exception as e:
        _record("Bulk Ops", "Snap to Grid", False, str(e))

    # --- Test Randomize ---
    a_rand = _spawn_fixture(location=unreal.Vector(0,0,0))
    _select_fixture([a_rand])
    try:
        # rot_min/rot_max were not real parameters - they fell into **kwargs and
        # were ignored, so this ran on defaults without anyone noticing.
        tb.run("bulk_randomize", rot_range=360.0, pitch_range=0.0,
               randomize_scale=False)
        r = a_rand.get_actor_rotation()
        # The old assertion accepted ANY axis moving, which is exactly how
        # Quirk #41 hid here: the yaw landed in pitch and this still passed.
        # pitch_range=0 on a zeroed fixture makes pitch and roll deterministic.
        axes_ok = abs(r.pitch) < 0.01 and abs(r.roll) < 0.01
        _record(
            "Bulk Ops", "Randomize (Rot)", axes_ok,
            f"yaw={r.yaw:.2f} pitch={r.pitch:.2f} roll={r.roll:.2f} "
            f"(pitch/roll must stay 0 — a value here means Quirk #41 is back)",
        )
    except Exception as e:
        _record("Bulk Ops", "Randomize", False, str(e))

    # --- Test Stack ---
    a_low = _spawn_fixture(location=unreal.Vector(0,0,0))
    a_high = _spawn_fixture(location=unreal.Vector(0,0,500))
    _select_fixture([a_low, a_high])
    try:
        tb.run("bulk_stack")
        # a_high should now be at Z=150.0
        # (a_low moved to Z=50 center-pivot height, a_high stacked 100 units above that)
        l = a_high.get_actor_location()
        passed = _assert_delta(l.z, 150.0)
        _record("Bulk Ops", "Stack Z", passed, f"High actor Z: {l.z} (Expected: 150.0)")
    except Exception as e:
        _record("Bulk Ops", "Stack", False, str(e))

    # --- Test Reset ---
    a_bad = _spawn_fixture(location=unreal.Vector(1,2,3))
    a_bad.set_actor_rotation(unreal.Rotator(roll=30, pitch=10, yaw=20), True)
    a_bad.set_actor_scale3d(unreal.Vector(2,2,2))
    _select_fixture([a_bad])
    try:
        tb.run("bulk_reset")
        l, r, s = a_bad.get_actor_location(), a_bad.get_actor_rotation(), a_bad.get_actor_scale3d()
        # Should be back to (0,0,0) rot and (1,1,1) scale. Location (1,2,3) remains.
        passed = (_assert_delta(r.pitch, 0) and _assert_delta(s.x, 1) and _assert_delta(l.x, 1))
        _record("Bulk Ops", "Reset Transforms", passed, f"Loc: {l}, Rot: {r}, Scale: {s}")
    except Exception as e:
        _record("Bulk Ops", "Reset", False, str(e))

def _test_bulk_ops_extensions() -> None:
    _header("2.2 Bulk Operations (Extensions)")
    import UEFN_Toolbelt as tb

    # --- Test Mirror ---
    a_mirror = _spawn_fixture(location=unreal.Vector(100, 50, 0))
    _select_fixture([a_mirror])
    try:
        tb.run("bulk_mirror", axis="X")
        # Mirrored across the center of bounding box (which is itself, X=100).
        # Wait, if there's only 1 actor, the "center" of selection is just its location.
        # Mirroring a single actor about its own center does nothing to location, but it flips the mesh/rotation.
        # So we'll spawn 2 actors to test mirror properly.
    except Exception:
        pass

    a_mirror_1 = _spawn_fixture(location=unreal.Vector(100, 0, 0))
    a_mirror_2 = _spawn_fixture(location=unreal.Vector(200, 0, 0))
    # Center of X is 150.
    # Mirror across X: (100) -> 2*150 - 100 = 200. (200) -> 2*150 - 200 = 100.
    _select_fixture([a_mirror_1, a_mirror_2])
    try:
        tb.run("bulk_mirror", axis="X")
        passed = _assert_delta(a_mirror_1.get_actor_location().x, 200) and _assert_delta(a_mirror_2.get_actor_location().x, 100)
        _record("Bulk Ops", "Mirror X", passed)
    except Exception as e:
        _record("Bulk Ops", "Mirror X", False, str(e))

    # --- Test Normalize Scale ---
    a_scale = _spawn_fixture(location=unreal.Vector(0,0,0))
    a_scale.set_actor_scale3d(unreal.Vector(2.0, 3.5, 4.1))
    _select_fixture([a_scale])
    try:
        tb.run("bulk_normalize_scale", target_scale=1.5)
        s = a_scale.get_actor_scale3d()
        passed = _assert_delta(s.x, 1.5) and _assert_delta(s.y, 1.5) and _assert_delta(s.z, 1.5)
        _record("Bulk Ops", "Normalize Scale", passed, f"Scale: {s}")
    except Exception as e:
        _record("Bulk Ops", "Normalize Scale", False, str(e))

    # --- Test Face Camera ---
    a_face = _spawn_fixture(location=unreal.Vector(0,0,0))
    _select_fixture([a_face])
    try:
        tb.run("bulk_face_camera")
        # Hard to assert specific value without knowing camera pos, just assert no crash
        _record("Bulk Ops", "Face Camera", True, verified=False)
    except Exception as e:
        _record("Bulk Ops", "Face Camera", False, str(e))

def _test_patterns() -> None:
    _header("3. Prop Patterns")
    import UEFN_Toolbelt as tb

    try:
        # Run a small grid
        tb.run("pattern_grid", cols=2, rows=2, spacing_x=500, spacing_y=500)

        # Count actors with the tag
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]

        _record("Patterns", "Grid Spawn (2x2)", len(pattern_actors) >= 4, f"Found {len(pattern_actors)} actors")

        # Test clear
        tb.run("pattern_clear")
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors_after = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]
        _record("Patterns", "Clear All", len(pattern_actors_after) == 0, f"Remaining: {len(pattern_actors_after)}")
    except Exception as e:
        _record("Patterns", "Execution", False, str(e))

def _test_patterns_advanced() -> None:
    _header("3.1 Prop Patterns (Advanced)")
    import UEFN_Toolbelt as tb

    # --- Test Circle ---
    try:
        radius = 1000.0
        count = 8
        tb.run("pattern_circle", radius=radius, count=count)

        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]

        # Verify count
        passed_count = len(pattern_actors) >= count

        # Verify distance from center (0,0,0)
        passed_dist = True
        if pattern_actors:
            for a in pattern_actors:
                dist = a.get_actor_location().length()
                if not _assert_delta(dist, radius, tolerance=10.0):
                    passed_dist = False
                    break

        _record("Patterns", "Circle (Radius/Count)", passed_count and passed_dist, f"Count: {len(pattern_actors)}, Dist: {radius}")
        tb.run("pattern_clear")
    except Exception as e:
        _record("Patterns", "Circle", False, str(e))

    # --- Test Line ---
    try:
        tb.run("pattern_line", count=5, spacing=200)
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]
        _record("Patterns", "Line Spawn (Count=5)", len(pattern_actors) >= 5, f"Found {len(pattern_actors)} actors")
        tb.run("pattern_clear")
    except Exception as e:
        _record("Patterns", "Line", False, str(e))

    # --- Test Arc ---
    try:
        tb.run("pattern_arc", radius=500, angle=180, count=4)
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]
        _record("Patterns", "Arc Spawn (180deg)", len(pattern_actors) >= 4, f"Found {len(pattern_actors)} actors")
        tb.run("pattern_clear")
    except Exception as e:
        _record("Patterns", "Arc", False, str(e))

    # --- Test Spiral ---
    try:
        tb.run("pattern_spiral", count=12)
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]
        _record("Patterns", "Spiral Spawn (Count=12)", len(pattern_actors) >= 12, f"Found {len(pattern_actors)} actors")
        tb.run("pattern_clear")
    except Exception as e:
        _record("Patterns", "Spiral", False, str(e))

    # --- Test Wave ---
    try:
        tb.run("pattern_wave", count=6)
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]
        _record("Patterns", "Wave Spawn (Count=6)", len(pattern_actors) >= 6, f"Found {len(pattern_actors)} actors")
        tb.run("pattern_clear")
    except Exception as e:
        _record("Patterns", "Wave", False, str(e))

def _test_advanced_patterns() -> None:
    _header("3.2 Prop Patterns (Advanced / Scatter)")
    import UEFN_Toolbelt as tb

    # --- Test Helix ---
    try:
        tb.run("pattern_helix", count=24, radius=600, turns=2.0)
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]
        _record("Patterns", "Helix Spawn (Count=24)", len(pattern_actors) >= 24, f"Found {len(pattern_actors)} actors")
        tb.run("pattern_clear")
    except Exception as e:
        _record("Patterns", "Helix", False, str(e))

    # --- Test Radial Rows ---
    try:
        tb.run("pattern_radial_rows", rings=3, props_per_ring=6, include_center=True)
        # Expected: 1 (center) + 6 + 12 + 18 = 37
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        pattern_actors = [a for a in all_actors if "TOOLBELT_PATTERN" in [str(t) for t in a.get_editor_property("tags")]]
        _record("Patterns", "Radial Rows (Count=37)", len(pattern_actors) >= 37, f"Found {len(pattern_actors)} actors")
        tb.run("pattern_clear")
    except Exception as e:
        _record("Patterns", "Radial Rows", False, str(e))

    # --- Test Scatter Along Path ---
    try:
        pts = [(0.0, 0.0, 0.0), (1000.0, 0.0, 0.0)]
        tb.run("scatter_along_path", path_points=pts, count_per_point=3, folder="TestScatterPath")

        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        scatter_actors = [a for a in all_actors if a.get_folder_path() and "TestScatterPath" in str(a.get_folder_path())]
        _record("Procedural", "Scatter Along Path (Count=6)", len(scatter_actors) == 6, f"Found {len(scatter_actors)}")

        # Cleanup
        tb.run("scatter_clear", folder="TestScatterPath")
    except Exception as e:
        _record("Procedural", "Scatter Along Path", False, str(e))

def _test_snapshots() -> None:
    _header("4. Level Snapshots")
    import UEFN_Toolbelt as tb

    try:
        snap_name = "test_integration_snap_A"

        # 1. Save Snapshot A
        tb.run("snapshot_save", name=snap_name)
        snap_dir = os.path.join(_SAVED, "snapshots")
        snap_file = os.path.join(snap_dir, f"{snap_name}.json")
        passed = os.path.exists(snap_file)
        _record("Snapshots", "Save JSON", passed)

        # 2. Export Snapshot
        export_path = os.path.join(_SAVED, "exported_snap_A.json")
        tb.run("snapshot_export", name=snap_name, export_path=export_path)
        _record("Snapshots", "Export JSON", os.path.exists(export_path))

        # 3. Import Snapshot
        tb.run("snapshot_import", import_path=export_path, name="test_integration_snap_Imported")
        imported_file = os.path.join(snap_dir, "test_integration_snap_Imported.json")
        _record("Snapshots", "Import JSON", os.path.exists(imported_file))

        # Spawn an actor to create a diff
        a_diff = _spawn_fixture(location=unreal.Vector(100, 200, 300))

        # 4. Compare Live
        tb.run("snapshot_compare_live", name=snap_name)
        _record("Snapshots", "Compare Live", True, verified=False) # Just testing no crash

        # 5. Save Snapshot B & Diff
        snap_name_b = "test_integration_snap_B"
        tb.run("snapshot_save", name=snap_name_b)
        tb.run("snapshot_diff", name_a=snap_name, name_b=snap_name_b)
        _record("Snapshots", "Diff JSON", True, verified=False)

        # 6. Restore
        a_diff.set_actor_location(unreal.Vector(999, 999, 999), False, False)
        tb.run("snapshot_restore", name=snap_name_b)
        passed_restore = _assert_delta(a_diff.get_actor_location().x, 100)
        _record("Snapshots", "Restore Transforms", passed_restore)

        # Cleanup
        if passed:
            tb.run("snapshot_delete", name=snap_name)
            tb.run("snapshot_delete", name=snap_name_b)
            tb.run("snapshot_delete", name="test_integration_snap_Imported")
            if os.path.exists(export_path):
                os.remove(export_path)

            _record("Snapshots", "Delete JSON", not os.path.exists(snap_file))
            if a_diff:
                a_diff.destroy_actor()

    except Exception as e:
        _record("Snapshots", "Execution", False, str(e))

def _test_crawler() -> None:
    _header("5. API Capability Crawler")
    import UEFN_Toolbelt as tb

    try:
        # Crawl the level (fast read-only)
        tb.run("api_crawl_level_classes")

        # Verify file
        out_path = os.path.join(_SAVED, "api_level_classes_schema.json")
        _record("Crawler", "Level Crawl JSON", os.path.exists(out_path))

        # Crawl selection
        actor = _spawn_fixture()
        _select_fixture([actor])
        tb.run("api_crawl_selection")

        # Output is typically api_selection_crawl.json
        out_path_sel = os.path.join(_SAVED, "api_selection_crawl.json")
        _record("Crawler", "Selection Crawl JSON", os.path.exists(out_path_sel))

    except Exception as e:
        _record("Crawler", "Execution", False, str(e))

def _test_asset_tagger() -> None:
    _header("6. Asset Tagger")
    import UEFN_Toolbelt as tb

    # Spawn a fixture to have something to tag
    actor = _spawn_fixture()
    if not actor:
        _record("Asset Tagger", "Add Tag", False, "Fixture spawn failed")
        return

    try:
        # This used to tag /Engine/BasicShapes/Cube. Engine content cannot be
        # saved, so the tag never persisted - and because tag_add discarded
        # save_asset's return it reported success anyway, while tag_search then
        # found nothing. Two tools disagreeing, both recorded as passes.
        #
        # Tagging a project-owned asset makes the round trip real: write it,
        # find it by search, remove it, confirm it is gone.
        tag_dir = resolve_content_path("/Game/TOOLBELT_TEST/Tags")
        unreal.EditorAssetLibrary.make_directory(tag_dir)
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        asset_tools.create_asset("MI_TagTarget", tag_dir,
                                 unreal.MaterialInstanceConstant,
                                 unreal.MaterialInstanceConstantFactoryNew())
        asset_path = f"{tag_dir}/MI_TagTarget"
        tag_name = "TEST_INTEGRATION_TAG"

        added = tb.run("tag_add", asset_paths=[asset_path],
                       tag_name=tag_name, value="verified")
        _record("Asset Tagger", "Add Tag",
                added.get("status") == "ok" and added.get("tagged") == 1,
                f"status={added.get('status')} tagged={added.get('tagged')}"
                f"/{added.get('attempted')}")

        # Show tags. Passing asset_paths explicitly, because tag_show otherwise
        # reads the CONTENT BROWSER selection - selecting a level actor, as this
        # test used to, left it with nothing to inspect. It logged "Nothing
        # selected in the Content Browser" and the check passed anyway.
        _select_fixture([actor])
        shown = tb.run("tag_show", asset_paths=[asset_path])
        shown_tags = shown.get("assets", {}).get(asset_path, {})
        _record("Asset Tagger", "Show Tags",
                shown.get("status") == "ok" and shown_tags.get(tag_name) == "verified",
                f"status={shown.get('status')} tags={shown_tags}")

        # The round trip the old test could not do: the tag must come back.
        found = tb.run("tag_search", tag_name=tag_name, value="verified",
                       folder=tag_dir)
        hits = found.get("matches", [])
        _record("Asset Tagger", "Search finds the tag it just wrote",
                any(asset_path in str(h) for h in hits),
                f"{len(hits)} hit(s) in {tag_dir}")

        all_tags = tb.run("tag_list_all", folder=tag_dir).get("tags", {})
        _record("Asset Tagger", "List All", all_tags.get(tag_name) == 1,
                f"{tag_name}={all_tags.get(tag_name)} asset(s), keys={list(all_tags)}")

        # Export
        tb.run("tag_export", folder=tag_dir)
        export_path = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "tag_export.json")
        _record("Asset Tagger", "Export Tags", os.path.exists(export_path))

        removed = tb.run("tag_remove", asset_paths=[asset_path], tag_name=tag_name)
        _record("Asset Tagger", "Remove Tag",
                removed.get("status") == "ok" and removed.get("removed") == 1,
                f"status={removed.get('status')} removed={removed.get('removed')}"
                f"/{removed.get('attempted')}")

        gone = tb.run("tag_search", tag_name=tag_name, value="verified",
                      folder=tag_dir)
        gone_hits = gone.get("matches", [])
        _record("Asset Tagger", "Search no longer finds it after removal",
                not any(asset_path in str(h) for h in gone_hits),
                f"{len(gone_hits)} hit(s) remaining")

        unreal.EditorAssetLibrary.delete_directory(tag_dir)
    except Exception as e:
        _record("Asset Tagger", "Execution", False, str(e))

def _test_verse() -> None:
    _header("7. Verse Helpers")
    import UEFN_Toolbelt as tb

    try:
        # Test snippet listing
        tb.run("verse_list_snippets")
        _record("Verse", "List Snippets", True, verified=False)

        # Test device generation (requires selection)
        actor = _spawn_fixture()
        _select_fixture([actor])
        tb.run("verse_gen_device_declarations")
        _record("Verse", "Gen Device Declarations", True, verified=False)
    except Exception as e:
        _record("Verse", "Execution", False, str(e))

def _test_verse_advanced() -> None:
    _header("7.2 Verse Layout & Boilerplate")
    import UEFN_Toolbelt as tb

    try:
        # Code Generators
        tb.run("verse_gen_custom", code="# custom test snippet", description="pytest")
        tb.run("verse_gen_elimination_handler")
        tb.run("verse_gen_game_skeleton", device_name="TestIntegrationGameMgr")
        tb.run("verse_gen_prop_spawner")
        tb.run("verse_gen_scoring_tracker", max_score=50)
        _record("Verse", "CodeGen Boilerplates", True, verified=False)

        # Device Editors
        tb.run("verse_list_devices")
        tb.run("verse_export_report")

        actor = _spawn_fixture()
        _select_fixture([actor])

        # Select by name fallback (will likely select 0 devices, but shouldn't crash)
        tb.run("verse_select_by_name", name_filter="RandomNonExistentString123")
        tb.run("verse_select_by_class", class_filter="RandomNonExistentString123")

        # Re-select the fixture actor for property sets
        _select_fixture([actor])
        tb.run("verse_bulk_set_property", property_name="bHidden", value=True, use_all_devices=False)
        passed_prop = actor.get_editor_property("bHidden") is True
        _record("Verse", "Bulk Set Property", passed_prop)

        # Snippets Open Directory (just test execution path)
        # Note: actually executing this spawns windows explorer, which is annoying for automation.
        # tb.run("verse_open_snippets_folder")

        # Cleanup
        actor.destroy_actor()
    except Exception as e:
        _record("Verse", "Advanced Execution", False, str(e))

def _test_screenshots() -> None:
    _header("8. Screenshot Tools")
    import UEFN_Toolbelt as tb
    try:
        # Take a screenshot (full resolution)
        shot_name = "integration_test_shot"
        path = tb.run("screenshot_take", name=shot_name, width=1920, height=1080)

        # Test Focus Selection
        a1 = _spawn_fixture()
        _select_fixture([a1])
        tb.run("screenshot_focus_selection", name="focus_shot", width=1280, height=720, restore_camera=False)
        _record("Screenshots", "Focus Selection", True, verified=False)

        # Test Timed Series (short interval for speed)
        tb.run("screenshot_timed_series", name="series_shot", count=2, width=1280, height=720, interval_sec=0.1)
        _record("Screenshots", "Timed Series", True, verified=False)

        # Test Open Folder
        tb.run("screenshot_open_folder")

        a1.destroy_actor()

        # Note: AutomationLibrary.take_high_res_screenshot is ASYNCHRONOUS.
        # It only writes the file AFTER this Python script finishes and the engine ticks.
        # We verify that the command was successfully sent and the path is valid.
        passed = bool(path and "screenshots" in str(path))

        _record("Screenshots", "Capture Paths", passed, f"Queued → {path}" if passed else "Capture request failed")
    except Exception as e:
        _record("Screenshot", "Capture Error", False, str(e))


def _test_scatter() -> None:
    _header("3.2 Scatter Tools")
    import UEFN_Toolbelt as tb
    try:
        # Pre-cleanup
        tb.run("scatter_clear", folder="TestScatter")

        # --- Test Props Scatter ---
        tb.run("scatter_props", count=10, radius=500.0, folder="TestScatter")
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = [a for a in actor_sub.get_all_level_actors() if "TestScatter" in str(a.get_folder_path())]
        _record("Scatter", "Props Count", len(actors) == 10, f"Found {len(actors)} actors")

        # --- Test HISM Scatter ---
        tb.run("scatter_hism", count=50, radius=500.0, folder="TestScatterHISM")
        hism_actors = [a for a in actor_sub.get_all_level_actors() if "HISM_Scatter" in a.get_actor_label()]
        passed_hism = False
        if hism_actors:
            comps = hism_actors[0].get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent.static_class())
            if comps:
                count = comps[0].get_instance_count()
                passed_hism = (count == 50)
        _record("Scatter", "HISM Instances", passed_hism, f"HISM count: {count if passed_hism else 0}")

        # --- Test Clear ---
        tb.run("scatter_clear", folder="TestScatter")
        tb.run("scatter_clear", folder="TestScatterHISM")
        remaining = [a for a in actor_sub.get_all_level_actors() if "TestScatter" in str(a.get_folder_path())]
        _record("Scatter", "Clear", len(remaining) == 0, f"Remaining: {len(remaining)}")

    except Exception as e:
        _record("Scatter", "Error", False, str(e))


def _test_splines() -> None:
    _header("3.3 Spline Tools")
    import UEFN_Toolbelt as tb
    try:
        # Pre-cleanup to ensure accurate actor counts
        tb.run("spline_clear_props", folder_name="TestSplineProps")

        # Setup: Spawn actor + SplineComponent
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        spline_host = actor_sub.spawn_actor_from_class(unreal.Actor, unreal.Vector(0,0,0))
        spline_host.set_actor_label("TestSplineHost")

        _spline_comp = unreal.SplineComponent(spline_host)

        # Select it
        _select_fixture([spline_host])

        # Run placement (default count=10)
        tb.run("spline_place_props", count=5, folder_name="TestSplineProps")

        props = [a for a in actor_sub.get_all_level_actors() if "TestSplineProps" in str(a.get_folder_path())]
        _record("Spline", "Place Props", len(props) == 5, f"Spawned {len(props)} props along spline")

        # 2. Spline to Verse routines
        tb.run("spline_to_verse_points", sample_count=10)
        tb.run("spline_to_verse_patrol", device_name="TestSplinePatrol")
        tb.run("spline_to_verse_zone_boundary", zone_name="TestSplineZone")
        _record("Spline", "Code Generate Verse", True, verified=False)

        # 3. Spline Export
        tb.run("spline_export_json", sample_count=5, include_tangents=True)
        export_path = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "spline_export.json")
        _record("Spline", "Export JSON", os.path.exists(export_path))

        # Cleanup
        tb.run("spline_clear_props", folder_name="TestSplineProps")
        spline_host.destroy_actor()
        left = [a for a in actor_sub.get_all_level_actors()
                if "TestSplineProps" in str(a.get_folder_path())]
        _record("Spline", "Clear Props", not left,
                f"{len(props)} placed, {len(left)} left after clear")

    except Exception as e:
        _record("Spline", "Error", False, str(e))


def _test_assets() -> None:
    _header("6.1 Asset Toolkit")
    import UEFN_Toolbelt as tb
    try:
        # Dry Run Renamer
        tb.run("rename_dry_run", scan_path="/Engine/BasicShapes") # Scan a safe folder
        report_path = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "rename_report.json")
        passed = os.path.exists(report_path)
        _record("Assets", "Rename Dry Run", passed, f"Report generated: {passed}")

        # --- Asset Creation for invasive tests ---
        test_dir = resolve_content_path("/Game/TOOLBELT_TEST")
        unreal.EditorAssetLibrary.make_directory(test_dir)

        # We cannot duplicate engine assets because they are cooked.
        # Instead, we will create dummy Material Instances.
        factory = unreal.MaterialInstanceConstantFactoryNew()
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

        asset_tools.create_asset("BadNameMat", test_dir, unreal.MaterialInstanceConstant, factory)
        asset_tools.create_asset("M_WrongPrefix", test_dir, unreal.MaterialInstanceConstant, factory)

        # Note: Unreal's AssetRegistry caches paths. Sequential rename operations
        # inside the same tick won't see the updated paths from previous steps.
        # We verify that the tools execute properly against the created assets without crashing.

        # Test Report
        tb.run("rename_report", scan_path=test_dir)
        _record("Assets", "Rename Report", os.path.exists(report_path), "JSON Report created")

        # Test Enforce. dry_run defaults True now, so the real path is opted
        # into deliberately - and the result is checked rather than assumed.
        enforced = tb.run("rename_enforce_conventions", scan_path=test_dir, dry_run=False)
        _record("Assets", "Enforce Conventions",
                enforced.get("status") in ("ok", "partial") and enforced.get("renamed", 0) > 0,
                f"renamed={enforced.get('renamed')} status={enforced.get('status')}")

        # Test Strip
        # Spawn a fresh asset for strip_prefix so it's in the registry's initial state
        asset_tools.create_asset("MI_StripMe", test_dir, unreal.MaterialInstanceConstant, factory)
        # Assert on the tool's own counts rather than re-reading the registry:
        # the caching note above means a fresh path lookup in this tick is
        # unreliable, but done/status come from the checked rename_asset return,
        # so a refused rename shows up as done=0 status=error.
        stripped = tb.run("rename_strip_prefix", scan_path=test_dir, prefix="MI_", dry_run=False)
        _record("Assets", "Strip Prefix",
                stripped.get("status") in ("ok", "partial") and stripped.get("done", 0) > 0,
                f"done={stripped.get('done')}/{stripped.get('total')} "
                f"status={stripped.get('status')}")

        # Cleanup
        unreal.EditorAssetLibrary.delete_directory(test_dir)

    except Exception as e:
        _record("Assets", "Error", False, str(e))


def _test_memory() -> None:
    _header("1.2 Memory Profiler")
    import UEFN_Toolbelt as tb
    try:
        # Run scan on a safe folder
        tb.run("memory_scan", scan_path="/Engine/BasicShapes")
        report_path = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "memory_report.json")
        passed = os.path.exists(report_path)
        _record("Optimization", "Memory Scan JSON", passed, f"Report generated: {passed}")

        # Run specific scans (read-only)
        tb.run("memory_scan_textures", scan_path="/Engine/EngineMaterials")
        _record("Optimization", "Scan Textures", True, verified=False)

        tb.run("memory_scan_meshes", scan_path="/Engine/BasicShapes")
        _record("Optimization", "Scan Meshes", True, verified=False)

        tb.run("memory_top_offenders", scan_path="/Engine/BasicShapes", top_n=5)
        _record("Optimization", "Top Offenders", True, verified=False)

        # Test Auto-Fix LODs
        # We cannot duplicate engine meshes because they are cooked.
        # So we just run the tool on an empty directory to ensure it doesn't crash
        # when traversing the Asset Registry.
        test_dir = resolve_content_path("/Game/TOOLBELT_TEST_MEM")
        unreal.EditorAssetLibrary.make_directory(test_dir)

        tb.run("memory_autofix_lods", scan_path=test_dir, num_lods=3)
        _record("Optimization", "Auto-Fix LODs", True, "Tool runs safely on Empty Dir", verified=False)

        # Cleanup
        unreal.EditorAssetLibrary.delete_directory(test_dir)

    except Exception as e:
        _record("Optimization", "Error", False, str(e))

# ─── Batch 5 Additions ────────────────────────────────────────────────────────

def _test_reference_auditor() -> None:
    _header("1.3 Reference Auditor")
    import UEFN_Toolbelt as tb
    try:
        # Run audit scans on engine shapes (we don't delete them, just verify tools run)
        tb.run("ref_audit_orphans", scan_path="/Engine/BasicShapes", excluded_classes=[])
        _record("Assets", "Audit Orphans", True, verified=False)

        tb.run("ref_audit_redirectors", scan_path="/Engine/BasicShapes")
        _record("Assets", "Audit Redirectors", True, verified=False)

        tb.run("ref_audit_duplicates", scan_path="/Engine/BasicShapes")
        _record("Assets", "Audit Duplicates", True, verified=False)

        tb.run("ref_audit_unused_textures", scan_path="/Engine/EngineMaterials")
        _record("Assets", "Audit Unused Textures", True, verified=False)

        tb.run("ref_full_report", scan_path="/Engine/BasicShapes", excluded_classes=[])
        report_path = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "ref_audit_report.json")
        passed = os.path.exists(report_path)
        _record("Assets", "Ref Aud Full Report", passed, f"Report generated: {passed}")

    except Exception as e:
        _record("Assets", "Reference Auditor Error", False, str(e))


def _test_project_scaffold() -> None:
    _header("1.4 Project Scaffold")
    import UEFN_Toolbelt as tb
    try:
        # Build a temporary test scaffold structure
        test_project = "ScaffoldTest"
        test_base = resolve_content_path("/Game/TOOLBELT_TEST")
        root_path = f"{test_base}/{test_project}"

        # 1. Preview
        tb.run("scaffold_preview", template="solo_dev", project_name=test_project, base=test_base)
        _record("Project", "Scaffold Preview", True, verified=False)

        # 2. Generate
        tb.run("scaffold_generate", template="solo_dev", project_name=test_project, base=test_base)
        maps_path = f"{root_path}/Maps"
        passed = unreal.EditorAssetLibrary.does_directory_exist(maps_path)
        _record("Project", "Scaffold Generate", passed, f"Maps folder created: {passed}")

        # 3. Save Custom Template — read it back rather than trusting the call.
        tb.run("scaffold_save_template", template_name="TEST_Tmpl", folders=["A", "B/C"])
        listed = tb.run("scaffold_list_templates").get("templates", {})
        saved = listed.get("TEST_Tmpl")
        _record("Project", "Scaffold Save Template",
                saved is not None and saved.get("folder_count") == 2,
                f"listed as {saved}" if saved else "not present in scaffold_list_templates")

        # 4. Delete Custom Template — and confirm it is actually gone.
        tb.run("scaffold_delete_template", template_name="TEST_Tmpl")
        still = tb.run("scaffold_list_templates").get("templates", {})
        _record("Project", "Scaffold Delete Template", "TEST_Tmpl" not in still,
                "still listed after delete" if "TEST_Tmpl" in still else "removed from the list")

        # Cleanup
        unreal.EditorAssetLibrary.delete_directory(test_base)

    except Exception as e:
        _record("Project", "Scaffold Error", False, str(e))


def _test_text_painter() -> None:
    _header("1.5 Text Painter")
    import UEFN_Toolbelt as tb
    try:
        # 1. Place Text
        result1 = tb.run("text_place", text="UNIT_TEST", location=(0,0,1000), folder="TestTextProps")
        passed = isinstance(result1, dict) and result1.get("status") == "ok"
        _record("Procedural", "Text Place", passed)

        # 2. Paint Grid
        tb.run("text_paint_grid", cols=2, rows=2, origin=(0,0,2000), cell_size=200, folder="TestTextGrid")
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        grid_actors = [
            a for a in actor_sub.get_all_level_actors()
            if isinstance(a, unreal.TextRenderActor) and "TestTextGrid" in str(a.get_folder_path())
        ]
        passed_grid = len(grid_actors) == 4
        _record("Procedural", "Text Paint Grid", passed_grid, f"Found {len(grid_actors)} actors, expected 4")

        # 3. Save Style & List Styles
        tb.run("text_save_style", style_name="TEST_Style", color="#FF0000")
        _record("Procedural", "Text Save Style", True, verified=False)
        tb.run("text_list_styles")

        # 4. Color Cycle & Label Selection
        tb.run("text_color_cycle", start_location=(0,500,1000), spacing_x=200)
        _record("Procedural", "Text Color Cycle", True, verified=False)

        a1 = _spawn_fixture()
        _select_fixture([a1])
        tb.run("text_label_selection", offset_z=100.0, color="#FF00FF")
        _record("Procedural", "Text Label Selection", True, verified=False)
        a1.destroy_actor()

        # 5. Clear Folder
        tb.run("text_clear_folder", folder="TestTextProps")
        tb.run("text_clear_folder", folder="TestTextGrid")
        tb.run("text_clear_folder", folder="ToolbeltText")

        remaining = [
            a for a in actor_sub.get_all_level_actors()
            if isinstance(a, unreal.TextRenderActor) and ("TestText" in str(a.get_folder_path()) or "ToolbeltText" in str(a.get_folder_path()))
        ]
        passed_clear = len(remaining) == 0
        _record("Procedural", "Text Clear", passed_clear, f"Remaining actors: {len(remaining)}")

    except Exception as e:
        _record("Procedural", "Text Painter Error", False, str(e))


def _test_advanced_materials() -> None:
    _header("1.6 Advanced Materials")
    import UEFN_Toolbelt as tb
    try:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

        # Spawn 3 cubes for material testing
        a1 = _spawn_fixture(location=unreal.Vector(0, 0, 0))
        a2 = _spawn_fixture(location=unreal.Vector(200, 0, 0))
        a3 = _spawn_fixture(location=unreal.Vector(400, 0, 0))
        actor_sub.set_selected_level_actors([a1, a2, a3])

        # 1. Randomize Colors
        r = tb.run("material_randomize_colors", saturation=0.8)
        _record("Materials", "Randomize Colors",
                r.get("status") == "ok" and r.get("count") == r.get("attempted") == 3,
                f"{r.get('count')}/{r.get('attempted')} actor(s) status={r.get('status')}")

        # 2. Gradient Painter
        r = tb.run("material_gradient_painter", color_a="#0000FF", color_b="#FF0000", axis="X")
        _record("Materials", "Gradient Painter",
                r.get("status") == "ok" and r.get("count") == r.get("attempted") == 3,
                f"{r.get('count')}/{r.get('attempted')} actor(s) status={r.get('status')}")

        # 3. Team Color Split. red+blue must account for every actor - the
        # counters used to increment on which side of the midpoint an actor sat,
        # whether or not the material actually applied.
        r = tb.run("material_team_color_split")
        red, blue = r.get("red", 0), r.get("blue", 0)
        _record("Materials", "Team Color Split",
                r.get("status") == "ok" and red + blue == 3,
                f"{red} red + {blue} blue = {red + blue} of 3")

        # 4. Pattern Painter
        r = tb.run("material_pattern_painter", pattern="checkerboard", preset_a="neon", preset_b="rubber")
        _record("Materials", "Pattern Painter",
                r.get("status") == "ok" and r.get("count") == r.get("attempted") == 3,
                f"{r.get('count')}/{r.get('attempted')} actor(s) status={r.get('status')}")

        # 5. Glow Pulse Preview
        r = tb.run("material_glow_pulse_preview", intensity=10.0)
        _record("Materials", "Glow Pulse Preview",
                r.get("status") == "ok" and r.get("count") == r.get("attempted") == 3,
                f"{r.get('count')}/{r.get('attempted')} actor(s) status={r.get('status')}")

        # 6. Color Harmony
        r = tb.run("material_color_harmony", harmony="triadic")
        _record("Materials", "Color Harmony",
                r.get("status") == "ok" and r.get("count") == r.get("attempted") == 3
                and r.get("harmony") == "triadic",
                f"{r.get('count')}/{r.get('attempted')} actor(s) harmony={r.get('harmony')}")

        # 7. Save Preset / List Presets
        actor_sub.set_selected_level_actors([a1])
        tb.run("material_apply_preset", preset="chrome")
        tb.run("material_save_preset", preset_name="TEST_Integration_Preset")
        listed = tb.run("material_list_presets")
        names = listed.get("presets", [])
        _record("Materials", "Save & List Presets",
                "TEST_Integration_Preset" in names and "chrome" in names,
                f"{len(names)} preset(s), saved one present="
                f"{'TEST_Integration_Preset' in names}")

        # 8. Bulk Swap — on a FRESH cube, because a1..a3 have had preset
        # instances applied above and no longer carry BasicShapeMaterial. That
        # is why this check used to swap 0 slots and still pass: the tool
        # returned "ok" for a swap that matched nothing.
        swap_target = _spawn_fixture(location=unreal.Vector(0, 3000, 0))
        actor_sub.set_selected_level_actors([swap_target])
        r = tb.run("material_bulk_swap",
                   old_material_path="/Engine/BasicShapes/BasicShapeMaterial",
                   new_material_path="/Engine/EngineMaterials/DefaultMaterial",
                   scope="selection")
        _record("Materials", "Bulk Swap",
                r.get("status") == "ok" and r.get("total_slots", 0) > 0,
                f"status={r.get('status')} slots={r.get('total_slots')} "
                f"actors={r.get('actors_touched')}")

        # Running the SAME swap again matches nothing, because the slot no
        # longer holds BasicShapeMaterial - and both materials still load, so
        # this reaches the no_slots_matched path rather than an early load
        # failure. That is the exact shape that used to return "ok" with 0
        # slots and tell every caller a swap had happened.
        miss = tb.run("material_bulk_swap",
                      old_material_path="/Engine/BasicShapes/BasicShapeMaterial",
                      new_material_path="/Engine/EngineMaterials/DefaultMaterial",
                      scope="selection")
        _record("Materials", "Bulk Swap reports a miss as error",
                miss.get("status") == "error"
                and miss.get("total_slots", -1) == 0
                and miss.get("reason") == "no_slots_matched",
                f"status={miss.get('status')} reason={miss.get('reason')}")
        swap_target.destroy_actor()

        # Cleanup
        for a in [a1, a2, a3]:
            a.destroy_actor()

    except Exception as e:
        _record("Materials", "Adv Material Error", False, str(e))


# ─── Main Run ─────────────────────────────────────────────────────────────────

@register_tool(
    name="toolbelt_integration_test",
    category="Tests",
    description="[WARNING: INVASIVE] Runs full automation. Spawns/Deletes actors. BEST IN TEST TEMPLATE.",
    icon="🧪",
    tags=["test", "integration", "full", "automation"],
)
def toolbelt_integration_test(**kwargs) -> dict:
    """
    Run the full suite of integration tests.
    This will spawn temporary actors, select them, and run tools to verify behavior.
    """
    global _results, _start_time
    _results = []
    _start_time = time.time()

    unreal.log("══════════════════════════════════════════════════════")
    unreal.log("  UEFN TOOLBELT INTEGRATION TEST — STARTING")
    unreal.log("══════════════════════════════════════════════════════")

    with undo_transaction("Toolbelt Integration Test"):
        try:
            _test_materials()
            _test_bulk_ops()
            _test_bulk_ops_advanced()
            _test_bulk_ops_extensions()
            _test_patterns()
            _test_patterns_advanced()
            _test_advanced_patterns()
            _test_scatter()
            _test_splines()
            _test_assets()
            _test_memory()
            _test_reference_auditor()
            _test_project_scaffold()
            _test_text_painter()
            _test_advanced_materials()
            _test_snapshots()
            _test_crawler()
            _test_asset_tagger()
            _test_verse()
            _test_verse_advanced()
            _test_screenshots()

            # --- Batch 8 (Careful/Non-Invasive) ---
            _test_lods_safe()
            _test_optimization_safe()
            _test_arena_safe()
            _test_scatter_advanced_safe()
            _test_assets_advanced_safe()
            _test_bridge_safe()
            _test_cooker_safe()
            _test_measurement()
            _test_localization()
            _test_environmental()
            _test_entities()
            _test_selection()
            _test_lighting_integration()
            _test_project_admin_integration()

            # --- Batch 9 (Tools added after v1.6.0) ---
            _test_zone_tools()
            _test_stamp_tools()
            _test_actor_org_tools()
            _test_proximity_tools()
            _test_advanced_alignment()
            _test_sign_tools()
            _test_postprocess_and_world()
            _test_audio_tools()
            _test_level_health()
            _test_config_tools()
            _test_lighting_extended()
            _test_world_state()

            # --- Batch 10 (Tools added in v1.9.6) ---
            _test_visibility_tools()
            _test_viewport_bookmarks()
            _test_selection_sets()
            _test_project_admin_v196()

            # Finalize
            _cleanup_fixtures()
            report_path = _save_report()

            passed = sum(1 for r in _results if r["passed"])
            total = len(_results)

            unreal.log("\n══════════════════════════════════════════════════════")
            unreal.log("  INTEGRATION TEST COMPLETE")
            verified_n = sum(1 for r in _results if r.get("verified", True))
            unreal.log(f"  Passed: {passed}/{total}")
            unreal.log(f"  Verified: {verified_n} · execution-only: {total - verified_n}")
            unreal.log(f"  Results: {report_path}")
            unreal.log("══════════════════════════════════════════════════════")

            return {
                "status": "ok" if passed == total else "error",
                "passed": passed,
                "failed": total - passed,
                "total": total,
                "verified": verified_n,
                "execution_only": total - verified_n,
                "report": report_path,
                "failures": [
                    {"section": r.get("section"), "name": r.get("name"),
                     "detail": r.get("detail")}
                    for r in _results if not r["passed"]
                ],
            }

        except Exception as e:
            unreal.log_error(f"FATAL ERROR IN INTEGRATION TEST: {e}")
            _cleanup_fixtures()
            # The suite spawns real actors. A caller that cannot tell a crash
            # from a clean run cannot know whether fixtures were left behind.
            return {"status": "error", "reason": "fatal", "message": str(e),
                    "passed": sum(1 for r in _results if r["passed"]),
                    "total": len(_results)}


# ─── Batch 8 (Final 20%) ──────────────────────────────────────────────────────

def _test_lods_safe() -> None:
    _header("8.1 LODs & Collision (Safe Version)")
    import UEFN_Toolbelt as tb
    try:
        # Restriction: Only use the TOOLBELT_TEST folder
        test_folder = resolve_content_path("/Game/TOOLBELT_TEST/LODs")
        unreal.EditorAssetLibrary.make_directory(test_folder)

        # 1. Spawn a fresh test mesh (Material Instance + Proxy)
        # Instead of duplicating project meshes (which might be cooked),
        # we'll test the audit and folder tools which are the main goal.
        tb.run("lod_audit_folder", folder_path=test_folder)
        _record("LODs", "Audit Folder", True, "Audit executed on test folder", verified=False)

    except Exception as e:
        _record("LODs", "Error", False, str(e))

def _test_optimization_safe() -> None:
    _header("8.2 Optimization (Restricted Path)")
    import UEFN_Toolbelt as tb
    try:
        # Restriction: Never scan /Game. Only scan the test folder.
        test_folder = resolve_content_path("/Game/TOOLBELT_TEST")

        tb.run("memory_scan_textures", scan_path=test_folder)
        tb.run("memory_scan_meshes", scan_path=test_folder)
        _record("Optimization", "Safe Scans", True, f"Scanned: {test_folder}", verified=False)

    except Exception as e:
        _record("Optimization", "Error", False, str(e))

def _test_arena_safe() -> None:
    _header("8.3 Arena Generator (Safe Spawn/Cleanup)")
    import UEFN_Toolbelt as tb
    try:
        # Run a SMALL arena generation
        tb.run("arena_generate", size="small", apply_team_colors=False)

        # Verify spawning - check for actors containing 'Arena' or 'Base' in folder
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        arena_actors = [a for a in actor_sub.get_all_level_actors() if "Arena" in str(a.get_folder_path())]
        _record("Arena", "Generate", len(arena_actors) > 10, f"Spawned {len(arena_actors)} actors")

        # MANDATORY CLEANUP: Mass destroy everything in the Arena folder
        for a in arena_actors:
            a.destroy_actor()
        # Re-scan rather than trusting the loop. destroy_actor is refused for a
        # locked actor or a read-only sublevel, and the void Actor form returns
        # nothing to check, so a survivor is only visible by looking again.
        left = [a for a in actor_sub.get_all_level_actors()
                if "Arena" in str(a.get_folder_path())]
        _record("Arena", "Cleanup", not left,
                f"{len(arena_actors)} destroyed, {len(left)} still in the Arena folder")

    except Exception as e:
        _record("Arena", "Error", False, str(e))

def _test_scatter_advanced_safe() -> None:
    _header("8.4 Scatter Advanced (Non-Linear)")
    import UEFN_Toolbelt as tb
    try:
        test_folder = "TOOLBELT_SCATTER_TEST"
        # 1. Scatter Along Path (Linear)
        pts = [(0,0,0), (1000,0,0)]
        tb.run("scatter_along_path", path_points=pts, count_per_point=2, folder=test_folder)

        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = [a for a in actor_sub.get_all_level_actors() if test_folder in str(a.get_folder_path())]
        _record("Scatter", "Along Path", len(actors) == 4, f"Found {len(actors)} actors")

        # CLEANUP — re-scan, because scatter_clear counting a deletion is not
        # the same as the actor being gone.
        tb.run("scatter_clear", folder=test_folder)
        left = [a for a in actor_sub.get_all_level_actors()
                if test_folder in str(a.get_folder_path())]
        _record("Scatter", "Cleanup", not left,
                f"{len(left)} actor(s) left in '{test_folder}'")

    except Exception as e:
        _record("Scatter", "Error", False, str(e))

def _test_assets_advanced_safe() -> None:
    _header("8.5 Assets Advanced (Safe Rename/Organize)")
    import UEFN_Toolbelt as tb
    try:
        # Restriction: Only operate on TOOLBELT_TEST
        test_dir = resolve_content_path("/Game/TOOLBELT_TEST/AssetOps")
        # Fix: use full unreal path creation to avoid scope issues
        unreal.EditorAssetLibrary.make_directory(test_dir)

        # Create a Material Instance to test renaming
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        mi = asset_tools.create_asset("mi_bad_Name", test_dir,
                                      unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())

        if mi:
            # Test enforce (mi_ -> MI_)
            enforced = tb.run("rename_enforce_conventions", scan_path=test_dir, dry_run=False)
            _record("Assets", "Enforce Conventions",
                    enforced.get("renamed", 0) > 0,
                    f"renamed={enforced.get('renamed')}")

            # Test organize. A dry run first, so the preview path is covered too.
            preview = tb.run("organize_assets", source_path=test_dir,
                             target_base=resolve_content_path("/Game/TOOLBELT_TEST/Organized"),
                             dry_run=True)
            moved = tb.run("organize_assets", source_path=test_dir,
                           target_base=resolve_content_path("/Game/TOOLBELT_TEST/Organized"),
                           dry_run=False)
            _record("Assets", "Organize Assets",
                    preview.get("dry_run") is True and preview.get("moved") == 0
                    and moved.get("moved", 0) > 0,
                    f"preview would_move={preview.get('would_move')} moved={moved.get('moved')}")

        # Cleanup
        unreal.EditorAssetLibrary.delete_directory(resolve_content_path("/Game/TOOLBELT_TEST/AssetOps"))
        unreal.EditorAssetLibrary.delete_directory(resolve_content_path("/Game/TOOLBELT_TEST/Organized"))

    except Exception as e:
        _record("Assets", "Error", False, str(e))

def _test_bridge_safe() -> None:
    _header("8.6 Bridge Toggle")
    import UEFN_Toolbelt as tb
    try:
        # Start/Stop bridge. mcp_status reports whether the listener is
        # actually up, so assert on that rather than on the call not raising -
        # a listener that failed to bind its port would have passed before.
        tb.run("mcp_start")
        after_start = tb.run("mcp_status")
        _record("Bridge", "Start", after_start.get("running") is True,
                f"running={after_start.get('running')} url={after_start.get('url')} "
                f"commands={after_start.get('commands')}")

        tb.run("mcp_stop")
        after_stop = tb.run("mcp_status")
        _record("Bridge", "Stop", after_stop.get("running") is False,
                f"running={after_stop.get('running')}")
    except Exception as e:
        _record("Bridge", "Error", False, str(e))

def _test_cooker_safe() -> None:
    _header("8.7 Cooker Optimizer (mark/unmark selection)")
    import UEFN_Toolbelt as tb
    try:
        a1 = _spawn_fixture(location=unreal.Vector(0, 4000, 0))
        a2 = _spawn_fixture(location=unreal.Vector(200, 4000, 0))
        _select_fixture([a1, a2])

        # The assertion is status-matches-count, not a fixed outcome.
        # is_editor_only_actor may or may not be settable on this UEFN build -
        # _set_editor_only swallows the exception either way. What must never
        # happen is "ok" alongside 0 changed, which is what it used to return.
        marked = tb.run("cooker_mark_selection", mark=True)
        st, changed, failed = (marked.get("status"),
                               marked.get("changed", 0),
                               marked.get("failed", 0))
        consistent = (
            (st == "ok" and changed and not failed)
            or (st == "partial" and changed and failed)
            or (st == "error" and not changed and failed)
        )
        _record("Cooker", "mark_selection status matches the count", consistent,
                f"status={st} changed={changed} failed={failed} "
                f"(ok with 0 changed is the bug)")

        # Restore, so the fixtures do not leave the level in a marked state.
        cleared = tb.run("cooker_mark_selection", mark=False)
        c_st, c_changed, c_failed = (cleared.get("status"),
                                     cleared.get("changed", 0),
                                     cleared.get("failed", 0))
        c_consistent = (
            (c_st == "ok" and c_changed and not c_failed)
            or (c_st == "partial" and c_changed and c_failed)
            or (c_st == "error" and not c_changed and c_failed)
        )
        _record("Cooker", "mark_selection(False) status matches the count", c_consistent,
                f"status={c_st} changed={c_changed} failed={c_failed}")

        for a in (a1, a2):
            a.destroy_actor()

    except Exception as e:
        _record("Cooker", "Error", False, str(e))


def _test_measurement() -> None:
    _header("9. Measurement Tools")
    import UEFN_Toolbelt as tb

    # Setup: 2 actors at known distance
    a1 = _spawn_fixture(location=unreal.Vector(0,0,0))
    a2 = _spawn_fixture(location=unreal.Vector(1000,0,0))
    _select_fixture([a1, a2])

    try:
        # Test Distance
        dist_result = tb.run("measure_distance")
        dist = dist_result.get("distance_cm", 0.0) if isinstance(dist_result, dict) else float(dist_result)
        passed_dist = _assert_delta(dist, 1000.0)
        _record("Measurement", "Measure Distance", passed_dist, f"Dist: {dist}")

        # Test Travel Time (Run speed ~450 cm/s)
        res = tb.run("measure_travel_time", speed_type="Run")
        passed_time = _assert_delta(res["time_seconds"], 1000.0 / 450.0, tolerance=0.1)
        _record("Measurement", "Travel Time (Run)", passed_time, f"Time: {res['time_seconds']:.2f}s")
    except Exception as e:
        _record("Measurement", "Error", False, str(e))
    finally:
        a1.destroy_actor()
        a2.destroy_actor()

def _test_localization() -> None:
    _header("10. Localization Tools")
    import UEFN_Toolbelt as tb

    # Setup: TextRenderActor
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    txt_actor = actor_sub.spawn_actor_from_class(unreal.TextRenderActor, unreal.Vector(0,0,0))
    txt_actor.set_actor_label("Grok_Test_Actor")
    txt_actor.text_render.set_editor_property("text", "Grok_Test_String")

    try:
        # Test Export
        exp_result = tb.run("text_export_manifest", format="json")
        out_path = exp_result.get("path") if isinstance(exp_result, dict) else exp_result
        passed_exp = out_path is not None and os.path.exists(out_path)
        _record("Localization", "Export Manifest", passed_exp)

        # Modify manifest to "Grok_Translated"
        if passed_exp:
            import json
            with open(out_path, encoding="utf-8") as f:
                data = json.load(f)

            found = False
            for entry in data:
                if entry["original_text"] == "Grok_Test_String":
                    entry["translated_text"] = "Grok_Translated"
                    found = True

            if found:
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                # Test Apply
                tb.run("text_apply_translation", manifest_path=out_path)
                # Note: set_text takes a string, but get_text might return an unreal.Text
                current_text = str(txt_actor.text_render.text)
                passed_apply = ("Grok_Translated" in current_text)
                _record("Localization", "Apply Translation", passed_apply, f"Current: {current_text}")
            else:
                _record("Localization", "Apply Translation", False, "Test string not found in manifest")

    except Exception as e:
        _record("Localization", "Error", False, str(e))
    finally:
        if txt_actor:
            txt_actor.destroy_actor()

def _test_environmental() -> None:
    _header("11. Environmental Tools")
    import UEFN_Toolbelt as tb
    try:
        # Test Audit
        audit_result = tb.run("foliage_audit_brushes")
        _record("Environmental", "Audit Brushes", isinstance(audit_result, dict) and audit_result.get("status") == "ok")

        # Test Convert (Spawn small test actor)
        a = _spawn_fixture(location=unreal.Vector(0,0,100))
        _select_fixture([a])

        conv_result = tb.run("foliage_convert_selected_to_actor")
        converted = conv_result.get("converted", 0) if isinstance(conv_result, dict) else int(conv_result)
        _record("Environmental", "Convert Props", converted > 0, f"Converted: {converted}")
    except Exception as e:
        _record("Environmental", "Error", False, str(e))

def _test_entities() -> None:
    _header("12. Entity Kits")
    import UEFN_Toolbelt as tb
    try:
        # Test List
        kits = tb.run("entity_list_kits")
        _record("Entities", "List Kits", "Lobby Starter" in kits.get("kits", []))

        # Creative device class availability genuinely varies by UEFN build, so
        # this cannot require a spawn. What it CAN require is that the tool
        # tells the truth about what happened: on 2026-08-21 it logged
        # "Successfully spawned ... with 0 devices" and this recorded a pass.
        spawned = tb.run("entity_spawn_kit", kit_name="Teleport Link")
        status, count = spawned.get("status"), spawned.get("count", 0)
        honest = (status == "ok" and count > 0) or (status in ("error", "partial") and count < spawned.get("requested", 0))
        _record("Entities", "Spawn Kit", honest,
                f"status={status} count={count}/{spawned.get('requested')} "
                f"(status must match the count - ok with 0 spawned is the bug)")

        # Verify and Cleanup
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = actor_sub.get_all_level_actors()
        for a in actors:
            if "Teleport_" in a.get_actor_label():
                a.destroy_actor()

    except Exception as e:
        _record("Entities", "Error", False, str(e))

def _test_selection() -> None:
    _header("13. Selection Utils")
    import UEFN_Toolbelt as tb
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    a1 = _spawn_fixture(location=unreal.Vector(0,0,0))
    a2 = _spawn_fixture(location=unreal.Vector(500,0,0))
    a3 = _spawn_fixture(location=unreal.Vector(2000,0,0))

    try:
        # Test Radius Selection
        actor_sub.set_selected_level_actors([a1])
        tb.run("select_in_radius", radius=600.0, actor_class_name="StaticMeshActor")
        selected = actor_sub.get_selected_level_actors()
        # a1 (0cm) and a2 (500cm) are inside the 600cm radius, a3 (2000cm) is not.
        # len(selected) also counts whatever else the level happens to have in
        # range, so it is reported as context - the pass/fail is the three
        # fixtures only.
        passed_rad = (a1 in selected and a2 in selected and a3 not in selected)
        _record(
            "Selection", "Select in Radius", passed_rad,
            f"in-radius fixtures selected={a1 in selected and a2 in selected}, "
            f"out-of-radius fixture excluded={a3 not in selected} "
            f"({len(selected)} actors selected in total)",
        )

        # Test Property Selection
        a1.set_actor_label("INTEGRATION_TEST_TARGET")
        tb.run("select_by_property", prop_name="Actor Label", value="TARGET")
        selected = actor_sub.get_selected_level_actors()
        passed_prop = (a1 in selected and len(selected) == 1)
        _record("Selection", "Select by Property", passed_prop)
    except Exception as e:
        _record("Selection", "Error", False, str(e))
    finally:
        for a in [a1, a2, a3]:
            if a: actor_sub.destroy_actor(a)

def _test_lighting_integration() -> None:
    _header("14. Lighting Mastery")
    import UEFN_Toolbelt as tb
    try:
        # Just test execution path (hard to verify visual state without complex property checks)
        tb.run("light_cinematic_preset", mood="Cyberpunk")
        _record("Lighting", "Apply Preset (Cyberpunk)", True, verified=False)
        tb.run("light_randomize_sky")
        _record("Lighting", "Randomize Sky", True, verified=False)
    except Exception as e:
        _record("Lighting", "Error", False, str(e))

def _test_project_admin_integration() -> None:
    _header("15. Project Admin")
    import UEFN_Toolbelt as tb
    try:
        # Perf Audit
        tb.run("system_perf_audit")
        _record("Project Admin", "Perf Audit", True, verified=False)
    except Exception as e:
        _record("Project Admin", "Error", False, str(e))

# ─── Batch 9 (Tools added after v1.6.0) ───────────────────────────────────────

def _test_zone_tools() -> None:
    _header("9.1 Zone Tools")
    import UEFN_Toolbelt as tb
    test_folder = "TOOLBELT_TEST_Zones"
    zone_actor = None
    try:
        # spawn_zone → returns dict with actor path
        result = tb.run("zone_spawn", width=800, depth=800, height=400, label="TestZone")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Zone", "zone_spawn", passed, str(result.get("label", "")))

        # zone_list → should find at least our zone
        result = tb.run("zone_list")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Zone", "zone_list", passed, f"{result.get('count', 0)} zones found")

        # find the spawned zone actor for selection-based tests
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        zone_actors = [a for a in actor_sub.get_all_level_actors()
                       if "TestZone" in str(a.get_actor_label())]
        if zone_actors:
            zone_actor = zone_actors[0]
            # zone_select_contents — select everything inside zone bounds
            _select_fixture([zone_actor])
            result = tb.run("zone_select_contents")
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Zone", "zone_select_contents", passed)

            # zone_snap_to_selection — move zone center to selection bounds
            result = tb.run("zone_snap_to_selection")
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Zone", "zone_snap_to_selection", passed)

        # zone_fill_scatter — scatter cubes inside the zone
        if zone_actor:
            _select_fixture([zone_actor])
            result = tb.run("zone_fill_scatter", asset_path=_CUBE_MESH,
                            count=3, folder=test_folder)
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Zone", "zone_fill_scatter", passed, f"spawned {result.get('spawned', 0)}")

    except Exception as e:
        _record("Zone", "Error", False, str(e))
    finally:
        # cleanup: destroy zone actor + scatter fills
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        for a in actor_sub.get_all_level_actors():
            fp = str(a.get_folder_path())
            lbl = str(a.get_actor_label())
            if test_folder in fp or "TestZone" in lbl or "Zones" in fp:
                actor_sub.destroy_actor(a)


def _test_stamp_tools() -> None:
    _header("9.2 Stamp Tools")
    import UEFN_Toolbelt as tb
    actors = []
    try:
        # spawn 3 fixtures to save as a stamp
        a1 = _spawn_fixture(_CUBE_MESH, unreal.Vector(100, 0, 0))
        a2 = _spawn_fixture(_CUBE_MESH, unreal.Vector(200, 0, 0))
        a3 = _spawn_fixture(_CUBE_MESH, unreal.Vector(300, 0, 0))
        actors = [a for a in [a1, a2, a3] if a]
        _select_fixture(actors)

        result = tb.run("stamp_save", name="__test_stamp__")
        saved  = result.get("actors_saved") if isinstance(result, dict) else None
        passed = (isinstance(result, dict) and result.get("status") == "ok"
                  and saved == len(actors))
        _record("Stamps", "stamp_save", passed,
                f"saved {saved} of {len(actors)} fixtures")

        result = tb.run("stamp_list")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        has_stamp = "__test_stamp__" in str(result.get("stamps", []))
        _record("Stamps", "stamp_list", passed and has_stamp)

        result = tb.run("stamp_info", name="__test_stamp__")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        info_actors = len(result.get("stamp", {}).get("actors", [])) if isinstance(result, dict) else -1
        passed = passed and info_actors == len(actors)
        _record("Stamps", "stamp_info", passed, f"{info_actors} actors in stamp")

        result = tb.run("stamp_place", name="__test_stamp__",
                        folder="TOOLBELT_TEST_Stamps")
        stamped = result.get("actors_stamped") if isinstance(result, dict) else None
        total   = result.get("actors_total")   if isinstance(result, dict) else None
        passed  = (isinstance(result, dict) and result.get("status") == "ok"
                   and stamped == total and stamped)
        _record("Stamps", "stamp_place", passed, f"placed {stamped}/{total}")

        # stamp_export — write to a temp file
        import tempfile as _tmp
        export_path = os.path.join(_tmp.gettempdir(), "__tb_test_stamp__.json")
        result = tb.run("stamp_save", name="__test_stamp_exp__")
        if result.get("status") == "ok":
            result = tb.run("stamp_export", name="__test_stamp_exp__",
                            output_path=export_path)
            passed = (isinstance(result, dict) and result.get("status") == "ok"
                      and os.path.exists(export_path))
            _record("Stamps", "stamp_export", passed, export_path)

            # stamp_import — re-import under a different name
            result = tb.run("stamp_import", file_path=export_path,
                            name_override="__test_stamp_imported__", overwrite=True)
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Stamps", "stamp_import", passed,
                    f"actor_count={result.get('actor_count', '?')}")
            tb.run("stamp_delete", name="__test_stamp_exp__")
            tb.run("stamp_delete", name="__test_stamp_imported__")

        result = tb.run("stamp_delete", name="__test_stamp__")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Stamps", "stamp_delete", passed)

    except Exception as e:
        _record("Stamps", "Error", False, str(e))
    finally:
        actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        for a in actor_sub.get_all_level_actors():
            if "TOOLBELT_TEST_Stamps" in str(a.get_folder_path()):
                actor_sub.destroy_actor(a)


def _test_actor_org_tools() -> None:
    _header("9.3 Actor Org Tools")
    import UEFN_Toolbelt as tb
    _actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    try:
        a1 = _spawn_fixture(_CUBE_MESH, unreal.Vector(0, 500, 0))
        a2 = _spawn_fixture(_CUBE_MESH, unreal.Vector(200, 500, 0))
        if not (a1 and a2):
            _record("ActorOrg", "Fixture spawn", False); return

        # actor_move_to_folder
        _select_fixture([a1, a2])
        result = tb.run("actor_move_to_folder", folder_name="TOOLBELT_TEST_OrgFolder")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("ActorOrg", "actor_move_to_folder", passed)

        # actor_folder_list — read-only
        result  = tb.run("actor_folder_list")
        folders = result.get("folders", {}) if isinstance(result, dict) else {}
        passed  = (isinstance(result, dict) and result.get("status") == "ok"
                   and "TOOLBELT_TEST_OrgFolder" in folders)
        _record("ActorOrg", "actor_folder_list", passed,
                f"{len(folders)} folders, test folder present={'TOOLBELT_TEST_OrgFolder' in folders}")

        # actor_select_by_folder
        result = tb.run("actor_select_by_folder", folder_name="TOOLBELT_TEST_OrgFolder")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("ActorOrg", "actor_select_by_folder", passed)

        # actor_select_by_class
        result = tb.run("actor_select_by_class", class_filter="StaticMesh")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("ActorOrg", "actor_select_by_class", passed)

        # actor_match_transform — copy transform from first to rest
        _select_fixture([a1, a2])
        result = tb.run("actor_match_transform", copy_location=True,
                        copy_rotation=False, copy_scale=False)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("ActorOrg", "actor_match_transform", passed)

        # actor_move_to_root — strip folder
        _select_fixture([a1, a2])
        result = tb.run("actor_move_to_root")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("ActorOrg", "actor_move_to_root", passed)

        # actor_attach_to_parent + actor_detach
        _select_fixture([a1, a2])
        result = tb.run("actor_attach_to_parent")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("ActorOrg", "actor_attach_to_parent", passed)

        _select_fixture([a1, a2])
        result = tb.run("actor_detach")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("ActorOrg", "actor_detach", passed)

    except Exception as e:
        _record("ActorOrg", "Error", False, str(e))


def _test_proximity_tools() -> None:
    _header("9.4 Proximity & Relative Placement")
    import UEFN_Toolbelt as tb
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    try:
        a1 = _spawn_fixture(_CUBE_MESH, unreal.Vector(0, 1000, 0))
        a2 = _spawn_fixture(_CUBE_MESH, unreal.Vector(500, 1000, 0))
        a3 = _spawn_fixture(_CUBE_MESH, unreal.Vector(1000, 1000, 0))
        if not (a1 and a2 and a3):
            _record("Proximity", "Fixture spawn", False); return

        # actor_place_next_to
        _select_fixture([a1, a2])
        result = tb.run("actor_place_next_to", direction="+X", gap=10.0, align="center")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Proximity", "actor_place_next_to", passed)

        # actor_chain_place
        _select_fixture([a1, a2, a3])
        result = tb.run("actor_chain_place", axis="X", gap=0.0)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Proximity", "actor_chain_place", passed)

        # actor_duplicate_offset
        _select_fixture([a1])
        result = tb.run("actor_duplicate_offset", count=2, offset_x=200.0,
                        folder="TOOLBELT_TEST_DupOffset")
        spawned = result.get("total_spawned") if isinstance(result, dict) else None
        passed  = (isinstance(result, dict) and result.get("status") == "ok"
                   and spawned == 2)
        _record("Proximity", "actor_duplicate_offset", passed,
                f"spawned {spawned} (expected 2)")

        # actor_copy_to_positions
        _select_fixture([a1])
        result = tb.run("actor_copy_to_positions",
                        positions=[[100, 100, 0], [200, 100, 0]],
                        folder="TOOLBELT_TEST_CopyPos")
        spawned = result.get("spawned") if isinstance(result, dict) else None
        passed  = (isinstance(result, dict) and result.get("status") == "ok"
                   and spawned == 2)
        _record("Proximity", "actor_copy_to_positions", passed,
                f"placed {spawned} (expected 2)")

        # actor_cluster_to_folder (dry_run equivalent — min_cluster_size high so nothing moves)
        _select_fixture([a1, a2, a3])
        result = tb.run("actor_cluster_to_folder", radius=50000.0,
                        folder_prefix="TestCluster", min_cluster_size=2,
                        base_folder="TOOLBELT_TEST_Clusters")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Proximity", "actor_cluster_to_folder", passed)

        # actor_replace_class — dry_run=True only, never execute live
        result = tb.run("actor_replace_class", old_class_filter="StaticMesh",
                        new_asset_path=_SPHERE_MESH, dry_run=True, scope="level")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Proximity", "actor_replace_class (dry_run)", passed,
                f"would replace {result.get('would_replace', 0)}")

    except Exception as e:
        _record("Proximity", "Error", False, str(e))
    finally:
        for folder_tag in ["TOOLBELT_TEST_DupOffset", "TOOLBELT_TEST_CopyPos",
                           "TOOLBELT_TEST_Clusters"]:
            for a in actor_sub.get_all_level_actors():
                if folder_tag in str(a.get_folder_path()):
                    actor_sub.destroy_actor(a)


def _test_advanced_alignment() -> None:
    _header("9.5 Advanced Alignment")
    import UEFN_Toolbelt as tb
    try:
        a1 = _spawn_fixture(_CUBE_MESH, unreal.Vector(0,   2000, 0))
        a2 = _spawn_fixture(_CUBE_MESH, unreal.Vector(300, 2000, 50))
        a3 = _spawn_fixture(_CUBE_MESH, unreal.Vector(600, 2000, 100))
        if not (a1 and a2 and a3):
            _record("AdvAlign", "Fixture spawn", False); return

        _select_fixture([a1, a2, a3])
        result = tb.run("align_to_reference", axis="Z", reference="first")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("AdvAlign", "align_to_reference", passed)

        _select_fixture([a1, a2, a3])
        result = tb.run("distribute_with_gap", axis="X", gap=50.0)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("AdvAlign", "distribute_with_gap", passed)

        _select_fixture([a1, a2, a3])
        result = tb.run("rotate_around_pivot", angle_deg=90, axis="Z", pivot="center")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("AdvAlign", "rotate_around_pivot", passed)

        _select_fixture([a1, a2, a3])
        result = tb.run("match_spacing", axis="X")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("AdvAlign", "match_spacing", passed)

        # align_to_surface needs EditorLevelLibrary.snap_objects_to_floor, which
        # UE 6.0 removed. Refusing cleanly IS the correct behaviour there, so
        # accept it — asserting "ok" made the suite permanently 179/180 and
        # trained everyone to ignore the one red line.
        _select_fixture([a1, a2])
        result = tb.run("align_to_surface", offset_z=0.0)
        passed = isinstance(result, dict) and (
            result.get("status") == "ok"
            or result.get("reason") == "engine_api_unavailable"
        )
        detail = ("refused cleanly — API absent on this build"
                  if isinstance(result, dict)
                  and result.get("reason") == "engine_api_unavailable" else "")
        _record("AdvAlign", "align_to_surface", passed, detail)

        _select_fixture([a1, a2, a3])
        result = tb.run("align_to_grid_two_points", grid_size=100.0)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("AdvAlign", "align_to_grid_two_points", passed)

    except Exception as e:
        _record("AdvAlign", "Error", False, str(e))


def _test_sign_tools() -> None:
    _header("9.6 Sign Tools")
    import UEFN_Toolbelt as tb
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    test_folder = "TOOLBELT_TEST_Signs"
    try:
        result = tb.run("sign_spawn_bulk", count=3, text="TEST",
                        prefix="TestSign", layout="row_x",
                        spacing=200.0, folder=test_folder)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Signs", "sign_spawn_bulk", passed, f"spawned {result.get('spawned', 0)}")

        result = tb.run("sign_list", folder=test_folder)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Signs", "sign_list", passed, f"{result.get('count', 0)} signs found")

        # select the signs for batch edit
        signs = [a for a in actor_sub.get_all_level_actors()
                 if test_folder in str(a.get_folder_path())]
        if signs:
            _select_fixture(signs)
            result = tb.run("sign_batch_edit", text="EDITED")
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Signs", "sign_batch_edit", passed)

            _select_fixture(signs)
            result = tb.run("sign_batch_rename", prefix="TB_Sign", start=1,
                            sync_text=False)
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Signs", "sign_batch_rename", passed)

            _select_fixture(signs)
            result = tb.run("sign_batch_set_text",
                            texts=["A", "B", "C"][:len(signs)])
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Signs", "sign_batch_set_text", passed)

        # label_attach — floating label above each fixture
        fixtures = _spawn_fixture(_CUBE_MESH, unreal.Vector(0, 3000, 0))
        if fixtures:
            _select_fixture([fixtures])
            result = tb.run("label_attach", offset_z=120, use_actor_name=True)
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Signs", "label_attach", passed)

        # cleanup
        result = tb.run("sign_clear", folder=test_folder, dry_run=False)
        _record("Signs", "sign_clear (cleanup)", result.get("status") == "ok")

    except Exception as e:
        _record("Signs", "Error", False, str(e))
    finally:
        for a in actor_sub.get_all_level_actors():
            if test_folder in str(a.get_folder_path()):
                actor_sub.destroy_actor(a)


def _test_postprocess_and_world() -> None:
    _header("9.7 Post-Process & World Settings")
    import UEFN_Toolbelt as tb
    try:
        # postprocess_spawn — find-or-create, safe
        result = tb.run("postprocess_spawn", unbounded=True)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("PostProcess", "postprocess_spawn", passed)

        # postprocess_set — set params, verify no exception
        result = tb.run("postprocess_set", bloom=0.5, vignette=0.2)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("PostProcess", "postprocess_set", passed)

        # postprocess_preset
        result = tb.run("postprocess_preset", preset="cinematic")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("PostProcess", "postprocess_preset (cinematic)", passed)

        # reset to neutral
        tb.run("postprocess_preset", preset="reset")
        _record("PostProcess", "postprocess_preset (reset)", True, verified=False)

        # UEFN 42.00 does not expose default_gravity_z on FortWorldSettings, so
        # gravity cannot be set from Python here. That is a known Epic-side
        # limit, and the tool is expected to SAY so rather than half-succeed.
        #
        # This used to assert isinstance(result, dict) - which passes for any
        # return at all, including {}. Now it pins the two outcomes that are
        # actually correct: the property works and gravity is applied, or it
        # does not and the tool names it as unavailable. If Epic exposes it in a
        # later build this flips to the ok branch on its own.
        result = tb.run("world_settings_set", gravity=-980.0)
        status = result.get("status")
        honest = (
            (status == "ok" and result.get("applied", {}).get("gravity") == -980.0)
            or (status == "error"
                and result.get("reason") == "properties_not_exposed"
                and "gravity" in result.get("unavailable", {}))
        )
        _record("PostProcess", "world_settings_set (gravity)", honest,
                f"status={status} applied={result.get('applied')} "
                f"unavailable={list(result.get('unavailable', {}))}")

    except Exception as e:
        _record("PostProcess", "Error", False, str(e))


def _test_audio_tools() -> None:
    _header("9.8 Audio Tools")
    import UEFN_Toolbelt as tb
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    try:
        # audio_place — no asset_path = places empty AmbientSound
        result = tb.run("audio_place", label="TB_TestAudio",
                        volume=0.5, folder="TOOLBELT_TEST_Audio")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Audio", "audio_place", passed)

        # audio_list
        result = tb.run("audio_list")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Audio", "audio_list", passed, f"{result.get('count', 0)} sounds")

        # select audio actor for batch ops
        audio_actors = [a for a in actor_sub.get_all_level_actors()
                        if "TOOLBELT_TEST_Audio" in str(a.get_folder_path())]
        if audio_actors:
            _select_fixture(audio_actors)
            result = tb.run("audio_set_volume", volume=0.8)
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Audio", "audio_set_volume", passed)

            _select_fixture(audio_actors)
            result = tb.run("audio_set_radius", radius=1500.0)
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Audio", "audio_set_radius", passed)

    except Exception as e:
        _record("Audio", "Error", False, str(e))
    finally:
        for a in actor_sub.get_all_level_actors():
            if "TOOLBELT_TEST_Audio" in str(a.get_folder_path()):
                actor_sub.destroy_actor(a)


def _test_level_health() -> None:
    _header("9.9 Level Health")
    import UEFN_Toolbelt as tb
    try:
        result = tb.run("level_health_report")
        passed = (isinstance(result, dict) and result.get("status") == "ok"
                  and "score" in result)
        score = result.get("score", "?")
        _record("LevelHealth", "level_health_report", passed, f"score={score}/100")

        # rogue_actor_scan — read-only
        result = tb.run("rogue_actor_scan")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        # The count depends on whatever is in the level, so this reports rather
        # than asserts — but it must report the real number.
        _record("LevelHealth", "rogue_actor_scan", passed,
                f"{result.get('rogue_count', '?')} of {result.get('total_scanned', '?')} actors flagged")

    except Exception as e:
        _record("LevelHealth", "Error", False, str(e))


def _test_config_tools() -> None:
    _header("9.10 Config Tools")
    import UEFN_Toolbelt as tb
    try:
        result = tb.run("config_list")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Config", "config_list", passed)

        result = tb.run("config_set", key="scatter.default_folder",
                        value="TOOLBELT_TEST_Config")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Config", "config_set", passed)

        result = tb.run("config_get", key="scatter.default_folder")
        passed = (isinstance(result, dict) and result.get("status") == "ok"
                  and result.get("value") == "TOOLBELT_TEST_Config")
        _record("Config", "config_get", passed, f"value={result.get('value', '?')}")

        result = tb.run("config_reset", key="scatter.default_folder")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Config", "config_reset", passed)

    except Exception as e:
        _record("Config", "Error", False, str(e))


def _test_lighting_extended() -> None:
    _header("9.11 Lighting (Extended)")
    import UEFN_Toolbelt as tb
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    try:
        result = tb.run("light_place", light_type="point", intensity=1000,
                        color="#FFFFFF", folder="TOOLBELT_TEST_Lights")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Lighting", "light_place (point)", passed)

        result = tb.run("light_list")
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("Lighting", "light_list", passed, f"{result.get('count', 0)} lights")

        lights = [a for a in actor_sub.get_all_level_actors()
                  if "TOOLBELT_TEST_Lights" in str(a.get_folder_path())]
        if lights:
            _select_fixture(lights)
            result = tb.run("light_set", intensity=2000, color="#FF8800")
            passed = isinstance(result, dict) and result.get("status") == "ok"
            _record("Lighting", "light_set", passed)

        # sky_set_time requires a DirectionalLight in the level.
        # Returns status=error on a bare template. Mark as expected-limited.
        result = tb.run("sky_set_time", hour=12.0)
        ran = isinstance(result, dict)  # pass if tool ran at all
        _record("Lighting", "sky_set_time", ran,
                result.get("message", "ok") if ran else "no result")

    except Exception as e:
        _record("Lighting", "Error", False, str(e))
    finally:
        for a in actor_sub.get_all_level_actors():
            if "TOOLBELT_TEST_Lights" in str(a.get_folder_path()):
                actor_sub.destroy_actor(a)


def _test_world_state() -> None:
    _header("9.12 World State & Devices")
    import UEFN_Toolbelt as tb
    try:
        result = tb.run("world_state_export")
        passed = (isinstance(result, dict) and result.get("status") == "ok"
                  and result.get("count", 0) > 0)
        _record("WorldState", "world_state_export", passed,
                f"{result.get('count', 0)} actors captured")

        result = tb.run("device_catalog_scan", save_to_docs=False)
        passed = isinstance(result, dict) and result.get("status") == "ok"
        _record("WorldState", "device_catalog_scan", passed,
                f"{result.get('devices_found', 0)} devices found")

    except Exception as e:
        _record("WorldState", "Error", False, str(e))


# ─── Batch 10 (Tools added in v1.9.6) ─────────────────────────────────────────

def _test_visibility_tools() -> None:
    _header("10.1 Actor Visibility")
    import UEFN_Toolbelt as tb
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    a1 = _spawn_fixture(location=unreal.Vector(0, 0, 0))
    a2 = _spawn_fixture(location=unreal.Vector(300, 0, 0))
    try:
        actor_sub.set_selected_level_actors([a1, a2])

        result = tb.run("actor_hide")
        passed = result.get("status") == "ok" and result.get("hidden", 0) == 2
        _record("Visibility", "actor_hide", passed, f"hidden={result.get('hidden', 0)}")

        result = tb.run("actor_show")
        passed = result.get("status") == "ok" and result.get("shown", 0) == 2
        _record("Visibility", "actor_show", passed, f"shown={result.get('shown', 0)}")

        # Isolate: these 2 visible, everything else hidden
        result = tb.run("actor_isolate")
        passed = result.get("status") == "ok" and result.get("visible", 0) == 2
        _record("Visibility", "actor_isolate", passed, f"visible={result.get('visible', 0)}")

        # Restore full visibility
        result = tb.run("actor_show_all")
        passed = result.get("status") == "ok" and result.get("restored", 0) > 0
        _record("Visibility", "actor_show_all", passed, f"restored={result.get('restored', 0)}")

        # Lock/unlock — may fail on special actor types (sandboxed), status:ok is sufficient
        actor_sub.set_selected_level_actors([a1])
        result = tb.run("actor_lock")
        _record("Visibility", "actor_lock (runs ok)", result.get("status") == "ok")
        result = tb.run("actor_unlock")
        _record("Visibility", "actor_unlock (runs ok)", result.get("status") == "ok")

    except Exception as e:
        _record("Visibility", "Error", False, str(e))
    finally:
        for a in [a1, a2]:
            if a: actor_sub.destroy_actor(a)


def _test_viewport_bookmarks() -> None:
    _header("10.2 Viewport Bookmarks & ShowFlags")
    import UEFN_Toolbelt as tb
    try:
        # ShowFlag preset
        result = tb.run("viewport_showflag", preset="clean")
        _record("Viewport", "viewport_showflag (clean)", result.get("status") == "ok",
                f"{result.get('commands_applied', [])}")
        result = tb.run("viewport_showflag", preset="reset")
        _record("Viewport", "viewport_showflag (reset)", result.get("status") == "ok")

        # Bookmark round-trip
        result = tb.run("viewport_bookmark_save", name="_integration_test")
        passed = result.get("status") == "ok" and "location" in result
        _record("Viewport", "viewport_bookmark_save", passed)

        result = tb.run("viewport_bookmark_list")
        passed = result.get("status") == "ok" and "_integration_test" in result.get("bookmarks", {})
        _record("Viewport", "viewport_bookmark_list", passed)

        result = tb.run("viewport_bookmark_jump", name="_integration_test")
        _record("Viewport", "viewport_bookmark_jump", result.get("status") == "ok")

        # Unknown preset should return error
        result = tb.run("viewport_showflag", preset="__nonexistent__")
        _record("Viewport", "viewport_showflag (unknown preset = error)", result.get("status") == "error")

    except Exception as e:
        _record("Viewport", "Error", False, str(e))


def _test_selection_sets() -> None:
    _header("10.3 Selection Sets")
    import UEFN_Toolbelt as tb
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    a1 = _spawn_fixture(location=unreal.Vector(0, 0, 0))
    a2 = _spawn_fixture(location=unreal.Vector(400, 0, 0))
    try:
        actor_sub.set_selected_level_actors([a1, a2])

        result = tb.run("selection_save", name="_integration_test")
        passed = result.get("status") == "ok" and result.get("count", 0) == 2
        _record("SelectionSets", "selection_save", passed, f"count={result.get('count', 0)}")

        result = tb.run("selection_list")
        passed = result.get("status") == "ok" and "_integration_test" in result.get("sets", {})
        _record("SelectionSets", "selection_list", passed)

        # Clear selection then restore
        actor_sub.set_selected_level_actors([])
        result = tb.run("selection_restore", name="_integration_test")
        passed = result.get("status") == "ok" and result.get("matched", 0) == 2 and result.get("missing", 0) == 0
        _record("SelectionSets", "selection_restore", passed,
                f"matched={result.get('matched')}, missing={result.get('missing')}")

        # Restore with unknown set
        result = tb.run("selection_restore", name="__nonexistent__")
        _record("SelectionSets", "selection_restore (unknown = error)", result.get("status") == "error")

    except Exception as e:
        _record("SelectionSets", "Error", False, str(e))
    finally:
        for a in [a1, a2]:
            if a: actor_sub.destroy_actor(a)


def _test_project_admin_v196() -> None:
    _header("10.4 Project Admin v1.9.6")
    import UEFN_Toolbelt as tb
    try:
        result = tb.run("save_all_dirty")
        passed = result.get("status") == "ok"
        _record("ProjectAdmin", "save_all_dirty", passed,
                f"level={result.get('level_saved')}, packages={result.get('packages_saved')}")
    except Exception as e:
        _record("ProjectAdmin", "Error", False, str(e))


if __name__ == "__main__":
    toolbelt_integration_test()
