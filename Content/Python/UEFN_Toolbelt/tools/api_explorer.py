"""
UEFN TOOLBELT — api_explorer.py
========================================
Inspect and document the live UEFN Python API directly from the editor.

Tools:
  api_search         — fuzzy-search class/function names across the unreal module
  api_inspect        — print full signature + docstring for a class or function
  api_generate_stubs — write a .pyi stub file for a class (or all of unreal)
  api_list_subsystems — print every *Subsystem* class available in this build
  api_export_full    — export complete unreal module stubs to Saved/UEFN_Toolbelt/stubs/

Why:
  UEFN ships without official .pyi stubs, so IDEs show no autocomplete for
  unreal.* calls. This tool generates them from the live running API so you get
  full autocomplete in VS Code / PyCharm without waiting for Epic to ship them.

Output:
  Saved/UEFN_Toolbelt/stubs/unreal.pyi   (full module stub)
  Saved/UEFN_Toolbelt/stubs/<ClassName>.pyi (per-class stub)
  Saved/UEFN_Toolbelt/api_report.json    (machine-readable index)
"""

from __future__ import annotations

import inspect
import json
import os
import re
import types
import sys
from typing import Any

import unreal

from UEFN_Toolbelt.registry import register_tool

# ─── Output paths ─────────────────────────────────────────────────────────────

_SAVED = os.path.join(
    unreal.Paths.project_saved_dir(), "UEFN_Toolbelt"
)
_STUB_DIR = os.path.join(_SAVED, "stubs")
_REPORT_PATH = os.path.join(_SAVED, "api_report.json")


def _ensure_dirs() -> None:
    os.makedirs(_STUB_DIR, exist_ok=True)


# ─── Reflection helpers ────────────────────────────────────────────────────────

def _all_unreal_names() -> list[str]:
    """Return every name exported from the unreal module."""
    return [n for n in dir(unreal) if not n.startswith("__")]


def _is_class(obj: Any) -> bool:
    return inspect.isclass(obj)


def _is_function(obj: Any) -> bool:
    return callable(obj) and not inspect.isclass(obj)


def _safe_doc(obj: Any) -> str:
    try:
        doc = inspect.getdoc(obj) or ""
        return doc.strip()
    except Exception:
        return ""


def _safe_signature(obj: Any) -> str:
    """Return a best-effort signature string; falls back to '(*args, **kwargs)'."""
    try:
        sig = inspect.signature(obj)
        return str(sig)
    except (ValueError, TypeError):
        return "(*args, **kwargs)"


def _classify_member(obj: Any) -> str:
    if inspect.isclass(obj):
        return "class"
    if callable(obj):
        return "function"
    if isinstance(obj, property):
        return "property"
    return "constant"


# ─── Stub generation ──────────────────────────────────────────────────────────

def _method_stub(name: str, method: Any, indent: str = "    ") -> str:
    """Generate a stub line for a single method."""
    sig = _safe_signature(method)
    doc = _safe_doc(method)
    lines: list[str] = []

    # Detect static / class methods (best-effort for unreal's C-ext methods)
    is_static = isinstance(inspect.getattr_static(method, "__func__", None), staticmethod)

    if is_static:
        lines.append(f"{indent}@staticmethod")
        lines.append(f"{indent}def {name}{sig}: ...")
    else:
        # Ensure 'self' is first param when not already present
        if sig.startswith("(self") or sig == "(*args, **kwargs)":
            lines.append(f"{indent}def {name}{sig}: ...")
        else:
            # Strip leading '(' and prepend self
            inner = sig[1:] if sig.startswith("(") else sig
            lines.append(f"{indent}def {name}(self, {inner}: ...")

    if doc:
        first_line = doc.split("\n")[0]
        lines.append(f'{indent}    """{first_line}"""')

    return "\n".join(lines)


def _class_stub(cls_name: str) -> str:
    """Generate a full .pyi stub for a class."""
    try:
        cls = getattr(unreal, cls_name)
    except AttributeError:
        return f"# {cls_name} not found in unreal module\n"

    if not inspect.isclass(cls):
        return f"# {cls_name} is not a class\n"

    # Bases
    base_names: list[str] = []
    for base in cls.__bases__:
        bname = base.__name__
        if bname != "object":
            base_names.append(bname)
    base_str = f"({', '.join(base_names)})" if base_names else ""

    lines: list[str] = [f"class {cls_name}{base_str}:"]
    doc = _safe_doc(cls)
    if doc:
        lines.append(f'    """{doc}"""')
        lines.append("")

    members_added = 0
    for attr_name in sorted(dir(cls)):
        if attr_name.startswith("__"):
            continue
        try:
            member = getattr(cls, attr_name)
        except Exception:
            continue

        if callable(member):
            lines.append(_method_stub(attr_name, member))
            lines.append("")
            members_added += 1
        else:
            # Emit as a typed attribute if we can determine type
            type_hint = type(member).__name__
            lines.append(f"    {attr_name}: {type_hint}")
            members_added += 1

    if members_added == 0:
        lines.append("    ...")

    return "\n".join(lines) + "\n"


def _module_stub_header() -> str:
    return (
        '"""\n'
        'unreal.pyi — Auto-generated UEFN Python API stubs\n'
        f'Generated by UEFN Toolbelt api_explorer on UEFN build: '
        f'{getattr(unreal, "ENGINE_VERSION_STRING", "unknown")}\n'
        '\n'
        'DO NOT EDIT — regenerate with:\n'
        '  import UEFN_Toolbelt as tb; tb.run("api_export_full")\n'
        '"""\n'
        'from __future__ import annotations\n'
        'from typing import Any, Optional, List, Tuple, Union, overload\n\n'
    )


# ─── Tool implementations ──────────────────────────────────────────────────────

def _tool_api_search(query: str = "", category: str = "all",
                     max_results: int = 40) -> None:
    """
    Fuzzy-search the unreal module by name.

    Args:
        query:       Substring to search for (case-insensitive).
        category:   "class", "function", "constant", or "all".
        max_results: Cap on printed results.
    """
    query_lower = query.lower()
    results: list[tuple[str, str]] = []

    for name in _all_unreal_names():
        if query_lower and query_lower not in name.lower():
            continue
        try:
            obj = getattr(unreal, name)
        except Exception:
            continue
        kind = _classify_member(obj)
        if category != "all" and kind != category:
            continue
        results.append((name, kind))

    results.sort(key=lambda x: (x[1], x[0]))

    unreal.log(f"[API Explorer] Search '{query}' → {len(results)} results "
               f"(showing up to {max_results})")
    unreal.log("")

    kind_icons = {"class": "🔷", "function": "🔶", "constant": "⬛", "property": "🔹"}
    for name, kind in results[:max_results]:
        icon = kind_icons.get(kind, "  ")
        unreal.log(f"  {icon} {kind:10s}  unreal.{name}")

    if len(results) > max_results:
        unreal.log(f"  … {len(results) - max_results} more — narrow your query.")


def _tool_api_inspect(name: str = "", **kwargs) -> None:
    """
    Print full signature and docstring for any unreal.* name.

    Args:
        name: e.g. "EditorActorSubsystem" or "log"
    """
    if not name:
        unreal.log_warning("[API Explorer] Provide a name to inspect. "
                           "Example: tb.run('api_inspect', name='EditorActorSubsystem')")
        return

    obj = getattr(unreal, name, None)
    if obj is None:
        unreal.log_warning(f"[API Explorer] 'unreal.{name}' not found.")
        return

    kind = _classify_member(obj)
    unreal.log(f"\n{'─'*60}")
    unreal.log(f"  unreal.{name}  [{kind}]")
    unreal.log(f"{'─'*60}")

    if inspect.isclass(obj):
        # Bases
        bases = [b.__name__ for b in obj.__bases__ if b.__name__ != "object"]
        if bases:
            unreal.log(f"  Inherits: {', '.join(bases)}")

        # Doc
        doc = _safe_doc(obj)
        if doc:
            unreal.log("")
            for line in doc.split("\n")[:8]:
                unreal.log(f"  {line}")

        # Members
        unreal.log("")
        unreal.log("  Methods:")
        for attr in sorted(dir(obj)):
            if attr.startswith("__"):
                continue
            try:
                member = getattr(obj, attr)
            except Exception:
                continue
            if callable(member):
                sig = _safe_signature(member)
                unreal.log(f"    .{attr}{sig}")
    else:
        sig = _safe_signature(obj)
        unreal.log(f"  Signature: {name}{sig}")
        doc = _safe_doc(obj)
        if doc:
            unreal.log("")
            for line in doc.split("\n")[:12]:
                unreal.log(f"  {line}")

    unreal.log(f"{'─'*60}\n")


def _tool_api_generate_stubs(class_name: str = "", **kwargs) -> None:
    """
    Write a .pyi stub file for a single class.

    Args:
        class_name: e.g. "EditorActorSubsystem". Omit to stub every class.
    """
    _ensure_dirs()

    if class_name:
        stub = _class_stub(class_name)
        out_path = os.path.join(_STUB_DIR, f"{class_name}.pyi")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("from __future__ import annotations\n\n")
            f.write(stub)
        unreal.log(f"[API Explorer] ✓ Wrote {out_path}")
    else:
        # Stub all classes
        all_names = _all_unreal_names()
        classes = [n for n in all_names
                   if inspect.isclass(getattr(unreal, n, None))]
        unreal.log(f"[API Explorer] Generating stubs for {len(classes)} classes…")
        for cls_name in classes:
            stub = _class_stub(cls_name)
            out_path = os.path.join(_STUB_DIR, f"{cls_name}.pyi")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("from __future__ import annotations\n\n")
                f.write(stub)
        unreal.log(f"[API Explorer] ✓ Wrote {len(classes)} stub files to {_STUB_DIR}")


def _tool_api_list_subsystems(**kwargs) -> None:
    """Print every *Subsystem class available in this UEFN build."""
    subsystems: list[str] = []
    for name in _all_unreal_names():
        if "subsystem" not in name.lower():
            continue
        try:
            obj = getattr(unreal, name)
        except Exception:
            continue
        if inspect.isclass(obj):
            subsystems.append(name)

    subsystems.sort()
    unreal.log(f"\n[API Explorer] Subsystems in this build ({len(subsystems)} found):\n")
    for name in subsystems:
        try:
            cls = getattr(unreal, name)
            bases = [b.__name__ for b in cls.__bases__ if b.__name__ != "object"]
            base_str = f"  ← {', '.join(bases)}" if bases else ""
        except Exception:
            base_str = ""
        unreal.log(f"  unreal.{name}{base_str}")

    unreal.log("")
    unreal.log("Usage example:")
    unreal.log("  sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)")


def _tool_api_export_full(include_constants: bool = False) -> None:
    """
    Export a monolithic unreal.pyi stub file covering the entire module.

    Args:
        include_constants: If True, also emit module-level constant stubs.
                           Can make the file large (~10 MB on full builds).
    """
    _ensure_dirs()
    out_path = os.path.join(_STUB_DIR, "unreal.pyi")

    all_names = _all_unreal_names()
    classes   = [n for n in all_names if inspect.isclass(getattr(unreal, n, None))]
    functions = [n for n in all_names
                 if not inspect.isclass(getattr(unreal, n, None))
                 and callable(getattr(unreal, n, None))]
    constants = [n for n in all_names
                 if not inspect.isclass(getattr(unreal, n, None))
                 and not callable(getattr(unreal, n, None))] if include_constants else []

    unreal.log(
        f"[API Explorer] Exporting full stubs — "
        f"{len(classes)} classes, {len(functions)} functions, "
        f"{len(constants)} constants…"
    )

    lines: list[str] = [_module_stub_header()]

    # Module-level functions
    if functions:
        lines.append("# ── Module-level functions " + "─" * 40)
        for fn_name in sorted(functions):
            try:
                fn = getattr(unreal, fn_name)
                sig = _safe_signature(fn)
                doc = _safe_doc(fn)
                lines.append(f"def {fn_name}{sig}: ...")
                if doc:
                    first = doc.split("\n")[0]
                    lines.append(f'    """{first}"""')
                lines.append("")
            except Exception:
                pass

    # Module-level constants
    if constants:
        lines.append("# ── Module-level constants " + "─" * 39)
        for const_name in sorted(constants):
            try:
                val = getattr(unreal, const_name)
                type_hint = type(val).__name__
                lines.append(f"{const_name}: {type_hint}")
            except Exception:
                pass
        lines.append("")

    # Classes
    lines.append("# ── Classes " + "─" * 53)
    for cls_name in sorted(classes):
        try:
            lines.append(_class_stub(cls_name))
        except Exception as e:
            lines.append(f"# {cls_name}: skipped ({e})\n")

    content = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    size_kb = os.path.getsize(out_path) // 1024
    unreal.log(f"[API Explorer] ✓ Wrote {out_path}  ({size_kb} KB)")
    unreal.log("")
    unreal.log("To enable autocomplete in VS Code:")
    unreal.log(f'  Add "{_STUB_DIR}" to python.analysis.extraPaths in settings.json')
    unreal.log("  Or drop unreal.pyi into your project's .vscode/ folder.")

    # Also write the machine-readable index
    index: dict[str, Any] = {
        "build": getattr(unreal, "ENGINE_VERSION_STRING", "unknown"),
        "class_count": len(classes),
        "function_count": len(functions),
        "classes": sorted(classes),
        "functions": sorted(functions),
    }
    with open(_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    unreal.log(f"[API Explorer] ✓ Index written to {_REPORT_PATH}")


# ─── Registration ──────────────────────────────────────────────────────────────

@register_tool(
    name="api_search",
    category="API Explorer",
    description="Fuzzy-search class/function names across the live unreal module",
    icon="🔍",
    tags=["api", "search", "inspect", "stubs"],
)
def api_search(query: str = "", category: str = "all", max_results: int = 40, **kwargs) -> dict:
    """Returns: dict: {"status", "query", "result_count"}"""
    query_lower = query.lower()
    results = [
        (name, _classify_member(getattr(unreal, name, None)))
        for name in _all_unreal_names()
        if (not query_lower or query_lower in name.lower())
        and getattr(unreal, name, None) is not None
        and (category == "all" or _classify_member(getattr(unreal, name, None)) == category)
    ]
    _tool_api_search(query=query, category=category, max_results=max_results)
    return {"status": "ok", "query": query, "result_count": len(results)}


@register_tool(
    name="api_inspect",
    category="API Explorer",
    description="Print full signature + docstring for any unreal.* class or function",
    icon="🔎",
    tags=["api", "inspect", "signature", "docs"],
)
def api_inspect(name: str = "", **kwargs) -> dict:
    """Returns: dict: {"status", "name", "found"}"""
    found = name and getattr(unreal, name, None) is not None
    _tool_api_inspect(name=name)
    return {"status": "ok" if found else "error", "name": name, "found": found}


@register_tool(
    name="api_generate_stubs",
    category="API Explorer",
    description="Write .pyi stub file for one class (or all classes if name omitted)",
    icon="📄",
    tags=["api", "stubs", "autocomplete", "pyi"],
)
def api_generate_stubs(class_name: str = "", **kwargs) -> dict:
    """Returns: dict: {"status", "path"}"""
    _ensure_dirs()
    _tool_api_generate_stubs(class_name=class_name)
    path = os.path.join(_STUB_DIR, f"{class_name}.pyi") if class_name else _STUB_DIR
    return {"status": "ok", "path": path}


@register_tool(
    name="api_list_subsystems",
    category="API Explorer",
    description="Print every *Subsystem class available in this UEFN build",
    icon="🔷",
    tags=["api", "subsystems", "list"],
)
def api_list_subsystems(**kwargs) -> dict:
    """Returns: dict: {"status", "count", "subsystems": [name]}"""
    subsystems = sorted(
        name for name in _all_unreal_names()
        if "subsystem" in name.lower()
        and inspect.isclass(getattr(unreal, name, None))
    )
    _tool_api_list_subsystems()
    return {"status": "ok", "count": len(subsystems), "subsystems": subsystems}


@register_tool(
    name="api_export_full",
    category="API Explorer",
    description="Export monolithic unreal.pyi stub file for full IDE autocomplete",
    icon="📦",
    tags=["api", "stubs", "export", "autocomplete", "pyi"],
)
def api_export_full(include_constants: bool = False, **kwargs) -> dict:
    """Returns: dict: {"status", "path", "size_kb"}"""
    _ensure_dirs()
    _tool_api_export_full(include_constants=include_constants)
    out_path = os.path.join(_STUB_DIR, "unreal.pyi")
    size_kb = os.path.getsize(out_path) // 1024 if os.path.exists(out_path) else 0
    return {"status": "ok", "path": out_path, "size_kb": size_kb}
