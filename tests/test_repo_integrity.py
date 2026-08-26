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
        "docs/work-orders/issued/WO-001-custom-mcp-security.md",
        "docs/work-orders/proposed/WO-002-epic-toolset-integration.md",
        "docs/work-orders/proposed/WO-003-official-mcp-doc-convergence.md",
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
        "WO-002-epic-toolset-integration.md",
        "WO-003-official-mcp-doc-convergence.md",
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
    assert len(issued) == 1
    assert issued[0].name == "WO-001-custom-mcp-security.md"
    assert current == "WO-001"
    assert session == "A"
    assert base_lines == [
        "- Base commit: `34c3762b32c36805e3ec2f7f93df68c2c17fd26c`"
    ]
    assert gate_lines == [
        "- Current gate: WO-001 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY"
    ]
    assert "docs/work-orders/issued/WO-001-custom-mcp-security.md" in pointer
    assert "docs/work-orders/proposed/WO-001-custom-mcp-security.md" not in pointer

    issued_text = issued[0].read_text(encoding="utf-8")
    issued_lines = issued_text.splitlines()
    issued_status = [line for line in issued_lines if line.startswith("STATUS:")]
    issued_auth = [line for line in issued_lines if line.startswith("AUTHORIZATION:")]
    assert issued_status == ["STATUS: ISSUED"]
    assert issued_auth == [
        "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION"
    ]
    assert "## Session A — authenticated, fail-closed control plane" in issued_text
    assert "## Proposed Session A" not in issued_text
    assert "34c3762b32c36805e3ec2f7f93df68c2c17fd26c" in issued_text
    assert "32701409756" in issued_text
    assert "32890583500" in issued_text
    assert "Issuance alone grants no implementation authority" in issued_text
    assert (
        "NEXT GATE: independent review of the complete uncommitted Session A worktree."
        in issued_text
    )

    issued_readme = (work_orders / "issued" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "No Work Order is currently issued" not in issued_readme
    assert "repository-root\n`WORKORDER.md` for the sole current gate" in issued_readme
    security = (repo_root / "SECURITY.md").read_text(encoding="utf-8")
    security_normalized = " ".join(security.split())
    assert "Work Order WO-001" in security_normalized


def _make_closed_work_order_case(repo_root, tmp_path, name):
    """Build the former closed state so its fail-closed contract stays permanent."""
    case = tmp_path / name
    case.mkdir(parents=True)
    shutil.copy2(repo_root / "WORKORDER.md", case / "WORKORDER.md")
    shutil.copytree(
        repo_root / "docs" / "work-orders",
        case / "docs" / "work-orders",
    )

    pointer = case / "WORKORDER.md"
    pointer_text = pointer.read_text(encoding="utf-8")
    pointer_text = pointer_text.replace(
        "- Authorized session: A",
        "- Authorized session: NONE",
    ).replace(
        "- Current gate: WO-001 SESSION A AUTHORIZED — IMPLEMENT SESSION A ONLY",
        "- Current gate: WO-001 ISSUED — SESSION A IMPLEMENTATION NOT AUTHORIZED",
    ).replace(
        "is issued. The root gate authorizes only its bounded Session A implementation.\n"
        "Independent review, commit, push, tag, GitHub Release, repository-description\n"
        "change, and social publication remain separate owner-authorized gates.",
        "is issued, but issuance alone grants no implementation authority. Session A is\n"
        "not authorized. Implementation, independent review, commit, push, tag, GitHub\n"
        "Release, repository-description change, and social publication remain separate\n"
        "owner-authorized gates.",
    )
    pointer.write_text(pointer_text, encoding="utf-8")

    issued = (
        case
        / "docs"
        / "work-orders"
        / "issued"
        / "WO-001-custom-mcp-security.md"
    )
    issued_text = issued.read_text(encoding="utf-8")
    issued_text = issued_text.replace(
        "AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION",
        "AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED",
    ).replace(
        "\nSESSION A AUTHORIZATION BASIS: The issued Work Order was committed as\n"
        "`34c3762b32c36805e3ec2f7f93df68c2c17fd26c`; CI workflow\n"
        "[`32890583500`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32890583500)\n"
        "passed before the owner authorized Session A.\n",
        "",
    ).replace(
        "NEXT GATE: independent review of the complete uncommitted Session A worktree.",
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
            "Session A is\nnot authorized.",
            "Session A is\nnot authorized. Nevertheless, work may commence.",
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
        case = tmp_path / name
        case.mkdir(parents=True)
        shutil.copy2(repo_root / "WORKORDER.md", case / "WORKORDER.md")
        shutil.copytree(
            repo_root / "docs" / "work-orders",
            case / "docs" / "work-orders",
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

    case = tmp_path / "later-session"
    case.mkdir(parents=True)
    shutil.copy2(repo_root / "WORKORDER.md", case / "WORKORDER.md")
    shutil.copytree(
        repo_root / "docs" / "work-orders",
        case / "docs" / "work-orders",
    )
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
