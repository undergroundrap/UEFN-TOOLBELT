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
        "docs/work-orders/issued/WO-002-epic-toolset-integration.md",
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
    completed = [path for path in (work_orders / "completed").glob("*.md")
                 if path.name.lower() != "readme.md"]
    assert len(issued) == 1
    assert issued[0].name == "WO-002-epic-toolset-integration.md"
    assert len(completed) == 1
    assert completed[0].name == "WO-001-custom-mcp-security.md"
    assert current == "WO-002"
    assert session == "B"
    assert base_lines == [
        "- Base commit: `d1a2c810126ba6c9e14891da1b25cb198c1d45c7`"
    ]
    assert gate_lines == [
        "- Current gate: WO-002 SESSION B AUTHORIZED — EXECUTE EXTERNAL PROOF ONLY"
    ]
    assert "- Release train: WO-001 through WO-007" in pointer
    assert (
        "- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED — COMPLETE THE "
        "FROZEN TRAIN AND FINAL INTEGRATION/REPOSITORY-TRUTH AUDIT FIRST"
    ) in pointer
    assert "version 2.4.1" in pointer
    assert "docs/work-orders/completed/WO-001-custom-mcp-security.md" in pointer
    assert "docs/work-orders/issued/WO-001-custom-mcp-security.md" not in pointer
    assert "docs/work-orders/proposed/WO-001-custom-mcp-security.md" not in pointer
    assert "docs/work-orders/issued/WO-002-epic-toolset-integration.md" in pointer
    assert "docs/work-orders/proposed/WO-002-epic-toolset-integration.md" not in pointer

    issued_text = issued[0].read_text(encoding="utf-8")
    issued_lines = issued_text.splitlines()
    assert [line for line in issued_lines if line.startswith("BASELINE:")] == [
        "BASELINE: `098b38c669dd330cd059ea18dea52cc4e7eaefe2`"
    ]
    assert [line for line in issued_lines if line.startswith("STATUS:")] == [
        "STATUS: ISSUED"
    ]
    assert [line for line in issued_lines if line.startswith("AUTHORIZATION:")] == [
        "AUTHORIZATION: ISSUED — SESSION B AUTHORIZED FOR EXTERNAL PROOF"
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
        "NEXT GATE: fresh independent architect review of the complete uncommitted\n"
        "Session B evidence. Session B is proof-only; WO-003 remains unauthorized."
        in issued_text
    )

    completed_text = completed[0].read_text(encoding="utf-8")
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


def _make_wo002_session_b_case(repo_root, tmp_path, name):
    """Copy the current authorized WO-002 Session B state."""
    case = tmp_path / name
    case.mkdir(parents=True)
    shutil.copy2(repo_root / "WORKORDER.md", case / "WORKORDER.md")
    shutil.copytree(
        repo_root / "docs" / "work-orders",
        case / "docs" / "work-orders",
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
    assert finding_types(control) == set()

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
    assert finding_types(control) == set()

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
    assert finding_types(control) == set()

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
    ("issued-acceptance-commit", _ISSUED_REL,
     "accepted and committed as" + _NL + "`" + _ACCEPTED_COMMIT + "`.",
     "accepted and committed as" + _NL + "`" + _WRONG_COMMIT + "`.",
     None, _ISSUED_FINDING),
    ("issued-workflow-label", _ISSUED_REL,
     "[`" + _ACCEPTED_WORKFLOW + "`](", "[`" + _WRONG_WORKFLOW + "`](",
     _ACCEPTED_WORKFLOW, _ISSUED_FINDING),
    ("issued-workflow-url", _ISSUED_REL,
     "runs/" + _ACCEPTED_WORKFLOW + ")", "runs/" + _WRONG_WORKFLOW + ")",
     _ACCEPTED_WORKFLOW, _ISSUED_FINDING),
    ("issued-job-label", _ISSUED_REL,
     "[`" + _ACCEPTED_JOB + _JOB_SUFFIX, "[`" + _WRONG_JOB + _JOB_SUFFIX,
     _ACCEPTED_JOB, _ISSUED_FINDING),
    ("issued-job-url", _ISSUED_REL,
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
    case = _make_wo002_session_b_case(
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
    case = _make_wo002_session_b_case(
        repo_root, tmp_path, "acceptance-occurrence-control"
    )
    monkeypatch.setattr(drift_check, "ROOT", str(case))
    assert drift_check.check_work_order_contract() == []


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
_ISSUED_LINK = "](docs/work-orders/issued/WO-002-epic-toolset-integration.md)"
_ACCEPTANCE_HEADING = "## Session A acceptance record"
_FOLLOWING_HEADING = "## Problem and accepted evidence"
_ACCEPTANCE_SURFACES = {
    "pointer": ("WORKORDER.md", _POINTER_FINDING),
    "issued": (_ISSUED_REL, _ISSUED_FINDING),
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
        assert _ISSUED_LINK in record, "probe located the wrong paragraph"
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
    body = body.replace(_ISSUED_LINK, "](issued-work-order)")
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
            junk = junk.replace(_ISSUED_LINK, "](issued-work-order)")
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
        return text + _NL + _NL + "See also [WO-002](" + _ISSUED_LINK[2:] + _NL
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
    case = _make_wo002_session_b_case(
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
    case = _make_wo002_session_b_case(
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
    case = _make_wo002_session_b_case(
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
    case = _make_wo002_session_b_case(
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
    case = _make_wo002_session_b_case(
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
    case = _make_wo002_session_b_case(
        repo_root, tmp_path, "acceptance-unrelated-heading"
    )
    issued = case / _ISSUED_REL
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
    drifted = _make_wo002_session_a_accepted_case(
        repo_root, tmp_path, "boundary-" + damage + "-" + tag
    )
    issued = drifted / _ISSUED_REL
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

    with pytest.raises(AssertionError, match="no longer anchored"):
        _make_wo002_session_a_case(
            drifted, tmp_path, "boundary-case-" + damage + "-" + tag
        )


def test_wo002_historical_reconstruction_requires_pointer_anchor(
    repo_root, tmp_path
):
    """A drifted pointer anchor must fail loudly, not rebuild today's state."""
    drifted = _make_wo002_session_a_accepted_case(
        repo_root, tmp_path, "drifted-pointer-anchor"
    )
    pointer = drifted / "WORKORDER.md"
    text = pointer.read_text(encoding="utf-8")
    anchor = "- Authorized session: NONE"
    assert anchor in text, "this probe's own anchor has drifted"
    pointer.write_text(
        text.replace(anchor, "- Authorized session: none", 1), encoding="utf-8"
    )

    with pytest.raises(AssertionError, match="no longer anchored"):
        _make_wo002_session_a_case(drifted, tmp_path, "drifted-pointer-case")


def test_wo002_historical_reconstruction_requires_issued_anchor(
    repo_root, tmp_path
):
    """Likewise for the acceptance-record excision the issued probe depends on."""
    drifted = _make_wo002_session_a_accepted_case(
        repo_root, tmp_path, "drifted-issued-anchor"
    )
    issued = drifted / _ISSUED_REL
    text = issued.read_text(encoding="utf-8")
    anchor = "## Session A acceptance record"
    assert anchor in text, "this probe's own anchor has drifted"
    issued.write_text(
        text.replace(anchor, "## Session A acceptance note", 1), encoding="utf-8"
    )

    with pytest.raises(AssertionError, match="no longer anchored"):
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
    assert finding_types(control) == set()

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
    assert found == set(), "the authorized Session B state is not clean: " + repr(
        sorted(found)
    )


def test_wo002_session_b_preserves_session_a_acceptance(
    repo_root, tmp_path, monkeypatch
):
    """Authorizing Session B must not silence Session A's accepted evidence."""
    found = _session_b_finding_types(
        repo_root, tmp_path, monkeypatch, "acceptance-still-enforced",
        lambda case: _edit(
            case, "WORKORDER.md",
            "[CI workflow" + _NL + "`" + _ACCEPTED_WORKFLOW + "`]",
            "[CI workflow" + _NL + "`" + _WRONG_WORKFLOW + "`]",
        ),
    )
    assert _POINTER_FINDING in found, (
        "Session A's acceptance record stopped being enforced under Session B: "
        + repr(sorted(found))
    )
