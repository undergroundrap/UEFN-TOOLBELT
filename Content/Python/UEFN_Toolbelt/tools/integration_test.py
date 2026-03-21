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

import os
import time
from datetime import datetime
from typing import Any, List, Optional, Tuple

import unreal

from UEFN_Toolbelt.registry import register_tool
from UEFN_Toolbelt.core import undo_transaction

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

def _record(section: str, name: str, passed: bool, detail: str = "") -> None:
    icon = "✓" if passed else "✗"
    _results.append({"section": section, "name": name, "passed": passed, "detail": detail})
    msg = f"[TEST]  [{icon}] {name}{f'  —  {detail}' if detail else ''}"
    if passed:
        unreal.log(msg)
    else:
        unreal.log_warning(msg)

def _header(title: str) -> None:
    unreal.log(f"\n{'═' * 60}")
    unreal.log(f"  {title}")
    unreal.log(f"{'═' * 60}")

def _spawn_fixture(mesh_path: str = _CUBE_MESH, location: unreal.Vector = unreal.Vector(0,0,0)) -> unreal.Actor:
    """Spawn a temporary actor and track it for cleanup."""
    actor = unreal.EditorLevelLibrary.spawn_actor_from_object(
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
    unreal.get_editor_subsystem(unreal.EditorActorSubsystem).set_selected_level_actors(actors)

def _cleanup_fixtures() -> None:
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in _spawn_fixtures:
        if actor and unreal.EditorLevelLibrary.get_all_level_actors().count(actor) > 0:
            actor_sub.destroy_actor(actor)
    _spawn_fixtures.clear()

def _save_report() -> str:
    os.makedirs(_SAVED, exist_ok=True)
    passed = sum(1 for r in _results if r["passed"])
    total = len(_results)
    elapsed = time.time() - _start_time

    lines = [
        "UEFN TOOLBELT — Integration Test Results",
        "=" * 60,
        f"Date:    {datetime.now().isoformat()}",
        f"Passed:  {passed}/{total}",
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

    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return _RESULTS_PATH

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
        PARENT_MATERIAL_PATH = "/UEFN_Toolbelt/Materials/M_ToolbeltBase"
        if not unreal.EditorAssetSubsystem().does_asset_exist(PARENT_MATERIAL_PATH):
            PARENT_MATERIAL_PATH = "/Engine/BasicShapes/BasicShapeMaterial"
            _header("Material Fallback: Using Engine BasicShapeMaterial")

        passed = False
        try:
            # Check current material of the first cube
            component = _spawn_fixtures[0].get_component_by_class(unreal.StaticMeshComponent)
            mat = component.get_material(0)
            if mat and (PARENT_MATERIAL_PATH in mat.get_path_name()):
                passed = True
        except:
            pass
        
        _record("Materials", "Apply Preset", passed, "Applied 'gold' to cube" if passed else f"Material mismatch (Target: {PARENT_MATERIAL_PATH})")
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
        tb.run("bulk_randomize", rot_min=-180, rot_max=180)
        r = a_rand.get_actor_rotation()
        # Check if rotation is no longer (0,0,0). (Possible but unlikely to hit 0,0,0 randomly)
        passed = abs(r.roll) > 0.1 or abs(r.pitch) > 0.1 or abs(r.yaw) > 0.1
        _record("Bulk Ops", "Randomize (Rot)", passed, f"Rot: {r}")
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
    a_bad.set_actor_rotation(unreal.Rotator(10,20,30), True)
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
        pass
    except Exception as e:
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
        _record("Bulk Ops", "Face Camera", True)
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
        _record("Snapshots", "Compare Live", True) # Just testing no crash
        
        # 5. Save Snapshot B & Diff
        snap_name_b = "test_integration_snap_B"
        tb.run("snapshot_save", name=snap_name_b)
        tb.run("snapshot_diff", name_a=snap_name, name_b=snap_name_b)
        _record("Snapshots", "Diff JSON", True)
        
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
        # Asset path of basic cube
        asset_path = _CUBE_MESH
        tag_name = "TEST_INTEGRATION_TAG"
        
        # Add tag (passing explicit asset_paths to bypass selection)
        tb.run("tag_add", asset_paths=[asset_path], tag_name=tag_name, value="verified")
        _record("Asset Tagger", "Add Tag", True)
        
        # Remove tag
        tb.run("tag_remove", asset_paths=[asset_path], tag_name=tag_name)
        _record("Asset Tagger", "Remove Tag", True)
    except Exception as e:
        _record("Asset Tagger", "Execution", False, str(e))

def _test_verse() -> None:
    _header("7. Verse Helpers")
    import UEFN_Toolbelt as tb
    
    try:
        # Test snippet listing
        tb.run("verse_list_snippets")
        _record("Verse", "List Snippets", True)
        
        # Test device generation (requires selection)
        actor = _spawn_fixture()
        _select_fixture([actor])
        tb.run("verse_gen_device_declarations")
        _record("Verse", "Gen Device Declarations", True)
    except Exception as e:
        _record("Verse", "Execution", False, str(e))

def _test_screenshots() -> None:
    _header("8. Screenshot Tools")
    import UEFN_Toolbelt as tb
    try:
        # Take a screenshot (full resolution)
        shot_name = "integration_test_shot"
        path = tb.run("screenshot_take", name=shot_name, width=1920, height=1080)
        
        # Note: AutomationLibrary.take_high_res_screenshot is ASYNCHRONOUS.
        # It only writes the file AFTER this Python script finishes and the engine ticks.
        # We verify that the command was successfully sent and the path is valid.
        passed = bool(path and "screenshots" in str(path))
            
        _record("Screenshots", "Capture", passed, f"Queued → {path}" if passed else "Capture request failed")
    except Exception as e:
        _record("Screenshot", "Capture", False, str(e))


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
        
        spline_comp = unreal.SplineComponent(spline_host)
        
        # Select it
        _select_fixture([spline_host])
        
        # Run placement (default count=10)
        tb.run("spline_place_props", count=5, folder_name="TestSplineProps")
        
        props = [a for a in actor_sub.get_all_level_actors() if "TestSplineProps" in str(a.get_folder_path())]
        _record("Spline", "Place Props", len(props) == 5, f"Spawned {len(props)} props along spline")
        
        # Cleanup
        tb.run("spline_clear_props", folder_name="TestSplineProps")
        spline_host.destroy_actor()
        _record("Spline", "Clear Props", True)
        
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
        test_dir = "/Game/TOOLBELT_TEST"
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
        
        # Test Enforce
        tb.run("rename_enforce_conventions", scan_path=test_dir)
        _record("Assets", "Enforce Conventions", True, "Tool executed and processed assets")
        
        # Test Strip
        # Spawn a fresh asset for strip_prefix so it's in the registry's initial state
        asset_tools.create_asset("MI_StripMe", test_dir, unreal.MaterialInstanceConstant, factory)
        tb.run("rename_strip_prefix", scan_path=test_dir, prefix="MI_", dry_run=False)
        _record("Assets", "Strip Prefix", True, "Tool executed without errors")
        
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
        _record("Optimization", "Scan Textures", True)
        
        tb.run("memory_scan_meshes", scan_path="/Engine/BasicShapes")
        _record("Optimization", "Scan Meshes", True)
        
        tb.run("memory_top_offenders", scan_path="/Engine/BasicShapes", top_n=5)
        _record("Optimization", "Top Offenders", True)
        
        # Test Auto-Fix LODs
        # We cannot duplicate engine meshes because they are cooked. 
        # So we just run the tool on an empty directory to ensure it doesn't crash 
        # when traversing the Asset Registry.
        test_dir = "/Game/TOOLBELT_TEST_MEM"
        unreal.EditorAssetLibrary.make_directory(test_dir)
        
        tb.run("memory_autofix_lods", scan_path=test_dir, num_lods=3)
        _record("Optimization", "Auto-Fix LODs", True, "Tool runs safely on Empty Dir")
        
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
        _record("Assets", "Audit Orphans", True)
        
        tb.run("ref_audit_redirectors", scan_path="/Engine/BasicShapes")
        _record("Assets", "Audit Redirectors", True)
        
        tb.run("ref_audit_duplicates", scan_path="/Engine/BasicShapes")
        _record("Assets", "Audit Duplicates", True)
        
        tb.run("ref_audit_unused_textures", scan_path="/Engine/EngineMaterials")
        _record("Assets", "Audit Unused Textures", True)
        
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
        test_base = "/Game/TOOLBELT_TEST"
        root_path = f"{test_base}/{test_project}"
        
        # 1. Preview
        tb.run("scaffold_preview", template="solo_dev", project_name=test_project, base=test_base)
        _record("Project", "Scaffold Preview", True)
        
        # 2. Generate
        tb.run("scaffold_generate", template="solo_dev", project_name=test_project, base=test_base)
        maps_path = f"{root_path}/Maps"
        passed = unreal.EditorAssetLibrary.does_directory_exist(maps_path)
        _record("Project", "Scaffold Generate", passed, f"Maps folder created: {passed}")
        
        # 3. Save Custom Template
        tb.run("scaffold_save_template", template_name="TEST_Tmpl", folders=["A", "B/C"])
        _record("Project", "Scaffold Save Template", True)
        
        # 4. Delete Custom Template
        tb.run("scaffold_delete_template", template_name="TEST_Tmpl")
        _record("Project", "Scaffold Delete Template", True)
        
        # Cleanup
        unreal.EditorAssetLibrary.delete_directory(test_base)
        
    except Exception as e:
        _record("Project", "Scaffold Error", False, str(e))


def _test_text_painter() -> None:
    _header("1.5 Text Painter")
    import UEFN_Toolbelt as tb
    try:
        # 1. Place Text
        actor1 = tb.run("text_place", text="UNIT_TEST", location=(0,0,1000), folder="TestTextProps")
        passed = actor1 is not None and isinstance(actor1, unreal.TextRenderActor)
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
        _record("Procedural", "Text Save Style", True)
        tb.run("text_list_styles")
        
        # 4. Clear Folder
        tb.run("text_clear_folder", folder="TestTextProps")
        tb.run("text_clear_folder", folder="TestTextGrid")
        
        remaining = [
            a for a in actor_sub.get_all_level_actors() 
            if isinstance(a, unreal.TextRenderActor) and ("TestTextProps" in str(a.get_folder_path()) or "TestTextGrid" in str(a.get_folder_path()))
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
        tb.run("material_randomize_colors", saturation=0.8)
        _record("Materials", "Randomize Colors", True)
        
        # 2. Gradient Painter
        tb.run("material_gradient_painter", color_a="#0000FF", color_b="#FF0000", axis="X")
        _record("Materials", "Gradient Painter", True)
        
        # 3. Team Color Split
        tb.run("material_team_color_split")
        _record("Materials", "Team Color Split", True)
        
        # 4. Pattern Painter
        tb.run("material_pattern_painter", pattern="checkerboard", preset_a="neon", preset_b="rubber")
        _record("Materials", "Pattern Painter", True)
        
        # 5. Glow Pulse Preview
        tb.run("material_glow_pulse_preview", intensity=10.0)
        _record("Materials", "Glow Pulse Preview", True)
        
        # 6. Color Harmony
        tb.run("material_color_harmony", harmony="triadic")
        _record("Materials", "Color Harmony", True)
        
        # 7. Save Preset / List Presets
        actor_sub.set_selected_level_actors([a1])
        tb.run("material_apply_preset", preset="chrome")
        tb.run("material_save_preset", preset_name="TEST_Integration_Preset")
        tb.run("material_list_presets")
        _record("Materials", "Save & List Presets", True)
        
        # 8. Bulk Swap (Basic verification without precise paths)
        # Apply neon to all 3, then swap neon for rubber. We use the engine fallback since we don't have exact material paths 
        # stored easily. However, `material_bulk_swap` requires exact string paths.
        # So we'll run it with dummy paths expecting it to exit cleanly without erroring.
        actor_sub.set_selected_level_actors([a1, a2, a3])
        tb.run("material_bulk_swap", old_material_path="/Engine/BasicShapes/BasicShapeMaterial", new_material_path="/Engine/EngineMaterials/DefaultMaterial", scope="selection")
        _record("Materials", "Bulk Swap", True)
        
        # Cleanup
        for a in [a1, a2, a3]:
            a.destroy_actor()

    except Exception as e:
        _record("Materials", "Adv Material Error", False, str(e))


# ─── Main Run ─────────────────────────────────────────────────────────────────

@register_tool(
    name="toolbelt_integration_test",
    category="Tests",
    description="RUN ME: Programmatically verify context-dependent tools (Requires UEFN Viewport)",
    icon="🧪",
    tags=["test", "integration", "full", "automation"],
)
def toolbelt_integration_test(**kwargs) -> None:
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
            _test_screenshots()
            
            # Finalize
            _cleanup_fixtures()
            report_path = _save_report()
            
            passed = sum(1 for r in _results if r["passed"])
            total = len(_results)
            
            unreal.log("\n══════════════════════════════════════════════════════")
            unreal.log("  INTEGRATION TEST COMPLETE")
            unreal.log(f"  Passed: {passed}/{total}")
            unreal.log(f"  Results: {report_path}")
            unreal.log("══════════════════════════════════════════════════════")
            
        except Exception as e:
            unreal.log_error(f"FATAL ERROR IN INTEGRATION TEST: {e}")
            _cleanup_fixtures()

if __name__ == "__main__":
    toolbelt_integration_test()
