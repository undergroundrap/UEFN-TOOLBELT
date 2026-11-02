# Epic's Official UEFN MCP and UEFN Toolbelt

This page explains what Epic's official UEFN MCP does, what Toolbelt still
adds, how the two coexist, when Toolbelt needs a manual recovery step, and
where a custom MCP client fits. It states only what the repository's accepted
records support, and links each section to them.

## How to read this page

- **Two surfaces, kept apart.** Epic's official MCP server and its own
  toolsets are one surface. Toolbelt's custom bridge, with `mcp_server.py` and
  `client.py`, is another. Toolbelt's in-process registration with Epic's
  toolset registry is a third fact, and it does not make Toolbelt reachable
  through Epic's server. See the
  [four-surface truth model](work-orders/completed/WO-003-official-mcp-doc-convergence.md#locked-truth-model--four-distinct-surfaces).
- **Static is not live.** Source-defined coverage categories and static tests
  are not live verification. Where something ran live, the build it ran on is
  named where the record gives it.
- **Findings are historical.** Observations are tied to the UEFN build they
  were made on. Most come from one audit on UEFN 42.00; one later client
  acceptance run used one UEFN 42.20 boot. Neither is a claim about current or
  every build.

## Capability matrix

| Capability | Epic's official MCP toolsets | Toolbelt's custom bridge and registered tools | Evidence |
|---|---|---|---|
| Verse files and compilation | List, write, read, delete, and a clean `BuildAll` passed live. A deliberate syntax error returned a structured diagnostic. UEFN 42.00. | No in-editor Python API compiles Verse. The audit names Verse templates, generators, schema intelligence, and project-specific repair as Toolbelt's differentiation. | [Audit: Verse](audits/2026-08-24-uefn-42-official-mcp-audit.md#verse); [audit: capability direction](audits/2026-08-24-uefn-42-official-mcp-audit.md#capability-direction); [WO-003: claim disposition](work-orders/completed/WO-003-official-mcp-doc-convergence.md#claim-disposition-inventory) |
| Creative devices | Catalog, placement, and Verse `@editable` read, change, and restore passed live. Stock-device property operations rejected a placed device (see quirks below). UEFN 42.00. | Bulk audits and high-level composition, per the audit. | [Audit: Creative devices](audits/2026-08-24-uefn-42-official-mcp-audit.md#creative-devices); [audit: capability direction](audits/2026-08-24-uefn-42-official-mcp-audit.md#capability-direction) |
| Scene Graph entities | Class discovery, creation, lookup, transform read and change, and component listing passed live. A top-level entity could not be deleted through the same surface. UEFN 42.00. | Reusable entity kits, per the audit. | [Audit: Scene Graph](audits/2026-08-24-uefn-42-official-mcp-audit.md#scene-graph); [audit: capability direction](audits/2026-08-24-uefn-42-official-mcp-audit.md#capability-direction) |
| UMG authoring | All 21 signatures were described live. No widget was created, so UMG is signature-confirmed only, not mutation-verified. UEFN 42.00. | No Toolbelt UMG claim is made here. | [Audit: UMG](audits/2026-08-24-uefn-42-official-mcp-audit.md#umg); [WO-003: evidence qualifications](work-orders/completed/WO-003-official-mcp-doc-convergence.md#evidence-qualifications-to-preserve) |
| Play sessions | Session start, a game stop and restart, a Verse-only `PushChanges`, and session stop completed live. UEFN 42.00. | No in-editor Python API launches or stops a session. Toolbelt contributes the `publish_audit` preflight and, outside the bridge, the `prepare_launch.bat` / `restore_after_launch.bat` boundary. | [Audit: session and launch boundary](audits/2026-08-24-uefn-42-official-mcp-audit.md#session-and-launch-boundary); [WO-003: claim disposition](work-orders/completed/WO-003-official-mcp-doc-convergence.md#claim-disposition-inventory) |
| Broad asset and world automation | The live toolset list on UEFN 42.00 includes editor actor, asset, material, scene, and other editor toolsets. The audit did not exercise them. | The audit's recommended primary: snapshots, procedural systems, materials, lighting, diagnostics, and localization. | [Audit: official MCP inventory](audits/2026-08-24-uefn-42-official-mcp-audit.md#official-mcp-inventory); [audit: capability direction](audits/2026-08-24-uefn-42-official-mcp-audit.md#capability-direction) |
| Reaching it from an MCP client | Epic's own loopback server. It negotiated protocol `2025-11-25`, and its top level exposes only `list_toolsets`, `describe_toolset`, and `call_tool`. UEFN 42.00. | Through Toolbelt's own `mcp_server.py` or `client.py`, over the authenticated same-user loopback bridge. Not through Epic's server. | [Audit: official MCP inventory](audits/2026-08-24-uefn-42-official-mcp-audit.md#official-mcp-inventory); [WO-003: four surfaces](work-orders/completed/WO-003-official-mcp-doc-convergence.md#locked-truth-model--four-distinct-surfaces); [Security boundary](#security-boundary-of-toolbelts-custom-bridge) |
| Toolbelt in Epic's toolset registry | `UEFN_Toolbelt` was absent from `list_toolsets()`, and the describe probe and all three `call_tool` probes returned toolset-not-found. This accepted negative result is bounded by `UE::ValkyrieToolset::ToolsetPolicy`. UEFN 42.00. | In-process registration and the internal list, describe, and run meta-tools passed before, during, and after the official probes. That is not external exposure. | [WO-002: Session B acceptance and completion record](work-orders/completed/WO-002-epic-toolset-integration.md#session-b-acceptance-and-completion-record); [evidence record](audits/evidence/2026-08-27-wo002-session-b-official-mcp.json) |
| Toolbelt's custom HTTP bridge | Not part of Epic's surface. | An authenticated, fail-closed control plane. It remains experimental and trusted-same-user-only. | [WO-001](work-orders/completed/WO-001-custom-mcp-security.md#session-a--authenticated-fail-closed-control-plane); [`SECURITY.md`](../SECURITY.md#experimental-custom-mcp-boundary) |

The last two rows replace the audit's capability-direction rows for the custom
HTTP bridge and for Epic Toolset registration: WO-001 and WO-002 are the later
accepted records for those two rows. Every other row keeps the audit's
capability direction as recorded on UEFN 42.00.

## Launch boundary: Verse compilation and play sessions

Verse compilation and play-session launch and stop have no in-editor Python
API. Epic's official server provides both on its own surface; Toolbelt's
in-editor Python does not. See the
[WO-003 claim disposition](work-orders/completed/WO-003-official-mcp-doc-convergence.md#claim-disposition-inventory).

On UEFN 42.00 the audit verified this order around an official session:

```text
publish_audit while Python was present
-> confirm zero TextRenderActors
-> prepare_launch.bat moved 96 Python files
-> official StartSession returned Completed
-> inspect connected/running state
-> stop and restart the game
-> clean Verse compile and Verse-only PushChanges
-> stop game and session
-> restore_after_launch.bat restored the same 96 files
-> delete fixture and compile cleanly
```

No restart, hot reload, deploy, or replacement Python creation occurred while
the Python files were stashed. The remote result was awaited, and Fortnite
opening was not treated as proof. See the
[audit's session and launch boundary](audits/2026-08-24-uefn-42-official-mcp-audit.md#session-and-launch-boundary).

## Recovery and the project-Python rule

### Toolbelt does not start when the MCP Toolsets beta is on

On UEFN 42.00, enabling Project Settings → Beta Access → UEFN MCP Toolsets
stops the project's `Content/Python/init_unreal.py` from running at editor
start. Nothing raises: Toolbelt simply does not start, and `tb.run(...)`
reports tools as unregistered. Recover once per editor session in the UEFN
Python console, or turn the flag off:

```python
import UEFN_Toolbelt as tb; tb.register()
```

The audit observed the suppression and this recovery on UEFN 42.00, and the
recovery restored the registry of 362 tools across 55 categories. See
[Quirk #36](UEFN_QUIRKS.md#quirk-36--uefn-mcp-toolsets-beta-flag-stops-the-projects-init_unrealpy)
and the [audit's Toolbelt coexistence](audits/2026-08-24-uefn-42-official-mcp-audit.md#toolbelt-coexistence).

On one later boot of UEFN 42.20 (`Release-42.20-CL-58011042`) with the beta
on, the project script did run. That is one boot. It is not a demonstrated fix
and not a general result. See
[WO-004 Session C, section 3](audits/2026-09-28-wo004-session-c-live-acceptance.md#3-build-compatibility-and-beta-state).

### Remove project Python before Launch Session, Push Changes, or publishing

On UEFN 42.00, the standard `VKCreateUGC` role cannot upload Python as island
content. Launch Session or Push Changes can open Fortnite before the remote
validation failure arrives, so Fortnite opening is not evidence that
validation passed. `.urcignore` does not control the module staging that is
validated. The only safe precondition is zero `.py` files anywhere under the
UEFN project root:

1. Run `prepare_launch.bat` from the Toolbelt repository.
2. Launch Session or Push Changes, and wait for remote validation.
3. Run `restore_after_launch.bat`.

See [Quirk #42](UEFN_QUIRKS.md#quirk-42--project-py-files-pass-local-staging-but-fail-remote-validation-discovered-2026-08-23).

## Security boundary of Toolbelt's custom bridge

The custom bridge is experimental and for trusted same-user local clients
only. Do not expose it beyond the local machine or connect an untrusted local
process. Its control plane, from
[WO-001](work-orders/completed/WO-001-custom-mcp-security.md#session-a--authenticated-fail-closed-control-plane)
and [`SECURITY.md`](../SECURITY.md#experimental-custom-mcp-boundary):

- Every listener start generates a bearer secret and writes it to the
  same-user local handoff file `Saved/UEFN_Toolbelt/mcp_session.json`. A
  restart rotates it and a stop removes it.
- Secrets are compared in constant time and redacted before status, command
  results, errors, logs, history, or client output is stored or emitted.
- Method, path, `Host`, `Origin`, content type, authentication, and body size
  are checked before parsing or dispatch. Browser origins and preflight
  requests are rejected, and no CORS permission is emitted.
- Arbitrary remote Python is not available. The bridge exposes only
  registered, bounded commands; deliberate scripting stays in UEFN's local
  Python console.
- The listener becomes reachable only after main-thread callback registration
  and the session handoff succeed. If registration fails, there is no
  listener, no token, and no fallback that runs work on the HTTP thread.
  Accepted commands run from that callback on the editor main thread.

WO-001's accepted live `TOOL_TEST` evidence covered a full UEFN restart,
authenticated queued dispatch, exact HTTP 411 rejection of signed and duplicate
`Content-Length` without dispatch, exact HTTP 401 rejection of missing and
wrong credentials, credential non-disclosure, the local-only listener
lifecycle, and clean shutdown. The mandate does not record the editor build
for that run.

### What it does not defend against

- The handoff file is privileged local material. It is deliberately readable
  by the same Windows user, so another process running as that user may read
  it or otherwise act with the user's privileges.
- Loopback plus a bearer token is not a sandbox.
- There is no defence against a compromised same-user account or privileged
  local malware.
- Binding to `127.0.0.1` limits network reach; it does not authenticate a
  client by itself.

See [`SECURITY.md`](../SECURITY.md#experimental-custom-mcp-boundary).

### Client outcomes and transport

`client.py` and `mcp_server.py` make at most one connection attempt per call,
and none when the handoff is missing or invalid. Nothing is retried
automatically. They connect directly to the validated loopback
endpoint, ignoring HTTP proxy settings and following no redirect. When no
reply confirms whether a command ran, they report an unknown outcome; check
the editor state before sending a state-changing command again. See the
[client transport and outcomes](../.claude/mcp_reference.md#transport-and-outcomes)
and the
[WO-004 completion record](work-orders/completed/WO-004-modal-observability.md#completion-record).

What ran live, on one UEFN 42.20 boot:

- The single-attempt behaviour: every client call that sent a request made
  exactly one attempt. See
  [Session C, section 6](audits/2026-09-28-wo004-session-c-live-acceptance.md#6-reconciliation).
- Only the outcome rows listed as exercised live: row 1, row 3 (a direct
  socket timeout only), row 4 (the `401` pair only), row 7, and row 9. See
  [Session C, section 9](audits/2026-09-28-wo004-session-c-live-acceptance.md#9-deviations-and-coverage-limits).

Proxy bypass and redirect refusal rest on static tests only.

## Known official-MCP quirks

Each of these was observed on UEFN 42.00 by the
[audit](audits/2026-08-24-uefn-42-official-mcp-audit.md#findings) (P1 items 4
and 5, P2 item 4). Each is historical and build-specific.

- **Modal blocking.** A Save Content modal blocked a queued official call
  until the owner closed it. Agentic automation had no way to observe the
  modal.
- **Stock-device type mismatch.** `PlaceDevice` succeeded but returned an
  Actor that stock-device property operations rejected, because they require
  `ScriptDevice`. See [Creative devices](audits/2026-08-24-uefn-42-official-mcp-audit.md#creative-devices).
- **Root-entity deletion.** `DeleteEntity` returned `Cannot delete the root
  entity` for a top-level entity created by the same official surface. See
  [Scene Graph](audits/2026-08-24-uefn-42-official-mcp-audit.md#scene-graph).
- **False no-client-log report.** `GetClientLogEntries` reported that no
  client log was found while the official session state was connected and
  running. See [session and launch boundary](audits/2026-08-24-uefn-42-official-mcp-audit.md#session-and-launch-boundary).
- **Blank server identity.** The server's name, title, and version fields were
  blank, although Epic's documentation refers to `unreal-mcp`. See the
  [official MCP inventory](audits/2026-08-24-uefn-42-official-mcp-audit.md#official-mcp-inventory).

## Evidence gaps

**Benchmark disclosure.** From the
[WO-006 closure record](work-orders/superseded/WO-006-official-vs-toolbelt-benchmark.md#closure-amendment-owner-decision):

A controlled comparison was planned. The only live attempt was rejected:
logged cadence did not establish the required foreground condition, and the
project was saved during the session. No accepted comparison, performance
ranking, compatibility finding or bridge-replacement conclusion exists.

**Modal detection is deferred.** WO-004 deferred modal or dialog detection,
heartbeat and status endpoints, and further feasibility probes. Its live
stalls were console sleeps, not dialogs, and no modal diagnosis is claimed.
See [WO-004: exclusions and deferred work](work-orders/completed/WO-004-modal-observability.md#exclusions-and-deferred-work)
and [Session C, section 9](audits/2026-09-28-wo004-session-c-live-acceptance.md#9-deviations-and-coverage-limits).

**WO-004's live limits.** See
[Session C, sections 7 and 9](audits/2026-09-28-wo004-session-c-live-acceptance.md#7-harness-and-what-was-not-integration-tested)
and the [WO-004 completion record](work-orders/completed/WO-004-modal-observability.md#completion-record).

- The client acceptance ran on one machine and one boot: Windows 11, UEFN
  build `Release-42.20-CL-58011042`, with the MCP Toolsets beta on.
- Outcome rows 2, 5, 6, 8, and 10 and the other 13 enumerated rejections
  were not exercised live. They rest on static tests.
- Proxy bypass and redirect refusal are protected by static tests only.
- No MCP-host, stdio, or FastMCP integration was tested.
- Exactly-once execution is not claimed.
- The bridge's unhandled `ConnectionAbortedError` was observed and not fixed.

**MCP-client check (2026-11-01).** After WO-004, a read-only check ran
`mcp_server.py` through two MCP clients, each registered once at user level
(see [MCP_CLIENT_SETUP.md](MCP_CLIENT_SETUP.md)): the Claude desktop app's Code
tab and the Codex desktop app, on Windows 11 with UEFN
`Release-43.00-CL-59596594`. In each, `ping`, the first page of
`list_toolbelt_tools` (50 of 362 tools) and the first page of `get_all_actors`
(50 of 176 actors) returned inline. Tools that change the level, later pages,
maximum-size replies and other clients were not exercised. The check was an
owner-run practical check; the WO-008 formal live proof was not performed.

**Coverage categories are not live verification.** Of 362 registered tools,
80 are `defined-outcome`, 73 `defined-execution`, and 209
`registration-only`. These source categories describe what the test code is
written to check. They establish no live verification of any tool, and run
evidence is recorded separately. See the
[WO-005 definitions](work-orders/completed/WO-005-coverage-source-of-truth.md#definitions--decision-lock)
and the generated block in [`TOOL_STATUS.md`](../TOOL_STATUS.md).

**Unexercised official surfaces.** UMG is signature-confirmed only, and the
audit did not exercise the editor toolsets in the official list. See the
[audit's UMG section](audits/2026-08-24-uefn-42-official-mcp-audit.md#umg).
