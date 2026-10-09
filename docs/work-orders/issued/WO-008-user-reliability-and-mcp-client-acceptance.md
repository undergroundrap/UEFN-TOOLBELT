# WO-008 User reliability and MCP client acceptance

STATUS: ISSUED
AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR THE PINNED LIVE BASELINE ONLY
Owner: Ocean Bennett
Priority: user-facing reliability and missing integration evidence
Draft date: 2026-10-04
Revision: r2
Planning baseline: `9879d39fbdb58083a0f7229a9c9c90c7d6fb375f`

This is an issued following-train Work Order, outside the frozen
WO-001 through WO-007 train. The root pointer identifies WO-008 with
Session A authorized for the pinned live baseline only. Product
corrections, Session B and Session C remain unauthorized.

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
closed issuance and Session A offline preparation, and a separate transition
installs the pinned Session A live baseline only. Recording the result,
product corrections and live acceptance still need separately reviewed
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

NEXT GATE: separate owner decisions on an independent review of the redacted
Session A live evidence, and then on a transition recording its result.
Product corrections, Session B, Session C, recovery, a repeat run, exact
commits and pushes remain separate decisions. This mandate grants no review,
implementation, commit or push authority.
