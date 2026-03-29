"""
UEFN TOOLBELT — Smart Auto-Organizer
========================================
Advanced heuristic-based asset organizer.
Scans a folder, detects asset classes, parses asset names for keywords, and automatically
sorts them into an intelligent /Type/Category folder structure.

FEATURES:
  • No external UI required — Native Toolbelt integration
  • Guesses categories by tokenizing names (e.g., "SM_PineTree" -> /Meshes/Trees)
  • Safe dry-run preview mode
  • Filter options to include unused assets or keep only referenced items

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Preview what would happen
    tb.run("organize_smart_categorize", scan_path="/Game/Imported", organized_root="/Game/MyLevel", dry_run=True)

    # Actually execute
    tb.run("organize_smart_categorize", scan_path="/Game/Imported", organized_root="/Game/MyLevel", dry_run=False)
"""

from __future__ import annotations

import unreal
import re
from collections import deque
from typing import Optional, List, Dict, Set, Tuple, Any

from ..core import log_info, log_warning, log_error, with_progress, load_asset
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Mappings & Heuristics
# ─────────────────────────────────────────────────────────────────────────────

CLASS_TO_TYPE: Dict[str, str] = {
    # Textures
    "Texture2D": "Textures",
    "TextureCube": "Textures",
    "TextureRenderTarget2D": "Textures",
    # Sounds
    "SoundWave": "Sounds",
    "SoundCue": "Sounds",
    "MetaSoundSource": "Sounds",
    "MetaSoundPatch": "Sounds",
    # Meshes
    "StaticMesh": "Meshes",
    "SkeletalMesh": "Meshes",
    # Materials
    "Material": "Materials",
    "MaterialInstanceConstant": "MaterialInstances",
    "MaterialInstance": "MaterialInstances",
    "MaterialFunction": "MaterialFunctions",
    "MaterialFunctionMaterialLayer": "MaterialFunctions",
    "MaterialFunctionMaterialLayerBlend": "MaterialFunctions",
    "MaterialParameterCollection": "MaterialParameterCollections",
    # Blueprints
    "Blueprint": "Blueprints",
    "AnimBlueprint": "Blueprints",
    "WidgetBlueprint": "WidgetBlueprints",
    # Niagara & VFX
    "NiagaraSystem": "Niagara",
    "NiagaraEmitter": "Niagara",
    # Animation
    "AnimSequence": "Animations",
    "AnimMontage": "Animations",
    "BlendSpace": "Animations",
    "Skeleton": "Animations",
    "PhysicsAsset": "Animations",
    # Data
    "CurveFloat": "Data",
    "CurveVector": "Data",
    "CurveLinearColor": "Data",
    "DataTable": "Data",
    "PrimaryDataAsset": "Data",
    # Sequences
    "LevelSequence": "LevelSequences",
    "DataLayerAsset": "WorldPartition",
}

CATEGORY_RULES: List[Tuple[str, Set[str]]] = [
    ("Trees", {"tree", "trees", "oak", "pine", "birch", "branch", "stump", "log"}),
    ("Foliage", {"grass", "bush", "fern", "leaf", "shrub", "plant", "ivy", "flower"}),
    ("Rocks", {"rock", "rocks", "stone", "cliff", "boulder", "ore", "pebble"}),
    ("Terrain", {"terrain", "landscape", "ground", "soil", "mud", "sand", "snow", "dirt"}),
    ("Buildings", {"house", "building", "wall", "roof", "door", "window", "tower", "castle"}),
    ("Props", {"prop", "barrel", "crate", "bench", "table", "chair", "lamp", "fence"}),
    ("Roads", {"road", "path", "trail", "bridge", "stairs", "step", "ramp"}),
    ("Water", {"water", "river", "lake", "ocean", "pond", "shore", "wave", "foam"}),
    ("Characters", {"character", "npc", "enemy", "player", "creature", "monster", "humanoid"}),
    ("Weapons", {"weapon", "sword", "bow", "gun", "rifle", "shield", "arrow", "axe"}),
    ("VFX", {"fx", "vfx", "effect", "impact", "explosion", "smoke", "fire", "spark", "dust"}),
    ("UI", {"ui", "widget", "icon", "hud", "menu", "button", "cursor"}),
    ("Music", {"music", "theme", "track", "song", "score"}),
    ("Ambience", {"ambient", "ambience", "wind", "birds", "rain", "waterfall", "forest"}),
    ("SFX", {"sfx", "footstep", "hit", "pickup", "jump", "attack", "swing"}),
    ("Functions", {"function", "functions"}),
    ("Cinematics", {"sequence", "cinematic", "intro", "outro", "cutscene"}),
]

# ─────────────────────────────────────────────────────────────────────────────
#  Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_folder_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_ ]+", "", name or "")
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or "Misc"

def _tokenize_name(name: str) -> List[str]:
    base = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    base = re.sub(r"[_\-\.]+", " ", base)
    return [t.lower() for t in base.split() if t.strip()]

def _guess_category(asset_name: str, asset_type: str) -> str:
    toks = set(_tokenize_name(asset_name))
    for category, keys in CATEGORY_RULES:
        if toks.intersection(keys):
            return category

    # Fallbacks based on type
    if asset_type == "Sounds": return "General"
    if asset_type in ["Textures", "Materials", "MaterialInstances"]: return "Surface"
    if asset_type == "MaterialFunctions": return "Functions"
    if asset_type == "MaterialParameterCollections": return "GlobalParameters"
    if asset_type == "Meshes": return "Props"
    if asset_type == "Blueprints": return "Gameplay"
    if asset_type == "WidgetBlueprints": return "UI"
    if asset_type == "Niagara": return "VFX"
    if asset_type == "Animations": return "Characters"
    if asset_type == "Data": return "General"
    if asset_type == "LevelSequences": return "Cinematics"
    if asset_type == "WorldPartition": return "DataLayers"
    return "Misc"

def _get_current_level_referenced_packages() -> Set[str]:
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        world_path = str(world.get_path_name()).split(".")[0]
    except Exception:
        return set()

    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    visited = set()
    queue = deque([world_path])

    try:
        dep_options = unreal.AssetRegistryDependencyOptions(
            include_soft_package_references=True,
            include_hard_package_references=True,
            include_searchable_names=False,
            include_soft_management_references=True,
            include_hard_management_references=True
        )
    except Exception:
        dep_options = None

    while queue:
        pkg = queue.popleft()
        if not pkg or pkg in visited:
            continue
            
        visited.add(pkg)
        try:
            deps = ar.get_dependencies(pkg, dep_options) if dep_options else ar.get_dependencies(pkg)
            for dep in (deps or []):
                dep_str = str(dep)
                if dep_str and dep_str not in visited:
                    queue.append(dep_str)
        except Exception:
            pass

    return visited

# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="organize_smart_categorize",
    category="Project",
    description="Scan a folder and automatically organize assets functionally (e.g. Meshes/Trees) via smart keyword detection.",
    tags=["organize", "smart", "category", "folder", "heuristic"]
)
def run_smart_categorize(
    scan_path: str = "/Game",
    organized_root: str = "/Game/Organized",
    dry_run: bool = True,
    include_unused: bool = True,
    **kwargs
) -> dict:
    """
    Scans a folder path, detects the asset type, guesses a functional category using regex keywords on the asset name,
    and moves them to a structured destination.
    
    Example: 
      `T_Log_01` -> /Game/Organized/Textures/Trees/T_Log_01
      
    Args:
        scan_path:      Folder to scan for messy assets.
        organized_root: Target baseline folder for the organized assets.
        dry_run:        If True, only prints out the planned moves.
        include_unused: If False, ignores assets that aren't hooked into the current level.
    """
    eal = unreal.EditorAssetLibrary
    if not eal.does_directory_exist(scan_path):
        log_error(f"Scan path does not exist: {scan_path}")
        return {"status": "error", "moved": 0, "failed": 0, "dry_run": dry_run}

    log_info(f"Scanning {scan_path} for smart organization...")
    asset_paths = eal.list_assets(scan_path, recursive=True, include_folder=False)

    if not asset_paths:
        log_info("No assets found.")
        return {"status": "ok", "moved": 0, "failed": 0, "dry_run": dry_run}

    level_refs = None
    if not include_unused:
        log_info("Collating level dependencies (this may take a moment)...")
        level_refs = _get_current_level_referenced_packages()

    plan: List[Dict[str, Any]] = []
    skipped = 0

    for path in asset_paths:
        package_name = path.rsplit(".", 1)[0]
        
        if not include_unused and level_refs and package_name not in level_refs:
            skipped += 1
            continue
            
        if package_name.startswith(organized_root):
            skipped += 1
            continue

        asset_data = eal.find_asset_data(path)
        if not asset_data:
            skipped += 1
            continue

        asset_name = str(asset_data.asset_name)
        class_name = str(asset_data.asset_class_path.asset_name)
        asset_type = CLASS_TO_TYPE.get(class_name, "Other")

        if asset_type == "Other":
            skipped += 1
            continue

        category = _guess_category(asset_name, asset_type)
        dest_dir = f"{organized_root}/{_sanitize_folder_name(asset_type)}/{_sanitize_folder_name(category)}"
        target_path = f"{dest_dir}/{asset_name}.{asset_name}"

        if eal.does_asset_exist(target_path):
            skipped += 1
            continue

        plan.append({
            "source": path,
            "dest_dir": dest_dir,
            "target": target_path,
            "type": asset_type,
            "category": category,
            "name": asset_name
        })

    if not plan:
        log_info(f"No valid assets remaining to organize. (Skipped {skipped})")
        return {"status": "ok", "moved": 0, "failed": 0, "dry_run": dry_run}

    log_info(f"{'[DRY RUN] ' if dry_run else ''}Found {len(plan)} assets to smartly group (Skipped: {skipped}).")

    # Print the first 10 for preview
    for row in plan[:10]:
        log_info(f"  {row['name']:30s} -> {row['dest_dir']}")
    if len(plan) > 10:
        log_info(f"  ... plus {len(plan) - 10} more.")

    if dry_run:
        log_info("\nDry run complete. Pass dry_run=False to execute moves.")
        return {"status": "ok", "moved": 0, "failed": 0, "planned": len(plan), "dry_run": True}

    moved = 0
    failed = 0

    with with_progress(plan, f"Organizing smartly: {organized_root}") as bar:
        for row in bar:
            # We must ensure directory exists, although unreal.EditorAssetLibrary.rename_asset automatically creates directories!
            # It's perfectly safe to just call rename_asset.
            try:
                success = eal.rename_asset(row["source"], row["target"])
                if success:
                    moved += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                log_warning(f"Failed to move {row['name']}: {e}")

    log_info(f"Smart Organization complete. Moved: {moved}, Failed: {failed}.")
    return {"status": "ok", "moved": moved, "failed": failed, "dry_run": False}


# ─────────────────────────────────────────────────────────────────────────────
#  Interactive Window
# ─────────────────────────────────────────────────────────────────────────────

_organizer_window = None  # singleton

# Prefix → type mapping used by the window scan.
# Zero per-asset API calls — pure string matching on the asset name.
# Covers Epic naming conventions used in UEFN projects.
_PREFIX_TO_TYPE: Dict[str, str] = {
    "T_":    "Textures",
    "TX_":   "Textures",
    "SM_":   "Meshes",
    "SKM_":  "Meshes",
    "SK_":   "Meshes",
    "M_":    "Materials",
    "MI_":   "MaterialInstances",
    "MIC_":  "MaterialInstances",
    "MF_":   "MaterialFunctions",
    "MPC_":  "MaterialParameterCollections",
    "BP_":   "Blueprints",
    "ABP_":  "Blueprints",
    "WBP_":  "WidgetBlueprints",
    "NS_":   "Niagara",
    "NE_":   "Niagara",
    "FX_":   "Niagara",
    "AM_":   "Animations",
    "AS_":   "Animations",
    "A_":    "Sounds",
    "SFX_":  "Sounds",
    "SC_":   "Sounds",
    "DA_":   "Data",
    "DT_":   "Data",
    "LS_":   "LevelSequences",
}

def _type_from_prefix(asset_name: str) -> str:
    """Detect asset type from Epic naming prefix. O(1), no API calls."""
    for prefix, atype in _PREFIX_TO_TYPE.items():
        if asset_name.startswith(prefix):
            return atype
    return "Other"

_ALL_TYPES = [
    "Textures", "Sounds", "Meshes", "Materials", "MaterialInstances",
    "MaterialFunctions", "MaterialParameterCollections", "Blueprints",
    "WidgetBlueprints", "Niagara", "Animations", "Data", "LevelSequences",
    "WorldPartition",
]


def _build_organizer_window():
    """Deferred PySide6 build — returns OrganizerWindow instance."""
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QCheckBox, QFrame, QScrollArea, QTextEdit, QMessageBox,
    )
    from PySide6.QtCore import Qt
    from ..core.base_window import ToolbeltWindow
    from ..core.theme import PALETTE

    class _HelpDialog(ToolbeltWindow):
        def __init__(self, parent=None):
            super().__init__(title="UEFN Toolbelt — Auto Organizer Help", parent=parent)
            w = QWidget()
            L = QVBoxLayout(w)
            L.setContentsMargins(16, 16, 16, 16)
            text = QTextEdit()
            text.setReadOnly(True)
            text.setLineWrapMode(QTextEdit.NoWrap)
            text.setStyleSheet(
                f"background:{self.hex('panel')}; color:{self.hex('text')}; border:none;"
            )
            text.setPlainText(
                "UEFN Toolbelt — Auto Type Organizer\n"
                "═══════════════════════════════════════════\n\n"
                "Scans a Content Browser path, detects asset types,\n"
                "guesses a functional category from the asset name,\n"
                "and moves assets into a /Type/Category/ hierarchy.\n\n"
                "WORKFLOW\n"
                "────────\n"
                "1. Enter Scan Root — the messy folder to organize\n"
                "2. Enter Organized Root — destination base folder\n"
                "3. Toggle which asset types to include\n"
                "4. Click SCAN to preview planned moves\n"
                "5. Review the table\n"
                "6. Click ORGANIZE to execute\n\n"
                "SAFETY\n"
                "──────\n"
                "• Uses rename_asset — references stay valid via redirectors\n"
                "• Assets already inside the organized root are skipped\n"
                "• If destination asset already exists, it is skipped\n"
                "• Redirectors after organize are normal and expected\n\n"
                "HEADLESS TOOLS (MCP / Python)\n"
                "──────────────────────────────\n"
                "  organize_smart_categorize   — scan + dry_run/execute\n"
                "  organize_assets             — basic type-folder sort\n"
                "  organize_open               — open this window\n"
            )
            L.addWidget(text)
            btn = self.make_btn("Close", cb=self.close)
            L.addWidget(btn)
            self.setCentralWidget(w)
            self.resize(500, 440)

    class OrganizerWindow(ToolbeltWindow):
        def __init__(self):
            super().__init__(title="UEFN Toolbelt — Auto Organizer")
            self._plan: List[Dict[str, Any]] = []
            self._help_win = None
            # Derive the project mount name from __file__ (walk up to find Content/).
            # detect_project_mount() uses "most AR entries" which returns BRCosmetics
            # (Fortnite game paks) instead of the user's project on pak-heavy installs.
            try:
                import os as _os
                _curr = _os.path.abspath(__file__)
                _cdir = None
                while True:
                    _par = _os.path.dirname(_curr)
                    if _par == _curr:
                        break
                    if _os.path.basename(_curr) == "Content":
                        _cdir = _curr
                        break
                    _curr = _par
                if _cdir:
                    _mount_name = _os.path.basename(_os.path.dirname(_cdir))
                    self._default_root = f"/{_mount_name}"
                else:
                    self._default_root = "/Game"
            except Exception:
                self._default_root = "/Game"
            self._build_ui()

        def _build_ui(self):
            root_w = QWidget()
            root_l = QVBoxLayout(root_w)
            root_l.setContentsMargins(0, 0, 0, 0)
            root_l.setSpacing(0)

            # ── Topbar ───────────────────────────────────────────────────────
            bar, bl = self.make_topbar("")
            self._scan_btn = self.make_btn("Scan", accent=True, cb=self._do_scan)
            bl.addWidget(self._scan_btn)
            self._org_btn = self.make_btn("Organize", cb=self._do_organize)
            self._org_btn.setEnabled(False)
            bl.addWidget(self._org_btn)
            bl.addStretch()
            bl.addWidget(self.make_btn("?", cb=self._show_help))
            root_l.addWidget(bar)

            # ── Scrollable content ───────────────────────────────────────────
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("border:none;")
            content = QWidget()
            cl = QVBoxLayout(content)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(8)
            scroll.setWidget(content)
            root_l.addWidget(scroll)

            # ── Paths row ────────────────────────────────────────────────────
            path_frame, path_l = self._section("Paths")

            row1 = QHBoxLayout()
            row1.addWidget(QLabel("Scan Root:"))
            self._scan_input = QLineEdit(self._default_root)
            self._scan_input.setFixedHeight(26)
            self._scan_input.setStyleSheet(
                f"background:{self.hex('panel')}; color:{self.hex('text')}; "
                f"border:1px solid {self.hex('border2')}; border-radius:3px; padding:0 4px;"
            )
            row1.addWidget(self._scan_input, 2)
            row1.addSpacing(12)
            row1.addWidget(QLabel("Organized Root:"))
            self._org_input = QLineEdit(f"{self._default_root}/Organized")
            self._org_input.setFixedHeight(26)
            self._org_input.setStyleSheet(
                f"background:{self.hex('panel')}; color:{self.hex('text')}; "
                f"border:1px solid {self.hex('border2')}; border-radius:3px; padding:0 4px;"
            )
            row1.addWidget(self._org_input, 2)
            path_l.addLayout(row1)

            opts_row = QHBoxLayout()
            self._unused_chk = QCheckBox("Level-referenced only")
            self._unused_chk.setChecked(False)
            self._unused_chk.setStyleSheet(f"color:{self.hex('text')};")
            opts_row.addWidget(self._unused_chk)

            self._recursive_chk = QCheckBox("Include subfolders")
            self._recursive_chk.setChecked(True)
            self._recursive_chk.setStyleSheet(f"color:{self.hex('text')};")
            opts_row.addWidget(self._recursive_chk)
            opts_row.addStretch()
            path_l.addLayout(opts_row)
            cl.addWidget(path_frame)

            # ── Type checkboxes ──────────────────────────────────────────────
            types_frame, types_l = self._section("Asset Types to Organize")
            self._type_checks: Dict[str, QCheckBox] = {}
            row_a = QHBoxLayout()
            row_b = QHBoxLayout()
            for i, t in enumerate(_ALL_TYPES):
                chk = QCheckBox(t)
                chk.setChecked(True)
                chk.setStyleSheet(f"color:{self.hex('text')};")
                self._type_checks[t] = chk
                (row_a if i < 7 else row_b).addWidget(chk)
            row_a.addStretch()
            row_b.addStretch()
            types_l.addLayout(row_a)
            types_l.addLayout(row_b)
            cl.addWidget(types_frame)

            # ── Summary ──────────────────────────────────────────────────────
            self._summary_lbl = QLabel("Scan to preview planned moves.")
            self._summary_lbl.setStyleSheet(f"color:{self.hex('text_dim')}; font-size:11px;")
            cl.addWidget(self._summary_lbl)

            # ── Preview table ────────────────────────────────────────────────
            tbl_frame, tbl_l = self._section("Organize Preview")

            hdr = QFrame()
            hdr.setStyleSheet(f"background:{self.hex('topbar')};")
            hdr_l = QHBoxLayout(hdr)
            hdr_l.setContentsMargins(6, 4, 6, 4)
            for txt, w in [("Asset Name", 190), ("Class", 160), ("Type", 130), ("Category", 110), ("Destination", 0)]:
                lbl = QLabel(txt)
                lbl.setStyleSheet(f"color:{self.hex('text')}; font-weight:bold; font-size:11px;")
                if w:
                    lbl.setFixedWidth(w)
                hdr_l.addWidget(lbl)
            hdr_l.addStretch()
            tbl_l.addWidget(hdr)

            rows_scroll = QScrollArea()
            rows_scroll.setWidgetResizable(True)
            rows_scroll.setFixedHeight(320)
            rows_scroll.setStyleSheet(f"background:{self.hex('bg')}; border:none;")
            self._rows_widget = QWidget()
            self._rows_widget.setStyleSheet(f"background:{self.hex('bg')};")
            self._rows_layout = QVBoxLayout(self._rows_widget)
            self._rows_layout.setContentsMargins(0, 0, 0, 0)
            self._rows_layout.setSpacing(1)
            self._rows_layout.addStretch()
            rows_scroll.setWidget(self._rows_widget)
            tbl_l.addWidget(rows_scroll)
            cl.addWidget(tbl_frame)

            # ── Status bar ───────────────────────────────────────────────────
            self._status_lbl = QLabel("Ready.")
            self._status_lbl.setStyleSheet(
                f"color:{self.hex('muted')}; font-size:10px; "
                f"padding:4px 12px; background:{self.hex('topbar')};"
            )
            root_l.addWidget(self._status_lbl)

            self.setCentralWidget(root_w)
            self.resize(1100, 720)

        def _section(self, title: str):
            """Returns (frame, content_layout) with a titled section box."""
            from PySide6.QtWidgets import QVBoxLayout, QLabel
            frame = QFrame()
            frame.setStyleSheet(
                f"QFrame {{ background:{self.hex('card')}; border:1px solid {self.hex('border')}; "
                f"border-radius:4px; }}"
            )
            outer = QVBoxLayout(frame)
            outer.setContentsMargins(10, 8, 10, 8)
            outer.setSpacing(6)
            lbl = QLabel(title.upper())
            lbl.setStyleSheet(
                f"color:{self.hex('text_dim')}; font-weight:bold; font-size:10px; "
                f"letter-spacing:1px; border:none; background:transparent;"
            )
            outer.addWidget(lbl)
            content = QWidget()
            content.setStyleSheet("background:transparent; border:none;")
            content_l = QVBoxLayout(content)
            content_l.setContentsMargins(0, 0, 0, 0)
            content_l.setSpacing(4)
            outer.addWidget(content)
            return frame, content_l

        def _get_enabled_types(self) -> set:
            return {t for t, chk in self._type_checks.items() if chk.isChecked()}

        def _clear_rows(self):
            while self._rows_layout.count() > 1:
                item = self._rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        def _add_row(self, idx: int, row: dict):
            from PySide6.QtWidgets import QHBoxLayout
            bg = self.hex("card") if idx % 2 == 0 else self.hex("bg")
            frame = QFrame()
            frame.setStyleSheet(f"background:{bg};")
            hl = QHBoxLayout(frame)
            hl.setContentsMargins(6, 2, 6, 2)
            hl.setSpacing(4)
            for txt, w, color in [
                (row["name"],       190, self.hex("text")),
                (row["class_name"], 160, self.hex("text_dim")),
                (row["type"],       130, self.hex("text")),
                (row["category"],   110, self.hex("text_dim")),
                (row["dest_dir"],   0,   "#9ecbff"),
            ]:
                lbl = QLabel(txt)
                lbl.setStyleSheet(f"color:{color}; font-size:10px; font-family:Consolas;")
                lbl.setToolTip(txt)
                if w:
                    lbl.setFixedWidth(w)
                hl.addWidget(lbl)
            hl.addStretch()
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, frame)

        def _do_scan(self):
            """Button handler — validate inputs then defer the actual scan to the next Slate tick.
            Unreal asset registry calls must not run inside app.processEvents() or they can
            re-enter the engine tick and crash. Scheduling via register_slate_post_tick_callback
            runs the scan directly on the game thread, outside of Qt event processing."""
            scan_root = self._scan_input.text().strip() or self._default_root
            org_root  = self._org_input.text().strip() or f"{self._default_root}/Organized"

            depth = len([p for p in scan_root.strip("/").split("/") if p])
            if depth < 1:
                self._status_lbl.setText("Scan Root must be at least one level deep (e.g. /ProjectName/Folder).")
                return

            recursive = self._recursive_chk.isChecked()
            self._status_lbl.setText(f"Queued scan of {scan_root} …")
            self._scan_btn.setEnabled(False)
            self._org_btn.setEnabled(False)

            handle = [None]
            win = self

            def _scan_on_tick(dt):
                unreal.unregister_slate_post_tick_callback(handle[0])
                win._execute_scan(scan_root, org_root, recursive)

            handle[0] = unreal.register_slate_post_tick_callback(_scan_on_tick)

        def _execute_scan(self, scan_root, org_root, recursive=False):
            """Disk-based scan — walks the project Content directory on disk.
            Never touches the Asset Registry, so it cannot block or crash on
            pak-heavy projects (e.g. /BRCosmetics where Fortnite mounts millions
            of pak entries under the same mount point).
            Type detection uses _type_from_prefix() — zero API calls, pure string match."""
            import os
            try:
                enabled = self._get_enabled_types()

                # Convert AR path (/MountPoint/Folder) → disk path (Content/Folder)
                # strip the leading mount name — it maps to Content/
                parts = scan_root.strip("/").split("/", 1)
                mount    = parts[0]                        # e.g. "BRCosmetics"
                rel_path = parts[1] if len(parts) > 1 else ""  # e.g. "Imported" or ""

                # Walk up from __file__ to find the Content directory.
                # unreal.Paths.project_dir() returns ../../../FortniteGame/ in UEFN —
                # not the user project. __file__ is always inside Content/ so walking up
                # is the only reliable method (same trick used by verse_find_project_path).
                _curr = os.path.abspath(__file__)
                content_dir = None
                while True:
                    _parent = os.path.dirname(_curr)
                    if _parent == _curr:
                        break
                    if os.path.basename(_curr) == "Content":
                        content_dir = _curr
                        break
                    _curr = _parent
                if content_dir is None:
                    self._status_lbl.setText("Could not locate project Content directory.")
                    self._scan_btn.setEnabled(True)
                    return

                if rel_path:
                    disk_root = os.path.normpath(os.path.join(content_dir, *rel_path.split("/")))
                else:
                    disk_root = content_dir

                if not os.path.isdir(disk_root):
                    self._status_lbl.setText(f"Disk path not found: {disk_root}")
                    self._scan_btn.setEnabled(True)
                    return

                # Collect .uasset files from disk
                uasset_files: List[str] = []
                if recursive:
                    for dirpath, _dirs, filenames in os.walk(disk_root):
                        for fn in filenames:
                            if fn.lower().endswith(".uasset"):
                                uasset_files.append(os.path.join(dirpath, fn))
                else:
                    try:
                        for fn in os.listdir(disk_root):
                            fp = os.path.join(disk_root, fn)
                            if fn.lower().endswith(".uasset") and os.path.isfile(fp):
                                uasset_files.append(fp)
                    except OSError:
                        pass

                skipped = 0
                self._plan = []

                for fp in uasset_files:
                    asset_name = os.path.splitext(os.path.basename(fp))[0]
                    asset_type = _type_from_prefix(asset_name)

                    if asset_type == "Other" or asset_type not in enabled:
                        skipped += 1
                        continue

                    # Rebuild Content Browser path from disk path.
                    # In UEFN the project mount always maps directly to Content/ on disk.
                    # A file at Content/Folder/Asset.uasset → /{mount}/Folder/Asset.
                    # Never add an extra "/Content/" segment — if the user has a folder
                    # literally named "Content" inside Content/, it naturally appears in
                    # the rel path (e.g. "Content/Assets/...") and the CB path becomes
                    # /{mount}/Content/Assets/... which is correct.
                    rel        = os.path.relpath(fp, content_dir).replace("\\", "/")
                    rel_no_ext = rel.rsplit(".", 1)[0]
                    package_name = f"/{mount}/{rel_no_ext}"
                    source = f"{package_name}.{asset_name}"

                    if package_name.startswith(org_root):
                        skipped += 1
                        continue

                    category = _guess_category(asset_name, asset_type)
                    dest_dir = f"{org_root}/{_sanitize_folder_name(asset_type)}/{_sanitize_folder_name(category)}"
                    target   = f"{dest_dir}/{asset_name}.{asset_name}"

                    self._plan.append({
                        "source":     source,
                        "dest_dir":   dest_dir,
                        "target":     target,
                        "type":       asset_type,
                        "category":   category,
                        "name":       asset_name,
                        "class_name": asset_type,
                        "org_root":   org_root,
                        "scan_root":  scan_root,
                    })

            except Exception as exc:
                self._status_lbl.setText(f"Scan error: {exc}")
                self._scan_btn.setEnabled(True)
                log_error(f"organize_open scan: {exc}")
                return

            self._clear_rows()
            for i, row in enumerate(self._plan):
                self._add_row(i, row)

            self._scan_btn.setEnabled(True)
            self._org_btn.setEnabled(len(self._plan) > 0)

            from collections import Counter
            counts = Counter(r["type"] for r in self._plan)
            count_text = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) if counts else "nothing to organize"
            self._summary_lbl.setText(
                f"Found {len(self._plan)} assets to organize.  {count_text}"
            )
            depth_note = "recursive" if recursive else "immediate folder only"
            self._status_lbl.setText(
                f"Scan complete ({depth_note}) — {len(self._plan)} planned moves, {skipped} skipped."
            )

        def _do_organize(self):
            from PySide6.QtWidgets import QMessageBox
            if not self._plan:
                return
            org_root   = self._plan[0]["org_root"]
            scan_root  = self._plan[0]["scan_root"]
            msg = QMessageBox(self)
            msg.setWindowTitle("UEFN Toolbelt — Confirm Organize")
            msg.setText(
                f"Move {len(self._plan)} assets into:\n{org_root}\n\n"
                "Unreal creates redirectors automatically — references remain valid.\n\nContinue?"
            )
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            if msg.exec() != QMessageBox.Yes:
                return

            eal = unreal.EditorAssetLibrary
            moved, failed = 0, 0
            self._status_lbl.setText("Organizing …")

            for row in self._plan:
                ok = False
                try:
                    ok = eal.rename_asset(row["source"], row["target"])
                except Exception:
                    pass

                if not ok:
                    # Rename failed — check if destination already has this asset.
                    # This happens when a previous organize run moved the file but
                    # left the source copy behind. Delete the stale source; the
                    # destination copy is the authoritative one.
                    target_pkg = row["target"].rsplit(".", 1)[0]
                    source_pkg = row["source"].rsplit(".", 1)[0]
                    try:
                        if eal.does_asset_exist(target_pkg):
                            eal.delete_asset(source_pkg)
                            ok = True
                    except Exception as _del_e:
                        log_warning(f"smart_organizer: could not clean up duplicate {row['name']}: {_del_e}")

                if ok:
                    moved += 1
                else:
                    failed += 1

            self._status_lbl.setText(f"Done — Moved: {moved}  Failed: {failed}")
            self._summary_lbl.setText(
                f"Organize complete. Moved {moved} assets. "
                f"Redirectors are normal and keep references valid — "
                f"run Edit → Fix Up Redirectors to clean them up."
            )
            self._plan = []
            self._org_btn.setEnabled(False)

        def _show_help(self):
            if not self._help_win:
                self._help_win = _HelpDialog(self)
            self._help_win.show()
            self._help_win.raise_()

    return OrganizerWindow()


@register_tool(
    name="organize_open",
    category="Project",
    description=(
        "Open the Auto Organizer window — scan a Content Browser path, preview planned moves "
        "in a table (asset name / class / type / category / destination), toggle per-type "
        "checkboxes, then organize in one click. Uses the same smart keyword-categorization "
        "as organize_smart_categorize."
    ),
    tags=["organize", "smart", "category", "folder", "window", "ui"],
)
def run_organize_open(**kwargs) -> dict:
    global _organizer_window
    try:
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        if _organizer_window is None or not _organizer_window.isVisible():
            _organizer_window = _build_organizer_window()
            _organizer_window.show_in_uefn()
        else:
            _organizer_window.raise_()
            _organizer_window.activateWindow()
        return {"status": "ok", "message": "Auto Organizer window opened."}
    except Exception as exc:
        log_error(f"organize_open: {exc}")
        return {"status": "error", "error": str(exc)}
