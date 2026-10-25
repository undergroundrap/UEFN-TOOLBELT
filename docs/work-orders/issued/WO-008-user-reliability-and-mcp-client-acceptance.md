# WO-008 User reliability and MCP client acceptance

STATUS: ISSUED
AUTHORIZATION: ISSUED — SESSION B AUTHORIZED FOR THE PINNED OVERSIZED-REPLY LIVE PROOF ONLY
Owner: Ocean Bennett
Priority: user-facing reliability and missing integration evidence
Draft date: 2026-10-04
Revision: r2
Planning baseline: `9879d39fbdb58083a0f7229a9c9c90c7d6fb375f`

This is an issued following-train Work Order, outside the frozen
WO-001 through WO-007 train. The root pointer identifies WO-008 with
session B for the pinned oversized-reply live proof only. The Session A
result stays recorded as diagnostic only, Session A acceptance is not met,
and Session C remains unauthorized.

## Purpose and evidence

Establish that one actual MCP client can use Toolbelt's authenticated bridge to
read, change, and restore one actor in the owner's installed UEFN build. Then
repair the bounded disconnect-handling issue and misleading setup/UI wording,
and verify the changed package through that same client. A useful result is a
repeatable user workflow with explicit limits, not more tools or a benchmark.

The baseline's repository CI succeeded: workflow `37227518827`, job
`111510144686`, with 2666 passed and 14 skipped on Ubuntu 24.04 / Python 3.11.16.
That is carried evidence from the verified push handoff, not a run for this
draft or live MCP-host evidence. The skip reasons were not printed.

The released `v2.5.0` tag remains on
`eabce22518d07725e05173aa707909023166a799`. Runtime, `client.py`, `mcp_server.py`,
and `.mcp.json.template` have no diff between that tag and the planning baseline.
Accepted records do not demonstrate the hardened package through an actual
MCP host, or establish compatibility with UEFN 42.30. Record the installed
build at execution; do not assume it from chat or advertise an untested build.

The [WO-004 Session C record](../../audits/2026-09-28-wo004-session-c-live-acceptance.md)
observed `ConnectionAbortedError` during response writes. Later requests still
succeeded; this is not evidence that the listener crashed. The
[composition explainer](../../OFFICIAL_MCP_AND_TOOLBELT.md) and
2.5.0 notes disclose missing host integration and unsupported dashboard/menu
wording. WO-006 remains superseded, with no accepted benchmark.

## Admission and issuance prerequisites

Proposal admission was separately accepted and committed at
`4ff86e8d1c9c89ebda597570ad4f757605ccd81e`. It recognized this exact
following-train proposal only and retained NONE/NONE. WO-008 is not added
to the frozen WO-001 through WO-007 train.

The separately adopted issuance/session-enforcement plan r2 supported the
closed issuance and Session A offline preparation. Separate transitions
installed the pinned Session A live baseline and its replacement attempt and
recorded that attempt's result as diagnostic only. Owner amendment OR-1 adds
three literal oversized-reply phases beside plan r2's phase table; separate
transitions installed the first, OR_CORRECTION, and install the second,
OR_PROOF. Session A acceptance, other product corrections, recording the
proof's result and live acceptance still need separately reviewed
enforcement transitions and explicit owner decisions. No later phase is
installed here.
Frozen-train missing, duplicate and misplaced-order protections, publication
history and earlier terminal records remain in force. Unknown issued orders
remain invalid; there is no blanket scanner exemption.

## Issuance basis

BASELINE: `4ff86e8d1c9c89ebda597570ad4f757605ccd81e`
Admission CI workflow: `37246398757`
Admission CI job: `111565059168` — Lint, types, tests
Owner issuance instruction SHA-256: `5997654fb63b587ae72265d4382bf9f2f8a752e4fb09a6d79593a5b88725746a`

The owner adopted the accepted plan r2 and authorized only this closed
governance issuance transition. Admission CI succeeded on the baseline,
not on this uncommitted transition or any session output; it demonstrates
neither an MCP host nor a live UEFN build.

The owner accepted a narrow offline-verification exemption for these seven
governance paths only. Runtime or live need stops this transition. This
record grants no session execution, configuration change, installation,
UEFN contact, recovery, commit, push, cleanup or publication authority.

## Session A offline preparation record

Session A preparation basis commit: `0d1de9e6a1f49ea422cd7911d1c40d67787ddde4`
Session A preparation CI workflow: `37359992194`
Session A preparation CI job: `111931901481` — Lint, types, tests
Owner Session A preparation instruction SHA-256: `3f2218b675dc2257fffe3ea4e4ceb4e351a23bc651cfd53177fe7ef62882c9ed`

The owner authorized Session A for offline preparation only. CI succeeded on
the closed issuance commit, not on this transition or any Session A output;
it demonstrates neither an MCP host nor a live UEFN build.

Preparation produced, outside the checkout, a redacted exact call plan and a
fixture/setup checklist for independent review. It read no owner
`.mcp.json`, credential, session handoff or private editor log, and changed
no repository file. At that gate, client launch, configuration reads or changes, dependency
installation, deploy, editor contact, bridge lifecycle, endpoint calls,
fixture mutation, product changes, recovery, commits and pushes remained
unauthorized. Planned values were not recorded as observed results.

The owner accepted a narrow offline-verification exemption for this
transition's five governance paths only. Runtime or live need stopped that work.

## Session A live baseline record

Session A live baseline basis commit: `075ba2948444e40da9fb975f1cda4c29006b0169`
Session A live baseline CI workflow: `37698808630`
Session A live baseline CI job: `113057020206` — Lint, types, tests
Accepted preparation package SHA256SUMS: `8df8abdb4d70882f4ee0d1129907b166fa44f1ffbf87361ca3586d565d261ed1`
Accepted preparation review SHA256SUMS: `517b9c15744ee26e4c5967ff00eb9a4476330b723e878eb11902fc9d84e0351a`
Accepted A_LIVE plan SHA256SUMS: `8e2d7481e4b245ed5e5afb132b9545d3754108907b1c16beb8c64fe3ad8a9add`
Owner Session A live baseline instruction SHA-256: `671d1dfe2c84922709366cf189c2576c8fc3ea96ddd2bc45e1346b9ce22925a9`

The owner authorized Session A for the pinned live baseline only: one run
of the accepted call plan, as amended by the accepted execution addendum,
through Claude Code against an owner-approved disposable project, with the
owner decisions that instruction records. CI succeeded on the preparation
commit, not on this transition or any live result; it demonstrates neither
an MCP host nor a live UEFN build.

Within that one run, Session A uses as its deploy source the clean,
synchronized commit that carries this record, after that commit's own CI
has succeeded and its runtime and deployment sources are shown unchanged
from the basis commit. For Session A the owner performs the deploy, editor
start, fixture preparation and local bridge start, and stops the bridge only
as the cleanup decision that instruction records allows; Session A's client
issues only the nine planned tool calls, each approved individually, with no
retry. Any stop after live-run setup begins ends the attempt. Session A
recovery, a repeat run, installations or configuration changes that
instruction does not name, product corrections, Session B, Session C,
commits and pushes remain unauthorized. Results are recorded only by a
separate transition.

Independent review, the commit, the push and successful CI are
preconditions only; none of them authorizes or starts the run. A choice
or setup item that instruction omits follows the accepted addendum's
missing-choice rule.

The owner accepted a narrow offline-verification exemption for this
transition's five governance paths only. The live run is Session A
evidence, not verification of this transition.

## Session A replacement attempt record

Session A live baseline commit: `ce04d17ab5fd548adaddb95775e23b97f418829f`
Session A live baseline commit CI workflow: `37874506631`
Session A live baseline commit CI job: `113639869831` — Lint, types, tests
Stopped attempt run ID: `wo008-a-live-2026-10-09-1`
Accepted replacement attempt plan SHA256SUMS: `5806aeef223c80a10f9b540728b574af4600852727b0f231bae1082dd7ec7440`
Owner Session A replacement attempt instruction SHA-256: `420d59ff3fb1f4bcbd1169ef5a3fce3c63187aa7ab99bc4faa628864274f44e2`

The single attempt that the live baseline record allowed stopped at setup
step 2, before step 0, because a setup method was supplied at a path the
operator's environment could not resolve. Nothing was deployed, no editor or
client was launched, no tool call was made and no project file was read. It
produced no live result, and this section records only why it stopped.

That attempt is used, and this section alone governs the next one. The owner
authorized one replacement attempt for Session A: one run of the accepted
call plan, as amended by the accepted execution addendum and the accepted
replacement attempt plan, through Claude Code against an owner-approved
disposable project, with the owner decisions that the replacement attempt
instruction records. CI succeeded on the live baseline commit, not on this
transition or any live result; it demonstrates neither an MCP host nor a
live UEFN build.

Within that one run, Session A uses as its deploy source the clean,
synchronized commit that carries this record, after that commit's own CI
has succeeded and its runtime and deployment sources are shown unchanged
from `075ba2948444e40da9fb975f1cda4c29006b0169`, and every setup method is
verified at its pinned path before setup begins. For Session A the owner
performs the deploy, editor start, fixture preparation and local bridge
start, and stops the bridge only as the cleanup decision that instruction
records allows; Session A's client issues only the nine planned tool calls,
each approved individually, with no retry. Any stop after its setup begins
ends the attempt. Session A recovery, a further attempt, installations or
configuration changes that instruction does not name, product corrections,
Session B, Session C, commits and pushes remain unauthorized. Results are
recorded only by a separate transition.

Independent review, the commit, the push and successful CI are
preconditions only; none of them authorizes or starts the run. A choice
or setup item that instruction omits follows the accepted addendum's
missing-choice rule.

The owner accepted a narrow offline-verification exemption for this
transition's four governance paths only. The replacement attempt is
Session A evidence, not verification of this transition.

## Session A diagnostic result record

Session A replacement attempt commit: `ca86bc0f641591e830fd882ea05607d62ca11c6b`
Session A replacement attempt CI workflow: `38164234607`
Session A replacement attempt CI job: `114543334362` — Lint, types, tests
Replacement attempt run ID: `wo008-a-live-2026-10-11-2`
Accepted evidence handoff r2 SHA256SUMS: `67d3728dafbda53955fe31ea40de281dc9c0f51d18d003c53548fbe346c94486`
Accepted evidence delta review SHA256SUMS: `9722d9d75eee4d33f2a2b90b9092f92293f7096a0fc99e0acec69652e3fa0f4d`
First evidence review SHA256SUMS: `38a160706f8700fae7f915211ee498a9eb3bfec279196f1ca3efe109780651c6`
Accepted diagnostic result plan SHA256SUMS: `c39081f3aacf38c0dbdf2ec459a6743c78e43d6429e0cda296c7848ecf2e7971`
Owner Session A diagnostic result instruction SHA-256: `dffc1b6e525b9242770cd850bc76cbb79628df52f988b4d3b594d9bd8c0b8e14`

The replacement attempt is consumed. As the accepted handoff reports, under
the accepted protocol its first evidenced definite stop came before step 0,
when the client showed a first-run prompt that the instruction did not name.
Further stop and hold conditions followed: a second MCP server was connected,
an auto-accept permission mode was active, no per-call approval prompt was
shown, and the client replaced four oversized replies with notices. These
observations rest on owner screenshots and reports that the run's evidence
folder does not preserve. As the client displayed, the nine planned calls were
then made under owner direction, outside the retry gate; that no other call
was made is not established. None of Session A's call stages is met as an
attempt step, and this record is not Session A acceptance or compatibility
evidence. Other disclosed protocol departures are recorded in the accepted
handoff.

The owner accepted the redacted evidence handoff r2 and its independent delta
review as a limited diagnostic result only. Preserved records show that the
deployed runtime matched the source commit, and that the project footprint
gained one saved actor and lost no file. A preserved narrative record, without
a command transcript, reports that after the run no listener remained. The
absence of the bridge handoff file at both default locations rests on unsaved
session output and on an owner-reported editor-side check, and its record has
no command transcript. Owner reports, screenshots read by the implementer and
unsaved session output, none of them preserved in the run's evidence folder,
indicate that the client's tool list had 34 entries, that it reported
authenticated queued transport with remote Python disabled, and that one actor
was moved 100 cm and restored in memory within tolerance. These are credible
but unverified.

Required records were not made for the UEFN About build, the external Python
version or the engine install to be started, and the evidence-location rule
was not met for the owner-operated and live steps. The required repeat of the
launch-window environment check is not evidenced. Simulate Physics was not
observed as a setting, an unresolved block before live start with no recorded
owner decision. The cleanup ran under owner direction, outside the
normal-cleanup rule, and its save-prompt answer was not recorded. Persistent
rollback is not established: one actor was saved during editor use, and its
saved transform is unknown. Client configuration changes, a client
auto-update and approval writes occurred during the run, and retained client
and project state was not removed. Per-call approval, conformance beyond the
client's own display, exactly-once execution and the completeness of any
oversized reply are not established.

As the client displayed and unsaved session output recorded, at the client's
default MCP output limit the `list_toolbelt_tools` reply, which lists every
registered tool (about 235,000 characters), and each `get_all_actors` reply on
the 176-actor test level (about 580 characters per actor) were replaced by
notices, so on that level those steps cannot be met in the client as planned.
A correction is product work. It needs a separately authorized bounded
amendment and plan, and this record installs none.

That attempt is consumed, and this section governs over the earlier Session A
sections, including the replacement attempt section. No session is authorized.
A further Session A attempt, Session B, Session C, product corrections,
installations and configuration changes each need a separate reviewed
transition recorded in the root pointer; recovery and cleanup of retained
client or project state need a separately bounded owner instruction; and
commits and pushes remain separate owner decisions.

The owner accepted a narrow offline-verification exemption for this
transition's five governance paths only. This transition records evidence; it
is not live verification.

## Session B oversized-reply amendment record

Session A diagnostic result commit: `f551b7fa161464ecca0aa0a0ea959d873430fc4e`
Session A diagnostic result CI workflow: `38521809934`
Session A diagnostic result CI job: `115712995226` — Lint, types, tests
Owner amendment OR-1 SHA-256: `7e2282fc3d8578c32a9d7469708306cd621dff699ec15bfba1ab0f125e4b2538`
Oversized-reply correction plan SHA256SUMS: `fe528f8e9a872defd4beab4441495ff4f43282c3a1f66a94c2e10d2a527eeca9`
Accepting correction plan check SHA256SUMS: `aac9238481763371008575780ce867e1daa3fcb3a8f7d838534438d52f8c2c88`
Owner adoption instruction SHA-256: `ab0f1b3854203fad6ea8845f7c29515fbf83475042b2605e605402c352baea9c`
Accepted amendment transition plan SHA256SUMS: `00bda882993a9f32c94d468015d5e745ffb7b646c624707f81a22b49fafe9e6f`
Owner amendment transition instruction SHA-256: `198897bb226ca5ed290dfd073e41ca2bc43892d667a8089216553420975d7b11`

The Session A replacement attempt is consumed and recorded with a limited
diagnostic result only; Session A acceptance is not met, and this record does
not treat it as met. As the bounded amendment this mandate requires for an
unexpected integration defect, the owner allowed one correction on the basis
of the accepted diagnostic finding alone: bounded, paged replies for the MCP
tools `list_toolbelt_tools` and `get_all_actors`, under the reviewed
correction plan identified above. Its ceiling is `mcp_server.py`,
`tests/test_mcp_security.py`, `.claude/mcp_reference.md` and a new unreleased
entry in `docs/CHANGELOG.md`. Every other Session B item still requires
accepted Session A evidence. The implementation authority is single-pass. It
covers the implementation and any fixes the independent review requires,
within those four paths and under a bounded owner instruction with a delta
review, and it ends at the reviewed snapshot that the live-proof record pins.
The correction stays uncommitted for independent review and its separately
authorized live proof. It is not Session C and records no Session A, Session
C or compatibility acceptance. Commits, pushes and publication remain separate
owner decisions, and this section grants no further authority.

This section is the separate reviewed transition that the diagnostic result
section requires for Session B, for this one correction only. It governs over
that section's statement that no session is authorized, and over nothing else;
the Session A diagnostic result stays as recorded. This transition's
independent review, commit, push and successful CI are preconditions only and
are not permission for the correction's implementation, which needs a separate
owner implementation instruction. The oversized-reply live proof and
its later record each need their own reviewed transition recorded in the root
pointer, and neither is installed here.

The owner accepted a narrow offline-verification exemption for this
transition's five governance paths only. This transition records authority; it
is not live verification.

## Session B oversized-reply live proof record

Oversized-reply amendment commit: `255edf273d181d3ab8f89d204c4369ebfb6a4b8a`
Oversized-reply amendment CI workflow: `39191040408`
Oversized-reply amendment CI job: `117863696942` — Lint, types, tests
Oversized-reply implementation SHA256SUMS: `56cff017a7f186490dd7dfa18b6cd09b3807bc95ae0148f3d77f27393d809bf5`
Oversized-reply implementation review SHA256SUMS: `f90445552e3e21fc8f2914251bea7f1075885cd9e3328ba56e6f5d976bdbfffd`
Oversized-reply implementation review verdict: `ACCEPT`
Oversized-reply live-proof plan SHA256SUMS: `c03bfffc2d99bb477ee2d4a81943ac6f35bd2eb1de07c1f96c413c6ff09adc38`
Deploy-source manifest SHA-256: `a9269b73da0a14c7166e1fe115b9bc9e236addacf6763d1d2d1a28b2018ab014`
Owner live-proof instruction SHA-256: `ba22e4543f4613942788436f45e28bcb009efa66297c32d16651c78aa833b370`

The owner allowed one read-only live proof of the reviewed oversized-reply
correction, through Claude Code in the Claude desktop app only, under the
accepted proof plan identified above, with the calls, caps and stop rules that
plan records and no restart, retry or recovery. The proof has at most 24 calls
in its one client run, counting only calls of the server's tools, each
approved individually, and any stop ends the entire proof. That plan records
the Codex route as not verified, so no Codex client run is authorized. This
record carries no Session A, Session C or compatibility acceptance, and it
grants no commit or push.

The oversized-reply live proof tests exactly this reviewed correction,
identified by its files in the reviewed snapshot `wo008-or-product-implementation-2026-10-19`:

- `.claude/mcp_reference.md`: Git blob `be786fa04c7b5db008ad7bc320dbe19f816e1ec5`, SHA-256 `bf65e59aea783330d5f68a8f160736d0b7d19f3786f22d02fd6f05857baed7aa`
- `docs/CHANGELOG.md`: Git blob `6395dfe0dd34455e5088c40d27bf20351340d4cc`, SHA-256 `2f5cb90fea5b018483df6d532c2c378eb4f50ba9e86303de532c9b97a3affd80`
- `mcp_server.py`: Git blob `c3a4a8a0326ffb95a5a48c344f2473cbb4a08ae2`, SHA-256 `7a167a20d88e49e6ec31784a0869287038e17664a36d7d6bf5dad07d72498824`
- `tests/test_mcp_security.py`: Git blob `7b18d7d3abc6b529bc3cf54e5080f89acd393a69`, SHA-256 `6743e5879dca4b5e42eeb951e7f5829a1dcb55f78d91d2b3b1f97436a5cd7862`

Each Git blob is the line-ending-normalized identity Git would commit; each
SHA-256 is of the reviewed worktree bytes.

The proof uses only the commit that carries this record, after that commit's
own CI has succeeded, with exactly those four files present, uncommitted and
unchanged, and with the deployed runtime and the listed project files
matching the pinned deploy-source manifest and the plan's file classes.
Any stop, error, timeout, unknown outcome, rejected offset or keys_digest
change ends the proof as recorded. The correction stays uncommitted until a
separate transition records the proof's reviewed result.

This transition's independent review, commit, push and successful CI are
preconditions only and are not permission for the proof's first call, which
needs the owner's individual approval. The owner accepted a narrow
offline-verification exemption for this transition's five governance paths
only. This transition records authority; it is not live verification.

## Session A Real client baseline

The owner selected **Claude Code** as the first MCP client. This selects a test
target only; it grants no setup or live authority and establishes no compatibility.
Session A, if separately authorized, changes no product code. Use Claude Code
and an owner-approved disposable project, not a production project or recovery
of the old WO-006 fixture. Prepare and review the exact call sequence offline
before a separate owner instruction starts live contact. No launcher rehearsal
or timing harness is required.

Before live contact, record the client name/version, external Python and MCP
package versions, UEFN About build, source/deployment identities, deployed
extras, and the disposable project's file baseline. The owner performs deploy,
full editor restart, fixture checks, and local bridge lifecycle steps. Use the
selected client's normal MCP launch mechanism in an isolated configuration;
do not read or overwrite the owner's existing `.mcp.json`, install dependencies,
or change shared agent permissions without separate approval.

Use a movable, unlocked test actor approved by the owner. Before the baseline,
the owner prepares it with non-default rotation and scale: at least one component
of each must differ from its default by more than its agreed comparison
tolerance. Resetting to zero rotation or unit scale must therefore fail the
preservation check. Record its exact path, class, full transform, and an explicit
small location-only target.
The target must differ from the recorded baseline on at least one coordinate
by more than the agreed location-comparison tolerance; an unchanged actor must
fail the target check. Preserve rotation and scale. Resolve any unsupported
fixture check before starting; there is no implied exception to a required
check. The owner observes UEFN without unrelated editing during the short call
sequence. These fixture requirements add no endpoint calls.

The **actual client**, not a direct `client.py` harness or unit stub, must:

1. Initialize the MCP connection to `mcp_server.py` over its normal stdio path
   and enumerate its tools. This is Toolbelt's server, not Epic's official MCP.
2. Call `ping`, `list_toolbelt_tools`,
   `describe_toolbelt_tool("mcp_status")`, and
   `run_toolbelt_tool("mcp_status")`. Confirm authenticated queued transport
   and `execute_python_enabled: false`; do not infer authentication from a
   successful unauthenticated request or merely from tool registration.
3. Call `get_all_actors` and identify exactly one actor by its recorded path.
   Save the returned location, rotation, and scale as the baseline.
4. Call `set_actor_transform` once with that exact path and approved location.
   A separate `get_all_actors` call must confirm the target and unchanged
   rotation/scale; the owner also checks the actor in the editor.
5. Restore the original location once and independently re-read all transform
   fields. Compare numeric values with any representation tolerance explicitly
   agreed before the run, not by claiming JSON is byte-identical.

No additional tool execution, save command, generic batch, arbitrary Python,
Launch Session, Push Changes, or publishing is in scope. Record calls and
outcomes, but never bearer values, authorization headers, session identifiers,
or unredacted personal paths. Normal code may consume the handoff; agents must
not print its contents. Record credential discovery and rotation only through
redacted observations or existing tests.

On a timeout, UNKNOWN, disconnect, unexpected mutation, or ambiguous actor
identity, stop automatic calls. Do not retry or automatically restore a possibly
still-running mutation. The owner decides state inspection and recovery under
a separately bounded instruction. A failed or incomplete run is evidence,
not permission to repair code or repeat the run live.

Cleanup stops the local bridge, closes the client connection, and verifies
listener shutdown and handoff removal. Preserve the disposable project for
inspection; deleting it is not implicit. Record saves separately from in-memory
transform restoration, and do not claim persistent project rollback.

Acceptance requires independent review of each stage as MET, NOT MET, or NOT
TESTED, with the exact host/build/package identities. A negative result may be
accepted as a diagnostic result, but cannot support a compatibility claim.

## Session B Bounded reliability corrections

Session B requires accepted Session A evidence and a separate owner-authorized
file/test plan. An unexpected integration defect needs its own bounded amendment;
the words "fix integration" do not authorize an open-ended transport rewrite.

Proposed corrections are:

- Handle `ConnectionAbortedError` narrowly alongside the existing broken-pipe
  and reset cases during response-body writes/flushes. Test write and flush
  failures and a healthy response. Unrelated exceptions must still surface.
  A lost reply must remain UNKNOWN; this changes neither retry policy nor
  execution guarantees.
- Correct the complete dashboard/menu claims about any MCP-compatible agent,
  auto-connection, and running all registered tools. Describe configured access
  and local-only lifecycle exclusions; name a tested host/build only after
  accepted live evidence. Do not change layout or add capabilities.
- Align setup documentation with the tested client configuration and remaining
  evidence limits. Close the deferred `.MCP.json` case-variant test gap, preserving
  missing-Git and parent-repository protections. Make historical security tag
  wording range-specific and soften the remaining universal README claims.

Proposed maximum product scope is
`Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py`,
`Content/Python/UEFN_Toolbelt/dashboard_pyside6.py`,
`Content/Python/UEFN_Toolbelt/menu.py`, `tests/test_mcp_security.py`,
`tests/test_repo_integrity.py`, `README.md`, `SECURITY.md`,
`.claude/mcp_reference.md`, `docs/OFFICIAL_MCP_AND_TOOLBELT.md`, and a new
unreleased entry in `docs/CHANGELOG.md`. The owner-approved Session B plan must
narrow this list to files actually needed. Do not edit historical records or
the released 2.5.0 notes. No version change is proposed.

Run affected tests and static gates on final uncommitted content. Damage probes
must show the new tests catch the intended defects. Leave all work uncommitted
for independent review; apply only authorized corrections before Session C.

## Session C Live acceptance of the corrections

Before the Session C gate, determine whether the changed menu and its tooltip
can be observed on the actual build and resolve the acceptance plan with the
owner. The README records the menu as non-rendering; do not assume it is visible
on a later build. If unavailable, record its live wording inspection as NOT
TESTED, not a pass. Any alternate acceptance method requires an explicitly
owner-approved plan; this observation authorizes neither menu repair nor a
live-verification exemption.

After independent acceptance of Session B and separate owner authorization,
deploy exactly the reviewed content and fully restart UEFN. Repeat the short
Session A workflow through Claude Code, re-recording actual versions and file
identities. Inspect all changed dashboard wording and any visible changed menu
wording in the editor, preserving the unavailable-menu limit above.

Offline tests may force the disconnect exception; a healthy live request after
a disconnect is only live recovery evidence if that disconnect actually
occurred. Do not manufacture an editor stall or claim the exception branch was
tested live when only a unit test exercised it.

Run one complete offline suite on final product/test content, plus the required
static gates. Use actual Git checkout coverage for tracked-file tests; disclose
skips and platform differences. CI belongs to the exact commit it tested, not
future content. Any `Content/Python` commit follows the repository's accepted
live-verification rule and records its actual limits; this proposal grants no
exemption.

Deliver a concise redacted evidence ledger, raw evidence needed to support it,
and one checksum manifest. Separate offline checks, owner observations, actual
MCP-host calls, and CI. An accepted public summary may state only the tested
host/build, calls, and outcomes. It proves neither all 362 tools nor exactly-once
execution, and makes no Epic-versus-Toolbelt comparison.

## Process discipline and exclusions

Record setup time, owner interruptions, failed attempts, and test durations as
ordinary notes so the next process-improvement proposal has real bottlenecks.
Do not build another benchmark or expand this order into a checker/test-system
redesign. Reuse unchanged evidence only when its inputs are bound to the current
content; rerun the checks affected by an edit. Do not repeat full suites for
prose-only corrections without a concrete reason or stricter repository rule.

Keep one implementer and an independent reviewer per deliverable. Use the
existing mandatory gates, not extra rehearsal/review loops without a specific
risk they test. This is a proposed working discipline, not an adopted policy
amendment and not authority to omit existing gates.

Other tools, performance rankings, official-MCP integration, WO-006 resumption,
project recovery, modal detection, heartbeat, timeout redesign, automatic retries,
trust-boundary weakening, broad type-checking work, dependency upgrades, version
selection, tag/Release changes, metadata, social posting, and scratch cleanup
are excluded. A future process-speed pilot and broader tool coverage work need
separate proposals.

## Decision locks and next gate

The owner reserves proposal adoption and admission, issuance, session starts,
the client/project/fixture/target choices, live start, any unexpected repair,
recovery, exact commits, pushes, completion, and any later release decision.
Review acceptance never substitutes for these decisions.

NEXT GATE: the owner's individual approval of each call of the pinned
oversized-reply live proof, then an independent review of its redacted
evidence and a separate transition recording its result. The correction's own
commit and push, Session C, Session A acceptance, other product corrections,
recovery, cleanup, exact commits and pushes remain separate decisions. By
itself, this mandate grants no implementation, review, commit or push
authority.
