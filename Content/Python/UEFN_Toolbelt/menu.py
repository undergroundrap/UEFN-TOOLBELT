"""
UEFN Toolbelt — menu.py
Builds the "Toolbelt ▾" top-menu entry in the UEFN editor bar.

Called from __init__.register() via a deferred Slate tick callback.
Kept in its own module so init_unreal.py can stay a generic loader.
"""

import unreal


def build_toolbelt_menu() -> None:
    """
    Injects a 'Toolbelt' drop-down into MainFrame.MainTabMenu (next to Help).
    Must be called after the editor's Slate UI is fully constructed —
    use _schedule_menu() in __init__.py to defer to the first editor tick.
    """
    menus = unreal.ToolMenus.get()
    menus.extend_menu("MainFrame.MainTabMenu")

    tb_sub = menus.register_menu(
        "MainFrame.MainTabMenu.Toolbelt",
        "MainFrame.MainTabMenu",
        unreal.MultiBoxType.MENU,
        False,
    )

    _sections_added: set = set()

    def _entry(section: str, name: str, label: str, tooltip: str, cmd: str) -> None:
        if section not in _sections_added:
            tb_sub.add_section(section, unreal.Text(section))
            _sections_added.add(section)
        e = unreal.ToolMenuEntry(
            name=name,
            type=unreal.MultiBlockType.MENU_ENTRY,
            insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT),
        )
        e.set_label(unreal.Text(label))
        e.set_tool_tip(unreal.Text(tooltip))
        e.set_string_command(
            type=unreal.ToolMenuStringCommandType.PYTHON,
            custom_type=unreal.Name(""),
            string=cmd,
        )
        tb_sub.add_menu_entry(section, e)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    _entry("Dashboard", "ToolbeltOpenQt",
           "Open Dashboard  (PySide6)",
           "Launch the dark-themed PySide6 tabbed dashboard",
           "import UEFN_Toolbelt as tb; tb.launch_qt()")

    _entry("Dashboard", "ToolbeltOpen",
           "Open Dashboard  (Blueprint fallback)",
           "Launch via Editor Utility Widget",
           "import UEFN_Toolbelt as tb; tb._try_open_widget()")

    _entry("Dashboard", "ToolbeltListTools",
           "List All Tools",
           "Print every registered tool to the Output Log",
           "import UEFN_Toolbelt as tb; [print(f\"  {t['category']:15s} {t['name']}\") for t in tb.registry.list_tools()]")

    _entry("Dashboard", "ToolbeltRunIntegration",
           "Run Integration Test [WARNING: INVASIVE]",
           "Full check of tools. Spawns/Deletes actors. RUN IN TEST TEMPLATE ONLY.",
           "import UEFN_Toolbelt as tb; tb.run('toolbelt_integration_test')")

    # ── Materials ─────────────────────────────────────────────────────────────
    for preset in ["chrome", "gold", "neon", "hologram", "lava", "team_red", "team_blue"]:
        _entry("Materials", f"MatPreset_{preset}",
               f"Material: {preset.replace('_', ' ').title()}",
               f"Apply '{preset}' preset to selected actors",
               f"import UEFN_Toolbelt as tb; tb.run('material_apply_preset', preset='{preset}')")

    _entry("Materials", "MatRandom",
           "Material: Randomize Colors",
           "Randomize base color on selection",
           "import UEFN_Toolbelt as tb; tb.run('material_randomize_colors')")

    _entry("Materials", "MatGradient",
           "Material: Gradient Painter",
           "Paint Blue→Red gradient across selection on X axis",
           "import UEFN_Toolbelt as tb; tb.run('material_gradient_painter')")

    _entry("Materials", "MatTeamSplit",
           "Material: Team Color Split",
           "Auto Red/Blue split based on world X position",
           "import UEFN_Toolbelt as tb; tb.run('material_team_color_split')")

    # ── Procedural ────────────────────────────────────────────────────────────
    for size in ["small", "medium", "large"]:
        _entry("Procedural", f"Arena_{size}",
               f"Arena: Generate {size.title()}",
               f"Spawn a symmetrical {size} Red vs Blue arena",
               f"import UEFN_Toolbelt as tb; tb.run('arena_generate', size='{size}', apply_team_colors=True)")

    _entry("Procedural", "SplinePlaceProps",
           "Spline: Place Props",
           "Place props along selected spline (20 count, aligned to tangent)",
           "import UEFN_Toolbelt as tb; tb.run('spline_place_props', count=20, align_to_tangent=True)")

    # ── Bulk Ops ──────────────────────────────────────────────────────────────
    for axis in ["X", "Y", "Z"]:
        _entry("BulkOps", f"AlignAxis{axis}",
               f"Align to {axis}",
               f"Align all selected actors on {axis} axis",
               f"import UEFN_Toolbelt as tb; tb.run('bulk_align', axis='{axis}')")

    _entry("BulkOps", "DistributeX",
           "Distribute Evenly (X)",
           "Space selected actors evenly along X",
           "import UEFN_Toolbelt as tb; tb.run('bulk_distribute', axis='X')")

    _entry("BulkOps", "RandomizeRot",
           "Randomize Rotations",
           "Apply random yaw to selected actors",
           "import UEFN_Toolbelt as tb; tb.run('bulk_randomize', rot_range=360.0, randomize_rot=True, randomize_scale=False)")

    _entry("BulkOps", "SnapGrid100",
           "Snap to 100cm Grid",
           "Snap selected actor locations to a 100cm world grid",
           "import UEFN_Toolbelt as tb; tb.run('bulk_snap_to_grid', grid=100.0)")

    _entry("BulkOps", "ResetTransforms",
           "Reset Transforms",
           "Zero rotation and reset scale to 1 on selection",
           "import UEFN_Toolbelt as tb; tb.run('bulk_reset')")

    _entry("BulkOps", "MirrorX",
           "Mirror Selection (X)",
           "Mirror selected actors across X axis",
           "import UEFN_Toolbelt as tb; tb.run('bulk_mirror', axis='X')")

    # ── Verse ─────────────────────────────────────────────────────────────────
    _entry("Verse", "VerseListDevices",
           "Verse: List Devices",
           "Print all Verse/Creative devices in the level",
           "import UEFN_Toolbelt as tb; tb.run('verse_list_devices')")

    _entry("Verse", "VerseGenDeclarations",
           "Verse: Generate Device Declarations",
           "Generate @editable Verse declarations from selection",
           "import UEFN_Toolbelt as tb; tb.run('verse_gen_device_declarations')")

    _entry("Verse", "VerseGenSkeleton",
           "Verse: Generate Game Skeleton",
           "Generate a full game manager device skeleton",
           "import UEFN_Toolbelt as tb; tb.run('verse_gen_game_skeleton')")

    _entry("Verse", "VerseExportReport",
           "Verse: Export Device Report",
           "Export JSON report of all device properties",
           "import UEFN_Toolbelt as tb; tb.run('verse_export_report')")

    # ── Text & Signs ──────────────────────────────────────────────────────────
    _entry("Text", "TextPlace",
           "Text: Place Sign",
           "Place a styled 3D text actor at world origin",
           "import UEFN_Toolbelt as tb; tb.run('text_place', text='ZONE', location=(0,0,200), color='#FFDD00')")

    _entry("Text", "TextLabelSelection",
           "Text: Label Selection",
           "Auto-label every selected actor with its own name",
           "import UEFN_Toolbelt as tb; tb.run('text_label_selection', color='#00FFCC', world_size=60.0)")

    _entry("Text", "TextPaintGrid",
           "Text: Paint Zone Grid (4×4)",
           "Place A1–D4 coordinate grid labels across 4×4 map area",
           "import UEFN_Toolbelt as tb; tb.run('text_paint_grid', cols=4, rows=4, cell_size=2000.0)")

    _entry("Text", "TextColorCycle",
           "Text: Color Cycle Banner",
           "Place a row of team/color labels",
           "import UEFN_Toolbelt as tb; tb.run('text_color_cycle')")

    _entry("Text", "TextClear",
           "Text: Clear All Text Actors",
           "Delete all Toolbelt text actors from the level (undoable)",
           "import UEFN_Toolbelt as tb; tb.run('text_clear_folder')")

    # ── Prop Patterns ─────────────────────────────────────────────────────────
    for pattern, label, tip in [
        ("grid",        "Grid (5×5)",       "Spawn a mesh in a precise N×M rectangular grid"),
        ("circle",      "Circle Ring",      "Evenly-spaced ring of props at a fixed radius"),
        ("arc",         "Arc (180°)",       "Props along a partial arc between two angles"),
        ("spiral",      "Spiral",           "Archimedean spiral — radius grows with angle"),
        ("line",        "Line",             "Evenly spaced props between two world points"),
        ("wave",        "Sine Wave",        "Props along a sine-wave path"),
        ("helix",       "Helix (3D)",       "3D corkscrew / spiral staircase layout"),
        ("radial_rows", "Radial Rings",     "Concentric rings — dartboard / arena layout"),
    ]:
        _entry("PropPatterns", f"Pattern_{pattern}",
               f"Pattern: {label}", tip,
               f"import UEFN_Toolbelt as tb; tb.run('pattern_{pattern}', preview=True)")

    _entry("PropPatterns", "PatternClearPreview",
           "Pattern: Clear Preview",
           "Remove sphere preview markers spawned by pattern tools",
           "import UEFN_Toolbelt as tb; tb.run('pattern_clear', preview_only=True)")

    _entry("PropPatterns", "PatternClearAll",
           "Pattern: Clear All Pattern Actors",
           "Remove all actors spawned by pattern tools (undoable)",
           "import UEFN_Toolbelt as tb; tb.run('pattern_clear', preview_only=False)")

    # ── Project Scaffold ──────────────────────────────────────────────────────
    for tmpl, label in [
        ("uefn_standard",  "Standard"),
        ("competitive_map", "Competitive Map"),
        ("solo_dev",       "Solo Dev"),
        ("verse_heavy",    "Verse-Heavy"),
    ]:
        _entry("Project", f"Scaffold_{tmpl}",
               f"Project: Init {label}",
               f"Generate {label} folder structure",
               f"import UEFN_Toolbelt as tb; tb.run('scaffold_generate', template='{tmpl}', project_name='MyProject')")

    _entry("Project", "ScaffoldPreview",
           "Project: Preview Structure",
           "Preview scaffold without making changes (dry run)",
           "import UEFN_Toolbelt as tb; tb.run('scaffold_preview', template='uefn_standard', project_name='MyProject')")

    # ── Reference Auditor ─────────────────────────────────────────────────────
    _entry("RefAuditor", "RefFullReport",
           "Refs: Full Audit Report",
           "Run all reference scans and export JSON health report",
           "import UEFN_Toolbelt as tb; tb.run('ref_full_report', scan_path='/Game')")

    _entry("RefAuditor", "RefOrphans",
           "Refs: Find Orphaned Assets",
           "Find assets with no referencers — safe deletion candidates",
           "import UEFN_Toolbelt as tb; tb.run('ref_audit_orphans', scan_path='/Game')")

    _entry("RefAuditor", "RefFixRedirectors",
           "Refs: Fix Redirectors (Dry Run)",
           "Preview redirector consolidation — no changes made",
           "import UEFN_Toolbelt as tb; tb.run('ref_fix_redirectors', scan_path='/Game', dry_run=True)")

    # ── Optimization ──────────────────────────────────────────────────────────
    _entry("Optimization", "MemScanAll",
           "Memory: Full Scan",
           "Scan all assets for memory/performance issues",
           "import UEFN_Toolbelt as tb; tb.run('memory_scan')")

    _entry("Optimization", "MemTopOffenders",
           "Memory: Top 20 Offenders",
           "Print the 20 heaviest assets ranked by estimated VRAM / tri count",
           "import UEFN_Toolbelt as tb; tb.run('memory_top_offenders', limit=20)")

    _entry("Optimization", "MemAutofixLODs",
           "Memory: Auto-Fix LODs (/Game)",
           "Generate LODs for every StaticMesh in /Game that is missing them",
           "import UEFN_Toolbelt as tb; tb.run('memory_autofix_lods', scan_path='/Game')")

    # ── Level Snapshot ────────────────────────────────────────────────────────
    _entry("Snapshot", "SnapSave",
           "Snapshot: Save Level",
           "Save a timestamped JSON snapshot of all actor transforms",
           "import UEFN_Toolbelt as tb; tb.run('snapshot_save')")

    _entry("Snapshot", "SnapList",
           "Snapshot: List Saved",
           "Print all saved snapshots with actor count and timestamp",
           "import UEFN_Toolbelt as tb; tb.run('snapshot_list')")

    # ── Asset Tagger ──────────────────────────────────────────────────────────
    _entry("AssetTagger", "TagShow",
           "Tags: Show Tags on Selection",
           "Print all Toolbelt metadata tags on selected Content Browser assets",
           "import UEFN_Toolbelt as tb; tb.run('tag_show')")

    _entry("AssetTagger", "TagListAll",
           "Tags: List All Tags (/Game)",
           "List every unique tag key used under /Game with asset counts",
           "import UEFN_Toolbelt as tb; tb.run('tag_list_all', folder='/Game')")

    # ── Screenshot ────────────────────────────────────────────────────────────
    _entry("Screenshot", "ShotViewport",
           "Screenshot: Viewport (1080p)",
           "Capture the editor viewport at 1920×1080",
           "import UEFN_Toolbelt as tb; tb.run('screenshot_take', width=1920, height=1080)")

    _entry("Screenshot", "Shot4K",
           "Screenshot: Viewport (4K)",
           "Capture the editor viewport at 3840×2160",
           "import UEFN_Toolbelt as tb; tb.run('screenshot_take', width=3840, height=2160, name='4k')")

    _entry("Screenshot", "ShotSelection",
           "Screenshot: Frame Selection",
           "Auto-frame selected actors and capture a screenshot",
           "import UEFN_Toolbelt as tb; tb.run('screenshot_focus_selection')")

    # ── MCP Bridge ────────────────────────────────────────────────────────────
    _entry("MCPBridge", "MCPStart",
           "MCP: Start Listener",
           "Start the HTTP listener so any MCP-compatible AI can control UEFN directly",
           "import UEFN_Toolbelt as tb; tb.run('mcp_start')")

    _entry("MCPBridge", "MCPStop",
           "MCP: Stop Listener",
           "Stop the MCP HTTP listener",
           "import UEFN_Toolbelt as tb; tb.run('mcp_stop')")

    _entry("MCPBridge", "MCPStatus",
           "MCP: Status",
           "Print listener port, running state and command count",
           "import UEFN_Toolbelt as tb; tb.run('mcp_status')")

    _entry("MCPBridge", "MCPRestart",
           "MCP: Restart Listener",
           "Restart the listener — use after hot-reloading the toolbelt",
           "import UEFN_Toolbelt as tb; tb.run('mcp_restart')")

    # ── API Explorer ──────────────────────────────────────────────────────────
    _entry("APIExplorer", "APIListSubsystems",
           "API: List Subsystems",
           "Print every *Subsystem class available in this UEFN build",
           "import UEFN_Toolbelt as tb; tb.run('api_list_subsystems')")

    _entry("APIExplorer", "APIExportStubs",
           "API: Export Full Stubs (.pyi)",
           "Generate unreal.pyi for full IDE autocomplete",
           "import UEFN_Toolbelt as tb; tb.run('api_export_full')")

    _entry("APIExplorer", "APICrawlLevel",
           "API: Crawl Level Classes (JSON)",
           "Headless dump of exposed properties for every unique class in the current map",
           "import UEFN_Toolbelt as tb; tb.run('api_crawl_level_classes')")

    menus.refresh_all_widgets()
    unreal.log("[TOOLBELT] ✓ Menu registered — look for 'Toolbelt' in the top menu bar.")
