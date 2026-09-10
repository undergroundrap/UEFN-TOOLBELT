# WO-004 — Modal Observability and Human-Safe Blocking

STATUS: ISSUED

AUTHORIZATION: ISSUED — SESSION NOT AUTHORIZED

OWNER: Ocean Bennett

PRIORITY: P1

BASELINE: `0d513f1639cf197707132205f4074d0fe3a750cc`

ISSUANCE_COMMIT: `8444faf340afe47765c43d943200db712880817b`

ISSUANCE_CI_WORKFLOW: `34441169191`

ISSUANCE_CI_JOB: `102756337393` — Lint, types, tests

## Issuance basis

The independently accepted revision of this mandate was committed as
`8444faf340afe47765c43d943200db712880817b`; [CI workflow
`34441169191`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34441169191)
completed successfully, including required job
[`102756337393` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34441169191/job/102756337393).

Issuance alone grants no implementation authority. A session becomes
implementable only when the owner names it in root `WORKORDER.md`. The
planning baseline above is preserved unchanged; it records the state this
mandate was planned against, not the issuance point.

## Planning basis

This revision was prepared at `0d513f1639cf197707132205f4074d0fe3a750cc`, on
which CI workflow
[`34434992222`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34434992222)
completed successfully, including required job
[`102738086806` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34434992222/job/102738086806).

That is planning evidence only. The issuance basis is separate: issuance records
its own commit, workflow, and required job in the root pointer at that gate.

## Problem and accepted evidence

**Observed**, recorded as P1 finding 4 of the
[2026-08-24 UEFN 42.00 audit](../../audits/2026-08-24-uefn-42-official-mcp-audit.md)
(`:274`, with the owner action at `:68`): a Save Content modal blocked an
official queued call for approximately four minutes, and the call resumed
immediately after the owner closed the dialog. The audit states in the same
finding that agentic automation lacks modal observability.

**Inferred, not observed**: that a modal is the general cause of long-pending
operations. One correlated incident establishes that a modal *can* block a
queued call. It does not establish that pending calls are usually
modal-blocked, nor that any modal state is reachable from third-party Python.

**Evidence gap**: the audit records the incident narratively. No log excerpt,
timestamp range, or screenshot is preserved as a citable artifact for that
specific four-minute block. This Work Order does not manufacture one. Session A
records whatever primary evidence still exists, or records its absence.

## Transport boundaries — read before scoping anything

Three distinct surfaces are involved. Conflating them is the main way this Work
Order could produce work that cannot address the recorded incident.

| Surface | What it is | Relationship to the incident |
|---|---|---|
| Epic's official UEFN MCP | Epic's own server and toolsets, `127.0.0.1:8000/mcp` | **The blocked call was here.** Not Toolbelt code. Toolbelt cannot instrument it |
| Toolbelt's custom bridge | `Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py`, in-editor authenticated same-user loopback listener | A *separate* transport. WO-002 recorded Toolbelt is not reachable through Epic's MCP, bounded by `UE::ValkyrieToolset::ToolsetPolicy` |
| Toolbelt client side | `mcp_server.py`, `client.py` | Callers of Toolbelt's bridge only. They observe Toolbelt commands, never official-MCP ones |

**Consequence for scope.** Improving Toolbelt's bridge or client does not
observe, classify, or recover the official-MCP call described in the incident.
Any claim that it does must be rejected in review. What Toolbelt can honestly
offer is (a) better status semantics for *its own* operations, and (b) if and
only if Session A proves it, a read-only editor-state signal the owner or an
agent can consult while *any* surface appears stalled.

## Candidate paths and responsibilities

Identified by source inspection at the baseline. Session B confirms or revises.

| Path | Current responsibility | Candidate change |
|---|---|---|
| `mcp_server.py` (`:190`, `:211`, `:232-236`, `:327`, `:646`) | External bridge client; raises one undifferentiated `TimeoutError` — *"timed out after Ns. The UEFN editor may be blocked. Try a shorter operation."* | Evidence-based status result instead of that single guess |
| `client.py` (`:50-71`, `:145-186`, `:241`, `:265`) | Stdlib client. It **already** separates `NotConnected`, `CommandTimeout`, and `AuthenticationError` (`:171-186`). What is absent is a `queued` or `modal_blocked` outcome and a shared structured result rather than exceptions | Extend to the shared status result; do not rebuild the split that exists |
| `Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py` (`:114`, `:1006-1015`, `:1072`) | In-editor listener; `queue.Queue` handoff drained by `register_slate_post_tick_callback` | Possible read-only status endpoint — subject to the main-thread constraint below |
| `tests/` | Static suites, fake `unreal` via `conftest.py` | Simulated status/regression tests |

**Main-thread constraint.** Toolbelt drains its command queue on the Slate
post-tick callback — the same main thread every `unreal.*` call requires. A
modal that blocks the main thread therefore blocks Toolbelt's own sensing on
that thread. Any design that senses modal state from the tick callback is
self-defeating for the exact case it targets. Session A must confront this
directly. A design that cannot report while blocked is not a solution.

## Session A — feasibility, read-only

No implementation. Feasibility settles first, because every later session
depends on its result.

1. Identify candidate supported APIs for editor, window, or modal state by
   read-only source and documentation inspection.
2. Determine whether any candidate is readable **while the main thread is
   blocked**, or whether all sensing shares that thread.
3. Record whatever primary evidence remains for the 2026-08-24 incident, or
   record its absence.
4. Specify the exact owner-operated TOOL_TEST probes the questions above
   require, including any `api_search` or `api_inspect` run against the live
   runtime. Those probes need their own owner gate. This document does not open
   it, and no live UEFN operation happens during Session A planning.

**`unavailable` and `unknown` are valid, complete results.** WO-002 established
that a recorded negative result is an acceptable outcome. If no supported API
exists, or none is readable while blocked, Session A ends with that finding and
the remaining sessions are re-scoped or dropped.

**Explicit decision required.** After Session A the owner decides in writing
whether the next session is re-scoped, dropped, or opened. Every dependent
session stays closed until that decision is recorded, and each one needs its own
owner gate.

**Stop.** Session A ends with its finding recorded. Nothing further follows from
it without a separate owner gate.

## Status semantics — evidence required per outcome

An elapsed timeout is the absence of a reply. It is not evidence of a modal, of
failure, or of anything else. It cannot on its own distinguish a blocked editor
from a slow operation, a crashed editor, or a dropped connection.

| Status | Evidence required |
|---|---|
| `queued` | Bridge acknowledged receipt and the operation is present in its queue |
| `disconnected` | Transport-level failure: connection refused, socket closed, listener absent |
| `failed` | The operation returned an error, or the bridge reported it terminal |
| `modal_blocked` | A supported editor-state signal, proven in Session A, positively reports a blocking dialog |
| `unknown` / `pending` | **Default.** No reply and no positive evidence for any of the above |

`unknown` must remain reachable and must be reported as such. Collapsing it into
`modal_blocked` would restate the guess the current message already makes.

**No automatic retry of a possibly executed mutating command.** A timeout does
not prove the command did not run. Retrying a spawn, delete, save, or property
write risks duplicating or compounding an applied change. Retry may be offered
only for operations the transport can prove idempotent or unexecuted, and
otherwise must be an explicit owner decision.

**Operation identity and recovery** may be specified only where the actual
transport supports them. The bridge is synchronous and its internal request id
is never returned to a caller, so correlation of a late reply to a specific
in-flight operation is unproven. Session B must confirm what the transport can
actually do before any resume, cancel, or reattach behaviour is designed.
Official MCP operations are out of reach on both counts.

## Session B — implementation and static verification

- Shared status result across `mcp_server.py` and `client.py`, extending the
  existing `client.py` error split rather than replacing it.
- In-editor status surface only if Session A proved one exists.
- Simulated status and regression tests under `tests/`, driving the real code
  paths with the fake `unreal` module.
- Static gates: `ruff`, `mypy`, `pytest`, `scripts/drift_check.py`,
  `scripts/gen_api_manifest.py --check`.

**Stop.** Session B ends with the worktree uncommitted for independent review.
Commit, push, and live verification each need their own owner gate.

## Session C — live acceptance, owner-operated

Static tests cannot establish editor behaviour. Client-side timeout handling in
particular still requires live integration verification: its inputs come from a
real editor under real blocking conditions, and a fake `unreal` module cannot
produce them.

Per `CLAUDE.md`, an MCP-bridge change requires `deploy.bat` → **full UEFN
restart** → `tb.run("mcp_start")` → authenticated external ping. Acceptance
additionally requires, in TOOL_TEST:

1. A long-running operation reported `queued` while genuinely progressing, if
   Session A produced an in-editor status surface. If it did not, this case is
   dropped with the reduction recorded.
2. A stopped listener reported `disconnected`, never `modal_blocked`.
3. An owner-opened dialog: either `modal_blocked` with the Session A signal, or
   `unknown`. Both pass. A false `modal_blocked` fails.
4. The owner closes the dialog; the pending operation resolves with no automatic
   retry having occurred.
5. No mutating command duplicated across the sequence.

For case 3 the owner opens a dialog that can be dismissed without writing to the
level, so the cleanup requirement below still holds. If no such dialog is
available, the case is recorded as untested rather than forced.

**Stop.** Session C ends at recorded acceptance. Nothing further follows.

## Safety — non-negotiable

Toolbelt must never auto-confirm, dismiss, accept, decline, or manipulate any
dialog: destructive, save, validation, overwrite, missing-class, or otherwise
ambiguous. No blind keystrokes, no forced window closure, no automatic save, no
synthetic confirmation.

The only supported resolution is the owner reading the dialog and acting. The
deliverable's job is to tell the owner **that** something appears blocked and
**what** to look at — never to act for them.

## Inclusions

Status semantics and their evidence; read-only feasibility work; a shared client
status result; simulated regression tests; owner-facing instruction text.

## Exclusions and deferred work

- No general computer control, window manipulation, or input synthesis.
- No WO-001 custom-bridge security change or expansion.
- No instrumentation of Epic's official MCP server.
- **Repository metadata is out of scope** — the GitHub description, the
  homepage, the topics, and the visibility all stay as they are.
- **Branch-protection settings are out of scope.**
- **No tag. No GitHub Release. Social publication is out of scope.**
- Four non-blocking observations recorded during the review of commit
  `0d513f1639cf197707132205f4074d0fe3a750cc` remain deferred and out of scope:
  a claim carried on both the root pointer and an issued mandate is reported
  against only one of them; a redundant conjunct in the WO-007 identity test;
  an unreachable `ValueError` guarding an internal `surface` argument; and a
  redundant proposal-set branch in `scripts/drift_check.py`.
- Reducing the size of the governance-enforcement surface added by that same
  commit — 1024 insertions against 113 deletions across
  `scripts/drift_check.py` and `tests/test_repo_integrity.py` — belongs to a
  separate mandate. This one leaves that surface alone.

## Configurations and fixtures

UEFN 42.00; TOOL_TEST as the disposable level; Toolbelt's bridge started
manually; Epic's UEFN MCP Toolsets beta state recorded per run, since Quirk #36
suppresses the project startup script when enabled.

## Cleanup

Stop the listener, close the editor, confirm the handoff file is absent and
ports 8765–8770 are closed. Leave TOOL_TEST unsaved and unmutated.

## Acceptance criteria

- Every status is produced only from its specified evidence.
- `unknown`/`pending` is reachable and is the default without positive evidence.
- No mutating command is automatically retried after a timeout.
- Session A's result — including `unavailable` — is recorded before any
  dependent work is planned.
- Static gates and the CI required job pass.
- Session C evidence recorded, or the deliverable reduced to what was proven,
  with the reduction stated.

## Stop boundaries

Each is a separate owner gate and none implies the next: proposal revision →
independent pre-issuance review → issuance → Session A gate → Session A decision
→ Session B gate → independent review → commit → push → CI → Session C gate →
acceptance.

Live UEFN probes are owner-operated and separately gated. This document opens
nothing.

## Issuance enforcement

Issuance acceptance had to protect three surfaces that were unenforced at the
planning baseline. Driving the real `check_work_order_contract()` against a
temporary issued-state fixture at
`0d513f1639cf197707132205f4074d0fe3a750cc` produced zero findings for all of
the following, which is why each is named here:

1. **The root pointer's `- Base commit:`** — a zeroed, garbage, or simply wrong
   value raised nothing once a later order owned the pointer. It is now pinned
   to the issuance commit while this mandate is issued and no session is open.
2. **The root pointer's issuance evidence** — the `- Issuance commit:`,
   `- Issuance CI workflow:`, and `- Issuance CI job:` bullets could be deleted
   with no finding. They are now an exact, contiguous, terminal slice of the
   pointer's canonical bullet block.
3. **This mandate's own `BASELINE:` marker** — it could be zeroed with no
   finding. Exactly one canonical marker must now be present in this document,
   carrying the expected value, opening the canonical metadata slice.

Enforcement uses the existing structural validators in
`scripts/drift_check.py` and carries mutation coverage in
`tests/test_repo_integrity.py`, driving the real checker over temporary copies.
The mutation set covers, for each of the three surfaces: a changed value,
a removed field, a duplicated field, and a decoy — a correct value placed
somewhere else in the file, which does not satisfy the check.

All three surfaces are enforced as of this issuance, against the values
declared in the canonical metadata block above and in the root pointer's
canonical bullet block. The planning basis and the issuance basis are
distinct records and must not be conflated.

NEXT GATE: separate owner authorization for Session A feasibility only,
recorded in root `WORKORDER.md`. Issuance authorizes no session. Session A,
Session B, Session C, and all live UEFN work remain closed.
