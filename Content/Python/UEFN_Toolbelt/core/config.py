"""
UEFN TOOLBELT — Persistent Config
==================================
A thin JSON-backed key/value store that survives install.py updates.

Lives at: Saved/UEFN_Toolbelt/config.json
            ↑ outside the package directory, never overwritten on update

Usage (from any tool):
    from ..core import get_config
    cfg = get_config()

    mesh = cfg.get("arena.fallback_mesh")           # returns default if not set
    cfg.set("scatter.default_folder", "MyScatter")  # persists immediately
    cfg.reset("scatter.default_folder")             # back to default

Keys use dot-notation namespaced by tool family:
    arena.*      scatter.*     text.*
    screenshot.* snapshot.*    lod.*

DEFAULTS act as the fallback for any key not present in config.json.
To add a new configurable value: add it to DEFAULTS below.
Tools read via cfg.get("key") — they never need to know if the user
customised the value or if the default is being used.
"""

from __future__ import annotations

import json
import os
from typing import Any

# ── Defaults — the canonical fallback for every configurable value ─────────────
# These are the values tools get when the user hasn't customised anything.
# Never read these directly in tool code — always go through cfg.get().

DEFAULTS: dict[str, Any] = {
    # Arena Generator
    "arena.fallback_mesh":      "/Engine/BasicShapes/Cube",

    # Scatter / Foliage
    "scatter.default_folder":   "Scatter",
    "scatter.default_radius":   2000.0,
    "scatter.default_count":    50,

    # Text Painter
    "text.default_folder":      "ToolbeltText",
    "text.default_color":       "#FFFFFF",
    "text.default_size":        100.0,

    # Screenshots
    "screenshot.default_width":  1920,
    "screenshot.default_height": 1080,
    "screenshot.default_name":   "shot",

    # Snapshots
    "snapshot.default_scope":   "all",

    # Verse Device Graph
    "verse.project_path":       "",

    # Image Import (import_image_from_clipboard / import_image_from_url)
    # Empty string = auto-detect project mount at call time → /{mount}/UEFN_Toolbelt/Textures
    "import.default_dir":       "",

    # UI Theme
    "ui.theme":                 "toolbelt_dark",
}


class Config:
    """
    Lazy-loading JSON config store.
    Loads from disk on first access, auto-saves on every set().
    Thread-safety is not required — UEFN Python is single-threaded.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._data: dict[str, Any] | None = None  # None = not loaded yet

    # ── Private ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _ensure_loaded(self) -> None:
        if self._data is None:
            self._load()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def get(self, key: str, fallback: Any = None) -> Any:
        """
        Return the value for key.
        Priority: user config → DEFAULTS → fallback argument.
        """
        self._ensure_loaded()
        if key in self._data:
            return self._data[key]
        if key in DEFAULTS:
            return DEFAULTS[key]
        return fallback

    def set(self, key: str, value: Any) -> None:
        """Set a value and immediately persist it to disk."""
        self._ensure_loaded()
        self._data[key] = value
        self._save()

    def reset(self, key: str) -> bool:
        """
        Remove a user-set value, restoring the default.
        Returns True if the key existed, False if it wasn't set.
        """
        self._ensure_loaded()
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def all(self) -> dict[str, Any]:
        """
        Return a snapshot of all values — merging defaults with user overrides.
        User-set values take priority. Keys with defaults that haven't been
        customised show the default value with an 'is_default' marker in
        config_list output (not in this dict — this is the clean merged view).
        """
        self._ensure_loaded()
        merged = dict(DEFAULTS)
        merged.update(self._data)
        return merged

    def is_default(self, key: str) -> bool:
        """True if the user has not customised this key."""
        self._ensure_loaded()
        return key not in self._data


# ── Singleton ──────────────────────────────────────────────────────────────────

_config_instance: Config | None = None


def get_config() -> Config:
    """
    Return the shared Config singleton.
    Path resolves lazily so this is safe to call at module import time
    (before unreal.Paths is available in some edge cases).
    """
    global _config_instance
    if _config_instance is None:
        import unreal
        path = os.path.join(
            unreal.Paths.project_saved_dir(),
            "UEFN_Toolbelt",
            "config.json",
        )
        _config_instance = Config(path)
    return _config_instance
