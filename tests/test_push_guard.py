"""
The pre-push hook is the only mechanism standing between an unverified runtime
change and the users' editors, and it is a shell script that nothing else tests.

It has already failed twice in ways that looked like success:
  1. A test of it was invalidated by `git stash -u` sweeping the untracked hook
     file away, so the push sailed through and read as proof the hook was broken.
  2. It accepted ANY trailer, so "Live-Verification: not-required" waved through
     a hard_reload() that was broken in a way only a live run could catch.

These build a throwaway repo so the assertions do not depend on this project's
history staying reachable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "pre-push"

pytestmark = pytest.mark.skipif(
    shutil.which("sh") is None or not HOOK.exists(),
    reason="POSIX sh or the hook is unavailable",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo_with_commit(tmp_path: Path, message: str, runtime: bool) -> tuple[Path, str, str]:
    """A repo with a base commit plus one commit carrying `message`."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    # Detach from the machine-wide core.hooksPath: its commit-msg hook enforces
    # scoped Conventional Commits, which would fail this fixture for reasons that
    # have nothing to do with the hook under test.
    hooks = tmp_path / "nohooks"
    hooks.mkdir()
    _git(repo, "config", "core.hooksPath", str(hooks))

    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: base")
    base = _git(repo, "rev-parse", "HEAD")

    if runtime:
        target = repo / "Content" / "Python" / "UEFN_Toolbelt"
        target.mkdir(parents=True)
        (target / "thing.py").write_text("x = 1\n", encoding="utf-8")
    else:
        (repo / "docs.md").write_text("d\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return repo, base, _git(repo, "rev-parse", "HEAD")


def _run_hook(repo: Path, base: str, head: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(HOOK), "origin", "https://example.invalid"],
        cwd=repo,
        input=f"refs/heads/main {head} refs/heads/main {base}\n",
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "trailer",
    ["", "Live-Verification: pending", "Verified-Live: TODO",
     "Live-Verification: tbd", "Verified-Live: untested",
     # "not yet" said the same thing as "pending" and sailed through, which is
     # how nine verified-but-unlabelled commits nearly left the machine.
     "Live-Verification: not yet - needs one run in the editor",
     "Verified-Live: not-yet"],
)
def test_blocks_runtime_change_without_real_verification(tmp_path, trailer):
    msg = "fix(x): touch runtime code" + (f"\n\n{trailer}" if trailer else "")
    repo, base, head = _repo_with_commit(tmp_path, msg, runtime=True)
    res = _run_hook(repo, base, head)
    assert res.returncode == 1, f"hook allowed {trailer!r}\n{res.stdout}{res.stderr}"
    assert "BLOCKED" in res.stdout


@pytest.mark.parametrize(
    "trailer",
    ["Verified-Live: ran tag_list_all in TOOL_TEST, no $Digest errors",
     "Live-Verification: not-required — docs only"],
)
def test_allows_runtime_change_with_a_real_claim(tmp_path, trailer):
    """A hook that blocks everything is as useless as one that blocks nothing."""
    repo, base, head = _repo_with_commit(
        tmp_path, f"fix(x): touch runtime code\n\n{trailer}", runtime=True)
    res = _run_hook(repo, base, head)
    assert res.returncode == 0, f"hook blocked {trailer!r}\n{res.stdout}{res.stderr}"


def test_ignores_commits_that_touch_no_runtime_code(tmp_path):
    repo, base, head = _repo_with_commit(tmp_path, "docs: edit", runtime=False)
    res = _run_hook(repo, base, head)
    assert res.returncode == 0, res.stdout
