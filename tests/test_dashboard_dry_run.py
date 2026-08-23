"""A dashboard button that says "apply" must actually apply.

v2.4.0 flipped `dry_run` to default True on three tools that rewrite asset
names and paths in bulk. That is the right default for a scripting API - the
safe mode should be the one you get for free. But the dashboard was written
against the old default and called all three with no `dry_run` argument, so
the flip turned four buttons into no-ops that reported success.

The sharpest case was a pair: "Audit - Dry Run (no changes)" sitting directly
above "Enforce - Apply All Renames". After the flip both buttons did the same
thing, and the second one still said Apply.

This is the same failure this release is about - something reporting that work
happened when it did not - except surfaced through the UI rather than a return
value. So it gets the same treatment: pin it.
"""

from __future__ import annotations

import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DASHBOARD = _ROOT / "Content" / "Python" / "UEFN_Toolbelt" / "dashboard_pyside6.py"

# Tools whose dry_run default is True *and* whose whole purpose is to mutate.
# A dashboard call to one of these without an explicit dry_run is a no-op
# button. Add to this set whenever another tool's dry_run default flips on.
_MUST_BE_EXPLICIT = {
    "rename_enforce_conventions",
    "organize_assets",
    "actor_rename_folder",
}


def _dashboard_tool_calls(source: str) -> list[tuple[str, int, bool]]:
    """Every R("tool_name", ...) in the dashboard: (name, lineno, passes_dry_run)."""
    tree = ast.parse(source)
    found: list[tuple[str, int, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        # The dashboard's tool-runner helper is a bare name: R("tool", ...)
        if not (isinstance(fn, ast.Name) and fn.id == "R"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        passes = any(kw.arg == "dry_run" for kw in node.keywords)
        found.append((first.value, node.lineno, passes))
    return found


def test_mutating_buttons_pass_dry_run_explicitly() -> None:
    source = _DASHBOARD.read_text(encoding="utf-8")
    offenders = [
        f"{_DASHBOARD.name}:{lineno} R({name!r}) has no dry_run - "
        f"this button previews and reports success without doing anything"
        for name, lineno, passes in _dashboard_tool_calls(source)
        if name in _MUST_BE_EXPLICIT and not passes
    ]
    assert not offenders, "\n".join(offenders)


def test_every_guarded_tool_is_actually_reached_from_the_dashboard() -> None:
    """Keep the set honest.

    If a tool in _MUST_BE_EXPLICIT stops appearing in the dashboard entirely,
    the check above passes vacuously for it. That is a suppression, not a
    guarantee - either the button was removed (drop it from the set) or it was
    renamed (update the set).
    """
    source = _DASHBOARD.read_text(encoding="utf-8")
    reached = {name for name, _, _ in _dashboard_tool_calls(source)}
    missing = sorted(_MUST_BE_EXPLICIT - reached)
    assert not missing, (
        f"{missing} are guarded but no longer called from the dashboard - "
        f"the guard is passing vacuously for them"
    )


def test_the_detector_would_catch_a_regression() -> None:
    """Non-vacuous: prove it rejects the shape that was actually wrong."""
    bad = 'R("rename_enforce_conventions", scan_path=x.text())'
    good = 'R("rename_enforce_conventions", scan_path=x.text(), dry_run=False)'

    (name, _, passes_bad), = _dashboard_tool_calls(bad)
    assert name == "rename_enforce_conventions" and not passes_bad, (
        "detector failed to flag the bare call that shipped in 2.4.0"
    )

    (_, _, passes_good), = _dashboard_tool_calls(good)
    assert passes_good, "detector rejects the corrected form"

    # dry_run=True is explicit too - a deliberate preview button is fine.
    (_, _, passes_preview), = _dashboard_tool_calls(
        'R("organize_assets", source_path=x, dry_run=True)'
    )
    assert passes_preview, "an intentional preview button must not be flagged"
