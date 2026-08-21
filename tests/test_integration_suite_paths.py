"""
The integration suite must not write to Epic's Fortnite install.

In UEFN `/Game/` is Epic's install, not the creator's project (Quirk #23). The
suite had nine hardcoded `/Game/TOOLBELT_TEST...` paths — it created test assets
there and called delete_directory() on them. The rest of the codebase was swept
for this earlier; the suite that verifies the codebase never was.

It also checked its material result against "/UEFN_Toolbelt/Materials/
M_ToolbeltBase" — a mount that does not exist at all. does_asset_exist() was
therefore always False, the check always fell back to an engine stub, and the
assertion never tested the preset material it claimed to be testing. A test
asserting against a path that cannot exist passes or fails for reasons unrelated
to the thing under test.

These pin both, because a suite that writes to the wrong place is worse than no
suite: it reports on a project it never touched.
"""

from __future__ import annotations

import re
from pathlib import Path

SUITE = (Path(__file__).resolve().parents[1] / "Content" / "Python" /
         "UEFN_Toolbelt" / "tools" / "integration_test.py")

_WRAPPER = "resolve_content_path("


def _bare_game_literals(text: str) -> list[str]:
    """`/Game/...` string literals NOT wrapped in resolve_content_path().

    Wrapped ones are correct: resolve_content_path() rewrites a /Game/ prefix
    onto the detected project mount, which is exactly the intended form.
    """
    out = []
    for m in re.finditer(r'"/Game/[^"]*"', text):
        before = text[max(0, m.start() - len(_WRAPPER)):m.start()]
        if not before.endswith(_WRAPPER):
            out.append(m.group(0))
    return out


def test_suite_writes_no_paths_into_epics_install():
    bare = _bare_game_literals(SUITE.read_text(encoding="utf-8"))
    assert not bare, (
        "integration_test.py has unwrapped /Game/ paths — in UEFN these point at "
        f"Epic's Fortnite install, not the project: {bare}"
    )


def test_suite_does_not_reference_a_nonexistent_mount():
    """/UEFN_Toolbelt/ is not a mount. It is a folder inside the project mount.

    Comment lines are skipped: the fix's own comment quotes the bad path to
    explain it, and flagging that would be flagging the documentation rather
    than the code. Check what the code DOES.
    """
    bad = [
        m
        for n, line in enumerate(SUITE.read_text(encoding="utf-8").splitlines(), 1)
        if not line.lstrip().startswith("#")
        for m in re.findall(r'"/UEFN_Toolbelt[^"]*"', line)
    ]
    assert not bad, f"references a mount that does not exist: {bad}"


def test_suite_resolves_the_master_material_the_same_way_the_tools_do():
    """Sharing parent_material_path() keeps the suite from drifting from its
    subject — the previous hardcoded path had already drifted."""
    text = SUITE.read_text(encoding="utf-8")
    assert "from UEFN_Toolbelt.tools.material_master import parent_material_path" in text
    assert "PARENT_MATERIAL_PATH = parent_material_path()" in text


def test_the_detector_would_actually_catch_a_regression():
    """Non-vacuous: a bare literal must be reported, a wrapped one must not."""
    assert _bare_game_literals('x = "/Game/TOOLBELT_TEST"') == ['"/Game/TOOLBELT_TEST"']
    assert _bare_game_literals('x = resolve_content_path("/Game/TOOLBELT_TEST")') == []
