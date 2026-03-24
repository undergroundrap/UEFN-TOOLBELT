"""
UEFN TOOLBELT — Prefab Asset Migrator
========================================
Exports prefab assets (+ all dependencies) to another UEFN project cleanly.

Two workflows:
  • Export tab    — select assets in Content Browser, resolve deps, export
  • Paste Export  — paste Ctrl+C prefab T3D clipboard text, auto-parse asset
                    paths, resolve deps, export

Key features vs. Epic's built-in migration:
  • Dependency graph walk via AssetRegistry — meshes, materials, textures,
    Verse components all come along automatically
  • Flatten option — copies everything into one destination folder instead of
    recreating the entire source project folder tree
  • Cross-project copy via raw .uasset file copy (shutil) — works even when
    migrate_packages() is sandboxed in UEFN
  • Diff-aware — skips assets that already exist at the destination (dry-run
    shows what would be copied before you commit)
"""

from __future__ import annotations

import os
import re
import shutil
from typing import List, Set, Dict, Tuple

import unreal

from ..core import log_info, log_error, log_warning
from ..registry import register_tool

# ── PySide6 guard ─────────────────────────────────────────────────────────────
try:
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget,
        QListWidgetItem, QFileDialog, QCheckBox, QTabWidget,
        QSplitter, QFrame, QScrollArea,
    )
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QColor, QFont
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

# ── Asset path helpers ────────────────────────────────────────────────────────

# Matches any /MountPoint/... path in T3D text (quoted or unquoted).
# Catches /Game/, /SPUNCHBROTHUS/, /MyProject/ etc.
# Engine/Script/Transient paths are filtered out in _parse_t3d.
_T3D_PATH_RE = re.compile(
    r"['\"]?(\/[A-Za-z][A-Za-z0-9_]+(?:\/[A-Za-z0-9_\-\.]+)+)['\"]?",
)

# Mounts to ignore when parsing T3D — engine/runtime paths, not user assets
_T3D_SKIP_MOUNTS = {
    "/Engine", "/Script", "/Transient", "/FortniteGame", "/Fortnite",
    "/Paper2D", "/Plugin", "/Plugins", "/Epic", "/Fortnite.com",
}


def _normalize_pkg(path: str) -> str:
    """Strip .AssetName suffix so we always work with package paths."""
    if "." in path.rsplit("/", 1)[-1]:
        path = path.rsplit(".", 1)[0]
    return path.rstrip("/")


def _pkg_to_asset(pkg: str) -> str:
    """'/Game/Folder/SM_Wall' → '/Game/Folder/SM_Wall.SM_Wall'"""
    name = pkg.rsplit("/", 1)[-1]
    return f"{pkg}.{name}"


def _pkg_to_disk(pkg: str, content_dir: str) -> str:
    """'/MountPoint/Folder/SM_Wall' → '<content_dir>/Folder/SM_Wall.uasset'"""
    parts = pkg.lstrip("/").split("/", 1)
    relative = parts[1] if len(parts) > 1 else parts[0]
    return os.path.join(content_dir, relative.replace("/", os.sep) + ".uasset")


def _parse_t3d(text: str) -> List[str]:
    """
    Extract all unique project asset package paths from T3D clipboard text.
    Handles /Game/... paths AND project-mount paths like /SPUNCHBROTHUS/...
    Filters out engine, script, and transient runtime paths.
    """
    seen: Set[str] = set()
    for m in _T3D_PATH_RE.finditer(text):
        raw = m.group(1)
        pkg = _normalize_pkg(raw)
        # Skip engine/runtime mounts
        if any(pkg.startswith(s) for s in _T3D_SKIP_MOUNTS):
            continue
        # Must have at least two path segments to be a real asset
        if pkg.count("/") < 2:
            continue
        if pkg not in seen:
            seen.add(pkg)
    return sorted(seen)


# ── Dependency resolver ───────────────────────────────────────────────────────

def _resolve_deps(packages: List[str], include_deps: bool = True) -> Tuple[Set[str], List[str]]:
    """
    Walk the AssetRegistry dependency graph from the seed packages.
    Returns (resolved_set, warnings_list).
    Only /Game/ packages are included — Engine/FortniteGame paths are skipped.
    """
    ar = unreal.AssetRegistryHelpers.get_asset_registry()

    dep_options = unreal.AssetRegistryDependencyOptions()
    dep_options.include_hard_package_references = True
    dep_options.include_soft_package_references = True
    dep_options.include_game_package_references = True
    dep_options.include_editor_only_package_references = False
    dep_options.include_searchable_names = False
    dep_options.include_soft_management_references = False
    dep_options.include_hard_management_references = False

    # Skip engine/plugin paths — keep /Game/ and any project mount point (e.g. /MyProject/)
    _SKIP_PREFIXES = ("/Engine/", "/FortniteGame/", "/Paper2D/", "/Script/")

    visited: Set[str] = set()
    warnings: List[str] = []
    queue = [_normalize_pkg(p) for p in packages]

    while queue:
        pkg = queue.pop()
        if pkg in visited:
            continue
        visited.add(pkg)

        if not include_deps:
            continue

        try:
            deps = ar.get_dependencies(pkg, dep_options) or []
            for dep in deps:
                dep_str = _normalize_pkg(str(dep))
                if dep_str and not any(dep_str.startswith(s) for s in _SKIP_PREFIXES) and dep_str not in visited:
                    queue.append(dep_str)
        except Exception as exc:
            warnings.append(f"dep scan failed for {pkg}: {exc}")

    return visited, warnings


# ── Export engines ────────────────────────────────────────────────────────────

def _export_to_disk(
    packages: Set[str],
    src_content: str,
    dst_content: str,
    flatten: bool,
    overwrite: bool,
    dry_run: bool,
) -> Dict[str, List[str]]:
    """
    Copy raw .uasset files from src_content to dst_content.
    Returns {"ok": [...], "skip": [...], "missing": [...], "error": [...]}.
    """
    results: Dict[str, List[str]] = {"ok": [], "skip": [], "missing": [], "error": []}

    for pkg in sorted(packages):
        src_file = _pkg_to_disk(pkg, src_content)

        if not os.path.exists(src_file):
            results["missing"].append(pkg)
            continue

        asset_name = pkg.rsplit("/", 1)[-1]
        if flatten:
            dst_file = os.path.join(dst_content, asset_name + ".uasset")
        else:
            relative = pkg[len("/Game/"):]
            dst_file = os.path.join(dst_content, relative.replace("/", os.sep) + ".uasset")

        if os.path.exists(dst_file) and not overwrite:
            results["skip"].append(pkg)
            continue

        if dry_run:
            results["ok"].append(f"[DRY] {pkg}")
            continue

        try:
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy2(src_file, dst_file)
            results["ok"].append(pkg)
        except Exception as exc:
            results["error"].append(f"{pkg}: {exc}")

    return results


def _export_within_project(
    packages: Set[str],
    dest_folder: str,
    flatten: bool,
    overwrite: bool,
    dry_run: bool,
) -> Dict[str, List[str]]:
    """
    Duplicate assets within the same project to dest_folder (/Game/... path).
    """
    eal = unreal.EditorAssetLibrary
    results: Dict[str, List[str]] = {"ok": [], "skip": [], "missing": [], "error": []}
    dest_folder = dest_folder.rstrip("/")

    for pkg in sorted(packages):
        asset_path = _pkg_to_asset(pkg)

        if not eal.does_asset_exist(asset_path):
            results["missing"].append(pkg)
            continue

        asset_name = pkg.rsplit("/", 1)[-1]
        if flatten:
            dst_pkg = f"{dest_folder}/{asset_name}"
        else:
            # Strip whatever mount point prefix the pkg uses (/Game/, /MyProject/, etc.)
            parts = pkg.lstrip("/").split("/", 1)
            relative = parts[1] if len(parts) > 1 else asset_name
            dst_pkg = f"{dest_folder}/{relative}"

        dst_asset = _pkg_to_asset(dst_pkg)

        if eal.does_asset_exist(dst_asset) and not overwrite:
            results["skip"].append(pkg)
            continue

        if dry_run:
            results["ok"].append(f"[DRY] {pkg} → {dst_pkg}")
            continue

        try:
            eal.duplicate_asset(asset_path, dst_pkg)
            eal.save_asset(dst_pkg, only_if_is_dirty=False)
            results["ok"].append(pkg)
        except Exception as exc:
            results["error"].append(f"{pkg}: {exc}")

    # Sync Content Browser so new folder appears immediately
    if not dry_run and results["ok"]:
        try:
            unreal.AssetRegistryHelpers.get_asset_registry().search_all_assets(True)
        except Exception:
            pass

    return results


# ── PySide6 window ────────────────────────────────────────────────────────────

if _PYSIDE6:
    try:
        from ..dashboard_pyside6 import _QSS as _DASH_QSS
    except Exception:
        _DASH_QSS = ""

    try:
        from ..core.base_window import ToolbeltWindow
    except Exception:
        from ..dashboard_pyside6 import ToolbeltWindow

    _LABEL_CSS  = "color:#AAAAAA; font-size:9pt;"
    _MUTED_CSS  = "color:#666666; font-size:8pt;"
    _INPUT_CSS  = (
        "background:#1A1A1A; color:#E0E0E0; border:1px solid #3A3A3A;"
        "border-radius:3px; padding:4px 6px; font-size:9pt;"
    )
    _BTN_CSS    = (
        "QPushButton{background:#252525; color:#E0E0E0; border:1px solid #3A3A3A;"
        "border-radius:3px; padding:4px 10px; font-size:9pt;}"
        "QPushButton:hover{background:#2E2E2E; border-color:#555;}"
        "QPushButton:pressed{background:#1A1A1A;}"
    )
    _ACCENT_CSS = (
        "QPushButton{background:#2A6099; color:#FFFFFF; border:1px solid #3A8FC7;"
        "border-radius:3px; padding:4px 10px; font-size:9pt; font-weight:600;}"
        "QPushButton:hover{background:#3A8FC7;}"
        "QPushButton:pressed{background:#1A4A70;}"
        "QPushButton:disabled{background:#1A1A1A; color:#555; border-color:#2A2A2A;}"
    )
    _LIST_CSS   = (
        "QListWidget{background:#141414; color:#CCCCCC; border:1px solid #2A2A2A;"
        "border-radius:3px; font-family:Consolas; font-size:8pt;}"
        "QListWidget::item:selected{background:#1E3A5F; color:#FFFFFF;}"
        "QListWidget::item:hover{background:#1A1A1A;}"
    )
    _LOG_CSS    = (
        "background:#0E0E0E; color:#AAAAAA; border:1px solid #2A2A2A;"
        "border-radius:3px; font-family:Consolas; font-size:8pt; padding:4px;"
    )

    def _div() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color:#2A2A2A;")
        return f

    def _lbl(text: str, muted: bool = False) -> QLabel:
        w = QLabel(text)
        w.setStyleSheet(_MUTED_CSS if muted else _LABEL_CSS)
        return w

    def _btn(text: str, accent: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setStyleSheet(_ACCENT_CSS if accent else _BTN_CSS)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _inp(placeholder: str = "", fixed_width: int = 0) -> QLineEdit:
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        w.setStyleSheet(_INPUT_CSS)
        w.setFixedHeight(28)
        if fixed_width:
            w.setFixedWidth(fixed_width)
        return w

    # ── Worker thread ──────────────────────────────────────────────────────

    class _ExportWorker(QThread):
        progress = Signal(str)   # log line
        finished = Signal(dict)  # results dict

        def __init__(self, packages, src_content, dst_content,
                     dest_game_folder, flatten, overwrite, dry_run,
                     cross_project):
            super().__init__()
            self._packages       = packages
            self._src_content    = src_content
            self._dst_content    = dst_content
            self._dest_folder    = dest_game_folder
            self._flatten        = flatten
            self._overwrite      = overwrite
            self._dry_run        = dry_run
            self._cross_project  = cross_project

        def run(self):
            if self._cross_project:
                r = _export_to_disk(
                    self._packages, self._src_content, self._dst_content,
                    self._flatten, self._overwrite, self._dry_run,
                )
            else:
                r = _export_within_project(
                    self._packages, self._dest_folder,
                    self._flatten, self._overwrite, self._dry_run,
                )
            self.finished.emit(r)

    # ── Shared path-row widget ─────────────────────────────────────────────

    class _PathRow(QWidget):
        def __init__(self, label: str, placeholder: str,
                     browse_dir: bool = True, parent=None):
            super().__init__(parent)
            lay = QHBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            lay.addWidget(_lbl(label))
            self.edit = _inp(placeholder)
            lay.addWidget(self.edit, 1)
            self._browse_dir = browse_dir
            btn = _btn("…")
            btn.setFixedWidth(32)
            btn.clicked.connect(self._browse)
            lay.addWidget(btn)

        def _browse(self):
            if self._browse_dir:
                path = QFileDialog.getExistingDirectory(self, "Select Folder")
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Select File")
            if path:
                self.edit.setText(path)

        @property
        def text(self) -> str:
            return self.edit.text().strip()

    # ── Help dialog ───────────────────────────────────────────────────────────

    class _HelpDialog(ToolbeltWindow):
        """Purpose, workflow, and reference for the Prefab Asset Migrator."""

        _CONTENT = """\
WHAT IS THIS?

The Prefab Asset Migrator copies assets — and all of their dependencies — from
your project to a new destination in one click. Where UEFN's built-in migration
can silently drop meshes, materials, or textures, this tool walks the full
dependency graph via the Asset Registry so every referenced asset comes along.

─────────────────────────────────────────────────────────────────────────

WHY IT WAS MADE

Working with prefabs across UEFN projects is painful. Copy-pasting actors between
projects leaves them broken because the assets they reference don't transfer.
Epic's migrate tool works but can drag in unwanted parent folders and gives no
dry-run preview. This tool was built to solve both problems cleanly.

─────────────────────────────────────────────────────────────────────────

TWO WORKFLOWS

  EXPORT TAB — start from the Content Browser
    1. Select assets in the UEFN Content Browser
    2. Click  + Add Selected from CB  — paths appear in the list
       (or select actors in the viewport → + Add Selected from Viewport
        to extract asset paths directly from placed actors using your assets)
    3. Click  Resolve Dependencies  — the full dependency closure is shown
       below. Review what will be copied before committing.
    4. Set the destination:
         Same-project copy  →  /YourProject/SomeFolder/
           Assets appear in your Content Browser under that folder.
         Cross-project copy  →  C:/OtherProject/Content
           Raw .uasset files are copied to disk — open the other project
           and the assets will appear on next load.
    5. Check  Dry run  first to preview exactly what would be copied.
    6. Uncheck  Dry run  and click  Export.

  PASTE EXPORT TAB — start from the viewport clipboard
    1. In the UEFN viewport, select actors and press  Ctrl+C
    2. Switch to the Paste Export tab and paste the clipboard text
    3. Click  Parse References  — asset paths are extracted from the T3D data
    4. Click  Resolve Dependencies, then  Export  as above

─────────────────────────────────────────────────────────────────────────

OPTIONS

  Include dependencies  (default ON)
      Walk the Asset Registry dep graph from each seed asset.
      Meshes pull in materials. Materials pull in textures.
      Turn OFF only to copy a single asset with no deps.

  Flatten folder structure
      Copies everything into one flat destination folder instead of
      recreating the source subfolder tree. Useful when you want a
      clean drop-in without nested paths.

  Overwrite existing
      By default, existing assets at the destination are skipped.
      Turn ON to replace them.

  Dry run
      Simulates the entire export and prints the result log without
      writing anything. Always run this first on large exports.

─────────────────────────────────────────────────────────────────────────

DESTINATION PATHS

  /YourProject/Migrated/       same-project copy — visible in Content Browser
  C:/Projects/Other/Content    cross-project disk copy — raw .uasset files

  The destination auto-fills from your project's mount point the first time
  you add an asset from the Content Browser.

  NOTE: In UEFN, /Game/ is an internal mount NOT visible in the Content
  Browser. Always use your project's named mount (e.g. /Device_API_Mapping/)
  for same-project copies. See UEFN_QUIRKS.md Quirk #23.

─────────────────────────────────────────────────────────────────────────

WHAT IT DOES NOT MIGRATE

  Verse source files (.verse) — not tracked by the Asset Registry.
    Copy them manually from your project's Verse source directory.

  Fortnite / Engine built-ins — already exist in every project.

  Level or World Partition data — export the level file itself for that.
"""

        def __init__(self) -> None:
            super().__init__(title="UEFN Toolbelt — Prefab Asset Migrator Help",
                             width=700, height=760)
            self._build_ui()

        def _build_ui(self) -> None:
            root = QWidget()
            self.setCentralWidget(root)
            vl = QVBoxLayout(root)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)
            editor = QTextEdit()
            editor.setReadOnly(True)
            editor.setPlainText(self._CONTENT)
            editor.setFont(QFont("Consolas", 9))
            editor.setLineWrapMode(QTextEdit.NoWrap)
            editor.setStyleSheet(
                f"background:{self.hex('panel')}; color:{self.hex('text')};"
                f"border:none; padding:16px;"
            )
            vl.addWidget(editor)

    # ── Main window ────────────────────────────────────────────────────────

    class _PrefabMigratorWindow(ToolbeltWindow):
        """Prefab asset migrator — Export and Paste Export tabs."""

        def __init__(self) -> None:
            super().__init__(title="UEFN Toolbelt — Prefab Asset Migrator",
                             width=820, height=700)
            self._worker = None
            self._resolved: Set[str] = set()
            self._build_ui()

        def _build_ui(self) -> None:
            root = QWidget()
            self.setCentralWidget(root)
            vl = QVBoxLayout(root)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            # Shared project paths (used by both tabs)
            proj_row = QWidget()
            pl = QVBoxLayout(proj_row)
            pl.setContentsMargins(16, 10, 16, 4)
            pl.setSpacing(6)

            # Mount point is unknown until the user adds an asset — will be
            # updated automatically by _update_mount_from_path() on first add.
            self._proj_mount = ""

            # Source path — only used for cross-project disk copy
            _project_root = unreal.Paths.convert_relative_path_to_full(
                unreal.Paths.project_dir()
            ).rstrip("/\\")
            _abs_content = _project_root + "/Content"
            self._src_lbl = _lbl("Source project Content folder  (only used for cross-project disk copy — not needed for /Game/… destinations):")
            self._src_lbl.setStyleSheet("color:#666666; font-size:8pt;")
            pl.addWidget(self._src_lbl)
            self._src_row = _PathRow("", _abs_content)
            self._src_row.edit.setText(_abs_content)
            self._src_row.setEnabled(False)  # greyed out until destination is a disk path
            pl.addWidget(self._src_row)

            pl.addWidget(_lbl("Export destination  (Content folder of another project on disk, OR a project path for same-project copy):"))
            self._dst_row = _PathRow("", "C:/Fortnite Projects/MyOtherProject/Content")
            self._dst_row.edit.setPlaceholderText("Auto-set when you add an asset")
            self._dst_row.edit.textChanged.connect(self._on_dst_changed)
            pl.addWidget(self._dst_row)

            # Options row
            opt_row = QWidget()
            ol = QHBoxLayout(opt_row)
            ol.setContentsMargins(0, 0, 0, 0)
            ol.setSpacing(16)
            self._cb_deps     = QCheckBox("Include dependencies")
            self._cb_flatten  = QCheckBox("Flatten folder structure")
            self._cb_overwrite = QCheckBox("Overwrite existing")
            self._cb_dry      = QCheckBox("Dry run (preview only)")
            self._cb_deps.setChecked(True)
            self._cb_flatten.setChecked(False)
            self._cb_dry.setChecked(False)
            for cb in (self._cb_deps, self._cb_flatten, self._cb_overwrite, self._cb_dry):
                cb.setStyleSheet("color:#CCCCCC; font-size:9pt;")
                ol.addWidget(cb)
            ol.addStretch()
            pl.addWidget(opt_row)
            pl.addWidget(_div())

            vl.addWidget(proj_row)

            # Tabs
            tabs = QTabWidget()
            tabs.setStyleSheet(
                "QTabWidget::pane{border:none; background:#161616;}"
                "QTabBar::tab{background:#1A1A1A; color:#888; padding:6px 16px;"
                "border:1px solid #2A2A2A; border-bottom:none; border-radius:3px 3px 0 0;}"
                "QTabBar::tab:selected{background:#252525; color:#E0E0E0;"
                "border-color:#3A8FC7; border-bottom:none;}"
                "QTabBar::tab:hover{color:#CCCCCC;}"
            )
            tabs.addTab(self._build_export_tab(), "Export")
            tabs.addTab(self._build_paste_tab(), "Paste Export")
            tabs.addTab(self._build_log_tab(), "Log")
            vl.addWidget(tabs, 1)

        # ── Export tab ─────────────────────────────────────────────────────

        def _build_export_tab(self) -> QWidget:
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(16, 12, 16, 12)
            vl.setSpacing(8)

            vl.addWidget(_lbl("Assets to export:"))
            vl.addWidget(_lbl(
                "Select assets in the Content Browser, then click + Add Selected."
                "  You can also type /Game/… paths directly.",
                muted=True,
            ))

            self._export_list = QListWidget()
            self._export_list.setStyleSheet(_LIST_CSS)
            self._export_list.setMinimumHeight(160)
            vl.addWidget(self._export_list)

            btn_row = QWidget()
            bl = QHBoxLayout(btn_row)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(6)
            b_add = _btn("+ Add Selected from CB")
            b_add.clicked.connect(self._add_selected_cb)
            b_add.setToolTip("Adds whatever is currently selected in the Content Browser")
            b_viewport = _btn("+ Add Selected from Viewport")
            b_viewport.clicked.connect(self._add_selected_viewport)
            b_viewport.setToolTip("Extracts asset paths from actors selected in the viewport")
            b_manual = _btn("+ Add Path Manually")
            b_manual.clicked.connect(self._add_manual)
            b_clear = _btn("Clear")
            b_clear.clicked.connect(self._export_list.clear)
            bl.addWidget(b_add)
            bl.addWidget(b_viewport)
            bl.addWidget(b_manual)
            bl.addWidget(b_clear)
            bl.addStretch()
            vl.addWidget(btn_row)

            vl.addWidget(_div())
            vl.addWidget(_lbl("Resolved dependency closure:"))

            self._export_dep_list = QListWidget()
            self._export_dep_list.setStyleSheet(_LIST_CSS)
            self._export_dep_list.setMinimumHeight(100)
            vl.addWidget(self._export_dep_list)

            action_row = QWidget()
            al = QHBoxLayout(action_row)
            al.setContentsMargins(0, 0, 0, 0)
            al.setSpacing(8)
            b_resolve = _btn("Resolve Dependencies")
            b_resolve.clicked.connect(self._resolve_export_deps)
            b_export  = _btn("Export", accent=True)
            b_export.clicked.connect(self._run_export)
            b_help = _btn("?")
            b_help.clicked.connect(self._do_help)
            b_help.setFixedWidth(28)
            b_help.setToolTip("Help & reference")
            self._export_status = _lbl("", muted=True)
            al.addWidget(b_resolve)
            al.addWidget(b_export)
            al.addStretch()
            al.addWidget(self._export_status)
            al.addWidget(b_help)
            vl.addWidget(action_row)

            return w

        # ── Paste Export tab ───────────────────────────────────────────────

        def _build_paste_tab(self) -> QWidget:
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(16, 12, 16, 12)
            vl.setSpacing(8)

            vl.addWidget(_lbl("Paste prefab clipboard data below:"))
            vl.addWidget(_lbl(
                "Select a prefab in UEFN and press Ctrl+C.  Paste the full T3D text here"
                " — all /Game/ asset references are extracted automatically.",
                muted=True,
            ))

            self._paste_area = QTextEdit()
            self._paste_area.setStyleSheet(_LOG_CSS)
            self._paste_area.setPlaceholderText(
                "Begin ElementGroup TypeComponents\n"
                "  Begin Object Class=/Script/EntityLevel… Name=\"…\"\n"
                "    ExportPath=\"/Script/…\"\n"
                "    Entity=\"/YOURPROJECT/Prefabs/PF_MyPrefab.PF_MyPrefab\"\n"
                "  End Object\n"
                "End ElementGroup\n\n"
                "(Ctrl+C a prefab in UEFN, then Ctrl+V here)"
            )
            self._paste_area.setMinimumHeight(160)
            self._paste_area.setFont(QFont("Consolas", 8))
            vl.addWidget(self._paste_area)

            btn_row = QWidget()
            bl = QHBoxLayout(btn_row)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(6)
            b_parse = _btn("Parse References")
            b_parse.clicked.connect(self._parse_paste)
            b_clear = _btn("Clear")
            b_clear.clicked.connect(self._paste_area.clear)
            b_clear.clicked.connect(lambda: (
                self._paste_list.clear(),
                self._paste_dep_list.clear(),
            ))
            bl.addWidget(b_parse)
            bl.addWidget(b_clear)
            bl.addStretch()
            vl.addWidget(btn_row)

            vl.addWidget(_lbl("Found asset references:"))
            self._paste_list = QListWidget()
            self._paste_list.setStyleSheet(_LIST_CSS)
            self._paste_list.setMinimumHeight(80)
            vl.addWidget(self._paste_list)

            vl.addWidget(_lbl("Resolved dependency closure:"))
            self._paste_dep_list = QListWidget()
            self._paste_dep_list.setStyleSheet(_LIST_CSS)
            self._paste_dep_list.setMinimumHeight(80)
            vl.addWidget(self._paste_dep_list)

            action_row = QWidget()
            al = QHBoxLayout(action_row)
            al.setContentsMargins(0, 0, 0, 0)
            al.setSpacing(8)
            b_resolve = _btn("Resolve Dependencies")
            b_resolve.clicked.connect(self._resolve_paste_deps)
            b_export  = _btn("Export", accent=True)
            b_export.clicked.connect(self._run_paste_export)
            self._paste_status = _lbl("", muted=True)
            al.addWidget(b_resolve)
            al.addWidget(b_export)
            al.addStretch()
            al.addWidget(self._paste_status)
            vl.addWidget(action_row)

            return w

        # ── Log tab ────────────────────────────────────────────────────────

        def _build_log_tab(self) -> QWidget:
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(16, 12, 16, 12)
            vl.setSpacing(8)

            hdr = QWidget()
            hl = QHBoxLayout(hdr)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(8)
            hl.addWidget(_lbl("Operation log:"))
            hl.addStretch()
            b_clear = _btn("Clear Log")
            b_clear.clicked.connect(lambda: self._log_area.clear())
            hl.addWidget(b_clear)
            vl.addWidget(hdr)

            self._log_area = QTextEdit()
            self._log_area.setReadOnly(True)
            self._log_area.setStyleSheet(_LOG_CSS)
            self._log_area.setFont(QFont("Consolas", 8))
            vl.addWidget(self._log_area, 1)
            return w

        # ── Helpers ────────────────────────────────────────────────────────

        def _log(self, msg: str) -> None:
            self._log_area.append(msg)
            self._log_area.ensureCursorVisible()

        def _get_dst(self) -> str:
            return self._dst_row.text

        def _is_cross_project(self) -> bool:
            dst = self._get_dst()
            # Same-project if destination starts with any /MountPoint/ style path (no disk separator)
            return not (dst.startswith("/") and "/" in dst[1:])

        def _do_help(self) -> None:
            self._help_dlg = _HelpDialog()
            self._help_dlg.show_in_uefn()

        def _on_dst_changed(self, text: str) -> None:
            """Grey out source path when destination is a project mount path (not needed for same-project copy)."""
            t = text.strip()
            is_project_path = t.startswith("/") and "/" in t[1:]
            self._src_row.setEnabled(not is_project_path)

        def _update_mount_from_path(self, pkg: str) -> None:
            """Extract mount point from asset path and set destination if not yet set."""
            if self._proj_mount:
                return
            parts = pkg.lstrip("/").split("/")
            if parts:
                self._proj_mount = f"/{parts[0]}"
                if not self._dst_row.text:
                    self._dst_row.edit.setText(f"{self._proj_mount}/Migrated/")

        def _add_selected_cb(self) -> None:
            try:
                assets = unreal.EditorUtilityLibrary.get_selected_asset_data()
                added = 0
                for a in assets:
                    pkg = _normalize_pkg(str(a.package_name))
                    items = self._export_list.findItems(pkg, Qt.MatchExactly)
                    if not items:
                        self._export_list.addItem(pkg)
                        self._update_mount_from_path(pkg)
                        added += 1
                self._export_status.setText(f"Added {added} assets from Content Browser.")
            except Exception as exc:
                self._export_status.setText(f"Error: {exc}")

        def _add_selected_viewport(self) -> None:
            """Extract asset paths from actors currently selected in the viewport."""
            try:
                actors = unreal.EditorLevelLibrary.get_selected_level_actors()
                added = 0
                for actor in actors:
                    # Get the Blueprint/class asset path if it's a BP actor
                    cls = actor.get_class()
                    if cls:
                        pkg = _normalize_pkg(str(cls.get_path_name()))
                        # Skip engine/built-in classes
                        if any(pkg.startswith(s) for s in ("/Engine/", "/Script/", "/FortniteGame/")):
                            continue
                        if not self._export_list.findItems(pkg, Qt.MatchExactly):
                            self._export_list.addItem(pkg)
                            self._update_mount_from_path(pkg)
                            added += 1
                    # Also grab the static mesh if it's a StaticMeshActor
                    try:
                        mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
                        if mesh_comp:
                            mesh = mesh_comp.static_mesh
                            if mesh:
                                pkg = _normalize_pkg(str(mesh.get_path_name()))
                                if not any(pkg.startswith(s) for s in ("/Engine/", "/Script/", "/FortniteGame/")):
                                    if not self._export_list.findItems(pkg, Qt.MatchExactly):
                                        self._export_list.addItem(pkg)
                                        self._update_mount_from_path(pkg)
                                        added += 1
                    except Exception:
                        pass
                actor_count = len(list(actors))
                if added:
                    self._export_status.setText(f"Added {added} assets from {actor_count} viewport actor(s).")
                elif actor_count:
                    self._export_status.setText(
                        f"Found {actor_count} actor(s) but all reference engine/Fortnite built-in assets — "
                        f"only actors using your project's custom meshes/BPs will appear here."
                    )
                else:
                    self._export_status.setText("No actors selected in viewport.")
            except Exception as exc:
                self._export_status.setText(f"Error: {exc}")

        def _add_manual(self) -> None:
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(
                self, "Add Asset Path",
                "Enter /Game/… package path:",
            )
            if ok and text.strip().startswith("/"):
                pkg = _normalize_pkg(text.strip())
                if not self._export_list.findItems(pkg, Qt.MatchExactly):
                    self._export_list.addItem(pkg)
                    self._update_mount_from_path(pkg)

        def _list_packages(self, list_widget: QListWidget) -> List[str]:
            return [list_widget.item(i).text() for i in range(list_widget.count())]

        def _categorize(self, pkg: str) -> tuple:
            """Return (label, color) for a package path based on name/path hints."""
            name = pkg.rsplit("/", 1)[-1].upper()
            low  = pkg.lower()
            if any(x in low for x in ("/verse/", "/verse_", "_verse", ".verse")):
                return "Verse",    "#C678DD"
            if any(name.startswith(p) for p in ("SM_", "SKM_", "SK_")):
                return "Mesh",     "#E5C07B"
            if any(name.startswith(p) for p in ("M_", "MI_", "MF_", "MM_")):
                return "Material", "#E06C75"
            if any(name.startswith(p) for p in ("T_", "TX_")):
                return "Texture",  "#56B6C2"
            if any(name.startswith(p) for p in ("BP_", "ABP_")):
                return "Blueprint","#61AFEF"
            if any(name.startswith(p) for p in ("A_", "S_", "SC_", "SFX_")):
                return "Audio",    "#98C379"
            if any(name.startswith(p) for p in ("P_", "NS_", "FX_", "VFX_")):
                return "FX",       "#FF9900"
            if any(name.startswith(p) for p in ("DA_", "DT_", "D_")):
                return "Data",     "#ABB2BF"
            return "Asset",        "#888888"

        def _populate_dep_list(self, dep_list: QListWidget,
                               resolved: Set[str], seeds: List[str]) -> None:
            dep_list.clear()
            seed_set = set(seeds)
            for pkg in sorted(resolved):
                cat, color = self._categorize(pkg)
                seed_marker = " ●" if pkg in seed_set else ""
                item = QListWidgetItem(f"[{cat}]{seed_marker}  {pkg}")
                item.setForeground(QColor(color))
                item.setToolTip(
                    ("Direct seed asset" if pkg in seed_set else "Pulled in as dependency")
                    + f"  ·  {cat}"
                )
                dep_list.addItem(item)

        # ── Resolve ────────────────────────────────────────────────────────

        def _resolve_export_deps(self) -> None:
            seeds = self._list_packages(self._export_list)
            if not seeds:
                self._export_status.setText("Add assets first.")
                return
            self._export_status.setText("Resolving…")
            QApplication.processEvents()
            resolved, warns = _resolve_deps(seeds, self._cb_deps.isChecked())
            self._resolved = resolved
            self._populate_dep_list(self._export_dep_list, resolved, seeds)
            for w in warns:
                self._log(f"WARN  {w}")
            self._export_status.setText(
                f"{len(resolved)} assets in closure  ({len(resolved) - len(seeds)} dependencies)"
            )
            self._log(f"Resolved {len(resolved)} assets from {len(seeds)} seeds.")

        def _resolve_paste_deps(self) -> None:
            seeds = self._list_packages(self._paste_list)
            if not seeds:
                self._paste_status.setText("Parse references first.")
                return
            self._paste_status.setText("Resolving…")
            QApplication.processEvents()
            resolved, warns = _resolve_deps(seeds, self._cb_deps.isChecked())
            self._resolved = resolved
            self._populate_dep_list(self._paste_dep_list, resolved, seeds)
            for w in warns:
                self._log(f"WARN  {w}")
            self._paste_status.setText(
                f"{len(resolved)} assets in closure  ({len(resolved) - len(seeds)} dependencies)"
            )
            self._log(f"Resolved {len(resolved)} assets from {len(seeds)} seeds.")

        # ── Parse ──────────────────────────────────────────────────────────

        def _parse_paste(self) -> None:
            text = self._paste_area.toPlainText()
            if not text.strip():
                self._paste_status.setText("Paste T3D text first.")
                return
            paths = _parse_t3d(text)
            self._paste_list.clear()
            self._paste_dep_list.clear()
            for p in paths:
                self._paste_list.addItem(p)
            self._paste_status.setText(
                f"Found {len(paths)} /Game/ references.  Click Resolve Dependencies next."
            )
            self._log(f"Parsed {len(paths)} asset refs from clipboard text.")

        # ── Export ─────────────────────────────────────────────────────────

        def _run_export_common(self, status_lbl: QLabel) -> None:
            if not self._resolved:
                status_lbl.setText("Resolve dependencies first.")
                return
            dst = self._get_dst()
            if not dst:
                status_lbl.setText("Set export destination first.")
                return

            flatten   = self._cb_flatten.isChecked()
            overwrite = self._cb_overwrite.isChecked()
            dry_run   = self._cb_dry.isChecked()
            cross     = self._is_cross_project()

            src_content = self._src_row.text
            if cross and not os.path.isdir(src_content):
                status_lbl.setText("Source Content folder not found on disk.")
                return
            if cross and not os.path.isdir(dst):
                try:
                    os.makedirs(dst, exist_ok=True)
                except Exception as exc:
                    status_lbl.setText(f"Cannot create destination: {exc}")
                    return

            prefix = "[DRY RUN] " if dry_run else ""
            self._log(f"\n{'─'*60}")
            self._log(f"{prefix}Exporting {len(self._resolved)} assets…")
            self._log(f"  flatten={flatten}  overwrite={overwrite}  cross_project={cross}")
            self._log(f"  dst → {dst}")
            status_lbl.setText(f"{prefix}Exporting…")
            QApplication.processEvents()

            if cross:
                results = _export_to_disk(
                    self._resolved, src_content, dst,
                    flatten, overwrite, dry_run,
                )
            else:
                results = _export_within_project(
                    self._resolved, dst, flatten, overwrite, dry_run,
                )

            ok      = len(results["ok"])
            skipped = len(results["skip"])
            missing = len(results["missing"])
            errors  = len(results["error"])

            for line in results["ok"]:
                self._log(f"  OK      {line}")
            for line in results["skip"]:
                self._log(f"  SKIP    {line}  (already exists)")
            for line in results["missing"]:
                self._log(f"  MISSING {line}  (not found in source)")
            for line in results["error"]:
                self._log(f"  ERROR   {line}")

            summary = (
                f"{prefix}Done — {ok} exported · {skipped} skipped · "
                f"{missing} missing · {errors} errors"
            )
            self._log(summary)
            status_lbl.setText(summary)

        def _run_export(self) -> None:
            if not self._resolved:
                self._resolve_export_deps()
            self._run_export_common(self._export_status)

        def _run_paste_export(self) -> None:
            if not self._resolved:
                self._resolve_paste_deps()
            self._run_export_common(self._paste_status)


# ── Registered tools ──────────────────────────────────────────────────────────

@register_tool(
    name="prefab_migrate_open",
    category="Asset Management",
    description=(
        "Open the Prefab Asset Migrator — paste Ctrl+C prefab T3D text to "
        "auto-extract all asset references, resolve the full dependency closure "
        "(meshes, materials, textures, Verse components), and export cleanly to "
        "another project with optional folder flattening."
    ),
    tags=["prefab", "migrate", "export", "dependency", "asset", "copy"],
)
def prefab_migrate_open(**kwargs) -> dict:
    if not _PYSIDE6:
        return {"status": "error", "message": "PySide6 not installed."}
    try:
        win = _PrefabMigratorWindow()
        win.show_in_uefn()
        return {"status": "ok", "message": "Prefab Asset Migrator opened."}
    except Exception as exc:
        log_error(f"prefab_migrate_open: {exc}")
        return {"status": "error", "message": str(exc)}


@register_tool(
    name="prefab_parse_refs",
    category="Asset Management",
    description=(
        "Headless: parse a T3D prefab text string and return all /Game/ asset "
        "package paths found. No UI — MCP/script friendly."
    ),
    tags=["prefab", "parse", "references", "headless"],
)
def prefab_parse_refs(t3d_text: str = "", **kwargs) -> dict:
    if not t3d_text:
        return {"status": "error", "message": "Provide t3d_text parameter."}
    paths = _parse_t3d(t3d_text)
    return {"status": "ok", "paths": paths, "count": len(paths)}


@register_tool(
    name="prefab_resolve_deps",
    category="Asset Management",
    description=(
        "Headless: given a list of /Game/ package paths, walk the AssetRegistry "
        "dependency graph and return the full closure of all required assets. "
        "MCP/script friendly."
    ),
    tags=["prefab", "dependency", "resolve", "headless"],
)
def prefab_resolve_deps(packages: list = None, include_deps: bool = True, **kwargs) -> dict:
    if not packages:
        return {"status": "error", "message": "Provide packages list."}
    resolved, warnings = _resolve_deps(packages, include_deps)
    return {
        "status": "ok",
        "resolved": sorted(resolved),
        "count": len(resolved),
        "warnings": warnings,
    }


@register_tool(
    name="prefab_export_to_disk",
    category="Asset Management",
    description=(
        "Headless: copy resolved .uasset files from this project's Content folder "
        "to a destination disk directory. Set dry_run=True to preview without "
        "copying. MCP/script friendly."
    ),
    tags=["prefab", "export", "disk", "headless"],
)
def prefab_export_to_disk(
    packages: list = None,
    dst_content: str = "",
    flatten: bool = False,
    overwrite: bool = False,
    dry_run: bool = True,
    **kwargs,
) -> dict:
    if not packages:
        return {"status": "error", "message": "Provide packages list."}
    if not dst_content:
        return {"status": "error", "message": "Provide dst_content path."}
    src_content = unreal.Paths.project_content_dir().rstrip("/\\")
    results = _export_to_disk(
        set(packages), src_content, dst_content,
        flatten, overwrite, dry_run,
    )
    return {
        "status": "ok",
        "exported":  len(results["ok"]),
        "skipped":   len(results["skip"]),
        "missing":   len(results["missing"]),
        "errors":    results["error"],
        "dry_run":   dry_run,
    }
