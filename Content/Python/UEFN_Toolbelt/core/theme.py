"""
UEFN Toolbelt — Theme
======================
Single source of truth for all UI colors and QSS styling.

To change one color everywhere: edit PALETTE or call set_theme().
To add a new theme: add an entry to THEMES below — nothing else needed.

Usage:
    from ..core.theme import PALETTE, QSS, color, set_theme, list_themes

    set_theme("ocean")              # applies live to all open windows
    hex_str = color("accent")       # "#3A3AFF"
    QColor palette usage:
        from ..core.theme import PALETTE
        _P = {k: QColor(v) for k, v in PALETTE.items()}
"""

from __future__ import annotations

from typing import Dict, List

# ── Color Palette ──────────────────────────────────────────────────────────────
# This dict reflects the ACTIVE theme. set_theme() updates it in-place.
# Always read from PALETTE — never hard-code a hex value elsewhere.

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

# ── Theme Library ──────────────────────────────────────────────────────────────
# Each theme is a full PALETTE override dict.
# Add a new theme: copy an existing entry and change the values.

THEMES: Dict[str, Dict[str, str]] = {

    "toolbelt_dark": {  # ← Default
        "bg":      "#181818",
        "panel":   "#212121",
        "card":    "#1E1E1E",
        "border":  "#2A2A2A",
        "border2": "#363636",
        "text":    "#CCCCCC",
        "muted":   "#555555",
        "accent":  "#3A3AFF",
        "brand":   "#e94560",
        "warn":    "#f1c40f",
        "error":   "#FF4444",
        "ok":      "#44FF88",
        "grid":    "#1A1A1A",
        "topbar":  "#111111",
    },

    "midnight": {  # GitHub dark — deep navy black
        "bg":      "#0D1117",
        "panel":   "#161B22",
        "card":    "#13181F",
        "border":  "#21262D",
        "border2": "#30363D",
        "text":    "#E6EDF3",
        "muted":   "#8B949E",
        "accent":  "#58A6FF",
        "brand":   "#F78166",
        "warn":    "#D29922",
        "error":   "#F85149",
        "ok":      "#3FB950",
        "grid":    "#090D12",
        "topbar":  "#090D12",
    },

    "ocean": {  # Deep ocean blue — Ocean Bennett's personal palette
        "bg":      "#0A1628",
        "panel":   "#0F1F38",
        "card":    "#0C1930",
        "border":  "#1A3050",
        "border2": "#1E4070",
        "text":    "#B8D4F0",
        "muted":   "#4A7A9B",
        "accent":  "#00BFFF",
        "brand":   "#00E5FF",
        "warn":    "#FFB347",
        "error":   "#FF4466",
        "ok":      "#00FF88",
        "grid":    "#081220",
        "topbar":  "#060E1A",
    },

    "nord": {  # Arctic, north-blue — popular Nord scheme
        "bg":      "#2E3440",
        "panel":   "#3B4252",
        "card":    "#343A47",
        "border":  "#434C5E",
        "border2": "#4C566A",
        "text":    "#ECEFF4",
        "muted":   "#7B88A1",
        "accent":  "#88C0D0",
        "brand":   "#BF616A",
        "warn":    "#EBCB8B",
        "error":   "#BF616A",
        "ok":      "#A3BE8C",
        "grid":    "#272C38",
        "topbar":  "#252B36",
    },

    "forest": {  # Dark green — natural, focused
        "bg":      "#0F1B12",
        "panel":   "#162018",
        "card":    "#121A14",
        "border":  "#1E3020",
        "border2": "#2A4A2C",
        "text":    "#C8E8C8",
        "muted":   "#4A7A4A",
        "accent":  "#4CAF7D",
        "brand":   "#FF6644",
        "warn":    "#F0C040",
        "error":   "#FF4444",
        "ok":      "#66DD44",
        "grid":    "#0C1610",
        "topbar":  "#0A120C",
    },

    "daylight": {  # Light — for bright monitors and accessibility
        "bg":      "#F5F5F5",
        "panel":   "#FFFFFF",
        "card":    "#EFEFEF",
        "border":  "#DDDDDD",
        "border2": "#CCCCCC",
        "text":    "#1A1A2A",
        "muted":   "#888888",
        "accent":  "#2255CC",
        "brand":   "#CC1A3A",
        "warn":    "#B87800",
        "error":   "#CC2222",
        "ok":      "#1A8822",
        "grid":    "#E8E8E8",
        "topbar":  "#E0E0E0",
    },
}

# ── Active theme ───────────────────────────────────────────────────────────────

_active_theme: str = "toolbelt_dark"


def color(token: str) -> str:
    """Return the hex string for a palette token."""
    return PALETTE.get(token, token)


def get_current_theme() -> str:
    """Return the name of the currently active theme."""
    return _active_theme


def list_themes() -> List[str]:
    """Return all available theme names."""
    return list(THEMES.keys())


# ── Subscriber system ──────────────────────────────────────────────────────────
# Windows subscribe to receive the new QSS string whenever set_theme() is called.
# theme.py never imports from any other Toolbelt module — no circular imports.

_listeners: list = []


def subscribe(fn) -> None:
    """Register a callable(qss: str) to be notified on theme changes."""
    if fn not in _listeners:
        _listeners.append(fn)


def unsubscribe(fn) -> None:
    """Remove a previously registered listener."""
    try:
        _listeners.remove(fn)
    except ValueError:
        pass


def _notify(qss: str) -> None:
    dead = []
    for fn in _listeners:
        try:
            fn(qss)
        except RuntimeError:   # Qt C++ object deleted without unsubscribing
            dead.append(fn)
        except Exception:
            pass
    for fn in dead:
        unsubscribe(fn)


# ── set_theme ──────────────────────────────────────────────────────────────────

def set_theme(name: str) -> bool:
    """
    Switch to a named theme. Updates PALETTE in-place, rebuilds QSS,
    and notifies all subscribed windows so they re-apply the stylesheet live.

    Returns True on success, False if name is not in THEMES.
    Falls back to 'toolbelt_dark' if name is unknown.
    """
    global QSS, _active_theme

    if name not in THEMES:
        name = "toolbelt_dark"   # silent fallback

    theme_data = THEMES[name]
    PALETTE.update(theme_data)
    QSS = _build_qss()
    _active_theme = name
    _notify(QSS)
    return name in THEMES


# ── QSS builder ────────────────────────────────────────────────────────────────
# Built from PALETTE so a theme swap automatically produces the right stylesheet.

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
