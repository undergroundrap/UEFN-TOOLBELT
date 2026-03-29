"""
UEFN TOOLBELT — cooker_optimizer.py
=====================================
Manage "Editor Only" actor flags to help large projects cook successfully.

When a project fails to cook due to out-of-memory errors, exclude actor batches
from the cooked build progressively until the cook succeeds, then restore them.
Confidence estimates are built from your cook feedback history across sessions.

Workflow:
  1. tb.run("cooker_scan")                             # audit level actors
  2. tb.run("cooker_mark_batch", percent=50, dry_run=True)  # preview
  3. tb.run("cooker_mark_batch", percent=50, dry_run=False) # apply
  4. Launch session in UEFN -- report success/fail in the window
  5. Iterate percent up or down until cook succeeds
  6. tb.run("cooker_unmark_all")                       # ALWAYS restore before publishing

Credits:
  Original concept & tool: BiomeForge (CookerOptimizer)
  Native Toolbelt implementation: Ocean Bennett (UEFN Toolbelt v1.9.8+)
"""

import os
import json
import math
import unreal
from ..registry import register_tool
from ..core import log_info, log_warning, log_error

# ── Module-level scan cache (shared between headless tools and the window) ─────
_scan_cache: dict = {
    "rows":    [],    # [{label, class_name, actor_type, is_editor_only, actor}]
    "scanned": False,
}

# ─────────────────────────────────────────────────────────────────────────────
#  Cook feedback — persisted across sessions
# ─────────────────────────────────────────────────────────────────────────────

def _feedback_path() -> str:
    return os.path.join(
        unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "cooker_feedback.json"
    )


def _load_feedback() -> list:
    try:
        p = _feedback_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_feedback(history: list) -> None:
    try:
        p = _feedback_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        log_warning(f"cooker: could not save feedback history: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Actor helpers
# ─────────────────────────────────────────────────────────────────────────────

def _all_actors() -> list:
    try:
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        return list(sub.get_all_level_actors() or [])
    except Exception:
        return list(unreal.EditorLevelLibrary.get_all_level_actors() or [])


def _selected_actors() -> list:
    try:
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        return list(sub.get_selected_level_actors() or [])
    except Exception:
        return list(unreal.EditorLevelLibrary.get_selected_level_actors() or [])


def _is_blueprint(actor) -> bool:
    try:
        return not str(actor.get_class().get_path_name()).startswith("/Script/")
    except Exception:
        return False


def _is_static_mesh(actor) -> bool:
    try:
        return actor.get_class().get_name() == "StaticMeshActor"
    except Exception:
        return False


def _is_landscape(actor) -> bool:
    try:
        return actor.get_class().get_name() in {
            "Landscape", "LandscapeProxy", "LandscapeStreamingProxy"
        }
    except Exception:
        return False


def _get_editor_only(actor) -> bool:
    try:
        return bool(actor.get_editor_property("is_editor_only_actor"))
    except Exception:
        return False


def _set_editor_only(actor, value: bool) -> bool:
    try:
        actor.set_editor_property("is_editor_only_actor", value)
        return True
    except Exception:
        return False


def _save_level() -> None:
    try:
        unreal.EditorLevelLibrary.save_current_level()
    except Exception as e:
        log_warning(f"cooker: level save failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Confidence estimator — weighted nearest-neighbour
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_confidence(history: list, percent: float, pool: int):
    """Return (pct_int | None, basis_str)."""
    if not history:
        return None, "Awaiting first cook result"
    if pool <= 0:
        return None, "No scanned pool"

    # Exact match
    exact = [h for h in history
             if abs(h["percent"] - percent) < 0.0001 and h["pool"] == pool]
    if exact:
        avg = sum(1.0 if h["success"] else 0.0 for h in exact) / len(exact)
        return (
            int(round(avg * 100)),
            f"Exact match from {len(exact)} result(s) at {percent:g}% with pool {pool}",
        )

    # Weighted interpolation
    ws = wt = 0.0
    for h in history:
        pd = abs(h["percent"] - percent) / 100.0
        qd = abs(h["pool"] - pool) / float(max(pool, 1))
        w  = 1.0 / (1.0 + pd * 6.0 + qd * 2.5)
        ws += (1.0 if h["success"] else 0.0) * w
        wt += w

    if wt <= 0:
        return None, "Insufficient history"
    return (
        int(round((ws / wt) * 100)),
        f"Rough estimate from {len(history)} result(s), weighted by setting similarity",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Headless tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="cooker_scan",
    category="Optimization",
    description=(
        "Scan level actors and return a count breakdown by type and editor-only status. "
        "Run before cooker_mark_batch. Filters: blueprints, static_meshes, landscapes."
    ),
    tags=["cooker", "cook", "editor-only", "optimization", "scan", "memory", "oom"],
    example='tb.run("cooker_scan", blueprints=True, static_meshes=True)',
)
def cooker_scan(
    blueprints: bool = True,
    static_meshes: bool = True,
    landscapes: bool = False,
    exclude_already_editor_only: bool = False,
    **kwargs,
) -> dict:
    """
    Scan level actors for cooker optimization.

    Args:
        blueprints:                  Include Blueprint actors (default True)
        static_meshes:               Include StaticMesh actors (default True)
        landscapes:                  Include Landscape actors (default False — use cautiously)
        exclude_already_editor_only: Skip actors already marked editor-only (default False)

    Returns:
        {
          "status": "ok",
          "total": int, "editor_only": int, "not_editor_only": int,
          "blueprints": int, "static_meshes": int, "landscapes": int
        }
    """
    if not (blueprints or static_meshes or landscapes):
        return {"status": "error", "error": "Enable at least one actor type filter."}

    rows = []
    for actor in _all_actors():
        if actor is None:
            continue
        is_eo = _get_editor_only(actor)
        if exclude_already_editor_only and is_eo:
            continue

        if blueprints and _is_blueprint(actor):
            atype = "blueprint"
        elif static_meshes and _is_static_mesh(actor):
            atype = "static_mesh"
        elif landscapes and _is_landscape(actor):
            atype = "landscape"
        else:
            continue

        try:
            label = actor.get_actor_label()
        except Exception:
            label = "<unknown>"
        try:
            cls = actor.get_class().get_name()
        except Exception:
            cls = "unknown"

        rows.append({
            "actor":          actor,
            "label":          label,
            "class_name":     cls,
            "actor_type":     atype,
            "is_editor_only": is_eo,
        })

    rows.sort(key=lambda r: (r["actor_type"], r["class_name"].lower(), r["label"].lower()))
    _scan_cache["rows"]    = rows
    _scan_cache["scanned"] = True

    total  = len(rows)
    eo_cnt = sum(1 for r in rows if r["is_editor_only"])
    bp_cnt = sum(1 for r in rows if r["actor_type"] == "blueprint")
    sm_cnt = sum(1 for r in rows if r["actor_type"] == "static_mesh")
    ls_cnt = sum(1 for r in rows if r["actor_type"] == "landscape")

    log_info(f"cooker_scan: {total} eligible (bp={bp_cnt} sm={sm_cnt} ls={ls_cnt} eo={eo_cnt})")
    return {
        "status":          "ok",
        "total":           total,
        "editor_only":     eo_cnt,
        "not_editor_only": total - eo_cnt,
        "blueprints":      bp_cnt,
        "static_meshes":   sm_cnt,
        "landscapes":      ls_cnt,
        "tip": "Run cooker_mark_batch(percent=50, dry_run=True) to preview which actors would be marked.",
    }


@register_tool(
    name="cooker_mark_batch",
    category="Optimization",
    description=(
        "Mark a percentage of scanned actors as editor-only to reduce cook load. "
        "Run cooker_scan first. Always use dry_run=True to preview before applying. "
        "Start at percent=50, iterate down until cook succeeds, then cooker_unmark_all."
    ),
    tags=["cooker", "cook", "editor-only", "optimization", "batch", "mark"],
    example='tb.run("cooker_mark_batch", percent=50, dry_run=True)',
)
def cooker_mark_batch(
    percent: float = 50.0,
    dry_run: bool = True,
    **kwargs,
) -> dict:
    """
    Mark a percentage of scanned actors as editor-only.

    Args:
        percent:  Percentage of scanned pool to mark (1-100). Start at 50.
        dry_run:  Preview without changes if True (default True — always preview first).

    Returns:
        {
          "status": "ok", "dry_run": bool, "percent": float,
          "pool": int, "target_count": int, "changed": int, "failed": int,
          "actors": [str, ...]  -- first 50 labels
        }
    """
    if not _scan_cache["scanned"] or not _scan_cache["rows"]:
        return {"status": "error", "error": "Run cooker_scan first."}
    if percent <= 0 or percent > 100:
        return {"status": "error", "error": "percent must be between 1 and 100."}

    rows   = _scan_cache["rows"]
    total  = len(rows)
    target = max(1, math.floor(total * (percent / 100.0)))

    # Even distribution across sorted pool (mirrors original algorithm)
    step    = total / float(target)
    indices: set = set()
    for i in range(target):
        indices.add(min(int(round(i * step)), total - 1))
    candidate = 0
    while len(indices) < target and candidate < total:
        indices.add(candidate)
        candidate += 1

    chosen = [rows[i] for i in sorted(indices)]
    labels = [r["label"] for r in chosen]

    if dry_run:
        log_info(f"cooker_mark_batch DRY RUN: {len(chosen)}/{total} at {percent:g}%")
        return {
            "status":       "ok",
            "dry_run":      True,
            "percent":      percent,
            "pool":         total,
            "target_count": len(chosen),
            "changed":      0,
            "failed":       0,
            "actors":       labels[:50],
            "tip": "Set dry_run=False to apply. Run cooker_unmark_all before publishing.",
        }

    changed = 0
    failed  = []
    with unreal.ScopedEditorTransaction("Cooker Optimizer — mark editor-only") as _t:
        for row in chosen:
            if _set_editor_only(row["actor"], True):
                row["is_editor_only"] = True
                changed += 1
            else:
                failed.append(row["label"])

    _save_level()
    log_info(f"cooker_mark_batch: marked {changed}/{len(chosen)} at {percent:g}%  failed={len(failed)}")
    return {
        "status":        "ok",
        "dry_run":       False,
        "percent":       percent,
        "pool":          total,
        "target_count":  len(chosen),
        "changed":       changed,
        "failed":        len(failed),
        "failed_labels": failed[:20],
        "tip": "Launch a session. If cook fails, increase percent. If succeeds, reduce or run cooker_unmark_all.",
    }


@register_tool(
    name="cooker_unmark_all",
    category="Optimization",
    description=(
        "Clear the editor-only flag from all scanned actors. "
        "Always run this before publishing your map."
    ),
    tags=["cooker", "cook", "editor-only", "optimization", "restore", "unmark"],
    example='tb.run("cooker_unmark_all")',
)
def cooker_unmark_all(**kwargs) -> dict:
    """
    Remove editor-only flag from every actor in the current scan cache.

    Returns:
        {"status": "ok", "changed": int, "failed": int}
    """
    if not _scan_cache["scanned"] or not _scan_cache["rows"]:
        return {"status": "error", "error": "Run cooker_scan first."}

    changed = 0
    failed  = []
    with unreal.ScopedEditorTransaction("Cooker Optimizer — unmark all") as _t:
        for row in _scan_cache["rows"]:
            if row["is_editor_only"]:
                if _set_editor_only(row["actor"], False):
                    row["is_editor_only"] = False
                    changed += 1
                else:
                    failed.append(row["label"])

    _save_level()
    log_info(f"cooker_unmark_all: cleared {changed}  failed={len(failed)}")
    return {
        "status":        "ok",
        "changed":       changed,
        "failed":        len(failed),
        "failed_labels": failed[:20],
    }


@register_tool(
    name="cooker_mark_selection",
    category="Optimization",
    description=(
        "Mark or clear editor-only on the current viewport selection. "
        "mark=True excludes actors from cook, mark=False restores them."
    ),
    tags=["cooker", "cook", "editor-only", "selection", "mark", "optimization"],
    example='tb.run("cooker_mark_selection", mark=True)',
)
def cooker_mark_selection(mark: bool = True, **kwargs) -> dict:
    """
    Apply or remove editor-only flag on the current viewport selection.

    Args:
        mark: True to mark as editor-only, False to clear (default True).

    Returns:
        {"status": "ok", "action": str, "changed": int, "failed": int}
    """
    actors = _selected_actors()
    if not actors:
        return {"status": "error", "error": "No actors selected in the viewport."}

    changed = 0
    failed  = []
    action  = "mark" if mark else "clear"

    with unreal.ScopedEditorTransaction(f"Cooker Optimizer — {action} selection") as _t:
        for actor in actors:
            if _set_editor_only(actor, mark):
                changed += 1
                # Sync scan cache if populated
                try:
                    lbl = actor.get_actor_label()
                    for row in _scan_cache["rows"]:
                        if row["label"] == lbl:
                            row["is_editor_only"] = mark
                except Exception:
                    pass
            else:
                try:
                    failed.append(actor.get_actor_label())
                except Exception:
                    failed.append("<unknown>")

    _save_level()
    log_info(f"cooker_mark_selection: {action} {changed}/{len(actors)}  failed={len(failed)}")
    return {
        "status":        "ok",
        "action":        action,
        "changed":       changed,
        "failed":        len(failed),
        "failed_labels": failed[:20],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PySide6 window
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="cooker_open",
    category="Optimization",
    description=(
        "Open the Cooker Optimizer window — scan actors, mark/unmark editor-only batches "
        "to reduce cook load, and track cook success history with confidence estimates. "
        "Based on CookerOptimizer by BiomeForge."
    ),
    tags=["cooker", "cook", "editor-only", "optimization", "window", "ui"],
    example='tb.run("cooker_open")',
)
def cooker_open(**kwargs) -> dict:
    """Open the Cooker Optimizer PySide6 window."""
    try:
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        win = _build_cooker_window()
        win.show()
        win.raise_()
        win.activateWindow()
        log_info("cooker_open: window opened")
        return {"status": "ok"}
    except Exception as e:
        log_error(f"cooker_open failed: {e}")
        return {"status": "error", "error": str(e)}


def _build_cooker_window():
    """Construct and return the Cooker Optimizer window (deferred PySide6 import)."""
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
        QPushButton, QLineEdit, QFrame, QScrollArea, QTextEdit,
    )
    from PySide6.QtCore import Qt
    from ..core.base_window import ToolbeltWindow

    # ── Help dialog ───────────────────────────────────────────────────────────
    class _HelpDialog(ToolbeltWindow):
        def __init__(self, parent=None):
            super().__init__(title="UEFN Toolbelt — Cooker Optimizer Help", parent=parent)
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
                "UEFN Toolbelt -- Cooker Optimizer\n"
                "Based on CookerOptimizer by BiomeForge.\n"
                "===========================================\n\n"
                "WHAT IT DOES\n"
                "------------\n"
                "Sets 'is_editor_only_actor' on batches of level actors so they\n"
                "are excluded from the cooked build. This reduces cook memory\n"
                "load so large projects can cook in stages.\n\n"
                "WORKFLOW\n"
                "--------\n"
                "1. Select actor types to include (Blueprint, Static Mesh, Landscape)\n"
                "2. Click Scan\n"
                "3. Choose a batch size (1/2, 1/3, 1/4, or custom %)\n"
                "4. Launch a session in UEFN\n"
                "5. Report Yes / No in the Cook Feedback section\n"
                "6. If cook failed: increase the batch %. If succeeded: reduce or Undo All\n"
                "7. ALWAYS click Undo All before publishing your map\n\n"
                "WARNING\n"
                "-------\n"
                "Editor-only actors are EXCLUDED from cooked builds.\n"
                "Broken references can occur if gameplay-critical actors are marked.\n"
                "NEVER publish a map with editor-only actors still set.\n"
                "Back up your project before using this tool.\n\n"
                "COOK CONFIDENCE\n"
                "---------------\n"
                "Records whether each batch setting resulted in a successful cook.\n"
                "Estimates cook probability for future settings based on history.\n"
                "History is saved to Saved/UEFN_Toolbelt/cooker_feedback.json.\n\n"
                "MCP / HEADLESS TOOLS\n"
                "--------------------\n"
                "cooker_scan          -- audit actors\n"
                "cooker_mark_batch    -- mark N% as editor-only (dry_run=True first)\n"
                "cooker_unmark_all    -- restore all\n"
                "cooker_mark_selection -- mark/clear viewport selection\n\n"
                "CREDITS\n"
                "-------\n"
                "Original tool: BiomeForge (CookerOptimizer)\n"
                "Toolbelt integration: Ocean Bennett (UEFN Toolbelt v1.9.8+)"
            )
            L.addWidget(text)
            self.setCentralWidget(w)
            self.resize(560, 580)

    # ── Main window ───────────────────────────────────────────────────────────
    class CookerOptimizerWindow(ToolbeltWindow):
        def __init__(self):
            super().__init__(title="UEFN Toolbelt — Cooker Optimizer")
            self._feedback: list = _load_feedback()
            self._current_percent: float = 50.0
            self._help_win = None

            central = QWidget()
            root_l = QVBoxLayout(central)
            root_l.setContentsMargins(0, 0, 0, 0)
            root_l.setSpacing(0)

            # Topbar
            bar, bl = self.make_topbar("")
            self._scan_btn = self.make_btn("Scan", accent=True, cb=self._do_scan)
            bl.addWidget(self._scan_btn)
            bl.addWidget(self.make_btn("Undo All", cb=self._do_unmark_all))
            bl.addStretch()
            bl.addWidget(self.make_btn("?", cb=self._show_help))
            root_l.addWidget(bar)

            # Scroll content
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("border:none;")
            content = QWidget()
            cl = QVBoxLayout(content)
            cl.setContentsMargins(14, 14, 14, 14)
            cl.setSpacing(10)
            scroll.setWidget(content)
            root_l.addWidget(scroll)

            # ── Filters ───────────────────────────────────────────────────────
            f_frame, f_l = self._section("Actor Filters")
            type_row = QHBoxLayout()
            self._cb_bp = QCheckBox("Blueprint Actors")
            self._cb_sm = QCheckBox("Static Mesh Actors")
            self._cb_ls = QCheckBox("Landscapes")
            self._cb_bp.setChecked(True)
            self._cb_sm.setChecked(True)
            for cb in (self._cb_bp, self._cb_sm, self._cb_ls):
                cb.setStyleSheet(f"color:{self.hex('text')};")
                type_row.addWidget(cb)
            type_row.addStretch()
            f_l.addLayout(type_row)
            self._cb_excl = QCheckBox("Exclude actors already marked editor-only from scan")
            self._cb_excl.setStyleSheet(f"color:{self.hex('text_dim')};")
            f_l.addWidget(self._cb_excl)
            cl.addWidget(f_frame)

            # ── Scan metrics ──────────────────────────────────────────────────
            m_frame, m_l = self._section("Scan Metrics")
            metrics_row = QHBoxLayout()
            self._m_total   = self._stat_card(metrics_row, "Eligible", "0")
            self._m_eo      = self._stat_card(metrics_row, "Editor-Only", "0", self.hex("ok"))
            self._m_not_eo  = self._stat_card(metrics_row, "Not Editor-Only", "0", self.hex("error"))
            self._m_bp      = self._stat_card(metrics_row, "Blueprints", "0")
            self._m_sm      = self._stat_card(metrics_row, "Static Meshes", "0")
            self._m_ls      = self._stat_card(metrics_row, "Landscapes", "0")
            metrics_row.addStretch()
            m_l.addLayout(metrics_row)
            cl.addWidget(m_frame)

            # ── Batch controls ────────────────────────────────────────────────
            b_frame, b_l = self._section("Apply Editor-Only Batch")
            warn = QLabel(
                "  Do NOT publish with editor-only actors set. "
                "Always click Undo All before shipping your map."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{self.hex('warn')}; font-size:11px; padding:2px 0;")
            b_l.addWidget(warn)

            btn_row = QHBoxLayout()
            for lbl, pct in [("1/2  (50%)", 50.0), ("1/3  (33%)", 33.33), ("1/4  (25%)", 25.0)]:
                btn_row.addWidget(
                    self.make_btn(lbl, cb=lambda _=False, p=pct: self._apply_pct(p))
                )
            btn_row.addSpacing(12)
            pct_lbl = QLabel("Custom %:")
            pct_lbl.setStyleSheet(f"color:{self.hex('text_dim')};")
            btn_row.addWidget(pct_lbl)
            self._custom_pct = QLineEdit("25")
            self._custom_pct.setFixedWidth(58)
            self._custom_pct.setStyleSheet(
                f"background:{self.hex('panel')}; color:{self.hex('text')}; "
                f"border:1px solid {self.hex('border2')}; padding:4px; border-radius:3px;"
            )
            self._custom_pct.textChanged.connect(self._on_custom_changed)
            btn_row.addWidget(self._custom_pct)
            btn_row.addWidget(self.make_btn("Apply %", accent=True, cb=self._apply_custom))
            btn_row.addSpacing(12)
            btn_row.addWidget(self.make_btn("Mark Selected", cb=lambda: self._mark_sel(True)))
            btn_row.addWidget(self.make_btn("Clear Selected", cb=lambda: self._mark_sel(False)))
            btn_row.addStretch()
            b_l.addLayout(btn_row)

            # Preview cards
            prev_row = QHBoxLayout()
            self._p_pct   = self._stat_card(prev_row, "Batch Size", "50%")
            self._p_count = self._stat_card(prev_row, "Actors to Mark", "0", self.hex("warn"))
            self._p_pool  = self._stat_card(prev_row, "Scanned Pool", "0")
            prev_row.addStretch()
            b_l.addLayout(prev_row)
            cl.addWidget(b_frame)

            # ── Cook feedback ─────────────────────────────────────────────────
            c_frame, c_l = self._section("Cook Feedback")
            note = QLabel(
                "After attempting a session launch, report whether it cooked successfully. "
                "Only click after you see a clean session launch or an out-of-memory error."
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color:{self.hex('text_dim')}; font-size:11px;")
            c_l.addWidget(note)

            cook_btns = QHBoxLayout()
            self._cook_yes = self.make_btn("  Cook Succeeded", cb=lambda: self._record_cook(True))
            self._cook_no  = self.make_btn("  Cook Failed",    cb=lambda: self._record_cook(False))
            self._cook_yes.setEnabled(False)
            self._cook_no.setEnabled(False)
            cook_btns.addWidget(self._cook_yes)
            cook_btns.addWidget(self._cook_no)
            cook_btns.addStretch()
            c_l.addLayout(cook_btns)

            conf_row = QHBoxLayout()
            self._c_results = self._stat_card(conf_row, "Reported Results", "0")
            self._c_conf    = self._stat_card(conf_row, "Cook Confidence", "-", self.hex("warn"))
            conf_row.addStretch()
            c_l.addLayout(conf_row)
            self._conf_basis = QLabel("Awaiting first cook result")
            self._conf_basis.setStyleSheet(f"color:{self.hex('muted')}; font-size:11px;")
            c_l.addWidget(self._conf_basis)
            cl.addWidget(c_frame)

            # Status bar
            self._status = QLabel("Select actor types and click Scan.")
            self._status.setStyleSheet(
                f"color:{self.hex('muted')}; padding:8px 14px; font-size:11px; "
                f"border-top:1px solid {self.hex('border')};"
            )
            root_l.addWidget(self._status)

            self.setCentralWidget(central)
            self.resize(960, 720)
            self._refresh_feedback()

        # ── Layout helpers ────────────────────────────────────────────────────
        def _section(self, title: str):
            """Return (outer QFrame, content QVBoxLayout)."""
            frame = QFrame()
            frame.setStyleSheet(
                f"background:{self.hex('panel')}; "
                f"border:1px solid {self.hex('border')}; border-radius:4px;"
            )
            outer = QVBoxLayout(frame)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            hdr = QLabel(f"  {title}")
            hdr.setStyleSheet(
                f"color:{self.hex('text_bright')}; font-weight:bold; font-size:12px; "
                f"padding:8px 12px; "
                f"border-bottom:1px solid {self.hex('border')}; border-radius:0px; background:transparent;"
            )
            outer.addWidget(hdr)
            inner_w = QWidget()
            inner_w.setStyleSheet("background:transparent; border:none;")
            inner_l = QVBoxLayout(inner_w)
            inner_l.setContentsMargins(12, 8, 12, 12)
            inner_l.setSpacing(6)
            outer.addWidget(inner_w)
            return frame, inner_l

        def _stat_card(self, layout, label: str, initial: str, color: str = None) -> QLabel:
            """Add a metric card to layout and return the value QLabel for updates."""
            color = color or self.hex("text")
            card = QFrame()
            card.setFixedWidth(140)
            card.setStyleSheet(
                f"background:{self.hex('card')}; "
                f"border:1px solid {self.hex('border')}; border-radius:4px;"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{self.hex('muted')}; font-size:10px; border:none; background:transparent;")
            val = QLabel(initial)
            val.setStyleSheet(f"color:{color}; font-size:20px; font-weight:bold; border:none; background:transparent;")
            cl.addWidget(lbl)
            cl.addWidget(val)
            layout.addWidget(card)
            return val

        # ── Actions ───────────────────────────────────────────────────────────
        def _do_scan(self):
            r = cooker_scan(
                blueprints=self._cb_bp.isChecked(),
                static_meshes=self._cb_sm.isChecked(),
                landscapes=self._cb_ls.isChecked(),
                exclude_already_editor_only=self._cb_excl.isChecked(),
            )
            if r["status"] == "ok":
                self._m_total.setText(str(r["total"]))
                self._m_eo.setText(str(r["editor_only"]))
                self._m_not_eo.setText(str(r["not_editor_only"]))
                self._m_bp.setText(str(r["blueprints"]))
                self._m_sm.setText(str(r["static_meshes"]))
                self._m_ls.setText(str(r["landscapes"]))
                can_feedback = r["total"] > 0
                self._cook_yes.setEnabled(can_feedback)
                self._cook_no.setEnabled(can_feedback)
                self._refresh_preview()
                self._set_status(f"Scan complete — {r['total']} eligible actors.")
            else:
                self._set_status(f"Scan error: {r.get('error')}")

        def _do_unmark_all(self):
            r = cooker_unmark_all()
            if r["status"] == "ok":
                self._do_scan()
                self._set_status(f"Undo All — cleared editor-only on {r['changed']} actors.")
            else:
                self._set_status(f"Undo All error: {r.get('error')}")

        def _apply_pct(self, pct: float):
            self._current_percent = pct
            self._refresh_preview()
            r = cooker_mark_batch(percent=pct, dry_run=False)
            if r["status"] == "ok":
                self._do_scan()
                self._set_status(
                    f"Marked {r['changed']} actors editor-only ({pct:g}%). "
                    "Launch a session and report the result below."
                )
            else:
                self._set_status(f"Error: {r.get('error')}")

        def _apply_custom(self):
            try:
                pct = float(self._custom_pct.text().strip())
                self._apply_pct(pct)
            except ValueError:
                self._set_status("Enter a valid number for custom %.")

        def _on_custom_changed(self, text: str):
            try:
                self._current_percent = float(text.strip())
                self._refresh_preview()
            except ValueError:
                pass

        def _mark_sel(self, mark: bool):
            r = cooker_mark_selection(mark=mark)
            if r["status"] == "ok":
                self._do_scan()
                verb = "Marked" if mark else "Cleared"
                self._set_status(f"{verb} editor-only on {r['changed']} selected actors.")
            else:
                self._set_status(f"Error: {r.get('error')}")

        def _record_cook(self, success: bool):
            rows = _scan_cache.get("rows", [])
            if not rows:
                self._set_status("Run a scan first.")
                return
            pool   = len(rows)
            target = max(1, math.floor(pool * (self._current_percent / 100.0)))
            self._feedback.append({
                "percent": self._current_percent,
                "pool":    pool,
                "count":   target,
                "success": success,
            })
            _save_feedback(self._feedback)
            self._refresh_feedback()
            result = "SUCCESS" if success else "FAILED"
            self._set_status(f"Recorded cook result: {result} at {self._current_percent:g}%")

        def _refresh_preview(self):
            rows  = _scan_cache.get("rows", [])
            pool  = len(rows)
            count = max(1, math.floor(pool * (self._current_percent / 100.0))) if pool else 0
            self._p_pct.setText(f"{self._current_percent:g}%")
            self._p_count.setText(str(count))
            self._p_pool.setText(str(pool))
            self._refresh_feedback()

        def _refresh_feedback(self):
            rows = _scan_cache.get("rows", [])
            pct, basis = _estimate_confidence(
                self._feedback, self._current_percent, len(rows)
            )
            self._c_results.setText(str(len(self._feedback)))
            self._c_conf.setText(f"{pct}%" if pct is not None else "-")
            self._conf_basis.setText(basis)

        def _set_status(self, text: str):
            self._status.setText(text)

        def _show_help(self):
            if not self._help_win:
                self._help_win = _HelpDialog(self)
            self._help_win.show()
            self._help_win.raise_()

    return CookerOptimizerWindow()
