# UEFN Toolbelt — MCP Commands, Patterns & Key Files

## Toolbelt custom bridge — commands (from Claude Code → UEFN)

These commands belong to **Toolbelt's custom bridge**: Toolbelt's own authenticated,
same-user loopback HTTP listener. This is not Epic's official UEFN MCP server, and
Toolbelt is not reachable through that server — WO-002 recorded the external
result as `failed`, bounded by `UE::ValkyrieToolset::ToolsetPolicy`.

When the listener is running, an authenticated client can call these directly:

| Command | Params | What it does |
|---|---|---|
| `ping` | — | Health check + command list |
| `get_log` | `last_n=50` | Return last N lines from the MCP command log ring |
| `run_tool` | `tool_name`, `kwargs={}` | Run registered tools; `mcp_start/stop/restart` remain local-only |
| `list_tools` | `category=""` | List all registered tools |
| `describe_tool` | `tool_name` | Full manifest entry for one tool (name, description, parameters, tags) |
| `batch_exec` | `commands=[{command, params}]` | Multiple commands in one tick |
| `undo` | — | Undo last action |
| `redo` | — | Redo last undone action |
| `history` | `tail=30` | Recent command history with timing |
| `get_all_actors` | `class_filter=""` | Snapshot entire level |
| `get_selected_actors` | — | Currently selected viewport actors |
| `spawn_actor` | `asset_path`, `location`, `rotation`, `label` | Spawn actor |
| `delete_actors` | `actor_paths=[...]` | Delete by path or label |
| `set_actor_transform` | `actor_path`, `location`, `rotation`, `scale` | Move/rotate/scale |
| `set_actor_property` | `actor_path`, `property_name`, `value` | Set a single editor property on an actor |
| `get_actor_properties` | `actor_path`, `properties=[...]` | Read editor properties |
| `list_assets` | `directory`, `recursive`, `class_filter` | List Content Browser assets |
| `get_asset_info` | `asset_path` | Asset metadata |
| `get_selected_assets` | — | Currently selected Content Browser assets |
| `rename_asset` | `old_path`, `new_path` | Rename/move |
| `duplicate_asset` | `source_path`, `dest_path` | Duplicate |
| `delete_asset` | `asset_path` | Delete |
| `does_asset_exist` | `asset_path` | Check if an asset exists |
| `save_asset` | `asset_path` | Save |
| `import_asset` | `source_file`, `destination_path`, `replace_existing=True` | Import external file (FBX, PNG, etc.) into Content Browser |
| `search_assets` | `class_name`, `directory` | Asset Registry search |
| `save_current_level` | — | Save level |
| `get_level_info` | — | World name + actor count |
| `get_viewport_camera` | — | Camera loc + rot |
| `set_viewport_camera` | `location`, `rotation` | Move viewport camera |
| `create_material_instance` | `parent_path`, `instance_name`, `destination`, `scalar_params`, `vector_params` | Create MI |

---

## Paged MCP tool listings (`mcp_server.py`)

Through `mcp_server.py`, the MCP tools `list_toolbelt_tools` and `get_all_actors`
return one bounded page per call. The bridge commands `list_tools` and
`get_all_actors` in the table above, and `client.py`, still return complete lists.

- **Size.** Each reply is at most 24,000 characters, counted as code points of the
  returned text. Replies are ASCII-only JSON, so that is also their UTF-8 byte
  count. It is not a token count, and the MCP transport adds its own framing, so
  no particular client output limit is promised.
- **Paging.** Pass `offset` (0 or more) and `limit` (1–500, default 50) and follow
  `next_offset` until `complete` is true. A page ends before `limit` when the size
  budget ends it (`budget_limited`).
- **Order.** Tools are ordered by name and actors by path, compared by code point.
  Keys must be unique: a bridge listing with a duplicate tool name or actor path
  is rejected as malformed, and no page is returned.
- **Oversized entries.** An entry over 20,000 characters is replaced by a
  placeholder with `omitted: true`, its key (or `key_sha256` when the key itself is
  very long), `omitted_chars` and `item_sha256`. It is still enumerated and
  counted, and `omitted_count` reports the placeholders on each page. `complete`
  means every matching entry was enumerated, not that every entry was delivered
  in full. The full entry is available through `client.py` or the bridge command,
  not through these MCP tools.
- **Hashes.** Every hash is written `sha256:` followed by 64 lowercase hex digits,
  over ASCII text produced by Python's `json.dumps` with `ensure_ascii=True`:
  - `key_sha256` hashes the key's JSON string literal, quotes included
    (`json.dumps(key, ensure_ascii=True)`);
  - `item_sha256` hashes the entry's canonical form
    (`json.dumps(entry, separators=(",", ":"), ensure_ascii=True, sort_keys=True)`),
    for the entry as received at the requested `detail`;
  - `listing_digest` hashes the canonical form of the complete ordered listing;
  - `keys_digest` hashes the canonical form of the ordered list of keys.

  Other JSON libraries may format numbers differently, so recomputing a hash
  outside Python's `json` may not match.
- **Non-finite numbers.** As before this change, a NaN or infinite value, for
  example in an actor coordinate, is written as `NaN`, `Infinity` or
  `-Infinity`. That is Python's `json` default. Strict JSON parsers may reject
  such a reply.
- **Changes during a walk.** `keys_digest` covers the ordered keys, and
  `listing_digest` the delivered entries, at the requested `detail` and filters.
  In normal use, if `keys_digest` changes, or an offset is rejected as beyond the
  listing, restart from offset 0, at most twice, then report that the listing was
  not stable. A `listing_digest` change alone means values changed between page
  calls; because keys are unique, every entry is still enumerated exactly once,
  but pages are separate reads, not one snapshot.
- **Arguments.** `list_toolbelt_tools` takes `category` (exact) and `detail`
  (`"summary"`: name, category, description and tags; or `"full"`).
  `get_all_actors` takes `class_filter` (exact class), `label_contains`
  (case-insensitive) and `actor_path` (exact). Filters are applied before paging
  and are not echoed. The server rejects invalid values before any bridge
  request. An MCP SDK validates arguments first and may convert some values: the
  Python SDK releases checked (1.27.1 and 1.27.2) turned `true` into 1 and `"5"`
  into 5.
- **Cost.** Every page call reads the complete listing from the editor again. On a
  very large level, each page costs editor main-thread time, and a level whose
  complete listing cannot be produced within the request timeout is not helped
  by paging.

---

## External HTTP Client (no MCP required)

`client.py` at the project root gives trusted same-user Python automation
authenticated access to UEFN through **Toolbelt's custom bridge**. It reads the
rotating session handoff automatically:

```python
from client import ToolbeltClient

ue = ToolbeltClient()               # loads Saved/UEFN_Toolbelt/mcp_session.json
ue.ping()
ue.run_tool("material_apply_preset", preset="chrome")
ue.batch([
    {"command": "run_tool", "params": {"tool_name": "snapshot_save"}},
    {"command": "run_tool", "params": {"tool_name": "scatter_hism",
                                       "kwargs": {"count": 200, "radius": 3000}}},
])
```

Unauthenticated raw HTTP, browser origins, CORS preflight, non-loopback hosts,
and requests without the current bearer session are rejected before body
parsing. The handoff is same-user privileged material, not a sandbox boundary.
Arbitrary remote Python is unavailable; use registered commands or UEFN's local
Python console. Listener lifecycle and the self-managing integration suite are
local-only.

If Epic's **UEFN MCP Toolsets** beta is enabled and the listener command says
Toolbelt is not registered, Quirk #36 suppressed `init_unreal.py`. Recover once
for the current editor session before starting the listener:

```python
import UEFN_Toolbelt as tb; tb.register(); tb.run("mcp_start")
```

### Transport and outcomes

Both `client.py` and `mcp_server.py` open every bridge request directly to the
endpoint validated from the session handoff (`127.0.0.1` and its port) through
a per-request opener that ignores environment and system HTTP proxy settings
and follows no redirect. No global opener is installed and no environment
variable is changed. A setup that reached the bridge only through a proxy stops
working.

`mcp_server.py` uses an explicit `UEFN_MCP_PORT` instead of the handoff's port.
Set it only to the port the listener actually bound; `.mcp.json.template` sets
none.

Each call makes exactly one connection attempt, and none when the handoff is
missing or invalid. Nothing is retried, and `connect()` sends one `ping`.

| What happened | What it establishes | `client.py` | `mcp_server.py` |
|---|---|---|---|
| Handoff missing, unreadable, or invalid | No request was sent | `AuthenticationError` | `ConnectionError` |
| Connection refused | No request reached a listener | `NotConnected` | `ConnectionError` |
| A timeout - `TimeoutError` or `socket.timeout`, raised directly or wrapped in `URLError` | Unknown outcome | `CommandTimeout` | `TimeoutError` |
| One of the bridge's exact pre-queue rejection bodies | Rejected before queueing | `AuthenticationError` for `401`, otherwise `ToolbeltError` | `PermissionError` for `401`, otherwise `RuntimeError` |
| The bridge's exact `504` deadline body for the command sent | Unknown outcome | `CommandTimeout` | `TimeoutError` |
| Any other status that is not `200`, including redirects and anything a proxy or another server could produce | Unknown outcome | `OutcomeUnknown` | `RuntimeError` |
| `200` with `success: true` | The handler returned | the result | the result |
| `200` with exactly the stop-drain body | Stopped before dispatch | `ToolbeltError` | `RuntimeError` |
| Any other `200` with `success: false` | A reported failure; it may have run partway | `ToolbeltError` | `RuntimeError` |
| A lost or reset connection, a truncated body, or a `200` that is not the bridge's result format | Unknown outcome | `OutcomeUnknown` | `ConnectionError` for a wrapped transport error, otherwise `RuntimeError` |

One missing-handoff case is local configuration rather than the listener.
When `LOCALAPPDATA` is unset, the clients cannot locate the session handoff
(`Saved/UEFN_Toolbelt/mcp_session.json`, described above and in `SECURITY.md`)
before any networking starts, so restarting the listener alone does not repair
it. Its message therefore carries no restart step.

`OutcomeUnknown` subclasses `ToolbeltError`, and `CommandTimeout` subclasses
`OutcomeUnknown`. An unknown outcome means no reply confirmed whether the
command ran: it may not have run, may still be queued or running, or may have
completed. Do not send a command that changes editor or project state again
until that state has been checked; a check sent while the editor is not
processing the bridge queue can also go unanswered. `history` entries carry a
command name, an elapsed time, and a success flag, but no request identity, so
they cannot show how many times a call ran. The clients do not diagnose why a
reply is missing.

**Compatibility changes** (WO-004 Session B):

- A bridge `504`: `client.py` raises `CommandTimeout` (was `ToolbeltError`), and
  `mcp_server.py` raises `TimeoutError` (was `RuntimeError`).
- A timeout wrapped in `URLError`: `CommandTimeout` (was `NotConnected`) and
  `TimeoutError` (was `ConnectionError`).
- Any other `URLError` that is not a refusal: `client.py` raises
  `OutcomeUnknown` (was `NotConnected`). A refusal is recognized by the
  exception type only, never by its message text.
- A lost connection, an unreadable body, or an error status without an exact
  bridge body: `client.py` raises `OutcomeUnknown` (was `ToolbeltError`). An
  unmatched `401` raises `OutcomeUnknown` and `RuntimeError` (was
  `AuthenticationError` and `PermissionError`).
- A `200` body that is not a JSON object (previously an `AttributeError`) and
  a truthy non-boolean `success` (previously returned as a result) are now
  unknown outcomes, and so is every 2xx other than `200`. Such a 2xx was
  previously returned as a result only when its body carried a truthy
  `success`.
- Bridge requests no longer use HTTP proxies or follow redirects.
- Message text changed for timeouts, lost connections, rejections, and
  reported failures.

**Limitations.** When the bridge's deadline loop runs, it bounds the wait for
a reply at 30 seconds (`HTTP_TIMEOUT_SEC`), so an operation longer than that is
reported as an unknown outcome even if it later succeeds, and a longer client
timeout is not reached on that path. Whether that loop completes while the
editor is not servicing ticks has not been shown, so the client's own timeout
may arrive instead; both are unknown outcomes. A timeout is not a cancellation: a
`504` neither removes nor cancels the queued command, and its late result is
discarded. The listener handles one request at a time,
so a follow-up check can wait behind a pending one. No request identifier
reaches the client, so a late execution cannot be matched to the call that
submitted it.

---

## Common Patterns Claude Should Know

### Safe destructive ops — always dry_run first
```python
tb.run("ref_delete_orphans", scan_path="", dry_run=True)   # preview
tb.run("ref_delete_orphans", scan_path="", dry_run=False)  # execute
```

### Undo safety — all actor ops are wrapped in transactions
```python
# If something goes wrong after a bulk op:
# UEFN menu: Edit → Undo (or Ctrl+Z)
# Via MCP: ue.run("undo")
```

### Checking what's selected
```python
# Via tb.run (inside UEFN):
tb.run("verse_list_devices")   # lists all devices (works regardless of selection)

# Via MCP (from Claude Code):
# get_selected_actors() → snapshot of viewport selection
# get_selected_assets() → Content Browser selection
```

### Material instance — always call update after params
```python
# This is handled automatically by toolbelt tools
# For local UEFN-console material scripting, remember:
# MaterialEditingLibrary.update_material_instance(mi)  ← never skip
```

### Large batch ops — use progress-aware tools
```python
# For 500+ actors, prefer HISM scatter over props
tb.run("scatter_hism", ...)    # one draw call
# not
tb.run("scatter_props", ...)   # N actors
```

---

## Key File Locations

| File | Purpose |
|---|---|
| `init_unreal.py` (repo root — copy to `Content/Python/`) | Generic submodule loader, auto-runs on editor start. Scans `Content/Python/` for packages with `register()` and calls them. Not Toolbelt-specific — do not overwrite an existing `init_unreal.py`; merge only the discovery loop instead. |
| `Content/Python/UEFN_Toolbelt/__init__.py` | Package root. Contains `__version__`, `register()`, `load_custom_plugins()`, `run()`, `config`. **`__version__`** is the single source of truth — bump it here when shipping a release. Propagates to audit logs, reload messages, and manifests automatically. |
| `Content/Python/UEFN_Toolbelt/core/config.py` | Persistent config system. `get_config().get/set/reset()`. Reads/writes `Saved/UEFN_Toolbelt/config.json` — survives `install.py` updates. |
| `Content/Python/UEFN_Toolbelt/tools/` | All tool modules |
| `Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py` | HTTP listener (runs inside UEFN) |
| `mcp_server.py` | External FastMCP stdio server for MCP clients such as Claude Code; host integration is untested since the WO-001/WO-004 hardening |
| `client.py` | Stdlib-only HTTP client for non-MCP external scripts |
| `install.py` | One-command community installer — copies Toolbelt into any UEFN project, handles `init_unreal.py` safely |
| `deploy.bat` | Dev workflow tool — deploy + PySide6 check + prints hot-reload command. Use this for active development. |
| `prepare_launch.bat` | Host-side pre-validation helper — stashes every project `.py`, writes a recoverable manifest, and verifies zero remain before Launch Session, Push Changes, or publishing. Run Python audits first. |
| `restore_after_launch.bat` | Restores the exact manifest after remote validation; collision-checks instead of overwriting files created while the stash was active. |
| `.mcp.json` | Your local MCP client config — not tracked (gitignored). Copy `.mcp.json.template` and set the absolute path to `mcp_server.py`; never commit it. |
| `docs/uefn_python_capabilities.md` | Full UEFN Python API surface reference |
| Epic UE5.7 Python API (https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/?application_version=5.7) | **Primary API reference** — check here first for correct class/method names. UEFN omits some standard UE5 APIs: `KismetMaterialLibrary` is absent, `/FortniteGame/` asset paths are blocked, some editor factories may not be exposed. |
| Epic UE4.27 Python API (https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/?application_version=4.27) | **Last resort only — UEFN is NOT UE4.27.** Some classes were more thoroughly documented in 4.27 before Epic restructured their docs. If a class or method is absent from the 5.7 reference, try 4.27 for an older doc entry. Always cross-check against `tb.run("api_inspect", name="ClassName")` — that queries the live UEFN runtime, which is authoritative. |
| `Content/Python/UEFN_Toolbelt/core/theme.py` | **Single source of truth for all UI colors.** Edit `PALETTE` here to change the platform's appearance everywhere. |
| `Content/Python/UEFN_Toolbelt/core/base_window.py` | `ToolbeltWindow` base class — subclass instead of `QMainWindow` for any tool window. Auto-applies theme + Slate tick. |
| `docs/ui_style_guide.md` | **UI Style Guide — MANDATORY** for all windowed tools and plugins. Color palette, `ToolbeltWindow` API, widget recipes. Read this before writing any PySide6 UI. |
| `docs/UEFN_QUIRKS.md` | **Critical reading for tool authors** — non-obvious UEFN Python behaviors. Key quirks: #2 Main Thread Lock, #19 V2 Device Property Wall, #23 `/Game/` mount + disk path detection, #31 PySide6 window crash pattern, #32 pak-heavy Asset Registry scans, #37 `TextRenderActor` publish blockers, #41 keyword-only `unreal.*` structs, and #42 project-Python remote validation. |
| `docs/CHANGELOG.md` | Version history — all notable changes by release. |
| `docs/plugin_dev_guide.md` | Plugin authorship guide — security model, audit format, version stamp |
| `tests/smoke_test.py` | 5-layer health check — run `tb.smoke_test()` |
| `TOOL_STATUS.md` | **Authoritative test coverage doc.** Tool count, per-tool verification status (🟡/🟠/🔴), integration test batch history, disabled tools, and roadmap. Always update when adding tools. AI agents should check this before assuming a tool is tested. |
| `ARCHITECTURE.md` | **System design reference.** Directory map, subsystem descriptions, data flow, execution constraints, and extension points. Read before making structural changes or adding new subsystems. |
| `Saved/UEFN_Toolbelt/plugin_audit.json` | Security audit of all loaded custom plugins — includes `toolbelt_version`, SHA-256 hashes, timestamps |
| `Saved/UEFN_Toolbelt/` | All tool outputs (screenshots, snapshots, stubs, exports) |
