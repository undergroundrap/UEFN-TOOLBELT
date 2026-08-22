"""Every registered tool must return a dict carrying "status".

CLAUDE.md and the README both state:

    All 362 tools (100%) return {"status": "ok"/"error", ...} structured dicts
    as of Phase 21. Zero None returns remain in the codebase - MCP callers can
    read every result directly without parsing log output.

That was not true. On 2026-08-22 an audit found 37 returns across 16 tools with
no `status` key at all - the entire Bulk Ops category returned a bare
{"count": N}, and several error paths returned {"error": msg}. A caller doing

    result.get("status") == "ok"

read every one of those successes as a failure, and one doing result["status"]
got a KeyError. The claim in the docs was the thing keeping anyone from
checking.

The tools are fixed; this test is what stops the claim going stale again.

NOT covered here, deliberately: the handlers in mcp_bridge.py. Those are wire
commands, not registered tools, and _execute_command already wraps every one of
them in {"success": bool, "result": ...}. The envelope carries the signal, so a
handler returning {"lines": [...]} is correct. Requiring `status` there would be
false-positive noise of exactly the kind that made ref_audit_broken useless.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Content" / "Python" / "UEFN_Toolbelt" / "tools"

# Wire-protocol handlers, wrapped by the transport rather than self-describing.
EXEMPT_FILES = {"mcp_bridge.py"}


def _registered_functions(tree: ast.Module):
    """Functions carrying a decorator call — @register_tool(...) and friends."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and any(
            isinstance(d, ast.Call) for d in node.decorator_list
        ):
            yield node


def _dict_returns_without_status(fn: ast.FunctionDef):
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)):
            continue
        keys = {
            k.value
            for k in node.value.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        if "status" not in keys:
            yield node.lineno, sorted(keys)


def _scan() -> list[str]:
    findings: list[str] = []
    for path in sorted(TOOLS.glob("*.py")):
        if path.name in EXEMPT_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _registered_functions(tree):
            for lineno, keys in _dict_returns_without_status(fn):
                findings.append(f"{path.name}:{lineno}  {fn.name}  returns {keys}")
    return findings


def test_every_tool_return_carries_status():
    findings = _scan()
    assert not findings, (
        f"{len(findings)} tool return(s) have no 'status' key. CLAUDE.md and the "
        "README promise callers can read status on every tool, so a caller "
        "checking result.get('status') == 'ok' reads these successes as "
        "failures:\n  " + "\n  ".join(findings)
    )


def test_the_detector_would_catch_a_regression():
    """Non-vacuous: prove the scan rejects the shape that was actually wrong."""
    bad = ast.parse(
        "@register_tool(name='x')\n"
        "def run_x():\n"
        "    return {'count': 0}\n"
    )
    fn = next(_registered_functions(bad))
    assert list(_dict_returns_without_status(fn)) == [(3, ["count"])]

    good = ast.parse(
        "@register_tool(name='x')\n"
        "def run_x():\n"
        "    return {'status': 'ok', 'count': 0}\n"
    )
    fn = next(_registered_functions(good))
    assert list(_dict_returns_without_status(fn)) == []


def test_the_bridge_envelope_still_supplies_the_signal():
    """The exemption above is only sound while the transport keeps wrapping.

    If _execute_command stops adding {"success": ...}, mcp_bridge handlers
    returning bare dicts become a real gap and the exemption must be revisited.
    """
    bridge = (TOOLS / "mcp_bridge.py").read_text(encoding="utf-8")
    assert '"success": True, "result": result' in bridge, (
        "the MCP transport no longer wraps handler results, so mcp_bridge.py "
        "can no longer be exempt from the status contract"
    )
