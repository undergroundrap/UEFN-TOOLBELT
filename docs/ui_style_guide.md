# UEFN Toolbelt — UI Style Guide

> **This is the canonical reference for all windowed UI in the UEFN Toolbelt.**
> Every tool, plugin, or feature that opens a PySide6 window — whether built by Ocean,
> a third-party plugin author, or an AI agent — **must follow this guide exactly.**
> Consistency is non-negotiable. Users should never be able to tell which window came from
> which tool.

---

## Architecture (How the Theme System Works)

```
core/theme.py          ← SINGLE SOURCE OF TRUTH — all hex values live here
      │
      ├── core/base_window.py   ← ToolbeltWindow base class (auto-applies theme)
      │         │
      │         └── verse_device_graph._DeviceGraphWindow   (example)
      │         └── your_tool.MyToolWindow                  (your new window)
      │
      └── dashboard_pyside6.py  ← imports QSS as _QSS from theme
```

**To change the platform's appearance:** edit `PALETTE` in `core/theme.py`.
One edit → dashboard, device graph, every tool window, every plugin updates automatically.
**Never hard-code a hex color value anywhere else.**

---

## TL;DR (The Minimum You Need)

```python
from ..core.base_window import ToolbeltWindow

class MyToolWindow(ToolbeltWindow):
    def __init__(self):
        super().__init__(title="MY TOOL", width=1100, height=700)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vl = QVBoxLayout(root)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        bar, bl = self.make_topbar("MY TOOL")
        bl.addWidget(self.make_btn("Run", accent=True, cb=self._run))
        bl.addStretch()
        vl.addWidget(bar)
        # ... rest of UI

# In your tool function:
win = MyToolWindow()
win.show_in_uefn()   # ← QSS + Slate tick, both handled automatically
```

That's it. No manual `setStyleSheet`, no Slate tick boilerplate, no color constants to copy.

---

## Color Palette

All values live in `core/theme.PALETTE`. Use the token name — never raw hex.

| Token | Hex | Use |
|---|---|---|
| `bg` | `#181818` | Window / root background |
| `panel` | `#212121` | Input fields, text areas, secondary panels |
| `card` | `#1E1E1E` | Elevated surfaces, node bodies |
| `border` | `#2A2A2A` | Subtle borders, dividers, splitters |
| `border2` | `#363636` | Heavier borders, node outlines, button borders |
| `text` | `#CCCCCC` | Primary text |
| `muted` | `#555555` | Secondary / hint / disabled text |
| `accent` | `#3A3AFF` | Primary action, focus rings, pressed states |
| `brand` | `#e94560` | Toolbelt brand red — window titles **only** |
| `warn` | `#f1c40f` | Warnings |
| `error` | `#FF4444` | Errors |
| `ok` | `#44FF88` | Success / healthy |
| `grid` | `#1A1A1A` | Canvas grid lines, scrollbar track |
| `topbar` | `#111111` | Top bar / status bar background |

### In Python code

```python
# Hex string (for inline stylesheets)
self.hex("accent")      # → "#3A3AFF"

# QColor (for QPainter / QBrush / QPen)
self.P["accent"]        # → QColor("#3A3AFF")

# Outside a ToolbeltWindow (e.g. QGraphicsItem subclasses)
from ..core.theme import PALETTE
_P = {k: QColor(v) for k, v in PALETTE.items()}
_P["accent"]            # → QColor("#3A3AFF")
```

---

## ToolbeltWindow — Reference

`core/base_window.ToolbeltWindow` provides these helpers. Call them from inside
any subclass — no imports or style arguments needed.

### `make_topbar(title) → (QWidget, QHBoxLayout)`
46px dark bar with brand-red title. Add buttons/inputs to the layout.
```python
bar, bl = self.make_topbar("VERSE GRAPH")
bl.addWidget(self.make_btn("Scan", accent=True, cb=self._scan))
bl.addStretch()
vl.addWidget(bar)
```

### `make_btn(text, accent, cb, height, width) → QPushButton`
`accent=True` → primary blue tint. `cb` wires `clicked` signal.
```python
self.make_btn("Export", cb=self._export)
self.make_btn("Run", accent=True, cb=self._run, height=32)
```

### `make_label(text, role, color, size, bold) → QLabel`
Roles: `'body'` · `'header'` · `'section'` · `'muted'` · `'brand'`
```python
self.make_label("SECTION TITLE", role="section")
self.make_label("Status: ok", color=self.hex("ok"))
```

### `make_divider() → QFrame`
Horizontal separator at `border2` color.

### `make_text_area(height, text_color, mono, read_only) → QTextEdit`
```python
self.make_text_area(60, mono=True)              # code output
self.make_text_area(52, mono=False, read_only=False)  # editable notes
self.make_text_area(50, text_color=self.hex("warn"))  # warning output
```

### `make_hbar(height) → QLabel`  +  `set_hbar_value(bar, value, max_value, ...)`
Thin gradient health / progress bar.
```python
self._bar = self.make_hbar(4)
vl.addWidget(self._bar)
# Later:
self.set_hbar_value(self._bar, 73)   # green fill at 73%
self.set_hbar_value(self._bar, 35)   # red fill at 35%
```

### `make_scroll_panel(width, border_left) → (QScrollArea, QWidget)`
Side-panel scroll area. Add content to the returned inner widget.
```python
scroll, inner = self.make_scroll_panel(300)
inner_lay = QVBoxLayout(inner)
```

### `show_in_uefn()`
Show the window AND register the Slate tick driver.
Always call this instead of `show()`.

### `close_clean()`
Close + unregister the Slate tick cleanly.

---

## Typography

| Role | Font | Size | Weight |
|---|---|---|---|
| Window / tool title | Segoe UI | 12pt | Bold |
| Section header | Segoe UI | 9–10pt | Bold |
| Body / labels | Segoe UI | 9pt | Normal |
| Monospaced output | Consolas | 8pt | Normal |
| Status bar | Segoe UI | 11px | Normal |

---

## Semantic Color Usage

| Situation | Token |
|---|---|
| Window / tool title | `brand` |
| Success, healthy, passing | `ok` |
| Warning, degraded | `warn` |
| Error, failed, broken | `error` |
| Primary action | `accent` |
| Body text | `text` |
| Hint / disabled / secondary | `muted` |
| `@editable` / device refs | `brand` |
| Events / `.Subscribe` | `#2ecc71` (semantic green, not in palette) |
| Functions / `.calls` | `#3498db` (semantic blue, not in palette) |

---

## UEFN Slate Tick — Why It's Required

> UEFN runs Unreal's **Slate** event loop, not Qt's. Without driving
> `app.processEvents()` from a Slate callback, Qt windows open but never render.

`show_in_uefn()` handles this automatically. If you ever need the raw pattern:

```python
import unreal
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
win.show()

handle = [None]
def _tick(dt):
    try:
        if not win.isVisible():
            unreal.unregister_slate_post_tick_callback(handle[0]); return
        app.processEvents()
    except Exception:
        try: unreal.unregister_slate_post_tick_callback(handle[0])
        except Exception: pass
handle[0] = unreal.register_slate_post_tick_callback(_tick)
```

---

## QGraphicsScene / Canvas Theming

For tools with a node graph or canvas (like the Verse Device Graph):

```python
from ..core.theme import PALETTE
from PySide6.QtGui import QColor

# Module-level palette dict for QGraphicsItem subclasses
_P = {k: QColor(v) for k, v in PALETTE.items()}

# Scene background
scene = QGraphicsScene()
scene.setBackgroundBrush(QBrush(_P["bg"]))

# View
view = QGraphicsView(scene)
view.setBackgroundBrush(QBrush(_P["bg"]))
view.setStyleSheet(f"background:{PALETTE['bg']}; border:none;")

# Grid lines (in drawBackground override)
p.setPen(QPen(_P["border"]))

# Node body gradient
grad = QLinearGradient(0, 0, 0, NODE_H)
grad.setColorAt(0, _P["card"])
grad.setColorAt(1, _P["bg"])

# Node outline
outline_color = _P["border2"]    # default
outline_color = _P["accent"]     # selected
```

---

## What NOT to Do

- **No purple, navy, or blue-grey tints.** Banned values: `#0a0a1a`, `#1a1a30`,
  `#2a2a45`, `#3a3a5a`, `#888899`, `#444466`, `#d0d0e0`, or any hex where
  R/G/B are unequal in a blue/purple direction. The palette is strictly neutral
  dark grey + semantic accents.
- **No inline `setStyleSheet` with raw hex** — use `self.hex("token")`.
- **No manual `_QSS` import** from `dashboard_pyside6` — use `ToolbeltWindow`.
- **No subclassing `QMainWindow` directly** — always use `ToolbeltWindow`.
- **No calling `show()` alone** — always `show_in_uefn()` or the window is invisible.
- **No custom button colors** — `accent=True` for primary, default QSS for secondary.

---

## For AI Agents

If you are an AI agent generating code for this project, apply these rules unconditionally:

1. Subclass `ToolbeltWindow` from `..core.base_window` — never `QMainWindow` directly.
2. Call `win.show_in_uefn()` — never `win.show()` alone.
3. Use `self.hex("token")` for hex strings, `self.P["token"]` for QColor.
4. Use `self.make_topbar`, `self.make_btn`, `self.make_text_area`, etc. — don't build widgets manually.
5. For `QGraphicsItem` subclasses: `from ..core.theme import PALETTE` and build a local `_P` dict.
6. **Never hard-code a hex color.** If a semantic token doesn't exist, add it to `core/theme.PALETTE`.
7. Reference implementation: `tools/verse_device_graph.py`

---

## Adding a New Palette Color

If you need a color that doesn't exist in `PALETTE`:

1. Add it to `PALETTE` in `core/theme.py` with a semantic name.
2. `QSS` rebuilds automatically on next reload — add a QSS rule to `_build_qss()` if needed.
3. Document it in the table above.
4. Use `self.hex("your_new_token")` in your tool.

Do **not** add a one-off color inline. If it's worth using, it's worth naming.

---

## Reference Implementation

`Content/Python/UEFN_Toolbelt/tools/verse_device_graph.py` is the canonical example:
- Subclasses `ToolbeltWindow` (search `_DeviceGraphWindow`)
- `_P` built from `PALETTE` for `QGraphicsItem` usage (search `_P = {k:`)
- `show_in_uefn()` in the registered tool function (search `run_verse_graph_open`)
- Full top bar, health bar, side scroll panel, QGraphicsScene canvas
