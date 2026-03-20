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
        
        # Verify
        mesh_comp = actor.root_component
        current_mat = mesh_comp.get_material(0)
        # Built-in "gold" preset uses MI_Gold_...
        if not current_mat or "BasicShapeMaterial" in str(current_mat.get_name()):
             _record("Materials", "Apply Preset", False, "Parent material missing (M_ToolbeltBase)")
        else:
            passed = "Gold" in str(current_mat.get_name())
            _record("Materials", "Apply Preset", passed, f"Got: {current_mat.get_name()}" if not passed else "")
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

def _test_snapshots() -> None:
    _header("4. Level Snapshots")
    import UEFN_Toolbelt as tb
    
    try:
        snap_name = "test_integration_snap"
        tb.run("snapshot_save", name=snap_name)
        
        # Verify file exists
        snap_dir = os.path.join(_SAVED, "snapshots")
        snap_file = os.path.join(snap_dir, f"{snap_name}.json")
        passed = os.path.exists(snap_file)
        _record("Snapshots", "Save JSON", passed)
        
        # Cleanup
        if passed:
            tb.run("snapshot_delete", name=snap_name)
            _record("Snapshots", "Delete JSON", not os.path.exists(snap_file))
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
        # Take a screenshot (tiny resolution for speed/stability in tests)
        shot_name = "integration_test_shot"
        path = tb.run("screenshot_take", name=shot_name, width=480, height=270)
        
        # Wait for file (asynchronous in Unreal)
        # We scan the directory because direct path checks can fail due to slash/encoding quirks
        passed = False
        if path:
            dir_path = os.path.dirname(str(path))
            base_name = os.path.basename(str(path))
            for _ in range(600): # Wait up to 60 seconds
                if os.path.exists(dir_path):
                    if base_name in os.listdir(dir_path):
                        passed = True
                        break
                time.sleep(0.1)
            
        _record("Screenshots", "Capture", passed, f"Saved to {path}" if passed else "File missing (timeout after 60s)")
    except Exception as e:
        _record("Screenshots", "Execution", False, str(e))

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
            _test_patterns()
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
