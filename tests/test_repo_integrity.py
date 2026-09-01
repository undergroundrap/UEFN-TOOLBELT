"""
Repo-level integrity checks.
==============================================================================
These replace the inline heredocs that used to live in .github/workflows/ci.yml,
so the same gates run locally via `pytest` and in CI without duplicated logic.

Note the syntax check here is broader than the old CI one, which globbed only
Content/Python/** plus three root files — it silently skipped scripts/, tests/,
tools/, and community_plugins/.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys

import pytest

SKIP_DIRS = {"verse-book", "__pycache__", ".git", "Intermediate", "Saved"}

BASE_FIELDS = ["id", "name", "version", "author", "type",
               "description", "category", "url", "min_toolbelt_version"]
COMMUNITY_EXTRA = ["download_url"]


def _python_files(root):
    for path in root.rglob("*.py"):
        if not SKIP_DIRS.intersection(path.parts):
            yield path


# ── Syntax ────────────────────────────────────────────────────────────────────

def test_every_python_file_parses(repo_root):
    failures = []
    for path in _python_files(repo_root):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"{path.relative_to(repo_root)}: {exc}")
    assert not failures, "Syntax errors:\n" + "\n".join(failures)


def test_syntax_check_actually_covers_the_tree(repo_root):
    """Guard against the glob silently narrowing again."""
    assert sum(1 for _ in _python_files(repo_root)) > 100


# ── registry.json (Plugin Hub) ────────────────────────────────────────────────

@pytest.fixture
def registry(repo_root):
    return json.loads((repo_root / "registry.json").read_text(encoding="utf-8"))


def test_registry_entries_have_required_fields(registry):
    failures = []
    for plugin in registry.get("plugins", []):
        required = BASE_FIELDS + (COMMUNITY_EXTRA if plugin.get("type") == "community" else [])
        for field in required:
            if field not in plugin:
                failures.append(f"plugin '{plugin.get('id', '?')}' missing '{field}'")
    assert not failures, "registry.json:\n" + "\n".join(failures)


def test_registry_ids_are_unique(registry):
    ids = [p.get("id") for p in registry.get("plugins", [])]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate plugin ids: {dupes}"


def test_registry_types_are_known(registry):
    bad = {p.get("type") for p in registry.get("plugins", [])} - {"core", "community"}
    assert not bad, f"unknown plugin type(s): {bad}"


# ── Version / count consistency ───────────────────────────────────────────────

def test_suite_does_not_pollute_the_repo(repo_root):
    """
    Regression guard. The fake `unreal` in conftest once returned a MagicMock from
    Paths.project_saved_dir(); core/activity_log.py joined it into a path and
    makedirs'd it, creating a literal `MagicMock/` tree inside the repo on every
    test run. Path-shaped fakes must return real strings pointed at the sandbox.
    """
    strays = [p.name for p in repo_root.iterdir()
              if p.is_dir() and ("MagicMock" in p.name or p.name.startswith("<"))]
    assert not strays, f"test run created stray directories: {strays}"


def test_drift_check_passes(repo_root):
    """
    scripts/drift_check.py is the project's own gate for stale version and
    tool-count references across docs and UI. Run it here so it can't rot.
    """
    proc = subprocess.run(
        [sys.executable, "scripts/drift_check.py"],
        cwd=repo_root, capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"drift_check failed:\n{proc.stdout}\n{proc.stderr}"


def test_drift_check_covers_agent_context_surfaces(repo_root):
    """Counts in secondary agent entry points must not escape the drift gate."""
    tree = ast.parse(
        (repo_root / "scripts" / "drift_check.py").read_text(encoding="utf-8")
    )
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SCAN_FILES"
                for target in node.targets)
    )
    assert isinstance(assignment.value, ast.List)
    scanned = {
        item.value
        for item in assignment.value.elts
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }
    required = {
        "WORKORDER.md",
        "SECURITY.md",
        "AGENTS.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "llms.txt",
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
        ".agents/workflows/add_new_tool.md",
        ".agents/workflows/run_tests.md",
        ".github/pull_request_template.md",
        ".claude/agents/tool-developer.md",
        ".claude/commands/add-tool.md",
        ".claude/commands/deploy.md",
        ".claude/commands/drift.md",
        ".claude/commands/publish-check.md",
        ".claude/mcp_reference.md",
        ".claude/rules/tool_authoring.md",
    }
    assert required <= scanned, f"agent context missing from drift scan: {required - scanned}"


def test_work_order_repository_memory_cannot_self_authorize(repo_root):
    """Proposals are durable plans; only the root pointer can open a gate."""
    pointer = (repo_root / "WORKORDER.md").read_text(encoding="utf-8")
    pointer_lines = pointer.splitlines()
    current_lines = [line for line in pointer_lines
                     if line.startswith("- Current issued Work Order:")]
    session_lines = [line for line in pointer_lines
                     if line.startswith("- Authorized session:")]
    base_lines = [line for line in pointer_lines
                  if line.startswith("- Base commit:")]
    assert len(current_lines) == 1
    assert len(session_lines) == 1
    assert len(base_lines) == 1
    current = current_lines[0].split(":", 1)[1].strip()
    session = session_lines[0].split(":", 1)[1].strip()
    gate_lines = [line for line in pointer_lines if line.startswith("- Current gate:")]
    assert len(gate_lines) == 1

    work_orders = repo_root / "docs" / "work-orders"
    guide = (work_orders / "README.md").read_text(encoding="utf-8")
    for state in ("PROPOSED", "ISSUED", "COMPLETED", "SUPERSEDED"):
        assert f"`{state}`" in guide
    assert "Only the repository-root `WORKORDER.md`" in guide
    assert "no implementation is authorized" in guide
    assert "at most one detailed Work Order is issued" in guide

    proposals = sorted((work_orders / "proposed").glob("WO-*.md"))
    expected_proposals = {
        "WO-004-modal-observability.md",
        "WO-005-coverage-source-of-truth.md",
        "WO-006-official-vs-toolbelt-benchmark.md",
        "WO-007-public-mcp-explainer.md",
    }
    assert {path.name for path in proposals} == expected_proposals
    for proposal in proposals:
        lines = proposal.read_text(encoding="utf-8").splitlines()
        status_lines = [line.strip() for line in lines if line.startswith("STATUS:")]
        auth_lines = [line.strip() for line in lines if line.startswith("AUTHORIZATION:")]
        assert status_lines == ["STATUS: PROPOSED"], proposal
        assert auth_lines == ["AUTHORIZATION: NOT AUTHORIZED"], proposal
        assert not any(line.startswith("- Current issued Work Order:") for line in lines)
        assert not any(line.startswith("- Authorized session:") for line in lines)

    for document in work_orders.rglob("*.md"):
        lines = document.read_text(encoding="utf-8").splitlines()
        assert not any(
            line.startswith(("- Current issued Work Order:",
                             "- Authorized session:",
                             "- Current gate:"))
            for line in lines
        ), document

    issued = [path for path in (work_orders / "issued").glob("*.md")
              if path.name.lower() != "readme.md"]
    completed = [path for path in (work_orders / "completed").glob("*.md")
                 if path.name.lower() != "readme.md"]
    assert [path.name for path in issued] == [
        "WO-003-official-mcp-doc-convergence.md"
    ]
    assert {path.name for path in completed} == {
        "WO-001-custom-mcp-security.md",
        "WO-002-epic-toolset-integration.md",
    }
    assert len(completed) == 2
    assert (work_orders / "completed" / "WO-002-epic-toolset-integration.md").exists()
    assert current == "WO-003"
    assert session == "NONE"
    assert base_lines == [
        "- Base commit: `e23baa40c4b9358eb6b4448f460c054650ae64f0`"
    ]
    assert gate_lines == [
        "- Current gate: WO-003 SESSION B ACCEPTED "
        "— REPOSITORY DESCRIPTION APPLICATION NOT AUTHORIZED"
    ]
    # Session A and Session B are both accepted and no session is open.
    # All issuance, authorization, and acceptance provenance stays declared.
    for line in (
        "- Issuance commit: `19350aa324bea4d88e494ee806801586a383d76e`",
        "- Issuance CI workflow: `33148089523`",
        "- Issuance CI job: `98773518991` — Lint, types, tests",
        "- Session A authorization commit:"
        " `52d89295614a4ce686094736d87f7e6c907e12a0`",
        "- Session A authorization CI workflow: `33200547479`",
        "- Session A authorization CI job: `98948639416` — Lint, types, tests",
        "- Session A acceptance commit:"
        " `d23add58e02ddc855573cf9be7a2542776d25e7e`",
        "- Session A acceptance CI workflow: `33344006899`",
        "- Session A acceptance CI job: `99344607213` — Lint, types, tests",
        "- Session B authorization commit:"
        " `2582be8c9168d72b46846334bbba44307d348ce6`",
        "- Session B authorization CI workflow: `33351157691`",
        "- Session B authorization CI job: `99364656646` — Lint, types, tests",
        "- Session B acceptance commit:"
        " `e23baa40c4b9358eb6b4448f460c054650ae64f0`",
        "- Session B acceptance CI workflow: `33476969423`",
        "- Session B acceptance CI job: `99758148278` — Lint, types, tests",
    ):
        assert line in pointer, line
    normalized_pointer = " ".join(pointer.split())
    assert (
        "The live GitHub repository description is unchanged. Applying the "
        "exact accepted repository description remains a separate "
        "owner-authorized external action. Metadata application, tags, "
        "Releases, and social publication all remain unauthorized, as do "
        "Session C and WO-004."
        in normalized_pointer
    )
    assert (
        "No repository metadata application, tag, Release, or social publication "
        "is authorized." not in normalized_pointer
    )
    assert "- Release train: WO-001 through WO-007" in pointer
    assert (
        "- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED — COMPLETE THE "
        "FROZEN TRAIN AND FINAL INTEGRATION/REPOSITORY-TRUTH AUDIT FIRST"
    ) in pointer
    assert "version 2.4.1" in pointer
    assert "docs/work-orders/completed/WO-001-custom-mcp-security.md" in pointer
    assert "docs/work-orders/issued/WO-001-custom-mcp-security.md" not in pointer
    assert "docs/work-orders/proposed/WO-001-custom-mcp-security.md" not in pointer
    assert "docs/work-orders/completed/WO-002-epic-toolset-integration.md" in pointer
    assert "docs/work-orders/proposed/WO-002-epic-toolset-integration.md" not in pointer

    wo003 = work_orders / "issued" / "WO-003-official-mcp-doc-convergence.md"
    wo003_text = wo003.read_text(encoding="utf-8")
    wo003_lines = wo003_text.splitlines()
    assert [line for line in wo003_lines if line.startswith("STATUS:")] == [
        "STATUS: ISSUED"
    ]
    assert [line for line in wo003_lines if line.startswith("AUTHORIZATION:")] == [
        "AUTHORIZATION: ISSUED — SESSION B ACCEPTED; NO SESSION AUTHORIZED"
    ]
    for evidence in (
        "SESSION_A_ACCEPTANCE_COMMIT:"
        " `d23add58e02ddc855573cf9be7a2542776d25e7e`",
        "SESSION_A_ACCEPTANCE_CI_WORKFLOW: `33344006899`",
        "SESSION_A_ACCEPTANCE_CI_JOB: `99344607213` — Lint, types, tests",
        "## Session A acceptance record",
        "At the Session A acceptance gate, Session A was accepted and complete",
        "SESSION_B_AUTHORIZATION_COMMIT:"
        " `2582be8c9168d72b46846334bbba44307d348ce6`",
        "SESSION_B_AUTHORIZATION_CI_WORKFLOW: `33351157691`",
        "SESSION_B_AUTHORIZATION_CI_JOB: `99364656646` — Lint, types, tests",
        "## Session B authorization and draft record",
        "PROPOSED_DESCRIPTION_CHARACTER_COUNT: `261`",
        _WO003_DESCRIPTION_DRAFT,
        "SESSION_B_ACCEPTANCE_COMMIT:"
        " `e23baa40c4b9358eb6b4448f460c054650ae64f0`",
        "SESSION_B_ACCEPTANCE_CI_WORKFLOW: `33476969423`",
        "SESSION_B_ACCEPTANCE_CI_JOB: `99758148278` — Lint, types, tests",
        "## Session B acceptance record",
        "ACCEPTED_DESCRIPTION_CHARACTER_COUNT: `261`",
        "still a DRAFT and has NOT BEEN APPLIED",
        "The live GitHub repository description is unchanged.",
        "NEXT GATE: separate BDFL/owner authorization to apply the exact"
        " accepted",
    ):
        assert evidence in wo003_text
    assert "SESSION B AUTHORIZED FOR DRAFTING ONLY" not in wo003_text

    wo002 = (work_orders / "completed"
             / "WO-002-epic-toolset-integration.md")
    issued_text = wo002.read_text(encoding="utf-8")
    issued_lines = issued_text.splitlines()
    assert [line for line in issued_lines if line.startswith("BASELINE:")] == [
        "BASELINE: `098b38c669dd330cd059ea18dea52cc4e7eaefe2`"
    ]
    assert [line for line in issued_lines if line.startswith("STATUS:")] == [
        "STATUS: COMPLETED"
    ]
    assert [line for line in issued_lines if line.startswith("AUTHORIZATION:")] == [
        "AUTHORIZATION: COMPLETED — NO SESSION AUTHORIZED"
    ]
    for evidence in (
        "098b38c669dd330cd059ea18dea52cc4e7eaefe2",
        "32925047925",
        "98046156859",
        "d87572e2a272c98f8dd634cfe17ff8a130446a7b",
        "32931353926",
        "98064090312",
    ):
        assert evidence in issued_text
    for evidence in (
        "50b881716abea3b5838c2a971caac40ee4cd5d30",
        "32937631903",
        "98081919978",
    ):
        assert evidence in issued_text
        assert evidence in pointer
    assert "## Session A acceptance record" in issued_text
    assert "## Session A — internal contract and truth correction" in issued_text
    assert "## Session B — external official-MCP proof" in issued_text
    assert "## Proposed Session A" not in issued_text
    assert "## Proposed Session B" not in issued_text
    assert (
        "NEXT GATE: separate owner authorization for a fresh independent WO-003\n"
        "pre-issuance review, after this completion transition is accepted,\n"
        "committed, pushed, and green. Completion of WO-002 does not issue or\n"
        "authorize WO-003, which remains proposed and unauthorized."
        in issued_text
    )

    # Addressed by filename, never by enumeration order: Path.glob is
    # filesystem-ordered, so completed[0] was WO-001 on Windows and WO-002
    # on Linux once a second Work Order was completed.
    wo001 = work_orders / "completed" / "WO-001-custom-mcp-security.md"
    completed_text = wo001.read_text(encoding="utf-8")
    completed_lines = completed_text.splitlines()
    completed_status = [
        line for line in completed_lines if line.startswith("STATUS:")
    ]
    completed_auth = [
        line for line in completed_lines if line.startswith("AUTHORIZATION:")
    ]
    assert completed_status == ["STATUS: COMPLETED"]
    assert completed_auth == [
        "AUTHORIZATION: COMPLETED — NO SESSION AUTHORIZED"
    ]
    assert "## Session A — authenticated, fail-closed control plane" in completed_text
    assert "## Proposed Session A" not in completed_text
    assert "34c3762b32c36805e3ec2f7f93df68c2c17fd26c" in completed_text
    assert "32701409756" in completed_text
    assert "32890583500" in completed_text
    assert "ffcbe8b1bfa03cb37453b9beefda0bbdbe45543c" in completed_text
    assert "32921154482" in completed_text
    assert "98034843256" in completed_text
    assert "Issuance alone grants no implementation authority" in completed_text
    assert (
        "NEXT GATE: separate owner authorization for fresh independent pre-issuance\n"
        "review of WO-002. Completion of WO-001 does not issue or authorize WO-002, "
        "and\nno implementation session is authorized."
        in completed_text
    )

    issued_readme = (work_orders / "issued" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "No Work Order is currently issued" not in issued_readme
    assert "repository-root\n`WORKORDER.md` for the sole current gate" in issued_readme
    security = (repo_root / "SECURITY.md").read_text(encoding="utf-8")
    security_normalized = " ".join(security.split())
    assert "Work Order WO-001" in security_normalized


def _make_wo003_session_b_accepted_case(repo_root, tmp_path, name):
    """Copy the current accepted WO-003 Session B state."""
    case = tmp_path / name
    case.mkdir(parents=True)
    shutil.copy2(repo_root / "WORKORDER.md", case / "WORKORDER.md")
    shutil.copytree(
        repo_root / "docs" / "work-orders",
        case / "docs" / "work-orders",
    )
    return case


def _make_wo003_session_b_case(repo_root, tmp_path, name):
    """Reconstruct the preserved authorized Session B drafting state.

    Accepting Session B moved the current state forward again, so the
    drafting-only state every earlier WO-003 fixture builds on is now
    itself a reconstruction.
    """
    case = _make_wo003_session_b_accepted_case(repo_root, tmp_path, name)
    issued = case / _WO003_REL
    text = issued.read_text(encoding="utf-8")
    for old, new in (
        (_WO003_SESSION_B_ACCEPTED_MARKER, _WO003_SESSION_B_MARKER),
        (
            _NL + "SESSION_B_ACCEPTANCE_COMMIT: `"
            + _WO003_SESSION_B_ACCEPTED_BASE + "`" + _NL
            + _NL + "SESSION_B_ACCEPTANCE_CI_WORKFLOW: `"
            + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`" + _NL
            + _NL + "SESSION_B_ACCEPTANCE_CI_JOB: `"
            + _WO003_SESSION_B_ACCEPTED_JOB + "` " + _EM
            + " Lint, types, tests" + _NL,
            "",
        ),
        (_WO003_SESSION_B_ACCEPTED_STATEMENT, _WO003_SESSION_B_STATEMENT),
        (_WO003_SESSION_B_ACCEPTED_NEXT_GATE, _WO003_SESSION_B_NEXT_GATE),
    ):
        text = _replace_once(text, old, new, "WO-003 drafting reconstruction")
    _require_unique(
        text,
        (_WO003_SESSION_B_ACCEPTANCE_HEADING, "## Planning basis"),
        "WO-003 Session B acceptance-record excision",
    )
    text = _sub_once(
        _NL + _WO003_SESSION_B_ACCEPTANCE_HEADING + _NL + ".*?(?="
        + _NL + "## Planning basis" + _NL + ")",
        "",
        text,
        "WO-003 Session B acceptance-record excision",
        flags=re.DOTALL,
    )
    issued.write_text(text, encoding="utf-8")

    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    for old, new in (
        ("- Authorized session: NONE", "- Authorized session: B"),
        (
            "- Base commit: `" + _WO003_SESSION_B_ACCEPTED_BASE + "`",
            "- Base commit: `" + _WO003_SESSION_B_BASE + "`",
        ),
        (_WO003_SESSION_B_ACCEPTED_GATE, _WO003_SESSION_B_GATE),
        (
            "- Session B acceptance commit: `"
            + _WO003_SESSION_B_ACCEPTED_BASE + "`" + _NL
            + "- Session B acceptance CI workflow: `"
            + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`" + _NL
            + "- Session B acceptance CI job: `"
            + _WO003_SESSION_B_ACCEPTED_JOB + "` " + _EM
            + " Lint, types, tests" + _NL,
            "",
        ),
        (
            _WO003_SESSION_B_ACCEPTED_POINTER_STATEMENT,
            _WO003_SESSION_B_POINTER_STATEMENT,
        ),
    ):
        text = _replace_once(text, old, new, "WO-003 drafting pointer")
    pointer.write_text(text, encoding="utf-8")

    _assert_reconstructed(
        "WO-003 drafting pointer", pointer.read_text(encoding="utf-8"),
        ("- Authorized session: B", _WO003_SESSION_B_GATE,
         "- Session B authorization commit: `" + _WO003_SESSION_B_BASE
         + "`"),
        ("- Session B acceptance commit:", "SESSION B ACCEPTED"),
    )
    _assert_reconstructed(
        "WO-003 drafting reconstruction", issued.read_text(encoding="utf-8"),
        (_WO003_SESSION_B_MARKER,
         "## Session B authorization and draft record"),
        ("SESSION_B_ACCEPTANCE_COMMIT:",
         _WO003_SESSION_B_ACCEPTANCE_HEADING),
    )
    return case


def _make_wo003_accepted_case(repo_root, tmp_path, name):
    """Reconstruct the preserved accepted WO-003 Session A state."""
    case = _make_wo003_session_b_case(repo_root, tmp_path, name)
    issued = case / _WO003_REL
    text = issued.read_text(encoding="utf-8")
    for old, new in (
        (
            _WO003_SESSION_B_MARKER,
            "AUTHORIZATION: ISSUED " + _EM
            + " SESSION A ACCEPTED; NO SESSION AUTHORIZED",
        ),
        (
            _NL + "SESSION_B_AUTHORIZATION_COMMIT: `"
            + _WO003_SESSION_B_BASE + "`" + _NL
            + _NL + "SESSION_B_AUTHORIZATION_CI_WORKFLOW: `"
            + _WO003_SESSION_B_WORKFLOW + "`" + _NL
            + _NL + "SESSION_B_AUTHORIZATION_CI_JOB: `"
            + _WO003_SESSION_B_JOB + "` " + _EM
            + " Lint, types, tests" + _NL,
            "",
        ),
        (
            _WO003_SESSION_B_STATEMENT,
            "This Work Order remains issued. Session A is accepted and complete,"
            + " and no" + _NL
            + "session is currently authorized. Session B remains unauthorized"
            + " and requires" + _NL
            + "separate owner authorization.",
        ),
        (
            _WO003_SESSION_B_NEXT_GATE,
            "NEXT GATE: fresh independent architect review of the complete"
            + " uncommitted" + _NL
            + "Session A acceptance transition. Session B remains unauthorized.",
        ),
        (
            "Session B is authorized under the current root `WORKORDER.md` gate."
            + " Its scope" + _NL
            + "is drafting only: it may read the current GitHub repository"
            + " description," + _NL
            + "prepare exactly one replacement description",
            "Session B requires a separate owner gate. Its scope after that gate"
            + " is drafting only: it may read the current" + _NL
            + "GitHub repository description, prepare exactly one replacement"
            + " description",
        ),
    ):
        text = _replace_once(text, old, new, "WO-003 accepted reconstruction")
    _require_unique(
        text,
        ("## Session B authorization and draft record", "## Planning basis"),
        "WO-003 Session B record excision",
    )
    text = _sub_once(
        _NL + "## Session B authorization and draft record" + _NL + ".*?(?="
        + _NL + "## Planning basis" + _NL + ")",
        "",
        text,
        "WO-003 Session B record excision",
        flags=re.DOTALL,
    )
    issued.write_text(text, encoding="utf-8")

    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    for old, new in (
        ("- Authorized session: B", "- Authorized session: NONE"),
        (
            "- Base commit: `" + _WO003_SESSION_B_BASE + "`",
            "- Base commit: `" + _WO003_SESSION_A_ACCEPTED_BASE + "`",
        ),
        (
            _WO003_SESSION_B_GATE,
            "- Current gate: WO-003 SESSION A ACCEPTED " + _EM
            + " SESSION B NOT AUTHORIZED",
        ),
        (
            "- Session B authorization commit: `" + _WO003_SESSION_B_BASE
            + "`" + _NL
            + "- Session B authorization CI workflow: `"
            + _WO003_SESSION_B_WORKFLOW + "`" + _NL
            + "- Session B authorization CI job: `" + _WO003_SESSION_B_JOB
            + "` " + _EM + " Lint, types, tests" + _NL,
            "",
        ),
        (_NL + _WO003_SESSION_B_POINTER_STATEMENT + _NL, ""),
    ):
        text = _replace_once(text, old, new, "WO-003 accepted pointer")
    pointer.write_text(text, encoding="utf-8")

    _assert_reconstructed(
        "WO-003 accepted pointer", pointer.read_text(encoding="utf-8"),
        ("- Authorized session: NONE", _WO003_SESSION_A_ACCEPTED_GATE),
        ("- Session B authorization commit:",
         "DRAFT REPOSITORY DESCRIPTION ONLY"),
    )
    _assert_reconstructed(
        "WO-003 accepted reconstruction", issued.read_text(encoding="utf-8"),
        ("AUTHORIZATION: ISSUED " + _EM
         + " SESSION A ACCEPTED; NO SESSION AUTHORIZED",
         "## Session A acceptance record"),
        ("SESSION_B_AUTHORIZATION_COMMIT:",
         "## Session B authorization and draft record"),
    )
    return case


def _make_wo003_session_a_case(repo_root, tmp_path, name):
    """Reconstruct the preserved authorized WO-003 Session A state."""
    case = _make_wo003_accepted_case(repo_root, tmp_path, name)
    issued = case / _WO003_REL
    text = issued.read_text(encoding="utf-8")
    for old, new in (
        (
            "AUTHORIZATION: ISSUED " + _EM
            + " SESSION A ACCEPTED; NO SESSION AUTHORIZED",
            "AUTHORIZATION: ISSUED " + _EM
            + " SESSION A AUTHORIZED FOR IMPLEMENTATION",
        ),
        (
            _NL + "SESSION_A_ACCEPTANCE_COMMIT: `"
            + _WO003_SESSION_A_ACCEPTED_BASE + "`" + _NL
            + _NL + "SESSION_A_ACCEPTANCE_CI_WORKFLOW: `"
            + _WO003_SESSION_A_ACCEPTED_WORKFLOW + "`" + _NL
            + _NL + "SESSION_A_ACCEPTANCE_CI_JOB: `"
            + _WO003_SESSION_A_ACCEPTED_JOB + "` " + _EM
            + " Lint, types, tests" + _NL,
            "",
        ),
        (
            "This Work Order remains issued. Session A is accepted and complete,"
            + " and no" + _NL
            + "session is currently authorized. Session B remains unauthorized"
            + " and requires" + _NL
            + "separate owner authorization.",
            "This Work Order is issued and Session A is authorized under root"
            + _NL + "`WORKORDER.md`. Session B is not authorized and requires a"
            + " separate owner gate.",
        ),
        (
            "NEXT GATE: fresh independent architect review of the complete"
            + " uncommitted" + _NL
            + "Session A acceptance transition. Session B remains unauthorized.",
            "NEXT GATE: fresh independent architect review of the complete"
            + " uncommitted" + _NL
            + "Session A implementation. Session B remains unauthorized.",
        ),
    ):
        text = _replace_once(text, old, new, "WO-003 authorized reconstruction")
    _require_unique(
        text,
        ("## Session A acceptance record", "## Planning basis"),
        "WO-003 acceptance-record excision",
    )
    text = _sub_once(
        _NL + "## Session A acceptance record" + _NL + ".*?(?="
        + _NL + "## Planning basis" + _NL + ")",
        "",
        text,
        "WO-003 acceptance-record excision",
        flags=re.DOTALL,
    )
    issued.write_text(text, encoding="utf-8")

    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    for old, new in (
        ("- Authorized session: NONE", "- Authorized session: A"),
        (
            "- Base commit: `" + _WO003_SESSION_A_ACCEPTED_BASE + "`",
            "- Base commit: `" + _WO003_SESSION_A_BASE + "`",
        ),
        (
            "- Current gate: WO-003 SESSION A ACCEPTED " + _EM
            + " SESSION B NOT AUTHORIZED",
            "- Current gate: WO-003 SESSION A AUTHORIZED " + _EM
            + " IMPLEMENT SESSION A ONLY",
        ),
        (
            "- Session A acceptance commit: `"
            + _WO003_SESSION_A_ACCEPTED_BASE + "`" + _NL
            + "- Session A acceptance CI workflow: `"
            + _WO003_SESSION_A_ACCEPTED_WORKFLOW + "`" + _NL
            + "- Session A acceptance CI job: `"
            + _WO003_SESSION_A_ACCEPTED_JOB + "` " + _EM
            + " Lint, types, tests" + _NL,
            "",
        ),
        (
            "Session A was independently accepted, committed, and pushed as"
            + _NL + "`" + _WO003_SESSION_A_ACCEPTED_BASE
            + "`; successful CI workflow" + _NL
            + "`" + _WO003_SESSION_A_ACCEPTED_WORKFLOW
            + "` included successful required job `"
            + _WO003_SESSION_A_ACCEPTED_JOB + "` (`Lint, types," + _NL
            + "tests`). Accepted live `TOOL_TEST` evidence recorded a deploy"
            + " and full UEFN" + _NL
            + "restart, 362 tools across 55 categories, corrected dashboard"
            + " About ordering," + _NL
            + "matching source and deployed runtime hashes, no Fortnite or"
            + " play session and no" + _NL
            + "level mutation, then a stopped listener, closed UEFN, absent"
            + " handoff, and closed" + _NL
            + "ports 8765" + chr(8211)
            + "8770. At the Session A acceptance gate, Session A was accepted and"
            + _NL
            + "complete with no current implementation authority; Session B was"
            + " not authorized" + _NL
            + "pending separate owner authorization.",
            "Session A is authorized for implementation under this pointer alone,"
            + " on the" + _NL + "basis of commit `" + _WO003_SESSION_A_BASE
            + "`, successful CI" + _NL + "workflow `"
            + _WO003_SESSION_A_WORKFLOW + "`, and successful required job `"
            + _WO003_SESSION_A_JOB + "`" + _NL
            + "(`Lint, types, tests`). Session B is not authorized and requires"
            + " a separate owner gate.",
        ),
    ):
        text = _replace_once(text, old, new, "WO-003 authorized pointer")
    pointer.write_text(text, encoding="utf-8")

    _assert_reconstructed(
        "WO-003 authorized pointer", pointer.read_text(encoding="utf-8"),
        ("- Authorized session: A", _WO003_SESSION_A_GATE),
        ("- Session A acceptance commit:", "SESSION A ACCEPTED"),
    )
    _assert_reconstructed(
        "WO-003 authorized reconstruction", issued.read_text(encoding="utf-8"),
        (_WO003_SESSION_A_MARKER, "## Session A authorization basis"),
        ("SESSION_A_ACCEPTANCE_COMMIT:", "## Session A acceptance record"),
    )
    return case


def _make_wo003_issued_case(repo_root, tmp_path, name):
    """Reconstruct the closed-session issued WO-003 state.

    Authorizing Session A moved the current state forward again, so the
    issued state every earlier fixture builds on is now itself a
    reconstruction.
    """
    case = _make_wo003_session_a_case(repo_root, tmp_path, name)
    issued = case / _WO003_REL
    assert issued.exists(), "WO-003 is not in issued/ to reconstruct from"

    text = issued.read_text(encoding="utf-8")
    for _old, _new in (
        (
            "AUTHORIZATION: ISSUED " + _EM
            + " SESSION A AUTHORIZED FOR IMPLEMENTATION",
            "AUTHORIZATION: ISSUED " + _EM + " SESSION NOT AUTHORIZED",
        ),
        (
            _NL + "SESSION_A_AUTHORIZATION_COMMIT: `"
            + _WO003_SESSION_A_BASE + "`" + _NL
            + _NL + "SESSION_A_AUTHORIZATION_CI_WORKFLOW: `"
            + _WO003_SESSION_A_WORKFLOW + "`" + _NL
            + _NL + "SESSION_A_AUTHORIZATION_CI_JOB: `"
            + _WO003_SESSION_A_JOB + "` " + _EM + " Lint, types, tests" + _NL,
            "",
        ),
        (
            "Issuance alone grants no implementation authority. A session becomes"
            + _NL
            + "implementable only when the owner names it in root `WORKORDER.md`; the"
            + _NL
            + "Session A authorization recorded below came from that pointer, not from"
            + _NL
            + "issuance. Session B is not authorized and requires a separate owner gate."
            + _NL
            + "The planning baseline above is preserved unchanged; it records the state"
            + _NL + "this mandate was planned against, not the issuance point.",
            "Issuance alone grants no implementation authority. Session A and Session B"
            + _NL
            + "both remain unauthorized until the owner authorizes a session in root"
            + _NL
            + "`WORKORDER.md`. The planning baseline above is preserved unchanged; it"
            + _NL
            + "records the state this mandate was planned against, not the issuance point.",
        ),
        (
            "This Work Order is issued and Session A is authorized under root" + _NL
            + "`WORKORDER.md`. Session B is not authorized and requires a separate"
            + " owner gate.",
            "This Work Order is issued but authorizes neither session.",
        ),
        (
            "NEXT GATE: fresh independent architect review of the complete uncommitted"
            + _NL
            + "Session A implementation. Session B remains unauthorized.",
            "NEXT GATE: explicit BDFL/owner authorization for Session A. Issuance alone"
            + _NL
            + "grants no implementation authority; Session A and Session B remain" + _NL
            + "unauthorized.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-003 issued reconstruction")
    _require_unique(
        text,
        ("## Session A authorization basis", "## Planning basis"),
        "WO-003 authorization-basis excision",
    )
    text = _sub_once(
        _NL + "## Session A authorization basis" + _NL + ".*?(?="
        + _NL + "## Planning basis" + _NL + ")",
        "",
        text,
        "WO-003 authorization-basis excision",
        flags=re.DOTALL,
    )
    issued.write_text(text, encoding="utf-8")

    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    for _old, _new in (
        ("- Authorized session: A", "- Authorized session: NONE"),
        (
            "- Base commit: `" + _WO003_SESSION_A_BASE + "`",
            "- Base commit: `" + _WO003_ISSUANCE_COMMIT + "`",
        ),
        (
            "- Current gate: WO-003 SESSION A AUTHORIZED " + _EM
            + " IMPLEMENT SESSION A ONLY",
            "- Current gate: WO-003 ISSUED " + _EM
            + " SESSION A IMPLEMENTATION NOT AUTHORIZED",
        ),
        (
            "- Session A authorization commit: `" + _WO003_SESSION_A_BASE
            + "`" + _NL
            + "- Session A authorization CI workflow: `"
            + _WO003_SESSION_A_WORKFLOW + "`" + _NL
            + "- Session A authorization CI job: `" + _WO003_SESSION_A_JOB
            + "` " + _EM + " Lint, types, tests" + _NL,
            "",
        ),
        (
            "is issued. Its accepted planning baseline is",
            "is issued, but issuance grants no implementation authority."
            + " Session A and" + _NL
            + "Session B remain unauthorized. Its accepted planning baseline is",
        ),
        (
            _NL
            + "Session A is authorized for implementation under this pointer alone,"
            + " on the" + _NL + "basis of commit `" + _WO003_SESSION_A_BASE
            + "`, successful CI" + _NL + "workflow `"
            + _WO003_SESSION_A_WORKFLOW + "`, and successful required job `"
            + _WO003_SESSION_A_JOB + "`" + _NL
            + "(`Lint, types, tests`). Session B is not authorized and requires"
            + " a separate owner gate." + _NL,
            "",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-003 issued pointer")
    pointer.write_text(text, encoding="utf-8")

    _assert_reconstructed(
        "WO-003 issued pointer",
        pointer.read_text(encoding="utf-8"),
        ("- Authorized session: NONE",
         "- Current gate: WO-003 ISSUED " + _EM
         + " SESSION A IMPLEMENTATION NOT AUTHORIZED"),
        ("- Authorized session: A", "SESSION A AUTHORIZED",
         "- Session A authorization commit:"),
    )
    _assert_reconstructed(
        "WO-003 issued reconstruction",
        issued.read_text(encoding="utf-8"),
        ("AUTHORIZATION: ISSUED " + _EM + " SESSION NOT AUTHORIZED",
         "ISSUANCE_COMMIT: `" + _WO003_ISSUANCE_COMMIT + "`"),
        ("## Session A authorization basis",
         "SESSION_A_AUTHORIZATION_COMMIT:",
         "SESSION A AUTHORIZED FOR IMPLEMENTATION"),
    )
    return case


def _make_wo002_completed_case(repo_root, tmp_path, name):
    """Reconstruct the terminal WO-002 state from the issued WO-003 state.

    Issuing WO-003 moved the current state forward again, so the WO-002
    completion every earlier fixture builds on is now itself a reconstruction.
    """
    case = _make_wo003_issued_case(repo_root, tmp_path, name)
    issued = (case / "docs" / "work-orders" / "issued"
              / "WO-003-official-mcp-doc-convergence.md")
    proposed = (case / "docs" / "work-orders" / "proposed"
                / "WO-003-official-mcp-doc-convergence.md")
    assert issued.exists(), "WO-003 is not in issued/ to reconstruct from"
    issued.replace(proposed)

    text = proposed.read_text(encoding="utf-8")
    for _old, _new in (
        ("STATUS: ISSUED", "STATUS: PROPOSED"),
        (
            _NL + "ISSUANCE_COMMIT: `19350aa324bea4d88e494ee806801586a383d76e`"
            + _NL + _NL + "ISSUANCE_CI_WORKFLOW: `33148089523`"
            + _NL + _NL + "ISSUANCE_CI_JOB: `98773518991` " + _EM
            + " Lint, types, tests" + _NL,
            "",
        ),
        (
            "AUTHORIZATION: ISSUED " + _EM + " SESSION NOT AUTHORIZED",
            "AUTHORIZATION: NOT AUTHORIZED",
        ),
        (
            "NEXT GATE: explicit BDFL/owner authorization for Session A."
            " Issuance alone" + _NL
            + "grants no implementation authority; Session A and Session B remain" + _NL
            + "unauthorized.",
            "NEXT GATE: fresh independent pre-issuance architect review of this"
            " corrected" + _NL + "proposed WO-003 mandate.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-003 proposed reconstruction")
    _require_unique(
        text,
        ("## Issuance basis", "## Planning basis"),
        "WO-003 issuance-basis excision",
    )
    text = _sub_once(
        _NL + "## Issuance basis" + _NL + ".*?(?=" + _NL + "## Planning basis" + _NL + ")",
        "",
        text,
        "WO-003 issuance-basis excision",
        flags=re.DOTALL,
    )
    proposed.write_text(text, encoding="utf-8")

    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    for _old, _new in (
        ("- Current issued Work Order: WO-003", "- Current issued Work Order: NONE"),
        (
            "- Issuance commit: `19350aa324bea4d88e494ee806801586a383d76e`" + _NL
            + "- Issuance CI workflow: `33148089523`" + _NL
            + "- Issuance CI job: `98773518991` " + _EM + " Lint, types, tests"
            + _NL,
            "",
        ),
        (
            "- Base commit: `19350aa324bea4d88e494ee806801586a383d76e`",
            "- Base commit: `c031f20e33c716ecc9f9ce546a7419b865ed8641`",
        ),
        (
            "- Current gate: WO-003 ISSUED " + _EM
            + " SESSION A IMPLEMENTATION NOT AUTHORIZED",
            "- Current gate: WO-002 COMPLETED " + _EM
            + " WO-003 PROPOSED AND NOT AUTHORIZED",
        ),
        (
            "negative result bounded by ToolsetPolicy. WO-002 is complete; no session" + _NL
            + "is authorized.",
            "negative result bounded by ToolsetPolicy. WO-002 is complete; no session" + _NL
            + "is authorized. WO-003 remains proposed and unauthorized.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-002 completed pointer")
    _require_unique(
        text,
        ("[`WO-003`](docs/work-orders/issued/"
         "WO-003-official-mcp-doc-convergence.md)",
         "WO-001 through WO-007 form the frozen next release train."
         " The release version"),
        "WO-003 pointer-paragraph excision",
    )
    text = _sub_once(
        _NL + re.escape("[`WO-003`](docs/work-orders/issued/"
                        "WO-003-official-mcp-doc-convergence.md)")
        + ".*?(?=" + _NL + "WO-001 through WO-007 form the frozen next release train.)",
        "",
        text,
        "WO-003 pointer-paragraph excision",
        flags=re.DOTALL,
    )
    pointer.write_text(text, encoding="utf-8")

    _assert_reconstructed(
        "WO-002 completed pointer",
        pointer.read_text(encoding="utf-8"),
        ("- Current issued Work Order: NONE",
         "- Current gate: WO-002 COMPLETED " + _EM
         + " WO-003 PROPOSED AND NOT AUTHORIZED"),
        ("- Current issued Work Order: WO-003", "WO-003 ISSUED"),
    )
    _assert_reconstructed(
        "WO-003 proposed reconstruction",
        proposed.read_text(encoding="utf-8"),
        ("STATUS: PROPOSED", "AUTHORIZATION: NOT AUTHORIZED"),
        ("STATUS: ISSUED", "## Issuance basis"),
    )
    return case


def _make_wo002_session_b_case(repo_root, tmp_path, name):
    """Reconstruct the authorized Session B state from the completed state.

    Completing WO-002 moved the current state forward again, so every earlier
    stage is now a reconstruction rooted here.
    """
    case = _make_wo002_completed_case(repo_root, tmp_path, name)
    completed = (case / "docs" / "work-orders" / "completed"
                 / "WO-002-epic-toolset-integration.md")
    issued = case / _ISSUED_REL
    assert completed.exists(), "WO-002 is not in completed/ to reconstruct from"
    completed.replace(issued)

    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    for _old, _new in (
        ("- Current issued Work Order: NONE", "- Current issued Work Order: WO-002"),
        ("- Authorized session: NONE", "- Authorized session: B"),
        (
            "- Base commit: `c031f20e33c716ecc9f9ce546a7419b865ed8641`",
            "- Base commit: `d1a2c810126ba6c9e14891da1b25cb198c1d45c7`",
        ),
        (
            "- Current gate: WO-002 COMPLETED " + _EM
            + " WO-003 PROPOSED AND NOT AUTHORIZED",
            "- Current gate: WO-002 SESSION B AUTHORIZED " + _EM
            + " EXECUTE EXTERNAL PROOF ONLY",
        ),
        (
            "](docs/work-orders/completed/WO-002-epic-toolset-integration.md)",
            "](docs/work-orders/issued/WO-002-epic-toolset-integration.md)",
        ),
        (
            "is completed. Session A was independently accepted",
            "is issued. Session A was independently accepted",
        ),
        (
            "Session B was independently accepted and committed as" + _NL
            + "`c031f20e33c716ecc9f9ce546a7419b865ed8641`; [CI workflow" + _NL
            + "`33133090929`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33133090929)" + _NL
            + "completed successfully, including required job" + _NL
            + "[`98726805137` " + _EM + " Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33133090929/job/98726805137)." + _NL
            + "External official-MCP exposure failed and was accepted as a terminal" + _NL
            + "negative result bounded by ToolsetPolicy. WO-002 is complete; no session" + _NL
            + "is authorized. WO-003 remains proposed and unauthorized.",
            "Session B is authorized for external official-MCP proof only at" + _NL
            + "`d1a2c810126ba6c9e14891da1b25cb198c1d45c7`, after [CI workflow" + _NL
            + "`33047743360`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33047743360)" + _NL
            + "completed successfully, including required job" + _NL
            + "[`98435618996` " + _EM + " Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33047743360/job/98435618996)." + _NL
            + "Session B grants no repair, advertising, commit, push, tag, GitHub Release," + _NL
            + "or publication authority. WO-003 and every later Work Order remain" + _NL
            + "unauthorized.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-002 Session B pointer")
    pointer.write_text(text, encoding="utf-8")

    text = issued.read_text(encoding="utf-8")
    for _old, _new in (
        ("STATUS: COMPLETED", "STATUS: ISSUED"),
        (
            "AUTHORIZATION: COMPLETED " + _EM + " NO SESSION AUTHORIZED",
            "AUTHORIZATION: ISSUED " + _EM
            + " SESSION B AUTHORIZED FOR EXTERNAL PROOF",
        ),
        (
            "NEXT GATE: separate owner authorization for a fresh independent WO-003" + _NL
            + "pre-issuance review, after this completion transition is accepted," + _NL
            + "committed, pushed, and green. Completion of WO-002 does not issue or" + _NL
            + "authorize WO-003, which remains proposed and unauthorized.",
            "NEXT GATE: fresh independent architect review of the complete uncommitted" + _NL
            + "Session B evidence. Session B is proof-only; WO-003 remains unauthorized.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-002 Session B issued document")
    # Literal newlines rather than escapes: the section boundary is structural.
    _require_unique(
        text,
        ("## Session B acceptance and completion record",
         "## Exclusions and deferred work"),
        "WO-002 Session B completion-record excision",
    )
    text = _sub_once(
        _NL + "## Session B acceptance and completion record" + _NL
        + ".*?(?=" + _NL + "## Exclusions and deferred work" + _NL + ")",
        "",
        text,
        "WO-002 Session B completion-record excision",
        flags=re.DOTALL,
    )
    issued.write_text(text, encoding="utf-8")
    _assert_reconstructed(
        "WO-002 Session B pointer",
        pointer.read_text(encoding="utf-8"),
        ("- Authorized session: B", "- Current issued Work Order: WO-002"),
        ("- Authorized session: NONE", "WO-002 COMPLETED"),
    )
    _assert_reconstructed(
        "WO-002 Session B issued document",
        text,
        ("STATUS: ISSUED", "AUTHORIZATION: ISSUED " + _EM
         + " SESSION B AUTHORIZED FOR EXTERNAL PROOF"),
        ("STATUS: COMPLETED", "## Session B acceptance and completion record"),
    )
    return case


def _make_wo002_session_a_accepted_case(repo_root, tmp_path, name):
    """Reconstruct the preserved accepted Session A state from Session B.

    Authorizing Session B moved the current state forward, so the accepted
    state every historical probe builds on is now itself a reconstruction.
    """
    case = _make_wo002_session_b_case(repo_root, tmp_path, name)
    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    for _old, _new in (
        ("- Authorized session: B", "- Authorized session: NONE"),
        (
            "- Base commit: `d1a2c810126ba6c9e14891da1b25cb198c1d45c7`",
            "- Base commit: `50b881716abea3b5838c2a971caac40ee4cd5d30`",
        ),
        (
            "- Current gate: WO-002 SESSION B AUTHORIZED "
            + _EM + " EXECUTE EXTERNAL PROOF ONLY",
            "- Current gate: WO-002 SESSION A ACCEPTED "
            + _EM + " SESSION B NOT AUTHORIZED",
        ),
        (
            _NL + "Session B is authorized for external official-MCP proof only at" + _NL
            + "`d1a2c810126ba6c9e14891da1b25cb198c1d45c7`, after [CI workflow" + _NL
            + "`33047743360`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33047743360)" + _NL
            + "completed successfully, including required job" + _NL
            + "[`98435618996` " + _EM + " Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33047743360/job/98435618996)." + _NL
            + "Session B grants no repair, advertising, commit, push, tag, GitHub Release," + _NL
            + "or publication authority. WO-003 and every later Work Order remain" + _NL
            + "unauthorized." + _NL,
            "",
        ),
    ):
        text = _replace_once(text, _old, _new,
                             "WO-002 accepted Session A pointer")
    pointer.write_text(text, encoding="utf-8")

    issued = case / _ISSUED_REL
    text = issued.read_text(encoding="utf-8")
    for _old, _new in (
        (
            "AUTHORIZATION: ISSUED " + _EM
            + " SESSION B AUTHORIZED FOR EXTERNAL PROOF",
            "AUTHORIZATION: ISSUED " + _EM
            + " SESSION A ACCEPTED; NO SESSION AUTHORIZED",
        ),
        (
            "Session A is accepted and complete. Session B is authorized for external" + _NL
            + "official-MCP proof only and grants no repair authority.",
            "Session A is accepted and complete. No session is currently authorized;" + _NL
            + "Session B requires separate BDFL/owner authorization.",
        ),
        (
            "Session B is authorized for external official-MCP proof only." + _NL + _NL
            + "### Session B authorization basis" + _NL + _NL
            + "The accepted Session A transition was committed as" + _NL
            + "`d1a2c810126ba6c9e14891da1b25cb198c1d45c7`; successful CI workflow" + _NL
            + "`33047743360` included successful required job `98435618996` (`Lint, types," + _NL
            + "tests`)." + _NL
            + "Under the sole current gate in root `WORKORDER.md`, Session B is authorized" + _NL
            + "for external proof only. It grants no repair, advertising, commit, push, tag," + _NL
            + "GitHub Release, repository-metadata, or publication authority. WO-003 and" + _NL
            + "every later Work Order remain unauthorized." + _NL,
            "Session B is not authorized." + _NL,
        ),
        (
            "NEXT GATE: fresh independent architect review of the complete uncommitted" + _NL
            + "Session B evidence. Session B is proof-only; WO-003 remains unauthorized.",
            "NEXT GATE: explicit BDFL/owner authorization for Session B. Session A is" + _NL
            + "accepted and complete; no session is currently authorized.",
        ),
    ):
        text = _replace_once(text, _old, _new,
                             "WO-002 accepted Session A issued document")
    issued.write_text(text, encoding="utf-8")
    _assert_reconstructed(
        "WO-002 accepted Session A pointer",
        pointer.read_text(encoding="utf-8"),
        ("- Authorized session: NONE",
         "- Current gate: WO-002 SESSION A ACCEPTED " + _EM
         + " SESSION B NOT AUTHORIZED"),
        ("- Authorized session: B",
         "SESSION B AUTHORIZED"),
    )
    _assert_reconstructed(
        "WO-002 accepted Session A issued document",
        text,
        ("AUTHORIZATION: ISSUED " + _EM
         + " SESSION A ACCEPTED; NO SESSION AUTHORIZED",
         "## Session A acceptance record"),
        ("### Session B authorization basis",
         "SESSION B AUTHORIZED FOR EXTERNAL PROOF"),
    )
    return case


def _replace_once(text, old, new, where):
    """Replace exactly one occurrence, or fail loudly.

    ``str.replace`` with an absent needle returns the input unchanged and says
    nothing. A historical reconstruction whose anchor has drifted therefore
    rebuilds the *current* state, and every probe built on it passes vacuously
    - the exact failure mode this file exists to reject. A duplicated anchor is
    equally unsafe: a count-limited replace edits one and leaves the other.
    """
    occurrences = text.count(old)
    assert occurrences == 1, (
        where + ": expected exactly 1 occurrence to replace, found "
        + str(occurrences) + " - this reconstruction is no longer anchored to "
        "the recorded historical state: " + repr(old[:90])
    )
    return text.replace(old, new, 1)


def _require_unique(text, headings, where):
    """Every boundary the reconstruction depends on must occur exactly once.

    Counted as exact lines. A non-greedy span between two headings reports one
    match even when a duplicate boundary is swallowed *inside* that match, so
    regex match counts cannot see a duplicated anchor. Newline-framed substring
    counting cannot see one either, because a duplicate at the start of the
    file has no preceding newline and one at EOF has no trailing newline.
    """
    lines = text.splitlines()
    for heading in headings:
        occurrences = lines.count(heading)
        assert occurrences == 1, (
            where + ": boundary " + repr(heading) + " occurs "
            + str(occurrences) + "x, expected exactly 1 - this reconstruction "
            "is no longer anchored to the recorded historical state"
        )


def _sub_once(pattern, repl, text, where, flags=0):
    """``re.subn`` that must match exactly once - see _replace_once."""
    result, count = re.subn(pattern, repl, text, flags=flags)
    assert count == 1, (
        where + ": expected exactly 1 regex match, found " + str(count)
        + " - this reconstruction is no longer anchored: " + pattern
    )
    return result


def _assert_reconstructed(where, text, required, forbidden):
    """A reconstruction must land on the intended state, not merely run.

    Anchored replacement proves each edit fired. It does not prove the edits
    together describe the historical stage the probe claims to test, so the
    end state is asserted directly.
    """
    for needle in required:
        assert needle in text, (
            where + ": reconstruction never reached the intended historical "
            "state - missing " + repr(needle)
        )
    for needle in forbidden:
        assert needle not in text, (
            where + ": reconstruction still carries current-state text "
            + repr(needle)
        )


def _make_wo002_session_a_case(repo_root, tmp_path, name):
    """Reconstruct the preserved authorized Session A state for historical probes."""
    case = _make_wo002_session_a_accepted_case(repo_root, tmp_path, name)
    pointer = case / "WORKORDER.md"
    accepted_pointer_record = (
        "is issued. Session A was independently accepted, committed, and pushed as\n"
        "`50b881716abea3b5838c2a971caac40ee4cd5d30`; [CI workflow\n"
        "`32937631903`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32937631903)\n"
        "completed successfully, including required job\n"
        "[`98081919978` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32937631903/job/98081919978).\n"
        "Session A is accepted and complete."
    )
    text = pointer.read_text(encoding="utf-8")
    for _old, _new in (
        (
            "- Authorized session: NONE",
            "- Authorized session: A",
        ),
        (
            "- Base commit: `50b881716abea3b5838c2a971caac40ee4cd5d30`",
            "- Base commit: `d87572e2a272c98f8dd634cfe17ff8a130446a7b`",
        ),
        (
            "- Current gate: WO-002 SESSION A ACCEPTED — SESSION B NOT AUTHORIZED",
            "- Current gate: WO-002 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY",
        ),
        (
            accepted_pointer_record,
            "is issued. Session A is authorized for implementation under this root gate;\n"
            "Session B remains unauthorized.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-002 authorized Session A pointer")
    pointer.write_text(text, encoding="utf-8")
    issued = (
        case / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    text = issued.read_text(encoding="utf-8")
    _require_unique(
        text,
        ("## Session A acceptance record",
         "## Problem and accepted evidence"),
        "WO-002 authorized Session A acceptance-record excision",
    )
    text = _sub_once(
        r"\n## Session A acceptance record\n.*?(?=\n## Problem and accepted evidence\n)",
        "",
        text,
        "WO-002 authorized Session A acceptance-record excision",
        flags=re.DOTALL,
    )
    for _old, _new in (
        (
            "AUTHORIZATION: ISSUED — SESSION A ACCEPTED; NO SESSION AUTHORIZED",
            "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",
        ),
        (
            "authorized for implementation at this recorded historical stage. Session B\n"
            "remains unauthorized.",
            "authorized for implementation. Session B remains unauthorized.",
        ),
        (
            "Session A is accepted and complete. No session is currently authorized;\n"
            "Session B requires separate BDFL/owner authorization.",
            "Session A is authorized for implementation under the current root\n"
            "`WORKORDER.md` gate. This authorization does not extend to Session B.",
        ),
        (
            "NEXT GATE: explicit BDFL/owner authorization for Session B. Session A is\n"
            "accepted and complete; no session is currently authorized.",
            "NEXT GATE: fresh independent architect review of the complete uncommitted\n"
            "Session A implementation. Session B remains unauthorized.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-002 authorized Session A issued document")
    issued.write_text(text, encoding="utf-8")
    _assert_reconstructed(
        "WO-002 authorized Session A pointer",
        pointer.read_text(encoding="utf-8"),
        ("- Authorized session: A",
         "- Current gate: WO-002 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY"),
        ("- Authorized session: NONE",
         "SESSION A ACCEPTED"),
    )
    _assert_reconstructed(
        "WO-002 authorized Session A issued document",
        text,
        ("AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",),
        ("## Session A acceptance record",
         "SESSION A ACCEPTED"),
    )
    return case

def _make_wo002_issuance_case(repo_root, tmp_path, name):
    """Reconstruct the preserved closed issuance state for historical probes."""
    case = _make_wo002_session_a_case(repo_root, tmp_path, name)
    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    for _old, _new in (
        (
            "- Authorized session: A",
            "- Authorized session: NONE",
        ),
        (
            "- Base commit: `d87572e2a272c98f8dd634cfe17ff8a130446a7b`",
            "- Base commit: `098b38c669dd330cd059ea18dea52cc4e7eaefe2`",
        ),
        (
            "- Current gate: WO-002 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY",
            "- Current gate: WO-002 ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED",
        ),
        (
            "is issued. Session A is authorized for implementation under this root gate;\n"
            "Session B remains unauthorized.",
            "is issued, but issuance grants no implementation authority. Session A and\n"
            "Session B remain unauthorized.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-002 closed issuance pointer")
    pointer.write_text(text, encoding="utf-8")
    issued = (
        case / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    text = issued.read_text(encoding="utf-8")
    authorization_basis = (
        "\n## Session A authorization basis\n\n"
        "The issued Work Order was committed as\n"
        "`d87572e2a272c98f8dd634cfe17ff8a130446a7b`; successful CI workflow\n"
        "`32931353926` included successful required job `98064090312` (`Lint, types,\n"
        "tests`). Under the sole current gate in root `WORKORDER.md`, Session A is\n"
        "authorized for implementation. Session B remains unauthorized.\n"
    )
    for _old, _new in (
        (
            "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",
            "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
        ),
        (
            authorization_basis,
            "",
        ),
        (
            "Session A is authorized for implementation under the current root\n"
            "`WORKORDER.md` gate. This authorization does not extend to Session B.",
            "Session A is not authorized.",
        ),
        (
            "NEXT GATE: fresh independent architect review of the complete uncommitted\n"
            "Session A implementation. Session B remains unauthorized.",
            "NEXT GATE: explicit BDFL/owner authorization for Session A. Issuance alone\n"
            "grants no implementation authority; Session B remains unauthorized.",
        ),
    ):
        text = _replace_once(text, _old, _new, "WO-002 closed issuance issued document")
    issued.write_text(text, encoding="utf-8")
    _assert_reconstructed(
        "WO-002 closed issuance pointer",
        pointer.read_text(encoding="utf-8"),
        ("- Authorized session: NONE",
         "- Current gate: WO-002 ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED"),
        ("- Authorized session: A",
         "SESSION A ACCEPTED"),
    )
    _assert_reconstructed(
        "WO-002 closed issuance issued document",
        text,
        ("AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",),
        ("## Session A authorization basis",
         "## Session A acceptance record"),
    )
    return case


@pytest.mark.parametrize("permission", (
    "Session A is authorized.",
    "Session A is ready to begin.",
    "Session A is permitted to proceed.",
    "Session A is able to begin.",
))
def test_wo002_issuance_rejects_session_a_activation(
    repo_root, tmp_path, monkeypatch, permission
):
    """Issuance alone cannot activate Session A in ordinary language."""
    spec = importlib.util.spec_from_file_location(
        "wo002_closed_session_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    case = _make_wo002_issuance_case(repo_root, tmp_path, "session-a")
    issued = (
        case / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8") + f"\n{permission}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "implicit session authorization" in finding_types


@pytest.mark.parametrize("permission", (
    "Session B is authorized.",
    "Session C is ready to begin.",
    "Session AA may proceed.",
))
def test_wo002_issuance_rejects_later_session_activation(
    repo_root, tmp_path, monkeypatch, permission
):
    """Session B and every later labeled session remain closed at issuance."""
    spec = importlib.util.spec_from_file_location(
        "wo002_later_session_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    case = _make_wo002_issuance_case(repo_root, tmp_path, "later-session")
    issued = (
        case / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8") + f"\n{permission}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "later session authorization" in finding_types


def test_wo002_issuance_contract_rejects_structural_mutations(
    repo_root, tmp_path, monkeypatch
):
    """Pointer, state, marker, train, and publication gates fail closed."""
    spec = importlib.util.spec_from_file_location(
        "wo002_issuance_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    def finding_types(case):
        monkeypatch.setattr(drift_check, "ROOT", str(case))
        return {finding["type"] for finding in drift_check.check_work_order_contract()}

    control = _make_wo002_issuance_case(repo_root, tmp_path, "control")
    assert _without_terminal_lock(finding_types(control)) == set()

    for state in ("proposed", "completed", "superseded"):
        duplicate = _make_wo002_issuance_case(
            repo_root, tmp_path, f"duplicate-{state}"
        )
        shutil.copy2(
            duplicate / "docs" / "work-orders" / "issued"
            / "WO-002-epic-toolset-integration.md",
            duplicate / "docs" / "work-orders" / state
            / "WO-002-epic-toolset-integration.md",
        )
        assert "duplicate work order state" in finding_types(duplicate)

    status = _make_wo002_issuance_case(repo_root, tmp_path, "status")
    issued = (
        status / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8").replace(
            "STATUS: ISSUED", "STATUS: PROPOSED"
        ),
        encoding="utf-8",
    )
    assert "issued status" in finding_types(status)

    authorization = _make_wo002_issuance_case(repo_root, tmp_path, "authorization")
    issued = (
        authorization / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8").replace(
            "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
            "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",
        ),
        encoding="utf-8",
    )
    assert "issued session authorization" in finding_types(authorization)

    pointer_cases = (
        (
            "wrong-pointer",
            "Current issued Work Order: WO-002",
            "Current issued Work Order: WO-003",
            "current issued work order mismatch",
        ),
        (
            "open-session",
            "Authorized session: NONE",
            "Authorized session: A",
            "issued session authorization",
        ),
        (
            "wrong-base",
            "098b38c669dd330cd059ea18dea52cc4e7eaefe2",
            "198b38c669dd330cd059ea18dea52cc4e7eaefe2",
            "issuance base commit",
        ),
        (
            "expanded-train",
            "Release train: WO-001 through WO-007",
            "Release train: WO-001 through WO-008",
            "release train",
        ),
    )
    for name, old, new, expected in pointer_cases:
        case = _make_wo002_issuance_case(repo_root, tmp_path, name)
        pointer = case / "WORKORDER.md"
        pointer.write_text(
            pointer.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        assert expected in finding_types(case)

    release = _make_wo002_issuance_case(repo_root, tmp_path, "release")
    pointer = release / "WORKORDER.md"
    pointer.write_text(
        pointer.read_text(encoding="utf-8")
        + "\nThe next tag and GitHub Release are authorized.\n",
        encoding="utf-8",
    )
    assert "release authorization" in finding_types(release)


@pytest.mark.parametrize(("identifier", "expected"), (
    ("098b38c669dd330cd059ea18dea52cc4e7eaefe2", "issuance baseline"),
    ("32925047925", "issuance workflow"),
    ("98046156859", "issuance job"),
))
def test_wo002_issuance_requires_exact_basis_evidence(
    repo_root, tmp_path, monkeypatch, identifier, expected
):
    """The accepted baseline and successful CI basis remain durable."""
    spec = importlib.util.spec_from_file_location(
        "wo002_evidence_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    case = _make_wo002_issuance_case(repo_root, tmp_path, f"evidence-{expected}")
    issued = (
        case / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8").replace(identifier, "REMOVED"),
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert expected in finding_types


@pytest.mark.parametrize("mutation", ("changed", "duplicated"))
def test_wo002_issuance_requires_exactly_one_canonical_baseline_marker(
    repo_root, tmp_path, monkeypatch, mutation
):
    """Other hash occurrences cannot substitute for the canonical header."""
    spec = importlib.util.spec_from_file_location(
        "wo002_baseline_marker_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    case = _make_wo002_issuance_case(repo_root, tmp_path, f"baseline-{mutation}")
    issued = (
        case / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    marker = "BASELINE: `098b38c669dd330cd059ea18dea52cc4e7eaefe2`"
    text = issued.read_text(encoding="utf-8")
    if mutation == "changed":
        text = text.replace(
            marker,
            "BASELINE: `198b38c669dd330cd059ea18dea52cc4e7eaefe2`",
            1,
        )
    else:
        text += f"\n{marker}\n"
    issued.write_text(text, encoding="utf-8")
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "issuance baseline marker" in finding_types


def test_wo002_session_a_authorization_contract_is_exact(
    repo_root, tmp_path, monkeypatch
):
    """The current gate opens only Session A and preserves all issuance evidence."""
    spec = importlib.util.spec_from_file_location(
        "wo002_session_a_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    def finding_types(case):
        monkeypatch.setattr(drift_check, "ROOT", str(case))
        return {finding["type"] for finding in drift_check.check_work_order_contract()}

    control = _make_wo002_session_a_case(repo_root, tmp_path, "session-a-control")
    assert _without_terminal_lock(finding_types(control)) == set()

    pointer_mutations = (
        (
            "session",
            "- Authorized session: A",
            "- Authorized session: NONE",
            "issued session authorization",
        ),
        (
            "base",
            "d87572e2a272c98f8dd634cfe17ff8a130446a7b",
            "e87572e2a272c98f8dd634cfe17ff8a130446a7b",
            "Session A base commit",
        ),
        (
            "gate",
            "WO-002 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY",
            "WO-002 SESSION A AUTHORIZED — IMPLEMENT ALL SESSIONS",
            "authorized session gate",
        ),
    )
    for name, old, new, expected in pointer_mutations:
        case = _make_wo002_session_a_case(repo_root, tmp_path, f"session-a-{name}")
        pointer = case / "WORKORDER.md"
        pointer.write_text(
            pointer.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        assert expected in finding_types(case)

    issued_path = (
        "docs/work-orders/issued/WO-002-epic-toolset-integration.md"
    )
    evidence_cases = (
        ("commit", "d87572e2a272c98f8dd634cfe17ff8a130446a7b",
         "Session A authorization commit"),
        ("workflow", "32931353926", "Session A authorization workflow"),
        ("job", "98064090312", "Session A authorization job"),
    )
    for name, evidence, expected in evidence_cases:
        case = _make_wo002_session_a_case(repo_root, tmp_path, f"session-a-{name}")
        issued = case / issued_path
        issued.write_text(
            issued.read_text(encoding="utf-8").replace(evidence, "REMOVED"),
            encoding="utf-8",
        )
        assert expected in finding_types(case)

    later = _make_wo002_session_a_case(repo_root, tmp_path, "session-b-open")
    issued = later / issued_path
    issued.write_text(
        issued.read_text(encoding="utf-8") + "\nSession B may now begin.\n",
        encoding="utf-8",
    )
    assert "later session authorization" in finding_types(later)


def test_wo002_session_a_acceptance_contract_is_exact(
    repo_root, tmp_path, monkeypatch
):
    """Accepted Session A closes implementation while preserving exact evidence."""
    spec = importlib.util.spec_from_file_location(
        "wo002_session_a_accepted_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    def finding_types(case):
        monkeypatch.setattr(drift_check, "ROOT", str(case))
        return {finding["type"] for finding in drift_check.check_work_order_contract()}

    control = _make_wo002_session_a_accepted_case(
        repo_root, tmp_path, "session-a-accepted-control"
    )
    assert _without_terminal_lock(finding_types(control)) == set()

    pointer_mutations = (
        (
            "authorized-session",
            "- Authorized session: NONE",
            "- Authorized session: A",
            "issued session authorization",
        ),
        (
            "accepted-gate",
            "WO-002 SESSION A ACCEPTED — SESSION B NOT AUTHORIZED",
            "WO-002 SESSION A ACCEPTED — SESSION B MAY BEGIN",
            "Session A accepted gate",
        ),
        (
            "stale-pointer",
            "- Current issued Work Order: WO-002",
            "- Current issued Work Order: WO-003",
            "current issued work order mismatch",
        ),
        (
            "stale-base",
            "- Base commit: `50b881716abea3b5838c2a971caac40ee4cd5d30`",
            "- Base commit: `60b881716abea3b5838c2a971caac40ee4cd5d30`",
            "Session A accepted base commit",
        ),
        (
            "expanded-train",
            "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-008",
            "release train",
        ),
    )
    for name, old, new, expected in pointer_mutations:
        case = _make_wo002_session_a_accepted_case(
            repo_root, tmp_path, f"session-a-accepted-{name}"
        )
        pointer = case / "WORKORDER.md"
        pointer.write_text(
            pointer.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        assert expected in finding_types(case)

    issued_path = (
        "docs/work-orders/issued/WO-002-epic-toolset-integration.md"
    )
    marker = _make_wo002_session_a_accepted_case(
        repo_root, tmp_path, "session-a-accepted-marker"
    )
    issued = marker / issued_path
    issued.write_text(
        issued.read_text(encoding="utf-8").replace(
            "AUTHORIZATION: ISSUED — SESSION A ACCEPTED; NO SESSION AUTHORIZED",
            "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",
        ),
        encoding="utf-8",
    )
    assert "Session A accepted authorization" in finding_types(marker)

    evidence_cases = (
        (
            "commit",
            "50b881716abea3b5838c2a971caac40ee4cd5d30",
            "Session A accepted commit",
        ),
        ("workflow", "32937631903", "Session A accepted workflow"),
        ("job", "98081919978", "Session A accepted job"),
    )
    for name, evidence, expected in evidence_cases:
        case = _make_wo002_session_a_accepted_case(
            repo_root, tmp_path, f"session-a-accepted-{name}"
        )
        issued = case / issued_path
        issued.write_text(
            issued.read_text(encoding="utf-8").replace(evidence, "REMOVED"),
            encoding="utf-8",
        )
        assert expected in finding_types(case)

    reopened = _make_wo002_session_a_accepted_case(
        repo_root, tmp_path, "session-a-reopened"
    )
    issued = reopened / issued_path
    issued.write_text(
        issued.read_text(encoding="utf-8")
        + "\nSession A is currently authorized for implementation.\n",
        encoding="utf-8",
    )
    assert "session authorization reopening" in finding_types(reopened)

    release = _make_wo002_session_a_accepted_case(
        repo_root, tmp_path, "session-a-accepted-release"
    )
    pointer = release / "WORKORDER.md"
    pointer.write_text(
        pointer.read_text(encoding="utf-8")
        + "\nThe next tag and GitHub Release are authorized.\n",
        encoding="utf-8",
    )
    assert "release authorization" in finding_types(release)


@pytest.mark.parametrize("permission", (
    "Session B is authorized.",
    "Session B is ready to begin.",
    "Session B is permitted to proceed.",
    "Session B is able to begin.",
))
def test_wo002_session_a_acceptance_rejects_session_b_activation(
    repo_root, tmp_path, monkeypatch, permission
):
    """Accepted Session A does not implicitly activate Session B."""
    spec = importlib.util.spec_from_file_location(
        "wo002_session_b_closed_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    case = _make_wo002_session_a_accepted_case(
        repo_root, tmp_path, "session-b-closed"
    )
    issued = (
        case / "docs" / "work-orders" / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8") + f"\n{permission}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "session authorization reopening" in finding_types


_ACCEPTED_COMMIT = "50b881716abea3b5838c2a971caac40ee4cd5d30"
_ACCEPTED_WORKFLOW = "32937631903"
_ACCEPTED_JOB = "98081919978"
_ISSUED_REL = "docs/work-orders/issued/WO-002-epic-toolset-integration.md"
_TERMINAL_WO002_FINDING = "completed WO-002 state"
_TERMINAL_WO003_FINDING = "accepted WO-003 Session B state"


def _without_terminal_lock(finding_types):
    """Set aside one-way state locks for historical reconstructions.

    WO-002 completion is one-way, so every pre-completion state a fixture
    rebuilds necessarily trips it. Their narrower legacy contracts are still
    asserted in full; only this one expected finding is subtracted.
    """
    return set(finding_types) - {
        _TERMINAL_WO002_FINDING,
        _TERMINAL_WO003_FINDING,
    }


_RECONSTRUCTION_FAILURE = (
    "no longer anchored|never reached the intended historical state"
)
_COMPLETED_REL = (
    "docs/work-orders/completed/WO-002-epic-toolset-integration.md"
)
_NL = chr(10)
_EM = chr(8212)
_WRONG_COMMIT = "60b881716abea3b5838c2a971caac40ee4cd5d30"
_WRONG_WORKFLOW = "42937631903"
_WRONG_JOB = "98081919979"
_JOB_SUFFIX = "` — Lint, types, tests]"
_POINTER_FINDING = "Session A acceptance record (WORKORDER.md)"
_ISSUED_FINDING = "Session A acceptance record (issued WO-002)"

# Each case alters exactly ONE occurrence. `surviving` names an identifier that
# is still correct elsewhere in the same file afterwards - that is precisely the
# state a presence-only membership test accepted.
_ACCEPTANCE_OCCURRENCE_MUTATIONS = (
    ("pointer-narrative-commit", "WORKORDER.md",
     "pushed as" + _NL + "`" + _ACCEPTED_COMMIT + "`;",
     "pushed as" + _NL + "`" + _WRONG_COMMIT + "`;",
     None, _POINTER_FINDING),
    ("pointer-workflow-label", "WORKORDER.md",
     "[CI workflow" + _NL + "`" + _ACCEPTED_WORKFLOW + "`]",
     "[CI workflow" + _NL + "`" + _WRONG_WORKFLOW + "`]",
     _ACCEPTED_WORKFLOW, _POINTER_FINDING),
    ("pointer-workflow-url", "WORKORDER.md",
     "runs/" + _ACCEPTED_WORKFLOW + ")", "runs/" + _WRONG_WORKFLOW + ")",
     _ACCEPTED_WORKFLOW, _POINTER_FINDING),
    ("pointer-job-label", "WORKORDER.md",
     "[`" + _ACCEPTED_JOB + _JOB_SUFFIX, "[`" + _WRONG_JOB + _JOB_SUFFIX,
     _ACCEPTED_JOB, _POINTER_FINDING),
    ("pointer-job-url", "WORKORDER.md",
     "/job/" + _ACCEPTED_JOB + ")", "/job/" + _WRONG_JOB + ")",
     _ACCEPTED_JOB, _POINTER_FINDING),
    ("issued-acceptance-commit", _COMPLETED_REL,
     "accepted and committed as" + _NL + "`" + _ACCEPTED_COMMIT + "`.",
     "accepted and committed as" + _NL + "`" + _WRONG_COMMIT + "`.",
     None, _ISSUED_FINDING),
    ("issued-workflow-label", _COMPLETED_REL,
     "[`" + _ACCEPTED_WORKFLOW + "`](", "[`" + _WRONG_WORKFLOW + "`](",
     _ACCEPTED_WORKFLOW, _ISSUED_FINDING),
    ("issued-workflow-url", _COMPLETED_REL,
     "runs/" + _ACCEPTED_WORKFLOW + ")", "runs/" + _WRONG_WORKFLOW + ")",
     _ACCEPTED_WORKFLOW, _ISSUED_FINDING),
    ("issued-job-label", _COMPLETED_REL,
     "[`" + _ACCEPTED_JOB + _JOB_SUFFIX, "[`" + _WRONG_JOB + _JOB_SUFFIX,
     _ACCEPTED_JOB, _ISSUED_FINDING),
    ("issued-job-url", _COMPLETED_REL,
     "/job/" + _ACCEPTED_JOB + ")", "/job/" + _WRONG_JOB + ")",
     _ACCEPTED_JOB, _ISSUED_FINDING),
)


def _load_drift_check(repo_root, label):
    spec = importlib.util.spec_from_file_location(
        label, repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "name,rel,old,new,surviving,expected", _ACCEPTANCE_OCCURRENCE_MUTATIONS
)
def test_wo002_acceptance_evidence_is_enforced_per_occurrence(
    repo_root, tmp_path, monkeypatch, name, rel, old, new, surviving, expected
):
    """Every visible label, URL, and narrative value is pinned individually.

    Membership testing cannot enforce this record. Each identifier occurs two
    or three times per surface - visible label, run URL, job URL, and in
    WORKORDER.md the separate Base commit marker - so one occurrence could
    diverge while another kept the containment test satisfied. The root Base
    commit marker in particular must not stand in for the acceptance-record
    commit.
    """
    drift_check = _load_drift_check(repo_root, "wo002_occurrence_" + name)
    case = _make_wo002_completed_case(
        repo_root, tmp_path, "acceptance-occurrence-" + name
    )
    target = case / rel
    text = target.read_text(encoding="utf-8")
    assert old in text, (
        "mutation needle absent - this case no longer alters " + name
        + " and would pass vacuously: " + repr(old)
    )
    mutated = text.replace(old, new, 1)
    if surviving is not None:
        assert surviving in mutated, (
            "mutation removed every occurrence, so it no longer reproduces the "
            "state presence-only enforcement accepted"
        )
    target.write_text(mutated, encoding="utf-8")

    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert expected in finding_types


def test_wo002_acceptance_evidence_control_is_clean(repo_root, tmp_path, monkeypatch):
    """The unchanged canonical acceptance state produces no findings."""
    drift_check = _load_drift_check(repo_root, "wo002_occurrence_control")
    case = _make_wo002_completed_case(
        repo_root, tmp_path, "acceptance-occurrence-control"
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    found = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert found == {_TERMINAL_WO003_FINDING}


# --- Structurally anchored acceptance records -------------------------------
#
# Presence-only enforcement asks whether a correct fragment occurs *somewhere*
# in the document. That is defeated by a decoy: corrupt the genuine occurrence,
# then reinstate a correct copy elsewhere - even inside an HTML comment.
#
# Bounding the record by markers taken from its own prose is also not enough.
# Those markers travel with the content, so a transplant defeats them: corrupt
# the genuine record together with its markers, paste a byte-correct copy
# anywhere else, and a marker search selects the transplant and passes.
#
# The record is therefore located by neighbouring structure that is not part of
# it, and the block at that anchored position must match. These probes hold
# both lines: decoys and transplants.

_WO001_LINK = "](docs/work-orders/completed/WO-001-custom-mcp-security.md)"
_WO002_LINK = (
    "](docs/work-orders/completed/WO-002-epic-toolset-integration.md)"
)
_ACCEPTANCE_HEADING = "## Session A acceptance record"
_FOLLOWING_HEADING = "## Problem and accepted evidence"
_ACCEPTANCE_SURFACES = {
    "pointer": ("WORKORDER.md", _POINTER_FINDING),
    "issued": (_COMPLETED_REL, _ISSUED_FINDING),
}


def _record_text(text, surface):
    """The canonical record, located exactly as the checker locates it.

    Deliberately a second, independent implementation: a probe that reused the
    checker's own locator could not tell a correct anchor from a broken one.
    """
    if surface == "pointer":
        chunks = text.split(_NL + _NL)
        anchors = [i for i, chunk in enumerate(chunks) if _WO001_LINK in chunk]
        assert len(anchors) == 1, "probe cannot find a unique WO-001 paragraph"
        record = chunks[anchors[0] + 1]
        assert _WO002_LINK in record, "probe located the wrong paragraph"
    else:
        lines = text.split(_NL)
        marks = [i for i, line in enumerate(lines) if line.startswith("## ")]
        headings = [lines[i] for i in marks]
        first = marks[headings.index(_ACCEPTANCE_HEADING)]
        last = marks[headings.index(_FOLLOWING_HEADING)]
        assert first < last, "probe headings are out of order"
        record = _NL.join(lines[first:last]).rstrip(_NL)
    assert text.count(record) == 1, "the canonical record is not unique"
    return record


def _decoy_of(record, surface):
    """A correct copy that restores every pinned fragment.

    The structural anchor is stripped so the region stays unambiguously
    located: this probe must be caught by comparing the anchored block, not by
    tripping an anchor-uniqueness check.
    """
    body = " ".join(record.split())
    body = body.replace(_WO002_LINK, "](issued-work-order)")
    body = body.replace(" ".join(_ACCEPTANCE_HEADING.split()), "")
    return "<!-- " + " ".join(body.split()) + " -->"


def _decoyed(text, surface, placement):
    """Corrupt the genuine record, then reinstate a correct copy as a decoy."""
    record = _record_text(text, surface)
    corrupted = record.replace(_ACCEPTED_WORKFLOW, _WRONG_WORKFLOW)
    assert corrupted != record, (
        "this probe no longer corrupts the canonical record and would pass "
        "vacuously"
    )
    decoy = _decoy_of(record, surface)
    if placement == "outside":
        return text.replace(record, corrupted, 1) + _NL + _NL + decoy + _NL
    head, _, tail = corrupted.partition(_NL)
    return text.replace(record, head + _NL + decoy + _NL + tail, 1)


def _transplanted(text, surface, variant):
    """Corrupt the genuine record *and its markers*; paste a true copy elsewhere.

    This is the attack that marker-bounded enforcement cannot see: after the
    mutation exactly one correctly ordered marker pair remains in the file, and
    the block between those markers is byte-correct - it is simply no longer
    where the record belongs.
    """
    record = _record_text(text, surface)
    if surface == "pointer":
        junk = (
            record.replace("Session A was independently accepted",
                           "Session A was quietly waved through")
            .replace("separate BDFL/owner authorization.",
                     "no further authorization is needed.")
            .replace(_ACCEPTED_WORKFLOW, _WRONG_WORKFLOW)
        )
        if variant == "unanchored":
            junk = junk.replace(_WO002_LINK, "](issued-work-order)")
        return text.replace(record, junk, 1) + _NL + _NL + record + _NL
    junk = (
        record.replace(_ACCEPTANCE_HEADING, "## Session A acceptance note")
        .replace(_ACCEPTED_WORKFLOW, _WRONG_WORKFLOW)
    )
    mutated = text.replace(record, junk, 1)
    if variant == "anchored":
        # Paste the true record ahead of the next heading, so a marker search
        # still finds one correctly ordered pair around byte-correct text.
        return mutated.replace(
            _FOLLOWING_HEADING, record + _NL + _NL + _FOLLOWING_HEADING, 1
        )
    # Or drop the heading altogether and re-home the record after the section
    # it belongs before, which no marker pair can distinguish from the truth.
    mutated = mutated.replace(
        "## Session A acceptance note", "Session A acceptance note", 1
    )
    return mutated.replace(
        _FOLLOWING_HEADING, _FOLLOWING_HEADING + _NL + _NL + record, 1
    )


def _damaged_anchor(text, surface, damage):
    """Make the anchoring structure ambiguous rather than the record wrong."""
    if damage == "displace_record":
        chunks = text.split(_NL + _NL)
        anchors = [i for i, chunk in enumerate(chunks) if _WO001_LINK in chunk]
        assert len(anchors) == 1
        chunks.insert(anchors[0] + 1, "An unrelated note about the release train.")
        return (_NL + _NL).join(chunks)
    if damage == "duplicate_wo001_link":
        return text + _NL + _NL + "See also [WO-001](" + _WO001_LINK[2:] + _NL
    if damage == "duplicate_issued_link":
        return text + _NL + _NL + "See also [WO-002](" + _WO002_LINK[2:] + _NL
    if damage == "duplicate_heading":
        return text + _NL + _ACCEPTANCE_HEADING + _NL
    if damage == "reorder_headings":
        lines = text.split(_NL)
        marks = [i for i, line in enumerate(lines) if line.startswith("## ")]
        headings = [lines[i] for i in marks]
        first = marks[headings.index(_ACCEPTANCE_HEADING)]
        last = marks[headings.index(_FOLLOWING_HEADING)]
        lines[first], lines[last] = lines[last], lines[first]
        return _NL.join(lines)
    raise AssertionError("unknown anchor damage: " + damage)


def _pinned_fragments(drift_check, surface):
    """The evidence tuples the checker pins for one surface."""
    return (
        drift_check._WO002_ACCEPTED_POINTER_EVIDENCE
        if surface == "pointer"
        else drift_check._WO002_ACCEPTED_ISSUED_EVIDENCE
    )


def _acceptance_findings(drift_check, monkeypatch, case, finding_type):
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return [
        finding
        for finding in drift_check.check_work_order_contract()
        if finding["type"] == finding_type
    ]


@pytest.mark.parametrize("placement", ("outside", "inside"))
@pytest.mark.parametrize("surface", ("pointer", "issued"))
def test_wo002_acceptance_record_rejects_correct_decoys(
    repo_root, tmp_path, monkeypatch, surface, placement
):
    """A correct copy elsewhere does not repair a corrupted record."""
    rel, finding_type = _ACCEPTANCE_SURFACES[surface]
    drift_check = _load_drift_check(
        repo_root, "wo002_decoy_" + surface + "_" + placement
    )
    case = _make_wo002_completed_case(
        repo_root, tmp_path, "acceptance-decoy-" + surface + "-" + placement
    )
    target = case / rel
    mutated = _decoyed(target.read_text(encoding="utf-8"), surface, placement)
    target.write_text(mutated, encoding="utf-8")

    normalized = " ".join(mutated.split())
    for label, fragment in _pinned_fragments(drift_check, surface):
        assert fragment in normalized, (
            "the decoy no longer restores " + label + ", so this probe does "
            "not reproduce the state presence-only enforcement accepted"
        )
    assert _WRONG_WORKFLOW in mutated, "the genuine occurrence was not corrupted"
    assert _acceptance_findings(drift_check, monkeypatch, case, finding_type), (
        surface + " " + placement
        + " decoy was accepted - the canonical record is not bounded"
    )


@pytest.mark.parametrize("variant", ("anchored", "unanchored"))
@pytest.mark.parametrize("surface", ("pointer", "issued"))
def test_wo002_acceptance_record_rejects_transplants(
    repo_root, tmp_path, monkeypatch, surface, variant
):
    """Moving the true record elsewhere does not satisfy the anchored position.

    Marker-bounded enforcement passes this: the surviving marker pair is
    unique and correctly ordered, and the text between it is byte-correct. Only
    an anchor outside the protected record notices that the position where the
    acceptance record belongs now holds corrupted text.
    """
    rel, finding_type = _ACCEPTANCE_SURFACES[surface]
    drift_check = _load_drift_check(
        repo_root, "wo002_transplant_" + surface + "_" + variant
    )
    case = _make_wo002_completed_case(
        repo_root, tmp_path, "acceptance-transplant-" + surface + "-" + variant
    )
    target = case / rel
    original = target.read_text(encoding="utf-8")
    record = _record_text(original, surface)
    mutated = _transplanted(original, surface, variant)
    target.write_text(mutated, encoding="utf-8")

    assert record in mutated, (
        "the transplanted copy is missing, so this probe no longer reproduces "
        "the attack marker-bounded enforcement accepted"
    )
    assert _WRONG_WORKFLOW in mutated, "the genuine record was not corrupted"
    assert _acceptance_findings(drift_check, monkeypatch, case, finding_type), (
        surface + " " + variant + " transplant was accepted - the record is "
        "still located by markers that travel with it"
    )


@pytest.mark.parametrize(("surface", "damage"), (
    ("pointer", "displace_record"),
    ("pointer", "duplicate_wo001_link"),
    ("pointer", "duplicate_issued_link"),
    ("issued", "duplicate_heading"),
    ("issued", "reorder_headings"),
))
def test_wo002_acceptance_record_requires_unambiguous_anchors(
    repo_root, tmp_path, monkeypatch, surface, damage
):
    """An ambiguous anchor is a failure, never a licence to skip the check."""
    rel, finding_type = _ACCEPTANCE_SURFACES[surface]
    drift_check = _load_drift_check(
        repo_root, "wo002_anchor_" + surface + "_" + damage
    )
    case = _make_wo002_completed_case(
        repo_root, tmp_path, "acceptance-anchor-" + surface + "-" + damage
    )
    target = case / rel
    original = target.read_text(encoding="utf-8")
    target.write_text(_damaged_anchor(original, surface, damage), encoding="utf-8")

    findings = _acceptance_findings(drift_check, monkeypatch, case, finding_type)
    assert findings, surface + " " + damage + " left the record unenforced"
    assert any("canonical acceptance region" in f["found"] for f in findings), (
        "anchor damage must be reported as a region failure, not guessed past"
    )


def test_wo002_acceptance_record_control_is_clean(repo_root, tmp_path, monkeypatch):
    """The unmutated tree produces no acceptance-record finding."""
    drift_check = _load_drift_check(repo_root, "wo002_region_control")
    case = _make_wo002_completed_case(
        repo_root, tmp_path, "acceptance-region-control"
    )
    for finding_type in (_POINTER_FINDING, _ISSUED_FINDING):
        assert not _acceptance_findings(
            drift_check, monkeypatch, case, finding_type
        ), finding_type + " fires on the unmodified repository"


def test_wo002_acceptance_record_ignores_unrelated_wo001_rewording(
    repo_root, tmp_path, monkeypatch
):
    """WO-001 supplies position, never pinned wording.

    The anchor is WO-001's completion *reference*, so rewording the sentence
    around it must not surface as a WO-002 acceptance-evidence finding.
    """
    drift_check = _load_drift_check(repo_root, "wo002_wo001_rewording")
    case = _make_wo002_completed_case(
        repo_root, tmp_path, "acceptance-wo001-rewording"
    )
    pointer = case / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    assert "is completed as" in text, "this control's own anchor has drifted"
    pointer.write_text(
        text.replace("is completed as", "was completed as", 1), encoding="utf-8"
    )

    for finding_type in (_POINTER_FINDING, _ISSUED_FINDING):
        assert not _acceptance_findings(
            drift_check, monkeypatch, case, finding_type
        ), "a WO-001-only rewording produced " + finding_type


def test_wo002_acceptance_record_ignores_unrelated_issued_heading(
    repo_root, tmp_path, monkeypatch
):
    """Only the acceptance section's own boundaries are frozen.

    An unrelated future heading elsewhere in the issued Work Order is none of
    this check's business, so adding one must stay silent.
    """
    drift_check = _load_drift_check(repo_root, "wo002_unrelated_heading")
    case = _make_wo002_completed_case(
        repo_root, tmp_path, "acceptance-unrelated-heading"
    )
    issued = case / _COMPLETED_REL
    issued.write_text(
        issued.read_text(encoding="utf-8") + _NL
        + "## Later operational notes" + _NL + _NL
        + "Added by some unrelated future Work Order edit." + _NL,
        encoding="utf-8",
    )

    for finding_type in (_POINTER_FINDING, _ISSUED_FINDING):
        assert not _acceptance_findings(
            drift_check, monkeypatch, case, finding_type
        ), "an unrelated heading produced " + finding_type


@pytest.mark.parametrize("heading", (_ACCEPTANCE_HEADING, _FOLLOWING_HEADING))
@pytest.mark.parametrize(
    "damage", ("duplicate_middle", "duplicate_start", "duplicate_eof", "remove")
)
def test_wo002_historical_reconstruction_requires_unique_boundaries(
    repo_root, tmp_path, damage, heading
):
    """A duplicated boundary heading is invisible to the excision regex.

    The span between the two headings is non-greedy, so a second copy of either
    heading inside that span is swallowed and still reports one match. Framing
    the count with newlines does not fix it either: a duplicate at the start of
    the file has no preceding newline, and one at EOF has no trailing newline.
    The boundaries are counted as exact lines instead.
    """
    tag = "acceptance" if heading == _ACCEPTANCE_HEADING else "following"
    drifted = _make_wo003_issued_case(
        repo_root, tmp_path, "boundary-" + damage + "-" + tag
    )
    issued = drifted / _COMPLETED_REL
    text = issued.read_text(encoding="utf-8")
    assert text.splitlines().count(heading) == 1, "this probe's anchor has drifted"

    if damage == "duplicate_middle":
        mutated = text.replace(
            _NL + heading + _NL, _NL + heading + _NL + _NL + heading + _NL, 1
        )
    elif damage == "duplicate_start":
        mutated = heading + _NL + text
    elif damage == "duplicate_eof":
        mutated = text.rstrip(_NL) + _NL + heading
    else:
        mutated = text.replace(_NL + heading + _NL, _NL + heading + " note" + _NL, 1)

    if damage == "remove":
        assert heading not in mutated.splitlines(), "the boundary was not removed"
    else:
        assert mutated.splitlines().count(heading) == 2, "the probe added no duplicate"
    if damage in ("duplicate_start", "duplicate_eof"):
        # Non-vacuous: newline-framed counting still reports a single boundary,
        # which is exactly the blindness this probe exists to reject.
        assert mutated.count(_NL + heading + _NL) == 1, (
            "this probe no longer reproduces the file-boundary blind spot"
        )
    issued.write_text(mutated, encoding="utf-8")

    with pytest.raises(AssertionError, match=_RECONSTRUCTION_FAILURE):
        _make_wo002_session_a_case(
            drifted, tmp_path, "boundary-case-" + damage + "-" + tag
        )


def test_wo002_historical_reconstruction_requires_pointer_anchor(
    repo_root, tmp_path
):
    """A drifted pointer anchor must fail loudly, not rebuild today's state."""
    drifted = _make_wo003_issued_case(
        repo_root, tmp_path, "drifted-pointer-anchor"
    )
    pointer = drifted / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    anchor = "- Authorized session: NONE"
    assert anchor in text, "this probe's own anchor has drifted"
    pointer.write_text(
        text.replace(anchor, "- Authorized session: none", 1), encoding="utf-8"
    )

    with pytest.raises(AssertionError, match=_RECONSTRUCTION_FAILURE):
        _make_wo002_session_a_case(drifted, tmp_path, "drifted-pointer-case")


def test_wo002_historical_reconstruction_requires_issued_anchor(
    repo_root, tmp_path
):
    """Likewise for the acceptance-record excision the issued probe depends on."""
    drifted = _make_wo003_issued_case(
        repo_root, tmp_path, "drifted-issued-anchor"
    )
    issued = drifted / _COMPLETED_REL
    text = issued.read_text(encoding="utf-8")
    anchor = "## Session A acceptance record"
    assert anchor in text, "this probe's own anchor has drifted"
    issued.write_text(
        text.replace(anchor, "## Session A acceptance note", 1), encoding="utf-8"
    )

    with pytest.raises(AssertionError, match=_RECONSTRUCTION_FAILURE):
        _make_wo002_session_a_case(drifted, tmp_path, "drifted-issued-case")


def test_wo002_historical_reconstructions_reach_their_intended_states(
    repo_root, tmp_path
):
    """Both reconstructions still describe the stage their probes claim.

    Anchored replacement proves each edit fired; this proves the edits together
    land on the authorized-Session-A and closed-issuance states rather than on
    some third thing, and that neither still carries the accepted record.
    """
    authorized = _make_wo002_session_a_case(repo_root, tmp_path, "state-authorized")
    issuance = _make_wo002_issuance_case(repo_root, tmp_path, "state-issuance")
    for case, gate in (
        (authorized, "WO-002 SESSION A AUTHORIZED"),
        (issuance, "WO-002 ISSUED"),
    ):
        pointer = (case / "WORKORDER.md").read_text(encoding="utf-8")
        issued = (case / _ISSUED_REL).read_text(encoding="utf-8")
        assert gate in pointer, case.name + ": pointer gate is not " + gate
        assert "## Session A acceptance record" not in issued, (
            case.name + ": the accepted record survived a historical "
            "reconstruction, so the probe is testing today's state"
        )
        assert _ACCEPTED_COMMIT not in issued, (
            case.name + ": the accepted base commit survived reconstruction"
        )


def _make_completed_work_order_case(repo_root, tmp_path, name):
    """Copy the current terminal WO-001 state for real-checker mutations."""
    case = _make_wo002_issuance_case(repo_root, tmp_path, name)
    (case / "WORKORDER.md").write_text(
        "# Current Work Order Gate\n\n"
        "This file is the repository's sole authority pointer for current Work Order\n"
        "state. Detailed mandates live under `docs/work-orders/`; their presence alone\n"
        "never authorizes implementation.\n\n"
        "- Current issued Work Order: NONE\n"
        "- Authorized session: NONE\n"
        "- Base commit: `ffcbe8b1bfa03cb37453b9beefda0bbdbe45543c`\n"
        "- Current gate: WO-001 COMPLETED — WO-002 PROPOSED AND NOT AUTHORIZED\n"
        "- Release train: WO-001 through WO-007\n"
        "- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED — COMPLETE THE FROZEN "
        "TRAIN AND FINAL INTEGRATION/REPOSITORY-TRUTH AUDIT FIRST\n\n"
        "[`WO-001-custom-mcp-security.md`](docs/work-orders/completed/"
        "WO-001-custom-mcp-security.md) is completed as "
        "`ffcbe8b1bfa03cb37453b9beefda0bbdbe45543c` after CI workflow "
        "`32921154482` passed. "
        "[`WO-002`](docs/work-orders/proposed/WO-002-epic-toolset-integration.md) "
        "is the next proposal only; it is not issued and no implementation session "
        "is authorized.\n\n"
        "WO-001 through WO-007 form the frozen next release train. The release "
        "version remains undecided and the repository stays at version 2.4.1. No "
        "tag or GitHub Release is authorized until the frozen train is complete, a "
        "final integration/repository-truth audit passes, and the owner separately "
        "authorizes a release session. New proposals default to the following "
        "release train unless the owner explicitly classifies one as a blocker.\n",
        encoding="utf-8",
    )
    issued = (
        case
        / "docs"
        / "work-orders"
        / "issued"
        / "WO-002-epic-toolset-integration.md"
    )
    proposal = issued.parent.parent / "proposed" / issued.name
    issued.replace(proposal)
    proposal.write_text(
        proposal.read_text(encoding="utf-8")
        .replace("STATUS: ISSUED", "STATUS: PROPOSED")
        .replace(
            "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
            "AUTHORIZATION: NOT AUTHORIZED",
        )
        .replace(
            "## Session A — internal contract and truth correction",
            "## Proposed Session A — internal contract and truth correction",
        )
        .replace(
            "## Session B — external official-MCP proof",
            "## Proposed Session B — external official-MCP proof",
        )
        .replace(
            "NEXT GATE: explicit BDFL/owner authorization for Session A. Issuance "
            "alone\ngrants no implementation authority; Session B remains "
            "unauthorized.",
            "NEXT GATE: fresh independent pre-issuance review of this corrected "
            "WO-002\nproposal. Issuance and all implementation sessions remain "
            "unauthorized.",
        ),
        encoding="utf-8",
    )
    return case


def test_completed_work_order_contract_rejects_terminal_state_mutations(
    repo_root, tmp_path, monkeypatch
):
    """WO-001 completion and the closed WO-002/release gates must fail closed."""
    spec = importlib.util.spec_from_file_location(
        "wo001_completed_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    def finding_types(case):
        monkeypatch.setattr(drift_check, "ROOT", str(case))
        return {finding["type"] for finding in drift_check.check_work_order_contract()}

    control = _make_completed_work_order_case(repo_root, tmp_path, "control")
    assert _without_terminal_lock(finding_types(control)) == set()

    returned_to_issued = _make_completed_work_order_case(
        repo_root, tmp_path, "returned-to-issued"
    )
    completed = (
        returned_to_issued
        / "docs"
        / "work-orders"
        / "completed"
        / "WO-001-custom-mcp-security.md"
    )
    issued = completed.parent.parent / "issued" / completed.name
    completed.replace(issued)
    issued.write_text(
        issued.read_text(encoding="utf-8").replace(
            "STATUS: COMPLETED", "STATUS: ISSUED"
        ).replace(
            "AUTHORIZATION: COMPLETED — NO SESSION AUTHORIZED",
            "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
        ),
        encoding="utf-8",
    )
    assert "completed WO-001 state" in finding_types(returned_to_issued)

    duplicate = _make_completed_work_order_case(repo_root, tmp_path, "duplicate")
    shutil.copy2(
        duplicate
        / "docs"
        / "work-orders"
        / "completed"
        / "WO-001-custom-mcp-security.md",
        duplicate
        / "docs"
        / "work-orders"
        / "issued"
        / "WO-001-custom-mcp-security.md",
    )
    assert "duplicate work order state" in finding_types(duplicate)

    wrong_status = _make_completed_work_order_case(repo_root, tmp_path, "status")
    status_path = (
        wrong_status
        / "docs"
        / "work-orders"
        / "completed"
        / "WO-001-custom-mcp-security.md"
    )
    status_path.write_text(
        status_path.read_text(encoding="utf-8").replace(
            "STATUS: COMPLETED", "STATUS: ISSUED"
        ),
        encoding="utf-8",
    )
    assert "completed status" in finding_types(wrong_status)

    wrong_auth = _make_completed_work_order_case(repo_root, tmp_path, "auth")
    auth_path = (
        wrong_auth
        / "docs"
        / "work-orders"
        / "completed"
        / "WO-001-custom-mcp-security.md"
    )
    auth_path.write_text(
        auth_path.read_text(encoding="utf-8").replace(
            "AUTHORIZATION: COMPLETED — NO SESSION AUTHORIZED",
            "AUTHORIZATION: COMPLETED — SESSION A AUTHORIZED",
        ),
        encoding="utf-8",
    )
    assert "completed authorization" in finding_types(wrong_auth)

    pointer_cases = (
        (
            "issued-pointer",
            "Current issued Work Order: NONE",
            "Current issued Work Order: WO-002",
            "current issued work order",
        ),
        (
            "authorized-session",
            "Authorized session: NONE",
            "Authorized session: A",
            "authorization without issued work order",
        ),
        (
            "expanded-train",
            "Release train: WO-001 through WO-007",
            "Release train: WO-001 through WO-008",
            "release train",
        ),
        (
            "open-release",
            "Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED — COMPLETE THE "
            "FROZEN TRAIN AND FINAL INTEGRATION/REPOSITORY-TRUTH AUDIT FIRST",
            "Release gate: TAG AND GITHUB RELEASE AUTHORIZED",
            "release authorization",
        ),
    )
    for name, old, new, expected in pointer_cases:
        case = _make_completed_work_order_case(repo_root, tmp_path, name)
        pointer = case / "WORKORDER.md"
        pointer.write_text(
            pointer.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        assert expected in finding_types(case)

    contradictory_release = _make_completed_work_order_case(
        repo_root, tmp_path, "contradictory-release"
    )
    release_pointer = contradictory_release / "WORKORDER.md"
    release_pointer.write_text(
        release_pointer.read_text(encoding="utf-8")
        + "\nThe v2.5.0 tag and GitHub Release are authorized.\n",
        encoding="utf-8",
    )
    assert "release authorization" in finding_types(contradictory_release)


@pytest.mark.parametrize(("identifier", "expected"), (
    ("ffcbe8b1bfa03cb37453b9beefda0bbdbe45543c", "completion commit"),
    ("32921154482", "completion workflow"),
    ("98034843256", "completion job"),
))
def test_completed_work_order_requires_exact_terminal_evidence(
    repo_root, tmp_path, monkeypatch, identifier, expected
):
    """Accepted commit, workflow, and required job remain durable evidence."""
    spec = importlib.util.spec_from_file_location(
        "wo001_evidence_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    case = _make_completed_work_order_case(repo_root, tmp_path, f"evidence-{identifier}")
    completed = (
        case
        / "docs"
        / "work-orders"
        / "completed"
        / "WO-001-custom-mcp-security.md"
    )
    completed.write_text(
        completed.read_text(encoding="utf-8").replace(identifier, "REMOVED"),
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert expected in finding_types


@pytest.mark.parametrize("permission", (
    "WO-002 is issued.",
    "WO-002 is authorized.",
    "WO-002 is ready to implement.",
))
def test_completed_work_order_rejects_wo002_activation(
    repo_root, tmp_path, monkeypatch, permission
):
    """A completed predecessor cannot silently activate the next proposal."""
    spec = importlib.util.spec_from_file_location(
        "wo002_activation_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    case = _make_completed_work_order_case(repo_root, tmp_path, "wo002-activation")
    pointer = case / "WORKORDER.md"
    pointer.write_text(
        pointer.read_text(encoding="utf-8") + f"\n{permission}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "next work order authorization" in finding_types


def _make_closed_work_order_case(repo_root, tmp_path, name):
    """Build the former closed state so its fail-closed contract stays permanent."""
    case = _make_completed_work_order_case(repo_root, tmp_path, name)

    pointer = case / "WORKORDER.md"
    pointer.write_text(
        "# Current Work Order Gate\n\n"
        "This file is the repository's sole authority pointer for current Work Order\n"
        "state.\n\n"
        "- Current issued Work Order: WO-001\n"
        "- Authorized session: NONE\n"
        "- Base commit: `318c28fa08bfef032280bad9b76eab7cd81f626d`\n"
        "- Current gate: WO-001 ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED\n"
        "- Release train: WO-001 through WO-007\n"
        "- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED — COMPLETE THE FROZEN "
        "TRAIN AND FINAL INTEGRATION/REPOSITORY-TRUTH AUDIT FIRST\n\n"
        "WO-001 is issued, but issuance alone grants no implementation authority. "
        "Session A is not authorized.\n",
        encoding="utf-8",
    )

    completed = (
        case
        / "docs"
        / "work-orders"
        / "completed"
        / "WO-001-custom-mcp-security.md"
    )
    issued = completed.parent.parent / "issued" / completed.name
    completed.replace(issued)
    issued_text = issued.read_text(encoding="utf-8")
    issued_text = issued_text.replace("STATUS: COMPLETED", "STATUS: ISSUED").replace(
        "AUTHORIZATION: COMPLETED — NO SESSION AUTHORIZED",
        "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
    )
    issued_text = re.sub(
        r"\nSESSION A AUTHORIZATION BASIS:.*?\nIssuance alone",
        "\nIssuance alone",
        issued_text,
        flags=re.DOTALL,
    ).replace(
        "NEXT GATE: separate owner authorization for fresh independent pre-issuance\n"
        "review of WO-002. Completion of WO-001 does not issue or authorize WO-002, and\n"
        "no implementation session is authorized.",
        "NEXT GATE: explicit BDFL/owner authorization for Session A.",
    )
    issued.write_text(issued_text, encoding="utf-8")
    return case


@pytest.mark.parametrize("permission", (
    "SESSION A IS AUTHORIZED",
    "Session A is permitted to begin",
    "Session A is approved to proceed",
    "Session A is ready to begin",
    "Session A may now begin",
    "You may begin work on Session A",
    "Proceed with Session A",
    "The owner has cleared Session A to proceed",
    "The implementation gate for Session A is open",
    "Session A can proceed",
    "Begin implementation work for Session A",
    "The implementation gate for Session A has passed",
    "Session A has the green light",
    "Implementation may commence.",
    "The owner gave the go-ahead.",
    "Implementation is unlocked.",
    "Resume implementation work.",
    "Approval to implement is granted.",
    "Session A is not authorized. Nevertheless, work may commence.",
    "Implementation work can now proceed.",
    "Owner approval has unlocked implementation.",
    "The go-ahead came from the owner.",
    "The green light came from the owner.",
))
def test_closed_work_order_rejects_permission_phrasings(
    repo_root, tmp_path, monkeypatch, permission
):
    """Permission language must fail through the real drift contract."""
    spec = importlib.util.spec_from_file_location(
        "wo001_drift_check", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    case = _make_closed_work_order_case(repo_root, tmp_path, "permission")
    issued = (
        case
        / "docs"
        / "work-orders"
        / "issued"
        / "WO-001-custom-mcp-security.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8") + f"\n{permission}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "implicit session authorization" in finding_types


def test_closed_work_order_rejects_contradiction_after_canonical_negative(
    repo_root, tmp_path, monkeypatch
):
    """A positive clause cannot hide behind the required negative sentence."""
    spec = importlib.util.spec_from_file_location(
        "wo001_drift_check", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    case = _make_closed_work_order_case(
        repo_root, tmp_path, "canonical-negative-contradiction"
    )
    pointer = case / "WORKORDER.md"
    pointer.write_text(
        pointer.read_text(encoding="utf-8").replace(
            "Session A is not authorized.",
            "Session A is not authorized. Nevertheless, work may commence.",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "implicit session authorization" in finding_types


def test_closed_work_order_accepts_canonical_closed_authority_language(
    repo_root, tmp_path, monkeypatch
):
    """The unchanged issued state is the positive control for the detector."""
    spec = importlib.util.spec_from_file_location(
        "wo001_drift_check", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    case = _make_closed_work_order_case(
        repo_root, tmp_path, "canonical-closed-state"
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "implicit session authorization" not in finding_types


def test_work_order_issuance_contract_rejects_structural_authority_mutations(
    repo_root, tmp_path, monkeypatch
):
    """Issued metadata must fail closed under structural authority mutations."""
    spec = importlib.util.spec_from_file_location(
        "wo001_drift_check", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    def make_case(name):
        return _make_closed_work_order_case(repo_root, tmp_path, name)

    def finding_types(case):
        monkeypatch.setattr(drift_check, "ROOT", str(case))
        return {finding["type"] for finding in drift_check.check_work_order_contract()}

    wrong_status = make_case("wrong-status")
    wrong_status_issued = (
        wrong_status
        / "docs"
        / "work-orders"
        / "issued"
        / "WO-001-custom-mcp-security.md"
    )
    wrong_status_issued.write_text(
        wrong_status_issued.read_text(encoding="utf-8").replace(
            "STATUS: ISSUED", "STATUS: PROPOSED"
        ),
        encoding="utf-8",
    )
    assert "issued status" in finding_types(wrong_status)

    stale_pointer = make_case("stale-pointer")
    stale_pointer_path = stale_pointer / "WORKORDER.md"
    stale_pointer_path.write_text(
        stale_pointer_path.read_text(encoding="utf-8").replace(
            "Current issued Work Order: WO-001",
            "Current issued Work Order: WO-009",
        ),
        encoding="utf-8",
    )
    assert "current issued work order mismatch" in finding_types(stale_pointer)

    duplicate = make_case("duplicate-state")
    shutil.copy2(
        duplicate
        / "docs"
        / "work-orders"
        / "issued"
        / "WO-001-custom-mcp-security.md",
        duplicate
        / "docs"
        / "work-orders"
        / "proposed"
        / "WO-001-custom-mcp-security.md",
    )
    assert "duplicate work order state" in finding_types(duplicate)

    unauthorized_session = make_case("unauthorized-session")
    unauthorized_pointer = unauthorized_session / "WORKORDER.md"
    unauthorized_pointer.write_text(
        unauthorized_pointer.read_text(encoding="utf-8").replace(
            "Authorized session: NONE", "Authorized session: A"
        ),
        encoding="utf-8",
    )
    assert "issued session authorization" in finding_types(unauthorized_session)


def test_authorized_session_a_contract_rejects_metadata_or_gate_drift(
    repo_root, tmp_path, monkeypatch
):
    """The live Session A gate must agree across pointer and issued metadata."""
    spec = importlib.util.spec_from_file_location(
        "wo001_authorized_drift_check", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    def make_case(name):
        case = _make_closed_work_order_case(repo_root, tmp_path, name)
        pointer = case / "WORKORDER.md"
        pointer.write_text(
            pointer.read_text(encoding="utf-8").replace(
                "Authorized session: NONE", "Authorized session: A"
            ).replace(
                "WO-001 ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED",
                "WO-001 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY",
            ),
            encoding="utf-8",
        )
        issued = (
            case
            / "docs"
            / "work-orders"
            / "issued"
            / "WO-001-custom-mcp-security.md"
        )
        issued.write_text(
            issued.read_text(encoding="utf-8").replace(
                "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
                "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",
            ),
            encoding="utf-8",
        )
        return case

    def finding_types(case):
        monkeypatch.setattr(drift_check, "ROOT", str(case))
        return {finding["type"] for finding in drift_check.check_work_order_contract()}

    closed_marker = make_case("closed-marker")
    issued = (
        closed_marker
        / "docs"
        / "work-orders"
        / "issued"
        / "WO-001-custom-mcp-security.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8").replace(
            "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",
            "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
        ),
        encoding="utf-8",
    )
    assert "issued session authorization" in finding_types(closed_marker)

    wrong_gate = make_case("wrong-gate")
    pointer = wrong_gate / "WORKORDER.md"
    pointer.write_text(
        pointer.read_text(encoding="utf-8").replace(
            "WO-001 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY",
            "WO-001 SESSION A AUTHORIZED — IMPLEMENT ALL SESSIONS",
        ),
        encoding="utf-8",
    )
    assert "authorized session gate" in finding_types(wrong_gate)

    unknown_session = make_case("unknown-session")
    pointer = unknown_session / "WORKORDER.md"
    pointer.write_text(
        pointer.read_text(encoding="utf-8").replace(
            "Authorized session: A", "Authorized session: B"
        ),
        encoding="utf-8",
    )
    assert "authorized session gate" in finding_types(unknown_session)


@pytest.mark.parametrize("permission", (
    "Session B is authorized. Implementation may begin.",
    "Implementation of Session C may now proceed.",
    "The owner gave Session AA the green light.",
    "Session B: AUTHORIZED",
    "Session C: implementation may proceed",
    "Session AA: owner approval granted",
))
def test_authorized_session_rejects_later_session_activation(
    repo_root, tmp_path, monkeypatch, permission
):
    """Only the exact root-authorized session may receive positive authority."""
    spec = importlib.util.spec_from_file_location(
        "wo001_later_session_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    case_name = "later-session-" + re.sub(
        r"[^A-Za-z0-9]", "-", permission
    )[:24]
    case = _make_closed_work_order_case(repo_root, tmp_path, case_name)
    pointer = case / "WORKORDER.md"
    pointer.write_text(
        pointer.read_text(encoding="utf-8").replace(
            "Authorized session: NONE", "Authorized session: A"
        ).replace(
            "WO-001 ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED",
            "WO-001 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY",
        ),
        encoding="utf-8",
    )
    issued = (
        case
        / "docs"
        / "work-orders"
        / "issued"
        / "WO-001-custom-mcp-security.md"
    )
    issued.write_text(
        issued.read_text(encoding="utf-8").replace(
            "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
            "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",
        ) + f"\n{permission}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert "later session authorization" in finding_types


@pytest.mark.parametrize("closed", (
    "Session B is not authorized.",
    "Session B requires a separate owner gate.",
    "Session B must not begin until a separate owner gate.",
    "Session C is not ready to proceed.",
    "Session AA may not start without explicit owner authorization.",
    "No later session is implicitly authorized.",
))
def test_authorized_session_allows_later_session_closed_language(
    repo_root, closed
):
    spec = importlib.util.spec_from_file_location(
        "wo001_closed_later_session", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    assert not drift_check._has_other_session_authorization(
        "- Authorized session: A",
        closed,
        "A",
    )


def test_llms_mcp_security_contract_is_non_vacuous(repo_root, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "llms_mcp_security_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)
    assert drift_check.check_mcp_security_contract() == []

    source = " ".join(
        (repo_root / "llms.txt").read_text(encoding="utf-8").split()
    )
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
    for index, phrase in enumerate(required):
        case = tmp_path / f"missing-{index}"
        case.mkdir()
        (case / "llms.txt").write_text(
            source.replace(phrase, "removed security claim", 1),
            encoding="utf-8",
        )
        monkeypatch.setattr(drift_check, "ROOT", str(case))
        assert drift_check.check_mcp_security_contract(), phrase

    forbidden_case = tmp_path / "forbidden"
    forbidden_case.mkdir()
    (forbidden_case / "llms.txt").write_text(
        source + "\nAny MCP client auto-connects and can execute arbitrary Python.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(forbidden_case))
    findings = drift_check.check_mcp_security_contract()
    assert len(findings) >= 2


@pytest.mark.parametrize("inversion", (
    "Browser-originated requests are accepted.",
    "Arbitrary remote Python is available.",
    "mcp_start may be called remotely.",
    "The custom bridge is reachable from remote hosts.",
))
def test_llms_mcp_security_contract_rejects_direct_inversions(
    repo_root, tmp_path, monkeypatch, inversion
):
    """Correct claims cannot coexist with a direct inversion of the boundary."""
    spec = importlib.util.spec_from_file_location(
        "llms_mcp_inversion_drift", repo_root / "scripts" / "drift_check.py"
    )
    assert spec is not None and spec.loader is not None
    drift_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift_check)

    case = tmp_path / "inversion"
    case.mkdir()
    source = (repo_root / "llms.txt").read_text(encoding="utf-8")
    (case / "llms.txt").write_text(
        source + f"\n{inversion}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    finding_types = {
        finding["type"] for finding in drift_check.check_mcp_security_contract()
    }
    assert "MCP security contract" in finding_types


def test_agent_context_links_audit_work_orders_and_security(repo_root):
    """Fresh agents must discover durable evidence before relying on chat."""
    agent_guide = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    claude = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
    for text in (agent_guide, claude):
        assert "WORKORDER.md" in text
        assert "SECURITY.md" in text
        assert "2026-08-24-uefn-42-official-mcp-audit.md" in text
    assert "planning only and never grant implementation" in " ".join(agent_guide.split())
    assert "is not a go signal" in " ".join(claude.split())


def test_official_mcp_audit_evidence_is_sanitized_and_complete(repo_root):
    """The durable audit preserves its measured surface and responsibility split."""
    audit = (
        repo_root
        / "docs"
        / "audits"
        / "2026-08-24-uefn-42-official-mcp-audit.md"
    ).read_text(encoding="utf-8")
    evidence_path = (
        repo_root
        / "docs"
        / "audits"
        / "evidence"
        / "2026-08-24-official-mcp-signatures.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    security = (repo_root / "SECURITY.md").read_text(encoding="utf-8")

    assert evidence["environment"]["sanitized"] is True
    assert len(evidence["toolsets"]) == 29
    expected_surface_counts = {
        "verse": 10,
        "creative_devices": 9,
        "scene_graph_entities": 13,
        "umg": 21,
        "play_sessions": 8,
    }
    for surface, count in expected_surface_counts.items():
        assert len(evidence["surfaces"][surface]["tools"]) == count
    serialized = json.dumps(evidence).lower()
    assert "session_id" not in serialized
    assert "@fortnite.com" not in serialized

    for heading in ("Codex-autonomous work", "Owner/manual work", "Intentionally withheld"):
        assert heading in audit
    assert "96 Python files restored" in audit
    assert "session Disconnected and game Unconnected" in audit
    security_normalized = " ".join(security.split())
    assert "binding to `127.0.0.1` limits network reach but does not authenticate" in security_normalized
    assert "did not perform malicious or destructive exploit testing" in security_normalized


def test_agent_publish_workflow_preserves_runtime_order(repo_root):
    """Audits need Python; staging it first makes the documented cleanup unusable."""
    publish = (repo_root / ".claude" / "commands" / "publish-check.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(publish.split())
    prohibition = (
        "Do **not** restart UEFN, hot-reload Toolbelt, deploy again, or create "
        "replacement Python files while the stash is active."
    )
    audit_at = normalized.index('tb.run("publish_audit")')
    cleanup_at = normalized.index('tb.run("sign_clear"')
    prepare_at = normalized.index("prepare_launch.bat")
    prohibition_at = normalized.index(prohibition)
    restore_at = normalized.rindex("restore_after_launch.bat")
    assert audit_at < cleanup_at < prepare_at < prohibition_at < restore_at
    assert "Fortnite opening is not proof" in normalized
    normalized_lower = normalized.lower()
    assert normalized_lower.count("deploy again") == 1
    assert normalized_lower.count("replacement python files") == 1


def test_agent_deploy_guidance_stops_before_git_mutation(repo_root):
    """A live pass is evidence, not implicit commit or push authorization."""
    deploy = (repo_root / ".claude" / "commands" / "deploy.md").read_text(
        encoding="utf-8"
    )
    for forbidden in ("git add -A", "git add --all", "git commit -m", "git push origin"):
        assert forbidden not in deploy
    assert "leave the complete worktree uncommitted" in deploy
    assert "separate explicit owner go signal" in deploy


def test_agent_authoring_guidance_matches_registry_and_release_boundary(repo_root):
    """Authoring guidance must match the decorator API and release boundary."""
    developer = (repo_root / ".claude" / "agents" / "tool-developer.md").read_text(
        encoding="utf-8"
    )
    add_command = (repo_root / ".claude" / "commands" / "add-tool.md").read_text(
        encoding="utf-8"
    )
    contributing = (repo_root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    registry_tree = ast.parse(
        (repo_root / "Content" / "Python" / "UEFN_Toolbelt" / "registry.py").read_text(
            encoding="utf-8"
        )
    )
    register_tool = next(
        node
        for node in registry_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_tool"
    )
    decorator_params = {arg.arg for arg in register_tool.args.args}
    contributing_normalized = " ".join(contributing.split())
    assert "example" in decorator_params
    assert "parameters" not in decorator_params
    assert "`example=` is optional manifest metadata" in developer
    assert "the decorator does not accept `parameters=`" in developer
    assert "`example=` metadata is supported" in contributing_normalized
    assert "Do not pass `parameters=`" in contributing
    assert "Do not change `__version__`" in developer
    assert "Do not change `__version__`" in add_command
    assert "full UEFN restart" in developer
    assert "full UEFN restart" in add_command


def test_pr_template_preserves_runtime_verification_and_static_na(repo_root):
    """Static-only N/A must not replace the live gate for runtime changes."""
    pr_template = (repo_root / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    lines = pr_template.splitlines()
    deploy_line = next(line for line in lines if "Ran `deploy.bat`" in line)
    runtime_line = next(line for line in lines if "Tested in live UEFN" in line)
    new_module_line = next(line for line in lines if "New module:" in line)
    static_na_line = next(line for line in lines if "Docs/static-only change" in line)
    checkbox_lines = [line for line in lines if line.startswith("- [ ]")]
    na_checkboxes = [line for line in checkbox_lines if "N/A" in line.upper()]
    assert "N/A" not in deploy_line
    assert "N/A" not in runtime_line
    assert na_checkboxes == [new_module_line, static_na_line]
    assert static_na_line.startswith("- [ ] Docs/static-only change:")
    assert "live UEFN is N/A" in static_na_line
    assert "reason is stated below" in static_na_line
    assert "**Live verification or N/A reason:**" in pr_template


def test_agent_authority_and_commit_format_are_explicit(repo_root):
    """Every high-level entry point must preserve the owner's distribution gates."""
    agent_guide = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    claude = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
    for text in (agent_guide, claude):
        for boundary in ("commit", "push", "tag", "GitHub Release", "social"):
            assert boundary in text
    contributing = (repo_root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    pr_template = (repo_root / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    assert "feat(scope): concise description" in contributing
    assert "type(scope): lowercase description" in pr_template
    assert "feat: add my_tool" not in contributing


_SESSION_B_BASE = "d1a2c810126ba6c9e14891da1b25cb198c1d45c7"
_SESSION_B_WORKFLOW = "33047743360"
_SESSION_B_JOB = "98435618996"
_SESSION_B_GATE = (
    "- Current gate: WO-002 SESSION B AUTHORIZED " + _EM
    + " EXECUTE EXTERNAL PROOF ONLY"
)
_SESSION_B_MARKER = (
    "AUTHORIZATION: ISSUED " + _EM + " SESSION B AUTHORIZED FOR EXTERNAL PROOF"
)


def _completed_finding_types(repo_root, tmp_path, monkeypatch, name, mutate):
    """Findings drift_check reports for a mutated completed WO-002 state."""
    drift_check = _load_drift_check(repo_root, "wo002_completed_" + name)
    case = _make_wo002_completed_case(repo_root, tmp_path, "completed-" + name)
    mutate(case)
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return {
        finding["type"] for finding in drift_check.check_work_order_contract()
    } - {_TERMINAL_WO003_FINDING}


def _session_b_finding_types(repo_root, tmp_path, monkeypatch, name, mutate):
    """Findings drift_check reports for a mutated Session B state."""
    drift_check = _load_drift_check(repo_root, "wo002_session_b_" + name)
    case = _make_wo002_session_b_case(repo_root, tmp_path, "session-b-" + name)
    mutate(case)
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return {finding["type"] for finding in drift_check.check_work_order_contract()}


def _edit(case, rel, old, new):
    target = case / rel
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1, "probe anchor drifted: " + repr(old[:60])
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


@pytest.mark.parametrize(("name", "rel", "old", "new", "expected"), (
    ("session-field", "WORKORDER.md",
     "- Authorized session: B", "- Authorized session: NONE",
     "Session A accepted gate"),
    ("gate", "WORKORDER.md",
     _SESSION_B_GATE,
     "- Current gate: WO-002 SESSION B AUTHORIZED " + _EM + " DO ANYTHING",
     "authorized session gate"),
    ("base-commit", "WORKORDER.md",
     "- Base commit: `" + _SESSION_B_BASE + "`",
     "- Base commit: `" + _WRONG_COMMIT + "`",
     "Session B base commit"),
    ("marker", _ISSUED_REL,
     _SESSION_B_MARKER,
     "AUTHORIZATION: ISSUED " + _EM + " SESSION B AUTHORIZED FOR ANYTHING",
     "issued session authorization"),
    ("authorization-commit", _ISSUED_REL,
     "`" + _SESSION_B_BASE + "`; successful CI workflow",
     "`" + _WRONG_COMMIT + "`; successful CI workflow",
     "Session B authorization commit"),
    ("authorization-workflow", _ISSUED_REL,
     "`" + _SESSION_B_WORKFLOW + "` included",
     "`" + _WRONG_WORKFLOW + "` included",
     "Session B authorization workflow"),
    ("authorization-job", _ISSUED_REL,
     "required job `" + _SESSION_B_JOB + "`",
     "required job `" + _WRONG_JOB + "`",
     "Session B authorization job"),
    ("proof-only", _ISSUED_REL,
     "Session B is authorized" + _NL + "for external proof only.",
     "Session B is authorized" + _NL + "for whatever it judges necessary.",
     "Session B proof-only statement"),
    ("next-gate", _ISSUED_REL,
     "NEXT GATE: fresh independent architect review of the complete uncommitted",
     "NEXT GATE: none; Session B may self-accept and continue",
     "WO-002 next gate"),
))
def test_wo002_session_b_contract_is_exact(
    repo_root, tmp_path, monkeypatch, name, rel, old, new, expected
):
    """Session B's gate, marker, and authorization evidence are each pinned."""
    found = _session_b_finding_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _edit(case, rel, old, new),
    )
    assert expected in found, (
        name + " was accepted; drift_check reported " + repr(sorted(found))
    )


@pytest.mark.parametrize("activation", (
    "WO-003 is authorized and may begin.",
    "Session C is authorized to proceed.",
))
def test_wo002_session_b_rejects_later_work_order_activation(
    repo_root, tmp_path, monkeypatch, activation
):
    """Authorizing Session B never opens WO-003 or a later session."""
    found = _session_b_finding_types(
        repo_root, tmp_path, monkeypatch,
        "activation-" + activation.split()[0],
        lambda case: _edit(
            case, "WORKORDER.md",
            "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-007" + _NL + _NL + activation,
        ),
    )
    assert found & {"later session authorization",
                    "next work order authorization"}, (
        "later activation was accepted: " + repr(sorted(found))
    )


def test_wo002_session_b_control_is_clean(repo_root, tmp_path, monkeypatch):
    """The unmutated Session B state produces no Work Order findings."""
    found = _session_b_finding_types(
        repo_root, tmp_path, monkeypatch, "control", lambda case: None
    )
    assert _without_terminal_lock(found) == set(), (
        "the authorized Session B state is not clean: " + repr(sorted(found))
    )
    assert found == {_TERMINAL_WO002_FINDING, _TERMINAL_WO003_FINDING}, (
        "the reconstructed Session B state must still trip both later locks: "
        + repr(sorted(found))
    )


def test_wo002_completed_preserves_session_a_acceptance(
    repo_root, tmp_path, monkeypatch
):
    """Authorizing Session B must not silence Session A's accepted evidence."""
    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch, "acceptance-still-enforced",
        lambda case: _edit(
            case, "WORKORDER.md",
            "[CI workflow" + _NL + "`" + _ACCEPTED_WORKFLOW + "`]",
            "[CI workflow" + _NL + "`" + _WRONG_WORKFLOW + "`]",
        ),
    )
    assert _POINTER_FINDING in found, (
        "Session A's acceptance record stopped being enforced after completion: "
        + repr(sorted(found))
    )


_WO002_COMPLETION_COMMIT = "c031f20e33c716ecc9f9ce546a7419b865ed8641"
_WO002_COMPLETION_WORKFLOW = "33133090929"
_WO002_COMPLETION_JOB = "98726805137"
_WO002_EVIDENCE_PATH = (
    "docs/audits/evidence/2026-08-27-wo002-session-b-official-mcp.json"
)
_WO002_EVIDENCE_SHA256 = (
    "9DFBD500808113A122C65DA680AF8AD5409045DC1414AFEBEFB6B8771FE46CB0"
)
_COMPLETED_GATE = (
    "- Current gate: WO-002 COMPLETED " + _EM
    + " WO-003 PROPOSED AND NOT AUTHORIZED"
)
_COMPLETED_MARKER = "AUTHORIZATION: COMPLETED " + _EM + " NO SESSION AUTHORIZED"


@pytest.mark.parametrize(("name", "rel", "old", "new", "expected"), (
    ("reopened-pointer", "WORKORDER.md",
     "- Current issued Work Order: NONE", "- Current issued Work Order: WO-002",
     "current issued work order"),
    ("reopened-session", "WORKORDER.md",
     "- Authorized session: NONE", "- Authorized session: B",
     "authorization without issued work order"),
    ("gate", "WORKORDER.md", _COMPLETED_GATE,
     "- Current gate: WO-002 COMPLETED " + _EM + " WO-003 MAY BEGIN",
     "completed work order gate"),
    ("base-commit", "WORKORDER.md",
     "- Base commit: `" + _WO002_COMPLETION_COMMIT + "`",
     "- Base commit: `" + _WRONG_COMMIT + "`",
     "completion base commit"),
    ("status", _COMPLETED_REL, "STATUS: COMPLETED", "STATUS: ISSUED",
     "completed status"),
    ("marker", _COMPLETED_REL, _COMPLETED_MARKER,
     "AUTHORIZATION: COMPLETED " + _EM + " SESSION C AUTHORIZED",
     "completed authorization"),
    ("completion-commit", _COMPLETED_REL,
     "`" + _WO002_COMPLETION_COMMIT + "`; successful CI workflow",
     "`" + _WRONG_COMMIT + "`; successful CI workflow",
     "WO-002 completion commit"),
    ("completion-workflow", _COMPLETED_REL,
     "`" + _WO002_COMPLETION_WORKFLOW + "` included",
     "`" + _WRONG_WORKFLOW + "` included",
     "WO-002 completion workflow"),
    ("completion-job", _COMPLETED_REL,
     "required job `" + _WO002_COMPLETION_JOB + "`",
     "required job `" + _WRONG_JOB + "`",
     "WO-002 completion job"),
    ("evidence-path", _COMPLETED_REL, _WO002_EVIDENCE_PATH,
     "docs/audits/evidence/some-other-file.json",
     "WO-002 evidence artifact"),
    ("evidence-digest", _COMPLETED_REL, _WO002_EVIDENCE_SHA256,
     "0" * len(_WO002_EVIDENCE_SHA256), "WO-002 evidence digest"),
    ("terminal-external", _COMPLETED_REL,
     "`externally_callable` all failed.",
     "`externally_callable` all passed.",
     "WO-002 terminal external result"),
    ("negative-result", _COMPLETED_REL,
     "This is an accepted negative result bounded by",
     "This is a fully exposed integration proven by",
     "WO-002 accepted negative result"),
))
def test_wo002_completed_contract_is_exact(
    repo_root, tmp_path, monkeypatch, name, rel, old, new, expected
):
    """The terminal WO-002 state pins its own gate, markers, and evidence."""
    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _edit(case, rel, old, new),
    )
    assert expected in found, (
        name + " was accepted; drift_check reported " + repr(sorted(found))
    )


def test_wo002_completed_rejects_a_reopened_duplicate(
    repo_root, tmp_path, monkeypatch
):
    """WO-002 may exist in exactly one state directory."""
    def reopen(case):
        completed = case / _COMPLETED_REL
        issued = case / _ISSUED_REL
        issued.write_text(completed.read_text(encoding="utf-8"), encoding="utf-8")

    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch, "reopened-duplicate", reopen
    )
    assert found & {"duplicate work order state", "WO-002 state",
                    "unpointed issued work order"}, (
        "a reopened WO-002 copy was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize("activation", (
    "WO-003 is authorized and may begin.",
    "The gate for WO-003 is now cleared.",
))
def test_wo002_completed_rejects_wo003_activation(
    repo_root, tmp_path, monkeypatch, activation
):
    """Completing WO-002 never issues or authorizes WO-003."""
    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch,
        "wo003-" + activation.split()[0].strip("."),
        lambda case: _edit(
            case, "WORKORDER.md",
            "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-007" + _NL + _NL + activation,
        ),
    )
    assert "next work order authorization" in found, (
        "WO-003 activation was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "old", "new", "expected"), (
    ("release-train", "- Release train: WO-001 through WO-007",
     "- Release train: WO-001 through WO-008", "release train"),
    ("release-gate", "- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED",
     "- Release gate: TAG AND GITHUB RELEASE AUTHORIZED",
     "release authorization"),
))
def test_wo002_completed_keeps_the_release_gate_closed(
    repo_root, tmp_path, monkeypatch, name, old, new, expected
):
    """Completion expands neither the frozen train nor the tag/Release gate."""
    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch, "release-" + name,
        lambda case: _edit(case, "WORKORDER.md", old, new),
    )
    assert expected in found, (
        name + " was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize("proposal", (
    "WO-004-modal-observability.md",
    "WO-005-coverage-source-of-truth.md",
    "WO-006-official-vs-toolbelt-benchmark.md",
    "WO-007-public-mcp-explainer.md",
))
def test_remaining_proposals_stay_unauthorized(
    repo_root, tmp_path, monkeypatch, proposal
):
    """WO-003 through WO-007 keep PROPOSED and NOT AUTHORIZED."""
    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch, "proposal-" + proposal[:6],
        lambda case: _edit(
            case, "docs/work-orders/proposed/" + proposal,
            "AUTHORIZATION: NOT AUTHORIZED",
            "AUTHORIZATION: ISSUED " + _EM + " SESSION A AUTHORIZED",
        ),
    )
    assert "proposed authorization" in found, (
        proposal + " was allowed to self-authorize: " + repr(sorted(found))
    )


def test_wo002_completed_control_is_clean(repo_root, tmp_path, monkeypatch):
    """The unmutated terminal state produces no Work Order findings."""
    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch, "control", lambda case: None
    )
    assert found == set(), "the completed state is not clean: " + repr(sorted(found))


def test_wo002_completion_cannot_be_rolled_back(repo_root, tmp_path, monkeypatch):
    """A fully coherent rollback to authorized Session B must still fail.

    Partial edits were already rejected. The gap this closes is the *coherent*
    rollback: WO-002 moved back to issued/ with its pointer fields, markers,
    gate, Session B record, and pre-completion NEXT GATE all restored together,
    so nothing internally contradicts. Completion is one-way because this
    checker carries the completion contract, not because the documents disagree.
    """
    drift_check = _load_drift_check(repo_root, "wo002_rollback")
    case = _make_wo002_session_b_case(repo_root, tmp_path, "wo002-rollback")

    # The reconstruction really is the whole prior state, not a partial edit.
    pointer = (case / "WORKORDER.md").read_text(encoding="utf-8")
    issued = (case / _ISSUED_REL).read_text(encoding="utf-8")
    assert (case / _ISSUED_REL).exists(), "WO-002 was not moved back to issued/"
    assert not (case / _COMPLETED_REL).exists(), "a completed copy was left behind"
    for needle in (
        "- Current issued Work Order: WO-002",
        "- Authorized session: B",
        "- Base commit: `d1a2c810126ba6c9e14891da1b25cb198c1d45c7`",
        "- Current gate: WO-002 SESSION B AUTHORIZED " + _EM
        + " EXECUTE EXTERNAL PROOF ONLY",
    ):
        assert needle in pointer, "rollback did not restore: " + needle
    for needle in (
        "STATUS: ISSUED",
        "AUTHORIZATION: ISSUED " + _EM + " SESSION B AUTHORIZED FOR EXTERNAL PROOF",
        "NEXT GATE: fresh independent architect review of the complete uncommitted",
    ):
        assert needle in issued, "rollback did not restore: " + needle
    assert "## Session B acceptance and completion record" not in issued, (
        "the completion record survived the rollback"
    )

    monkeypatch.setattr(drift_check, "ROOT", str(case))
    found = {finding["type"] for finding in drift_check.check_work_order_contract()}
    assert _TERMINAL_WO002_FINDING in found, (
        "a coherent rollback to Session B was accepted: " + repr(sorted(found))
    )


def test_terminal_lock_does_not_fire_on_the_completed_state(
    repo_root, tmp_path, monkeypatch
):
    """Non-vacuous: the lock is silent on the state it is protecting."""
    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch, "terminal-control", lambda case: None
    )
    assert _TERMINAL_WO002_FINDING not in found, (
        "the terminal lock fires on the completed state itself"
    )


@pytest.mark.parametrize("destination", ("issued", "proposed"))
def test_wo002_cannot_leave_completed(
    repo_root, tmp_path, monkeypatch, destination
):
    """WO-002 exists only under completed/, wherever else it is moved."""
    def relocate(case):
        completed = case / _COMPLETED_REL
        target = (case / "docs" / "work-orders" / destination
                  / "WO-002-epic-toolset-integration.md")
        completed.replace(target)

    found = _completed_finding_types(
        repo_root, tmp_path, monkeypatch, "moved-to-" + destination, relocate
    )
    assert _TERMINAL_WO002_FINDING in found, (
        "moving WO-002 to " + destination + " was accepted: " + repr(sorted(found))
    )


_MISSING_TARGET = "missing scan target"
_COMPLETED_WO002_SCAN = (
    "docs/work-orders/completed/WO-002-epic-toolset-integration.md"
)
_ISSUED_WO002_SCAN = "docs/work-orders/issued/WO-002-epic-toolset-integration.md"


def _missing_scan_targets(drift_check):
    """Every declared scan target the real scanner reports as absent."""
    missing = []
    for rel in drift_check.SCAN_FILES:
        missing.extend(
            finding
            for finding in drift_check.scan_file(
                rel, drift_check.VERSION, drift_check.TOOL_COUNT,
                drift_check.CATEGORY_COUNT,
            )
            if finding["type"] == _MISSING_TARGET
        )
    return missing


def _scan_target_case(repo_root, tmp_path, name, drift_check):
    """A temporary tree holding exactly the declared scan targets."""
    case = tmp_path / name
    for rel in drift_check.SCAN_FILES:
        source = repo_root / rel
        assert source.exists(), "declared scan target is missing: " + rel
        target = case / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return case


def test_completed_wo002_is_the_declared_scan_target(repo_root) -> None:
    """WO-002 is scanned where it now lives, not where it used to."""
    drift_check = _load_drift_check(repo_root, "scan_target_identity")
    assert _COMPLETED_WO002_SCAN in drift_check.SCAN_FILES
    assert _ISSUED_WO002_SCAN not in drift_check.SCAN_FILES
    assert (repo_root / _COMPLETED_WO002_SCAN).exists()
    assert not (repo_root / _ISSUED_WO002_SCAN).exists()


def test_every_declared_scan_target_exists(repo_root) -> None:
    """The intact repository declares no target it does not ship."""
    drift_check = _load_drift_check(repo_root, "scan_target_intact")
    absent = [rel for rel in drift_check.SCAN_FILES
              if not (repo_root / rel).exists()]
    assert not absent, "declared but absent scan targets: " + repr(absent)
    assert not _missing_scan_targets(drift_check)


@pytest.mark.parametrize("victim", (
    _COMPLETED_WO002_SCAN,
    "CLAUDE.md",
))
def test_deleting_a_declared_scan_target_is_reported(
    repo_root, tmp_path, monkeypatch, victim
) -> None:
    """A declared target that vanishes is drift, never clean input."""
    drift_check = _load_drift_check(repo_root, "scan_target_del_" + victim[:8])
    case = _scan_target_case(
        repo_root, tmp_path, "scan-del-" + victim.replace("/", "-"), drift_check
    )
    (case / victim).unlink()
    monkeypatch.setattr(drift_check, "ROOT", str(case))

    missing = _missing_scan_targets(drift_check)
    assert [finding["file"] for finding in missing] == [victim], (
        "deleting " + victim + " produced " + repr(missing)
    )
    assert missing[0]["type"] == _MISSING_TARGET
    assert victim in missing[0]["expected"], (
        "the finding must name the missing repository-relative path"
    )


def test_a_missing_target_cannot_be_hidden_by_equivalent_text(
    repo_root, tmp_path, monkeypatch
) -> None:
    """The check is keyed on the declared path, not on text existing somewhere.

    Copying the vanished document's exact content to another location must not
    satisfy the target - otherwise a scan set could be silently emptied while
    every string it pinned still appeared somewhere in the tree.
    """
    drift_check = _load_drift_check(repo_root, "scan_target_decoy")
    case = _scan_target_case(repo_root, tmp_path, "scan-decoy", drift_check)
    victim = case / _COMPLETED_WO002_SCAN
    content = victim.read_text(encoding="utf-8")
    victim.unlink()
    decoy = case / "docs" / "work-orders" / "completed" / "WO-002-copy.md"
    decoy.write_text(content, encoding="utf-8")
    monkeypatch.setattr(drift_check, "ROOT", str(case))

    missing = _missing_scan_targets(drift_check)
    assert [finding["file"] for finding in missing] == [_COMPLETED_WO002_SCAN], (
        "an equivalent-text decoy satisfied the declared target: " + repr(missing)
    )


def test_present_targets_still_scan_normally(repo_root, tmp_path, monkeypatch) -> None:
    """Non-vacuous: existing files keep being read, not just counted.

    A stale tool count planted inside the completed WO-002 document must be
    caught, which proves the repaired target is genuinely scanned rather than
    merely listed.
    """
    drift_check = _load_drift_check(repo_root, "scan_target_reads")
    case = _scan_target_case(repo_root, tmp_path, "scan-reads", drift_check)
    target = case / _COMPLETED_WO002_SCAN
    target.write_text(
        target.read_text(encoding="utf-8") + _NL + "This ships 361 tools." + _NL,
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))

    found = drift_check.scan_file(
        _COMPLETED_WO002_SCAN, drift_check.VERSION, drift_check.TOOL_COUNT,
        drift_check.CATEGORY_COUNT,
    )
    assert "tool count" in {finding["type"] for finding in found}, (
        "the repaired scan target is listed but not actually read"
    )
    assert _MISSING_TARGET not in {finding["type"] for finding in found}


_WO003_REL = "docs/work-orders/issued/WO-003-official-mcp-doc-convergence.md"
_WO003_PLANNING_BASELINE = "e0b1063f5300404534c76789bdb6742f639425ba"
_WO003_ISSUANCE_COMMIT = "19350aa324bea4d88e494ee806801586a383d76e"
_WO003_ISSUANCE_WORKFLOW = "33148089523"
_WO003_ISSUANCE_JOB = "98773518991"
_WO003_SESSION_A_BASE = "52d89295614a4ce686094736d87f7e6c907e12a0"
_WO003_SESSION_A_WORKFLOW = "33200547479"
_WO003_SESSION_A_JOB = "98948639416"
_WO003_SESSION_A_ACCEPTED_BASE = "d23add58e02ddc855573cf9be7a2542776d25e7e"
_WO003_SESSION_A_ACCEPTED_WORKFLOW = "33344006899"
_WO003_SESSION_A_ACCEPTED_JOB = "99344607213"
_WO003_SESSION_B_BASE = "2582be8c9168d72b46846334bbba44307d348ce6"
_WO003_SESSION_B_WORKFLOW = "33351157691"
_WO003_SESSION_B_JOB = "99364656646"
_WO003_SESSION_B_GATE = (
    "- Current gate: WO-003 SESSION B AUTHORIZED " + _EM
    + " DRAFT REPOSITORY DESCRIPTION ONLY"
)
_WO003_SESSION_B_MARKER = (
    "AUTHORIZATION: ISSUED " + _EM
    + " SESSION B AUTHORIZED FOR DRAFTING ONLY"
)
_WO003_SESSION_B_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted"
    + _NL + "Session B repository-description draft. The draft is not applied,"
    + " and metadata" + _NL + "application remains unauthorized."
)
_WO003_SESSION_B_STATEMENT = (
    "This Work Order remains issued. Session A is accepted and complete. Session"
    + " B" + _NL
    + "is authorized for repository-description drafting only. Metadata"
    + " application," + _NL
    + "Session C or any later session, WO-004, tagging, Release creation, and"
    + " social" + _NL
    + "publication remain unauthorized."
)
_WO003_SESSION_B_POINTER_STATEMENT = (
    "Session B is authorized under this pointer for repository-description"
    + " drafting" + _NL
    + "only, on the basis of commit `" + _WO003_SESSION_B_BASE + "`," + _NL
    + "successful CI workflow `" + _WO003_SESSION_B_WORKFLOW
    + "`, and successful required job `" + _WO003_SESSION_B_JOB + "`" + _NL
    + "(`Lint, types, tests`). No repository metadata application, tag, Release,"
    + " or" + _NL + "social publication is authorized."
)
_WO003_CURRENT_DESCRIPTION = (
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
_WO003_SESSION_B_ACCEPTED_BASE = "e23baa40c4b9358eb6b4448f460c054650ae64f0"
_WO003_SESSION_B_ACCEPTED_WORKFLOW = "33476969423"
_WO003_SESSION_B_ACCEPTED_JOB = "99758148278"
_WO003_SESSION_B_ACCEPTED_GATE = (
    "- Current gate: WO-003 SESSION B ACCEPTED " + _EM
    + " REPOSITORY DESCRIPTION APPLICATION NOT AUTHORIZED"
)
_WO003_SESSION_B_ACCEPTED_MARKER = (
    "AUTHORIZATION: ISSUED " + _EM
    + " SESSION B ACCEPTED; NO SESSION AUTHORIZED"
)
_WO003_SESSION_B_ACCEPTED_NEXT_GATE = (
    "NEXT GATE: separate BDFL/owner authorization to apply the exact accepted"
    + _NL + "repository description. Metadata application remains unauthorized"
    + " until that" + _NL + "explicit gate."
)
_WO003_SESSION_B_ACCEPTED_STATEMENT = (
    "This Work Order remains issued. Session A is accepted and complete."
    + " Session B" + _NL
    + "is accepted and complete. Repository-description application, Session C"
    + " or any" + _NL
    + "later session, WO-004, tagging, Release creation, and social publication"
    + _NL + "remain unauthorized."
)
_WO003_SESSION_B_ACCEPTED_POINTER_STATEMENT = (
    "Session B's repository-description draft was independently accepted."
    + " The" + _NL + "accepted draft was committed and pushed as" + _NL
    + "`" + _WO003_SESSION_B_ACCEPTED_BASE + "`; successful CI workflow"
    + _NL + "`" + _WO003_SESSION_B_ACCEPTED_WORKFLOW
    + "` included successful required job `"
    + _WO003_SESSION_B_ACCEPTED_JOB + "` (`Lint, types," + _NL
    + "tests`). The live GitHub repository description is unchanged."
    + " Applying the" + _NL
    + "exact accepted repository description remains a separate"
    + " owner-authorized" + _NL
    + "external action. Metadata application, tags, Releases, and social"
    + " publication" + _NL
    + "all remain unauthorized, as do Session C and WO-004."
)
_WO003_SESSION_B_ACCEPTANCE_HEADING = "## Session B acceptance record"
_WO003_ACCEPTED_DESCRIPTION_PREFIX = (
    "ACCEPTED_REPOSITORY_DESCRIPTION_NOT_APPLIED: `"
)
_WO003_ACCEPTED_DESCRIPTION_FIELD = (
    _WO003_ACCEPTED_DESCRIPTION_PREFIX + _WO003_DESCRIPTION_DRAFT + "`"
)
_WO003_ACCEPTED_COUNT_FIELD = (
    "ACCEPTED_DESCRIPTION_CHARACTER_COUNT: `"
    + str(_WO003_DESCRIPTION_DRAFT_LENGTH) + "`"
)
_WO003_ISSUED_GATE = (
    "- Current gate: WO-003 ISSUED " + _EM
    + " SESSION A IMPLEMENTATION NOT AUTHORIZED"
)
_WO003_ISSUED_MARKER = "AUTHORIZATION: ISSUED " + _EM + " SESSION NOT AUTHORIZED"
# The four semantic-preserving corrections applied at issuance. Each avoids a
# false positive in the session scanner while keeping the accepted meaning.
_WO003_CORRECTED_WORDING = (
    "play-session launch, termination, and inspection operations",
    "attempted activation of Session B or application of repository metadata",
    "Session B is authorized under the current root `WORKORDER.md` gate",
    "run a play session, activate the custom bridge",
)


def _wo003_finding_types(repo_root, tmp_path, monkeypatch, name, mutate):
    """Findings drift_check reports for a mutated issued WO-003 state."""
    drift_check = _load_drift_check(repo_root, "wo003_" + name)
    case = _make_wo003_issued_case(repo_root, tmp_path, "wo003-" + name)
    mutate(case)
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return {
        finding["type"] for finding in drift_check.check_work_order_contract()
    } - {_TERMINAL_WO003_FINDING}


def test_wo003_issued_state_is_clean(repo_root, tmp_path, monkeypatch) -> None:
    """The corrected canonical issued document raises no finding at all.

    Both session detectors produced false positives on the accepted mandate's
    own prose before the four wording corrections. This pins that they stay
    silent.
    """
    found = _wo003_finding_types(
        repo_root, tmp_path, monkeypatch, "control", lambda case: None
    )
    assert found == set(), "the issued WO-003 state is not clean: " + repr(
        sorted(found)
    )
    assert not (found & {"implicit session authorization",
                         "later session authorization"})


@pytest.mark.parametrize("phrase", _WO003_CORRECTED_WORDING)
def test_wo003_corrected_wording_is_present(repo_root, phrase) -> None:
    """The four corrections stay in place, carrying the accepted meaning."""
    text = (repo_root / _WO003_REL).read_text(encoding="utf-8")
    assert phrase in text, "issuance wording correction lost: " + phrase


def test_wo003_retains_no_scanner_tripping_wording(repo_root) -> None:
    """Non-vacuous: the exact strings that tripped the scanner are gone."""
    text = (repo_root / _WO003_REL).read_text(encoding="utf-8")
    for gone in (
        "play-session start/stop/inspect",
        "Session B or metadata application becoming implicitly authorized",
        "Session B is a separately authorized drafting session",
        "start a play session, start the custom bridge",
    ):
        assert gone not in text, "scanner-tripping wording returned: " + gone


@pytest.mark.parametrize(("name", "rel", "old", "new", "expected"), (
    ("pointer-work-order", "WORKORDER.md",
     "- Current issued Work Order: WO-003",
     "- Current issued Work Order: NONE",
     "unpointed issued work order"),
    ("pointer-session", "WORKORDER.md",
     "- Authorized session: NONE", "- Authorized session: A",
     "authorized session gate"),
    ("base-commit", "WORKORDER.md",
     "- Base commit: `" + _WO003_ISSUANCE_COMMIT + "`",
     "- Base commit: `" + _WRONG_COMMIT + "`",
     "WO-003 issuance base commit"),
    ("gate", "WORKORDER.md", _WO003_ISSUED_GATE,
     "- Current gate: WO-003 ISSUED " + _EM + " SESSION A MAY BEGIN",
     "closed session gate"),
    ("marker", _WO003_REL, _WO003_ISSUED_MARKER,
     "AUTHORIZATION: ISSUED " + _EM + " SESSION A AUTHORIZED",
     "issued session authorization"),
    ("planning-baseline", _WO003_REL,
     "BASELINE: `" + _WO003_PLANNING_BASELINE + "`",
     "BASELINE: `" + _WRONG_COMMIT + "`",
     "WO-003 planning baseline"),
    ("release-train", "WORKORDER.md",
     "- Release train: WO-001 through WO-007",
     "- Release train: WO-001 through WO-008", "release train"),
    ("release-gate", "WORKORDER.md",
     "- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED",
     "- Release gate: TAG AND GITHUB RELEASE AUTHORIZED",
     "release authorization"),
))
def test_wo003_issued_contract_is_exact(
    repo_root, tmp_path, monkeypatch, name, rel, old, new, expected
):
    """Pointer, markers, baseline, issuance evidence and gates are each pinned."""
    found = _wo003_finding_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _edit(case, rel, old, new),
    )
    assert expected in found, (
        name + " was accepted; drift_check reported " + repr(sorted(found))
    )


@pytest.mark.parametrize("activation", (
    "Session A is authorized and may begin.",
    "Session B is authorized to proceed.",
    "Session C is cleared to start implementation.",
))
def test_wo003_issuance_rejects_session_activation(
    repo_root, tmp_path, monkeypatch, activation
):
    """Issuance grants no implementation authority to any session."""
    found = _wo003_finding_types(
        repo_root, tmp_path, monkeypatch,
        "activation-" + activation.split()[1],
        lambda case: _edit(
            case, "WORKORDER.md",
            "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-007" + _NL + _NL + activation,
        ),
    )
    assert found & {"implicit session authorization",
                    "later session authorization",
                    "next work order authorization"}, (
        "session activation was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize("destination", ("proposed", "completed", "superseded"))
def test_wo003_cannot_be_duplicated_into_another_state(
    repo_root, tmp_path, monkeypatch, destination
):
    """WO-003 lives in exactly one state directory."""
    def duplicate(case):
        issued = case / _WO003_REL
        copy_dir = case / "docs" / "work-orders" / destination
        copy_dir.mkdir(parents=True, exist_ok=True)
        copy_target = copy_dir / "WO-003-official-mcp-doc-convergence.md"
        copy_target.write_text(issued.read_text(encoding="utf-8"), encoding="utf-8")

    found = _wo003_finding_types(
        repo_root, tmp_path, monkeypatch, "dup-" + destination, duplicate
    )
    assert found & {"duplicate work order state", "WO-003 state",
                    "release train proposal set"}, (
        "a duplicate WO-003 under " + destination + " was accepted: "
        + repr(sorted(found))
    )


def test_wo003_issuance_preserves_wo002_terminal_lock(
    repo_root, tmp_path, monkeypatch
):
    """Issuing WO-003 does not loosen WO-002's one-way completion."""
    def reopen(case):
        completed = (case / "docs" / "work-orders" / "completed"
                     / "WO-002-epic-toolset-integration.md")
        issued = (case / "docs" / "work-orders" / "issued"
                  / "WO-002-epic-toolset-integration.md")
        completed.replace(issued)

    found = _wo003_finding_types(
        repo_root, tmp_path, monkeypatch, "wo002-reopened", reopen
    )
    assert "completed WO-002 state" in found, (
        "WO-002's terminal lock stopped firing after WO-003 issuance: "
        + repr(sorted(found))
    )


_WO003_FIELD_MARKERS = (
    ("commit", _WO003_REL,
     "ISSUANCE_COMMIT: `" + _WO003_ISSUANCE_COMMIT + "`",
     "ISSUANCE_COMMIT: `" + _WRONG_COMMIT + "`",
     _WO003_ISSUANCE_COMMIT, "issued record"),
    ("workflow", _WO003_REL,
     "ISSUANCE_CI_WORKFLOW: `" + _WO003_ISSUANCE_WORKFLOW + "`",
     "ISSUANCE_CI_WORKFLOW: `" + _WRONG_WORKFLOW + "`",
     _WO003_ISSUANCE_WORKFLOW, "issued record"),
    ("job", _WO003_REL,
     "ISSUANCE_CI_JOB: `" + _WO003_ISSUANCE_JOB + "` " + _EM
     + " Lint, types, tests",
     "ISSUANCE_CI_JOB: `" + _WRONG_JOB + "` " + _EM + " Lint, types, tests",
     _WO003_ISSUANCE_JOB, "issued record"),
    ("pointer-commit", "WORKORDER.md",
     "- Issuance commit: `" + _WO003_ISSUANCE_COMMIT + "`",
     "- Issuance commit: `" + _WRONG_COMMIT + "`",
     _WO003_ISSUANCE_COMMIT, "WORKORDER.md"),
    ("pointer-workflow", "WORKORDER.md",
     "- Issuance CI workflow: `" + _WO003_ISSUANCE_WORKFLOW + "`",
     "- Issuance CI workflow: `" + _WRONG_WORKFLOW + "`",
     _WO003_ISSUANCE_WORKFLOW, "WORKORDER.md"),
    ("pointer-job", "WORKORDER.md",
     "- Issuance CI job: `" + _WO003_ISSUANCE_JOB + "` " + _EM
     + " Lint, types, tests",
     "- Issuance CI job: `" + _WRONG_JOB + "` " + _EM + " Lint, types, tests",
     _WO003_ISSUANCE_JOB, "WORKORDER.md"),
)
_WO003_FIELD_FINDING = "WO-003 issuance field ("


def _wo003_field_types(repo_root, tmp_path, monkeypatch, name, mutate):
    return _wo003_finding_types(repo_root, tmp_path, monkeypatch, name, mutate)


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "bare", "where"), _WO003_FIELD_MARKERS
)
def test_wo003_issuance_field_rejects_a_bare_decoy(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, bare, where
):
    """A correct identifier pasted elsewhere cannot repair a corrupted field."""
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        target.write_text(
            text.replace(marker, corrupt, 1) + _NL + "<!-- " + bare + " -->" + _NL,
            encoding="utf-8",
        )

    found = _wo003_field_types(repo_root, tmp_path, monkeypatch,
                               "bare-decoy-" + kind, mutate)
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        kind + " bare decoy was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "bare", "where"), _WO003_FIELD_MARKERS
)
def test_wo003_issuance_field_rejects_a_full_marker_decoy(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, bare, where
):
    """Even a byte-correct marker outside the canonical block does not count.

    This is the case every occurrence-counting design lost to: the field is
    identified by position in the top block, not by appearing somewhere.
    """
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        target.write_text(
            text.replace(marker, corrupt, 1) + _NL + marker + _NL,
            encoding="utf-8",
        )

    found = _wo003_field_types(repo_root, tmp_path, monkeypatch,
                               "marker-decoy-" + kind, mutate)
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        kind + " full-marker decoy was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "bare", "where"), _WO003_FIELD_MARKERS
)
def test_wo003_issuance_field_rejects_duplication(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, bare, where
):
    """Two declarations of the same field are ambiguous, never acceptable."""
    found = _wo003_field_types(
        repo_root, tmp_path, monkeypatch, "dup-" + kind,
        lambda case: _edit(case, rel, marker, marker + _NL + _NL + marker),
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        kind + " duplication was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "bare", "where"), _WO003_FIELD_MARKERS
)
def test_wo003_issuance_field_rejects_removal(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, bare, where
):
    """A missing field fails loudly rather than passing as clean input."""
    found = _wo003_field_types(
        repo_root, tmp_path, monkeypatch, "gone-" + kind,
        lambda case: _edit(case, rel, marker, "REMOVED_FIELD: none"),
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        kind + " removal was accepted: " + repr(sorted(found))
    )


def test_wo003_issuance_fields_are_clean_when_canonical(
    repo_root, tmp_path, monkeypatch
):
    """Non-vacuous: the unchanged canonical state raises no issuance finding."""
    found = _wo003_field_types(
        repo_root, tmp_path, monkeypatch, "field-control", lambda case: None
    )
    assert not {item for item in found if item.startswith("WO-003 issuance")}, (
        "the canonical issuance fields are not clean: " + repr(sorted(found))
    )
    assert found == set()


# Structural intrusions, deliberately including a wrapper the checker has
# never heard of and one that is not a wrapper at all. Slice equality rejects
# each without knowing what any of them mean.
_WO003_WRAPPERS = (
    ("html-comment", "<!--", "-->"),
    ("fenced-code", "```", "```"),
    ("details", "<details>", "</details>"),
    ("plain-lines", "NOTE: injected", "NOTE: trailing"),
)
_WO003_WRAPPED_TARGETS = (
    ("issued-commit", _WO003_REL,
     "ISSUANCE_COMMIT: `" + _WO003_ISSUANCE_COMMIT + "`",
     "ISSUANCE_COMMIT: `" + _WRONG_COMMIT + "`", "issued record"),
    ("issued-workflow", _WO003_REL,
     "ISSUANCE_CI_WORKFLOW: `" + _WO003_ISSUANCE_WORKFLOW + "`",
     "ISSUANCE_CI_WORKFLOW: `" + _WRONG_WORKFLOW + "`", "issued record"),
    ("pointer-commit", "WORKORDER.md",
     "- Issuance commit: `" + _WO003_ISSUANCE_COMMIT + "`",
     "- Issuance commit: `" + _WRONG_COMMIT + "`", "WORKORDER.md"),
    ("pointer-workflow", "WORKORDER.md",
     "- Issuance CI workflow: `" + _WO003_ISSUANCE_WORKFLOW + "`",
     "- Issuance CI workflow: `" + _WRONG_WORKFLOW + "`", "WORKORDER.md"),
)


@pytest.mark.parametrize(("wrapper", "opener", "closer"), _WO003_WRAPPERS)
@pytest.mark.parametrize(
    ("target", "rel", "marker", "corrupt", "where"), _WO003_WRAPPED_TARGETS
)
def test_wo003_wrapped_field_does_not_satisfy_the_canonical_block(
    repo_root, tmp_path, monkeypatch,
    target, rel, marker, corrupt, where, wrapper, opener, closer,
):
    """A wrapped copy inside the block is structure, not a declaration.

    Membership matching accepted this: the line still began with the field key
    and still sat inside the canonical block, so an HTML comment or fenced code
    block holding a byte-correct field stood in for the real one.
    """
    def mutate(case):
        target_path = case / rel
        text = target_path.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        text = text.replace(
            marker,
            corrupt + _NL + _NL + opener + _NL + marker + _NL + closer, 1
        )
        target_path.write_text(text, encoding="utf-8")

    found = _wo003_field_types(
        repo_root, tmp_path, monkeypatch,
        "wrapped-" + wrapper + "-" + target, mutate,
    )
    assert "WO-003 issuance field (" + where + ")" in found, (
        target + " satisfied by a " + wrapper + " wrapper: " + repr(sorted(found))
    )


@pytest.mark.parametrize(("wrapper", "opener", "closer"), _WO003_WRAPPERS)
@pytest.mark.parametrize(("rel", "where"), (
    (_WO003_REL, "issued record"),
    ("WORKORDER.md", "WORKORDER.md"),
))
def test_wo003_canonical_slice_rejects_an_intruding_line(
    repo_root, tmp_path, monkeypatch, rel, where, wrapper, opener, closer
):
    """Any line between the canonical declarations breaks the slice.

    This is why the check is slice equality rather than a wrapper blacklist:
    the intruder does not have to be markup, and the checker does not have to
    recognise it.
    """
    anchor = ("BASELINE: `" + _WO003_PLANNING_BASELINE + "`"
              if rel == _WO003_REL else "- Authorized session: NONE")

    found = _wo003_field_types(
        repo_root, tmp_path, monkeypatch, "wrapper-only-" + wrapper + "-" + where,
        lambda case: _edit(
            case, rel, anchor,
            anchor + _NL + _NL + opener + _NL + "noise" + _NL + closer,
        ),
    )
    assert "WO-003 issuance field (" + where + ")" in found, (
        wrapper + " inside the " + where + " canonical block was accepted: "
        + repr(sorted(found))
    )


def test_wo003_issued_metadata_order_is_enforced(
    repo_root, tmp_path, monkeypatch
):
    """The declarations must appear in their canonical order, not merely exist."""
    marker = "ISSUANCE_COMMIT: `" + _WO003_ISSUANCE_COMMIT + "`"

    def reorder(case):
        target = case / _WO003_REL
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1
        text = text.replace(_NL + marker, "", 1)
        text = text.replace(
            "ISSUANCE_CI_JOB:", marker + _NL + _NL + "ISSUANCE_CI_JOB:", 1
        )
        target.write_text(text, encoding="utf-8")

    found = _wo003_field_types(
        repo_root, tmp_path, monkeypatch, "order", reorder
    )
    assert "WO-003 issuance field (issued record)" in found, (
        "out-of-order canonical metadata was accepted: " + repr(sorted(found))
    )


_WO003_RELEASE_GATE_LINE = "- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED"


@pytest.mark.parametrize(("name", "intruder"), (
    ("duplicate-issuance-commit",
     "- Issuance commit: `" + _WO003_ISSUANCE_COMMIT + "`"),
    ("duplicate-issuance-workflow",
     "- Issuance CI workflow: `" + _WO003_ISSUANCE_WORKFLOW + "`"),
    ("plain-line", "NOTE: injected"),
))
def test_wo003_pointer_slice_is_terminal(
    repo_root, tmp_path, monkeypatch, name, intruder
):
    """Nothing may follow the canonical nine before the WO-001 record.

    A non-terminal slice let a second byte-correct declaration sit after
    `Release gate`, so the canonical block could hold two of the same field
    while every positional check still passed.
    """
    def append_after_gate(case):
        pointer = case / "WORKORDER.md"
        text = pointer.read_text(encoding="utf-8")
        assert text.count(_WO003_RELEASE_GATE_LINE) == 1, (
            "probe anchor drifted: " + _WO003_RELEASE_GATE_LINE
        )
        head, _, tail = text.partition(_WO003_RELEASE_GATE_LINE)
        line_end = tail.index(_NL)
        pointer.write_text(
            head + _WO003_RELEASE_GATE_LINE + tail[:line_end + 1]
            + intruder + _NL + tail[line_end + 1:],
            encoding="utf-8",
        )

    found = _wo003_field_types(
        repo_root, tmp_path, monkeypatch, "terminal-" + name, append_after_gate
    )
    assert "WO-003 issuance field (WORKORDER.md)" in found, (
        name + " after the canonical slice was accepted: " + repr(sorted(found))
    )


# ── WO-003 Session A authorization ────────────────────────────────────────────
#
# Authorizing a session moves the canonical block forward. The risk is not that
# the new declarations go unchecked - it is that the *old* ones quietly stop
# being checked because the enforcement lived inside the closed-session branch.
# Every probe below therefore runs against the authorized state, and the
# issuance-record family exists specifically to catch that silence.

_WO003_SESSION_A_GATE = (
    "- Current gate: WO-003 SESSION A AUTHORIZED " + _EM
    + " IMPLEMENT SESSION A ONLY"
)
_WO003_SESSION_A_MARKER = (
    "AUTHORIZATION: ISSUED " + _EM + " SESSION A AUTHORIZED FOR IMPLEMENTATION"
)
_WO003_SESSION_A_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted"
    + _NL + "Session A implementation. Session B remains unauthorized."
)


def _wo003_session_a_types(repo_root, tmp_path, monkeypatch, name, mutate):
    """Findings drift_check reports for a mutated authorized Session A state."""
    drift_check = _load_drift_check(repo_root, "wo003_a_" + name)
    case = _make_wo003_session_a_case(repo_root, tmp_path, "wo003-a-" + name)
    mutate(case)
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return {
        finding["type"] for finding in drift_check.check_work_order_contract()
    } - {_TERMINAL_WO003_FINDING}


def test_wo003_session_a_state_is_clean(repo_root, tmp_path, monkeypatch) -> None:
    """Non-vacuous: the live authorized state raises no finding at all."""
    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "control", lambda case: None
    )
    assert found == set(), (
        "the authorized WO-003 Session A state is not clean: " + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "rel", "old", "new", "expected"), (
    ("session-field", "WORKORDER.md",
     "- Authorized session: A", "- Authorized session: NONE",
     "WO-003 issued gate"),
    ("gate", "WORKORDER.md", _WO003_SESSION_A_GATE,
     "- Current gate: WO-003 SESSION A AUTHORIZED " + _EM + " DO ANYTHING",
     "authorized session gate"),
    ("base-commit", "WORKORDER.md",
     "- Base commit: `" + _WO003_SESSION_A_BASE + "`",
     "- Base commit: `" + _WRONG_COMMIT + "`",
     "WO-003 Session A base commit"),
    ("authorization-marker", _WO003_REL, _WO003_SESSION_A_MARKER,
     "AUTHORIZATION: ISSUED " + _EM + " SESSION A MAY DO ANYTHING",
     "issued session authorization"),
    ("next-gate", _WO003_REL, _WO003_SESSION_A_NEXT_GATE,
     "NEXT GATE: none.", "WO-003 next gate"),
    ("authorization-statement", _WO003_REL,
     "Session A is authorized for implementation under the current root",
     "Session A is authorized for implementation by this document",
     "WO-003 Session A authorization statement"),
    ("planning-baseline", _WO003_REL,
     "BASELINE: `" + _WO003_PLANNING_BASELINE + "`",
     "BASELINE: `" + _WRONG_COMMIT + "`",
     "WO-003 planning baseline"),
))
def test_wo003_session_a_contract_is_exact(
    repo_root, tmp_path, monkeypatch, name, rel, old, new, expected
):
    """Gate, base, marker, next gate, statement and baseline are each pinned."""
    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _edit(case, rel, old, new),
    )
    assert expected in found, (
        name + " was accepted; drift_check reported " + repr(sorted(found))
    )


# The declarations added by the authorization, and the issuance declarations
# that must keep being checked alongside them.
_WO003_SESSION_A_MARKERS = (
    ("a-commit", _WO003_REL,
     "SESSION_A_AUTHORIZATION_COMMIT: `" + _WO003_SESSION_A_BASE + "`",
     "SESSION_A_AUTHORIZATION_COMMIT: `" + _WRONG_COMMIT + "`",
     _WO003_SESSION_A_BASE, "issued record"),
    ("a-workflow", _WO003_REL,
     "SESSION_A_AUTHORIZATION_CI_WORKFLOW: `" + _WO003_SESSION_A_WORKFLOW + "`",
     "SESSION_A_AUTHORIZATION_CI_WORKFLOW: `" + _WRONG_WORKFLOW + "`",
     _WO003_SESSION_A_WORKFLOW, "issued record"),
    ("a-job", _WO003_REL,
     "SESSION_A_AUTHORIZATION_CI_JOB: `" + _WO003_SESSION_A_JOB + "` " + _EM
     + " Lint, types, tests",
     "SESSION_A_AUTHORIZATION_CI_JOB: `" + _WRONG_JOB + "` " + _EM
     + " Lint, types, tests",
     _WO003_SESSION_A_JOB, "issued record"),
    ("a-pointer-commit", "WORKORDER.md",
     "- Session A authorization commit: `" + _WO003_SESSION_A_BASE + "`",
     "- Session A authorization commit: `" + _WRONG_COMMIT + "`",
     _WO003_SESSION_A_BASE, "WORKORDER.md"),
    ("a-pointer-workflow", "WORKORDER.md",
     "- Session A authorization CI workflow: `" + _WO003_SESSION_A_WORKFLOW + "`",
     "- Session A authorization CI workflow: `" + _WRONG_WORKFLOW + "`",
     _WO003_SESSION_A_WORKFLOW, "WORKORDER.md"),
    ("a-pointer-job", "WORKORDER.md",
     "- Session A authorization CI job: `" + _WO003_SESSION_A_JOB + "` " + _EM
     + " Lint, types, tests",
     "- Session A authorization CI job: `" + _WRONG_JOB + "` " + _EM
     + " Lint, types, tests",
     _WO003_SESSION_A_JOB, "WORKORDER.md"),
)

_WO003_AUTHORIZED_ISSUANCE_MARKERS = (
    ("i-commit", _WO003_REL,
     "ISSUANCE_COMMIT: `" + _WO003_ISSUANCE_COMMIT + "`",
     "ISSUANCE_COMMIT: `" + _WRONG_COMMIT + "`",
     _WO003_ISSUANCE_COMMIT, "issued record"),
    ("i-workflow", _WO003_REL,
     "ISSUANCE_CI_WORKFLOW: `" + _WO003_ISSUANCE_WORKFLOW + "`",
     "ISSUANCE_CI_WORKFLOW: `" + _WRONG_WORKFLOW + "`",
     _WO003_ISSUANCE_WORKFLOW, "issued record"),
    ("i-job", _WO003_REL,
     "ISSUANCE_CI_JOB: `" + _WO003_ISSUANCE_JOB + "` " + _EM
     + " Lint, types, tests",
     "ISSUANCE_CI_JOB: `" + _WRONG_JOB + "` " + _EM + " Lint, types, tests",
     _WO003_ISSUANCE_JOB, "issued record"),
    ("i-pointer-commit", "WORKORDER.md",
     "- Issuance commit: `" + _WO003_ISSUANCE_COMMIT + "`",
     "- Issuance commit: `" + _WRONG_COMMIT + "`",
     _WO003_ISSUANCE_COMMIT, "WORKORDER.md"),
    ("i-pointer-workflow", "WORKORDER.md",
     "- Issuance CI workflow: `" + _WO003_ISSUANCE_WORKFLOW + "`",
     "- Issuance CI workflow: `" + _WRONG_WORKFLOW + "`",
     _WO003_ISSUANCE_WORKFLOW, "WORKORDER.md"),
    ("i-pointer-job", "WORKORDER.md",
     "- Issuance CI job: `" + _WO003_ISSUANCE_JOB + "` " + _EM
     + " Lint, types, tests",
     "- Issuance CI job: `" + _WRONG_JOB + "` " + _EM + " Lint, types, tests",
     _WO003_ISSUANCE_JOB, "WORKORDER.md"),
)

_WO003_AUTHORIZED_MARKERS = (
    _WO003_SESSION_A_MARKERS + _WO003_AUTHORIZED_ISSUANCE_MARKERS
)


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "bare", "where"),
    _WO003_AUTHORIZED_MARKERS,
)
def test_wo003_authorized_field_rejects_a_bare_decoy(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, bare, where
):
    """A correct identifier pasted elsewhere cannot repair a corrupted field."""
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        target.write_text(
            text.replace(marker, corrupt, 1) + _NL + "<!-- " + bare + " -->" + _NL,
            encoding="utf-8",
        )

    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "bare-decoy-" + kind, mutate
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        kind + " bare decoy was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "bare", "where"),
    _WO003_AUTHORIZED_MARKERS,
)
def test_wo003_authorized_field_rejects_a_full_marker_decoy(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, bare, where
):
    """Even a byte-correct marker outside the canonical slice does not count."""
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        target.write_text(
            text.replace(marker, corrupt, 1) + _NL + marker + _NL,
            encoding="utf-8",
        )

    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "marker-decoy-" + kind, mutate
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        kind + " full-marker decoy was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "bare", "where"),
    _WO003_AUTHORIZED_MARKERS,
)
def test_wo003_authorized_field_rejects_duplication(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, bare, where
):
    """Two declarations of the same field are ambiguous, never acceptable."""
    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "dup-" + kind,
        lambda case: _edit(case, rel, marker, marker + _NL + _NL + marker),
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        kind + " duplication was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "bare", "where"),
    _WO003_AUTHORIZED_MARKERS,
)
def test_wo003_authorized_field_rejects_removal(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, bare, where
):
    """A missing field fails loudly rather than passing as clean input.

    The issuance half of this family is the point: authorizing Session A must
    not let the record that issued WO-003 be dropped unnoticed.
    """
    replacement = ("REMOVED_FIELD: none" if rel == _WO003_REL
                   else "- Removed field: none")
    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "gone-" + kind,
        lambda case: _edit(case, rel, marker, replacement),
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        kind + " removal was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(("rel", "anchor", "where"), (
    (_WO003_REL,
     "SESSION_A_AUTHORIZATION_CI_JOB: `" + _WO003_SESSION_A_JOB + "` " + _EM
     + " Lint, types, tests",
     "issued record"),
    ("WORKORDER.md",
     "- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED",
     "WORKORDER.md"),
))
def test_wo003_authorized_slice_is_terminal(
    repo_root, tmp_path, monkeypatch, rel, anchor, where
):
    """Nothing may follow the canonical slice in the authorized state either."""
    def append_after(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert text.count(anchor) == 1, "probe anchor drifted: " + anchor
        head, _, tail = text.partition(anchor)
        line_end = tail.index(_NL)
        target.write_text(
            head + anchor + tail[:line_end + 1] + "NOTE: injected" + _NL
            + tail[line_end + 1:],
            encoding="utf-8",
        )

    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "terminal-" + where, append_after
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        "a line after the canonical slice was accepted in " + where + ": "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(("rel", "first", "second"), (
    (_WO003_REL,
     "ISSUANCE_CI_WORKFLOW: `" + _WO003_ISSUANCE_WORKFLOW + "`",
     "SESSION_A_AUTHORIZATION_COMMIT: `" + _WO003_SESSION_A_BASE + "`"),
    ("WORKORDER.md",
     "- Issuance CI workflow: `" + _WO003_ISSUANCE_WORKFLOW + "`",
     "- Session A authorization commit: `" + _WO003_SESSION_A_BASE + "`"),
))
def test_wo003_authorized_metadata_order_is_enforced(
    repo_root, tmp_path, monkeypatch, rel, first, second
):
    """The declarations must appear in canonical order, not merely exist."""
    def swap(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        for line in (first, second):
            assert text.count(line) == 1, "probe anchor drifted: " + line
        text = text.replace(first, "\x00", 1).replace(second, first, 1)
        target.write_text(text.replace("\x00", second, 1), encoding="utf-8")

    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "order-" + rel.replace("/", "-"), swap
    )
    assert _WO003_FIELD_FINDING in " ".join(sorted(found)), (
        "out-of-order canonical metadata was accepted: " + repr(sorted(found))
    )


def test_wo003_session_b_activation_is_rejected(
    repo_root, tmp_path, monkeypatch
) -> None:
    """The old external-proof shape cannot stand in for drafting authority."""
    def activate(case):
        _edit(case, "WORKORDER.md",
              "- Authorized session: A", "- Authorized session: B")
        _edit(case, "WORKORDER.md", _WO003_SESSION_A_GATE,
              "- Current gate: WO-003 SESSION B AUTHORIZED " + _EM
              + " EXECUTE EXTERNAL PROOF ONLY")
        _edit(case, _WO003_REL, _WO003_SESSION_A_MARKER,
              "AUTHORIZATION: ISSUED " + _EM
              + " SESSION B AUTHORIZED FOR EXTERNAL PROOF")

    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "session-b", activate
    )
    assert {"authorized session gate", "issued session authorization"} <= found, (
        "the wrong Session B contract was accepted: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize("session", ("C", "AB", "ANY"))
def test_wo003_later_session_labels_are_rejected(
    repo_root, tmp_path, monkeypatch, session
) -> None:
    """Only NONE, A, and B are recognised session values."""
    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "session-" + session,
        lambda case: _edit(case, "WORKORDER.md",
                           "- Authorized session: A",
                           "- Authorized session: " + session),
    )
    assert "authorized session gate" in found, (
        "session " + session + " was accepted: " + repr(sorted(found))
    )


def test_wo003_session_a_preserves_wo002_terminal_lock(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Authorizing Session A does not loosen WO-002's one-way completion."""
    def reopen(case):
        completed = (case / "docs" / "work-orders" / "completed"
                     / "WO-002-epic-toolset-integration.md")
        issued = (case / "docs" / "work-orders" / "issued"
                  / "WO-002-epic-toolset-integration.md")
        completed.replace(issued)

    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "wo002-reopened", reopen
    )
    assert "completed WO-002 state" in found, (
        "WO-002's terminal lock stopped firing under Session A: "
        + repr(sorted(found))
    )


def test_wo003_session_a_preserves_the_release_gate(
    repo_root, tmp_path, monkeypatch
) -> None:
    """An implementation session never opens the tag or Release gate."""
    found = _wo003_session_a_types(
        repo_root, tmp_path, monkeypatch, "release-gate",
        lambda case: _edit(
            case, "WORKORDER.md",
            "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-007" + _NL + _NL
            + "A tag and GitHub Release are authorized for this session.",
        ),
    )
    assert "release authorization" in found, (
        "an opened release gate was accepted under Session A: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(("rel", "anchor", "damaged"), (
    ("WORKORDER.md", "- Authorized session: A", "- Authorized session: a"),
    (_WO003_REL, "## Session A authorization basis",
     "## Session A authorization note"),
    (_WO003_REL,
     "SESSION_A_AUTHORIZATION_COMMIT: `" + _WO003_SESSION_A_BASE + "`",
     "SESSION_A_AUTH_COMMIT: `" + _WO003_SESSION_A_BASE + "`"),
))
def test_wo003_issued_reconstruction_requires_its_anchors(
    repo_root, tmp_path, rel, anchor, damaged
):
    """A drifted anchor must fail loudly, not rebuild today's state.

    Every earlier fixture is now rooted in this reconstruction, so a silent
    no-op here would make the whole historical chain pass vacuously.
    """
    drifted = _make_wo003_session_a_case(
        repo_root, tmp_path, "drifted-" + anchor[:20].replace(" ", "-").replace("/", "-")
    )
    target = drifted / rel
    text = target.read_text(encoding="utf-8")
    assert text.count(anchor) == 1, "this probe's own anchor has drifted"
    target.write_text(text.replace(anchor, damaged, 1), encoding="utf-8")

    with pytest.raises(AssertionError, match=_RECONSTRUCTION_FAILURE):
        _make_wo003_issued_case(drifted, tmp_path, "drifted-issued-case")


def test_wo003_issued_reconstruction_reaches_the_closed_state(
    repo_root, tmp_path, monkeypatch
):
    """The reconstruction lands on the closed-session state and is clean there."""
    found = _wo003_finding_types(
        repo_root, tmp_path, monkeypatch, "reconstruction-control",
        lambda case: None,
    )
    assert found == set(), (
        "the reconstructed issued state is not clean: " + repr(sorted(found))
    )


# ── WO-003 Session A acceptance ───────────────────────────────────────────────

_WO003_SESSION_A_ACCEPTED_GATE = (
    "- Current gate: WO-003 SESSION A ACCEPTED " + _EM
    + " SESSION B NOT AUTHORIZED"
)
_WO003_SESSION_A_ACCEPTED_MARKER = (
    "AUTHORIZATION: ISSUED " + _EM
    + " SESSION A ACCEPTED; NO SESSION AUTHORIZED"
)
_WO003_SESSION_A_ACCEPTED_NEXT_GATE = (
    "NEXT GATE: fresh independent architect review of the complete uncommitted"
    + _NL + "Session A acceptance transition. Session B remains unauthorized."
)
_WO003_SESSION_A_ACCEPTED_STATEMENT = (
    "At the Session A acceptance gate, Session A was accepted and complete with "
    "no current implementation authority; Session B was not authorized pending "
    "separate owner authorization."
)


def _wo003_accepted_types(repo_root, tmp_path, monkeypatch, name, mutate):
    """Findings drift_check reports for a mutated accepted Session A state."""
    drift_check = _load_drift_check(repo_root, "wo003_accepted_" + name)
    case = _make_wo003_accepted_case(
        repo_root, tmp_path, "wo003-accepted-" + name
    )
    mutate(case)
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return {
        finding["type"] for finding in drift_check.check_work_order_contract()
    } - {_TERMINAL_WO003_FINDING}


def test_wo003_session_a_accepted_state_is_clean(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Non-vacuous: the canonical accepted state raises no finding."""
    found = _wo003_accepted_types(
        repo_root, tmp_path, monkeypatch, "control", lambda case: None
    )
    assert found == set(), (
        "the accepted WO-003 Session A state is not clean: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "rel", "old", "new", "expected"), (
    ("session-field", "WORKORDER.md",
     "- Authorized session: NONE", "- Authorized session: A",
     "authorized session gate"),
    ("gate", "WORKORDER.md", _WO003_SESSION_A_ACCEPTED_GATE,
     "- Current gate: WO-003 SESSION A ACCEPTED " + _EM + " SESSION B MAY BEGIN",
     "WO-003 Session A accepted gate"),
    ("base-commit", "WORKORDER.md",
     "- Base commit: `" + _WO003_SESSION_A_ACCEPTED_BASE + "`",
     "- Base commit: `" + _WRONG_COMMIT + "`",
     "WO-003 Session A accepted base commit"),
    ("authorization-marker", _WO003_REL, _WO003_SESSION_A_ACCEPTED_MARKER,
     "AUTHORIZATION: ISSUED " + _EM + " SESSION A AUTHORIZED FOR IMPLEMENTATION",
     "WO-003 Session A accepted authorization"),
    ("next-gate", _WO003_REL, _WO003_SESSION_A_ACCEPTED_NEXT_GATE,
     "NEXT GATE: none.", "WO-003 next gate"),
    ("accepted-statement", _WO003_REL,
     "At the Session A acceptance gate, Session A was accepted and complete with no",
     "Session A acceptance statement removed.",
     "WO-003 Session A accepted statement"),
    ("planning-baseline", _WO003_REL,
     "BASELINE: `" + _WO003_PLANNING_BASELINE + "`",
     "BASELINE: `" + _WRONG_COMMIT + "`", "WO-003 planning baseline"),
))
def test_wo003_session_a_accepted_contract_is_exact(
    repo_root, tmp_path, monkeypatch, name, rel, old, new, expected
):
    """Accepted gate, marker, next gate, statement, and baseline are pinned."""
    found = _wo003_accepted_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _edit(case, rel, old, new),
    )
    assert expected in found, (
        name + " was accepted; drift_check reported " + repr(sorted(found))
    )


_WO003_ACCEPTANCE_MARKERS = (
    ("accepted-commit", _WO003_REL,
     "SESSION_A_ACCEPTANCE_COMMIT: `" + _WO003_SESSION_A_ACCEPTED_BASE + "`",
     "SESSION_A_ACCEPTANCE_COMMIT: `" + _WRONG_COMMIT + "`",
     "issued record"),
    ("accepted-workflow", _WO003_REL,
     "SESSION_A_ACCEPTANCE_CI_WORKFLOW: `"
     + _WO003_SESSION_A_ACCEPTED_WORKFLOW + "`",
     "SESSION_A_ACCEPTANCE_CI_WORKFLOW: `" + _WRONG_WORKFLOW + "`",
     "issued record"),
    ("accepted-job", _WO003_REL,
     "SESSION_A_ACCEPTANCE_CI_JOB: `" + _WO003_SESSION_A_ACCEPTED_JOB + "` "
     + _EM + " Lint, types, tests",
     "SESSION_A_ACCEPTANCE_CI_JOB: `" + _WRONG_JOB + "` " + _EM
     + " Lint, types, tests", "issued record"),
    ("accepted-pointer-commit", "WORKORDER.md",
     "- Session A acceptance commit: `" + _WO003_SESSION_A_ACCEPTED_BASE + "`",
     "- Session A acceptance commit: `" + _WRONG_COMMIT + "`",
     "WORKORDER.md"),
    ("accepted-pointer-workflow", "WORKORDER.md",
     "- Session A acceptance CI workflow: `"
     + _WO003_SESSION_A_ACCEPTED_WORKFLOW + "`",
     "- Session A acceptance CI workflow: `" + _WRONG_WORKFLOW + "`",
     "WORKORDER.md"),
    ("accepted-pointer-job", "WORKORDER.md",
     "- Session A acceptance CI job: `" + _WO003_SESSION_A_ACCEPTED_JOB + "` "
     + _EM + " Lint, types, tests",
     "- Session A acceptance CI job: `" + _WRONG_JOB + "` " + _EM
     + " Lint, types, tests", "WORKORDER.md"),
)


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "where"),
    _WO003_ACCEPTANCE_MARKERS,
)
@pytest.mark.parametrize(
    "damage", ("wrong", "duplicate", "removed", "transplant", "wrapped", "extra")
)
def test_wo003_acceptance_fields_are_structural(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, where, damage
):
    """Acceptance declarations are exact canonical fields, never decoy text."""
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        if damage == "wrong":
            replacement = corrupt
        elif damage == "duplicate":
            replacement = marker + _NL + _NL + marker
        elif damage == "removed":
            replacement = ("REMOVED_FIELD: none" if rel == _WO003_REL
                           else "- Removed field: none")
        elif damage == "transplant":
            target.write_text(
                text.replace(marker, corrupt, 1) + _NL + marker + _NL,
                encoding="utf-8",
            )
            return
        elif damage == "wrapped":
            replacement = corrupt + _NL + _NL + "<!--" + _NL + marker + _NL + "-->"
        else:
            replacement = marker + _NL + "NOTE: injected"
        target.write_text(text.replace(marker, replacement, 1), encoding="utf-8")

    found = _wo003_accepted_types(
        repo_root, tmp_path, monkeypatch, damage + "-" + kind, mutate
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        damage + " acceptance field " + kind + " was accepted: "
        + repr(sorted(found))
    )


def test_wo003_acceptance_record_rejects_a_presence_decoy(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A correct live-evidence phrase outside the record cannot repair it."""
    marker = (
        "362 tools across 55 categories; corrected dashboard About ordering; "
        "matching" + _NL + "source and deployed runtime hashes"
    )
    corrupt = (
        "361 tools across 54 categories; corrected dashboard About ordering; "
        "matching" + _NL + "source and deployed runtime hashes"
    )

    def transplant(case):
        target = case / _WO003_REL
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        target.write_text(
            text.replace(marker, corrupt, 1)
            + _NL + "<!-- " + marker + " -->" + _NL,
            encoding="utf-8",
        )

    found = _wo003_accepted_types(
        repo_root, tmp_path, monkeypatch, "record-transplant", transplant
    )
    assert "WO-003 Session A acceptance record" in found, (
        "an out-of-record evidence decoy repaired the acceptance record: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize("intruder", (
    "<!-- acceptance record decoy -->",
    "```text",
    "NOTE: injected",
))
def test_wo003_acceptance_record_rejects_wrappers_and_extra_lines(
    repo_root, tmp_path, monkeypatch, intruder
) -> None:
    """The bounded record is exact; no wrapper vocabulary is needed."""
    heading = "## Session A acceptance record"
    found = _wo003_accepted_types(
        repo_root, tmp_path, monkeypatch,
        "record-intruder-"
        + intruder.split()[0].replace("<", "x").replace(":", ""),
        lambda case: _edit(case, _WO003_REL, heading,
                           heading + _NL + _NL + intruder),
    )
    assert "WO-003 Session A acceptance record" in found, (
        "an acceptance-record intruder was accepted: " + repr(sorted(found))
    )


def test_wo003_session_a_acceptance_cannot_roll_back(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A coherent document rollback to authorized Session A still fails."""
    drift_check = _load_drift_check(repo_root, "wo003_acceptance_rollback")
    case = _make_wo003_session_a_case(
        repo_root, tmp_path, "wo003-acceptance-rollback"
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    found = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert found == {_TERMINAL_WO003_FINDING}, (
        "the authorized historical reconstruction is incomplete or reopened "
        "without the terminal finding: " + repr(sorted(found))
    )


@pytest.mark.parametrize("session", ("A", "B", "C"))
def test_wo003_accepted_state_rejects_session_reactivation(
    repo_root, tmp_path, monkeypatch, session
) -> None:
    """No labeled session can self-reactivate after Session A acceptance."""
    statement = "Session " + session + " is authorized and may begin."
    found = _wo003_accepted_types(
        repo_root, tmp_path, monkeypatch, "later-" + session,
        lambda case: _append(case, "WORKORDER.md", statement),
    )
    assert "session authorization reopening" in found, (
        statement + " was accepted: " + repr(sorted(found))
    )


def test_wo003_accepted_state_preserves_release_gate(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Accepting Session A never opens tag or Release authority."""
    found = _wo003_accepted_types(
        repo_root, tmp_path, monkeypatch, "release",
        lambda case: _append(
            case, "WORKORDER.md",
            "A tag and GitHub Release are authorized for this session.",
        ),
    )
    assert "release authorization" in found, (
        "the accepted state opened publication authority: " + repr(sorted(found))
    )


# ── WO-003 Session B repository-description drafting ────────────────────────

_WO003_SESSION_B_DRAFT_PREFIX = (
    "PROPOSED_REPOSITORY_DESCRIPTION_DRAFT_NOT_APPLIED: `"
)
_WO003_SESSION_B_DRAFT_FIELD = (
    _WO003_SESSION_B_DRAFT_PREFIX + _WO003_DESCRIPTION_DRAFT + "`"
)
_WO003_SESSION_B_COUNT_FIELD = (
    "PROPOSED_DESCRIPTION_CHARACTER_COUNT: `"
    + str(_WO003_DESCRIPTION_DRAFT_LENGTH) + "`"
)
_WO003_SESSION_B_FIELD_MARKERS = (
    ("b-commit", _WO003_REL,
     "SESSION_B_AUTHORIZATION_COMMIT: `" + _WO003_SESSION_B_BASE + "`",
     "SESSION_B_AUTHORIZATION_COMMIT: `" + _WRONG_COMMIT + "`",
     "issued record"),
    ("b-workflow", _WO003_REL,
     "SESSION_B_AUTHORIZATION_CI_WORKFLOW: `"
     + _WO003_SESSION_B_WORKFLOW + "`",
     "SESSION_B_AUTHORIZATION_CI_WORKFLOW: `" + _WRONG_WORKFLOW + "`",
     "issued record"),
    ("b-job", _WO003_REL,
     "SESSION_B_AUTHORIZATION_CI_JOB: `" + _WO003_SESSION_B_JOB + "` "
     + _EM + " Lint, types, tests",
     "SESSION_B_AUTHORIZATION_CI_JOB: `" + _WRONG_JOB + "` "
     + _EM + " Lint, types, tests", "issued record"),
    ("b-pointer-commit", "WORKORDER.md",
     "- Session B authorization commit: `" + _WO003_SESSION_B_BASE + "`",
     "- Session B authorization commit: `" + _WRONG_COMMIT + "`",
     "WORKORDER.md"),
    ("b-pointer-workflow", "WORKORDER.md",
     "- Session B authorization CI workflow: `"
     + _WO003_SESSION_B_WORKFLOW + "`",
     "- Session B authorization CI workflow: `" + _WRONG_WORKFLOW + "`",
     "WORKORDER.md"),
    ("b-pointer-job", "WORKORDER.md",
     "- Session B authorization CI job: `" + _WO003_SESSION_B_JOB + "` "
     + _EM + " Lint, types, tests",
     "- Session B authorization CI job: `" + _WRONG_JOB + "` "
     + _EM + " Lint, types, tests", "WORKORDER.md"),
)


def _wo003_session_b_types(repo_root, tmp_path, monkeypatch, name, mutate):
    """Findings from a mutated reconstruction of the drafting-only state.

    The reconstruction is historical now, so it always trips the one-way
    accepted-state lock. That finding is subtracted here and asserted on
    its own in the rollback probe.
    """
    drift_check = _load_drift_check(repo_root, "wo003_b_" + name)
    case = _make_wo003_session_b_case(
        repo_root, tmp_path, "wo003-b-" + name
    )
    mutate(case)
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return {
        finding["type"] for finding in drift_check.check_work_order_contract()
    } - {_TERMINAL_WO003_FINDING}


def test_wo003_session_b_drafting_state_is_clean(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Non-vacuous: the exact drafting-only state raises no finding."""
    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, "control", lambda case: None
    )
    assert found == set(), "the Session B draft state is not clean: " + repr(
        sorted(found)
    )
    assert len(_WO003_DESCRIPTION_DRAFT) == _WO003_DESCRIPTION_DRAFT_LENGTH


@pytest.mark.parametrize(("name", "rel", "old", "new", "expected"), (
    ("session", "WORKORDER.md", "- Authorized session: B",
     "- Authorized session: C", "authorized session gate"),
    ("base", "WORKORDER.md", "- Base commit: `" + _WO003_SESSION_B_BASE + "`",
     "- Base commit: `" + _WRONG_COMMIT + "`", "WO-003 Session B base commit"),
    ("gate", "WORKORDER.md", _WO003_SESSION_B_GATE,
     "- Current gate: WO-003 SESSION B AUTHORIZED " + _EM + " APPLY METADATA",
     "authorized session gate"),
    ("marker", _WO003_REL, _WO003_SESSION_B_MARKER,
     "AUTHORIZATION: ISSUED " + _EM + " SESSION B MAY APPLY METADATA",
     "issued session authorization"),
    ("next-gate", _WO003_REL, _WO003_SESSION_B_NEXT_GATE,
     "NEXT GATE: apply the description.", "WO-003 next gate"),
    ("statement", _WO003_REL, _WO003_SESSION_B_STATEMENT,
     "Session B may apply repository metadata.",
     "WO-003 Session B drafting-only statement"),
))
def test_wo003_session_b_contract_is_exact(
    repo_root, tmp_path, monkeypatch, name, rel, old, new, expected
) -> None:
    """The drafting gate, base, marker, next gate and boundary are exact."""
    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _edit(case, rel, old, new),
    )
    assert expected in found, (
        name + " was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "where"),
    _WO003_SESSION_B_FIELD_MARKERS,
)
@pytest.mark.parametrize(
    "damage", ("wrong", "removed", "duplicate", "transplant", "wrapped", "extra")
)
def test_wo003_session_b_authorization_fields_are_structural(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, where, damage
) -> None:
    """Every B authorization field is an exact canonical declaration."""
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        if damage == "wrong":
            replacement = corrupt
        elif damage == "removed":
            replacement = ("REMOVED_FIELD: none" if rel == _WO003_REL
                           else "- Removed field: none")
        elif damage == "duplicate":
            replacement = marker + _NL + _NL + marker
        elif damage == "transplant":
            target.write_text(
                text.replace(marker, corrupt, 1) + _NL + marker + _NL,
                encoding="utf-8",
            )
            return
        elif damage == "wrapped":
            replacement = corrupt + _NL + "<!--" + _NL + marker + _NL + "-->"
        else:
            replacement = marker + _NL + "NOTE: injected"
        target.write_text(text.replace(marker, replacement, 1), encoding="utf-8")

    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, damage + "-" + kind, mutate
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        damage + " Session B field " + kind + " was accepted: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "replacement", "expected"), (
    ("removed", "REMOVED_DRAFT: none", "WO-003 Session B draft count"),
    ("duplicate", _WO003_SESSION_B_DRAFT_FIELD + _NL
     + _WO003_SESSION_B_DRAFT_FIELD, "WO-003 Session B draft count"),
    ("stale-tools", _WO003_SESSION_B_DRAFT_FIELD.replace("362", "358+"),
     "WO-003 Session B draft truth"),
    ("stale-categories", _WO003_SESSION_B_DRAFT_FIELD.replace("55", "55+"),
     "WO-003 Session B draft truth"),
    ("stale-offline", _WO003_SESSION_B_DRAFT_FIELD.replace(
        "PySide6 dashboard", "fully-offline PySide6 dashboard"
    ), "WO-003 Session B draft truth"),
    ("missing-experimental", _WO003_SESSION_B_DRAFT_FIELD.replace(
        "experimental, ", ""
    ), "WO-003 Session B draft truth"),
    ("missing-loopback", _WO003_SESSION_B_DRAFT_FIELD.replace(
        "authenticated same-user loopback bridge", "local bridge"
    ), "WO-003 Session B draft truth"),
    ("missing-official", _WO003_SESSION_B_DRAFT_FIELD.replace(
        "Epic's official UEFN MCP", "the built-in service"
    ), "WO-003 Session B draft truth"),
    ("missing-not-exposed", _WO003_SESSION_B_DRAFT_FIELD.replace(
        "not exposed through Epic's MCP server", "integrates with MCP"
    ), "WO-003 Session B draft truth"),
))
def test_wo003_session_b_draft_truth_is_enforced(
    repo_root, tmp_path, monkeypatch, name, replacement, expected
) -> None:
    """Zero/two drafts and each material-truth regression fail independently."""
    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, "draft-" + name,
        lambda case: _edit(
            case, _WO003_REL, _WO003_SESSION_B_DRAFT_FIELD, replacement
        ),
    )
    assert expected in found, (
        name + " draft damage was accepted: " + repr(sorted(found))
    )


def test_wo003_session_b_rejects_a_second_draft_outside_the_record(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Exactly one draft means one in the document, not one per section."""
    def mutate(case):
        target = case / _WO003_REL
        target.write_text(
            target.read_text(encoding="utf-8")
            + _NL + _WO003_SESSION_B_DRAFT_FIELD + _NL,
            encoding="utf-8",
        )

    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, "second-draft-outside", mutate
    )
    assert "WO-003 Session B draft count" in found, (
        "a second draft outside the bounded record was accepted: "
        + repr(sorted(found))
    )


def test_wo003_session_b_draft_length_is_enforced(
    repo_root, tmp_path, monkeypatch
) -> None:
    """The proposed replacement is capped at 350 characters."""
    longer = _WO003_DESCRIPTION_DRAFT + " " + (
        "x" * (350 - len(_WO003_DESCRIPTION_DRAFT))
    )
    assert len(longer) == 351

    def mutate(case):
        _edit(case, _WO003_REL, _WO003_SESSION_B_DRAFT_FIELD,
              _WO003_SESSION_B_DRAFT_PREFIX + longer + "`")
        _edit(case, _WO003_REL, _WO003_SESSION_B_COUNT_FIELD,
              "PROPOSED_DESCRIPTION_CHARACTER_COUNT: `351`")

    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, "draft-length", mutate
    )
    assert "WO-003 Session B draft length" in found, (
        "a 351-character draft was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize("permission", (
    "Repository metadata may now be applied.",
    "Repository metadata was applied.",
    "Repository metadata application is authorized.",
    "The GitHub repository description was changed.",
    "The repository description has been updated.",
    "The GitHub description may be applied.",
    "Social publication may now be published.",
    "Social publication is authorized.",
))
def test_wo003_session_b_rejects_external_action_permission(
    repo_root, tmp_path, monkeypatch, permission
) -> None:
    """Drafting authority never becomes metadata or publication authority."""
    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch,
        "external-" + permission.split()[0].lower(),
        lambda case: _edit(
            case, "WORKORDER.md", "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-007" + _NL + permission,
        ),
    )
    assert "WO-003 Session B external-action boundary" in found, (
        permission + " was accepted: " + repr(sorted(found))
    )


def test_wo003_session_b_rejects_applied_draft_record(
    repo_root, tmp_path, monkeypatch
) -> None:
    """The bounded draft record cannot claim the remote edit happened."""
    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, "applied-record",
        lambda case: _edit(
            case, _WO003_REL, "It is a DRAFT and has" + _NL + "NOT BEEN APPLIED.",
            "It is a DRAFT and HAS BEEN APPLIED.",
        ),
    )
    assert "WO-003 Session B draft record" in found


def test_wo003_session_b_cannot_roll_back_to_session_a_accepted(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A coherent document-only rollback still trips the one-way B lock."""
    drift_check = _load_drift_check(repo_root, "wo003_b_rollback")
    case = _make_wo003_accepted_case(
        repo_root, tmp_path, "wo003-b-rollback"
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    found = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert found == {_TERMINAL_WO003_FINDING}, (
        "the accepted historical state escaped or reconstructed incompletely: "
        + repr(sorted(found))
    )


def test_wo003_session_b_rejects_wo004_activation(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Drafting WO-003 never issues or authorizes WO-004."""
    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, "wo004",
        lambda case: _edit(
            case, "WORKORDER.md", "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-007" + _NL
            + "WO-004 is authorized and may begin.",
        ),
    )
    assert "next work order authorization" in found


def test_wo003_session_b_preserves_release_gate(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Drafting Session B never opens tag or Release authority."""
    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, "release",
        lambda case: _edit(
            case, "WORKORDER.md", "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-007" + _NL
            + "A tag and GitHub Release are authorized.",
        ),
    )
    assert "release authorization" in found


def test_wo003_session_b_does_not_pin_unrelated_mandate_prose(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Harmless prose outside the bounded record remains editable."""
    found = _wo003_session_b_types(
        repo_root, tmp_path, monkeypatch, "unrelated-prose",
        lambda case: _edit(
            case, _WO003_REL,
            "These are the anticipated writable paths;",
            "These paths are the anticipated writable set;",
        ),
    )
    assert found == set(), (
        "unrelated mandate prose was frozen: " + repr(sorted(found))
    )


# ── WO-003 Session B acceptance ──────────────────────────────────────────────
#
# Every probe below runs a temporary copy of the real repository through the
# production `check_work_order_contract()`. Each one reproduces a bypass that
# the checker missed before this transition added its branch, so none of them
# is an imagined shape.

_WO003_SESSION_B_ACCEPTANCE_FIELD_MARKERS = (
    ("accept-commit", _WO003_REL,
     "SESSION_B_ACCEPTANCE_COMMIT: `" + _WO003_SESSION_B_ACCEPTED_BASE + "`",
     "SESSION_B_ACCEPTANCE_COMMIT: `" + _WRONG_COMMIT + "`", "issued record"),
    ("accept-workflow", _WO003_REL,
     "SESSION_B_ACCEPTANCE_CI_WORKFLOW: `"
     + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`",
     "SESSION_B_ACCEPTANCE_CI_WORKFLOW: `" + _WRONG_WORKFLOW + "`",
     "issued record"),
    ("accept-job", _WO003_REL,
     "SESSION_B_ACCEPTANCE_CI_JOB: `" + _WO003_SESSION_B_ACCEPTED_JOB + "` "
     + _EM + " Lint, types, tests",
     "SESSION_B_ACCEPTANCE_CI_JOB: `" + _WRONG_JOB + "` " + _EM
     + " Lint, types, tests", "issued record"),
    ("accept-pointer-commit", "WORKORDER.md",
     "- Session B acceptance commit: `" + _WO003_SESSION_B_ACCEPTED_BASE + "`",
     "- Session B acceptance commit: `" + _WRONG_COMMIT + "`", "WORKORDER.md"),
    ("accept-pointer-workflow", "WORKORDER.md",
     "- Session B acceptance CI workflow: `"
     + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`",
     "- Session B acceptance CI workflow: `" + _WRONG_WORKFLOW + "`",
     "WORKORDER.md"),
    ("accept-pointer-job", "WORKORDER.md",
     "- Session B acceptance CI job: `" + _WO003_SESSION_B_ACCEPTED_JOB + "` "
     + _EM + " Lint, types, tests",
     "- Session B acceptance CI job: `" + _WRONG_JOB + "` " + _EM
     + " Lint, types, tests", "WORKORDER.md"),
)


def _wo003_b_accepted_types(repo_root, tmp_path, monkeypatch, name, mutate):
    """Findings from a mutated copy of the current accepted Session B state."""
    drift_check = _load_drift_check(repo_root, "wo003_ba_" + name)
    case = _make_wo003_session_b_accepted_case(
        repo_root, tmp_path, "wo003-ba-" + name
    )
    mutate(case)
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }


def test_wo003_session_b_accepted_state_is_clean(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Non-vacuous: the canonical accepted state raises no finding at all."""
    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "control", lambda case: None
    )
    assert found == set(), (
        "the accepted WO-003 Session B state is not clean: "
        + repr(sorted(found))
    )
    assert len(_WO003_DESCRIPTION_DRAFT) == _WO003_DESCRIPTION_DRAFT_LENGTH


@pytest.mark.parametrize(("name", "rel", "old", "new", "expected"), (
    ("session-field", "WORKORDER.md", "- Authorized session: NONE",
     "- Authorized session: C", "authorized session gate"),
    ("session-field-b", "WORKORDER.md", "- Authorized session: NONE",
     "- Authorized session: B", "accepted WO-003 Session B state"),
    ("base", "WORKORDER.md",
     "- Base commit: `" + _WO003_SESSION_B_ACCEPTED_BASE + "`",
     "- Base commit: `" + _WRONG_COMMIT + "`",
     "WO-003 Session B accepted base commit"),
    ("gate", "WORKORDER.md", _WO003_SESSION_B_ACCEPTED_GATE,
     "- Current gate: WO-003 SESSION B ACCEPTED " + _EM
     + " APPLY THE DESCRIPTION", "WO-003 Session B accepted gate"),
    ("marker", _WO003_REL, _WO003_SESSION_B_ACCEPTED_MARKER,
     "AUTHORIZATION: ISSUED " + _EM + " SESSION B MAY APPLY METADATA",
     "WO-003 Session B accepted authorization"),
    ("next-gate", _WO003_REL, _WO003_SESSION_B_ACCEPTED_NEXT_GATE,
     "NEXT GATE: apply the description.", "WO-003 next gate"),
    ("statement", _WO003_REL, _WO003_SESSION_B_ACCEPTED_STATEMENT,
     "Session B may apply repository metadata.",
     "WO-003 Session B accepted statement"),
    ("pointer-statement", "WORKORDER.md",
     _WO003_SESSION_B_ACCEPTED_POINTER_STATEMENT,
     "Session B is done.", "WO-003 Session B accepted pointer statement"),
))
def test_wo003_session_b_accepted_contract_is_exact(
    repo_root, tmp_path, monkeypatch, name, rel, old, new, expected
) -> None:
    """Pointer session, base, gate, marker, next gate, and both statements."""
    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _edit(case, rel, old, new),
    )
    assert expected in found, (
        name + " was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("kind", "rel", "marker", "corrupt", "where"),
    _WO003_SESSION_B_ACCEPTANCE_FIELD_MARKERS,
)
@pytest.mark.parametrize(
    "damage", ("wrong", "removed", "duplicate", "transplant", "wrapped", "extra")
)
def test_wo003_session_b_acceptance_fields_are_structural(
    repo_root, tmp_path, monkeypatch, kind, rel, marker, corrupt, where, damage
) -> None:
    """Each acceptance field is an exact canonical slice entry, not text."""
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        if damage == "wrong":
            replacement = corrupt
        elif damage == "removed":
            replacement = ("REMOVED_FIELD: none" if rel == _WO003_REL
                           else "- Removed field: none")
        elif damage == "duplicate":
            replacement = marker + _NL + _NL + marker
        elif damage == "transplant":
            target.write_text(
                text.replace(marker, corrupt, 1) + _NL + marker + _NL,
                encoding="utf-8",
            )
            return
        elif damage == "wrapped":
            replacement = corrupt + _NL + "<!--" + _NL + marker + _NL + "-->"
        else:
            replacement = marker + _NL + "NOTE: injected"
        target.write_text(text.replace(marker, replacement, 1), encoding="utf-8")

    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, damage + "-" + kind, mutate
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        damage + " acceptance field " + kind + " was accepted: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "rel", "first", "second", "joiner", "where"), (
    ("issued", _WO003_REL,
     "SESSION_B_ACCEPTANCE_COMMIT: `" + _WO003_SESSION_B_ACCEPTED_BASE + "`",
     "SESSION_B_ACCEPTANCE_CI_WORKFLOW: `"
     + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`", _NL + _NL, "issued record"),
    ("pointer", "WORKORDER.md",
     "- Session B acceptance commit: `" + _WO003_SESSION_B_ACCEPTED_BASE + "`",
     "- Session B acceptance CI workflow: `"
     + _WO003_SESSION_B_ACCEPTED_WORKFLOW + "`", _NL, "WORKORDER.md"),
))
def test_wo003_session_b_acceptance_order_is_enforced(
    repo_root, tmp_path, monkeypatch, name, rel, first, second, joiner, where
) -> None:
    """Reordering two acceptance declarations breaks the canonical slice."""
    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "reorder-" + name,
        lambda case: _edit(case, rel, first + joiner + second,
                           second + joiner + first),
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        "a reordered acceptance slice was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "rel", "anchor", "padding", "where"), (
    ("issued", _WO003_REL,
     "SESSION_B_ACCEPTANCE_CI_JOB: `" + _WO003_SESSION_B_ACCEPTED_JOB + "` "
     + _EM + " Lint, types, tests",
     "SESSION_C_AUTHORIZATION_COMMIT: `" + _WRONG_COMMIT + "`",
     "issued record"),
    ("pointer", "WORKORDER.md", _WO003_RELEASE_GATE_LINE,
     "- Session C authorization commit: `" + _WRONG_COMMIT + "`",
     "WORKORDER.md"),
))
def test_wo003_session_b_accepted_slice_stays_terminal(
    repo_root, tmp_path, monkeypatch, name, rel, anchor, padding, where
) -> None:
    """Padding appended after the canonical slice is not silently absorbed."""
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        matches = [line for line in text.splitlines()
                   if line.startswith(anchor)]
        assert len(matches) == 1, "probe anchor drifted: " + anchor
        target.write_text(
            text.replace(matches[0], matches[0] + _NL + _NL + padding, 1),
            encoding="utf-8",
        )

    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "terminal-" + name, mutate
    )
    assert _WO003_FIELD_FINDING + where + ")" in found, (
        "padding after the canonical slice was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "old", "new", "expected"), (
    ("accepted-description", _WO003_ACCEPTED_DESCRIPTION_FIELD,
     _WO003_ACCEPTED_DESCRIPTION_PREFIX
     + _WO003_DESCRIPTION_DRAFT.replace("362 Python", "358+ Python") + "`",
     "WO-003 Session B accepted description"),
    ("accepted-description-removed", _WO003_ACCEPTED_DESCRIPTION_FIELD,
     "REMOVED_DESCRIPTION: none",
     "WO-003 Session B accepted description count"),
    ("accepted-description-duplicated", _WO003_ACCEPTED_DESCRIPTION_FIELD,
     _WO003_ACCEPTED_DESCRIPTION_FIELD + _NL
     + _WO003_ACCEPTED_DESCRIPTION_FIELD,
     "WO-003 Session B accepted description count"),
    ("accepted-count", _WO003_ACCEPTED_COUNT_FIELD,
     "ACCEPTED_DESCRIPTION_CHARACTER_COUNT: `262`",
     "WO-003 Session B acceptance record"),
    ("not-applied-status", "still a DRAFT and has NOT BEEN APPLIED",
     "has now BEEN APPLIED", "WO-003 Session B acceptance record"),
    ("live-description-changed",
     "The live GitHub repository description is unchanged.",
     "The live GitHub repository description was updated.",
     "WO-003 Session B acceptance record"),
    ("nothing-published",
     "changed, updated, applied, or published.",
     "published to the repository.", "WO-003 Session B acceptance record"),
    ("proposed-draft", _WO003_SESSION_B_DRAFT_FIELD,
     _WO003_SESSION_B_DRAFT_FIELD.replace("362 Python", "358+ Python"),
     "WO-003 Session B draft truth"),
    ("session-a-record",
     "362 tools across 55 categories; corrected dashboard About ordering",
     "361 tools across 54 categories; corrected dashboard About ordering",
     "WO-003 Session A acceptance record"),
))
def test_wo003_session_b_accepted_preserves_bounded_records(
    repo_root, tmp_path, monkeypatch, name, old, new, expected
) -> None:
    """The accepted draft, its status, and every earlier record stay pinned."""
    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "record-" + name,
        lambda case: _edit(case, _WO003_REL, old, new),
    )
    assert expected in found, (
        name + " damage was accepted: " + repr(sorted(found))
    )


def test_wo003_session_b_acceptance_record_rejects_a_presence_decoy(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A correct phrase parked outside the record cannot repair it."""
    marker = "The live GitHub repository description is unchanged."
    corrupt = "The live GitHub repository description was updated."

    def mutate(case):
        target = case / _WO003_REL
        text = target.read_text(encoding="utf-8")
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        target.write_text(
            text.replace(marker, corrupt, 1)
            + _NL + "<!-- " + marker + " -->" + _NL,
            encoding="utf-8",
        )

    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "record-decoy", mutate
    )
    assert "WO-003 Session B acceptance record" in found, (
        "an out-of-record decoy repaired the acceptance record: "
        + repr(sorted(found))
    )


def test_wo003_session_b_acceptance_record_rejects_an_equivalent_copy(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A whole equivalent record elsewhere cannot stand in for the real one."""
    def mutate(case):
        target = case / _WO003_REL
        text = target.read_text(encoding="utf-8")
        head, sep, tail = text.partition(_WO003_SESSION_B_ACCEPTANCE_HEADING)
        assert sep, "probe anchor drifted: acceptance heading"
        body, following, rest = tail.partition("## Planning basis")
        assert following, "probe anchor drifted: planning basis"
        assert body.count(_WO003_SESSION_B_ACCEPTED_BASE) == 1, body[:200]
        corrupted = body.replace(
            _WO003_SESSION_B_ACCEPTED_BASE, _WRONG_COMMIT, 1
        )
        target.write_text(
            head + sep + corrupted + following + rest + _NL
            + "## Preserved acceptance copy" + body,
            encoding="utf-8",
        )

    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "record-copy", mutate
    )
    assert "WO-003 Session B acceptance record" in found, (
        "an equivalent record planted elsewhere was accepted: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize("intruder", (
    "<!-- acceptance record decoy -->",
    "```text",
    "NOTE: injected",
))
def test_wo003_session_b_acceptance_record_rejects_wrappers(
    repo_root, tmp_path, monkeypatch, intruder
) -> None:
    """The bounded record is exact; no wrapper vocabulary is needed."""
    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch,
        "record-intruder-"
        + intruder.split()[0].replace("<", "x").replace(":", ""),
        lambda case: _edit(
            case, _WO003_REL, _WO003_SESSION_B_ACCEPTANCE_HEADING,
            _WO003_SESSION_B_ACCEPTANCE_HEADING + _NL + _NL + intruder,
        ),
    )
    assert "WO-003 Session B acceptance record" in found, (
        "an acceptance-record intruder was accepted: " + repr(sorted(found))
    )


def test_wo003_session_b_acceptance_record_requires_a_unique_heading(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A duplicated heading destroys the anchor and must fail closed."""
    def mutate(case):
        target = case / _WO003_REL
        target.write_text(
            target.read_text(encoding="utf-8") + _NL
            + _WO003_SESSION_B_ACCEPTANCE_HEADING + _NL,
            encoding="utf-8",
        )

    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "record-duplicate-heading", mutate
    )
    assert "WO-003 Session B acceptance record" in found, (
        "a duplicated acceptance heading was accepted: " + repr(sorted(found))
    )


def test_wo003_session_b_acceptance_cannot_roll_back_to_drafting(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A coherent document-only rollback to drafting still trips the lock."""
    drift_check = _load_drift_check(repo_root, "wo003_ba_rollback")
    case = _make_wo003_session_b_case(
        repo_root, tmp_path, "wo003-ba-rollback"
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    found = {
        finding["type"] for finding in drift_check.check_work_order_contract()
    }
    assert found == {_TERMINAL_WO003_FINDING}, (
        "the drafting reconstruction escaped or rebuilt incompletely: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "statement", "expected"), (
    ("session-a", "Session A is authorized and may begin.",
     "session authorization reopening"),
    ("session-b", "Session B is authorized and may begin.",
     "session authorization reopening"),
    ("session-c", "Session C is authorized and may begin.",
     "session authorization reopening"),
    ("wo004", "WO-004 is authorized and may begin.",
     "next work order authorization"),
    ("tag", "A tag and GitHub Release are authorized.",
     "release authorization"),
    ("release-session", "A release session is authorized.",
     "release authorization"),
    ("metadata-may", "Repository metadata may now be applied.",
     "WO-003 Session B external-action boundary"),
    ("metadata-was", "Repository metadata was applied.",
     "WO-003 Session B external-action boundary"),
    ("metadata-authorized", "Repository metadata application is authorized.",
     "WO-003 Session B external-action boundary"),
    ("description-changed", "The GitHub repository description was changed.",
     "WO-003 Session B external-action boundary"),
    ("description-updated", "The repository description has been updated.",
     "WO-003 Session B external-action boundary"),
    ("description-may", "The GitHub description may be applied.",
     "WO-003 Session B external-action boundary"),
    ("social-published", "Social publication may now be published.",
     "WO-003 Session B external-action boundary"),
    ("social-authorized", "Social publication is authorized.",
     "WO-003 Session B external-action boundary"),
))
def test_wo003_session_b_accepted_rejects_new_authority(
    repo_root, tmp_path, monkeypatch, name, statement, expected
) -> None:
    """Acceptance is not application, activation, publication, or release."""
    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "authority-" + name,
        lambda case: _edit(
            case, "WORKORDER.md", "- Release train: WO-001 through WO-007",
            "- Release train: WO-001 through WO-007" + _NL + statement,
        ),
    )
    assert expected in found, (
        statement + " was accepted: " + repr(sorted(found))
    )


def test_wo003_session_b_accepted_does_not_pin_unrelated_prose(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Control: harmless prose outside every bounded record stays editable."""
    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "unrelated-prose",
        lambda case: _edit(
            case, _WO003_REL,
            "These are the anticipated writable paths;",
            "These paths are the anticipated writable set;",
        ),
    )
    assert found == set(), (
        "unrelated mandate prose was frozen: " + repr(sorted(found))
    )


def test_wo003_session_b_accepted_does_not_pin_unrelated_pointer_prose(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Control: the pointer's own harmless prose stays editable too."""
    found = _wo003_b_accepted_types(
        repo_root, tmp_path, monkeypatch, "unrelated-pointer-prose",
        lambda case: _edit(
            case, "WORKORDER.md",
            "New proposals default to the following release train unless",
            "New proposals join the following release train unless",
        ),
    )
    assert found == set(), (
        "unrelated pointer prose was frozen: " + repr(sorted(found))
    )


# ── WO-003 surface truth contract ─────────────────────────────────────────────
#
# Session A separated four surfaces the documentation had been running together.
# Every probe here reintroduces a sentence the repository *actually carried*
# before the correction, so each one reproduces a real regression rather than an
# imagined shape. The control cases prove the checks are not vacuously green.

_SURFACE_COPY_PATHS = (
    "README.md", "CLAUDE.md", "AGENTS.md", "llms.txt", "ARCHITECTURE.md",
    "SECURITY.md", "TOOL_STATUS.md", "ROADMAP.md", "install.py", "launcher.py",
    "docs/PIPELINE.md", "docs/AI_AUTONOMY.md", "docs/uefn_python_capabilities.md",
    "docs/plugin_dev_guide.md", "docs/UEFN_QUIRKS.md",
    ".claude/mcp_reference.md", ".claude/tool_tables.md",
    "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py",
    "Content/Python/UEFN_Toolbelt/tools/epic_mcp_tools.py",
)
_DASHBOARD_REL = "Content/Python/UEFN_Toolbelt/dashboard_pyside6.py"
_DASHBOARD_LIVE_READ = (
    '        _cat_count  = str(len({t.get("category","") for t in '
    '_tb.registry.list_tools() if t.get("category")}))'
)
_DASHBOARD_FALLBACK = (
    "    except Exception:" + _NL
    + '        _tool_count = "362"' + _NL
    + '        _cat_count  = "55"'
)


def _make_surface_case(repo_root, tmp_path, name):
    """Copy just the paths the surface-truth checks read."""
    case = tmp_path / name
    for rel in _SURFACE_COPY_PATHS:
        target = case / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, target)
    return case


def _surface_types(repo_root, tmp_path, monkeypatch, name, mutate):
    """Findings the production surface checks report for a mutated copy."""
    drift_check = _load_drift_check(repo_root, "surface_" + name)
    case = _make_surface_case(repo_root, tmp_path, "surface-" + name)
    mutate(case)
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    return {
        finding["type"]
        for finding in (drift_check.check_surface_truth_contract()
                        + drift_check.check_dashboard_fallbacks())
    }


def _append(case, rel, text):
    target = case / rel
    target.write_text(
        target.read_text(encoding="utf-8") + _NL + text + _NL, encoding="utf-8"
    )


def test_surface_truth_contract_is_clean_on_the_corrected_tree(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Non-vacuous: the corrected repository raises no surface finding."""
    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "control", lambda case: None
    )
    assert found == set(), "the corrected tree is not clean: " + repr(sorted(found))


# Each entry is a claim WO-003 removed, paired with a path that carried it.
_RETIRED_CLAIM_PROBES = (
    ("epic-locked-claude", "CLAUDE.md",
     "KNOWN HARD LIMITS (Epic must unlock):"),
    ("epic-locked-llms", "llms.txt",
     "The remaining 3% is locked by Epic."),
    ("menu-startup-injection-readme", "README.md",
     "Permanent top-bar menu entry injected on editor startup"),
    ("compiler-unavailable", "docs/PIPELINE.md",
     "| 5 | `system_build_verse` | Waiting for Epic Python compiler API |"),
    ("offline-readme", "README.md",
     "| **No network calls** | Zero outbound HTTP/socket connections |"),
    ("offline-dashboard", _DASHBOARD_REL,
     '# ("0", "network calls ' + _EM + ' fully offline"),'),
    ("menu-renders-readme", "README.md",
     "A **Toolbelt** menu appears in the top menu bar next to Help."),
    ("menu-renders-install", "install.py",
     '# The "Toolbelt" menu appears in the top menu bar automatically'),
    ("restart-absolute-readme", "README.md",
     "You **never need to restart UEFN** when developing for the Toolbelt."),
    ("restart-absolute-plugin", "docs/plugin_dev_guide.md",
     "You don't even need to restart!"),
    ("network-count-readme", "README.md",
     "Two features reach the network: the Plugin Hub and URL import."),
    ("network-count-dashboard", _DASHBOARD_REL,
     '# ("2", "network features — Plugin Hub, URL import"),'),
)


@pytest.mark.parametrize(("name", "rel", "claim"), _RETIRED_CLAIM_PROBES)
def test_surface_truth_contract_rejects_a_retired_claim(
    repo_root, tmp_path, monkeypatch, name, rel, claim
):
    """A claim WO-003 removed cannot come back to a corrected document."""
    found = _surface_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _append(case, rel, claim),
    )
    assert "retired claim" in found, (
        name + " was accepted back into " + rel + ": " + repr(sorted(found))
    )


@pytest.mark.parametrize("rel", (
    "CLAUDE.md", ".claude/tool_tables.md", ".claude/mcp_reference.md",
))
@pytest.mark.parametrize(("kind", "old", "new"), (
    ("softened", "`failed`", "`unproven`"),
    ("inverted", "`failed`", "`passed`"),
    ("unbounded", "`UE::ValkyrieToolset::ToolsetPolicy`", "Epic's server"),
))
def test_accepted_external_result_cannot_be_softened(
    repo_root, tmp_path, monkeypatch, rel, kind, old, new
):
    """WO-002's accepted `failed` result stays stated, with its bound.

    Both halves have to sit on one line: `failed` alone could be about anything,
    and naming ToolsetPolicy without the result does not say what happened.
    """
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        assert old in text, "probe anchor drifted in " + rel + ": " + old
        target.write_text(text.replace(old, new), encoding="utf-8")

    found = _surface_types(
        repo_root, tmp_path, monkeypatch,
        "external-" + kind + "-" + rel.replace("/", "-").replace(".", ""),
        mutate,
    )
    assert "accepted external result" in found, (
        rel + " accepted a " + kind + " external result: " + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "fragment"), (
    ("quirk36-recovery-import", "import UEFN_Toolbelt as tb;"),
    ("quirk36-recovery-call", "tb.register()"),
    ("quirk36-flag", "UEFN MCP Toolsets"),
    ("quirk42-prepare", "prepare_launch.bat"),
    ("quirk42-restore", "restore_after_launch.bat"),
    ("quirk42-zero-py", "zero `.py` files anywhere"),
    ("quirk42-validator", "ContainsPythonData"),
))
def test_preserved_quirks_cannot_lose_their_evidence(
    repo_root, tmp_path, monkeypatch, name, fragment
):
    """Quirk #36 recovery and Quirk #42 launch safety survive intact.

    The section body is what is checked, not the whole file: a heading kept
    while its recovery step is deleted is exactly the loss this rejects.
    """
    def strip(case):
        target = case / "docs/UEFN_QUIRKS.md"
        text = target.read_text(encoding="utf-8")
        assert fragment in text, "probe anchor drifted: " + fragment
        target.write_text(text.replace(fragment, "REMOVED"), encoding="utf-8")

    found = _surface_types(repo_root, tmp_path, monkeypatch, name, strip)
    assert "preserved quirk" in found, (
        fragment + " could be deleted from its quirk: " + repr(sorted(found))
    )


@pytest.mark.parametrize("heading", ("## Quirk #36 " + _EM, "## Quirk #42 " + _EM))
def test_preserved_quirks_reject_a_duplicated_heading(
    repo_root, tmp_path, monkeypatch, heading
):
    """Two sections under one heading make the evidence ambiguous."""
    def duplicate(case):
        target = case / "docs/UEFN_QUIRKS.md"
        text = target.read_text(encoding="utf-8")
        lines = text.split(_NL)
        matches = [line for line in lines if line.startswith(heading)]
        assert len(matches) == 1, "probe anchor drifted: " + heading
        target.write_text(
            text + _NL + matches[0] + _NL + _NL + "nothing here" + _NL,
            encoding="utf-8",
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch,
        "dup-" + heading.split("#")[2].strip(), duplicate
    )
    assert "preserved quirk" in found, (
        "a duplicated " + heading + " section was accepted: " + repr(sorted(found))
    )


def test_dashboard_fallbacks_are_clean_when_current(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Non-vacuous: the corrected except branch raises nothing."""
    drift_check = _load_drift_check(repo_root, "dash_control")
    case = _make_surface_case(repo_root, tmp_path, "dash-control")
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    assert drift_check.check_dashboard_fallbacks() == []


@pytest.mark.parametrize(("name", "old", "new"), (
    ("stale-tool-count", '_tool_count = "362"', '_tool_count = "355"'),
    ("stale-category-count", '_cat_count  = "55"', '_cat_count  = "54"'),
))
def test_dashboard_fallbacks_reject_stale_literals(
    repo_root, tmp_path, monkeypatch, name, old, new
):
    """The two bare literals the count regexes cannot see are pinned by position.

    Both went stale unnoticed for exactly this reason: they are assignments, not
    prose, so no count pattern could ever match them.
    """
    found = _surface_types(
        repo_root, tmp_path, monkeypatch, name,
        lambda case: _edit(case, _DASHBOARD_REL, old, new),
    )
    assert "dashboard fallback counts" in found, (
        name + " was accepted: " + repr(sorted(found))
    )


def test_dashboard_fallback_decoy_elsewhere_does_not_satisfy_the_check(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A byte-correct copy elsewhere cannot stand in for the rendered branch."""
    def mutate(case):
        target = case / _DASHBOARD_REL
        text = target.read_text(encoding="utf-8")
        assert text.count(_DASHBOARD_FALLBACK) == 1, "probe anchor drifted"
        text = text.replace(
            _DASHBOARD_FALLBACK,
            "    except Exception:" + _NL
            + '        _tool_count = "355"' + _NL
            + '        _cat_count  = "54"',
            1,
        )
        target.write_text(
            text + _NL + "# " + _DASHBOARD_FALLBACK.replace(_NL, _NL + "# ") + _NL,
            encoding="utf-8",
        )

    found = _surface_types(repo_root, tmp_path, monkeypatch, "dash-decoy", mutate)
    assert "dashboard fallback counts" in found, (
        "a fallback decoy elsewhere in the module was accepted: "
        + repr(sorted(found))
    )


def test_dashboard_fallback_requires_a_single_anchor(
    repo_root, tmp_path, monkeypatch
) -> None:
    """A duplicated live registry read makes the anchored position ambiguous."""
    def duplicate(case):
        target = case / _DASHBOARD_REL
        text = target.read_text(encoding="utf-8")
        assert text.count(_DASHBOARD_LIVE_READ) == 1, "probe anchor drifted"
        target.write_text(
            text + _NL + _DASHBOARD_LIVE_READ + _NL, encoding="utf-8"
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "dash-two-anchors", duplicate
    )
    assert "dashboard fallback counts" in found, (
        "two live registry reads were accepted: " + repr(sorted(found))
    )


def test_dashboard_fallback_branch_cannot_be_dropped(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Deleting the fallback entirely fails loudly rather than passing."""
    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "dash-dropped",
        lambda case: _edit(
            case, _DASHBOARD_REL, _DASHBOARD_FALLBACK,
            "    except Exception:" + _NL + '        _tool_count = "362"'
            + _NL + '        _unrelated = "55"',
        ),
    )
    assert "dashboard fallback counts" in found, (
        "a dropped category fallback was accepted: " + repr(sorted(found))
    )


@pytest.mark.parametrize("rel", (
    "Content/Python/UEFN_Toolbelt/__init__.py", "launcher.py",
))
def test_runtime_count_paths_are_declared_scan_targets(repo_root, rel) -> None:
    """The two paths whose stale counts nothing could see are now declared.

    They were corrected under the runtime-text lock; declaring them is what
    stops the same drift returning silently.
    """
    drift_check = _load_drift_check(repo_root, "scan_decl_" + rel.split("/")[-1])
    assert rel in drift_check.SCAN_FILES, rel + " is not a declared scan target"


@pytest.mark.parametrize(("rel", "stale"), (
    ("Content/Python/UEFN_Toolbelt/__init__.py",
     "# Reload message: 355 tools registered"),
    ("launcher.py", "  3. Registers all 355 tools"),
))
def test_declared_runtime_paths_catch_stale_counts(
    repo_root, tmp_path, monkeypatch, rel, stale
):
    """Declaring them is only worth something if the scan actually fires."""
    drift_check = _load_drift_check(repo_root, "scan_fire_" + rel.split("/")[-1])
    case = tmp_path / ("scan-fire-" + rel.split("/")[-1])
    target = case / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        (repo_root / rel).read_text(encoding="utf-8") + _NL + stale + _NL,
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    findings = drift_check.scan_file(
        rel, drift_check.VERSION, drift_check.TOOL_COUNT,
        drift_check.CATEGORY_COUNT,
    )
    assert any(finding["type"] == "tool count" for finding in findings), (
        rel + " did not report the stale count: " + repr(findings)
    )


# ── WO-003 Amendment 1 ────────────────────────────────────────────────────────
#
# Two contradictions Session A disclosed rather than fixing on its own, admitted
# by owner ruling: the runtime docstring that still softened WO-002's accepted
# external result to "unproven", and README's absolute project-only file-write
# guarantee. The probes below reproduce both regressions, and the last one
# proves the runtime correction was text and nothing else.

_EPIC_MCP_TOOLS_REL = "Content/Python/UEFN_Toolbelt/tools/epic_mcp_tools.py"
_FILE_WRITE_ABSOLUTES = (
    "No file writes outside project",
    "All output goes to `Saved/UEFN_Toolbelt/` inside your project",
)


@pytest.mark.parametrize(("name", "rel", "restored"), (
    ("runtime-docstring", _EPIC_MCP_TOOLS_REL,
     "# separately unproven external official-MCP states"),
    ("tool-table", ".claude/tool_tables.md",
     "External exposure remains unproven."),
    ("agent-context", "CLAUDE.md",
     "External exposure through Epic's official MCP is unproven."),
))
def test_unproven_cannot_replace_the_accepted_failed_result(
    repo_root, tmp_path, monkeypatch, name, rel, restored
):
    """`unproven` is the softening WO-002's accepted `failed` result replaced.

    The runtime docstring carried it for a whole Work Order after the external
    probe returned `failed`, which is why it is pinned in the runtime too and
    not only in the documents.
    """
    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "unproven-" + name,
        lambda case: _append(case, rel, restored),
    )
    assert "retired claim" in found, (
        name + " reintroduced `unproven` unchallenged: " + repr(sorted(found))
    )


@pytest.mark.parametrize(("kind", "old", "new"), (
    ("softened", "`failed`", "`unproven`"),
    ("inverted", "`failed`", "`passed`"),
    ("unbounded", "`UE::ValkyrieToolset::ToolsetPolicy`", "Epic's own policy"),
))
def test_runtime_docstring_states_the_accepted_external_result(
    repo_root, tmp_path, monkeypatch, kind, old, new
):
    """The runtime's own description of the external result stays accepted.

    One sentence has to carry both halves: `failed` alone could be about
    anything, and naming ToolsetPolicy without the result does not say what
    happened.
    """
    def mutate(case):
        target = case / _EPIC_MCP_TOOLS_REL
        text = target.read_text(encoding="utf-8")
        assert old in text, "probe anchor drifted: " + old
        target.write_text(text.replace(old, new), encoding="utf-8")

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "runtime-external-" + kind, mutate
    )
    assert "accepted external result" in found, (
        "the runtime accepted a " + kind + " external result: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize("absolute", _FILE_WRITE_ABSOLUTES)
def test_readme_cannot_restore_the_project_only_file_write_guarantee(
    repo_root, tmp_path, monkeypatch, absolute
):
    """Four export tools write wherever the operator points them.

    `snapshot_export`, `datatable_export`, `curve_export`, and `stamp_export`
    each take an explicit path, so the absolute guarantee was false as written.
    """
    found = _surface_types(
        repo_root, tmp_path, monkeypatch,
        "file-write-" + str(_FILE_WRITE_ABSOLUTES.index(absolute)),
        lambda case: _append(case, "README.md", "| **Safety** | " + absolute + " |"),
    )
    assert "retired claim" in found, (
        "README restored the absolute file-write guarantee: " + repr(sorted(found))
    )


@pytest.mark.parametrize("tool", (
    "snapshot_export", "datatable_export", "curve_export", "stamp_export",
))
def test_named_export_tools_still_take_an_explicit_path(repo_root, tool) -> None:
    """Non-vacuous: the evidence behind the corrected row is still true.

    If these tools ever stop accepting an operator-chosen path, the bounded
    wording becomes the wrong answer and this fails rather than going stale.
    """
    sources = list((repo_root / "Content" / "Python" / "UEFN_Toolbelt"
                    / "tools").glob("*.py"))
    definitions = []
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            # Registered name, not function name: several tools are defined
            # as run_<name> and only the decorator carries the tool name.
            registered = {
                keyword.value.value
                for decorator in node.decorator_list
                if isinstance(decorator, ast.Call)
                for keyword in decorator.keywords
                if keyword.arg == "name"
                and isinstance(keyword.value, ast.Constant)
            }
            if tool in registered:
                definitions.append(node)
    assert len(definitions) == 1, (
        tool + " is defined " + str(len(definitions)) + "x"
    )
    names = {arg.arg for arg in definitions[0].args.args}
    assert names & {"export_path", "output_path", "destination"}, (
        tool + " no longer takes an explicit export path: " + repr(sorted(names))
    )


def test_epic_mcp_tools_correction_is_text_only(repo_root) -> None:
    """Amendment 1's runtime edit changed a docstring and nothing else.

    Every tool in this module is a thin delegation to `epic_toolset`, which is
    what makes the correction provably text-only: with docstrings stripped, each
    body is a single return of that delegated call. Adding logic here would
    break this, which is the behaviour change the runtime-text lock forbids.
    """
    module = ast.parse(
        (repo_root / _EPIC_MCP_TOOLS_REL).read_text(encoding="utf-8")
    )
    functions = [node for node in module.body
                 if isinstance(node, ast.FunctionDef)]
    assert functions, "no tool functions found in " + _EPIC_MCP_TOOLS_REL
    for function in functions:
        body = [node for node in function.body
                if not (isinstance(node, ast.Expr)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str))]
        assert len(body) == 1, (
            function.name + " is no longer a thin wrapper: "
            + str(len(body)) + " statements besides its docstring"
        )
        statement = body[0]
        assert isinstance(statement, ast.Return), (
            function.name + " does not return directly"
        )
        assert isinstance(statement.value, ast.Call), (
            function.name + " no longer returns a delegated call"
        )
        target = statement.value.func
        assert isinstance(target, ast.Attribute), (
            function.name + " does not delegate to an attribute"
        )
        assert isinstance(target.value, ast.Name), (
            function.name + " does not delegate to a module"
        )
        assert target.value.id == "epic_toolset", (
            function.name + " delegates to " + target.value.id
            + ", not epic_toolset"
        )


def test_epic_mcp_tools_is_a_declared_runtime_occurrence(repo_root) -> None:
    """The ninth occurrence is enforced, not merely corrected."""
    drift_check = _load_drift_check(repo_root, "amendment_decl")
    assert _EPIC_MCP_TOOLS_REL in drift_check._SURFACE_PATHS
    assert _EPIC_MCP_TOOLS_REL in {
        rel for rel, _anchor, _clause in drift_check._EXTERNAL_RESULT_SITES
    }


@pytest.mark.parametrize(("marker", "count"), (
    ("nine runtime occurrences", 2),
    ("#### Amendment 1 " + _EM + " two disclosed contradictions", 1),
    # Named in full twice: the admitted inventory row, and the ninth
    # bullet of the runtime-text lock.
    (_EPIC_MCP_TOOLS_REL, 2),
))
def test_mandate_records_the_amendment(repo_root, marker, count) -> None:
    """The mandate itself carries the amendment that authorized these two rows.

    Without this the corrections would look like unilateral scope growth, which
    is exactly what Session A stopped to avoid.
    """
    text = (repo_root / _WO003_REL).read_text(encoding="utf-8")
    assert text.count(marker) == count, (
        repr(marker) + " occurs " + str(text.count(marker)) + "x, expected "
        + str(count)
    )
    assert "eight runtime occurrences" not in text


# ── Independent-review P1 regressions ─────────────────────────────────────────
#
# Two evidence checks were position-blind, and independent review proved it with
# temporary-copy probes that returned zero findings. Both bypasses are
# reproduced permanently below. The distinction they turn on: a *required*
# statement must be made by the document at the place it makes the claim, while
# a *retired* claim counts wherever it appears, comments included.

# (name, path, stable semantic key, block anchor used only to plant a probe,
#  the real claim, its corrupted form, the complete keyed material clause)
_EXTERNAL_RESULT_SITES = (
    ("claude-md", "CLAUDE.md",
     "WO-002 recorded that external result as", "official MCP server:",
     "external result as `failed`, bounded by",
     "external result as `passed`, bounded by",
     "WO-002 recorded that external result as `failed`, bounded by "
     "`UE::ValkyrieToolset::ToolsetPolicy`"),
    ("tool-tables", ".claude/tool_tables.md",
     "External exposure through Epic's official MCP server",
     "| `epic_mcp_register` |",
     "official MCP server `failed` on UEFN 42.00",
     "official MCP server `passed` on UEFN 42.00",
     "External exposure through Epic's official MCP server `failed` on "
     "UEFN 42.00, bounded by `UE::ValkyrieToolset::ToolsetPolicy`"),
    ("mcp-reference", ".claude/mcp_reference.md",
     "WO-002 recorded the external result as", "## Toolbelt custom bridge",
     "result as `failed`, bounded by",
     "result as `passed`, bounded by",
     "WO-002 recorded the external result as `failed`, bounded by "
     "`UE::ValkyrieToolset::ToolsetPolicy`"),
    ("runtime", _EPIC_MCP_TOOLS_REL,
     "WO-002 recorded that external result as", "def run_epic_mcp_status",
     "external result as `failed`, bounded by",
     "external result as `passed`, bounded by",
     "WO-002 recorded that external result as `failed`, bounded by "
     "`UE::ValkyrieToolset::ToolsetPolicy`"),
)
_EXTERNAL_SITE_ANCHORS = (
    ("claude-md", "CLAUDE.md",
     "Toolbelt is **not** reachable through Epic's official MCP server:"),
    ("tool-tables", ".claude/tool_tables.md",
     "| `epic_mcp_register` | — | Attempt in-process Toolset Registry "
     "submission."),
    ("mcp-reference", ".claude/mcp_reference.md",
     "Toolbelt is not reachable through that server —"),
    ("runtime", _EPIC_MCP_TOOLS_REL, "def run_epic_mcp_status"),
)
_ACCEPTED_SENTENCE = (
    "External exposure was `failed`, bounded by"
    " `UE::ValkyrieToolset::ToolsetPolicy`."
)


def _corrupt(case, rel, marker, corrupt):
    target = case / rel
    text = target.read_text(encoding="utf-8")
    assert text.count(marker) == 1, "probe anchor drifted in " + rel + ": " + marker
    target.write_text(text.replace(marker, corrupt, 1), encoding="utf-8")


def _plant_after(case, rel, anchor, planted):
    """Insert a line immediately after the anchor line, inside its block."""
    target = case / rel
    lines = target.read_text(encoding="utf-8").split(_NL)
    hits = [i for i, line in enumerate(lines) if line.strip().startswith(anchor)]
    assert len(hits) == 1, "probe anchor drifted in " + rel + ": " + anchor
    lines.insert(hits[0] + 1, planted)
    target.write_text(_NL.join(lines), encoding="utf-8")


def _replace_folded_once(text, phrase, replacement):
    """Replace one phrase independent of its current whitespace wrapping."""
    pattern = re.compile(r"\s+".join(re.escape(part) for part in phrase.split()))
    hits = list(pattern.finditer(text))
    assert len(hits) == 1, "folded probe phrase occurs " + str(len(hits)) + "x"
    hit = hits[0]
    return text[:hit.start()] + replacement + text[hit.end():]


@pytest.mark.parametrize(
    ("name", "rel", "claim_key", "anchor", "marker", "corrupt", "clause"),
    _EXTERNAL_RESULT_SITES,
)
def test_accepted_external_result_rejects_a_transplant(
    repo_root, tmp_path, monkeypatch, name, rel, claim_key, anchor, marker,
    corrupt, clause
):
    """A correct sentence elsewhere cannot repair a corrupted claim site.

    Independent review reproduced exactly this and got zero findings: the real
    row was flipped to `passed` and a valid sentence appended at the end of the
    file, which a whole-file search accepted.
    """
    def mutate(case):
        _corrupt(case, rel, marker, corrupt)
        target = case / rel
        suffix = ("# " if rel.endswith(".py") else "") + _ACCEPTED_SENTENCE
        target.write_text(
            target.read_text(encoding="utf-8") + _NL + suffix + _NL,
            encoding="utf-8",
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "transplant-" + name, mutate
    )
    assert "accepted external result" in found, (
        name + " accepted a transplanted result: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("name", "rel", "claim_key", "anchor", "marker", "corrupt", "clause"),
    _EXTERNAL_RESULT_SITES,
)
def test_accepted_external_result_rejects_a_full_keyed_clause_transplant(
    repo_root, tmp_path, monkeypatch, name, rel, claim_key, anchor, marker,
    corrupt, clause
):
    """The whole correct clause elsewhere cannot replace the claim-site clause.

    This removes the semantic key together with the result and bound, then
    plants the byte-correct keyed clause elsewhere. The former whole-file
    semantic-key check saw one key and one correct clause and therefore passed.
    """
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        text = _replace_folded_once(
            text, clause, "External official-MCP evidence is unavailable."
        )
        planted = (
            '_EXTERNAL_RESULT_TRANSPLANT = """' + clause + '"""'
            if rel.endswith(".py") else clause
        )
        text += _NL + planted + _NL
        target.write_text(text, encoding="utf-8")

        # Discriminate from the replaced position-blind implementation: its
        # exact conditions are both satisfied by this transplanted copy.
        prose = " ".join(text.split())
        assert prose.count(claim_key) == 1
        assert clause in prose

    found = _surface_types(
        repo_root, tmp_path, monkeypatch,
        "full-keyed-transplant-" + name, mutate,
    )
    assert "accepted external result" in found, (
        name + " accepted a full keyed-clause transplant: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("name", "rel", "site_anchor"), _EXTERNAL_SITE_ANCHORS
)
@pytest.mark.parametrize("damage", ("missing", "duplicate"))
def test_accepted_external_result_requires_one_semantic_anchor(
    repo_root, tmp_path, monkeypatch, name, rel, site_anchor, damage
):
    """The path-specific claim identity must be present exactly once."""
    def mutate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        if damage == "missing":
            if name == "runtime":
                assert text.count(site_anchor) == 1
                text = text.replace(
                    site_anchor, "def removed_epic_mcp_status", 1
                )
            else:
                text = _replace_folded_once(
                    text, site_anchor, "REMOVED CLAIM-SITE ANCHOR"
                )
        elif name == "runtime":
            text += (
                _NL + _NL + "def run_epic_mcp_status(**kwargs):"
                + _NL + "    return {}" + _NL
            )
        else:
            text += _NL + site_anchor + _NL
        target.write_text(text, encoding="utf-8")

    found = _surface_types(
        repo_root, tmp_path, monkeypatch,
        "semantic-anchor-" + damage + "-" + name, mutate,
    )
    assert "accepted external result" in found, (
        name + " accepted a " + damage + " semantic anchor: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("name", "rel", "claim_key", "anchor", "marker", "corrupt", "clause"),
    _EXTERNAL_RESULT_SITES,
)
def test_accepted_external_result_rejects_a_commented_decoy(
    repo_root, tmp_path, monkeypatch, name, rel, claim_key, anchor, marker,
    corrupt, clause
):
    """Commentary inside the claim block is not the document making the claim."""
    def mutate(case):
        _corrupt(case, rel, marker, corrupt)
        decoy = ("    # " + _ACCEPTED_SENTENCE if rel.endswith(".py")
                 else "<!-- " + _ACCEPTED_SENTENCE + " -->")
        _plant_after(case, rel, anchor, decoy)

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "commented-" + name, mutate
    )
    assert "accepted external result" in found, (
        name + " accepted a commented decoy: " + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("name", "rel", "claim_key", "anchor", "marker", "corrupt", "clause"),
    _EXTERNAL_RESULT_SITES,
)
def test_accepted_external_result_requires_a_unique_claim_site(
    repo_root, tmp_path, monkeypatch, name, rel, claim_key, anchor, marker,
    corrupt, clause
):
    """Two active copies of the semantic claim make its identity ambiguous."""
    def duplicate(case):
        target = case / rel
        text = target.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        assert normalized.count(claim_key) == 1, "probe key drifted in " + rel
        target.write_text(
            text + _NL + clause + _NL, encoding="utf-8"
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "two-sites-" + name, duplicate
    )
    assert "accepted external result" in found, (
        name + " accepted two claim sites: " + repr(sorted(found))
    )


_FENCED_DECOY_SITES = tuple(
    site for site in _EXTERNAL_RESULT_SITES
    if site[0] in {"claude-md", "mcp-reference"}
)


@pytest.mark.parametrize(
    ("name", "rel", "claim_key", "anchor", "marker", "corrupt", "clause"),
    _EXTERNAL_RESULT_SITES,
)
def test_accepted_external_result_rejects_a_visible_in_block_decoy(
    repo_root, tmp_path, monkeypatch, name, rel, claim_key, anchor, marker,
    corrupt, clause
):
    """A nearby correct sentence cannot repair the keyed material clause.

    Each insertion sits inside the exact block the prior implementation chose,
    carries `failed` plus ToolsetPolicy, and leaves the real keyed claim saying
    `passed`.  That old window-membership rule accepted every one.
    """
    def mutate(case):
        _corrupt(case, rel, marker, corrupt)
        target = case / rel
        lines = target.read_text(encoding="utf-8").split(_NL)
        hits = [i for i, line in enumerate(lines)
                if line.strip().startswith(anchor)]
        assert len(hits) == 1, "probe anchor drifted in " + rel
        index = hits[0]
        if name == "tool-tables":
            assert lines[index].rstrip().endswith("|"), "table row drifted"
            lines[index] = lines[index].rstrip()[:-1] + _ACCEPTED_SENTENCE + " |"
        elif name == "runtime":
            lines.insert(index + 1, '    """' + _ACCEPTED_SENTENCE + '"""')
        else:
            lines.insert(index + 1, _ACCEPTED_SENTENCE)
        target.write_text(_NL.join(lines), encoding="utf-8")
        raw = (case / rel).read_text(encoding="utf-8")
        assert corrupt in raw and _ACCEPTED_SENTENCE in raw, (
            "probe no longer reproduces the in-block decoy"
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch,
        "in-block-visible-" + name, mutate,
    )
    assert "accepted external result" in found, (
        name + " accepted an in-block visible decoy: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(
    ("name", "rel", "claim_key", "anchor", "marker", "corrupt", "clause"),
    _FENCED_DECOY_SITES,
)
def test_accepted_external_result_rejects_a_fenced_in_block_decoy(
    repo_root, tmp_path, monkeypatch, name, rel, claim_key, anchor, marker,
    corrupt, clause
):
    """A fenced example inside the old block is not accepted evidence."""
    def mutate(case):
        _corrupt(case, rel, marker, corrupt)
        planted = "```text" + _NL + _ACCEPTED_SENTENCE + _NL + "```"
        _plant_after(case, rel, anchor, planted)
        raw = (case / rel).read_text(encoding="utf-8")
        assert corrupt in raw and planted in raw, "fenced probe drifted"

    found = _surface_types(
        repo_root, tmp_path, monkeypatch,
        "in-block-fenced-" + name, mutate,
    )
    assert "accepted external result" in found, (
        name + " accepted an in-block fenced decoy: "
        + repr(sorted(found))
    )


def test_external_result_identity_tolerates_claude_line_reflow(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Claim identity is semantic, not the current Markdown line wrapping."""
    old = (
        "Toolbelt is **not** reachable through Epic's" + _NL
        + "  official MCP server:"
    )
    new = "Toolbelt is **not** reachable through Epic's official MCP server:"

    def reflow(case):
        target = case / "CLAUDE.md"
        text = target.read_text(encoding="utf-8")
        assert text.count(old) == 1, "CLAUDE reflow probe anchor drifted"
        target.write_text(text.replace(old, new, 1), encoding="utf-8")

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "claude-reflow", reflow
    )
    assert found == set(), (
        "harmless CLAUDE line reflow changed the truth verdict: "
        + repr(sorted(found))
    )


_QUIRK_RECOVERY = (
    "**Workaround.** Turn the flag off, or run `import UEFN_Toolbelt as tb;"
    + _NL + "tb.register()` once per session."
)
_QUIRK_WORKFLOW_FRAGMENTS = ("prepare_launch.bat", "restore_after_launch.bat")


def test_quirk36_recovery_rejects_a_commented_decoy(
    repo_root, tmp_path, monkeypatch
) -> None:
    """The disclosed bypass: delete the real command, comment out a copy.

    Section-wide membership accepted this, because the fragment was still
    somewhere inside Quirk #36. The recovery command has to be in the Workaround
    itself, and a commented copy is not the document telling anyone what to run.
    """
    def mutate(case):
        target = case / "docs/UEFN_QUIRKS.md"
        text = target.read_text(encoding="utf-8")
        assert text.count(_QUIRK_RECOVERY) == 1, "probe anchor drifted"
        target.write_text(
            text.replace(
                _QUIRK_RECOVERY,
                "**Workaround.** Turn the flag off." + _NL
                + "<!-- import UEFN_Toolbelt as tb; tb.register() -->",
                1,
            ),
            encoding="utf-8",
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "quirk36-commented", mutate
    )
    assert "preserved quirk" in found, (
        "a commented recovery command was accepted: " + repr(sorted(found))
    )


def test_quirk36_recovery_rejects_a_transplant(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Moving the command out of the Workaround is losing it, not keeping it."""
    def mutate(case):
        target = case / "docs/UEFN_QUIRKS.md"
        text = target.read_text(encoding="utf-8")
        assert text.count(_QUIRK_RECOVERY) == 1, "probe anchor drifted"
        anchor = "**Detection.**"
        assert text.count(anchor) == 1, "probe anchor drifted: " + anchor
        text = text.replace(
            _QUIRK_RECOVERY, "**Workaround.** Turn the flag off.", 1
        )
        target.write_text(
            text.replace(
                anchor,
                "Formerly: `import UEFN_Toolbelt as tb; tb.register()`." + _NL
                + _NL + anchor,
                1,
            ),
            encoding="utf-8",
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "quirk36-transplant", mutate
    )
    assert "preserved quirk" in found, (
        "the recovery command was accepted outside its Workaround: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize(("name", "replacement"), (
    (
        "commented-fence",
        "**Workaround.** Turn the flag off." + _NL + _NL
        + "```python" + _NL
        + "# import UEFN_Toolbelt as tb;" + _NL
        + "# tb.register()" + _NL
        + "```",
    ),
    (
        "details-wrapper",
        "**Workaround.** Turn the flag off." + _NL
        + "<details>" + _NL
        + "<summary>Former recovery</summary>" + _NL
        + "`import UEFN_Toolbelt as tb; tb.register()`" + _NL
        + "</details>",
    ),
))
def test_quirk36_recovery_rejects_wrapped_copies(
    repo_root, tmp_path, monkeypatch, name, replacement
) -> None:
    """Commented examples and disclosure wrappers are not the Workaround."""
    def mutate(case):
        target = case / "docs/UEFN_QUIRKS.md"
        text = target.read_text(encoding="utf-8")
        assert text.count(_QUIRK_RECOVERY) == 1, "probe anchor drifted"
        mutated = text.replace(_QUIRK_RECOVERY, replacement, 1)
        assert "import UEFN_Toolbelt as tb;" in mutated
        assert "tb.register()" in mutated
        target.write_text(mutated, encoding="utf-8")

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "quirk36-" + name, mutate
    )
    assert "preserved quirk" in found, (
        name + " copy satisfied the Quirk #36 recovery: "
        + repr(sorted(found))
    )


@pytest.mark.parametrize("fragment", _QUIRK_WORKFLOW_FRAGMENTS)
def test_quirk42_workflow_rejects_a_commented_decoy(
    repo_root, tmp_path, monkeypatch, fragment
):
    """Quirk #42's helpers must stay in the verified workflow, uncommented."""
    def mutate(case):
        target = case / "docs/UEFN_QUIRKS.md"
        text = target.read_text(encoding="utf-8")
        assert text.count(fragment) >= 1, "probe anchor drifted: " + fragment
        target.write_text(
            text.replace(fragment, "REMOVED")
            + _NL + "<!-- " + fragment + " -->" + _NL,
            encoding="utf-8",
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "quirk42-commented-" + fragment, mutate
    )
    assert "preserved quirk" in found, (
        fragment + " survived only as a comment: " + repr(sorted(found))
    )


def test_quirk_evidence_requires_a_unique_sub_anchor(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Two Workaround blocks in one quirk make the recovery step ambiguous."""
    def duplicate(case):
        target = case / "docs/UEFN_QUIRKS.md"
        text = target.read_text(encoding="utf-8")
        anchor = "**Workaround.**"
        assert text.count(anchor) == 1, "probe anchor drifted: " + anchor
        marker = "**Not fixable from Toolbelt.**"
        assert text.count(marker) == 1, "probe anchor drifted: " + marker
        target.write_text(
            text.replace(marker, anchor + " Something else." + _NL + _NL + marker, 1),
            encoding="utf-8",
        )

    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "quirk-two-workarounds", duplicate
    )
    assert "preserved quirk" in found, (
        "two Workaround blocks were accepted: " + repr(sorted(found))
    )


def test_retired_claims_still_count_inside_commentary(
    repo_root, tmp_path, monkeypatch
) -> None:
    """Required evidence ignores comments; forbidden claims do not.

    The asymmetry is deliberate. A commented copy cannot *make* a statement, but
    a retired claim sitting in a comment is still the repository carrying it.
    """
    found = _surface_types(
        repo_root, tmp_path, monkeypatch, "retired-in-comment",
        lambda case: _append(case, "README.md",
                             "<!-- You **never need to restart UEFN**. -->"),
    )
    assert "retired claim" in found, (
        "a retired claim hid inside a comment: " + repr(sorted(found))
    )
