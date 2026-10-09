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
import hashlib
import io
import os
import re
import sys
import tokenize
from typing import NamedTuple

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
    "docs/OFFICIAL_MCP_AND_TOOLBELT.md",
    "docs/audits/2026-08-24-uefn-42-official-mcp-audit.md",
    "docs/audits/2026-09-10-wo004-session-a-modal-feasibility.md",
    "docs/audits/evidence/2026-08-24-official-mcp-signatures.json",
    "docs/work-orders/README.md",
    "docs/work-orders/completed/WO-001-custom-mcp-security.md",
    "docs/work-orders/completed/WO-002-epic-toolset-integration.md",
    "docs/work-orders/completed/WO-003-official-mcp-doc-convergence.md",
    "docs/work-orders/completed/WO-004-modal-observability.md",
    "docs/work-orders/completed/WO-005-coverage-source-of-truth.md",
    "docs/work-orders/superseded/WO-006-official-vs-toolbelt-benchmark.md",
    "docs/work-orders/completed/WO-007-public-mcp-explainer.md",
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
_ISSUED_SESSION_B_DRAFT_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION B AUTHORIZED FOR DRAFTING ONLY"
)
_ISSUED_SESSION_B_ACCEPTED = (
    "AUTHORIZATION: ISSUED — SESSION B ACCEPTED; NO SESSION AUTHORIZED"
)
_ISSUED_DESCRIPTION_APPLIED = (
    "AUTHORIZATION: ISSUED — DESCRIPTION APPLIED; NO SESSION AUTHORIZED"
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
_WO003_SESSION_A_ACCEPTED_BASE = "d23add58e02ddc855573cf9be7a2542776d25e7e"
_WO003_SESSION_A_ACCEPTED_WORKFLOW = "33344006899"
_WO003_SESSION_A_ACCEPTED_JOB = "99344607213"
_WO003_SESSION_A_ACCEPTED_GATE = (
    "WO-003 SESSION A ACCEPTED — SESSION B NOT AUTHORIZED"
)
_WO003_SESSION_A_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted "
    "Session A implementation. Session B remains unauthorized."
)
_WO003_SESSION_A_STATEMENT = (
    "Session A is authorized for implementation under the current root"
)
_WO003_SESSION_A_ACCEPTED_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted "
    "Session A acceptance transition. Session B remains unauthorized."
)
_WO003_SESSION_A_ACCEPTED_STATEMENT = (
    "At the Session A acceptance gate, Session A was accepted and complete with "
    "no current implementation authority; Session B was not authorized pending "
    "separate owner authorization."
)
_WO003_SESSION_B_BASE = "2582be8c9168d72b46846334bbba44307d348ce6"
_WO003_SESSION_B_WORKFLOW = "33351157691"
_WO003_SESSION_B_JOB = "99364656646"
_WO003_SESSION_B_GATE = (
    "WO-003 SESSION B AUTHORIZED — DRAFT REPOSITORY DESCRIPTION ONLY"
)
_WO003_SESSION_B_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted "
    "Session B repository-description draft. The draft is not applied, and "
    "metadata application remains unauthorized."
)
_WO003_SESSION_B_STATEMENT = (
    "Session B is authorized for repository-description drafting only. Metadata "
    "application, Session C or any later session, WO-004, tagging, Release "
    "creation, and social publication remain unauthorized."
)
_WO003_SESSION_B_POINTER_STATEMENT = (
    "Session B is authorized under this pointer for repository-description "
    "drafting only, on the basis of commit `" + _WO003_SESSION_B_BASE
    + "`, successful CI workflow `" + _WO003_SESSION_B_WORKFLOW
    + "`, and successful required job `" + _WO003_SESSION_B_JOB
    + "` (`Lint, types, tests`). No repository metadata application, tag, "
    "Release, or social publication is authorized."
)
_WO003_SESSION_B_ACCEPTED_BASE = "e23baa40c4b9358eb6b4448f460c054650ae64f0"
_WO003_SESSION_B_ACCEPTED_WORKFLOW = "33476969423"
_WO003_SESSION_B_ACCEPTED_JOB = "99758148278"
_WO003_SESSION_B_ACCEPTED_GATE = (
    "WO-003 SESSION B ACCEPTED — REPOSITORY DESCRIPTION APPLICATION NOT "
    "AUTHORIZED"
)
_WO003_SESSION_B_ACCEPTED_NEXT_GATE = (
    "NEXT GATE: separate BDFL/owner authorization to apply the exact accepted "
    "repository description. Metadata application remains unauthorized until "
    "that explicit gate."
)
_WO003_SESSION_B_ACCEPTED_STATEMENT = (
    "This Work Order remains issued. Session A is accepted and complete. "
    "Session B is accepted and complete. Repository-description application, "
    "Session C or any later session, WO-004, tagging, Release creation, and "
    "social publication remain unauthorized."
)
# The pointer records the acceptance and, in the same breath, that nothing
# external happened. It is pinned exactly and removed before the
# external-action scan below, exactly as the drafting statement was.
_WO003_SESSION_B_ACCEPTED_POINTER_STATEMENT = (
    "Session B's repository-description draft was independently accepted. The "
    "accepted draft was committed and pushed as `"
    + _WO003_SESSION_B_ACCEPTED_BASE + "`; successful CI workflow `"
    + _WO003_SESSION_B_ACCEPTED_WORKFLOW
    + "` included successful required job `"
    + _WO003_SESSION_B_ACCEPTED_JOB + "` (`Lint, types, tests`). The live "
    "GitHub repository description is unchanged. Applying the exact accepted "
    "repository description remains a separate owner-authorized external "
    "action. Metadata application, tags, Releases, and social publication all "
    "remain unauthorized, as do Session C and WO-004."
)
_WO003_PRE_APPLICATION_DESCRIPTION = (
    "The ultimate, ever-expanding Swiss Army Knife for the UEFN Python API "
    "(358+ tools registered across 55+ categories). Automate world-building, "
    "manage assets, generate boilerplate Verse code, and control the editor "
    "with AI via a fully-offline PySide6 dashboard."
)
_WO003_DESCRIPTION_DRAFT = (
    "UEFN Toolbelt: 362 Python automation tools across 55 categories, with a "
    "PySide6 dashboard and an experimental, authenticated same-user loopback "
    "bridge for local AI control. Complements Epic's official UEFN MCP; "
    "Toolbelt is not exposed through Epic's MCP server."
)
_WO003_DESCRIPTION_DRAFT_LENGTH = 261
# Applying the accepted description is the next one-way transition. The
# applied value IS the accepted draft, so it is reused rather than restated;
# only the digest, the live read-back, and the unchanged non-description
# metadata are new facts. No canonical metadata field is added: the pointer
# and issued slices carry no new declaration, and the base commit and gate
# below are checked by the same _wo003_record_findings comparison every
# earlier transition used.
_WO003_APPLIED_BASE = "624ccc7f8f28cc897ec580c660607524ad5a4a3d"
_WO003_APPLIED_DESCRIPTION = _WO003_DESCRIPTION_DRAFT
_WO003_APPLIED_DESCRIPTION_SHA256 = (
    "a2d3b9a40e187c1fc4bce18666e3095687cc94b45d10ab27f1bee1e1e3417415"
)
_WO003_APPLIED_GATE = (
    "WO-003 REPOSITORY DESCRIPTION APPLIED — COMPLETION NOT AUTHORIZED"
)
_WO003_APPLIED_NEXT_GATE = (
    "NEXT GATE: separate BDFL/owner authorization for the WO-003 completion "
    "transition. WO-003 remains issued; WO-004 remains proposed and "
    "unauthorized."
)
_WO003_APPLIED_STATEMENT = (
    "This Work Order remains issued. Session A is accepted and complete. "
    "Session B is accepted and complete. The exact accepted repository "
    "description has been applied under separate owner authorization. WO-003 "
    "completion, Session C or any later session, WO-004, tagging, Release "
    "creation, branch-protection changes, other repository metadata changes, "
    "and social publication remain unauthorized."
)
# The pointer's Session B acceptance paragraph keeps every accepted
# identifier and now states, in the past tense, what was true at that gate.
_WO003_PRE_APPLICATION_POINTER_STATEMENT = (
    "Session B's repository-description draft was independently accepted. The "
    "accepted draft was committed and pushed as `"
    + _WO003_SESSION_B_ACCEPTED_BASE + "`; successful CI workflow `"
    + _WO003_SESSION_B_ACCEPTED_WORKFLOW
    + "` included successful required job `"
    + _WO003_SESSION_B_ACCEPTED_JOB + "` (`Lint, types, tests`). At that gate "
    "the live GitHub repository description was still unchanged, applying the "
    "exact accepted repository description was still a separate "
    "owner-authorized external action, and metadata application was not "
    "authorized. Tags, Releases, and social publication remain unauthorized, "
    "as do Session C and WO-004."
)
# The applied record. Like the drafting and acceptance statements before it,
# it is the statement this gate is allowed to make, so it is removed once
# before the positive-permission scans rather than parsed by them.
# The applied facts themselves - value, count, digest, live read-back, and the
# unchanged non-description metadata - are identical before and after
# completion. Only the closing sentence moves to the past tense, so the facts
# are defined once and both gates' statements are built from them. That is what
# keeps the pointer's copy of the applied description enforced after
# completion, not just the completed document's copy.
_WO003_APPLIED_POINTER_FACTS = (
    "The exact accepted repository description was applied to the live GitHub "
    "repository under separate BDFL/owner authorization, at repository commit "
    "`" + _WO003_APPLIED_BASE + "`. The applied value is exactly `"
    + _WO003_APPLIED_DESCRIPTION + "` Its character count is `"
    + str(_WO003_DESCRIPTION_DRAFT_LENGTH) + "` and its SHA-256 is `"
    + _WO003_APPLIED_DESCRIPTION_SHA256 + "`; a read-only `gh repo view` "
    "read-back returned the applied value byte for byte. The homepage "
    "`https://www.fortnite.com/@ohshh`, PUBLIC visibility, archived state "
    "`false`, and all 20 repository topics are unchanged. No file, commit, "
    "push, tag, Release, branch-protection setting, other repository "
    "metadata, or social state changed."
)
_WO003_APPLIED_POINTER_STATEMENT = (
    _WO003_APPLIED_POINTER_FACTS + " WO-003 remains issued, and its "
    "completion transition requires a separate owner gate. Session C, WO-004, "
    "tagging, Release creation, branch-protection changes, other repository "
    "metadata changes, and social publication all remain unauthorized."
)
_WO003_COMPLETED_APPLIED_POINTER_STATEMENT = (
    _WO003_APPLIED_POINTER_FACTS + " At that gate WO-003 remained issued, and "
    "its completion transition required a separate owner gate."
)
# Completion is the next one-way transition after application. The applied
# description facts outlive the Work Order that carried them: the application
# record moves into the completed document and
# _wo003_application_record_findings still enforces it there, so completing
# WO-003 records the transition without relaxing any earlier pin.
_WO003_COMPLETION_COMMIT = "7a7eedb493cbf810f758383a1fc66a285bca841a"
_WO003_COMPLETION_WORKFLOW = "34301244038"
_WO003_COMPLETION_JOB = "102308406590"
_WO003_COMPLETED_GATE = (
    "WO-003 COMPLETED — WO-004 PROPOSED AND NOT AUTHORIZED"
)
_WO003_COMPLETED_STATEMENT = (
    "WO-003 is complete; no session is authorized. WO-004 remains proposed "
    "and unauthorized."
)
# The completed document is a frozen record of what was true at its own
# gate, so it keeps the clause about WO-004's state. The root pointer is
# the LIVE authority surface, and there that clause goes stale the moment
# WO-004 is issued: it would assert, in the present tense, that the
# currently issued Work Order is still a proposal - and pinning it here
# would make correcting the pointer fail this very gate. Issuing WO-003
# dropped the identical clause about WO-003 from the pointer (`52d8929`);
# this is the same deletion, one order later.
_WO003_COMPLETED_POINTER_CLAUSE = (
    "WO-003 is complete; no session is authorized."
)
_WO003_COMPLETED_NEXT_GATE = (
    "NEXT GATE: separate owner authorization for a fresh independent WO-004 "
    "pre-issuance review, after this completion transition is accepted, "
    "committed, pushed, and green. Completion of WO-003 does not issue or "
    "authorize WO-004, which remains proposed and unauthorized."
)
_WO003_COMPLETION_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO003_COMPLETION_WORKFLOW
)
_WO003_COMPLETION_JOB_URL = (
    _WO003_COMPLETION_RUN_URL + "/job/" + _WO003_COMPLETION_JOB
)
_WO003_COMPLETION_POINTER_STATEMENT = (
    "WO-003 is completed as `" + _WO003_COMPLETION_COMMIT + "`; [CI workflow "
    "`" + _WO003_COMPLETION_WORKFLOW + "`](" + _WO003_COMPLETION_RUN_URL
    + ") completed successfully, including required job [`"
    + _WO003_COMPLETION_JOB + "` — Lint, types, tests]("
    + _WO003_COMPLETION_JOB_URL + "). The repository-description application "
    "record is preserved and still enforced from the completed Work Order "
    "document. " + _WO003_COMPLETED_POINTER_CLAUSE + " Session C or any "
    "later "
    "session, tagging, Release creation, branch-protection changes, other "
    "repository metadata changes, and social publication all remain "
    "unauthorized."
)
# The completion record is bounded by its two neighbouring headings, exactly
# as the application record beside it is. Presence-only checking would let a
# correct copy elsewhere in the file - an HTML comment, a relocated section -
# satisfy a falsified record.
_WO003_COMPLETION_HEADING = "## WO-003 completion record"
_WO003_BOUNDARIES_HEADING = "## Boundaries with WO-004 through WO-007"
_WO003_STOP_HEADING = "## Authority stop boundaries"
_WO003_COMPLETION_RECORD = (
    _WO003_COMPLETION_HEADING + " WO-003 is completed. The "
    "repository-description application record above was committed and pushed "
    "as `" + _WO003_COMPLETION_COMMIT + "`; CI workflow [`"
    + _WO003_COMPLETION_WORKFLOW + "`](" + _WO003_COMPLETION_RUN_URL
    + ") completed successfully, including required job [`"
    + _WO003_COMPLETION_JOB + "` — Lint, types, tests]("
    + _WO003_COMPLETION_JOB_URL + "). Session A converged repository "
    "documentation truth across the row table above and is accepted and "
    "complete. Session B drafted exactly one replacement repository "
    "description and is accepted and complete. The exact accepted description "
    "was applied to the live GitHub repository under separate owner "
    "authorization, and that application record remains enforced from this "
    "completed document rather than relaxed by completion. "
    + _WO003_COMPLETED_STATEMENT
)
_WO003_COMPLETION_EVIDENCE = (
    ("completion commit", "`" + _WO003_COMPLETION_COMMIT + "`"),
    ("completion workflow",
     "[`" + _WO003_COMPLETION_WORKFLOW + "`](" + _WO003_COMPLETION_RUN_URL
     + ")"),
    ("completion job",
     "[`" + _WO003_COMPLETION_JOB + "` — Lint, types, tests]("
     + _WO003_COMPLETION_JOB_URL + ")"),
    ("completion statement", _WO003_COMPLETED_STATEMENT),
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
_WO003_SESSION_A_ACCEPTED_ISSUED_SEQUENCE = (
    _WO003_SESSION_A_ISSUED_SEQUENCE + (
        "SESSION_A_ACCEPTANCE_COMMIT: `"
        + _WO003_SESSION_A_ACCEPTED_BASE + "`",
        "SESSION_A_ACCEPTANCE_CI_WORKFLOW: `"
        + _WO003_SESSION_A_ACCEPTED_WORKFLOW + "`",
        "SESSION_A_ACCEPTANCE_CI_JOB: `"
        + _WO003_SESSION_A_ACCEPTED_JOB + "` — Lint, types, tests",
    )
)
_WO003_SESSION_A_ACCEPTED_POINTER_SEQUENCE = (
    _WO003_SESSION_A_POINTER_SEQUENCE[:-2] + (
        "- Session A acceptance commit: `"
        + _WO003_SESSION_A_ACCEPTED_BASE + "`",
        "- Session A acceptance CI workflow: `"
        + _WO003_SESSION_A_ACCEPTED_WORKFLOW + "`",
        "- Session A acceptance CI job: `"
        + _WO003_SESSION_A_ACCEPTED_JOB + "` — Lint, types, tests",
    ) + _WO003_SESSION_A_POINTER_SEQUENCE[-2:]
)
_WO003_SESSION_B_ISSUED_SEQUENCE = (
    _WO003_SESSION_A_ACCEPTED_ISSUED_SEQUENCE + (
        "SESSION_B_AUTHORIZATION_COMMIT: `" + _WO003_SESSION_B_BASE + "`",
        "SESSION_B_AUTHORIZATION_CI_WORKFLOW: `"
        + _WO003_SESSION_B_WORKFLOW + "`",
        "SESSION_B_AUTHORIZATION_CI_JOB: `" + _WO003_SESSION_B_JOB
        + "` — Lint, types, tests",
    )
)
_WO003_SESSION_B_POINTER_SEQUENCE = (
    _WO003_SESSION_A_ACCEPTED_POINTER_SEQUENCE[:-2] + (
        "- Session B authorization commit: `" + _WO003_SESSION_B_BASE + "`",
        "- Session B authorization CI workflow: `"
        + _WO003_SESSION_B_WORKFLOW + "`",
        "- Session B authorization CI job: `" + _WO003_SESSION_B_JOB
        + "` — Lint, types, tests",
    ) + _WO003_SESSION_A_ACCEPTED_POINTER_SEQUENCE[-2:]
)
# Accepting Session B adds three more declarations to each canonical
# block. The slice stays exact and terminal, so neither the issuance nor
# any earlier session record can be dropped, reordered, or padded on the
# way through this transition either.
_WO003_SESSION_B_ACCEPTED_ISSUED_SEQUENCE = (
    _WO003_SESSION_B_ISSUED_SEQUENCE + (
        "SESSION_B_ACCEPTANCE_COMMIT: `"
        + _WO003_SESSION_B_ACCEPTED_BASE + "`",
        "SESSION_B_ACCEPTANCE_CI_WORKFLOW: `"
        + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`",
        "SESSION_B_ACCEPTANCE_CI_JOB: `"
        + _WO003_SESSION_B_ACCEPTED_JOB + "` — Lint, types, tests",
    )
)
_WO003_SESSION_B_ACCEPTED_POINTER_SEQUENCE = (
    _WO003_SESSION_B_POINTER_SEQUENCE[:-2] + (
        "- Session B acceptance commit: `"
        + _WO003_SESSION_B_ACCEPTED_BASE + "`",
        "- Session B acceptance CI workflow: `"
        + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`",
        "- Session B acceptance CI job: `"
        + _WO003_SESSION_B_ACCEPTED_JOB + "` — Lint, types, tests",
    ) + _WO003_SESSION_B_POINTER_SEQUENCE[-2:]
)


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


def _canonical_field_findings(text, sequence, stop, where, exact, terminal,
                              label="WO-003 issuance field"):
    """The canonical metadata as an exact contiguous slice.

    Enumerating wrapper syntax was a blacklist: an unlisted wrapper such as
    <details> still let a byte-correct field stand in for the declaration, and
    an ordering-only check still permitted arbitrary lines between fields. The
    slice must therefore *equal* the expected sequence with nothing between its
    entries, so any inserted line - wrapper, note, or otherwise - breaks it
    without the checker needing to know what that line means.
    """
    label = label + " (" + where + ")"

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


def _canonical_key_findings(text, stop, keys, label):
    """Each canonical key is declared exactly once, and only there.

    The exact-slice comparison above proves that the declarations it finds
    are right, contiguous, and terminal. It cannot see a corrupted twin
    sitting BEFORE the slice: a wrong BASELINE line followed by a
    byte-correct one leaves the slice intact and the corruption in the
    file. Counting keys inside the canonical block closes that, and
    counting the exact declaration across the whole document stops a
    correct copy placed elsewhere - prose, a comment, a relocated section
    - from standing in for a missing or corrupted one.
    """
    out = []
    block = _canonical_metadata(text, stop)
    for prefix, declaration in keys:
        declared = [line for line in block if line.startswith(prefix)]
        if len(declared) != 1:
            out.append((label,
                        prefix + " is declared " + str(len(declared))
                        + "x in the canonical block",
                        "exactly one canonical " + prefix))
        occurrences = text.count(declaration)
        if occurrences != 1:
            out.append((label,
                        declaration + " occurs " + str(occurrences) + "x",
                        "exactly one " + declaration))
    return out


def _wo003_record_findings(
    pointer, issued_text, wo003_rel, base, current_gate, session,
    surface="both",
):
    """WO-003 issuance evidence survives the Session A transition.

    Authorizing a session must not silence the record that issued it, so
    the same exact-slice comparison runs from every session branch rather
    than living inside the closed-session one. The authorized state adds
    three declarations to each canonical block; the slice stays exact and
    terminal, so the issuance fields cannot be dropped, reordered, or
    padded on the way through.
    """
    if surface not in ("both", "pointer", "document"):
        raise ValueError("unknown surface: " + repr(surface))
    out = []
    issued_sequence: tuple[str, ...]
    pointer_sequence: tuple[str, ...]
    if session == "COMPLETED":
        # Completion adds no canonical declaration either, so the same
        # accepted slices are reused again: every provenance bullet the
        # applied gate pinned stays pinned once WO-003 is completed. Only the
        # base and gate move.
        expected_base = _WO003_COMPLETION_COMMIT
        expected_gate = _WO003_COMPLETED_GATE
        issued_sequence = _WO003_SESSION_B_ACCEPTED_ISSUED_SEQUENCE
        pointer_sequence = _WO003_SESSION_B_ACCEPTED_POINTER_SEQUENCE
        base_kind = "WO-003 completion base commit"
        gate_kind = "WO-003 completed gate"
    elif session == "APPLIED":
        # Applying the description adds no canonical declaration, so the
        # accepted slices are reused unchanged; only the base and gate move.
        expected_base = _WO003_APPLIED_BASE
        expected_gate = _WO003_APPLIED_GATE
        issued_sequence = _WO003_SESSION_B_ACCEPTED_ISSUED_SEQUENCE
        pointer_sequence = _WO003_SESSION_B_ACCEPTED_POINTER_SEQUENCE
        base_kind = "WO-003 applied base commit"
        gate_kind = "WO-003 applied gate"
    elif session == "B_ACCEPTED":
        expected_base = _WO003_SESSION_B_ACCEPTED_BASE
        expected_gate = _WO003_SESSION_B_ACCEPTED_GATE
        issued_sequence = _WO003_SESSION_B_ACCEPTED_ISSUED_SEQUENCE
        pointer_sequence = _WO003_SESSION_B_ACCEPTED_POINTER_SEQUENCE
        base_kind = "WO-003 Session B accepted base commit"
        gate_kind = "WO-003 Session B accepted gate"
    elif session == "B":
        expected_base = _WO003_SESSION_B_BASE
        expected_gate = _WO003_SESSION_B_GATE
        issued_sequence = _WO003_SESSION_B_ISSUED_SEQUENCE
        pointer_sequence = _WO003_SESSION_B_POINTER_SEQUENCE
        base_kind = "WO-003 Session B base commit"
        gate_kind = "WO-003 Session B gate"
    elif session == "ACCEPTED":
        expected_base = _WO003_SESSION_A_ACCEPTED_BASE
        expected_gate = _WO003_SESSION_A_ACCEPTED_GATE
        issued_sequence = _WO003_SESSION_A_ACCEPTED_ISSUED_SEQUENCE
        pointer_sequence = _WO003_SESSION_A_ACCEPTED_POINTER_SEQUENCE
        base_kind = "WO-003 Session A accepted base commit"
        gate_kind = "WO-003 Session A accepted gate"
    elif session == "A":
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
    # `surface` separates the two halves. The base, gate, and canonical
    # pointer slice describe the ROOT POINTER and are only meaningful while
    # WO-003 owns it. The baseline marker and the canonical issued slice
    # describe the WORK ORDER DOCUMENT and must keep being checked after a
    # later order takes the pointer over.
    if surface in ("both", "pointer"):
        if base != "`" + expected_base + "`":
            out.append(("WORKORDER.md", base_kind, str(base),
                        "`" + expected_base + "`"))
        if current_gate != expected_gate:
            out.append(("WORKORDER.md", gate_kind, str(current_gate),
                        expected_gate))
        for kind, found_detail, want in _canonical_field_findings(
            pointer, pointer_sequence,
            lambda line: _WO001_COMPLETED_LINK in line,
            "WORKORDER.md",
            exact={item for item in pointer_sequence if "`" in item},
            terminal=True,
        ):
            out.append(("WORKORDER.md", kind, found_detail, want))
    if surface in ("both", "document"):
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
        for kind, found_detail, want in _canonical_field_findings(
            issued_text, issued_sequence,
            lambda line: line.startswith("## "),
            "issued record",
            exact={item for item in issued_sequence if "`" in item},
            terminal=True,
        ):
            out.append((wo003_rel, kind, found_detail, want))
    return out


_WO003_AUTHORIZATION_HEADING = "## Session A authorization basis"
_WO003_ACCEPTANCE_HEADING = "## Session A acceptance record"
_WO003_SESSION_B_HEADING = "## Session B authorization and draft record"
_WO003_SESSION_B_ACCEPTANCE_HEADING = "## Session B acceptance record"
_WO003_PLANNING_HEADING = "## Planning basis"
_WO003_ACCEPTED_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO003_SESSION_A_ACCEPTED_WORKFLOW
)
_WO003_ACCEPTED_JOB_URL = (
    _WO003_ACCEPTED_RUN_URL + "/job/" + _WO003_SESSION_A_ACCEPTED_JOB
)
_WO003_ACCEPTANCE_RECORD = (
    "## Session A acceptance record Session A was independently accepted and "
    "committed as `" + _WO003_SESSION_A_ACCEPTED_BASE + "`. CI workflow "
    "[`" + _WO003_SESSION_A_ACCEPTED_WORKFLOW + "`]("
    + _WO003_ACCEPTED_RUN_URL + ") completed successfully, including required "
    "job [`" + _WO003_SESSION_A_ACCEPTED_JOB + "` — Lint, types, tests]("
    + _WO003_ACCEPTED_JOB_URL + "). Accepted live `TOOL_TEST` evidence recorded "
    "a deploy and full UEFN restart; 362 tools across 55 categories; corrected "
    "dashboard About ordering; matching source and deployed runtime hashes; no "
    "Fortnite session, play session, or level mutation; then a stopped listener, "
    "closed UEFN, absent handoff, and closed ports 8765–8770. "
    + _WO003_SESSION_A_ACCEPTED_STATEMENT
)


def _wo003_anchored_section(text, required):
    """The middle section of three consecutive headings, or why not.

    Returns ``(region, reason)``. The region is the whitespace-normalized
    block at the anchored position; ``reason`` names the structural failure
    when there is no such position. Locating a record by the structure
    around it - never by anything inside it - is what makes a byte-correct
    transplant elsewhere fail: the anchored position still holds the
    corrupted text.
    """
    lines = text.split("\n")
    marks = [i for i, line in enumerate(lines) if line.startswith("## ")]
    headings = [lines[index] for index in marks]
    for heading in required:
        occurrences = headings.count(heading)
        if occurrences != 1:
            return None, (
                heading + " occurs " + str(occurrences)
                + "x, expected exactly 1"
            )
    first = headings.index(required[0])
    if (first + 2 >= len(headings)
            or headings[first:first + 3] != list(required)):
        return None, (
            "the headings " + ", ".join(required)
            + " are not consecutive and ordered"
        )
    block = lines[marks[first + 1]:marks[first + 2]]
    return " ".join("\n".join(block).split()), None


def _wo003_acceptance_record_findings(
    text, following_heading=_WO003_PLANNING_HEADING
):
    """Check only the structurally located Session A acceptance evidence."""
    region, reason = _wo003_anchored_section(
        text,
        (_WO003_AUTHORIZATION_HEADING, _WO003_ACCEPTANCE_HEADING,
         following_heading),
    )
    if region is None:
        return [("WO-003 Session A acceptance record", reason,
                 "one structurally anchored Session A acceptance record")]
    if region != _WO003_ACCEPTANCE_RECORD:
        return [("WO-003 Session A acceptance record",
                 "the bounded acceptance record changed",
                 "the exact accepted commit, CI, and live evidence record")]
    return []


_WO003_PRE_APPLICATION_DESCRIPTION_FIELD = (
    "PRE_APPLICATION_LIVE_DESCRIPTION_HISTORICAL_SNAPSHOT: `"
    + _WO003_PRE_APPLICATION_DESCRIPTION + "`"
)
_WO003_DRAFT_FIELD_PREFIX = (
    "PRE_APPLICATION_PROPOSED_DESCRIPTION_HISTORICAL_SNAPSHOT: `"
)
_WO003_DRAFT_FIELD = _WO003_DRAFT_FIELD_PREFIX + _WO003_DESCRIPTION_DRAFT + "`"
_WO003_DRAFT_COUNT_FIELD = (
    "PROPOSED_DESCRIPTION_CHARACTER_COUNT: `"
    + str(_WO003_DESCRIPTION_DRAFT_LENGTH) + "`"
)
_WO003_SESSION_B_RECORD = (
    "## Session B authorization and draft record HISTORICAL "
    "PRE-APPLICATION SNAPSHOT. Every value in this section records the "
    "state at the Session B drafting gate, before the accepted description "
    "was applied. It does not describe the current live repository. "
    "Session B is authorized for repository-description drafting only "
    "under the current root `WORKORDER.md` gate. The recorded basis is "
    "commit `" + _WO003_SESSION_B_BASE
    + "`, successful CI workflow `" + _WO003_SESSION_B_WORKFLOW
    + "`, and successful required job `" + _WO003_SESSION_B_JOB
    + "` (`Lint, types, tests`). "
    + _WO003_PRE_APPLICATION_DESCRIPTION_FIELD + " "
    + _WO003_DRAFT_FIELD + " " + _WO003_DRAFT_COUNT_FIELD
    + " Exactly one replacement description was proposed above. At that gate "
    "it was a DRAFT and had NOT BEEN APPLIED, this Work Order did not "
    "authorize repository metadata application, and applying an independently "
    "accepted description was a separate owner-authorized external action "
    "after review, commit, push, and green CI."
)


def _wo003_session_b_record_findings(
    text, following_heading=_WO003_PLANNING_HEADING
):
    """Validate only the structurally bounded Session B description record."""
    region, reason = _wo003_anchored_section(
        text,
        (_WO003_ACCEPTANCE_HEADING, _WO003_SESSION_B_HEADING,
         following_heading),
    )
    if region is None:
        return [("WO-003 Session B draft record", reason,
                 "one structurally anchored Session B draft record")]
    findings = []
    if region != _WO003_SESSION_B_RECORD:
        findings.append(("WO-003 Session B draft record",
                         "the bounded Session B draft record changed",
                         "the exact authorization, observation, draft, and boundary"))

    # The canonical record anchors the real draft. Count the keyed declaration
    # across the whole document as well, so a second plausible draft outside
    # the record cannot coexist with the one under review.
    draft_lines = [
        line.strip() for line in text.split("\n")
        if line.strip().startswith(_WO003_DRAFT_FIELD_PREFIX)
    ]
    if len(draft_lines) != 1:
        findings.append(("WO-003 Session B draft count", str(len(draft_lines)),
                         "exactly one proposed description draft"))
        return findings
    draft_line = draft_lines[0]
    draft = draft_line[len(_WO003_DRAFT_FIELD_PREFIX):]
    if not draft.endswith("`"):
        findings.append(("WO-003 Session B draft record", draft_line,
                         "a backtick-delimited draft field"))
        return findings
    draft = draft[:-1]
    if len(draft) > 350:
        findings.append(("WO-003 Session B draft length", str(len(draft)),
                         "350 characters or fewer"))
    if len(draft) != _WO003_DESCRIPTION_DRAFT_LENGTH:
        findings.append(("WO-003 Session B draft character count",
                         str(len(draft)),
                         str(_WO003_DESCRIPTION_DRAFT_LENGTH)))
    required_truth = (
        "362 Python automation tools",
        "55 categories",
        "experimental",
        "authenticated same-user loopback bridge",
        "Epic's official UEFN MCP",
        "not exposed through Epic's MCP server",
    )
    for phrase in required_truth:
        if phrase not in draft:
            findings.append(("WO-003 Session B draft truth",
                             "missing " + phrase, phrase))
    for stale in ("358+", "55+", "fully-offline"):
        if stale in draft:
            findings.append(("WO-003 Session B draft truth",
                             "stale claim " + stale,
                             "the accepted 362/55 and bounded-network truth"))
    return findings


_WO003_ACCEPTED_DESCRIPTION_PREFIX = (
    "PRE_APPLICATION_ACCEPTED_DESCRIPTION_HISTORICAL_SNAPSHOT: `"
)
_WO003_SESSION_B_ACCEPTED_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO003_SESSION_B_ACCEPTED_WORKFLOW
)
_WO003_SESSION_B_ACCEPTED_JOB_URL = (
    _WO003_SESSION_B_ACCEPTED_RUN_URL + "/job/"
    + _WO003_SESSION_B_ACCEPTED_JOB
)
_WO003_SESSION_B_ACCEPTANCE_RECORD = (
    "## Session B acceptance record HISTORICAL PRE-APPLICATION SNAPSHOT. "
    "Every value in this section records the state at the Session B "
    "acceptance gate, before the accepted description was applied. It does "
    "not describe the current live repository. Session B's "
    "repository-description draft was independently accepted. The accepted "
    "draft was committed and pushed "
    "as `" + _WO003_SESSION_B_ACCEPTED_BASE + "`. CI workflow "
    "[`" + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`]("
    + _WO003_SESSION_B_ACCEPTED_RUN_URL + ") completed successfully, "
    "including required job [`" + _WO003_SESSION_B_ACCEPTED_JOB
    + "` — Lint, types, tests](" + _WO003_SESSION_B_ACCEPTED_JOB_URL
    + "). " + _WO003_ACCEPTED_DESCRIPTION_PREFIX + _WO003_DESCRIPTION_DRAFT
    + "` ACCEPTED_DESCRIPTION_CHARACTER_COUNT: `"
    + str(_WO003_DESCRIPTION_DRAFT_LENGTH) + "` At that gate the accepted "
    "description above was still a DRAFT and had NOT BEEN APPLIED, and the "
    "live GitHub repository description was still unchanged. No repository "
    "description, repository metadata, tag, Release, or social publication "
    "had been changed, updated, applied, or published at that gate, and "
    "applying the exact accepted description was a separate owner-authorized "
    "external action that this Work Order did not authorize."
)
# One pinned occurrence each, in its own position and form. Containment
# alone cannot enforce these: each identifier appears twice per record -
# visible label and URL - so one can rot while the other keeps `in` true.
_WO003_SESSION_B_ACCEPTANCE_EVIDENCE = (
    ("acceptance narrative commit",
     "pushed as `" + _WO003_SESSION_B_ACCEPTED_BASE + "`."),
    ("acceptance workflow label",
     "[`" + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`]"),
    ("acceptance workflow URL",
     "(" + _WO003_SESSION_B_ACCEPTED_RUN_URL + ")"),
    ("acceptance required-job label",
     "[`" + _WO003_SESSION_B_ACCEPTED_JOB + "` — Lint, types, tests]"),
    ("acceptance job URL",
     "(" + _WO003_SESSION_B_ACCEPTED_JOB_URL + ")"),
    ("accepted description",
     _WO003_ACCEPTED_DESCRIPTION_PREFIX + _WO003_DESCRIPTION_DRAFT + "`"),
    ("pre-application not-applied status",
     "was still a DRAFT and had NOT BEEN APPLIED"),
    ("pre-application live description",
     "the live GitHub repository description was still unchanged."),
)


def _locate_wo003_session_b_acceptance(
    text, following_heading=_WO003_PLANNING_HEADING
):
    """The Session B acceptance record, located by its two neighbours."""
    return _wo003_anchored_section(
        text,
        (_WO003_SESSION_B_HEADING, _WO003_SESSION_B_ACCEPTANCE_HEADING,
         following_heading),
    )


def _wo003_declared_value(text, prefix, kind, noun):
    """The one backticked value declared under `prefix`, or why there is none.

    Returns ``(value, findings)``. Each bounded record carries its description
    a second time, so the value is parsed back out and re-derived rather than
    trusted to the byte comparison alone.
    """
    lines = [line.strip() for line in text.split("\n")
             if line.strip().startswith(prefix)]
    if len(lines) != 1:
        return None, [(kind + " count", str(len(lines)),
                       "exactly one " + noun + " declaration")]
    value = lines[0][len(prefix):]
    if not value.endswith("`"):
        return None, [(kind, lines[0], "a backtick-delimited " + noun)]
    return value[:-1], []


def _wo003_session_b_acceptance_findings(
    text, following_heading=_WO003_PLANNING_HEADING
):
    """The accepted draft, its evidence, and its not-applied status.

    The bounded record carries the accepted description a second time, so
    the exact text and its 261-character count are re-derived here rather
    than trusted to the byte comparison alone: a coordinated edit to both
    the record and this constant would still have to change the recomputed
    length to pass.
    """
    findings = []
    for found_detail, want in _acceptance_record_findings(
        text,
        lambda body: _locate_wo003_session_b_acceptance(
            body, following_heading),
        _WO003_SESSION_B_ACCEPTANCE_RECORD,
        _WO003_SESSION_B_ACCEPTANCE_EVIDENCE,
    ):
        findings.append(("WO-003 Session B acceptance record",
                         found_detail, want))
    value, problems = _wo003_declared_value(
        text, _WO003_ACCEPTED_DESCRIPTION_PREFIX,
        "WO-003 Session B accepted description", "accepted description")
    if value is None:
        return findings + problems
    if value != _WO003_DESCRIPTION_DRAFT:
        findings.append(("WO-003 Session B accepted description",
                         "the accepted description changed",
                         "the exact accepted draft, unchanged"))
    if len(value) != _WO003_DESCRIPTION_DRAFT_LENGTH:
        findings.append(
            ("WO-003 Session B accepted description character count",
             str(len(value)), str(_WO003_DESCRIPTION_DRAFT_LENGTH)))
    return findings


_WO003_APPLICATION_HEADING = "## Repository description application record"
_WO003_APPLIED_DESCRIPTION_PREFIX = "APPLIED_REPOSITORY_DESCRIPTION: `"
_WO003_APPLIED_DESCRIPTION_FIELD = (
    _WO003_APPLIED_DESCRIPTION_PREFIX + _WO003_APPLIED_DESCRIPTION + "`"
)
_WO003_APPLIED_COUNT_FIELD = (
    "APPLIED_DESCRIPTION_CHARACTER_COUNT: `"
    + str(_WO003_DESCRIPTION_DRAFT_LENGTH) + "`"
)
_WO003_APPLIED_SHA_FIELD = (
    "APPLIED_DESCRIPTION_SHA256: `" + _WO003_APPLIED_DESCRIPTION_SHA256 + "`"
)
_WO003_APPLIED_READ_BACK_FIELD = (
    "APPLIED_DESCRIPTION_LIVE_READ_BACK: `byte-for-byte identical`"
)
_WO003_APPLICATION_RECORD = (
    _WO003_APPLICATION_HEADING + " Under separate BDFL/owner authorization, "
    "and at repository commit `" + _WO003_APPLIED_BASE + "`, the exact "
    "accepted repository description was applied to the live GitHub "
    "repository. " + _WO003_APPLIED_DESCRIPTION_FIELD + " "
    + _WO003_APPLIED_COUNT_FIELD + " " + _WO003_APPLIED_SHA_FIELD + " "
    + _WO003_APPLIED_READ_BACK_FIELD + " The exact authorized command was "
    "`gh repo edit undergroundrap/UEFN-TOOLBELT --description \"<the applied "
    "value above>\"`. A read-only `gh repo view` read-back returned the "
    "applied value byte for byte, and its recomputed SHA-256 equals the "
    "digest declared above. The stale `358+`, `55+`, and fully-offline "
    "wording is absent from the live description. Non-description metadata "
    "is unchanged: homepage `https://www.fortnite.com/@ohshh`, visibility "
    "PUBLIC, archived state `false`, and all 20 repository topics. No file, "
    "commit, push, tag, Release, branch setting, other repository metadata, "
    "or social state changed. WO-003 remains issued. Its completion "
    "transition requires a separate owner gate, and no session is authorized."
)
# One pinned occurrence each, in its own position and form - the same
# per-occurrence discipline the acceptance evidence uses.
_WO003_APPLICATION_EVIDENCE = (
    ("applied description", _WO003_APPLIED_DESCRIPTION_FIELD),
    ("applied character count", _WO003_APPLIED_COUNT_FIELD),
    ("applied digest", _WO003_APPLIED_SHA_FIELD),
    ("live read-back", _WO003_APPLIED_READ_BACK_FIELD),
    ("authorized command", "gh repo edit undergroundrap/UEFN-TOOLBELT"),
    ("unchanged non-description metadata",
     "visibility PUBLIC, archived state `false`, and all 20 repository "
     "topics."),
    ("nothing else changed",
     "No file, commit, push, tag, Release, branch setting, other repository "
     "metadata, or social state changed."),
)


def _locate_wo003_application(text):
    """The application record, located by its two neighbouring headings."""
    return _wo003_anchored_section(
        text,
        (_WO003_SESSION_B_ACCEPTANCE_HEADING, _WO003_APPLICATION_HEADING,
         _WO003_PLANNING_HEADING),
    )


def _locate_wo003_completion(text):
    """The completion record, located by its two neighbouring headings."""
    return _wo003_anchored_section(
        text,
        (_WO003_BOUNDARIES_HEADING, _WO003_COMPLETION_HEADING,
         _WO003_STOP_HEADING),
    )


def _wo003_completion_record_findings(text):
    """The completion commit, workflow, and job, bounded by position.

    Structural rather than present-anywhere: the record must sit between its
    two neighbouring headings and match byte for byte, so a correct copy
    parked elsewhere in the document cannot satisfy a falsified one, and the
    heading cannot be duplicated, demoted, or relocated.
    """
    return [
        ("WO-003 completion record", found_detail, want)
        for found_detail, want in _acceptance_record_findings(
            text, _locate_wo003_completion, _WO003_COMPLETION_RECORD,
            _WO003_COMPLETION_EVIDENCE,
        )
    ]


def _wo003_application_record_findings(text):
    """The applied value, its count, its digest, and the live read-back.

    The bounded record carries the applied description a second time, so its
    text, its 261-character length, and its SHA-256 are re-derived here rather
    than trusted to the byte comparison alone: a coordinated edit to the
    record, the declared count, and the declared digest would still have to
    survive recomputation from the value actually recorded.
    """
    findings = []
    for found_detail, want in _acceptance_record_findings(
        text, _locate_wo003_application, _WO003_APPLICATION_RECORD,
        _WO003_APPLICATION_EVIDENCE,
    ):
        findings.append(("WO-003 description application record",
                         found_detail, want))
    value, problems = _wo003_declared_value(
        text, _WO003_APPLIED_DESCRIPTION_PREFIX,
        "WO-003 applied description", "applied description")
    if value is None:
        return findings + problems
    if value != _WO003_APPLIED_DESCRIPTION:
        findings.append(("WO-003 applied description",
                         "the applied description changed",
                         "the exact value read back from the live repository"))
    if len(value) != _WO003_DESCRIPTION_DRAFT_LENGTH:
        findings.append(("WO-003 applied description character count",
                         str(len(value)),
                         str(_WO003_DESCRIPTION_DRAFT_LENGTH)))
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    if digest != _WO003_APPLIED_DESCRIPTION_SHA256:
        findings.append(("WO-003 applied description digest", digest,
                         _WO003_APPLIED_DESCRIPTION_SHA256))
    for field, kind in (
        (_WO003_APPLIED_COUNT_FIELD,
         "WO-003 applied character-count declaration"),
        (_WO003_APPLIED_SHA_FIELD, "WO-003 applied digest declaration"),
        (_WO003_APPLIED_READ_BACK_FIELD, "WO-003 applied read-back evidence"),
    ):
        occurrences = text.count(field)
        if occurrences != 1:
            findings.append((kind, str(occurrences), "exactly one " + field))
    return findings


class _Wo003SettledGate(NamedTuple):
    """One settled WO-003 gate, as data rather than as a branch.

    Session B acceptance and the description application are the same
    shape, so only the values that differ live here and the validation is
    written once. This is internal checker structure carrying no authority:
    root `WORKORDER.md` stays the sole authority pointer, and every value
    below is only the expected form of what it already says.
    """

    gate: str                 # expected pointer `- Current gate:` value
    marker: str               # expected issued AUTHORIZATION line
    heading: str              # the record heading that identifies this gate
    record_key: str           # canonical base/gate/slice row
    auth_kind: str
    next_gate: str
    statement: str
    statement_kind: str
    # (exact text, finding kind, expected wording) per pointer statement.
    pointer_statements: tuple[tuple[str, str, str], ...]
    # Heading that closes the Session B acceptance record in this state.
    acceptance_following: str
    # Whether this gate additionally requires the bounded application record.
    application_record: bool
    boundary: tuple[str, str, str]
    session_want: str


_WO003_SETTLED_GATES = (
    _Wo003SettledGate(
        gate=_WO003_APPLIED_GATE,
        marker=_ISSUED_DESCRIPTION_APPLIED,
        heading=_WO003_APPLICATION_HEADING,
        record_key="APPLIED",
        auth_kind="WO-003 applied authorization",
        next_gate=_WO003_APPLIED_NEXT_GATE,
        statement=_WO003_APPLIED_STATEMENT,
        statement_kind="WO-003 applied statement",
        pointer_statements=(
            (_WO003_PRE_APPLICATION_POINTER_STATEMENT,
             "WO-003 pre-application pointer statement",
             "exactly one " + _WO003_PRE_APPLICATION_POINTER_STATEMENT),
            (_WO003_APPLIED_POINTER_STATEMENT,
             "WO-003 applied pointer statement",
             "exactly one " + _WO003_APPLIED_POINTER_STATEMENT),
        ),
        acceptance_following=_WO003_APPLICATION_HEADING,
        application_record=True,
        boundary=("WO-003 external-action boundary",
                  "a further metadata or publication action opened",
                  "the applied description only; nothing further"),
        session_want="description applied; no session authorized",
    ),
    _Wo003SettledGate(
        gate=_WO003_SESSION_B_ACCEPTED_GATE,
        marker=_ISSUED_SESSION_B_ACCEPTED,
        heading=_WO003_SESSION_B_ACCEPTANCE_HEADING,
        record_key="B_ACCEPTED",
        auth_kind="WO-003 Session B accepted authorization",
        next_gate=_WO003_SESSION_B_ACCEPTED_NEXT_GATE,
        statement=_WO003_SESSION_B_ACCEPTED_STATEMENT,
        statement_kind="WO-003 Session B accepted statement",
        pointer_statements=(
            (_WO003_SESSION_B_ACCEPTED_POINTER_STATEMENT,
             "WO-003 Session B accepted pointer statement",
             "exactly one accepted, not-applied statement"),
        ),
        acceptance_following=_WO003_PLANNING_HEADING,
        application_record=False,
        boundary=("WO-003 Session B external-action boundary",
                  "metadata application or social publication opened",
                  "accepted draft only; no metadata or publication action"),
        session_want="Session B accepted; no session authorized",
    ),
)


def _wo003_settled_gate(name, current_gate, auth_lines, issued_text):
    """The settled gate this issued WO-003 is in, or None.

    Ordered most-recent-first, so a document that still carries an earlier
    record is identified by the gate it has actually reached.
    """
    if name != _WO003_NAME:
        return None
    for state in _WO003_SETTLED_GATES:
        if (current_gate == state.gate
                or auth_lines == [state.marker]
                or state.heading in issued_text):
            return state
    return None


def _wo003_settled_findings(
    state, pointer, issued_text, rel, base, current_gate, auth_lines
):
    """Validate one settled WO-003 gate against its configuration.

    Every earlier bounded record stays enforced from whichever gate is
    current, so reaching a later gate never silences what came before.
    """
    out = []
    normalized_issued = " ".join(issued_text.split())
    normalized_pointer = " ".join(pointer.split())
    if auth_lines != [state.marker]:
        out.append((rel, state.auth_kind, repr(auth_lines),
                    "exactly " + state.marker))
    out.extend(_wo003_record_findings(
        pointer, issued_text, rel, base, current_gate, state.record_key))
    records = [
        _wo003_acceptance_record_findings(
            issued_text, _WO003_SESSION_B_HEADING),
        _wo003_session_b_record_findings(
            issued_text, _WO003_SESSION_B_ACCEPTANCE_HEADING),
        _wo003_session_b_acceptance_findings(
            issued_text, state.acceptance_following),
    ]
    if state.application_record:
        records.append(_wo003_application_record_findings(issued_text))
    for record in records:
        for kind, found, want in record:
            out.append((rel, kind, found, want))
    for required, kind in ((state.next_gate, "WO-003 next gate"),
                           (state.statement, state.statement_kind)):
        if normalized_issued.count(required) != 1:
            out.append((rel, kind, str(normalized_issued.count(required)),
                        "exactly one " + required))
    for required, kind, want in state.pointer_statements:
        if normalized_pointer.count(required) != 1:
            out.append(("WORKORDER.md", kind,
                        str(normalized_pointer.count(required)), want))
    # Reaching this gate is not reaching the next one. The pointer may not
    # open a further external action, reopen a labeled session, or reach
    # WO-004.
    allowed = (state.gate,) + tuple(
        statement for statement, _kind, _want in state.pointer_statements)
    if _has_session_b_external_action_authorization(pointer, allowed):
        out.append(("WORKORDER.md",) + state.boundary)
    if _has_other_session_authorization(pointer, "", ""):
        out.append(("WORKORDER.md", "session authorization reopening",
                    "positive permission for Session A, Session B, or later",
                    state.session_want))
    if _has_next_work_order_authorization(pointer, "", "WO-004"):
        out.append(("WORKORDER.md", "next work order authorization",
                    "implicit WO-004 permission",
                    "WO-004 remains proposed and not authorized"))
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
# Exact proposal-only admission; this does not extend the frozen train or
# register an issued identity. Presence is optional to the historical checker.
_PLANNING_ONLY_PROPOSALS = frozenset({
    "WO-008-user-reliability-and-mcp-client-acceptance.md",
})
# The frozen train as a DECLARED ordered inventory: canonical order identity
# to canonical filename. Successor identity is read from here, never from
# whatever files happen to be on disk, so an extra, malformed, or misplaced
# document cannot move the train or silence a later-order check.
_RELEASE_TRAIN = (
    ("WO-001", "WO-001-custom-mcp-security.md"),
    ("WO-002", _WO002_NAME),
    ("WO-003", _WO003_NAME),
    ("WO-004", "WO-004-modal-observability.md"),
    ("WO-005", "WO-005-coverage-source-of-truth.md"),
    ("WO-006", "WO-006-official-vs-toolbelt-benchmark.md"),
    ("WO-007", "WO-007-public-mcp-explainer.md"),
)
_RELEASE_TRAIN_IDS = tuple(order for order, _name in _RELEASE_TRAIN)
_WO007_ID, _WO007_NAME = _RELEASE_TRAIN[-1]
# WO-007's mandate forbids the very actions the external-action scanner looks
# for. The scanner has no negation handling, so this exact sentence is removed
# once before scanning - but only from WO-007's own validated mandate.
_WO007_DRAFTING_PROHIBITION = (
    "Decision lock: drafting grants no authority to publish, change the "
    "repository description, create a Release, or post socially."
)
_FROZEN_RELEASE_TRAIN = "WO-001 through WO-007"
_CLOSED_RELEASE_GATE = (
    "NO TAG OR GITHUB RELEASE AUTHORIZED — COMPLETE THE FROZEN TRAIN AND FINAL "
    "INTEGRATION/REPOSITORY-TRUTH AUDIT FIRST"
)

# WO-004's issuance record. The canonical bullet block in WORKORDER.md and
# the canonical metadata block in the mandate are the only surfaces that
# DECLARE these values; the narrative paragraphs restate them. Each surface
# is therefore compared as an exact, contiguous, terminal slice AND has its
# keys counted, so a restatement can never satisfy a missing or corrupted
# declaration.
_WO004_ID, _WO004_NAME = _RELEASE_TRAIN[3]
_WO004_PLANNING_BASELINE = "0d513f1639cf197707132205f4074d0fe3a750cc"
_WO004_BASELINE_MARKER = "BASELINE: `" + _WO004_PLANNING_BASELINE + "`"
_WO004_ISSUANCE_COMMIT = "8444faf340afe47765c43d943200db712880817b"
_WO004_ISSUANCE_WORKFLOW = "34441169191"
_WO004_ISSUANCE_JOB = "102756337393"
_WO004_ISSUED_SEQUENCE = (
    _WO004_BASELINE_MARKER,
    "ISSUANCE_COMMIT: `" + _WO004_ISSUANCE_COMMIT + "`",
    "ISSUANCE_CI_WORKFLOW: `" + _WO004_ISSUANCE_WORKFLOW + "`",
    "ISSUANCE_CI_JOB: `" + _WO004_ISSUANCE_JOB + "` — Lint, types, tests",
)
# Only the pinned declarations carry a backticked value in THIS sequence,
# so key and position are all the slice comparison asserts for the rest.
# That is not the whole story for the base commit: its exact value is
# pinned by _WO004_POINTER_KEYS below, which runs in every session state,
# and the closed-session branch compares it a second time under a finding
# that names it directly. Moving the base to a later gate's commit is
# therefore not a WORKORDER.md-only edit - that transition has to update
# this file too, which is the visible act the governance model wants.
_WO004_POINTER_SEQUENCE = (
    "- Current issued Work Order:",
    "- Authorized session:",
    "- Base commit:",
    "- Current gate:",
    "- Issuance commit: `" + _WO004_ISSUANCE_COMMIT + "`",
    "- Issuance CI workflow: `" + _WO004_ISSUANCE_WORKFLOW + "`",
    "- Issuance CI job: `" + _WO004_ISSUANCE_JOB + "` — Lint, types, tests",
    "- Release train:",
    "- Release gate:",
)
_WO004_POINTER_KEYS = (
    ("- Base commit:",
     "- Base commit: `" + _WO004_ISSUANCE_COMMIT + "`"),
    ("- Issuance commit:", _WO004_POINTER_SEQUENCE[4]),
    ("- Issuance CI workflow:", _WO004_POINTER_SEQUENCE[5]),
    ("- Issuance CI job:", _WO004_POINTER_SEQUENCE[6]),
)
_WO004_ISSUED_KEYS = (
    ("BASELINE:", _WO004_ISSUED_SEQUENCE[0]),
    ("ISSUANCE_COMMIT:", _WO004_ISSUED_SEQUENCE[1]),
    ("ISSUANCE_CI_WORKFLOW:", _WO004_ISSUED_SEQUENCE[2]),
    ("ISSUANCE_CI_JOB:", _WO004_ISSUED_SEQUENCE[3]),
)
# Authorizing Session A adds three declarations to each canonical block.
# The slices stay exact and terminal in the new state, so the issuance
# record cannot be dropped, reordered, or padded on the way through - the
# same cumulative shape WO-003's session transitions used.
_WO004_SESSION_A_COMMIT = "f9fc7268d63dad92f5dd009bbf20e11477b8f926"
_WO004_SESSION_A_WORKFLOW = "34509193110"
_WO004_SESSION_A_JOB = "102978793893"
_WO004_SESSION_A_GATE = (
    "WO-004 SESSION A AUTHORIZED — READ-ONLY FEASIBILITY PLANNING ONLY"
)
_WO004_SESSION_A_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR FEASIBILITY "
    "PLANNING ONLY"
)
_WO004_SESSION_A_ISSUED_SEQUENCE = _WO004_ISSUED_SEQUENCE + (
    "SESSION_A_AUTHORIZATION_COMMIT: `" + _WO004_SESSION_A_COMMIT + "`",
    "SESSION_A_AUTHORIZATION_CI_WORKFLOW: `"
    + _WO004_SESSION_A_WORKFLOW + "`",
    "SESSION_A_AUTHORIZATION_CI_JOB: `" + _WO004_SESSION_A_JOB + "` "
    + "— Lint, types, tests",
)
_WO004_SESSION_A_POINTER_SEQUENCE = _WO004_POINTER_SEQUENCE[:7] + (
    "- Session A authorization commit: `" + _WO004_SESSION_A_COMMIT + "`",
    "- Session A authorization CI workflow: `"
    + _WO004_SESSION_A_WORKFLOW + "`",
    "- Session A authorization CI job: `" + _WO004_SESSION_A_JOB + "` "
    + "— Lint, types, tests",
) + _WO004_POINTER_SEQUENCE[7:]
_WO004_SESSION_A_ISSUED_KEYS = _WO004_ISSUED_KEYS + (
    ("SESSION_A_AUTHORIZATION_COMMIT:",
     _WO004_SESSION_A_ISSUED_SEQUENCE[4]),
    ("SESSION_A_AUTHORIZATION_CI_WORKFLOW:",
     _WO004_SESSION_A_ISSUED_SEQUENCE[5]),
    ("SESSION_A_AUTHORIZATION_CI_JOB:",
     _WO004_SESSION_A_ISSUED_SEQUENCE[6]),
)
# The base commit is the one declared value that moves with the gate, so
# the Session A key set repins it to the authorization commit and keeps
# every issuance bullet unchanged beside it.
_WO004_SESSION_A_POINTER_KEYS = (
    (("- Base commit:",
      "- Base commit: `" + _WO004_SESSION_A_COMMIT + "`"),)
    + _WO004_POINTER_KEYS[1:]
    + (("- Session A authorization commit:",
        _WO004_SESSION_A_POINTER_SEQUENCE[7]),
       ("- Session A authorization CI workflow:",
        _WO004_SESSION_A_POINTER_SEQUENCE[8]),
       ("- Session A authorization CI job:",
        _WO004_SESSION_A_POINTER_SEQUENCE[9]))
)
_WO004_SESSION_A_STATEMENT = (
    "Session A is authorized for read-only feasibility planning under the "
    "current root `WORKORDER.md` gate alone."
)
_WO004_ISSUANCE_STATEMENT = (
    "Issuance alone grants no implementation authority. A session becomes "
    "implementable only when the owner names it in root `WORKORDER.md`."
)
_WO004_ISSUED_NEXT_GATE = (
    "NEXT GATE: separate owner authorization for Session A feasibility "
    "only, recorded in root `WORKORDER.md`. Issuance authorizes no session. "
    "Session A, Session B, Session C, and all live UEFN work remain closed."
)
_WO004_SESSION_A_NEXT_GATE = (
    "NEXT GATE: fresh independent review of the complete uncommitted "
    "Session A feasibility record, followed by a separate owner decision "
    "on whether the proposed probes run. Session B, Session C, and all "
    "live UEFN work remain closed."
)
# Accepting Session A adds three more declarations to each canonical block
# and moves the base to the acceptance commit. The issuance and Session A
# authorization declarations stay inside the same exact, terminal slice, so
# accepting the session cannot drop the evidence that authorized it.
_WO004_SESSION_A_ACCEPTED_COMMIT = "c4c21caa0960c430a4bcfb90cd65ef1edfc1a790"
_WO004_SESSION_A_ACCEPTED_WORKFLOW = "34735715115"
_WO004_SESSION_A_ACCEPTED_JOB = "103666661855"
_WO004_SESSION_A_ACCEPTED_GATE = (
    "WO-004 SESSION A ACCEPTED — SESSION B IMPLEMENTATION NOT AUTHORIZED"
)
_WO004_DECISION_HEADING = "## Session A decision record"
_WO004_ACCEPTED_ISSUED_SEQUENCE = _WO004_SESSION_A_ISSUED_SEQUENCE + (
    "SESSION_A_ACCEPTANCE_COMMIT: `" + _WO004_SESSION_A_ACCEPTED_COMMIT + "`",
    "SESSION_A_ACCEPTANCE_CI_WORKFLOW: `"
    + _WO004_SESSION_A_ACCEPTED_WORKFLOW + "`",
    "SESSION_A_ACCEPTANCE_CI_JOB: `" + _WO004_SESSION_A_ACCEPTED_JOB + "` "
    + "— Lint, types, tests",
)
_WO004_ACCEPTED_POINTER_SEQUENCE = _WO004_SESSION_A_POINTER_SEQUENCE[:10] + (
    "- Session A acceptance commit: `" + _WO004_SESSION_A_ACCEPTED_COMMIT + "`",
    "- Session A acceptance CI workflow: `"
    + _WO004_SESSION_A_ACCEPTED_WORKFLOW + "`",
    "- Session A acceptance CI job: `" + _WO004_SESSION_A_ACCEPTED_JOB + "` "
    + "— Lint, types, tests",
) + _WO004_SESSION_A_POINTER_SEQUENCE[10:]
_WO004_ACCEPTED_ISSUED_KEYS = _WO004_SESSION_A_ISSUED_KEYS + (
    ("SESSION_A_ACCEPTANCE_COMMIT:", _WO004_ACCEPTED_ISSUED_SEQUENCE[7]),
    ("SESSION_A_ACCEPTANCE_CI_WORKFLOW:", _WO004_ACCEPTED_ISSUED_SEQUENCE[8]),
    ("SESSION_A_ACCEPTANCE_CI_JOB:", _WO004_ACCEPTED_ISSUED_SEQUENCE[9]),
)
# The base moves again, to the acceptance commit; every earlier bullet keeps
# its exact pin beside it.
_WO004_ACCEPTED_POINTER_KEYS = (
    (("- Base commit:",
      "- Base commit: `" + _WO004_SESSION_A_ACCEPTED_COMMIT + "`"),)
    + _WO004_SESSION_A_POINTER_KEYS[1:]
    + (("- Session A acceptance commit:",
        _WO004_ACCEPTED_POINTER_SEQUENCE[10]),
       ("- Session A acceptance CI workflow:",
        _WO004_ACCEPTED_POINTER_SEQUENCE[11]),
       ("- Session A acceptance CI job:",
        _WO004_ACCEPTED_POINTER_SEQUENCE[12]))
)
_WO004_SESSION_A_ACCEPTED_STATEMENT = (
    "Session A is accepted and complete. Session B implementation and "
    "Session C live testing are not authorized; each requires a separate "
    "owner gate recorded in root `WORKORDER.md`."
)
_WO004_SESSION_A_ACCEPTED_NEXT_GATE = (
    "NEXT GATE: fresh independent review of this uncommitted Session A "
    "decision and mandate amendment, followed by a separate owner "
    "authorization for Session B implementation. Session B, Session C, and "
    "all live UEFN work remain closed."
)
# Authorizing Session B adds three more declarations to each canonical block
# and moves the base to the Session B authorization commit. Every earlier
# declaration - issuance, Session A authorization, Session A acceptance - stays
# inside the same exact, terminal slice.
_WO004_SESSION_B_COMMIT = "da846ec36773d673ca9dcab3025ac36555579d0f"
_WO004_SESSION_B_WORKFLOW = "36375370541"
_WO004_SESSION_B_JOB = "108780005124"
_WO004_SESSION_B_GATE = (
    "WO-004 SESSION B AUTHORIZED — CLIENT OUTCOME SEMANTICS ONLY"
)
_WO004_SESSION_B_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION B AUTHORIZED FOR CLIENT OUTCOME "
    "SEMANTICS ONLY"
)
_WO004_SESSION_B_ISSUED_SEQUENCE = _WO004_ACCEPTED_ISSUED_SEQUENCE + (
    "SESSION_B_AUTHORIZATION_COMMIT: `" + _WO004_SESSION_B_COMMIT + "`",
    "SESSION_B_AUTHORIZATION_CI_WORKFLOW: `"
    + _WO004_SESSION_B_WORKFLOW + "`",
    "SESSION_B_AUTHORIZATION_CI_JOB: `" + _WO004_SESSION_B_JOB + "` "
    + "— Lint, types, tests",
)
_WO004_SESSION_B_POINTER_SEQUENCE = _WO004_ACCEPTED_POINTER_SEQUENCE[:13] + (
    "- Session B authorization commit: `" + _WO004_SESSION_B_COMMIT + "`",
    "- Session B authorization CI workflow: `"
    + _WO004_SESSION_B_WORKFLOW + "`",
    "- Session B authorization CI job: `" + _WO004_SESSION_B_JOB + "` "
    + "— Lint, types, tests",
) + _WO004_ACCEPTED_POINTER_SEQUENCE[13:]
_WO004_SESSION_B_ISSUED_KEYS = _WO004_ACCEPTED_ISSUED_KEYS + (
    ("SESSION_B_AUTHORIZATION_COMMIT:", _WO004_SESSION_B_ISSUED_SEQUENCE[10]),
    ("SESSION_B_AUTHORIZATION_CI_WORKFLOW:",
     _WO004_SESSION_B_ISSUED_SEQUENCE[11]),
    ("SESSION_B_AUTHORIZATION_CI_JOB:", _WO004_SESSION_B_ISSUED_SEQUENCE[12]),
)
_WO004_SESSION_B_POINTER_KEYS = (
    (("- Base commit:",
      "- Base commit: `" + _WO004_SESSION_B_COMMIT + "`"),)
    + _WO004_ACCEPTED_POINTER_KEYS[1:]
    + (("- Session B authorization commit:",
        _WO004_SESSION_B_POINTER_SEQUENCE[13]),
       ("- Session B authorization CI workflow:",
        _WO004_SESSION_B_POINTER_SEQUENCE[14]),
       ("- Session B authorization CI job:",
        _WO004_SESSION_B_POINTER_SEQUENCE[15]))
)
_WO004_SESSION_B_STATEMENT = (
    "Session B is authorized for client outcome semantics only under the "
    "current root `WORKORDER.md` gate alone."
)
_WO004_SESSION_B_NEXT_GATE = (
    "NEXT GATE: fresh independent review of the complete uncommitted Session "
    "B implementation, which is limited to client outcome semantics, "
    "followed by a separate owner gate for Session C live acceptance. "
    "Session C, commit, push, and all live UEFN work remain closed."
)
# Once Session B is authorized, the acceptance statement is kept as history
# in the past tense, beside the Session A authorization statement it follows.
_WO004_SESSION_A_ACCEPTANCE_RECORD = (
    "Session A is accepted and complete. At the Session A acceptance gate, "
    "Session B implementation and Session C live testing were not "
    "authorized; each required a separate owner gate recorded in root "
    "`WORKORDER.md`."
)
# Session A's authorization statement, anchored to the heading it opens. The
# Session B scan pins and removes this form rather than the bare sentence, so
# words fused onto the statement stay in place for the scan to see.
_WO004_SESSION_A_BASIS_HEADING = "## Session A authorization basis"
_WO004_SESSION_A_ANCHORED = (
    _WO004_SESSION_A_BASIS_HEADING + " " + _WO004_SESSION_A_STATEMENT
)
# Authorizing Session C adds three more declarations and moves the base to the
# Session C authorization commit. Its CI ran on that base commit, which does
# not contain the uncommitted Session B implementation, so the mandate also
# records the reviewed implementation files by identity.
_WO004_SESSION_C_COMMIT = "17b5afe3f50bfa3ab882ff362a10eef70750c694"
_WO004_SESSION_C_WORKFLOW = "36385787242"
_WO004_SESSION_C_JOB = "108810759914"
_WO004_SESSION_C_GATE = (
    "WO-004 SESSION C AUTHORIZED — OWNER-OPERATED LIVE ACCEPTANCE ONLY"
)
_WO004_SESSION_C_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION C AUTHORIZED FOR LIVE ACCEPTANCE ONLY"
)
_WO004_SESSION_C_ISSUED_SEQUENCE = _WO004_SESSION_B_ISSUED_SEQUENCE + (
    "SESSION_C_AUTHORIZATION_COMMIT: `" + _WO004_SESSION_C_COMMIT + "`",
    "SESSION_C_AUTHORIZATION_CI_WORKFLOW: `"
    + _WO004_SESSION_C_WORKFLOW + "`",
    "SESSION_C_AUTHORIZATION_CI_JOB: `" + _WO004_SESSION_C_JOB + "` "
    + "— Lint, types, tests",
)
_WO004_SESSION_C_POINTER_SEQUENCE = _WO004_SESSION_B_POINTER_SEQUENCE[:16] + (
    "- Session C authorization commit: `" + _WO004_SESSION_C_COMMIT + "`",
    "- Session C authorization CI workflow: `"
    + _WO004_SESSION_C_WORKFLOW + "`",
    "- Session C authorization CI job: `" + _WO004_SESSION_C_JOB + "` "
    + "— Lint, types, tests",
) + _WO004_SESSION_B_POINTER_SEQUENCE[16:]
_WO004_SESSION_C_ISSUED_KEYS = _WO004_SESSION_B_ISSUED_KEYS + (
    ("SESSION_C_AUTHORIZATION_COMMIT:", _WO004_SESSION_C_ISSUED_SEQUENCE[13]),
    ("SESSION_C_AUTHORIZATION_CI_WORKFLOW:",
     _WO004_SESSION_C_ISSUED_SEQUENCE[14]),
    ("SESSION_C_AUTHORIZATION_CI_JOB:", _WO004_SESSION_C_ISSUED_SEQUENCE[15]),
)
_WO004_SESSION_C_POINTER_KEYS = (
    (("- Base commit:",
      "- Base commit: `" + _WO004_SESSION_C_COMMIT + "`"),)
    + _WO004_SESSION_B_POINTER_KEYS[1:]
    + (("- Session C authorization commit:",
        _WO004_SESSION_C_POINTER_SEQUENCE[16]),
       ("- Session C authorization CI workflow:",
        _WO004_SESSION_C_POINTER_SEQUENCE[17]),
       ("- Session C authorization CI job:",
        _WO004_SESSION_C_POINTER_SEQUENCE[18]))
)
_WO004_SESSION_C_STATEMENT = (
    "Session C is authorized for owner-operated live acceptance only under "
    "the current root `WORKORDER.md` gate alone."
)
_WO004_SESSION_C_NEXT_GATE = (
    "NEXT GATE: owner-operated Session C live acceptance of the reviewed "
    "uncommitted Session B implementation, followed by fresh independent "
    "review of the recorded evidence. Any change to the implementation, "
    "commit, push, and WO-004 completion remain closed."
)
# Session B's authorization statement, kept as history once Session C is
# authorized and anchored to its heading, as Session A's is.
_WO004_SESSION_B_BASIS_HEADING = "## Session B authorization basis"
_WO004_SESSION_B_ANCHORED = (
    _WO004_SESSION_B_BASIS_HEADING + " At the Session B authorization gate, "
    "Session B was authorized for client outcome semantics only under the "
    "root `WORKORDER.md` gate."
)
# A sentence the issued mandate has carried since issuance (Status semantics,
# "Operation identity and recovery"). It names Session B beside the word
# "resume", so once Session B is no longer the authorized session the scanner
# would read it as a grant. It is pinned and removed in a form anchored to the
# sentence before it, as the authorization statements are.
_WO004_ISSUED_RECOVERY_STATEMENT = (
    "correlation of a late reply to a specific in-flight operation is "
    "unproven. Session B must confirm what the transport can actually do "
    "before any resume, cancel, or reattach behaviour is designed."
)
# The reviewed, uncommitted implementation Session C tests: path, the Git blob
# Git would commit (line-ending normalized), and the SHA-256 of the reviewed
# worktree bytes. The mandate records them as one list in the Session C
# authorization section, checked by _wo004_implementation_identity_findings.
_WO004_SESSION_C_IMPLEMENTATION = (
    (".claude/mcp_reference.md", "75873316c1f0f57037181a4fda2f2cd4365a730d",
     "cb55912ec5168d2d46a3631443bc2dcc462f543567142d91b1fdd0b1cb6e5c26"),
    ("client.py", "bfff40e02fa167a0f987a5e066e7bc6f13f8b308",
     "c5097f3141b19122b665b0be2a570e13ec642a5d2cc582a6bec717ae25e34850"),
    ("mcp_server.py", "70a88474dc138b5d3915f06a96dffef24c71c993",
     "0aa4268491d60f7fbb663da1d3bbcb095997243a51db91357452160b04eed0b3"),
    ("tests/test_mcp_security.py", "34580cb9426f4aeaaa47381cf77d707936e88ffa",
     "dd0c2ceaebfb813b371650e10658c98b41958e8d1f5139181ecaf8955cfe6976"),
)
_WO004_SESSION_C_IMPLEMENTATION_LINES = tuple(
    "- `" + path + "`: Git blob `" + blob + "`, SHA-256 `" + sha + "`"
    for path, blob, sha in _WO004_SESSION_C_IMPLEMENTATION
)
_WO004_SESSION_C_BASIS_HEADING = "## Session C authorization basis"
# The paragraphs directly before and after the identity list, which place it.
_WO004_SESSION_C_IDENTITY_INTRO = (
    "Session C tests exactly this reviewed implementation, identified by its "
    "files in the reviewed snapshot `wo004-session-b-cleanup-2026-09-28`:"
)
_WO004_SESSION_C_IDENTITY_CLOSING = (
    "Each Git blob is the line-ending-normalized identity Git would commit; "
    "each SHA-256 is of the reviewed worktree bytes."
)
# An identity declaration names its kind and then gives a code-span value.
# Prose that only names a kind, as the closing paragraph does, declares nothing.
_WO004_IDENTITY_DECLARATION = re.compile(r"(Git blob|SHA-256)[\s:]*`")
# Completing WO-004 adds its completion basis - the commit that carried the
# accepted implementation and the Session C evidence, and that commit's CI - as
# three more declarations on each canonical block, and moves the base to that
# commit. The completion transition's own commit is not recorded: it does not
# exist when the transition is written. Every earlier declaration stays inside
# the same exact, terminal slice, so completion cannot drop the evidence that
# led to it.
_WO004_COMPLETION_COMMIT = "b4fa0a5245944fd992b6a2b52dbac1e59de242ae"
_WO004_COMPLETION_WORKFLOW = "36494750779"
_WO004_COMPLETION_JOB = "109171582586"
_WO004_COMPLETED_GATE = (
    "WO-004 COMPLETED — WO-005 PROPOSED AND NOT AUTHORIZED"
)
_WO004_COMPLETED_ISSUED_SEQUENCE = _WO004_SESSION_C_ISSUED_SEQUENCE + (
    "COMPLETION_BASIS_COMMIT: `" + _WO004_COMPLETION_COMMIT + "`",
    "COMPLETION_BASIS_CI_WORKFLOW: `" + _WO004_COMPLETION_WORKFLOW + "`",
    "COMPLETION_BASIS_CI_JOB: `" + _WO004_COMPLETION_JOB + "` "
    + "— Lint, types, tests",
)
_WO004_COMPLETED_POINTER_SEQUENCE = _WO004_SESSION_C_POINTER_SEQUENCE[:19] + (
    "- Completion basis commit: `" + _WO004_COMPLETION_COMMIT + "`",
    "- Completion basis CI workflow: `" + _WO004_COMPLETION_WORKFLOW + "`",
    "- Completion basis CI job: `" + _WO004_COMPLETION_JOB + "` "
    + "— Lint, types, tests",
) + _WO004_SESSION_C_POINTER_SEQUENCE[19:]
_WO004_COMPLETED_ISSUED_KEYS = _WO004_SESSION_C_ISSUED_KEYS + (
    ("COMPLETION_BASIS_COMMIT:", _WO004_COMPLETED_ISSUED_SEQUENCE[16]),
    ("COMPLETION_BASIS_CI_WORKFLOW:", _WO004_COMPLETED_ISSUED_SEQUENCE[17]),
    ("COMPLETION_BASIS_CI_JOB:", _WO004_COMPLETED_ISSUED_SEQUENCE[18]),
)
_WO004_COMPLETED_POINTER_KEYS = (
    (("- Base commit:",
      "- Base commit: `" + _WO004_COMPLETION_COMMIT + "`"),)
    + _WO004_SESSION_C_POINTER_KEYS[1:]
    + (("- Completion basis commit:",
        _WO004_COMPLETED_POINTER_SEQUENCE[19]),
       ("- Completion basis CI workflow:",
        _WO004_COMPLETED_POINTER_SEQUENCE[20]),
       ("- Completion basis CI job:",
        _WO004_COMPLETED_POINTER_SEQUENCE[21]))
)
# Pinned exactly once in the completed mandate, a frozen record of what was
# true at its own gate, which keeps the clause about WO-005's state.
_WO004_COMPLETED_STATEMENT = (
    "WO-004 is complete; no session is authorized. WO-005 remains proposed "
    "and unauthorized."
)
# The root pointer is the LIVE authority surface, where that clause goes stale
# the moment WO-005 is issued, so the pointer pins only this prefix - the same
# deletion issuing WO-004 made for WO-003's clause (_WO003_COMPLETED_POINTER_
# CLAUSE). A pointer that still carries the full statement also carries this.
_WO004_COMPLETED_POINTER_CLAUSE = (
    "WO-004 is complete; no session is authorized."
)
_WO004_COMPLETED_NEXT_GATE = (
    "NEXT GATE: separate owner authorization for a fresh independent WO-005 "
    "pre-issuance review, after this completion transition is accepted, "
    "committed, pushed, and green. Completion of WO-004 does not issue or "
    "authorize WO-005, which remains proposed and unauthorized."
)
# Session C's authorization statement, kept as history once WO-004 is
# completed and anchored to its heading, as Session A's and Session B's are.
_WO004_SESSION_C_ANCHORED = (
    _WO004_SESSION_C_BASIS_HEADING + " At the Session C authorization gate, "
    "Session C was authorized for owner-operated live acceptance only under "
    "the root `WORKORDER.md` gate."
)
# Which canonical shape each WO-004 state must present. Adding a state here
# is the visible act that moves the pointer's base commit. Keys come from
# _wo004_state_key, never straight from the pointer, so a pointer cannot
# select a state by naming it.
_WO004_STATES = {
    "NONE": (_WO004_POINTER_SEQUENCE, _WO004_POINTER_KEYS,
             _WO004_ISSUED_SEQUENCE, _WO004_ISSUED_KEYS,
             _WO004_ISSUED_NEXT_GATE, None),
    "A": (_WO004_SESSION_A_POINTER_SEQUENCE, _WO004_SESSION_A_POINTER_KEYS,
          _WO004_SESSION_A_ISSUED_SEQUENCE, _WO004_SESSION_A_ISSUED_KEYS,
          _WO004_SESSION_A_NEXT_GATE, _WO004_SESSION_A_STATEMENT),
    "A_ACCEPTED": (_WO004_ACCEPTED_POINTER_SEQUENCE,
                   _WO004_ACCEPTED_POINTER_KEYS,
                   _WO004_ACCEPTED_ISSUED_SEQUENCE,
                   _WO004_ACCEPTED_ISSUED_KEYS,
                   _WO004_SESSION_A_ACCEPTED_NEXT_GATE,
                   _WO004_SESSION_A_ACCEPTED_STATEMENT),
    "B": (_WO004_SESSION_B_POINTER_SEQUENCE, _WO004_SESSION_B_POINTER_KEYS,
          _WO004_SESSION_B_ISSUED_SEQUENCE, _WO004_SESSION_B_ISSUED_KEYS,
          _WO004_SESSION_B_NEXT_GATE, _WO004_SESSION_B_STATEMENT),
    "C": (_WO004_SESSION_C_POINTER_SEQUENCE, _WO004_SESSION_C_POINTER_KEYS,
          _WO004_SESSION_C_ISSUED_SEQUENCE, _WO004_SESSION_C_ISSUED_KEYS,
          _WO004_SESSION_C_NEXT_GATE, _WO004_SESSION_C_STATEMENT),
    # Selected by WHERE the mandate is - completed/ - never by the pointer,
    # which is why _wo004_state_key cannot return it.
    "COMPLETED": (_WO004_COMPLETED_POINTER_SEQUENCE,
                  _WO004_COMPLETED_POINTER_KEYS,
                  _WO004_COMPLETED_ISSUED_SEQUENCE,
                  _WO004_COMPLETED_ISSUED_KEYS,
                  _WO004_COMPLETED_NEXT_GATE, _WO004_COMPLETED_STATEMENT),
}


def _wo004_state_key(session, current_gate, auth_lines, issued_text):
    """The _WO004_STATES key for this pointer and mandate, or None.

    A closed session carrying ANY Session A acceptance signal - the accepted
    gate, the accepted marker, or the decision record - is compared against
    the whole accepted shape, so a partial transition fails as the state it
    claims to be instead of passing as the closed issuance. NONE, A, B, and
    C are the only recognized session values; anything else is rogue.
    """
    if session in ("A", "B", "C"):
        return session
    if session != "NONE":
        return None
    if (current_gate == _WO004_SESSION_A_ACCEPTED_GATE
            or auth_lines == [_ISSUED_SESSION_A_ACCEPTED]
            or _WO004_DECISION_HEADING in issued_text):
        return "A_ACCEPTED"
    return "NONE"


def _wo004_decision_record_findings(issued_text, rel):
    """The Session A decision record heading occurs exactly once."""
    headings = [line for line in issued_text.splitlines()
                if line.strip() == _WO004_DECISION_HEADING]
    if len(headings) == 1:
        return []
    return [(rel, "WO-004 Session A decision record", str(len(headings)),
             "exactly one " + _WO004_DECISION_HEADING)]


def _wo004_implementation_identity_findings(issued_text, rel):
    """The reviewed implementation's identity list, where Session C records it.

    The mandate has exactly one Session C authorization section. Inside it,
    exactly one paragraph is the introduction, followed by the four identity
    lines in order as a paragraph of their own, followed by the closing
    explanation. No identity is declared anywhere else in the mandate: each
    kind's declarations are counted over the whole file, so a decoy, a
    conflicting or additional entry, or the complete block moved out of the
    section cannot satisfy the record.
    """
    kind = "WO-004 Session C implementation identity"
    expected = len(_WO004_SESSION_C_IMPLEMENTATION)
    findings = []
    declared = [
        match.group(1)
        for match in _WO004_IDENTITY_DECLARATION.finditer(
            " ".join(issued_text.split()))
    ]
    for term in ("Git blob", "SHA-256"):
        if declared.count(term) != expected:
            findings.append((
                rel, kind,
                str(declared.count(term)) + " " + term + " declarations",
                "exactly " + str(expected) + ", all in the Session C "
                "identity list"))
    lines = issued_text.splitlines()
    starts = [index for index, line in enumerate(lines)
              if line == _WO004_SESSION_C_BASIS_HEADING]
    if len(starts) != 1:
        findings.append((
            rel, kind,
            str(len(starts)) + " Session C authorization sections",
            "exactly one " + _WO004_SESSION_C_BASIS_HEADING))
        return findings
    end = next((index for index in range(starts[0] + 1, len(lines))
                if lines[index].startswith("## ")), len(lines))
    blocks = _paragraphs("\n".join(lines[starts[0] + 1:end]))
    records = [
        index for index in range(len(blocks) - 2)
        if " ".join(" ".join(blocks[index]).split())
        == _WO004_SESSION_C_IDENTITY_INTRO
        and tuple(blocks[index + 1]) == _WO004_SESSION_C_IMPLEMENTATION_LINES
        and " ".join(" ".join(blocks[index + 2]).split())
        == _WO004_SESSION_C_IDENTITY_CLOSING
    ]
    if len(records) != 1:
        findings.append((
            rel, kind,
            str(len(records)) + " canonical identity lists in the Session C "
            "authorization section",
            "exactly one: the introduction, the four reviewed identities in "
            "order, and the closing explanation"))
    return findings


def _wo004_issuance_findings(pointer, issued_text, rel, state_key,
                             surface="both"):
    """WO-004's issuance record on the two surfaces that declare it.

    Called from outside the session branches on purpose: authorizing or
    accepting a session must not silence the record that issued the Work
    Order. `state_key` comes from _wo004_state_key, or is "COMPLETED" when
    the mandate is under completed/. `surface` limits a state-driven check to
    the "pointer" or the "document" half, as WO-003's completed checks are
    split, so the document half can stay bound to the artifact.

    That includes the base commit. _WO004_POINTER_KEYS pins its exact
    value from here, in EVERY session state - not only while the session
    is closed. The closed-session branch adds a second comparison that
    names the base directly, but it is not the only pin, so a later
    authorization gate cannot move the base by editing WORKORDER.md
    alone: it must update this file too.
    """
    def pointer_stop(line: str) -> bool:
        return _WO001_COMPLETED_LINK in line

    def document_stop(line: str) -> bool:
        return line.startswith("## ")

    out = []
    state = _WO004_STATES.get(state_key) if state_key else None
    if state is None:
        # An unrecognized session value is its own finding in the session
        # branch below. The issuance declarations are common to every
        # valid state, so they are still counted here - a rogue value
        # must not be a way to silence the record that issued the order.
        # Distinct loop names: this branch and the state-driven one below
        # bind differently shaped key tuples, and reusing one name makes the
        # second assignment a type error rather than a wider inference.
        for surface, text, stop, common_keys, where in (
            ("WORKORDER.md", pointer, pointer_stop,
             _WO004_POINTER_KEYS[1:], "WORKORDER.md"),
            (rel, issued_text, document_stop, _WO004_ISSUED_KEYS,
             "issued record"),
        ):
            for kind, found, want in _canonical_key_findings(
                text, stop, common_keys,
                "WO-004 issuance declaration (" + where + ")",
            ):
                out.append((surface, kind, found, want))
        return out
    (pointer_sequence, pointer_keys, issued_sequence, issued_keys,
     next_gate, statement) = state
    for half, target, text, stop, sequence, keys, where in (
        ("pointer", "WORKORDER.md", pointer, pointer_stop, pointer_sequence,
         pointer_keys, "WORKORDER.md"),
        ("document", rel, issued_text, document_stop, issued_sequence,
         issued_keys, "issued record"),
    ):
        if surface not in ("both", half):
            continue
        for kind, found, want in _canonical_field_findings(
            text, sequence, stop, where,
            exact={item for item in sequence if "`" in item},
            terminal=True, label="WO-004 issuance field",
        ):
            out.append((target, kind, found, want))
        for kind, found, want in _canonical_key_findings(
            text, stop, keys,
            "WO-004 issuance declaration (" + where + ")",
        ):
            out.append((target, kind, found, want))
    if surface == "pointer":
        return out
    normalized = " ".join(issued_text.split())
    wordings = [(_WO004_ISSUANCE_STATEMENT, "WO-004 issuance statement"),
                (next_gate, "WO-004 next gate")]
    if statement is not None:
        wordings.append((statement, "WO-004 session A statement"))
    for wording, kind in wordings:
        if normalized.count(wording) != 1:
            out.append((rel, kind, str(normalized.count(wording)),
                        "exactly one " + wording))
    return out


# WO-005's issuance record, with the same two canonical surfaces as WO-004's:
# the root pointer's bullet block and the mandate's metadata block. Each is an
# exact, contiguous, terminal slice whose keys are also counted, so a
# restatement, a decoy, or a duplicate cannot satisfy a corrupted or missing
# declaration. The issuance evidence identifies the accepted proposal commit,
# not the later transition commit, and the planning baseline stays at the
# revision the proposal was reviewed against.
_WO005_ID, _WO005_NAME = _RELEASE_TRAIN[4]
_WO005_PLANNING_BASELINE = "1925ba8a09c3696d25de7ffc3f23caf970362c4d"
_WO005_ISSUANCE_COMMIT = "528f1962c0c45c0631bab3637f3fd40db6317027"
_WO005_ISSUANCE_WORKFLOW = "36529997892"
_WO005_ISSUANCE_JOB = "109281301869"
_WO005_ISSUED_SEQUENCE = (
    "BASELINE: `" + _WO005_PLANNING_BASELINE + "`",
    "ISSUANCE_COMMIT: `" + _WO005_ISSUANCE_COMMIT + "`",
    "ISSUANCE_CI_WORKFLOW: `" + _WO005_ISSUANCE_WORKFLOW + "`",
    "ISSUANCE_CI_JOB: `" + _WO005_ISSUANCE_JOB + "` — Lint, types, tests",
)
# Unlike WO-004's, whose base moved with every session gate, this slice pins
# the base value itself, so a corrupted base cannot hide behind a byte-correct
# copy parked elsewhere. These pins cover evidence only: they do not restrict
# the authorized-session value, and a later transition that changes the base
# must update them.
_WO005_POINTER_SEQUENCE = (
    "- Current issued Work Order:",
    "- Authorized session:",
    "- Base commit: `" + _WO005_ISSUANCE_COMMIT + "`",
    "- Current gate:",
    "- Issuance commit: `" + _WO005_ISSUANCE_COMMIT + "`",
    "- Issuance CI workflow: `" + _WO005_ISSUANCE_WORKFLOW + "`",
    "- Issuance CI job: `" + _WO005_ISSUANCE_JOB + "` — Lint, types, tests",
    "- Release train:",
    "- Release gate:",
)
_WO005_POINTER_KEYS = (
    ("- Base commit:", _WO005_POINTER_SEQUENCE[2]),
    ("- Issuance commit:", _WO005_POINTER_SEQUENCE[4]),
    ("- Issuance CI workflow:", _WO005_POINTER_SEQUENCE[5]),
    ("- Issuance CI job:", _WO005_POINTER_SEQUENCE[6]),
)
_WO005_ISSUED_KEYS = (
    ("BASELINE:", _WO005_ISSUED_SEQUENCE[0]),
    ("ISSUANCE_COMMIT:", _WO005_ISSUED_SEQUENCE[1]),
    ("ISSUANCE_CI_WORKFLOW:", _WO005_ISSUED_SEQUENCE[2]),
    ("ISSUANCE_CI_JOB:", _WO005_ISSUED_SEQUENCE[3]),
)
# Authorizing Session A adds three declarations to each canonical block and
# moves the base to the Session A authorization commit. The issuance
# declarations stay inside the same exact, terminal slice.
_WO005_SESSION_A_COMMIT = "867074f8a520450ef6073b4c922079a897a83886"
_WO005_SESSION_A_WORKFLOW = "36596756689"
_WO005_SESSION_A_JOB = "109503539592"
_WO005_SESSION_A_GATE = (
    "WO-005 SESSION A AUTHORIZED — OFFLINE COVERAGE MODEL ONLY"
)
_WO005_SESSION_A_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR OFFLINE COVERAGE "
    "MODEL ONLY"
)
_WO005_SESSION_A_ISSUED_SEQUENCE = _WO005_ISSUED_SEQUENCE + (
    "SESSION_A_AUTHORIZATION_COMMIT: `" + _WO005_SESSION_A_COMMIT + "`",
    "SESSION_A_AUTHORIZATION_CI_WORKFLOW: `"
    + _WO005_SESSION_A_WORKFLOW + "`",
    "SESSION_A_AUTHORIZATION_CI_JOB: `" + _WO005_SESSION_A_JOB + "` "
    + "— Lint, types, tests",
)
_WO005_SESSION_A_POINTER_SEQUENCE = (
    _WO005_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _WO005_SESSION_A_COMMIT + "`",)
    + _WO005_POINTER_SEQUENCE[3:7]
    + ("- Session A authorization commit: `"
       + _WO005_SESSION_A_COMMIT + "`",
       "- Session A authorization CI workflow: `"
       + _WO005_SESSION_A_WORKFLOW + "`",
       "- Session A authorization CI job: `" + _WO005_SESSION_A_JOB + "` "
       + "— Lint, types, tests")
    + _WO005_POINTER_SEQUENCE[7:]
)
_WO005_SESSION_A_POINTER_KEYS = (
    (("- Base commit:", _WO005_SESSION_A_POINTER_SEQUENCE[2]),)
    + _WO005_POINTER_KEYS[1:]
    + (("- Session A authorization commit:",
        _WO005_SESSION_A_POINTER_SEQUENCE[7]),
       ("- Session A authorization CI workflow:",
        _WO005_SESSION_A_POINTER_SEQUENCE[8]),
       ("- Session A authorization CI job:",
        _WO005_SESSION_A_POINTER_SEQUENCE[9]))
)
_WO005_SESSION_A_ISSUED_KEYS = _WO005_ISSUED_KEYS + (
    ("SESSION_A_AUTHORIZATION_COMMIT:", _WO005_SESSION_A_ISSUED_SEQUENCE[4]),
    ("SESSION_A_AUTHORIZATION_CI_WORKFLOW:",
     _WO005_SESSION_A_ISSUED_SEQUENCE[5]),
    ("SESSION_A_AUTHORIZATION_CI_JOB:", _WO005_SESSION_A_ISSUED_SEQUENCE[6]),
)
# The Session A record in the mandate. Each of its two sections is a closed
# record: everything from its heading to the next heading must normalize to
# the accepted text exactly, so an added term, a fused sentence, or an extra
# paragraph fails. The four headings around them are unique and consecutive in
# the canonical order, so a renamed original cannot hide behind a correct copy
# parked elsewhere.
_WO005_SESSION_A_BASIS_HEADING = "## Session A authorization basis"
_WO005_EXEMPTION_HEADING = "## Session A live-verification exemption"
_WO005_SESSION_A_HEADINGS = (
    "## Issuance basis",
    _WO005_SESSION_A_BASIS_HEADING,
    _WO005_EXEMPTION_HEADING,
    "## Revision provenance",
)
_WO005_SESSION_A_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO005_SESSION_A_WORKFLOW
)
_WO005_SESSION_A_BASIS_RECORD = (
    _WO005_SESSION_A_BASIS_HEADING + " Session A is authorized for the "
    "offline coverage model only under the current root `WORKORDER.md` gate "
    "alone. The recorded basis is commit `" + _WO005_SESSION_A_COMMIT
    + "`; [CI workflow `" + _WO005_SESSION_A_WORKFLOW + "`]("
    + _WO005_SESSION_A_RUN_URL + ") completed successfully, including "
    "required job [`" + _WO005_SESSION_A_JOB + "` — Lint, types, tests]("
    + _WO005_SESSION_A_RUN_URL + "/job/" + _WO005_SESSION_A_JOB + "). This "
    "gate covers exactly the scope in \"Proposed Session A — offline "
    "coverage model\" below: its six-path file scope, the migration shim, the "
    "acceptance tests, the static gates, the cleanup duties, and the "
    "exclusions, unchanged. Session A ends with its worktree uncommitted for "
    "independent review. It opens no deploy, editor launch, bridge startup, "
    "MCP call, commit, or push. The planning baseline and the issuance "
    "evidence above are preserved unchanged, and neither is the Session A "
    "basis."
)
_WO005_EXEMPTION_RECORD = (
    _WO005_EXEMPTION_HEADING + " The owner accepted the live-verification "
    "exemption proposed for Session A under \"Live verification\" below, on "
    "these terms only: - It applies only to the offline Session A scope "
    "accepted above. - Session A changes no tool, registry, startup, bridge, "
    "dashboard, or editor behaviour. - The only `Content/Python/` change "
    "permitted during implementation is the standalone `list_untested.py` "
    "migration shim specified under \"Migration shim\" below. - Offline tests "
    "and source mappings are not live execution evidence. - Any editor or "
    "runtime impact discovered during implementation stops Session A for a "
    "new owner decision; it does not silently widen this exemption. - The "
    "eventual implementation commit must explain this exemption truthfully "
    "through the existing `Live-Verification: not-required — <reason>` "
    "trailer. - This exemption grants no commit, push, deployment, or "
    "live-run permission."
)
_WO005_SESSION_A_NEXT_GATE = (
    "NEXT GATE: fresh independent review of the complete uncommitted Session "
    "A implementation, which is limited to the offline coverage model, "
    "followed by separate owner gates for its commit and its push. Deploy, "
    "live runs, the deferred integration run, and WO-005 completion remain "
    "closed."
)
# The pointer's own Session A record: the statement with its basis evidence
# and the accepted exemption, then the restriction that follows it. The record
# occurs once, and once more anchored to the historical issuance note before
# it, which occurs once too - so neither a duplicate nor a decoy copy can
# stand in for it.
_WO005_ISSUANCE_POINTER_HISTORY = (
    "At its issuance gate, WO-005 gave no implementation authority and opened "
    "no session. Session A needed its own separate owner gate recorded in "
    "this pointer, and the live-verification exemption proposed for it was "
    "not accepted at that gate."
)
_WO005_SESSION_A_POINTER_RECORD = (
    "Session A is authorized under this pointer for the offline coverage "
    "model only, on the basis of commit `" + _WO005_SESSION_A_COMMIT + "`, "
    "successful CI workflow `" + _WO005_SESSION_A_WORKFLOW + "`, and "
    "successful required job `" + _WO005_SESSION_A_JOB + "` (`Lint, types, "
    "tests`). It covers the Session A scope recorded in the issued mandate, "
    "unchanged, and ends with that worktree uncommitted for independent "
    "review. The owner accepted the proposed live-verification exemption for "
    "that offline scope only, on the terms recorded in the mandate; it grants "
    "no commit, push, deploy, or live run. Session A opens no deploy, UEFN "
    "launch, bridge startup, MCP call, commit, or push."
)
_WO005_SESSION_A_POINTER_ANCHORED = (
    _WO005_ISSUANCE_POINTER_HISTORY + " " + _WO005_SESSION_A_POINTER_RECORD
)
# Completing WO-005 adds the completion basis - the implementation commit and
# its CI - to each canonical block and moves the base to that commit. The
# completion transition's own commit is not recorded: it does not exist when
# the transition is written. Every earlier declaration stays inside the same
# exact, terminal slice.
_WO005_COMPLETION_COMMIT = "5ef3aef2934b33a357ab9114e68aae41bc78639c"
_WO005_COMPLETION_WORKFLOW = "36662471593"
_WO005_COMPLETION_JOB = "109719997181"
_WO005_COMPLETED_GATE = (
    "WO-005 COMPLETED — WO-006 PROPOSED AND NOT AUTHORIZED"
)
_WO005_COMPLETED_ISSUED_SEQUENCE = _WO005_SESSION_A_ISSUED_SEQUENCE + (
    "COMPLETION_BASIS_COMMIT: `" + _WO005_COMPLETION_COMMIT + "`",
    "COMPLETION_BASIS_CI_WORKFLOW: `" + _WO005_COMPLETION_WORKFLOW + "`",
    "COMPLETION_BASIS_CI_JOB: `" + _WO005_COMPLETION_JOB + "` "
    + "— Lint, types, tests",
)
_WO005_COMPLETED_POINTER_SEQUENCE = (
    _WO005_SESSION_A_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _WO005_COMPLETION_COMMIT + "`",)
    + _WO005_SESSION_A_POINTER_SEQUENCE[3:10]
    + ("- Completion basis commit: `" + _WO005_COMPLETION_COMMIT + "`",
       "- Completion basis CI workflow: `"
       + _WO005_COMPLETION_WORKFLOW + "`",
       "- Completion basis CI job: `" + _WO005_COMPLETION_JOB + "` "
       + "— Lint, types, tests")
    + _WO005_SESSION_A_POINTER_SEQUENCE[10:]
)
_WO005_COMPLETED_POINTER_KEYS = (
    (("- Base commit:", _WO005_COMPLETED_POINTER_SEQUENCE[2]),)
    + _WO005_SESSION_A_POINTER_KEYS[1:]
    + (("- Completion basis commit:", _WO005_COMPLETED_POINTER_SEQUENCE[10]),
       ("- Completion basis CI workflow:",
        _WO005_COMPLETED_POINTER_SEQUENCE[11]),
       ("- Completion basis CI job:", _WO005_COMPLETED_POINTER_SEQUENCE[12]))
)
_WO005_COMPLETED_ISSUED_KEYS = _WO005_SESSION_A_ISSUED_KEYS + (
    ("COMPLETION_BASIS_COMMIT:", _WO005_COMPLETED_ISSUED_SEQUENCE[7]),
    ("COMPLETION_BASIS_CI_WORKFLOW:", _WO005_COMPLETED_ISSUED_SEQUENCE[8]),
    ("COMPLETION_BASIS_CI_JOB:", _WO005_COMPLETED_ISSUED_SEQUENCE[9]),
)
# Once WO-005 is completed, its mandate records Session A's authorization as
# history, adds the completion record, and keeps the accepted exemption terms
# unchanged. The same closed-record and heading checks keep running against it.
_WO005_COMPLETION_HEADING = "## Completion record"
_WO005_COMPLETED_HEADINGS = (
    _WO005_SESSION_A_HEADINGS[:3] + (_WO005_COMPLETION_HEADING,)
    + _WO005_SESSION_A_HEADINGS[3:]
)
_WO005_COMPLETED_BASIS_RECORD = (
    _WO005_SESSION_A_BASIS_HEADING + " At the Session A authorization gate, "
    "Session A was authorized for the offline coverage model only under the "
    "root `WORKORDER.md` gate. The recorded basis is commit `"
    + _WO005_SESSION_A_COMMIT + "`; [CI workflow `"
    + _WO005_SESSION_A_WORKFLOW + "`](" + _WO005_SESSION_A_RUN_URL
    + ") completed successfully, including required job [`"
    + _WO005_SESSION_A_JOB + "` — Lint, types, tests]("
    + _WO005_SESSION_A_RUN_URL + "/job/" + _WO005_SESSION_A_JOB + "). That "
    "gate covered exactly the scope in \"Proposed Session A — offline "
    "coverage model\" below: its six-path file scope, the migration shim, "
    "the acceptance tests, the static gates, the cleanup duties, and the "
    "exclusions, unchanged. Session A ended with its worktree uncommitted for "
    "independent review. It opened no deploy, editor launch, bridge startup, "
    "MCP call, commit, or push. The planning baseline and the issuance "
    "evidence above are preserved unchanged, and neither is the Session A "
    "basis."
)
# Pinned exactly once in the completed mandate, a frozen record of what was
# true at its own gate, which keeps the clause about WO-006's state. The root
# pointer pins only the prefix, which stays true when WO-006 is issued.
_WO005_COMPLETED_STATEMENT = (
    "WO-005 is complete; no session is authorized. WO-006 remains proposed "
    "and unauthorized."
)
_WO005_COMPLETED_POINTER_CLAUSE = (
    "WO-005 is complete; no session is authorized."
)
_WO005_COMPLETED_NEXT_GATE = (
    "NEXT GATE: separate owner authorization for a fresh independent WO-006 "
    "pre-issuance review, after this completion transition is accepted, "
    "committed, pushed, and green. Completion of WO-005 does not issue or "
    "authorize WO-006, which remains proposed and unauthorized."
)


def _wo005_closed_section(lines, heading):
    """The normalized text from `heading` up to the next heading."""
    start = lines.index(heading)
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].startswith("## ")), len(lines))
    return " ".join(" ".join(lines[start:end]).split())


def _wo005_session_a_record_findings(pointer, issued_text, rel,
                                     completed=False):
    """Session A's record while Session A is open, and after completion.

    In the mandate, the headings around the record are unique and consecutive
    in the canonical order; the authorization basis and the exemption are
    closed records, each equal to its accepted text; and the next gate occurs
    once, with no second next gate beside it. While Session A is open, the
    pointer's issuance note, Session A record, and the record anchored to the
    note each occur exactly once. Once WO-005 is completed, the basis is its
    past-tense record, the completion record joins the headings, the next gate
    is the completion gate, and the pointer's Session A record is history.
    """
    out = []
    headings_wanted: tuple[str, ...]
    if completed:
        headings_wanted = _WO005_COMPLETED_HEADINGS
        basis_record = _WO005_COMPLETED_BASIS_RECORD
        next_gate = _WO005_COMPLETED_NEXT_GATE
    else:
        headings_wanted = _WO005_SESSION_A_HEADINGS
        basis_record = _WO005_SESSION_A_BASIS_RECORD
        next_gate = _WO005_SESSION_A_NEXT_GATE
        normalized_pointer = " ".join(pointer.split())
        for required in (_WO005_ISSUANCE_POINTER_HISTORY,
                         _WO005_SESSION_A_POINTER_RECORD,
                         _WO005_SESSION_A_POINTER_ANCHORED):
            if normalized_pointer.count(required) != 1:
                out.append(("WORKORDER.md",
                            "WO-005 Session A pointer statement",
                            str(normalized_pointer.count(required)),
                            "exactly one " + required))
    lines = [line.strip() for line in issued_text.splitlines()]
    headings = [line for line in lines if line.startswith("## ")]
    unique = True
    for heading in headings_wanted:
        if headings.count(heading) != 1:
            unique = False
            out.append((rel, "WO-005 Session A record heading",
                        str(headings.count(heading)), "exactly one " + heading))
    if unique:
        first = headings.index(headings_wanted[0])
        found = tuple(headings[first:first + len(headings_wanted)])
        if found != headings_wanted:
            out.append((rel, "WO-005 Session A record heading",
                        " / ".join(found),
                        "consecutive " + " / ".join(headings_wanted)))
    for heading, record, kind in (
        (_WO005_SESSION_A_BASIS_HEADING, basis_record,
         "WO-005 Session A authorization statement"),
        (_WO005_EXEMPTION_HEADING, _WO005_EXEMPTION_RECORD,
         "WO-005 Session A exemption record"),
    ):
        if headings.count(heading) == 1:
            section = _wo005_closed_section(lines, heading)
            if section != record:
                out.append((rel, kind, "a section that differs from the "
                            "accepted record", "exactly " + record))
    normalized = " ".join(issued_text.split())
    if normalized.count(next_gate) != 1:
        out.append((rel, "WO-005 next gate",
                    str(normalized.count(next_gate)),
                    "exactly one " + next_gate))
    gates = [line for line in lines if line.startswith("NEXT GATE:")]
    if len(gates) != 1:
        out.append((rel, "WO-005 next gate", str(len(gates)),
                    "exactly one NEXT GATE"))
    return out


def _wo005_issuance_findings(pointer, issued_text, rel, session,
                             surface="both"):
    """WO-005's issuance record on the two surfaces that declare it.

    This pins the issuance evidence and the root base value, and once Session
    A is authorized, the Session A authorization evidence beside them; once
    WO-005 is completed ("COMPLETED"), the completion basis too. The session
    value only selects which shape applies; the gate and the marker are
    checked by the branches that call this. A later transition that changes
    the base commit must update these pins - the visible act the governance
    model wants. `surface` limits the check to the pointer or the document,
    so the document half can keep running under a later pointer owner.
    """
    if surface not in ("both", "pointer", "document"):
        raise ValueError("unknown surface: " + repr(surface))
    shapes: tuple[tuple[tuple[str, ...], tuple[tuple[str, str], ...]], ...]
    if session == "COMPLETED":
        shapes = ((_WO005_COMPLETED_POINTER_SEQUENCE,
                   _WO005_COMPLETED_POINTER_KEYS),
                  (_WO005_COMPLETED_ISSUED_SEQUENCE,
                   _WO005_COMPLETED_ISSUED_KEYS))
    elif session == "A":
        shapes = ((_WO005_SESSION_A_POINTER_SEQUENCE,
                   _WO005_SESSION_A_POINTER_KEYS),
                  (_WO005_SESSION_A_ISSUED_SEQUENCE,
                   _WO005_SESSION_A_ISSUED_KEYS))
    else:
        shapes = ((_WO005_POINTER_SEQUENCE, _WO005_POINTER_KEYS),
                  (_WO005_ISSUED_SEQUENCE, _WO005_ISSUED_KEYS))
    out = []
    for target, text, stop, (sequence, keys), where in (
        ("WORKORDER.md", pointer,
         lambda line: _WO001_COMPLETED_LINK in line,
         shapes[0], "WORKORDER.md"),
        (rel, issued_text, lambda line: line.startswith("## "),
         shapes[1], "issued record"),
    ):
        if surface == ("document" if target == "WORKORDER.md" else "pointer"):
            continue
        for kind, found, want in _canonical_field_findings(
            text, sequence, stop, where,
            exact={item for item in sequence if "`" in item},
            terminal=True, label="WO-005 issuance field",
        ):
            out.append((target, kind, found, want))
        for kind, found, want in _canonical_key_findings(
            text, stop, keys, "WO-005 issuance declaration (" + where + ")",
        ):
            out.append((target, kind, found, want))
    return out


# WO-006's issuance record, on the same two canonical surfaces as WO-005's:
# the root pointer's bullet block and the mandate's metadata block, each an
# exact, contiguous, terminal slice whose keys are also counted. The evidence
# identifies the accepted proposal commit, not the later transition commit,
# and the planning baseline stays at the revision the proposal was reviewed
# against. These pins cover evidence only; a later transition that changes
# the base must update them.
_WO006_ID, _WO006_NAME = _RELEASE_TRAIN[5]
_WO006_PLANNING_BASELINE = "f9354feaf4ab072c9941ab4d6ec8337395ce18a0"
_WO006_ISSUANCE_COMMIT = "0c0bf26191ee953c7a27237109b4a91a4db97275"
_WO006_ISSUANCE_WORKFLOW = "36743995194"
_WO006_ISSUANCE_JOB = "109985389182"
_WO006_ISSUED_SEQUENCE = (
    "BASELINE: `" + _WO006_PLANNING_BASELINE + "`",
    "ISSUANCE_COMMIT: `" + _WO006_ISSUANCE_COMMIT + "`",
    "ISSUANCE_CI_WORKFLOW: `" + _WO006_ISSUANCE_WORKFLOW + "`",
    "ISSUANCE_CI_JOB: `" + _WO006_ISSUANCE_JOB + "` — Lint, types, tests",
)
_WO006_POINTER_SEQUENCE = (
    "- Current issued Work Order:",
    "- Authorized session:",
    "- Base commit: `" + _WO006_ISSUANCE_COMMIT + "`",
    "- Current gate:",
    "- Issuance commit: `" + _WO006_ISSUANCE_COMMIT + "`",
    "- Issuance CI workflow: `" + _WO006_ISSUANCE_WORKFLOW + "`",
    "- Issuance CI job: `" + _WO006_ISSUANCE_JOB + "` — Lint, types, tests",
    "- Release train:",
    "- Release gate:",
)
_WO006_POINTER_KEYS = (
    ("- Base commit:", _WO006_POINTER_SEQUENCE[2]),
    ("- Issuance commit:", _WO006_POINTER_SEQUENCE[4]),
    ("- Issuance CI workflow:", _WO006_POINTER_SEQUENCE[5]),
    ("- Issuance CI job:", _WO006_POINTER_SEQUENCE[6]),
)
_WO006_ISSUED_KEYS = (
    ("BASELINE:", _WO006_ISSUED_SEQUENCE[0]),
    ("ISSUANCE_COMMIT:", _WO006_ISSUED_SEQUENCE[1]),
    ("ISSUANCE_CI_WORKFLOW:", _WO006_ISSUED_SEQUENCE[2]),
    ("ISSUANCE_CI_JOB:", _WO006_ISSUED_SEQUENCE[3]),
)
# Authorizing Session A adds three declarations to each canonical block and
# moves the base to the Session A authorization commit, as WO-005's did. The
# issuance declarations stay inside the same exact, terminal slice. The
# Session A evidence identifies the issued mandate; it establishes no harness
# implementation or test result.
_WO006_SESSION_A_COMMIT = "d46a30ed9de54ec01536d132e1032fcf762fa3c7"
_WO006_SESSION_A_WORKFLOW = "36756889729"
_WO006_SESSION_A_JOB = "110029304446"
_WO006_SESSION_A_GATE = (
    "WO-006 SESSION A AUTHORIZED — OFFLINE DESIGN AND HARNESS ONLY"
)
_WO006_SESSION_A_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR OFFLINE DESIGN AND "
    "HARNESS ONLY"
)
_WO006_SESSION_A_ISSUED_SEQUENCE = _WO006_ISSUED_SEQUENCE + (
    "SESSION_A_AUTHORIZATION_COMMIT: `" + _WO006_SESSION_A_COMMIT + "`",
    "SESSION_A_AUTHORIZATION_CI_WORKFLOW: `"
    + _WO006_SESSION_A_WORKFLOW + "`",
    "SESSION_A_AUTHORIZATION_CI_JOB: `" + _WO006_SESSION_A_JOB + "` "
    + "— Lint, types, tests",
)
_WO006_SESSION_A_POINTER_SEQUENCE = (
    _WO006_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _WO006_SESSION_A_COMMIT + "`",)
    + _WO006_POINTER_SEQUENCE[3:7]
    + ("- Session A authorization commit: `"
       + _WO006_SESSION_A_COMMIT + "`",
       "- Session A authorization CI workflow: `"
       + _WO006_SESSION_A_WORKFLOW + "`",
       "- Session A authorization CI job: `" + _WO006_SESSION_A_JOB + "` "
       + "— Lint, types, tests")
    + _WO006_POINTER_SEQUENCE[7:]
)
_WO006_SESSION_A_POINTER_KEYS = (
    (("- Base commit:", _WO006_SESSION_A_POINTER_SEQUENCE[2]),)
    + _WO006_POINTER_KEYS[1:]
    + (("- Session A authorization commit:",
        _WO006_SESSION_A_POINTER_SEQUENCE[7]),
       ("- Session A authorization CI workflow:",
        _WO006_SESSION_A_POINTER_SEQUENCE[8]),
       ("- Session A authorization CI job:",
        _WO006_SESSION_A_POINTER_SEQUENCE[9]))
)
_WO006_SESSION_A_ISSUED_KEYS = _WO006_ISSUED_KEYS + (
    ("SESSION_A_AUTHORIZATION_COMMIT:", _WO006_SESSION_A_ISSUED_SEQUENCE[4]),
    ("SESSION_A_AUTHORIZATION_CI_WORKFLOW:",
     _WO006_SESSION_A_ISSUED_SEQUENCE[5]),
    ("SESSION_A_AUTHORIZATION_CI_JOB:", _WO006_SESSION_A_ISSUED_SEQUENCE[6]),
)
# The Session A record in the mandate is one closed section: everything from
# its heading to the next heading must normalize to the accepted text exactly,
# so a widened scope, a fused sentence, or an extra paragraph fails. The three
# headings around it are unique and consecutive in the canonical order. The
# pointer's record occurs once, and once more anchored to the historical
# issuance note before it, which occurs once too.
_WO006_SESSION_A_BASIS_HEADING = "## Session A authorization basis"
_WO006_SESSION_A_HEADINGS = (
    "## Issuance basis",
    _WO006_SESSION_A_BASIS_HEADING,
    "## Revision provenance",
)
_WO006_SESSION_A_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO006_SESSION_A_WORKFLOW
)
_WO006_SESSION_A_BASIS_RECORD = (
    _WO006_SESSION_A_BASIS_HEADING + " Session A is authorized for the "
    "offline design and harness only under the current root `WORKORDER.md` "
    "gate alone. The recorded basis is commit `" + _WO006_SESSION_A_COMMIT
    + "`; [CI workflow `" + _WO006_SESSION_A_WORKFLOW + "`]("
    + _WO006_SESSION_A_RUN_URL + ") completed successfully, including "
    "required job [`" + _WO006_SESSION_A_JOB + "` — Lint, types, tests]("
    + _WO006_SESSION_A_RUN_URL + "/job/" + _WO006_SESSION_A_JOB + "). That "
    "commit and its CI are evidence for this issued mandate; they establish "
    "no harness implementation and no test result. This gate covers exactly "
    "the scope in \"Proposed Session A — offline design and harness\" below, "
    "unchanged: `harness.py` and the data-only `config.json`, `analysis.py` "
    "and `plan.md`, the synthetic results and summary, and testing against "
    "local stubs, with the artifacts and their SHA-256 hashes kept in the "
    "owner's private evidence folder. Session A changes no repository file. "
    "The four clarifications recorded under \"Issuance basis\" remain "
    "questions for `plan.md` to settle and for its review to examine; this "
    "gate decides none of them. Session A ends with its artifacts held for "
    "independent review. It opens no deploy, editor launch, bridge startup, "
    "MCP call, connection to a real editor endpoint, live measurement, "
    "commit, or push, and Session B stays closed. The planning baseline and "
    "the issuance evidence above are preserved unchanged, and neither is the "
    "Session A basis."
)
_WO006_SESSION_A_NEXT_GATE = (
    "NEXT GATE: execution of the accepted offline Session A scope, limited to "
    "the offline design and harness, ending with its private artifacts held "
    "for independent review. Session B, connections to real editor "
    "endpoints, deploy, live measurement, commit, push, and WO-006 completion "
    "remain closed."
)
_WO006_ISSUANCE_POINTER_HISTORY = (
    "At its issuance gate, WO-006 gave no implementation authority and opened "
    "no session. Session A, the offline design and harness, needed its own "
    "separate owner gate recorded in this pointer, and Session B, the "
    "owner-operated live measurement, stayed closed behind it."
)
_WO006_SESSION_A_POINTER_RECORD = (
    "Session A is authorized under this pointer for the offline design and "
    "harness only, on the basis of commit `" + _WO006_SESSION_A_COMMIT
    + "`, successful CI workflow `" + _WO006_SESSION_A_WORKFLOW + "`, and "
    "successful required job `" + _WO006_SESSION_A_JOB + "` (`Lint, types, "
    "tests`). That evidence establishes the issued mandate, not any harness "
    "implementation or test result. It covers the Session A scope recorded "
    "in the issued mandate, unchanged, changes no repository file, and ends "
    "with its private artifacts held for independent review. Session A opens "
    "no deploy, UEFN launch, bridge startup, MCP call, connection to a real "
    "editor endpoint, live measurement, commit, or push, and Session B stays "
    "closed."
)
_WO006_SESSION_A_POINTER_ANCHORED = (
    _WO006_ISSUANCE_POINTER_HISTORY + " " + _WO006_SESSION_A_POINTER_RECORD
)


# The only statements allowed to grant WO-006's Session A anything: the
# pinned records - the gate and marker, checked exactly by the Session A
# branch, and the records _wo006_session_record_findings checks exactly.
_WO006_SESSION_A_CANONICAL = (
    _WO006_SESSION_A_GATE,
    _WO006_SESSION_A_AUTH,
    _WO006_SESSION_A_BASIS_RECORD,
    _WO006_SESSION_A_POINTER_RECORD,
    _WO006_ISSUANCE_POINTER_HISTORY,
    _WO006_SESSION_A_NEXT_GATE,
)
# Authorizing Session B records Session A's private acceptance and adds three
# more declarations to each canonical block, moving the base to the Session B
# authorization commit. That commit's CI tested the repository's checker and
# tests; it never ran the private harness, and the records say so. Session A's
# authorization basis stays in the mandate verbatim, as WO-004's did once its
# Session B opened, while the pointer's Session A record becomes history.
_WO006_SESSION_B_COMMIT = "8667b0e0ef78d504586d710984ef1a1fef7263b2"
_WO006_SESSION_B_WORKFLOW = "36801338578"
_WO006_SESSION_B_JOB = "110176132684"
_WO006_SESSION_B_GATE = (
    "WO-006 SESSION B AUTHORIZED — OWNER-OPERATED LIVE MEASUREMENT ONLY"
)
_WO006_SESSION_B_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION B AUTHORIZED FOR OWNER-OPERATED LIVE "
    "MEASUREMENT ONLY"
)
_WO006_SESSION_B_ISSUED_SEQUENCE = _WO006_SESSION_A_ISSUED_SEQUENCE + (
    "SESSION_B_AUTHORIZATION_COMMIT: `" + _WO006_SESSION_B_COMMIT + "`",
    "SESSION_B_AUTHORIZATION_CI_WORKFLOW: `"
    + _WO006_SESSION_B_WORKFLOW + "`",
    "SESSION_B_AUTHORIZATION_CI_JOB: `" + _WO006_SESSION_B_JOB + "` "
    + "— Lint, types, tests",
)
_WO006_SESSION_B_POINTER_SEQUENCE = (
    _WO006_SESSION_A_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _WO006_SESSION_B_COMMIT + "`",)
    + _WO006_SESSION_A_POINTER_SEQUENCE[3:10]
    + ("- Session B authorization commit: `"
       + _WO006_SESSION_B_COMMIT + "`",
       "- Session B authorization CI workflow: `"
       + _WO006_SESSION_B_WORKFLOW + "`",
       "- Session B authorization CI job: `" + _WO006_SESSION_B_JOB + "` "
       + "— Lint, types, tests")
    + _WO006_SESSION_A_POINTER_SEQUENCE[10:]
)
_WO006_SESSION_B_POINTER_KEYS = (
    (("- Base commit:", _WO006_SESSION_B_POINTER_SEQUENCE[2]),)
    + _WO006_SESSION_A_POINTER_KEYS[1:]
    + (("- Session B authorization commit:",
        _WO006_SESSION_B_POINTER_SEQUENCE[10]),
       ("- Session B authorization CI workflow:",
        _WO006_SESSION_B_POINTER_SEQUENCE[11]),
       ("- Session B authorization CI job:",
        _WO006_SESSION_B_POINTER_SEQUENCE[12]))
)
_WO006_SESSION_B_ISSUED_KEYS = _WO006_SESSION_A_ISSUED_KEYS + (
    ("SESSION_B_AUTHORIZATION_COMMIT:", _WO006_SESSION_B_ISSUED_SEQUENCE[7]),
    ("SESSION_B_AUTHORIZATION_CI_WORKFLOW:",
     _WO006_SESSION_B_ISSUED_SEQUENCE[8]),
    ("SESSION_B_AUTHORIZATION_CI_JOB:", _WO006_SESSION_B_ISSUED_SEQUENCE[9]),
)
# Three closed sections in the mandate now, each equal to its accepted text:
# Session A's authorization basis (unchanged), its acceptance record, and the
# Session B authorization basis. The acceptance identifies the private
# artifacts by digest only and claims no CI run of the harness.
_WO006_SESSION_A_ACCEPTANCE_HEADING = "## Session A acceptance record"
_WO006_SESSION_B_BASIS_HEADING = "## Session B authorization basis"
_WO006_SESSION_B_HEADINGS = (
    "## Issuance basis",
    _WO006_SESSION_A_BASIS_HEADING,
    _WO006_SESSION_A_ACCEPTANCE_HEADING,
    _WO006_SESSION_B_BASIS_HEADING,
    "## Revision provenance",
)
_WO006_HARNESS_PACKAGE_SHA256 = (
    "f17a44a477b2fb2d3d347a75232c7076516ce110308aeb25c0efefad90dff3f8"
)
_WO006_HARNESS_REVIEW_SHA256 = (
    "a856bdfff88565831905b0e1fcd77862e408b0eb704774ac1631da9225ac94c1"
)
_WO006_SESSION_A_ACCEPTANCE_RECORD = (
    _WO006_SESSION_A_ACCEPTANCE_HEADING + " The owner accepted Session A's "
    "private offline artifacts after independent review, as offline "
    "preparation only and not as proof of live compatibility. The accepted "
    "harness package is identified by its `SHA256SUMS` digest `"
    + _WO006_HARNESS_PACKAGE_SHA256 + "`, and its preserved independent "
    "review by the `SHA256SUMS` digest `" + _WO006_HARNESS_REVIEW_SHA256
    + "`; both are kept in the owner's private evidence folder. The first "
    "review required fixes, the second revision made them, and the review of "
    "that revision accepted it with its limitations disclosed. `plan.md` "
    "settles the four clarifications recorded under \"Issuance basis\", and "
    "the first review examined them. The harness and its stub tests ran "
    "offline on the owner's Windows machine only. They have never run in "
    "GitHub CI, and no repository commit or CI run attests to them. Session A "
    "changed no repository file, made no live contact, and took no "
    "measurement. Session A is closed, and its authorization basis above is "
    "kept verbatim as the record of that gate."
)
_WO006_SESSION_B_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO006_SESSION_B_WORKFLOW
)
_WO006_SESSION_B_BASIS_RECORD = (
    _WO006_SESSION_B_BASIS_HEADING + " Session B is authorized for "
    "owner-operated live measurement only under the current root "
    "`WORKORDER.md` gate alone. The recorded basis is commit `"
    + _WO006_SESSION_B_COMMIT + "`; [CI workflow `"
    + _WO006_SESSION_B_WORKFLOW + "`](" + _WO006_SESSION_B_RUN_URL
    + ") completed successfully, including required job [`"
    + _WO006_SESSION_B_JOB + "` — Lint, types, tests]("
    + _WO006_SESSION_B_RUN_URL + "/job/" + _WO006_SESSION_B_JOB + "). That "
    "CI tested the repository's checker and tests at that commit. It did not "
    "run the private harness, and it establishes no live result. This gate "
    "covers exactly the scope in \"Proposed Session B — owner-operated live "
    "measurement\" below, unchanged, together with the operator procedure in "
    "the accepted `plan.md`. The owner operates UEFN and performs every owner "
    "check and attestation. The harness runs only after the owner's "
    "separate, explicit instruction to begin the live run, invoked by the "
    "owner or by the agent under the owner's direct supervision. The run uses "
    "the accepted harness files unchanged, each verified against the "
    "accepted package's `SHA256SUMS` before use, and `client.py` unchanged "
    "from the repository at the base commit above. The data-only "
    "configuration is filled from live `describe_toolset` output in a "
    "separate live copy, recorded with its SHA-256; the accepted package's "
    "stub configuration and every other file stay unchanged. The run uses the "
    "verified Python 3.13.5 interpreter. Actual response classes and "
    "measured wall times are preserved. An actual Toolbelt timeout remains "
    "UNKNOWN and follows the abort and barrier rules. The Toolbelt client "
    "applies its 10-second timeout to each socket operation, not to the whole "
    "call, so a confirmed response can take longer than 10 seconds. Any such "
    "response keeps its response class, is flagged explicitly wherever the "
    "results are reported, and is never presented as meeting a hard "
    "10-second whole-call deadline. The official client enforces a whole-call "
    "deadline with a watchdog whose overhead falls inside the official timing "
    "window only. Both asymmetries are disclosed with the results, and no "
    "estimated constant is subtracted. The owner accepted the harness's "
    "recorded limitations for this run, with no further harness revision. A "
    "timed-out call is not cancelled and may still act. SSE resumption, "
    "server-initiated requests, and unsupported protocol versions are not "
    "implemented and end their pair HARNESS-LIMITED. Discovery matches tool "
    "names by substring, and the confirmation calls back it up. Toolbelt "
    "exclusivity rests on the owner's attestation, because a caller in "
    "lockstep with the harness cannot be detected. A harness programming "
    "defect stops the run, and its record can then show the in-flight slot "
    "as NOT ATTEMPTED or, late in the run, lack the closing footer; a harness "
    "`ValueError` inside the official exchange reads conservatively as "
    "UNKNOWN. The stub tests ran on Windows only, against stubs that are not "
    "Epic's server. "
    "Session B ends with its private artifacts held for independent review. "
    "It opens no code change, fallback, emulation, policy change, live "
    "repair, commit, or push. A runtime defect, or any apparent need to "
    "change bridge, client, transport, harness, or policy code, stops the "
    "session for a new owner decision. The evidence-recording transition, "
    "WO-006 completion, and WO-007 remain closed. The planning baseline, the "
    "issuance evidence, and the Session A authorization evidence above are "
    "preserved unchanged, and none of them is the Session B basis."
)
_WO006_SESSION_B_NEXT_GATE = (
    "NEXT GATE: owner-operated execution of the accepted Session B scope, "
    "after the owner's separate instruction to begin the live run, ending "
    "with its private artifacts held for independent review. The "
    "evidence-recording transition, commit, push, WO-006 completion, and "
    "WO-007 remain closed."
)
# The pointer keeps the issuance note, turns Session A's record into history,
# records Session A's acceptance, and adds the one present-tense Session B
# record. Each occurs once, and once more anchored in that order.
_WO006_SESSION_A_POINTER_HISTORY = (
    "At the Session A authorization gate, this pointer opened the offline "
    "design and harness only, on the basis of commit `"
    + _WO006_SESSION_A_COMMIT + "`, successful CI workflow `"
    + _WO006_SESSION_A_WORKFLOW + "`, and successful required job `"
    + _WO006_SESSION_A_JOB + "` (`Lint, types, tests`). That evidence "
    "established the issued mandate, not any harness implementation or test "
    "result. That gate covered the Session A scope recorded in the issued "
    "mandate, unchanged, changed no repository file, and ended with its "
    "private artifacts held for independent review. It opened no deploy, "
    "UEFN launch, bridge startup, MCP call, connection to a real editor "
    "endpoint, live measurement, commit, or push, and Session B stayed closed "
    "at that gate."
)
_WO006_SESSION_A_POINTER_ACCEPTANCE = (
    "The owner accepted Session A's private offline artifacts after "
    "independent review, as offline preparation only and not as proof of "
    "live compatibility. The accepted harness package and its preserved "
    "independent review are kept in the owner's private evidence folder, "
    "identified by their `SHA256SUMS` digests `"
    + _WO006_HARNESS_PACKAGE_SHA256 + "` and `"
    + _WO006_HARNESS_REVIEW_SHA256 + "`. The harness and its stub tests ran "
    "offline on the owner's Windows machine only; they have never run in "
    "GitHub CI, and no repository commit or CI run attests to them. Session A "
    "is accepted and closed."
)
_WO006_SESSION_B_POINTER_RECORD = (
    "Session B is authorized under this pointer for owner-operated live "
    "measurement only, on the basis of commit `" + _WO006_SESSION_B_COMMIT
    + "`, successful CI workflow `" + _WO006_SESSION_B_WORKFLOW + "`, and "
    "successful required job `" + _WO006_SESSION_B_JOB + "` (`Lint, types, "
    "tests`). That CI tested the repository's checker and tests, not the "
    "private harness, and establishes no live result. It covers the Session B "
    "scope recorded in the issued mandate, unchanged: the owner operates UEFN "
    "and performs the owner checks, and the accepted harness runs only after "
    "the owner's separate, explicit instruction to begin the live run. "
    "Session B changes no repository file and ends with its private artifacts "
    "held for independent review. It opens no code change, fallback, "
    "emulation, policy change, live repair, commit, or push, and the "
    "evidence-recording transition and WO-006 completion stay closed."
)
_WO006_SESSION_B_POINTER_ANCHORED = " ".join((
    _WO006_ISSUANCE_POINTER_HISTORY,
    _WO006_SESSION_A_POINTER_HISTORY,
    _WO006_SESSION_A_POINTER_ACCEPTANCE,
    _WO006_SESSION_B_POINTER_RECORD,
))
# The mandate's unchanged technical body says the live configuration is
# something "Session B may fill". That one complete sentence, through its
# list, must occur exactly once in the mandate, and only that occurrence is
# exempt from the Session B widening scan. It is not exempt anywhere else,
# so a widened list, a grant fused after the colon, a second copy, or a copy
# in WORKORDER.md is still scanned.
_WO006_SESSION_B_CONFIG_SENTENCE = (
    "The harness takes a data-only configuration file that Session B may "
    "fill from the live `describe_toolset` output and record as evidence: "
    "official toolset and tool names, parameter names, the actor-identifier "
    "encoding, and the transform and rotation shapes for each surface."
)


# The only statements allowed to grant WO-006's Session B anything, in
# either file: the gate and marker, and the records
# _wo006_session_record_findings checks exactly. The current-session guard is
# reused unchanged with label "B" and this set; its known limits carry over.
_WO006_SESSION_B_CANONICAL = (
    _WO006_SESSION_B_GATE,
    _WO006_SESSION_B_AUTH,
    _WO006_SESSION_A_BASIS_RECORD,
    _WO006_SESSION_A_ACCEPTANCE_RECORD,
    _WO006_SESSION_B_BASIS_RECORD,
    _WO006_SESSION_B_NEXT_GATE,
    _WO006_ISSUANCE_POINTER_HISTORY,
    _WO006_SESSION_A_POINTER_HISTORY,
    _WO006_SESSION_A_POINTER_ACCEPTANCE,
    _WO006_SESSION_B_POINTER_RECORD,
)
# Closing WO-006 as superseded, without an accepted measurement, adds the
# closure basis - the base commit and its CI - to each canonical block and
# moves the base to that commit. The closure transition's own commit is not
# recorded: it does not exist when the transition is written. Every earlier
# declaration stays inside the same exact, terminal slice. That CI tested the
# checker and tests at the base commit; it establishes no live result.
_WO006_CLOSURE_COMMIT = "13e0bbb67f98ac3f33aff917737fcf9b77a3d64c"
_WO006_CLOSURE_WORKFLOW = "36817435116"
_WO006_CLOSURE_JOB = "110225453445"
_WO006_SUPERSEDED_STATUS = "STATUS: SUPERSEDED"
_WO006_SUPERSEDED_AUTH = (
    "AUTHORIZATION: SUPERSEDED — CLOSED WITHOUT AN ACCEPTED MEASUREMENT; NO "
    "SESSION AUTHORIZED"
)
_WO006_SUPERSEDED_GATE = (
    "WO-006 SUPERSEDED — WO-007 PROPOSED AND NOT AUTHORIZED"
)
_WO006_SUPERSEDED_ISSUED_SEQUENCE = _WO006_SESSION_B_ISSUED_SEQUENCE + (
    "CLOSURE_BASIS_COMMIT: `" + _WO006_CLOSURE_COMMIT + "`",
    "CLOSURE_BASIS_CI_WORKFLOW: `" + _WO006_CLOSURE_WORKFLOW + "`",
    "CLOSURE_BASIS_CI_JOB: `" + _WO006_CLOSURE_JOB + "` "
    + "— Lint, types, tests",
)
_WO006_SUPERSEDED_POINTER_SEQUENCE = (
    _WO006_SESSION_B_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _WO006_CLOSURE_COMMIT + "`",)
    + _WO006_SESSION_B_POINTER_SEQUENCE[3:13]
    + ("- Closure basis commit: `" + _WO006_CLOSURE_COMMIT + "`",
       "- Closure basis CI workflow: `" + _WO006_CLOSURE_WORKFLOW + "`",
       "- Closure basis CI job: `" + _WO006_CLOSURE_JOB + "` "
       + "— Lint, types, tests")
    + _WO006_SESSION_B_POINTER_SEQUENCE[13:]
)
_WO006_SUPERSEDED_POINTER_KEYS = (
    (("- Base commit:", _WO006_SUPERSEDED_POINTER_SEQUENCE[2]),)
    + _WO006_SESSION_B_POINTER_KEYS[1:]
    + (("- Closure basis commit:", _WO006_SUPERSEDED_POINTER_SEQUENCE[13]),
       ("- Closure basis CI workflow:",
        _WO006_SUPERSEDED_POINTER_SEQUENCE[14]),
       ("- Closure basis CI job:", _WO006_SUPERSEDED_POINTER_SEQUENCE[15]))
)
_WO006_SUPERSEDED_ISSUED_KEYS = _WO006_SESSION_B_ISSUED_KEYS + (
    ("CLOSURE_BASIS_COMMIT:", _WO006_SUPERSEDED_ISSUED_SEQUENCE[10]),
    ("CLOSURE_BASIS_CI_WORKFLOW:", _WO006_SUPERSEDED_ISSUED_SEQUENCE[11]),
    ("CLOSURE_BASIS_CI_JOB:", _WO006_SUPERSEDED_ISSUED_SEQUENCE[12]),
)
# The superseded mandate keeps Session A's and Session B's authorization bases
# and Session A's acceptance record verbatim, each still a closed section equal
# to its accepted text, and adds one closed closure section after them. The
# closure section opens with the note that the kept bases grant nothing.
_WO006_CLOSURE_HEADING = "## Closure amendment (owner decision)"
_WO006_SUPERSEDED_HEADINGS = (
    _WO006_SESSION_B_HEADINGS[:4] + (_WO006_CLOSURE_HEADING,)
    + _WO006_SESSION_B_HEADINGS[4:]
)
_WO006_CLOSURE_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO006_CLOSURE_WORKFLOW
)
_WO006_KEPT_BASES_NOTE = (
    "The Session A and Session B authorization bases above are kept verbatim "
    "as the records of their gates; neither grants anything."
)
_WO006_CLOSURE_RECORD = (
    _WO006_CLOSURE_HEADING + " " + _WO006_KEPT_BASES_NOTE + " On 2026-10-01 "
    "the owner decided: \"I decline further benchmark attempts under WO-006. "
    "Any future benchmark requires a new proposal.\" On 2026-10-02 the owner "
    "adopted the independently accepted closure proposal and authorized this "
    "transition. WO-006 is superseded: it closed without an accepted "
    "measurement, and it has no successor. The closure basis is commit `"
    + _WO006_CLOSURE_COMMIT + "`; [CI workflow `" + _WO006_CLOSURE_WORKFLOW
    + "`](" + _WO006_CLOSURE_RUN_URL + ") completed successfully, including "
    "required job [`" + _WO006_CLOSURE_JOB + "` — Lint, types, tests]("
    + _WO006_CLOSURE_RUN_URL + "/job/" + _WO006_CLOSURE_JOB + "). That CI "
    "tested the repository's checker and tests at that commit. It "
    "establishes no live result. Session A's offline preparation was "
    "accepted as recorded above, as offline preparation only and not as "
    "proof of live compatibility. **What live-1 established (independently "
    "verified; not a WO-006 result).** One live run, live-1, took place under "
    "the Session B gate and was independently rejected. All 299 command calls "
    "returned SUCCESS, and the 3 official lifecycle messages were "
    "ok/ok/closed. Both pairs ended MEASURED by the mandate's precedence. "
    "Each of the 72 transform sets was followed by a same-surface restore and "
    "a verifying re-read, and both final re-reads verified. Independent "
    "recomputation and recount (0 problems) reproduced every count. "
    "`client.py` and the accepted harness were unchanged. The private run "
    "folder is identified by the `SHA256SUMS` digest "
    "`0e7ec0450c01395263eb5d94d58c9bd6f91420dae93ab1136d701baa9ed7253f`. "
    "**Why live-1 was rejected.** - Foreground condition: NOT MET (not shown "
    "to hold). The editor's own log shows it ticking at 3 frames per second "
    "throughout the timed calls. That is consistent with, but not "
    "established as, background throttling (a minimized window or another "
    "throttle is not excluded; the 3 Hz cap is unverified on this build). "
    "The background-CPU setting was not recorded. - No-save requirement not "
    "met: the fixture's actor package was saved three times on 2026-10-01 "
    "(05:56Z and 06:07Z before any endpoint contact; 06:43Z after the "
    "harness ended), against \"Nothing is saved at any point\". The transform "
    "restores themselves all verified. None of the three saves fell inside "
    "the timed window. - Physics: the Details-panel physics check was not "
    "completed; live-1 went ahead under the owner's one-run physics "
    "exception. - Fixture class: `FortStaticMeshActor`, a native subclass of "
    "`StaticMeshActor`, was used under the owner's conditional class "
    "acceptance, a separate matter from the physics exception. - Fixture "
    "mobility: its mobility during the run is unresolved. **No accepted "
    "comparative measurement exists**, and the question in \"Problem\" "
    "remains unanswered. Closure makes no performance ranking and no "
    "compatibility or incompatibility finding (the NOT RUN rule in "
    "\"Outcomes — decision lock\" is applied by analogy), and it gives no "
    "support for removing, replacing, "
    "or deprecating the custom bridge. No timing figure from the rejected run "
    "is published. Before the owner's decision, a repeat had been planned "
    "under a private recovery plan, accepted on independent delta review, "
    "and its launcher was rehearsed twice: both rehearsals executed "
    "correctly, and neither produced a clean observation. The evidence stays "
    "private and is identified by `SHA256SUMS` digests: the rejection bundle "
    "`ea7c75459cec902c0d8fb2628ac58a1b83dc710c366a45ee7a085798b14a3cef`, the "
    "recovery plan "
    "`9716baa9c4b7ba757dbb52c9e757be19639b6c689ff71b9eed2db60f945b4eb6`, and "
    "the two rehearsals "
    "`12b287fdcdb8badf7678e914e8ecf13876c8973188899ef97dc95379d253b5b9` and "
    "`29b4618c4f04e1983ca0dcaa8f493a5b2d3ba0d0bb37df5a324e5feadf5a18a6`. The "
    "evidence-recording transition was not performed. Owner-local project "
    "questions about the disposable `TOOL_TEST` project remain open and are "
    "recorded privately; closure does not resolve them and authorizes no "
    "recovery. **Acceptance criteria, with their accurate status.** No "
    "criterion is redefined. | Criterion | Status | |---|---| | Each pair "
    "ends in exactly one outcome, with its evidence | NOT MET as an accepted "
    "WO-006 result; mechanically satisfied in rejected live-1 (both pairs "
    "MEASURED, independently recomputed) | | Every call recorded; every "
    "scheduled slot has a disposition; nothing retried, replaced, or padded "
    "| MET within rejected live-1 | | Every mutation restored and verified | "
    "MET (72 of 72, and both final re-reads) | | The report: every raw call, "
    "the per-cell counts, and the latency summary, with no general "
    "conclusion | NOT MET; a private report exists for a rejected run, and it "
    "is not accepted, recorded, or published | | No bridge, client, "
    "transport, test, or Epic-policy code changes | MET; governance-state "
    "transitions update the checker and tests, as `" + _WO006_CLOSURE_COMMIT
    + "` did | Separately NOT MET: the foreground-and-focused condition (not "
    "shown to hold), the background-CPU record, \"Nothing is saved at any "
    "point\", the level being otherwise unchanged, and closing with the save "
    "prompt declined. The physics Details check was not met, under the "
    "owner's one-run exception. NOT APPLICABLE is used for none of these. "
    "**What this amends.** \"Acceptance criteria\" gains the statuses above, "
    "and no criterion is redefined. \"Recording and publication\" is closed: "
    "the evidence-recording transition is not performed, and no sanitized "
    "record or evidence is added under `docs/audits/`. \"Stop boundaries\" is "
    "closed for WO-006: Session B execution, the evidence-recording "
    "transition, any commit or push of WO-006 work after this closure "
    "transition, and WO-006 completion are closed permanently. This record "
    "grants no commit or push authority. The NEXT GATE line below is "
    "replaced. Every other section is kept verbatim, and the earlier text "
    "remains in the repository history. **This closure is terminal.** It "
    "permanently closes Session B, including its single live-run authority, "
    "the evidence-recording transition, WO-006 completion, any further live "
    "run, adoption of the private recovery plan's rules, and any project "
    "recovery. WO-006 cannot be resumed or completed; any future benchmark "
    "needs a new proposal."
)
_WO006_SUPERSEDED_NEXT_GATE = (
    "NEXT GATE: none for WO-006. It is superseded and cannot be resumed or "
    "completed; any future benchmark needs a new proposal. WO-007 remains "
    "proposed and unauthorized."
)
# The pointer turns the Session B record into history beside the earlier
# history, records the closure once, and keeps WO-006's link on its
# superseded path. The history paragraphs and the closure clause outlive any
# later pointer owner, so they are pinned wherever WO-006 is superseded. The
# clause stops before its WO-007 sentence, which a later issuance must
# change; the next-order scan covers that sentence.
_WO006_SESSION_B_POINTER_HISTORY = (
    "At the Session B authorization gate, this pointer opened owner-operated "
    "live measurement only, on the basis of commit `"
    + _WO006_SESSION_B_COMMIT + "`, successful CI workflow `"
    + _WO006_SESSION_B_WORKFLOW + "`, and successful required job `"
    + _WO006_SESSION_B_JOB + "` (`Lint, types, tests`). That CI tested the "
    "repository's checker and tests, not the private harness, and established "
    "no live result. That gate covered the Session B scope recorded in the "
    "issued mandate, unchanged: the owner operated UEFN and performed the "
    "owner checks, and the accepted harness ran only after the owner's "
    "separate, explicit instruction to begin the live run. It changed no "
    "repository file and ended with its private artifacts held for "
    "independent review. It opened no code change, fallback, emulation, "
    "policy change, live repair, commit, or push, and the evidence-recording "
    "transition and WO-006 completion stayed closed at that gate."
)
_WO006_SUPERSEDED_POINTER_ANCHORED = " ".join((
    _WO006_ISSUANCE_POINTER_HISTORY,
    _WO006_SESSION_A_POINTER_HISTORY,
    _WO006_SESSION_A_POINTER_ACCEPTANCE,
    _WO006_SESSION_B_POINTER_HISTORY,
))
_WO006_SUPERSEDED_LINK = (
    "[`WO-006`](docs/work-orders/superseded/"
    "WO-006-official-vs-toolbelt-benchmark.md)"
)
_WO006_SUPERSEDED_POINTER_OPENING = (
    _WO006_SUPERSEDED_LINK + " is superseded. Its planning baseline is `"
    + _WO006_PLANNING_BASELINE + "`; the independently accepted proposal was "
    "committed as `" + _WO006_ISSUANCE_COMMIT + "` after [CI workflow `"
    + _WO006_ISSUANCE_WORKFLOW + "`]"
)
_WO006_SUPERSEDED_POINTER_CLAUSE = (
    _WO006_SUPERSEDED_LINK + " is superseded. It closed without an accepted "
    "measurement under the owner's closure decision recorded in its mandate, "
    "which keeps its unmet requirements. WO-006 cannot be resumed or "
    "completed, and no session is authorized."
)
# Pointer-bound while WO-006 closed last: the owner's release-train
# amendment, which a later pointer owner must restate visibly.
_WO006_RELEASE_TRAIN_AMENDMENT = (
    "Release-train amendment (owner decision): the frozen train remains "
    "WO-001 through WO-007. WO-006 is closed as superseded without an "
    "accepted measurement. It is resolved for this train, not completed, and "
    "its unmet requirements stay recorded in its mandate. For the release "
    "gate above, the frozen train is complete when WO-001 through WO-005 and "
    "WO-007 are completed and WO-006 remains superseded. This amendment opens "
    "no session and grants nothing: WO-007 remains proposed and "
    "unauthorized, and the final integration/repository-truth audit and a "
    "separate owner decision on any release remain required."
)
# The superseded mandate's kept records name sessions beside words the
# reopening scan reads as grants. Each is pinned exactly by
# _wo006_superseded_record_findings and removed once before that scan; the
# closure section, which carries the kept-bases note, is pinned and removed
# the same way.
_WO006_SUPERSEDED_KEPT_RECORDS = (
    _WO006_SESSION_A_BASIS_RECORD,
    _WO006_SESSION_A_ACCEPTANCE_RECORD,
    _WO006_SESSION_B_BASIS_RECORD,
    _WO006_CLOSURE_RECORD,
)


def _wo006_superseded_record_findings(text, rel):
    """The superseded mandate's closed records and its terminal next gate.

    The WO-005 completed pattern: the headings are unique and consecutive in
    the canonical order; Session A's authorization basis, its acceptance
    record, Session B's authorization basis, and the closure section are each
    a closed section equal to its accepted text; and the terminal next gate
    occurs once, with no second next gate beside it.
    """
    out = []
    lines = [line.strip() for line in text.splitlines()]
    headings = [line for line in lines if line.startswith("## ")]
    unique = True
    for heading in _WO006_SUPERSEDED_HEADINGS:
        if headings.count(heading) != 1:
            unique = False
            out.append((rel, "WO-006 superseded record heading",
                        str(headings.count(heading)), "exactly one " + heading))
    if unique:
        first = headings.index(_WO006_SUPERSEDED_HEADINGS[0])
        found = tuple(headings[first:first + len(_WO006_SUPERSEDED_HEADINGS)])
        if found != _WO006_SUPERSEDED_HEADINGS:
            out.append((rel, "WO-006 superseded record heading",
                        " / ".join(found),
                        "consecutive " + " / ".join(_WO006_SUPERSEDED_HEADINGS)))
        for heading, record, kind in (
            (_WO006_SESSION_A_BASIS_HEADING, _WO006_SESSION_A_BASIS_RECORD,
             "WO-006 Session A authorization statement"),
            (_WO006_SESSION_A_ACCEPTANCE_HEADING,
             _WO006_SESSION_A_ACCEPTANCE_RECORD,
             "WO-006 Session A acceptance record"),
            (_WO006_SESSION_B_BASIS_HEADING, _WO006_SESSION_B_BASIS_RECORD,
             "WO-006 Session B authorization statement"),
            (_WO006_CLOSURE_HEADING, _WO006_CLOSURE_RECORD,
             "WO-006 closure record"),
        ):
            if _wo005_closed_section(lines, heading) != record:
                out.append((rel, kind,
                            "a section that differs from the accepted record",
                            "exactly " + record))
    normalized = " ".join(text.split())
    if normalized.count(_WO006_SUPERSEDED_NEXT_GATE) != 1:
        out.append((rel, "WO-006 next gate",
                    str(normalized.count(_WO006_SUPERSEDED_NEXT_GATE)),
                    "exactly one " + _WO006_SUPERSEDED_NEXT_GATE))
    gates = [line for line in lines if line.startswith("NEXT GATE:")]
    if len(gates) != 1:
        out.append((rel, "WO-006 next gate", str(len(gates)),
                    "exactly one NEXT GATE"))
    return out


# WO-007's issuance record, on the same two canonical surfaces as WO-006's:
# the root pointer's bullet block and the mandate's metadata block, each an
# exact, contiguous, terminal slice whose keys are also counted. The evidence
# identifies the accepted proposal commit and its CI, not the later issuance
# transition commit or any Session A output, and the planning baseline stays
# at the commit the proposal was reviewed against. A later transition that
# changes the base must update these pins.
_WO007_PLANNING_BASELINE = "5d88a4ee56309df43537d289514a150615dfeba6"
_WO007_ISSUANCE_COMMIT = "c04e4a794f1e7d0c607c7ad712cbd28e86a55914"
_WO007_ISSUANCE_WORKFLOW = "37050236355"
_WO007_ISSUANCE_JOB = "110981533635"
_WO007_ISSUED_SEQUENCE = (
    "BASELINE: `" + _WO007_PLANNING_BASELINE + "`",
    "ISSUANCE_COMMIT: `" + _WO007_ISSUANCE_COMMIT + "`",
    "ISSUANCE_CI_WORKFLOW: `" + _WO007_ISSUANCE_WORKFLOW + "`",
    "ISSUANCE_CI_JOB: `" + _WO007_ISSUANCE_JOB + "` — Lint, types, tests",
)
_WO007_POINTER_SEQUENCE = (
    "- Current issued Work Order:",
    "- Authorized session:",
    "- Base commit: `" + _WO007_ISSUANCE_COMMIT + "`",
    "- Current gate:",
    "- Issuance commit: `" + _WO007_ISSUANCE_COMMIT + "`",
    "- Issuance CI workflow: `" + _WO007_ISSUANCE_WORKFLOW + "`",
    "- Issuance CI job: `" + _WO007_ISSUANCE_JOB + "` — Lint, types, tests",
    "- Release train:",
    "- Release gate:",
)
_WO007_POINTER_KEYS = (
    ("- Base commit:", _WO007_POINTER_SEQUENCE[2]),
    ("- Issuance commit:", _WO007_POINTER_SEQUENCE[4]),
    ("- Issuance CI workflow:", _WO007_POINTER_SEQUENCE[5]),
    ("- Issuance CI job:", _WO007_POINTER_SEQUENCE[6]),
)
_WO007_ISSUED_KEYS = (
    ("BASELINE:", _WO007_ISSUED_SEQUENCE[0]),
    ("ISSUANCE_COMMIT:", _WO007_ISSUED_SEQUENCE[1]),
    ("ISSUANCE_CI_WORKFLOW:", _WO007_ISSUED_SEQUENCE[2]),
    ("ISSUANCE_CI_JOB:", _WO007_ISSUED_SEQUENCE[3]),
)
# The mandate's issuance basis is one closed section equal to its accepted
# text, and the issued next gate occurs once, with no second next gate.
_WO007_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO007_ISSUANCE_WORKFLOW
)
_WO007_ISSUANCE_HEADING = "## Issuance basis"
_WO007_ISSUANCE_RECORD = (
    _WO007_ISSUANCE_HEADING + " The independently accepted revision of this "
    "mandate was committed as `" + _WO007_ISSUANCE_COMMIT + "`; [CI workflow `"
    + _WO007_ISSUANCE_WORKFLOW + "`](" + _WO007_RUN_URL + ") completed "
    "successfully, including required job [`" + _WO007_ISSUANCE_JOB
    + "` — Lint, types, tests](" + _WO007_RUN_URL + "/job/"
    + _WO007_ISSUANCE_JOB + "). Those identify the accepted proposal, not the "
    "later commit that records this issuance, and they establish nothing "
    "about any Session A output. The planning baseline above and the "
    "revision basis below are preserved unchanged; the train state the "
    "revision basis describes is the state before this issuance. Issuance "
    "alone grants no implementation authority. Session A, the repository "
    "explainer and draft variants, needs its own separate owner gate recorded "
    "in root `WORKORDER.md`, and its proposed live-verification exemption "
    "remains pending the owner's decision."
)
_WO007_ISSUED_NEXT_GATE = (
    "NEXT GATE: separate owner decision on Session A authorization, recorded "
    "in root `WORKORDER.md`, together with the owner's decision on its "
    "proposed live-verification exemption. Issuance authorizes no session, "
    "and this mandate grants no review, commit, push, or session authority."
)
# The pointer records the issuance once, with its accepted proposal evidence
# and a note that opens no session. WO-006's closure evidence, which left the
# bullet block at this issuance, is kept once as history beside it.
_WO007_POINTER_OPENING = (
    "[`WO-007`](docs/work-orders/issued/" + _WO007_NAME + ") is issued. Its "
    "planning baseline is `" + _WO007_PLANNING_BASELINE + "`; the "
    "independently accepted proposal was committed as `"
    + _WO007_ISSUANCE_COMMIT + "` after [CI workflow `"
    + _WO007_ISSUANCE_WORKFLOW + "`](" + _WO007_RUN_URL + ") completed "
    "successfully, including required job [`" + _WO007_ISSUANCE_JOB
    + "` — Lint, types, tests](" + _WO007_RUN_URL + "/job/"
    + _WO007_ISSUANCE_JOB + ")."
)
_WO007_ISSUANCE_POINTER_NOTE = (
    "Issuance grants no implementation authority and opens no session. "
    "Session A, the repository explainer and draft variants, needs its own "
    "separate owner gate recorded in this pointer, and its proposed "
    "live-verification exemption remains pending the owner's decision."
)
_WO006_CLOSURE_POINTER_EVIDENCE = (
    "WO-006 was superseded as `5d88a4ee56309df43537d289514a150615dfeba6`; [CI "
    "workflow `37037329967`](https://github.com/undergroundrap/UEFN-TOOLBELT/"
    "actions/runs/37037329967) completed successfully, including required job "
    "[`110938646551` — Lint, types, tests](https://github.com/undergroundrap/"
    "UEFN-TOOLBELT/actions/runs/37037329967/job/110938646551). Its closure "
    "basis was commit `" + _WO006_CLOSURE_COMMIT + "`, successful CI workflow `"
    + _WO006_CLOSURE_WORKFLOW + "`, and successful required job `"
    + _WO006_CLOSURE_JOB + "` (`Lint, types, tests`)."
)
# While WO-007 is issued with no session, the owner's release-train amendment
# keeps every substantive term; only its WO-007 status clause reads issued,
# with every session still unauthorized. The pre-issuance form must be gone.
_WO007_ISSUED_RELEASE_TRAIN_AMENDMENT = (
    "Release-train amendment (owner decision): the frozen train remains "
    "WO-001 through WO-007. WO-006 is closed as superseded without an "
    "accepted measurement. It is resolved for this train, not completed, and "
    "its unmet requirements stay recorded in its mandate. For the release "
    "gate above, the frozen train is complete when WO-001 through WO-005 and "
    "WO-007 are completed and WO-006 remains superseded. This amendment opens "
    "no session and grants nothing: WO-007 is issued with every session still "
    "unauthorized, and the final integration/repository-truth audit and a "
    "separate owner decision on any release remain required."
)

# Authorizing Session A adds three declarations to each canonical block and
# moves the base to the Session A authorization commit, as WO-005's and
# WO-006's did. That commit recorded WO-007's issuance, and its CI tested the
# repository's checker and tests there: it is issuance evidence, never evidence
# for a Session A output.
_WO007_SESSION_A_COMMIT = "c49905067e6c0d7038c467b3ae6f1116640a904a"
_WO007_SESSION_A_WORKFLOW = "37091060115"
_WO007_SESSION_A_JOB = "111111315920"
_WO007_SESSION_A_GATE = (
    "WO-007 SESSION A AUTHORIZED — EXPLAINER AND PRIVATE DRAFTS ONLY"
)
_WO007_SESSION_A_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR EXPLAINER AND PRIVATE "
    "DRAFTS ONLY"
)
_WO007_SESSION_A_ISSUED_SEQUENCE = _WO007_ISSUED_SEQUENCE + (
    "SESSION_A_AUTHORIZATION_COMMIT: `" + _WO007_SESSION_A_COMMIT + "`",
    "SESSION_A_AUTHORIZATION_CI_WORKFLOW: `"
    + _WO007_SESSION_A_WORKFLOW + "`",
    "SESSION_A_AUTHORIZATION_CI_JOB: `" + _WO007_SESSION_A_JOB + "` "
    + "— Lint, types, tests",
)
_WO007_SESSION_A_POINTER_SEQUENCE = (
    _WO007_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _WO007_SESSION_A_COMMIT + "`",)
    + _WO007_POINTER_SEQUENCE[3:7]
    + ("- Session A authorization commit: `"
       + _WO007_SESSION_A_COMMIT + "`",
       "- Session A authorization CI workflow: `"
       + _WO007_SESSION_A_WORKFLOW + "`",
       "- Session A authorization CI job: `" + _WO007_SESSION_A_JOB + "` "
       + "— Lint, types, tests")
    + _WO007_POINTER_SEQUENCE[7:]
)
_WO007_SESSION_A_POINTER_KEYS = (
    (("- Base commit:", _WO007_SESSION_A_POINTER_SEQUENCE[2]),)
    + _WO007_POINTER_KEYS[1:]
    + (("- Session A authorization commit:",
        _WO007_SESSION_A_POINTER_SEQUENCE[7]),
       ("- Session A authorization CI workflow:",
        _WO007_SESSION_A_POINTER_SEQUENCE[8]),
       ("- Session A authorization CI job:",
        _WO007_SESSION_A_POINTER_SEQUENCE[9]))
)
_WO007_SESSION_A_ISSUED_KEYS = _WO007_ISSUED_KEYS + (
    ("SESSION_A_AUTHORIZATION_COMMIT:", _WO007_SESSION_A_ISSUED_SEQUENCE[4]),
    ("SESSION_A_AUTHORIZATION_CI_WORKFLOW:",
     _WO007_SESSION_A_ISSUED_SEQUENCE[5]),
    ("SESSION_A_AUTHORIZATION_CI_JOB:", _WO007_SESSION_A_ISSUED_SEQUENCE[6]),
)
# Once Session A opens, the issuance basis keeps its evidence and reads its
# closing note as history: the exemption it called pending is decided.
_WO007_ISSUANCE_HISTORY_RECORD = (
    _WO007_ISSUANCE_RECORD.split(" Issuance alone grants")[0]
    + " Issuance alone granted no implementation authority. At that gate, "
    "Session A, the repository explainer and draft variants, needed its own "
    "separate owner gate recorded in root `WORKORDER.md`, and its proposed "
    "live-verification exemption remained pending the owner's decision."
)
# The Session A record in the mandate, WO-005's pattern: the authorization
# basis and the accepted exemption are closed records, each equal to its
# accepted text, under four unique, consecutive headings. The exemption
# record pins the owner's decision and its exact offline scope, and the
# proposal paragraph it answers stays verbatim, exactly once.
_WO007_SESSION_A_BASIS_HEADING = "## Session A authorization basis"
_WO007_EXEMPTION_HEADING = "## Session A live-verification exemption"
_WO007_SESSION_A_HEADINGS = (
    _WO007_ISSUANCE_HEADING,
    _WO007_SESSION_A_BASIS_HEADING,
    _WO007_EXEMPTION_HEADING,
    "## Revision basis",
)
_WO007_SESSION_A_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO007_SESSION_A_WORKFLOW
)
_WO007_SESSION_A_SCOPE_TITLE = (
    "\"Proposed Session A — repository explainer and draft variants\" below"
)
_WO007_SESSION_A_BASIS_RECORD = (
    _WO007_SESSION_A_BASIS_HEADING + " Session A is authorized for the "
    "repository explainer and the two private drafts only under the current "
    "root `WORKORDER.md` gate alone. The recorded basis is commit `"
    + _WO007_SESSION_A_COMMIT + "`; [CI workflow `"
    + _WO007_SESSION_A_WORKFLOW + "`](" + _WO007_SESSION_A_RUN_URL
    + ") completed successfully, including required job [`"
    + _WO007_SESSION_A_JOB + "` — Lint, types, tests]("
    + _WO007_SESSION_A_RUN_URL + "/job/" + _WO007_SESSION_A_JOB + "). That "
    "commit recorded this mandate's issuance, and its CI tested the "
    "repository's checker and tests at that commit. Both are issuance "
    "evidence: they establish nothing about any Session A output, which does "
    "not exist yet and needs its own independent review and CI evidence. This "
    "gate covers exactly the scope in " + _WO007_SESSION_A_SCOPE_TITLE
    + ", unchanged: the explainer at `docs/OFFICIAL_MCP_AND_TOOLBELT.md`, one "
    "`SCAN_FILES` entry for it in `scripts/drift_check.py`, the matching "
    "scan-target entry in `tests/test_repo_integrity.py`, and the two private "
    "drafts outside the repository, under the evidence sources, the benchmark "
    "disclosure, the acceptance criteria, the exclusions, the cleanup duties, "
    "and the proportional checks recorded there. Session A ends with its three "
    "repository paths uncommitted and its two drafts held privately, for "
    "independent review. It opens no publication, deploy, editor launch, "
    "bridge startup, MCP call, benchmark, commit, or push. The planning "
    "baseline and the issuance evidence above are preserved unchanged, and "
    "neither is the Session A basis."
)
_WO007_EXEMPTION_RECORD = (
    _WO007_EXEMPTION_HEADING + " The owner accepted the live-verification "
    "exemption proposed for Session A under " + _WO007_SESSION_A_SCOPE_TITLE
    + ", for exactly that scope and on these terms only: - It covers only the "
    "repository explainer, one `SCAN_FILES` entry for it in "
    "`scripts/drift_check.py`, the matching scan-target entry in "
    "`tests/test_repo_integrity.py`, and the two private drafts outside the "
    "repository. - Verification is offline only. - It accepts no "
    "publication, runtime change, or live activity. - Any runtime, editor, or "
    "live need found during Session A stops it for a new owner decision; it "
    "does not silently widen this exemption. - It grants no commit or push."
)
_WO007_EXEMPTION_PROPOSAL = (
    "Proposed live-verification exemption, offered for the owner's decision "
    "and not accepted by this proposal: Session A's whole scope is the "
    "explainer, one `SCAN_FILES` entry in `scripts/drift_check.py`, the "
    "matching scan-target entry in `tests/test_repo_integrity.py`, and the "
    "two private drafts outside the repository. It runs nothing in UEFN and "
    "touches no runtime path, so its verification would be offline only. The "
    "owner may accept it, narrow it, or require a live check at the Session A "
    "gate."
)
_WO007_SESSION_A_NEXT_GATE = (
    "NEXT GATE: execution of the accepted Session A scope, limited to the "
    "repository explainer, its one scan-target entry and matching test entry, "
    "and the two private drafts, ending with the three repository paths "
    "uncommitted and the drafts held privately for independent review. "
    "Publication, deploy, live activity, commit, push, WO-007 completion, "
    "version selection, and the final integration/repository-truth audit "
    "remain closed."
)
# The pointer's own Session A record: the issuance note as history, then the
# record with its basis evidence and the accepted exemption. The record occurs
# once, and once more anchored to the note before it, which occurs once too.
_WO007_ISSUANCE_POINTER_HISTORY = (
    "At its issuance gate, WO-007 gave no implementation authority and opened "
    "no session. Session A, the repository explainer and draft variants, "
    "needed its own separate owner gate recorded in this pointer, and its "
    "proposed live-verification exemption remained pending the owner's "
    "decision at that gate."
)
_WO007_SESSION_A_POINTER_RECORD = (
    "Session A is authorized under this pointer for the repository explainer "
    "and the two private drafts only, on the basis of commit `"
    + _WO007_SESSION_A_COMMIT + "`, successful CI workflow `"
    + _WO007_SESSION_A_WORKFLOW + "`, and successful required job `"
    + _WO007_SESSION_A_JOB + "` (`Lint, types, tests`). That evidence is CI "
    "on the issuance commit; it establishes the issued mandate, not any "
    "Session A output. It covers the Session A scope recorded in the issued "
    "mandate, unchanged, and ends with its three repository paths uncommitted "
    "and its two private drafts held for independent review. The owner "
    "accepted the proposed live-verification exemption for exactly that "
    "scope, with offline verification only, on the terms recorded in the "
    "mandate; it accepts no publication, runtime change, or live activity. "
    "Session A opens no publication, deploy, UEFN launch, bridge startup, MCP "
    "call, benchmark, commit, or push."
)
_WO007_SESSION_A_POINTER_ANCHORED = (
    _WO007_ISSUANCE_POINTER_HISTORY + " " + _WO007_SESSION_A_POINTER_RECORD
)
# While Session A is open, the release-train amendment keeps every
# substantive term; only its WO-007 clause names the one open session. The
# issued and pre-issuance forms must both be gone.
_WO007_SESSION_A_RELEASE_TRAIN_AMENDMENT = (
    _WO007_ISSUED_RELEASE_TRAIN_AMENDMENT.replace(
        "WO-007 is issued with every session still unauthorized,",
        "WO-007 is issued with only Session A authorized, for the repository "
        "explainer and the two private drafts,")
)
# The only statements allowed to grant WO-007's Session A anything: the
# gate and marker, checked exactly by the Session A branch, and the records
# the WO-007 checks pin exactly.
_WO007_SESSION_A_CANONICAL = (
    _WO007_SESSION_A_GATE,
    _WO007_SESSION_A_AUTH,
    _WO007_SESSION_A_BASIS_RECORD,
    _WO007_EXEMPTION_RECORD,
    _WO007_EXEMPTION_PROPOSAL,
    _WO007_SESSION_A_POINTER_RECORD,
    _WO007_ISSUANCE_POINTER_HISTORY,
    _WO007_SESSION_A_NEXT_GATE,
    _WO007_SESSION_A_RELEASE_TRAIN_AMENDMENT,
)



def _replaced_once(text: str, pairs: tuple[tuple[str, str], ...]) -> str:
    """Apply each replacement exactly once; a missed anchor fails at import,
    so a derived record can never silently equal its source."""
    for old, new in pairs:
        if text.count(old) != 1:
            raise ValueError("derived record anchor drifted: " + old)
        text = text.replace(old, new)
    return text


# Completing WO-007 adds the completion basis - the Session A implementation
# commit and its CI - to each canonical block and moves the base to that
# commit, as WO-005's completion did. The completion transition's own commit
# is not recorded: it does not exist when the transition is written. WO-007
# is the last order of the frozen train, so no successor follows it; the next
# gate is the separately authorized final integration/repository-truth audit.
_WO007_COMPLETION_COMMIT = "e34e9fcdfb27ef7e443ae4e47799512d5c28489b"
_WO007_COMPLETION_WORKFLOW = "37137035181"
_WO007_COMPLETION_JOB = "111243552871"
_WO007_COMPLETED_GATE = (
    "WO-007 COMPLETED — FINAL INTEGRATION/REPOSITORY-TRUTH AUDIT NOT "
    "AUTHORIZED"
)
_WO007_COMPLETED_ISSUED_SEQUENCE = _WO007_SESSION_A_ISSUED_SEQUENCE + (
    "COMPLETION_BASIS_COMMIT: `" + _WO007_COMPLETION_COMMIT + "`",
    "COMPLETION_BASIS_CI_WORKFLOW: `" + _WO007_COMPLETION_WORKFLOW + "`",
    "COMPLETION_BASIS_CI_JOB: `" + _WO007_COMPLETION_JOB + "` "
    + "— Lint, types, tests",
)
_WO007_COMPLETED_POINTER_SEQUENCE = (
    _WO007_SESSION_A_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _WO007_COMPLETION_COMMIT + "`",)
    + _WO007_SESSION_A_POINTER_SEQUENCE[3:10]
    + ("- Completion basis commit: `" + _WO007_COMPLETION_COMMIT + "`",
       "- Completion basis CI workflow: `" + _WO007_COMPLETION_WORKFLOW + "`",
       "- Completion basis CI job: `" + _WO007_COMPLETION_JOB + "` "
       + "— Lint, types, tests")
    + _WO007_SESSION_A_POINTER_SEQUENCE[10:]
)
_WO007_COMPLETED_POINTER_KEYS = (
    (("- Base commit:", _WO007_COMPLETED_POINTER_SEQUENCE[2]),)
    + _WO007_SESSION_A_POINTER_KEYS[1:]
    + (("- Completion basis commit:", _WO007_COMPLETED_POINTER_SEQUENCE[10]),
       ("- Completion basis CI workflow:",
        _WO007_COMPLETED_POINTER_SEQUENCE[11]),
       ("- Completion basis CI job:", _WO007_COMPLETED_POINTER_SEQUENCE[12]))
)
_WO007_COMPLETED_ISSUED_KEYS = _WO007_SESSION_A_ISSUED_KEYS + (
    ("COMPLETION_BASIS_COMMIT:", _WO007_COMPLETED_ISSUED_SEQUENCE[7]),
    ("COMPLETION_BASIS_CI_WORKFLOW:", _WO007_COMPLETED_ISSUED_SEQUENCE[8]),
    ("COMPLETION_BASIS_CI_JOB:", _WO007_COMPLETED_ISSUED_SEQUENCE[9]),
)
# Once WO-007 is completed, its mandate records Session A's authorization as
# history, keeps the accepted exemption terms unchanged, and adds a closed
# completion record. The completion record names the private drafts only by
# their accepted counts and SHA-256 identities; their text stays private.
_WO007_COMPLETION_HEADING = "## Completion record"
_WO007_COMPLETED_HEADINGS = (
    _WO007_SESSION_A_HEADINGS[:3] + (_WO007_COMPLETION_HEADING,)
    + _WO007_SESSION_A_HEADINGS[3:]
)
_WO007_COMPLETED_BASIS_RECORD = _replaced_once(_WO007_SESSION_A_BASIS_RECORD, (
    ("Session A is authorized for the repository explainer and the two "
     "private drafts only under the current root `WORKORDER.md` gate alone.",
     "At the Session A authorization gate, Session A was authorized for the "
     "repository explainer and the two private drafts only under the root "
     "`WORKORDER.md` gate."),
    ("which does not exist yet and needs its own",
     "which did not exist at that gate and needed its own"),
    ("This gate covers exactly", "That gate covered exactly"),
    ("Session A ends with", "Session A ended with"),
    ("It opens no publication", "It opened no publication"),
))
_WO007_COMPLETION_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO007_COMPLETION_WORKFLOW
)
_WO007_RELEASE_DRAFT_SHA256 = (
    "f136d95f817bec11d6b0eb2e1638d0e1343d7ba9ccf23ef53053d992eaf16580"
)
_WO007_X_DRAFT_SHA256 = (
    "354414fd3f037aede92ee7b3702ce81854866b7a43b1cddb830d148e3910e2a0"
)
_WO007_COMPLETION_RECORD = (
    _WO007_COMPLETION_HEADING + " WO-007 is completed as `"
    + _WO007_COMPLETION_COMMIT + "`; [CI workflow `"
    + _WO007_COMPLETION_WORKFLOW + "`](" + _WO007_COMPLETION_RUN_URL
    + ") completed successfully, including required job [`"
    + _WO007_COMPLETION_JOB + "` — Lint, types, tests]("
    + _WO007_COMPLETION_RUN_URL + "/job/" + _WO007_COMPLETION_JOB + "). That "
    "commit carries the independently accepted Session A repository output, "
    "the three-path scope in " + _WO007_SESSION_A_SCOPE_TITLE + ": the "
    "explainer at `docs/OFFICIAL_MCP_AND_TOOLBELT.md`, its one `SCAN_FILES` "
    "entry, and the matching required scan-target entry. The owner accepted "
    "the independently reviewed Session A outputs as completed "
    "explainer-and-draft preparation. The two drafts stay private, outside "
    "the repository; only their accepted public-copy counts and SHA-256 "
    "identities are recorded here: - Release-note draft: 299 words by "
    "`len(text.split())`; SHA-256 `" + _WO007_RELEASE_DRAFT_SHA256 + "`. - X "
    "draft: 273 characters under the counting rule in \"Acceptance "
    "criteria\" below; SHA-256 `" + _WO007_X_DRAFT_SHA256 + "`. This "
    "acceptance does not approve publishing either private draft or "
    "authorize a release. Completion accepts no benchmark result, performance "
    "comparison, version choice, or publication. WO-007 is complete; no "
    "session is authorized. The final integration/repository-truth audit is "
    "not authorized."
)
_WO007_COMPLETED_NEXT_GATE = (
    "NEXT GATE: separate owner authorization for the final "
    "integration/repository-truth audit of the frozen WO-001 through WO-007 "
    "train, after this completion transition is accepted, committed, pushed, "
    "and green. Completion of WO-007 authorizes no audit, version selection, "
    "tag, GitHub Release, repository-metadata change, or publication."
)
# The pointer records the completion on the completed path, keeps the
# issuance note and the Session A record as history, each exactly once and
# anchored together, and states the completion once. The present-tense
# records and every earlier form of the amendment must be gone.
_WO007_COMPLETED_POINTER_OPENING = _replaced_once(_WO007_POINTER_OPENING, (
    ("docs/work-orders/issued/", "docs/work-orders/completed/"),
    (") is issued. Its", ") is completed. Its"),
))
_WO007_SESSION_A_POINTER_HISTORY = (
    "At the Session A authorization gate, this pointer opened the repository "
    "explainer and the two private drafts only, on the basis of commit `"
    + _WO007_SESSION_A_COMMIT + "`, successful CI workflow `"
    + _WO007_SESSION_A_WORKFLOW + "`, and successful required job `"
    + _WO007_SESSION_A_JOB + "` (`Lint, types, tests`). That evidence was CI "
    "on the issuance commit; it established the issued mandate, not any "
    "Session A output. That gate covered the Session A scope recorded in the "
    "mandate, unchanged, and ended with its three repository paths "
    "uncommitted and its two private drafts held for independent review. The "
    "owner accepted the proposed live-verification exemption for exactly that "
    "scope, with offline verification only, on the terms recorded in the "
    "mandate; it accepted no publication, runtime change, or live activity. "
    "That gate opened no publication, deploy, UEFN launch, bridge startup, "
    "MCP call, benchmark, commit, or push."
)
_WO007_SESSION_A_POINTER_HISTORY_ANCHORED = (
    _WO007_ISSUANCE_POINTER_HISTORY + " " + _WO007_SESSION_A_POINTER_HISTORY
)
_WO007_COMPLETED_POINTER_RECORD = (
    "WO-007 is completed as `" + _WO007_COMPLETION_COMMIT + "`; [CI workflow `"
    + _WO007_COMPLETION_WORKFLOW + "`](" + _WO007_COMPLETION_RUN_URL
    + ") completed successfully, including required job [`"
    + _WO007_COMPLETION_JOB + "` — Lint, types, tests]("
    + _WO007_COMPLETION_RUN_URL + "/job/" + _WO007_COMPLETION_JOB + "). That "
    "commit carries the independently accepted Session A repository output: "
    "the explainer `docs/OFFICIAL_MCP_AND_TOOLBELT.md`, its drift scan-target "
    "entry, and the matching test entry. The two accepted drafts stay "
    "private; their counts and SHA-256 identities are recorded in the "
    "completed mandate. Completion accepts no benchmark result, performance "
    "comparison, version choice, or publication, and approves publishing "
    "neither draft. WO-007 is complete; no session is authorized. With WO-007 "
    "completed and WO-006 superseded, the frozen train meets the completion "
    "condition of the release-train amendment below. The final "
    "integration/repository-truth audit, version selection, tagging, Release "
    "creation, branch-protection changes, other repository metadata changes, "
    "and social publication all remain unauthorized."
)
# Once WO-007 is completed, the amendment keeps every substantive term; only
# its WO-007 clause reads completed with no session. Every earlier form of
# the amendment must be gone.
_WO007_COMPLETED_RELEASE_TRAIN_AMENDMENT = _replaced_once(
    _WO007_ISSUED_RELEASE_TRAIN_AMENDMENT, ((
        "WO-007 is issued with every session still unauthorized,",
        "WO-007 is completed with no session authorized,"),))
_WO007_EARLIER_RELEASE_TRAIN_AMENDMENTS = (
    _WO006_RELEASE_TRAIN_AMENDMENT,
    _WO007_ISSUED_RELEASE_TRAIN_AMENDMENT,
    _WO007_SESSION_A_RELEASE_TRAIN_AMENDMENT,
)
# The completed mandate's kept records name Session A beside words the
# session scanner reads as grants, so their pinned forms are removed once
# each before it looks for a positive statement about ANY session.
_WO007_COMPLETED_KEPT_RECORDS = (
    _WO007_COMPLETED_BASIS_RECORD,
    _WO007_EXEMPTION_RECORD,
    _WO007_EXEMPTION_PROPOSAL,
    _WO007_COMPLETION_RECORD,
)

# Recording the final integration/repository-truth audit is a pointer-only
# transition: the pointer keeps WO-007's completion record, moves its base to
# the audited commit, adds the audited commit and its CI to the canonical
# block, recasts the completion statement's closing denials as history, and
# records the verdict, the outstanding required fixes, and the open owner
# decisions once. The private report and logs are named by digest only. Once
# recorded, the record is one-way: a pointer that drops it is a finding.
_FINAL_AUDIT_COMMIT = "066cf6d751740c0daaff165fc076be19e1b8e22d"
_FINAL_AUDIT_WORKFLOW = "37142847095"
_FINAL_AUDIT_JOB = "111260679508"
_FINAL_AUDIT_REPORT_SHA256 = (
    "aed10f85280517a6916398cff384562e2af6fb75d5a0896be7985b01204288f3"
)
_FINAL_AUDIT_LOGS_SHA256 = (
    "88dc0e5bb7c3d246f3fdb03ef05c0ba549805f3012d926feef356f63e3c933b9"
)
_FINAL_AUDIT_GATE = (
    "FINAL AUDIT RECORDED — REQUIRED FIXES OUTSTANDING; RELEASE PREPARATION "
    "NOT AUTHORIZED"
)
_FINAL_AUDIT_POINTER_SEQUENCE = (
    _WO007_COMPLETED_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _FINAL_AUDIT_COMMIT + "`",)
    + _WO007_COMPLETED_POINTER_SEQUENCE[3:13]
    + ("- Final audit commit: `" + _FINAL_AUDIT_COMMIT + "`",
       "- Final audit CI workflow: `" + _FINAL_AUDIT_WORKFLOW + "`",
       "- Final audit CI job: `" + _FINAL_AUDIT_JOB + "` "
       + "— Lint, types, tests")
    + _WO007_COMPLETED_POINTER_SEQUENCE[13:]
)
_FINAL_AUDIT_POINTER_KEYS = (
    (("- Base commit:", _FINAL_AUDIT_POINTER_SEQUENCE[2]),)
    + _WO007_COMPLETED_POINTER_KEYS[1:]
    + (("- Final audit commit:", _FINAL_AUDIT_POINTER_SEQUENCE[13]),
       ("- Final audit CI workflow:", _FINAL_AUDIT_POINTER_SEQUENCE[14]),
       ("- Final audit CI job:", _FINAL_AUDIT_POINTER_SEQUENCE[15]))
)
_FINAL_AUDIT_MARKERS = (
    "- Final audit commit:",
    "- Final audit CI workflow:",
    "- Final audit CI job:",
    "Final integration/repository-truth audit record:",
)
_FINAL_AUDIT_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _FINAL_AUDIT_WORKFLOW
)
_WO007_COMPLETED_POINTER_HISTORY_RECORD = _replaced_once(
    _WO007_COMPLETED_POINTER_RECORD, ((
        "and social publication all remain unauthorized.",
        "and social publication all remained unauthorized at that gate."),))
_FINAL_AUDIT_RECORD = (
    "Final integration/repository-truth audit record: under a separate owner "
    "authorization for a read-only audit only, which opened no implementation "
    "session and no release authority, an independent auditor audited commit "
    "`" + _FINAL_AUDIT_COMMIT + "`; [CI workflow `" + _FINAL_AUDIT_WORKFLOW
    + "`](" + _FINAL_AUDIT_RUN_URL + ") completed successfully on that "
    "commit, including required job [`" + _FINAL_AUDIT_JOB + "` — Lint, "
    "types, tests](" + _FINAL_AUDIT_RUN_URL + "/job/" + _FINAL_AUDIT_JOB
    + "). The audit changed no repository file and ran no UEFN, deploy, "
    "endpoint contact, or benchmark. Its verdict is ACCEPT WITH REQUIRED FIX. "
    "The private audit report is identified by its SHA-256 `"
    + _FINAL_AUDIT_REPORT_SHA256 + "` and its private logs by their manifest "
    "digest `" + _FINAL_AUDIT_LOGS_SHA256 + "`. Two required fixes are "
    "outstanding. P1-1: public and agent pages claim MCP-host compatibility "
    "that no accepted record supports. P1-2: public and agent pages present "
    "the smoke test's registration checks as tool execution or schema "
    "validation. The final audit has not passed the release gate. The "
    "`.mcp.json` fresh-clone documentation defect remains queued for "
    "correction with them. The version choice, the checker's handling of "
    "historical version lines, the pinned-port configuration, the agent "
    "settings, the privacy finding, and the disclosure of the security fix "
    "remain open owner decisions; this record neither accepts nor waives any "
    "of them. Release preparation, any version bump, tagging, Release "
    "creation, branch-protection changes, other repository metadata changes, "
    "and social publication all remain unauthorized."
)

# Preparing the release is a pointer transition under its own owner
# authorization: the pointer keeps the final audit record, recast as history
# with its verdict and its unpassed release gate unchanged, moves its base to
# the audit-recording commit, adds that commit and its CI to the canonical
# block, records the selected version in the release-train paragraph, and
# records the adopted owner decisions once. The private authorization is named
# by digest only. Once recorded, the record is one-way: a pointer that drops it
# is a finding.
_RELEASE_PREP_COMMIT = "fb7f9540464ac0898662087d4f70caa534de60d6"
_RELEASE_PREP_WORKFLOW = "37149178090"
_RELEASE_PREP_JOB = "111279224830"
_RELEASE_PREP_VERSION = "2.5.0"
_RELEASE_PREP_AUTHORIZATION_SHA256 = (
    "aa6f386781c9db3d11ae54012aaef2184ca985edc876cf25ae4d95b880f2f40a"
)
_RELEASE_PREP_GATE = (
    "RELEASE " + _RELEASE_PREP_VERSION + " PREPARED — FINAL AUDIT RECHECK "
    "REQUIRED; TAGGING AND RELEASE CREATION UNAUTHORIZED"
)
_RELEASE_PREP_POINTER_SEQUENCE = (
    _FINAL_AUDIT_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _RELEASE_PREP_COMMIT + "`",)
    + _FINAL_AUDIT_POINTER_SEQUENCE[3:16]
    + ("- Audit recording commit: `" + _RELEASE_PREP_COMMIT + "`",
       "- Audit recording CI workflow: `" + _RELEASE_PREP_WORKFLOW + "`",
       "- Audit recording CI job: `" + _RELEASE_PREP_JOB + "` "
       + "— Lint, types, tests")
    + _FINAL_AUDIT_POINTER_SEQUENCE[16:]
)
_RELEASE_PREP_POINTER_KEYS = (
    (("- Base commit:", _RELEASE_PREP_POINTER_SEQUENCE[2]),)
    + _FINAL_AUDIT_POINTER_KEYS[1:]
    + (("- Audit recording commit:", _RELEASE_PREP_POINTER_SEQUENCE[16]),
       ("- Audit recording CI workflow:", _RELEASE_PREP_POINTER_SEQUENCE[17]),
       ("- Audit recording CI job:", _RELEASE_PREP_POINTER_SEQUENCE[18]))
)
_RELEASE_PREP_MARKERS = (
    "- Audit recording commit:",
    "- Audit recording CI workflow:",
    "- Audit recording CI job:",
    "Release preparation record:",
)
_RELEASE_PREP_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _RELEASE_PREP_WORKFLOW
)
# The release-train paragraph's version sentence, before and after.
_PRE_RELEASE_PREP_VERSION_STATEMENT = (
    "The release version remains undecided and the repository stays at "
    "version 2.4.1."
)
_RELEASE_PREP_VERSION_STATEMENT = (
    "The owner selected release version " + _RELEASE_PREP_VERSION + ", "
    "recorded in the release preparation record below."
)
# The audit record as history: the verdict and the unpassed release gate are
# unchanged; the outstanding fixes, the queued defect, the open decisions, and
# the closing denials describe the recording gate.
_FINAL_AUDIT_HISTORY_RECORD = _replaced_once(_FINAL_AUDIT_RECORD, (
    ("Two required fixes are outstanding. P1-1: public and agent pages claim",
     "At that gate, two required fixes were outstanding. P1-1: public and "
     "agent pages claimed"),
    ("P1-2: public and agent pages present the smoke test's",
     "P1-2: public and agent pages presented the smoke test's"),
    ("defect remains queued for correction with them.",
     "defect remained queued for correction with them."),
    ("security fix remain open owner decisions; this record neither accepts "
     "nor waives any of them.",
     "security fix remained open owner decisions; that record neither "
     "accepted nor waived any of them."),
    ("and social publication all remain unauthorized.",
     "and social publication all remained unauthorized at that gate."),
))
_RELEASE_PREP_RECORD = (
    "Release preparation record: under a separate owner authorization for one "
    "bounded release-preparation session, which opened no review, commit, "
    "push, tag, Release, or publication authority, the repository was "
    "prepared on base commit `" + _RELEASE_PREP_COMMIT + "`; [CI workflow `"
    + _RELEASE_PREP_WORKFLOW + "`](" + _RELEASE_PREP_RUN_URL + ") completed "
    "successfully on that commit, including required job [`"
    + _RELEASE_PREP_JOB + "` — Lint, types, tests](" + _RELEASE_PREP_RUN_URL
    + "/job/" + _RELEASE_PREP_JOB + "). The owner adopted version "
    + _RELEASE_PREP_VERSION + ", with an explicit read-before-upgrading "
    "section and no backward-compatibility claim; MCP-host claims limited to "
    "the evidence, so integration after the hardening is stated as untested; "
    "the smoke test described as registration and module-loading checks that "
    "execute no tool and validate no schema; fresh-clone setup through a "
    "local, gitignored `.mcp.json` copied from `.mcp.json.template`; no "
    "pinned port in that template; `enableAllProjectMcpServers`, "
    "`Bash(python -c *)`, and `Bash(find*)` removed from the shared agent "
    "settings; the profile path in `docs/UEFN_QUIRKS.md` redacted, with "
    "completed mandates and Git history unchanged; disclosure of the released "
    "unauthenticated `execute_python` issue and of the proxy and redirect "
    "bearer leak on unreleased `main`, without exploit detail or a GitHub "
    "advisory; the checker's historical-version exemption limited to exact "
    "lines; and an offline live-verification exemption for this preparation "
    "change, whose only `Content/Python` edit is `__version__` and which "
    "supplies no live verification. The private authorization is identified "
    "by its SHA-256 `" + _RELEASE_PREP_AUTHORIZATION_SHA256 + "`. The final "
    "audit has not passed the release gate; passing it requires an "
    "independent recheck of the required fixes and the affected changes, "
    "which this authorization does not open. Tagging, Release creation, "
    "branch-protection changes, other repository metadata changes, and draft "
    "or social publication all remain unauthorized."
)

# Recording the final audit's recheck is a pointer transition under its own
# owner authorization: the pointer keeps the original audit record, verdict
# included, as history, recasts the preparation record's closing gate as
# history, moves its base to the committed preparation, adds that commit and
# its CI to the canonical block, and records the follow-up acceptance once.
# The private review reports and logs are named by digest only. Once
# recorded, the record is one-way: a pointer that drops it is a finding.
_AUDIT_RECHECK_COMMIT = "82f256da98dc606de9fcca19afd68de2c69a026d"
_AUDIT_RECHECK_WORKFLOW = "37172802902"
_AUDIT_RECHECK_JOB = "111349057775"
_AUDIT_RECHECK_REPORT_SHA256 = (
    "4ecc6fd0284c1bfb9a1461b11355904615f49852219c87b29474f5a288e10b00"
)
_AUDIT_RECHECK_LOGS_SHA256 = (
    "7da7879c48f5b2f7577f10c52f461cf7d6c029055f8a35838e765bd570c22b69"
)
_AUDIT_RERECHECK_REPORT_SHA256 = (
    "9e848b0fe84bc002689548db6cbde834fded5574eb94b7a2370a5227b860a642"
)
_AUDIT_RERECHECK_LOGS_SHA256 = (
    "1ca8d489fee0b1481c1986a21e134cf61742eadd1fb506054179d4e58cca72da"
)
_AUDIT_RECHECK_GATE = (
    "FINAL AUDIT RECHECK RECORDED — TAGGING AND RELEASE CREATION UNAUTHORIZED"
)
_AUDIT_RECHECK_POINTER_SEQUENCE = (
    _RELEASE_PREP_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _AUDIT_RECHECK_COMMIT + "`",)
    + _RELEASE_PREP_POINTER_SEQUENCE[3:19]
    + ("- Release preparation commit: `" + _AUDIT_RECHECK_COMMIT + "`",
       "- Release preparation CI workflow: `" + _AUDIT_RECHECK_WORKFLOW + "`",
       "- Release preparation CI job: `" + _AUDIT_RECHECK_JOB + "` "
       + "— Lint, types, tests")
    + _RELEASE_PREP_POINTER_SEQUENCE[19:]
)
_AUDIT_RECHECK_POINTER_KEYS = (
    (("- Base commit:", _AUDIT_RECHECK_POINTER_SEQUENCE[2]),)
    + _RELEASE_PREP_POINTER_KEYS[1:]
    + (("- Release preparation commit:", _AUDIT_RECHECK_POINTER_SEQUENCE[19]),
       ("- Release preparation CI workflow:",
        _AUDIT_RECHECK_POINTER_SEQUENCE[20]),
       ("- Release preparation CI job:", _AUDIT_RECHECK_POINTER_SEQUENCE[21]))
)
_AUDIT_RECHECK_MARKERS = (
    "- Release preparation commit:",
    "- Release preparation CI workflow:",
    "- Release preparation CI job:",
    "Final audit recheck record:",
)
_AUDIT_RECHECK_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _AUDIT_RECHECK_WORKFLOW
)
# The preparation record as history: its closing gate describes the
# preparation gate, before the recheck ran.
_RELEASE_PREP_HISTORY_RECORD = _replaced_once(_RELEASE_PREP_RECORD, (
    ("The final audit has not passed the release gate; passing it requires "
     "an independent recheck of the required fixes and the affected "
     "changes, which this authorization does not open.",
     "At that gate, the final audit had not passed the release gate; "
     "passing it required an independent recheck of the required fixes and "
     "the affected changes, which that authorization did not open."),
    ("or social publication all remain unauthorized.",
     "or social publication all remained unauthorized at that gate."),
))
_AUDIT_RECHECK_RECORD = (
    "Final audit recheck record: under separate owner authorizations, an "
    "independent reviewer that authored none of the release preparation "
    "reviewed it against the final audit's required fixes and returned ACCEPT "
    "WITH REQUIRED FIX; after a bounded correction, its scoped re-review of "
    "that correction returned ACCEPT, and the owner accepted that review. The "
    "accepted content is committed as `" + _AUDIT_RECHECK_COMMIT + "`; [CI "
    "workflow `" + _AUDIT_RECHECK_WORKFLOW + "`](" + _AUDIT_RECHECK_RUN_URL
    + ") completed successfully on that commit, including required job [`"
    + _AUDIT_RECHECK_JOB + "` — Lint, types, tests](" + _AUDIT_RECHECK_RUN_URL
    + "/job/" + _AUDIT_RECHECK_JOB + "), which logged 2529 passed and 14 "
    "skipped on Linux. Within the accepted scope, P1-1, P1-2, and the queued "
    "`.mcp.json` fresh-clone documentation defect are resolved. The original "
    "audit record above keeps its verdict, ACCEPT WITH REQUIRED FIX, as "
    "history; this record is a separate follow-up acceptance, not a rewritten "
    "pass. The private review reports are identified by their SHA-256 `"
    + _AUDIT_RECHECK_REPORT_SHA256 + "` and `" + _AUDIT_RERECHECK_REPORT_SHA256
    + "`, and their private logs by their manifest digests `"
    + _AUDIT_RECHECK_LOGS_SHA256 + "` and `" + _AUDIT_RERECHECK_LOGS_SHA256
    + "`. The dashboard and menu runtime wording about MCP-compatible "
    "clients, and the limitations the release notes defer, are disclosed; "
    "this record neither fixes nor waives them. This acceptance supplies no "
    "live UEFN, MCP-host, or effective-permissions evidence. Tagging, Release "
    "creation, branch-protection changes, other repository metadata changes, "
    "and draft or social publication all remain unauthorized."
)

# Recording that the frozen train's release conditions are met is a pointer
# transition under its own owner decision: the owner accepted that the
# original audit, with the accepted recheck and green CI, satisfies the train's
# audit condition. The pointer recasts the original audit record's unpassed
# gate and the amendment's closing requirement as history, keeps every verdict,
# identity, and digest, moves its base to the recheck-recording commit, adds
# that commit and its CI to the canonical block, states in the release-gate
# bullet that the conditions are satisfied while tags and Releases stay
# unauthorized, and records the decision once. The private instruction is
# named by digest only. Once recorded, the record is one-way.
_RELEASE_CONDITIONS_COMMIT = "b305a1746c59637854a6877fe6196f17ec84e245"
_RELEASE_CONDITIONS_WORKFLOW = "37180447555"
_RELEASE_CONDITIONS_JOB = "111371778482"
_RELEASE_CONDITIONS_INSTRUCTION_SHA256 = (
    "e7083af5399b4c0e0196e4cf481ab85e90d42c8b93905f15d78b59ea77c8a416"
)
_RELEASE_CONDITIONS_GATE = (
    "FROZEN TRAIN AND AUDIT CONDITIONS SATISFIED — TAGGING AND RELEASE "
    "CREATION UNAUTHORIZED"
)
_SATISFIED_RELEASE_GATE = (
    "NO TAG OR GITHUB RELEASE AUTHORIZED — FROZEN TRAIN AND FINAL "
    "INTEGRATION/REPOSITORY-TRUTH AUDIT CONDITIONS SATISFIED; SEPARATE OWNER "
    "EXECUTION AUTHORIZATIONS REQUIRED"
)
_RELEASE_CONDITIONS_POINTER_SEQUENCE = (
    _AUDIT_RECHECK_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _RELEASE_CONDITIONS_COMMIT + "`",)
    + _AUDIT_RECHECK_POINTER_SEQUENCE[3:22]
    + ("- Audit recheck recording commit: `" + _RELEASE_CONDITIONS_COMMIT
       + "`",
       "- Audit recheck recording CI workflow: `"
       + _RELEASE_CONDITIONS_WORKFLOW + "`",
       "- Audit recheck recording CI job: `" + _RELEASE_CONDITIONS_JOB + "` "
       + "— Lint, types, tests")
    + _AUDIT_RECHECK_POINTER_SEQUENCE[22:]
)
_RELEASE_CONDITIONS_POINTER_KEYS = (
    (("- Base commit:", _RELEASE_CONDITIONS_POINTER_SEQUENCE[2]),)
    + _AUDIT_RECHECK_POINTER_KEYS[1:]
    + (("- Audit recheck recording commit:",
        _RELEASE_CONDITIONS_POINTER_SEQUENCE[22]),
       ("- Audit recheck recording CI workflow:",
        _RELEASE_CONDITIONS_POINTER_SEQUENCE[23]),
       ("- Audit recheck recording CI job:",
        _RELEASE_CONDITIONS_POINTER_SEQUENCE[24]))
)
_RELEASE_CONDITIONS_MARKERS = (
    "- Audit recheck recording commit:",
    "- Audit recheck recording CI workflow:",
    "- Audit recheck recording CI job:",
    "Release conditions record:",
)
_RELEASE_CONDITIONS_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _RELEASE_CONDITIONS_WORKFLOW
)
# The original audit record with its unpassed release gate recast as history
# at that gate; its verdict, identities, and digests are unchanged.
_FINAL_AUDIT_SETTLED_HISTORY_RECORD = _replaced_once(
    _FINAL_AUDIT_HISTORY_RECORD, ((
        "The final audit has not passed the release gate.",
        "At that gate, the final audit had not passed the release gate."),))
# The amendment with its closing requirement recast as history; every
# substantive term is unchanged.
_RELEASE_CONDITIONS_RELEASE_TRAIN_AMENDMENT = _replaced_once(
    _WO007_COMPLETED_RELEASE_TRAIN_AMENDMENT, ((
        "a separate owner decision on any release remain required.",
        "a separate owner decision on any release remained required at that "
        "gate."),))
_RELEASE_CONDITIONS_RECORD = (
    "Release conditions record: the owner accepted that the original final "
    "integration/repository-truth audit, together with the accepted "
    "corrective recheck and green CI, satisfies the frozen train's audit "
    "condition; this does not rewrite the original verdict, ACCEPT WITH "
    "REQUIRED FIX, which the audit record above keeps as history with its "
    "evidence identities and digests. The recheck recording is committed as `"
    + _RELEASE_CONDITIONS_COMMIT + "`; [CI workflow `"
    + _RELEASE_CONDITIONS_WORKFLOW + "`](" + _RELEASE_CONDITIONS_RUN_URL
    + ") completed successfully on that commit, including required job [`"
    + _RELEASE_CONDITIONS_JOB + "` — Lint, types, tests]("
    + _RELEASE_CONDITIONS_RUN_URL + "/job/" + _RELEASE_CONDITIONS_JOB + "). "
    "The frozen train, WO-001 through WO-007, meets its completion condition: "
    "WO-001 through WO-005 and WO-007 are completed, and WO-006 remains "
    "superseded with no accepted benchmark. Its audit condition is satisfied. "
    "Version 2.5.0 and the accepted release-preparation content committed as `"
    + _AUDIT_RECHECK_COMMIT + "` are unchanged. The owner deferred the "
    "nonblocking review advisories to post-release hygiene: the `.MCP.json` "
    "case variant in the tracked-configuration test, the incomplete dashboard "
    "quotation in the known issues, the historical-tag wording in "
    "`SECURITY.md`, and the residual README intent wording (review item "
    "P2-7); they remain open, neither fixed nor waived. The owner's "
    "instruction is identified by its SHA-256 `"
    + _RELEASE_CONDITIONS_INSTRUCTION_SHA256 + "`. Tagging, GitHub Release "
    "creation, branch-protection changes, other repository metadata changes, "
    "and draft or social publication each still require a separate owner "
    "execution authorization, and none is given here."
)

# Recording the published release is a post-release pointer transition under
# its own owner instruction: the tag and the GitHub Release were each created
# under a separate owner authorization after the conditions record. The
# pointer recasts the conditions record's closing requirement as history,
# moves its base to the tagged commit, adds that commit and its CI to the
# canonical block, states in the release-gate bullet that this tag and
# Release are complete while no further tag or Release follows, and records
# the tag and Release identities once. The private instruction is named by
# digest only. The record is not part of the tagged package. Once recorded,
# it is one-way.
_RELEASE_PUBLISHED_COMMIT = "eabce22518d07725e05173aa707909023166a799"
_RELEASE_PUBLISHED_WORKFLOW = "37186239025"
_RELEASE_PUBLISHED_JOB = "111388630828"
_RELEASE_PUBLISHED_TAG_OBJECT = "39afcab4d2f3a8ae3af58fdbd01312c7ec05c93a"
_RELEASE_PUBLISHED_RELEASE_ID = "402913965"
_RELEASE_PUBLISHED_AT = "2026-10-04T08:10:21Z"
_RELEASE_PUBLISHED_BODY_SHA256 = (
    "6c1234865662798fdf13eb3f72449565264545b690c6218bc549a794a6e1eb4a"
)
_RELEASE_PUBLISHED_INSTRUCTION_SHA256 = (
    "aadad5fbeccd0f656dfba476cf035e7cf4aba24324ae93ab47c0ab396168920a"
)
_RELEASE_PUBLISHED_GATE = (
    "V2.5.0 TAGGED AND RELEASED — NEXT WORK ORDER AWAITS A SEPARATE OWNER "
    "DECISION"
)
_PUBLISHED_RELEASE_GATE = (
    "V2.5.0 TAG AND GITHUB RELEASE COMPLETED UNDER SEPARATE OWNER "
    "AUTHORIZATIONS — NO FURTHER TAG OR GITHUB RELEASE AUTHORIZED"
)
_RELEASE_PUBLISHED_POINTER_SEQUENCE = (
    _RELEASE_CONDITIONS_POINTER_SEQUENCE[:2]
    + ("- Base commit: `" + _RELEASE_PUBLISHED_COMMIT + "`",)
    + _RELEASE_CONDITIONS_POINTER_SEQUENCE[3:25]
    + ("- Release conditions recording commit: `"
       + _RELEASE_PUBLISHED_COMMIT + "`",
       "- Release conditions recording CI workflow: `"
       + _RELEASE_PUBLISHED_WORKFLOW + "`",
       "- Release conditions recording CI job: `" + _RELEASE_PUBLISHED_JOB
       + "` " + "— Lint, types, tests")
    + _RELEASE_CONDITIONS_POINTER_SEQUENCE[25:]
)
_RELEASE_PUBLISHED_POINTER_KEYS = (
    (("- Base commit:", _RELEASE_PUBLISHED_POINTER_SEQUENCE[2]),)
    + _RELEASE_CONDITIONS_POINTER_KEYS[1:]
    + (("- Release conditions recording commit:",
        _RELEASE_PUBLISHED_POINTER_SEQUENCE[25]),
       ("- Release conditions recording CI workflow:",
        _RELEASE_PUBLISHED_POINTER_SEQUENCE[26]),
       ("- Release conditions recording CI job:",
        _RELEASE_PUBLISHED_POINTER_SEQUENCE[27]))
)
_RELEASE_PUBLISHED_MARKERS = (
    "- Release conditions recording commit:",
    "- Release conditions recording CI workflow:",
    "- Release conditions recording CI job:",
    "Release publication record:",
)
_RELEASE_PUBLISHED_RUN_URL = (
    "https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _RELEASE_PUBLISHED_WORKFLOW
)
# The conditions record as history: its closing requirement describes the
# conditions gate, before the tag and Release were authorized and created.
_RELEASE_CONDITIONS_HISTORY_RECORD = _replaced_once(
    _RELEASE_CONDITIONS_RECORD, ((
        "each still require a separate owner execution authorization, and "
        "none is given here.",
        "each still required a separate owner execution authorization at "
        "that gate, and that record gave none."),))
_RELEASE_PUBLISHED_RECORD = (
    "Release publication record: under separate owner authorizations given "
    "after the conditions record, the annotated tag `v2.5.0`, tag object `"
    + _RELEASE_PUBLISHED_TAG_OBJECT + "`, was created on commit `"
    + _RELEASE_PUBLISHED_COMMIT + "` and pushed; [CI workflow `"
    + _RELEASE_PUBLISHED_WORKFLOW + "`](" + _RELEASE_PUBLISHED_RUN_URL
    + ") completed successfully on that commit, including required job [`"
    + _RELEASE_PUBLISHED_JOB + "` — Lint, types, tests]("
    + _RELEASE_PUBLISHED_RUN_URL + "/job/" + _RELEASE_PUBLISHED_JOB + "). "
    "GitHub Release `" + _RELEASE_PUBLISHED_RELEASE_ID + "`, titled \"UEFN "
    "Toolbelt v2.5.0\", was then published from that tag at "
    + _RELEASE_PUBLISHED_AT + ", not as a prerelease, and marked Latest. Its "
    "body is the 2.5.0 section of `docs/CHANGELOG.md` at the tag, with only "
    "the `SECURITY.md` link made absolute, and is identified by its SHA-256 `"
    + _RELEASE_PUBLISHED_BODY_SHA256 + "`. Statements in the earlier records "
    "above that tagging or Release creation remain unauthorized describe "
    "their own gates; only those separate owner authorizations changed that, "
    "for v2.5.0 alone. This record is a post-release change and is not part "
    "of the tagged package; `v2.5.0` and every earlier tag stay where they "
    "are. The owner's instruction is identified by its SHA-256 `"
    + _RELEASE_PUBLISHED_INSTRUCTION_SHA256 + "`. No further tagging or "
    "GitHub Release creation follows from this record. Social publication, "
    "private-draft publication, and scratch cleanup remain separately gated, "
    "and the deferred review advisories remain open. The next Work Order "
    "awaits a separate owner decision, and no implementation follows from "
    "this record."
)


def _wo007_issuance_findings(pointer, issued_text, rel, session):
    """WO-007's issuance record while it is issued.

    The WO-006 issuance pattern: the canonical slices on both surfaces, plus
    the mandate's closed issuance-basis section and its single next gate, and
    the pointer's issuance paragraph and WO-006 closure evidence, each exactly
    once. With no session open, the issuance note occurs exactly once and the
    release-train amendment reads in its issued form exactly once, its
    pre-issuance form gone. Once Session A is authorized, the slices carry
    the Session A declarations and base, the issuance basis reads its note as
    history, the next gate is Session A's, the present-tense issuance note is
    gone, and the amendment reads in its Session A form exactly once, both
    earlier forms gone. The gate, the marker, and the session value are
    checked by the branches that call this.
    """
    out = []
    session_a = session == "A"
    shapes: tuple[tuple[tuple[str, ...], tuple[tuple[str, str], ...]], ...]
    if session_a:
        shapes = ((_WO007_SESSION_A_POINTER_SEQUENCE,
                   _WO007_SESSION_A_POINTER_KEYS),
                  (_WO007_SESSION_A_ISSUED_SEQUENCE,
                   _WO007_SESSION_A_ISSUED_KEYS))
        issuance_record = _WO007_ISSUANCE_HISTORY_RECORD
        next_gate = _WO007_SESSION_A_NEXT_GATE
    else:
        shapes = ((_WO007_POINTER_SEQUENCE, _WO007_POINTER_KEYS),
                  (_WO007_ISSUED_SEQUENCE, _WO007_ISSUED_KEYS))
        issuance_record = _WO007_ISSUANCE_RECORD
        next_gate = _WO007_ISSUED_NEXT_GATE
    for target, text, stop, (sequence, keys), where in (
        ("WORKORDER.md", pointer,
         lambda line: _WO001_COMPLETED_LINK in line,
         shapes[0], "WORKORDER.md"),
        (rel, issued_text, lambda line: line.startswith("## "),
         shapes[1], "issued record"),
    ):
        for kind, found, want in _canonical_field_findings(
            text, sequence, stop, where,
            exact={item for item in sequence if "`" in item},
            terminal=True, label="WO-007 issuance field",
        ):
            out.append((target, kind, found, want))
        for kind, found, want in _canonical_key_findings(
            text, stop, keys, "WO-007 issuance declaration (" + where + ")",
        ):
            out.append((target, kind, found, want))
    lines = [line.strip() for line in issued_text.splitlines()]
    headings = [line for line in lines if line.startswith("## ")]
    if headings.count(_WO007_ISSUANCE_HEADING) != 1:
        out.append((rel, "WO-007 issuance record",
                    str(headings.count(_WO007_ISSUANCE_HEADING)),
                    "exactly one " + _WO007_ISSUANCE_HEADING))
    elif (_wo005_closed_section(lines, _WO007_ISSUANCE_HEADING)
          != issuance_record):
        out.append((rel, "WO-007 issuance record",
                    "a section that differs from the accepted record",
                    "exactly " + issuance_record))
    normalized = " ".join(issued_text.split())
    if normalized.count(next_gate) != 1:
        out.append((rel, "WO-007 next gate",
                    str(normalized.count(next_gate)),
                    "exactly one " + next_gate))
    gates = [line for line in lines if line.startswith("NEXT GATE:")]
    if len(gates) != 1:
        out.append((rel, "WO-007 next gate", str(len(gates)),
                    "exactly one NEXT GATE"))
    normalized_pointer = " ".join(pointer.split())
    for required in (_WO007_POINTER_OPENING, _WO006_CLOSURE_POINTER_EVIDENCE):
        if normalized_pointer.count(required) != 1:
            out.append(("WORKORDER.md", "WO-007 issuance pointer statement",
                        str(normalized_pointer.count(required)),
                        "exactly one " + required))
    note_count = normalized_pointer.count(_WO007_ISSUANCE_POINTER_NOTE)
    if session_a and note_count:
        out.append(("WORKORDER.md", "WO-007 issuance pointer statement",
                    "the present-tense issuance note remains",
                    "the issuance note recorded as history"))
    elif not session_a and note_count != 1:
        out.append(("WORKORDER.md", "WO-007 issuance pointer statement",
                    str(note_count),
                    "exactly one " + _WO007_ISSUANCE_POINTER_NOTE))
    stale_forms: tuple[str, ...]
    if session_a:
        current_form = _WO007_SESSION_A_RELEASE_TRAIN_AMENDMENT
        stale_forms = (_WO007_ISSUED_RELEASE_TRAIN_AMENDMENT,
                       _WO006_RELEASE_TRAIN_AMENDMENT)
    elif session == "NONE":
        current_form = _WO007_ISSUED_RELEASE_TRAIN_AMENDMENT
        stale_forms = (_WO006_RELEASE_TRAIN_AMENDMENT,)
    else:
        return out
    if normalized_pointer.count(current_form) != 1:
        out.append(("WORKORDER.md", "WO-007 release-train amendment",
                    str(normalized_pointer.count(current_form)),
                    "exactly one " + current_form))
    if any(normalized_pointer.count(stale) for stale in stale_forms):
        out.append(("WORKORDER.md", "WO-007 release-train amendment",
                    "an earlier form of the amendment remains",
                    "only the current form of the amendment"))
    return out


def _wo007_session_a_record_findings(pointer, issued_text, rel):
    """Session A's record while WO-007 Session A is open.

    WO-005's pattern: the four headings are unique and consecutive in the
    canonical order; the authorization basis and the accepted exemption are
    closed records, each equal to its accepted text; the proposal paragraph
    the exemption answers occurs exactly once, verbatim; and the pointer's
    historical issuance note, Session A record, and the record anchored to
    the note each occur exactly once. The issuance-side checks, including
    the next gate and the amendment, run in _wo007_issuance_findings.
    """
    out = []
    normalized_pointer = " ".join(pointer.split())
    for required in (_WO007_ISSUANCE_POINTER_HISTORY,
                     _WO007_SESSION_A_POINTER_RECORD,
                     _WO007_SESSION_A_POINTER_ANCHORED):
        if normalized_pointer.count(required) != 1:
            out.append(("WORKORDER.md", "WO-007 Session A pointer statement",
                        str(normalized_pointer.count(required)),
                        "exactly one " + required))
    lines = [line.strip() for line in issued_text.splitlines()]
    headings = [line for line in lines if line.startswith("## ")]
    unique = True
    for heading in _WO007_SESSION_A_HEADINGS:
        if headings.count(heading) != 1:
            unique = False
            out.append((rel, "WO-007 Session A record heading",
                        str(headings.count(heading)), "exactly one " + heading))
    if unique:
        first = headings.index(_WO007_SESSION_A_HEADINGS[0])
        found = tuple(headings[first:first + len(_WO007_SESSION_A_HEADINGS)])
        if found != _WO007_SESSION_A_HEADINGS:
            out.append((rel, "WO-007 Session A record heading",
                        " / ".join(found),
                        "consecutive " + " / ".join(_WO007_SESSION_A_HEADINGS)))
    for heading, record, kind in (
        (_WO007_SESSION_A_BASIS_HEADING, _WO007_SESSION_A_BASIS_RECORD,
         "WO-007 Session A authorization statement"),
        (_WO007_EXEMPTION_HEADING, _WO007_EXEMPTION_RECORD,
         "WO-007 Session A exemption record"),
    ):
        if headings.count(heading) == 1:
            if _wo005_closed_section(lines, heading) != record:
                out.append((rel, kind, "a section that differs from the "
                            "accepted record", "exactly " + record))
    normalized = " ".join(issued_text.split())
    if normalized.count(_WO007_EXEMPTION_PROPOSAL) != 1:
        out.append((rel, "WO-007 Session A exemption record",
                    str(normalized.count(_WO007_EXEMPTION_PROPOSAL)),
                    "exactly one " + _WO007_EXEMPTION_PROPOSAL))
    return out


def _wo007_completed_findings(pointer, text, rel, surface,
                              audit_recorded=False, release_prepared=False,
                              audit_rechecked=False,
                              conditions_satisfied=False,
                              release_published=False, following_wo008=False):
    """WO-007's completed record, on one surface at a time.

    The WO-005 completion pattern. On the pointer: the canonical slice with
    the completion basis and the base on the completion commit; the completed
    opening, the issuance note and the Session A record as history (each once
    and anchored together), the completion statement, the WO-006 closure
    evidence, and the amendment's completed form, each exactly once; and no
    present-tense issuance or Session A record, earlier amendment form, or
    stale WO-007 path. On the document: the canonical slice with the
    completion basis; five unique, consecutive headings; the issuance basis,
    the Session A basis as history, the accepted exemption, and the
    completion record, each a closed section equal to its accepted text; the
    exemption proposal and the decision lock, each exactly once; and the
    completed next gate, once, as the only NEXT GATE. The document half runs
    whoever owns the pointer. Once the final audit is recorded, the pointer
    half takes the recorded shape: the audited commit as base, the audit
    bullets after the completion basis, the completion statement's closing
    denials as history, and the audit record, each exactly once. Once the
    release is prepared, it takes the prepared shape: the audit-recording
    commit as base, its bullets after the audit bullets, the audit record as
    history, the selected version, and the preparation record, each exactly
    once, with no pre-preparation statement left. Once the audit recheck is
    recorded, it takes the rechecked shape: the committed preparation as base,
    its bullets after the audit-recording bullets, the preparation record as
    history, and the recheck record, each exactly once. Once the release
    conditions are recorded as satisfied, it takes that shape: the
    recheck-recording commit as base, its bullets after the preparation
    bullets, the original audit's unpassed gate and the amendment's closing
    requirement as history, and the conditions record, each exactly once.
    Once the published release is recorded, it takes that shape: the tagged
    commit as base, its bullets after the recheck-recording bullets, the
    conditions record's closing requirement as history, and the publication
    record, each exactly once.
    """
    out = []
    sequence: tuple[str, ...]
    keys: tuple[tuple[str, str], ...]
    label = "WO-007 completion"
    if surface == "pointer":
        target, src, where = "WORKORDER.md", pointer, "WORKORDER.md"
        sequence = _WO007_COMPLETED_POINTER_SEQUENCE
        keys = _WO007_COMPLETED_POINTER_KEYS
        if audit_recorded:
            sequence = _FINAL_AUDIT_POINTER_SEQUENCE
            keys = _FINAL_AUDIT_POINTER_KEYS
            label = "final audit"
        if release_prepared:
            sequence = _RELEASE_PREP_POINTER_SEQUENCE
            keys = _RELEASE_PREP_POINTER_KEYS
            label = "release preparation"
        if audit_rechecked:
            sequence = _AUDIT_RECHECK_POINTER_SEQUENCE
            keys = _AUDIT_RECHECK_POINTER_KEYS
            label = "audit recheck"
        if conditions_satisfied:
            sequence = _RELEASE_CONDITIONS_POINTER_SEQUENCE
            keys = _RELEASE_CONDITIONS_POINTER_KEYS
            label = "release conditions"
        if release_published:
            sequence = _RELEASE_PUBLISHED_POINTER_SEQUENCE
            keys = _RELEASE_PUBLISHED_POINTER_KEYS
            label = "release publication"
        if following_wo008:
            sequence = _RELEASE_PUBLISHED_POINTER_SEQUENCE[4:]
            keys = tuple(pair for pair in _RELEASE_PUBLISHED_POINTER_KEYS
                         if pair[0] != "- Base commit:")
            label = "frozen publication history"

        def stop(line):
            return _WO001_COMPLETED_LINK in line
    else:
        target, src, where = rel, text, "completed record"
        sequence = _WO007_COMPLETED_ISSUED_SEQUENCE
        keys = _WO007_COMPLETED_ISSUED_KEYS

        def stop(line):
            return line.startswith("## ")
    for kind, found, want in _canonical_field_findings(
        src, sequence, stop, where,
        exact={item for item in sequence if "`" in item},
        terminal=True, label=label + " field",
    ):
        out.append((target, kind, found, want))
    for kind, found, want in _canonical_key_findings(
        src, stop, keys, label + " declaration (" + where + ")",
    ):
        out.append((target, kind, found, want))
    if surface == "pointer":
        normalized_pointer = " ".join(pointer.split())
        completion_record = (_WO007_COMPLETED_POINTER_HISTORY_RECORD
                             if audit_recorded
                             else _WO007_COMPLETED_POINTER_RECORD)
        for required in (_WO007_COMPLETED_POINTER_OPENING,
                         _WO007_ISSUANCE_POINTER_HISTORY,
                         _WO007_SESSION_A_POINTER_HISTORY,
                         _WO007_SESSION_A_POINTER_HISTORY_ANCHORED,
                         completion_record,
                         _WO006_CLOSURE_POINTER_EVIDENCE):
            if normalized_pointer.count(required) != 1:
                out.append(("WORKORDER.md", "WO-007 completion pointer "
                            "statement", str(normalized_pointer.count(required)),
                            "exactly one " + required))
        if audit_recorded:
            # The full record once, and its opening once, so a second,
            # partial record cannot sit beside it.
            audit_record = (
                _FINAL_AUDIT_SETTLED_HISTORY_RECORD if conditions_satisfied
                else _FINAL_AUDIT_HISTORY_RECORD if release_prepared
                else _FINAL_AUDIT_RECORD)
            for required in (audit_record, _FINAL_AUDIT_MARKERS[3]):
                count = normalized_pointer.count(required)
                if count != 1:
                    out.append(("WORKORDER.md",
                                "final audit pointer statement", str(count),
                                "exactly one " + required))
            if _WO007_COMPLETED_POINTER_RECORD in normalized_pointer:
                out.append(("WORKORDER.md", "final audit pointer statement",
                            "the pre-audit completion statement remains",
                            "the completion statement recorded as history"))
        if release_prepared:
            prep_record = (_RELEASE_PREP_HISTORY_RECORD if audit_rechecked
                           else _RELEASE_PREP_RECORD)
            for required in (prep_record, _RELEASE_PREP_MARKERS[3],
                             _RELEASE_PREP_VERSION_STATEMENT):
                count = normalized_pointer.count(required)
                if count != 1:
                    out.append(("WORKORDER.md",
                                "release preparation pointer statement",
                                str(count), "exactly one " + required))
            for stale in (_FINAL_AUDIT_RECORD,
                          _PRE_RELEASE_PREP_VERSION_STATEMENT):
                if stale in normalized_pointer:
                    out.append(("WORKORDER.md",
                                "release preparation pointer statement",
                                "a pre-preparation statement remains: "
                                + stale[:80],
                                "the prepared record only"))
        if audit_rechecked:
            for required in (_AUDIT_RECHECK_RECORD, _AUDIT_RECHECK_MARKERS[3]):
                count = normalized_pointer.count(required)
                if count != 1:
                    out.append(("WORKORDER.md",
                                "audit recheck pointer statement",
                                str(count), "exactly one " + required))
            if _RELEASE_PREP_RECORD in normalized_pointer:
                out.append(("WORKORDER.md", "audit recheck pointer statement",
                            "the pre-recheck preparation record remains",
                            "the preparation record recorded as history"))
        if conditions_satisfied:
            conditions_record = (_RELEASE_CONDITIONS_HISTORY_RECORD
                                 if release_published
                                 else _RELEASE_CONDITIONS_RECORD)
            for required in (conditions_record,
                             _RELEASE_CONDITIONS_MARKERS[3]):
                count = normalized_pointer.count(required)
                if count != 1:
                    out.append(("WORKORDER.md",
                                "release conditions pointer statement",
                                str(count), "exactly one " + required))
            for stale in (_FINAL_AUDIT_HISTORY_RECORD,
                          _WO007_COMPLETED_RELEASE_TRAIN_AMENDMENT):
                if stale in normalized_pointer:
                    out.append(("WORKORDER.md",
                                "release conditions pointer statement",
                                "a pre-conditions statement remains: "
                                + stale[:80],
                                "the satisfied conditions recorded as history"))
        if release_published:
            for required in (_RELEASE_PUBLISHED_RECORD,
                             _RELEASE_PUBLISHED_MARKERS[3]):
                count = normalized_pointer.count(required)
                if count != 1:
                    out.append(("WORKORDER.md",
                                "release publication pointer statement",
                                str(count), "exactly one " + required))
            if _RELEASE_CONDITIONS_RECORD in normalized_pointer:
                out.append(("WORKORDER.md",
                            "release publication pointer statement",
                            "the pre-publication conditions record remains",
                            "the conditions record recorded as history"))
        for stale in (_WO007_ISSUANCE_POINTER_NOTE,
                      _WO007_SESSION_A_POINTER_RECORD,
                      "docs/work-orders/issued/" + _WO007_NAME,
                      "docs/work-orders/proposed/" + _WO007_NAME):
            if stale in normalized_pointer:
                out.append(("WORKORDER.md", "WO-007 completion pointer "
                            "statement", "a stale WO-007 record remains: "
                            + stale[:80], "the completed record only"))
        amendment = (_RELEASE_CONDITIONS_RELEASE_TRAIN_AMENDMENT
                     if conditions_satisfied
                     else _WO007_COMPLETED_RELEASE_TRAIN_AMENDMENT)
        count = normalized_pointer.count(amendment)
        if count != 1:
            out.append(("WORKORDER.md", "WO-007 release-train amendment",
                        str(count), "exactly one " + amendment))
        if any(normalized_pointer.count(earlier)
               for earlier in _WO007_EARLIER_RELEASE_TRAIN_AMENDMENTS):
            out.append(("WORKORDER.md", "WO-007 release-train amendment",
                        "an earlier form of the amendment remains",
                        "only the completed form of the amendment"))
        return out
    lines = [line.strip() for line in text.splitlines()]
    headings = [line for line in lines if line.startswith("## ")]
    unique = True
    for heading in _WO007_COMPLETED_HEADINGS:
        if headings.count(heading) != 1:
            unique = False
            out.append((rel, "WO-007 completed record heading",
                        str(headings.count(heading)), "exactly one " + heading))
    if unique:
        first = headings.index(_WO007_COMPLETED_HEADINGS[0])
        found = tuple(headings[first:first + len(_WO007_COMPLETED_HEADINGS)])
        if found != _WO007_COMPLETED_HEADINGS:
            out.append((rel, "WO-007 completed record heading",
                        " / ".join(found),
                        "consecutive " + " / ".join(_WO007_COMPLETED_HEADINGS)))
    for heading, record in (
        (_WO007_ISSUANCE_HEADING, _WO007_ISSUANCE_HISTORY_RECORD),
        (_WO007_SESSION_A_BASIS_HEADING, _WO007_COMPLETED_BASIS_RECORD),
        (_WO007_EXEMPTION_HEADING, _WO007_EXEMPTION_RECORD),
        (_WO007_COMPLETION_HEADING, _WO007_COMPLETION_RECORD),
    ):
        if headings.count(heading) == 1:
            if _wo005_closed_section(lines, heading) != record:
                out.append((rel, "WO-007 completed record", "a section that "
                            "differs from the accepted record",
                            "exactly " + record))
    normalized = " ".join(text.split())
    for required, kind in (
        (_WO007_EXEMPTION_PROPOSAL, "WO-007 completed record"),
        (_WO007_DRAFTING_PROHIBITION, "WO-007 decision lock"),
        (_WO007_COMPLETED_NEXT_GATE, "WO-007 next gate"),
    ):
        if normalized.count(required) != 1:
            out.append((rel, kind, str(normalized.count(required)),
                        "exactly one " + required))
    gates = [line for line in lines if line.startswith("NEXT GATE:")]
    if len(gates) != 1:
        out.append((rel, "WO-007 next gate", str(len(gates)),
                    "exactly one NEXT GATE"))
    return out


def _wo006_session_record_findings(pointer, issued_text, rel, session="A"):
    """The current session's records while WO-006 Session A or B is open.

    The WO-005 Session A pattern: the headings are unique and consecutive,
    each closed section equals its accepted text, the next gate occurs once
    with no second next gate, and the pointer's statements and their anchored
    form each occur exactly once. For Session A that is one closed section,
    the issuance note, and the Session A record. For Session B the closed
    sections are Session A's authorization basis, kept verbatim, its
    acceptance record, and the Session B basis; the pointer carries the
    issuance note, Session A's history and acceptance, and the Session B
    record.
    """
    statements: tuple[str, ...]
    headings_wanted: tuple[str, ...]
    sections: tuple[tuple[str, str, str], ...]
    if session == "B":
        statements = (_WO006_ISSUANCE_POINTER_HISTORY,
                      _WO006_SESSION_A_POINTER_HISTORY,
                      _WO006_SESSION_A_POINTER_ACCEPTANCE,
                      _WO006_SESSION_B_POINTER_RECORD,
                      _WO006_SESSION_B_POINTER_ANCHORED)
        headings_wanted = _WO006_SESSION_B_HEADINGS
        sections = (
            (_WO006_SESSION_A_BASIS_HEADING, _WO006_SESSION_A_BASIS_RECORD,
             "WO-006 Session A authorization statement"),
            (_WO006_SESSION_A_ACCEPTANCE_HEADING,
             _WO006_SESSION_A_ACCEPTANCE_RECORD,
             "WO-006 Session A acceptance record"),
            (_WO006_SESSION_B_BASIS_HEADING, _WO006_SESSION_B_BASIS_RECORD,
             "WO-006 Session B authorization statement"),
        )
        next_gate = _WO006_SESSION_B_NEXT_GATE
    else:
        statements = (_WO006_ISSUANCE_POINTER_HISTORY,
                      _WO006_SESSION_A_POINTER_RECORD,
                      _WO006_SESSION_A_POINTER_ANCHORED)
        headings_wanted = _WO006_SESSION_A_HEADINGS
        sections = (
            (_WO006_SESSION_A_BASIS_HEADING, _WO006_SESSION_A_BASIS_RECORD,
             "WO-006 Session A authorization statement"),
        )
        next_gate = _WO006_SESSION_A_NEXT_GATE
    label = "WO-006 Session " + session
    out = []
    normalized_pointer = " ".join(pointer.split())
    for required in statements:
        if normalized_pointer.count(required) != 1:
            out.append(("WORKORDER.md", label + " pointer statement",
                        str(normalized_pointer.count(required)),
                        "exactly one " + required))
    lines = [line.strip() for line in issued_text.splitlines()]
    headings = [line for line in lines if line.startswith("## ")]
    unique = True
    for heading in headings_wanted:
        if headings.count(heading) != 1:
            unique = False
            out.append((rel, label + " record heading",
                        str(headings.count(heading)), "exactly one " + heading))
    if unique:
        first = headings.index(headings_wanted[0])
        found = tuple(headings[first:first + len(headings_wanted)])
        if found != headings_wanted:
            out.append((rel, label + " record heading",
                        " / ".join(found),
                        "consecutive " + " / ".join(headings_wanted)))
        for heading, record, kind in sections:
            if _wo005_closed_section(lines, heading) != record:
                out.append((rel, kind,
                            "a section that differs from the accepted record",
                            "exactly " + record))
    normalized = " ".join(issued_text.split())
    if normalized.count(next_gate) != 1:
        out.append((rel, "WO-006 next gate",
                    str(normalized.count(next_gate)),
                    "exactly one " + next_gate))
    gates = [line for line in lines if line.startswith("NEXT GATE:")]
    if len(gates) != 1:
        out.append((rel, "WO-006 next gate", str(len(gates)),
                    "exactly one NEXT GATE"))
    return out


def _wo006_issuance_findings(pointer, issued_text, rel, session="NONE",
                             surface="both"):
    """WO-006's issuance record on the two surfaces that declare it.

    The same canonical-slice checks WO-005's issuance used, with WO-006's
    evidence. It pins the issuance evidence and the root base value, and once
    Session A is authorized, the Session A authorization evidence beside
    them, and once Session B is authorized, the Session B authorization
    evidence after that; once WO-006 is superseded ("SUPERSEDED"), the
    closure basis too. The session value only selects which shape applies;
    the gate, the marker, and the session value itself are checked by the
    branches that call this. `surface` limits the check to the pointer or the
    document, so the document half keeps running under a later pointer owner.
    """
    if surface not in ("both", "pointer", "document"):
        raise ValueError("unknown surface: " + repr(surface))
    shapes: tuple[tuple[tuple[str, ...], tuple[tuple[str, str], ...]], ...]
    if session == "SUPERSEDED":
        shapes = ((_WO006_SUPERSEDED_POINTER_SEQUENCE,
                   _WO006_SUPERSEDED_POINTER_KEYS),
                  (_WO006_SUPERSEDED_ISSUED_SEQUENCE,
                   _WO006_SUPERSEDED_ISSUED_KEYS))
    elif session == "B":
        shapes = ((_WO006_SESSION_B_POINTER_SEQUENCE,
                   _WO006_SESSION_B_POINTER_KEYS),
                  (_WO006_SESSION_B_ISSUED_SEQUENCE,
                   _WO006_SESSION_B_ISSUED_KEYS))
    elif session == "A":
        shapes = ((_WO006_SESSION_A_POINTER_SEQUENCE,
                   _WO006_SESSION_A_POINTER_KEYS),
                  (_WO006_SESSION_A_ISSUED_SEQUENCE,
                   _WO006_SESSION_A_ISSUED_KEYS))
    else:
        shapes = ((_WO006_POINTER_SEQUENCE, _WO006_POINTER_KEYS),
                  (_WO006_ISSUED_SEQUENCE, _WO006_ISSUED_KEYS))
    out = []
    for target, text, stop, (sequence, keys), where in (
        ("WORKORDER.md", pointer,
         lambda line: _WO001_COMPLETED_LINK in line,
         shapes[0], "WORKORDER.md"),
        (rel, issued_text, lambda line: line.startswith("## "),
         shapes[1], "issued record"),
    ):
        if surface == ("document" if target == "WORKORDER.md" else "pointer"):
            continue
        for kind, found, want in _canonical_field_findings(
            text, sequence, stop, where,
            exact={item for item in sequence if "`" in item},
            terminal=True, label="WO-006 issuance field",
        ):
            out.append((target, kind, found, want))
        for kind, found, want in _canonical_key_findings(
            text, stop, keys, "WO-006 issuance declaration (" + where + ")",
        ):
            out.append((target, kind, found, want))
    return out


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


# WO-008 is an exact following-train identity, not a frozen-train extension.
_WO008_ID = "WO-008"
_WO008_NAME = "WO-008-user-reliability-and-mcp-client-acceptance.md"
_WO008_BASE = "4ff86e8d1c9c89ebda597570ad4f757605ccd81e"
_WO008_GATE = "WO-008 ISSUED — SESSION A OFFLINE PREPARATION NOT AUTHORIZED"
_WO008_INSTRUCTION_SHA256 = (
    "5997654fb63b587ae72265d4382bf9f2f8a752e4fb09a6d79593a5b88725746a"
)
_WO008_POINTER_RECORD = "WO-008 closed issuance record: the owner adopted the accepted\nissuance/session-enforcement plan r2 and authorized only its seven-path\nclosed-issuance implementation under an offline-verification exemption for\nthis governance scope. The instruction is identified by SHA-256\n`5997654fb63b587ae72265d4382bf9f2f8a752e4fb09a6d79593a5b88725746a`.\n[`WO-008-user-reliability-and-mcp-client-acceptance.md`](docs/work-orders/issued/WO-008-user-reliability-and-mcp-client-acceptance.md)\nis issued outside the frozen train with session NONE. Admission CI workflow\n`37246398757` and job `111565059168` succeeded on\n`4ff86e8d1c9c89ebda597570ad4f757605ccd81e`; they cover admission only,\nnot this transition, Session A outputs, a live build or MCP-host acceptance.\nSession A offline preparation, live start, Session B and Session C remain\nunauthorized. Runtime or live need stops this transition. Configuration\nchanges, installations, recovery, exact commits, pushes, cleanup, further\ntags or Releases, metadata and publication remain separately gated.\nThis record grants none of those authorities."
_WO008_OPENING = "This is an issued following-train Work Order, outside the frozen\nWO-001 through WO-007 train. Issuance alone grants no session authority.\nThe root pointer identifies WO-008 with session NONE. Session A offline\npreparation, live start, Session B and Session C remain unauthorized."
_WO008_PREREQUISITES = "Proposal admission was separately accepted and committed at\n`4ff86e8d1c9c89ebda597570ad4f757605ccd81e`. It recognized this exact\nfollowing-train proposal only and retained NONE/NONE. WO-008 is not added\nto the frozen WO-001 through WO-007 train.\n\nThe separately adopted issuance/session-enforcement plan r2 supports this\nclosed issuance only. Later offline preparation, live start, product\ncorrections and live acceptance still need separately reviewed enforcement\ntransitions and explicit owner decisions. No later phase is installed here.\nFrozen-train missing, duplicate and misplaced-order protections, publication\nhistory and earlier terminal records remain in force. Unknown issued orders\nremain invalid; there is no blanket scanner exemption."
_WO008_ISSUANCE_RECORD = "BASELINE: `4ff86e8d1c9c89ebda597570ad4f757605ccd81e`\nAdmission CI workflow: `37246398757`\nAdmission CI job: `111565059168` — Lint, types, tests\nOwner issuance instruction SHA-256: `5997654fb63b587ae72265d4382bf9f2f8a752e4fb09a6d79593a5b88725746a`\n\nThe owner adopted the accepted plan r2 and authorized only this closed\ngovernance issuance transition. Admission CI succeeded on the baseline,\nnot on this uncommitted transition or any session output; it demonstrates\nneither an MCP host nor a live UEFN build.\n\nThe owner accepted a narrow offline-verification exemption for these seven\ngovernance paths only. Runtime or live need stops this transition. This\nrecord grants no session execution, configuration change, installation,\nUEFN contact, recovery, commit, push, cleanup or publication authority."
_WO008_NEXT_GATE = "NEXT GATE: separate owner decision on Session A offline preparation.\nNo session is authorized. Live start, Session B, Session C, product corrections,\nrecovery, exact commits and pushes remain separate decisions. This mandate\ngrants no review, implementation, commit or push authority."
_WO008_POINTER_SEQUENCE = (
    "- Current issued Work Order: WO-008",
    "- Authorized session: NONE",
    "- Base commit: `" + _WO008_BASE + "`",
    "- Current gate: " + _WO008_GATE,
    "- WO-008 admission basis commit: `" + _WO008_BASE + "`",
    "- WO-008 admission CI workflow: `37246398757`",
    "- WO-008 admission CI job: `111565059168` — Lint, types, tests",
    "- WO-008 issuance decision SHA-256: `" + _WO008_INSTRUCTION_SHA256 + "`",
)
_WO008_ISSUED_SEQUENCE = (
    "STATUS: ISSUED", _ISSUED_NO_SESSION_AUTH,
    "Owner: Ocean Bennett",
    "Priority: user-facing reliability and missing integration evidence",
    "Draft date: 2026-10-04", "Revision: r2",
    "Planning baseline: `9879d39fbdb58083a0f7229a9c9c90c7d6fb375f`",
)
_WO008_CONDITIONAL_PARAGRAPHS = (
    ("## Session A Real client baseline", "The owner selected **Claude Code** as the first MCP client. This selects a test\ntarget only; it grants no setup or live authority and establishes no compatibility.\nSession A, if separately authorized, changes no product code. Use Claude Code\nand an owner-approved disposable project, not a production project or recovery\nof the old WO-006 fixture. Prepare and review the exact call sequence offline\nbefore a separate owner instruction starts live contact. No launcher rehearsal\nor timing harness is required."),
    ("## Session B Bounded reliability corrections", "Session B requires accepted Session A evidence and a separate owner-authorized\nfile/test plan. An unexpected integration defect needs its own bounded amendment;\nthe words \"fix integration\" do not authorize an open-ended transport rewrite."),
    ("## Session B Bounded reliability corrections", "Proposed maximum product scope is\n`Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py`,\n`Content/Python/UEFN_Toolbelt/dashboard_pyside6.py`,\n`Content/Python/UEFN_Toolbelt/menu.py`, `tests/test_mcp_security.py`,\n`tests/test_repo_integrity.py`, `README.md`, `SECURITY.md`,\n`.claude/mcp_reference.md`, `docs/OFFICIAL_MCP_AND_TOOLBELT.md`, and a new\nunreleased entry in `docs/CHANGELOG.md`. The owner-approved Session B plan must\nnarrow this list to files actually needed. Do not edit historical records or\nthe released 2.5.0 notes. No version change is proposed."),
    ("## Session B Bounded reliability corrections", "Run affected tests and static gates on final uncommitted content. Damage probes\nmust show the new tests catch the intended defects. Leave all work uncommitted\nfor independent review; apply only authorized corrections before Session C."),
    ("## Decision locks and next gate", "The owner reserves proposal adoption and admission, issuance, session starts,\nthe client/project/fixture/target choices, live start, any unexpected repair,\nrecovery, exact commits, pushes, completion, and any later release decision.\nReview acceptance never substitutes for these decisions."),
)
# Exact accepted historical paragraphs, on the pointer surface only. They
# are independently bound to the preserved publication pointer below; a
# changed, duplicated, fused or displaced paragraph receives no exemption.
_WO008_POINTER_HISTORY_PARAGRAPHS = (
    "[`WO-001-custom-mcp-security.md`](docs/work-orders/completed/WO-001-custom-mcp-security.md)\r\nis completed as `ffcbe8b1bfa03cb37453b9beefda0bbdbe45543c` after\r\n[CI workflow `32921154482`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32921154482)\r\npassed.\r",
    "[`WO-002`](docs/work-orders/completed/WO-002-epic-toolset-integration.md)\r\nis completed. Session A was independently accepted, committed, and pushed as\r\n`50b881716abea3b5838c2a971caac40ee4cd5d30`; [CI workflow\r\n`32937631903`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32937631903)\r\ncompleted successfully, including required job\r\n[`98081919978` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32937631903/job/98081919978).\r\nSession A is accepted and complete.\r",
    "Session B was independently accepted and committed as\r\n`c031f20e33c716ecc9f9ce546a7419b865ed8641`; [CI workflow\r\n`33133090929`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33133090929)\r\ncompleted successfully, including required job\r\n[`98726805137` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33133090929/job/98726805137).\r\nExternal official-MCP exposure failed and was accepted as a terminal\r\nnegative result bounded by ToolsetPolicy. WO-002 is complete; no session\r\nis authorized.\r",
    "[`WO-003`](docs/work-orders/completed/WO-003-official-mcp-doc-convergence.md)\r\nis completed. Its accepted planning baseline is\r\n`e0b1063f5300404534c76789bdb6742f639425ba`; the accepted revision was\r\ncommitted as `19350aa324bea4d88e494ee806801586a383d76e` after CI\r\nworkflow `33148089523` and required job `98773518991` passed.\r",
    "Session A was independently accepted, committed, and pushed as\r\n`d23add58e02ddc855573cf9be7a2542776d25e7e`; successful CI workflow\r\n`33344006899` included successful required job `99344607213` (`Lint, types,\r\ntests`). Accepted live `TOOL_TEST` evidence recorded a deploy and full UEFN\r\nrestart, 362 tools across 55 categories, corrected dashboard About ordering,\r\nmatching source and deployed runtime hashes, no Fortnite or play session and no\r\nlevel mutation, then a stopped listener, closed UEFN, absent handoff, and closed\r\nports 8765–8770. At the Session A acceptance gate, Session A was accepted and\r\ncomplete with no current implementation authority; Session B was not authorized\r\npending separate owner authorization.\r",
    "Session B's repository-description draft was independently accepted. The\r\naccepted draft was committed and pushed as\r\n`e23baa40c4b9358eb6b4448f460c054650ae64f0`; successful CI workflow\r\n`33476969423` included successful required job `99758148278` (`Lint, types,\r\ntests`). At that gate the live GitHub repository description was still\r\nunchanged, applying the exact accepted repository description was still a\r\nseparate owner-authorized external action, and metadata application was not\r\nauthorized. Tags, Releases, and social publication remain unauthorized, as do\r\nSession C and WO-004.\r",
    "The exact accepted repository description was applied to the live GitHub\r\nrepository under separate BDFL/owner authorization, at repository commit\r\n`624ccc7f8f28cc897ec580c660607524ad5a4a3d`. The applied value is exactly\r\n`UEFN Toolbelt: 362 Python automation tools across 55 categories, with a PySide6 dashboard and an experimental, authenticated same-user loopback bridge for local AI control. Complements Epic's official UEFN MCP; Toolbelt is not exposed through Epic's MCP server.`\r\nIts character count is `261` and\r\nits SHA-256 is\r\n`a2d3b9a40e187c1fc4bce18666e3095687cc94b45d10ab27f1bee1e1e3417415`; a\r\nread-only `gh repo view` read-back returned the applied value byte for byte.\r\nThe homepage `https://www.fortnite.com/@ohshh`, PUBLIC visibility, archived\r\nstate `false`, and all 20 repository topics are unchanged. No file, commit,\r\npush, tag, Release, branch-protection setting, other repository metadata, or\r\nsocial state changed. At that gate WO-003 remained issued, and its completion\r\ntransition required a separate owner gate.\r",
    "WO-003 is completed as `7a7eedb493cbf810f758383a1fc66a285bca841a`; [CI workflow\r\n`34301244038`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34301244038)\r\ncompleted successfully, including required job\r\n[`102308406590` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34301244038/job/102308406590).\r\nThe repository-description application record is preserved and still enforced\r\nfrom the completed Work Order document. WO-003 is complete; no session is\r\nauthorized. Session C or any later session, tagging, Release creation,\r\nbranch-protection changes, other repository metadata changes, and social\r\npublication all remain unauthorized.\r",
    "[`WO-004`](docs/work-orders/completed/WO-004-modal-observability.md) is\r\ncompleted. Its accepted planning baseline is\r\n`0d513f1639cf197707132205f4074d0fe3a750cc`; the independently accepted\r\nproposal was committed as `8444faf340afe47765c43d943200db712880817b`\r\nafter [CI workflow\r\n`34441169191`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34441169191)\r\ncompleted successfully, including required job\r\n[`102756337393` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34441169191/job/102756337393).\r",
    "At that gate, issuance gave no implementation authority and opened no\r\nsession. Session A feasibility work needed its own separate owner gate recorded\r\nin this pointer, and Session B and Session C stayed closed behind it. Tagging,\r\nRelease creation, branch-protection changes, other repository metadata\r\nchanges, and social publication remained unauthorized, as did WO-005,\r\nWO-006, and WO-007, which stayed proposed.\r",
    "At the Session A authorization gate, this pointer opened read-only\r\nfeasibility planning only, on the basis of commit\r\n`f9fc7268d63dad92f5dd009bbf20e11477b8f926`, successful CI workflow\r\n`34509193110`, and successful required job `102978793893` (`Lint, types,\r\ntests`). That gate covered source and documentation inspection and the\r\ndrafting of proposed probes, and it opened no live UEFN work. Live Probe A\r\nran later under a separate owner authorization and is recorded in Section 6\r\nof the [Session A record](docs/audits/2026-09-10-wo004-session-a-modal-feasibility.md),\r\nwith preserved evidence under `docs/audits/evidence/wo004-probe-a/`. Probes\r\nB and C were not run.\r",
    "The owner accepted Session A's bounded findings. Session A is accepted as\r\n`c4c21caa0960c430a4bcfb90cd65ef1edfc1a790`; [CI workflow\r\n`34735715115`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34735715115)\r\ncompleted successfully, including required job\r\n[`103666661855` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34735715115/job/103666661855).\r\nPython post-tick callback silence was observed; its cause, any modal\r\ndiagnosis, and heartbeat reliability remain unproven. WO-004's remaining work\r\nis narrowed to client timeout and error semantics, to direct loopback client\r\ntransport that bypasses HTTP proxies, and to no-automatic-retry guidance; modal\r\ndetection, heartbeat and status endpoints, and further feasibility probes are\r\ndeferred. The decision and the amended Session B and\r\nSession C scope are recorded in the issued mandate. At that gate, Session B\r\nimplementation and Session C live testing were not authorized, and each\r\nrequired a separate owner gate recorded here.\r",
    "At the Session B authorization gate, this pointer opened client outcome\r\nsemantics only, on the basis of commit `da846ec36773d673ca9dcab3025ac36555579d0f`,\r\nsuccessful CI workflow `36375370541`, and successful required job\r\n`108780005124` (`Lint, types, tests`). That gate covered the amended Session B\r\nscope recorded in the issued mandate - client outcome classification and\r\nwording, direct loopback transport for bridge requests, and no-automatic-retry\r\nguidance - in `client.py`, `mcp_server.py`, `.claude/mcp_reference.md`, and\r\n`tests/test_mcp_security.py` only, ending with that worktree uncommitted for\r\nindependent review. It opened no bridge change, deploy, UEFN launch, bridge startup,\r\nMCP call, commit, or push, and Session C live testing was not authorized\r\nat that gate.\r",
    "At the Session C authorization gate, this pointer opened owner-operated live\r\nacceptance only, on the basis of commit `17b5afe3f50bfa3ab882ff362a10eef70750c694`,\r\nsuccessful CI workflow `36385787242`, and successful required job\r\n`108810759914` (`Lint, types, tests`). That CI ran on the base commit, which did\r\nnot contain the Session B implementation. At that gate the implementation was\r\nuncommitted; it had been accepted on local checks and independent static review\r\nonly, and the mandate records its reviewed file identities. That gate covered\r\nthe owner-operated live acceptance procedure in the mandate, including its\r\nruntime and updated-editor prerequisites, against exactly that uncommitted\r\nimplementation. It changed no implementation file and opened no commit or push.\r",
    "WO-004 is completed as `b4fa0a5245944fd992b6a2b52dbac1e59de242ae`; [CI workflow\r\n`36494750779`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36494750779)\r\ncompleted successfully, including required job\r\n[`109171582586` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36494750779/job/109171582586).\r\nThat commit carries the independently accepted client implementation, the\r\nSession C authorization transition, and the independently accepted [Session C\r\nlive-acceptance record](docs/audits/2026-09-28-wo004-session-c-live-acceptance.md)\r\nwith its evidence. Completion accepts the narrowed client-outcome work only; it\r\nclaims no modal detection, exactly-once execution, MCP-host integration, or\r\nbridge exception fix. WO-004 is complete; no session is authorized. WO-006 and\r\nWO-007 stayed proposed. Any later session, tagging, Release creation,\r\nbranch-protection changes, other repository metadata changes, and social\r\npublication all remain unauthorized.\r",
    "[`WO-005`](docs/work-orders/completed/WO-005-coverage-source-of-truth.md) is\r\ncompleted. Its planning baseline is `1925ba8a09c3696d25de7ffc3f23caf970362c4d`;\r\nthe independently accepted proposal was committed as\r\n`528f1962c0c45c0631bab3637f3fd40db6317027` after [CI workflow\r\n`36529997892`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36529997892)\r\ncompleted successfully, including required job\r\n[`109281301869` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36529997892/job/109281301869).\r",
    "At its issuance gate, WO-005 gave no implementation authority and opened no\r\nsession. Session A needed its own separate owner gate recorded in this\r\npointer, and the live-verification exemption proposed for it was not accepted\r\nat that gate.\r",
    "At the Session A authorization gate, this pointer opened the offline coverage\r\nmodel only, on the basis of commit `867074f8a520450ef6073b4c922079a897a83886`,\r\nsuccessful CI workflow `36596756689`, and successful required job\r\n`109503539592` (`Lint, types, tests`). That gate covered the Session A scope\r\nrecorded in the mandate, unchanged, and ended with that worktree uncommitted\r\nfor independent review. The owner accepted the proposed live-verification\r\nexemption for that offline scope only, on the terms recorded in the mandate;\r\nit gave no commit, push, deploy, or live-run permission. That gate opened no\r\ndeploy, UEFN launch, bridge startup, MCP call, commit, or push.\r",
    "WO-005 is completed as `5ef3aef2934b33a357ab9114e68aae41bc78639c`; [CI workflow\r\n`36662471593`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36662471593)\r\ncompleted successfully, including required job\r\n[`109719997181` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36662471593/job/109719997181).\r\nThat commit carries the independently accepted Session A implementation: the\r\nregistry-derived coverage report with its explicit evidence mappings and\r\ntests, the generated `TOOL_STATUS.md` block with the named corrections, the\r\nshared registry enumerator behind `drift_check`, and the `list_untested.py`\r\nmigration shim. Source categories describe what test code is written to\r\ncheck; they establish no live verification of any tool. WO-005 is complete;\r\nno session is authorized. WO-006 and WO-007 stayed proposed, and the optional\r\nintegration run stayed deferred. Any later session, tagging, Release creation,\r\nbranch-protection changes, other repository metadata changes, and social\r\npublication all remain unauthorized.\r",
    "[`WO-006`](docs/work-orders/superseded/WO-006-official-vs-toolbelt-benchmark.md) is\r\nsuperseded. Its planning baseline is `f9354feaf4ab072c9941ab4d6ec8337395ce18a0`;\r\nthe independently accepted proposal was committed as\r\n`0c0bf26191ee953c7a27237109b4a91a4db97275` after [CI workflow\r\n`36743995194`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36743995194)\r\ncompleted successfully, including required job\r\n[`109985389182` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36743995194/job/109985389182).\r",
    "At its issuance gate, WO-006 gave no implementation authority and opened no\r\nsession. Session A, the offline design and harness, needed its own separate\r\nowner gate recorded in this pointer, and Session B, the owner-operated live\r\nmeasurement, stayed closed behind it.\r",
    "At the Session A authorization gate, this pointer opened the offline design and\r\nharness only, on the basis of commit `d46a30ed9de54ec01536d132e1032fcf762fa3c7`,\r\nsuccessful CI workflow `36756889729`, and successful required job\r\n`110029304446` (`Lint, types, tests`). That evidence established the issued\r\nmandate, not any harness implementation or test result. That gate covered the\r\nSession A scope recorded in the issued mandate, unchanged, changed no\r\nrepository file, and ended with its private artifacts held for independent\r\nreview. It opened no deploy, UEFN launch, bridge startup, MCP call, connection\r\nto a real editor endpoint, live measurement, commit, or push, and Session B\r\nstayed closed at that gate.\r",
    "The owner accepted Session A's private offline artifacts after independent\r\nreview, as offline preparation only and not as proof of live compatibility.\r\nThe accepted harness package and its preserved independent review are kept in\r\nthe owner's private evidence folder, identified by their `SHA256SUMS` digests\r\n`f17a44a477b2fb2d3d347a75232c7076516ce110308aeb25c0efefad90dff3f8` and\r\n`a856bdfff88565831905b0e1fcd77862e408b0eb704774ac1631da9225ac94c1`. The\r\nharness and its stub tests ran offline on the owner's Windows machine only;\r\nthey have never run in GitHub CI, and no repository commit or CI run attests\r\nto them. Session A is accepted and closed.\r",
    "At the Session B authorization gate, this pointer opened owner-operated live\r\nmeasurement only, on the basis of commit\r\n`8667b0e0ef78d504586d710984ef1a1fef7263b2`, successful CI workflow\r\n`36801338578`, and successful required job `110176132684` (`Lint, types,\r\ntests`). That CI tested the repository's checker and tests, not the private\r\nharness, and established no live result. That gate covered the Session B scope\r\nrecorded in the issued mandate, unchanged: the owner operated UEFN and\r\nperformed the owner checks, and the accepted harness ran only after the\r\nowner's separate, explicit instruction to begin the live run. It changed no\r\nrepository file and ended with its private artifacts held for independent\r\nreview. It opened no code change, fallback, emulation, policy change, live\r\nrepair, commit, or push, and the evidence-recording transition and WO-006\r\ncompletion stayed closed at that gate. Tagging, Release creation,\r\nbranch-protection changes, other repository metadata changes, and social\r\npublication all remain unauthorized, and WO-007 stayed proposed at that gate.\r",
    "[`WO-006`](docs/work-orders/superseded/WO-006-official-vs-toolbelt-benchmark.md)\r\nis superseded. It closed without an accepted measurement under the owner's\r\nclosure decision recorded in its mandate, which keeps its unmet requirements.\r\nWO-006 cannot be resumed or completed, and no session is authorized. WO-007\r\nstayed proposed at that gate.\r",
    "WO-006 was superseded as `5d88a4ee56309df43537d289514a150615dfeba6`; [CI\r\nworkflow `37037329967`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37037329967)\r\ncompleted successfully, including required job\r\n[`110938646551` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37037329967/job/110938646551).\r\nIts closure basis was commit `13e0bbb67f98ac3f33aff917737fcf9b77a3d64c`,\r\nsuccessful CI workflow `36817435116`, and successful required job\r\n`110225453445` (`Lint, types, tests`).\r",
    "[`WO-007`](docs/work-orders/completed/WO-007-public-mcp-explainer.md) is completed.\r\nIts planning baseline is `5d88a4ee56309df43537d289514a150615dfeba6`; the\r\nindependently accepted proposal was committed as\r\n`c04e4a794f1e7d0c607c7ad712cbd28e86a55914` after [CI workflow\r\n`37050236355`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37050236355)\r\ncompleted successfully, including required job\r\n[`110981533635` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37050236355/job/110981533635).\r",
    "At its issuance gate, WO-007 gave no implementation authority and opened no\r\nsession. Session A, the repository explainer and draft variants, needed its\r\nown separate owner gate recorded in this pointer, and its proposed\r\nlive-verification exemption remained pending the owner's decision at that\r\ngate.\r",
    "At the Session A authorization gate, this pointer opened the repository\r\nexplainer and the two private drafts only, on the basis of commit\r\n`c49905067e6c0d7038c467b3ae6f1116640a904a`, successful CI workflow\r\n`37091060115`, and successful required job `111111315920` (`Lint, types,\r\ntests`). That evidence was CI on the issuance commit; it established the issued\r\nmandate, not any Session A output. That gate covered the Session A scope\r\nrecorded in the mandate, unchanged, and ended with its three repository paths\r\nuncommitted and its two private drafts held for independent review. The owner\r\naccepted the proposed live-verification exemption for exactly that scope, with\r\noffline verification only, on the terms recorded in the mandate; it accepted\r\nno publication, runtime change, or live activity. That gate opened no\r\npublication, deploy, UEFN launch, bridge startup, MCP call, benchmark, commit,\r\nor push.\r",
    "WO-007 is completed as `e34e9fcdfb27ef7e443ae4e47799512d5c28489b`; [CI workflow\r\n`37137035181`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37137035181)\r\ncompleted successfully, including required job\r\n[`111243552871` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37137035181/job/111243552871).\r\nThat commit carries the independently accepted Session A repository output:\r\nthe explainer `docs/OFFICIAL_MCP_AND_TOOLBELT.md`, its drift scan-target\r\nentry, and the matching test entry. The two accepted drafts stay private;\r\ntheir counts and SHA-256 identities are recorded in the completed mandate.\r\nCompletion accepts no benchmark result, performance comparison, version\r\nchoice, or publication, and approves publishing neither draft. WO-007 is\r\ncomplete; no session is authorized. With WO-007 completed and WO-006\r\nsuperseded, the frozen train meets the completion condition of the\r\nrelease-train amendment below. The final integration/repository-truth audit,\r\nversion selection, tagging, Release creation, branch-protection changes, other\r\nrepository metadata changes, and social publication all remained unauthorized\r\nat that gate.\r",
    "WO-001 through WO-007 form the frozen next release train. The owner selected\r\nrelease version 2.5.0, recorded in the release preparation record below. No tag\r\nor GitHub Release is authorized until the frozen train is complete, a final\r\nintegration/repository-truth audit passes, and the owner separately authorizes\r\na release session. New proposals default to the following release train unless\r\nthe owner explicitly classifies one as a blocker.\r",
    "Release-train amendment (owner decision): the frozen train remains WO-001\r\nthrough WO-007. WO-006 is closed as superseded without an accepted\r\nmeasurement. It is resolved for this train, not completed, and its unmet\r\nrequirements stay recorded in its mandate. For the release gate above, the\r\nfrozen train is complete when WO-001 through WO-005 and WO-007 are completed\r\nand WO-006 remains superseded. This amendment opens no session and grants\r\nnothing: WO-007 is completed with no session authorized, and the final\r\nintegration/repository-truth audit and a separate owner decision on any\r\nrelease remained required at that gate.\r",
    "Final integration/repository-truth audit record: under a separate owner\r\nauthorization for a read-only audit only, which opened no implementation\r\nsession and no release authority, an independent auditor audited commit\r\n`066cf6d751740c0daaff165fc076be19e1b8e22d`; [CI workflow\r\n`37142847095`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37142847095)\r\ncompleted successfully on that commit, including required job\r\n[`111260679508` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37142847095/job/111260679508).\r\nThe audit changed no repository file and ran no UEFN, deploy, endpoint\r\ncontact, or benchmark. Its verdict is ACCEPT WITH REQUIRED FIX. The private\r\naudit report is identified by its SHA-256\r\n`aed10f85280517a6916398cff384562e2af6fb75d5a0896be7985b01204288f3` and its private logs\r\nby their manifest digest\r\n`88dc0e5bb7c3d246f3fdb03ef05c0ba549805f3012d926feef356f63e3c933b9`.\r",
    "At that gate, two required fixes were outstanding. P1-1: public and agent pages\r\nclaimed MCP-host compatibility that no accepted record supports. P1-2: public\r\nand agent pages presented the smoke test's registration checks as tool\r\nexecution or schema validation. At that gate, the final audit had not passed\r\nthe release gate. The `.mcp.json` fresh-clone documentation defect remained\r\nqueued for\r\ncorrection with them. The version choice, the checker's handling of historical\r\nversion lines, the pinned-port configuration, the agent settings, the privacy\r\nfinding, and the disclosure of the security fix remained open owner decisions;\r\nthat record neither accepted nor waived any of them. Release preparation, any\r\nversion bump, tagging, Release creation, branch-protection changes, other\r\nrepository metadata changes, and social publication all remained unauthorized\r\nat that gate.\r",
    "Release preparation record: under a separate owner authorization for one\r\nbounded release-preparation session, which opened no review, commit, push, tag,\r\nRelease, or publication authority, the repository was prepared on base commit\r\n`fb7f9540464ac0898662087d4f70caa534de60d6`; [CI workflow\r\n`37149178090`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37149178090)\r\ncompleted successfully on that commit, including required job\r\n[`111279224830` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37149178090/job/111279224830).\r\nThe owner adopted version 2.5.0, with an explicit read-before-upgrading section\r\nand no backward-compatibility claim; MCP-host claims limited to the evidence,\r\nso integration after the hardening is stated as untested; the smoke test\r\ndescribed as registration and module-loading checks that execute no tool and\r\nvalidate no schema; fresh-clone setup through a local, gitignored `.mcp.json`\r\ncopied from `.mcp.json.template`; no pinned port in that template;\r\n`enableAllProjectMcpServers`, `Bash(python -c *)`, and `Bash(find*)` removed\r\nfrom the shared agent settings; the profile path in `docs/UEFN_QUIRKS.md`\r\nredacted, with completed mandates and Git history unchanged; disclosure of the\r\nreleased unauthenticated `execute_python` issue and of the proxy and redirect\r\nbearer leak on unreleased `main`, without exploit detail or a GitHub advisory;\r\nthe checker's historical-version exemption limited to exact lines; and an\r\noffline live-verification exemption for this preparation change, whose only\r\n`Content/Python` edit is `__version__` and which supplies no live verification.\r\nThe private authorization is identified by its SHA-256\r\n`aa6f386781c9db3d11ae54012aaef2184ca985edc876cf25ae4d95b880f2f40a`. At that\r\ngate, the final audit had not passed the release gate; passing it required an\r\nindependent recheck of the required fixes and the affected changes, which that\r\nauthorization did not open. Tagging, Release creation, branch-protection\r\nchanges, other repository metadata changes, and draft or social publication all\r\nremained unauthorized at that gate.\r",
    "Final audit recheck record: under separate owner authorizations, an independent\r\nreviewer that authored none of the release preparation reviewed it against the\r\nfinal audit's required fixes and returned ACCEPT WITH REQUIRED FIX; after a\r\nbounded correction, its scoped re-review of that correction returned ACCEPT,\r\nand the owner accepted that review. The accepted content is committed as\r\n`82f256da98dc606de9fcca19afd68de2c69a026d`; [CI workflow\r\n`37172802902`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37172802902)\r\ncompleted successfully on that commit, including required job\r\n[`111349057775` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37172802902/job/111349057775),\r\nwhich logged 2529 passed and 14 skipped on Linux. Within the accepted scope,\r\nP1-1, P1-2, and the queued `.mcp.json` fresh-clone documentation defect are\r\nresolved. The original audit record above keeps its verdict, ACCEPT WITH\r\nREQUIRED FIX, as history; this record is a separate follow-up acceptance, not a\r\nrewritten pass. The private review reports are identified by their SHA-256\r\n`4ecc6fd0284c1bfb9a1461b11355904615f49852219c87b29474f5a288e10b00` and\r\n`9e848b0fe84bc002689548db6cbde834fded5574eb94b7a2370a5227b860a642`, and their\r\nprivate logs by their manifest digests\r\n`7da7879c48f5b2f7577f10c52f461cf7d6c029055f8a35838e765bd570c22b69` and\r\n`1ca8d489fee0b1481c1986a21e134cf61742eadd1fb506054179d4e58cca72da`. The\r\ndashboard and menu runtime wording about MCP-compatible clients, and the\r\nlimitations the release notes defer, are disclosed; this record neither fixes\r\nnor waives them. This acceptance supplies no live UEFN, MCP-host, or\r\neffective-permissions evidence. Tagging, Release creation, branch-protection\r\nchanges, other repository metadata changes, and draft or social publication all\r\nremain unauthorized.\r",
    "Release conditions record: the owner accepted that the original final\r\nintegration/repository-truth audit, together with the accepted corrective\r\nrecheck and green CI, satisfies the frozen train's audit condition; this does\r\nnot rewrite the original verdict, ACCEPT WITH REQUIRED FIX, which the audit\r\nrecord above keeps as history with its evidence identities and digests. The\r\nrecheck recording is committed as `b305a1746c59637854a6877fe6196f17ec84e245`;\r\n[CI workflow\r\n`37180447555`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37180447555)\r\ncompleted successfully on that commit, including required job\r\n[`111371778482` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37180447555/job/111371778482).\r\nThe frozen train, WO-001 through WO-007, meets its completion condition: WO-001\r\nthrough WO-005 and WO-007 are completed, and WO-006 remains superseded with no\r\naccepted benchmark. Its audit condition is satisfied. Version 2.5.0 and the\r\naccepted release-preparation content committed as\r\n`82f256da98dc606de9fcca19afd68de2c69a026d` are unchanged. The owner deferred\r\nthe nonblocking review advisories to post-release hygiene: the `.MCP.json` case\r\nvariant in the tracked-configuration test, the incomplete dashboard quotation\r\nin the known issues, the historical-tag wording in `SECURITY.md`, and the\r\nresidual README intent wording (review item P2-7); they remain open, neither\r\nfixed nor waived. The owner's instruction is identified by its SHA-256\r\n`e7083af5399b4c0e0196e4cf481ab85e90d42c8b93905f15d78b59ea77c8a416`. Tagging,\r\nGitHub Release creation, branch-protection changes, other repository metadata\r\nchanges, and draft or social publication each still required a separate owner\r\nexecution authorization at that gate, and that record gave none.\r",
    "Release publication record: under separate owner authorizations given after the\r\nconditions record, the annotated tag `v2.5.0`, tag object\r\n`39afcab4d2f3a8ae3af58fdbd01312c7ec05c93a`, was created on commit\r\n`eabce22518d07725e05173aa707909023166a799` and pushed; [CI workflow\r\n`37186239025`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37186239025)\r\ncompleted successfully on that commit, including required job\r\n[`111388630828` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37186239025/job/111388630828).\r\nGitHub Release `402913965`, titled \"UEFN Toolbelt v2.5.0\", was then published\r\nfrom that tag at 2026-10-04T08:10:21Z, not as a prerelease, and marked Latest.\r\nIts body is the 2.5.0 section of `docs/CHANGELOG.md` at the tag, with only the\r\n`SECURITY.md` link made absolute, and is identified by its SHA-256\r\n`6c1234865662798fdf13eb3f72449565264545b690c6218bc549a794a6e1eb4a`. Statements\r\nin the earlier records above that tagging or Release creation remain\r\nunauthorized describe their own gates; only those separate owner authorizations\r\nchanged that, for v2.5.0 alone. This record is a post-release change and is not\r\npart of the tagged package; `v2.5.0` and every earlier tag stay where they are.\r\nThe owner's instruction is identified by its SHA-256\r\n`aadad5fbeccd0f656dfba476cf035e7cf4aba24324ae93ab47c0ab396168920a`. No further\r\ntagging or GitHub Release creation follows from this record. Social\r\npublication, private-draft publication, and scratch cleanup remain separately\r\ngated, and the deferred review advisories remain open. The next Work Order\r\nawaits a separate owner decision, and no implementation follows from this\r\nrecord.",
)


_WO008_SECTION_HEADINGS = (
    "## Purpose and evidence",
    "## Admission and issuance prerequisites",
    "## Issuance basis",
    "## Session A Real client baseline",
    "## Session B Bounded reliability corrections",
    "## Session C Live acceptance of the corrections",
    "## Process discipline and exclusions",
    "## Decision locks and next gate",
)

# Session A offline preparation (A_PREP) was the first later phase installed.
# Its records replaced the closed current gate and marker; the closed record
# stays as history. A_LIVE, below, now replaces A_PREP's current texts the
# same way.
_WO008_A_PREP_BASE = "0d1de9e6a1f49ea422cd7911d1c40d67787ddde4"
_WO008_A_PREP_WORKFLOW = "37359992194"
_WO008_A_PREP_JOB = "111931901481"
_WO008_A_PREP_INSTRUCTION_SHA256 = (
    "3f2218b675dc2257fffe3ea4e4ceb4e351a23bc651cfd53177fe7ef62882c9ed"
)
_WO008_A_PREP_GATE = (
    "WO-008 SESSION A OFFLINE PREPARATION ONLY — LIVE START NOT AUTHORIZED"
)
_ISSUED_SESSION_A_PREP_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR OFFLINE PREPARATION ONLY"
)
_WO008_A_PREP_POINTER_SEQUENCE = (
    "- Current issued Work Order: WO-008",
    "- Authorized session: A",
    "- Base commit: `" + _WO008_A_PREP_BASE + "`",
    "- Current gate: " + _WO008_A_PREP_GATE,
) + _WO008_POINTER_SEQUENCE[4:] + (
    "- WO-008 closed issuance commit: `" + _WO008_A_PREP_BASE + "`",
    "- WO-008 closed issuance CI workflow: `" + _WO008_A_PREP_WORKFLOW + "`",
    "- WO-008 closed issuance CI job: `" + _WO008_A_PREP_JOB
    + "` — Lint, types, tests",
    "- WO-008 Session A preparation decision SHA-256: `"
    + _WO008_A_PREP_INSTRUCTION_SHA256 + "`",
)
# The closed record as history: exactly two present-tense passages change.
_WO008_CLOSED_HISTORY_RECORD = _replaced_once(_WO008_POINTER_RECORD, (
    ("\nis issued outside the frozen train with session NONE. Admission CI workflow\n",
     "\nwas issued outside the frozen train with session NONE. Admission CI workflow\n"),
    ("Session A offline preparation, live start, Session B and Session C remain\n"
     "unauthorized.",
     "At that gate, Session A offline preparation, live start, Session B and\n"
     "Session C remained unauthorized."),
))
_WO008_A_PREP_POINTER_RECORD = (
    "WO-008 Session A offline preparation record: the owner authorized Session A\n"
    "for offline preparation only, on the basis of the closed issuance committed as\n"
    "`" + _WO008_A_PREP_BASE + "`; [CI workflow\n"
    "`" + _WO008_A_PREP_WORKFLOW + "`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO008_A_PREP_WORKFLOW + ")\n"
    "completed successfully on that commit, including required job\n"
    "[`" + _WO008_A_PREP_JOB + "` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO008_A_PREP_WORKFLOW + "/job/" + _WO008_A_PREP_JOB + ").\n"
    "That CI tested the closed issuance enforcement, not this transition, a\n"
    "Session A output, an MCP host or a live build. The instruction is identified\n"
    "by SHA-256 `" + _WO008_A_PREP_INSTRUCTION_SHA256 + "`.\n"
    "Preparation produces only a redacted exact call plan and a fixture/setup\n"
    "checklist, outside the checkout, for independent review, and changes no\n"
    "repository file. Client launch, configuration reads or changes, dependency\n"
    "installation, deploy, editor contact, bridge lifecycle, endpoint calls,\n"
    "fixture mutation, product changes, recovery, commits and pushes remain\n"
    "unauthorized. Live start needs an accepted call plan and a separate owner\n"
    "live-start instruction recorded here. Session B and Session C remain\n"
    "unauthorized, and this record grants no further authority."
)
_WO008_A_PREP_OPENING = (
    "This is an issued following-train Work Order, outside the frozen\n"
    "WO-001 through WO-007 train. The root pointer identifies WO-008 with\n"
    "Session A authorized for offline preparation only. Live start, Session B\n"
    "and Session C remain unauthorized."
)
_WO008_CLOSED_PREREQUISITES_HEAD = (
    "The separately adopted issuance/session-enforcement plan r2 supports this\n"
    "closed issuance only. Later offline preparation, live start, product\n"
    "corrections and live acceptance still need separately reviewed enforcement\n"
    "transitions and explicit owner decisions. No later phase is installed here."
)
_WO008_A_PREP_PREREQUISITES = _replaced_once(_WO008_PREREQUISITES, ((
    _WO008_CLOSED_PREREQUISITES_HEAD,
    "The separately adopted issuance/session-enforcement plan r2 supported the\n"
    "closed issuance, and a separate transition installs Session A offline\n"
    "preparation only. Live start, product corrections and live acceptance still\n"
    "need separately reviewed enforcement transitions and explicit owner\n"
    "decisions. No later phase is installed here.",
),))
_WO008_A_PREP_HEADING = "## Session A offline preparation record"
_WO008_A_PREP_RECORD = (
    "Session A preparation basis commit: `" + _WO008_A_PREP_BASE + "`\n"
    "Session A preparation CI workflow: `" + _WO008_A_PREP_WORKFLOW + "`\n"
    "Session A preparation CI job: `" + _WO008_A_PREP_JOB + "` — Lint, types, tests\n"
    "Owner Session A preparation instruction SHA-256: `"
    + _WO008_A_PREP_INSTRUCTION_SHA256 + "`\n"
    "\n"
    "The owner authorized Session A for offline preparation only. CI succeeded on\n"
    "the closed issuance commit, not on this transition or any Session A output;\n"
    "it demonstrates neither an MCP host nor a live UEFN build.\n"
    "\n"
    "Preparation produces, outside the checkout, a redacted exact call plan and a\n"
    "fixture/setup checklist for independent review. It reads no owner\n"
    "`.mcp.json`, credential, session handoff or private editor log, and changes\n"
    "no repository file. Client launch, configuration reads or changes, dependency\n"
    "installation, deploy, editor contact, bridge lifecycle, endpoint calls,\n"
    "fixture mutation, product changes, recovery, commits and pushes remain\n"
    "unauthorized. Planned values are not recorded as observed results.\n"
    "\n"
    "The owner accepted a narrow offline-verification exemption for this\n"
    "transition's five governance paths only. Runtime or live need stops the work."
)
_WO008_A_PREP_NEXT_GATE = (
    "NEXT GATE: separate owner decisions on an independent review of the Session A\n"
    "offline call plan and fixture/setup checklist, and then on live start.\n"
    "Live start, Session B, Session C, product corrections, recovery, exact\n"
    "commits and pushes remain separate decisions. This mandate grants no review,\n"
    "implementation, commit or push authority."
)
_WO008_A_PREP_ISSUED_SEQUENCE = tuple(
    _ISSUED_SESSION_A_PREP_AUTH if line == _ISSUED_NO_SESSION_AUTH else line
    for line in _WO008_ISSUED_SEQUENCE)
_WO008_A_PREP_SECTION_HEADINGS = (
    _WO008_SECTION_HEADINGS[:3] + (_WO008_A_PREP_HEADING,)
    + _WO008_SECTION_HEADINGS[3:])
# Substring traces on either surface; the session line is matched exactly so
# that "AA" cannot pass for "A".
_WO008_A_PREP_TRACES = (
    _WO008_A_PREP_GATE,
    "- WO-008 closed issuance commit:",
    "- WO-008 Session A preparation decision SHA-256:",
    "WO-008 Session A offline preparation record:",
    _ISSUED_SESSION_A_PREP_AUTH,
    _WO008_A_PREP_HEADING,
)

# Session A live baseline (A_LIVE): one bounded live run under the owner's X2
# instruction. Its records replace the A_PREP current gate and marker; the
# closed and A_PREP records stay as history. Later phases still have no entry
# in _WO008_PHASES, so their traces fail instead of falling back.
_WO008_A_LIVE_BASE = "075ba2948444e40da9fb975f1cda4c29006b0169"
_WO008_A_LIVE_WORKFLOW = "37698808630"
_WO008_A_LIVE_JOB = "113057020206"
_WO008_A_LIVE_INSTRUCTION_SHA256 = (
    "671d1dfe2c84922709366cf189c2576c8fc3ea96ddd2bc45e1346b9ce22925a9"
)
_WO008_A_LIVE_PLAN_SHA256SUMS = (
    "8e2d7481e4b245ed5e5afb132b9545d3754108907b1c16beb8c64fe3ad8a9add"
)
_WO008_A_PREP_PACKAGE_SHA256SUMS = (
    "8df8abdb4d70882f4ee0d1129907b166fa44f1ffbf87361ca3586d565d261ed1"
)
_WO008_A_PREP_REVIEW_SHA256SUMS = (
    "517b9c15744ee26e4c5967ff00eb9a4476330b723e878eb11902fc9d84e0351a"
)
_WO008_A_LIVE_GATE = (
    "WO-008 SESSION A LIVE BASELINE ONLY — PRODUCT CORRECTIONS NOT AUTHORIZED"
)
_ISSUED_SESSION_A_LIVE_AUTH = (
    "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR THE PINNED LIVE BASELINE ONLY"
)
_WO008_A_LIVE_POINTER_SEQUENCE = (
    "- Current issued Work Order: WO-008",
    "- Authorized session: A",
    "- Base commit: `" + _WO008_A_LIVE_BASE + "`",
    "- Current gate: " + _WO008_A_LIVE_GATE,
) + _WO008_A_PREP_POINTER_SEQUENCE[4:] + (
    "- WO-008 Session A preparation commit: `" + _WO008_A_LIVE_BASE + "`",
    "- WO-008 Session A preparation CI workflow: `" + _WO008_A_LIVE_WORKFLOW + "`",
    "- WO-008 Session A preparation CI job: `" + _WO008_A_LIVE_JOB
    + "` — Lint, types, tests",
    "- WO-008 Session A live baseline instruction SHA-256: `"
    + _WO008_A_LIVE_INSTRUCTION_SHA256 + "`",
)
# The A_PREP records as history: exact-once pairs, applied per record constant
# because the pointer and the mandate share one passage.
_WO008_A_PREP_HISTORY_POINTER_RECORD = _replaced_once(_WO008_A_PREP_POINTER_RECORD, (
    ("Preparation produces only a redacted exact call plan and a fixture/setup\n"
     "checklist, outside the checkout, for independent review, and changes no\n"
     "repository file. Client launch,",
     "Preparation produced only a redacted exact call plan and a fixture/setup\n"
     "checklist, outside the checkout, for independent review, and changed no\n"
     "repository file. At that gate, client launch,"),
    ("fixture mutation, product changes, recovery, commits and pushes remain\n"
     "unauthorized. Live start needs an accepted call plan and a separate owner\n"
     "live-start instruction recorded here.",
     "fixture mutation, product changes, recovery, commits and pushes remained\n"
     "unauthorized. Live start needed an accepted call plan and a separate owner\n"
     "live-start instruction recorded here."),
))
_WO008_A_PREP_HISTORY_RECORD = _replaced_once(_WO008_A_PREP_RECORD, (
    ("Preparation produces, outside the checkout, a redacted exact call plan and a\n"
     "fixture/setup checklist for independent review. It reads no owner\n"
     "`.mcp.json`, credential, session handoff or private editor log, and changes\n"
     "no repository file. Client launch,",
     "Preparation produced, outside the checkout, a redacted exact call plan and a\n"
     "fixture/setup checklist for independent review. It read no owner\n"
     "`.mcp.json`, credential, session handoff or private editor log, and changed\n"
     "no repository file. At that gate, client launch,"),
    ("fixture mutation, product changes, recovery, commits and pushes remain\n"
     "unauthorized. Planned values are not recorded as observed results.",
     "fixture mutation, product changes, recovery, commits and pushes remained\n"
     "unauthorized. Planned values were not recorded as observed results."),
    ("Runtime or live need stops the work.",
     "Runtime or live need stopped that work."),
))
_WO008_A_LIVE_POINTER_RECORD = (
    "WO-008 Session A live baseline record: the owner authorized Session A for the\n"
    "pinned live baseline only, on the basis of the offline preparation committed\n"
    "as `" + _WO008_A_LIVE_BASE + "`; [CI workflow\n"
    "`" + _WO008_A_LIVE_WORKFLOW + "`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO008_A_LIVE_WORKFLOW + ")\n"
    "completed successfully on that commit, including required job\n"
    "[`" + _WO008_A_LIVE_JOB + "` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/"
    + _WO008_A_LIVE_WORKFLOW + "/job/" + _WO008_A_LIVE_JOB + ").\n"
    "That CI tested the offline-preparation enforcement, not this transition, a\n"
    "live result, an MCP host or a live build. The accepted preparation package\n"
    "is identified by SHA256SUMS `" + _WO008_A_PREP_PACKAGE_SHA256SUMS + "`,\n"
    "its review by SHA256SUMS `" + _WO008_A_PREP_REVIEW_SHA256SUMS + "`,\n"
    "and the accepted plan for this transition by SHA256SUMS\n"
    "`" + _WO008_A_LIVE_PLAN_SHA256SUMS + "`. The instruction is\n"
    "identified by SHA-256 `" + _WO008_A_LIVE_INSTRUCTION_SHA256 + "`.\n"
    "Session A may run at most once: one attempt of the accepted call plan, as\n"
    "amended by the accepted execution addendum, through Claude Code with the\n"
    "owner decisions that instruction records, deployed from the clean,\n"
    "synchronized commit that carries this record once that commit's own CI has\n"
    "succeeded. Independent review, the commit, the push and that CI are\n"
    "preconditions only; none of them authorizes or starts the run. Any stop\n"
    "after live-run setup begins ends the attempt. A retry or repeat run needs a\n"
    "new reviewed transition recorded here, and recovery needs a separately\n"
    "bounded owner instruction. A choice or setup item that instruction omits\n"
    "follows the accepted addendum's missing-choice rule. Product corrections,\n"
    "installations or configuration changes that instruction does not name,\n"
    "commits and pushes remain unauthorized. Session B and Session C remain\n"
    "unauthorized, results are recorded only by a separate transition, and this\n"
    "record grants no further authority."
)
_WO008_A_LIVE_OPENING = (
    "This is an issued following-train Work Order, outside the frozen\n"
    "WO-001 through WO-007 train. The root pointer identifies WO-008 with\n"
    "Session A authorized for the pinned live baseline only. Product\n"
    "corrections, Session B and Session C remain unauthorized."
)
_WO008_A_PREP_PREREQUISITES_HEAD = (
    "The separately adopted issuance/session-enforcement plan r2 supported the\n"
    "closed issuance, and a separate transition installs Session A offline\n"
    "preparation only. Live start, product corrections and live acceptance still\n"
    "need separately reviewed enforcement transitions and explicit owner\n"
    "decisions. No later phase is installed here."
)
_WO008_A_LIVE_PREREQUISITES = _replaced_once(_WO008_A_PREP_PREREQUISITES, ((
    _WO008_A_PREP_PREREQUISITES_HEAD,
    "The separately adopted issuance/session-enforcement plan r2 supported the\n"
    "closed issuance and Session A offline preparation, and a separate transition\n"
    "installs the pinned Session A live baseline only. Recording the result,\n"
    "product corrections and live acceptance still need separately reviewed\n"
    "enforcement transitions and explicit owner decisions. No later phase is\n"
    "installed here.",
),))
_WO008_A_LIVE_HEADING = "## Session A live baseline record"
_WO008_A_LIVE_RECORD = (
    "Session A live baseline basis commit: `" + _WO008_A_LIVE_BASE + "`\n"
    "Session A live baseline CI workflow: `" + _WO008_A_LIVE_WORKFLOW + "`\n"
    "Session A live baseline CI job: `" + _WO008_A_LIVE_JOB + "` — Lint, types, tests\n"
    "Accepted preparation package SHA256SUMS: `" + _WO008_A_PREP_PACKAGE_SHA256SUMS + "`\n"
    "Accepted preparation review SHA256SUMS: `" + _WO008_A_PREP_REVIEW_SHA256SUMS + "`\n"
    "Accepted A_LIVE plan SHA256SUMS: `" + _WO008_A_LIVE_PLAN_SHA256SUMS + "`\n"
    "Owner Session A live baseline instruction SHA-256: `"
    + _WO008_A_LIVE_INSTRUCTION_SHA256 + "`\n"
    "\n"
    "The owner authorized Session A for the pinned live baseline only: one run\n"
    "of the accepted call plan, as amended by the accepted execution addendum,\n"
    "through Claude Code against an owner-approved disposable project, with the\n"
    "owner decisions that instruction records. CI succeeded on the preparation\n"
    "commit, not on this transition or any live result; it demonstrates neither\n"
    "an MCP host nor a live UEFN build.\n"
    "\n"
    "Within that one run, Session A uses as its deploy source the clean,\n"
    "synchronized commit that carries this record, after that commit's own CI\n"
    "has succeeded and its runtime and deployment sources are shown unchanged\n"
    "from the basis commit. For Session A the owner performs the deploy, editor\n"
    "start, fixture preparation and local bridge start, and stops the bridge only\n"
    "as the cleanup decision that instruction records allows; Session A's client\n"
    "issues only the nine planned tool calls, each approved individually, with no\n"
    "retry. Any stop after live-run setup begins ends the attempt. Session A\n"
    "recovery, a repeat run, installations or configuration changes that\n"
    "instruction does not name, product corrections, Session B, Session C,\n"
    "commits and pushes remain unauthorized. Results are recorded only by a\n"
    "separate transition.\n"
    "\n"
    "Independent review, the commit, the push and successful CI are\n"
    "preconditions only; none of them authorizes or starts the run. A choice\n"
    "or setup item that instruction omits follows the accepted addendum's\n"
    "missing-choice rule.\n"
    "\n"
    "The owner accepted a narrow offline-verification exemption for this\n"
    "transition's five governance paths only. The live run is Session A\n"
    "evidence, not verification of this transition."
)
_WO008_A_LIVE_NEXT_GATE = (
    "NEXT GATE: separate owner decisions on an independent review of the redacted\n"
    "Session A live evidence, and then on a transition recording its result.\n"
    "Product corrections, Session B, Session C, recovery, a repeat run, exact\n"
    "commits and pushes remain separate decisions. This mandate grants no review,\n"
    "implementation, commit or push authority."
)
_WO008_A_LIVE_ISSUED_SEQUENCE = tuple(
    _ISSUED_SESSION_A_LIVE_AUTH if line == _ISSUED_SESSION_A_PREP_AUTH else line
    for line in _WO008_A_PREP_ISSUED_SEQUENCE)
_WO008_A_LIVE_SECTION_HEADINGS = (
    _WO008_A_PREP_SECTION_HEADINGS[:4] + (_WO008_A_LIVE_HEADING,)
    + _WO008_A_PREP_SECTION_HEADINGS[4:])
# None of these occurs in the A_PREP state; the A_LIVE state keeps the A_PREP
# traces as history, which is why A_LIVE is selected first.
_WO008_A_LIVE_TRACES = (
    _WO008_A_LIVE_GATE,
    "- WO-008 Session A preparation commit:",
    "- WO-008 Session A live baseline instruction SHA-256:",
    "WO-008 Session A live baseline record:",
    _ISSUED_SESSION_A_LIVE_AUTH,
    _WO008_A_LIVE_HEADING,
)
# Three literal entries, not a policy engine. Each phase names its own current
# texts and the prior-state texts that must not survive the change.
_WO008_PHASES: dict[str, dict] = {
    "ISSUED_CLOSED": {
        "pointer_sequence": _WO008_POINTER_SEQUENCE,
        "issued_sequence": _WO008_ISSUED_SEQUENCE,
        "marker": _ISSUED_NO_SESSION_AUTH,
        "gate": _WO008_GATE,
        "pointer_records": (_WO008_POINTER_RECORD,),
        "opening": _WO008_OPENING,
        "prerequisites": _WO008_PREREQUISITES,
        "sections": (("## Issuance basis", _WO008_ISSUANCE_RECORD),),
        "next_gate": _WO008_NEXT_GATE,
        "headings": _WO008_SECTION_HEADINGS,
        "forbidden_pointer": (),
        "forbidden_document": (),
        "label": "WO-008 issuance",
        "record": "WO-008 issuance record",
        "session": "",
    },
    "A_PREP": {
        "pointer_sequence": _WO008_A_PREP_POINTER_SEQUENCE,
        "issued_sequence": _WO008_A_PREP_ISSUED_SEQUENCE,
        "marker": _ISSUED_SESSION_A_PREP_AUTH,
        "gate": _WO008_A_PREP_GATE,
        "pointer_records": (_WO008_CLOSED_HISTORY_RECORD,
                            _WO008_A_PREP_POINTER_RECORD),
        "opening": _WO008_A_PREP_OPENING,
        "prerequisites": _WO008_A_PREP_PREREQUISITES,
        "sections": (("## Issuance basis", _WO008_ISSUANCE_RECORD),
                     (_WO008_A_PREP_HEADING, _WO008_A_PREP_RECORD)),
        "next_gate": _WO008_A_PREP_NEXT_GATE,
        "headings": _WO008_A_PREP_SECTION_HEADINGS,
        # A restored prior-state text reads as a denial; the old
        # prerequisites head trips no scanner at all, so it is named here.
        "forbidden_pointer": (_WO008_POINTER_RECORD, _WO008_GATE),
        "forbidden_document": (_WO008_OPENING, _WO008_NEXT_GATE,
                               _WO008_CLOSED_PREREQUISITES_HEAD,
                               _ISSUED_NO_SESSION_AUTH),
        "label": "WO-008 Session A preparation",
        "record": "WO-008 Session A preparation record",
        "session": "A",
    },
    "A_LIVE": {
        "pointer_sequence": _WO008_A_LIVE_POINTER_SEQUENCE,
        "issued_sequence": _WO008_A_LIVE_ISSUED_SEQUENCE,
        "marker": _ISSUED_SESSION_A_LIVE_AUTH,
        "gate": _WO008_A_LIVE_GATE,
        "pointer_records": (_WO008_CLOSED_HISTORY_RECORD,
                            _WO008_A_PREP_HISTORY_POINTER_RECORD,
                            _WO008_A_LIVE_POINTER_RECORD),
        "opening": _WO008_A_LIVE_OPENING,
        "prerequisites": _WO008_A_LIVE_PREREQUISITES,
        "sections": (("## Issuance basis", _WO008_ISSUANCE_RECORD),
                     (_WO008_A_PREP_HEADING, _WO008_A_PREP_HISTORY_RECORD),
                     (_WO008_A_LIVE_HEADING, _WO008_A_LIVE_RECORD)),
        "next_gate": _WO008_A_LIVE_NEXT_GATE,
        "headings": _WO008_A_LIVE_SECTION_HEADINGS,
        "forbidden_pointer": (_WO008_POINTER_RECORD, _WO008_GATE,
                              _WO008_A_PREP_POINTER_RECORD, _WO008_A_PREP_GATE),
        "forbidden_document": (_WO008_OPENING, _WO008_NEXT_GATE,
                               _WO008_CLOSED_PREREQUISITES_HEAD,
                               _ISSUED_NO_SESSION_AUTH,
                               _WO008_A_PREP_OPENING, _WO008_A_PREP_NEXT_GATE,
                               _WO008_A_PREP_PREREQUISITES_HEAD,
                               _ISSUED_SESSION_A_PREP_AUTH,
                               _WO008_A_PREP_RECORD),
        "label": "WO-008 Session A live baseline",
        "record": "WO-008 Session A live baseline record",
        "session": "A",
    },
}


def _wo008_phase(pointer: str, text: str) -> str:
    """Any trace on either surface selects that phase's full shape.

    A_LIVE is checked first, because the A_LIVE state legitimately keeps
    A_PREP traces in its history. A partial install is then validated against
    the selected shape and fails on what is missing; it can never fall back to
    an earlier clean shape. The session line counts only while the pointer
    names WO-008: an earlier order's Session A, such as WO-007's in its
    historical states, is not a trace.
    """
    if any(trace in pointer or trace in text for trace in _WO008_A_LIVE_TRACES):
        return "A_LIVE"
    lines = pointer.splitlines()
    session_a = ("- Authorized session: A" in lines
                 and "- Current issued Work Order: WO-008" in lines)
    if session_a or any(
        trace in pointer or trace in text for trace in _WO008_A_PREP_TRACES
    ):
        return "A_PREP"
    return "ISSUED_CLOSED"


def _wo008_paragraph_residual(
    text: str, contexts: tuple[tuple[str | None, str], ...],
) -> tuple[list[str], str]:
    """Validate full paragraphs in their own sections before removing once.

    Preserve original case and statement/newline boundaries for the labeled
    and current-session scanners. Failure returns the original text unchanged.
    """
    problems: list[str] = []
    spans: list[tuple[int, int]] = []
    paragraphs = list(re.finditer(r"(?ms)\S.*?(?=\n[ \t]*\n|\Z)", text))
    for heading, expected in contexts:
        normalized = " ".join(expected.split())
        candidates = [m for m in paragraphs
                      if " ".join(m.group().split()) == normalized]
        if " ".join(text.split()).count(normalized) != 1 or len(candidates) != 1:
            problems.append(expected)
            continue
        match = candidates[0]
        headings = list(re.finditer(r"(?m)^## .+$", text))
        owning = [h for h in headings if h.start() < match.start()]
        if heading is None and owning:
            problems.append(expected)
            continue
        if heading is not None:
            if (sum(h.group().strip() == heading for h in headings) != 1
                    or not owning or owning[-1].group().strip() != heading):
                problems.append(expected)
                continue
        spans.append(match.span())
    if problems:
        return problems, text
    residual = text
    for start, end in sorted(spans, reverse=True):
        residual = residual[:start] + "\n" + residual[end:]
    return [], residual


def _wo008_issuance_findings(
    pointer: str, text: str, rel: str, surface: str, phase: str | None = None,
) -> list[tuple[str, str, str, str]]:
    """Validate the actual phase records, never a fabricated wrapper."""
    spec = _WO008_PHASES[phase or _wo008_phase(pointer, text)]
    where = "WORKORDER.md" if surface == "pointer" else rel
    history_sequence = tuple(
        "- Release train: " + _FROZEN_RELEASE_TRAIN if line == "- Release train:"
        else "- Release gate: " + _PUBLISHED_RELEASE_GATE if line == "- Release gate:"
        else line for line in _RELEASE_PUBLISHED_POINTER_SEQUENCE[4:])
    sequence = (spec["pointer_sequence"] + history_sequence
                if surface == "pointer" else spec["issued_sequence"])
    stop = (lambda line: line.startswith("[`WO-001")) if surface == "pointer" else (
        lambda line: line.startswith("This is an issued"))
    keys = tuple((line.split(":", 1)[0] + ":", line) for line in (
        spec["pointer_sequence"] if surface == "pointer" else sequence))
    out = [(where, kind, found, want) for kind, found, want
           in _canonical_field_findings(
               pointer if surface == "pointer" else text, sequence, stop,
               where, exact=frozenset(sequence),
               terminal=True, label=spec["label"])]
    out.extend((where, kind, found, want) for kind, found, want
               in _canonical_key_findings(
                   pointer if surface == "pointer" else text, stop, keys,
                   label=spec["label"]))
    contexts: tuple[tuple[str | None, str], ...]
    if surface == "pointer":
        contexts = tuple((None, record) for record in spec["pointer_records"])
    else:
        if tuple(line for line in text.splitlines() if line.startswith("## ")) != (
            spec["headings"]
        ):
            out.append((where, "WO-008 unsupported phase", "changed section inventory",
                        "only the accepted sections of the installed phase"))
        contexts = (
            (None, spec["opening"]),
            ("## Decision locks and next gate", spec["next_gate"]),
        ) + tuple(("## Admission and issuance prerequisites", paragraph)
                  for paragraph in spec["prerequisites"].split("\n\n"))
        # A closed section may contain several paragraphs. Pin it as a
        # section, not as a prefix or a non-anchored substring.
        for heading, expected in spec["sections"]:
            lines = text.splitlines()
            actual = (_wo005_closed_section(lines, heading)
                      if heading in lines else "")
            if (lines.count(heading) != 1
                    or actual != heading + " " + " ".join(expected.split())):
                out.append((where, spec["record"], heading,
                            "exact accepted closed section"))
        if sum(line.startswith("NEXT GATE:") for line in text.splitlines()) != 1:
            out.append((where, "WO-008 next gate", "missing or duplicated",
                        "exactly one closed NEXT GATE"))
    bad, _residual = _wo008_paragraph_residual(
        pointer if surface == "pointer" else text, contexts)
    out.extend((where, spec["record"], value,
                "one exact accepted paragraph on its owning surface") for value in bad)
    # A prior-state text restored beside valid records would read as a
    # denial; it must not survive the phase change at all.
    normalized = " ".join((pointer if surface == "pointer" else text).split())
    for value in spec["forbidden_" + surface]:
        if " ".join(value.split()) in normalized:
            out.append((where, spec["record"], value,
                        "no prior-state text after the phase change"))
    return out


def _wo008_phase_findings(
    pointer: str, text: str, rel: str, surface: str, phase: str | None = None,
) -> tuple[list[tuple[str, str, str, str]], str]:
    """ISSUED_CLOSED, A_PREP or A_LIVE only; later phases need separate transitions."""
    spec = _WO008_PHASES[phase or _wo008_phase(pointer, text)]
    source = pointer if surface == "pointer" else text
    out = _wo008_issuance_findings(pointer, text, rel, surface, phase)
    where = "WORKORDER.md" if surface == "pointer" else rel
    contexts = (
        tuple((None, value) for value in _WO008_POINTER_HISTORY_PARAGRAPHS)
        + tuple((None, record) for record in spec["pointer_records"])
        if surface == "pointer" else
        _WO008_CONDITIONAL_PARAGRAPHS + (
            (None, spec["opening"]),
            ("## Decision locks and next gate", spec["next_gate"]),
        ) + tuple(("## Admission and issuance prerequisites", paragraph)
                  for paragraph in spec["prerequisites"].split("\n\n")))
    bad, residual = _wo008_paragraph_residual(source, contexts)
    out.extend((where, "WO-008 conditional context", value,
                "one full accepted paragraph in its own section") for value in bad)
    if surface == "pointer":
        # The header is removed only after actual field validation.
        spans = spec["pointer_sequence"] + _RELEASE_PUBLISHED_POINTER_SEQUENCE[4:]
        for line in spans:
            suffix = r"[^\r\n]*" if line in (
                "- Release train:", "- Release gate:") else ""
            residual = re.sub(r"(?m)^" + re.escape(line) + suffix + r"\r?$", "", residual,
                              count=1)
    else:
        # These are section-bound closed records, validated above. Removal
        # preserves case and line boundaries and is singular, never global.
        for value in tuple(body for _heading, body in spec["sections"]) + (
            spec["next_gate"],
        ):
            pattern = r"\s+".join(re.escape(word) for word in value.split())
            residual = re.sub(pattern, "\n", residual, count=1)
        residual = re.sub(r"(?m)^" + re.escape(spec["marker"]) + r"\r?$",
                          "", residual, count=1)
    return out, source if out else residual


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

    return _has_residual_session_authorization(authority_text)


def _has_residual_session_authorization(authority_text: str) -> bool:
    """Scan a prevalidated residual; caller owns canonical context handling."""
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


_CURRENT_SESSION_GRANT = re.compile(
    r"\b(?:authorized|permitted|approved|allowed|cleared|granted|unlocked|"
    r"entitled|free\s+to|may|can|go[- ]ahead|green\s+light|begin|start|"
    r"commence|proceed|resume)\b",
    re.IGNORECASE,
)
# Words that may sit inside a denial or a past-tense phrase ("not yet
# authorized", "was previously approved"). A conjunction or a present-tense
# auxiliary may not, so "was authorized ... and is now permitted" and "not
# idle and authorized" keep their present grant.
_CURRENT_SESSION_SPAN = r"(?:(?!(?:and|or|but|is|are|now|be|being)\b)\w+\s+){0,2}"
# A denial also consumes the activation verb it governs: "not authorized to
# start", "may not begin", and "must not proceed" grant nothing, so the verb
# must not survive to be read as a grant. A separate grant elsewhere in the
# sentence ("..., but it may connect") is untouched.
_CURRENT_SESSION_CLOSED = re.compile(
    r"\b(?:not\s+" + _CURRENT_SESSION_SPAN
    + r"(?:authorized|permitted|approved|allowed|cleared|granted|unlocked|"
    r"entitled)|unauthorized|cannot|can\s+not|may\s+not|must\s+not|"
    r"remains?\s+closed|stays?\s+closed|"
    r"requires?\s+(?:a\s+)?separate\s+(?:owner\s+)?gate)"
    r"(?:\s+(?:to\s+)?(?:begin|start|commence|proceed|resume)\b)?\b",
    re.IGNORECASE,
)
# Past-tense history ("was authorized at that gate") records an earlier state
# and grants nothing now.
_CURRENT_SESSION_HISTORY = re.compile(
    r"\b(?:was|were|had\s+been)\s+" + _CURRENT_SESSION_SPAN
    + r"(?:authorized|permitted|approved|allowed|cleared|granted|unlocked)\b",
    re.IGNORECASE,
)


def _current_session_widening(text: str, label: str,
                              canonical: tuple[str, ...]) -> list[str]:
    """Statements that grant the CURRENT session anything beyond its pinned
    records.

    _has_other_session_authorization deliberately skips statements that name
    only the current session, so extra prose such as "Session A is also
    authorized to connect to the running editor" was never scanned. Here the
    pinned canonical records are removed first (they are enforced exactly,
    elsewhere); any remaining statement that names the current session, by
    label or as "the current session" / "this session", and still carries a
    present-tense grant once closed and past-tense wording is removed, is
    reported. Whitespace is normalized first, so reflowed prose is unaffected.
    """
    normalized = " ".join(text.split())
    for record in canonical:
        normalized = normalized.replace(record, " ")
    mention = re.compile(
        rf"\bsession\s+{re.escape(label)}\b|"
        r"\b(?:the\s+)?(?:current|open|active)\s+session\b|\bthis\s+session\b",
        re.IGNORECASE,
    )
    # Whole sentences, not clauses: splitting at "but" would separate the label
    # from a grant carried by a pronoun ("... not authorized to deploy, but it
    # may connect to the editor").
    statements = re.split(r"[.!?;:|]|##", normalized)
    out = []
    for statement in statements:
        if not mention.search(statement):
            continue
        residual = _CURRENT_SESSION_HISTORY.sub(" ", statement)
        residual = _CURRENT_SESSION_CLOSED.sub(" ", residual)
        if _CURRENT_SESSION_GRANT.search(residual):
            out.append(" ".join(statement.split()))
    return out


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


def _has_release_authorization(pointer: str, other_text: str = "") -> bool:
    """Reject a positive tag or Release grant while the train gate is closed.

    `other_text` is an additional surface - an issued Work Order body. The
    exact-once guard belongs to the POINTER, where those lines are canonical;
    applying it to the combined text made a mandate that legitimately restates
    the closed boundary read as a grant. The body's restatements are removed
    by the same bounded-context mechanism instead. Removal cannot conceal a
    separate positive permission, which is different text and survives it.
    """
    text = " ".join(pointer.split())
    extra = " ".join(other_text.split())
    # The release-gate bullet is one of three pinned texts: closed, closed
    # with the train's conditions recorded as satisfied, or the published
    # tag and Release with no further one authorized. Exactly one may appear;
    # which one the state allows is bound by the contract check.
    gate_lines = [f"- Release gate: {gate}"
                  for gate in (_CLOSED_RELEASE_GATE, _SATISFIED_RELEASE_GATE,
                               _PUBLISHED_RELEASE_GATE)]
    if sum(text.count(line) for line in gate_lines) != 1:
        return True
    allowed = (
        next(line for line in gate_lines if line in text),
        "No tag or GitHub Release is authorized until the frozen train is complete, "
        "a final integration/repository-truth audit passes, and the owner separately "
        "authorizes a release session.",
    )
    for context in allowed:
        if text.count(context) != 1:
            return True
        text = text.replace(context, "", 1)
        extra = extra.replace(context, "")
    # Session B's current drafting-only record repeats the same closed release
    # boundary. It is optional in historical fixtures, exact when present, and
    # removed before the positive-permission scan.
    for statement in (
        _WO003_SESSION_B_POINTER_STATEMENT,
        _WO003_SESSION_B_ACCEPTED_POINTER_STATEMENT,
        _WO003_PRE_APPLICATION_POINTER_STATEMENT,
        _WO003_APPLIED_POINTER_STATEMENT,
    ):
        occurrences = text.count(statement)
        if occurrences > 1:
            return True
        if occurrences == 1:
            text = text.replace(statement, "", 1)
        extra = extra.replace(statement, "")
    text = text + " " + extra
    release_target = r"(?:tag|github\s+release|release\s+session)"
    positive = r"(?:authorized|permitted|approved|cleared|granted|ready)"
    return bool(re.search(
        rf"(?:\b{release_target}\b.{{0,40}}\b{positive}\b|"
        rf"\b{positive}\b.{{0,40}}\b{release_target}\b)",
        text,
        re.IGNORECASE,
    ))


def _has_session_b_external_action_authorization(
    pointer: str, allowed_contexts: tuple[str, ...], other_text: str = ""
) -> bool:
    """Reject applying the draft or publishing it, drafted or accepted.

    The caller supplies the exact statements the current gate is allowed to
    make - the drafting-only pair while Session B drafts, the accepted-and-
    not-applied pair after acceptance, and the pre-application record plus
    the applied record once the description is applied - and each is removed
    once before the scan. The remaining check is intentionally limited to
    description/metadata application and social publication; it is not
    another general authorization-language parser.

    `other_text` is an additional surface - an issued Work Order body. The
    exact-once guard is a POINTER-integrity check: those statements are
    canonical there, and a missing or duplicated one is a finding. A mandate
    that merely quotes one is not a second canonical declaration, so the body
    is scanned with the same statements removed rather than counted. Removal
    cannot hide an independent positive permission, which is different text.
    """
    text = " ".join(pointer.split())
    extra = " ".join(other_text.split())
    for context in allowed_contexts:
        if text.count(context) != 1:
            return True
        text = text.replace(context, "", 1)
        extra = extra.replace(context, "")
    text = text + " " + extra
    action = (
        r"(?:repository\s+metadata|(?:github\s+)?repository\s+description|"
        r"github\s+description|social\s+publication|"
        r"branch[-\s]protection)"
    )
    applied = r"(?:appl(?:y|ied)|updat(?:e|ed)|chang(?:e|ed)|publish(?:ed)?)"
    permission = r"(?:may|can|will|authorized|permitted|approved|completed)"
    return bool(re.search(
        rf"(?:\b{action}\b.{{0,50}}\b(?:authorized|permitted|approved)\b|"
        rf"\b(?:authorized|permitted|approved)\b.{{0,50}}\b{action}\b|"
        rf"\b{action}\b.{{0,50}}\b{permission}\b.{{0,30}}\b{applied}\b|"
        rf"\b{permission}\b.{{0,30}}\b{applied}\b.{{0,50}}\b{action}\b|"
        rf"\b{action}\b.{{0,50}}\b(?:was|is|has\s+been)\s+{applied}\b|"
        rf"\b{applied}\b.{{0,50}}\b{action}\b)",
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
    """Map every @register_tool name to its category, parsed from source.

    Delegates to the shared enumerator in coverage_report.py beside this file,
    loaded by path so `scripts/` need not be on sys.path. The package still
    resolves from ROOT. An unparseable file, a duplicate name, or a
    non-constant name raises RegistryDefect naming each site, rather than
    being skipped or overwritten.
    """
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "_coverage_report", Path(__file__).resolve().parent / "coverage_report.py")
    assert spec is not None and spec.loader is not None
    coverage_report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(coverage_report)
    pkg = Path(ROOT) / "Content" / "Python" / "UEFN_Toolbelt"
    return {site.name: site.category
            for site in coverage_report.enumerate_registrations(pkg)}


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


def _next_release_train_order(current_id: str) -> str | None:
    """The next order in the declared frozen train, or None at its end.

    Read from the declared inventory, not the filesystem. Enumerating state
    directories let one unvalidated file become the highest name and
    silently disable the successor check: `superseded/` validates only the
    superseded WO-006 document, and any other file there is checked only by
    the inventory and duplicate-state checks.
    WO-007 ends the train and yields no successor rather than an invented
    WO-008.
    """
    if current_id not in _RELEASE_TRAIN_IDS:
        return None
    index = _RELEASE_TRAIN_IDS.index(current_id)
    if index + 1 < len(_RELEASE_TRAIN_IDS):
        return _RELEASE_TRAIN_IDS[index + 1]
    return None


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
    if release_gate not in (_CLOSED_RELEASE_GATE, _SATISFIED_RELEASE_GATE,
                            _PUBLISHED_RELEASE_GATE):
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
    # A proposal is required only while a declared frozen-train order has not
    # left proposed/. Once every order is issued, completed, or superseded -
    # as after WO-007's issuance - an empty proposed/ is the correct state.
    unplaced_train = [
        name for _id, name in _RELEASE_TRAIN
        if not any((directory / name).exists()
                   for directory in (issued_dir, completed_dir,
                                     superseded_dir))
    ]
    if not proposals and unplaced_train:
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
    def _placed(name: str) -> bool:
        """True once a Work Order has left proposed/ for issued, completed, or
        superseded."""
        return ((issued_dir / name).exists() or (completed_dir / name).exists()
                or (superseded_dir / name).exists())

    wo002_placed = _placed(_WO002_NAME)
    expected_proposals = set(_REMAINING_RELEASE_PROPOSALS)
    if not wo002_placed:
        expected_proposals.add(_WO002_NAME)
    # An issued or completed Work Order is no longer a proposal. This is
    # derived per name rather than hardcoded per order, so issuing WO-004
    # through WO-007 needs no further edit here.
    for _name in tuple(expected_proposals):
        if _placed(_name):
            expected_proposals.discard(_name)
    frozen_proposal_names = proposal_names - _PLANNING_ONLY_PROPOSALS
    if frozen_proposal_names != expected_proposals:
        add("docs/work-orders/proposed", "release train proposal set",
            "frozen/unregistered: " + repr(sorted(frozen_proposal_names))
            + "; registered: "
            + repr(sorted(proposal_names & _PLANNING_ONLY_PROPOSALS)),
            "frozen: " + repr(sorted(expected_proposals)))

    work_order_docs = sorted((root / "docs" / "work-orders").rglob("*.md"))
    for path in work_order_docs:
        if path.name in _PLANNING_ONLY_PROPOSALS:
            canonical_proposal = proposed_dir / path.name
            if (path != canonical_proposal
                    and not (path == issued_dir / _WO008_NAME
                             and current == _WO008_ID)):
                add(path.relative_to(root).as_posix(),
                    "planning-only proposal placement",
                    "registered proposal outside its canonical path",
                    canonical_proposal.relative_to(root).as_posix())
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
    # The declared frozen train must be present and unambiguous. A missing
    # document is its own finding, never something that quietly changes which
    # order comes next.
    for _train_id, _train_name in _RELEASE_TRAIN:
        if sum(1 for path in state_paths if path.name == _train_name) != 1:
            add("docs/work-orders", "release train inventory",
                _train_id + ": " + _train_name,
                "exactly one document per frozen-train order")
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
    wo004_paths = [path for path in state_paths if path.name == _WO004_NAME]
    wo005_paths = [path for path in state_paths if path.name == _WO005_NAME]
    wo006_paths = [path for path in state_paths if path.name == _WO006_NAME]

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

    # Completing WO-003 is one-way, exactly as applying the description was.
    # A coherent document-only rollback - to the applied-but-not-completed
    # state, to Session B's acceptance, to drafting, or anywhere earlier -
    # must therefore still fail, and so must moving WO-003 back out of
    # completed/. Either would have to edit this file too, which is a
    # visible act.
    # The lock is on WO-003's terminal *document* state, not on the root
    # pointer. WO-003 must stay exclusively under completed/ carrying the
    # completed status and closed authorization markers, and its document
    # cannot be rolled back. The pointer's own completed-state values - base,
    # gate, and the closed session - belong to the branch that owns the
    # pointer, so a later legitimately issued Work Order may take it over
    # without disturbing this lock.
    terminal_wo003_path = completed_dir / _WO003_NAME
    completed_wo003_status, completed_wo003_auth, _text = (
        completed_metadata.get(_WO003_NAME, ([], [], ""))
    )
    if not (
        wo003_paths == [terminal_wo003_path]
        and completed_wo003_status == ["STATUS: COMPLETED"]
        and completed_wo003_auth == [_COMPLETED_NO_SESSION_AUTH]
    ):
        add("docs/work-orders", "completed WO-003 state",
            "the completed WO-003 state was removed or changed",
            "WO-003 exclusively under completed/ with the completed status "
            "and closed authorization markers")

    # Completing WO-004 is one-way in the same way. A coherent document-only
    # rollback - to Session C, to any earlier session, or to issuance - must
    # still fail, and so must moving WO-004 back out of completed/. Like the
    # WO-003 lock above, this locks the document, not the pointer.
    terminal_wo004_path = completed_dir / _WO004_NAME
    completed_wo004_status, completed_wo004_auth, _text = (
        completed_metadata.get(_WO004_NAME, ([], [], ""))
    )
    if not (
        wo004_paths == [terminal_wo004_path]
        and completed_wo004_status == ["STATUS: COMPLETED"]
        and completed_wo004_auth == [_COMPLETED_NO_SESSION_AUTH]
    ):
        add("docs/work-orders", "completed WO-004 state",
            "the completed WO-004 state was removed or changed",
            "WO-004 exclusively under completed/ with the completed status "
            "and closed authorization markers")

    # Completing WO-005 is one-way in the same way, and locks the document,
    # not the pointer.
    terminal_wo005_path = completed_dir / _WO005_NAME
    completed_wo005_status, completed_wo005_auth, _text = (
        completed_metadata.get(_WO005_NAME, ([], [], ""))
    )
    if not (
        wo005_paths == [terminal_wo005_path]
        and completed_wo005_status == ["STATUS: COMPLETED"]
        and completed_wo005_auth == [_COMPLETED_NO_SESSION_AUTH]
    ):
        add("docs/work-orders", "completed WO-005 state",
            "the completed WO-005 state was removed or changed",
            "WO-005 exclusively under completed/ with the completed status "
            "and closed authorization markers")

    # Completing WO-007 is one-way in the same way, and locks the document,
    # not the pointer: a coherent document-only rollback - to Session A, to
    # issuance, or to the proposal - must still fail, and so must moving
    # WO-007 back out of completed/.
    wo007_paths = [path for path in state_paths if path.name == _WO007_NAME]
    terminal_wo007_path = completed_dir / _WO007_NAME
    completed_wo007_status, completed_wo007_auth, _text = (
        completed_metadata.get(_WO007_NAME, ([], [], ""))
    )
    if not (
        wo007_paths == [terminal_wo007_path]
        and completed_wo007_status == ["STATUS: COMPLETED"]
        and completed_wo007_auth == [_COMPLETED_NO_SESSION_AUTH]
    ):
        add("docs/work-orders", "completed WO-007 state",
            "the completed WO-007 state was removed or changed",
            "WO-007 exclusively under completed/ with the completed status "
            "and closed authorization markers")

    # Superseding WO-006 is one-way in the same way, and locks the document,
    # not the pointer: WO-006 must stay exclusively under superseded/ with the
    # superseded status and closed authorization markers. A coherent
    # document-only rollback - to Session B, to any earlier session, or to
    # issuance - must still fail, and so must moving WO-006 back out of
    # superseded/. Either would have to edit this file too, which is a
    # visible act.
    superseded_metadata: dict[str, tuple[list[str], list[str], str]] = {}
    for path in superseded:
        text = path.read_text(encoding="utf-8")
        superseded_metadata[path.name] = (
            [line.strip() for line in text.splitlines()
             if line.startswith("STATUS:")],
            [line.strip() for line in text.splitlines()
             if line.startswith("AUTHORIZATION:")],
            text,
        )
    terminal_wo006_path = superseded_dir / _WO006_NAME
    superseded_wo006_status, superseded_wo006_auth, _text = (
        superseded_metadata.get(_WO006_NAME, ([], [], ""))
    )
    if not (
        wo006_paths == [terminal_wo006_path]
        and superseded_wo006_status == [_WO006_SUPERSEDED_STATUS]
        and superseded_wo006_auth == [_WO006_SUPERSEDED_AUTH]
    ):
        add("docs/work-orders", "superseded WO-006 state",
            "the superseded WO-006 state was removed or changed",
            "WO-006 exclusively under superseded/ with the superseded status "
            "and closed authorization markers")

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

    wo003_completed_text = ""
    if _WO003_NAME in completed_metadata:
        wo003_completed_text = completed_metadata[_WO003_NAME][2]

    wo004_completed_text = ""
    if _WO004_NAME in completed_metadata:
        wo004_completed_text = completed_metadata[_WO004_NAME][2]

    wo005_completed_text = ""
    if _WO005_NAME in completed_metadata:
        wo005_completed_text = completed_metadata[_WO005_NAME][2]

    wo006_superseded_text = ""
    if _WO006_NAME in superseded_metadata:
        wo006_superseded_text = superseded_metadata[_WO006_NAME][2]

    wo007_completed_text = ""
    if _WO007_NAME in completed_metadata:
        wo007_completed_text = completed_metadata[_WO007_NAME][2]

    wo008_paths = [path for path in state_paths if path.name == _WO008_NAME]
    wo008_issued = issued_dir / _WO008_NAME
    wo008_status, wo008_auth, wo008_text = issued_metadata.get(
        _WO008_NAME, ([], [], ""))
    wo008_phase = _wo008_phase(pointer, wo008_text)
    if not (wo008_paths == [wo008_issued]
            and wo008_status == ["STATUS: ISSUED"]
            and wo008_auth == [_WO008_PHASES[wo008_phase]["marker"]]):
        add("docs/work-orders", "WO-008 issued state",
            "the closed issued WO-008 state was removed or changed",
            "WO-008 exclusively under issued/ with the installed phase marker")
    wo008_trace = (
        current == _WO008_ID or bool(wo008_text)
        or "WO-008 closed issuance record:" in pointer
        or "- WO-008 admission basis commit:" in pointer
        or wo008_phase in ("A_PREP", "A_LIVE"))
    wo008_pointer_residual = pointer
    wo008_history_findings = []
    if wo008_trace:
        # One-way: once Session A offline preparation is installed, a
        # coherent rollback to closed issuance trips exactly this lock.
        if wo008_phase == "ISSUED_CLOSED":
            add("WORKORDER.md", "WO-008 Session A preparation state",
                "the Session A offline preparation records were removed",
                "WO-008 Session A offline preparation records")
        # One-way: once the Session A live baseline is installed, a coherent
        # rollback to offline preparation trips exactly this lock.
        if wo008_phase == "A_PREP":
            add("WORKORDER.md", "WO-008 Session A live baseline state",
                "the Session A live baseline records were removed",
                "WO-008 Session A live baseline records")
        # Old NONE fields retire, not their canonical history or terminal locks.
        wo008_history_findings = _wo007_completed_findings(
            pointer, wo007_completed_text,
            (completed_dir / _WO007_NAME).relative_to(root).as_posix(),
            "pointer", audit_recorded=True, release_prepared=True,
            audit_rechecked=True, conditions_satisfied=True,
            release_published=True, following_wo008=True)
        for _f, _k, _found, _want in wo008_history_findings:
            add(_f, _k, _found, _want)
        wo008_pointer_findings, wo008_pointer_residual = _wo008_phase_findings(
            pointer, wo008_text,
            wo008_issued.relative_to(root).as_posix(), "pointer", wo008_phase)
        for _f, _k, _found, _want in wo008_pointer_findings:
            add(_f, _k, _found, _want)
        if wo008_history_findings:
            wo008_pointer_residual = pointer

    # Whichever Work Order closed last owns the pointer's base and gate,
    # and its document is the basis for the successor guard. Selecting it
    # here rather than inside the branch below is what lets the ARTIFACT
    # half of that guard keep running: a completed Work Order must never
    # grant authority to the order that follows it, whoever owns the
    # pointer. Leaving the whole guard in the NONE branch meant issuing
    # WO-004 silenced the scan of WO-003's completed document - exactly
    # the failure the WO-002 hoist below exists to prevent.
    # A completed WO-007 closed last of all, so it is selected first. It is
    # the last order of the frozen train, so it has no successor to guard;
    # its next gate is the final audit, pinned by its own records. Before
    # it, a superseded WO-006 closed last. Its document lives under
    # superseded/, so the basis directory is selected with it.
    basis_dir = completed_dir
    next_order: str | None
    final_audit_recorded = False
    release_prepared = False
    audit_rechecked = False
    conditions_satisfied = False
    release_published = False
    if wo007_completed_text:
        next_order, basis_name = None, _WO007_NAME
        basis_text = wo007_completed_text
        # Any trace of a later record selects that record's shape, so a
        # partial rollback is checked against it rather than accepted as an
        # earlier state. The prepared release carries the final audit record,
        # and the recorded recheck carries the prepared release. The
        # satisfied release conditions carry the recorded recheck, and the
        # published release carries the satisfied conditions.
        release_published = (
            current_gate == _RELEASE_PUBLISHED_GATE
            or release_gate == _PUBLISHED_RELEASE_GATE
            or any(marker in pointer for marker in _RELEASE_PUBLISHED_MARKERS)
        )
        conditions_satisfied = (
            release_published
            or current_gate == _RELEASE_CONDITIONS_GATE
            or release_gate == _SATISFIED_RELEASE_GATE
            or any(marker in pointer for marker in _RELEASE_CONDITIONS_MARKERS)
        )
        audit_rechecked = (
            conditions_satisfied
            or current_gate == _AUDIT_RECHECK_GATE
            or any(marker in pointer for marker in _AUDIT_RECHECK_MARKERS)
        )
        release_prepared = (
            audit_rechecked
            or current_gate == _RELEASE_PREP_GATE
            or any(marker in pointer for marker in _RELEASE_PREP_MARKERS)
        )
        final_audit_recorded = (
            release_prepared
            or current_gate == _FINAL_AUDIT_GATE
            or any(marker in pointer for marker in _FINAL_AUDIT_MARKERS)
        )
        if release_published:
            expected_base = _RELEASE_PUBLISHED_COMMIT
            expected_closed_gate = _RELEASE_PUBLISHED_GATE
        elif conditions_satisfied:
            expected_base = _RELEASE_CONDITIONS_COMMIT
            expected_closed_gate = _RELEASE_CONDITIONS_GATE
            # Recording the published release is one-way too: this checker
            # carries the record, so a conditions pointer without it is a
            # finding. Undoing it would have to edit this file too.
            add("WORKORDER.md", "release publication record",
                "the recorded release publication is missing from the pointer",
                "the owner-authorized tag and Release recorded")
        elif audit_rechecked:
            expected_base = _AUDIT_RECHECK_COMMIT
            expected_closed_gate = _AUDIT_RECHECK_GATE
            # Recording the satisfied release conditions is one-way too: this
            # checker carries the record, so a rechecked pointer without it is
            # a finding. Undoing it would have to edit this file too.
            add("WORKORDER.md", "release conditions record",
                "the recorded release conditions are missing from the pointer",
                "the owner-accepted release conditions recorded")
        elif release_prepared:
            expected_base = _RELEASE_PREP_COMMIT
            expected_closed_gate = _RELEASE_PREP_GATE
            # Recording the audit recheck is one-way too: this checker carries
            # the recheck record, so a prepared pointer without it is a
            # finding. Undoing it would have to edit this file too.
            add("WORKORDER.md", "audit recheck record",
                "the recorded audit recheck is missing from the pointer",
                "the final audit recheck recorded as accepted")
        elif final_audit_recorded:
            expected_base = _FINAL_AUDIT_COMMIT
            expected_closed_gate = _FINAL_AUDIT_GATE
            # Preparing the release is one-way too: this checker carries the
            # preparation record, so an audit-recorded pointer without it is a
            # finding. Undoing it would have to edit this file too.
            add("WORKORDER.md", "release preparation record",
                "the recorded release preparation is missing from the pointer",
                "the owner-authorized release preparation recorded")
        else:
            expected_base = _WO007_COMPLETION_COMMIT
            expected_closed_gate = _WO007_COMPLETED_GATE
            # Recording the final audit is one-way: this checker carries the
            # record, so a pointer without it - however coherent - is a
            # finding. Undoing the record would have to edit this file too.
            add("WORKORDER.md", "final audit record",
                "the recorded final audit is missing from the pointer",
                "the final audit recorded as ACCEPT WITH REQUIRED FIX")
    elif wo006_superseded_text:
        next_order, basis_name = "WO-007", _WO006_NAME
        basis_dir = superseded_dir
        basis_text = wo006_superseded_text
        expected_base = _WO006_CLOSURE_COMMIT
        expected_closed_gate = _WO006_SUPERSEDED_GATE
    elif wo005_completed_text:
        next_order, basis_name = "WO-006", _WO005_NAME
        basis_text = wo005_completed_text
        expected_base = _WO005_COMPLETION_COMMIT
        expected_closed_gate = _WO005_COMPLETED_GATE
    elif wo004_completed_text:
        next_order, basis_name = "WO-005", _WO004_NAME
        basis_text = wo004_completed_text
        expected_base = _WO004_COMPLETION_COMMIT
        expected_closed_gate = _WO004_COMPLETED_GATE
    elif wo003_completed_text:
        next_order, basis_name = "WO-004", _WO003_NAME
        basis_text = wo003_completed_text
        expected_base = _WO003_COMPLETION_COMMIT
        expected_closed_gate = _WO003_COMPLETED_GATE
    elif wo002_completed_text:
        next_order, basis_name = "WO-003", _WO002_NAME
        basis_text = wo002_completed_text
        expected_base = _WO002_COMPLETION_COMMIT
        expected_closed_gate = _WO002_COMPLETED_GATE
    else:
        next_order, basis_name = "WO-002", wo001_name
        basis_text = wo001_completed_text
        expected_base = _WO001_COMPLETION_COMMIT
        expected_closed_gate = _WO001_COMPLETED_GATE
    # Each release-gate text belongs to exactly one state: the published
    # text to the recorded publication, the satisfied text to the recorded
    # conditions before publication, and the closed text to every earlier
    # state. Any other pairing is a release-gate finding.
    expected_release_gate = (
        _PUBLISHED_RELEASE_GATE if release_published
        else _SATISFIED_RELEASE_GATE if conditions_satisfied
        else _CLOSED_RELEASE_GATE)
    if release_gate != expected_release_gate:
        add("WORKORDER.md", "release authorization", str(release_gate),
            expected_release_gate)
    # Scanned alone, so the finding names the file that carries the claim.
    if (next_order is not None
            and _has_next_work_order_authorization("", basis_text,
                                                   next_order)):
        add((basis_dir / basis_name).relative_to(root).as_posix(),
            "next work order authorization",
            f"implicit {next_order} permission",
            f"{next_order} authority comes only from the root pointer")

    if current == "NONE":
        if session != "NONE":
            add("WORKORDER.md", "authorization without issued work order",
                str(session), "NONE")
        if issued:
            add("docs/work-orders/issued", "unpointed issued work order",
                issued[0].name, "empty while current pointer is NONE")
        # The pointer half of the successor guard. The document half is
        # artifact-bound and runs outside this branch, so issuing a later
        # order cannot silence it.
        if (next_order is not None
                and _has_next_work_order_authorization(pointer, "",
                                                       next_order)):
            add("WORKORDER.md", "next work order authorization",
                f"implicit {next_order} permission",
                f"{next_order} remains proposed and not authorized")
        if base != f"`{expected_base}`":
            add("WORKORDER.md", "completion base commit", str(base),
                f"`{expected_base}`")
        if current_gate != expected_closed_gate:
            add("WORKORDER.md", "completed work order gate", str(current_gate),
                expected_closed_gate)
        if wo007_completed_text:
            # WO-007 closed last, so it owns the pointer's canonical slice:
            # its issuance, Session A authorization, and completion basis,
            # with the base on the completion commit, and the amendment's
            # completed form. Pointer-bound half only; the document half runs
            # outside this branch.
            for _f, _k, _found, _want in _wo007_completed_findings(
                pointer, wo007_completed_text,
                (completed_dir / _WO007_NAME).relative_to(root).as_posix(),
                "pointer", audit_recorded=final_audit_recorded,
                release_prepared=release_prepared,
                audit_rechecked=audit_rechecked,
                conditions_satisfied=conditions_satisfied,
                release_published=release_published,
            ):
                add(_f, _k, _found, _want)
        elif wo006_superseded_text:
            # WO-006 closed last, so it owns the pointer's canonical slice:
            # its issuance, Session A and Session B authorization, and closure
            # basis, with the base on the closure basis commit, and the
            # owner's release-train amendment. Pointer-bound half only; the
            # document half runs outside this branch.
            for _f, _k, _found, _want in _wo006_issuance_findings(
                pointer, wo006_superseded_text,
                (superseded_dir / _WO006_NAME).relative_to(root).as_posix(),
                "SUPERSEDED", surface="pointer",
            ):
                add(_f, _k, _found, _want)
            amendment_count = " ".join(pointer.split()).count(
                _WO006_RELEASE_TRAIN_AMENDMENT)
            if amendment_count != 1:
                add("WORKORDER.md", "WO-006 release-train amendment",
                    str(amendment_count),
                    "exactly one " + _WO006_RELEASE_TRAIN_AMENDMENT)
        elif wo005_completed_text:
            # WO-005 closed last, so it owns the pointer's canonical slice:
            # its issuance, Session A authorization, and completion basis,
            # with the base on the completion commit. Pointer-bound half
            # only; the document half runs outside this branch.
            for _f, _k, _found, _want in _wo005_issuance_findings(
                pointer, wo005_completed_text,
                (completed_dir / _WO005_NAME).relative_to(root).as_posix(),
                "COMPLETED", surface="pointer",
            ):
                add(_f, _k, _found, _want)
        elif wo004_completed_text:
            # WO-004 closed last, so it owns the pointer's canonical slice:
            # every WO-004 bullet from issuance through Session C, then the
            # completion basis, with the base on the completion commit.
            # Pointer-bound half only; the document half runs outside this
            # branch so it survives a later issuance.
            for _f, _k, _found, _want in _wo004_issuance_findings(
                pointer, wo004_completed_text,
                (completed_dir / _WO004_NAME).relative_to(root).as_posix(),
                "COMPLETED", surface="pointer",
            ):
                add(_f, _k, _found, _want)
        elif wo003_completed_text:
            # Pointer-bound half only: the canonical pointer slice with its
            # provenance bullets, and the completed base and gate. The
            # document-bound half runs outside this branch so it survives a
            # later issuance.
            for _f, _k, _found, _want in _wo003_record_findings(
                pointer, wo003_completed_text,
                (completed_dir / _WO003_NAME).relative_to(root).as_posix(),
                base, current_gate, "COMPLETED", surface="pointer",
            ):
                add(_f, _k, _found, _want)
    elif current is not None:
        if len(issued) != 1:
            add("docs/work-orders/issued", "current issued work order",
                str(len(issued)), "exactly one file matching the pointer")
        else:
            issued_id = "-".join(issued[0].stem.split("-")[:2])
            # Only a declared frozen-train order may be issued, under its own
            # canonical filename. Without this, an order outside the inventory
            # yields no successor and the next-order guard silently stops
            # running - the enforcement fails open, which is the one direction
            # a governance check must never fail.
            _declared = dict(_RELEASE_TRAIN)
            exact_wo008 = (current == _WO008_ID and issued_id == _WO008_ID
                           and issued[0].name == _WO008_NAME)
            if (_declared.get(issued_id) != issued[0].name and not exact_wo008):
                add("docs/work-orders/issued", "issued work order identity",
                    issued_id + " / " + issued[0].name,
                    "a declared frozen-train order under its canonical "
                    "filename")
            valid_pointers = {issued[0].name, issued[0].stem, issued_id}
            if current not in valid_pointers:
                add("WORKORDER.md", "current issued work order mismatch", current,
                    ", ".join(sorted(valid_pointers)))

            _statuses, auth_lines, issued_text = issued_metadata[issued[0].name]
            # Bound to the ISSUED ARTIFACT rather than to a session, and so
            # placed outside the session branches below: authorizing a session
            # must not silence the record that issued the Work Order.
            if (issued[0].name == _WO004_NAME
                    and issued_id == _WO004_ID):
                for _f, _k, _found, _want in _wo004_issuance_findings(
                    pointer, issued_text,
                    issued[0].relative_to(root).as_posix(),
                    _wo004_state_key(session, current_gate, auth_lines,
                                     issued_text),
                ):
                    add(_f, _k, _found, _want)
            if (issued[0].name == _WO005_NAME
                    and issued_id == _WO005_ID):
                for _f, _k, _found, _want in _wo005_issuance_findings(
                    pointer, issued_text,
                    issued[0].relative_to(root).as_posix(), session,
                ):
                    add(_f, _k, _found, _want)
            if (issued[0].name == _WO006_NAME
                    and issued_id == _WO006_ID):
                for _f, _k, _found, _want in _wo006_issuance_findings(
                    pointer, issued_text,
                    issued[0].relative_to(root).as_posix(), session,
                ):
                    add(_f, _k, _found, _want)
            if (issued[0].name == _WO007_NAME
                    and issued_id == _WO007_ID):
                for _f, _k, _found, _want in _wo007_issuance_findings(
                    pointer, issued_text,
                    issued[0].relative_to(root).as_posix(), session,
                ):
                    add(_f, _k, _found, _want)
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

            # Generic issued-order boundary for the rest of the frozen train.
            # WO-002 and WO-003 carry bespoke paths of their own, so they are
            # excluded here rather than checked twice. Both surfaces are
            # scanned - the root pointer and the issued document - because an
            # authorization claim is as effective in the mandate body as in
            # the pointer, and the body was previously unscanned for these
            # three classes. The existing scanners and their vocabulary are
            # reused unchanged: nothing new parses prose.
            if issued[0].name not in (_WO002_NAME, _WO003_NAME, _WO008_NAME):
                rel = issued[0].relative_to(root).as_posix()
                normalized_issued = " ".join(issued_text.split())
                # Attribution: each surface is scanned alone first, so a claim
                # is reported against the file that actually carries it.
                # Reporting a mandate's claim against WORKORDER.md sends the
                # reader to a file with nothing wrong in it.
                if _has_release_authorization(pointer):
                    add("WORKORDER.md", "release authorization",
                        "positive release permission", _CLOSED_RELEASE_GATE)
                elif _has_release_authorization(pointer, issued_text):
                    add(rel, "release authorization",
                        "positive release permission", _CLOSED_RELEASE_GATE)
                # A completed WO-003 leaves three statements in the pointer
                # that legitimately describe an applied description. They are
                # pinned byte-exact and singular elsewhere, so they are
                # removed once here - the same allowed-context mechanism the
                # WO-003 gates use - rather than being read as fresh
                # permission for a later order.
                allowed_history: tuple[str, ...] = ()
                if wo003_completed_text:
                    allowed_history = (
                        _WO003_PRE_APPLICATION_POINTER_STATEMENT,
                        _WO003_COMPLETED_APPLIED_POINTER_STATEMENT,
                        _WO003_COMPLETION_POINTER_STATEMENT,
                    )
                # WO-007's accepted mandate forbids these very actions in
                # prose, and this scanner has no negation handling, so that
                # one sentence is removed before scanning. The exemption is
                # bound to WO-007's validated identity AND to the sentence
                # occurring exactly once in WO-007's own mandate - not to the
                # text appearing anywhere in arbitrary input, which would be
                # the same decoy weakness in a new place. A missing or
                # duplicated decision lock is its own finding and grants no
                # exemption, so the exact-occurrence guard stays meaningful.
                # The lock is removed from the BODY surface, not offered as a
                # pointer context: it lives in WO-007's mandate and never in
                # WORKORDER.md, so passing it as an allowed context would fail
                # the pointer's exact-once guard on a perfectly valid WO-007
                # issuance.
                scannable_body = normalized_issued
                if issued[0].name == _WO007_NAME and issued_id == _WO007_ID:
                    locks = normalized_issued.count(_WO007_DRAFTING_PROHIBITION)
                    if locks != 1:
                        add(rel, "WO-007 decision lock", str(locks),
                            "exactly one " + _WO007_DRAFTING_PROHIBITION)
                    else:
                        scannable_body = normalized_issued.replace(
                            _WO007_DRAFTING_PROHIBITION, "", 1)
                _external_want = (
                    "repository metadata, branch-protection, and social "
                    "publication remain unauthorized"
                )
                if _has_session_b_external_action_authorization(
                    pointer, allowed_history
                ):
                    add("WORKORDER.md", "external-action boundary",
                        "positive permission for a further external action",
                        _external_want)
                elif _has_session_b_external_action_authorization(
                    pointer, allowed_history, scannable_body
                ):
                    add(rel, "external-action boundary",
                        "positive permission for a further external action",
                        _external_want)
                successor = _next_release_train_order(issued_id)
                if successor is not None:
                    _next_want = (
                        f"{successor} remains proposed and not authorized"
                    )
                    if _has_next_work_order_authorization(
                        pointer, "", successor
                    ):
                        add("WORKORDER.md", "next work order authorization",
                            f"implicit {successor} permission", _next_want)
                    elif _has_next_work_order_authorization(
                        pointer, issued_text, successor
                    ):
                        add(rel, "next work order authorization",
                            f"implicit {successor} permission", _next_want)

            if exact_wo008:
                rel = issued[0].relative_to(root).as_posix()
                spec = _WO008_PHASES[wo008_phase]
                phase_findings, body_residual = _wo008_phase_findings(
                    pointer, issued_text, rel, "document", wo008_phase)
                for _f, _k, _found, _want in phase_findings:
                    add(_f, _k, _found, _want)
                if phase_findings:
                    add(rel, "planning-only proposal placement",
                        "issuance record missing or malformed",
                        "canonical issued WO-008 with validated closed records")
                # In A_PREP and A_LIVE the other-session scan exempts only Session A;
                # any Session A grant beyond the records is widening below.
                for where, residual in (
                    ("WORKORDER.md", wo008_pointer_residual),
                    (rel, body_residual),
                ):
                    if _has_residual_session_authorization(
                        " ".join(residual.lower().split())
                    ):
                        add(where, "implicit session authorization",
                            "positive activation outside accepted records", spec["gate"])
                    if _has_other_session_authorization(residual, "", spec["session"]):
                        add(where, "later session authorization",
                            "positive labeled session permission", "no session authorized")
                    if _current_session_widening(residual, "A", ()):
                        add(where, "session scope widening",
                            "positive Session A permission", "no session authorized")
                # Release/external scans always see the original surfaces.
                if _has_release_authorization(pointer):
                    add("WORKORDER.md", "release authorization", "positive permission",
                        _PUBLISHED_RELEASE_GATE)
                elif _has_release_authorization(pointer, issued_text):
                    add(rel, "release authorization", "positive permission",
                        _PUBLISHED_RELEASE_GATE)
                allowed_history = (
                    _WO003_PRE_APPLICATION_POINTER_STATEMENT,
                    _WO003_COMPLETED_APPLIED_POINTER_STATEMENT,
                    _WO003_COMPLETION_POINTER_STATEMENT)
                if _has_session_b_external_action_authorization(pointer, allowed_history):
                    add("WORKORDER.md", "external-action boundary", "positive permission",
                        "metadata and social publication remain unauthorized")
                if _has_session_b_external_action_authorization("", (), issued_text):
                    add(rel, "external-action boundary", "positive permission",
                        "metadata and social publication remain unauthorized")
            elif session == "NONE":
                wo002_session_a_accepted = issued[0].name == _WO002_NAME and (
                    current_gate == _WO002_SESSION_A_ACCEPTED_GATE
                    or auth_lines == [_ISSUED_SESSION_A_ACCEPTED]
                    or "## Session A acceptance record" in issued_text
                )
                wo003_session_a_accepted = issued[0].name == _WO003_NAME and (
                    current_gate == _WO003_SESSION_A_ACCEPTED_GATE
                    or auth_lines == [_ISSUED_SESSION_A_ACCEPTED]
                    or _WO003_ACCEPTANCE_HEADING in issued_text
                )
                settled = _wo003_settled_gate(
                    issued[0].name, current_gate, auth_lines, issued_text)
                wo004_session_a_accepted = (
                    issued[0].name == _WO004_NAME
                    and issued_id == _WO004_ID
                    and _wo004_state_key(session, current_gate, auth_lines,
                                         issued_text) == "A_ACCEPTED"
                )
                if wo002_session_a_accepted:
                    rel = issued[0].relative_to(root).as_posix()
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
                elif settled is not None:
                    for _f, _k, _found, _want in _wo003_settled_findings(
                        settled, pointer, issued_text,
                        issued[0].relative_to(root).as_posix(),
                        base, current_gate, auth_lines,
                    ):
                        add(_f, _k, _found, _want)
                elif wo003_session_a_accepted:
                    rel = issued[0].relative_to(root).as_posix()
                    normalized_issued = " ".join(issued_text.split())
                    if auth_lines != [_ISSUED_SESSION_A_ACCEPTED]:
                        add(rel, "WO-003 Session A accepted authorization",
                            repr(auth_lines),
                            f"exactly {_ISSUED_SESSION_A_ACCEPTED}")
                    for _f, _k, _found, _want in _wo003_record_findings(
                        pointer, issued_text, rel, base, current_gate,
                        "ACCEPTED",
                    ):
                        add(_f, _k, _found, _want)
                    for _k, _found, _want in _wo003_acceptance_record_findings(
                        issued_text
                    ):
                        add(rel, _k, _found, _want)
                    if _WO003_SESSION_A_ACCEPTED_NEXT_GATE not in normalized_issued:
                        add(rel, "WO-003 next gate", "missing or changed",
                            _WO003_SESSION_A_ACCEPTED_NEXT_GATE)
                    if _WO003_SESSION_A_ACCEPTED_STATEMENT not in normalized_issued:
                        add(rel, "WO-003 Session A accepted statement", "missing",
                            _WO003_SESSION_A_ACCEPTED_STATEMENT)
                    # The root pointer is the sole current authority surface.
                    # Scan it for any reopened labeled session; the issued
                    # document's accepted metadata and bounded record are
                    # enforced structurally above, without treating the
                    # preserved technical mandate as live authorization prose.
                    if _has_other_session_authorization(pointer, "", ""):
                        add("WORKORDER.md", "session authorization reopening",
                            "positive permission for Session A, Session B, or later",
                            "Session A accepted; no session authorized")
                elif wo004_session_a_accepted:
                    # The canonical slices, the base commit, the next gate,
                    # and the accepted statement are enforced by
                    # _wo004_issuance_findings above. This branch adds the
                    # marker, the gate, the decision record, and the closed
                    # sessions.
                    rel = issued[0].relative_to(root).as_posix()
                    if auth_lines != [_ISSUED_SESSION_A_ACCEPTED]:
                        add(rel, "WO-004 Session A accepted authorization",
                            repr(auth_lines),
                            f"exactly {_ISSUED_SESSION_A_ACCEPTED}")
                    if base != f"`{_WO004_SESSION_A_ACCEPTED_COMMIT}`":
                        add("WORKORDER.md",
                            "WO-004 Session A accepted base commit", str(base),
                            f"`{_WO004_SESSION_A_ACCEPTED_COMMIT}`")
                    if current_gate != _WO004_SESSION_A_ACCEPTED_GATE:
                        add("WORKORDER.md", "WO-004 Session A accepted gate",
                            str(current_gate), _WO004_SESSION_A_ACCEPTED_GATE)
                    for _f, _k, _found, _want in (
                        _wo004_decision_record_findings(issued_text, rel)
                    ):
                        add(_f, _k, _found, _want)
                    # This branch does not scan the pointer for a reopened
                    # labeled session. The completed-WO-003 boundary at the end
                    # of this function does, and it runs whenever a non-empty
                    # WO-003 document was read from completed/
                    # (`if wo003_completed_text:`), whatever that document's own
                    # markers say. Deleting it, moving it out, or emptying it
                    # skips that scan and raises the "completed WO-003 state"
                    # finding instead; changing its status or authorization
                    # marker raises that finding with the scan still running.
                    # The mandate is not scanned there. It keeps Session A's
                    # historical authorization basis verbatim, so it is
                    # scanned here with Session A exempt: a positive Session B,
                    # Session C, or later statement in it is a finding.
                    if _has_other_session_authorization("", issued_text, "A"):
                        add(rel, "session authorization reopening",
                            "positive permission for Session B or later",
                            "Session B and Session C remain unauthorized")
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
                    if (issued[0].name == _WO004_NAME
                            and issued_id == _WO004_ID
                            and base != f"`{_WO004_ISSUANCE_COMMIT}`"):
                        add("WORKORDER.md", "WO-004 issuance base commit",
                            str(base), f"`{_WO004_ISSUANCE_COMMIT}`")
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
                # WO-004's Session A is read-only feasibility planning, not
                # implementation, so it carries its own gate and marker
                # rather than the generic implementation pair. WO-005's is
                # limited to the offline coverage model, and carries its own
                # pair for the same reason.
                wo004_session_a = issued[0].name == _WO004_NAME
                wo005_session_a = (issued[0].name == _WO005_NAME
                                   and issued_id == _WO005_ID)
                # WO-006's is limited to the offline design and harness.
                wo006_session_a = (issued[0].name == _WO006_NAME
                                   and issued_id == _WO006_ID)
                # WO-007's is limited to the explainer and private drafts.
                wo007_session_a = (issued[0].name == _WO007_NAME
                                   and issued_id == _WO007_ID)
                if wo004_session_a:
                    expected_gate = _WO004_SESSION_A_GATE
                    expected_session_a_auth = _WO004_SESSION_A_AUTH
                elif wo005_session_a:
                    expected_gate = _WO005_SESSION_A_GATE
                    expected_session_a_auth = _WO005_SESSION_A_AUTH
                elif wo006_session_a:
                    expected_gate = _WO006_SESSION_A_GATE
                    expected_session_a_auth = _WO006_SESSION_A_AUTH
                elif wo007_session_a:
                    expected_gate = _WO007_SESSION_A_GATE
                    expected_session_a_auth = _WO007_SESSION_A_AUTH
                else:
                    expected_gate = (
                        f"{issued_id} SESSION A AUTHORIZED — IMPLEMENT "
                        "SESSION A ONLY"
                    )
                    expected_session_a_auth = _ISSUED_SESSION_A_AUTH
                if auth_lines != [expected_session_a_auth]:
                    add(issued[0].relative_to(root).as_posix(),
                        "issued session authorization", repr(auth_lines),
                        f"exactly {expected_session_a_auth}")
                if current_gate != expected_gate:
                    add("WORKORDER.md", "authorized session gate", str(current_gate),
                        expected_gate)
                if _has_other_session_authorization(pointer, issued_text, session):
                    add("WORKORDER.md", "later session authorization",
                        "positive permission for a non-current session",
                        "only Session A authorized")
                if wo005_session_a:
                    # The canonical slices and the base commit are enforced by
                    # _wo005_issuance_findings; this adds the Session A record
                    # and its accepted exemption terms, in the mandate and in
                    # the pointer statement.
                    for _f, _k, _found, _want in (
                        _wo005_session_a_record_findings(
                            pointer, issued_text,
                            issued[0].relative_to(root).as_posix())
                    ):
                        add(_f, _k, _found, _want)
                if wo006_session_a:
                    # Likewise for WO-006: the canonical slices and base come
                    # from _wo006_issuance_findings; this adds the closed
                    # Session A record, the next gate, and the pointer
                    # statement.
                    for _f, _k, _found, _want in (
                        _wo006_session_record_findings(
                            pointer, issued_text,
                            issued[0].relative_to(root).as_posix())
                    ):
                        add(_f, _k, _found, _want)
                    # P2-A: no prose outside those pinned records may widen
                    # Session A. Each surface is scanned alone, so a finding
                    # names the file that carries the grant.
                    for _file, _text in (
                        ("WORKORDER.md", pointer),
                        (issued[0].relative_to(root).as_posix(), issued_text),
                    ):
                        for _statement in _current_session_widening(
                            _text, "A", _WO006_SESSION_A_CANONICAL
                        ):
                            add(_file, "current session widening",
                                _statement[:200],
                                "no grant to Session A beyond its pinned "
                                "records")
                if wo007_session_a:
                    # Likewise for WO-007: the canonical slices, base, next
                    # gate, and amendment come from _wo007_issuance_findings;
                    # this adds the closed Session A and exemption records and
                    # the pointer statement, then WO-006's widening scan with
                    # WO-007's pinned records.
                    for _f, _k, _found, _want in (
                        _wo007_session_a_record_findings(
                            pointer, issued_text,
                            issued[0].relative_to(root).as_posix())
                    ):
                        add(_f, _k, _found, _want)
                    for _file, _text in (
                        ("WORKORDER.md", pointer),
                        (issued[0].relative_to(root).as_posix(), issued_text),
                    ):
                        for _statement in _current_session_widening(
                            _text, "A", _WO007_SESSION_A_CANONICAL
                        ):
                            add(_file, "current session widening",
                                _statement[:200],
                                "no grant to Session A beyond its pinned "
                                "records")
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
                wo003_session_b = issued[0].name == _WO003_NAME
                wo004_session_b = (issued[0].name == _WO004_NAME
                                   and issued_id == _WO004_ID)
                # WO-006's is owner-operated live measurement only.
                wo006_session_b = (issued[0].name == _WO006_NAME
                                   and issued_id == _WO006_ID)
                if wo003_session_b:
                    expected_gate = _WO003_SESSION_B_GATE
                    expected_auth = _ISSUED_SESSION_B_DRAFT_AUTH
                elif wo004_session_b:
                    expected_gate = _WO004_SESSION_B_GATE
                    expected_auth = _WO004_SESSION_B_AUTH
                elif wo006_session_b:
                    expected_gate = _WO006_SESSION_B_GATE
                    expected_auth = _WO006_SESSION_B_AUTH
                else:
                    expected_gate = (
                        f"{issued_id} SESSION B AUTHORIZED "
                        f"{chr(8212)} EXECUTE EXTERNAL PROOF ONLY"
                    )
                    expected_auth = _ISSUED_SESSION_B_AUTH
                if auth_lines != [expected_auth]:
                    add(issued[0].relative_to(root).as_posix(),
                        "issued session authorization", repr(auth_lines),
                        f"exactly {expected_auth}")
                if current_gate != expected_gate:
                    add("WORKORDER.md", "authorized session gate",
                        str(current_gate), expected_gate)
                # The root pointer is the sole live authority surface. The
                # detailed mandate intentionally records older session states.
                if _has_other_session_authorization(pointer, "", session):
                    add("WORKORDER.md", "later session authorization",
                        "positive permission for a non-current session",
                        "only Session B authorized")
                if wo004_session_b:
                    # The canonical slices, the base commit, the next gate,
                    # and the Session B statement are enforced by
                    # _wo004_issuance_findings. Session A's record stays in
                    # place beside them: its authorization statement, its
                    # acceptance statement, and the decision record, each
                    # exactly once.
                    wo004_rel = issued[0].relative_to(root).as_posix()
                    normalized_wo004 = " ".join(issued_text.split())
                    for required, kind in (
                        (_WO004_SESSION_A_ANCHORED,
                         "WO-004 Session A authorization statement"),
                        (_WO004_SESSION_A_ACCEPTANCE_RECORD,
                         "WO-004 Session A acceptance statement"),
                    ):
                        if normalized_wo004.count(required) != 1:
                            add(wo004_rel, kind,
                                str(normalized_wo004.count(required)),
                                "exactly one " + required)
                    for _f, _k, _found, _want in (
                        _wo004_decision_record_findings(issued_text,
                                                        wo004_rel)
                    ):
                        add(_f, _k, _found, _want)
                    # The mandate keeps Session A's authorization statement
                    # verbatim as history. Its heading-anchored form is pinned
                    # above, and that same form is removed once before the
                    # existing scanner looks for a positive statement about
                    # any session other than B.
                    if _has_other_session_authorization(
                        "",
                        normalized_wo004.replace(
                            _WO004_SESSION_A_ANCHORED, "", 1),
                        session,
                    ):
                        add(wo004_rel, "session authorization reopening",
                            "positive permission for Session A, Session C, "
                            "or later",
                            "only Session B authorized")
                if wo006_session_b:
                    # The canonical slices and base come from
                    # _wo006_issuance_findings; this adds the closed records,
                    # the next gate, and the pointer statements.
                    wo006_rel = issued[0].relative_to(root).as_posix()
                    for _f, _k, _found, _want in (
                        _wo006_session_record_findings(
                            pointer, issued_text, wo006_rel, "B")
                    ):
                        add(_f, _k, _found, _want)
                    # The mandate keeps Session A's authorization basis
                    # verbatim. Its closed section is pinned above, and that
                    # same text is removed once before the existing scanner
                    # looks for a positive statement about any session other
                    # than B.
                    if _has_other_session_authorization(
                        "",
                        " ".join(issued_text.split()).replace(
                            _WO006_SESSION_A_BASIS_RECORD, "", 1),
                        session,
                    ):
                        add(wo006_rel, "session authorization reopening",
                            "positive permission for Session A, Session C, "
                            "or later",
                            "only Session B authorized")
                    # The mandate's configuration sentence is required exactly
                    # once, and that one occurrence alone is exempt below.
                    normalized_wo006 = " ".join(issued_text.split())
                    if normalized_wo006.count(
                        _WO006_SESSION_B_CONFIG_SENTENCE
                    ) != 1:
                        add(wo006_rel, "WO-006 Session B configuration sentence",
                            str(normalized_wo006.count(
                                _WO006_SESSION_B_CONFIG_SENTENCE)),
                            "exactly one " + _WO006_SESSION_B_CONFIG_SENTENCE)
                    # P2-A for Session B: the Session A guard, reused with
                    # Session B's pinned records. Each surface is scanned
                    # alone, so a finding names the file that carries it.
                    for _file, _text in (
                        ("WORKORDER.md", pointer),
                        (wo006_rel, normalized_wo006.replace(
                            _WO006_SESSION_B_CONFIG_SENTENCE, " ", 1)),
                    ):
                        for _statement in _current_session_widening(
                            _text, "B", _WO006_SESSION_B_CANONICAL
                        ):
                            add(_file, "current session widening",
                                _statement[:200],
                                "no grant to Session B beyond its pinned "
                                "records")
                if wo003_session_b:
                    wo003_rel = issued[0].relative_to(root).as_posix()
                    for _f, _k, _found, _want in _wo003_record_findings(
                        pointer, issued_text, wo003_rel, base, current_gate,
                        session,
                    ):
                        add(_f, _k, _found, _want)
                    for _k, _found, _want in _wo003_acceptance_record_findings(
                        issued_text, _WO003_SESSION_B_HEADING
                    ):
                        add(wo003_rel, _k, _found, _want)
                    for _k, _found, _want in _wo003_session_b_record_findings(
                        issued_text
                    ):
                        add(wo003_rel, _k, _found, _want)
                    normalized_wo003 = " ".join(issued_text.split())
                    for required, kind in (
                        (_WO003_SESSION_B_NEXT_GATE, "WO-003 next gate"),
                        (_WO003_SESSION_B_STATEMENT,
                         "WO-003 Session B drafting-only statement"),
                    ):
                        if normalized_wo003.count(required) != 1:
                            add(wo003_rel, kind,
                                str(normalized_wo003.count(required)),
                                "exactly one " + required)
                    normalized_pointer = " ".join(pointer.split())
                    if normalized_pointer.count(
                        _WO003_SESSION_B_POINTER_STATEMENT
                    ) != 1:
                        add("WORKORDER.md", "WO-003 Session B pointer statement",
                            str(normalized_pointer.count(
                                _WO003_SESSION_B_POINTER_STATEMENT
                            )),
                            "exactly one drafting-only authority statement")
                    if _has_session_b_external_action_authorization(
                        pointer,
                        (_WO003_SESSION_B_GATE,
                         _WO003_SESSION_B_POINTER_STATEMENT),
                    ):
                        add("WORKORDER.md",
                            "WO-003 Session B external-action boundary",
                            "metadata application or social publication opened",
                            "drafting only; no metadata or publication action")
                    if _has_next_work_order_authorization(
                        pointer, "", "WO-004"
                    ):
                        add("WORKORDER.md", "next work order authorization",
                            "implicit WO-004 permission",
                            "WO-004 remains proposed and not authorized")
                elif issued[0].name == _WO002_NAME:
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
            elif (session == "C" and issued[0].name == _WO004_NAME
                  and issued_id == _WO004_ID):
                # WO-004's Session C is owner-operated live acceptance of the
                # reviewed, uncommitted Session B implementation. The
                # canonical slices, the base commit, the next gate, and the
                # Session C statement are enforced by _wo004_issuance_findings.
                wo004_rel = issued[0].relative_to(root).as_posix()
                if auth_lines != [_WO004_SESSION_C_AUTH]:
                    add(wo004_rel, "issued session authorization",
                        repr(auth_lines), f"exactly {_WO004_SESSION_C_AUTH}")
                if current_gate != _WO004_SESSION_C_GATE:
                    add("WORKORDER.md", "authorized session gate",
                        str(current_gate), _WO004_SESSION_C_GATE)
                if _has_other_session_authorization(pointer, "", session):
                    add("WORKORDER.md", "later session authorization",
                        "positive permission for a non-current session",
                        "only Session C authorized")
                # The records that came before stay in place, each exactly
                # once: Session A's authorization and acceptance statements,
                # the decision record, Session B's authorization statement,
                # and the issued recovery sentence. The reviewed
                # implementation's identity list is checked in place.
                normalized_wo004 = " ".join(issued_text.split())
                pinned = (
                    (_WO004_SESSION_A_ANCHORED,
                     "WO-004 Session A authorization statement"),
                    (_WO004_SESSION_A_ACCEPTANCE_RECORD,
                     "WO-004 Session A acceptance statement"),
                    (_WO004_SESSION_B_ANCHORED,
                     "WO-004 Session B authorization statement"),
                    (_WO004_ISSUED_RECOVERY_STATEMENT,
                     "WO-004 issued recovery statement"),
                )
                for required, kind in pinned:
                    if normalized_wo004.count(required) != 1:
                        add(wo004_rel, kind,
                            str(normalized_wo004.count(required)),
                            "exactly one " + required)
                for _f, _k, _found, _want in (
                    _wo004_decision_record_findings(issued_text, wo004_rel)
                    + _wo004_implementation_identity_findings(issued_text,
                                                              wo004_rel)
                ):
                    add(_f, _k, _found, _want)
                # Session A's and Session B's authorization statements and the
                # issued recovery sentence are kept verbatim. Their anchored
                # forms are pinned above, and those same forms are removed once
                # each before the existing scanner looks for a positive
                # statement about any session other than C.
                scannable = normalized_wo004
                for kept in (_WO004_SESSION_A_ANCHORED,
                             _WO004_SESSION_B_ANCHORED,
                             _WO004_ISSUED_RECOVERY_STATEMENT):
                    scannable = scannable.replace(kept, "", 1)
                if _has_other_session_authorization("", scannable, session):
                    add(wo004_rel, "session authorization reopening",
                        "positive permission for Session A, Session B, or "
                        "later",
                        "only Session C authorized")
            else:
                add("WORKORDER.md", "authorized session gate", str(session),
                    "NONE or the specifically authorized session A or B, or "
                    "WO-004's Session C")

    # WO-002's completed-document enforcement is bound to the artifact too.
    # It used to live in the NONE branch, where a later Work Order taking the
    # root pointer over would have silently stopped it - the same incomplete
    # hoist WO-003's completed checks were split to avoid. The pointer-bound
    # halves it reads (the acceptance paragraph and the accepted identifiers)
    # are anchored by WO-001's completion reference, which no issuance moves.
    if wo002_completed_text:
        wo002_rel = (completed_dir / _WO002_NAME).relative_to(root).as_posix()
        for evidence, kind in (
            (_WO002_COMPLETION_COMMIT, "WO-002 completion commit"),
            (_WO002_COMPLETION_WORKFLOW, "WO-002 completion workflow"),
            (_WO002_COMPLETION_JOB, "WO-002 completion job"),
            (_WO002_EVIDENCE_PATH, "WO-002 evidence artifact"),
            (_WO002_EVIDENCE_SHA256, "WO-002 evidence digest"),
        ):
            if evidence not in wo002_completed_text:
                add(wo002_rel, kind, "missing", evidence)
        normalized_wo002 = " ".join(wo002_completed_text.split())
        for wording, kind in (
            (_WO002_TERMINAL_EXTERNAL, "WO-002 terminal external result"),
            (_WO002_NEGATIVE_RESULT, "WO-002 accepted negative result"),
        ):
            if wording not in normalized_wo002:
                add(wo002_rel, kind, "missing or changed", wording)
        # Session A's accepted record outlives the Work Order that carried it.
        for _f, _k, _found, _want in _accepted_record_findings(
            pointer, wo002_completed_text, wo002_rel
        ):
            add(_f, _k, _found, _want)

    # WO-003's completed-document enforcement is bound to the artifact, not to
    # the root pointer, so it keeps running once a later Work Order takes the
    # pointer over. Only the pointer's completed-state base and gate are
    # pointer-bound, and those stay in the NONE branch above.
    if wo003_completed_text:
        rel = (completed_dir / _WO003_NAME).relative_to(root).as_posix()
        # Document-bound half: the planning baseline and the canonical issued
        # slice live in the completed document, so they are checked whichever
        # Work Order currently owns the root pointer.
        for _f, _k, _found, _want in _wo003_record_findings(
            pointer, wo003_completed_text, rel, base, current_gate,
            "COMPLETED", surface="document",
        ):
            add(_f, _k, _found, _want)
        for record in (
            _wo003_acceptance_record_findings(
                wo003_completed_text, _WO003_SESSION_B_HEADING),
            _wo003_session_b_record_findings(
                wo003_completed_text, _WO003_SESSION_B_ACCEPTANCE_HEADING),
            _wo003_session_b_acceptance_findings(
                wo003_completed_text, _WO003_APPLICATION_HEADING),
            _wo003_application_record_findings(wo003_completed_text),
            _wo003_completion_record_findings(wo003_completed_text),
        ):
            for kind, found, want in record:
                add(rel, kind, found, want)
        normalized_wo003 = " ".join(wo003_completed_text.split())
        for wording, kind in (
            (_WO003_COMPLETED_STATEMENT, "WO-003 completion statement"),
            (_WO003_COMPLETED_NEXT_GATE, "WO-003 next gate"),
        ):
            if normalized_wo003.count(wording) != 1:
                add(rel, kind, str(normalized_wo003.count(wording)),
                    "exactly one " + wording)
        normalized_pointer = " ".join(pointer.split())
        wo003_pointer_statements = (
            (_WO003_PRE_APPLICATION_POINTER_STATEMENT,
             "WO-003 pre-application pointer statement"),
            (_WO003_COMPLETED_APPLIED_POINTER_STATEMENT,
             "WO-003 applied pointer statement"),
            (_WO003_COMPLETION_POINTER_STATEMENT,
             "WO-003 completion pointer statement"),
        )
        for required, kind in wo003_pointer_statements:
            if normalized_pointer.count(required) != 1:
                add("WORKORDER.md", kind,
                    str(normalized_pointer.count(required)),
                    "exactly one " + required)
        # Completing WO-003 is not reaching the next gate. These are the
        # statements this gate is allowed to make; the completed gate line is
        # one of them only while WO-003 still owns the pointer.
        allowed = tuple(
            statement for statement, _kind in wo003_pointer_statements)
        if current == "NONE" and not wo004_completed_text:
            allowed = (_WO003_COMPLETED_GATE,) + allowed
        if _has_session_b_external_action_authorization(pointer, allowed):
            add("WORKORDER.md", "WO-003 external-action boundary",
                "positive permission for a further external action",
                "WO-003 is completed; repository metadata, branch-protection, "
                "and social publication remain unauthorized")
        if _has_other_session_authorization(
            wo008_pointer_residual if current == _WO008_ID else pointer,
            "", session or ""
        ):
            add("WORKORDER.md", "session authorization reopening",
                "positive permission for a session other than the authorized "
                "one",
                "WO-003 is completed; only the authorized session may act")

    # WO-004's completed-document enforcement is bound to the artifact in the
    # same way, so it keeps running once a later Work Order takes the pointer
    # over. Completion retires no earlier pin: the canonical slice from
    # issuance through Session C plus the completion basis, the next gate, the
    # completion statement, every kept authorization and acceptance record,
    # the decision record, and the reviewed implementation identities are all
    # checked here.
    if wo004_completed_text:
        wo004_rel = (completed_dir / _WO004_NAME).relative_to(root).as_posix()
        for _f, _k, _found, _want in _wo004_issuance_findings(
            pointer, wo004_completed_text, wo004_rel, "COMPLETED",
            surface="document",
        ):
            add(_f, _k, _found, _want)
        normalized_wo004 = " ".join(wo004_completed_text.split())
        wo004_kept = (
            (_WO004_SESSION_A_ANCHORED,
             "WO-004 Session A authorization statement"),
            (_WO004_SESSION_A_ACCEPTANCE_RECORD,
             "WO-004 Session A acceptance statement"),
            (_WO004_SESSION_B_ANCHORED,
             "WO-004 Session B authorization statement"),
            (_WO004_SESSION_C_ANCHORED,
             "WO-004 Session C authorization statement"),
            (_WO004_ISSUED_RECOVERY_STATEMENT,
             "WO-004 issued recovery statement"),
        )
        for required, kind in wo004_kept:
            if normalized_wo004.count(required) != 1:
                add(wo004_rel, kind, str(normalized_wo004.count(required)),
                    "exactly one " + required)
        for _f, _k, _found, _want in (
            _wo004_decision_record_findings(wo004_completed_text, wo004_rel)
            + _wo004_implementation_identity_findings(wo004_completed_text,
                                                      wo004_rel)
        ):
            add(_f, _k, _found, _want)
        # The kept statements name sessions beside words the scanner reads
        # as grants, so their pinned anchored forms are removed once each
        # before it looks for a positive statement about ANY session: none is
        # authorized once WO-004 is completed.
        scannable = normalized_wo004
        for statement, _kind in wo004_kept:
            scannable = scannable.replace(statement, "", 1)
        if _has_other_session_authorization("", scannable, ""):
            add(wo004_rel, "session authorization reopening",
                "positive permission for a WO-004 session",
                "WO-004 is completed and no session is authorized")
        # The issued-order path scanned this body for release and external-
        # action claims while WO-004 was issued; completion must not retire
        # those scans. Same scanners, allowed history, and attribution rule
        # as that path: the body is scanned only when the pointer alone is
        # clean, so a pointer claim is never reported against the mandate.
        if (not _has_release_authorization(pointer)
                and _has_release_authorization(pointer,
                                               wo004_completed_text)):
            add(wo004_rel, "release authorization",
                "positive release permission", _CLOSED_RELEASE_GATE)
        wo004_allowed_history: tuple[str, ...] = ()
        if wo003_completed_text:
            wo004_allowed_history = (
                _WO003_PRE_APPLICATION_POINTER_STATEMENT,
                _WO003_COMPLETED_APPLIED_POINTER_STATEMENT,
                _WO003_COMPLETION_POINTER_STATEMENT,
            )
        if (not _has_session_b_external_action_authorization(
                pointer, wo004_allowed_history)
                and _has_session_b_external_action_authorization(
                    pointer, wo004_allowed_history, normalized_wo004)):
            add(wo004_rel, "external-action boundary",
                "positive permission for a further external action",
                "repository metadata, branch-protection, and social "
                "publication remain unauthorized")
        normalized_pointer = " ".join(pointer.split())
        if normalized_pointer.count(_WO004_COMPLETED_POINTER_CLAUSE) != 1:
            add("WORKORDER.md", "WO-004 completion pointer statement",
                str(normalized_pointer.count(_WO004_COMPLETED_POINTER_CLAUSE)),
                "exactly one " + _WO004_COMPLETED_POINTER_CLAUSE)

    # WO-005's completed document is bound to the artifact the same way:
    # the canonical slice with its completion basis, the Session A record and
    # accepted exemption terms, the completion statement, and the release,
    # external-action, and session boundaries keep running whoever owns the
    # pointer.
    if wo005_completed_text:
        wo005_rel = (completed_dir / _WO005_NAME).relative_to(root).as_posix()
        for _f, _k, _found, _want in (
            _wo005_issuance_findings(pointer, wo005_completed_text, wo005_rel,
                                     "COMPLETED", surface="document")
            + _wo005_session_a_record_findings(pointer, wo005_completed_text,
                                               wo005_rel, completed=True)
        ):
            add(_f, _k, _found, _want)
        normalized_wo005 = " ".join(wo005_completed_text.split())
        if normalized_wo005.count(_WO005_COMPLETED_STATEMENT) != 1:
            add(wo005_rel, "WO-005 completion statement",
                str(normalized_wo005.count(_WO005_COMPLETED_STATEMENT)),
                "exactly one " + _WO005_COMPLETED_STATEMENT)
        # The kept records name Session A beside words the scanner reads as
        # grants, so their pinned forms are removed once each before it looks
        # for a positive statement about ANY session.
        scannable = normalized_wo005
        for kept in (_WO005_COMPLETED_BASIS_RECORD, _WO005_EXEMPTION_RECORD):
            scannable = scannable.replace(kept, "", 1)
        if _has_other_session_authorization("", scannable, ""):
            add(wo005_rel, "session authorization reopening",
                "positive permission for a WO-005 session",
                "WO-005 is completed and no session is authorized")
        # Same scanners and attribution rule as the completed WO-004 block.
        if (not _has_release_authorization(pointer)
                and _has_release_authorization(pointer,
                                               wo005_completed_text)):
            add(wo005_rel, "release authorization",
                "positive release permission", _CLOSED_RELEASE_GATE)
        wo005_allowed_history: tuple[str, ...] = ()
        if wo003_completed_text:
            wo005_allowed_history = (
                _WO003_PRE_APPLICATION_POINTER_STATEMENT,
                _WO003_COMPLETED_APPLIED_POINTER_STATEMENT,
                _WO003_COMPLETION_POINTER_STATEMENT,
            )
        if (not _has_session_b_external_action_authorization(
                pointer, wo005_allowed_history)
                and _has_session_b_external_action_authorization(
                    pointer, wo005_allowed_history, normalized_wo005)):
            add(wo005_rel, "external-action boundary",
                "positive permission for a further external action",
                "repository metadata, branch-protection, and social "
                "publication remain unauthorized")
        wo005_pointer = " ".join(pointer.split())
        if wo005_pointer.count(_WO005_COMPLETED_POINTER_CLAUSE) != 1:
            add("WORKORDER.md", "WO-005 completion pointer statement",
                str(wo005_pointer.count(_WO005_COMPLETED_POINTER_CLAUSE)),
                "exactly one " + _WO005_COMPLETED_POINTER_CLAUSE)

    # WO-006's superseded document is bound to the artifact the same way: the
    # canonical slice with its closure basis, the kept authorization and
    # acceptance records, the closure record, the terminal next gate, the
    # pointer's history, link, and closure clause, and the session, release,
    # and external-action boundaries keep running whoever owns the pointer.
    if wo006_superseded_text:
        wo006_rel = (superseded_dir / _WO006_NAME).relative_to(root).as_posix()
        for _f, _k, _found, _want in (
            _wo006_issuance_findings(pointer, wo006_superseded_text, wo006_rel,
                                     "SUPERSEDED", surface="document")
            + _wo006_superseded_record_findings(wo006_superseded_text,
                                                wo006_rel)
        ):
            add(_f, _k, _found, _want)
        wo006_pointer = " ".join(pointer.split())
        for required in (_WO006_ISSUANCE_POINTER_HISTORY,
                         _WO006_SESSION_A_POINTER_HISTORY,
                         _WO006_SESSION_A_POINTER_ACCEPTANCE,
                         _WO006_SESSION_B_POINTER_HISTORY,
                         _WO006_SUPERSEDED_POINTER_ANCHORED,
                         _WO006_SUPERSEDED_POINTER_OPENING,
                         _WO006_SUPERSEDED_POINTER_CLAUSE):
            if wo006_pointer.count(required) != 1:
                add("WORKORDER.md", "WO-006 superseded pointer statement",
                    str(wo006_pointer.count(required)),
                    "exactly one " + required)
        for stale in ("docs/work-orders/issued/" + _WO006_NAME,
                      "docs/work-orders/proposed/" + _WO006_NAME,
                      "docs/work-orders/completed/" + _WO006_NAME):
            if stale in pointer:
                add("WORKORDER.md", "WO-006 pointer path", stale,
                    "docs/work-orders/superseded/" + _WO006_NAME)
        # The kept records name sessions beside words the scanner reads as
        # grants, so their pinned forms are removed once each before it looks
        # for a positive statement about ANY session: none is authorized once
        # WO-006 is superseded.
        scannable = " ".join(wo006_superseded_text.split())
        for kept in _WO006_SUPERSEDED_KEPT_RECORDS:
            scannable = scannable.replace(kept, "", 1)
        if _has_other_session_authorization("", scannable, ""):
            add(wo006_rel, "session authorization reopening",
                "positive permission for a WO-006 session",
                "WO-006 is superseded and no session is authorized")
        # Same scanners and attribution rule as the completed WO-004 and
        # WO-005 blocks.
        if (not _has_release_authorization(pointer)
                and _has_release_authorization(pointer,
                                               wo006_superseded_text)):
            add(wo006_rel, "release authorization",
                "positive release permission", _CLOSED_RELEASE_GATE)
        wo006_allowed_history: tuple[str, ...] = ()
        if wo003_completed_text:
            wo006_allowed_history = (
                _WO003_PRE_APPLICATION_POINTER_STATEMENT,
                _WO003_COMPLETED_APPLIED_POINTER_STATEMENT,
                _WO003_COMPLETION_POINTER_STATEMENT,
            )
        if (not _has_session_b_external_action_authorization(
                pointer, wo006_allowed_history)
                and _has_session_b_external_action_authorization(
                    pointer, wo006_allowed_history,
                    " ".join(wo006_superseded_text.split()))):
            add(wo006_rel, "external-action boundary",
                "positive permission for a further external action",
                "repository metadata, branch-protection, and social "
                "publication remain unauthorized")

    # WO-007's completed document is bound to the artifact the same way: the
    # canonical slice with its completion basis, the kept Session A and
    # exemption records, the completion record with the drafts' accepted
    # identities, the decision lock, the next gate, and the session, release,
    # and external-action boundaries keep running whoever owns the pointer.
    if wo007_completed_text:
        wo007_rel = (completed_dir / _WO007_NAME).relative_to(root).as_posix()
        for _f, _k, _found, _want in _wo007_completed_findings(
            pointer, wo007_completed_text, wo007_rel, "document"
        ):
            add(_f, _k, _found, _want)
        normalized_wo007 = " ".join(wo007_completed_text.split())
        scannable = normalized_wo007
        for kept in _WO007_COMPLETED_KEPT_RECORDS:
            scannable = scannable.replace(kept, "", 1)
        if _has_other_session_authorization("", scannable, ""):
            add(wo007_rel, "session authorization reopening",
                "positive permission for a WO-007 session",
                "WO-007 is completed and no session is authorized")
        if (not _has_release_authorization(pointer)
                and _has_release_authorization(pointer,
                                               wo007_completed_text)):
            add(wo007_rel, "release authorization",
                "positive release permission", _CLOSED_RELEASE_GATE)
        wo007_allowed_history: tuple[str, ...] = ()
        if wo003_completed_text:
            wo007_allowed_history = (
                _WO003_PRE_APPLICATION_POINTER_STATEMENT,
                _WO003_COMPLETED_APPLIED_POINTER_STATEMENT,
                _WO003_COMPLETION_POINTER_STATEMENT,
            )
        # The decision lock forbids the very actions this scanner looks for,
        # so its one pinned occurrence is removed first, as in the issued
        # branch.
        if (not _has_session_b_external_action_authorization(
                pointer, wo007_allowed_history)
                and _has_session_b_external_action_authorization(
                    pointer, wo007_allowed_history,
                    normalized_wo007.replace(_WO007_DRAFTING_PROHIBITION, "",
                                             1))):
            add(wo007_rel, "external-action boundary",
                "positive permission for a further external action",
                "repository metadata, branch-protection, and social "
                "publication remain unauthorized")

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

# Lines that state a past release's version as history. The frozen 2026-08-24
# audit names the tag it compared and the drift result it recorded, and the
# test workflow names the release its integration baseline was recorded on.
# Rewriting any of them to the current version would make it false, and the
# audit is a frozen record. Each entry is exempt from the version patterns
# only - tool and category counts on the line are still checked - and matches
# by its exact stripped content, so any other version string in the same file
# is still drift. Each must match exactly one line of its file: an edited,
# duplicated, or vanished line is a finding, never a silent loss of coverage.
_HISTORICAL_VERSION_LINES = (
    ("docs/audits/2026-08-24-uefn-42-official-mcp-audit.md",
     "Release tag under comparison: `v2.4.1` at"),
    ("docs/audits/2026-08-24-uefn-42-official-mcp-audit.md",
     "- drift: passed at v2.4.1, 362 tools, 55 categories;"),
    (".agents/workflows/run_tests.md",
     "Check the Output Log for `INTEGRATION TEST COMPLETE — Passed: N/N`. "
     "The v2.4.1"),
)

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
    historical_seen = {line: 0 for path, line in _HISTORICAL_VERSION_LINES
                       if path == rel_path}

    with open(abs_path, encoding="utf-8", errors="ignore") as f:
        for lineno, line in enumerate(f, 1):
            # Counted before any skip, so the exactly-once rule sees every line.
            version_exempt = line.strip() in historical_seen
            if version_exempt:
                historical_seen[line.strip()] += 1
            if _should_skip_line(line):
                continue

            if not exempt_file and not version_exempt:
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

    for line, count in historical_seen.items():
        if count != 1:
            findings.append({
                "file":     rel_path,
                "line":     0,
                "type":     "historical version exemption",
                "found":    f"{count} matching lines",
                "expected": "exactly one line: " + line,
                "content":  line,
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
