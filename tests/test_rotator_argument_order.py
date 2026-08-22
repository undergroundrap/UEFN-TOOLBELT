"""Some `unreal.*` struct constructors take positional args in C++ field order.

Quirk #41. Confirmed live on UEFN 42.00, 2026-08-21:

    unreal.Rotator(10, 20, 30) -> roll=10  pitch=20  yaw=30
    unreal.Color(10, 20, 30)   -> r=30     g=20      b=10

So `unreal.Rotator(0, yaw, 0)` sets **pitch**, and `unreal.Color(r, g, b, 255)`
swaps red and blue. Nothing raises. Props tilt instead of turning, red signs
render blue, and every tool reports success.

31 Rotator sites across 14 modules had it, plus one Color site in sign_tools.
CLAUDE.md was documenting the wrong order, which is the likely reason they were
all written that way.

The Rotator case was found from a log line rather than a bug report:
`bulk_randomize` defaults to rot_range=360 (yaw) and pitch_range=0, so on a
zeroed fixture the 2026-08-21 run should have produced a random yaw and a pitch
of 0. It printed `{pitch: 23.004272, yaw: 0.0, roll: -0.0}`.

This fails on any positional call with a non-zero argument. All-zero calls are
allowed: (0, 0, 0) means the same thing in either order, and rewriting ~13 of
them would be churn with no safety gained.

`unreal.Vector` (X, Y, Z) and `unreal.LinearColor` (R, G, B, A) are declared in
the expected order and are safe positionally, so they are not guarded here.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [ROOT / "Content" / "Python", ROOT / "tests"]
SCAN_FILES = [ROOT / "mcp_server.py", ROOT / "client.py"]


# Structs whose positional order follows the C++ field declaration rather than
# the order everything else describes them in. Both confirmed live on UEFN 42.00
# (2026-08-21):
#
#   unreal.Rotator(10, 20, 30) -> roll=10  pitch=20  yaw=30
#   unreal.Color(10, 20, 30)   -> r=30     g=20      b=10
#
# unreal.Vector and unreal.LinearColor are declared in the order you would
# expect (X,Y,Z and R,G,B,A), so they are not listed here.
_FIELD_ORDER_STRUCTS = ("Rotator", "Color")


def _is_zero(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and node.value == 0
    )


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.exists():
            files.extend(sorted(root.rglob("*.py")))
    files.extend(f for f in SCAN_FILES if f.exists())
    return files


def _offending_calls(path: Path) -> list[tuple[int, str]]:
    """Positional unreal.Rotator(...) calls that are not entirely zeros."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in _FIELD_ORDER_STRUCTS):
            continue
        if node.keywords:          # roll=/pitch=/yaw= — unambiguous, fine
            continue
        if not node.args:          # Rotator() — fine
            continue
        if any(isinstance(a, ast.Starred) for a in node.args):
            out.append((node.lineno, ast.unparse(node)))
            continue
        if all(_is_zero(a) for a in node.args):
            continue
        out.append((node.lineno, ast.unparse(node)))
    return out


def test_no_positional_rotator_calls():
    findings = [
        f"{p.relative_to(ROOT).as_posix()}:{ln}  {src}"
        for p in _python_files()
        for ln, src in _offending_calls(p)
    ]
    assert not findings, (
        "positional unreal.Rotator/Color call(s) found. Their argument order "
        "follows the C++ field declaration: Rotator is (roll, pitch, yaw) and "
        "Color is (b, g, r, a), so these set the wrong field silently. Use "
        "keyword args. See UEFN_QUIRKS.md Quirk #41.\n  "
        + "\n  ".join(findings)
    )


def test_the_detector_would_catch_a_regression():
    """Non-vacuous: the exact shape that was wrong must be rejected, and the
    two shapes that are fine must not be."""
    import tempfile

    def check(src: str) -> int:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(src)
            tmp = Path(fh.name)
        try:
            return len(_offending_calls(tmp))
        finally:
            tmp.unlink()

    assert check("r = unreal.Rotator(0, yaw, 0)") == 1, "missed the real bug shape"
    assert check("c = unreal.Color(r, g, b, 255)") == 1, "missed the Color shape"
    assert check("r = unreal.Rotator(*rotation)") == 1, "missed the starred shape"
    assert check("r = unreal.Rotator(roll=0, pitch=0, yaw=yaw)") == 0
    assert check("r = unreal.Rotator(0, 0, 0)") == 0
    assert check("c = unreal.Color(r=r, g=g, b=b, a=255)") == 0


def test_the_mcp_bridge_maps_the_wire_order_explicitly():
    """The bridge documents rotations as [pitch, yaw, roll]. Unpacking that
    straight into the constructor put every component on the wrong axis."""
    bridge = (ROOT / "Content" / "Python" / "UEFN_Toolbelt" / "tools"
              / "mcp_bridge.py").read_text(encoding="utf-8")
    assert "def _rotator_from_list(" in bridge
    assert bridge.count("_rotator_from_list(") >= 4, (
        "the bridge has rotation entry points that bypass the mapper"
    )
