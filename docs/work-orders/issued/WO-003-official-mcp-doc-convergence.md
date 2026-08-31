# WO-003 — Official UEFN MCP Documentation Convergence

STATUS: ISSUED

AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION

OWNER: Ocean Bennett

PRIORITY: P1

BASELINE: `e0b1063f5300404534c76789bdb6742f639425ba`

ISSUANCE_COMMIT: `19350aa324bea4d88e494ee806801586a383d76e`

ISSUANCE_CI_WORKFLOW: `33148089523`

ISSUANCE_CI_JOB: `98773518991` — Lint, types, tests

SESSION_A_AUTHORIZATION_COMMIT: `52d89295614a4ce686094736d87f7e6c907e12a0`

SESSION_A_AUTHORIZATION_CI_WORKFLOW: `33200547479`

SESSION_A_AUTHORIZATION_CI_JOB: `98948639416` — Lint, types, tests

## Issuance basis

The independently accepted revision of this mandate was committed as
`19350aa324bea4d88e494ee806801586a383d76e`; successful CI workflow
`33148089523` included successful required job `98773518991` (`Lint, types,
tests`).

Issuance alone grants no implementation authority. A session becomes
implementable only when the owner names it in root `WORKORDER.md`; the
Session A authorization recorded below came from that pointer, not from
issuance. Session B is not authorized and requires a separate owner gate.
The planning baseline above is preserved unchanged; it records the state
this mandate was planned against, not the issuance point.

## Session A authorization basis

Session A is authorized for implementation under the current root
`WORKORDER.md` gate alone. The recorded basis is commit
`52d89295614a4ce686094736d87f7e6c907e12a0`, successful CI workflow
`33200547479`, and successful required job `98948639416`
(`Lint, types, tests`).

The accepted mandate below is unchanged. Session A implements exactly the
scope it defines. Session B is not authorized and requires a separate owner gate.

## Planning basis

This proposal is planned against the green repository state at
`e0b1063f5300404534c76789bdb6742f639425ba`, where CI workflow `33143519105`
completed successfully including required job `98759451491` (`Lint, types,
tests`).

Accepted prior results this mandate builds on:

- WO-001 closed the custom bridge security work: the listener authenticates
  same-user loopback clients, rotates a session secret, rejects browser
  origins, and fails closed.
- WO-002 Session A corrected Toolbelt's internal contract and truth surfaces
  and was accepted at `50b881716abea3b5838c2a971caac40ee4cd5d30`.
- WO-002 Session B produced the sanitized external-proof artifact
  `docs/audits/evidence/2026-08-27-wo002-session-b-official-mcp.json`, accepted
  at `c031f20e33c716ecc9f9ce546a7419b865ed8641`.
- Commit `e0b1063` repaired declared-drift-target enforcement: a declared entry
  in the drift scanner's file inventory that no longer exists now raises a
  dedicated `missing scan target` finding instead of being silently skipped.

### Terminal WO-002 result, recorded exactly

- Toolbelt's in-process registration record and its internal list, describe,
  and run meta-tool contracts work, verified before, during, and after the
  official probe sequence.
- `UEFN_Toolbelt` was **not** externally listable, describable, or callable
  through Epic's official MCP server.
- The accepted external result is `failed`, bounded by
  `UE::ValkyrieToolset::ToolsetPolicy`, which Epic's own installed Valkyrie
  registration source names as the sole owner of the creator-facing surface.
- In-process registration success, `_REGISTERED` state, or internal meta-tool
  success never proves external exposure. These are separate facts.

## Locked truth model — four distinct surfaces

Every affected document must name which of these it means. Ambiguous phrases
such as "the MCP", "MCP integration", "our MCP server", or "available to any
client" are prohibited wherever they could span more than one surface.

| # | Surface | What it is | Accepted state |
|---|---|---|---|
| 1 | Epic built-in official UEFN MCP toolsets | Epic's own toolsets reached through Epic's official MCP server | Shipped and available in 42.00; observed Beta Access qualification and accepted live gaps below |
| 2 | Toolbelt internal in-process registry and meta-tools | `epic_toolset` registration plus `toolbelt_list_tools`, `toolbelt_describe_tool`, `toolbelt_run_tool` | Working, in-process only |
| 3 | Toolbelt custom bridge | Toolbelt's own authenticated same-user loopback HTTP listener | Working; experimental, authenticated, same-user, loopback |
| 4 | Toolbelt external exposure through Epic's official MCP | Whether surface 2 is reachable from an official MCP client | `failed`, bounded by `ToolsetPolicy` |

Surface 2 succeeding says nothing about surface 4. That inference is the exact
error this mandate exists to remove from the documentation.

## Evidence qualifications to preserve

- Epic's 42.00 ecosystem release notes state that Unreal MCP is available and
  ships in 42.00, covering writing and compiling Verse, placing and
  configuring devices, creating Scene Graph entities, building UI with UMG,
  and running play sessions. Epic does **not** state that it left beta or
  experimental status, and the same notes name other features explicitly
  when those leave Experimental. No document may claim it exited beta.
- Locally accepted evidence still places `UEFN MCP Toolsets` under Beta
  Access (`docs/UEFN_QUIRKS.md`, Quirk #36). That qualification is preserved.
- "Available" is not "flawless". The accepted audit recorded live gaps on
  the official surface: a stock-device type mismatch, inability to delete a
  created root entity, and false no-client-log reporting during a live
  session, plus a Save Content modal that blocked a queued official call for
  roughly four minutes. These carry forward; no document may describe the
  official surface as simply "working".
- Epic's UEFN MCP documentation page describes Verse file read/write/compile,
  Scene Graph entity creation, Creative device catalog browsing and editable
  property configuration, and play-session launch, termination, and inspection operations. It does not
  headline UMG on that page. Session A must not resolve this by silently
  picking one source; it must cite the source it relies on for each claim.
- Epic documents server startup as an Editor Preferences setting under Model
  Context Protocol (`Auto Start Server`) or the console command
  `ModelContextProtocol.StartServer`, binding by default to
  `http://127.0.0.1:8000/mcp`. This is Epic's server lifecycle and is a
  separate matter from Quirk #36.
- Epic documents two current limitations: a coordinate-system mismatch between
  Python toolsets (XYZ) and UEFN's Left-Up-Forward convention, and editor
  hitching during MCP tool calls.
- The accepted audit recorded 29 official toolsets, with signature counts of
  10 Verse, 9 Device, 13 Entity, 21 UMG, and 8 Session operations.
- Verse, Device, Entity, and Session surfaces carry bounded live evidence.
  **UMG remains signature-only evidence** and must be labelled as such even
  though Epic's release notes list it as a capability.
- The custom bridge is experimental, authenticated, same-user, loopback-bound.
  It is not universally offline, not a security sandbox, and does not offer
  arbitrary remote Python.
- Audit timings are individual observations from one environment, never
  benchmark evidence.

## Session A — repository documentation truth convergence

### Claim disposition inventory

Every row below was confirmed by source inspection at the planning baseline.
These are the anticipated writable paths; the inventory is closed, not
open-ended.

| Path | Stale or contradictory claim | Evidence or source | Required disposition | Later-order boundary |
|---|---|---|---|---|
| `CLAUDE.md` (~217) | "~97% of the UEFN Python API surface… remaining 3% is locked by Epic", listing Verse compiler trigger, match control, session launch/stop | Epic 42.00 release notes; UEFN MCP doc page | Scope the limit to the legacy in-editor `unreal` Python surface, and state that Epic's official MCP provides Verse compilation and session control on surface 1 | — |
| `CLAUDE.md` (~409) | "KNOWN HARD LIMITS (Epic must unlock)" pipeline block naming Verse compiler trigger and session launch/stop | Same | Same scoping; retain the genuine Python-API limits and drop the ones official MCP now covers | — |
| `CLAUDE.md` (~220) | "A persistent top-menu entry (`Toolbelt ▾`) in the UEFN editor bar" | Live editor log: `MainFrame.MainTabMenu is not registered on this build`; README release history already records the retraction | Remove the persistent-menu claim; direct readers to `tb.launch_qt()` | — |
| `llms.txt` (5) | "an editor top-menu integration" | Same | Same correction | — |
| `llms.txt` (6–7) | "Any MCP-compatible AI can control UEFN through the configured authenticated, same-user local bridge" | Surface model rows 3 and 4 | Keep the authentication wording, name surface 3 explicitly, and state that this is not Epic's official MCP surface | — |
| `llms.txt` (11–13) | "~97%… remaining 3% is locked by Epic" list | Epic sources | Same scoping as `CLAUDE.md` | — |
| `AGENTS.md` (7–9) | "MCP HTTP bridge" and "Any MCP-compatible AI connects via `.mcp.json`" without naming the surface | Surface model | Name surface 3, state the authenticated same-user loopback boundary | — |
| `README.md` (~323, ~2002) | Top-menu dropdown described as a working entry point | Live editor log | Correct to the dashboard entry point | — |
| `README.md` (~2216) | "You **never need to restart UEFN** when developing for the Toolbelt" | Quirk #26, #27, #36; `CLAUDE.md` test matrix requiring full restarts | Replace the absolute with the real rule: hot reload covers most tool edits; dashboard, Qt-window, `init_unreal.py`, and new-module changes need a restart. No new absolute in either direction | — |
| `README.md` (~218–225) | Safety table claiming "No network calls — Zero outbound HTTP/socket connections anywhere in the codebase" and "No eval/exec on external input" | `SECURITY.md` (~57–59) states Toolbelt must not be described as universally offline; Plugin Hub fetches a remote registry; `import_image_from_url` fetches URLs; the plugin loader executes plugin files | Replace both rows with accurate, bounded statements consistent with `SECURITY.md` | — |
| `SECURITY.md` (~51–52) | Official Epic MCP described as "a separate experimental Epic control plane" | Epic 42.00 notes state it is available and ships in 42.00; Quirk #36 records the Beta Access setting | State that it is shipped and available in 42.00 while preserving the observed Beta Access qualification. Do not assert it left beta. Keep the experimental wording where it correctly describes surface 3 | — |
| `TOOL_STATUS.md` (14) | "**Twelve tools are non-functional on 42.00**" | The table immediately below lists thirteen entries (8 geometry, 2 blueprint, 1 input, 1 system, 1 alignment) | Reconcile the count to the listed entries, or the entries to the count, from the table itself | — |
| `TOOL_STATUS.md` (45–60) | Headline "187 / 362 Tools (52% Coverage)" sitting beside "190 checks, 163 verified, 27 execution-only" | Accepted audit coverage reconciliation | Use the accepted labels verbatim: 362 runtime registry (authoritative registered universe); 356 `list_untested` discovery; 191 lexically referenced entries; 187 curated `TOOL_STATUS` unique-entry claim; 190 integration checks comprising 163 outcome-verified and 27 execution-only. 187 is **not** a registration count | WO-005 owns the authoritative model; WO-003 must not build it |
| `ROADMAP.md` (~41–43) | Phase 23 "Long-running tools… run in background" | Main-thread constraint in `CLAUDE.md` and Quirk #2 | State that worker threads may perform non-`unreal` work while every `unreal.*` call stays on the editor main thread | — |
| `ROADMAP.md` (phase headings) | Phase state predating WO-001/WO-002 completion | Completed Work Orders | Refresh phase status to current fact only | — |
| `docs/PIPELINE.md` (~396) | `system_build_verse` "Waiting for Epic Python compiler API" | Epic sources; surface model | Distinguish "no in-editor Python API" from "available on surface 1" | — |
| `docs/AI_AUTONOMY.md` (~299) | "Cannot trigger Verse compiler from Python — Epic has not exposed a `BuildVerseCode` Python API" | Same | Same distinction | — |
| `docs/uefn_python_capabilities.md` | Capability limits stated without naming the surface | Surface model | Add surface labels; correct any limit that official MCP now covers | — |
| `docs/UEFN_QUIRKS.md` | Quirk #36 and Quirk #42 must survive intact | WO-002 accepted live evidence and the accepted 42.00 audit | **Preserve.** Quirk #36's manual recovery (`import UEFN_Toolbelt as tb; tb.register()`) and Quirk #42's zero-project-Python launch rule with `prepare_launch.bat` / `restore_after_launch.bat` are accepted evidence and must not be softened by Epic's separate auto-start behaviour | — |
| `docs/plugin_dev_guide.md` (~84) | "You don't even need to restart!" | Quirk #26/#27 | Bound the claim to the plugin-reload case it actually covers | — |
| `.claude/mcp_reference.md` | Bridge described without consistent surface labels | Surface model | Add surface labels | — |
| `.claude/tool_tables.md` (~835) | `epic_mcp_register` described as "external exposure remains unproven" | WO-002 accepted `failed` | Change `unproven` to the accepted `failed` result, bounded by `ToolsetPolicy` | — |
| `install.py` (~15, ~297) | Two menu promises: "The Toolbelt menu appears automatically" in the module header and the post-install step "appears in the top menu bar automatically" | Live editor log; README release history | Correct both to the dashboard entry point. See the runtime-text lock for the required end-to-end run | — |
| `ARCHITECTURE.md` (~13, ~30) | Surface table listing "Editor menu — `Toolbelt ▾` (top bar)" as a working entry point, and the directory map describing `menu.py` as building a functioning top-bar menu | Same | Mark both unavailable on this build; `menu.py` registers but never renders | — |
| `ARCHITECTURE.md` (~15) | "MCP HTTP bridge … any MCP client controls UEFN" | Surface model rows 3 and 4 | Name surface 3 and its authenticated same-user loopback boundary | — |
| `README.md` (~39, ~142, ~1429, ~1432, ~1468, ~1970, ~2002) | Seven further menu claims: "a single persistent menu entry", "use the `Toolbelt` menu", "Menu registered — look for 'Toolbelt' in the top menu bar", "A **Toolbelt** menu now appears in the top menu bar next to Help", two "Toolbelt → Open Dashboard" instructions, and "The top-menu Toolbelt entries work without this" | Live editor log | Correct every occurrence to the dashboard entry point | — |
| `Content/Python/UEFN_Toolbelt/__init__.py` (40, 67, 164) | Three stale count references: a reload-message comment reading `355` and `54`, and two `361` references in one comment and one docstring | Runtime registry is authoritative at 362 tools across 55 categories | Correct all three, under the runtime-text lock below | — |
| `Content/Python/UEFN_Toolbelt/dashboard_pyside6.py` (~23, ~2952, ~2953, ~2958) | Docstring recommending "Toolbelt menu → Open Dashboard (Qt)"; except-branch fallback literals `355` and `54` shown when the live registry read fails; and the stats row rendering `("0", "network calls — fully offline")` | Live editor log; runtime registry; `SECURITY.md` (~57–59); Plugin Hub and URL-import features make outbound requests | Correct all four, under the runtime-text lock below | — |
| `launcher.py` (~18) | Docstring step reading "Registers all `355`" tool entries | Runtime registry is authoritative at 362 tools | Correct the count, under the runtime-text lock below | — |
| `Content/Python/UEFN_Toolbelt/tools/epic_mcp_tools.py` (27) | `run_epic_mcp_status` docstring describing "separately unproven external official-MCP states" | WO-002 accepted the external result as `failed`, bounded by `UE::ValkyrieToolset::ToolsetPolicy` | Describe the accepted external official-MCP result as `failed`, bounded by `ToolsetPolicy`. Docstring only, under the runtime-text lock below | — |
| `README.md` (~224) | Safety table claiming "No file writes outside project — All output goes to `Saved/UEFN_Toolbelt/` inside your project" | `snapshot_export` (`level_snapshot.py:518`), `datatable_export` (`datatable_tools.py:171`), `curve_export` (`curve_tools.py:168`), and `stamp_export` (`prefab_stamp.py:409`) each accept an explicit export path and write to it | Replace the absolute guarantee with bounded truth: defaults commonly use `Saved/UEFN_Toolbelt/`, and explicit export parameters write to operator-selected OS paths | — |

#### Amendment 1 — two disclosed contradictions

Session A source inspection disclosed two directly contradictory claims that the
original inventory did not dispose of, and stopped rather than expanding scope on
its own. The owner ruled on both and admitted exactly these two rows, which are
the last two entries in the table above. The inventory is closed again at that
ruling.

`epic_mcp_tools.py` is a runtime path, so its correction is the **ninth** occurrence
under the runtime-text lock below and carries the same live verification set.
It is a docstring-only correction: no registration, MCP, or status-schema behaviour
changes.

The already-corrected eighth `README.md` menu occurrence (approximately line 1715)
needed no amendment. The existing README menu row requires **every** occurrence to
be corrected, and that occurrence is on the named path.

`Content/Python/UEFN_Toolbelt/list_untested.py` and the `.urcignore` `TOOL_TEST`
experiment stay deferred and outside this amendment.

### Runtime-text lock

Session A touches exactly nine runtime occurrences plus the two `install.py`
menu strings, and nothing else. All are text or fallback literals; none is
logic:

- `Content/Python/UEFN_Toolbelt/__init__.py` line 40 — reload-message comment
  carrying stale `355` and `54` values.
- `Content/Python/UEFN_Toolbelt/__init__.py` line 67 — stale `361` in a comment.
- `Content/Python/UEFN_Toolbelt/__init__.py` line 164 — stale `361` in a
  docstring.
- `Content/Python/UEFN_Toolbelt/dashboard_pyside6.py` line 23 — docstring
  recommending the unavailable Toolbelt menu.
- `Content/Python/UEFN_Toolbelt/dashboard_pyside6.py` line 2952 — except-branch
  fallback literal `355`.
- `Content/Python/UEFN_Toolbelt/dashboard_pyside6.py` line 2953 — except-branch
  fallback literal `54`.
- `Content/Python/UEFN_Toolbelt/dashboard_pyside6.py` line 2958 — the
  user-visible statistic label `"network calls — fully offline"`.
- `launcher.py` line 18 — docstring step carrying a stale `355` count.
- `Content/Python/UEFN_Toolbelt/tools/epic_mcp_tools.py` line 27 — the
  `run_epic_mcp_status` docstring softening WO-002's accepted external result
  to "unproven". Admitted by Amendment 1 above.

Every corrected count becomes 362 tools and 55 categories, matching the
authoritative runtime registry. The two dashboard fallbacks are replaced
value-for-value: the `try`/`except` structure, the live registry read, and
the statistic computation are untouched.

These corrections are included, not deferred. Deferring the dashboard label
would leave the shipped UI asserting "fully offline" while WO-003 corrects the
identical claim in `README.md`, producing exactly the surface disagreement this
mandate exists to remove.

Permitted: text and fallback-literal edits to those nine occurrences, and the
two `install.py` menu strings. Prohibited: any dashboard behaviour, layout,
widget, signal, theme, or statistic-computation change; any change to
registration logic, the `__tool_count__` / `__category_count__` constants, or
any signature; any edit to a tenth runtime occurrence without a further
mandate amendment.

Because repository policy treats these paths as live-sensitive, Session A must
complete all of the following before any commit:

- deploy to disposable `TOOL_TEST`;
- perform a **full UEFN restart**, which policy requires for every
  `dashboard_pyside6.py` change;
- verify 362 tools across 55 categories register after restart;
- visually inspect the dashboard and confirm the corrected statistic renders;
- run `install.py` end-to-end against a disposable target, which policy
  requires for every `install.py` change, and remove that target afterwards.

Throughout, Session A must not mutate or save the `TOOL_TEST` level, launch
Fortnite, run a play session, activate the custom bridge, or perform any
official-MCP probing.

Why the drift scanner did not catch these: `__init__.py` and `launcher.py`
are not declared scan targets, and the two dashboard fallbacks are bare
quoted literals that the count patterns cannot match. Session A may add
those two paths to the declared inventory under its proportional-enforcement
allowance.

The two dashboard fallbacks must not be left unprotected once corrected. Session A
adds an **assignment-specific** assertion pinning those two literals to 362 and
55 in that except branch. Generalising the count regexes to match bare quoted
literals is a scanner redesign, belongs to WO-005, and is **not** in scope here.

### Discovered scope tension, flagged for the reviewer

`Content/Python/UEFN_Toolbelt/list_untested.py` reports `356` from its own
discovery scan while the registry holds 362 tools; the accepted audit already
records the gap as "misses six registrations outside its direct scan". Changing
that script is behaviour, not documentation, so this mandate **defers the code
fix** and requires only that any document citing its output labels the number as
a discovery-scan result rather than a registry count. This path is deliberately
excluded from the writable inventory above.

### Session A inclusions

- Correct exactly the rows in the inventory table, and nothing else.
- The inventory is closed. If source inspection finds another directly
  contradictory path, Session A stops and requests a bounded mandate
  amendment naming that exact path. It may not expand scope on its own.
- Update `scripts/drift_check.py` and `tests/test_repo_integrity.py` only in
  proportion to protecting the material facts listed under enforcement.
- Add exact documentation paths to the drift scanner's declared file inventory
  where version or count drift genuinely applies.

### Session A exclusions

- No runtime behaviour changes. No changes to registration, MCP, listener,
  or UEFN API code, and no dashboard behaviour, layout, or widget change.
  The only permitted runtime edits are the text occurrences named in the
  runtime-text lock.
- No modal detection or timeout classification.
- No redesign of the coverage source of truth.
- No benchmarking of either MCP surface.
- No public composition guide, release copy, or social drafts.
- No `.urcignore` `TOOL_TEST` experiment.
- No tag, GitHub Release, repository-metadata, or social change.
- No repeat of official-MCP probing; WO-002's accepted evidence stands.

### Decision locks

- A sweeping claim may never be replaced by a different sweeping claim. Each
  correction states its surface, its evidence, and its boundary.
- Where Epic's two sources differ, the document cites which one it relies on.
- Accepted WO-002 states are copied, never re-derived: internal `passed`,
  external `failed`.
- Quirk #36 and Quirk #42 evidence is preserved verbatim in substance.

### Acceptance criteria

- A before/after claim inventory covering every row above.
- A direct evidence or primary-source mapping for every material correction.
- Demonstration that the four surfaces remain distinct in every corrected file.
- The mutation probes required under enforcement.
- Ruff, mypy, full pytest, drift check, the API-manifest check where
  applicable, and `git diff --check`, all clean.
- A final clean authority and publication state.

## Static enforcement contract

Proportional protection for concrete material inversions only. Each assertion
must protect one named fact or authority boundary, proven by temporary-copy
mutation through the real production checkers. Phrase presence alone is
insufficient.

Required inversions to reject:

- a built-in official capability reverting to "unavailable" or "Epic-locked";
- Toolbelt internal success being described as official external exposure;
- the accepted external `failed` result being changed to `passed` or softened
  back to "unproven";
- the custom bridge being described as unauthenticated, universally offline, or
  offering arbitrary remote Python;
- Quirk #36 recovery or Quirk #42 launch-safety rules disappearing;
- stale tool-count, category-count, or unavailable-entry values returning, including
  the two dashboard except-branch fallback literals, protected by an
  assignment-specific assertion rather than a broadened count pattern;
- attempted activation of Session B or application of repository metadata without a separate owner gate;

Explicitly not permitted: whole-paragraph pinning, positional Markdown parsing,
a general natural-language authorization engine, a new governance ledger, or
freezing harmless prose and formatting.

## Session B — repository-description draft only

Session B requires a separate owner gate. Its scope after that gate is drafting only: it may read the current
GitHub repository description, prepare exactly one replacement description
grounded in Session A's accepted wording, and leave that draft uncommitted for
independent review.

The current live description carries stale `358+` wording and a "fully-offline"
characterisation, both of which the corrected surface model contradicts.

Session B must not apply the description, change any remote metadata, tag,
create a GitHub Release, prepare WO-007 release or social copy, or publish
anything. Applying an accepted description is a separate explicit owner-
authorized external action, taken only after independent review, commit, push,
and green CI.

## Boundaries with WO-004 through WO-007

- **WO-004** owns modal detection and timeout classification. WO-003 may
  document known modal limitations only.
- **WO-005** owns the authoritative coverage-model redesign. WO-003 may correct
  present coverage claims from accepted evidence, and may not implement that
  model.
- **WO-006** owns controlled performance measurement. Existing audit timings
  stay labelled as non-benchmark observations.
- **WO-007** owns the full public composition guide, capability matrix, release
  copy, and social drafts.
- The `.urcignore` `TOOL_TEST` experiment remains outside WO-003.
- Runtime feature development remains outside WO-003.

## Authority stop boundaries

Each step below is a separate owner-authorized gate. None implies the next:

proposal revision → independent pre-issuance review → issuance → Session A
authorization → implementation → independent implementation review → commit →
push → CI → Session B authorization → metadata application → tag → GitHub
Release → social publication.

This Work Order is issued and Session A is authorized under root
`WORKORDER.md`. Session B is not authorized and requires a separate owner gate.

Live UEFN verification is not required for the documentation-only rows. The
exception is the runtime-text lock — nine runtime occurrences across
`__init__.py`, `dashboard_pyside6.py`, `launcher.py` and `epic_mcp_tools.py`,
plus the two `install.py` strings — which carries the deploy, full-restart,
registration, visual-inspection, and end-to-end install verification set defined
above.

NEXT GATE: fresh independent architect review of the complete uncommitted
Session A implementation. Session B remains unauthorized.
