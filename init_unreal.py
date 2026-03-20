"""
UEFN TOOLBELT — init_unreal.py
========================================
Copy this file to:  [YourProject]/Content/Python/init_unreal.py

UEFN (and Unreal Engine) automatically executes any file named
exactly "init_unreal.py" inside Content/Python/ every time the
editor starts. No plugins, no menu clicks needed.

This file does three things:
  1. Adds Content/Python/ to sys.path so `import UEFN_Toolbelt` works.
  2. Registers all tool modules (fires all @register_tool decorators).
  3. Injects a "Toolbelt" entry into the editor's top menu bar using
     unreal.ToolMenus so the dashboard is one click away, forever.

After this is in place you never need to open the Output Log again
unless you want to run a tool directly.
"""

import sys
import os
import unreal

# ─────────────────────────────────────────────────────────────────────────────
#  1. Path setup
#     unreal.Paths.project_content_dir() returns the absolute OS path to
#     the project's Content/ folder (with trailing slash).
# ─────────────────────────────────────────────────────────────────────────────

_CONTENT_PYTHON = os.path.join(unreal.Paths.project_content_dir(), "Python")

if _CONTENT_PYTHON not in sys.path:
    sys.path.insert(0, _CONTENT_PYTHON)

# ─────────────────────────────────────────────────────────────────────────────
#  2. Bootstrap — import package and register all tools
# ─────────────────────────────────────────────────────────────────────────────

_toolbelt_loaded = False

try:
    import UEFN_Toolbelt as _tb
    _tb.register_all_tools()
    _toolbelt_loaded = True
    unreal.log("[TOOLBELT] ✓ All tools registered.")
except ModuleNotFoundError:
    unreal.log_warning(
        "[TOOLBELT] Package not found. "
        "Ensure Content/Python/UEFN_Toolbelt/ exists and all files are in place."
    )
except Exception as _e:
    unreal.log_error(f"[TOOLBELT] Startup error: {_e}")

# ─────────────────────────────────────────────────────────────────────────────
#  3. Register top-menu entries via unreal.ToolMenus
#
#  This injects a "Toolbelt ▾" top-level menu next to Help in the UEFN
#  menu bar. Each entry fires an Execute Python Command equivalent.
#
#  The @unreal.ufunction decorator is NOT needed — ToolMenus accepts plain
#  Python strings as commands via set_string_command().
#
#  Note: ToolMenus.get() must be called *after* the editor menu bar is
#  constructed. Using unreal.register_slate_post_tick_callback for the
#  first tick is the correct pattern when running from init_unreal.py.
# ─────────────────────────────────────────────────────────────────────────────

def _build_toolbelt_menu() -> None:
    """
    Called once on the first editor tick so the menu bar is fully built.
    Adds a "Toolbelt" drop-down to the UEFN top menu bar.
    """

    menus = unreal.ToolMenus.get()

    # "MainFrame.MainTabMenu" is the top-level menu bar in UE / UEFN.
    # We add our own named sub-menu entry to it.
    main_menu = menus.extend_menu("MainFrame.MainTabMenu")

    # ── Sub-menu container (the "Toolbelt ▾" drop-down) ──────────────────
    tb_menu_entry = unreal.ToolMenuEntry(
        name="ToolbeltMenu",
        type=unreal.MultiBlockType.MENU_ENTRY,
        insert_position=unreal.ToolMenuInsert("Help", unreal.ToolMenuInsertType.BEFORE),
    )
    tb_menu_entry.set_label(unreal.Text("Toolbelt"))
    tb_menu_entry.set_tool_tip(unreal.Text("UEFN Toolbelt — creator tools"))

    # Register the sub-menu so we can add entries into it
    tb_sub = menus.register_menu(
        "MainFrame.MainTabMenu.Toolbelt",
        "MainFrame.MainTabMenu",
        unreal.MultiBoxType.MENU,
        False,
    )

    # ── Helper: add one clickable entry to the sub-menu ───────────────────
    _sections_added = set()

    def _add_entry(menu, section_name: str, entry_name: str,
                   label: str, tooltip: str, python_cmd: str) -> None:
        if section_name not in _sections_added:
            menu.add_section(section_name, unreal.Text(section_name))
            _sections_added.add(section_name)
        entry = unreal.ToolMenuEntry(
            name=entry_name,
            type=unreal.MultiBlockType.MENU_ENTRY,
            insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT),
        )
        entry.set_label(unreal.Text(label))
        entry.set_tool_tip(unreal.Text(tooltip))
        entry.set_string_command(
            type=unreal.ToolMenuStringCommandType.PYTHON,
            custom_type=unreal.Name(""),
            string=python_cmd,
        )
        menu.add_menu_entry(section_name, entry)

    # ── Section: Dashboard ────────────────────────────────────────────────
    _add_entry(tb_sub, "Dashboard", "ToolbeltOpenQt",
               "Open Dashboard  (PySide6)",
               "Launch the dark-themed PySide6 tabbed dashboard — no Blueprint needed",
               "import UEFN_Toolbelt as tb; tb.launch_qt()")

    _add_entry(tb_sub, "Dashboard", "ToolbeltOpen",
               "Open Dashboard  (Blueprint fallback)",
               "Launch via Editor Utility Widget — requires WBP_ToolbeltDashboard Blueprint",
               "import UEFN_Toolbelt as tb; tb._try_open_widget()")

    _add_entry(tb_sub, "Dashboard", "ToolbeltListTools",
               "List All Tools",
               "Print every registered tool to the Output Log",
               "import UEFN_Toolbelt as tb; [print(f\"  {t['category']:15s} {t['name']}\") for t in tb.registry.list_tools()]")

    # ── Section: Materials ────────────────────────────────────────────────
    for preset in ["chrome", "gold", "neon", "hologram", "lava", "team_red", "team_blue"]:
        _add_entry(tb_sub, "Materials", f"MatPreset_{preset}",
                   f"Material: {preset.replace('_',' ').title()}",
                   f"Apply '{preset}' preset to selected actors",
                   f"import UEFN_Toolbelt as tb; tb.run('material_apply_preset', preset='{preset}')")

    _add_entry(tb_sub, "Materials", "MatRandom",
               "Material: Randomize Colors",
               "Randomize base color on selection",
               "import UEFN_Toolbelt as tb; tb.run('material_randomize_colors')")

    _add_entry(tb_sub, "Materials", "MatGradient",
               "Material: Gradient Painter",
               "Paint Blue→Red gradient across selection on X axis",
               "import UEFN_Toolbelt as tb; tb.run('material_gradient_painter')")

    _add_entry(tb_sub, "Materials", "MatTeamSplit",
               "Material: Team Color Split",
               "Auto Red/Blue split based on world X position",
               "import UEFN_Toolbelt as tb; tb.run('material_team_color_split')")

    # ── Section: Procedural ───────────────────────────────────────────────
    for size in ["small", "medium", "large"]:
        _add_entry(tb_sub, "Procedural", f"Arena_{size}",
                   f"Arena: Generate {size.title()}",
                   f"Spawn a symmetrical {size} Red vs Blue arena",
                   f"import UEFN_Toolbelt as tb; tb.run('arena_generate', size='{size}', apply_team_colors=True)")

    _add_entry(tb_sub, "Procedural", "SplinePlaceProps",
               "Spline: Place Props",
               "Place props along selected spline (20 count, aligned to tangent)",
               "import UEFN_Toolbelt as tb; tb.run('spline_place_props', count=20, align_to_tangent=True)")

    # ── Section: Bulk Ops ─────────────────────────────────────────────────
    for axis in ["X", "Y", "Z"]:
        _add_entry(tb_sub, "BulkOps", f"AlignAxis{axis}",
                   f"Align to {axis}",
                   f"Align all selected actors on {axis} axis",
                   f"import UEFN_Toolbelt as tb; tb.run('bulk_align', axis='{axis}')")

    _add_entry(tb_sub, "BulkOps", "DistributeX",
               "Distribute Evenly (X)",
               "Space selected actors evenly along X",
               "import UEFN_Toolbelt as tb; tb.run('bulk_distribute', axis='X')")

    _add_entry(tb_sub, "BulkOps", "RandomizeRot",
               "Randomize Rotations",
               "Apply random yaw to selected actors",
               "import UEFN_Toolbelt as tb; tb.run('bulk_randomize', rot_range=360.0, randomize_rot=True, randomize_scale=False)")

    _add_entry(tb_sub, "BulkOps", "SnapGrid100",
               "Snap to 100cm Grid",
               "Snap selected actor locations to a 100cm world grid",
               "import UEFN_Toolbelt as tb; tb.run('bulk_snap_to_grid', grid=100.0)")

    _add_entry(tb_sub, "BulkOps", "ResetTransforms",
               "Reset Transforms",
               "Zero rotation and reset scale to 1 on selection",
               "import UEFN_Toolbelt as tb; tb.run('bulk_reset')")

    _add_entry(tb_sub, "BulkOps", "MirrorX",
               "Mirror Selection (X)",
               "Mirror selected actors across X axis",
               "import UEFN_Toolbelt as tb; tb.run('bulk_mirror', axis='X')")

    # ── Section: Verse ────────────────────────────────────────────────────
    _add_entry(tb_sub, "Verse", "VerseListDevices",
               "Verse: List Devices",
               "Print all Verse/Creative devices in the level",
               "import UEFN_Toolbelt as tb; tb.run('verse_list_devices')")

    _add_entry(tb_sub, "Verse", "VerseGenDeclarations",
               "Verse: Generate Device Declarations",
               "Generate @editable Verse declarations from selection",
               "import UEFN_Toolbelt as tb; tb.run('verse_gen_device_declarations')")

    _add_entry(tb_sub, "Verse", "VerseGenSkeleton",
               "Verse: Generate Game Skeleton",
               "Generate a full game manager device skeleton",
               "import UEFN_Toolbelt as tb; tb.run('verse_gen_game_skeleton')")

    _add_entry(tb_sub, "Verse", "VerseExportReport",
               "Verse: Export Device Report",
               "Export JSON report of all device properties",
               "import UEFN_Toolbelt as tb; tb.run('verse_export_report')")

    # ── Section: Text & Signs ─────────────────────────────────────────────
    _add_entry(tb_sub, "Text", "TextPlace",
               "Text: Place Sign",
               "Place a styled 3D text actor at world origin",
               "import UEFN_Toolbelt as tb; tb.run('text_place', text='ZONE', location=(0,0,200), color='#FFDD00')")

    _add_entry(tb_sub, "Text", "TextLabelSelection",
               "Text: Label Selection",
               "Auto-label every selected actor with its own name",
               "import UEFN_Toolbelt as tb; tb.run('text_label_selection', color='#00FFCC', world_size=60.0)")

    _add_entry(tb_sub, "Text", "TextPaintGrid",
               "Text: Paint Zone Grid (4×4)",
               "Place A1–D4 coordinate grid labels across 4×4 map area",
               "import UEFN_Toolbelt as tb; tb.run('text_paint_grid', cols=4, rows=4, cell_size=2000.0)")

    _add_entry(tb_sub, "Text", "TextColorCycle",
               "Text: Color Cycle Banner",
               "Place a row of team/color labels cycling through the palette",
               "import UEFN_Toolbelt as tb; tb.run('text_color_cycle')")

    _add_entry(tb_sub, "Text", "TextListStyles",
               "Text: List Saved Styles",
               "Print all saved text style presets",
               "import UEFN_Toolbelt as tb; tb.run('text_list_styles')")

    _add_entry(tb_sub, "Text", "TextClear",
               "Text: Clear All Text Actors",
               "Delete all Toolbelt text actors from the level (undoable)",
               "import UEFN_Toolbelt as tb; tb.run('text_clear_folder')")

    # ── Section: Project ──────────────────────────────────────────────────
    _add_entry(tb_sub, "Project", "ScaffoldStandard",
               "Project: Init Standard Structure",
               "Generate full UEFN standard folder structure under /Game/MyProject",
               "import UEFN_Toolbelt as tb; tb.run('scaffold_generate', template='uefn_standard', project_name='MyProject')")

    _add_entry(tb_sub, "Project", "ScaffoldCompetitive",
               "Project: Init Competitive Map",
               "Generate a streamlined arena/competitive map folder structure",
               "import UEFN_Toolbelt as tb; tb.run('scaffold_generate', template='competitive_map', project_name='MyArena')")

    _add_entry(tb_sub, "Project", "ScaffoldSolo",
               "Project: Init Solo Dev",
               "Generate a minimal fast-start folder structure for solo creators",
               "import UEFN_Toolbelt as tb; tb.run('scaffold_generate', template='solo_dev', project_name='MyProject')")

    _add_entry(tb_sub, "Project", "ScaffoldVerseHeavy",
               "Project: Init Verse-Heavy",
               "Generate a deep Verse module folder structure",
               "import UEFN_Toolbelt as tb; tb.run('scaffold_generate', template='verse_heavy', project_name='MyProject')")

    _add_entry(tb_sub, "Project", "ScaffoldPreview",
               "Project: Preview Structure",
               "Preview scaffold without making changes (dry run)",
               "import UEFN_Toolbelt as tb; tb.run('scaffold_preview', template='uefn_standard', project_name='MyProject')")

    _add_entry(tb_sub, "Project", "ScaffoldListTemplates",
               "Project: List Templates",
               "Print all available scaffold templates",
               "import UEFN_Toolbelt as tb; tb.run('scaffold_list_templates')")

    _add_entry(tb_sub, "Project", "ScaffoldOrganizeLoose",
               "Project: Organize Loose Assets",
               "Preview moving loose /Game root assets into project structure (dry run)",
               "import UEFN_Toolbelt as tb; tb.run('scaffold_organize_loose', project_name='MyProject', dry_run=True)")

    # ── Section: Optimization ─────────────────────────────────────────────
    _add_entry(tb_sub, "Optimization", "MemScanAll",
               "Memory: Full Scan",
               "Scan all assets for memory/performance issues",
               "import UEFN_Toolbelt as tb; tb.run('memory_scan')")

    _add_entry(tb_sub, "Optimization", "MemScanTextures",
               "Memory: Scan Textures",
               "Find oversized textures (>2K warning, >4K critical)",
               "import UEFN_Toolbelt as tb; tb.run('memory_scan_textures')")

    _add_entry(tb_sub, "Optimization", "MemScanMeshes",
               "Memory: Scan Meshes",
               "Find high-polycount meshes missing LODs",
               "import UEFN_Toolbelt as tb; tb.run('memory_scan_meshes')")

    _add_entry(tb_sub, "Optimization", "MemTopOffenders",
               "Memory: Top 20 Offenders",
               "Print the 20 heaviest assets ranked by estimated VRAM / tri count",
               "import UEFN_Toolbelt as tb; tb.run('memory_top_offenders', limit=20)")

    _add_entry(tb_sub, "Optimization", "MemAutofixLODs",
               "Memory: Auto-Fix LODs (/Game)",
               "Generate LODs for every StaticMesh in /Game that is missing them",
               "import UEFN_Toolbelt as tb; tb.run('memory_autofix_lods', scan_path='/Game')")

    # ── Section: Assets ───────────────────────────────────────────────────
    _add_entry(tb_sub, "Assets", "RenameDryRun",
               "Assets: Naming Audit (Dry Run)",
               "Preview Epic naming convention violations — no changes made",
               "import UEFN_Toolbelt as tb; tb.run('rename_dry_run', scan_path='/Game')")

    _add_entry(tb_sub, "Assets", "RenameEnforce",
               "Assets: Enforce Naming Conventions",
               "Rename all violating assets to follow Epic convention",
               "import UEFN_Toolbelt as tb; tb.run('rename_enforce_conventions', scan_path='/Game')")

    _add_entry(tb_sub, "Assets", "RenameReport",
               "Assets: Full Naming Report",
               "Export full naming audit JSON without making changes",
               "import UEFN_Toolbelt as tb; tb.run('rename_report', scan_path='/Game')")

    # ── Section: Prop Patterns ────────────────────────────────────────────
    for pattern, label, tip in [
        ("grid",         "Grid (5×5)",        "Spawn a mesh in a precise N×M rectangular grid"),
        ("circle",       "Circle Ring",        "Evenly-spaced ring of props at a fixed radius"),
        ("arc",          "Arc (180°)",         "Props along a partial arc between two angles"),
        ("spiral",       "Spiral",             "Archimedean spiral — radius grows with angle"),
        ("line",         "Line",               "Evenly spaced props between two world points"),
        ("wave",         "Sine Wave",          "Props along a sine-wave path"),
        ("helix",        "Helix (3D Screw)",   "3D corkscrew / spiral staircase layout"),
        ("radial_rows",  "Radial Rings",       "Concentric rings — dartboard / arena layout"),
    ]:
        _add_entry(
            tb_sub, "PropPatterns", f"Pattern_{pattern}",
            f"Pattern: {label}", tip,
            f"import UEFN_Toolbelt as tb; tb.run('pattern_{pattern}', preview=True)",
        )

    _add_entry(tb_sub, "PropPatterns", "PatternClearPreview",
               "Pattern: Clear Preview",
               "Remove sphere preview markers spawned by pattern tools",
               "import UEFN_Toolbelt as tb; tb.run('pattern_clear', preview_only=True)")

    _add_entry(tb_sub, "PropPatterns", "PatternClearAll",
               "Pattern: Clear All Pattern Actors",
               "Remove all actors spawned by pattern tools (undoable)",
               "import UEFN_Toolbelt as tb; tb.run('pattern_clear', preview_only=False)")

    # ── Section: Reference Auditor ────────────────────────────────────────
    _add_entry(tb_sub, "RefAuditor", "RefFullReport",
               "Refs: Full Audit Report",
               "Run all reference scans and export JSON health report",
               "import UEFN_Toolbelt as tb; tb.run('ref_full_report', scan_path='/Game')")

    _add_entry(tb_sub, "RefAuditor", "RefOrphans",
               "Refs: Find Orphaned Assets",
               "Find assets with no referencers — safe deletion candidates",
               "import UEFN_Toolbelt as tb; tb.run('ref_audit_orphans', scan_path='/Game')")

    _add_entry(tb_sub, "RefAuditor", "RefRedirectors",
               "Refs: Find Redirectors",
               "Find stale ObjectRedirector assets (move/rename artifacts)",
               "import UEFN_Toolbelt as tb; tb.run('ref_audit_redirectors', scan_path='/Game')")

    _add_entry(tb_sub, "RefAuditor", "RefDuplicates",
               "Refs: Find Duplicate Names",
               "Find assets sharing the same base name in different folders",
               "import UEFN_Toolbelt as tb; tb.run('ref_audit_duplicates', scan_path='/Game')")

    _add_entry(tb_sub, "RefAuditor", "RefFixRedirectors",
               "Refs: Fix Redirectors (Dry Run)",
               "Preview redirector consolidation — no changes made",
               "import UEFN_Toolbelt as tb; tb.run('ref_fix_redirectors', scan_path='/Game', dry_run=True)")

    # ── Section: Level Snapshot ───────────────────────────────────────────
    _add_entry(tb_sub, "Snapshot", "SnapSave",
               "Snapshot: Save Level",
               "Save a timestamped JSON snapshot of all actor transforms",
               "import UEFN_Toolbelt as tb; tb.run('snapshot_save')")

    _add_entry(tb_sub, "Snapshot", "SnapSaveSelection",
               "Snapshot: Save Selection",
               "Save transforms of currently selected actors only",
               "import UEFN_Toolbelt as tb; tb.run('snapshot_save', scope='selection')")

    _add_entry(tb_sub, "Snapshot", "SnapList",
               "Snapshot: List Saved",
               "Print all saved snapshots with actor count and timestamp",
               "import UEFN_Toolbelt as tb; tb.run('snapshot_list')")

    _add_entry(tb_sub, "Snapshot", "SnapCompareLive",
               "Snapshot: What Changed?",
               "Compare the most recent snapshot against the current live level",
               "import UEFN_Toolbelt as tb; tb.run('snapshot_list'); unreal.log('Run snapshot_compare_live with a name from the list above')")

    # ── Section: Asset Tagger ─────────────────────────────────────────────
    _add_entry(tb_sub, "AssetTagger", "TagShow",
               "Tags: Show Tags on Selection",
               "Print all Toolbelt metadata tags on selected Content Browser assets",
               "import UEFN_Toolbelt as tb; tb.run('tag_show')")

    _add_entry(tb_sub, "AssetTagger", "TagListAll",
               "Tags: List All Tags (/Game)",
               "List every unique tag key used under /Game with asset counts",
               "import UEFN_Toolbelt as tb; tb.run('tag_list_all', folder='/Game')")

    _add_entry(tb_sub, "AssetTagger", "TagExport",
               "Tags: Export Tag Index (JSON)",
               "Export the full tag → asset mapping to Saved/UEFN_Toolbelt/tag_export.json",
               "import UEFN_Toolbelt as tb; tb.run('tag_export', folder='/Game')")

    # ── Section: Screenshot ───────────────────────────────────────────────
    _add_entry(tb_sub, "Screenshot", "ShotViewport",
               "Screenshot: Viewport (1080p)",
               "Capture the editor viewport at 1920×1080 to Saved/UEFN_Toolbelt/screenshots/",
               "import UEFN_Toolbelt as tb; tb.run('screenshot_take', width=1920, height=1080)")

    _add_entry(tb_sub, "Screenshot", "Shot4K",
               "Screenshot: Viewport (4K)",
               "Capture the editor viewport at 3840×2160",
               "import UEFN_Toolbelt as tb; tb.run('screenshot_take', width=3840, height=2160, name='4k')")

    _add_entry(tb_sub, "Screenshot", "ShotSelection",
               "Screenshot: Frame Selection",
               "Auto-frame selected actors and capture a screenshot, then restore camera",
               "import UEFN_Toolbelt as tb; tb.run('screenshot_focus_selection')")

    _add_entry(tb_sub, "Screenshot", "ShotFolder",
               "Screenshot: Open Output Folder",
               "Print the screenshot output folder path to the Output Log",
               "import UEFN_Toolbelt as tb; tb.run('screenshot_open_folder')")

    # ── Section: MCP Bridge ───────────────────────────────────────────────
    _add_entry(tb_sub, "MCPBridge", "MCPStart",
               "MCP: Start Listener",
               "Start the HTTP listener so Claude Code can control UEFN directly",
               "import UEFN_Toolbelt as tb; tb.run('mcp_start')")

    _add_entry(tb_sub, "MCPBridge", "MCPStop",
               "MCP: Stop Listener",
               "Stop the MCP HTTP listener",
               "import UEFN_Toolbelt as tb; tb.run('mcp_stop')")

    _add_entry(tb_sub, "MCPBridge", "MCPStatus",
               "MCP: Status",
               "Print listener port, running state and available command count",
               "import UEFN_Toolbelt as tb; tb.run('mcp_status')")

    _add_entry(tb_sub, "MCPBridge", "MCPRestart",
               "MCP: Restart Listener",
               "Restart the listener — use after hot-reloading the toolbelt",
               "import UEFN_Toolbelt as tb; tb.run('mcp_restart')")

    # ── Section: API Explorer ─────────────────────────────────────────────
    _add_entry(tb_sub, "APIExplorer", "APISearch",
               "API: Search",
               "Fuzzy-search class/function names across the live unreal module",
               "import UEFN_Toolbelt as tb; tb.run('api_search', query='', category='all')")

    _add_entry(tb_sub, "APIExplorer", "APIListSubsystems",
               "API: List Subsystems",
               "Print every *Subsystem class available in this UEFN build",
               "import UEFN_Toolbelt as tb; tb.run('api_list_subsystems')")

    _add_entry(tb_sub, "APIExplorer", "APIExportStubs",
               "API: Export Full Stubs (.pyi)",
               "Generate unreal.pyi for full IDE autocomplete — no more red squiggles",
               "import UEFN_Toolbelt as tb; tb.run('api_export_full')")

    _add_entry(tb_sub, "APIExplorer", "APIInspect",
               "API: Inspect Class (EditorActorSubsystem)",
               "Print full signature and docs for EditorActorSubsystem",
               "import UEFN_Toolbelt as tb; tb.run('api_inspect', name='EditorActorSubsystem')")

    # ── Refresh so changes appear immediately ─────────────────────────────
    menus.refresh_all_widgets()
    unreal.log("[TOOLBELT] ✓ Menu registered — look for 'Toolbelt' in the top menu bar.")


# ─────────────────────────────────────────────────────────────────────────────
#  Deferred menu registration
#
#  init_unreal.py runs before the editor's Slate UI is fully built, so we
#  cannot call ToolMenus.get() directly here — the menu bar doesn't exist yet.
#
#  The correct pattern is to register a one-shot post-tick callback.
#  On the very first editor tick the callback fires, builds the menu, then
#  immediately unregisters itself so it never runs again.
# ─────────────────────────────────────────────────────────────────────────────

if _toolbelt_loaded:
    _menu_registered = False

    def _on_tick(delta_time: float) -> None:
        global _menu_registered
        if _menu_registered:
            return
        _menu_registered = True
        try:
            _build_toolbelt_menu()
        except Exception as _menu_err:
            unreal.log_warning(f"[TOOLBELT] Menu registration failed: {_menu_err}")
        finally:
            # Unregister this callback — it only needs to run once
            unreal.unregister_slate_pre_tick_callback(_tick_handle)

    _tick_handle = unreal.register_slate_pre_tick_callback(_on_tick)
