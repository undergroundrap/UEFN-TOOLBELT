"""
The integration suite must read keys its tools actually return.
==============================================================================
`result.get("some_key", 0)` silently yields the default when the tool never
returns that key. The assertion still passes — it checks `status` — so the suite
stays green while its own report says something false.

Seven of these were live on 2026-08-21. `stamp_save` logged "3 actors" and
reported "saved 0 actors"; `actor_folder_list` logged 4 folders and reported 0;
`rogue_actor_scan` logged 49 flagged actors and reported 0. Nothing was hidden —
but a suite whose output cannot be read at a glance is one nobody reads, and
every real bug found that week came from reading output rather than a red check.

Static, so it costs nothing and needs no editor.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

TOOLS = pathlib.Path("Content/Python/UEFN_Toolbelt/tools")
SUITE = TOOLS / "integration_test.py"
BLOCKS = ("body", "orelse", "finalbody", "handlers")


@pytest.fixture(scope="module")
def tool_return_keys() -> dict:
    """tool name -> keys it can return, or None when it splats or returns a var."""
    out: dict = {}
    for path in sorted(TOOLS.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = None
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, "id", "") == "register_tool":
                    for k in d.keywords:
                        if k.arg == "name" and isinstance(k.value, ast.Constant):
                            name = k.value.value
            if not name:
                continue
            keys: set = set()
            unknown = False
            for r in ast.walk(node):
                if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict):
                    for k in r.value.keys:
                        if k is None:                      # {**other} — can't know
                            unknown = True
                        elif isinstance(k, ast.Constant):
                            keys.add(k.value)
                elif (isinstance(r, ast.Return) and r.value is not None
                      and not isinstance(r.value, ast.Dict)):
                    unknown = True                          # returns a variable
            out[name] = None if unknown else keys
    return out


def _own_gets(stmt, var):
    """
    `var.get('k')` in THIS statement only.

    Nested bodies are excluded — a .get() inside an `if` may belong to a later
    tb.run — and the receiver must be the result variable itself, so a .get() on
    a nested dict is not mistaken for a top-level return key. Both of those were
    false-positive sources when this analysis was first written.
    """
    skip = set()
    for field in BLOCKS:
        for sub in (getattr(stmt, field, None) or []):
            for node in ast.walk(sub):
                skip.add(id(node))
    for c in ast.walk(stmt):
        if id(c) in skip:
            continue
        if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                and c.func.attr == "get"
                and isinstance(c.func.value, ast.Name) and c.func.value.id == var
                and c.args and isinstance(c.args[0], ast.Constant)
                and isinstance(c.args[0].value, str)):
            yield c.args[0].value


def _scan(tool_keys):
    """(lineno, tool, key) for every suite read of a key the tool never returns."""
    src = SUITE.read_text(encoding="utf-8")
    found, checked = [], []

    def visit(body, tool, var):
        for stmt in body:
            if (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Attribute)
                    and stmt.value.func.attr == "run" and stmt.value.args
                    and isinstance(stmt.value.args[0], ast.Constant)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)):
                tool, var = stmt.value.args[0].value, stmt.targets[0].id
                continue
            if tool:
                for key in _own_gets(stmt, var):
                    known = tool_keys.get(tool)
                    if known is None or key == "status":
                        continue
                    checked.append((tool, key))
                    if key not in known:
                        found.append((stmt.lineno, tool, key, sorted(known)))
            for field in ("body", "orelse", "finalbody"):
                if getattr(stmt, field, None):
                    tool, var = visit(getattr(stmt, field), tool, var)
            for h in getattr(stmt, "handlers", []):
                tool, var = visit(h.body, tool, var)
        return tool, var

    for fn in ast.parse(src).body:
        if isinstance(fn, ast.FunctionDef):
            visit(fn.body, None, None)
    return found, checked


def test_the_analysis_actually_checks_something(tool_return_keys):
    """An analyser matching nothing would make the real test vacuously pass."""
    assert len(tool_return_keys) > 300
    _found, checked = _scan(tool_return_keys)
    assert len(checked) > 40, f"only {len(checked)} reads examined — traversal broke"


def test_suite_reads_only_keys_its_tools_return(tool_return_keys):
    found, _checked = _scan(tool_return_keys)
    lines = [f"L{ln} {tool}.get({key!r}) — returns {known[:8]}"
             for ln, tool, key, known in found]
    assert found == [], (
        "the integration suite reads keys these tools never return, so it will "
        "report the default and still pass:\n  " + "\n  ".join(lines)
    )
