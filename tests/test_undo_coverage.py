"""Tools that spawn or destroy level actors must be undoable.

`.claude/mcp_reference.md` tells users, and tells agents driving the bridge:

    ### Undo safety — all actor ops are wrapped in transactions

That was not true. niagara_spawn_system spawned an actor and
niagara_clear_systems deleted every Niagara actor in a folder, both outside any
transaction, so Ctrl+Z could not bring back a level someone had just cleared.

Scope is deliberately narrow. This checks tools that create or destroy LEVEL
ACTORS, because that is what the editor's undo stack covers and what the doc
promises. It does not check tools that edit and save assets - texture
compression, nanite flags, physics assets and so on. A ScopedEditorTransaction
does not roll back a package already written to disk, so demanding one there
would be theatre: a wrapper that looks like safety and provides none.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Content" / "Python" / "UEFN_Toolbelt" / "tools"

# Creating or destroying a level actor is exactly what undo covers.
LEVEL_ACTOR_MUTATORS = (
    "spawn_actor_from_class",
    "spawn_actor_from_object",
    "spawn_system_at_location",
    "destroy_actor",
)

TRANSACTIONS = ("undo_transaction", "ScopedEditorTransaction")

EXEMPT_FILES = {
    # Wire commands: an agent issues one op per call and can undo via the
    # bridge's own `undo` command, which is a transaction boundary already.
    "mcp_bridge.py",
    # Spawns and deletes its own fixtures; a test is not user work.
    "integration_test.py",
}


def _tool_name(fn: ast.FunctionDef) -> str:
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
    return ""


def _unwrapped_tools() -> list[str]:
    findings = []
    for path in sorted(TOOLS.glob("*.py")):
        if path.name in EXEMPT_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            name = _tool_name(fn)
            if not name:
                continue
            body = ast.unparse(fn)
            used = [m for m in LEVEL_ACTOR_MUTATORS if f".{m}(" in body]
            if not used:
                continue
            if not any(t in body for t in TRANSACTIONS):
                findings.append(f"{path.name}  {name}  uses {sorted(set(used))}")
    return findings


def test_actor_spawn_and_delete_is_undoable():
    findings = _unwrapped_tools()
    assert not findings, (
        "these tools create or destroy level actors outside any transaction, so "
        "Ctrl+Z cannot undo them - and mcp_reference.md tells users it can:\n  "
        + "\n  ".join(findings)
    )


def test_the_documented_promise_still_says_this():
    """If the promise is ever withdrawn, this test should be reconsidered
    rather than silently guarding something nobody claims any more."""
    doc = (ROOT / ".claude" / "mcp_reference.md").read_text(encoding="utf-8")
    assert "wrapped in transactions" in doc, (
        "mcp_reference.md no longer promises transaction-wrapped actor ops; "
        "decide whether this guard is still the contract you want"
    )
