# WO-002 — Epic Toolset Integration Truth

STATUS: ISSUED

AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION

OWNER: Ocean Bennett

PRIORITY: P1

BASELINE: `098b38c669dd330cd059ea18dea52cc4e7eaefe2`

## Pre-issuance basis

This proposal is based on commit
`098b38c669dd330cd059ea18dea52cc4e7eaefe2`, successful CI workflow
`32925047925`, and successful required job `98046156859` (`Lint, types,
tests`). Recording that evidence does not issue this Work Order or authorize an
implementation session.

## Session A authorization basis

The issued Work Order was committed as
`d87572e2a272c98f8dd634cfe17ff8a130446a7b`; successful CI workflow
`32931353926` included successful required job `98064090312` (`Lint, types,
tests`). Under the sole current gate in root `WORKORDER.md`, Session A is
authorized for implementation. Session B remains unauthorized.

## Problem and accepted evidence

Toolbelt reports an in-process Epic toolset registration, but the accepted
UEFN 42.00 audit found that the external official server did not list,
describe, or call it. Internally, `toolbelt_list_tools` and
`toolbelt_run_tool` worked, while `toolbelt_describe_tool` expected a nested
`tools` list even though the registry returns a flat manifest keyed by tool
name.

Epic's installed Valkyrie registration source also says the creator-facing
surface is selected separately by `UE::ValkyrieToolset::ToolsetPolicy`.
Submitting a Python toolset class to the in-editor registry is therefore not
proof that the official MCP creator surface exposes it.

## Decision locks — integration truth model

The implementation and its tests must keep these states independent:

1. **Registration attempted** — whether
   `register_toolset_class()` was invoked, with the exact outcome recorded as
   not attempted, returned without exception, raised, or adopted from the
   current editor session.
2. **In-process registry confirmation** — `confirmed` only after a positive
   registry query for the live class; otherwise `unknown`. UEFN 42.00's
   observed false query results are not reliable negative evidence.
3. **Internal list contract** — `not_tested`, `passed`, or `failed` for a direct
   in-process `toolbelt_list_tools` call.
4. **Internal describe contract** — `not_tested`, `passed`, or `failed` for a
   direct in-process `toolbelt_describe_tool` call.
5. **Internal run contract** — `not_tested`, `passed`, or `failed` for a direct
   in-process `toolbelt_run_tool` call.
6. **Externally listable** — `passed` only when the official external
   `list_toolsets()` result contains the exact Toolbelt toolset name; otherwise
   `failed` after a completed proof or `not_tested` before one.
7. **Externally describable** — `passed` only when official external
   `describe_toolset()` succeeds for that exact name and exposes the expected
   three meta-tool signatures; otherwise `failed` or `not_tested`.
8. **Externally callable** — `passed` only when official external `call_tool()`
   successfully invokes all three Toolbelt meta-tools and their decoded results
   satisfy the internal contracts; otherwise `failed` or `not_tested`.

A non-raising `register_toolset_class()` call, `_REGISTERED`, the cross-reload
class stash, or a successful direct in-process meta-tool call never proves any
external state. Externally listable, describable, and callable are separate
facts; none may imply another. Missing evidence must remain `not_tested`, not be
inferred as success or failure.

Every registration and status branch must return a stable schema that preserves
the distinctions above. Compatibility fields such as `registered`,
`registration_confirmed`, or `tools_exposed` must not describe external
availability. Narrow logs, tool descriptions, and dashboard copy must follow
the same truth model.

## Locked internal meta-tool contracts

### `toolbelt_list_tools(category: string)`

- An empty category lists all registered Toolbelt tools; a non-empty category
  applies that exact registry filter.
- Successful decoded JSON contains `count`, `categories`, and `tools`.
- `count` equals the number of returned `tools` entries.
- Each returned tool contains `name`, `category`, and `description`.

### `toolbelt_describe_tool(tool_name: string)`

- It consumes the registry's actual flat manifest and returns
  `manifest[tool_name]`.
- A successful decoded entry preserves the registry fields, including `name`,
  `category`, `description`, `tags`, `parameters`, and optional `example`
  metadata.
- An unknown name fails explicitly and reports that the requested tool is
  unknown; it must not return an empty success value.

### `toolbelt_run_tool(tool_name: string, arguments_json: string)`

- `arguments_json` must decode to a JSON object; an empty string means an empty
  object.
- Successful decoded JSON contains `tool` and `result`.
- Invalid JSON, a non-object value, an unknown tool, an exception, or a
  structured Toolbelt refusal fails explicitly and must not be returned as a
  successful execution.

## Session A — internal contract and truth correction

Session A is authorized for implementation under the current root
`WORKORDER.md` gate. This authorization does not extend to Session B.

### Scope

Change only the runtime, narrow user-facing status surfaces, tests, and directly
generated/static artifacts required to:

- repair `toolbelt_describe_tool` against the flat manifest;
- implement the separated truth states and a consistent registration/status
  result schema;
- lock the positive and failure paths of all three internal meta-tools with
  non-vacuous tests;
- ensure every external state remains `not_tested` throughout Session A and is
  never inferred from internal success;
- replace claims that registration exposes Toolbelt to "any MCP client" with
  wording that distinguishes an attempted or confirmed in-process registration
  from externally proven official-MCP exposure;
- correct the directly related `epic_toolset.py` log/docstring text,
  `epic_mcp_tools.py` descriptions and result contracts, and dashboard status,
  button, tooltip, and failure copy;
- preserve Quirk #36 manual recovery; and
- preserve every accepted WO-001 control-plane guarantee.

The anticipated implementation surfaces are:

- `Content/Python/UEFN_Toolbelt/epic_toolset.py`;
- `Content/Python/UEFN_Toolbelt/tools/epic_mcp_tools.py`;
- `Content/Python/UEFN_Toolbelt/dashboard_pyside6.py`;
- `tests/test_epic_toolset.py`;
- existing smoke, security, manifest, integrity, and drift coverage only where
  directly required by those changes.

### Static acceptance evidence

- Unit tests exercise every registration/status branch and require the same
  truth-state schema.
- Unit tests prove a non-raising registration attempt, `_REGISTERED`, and the
  reload stash do not set an external state to `passed`.
- Unit tests prove list-all, category filtering, count agreement, known and
  unknown describe behavior, valid run behavior, invalid JSON, non-object JSON,
  unknown tools, raised exceptions, and structured Toolbelt refusals.
- Existing MCP security tests continue to prove authentication, queue-only
  main-thread dispatch, raw-Python rejection, local-only lifecycle controls,
  bounded request handling, and fail-closed startup.
- Ruff, mypy, focused tests, full pytest, drift check, API-manifest check, and
  diff hygiene pass.

### Live TOOL_TEST acceptance evidence

Because Session A changes deployed Python and PySide6 status copy:

1. Deploy only to disposable `TOOL_TEST` and perform a full UEFN restart.
2. If Quirk #36 suppresses startup, recover with:

   ```python
   import UEFN_Toolbelt as tb; tb.register()
   ```

3. Verify 362 tools and 55 categories are loaded.
4. Invoke the generated class directly and verify:
   - `toolbelt_list_tools("MCP Bridge")` returns a correct filtered payload;
   - `toolbelt_describe_tool("epic_mcp_status")` returns its flat manifest
     entry;
   - `toolbelt_run_tool("epic_mcp_status", "{}")` returns its decoded Toolbelt
     result.
5. Exercise the locked failure paths without mutating the level.
6. Open the dashboard and verify it distinguishes internal state from external
   official-MCP proof and never claims externally exposed tools.
7. Confirm all three external states remain `not_tested`.

Do not launch Fortnite or mutate/save the `TOOL_TEST` level. Keep the custom
Toolbelt bridge stopped; its handoff must be absent and ports 8765–8770 closed
before and after live verification.

### Session A stop boundary

Leave the complete implementation uncommitted and unstaged for fresh
independent architect review. Commit and push require separate owner gates.
Required CI must succeed for the accepted Session A commit before any owner
gate for Session B. Session B remains unauthorized throughout Session A.

## Session B — external official-MCP proof

Session B is not authorized.

### Scope

- Read the current installed Epic ToolsetRegistry and Valkyrie registration
  source and inspect the `ToolsetPolicy` exposure boundary without modifying
  Epic's installation or bypassing policy.
- Use only the official UEFN loopback MCP endpoint in disposable `TOOL_TEST`.
- Preserve sanitized raw request/result or exact failure-envelope evidence for:
  - `list_toolsets()` containing or omitting the exact `UEFN_Toolbelt` name;
  - `describe_toolset()` against that exact name;
  - `call_tool()` invoking `toolbelt_list_tools` with category `MCP Bridge`;
  - `call_tool()` invoking `toolbelt_describe_tool` for `epic_mcp_status`;
  - `call_tool()` invoking `toolbelt_run_tool` for `epic_mcp_status` with an
    empty JSON object;
  - Toolbelt remaining directly callable throughout; and
  - Quirk #36 recovery when startup registration is suppressed.
- Record the official protocol, exact toolset name, argument envelopes, decoded
  Toolbelt payloads, timestamps, and cleanup state without personal email,
  session identifiers, credentials, or transient secrets.

### Decision rules and acceptance evidence

- `externally_listable=passed` requires the exact name in the completed
  `list_toolsets()` result.
- `externally_describable=passed` requires a successful description of exactly
  the three expected meta-tool signatures.
- `externally_callable=passed` requires all three official `call_tool()` probes
  to succeed and satisfy their locked internal contracts.
- A result for one external state cannot satisfy another.
- Each external state records `passed`, `failed`, or `not_tested` plus the
  corresponding sanitized evidence or exact reason.
- An honest negative result is an acceptable terminal Session B outcome. A
  failure remains failed or unavailable; it must not trigger advertising,
  speculative success, retries that mask the first result, Epic-installation
  changes, or a policy bypass.
- Toolbelt's internal list, describe, and run contracts must remain callable
  before, during, and after the official probes.
- Static checks and all Session A regression tests remain green.

### Safety and cleanup

- Do not launch Fortnite, start a play session, mutate or save the `TOOL_TEST`
  level, or create a project fixture.
- Do not start the custom Toolbelt HTTP bridge or weaken any WO-001 control.
- Record the initial UEFN and official-server state and restore it afterward.
- Remove temporary client configuration and evidence artifacts that are not
  intentionally sanitized repository evidence.
- Confirm no custom bridge handoff exists, ports 8765–8770 are closed, and no
  Toolbelt listener or official test client remains running.

### Session B stop boundary

Leave any bounded repository evidence or truth-surface correction uncommitted
and unstaged for fresh independent architect review. A successful external proof
does not itself authorize advertising, a commit, push, Work Order completion,
tag, GitHub Release, repository metadata, or social publication.

## Exclusions and deferred work

- No custom-bridge security redesign or weakening of WO-001.
- No broad official-MCP documentation convergence; that remains WO-003.
- No modal observability, coverage-source rewrite, benchmark, or public MCP
  explainer; those remain WO-004 through WO-007.
- No tool/category count or version change.
- No tag, GitHub Release, repository-description change, or social action.

## Work Order-wide authority boundaries

- Session A and Session B each require a separate explicit owner authorization
  in root `WORKORDER.md`.
- Implementation, independent review, commit, push, CI recording, Work Order
  completion, tag, GitHub Release, repository metadata, and social publication
  are separate gates. Authorization for one never implies another.
- WO-003 and every later Work Order remain unauthorized.
- The frozen WO-001–WO-007 release train and repository version 2.4.1 remain
  unchanged.

NEXT GATE: fresh independent architect review of the complete uncommitted
Session A implementation. Session B remains unauthorized.
