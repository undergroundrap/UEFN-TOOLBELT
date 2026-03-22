"""
UEFN TOOLBELT — Config Tools
=============================
Read/write the persistent Toolbelt config from the dashboard or MCP.

Config lives at: Saved/UEFN_Toolbelt/config.json
Survives install.py updates — never inside the package directory.

Usage:
    tb.run("config_list")                              # see everything
    tb.run("config_get", key="arena.fallback_mesh")
    tb.run("config_set", key="scatter.default_folder", value="MyScatter")
    tb.run("config_reset", key="scatter.default_folder")
"""

from __future__ import annotations

from ..core import log_info, log_warning, log_error, get_config
from ..core.config import DEFAULTS
from ..core import theme as _theme
from ..registry import register_tool


@register_tool(
    name="config_list",
    category="Utilities",
    description="Show all Toolbelt config values — user overrides and defaults.",
    tags=["config", "settings", "list"],
)
def run_config_list(**kwargs) -> dict:
    """
    Prints every configurable key with its current value.
    Keys the user has customised are marked [custom].
    Keys using the built-in default are marked [default].

    Returns:
        dict: {"status", "values": {key: value}, "custom_count", "total"}
    """
    cfg = get_config()
    merged = cfg.all()

    lines = ["\n=== UEFN Toolbelt Config ==="]
    for key in sorted(merged):
        tag = "[default]" if cfg.is_default(key) else "[custom] "
        lines.append(f"  {tag}  {key:40s} = {merged[key]!r}")
    lines.append(f"\n  {sum(1 for k in merged if not cfg.is_default(k))} custom / {len(merged)} total keys")
    lines.append(f"  File: {cfg._path}")
    log_info("\n".join(lines))

    custom_count = sum(1 for k in merged if not cfg.is_default(k))
    return {
        "status": "ok",
        "values": merged,
        "custom_count": custom_count,
        "total": len(merged),
    }


@register_tool(
    name="config_get",
    category="Utilities",
    description="Get the current value of a Toolbelt config key.",
    tags=["config", "settings", "get"],
)
def run_config_get(key: str = "", **kwargs) -> dict:
    """
    Args:
        key: The config key to read (e.g. "arena.fallback_mesh").

    Returns:
        dict: {"status", "key", "value", "is_default"}
    """
    if not key:
        log_warning("config_get: provide a key. Run config_list to see all keys.")
        return {"status": "error", "message": "No key provided."}

    cfg = get_config()
    value = cfg.get(key)

    if value is None and key not in DEFAULTS:
        log_warning(f"config_get: unknown key '{key}'. Run config_list to see valid keys.")
        return {"status": "error", "message": f"Unknown key: '{key}'"}

    is_def = cfg.is_default(key)
    log_info(f"  {key} = {value!r}  ({'default' if is_def else 'custom'})")
    return {"status": "ok", "key": key, "value": value, "is_default": is_def}


@register_tool(
    name="config_set",
    category="Utilities",
    description="Set a persistent Toolbelt config value. Survives restarts and updates.",
    tags=["config", "settings", "set"],
)
def run_config_set(key: str = "", value: str = "", **kwargs) -> dict:
    """
    Args:
        key:   The config key to set (e.g. "scatter.default_folder").
        value: The new value. Strings, numbers, and booleans are all valid.
               Numbers and booleans passed as strings are auto-converted.

    Returns:
        dict: {"status", "key", "value", "previous"}
    """
    if not key:
        log_warning("config_set: provide a key and value.")
        return {"status": "error", "message": "No key provided."}

    if key not in DEFAULTS:
        log_warning(f"config_set: '{key}' is not a known config key. Run config_list to see valid keys.")
        return {"status": "error", "message": f"Unknown key: '{key}'"}

    # Auto-convert type to match the default's type
    default_val = DEFAULTS.get(key)
    coerced = value
    try:
        if isinstance(default_val, bool):
            coerced = str(value).lower() in ("true", "1", "yes")
        elif isinstance(default_val, int):
            coerced = int(value)
        elif isinstance(default_val, float):
            coerced = float(value)
    except (ValueError, TypeError):
        pass  # keep as string if conversion fails

    cfg = get_config()
    previous = cfg.get(key)
    cfg.set(key, coerced)

    log_info(f"  Config updated: {key} = {coerced!r}  (was: {previous!r})")
    return {"status": "ok", "key": key, "value": coerced, "previous": previous}


@register_tool(
    name="config_reset",
    category="Utilities",
    description="Reset a config key back to its built-in default value.",
    tags=["config", "settings", "reset"],
)
def run_config_reset(key: str = "", **kwargs) -> dict:
    """
    Args:
        key: The config key to reset. Pass "all" to wipe all customisations.

    Returns:
        dict: {"status", "key", "default_value", "was_custom"}
    """
    if not key:
        log_warning("config_reset: provide a key, or 'all' to reset everything.")
        return {"status": "error", "message": "No key provided."}

    cfg = get_config()

    if key == "all":
        count = sum(1 for k in DEFAULTS if not cfg.is_default(k))
        for k in list(DEFAULTS.keys()):
            cfg.reset(k)
        log_info(f"  Config reset: {count} custom values cleared, all keys back to defaults.")
        return {"status": "ok", "key": "all", "cleared": count}

    if key not in DEFAULTS:
        log_warning(f"config_reset: unknown key '{key}'.")
        return {"status": "error", "message": f"Unknown key: '{key}'"}

    was_custom = not cfg.is_default(key)
    cfg.reset(key)
    default_val = DEFAULTS[key]
    log_info(f"  Config reset: {key} → {default_val!r}  ({'was custom' if was_custom else 'was already default'})")
    return {"status": "ok", "key": key, "default_value": default_val, "was_custom": was_custom}


# ── Theme tools ────────────────────────────────────────────────────────────────

@register_tool(
    name="theme_list",
    category="Utilities",
    description="List all available Toolbelt UI themes.",
    tags=["theme", "appearance", "ui"],
)
def run_theme_list(**kwargs) -> dict:
    """
    Returns:
        dict: {"status", "themes": [str], "current": str}
    """
    themes = _theme.list_themes()
    current = _theme.get_current_theme()
    log_info(f"  Available themes: {themes}  |  Active: {current}")
    return {"status": "ok", "themes": themes, "current": current}


@register_tool(
    name="theme_set",
    category="Utilities",
    description="Switch the Toolbelt UI theme. Applies live to all open windows and persists across restarts.",
    tags=["theme", "appearance", "ui", "set"],
)
def run_theme_set(name: str = "", **kwargs) -> dict:
    """
    Args:
        name: Theme name. Run theme_list to see available options.

    Returns:
        dict: {"status", "theme", "previous"}
    """
    if not name:
        return {"status": "error", "message": "Provide a theme name. Run theme_list to see options."}

    available = _theme.list_themes()
    if name not in available:
        log_warning(f"theme_set: '{name}' is not a known theme. Available: {available}")
        return {"status": "error", "message": f"Unknown theme '{name}'. Available: {available}"}

    previous = _theme.get_current_theme()
    _theme.set_theme(name)
    get_config().set("ui.theme", name)
    log_info(f"  Theme changed: {previous} → {name}")
    return {"status": "ok", "theme": name, "previous": previous}


@register_tool(
    name="theme_get",
    category="Utilities",
    description="Get the name of the currently active Toolbelt UI theme.",
    tags=["theme", "appearance", "ui", "get"],
)
def run_theme_get(**kwargs) -> dict:
    """
    Returns:
        dict: {"status", "theme": str, "palette": dict}
    """
    current = _theme.get_current_theme()
    log_info(f"  Active theme: {current}")
    return {"status": "ok", "theme": current, "palette": dict(_theme.PALETTE)}
