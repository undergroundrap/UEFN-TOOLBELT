# Current Work Order Gate

This file is the repository's sole authority pointer for current Work Order
state. Detailed mandates live under `docs/work-orders/`; their presence alone
never authorizes implementation.

- Current issued Work Order: WO-008
- Authorized session: A
- Base commit: `075ba2948444e40da9fb975f1cda4c29006b0169`
- Current gate: WO-008 SESSION A LIVE BASELINE ONLY — PRODUCT CORRECTIONS NOT AUTHORIZED
- WO-008 admission basis commit: `4ff86e8d1c9c89ebda597570ad4f757605ccd81e`
- WO-008 admission CI workflow: `37246398757`
- WO-008 admission CI job: `111565059168` — Lint, types, tests
- WO-008 issuance decision SHA-256: `5997654fb63b587ae72265d4382bf9f2f8a752e4fb09a6d79593a5b88725746a`
- WO-008 closed issuance commit: `0d1de9e6a1f49ea422cd7911d1c40d67787ddde4`
- WO-008 closed issuance CI workflow: `37359992194`
- WO-008 closed issuance CI job: `111931901481` — Lint, types, tests
- WO-008 Session A preparation decision SHA-256: `3f2218b675dc2257fffe3ea4e4ceb4e351a23bc651cfd53177fe7ef62882c9ed`
- WO-008 Session A preparation commit: `075ba2948444e40da9fb975f1cda4c29006b0169`
- WO-008 Session A preparation CI workflow: `37698808630`
- WO-008 Session A preparation CI job: `113057020206` — Lint, types, tests
- WO-008 Session A live baseline instruction SHA-256: `671d1dfe2c84922709366cf189c2576c8fc3ea96ddd2bc45e1346b9ce22925a9`
- Issuance commit: `c04e4a794f1e7d0c607c7ad712cbd28e86a55914`
- Issuance CI workflow: `37050236355`
- Issuance CI job: `110981533635` — Lint, types, tests
- Session A authorization commit: `c49905067e6c0d7038c467b3ae6f1116640a904a`
- Session A authorization CI workflow: `37091060115`
- Session A authorization CI job: `111111315920` — Lint, types, tests
- Completion basis commit: `e34e9fcdfb27ef7e443ae4e47799512d5c28489b`
- Completion basis CI workflow: `37137035181`
- Completion basis CI job: `111243552871` — Lint, types, tests
- Final audit commit: `066cf6d751740c0daaff165fc076be19e1b8e22d`
- Final audit CI workflow: `37142847095`
- Final audit CI job: `111260679508` — Lint, types, tests
- Audit recording commit: `fb7f9540464ac0898662087d4f70caa534de60d6`
- Audit recording CI workflow: `37149178090`
- Audit recording CI job: `111279224830` — Lint, types, tests
- Release preparation commit: `82f256da98dc606de9fcca19afd68de2c69a026d`
- Release preparation CI workflow: `37172802902`
- Release preparation CI job: `111349057775` — Lint, types, tests
- Audit recheck recording commit: `b305a1746c59637854a6877fe6196f17ec84e245`
- Audit recheck recording CI workflow: `37180447555`
- Audit recheck recording CI job: `111371778482` — Lint, types, tests
- Release conditions recording commit: `eabce22518d07725e05173aa707909023166a799`
- Release conditions recording CI workflow: `37186239025`
- Release conditions recording CI job: `111388630828` — Lint, types, tests
- Release train: WO-001 through WO-007
- Release gate: V2.5.0 TAG AND GITHUB RELEASE COMPLETED UNDER SEPARATE OWNER AUTHORIZATIONS — NO FURTHER TAG OR GITHUB RELEASE AUTHORIZED

[`WO-001-custom-mcp-security.md`](docs/work-orders/completed/WO-001-custom-mcp-security.md)
is completed as `ffcbe8b1bfa03cb37453b9beefda0bbdbe45543c` after
[CI workflow `32921154482`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32921154482)
passed.

[`WO-002`](docs/work-orders/completed/WO-002-epic-toolset-integration.md)
is completed. Session A was independently accepted, committed, and pushed as
`50b881716abea3b5838c2a971caac40ee4cd5d30`; [CI workflow
`32937631903`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32937631903)
completed successfully, including required job
[`98081919978` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32937631903/job/98081919978).
Session A is accepted and complete.

Session B was independently accepted and committed as
`c031f20e33c716ecc9f9ce546a7419b865ed8641`; [CI workflow
`33133090929`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33133090929)
completed successfully, including required job
[`98726805137` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/33133090929/job/98726805137).
External official-MCP exposure failed and was accepted as a terminal
negative result bounded by ToolsetPolicy. WO-002 is complete; no session
is authorized.

[`WO-003`](docs/work-orders/completed/WO-003-official-mcp-doc-convergence.md)
is completed. Its accepted planning baseline is
`e0b1063f5300404534c76789bdb6742f639425ba`; the accepted revision was
committed as `19350aa324bea4d88e494ee806801586a383d76e` after CI
workflow `33148089523` and required job `98773518991` passed.

Session A was independently accepted, committed, and pushed as
`d23add58e02ddc855573cf9be7a2542776d25e7e`; successful CI workflow
`33344006899` included successful required job `99344607213` (`Lint, types,
tests`). Accepted live `TOOL_TEST` evidence recorded a deploy and full UEFN
restart, 362 tools across 55 categories, corrected dashboard About ordering,
matching source and deployed runtime hashes, no Fortnite or play session and no
level mutation, then a stopped listener, closed UEFN, absent handoff, and closed
ports 8765–8770. At the Session A acceptance gate, Session A was accepted and
complete with no current implementation authority; Session B was not authorized
pending separate owner authorization.

Session B's repository-description draft was independently accepted. The
accepted draft was committed and pushed as
`e23baa40c4b9358eb6b4448f460c054650ae64f0`; successful CI workflow
`33476969423` included successful required job `99758148278` (`Lint, types,
tests`). At that gate the live GitHub repository description was still
unchanged, applying the exact accepted repository description was still a
separate owner-authorized external action, and metadata application was not
authorized. Tags, Releases, and social publication remain unauthorized, as do
Session C and WO-004.

The exact accepted repository description was applied to the live GitHub
repository under separate BDFL/owner authorization, at repository commit
`624ccc7f8f28cc897ec580c660607524ad5a4a3d`. The applied value is exactly
`UEFN Toolbelt: 362 Python automation tools across 55 categories, with a PySide6 dashboard and an experimental, authenticated same-user loopback bridge for local AI control. Complements Epic's official UEFN MCP; Toolbelt is not exposed through Epic's MCP server.`
Its character count is `261` and
its SHA-256 is
`a2d3b9a40e187c1fc4bce18666e3095687cc94b45d10ab27f1bee1e1e3417415`; a
read-only `gh repo view` read-back returned the applied value byte for byte.
The homepage `https://www.fortnite.com/@ohshh`, PUBLIC visibility, archived
state `false`, and all 20 repository topics are unchanged. No file, commit,
push, tag, Release, branch-protection setting, other repository metadata, or
social state changed. At that gate WO-003 remained issued, and its completion
transition required a separate owner gate.

WO-003 is completed as `7a7eedb493cbf810f758383a1fc66a285bca841a`; [CI workflow
`34301244038`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34301244038)
completed successfully, including required job
[`102308406590` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34301244038/job/102308406590).
The repository-description application record is preserved and still enforced
from the completed Work Order document. WO-003 is complete; no session is
authorized. Session C or any later session, tagging, Release creation,
branch-protection changes, other repository metadata changes, and social
publication all remain unauthorized.

[`WO-004`](docs/work-orders/completed/WO-004-modal-observability.md) is
completed. Its accepted planning baseline is
`0d513f1639cf197707132205f4074d0fe3a750cc`; the independently accepted
proposal was committed as `8444faf340afe47765c43d943200db712880817b`
after [CI workflow
`34441169191`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34441169191)
completed successfully, including required job
[`102756337393` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34441169191/job/102756337393).

At that gate, issuance gave no implementation authority and opened no
session. Session A feasibility work needed its own separate owner gate recorded
in this pointer, and Session B and Session C stayed closed behind it. Tagging,
Release creation, branch-protection changes, other repository metadata
changes, and social publication remained unauthorized, as did WO-005,
WO-006, and WO-007, which stayed proposed.

At the Session A authorization gate, this pointer opened read-only
feasibility planning only, on the basis of commit
`f9fc7268d63dad92f5dd009bbf20e11477b8f926`, successful CI workflow
`34509193110`, and successful required job `102978793893` (`Lint, types,
tests`). That gate covered source and documentation inspection and the
drafting of proposed probes, and it opened no live UEFN work. Live Probe A
ran later under a separate owner authorization and is recorded in Section 6
of the [Session A record](docs/audits/2026-09-10-wo004-session-a-modal-feasibility.md),
with preserved evidence under `docs/audits/evidence/wo004-probe-a/`. Probes
B and C were not run.

The owner accepted Session A's bounded findings. Session A is accepted as
`c4c21caa0960c430a4bcfb90cd65ef1edfc1a790`; [CI workflow
`34735715115`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34735715115)
completed successfully, including required job
[`103666661855` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/34735715115/job/103666661855).
Python post-tick callback silence was observed; its cause, any modal
diagnosis, and heartbeat reliability remain unproven. WO-004's remaining work
is narrowed to client timeout and error semantics, to direct loopback client
transport that bypasses HTTP proxies, and to no-automatic-retry guidance; modal
detection, heartbeat and status endpoints, and further feasibility probes are
deferred. The decision and the amended Session B and
Session C scope are recorded in the issued mandate. At that gate, Session B
implementation and Session C live testing were not authorized, and each
required a separate owner gate recorded here.

At the Session B authorization gate, this pointer opened client outcome
semantics only, on the basis of commit `da846ec36773d673ca9dcab3025ac36555579d0f`,
successful CI workflow `36375370541`, and successful required job
`108780005124` (`Lint, types, tests`). That gate covered the amended Session B
scope recorded in the issued mandate - client outcome classification and
wording, direct loopback transport for bridge requests, and no-automatic-retry
guidance - in `client.py`, `mcp_server.py`, `.claude/mcp_reference.md`, and
`tests/test_mcp_security.py` only, ending with that worktree uncommitted for
independent review. It opened no bridge change, deploy, UEFN launch, bridge startup,
MCP call, commit, or push, and Session C live testing was not authorized
at that gate.

At the Session C authorization gate, this pointer opened owner-operated live
acceptance only, on the basis of commit `17b5afe3f50bfa3ab882ff362a10eef70750c694`,
successful CI workflow `36385787242`, and successful required job
`108810759914` (`Lint, types, tests`). That CI ran on the base commit, which did
not contain the Session B implementation. At that gate the implementation was
uncommitted; it had been accepted on local checks and independent static review
only, and the mandate records its reviewed file identities. That gate covered
the owner-operated live acceptance procedure in the mandate, including its
runtime and updated-editor prerequisites, against exactly that uncommitted
implementation. It changed no implementation file and opened no commit or push.

WO-004 is completed as `b4fa0a5245944fd992b6a2b52dbac1e59de242ae`; [CI workflow
`36494750779`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36494750779)
completed successfully, including required job
[`109171582586` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36494750779/job/109171582586).
That commit carries the independently accepted client implementation, the
Session C authorization transition, and the independently accepted [Session C
live-acceptance record](docs/audits/2026-09-28-wo004-session-c-live-acceptance.md)
with its evidence. Completion accepts the narrowed client-outcome work only; it
claims no modal detection, exactly-once execution, MCP-host integration, or
bridge exception fix. WO-004 is complete; no session is authorized. WO-006 and
WO-007 stayed proposed. Any later session, tagging, Release creation,
branch-protection changes, other repository metadata changes, and social
publication all remain unauthorized.

[`WO-005`](docs/work-orders/completed/WO-005-coverage-source-of-truth.md) is
completed. Its planning baseline is `1925ba8a09c3696d25de7ffc3f23caf970362c4d`;
the independently accepted proposal was committed as
`528f1962c0c45c0631bab3637f3fd40db6317027` after [CI workflow
`36529997892`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36529997892)
completed successfully, including required job
[`109281301869` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36529997892/job/109281301869).

At its issuance gate, WO-005 gave no implementation authority and opened no
session. Session A needed its own separate owner gate recorded in this
pointer, and the live-verification exemption proposed for it was not accepted
at that gate.

At the Session A authorization gate, this pointer opened the offline coverage
model only, on the basis of commit `867074f8a520450ef6073b4c922079a897a83886`,
successful CI workflow `36596756689`, and successful required job
`109503539592` (`Lint, types, tests`). That gate covered the Session A scope
recorded in the mandate, unchanged, and ended with that worktree uncommitted
for independent review. The owner accepted the proposed live-verification
exemption for that offline scope only, on the terms recorded in the mandate;
it gave no commit, push, deploy, or live-run permission. That gate opened no
deploy, UEFN launch, bridge startup, MCP call, commit, or push.

WO-005 is completed as `5ef3aef2934b33a357ab9114e68aae41bc78639c`; [CI workflow
`36662471593`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36662471593)
completed successfully, including required job
[`109719997181` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36662471593/job/109719997181).
That commit carries the independently accepted Session A implementation: the
registry-derived coverage report with its explicit evidence mappings and
tests, the generated `TOOL_STATUS.md` block with the named corrections, the
shared registry enumerator behind `drift_check`, and the `list_untested.py`
migration shim. Source categories describe what test code is written to
check; they establish no live verification of any tool. WO-005 is complete;
no session is authorized. WO-006 and WO-007 stayed proposed, and the optional
integration run stayed deferred. Any later session, tagging, Release creation,
branch-protection changes, other repository metadata changes, and social
publication all remain unauthorized.

[`WO-006`](docs/work-orders/superseded/WO-006-official-vs-toolbelt-benchmark.md) is
superseded. Its planning baseline is `f9354feaf4ab072c9941ab4d6ec8337395ce18a0`;
the independently accepted proposal was committed as
`0c0bf26191ee953c7a27237109b4a91a4db97275` after [CI workflow
`36743995194`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36743995194)
completed successfully, including required job
[`109985389182` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/36743995194/job/109985389182).

At its issuance gate, WO-006 gave no implementation authority and opened no
session. Session A, the offline design and harness, needed its own separate
owner gate recorded in this pointer, and Session B, the owner-operated live
measurement, stayed closed behind it.

At the Session A authorization gate, this pointer opened the offline design and
harness only, on the basis of commit `d46a30ed9de54ec01536d132e1032fcf762fa3c7`,
successful CI workflow `36756889729`, and successful required job
`110029304446` (`Lint, types, tests`). That evidence established the issued
mandate, not any harness implementation or test result. That gate covered the
Session A scope recorded in the issued mandate, unchanged, changed no
repository file, and ended with its private artifacts held for independent
review. It opened no deploy, UEFN launch, bridge startup, MCP call, connection
to a real editor endpoint, live measurement, commit, or push, and Session B
stayed closed at that gate.

The owner accepted Session A's private offline artifacts after independent
review, as offline preparation only and not as proof of live compatibility.
The accepted harness package and its preserved independent review are kept in
the owner's private evidence folder, identified by their `SHA256SUMS` digests
`f17a44a477b2fb2d3d347a75232c7076516ce110308aeb25c0efefad90dff3f8` and
`a856bdfff88565831905b0e1fcd77862e408b0eb704774ac1631da9225ac94c1`. The
harness and its stub tests ran offline on the owner's Windows machine only;
they have never run in GitHub CI, and no repository commit or CI run attests
to them. Session A is accepted and closed.

At the Session B authorization gate, this pointer opened owner-operated live
measurement only, on the basis of commit
`8667b0e0ef78d504586d710984ef1a1fef7263b2`, successful CI workflow
`36801338578`, and successful required job `110176132684` (`Lint, types,
tests`). That CI tested the repository's checker and tests, not the private
harness, and established no live result. That gate covered the Session B scope
recorded in the issued mandate, unchanged: the owner operated UEFN and
performed the owner checks, and the accepted harness ran only after the
owner's separate, explicit instruction to begin the live run. It changed no
repository file and ended with its private artifacts held for independent
review. It opened no code change, fallback, emulation, policy change, live
repair, commit, or push, and the evidence-recording transition and WO-006
completion stayed closed at that gate. Tagging, Release creation,
branch-protection changes, other repository metadata changes, and social
publication all remain unauthorized, and WO-007 stayed proposed at that gate.

[`WO-006`](docs/work-orders/superseded/WO-006-official-vs-toolbelt-benchmark.md)
is superseded. It closed without an accepted measurement under the owner's
closure decision recorded in its mandate, which keeps its unmet requirements.
WO-006 cannot be resumed or completed, and no session is authorized. WO-007
stayed proposed at that gate.

WO-006 was superseded as `5d88a4ee56309df43537d289514a150615dfeba6`; [CI
workflow `37037329967`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37037329967)
completed successfully, including required job
[`110938646551` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37037329967/job/110938646551).
Its closure basis was commit `13e0bbb67f98ac3f33aff917737fcf9b77a3d64c`,
successful CI workflow `36817435116`, and successful required job
`110225453445` (`Lint, types, tests`).

[`WO-007`](docs/work-orders/completed/WO-007-public-mcp-explainer.md) is completed.
Its planning baseline is `5d88a4ee56309df43537d289514a150615dfeba6`; the
independently accepted proposal was committed as
`c04e4a794f1e7d0c607c7ad712cbd28e86a55914` after [CI workflow
`37050236355`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37050236355)
completed successfully, including required job
[`110981533635` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37050236355/job/110981533635).

At its issuance gate, WO-007 gave no implementation authority and opened no
session. Session A, the repository explainer and draft variants, needed its
own separate owner gate recorded in this pointer, and its proposed
live-verification exemption remained pending the owner's decision at that
gate.

At the Session A authorization gate, this pointer opened the repository
explainer and the two private drafts only, on the basis of commit
`c49905067e6c0d7038c467b3ae6f1116640a904a`, successful CI workflow
`37091060115`, and successful required job `111111315920` (`Lint, types,
tests`). That evidence was CI on the issuance commit; it established the issued
mandate, not any Session A output. That gate covered the Session A scope
recorded in the mandate, unchanged, and ended with its three repository paths
uncommitted and its two private drafts held for independent review. The owner
accepted the proposed live-verification exemption for exactly that scope, with
offline verification only, on the terms recorded in the mandate; it accepted
no publication, runtime change, or live activity. That gate opened no
publication, deploy, UEFN launch, bridge startup, MCP call, benchmark, commit,
or push.

WO-007 is completed as `e34e9fcdfb27ef7e443ae4e47799512d5c28489b`; [CI workflow
`37137035181`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37137035181)
completed successfully, including required job
[`111243552871` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37137035181/job/111243552871).
That commit carries the independently accepted Session A repository output:
the explainer `docs/OFFICIAL_MCP_AND_TOOLBELT.md`, its drift scan-target
entry, and the matching test entry. The two accepted drafts stay private;
their counts and SHA-256 identities are recorded in the completed mandate.
Completion accepts no benchmark result, performance comparison, version
choice, or publication, and approves publishing neither draft. WO-007 is
complete; no session is authorized. With WO-007 completed and WO-006
superseded, the frozen train meets the completion condition of the
release-train amendment below. The final integration/repository-truth audit,
version selection, tagging, Release creation, branch-protection changes, other
repository metadata changes, and social publication all remained unauthorized
at that gate.

WO-001 through WO-007 form the frozen next release train. The owner selected
release version 2.5.0, recorded in the release preparation record below. No tag
or GitHub Release is authorized until the frozen train is complete, a final
integration/repository-truth audit passes, and the owner separately authorizes
a release session. New proposals default to the following release train unless
the owner explicitly classifies one as a blocker.

Release-train amendment (owner decision): the frozen train remains WO-001
through WO-007. WO-006 is closed as superseded without an accepted
measurement. It is resolved for this train, not completed, and its unmet
requirements stay recorded in its mandate. For the release gate above, the
frozen train is complete when WO-001 through WO-005 and WO-007 are completed
and WO-006 remains superseded. This amendment opens no session and grants
nothing: WO-007 is completed with no session authorized, and the final
integration/repository-truth audit and a separate owner decision on any
release remained required at that gate.

Final integration/repository-truth audit record: under a separate owner
authorization for a read-only audit only, which opened no implementation
session and no release authority, an independent auditor audited commit
`066cf6d751740c0daaff165fc076be19e1b8e22d`; [CI workflow
`37142847095`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37142847095)
completed successfully on that commit, including required job
[`111260679508` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37142847095/job/111260679508).
The audit changed no repository file and ran no UEFN, deploy, endpoint
contact, or benchmark. Its verdict is ACCEPT WITH REQUIRED FIX. The private
audit report is identified by its SHA-256
`aed10f85280517a6916398cff384562e2af6fb75d5a0896be7985b01204288f3` and its private logs
by their manifest digest
`88dc0e5bb7c3d246f3fdb03ef05c0ba549805f3012d926feef356f63e3c933b9`.

At that gate, two required fixes were outstanding. P1-1: public and agent pages
claimed MCP-host compatibility that no accepted record supports. P1-2: public
and agent pages presented the smoke test's registration checks as tool
execution or schema validation. At that gate, the final audit had not passed
the release gate. The `.mcp.json` fresh-clone documentation defect remained
queued for
correction with them. The version choice, the checker's handling of historical
version lines, the pinned-port configuration, the agent settings, the privacy
finding, and the disclosure of the security fix remained open owner decisions;
that record neither accepted nor waived any of them. Release preparation, any
version bump, tagging, Release creation, branch-protection changes, other
repository metadata changes, and social publication all remained unauthorized
at that gate.

Release preparation record: under a separate owner authorization for one
bounded release-preparation session, which opened no review, commit, push, tag,
Release, or publication authority, the repository was prepared on base commit
`fb7f9540464ac0898662087d4f70caa534de60d6`; [CI workflow
`37149178090`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37149178090)
completed successfully on that commit, including required job
[`111279224830` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37149178090/job/111279224830).
The owner adopted version 2.5.0, with an explicit read-before-upgrading section
and no backward-compatibility claim; MCP-host claims limited to the evidence,
so integration after the hardening is stated as untested; the smoke test
described as registration and module-loading checks that execute no tool and
validate no schema; fresh-clone setup through a local, gitignored `.mcp.json`
copied from `.mcp.json.template`; no pinned port in that template;
`enableAllProjectMcpServers`, `Bash(python -c *)`, and `Bash(find*)` removed
from the shared agent settings; the profile path in `docs/UEFN_QUIRKS.md`
redacted, with completed mandates and Git history unchanged; disclosure of the
released unauthenticated `execute_python` issue and of the proxy and redirect
bearer leak on unreleased `main`, without exploit detail or a GitHub advisory;
the checker's historical-version exemption limited to exact lines; and an
offline live-verification exemption for this preparation change, whose only
`Content/Python` edit is `__version__` and which supplies no live verification.
The private authorization is identified by its SHA-256
`aa6f386781c9db3d11ae54012aaef2184ca985edc876cf25ae4d95b880f2f40a`. At that
gate, the final audit had not passed the release gate; passing it required an
independent recheck of the required fixes and the affected changes, which that
authorization did not open. Tagging, Release creation, branch-protection
changes, other repository metadata changes, and draft or social publication all
remained unauthorized at that gate.

Final audit recheck record: under separate owner authorizations, an independent
reviewer that authored none of the release preparation reviewed it against the
final audit's required fixes and returned ACCEPT WITH REQUIRED FIX; after a
bounded correction, its scoped re-review of that correction returned ACCEPT,
and the owner accepted that review. The accepted content is committed as
`82f256da98dc606de9fcca19afd68de2c69a026d`; [CI workflow
`37172802902`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37172802902)
completed successfully on that commit, including required job
[`111349057775` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37172802902/job/111349057775),
which logged 2529 passed and 14 skipped on Linux. Within the accepted scope,
P1-1, P1-2, and the queued `.mcp.json` fresh-clone documentation defect are
resolved. The original audit record above keeps its verdict, ACCEPT WITH
REQUIRED FIX, as history; this record is a separate follow-up acceptance, not a
rewritten pass. The private review reports are identified by their SHA-256
`4ecc6fd0284c1bfb9a1461b11355904615f49852219c87b29474f5a288e10b00` and
`9e848b0fe84bc002689548db6cbde834fded5574eb94b7a2370a5227b860a642`, and their
private logs by their manifest digests
`7da7879c48f5b2f7577f10c52f461cf7d6c029055f8a35838e765bd570c22b69` and
`1ca8d489fee0b1481c1986a21e134cf61742eadd1fb506054179d4e58cca72da`. The
dashboard and menu runtime wording about MCP-compatible clients, and the
limitations the release notes defer, are disclosed; this record neither fixes
nor waives them. This acceptance supplies no live UEFN, MCP-host, or
effective-permissions evidence. Tagging, Release creation, branch-protection
changes, other repository metadata changes, and draft or social publication all
remain unauthorized.

Release conditions record: the owner accepted that the original final
integration/repository-truth audit, together with the accepted corrective
recheck and green CI, satisfies the frozen train's audit condition; this does
not rewrite the original verdict, ACCEPT WITH REQUIRED FIX, which the audit
record above keeps as history with its evidence identities and digests. The
recheck recording is committed as `b305a1746c59637854a6877fe6196f17ec84e245`;
[CI workflow
`37180447555`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37180447555)
completed successfully on that commit, including required job
[`111371778482` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37180447555/job/111371778482).
The frozen train, WO-001 through WO-007, meets its completion condition: WO-001
through WO-005 and WO-007 are completed, and WO-006 remains superseded with no
accepted benchmark. Its audit condition is satisfied. Version 2.5.0 and the
accepted release-preparation content committed as
`82f256da98dc606de9fcca19afd68de2c69a026d` are unchanged. The owner deferred
the nonblocking review advisories to post-release hygiene: the `.MCP.json` case
variant in the tracked-configuration test, the incomplete dashboard quotation
in the known issues, the historical-tag wording in `SECURITY.md`, and the
residual README intent wording (review item P2-7); they remain open, neither
fixed nor waived. The owner's instruction is identified by its SHA-256
`e7083af5399b4c0e0196e4cf481ab85e90d42c8b93905f15d78b59ea77c8a416`. Tagging,
GitHub Release creation, branch-protection changes, other repository metadata
changes, and draft or social publication each still required a separate owner
execution authorization at that gate, and that record gave none.

Release publication record: under separate owner authorizations given after the
conditions record, the annotated tag `v2.5.0`, tag object
`39afcab4d2f3a8ae3af58fdbd01312c7ec05c93a`, was created on commit
`eabce22518d07725e05173aa707909023166a799` and pushed; [CI workflow
`37186239025`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37186239025)
completed successfully on that commit, including required job
[`111388630828` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37186239025/job/111388630828).
GitHub Release `402913965`, titled "UEFN Toolbelt v2.5.0", was then published
from that tag at 2026-10-04T08:10:21Z, not as a prerelease, and marked Latest.
Its body is the 2.5.0 section of `docs/CHANGELOG.md` at the tag, with only the
`SECURITY.md` link made absolute, and is identified by its SHA-256
`6c1234865662798fdf13eb3f72449565264545b690c6218bc549a794a6e1eb4a`. Statements
in the earlier records above that tagging or Release creation remain
unauthorized describe their own gates; only those separate owner authorizations
changed that, for v2.5.0 alone. This record is a post-release change and is not
part of the tagged package; `v2.5.0` and every earlier tag stay where they are.
The owner's instruction is identified by its SHA-256
`aadad5fbeccd0f656dfba476cf035e7cf4aba24324ae93ab47c0ab396168920a`. No further
tagging or GitHub Release creation follows from this record. Social
publication, private-draft publication, and scratch cleanup remain separately
gated, and the deferred review advisories remain open. The next Work Order
awaits a separate owner decision, and no implementation follows from this
record.

WO-008 closed issuance record: the owner adopted the accepted
issuance/session-enforcement plan r2 and authorized only its seven-path
closed-issuance implementation under an offline-verification exemption for
this governance scope. The instruction is identified by SHA-256
`5997654fb63b587ae72265d4382bf9f2f8a752e4fb09a6d79593a5b88725746a`.
[`WO-008-user-reliability-and-mcp-client-acceptance.md`](docs/work-orders/issued/WO-008-user-reliability-and-mcp-client-acceptance.md)
was issued outside the frozen train with session NONE. Admission CI workflow
`37246398757` and job `111565059168` succeeded on
`4ff86e8d1c9c89ebda597570ad4f757605ccd81e`; they cover admission only,
not this transition, Session A outputs, a live build or MCP-host acceptance.
At that gate, Session A offline preparation, live start, Session B and
Session C remained unauthorized. Runtime or live need stops this transition. Configuration
changes, installations, recovery, exact commits, pushes, cleanup, further
tags or Releases, metadata and publication remain separately gated.
This record grants none of those authorities.

WO-008 Session A offline preparation record: the owner authorized Session A
for offline preparation only, on the basis of the closed issuance committed as
`0d1de9e6a1f49ea422cd7911d1c40d67787ddde4`; [CI workflow
`37359992194`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37359992194)
completed successfully on that commit, including required job
[`111931901481` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37359992194/job/111931901481).
That CI tested the closed issuance enforcement, not this transition, a
Session A output, an MCP host or a live build. The instruction is identified
by SHA-256 `3f2218b675dc2257fffe3ea4e4ceb4e351a23bc651cfd53177fe7ef62882c9ed`.
Preparation produced only a redacted exact call plan and a fixture/setup
checklist, outside the checkout, for independent review, and changed no
repository file. At that gate, client launch, configuration reads or changes, dependency
installation, deploy, editor contact, bridge lifecycle, endpoint calls,
fixture mutation, product changes, recovery, commits and pushes remained
unauthorized. Live start needed an accepted call plan and a separate owner
live-start instruction recorded here. Session B and Session C remain
unauthorized, and this record grants no further authority.

WO-008 Session A live baseline record: the owner authorized Session A for the
pinned live baseline only, on the basis of the offline preparation committed
as `075ba2948444e40da9fb975f1cda4c29006b0169`; [CI workflow
`37698808630`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37698808630)
completed successfully on that commit, including required job
[`113057020206` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/37698808630/job/113057020206).
That CI tested the offline-preparation enforcement, not this transition, a
live result, an MCP host or a live build. The accepted preparation package
is identified by SHA256SUMS `8df8abdb4d70882f4ee0d1129907b166fa44f1ffbf87361ca3586d565d261ed1`,
its review by SHA256SUMS `517b9c15744ee26e4c5967ff00eb9a4476330b723e878eb11902fc9d84e0351a`,
and the accepted plan for this transition by SHA256SUMS
`8e2d7481e4b245ed5e5afb132b9545d3754108907b1c16beb8c64fe3ad8a9add`. The instruction is
identified by SHA-256 `671d1dfe2c84922709366cf189c2576c8fc3ea96ddd2bc45e1346b9ce22925a9`.
Session A may run at most once: one attempt of the accepted call plan, as
amended by the accepted execution addendum, through Claude Code with the
owner decisions that instruction records, deployed from the clean,
synchronized commit that carries this record once that commit's own CI has
succeeded. Independent review, the commit, the push and that CI are
preconditions only; none of them authorizes or starts the run. Any stop
after live-run setup begins ends the attempt. A retry or repeat run needs a
new reviewed transition recorded here, and recovery needs a separately
bounded owner instruction. A choice or setup item that instruction omits
follows the accepted addendum's missing-choice rule. Product corrections,
installations or configuration changes that instruction does not name,
commits and pushes remain unauthorized. Session B and Session C remain
unauthorized, results are recorded only by a separate transition, and this
record grants no further authority.
