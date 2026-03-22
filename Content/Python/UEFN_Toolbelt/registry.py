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

import inspect
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
    source: str = ""                    # filename for custom plugins; empty = core tool
    # Extensible Metadata (for Plugin Hub)
    author: str = ""
    version: str = "1.0.0"
    url: str = ""
    last_updated: str = ""


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
        source: str = "",
        author: str = "",
        version: str = "1.0.0",
        url: str = "",
        last_updated: str = "",
    ) -> None:
        """Register a tool, with overwrite protection for core system tools."""
        if not source:
            try:
                source = inspect.getfile(fn)
            except Exception:
                source = ""
                
        is_custom = "Custom_Plugins" in source.replace("\\", "/")
        
        if name in self._tools:
            existing_source = self._tools[name].source
            existing_is_custom = "Custom_Plugins" in existing_source.replace("\\", "/")
            
            # Namespace Protection: Do not allow custom plugins to overwrite core tools
            if is_custom and not existing_is_custom:
                log_error(f"[SECURITY] Custom plugin attempted to overwrite core OS tool '{name}'. Registration rejected.")
                return
                
            log_warning(f"Re-registering tool '{name}' (hot-reload?).")
                
        self._tools[name] = ToolEntry(
            name=name,
            fn=fn,
            category=category,
            description=description,
            icon=icon,
            shortcut=shortcut,
            tags=tags or [],
            source=source,
            author=author,
            version=version,
            url=url,
            last_updated=last_updated,
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
        source: str = "",
        author: str = "",
        version: str = "1.0.0",
        url: str = "",
        last_updated: str = "",
    ) -> Callable:
        """
        @register_tool decorator factory. Use this on the tool's entry-point.

            @register_tool(name="my_tool", category="Materials", description="...")
            def run(**kwargs): ...
        """
        def _wrap(fn: Callable) -> Callable:
            self.register(name, fn, category, description, icon, shortcut, tags, source, author, version, url, last_updated)
            return fn
        return _wrap

    # ── Execution ─────────────────────────────────────────────────────────────

    def execute(self, tool_id: str, **kwargs) -> Any:
        """
        Execute a tool by name. All exceptions are caught and logged so a
        failing tool never crashes the editor session.

        Returns the tool's return value, or None on failure.
        """
        if tool_id not in self._tools:
            log_error(f"Unknown tool: '{tool_id}'. Call list_tools() to see available tools.")
            return None

        entry = self._tools[tool_id]
        log_info(f"Running tool: {tool_id}")
        try:
            return entry.fn(**kwargs)
        except Exception:
            log_error(f"Tool '{tool_id}' raised an exception:\n{traceback.format_exc()}")
            return None

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self, tool_name: Optional[str] = None) -> List[str]:
        """
        Validate tools for correct schema and standard conventions.
        Returns a list of warning/error strings. Empty list means perfect health.
        """
        checks = [tool_name] if tool_name else list(self._tools.keys())
        errors = []
        for name in checks:
            if name not in self._tools:
                errors.append(f"[{name}] Tool not found.")
                continue
                
            entry = self._tools[name]
            if not name.islower() or " " in name:
                errors.append(f"[{name}] Name must be snake_case without spaces.")
            if not entry.description:
                errors.append(f"[{name}] Missing description. UI will be blank.")
            if not entry.category:
                errors.append(f"[{name}] Missing category. UI tab will be undefined.")
            
            sig = inspect.signature(entry.fn)
            if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                errors.append(f"[{name}] Function signature should accept **kwargs.")
                
        return errors

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
                "source": e.source,
                "author": e.author,
                "version": e.version,
                "url": e.url,
                "last_updated": e.last_updated,
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
    author: str = "",
    version: str = "1.0.0",
    url: str = "",
    last_updated: str = "",
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
        author=author,
        version=version,
        url=url,
        last_updated=last_updated,
    )
