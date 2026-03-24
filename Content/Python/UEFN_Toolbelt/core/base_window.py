"""
UEFN Toolbelt — ToolbeltWindow
================================
Base class for every PySide6 window opened by a Toolbelt tool or plugin.
Subclass this instead of QMainWindow — you get the full dashboard theme,
the required Slate tick driver, and factory helpers for every standard widget
type, all for free.

Usage:
    from ..core.base_window import ToolbeltWindow

    class MyToolWindow(ToolbeltWindow):
        def __init__(self):
            super().__init__(title="UEFN Toolbelt — My Tool", width=1100, height=700)
            self._build_ui()

        def _build_ui(self):
            # Only add make_topbar() when it carries actual toolbar buttons.
            # The OS title bar already shows the tool name — don't repeat it
            # with a stretch-only bar.
            bar, bl = self.make_topbar("MY TOOL")
            bl.addWidget(self.make_btn("Run", accent=True, cb=self._run))
            bl.addWidget(self.make_btn("Clear", cb=self._clear))
            bl.addStretch()
            ...

    # In your tool function:
    win = MyToolWindow()
    win.show_in_uefn()          # ← handles Slate tick automatically

See docs/ui_style_guide.md for the full color palette and widget reference.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from .theme import PALETTE, QSS, subscribe, unsubscribe

# ── PySide6 availability guard ────────────────────────────────────────────────

_PYSIDE6 = False
try:
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
        QPushButton, QLabel, QFrame, QTextEdit, QScrollArea,
    )
    from PySide6.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QBrush, QPolygonF
    from PySide6.QtCore import Qt, QPointF
    _PYSIDE6 = True
except ImportError:
    QMainWindow = object  # type: ignore[misc,assignment]


def make_toolbelt_icon() -> "QIcon":
    """
    Create the canonical UEFN Toolbelt window icon — blue hexagon with 'TB' text.
    Used by ToolbeltWindow (auto-applied) and ToolbeltDashboard.
    Import this wherever you need the icon; never recreate it inline.
    """
    if not _PYSIDE6:
        return None  # type: ignore[return-value]
    import math
    size = 64
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
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
    p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
    p.drawText(pm.rect(), Qt.AlignCenter, "TB")
    p.end()
    return QIcon(pm)


# ── ToolbeltWindow ─────────────────────────────────────────────────────────────

if _PYSIDE6:

    class ToolbeltWindow(QMainWindow):
        """
        Base class for all Toolbelt PySide6 windows.

        Provides:
          - Dashboard QSS applied automatically (from core/theme.py)
          - Slate tick driver via show_in_uefn() — required in UEFN or the
            window will be invisible
          - self.P  — dict[str, QColor] keyed by palette token
          - self.hex(token) → str — hex color for a token
          - Widget factory helpers: make_topbar, make_btn, make_label,
            make_divider, make_text_area, make_hbar, set_hbar_value,
            make_scroll_panel
        """

        def __init__(
            self,
            title: str = "TOOLBELT",
            width: int = 900,
            height: int = 600,
            parent: Optional[QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setWindowIcon(make_toolbelt_icon())
            self.resize(width, height)
            self.setStyleSheet(QSS)

            # Palette: token -> QColor (same values as core/theme.PALETTE)
            self.P: dict[str, QColor] = {k: QColor(v) for k, v in PALETTE.items()}

            # Slate tick handle — populated by show_in_uefn()
            self._slate_tick_handle: list = [None]

            # Subscribe to live theme changes
            subscribe(self._apply_theme)

        # ── Palette helpers ───────────────────────────────────────────────────

        def hex(self, token: str) -> str:
            """Return the hex string for a palette token."""
            return PALETTE.get(token, token)

        def _apply_theme(self, qss: str) -> None:
            """Called by the theme system when the active theme changes."""
            self.setStyleSheet(qss)
            self.P = {k: QColor(v) for k, v in PALETTE.items()}

        def closeEvent(self, event) -> None:
            unsubscribe(self._apply_theme)
            super().closeEvent(event)

        # ── Slate integration ─────────────────────────────────────────────────

        def show_in_uefn(self) -> None:
            """
            Show the window and start the Unreal Slate tick driver.

            REQUIRED in UEFN — without this PySide6 windows are invisible
            because Qt's event loop is never pumped (Unreal owns the thread).
            Call this instead of show().
            """
            import unreal  # type: ignore[import]
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance() or QApplication([])
            self.show()
            self.raise_()
            self.activateWindow()

            handle = self._slate_tick_handle
            win    = self

            def _tick(dt: float) -> None:
                try:
                    if not win.isVisible():
                        unreal.unregister_slate_post_tick_callback(handle[0])
                        return
                    app.processEvents()
                except Exception:
                    try:
                        unreal.unregister_slate_post_tick_callback(handle[0])
                    except Exception:
                        pass

            handle[0] = unreal.register_slate_post_tick_callback(_tick)

        def close_clean(self) -> None:
            """Close the window and unregister the Slate tick cleanly."""
            self.close()
            try:
                import unreal  # type: ignore[import]
                if self._slate_tick_handle[0] is not None:
                    unreal.unregister_slate_post_tick_callback(
                        self._slate_tick_handle[0]
                    )
            except Exception:
                pass

        # ── Widget factory helpers ────────────────────────────────────────────

        def make_topbar(self, title: str) -> Tuple[QWidget, QHBoxLayout]:
            """
            Standard 46px Toolbelt top bar with brand-red title.
            Returns (bar_widget, bar_layout).
            Add buttons / inputs / spacers to bar_layout after the call.

            Example:
                bar, bl = self.make_topbar("MY TOOL")
                bl.addWidget(self.make_btn("Run", accent=True, cb=self._run))
                bl.addStretch()
                vl.addWidget(bar)
            """
            bar = QWidget()
            bar.setFixedHeight(46)
            bar.setStyleSheet(
                f"background:{self.hex('topbar')}; "
                f"border-bottom:1px solid {self.hex('border')};"
            )
            bl = QHBoxLayout(bar)
            bl.setContentsMargins(12, 0, 12, 0)
            bl.setSpacing(6)

            lbl = QLabel(title)
            lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
            lbl.setStyleSheet(f"color:{self.hex('brand')};")
            bl.addWidget(lbl)
            bl.addSpacing(8)

            return bar, bl

        def make_btn(
            self,
            text: str,
            accent: bool = False,
            cb: Optional[Callable] = None,
            height: int = 28,
            width: int = 0,
        ) -> QPushButton:
            """
            Standard Toolbelt button.
            accent=True → primary action (blue tint).
            """
            b = QPushButton(text)
            b.setFixedHeight(height)
            if width:
                b.setFixedWidth(width)
            if accent:
                b.setProperty("accent", "true")
            b.setCursor(Qt.PointingHandCursor)
            if cb:
                b.clicked.connect(cb)
            return b

        def make_label(
            self,
            text: str = "",
            role: str = "body",
            color: str = "",
            size: int = 0,
            bold: bool = False,
        ) -> QLabel:
            """
            Styled label.
            role: 'body' | 'header' | 'section' | 'muted' | 'brand'
            color / size / bold override the role defaults when provided.
            """
            _roles = {
                "header":  (self.hex("text"),   12, True),
                "section": (self.hex("muted"),   9, True),
                "muted":   (self.hex("muted"),   9, False),
                "brand":   (self.hex("brand"),  12, True),
                "body":    (self.hex("text"),    9, False),
            }
            dc, ds, db = _roles.get(role, _roles["body"])
            w = QLabel(text)
            w.setFont(QFont("Segoe UI", size or ds, QFont.Bold if (bold or db) else QFont.Normal))
            w.setStyleSheet(f"color:{color or dc}; background:transparent;")
            w.setWordWrap(True)
            return w

        def make_divider(self) -> QFrame:
            """Horizontal separator line."""
            f = QFrame()
            f.setFrameShape(QFrame.HLine)
            f.setStyleSheet(f"color:{self.hex('border2')};")
            return f

        def make_text_area(
            self,
            height: int = 52,
            text_color: str = "",
            mono: bool = True,
            read_only: bool = True,
        ) -> QTextEdit:
            """
            Panel text area.
            mono=True  → Consolas 8pt (for tool output / code)
            mono=False → Segoe UI 9pt (for notes / prose)
            """
            t = QTextEdit()
            t.setReadOnly(read_only)
            t.setFixedHeight(height)
            fg   = text_color or self.hex("text")
            font = "Consolas" if mono else "'Segoe UI'"
            size = "8pt" if mono else "9pt"
            t.setStyleSheet(
                f"background:{self.hex('panel')}; color:{fg}; "
                f"border:1px solid {self.hex('border')}; "
                f"font-family:{font}; font-size:{size}; padding:4px;"
            )
            return t

        def make_hbar(self, height: int = 4) -> QLabel:
            """
            Thin progress / health bar widget.
            Call set_hbar_value() to update fill and color.
            """
            b = QLabel()
            b.setFixedHeight(height)
            b.setStyleSheet(
                f"background:{self.hex('border')}; border-radius:{height // 2}px;"
            )
            return b

        def set_hbar_value(
            self,
            bar: QLabel,
            value: float,
            max_value: float = 100.0,
            ok_threshold: float = 70.0,
            warn_threshold: float = 40.0,
        ) -> None:
            """
            Fill a bar created by make_hbar().
            Color: ok (green) → warn (yellow) → error (red) based on thresholds.
            """
            pct = max(0.0, min(1.0, value / max_value)) if max_value else 0.0
            col = (
                self.hex("ok")    if value >= ok_threshold  else
                self.hex("warn")  if value >= warn_threshold else
                self.hex("error")
            )
            h = bar.height() or height
            bar.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {col},stop:{pct:.3f} {col},"
                f"stop:{min(pct + 0.001, 1):.3f} {self.hex('border')},"
                f"stop:1 {self.hex('border')});"
                f"border-radius:{h // 2}px;"
            )

        def make_scroll_panel(
            self,
            width: int = 314,
            border_left: bool = True,
        ) -> Tuple[QScrollArea, QWidget]:
            """
            Standard side panel scroll area.
            Returns (scroll_area, inner_widget).
            Add your content widgets to inner_widget.
            """
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            if width:
                scroll.setFixedWidth(width)
            border = f"border-left:1px solid {self.hex('border')};" if border_left else ""
            scroll.setStyleSheet(
                f"background:{self.hex('bg')}; border:none; {border}"
            )
            inner = QWidget()
            inner.setStyleSheet(f"background:{self.hex('bg')};")
            scroll.setWidget(inner)
            return scroll, inner

else:
    # Stub — module loads cleanly when PySide6 is absent
    class ToolbeltWindow:  # type: ignore[no-redef]
        """No-op stub when PySide6 is not installed."""
        def __init__(self, *a, **kw) -> None: ...
        def show_in_uefn(self) -> None: ...
        def close_clean(self) -> None: ...
        def hex(self, token: str) -> str: return PALETTE.get(token, token)
