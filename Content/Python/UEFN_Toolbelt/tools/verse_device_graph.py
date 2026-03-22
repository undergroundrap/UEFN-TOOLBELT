"""
UEFN TOOLBELT — Verse Device Graph
========================================
Interactive force-directed node graph of every Creative/Verse device in the
current level. Shows wiring, broken links, orphans, and an Architecture Health
Score (0–100) so you know at a glance how well-connected your island logic is.

ATTRIBUTION:
  Concept and inspiration: ImmatureGamer's uefn-device-graph (tkinter)
    GitHub: https://github.com/ImmatureGamer/uefn-device-graph
    Twitter/X: https://x.com/ImmatureGamer
  This Toolbelt implementation is an independent rewrite using PySide6 /
  QGraphicsScene, integrated into the Toolbelt theme + config + MCP stack.
  Full credit goes to ImmatureGamer for pioneering UEFN device graph tooling.

WHAT MAKES THIS DIFFERENT:
  • Force-directed layout (Fruchterman-Reingold, animated at 60fps) — nodes
    self-organize by connection topology, not a static circle.
  • Architecture Health Score — orphan penalty + broken-link penalty +
    unused-function penalty + verse-coverage bonus = one number you can track.
  • Cluster detection (Union-Find) — isolated device groups get a cluster ID
    so you can spot disconnected sub-systems at a glance.
  • Two-pass Verse parser — fast regex scan then schema type validation via
    toolbelt's schema_utils for reliable @editable type resolution.
  • Three MCP-callable tools — verse_graph_scan returns the full adjacency
    dict; Claude Code can reason about your architecture without opening a UI.
  • Config-backed Verse path — no hardcoded user paths anywhere.
  • QGraphicsScene/QGraphicsView — proper GPU-accelerated Qt canvas with
    anti-aliased bezier edges, glow effects, and dot-grid background.

USAGE:
    tb.run("verse_graph_open")                       # open the graph window
    tb.run("verse_graph_scan")                       # headless scan, returns dict
    tb.run("verse_graph_export", path="graph.json")  # export to JSON
    tb.run("config_set", key="verse.project_path",
           value="C:/MyIsland/Content")              # set default verse path
"""

from __future__ import annotations

import json
import math
import os
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import unreal

from ..core import log_info, log_warning, log_error, get_config, notify
from ..core.theme import PALETTE as _PALETTE
from ..core.base_window import ToolbeltWindow
from ..registry import register_tool


# ─────────────────────────────────────────────────────────────────────────────
#  PySide6 guard  (mirrors the project-wide convention)
# ─────────────────────────────────────────────────────────────────────────────

_PYSIDE6 = False
try:
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QPushButton, QLabel, QLineEdit, QTextEdit, QScrollArea,
        QFrame, QFileDialog, QGraphicsView, QGraphicsScene,
        QGraphicsItem, QGraphicsObject,
    )
    from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
    from PySide6.QtGui import (
        QPainter, QPen, QBrush, QColor, QFont,
        QPainterPath, QLinearGradient, QRadialGradient,
    )
    _PYSIDE6 = True
except ImportError:
    pass  # ToolbeltWindow stub handles the no-PySide6 case


# ─────────────────────────────────────────────────────────────────────────────
#  Visual constants
# ─────────────────────────────────────────────────────────────────────────────

_NODE_W = 200
_NODE_H = 76

_CAT_COLORS: Dict[str, str] = {
    "verse":       "#e94560",
    "elimination": "#ff6b35",
    "spawner":     "#27ae60",
    "guard":       "#2ecc71",
    "hud":         "#2980b9",
    "round":       "#8e44ad",
    "item":        "#f39c12",
    "settings":    "#16a085",
    "timer":       "#e67e22",
    "trigger":     "#d35400",
    "score":       "#3498db",
    "audio":       "#1abc9c",
    "teleport":    "#9b59b6",
    "tracker":     "#e67e22",
    "zone":        "#27ae60",
    "generic":     "#5d6d7e",
}

_EDGE_COLORS: Dict[str, str] = {
    "editable": "#e94560",
    "event":    "#2ecc71",
    "call":     "#3498db",
}

# ─────────────────────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DeviceNode:
    id: str
    label: str
    class_name: str
    category: str
    color: str
    world_loc: Tuple[float, float, float]
    actor: object  # unreal.Actor or None
    verse_file: str = ""
    verse_path: str = ""
    editables: List[Dict] = field(default_factory=list)
    events:    List[Dict] = field(default_factory=list)
    calls:     List[Dict] = field(default_factory=list)
    functions: List[str]  = field(default_factory=list)
    called_functions: Set[str] = field(default_factory=set)
    warnings: List[str] = field(default_factory=list)
    errors:   List[str] = field(default_factory=list)
    note: str = ""
    cluster_id: int = -1
    # Layout velocity (used by force simulation)
    x: float = 0.0
    y: float = 0.0


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    label: str
    edge_type: str   # "editable" | "event" | "call"
    color: str


@dataclass
class GraphData:
    nodes: List[DeviceNode]
    edges: List[GraphEdge]
    warnings: List[str]
    health_score: int
    cluster_count: int
    verse_file_count: int


# ─────────────────────────────────────────────────────────────────────────────
#  Verse parser  (two-pass: regex + schema type validation)
# ─────────────────────────────────────────────────────────────────────────────

class _VerseParser:
    """
    Pass 1 — fast regex scan for structure.
    Pass 2 — schema type validation via toolbelt's schema_utils (best-effort).
    """

    _DEVICE_CLASS  = re.compile(r'(\w+)\s*:=\s*class\s*\(\s*creative_device\s*\)')
    _EDITABLE      = re.compile(r'@editable\s+(?:var\s+)?(\w+)\s*:\s*([\w\[\]<>?_]+)')
    _SUBSCRIBE     = re.compile(r'(\w+)\.(\w+)\s*\.\s*Subscribe\s*\(\s*(\w+)\s*\)')
    _FUNC_DEF      = re.compile(
        r'^[ \t]*(\w+)\s*(?:<[\w,\s]+>)?\s*\([^)]*\)\s*(?:<[\w,\s]+>)?\s*:\s*void\s*=',
        re.MULTILINE,
    )
    _FUNC_CALL     = re.compile(r'\b(\w+)\s*\(')
    _USING         = re.compile(r'using\s*\{\s*([^\}]+)\s*\}')

    # Keywords that look like function names but aren't
    _KW = frozenset(["class", "using", "if", "for", "loop", "sync", "race", "branch",
                     "block", "spawn", "await", "return"])

    @classmethod
    def parse(cls, filepath: str) -> Optional[Dict]:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            return None

        out: Dict = {
            "file": os.path.basename(filepath),
            "filepath": filepath,
            "device": "",
            "modules": [],
            "editables": [],
            "events": [],
            "calls": [],
            "functions": [],
            "called_functions": set(),
        }

        # ── Pass 1 — structure ───────────────────────────────────────────
        m = cls._DEVICE_CLASS.search(src)
        if m:
            out["device"] = m.group(1)

        out["modules"] = [m.group(1).strip() for m in cls._USING.finditer(src)]

        for m in cls._EDITABLE.finditer(src):
            out["editables"].append({"name": m.group(1), "type": m.group(2)})

        for m in cls._SUBSCRIBE.finditer(src):
            out["events"].append({
                "source": m.group(1), "event": m.group(2), "handler": m.group(3),
            })

        editable_names = {e["name"] for e in out["editables"]}
        for en in editable_names:
            for m in re.finditer(rf'\b{re.escape(en)}\s*\.\s*(\w+)\s*[\(\[]', src):
                fn = m.group(1)
                if fn not in ("Subscribe", "Unsubscribe", "SubscribeOnce"):
                    out["calls"].append({"target": en, "func": fn})

        seen_funcs: Dict[str, None] = {}  # ordered dedup
        for m in cls._FUNC_DEF.finditer(src):
            fname = m.group(1)
            if fname not in cls._KW:
                seen_funcs[fname] = None
        out["functions"] = list(seen_funcs.keys())

        out["called_functions"] = {m.group(1) for m in cls._FUNC_CALL.finditer(src)}

        # ── Pass 2 — type validation (best-effort, never fatal) ──────────
        try:
            from .. import schema_utils
            for ed in out["editables"]:
                clean = ed["type"].replace("?", "").replace("[]", "")
                ed["is_device_ref"] = (
                    "device" in ed["type"].lower()
                    or schema_utils.get_class_info(clean) is not None
                )
        except Exception:
            for ed in out["editables"]:
                ed["is_device_ref"] = "device" in ed["type"].lower()

        return out


# ─────────────────────────────────────────────────────────────────────────────
#  Category classifier
# ─────────────────────────────────────────────────────────────────────────────

_EXTRA_KW: Dict[str, str] = {
    "capture": "zone", "area": "zone",
    "weapon": "item", "chest": "item",
    "bot": "guard", "ai": "guard",
    "npc": "guard",
}

def _classify(class_name: str, label: str) -> str:
    text = (class_name + " " + label).lower()
    for key in _CAT_COLORS:
        if key in text:
            return key
    for kw, cat in _EXTRA_KW.items():
        if kw in text:
            return cat
    return "generic"


# ─────────────────────────────────────────────────────────────────────────────
#  Graph builder
# ─────────────────────────────────────────────────────────────────────────────

class _GraphBuilder:

    @staticmethod
    def build(level_devs: List[Dict], verse_data: List[Dict]) -> GraphData:
        nodes: List[DeviceNode] = []
        edges: List[GraphEdge] = []
        all_warnings: List[str] = []

        # ── Nodes from level scan ────────────────────────────────────────
        for i, dev in enumerate(level_devs):
            cat   = _classify(dev["class"], dev["label"])
            color = _CAT_COLORS.get(cat, _CAT_COLORS["generic"])
            nodes.append(DeviceNode(
                id=f"d{i}", label=dev["label"], class_name=dev["class"],
                category=cat, color=color, world_loc=dev["loc"], actor=dev["actor"],
            ))

        # ── Attach verse data ────────────────────────────────────────────
        for vd in verse_data:
            if not vd or not vd.get("device"):
                continue
            match = _GraphBuilder._match(nodes, vd["device"])
            if match:
                match.verse_file = vd["file"]
                match.verse_path = vd["filepath"]
                match.editables        = vd["editables"]
                match.events           = vd["events"]
                match.calls            = vd["calls"]
                match.functions        = vd["functions"]
                match.called_functions = vd["called_functions"]
            else:
                # Verse-only device (base class not placed in level)
                nodes.append(DeviceNode(
                    id=f"v_{vd['device']}", label=vd["device"],
                    class_name="VerseDevice", category="verse",
                    color=_CAT_COLORS["verse"], world_loc=(0.0, 0.0, 0.0),
                    actor=None, verse_file=vd["file"], verse_path=vd["filepath"],
                    editables=vd["editables"], events=vd["events"],
                    calls=vd["calls"], functions=vd["functions"],
                    called_functions=vd["called_functions"],
                ))

        # ── Edges from @editable device refs ─────────────────────────────
        for node in nodes:
            for ed in node.editables:
                if not ed.get("is_device_ref"):
                    continue
                type_key = (
                    ed["type"].lower()
                    .replace("?", "").replace("[]", "")
                    .replace("_device", "").replace("device", "").replace("_", "")
                )
                target = _GraphBuilder._find_target(nodes, node.id, type_key)
                if target:
                    edges.append(GraphEdge(
                        source_id=node.id, target_id=target.id,
                        label=ed["name"], edge_type="editable",
                        color=_EDGE_COLORS["editable"],
                    ))
                else:
                    msg = f"Broken @editable: {ed['name']} ({ed['type']})"
                    node.errors.append(msg)
                    all_warnings.append(f"{node.label}: {msg}")

        # ── Edges from .Subscribe() ──────────────────────────────────────
        for node in nodes:
            for ev in node.events:
                src_key = ev["source"].lower().replace("_", "")
                target  = _GraphBuilder._find_by_label(nodes, node.id, src_key)
                if target:
                    edges.append(GraphEdge(
                        source_id=target.id, target_id=node.id,
                        label=ev["event"], edge_type="event",
                        color=_EDGE_COLORS["event"],
                    ))

        # ── Orphan detection ─────────────────────────────────────────────
        connected: Set[str] = set()
        for e in edges:
            connected.add(e.source_id)
            connected.add(e.target_id)
        for node in nodes:
            if node.id not in connected and node.category != "settings":
                node.warnings.append("Orphan: no connections to other devices")
                all_warnings.append(f"{node.label}: orphan device")

        # ── Unused function detection ────────────────────────────────────
        _lifecycle = frozenset([
            "OnBegin", "OnEnd", "OnRound", "OnPlayerAdded", "OnPlayerRemoved",
            "OnActivated", "OnDeactivated",
        ])
        for node in nodes:
            for fn in node.functions:
                if fn in _lifecycle:
                    continue
                if fn not in node.called_functions:
                    node.warnings.append(f"Unused function: {fn}()")

        # ── Cluster detection (Union-Find) ───────────────────────────────
        cluster_count = _GraphBuilder._assign_clusters(nodes, edges)

        # ── Deduplicate edges ────────────────────────────────────────────
        seen_edges: Set[Tuple] = set()
        unique_edges: List[GraphEdge] = []
        for e in edges:
            k = (e.source_id, e.target_id, e.label)
            if k not in seen_edges:
                seen_edges.add(k)
                unique_edges.append(e)

        health = _GraphBuilder._health_score(nodes, unique_edges)

        return GraphData(
            nodes=nodes, edges=unique_edges, warnings=all_warnings,
            health_score=health, cluster_count=cluster_count,
            verse_file_count=sum(1 for n in nodes if n.verse_file),
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _match(nodes: List[DeviceNode], verse_name: str) -> Optional[DeviceNode]:
        vn = verse_name.lower().replace("_", "")
        for n in nodes:
            nl = n.label.lower().replace(" ", "").replace("_", "")
            if vn in nl or nl in vn:
                return n
        return None

    @staticmethod
    def _find_target(nodes: List[DeviceNode], src_id: str, type_key: str) -> Optional[DeviceNode]:
        best, best_score = None, 0
        for n in nodes:
            if n.id == src_id:
                continue
            tc = n.class_name.lower().replace("_", "").replace("device", "")
            tl = n.label.lower().replace(" ", "").replace("_", "")
            score = (2 if type_key in tc else 0) + (1 if type_key in tl else 0) + (1 if tc in type_key else 0)
            if score > best_score:
                best_score, best = score, n
        return best if best_score > 0 else None

    @staticmethod
    def _find_by_label(nodes: List[DeviceNode], src_id: str, key: str) -> Optional[DeviceNode]:
        for n in nodes:
            if n.id == src_id:
                continue
            nl = n.label.lower().replace(" ", "").replace("_", "")
            if key in nl or nl in key:
                return n
        return None

    @staticmethod
    def _assign_clusters(nodes: List[DeviceNode], edges: List[GraphEdge]) -> int:
        parent = {n.id: n.id for n in nodes}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            parent[find(a)] = find(b)

        for e in edges:
            if e.source_id in parent and e.target_id in parent:
                union(e.source_id, e.target_id)

        cluster_map: Dict[str, int] = {}
        cid = 0
        for node in nodes:
            root = find(node.id)
            if root not in cluster_map:
                cluster_map[root] = cid
                cid += 1
            node.cluster_id = cluster_map[root]

        return cid

    @staticmethod
    def _health_score(nodes: List[DeviceNode], edges: List[GraphEdge]) -> int:
        """
        Architecture Health Score (0–100).
          Orphan penalty  — up to 30 pts
          Broken-link penalty — up to 30 pts (capped)
          Unused-function penalty — up to 20 pts (capped)
          Verse-coverage bonus — up to 20 pts
        """
        if not nodes:
            return 100
        total   = len(nodes)
        orphans = sum(1 for n in nodes if any("Orphan" in w for w in n.warnings))
        broken  = sum(len(n.errors) for n in nodes)
        unused  = sum(sum(1 for w in n.warnings if "Unused" in w) for n in nodes)
        linked  = sum(1 for n in nodes if n.verse_file)

        score = (
            100
            - (orphans / total) * 30
            - min(broken * 5, 30)
            - min(unused * 3, 20)
            + (linked / total) * 20
        )
        return max(0, min(100, int(score)))


# ─────────────────────────────────────────────────────────────────────────────
#  Level scanner
# ─────────────────────────────────────────────────────────────────────────────

_DEV_KEYWORDS = frozenset([
    "device", "Device", "CRD", "VerseDevice", "Settings",
    "Spawner", "Timer", "Trigger", "Teleporter", "HUD",
    "Manager", "Controller", "Hub", "Zone", "Tracker",
])


def _scan_level() -> List[Dict]:
    result: List[Dict] = []
    try:
        sub    = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = sub.get_all_level_actors()
        for actor in actors:
            cn = actor.get_class().get_name()
            if any(kw in cn for kw in _DEV_KEYWORDS):
                try:
                    label = actor.get_actor_label()
                except Exception:
                    label = cn
                loc = actor.get_actor_location()
                result.append({
                    "label": label or cn,
                    "class": cn,
                    "loc":   (loc.x, loc.y, loc.z),
                    "actor": actor,
                })
    except Exception as exc:
        log_error(f"verse_device_graph: level scan failed: {exc}")
    return result


def _find_verse_files(root: str) -> List[str]:
    files: List[str] = []
    if not root or not os.path.exists(root):
        return files
    for dirpath, _, fnames in os.walk(root):
        for fname in fnames:
            if fname.endswith(".verse") and "digest" not in fname.lower():
                files.append(os.path.join(dirpath, fname))
    return files


# ─────────────────────────────────────────────────────────────────────────────
#  Registered tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="verse_graph_scan",
    category="Verse Helpers",
    description="Scan level devices + Verse files, return full architecture graph as structured dict.",
    tags=["verse", "graph", "devices", "scan", "architecture", "health"],
)
def run_verse_graph_scan(verse_path: str = "", **kwargs) -> dict:
    """
    Headless scan — no UI required. MCP-friendly.

    Args:
        verse_path: Root folder to walk for .verse files.
                    Defaults to config key 'verse.project_path'.

    Returns:
        {status, node_count, edge_count, health_score, cluster_count,
         verse_file_count, warning_count, warnings[], nodes[], edges[]}
    """
    path = verse_path or get_config().get("verse.project_path") or ""
    log_info(f"verse_graph_scan: scanning level + '{path}'")

    level_devs  = _scan_level()
    verse_files = _find_verse_files(path)
    verse_data  = [v for v in (_VerseParser.parse(vf) for vf in verse_files) if v]
    graph       = _GraphBuilder.build(level_devs, verse_data)

    log_info(
        f"verse_graph_scan: {len(graph.nodes)} devices, {len(graph.edges)} connections, "
        f"health={graph.health_score}/100, {graph.cluster_count} clusters"
    )

    return {
        "status":           "ok",
        "node_count":       len(graph.nodes),
        "edge_count":       len(graph.edges),
        "health_score":     graph.health_score,
        "cluster_count":    graph.cluster_count,
        "verse_file_count": graph.verse_file_count,
        "warning_count":    len(graph.warnings),
        "warnings":         graph.warnings,
        "nodes": [
            {
                "id":         n.id,
                "label":      n.label,
                "class":      n.class_name,
                "category":   n.category,
                "verse_file": n.verse_file,
                "editables":  n.editables,
                "events":     n.events,
                "errors":     n.errors,
                "warnings":   n.warnings,
                "cluster_id": n.cluster_id,
                "world_loc":  n.world_loc,
            }
            for n in graph.nodes
        ],
        "edges": [
            {"from": e.source_id, "to": e.target_id, "label": e.label, "type": e.edge_type}
            for e in graph.edges
        ],
    }


@register_tool(
    name="verse_graph_export",
    category="Verse Helpers",
    description="Export the Verse device graph to JSON for external tooling or archiving.",
    tags=["verse", "graph", "export", "json"],
)
def run_verse_graph_export(verse_path: str = "", output_path: str = "", **kwargs) -> dict:
    """Export graph data to JSON. Saved to Saved/UEFN_Toolbelt/ by default."""
    result = run_verse_graph_scan(verse_path=verse_path)
    if result["status"] != "ok":
        return result

    saved_dir = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    os.makedirs(saved_dir, exist_ok=True)
    out = output_path or os.path.join(saved_dir, "verse_device_graph.json")

    export = {k: v for k, v in result.items() if k not in ("status",)}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(export, fh, indent=2, default=str)

    log_info(f"verse_graph_export: saved → {out}")
    return {"status": "ok", "path": out, "node_count": result["node_count"]}


@register_tool(
    name="verse_graph_open",
    category="Verse Helpers",
    description="Open the interactive Verse Device Graph — force-directed layout, health score, cluster view.",
    tags=["verse", "graph", "ui", "visualize", "devices"],
)
def run_verse_graph_open(verse_path: str = "", **kwargs) -> dict:
    """Open the PySide6 graph window."""
    if not _PYSIDE6:
        log_error("verse_graph_open: PySide6 not installed. Run: pip install PySide6")
        return {"status": "error", "message": "PySide6 not installed."}
    try:
        path = verse_path or get_config().get("verse.project_path") or ""
        win  = _DeviceGraphWindow(verse_path=path)
        win.show_in_uefn()   # applies QSS + drives Slate tick automatically
        return {"status": "ok", "message": "Verse Device Graph window opened."}
    except Exception as exc:
        log_error(f"verse_graph_open: {exc}")
        return {"status": "error", "message": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
#  PySide6 UI
# ─────────────────────────────────────────────────────────────────────────────

if _PYSIDE6:

    # ── Palette — derived from core/theme.PALETTE (single source of truth) ───
    # To change colors platform-wide, edit core/theme.py — not here.

    _P = {k: QColor(v) for k, v in _PALETTE.items()}

    # ── NodeItem ──────────────────────────────────────────────────────────────

    class _NodeItem(QGraphicsObject):
        node_clicked = Signal(object)

        def __init__(self, data: DeviceNode) -> None:
            super().__init__()
            self.data = data
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            self.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.setAcceptHoverEvents(True)
            self.setPos(data.x, data.y)
            self._hovered = False

        def boundingRect(self) -> QRectF:
            return QRectF(-4, -4, _NODE_W + 8, _NODE_H + 8)

        def itemChange(self, change, value):
            if change == QGraphicsItem.ItemPositionHasChanged:
                self.data.x = self.x()
                self.data.y = self.y()
                if self.scene():
                    for it in self.scene().items():
                        if isinstance(it, _EdgeItem):
                            it.prepareGeometryChange()
            return super().itemChange(change, value)

        def hoverEnterEvent(self, e):
            self._hovered = True
            self.update()

        def hoverLeaveEvent(self, e):
            self._hovered = False
            self.update()

        def mousePressEvent(self, e):
            super().mousePressEvent(e)
            self.node_clicked.emit(self.data)

        def paint(self, p: QPainter, *_):
            nd  = self.data
            w, h = _NODE_W, _NODE_H
            r   = 6.0
            col = QColor(nd.color)
            sel = self.isSelected()
            p.setRenderHint(QPainter.Antialiasing)

            # Glow
            if sel or self._hovered:
                gc = QColor(col)
                gc.setAlpha(55 if sel else 28)
                glow = QRadialGradient(w / 2, h / 2, w * 0.75)
                glow.setColorAt(0, gc)
                glow.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(QBrush(glow))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(-12, -12, w + 24, h + 24, r + 12, r + 12)

            # Shadow
            p.setBrush(QBrush(QColor(0, 0, 0, 70)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(3, 4, w, h, r, r)

            # Body gradient — dashboard card colors
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, QColor("#242424"))
            grad.setColorAt(1, QColor("#1A1A1A"))
            p.setBrush(QBrush(grad))
            outline = col if sel else (QColor("#FFFFFF") if self._hovered else QColor("#363636"))
            p.setPen(QPen(outline, 1.5 if sel else 1.0))
            p.drawRoundedRect(0, 0, w, h, r, r)

            # Left accent bar (rounded left edge)
            bar = QPainterPath()
            bar.addRoundedRect(0, 0, 4, h, r, r)
            fill = QPainterPath()
            fill.addRect(2, 0, 4, h)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            p.drawPath(bar | fill)

            # Top shimmer line
            shine = QLinearGradient(0, 0, w, 0)
            shine.setColorAt(0, col)
            shine.setColorAt(0.6, QColor(col.red(), col.green(), col.blue(), 60))
            shine.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(shine))
            p.drawRect(0, 0, w, 2)

            # Label
            p.setPen(QPen(QColor("white")))
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            lbl = nd.label if len(nd.label) <= 22 else nd.label[:20] + "…"
            p.drawText(QRectF(10, 7, w - 18, 22), Qt.AlignVCenter | Qt.AlignLeft, lbl)

            # Class
            p.setPen(QPen(_P["muted"]))
            p.setFont(QFont("Segoe UI", 7))
            cn = nd.class_name.replace("Device_", "").replace("_C", "")
            cn = cn if len(cn) <= 28 else cn[:26] + "…"
            p.drawText(QRectF(10, 30, w - 18, 16), Qt.AlignVCenter | Qt.AlignLeft, cn)

            # Footer indicators
            p.setFont(QFont("Segoe UI", 6, QFont.Bold))
            if nd.verse_file:
                p.setPen(QPen(col))
                p.drawText(QRectF(10, h - 15, 24, 12), Qt.AlignVCenter | Qt.AlignLeft, "VS")
            if nd.note:
                p.setPen(QPen(_P["muted"]))
                p.drawText(QRectF(38, h - 15, 36, 12), Qt.AlignVCenter | Qt.AlignLeft, "NOTE")

            # Cluster badge (top-left)
            if nd.cluster_id >= 0:
                self._badge(p, 12, 12, 7, QColor(col.red(), col.green(), col.blue(), 160),
                            str(nd.cluster_id), QColor("white"))

            # Warning / error badge (top-right)
            if nd.errors:
                self._badge(p, w - 14, 14, 8, _P["error"], "!", QColor("white"))
            elif nd.warnings:
                self._badge(p, w - 14, 14, 8, _P["warn"], "!", QColor("#111"))

        @staticmethod
        def _badge(p: QPainter, cx: float, cy: float, r: float,
                   fill: QColor, text: str, fg: QColor) -> None:
            p.setBrush(QBrush(fill))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.setPen(QPen(fg))
            p.setFont(QFont("Segoe UI", 6, QFont.Bold))
            p.drawText(QRectF(cx - r, cy - r, r * 2, r * 2), Qt.AlignCenter, text)

    # ── EdgeItem ──────────────────────────────────────────────────────────────

    class _EdgeItem(QGraphicsItem):

        def __init__(self, data: GraphEdge, src: _NodeItem, tgt: _NodeItem) -> None:
            super().__init__()
            self.data = data
            self.src  = src
            self.tgt  = tgt
            self.setZValue(-1)
            self.setFlag(QGraphicsItem.ItemIsSelectable, False)

        def _pts(self):
            sp = self.src.pos() + QPointF(_NODE_W, _NODE_H / 2)
            tp = self.tgt.pos() + QPointF(0,      _NODE_H / 2)
            return sp, tp

        def boundingRect(self) -> QRectF:
            sp, tp = self._pts()
            mx = min(sp.x(), tp.x()) - 20
            my = min(sp.y(), tp.y()) - 20
            return QRectF(mx, my, abs(tp.x() - sp.x()) + 40, abs(tp.y() - sp.y()) + 40)

        def paint(self, p: QPainter, *_):
            sp, tp = self._pts()
            col     = QColor(self.data.color)
            is_evt  = self.data.edge_type == "event"

            p.setRenderHint(QPainter.Antialiasing)
            dx   = (tp.x() - sp.x()) * 0.5
            c1   = QPointF(sp.x() + dx, sp.y())
            c2   = QPointF(tp.x() - dx, tp.y())
            path = QPainterPath(sp)
            path.cubicTo(c1, c2, tp)

            pen = QPen(col, 1.8, Qt.DashLine if is_evt else Qt.SolidLine)
            if is_evt:
                pen.setDashPattern([5, 3])
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

            # Arrowhead
            angle = math.atan2(tp.y() - c2.y(), tp.x() - c2.x())
            al = 8.0
            a1 = QPointF(tp.x() - al * math.cos(angle - 0.45),
                         tp.y() - al * math.sin(angle - 0.45))
            a2 = QPointF(tp.x() - al * math.cos(angle + 0.45),
                         tp.y() - al * math.sin(angle + 0.45))
            arrow = QPainterPath(tp)
            arrow.lineTo(a1)
            arrow.lineTo(a2)
            arrow.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            p.drawPath(arrow)

            # Label at midpoint
            mid = path.pointAtPercent(0.5)
            p.setPen(QPen(QColor("#2A2A2A")))
            p.setFont(QFont("Segoe UI", 6))
            p.drawText(QRectF(mid.x() + 4, mid.y() - 9, 90, 12),
                       Qt.AlignLeft | Qt.AlignVCenter, self.data.label)

    # ── Canvas view ───────────────────────────────────────────────────────────

    class _GraphView(QGraphicsView):

        def __init__(self, scene: QGraphicsScene) -> None:
            super().__init__(scene)
            self.setRenderHint(QPainter.Antialiasing)
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
            self.setBackgroundBrush(QBrush(QColor("#181818")))
            self.setFrameStyle(0)
            self.setStyleSheet("background: #181818; border: none;")

        def wheelEvent(self, e):
            factor = 1.12 if e.angleDelta().y() > 0 else 0.89
            new_scale = self.transform().m11() * factor
            if 0.15 < new_scale < 3.5:
                self.scale(factor, factor)

        def drawBackground(self, p: QPainter, rect):
            super().drawBackground(p, rect)
            p.setPen(QPen(_P["grid"], 0.5))
            step = 40
            l = int(rect.left())  - (int(rect.left())  % step)
            t = int(rect.top())   - (int(rect.top())   % step)
            for x in range(l, int(rect.right()),  step):
                for y in range(t, int(rect.bottom()), step):
                    p.drawPoint(x, y)

    # ── Info panel ────────────────────────────────────────────────────────────

    class _InfoPanel(QWidget):

        def __init__(self) -> None:
            super().__init__()
            self.setFixedWidth(300)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(12, 12, 12, 8)
            lay.setSpacing(5)

            def lbl(text, bold=False, color="#CCCCCC", sz=9):
                w = QLabel(text)
                w.setFont(QFont("Segoe UI", sz, QFont.Bold if bold else QFont.Normal))
                w.setStyleSheet(f"color:{color}; background:transparent;")
                w.setWordWrap(True)
                return w

            def div():
                f = QFrame()
                f.setFrameShape(QFrame.HLine)
                f.setStyleSheet("color:#363636;")
                return f

            def txt(h=52, fg="#cccccc"):
                t = QTextEdit()
                t.setReadOnly(True)
                t.setFixedHeight(h)
                t.setStyleSheet(
                    f"background:#212121; color:{fg}; border:1px solid #2A2A2A; "
                    f"font-family:Consolas; font-size:8pt; padding:4px;"
                )
                return t

            lay.addWidget(lbl("DEVICE INFO", bold=True, color="#e94560", sz=11))
            self.w_name  = lbl("No device selected", bold=True, color="white", sz=10)
            self.w_cls   = lbl("", color="#888888")
            self.w_loc   = lbl("", color="#555555", sz=8)
            for w in (self.w_name, self.w_cls, self.w_loc):
                lay.addWidget(w)

            lay.addWidget(div())

            # Health bar
            lay.addWidget(lbl("ARCHITECTURE HEALTH", bold=True, color="#888888", sz=8))
            self.w_hbar = QLabel()
            self.w_hbar.setFixedHeight(5)
            self.w_hbar.setStyleSheet("background:#2A2A2A; border-radius:2px;")
            lay.addWidget(self.w_hbar)
            self.w_hval = lbl("", color="#888888", sz=8)
            lay.addWidget(self.w_hval)

            lay.addWidget(div())

            lay.addWidget(lbl("WARNINGS / ERRORS", bold=True, color="#f1c40f"))
            self.w_warn = txt(50, "#f1c40f")
            lay.addWidget(self.w_warn)

            lay.addWidget(lbl("@editable refs", bold=True, color="#e94560"))
            self.w_edit = txt(52)
            lay.addWidget(self.w_edit)

            lay.addWidget(lbl("Events (.Subscribe)", bold=True, color="#2ecc71"))
            self.w_evt = txt(52)
            lay.addWidget(self.w_evt)

            lay.addWidget(lbl("Functions", bold=True, color="#3498db"))
            self.w_fn = txt(52)
            lay.addWidget(self.w_fn)

            lay.addWidget(div())

            lay.addWidget(lbl("NOTES", bold=True, color="#888888"))
            self.w_note = QTextEdit()
            self.w_note.setFixedHeight(52)
            self.w_note.setStyleSheet(
                "background:#212121; color:#cccccc; border:1px solid #2A2A2A; "
                "font-family:'Segoe UI'; font-size:9pt; padding:4px;"
            )
            lay.addWidget(self.w_note)
            self.w_verse = lbl("", color="#e94560", sz=8)
            lay.addWidget(self.w_verse)
            lay.addStretch()

        def show_node(self, nd: DeviceNode, project_health: int) -> None:
            self.w_name.setText(nd.label)
            self.w_cls.setText(nd.class_name.replace("Device_", "").replace("_C", ""))
            self.w_loc.setText(f"X:{nd.world_loc[0]:.0f}  Y:{nd.world_loc[1]:.0f}  Z:{nd.world_loc[2]:.0f}")

            issues = len(nd.errors) * 2 + len(nd.warnings)
            node_h = max(0, 100 - issues * 15)
            hcol   = "#27ae60" if node_h >= 70 else ("#f1c40f" if node_h >= 40 else "#e74c3c")
            pct    = node_h / 100
            self.w_hbar.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {hcol},stop:{pct:.3f} {hcol},"
                f"stop:{min(pct+0.001,1):.3f} #2A2A2A,stop:1 #2A2A2A);"
                f"border-radius:2px;"
            )
            self.w_hval.setText(f"This device: {node_h}/100  ·  Project: {project_health}/100")

            wlines = [f"W: {w}" for w in nd.warnings] + [f"E: {e}" for e in nd.errors]
            self.w_warn.setPlainText("\n".join(wlines) or "No issues")
            self.w_edit.setPlainText("\n".join(f"{e['name']}: {e['type']}" for e in nd.editables) or "none")
            self.w_evt.setPlainText(
                "\n".join(f"{e['source']}.{e['event']} → {e['handler']}" for e in nd.events) or "none"
            )

            fn_lines: List[str] = []
            lc = nd.called_functions
            for fn in nd.functions:
                tag = "" if fn in lc or fn in ("OnBegin", "OnEnd") else " [UNUSED]"
                fn_lines.append(f"{fn}(){tag}")
            for c in nd.calls:
                fn_lines.append(f"  → {c['target']}.{c['func']}()")
            self.w_fn.setPlainText("\n".join(fn_lines) or "none")

            self.w_note.setPlainText(nd.note)
            self.w_verse.setText(f"Verse: {nd.verse_file}" if nd.verse_file else "No Verse file linked")

        def clear(self) -> None:
            self.w_name.setText("No device selected")
            for w in (self.w_cls, self.w_loc, self.w_hval, self.w_verse):
                w.setText("")
            for w in (self.w_warn, self.w_edit, self.w_evt, self.w_fn, self.w_note):
                w.setPlainText("")

    # ── Main window ───────────────────────────────────────────────────────────

    class _DeviceGraphWindow(ToolbeltWindow):

        def __init__(self, verse_path: str = "") -> None:
            super().__init__(title="UEFN Toolbelt — Verse Device Graph", width=1400, height=860)

            self._verse_path   = verse_path
            self._graph: Optional[GraphData] = None
            self._node_items:  Dict[str, _NodeItem] = {}
            self._edge_items:  List[_EdgeItem]      = []
            self._selected:    Optional[DeviceNode]  = None
            self._health_score = 0

            # Layout animation state
            self._ltimer:  Optional[QTimer] = None
            self._l_step   = 0
            self._l_temp   = 0.0
            self._l_cool   = 0.0
            self._l_k      = 260.0
            self._l_nodes: List[DeviceNode] = []
            self._l_edges: List[GraphEdge]  = []
            self._l_vw = 1200.0
            self._l_vh = 800.0

            self._build_ui()

        # ── UI ────────────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            root = QWidget()
            self.setCentralWidget(root)
            vl = QVBoxLayout(root)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            # Top bar
            bar = QWidget()
            bar.setFixedHeight(46)
            bar.setStyleSheet("background:#111111; border-bottom:1px solid #2A2A2A;")
            bl = QHBoxLayout(bar)
            bl.setContentsMargins(12, 0, 12, 0)
            bl.setSpacing(6)

            title = QLabel("VERSE DEVICE GRAPH")
            title.setFont(QFont("Segoe UI", 12, QFont.Bold))
            title.setStyleSheet("color:#e94560;")   # toolbelt brand red
            bl.addWidget(title)
            bl.addSpacing(8)

            def btn(text, accent=False, cb=None):
                b = QPushButton(text)
                b.setFixedHeight(28)
                if accent:
                    b.setProperty("accent", "true")
                b.setCursor(Qt.PointingHandCursor)
                if cb:
                    b.clicked.connect(cb)
                return b

            bl.addWidget(btn("SCAN", accent=True, cb=self._do_scan))
            bl.addWidget(btn("Re-Layout", cb=self._do_relayout))
            bl.addWidget(btn("Export JSON", cb=self._do_export))
            bl.addSpacing(14)

            lbl_path = QLabel("Verse Path:")
            lbl_path.setStyleSheet("color:#555555;")
            bl.addWidget(lbl_path)

            self._path_edit = QLineEdit(self._verse_path)
            self._path_edit.setFixedHeight(26)
            self._path_edit.setMinimumWidth(220)
            bl.addWidget(self._path_edit)

            browse = btn("…", cb=self._do_browse)
            browse.setFixedWidth(28)
            bl.addWidget(browse)

            bl.addSpacing(12)

            lbl_s = QLabel("Search:")
            lbl_s.setStyleSheet("color:#555555;")
            bl.addWidget(lbl_s)

            self._search = QLineEdit()
            self._search.setFixedHeight(26)
            self._search.setFixedWidth(140)
            self._search.setPlaceholderText("filter nodes…")
            self._search.textChanged.connect(self._on_search)
            bl.addWidget(self._search)
            bl.addStretch()

            self._status = QLabel("Click SCAN to begin")
            self._status.setStyleSheet("color:#555555; font-size:11px;")
            bl.addWidget(self._status)
            vl.addWidget(bar)

            # Health bar (full-width, 4px)
            self._hbar = QLabel()
            self._hbar.setFixedHeight(4)
            self._hbar.setStyleSheet("background:#2A2A2A;")
            vl.addWidget(self._hbar)

            # Canvas + panel
            split = QSplitter(Qt.Horizontal)
            split.setStyleSheet("QSplitter::handle{background:#2A2A2A; width:1px;}")

            self._scene = QGraphicsScene()
            self._view  = _GraphView(self._scene)
            split.addWidget(self._view)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedWidth(314)
            scroll.setStyleSheet("background:#181818; border:none; border-left:1px solid #2A2A2A;")
            self._panel = _InfoPanel()
            self._panel.setStyleSheet("background:#181818;")
            self._panel.w_note.textChanged.connect(self._on_note)
            scroll.setWidget(self._panel)
            split.addWidget(scroll)
            split.setStretchFactor(0, 1)
            split.setStretchFactor(1, 0)
            vl.addWidget(split)

        # ── Actions ───────────────────────────────────────────────────────

        def _do_scan(self) -> None:
            self._status.setText("Scanning…")
            QApplication.processEvents()
            try:
                path        = self._path_edit.text().strip()
                level_devs  = _scan_level()
                verse_files = _find_verse_files(path)
                verse_data  = [v for v in (_VerseParser.parse(vf) for vf in verse_files) if v]
                self._graph = _GraphBuilder.build(level_devs, verse_data)
                self._health_score = self._graph.health_score
                self._rebuild_scene()
                self._start_layout(animate=True)
                self._paint_hbar()
                nd = len(self._graph.nodes)
                ne = len(self._graph.edges)
                nw = sum(len(n.warnings) for n in self._graph.nodes)
                nerr = sum(len(n.errors) for n in self._graph.nodes)
                self._status.setText(
                    f"{nd} devices · {ne} connections · {len(verse_files)} verse files · "
                    f"health {self._health_score}/100 · {self._graph.cluster_count} clusters · "
                    f"{nw}W {nerr}E"
                )
            except Exception as exc:
                self._status.setText(f"Scan error: {exc}")
                log_error(f"verse_graph_open: {exc}")

        def _do_relayout(self) -> None:
            if not self._graph:
                return
            for nd in self._graph.nodes:
                nd.x = nd.y = 0.0
            self._start_layout(animate=True)

        def _do_export(self) -> None:
            if not self._graph:
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Graph JSON", "verse_device_graph.json", "JSON (*.json)"
            )
            if path:
                run_verse_graph_export(verse_path=self._path_edit.text().strip(), output_path=path)
                self._status.setText(f"Exported → {path}")

        def _do_browse(self) -> None:
            path = QFileDialog.getExistingDirectory(self, "Select Verse Project Folder")
            if path:
                self._path_edit.setText(path)

        def _on_search(self, text: str) -> None:
            t = text.strip().lower()
            for nid, item in self._node_items.items():
                item.setVisible(not t or t in item.data.label.lower())

        def _on_note(self) -> None:
            if self._selected:
                self._selected.note = self._panel.w_note.toPlainText().strip()

        def _on_node_clicked(self, nd: DeviceNode) -> None:
            self._selected = nd
            self._panel.show_node(nd, self._health_score)
            if nd.actor:
                try:
                    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                    sub.select_nothing()
                    sub.set_actor_selection_state(nd.actor, True)
                except Exception:
                    pass

        # ── Scene ─────────────────────────────────────────────────────────

        def _rebuild_scene(self) -> None:
            self._scene.clear()
            self._node_items.clear()
            self._edge_items.clear()
            if not self._graph:
                return

            for nd in self._graph.nodes:
                item = _NodeItem(nd)
                item.node_clicked.connect(self._on_node_clicked)
                self._scene.addItem(item)
                self._node_items[nd.id] = item

            for edge in self._graph.edges:
                si = self._node_items.get(edge.source_id)
                ti = self._node_items.get(edge.target_id)
                if si and ti:
                    eitem = _EdgeItem(edge, si, ti)
                    self._scene.addItem(eitem)
                    self._edge_items.append(eitem)

        # ── Force layout (Fruchterman-Reingold, animated) ──────────────────

        def _start_layout(self, animate: bool = True) -> None:
            if self._ltimer:
                self._ltimer.stop()
            if not self._graph or not self._graph.nodes:
                return

            vr = self._view.viewport().rect()
            vw = max(vr.width(),  1200)
            vh = max(vr.height(), 800)

            nodes = self._graph.nodes
            edges = self._graph.edges

            # Seed unplaced nodes with jittered positions
            for nd in nodes:
                if nd.x == 0 and nd.y == 0:
                    nd.x = vw / 2 + random.uniform(-vw * 0.35, vw * 0.35)
                    nd.y = vh / 2 + random.uniform(-vh * 0.35, vh * 0.35)

            TOTAL = 80
            self._l_step  = 0
            self._l_nodes = nodes
            self._l_edges = edges
            self._l_k     = 260.0
            self._l_temp  = min(vw, vh) / 8.0
            self._l_cool  = self._l_temp / (TOTAL + 1)
            self._l_vw    = float(vw)
            self._l_vh    = float(vh)
            self._l_total = TOTAL

            if animate:
                self._ltimer = QTimer(self)
                self._ltimer.setInterval(16)
                self._ltimer.timeout.connect(self._layout_tick)
                self._ltimer.start()
            else:
                for _ in range(TOTAL):
                    self._layout_step()
                self._sync_positions()

        def _layout_tick(self) -> None:
            BATCH = 8
            for _ in range(BATCH):
                if self._l_step >= self._l_total:
                    self._ltimer.stop()
                    return
                self._layout_step()
            self._sync_positions()

        def _layout_step(self) -> None:
            nodes = self._l_nodes
            edges = self._l_edges
            n     = len(nodes)
            k     = self._l_k
            temp  = self._l_temp
            vw    = self._l_vw
            vh    = self._l_vh

            forces: Dict[str, List[float]] = {nd.id: [0.0, 0.0] for nd in nodes}

            # Repulsion between all node pairs
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = nodes[i], nodes[j]
                    dx   = a.x - b.x
                    dy   = a.y - b.y
                    dist = max(math.hypot(dx, dy), 1.0)
                    rep  = (k * k) / dist
                    fx   = (dx / dist) * rep
                    fy   = (dy / dist) * rep
                    forces[a.id][0] += fx;  forces[a.id][1] += fy
                    forces[b.id][0] -= fx;  forces[b.id][1] -= fy

            # Spring attraction along edges
            node_map = {nd.id: nd for nd in nodes}
            for e in edges:
                src = node_map.get(e.source_id)
                tgt = node_map.get(e.target_id)
                if not src or not tgt:
                    continue
                dx   = tgt.x - src.x
                dy   = tgt.y - src.y
                dist = max(math.hypot(dx, dy), 1.0)
                att  = (dist * dist) / k
                fx   = (dx / dist) * att
                fy   = (dy / dist) * att
                forces[src.id][0] += fx;  forces[src.id][1] += fy
                forces[tgt.id][0] -= fx;  forces[tgt.id][1] -= fy

            # Apply with temperature clamping and boundary clamping
            for nd in nodes:
                fx, fy = forces[nd.id]
                speed  = max(math.hypot(fx, fy), 0.001)
                if speed > temp:
                    fx = (fx / speed) * temp
                    fy = (fy / speed) * temp
                nd.x = max(_NODE_W * 0.5,  min(vw - _NODE_W * 1.5,  nd.x + fx))
                nd.y = max(_NODE_H * 0.5,  min(vh - _NODE_H * 1.5,  nd.y + fy))

            self._l_temp -= self._l_cool
            self._l_step += 1

        def _sync_positions(self) -> None:
            for nid, item in self._node_items.items():
                item.setPos(item.data.x, item.data.y)
            self._scene.update()

        def _paint_hbar(self) -> None:
            s = self._health_score
            c = "#44FF88" if s >= 70 else ("#f1c40f" if s >= 40 else "#FF4444")
            p = s / 100
            self._hbar.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {c},stop:{p:.3f} {c},"
                f"stop:{min(p+0.001,1):.3f} #2A2A2A,stop:1 #2A2A2A);"
            )

else:
    # Fallback stub so the module loads cleanly when PySide6 is absent
    class _DeviceGraphWindow(ToolbeltWindow):  # type: ignore[no-redef]
        def __init__(self, *a, **kw): pass
