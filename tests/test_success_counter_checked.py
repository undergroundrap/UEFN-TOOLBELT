"""A success counter that is never checked must not be returned as "ok".

    total_slots = 0
    for actor in actors:
        if _swap(actor):            # conditional -> can end at 0 on valid input
            total_slots += 1
    return {"status": "ok", "total_slots": total_slots}     # never checked

That was material_bulk_swap. It logged a checkmark and returned "ok" for a swap
that changed nothing, so a caller branching on status believed the material had
been replaced. The usual cause is a near-miss asset path, which looks identical
in the log.

An audit on 2026-08-22 found the same shape in five more tools:

    cooker_mark_batch / cooker_unmark_all / cooker_mark_selection
        _set_editor_only swallows the exception and returns False, so a run
        where every set failed was indistinguishable from a clean one.
    text_apply_translation
        0 of N applied when no actor in the manifest resolves.
    niagara_bulk_set_parameter
        0 components updated - the parameter name did not match anything.

WHY THIS IS A RATCHET, NOT A CLEAN GATE
---------------------------------------
The detector still reports candidates that are fine, and the honest thing is to
say so rather than allowlist them one by one as "reviewed" when they have not
all been read:

  * FAILURE counters. `{"status": "ok", "failed": failed}` with failed == 0 is
    correct and common - actor_lock, device_set_property, verse_build_status.
  * Counters guarded through a sibling. material_bulk_swap now tests
    `total_slots` and returns early, but still reports `actors_touched` in the
    ok branch; the detector cannot see that the early return covers it.
  * Tools where zero is a real no-op - cooker_unmark_all with nothing marked.

So this pins the count. Fixing one of the remaining candidates should LOWER the
baseline; adding a new unchecked counter raises it and fails here. Do not raise
the baseline to make this pass without saying why in the commit.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Content" / "Python" / "UEFN_Toolbelt" / "tools"

SKIP = {"integration_test.py"}

# Candidates remaining after the 2026-08-22 fixes. Lower this when you fix one.
BASELINE = 28


def _tool_name(fn: ast.FunctionDef) -> str:
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
    return ""


def _conditional_counters(fn: ast.FunctionDef) -> set[str]:
    """Names incremented by += inside an `if` that sits inside a loop.

    Unconditional increments are excluded on purpose: those end up equal to the
    input size, so an existing empty-input guard already covers them.
    """
    found: set[str] = set()
    for loop in ast.walk(fn):
        if not isinstance(loop, (ast.For, ast.While)):
            continue
        for branch in ast.walk(loop):
            if not isinstance(branch, ast.If):
                continue
            for node in ast.walk(branch):
                if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                    found.add(node.target.id)
    return found


def _tested_names(fn: ast.FunctionDef) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.IfExp)):
            for sub in ast.walk(node.test):
                if isinstance(sub, ast.Name):
                    out.add(sub.id)
    return out


def _scan_tree(tree: ast.Module, filename: str) -> list[str]:
    out: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        name = _tool_name(fn)
        if not name:
            continue
        counters = _conditional_counters(fn)
        if not counters:
            continue
        tested = _tested_names(fn)
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)):
                continue
            pairs = {
                k.value: v
                # ast.Dict keeps keys and values parallel (a **expansion puts
                # None in keys), so strict is safe and catches a bad parse.
                for k, v in zip(node.value.keys, node.value.values, strict=True)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            status = pairs.get("status")
            if not (isinstance(status, ast.Constant) and status.value == "ok"):
                continue
            risky = sorted(
                key
                for key, val in pairs.items()
                if isinstance(val, ast.Name)
                and val.id in counters
                and val.id not in tested
            )
            if risky:
                out.append(f"{filename}:{node.lineno}  {name}  -> {risky}")
    return out


def _candidates() -> list[str]:
    found: list[str] = []
    for path in sorted(TOOLS.glob("*.py")):
        if path.name in SKIP:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend(_scan_tree(tree, path.name))
    return found


def test_unchecked_success_counters_do_not_grow():
    found = _candidates()
    assert len(found) <= BASELINE, (
        f"{len(found)} tool returns report status=ok with a success counter that "
        f"is never checked, up from the {BASELINE} baseline. A counter that only "
        f"increments on success can end at zero on valid input, and returning "
        f"'ok' then tells the caller the work happened:\n  "
        + "\n  ".join(found)
    )


def test_baseline_is_not_stale():
    """If someone fixes one and forgets to lower BASELINE, say so.

    A ratchet that never tightens is just a suppression list.
    """
    found = _candidates()
    assert len(found) >= BASELINE - 2, (
        f"only {len(found)} candidates remain but BASELINE is still {BASELINE}. "
        f"Lower BASELINE to {len(found)} so the ratchet keeps its grip."
    )


def test_the_detector_would_catch_a_regression():
    """Non-vacuous: prove it flags the bug shape and clears the fixed one."""
    bad = ast.parse(
        "@register_tool(name='x')\n"
        "def run_x():\n"
        "    n = 0\n"
        "    for a in actors:\n"
        "        if work(a):\n"
        "            n += 1\n"
        "    return {'status': 'ok', 'count': n}\n"
    )
    assert _scan_tree(bad, "t.py"), "missed the unchecked-counter shape"

    # Checking the counter before returning ok clears it.
    good = ast.parse(
        "@register_tool(name='x')\n"
        "def run_x():\n"
        "    n = 0\n"
        "    for a in actors:\n"
        "        if work(a):\n"
        "            n += 1\n"
        "    if n == 0:\n"
        "        return {'status': 'error', 'count': 0}\n"
        "    return {'status': 'ok', 'count': n}\n"
    )
    assert not _scan_tree(good, "t.py"), "flagged a counter that IS checked"

    # An unconditional increment equals the input size - not this bug.
    uncond = ast.parse(
        "@register_tool(name='x')\n"
        "def run_x():\n"
        "    n = 0\n"
        "    for a in actors:\n"
        "        n += 1\n"
        "    return {'status': 'ok', 'count': n}\n"
    )
    assert not _scan_tree(uncond, "t.py"), "flagged an unconditional counter"


def test_the_five_fixed_tools_stay_fixed():
    """Named pins, so a revert is loud rather than a baseline drift of one."""
    found = "\n".join(_candidates())
    for tool in (
        "cooker_mark_batch",
        "cooker_unmark_all",
        "cooker_mark_selection",
        "text_apply_translation",
        "niagara_bulk_set_parameter",
    ):
        assert tool not in found, (
            f"{tool} is reporting status=ok with an unchecked success counter "
            f"again - it was fixed on 2026-08-22"
        )
