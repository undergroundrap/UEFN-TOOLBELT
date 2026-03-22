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

from .core.theme import QSS as _QSS  # noqa: E402 — after sys/unreal imports

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
    s.setFixedWidth(width)
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
    line.setStyleSheet("color: #2A2A2A;")
    layout.addWidget(line)


# ─── Quick Actions ─────────────────────────────────────────────────────────────

def _tab_quick_actions(R) -> "QScrollArea":
    scroll, L = _page()

    hero = QLabel("Quick Actions")
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    desc = QLabel("The most frequently used tools for daily UEFN workflow automation.")
    desc.setStyleSheet("font-size: 12px; color: #AAAAAA; padding-bottom: 12px;")
    desc.setWordWrap(True)
    L.addWidget(desc)

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
    _btn(g_media, "Paste Image from Clipboard", lambda: R("import_image_from_clipboard"), "Instantly imports your current clipboard image as a Texture2D.")

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

    # Arena
    g = _group(L, "Arena Generator")
    _row(L if False else g, *[
        (f"{s.title()} Arena", lambda s=s: R("arena_generate", size=s, apply_team_colors=True))
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
        ("Grid 5×5",      lambda: R("pattern_grid",        mesh_path=_mesh(), preview=_prev())),
        ("Circle Ring",   lambda: R("pattern_circle",      mesh_path=_mesh(), preview=_prev())),
        ("Arc 180°",      lambda: R("pattern_arc",         mesh_path=_mesh(), preview=_prev())),
        ("Spiral",        lambda: R("pattern_spiral",      mesh_path=_mesh(), preview=_prev())),
        ("Line",          lambda: R("pattern_line",        mesh_path=_mesh(), preview=_prev())),
        ("Sine Wave",     lambda: R("pattern_wave",        mesh_path=_mesh(), preview=_prev())),
        ("Helix",         lambda: R("pattern_helix",       mesh_path=_mesh(), preview=_prev())),
        ("Radial Rings",  lambda: R("pattern_radial_rows", mesh_path=_mesh(), preview=_prev())),
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
                                     count=int(count_s.value()), radius=radius_s.value())),
         ("Scatter HISM",   lambda: R("scatter_hism",
                                     mesh_path=scatter_inp.text() or "/Engine/BasicShapes/Sphere",
                                     count=int(count_s.value()), radius=radius_s.value())),
         ("Clear Scatter",  lambda: R("scatter_clear")),
    )

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

    g = _group(L, "Place")
    text_inp  = _inp("Sign text", "ZONE", width=120)
    color_inp = _inp("#RRGGBB", "#FFDD00", width=90)
    z_s       = _spin(200, -9999, 9999, width=80)
    row1 = QWidget(); h1 = QHBoxLayout(row1); h1.setContentsMargins(0, 0, 0, 0); h1.setSpacing(4)
    h1.addWidget(QLabel("Text:")); h1.addWidget(text_inp)
    h1.addWidget(QLabel("Color:")); h1.addWidget(color_inp)
    h1.addWidget(QLabel("Z:")); h1.addWidget(z_s); h1.addStretch()
    g.addWidget(row1)
    _btn(g, "Place Sign at Origin",
         lambda: R("text_place",
                   text=text_inp.text() or "ZONE",
                   color=color_inp.text() or "#FFDD00",
                   location=(0, 0, z_s.value())))

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
    h2.addWidget(QLabel("Rows:")); h2.addWidget(rows_s)
    h2.addWidget(QLabel("Cell cm:")); h2.addWidget(cell_s); h2.addStretch()
    g2.addWidget(row2)
    _btn(g2, "Paint Zone Grid (A1–D4 style)",
         lambda: R("text_paint_grid",
                   cols=int(cols_s.value()), rows=int(rows_s.value()),
                   cell_size=cell_s.value()))

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
    hint.setStyleSheet("font-size: 10px; color: #555555; padding: 4px;")
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
            lbl.setStyleSheet("color: #555555; padding: 6px; font-size: 11px;")
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
                "font-size: 10px; color: #555555; letter-spacing: 1px;"
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
                    "QPushButton { text-align: left; background: #1E1E1E;"
                    " border: 1px solid #2A2A2A; color: #AAAAAA; font-size: 11px;"
                    " padding: 5px 8px; border-radius: 3px; }"
                    "QPushButton:hover { background: #252525; color: #CCCCCC; }"
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
                    "QPushButton { background: #1A1A1A; border: 1px solid #2A2A2A;"
                    " color: #555555; padding: 4px; font-size: 10px; border-radius: 3px; }"
                    "QPushButton:hover { color: #AAAAAA; }"
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
            lbl.setStyleSheet("color: #555555; padding: 6px; font-size: 11px;")
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
    lbl.setStyleSheet("color: #555555; font-size: 11px; padding: 4px;")
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

    # ── Status & controls ─────────────────────────────────────────────────
    g = _group(L, "Listener Controls")

    _btn(g, "▶  Start Listener",
         lambda: R("mcp_start"),
         "Start the HTTP listener so Claude Code can control UEFN directly")

    _btn(g, "■  Stop Listener",
         lambda: R("mcp_stop"),
         "Stop the MCP HTTP listener")

    _btn(g, "↺  Restart Listener",
         lambda: R("mcp_restart"),
         "Restart after hot-reload or port conflict")

    _btn(g, "📡  Print Status",
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

    _btn(g2, "List All Tools → Output Log",
         lambda: R("mcp_status"),
         "Print every registered toolbelt tool name")

    # ── Setup info ────────────────────────────────────────────────────────
    g3 = _group(L, "Claude Code Setup (.mcp.json)")
    info = QLabel(
        "1. Start Listener above (port 8765)\n"
        "2. Place mcp_server.py next to .mcp.json\n"
        "3. Add to .mcp.json:\n"
        '   {"mcpServers": {"uefn-toolbelt":\n'
        '     {"command": "python",\n'
        '      "args": ["<path>/mcp_server.py"]}}}\n'
        "4. Restart Claude Code — it auto-connects"
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
    warn_lbl.setStyleSheet("color: #FF4444; font-weight: bold; font-size: 13px; padding-top: 10px;")
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
    """Draw a 64×64 hexagon icon for the dashboard window."""
    import math
    size = 64
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))  # transparent

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    cx, cy, r = size / 2, size / 2, size / 2 - 3
    pts = [
        QPointF(cx + r * math.cos(math.radians(60 * i - 30)),
                cy + r * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]
    p.setBrush(QBrush(QColor("#3A3AFF")))
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF(pts))

    p.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 16, QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, "TB")
    p.end()

    return QIcon(pm)


# ─── Plugin Hub ───────────────────────────────────────────────────────────────

def _tab_plugin_hub(R) -> "QScrollArea":
    import os, json
    scroll, L = _page()

    # ── Header
    hero = QLabel("Plugin Ecosystem")
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; padding: 12px 0 4px 0;")
    L.addWidget(hero)

    desc = QLabel("Discover and run third-party tools installed in your Custom_Plugins directory.")
    desc.setStyleSheet("font-size: 12px; color: #AAAAAA; padding-bottom: 12px;")
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
        card.setStyleSheet("QFrame { background: #212121; border: 1px solid #363636; border-radius: 6px; margin-bottom: 6px; }")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 12, 12, 12)
        c_layout.setSpacing(6)

        # Header: Name + Version
        header = QWidget()
        header.setStyleSheet("border: none; background: transparent;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(entry.name)
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFFFFF;")
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
            meta.setStyleSheet("font-size: 11px; color: #AAAAAA; border: none; background: transparent;")
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
            color = "#44FF88" if ok else "#FFAAAA"
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
            "QPushButton { background: #2D2D2D; border: 1px solid #444444; color: #FFFFFF;"
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
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; padding: 12px 0 4px 0;")
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
    hero = QLabel("Cinematic Lighting")
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; padding: 12px 0 4px 0;")
    L.addWidget(hero)
    
    g = _group(L, "Atmospheric Presets")
    
    mood_combo = QComboBox()
    mood_combo.addItems(["Star Wars", "Cyberpunk", "Vibrant"])
    mood_combo.setFixedWidth(160)
    _btn_inp(g, "Apply Lighting Preset", 
             lambda: R("light_cinematic_preset", mood=mood_combo.currentText()), 
             mood_combo, tip="Sets Directional Light and Atmosphere for a specific cinematic mood.")
             
    _btn(g, "Randomize Sun Orientation", lambda: R("light_randomize_sky"), 
         "Randomly shifts sun position for environmental look-dev.")
         
    L.addStretch()
    return scroll

def _tab_project_admin(R) -> "QScrollArea":
    scroll, L = _page()
    hero = QLabel("Project Administration")
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; padding: 12px 0 4px 0;")
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
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; padding: 12px 0 4px 0;")
    L.addWidget(hero)
    
    desc = QLabel("Prop-to-Foliage conversion and brush auditing.")
    desc.setStyleSheet("font-size: 12px; color: #AAAAAA; padding-bottom: 12px;")
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
    hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; padding: 12px 0 4px 0;")
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
    desc.setStyleSheet("font-size: 12px; color: #AAAAAA; padding-bottom: 12px;")
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
    desc.setStyleSheet("font-size: 12px; color: #AAAAAA; padding-bottom: 12px;")
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

def _tab_about(_R=None) -> "QScrollArea":
    scroll, L = _page()

    # ── Hero ─────────────────────────────────────────────────────────────────
    hero = QLabel("UEFN Toolbelt")
    hero.setStyleSheet(
        "font-size: 26px; font-weight: bold; color: #FFFFFF;"
        " padding: 12px 0 4px 0; letter-spacing: 1px;"
    )
    hero.setAlignment(Qt.AlignCenter)
    L.addWidget(hero)

    tagline = QLabel("The Swiss Army Knife for UEFN Python Scripting")
    tagline.setStyleSheet("font-size: 13px; color: #888888; padding-bottom: 4px;")
    tagline.setAlignment(Qt.AlignCenter)
    L.addWidget(tagline)

    version = QLabel("v1.0  ·  UEFN 40.00+  ·  Python 3.11  ·  March 2026")
    version.setStyleSheet("font-size: 11px; color: #555555; padding-bottom: 12px;")
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
            "QPushButton:pressed { background: #3A3AFF; color: #FFFFFF; }"
        )
        copy_btn.clicked.connect(
            lambda _, c=command: QApplication.clipboard().setText(c)
        )

        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 10px; color: #555555; min-width: 120px;")

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
    author.setStyleSheet("font-size: 13px; color: #CCCCCC; padding: 6px 4px;")
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
        ("155", "registered tools"),
        ("18",  "categories"),
        ("6",   "smoke-test layers"),
        ("0",   "network calls — fully offline"),
        ("1",   "Ctrl+Z to undo anything"),
    ]
    for num, label in stats:
        row = QLabel(f"  {num:>4}   {label}")
        row.setStyleSheet("font-size: 12px; color: #AAAAAA; padding: 3px 4px;")
        g_stats.addWidget(row)

    _sep(L)

    # ── License ───────────────────────────────────────────────────────────────
    g_lic = _group(L, "License")

    lic_title = QLabel("AGPL-3.0 with Visible Attribution Requirement")
    lic_title.setStyleSheet("font-size: 12px; color: #CCCCCC; padding: 4px 4px 2px 4px; font-weight: bold;")
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
        ("About",       _tab_about),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("⬡  UEFN Toolbelt")
        self.setWindowIcon(_make_icon())
        self.setMinimumSize(820, 640)
        self.resize(960, 740)
        self.setStyleSheet(_QSS)

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
        for label, builder in self._CATEGORIES:
            self._cat_indices[label] = self._stack.addWidget(builder(R))

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
            "QLineEdit { background: #1A1A1A; border: none;"
            " border-bottom: 1px solid #2A2A2A; color: #CCCCCC;"
            " padding: 8px 10px; font-size: 12px; }"
            "QLineEdit:focus { border-bottom: 1px solid #3A3AFF; }"
        )
        self._search_box.textChanged.connect(self._on_search)
        sb_layout.addWidget(self._search_box)

        _NAV_BASE = (
            "QPushButton { background: transparent; border: none; border-left: 3px solid transparent;"
            " color: #777777; text-align: left; padding: 9px 12px; font-size: 12px; }"
            "QPushButton:hover { background: #1C1C1C; color: #CCCCCC; }"
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
            "font-size: 11px; font-weight: bold; color: #555555;"
            " letter-spacing: 1px; text-transform: uppercase;"
        )
        hdr_layout.addWidget(self._cat_label)
        hdr_layout.addStretch()

        self._filter_box = QLineEdit()
        self._filter_box.setPlaceholderText("Filter this page…")
        self._filter_box.setToolTip("Filters buttons visible on the current category page")
        self._filter_box.setFixedWidth(170)
        self._filter_box.setStyleSheet(
            "QLineEdit { background: #212121; border: 1px solid #2A2A2A;"
            " color: #CCCCCC; padding: 4px 8px; font-size: 11px; border-radius: 3px; }"
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
        divider.setStyleSheet("background: #2A2A2A;")

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
            lbl.setStyleSheet("color: #555555; padding: 16px;")
            self._search_layout.addWidget(lbl)
            return

        count_lbl = QLabel(f"  {len(results)} tool{'s' if len(results) != 1 else ''} found")
        count_lbl.setStyleSheet("color: #555555; font-size: 11px; padding: 6px 8px 2px 8px;")
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
                "font-size: 9px; color: #555555; background: #1E1E1E;"
                " border: 1px solid #2A2A2A; border-radius: 3px; padding: 2px 4px;"
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
        color = "#44FF88" if ok else "#FF4444"
        self._sbar.setStyleSheet(f"QStatusBar {{ color: {color}; }}")
        self._sbar.showMessage(msg, 5000)

    def closeEvent(self, event) -> None:
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

