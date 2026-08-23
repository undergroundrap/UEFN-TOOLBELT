"""Asset APIs that report failure by return value must have that value read.

The engine never raises for these. It hands back a value and moves on:

    save_asset / save_loaded_asset       -> False
    rename_asset                         -> False
    duplicate_asset                      -> None
    consolidate_assets                   -> False
    EditorActorSubsystem.destroy_actor   -> False

Called as a bare statement, the failure vanishes. The work is done in memory,
the tool counts it, the user is told it succeeded, and the change is gone after
a restart.

This started as one bug - tag_add set a metadata tag on read-only content,
discarded save_asset's False, and logged a checkmark two lines under the
editor's own "failed to save" message. An audit on 2026-08-22 found 50 discarded
returns of this family across the codebase, including:

  * texture_set_compression counting textures whose enum lookup failed
  * six nanite/uv/collision batch tools counting meshes that never saved
  * rename_strip_prefix, the sibling of a function fixed the day before
  * prefab_export_to_disk, which reported assets migrated between projects
    while neither the duplicate nor the save had worked

make_directory is not in the list on purpose: it returns True when the folder
already exists, and a real failure makes the following write fail loudly anyway.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "Content" / "Python" / "UEFN_Toolbelt"

# Report failure by return value, never by raising.
MUST_CHECK = {
    "save_asset",
    "save_loaded_asset",
    "rename_asset",
    "duplicate_asset",
    "consolidate_assets",
}

# destroy_actor exists in two forms and only one of them returns anything:
#
#   EditorActorSubsystem.destroy_actor(actor)  -> bool     (takes the actor)
#   Actor.destroy_actor()                      -> None     (takes nothing)
#
# The argument count separates them cleanly. Flagging the void form would be a
# false positive - foliage_convert_selected_to_actor uses exactly that form.
ARG_FORM_ONLY = {"destroy_actor"}

# Test scaffolding tears down its own fixtures; a failed cleanup is not user work.
EXEMPT = {"integration_test.py"}


def _discarded(path: Path) -> list[tuple[int, str]]:
    """Calls used as a bare statement, i.e. with the return value dropped."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr in MUST_CHECK or func.attr in ARG_FORM_ONLY and node.value.args:
            out.append((node.lineno, func.attr))
    return out


def _python_files() -> list[Path]:
    return [
        p
        for p in sorted(PKG.rglob("*.py"))
        if "__pycache__" not in p.parts and p.name not in EXEMPT
    ]


def test_no_asset_write_result_is_discarded():
    findings = [
        f"{p.relative_to(PKG).as_posix()}:{ln}  {name}(...) result discarded"
        for p in _python_files()
        for ln, name in _discarded(p)
    ]
    assert not findings, (
        f"{len(findings)} call(s) drop a return value that is the only signal of "
        "failure. The edit will be made in memory, reported as success, and lost "
        "on restart:\n  " + "\n  ".join(findings)
    )


def test_the_detector_would_catch_a_regression():
    """Non-vacuous: the bare-statement form must be rejected, checked forms not."""
    import tempfile

    def count(src: str) -> int:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(src)
            tmp = Path(fh.name)
        try:
            return len(_discarded(tmp))
        finally:
            tmp.unlink()

    assert count("unreal.EditorAssetLibrary.save_asset(p)") == 1
    assert count("eal.rename_asset(a, b)") == 1
    assert count("eal.duplicate_asset(a, b)") == 1
    # Reading the result in any form is fine.
    assert count("if not eal.save_asset(p):\n    pass") == 0
    assert count("ok = eal.rename_asset(a, b)") == 0
    assert count("return eal.save_loaded_asset(x)") == 0

    # destroy_actor: the subsystem form returns bool, the Actor method is void.
    assert count("actor_sub.destroy_actor(actor)") == 1, "missed the bool form"
    assert count("actor.destroy_actor()") == 0, "flagged the void Actor method"
    assert count("if actor_sub.destroy_actor(actor):\n    pass") == 0


def test_core_supplies_the_checked_helpers():
    """The fix depends on these existing, so pin them."""
    core = (PKG / "core" / "__init__.py").read_text(encoding="utf-8")
    assert "def save_asset(" in core
    assert "def save_loaded_asset(" in core
    # Both must report a False return, not only an exception.
    for helper in ("save_asset", "save_loaded_asset"):
        body = core.split(f"def {helper}(", 1)[1].split("\ndef ", 1)[0]
        assert "log_warning" in body, (
            f"core.{helper} no longer warns on a False return, which is the "
            f"whole point of routing calls through it"
        )
