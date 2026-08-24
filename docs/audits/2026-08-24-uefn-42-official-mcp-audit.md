# UEFN 42.00 Official MCP Convergence and Repository-Truth Audit

Date: 2026-08-24

Repository base: `6b8ffb2b2d672812f8699af2c22f92c19708f29b`

Release tag under comparison: `v2.4.1` at
`a38ab31f5ccef20c8a23a4c9404f58c7c9c2489f`

Audit type: bounded, read-only repository audit with disposable live TOOL_TEST
fixtures

Outcome: findings recorded; no implementation or publication authorized

## Scope and sources

The audit compared repository claims with Epic's UEFN 42.00 official MCP
surface, inspected Toolbelt's custom control plane, exercised reversible live
fixtures in TOOL_TEST, reconciled coverage accounting, and verified cleanup.

Primary external references:

- [Epic UEFN MCP documentation](https://dev.epicgames.com/documentation/fortnite/uefn-mcp?lang=en-US)
- [Epic 42.00 ecosystem release notes](https://dev.epicgames.com/documentation/fortnite/42-00-fortnite-ecosystem-updates-and-release-notes)

The machine-readable live signature snapshot is
[`evidence/2026-08-24-official-mcp-signatures.json`](evidence/2026-08-24-official-mcp-signatures.json).

## Execution responsibility ledger

### Codex-autonomous work

Within the owner-authorized audit boundary, Codex:

- inspected repository instructions, source, installed Epic plugin code, git
  state, documentation, tests, and drift enforcement;
- connected to the already enabled official loopback MCP endpoint and negotiated
  the protocol;
- enumerated the official toolsets and exact signatures;
- created uniquely prefixed disposable Verse, Creative-device, and Scene Graph
  fixtures;
- wrote, read, compiled, deliberately broke, diagnosed, repaired, and removed a
  Verse fixture;
- catalogued and placed devices, inspected and mutated a Verse `@editable`
  property, restored it, and initiated cleanup;
- created, inspected, moved, and attempted to remove a Scene Graph entity;
- ran Toolbelt publish preflight while Python was present;
- ran the repository's launch preparation helper immediately before remote
  validation;
- started and inspected the official session, stopped and restarted the game,
  requested logs, performed a Verse-only push, stopped the session, and ran the
  restoration helper;
- verified final fixture absence, clean compilation, restored Python inventory,
  disconnected session state, and clean repository state;
- ran the standing static checks and inspected the custom bridge threat model;
- intentionally stopped at reporting and proposed Work Orders.

### Owner/manual work

The owner:

- enabled Python Editor Scripting, Scene Graph System, and UEFN MCP Toolsets in
  Project Settings;
- restarted and opened TOOL_TEST when required;
- ran the manual Toolbelt recovery command after official MCP startup suppressed
  the project startup script;
- dismissed the missing-Verse-class validation dialog after reviewing it;
- closed a Save Content modal that was blocking queued MCP work;
- removed the top-level Scene Graph entity and remaining Verse-device actor when
  official cleanup could not complete them safely;
- saved the level and pasted visible logs and screenshots for independent
  correlation.

### Intentionally withheld

The audit did not:

- start or expose Toolbelt's custom HTTP listener after the P0 source finding;
- perform malicious, destructive, authentication-bypass, or browser exploit
  testing;
- touch a production UEFN project;
- modify repository files, stage, commit, push, tag, change a GitHub Release or
  repository description, or post socially;
- claim the observed timings were a controlled performance benchmark.

## Official MCP inventory

The live server negotiated MCP protocol `2025-11-25`. `serverInfo.name`, title,
and version were blank even though Epic documentation refers to `unreal-mcp`.
The top-level protocol exposed only:

```text
list_toolsets()
describe_toolset(toolset_name: string)
call_tool(tool_name: string, toolset_name?: string, arguments?: object)
```

`list_toolsets` returned 29 toolsets:

```text
EditorToolset.EditorAppToolset
EditorToolset.LogsToolset
GameplayTagsToolset.GameplayTagsToolset
MVVMToolset.MVVMToolset
NiagaraToolsets.NiagaraToolset_Info
NiagaraToolsets.NiagaraToolset_Component
NiagaraToolsets.NiagaraToolset_System
NiagaraToolsets.NiagaraToolset_Assets
PhysicsToolsets.PhysicsAssetToolset
VerseFieldsToolset.VerseFieldsToolset
WidgetAnimationToolset.WidgetAnimationToolset
UMGToolSet.UMGToolSet
ValkyrieToolset.ValkyriePythonToolset
ValkyrieToolset.VerseToolset
ValkyrieToolset.SessionToolset
ValkyrieToolset.DeviceToolset
ValkyrieToolset.EntityToolset
editor_toolset.toolsets.actor.ActorTools
editor_toolset.toolsets.asset.AssetTools
editor_toolset.toolsets.curve_table.CurveTableTools
editor_toolset.toolsets.data_table.DataTableTools
editor_toolset.toolsets.material.MaterialTools
editor_toolset.toolsets.material_instance.MaterialInstanceTools
editor_toolset.toolsets.object.ObjectTools
editor_toolset.toolsets.primitive.PrimitiveTools
editor_toolset.toolsets.scene.SceneTools
editor_toolset.toolsets.skeletal_mesh.SkeletalMeshTools
editor_toolset.toolsets.static_mesh.StaticMeshTools
editor_toolset.toolsets.texture.TextureTools
```

The requested official surfaces contained 10 Verse operations, 9 Creative
device operations, 13 Scene Graph entity operations, 21 UMG operations, and 8
session operations. Exact names, arguments, defaults, result schemas, and the
UMG signature-only evidence boundary are preserved in the JSON snapshot.

## Live evidence

All disposable fixtures used the prefix `TB42AUDIT_20260824`.

### Verse

- list, write, read, and delete passed;
- a clean `BuildAll` returned no diagnostics;
- a deliberate missing quote returned a structured diagnostic with severity
  `Error`, code `3100`, file path, source span, and message
  `Unexpected end of file or missing end quote in string literal`;
- repair returned the project to a clean build;
- final deletion and build passed.

### Creative devices

- the Timer catalog returned three matching device assets;
- `PlaceDevice` succeeded but returned an Actor object that stock-device
  property operations rejected because they require `ScriptDevice`;
- a disposable Verse device with `@editable AuditValue:int = 7` was catalogued
  as a Verse device;
- its `auditValue` property read correctly, changed from 7 to 99, and was
  restored to 7;
- the actor and source were removed, the level was saved, and the final catalog
  and actor queries contained no fixture.

### Scene Graph

- class discovery, creation, recursive lookup, transform read, transform
  mutation from Z=500 to Z=750, component listing, and final inspection passed;
- `DeleteEntity` returned `Cannot delete the root entity` for the top-level
  entity created by the same official surface;
- the owner removed it through the Outliner;
- final official lookup returned no matching entity.

### UMG

The live official server described all 21 UMG signatures. No widget asset was
created in this audit, so UMG remains signature-confirmed but not mutation-
verified. A disposable create/add/compile/remove proof is a separate evidence
gap, not a hidden pass.

### Session and launch boundary

Before removing Python, Toolbelt `publish_audit` returned `BLOCKED — 10/100`
because TOOL_TEST lacked `SpawnPadDevice`. It also reported zero
TextRenderActors, so no sign cleanup was required. The audit recorded 175
actors, 66 rogue-transform warnings, 3,852 redirectors, an unavailable build-log
result, and a stale memory report without misrepresenting those warnings as the
remote upload outcome.

The verified order was:

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
the stash was active. The actual remote result was awaited. Fortnite opening
was not treated as proof.

Official session behavior:

- session start completed in approximately 87.4 seconds;
- explicit StopGame completed, StartGame completed, and state returned Running;
- Verse-only PushChanges completed in approximately 8.24 seconds;
- the Session Inspector independently displayed successful Verse compilation,
  pushed changes, content version 2, server/client running, and Game in Progress;
- `GetClientLogEntries` still returned `No client log was found; start a
  play-in-client session first` while the official state was connected/running;
- final session state was Disconnected and game state Unconnected.

These are individual observations from one audit environment, not a controlled
latency comparison.

## Toolbelt coexistence

Enabling UEFN MCP Toolsets continued to suppress the project's
`Content/Python/init_unreal.py`. Epic's installed Valkyrie registration module
deliberately follows the beta Toolsets path without its own `init_unreal.py`.
Manual recovery remained:

```python
import UEFN_Toolbelt as tb; tb.register()
```

That restored the 362-tool, 55-category registry in memory. During the live
official session loop, the owner ran:

```python
print(tb.run("epic_mcp_status"))
```

It returned `status=ok`, `epic_mcp_available=True`, `registered=True`, and
`registration_confirmed=False`. This proves the loaded Toolbelt remained
callable during the official loop and while its source files were stashed.

External coexistence did not pass. The official `list_toolsets` result omitted
Toolbelt, and external describe/call requests could not find it. Internally,
`toolbelt_list_tools` and `toolbelt_run_tool` worked, while
`toolbelt_describe_tool` failed because `epic_toolset.py:194` expects a `tools`
list but `registry.py:320` returns a flat manifest keyed by tool name.

## Findings

### P0

1. The custom bridge binds to loopback but authenticates no client before
   arbitrary `execute_python` dispatch. Relevant source:
   `Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py:231`, `:757`, `:821`, and
   `:879`.
2. Direct fallback can execute Unreal work on the HTTP handler thread when Slate
   callback registration is unavailable. Relevant source:
   `Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py:27`, `:784`, and `:912`, plus
   the main-thread promise in `CLAUDE.md:272`.

### P1

1. Agent-facing documents conflate legacy Python API limitations with current
   official MCP capability. Material surfaces include `CLAUDE.md:196`,
   `CLAUDE.md:383`, `llms.txt:4`, `docs/PIPELINE.md:394`,
   `docs/AI_AUTONOMY.md:281`, and `docs/uefn_python_capabilities.md:11`.
2. Toolbelt reports internal registration without external discoverability, and
   the internal describe meta-tool consumes the wrong manifest shape.
3. README safety and public repository metadata overstate offline, filesystem,
   dynamic-execution, and network guarantees. Counterexamples include
   `asset_importer.py:135`, `dashboard_pyside6.py:1990`,
   `level_snapshot.py:518`, and the custom bridge.
4. A Save Content modal blocked an official queued call for approximately four
   minutes and resumed immediately after owner action; agentic automation lacks
   modal observability.
5. Official MCP reproduced a stock-device type mismatch, inability to delete a
   created root entity, and false no-client-log reporting during a live session.

### P2

1. Current and stale count claims coexist in runtime and public surfaces;
   TOOL_STATUS labels thirteen unavailable entries as twelve.
2. `scripts/list_untested.py` scans direct tool files and lexical references,
   not the actual registry and outcome evidence.
3. Menu, restart, roadmap phase, and background-thread wording disagree across
   repository surfaces.
4. The official server's blank identity fields differ from current Epic
   documentation.

## Coverage reconciliation

| Measurement | Result | Meaning |
|---|---:|---|
| Runtime registry | 362 | Authoritative registered universe |
| `list_untested.py` discovery | 356 | Misses six registrations outside its direct scan |
| Lexically referenced entries | 191 | Name appears in one of two scanned test files |
| Curated TOOL_STATUS result | 187 | Manually maintained unique-entry claim |
| Integration checks | 190 | 163 outcome-verified plus 27 execution-only checks |

The six missed registrations are `toolbelt_smoke_test`, `launch_qt`,
`toolbelt_update`, `debug_dump_verse_actor`, `debug_audit_verse_assets`, and
`core_safety_audit`. A lexical reference is not proof of execution or outcome.

## Capability direction

| Surface | Recommended primary | Toolbelt differentiation or evidence gap |
|---|---|---|
| Verse files and compilation | Official MCP | Templates, generators, schema intelligence, project-specific repair |
| Device placement and Verse editables | Official MCP where compatible | Bulk audits and high-level composition; stock type mismatch remains |
| Scene Graph primitives | Official MCP | Reusable entity kits; top-level cleanup gap remains |
| UMG authoring | Official MCP | Signature-confirmed only in this audit; mutation proof remains |
| Play sessions | Official MCP | Toolbelt publish preflight and prepare/restore boundary |
| Broad assets/world automation | Toolbelt | Snapshots, procedural systems, materials, lighting, diagnostics, localization |
| Custom HTTP bridge | De-emphasize pending WO-001 | Other-client compatibility after security review |
| Epic Toolset registration | Experimental | External discovery and call proof still missing |

## Final evidence

Static checks at the audited base:

- Ruff: passed;
- mypy: passed for 12 source files;
- pytest: 216 passed, 10 skipped;
- drift: passed at v2.4.1, 362 tools, 55 categories;
- `git diff --check`: passed.

Final live state:

- 96 Python files restored and no active launch stash;
- no audit Verse file, actor, device, or entity remained;
- final Verse build was clean;
- official session Disconnected and game Unconnected;
- repository worktree and index clean;
- no runtime, helper, version, commit, push, tag, Release, repository metadata,
  or social state changed.

## Proposed sequence

The audit proposed WO-001 custom bridge security, WO-002 Epic integration truth,
WO-003 documentation convergence, WO-004 modal observability, WO-005 coverage
truth, WO-006 controlled benchmarking, and WO-007 a public composition
explainer. All remain proposals. See [`../work-orders/`](../work-orders/).
