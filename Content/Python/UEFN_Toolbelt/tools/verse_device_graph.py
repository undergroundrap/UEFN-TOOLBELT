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
        QGraphicsItem, QGraphicsObject, QGraphicsTextItem,
        QInputDialog, QMenu, QComboBox,
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
    folder: str = ""
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
                folder=dev.get("folder", ""),
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
#  Verse wiring code generator
# ─────────────────────────────────────────────────────────────────────────────

def _class_to_verse_type(class_name: str) -> str:
    """Convert a UE class name like 'TimerDevice_V2_C' to Verse type 'timer_device'."""
    import re as _re
    name = class_name
    for strip in ("_V2_C", "_V3_C", "_V4_C", "_C", "BP_", "CRD_",
                  "HidingProp_", "Device_", "Fortnite_"):
        name = name.replace(strip, "")
    # CamelCase → snake_case
    s1 = _re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    result = _re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower().strip("_")
    if result and "device" not in result:
        result += "_device"
    return result or "creative_device"


def _build_wiring_code(graph: "GraphData", has_verse_path: bool = True) -> str:
    """
    Generate a Verse creative_device class stub from the current graph.
    Produces @editable declarations, OnBegin subscriptions, and handler stubs.
    """
    nodes_by_id = {n.id: n for n in graph.nodes}

    # Collect @editable device refs (editable edges)
    editable_decls: List[str] = []
    seen_decls: set = set()
    for edge in graph.edges:
        if edge.edge_type != "editable":
            continue
        tgt = nodes_by_id.get(edge.target_id)
        if not tgt or edge.label in seen_decls:
            continue
        seen_decls.add(edge.label)
        vtype = _class_to_verse_type(tgt.class_name)
        editable_decls.append(f"    @editable {edge.label} : {vtype} = {vtype}{{}}")

    # Also pull @editables declared directly on nodes (from Verse parsing)
    for node in graph.nodes:
        for ed in node.editables:
            if not ed.get("is_device_ref"):
                continue
            name = ed["name"]
            if name in seen_decls:
                continue
            seen_decls.add(name)
            vtype = _class_to_verse_type(ed["type"])
            editable_decls.append(f"    @editable {name} : {vtype} = {vtype}{{}}")

    # Collect subscriptions (event edges)
    subscriptions: List[str] = []
    handlers: List[str] = []
    seen_subs: set = set()
    for edge in graph.edges:
        if edge.edge_type != "event":
            continue
        src = nodes_by_id.get(edge.source_id)
        if not src:
            continue
        # Find the @editable ref name for this source device
        ref_name = None
        for ed in nodes_by_id.get(edge.target_id, DeviceNode(
                "", "", "", "", "", (0,0,0), None)).editables:
            pass  # unused path
        # Use label with spaces removed as ref name
        ref_name = src.label.replace(" ", "").replace("-", "")
        handler_name = f"On{edge.label}"
        sub_key = f"{ref_name}.{edge.label}"
        if sub_key in seen_subs:
            continue
        seen_subs.add(sub_key)
        subscriptions.append(f"        {ref_name}.{edge.label}.Subscribe({handler_name})")
        handlers.append(
            f"    {handler_name}(Agent : ?agent) : void =\n"
            f"        # TODO: handle {edge.label} from {src.label}\n"
        )

    # Also pull subscriptions declared directly on nodes
    for node in graph.nodes:
        for ev in node.events:
            ref = ev.get("source", "")
            evt = ev.get("event", "")
            handler = ev.get("handler", f"On{evt}")
            sub_key = f"{ref}.{evt}"
            if sub_key in seen_subs:
                continue
            seen_subs.add(sub_key)
            subscriptions.append(f"        {ref}.{evt}.Subscribe({handler})")
            handlers.append(
                f"    {handler}(Agent : ?agent) : void =\n"
                f"        # TODO: handle {evt} from {ref}\n"
            )

    # Assemble
    lines: List[str] = [
        "# ─────────────────────────────────────────────────────────────────",
        "# Generated by UEFN Toolbelt — Verse Device Graph",
        f"# Devices: {len(graph.nodes)}  ·  Connections: {len(graph.edges)}",
        f"# Architecture Health: {graph.health_score}/100",
        "# ─────────────────────────────────────────────────────────────────",
        "",
        "using { /Fortnite.com/Devices }",
        "using { /Verse.org/Simulation }",
        "using { /UnrealEngine.com/Temporary/Diagnostics }",
        "",
        "GameManager := class(creative_device):",
        "",
    ]

    if editable_decls:
        lines.append("    # ── Device References ────────────────────────────────")
        lines.extend(editable_decls)
        lines.append("")

    if subscriptions:
        lines.append("    OnBegin<override>()<suspends> : void =")
        lines.extend(subscriptions)
        lines.append("")

    if handlers:
        lines.append("    # ── Event Handlers ───────────────────────────────────")
        lines.extend(handlers)

    if not editable_decls and not subscriptions:
        if not has_verse_path:
            lines += [
                "    # No Verse path set.",
                "    # Enter your project's Verse folder in the Path field and click SCAN.",
                "",
                "    OnBegin<override>()<suspends> : void =",
                "        Print(\"GameManager started\")",
            ]
        else:
            lines += [
                "    # No device connections found.",
                "    # Make sure your Verse files contain @editable device references,",
                "    # then click SCAN again.",
                "",
                "    OnBegin<override>()<suspends> : void =",
                "        Print(\"GameManager started\")",
            ]

    return "\n".join(lines)


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
                try:
                    folder = str(actor.get_folder_path())
                except Exception:
                    folder = ""
                result.append({
                    "label":  label or cn,
                    "class":  cn,
                    "loc":    (loc.x, loc.y, loc.z),
                    "actor":  actor,
                    "folder": folder,
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
#  Node tooltip builder
# ─────────────────────────────────────────────────────────────────────────────

def _make_node_tooltip(nd: DeviceNode) -> str:
    """Rich tooltip explaining every badge visible on the node."""
    lines = [f"{nd.label}", f"Class: {nd.class_name}", f"Category: {nd.category}"]

    if nd.world_loc != (0.0, 0.0, 0.0):
        lines.append(f"Location: X={nd.world_loc[0]:.0f}  Y={nd.world_loc[1]:.0f}  Z={nd.world_loc[2]:.0f}")

    lines.append("")

    # Cluster badge (top-left number)
    if nd.cluster_id >= 0:
        lines.append(f"#{nd.cluster_id}  Cluster ID — all devices sharing this number are")
        lines.append(f"     connected into the same logic group (Union-Find).")

    # Verse badge
    if nd.verse_file:
        lines.append(f"VS  Verse file matched: {nd.verse_file}")
    else:
        lines.append("     No Verse file linked to this device.")

    # Warning / error badges (top-right !)
    if nd.errors:
        lines.append("")
        lines.append("🔴  ERRORS (red !):")
        for e in nd.errors:
            lines.append(f"     • {e}")
    if nd.warnings:
        lines.append("")
        lines.append("⚠   WARNINGS (yellow !):")
        for w in nd.warnings:
            lines.append(f"     • {w}")

    if not nd.errors and not nd.warnings:
        lines.append("     No issues detected.")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  PySide6 UI
# ─────────────────────────────────────────────────────────────────────────────

if _PYSIDE6:

    # ── Palette — derived from core/theme.PALETTE (single source of truth) ───
    # To change colors platform-wide, edit core/theme.py — not here.

    _P = {k: QColor(v) for k, v in _PALETTE.items()}

    # ── NodeItem ──────────────────────────────────────────────────────────────

    class _NodeItem(QGraphicsObject):
        node_clicked   = Signal(object)
        node_hovered   = Signal(object)   # emits DeviceNode on enter
        node_unhovered = Signal()         # emits on leave

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
            self.node_hovered.emit(self.data)

        def hoverLeaveEvent(self, e):
            self._hovered = False
            self.update()
            self.node_unhovered.emit()

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
            accent = _P["accent"]
            if sel:
                # Large bright accent glow when selected
                glow = QRadialGradient(w / 2, h / 2, w * 1.1)
                gc = QColor(accent); gc.setAlpha(110)
                ge = QColor(accent); ge.setAlpha(0)
                glow.setColorAt(0, gc)
                glow.setColorAt(1, ge)
                p.setBrush(QBrush(glow))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(-20, -20, w + 40, h + 40, r + 20, r + 20)
            elif self._hovered:
                gc = QColor(col); gc.setAlpha(28)
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

            # Body gradient — slightly brighter when selected
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, QColor("#2E2E2E") if sel else QColor("#242424"))
            grad.setColorAt(1, QColor("#1E1E1E") if sel else QColor("#1A1A1A"))
            p.setBrush(QBrush(grad))
            if sel:
                outline = accent
                pen_w   = 2.5
            elif self._hovered:
                outline = QColor("#FFFFFF")
                pen_w   = 1.0
            else:
                outline = QColor("#363636")
                pen_w   = 1.0
            p.setPen(QPen(outline, pen_w))
            p.drawRoundedRect(0, 0, w, h, r, r)

            # Extra inner accent ring when selected
            if sel:
                inner = QColor(accent); inner.setAlpha(60)
                p.setPen(QPen(inner, 1.0))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(3, 3, w - 6, h - 6, r - 1, r - 1)

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

    # ── Comment box (Blueprint-style annotation) ──────────────────────────────

    class _CommentBox(QGraphicsObject):
        """Draggable, resizable, editable note box — Blueprint-style annotation."""
        deleted = Signal(object)

        _COLORS = [
            ("#FFD54F", "Yellow"),
            ("#EF9A9A", "Red"),
            ("#A5D6A7", "Green"),
            ("#90CAF9", "Blue"),
            ("#CE93D8", "Purple"),
            ("#80DEEA", "Cyan"),
            ("#FFCC80", "Orange"),
        ]
        _HANDLE = 14

        _HDR_H = 28   # header bar height

        def __init__(self, x: float = 0, y: float = 0,
                     w: float = 300, h: float = 160,
                     title: str = "Note", body: str = "",
                     color: str = "#FFD54F") -> None:
            super().__init__()
            self._w     = float(w)
            self._h     = float(h)
            self._title = title
            self._body  = body
            self._color = color
            self._resizing      = False
            self._resize_start  = None
            self._resize_orig   = None
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            self.setAcceptHoverEvents(True)
            self.setZValue(-2)
            self.setPos(x, y)

        def boundingRect(self) -> QRectF:
            return QRectF(-2, -2, self._w + 4, self._h + 4)

        def paint(self, p: QPainter, *_) -> None:
            p.setRenderHint(QPainter.Antialiasing)
            col = QColor(self._color)
            hdr = self._HDR_H

            # Semi-transparent background
            fill = QColor(col); fill.setAlpha(22)
            p.setBrush(QBrush(fill))
            border = QColor(col); border.setAlpha(140)
            p.setPen(QPen(border, 1.5))
            p.drawRoundedRect(0, 0, self._w, self._h, 7, 7)

            # Header bar
            hdr_fill = QColor(col); hdr_fill.setAlpha(65)
            p.setBrush(QBrush(hdr_fill))
            p.setPen(Qt.NoPen)
            path = QPainterPath()
            path.addRoundedRect(0, 0, self._w, hdr, 7, 7)
            path.addRect(0, hdr // 2, self._w, hdr // 2)
            p.drawPath(path)

            # Title
            p.setPen(QPen(QColor("#FFFFFF")))
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            p.drawText(QRectF(8, 4, self._w - 16, hdr - 4),
                       Qt.AlignVCenter | Qt.AlignLeft, self._title)

            # Body text (hint if empty)
            body_rect = QRectF(8, hdr + 6, self._w - 16, self._h - hdr - 20)
            if self._body:
                p.setPen(QPen(QColor("#DDDDDD")))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(body_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                           self._body)
            else:
                p.setPen(QPen(QColor("#555555")))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(body_rect, Qt.AlignLeft | Qt.AlignTop,
                           "double-click to add notes…")

            # Resize handle (bottom-right)
            rh = self._HANDLE
            hc = QColor(col); hc.setAlpha(110)
            p.setBrush(QBrush(hc))
            p.setPen(Qt.NoPen)
            p.drawRect(self._w - rh, self._h - rh, rh, rh)
            line_c = QColor(col).darker(160)
            p.setPen(QPen(line_c, 1.0))
            for i in range(3):
                off = 3 + i * 3
                p.drawLine(int(self._w - rh + off), int(self._h),
                           int(self._w),            int(self._h - rh + off))

        def _in_resize(self, pos: QPointF) -> bool:
            rh = self._HANDLE
            return (self._w - rh <= pos.x() <= self._w + 2 and
                    self._h - rh <= pos.y() <= self._h + 2)

        def _in_header(self, pos: QPointF) -> bool:
            return pos.y() <= self._HDR_H

        def mousePressEvent(self, e) -> None:
            if e.button() == Qt.LeftButton and self._in_resize(e.pos()):
                self._resizing     = True
                self._resize_start = e.scenePos()
                self._resize_orig  = (self._w, self._h)
                e.accept()
            else:
                super().mousePressEvent(e)

        def mouseMoveEvent(self, e) -> None:
            if self._resizing and self._resize_start is not None:
                d  = e.scenePos() - self._resize_start
                nw = max(180.0, self._resize_orig[0] + d.x())
                nh = max(90.0,  self._resize_orig[1] + d.y())
                self.prepareGeometryChange()
                self._w = nw
                self._h = nh
                self.update()
                e.accept()
            else:
                super().mouseMoveEvent(e)

        def mouseReleaseEvent(self, e) -> None:
            self._resizing = False
            super().mouseReleaseEvent(e)

        def mouseDoubleClickEvent(self, e) -> None:
            # Open the themed edit dialog for both title and body
            self._edit_dlg = _NoteEditDialog(self)
            self._edit_dlg.show_in_uefn()

        def contextMenuEvent(self, e) -> None:
            menu = QMenu()
            color_acts = []
            for hex_col, name in self._COLORS:
                act = menu.addAction(name)
                act.setData(hex_col)
                color_acts.append(act)
            menu.addSeparator()
            del_act = menu.addAction("Delete Note")
            chosen = menu.exec(e.screenPos())
            if chosen is del_act:
                self.deleted.emit(self)
            elif chosen and chosen in color_acts:
                self._color = chosen.data()
                self.update()

        def to_dict(self) -> dict:
            return {
                "x": self.x(), "y": self.y(),
                "w": self._w,  "h": self._h,
                "title": self._title, "body": self._body,
                "color": self._color,
            }

    # ── Help dialog ───────────────────────────────────────────────────────────

    class _HelpDialog(ToolbeltWindow):
        """Purpose, workflow, badge guide, and attribution for the Device Graph."""

        _CONTENT = """\
WHAT IS THIS?

The Verse Device Graph gives you a bird's-eye view of your entire UEFN level
architecture in one window. Every Creative/Verse device becomes a node. Every
@editable reference and .Subscribe() call becomes an edge. The result is a map
of how your island's logic actually flows — something the UEFN Properties panel
can never show you because it only looks at one device at a time.

─────────────────────────────────────────────────────────────────────────

WHY IT WAS MADE

UEFN levels with many devices become impossible to reason about without a map.
Once you pass ~30 devices connected through Verse, losing track of what talks to
what is inevitable. This graph was built to surface that architecture instantly:
who connects to whom, which devices are orphaned, where your Verse code reaches,
and whether the overall structure is healthy or broken.

Inspired by ImmatureGamer's uefn-device-graph (tkinter prototype).
This is an independent PySide6 rewrite — force-directed layout, health scoring,
cluster detection, live sync, write-back, and layout persistence — integrated
into the full Toolbelt stack.

─────────────────────────────────────────────────────────────────────────

TYPICAL WORKFLOW

  1. Set your Verse folder in the Path field (once — it's saved to config)
  2. Click SCAN — level actors + .verse files are parsed in one pass
  3. Read the Architecture Health score (0–100) in the top bar
       ≥ 70  — healthy, well-connected  (green)
       40–69 — some orphans or broken refs  (yellow)
       < 40  — significant issues  (red)
  4. Hover a node to dim everything it doesn't connect to
  5. Click a node to inspect its @editable refs, events, and functions
  6. Use the @ed / .sub / .call toggles to focus on one edge type at a time
  7. Use the Category dropdown to isolate a single device family (e.g. Timer,
     Capture Area, Score Manager) — great for large levels with 100+ devices
  8. Click Gen Wiring to generate a Verse creative_device stub from the graph
  9. Add + Note boxes to annotate sections for yourself or teammates
  10. Close the window — your layout and notes are saved automatically
 11. Reopen anytime — positions and notes restore on the next SCAN

─────────────────────────────────────────────────────────────────────────

NODE BADGES

  #N  (top-left, colored circle)
      Cluster ID — all nodes sharing this number are connected into the same
      logic group (Union-Find across all edges). A level with 197 devices and
      180 clusters means most devices are isolated — no Verse wiring links them.

  !   (top-right, RED)
      Error — a @editable device reference type couldn't be matched to any
      placed device in the level. The Verse stub will have a dangling ref.

  !   (top-right, YELLOW)
      Warning — one or more issues found:
        • Orphan: no @editable or .Subscribe connections to other devices
        • Unused function: defined but never called from within the device

  VS  (footer, bottom-left)
      Verse file linked — this device was matched to a .verse class by label.
      Its @editable refs and .Subscribe calls have been parsed and drawn as edges.

─────────────────────────────────────────────────────────────────────────

EDGE TYPES

  ─────  Red  (@ed)    @editable device reference declared in a Verse class
  - - -  Green (.sub)  .Subscribe() event subscription wired in OnBegin
         Blue  (.call) Direct method call on a device ref

  Toggle any edge type on/off with the @ed / .sub / .call buttons in the toolbar.

─────────────────────────────────────────────────────────────────────────

TIPS

  • The minimap (bottom-right corner of the canvas) shows every device as a
    colored dot (matching its category color). Click or drag on it to jump to
    any area instantly. The blue outline shows what's visible in the canvas.

  • Focus button: select any node then click Focus to instantly centre and zoom
    the canvas on it — useful when searching brings up a result buried deep in
    a large graph.

  • The Category dropdown filters the graph to one device family at a time.
    Search and Category stack — you can filter to "Timer" devices and then
    search within them. Select "All Categories" to reset.

  • Re-Layout runs force-directed physics (Fruchterman-Reingold). Nodes pull
    toward connected partners and repel unrelated ones. Run it after SCAN to
    see a topology-driven layout instead of the default category columns.

  • Live mode (● Live) polls for level changes every 4 seconds and refreshes
    the graph without moving nodes you've already positioned.

  • Write-back: select a node and use the Label / Folder fields in the side
    panel to rename actors and move them to World Outliner folders directly
    from the graph — no need to find them in the viewport.

  • The Gen Wiring dialog produces a ready-to-compile Verse stub with
    @editable declarations and OnBegin subscriptions generated from your graph.
    Click "Write to Verse File" to deploy it straight into your project.

  • Your layout (node positions + note boxes) is saved to
    Saved/UEFN_Toolbelt/graph_layout.json when you close the window.
"""

        def __init__(self) -> None:
            super().__init__(title="UEFN Toolbelt — Verse Device Graph Help",
                             width=700, height=720)
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

    # ── Note edit dialog (themed) ─────────────────────────────────────────────

    class _NoteEditDialog(ToolbeltWindow):
        """Fully-themed editor for a comment box's title + body text."""

        def __init__(self, box: "_CommentBox") -> None:
            super().__init__(title="UEFN Toolbelt — Edit Note", width=440, height=320)
            self._box = box
            self._build_ui()

        def _build_ui(self) -> None:
            root = QWidget()
            self.setCentralWidget(root)
            vl = QVBoxLayout(root)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            bar, bl = self.make_topbar("EDIT NOTE")
            bl.addWidget(self.make_btn("Save", accent=True, cb=self._save))
            bl.addWidget(self.make_btn("Cancel", cb=self.close))
            bl.addStretch()
            vl.addWidget(bar)

            body = QWidget()
            body.setStyleSheet(f"background:{self.hex('panel')};")
            fl = QVBoxLayout(body)
            fl.setContentsMargins(16, 14, 16, 14)
            fl.setSpacing(8)

            def _lbl(text):
                w = QLabel(text)
                w.setStyleSheet(
                    f"color:{self.hex('muted')}; font-size:9pt; background:transparent;")
                return w

            _input_qss = (
                f"background:#212121; color:{self.hex('text')}; "
                f"border:1px solid #363636; border-radius:3px; "
                f"padding:3px 8px; font-family:'Segoe UI'; font-size:10pt;"
            )

            fl.addWidget(_lbl("Title"))
            self._title_edit = QLineEdit(self._box._title)
            self._title_edit.setFixedHeight(28)
            self._title_edit.setStyleSheet(_input_qss)
            fl.addWidget(self._title_edit)

            fl.addWidget(_lbl("Notes"))
            self._body_edit = QTextEdit()
            self._body_edit.setPlainText(self._box._body)
            self._body_edit.setStyleSheet(_input_qss)
            fl.addWidget(self._body_edit)

            vl.addWidget(body)

        def _save(self) -> None:
            self._box._title = self._title_edit.text().strip() or "Note"
            self._box._body  = self._body_edit.toPlainText()
            self._box.update()
            self.close()

    # ── Activity log overlay ───────────────────────────────────────────────────

    class _ActivityLog(QWidget):
        """
        Semi-transparent bottom-left overlay showing the last N activity entries.
        Pinned to the viewport like the minimap — survives ScrollHandDrag.
        """

        _W, _H    = 300, 148
        _MAX      = 8
        _PAD      = 8
        _ROW_H    = 16
        _LEVEL_COLORS = {
            "info":  "#AAAAAA",
            "ok":    "#2ecc71",
            "warn":  "#e67e22",
            "error": "#e94560",
            "live":  "#3498db",
            "scan":  "#9b59b6",
        }

        def __init__(self, main_view: "QGraphicsView") -> None:
            super().__init__(main_view)
            self._entries: list = []   # [(time_str, msg, level), ...]
            self.setFixedSize(self._W, self._H)
            self.setStyleSheet(
                "background: transparent;"
            )
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        def push(self, msg: str, level: str = "info") -> None:
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            self._entries.append((ts, msg, level))
            if len(self._entries) > self._MAX:
                self._entries.pop(0)
            self.update()

        def paintEvent(self, event) -> None:
            if not self._entries:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, False)

            # Background panel
            p.setBrush(QBrush(QColor(14, 14, 14, 210)))
            p.setPen(QPen(QColor("#2A2A2A"), 1))
            p.drawRoundedRect(0, 0, self._W - 1, self._H - 1, 4, 4)

            # Header
            p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            p.setPen(QColor("#555555"))
            p.drawText(self._PAD, self._PAD + 9, "ACTIVITY")

            # Entries — most recent at bottom, older ones dimmer
            n = len(self._entries)
            y = self._PAD + 22
            p.setFont(QFont("Consolas", 8))
            for i, (ts, msg, level) in enumerate(self._entries):
                # Opacity: oldest = 35%, newest = 100%
                alpha = int(90 + (165 * i / max(n - 1, 1)))
                color = QColor(self._LEVEL_COLORS.get(level, "#AAAAAA"))
                color.setAlpha(alpha)
                ts_color = QColor("#444444")
                ts_color.setAlpha(alpha)

                p.setPen(ts_color)
                p.drawText(self._PAD, y, ts)
                p.setPen(color)
                # Truncate long messages to fit
                metrics = p.fontMetrics()
                available = self._W - self._PAD * 2 - 58
                elided = metrics.elidedText(msg, Qt.ElideRight, available)
                p.drawText(self._PAD + 58, y, elided)
                y += self._ROW_H

            p.end()

    # ── Canvas view ───────────────────────────────────────────────────────────

    class _MiniMap(QWidget):
        """
        Minimap overlay: draws node dots by category color + viewport outline.
        Uses the real scene bounding rect for accurate coordinate mapping.
        Delta-based dragging avoids jump-on-click jank.
        """

        _W, _H = 200, 130
        _PAD   = 6

        def __init__(self, scene: "QGraphicsScene", main_view: "QGraphicsView",
                     node_items_fn: "callable") -> None:
            super().__init__(main_view)
            self._scene      = scene
            self._main       = main_view
            self._node_items = node_items_fn   # callable → current _node_items dict
            self._scene_rect = None            # cached QRectF, set by fit_scene()
            self._drag_scene_center = None     # scene center at drag start

            self.setFixedSize(self._W, self._H)
            self.setStyleSheet(
                "background:#111; border:1px solid #2E2E2E; border-radius:4px;"
            )
            self.setCursor(Qt.PointingHandCursor)

            main_view.horizontalScrollBar().valueChanged.connect(self.update)
            main_view.verticalScrollBar().valueChanged.connect(self.update)
            main_view.horizontalScrollBar().rangeChanged.connect(self.update)
            main_view.verticalScrollBar().rangeChanged.connect(self.update)

        def fit_scene(self) -> None:
            """Use the real scene bounding rect for accurate mapping."""
            r = self._scene.itemsBoundingRect()
            if r.isValid():
                self._scene_rect = r.adjusted(-40, -40, 40, 40)
            else:
                self._scene_rect = None
            self.update()

        # ── coordinate helpers ──────────────────────────────────────────────

        def _s2m(self, sx: float, sy: float):
            """Scene point → minimap pixel."""
            r = self._scene_rect
            if not r or r.width() == 0 or r.height() == 0:
                return 0, 0
            pw = self._W - self._PAD * 2
            ph = self._H - self._PAD * 2
            return (
                self._PAD + (sx - r.x()) / r.width()  * pw,
                self._PAD + (sy - r.y()) / r.height() * ph,
            )

        def _m2s(self, px: float, py: float):
            """Minimap pixel → scene point."""
            r = self._scene_rect
            if not r:
                return 0.0, 0.0
            pw = self._W - self._PAD * 2
            ph = self._H - self._PAD * 2
            return (
                r.x() + (px - self._PAD) / pw * r.width(),
                r.y() + (py - self._PAD) / ph * r.height(),
            )

        # ── paint ───────────────────────────────────────────────────────────

        def paintEvent(self, event) -> None:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, False)
            p.fillRect(self.rect(), QColor("#111111"))

            if not self._scene_rect:
                p.setPen(QColor("#444"))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(self.rect(), Qt.AlignCenter, "Scan to populate")
                p.end()
                return

            # Node dots
            p.setPen(Qt.NoPen)
            for item in self._node_items().values():
                if not item.isVisible():
                    continue
                color = item.data.color if hasattr(item.data, "color") else "#5d6d7e"
                mx, my = self._s2m(item.pos().x(), item.pos().y())
                p.setBrush(QColor(color))
                p.drawRect(int(mx), int(my), 3, 3)

            # Viewport rect
            vp = self._main.mapToScene(self._main.viewport().rect()).boundingRect()
            x1, y1 = self._s2m(vp.x(), vp.y())
            x2, y2 = self._s2m(vp.right(), vp.bottom())
            rw = max(4, int(x2 - x1))
            rh = max(4, int(y2 - y1))
            rx = int(max(self._PAD, min(x1, self._W - self._PAD - rw)))
            ry = int(max(self._PAD, min(y1, self._H - self._PAD - rh)))
            p.setPen(QPen(QColor("#4A90D9"), 1.2))
            p.setBrush(QBrush(QColor(74, 144, 217, 18)))
            p.drawRect(rx, ry, rw, rh)

            # Outer border
            p.setPen(QPen(QColor("#2E2E2E"), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(0, 0, self._W - 1, self._H - 1, 4, 4)
            p.end()

        # ── interaction ─────────────────────────────────────────────────────

        def mousePressEvent(self, e) -> None:
            if not self._scene_rect:
                return
            # Jump to clicked position immediately
            sx, sy = self._m2s(float(e.pos().x()), float(e.pos().y()))
            from PySide6.QtCore import QPointF
            self._main.centerOn(QPointF(sx, sy))
            # Record start state for delta drag
            self._drag_scene_center = self._main.mapToScene(
                self._main.viewport().rect().center()
            )
            self._drag_mm_start = (float(e.pos().x()), float(e.pos().y()))
            self.update()

        def mouseMoveEvent(self, e) -> None:
            if not (e.buttons() and self._drag_scene_center
                    and self._drag_mm_start and self._scene_rect):
                return
            dx_mm = float(e.pos().x()) - self._drag_mm_start[0]
            dy_mm = float(e.pos().y()) - self._drag_mm_start[1]
            pw = self._W - self._PAD * 2
            ph = self._H - self._PAD * 2
            if pw <= 0 or ph <= 0:
                return
            dx_s = dx_mm / pw * self._scene_rect.width()
            dy_s = dy_mm / ph * self._scene_rect.height()
            from PySide6.QtCore import QPointF
            self._main.centerOn(QPointF(
                self._drag_scene_center.x() + dx_s,
                self._drag_scene_center.y() + dy_s,
            ))
            self.update()

        def mouseReleaseEvent(self, e) -> None:
            self._drag_scene_center = None
            self._drag_mm_start = None

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
            self._minimap: Optional["_MiniMap"] = None
            self._actlog:  Optional["_ActivityLog"] = None

        def set_minimap(self, mm: "_MiniMap") -> None:
            self._minimap = mm
            mm.setParent(self.viewport())
            mm.show()
            mm.raise_()
            self._position_minimap()

        def set_actlog(self, al: "_ActivityLog") -> None:
            self._actlog = al
            al.setParent(self.viewport())
            al.show()
            al.raise_()
            self._position_actlog()

        def resizeEvent(self, e) -> None:
            super().resizeEvent(e)
            self._position_minimap()
            self._position_actlog()

        def _position_minimap(self) -> None:
            if not self._minimap:
                return
            vp = self.viewport()
            margin = 10
            self._minimap.move(
                vp.width()  - self._minimap.width()  - margin,
                vp.height() - self._minimap.height() - margin,
            )
            self._minimap.show()
            self._minimap.raise_()

        def _position_actlog(self) -> None:
            if not self._actlog:
                return
            margin = 10
            self._actlog.move(
                margin,
                self.viewport().height() - self._actlog.height() - margin,
            )
            self._actlog.show()
            self._actlog.raise_()

        def scrollContentsBy(self, dx: int, dy: int) -> None:
            super().scrollContentsBy(dx, dy)
            self._position_minimap()
            self._position_actlog()

        def wheelEvent(self, e):
            factor = 1.12 if e.angleDelta().y() > 0 else 0.89
            new_scale = self.transform().m11() * factor
            if 0.15 < new_scale < 3.5:
                self.scale(factor, factor)
            if self._minimap:
                self._minimap.update()

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
        prop_apply = Signal(str, object)   # (prop_name, value)

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

            lay.addWidget(div())

            lay.addWidget(lbl("PROPERTIES", bold=True, color="#888888", sz=8))

            row_label = QHBoxLayout()
            row_label.setSpacing(4)
            row_label.addWidget(lbl("Label:", sz=8))
            self.w_prop_label = QLineEdit()
            self.w_prop_label.setFixedHeight(24)
            self.w_prop_label.setStyleSheet(
                "background:#212121; color:#CCCCCC; border:1px solid #363636; "
                "border-radius:3px; padding:2px 6px; font-size:9pt;"
            )
            self.w_prop_label.setEnabled(False)
            row_label.addWidget(self.w_prop_label)
            lay.addLayout(row_label)

            row_folder = QHBoxLayout()
            row_folder.setSpacing(4)
            row_folder.addWidget(lbl("Folder:", sz=8))
            self.w_prop_folder = QLineEdit()
            self.w_prop_folder.setFixedHeight(24)
            self.w_prop_folder.setStyleSheet(
                "background:#212121; color:#CCCCCC; border:1px solid #363636; "
                "border-radius:3px; padding:2px 6px; font-size:9pt;"
            )
            self.w_prop_folder.setEnabled(False)
            row_folder.addWidget(self.w_prop_folder)
            lay.addLayout(row_folder)

            self.w_apply = QPushButton("Apply Changes")
            self.w_apply.setFixedHeight(26)
            self.w_apply.setEnabled(False)
            self.w_apply.setStyleSheet(
                "background:#1A1A55; border:1px solid #3A3AFF; color:#8888FF; "
                "border-radius:3px; font-size:9pt; text-align:center;"
            )
            self.w_apply.clicked.connect(self._emit_apply)
            lay.addWidget(self.w_apply)

            self.w_prop_status = lbl("", color="#555555", sz=8)
            lay.addWidget(self.w_prop_status)

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

            # Properties — only editable if actor is live in level
            has_actor = nd.actor is not None
            self.w_prop_label.setText(nd.label)
            self.w_prop_folder.setText(nd.folder)
            self.w_prop_label.setEnabled(has_actor)
            self.w_prop_folder.setEnabled(has_actor)
            self.w_apply.setEnabled(has_actor)
            self.w_prop_status.setText("" if has_actor else "Verse-only device — no live actor")

        def _emit_apply(self) -> None:
            self.prop_apply.emit("label",  self.w_prop_label.text().strip())
            self.prop_apply.emit("folder", self.w_prop_folder.text().strip())

        def clear(self) -> None:
            self.w_name.setText("No device selected")
            for w in (self.w_cls, self.w_loc, self.w_hval, self.w_verse, self.w_prop_status):
                w.setText("")
            for w in (self.w_warn, self.w_edit, self.w_evt, self.w_fn, self.w_note):
                w.setPlainText("")
            for w in (self.w_prop_label, self.w_prop_folder):
                w.setText("")
                w.setEnabled(False)
            self.w_apply.setEnabled(False)

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
            self._comment_items:    List[_CommentBox]       = []
            self._cat_header_items: List[QGraphicsTextItem] = []
            self._hover_active   = False
            self._layout_loaded  = False   # True after first successful layout restore

            # Live sync state
            self._live_sync   = False
            self._live_timer: Optional[QTimer] = None
            self._actor_fingerprint = ""

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

            # Viewport → graph selection sync (polls every 800ms, always on)
            self._sel_timer = QTimer(self)
            self._sel_timer.setInterval(500)
            self._sel_timer.timeout.connect(self._check_viewport_selection)
            self._sel_timer.start()

        # ── UI ────────────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            root = QWidget()
            self.setCentralWidget(root)
            vl = QVBoxLayout(root)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            # Toolbar — window title already identifies the tool, no label needed
            bar = QWidget()
            bar.setFixedHeight(46)
            bar.setStyleSheet(
                f"background:{self.hex('topbar')};"
                f"border-bottom:1px solid {self.hex('border2')};"
            )
            bl = QHBoxLayout(bar)
            bl.setContentsMargins(12, 0, 12, 0)
            bl.setSpacing(6)

            def _btn(text, accent=False, cb=None, w=0):
                b = QPushButton(text)
                b.setFixedHeight(28)
                if w: b.setFixedWidth(w)
                if accent: b.setProperty("accent", "true")
                b.setCursor(Qt.PointingHandCursor)
                if cb: b.clicked.connect(cb)
                return b

            bl.addWidget(_btn("SCAN", accent=True, cb=self._do_scan))
            bl.addWidget(_btn("Fit", cb=self._do_fit_view, w=40))
            bl.addWidget(_btn("Focus", cb=self._do_focus_selection, w=52))
            bl.addWidget(_btn("Re-Layout", cb=self._do_relayout))
            bl.addWidget(_btn("Export JSON", cb=self._do_export))
            bl.addWidget(_btn("Gen Wiring", cb=self._do_generate_wiring))
            bl.addWidget(_btn("+ Note", cb=self._add_comment))
            bl.addWidget(_btn("?", cb=self._do_help, w=28))

            # Edge type toggle buttons
            bl.addSpacing(8)

            def _edge_btn(label, color, edge_type):
                b = QPushButton(label)
                b.setFixedHeight(22)
                b.setFixedWidth(46)
                b.setCheckable(True)
                b.setChecked(True)
                b.setCursor(Qt.PointingHandCursor)
                b.setToolTip(f"Show/hide {edge_type} edges")
                b.setStyleSheet(
                    f"QPushButton{{background:#1A1A1A; color:{color}; border:1px solid {color};"
                    f"border-radius:3px; font-size:8pt; font-weight:600;}}"
                    f"QPushButton:checked{{background:{color}22; color:{color};}}"
                    f"QPushButton:!checked{{background:#111; color:#444; border-color:#333;}}"
                )
                b.toggled.connect(self._on_edge_toggle)
                return b

            self._btn_editable = _edge_btn("@ed",  "#e94560", "editable")
            self._btn_events   = _edge_btn(".sub",  "#2ecc71", "event")
            self._btn_calls    = _edge_btn(".call", "#3498db", "call")
            for b in (self._btn_editable, self._btn_events, self._btn_calls):
                bl.addWidget(b)

            self._live_btn = _btn("● Live", cb=self._toggle_live)
            self._live_btn.setToolTip("Auto-refresh graph when level changes (polls every 4s)")
            bl.addWidget(self._live_btn)
            bl.addSpacing(16)

            lbl_path = QLabel("Path:")
            lbl_path.setStyleSheet(f"color:{self.hex('muted')};")
            bl.addWidget(lbl_path)

            self._path_edit = QLineEdit(self._verse_path)
            self._path_edit.setFixedHeight(26)
            self._path_edit.setMinimumWidth(260)
            self._path_edit.setPlaceholderText("Verse project path — required for wiring scan")
            bl.addWidget(self._path_edit)

            bl.addWidget(_btn("…", cb=self._do_browse))

            bl.addSpacing(16)

            lbl_s = QLabel("Search:")
            lbl_s.setStyleSheet(f"color:{self.hex('muted')};")
            bl.addWidget(lbl_s)

            self._search = QLineEdit()
            self._search.setFixedHeight(26)
            self._search.setFixedWidth(160)
            self._search.setPlaceholderText("filter nodes…")
            self._search.textChanged.connect(self._on_search)
            bl.addWidget(self._search)

            bl.addSpacing(8)
            lbl_cat = QLabel("Category:")
            lbl_cat.setStyleSheet(f"color:{self.hex('muted')};")
            bl.addWidget(lbl_cat)

            self._cat_combo = QComboBox()
            self._cat_combo.setFixedHeight(26)
            self._cat_combo.setMinimumWidth(160)
            self._cat_combo.setToolTip("Show only nodes in this device category")
            self._cat_combo.setStyleSheet(
                "QComboBox{background:#1A1A1A; color:#E0E0E0; border:1px solid #3A3A3A;"
                "border-radius:3px; padding:2px 6px;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox QAbstractItemView{background:#1A1A1A; color:#E0E0E0;"
                "selection-background-color:#2A2A2A;}"
            )
            self._cat_combo.addItem("All Categories")
            self._cat_combo.currentTextChanged.connect(self._on_category_filter)
            bl.addWidget(self._cat_combo)
            bl.addStretch()

            self._status = QLabel("Click SCAN to begin")
            self._status.setStyleSheet(f"color:{self.hex('muted')}; font-size:11px;")
            bl.addWidget(self._status)
            vl.addWidget(bar)

            # Health bar (full-width, 4px)
            self._hbar = self.make_hbar(4)
            vl.addWidget(self._hbar)

            # Canvas + panel
            split = QSplitter(Qt.Horizontal)
            split.setStyleSheet("QSplitter::handle{background:#2A2A2A; width:1px;}")

            self._scene = QGraphicsScene()
            self._view  = _GraphView(self._scene)
            self._minimap = _MiniMap(self._scene, self._view, lambda: self._node_items)
            self._view.set_minimap(self._minimap)
            self._actlog = _ActivityLog(self._view)
            self._view.set_actlog(self._actlog)
            split.addWidget(self._view)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedWidth(314)
            scroll.setStyleSheet("background:#181818; border:none; border-left:1px solid #2A2A2A;")
            self._panel = _InfoPanel()
            self._panel.setStyleSheet("background:#181818;")
            self._panel.w_note.textChanged.connect(self._on_note)
            self._panel.prop_apply.connect(self._on_prop_apply)
            scroll.setWidget(self._panel)
            split.addWidget(scroll)
            split.setStretchFactor(0, 1)
            split.setStretchFactor(1, 0)
            vl.addWidget(split)

        # ── Actions ───────────────────────────────────────────────────────

        def _log(self, msg: str, level: str = "info") -> None:
            """Update toolbar status label AND push to the activity log overlay."""
            self._status.setText(msg)
            self._actlog.push(msg, level)

        def _do_scan(self) -> None:
            self._log("Scanning…")
            QApplication.processEvents()
            try:
                path = self._path_edit.text().strip()

                # Auto-detect Verse path if field is empty
                if not path:
                    try:
                        from .verse_snippet_generator import (
                            _find_uefn_project_root,
                        )
                        root     = _find_uefn_project_root()
                        cfg_path = get_config().get("verse.project_path", "")
                        candidates = [
                            cfg_path,
                            os.path.join(root, "Verse"),
                        ] + [
                            os.path.join(root, e)
                            for e in (os.listdir(root) if os.path.isdir(root) else [])
                            if e.endswith(".verse")
                        ]
                        for c in candidates:
                            if c and os.path.isdir(c):
                                path = c
                                self._path_edit.setText(path)
                                break
                    except Exception:
                        pass

                level_devs  = _scan_level()
                verse_files = _find_verse_files(path)
                verse_data  = [v for v in (_VerseParser.parse(vf) for vf in verse_files) if v]
                self._graph = _GraphBuilder.build(level_devs, verse_data)
                self._health_score = self._graph.health_score
                self._rebuild_scene()
                self._grouped_layout()
                self._load_layout()     # restore saved positions + first-time comments
                self._do_fit_view()
                self._paint_hbar()
                nd = len(self._graph.nodes)
                ne = len(self._graph.edges)
                nw = sum(len(n.warnings) for n in self._graph.nodes)
                nerr = sum(len(n.errors) for n in self._graph.nodes)
                hlvl = "ok" if self._health_score >= 70 else ("warn" if self._health_score >= 40 else "error")
                self._log(
                    f"{nd} devices · {ne} edges · {len(verse_files)} verse files · "
                    f"health {self._health_score}/100 · {self._graph.cluster_count} clusters · "
                    f"{nw}W {nerr}E",
                    level=hlvl,
                )
                self._populate_cat_combo()
            except Exception as exc:
                self._log(f"Scan error: {exc}", level="error")
                log_error(f"verse_graph_open: {exc}")

        def _do_help(self) -> None:
            self._help_dlg = _HelpDialog()
            self._help_dlg.show_in_uefn()

        def _populate_cat_combo(self) -> None:
            """Rebuild the category dropdown from the current graph."""
            if not self._graph:
                return
            cats = sorted({nd.category or "Uncategorized" for nd in self._graph.nodes})
            self._cat_combo.blockSignals(True)
            current = self._cat_combo.currentText()
            self._cat_combo.clear()
            self._cat_combo.addItem("All Categories")
            for c in cats:
                self._cat_combo.addItem(c)
            # Restore previous selection if still valid
            idx = self._cat_combo.findText(current)
            self._cat_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._cat_combo.blockSignals(False)

        def _on_category_filter(self, category: str) -> None:
            """Show only nodes belonging to the selected category."""
            self._on_node_unhovered()
            show_all = (category == "All Categories")
            for nid, item in self._node_items.items():
                node_cat = item.data.category or "Uncategorized"
                item.setVisible(show_all or node_cat == category)
                if not item.isVisible() and self._selected and self._selected.id == nid:
                    self._selected = None
                    self._panel.clear()
            self._on_edge_toggle()
            # Keep search filter consistent
            if self._search.text().strip():
                self._on_search(self._search.text())

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
                self._log(f"Exported → {path}", level="ok")

        def _do_generate_wiring(self) -> None:
            if not self._graph:
                self._log("Run SCAN first.", level="warn")
                return
            has_path = bool(self._path_edit.text().strip())
            code = _build_wiring_code(self._graph, has_verse_path=has_path)
            dlg  = _WiringCodeDialog(
                code, verse_path=self._path_edit.text().strip()
            )
            dlg.show_in_uefn()

        def _do_browse(self) -> None:
            path = QFileDialog.getExistingDirectory(self, "Select Verse Project Folder")
            if path:
                self._path_edit.setText(path)

        def _on_search(self, text: str) -> None:
            self._on_node_unhovered()   # clear any active dim before refiltering
            t = text.strip().lower()
            cat = self._cat_combo.currentText()
            show_all_cats = (cat == "All Categories")
            for nid, item in self._node_items.items():
                node_cat = item.data.category or "Uncategorized"
                cat_ok = show_all_cats or node_cat == cat
                text_ok = (not t or t in item.data.label.lower()
                           or t in item.data.class_name.lower()
                           or t in (item.data.category or "").lower())
                visible = cat_ok and text_ok
                item.setVisible(visible)
                # Clear selection if the selected node is now hidden
                if not visible and self._selected and self._selected.id == nid:
                    self._selected = None
                    self._panel.clear()

            # Sync edge visibility — respects both search filter and type toggles
            self._on_edge_toggle()

        def _on_note(self) -> None:
            if self._selected:
                self._selected.note = self._panel.w_note.toPlainText().strip()

        def _on_prop_apply(self, prop: str, value: str) -> None:
            nd = self._selected
            if not nd or not nd.actor:
                return
            try:
                if prop == "label" and value and value != nd.label:
                    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                    sub.set_actor_label(nd.actor, value)
                    nd.label = value
                    # Refresh the node item label in the graph
                    item = self._node_items.get(nd.id)
                    if item:
                        item.update()
                    self._panel.w_name.setText(value)
                    self._panel.w_prop_status.setText(f"Renamed → {value}")
                    self._log(f"Renamed: {value}", level="ok")
                elif prop == "folder":
                    folder_val = value or "None"
                    nd.actor.set_folder_path(unreal.Name(value))
                    nd.folder = value
                    self._panel.w_prop_status.setText(f"Folder → {folder_val}")
                    self._log(f"Folder set: {folder_val}", level="ok")
            except Exception as exc:
                self._panel.w_prop_status.setText(f"Error: {exc}")
                self._log(f"Write-back failed: {exc}", level="error")

        # ── Fit / edge toggles / hover highlight ──────────────────────────

        def _do_fit_view(self) -> None:
            rect = self._scene.itemsBoundingRect()
            if rect.isValid():
                self._view.fitInView(rect.adjusted(-60, -60, 60, 60),
                                     Qt.KeepAspectRatio)
            self._minimap.fit_scene()

        def _do_focus_selection(self) -> None:
            """Centre and zoom the view onto the currently selected node."""
            if not self._selected:
                return
            item = self._node_items.get(self._selected.id)
            if not item:
                return
            r = item.sceneBoundingRect()
            self._view.fitInView(r.adjusted(-120, -80, 120, 80), Qt.KeepAspectRatio)
            self._minimap.update()

        def _on_edge_toggle(self) -> None:
            show_ed = self._btn_editable.isChecked()
            show_ev = self._btn_events.isChecked()
            show_ca = self._btn_calls.isChecked()
            for eitem in self._edge_items:
                t  = eitem.data.edge_type
                ok = ((t == "editable" and show_ed) or
                      (t == "event"    and show_ev) or
                      (t == "call"     and show_ca))
                si = self._node_items.get(eitem.data.source_id)
                ti = self._node_items.get(eitem.data.target_id)
                eitem.setVisible(ok and bool(si and si.isVisible()
                                             and ti and ti.isVisible()))

        def _on_node_hovered(self, nd: DeviceNode) -> None:
            # Collect the hovered node + all its direct neighbours
            highlight: set = {nd.id}
            active_edges: set = set()
            for eitem in self._edge_items:
                sid, tid = eitem.data.source_id, eitem.data.target_id
                if sid == nd.id or tid == nd.id:
                    highlight.add(sid)
                    highlight.add(tid)
                    active_edges.add(id(eitem))

            for nid, item in self._node_items.items():
                item.setOpacity(1.0 if nid in highlight else 0.12)
            for eitem in self._edge_items:
                eitem.setOpacity(1.0 if id(eitem) in active_edges else 0.06)
            self._hover_active = True

        def _on_node_unhovered(self) -> None:
            if not self._hover_active:
                return
            for item in self._node_items.values():
                item.setOpacity(1.0)
            for eitem in self._edge_items:
                eitem.setOpacity(1.0)
            self._hover_active = False

        # ── Comment boxes ─────────────────────────────────────────────────

        def _add_comment(self) -> None:
            """Spawn a new note box just outside the scene content, then pan to it."""
            rect = self._scene.itemsBoundingRect()
            if rect.isValid():
                x = rect.right() + 60
                y = rect.top()
            else:
                c = self._view.mapToScene(self._view.viewport().rect().center())
                x, y = c.x() - 150, c.y() - 70
            box = _CommentBox(x=x, y=y)
            box.deleted.connect(self._remove_comment)
            self._scene.addItem(box)
            self._comment_items.append(box)
            self._view.centerOn(box)

        def _remove_comment(self, box: "_CommentBox") -> None:
            if box in self._comment_items:
                self._comment_items.remove(box)
            if box.scene():
                self._scene.removeItem(box)

        # ── Grouped layout ────────────────────────────────────────────────

        def _grouped_layout(self) -> None:
            """
            Arrange nodes in labelled category columns — Blueprint-style.
            Categories are sorted by size (largest first), each gets a header
            label above its column, and nodes are stacked vertically within it.
            Re-Layout still uses force-directed physics for freeform exploration.
            """
            if not self._graph:
                return

            # Group by category
            from collections import defaultdict
            groups: Dict[str, List[DeviceNode]] = defaultdict(list)
            for nd in self._graph.nodes:
                groups[nd.category].append(nd)

            # Sort: largest group first, then alphabetical
            sorted_cats = sorted(groups.keys(), key=lambda c: (-len(groups[c]), c))

            MAX_ROWS         = 12    # nodes per column
            MAX_COLS_PER_ROW = 12    # columns before wrapping to a new row group
            COL_W            = _NODE_W + 60
            ROW_H            = _NODE_H + 26
            CAT_HDR          = 40
            PAD_X            = 60
            PAD_Y            = 80
            ROW_GROUP_H      = MAX_ROWS * ROW_H + CAT_HDR + 100  # vertical pitch per row group

            # Remove old category header text items
            for item in self._cat_header_items:
                if item.scene():
                    self._scene.removeItem(item)
            self._cat_header_items = []

            col_x       = PAD_X
            col_count   = 0
            row_y_base  = 0

            for cat in sorted_cats:
                nodes = groups[cat]
                n_sub = math.ceil(len(nodes) / MAX_ROWS)

                for sub in range(n_sub):
                    # Wrap to new row group when column limit is hit
                    if col_count > 0 and col_count % MAX_COLS_PER_ROW == 0:
                        row_y_base += ROW_GROUP_H
                        col_x       = PAD_X

                    sub_nodes = nodes[sub * MAX_ROWS:(sub + 1) * MAX_ROWS]
                    cat_color = _CAT_COLORS.get(cat, "#888888")

                    # Category header text
                    hdr = QGraphicsTextItem()
                    display = cat.upper() if sub == 0 else f"{cat.upper()} ({sub + 1})"
                    hdr.setHtml(
                        f'<span style="color:{cat_color}; '
                        f'font-family:\'Segoe UI\'; font-size:10px; font-weight:600;">'
                        f'{display}</span>'
                    )
                    hdr.setPos(col_x, row_y_base + PAD_Y - CAT_HDR)
                    hdr.setZValue(-1)
                    self._scene.addItem(hdr)
                    self._cat_header_items.append(hdr)

                    for row, nd in enumerate(sub_nodes):
                        nd.x = float(col_x)
                        nd.y = float(row_y_base + PAD_Y + row * ROW_H)
                        item = self._node_items.get(nd.id)
                        if item:
                            item.setPos(nd.x, nd.y)

                    col_x     += COL_W
                    col_count += 1

                col_x += 30   # extra gap between category groups

            self._scene.update()

        # ── Layout persistence ────────────────────────────────────────────

        def _layout_path(self) -> str:
            saved = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
            os.makedirs(saved, exist_ok=True)
            return os.path.join(saved, "graph_layout.json")

        def _save_layout(self) -> None:
            if not self._graph:
                return
            try:
                data = {
                    "version": 1,
                    "nodes": {
                        nd.label: {"x": nd.x, "y": nd.y}
                        for nd in self._graph.nodes
                    },
                    "comments": [b.to_dict() for b in self._comment_items],
                }
                with open(self._layout_path(), "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
                log_info(f"verse_graph: layout saved ({len(self._graph.nodes)} nodes, "
                         f"{len(self._comment_items)} notes)")
            except Exception as exc:
                log_warning(f"verse_graph: layout save failed: {exc}")

        def _load_layout(self) -> None:
            try:
                path = self._layout_path()
                if not os.path.exists(path):
                    return
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)

                # Restore node positions (always — covers re-scans too)
                pos_map  = data.get("nodes", {})
                restored = 0
                for nd in self._graph.nodes:
                    if nd.label in pos_map:
                        nd.x = pos_map[nd.label]["x"]
                        nd.y = pos_map[nd.label]["y"]
                        item = self._node_items.get(nd.id)
                        if item:
                            item.setPos(nd.x, nd.y)
                        restored += 1

                # Restore comment boxes only on first load — after that
                # the in-memory list is authoritative and _rebuild_scene handles it
                if not self._layout_loaded and not self._comment_items:
                    for d in data.get("comments", []):
                        box = _CommentBox(**d)
                        box.deleted.connect(self._remove_comment)
                        self._scene.addItem(box)
                        self._comment_items.append(box)

                self._layout_loaded = True
                if restored:
                    self._log(f"Layout restored ({restored}/{len(self._graph.nodes)} nodes)", level="ok")
            except Exception as exc:
                log_warning(f"verse_graph: layout load failed: {exc}")

        # ── Live sync ─────────────────────────────────────────────────────

        def closeEvent(self, event) -> None:
            self._save_layout()
            if self._live_timer:
                self._live_timer.stop()
            if self._sel_timer:
                self._sel_timer.stop()
            super().closeEvent(event)

        def _toggle_live(self) -> None:
            self._live_sync = not self._live_sync
            if self._live_sync:
                self._live_btn.setProperty("accent", "true")
                self._live_btn.setStyle(self._live_btn.style())
                self._live_timer = QTimer()
                self._live_timer.timeout.connect(self._live_check)
                self._live_timer.start(4000)
                self._log("● LIVE — watching for changes", level="live")
                self._status.setStyleSheet(f"color:{self.hex('ok')}; font-size:11px;")
                # Build initial fingerprint
                self._actor_fingerprint = self._build_fingerprint()
            else:
                if self._live_timer:
                    self._live_timer.stop()
                    self._live_timer = None
                self._live_btn.setProperty("accent", "false")
                self._live_btn.setStyle(self._live_btn.style())
                self._status.setStyleSheet(f"color:{self.hex('muted')}; font-size:11px;")
                self._log("Live sync off")

        def _build_fingerprint(self) -> str:
            """Lightweight level fingerprint — device actor count + sorted labels."""
            try:
                sub    = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                actors = sub.get_all_level_actors()
                labels = sorted(
                    a.get_actor_label()
                    for a in actors
                    if any(kw in a.get_class().get_name() for kw in _DEV_KEYWORDS)
                )
                return f"{len(labels)}:{','.join(labels[:30])}"
            except Exception:
                return ""

        def _live_check(self) -> None:
            """Poll for level changes; resync graph if anything moved or was added/removed."""
            if not self._live_sync:
                return
            fp = self._build_fingerprint()
            if fp and fp != self._actor_fingerprint:
                self._actor_fingerprint = fp
                self._do_live_scan()

        def _do_live_scan(self) -> None:
            """Re-scan and update graph without disturbing existing node positions."""
            # Cache current node positions from scene items
            pos_cache: Dict[str, Tuple[float, float]] = {}
            if self._graph:
                for nd in self._graph.nodes:
                    item = self._node_items.get(nd.id)
                    pos_cache[nd.id] = (item.x(), item.y()) if item else (nd.x, nd.y)

            try:
                path       = self._path_edit.text().strip()
                level_devs = _scan_level()
                verse_files = _find_verse_files(path)
                verse_data  = [v for v in (_VerseParser.parse(vf) for vf in verse_files) if v]
                self._graph = _GraphBuilder.build(level_devs, verse_data)
                self._health_score = self._graph.health_score

                # Restore positions for known nodes; new nodes land near graph centroid
                if pos_cache:
                    cx = sum(x for x, _ in pos_cache.values()) / len(pos_cache)
                    cy = sum(y for _, y in pos_cache.values()) / len(pos_cache)
                else:
                    cx, cy = 0.0, 0.0

                for nd in self._graph.nodes:
                    if nd.id in pos_cache:
                        nd.x, nd.y = pos_cache[nd.id]
                    else:
                        nd.x = cx + random.uniform(-200, 200)
                        nd.y = cy + random.uniform(-200, 200)

                self._rebuild_scene()

                # Place all nodes at their cached/assigned positions (no re-layout)
                for nd in self._graph.nodes:
                    item = self._node_items.get(nd.id)
                    if item:
                        item.setPos(nd.x, nd.y)

                self._minimap.fit_scene()
                self._paint_hbar()

                ndn  = len(self._graph.nodes)
                nde  = len(self._graph.edges)
                self._log(
                    f"● LIVE  {ndn} devices · {nde} edges · health {self._health_score}/100",
                    level="live",
                )
                self._status.setStyleSheet(f"color:{self.hex('ok')}; font-size:11px;")

                # Refresh side panel if selected node still exists
                if self._selected:
                    refreshed = next(
                        (n for n in self._graph.nodes if n.id == self._selected.id), None
                    )
                    if refreshed:
                        self._selected = refreshed
                        self._panel.show_node(refreshed, self._health_score)
                    else:
                        self._selected = None
                        self._panel.clear()

            except Exception as exc:
                self._log(f"Live sync error: {exc}", level="error")

        def _on_node_clicked(self, nd: DeviceNode) -> None:
            self._selected = nd
            self._panel.show_node(nd, self._health_score)
            if nd.actor:
                try:
                    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                    sub.select_nothing()
                    sub.set_actor_selection_state(nd.actor, True)
                    # Defer CAMERA ALIGN to the next Slate tick.
                    # execute_console_command triggers the engine's full command pipeline
                    # and crashes if called directly from a Qt signal handler.
                    # Deferring via register_slate_pre_tick_callback runs it on the main
                    # Unreal thread — same pattern used by _schedule_menu in __init__.py.
                    _fired = False
                    def _align(dt: float) -> None:
                        nonlocal _fired
                        if _fired:
                            return
                        _fired = True
                        try:
                            unreal.SystemLibrary.execute_console_command(
                                unreal.EditorLevelLibrary.get_editor_world(), "CAMERA ALIGN"
                            )
                        except Exception:
                            pass
                        finally:
                            unreal.unregister_slate_pre_tick_callback(_handle)
                    _handle = unreal.register_slate_pre_tick_callback(_align)
                except Exception:
                    pass

        def _check_viewport_selection(self) -> None:
            """Sync graph highlight when user clicks an actor in the UEFN viewport."""
            if not self._graph:
                return
            try:
                sub      = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                selected = sub.get_selected_level_actors()

                # Viewport deselected — remove graph glow, keep panel content
                if not selected:
                    if self._scene.selectedItems():
                        self._scene.clearSelection()
                    return

                actor = selected[0]

                # Skip if already showing this node (we set it from a graph click)
                if self._selected and self._selected.actor is not None:
                    try:
                        if self._selected.actor == actor:
                            return
                    except Exception:
                        self._selected = None  # stale pointer — reset

                # Find matching graph node
                match = None
                for nd in self._graph.nodes:
                    if nd.actor is None:
                        continue
                    try:
                        if nd.actor == actor:
                            match = nd
                            break
                    except Exception:
                        continue  # stale actor reference — skip

                if match:
                    self._selected = match
                    self._panel.show_node(match, self._health_score)
                    item = self._node_items.get(match.id)
                    if item:
                        self._scene.clearSelection()
                        item.setSelected(True)
                        self._view.centerOn(item)
                else:
                    # Non-graph actor selected — clear visual highlight, keep panel
                    if self._scene.selectedItems():
                        self._scene.clearSelection()
            except Exception:
                pass

        # ── Scene ─────────────────────────────────────────────────────────

        def _rebuild_scene(self) -> None:
            # Snapshot comment boxes before clearing (scene.clear() destroys all items)
            saved_comments = [b.to_dict() for b in self._comment_items]
            self._cat_header_items.clear()
            self._scene.clear()
            self._node_items.clear()
            self._edge_items.clear()
            self._comment_items.clear()
            if not self._graph:
                return

            for nd in self._graph.nodes:
                item = _NodeItem(nd)
                item.node_clicked.connect(self._on_node_clicked)
                item.node_hovered.connect(self._on_node_hovered)
                item.node_unhovered.connect(self._on_node_unhovered)
                item.setToolTip(_make_node_tooltip(nd))
                self._scene.addItem(item)
                self._node_items[nd.id] = item

            for edge in self._graph.edges:
                si = self._node_items.get(edge.source_id)
                ti = self._node_items.get(edge.target_id)
                if si and ti:
                    eitem = _EdgeItem(edge, si, ti)
                    self._scene.addItem(eitem)
                    self._edge_items.append(eitem)

            # Restore comment boxes — survive every rebuild (live sync, manual scan)
            for d in saved_comments:
                box = _CommentBox(**d)
                box.deleted.connect(self._remove_comment)
                self._scene.addItem(box)
                self._comment_items.append(box)

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

            # Seed unplaced nodes — category-based circular placement so
            # related devices start clustered and physics has a good starting point.
            cats      = list({nd.category for nd in nodes})
            n_cats    = max(len(cats), 1)
            cat_idx   = {c: i for i, c in enumerate(cats)}
            radius    = max(min(vw, vh) * 0.48, 600.0)

            for nd in nodes:
                if nd.x == 0 and nd.y == 0:
                    angle = (2 * math.pi * cat_idx.get(nd.category, 0) / n_cats
                             + random.uniform(-0.4, 0.4))
                    r     = radius * random.uniform(0.4, 1.0)
                    nd.x  = vw / 2 + r * math.cos(angle)
                    nd.y  = vh / 2 + r * math.sin(angle)

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
            # Only physics-simulate visible nodes — hidden nodes cause ghost jitter
            nodes = [nd for nd in self._l_nodes
                     if self._node_items.get(nd.id, None) is None
                     or self._node_items[nd.id].isVisible()]
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

    # ─────────────────────────────────────────────────────────────────────
    #  Wiring Code Dialog
    # ─────────────────────────────────────────────────────────────────────

    class _WiringCodeDialog(ToolbeltWindow):
        """Shows generated Verse wiring code with copy + write-to-file actions."""

        def __init__(self, code: str, verse_path: str = "") -> None:
            super().__init__(title="UEFN Toolbelt — Generated Verse Wiring",
                             width=860, height=620)
            self._code        = code
            self._verse_path  = verse_path
            self._build_ui()

        def _build_ui(self) -> None:
            root = QWidget()
            self.setCentralWidget(root)
            vl = QVBoxLayout(root)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            bar, bl = self.make_topbar("GENERATED VERSE WIRING")
            self._copy_btn  = self.make_btn("Copy to Clipboard", accent=True,
                                            cb=self._copy)
            self._write_btn = self.make_btn("Write to Verse File",
                                            cb=self._write_file)
            bl.addWidget(self._copy_btn)
            bl.addWidget(self._write_btn)
            bl.addStretch()
            self._write_status = QLabel("")
            self._write_status.setStyleSheet(f"color:{self.hex('ok')}; font-size:11px;")
            bl.addWidget(self._write_status)
            vl.addWidget(bar)

            # Code editor
            self._editor = QTextEdit()
            self._editor.setPlainText(self._code)
            self._editor.setFont(QFont("Consolas", 9))
            self._editor.setStyleSheet(
                f"background:{self.hex('panel')}; color:{self.hex('text')};"
                f"border:none; padding:12px;"
            )
            vl.addWidget(self._editor)

            # Tip bar
            tip = QLabel(
                "  Tip: paste into your creative_device class, "
                "or click 'Write to Verse File' to deploy as generated_wiring.verse"
            )
            tip.setStyleSheet(
                f"background:{self.hex('topbar')}; color:{self.hex('muted')};"
                f"font-size:11px; padding:6px 12px;"
                f"border-top:1px solid {self.hex('border')};"
            )
            vl.addWidget(tip)

        def _copy(self) -> None:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._editor.toPlainText())
            self._write_status.setText("Copied!")

        def _write_file(self) -> None:
            try:
                from ..registry import get_registry
                code = self._editor.toPlainText()
                result = get_registry().execute(
                    "verse_write_file",
                    filename="generated_wiring.verse",
                    content=code,
                    overwrite=True,
                )
                if isinstance(result, dict) and result.get("status") == "ok":
                    path = result.get("path", "generated_wiring.verse")
                    self._write_status.setText(f"Written → {path}")
                else:
                    self._write_status.setStyleSheet(
                        f"color:{self.hex('warn')}; font-size:11px;")
                    self._write_status.setText(
                        "verse_write_file needs a verse.project_path — "
                        "set it in Config tab first."
                    )
            except Exception as exc:
                self._write_status.setStyleSheet(
                    f"color:{self.hex('error')}; font-size:11px;")
                self._write_status.setText(f"Error: {exc}")

else:
    # Fallback stub so the module loads cleanly when PySide6 is absent
    class _DeviceGraphWindow(ToolbeltWindow):  # type: ignore[no-redef]
        def __init__(self, *a, **kw): pass
