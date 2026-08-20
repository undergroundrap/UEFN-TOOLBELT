"""
Generate the UEFN API dependency manifest.
==============================================================================
Statically extracts every `unreal.*` symbol the Toolbelt depends on, by parsing
the source with `ast` — no editor and no imports required.

The output (UEFN_Toolbelt/api_dependencies.json) is what smoke_test Layer 2 probes
at runtime, so that an engine update which removes or renames an API is reported
as a specific missing symbol instead of a mystery crash in whichever tool
happened to touch it first.

Usage:
    python scripts/gen_api_manifest.py            # write the manifest
    python scripts/gen_api_manifest.py --check    # fail if it is out of date (CI)

Why AST and not grep: grep matches `unreal.pyi` inside docstrings and comments.
The parser only sees real attribute access.
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "Content" / "Python" / "UEFN_Toolbelt"
# Lives INSIDE the package: install.py copies only Content/Python/UEFN_Toolbelt,
# so anything under docs/ never reaches an end user's editor.
MANIFEST_PATH = PACKAGE_DIR / "api_dependencies.json"

SKIP_DIRS = {"__pycache__"}


class _UnrealVisitor(ast.NodeVisitor):
    """Collect `unreal.X` and `unreal.X.Y` attribute chains."""

    def __init__(self) -> None:
        # symbol -> set of second-level attributes seen on it
        self.symbols: dict[str, set[str]] = defaultdict(set)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # unreal.X.Y  → Attribute(value=Attribute(value=Name('unreal'), attr='X'), attr='Y')
        inner = node.value
        if (
            isinstance(inner, ast.Attribute)
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "unreal"
        ):
            self.symbols[inner.attr].add(node.attr)
        # unreal.X → Attribute(value=Name('unreal'), attr='X')
        elif isinstance(inner, ast.Name) and inner.id == "unreal":
            self.symbols.setdefault(node.attr, set())
        self.generic_visit(node)


def _optional_declarations(tree: ast.Module) -> set[str]:
    """
    Read a module's `__optional_unreal_apis__` declaration.

    A module lists the unreal.* names it uses but does not require, either as
    "ClassName" or "ClassName.method_name". Those are APIs it probes with hasattr
    or guards with core.missing_unreal_apis(), degrading cleanly when they are
    absent.

    Without this every guarded API still counted as a hard dependency, so the
    smoke test stayed permanently red on UEFN 42.00 for problems that were
    already handled — and a health check that is always red gets ignored.
    """
    declared: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__optional_unreal_apis__"
                   for t in node.targets):
            continue
        if isinstance(node.value, (ast.Tuple, ast.List, ast.Set)):
            for elt in node.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    declared.add(elt.value)
    return declared


def _iter_sources():
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        if SKIP_DIRS.intersection(path.parts):
            continue
        yield path


def build_manifest() -> dict:
    symbols: dict[str, set[str]] = defaultdict(set)
    users: dict[str, set[str]] = defaultdict(set)
    # (symbol, attribute) -> files that touch that specific attribute.
    attr_users: dict[tuple[str, str], set[str]] = defaultdict(set)

    # file -> names that file declares it does not require
    optional_by_file: dict[str, set[str]] = {}

    for path in _iter_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # pragma: no cover — CI syntax gate catches this first
            print(f"SKIP (syntax error) {path}: {exc}", file=sys.stderr)
            continue

        visitor = _UnrealVisitor()
        visitor.visit(tree)

        rel = path.relative_to(PACKAGE_DIR).as_posix()
        optional_by_file[rel] = _optional_declarations(tree)
        for symbol, attrs in visitor.symbols.items():
            symbols[symbol] |= attrs
            users[symbol].add(rel)
            for attr in attrs:
                attr_users[(symbol, attr)].add(rel)

    def _is_optional(name: str, consumers: set[str]) -> bool:
        """
        Optional only when EVERY consumer declares it so.

        One module guarding an API does not make it safe for another module that
        calls it unguarded — that file would still break. Requiring unanimity
        means adding an unguarded consumer silently re-promotes the API to
        required, which is the safe direction to fail.
        """
        if not consumers:
            return False
        return all(name in optional_by_file.get(f, set()) for f in consumers)

    return {
        "_comment": (
            "Auto-generated by scripts/gen_api_manifest.py — do not hand-edit. "
            "Lists every unreal.* symbol the Toolbelt depends on. smoke_test Layer 2 "
            "probes these with hasattr() to detect API removals after an engine update. "
            "'attributes' maps each method/constant to the files that call it "
            "specifically — the symbol-level 'used_by' is every consumer of the class, "
            "which is far wider and must not be reported for a single missing method. "
            "'optional' marks APIs every consumer guards, so their absence is reported "
            "as handled rather than as a failure."
        ),
        "symbol_count": len(symbols),
        "symbols": {
            name: {
                "attributes": {
                    attr: {
                        "used_by": sorted(attr_users[(name, attr)]),
                        "optional": _is_optional(f"{name}.{attr}", attr_users[(name, attr)])
                                    or _is_optional(name, users[name]),
                    }
                    for attr in sorted(attrs)
                },
                "used_by": sorted(users[name]),
                "optional": _is_optional(name, users[name]),
            }
            for name, attrs in sorted(symbols.items())
        },
    }


def main(argv: list[str]) -> int:
    manifest = build_manifest()
    serialized = json.dumps(manifest, indent=2, sort_keys=False) + "\n"

    if "--check" in argv:
        if not MANIFEST_PATH.exists():
            print(f"MISSING {MANIFEST_PATH.relative_to(REPO_ROOT)} — run: "
                  f"python scripts/gen_api_manifest.py")
            return 1
        current = MANIFEST_PATH.read_text(encoding="utf-8")
        if current != serialized:
            print("API dependency manifest is out of date — run: "
                  "python scripts/gen_api_manifest.py")
            return 1
        print(f"OK — manifest current ({manifest['symbol_count']} symbols)")
        return 0

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(serialized, encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.relative_to(REPO_ROOT)} — "
          f"{manifest['symbol_count']} unreal.* symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
