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
import io
import os
import re
import sys
import tokenize

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
    "docs/work-orders/completed/WO-001-custom-mcp-security.md",
    "docs/work-orders/completed/WO-002-epic-toolset-integration.md",
    "docs/work-orders/issued/WO-003-official-mcp-doc-convergence.md",
    "docs/work-orders/proposed/WO-004-modal-observability.md",
    "docs/work-orders/proposed/WO-005-coverage-source-of-truth.md",
    "docs/work-orders/proposed/WO-006-official-vs-toolbelt-benchmark.md",
    "docs/work-orders/proposed/WO-007-public-mcp-explainer.md",
    "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py",
    # Both carried stale counts that no check could see, because neither was
    # a declared target. WO-003 corrected the counts and declared the paths.
    "Content/Python/UEFN_Toolbelt/__init__.py",
    "launcher.py",
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
_ISSUED_NO_SESSION_AUTH = "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED"
_ISSUED_SESSION_A_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION"
)
_ISSUED_SESSION_A_ACCEPTED = (
    "AUTHORIZATION: ISSUED — SESSION A ACCEPTED; NO SESSION AUTHORIZED"
)
_COMPLETED_NO_SESSION_AUTH = "AUTHORIZATION: COMPLETED — NO SESSION AUTHORIZED"
_WO001_COMPLETION_COMMIT = "ffcbe8b1bfa03cb37453b9beefda0bbdbe45543c"
_WO001_COMPLETION_WORKFLOW = "32921154482"
_WO001_COMPLETION_JOB = "98034843256"
_WO001_COMPLETED_GATE = "WO-001 COMPLETED — WO-002 PROPOSED AND NOT AUTHORIZED"
_WO002_COMPLETION_COMMIT = "c031f20e33c716ecc9f9ce546a7419b865ed8641"
_WO002_COMPLETION_WORKFLOW = "33133090929"
_WO002_COMPLETION_JOB = "98726805137"
_WO002_EVIDENCE_PATH = (
    "docs/audits/evidence/2026-08-27-wo002-session-b-official-mcp.json"
)
_WO002_EVIDENCE_SHA256 = (
    "9DFBD500808113A122C65DA680AF8AD5409045DC1414AFEBEFB6B8771FE46CB0"
)
_WO003_NAME = "WO-003-official-mcp-doc-convergence.md"
_WO003_PLANNING_BASELINE = "e0b1063f5300404534c76789bdb6742f639425ba"
_WO003_ISSUANCE_COMMIT = "19350aa324bea4d88e494ee806801586a383d76e"
_WO003_ISSUANCE_WORKFLOW = "33148089523"
_WO003_ISSUANCE_JOB = "98773518991"
_WO003_ISSUED_GATE = (
    "WO-003 ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED"
)
_WO003_SESSION_A_BASE = "52d89295614a4ce686094736d87f7e6c907e12a0"
_WO003_SESSION_A_WORKFLOW = "33200547479"
_WO003_SESSION_A_JOB = "98948639416"
_WO003_SESSION_A_GATE = (
    "WO-003 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY"
)
_WO003_SESSION_A_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted "
    "Session A implementation. Session B remains unauthorized."
)
_WO003_SESSION_A_STATEMENT = (
    "Session A is authorized for implementation under the current root"
)
# Session B drafting is a separate owner gate that has not been given. The
# checker carries that fact, so activating Session B in the pointer alone
# cannot open it - reopening has to edit this file too, which is visible.
_WO003_SESSION_B_UNAUTHORIZED = (
    "WO-003 Session B remains unauthorized and requires a separate owner gate"
)
_WO002_COMPLETED_GATE = (
    "WO-002 COMPLETED — WO-003 PROPOSED AND NOT AUTHORIZED"
)
_WO002_NAME = "WO-002-epic-toolset-integration.md"
_WO002_ISSUANCE_BASE = "098b38c669dd330cd059ea18dea52cc4e7eaefe2"
_WO002_BASELINE_MARKER = f"BASELINE: `{_WO002_ISSUANCE_BASE}`"
_WO002_ISSUANCE_WORKFLOW = "32925047925"
_WO002_ISSUANCE_JOB = "98046156859"
_WO002_CLOSED_GATE = "WO-002 ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED"
_WO002_SESSION_A_BASE = "d87572e2a272c98f8dd634cfe17ff8a130446a7b"
_WO002_SESSION_A_WORKFLOW = "32931353926"
_WO002_SESSION_A_JOB = "98064090312"
_WO002_SESSION_A_GATE = "WO-002 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY"
_WO002_SESSION_A_ACCEPTED_BASE = "50b881716abea3b5838c2a971caac40ee4cd5d30"
_WO002_SESSION_A_ACCEPTED_WORKFLOW = "32937631903"
_WO002_SESSION_A_ACCEPTED_JOB = "98081919978"
_WO002_SESSION_A_ACCEPTED_GATE = (
    "WO-002 SESSION A ACCEPTED — SESSION B NOT AUTHORIZED"
)
_WO002_REQUIRED_JOB_TITLE = "Lint, types, tests"
_WO002_ACCEPTED_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO002_SESSION_A_ACCEPTED_WORKFLOW
)
_WO002_ACCEPTED_JOB_URL = (
    _WO002_ACCEPTED_RUN_URL + "/job/" + _WO002_SESSION_A_ACCEPTED_JOB
)
# Exact acceptance-evidence fragments.
#
# A presence-only membership test cannot enforce this record. Each identifier
# occurs two or three times per surface - visible label, run URL, job URL, and
# in WORKORDER.md the separate `Base commit` marker - so one visible label or
# URL can rot to a wrong value while another occurrence keeps `in` satisfied.
# Every fragment below pins ONE occurrence in its own position and form, and
# the narrative commit is anchored to its sentence so the `Base commit` bullet
# can never stand in for it.
_WO002_ACCEPTED_POINTER_EVIDENCE = (
    ("acceptance narrative commit",
     "pushed as `" + _WO002_SESSION_A_ACCEPTED_BASE + "`;"),
    ("acceptance workflow label",
     "[CI workflow `" + _WO002_SESSION_A_ACCEPTED_WORKFLOW + "`]"),
    ("acceptance workflow URL", "(" + _WO002_ACCEPTED_RUN_URL + ")"),
    ("acceptance required-job label",
     "[`" + _WO002_SESSION_A_ACCEPTED_JOB + "` — "
     + _WO002_REQUIRED_JOB_TITLE + "]"),
    ("acceptance job URL", "(" + _WO002_ACCEPTED_JOB_URL + ")"),
)
_WO002_ACCEPTED_ISSUED_EVIDENCE = (
    ("acceptance narrative commit",
     "accepted and committed as `" + _WO002_SESSION_A_ACCEPTED_BASE + "`."),
    ("acceptance workflow label",
     "[`" + _WO002_SESSION_A_ACCEPTED_WORKFLOW + "`]"),
    ("acceptance workflow URL", "(" + _WO002_ACCEPTED_RUN_URL + ")"),
    ("acceptance required-job label",
     "[`" + _WO002_SESSION_A_ACCEPTED_JOB + "` — "
     + _WO002_REQUIRED_JOB_TITLE + "]"),
    ("acceptance job URL", "(" + _WO002_ACCEPTED_JOB_URL + ")"),
)

# Canonical acceptance regions.
#
# Fragment-presence over a whole document is position-blind: corrupting the
# real occurrence and appending a correct decoy elsewhere - even inside an
# HTML comment - satisfies a containment test.
#
# Bounding the record by markers drawn from its own prose is not enough
# either. Those markers travel with the content, so a transplant defeats them:
# corrupt the genuine record together with its markers, paste a byte-correct
# copy anywhere else, and a marker search selects the transplant as its one
# valid region and passes.
#
# Each record is therefore located by the structure immediately around it,
# never by anything inside it, and the block at that anchored position must
# match exactly. A transplant then leaves the anchored position holding the
# corrupted text.
#
# The anchors are references and headings, not prose: rewording a neighbouring
# record cannot produce a WO-002 acceptance finding, and an unrelated heading
# added elsewhere in the issued Work Order is none of this check's business.
_WO001_COMPLETED_LINK = "](docs/work-orders/completed/WO-001-custom-mcp-security.md)"
_WO002_COMPLETED_LINK = (
    "](docs/work-orders/completed/WO-002-epic-toolset-integration.md)"
)
_WO002_LINK_ANY = re.compile(
    r"\]\(docs/work-orders/(?:issued|completed)/"
    r"WO-002-epic-toolset-integration\.md\)"
)


def _normalize_wo002_link(text: str) -> str:
    """Collapse the WO-002 reference so its state directory is not pinned."""
    return _WO002_LINK_ANY.sub("](WO-002)", text)
_WO002_BASIS_HEADING = "## Session A authorization basis"
_WO002_RECORD_HEADING = "## Session A acceptance record"
_WO002_FOLLOWING_HEADING = "## Problem and accepted evidence"
_WO002_ACCEPTED_POINTER_BLOCK = (
    "[`WO-002`](docs/work-orders/completed/WO-002-epic-toolset-"
    "integration.md) is completed. Session A was independently "
    "accepted, committed, and pushed as "
    "`50b881716abea3b5838c2a971caac40ee4cd5d30`; [CI workflow "
    "`32937631903`](https://github.com/undergroundrap/UEFN-"
    "TOOLBELT/actions/runs/32937631903) completed successfully, "
    "including required job [`98081919978` — Lint, types, "
    "tests](https://github.com/undergroundrap/UEFN-"
    "TOOLBELT/actions/runs/32937631903/job/98081919978). Session A is "
    "accepted and complete."
)
_WO002_TERMINAL_EXTERNAL = (
    "`externally_listable`, `externally_describable`, and "
    "`externally_callable` all failed."
)
_WO002_NEGATIVE_RESULT = (
    "This is an accepted negative result bounded by "
    "`UE::ValkyrieToolset::ToolsetPolicy`, not a repaired or externally"
    " exposed integration."
)
_WO002_ACCEPTED_ISSUED_BLOCK = (
    "## Session A acceptance record Session A was independently "
    "accepted and committed as "
    "`50b881716abea3b5838c2a971caac40ee4cd5d30`. CI workflow "
    "[`32937631903`](https://github.com/undergroundrap/UEFN-"
    "TOOLBELT/actions/runs/32937631903) completed successfully, "
    "including required job [`98081919978` — Lint, types, "
    "tests](https://github.com/undergroundrap/UEFN-"
    "TOOLBELT/actions/runs/32937631903/job/98081919978). Accepted live "
    "`TOOL_TEST` evidence recorded 362 tools across 55 categories; the "
    "internal list, describe, and run contracts passed; every external "
    "official- MCP state remained `not_tested`; and the dashboard truth"
    " model was verified. Independent review also confirmed that the "
    "existing dashboard auto-start behavior required no Session A "
    "correction. The listener was stopped locally, the handoff was "
    "absent, and ports 8765–8770 were closed after verification. "
    "Session A is accepted and complete."
)


def _paragraphs(text: str) -> list[list[str]]:
    """Blank-line delimited blocks, each as its list of lines."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip():
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _anchored_pointer_region(text: str) -> tuple[str | None, str | None]:
    """The WO-002 acceptance paragraph, located by the paragraph before it.

    The preceding paragraph is identified by the WO-001 completion reference
    rather than by its wording, so WO-001 supplies position only: rewording it
    cannot produce a WO-002 finding, while duplicating its reference to forge
    an anchor fails closed.
    """
    occurrences = text.count(_WO001_COMPLETED_LINK)
    if occurrences != 1:
        return None, (
            "WO-001 completion link occurs " + str(occurrences)
            + "x, expected exactly 1"
        )
    occurrences = len(_WO002_LINK_ANY.findall(text))
    if occurrences != 1:
        return None, (
            "WO-002 link occurs " + str(occurrences) + "x, expected exactly 1"
        )
    blocks = _paragraphs(text)
    anchors = [
        index
        for index, block in enumerate(blocks)
        if _WO001_COMPLETED_LINK in "\n".join(block)
    ]
    if len(anchors) != 1:
        return None, (
            "WO-001 completion paragraph occurs " + str(len(anchors))
            + "x, expected exactly 1"
        )
    following = anchors[0] + 1
    if following >= len(blocks):
        return None, "no paragraph follows the WO-001 completion paragraph"
    region = "\n".join(blocks[following])
    if not _WO002_LINK_ANY.search(region):
        return None, (
            "the paragraph after the WO-001 completion paragraph does not "
            "carry the WO-002 link"
        )
    return " ".join(region.split()), None


def _anchored_issued_region(text: str) -> tuple[str | None, str | None]:
    """The acceptance section, located by its two neighbouring headings.

    Only the local ordering basis -> record -> following is required. Headings
    elsewhere in the Work Order are free to change, but the acceptance section
    cannot be renamed, duplicated, reordered, or re-homed without failing.
    """
    lines = text.split("\n")
    marks = [i for i, line in enumerate(lines) if line.startswith("## ")]
    headings = [lines[i] for i in marks]
    for heading in (
        _WO002_BASIS_HEADING,
        _WO002_RECORD_HEADING,
        _WO002_FOLLOWING_HEADING,
    ):
        occurrences = headings.count(heading)
        if occurrences != 1:
            return None, (
                "heading " + heading + " occurs " + str(occurrences)
                + "x, expected exactly 1"
            )
    basis = headings.index(_WO002_BASIS_HEADING)
    if basis + 2 >= len(headings):
        return None, "no two headings follow " + _WO002_BASIS_HEADING
    if headings[basis + 1] != _WO002_RECORD_HEADING:
        return None, (
            "the heading after " + _WO002_BASIS_HEADING + " is "
            + headings[basis + 1] + ", expected " + _WO002_RECORD_HEADING
        )
    if headings[basis + 2] != _WO002_FOLLOWING_HEADING:
        return None, (
            "the heading after " + _WO002_RECORD_HEADING + " is "
            + headings[basis + 2] + ", expected " + _WO002_FOLLOWING_HEADING
        )
    first = marks[basis + 1]
    last = marks[basis + 2]
    return " ".join("\n".join(lines[first:last]).split()), None


_WO003_ISSUED_SEQUENCE = (
    "BASELINE: `" + _WO003_PLANNING_BASELINE + "`",
    "ISSUANCE_COMMIT: `" + _WO003_ISSUANCE_COMMIT + "`",
    "ISSUANCE_CI_WORKFLOW: `" + _WO003_ISSUANCE_WORKFLOW + "`",
    "ISSUANCE_CI_JOB: `" + _WO003_ISSUANCE_JOB + "` — Lint, types, tests",
)
# The pointer's field keys in canonical order. Values for the three issuance
# fields are pinned exactly below; the other keys keep their own dedicated
# checks, so only their key and position are asserted here.
_WO003_POINTER_SEQUENCE = (
    "- Current issued Work Order:",
    "- Authorized session:",
    "- Base commit:",
    "- Current gate:",
    "- Issuance commit: `" + _WO003_ISSUANCE_COMMIT + "`",
    "- Issuance CI workflow: `" + _WO003_ISSUANCE_WORKFLOW + "`",
    "- Issuance CI job: `" + _WO003_ISSUANCE_JOB + "` — Lint, types, tests",
    "- Release train:",
    "- Release gate:",
)
# Authorizing Session A adds three declarations to each canonical block.
# The slice stays exact and terminal in the new state, so the issuance
# record cannot be dropped, reordered, or padded on the way through.
_WO003_SESSION_A_ISSUED_SEQUENCE = _WO003_ISSUED_SEQUENCE + (
    "SESSION_A_AUTHORIZATION_COMMIT: `" + _WO003_SESSION_A_BASE + "`",
    "SESSION_A_AUTHORIZATION_CI_WORKFLOW: `"
    + _WO003_SESSION_A_WORKFLOW + "`",
    "SESSION_A_AUTHORIZATION_CI_JOB: `" + _WO003_SESSION_A_JOB
    + "` — Lint, types, tests",
)
_WO003_SESSION_A_POINTER_SEQUENCE = _WO003_POINTER_SEQUENCE[:7] + (
    "- Session A authorization commit: `" + _WO003_SESSION_A_BASE + "`",
    "- Session A authorization CI workflow: `"
    + _WO003_SESSION_A_WORKFLOW + "`",
    "- Session A authorization CI job: `" + _WO003_SESSION_A_JOB
    + "` — Lint, types, tests",
) + _WO003_POINTER_SEQUENCE[7:]


def _canonical_metadata(text: str, stop) -> list[str]:
    """Non-blank lines of a document's canonical top block."""
    out = []
    for line in text.split("\n"):
        if stop(line):
            break
        stripped = line.strip()
        if stripped:
            out.append(stripped)
    return out


def _wo003_field_findings(text, sequence, stop, where, exact, terminal):
    """The canonical metadata as an exact contiguous slice.

    Enumerating wrapper syntax was a blacklist: an unlisted wrapper such as
    <details> still let a byte-correct field stand in for the declaration, and
    an ordering-only check still permitted arbitrary lines between fields. The
    slice must therefore *equal* the expected sequence with nothing between its
    entries, so any inserted line - wrapper, note, or otherwise - breaks it
    without the checker needing to know what that line means.
    """
    label = "WO-003 issuance field (" + where + ")"

    def fits(line: str, expected: str) -> bool:
        return line == expected if expected in exact else line.startswith(expected)

    block = _canonical_metadata(text, stop)
    heads = [i for i, line in enumerate(block) if fits(line, sequence[0])]
    if len(heads) != 1:
        return [(label,
                 sequence[0] + " opens the canonical slice " + str(len(heads))
                 + "x", "exactly one canonical metadata slice")]
    start = heads[0]
    actual = block[start:start + len(sequence)]
    if len(actual) != len(sequence):
        return [(label,
                 "the canonical slice holds " + str(len(actual))
                 + " lines", str(len(sequence)) + " canonical metadata lines")]
    for index, (expected, line) in enumerate(zip(sequence, actual, strict=True)):
        if not fits(line, expected):
            return [(label,
                     "canonical slice line " + str(index + 1) + " is " + line,
                     expected)]
    trailing = block[start + len(sequence):]
    if terminal and trailing:
        return [(label,
                 "extra metadata after the canonical slice: " + trailing[0],
                 "the canonical slice ends the metadata block")]
    return []


def _wo003_record_findings(
    pointer, issued_text, wo003_rel, base, current_gate, session
):
    """WO-003 issuance evidence survives the Session A transition.

    Authorizing a session must not silence the record that issued it, so
    the same exact-slice comparison runs from every session branch rather
    than living inside the closed-session one. The authorized state adds
    three declarations to each canonical block; the slice stays exact and
    terminal, so the issuance fields cannot be dropped, reordered, or
    padded on the way through.
    """
    out = []
    issued_sequence: tuple[str, ...]
    pointer_sequence: tuple[str, ...]
    if session == "A":
        expected_base = _WO003_SESSION_A_BASE
        expected_gate = _WO003_SESSION_A_GATE
        issued_sequence = _WO003_SESSION_A_ISSUED_SEQUENCE
        pointer_sequence = _WO003_SESSION_A_POINTER_SEQUENCE
        base_kind = "WO-003 Session A base commit"
        gate_kind = "WO-003 Session A gate"
    else:
        expected_base = _WO003_ISSUANCE_COMMIT
        expected_gate = _WO003_ISSUED_GATE
        issued_sequence = _WO003_ISSUED_SEQUENCE
        pointer_sequence = _WO003_POINTER_SEQUENCE
        base_kind = "WO-003 issuance base commit"
        gate_kind = "WO-003 issued gate"
    if base != "`" + expected_base + "`":
        out.append(("WORKORDER.md", base_kind, str(base),
                    "`" + expected_base + "`"))
    if current_gate != expected_gate:
        out.append(("WORKORDER.md", gate_kind, str(current_gate),
                    expected_gate))
    # The accepted planning baseline is pinned as its BASELINE marker; the
    # same hash also appears in the planning prose, which is not a second
    # declaration.
    marker = "BASELINE: `" + _WO003_PLANNING_BASELINE + "`"
    if issued_text.count(marker) != 1:
        out.append((wo003_rel, "WO-003 planning baseline",
                    str(issued_text.count(marker)),
                    "exactly one " + marker))
    # Only the pinned declarations carry a backticked value. The pointer's
    # remaining keys keep their own dedicated checks, so position and key
    # are all this comparison asserts for them.
    for kind, found_detail, want in _wo003_field_findings(
        issued_text, issued_sequence,
        lambda line: line.startswith("## "),
        "issued record",
        exact={item for item in issued_sequence if "`" in item},
        terminal=True,
    ):
        out.append((wo003_rel, kind, found_detail, want))
    for kind, found_detail, want in _wo003_field_findings(
        pointer, pointer_sequence,
        lambda line: _WO001_COMPLETED_LINK in line,
        "WORKORDER.md",
        exact={item for item in pointer_sequence if "`" in item},
        terminal=True,
    ):
        out.append(("WORKORDER.md", kind, found_detail, want))
    return out


def _acceptance_record_findings(text, locate, expected, fragments):
    """Findings for one structurally anchored canonical acceptance record."""
    found, reason = locate(text)
    if reason is not None:
        return [
            ("canonical acceptance region: " + reason,
             "exactly one structurally anchored canonical region")
        ]
    found = _normalize_wo002_link(found)
    expected = _normalize_wo002_link(expected)
    if found == expected:
        return []
    detail = []
    for label, fragment in fragments:
        occurrences = found.count(fragment)
        if occurrences != 1:
            detail.append((
                label + " occurs " + str(occurrences)
                + "x inside the canonical region",
                "exactly one canonical occurrence: " + fragment))
    if not detail:
        detail.append((
            "canonical acceptance block altered outside the pinned evidence",
            "the canonical acceptance record, byte-identical after normalization"))
    return detail


_WO002_NEXT_GATE = (
    "NEXT GATE: explicit BDFL/owner authorization for Session A. Issuance alone "
    "grants no implementation authority; Session B remains unauthorized."
)
_ISSUED_SESSION_B_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION B AUTHORIZED FOR EXTERNAL PROOF"
)
_WO002_SESSION_B_BASE = "d1a2c810126ba6c9e14891da1b25cb198c1d45c7"
_WO002_SESSION_B_WORKFLOW = "33047743360"
_WO002_SESSION_B_JOB = "98435618996"
_WO002_SESSION_B_GATE = (
    "WO-002 SESSION B AUTHORIZED — EXECUTE EXTERNAL PROOF ONLY"
)
_WO002_SESSION_B_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted "
    "Session B evidence. Session B is proof-only; WO-003 remains unauthorized."
)
_WO002_SESSION_B_PROOF_ONLY = (
    "Under the sole current gate in root `WORKORDER.md`, Session B is authorized "
    "for external proof only."
)
_WO002_SESSION_A_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted "
    "Session A implementation. Session B remains unauthorized."
)
_WO002_SESSION_A_ACCEPTED_NEXT_GATE = (
    "NEXT GATE: explicit BDFL/owner authorization for Session B. Session A is "
    "accepted and complete; no session is currently authorized."
)
_REMAINING_RELEASE_PROPOSALS = {
    "WO-003-official-mcp-doc-convergence.md",
    "WO-004-modal-observability.md",
    "WO-005-coverage-source-of-truth.md",
    "WO-006-official-vs-toolbelt-benchmark.md",
    "WO-007-public-mcp-explainer.md",
}
_FROZEN_RELEASE_TRAIN = "WO-001 through WO-007"
_CLOSED_RELEASE_GATE = (
    "NO TAG OR GITHUB RELEASE AUTHORIZED — COMPLETE THE FROZEN TRAIN AND FINAL "
    "INTEGRATION/REPOSITORY-TRUTH AUDIT FIRST"
)


def _accepted_record_findings(
    pointer: str, issued_text: str, rel: str
) -> list[tuple[str, str, str, str]]:
    """Session A's accepted record stays enforced in every later session.

    Authorizing Session B must not silence Session A's evidence, so the same
    anchored comparison runs from both branches rather than being duplicated.
    """
    out: list[tuple[str, str, str, str]] = []
    for evidence, kind in (
        (_WO002_SESSION_A_ACCEPTED_BASE, "Session A accepted commit"),
        (_WO002_SESSION_A_ACCEPTED_WORKFLOW, "Session A accepted workflow"),
        (_WO002_SESSION_A_ACCEPTED_JOB, "Session A accepted job"),
    ):
        if evidence not in pointer or evidence not in issued_text:
            out.append((rel, kind, "missing from pointer or issued record",
                        evidence))
    for found_detail, want in _acceptance_record_findings(
        pointer, _anchored_pointer_region,
        _WO002_ACCEPTED_POINTER_BLOCK, _WO002_ACCEPTED_POINTER_EVIDENCE,
    ):
        out.append(("WORKORDER.md",
                    "Session A acceptance record (WORKORDER.md)",
                    found_detail, want))
    for found_detail, want in _acceptance_record_findings(
        issued_text, _anchored_issued_region,
        _WO002_ACCEPTED_ISSUED_BLOCK, _WO002_ACCEPTED_ISSUED_EVIDENCE,
    ):
        out.append((rel, "Session A acceptance record (issued WO-002)",
                    found_detail, want))
    if "## Session A acceptance record" not in issued_text:
        out.append((rel, "Session A acceptance record", "missing",
                    "bounded accepted commit, CI, and live evidence"))
    return out


def _has_implicit_session_authorization(
    pointer: str, issued_text: str, expected_gate: str
) -> bool:
    """Reject positive activation language while the issued session is closed."""
    authority_text = " ".join((pointer + "\n" + issued_text).lower().split())
    allowed_contexts = (
        expected_gate.lower(),
        "authorized session: none",
        _ISSUED_NO_SESSION_AUTH.lower(),
    )
    for context in allowed_contexts:
        if authority_text.count(context) != 1:
            return True
        authority_text = authority_text.replace(context, "", 1)

    # Scan individual statements so an unrelated noun in the mandate cannot
    # combine with a distant verb to create a false positive. Contrast words
    # are boundaries too: "not authorized; nevertheless work may commence"
    # must inspect the positive clause independently from the negative one.
    statements = re.split(
        r"[.!?;:]|\b(?:but|however|nevertheless|nonetheless|yet)\b",
        authority_text,
        flags=re.IGNORECASE,
    )
    implementation_context = (
        r"(?:implement(?:ation|ing)?|work|session|approval|authorization|"
        r"permission)"
    )
    activation_action = re.compile(
        r"\b(?:begin(?:s|ning)?|start(?:s|ed|ing)?|commenc(?:e|es|ed|ing)|"
        r"proceed(?:s|ed|ing)?|resum(?:e|es|ed|ing))\b"
    )
    positive_state = re.compile(
        r"\b(?:authorized|permitted|approved|cleared|granted|unlocked|ready)\b"
    )
    grant_signal = re.compile(r"\b(?:go[- ]ahead|green\s+light)\b")
    unlabeled_activation = (
        re.compile(r"\byou\s+(?:may|can)\s+(?:now\s+)?"
                   r"(?:begin|start|commence|proceed|resume)\b"),
        re.compile(r"\bready\s+to\s+"
                   r"(?:begin|start|commence|proceed|resume)\b"),
        re.compile(r"\bproceed\s+with\b"),
    )
    contextual_action = re.compile(
        rf"(?:\b{implementation_context}\b.{{0,50}}{activation_action.pattern}|"
        rf"{activation_action.pattern}.{{0,50}}\b{implementation_context}\b)"
    )
    contextual_state = re.compile(
        rf"(?:\b{implementation_context}\b.{{0,50}}{positive_state.pattern}|"
        rf"{positive_state.pattern}.{{0,50}}\b{implementation_context}\b)"
    )
    gate_state = re.compile(
        r"(?:\bgate\b.{0,40}\b(?:open|cleared|passed|unlocked)\b|"
        r"\b(?:open|cleared|passed|unlocked)\b.{0,40}\bgate\b)"
    )
    owner_grant = re.compile(
        r"(?:\bowner\b(?:\s+(?:has|now|explicitly))*\s+"
        r"(?:authorized|permitted|approved|cleared|granted|unlocked)\b|"
        r"\bowner\b.{0,40}\b(?:go[- ]ahead|green\s+light)\b|"
        r"\b(?:go[- ]ahead|green\s+light)\b.{0,40}\bowner\b)"
    )
    closed_state = re.compile(
        r"\b(?:not\s+authorized|not\s+permitted|not\s+approved|unauthorized|"
        r"does\s+not\s+authorize|grants?\s+no\s+implementation\s+authority|"
        r"no\s+(?:implementation\s+)?session\s+is\s+authorized|"
        r"do\s+not.{0,120}\b(?:begin|start|commence|proceed|resume)\b|"
        r"(?:must|may)\s+not\s+(?:begin|start|commence|proceed|resume)"
        r"(?:\s+(?:until|without)\s+(?:a\s+|an\s+)?(?:separate\s+|explicit\s+)?"
        r"owner\s+(?:gate|authorization))?|"
        r"(?:is|are)\s+not\s+ready\s+to\s+"
        r"(?:begin|start|commence|proceed|resume))\b"
    )

    for statement in statements:
        residual = closed_state.sub("", statement)
        if any(pattern.search(residual) for pattern in unlabeled_activation):
            return True
        if (contextual_action.search(residual)
                or contextual_state.search(residual)
                or gate_state.search(residual)
                or owner_grant.search(residual)
                or (grant_signal.search(residual)
                    and re.search(rf"\b{implementation_context}\b", residual))):
            return True

    return False


def _has_other_session_authorization(
    pointer: str, issued_text: str, authorized_session: str
) -> bool:
    """Reject positive activation of a labeled session other than the current one."""
    authority_text = pointer + "\n" + issued_text
    statements = re.split(
        r"[\r\n]+|[.!?;]|\b(?:but|however|nevertheless|nonetheless|yet)\b",
        authority_text,
        flags=re.IGNORECASE,
    )
    positive = re.compile(
        r"\b(?:authorized|permitted|approved|cleared|granted|unlocked|ready|"
        r"go[- ]ahead|green\s+light|begin|start|commence|proceed|resume)\b",
        re.IGNORECASE,
    )
    negative = re.compile(
        r"\b(?:not\s+authorized|not\s+permitted|not\s+approved|unauthorized|"
        r"requires?\s+(?:a\s+)?separate\s+(?:owner\s+)?gate|"
        r"remains?\s+(?:closed|unauthorized)|"
        r"(?:must|may)\s+not\s+(?:begin|start|commence|proceed|resume)"
        r"(?:\s+(?:until|without)\s+(?:a\s+|an\s+)?(?:separate\s+|explicit\s+)?"
        r"owner\s+(?:gate|authorization))?|"
        r"(?:is|are)\s+not\s+ready\s+to\s+"
        r"(?:begin|start|commence|proceed|resume))\b",
        re.IGNORECASE,
    )
    for statement in statements:
        labels = re.findall(r"\bSession\s+([A-Z]{1,3})\b", statement)
        if not labels or all(label == authorized_session for label in labels):
            continue
        residual = negative.sub("", statement)
        if positive.search(residual):
            return True
    return False


def _has_next_work_order_authorization(
    pointer: str, other_text: str, work_order: str = "WO-002"
) -> bool:
    """Reject positive authority for a Work Order that is not issued."""
    authority_text = pointer + "\n" + other_text
    statements = re.split(
        r"[\r\n]+|[.!?;]|\b(?:but|however|nevertheless|nonetheless|yet)\b",
        authority_text,
        flags=re.IGNORECASE,
    )
    positive = re.compile(
        r"\b(?:issued|authorized|permitted|approved|cleared|granted|unlocked|ready|"
        r"go[- ]ahead|green\s+light|begin|start|commence|proceed|implement)\b",
        re.IGNORECASE,
    )
    negative = re.compile(
        r"\b(?:not\s+issued|not\s+authorized|unauthorized|does\s+not\s+issue|"
        r"does\s+not\s+authorize|no\s+implementation\s+session\s+is\s+authorized|"
        r"proposal\s+only|proposed|pre-issuance\s+review|separate\s+owner\s+"
        r"authorization)\b",
        re.IGNORECASE,
    )
    for statement in statements:
        if not re.search(rf"\b{re.escape(work_order)}\b", statement,
                         re.IGNORECASE):
            continue
        residual = negative.sub("", statement)
        if positive.search(residual):
            return True
    return False


def _has_release_authorization(pointer: str) -> bool:
    """Reject a positive tag or Release grant while the train gate is closed."""
    text = " ".join(pointer.split())
    allowed = (
        f"- Release gate: {_CLOSED_RELEASE_GATE}",
        "No tag or GitHub Release is authorized until the frozen train is complete, "
        "a final integration/repository-truth audit passes, and the owner separately "
        "authorizes a release session.",
    )
    for context in allowed:
        if text.count(context) != 1:
            return True
        text = text.replace(context, "", 1)
    release_target = r"(?:tag|github\s+release|release\s+session)"
    positive = r"(?:authorized|permitted|approved|cleared|granted|ready)"
    return bool(re.search(
        rf"(?:\b{release_target}\b.{{0,40}}\b{positive}\b|"
        rf"\b{positive}\b.{{0,40}}\b{release_target}\b)",
        text,
        re.IGNORECASE,
    ))


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
    completed_dir = root / "docs" / "work-orders" / "completed"
    superseded_dir = root / "docs" / "work-orders" / "superseded"

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
    base = pointer_value("- Base commit:")
    current_gate = pointer_value("- Current gate:")
    release_train = pointer_value("- Release train:")
    release_gate = pointer_value("- Release gate:")
    if current is None:
        add("WORKORDER.md", "current work order gate", "missing or duplicated",
            "one '- Current issued Work Order:' line")
    if session is None:
        add("WORKORDER.md", "authorized session gate", "missing or duplicated",
            "one '- Authorized session:' line")
    if base is None:
        add("WORKORDER.md", "base commit", "missing or duplicated",
            "one '- Base commit:' line")
    if current_gate is None:
        add("WORKORDER.md", "current gate", "missing or duplicated",
            "one '- Current gate:' line")
    if release_train != _FROZEN_RELEASE_TRAIN:
        add("WORKORDER.md", "release train", str(release_train),
            _FROZEN_RELEASE_TRAIN)
    if release_gate != _CLOSED_RELEASE_GATE:
        add("WORKORDER.md", "release authorization", str(release_gate),
            _CLOSED_RELEASE_GATE)
    elif _has_release_authorization(pointer):
        add("WORKORDER.md", "release authorization",
            "contradictory tag or GitHub Release permission",
            "release gate remains closed")

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

    proposal_names = {path.name for path in proposals}
    current_is_wo002 = current in {
        "WO-002", _WO002_NAME, _WO002_NAME.removesuffix(".md")
    }
    wo002_placed = ((issued_dir / _WO002_NAME).exists()
                    or (completed_dir / _WO002_NAME).exists())
    wo003_placed = ((issued_dir / _WO003_NAME).exists()
                    or (completed_dir / _WO003_NAME).exists())
    expected_proposals = set(_REMAINING_RELEASE_PROPOSALS)
    if not wo002_placed:
        expected_proposals.add(_WO002_NAME)
    if wo003_placed:
        # An issued or completed Work Order is no longer a proposal.
        expected_proposals.discard(_WO003_NAME)
    if proposal_names != expected_proposals:
        add("docs/work-orders/proposed", "release train proposal set",
            repr(sorted(proposal_names)),
            repr(sorted(expected_proposals)))

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
    completed = sorted(
        path for path in completed_dir.glob("*.md")
        if path.name.lower() != "readme.md"
    ) if completed_dir.exists() else []
    superseded = sorted(
        path for path in superseded_dir.glob("*.md")
        if path.name.lower() != "readme.md"
    ) if superseded_dir.exists() else []
    if len(issued) > 1:
        add("docs/work-orders/issued", "issued work order count", str(len(issued)), "at most 1")

    state_paths = proposals + issued + completed + superseded
    state_counts: dict[str, int] = {}
    for path in state_paths:
        state_counts[path.name] = state_counts.get(path.name, 0) + 1
    duplicate_names = sorted(name for name, count in state_counts.items() if count > 1)
    if duplicate_names:
        add("docs/work-orders", "duplicate work order state",
            ", ".join(duplicate_names), "a Work Order in exactly one state directory")

    wo002_paths = [path for path in state_paths if path.name == _WO002_NAME]
    if current_is_wo002:
        expected_wo002_path = issued_dir / _WO002_NAME
    elif (completed_dir / _WO002_NAME).exists():
        expected_wo002_path = completed_dir / _WO002_NAME
    else:
        expected_wo002_path = None
    if expected_wo002_path is not None and wo002_paths != [expected_wo002_path]:
        add("docs/work-orders", "WO-002 state",
            repr([path.relative_to(root).as_posix() for path in wo002_paths]),
            expected_wo002_path.relative_to(root).as_posix())

    wo003_paths = [path for path in state_paths if path.name == _WO003_NAME]
    if wo003_placed and wo003_paths != [issued_dir / _WO003_NAME]:
        add("docs/work-orders", "WO-003 state",
            repr([path.relative_to(root).as_posix() for path in wo003_paths]),
            (issued_dir / _WO003_NAME).relative_to(root).as_posix())

    # WO-002 completion is terminal. This checker carries the WO-002 completion
    # contract, so no rollback of the documents alone - however internally
    # coherent - can put the Work Order back into an implementable state.
    # Reopening it would have to edit this file too, which is a visible act.
    terminal_wo002_path = completed_dir / _WO002_NAME
    if wo002_paths != [terminal_wo002_path]:
        add("docs/work-orders", "completed WO-002 state",
            repr([path.relative_to(root).as_posix() for path in wo002_paths]),
            terminal_wo002_path.relative_to(root).as_posix())

    issued_metadata: dict[str, tuple[list[str], list[str], str]] = {}
    for path in issued:
        text = path.read_text(encoding="utf-8")
        status_lines = [line.strip() for line in text.splitlines()
                        if line.startswith("STATUS:")]
        auth_lines = [line.strip() for line in text.splitlines()
                      if line.startswith("AUTHORIZATION:")]
        rel = path.relative_to(root).as_posix()
        issued_metadata[path.name] = (status_lines, auth_lines, text)
        if status_lines != ["STATUS: ISSUED"]:
            add(rel, "issued status", repr(status_lines), "exactly STATUS: ISSUED")
        if len(auth_lines) != 1 or not auth_lines[0].startswith("AUTHORIZATION: ISSUED"):
            add(rel, "issued authorization", repr(auth_lines),
                "exactly one AUTHORIZATION: ISSUED marker")

    completed_metadata: dict[str, tuple[list[str], list[str], str]] = {}
    for path in completed:
        text = path.read_text(encoding="utf-8")
        status_lines = [line.strip() for line in text.splitlines()
                        if line.startswith("STATUS:")]
        auth_lines = [line.strip() for line in text.splitlines()
                      if line.startswith("AUTHORIZATION:")]
        rel = path.relative_to(root).as_posix()
        completed_metadata[path.name] = (status_lines, auth_lines, text)
        if status_lines != ["STATUS: COMPLETED"]:
            add(rel, "completed status", repr(status_lines),
                "exactly STATUS: COMPLETED")
        if auth_lines != [_COMPLETED_NO_SESSION_AUTH]:
            add(rel, "completed authorization", repr(auth_lines),
                f"exactly {_COMPLETED_NO_SESSION_AUTH}")

    wo001_name = "WO-001-custom-mcp-security.md"
    wo001_path = completed_dir / wo001_name
    wo001_completed_text = ""
    if [path.name for path in completed].count(wo001_name) != 1:
        add("docs/work-orders/completed", "completed WO-001 state",
            str([path.name for path in completed]),
            "exactly one WO-001-custom-mcp-security.md")
    else:
        _statuses, _authorizations, wo001_completed_text = completed_metadata[wo001_name]
        rel = wo001_path.relative_to(root).as_posix()
        for evidence, kind in (
            (_WO001_COMPLETION_COMMIT, "completion commit"),
            (_WO001_COMPLETION_WORKFLOW, "completion workflow"),
            (_WO001_COMPLETION_JOB, "completion job"),
        ):
            if evidence not in wo001_completed_text:
                add(rel, kind, "missing", evidence)

    wo002_completed_text = ""
    if _WO002_NAME in completed_metadata:
        wo002_completed_text = completed_metadata[_WO002_NAME][2]

    if current == "NONE":
        if session != "NONE":
            add("WORKORDER.md", "authorization without issued work order",
                str(session), "NONE")
        if issued:
            add("docs/work-orders/issued", "unpointed issued work order",
                issued[0].name, "empty while current pointer is NONE")
        # Whichever Work Order closed last owns the pointer's base and gate.
        if wo002_completed_text:
            next_order, basis_text = "WO-003", wo002_completed_text
            expected_base = _WO002_COMPLETION_COMMIT
            expected_closed_gate = _WO002_COMPLETED_GATE
        else:
            next_order, basis_text = "WO-002", wo001_completed_text
            expected_base = _WO001_COMPLETION_COMMIT
            expected_closed_gate = _WO001_COMPLETED_GATE
        if _has_next_work_order_authorization(pointer, basis_text, next_order):
            add("WORKORDER.md", "next work order authorization",
                f"implicit {next_order} permission",
                f"{next_order} remains proposed and not authorized")
        if base != f"`{expected_base}`":
            add("WORKORDER.md", "completion base commit", str(base),
                f"`{expected_base}`")
        if current_gate != expected_closed_gate:
            add("WORKORDER.md", "completed work order gate", str(current_gate),
                expected_closed_gate)
        if wo002_completed_text:
            rel = (completed_dir / _WO002_NAME).relative_to(root).as_posix()
            for evidence, kind in (
                (_WO002_COMPLETION_COMMIT, "WO-002 completion commit"),
                (_WO002_COMPLETION_WORKFLOW, "WO-002 completion workflow"),
                (_WO002_COMPLETION_JOB, "WO-002 completion job"),
                (_WO002_EVIDENCE_PATH, "WO-002 evidence artifact"),
                (_WO002_EVIDENCE_SHA256, "WO-002 evidence digest"),
            ):
                if evidence not in wo002_completed_text:
                    add(rel, kind, "missing", evidence)
            normalized_wo002 = " ".join(wo002_completed_text.split())
            for wording, kind in (
                (_WO002_TERMINAL_EXTERNAL, "WO-002 terminal external result"),
                (_WO002_NEGATIVE_RESULT, "WO-002 accepted negative result"),
            ):
                if wording not in normalized_wo002:
                    add(rel, kind, "missing or changed", wording)
            # Session A's accepted record outlives the Work Order that carried it.
            for _f, _k, _found, _want in _accepted_record_findings(
                pointer, wo002_completed_text, rel
            ):
                add(_f, _k, _found, _want)
    elif current is not None:
        if len(issued) != 1:
            add("docs/work-orders/issued", "current issued work order",
                str(len(issued)), "exactly one file matching the pointer")
        else:
            issued_id = "-".join(issued[0].stem.split("-")[:2])
            valid_pointers = {issued[0].name, issued[0].stem, issued_id}
            if current not in valid_pointers:
                add("WORKORDER.md", "current issued work order mismatch", current,
                    ", ".join(sorted(valid_pointers)))

            _statuses, auth_lines, issued_text = issued_metadata[issued[0].name]
            if issued[0].name == _WO002_NAME:
                rel = issued[0].relative_to(root).as_posix()
                baseline_lines = [
                    line.strip()
                    for line in issued_text.splitlines()
                    if line.startswith("BASELINE:")
                ]
                if baseline_lines != [_WO002_BASELINE_MARKER]:
                    add(rel, "issuance baseline marker", repr(baseline_lines),
                        f"exactly {_WO002_BASELINE_MARKER}")
                for evidence, kind in (
                    (_WO002_ISSUANCE_BASE, "issuance baseline"),
                    (_WO002_ISSUANCE_WORKFLOW, "issuance workflow"),
                    (_WO002_ISSUANCE_JOB, "issuance job"),
                ):
                    if issued_text.count(evidence) < 1:
                        add(rel, kind, "missing", evidence)
                if "## Session A —" not in issued_text or "## Session B —" not in issued_text:
                    add(rel, "issued session headings", "missing",
                        "Session A and Session B headings")
                if "## Proposed Session A" in issued_text or "## Proposed Session B" in issued_text:
                    add(rel, "issued session headings", "proposal heading remains",
                        "issued Session A and Session B headings")
                issued_link = (
                    "docs/work-orders/issued/WO-002-epic-toolset-integration.md"
                )
                if issued_link not in pointer or (
                    "docs/work-orders/proposed/WO-002-epic-toolset-integration.md"
                    in pointer
                ):
                    add("WORKORDER.md", "WO-002 pointer path", "stale or missing",
                        issued_link)

            if session == "NONE":
                session_a_accepted = issued[0].name == _WO002_NAME and (
                    current_gate == _WO002_SESSION_A_ACCEPTED_GATE
                    or auth_lines == [_ISSUED_SESSION_A_ACCEPTED]
                    or "## Session A acceptance record" in issued_text
                )
                if session_a_accepted:
                    normalized_issued = " ".join(issued_text.split())
                    if auth_lines != [_ISSUED_SESSION_A_ACCEPTED]:
                        add(rel, "Session A accepted authorization",
                            repr(auth_lines),
                            f"exactly {_ISSUED_SESSION_A_ACCEPTED}")
                    if base != f"`{_WO002_SESSION_A_ACCEPTED_BASE}`":
                        add("WORKORDER.md", "Session A accepted base commit",
                            str(base), f"`{_WO002_SESSION_A_ACCEPTED_BASE}`")
                    if current_gate != _WO002_SESSION_A_ACCEPTED_GATE:
                        add("WORKORDER.md", "Session A accepted gate",
                            str(current_gate), _WO002_SESSION_A_ACCEPTED_GATE)
                    for evidence, kind in (
                        (_WO002_SESSION_A_ACCEPTED_BASE,
                         "Session A accepted commit"),
                        (_WO002_SESSION_A_ACCEPTED_WORKFLOW,
                         "Session A accepted workflow"),
                        (_WO002_SESSION_A_ACCEPTED_JOB,
                         "Session A accepted job"),
                    ):
                        if evidence not in pointer or evidence not in issued_text:
                            add(rel, kind,
                                "missing from pointer or issued record", evidence)
                    if _WO002_SESSION_A_ACCEPTED_NEXT_GATE not in normalized_issued:
                        add(rel, "WO-002 next gate", "missing or changed",
                            _WO002_SESSION_A_ACCEPTED_NEXT_GATE)
                    if (
                        "Session A is accepted and complete. No session is currently authorized"
                        not in normalized_issued
                    ):
                        add(rel, "Session A accepted statement", "missing",
                            "Session A complete with no current session authority")
                    if _has_other_session_authorization(pointer, issued_text, ""):
                        add("WORKORDER.md", "session authorization reopening",
                            "positive permission for Session A, Session B, or later",
                            "Session A accepted; no session authorized")
                else:
                    expected_gate = (
                        f"{issued_id} ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED"
                    )
                    if auth_lines != [_ISSUED_NO_SESSION_AUTH]:
                        add(issued[0].relative_to(root).as_posix(),
                            "issued session authorization", repr(auth_lines),
                            f"exactly {_ISSUED_NO_SESSION_AUTH}")
                    if current_gate != expected_gate:
                        add("WORKORDER.md", "closed session gate", str(current_gate),
                            expected_gate)

                    if _has_implicit_session_authorization(
                        pointer, issued_text, expected_gate
                    ):
                        add("WORKORDER.md", "implicit session authorization",
                            "contradictory Session A permission", expected_gate)
                    if issued[0].name == _WO003_NAME:
                        for _f, _k, _found, _want in _wo003_record_findings(
                            pointer, issued_text,
                            issued[0].relative_to(root).as_posix(),
                            base, current_gate, session,
                        ):
                            add(_f, _k, _found, _want)
                    if _has_other_session_authorization(pointer, issued_text, ""):
                        add("WORKORDER.md", "later session authorization",
                            "positive permission for a labeled session",
                            "Session A, Session B, and later sessions remain unauthorized")

                    if issued[0].name == _WO002_NAME:
                        normalized_issued = " ".join(issued_text.split())
                        if base != f"`{_WO002_ISSUANCE_BASE}`":
                            add("WORKORDER.md", "issuance base commit", str(base),
                                f"`{_WO002_ISSUANCE_BASE}`")
                        if current_gate != _WO002_CLOSED_GATE:
                            add("WORKORDER.md", "WO-002 closed gate",
                                str(current_gate), _WO002_CLOSED_GATE)
                        if _WO002_NEXT_GATE not in normalized_issued:
                            add(rel, "WO-002 next gate", "missing or changed",
                                _WO002_NEXT_GATE)
            elif session == "A":
                expected_gate = (
                    f"{issued_id} SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY"
                )
                if auth_lines != [_ISSUED_SESSION_A_AUTH]:
                    add(issued[0].relative_to(root).as_posix(),
                        "issued session authorization", repr(auth_lines),
                        f"exactly {_ISSUED_SESSION_A_AUTH}")
                if current_gate != expected_gate:
                    add("WORKORDER.md", "authorized session gate", str(current_gate),
                        expected_gate)
                if _has_other_session_authorization(pointer, issued_text, session):
                    add("WORKORDER.md", "later session authorization",
                        "positive permission for a non-current session",
                        "only Session A authorized")
                if issued[0].name == _WO003_NAME:
                    wo003_rel = issued[0].relative_to(root).as_posix()
                    for _f, _k, _found, _want in _wo003_record_findings(
                        pointer, issued_text, wo003_rel, base, current_gate,
                        session,
                    ):
                        add(_f, _k, _found, _want)
                    normalized_wo003 = " ".join(issued_text.split())
                    for evidence, kind in (
                        (_WO003_SESSION_A_BASE,
                         "WO-003 Session A authorization commit"),
                        (_WO003_SESSION_A_WORKFLOW,
                         "WO-003 Session A authorization workflow"),
                        (_WO003_SESSION_A_JOB,
                         "WO-003 Session A authorization job"),
                    ):
                        if evidence not in pointer or evidence not in issued_text:
                            add(wo003_rel, kind,
                                "missing from pointer or issued record",
                                evidence)
                    if _WO003_SESSION_A_NEXT_GATE not in normalized_wo003:
                        add(wo003_rel, "WO-003 next gate",
                            "missing or changed", _WO003_SESSION_A_NEXT_GATE)
                    if _WO003_SESSION_A_STATEMENT not in normalized_wo003:
                        add(wo003_rel, "WO-003 Session A authorization statement",
                            "missing",
                            "authorized only under root WORKORDER.md")
                if issued[0].name == _WO002_NAME:
                    normalized_issued = " ".join(issued_text.split())
                    if base != f"`{_WO002_SESSION_A_BASE}`":
                        add("WORKORDER.md", "Session A base commit", str(base),
                            f"`{_WO002_SESSION_A_BASE}`")
                    if current_gate != _WO002_SESSION_A_GATE:
                        add("WORKORDER.md", "WO-002 Session A gate",
                            str(current_gate), _WO002_SESSION_A_GATE)
                    for evidence, kind in (
                        (_WO002_SESSION_A_BASE, "Session A authorization commit"),
                        (_WO002_SESSION_A_WORKFLOW, "Session A authorization workflow"),
                        (_WO002_SESSION_A_JOB, "Session A authorization job"),
                    ):
                        if issued_text.count(evidence) != 1:
                            add(rel, kind, str(issued_text.count(evidence)),
                                f"exactly one {evidence}")
                    if _WO002_SESSION_A_NEXT_GATE not in normalized_issued:
                        add(rel, "WO-002 next gate", "missing or changed",
                            _WO002_SESSION_A_NEXT_GATE)
                    if "Session A is authorized for implementation under the current root" not in normalized_issued:
                        add(rel, "Session A authorization statement", "missing",
                            "authorized only under root WORKORDER.md")
            elif session == "B":
                expected_gate = (
                    f"{issued_id} SESSION B AUTHORIZED "
                    f"{chr(8212)} EXECUTE EXTERNAL PROOF ONLY"
                )
                if auth_lines != [_ISSUED_SESSION_B_AUTH]:
                    add(issued[0].relative_to(root).as_posix(),
                        "issued session authorization", repr(auth_lines),
                        f"exactly {_ISSUED_SESSION_B_AUTH}")
                if current_gate != expected_gate:
                    add("WORKORDER.md", "authorized session gate",
                        str(current_gate), expected_gate)
                if _has_other_session_authorization(pointer, issued_text, session):
                    add("WORKORDER.md", "later session authorization",
                        "positive permission for a non-current session",
                        "only Session B authorized")
                if issued[0].name == _WO003_NAME:
                    add("WORKORDER.md", "WO-003 Session B activation",
                        "Session B authorized in the pointer alone",
                        _WO003_SESSION_B_UNAUTHORIZED)
                if issued[0].name == _WO002_NAME:
                    normalized_issued = " ".join(issued_text.split())
                    if base != f"`{_WO002_SESSION_B_BASE}`":
                        add("WORKORDER.md", "Session B base commit", str(base),
                            f"`{_WO002_SESSION_B_BASE}`")
                    if current_gate != _WO002_SESSION_B_GATE:
                        add("WORKORDER.md", "WO-002 Session B gate",
                            str(current_gate), _WO002_SESSION_B_GATE)
                    for evidence, kind in (
                        (_WO002_SESSION_B_BASE,
                         "Session B authorization commit"),
                        (_WO002_SESSION_B_WORKFLOW,
                         "Session B authorization workflow"),
                        (_WO002_SESSION_B_JOB, "Session B authorization job"),
                    ):
                        if issued_text.count(evidence) != 1:
                            add(rel, kind, str(issued_text.count(evidence)),
                                f"exactly one {evidence}")
                    if _WO002_SESSION_B_NEXT_GATE not in normalized_issued:
                        add(rel, "WO-002 next gate", "missing or changed",
                            _WO002_SESSION_B_NEXT_GATE)
                    if _WO002_SESSION_B_PROOF_ONLY not in normalized_issued:
                        add(rel, "Session B proof-only statement", "missing",
                            _WO002_SESSION_B_PROOF_ONLY)
                    if _has_next_work_order_authorization(
                        pointer, issued_text, "WO-003"
                    ):
                        add("WORKORDER.md", "next work order authorization",
                            "implicit WO-003 permission",
                            "WO-003 remains proposed and not authorized")
            else:
                add("WORKORDER.md", "authorized session gate", str(session),
                    "NONE or the specifically authorized session A or B")

    return findings


def check_mcp_security_contract() -> list[dict]:
    """Keep the compact agent surface aligned with the secured MCP boundary."""
    from pathlib import Path

    path = Path(ROOT) / "llms.txt"
    if not path.exists():
        return [{
            "file": "llms.txt",
            "line": 0,
            "type": "MCP security contract",
            "found": "missing",
            "expected": "authenticated bridge guidance",
            "content": "llms.txt is required",
        }]

    text = " ".join(path.read_text(encoding="utf-8").split())
    required = (
        "authenticated same-user loopback",
        "`mcp_server.py` and `client.py` load the rotating local session handoff automatically",
        "Unauthenticated, browser-originated, and remote-host requests are rejected",
        "Arbitrary remote Python is unavailable",
        "`mcp_start`, `mcp_stop`, and `mcp_restart` are local-only",
        "Epic's official MCP and Toolbelt can coexist",
        "Quirk #36",
        "run `tb.register()` once before `mcp_start`",
    )
    findings: list[dict] = []
    for phrase in required:
        if phrase not in text:
            findings.append({
                "file": "llms.txt",
                "line": 0,
                "type": "MCP security contract",
                "found": f"missing {phrase!r}",
                "expected": "current authenticated local-only guidance",
                "content": phrase,
            })

    forbidden = (
        (r"\bexecute arbitrary Python\b", "execute arbitrary Python"),
        (
            r"\bUEFN_TOOLBELT_MCP_ALLOW_EXECUTE_PYTHON\b",
            "UEFN_TOOLBELT_MCP_ALLOW_EXECUTE_PYTHON",
        ),
        (r"\bany MCP client auto-connects\b", "any MCP client auto-connects"),
        (
            r"\bbrowser-originated requests?\s+(?:are|is)\s+"
            r"(?:accepted|allowed|permitted)\b",
            "browser-originated requests accepted",
        ),
        (
            r"\bunauthenticated requests?\s+(?:are|is)\s+"
            r"(?:accepted|allowed|permitted)\b",
            "unauthenticated requests accepted",
        ),
        (
            r"\barbitrary remote Python\s+(?:is|remains|can be)\s+"
            r"(?:available|enabled|allowed|permitted|supported)\b",
            "arbitrary remote Python available",
        ),
        (
            r"\b`?mcp_(?:start|stop|restart)`?\s+(?:may|can)\s+be\s+"
            r"(?:called|invoked|run)\s+remotely\b",
            "remote listener lifecycle control",
        ),
        (
            r"\b(?:the\s+)?custom bridge\s+(?:is|remains)\s+reachable\s+"
            r"from\s+remote hosts\b|\bremote hosts\s+(?:may|can)\s+reach\s+"
            r"(?:the\s+)?custom bridge\b",
            "custom bridge reachable from remote hosts",
        ),
    )
    for pattern, description in forbidden:
        if re.search(pattern, text, re.IGNORECASE):
            findings.append({
                "file": "llms.txt",
                "line": 0,
                "type": "MCP security contract",
                "found": description,
                "expected": "no stale unauthenticated or arbitrary-execution guidance",
                "content": description,
            })
    return findings


# ── Surface truth contract ───────────────────────────────────────────────────
#
# WO-003 separated four surfaces that the documentation had been running
# together: Epic's built-in official MCP toolsets, Toolbelt's internal
# in-process registry, Toolbelt's custom bridge, and Toolbelt's external
# exposure through Epic's official MCP (which failed). Each assertion below
# protects one named fact from that separation. None of them freezes prose:
# they reject the specific inversion that was true before the correction.

_DASHBOARD_REL = "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py"
# The ninth runtime occurrence, admitted by Amendment 1. Its docstring is the
# only place the runtime itself describes the external official-MCP result.
_EPIC_MCP_TOOLS_REL = "Content/Python/UEFN_Toolbelt/tools/epic_mcp_tools.py"

# The dashboard reads the live registry and falls back to two bare quoted
# literals when that read raises. The count patterns cannot match them - they
# are assignments, not prose - so both went stale unnoticed. This pins that one
# except branch by position rather than broadening the count regexes, which is
# a scanner redesign and belongs to WO-005.
_DASHBOARD_LIVE_READ = (
    '_cat_count = str(len({t.get("category","") for t in '
    '_tb.registry.list_tools() if t.get("category")}))'
)


def _normalized_lines(text: str) -> list[str]:
    """Each line with its whitespace runs collapsed, for exact comparison."""
    return [" ".join(line.split()) for line in text.split("\n")]


def check_dashboard_fallbacks() -> list[dict]:
    """The dashboard's except-branch counts must match the runtime registry."""
    from pathlib import Path

    path = Path(ROOT) / _DASHBOARD_REL
    if not path.exists():
        return [{
            "file": _DASHBOARD_REL, "line": 0,
            "type": "dashboard fallback counts", "found": "missing",
            "expected": "the dashboard module", "content": _DASHBOARD_REL,
        }]
    lines = _normalized_lines(path.read_text(encoding="utf-8"))
    anchors = [i for i, line in enumerate(lines)
               if line == _DASHBOARD_LIVE_READ]
    if len(anchors) != 1:
        return [{
            "file": _DASHBOARD_REL, "line": 0,
            "type": "dashboard fallback counts",
            "found": "the live registry read occurs "
                     + str(len(anchors)) + "x",
            "expected": "exactly one live registry read to anchor the fallback",
            "content": _DASHBOARD_LIVE_READ,
        }]
    # The fallback is identified by sitting immediately after the live read,
    # never by appearing somewhere in the file: a byte-correct copy elsewhere
    # must not stand in for the branch the dashboard actually renders from.
    expected = [
        "except Exception:",
        '_tool_count = "' + str(TOOL_COUNT) + '"',
        '_cat_count = "' + str(CATEGORY_COUNT) + '"',
    ]
    start = anchors[0] + 1
    actual = [line for line in lines[start:start + 8] if line][:len(expected)]
    findings: list[dict] = []
    # actual is deliberately allowed to be short: a truncated fallback branch
    # is reported by the length check below rather than raising here.
    for index, (want, got) in enumerate(zip(expected, actual, strict=False)):
        if want != got:
            findings.append({
                "file": _DASHBOARD_REL, "line": start + index + 1,
                "type": "dashboard fallback counts", "found": got,
                "expected": want, "content": got,
            })
    if len(actual) != len(expected):
        findings.append({
            "file": _DASHBOARD_REL, "line": start + 1,
            "type": "dashboard fallback counts",
            "found": "the fallback branch holds " + str(len(actual)) + " lines",
            "expected": str(len(expected)) + " fallback lines",
            "content": _DASHBOARD_LIVE_READ,
        })
    return findings


# Stale claims WO-003 removed. Each one is a sentence the repository actually
# carried, not a shape it might one day carry, so each probe reproduces a real
# regression rather than an imagined one.
_RETIRED_CLAIMS = (
    # The legacy Python limit stated as a whole-product limit.
    ("Epic must unlock", "official capability described as Epic-locked"),
    ("is locked by Epic", "official capability described as Epic-locked"),
    ("Permanent top-bar menu entry injected on editor startup",
     "top-bar menu described as rendering"),
    ("Waiting for Epic Python compiler API",
     "Verse compilation described as unavailable"),
    # The custom bridge described as universally offline.
    ("fully offline", "Toolbelt described as universally offline"),
    ("Zero outbound HTTP", "Toolbelt described as universally offline"),
    # The top-bar menu described as a working entry point.
    ("appears in the top menu bar", "top-bar menu described as rendering"),
    ("from the top menu bar", "top-bar menu described as rendering"),
    ("in the top menu bar, or", "top-bar menu described as rendering"),
    # The accepted external result softened back to "unproven". Amendment 1
    # admitted the runtime docstring that still carried it.
    ("unproven", "accepted external result softened to unproven"),
    # The absolute project-only file-write guarantee. Four export tools take an
    # explicit path and write wherever the operator points them.
    ("No file writes outside project",
     "file writes described as project-only"),
    ("All output goes to `Saved/UEFN_Toolbelt/` inside your project",
     "file writes described as project-only"),
    # The network counts this Work Order itself got wrong before review:
    # the dashboard's own `toolbelt_update` runs `git pull`, so any total
    # stated so far has been an undercount.
    ("Two features reach the network",
     "network use stated as an exact count"),
    ("network features — Plugin Hub, URL import",
     "network use stated as an exact count"),
    # The restart absolute, in both directions.
    ("You **never need to restart UEFN**", "restart stated as an absolute"),
    ("You don't even need to restart!", "restart stated as an absolute"),
)

# Paths WO-003 corrected. The contributor guideline in README's plugin section
# says "No network calls" about a *plugin author's* tool, which is advice, not
# a claim about Toolbelt - so the phrases above are the ones pinned, not that.
_SURFACE_PATHS = (
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "llms.txt",
    "ARCHITECTURE.md",
    "SECURITY.md",
    "TOOL_STATUS.md",
    "ROADMAP.md",
    "docs/PIPELINE.md",
    "docs/AI_AUTONOMY.md",
    "docs/uefn_python_capabilities.md",
    "docs/plugin_dev_guide.md",
    ".claude/mcp_reference.md",
    ".claude/tool_tables.md",
    _DASHBOARD_REL,
    "launcher.py",
    "install.py",
    _EPIC_MCP_TOOLS_REL,
)

# The accepted WO-002 external result, bound to a stable semantic identity
# outside the protected clause. Markdown sites require the exact clause
# immediately after their path-specific anchor after whitespace folding; the
# Python site requires it in the named function's actual docstring. A complete
# keyed clause transplanted elsewhere therefore cannot repair the claim site,
# while harmless line wrapping remains irrelevant.
#
# (path, stable claim-site anchor, exact material clause after whitespace folding)
_EXTERNAL_RESULT_SITES: tuple[tuple[str, str, str], ...] = (
    (
        "CLAUDE.md",
        "Toolbelt is **not** reachable through Epic's official MCP server:",
        "WO-002 recorded that external result as `failed`, bounded by "
        "`UE::ValkyrieToolset::ToolsetPolicy`",
    ),
    (
        ".claude/tool_tables.md",
        "| `epic_mcp_register` | — | Attempt in-process Toolset Registry "
        "submission.",
        "External exposure through Epic's official MCP server `failed` on "
        "UEFN 42.00, bounded by `UE::ValkyrieToolset::ToolsetPolicy`",
    ),
    (
        ".claude/mcp_reference.md",
        "Toolbelt is not reachable through that server —",
        "WO-002 recorded the external result as `failed`, bounded by "
        "`UE::ValkyrieToolset::ToolsetPolicy`",
    ),
    (
        _EPIC_MCP_TOOLS_REL,
        "run_epic_mcp_status",
        "WO-002 recorded that external result as `failed`, bounded by "
        "`UE::ValkyrieToolset::ToolsetPolicy`",
    ),
)

_QUIRK36_RECOVERY = (
    "**Workaround.** Turn the flag off, or run "
    "`import UEFN_Toolbelt as tb; tb.register()` once per session."
)

# Quirk evidence, bound to the step that makes it useful rather than to the
# section as a whole. Section-wide membership was defeated by planting
# `<!-- tb.register() -->` inside Quirk #36 while deleting the real recovery
# command from its Workaround: the fragment was still 'in the section'.
#
# (section heading, sub-anchor or None, stop prefixes, fragments)
_QUIRK_EVIDENCE: tuple[
    tuple[str, str | None, tuple[str, ...] | None, tuple[str, ...]], ...
] = (
    ("## Quirk #36 " + "—", None, None, ("UEFN MCP Toolsets",)),
    ("## Quirk #42 " + "—", "### Verified workflow", ("## ", "---"),
     ("prepare_launch.bat", "restore_after_launch.bat")),
    ("## Quirk #42 " + "—", None, None,
     ("zero `.py` files anywhere", "ContainsPythonData")),
)


def _strip_python_comments(text: str) -> str:
    """Blank out `#` comments in place, keeping every line number intact."""
    lines = text.split("\n")
    try:
        tokens = list(
            tokenize.generate_tokens(io.StringIO(text).readline)
        )
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        row = token.start[0] - 1
        lines[row] = lines[row][:token.start[1]]
    return "\n".join(lines)


def _strip_markdown_fences(text: str) -> str:
    """Blank fenced blocks while preserving line positions.

    A fenced example can illustrate old or invalid text, but it is not the
    surrounding document making the accepted claim.  This intentionally knows
    only fence delimiters; it does not parse headings, paragraphs, or prose.
    """
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        opening = re.match(r"^\s*(`{3,}|~{3,})", lines[index])
        if opening is None:
            index += 1
            continue
        marker = opening.group(1)
        closing_pattern = re.compile(
            r"^\s*" + re.escape(marker[0]) + "{" + str(len(marker))
            + r",}\s*$"
        )
        closing = next(
            (candidate for candidate in range(index + 1, len(lines))
             if closing_pattern.match(lines[candidate])),
            None,
        )
        # An unclosed delimiter is malformed prose, not a license to hide the
        # rest of the document from required-evidence checks.
        if closing is None:
            index += 1
            continue
        for fenced_line in range(index, closing + 1):
            lines[fenced_line] = ""
        index = closing + 1
    return "\n".join(lines)


def _without_commentary(
    text: str, is_python: bool, *, strip_fences: bool = False
) -> str:
    """Drop commentary that could carry a planted copy of required evidence.

    A fragment inside an HTML or Python comment is not the document making
    the statement; it is a decoy that satisfied a substring search while the
    real statement was deleted. Comment spans are replaced by their own
    newlines so line positions - which the anchors depend on - do not move.
    """
    cleaned = re.sub(
        r"<!--.*?-->",
        lambda match: "\n" * match.group(0).count("\n"),
        text,
        flags=re.DOTALL,
    )
    if is_python:
        return _strip_python_comments(cleaned)
    return _strip_markdown_fences(cleaned) if strip_fences else cleaned


def _anchored_window(lines, anchor, stops):
    """The block opened by a unique anchor line, or why it is unusable."""
    starts = [i for i, line in enumerate(lines)
              if line.strip().startswith(anchor)]
    if len(starts) != 1:
        return None, anchor + " opens " + str(len(starts)) + " blocks"
    start = starts[0]
    if stops is None:
        return lines[start], None
    for index in range(start + 1, len(lines)):
        if lines[index].startswith(stops):
            return "\n".join(lines[start:index]), None
    return "\n".join(lines[start:]), None


def _quirk_section(text: str, heading: str) -> str | None:
    """The body of one quirk section, or None when it is absent or doubled."""
    window, reason = _anchored_window(text.split("\n"), heading, ("## ",))
    return None if reason else window


def check_surface_truth_contract() -> list[dict]:
    """Keep the four MCP surfaces distinct across the corrected documents."""
    from pathlib import Path

    root = Path(ROOT)
    findings: list[dict] = []

    def add(rel, kind, found, expected, content):
        findings.append({
            "file": rel, "line": 0, "type": kind,
            "found": found, "expected": expected, "content": content,
        })

    for rel in _SURFACE_PATHS:
        path = root / rel
        if not path.exists():
            add(rel, "surface truth target", "absent",
                "a committed file at " + rel, rel)
            continue
        text = path.read_text(encoding="utf-8")
        for claim, kind in _RETIRED_CLAIMS:
            if claim in text:
                add(rel, "retired claim", kind,
                    "the corrected WO-003 wording", claim)

    for rel, site_anchor, expected_clause in _EXTERNAL_RESULT_SITES:
        path = root / rel
        if not path.exists():
            continue
        is_python = rel.endswith(".py")
        source = path.read_text(encoding="utf-8")
        if is_python:
            active_python = _without_commentary(source, True)
            active_prose = " ".join(active_python.split())
            clause_count = active_prose.count(expected_clause)
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                add(rel, "accepted external result", "invalid Python source",
                    "one function named " + site_anchor
                    + " with the accepted result in its docstring",
                    str(exc))
                continue
            functions = [
                node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == site_anchor
            ]
            docstring = (
                "" if len(functions) != 1
                else ast.get_docstring(functions[0], clean=True) or ""
            )
            normalized_docstring = " ".join(docstring.split())
            if (len(functions) != 1
                    or expected_clause not in normalized_docstring
                    or clause_count != 1):
                add(rel, "accepted external result",
                    "the function anchor occurs " + str(len(functions))
                    + "x, the clause occurs " + str(clause_count)
                    + "x, or its docstring lacks the accepted result and bound",
                    "one function named " + site_anchor
                    + " whose docstring contains: " + expected_clause,
                    site_anchor)
            continue

        active_source = _without_commentary(
            source, False, strip_fences=True
        )
        prose = " ".join(active_source.split())
        anchor_count = prose.count(site_anchor)
        anchored_claim = site_anchor + " " + expected_clause
        anchored_count = prose.count(anchored_claim)
        clause_count = prose.count(expected_clause)
        if (anchor_count != 1 or anchored_count != 1
                or clause_count != 1):
            add(rel, "accepted external result",
                "the semantic anchor occurs " + str(anchor_count)
                + "x, carries the exact claim " + str(anchored_count)
                + "x, and the clause occurs " + str(clause_count) + "x",
                "one active anchored claim: " + anchored_claim,
                site_anchor)

    quirks_rel = "docs/UEFN_QUIRKS.md"
    quirks_path = root / quirks_rel
    if not quirks_path.exists():
        add(quirks_rel, "preserved quirk", "absent",
            "a committed file at " + quirks_rel, quirks_rel)
    else:
        quirks_source = quirks_path.read_text(encoding="utf-8")
        quirks = _without_commentary(quirks_source, False)
        quirks_without_fences = _without_commentary(
            quirks_source, False, strip_fences=True
        )
        quirk36 = _quirk_section(
            quirks_without_fences, "## Quirk #36 " + "—"
        )
        if quirk36 is not None:
            recovery, reason = _anchored_window(
                quirk36.split("\n"), "**Workaround.**",
                ("**", "---", "## "),
            )
            normalized_recovery = (
                "" if recovery is None else " ".join(recovery.split())
            )
            if reason or normalized_recovery != _QUIRK36_RECOVERY:
                add(quirks_rel, "preserved quirk",
                    reason or "the Workaround is missing or wrapped",
                    _QUIRK36_RECOVERY, "Quirk #36 / **Workaround.**")
        for heading, sub_anchor, stops, fragments in _QUIRK_EVIDENCE:
            section = _quirk_section(quirks, heading)
            if section is None:
                add(quirks_rel, "preserved quirk",
                    "no single section headed " + heading,
                    "exactly one " + heading + " section", heading)
                continue
            where = heading
            if sub_anchor is not None:
                window, reason = _anchored_window(
                    section.split("\n"), sub_anchor, stops
                )
                if reason:
                    add(quirks_rel, "preserved quirk", reason,
                        "exactly one " + sub_anchor + " block inside "
                        + heading, sub_anchor)
                    continue
                section, where = window, heading + " / " + sub_anchor
            for fragment in fragments:
                if fragment not in section:
                    add(quirks_rel, "preserved quirk",
                        "missing from " + where + ": " + fragment,
                        "the accepted quirk evidence, intact", fragment)

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
    "was removed in v",  # launcher.py names the release a helper was removed
                         # in. Bumping it would make the sentence false.
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
        # A declared target that vanished is drift, not clean input.
        # Returning [] here let a stale SCAN_FILES entry sit unnoticed after
        # WO-002 moved out of issued/. That document stayed scanned via the
        # work-order walk in run(), so nothing lost coverage - but the
        # declaration itself was wrong and no check could say so.
        return [{
            "file":     rel_path,
            "line":     0,
            "type":     "missing scan target",
            "found":    "absent",
            "expected": "a committed file at " + rel_path,
            "content":  rel_path,
        }]

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
    all_findings.extend(check_mcp_security_contract())
    all_findings.extend(check_dashboard_fallbacks())
    all_findings.extend(check_surface_truth_contract())

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
