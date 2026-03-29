"""
UEFN TOOLBELT — dashboard_pyside6.py
=========================================
PySide6 tabbed floating dashboard — the real deal, no Blueprint required.

Why PySide6 instead of the Blueprint widget (EUW) approach?
  - Works immediately on first launch, zero Blueprint setup
  - Full dark theme via QSS — pixel-perfect #181818 / #212121
  - Real Qt widgets: spinboxes, comboboxes, inline inputs per button
  - Built entirely as a standalone Python editor script, zero plugins required.
  - Battle-tested by early adopters and the UEFN Python
    creator community since the experimental drop (March 2026)

Install PySide6 (one-time, outside UEFN):
  Open a regular terminal and run:
    & "<UE_INSTALL>\\Engine\\Binaries\\ThirdParty\\Python3\\Win64\\python.exe" -m pip install PySide6

  Typical path:
    C:\\Program Files\\Epic Games\\Fortnite\\Engine\\Binaries\\ThirdParty\\Python3\\Win64\\python.exe

Launch:
  import UEFN_Toolbelt as tb; tb.launch_qt()
  — or — Toolbelt menu → Open Dashboard (Qt)

If PySide6 is not installed, launch_qt() falls back to tb.launch() (text mode).

Qt event pumping:
  A slate post-tick callback calls processEvents() once per editor tick so
  the window stays responsive while UEFN runs heavy operations.
  This is the same pattern used by Kirch's uefn_listener.py.
"""

from __future__ import annotations

import sys
import unreal

# ─── PySide6 availability guard ───────────────────────────────────────────────

_PYSIDE6 = False
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QTabWidget, QStackedWidget,
        QVBoxLayout, QHBoxLayout, QGridLayout,
        QPushButton, QLabel, QLineEdit,
        QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox,
        QScrollArea, QGroupBox, QStatusBar, QSizePolicy, QFrame,
    )
    from PySide6.QtCore import Qt, QUrl, QPointF
    from PySide6.QtGui import (
        QFont, QDesktopServices, QIcon, QPixmap,
        QPainter, QColor, QBrush, QPolygonF,
    )
    _PYSIDE6 = True
except ImportError:
    QMainWindow = object  # fallback so class definition doesn't crash at import time

from UEFN_Toolbelt.registry import register_tool

# ─── Dark theme ───────────────────────────────────────────────────────────────
# Sourced from core/theme.py — the single source of truth for all Toolbelt colors.
# To change colors platform-wide, edit core/theme.PALETTE. Do not hard-code hex here.

from .core.theme import QSS as _QSS, color as _color  # noqa: E402 — after sys/unreal imports
from .core import theme as _theme_mod
from .core.config import get_config as _get_config

# ─── Widget helpers ───────────────────────────────────────────────────────────

def _page() -> tuple["QScrollArea", "QVBoxLayout"]:
    """Create a scrollable tab page. Returns (scroll_area, content_layout)."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setAlignment(Qt.AlignTop)
    layout.setSpacing(6)
    layout.setContentsMargins(8, 8, 8, 12)

    scroll = QScrollArea()
    scroll.setWidget(container)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return scroll, layout


def _group(parent: "QVBoxLayout", title: str) -> "QVBoxLayout":
    box = QGroupBox(title.upper())
    inner = QVBoxLayout()
    inner.setSpacing(3)
    inner.setContentsMargins(6, 4, 6, 6)
    box.setLayout(inner)
    parent.addWidget(box)
    return inner


def _btn(layout: "QVBoxLayout", text: str, fn, tip: str = "") -> "QPushButton":
    b = QPushButton(text)
    if tip:
        b.setToolTip(tip)
    b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    b.clicked.connect(fn)
    layout.addWidget(b)
    return b


def _row(layout: "QVBoxLayout", *items) -> None:
    """Horizontal row of (label, fn) button pairs."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(3)
    for label, fn in items:
        b = QPushButton(label)
        b.clicked.connect(fn)
        h.addWidget(b)
    layout.addWidget(w)


def _grid_btns(layout: "QVBoxLayout", items: list, cols: int = 3) -> None:
    """Grid of (label, fn) button pairs."""
    w = QWidget()
    g = QGridLayout(w)
    g.setSpacing(3)
    g.setContentsMargins(0, 0, 0, 0)
    for i, (label, fn) in enumerate(items):
        b = QPushButton(label)
        b.clicked.connect(fn)
        g.addWidget(b, i // cols, i % cols)
    layout.addWidget(w)


def _inp(placeholder: str, default: str = "", width: int = 130) -> "QLineEdit":
    e = QLineEdit(default)
    e.setPlaceholderText(placeholder)
    e.setFixedWidth(width)
    return e


def _spin(value: float = 1.0, mn: float = 0.0, mx: float = 9999.0,
          decimals: int = 0, width: int = 90) -> "QDoubleSpinBox":
    s = QDoubleSpinBox()
    s.setRange(mn, mx)
    s.setValue(value)
    s.setDecimals(int(decimals))
    s.setFixedWidth(max(width, 90))  # 90px minimum — narrower clips 3-digit numbers against arrows
    return s


def _btn_inp(layout: "QVBoxLayout", label: str, fn_factory,
             *widgets, tip: str = "") -> None:
    """Button + inline input widget(s) on one row."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(3)
    b = QPushButton(label)
    if tip:
        b.setToolTip(tip)
    b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    b.clicked.connect(fn_factory)
    h.addWidget(b)
    for widget in widgets:
        h.addWidget(widget)
    layout.addWidget(w)


def _sep(layout: "QVBoxLayout") -> None:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color: {_color('border')};")
    layout.addWidget(line)


# ─── Quick Actions ─────────────────────────────────────────────────────────────

def _build_setup_status(L: "QVBoxLayout") -> None:
    """
    First-run health badge. Runs silently on dashboard open and shows a
    compact status row for each system dependency. Green = good, yellow = warning,
    red = broken. Zero user action required — just glance at it.
    """
    g = _group(L, "Setup Status")

    checks = []

    # ── PySide6 ───────────────────────────────────────────────────────────────
    try:
        import PySide6
        checks.append(("PySide6 (dashboard UI)", "ok", PySide6.__version__))
    except ImportError:
        checks.append(("PySide6 (dashboard UI)", "error", "Not installed — dashboard widgets may be missing"))

    # ── Tool registry ─────────────────────────────────────────────────────────
    try:
        import UEFN_Toolbelt as _tb
        count = len(_tb.registry.list_tools())
        color = "ok" if count >= 240 else "warn"
        checks.append(("Tool registry", color, f"{count} tools registered"))
    except Exception as e:
        checks.append(("Tool registry", "error", str(e)))

    # ── MCP bridge ────────────────────────────────────────────────────────────
    # Check _bound_port > 0 — set only after listener is fully bound,
    # more reliable than thread.is_alive() which can be True before bind completes.
    try:
        from UEFN_Toolbelt.tools import mcp_bridge as _mcpb
        port = getattr(_mcpb, "_bound_port", 0)
        if port and port > 0:
            checks.append(("MCP bridge", "ok", f"Listening on port {port}  —  Claude Code can now control UEFN"))
        else:
            checks.append(("MCP bridge", "warn", "Not running  —  go to the MCP tab to start AI control"))
    except Exception as e:
        checks.append(("MCP bridge", "error", str(e)))

    # ── Config file ───────────────────────────────────────────────────────────
    try:
        from UEFN_Toolbelt.core.config import get_config
        cfg = get_config()
        import os
        if os.path.exists(cfg._path):
            checks.append(("Config file", "ok", cfg._path))
        else:
            checks.append(("Config file", "warn", "Not yet created (first run — will be written on first config_set)"))
    except Exception as e:
        checks.append(("Config file", "error", str(e)))

    # ── Verse-book ────────────────────────────────────────────────────────────
    try:
        import UEFN_Toolbelt as _tb2
        import os
        vb_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(_tb2.__file__))),
            "verse-book"
        )
        if os.path.isdir(vb_path):
            chapters = [f for f in os.listdir(vb_path) if f.endswith(".md")]
            checks.append(("Verse-book spec", "ok", f"{len(chapters)} chapters"))
        else:
            checks.append(("Verse-book spec", "warn", "Not cloned — Verse codegen tools use fallback mode"))
    except Exception as e:
        checks.append(("Verse-book spec", "warn", "Could not verify"))

    # ── Render rows ───────────────────────────────────────────────────────────
    color_map = {"ok": _color("ok"), "warn": _color("warn"), "error": _color("error")}
    icon_map  = {"ok": "✓", "warn": "⚠", "error": "✗"}

    for name, status, detail in checks:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 1, 2, 1)
        row_layout.setSpacing(8)

        col = color_map[status]
        icon_lbl = QLabel(icon_map[status])
        icon_lbl.setFixedWidth(16)
        icon_lbl.setStyleSheet(f"color: {col}; font-weight: bold; font-size: 12px; background: transparent;")

        name_lbl = QLabel(name)
        name_lbl.setFixedWidth(140)
        name_lbl.setStyleSheet(f"font-size: 11px; color: {_color('text')}; background: transparent;")

        detail_lbl = QLabel(detail)
        detail_lbl.setStyleSheet(f"font-size: 10px; color: {col}; background: transparent;")
        detail_lbl.setWordWrap(True)

        row_layout.addWidget(icon_lbl)
        row_layout.addWidget(name_lbl)
        row_layout.addWidget(detail_lbl, 1)
        g.addWidget(row)

    # Summary line
    n_ok   = sum(1 for _, s, _ in checks if s == "ok")
    n_warn = sum(1 for _, s, _ in checks if s == "warn")
    n_err  = sum(1 for _, s, _ in checks if s == "error")
    if n_err:
        summary_col, summary = _color("error"), f"{n_err} issue(s) need attention — see rows above"
    elif n_warn:
        summary_col, summary = _color("warn"), f"{n_ok}/{len(checks)} checks passing — {n_warn} advisory"
    else:
        summary_col, summary = _color("ok"), f"All {n_ok} checks passing — you're good to go"

    summary_lbl = QLabel(summary)
    summary_lbl.setStyleSheet(f"font-size: 11px; color: {summary_col}; padding: 4px 2px 0 2px; background: transparent;")
    g.addWidget(summary_lbl)

    _sep(L)


def _tab_quick_actions(R) -> "QScrollArea":
    import os
    scroll, L = _page()

    hero = QLabel("Quick Actions")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    desc = QLabel("The most frequently used tools for daily UEFN workflow automation.")
    desc.setStyleSheet(f"font-size: 12px; color: {_color('text_dim')}; padding-bottom: 12px;")
    desc.setWordWrap(True)
    L.addWidget(desc)

    # ── First-run banner — shown only when config.json doesn't exist yet ──────
    _cfg_path = _get_config()._path
    if not os.path.exists(_cfg_path):
        banner = QLabel(
            "👋  First time here? Start with the AI Project Setup section below, "
            "or browse any tab to explore all 291 tools. "
            "Full docs: github.com/undergroundrap/UEFN-TOOLBELT"
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"background: {_color('card')}; border: 1px solid {_color('ok')}; "
            f"border-radius: 6px; color: {_color('text')}; "
            "font-size: 12px; padding: 10px 14px; margin-bottom: 8px;"
        )
        L.addWidget(banner)

    _build_setup_status(L)

    # Flagship Tools
    g_flag = _group(L, "Flagship Tools")
    _btn(g_flag, "Verse Device Graph  —  visualise island architecture",
         lambda: R("verse_graph_open"),
         "Opens the force-directed node graph — devices are nodes, @editable refs are edges. "
         "Detects clusters, scores architecture health 0–100, exports to JSON.")
    _btn(g_flag, "Prefab Asset Migrator  —  copy assets with full dependency closure",
         lambda: R("prefab_migrate_open"),
         "Migrates assets (+ all meshes, materials, textures) to another folder or project. "
         "Dry-run preview, flatten option, viewport + Content Browser selection, cross-project disk copy.")
    _btn(g_flag, "UI Icon Importer  —  paste any image, import with correct Mip settings",
         lambda: R("ui_icon_import_open"),
         "Copy an image from any browser, Figma, or Photoshop and paste it directly. "
         "Auto-applies TC_UserInterface2D / NoMipmaps. Supports file browse and drag-drop.")
    _btn(g_flag, "Level Health Report  —  unified 0-100 audit score",
         lambda: R("level_health_open"),
         "Runs all audit categories (actors, naming, assets, devices, level info) and "
         "prints a formatted score report to the Output Log. Use level_health_report for MCP/AI.")
    _btn(g_flag, "World State Export  —  full level snapshot for AI",
         lambda: R("world_state_export"),
         "Dumps every actor's transform and readable properties to world_state.json — "
         "the AI read layer for Claude to reason about your level.")
    _btn(g_flag, "Device Catalog Scan  —  browse all 4,698 Creative devices",
         lambda: R("device_catalog_scan"),
         "Scans the Asset Registry for every placeable Fortnite Creative device. "
         "Builds Claude's complete placement palette in device_catalog.json.")

    # Optimization Tools
    g_opt = _group(L, "Optimization")
    _btn(g_opt, "Rogue Actor Scan  —  find problem actors in the level",
         lambda: R("rogue_actor_scan"),
         "Scans every actor for: extreme/zero/negative scale, at-origin placement, "
         "unnamed actors, off-map transforms. Returns a full issue report.")
    _btn(g_opt, "Convert to HISM  —  preview (dry run)",
         lambda: R("convert_to_hism", dry_run=True),
         "Groups selected StaticMeshActors by shared mesh and shows what would be merged. "
         "No changes made.")
    _btn(g_opt, "Convert to HISM  —  merge selection",
         lambda: R("convert_to_hism", dry_run=False),
         "Merges selected StaticMeshActors that share the same mesh into one HISM actor "
         "(one draw call). Deletes the originals. Run the dry-run preview first.")
    _btn(g_opt, "Material Parent Audit  —  /Game",
         lambda: R("material_parent_audit", scan_path="/Game"),
         "Groups all MaterialInstanceConstants in /Game by parent. Flags orphaned MIs "
         "and shows consolidation opportunities.")

    # 0. AI Project Setup Demo
    g_demo = _group(L, "AI Project Setup  |  demo.py")

    demo_name_inp = _inp("MyGame", "Project Name", width=140)
    _btn_inp(g_demo, "1. Setup Project  (scaffold + Verse)",
             lambda: R("project_setup", project_name=demo_name_inp.text()),
             demo_name_inp,
             tip="Creates the professional folder structure and deploys a wired Verse game manager. Run this first, wait for it to finish.")

    arena_combo = QComboBox()
    arena_combo.addItems(["medium", "small", "large"])
    arena_combo.setFixedWidth(100)
    _btn_inp(g_demo, "2a. Spawn Arena at Origin",
             lambda: R("arena_generate", size=arena_combo.currentText()),
             arena_combo,
             tip="Spawns arena centered at world origin (0, 0, 0). Run after step 1 returns.")

    def _spawn_at_camera():
        try:
            loc, _ = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
            R("arena_generate", size=arena_combo.currentText(),
              origin=(loc.x, loc.y, 0.0))
        except Exception as e:
            from .core import log_error
            log_error(f"[Arena] Could not read camera position: {e}")

    _btn(g_demo, "2b. Spawn Arena at Camera  (navigate first, then click)",
         _spawn_at_camera,
         "Reads your viewport camera position and spawns the arena there. Navigate to where you want it, then click.")

    _btn(g_demo, "3. Check Build Errors  (run after Build Verse Code click)",
         lambda: R("verse_patch_errors"),
         "Reads the build log and returns any Verse errors with file content for Claude to fix.")

    # 1. Selection & Utility
    g_sel = _group(L, "Selection & Utility")
    _btn(g_sel, "Print Selected Actors to Log", lambda: R("get_all_actors"), "Prints total count and paths of current selection.")
    _btn(g_sel, "Auto-Generate LODs (Selected)", lambda: R("lod_auto_generate_selection"), "Forces bulk generation of LODs for selected static meshes.")
    _btn(g_sel, "Bulk Snap Selection to Grid", lambda: R("bulk_snap_to_grid"), "Fixes messy transforms by automatically snapping all selected props to the grid.")

    # 2. Safety & Optimization
    g_snap = _group(L, "Safety & Optimization")
    _btn(g_snap, "Snapshot: Backup Current Level", lambda: R("snapshot_save"), "Saves the current transforms of all actors to a JSON backup.")
    _btn(g_snap, "Snapshot: Restore Level", lambda: R("snapshot_restore"), "Restores actor positions from the latest snapshot.")
    _btn(g_snap, "Scan Project Memory Limits", lambda: R("memory_scan"), "Runs a comprehensive memory audit of textures, meshes, and audio to prevent publish failures.")
    _btn(g_snap, "Sync Level Schema to AI (Docs)", lambda: R("api_crawl_level_classes"), "Crawls the level and automatically syncs the 1.6MB schema to the project docs for AI context.")

    # 3. Organization
    g_org = _group(L, "Project Organization")

    gen_inp = _inp("MyProject", "Project Name", width=120)
    gen_combo = QComboBox()
    gen_combo.addItems(["uefn_standard", "competitive_map", "solo_dev", "verse_heavy"])
    _btn_inp(g_org, "Generate Professional Folder Tree", 
             lambda: R("scaffold_generate", template=gen_combo.currentText(), project_name=gen_inp.text()), 
             gen_combo, gen_inp, tip="Scaffolds a perfectly organized Epic-standard folder hierarchy.")
    
    org_inp = _inp("/Game", "Scan Path", width=120)
    _btn_inp(g_org, "Smart Auto-Categorize Assets", 
             lambda: R("organize_smart_categorize", scan_path=org_inp.text(), organized_root="/Game/Organized", dry_run=False), 
             org_inp, tip="Scans a generic folder, detects classes, parses keywords from names, and intelligently sorts them into functional sub-categories (e.g. Meshes/Trees, Textures/Surface).")

    ren_inp = _inp("/Game", "Scan Path", width=120)
    _btn_inp(g_org, "Fix Asset Naming Conventions", 
             lambda: R("rename_enforce_conventions", scan_path=ren_inp.text()), 
             ren_inp, tip="Scans the path and automatically fixes Epic naming convention rule violations.")

    # 4. Level Design
    g_mat = _group(L, "Level Design & Materials")
    
    mat_combo = QComboBox()
    mat_combo.addItems(["chrome", "gold", "neon", "hologram", "lava", "plasma", "ice", "wood", "concrete", "team_red"])
    mat_combo.setFixedWidth(120)
    _btn_inp(g_mat, "Apply Material Preset (Selected)", 
             lambda: R("material_apply_preset", preset=mat_combo.currentText()), 
             mat_combo, tip="Instantly applies a smart material preset to all selected actors.")

    _btn(g_mat, "Clear Unused References (Orphans)", lambda: R("ref_delete_orphans"), "Deletes assets that have zero references to free up project space.")
    _btn(g_mat, "Replace Selected with Blueprint/Asset", lambda: R("replace_with_assets"), "Swaps all selected viewport actors with a new mesh from the Content Browser.")

    # 5. Verse Code Generation
    g_verse = _group(L, "Verse Code Generation")
    _btn(g_verse, "Generate @editable properties (Selected)", lambda: R("verse_gen_device_declarations"), "Reads the selected actors in the viewport and instantly generates perfectly typed Verse code variables.")

    # 6. Media & Assets
    g_media = _group(L, "Media & Assets")
    _btn(g_media, "Paste Image from Clipboard", lambda: R("import_image_from_clipboard"), "Instantly imports your current clipboard image as a Texture2D into /Game/UEFN_Toolbelt/Textures/.")

    L.addStretch()
    return scroll

# ─── Category Pages ───────────────────────────────────────────────────────────

def _tab_materials(R) -> "QScrollArea":
    scroll, L = _page()

    # Presets — 4-column grid
    g = _group(L, "Presets")
    presets = [
        "chrome", "gold", "neon", "hologram",
        "lava", "plasma", "ice", "mirror",
        "wood", "concrete", "rubber", "carbon_fiber",
        "jade", "obsidian", "rusty_metal", "team_red", "team_blue",
    ]
    _grid_btns(g, [
        (p.replace("_", " ").title(), lambda p=p: R("material_apply_preset", preset=p))
        for p in presets
    ], cols=4)

    # Operations
    g2 = _group(L, "Operations")
    _btn(g2, "Randomize Colors", lambda: R("material_randomize_colors"),
         "Random base color across all selected actors")
    _btn(g2, "Team Color Split  (Red / Blue by X pos)",
         lambda: R("material_team_color_split"))

    harm_combo = QComboBox()
    harm_combo.addItems(["triadic", "complementary", "analogous", "split_complementary"])
    harm_combo.setFixedWidth(180)
    _btn_inp(g2, "Color Harmony",
             lambda: R("material_color_harmony", harmony=harm_combo.currentText()),
             harm_combo, tip="Generate harmonious palette across selection")

    _btn(g2, "Gradient Painter  (Blue → Red along X)",
         lambda: R("material_gradient_painter", color_a="#0044FF", color_b="#FF2200"))
    _btn(g2, "Checkerboard Pattern", lambda: R("material_pattern_painter", pattern="checkerboard"))
    _btn(g2, "Stripe Pattern",       lambda: R("material_pattern_painter", pattern="stripes"))
    _btn(g2, "Glow Pulse Preview",   lambda: R("material_glow_pulse_preview"))

    # Bulk swap
    g_swap = _group(L, "Bulk Material Swap")
    old_mat_inp = _inp("/Game/Materials/M_Old", width=220)
    new_mat_inp = _inp("/Game/Materials/M_New", width=220)
    g_swap.addWidget(QLabel("  Replace:"))
    g_swap.addWidget(old_mat_inp)
    g_swap.addWidget(QLabel("  With:"))
    g_swap.addWidget(new_mat_inp)
    _row(g_swap,
         ("Swap — Selection", lambda: R("material_bulk_swap",
                                        old_material_path=old_mat_inp.text(),
                                        new_material_path=new_mat_inp.text(),
                                        scope="selection")),
         ("Swap — All Actors", lambda: R("material_bulk_swap",
                                         old_material_path=old_mat_inp.text(),
                                         new_material_path=new_mat_inp.text(),
                                         scope="all")),
    )

    # Custom presets
    g3 = _group(L, "Custom Presets")
    preset_name_inp = _inp("preset name", width=160)
    _btn_inp(g3, "Save Current as Preset",
             lambda: R("material_save_preset", preset_name=preset_name_inp.text()),
             preset_name_inp, tip="Save current selection's MI params as a named preset")
    _btn(g3, "List All Presets", lambda: R("material_list_presets"))

    return scroll


def _tab_procedural(R) -> "QScrollArea":
    scroll, L = _page()

    def _cam():
        """Return (x, y, z) of the current viewport camera, fallback to origin."""
        try:
            import unreal
            loc, _ = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
            return (loc.x, loc.y, loc.z)
        except Exception:
            return (0.0, 0.0, 0.0)

    def _cam_xy():
        x, y, z = _cam()
        return (x, y, 0.0)

    # Arena
    g = _group(L, "Arena Generator")
    _row(L if False else g, *[
        (f"{s.title()} Arena", lambda *_, s=s: R("arena_generate", size=s, apply_team_colors=True, origin=_cam_xy()))
        for s in ("small", "medium", "large")
    ])

    # Prop Patterns
    g2 = _group(L, "Prop Patterns")
    mesh_inp = _inp("/Game/Props/SM_Pillar", width=220)
    L.addWidget(QLabel("  Mesh path:"))
    L.addWidget(mesh_inp)

    preview_chk = QCheckBox("Preview mode (sphere markers, no real mesh)")
    preview_chk.setChecked(True)
    g2.addWidget(preview_chk)

    def _mesh():  return mesh_inp.text() or "/Engine/BasicShapes/Cube"
    def _prev():  return preview_chk.isChecked()

    _grid_btns(g2, [
        ("Grid 5×5",      lambda: R("pattern_grid",        mesh_path=_mesh(), preview=_prev(), origin=_cam_xy())),
        ("Circle Ring",   lambda: R("pattern_circle",      mesh_path=_mesh(), preview=_prev(), origin=_cam_xy())),
        ("Arc 180°",      lambda: R("pattern_arc",         mesh_path=_mesh(), preview=_prev(), origin=_cam_xy())),
        ("Spiral",        lambda: R("pattern_spiral",      mesh_path=_mesh(), preview=_prev(), origin=_cam_xy())),
        ("Line",          lambda: R("pattern_line",        mesh_path=_mesh(), preview=_prev(), origin=_cam_xy())),
        ("Sine Wave",     lambda: R("pattern_wave",        mesh_path=_mesh(), preview=_prev(), origin=_cam_xy())),
        ("Helix",         lambda: R("pattern_helix",       mesh_path=_mesh(), preview=_prev(), origin=_cam_xy())),
        ("Radial Rings",  lambda: R("pattern_radial_rows", mesh_path=_mesh(), preview=_prev(), origin=_cam_xy())),
    ], cols=4)
    _row(g2,
         ("Clear Preview",  lambda: R("pattern_clear", preview_only=True)),
         ("Clear All",      lambda: R("pattern_clear", preview_only=False)),
    )

    # Foliage Scatter
    g3 = _group(L, "Foliage Scatter")
    scatter_inp = _inp("/Engine/BasicShapes/Sphere", width=220)
    g3.addWidget(QLabel("Mesh path:"))
    g3.addWidget(scatter_inp)

    count_s = _spin(100, 1, 10000, width=80)
    radius_s = _spin(3000, 100, 50000, width=90)
    row_w = QWidget()
    rh = QHBoxLayout(row_w); rh.setContentsMargins(0,0,0,0); rh.setSpacing(4)
    rh.addWidget(QLabel("Count:")); rh.addWidget(count_s)
    rh.addWidget(QLabel("Radius:")); rh.addWidget(radius_s); rh.addStretch()
    g3.addWidget(row_w)

    _row(g3,
         ("Scatter Props",  lambda: R("scatter_props",
                                     mesh_path=scatter_inp.text() or "/Engine/BasicShapes/Sphere",
                                     count=int(count_s.value()), radius=radius_s.value(),
                                     center=_cam_xy())),
         ("Scatter HISM",   lambda: R("scatter_hism",
                                     mesh_path=scatter_inp.text() or "/Engine/BasicShapes/Sphere",
                                     count=int(count_s.value()), radius=radius_s.value(),
                                     center=_cam_xy())),
         ("Clear Scatter",  lambda: R("scatter_clear")),
    )

    # PCG Scatter
    g_pcg = _group(L, "PCG Scatter")

    avoid_cls_inp  = QLineEdit(); avoid_cls_inp.setPlaceholderText("avoid_class (e.g. PlayerStart)")
    avoid_rad_s    = _spin(800, 50, 5000, width=90)
    avoid_count_s  = _spin(40, 1, 500, width=70)
    avoid_radius_s = _spin(3000, 100, 20000, width=90)
    row_av = QWidget(); rh_av = QHBoxLayout(row_av); rh_av.setContentsMargins(0,0,0,0); rh_av.setSpacing(4)
    rh_av.addWidget(QLabel("Count:")); rh_av.addWidget(avoid_count_s)
    rh_av.addWidget(QLabel("Area:")); rh_av.addWidget(avoid_radius_s); rh_av.addStretch()
    g_pcg.addWidget(row_av)
    row_av2 = QWidget(); rh_av2 = QHBoxLayout(row_av2); rh_av2.setContentsMargins(0,0,0,0); rh_av2.setSpacing(4)
    rh_av2.addWidget(QLabel("Avoid Radius:")); rh_av2.addWidget(avoid_rad_s); rh_av2.addStretch()
    g_pcg.addWidget(row_av2)
    _btn_inp(g_pcg, "Scatter (Avoid Obstacles)",
             lambda: R("scatter_avoid",
                       mesh_path=scatter_inp.text() or "/Engine/BasicShapes/Sphere",
                       count=int(avoid_count_s.value()),
                       radius=avoid_radius_s.value(),
                       center=_cam_xy(),
                       avoid_class=avoid_cls_inp.text().strip(),
                       avoid_radius=avoid_rad_s.value()),
             avoid_cls_inp,
             tip="Poisson scatter that skips positions near actors matching avoid_class.")

    road_pts_inp  = QLineEdit(); road_pts_inp.setPlaceholderText("points: [[x,y,z],[x,y,z],...]  (JSON)")
    road_offset_s = _spin(400, 50, 5000, width=80)
    road_spread_s = _spin(150, 0, 2000, width=80)
    row_rd = QWidget(); rh_rd = QHBoxLayout(row_rd); rh_rd.setContentsMargins(0,0,0,0); rh_rd.setSpacing(4)
    rh_rd.addWidget(QLabel("Offset:")); rh_rd.addWidget(road_offset_s)
    rh_rd.addWidget(QLabel("Spread:")); rh_rd.addWidget(road_spread_s); rh_rd.addStretch()
    g_pcg.addWidget(row_rd)
    def _scatter_road_edge():
        import json
        raw = road_pts_inp.text().strip()
        pts = json.loads(raw) if raw else None
        R("scatter_road_edge",
          mesh_path=scatter_inp.text() or "/Engine/BasicShapes/Sphere",
          points=pts,
          edge_offset=road_offset_s.value(),
          spread=road_spread_s.value())
    _btn_inp(g_pcg, "Scatter Road Edge",
             _scatter_road_edge,
             road_pts_inp,
             tip="Place props along both shoulders of a path. Paste [[x,y,z],...] or select a SplineActor.")

    # ── Zone Tools ────────────────────────────────────────────────────────────
    g_zone = _group(L, "Zone Spawner")

    zone_lbl_inp  = _inp("Zone label", "Zone", width=100)
    zone_w_s      = _spin(2000, 100, 50000, width=80)
    zone_d_s      = _spin(2000, 100, 50000, width=80)
    zone_h_s      = _spin(600,  100, 20000, width=80)
    row_zsize = QWidget(); h_zsize = QHBoxLayout(row_zsize); h_zsize.setContentsMargins(0,0,0,0); h_zsize.setSpacing(4)
    h_zsize.addWidget(QLabel("W:")); h_zsize.addWidget(zone_w_s)
    h_zsize.addWidget(QLabel("D:")); h_zsize.addWidget(zone_d_s)
    h_zsize.addWidget(QLabel("H:")); h_zsize.addWidget(zone_h_s); h_zsize.addStretch()
    g_zone.addWidget(row_zsize)
    _btn_inp(g_zone, "Spawn Zone at Camera",
             lambda: R("zone_spawn",
                       width=zone_w_s.value(), depth=zone_d_s.value(),
                       height=zone_h_s.value(), label=zone_lbl_inp.text() or "Zone"),
             zone_lbl_inp, tip="Spawns a cube zone marker at the camera position.")

    zone_fill_inp = _inp("asset path", "/Engine/BasicShapes/Cube", width=220)
    zone_fill_cnt = _spin(20, 1, 500, width=70)
    row_zfill = QWidget(); h_zfill = QHBoxLayout(row_zfill); h_zfill.setContentsMargins(0,0,0,0); h_zfill.setSpacing(4)
    h_zfill.addWidget(QLabel("Count:")); h_zfill.addWidget(zone_fill_cnt); h_zfill.addStretch()
    g_zone.addWidget(row_zfill)
    _btn_inp(g_zone, "Fill Zone with Scatter  (select zone first)",
             lambda: R("zone_fill_scatter",
                       asset_path=zone_fill_inp.text() or "/Engine/BasicShapes/Cube",
                       count=int(zone_fill_cnt.value())),
             zone_fill_inp, tip="Scatter copies of an asset randomly inside the selected zone actor.")

    _row(g_zone,
         ("Resize Zone → Selection",  lambda: R("zone_resize_to_selection")),
         ("Snap Zone → Selection",    lambda: R("zone_snap_to_selection")),
    )
    _row(g_zone,
         ("Select Zone Contents",     lambda: R("zone_select_contents")),
         ("List Zones",               lambda: R("zone_list")),
    )
    zone_dx_s = _spin(0, -99999, 99999, width=70)
    zone_dy_s = _spin(0, -99999, 99999, width=70)
    zone_dz_s = _spin(0, -99999, 99999, width=70)
    row_zmov = QWidget(); h_zmov = QHBoxLayout(row_zmov); h_zmov.setContentsMargins(0,0,0,0); h_zmov.setSpacing(4)
    h_zmov.addWidget(QLabel("ΔX:")); h_zmov.addWidget(zone_dx_s)
    h_zmov.addWidget(QLabel("ΔY:")); h_zmov.addWidget(zone_dy_s)
    h_zmov.addWidget(QLabel("ΔZ:")); h_zmov.addWidget(zone_dz_s); h_zmov.addStretch()
    g_zone.addWidget(row_zmov)
    _btn(g_zone, "Move Zone + Contents",
         lambda: R("zone_move_contents",
                   offset_x=zone_dx_s.value(), offset_y=zone_dy_s.value(), offset_z=zone_dz_s.value()))

    # Spline
    g4 = _group(L, "Spline Prop Placer")
    count2_s = _spin(20, 1, 500, width=80)
    _btn_inp(g4, "Place Props Along Spline",
             lambda: R("spline_place_props", count=int(count2_s.value()), align_to_tangent=True),
             count2_s)
    _btn(g4, "Clear Spline Props", lambda: R("spline_clear_props"))

    # Procedural Geometry
    g_geo = _group(L, "Procedural Geometry")
    wire_seg_s = _spin(16, 2, 64, width=70)
    wire_sag_s = _spin(120, 0, 1000, width=80)
    _btn_inp(g_geo, "Generate Wire (Between 2 Selected)",
             lambda: R("procedural_wire_create", segments=int(wire_seg_s.value()), sag_amount=wire_sag_s.value(), thickness=0.1),
             wire_seg_s, wire_sag_s, tip="Draws a sagging wire between two selected actors.")
    
    scat_count_s = _spin(50, 1, 1000, width=80)
    scat_rad_s = _spin(1000, 100, 10000, width=90)
    scat_combo = QComboBox(); scat_combo.addItems(["sphere", "cube"]); scat_combo.setFixedWidth(100)
    _btn_inp(g_geo, "Volume Scatter Meshes",
             lambda: R("procedural_volume_scatter", count=int(scat_count_s.value()), radius=scat_rad_s.value(), shape=scat_combo.currentText()),
             scat_count_s, scat_rad_s, scat_combo, tip="Scatters random meshes within a spherical or cubic boundary.")

    return scroll


def _tab_bulk_ops(R) -> "QScrollArea":
    scroll, L = _page()

    # Align
    g = _group(L, "Align")
    _row(g,
         ("Align X", lambda: R("bulk_align", axis="X")),
         ("Align Y", lambda: R("bulk_align", axis="Y")),
         ("Align Z", lambda: R("bulk_align", axis="Z")),
    )

    # Distribute
    g2 = _group(L, "Distribute")
    _row(g2,
         ("Distribute X", lambda: R("bulk_distribute", axis="X")),
         ("Distribute Y", lambda: R("bulk_distribute", axis="Y")),
         ("Distribute Z", lambda: R("bulk_distribute", axis="Z")),
    )

    # Snap
    g3 = _group(L, "Snap to Grid")
    grid_s = _spin(100, 1, 10000, width=90)
    _btn_inp(g3, "Snap to Grid",
             lambda: R("bulk_snap_to_grid", grid=grid_s.value()),
             grid_s, tip="Snap selected actor locations to world grid")

    # Randomize
    g4 = _group(L, "Randomize")
    rot_s  = _spin(360, 0, 360, width=80)
    scl_chk = QCheckBox("Also randomize scale")
    rot_row = QWidget()
    rh = QHBoxLayout(rot_row); rh.setContentsMargins(0,0,0,0)
    rh.addWidget(QLabel("Yaw range °:")); rh.addWidget(rot_s); rh.addStretch()
    g4.addWidget(rot_row)
    g4.addWidget(scl_chk)
    _btn(g4, "Randomize",
         lambda: R("bulk_randomize",
                   rot_range=rot_s.value(),
                   randomize_rot=True,
                   randomize_scale=scl_chk.isChecked()))

    # Other
    g5 = _group(L, "Other")
    _btn(g5, "Reset Transforms (rot→0, scale→1)", lambda: R("bulk_reset"))
    _row(g5,
         ("Mirror X", lambda: R("bulk_mirror", axis="X")),
         ("Mirror Y", lambda: R("bulk_mirror", axis="Y")),
         ("Mirror Z", lambda: R("bulk_mirror", axis="Z")),
    )
    _btn(g5, "Stack Vertically",     lambda: R("bulk_stack"))
    _btn(g5, "Normalize Scale →1",   lambda: R("bulk_normalize_scale"))

    # ── Advanced Alignment ─────────────────────────────────────────────────
    g_adv = _group(L, "Advanced Alignment")

    adv_axis_combo = QComboBox(); adv_axis_combo.addItems(["X","Y","Z"]); adv_axis_combo.setCurrentIndex(2); adv_axis_combo.setFixedWidth(55)
    adv_ref_combo  = QComboBox(); adv_ref_combo.addItems(["first","last"]); adv_ref_combo.setFixedWidth(60)
    row_adv1 = QWidget(); h_adv1 = QHBoxLayout(row_adv1); h_adv1.setContentsMargins(0,0,0,0); h_adv1.setSpacing(4)
    h_adv1.addWidget(QLabel("Axis:")); h_adv1.addWidget(adv_axis_combo)
    h_adv1.addWidget(QLabel("Ref:")); h_adv1.addWidget(adv_ref_combo); h_adv1.addStretch()
    g_adv.addWidget(row_adv1)
    _btn(g_adv, "Align to Reference Actor",
         lambda: R("align_to_reference", axis=adv_axis_combo.currentText(), reference=adv_ref_combo.currentText()))

    gap_s = _spin(0, -10000, 10000, width=80)
    gap_axis_combo = QComboBox(); gap_axis_combo.addItems(["X","Y","Z"]); gap_axis_combo.setFixedWidth(55)
    row_adv2 = QWidget(); h_adv2 = QHBoxLayout(row_adv2); h_adv2.setContentsMargins(0,0,0,0); h_adv2.setSpacing(4)
    h_adv2.addWidget(QLabel("Gap cm:")); h_adv2.addWidget(gap_s)
    h_adv2.addWidget(QLabel("Axis:")); h_adv2.addWidget(gap_axis_combo); h_adv2.addStretch()
    g_adv.addWidget(row_adv2)
    _btn(g_adv, "Distribute with Exact Gap",
         lambda: R("distribute_with_gap", axis=gap_axis_combo.currentText(), gap=gap_s.value()))

    pivot_angle_s = _spin(90, -360, 360, width=75)
    pivot_axis_combo  = QComboBox(); pivot_axis_combo.addItems(["Z","X","Y"]); pivot_axis_combo.setFixedWidth(55)
    pivot_ref_combo   = QComboBox(); pivot_ref_combo.addItems(["center","first"]); pivot_ref_combo.setFixedWidth(70)
    row_adv3 = QWidget(); h_adv3 = QHBoxLayout(row_adv3); h_adv3.setContentsMargins(0,0,0,0); h_adv3.setSpacing(4)
    h_adv3.addWidget(QLabel("Angle°:")); h_adv3.addWidget(pivot_angle_s)
    h_adv3.addWidget(QLabel("Axis:")); h_adv3.addWidget(pivot_axis_combo); h_adv3.addStretch()
    g_adv.addWidget(row_adv3)
    row_adv3b = QWidget(); h_adv3b = QHBoxLayout(row_adv3b); h_adv3b.setContentsMargins(0,0,0,0); h_adv3b.setSpacing(4)
    h_adv3b.addWidget(QLabel("Pivot:")); h_adv3b.addWidget(pivot_ref_combo); h_adv3b.addStretch()
    g_adv.addWidget(row_adv3b)
    _btn(g_adv, "Rotate Around Pivot",
         lambda: R("rotate_around_pivot", angle_deg=pivot_angle_s.value(),
                   axis=pivot_axis_combo.currentText(), pivot=pivot_ref_combo.currentText()))

    _grid_btns(g_adv, [
        ("Snap to Surface",  lambda: R("align_to_surface")),
        ("Match Spacing",    lambda: R("match_spacing", axis=adv_axis_combo.currentText())),
        ("Grid Two Points",  lambda: R("align_to_grid_two_points")),
    ], cols=2)

    # ── Actor Organization ─────────────────────────────────────────────────
    g_org = _group(L, "Actor Organization")

    folder_inp = _inp("folder name", "MyGroup", width=160)
    _btn_inp(g_org, "Move Selection → Folder",
             lambda: R("actor_move_to_folder", folder_name=folder_inp.text() or "MyGroup"),
             folder_inp, tip="Moves all selected actors into a named World Outliner folder.")

    _row(g_org,
         ("Move to Root",       lambda: R("actor_move_to_root")),
         ("List All Folders",   lambda: R("actor_folder_list")),
    )

    old_folder_inp = _inp("old folder", "", width=130)
    new_folder_inp = _inp("new folder", "", width=130)
    row_ren = QWidget(); h_ren = QHBoxLayout(row_ren); h_ren.setContentsMargins(0,0,0,0); h_ren.setSpacing(4)
    h_ren.addWidget(QLabel("From:")); h_ren.addWidget(old_folder_inp)
    h_ren.addWidget(QLabel("To:")); h_ren.addWidget(new_folder_inp); h_ren.addStretch()
    g_org.addWidget(row_ren)
    _btn(g_org, "Rename Folder",
         lambda: R("actor_rename_folder", old_folder=old_folder_inp.text(), new_folder=new_folder_inp.text()))

    sel_folder_inp = _inp("folder name", "", width=160)
    _btn_inp(g_org, "Select All in Folder",
             lambda: R("actor_select_by_folder", folder_name=sel_folder_inp.text()),
             sel_folder_inp)

    class_inp = _inp("class name e.g. PlayerStart", "", width=200)
    _btn_inp(g_org, "Select All by Class",
             lambda: R("actor_select_by_class", class_filter=class_inp.text()),
             class_inp)

    _grid_btns(g_org, [
        ("Select Same Folder",   lambda: R("actor_select_same_folder")),
        ("Attach to Parent",     lambda: R("actor_attach_to_parent")),
        ("Detach",               lambda: R("actor_detach")),
    ], cols=2)

    loc_chk = QCheckBox("Loc"); loc_chk.setChecked(True)
    rot_chk = QCheckBox("Rot"); rot_chk.setChecked(True)
    scl_chk2 = QCheckBox("Scale"); scl_chk2.setChecked(False)
    row_mt = QWidget(); h_mt = QHBoxLayout(row_mt); h_mt.setContentsMargins(0,0,0,0); h_mt.setSpacing(6)
    h_mt.addWidget(loc_chk); h_mt.addWidget(rot_chk); h_mt.addWidget(scl_chk2); h_mt.addStretch()
    g_org.addWidget(row_mt)
    _btn(g_org, "Match Transform  (first → others)",
         lambda: R("actor_match_transform",
                   copy_location=loc_chk.isChecked(),
                   copy_rotation=rot_chk.isChecked(),
                   copy_scale=scl_chk2.isChecked()))

    # ── Proximity & Duplication ────────────────────────────────────────────────
    g_prox = _group(L, "Proximity & Duplication")

    prox_dir_combo = QComboBox()
    prox_dir_combo.addItems(["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
    prox_dir_combo.setFixedWidth(60)
    prox_gap_s = _spin(0, 0, 10000, width=70)
    prox_align_combo = QComboBox(); prox_align_combo.addItems(["center", "keep"]); prox_align_combo.setFixedWidth(70)
    row_pn = QWidget(); h_pn = QHBoxLayout(row_pn); h_pn.setContentsMargins(0,0,0,0); h_pn.setSpacing(4)
    h_pn.addWidget(QLabel("Dir:")); h_pn.addWidget(prox_dir_combo)
    h_pn.addWidget(QLabel("Gap:")); h_pn.addWidget(prox_gap_s); h_pn.addStretch()
    g_prox.addWidget(row_pn)
    row_pn2 = QWidget(); h_pn2 = QHBoxLayout(row_pn2); h_pn2.setContentsMargins(0,0,0,0); h_pn2.setSpacing(4)
    h_pn2.addWidget(QLabel("Align:")); h_pn2.addWidget(prox_align_combo); h_pn2.addStretch()
    g_prox.addWidget(row_pn2)
    _btn(g_prox, "Place Next To  (2 selected: ref → mover)",
         lambda: R("actor_place_next_to",
                   direction=prox_dir_combo.currentText(),
                   gap=prox_gap_s.value(),
                   align=prox_align_combo.currentText()))

    chain_axis_combo = QComboBox(); chain_axis_combo.addItems(["X","Y","Z"]); chain_axis_combo.setFixedWidth(50)
    chain_gap_s = _spin(0, 0, 10000, width=70)
    row_ch = QWidget(); h_ch = QHBoxLayout(row_ch); h_ch.setContentsMargins(0,0,0,0); h_ch.setSpacing(4)
    h_ch.addWidget(QLabel("Axis:")); h_ch.addWidget(chain_axis_combo)
    h_ch.addWidget(QLabel("Gap:")); h_ch.addWidget(chain_gap_s); h_ch.addStretch()
    g_prox.addWidget(row_ch)
    _btn(g_prox, "Chain End-to-End  (selection ordered by axis)",
         lambda: R("actor_chain_place",
                   axis=chain_axis_combo.currentText(),
                   gap=chain_gap_s.value()))

    dup_count_s  = _spin(3, 1, 200, width=60)
    dup_dx_s     = _spin(300, -99999, 99999, width=70)
    dup_dy_s     = _spin(0,   -99999, 99999, width=70)
    dup_dz_s     = _spin(0,   -99999, 99999, width=70)
    row_dup = QWidget(); h_dup = QHBoxLayout(row_dup); h_dup.setContentsMargins(0,0,0,0); h_dup.setSpacing(4)
    h_dup.addWidget(QLabel("Count×:")); h_dup.addWidget(dup_count_s)
    h_dup.addWidget(QLabel("dX:")); h_dup.addWidget(dup_dx_s); h_dup.addStretch()
    g_prox.addWidget(row_dup)
    row_dup2 = QWidget(); h_dup2 = QHBoxLayout(row_dup2); h_dup2.setContentsMargins(0,0,0,0); h_dup2.setSpacing(4)
    h_dup2.addWidget(QLabel("dY:")); h_dup2.addWidget(dup_dy_s)
    h_dup2.addWidget(QLabel("dZ:")); h_dup2.addWidget(dup_dz_s); h_dup2.addStretch()
    g_prox.addWidget(row_dup2)
    _btn(g_prox, "Duplicate with Offset",
         lambda: R("actor_duplicate_offset",
                   count=int(dup_count_s.value()),
                   offset_x=dup_dx_s.value(),
                   offset_y=dup_dy_s.value(),
                   offset_z=dup_dz_s.value()))

    old_cls_inp  = _inp("old class filter  e.g. SM_OldRock", "", width=240)
    new_ast_inp  = _inp("new asset path  /Game/…", "", width=240)
    row_rc = QWidget(); h_rc = QHBoxLayout(row_rc); h_rc.setContentsMargins(0,0,0,0); h_rc.setSpacing(4)
    h_rc.addWidget(QLabel("Old:")); h_rc.addWidget(old_cls_inp); h_rc.addStretch()
    g_prox.addWidget(row_rc)
    row_rc2 = QWidget(); h_rc2 = QHBoxLayout(row_rc2); h_rc2.setContentsMargins(0,0,0,0); h_rc2.setSpacing(4)
    h_rc2.addWidget(QLabel("New:")); h_rc2.addWidget(new_ast_inp); h_rc2.addStretch()
    g_prox.addWidget(row_rc2)
    _row(g_prox,
         ("Replace Class  (Preview)",
          lambda: R("actor_replace_class", old_class_filter=old_cls_inp.text(),
                    new_asset_path=new_ast_inp.text(), dry_run=True)),
         ("EXECUTE",
          lambda: R("actor_replace_class", old_class_filter=old_cls_inp.text(),
                    new_asset_path=new_ast_inp.text(), dry_run=False)),
    )

    clust_rad_s    = _spin(800, 50, 20000, width=80)
    clust_prefix   = _inp("Cluster", "Cluster", width=80)
    clust_min_s    = _spin(2, 1, 50, width=60)
    row_clust = QWidget(); h_clust = QHBoxLayout(row_clust); h_clust.setContentsMargins(0,0,0,0); h_clust.setSpacing(4)
    h_clust.addWidget(QLabel("Radius:")); h_clust.addWidget(clust_rad_s)
    h_clust.addWidget(QLabel("Min:")); h_clust.addWidget(clust_min_s); h_clust.addStretch()
    g_prox.addWidget(row_clust)
    row_clust2 = QWidget(); h_clust2 = QHBoxLayout(row_clust2); h_clust2.setContentsMargins(0,0,0,0); h_clust2.setSpacing(4)
    h_clust2.addWidget(QLabel("Folder Prefix:")); h_clust2.addWidget(clust_prefix); h_clust2.addStretch()
    g_prox.addWidget(row_clust2)
    _btn(g_prox, "Auto-Cluster to Folders  (selection or level)",
         lambda: R("actor_cluster_to_folder",
                   radius=clust_rad_s.value(),
                   folder_prefix=clust_prefix.text() or "Cluster",
                   min_cluster_size=int(clust_min_s.value())))

    # Verse (Schema-Driven)
    g6 = _group(L, "Verse Property Hardening")
    prop_inp = _inp("bIsEnabled", "bIsEnabled", width=140)
    val_inp  = _inp("True", "True", width=100)
    _btn_inp(g6, "Bulk Set Verse Property", 
             lambda: R("verse_bulk_set_property", property_name=prop_inp.text(), value=val_inp.text()), 
             prop_inp, val_inp, tip="Sets a property on all selected Verse devices with schema-validated safety checks.")

    return scroll


def _tab_text(R) -> "QScrollArea":
    scroll, L = _page()

    def _cam():
        try:
            import unreal
            loc, _ = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
            return (loc.x, loc.y, loc.z)
        except Exception:
            return (0.0, 0.0, 0.0)

    g = _group(L, "Place")
    text_inp  = _inp("Sign text", "ZONE", width=120)
    color_inp = _inp("#RRGGBB", "#FFDD00", width=90)
    z_s       = _spin(200, -9999, 9999, width=80)
    row1 = QWidget(); h1 = QHBoxLayout(row1); h1.setContentsMargins(0, 0, 0, 0); h1.setSpacing(4)
    h1.addWidget(QLabel("Text:")); h1.addWidget(text_inp)
    h1.addWidget(QLabel("Color:")); h1.addWidget(color_inp); h1.addStretch()
    g.addWidget(row1)
    row1b = QWidget(); h1b = QHBoxLayout(row1b); h1b.setContentsMargins(0,0,0,0); h1b.setSpacing(4)
    h1b.addWidget(QLabel("Z Offset:")); h1b.addWidget(z_s); h1b.addStretch()
    g.addWidget(row1b)
    _btn(g, "Place Sign at Camera",
         lambda: R("text_place",
                   text=text_inp.text() or "ZONE",
                   color=color_inp.text() or "#FFDD00",
                   location=(_cam()[0], _cam()[1], _cam()[2] + z_s.value())))

    label_col_inp = _inp("#00FFCC", "#00FFCC", width=90)
    _btn_inp(g, "Label Selection (name each actor)",
             lambda: R("text_label_selection", color=label_col_inp.text() or "#00FFCC"),
             label_col_inp)

    # Grid
    g2 = _group(L, "Zone Grid")
    cols_s = _spin(4, 1, 26, width=70)
    rows_s = _spin(4, 1, 26, width=70)
    cell_s = _spin(2000, 100, 50000, width=90)
    row2 = QWidget(); h2 = QHBoxLayout(row2); h2.setContentsMargins(0,0,0,0); h2.setSpacing(4)
    h2.addWidget(QLabel("Cols:")); h2.addWidget(cols_s)
    h2.addWidget(QLabel("Rows:")); h2.addWidget(rows_s); h2.addStretch()
    g2.addWidget(row2)
    row2b = QWidget(); h2b = QHBoxLayout(row2b); h2b.setContentsMargins(0,0,0,0); h2b.setSpacing(4)
    h2b.addWidget(QLabel("Cell cm:")); h2b.addWidget(cell_s); h2b.addStretch()
    g2.addWidget(row2b)
    _btn(g2, "Paint Zone Grid (A1–D4 style)",
         lambda: R("text_paint_grid",
                   cols=int(cols_s.value()), rows=int(rows_s.value()),
                   cell_size=cell_s.value(), origin=_cam()))

    # ── Sign / Text Actor Bulk Spawner ─────────────────────────────────────
    g_bb = _group(L, "Sign Spawner  (TextRenderActor — not Billboard device)")

    bb_text_inp   = _inp("Sign text", "SIGN", width=110)
    bb_prefix_inp = _inp("Label prefix", "Sign", width=90)
    bb_color_inp  = _inp("#RRGGBB", "#FFFFFF", width=80)

    bb_count_s   = _spin(6,   1, 200,   width=60)
    bb_size_s    = _spin(100, 10, 2000, width=70)
    bb_spacing_s = _spin(400, 50, 5000, width=80)
    bb_cols_s    = _spin(4,   1, 20,   width=60)

    bb_layout_combo = QComboBox(); bb_layout_combo.addItems(["row_x", "row_y", "grid"]); bb_layout_combo.setFixedWidth(80)

    row_bb1 = QWidget(); h_bb1 = QHBoxLayout(row_bb1); h_bb1.setContentsMargins(0,0,0,0); h_bb1.setSpacing(4)
    h_bb1.addWidget(QLabel("Text:")); h_bb1.addWidget(bb_text_inp)
    h_bb1.addWidget(QLabel("Prefix:")); h_bb1.addWidget(bb_prefix_inp); h_bb1.addStretch()
    g_bb.addWidget(row_bb1)
    row_bb1b = QWidget(); h_bb1b = QHBoxLayout(row_bb1b); h_bb1b.setContentsMargins(0,0,0,0); h_bb1b.setSpacing(4)
    h_bb1b.addWidget(QLabel("Color:")); h_bb1b.addWidget(bb_color_inp); h_bb1b.addStretch()
    g_bb.addWidget(row_bb1b)

    row_bb2 = QWidget(); h_bb2 = QHBoxLayout(row_bb2); h_bb2.setContentsMargins(0,0,0,0); h_bb2.setSpacing(4)
    h_bb2.addWidget(QLabel("Count:")); h_bb2.addWidget(bb_count_s)
    h_bb2.addWidget(QLabel("Size:")); h_bb2.addWidget(bb_size_s); h_bb2.addStretch()
    g_bb.addWidget(row_bb2)
    row_bb3 = QWidget(); h_bb3 = QHBoxLayout(row_bb3); h_bb3.setContentsMargins(0,0,0,0); h_bb3.setSpacing(4)
    h_bb3.addWidget(QLabel("Spacing:")); h_bb3.addWidget(bb_spacing_s)
    h_bb3.addWidget(QLabel("Cols:")); h_bb3.addWidget(bb_cols_s); h_bb3.addStretch()
    g_bb.addWidget(row_bb3)
    row_bb4 = QWidget(); h_bb4 = QHBoxLayout(row_bb4); h_bb4.setContentsMargins(0,0,0,0); h_bb4.setSpacing(4)
    h_bb4.addWidget(QLabel("Layout:")); h_bb4.addWidget(bb_layout_combo); h_bb4.addStretch()
    g_bb.addWidget(row_bb4)

    _btn(g_bb, "Spawn Signs at Camera",
         lambda: R("sign_spawn_bulk",
                   count=int(bb_count_s.value()),
                   text=bb_text_inp.text() or "SIGN",
                   prefix=bb_prefix_inp.text() or "Sign",
                   location=(_cam()[0], _cam()[1], _cam()[2] + 200.0),
                   layout=bb_layout_combo.currentText(),
                   spacing=bb_spacing_s.value(),
                   cols=int(bb_cols_s.value()),
                   color=bb_color_inp.text() or "#FFFFFF",
                   world_size=bb_size_s.value()))

    # ── Sign Batch Edit ─────────────────────────────────────────────────────
    g_bbe = _group(L, "Sign Batch Edit  (select signs first)")

    bbe_text_inp  = _inp("new text (leave blank to skip)", "", width=180)
    bbe_color_inp = _inp("#RRGGBB (blank = skip)", "", width=130)
    bbe_size_s    = _spin(0, 0, 2000, width=70)
    bbe_size_chk  = QCheckBox("Change size"); bbe_size_chk.setChecked(False)

    row_bbe = QWidget(); h_bbe = QHBoxLayout(row_bbe); h_bbe.setContentsMargins(0,0,0,0); h_bbe.setSpacing(4)
    h_bbe.addWidget(QLabel("Color:")); h_bbe.addWidget(bbe_color_inp)
    h_bbe.addWidget(bbe_size_chk); h_bbe.addWidget(bbe_size_s); h_bbe.addStretch()
    g_bbe.addWidget(row_bbe)

    def _batch_edit():
        R("sign_batch_edit",
          text=bbe_text_inp.text().strip() or None,
          color=bbe_color_inp.text().strip() or None,
          world_size=bbe_size_s.value() if bbe_size_chk.isChecked() else None)
    _btn_inp(g_bbe, "Apply to Selected Signs", _batch_edit,
             bbe_text_inp, tip="Edits only the fields you fill in. Leave blank to skip that field.")

    # Batch rename
    rename_prefix_inp = _inp("prefix", "Sign", width=100)
    rename_start_s    = _spin(1, 1, 999, width=60)
    sync_text_chk     = QCheckBox("Sync text to label"); sync_text_chk.setChecked(False)
    row_ren = QWidget(); h_ren = QHBoxLayout(row_ren); h_ren.setContentsMargins(0,0,0,0); h_ren.setSpacing(4)
    h_ren.addWidget(QLabel("Prefix:")); h_ren.addWidget(rename_prefix_inp)
    h_ren.addWidget(QLabel("Start:")); h_ren.addWidget(rename_start_s)
    h_ren.addWidget(sync_text_chk); h_ren.addStretch()
    g_bbe.addWidget(row_ren)
    _btn(g_bbe, "Rename Selected Sequentially",
         lambda: R("sign_batch_rename",
                   prefix=rename_prefix_inp.text() or "Sign",
                   start=int(rename_start_s.value()),
                   sync_text=sync_text_chk.isChecked()))

    # Utilities
    _row(g_bbe,
         ("List All Signs",    lambda: R("sign_list")),
         ("Clear Signs Folder", lambda: R("sign_clear", dry_run=False)),
    )

    # ── Floating Label Attach ───────────────────────────────────────────────
    g_lbl = _group(L, "Floating Label Attach  (select actors first)")
    lbl_text_inp  = _inp("custom text (blank = actor name)", "", width=180)
    lbl_color_inp = _inp("#RRGGBB", "#00FFCC", width=80)
    lbl_size_s    = _spin(60, 10, 500, width=65)
    lbl_z_s       = _spin(150, 0, 2000, width=75)
    lbl_yaw_s     = _spin(0, -360, 360, width=65)
    lbl_name_chk  = QCheckBox("Use actor name"); lbl_name_chk.setChecked(True)

    row_lbl = QWidget(); h_lbl = QHBoxLayout(row_lbl); h_lbl.setContentsMargins(0,0,0,0); h_lbl.setSpacing(4)
    h_lbl.addWidget(QLabel("Color:")); h_lbl.addWidget(lbl_color_inp)
    h_lbl.addWidget(QLabel("Size:")); h_lbl.addWidget(lbl_size_s); h_lbl.addStretch()
    g_lbl.addWidget(row_lbl)
    row_lbl2 = QWidget(); h_lbl2 = QHBoxLayout(row_lbl2); h_lbl2.setContentsMargins(0,0,0,0); h_lbl2.setSpacing(4)
    h_lbl2.addWidget(QLabel("Z Offset:")); h_lbl2.addWidget(lbl_z_s)
    h_lbl2.addWidget(QLabel("Yaw°:")); h_lbl2.addWidget(lbl_yaw_s); h_lbl2.addStretch()
    g_lbl.addWidget(row_lbl2)
    g_lbl.addWidget(lbl_name_chk)

    def _attach_label():
        R("label_attach",
          text=lbl_text_inp.text().strip() or "",
          color=lbl_color_inp.text() or "#00FFCC",
          world_size=lbl_size_s.value(),
          offset_z=lbl_z_s.value(),
          yaw=lbl_yaw_s.value(),
          use_actor_name=lbl_name_chk.isChecked())
    _btn_inp(g_lbl, "Attach Floating Label to Selected",
             _attach_label, lbl_text_inp,
             tip="Spawns a text actor above each selected actor and parents it — label follows the actor when moved.")

    # Manage
    g3 = _group(L, "Manage")
    _btn(g3, "Color Cycle Banner",    lambda: R("text_color_cycle"))
    _btn(g3, "List Saved Styles",     lambda: R("text_list_styles"))
    _btn(g3, "Clear All Text Actors", lambda: R("text_clear_folder"))

    sname_inp = _inp("style name", width=140)
    _btn_inp(g3, "Save Style",
             lambda: R("text_save_style", style_name=sname_inp.text()),
             sname_inp)

    # Generative Text (Voxel)
    g_vox = _group(L, "Generative Text (Voxel)")
    vox_text_inp = _inp("Voxel Text", "UEFN", width=120)
    vox_size_s = _spin(120, 8, 512, width=70)
    _btn_inp(g_vox, "Voxelize Text to 3D Mesh",
             lambda: R("text_voxelize_3d", text=vox_text_inp.text(), font_size=int(vox_size_s.value())),
             vox_text_inp, vox_size_s, tip="Converts a text string into a single StaticMesh asset made of voxel blocks.")
    _btn_inp(g_vox, "Render Text to Texture2D",
             lambda: R("text_render_texture", text=vox_text_inp.text(), font_size=int(vox_size_s.value())),
             vox_text_inp, vox_size_s, tip="Renders text to a transparent Texture2D asset.")

    return scroll


def _tab_assets(R) -> "QScrollArea":
    scroll, L = _page()

    # Naming
    g = _group(L, "Naming Conventions (Epic)")
    _btn(g, "Audit — Dry Run  (no changes)",
         lambda: R("rename_dry_run", scan_path="/Game"),
         "Preview all naming violations without touching anything")
    _btn(g, "Enforce — Apply All Renames",
         lambda: R("rename_enforce_conventions", scan_path="/Game"))
    _btn(g, "Export Naming Report (JSON)",
         lambda: R("rename_report", scan_path="/Game"))

    # LODs
    g2 = _group(L, "LOD Tools")
    _btn(g2, "Auto-Generate LODs — Selection",
         lambda: R("lod_auto_generate_selection"),
         "Generate LODs on the Static Meshes used by selected actors")
    folder_inp = _inp("/Game/Meshes", width=200)
    _btn_inp(g2, "Auto-Generate LODs — Folder",
             lambda: R("lod_auto_generate_folder",
                       folder_path=folder_inp.text() or "/Game/Meshes"),
             folder_inp)
    _btn_inp(g2, "Audit Folder for Missing LODs",
             lambda: R("lod_audit_folder",
                       folder_path=folder_inp.text() or "/Game/Meshes"),
             folder_inp)
    col_combo = QComboBox(); col_combo.addItems(["use_complex", "simple", "no_collision"]); col_combo.setFixedWidth(160)
    _btn_inp(g2, "Set Collision — Folder",
             lambda: R("lod_set_collision_folder",
                       folder_path=folder_inp.text() or "/Game/Meshes",
                       collision=col_combo.currentText()),
             col_combo)

    # Memory
    g3 = _group(L, "Memory Profiler")
    _btn(g3, "Full Scan  (textures + meshes + sounds)",
         lambda: R("memory_scan", scan_path="/Game"))
    _btn(g3, "Scan Textures  (flag >2K)",
         lambda: R("memory_scan_textures", scan_path="/Game"))
    _btn(g3, "Scan Meshes  (flag high-poly)",
         lambda: R("memory_scan_meshes", scan_path="/Game"))
    limit_s = _spin(20, 5, 200, width=70)
    _btn_inp(g3, "Top Offenders",
             lambda: R("memory_top_offenders", limit=int(limit_s.value()),
                       scan_path="/Game"),
             limit_s)
    _btn(g3, "Auto-Fix LODs for Meshes Missing Them",
         lambda: R("memory_autofix_lods", scan_path="/Game"))

    # Master API Sync (Phase 14+)
    g_sync = _group(L, "API Documentation Sync")
    _btn(g_sync, "MASTER SYNC: Level + Verse IQ",
         lambda: R("api_sync_master"),
         "One-click sync: Crawls live actors, parses Verse digests, and updates docs/DEVICE_API_MAP.md.")
    _btn(g_sync, "Sync Individual Level Schema",
         lambda: R("api_crawl_level_classes"),
         "Syncs only the property-level class schema to docs/api_level_classes_schema.json.")

    # Reference Auditor
    g4 = _group(L, "Reference Auditor")
    _btn(g4, "Full Reference Audit Report  (JSON)",
         lambda: R("ref_full_report", scan_path="/Game"))
    _btn(g4, "Find Orphaned Assets",
         lambda: R("ref_audit_orphans", scan_path="/Game"))
    _btn(g4, "Find Redirectors (stale move artifacts)",
         lambda: R("ref_audit_redirectors", scan_path="/Game"))
    _btn(g4, "Find Duplicate Names",
         lambda: R("ref_audit_duplicates", scan_path="/Game"))
    _btn(g4, "Find Unused Textures",
         lambda: R("ref_audit_unused_textures", scan_path="/Game"))
    _btn(g4, "Fix Redirectors — Dry Run first",
         lambda: R("ref_fix_redirectors", scan_path="/Game", dry_run=True))

    # Asset Importers
    g_imp = _group(L, "Asset Importers")
    url_inp = _inp("https://...", width=200)
    _btn_inp(g_imp, "Import Image from URL",
             lambda: R("import_image_from_url", url=url_inp.text()),
             url_inp, tip="Downloads an image directly into the Content Browser.")
    _btn(g_imp, "Import Image from Clipboard",
         lambda: R("import_image_from_clipboard"),
         "Captures the current image sitting on the Windows Clipboard.")

    return scroll


def _tab_verse(R) -> "QScrollArea":
    scroll, L = _page()

    # Devices
    g = _group(L, "Device Inspector")
    _btn(g, "List All Devices in Level",
         lambda: R("verse_list_devices"))
    _btn(g, "Export Device Report (JSON)",
         lambda: R("verse_export_report"))
    
    # Verse Intelligence (Phase 14)
    g_intel = _group(L, "Verse & Build Intelligence")
    _btn(g_intel, "▶  Check Build Errors  (run after Build Verse Code click)",
         lambda: R("verse_patch_errors"),
         "Reads the Verse build log after you click Build Verse Code in the UEFN menu. "
         "Returns every error with file path, line number, and full file content — "
         "paste into Claude to fix and redeploy in one shot.")
    _btn(g_intel, "Compile Verse & Scrape Errors",
         lambda: R("system_build_verse"),
         "Triggers a background UEFN build and returns formatted Verse errors (file/line).")
    _btn(g_intel, "Refresh Class Schema (Digest)",
         lambda: R("api_verse_refresh_schemas"),
         "Scans all .digest.verse files to update the Toolbelt's internal Verse brain.")
    
    class_inp = _inp("trigger_device", width=200)
    _btn_inp(g_intel, "Inspect Verse Class Schema",
             lambda: R("api_verse_get_schema", class_name=class_inp.text()),
             class_inp, tip="Shows properties and events for any Verse class via digest parsing.")

    prop_inp = _inp("property name", "bIsEnabled", width=160)
    val_inp  = _inp("value", "True", width=80)
    _btn_inp(g, "Bulk Set Property — Selection",
             lambda: R("verse_bulk_set_property",
                       property_name=prop_inp.text(),
                       value=val_inp.text()),
             prop_inp, val_inp,
             tip="Set any UPROPERTY on all selected Verse devices")

    name_inp = _inp("label substring", width=140)
    _btn_inp(g, "Select by Label",
             lambda: R("verse_select_by_name", label_substring=name_inp.text()),
             name_inp)

    class_inp = _inp("class name", width=140)
    _btn_inp(g, "Select by Class",
             lambda: R("verse_select_by_class", class_name=class_inp.text()),
             class_inp)

    # Spline → Verse
    g2 = _group(L, "Spline → Verse")
    _btn(g2, "Selected Spline → vector3 Array",
         lambda: R("spline_to_verse_points"),
         "Copies Verse code to the Output Log — paste into your .verse file")
    _btn(g2, "Selected Spline → Patrol AI Skeleton",
         lambda: R("spline_to_verse_patrol"))
    _btn(g2, "Selected Spline → Zone Boundary + IsPointInZone()",
         lambda: R("spline_to_verse_zone_boundary"))
    _btn(g2, "Export Spline Points → JSON",
         lambda: R("spline_export_json"))

    # Code Generation
    g3 = _group(L, "Code Generation")
    _btn(g3, "Generate Game Manager Skeleton",
         lambda: R("verse_gen_game_skeleton"))
    _btn(g3, "@editable Declarations from Selection",
         lambda: R("verse_gen_device_declarations"))
    _btn(g3, "Elimination Event Handler stub",
         lambda: R("verse_gen_elimination_handler"))
    _btn(g3, "Zone Scoring Tracker stub",
         lambda: R("verse_gen_scoring_tracker"))
    _btn(g3, "Trigger Prop Spawner stub",
         lambda: R("verse_gen_prop_spawner"))

    # Snippet Library
    g4 = _group(L, "Snippet Library")

    hint = QLabel(
        "Generated snippets are saved to  Saved/UEFN_Toolbelt/snippets/\n"
        "organized into:  game_systems/  device_wiring/  spline_tools/  custom/\n"
        "Click Refresh to browse. Click any snippet to copy it to the clipboard."
    )
    hint.setStyleSheet(f"font-size: 10px; color: {_color('muted')}; padding: 4px;")
    hint.setWordWrap(True)
    g4.addWidget(hint)

    snippet_list = QVBoxLayout()
    snippet_list.setSpacing(2)
    snippet_list_widget = QWidget()
    snippet_list_widget.setLayout(snippet_list)
    g4.addWidget(snippet_list_widget)

    def _refresh_snippets():
        # Clear old entries
        while snippet_list.count():
            item = snippet_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        import unreal as _unreal
        snippets_dir = _unreal.Paths.project_saved_dir().replace("\\", "/")
        snippets_dir = snippets_dir.rstrip("/") + "/UEFN_Toolbelt/snippets"

        if not os.path.isdir(snippets_dir):
            lbl = QLabel("  No snippets yet — generate one above first.")
            lbl.setStyleSheet(f"color: {_color('muted')}; padding: 6px; font-size: 11px;")
            snippet_list.addWidget(lbl)
            return

        found = 0
        for subcat in sorted(os.listdir(snippets_dir)):
            subdir = os.path.join(snippets_dir, subcat)
            if not os.path.isdir(subdir):
                continue
            files = [f for f in sorted(os.listdir(subdir)) if f.endswith(".verse")]
            if not files:
                continue

            cat_lbl = QLabel(f"  {subcat}/")
            cat_lbl.setStyleSheet(
                f"font-size: 10px; color: {_color('muted')}; letter-spacing: 1px;"
                " padding: 6px 4px 2px 4px; font-weight: bold;"
            )
            snippet_list.addWidget(cat_lbl)

            for fname in files:
                fpath = os.path.join(subdir, fname)
                size  = os.path.getsize(fpath)
                row   = QWidget()
                rl    = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(4)

                name_btn = QPushButton(f"  {fname}  ({size} bytes)")
                name_btn.setStyleSheet(
                    f"QPushButton {{ text-align: left; background: {_color('card')};"
                    f" border: 1px solid {_color('border')}; color: {_color('text_dim')}; font-size: 11px;"
                    " padding: 5px 8px; border-radius: 3px; }"
                    f"QPushButton:hover {{ background: #252525; color: {_color('text')}; }}"
                )
                def _copy(p=fpath):
                    try:
                        with open(p, "r") as fh:
                            QApplication.clipboard().setText(fh.read())
                    except Exception as e:
                        pass
                name_btn.clicked.connect(_copy)
                name_btn.setToolTip("Click to copy to clipboard")

                open_btn = QPushButton("Open")
                open_btn.setFixedWidth(52)
                open_btn.setStyleSheet(
                    f"QPushButton {{ background: {_color('grid')}; border: 1px solid {_color('border')};"
                    f" color: {_color('muted')}; padding: 4px; font-size: 10px; border-radius: 3px; }}"
                    f"QPushButton:hover {{ color: {_color('text_dim')}; }}"
                )
                def _open(p=fpath):
                    import subprocess
                    subprocess.Popen(["notepad", os.path.normpath(p)])
                open_btn.clicked.connect(_open)

                rl.addWidget(name_btn, stretch=1)
                rl.addWidget(open_btn)
                snippet_list.addWidget(row)
                found += 1

        if found == 0:
            lbl = QLabel("  No .verse files found yet.")
            lbl.setStyleSheet(f"color: {_color('muted')}; padding: 6px; font-size: 11px;")
            snippet_list.addWidget(lbl)

    btn_row = QWidget()
    btn_rl  = QHBoxLayout(btn_row)
    btn_rl.setContentsMargins(0, 0, 0, 0)
    btn_rl.setSpacing(6)
    refresh_btn = QPushButton("Refresh Library")
    refresh_btn.clicked.connect(_refresh_snippets)
    explore_btn = QPushButton("Open Folder")
    explore_btn.clicked.connect(lambda: R("verse_open_snippets_folder"))
    btn_rl.addWidget(refresh_btn)
    btn_rl.addWidget(explore_btn)
    g4.insertWidget(1, btn_row)  # insert above the snippet list

    return scroll


def _tab_project(R) -> "QScrollArea":
    scroll, L = _page()

    # Scaffold
    g = _group(L, "Project Scaffold")
    proj_inp = _inp("MyProject", "MyProject", width=160)
    g.addWidget(QLabel("Project name:"))
    g.addWidget(proj_inp)

    def _pname(): return proj_inp.text() or "MyProject"

    _grid_btns(g, [
        ("Standard",    lambda: R("scaffold_generate", template="uefn_standard",    project_name=_pname())),
        ("Competitive", lambda: R("scaffold_generate", template="competitive_map",  project_name=_pname())),
        ("Solo Dev",    lambda: R("scaffold_generate", template="solo_dev",         project_name=_pname())),
        ("Verse-Heavy", lambda: R("scaffold_generate", template="verse_heavy",      project_name=_pname())),
    ], cols=2)
    _btn(g, "Preview Scaffold (dry run)",
         lambda: R("scaffold_preview", template="uefn_standard", project_name=_pname()))
    _btn(g, "List Templates",
         lambda: R("scaffold_list_templates"))
    _btn(g, "Organize Loose Assets (dry run)",
         lambda: R("scaffold_organize_loose", project_name=_pname(), dry_run=True))

    # Level Snapshot
    g2 = _group(L, "Level Snapshots")
    snap_inp = _inp("snapshot name", width=180)
    g2.addWidget(snap_inp)
    _row(g2,
         ("Save Whole Level",  lambda: R("snapshot_save", name=snap_inp.text())),
         ("Save Selection",    lambda: R("snapshot_save", name=snap_inp.text(), scope="selection")),
    )
    _btn(g2, "List All Snapshots",
         lambda: R("snapshot_list"))
    restore_inp = _inp("snapshot name to restore", width=180)
    _btn_inp(g2, "Restore Snapshot",
             lambda: R("snapshot_restore", name=restore_inp.text()),
             restore_inp)
    compare_inp = _inp("baseline snapshot name", width=180)
    _btn_inp(g2, "What Changed vs Saved?",
             lambda: R("snapshot_compare_live", name=compare_inp.text()),
             compare_inp,
             tip="Compare a saved snapshot against the current live level")

    diff_a = _inp("snapshot A", width=110)
    diff_b = _inp("snapshot B", width=110)
    _btn_inp(g2, "Diff Two Snapshots",
             lambda: R("snapshot_diff", name_a=diff_a.text(), name_b=diff_b.text()),
             diff_a, diff_b)

    # Smart Import
    g3 = _group(L, "Smart Import")
    fbx_inp = _inp("FBX file path or folder", width=260)
    g3.addWidget(fbx_inp)
    _row(g3,
         ("Import File",   lambda: R("import_fbx",        fbx_path=fbx_inp.text())),
         ("Import Folder", lambda: R("import_fbx_folder", folder_path=fbx_inp.text())),
         ("Organize",      lambda: R("organize_assets",   source_path=fbx_inp.text() or "/Game/Imports")),
    )

    return scroll


def _tab_screenshot(R) -> "QScrollArea":
    scroll, L = _page()

    # Quick shots
    g = _group(L, "Capture Viewport")
    w_s = _spin(1920, 320, 7680, width=90)
    h_s = _spin(1080, 180, 4320, width=90)
    row = QWidget(); rh = QHBoxLayout(row); rh.setContentsMargins(0, 0, 0, 0); rh.setSpacing(4)
    rh.addWidget(QLabel("W:")); rh.addWidget(w_s)
    rh.addWidget(QLabel("H:")); rh.addWidget(h_s); rh.addStretch()
    g.addWidget(row)

    name_inp = _inp("viewport", "viewport", width=140)
    _btn_inp(g, "Capture Viewport",
             lambda: R("screenshot_take",
                       name=name_inp.text() or "viewport",
                       width=int(w_s.value()),
                       height=int(h_s.value())),
             name_inp, tip="Save current viewport to Saved/UEFN_Toolbelt/screenshots/")

    hdr_chk = QCheckBox("HDR (16-bit EXR alongside PNG)")
    g.addWidget(hdr_chk)
    game_chk = QCheckBox("Force game view (hide editor gizmos)")
    g.addWidget(game_chk)
    _btn(g, "Capture  (with HDR / game view settings)",
         lambda: R("screenshot_take",
                   name=name_inp.text() or "viewport",
                   width=int(w_s.value()),
                   height=int(h_s.value()),
                   capture_hdr=hdr_chk.isChecked(),
                   force_game_view=game_chk.isChecked()))

    _row(g,
         ("1080p", lambda: R("screenshot_take", width=1920,  height=1080,  name="1080p")),
         ("2K",    lambda: R("screenshot_take", width=2560,  height=1440,  name="2K")),
         ("4K",    lambda: R("screenshot_take", width=3840,  height=2160,  name="4K")),
    )

    # Selection focus
    g2 = _group(L, "Frame Selection")
    fov_s = _spin(60, 10, 120, width=70)
    restore_chk = QCheckBox("Restore camera after capture")
    restore_chk.setChecked(True)
    row2 = QWidget(); rh2 = QHBoxLayout(row2); rh2.setContentsMargins(0, 0, 0, 0); rh2.setSpacing(4)
    rh2.addWidget(QLabel("FOV °:")); rh2.addWidget(fov_s); rh2.addStretch()
    g2.addWidget(row2)
    g2.addWidget(restore_chk)
    sel_name = _inp("selection", "selection", width=140)
    _btn_inp(g2, "Frame & Capture Selection",
             lambda: R("screenshot_focus_selection",
                       name=sel_name.text() or "selection",
                       width=int(w_s.value()),
                       height=int(h_s.value()),
                       fov_deg=fov_s.value(),
                       restore_camera=restore_chk.isChecked()),
             sel_name,
             tip="Auto-frames all selected actors, captures, optionally restores camera")

    # Series
    g3 = _group(L, "Timed Series")
    count_s   = _spin(3, 1, 50, width=70)
    delay_s   = _spin(2.0, 0.0, 60.0, decimals=1, width=80)
    series_nm = _inp("series", "series", width=130)
    row3 = QWidget(); rh3 = QHBoxLayout(row3); rh3.setContentsMargins(0, 0, 0, 0); rh3.setSpacing(4)
    rh3.addWidget(QLabel("Count:")); rh3.addWidget(count_s)
    rh3.addWidget(QLabel("Delay s:")); rh3.addWidget(delay_s); rh3.addStretch()
    g3.addWidget(row3)
    _btn_inp(g3, "Start Series",
             lambda: R("screenshot_timed_series",
                       name=series_nm.text() or "series",
                       count=int(count_s.value()),
                       width=int(w_s.value()),
                       height=int(h_s.value()),
                       interval_sec=delay_s.value()),
             series_nm,
             tip="Take N screenshots with a delay between each")

    # Folder
    g4 = _group(L, "Output")
    _btn(g4, "Show Output Folder Path",
         lambda: R("screenshot_open_folder"),
         "Print the screenshots folder path to the Output Log")

    return scroll


def _tab_tags(R) -> "QScrollArea":
    scroll, L = _page()

    # Apply tags
    g = _group(L, "Tag Selected Assets (Content Browser)")
    tag_inp = _inp("tag name", width=140)
    val_inp = _inp("value (default: 1)", "1", width=100)
    row1 = QWidget(); rh1 = QHBoxLayout(row1); rh1.setContentsMargins(0, 0, 0, 0); rh1.setSpacing(4)
    rh1.addWidget(QLabel("Tag:")); rh1.addWidget(tag_inp)
    rh1.addWidget(QLabel("Value:")); rh1.addWidget(val_inp); rh1.addStretch()
    g.addWidget(row1)
    _row(g,
         ("Add Tag",    lambda: R("tag_add",
                                  tag_name=tag_inp.text(),
                                  value=val_inp.text() or "1")),
         ("Remove Tag", lambda: R("tag_remove",
                                  tag_name=tag_inp.text())),
         ("Show Tags",  lambda: R("tag_show")),
    )

    # Search
    g2 = _group(L, "Search Assets by Tag")
    stag_inp  = _inp("tag name", width=140)
    sval_inp  = _inp("value", "1", width=80)
    sfold_inp = _inp("/Game", "/Game", width=160)
    row2 = QWidget(); rh2 = QHBoxLayout(row2); rh2.setContentsMargins(0, 0, 0, 0); rh2.setSpacing(4)
    rh2.addWidget(QLabel("Tag:")); rh2.addWidget(stag_inp)
    rh2.addWidget(QLabel("Value:")); rh2.addWidget(sval_inp); rh2.addStretch()
    g2.addWidget(row2)
    g2.addWidget(QLabel("  Folder:"))
    g2.addWidget(sfold_inp)
    _btn(g2, "Search",
         lambda: R("tag_search",
                   tag_name=stag_inp.text(),
                   value=sval_inp.text() or "1",
                   folder=sfold_inp.text() or "/Game"),
         "Find all assets matching this tag + value in the folder")

    # List / export
    g3 = _group(L, "Inventory")
    fold_inp = _inp("/Game", "/Game", width=200)
    g3.addWidget(fold_inp)
    _row(g3,
         ("List All Tags",  lambda: R("tag_list_all",
                                      folder=fold_inp.text() or "/Game")),
         ("Export to JSON", lambda: R("tag_export",
                                      folder=fold_inp.text() or "/Game")),
    )

    return scroll


def _tab_api(R) -> "QScrollArea":
    scroll, L = _page()

    g = _group(L, "Search & Inspect")
    q_inp = _inp("class or function name…", width=220)
    _btn_inp(g, "Search  unreal.*",
             lambda: R("api_search", query=q_inp.text()),
             q_inp)

    inspect_inp = _inp("class name", "EditorActorSubsystem", width=200)
    _btn_inp(g, "Inspect",
             lambda: R("api_inspect", name=inspect_inp.text()),
             inspect_inp)

    _btn(g, "List All Subsystems",
         lambda: R("api_list_subsystems"),
         "Print every *Subsystem class in this UEFN build")

    g2 = _group(L, "Stub Generator  (.pyi)")
    _btn(g2, "Export Full  unreal.pyi  (IDE autocomplete)",
         lambda: R("api_export_full"),
         "Writes Saved/UEFN_Toolbelt/stubs/unreal.pyi — no more red squiggles")

    stub_cls_inp = _inp("ClassName", width=180)
    _btn_inp(g2, "Stub Single Class",
             lambda: R("api_generate_stubs", class_name=stub_cls_inp.text()),
             stub_cls_inp)

    g3 = _group(L, "Kirch API Dump")
    lbl = QLabel(
        "  For the authoritative 37K-type dump, use Kirch's companion scripts:\n"
        "  dump_uefn_api.py → generate_uefn_stub.py\n"
        "  github.com/KirChuvakov/uefn-mcp-server"
    )
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {_color('muted')}; font-size: 11px; padding: 4px;")
    g3.addWidget(lbl)
    _btn(g3, "Open Output Log (check stub export path)",
         lambda: unreal.log(
             "[API] Stubs written to: "
             + __import__("os").path.join(
                 __import__("unreal").Paths.project_saved_dir(),
                 "UEFN_Toolbelt", "stubs"
             )
         ))

    return scroll


# ─── MCP tab ─────────────────────────────────────────────────────────────────

def _tab_mcp(R) -> "QScrollArea":
    """MCP Bridge tab — start/stop/status, connection info, quick tool runner."""
    scroll, L = _page()

    # ── Live status indicator ──────────────────────────────────────────────
    def _read_mcp_state():
        try:
            from UEFN_Toolbelt.tools import mcp_bridge as _mcpb
            port = getattr(_mcpb, "_bound_port", 0)
            if port and port > 0:
                return "running", f"● RUNNING  —  port {port}  —  Claude Code is connected"
            else:
                return "stopped", "● NOT RUNNING  —  click Start to enable AI control"
        except Exception:
            return "stopped", "● NOT RUNNING"

    status_lbl = QLabel()
    status_lbl.setContentsMargins(4, 10, 4, 6)

    def _refresh_status():
        state, text = _read_mcp_state()
        col = _color("ok") if state == "running" else "#FF5555"
        status_lbl.setText(text)
        status_lbl.setStyleSheet(
            f"color: {col}; font-size: 13px; font-weight: bold;"
            f" background: #141414; padding: 10px 14px; border-radius: 4px;"
            f" border: 1px solid {_color('border')};"
        )

    _refresh_status()
    L.addWidget(status_lbl)

    # Expose refresh fn so _select_category can call it on tab navigation
    status_lbl.setProperty("mcp_refresh_fn", _refresh_status)

    # ── Status & controls ─────────────────────────────────────────────────
    g = _group(L, "Listener Controls")

    def _start():
        R("mcp_start")
        _refresh_status()

    def _stop():
        R("mcp_stop")
        _refresh_status()

    def _restart():
        R("mcp_restart")
        _refresh_status()

    _btn(g, "▶  Start Listener",
         _start,
         "Start the HTTP listener so Claude Code can control UEFN directly")

    _btn(g, "■  Stop Listener",
         _stop,
         "Stop the MCP HTTP listener")

    _btn(g, "↺  Restart Listener",
         _restart,
         "Restart after hot-reload or port conflict")

    _btn(g, "↺  Refresh Status",
         _refresh_status,
         "Re-read the bridge state and update the status indicator above")

    _btn(g, "📡  Print Status to Log",
         lambda: R("mcp_status"),
         "Print port, running state, and command count to Output Log")

    # ── Tool runner ───────────────────────────────────────────────────────
    g2 = _group(L, "Run Any Toolbelt Tool")
    tool_inp = _inp("tool_name  (e.g. material_apply_preset)", width=220)
    kwargs_inp = _inp('kwargs JSON  (e.g. {"preset":"chrome"})', width=220)
    g2.addWidget(tool_inp)
    g2.addWidget(kwargs_inp)

    def _run_tool():
        import json as _json
        name = tool_inp.text().strip()
        if not name:
            unreal.log_warning("[MCP Dashboard] Enter a tool name")
            return
        raw = kwargs_inp.text().strip()
        kw = _json.loads(raw) if raw else {}
        R(name, **kw)

    _btn(g2, "Run Tool via MCP Bridge",
         _run_tool,
         "Calls the tool through mcp_bridge.run_tool so you can test the bridge")

    # ── Setup info ────────────────────────────────────────────────────────
    g3 = _group(L, "Claude Code Setup (.mcp.json)")
    info = QLabel(
        "1. Click Start Listener above\n"
        "2. Place mcp_server.py next to .mcp.json in this repo\n"
        "3. Add to .mcp.json:\n"
        '   {"mcpServers": {"uefn-toolbelt":\n'
        '     {"command": "python",\n'
        '      "args": ["<path>/mcp_server.py"]}}}\n'
        "4. Restart Claude Code — it auto-connects\n\n"
        "Claude can then run all 291 tools, spawn/move actors,\n"
        "write Verse code, and read your level — without leaving\n"
        "the conversation.\n\n"
        "When done: click ■ Stop Listener above, or run\n"
        "tb.run(\"mcp_stop\") in the Python console.\n"
        "This closes the port until you need it again."
    )
    info.setWordWrap(True)
    info.setStyleSheet("color: #888888; font-size: 11px; padding: 4px;")
    g3.addWidget(info)

    return scroll


def _tab_verification(R) -> "QScrollArea":
    """Automated testing and verification tab."""
    scroll, L = _page()

    g = _group(L, "Automated Verification")

    _btn(g, "Run Smoke Test (Registry + Layer 3)",
         lambda: R("toolbelt_smoke_test"),
         "Verifies 123 tools register and 9 'safe' tools execute. Safe for any level.")

    _sep(L)

    # Big scary WARNING label
    warn_lbl = QLabel("⚠️  WARNING: INVASIVE INTEGRATION TEST")
    warn_lbl.setStyleSheet(f"color: {_color('error')}; font-weight: bold; font-size: 13px; padding-top: 10px;")
    L.addWidget(warn_lbl)

    desc_lbl = QLabel(
        "The Integration Test (90/90 passed) is invasive. It programmatically spawns actors, "
        "modifies materials, and manages assets to achieve 100% verification.\n\n"
        "RUN IN VACANT TEST TEMPLATES ONLY. DO NOT RUN IN PRODUCTION MAPS."
    )
    desc_lbl.setStyleSheet("color: #FF8888; font-size: 11px; padding: 4px 0 10px 0;")
    desc_lbl.setWordWrap(True)
    L.addWidget(desc_lbl)

    _btn(L, "Run Full Integration Test (123 Tools)",
         lambda: R("toolbelt_integration_test"),
         "Executes 90 section-tests across all tool categories. Verified 2026-03-21.")

    L.addStretch()
    return scroll


# ─── Window icon (programmatic hexagon) ───────────────────────────────────────

def _make_icon() -> "QIcon":
    """Canonical TB icon — delegates to core/base_window so there's one source."""
    from .core.base_window import make_toolbelt_icon
    return make_toolbelt_icon()


# ─── Plugin Hub ───────────────────────────────────────────────────────────────

def _tab_plugin_hub(R) -> "QScrollArea":
    import os, json
    scroll, L = _page()

    # ── Header
    hero = QLabel("Plugin Ecosystem")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    desc = QLabel("Discover and run third-party tools installed in your Custom_Plugins directory.")
    desc.setStyleSheet(f"font-size: 12px; color: {_color('text_dim')}; padding-bottom: 12px;")
    desc.setWordWrap(True)
    L.addWidget(desc)

    # ── Open Folder Button
    btn_open = QPushButton("  Open Plugins Folder")
    btn_open.setProperty("accent", "true")
    btn_open.setStyleSheet(btn_open.styleSheet() + "QPushButton { padding: 8px; font-weight: bold; text-align: center; }")
    def open_plugins_folder():
        folder = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "Custom_Plugins")
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
    btn_open.clicked.connect(open_plugins_folder)
    L.addWidget(btn_open)

    _sep(L)

    # ── Online Plugin Hub ──────────────────────────────────────────────────────
    _REGISTRY_URL = (
        "https://raw.githubusercontent.com/undergroundrap/UEFN-TOOLBELT/main/registry.json"
    )

    hub_header = QLabel("Browse Online Hub")
    hub_header.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {_color('text_bright')}; padding: 4px 0 2px 0;")
    L.addWidget(hub_header)

    hub_desc = QLabel("Community plugins — click Install to download into your Custom_Plugins folder.")
    hub_desc.setStyleSheet(f"font-size: 11px; color: {_color('text_dim')}; padding-bottom: 8px;")
    hub_desc.setWordWrap(True)
    L.addWidget(hub_desc)

    # Status label updated by the fetch
    hub_status = QLabel("Click 'Refresh' to load the community registry.")
    hub_status.setStyleSheet("font-size: 11px; color: #777777; font-style: italic;")
    L.addWidget(hub_status)

    # Container for online cards — populated on refresh
    hub_container = QWidget()
    hub_container.setStyleSheet("background: transparent;")
    hub_vbox = QVBoxLayout(hub_container)
    hub_vbox.setContentsMargins(0, 0, 0, 0)
    hub_vbox.setSpacing(6)
    L.addWidget(hub_container)

    def _install_plugin(plugin_meta: dict):
        """Download a plugin from download_url into Custom_Plugins."""
        import urllib.request
        dl_url = plugin_meta.get("download_url", "")
        if not dl_url:
            hub_status.setText("⚠ No download URL for this plugin.")
            return
        plugin_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "Custom_Plugins")
        os.makedirs(plugin_dir, exist_ok=True)
        dest = os.path.join(plugin_dir, f"{plugin_meta['id']}.py")
        try:
            urllib.request.urlretrieve(dl_url, dest)
            hub_status.setText(f"✓ Installed '{plugin_meta['name']}' → restart UEFN to activate.")
        except Exception as ex:
            hub_status.setText(f"✗ Install failed: {ex}")

    def _make_online_card(pm: dict):
        is_core = pm.get("type", "community") == "core"
        border_color = "#336633" if is_core else "#363666"
        bg_color     = "#0F1F0F" if is_core else "#1A1A2E"

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {bg_color}; border: 1px solid {border_color};"
            f" border-radius: 6px; margin-bottom: 6px; }}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(4)

        # Title row
        hdr = QWidget()
        hdr.setStyleSheet("border: none; background: transparent;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 0, 0)

        t = QLabel(pm["name"])
        t.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {_color('text_bright')};")
        hl.addWidget(t)

        v = QLabel(f"v{pm['version']}")
        v.setStyleSheet("font-size: 11px; color: #8888AA;")
        hl.addWidget(v)

        cat = QLabel(pm.get("category", ""))
        cat.setStyleSheet(
            "font-size: 10px; color: #44AAFF; background: #0A1A2E;"
            " border: 1px solid #225588; border-radius: 3px; padding: 2px 6px;"
        )
        hl.addWidget(cat)

        if is_core:
            core_badge = QLabel("BUILT-IN")
            core_badge.setStyleSheet(
                f"font-size: 10px; color: {_color('ok')}; background: #0F3320;"
                f" border: 1px solid {_color('ok')}; border-radius: 3px; padding: 2px 6px; font-weight: bold;"
            )
            hl.addWidget(core_badge)

            tool_count = pm.get("tool_count")
            if tool_count:
                tc_badge = QLabel(f"{tool_count} tools")
                tc_badge.setStyleSheet(
                    f"font-size: 10px; color: {_color('text_dim')}; background: #222222;"
                    " border: 1px solid #444444; border-radius: 3px; padding: 2px 6px;"
                )
                hl.addWidget(tc_badge)

        hl.addStretch()
        cl.addWidget(hdr)

        # Author line — link if author_url present
        author = pm.get("author", "?")
        author_url = pm.get("author_url", "")
        size_kb = pm.get("size_kb", "?")
        if author_url:
            by_text = f'By <a href="{author_url}" style="color: #6688DD;">{author}</a>  ·  {size_kb} KB'
            by = QLabel(by_text)
            by.setOpenExternalLinks(True)
        else:
            by = QLabel(f"By {author}  ·  {size_kb} KB")
        by.setStyleSheet("font-size: 10px; color: #888888; border: none; background: transparent;")
        cl.addWidget(by)

        d = QLabel(pm.get("description", ""))
        d.setWordWrap(True)
        d.setStyleSheet(
            f"font-size: 12px; color: {_color('text')}; padding: 4px 0; border: none; background: transparent;"
        )
        cl.addWidget(d)

        footer = QWidget()
        footer.setStyleSheet("border: none; background: transparent;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(0, 4, 0, 0)

        if pm.get("url"):
            link = QLabel(f'<a href="{pm["url"]}" style="color: #6688DD;">View Source</a>')
            link.setOpenExternalLinks(True)
            link.setStyleSheet("font-size: 11px; border: none; background: transparent;")
            fl.addWidget(link)

        fl.addStretch()

        if not is_core:
            install_btn = QPushButton("Install")
            install_btn.setStyleSheet(
                f"QPushButton {{ background: #1A3322; border: 1px solid {_color('ok')}; color: {_color('ok')};"
                " padding: 4px 14px; border-radius: 3px; font-weight: bold; }"
                f"QPushButton:hover {{ background: #2A4A33; }}"
                f"QPushButton:pressed {{ background: {_color('ok')}; color: #000000; }}"
            )
            install_btn.clicked.connect(lambda _, p=pm: _install_plugin(p))
            fl.addWidget(install_btn)

        cl.addWidget(footer)
        return card

    # Cache for search filtering
    _all_plugins = []

    def _build_hub_cards(query: str = ""):
        while hub_vbox.count():
            item = hub_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        q = query.strip().lower()
        def _matches(pm):
            if not q:
                return True
            return (
                q in pm.get("name", "").lower() or
                q in pm.get("category", "").lower() or
                q in pm.get("description", "").lower() or
                any(q in t.lower() for t in pm.get("tags", []))
            )

        core      = [p for p in _all_plugins if p.get("type") == "core"      and _matches(p)]
        community = [p for p in _all_plugins if p.get("type") != "core"      and _matches(p)]
        total     = len(core) + len(community)

        if not total and q:
            no_result = QLabel(f'No results for "{q}"')
            no_result.setStyleSheet("color: #777777; font-style: italic; padding: 12px 0;")
            hub_vbox.addWidget(no_result)
            return

        if core:
            core_hdr = QLabel("Core Tools  —  Built into UEFN Toolbelt by Ocean Bennett")
            core_hdr.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {_color('ok')}; padding: 8px 0 4px 0;")
            hub_vbox.addWidget(core_hdr)
            for pm in core:
                hub_vbox.addWidget(_make_online_card(pm))

        if community:
            comm_hdr = QLabel("Community Plugins  —  Third-party tools")
            comm_hdr.setStyleSheet("font-size: 12px; font-weight: bold; color: #44AAFF; padding: 8px 0 4px 0;")
            hub_vbox.addWidget(comm_hdr)
            for pm in community:
                hub_vbox.addWidget(_make_online_card(pm))

    def _refresh_hub():
        import urllib.request, time
        nonlocal _all_plugins
        hub_status.setText("Fetching registry…")
        hub_search.setEnabled(False)
        try:
            bust_url = f"{_REGISTRY_URL}?t={int(time.time())}"
            req = urllib.request.Request(bust_url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            _all_plugins = data.get("plugins", [])
            core_count = sum(1 for p in _all_plugins if p.get("type") == "core")
            comm_count = sum(1 for p in _all_plugins if p.get("type") != "core")
            hub_status.setText(
                f"✓ {core_count} core tools · {comm_count} community plugins"
                f" · updated {data.get('updated','?')}"
            )
            hub_search.setEnabled(True)
            _build_hub_cards(hub_search.text())
        except Exception as ex:
            hub_status.setText(f"⚠ Could not reach registry: {ex}")

    # Search bar
    hub_search = QLineEdit()
    hub_search.setPlaceholderText("Filter Plugin Hub...")
    hub_search.setStyleSheet(
        f"QLineEdit {{ background: {_color('panel')}; border: 1px solid {_color('border2')}; color: {_color('text')};"
        " padding: 6px 10px; border-radius: 4px; font-size: 12px; }"
        "QLineEdit:focus { border-color: #3A3AFF; }"
    )
    hub_search.setEnabled(False)
    hub_search.textChanged.connect(_build_hub_cards)

    btn_refresh = QPushButton("  Refresh Hub")
    btn_refresh.setStyleSheet(
        f"QPushButton {{ background: #2D2D2D; border: 1px solid {_color('muted')}; color: #DDDDDD;"
        " padding: 6px 16px; border-radius: 4px; font-weight: bold; }"
        f"QPushButton:hover {{ background: #3A3AFF; border-color: #5555FF; color: {_color('text_bright')}; }}"
    )
    btn_refresh.clicked.connect(_refresh_hub)

    search_row = QWidget()
    search_row.setStyleSheet("background: transparent;")
    sr_layout = QHBoxLayout(search_row)
    sr_layout.setContentsMargins(0, 0, 0, 0)
    sr_layout.addWidget(hub_search)
    sr_layout.addWidget(btn_refresh)
    L.addWidget(search_row)
    L.addWidget(hub_container)

    _sep(L)

    # ── Load Audit Log
    audit_data = {}
    audit_path = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "plugin_audit.json")
    if os.path.exists(audit_path):
        try:
            with open(audit_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for p in data.get("plugins", []):
                    audit_data[p.get("plugin")] = p
        except Exception:
            pass

    # ── List Custom Plugins
    from UEFN_Toolbelt.registry import get_registry
    reg = get_registry()

    custom_entries = []
    for entry in reg._tools.values():
        source_path = entry.source.replace("\\", "/")
        if "Custom_Plugins" in source_path:
            custom_entries.append(entry)

    if not custom_entries:
        lbl = QLabel("No custom plugins installed.\nDrop Python scripts into the Custom_Plugins folder to see them here.")
        lbl.setStyleSheet("color: #777777; font-style: italic; padding: 20px 0;")
        lbl.setAlignment(Qt.AlignCenter)
        L.addWidget(lbl)
        L.addStretch()
        return scroll

    g_plugins = _group(L, "Installed Plugins")

    for entry in sorted(custom_entries, key=lambda e: e.name):
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {_color('panel')}; border: 1px solid {_color('border2')}; border-radius: 6px; margin-bottom: 6px; }}")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 12, 12, 12)
        c_layout.setSpacing(6)

        # Header: Name + Version
        header = QWidget()
        header.setStyleSheet("border: none; background: transparent;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(entry.name)
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {_color('text_bright')};")
        h_layout.addWidget(title)

        version = QLabel(f"v{entry.version}")
        version.setStyleSheet("font-size: 11px; color: #8888AA; font-weight: bold;")
        h_layout.addWidget(version)
        h_layout.addStretch()

        c_layout.addWidget(header)

        # Meta
        meta_str = []
        if entry.author: meta_str.append(f"By: {entry.author}")
        if entry.last_updated: meta_str.append(f"Updated: {entry.last_updated}")
        if meta_str:
            meta = QLabel("  |  ".join(meta_str))
            meta.setStyleSheet(f"font-size: 11px; color: {_color('text_dim')}; border: none; background: transparent;")
            c_layout.addWidget(meta)

        if entry.url:
            url_link = QLabel(f'<a href="{entry.url}" style="color: #6666DD;">{entry.url}</a>')
            url_link.setOpenExternalLinks(True)
            url_link.setStyleSheet("font-size: 11px; border: none; background: transparent;")
            c_layout.addWidget(url_link)

        # Description
        desc_lbl = QLabel(entry.description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 12px; color: #DDDDDD; padding: 4px 0; border: none; background: transparent;")
        c_layout.addWidget(desc_lbl)

        # Security Footer
        footer = QWidget()
        footer.setStyleSheet("border: none; background: transparent;")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(0, 4, 0, 0)
        f_layout.setSpacing(6)

        module_name = os.path.splitext(os.path.basename(entry.source))[0]
        audit_info = audit_data.get(module_name, {})

        def _badge(text, ok=True):
            b = QLabel(text)
            color = _color("ok") if ok else "#FFAAAA"
            bg = "#1A3322" if ok else "#331A1A"
            b.setStyleSheet(f"color: {color}; background: {bg}; border: 1px solid {color}; border-radius: 3px; padding: 3px 6px; font-size: 10px; font-weight: bold;")
            return b

        if audit_info:
            f_layout.addWidget(_badge("✓ AST Clean"))
            if "sha256" in audit_info:
                f_layout.addWidget(_badge("✓ SHA-256 Validated"))
            size = audit_info.get("size_kb", 0)
            f_layout.addWidget(_badge(f"Size: {size} KB"))
        else:
            f_layout.addWidget(_badge("No Audit Data", False))

        f_layout.addStretch()

        # Action button
        run_btn = QPushButton("Run Tool")
        run_btn.setStyleSheet(
            f"QPushButton {{ background: #2D2D2D; border: 1px solid #444444; color: {_color('text_bright')};"
            " padding: 4px 12px; border-radius: 3px; font-weight: bold; margin-left: 10px; }"
            "QPushButton:hover { background: #3A3AFF; border-color: #5555FF; }"
            "QPushButton:pressed { background: #5555FF; }"
        )
        run_btn.clicked.connect(lambda _, n=entry.name: R(n))
        f_layout.addWidget(run_btn)

        c_layout.addWidget(footer)
        g_plugins.addWidget(card)

    L.addStretch()
    return scroll


def _tab_measurement(R) -> "QScrollArea":
    scroll, L = _page()

    # Distance
    g_dist = _group(L, "Math & Measurement")
    _btn(g_dist, "Measure Distance (Chain Selection)", lambda: R("measure_distance"), 
         "Calculates the total 3D distance between a chain of selected actors.")
    
    speed_combo = QComboBox()
    speed_combo.addItems(["Walk", "Run", "Sprint"])
    speed_combo.setFixedWidth(120)
    _btn_inp(g_dist, "Measure Travel Time", 
             lambda: R("measure_travel_time", speed_type=speed_combo.currentText()), 
             speed_combo, tip="Estimates travel time in seconds between points at specific Fortnite speeds.")

    # Spline
    g_spline = _group(L, "Spline Analysis")
    _btn(g_spline, "Measure Spline Length", lambda: R("spline_measure"), 
         "Calculates the precise world-space length of the selected spline.")

    return scroll


def _tab_localization(R) -> "QScrollArea":
    scroll, L = _page()

    # Export
    g_exp = _group(L, "Localization Export")
    fmt_combo = QComboBox()
    fmt_combo.addItems(["json", "csv"])
    fmt_combo.setFixedWidth(100)
    _btn_inp(g_exp, "Export Text Manifest", 
             lambda: R("text_export_manifest", format=fmt_combo.currentText()), 
             fmt_combo, tip="Harvests all level text and exports it to Saved/UEFN_Toolbelt/localization/")

    _btn(g_exp, "Open Export Folder", 
         lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "localization"))),
         "Opens the directory where translation manifests are saved.")

    # Import
    g_imp = _group(L, "Localization Import")
    path_inp = _inp("path/to/translated.json", width=260)
    L.addWidget(QLabel("  Manifest JSON Path:"))
    L.addWidget(path_inp)
    _btn(g_imp, "Apply Translations from Manifest", 
         lambda: R("text_apply_translation", manifest_path=path_inp.text()), 
         "Reads a translated manifest and updates all matching actors in the level.")

    return scroll

def _tab_selection(R) -> "QScrollArea":
    scroll, L = _page()
    hero = QLabel("Advanced Selection")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)
    
    g = _group(L, "Proximity & Filtering")
    
    rad_s = _spin(1000, 10, 50000, width=100)
    cls_inp = _inp("StaticMeshActor", "StaticMeshActor", width=160)
    _btn_inp(g, "Select in Radius", 
             lambda: R("select_in_radius", radius=rad_s.value(), actor_class_name=cls_inp.text()), 
             rad_s, cls_inp, tip="Selects all actors of a specific class within a radius of the current selection.")
    
    prop_inp = _inp("Actor Label", "Actor Label", width=120)
    val_inp = _inp("Value", "", width=140)
    _btn_inp(g, "Select by Property", 
             lambda: R("select_by_property", prop_name=prop_inp.text(), value=val_inp.text()), 
             prop_inp, val_inp, tip="Selects actors where an editor property matches a specific value.")
             
    tag_inp = _inp("my_tag", "", width=160)
    _btn_inp(g, "Select by Verse Tag", 
             lambda: R("select_by_verse_tag", tag_name=tag_inp.text()), 
             tag_inp, tip="Selects all actors with the specified Verse tag.")
             
    L.addStretch()
    return scroll

def _tab_lighting(R) -> "QScrollArea":
    scroll, L = _page()
    hero = QLabel("Lighting & Post-Process")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    # ── Place Light ──────────────────────────────────────────────────────────
    g_place = _group(L, "Place Light at Camera")
    lt_combo     = QComboBox(); lt_combo.addItems(["point", "spot", "rect", "directional", "sky"]); lt_combo.setFixedWidth(100)
    intensity_sp = _spin(1000.0, 0.0, 99999.0, 0, 90)
    color_inp    = _inp("hex color", "#FFFFFF", 90)
    atten_sp     = _spin(1000.0, 0.0, 99999.0, 0, 90)

    def _lrow(*items):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0,0,0,0); h.setSpacing(4)
        for lbl, wgt in items:
            h.addWidget(QLabel(lbl)); h.addWidget(wgt)
        h.addStretch(); g_place.addWidget(w)

    _lrow(("Type:", lt_combo), ("Intensity:", intensity_sp))
    _lrow(("Color:", color_inp), ("Radius:", atten_sp))
    _btn(g_place, "Place Light at Camera",
         lambda: R("light_place", light_type=lt_combo.currentText(),
                   intensity=intensity_sp.value(), color=color_inp.text(),
                   attenuation=atten_sp.value()))

    # ── Adjust Selected Lights ────────────────────────────────────────────────
    g_set = _group(L, "Adjust Selected Lights")
    set_int_sp   = _spin(1000.0, 0.0, 99999.0, 0, 90)
    set_col_inp  = _inp("color #RRGGBB", "", 90)
    set_atten_sp = _spin(1000.0, 0.0, 99999.0, 0, 90)
    _btn_inp(g_set, "Set Intensity",
             lambda *_: R("light_set", intensity=set_int_sp.value()),
             set_int_sp, tip="Set intensity on all selected light actors")
    _btn_inp(g_set, "Set Color",
             lambda *_: R("light_set", color=set_col_inp.text()),
             set_col_inp, tip="Set hex color on all selected light actors")
    _btn_inp(g_set, "Set Radius",
             lambda *_: R("light_set", attenuation=set_atten_sp.value()),
             set_atten_sp, tip="Set attenuation radius on selected point/spot/rect lights")
    _btn(g_set, "List All Lights", lambda: R("light_list"),
         "Audit every light in the level — type, label, intensity, location.")

    # ── Time of Day ───────────────────────────────────────────────────────────
    g_tod = _group(L, "Time of Day  (needs DirectionalLight in level)")
    hour_sp = _spin(12.0, 0.0, 24.0, 1, 70)
    _btn_inp(g_tod, "Set Time of Day",
             lambda *_: R("sky_set_time", hour=hour_sp.value()),
             hour_sp, tip="0=midnight  6=sunrise  12=noon  18=sunset")
    _btn(g_tod, "Randomize Sun", lambda: R("light_randomize_sky"),
         "Random pitch+yaw on the DirectionalLight — fast look-dev.")

    # ── Atmospheric Presets ───────────────────────────────────────────────────
    g_mood = _group(L, "Atmospheric Presets")
    mood_combo = QComboBox(); mood_combo.addItems(["Star Wars", "Cyberpunk", "Vibrant"]); mood_combo.setFixedWidth(130)
    _btn_inp(g_mood, "Apply Mood Preset",
             lambda *_: R("light_cinematic_preset", mood=mood_combo.currentText()),
             mood_combo, tip="Adjusts DirectionalLight intensity+color and fog density.")

    # ── Post-Process ──────────────────────────────────────────────────────────
    g_pp = _group(L, "Post-Process Volume")
    _btn(g_pp, "Spawn Global PPV", lambda: R("postprocess_spawn"),
         "Creates a global PostProcessVolume (infinite extent). Skips if one already exists.")

    pp_preset_combo = QComboBox()
    pp_preset_combo.addItems(["cinematic", "night", "vibrant", "bleach", "horror", "fantasy", "reset"])
    pp_preset_combo.setFixedWidth(110)
    _btn_inp(g_pp, "Apply Visual Preset",
             lambda *_: R("postprocess_preset", preset=pp_preset_combo.currentText()),
             pp_preset_combo, tip="Applies bloom/exposure/vignette/saturation preset to the level PPV.")

    bloom_sp    = _spin(0.675, 0.0, 10.0, 2, 90)
    exposure_sp = _spin(0.0, -10.0, 10.0, 1, 90)
    _btn_inp(g_pp, "Set Bloom",
             lambda *_: R("postprocess_set", bloom=bloom_sp.value()),
             bloom_sp, tip="Bloom intensity (0–10). Default UE value is 0.675.")
    _btn_inp(g_pp, "Set Exposure",
             lambda *_: R("postprocess_set", exposure=exposure_sp.value()),
             exposure_sp, tip="EV bias — negative = darker, positive = brighter.")

    L.addStretch()
    return scroll

def _tab_audio(R) -> "QScrollArea":
    scroll, L = _page()
    hero = QLabel("Audio Placement")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    note = QLabel("Places standard AmbientSound actors (not Fortnite music devices).\nLeave Asset Path blank to assign a sound manually in the Details panel.")
    note.setStyleSheet(f"font-size: 11px; color: {_color('text_dim')}; padding-bottom: 10px;")
    note.setWordWrap(True)
    L.addWidget(note)

    # ── Place Sound ───────────────────────────────────────────────────────────
    g_place = _group(L, "Place Sound at Camera")
    audio_label_inp  = _inp("label", "AmbientSound", 130)
    audio_vol_sp     = _spin(1.0, 0.0, 4.0, 2, 70)
    audio_asset_inp  = _inp("/Game/Audio/… (optional)", "", 200)
    audio_radius_sp  = _spin(0.0, 0.0, 99999.0, 0, 90)

    def _arow(*items):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0,0,0,0); h.setSpacing(4)
        for lbl, wgt in items:
            h.addWidget(QLabel(lbl)); h.addWidget(wgt)
        h.addStretch(); g_place.addWidget(w)

    _arow(("Label:", audio_label_inp), ("Volume:", audio_vol_sp))
    _arow(("Asset:", audio_asset_inp))
    _arow(("Radius:", audio_radius_sp))
    _btn(g_place, "Place Ambient Sound at Camera",
         lambda: R("audio_place",
                   label=audio_label_inp.text() or "AmbientSound",
                   asset_path=audio_asset_inp.text(),
                   volume=audio_vol_sp.value(),
                   radius=audio_radius_sp.value()))

    # ── Bulk Adjust ───────────────────────────────────────────────────────────
    g_bulk = _group(L, "Adjust Selected Sounds")
    bulk_vol_sp    = _spin(1.0, 0.0, 4.0, 2, 90)
    bulk_radius_sp = _spin(2000.0, 0.0, 99999.0, 0, 90)
    _btn_inp(g_bulk, "Set Volume",
             lambda *_: R("audio_set_volume", volume=bulk_vol_sp.value()),
             bulk_vol_sp, tip="Set volume multiplier on all selected AmbientSound actors")
    _btn_inp(g_bulk, "Set Radius",
             lambda *_: R("audio_set_radius", radius=bulk_radius_sp.value()),
             bulk_radius_sp, tip="Override attenuation falloff radius on selected sounds")

    # ── Audit ─────────────────────────────────────────────────────────────────
    g_audit = _group(L, "Audit")
    _btn(g_audit, "List All Sounds", lambda: R("audio_list"),
         "List every AmbientSound in the level — label, asset, volume, folder.")

    L.addStretch()
    return scroll


def _tab_project_admin(R) -> "QScrollArea":
    scroll, L = _page()
    hero = QLabel("Project Administration")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    g = _group(L, "Maintenance & Safety")
    
    _btn(g, "Full Project Backup (.zip)", lambda: R("system_backup_project"), 
         "Creates a timestamped .zip of the Content folder in Saved/UEFN_Toolbelt/backups/")
    
    _btn(g, "Level Performance Audit", lambda: R("system_perf_audit"), 
         "Fast scan of level for excessive actors or lights.")
         
    L.addStretch()
    return scroll

def _tab_environmental(R) -> "QScrollArea":
    scroll, L = _page()
    hero = QLabel("Environmental Mastery")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)
    
    desc = QLabel("Prop-to-Foliage conversion and brush auditing.")
    desc.setStyleSheet(f"font-size: 12px; color: {_color('text_dim')}; padding-bottom: 12px;")
    desc.setWordWrap(True)
    L.addWidget(desc)
    
    g = _group(L, "Foliage Operations")
    _btn(g, "Convert Props to Foliage", lambda: R("foliage_convert_selected_to_actor"), "Converts regular meshes into foliage-capable actors.")
    _btn(g, "Audit Brushes", lambda: R("foliage_audit_brushes"), "Scans level for non-standard brush transforms.")
    
    L.addStretch()
    return scroll

def _tab_entities(R) -> "QScrollArea":
    scroll, L = _page()
    hero = QLabel("Entity Management")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)
    
    g = _group(L, "Device Kits")
    _btn(g, "Spawn Lobby Kit", lambda: R("entity_spawn_kit", kit_name="Lobby Starter"))
    _btn(g, "Spawn Teleport Link", lambda: R("entity_spawn_kit", kit_name="Teleport Link"))
    _btn(g, "Spawn Objective Hub", lambda: R("entity_spawn_kit", kit_name="Objective Hub"))
    _btn(g, "List All Custom Kits", lambda: R("entity_list_kits"))
    
    L.addStretch()
    return scroll


# ─── Simulation tab ──────────────────────────────────────────────────────────

def _tab_simulation(_R=None) -> "QScrollArea":
    scroll, L = _page()

    hero = QLabel("Simulation Helpers")
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #00F2FF; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    desc = QLabel("Test Verse logic in-editor without full sessions using schema-driven proxies.")
    desc.setStyleSheet(f"font-size: 12px; color: {_color('text_dim')}; padding-bottom: 12px;")
    desc.setWordWrap(True)
    L.addWidget(desc)

    g_sim = _group(L, "Verse Simulation")
    _btn(g_sim, "Generate Simulation Proxy", lambda: _R("sim_generate_proxy") if _R else None, "Creates a Python 'Shadow' of your Verse device APIs using discovered schema data.")
    
    # Method trigger with inline input
    method_inp = QLineEdit("Show")
    method_inp.setPlaceholderText("Method name...")
    method_inp.setFixedWidth(120)
    _btn_inp(g_sim, "Trigger Dev Method", lambda: _R("sim_trigger_method", method_name=method_inp.text()) if _R else None, 
             method_inp, tip="Force-fire a Verse method discovered in the schema.")

    L.addStretch()
    return scroll


# ─── Sequencer tab ───────────────────────────────────────────────────────────

def _tab_sequencer(_R=None) -> "QScrollArea":
    scroll, L = _page()

    hero = QLabel("Sequencer Automation")
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #FF00E4; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    desc = QLabel("Cinematic fly-throughs and bulk keyframe management.")
    desc.setStyleSheet(f"font-size: 12px; color: {_color('text_dim')}; padding-bottom: 12px;")
    desc.setWordWrap(True)
    L.addWidget(desc)

    g_seq = _group(L, "Level Sequence Tools")
    
    dur_inp = QDoubleSpinBox()
    dur_inp.setValue(5.0)
    dur_inp.setRange(0.1, 300.0)
    dur_inp.setSuffix("s")
    
    _btn_inp(g_seq, "Actor to Spline Path", lambda: _R("seq_actor_to_spline", duration=dur_inp.value()) if _R else None,
             dur_inp, tip="Animate selected actor along a spline path over a set duration.")

    _btn(g_seq, "Bulk Keyframe Selection", lambda: _R("seq_batch_keyframe") if _R else None, "Add transform keys for all selected actors in the active sequence.")

    L.addStretch()
    return scroll


# ─── About page ───────────────────────────────────────────────────────────────


_REPO_URL = "https://github.com/undergroundrap/UEFN-TOOLBELT"

def _tab_appearance(_R=None) -> "QScrollArea":
    scroll, L = _page()

    hero = QLabel("Appearance")
    hero.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {_color('text_bright')}; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    desc = QLabel("Switch the color theme. Changes apply live to all open windows and persist across restarts.")
    desc.setStyleSheet(f"font-size: 12px; color: {_color('text_dim')}; padding-bottom: 12px;")
    desc.setWordWrap(True)
    L.addWidget(desc)

    g = _group(L, "Color Themes")

    # Grid: 2 columns of theme swatch buttons
    grid_widget = QWidget()
    grid = QGridLayout(grid_widget)
    grid.setSpacing(8)
    grid.setContentsMargins(0, 0, 0, 0)

    swatch_btns: dict = {}

    def _make_swatch(name: str, t: dict) -> "QPushButton":
        display = name.replace("_", " ").title()
        btn = QPushButton(display)
        btn.setFixedHeight(68)
        btn.setStyleSheet(
            f"QPushButton {{ background: {t['bg']}; color: {t['text']}; "
            f"border: 1px solid {t['border2']}; border-radius: 6px; "
            f"font-size: 11px; font-weight: bold; }}"
            f"QPushButton:hover {{ border: 2px solid {_color('text_bright')}; }}"
        )

        # Colour strip — drawn as a sub-label showing bg + accent + brand
        strip_html = (
            f"<span style='color:{t['accent']}'>■</span> "
            f"<span style='color:{t['brand']}'>■</span> "
            f"<span style='color:{t['ok']}'>■</span> "
            f"<span style='color:{t['muted']}'>■</span>"
        )
        # Embed the strip into the button as a tooltip + second line via newline trick
        btn.setToolTip(
            f"<b>{display}</b><br>"
            f"Background: {t['bg']}  Accent: {t['accent']}<br>"
            f"Brand: {t['brand']}  Text: {t['text']}"
        )

        def _apply(_, n=name):
            if _R:
                _R("theme_set", name=n)
            else:
                _theme_mod.set_theme(n)
                try:
                    _get_config().set("ui.theme", n)
                except Exception:
                    pass

        btn.clicked.connect(_apply)
        return btn

    themes = _theme_mod.THEMES
    names = list(themes.keys())
    for i, name in enumerate(names):
        btn = _make_swatch(name, themes[name])
        swatch_btns[name] = btn
        grid.addWidget(btn, i // 2, i % 2)

    g.addWidget(grid_widget)

    # Active-theme indicator — updates live when theme changes
    active_lbl = QLabel()
    active_lbl.setStyleSheet(f"font-size: 11px; color: {_color('muted')}; padding-top: 6px;")
    g.addWidget(active_lbl)

    def _update_swatches(new_qss: str = None) -> None:
        current = _theme_mod.get_current_theme()
        active_lbl.setText(f"Active: {current.replace('_', ' ').title()}")
        for n, btn in swatch_btns.items():
            t = _theme_mod.THEMES.get(n, _theme_mod.THEMES["toolbelt_dark"])
            active = n == current
            border_w = "3px" if active else "1px"
            border_col = _color("text_bright") if active else t["border2"]
            prefix = "✓ " if active else ""
            display = prefix + n.replace("_", " ").title()
            btn.setText(display)
            btn.setStyleSheet(
                f"QPushButton {{ background: {t['bg']}; color: {t['text']}; "
                f"border: {border_w} solid {border_col}; border-radius: 6px; "
                f"font-size: 11px; font-weight: bold; }}"
                f"QPushButton:hover {{ border: 2px solid {_color('text_bright')}; }}"
            )

    _theme_mod.subscribe(_update_swatches)
    scroll.destroyed.connect(lambda: _theme_mod.unsubscribe(_update_swatches))
    _update_swatches()  # set initial state

    _sep(L)

    # MCP / console usage
    g2 = _group(L, "Apply a Theme via Console or MCP")
    for name in names:
        tip_lbl = QLabel(f'tb.run("theme_set", name="{name}")')
        tip_lbl.setStyleSheet(
            "font-family: monospace; font-size: 10px; color: #AAAAFF;"
            " background: #12121A; border: 1px solid #2A2A55;"
            " border-radius: 3px; padding: 4px 8px;"
        )
        g2.addWidget(tip_lbl)

    return scroll


def _tab_about(_R=None) -> "QScrollArea":
    scroll, L = _page()

    # ── Hero ─────────────────────────────────────────────────────────────────
    hero = QLabel("UEFN Toolbelt")
    hero.setStyleSheet(
        f"font-size: 26px; font-weight: bold; color: {_color('text_bright')};"
        " padding: 12px 0 4px 0; letter-spacing: 1px;"
    )
    hero.setAlignment(Qt.AlignCenter)
    L.addWidget(hero)

    tagline = QLabel("The Swiss Army Knife for UEFN Python Scripting")
    tagline.setStyleSheet("font-size: 13px; color: #888888; padding-bottom: 4px;")
    tagline.setAlignment(Qt.AlignCenter)
    L.addWidget(tagline)

    from . import __version__ as _tbv
    version = QLabel(f"v{_tbv}  ·  291 tools  ·  UEFN 40.00+  ·  Python 3.11  ·  March 2026")
    version.setStyleSheet(f"font-size: 11px; color: {_color('muted')}; padding-bottom: 12px;")
    version.setAlignment(Qt.AlignCenter)
    L.addWidget(version)

    _sep(L)

    # ── Updates ───────────────────────────────────────────────────────────────
    g_upd = _group(L, "Platform Updates")

    upd_desc = QLabel("Update the Toolbelt to the latest version directly from GitHub.\nWarning: The UEFN editor must be restarted after updating.")
    upd_desc.setStyleSheet("font-size: 11px; color: #777777; padding: 2px 4px;")
    upd_desc.setWordWrap(True)
    g_upd.addWidget(upd_desc)

    btn_update = QPushButton("  Check for Updates (git pull)")
    btn_update.setProperty("accent", "true")
    btn_update.setStyleSheet(btn_update.styleSheet() + "QPushButton { padding: 8px; font-weight: bold; text-align: center; }")
    btn_update.clicked.connect(lambda: _R("toolbelt_update") if _R else None)
    g_upd.addWidget(btn_update)
    
    _sep(L)

    # ── Quick commands (copy-to-clipboard) ────────────────────────────────────
    g_cmds = _group(L, "Quick Commands  —  paste into the UEFN Python console")

    tip = QLabel(
        "The UEFN Python console only accepts one line at a time.\n"
        "Use semicolons to chain statements. Click any button below to copy."
    )
    tip.setStyleSheet("font-size: 11px; color: #666666; padding: 4px 4px 8px 4px;")
    tip.setWordWrap(True)
    g_cmds.addWidget(tip)

    def _copy_btn(label: str, command: str) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        cmd_display = QLabel(command)
        cmd_display.setStyleSheet(
            "font-family: monospace; font-size: 10px; color: #AAAAFF;"
            " background: #12121A; border: 1px solid #2A2A55;"
            " border-radius: 3px; padding: 5px 8px;"
        )
        cmd_display.setWordWrap(True)
        cmd_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedWidth(54)
        copy_btn.setStyleSheet(
            "QPushButton { background: #1A1A55; border: 1px solid #3A3AFF;"
            " color: #8888FF; padding: 4px 8px; border-radius: 3px; font-size: 11px; }"
            "QPushButton:hover { background: #2A2A77; color: #AAAAFF; }"
            f"QPushButton:pressed {{ background: #3A3AFF; color: {_color('text_bright')}; }}"
        )
        copy_btn.clicked.connect(
            lambda _, c=command: QApplication.clipboard().setText(c)
        )

        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size: 10px; color: {_color('muted')}; min-width: 120px;")

        col = QWidget()
        col_layout = QVBoxLayout(col)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(2)
        col_layout.addWidget(lbl)
        col_layout.addWidget(cmd_display)

        row_layout.addWidget(col, stretch=1)
        row_layout.addWidget(copy_btn)
        g_cmds.addWidget(row)

    _copy_btn(
        "Open dashboard (first time or after update):",
        'import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.launch_qt()'
    )
    _copy_btn(
        "Open dashboard (normal — already loaded):",
        "import UEFN_Toolbelt as tb; tb.launch_qt()"
    )
    _copy_btn(
        "Run smoke test (verify everything works):",
        'import UEFN_Toolbelt as tb; tb.run("toolbelt_smoke_test")'
    )
    _copy_btn(
        "List all registered tools:",
        "import UEFN_Toolbelt as tb; tb.registry.list_tools()"
    )

    _sep(L)

    # ── Author & links ────────────────────────────────────────────────────────
    g_author = _group(L, "Author")

    author = QLabel("Ocean Bennett  (@undergroundrap)")
    author.setStyleSheet(f"font-size: 13px; color: {_color('text')}; padding: 6px 4px;")
    g_author.addWidget(author)

    role = QLabel(
        "Creator · Lead Developer\n"
        "UEFN creator tooling · Python editor scripting · Verse workflow automation"
    )
    role.setStyleSheet("font-size: 11px; color: #666666; padding: 0 4px 6px 4px;")
    role.setWordWrap(True)
    g_author.addWidget(role)

    btn_repo = QPushButton("  Open GitHub Repository")
    btn_repo.setProperty("accent", "true")
    btn_repo.setStyleSheet(
        btn_repo.styleSheet() +
        "QPushButton { text-align: center; font-size: 13px; padding: 10px; }"
    )
    btn_repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(_REPO_URL)))
    g_author.addWidget(btn_repo)

    _sep(L)

    # ── Stats ─────────────────────────────────────────────────────────────────
    g_stats = _group(L, "What's Inside")

    stats = [
        ("171", "registered tools"),
        ("30",  "categories"),
        ("6",   "smoke-test layers"),
        ("0",   "network calls — fully offline"),
        ("1",   "Ctrl+Z to undo anything"),
    ]
    for num, label in stats:
        row = QLabel(f"  {num:>4}   {label}")
        row.setStyleSheet(f"font-size: 12px; color: {_color('text_dim')}; padding: 3px 4px;")
        g_stats.addWidget(row)

    _sep(L)

    # ── License ───────────────────────────────────────────────────────────────
    g_lic = _group(L, "License")

    lic_title = QLabel("AGPL-3.0 with Visible Attribution Requirement")
    lic_title.setStyleSheet(f"font-size: 12px; color: {_color('text')}; padding: 4px 4px 2px 4px; font-weight: bold;")
    g_lic.addWidget(lic_title)

    lic_body = QLabel(
        "Free and open source. You may use, modify, and distribute this toolbelt\n"
        "under AGPL-3.0. Derivative works must also be open source.\n\n"
        "If you build something on top of this — a fork, plugin, or tool — you must\n"
        "include visible credit in your README or about screen:\n"
    )
    lic_body.setStyleSheet("font-size: 11px; color: #777777; padding: 2px 4px;")
    lic_body.setWordWrap(True)
    g_lic.addWidget(lic_body)

    credit_box = QLabel(
        '"Built on UEFN Toolbelt by Ocean Bennett\n'
        ' (https://github.com/undergroundrap/UEFN-TOOLBELT)"'
    )
    credit_box.setStyleSheet(
        "font-size: 11px; color: #AAAAFF; background: #12121A;"
        " border: 1px solid #2A2A55; border-radius: 4px;"
        " padding: 8px 10px; margin: 4px;"
    )
    credit_box.setWordWrap(True)
    g_lic.addWidget(credit_box)

    btn_lic = QPushButton("  Full License Text (AGPL-3.0)")
    btn_lic.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl("https://www.gnu.org/licenses/agpl-3.0.en.html"))
    )
    g_lic.addWidget(btn_lic)

    _sep(L)

    # ── Community ─────────────────────────────────────────────────────────────
    g_com = _group(L, "Community & Support")

    community = QLabel(
        "Built by Ocean Bennett (2026).\n"
        "Inspired by the UEFN creator community and everyone pushing the limits\n"
        "of Fortnite creation.\n\n"
        "Found a bug? Have a tool idea? Open an issue or PR on GitHub."
    )
    community.setStyleSheet("font-size: 11px; color: #666666; padding: 4px;")
    community.setWordWrap(True)
    g_com.addWidget(community)

    # ── Attributions ──────────────────────────────────────────────────────────
    g_attr = _group(L, "Attributions & Inspirations")

    for name, desc, url in [
        (
            "ImmatureGamer",
            "Verse Device Graph concept — uefn-device-graph (tkinter). "
            "This Toolbelt implementation is an independent PySide6 rewrite. "
            "Full credit for pioneering UEFN device graph tooling.",
            "https://github.com/ImmatureGamer/uefn-device-graph",
        ),
        (
            "Kirch  (KirchCreator)",
            "MCP Bridge queue + Slate tick architecture — uefn-mcp-server. "
            "Full credit for pioneering the MCP bridge pattern for UEFN Python "
            "and validating the threading model.",
            "https://github.com/KirChuvakov/uefn-mcp-server",
        ),
    ]:
        attr_name = QLabel(name)
        attr_name.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {_color('text')}; padding: 6px 4px 2px 4px;")
        g_attr.addWidget(attr_name)

        attr_desc_lbl = QLabel(desc)
        attr_desc_lbl.setStyleSheet("font-size: 11px; color: #777777; padding: 0 4px 2px 4px;")
        attr_desc_lbl.setWordWrap(True)
        g_attr.addWidget(attr_desc_lbl)

        link_btn = QPushButton(f"  {url}")
        link_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #8888FF;"
            " text-align: left; font-size: 11px; padding: 2px 4px; }"
            "QPushButton:hover { color: #AAAAFF; }"
        )
        _url = url
        link_btn.clicked.connect(lambda _, u=_url: QDesktopServices.openUrl(QUrl(u)))
        g_attr.addWidget(link_btn)

    btn_docs = QPushButton("  Getting Started — README")
    btn_docs.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl(_REPO_URL + "#getting-started"))
    )
    g_com.addWidget(btn_docs)

    btn_issue = QPushButton("  Open an Issue on GitHub")
    btn_issue.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl(_REPO_URL + "/issues"))
    )
    g_com.addWidget(btn_issue)

    L.addStretch()
    return scroll


# ─── Main window ──────────────────────────────────────────────────────────────

class ToolbeltDashboard(QMainWindow):
    """UEFN Toolbelt — sidebar nav + search + stacked content pages."""

    _CATEGORIES = [
        ("Quick Actions",_tab_quick_actions),
        ("Selection",   _tab_selection),
        ("Materials",   _tab_materials),
        ("Procedural",  _tab_procedural),
        ("Lighting",    _tab_lighting),
        ("Audio",       _tab_audio),
        ("Measurement", _tab_measurement),
        ("Localization",_tab_localization),
        ("Environmental",_tab_environmental),
        ("Entities",    _tab_entities),
        ("Bulk Ops",    _tab_bulk_ops),
        ("Text",        _tab_text),
        ("Assets",      _tab_assets),
        ("Verse",       _tab_verse),
        ("Project Admin", _tab_project_admin),
        ("Project",     _tab_project),
        ("Screenshot",  _tab_screenshot),
        ("Tags",        _tab_tags),
        ("MCP",         _tab_mcp),
        ("API",         _tab_api),
        ("Simulation",  _tab_simulation),
        ("Sequencer",   _tab_sequencer),
        ("Verification",_tab_verification),
        ("Plugin Hub",  _tab_plugin_hub),
        ("Appearance",  _tab_appearance),
        ("About",       _tab_about),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("UEFN Toolbelt")
        self.setWindowIcon(_make_icon())
        self.setMinimumSize(820, 640)
        self.resize(960, 740)
        self.setStyleSheet(_QSS)

        # Subscribe to live theme changes and restore saved theme
        _theme_mod.subscribe(self._apply_theme)
        saved_theme = _get_config().get("ui.theme", "toolbelt_dark")
        if saved_theme != _theme_mod.get_current_theme():
            _theme_mod.set_theme(saved_theme)

        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint
        )

        self._sbar = QStatusBar()
        self.setStatusBar(self._sbar)
        self._sbar.showMessage("  Ready — select actors, then click a tool")

        R = self._run

        # ── Stacked content area (page 0 = search results, 1-11 = categories) ──
        self._stack = QStackedWidget()

        self._search_container = QWidget()
        self._search_layout = QVBoxLayout(self._search_container)
        self._search_layout.setAlignment(Qt.AlignTop)
        self._search_layout.setContentsMargins(8, 8, 8, 8)
        self._search_layout.setSpacing(4)
        search_scroll = QScrollArea()
        search_scroll.setWidgetResizable(True)
        search_scroll.setWidget(self._search_container)
        self._stack.addWidget(search_scroll)  # index 0

        self._cat_indices: dict = {}
        self._mcp_refresh_fn = None  # populated after MCP tab is built
        for label, builder in self._CATEGORIES:
            idx = self._stack.addWidget(builder(R))
            self._cat_indices[label] = idx
            if label == "MCP":
                # Find the status label's stored refresh fn
                page = self._stack.widget(idx)
                for child in page.findChildren(QLabel):
                    fn = child.property("mcp_refresh_fn")
                    if fn:
                        self._mcp_refresh_fn = fn
                        break

        # ── Left sidebar ──────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(132)
        sidebar.setStyleSheet("QWidget { background: #141414; border: none; }")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("  Find any tool…")
        self._search_box.setToolTip("Global search — finds tools across all categories by name, description, or tag")
        self._search_box.setStyleSheet(
            f"QLineEdit {{ background: {_color('grid')}; border: none;"
            f" border-bottom: 1px solid {_color('border')}; color: {_color('text')};"
            " padding: 8px 10px; font-size: 12px; }"
            "QLineEdit:focus { border-bottom: 1px solid #3A3AFF; }"
        )
        self._search_box.textChanged.connect(self._on_search)
        sb_layout.addWidget(self._search_box)

        _NAV_BASE = (
            "QPushButton { background: transparent; border: none; border-left: 3px solid transparent;"
            " color: #777777; text-align: left; padding: 9px 12px; font-size: 12px; }"
            f"QPushButton:hover {{ background: #1C1C1C; color: {_color('text')}; }}"
            "QPushButton:checked { background: #1A1A55; color: #AAAAFF;"
            " border-left: 3px solid #3A3AFF; font-weight: bold; }"
        )

        # Nav buttons live inside a scroll area so adding more categories never clips
        nav_widget = QWidget()
        nav_widget.setStyleSheet("QWidget { background: #141414; }")
        nav_inner = QVBoxLayout(nav_widget)
        nav_inner.setContentsMargins(0, 0, 0, 0)
        nav_inner.setSpacing(0)

        self._nav_btns: dict = {}
        for label, _ in self._CATEGORIES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(_NAV_BASE)
            btn.clicked.connect(lambda _, l=label: self._select_category(l))
            nav_inner.addWidget(btn)
            self._nav_btns[label] = btn

        nav_inner.addStretch()

        nav_scroll = QScrollArea()
        nav_scroll.setWidget(nav_widget)
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        nav_scroll.setStyleSheet("QScrollArea { border: none; background: #141414; }")
        sb_layout.addWidget(nav_scroll, stretch=1)

        # ── Content area: header bar + stack ─────────────────────────────────
        # Header shows the active category name + a within-page filter input
        self._content_header = QWidget()
        self._content_header.setFixedHeight(38)
        self._content_header.setStyleSheet(
            "QWidget { background: #161616; border-bottom: 1px solid #252525; }"
        )
        hdr_layout = QHBoxLayout(self._content_header)
        hdr_layout.setContentsMargins(14, 0, 8, 0)
        hdr_layout.setSpacing(8)

        self._cat_label = QLabel("Materials")
        self._cat_label.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {_color('muted')};"
            " letter-spacing: 1px; text-transform: uppercase;"
        )
        hdr_layout.addWidget(self._cat_label)
        hdr_layout.addStretch()

        self._filter_box = QLineEdit()
        self._filter_box.setPlaceholderText("Filter this page…")
        self._filter_box.setToolTip("Filters buttons visible on the current category page")
        self._filter_box.setFixedWidth(170)
        self._filter_box.setStyleSheet(
            f"QLineEdit {{ background: {_color('panel')}; border: 1px solid {_color('border')};"
            f" color: {_color('text')}; padding: 4px 8px; font-size: 11px; border-radius: 3px; }}"
            "QLineEdit:focus { border-color: #3A3AFF; }"
        )
        self._filter_box.textChanged.connect(self._on_filter)
        hdr_layout.addWidget(self._filter_box)

        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._content_header)
        content_layout.addWidget(self._stack, stretch=1)

        # ── Divider + central layout ──────────────────────────────────────────
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFixedWidth(1)
        divider.setStyleSheet(f"background: {_color('border')};")

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(divider)
        layout.addWidget(content_area, stretch=1)
        self.setCentralWidget(central)

        self._select_category("Quick Actions")

    # ── Navigation ────────────────────────────────────────────────────────────

    def _select_category(self, label: str) -> None:
        for name, btn in self._nav_btns.items():
            btn.setChecked(name == label)
        # Clear global search without triggering _on_search
        self._search_box.blockSignals(True)
        self._search_box.clear()
        self._search_box.blockSignals(False)
        # Clear per-page filter without triggering _on_filter
        self._filter_box.blockSignals(True)
        self._filter_box.clear()
        self._filter_box.blockSignals(False)
        # Restore all hidden buttons from any previous filter
        page = self._stack.widget(self._cat_indices.get(label, 1))
        if page:
            for btn in page.findChildren(QPushButton):
                btn.setVisible(True)
        # Update header — hide filter on About (no tool buttons to filter)
        self._cat_label.setText(label.upper())
        show_filter = label != "About"
        self._filter_box.setPlaceholderText(f"Filter {label}…")
        self._filter_box.setVisible(show_filter)
        self._stack.setCurrentIndex(self._cat_indices[label])
        # Refresh MCP status indicator whenever the MCP tab is navigated to
        if label == "MCP" and hasattr(self, "_mcp_refresh_fn"):
            self._mcp_refresh_fn()

    def _on_filter(self, text: str) -> None:
        """Filter buttons within the currently visible category page."""
        text = text.strip().lower()
        page = self._stack.currentWidget()
        if page is None:
            return
        for btn in page.findChildren(QPushButton):
            btn.setVisible(not text or text in btn.text().lower())

    def _on_search(self, text: str) -> None:
        """Global search — finds tools across all categories."""
        text = text.strip().lower()
        if not text:
            # Restore whichever category nav button is checked
            for name, btn in self._nav_btns.items():
                if btn.isChecked():
                    self._filter_box.setVisible(True)
                    self._stack.setCurrentIndex(self._cat_indices[name])
                    return
            self._select_category("Materials")
            return

        # Hide per-page filter while global search is active
        self._filter_box.setVisible(False)
        self._filter_box.blockSignals(True)
        self._filter_box.clear()
        self._filter_box.blockSignals(False)

        self._cat_label.setText("SEARCH RESULTS")
        self._stack.setCurrentIndex(0)

        # Clear old results
        while self._search_layout.count():
            item = self._search_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        import UEFN_Toolbelt as _tb
        results = [
            t for t in _tb.registry.list_tools()
            if text in t["name"].lower()
            or text in t.get("description", "").lower()
            or any(text in tag.lower() for tag in t.get("tags", []))
        ]

        if not results:
            lbl = QLabel(f'  No tools match "{text}".')
            lbl.setStyleSheet(f"color: {_color('muted')}; padding: 16px;")
            self._search_layout.addWidget(lbl)
            return

        count_lbl = QLabel(f"  {len(results)} tool{'s' if len(results) != 1 else ''} found")
        count_lbl.setStyleSheet(f"color: {_color('muted')}; font-size: 11px; padding: 6px 8px 2px 8px;")
        self._search_layout.addWidget(count_lbl)

        for tool in results:
            cat = tool.get("category", "")
            desc = tool.get("description", "")
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)

            # Category badge
            cat_badge = QLabel(cat)
            cat_badge.setFixedWidth(86)
            cat_badge.setAlignment(Qt.AlignCenter)
            cat_badge.setStyleSheet(
                f"font-size: 9px; color: {_color('muted')}; background: {_color('card')};"
                f" border: 1px solid {_color('border')}; border-radius: 3px; padding: 2px 4px;"
                " margin: 2px 4px 2px 0;"
            )

            tool_btn = QPushButton(f"  {tool['name']}   —   {desc}")
            tool_btn.setToolTip(f"[{cat}]  {desc}")
            tool_btn.clicked.connect(lambda _, n=tool["name"]: self._run(n))

            row_layout.addWidget(cat_badge)
            row_layout.addWidget(tool_btn, stretch=1)
            self._search_layout.addWidget(row)

    # ── Tool execution ────────────────────────────────────────────────────────

    def _run(self, tool_name: str, **kwargs) -> None:
        import time
        import UEFN_Toolbelt as _tb
        self._sbar.showMessage(f"  Running  {tool_name}…")
        QApplication.processEvents()
        try:
            t0 = time.time()
            result = _tb.run(tool_name, **kwargs)
            t1 = time.time()
            ms = (t1 - t0) * 1000

            if result is None or result is True:
                msg = f"  ✓  {tool_name}  ({ms:.1f}ms)"
            elif isinstance(result, list):
                msg = f"  ✓  {tool_name}: {len(result)} items processed  ({ms:.1f}ms)"
            else:
                s_res = str(result)
                if len(s_res) > 30: s_res = s_res[:27] + "..."
                msg = f"  ✓  {tool_name}: {s_res}  ({ms:.1f}ms)"

            self._set_status(msg, ok=True)
        except Exception as e:
            self._set_status(f"  ✗  {str(e)[:60]}", ok=False)
            unreal.log_error(f"[Dashboard] {tool_name}: {e}")

    def _set_status(self, msg: str, ok: bool = True) -> None:
        color = _color("ok") if ok else _color("error")
        self._sbar.setStyleSheet(f"QStatusBar {{ color: {color}; }}")
        self._sbar.showMessage(msg, 5000)

    def _apply_theme(self, qss: str) -> None:
        """Called by the theme system when the active theme changes."""
        self.setStyleSheet(qss)

    def closeEvent(self, event) -> None:
        _theme_mod.unsubscribe(self._apply_theme)
        event.ignore()
        self.hide()


# ─── Launch machinery ─────────────────────────────────────────────────────────

_WINDOW: ToolbeltDashboard | None = None
_APP:    QApplication | None      = None
_TICK:   object | None            = None


def _ensure_app() -> bool:
    """Create QApplication if needed. Returns True if PySide6 is available."""
    global _APP
    if not _PYSIDE6:
        return False
    if _APP is None:
        _APP = QApplication.instance() or QApplication(sys.argv)
        # Pump Qt events on every editor tick so the window stays responsive
        global _TICK
        if _TICK is None:
            def _pump(dt: float) -> None:
                if _APP:
                    _APP.processEvents()
            _TICK = unreal.register_slate_post_tick_callback(_pump)
    return True


def launch_dashboard() -> None:
    """Open (or restore) the Toolbelt Qt dashboard."""
    global _WINDOW

    if not _ensure_app():
        unreal.log_warning(
            "[TOOLBELT] PySide6 not found — falling back to text mode.\n"
            "  Install: <UE_PATH>/Engine/Binaries/ThirdParty/Python3/Win64/python.exe"
            " -m pip install PySide6"
        )
        import UEFN_Toolbelt as _tb
        _tb._print_tool_list()
        return

    if _WINDOW is None:
        _WINDOW = ToolbeltDashboard()

    if _WINDOW.isHidden():
        _WINDOW.show()
    else:
        _WINDOW.raise_()
        _WINDOW.activateWindow()

    # Auto-start the MCP listener so Claude Code can connect immediately.
    # Silent if already running — mcp_start is idempotent.
    try:
        import UEFN_Toolbelt as _tb
        _tb.run("mcp_start")
    except Exception:
        pass  # never block dashboard open if MCP fails

    unreal.log("[TOOLBELT] ✓ Dashboard open.")


# ─── Registration ──────────────────────────────────────────────────────────────

@register_tool(
    name="launch_qt",
    category="Dashboard",
    description="Open the PySide6 tabbed Toolbelt dashboard (dark theme, no Blueprint needed)",
    icon="⬡",
    tags=["dashboard", "ui", "launch", "pyside6", "qt"],
)
def launch_qt(**kwargs) -> None:
    """Launch the PySide6 dashboard."""
    launch_dashboard()


@register_tool(
    name="toolbelt_update",
    category="Utilities",
    description="Securely pull the latest Toolbelt updates from the GitHub repository.",
    tags=["update", "git", "pull", "upgrade", "system", "health"]
)
def update_toolbelt(**kwargs) -> str:
    """Execute git pull against the toolbelt repository root."""
    import subprocess, os
    import UEFN_Toolbelt as _tb
    from UEFN_Toolbelt import core
    root = os.path.abspath(os.path.join(os.path.dirname(_tb.__file__), "..", "..", "..")) 
    
    # Pre-flight check: is it a git repo?
    if not os.path.exists(os.path.join(root, ".git")):
        return "Error: Not a git repository"
        
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        res = subprocess.run(["git", "-C", root, "pull", "origin", "main"], capture_output=True, text=True, startupinfo=startupinfo)
        
        if res.returncode == 0:
            if "Already up to date" in res.stdout:
                return "Already up-to-date"
            else:
                core.log_info(f"[Updater] {res.stdout}")
                return "Updated successfully! Restart UEFN."
        else:
            core.log_error(f"[Updater] Git failed:\n{res.stderr}")
            return "Git pull failed"
    except Exception as e:
        core.log_error(f"[Updater] Subprocess failed: {e}")
        return "Command error"

