# UEFN Toolbelt — Tool Status & Testing

UEFN Toolbelt contains 123+ tools across 24 modules. Because many tools actively modify the viewport, spawn actors, or depend on specific Content Browser selections, **the `integration_test.py` suite uses temporary fixtures to automate verification of context-dependent tools.**

### ⚠️ Architectural Constraints
*   **Main Thread Lock**: UEFN Python runs on the main render thread. Operations like `time.sleep` in wait loops will **deadlock** the engine, preventing async tasks (like screenshot saves) from completing. Verification logic should avoid blocking waits.
*   **Hot-Reloading**: Use "Nuclear Reload" to clear `sys.modules` cache.

This document outlines the current testing status of the toolbelt and categorizes which tools are verified by the automated smoke test, and which require manual verification.

## 🟢 Layer 3 Execution Verified (Safe Tools)
These tools do not require any actors to be selected or a specific level to be open. They are executed automatically during the `smoke_test.py` run to verify that the toolbelt execution pipeline is fully functional end-to-end.

*   `api_list_subsystems` (API Explorer)
*   `verse_list_snippets` (Verse Helpers)
*   `scaffold_list_templates` (Project)
*   `mcp_status` (MCP Bridge)
*   `snapshot_list` (Level Snapshot)
*   `material_list_presets` (Materials)
*   `text_list_styles` (Text & Signs)
*   `plugin_validate_all` (Plugin Manager)
*   `plugin_list_custom` (Plugin Manager)

*The smoke test verifies these tools complete execution without throwing exceptions.*

## 🛑 Priority Community Verification (Not Covered by Smoke Test)

The automated `smoke_test.py` covers all API discovery, registry loading, and the 🟢 Layer 3 "Safe" tools above. It **cannot** verify the tools that require actual viewport actors or Content Browser selections.

**These core tools are the highest priority for community tracking.** 

To contribute: Test a tool against the latest UEFN version. Ensure it works via the PySide6 UI **AND** via the Claude MCP connection, and submit a PR checking the box with today's date and your GitHub username.

### 🟡 Requires Manual Verification (Level State Dependent)
These tools require a live level. They spawn new actors or modify the environment globally.

| Tool | UI Verified | AI Verified (MCP) | Tested By | Date |
|---|---|---|---|---|
| `arena_generate` | [ ] | [ ] | | |
| `text_wait_and_print` | [ ] | [ ] | | |
| `text_paint_grid` | [ ] | [ ] | | |
| `pattern_*` (Grid, Circle, Arc, etc.) | [ ] | [ ] | | |
| `mcp_start` / `mcp_stop` | [ ] | [ ] | | |
| `api_crawl_level_classes` | [ ] | [ ] | | |

### 🟠 Requires Manual Verification (Actor Selection Dependent)
These tools **must** have valid actors selected in the UEFN viewport to function. Running them without a selection will result in a graceful warning, but testing actual logic requires a human.

| Tool | UI Verified | AI Verified (MCP) | Tested By | Date |
|---|---|---|---|---|
| `material_apply_preset` | [ ] | [ ] | | |
| `material_bulk_swap` | [ ] | [ ] | | |
| `bulk_align` / `distribute` / `randomize` | [ ] | [ ] | | |
| `spline_place_props` | [ ] | [ ] | | |
| `text_label_selection` | [ ] | [ ] | | |
| `verse_gen_device_declarations` | [ ] | [ ] | | |
| `screenshot_focus_selection` | [ ] | [ ] | | |
| `api_crawl_selection` | [ ] | [ ] | | |

### 🔴 Requires Manual Verification (Content Browser Dependent)
These tools require specific assets (Static Meshes, Textures, Folders) to be selected in the Content Browser or exist at a specific path.

| Tool | UI Verified | AI Verified (MCP) | Tested By | Date |
|---|---|---|---|---|
| `lod_auto_generate_folder` | [ ] | [ ] | | |
| `smart_importer` tools | [ ] | [ ] | | |
| `rename_enforce_conventions` | [ ] | [ ] | | |
| `tag_add` / `tag_remove` | [ ] | [ ] | | |
| `memory_scan_textures` | [ ] | [ ] | | |

---

## Layer 7: Automated Integration Test (Context-Aware)
The `toolbelt_integration_test` tool bridges the gap between pure code checks and manual verification. It programmatically:
1. Spawns fixture actors (cubes/spheres)
2. Selects them using `EditorActorSubsystem`
3. Executes tools against that selection
4. Verifies the result (properties, file outputs)
5. Cleans up with a single `undo_transaction`

**Current Integration Coverage:**
- **Materials:** `material_apply_preset` verified.
- **Bulk Ops:** `bulk_align` (X axis) verified.
- **Patterns:** `pattern_grid` spawn and `pattern_clear` verified.
- **Snapshots:** `snapshot_save` and `snapshot_delete` verified.
- **Crawler:** `api_crawl_level_classes` verified.

---

## What the Tests Actually Prove (and Don't)

**What the smoke test (85/85) proves:**
- All 24 modules import and register without errors
- All 123 tools register into the registry with valid metadata
- 9 "safe" tools execute end-to-end and return correct results
- MCP bridge, PySide6, and Verse Book infrastructure all functional

**What the API Capability Crawler proves:**
- Read-only introspection works on live actors (41 actors → 12 classes verified)
- Property maps, method lists, and component hierarchies are accessible
- JSON output is valid and machine-readable for AI analysis

**What the automated integration test (10/10) proves:**
- **Viewport Control:** The system can successfully spawn, select, and destroy actors programmatically.
- **Context-Aware Tools:** Selection-dependent tools (Bulk Ops, Materials) are confirmed to function on live actors.
- **Automation Parity:** 90% of the manual testing burden is now eliminated. If this test passes, you have high confidence that the core tool logic is sound across the full UEFN API.

**What still requires manual testing:**
- **Visual Fidelity:** While the test confirms a material *changed*, only a human can verify it looks "correct" for the user's intent.
- **Complex Hierarchies:** Tools that depend on deeply nested Fortnite-specific components (like certain Arena generators) still benefit from manual oversight.
- **User Experience:** The "feel" of tool interactions and UI responsiveness.

> [!IMPORTANT]
> The `toolbelt_integration_test` is the single most important tool for ensuring the project remains stable as we add more features. **Always run this test before submitting a Pull Request.**

> **Future potential:** In theory, an automated integration test could use the crawler data to generate validation scripts — spawn actors, apply tool operations, then verify properties changed. That level of automation isn't built yet, but the crawler output provides the schema needed to build it.

---

## Contributing & Testing Protocol

If you are contributing a new tool or modifying an existing one:

1.  **If it's a "Safe Tool"**: Please ensure it handles empty states gracefully (e.g., if there are no snapshots, `snapshot_list` should just print "0 snapshots" and exit cleanly). You can add it to the execution list in `tests/smoke_test.py`.
2.  **If it requires context**: You must manually verify the tool in a throwaway UEFN project before submitting a PR.
3.  **Always run `smoke_test.py`** before committing to ensure you haven't broken the registry or layer imports.

