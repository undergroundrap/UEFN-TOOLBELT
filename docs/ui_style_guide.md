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
        super().__init__(title="UEFN Toolbelt — My Tool Name", width=1100, height=700)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vl = QVBoxLayout(root)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Only add a topbar if it carries actual toolbar buttons.
        # The OS title bar (set via title=) already shows the tool name —
        # never add make_topbar() just to repeat that text.
        bar, bl = self.make_topbar("MY TOOL")
        bl.addWidget(self.make_btn("Run", accent=True, cb=self._run))
        bl.addWidget(self.make_btn("Clear", cb=self._clear))
        bl.addStretch()
        vl.addWidget(bar)
        # ... rest of UI

# In your tool function:
win = MyToolWindow()
win.show_in_uefn()   # ← QSS + Slate tick, both handled automatically
```

That's it. No manual `setStyleSheet`, no Slate tick boilerplate, no color constants to copy.

---

## Window Title Format (Mandatory)

Every `ToolbeltWindow` title **must** follow this exact format:

```
"UEFN Toolbelt — Tool Name"
```

- The prefix is always `UEFN Toolbelt` (not "Toolbelt", not the project name)
- The separator is ` — ` (space + em dash + space)
- The tool name is title-case, no trailing punctuation

**Help dialogs** append ` Help` to the main window title:
```
"UEFN Toolbelt — Tool Name Help"
```

**Sub-dialogs** (edit note, confirm, etc.) use a descriptive suffix:
```
"UEFN Toolbelt — Edit Note"
"UEFN Toolbelt — Generated Verse Wiring"
```

This convention ensures every OS title bar, taskbar entry, and Alt+Tab preview reads
consistently — users always know they are inside Toolbelt.

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

## The `?` Help Button — Mandatory for Every Tool Window

Every tool that opens its own `ToolbeltWindow` **must** include a `?` help button. Users should never have to guess what a tool does or how to use it.

**Placement rule:**
- If the window has a topbar with toolbar buttons → add `?` as the last button on the right of the topbar
- If the window has no topbar → add `?` to the bottom action row, right-aligned after a stretch

```python
# Window with topbar (e.g. verse_device_graph)
bar, bl = self.make_topbar("VERSE GRAPH")
bl.addWidget(self.make_btn("Scan", accent=True, cb=self._scan))
bl.addStretch()
bl.addWidget(self.make_btn("?", cb=self._do_help, width=28))

# Window without topbar (e.g. prefab_migrator)
# Add ? to the bottom action row:
al.addWidget(b_primary_action)
al.addStretch()
al.addWidget(self._status_label)
al.addWidget(b_help)   # _btn("?"), fixedWidth=28, cb=self._do_help
```

**The help dialog pattern** (use this every time — copy it verbatim):
```python
class _HelpDialog(ToolbeltWindow):
    _CONTENT = """\
WHAT IS THIS?
...

─────────────────────────────────────────────────────────────────────────

TYPICAL WORKFLOW
...
"""
    def __init__(self):
        super().__init__(title="UEFN Toolbelt — My Tool Help", width=700, height=760)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vl = QVBoxLayout(root)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(self._CONTENT)
        editor.setFont(QFont("Consolas", 9))
        editor.setLineWrapMode(QTextEdit.NoWrap)   # ← always NoWrap
        editor.setStyleSheet(
            f"background:{self.hex('panel')}; color:{self.hex('text')}; border:none; padding:16px;"
        )
        vl.addWidget(editor)

# In the main window:
def _do_help(self):
    self._help_dlg = _HelpDialog()
    self._help_dlg.show_in_uefn()
```

**Help content must cover:**
1. What is this? (one paragraph)
2. Why it was made / what problem it solves
3. Typical workflow (numbered steps)
4. Options/parameters explained
5. Any known limitations

---

## ToolbeltWindow — Reference

`core/base_window.ToolbeltWindow` provides these helpers. Call them from inside
any subclass — no imports or style arguments needed.

### `make_topbar(title) → (QWidget, QHBoxLayout)`
46px dark bar with brand-red title. Use this **only when the bar carries actual toolbar buttons** (scan, export, refresh, etc.). The OS title bar already shows the window name — do NOT add `make_topbar()` just to repeat it with a stretch-only layout. This applies to **help dialogs and sub-windows too** — the OS title bar already identifies them.

```python
# ✅ Correct — topbar earns its place with real actions
bar, bl = self.make_topbar("VERSE GRAPH")
bl.addWidget(self.make_btn("Scan", accent=True, cb=self._scan))
bl.addWidget(self.make_btn("Export", cb=self._export))
bl.addStretch()
vl.addWidget(bar)

# ❌ Wrong — title-only topbar duplicates the OS window title
bar, bl = self.make_topbar("MY TOOL")
bl.addStretch()   # no buttons = just visual noise, remove this entire block
vl.addWidget(bar)
```

### Read-only text areas (help dialogs, logs)
For help/reference dialogs with pre-formatted text content, always set `NoWrap` to prevent separator lines and fixed-width content from wrapping:
```python
editor = QTextEdit()
editor.setReadOnly(True)
editor.setFont(QFont("Consolas", 9))
editor.setLineWrapMode(QTextEdit.NoWrap)  # ← prevents separator lines from splitting
editor.setStyleSheet(f"background:{self.hex('panel')}; color:{self.hex('text')}; border:none; padding:16px;")
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

## Dashboard Widgets — Layout Rules

These rules apply when building tabs in `dashboard_pyside6.py`. Violations cause crowded
or broken layouts that are hard to fix after the fact.

### Spinboxes (`_spin`)

**Minimum width: 90px.** The `_spin()` helper enforces `max(width, 90)` automatically.
Never pass a width below 90 — 3-digit numbers (e.g. `400`, `100`) will crowd the arrow
buttons and become unreadable.

```python
# ✓ correct
count_s = _spin(6, 1, 200)           # default width=90
size_s  = _spin(100, 10, 2000)       # default width=90
large_s = _spin(5000, 0, 99999, 0, 100)  # explicit 100px for 5-digit values

# ✗ wrong — clips numbers against arrows
count_s = _spin(6, 1, 200, width=60)
```

**Width budget by digit count:**
| Max value | Recommended width |
|---|---|
| 1–2 digits (0–99) | 90px |
| 3 digits (100–999) | 90px |
| 4 digits (1000–9999) | 90px |
| 5+ digits (10000+) | 100px |
| Decimal (e.g. 1.00) | 90px |

**Do NOT style `QSpinBox::up-arrow` or `QDoubleSpinBox::down-arrow` in QSS.**
Setting `width`/`height` on arrow subcontrols with no image source causes a null-paint
crash (`EXCEPTION_ACCESS_VIOLATION`) in UEFN's embedded Qt runtime when the user clicks
the spinbox. Arrow subcontrols must be left at Qt native defaults.

### Rows with multiple inputs (`_btn_inp` groups)

All `_btn_inp` calls in the **same group** must use widgets of the **same width**.
The button expands to fill remaining space — if one row has a 70px widget and another
has a 90px widget, the buttons have different widths and the group looks broken.

```python
# ✓ correct — both widgets same width, buttons align
vol_sp    = _spin(1.0, 0.0, 4.0, 2)   # 90px (default)
radius_sp = _spin(2000.0, 0.0, 99999.0, 0)  # 90px (default)
_btn_inp(g, "Set Volume", lambda *_: ..., vol_sp)
_btn_inp(g, "Set Radius", lambda *_: ..., radius_sp)

# ✗ wrong — mismatched widgets, unequal button widths
vol_sp    = _spin(1.0, 0.0, 4.0, 2, 70)   # 70px
radius_sp = _spin(2000.0, 0.0, 99999.0, 0, 90)  # 90px
```

### Row density limit

**Max 2 label+widget pairs per `QHBoxLayout` row.** More than 2 pairs causes overflow
on typical panel widths. Use multiple rows instead:

```python
# ✓ correct
_lrow(("Type:", lt_combo), ("Intensity:", intensity_sp))
_lrow(("Color:", color_inp), ("Radius:", atten_sp))

# ✗ wrong — 4 pairs overflow
_lrow(("Type:", lt_combo), ("Intensity:", intensity_sp), ("Color:", color_inp), ("Radius:", atten_sp))
```

---

## Window Identity — Title and Icon

Every Toolbelt window must use the canonical TB icon and a consistent title format.
This is handled automatically by `ToolbeltWindow` — you just need to pass the right title.

### Icon

`ToolbeltWindow.__init__` calls `make_toolbelt_icon()` from `core/base_window.py` automatically.
**Never recreate the icon inline.** If you need the icon outside a `ToolbeltWindow` (e.g. the
main dashboard, which extends `QMainWindow` directly), import from the same source:

```python
from ..core.base_window import make_toolbelt_icon
self.setWindowIcon(make_toolbelt_icon())
```

### Title format

| Window type | Title string |
|---|---|
| Main dashboard | `"UEFN Toolbelt"` |
| Tool sub-window | `"UEFN Toolbelt — Tool Name"` |

```python
# ✓ correct
super().__init__(title="UEFN Toolbelt — Verse Device Graph", width=1400, height=860)

# ✗ wrong — no brand prefix
super().__init__(title="Verse Device Graph")

# ✗ wrong — shape/emoji prefix in title (the icon already serves this purpose)
self.setWindowTitle("⬡  UEFN Toolbelt")
```

The icon is a 64×64 blue hexagon with white "TB" text (`#3A3AFF` fill, Segoe UI 16pt Bold).
Do not use a different icon, a plain `QIcon()`, or no icon at all.

---

## Dialogs and Sub-Windows — The Hard Rule

> **Never use `QDialog`, `QInputDialog`, `QMessageBox`, or any other unstyled Qt dialog.**
> Every window the user sees — confirmation prompts, text editors, progress indicators,
> error messages — must be a `ToolbeltWindow` subclass with `show_in_uefn()`.
> Unstyled dialogs break the visual contract and are immediately obvious as unfinished.

### Pattern (canonical example: `_NoteEditDialog` in `verse_device_graph.py`)

```python
class MyPromptDialog(ToolbeltWindow):
    def __init__(self, initial_value: str = "") -> None:
        super().__init__(title="UEFN Toolbelt — My Prompt", width=440, height=300)
        self._value = initial_value
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        vl = QVBoxLayout(root)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        bar, bl = self.make_topbar("MY PROMPT")
        bl.addWidget(self.make_btn("Save", accent=True, cb=self._save))
        bl.addWidget(self.make_btn("Cancel", cb=self.close))
        bl.addStretch()
        vl.addWidget(bar)

        body = QWidget()
        body.setStyleSheet(f"background:{self.hex('panel')};")
        fl = QVBoxLayout(body)
        fl.setContentsMargins(16, 14, 16, 14)
        fl.setSpacing(8)

        fl.addWidget(self.make_label("Value", role="muted"))
        self._edit = QLineEdit(self._value)
        self._edit.setFixedHeight(28)
        self._edit.setStyleSheet(
            f"background:#212121; color:{self.hex('text')}; "
            f"border:1px solid #363636; border-radius:3px; padding:3px 8px;"
        )
        fl.addWidget(self._edit)
        vl.addWidget(body)

    def _save(self) -> None:
        self._value = self._edit.text().strip()
        # update whatever owns this dialog, then close
        self.close()

# Open it — always show_in_uefn(), never show() alone:
self._dlg = MyPromptDialog(initial_value="hello")   # store ref to prevent GC
self._dlg.show_in_uefn()
```

### Rules

- Always store the dialog reference on `self` (e.g. `self._dlg = ...`) to prevent Python GC from destroying it while Qt still holds the window open.
- Use `make_topbar` + `make_btn` — the title bar must be consistent with every other window.
- Body background: `self.hex('panel')` (`#212121`). Input fields: `background:#212121; border:1px solid #363636`.
- For multi-line text: use `QTextEdit` with the same input QSS.
- `show_in_uefn()` registers the Slate tick driver automatically. Never call `exec()` or `show()` alone.

---

## What NOT to Do

- **No `QDialog`, `QInputDialog`, or `QMessageBox`** — use a `ToolbeltWindow` subclass. See "Dialogs and Sub-Windows" above.
- **No calling `show()` or `exec()` on dialogs** — always `show_in_uefn()`.
- **No floating dialog reference** — always assign to `self._something` before calling `show_in_uefn()` or the window will be garbage-collected.
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
7. **Never use `QDialog`, `QInputDialog`, or `QMessageBox`** — subclass `ToolbeltWindow`. See "Dialogs and Sub-Windows".
8. Store dialog references on `self` before calling `show_in_uefn()` to prevent GC.
9. Reference implementation: `tools/verse_device_graph.py` — `_NoteEditDialog` for dialogs, `_DeviceGraphWindow` for full tool windows.

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
