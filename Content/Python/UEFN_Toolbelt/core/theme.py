"""
UEFN Toolbelt — Theme
======================
Single source of truth for all UI colors and QSS styling.

To change the entire platform's look: edit PALETTE below.
Everything — the dashboard, every tool window, every plugin — pulls from
here at runtime. No other file should hard-code hex color values.

Usage:
    from ..core.theme import PALETTE, QSS, color

    hex_str = color("accent")          # "#3A3AFF"
    qss     = QSS                      # full stylesheet string

For QColor usage (after PySide6 is confirmed available):
    from ..core.theme import qcolors
    P = qcolors()                      # dict[str, QColor]
"""

from __future__ import annotations

from typing import Dict

# ── Color Palette ──────────────────────────────────────────────────────────────
# THIS is the single place to change colors for the entire platform.
# Tokens map to semantic roles — use the token name, never raw hex, in tool code.

PALETTE: Dict[str, str] = {
    "bg":      "#181818",   # window / root background
    "panel":   "#212121",   # input fields, text areas, secondary panels
    "card":    "#1E1E1E",   # elevated surfaces, node bodies
    "border":  "#2A2A2A",   # subtle borders, dividers, splitters
    "border2": "#363636",   # heavier borders, node outlines, button borders
    "text":    "#CCCCCC",   # primary text
    "muted":   "#555555",   # secondary / hint / disabled text
    "accent":  "#3A3AFF",   # primary action, focus rings, pressed states
    "brand":   "#e94560",   # toolbelt brand red — window titles only
    "warn":    "#f1c40f",   # warnings
    "error":   "#FF4444",   # errors
    "ok":      "#44FF88",   # success / healthy
    "grid":    "#1A1A1A",   # canvas grid lines, scrollbar track
    "topbar":  "#111111",   # top bar / status bar background
}


def color(token: str) -> str:
    """Return hex string for a palette token. Returns the token itself if not found."""
    return PALETTE.get(token, token)


def qcolors() -> Dict[str, object]:
    """
    Return a dict of token -> QColor.
    Only call after PySide6 is confirmed available.
    """
    try:
        from PySide6.QtGui import QColor  # type: ignore[import]
        return {k: QColor(v) for k, v in PALETTE.items()}
    except ImportError:
        return {}


# ── QSS ────────────────────────────────────────────────────────────────────────
# Built dynamically from PALETTE — changing a color above updates the stylesheet
# automatically on next import / reload.

def _build_qss() -> str:
    p = PALETTE
    return f"""
QMainWindow, QDialog {{ background: {p['bg']}; }}
QWidget {{
    background: {p['bg']}; color: {p['text']};
    font-family: "Segoe UI", "Roboto", sans-serif; font-size: 12px;
}}

QPushButton {{
    background: #262626; border: 1px solid {p['border2']};
    color: {p['text']}; padding: 5px 10px; border-radius: 3px;
    text-align: left; min-height: 28px;
}}
QPushButton:hover  {{ background: #333333; border-color: #4A4A4A; color: #FFFFFF; }}
QPushButton:pressed {{ background: {p['accent']}; border-color: {p['accent']}; color: #FFFFFF; }}
QPushButton[accent="true"] {{ background: #1A1A55; border-color: {p['accent']}; color: #8888FF; }}
QPushButton[accent="true"]:hover {{ background: #2A2A77; color: #AAAAFF; }}

QGroupBox {{
    font-weight: bold; color: {p['muted']}; border: 1px solid {p['border']};
    border-radius: 4px; margin-top: 10px; padding-top: 6px;
    font-size: 10px; letter-spacing: 1px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {p['muted']}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p['panel']}; border: 1px solid {p['border2']};
    color: {p['text']}; padding: 3px 7px; border-radius: 3px; min-height: 24px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {p['accent']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {p['panel']}; border: 1px solid {p['border2']};
    color: {p['text']}; selection-background-color: {p['accent']};
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: {p['grid']}; width: 8px; border-radius: 4px; margin: 2px 1px;
}}
QScrollBar::handle:vertical {{ background: #404040; border-radius: 4px; min-height: 32px; }}
QScrollBar::handle:vertical:hover   {{ background: #606060; }}
QScrollBar::handle:vertical:pressed {{ background: {p['accent']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QTextEdit {{ background: {p['panel']}; border: 1px solid {p['border']}; color: {p['text']}; }}

QCheckBox {{ color: #AAAAAA; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {p['border2']};
    border-radius: 2px; background: {p['panel']};
}}
QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; }}

QSplitter::handle {{ background: {p['border']}; width: 1px; height: 1px; }}

QLabel[role="header"]  {{ color: #FFFFFF; font-size: 16px; font-weight: bold; padding: 4px 0; }}
QLabel[role="section"] {{ color: {p['muted']}; font-size: 10px; letter-spacing: 1px; padding: 6px 0 2px 0; }}

QStatusBar {{ background: {p['topbar']}; color: {p['muted']}; font-size: 11px; border-top: 1px solid {p['border']}; }}
QStatusBar[status="ok"]    {{ color: {p['ok']}; }}
QStatusBar[status="error"] {{ color: {p['error']}; }}
"""


QSS: str = _build_qss()
