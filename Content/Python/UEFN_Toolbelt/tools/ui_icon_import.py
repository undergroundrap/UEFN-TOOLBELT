"""
UEFN TOOLBELT — UI Icon Importer
========================================
Clipboard-first image importer for UEFN UI/icon textures.

Copy any image (from a browser, Figma, Photoshop, Paint) and paste it
directly into the window — it imports with the correct Mip/compression
settings for UI work in one click. No Photoshop export step, no manual
texture settings panel.

Three ways to feed an image:
  1. Ctrl+V  — paste from clipboard
  2. Click   — open file browser
  3. Drag    — drop an image file onto the zone

Presets cover the most common UEFN UI needs:
  • UI Icon (default)  — TC_UserInterface2D · NoMipmaps · sRGB · TextureGroup_UI
  • Sprite / 2D        — TC_BC7 · NoMipmaps · sRGB · TextureGroup_UI
  • Thumbnail          — TC_BC7 · NoMipmaps · sRGB · TextureGroup_UI
  • Normal Map         — TC_Normalmap · NoMipmaps · no sRGB · TextureGroup_World
  • Default / Mipmapped — TC_BC7 · standard mip chain · TextureGroup_World

Registered tools:
  ui_icon_import_open   Open the import window
"""

from __future__ import annotations

import os
import tempfile

import unreal

from ..core import log_info, log_warning, log_error, detect_project_mount
from ..core.base_window import ToolbeltWindow
from ..registry import register_tool

# ── PySide6 guard ─────────────────────────────────────────────────────────────
_PYSIDE6 = False
try:
    from PySide6.QtWidgets import (
        QApplication, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QComboBox, QFrame,
        QFileDialog, QSizePolicy, QTextEdit,
    )
    from PySide6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent
    from PySide6.QtCore import Qt
    _PYSIDE6 = True
except ImportError:
    pass


# ── Texture presets ───────────────────────────────────────────────────────────
_PRESETS: dict[str, dict] = {
    "UI Icon  (TC_UserInterface2D · no mips · sRGB)": {
        "compression": "TC_USER_INTERFACE2D",
        "mip_gen":     "TMGS_NO_MIPMAPS",
        "srgb":        True,
        "lod_group":   "TEXTUREGROUP_UI",
    },
    "Sprite / 2D  (TC_BC7 · no mips · sRGB)": {
        "compression": "TC_BC7",
        "mip_gen":     "TMGS_NO_MIPMAPS",
        "srgb":        True,
        "lod_group":   "TEXTUREGROUP_UI",
    },
    "Thumbnail  (TC_BC7 · no mips · sRGB)": {
        "compression": "TC_BC7",
        "mip_gen":     "TMGS_NO_MIPMAPS",
        "srgb":        True,
        "lod_group":   "TEXTUREGROUP_UI",
    },
    "Normal Map  (TC_Normalmap · no mips · linear)": {
        "compression": "TC_NORMALMAP",
        "mip_gen":     "TMGS_NO_MIPMAPS",
        "srgb":        False,
        "lod_group":   "TEXTUREGROUP_WORLD",
    },
    "Default / Mipmapped  (TC_BC7 · standard mips)": {
        "compression": "TC_BC7",
        "mip_gen":     "TMGS_FROM_TEXTURE_GROUP",
        "srgb":        True,
        "lod_group":   "TEXTUREGROUP_WORLD",
    },
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _apply_texture_settings(pkg_path: str, preset: dict) -> None:
    """Apply Mip/compression/LOD settings to an already-imported texture."""
    try:
        tex = unreal.EditorAssetLibrary.load_asset(pkg_path)
        if not tex:
            return

        comp = getattr(
            unreal.TextureCompressionSettings,
            preset["compression"],
            unreal.TextureCompressionSettings.TC_DEFAULT,
        )
        tex.set_editor_property("compression_settings", comp)

        mip = getattr(
            unreal.TextureMipGenSettings,
            preset["mip_gen"],
            unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP,
        )
        tex.set_editor_property("mip_gen_settings", mip)

        tex.set_editor_property("srgb", preset["srgb"])

        lod = getattr(
            unreal.TextureGroup,
            preset["lod_group"],
            unreal.TextureGroup.TEXTUREGROUP_UI,
        )
        tex.set_editor_property("lod_group", lod)

        tex.post_edit_change()
        unreal.EditorAssetLibrary.save_asset(pkg_path)
    except Exception as e:
        log_warning(f"[UI ICON] Could not apply texture settings to {pkg_path}: {e}")


# ── PySide6 classes ───────────────────────────────────────────────────────────

if _PYSIDE6:

    # ── Help dialog ───────────────────────────────────────────────────────────

    class _HelpDialog(ToolbeltWindow):
        _HELP = """\
UI ICON IMPORTER — Quick Reference
══════════════════════════════════════════════════════════════════════

WHAT IT DOES
  Imports any image into your UEFN project with the correct Mip and
  compression settings for UI textures — in one step.
  No Photoshop export. No texture settings panel. Just paste and import.

THREE WAYS TO LOAD AN IMAGE
  1. Ctrl+V  — copy an image in your browser, Figma, Photoshop, or
               Paint, then press Ctrl+V inside this window.
  2. Click   — click the drop zone to open a file browser (.png, .jpg,
               .tga, .bmp).
  3. Drag    — drag any image file directly onto the drop zone.

PRESETS
  UI Icon (default)
    → TC_UserInterface2D · NoMipmaps · sRGB · TextureGroup UI
    → Best for HUD icons, button art, inventory images, crosshairs.

  Sprite / 2D
    → TC_BC7 · NoMipmaps · sRGB · TextureGroup UI
    → Best for 2D game sprites or flat cutout textures.

  Thumbnail
    → TC_BC7 · NoMipmaps · sRGB · TextureGroup UI
    → Best for preview images, map art, loading screens.

  Normal Map
    → TC_Normalmap · NoMipmaps · linear (no sRGB) · TextureGroup World
    → Best for tangent-space normal maps.

  Default / Mipmapped
    → TC_BC7 · standard mip chain · TextureGroup World
    → Best for in-world textures that need LOD mipmapping.

DESTINATION
  Defaults to /[ProjectMount]/UI/Icons/ where [ProjectMount] is
  auto-detected from your Content Browser on open.
  You can type any valid Content Browser path.
  The folder is created automatically if it does not exist.

FILENAME
  Auto-filled from the source file name, or T_Paste_001 for clipboard
  pastes. The T_ prefix follows Epic naming conventions.
  Edit this field before importing to rename the asset.

WHY NO MIPMAPS FOR UI?
  UI textures are always displayed at a fixed pixel size — mipmaps waste
  memory and can cause blurry renders at certain resolutions.
  TC_UserInterface2D also preserves the full alpha channel correctly,
  which BC7/DXT5 may not in all cases.

TIPS
  • Transparent PNGs keep their alpha — use UI Icon preset.
  • For web images: right-click → Copy Image → Ctrl+V in this window.
  • The imported asset is auto-selected in the Content Browser so you
    can drag it onto a Widget Blueprint immediately.
  • Supports PNG, JPG, TGA, BMP.
"""

        def __init__(self, parent=None):
            super().__init__(title="UEFN Toolbelt — UI Icon Importer Help", width=580, height=580, parent=parent)
            self._build_ui()

        def _build_ui(self):
            central = QFrame()
            self.setCentralWidget(central)
            vl = QVBoxLayout(central)
            vl.setContentsMargins(14, 14, 14, 14)
            vl.setSpacing(8)

            editor = QTextEdit()
            editor.setReadOnly(True)
            editor.setLineWrapMode(QTextEdit.NoWrap)
            editor.setPlainText(self._HELP)
            editor.setStyleSheet(
                f"background:{self.hex('panel')}; color:{self.hex('text')}; "
                f"font-family:Consolas; font-size:9pt; "
                f"border:1px solid {self.hex('border')}; padding:8px;"
            )
            vl.addWidget(editor)

            close_row = QHBoxLayout()
            close_row.addStretch()
            close_row.addWidget(self.make_btn("Close", cb=self.close))
            vl.addLayout(close_row)

    # ── Drop Zone ─────────────────────────────────────────────────────────────

    class _DropZone(QLabel):
        """Paste / drag-and-drop target that accepts images and image files."""

        def __init__(self, palette: dict, parent=None):
            super().__init__(parent)
            self._P = palette
            self._has_image = False
            self.setAcceptDrops(True)
            self.setAlignment(Qt.AlignCenter)
            self.setMinimumHeight(180)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setScaledContents(False)
            self._show_empty()

        def _show_empty(self):
            self._has_image = False
            self.clear()
            self.setText("Click to browse  ·  Ctrl+V to paste  ·  or drop an image here")
            self.setStyleSheet(
                f"background:{self._P['panel']}; color:{self._P['muted']}; "
                f"border:2px dashed {self._P['border2']}; border-radius:6px; "
                f"font-size:11pt; padding:24px;"
            )

        def _show_image(self, img: QImage):
            self._has_image = True
            pm = QPixmap.fromImage(img)
            # Scale to fit, leaving a margin
            maxw = max(self.width() - 32, 200)
            maxh = max(self.height() - 32, 160)
            pm = pm.scaled(maxw, maxh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setPixmap(pm)
            self.setStyleSheet(
                f"background:{self._P['bg']}; "
                f"border:2px solid {self._P['accent']}; "
                f"border-radius:6px; padding:8px;"
            )

        def load_image(self, img: QImage):
            if not img.isNull():
                self._show_image(img)

        def clear_zone(self):
            self._show_empty()

        # Drag-and-drop
        def dragEnterEvent(self, event: QDragEnterEvent):
            md = event.mimeData()
            if md.hasUrls() or md.hasImage():
                event.acceptProposedAction()
                self.setStyleSheet(
                    f"background:{self._P['panel']}; color:{self._P['text']}; "
                    f"border:2px dashed {self._P['accent']}; border-radius:6px; "
                    f"font-size:11pt; padding:24px;"
                )
            else:
                event.ignore()

        def dragLeaveEvent(self, event):
            if not self._has_image:
                self._show_empty()

        def dropEvent(self, event: QDropEvent) -> tuple[QImage | None, str]:
            """Emits via _on_drop callback set by parent."""
            md = event.mimeData()
            if md.hasUrls():
                for url in md.urls():
                    local = url.toLocalFile()
                    if local and os.path.isfile(local):
                        img = QImage(local)
                        if not img.isNull():
                            self._on_drop(img, local)
                            return
            if md.hasImage():
                img = QImage(md.imageData())
                if not img.isNull():
                    self._on_drop(img, "")

        def set_drop_handler(self, fn):
            self._on_drop = fn

    # ── Main window ───────────────────────────────────────────────────────────

    class _UIIconImportWindow(ToolbeltWindow):

        def __init__(self):
            super().__init__(title="UEFN Toolbelt — UI Icon Importer", width=560, height=540)
            self._image: QImage | None = None
            self._paste_counter = 1
            self._mount = detect_project_mount()
            self._build_ui()
            # Accept key events on the window itself
            self.setFocusPolicy(Qt.StrongFocus)

        def _build_ui(self):
            central = QFrame()
            self.setCentralWidget(central)
            vl = QVBoxLayout(central)
            vl.setContentsMargins(14, 14, 14, 14)
            vl.setSpacing(10)

            # ── Drop zone ─────────────────────────────────────────────────────
            self._zone = _DropZone({k: self.hex(k) for k in (
                "panel", "muted", "border2", "accent", "bg", "text"
            )})
            self._zone.set_drop_handler(self._on_drop)
            self._zone.mousePressEvent = self._browse
            vl.addWidget(self._zone, stretch=1)

            # ── Options panel ─────────────────────────────────────────────────
            opts = QFrame()
            opts.setStyleSheet(
                f"background:{self.hex('panel')}; "
                f"border:1px solid {self.hex('border')}; border-radius:4px;"
            )
            ol = QVBoxLayout(opts)
            ol.setContentsMargins(10, 8, 10, 8)
            ol.setSpacing(6)

            def _field_style():
                return (
                    f"background:{self.hex('bg')}; color:{self.hex('text')}; "
                    f"border:1px solid {self.hex('border2')}; border-radius:3px; "
                    f"padding:3px 7px; min-height:24px;"
                )

            def _row(label_text, widget):
                r = QHBoxLayout()
                lbl = QLabel(label_text)
                lbl.setFixedWidth(90)
                lbl.setStyleSheet(
                    f"color:{self.hex('muted')}; font-size:9pt; "
                    f"background:transparent; border:none;"
                )
                r.addWidget(lbl)
                r.addWidget(widget)
                ol.addLayout(r)

            self._fname = QLineEdit("T_Paste_001")
            self._fname.setPlaceholderText("Asset name  (T_ prefix follows Epic convention)")
            self._fname.setStyleSheet(_field_style())
            _row("Filename:", self._fname)

            self._dest = QLineEdit(f"/{self._mount}/UI/Icons/")
            self._dest.setPlaceholderText("/ProjectMount/UI/Icons/")
            self._dest.setStyleSheet(_field_style())
            _row("Destination:", self._dest)

            self._preset = QComboBox()
            for p in _PRESETS:
                self._preset.addItem(p)
            self._preset.setStyleSheet(
                f"background:{self.hex('bg')}; color:{self.hex('text')}; "
                f"border:1px solid {self.hex('border2')}; border-radius:3px; min-height:24px;"
            )
            _row("Preset:", self._preset)

            vl.addWidget(opts)

            # ── Status log ────────────────────────────────────────────────────
            self._log = self.make_text_area(height=52, mono=True)
            self._log.setPlaceholderText("Import status will appear here…")
            vl.addWidget(self._log)

            # ── Action row ────────────────────────────────────────────────────
            actions = QHBoxLayout()
            actions.addWidget(self.make_btn("Clear", cb=self._clear))
            actions.addStretch()
            actions.addWidget(self.make_btn("?", cb=self._do_help, width=28))
            actions.addWidget(self.make_btn("Import", accent=True, cb=self._do_import))
            vl.addLayout(actions)

        # ── Image loading ──────────────────────────────────────────────────────

        def _set_image(self, img: QImage, suggested_name: str = ""):
            """Accept a loaded QImage and update UI."""
            if img.isNull():
                return
            self._image = img
            self._zone.load_image(img)
            if suggested_name:
                # Enforce T_ prefix (Epic naming convention)
                if not suggested_name.upper().startswith("T_"):
                    suggested_name = "T_" + suggested_name
                self._fname.setText(suggested_name)
            w, h = img.width(), img.height()
            self._set_status(f"Loaded  {w} × {h} px  — ready to import")

        def _on_drop(self, img: QImage, filepath: str):
            name = ""
            if filepath:
                name = os.path.splitext(os.path.basename(filepath))[0]
            self._set_image(img, name)

        def _browse(self, _event=None):
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Image",
                filter="Images (*.png *.jpg *.jpeg *.tga *.bmp *.gif)"
            )
            if path:
                img = QImage(path)
                name = os.path.splitext(os.path.basename(path))[0]
                self._set_image(img, name)

        # Ctrl+V paste
        def keyPressEvent(self, event):
            if event.key() == Qt.Key_V and (event.modifiers() & Qt.ControlModifier):
                clipboard = QApplication.clipboard()
                img = clipboard.image()
                if not img.isNull():
                    name = f"Paste_{self._paste_counter:03d}"
                    self._paste_counter += 1
                    self._set_image(img, name)
                else:
                    # Clipboard may hold a file URL
                    md = clipboard.mimeData()
                    if md and md.hasUrls():
                        for url in md.urls():
                            local = url.toLocalFile()
                            if local and os.path.isfile(local):
                                img2 = QImage(local)
                                name2 = os.path.splitext(os.path.basename(local))[0]
                                self._set_image(img2, name2)
                                return
                    self._set_status("Nothing on clipboard — copy an image first.", error=True)
            else:
                super().keyPressEvent(event)

        # ── Actions ────────────────────────────────────────────────────────────

        def _clear(self):
            self._image = None
            self._zone.clear_zone()
            self._log.clear()

        def _do_help(self):
            dlg = _HelpDialog(parent=self)
            dlg.show_in_uefn()

        def _set_status(self, msg: str, error: bool = False):
            color = self.hex("error") if error else self.hex("ok")
            self._log.setStyleSheet(
                f"background:{self.hex('panel')}; color:{color}; "
                f"border:1px solid {self.hex('border')}; "
                f"font-family:Consolas; font-size:8pt; padding:4px;"
            )
            self._log.setPlainText(msg)

        def _do_import(self):
            if self._image is None or self._image.isNull():
                self._set_status("No image loaded — paste, drag, or click to browse.", error=True)
                return

            fname = self._fname.text().strip()
            if not fname:
                self._set_status("Filename is empty.", error=True)
                return

            dest = self._dest.text().strip()
            if not dest.endswith("/"):
                dest += "/"

            preset_key = self._preset.currentText()
            preset = _PRESETS[preset_key]

            # Write QImage to a temp PNG for the Unreal importer
            tmp_path = os.path.join(tempfile.gettempdir(), fname + ".png")
            try:
                ok = self._image.save(tmp_path, "PNG")
                if not ok:
                    self._set_status(f"Could not write temp file: {tmp_path}", error=True)
                    return
            except Exception as e:
                self._set_status(f"Temp write error: {e}", error=True)
                return

            # AutomatedAssetImportData → import into Content Browser
            try:
                import_data = unreal.AutomatedAssetImportData()
                import_data.destination_path = dest
                import_data.filenames = [tmp_path]
                import_data.replace_existing = True

                asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
                imported = asset_tools.import_assets_automated(import_data)

                if not imported:
                    self._set_status(
                        "Import returned no assets.\n"
                        "Check the destination path — it must start with a valid Content Browser mount.",
                        error=True,
                    )
                    return

                # Normalise package path (strip :Object suffix if present)
                pkg = imported[0].get_path_name()
                if "." in pkg:
                    pkg = pkg.rsplit(".", 1)[0]

                # Apply texture settings
                _apply_texture_settings(pkg, preset)

                # Refresh Content Browser and sync selection
                unreal.AssetRegistryHelpers.get_asset_registry().search_all_assets(True)
                unreal.EditorAssetLibrary.sync_browser_to_objects([pkg])

                w, h = self._image.width(), self._image.height()
                self._set_status(
                    f"✓ Imported  {fname}  ({w}×{h})\n"
                    f"  Preset: {preset_key.split('(')[0].strip()}\n"
                    f"  Path:   {pkg}"
                )
                log_info(f"[UI ICON] ✓ {pkg} ({w}×{h}) — {preset_key.split('(')[0].strip()}")

            except Exception as e:
                self._set_status(f"Import error: {e}", error=True)
                log_error(f"[UI ICON] Import failed: {e}")
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


# ── Registered tool ───────────────────────────────────────────────────────────

@register_tool(
    name="ui_icon_import_open",
    category="Asset Management",
    description=(
        "Open the UI Icon Importer — paste any image from the clipboard "
        "(browser, Figma, Photoshop) and import it as a UEFN texture with "
        "correct Mip/compression settings. Supports file browse and drag-drop. "
        "No Photoshop export step required."
    ),
    tags=["ui", "icon", "texture", "import", "clipboard", "paste", "image", "mip", "sprite"],
)
def ui_icon_import_open(**kwargs) -> dict:
    """
    Open the clipboard-first UI icon importer.
    Paste from browser, Figma, or Photoshop → imports with correct UEFN UI texture settings.
    """
    if not _PYSIDE6:
        return {"status": "error", "message": "PySide6 is not installed."}
    win = _UIIconImportWindow()
    win.show_in_uefn()
    return {"status": "ok", "message": "UI Icon Importer opened."}
