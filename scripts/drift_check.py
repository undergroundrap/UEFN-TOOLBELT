"""
UEFN Toolbelt — drift_check.py
================================
Detects stale hardcoded version strings, tool counts, and category counts
across the codebase. Run this with plain Python before every commit — no
UEFN or unreal module required.

Usage:
    python scripts/drift_check.py

Exit code 0 = clean. Exit code 1 = drift found (blocks commit).

Add to pre-commit workflow:
    python scripts/drift_check.py || exit 1
"""

from __future__ import annotations

import ast
import os
import re
import sys

# ── Repo root ──────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Ground truth — read directly from the single source of truth ──────────────

def _read_constants() -> tuple[str, int, int]:
    """Read __version__, __tool_count__, and __category_count__ from the single source of truth."""
    init_path = os.path.join(ROOT, "Content", "Python", "UEFN_Toolbelt", "__init__.py")
    with open(init_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    version = None
    tool_count = None
    category_count = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__version__":
                    if isinstance(node.value, ast.Constant):
                        version = str(node.value.value)
                if isinstance(t, ast.Name) and t.id == "__tool_count__":
                    if isinstance(node.value, ast.Constant):
                        tool_count = int(node.value.value)  # type: ignore[arg-type]
                if isinstance(t, ast.Name) and t.id == "__category_count__":
                    if isinstance(node.value, ast.Constant):
                        category_count = int(node.value.value)  # type: ignore[arg-type]
    if version is None:
        raise RuntimeError("Could not read __version__ from __init__.py")
    if tool_count is None:
        raise RuntimeError("Could not read __tool_count__ from __init__.py")
    if category_count is None:
        raise RuntimeError("Could not read __category_count__ from __init__.py")
    return version, tool_count, category_count


VERSION, TOOL_COUNT, CATEGORY_COUNT = _read_constants()

# ── Files to scan ─────────────────────────────────────────────────────────────

SCAN_FILES = [
    "WORKORDER.md",
    "SECURITY.md",
    "README.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "llms.txt",
    "ARCHITECTURE.md",
    "TOOL_STATUS.md",
    "mcp_server.py",
    "docs/CHANGELOG.md",
    "docs/plugin_dev_guide.md",
    "docs/ui_style_guide.md",
    "docs/uefn_python_capabilities.md",
    "docs/SCHEMA_EXPLORER.md",
    "docs/PIPELINE.md",
    "docs/audits/2026-08-24-uefn-42-official-mcp-audit.md",
    "docs/audits/evidence/2026-08-24-official-mcp-signatures.json",
    "docs/work-orders/README.md",
    "docs/work-orders/proposed/WO-001-custom-mcp-security.md",
    "docs/work-orders/proposed/WO-002-epic-toolset-integration.md",
    "docs/work-orders/proposed/WO-003-official-mcp-doc-convergence.md",
    "docs/work-orders/proposed/WO-004-modal-observability.md",
    "docs/work-orders/proposed/WO-005-coverage-source-of-truth.md",
    "docs/work-orders/proposed/WO-006-official-vs-toolbelt-benchmark.md",
    "docs/work-orders/proposed/WO-007-public-mcp-explainer.md",
    "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py",
    "tests/smoke_test.py",
    # Agent context files. These carry tool counts and per-tool tables that go
    # stale exactly like the docs do — three counts had already drifted before
    # they were added here.
    "AGENTS.md",
    ".agents/workflows/add_new_tool.md",
    ".agents/workflows/run_tests.md",
    ".github/pull_request_template.md",
    ".claude/commands/add-tool.md",
    ".claude/commands/deploy.md",
    ".claude/commands/drift.md",
    ".claude/commands/publish-check.md",
    ".claude/tool_tables.md",
    ".claude/mcp_reference.md",
    ".claude/rules/tool_authoring.md",
    ".claude/agents/tool-developer.md",
]

# ── UI reachability ratchet ───────────────────────────────────────────────────
# The dashboard builds its tabs from hand-written functions, not from the
# registry, so registering a tool does NOT make it clickable. Three Epic MCP
# tools shipped registered-but-unreachable before this check existed.
#
# 158 of 362 tools are currently UI-invisible, and many of those are deliberate
# (MCP/CLI-only utilities). Failing on all of them would be a permanently red
# check, which is a check people learn to ignore. So this is a ratchet: the
# number may fall, never rise. A new tool must be surfaced, or the baseline
# raised deliberately with a reason.

_UI_SURFACES = [
    "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py",
    "Content/Python/UEFN_Toolbelt/menu.py",
]

_UI_INVISIBLE_BASELINE = 158


# ── /Game/ default-path ratchet ───────────────────────────────────────────────
# In UEFN, /Game/ is Epic's Fortnite install, not the creator's project
# (UEFN_QUIRKS.md #23). A tool defaulting a path there scans the wrong content
# tree — or, if it WRITES, produces assets the project cannot reference. That is
# what left ~700 dangling material references behind arena_generate.
#
# All of them are now gone: write destinations go through
# core.resolve_content_path(), scan paths through core.resolve_scan_path().
# The baseline is 0, so this is no longer a ratchet in practice — any new
# /Game/ default fails the check outright.

_GAME_PATH_DEFAULT_BASELINE = 0

_WORK_ORDER_STATES = {"PROPOSED", "ISSUED", "COMPLETED", "SUPERSEDED"}


def _game_path_defaults() -> list[str]:
    """
    Every /Game/ path baked into the source — parameter defaults and module-level
    constants alike.

    Module constants matter as much as defaults and were missed the first time:
    material_master's PARENT_MATERIAL_PATH and smart_importer's
    AUTO_MATERIAL_PARENT both pointed at /Game/, so every material tool silently
    applied the engine fallback while reporting success. A constant evaluated at
    import cannot be right here — mount detection needs a live editor.
    """
    import ast
    from pathlib import Path

    found = []
    pkg = Path(ROOT) / "Content" / "Python" / "UEFN_Toolbelt"
    for path in sorted(pkg.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        # module-level constants
        for stmt in tree.body:
            tgt: ast.expr | None = None
            val: ast.expr | None = None
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                tgt, val = stmt.targets[0], stmt.value
            elif isinstance(stmt, ast.AnnAssign):
                tgt, val = stmt.target, stmt.value
            if (isinstance(tgt, ast.Name) and isinstance(val, ast.Constant)
                    and isinstance(val.value, str)
                    and (val.value == "/Game" or val.value.startswith("/Game/"))):
                found.append(f"{path.name}:{tgt.id} = {val.value!r}")

        # UI call sites. The dashboard and menu are how most people actually run
        # these tools, and every button used to pass scan_path="/Game"
        # explicitly — which overrides the tool's own resolver, because
        # resolve_scan_path() only fills in an EMPTY value. Fixing 42 parameter
        # defaults did nothing for any of them.
        if path.name in {"dashboard_pyside6.py", "menu.py"}:
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and (node.value == "/Game" or node.value.startswith("/Game/"))):
                    found.append(f"{path.name}:{node.lineno} literal {node.value!r}")

        # function parameter defaults
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            a = node.args
            params = a.args + a.kwonlyargs
            defaults = ([None] * (len(a.args) - len(a.defaults))
                        + list(a.defaults) + list(a.kw_defaults))
            for prm, dflt in zip(params, defaults, strict=False):
                if (isinstance(dflt, ast.Constant)
                        and isinstance(dflt.value, str)
                        and (dflt.value == "/Game" or dflt.value.startswith("/Game/"))):
                    found.append(f"{node.name}({prm.arg}={dflt.value!r})")
    return found


def check_game_path_defaults() -> list[dict]:
    """Flag a rise in parameters defaulting to Epic's /Game/ mount."""
    found = _game_path_defaults()
    count = len(found)

    if count > _GAME_PATH_DEFAULT_BASELINE:
        return [{
            "file": "scripts/drift_check.py", "line": 0,
            "type": "/Game/ default path",
            "found": f"{count} /Game/ paths baked into source",
            "expected": f"at most {_GAME_PATH_DEFAULT_BASELINE} (the ratchet baseline)",
            "content": (
                f"{count - _GAME_PATH_DEFAULT_BASELINE} new. /Game/ is Epic's Fortnite "
                f"install, not the project. Use core.resolve_scan_path() for reads and "
                f"core.resolve_content_path() for writes. New: "
                + ", ".join(found[-8:])
            ),
        }]

    if count < _GAME_PATH_DEFAULT_BASELINE:
        return [{
            "file": "scripts/drift_check.py", "line": 0,
            "type": "/Game/ default path (ratchet)",
            "found": f"{count} /Game/ paths baked into source",
            "expected": f"_GAME_PATH_DEFAULT_BASELINE is still {_GAME_PATH_DEFAULT_BASELINE}",
            "content": (
                f"Fewer /Game/ defaults than the baseline — lower "
                f"_GAME_PATH_DEFAULT_BASELINE to {count} to lock the gain in."
            ),
        }]

    return []


def _registered_tools() -> dict:
    """Map every @register_tool name to its category, parsed from source."""
    import ast
    tools = {}
    from pathlib import Path
    pkg = Path(ROOT) / "Content" / "Python" / "UEFN_Toolbelt"
    for path in pkg.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call)
                        and getattr(dec.func, "id", "") == "register_tool"):
                    continue
                kw = {k.arg: k.value for k in dec.keywords}
                name, cat = kw.get("name"), kw.get("category")
                if isinstance(name, ast.Constant):
                    tools[name.value] = (cat.value if isinstance(cat, ast.Constant)
                                         else "?")
    return tools


def check_ui_coverage() -> list[dict]:
    """Flag a rise in the number of tools no UI surface can reach."""
    tools = _registered_tools()
    if not tools:
        return []

    from pathlib import Path
    surfaces = ""
    for rel in _UI_SURFACES:
        path = Path(ROOT) / rel
        if path.exists():
            surfaces += path.read_text(encoding="utf-8")

    invisible = sorted(
        n for n in tools
        if f'"{n}"' not in surfaces and f"'{n}'" not in surfaces
    )
    count = len(invisible)

    if count > _UI_INVISIBLE_BASELINE:
        return [{
            "file": "scripts/drift_check.py",
            "line": 0,
            "type": "ui reachability",
            "found": f"{count} tools unreachable from the dashboard or menu",
            "expected": f"at most {_UI_INVISIBLE_BASELINE} (the ratchet baseline)",
            "content": (
                f"{count - _UI_INVISIBLE_BASELINE} newly unreachable. Add them to a "
                f"tab in dashboard_pyside6.py or an _entry() in menu.py — registering "
                f"a tool does not surface it. If a tool is intentionally headless, "
                f"raise _UI_INVISIBLE_BASELINE and say why. Unreachable: "
                + ", ".join(invisible[-12:])
            ),
        }]

    if count < _UI_INVISIBLE_BASELINE:
        return [{
            "file": "scripts/drift_check.py",
            "line": 0,
            "type": "ui reachability (ratchet)",
            "found": f"{count} tools unreachable",
            "expected": f"_UI_INVISIBLE_BASELINE is still {_UI_INVISIBLE_BASELINE}",
            "content": (
                "UI coverage improved — lower _UI_INVISIBLE_BASELINE to "
                f"{count} so the gain is locked in and cannot silently regress."
            ),
        }]

    return []


def check_work_order_contract() -> list[dict]:
    """Prevent durable planning files from silently granting authority."""
    from pathlib import Path

    findings: list[dict] = []
    root = Path(ROOT)
    pointer_path = root / "WORKORDER.md"
    guide_path = root / "docs" / "work-orders" / "README.md"
    proposed_dir = root / "docs" / "work-orders" / "proposed"
    issued_dir = root / "docs" / "work-orders" / "issued"

    def add(file: str, kind: str, found: str, expected: str) -> None:
        findings.append({
            "file": file,
            "line": 0,
            "type": kind,
            "found": found,
            "expected": expected,
            "content": found,
        })

    if not pointer_path.exists():
        add("WORKORDER.md", "work order pointer", "missing", "canonical pointer present")
        return findings

    pointer = pointer_path.read_text(encoding="utf-8")
    pointer_lines = pointer.splitlines()

    def pointer_value(prefix: str) -> str | None:
        matches = [line.removeprefix(prefix).strip() for line in pointer_lines
                   if line.startswith(prefix)]
        return matches[0] if len(matches) == 1 else None

    current = pointer_value("- Current issued Work Order:")
    session = pointer_value("- Authorized session:")
    if current is None:
        add("WORKORDER.md", "current work order gate", "missing or duplicated",
            "one '- Current issued Work Order:' line")
    if session is None:
        add("WORKORDER.md", "authorized session gate", "missing or duplicated",
            "one '- Authorized session:' line")

    guide = guide_path.read_text(encoding="utf-8") if guide_path.exists() else ""
    missing_states = sorted(state for state in _WORK_ORDER_STATES if f"`{state}`" not in guide)
    if missing_states:
        add("docs/work-orders/README.md", "work order states",
            ", ".join(missing_states), "all allowed states documented")
    for required in (
        "Only the repository-root `WORKORDER.md`",
        "no implementation is authorized",
        "at most one detailed Work Order is issued",
    ):
        if required not in guide:
            add("docs/work-orders/README.md", "work order authority",
                f"missing {required!r}", "canonical non-authorizing guidance")

    proposals = sorted(proposed_dir.glob("WO-*.md")) if proposed_dir.exists() else []
    if not proposals:
        add("docs/work-orders/proposed", "proposed work orders", "none", "at least one proposal")
    for path in proposals:
        text = path.read_text(encoding="utf-8")
        status_lines = [line.strip() for line in text.splitlines()
                        if line.startswith("STATUS:")]
        auth_lines = [line.strip() for line in text.splitlines()
                      if line.startswith("AUTHORIZATION:")]
        rel = path.relative_to(root).as_posix()
        if status_lines != ["STATUS: PROPOSED"]:
            add(rel, "proposed status", repr(status_lines), "exactly STATUS: PROPOSED")
        if auth_lines != ["AUTHORIZATION: NOT AUTHORIZED"]:
            add(rel, "proposed authorization", repr(auth_lines),
                "exactly AUTHORIZATION: NOT AUTHORIZED")
        if any(line.startswith(("- Current issued Work Order:", "- Authorized session:"))
               for line in text.splitlines()):
            add(rel, "canonical gate duplication", "current gate outside WORKORDER.md",
                "current authority only in WORKORDER.md")

    work_order_docs = sorted((root / "docs" / "work-orders").rglob("*.md"))
    for path in work_order_docs:
        lines = path.read_text(encoding="utf-8").splitlines()
        duplicated = [
            line
            for line in lines
            if line.startswith(("- Current issued Work Order:",
                                "- Authorized session:",
                                "- Current gate:"))
        ]
        if duplicated:
            rel = path.relative_to(root).as_posix()
            add(rel, "canonical gate duplication", repr(duplicated),
                "current authority only in WORKORDER.md")

    issued = sorted(
        path for path in issued_dir.glob("*.md")
        if path.name.lower() != "readme.md"
    ) if issued_dir.exists() else []
    if len(issued) > 1:
        add("docs/work-orders/issued", "issued work order count", str(len(issued)), "at most 1")

    if current == "NONE":
        if session != "NONE":
            add("WORKORDER.md", "authorization without issued work order",
                str(session), "NONE")
        if issued:
            add("docs/work-orders/issued", "unpointed issued work order",
                issued[0].name, "empty while current pointer is NONE")
    elif current is not None:
        if len(issued) != 1:
            add("docs/work-orders/issued", "current issued work order",
                str(len(issued)), "exactly one file matching the pointer")
        elif not (current in {issued[0].name, issued[0].stem}
                  or issued[0].stem.startswith(current)):
            add("WORKORDER.md", "current issued work order mismatch", current,
                issued[0].name)

    return findings


# ── Patterns ──────────────────────────────────────────────────────────────────

# Version patterns — flag any version string that doesn't match VERSION
_VERSION_PATTERNS = [
    # badge: version-1.2.3
    (re.compile(r"version-(\d+\.\d+\.\d+)"), "badge version"),
    # inline: v1.2.3 (but not inside URLs or semver ranges like >=1.0.0)
    (re.compile(r"(?<![/>=])v(\d+\.\d+\.\d+)(?!\d)"), "inline version"),
    # quoted: "1.9.4" or '1.9.3' when near "version"
    (re.compile(r"""(?i)version['":\s]+['"]((\d+\.\d+\.\d+))['"]"""), "quoted version"),
]

# Tool count patterns — flag any number adjacent to "tool" that doesn't match TOOL_COUNT
# Up to two words may sit between the count and "tool". "355 registered tools",
# "358 built-in tools" and "355 Professional Tools" all went stale unnoticed
# because the old pattern required the number to be immediately adjacent.
_TOOL_COUNT_PATTERN = re.compile(
    r"\b(\d{2,4})\s+(?:[A-Za-z][\w-]*\s+){0,2}tools?\b",
    re.IGNORECASE,
)

# Category count patterns — flag any number adjacent to "categor" that doesn't match CATEGORY_COUNT
_CATEGORY_COUNT_PATTERN = re.compile(
    r"\b(\d{2,3})\s+categor",
    re.IGNORECASE,
)

# ── Known-ok exceptions (file, line_fragment) — intentionally historical ──────
# Add entries here for lines that should never be flagged (e.g. changelog entries,
# prior-version attribution, or "minimum version" declarations).

_EXCEPTIONS = {
    # Changelog entries are historical — always exempt
    "docs/CHANGELOG.md",
}

# Lines containing these fragments are always skipped (changelog bullets, prior art,
# partial coverage counts that are intentionally less than TOOL_COUNT, etc.)
_SKIP_LINE_FRAGMENTS = [
    "MIN_TOOLBELT_VERSION",
    "min_toolbelt_version",
    "## v",              # changelog header
    "### v",
    "**v",               # changelog bold header
    "uefn-mcp-server",   # attribution to prior art
    "KirChuvakov",
    "Kirch's original",  # "Kirch's original 22 tools" — historical attribution
    "prior art",
    "commits before v",  # "commits before v2.3.7 use the older unscoped form"
                         # — a statement about history. Bumping it would make
                         # it false; that is a wrong answer, not a fixed one.
    "# drift_check",     # this file itself
    # Smoke test and integration test cover a subset of tools — these counts are
    # intentionally less than TOOL_COUNT and should never be flagged as drift.
    "Smoke Test",
    "smoke test",
    "Smoke_Test",
    "Integration Test",
    # Subset counts that are intentionally smaller than TOOL_COUNT, and example
    # JSON in the plugin guide. Targeted fragments rather than exempting whole
    # files — a blanket exemption on plugin_dev_guide.md is what let two stale
    # tool counts sit in it unnoticed.
    "smoke-test time",
    "key tools",
    "toolbelt_version",
    "integration test",
    "integration_test",
    "toolbelt_smoke_test",
    "toolbelt_integration_test",
    "Verifies",          # "Verifies 123 tools register..."
    "exercised",         # "163 tools exercised end-to-end"
    "safe tools execute",
    # JSON schema examples in docs — version field is intentionally illustrative
    '"version": "1.0.0"',
    '"version": "1.',
    # README Patch Notes section — historical version/count entries
    "bumped from stale",
    "171 → 246",
    "→ 250 tools",
    "→ 247 tools",
    "→ 229 tools",
    "→ 217 tools",
    "→ 204 tools",
    "→ 165 tools",
    "→ 140 tools",
    "initial release",
    "Simulation, Sequencer",  # README patch notes v1.1 historical entry
    "Batch 9:",               # TOOL_STATUS.md integration test batch heading
    # README patch notes for v2.4.0 - both are statements about history, and
    # bumping either would make it false rather than current.
    "read the changelog rather than this",  # names the v1.6.0-v2.3.9 gap
    "stopped being maintained after v",     # ditto - names where the
                                            # README patch notes went stale.
    "carried no `status` key",              # "37 returns across 16 tools" - the
                                            # count of tools that had the bug,
                                            # not the total tool count.
    "Batch 10:",              # ditto - the heading names the release the batch
                              # shipped in (v1.9.6), which is history, not a
                              # claim about the current version.
    "Phase 19",   # patch notes historical entry
    "Phase 18",
    "Phase 17",
    "Phase 16",
    "Phase 15",
    "Phase 14",
    "Phase 13",
    # Module count (not tool count) — "23 tool modules" is a file count
    "tool modules",
    # Creative device categories (35) — different from tool categories
    "Creative device",
    "Creative devices",
    "device Blueprints",
    # Historical initial-release category list — intentionally partial
    "13 categories: Materials",
    # Module count in comparison table — "38 modules" not "38 categories"
    "38 modules",
    # Per-module tool counts in changelog — e.g. "(10 tools)" for a single module
    ") — Full actor",
    ") — Full",
    # CLAUDE.md integration test description — 163 is coverage count not total
    "163 tools *work*",
    "harness spawns real actor",
]

# ── Scanner ────────────────────────────────────────────────────────────────────

def _should_skip_line(line: str) -> bool:
    return any(frag in line for frag in _SKIP_LINE_FRAGMENTS)


def scan_file(rel_path: str, version: str, tool_count: int, category_count: int = 0) -> list[dict]:
    abs_path = os.path.join(ROOT, rel_path)
    if not os.path.exists(abs_path):
        return []

    findings = []
    exempt_file = rel_path in _EXCEPTIONS

    with open(abs_path, encoding="utf-8", errors="ignore") as f:
        for lineno, line in enumerate(f, 1):
            if _should_skip_line(line):
                continue

            if not exempt_file:
                # Version drift
                for pat, label in _VERSION_PATTERNS:
                    for m in pat.finditer(line):
                        found = m.group(1)
                        if found != version:
                            findings.append({
                                "file":     rel_path,
                                "line":     lineno,
                                "type":     f"version ({label})",
                                "found":    found,
                                "expected": version,
                                "content":  line.rstrip(),
                            })

            # Tool count drift — skip files that are entirely historical (changelog)
            if rel_path in {"docs/CHANGELOG.md"}:
                continue
            for m in _TOOL_COUNT_PATTERN.finditer(line):
                found = int(m.group(1))
                if found != tool_count:
                    findings.append({
                        "file":     rel_path,
                        "line":     lineno,
                        "type":     "tool count",
                        "found":    str(found),
                        "expected": str(tool_count),
                        "content":  line.rstrip(),
                    })

            # Category count drift
            if category_count:
                for m in _CATEGORY_COUNT_PATTERN.finditer(line):
                    found = int(m.group(1))
                    if found != category_count:
                        findings.append({
                            "file":     rel_path,
                            "line":     lineno,
                            "type":     "category count",
                            "found":    str(found),
                            "expected": str(category_count),
                            "content":  line.rstrip(),
                        })

    return findings


def run() -> int:
    # Force UTF-8 output on Windows to handle emoji/arrows in file content
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    print(f"\n[drift_check] Ground truth: version={VERSION}  tools={TOOL_COUNT}  categories={CATEGORY_COUNT}")
    scan_files = list(SCAN_FILES)
    work_order_root = os.path.join(ROOT, "docs", "work-orders")
    if os.path.isdir(work_order_root):
        for dirpath, _dirnames, filenames in os.walk(work_order_root):
            for filename in filenames:
                if filename.endswith(".md"):
                    rel = os.path.relpath(os.path.join(dirpath, filename), ROOT)
                    rel = rel.replace(os.sep, "/")
                    if rel not in scan_files:
                        scan_files.append(rel)

    print(f"[drift_check] Scanning {len(scan_files)} files...\n")

    all_findings: list[dict] = []
    for rel in scan_files:
        findings = scan_file(rel, VERSION, TOOL_COUNT, CATEGORY_COUNT)
        all_findings.extend(findings)

    all_findings.extend(check_ui_coverage())
    all_findings.extend(check_game_path_defaults())
    all_findings.extend(check_work_order_contract())

    if not all_findings:
        print("[drift_check] PASS — No drift found. Codebase is consistent.\n")
        return 0

    print(f"[drift_check] FAIL — {len(all_findings)} drift finding(s):\n")
    for f in all_findings:
        print(f"  {f['file']}:{f['line']}")
        print(f"    type:     {f['type']}")
        print(f"    found:    {f['found']}")
        print(f"    expected: {f['expected']}")
        print(f"    line:     {f['content'][:120]}")
        print()

    print("[drift_check] Fix the above before committing.\n")
    return 1


if __name__ == "__main__":
    sys.exit(run())
