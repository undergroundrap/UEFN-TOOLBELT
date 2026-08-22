"""Re-applying a material preset must not delete the asset first.

On 2026-08-21 `material_apply_preset` failed live with:

    Force Deleting 1 Package(s): MI_gold_Cube43
    SourceControl: Reverted 1 file.
    Message dialog closed, result: 1, title: Overwrite Existing Object
    Error: Failed to create material instance

The instance was still assigned to the actor, so it could not be deleted;
revision control restored the file, and `create_asset()` on the occupied path
raised a modal. A modal inside an automation tool blocks a batch run and
returns None when declined - which is what happened.

The fix updates an existing instance in place. These pin the shape of that fix,
because the delete-first version looks perfectly reasonable in review and would
come back.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CORE = (Path(__file__).resolve().parents[1] / "Content" / "Python" /
        "UEFN_Toolbelt" / "core" / "__init__.py")

# The exact old shape: an existence check whose entire body is a delete.
#
# Indent-insensitive on purpose. The first draft matched a fixed-indent string,
# which ast.unparse never produces the same way at module level (4 spaces) and
# inside a function (8) - so the detector silently matched nothing. The
# self-check below is what caught it.
_DELETE_FIRST = re.compile(
    r"if unreal\.EditorAssetLibrary\.does_asset_exist\(full_path\):\s*\n"
    r"\s*unreal\.EditorAssetLibrary\.delete_asset\(full_path\)"
)


def _func(name: str) -> ast.FunctionDef:
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() not found in core/__init__.py")


def _calls(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                out.append(f.attr)
            elif isinstance(f, ast.Name):
                out.append(f.id)
    return out


def _has_delete_first_shape(src: str) -> bool:
    """Parse and re-unparse so formatting differences cannot hide it."""
    return _DELETE_FIRST.search(ast.unparse(ast.parse(src))) is not None


def test_existing_instances_are_reused_not_recreated():
    fn = _func("create_material_instance")
    assert "_clear_instance_overrides" in _calls(fn), (
        "create_material_instance no longer resets an existing instance - either "
        "it went back to delete-and-recreate (the modal bug) or stale parameters "
        "now bleed between presets"
    )


def test_the_reuse_branch_is_guarded_on_the_asset_type():
    """Reuse only when what is already there really is a material instance."""
    src = ast.unparse(_func("create_material_instance"))
    assert "isinstance(existing, unreal.MaterialInstanceConstant)" in src


def test_the_delete_first_shape_is_gone():
    """An earlier draft of this test asserted load_asset ran before
    delete_asset. That was vacuous - the old code loaded the PARENT material
    first, so it passed against the very code it was written to reject. This
    names the actual shape instead.

    delete_asset may still appear: for a wrong-typed asset squatting on the
    path, and for cleanup when the parent cannot be set. Never as the
    unconditional opener.
    """
    assert not _has_delete_first_shape(CORE.read_text(encoding="utf-8")), (
        "create_material_instance deletes whenever the asset already exists "
        "again - that is what produced the Overwrite Existing Object modal"
    )


def test_that_detector_actually_fires():
    """Non-vacuous: the real old body must be caught, the current one must not."""
    old = "\n".join((
        "def create_material_instance():",
        "    if unreal.EditorAssetLibrary.does_asset_exist(full_path):",
        "        unreal.EditorAssetLibrary.delete_asset(full_path)",
    ))
    assert _has_delete_first_shape(old)
    assert not _has_delete_first_shape(CORE.read_text(encoding="utf-8"))


def test_the_clearing_helper_reports_failure_rather_than_pretending():
    """It returns a bool the caller checks. A helper that always returned True,
    or returned None, would make the caller's warning unreachable - the exact
    silent-success pattern this codebase keeps getting bitten by."""
    fn = _func("_clear_instance_overrides")
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    consts = {ast.unparse(r.value) for r in returns if r.value is not None}
    assert "True" in consts and "cleared" in consts, (
        f"_clear_instance_overrides no longer reports both outcomes: {consts}"
    )
