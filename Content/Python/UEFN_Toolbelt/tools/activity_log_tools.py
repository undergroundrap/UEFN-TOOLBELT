"""
UEFN TOOLBELT — Activity Log Tools
========================================
Expose the rolling activity log to users and the MCP bridge.

Every tb.run() call is recorded automatically by registry.execute().
These tools let you read, analyse, and clear that log from the console
or dashboard — useful for debugging, performance analysis, and auditing
which tools your AI agent has been calling.
"""

from __future__ import annotations

from ..registry import register_tool
from ..core import log_info


@register_tool(
    name="toolbelt_activity_log",
    category="System",
    description=(
        "View the rolling log of recent tool executions — tool name, status, "
        "duration, timestamp, and error message if it failed. "
        "Returns newest entries first."
    ),
    tags=["system", "log", "activity", "debug", "monitor", "history"],
)
def run_activity_log(last_n: int = 50, **kwargs) -> dict:
    """
    Return the most recent tool execution entries.

    Args:
        last_n: How many entries to return (default 50, max 500)
    """
    from ..core.activity_log import get_log
    entries = get_log(last_n=last_n)
    log_info(f"Activity log: {len(entries)} entries returned (last_n={last_n})")
    return {
        "status": "ok",
        "count": len(entries),
        "entries": entries,
    }


@register_tool(
    name="toolbelt_activity_stats",
    category="System",
    description=(
        "Aggregate stats for the current session: total calls, ok/error counts, "
        "error rate, slowest tool, most-called tool, and last 5 errors. "
        "Great for spotting flaky tools or performance bottlenecks."
    ),
    tags=["system", "stats", "activity", "debug", "monitor", "performance"],
)
def run_activity_stats(**kwargs) -> dict:
    """Return aggregate stats across all recorded tool calls this session."""
    from ..core.activity_log import get_stats
    stats = get_stats()
    log_info(
        f"Activity stats: {stats['total_calls']} calls, "
        f"{stats['errors']} errors ({stats['error_rate_pct']}%)"
    )
    return {"status": "ok", **stats}


@register_tool(
    name="toolbelt_activity_clear",
    category="System",
    description=(
        "Clear the in-memory activity log and the on-disk activity_log.json. "
        "Useful before a fresh benchmarking or testing run."
    ),
    tags=["system", "log", "activity", "clear", "reset"],
)
def run_activity_clear(**kwargs) -> dict:
    """Wipe the activity log buffer and the persisted JSON file."""
    from ..core.activity_log import clear_log
    count = clear_log()
    log_info(f"Activity log cleared ({count} entries removed).")
    return {
        "status": "ok",
        "cleared": count,
        "message": f"Cleared {count} log entries.",
    }
