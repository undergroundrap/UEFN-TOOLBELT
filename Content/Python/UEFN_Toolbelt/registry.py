"""
UEFN TOOLBELT — Tool Registry
========================================
One-line registration makes adding any new feature trivial.

ADDING A NEW TOOL (3 steps):
    1. Create Content/Python/UEFN_Toolbelt/tools/my_tool.py
    2. Decorate your entry-point function:

        @register_tool(
            name="my_tool",
            category="Utilities",
            description="Does something amazing",
            icon="T_Icon",          # optional — Content Browser icon path
            shortcut="Ctrl+Alt+M",  # optional — hotkey hint shown in UI
        )
        def run(**kwargs):
            ...

    3. Add an import in tools/__init__.py — that's it!

The ToolRegistry is a singleton. Access it anywhere via:
    from UEFN_Toolbelt.registry import get_registry
    registry = get_registry()
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import unreal
from .core import log_info, log_error, log_warning

# ─────────────────────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolEntry:
    name: str                           # unique snake_case key
    fn: Callable[..., Any]              # the tool's entry-point function
    category: str = "Utilities"         # tab/sidebar grouping
    description: str = ""               # tooltip / help text
    icon: str = ""                      # optional Content Browser icon path
    shortcut: str = ""                  # optional keyboard shortcut hint
    tags: List[str] = field(default_factory=list)  # searchable tags


# ─────────────────────────────────────────────────────────────────────────────
#  Registry singleton
# ─────────────────────────────────────────────────────────────────────────────

class ToolRegistry:
    """
    Central registry for all UEFN Toolbelt tools.

    Supports:
        • One-line registration via @register_tool decorator
        • Execute-by-name with error containment
        • Category-filtered listing for UI tab building
        • Tag-based search
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolEntry] = {}

    # ── Registration ─────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        category: str = "Utilities",
        description: str = "",
        icon: str = "",
        shortcut: str = "",
        tags: Optional[List[str]] = None,
    ) -> None:
        """Register a tool. Overwrites any previous registration with the same name."""
        if name in self._tools:
            log_warning(f"Re-registering tool '{name}' (hot-reload?).")
        self._tools[name] = ToolEntry(
            name=name,
            fn=fn,
            category=category,
            description=description,
            icon=icon,
            shortcut=shortcut,
            tags=tags or [],
        )
        log_info(f"  ✓ Registered: [{category}] {name}")

    def decorator(
        self,
        name: str,
        category: str = "Utilities",
        description: str = "",
        icon: str = "",
        shortcut: str = "",
        tags: Optional[List[str]] = None,
    ) -> Callable:
        """
        @register_tool decorator factory. Use this on the tool's entry-point.

            @register_tool(name="my_tool", category="Materials", description="...")
            def run(**kwargs): ...
        """
        def _wrap(fn: Callable) -> Callable:
            self.register(name, fn, category, description, icon, shortcut, tags)
            return fn
        return _wrap

    # ── Execution ─────────────────────────────────────────────────────────────

    def execute(self, name: str, **kwargs) -> Any:
        """
        Execute a tool by name. All exceptions are caught and logged so a
        failing tool never crashes the editor session.

        Returns the tool's return value, or None on failure.
        """
        if name not in self._tools:
            log_error(f"Unknown tool: '{name}'. Call list_tools() to see available tools.")
            return None

        entry = self._tools[name]
        log_info(f"Running tool: {name}")
        try:
            return entry.fn(**kwargs)
        except Exception:
            log_error(f"Tool '{name}' raised an exception:\n{traceback.format_exc()}")
            return None

    # ── Querying ──────────────────────────────────────────────────────────────

    def list_tools(self, category: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Return list-of-dict summaries, optionally filtered by category.

        Each dict has keys: name, category, description, icon, shortcut.
        """
        entries = self._tools.values()
        if category:
            entries = (e for e in entries if e.category == category)
        return [
            {
                "name": e.name,
                "category": e.category,
                "description": e.description,
                "icon": e.icon,
                "shortcut": e.shortcut,
                "tags": e.tags,
            }
            for e in entries
        ]

    def categories(self) -> List[str]:
        """Return sorted unique category names — used to build sidebar tabs."""
        return sorted({e.category for e in self._tools.values()})

    def search(self, query: str) -> List[Dict[str, str]]:
        """
        Case-insensitive substring search across name, description, and tags.
        """
        q = query.lower()
        results = []
        for e in self._tools.values():
            haystack = " ".join([e.name, e.description] + e.tags).lower()
            if q in haystack:
                results.append({
                    "name": e.name,
                    "category": e.category,
                    "description": e.description,
                })
        return results

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# ─────────────────────────────────────────────────────────────────────────────
#  Singleton accessor & convenience decorator
# ─────────────────────────────────────────────────────────────────────────────

_REGISTRY: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Return the global singleton ToolRegistry, creating it if needed."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ToolRegistry()
    return _REGISTRY


def register_tool(
    name: str,
    category: str = "Utilities",
    description: str = "",
    icon: str = "",
    shortcut: str = "",
    tags: Optional[List[str]] = None,
) -> Callable:
    """
    Module-level convenience decorator that registers with the global registry.

    Usage (inside any tool module):
        from UEFN_Toolbelt.registry import register_tool

        @register_tool(
            name="my_tool",
            category="Materials",
            description="Does cool things",
        )
        def run(**kwargs):
            ...
    """
    return get_registry().decorator(
        name=name,
        category=category,
        description=description,
        icon=icon,
        shortcut=shortcut,
        tags=tags,
    )
