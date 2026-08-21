"""
Every registered tool must return a structured dict on every path.
==============================================================================
CLAUDE.md, TOOL_STATUS.md and .claude/rules/tool_authoring.md all state that
every @register_tool function returns {"status": "ok"/"error", ...} and that
"zero None returns remain in the codebase". That was not true: six tools fell
off the end of their body and returned None implicitly, including all four MCP
bridge tools — the ones an agent calls to control the bridge, where a None
result means it cannot tell whether the listener actually came up.

Nothing enforced the claim, so it quietly stopped being accurate. This does.

Parsed rather than executed: importing every tool module needs a live editor.
"""

from __future__ import annotations

import ast
import pathlib

PKG = pathlib.Path("Content/Python/UEFN_Toolbelt")


def _always_returns(body: list) -> bool:
    """True when every path through this block ends in return or raise."""
    if not body:
        return False
    last = body[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return True
    if isinstance(last, ast.If):
        return (bool(last.orelse)
                and _always_returns(last.body)
                and _always_returns(last.orelse))
    if isinstance(last, (ast.With, ast.AsyncWith)):
        return _always_returns(last.body)
    if isinstance(last, ast.Try):
        if last.finalbody and _always_returns(last.finalbody):
            return True
        main = _always_returns(last.orelse) if last.orelse else _always_returns(last.body)
        return (main and bool(last.handlers)
                and all(_always_returns(h.body) for h in last.handlers))
    if isinstance(last, ast.Match):
        return bool(last.cases) and all(_always_returns(c.body) for c in last.cases)
    return False


def _tool_functions():
    for path in sorted(PKG.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            deco = next(
                (d for d in node.decorator_list
                 if isinstance(d, ast.Call)
                 and getattr(d.func, "id", "") == "register_tool"),
                None,
            )
            if deco is None:
                continue
            kw = {k.arg: k.value for k in deco.keywords}
            name = kw.get("name")
            yield (path, node,
                   name.value if isinstance(name, ast.Constant) else node.name)


def test_the_audit_actually_finds_tools():
    """A parser that silently matches nothing would make every check below pass."""
    assert sum(1 for _ in _tool_functions()) > 300


def test_no_tool_returns_none_implicitly():
    leaky = [
        f"{p.name}:{fn.lineno} {name}"
        for p, fn, name in _tool_functions()
        if not _always_returns(fn.body)
    ]
    assert leaky == [], (
        "these tools fall off the end and return None, which an MCP client "
        f"cannot distinguish from a tool that legitimately returned nothing: {leaky}"
    )


def test_no_tool_returns_a_bare_none():
    offenders = []
    for path, fn, name in _tool_functions():
        nested = {
            node
            for inner in ast.walk(fn)
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)) and inner is not fn
            for node in ast.walk(inner)
        }
        for node in ast.walk(fn):
            if node in nested or not isinstance(node, ast.Return):
                continue
            if node.value is None or (isinstance(node.value, ast.Constant)
                                      and node.value.value is None):
                offenders.append(f"{path.name}:{node.lineno} {name}")
    assert offenders == [], f"explicit None returns: {offenders}"


def test_mcp_bridge_tools_report_their_result():
    """
    Regression guard for the specific case that motivated this. These are the
    tools an agent calls to bring the bridge up; returning None told it nothing.
    """
    wanted = {"mcp_start", "mcp_stop", "mcp_restart", "mcp_status"}
    seen = {}
    for _p, fn, name in _tool_functions():
        if name in wanted:
            seen[name] = fn
    assert wanted <= set(seen), f"missing: {wanted - set(seen)}"
    for name, fn in seen.items():
        assert _always_returns(fn.body), f"{name} can still return None"
