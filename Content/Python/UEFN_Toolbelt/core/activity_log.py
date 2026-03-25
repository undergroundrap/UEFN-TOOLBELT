"""
UEFN TOOLBELT — core/activity_log.py
======================================
Rolling activity log for every tb.run() call.

Every tool execution is recorded with:
  - tool name
  - status (ok / error / unknown)
  - duration in milliseconds
  - ISO timestamp
  - error message if it failed

Stored in two places:
  - In-memory ring buffer (last MAX_ENTRIES calls, survives hot-reload)
  - Saved/UEFN_Toolbelt/activity_log.json (persists across sessions)

Usage (from registry.py):
    from .core.activity_log import record

    record(tool_id="publish_audit", status="ok", duration_ms=342)
    record(tool_id="scatter_hism", status="error", duration_ms=12,
           error="No actors selected.")

Usage (from tools / MCP):
    from .core.activity_log import get_log, get_stats, clear_log
"""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime
from typing import Any

# ── Config ─────────────────────────────────────────────────────────────────────

MAX_ENTRIES = 500   # ring buffer cap — old entries drop off the front automatically.
                    # Disk file is always overwritten (never appended), so this also
                    # caps the on-disk size (~100 KB at 500 entries, ~200 bytes each).
                    # Bump this number if you need longer session history.
_LOG_FILENAME = "activity_log.json"

# ── In-memory ring buffer ──────────────────────────────────────────────────────
# deque with maxlen automatically drops oldest entries when full.
# Populated on first use; pre-loaded from disk if the file exists.

_ring: deque[dict] = deque(maxlen=MAX_ENTRIES)
_initialized: bool = False


def _log_path() -> str:
    import unreal
    return os.path.join(
        unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", _LOG_FILENAME
    )


def _ensure_initialized() -> None:
    """Load persisted log from disk on first access."""
    global _initialized
    if _initialized:
        return
    _initialized = True
    try:
        path = _log_path()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("entries", [])[-MAX_ENTRIES:]:
                _ring.append(entry)
    except Exception:
        pass  # Corrupt or missing file — start fresh


def _flush() -> None:
    """Write the current ring buffer to disk."""
    try:
        path = _log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"entries": list(_ring)}, f, indent=2)
    except Exception:
        pass  # Never crash the editor over a log write


# ── Public API ─────────────────────────────────────────────────────────────────

def record(
    tool_id: str,
    status: str,
    duration_ms: float,
    error: str | None = None,
) -> None:
    """
    Record one tool execution. Called automatically by registry.execute().

    Args:
        tool_id:     Tool name (e.g. "publish_audit")
        status:      "ok", "error", or "unknown"
        duration_ms: Wall-clock execution time in milliseconds
        error:       Exception message if status == "error", else None
    """
    _ensure_initialized()
    entry: dict[str, Any] = {
        "tool":        tool_id,
        "status":      status,
        "duration_ms": round(duration_ms, 1),
        "timestamp":   datetime.now().isoformat(timespec="seconds"),
    }
    if error:
        entry["error"] = error[:500]  # cap long tracebacks
    _ring.append(entry)
    _flush()


def get_log(last_n: int = 50) -> list[dict]:
    """
    Return the most recent N entries, newest first.

    Args:
        last_n: How many entries to return (default 50, max MAX_ENTRIES)
    """
    _ensure_initialized()
    entries = list(_ring)
    entries.reverse()
    return entries[:min(last_n, MAX_ENTRIES)]


def get_stats() -> dict:
    """
    Return aggregate stats for the current session log.

    Returns:
        {
          "total_calls":   int,
          "ok":            int,
          "errors":        int,
          "slowest":       {"tool": str, "duration_ms": float},
          "most_called":   {"tool": str, "count": int},
          "error_rate_pct": float,
          "recent_errors": [{"tool", "error", "timestamp"}, ...]  # last 5
        }
    """
    _ensure_initialized()
    entries = list(_ring)
    if not entries:
        return {
            "total_calls": 0, "ok": 0, "errors": 0,
            "slowest": None, "most_called": None,
            "error_rate_pct": 0.0, "recent_errors": [],
        }

    ok_count    = sum(1 for e in entries if e["status"] == "ok")
    error_count = sum(1 for e in entries if e["status"] == "error")
    total       = len(entries)

    slowest = max(entries, key=lambda e: e["duration_ms"])

    counts: dict[str, int] = {}
    for e in entries:
        counts[e["tool"]] = counts.get(e["tool"], 0) + 1
    top_tool = max(counts, key=lambda k: counts[k])

    recent_errors = [
        {"tool": e["tool"], "error": e.get("error", ""), "timestamp": e["timestamp"]}
        for e in reversed(entries)
        if e["status"] == "error"
    ][:5]

    return {
        "total_calls":    total,
        "ok":             ok_count,
        "errors":         error_count,
        "error_rate_pct": round(100 * error_count / total, 1) if total else 0.0,
        "slowest":        {"tool": slowest["tool"], "duration_ms": slowest["duration_ms"]},
        "most_called":    {"tool": top_tool, "count": counts[top_tool]},
        "recent_errors":  recent_errors,
    }


def clear_log() -> int:
    """Clear the in-memory buffer and the on-disk log. Returns count cleared."""
    _ensure_initialized()
    count = len(_ring)
    _ring.clear()
    _flush()
    return count
