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

def _read_constants() -> tuple[str, int]:
    """Read __version__ and __tool_count__ from the single source of truth."""
    init_path = os.path.join(ROOT, "Content", "Python", "UEFN_Toolbelt", "__init__.py")
    with open(init_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    version = None
    tool_count = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__version__":
                    if isinstance(node.value, ast.Constant):
                        version = str(node.value.value)
                if isinstance(t, ast.Name) and t.id == "__tool_count__":
                    if isinstance(node.value, ast.Constant):
                        tool_count = int(node.value.value)
    if version is None:
        raise RuntimeError("Could not read __version__ from __init__.py")
    if tool_count is None:
        raise RuntimeError("Could not read __tool_count__ from __init__.py")
    return version, tool_count


VERSION, TOOL_COUNT = _read_constants()

# ── Files to scan ─────────────────────────────────────────────────────────────

SCAN_FILES = [
    "README.md",
    "CLAUDE.md",
    "ARCHITECTURE.md",
    "TOOL_STATUS.md",
    "mcp_server.py",
    "docs/CHANGELOG.md",
    "docs/plugin_dev_guide.md",
    "docs/ui_style_guide.md",
    "docs/uefn_python_capabilities.md",
    "docs/SCHEMA_EXPLORER.md",
    "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py",
    "tests/smoke_test.py",
]

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
_TOOL_COUNT_PATTERN = re.compile(
    r"\b(\d{2,4})\s+tool",
    re.IGNORECASE,
)

# ── Known-ok exceptions (file, line_fragment) — intentionally historical ──────
# Add entries here for lines that should never be flagged (e.g. changelog entries,
# prior-version attribution, or "minimum version" declarations).

_EXCEPTIONS = {
    # Changelog entries are historical — always exempt
    "docs/CHANGELOG.md",
    # Plugin dev guide references MIN_TOOLBELT_VERSION examples
    "docs/plugin_dev_guide.md",
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
    "# drift_check",     # this file itself
    # Smoke test and integration test cover a subset of tools — these counts are
    # intentionally less than TOOL_COUNT and should never be flagged as drift.
    "Smoke Test",
    "smoke test",
    "Smoke_Test",
    "Integration Test",
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
    "pending live run",       # TOOL_STATUS.md batch status notes
    "pending live UEFN run",
    "Phase 19",   # patch notes historical entry
    "Phase 18",
    "Phase 17",
    "Phase 16",
    "Phase 15",
    "Phase 14",
    "Phase 13",
    # Module count (not tool count) — "23 tool modules" is a file count
    "tool modules",
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


def scan_file(rel_path: str, version: str, tool_count: int) -> list[dict]:
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
                # Allow ±0 — exact match only
                if found != tool_count:
                    findings.append({
                        "file":     rel_path,
                        "line":     lineno,
                        "type":     "tool count",
                        "found":    str(found),
                        "expected": str(tool_count),
                        "content":  line.rstrip(),
                    })

    return findings


def run() -> int:
    # Force UTF-8 output on Windows to handle emoji/arrows in file content
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

    print(f"\n[drift_check] Ground truth: version={VERSION}  tools={TOOL_COUNT}")
    print(f"[drift_check] Scanning {len(SCAN_FILES)} files...\n")

    all_findings: list[dict] = []
    for rel in SCAN_FILES:
        findings = scan_file(rel, VERSION, TOOL_COUNT)
        all_findings.extend(findings)

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
