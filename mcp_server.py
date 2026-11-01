"""
UEFN TOOLBELT — mcp_server.py
=========================================
External FastMCP bridge that connects Claude Code to the UEFN editor.

This is the *outside-UEFN* side of the two-process MCP architecture:

    Claude Code  ←── stdio ──→  mcp_server.py (this file, external)
                                       │
                                  HTTP POST 127.0.0.1:8765
                                       │
                             UEFN editor process
                             └── Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py

Requirements:
    pip install mcp
    (Uses the standard 'mcp' package from Anthropic — same as Claude Code MCP ecosystem)

One-time setup:
    pip install mcp
    # Place this file anywhere accessible (project root is fine)

Claude Code config — add to .mcp.json in your project root:
    {
      "mcpServers": {
        "uefn-toolbelt": {
          "command": "python",
          "args": ["<ABSOLUTE_PATH_TO_THIS_FILE>"]
        }
      }
    }

Then in UEFN (Output Log or Toolbelt dashboard):
    import UEFN_Toolbelt as tb; tb.run("mcp_start")

After that, an authenticated same-user client can use Toolbelt tools, live actor
data, viewport control, and more. Arbitrary remote Python is not exposed.

What this exposes (beyond Kirch's original 22 tools):
    run_toolbelt_tool   — call any of the 362 registered toolbelt tools by name
    list_toolbelt_tools — list registered tools with category and description, one bounded page per call
    mcp_get_log         — read the last N lines of the MCP listener log ring

Author: Ocean Bennett
License: AGPL-3.0 with visible attribution requirement (see LICENSE)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# ─── Configuration ────────────────────────────────────────────────────────────

_PORT_OVERRIDE: int | None = None
if os.environ.get("UEFN_MCP_PORT"):
    try:
        _PORT_OVERRIDE = int(os.environ["UEFN_MCP_PORT"])
        if not (1 <= _PORT_OVERRIDE <= 65535):
            raise ValueError
    except ValueError:
        _PORT_OVERRIDE = None

TOKEN_FILE_NAME = "mcp_session.json"
VERSE_BOOK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "verse-book", "docs")

# Chapter topic → filename map for verse_book_chapter()
_VERSE_CHAPTERS: dict[str, str] = {
    "overview":       "00_overview.md",
    "expressions":    "01_expressions.md",
    "primitives":     "02_primitives.md",
    "types":          "02_primitives.md",
    "containers":     "03_containers.md",
    "arrays":         "03_containers.md",
    "maps":           "03_containers.md",
    "operators":      "04_operators.md",
    "mutability":     "05_mutability.md",
    "var":            "05_mutability.md",
    "functions":      "06_functions.md",
    "control":        "07_control.md",
    "if":             "07_control.md",
    "for":            "07_control.md",
    "failure":        "08_failure.md",
    "failable":       "08_failure.md",
    "decides":        "08_failure.md",
    "structs":        "09_structs_enums.md",
    "enums":          "09_structs_enums.md",
    "classes":        "10_classes_interfaces.md",
    "interfaces":     "10_classes_interfaces.md",
    "inheritance":    "10_classes_interfaces.md",
    "subtyping":      "11_types.md",
    "access":         "12_access.md",
    "public":         "12_access.md",
    "private":        "12_access.md",
    "effects":        "13_effects.md",
    "specifiers":     "13_effects.md",
    "computes":       "13_effects.md",
    "suspends":       "13_effects.md",
    "concurrency":    "14_concurrency.md",
    "async":          "14_concurrency.md",
    "spawn":          "14_concurrency.md",
    "race":           "14_concurrency.md",
    "sync":           "14_concurrency.md",
    "live_variables": "15_live_variables.md",
    "listenable":     "15_live_variables.md",
    "modules":        "16_modules.md",
    "using":          "16_modules.md",
    "persistable":    "17_persistable.md",
    "evolution":      "18_evolution.md",
    "syntax":         "VerseSyntaxValidation.md",
    "index":          "concept_index.md",
}
REQUEST_TIMEOUT        = 30.0
LONG_OPERATION_TIMEOUT = 120.0   # for tool runs that may take longer

# ─── HTTP client ──────────────────────────────────────────────────────────────


def _redact_secret(value: Any, secret: str) -> Any:
    """Defensively remove the current handoff credential from MCP output."""
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, dict):
        return {
            _redact_secret(key, secret): _redact_secret(item, secret)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secret(item, secret) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_secret(item, secret) for item in value)
    return value


# ─── Bridge outcome contract ─────────────────────────────────────────────────
#
# WO-004 Session B. Every (status, error) pair the bridge writes before it
# queues a command (mcp_bridge.py, its _reject and _error call sites). Only one
# of these exact two-key bodies, received directly from the validated loopback
# endpoint, shows that the request was rejected before queueing. Anything else
# is an unknown outcome: a status code alone does not identify its producer.
_BRIDGE_REJECTIONS = frozenset({
    (400, "Invalid Host header"),
    (400, "Transfer-Encoding is not supported"),
    (400, "Malformed JSON request"),
    (400, "JSON body must be an object"),
    (400, "Missing 'command'"),
    (400, "'params' must be an object"),
    (401, "Authentication required"),
    (403, "Browser-originated requests are not accepted"),
    (403, "Browser preflight is not accepted"),
    (404, "Unknown path"),
    (405, "Only authenticated POST requests are accepted"),
    (411, "A valid Content-Length is required"),
    (413, "Request body is too large"),
    (415, "Content-Type must be application/json"),
})
# The bridge's own 504 body, followed by the command that was sent.
_DEADLINE_ERROR_PREFIX = "Command timed out: "
# The body stop_listener returns for a command drained before dispatch.
_STOP_DRAIN_ERROR = "MCP listener stopped before command dispatch"
_INVALID_HANDOFF = (
    "No request was sent: the UEFN MCP session handoff is invalid.\n"
    "  Restart the listener in UEFN: import UEFN_Toolbelt as tb; tb.run('mcp_restart')"
)


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: it would carry the bearer to an unvalidated URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _direct_opener() -> urllib.request.OpenerDirector:
    """A per-request opener for the bridge: no HTTP proxy and no redirect.

    ProxyHandler({}) ignores environment and system proxy settings for these
    requests only. No global opener is installed and no environment variable
    is changed.
    """
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _RefuseRedirects()
    )


def _is_timeout(error: object) -> bool:
    """True for a timeout on every supported Python.

    socket.timeout is an alias of TimeoutError from Python 3.10, and a
    separate OSError subclass before it, so both are named here.
    """
    return isinstance(error, (TimeoutError, socket.timeout))


def _bridge_error_body(raw: bytes | None) -> dict | None:
    """The bridge's exact two-key error envelope, or None for anything else."""
    if raw is None:
        return None
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if (
        isinstance(body, dict)
        and set(body) == {"success", "error"}
        and body["success"] is False
        and isinstance(body["error"], str)
    ):
        return body
    return None


def _unknown_outcome(safe_command: str, detail: str) -> str:
    """Wording for every outcome no reply confirmed. It names no cause."""
    return (
        f"No reply confirmed the outcome of command '{safe_command}' ({detail}).\n"
        "  The command may not have run, may still be queued or running, or may "
        "have completed.\n"
        "  Do not send a command that changes editor or project state again "
        "until that state has been checked. A check sent while the editor is "
        "not processing the bridge queue can also go unanswered.\n"
        "  Toolbelt cannot determine why no reply arrived; look at the UEFN editor."
    )


def _http_status_error(code: int, raw: bytes | None, command: str,
                       safe_command: str, token: str) -> Exception:
    """Classify an HTTP error status. Only the bridge's exact bodies count."""
    body = _bridge_error_body(raw)
    if body is not None:
        error = body["error"]
        if (code, error) in _BRIDGE_REJECTIONS:
            if code == 401:
                return PermissionError(
                    "UEFN MCP authentication failed: the listener rejected the "
                    "request before queueing it (HTTP 401).\n"
                    "  Restart the listener to refresh the session."
                )
            return RuntimeError(
                "The UEFN Toolbelt listener rejected the request before queueing "
                f"it (HTTP {code}: {_redact_secret(error, token)})."
            )
        if code == 504 and error == _DEADLINE_ERROR_PREFIX + command:
            return TimeoutError(_unknown_outcome(
                safe_command, "the bridge's reply deadline elapsed (HTTP 504)"
            ))
    return RuntimeError(_unknown_outcome(
        safe_command, f"an unexpected HTTP {code} response"
    ))


def _token_handoff_path() -> Path:
    override = os.environ.get("UEFN_MCP_TOKEN_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise ConnectionError(
            "No request was sent: LOCALAPPDATA is unset, so the UEFN MCP session "
            "handoff cannot be located"
        )
    return (
        Path(local_app_data)
        / "UnrealEditorFortnite"
        / "Saved"
        / "UEFN_Toolbelt"
        / TOKEN_FILE_NAME
    )


def _load_session() -> tuple[str, str]:
    """Load the current same-user listener coordinates without exposing its token."""
    path = _token_handoff_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectionError(
            "No request was sent: the UEFN MCP session handoff is missing or "
            "unreadable.\n"
            "  Start or restart the listener in UEFN: "
            "import UEFN_Toolbelt as tb; tb.run('mcp_start')"
        ) from exc
    if not isinstance(payload, dict):
        raise ConnectionError(_INVALID_HANDOFF)
    host = payload.get("host")
    port = _PORT_OVERRIDE if _PORT_OVERRIDE is not None else payload.get("port")
    token = payload.get("token")
    if (
        payload.get("version") != 1
        or host != "127.0.0.1"
        or not isinstance(port, int)
        or not (1 <= port <= 65535)
        or not isinstance(token, str)
        or len(token) < 32
    ):
        raise ConnectionError(_INVALID_HANDOFF)
    return f"http://127.0.0.1:{port}", token


def _send(command: str, params: dict | None = None,
          timeout: float = REQUEST_TIMEOUT) -> dict:
    """
    Send a command to the UEFN listener and return the result dict.

    Exactly one connection attempt is made, directly to the validated
    loopback endpoint, and none when the session handoff is missing or
    invalid. Nothing is retried.

    Raises:
        ConnectionError: No request was sent (missing or invalid handoff); the
                         connection was refused; or, with an unknown outcome,
                         the connection failed before a reply.
        PermissionError: The bridge's own 401 rejection, before queueing.
        TimeoutError:    No reply before a deadline. The outcome is unknown.
        RuntimeError:    The bridge rejected the request before queueing it,
                         stopped before dispatching it, or reported a failure;
                         or, with an unknown outcome, an unexpected response.
    """
    listener_url, token = _load_session()
    payload = json.dumps({"command": command, "params": params or {}}).encode()
    req = urllib.request.Request(
        listener_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    safe_command = _redact_secret(command, token)
    try:
        with _direct_opener().open(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            error_raw: bytes | None = exc.read()
        except Exception as read_error:
            if _is_timeout(read_error):
                raise TimeoutError(
                    _unknown_outcome(safe_command, f"no reply within {timeout}s")
                ) from None
            error_raw = None
        raise _http_status_error(
            exc.code, error_raw, command, safe_command, token
        ) from None
    except Exception as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else None
        # A timeout is a timeout whether or not urllib wrapped it, so it is
        # decided before a refusal or any other transport error.
        if _is_timeout(exc) or _is_timeout(reason):
            raise TimeoutError(
                _unknown_outcome(safe_command, f"no reply within {timeout}s")
            ) from None
        if isinstance(reason, ConnectionRefusedError):
            raise ConnectionError(
                "The connection was refused, so no request reached a UEFN "
                "Toolbelt listener.\n"
                "  Start it in UEFN: import UEFN_Toolbelt as tb; tb.run('mcp_start')"
            ) from None
        unknown = _unknown_outcome(
            safe_command,
            "the connection failed or closed before a complete reply",
        )
        if isinstance(exc, urllib.error.URLError):
            raise ConnectionError(unknown) from None
        raise RuntimeError(unknown) from None

    if status != 200:
        # urllib raises only outside 200-299, so a 2xx other than 200
        # arrives here as an ordinary response. It is not the bridge's.
        raise RuntimeError(_unknown_outcome(
            safe_command, f"an unexpected HTTP {status} response"
        ))
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("success"), bool):
        raise RuntimeError(_unknown_outcome(
            safe_command, "a reply that is not the bridge's result format"
        ))
    if body == {"success": False, "error": _STOP_DRAIN_ERROR}:
        raise RuntimeError(
            "The UEFN Toolbelt listener stopped before it dispatched "
            f"command '{safe_command}'."
        )

    body = _redact_secret(body, token)

    if not body["success"]:
        err = body.get("error", "Unknown error")
        tb  = body.get("traceback", "")
        raise RuntimeError((
            f"UEFN error for '{safe_command}': {err}\n"
            "  It may have failed before running or partway through, leaving "
            "some changes applied. Check the editor's state before continuing.\n"
            f"{tb}"
        ).strip())

    return body.get("result", {})


def _j(obj: Any) -> str:
    """Pretty-print any object as JSON string."""
    return json.dumps(obj, indent=2)


# ─── Paged listings ───────────────────────────────────────────────────────────
#
# WO-008 oversized-reply correction. list_toolbelt_tools and get_all_actors
# return one bounded page per call; every other tool keeps _j.
#
# REPLY_CHAR_BUDGET bounds len(reply): code points of the complete returned
# str, including the prefix line and every metadata field. Every reply is
# serialized with ensure_ascii=True, so it is pure ASCII, and its code points,
# UTF-8 bytes and UTF-16 code units are one number. Tokens and transport
# framing are not measured, and no client output limit is promised. The bound
# holds through four parts: no caller string is echoed, metadata is sized at
# its worst case, a configuration guard makes a one-entry page always fit, and
# the finished reply is checked and fails closed.

REPLY_CHAR_BUDGET     = 24_000  # hard ceiling on len(reply) for every page
ITEM_CHAR_LIMIT       = 20_000  # a larger entry is replaced by a placeholder
PLACEHOLDER_KEY_CHARS = 256     # a placeholder echoes a key only up to this serialized size
MAX_PAGE_LIMIT        = 500
DEFAULT_PAGE_LIMIT    = 50
_SUMMARY_FIELDS = ("name", "category", "description", "tags")
_DETAILS = ("summary", "full")
# The paging fields every page carries, in this order. Extra fields may not reuse them.
_CORE_FIELDS = ("offset", "limit", "returned", "next_offset", "complete",
                "budget_limited", "omitted_count", "listing_digest", "keys_digest")


def _ser(obj: Any) -> str:
    """Reply form: compact, ASCII-only. Entry key order is kept as the bridge sent it."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def _canon(obj: Any) -> str:
    """Canonical form: compact, ASCII-only, sorted keys. Used for digests only."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True, sort_keys=True)


def _sha(text: str) -> str:
    """'sha256:' and the lowercase hex SHA-256 of the text's bytes (the text is ASCII)."""
    return "sha256:" + hashlib.sha256(text.encode("ascii")).hexdigest()


def _key_sha256(key: str) -> str:
    """key_sha256: the SHA-256 of the key's JSON string literal, quotes included,
    as json.dumps(key, ensure_ascii=True) writes it."""
    return _sha(json.dumps(key, ensure_ascii=True))


def _item_sha256(entry: dict) -> str:
    """item_sha256: the SHA-256 of the entry's canonical form, for the entry as
    projected at the requested detail, before any placeholder."""
    return _sha(_canon(entry))


def _validate_page_args(offset: Any, limit: Any) -> tuple[int, int]:
    """Direct-call validation, before any bridge request.

    Through an MCP SDK this sees values after the SDK's own argument
    coercion: booleans, integral floats and numeric strings may already have
    become integers there.
    """
    for name, value in (("offset", offset), ("limit", limit)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer, not {type(value).__name__}")
    if offset < 0:
        raise ValueError("offset must be 0 or greater")
    if not 1 <= limit <= MAX_PAGE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_LIMIT}")
    return offset, limit


def _validate_detail(detail: Any) -> str:
    if not isinstance(detail, str) or detail not in _DETAILS:
        raise ValueError("detail must be 'summary' or 'full'")
    return detail


def _validate_text(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, not {type(value).__name__}")
    return value


def _validate_listing(result: Any, field: str, key_field: str) -> list[dict]:
    """Fail closed on a malformed bridge listing: an error, never a partial page.

    The whole listing is checked, before any filter. A duplicate key is
    malformed too: paging, both digests and the placeholders rely on one
    entry per key, so a duplicate is neither dropped nor merged. The error
    names the two positions and the key's key_sha256, never the key, so its
    length stays bounded.
    """
    if not isinstance(result, dict) or not isinstance(result.get(field), list):
        raise ValueError(f"malformed bridge reply: no {field!r} list")
    items = result[field]
    seen: dict[str, int] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"malformed bridge reply: {field}[{index}] is not an object")
        key = item.get(key_field)
        if not isinstance(key, str):
            raise ValueError(
                f"malformed bridge reply: {field}[{index}] has no string {key_field!r}")
        if key in seen:
            raise ValueError(f"malformed bridge reply: {field}[{seen[key]}] and {field}[{index}] "
                             f"share one {key_field} ({_key_sha256(key)})")
        seen[key] = index
    return items


def _project_tools(tools: list[dict], detail: str) -> list[dict]:
    if detail == "full":
        return list(tools)
    return [{k: t[k] for k in _SUMMARY_FIELDS if k in t} for t in tools]


def _filter_actors(actors: list[dict], label_contains: str, actor_path: str) -> list[dict]:
    """Applied before paging. A non-string label never matches a label filter."""
    out = actors
    if actor_path:
        out = [a for a in out if a["path"] == actor_path]
    if label_contains:
        needle = label_contains.casefold()
        out = [a for a in out if isinstance(a.get("label"), str)
               and needle in a["label"].casefold()]
    return out


def _skeleton(prefix: str, count_field: str, items_field: str, total: int, offset: int,
              limit: int, n: int, nxt: int | None, by_budget: bool, omitted: int,
              digests: tuple[str, str], extra: tuple[tuple[str, str], ...]) -> str:
    """The page with no entries: everything except the entries themselves."""
    body: dict[str, Any] = {count_field: total, "offset": offset, "limit": limit,
                            "returned": n, "next_offset": nxt, "complete": nxt is None,
                            "budget_limited": by_budget, "omitted_count": omitted,
                            "listing_digest": digests[0], "keys_digest": digests[1]}
    body.update(extra)
    body[items_field] = []
    text = prefix + _ser(body)
    if not text.endswith("[]}"):
        raise RuntimeError("internal error: unexpected skeleton shape")
    return text


def _metadata_bound(prefix: str, count_field: str, items_field: str, total: int,
                    offset: int, limit: int, n: int, digests: tuple[str, str],
                    extra: tuple[tuple[str, str], ...]) -> int:
    """An upper bound on len(_skeleton(...)) for any page holding n entries.

    The final page has next_offset null and complete true. Any other page has a
    next_offset of at most `total`'s digits and complete false. budget_limited
    false is the longer boolean, and omitted_count has no more digits than n.
    """
    def length(nxt: int | None) -> int:
        return len(_skeleton(prefix, count_field, items_field, total, offset, limit, n,
                             nxt, False, n, digests, extra))
    return max(length(total), length(None))


def _placeholder(key_field: str, key: str, entry_chars: int, entry: dict) -> dict:
    holder: dict[str, Any] = {}
    if len(json.dumps(key, ensure_ascii=True)) <= PLACEHOLDER_KEY_CHARS:
        holder[key_field] = key
    else:
        holder["key_omitted"] = True
        holder["key_sha256"] = _key_sha256(key)
    holder["omitted"] = True
    holder["omitted_chars"] = entry_chars
    holder["item_sha256"] = _item_sha256(entry)
    return holder


def _page_listing(
    items: list[dict], *, key_field: str, items_field: str, count_field: str,
    offset: int, limit: int, extra: tuple[tuple[str, str], ...] = (),
    prefix_for: Callable[[int], str] | None = None,
) -> str:
    """One deterministic page of a validated listing, never longer than REPLY_CHAR_BUDGET.

    - `items` must already have passed _validate_listing: one entry per key.
    - Order: by key alone, compared by code point.
    - listing_digest covers the complete ordered listing as delivered at this
      detail, before any placeholder is substituted; keys_digest covers the
      ordered keys only.
    - An entry whose serialized size exceeds ITEM_CHAR_LIMIT is replaced by a
      bounded placeholder. It is still enumerated and counted, and
      omitted_count says how many entries on the page are placeholders.
    - Each entry is serialized for the reply at most once, and the page holds
      at least one entry whenever any remain, so paging always advances. The
      finished reply is checked against the budget before it is returned.
    """
    budget, item_limit = REPLY_CHAR_BUDGET, ITEM_CHAR_LIMIT
    names = {count_field, items_field, *_CORE_FIELDS}
    for name, _ in extra:
        if name in names:
            raise ValueError(f"extra field {name!r} would overwrite a paging field")
        names.add(name)

    order = sorted(range(len(items)), key=lambda i: items[i][key_field])
    for a, b in zip(order, order[1:], strict=False):  # defence in depth behind _validate_listing
        if items[a][key_field] == items[b][key_field]:
            raise ValueError(
                f"duplicate {key_field} in the listing ({_key_sha256(items[a][key_field])})")
    total = len(order)
    if offset > total:
        raise ValueError(f"offset {offset} is beyond the {total} matching items; "
                         "the listing changed, so restart from offset 0")
    canon = {i: _canon(items[i]) for i in order}  # the whole listing, once per call
    digests = (_sha("[" + ",".join(canon[i] for i in order) + "]"),
               _sha(_canon([items[i][key_field] for i in order])))
    prefix = prefix_for(total) if prefix_for is not None else ""

    def bound(n: int) -> int:
        return _metadata_bound(prefix, count_field, items_field, total, offset, limit,
                               n, digests, extra)

    # Configuration guard: a one-entry page always fits, so an empty page fits
    # too, and every page advances. The longest placeholder echoes a key whose
    # serialized form is exactly PLACEHOLDER_KEY_CHARS long, quotes included.
    placeholder_max = len(_ser(_placeholder(key_field, "k" * (PLACEHOLDER_KEY_CHARS - 2),
                                            10 ** 12, {})))
    if bound(1) + max(item_limit, placeholder_max) > budget:
        raise ValueError("budget too small for the item limit and metadata")

    want = min(limit, total - offset)
    entries: list[str] = []
    used = 0          # characters of the entries, plus their separating commas
    omitted = 0
    by_budget = False
    for position in range(offset, offset + want):
        i = order[position]
        text = _ser(items[i])                     # each entry is serialized once
        is_placeholder = len(text) > item_limit
        if is_placeholder:
            text = _ser(_placeholder(key_field, items[i][key_field], len(text), items[i]))
        extra_chars = len(text) + (1 if entries else 0)
        if entries and bound(len(entries) + 1) + used + extra_chars > budget:
            by_budget = True
            break
        entries.append(text)
        used += extra_chars
        omitted += is_placeholder

    n = len(entries)
    nxt = offset + n if offset + n < total else None
    head = _skeleton(prefix, count_field, items_field, total, offset, limit, n, nxt,
                     by_budget, omitted, digests, extra)
    reply = head[:-2] + ",".join(entries) + "]}"
    if len(reply) > budget:                       # unreachable by construction
        raise RuntimeError("internal error: reply exceeds its budget")
    return reply


# ─── FastMCP server ───────────────────────────────────────────────────────────

mcp = FastMCP(
    "uefn-toolbelt",
    instructions=(
        "MCP server for the UEFN Toolbelt — the most comprehensive Python toolbelt "
        "for Unreal Editor for Fortnite (UEFN 40.00+, March 2026).\n\n"
        "IMPORTANT: Start the listener in UEFN first:\n"
        "  import UEFN_Toolbelt as tb; tb.run('mcp_start')\n\n"
        "The listener uses a rotating same-user bearer session and queued main-thread "
        "dispatch. Browser-originated requests are rejected.\n\n"
        "Key tools:\n"
        "  run_toolbelt_tool   — run registered tools except local-only MCP lifecycle\n"
        "  list_toolbelt_tools — list registered tools, one bounded page per call\n"
        "  get_all_actors      — list level actors, one bounded page per call\n"
        "  get_selected_actors — what the user has selected right now\n\n"
        "Verse code generation (spec-accurate):\n"
        "  verse_book_search   — search the authoritative Verse spec by keyword\n"
        "  verse_book_chapter  — fetch a full spec chapter by topic\n"
        "  verse_book_update   — git pull the latest spec from upstream\n\n"
        "IMPORTANT for Verse codegen: always call verse_book_search or verse_book_chapter\n"
        "BEFORE writing Verse code to ensure syntax is spec-accurate.\n\n"
        "Arbitrary remote Python is unavailable; use the local UEFN Python console.\n\n"
        "Unknown outcomes: a timeout, a lost connection, or an unexpected response "
        "means no reply confirmed whether a command ran. Do not automatically send "
        "a state-changing tool call again. Once the editor answers, inspect state "
        "with read tools before deciding. get_history entries carry a command name, "
        "an elapsed time, and a success flag, but no request identifier, "
        "parameters, time, or caller, so they cannot identify a specific call or "
        "show how many times it ran."
        "\n\nPaged listings: list_toolbelt_tools and get_all_actors return one page "
        "per call, at most 24,000 characters of ASCII JSON. Follow next_offset until "
        "complete is true. An entry marked omitted: true was enumerated but is too "
        "large to deliver. A listing with a duplicate tool name or actor path is "
        "rejected as malformed. If keys_digest changes between pages, or an offset is "
        "rejected as beyond the listing, the set of entries changed: restart from "
        "offset 0, at most twice, then stop and report that the listing was not "
        "stable. A listing_digest change alone means values changed between page "
        "calls; re-read any actor you rely on with get_all_actors(actor_path=...)."
    ),
)

# ─── System ───────────────────────────────────────────────────────────────────


@mcp.tool()
def ping() -> str:
    """Check if the UEFN Toolbelt listener is running and get its status."""
    return _j(_send("ping"))


@mcp.tool()
def mcp_get_log(last_n: int = 50) -> str:
    """Get the last N lines from the MCP listener's internal log ring."""
    result = _send("get_log", {"last_n": last_n})
    lines = result.get("lines", [])
    return "\n".join(lines) if lines else "(log is empty)"


# ─── Toolbelt bridge (the killer feature) ─────────────────────────────────────


@mcp.tool()
def run_toolbelt_tool(tool_name: str, kwargs: dict | None = None) -> str:
    """Run any registered UEFN Toolbelt tool by name.

    This exposes the registered Toolbelt catalogue through one command, except
    local-only MCP listener lifecycle controls. Name the tool and pass its
    arguments as a dict instead of relying on arbitrary Python.

    Args:
        tool_name: Registered tool name (e.g. 'material_apply_preset').
        kwargs:    Dict of keyword arguments for the tool (optional).

    Examples:
        run_toolbelt_tool("material_apply_preset", {"preset": "chrome"})
        run_toolbelt_tool("arena_generate", {"size": "large", "apply_team_colors": True})
        run_toolbelt_tool("scatter_hism", {"count": 200, "radius": 4000.0})
        run_toolbelt_tool("snapshot_save")
        run_toolbelt_tool("tag_add", {"key": "biome", "value": "desert"})
        run_toolbelt_tool("screenshot_focus_selection")
        run_toolbelt_tool("ref_full_report", {"scan_path": "/Game"})

    Use list_toolbelt_tools() first to discover available tool names.
    """
    result = _send(
        "run_tool",
        {"tool_name": tool_name, "kwargs": kwargs or {}},
        timeout=LONG_OPERATION_TIMEOUT,
    )
    return _j(result)


@mcp.tool()
def list_toolbelt_tools(category: str = "", offset: int = 0, limit: int = 50,
                        detail: str = "summary") -> str:
    """List registered UEFN Toolbelt tools, one bounded page per call.

    Args:
        category: Optional exact category (e.g. 'Materials', 'Procedural',
                  'MCP Bridge'). Leave empty for every category.
        offset:   Index of the first tool on this page, 0 or more. Pass the
                  previous page's next_offset.
        limit:    Most tools on this page, 1-500 (default 50). A page holds
                  fewer when the size budget ends it.
        detail:   'summary' (name, category, description, tags) or 'full'
                  (every registry field).

    Returns '// <total> tools registered', then one JSON object with total,
    offset, limit, returned, next_offset (null on the last page), complete,
    budget_limited, omitted_count, listing_digest, keys_digest, detail and
    tools. Tools are ordered by name. Pass a name to describe_toolbelt_tool()
    or run_toolbelt_tool().
    """
    _validate_text("category", category)
    offset, limit = _validate_page_args(offset, limit)
    detail = _validate_detail(detail)
    tools = _validate_listing(_send("list_tools", {"category": category}),
                              "tools", "name")
    return _page_listing(_project_tools(tools, detail), key_field="name",
                         items_field="tools", count_field="total", offset=offset,
                         limit=limit, extra=(("detail", detail),),
                         prefix_for=lambda total: f"// {total} tools registered\n")


@mcp.tool()
def describe_toolbelt_tool(tool_name: str) -> str:
    """Get the full parameter schema for a single UEFN Toolbelt tool.

    Returns the tool's name, description, category, tags, and complete parameter
    signatures (type, required, default) — everything needed to call it correctly
    without loading the full tool manifest.

    Use this before calling run_toolbelt_tool() when you need to verify parameter
    names, types, or defaults for a specific tool.

    Args:
        tool_name: Registered tool name (e.g. 'scatter_hism', 'material_apply_preset').

    Examples:
        describe_toolbelt_tool("scatter_hism")
        describe_toolbelt_tool("verse_gen_game_skeleton")
        describe_toolbelt_tool("snapshot_save")
    """
    result = _send("describe_tool", {"tool_name": tool_name})
    return _j(result)


# ─── Actors ───────────────────────────────────────────────────────────────────


@mcp.tool()
def get_all_actors(class_filter: str = "", offset: int = 0, limit: int = 50,
                   label_contains: str = "", actor_path: str = "") -> str:
    """List actors in the current UEFN level, one bounded page per call.

    Args:
        class_filter:   Optional exact class name (e.g. 'StaticMeshActor').
        offset:         Index of the first actor on this page, 0 or more. Pass
                        the previous page's next_offset.
        limit:          Most actors on this page, 1-500 (default 50). A page
                        holds fewer when the size budget ends it.
        label_contains: Optional case-insensitive substring of the actor label.
        actor_path:     Optional exact actor path.

    Returns one JSON object with count (matching actors), offset, limit,
    returned, next_offset (null on the last page), complete, budget_limited,
    omitted_count, listing_digest, keys_digest and actors. Actors are ordered
    by path. Every page call reads the whole level again.
    """
    _validate_text("class_filter", class_filter)
    _validate_text("label_contains", label_contains)
    _validate_text("actor_path", actor_path)
    offset, limit = _validate_page_args(offset, limit)
    actors = _validate_listing(_send("get_all_actors", {"class_filter": class_filter}),
                               "actors", "path")
    return _page_listing(_filter_actors(actors, label_contains, actor_path),
                         key_field="path", items_field="actors", count_field="count",
                         offset=offset, limit=limit)


@mcp.tool()
def get_selected_actors() -> str:
    """Get the actors currently selected in the UEFN viewport."""
    return _j(_send("get_selected_actors"))


@mcp.tool()
def spawn_actor(
    asset_path: str = "",
    actor_class: str = "",
    location: list[float] | None = None,
    rotation: list[float] | None = None,
) -> str:
    """Spawn an actor in the current level.

    Provide asset_path OR actor_class (not both).

    Args:
        asset_path:  Content path (e.g. '/Engine/BasicShapes/Cube').
        actor_class: Unreal class name (e.g. 'PointLight', 'CameraActor').
        location:    [x, y, z] world coordinates. Defaults to origin.
        rotation:    [pitch, yaw, roll] in degrees.
    """
    params: dict[str, Any] = {}
    if asset_path:  params["asset_path"]  = asset_path
    if actor_class: params["actor_class"] = actor_class
    if location:    params["location"]    = location
    if rotation:    params["rotation"]    = rotation
    return _j(_send("spawn_actor", params))


@mcp.tool()
def delete_actors(actor_paths: list[str]) -> str:
    """Delete actors by path name or label.

    Args:
        actor_paths: List of actor path names or labels to delete.
    """
    return _j(_send("delete_actors", {"actor_paths": actor_paths}))


@mcp.tool()
def set_actor_transform(
    actor_path: str,
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale:    list[float] | None = None,
) -> str:
    """Set an actor's transform (any combination of location, rotation, scale).

    Args:
        actor_path: Actor path name or label.
        location:   [x, y, z] world coordinates.
        rotation:   [pitch, yaw, roll] in degrees.
        scale:      [x, y, z] scale factors.
    """
    params: dict[str, Any] = {"actor_path": actor_path}
    if location: params["location"] = location
    if rotation: params["rotation"] = rotation
    if scale:    params["scale"]    = scale
    return _j(_send("set_actor_transform", params))


@mcp.tool()
def set_actor_property(actor_path: str, property_name: str, value: Any) -> str:
    """Set a single editor property on an actor.

    Args:
        actor_path:    Actor path name or label.
        property_name: Property to set (e.g. 'mobility', 'hidden_in_game').
        value:         New value (must be JSON-serializable and match the property type).
    """
    return _j(_send("set_actor_property",
                    {"actor_path": actor_path, "property_name": property_name,
                     "value": value}))


@mcp.tool()
def get_actor_properties(actor_path: str, properties: list[str]) -> str:
    """Read specific editor properties from an actor.

    Args:
        actor_path: Actor path name or label.
        properties: Property names to read (e.g. ['mobility', 'hidden_in_game']).
    """
    return _j(_send("get_actor_properties",
                    {"actor_path": actor_path, "properties": properties}))


# ─── Assets ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_assets(directory: str = "/Game/", recursive: bool = True,
                class_filter: str = "") -> str:
    """List assets in a Content Browser directory.

    Args:
        directory:    Content path (e.g. '/Game/', '/Game/Materials/').
        recursive:    Include subdirectories (default True).
        class_filter: Class name filter (e.g. 'Material', 'StaticMesh').
    """
    return _j(_send("list_assets", {"directory": directory,
                                    "recursive": recursive,
                                    "class_filter": class_filter}))


@mcp.tool()
def get_asset_info(asset_path: str) -> str:
    """Get detailed info (class, package, path) about an asset.

    Args:
        asset_path: Full asset path (e.g. '/Game/Materials/M_Base').
    """
    return _j(_send("get_asset_info", {"asset_path": asset_path}))


@mcp.tool()
def get_selected_assets() -> str:
    """Get assets currently selected in the Content Browser."""
    return _j(_send("get_selected_assets"))


@mcp.tool()
def rename_asset(old_path: str, new_path: str) -> str:
    """Rename or move an asset.

    Args:
        old_path: Current asset path.
        new_path: New destination path.
    """
    return _j(_send("rename_asset", {"old_path": old_path, "new_path": new_path}))


@mcp.tool()
def delete_asset(asset_path: str) -> str:
    """Delete an asset permanently.

    Args:
        asset_path: Full asset path to delete.
    """
    return _j(_send("delete_asset", {"asset_path": asset_path}))


@mcp.tool()
def duplicate_asset(source_path: str, dest_path: str) -> str:
    """Duplicate an asset to a new path.

    Args:
        source_path: Source asset path.
        dest_path:   Destination asset path.
    """
    return _j(_send("duplicate_asset", {"source_path": source_path,
                                        "dest_path": dest_path}))


@mcp.tool()
def does_asset_exist(asset_path: str) -> str:
    """Check if an asset exists at the given path.

    Args:
        asset_path: Asset path to check.
    """
    return _j(_send("does_asset_exist", {"asset_path": asset_path}))


@mcp.tool()
def save_asset(asset_path: str) -> str:
    """Save a modified asset to disk.

    Args:
        asset_path: Asset path to save.
    """
    return _j(_send("save_asset", {"asset_path": asset_path}))


@mcp.tool()
def import_asset(
    source_file: str,
    destination_path: str,
    replace_existing: bool = True,
    save: bool = True,
) -> str:
    """Import an external file (FBX, PNG, WAV, etc.) into the Content Browser.

    Args:
        source_file:      Absolute path to the file on disk.
        destination_path: Content Browser destination (e.g. '/Game/Imports').
        replace_existing: Overwrite if an asset at that path already exists.
        save:             Save the imported asset immediately.
    """
    return _j(_send("import_asset", {
        "source_file":       source_file,
        "destination_path":  destination_path,
        "replace_existing":  replace_existing,
        "save":              save,
    }))


@mcp.tool()
def search_assets(class_name: str = "", directory: str = "/Game/",
                  recursive: bool = True) -> str:
    """Search for assets using the Asset Registry.

    Args:
        class_name: Class name filter (e.g. 'Material', 'Texture2D', 'StaticMesh').
        directory:  Directory to search.
        recursive:  Include subdirectories.
    """
    return _j(_send("search_assets", {"class_name": class_name,
                                      "directory": directory,
                                      "recursive": recursive}))


# ─── Materials ────────────────────────────────────────────────────────────────


@mcp.tool()
def create_material_instance(
    parent_path: str,
    instance_name: str,
    destination: str = "/Game/Materials",
    scalar_params: dict | None = None,
    vector_params: dict | None = None,
    texture_params: dict | None = None,
) -> str:
    """Create a new MaterialInstanceConstant from a parent material.

    Args:
        parent_path:    Content path to the parent Material (e.g. '/Game/Materials/M_Master').
        instance_name:  Name for the new MI asset (e.g. 'MI_TeamRed').
        destination:    Content Browser destination folder.
        scalar_params:  {param_name: float} — e.g. {"Roughness": 0.2, "Metallic": 0.9}
        vector_params:  {param_name: [r,g,b,a]} — e.g. {"BaseColor": [1.0, 0.1, 0.1, 1.0]}
        texture_params: {param_name: asset_path} — e.g. {"DiffuseTex": "/Game/T_Rock"}
    """
    return _j(_send("create_material_instance", {
        "parent_path":    parent_path,
        "instance_name":  instance_name,
        "destination":    destination,
        "scalar_params":  scalar_params or {},
        "vector_params":  vector_params or {},
        "texture_params": texture_params or {},
    }))


@mcp.tool()
def batch_exec(commands: list[dict]) -> str:
    """Execute multiple bridge commands in a single UEFN editor tick.

    Faster than sending commands one-by-one for multi-step sequences.
    Each entry: {"command": "name", "params": {...}}

    Example:
        batch_exec([
            {"command": "run_tool", "params": {"tool_name": "snapshot_save"}},
            {"command": "run_tool", "params": {"tool_name": "bulk_align",
                                               "kwargs": {"axis": "Z"}}},
            {"command": "save_current_level", "params": {}},
        ])
    """
    return _j(_send("batch_exec", {"commands": commands}, timeout=120.0))


@mcp.tool()
def undo() -> str:
    """Undo the last action in the UEFN editor."""
    return _j(_send("undo"))


@mcp.tool()
def redo() -> str:
    """Redo the last undone action in the UEFN editor."""
    return _j(_send("redo"))


@mcp.tool()
def get_history(tail: int = 30) -> str:
    """Get recent command history with per-command timing (elapsed_ms)."""
    return _j(_send("history", {"tail": tail}))


# ─── Level ────────────────────────────────────────────────────────────────────


@mcp.tool()
def save_current_level() -> str:
    """Save the current level to disk."""
    return _j(_send("save_current_level"))


@mcp.tool()
def get_level_info() -> str:
    """Get info about the current level: world name and actor count."""
    return _j(_send("get_level_info"))


# ─── Viewport ─────────────────────────────────────────────────────────────────


@mcp.tool()
def get_viewport_camera() -> str:
    """Get the current editor viewport camera location and rotation."""
    return _j(_send("get_viewport_camera"))


@mcp.tool()
def set_viewport_camera(
    location: list[float] | None = None,
    rotation: list[float] | None = None,
) -> str:
    """Move the editor viewport camera.

    Args:
        location: [x, y, z] world coordinates.
        rotation: [pitch, yaw, roll] in degrees.
    """
    params: dict[str, Any] = {}
    if location: params["location"] = location
    if rotation: params["rotation"] = rotation
    return _j(_send("set_viewport_camera", params))


# ─── Verse Book (spec-aware code generation) ──────────────────────────────────


def _verse_book_missing() -> str:
    return (
        "verse-book not found at expected path.\n"
        "Fix: cd to the project root and run:\n"
        "  git clone https://github.com/verselang/book.git verse-book"
    )


@mcp.tool()
def verse_book_search(query: str, context_lines: int = 8) -> str:
    """Search the authoritative Verse language spec for a keyword or concept.

    Always call this before writing Verse code to verify syntax.
    Returns matching sections with surrounding context from all spec chapters.

    Args:
        query:         Keyword, specifier, or concept to look up
                       (e.g. 'suspends', 'editable', 'creative_device', 'race',
                       'Subscribe', 'map', 'option', 'interface').
        context_lines: Lines of context around each match (default 8).

    Examples:
        verse_book_search("suspends")          # effect specifier syntax
        verse_book_search("@editable")         # device property declarations
        verse_book_search("race block")        # concurrency race pattern
        verse_book_search("Subscribe")         # event subscription pattern
    """
    if not os.path.isdir(VERSE_BOOK_PATH):
        return _verse_book_missing()

    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for fname in sorted(os.listdir(VERSE_BOOK_PATH)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(VERSE_BOOK_PATH, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            continue

        i = 0
        while i < len(lines):
            if pattern.search(lines[i]):
                start = max(0, i - context_lines)
                end   = min(len(lines), i + context_lines + 1)
                snippet = "".join(lines[start:end])
                results.append(f"### {fname} — line {i + 1}\n{snippet}")
                i = end  # skip past this match block
            else:
                i += 1

    if not results:
        return f"No matches for '{query}' in the Verse spec."

    capped = results[:12]
    header = f"// {len(results)} match(es) for '{query}' — showing {len(capped)}\n\n"
    return header + "\n---\n".join(capped)


@mcp.tool()
def verse_book_chapter(topic: str) -> str:
    """Fetch a complete chapter from the Verse language spec by topic.

    Use when you need full coverage of a language area before generating code.
    Chapters are pulled from the live verse-book clone — always current.

    Args:
        topic: Topic name. Supported values:
               overview, expressions, primitives, containers, operators,
               mutability, functions, control, failure, structs, enums,
               classes, interfaces, types, access, effects, concurrency,
               async, live_variables, modules, persistable, evolution,
               syntax, index.

    Examples:
        verse_book_chapter("concurrency")   # async/suspends/race/sync
        verse_book_chapter("classes")       # class/interface/inheritance
        verse_book_chapter("failure")       # failable expressions, decides
        verse_book_chapter("effects")       # effect specifiers: computes/reads/writes
    """
    if not os.path.isdir(VERSE_BOOK_PATH):
        return _verse_book_missing()

    topic_key = topic.lower().replace(" ", "_").replace("-", "_")
    fname = _VERSE_CHAPTERS.get(topic_key)

    if fname is None:
        # Fuzzy fallback — partial match
        for key, f in _VERSE_CHAPTERS.items():
            if topic_key in key or key in topic_key:
                fname = f
                break

    if fname is None:
        available = sorted(set(_VERSE_CHAPTERS.keys()))
        return f"Unknown topic '{topic}'.\nAvailable topics: {available}"

    fpath = os.path.join(VERSE_BOOK_PATH, fname)
    try:
        with open(fpath, encoding="utf-8") as f:
            content = f.read()
        return f"// {fname}  ({len(content.splitlines())} lines)\n\n{content}"
    except Exception as e:
        return f"Error reading {fname}: {e}"


@mcp.tool()
def verse_book_update() -> str:
    """Pull the latest Verse spec from upstream (git pull on verse-book/).

    Run this when Epic releases Verse language updates to stay current.
    Returns the git output showing what changed.
    """
    book_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verse-book")
    if not os.path.isdir(os.path.join(book_root, ".git")):
        return _verse_book_missing()
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=book_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        return f"// git pull — verse-book\n{output}"
    except subprocess.TimeoutExpired:
        return "git pull timed out after 30s."
    except Exception as e:
        return f"git pull failed: {e}"


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Allow --port override: python mcp_server.py --port 8766
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--port" and i < len(sys.argv) - 1:
            candidate_port = int(sys.argv[i + 1])
            if not (1 <= candidate_port <= 65535):
                raise ValueError(f"Port {candidate_port} out of range")
            _PORT_OVERRIDE = candidate_port

    mcp.run()
