# UEFN Toolbelt — Changelog

All notable changes to this project are documented here.
Format: `## [version] — date` · Types: `feat` · `fix` · `refactor` · `docs` · `perf` · `test`

---

## [Unreleased]

### Fixed
- **Six tools returned `None`, including all four MCP bridge tools.** CLAUDE.md,
  TOOL_STATUS.md and the tool-authoring rules all state that every tool returns
  `{"status": ...}` and that "zero None returns remain in the codebase". Six fell
  off the end of their body and returned None implicitly: `mcp_start`,
  `mcp_stop`, `mcp_restart`, `mcp_status`, `launch_qt` and
  `toolbelt_integration_test`.

  The MCP four are the worst of them — they are what an agent calls to control
  the bridge, so a None result meant it could not tell whether the listener had
  come up. `mcp_start` now returns port, URL and command count;
  `toolbelt_integration_test` returns pass/fail counts, the report path and the
  list of failures, and reports `status: error` on a fatal so a caller knows
  fixtures may have been left behind.

  A test now enforces the contract by parsing every `@register_tool` function
  and checking that every path terminates in a return. Nothing enforced it
  before, which is how the claim quietly stopped being true.

- **Quick Actions reported the MCP bridge as "Not running" while it was running.**
  Both it and the MCP tab read the same `mcp_bridge._bound_port`; the difference
  was staleness. Quick Actions rendered its Setup Status rows once when the tab
  was built and never again, so a listener started afterwards never appeared.

  Computing the checks is now separate from rendering them, and navigating to a
  tab re-runs any widget that registers a `refresh_fn` property. That replaces
  the previous single-tab special case — the MCP tab had one and nothing else
  did, which is exactly how Quick Actions was missed. Setup Status, the MCP
  listener indicator and the Epic MCP indicator all register as live.

- **The last 42 `/Game/` default paths are gone.** 39 scan paths now resolve
  through `core.resolve_scan_path()` and the three `project_scaffold` `base`
  parameters — which create folders — through `core.resolve_content_path()`.
  Until now every one of these scanned or wrote to Epic's Fortnite install
  instead of the creator's project.

  Explicit arguments to scan tools are unchanged: `resolve_scan_path()` fills in
  an empty value and passes anything else through. `_GAME_PATH_DEFAULT_BASELINE`
  drops from 42 to 0, so a new `/Game/` default now fails `drift_check` outright.

- **Every material tool was silently falling back to the engine default
  material.** `material_master.PARENT_MATERIAL_PATH` and `INSTANCE_OUTPUT_PATH`
  were module constants pointing at `/Game/UEFN_Toolbelt/Materials/`, which in
  UEFN is Epic's Fortnite install. The master material was never found, so
  `material_apply_preset`, `material_randomize_colors`, `material_gradient_painter`,
  `material_team_color_split`, `material_pattern_painter`,
  `material_glow_pulse_preview` and `material_color_harmony` all logged a
  `LoadAsset failed` error and applied the fallback — while reporting success.

  Both are now resolved at call time under the project mount. Found by reading
  the integration test log rather than its pass count: all seven tools were
  marked PASS.

- **Quick Actions reported the verse-book spec as "Not cloned" when it was
  present.** It walked three `dirname` calls up from `__init__.py`, but `__file__`
  is a file — one of those levels is spent reaching the package directory — so it
  looked in `Content/verse-book` instead of the project root. smoke_test Layer 6
  derives the same path correctly, which is why the two disagreed. Both now use
  the same derivation, pinned by a test. The chapter count also read the repo
  root rather than `verse-book/docs/`, reporting "1 chapters" — the README —
  against Layer 6's 22 from the same clone.

- **Nine tools wrote assets to Epic's Fortnite install instead of the project.**
  `/Game/` is not the creator's project in UEFN (UEFN_QUIRKS.md #23), so anything
  created there is unreferenceable — the same defect that left ~700 dangling
  material references behind `arena_generate`. Affected: `curve_create`,
  `text_render_texture`, `text_voxelize_3d`, `mesh_merge_selection`,
  `import_fbx`/`organize_assets` (source and target), `create_material_instance`
  (MCP), `anim_create_montage`, `input_create_action` and `organize_smart_categorize`.

  New `core.resolve_content_path()` is the write-side counterpart to
  `resolve_scan_path()`. It also rewrites an explicit `/Game/` prefix onto the
  project mount rather than trusting it, so a caller passing one is corrected too.

### Added
- **`drift_check` ratchets the number of `/Game/` default paths.** 42 remain,
  all read/scan paths — wrong tree, but not destructive. Fixing those is its own
  change with its own live verification, so the count is baselined and may fall,
  never rise. A test additionally asserts that *no write destination* is left on
  `/Game/`, since that is the destructive half.

- **`drift_check` now catches tools that no UI surface can reach.** The dashboard
  builds its tabs from hand-written functions, so `@register_tool` does not make
  a tool clickable — three Epic MCP tools shipped registered-but-invisible with
  every version string current and drift_check passing.

  158 of 361 tools are unreachable today and much of that is deliberate (MCP and
  CLI-only utilities), so this is a ratchet rather than a coverage requirement:
  the count may fall, never rise. A new tool must be surfaced or the baseline
  moved deliberately. Improving coverage also fails the check, asking for the
  baseline to be lowered — otherwise a ratchet only ever loosens.

### Changed
- The MCP client list is now "Claude Code, Codex, Cursor, or any MCP-compatible
  agent". Codex was missing; Windsurf, Zed, Continue, OpenClaw and NemoClaw were
  listed as confirmed compatible without having been exercised in a long time.

## [2.3.7] — 2026-08-20

### Added
- **The Epic MCP tools are now reachable from the UI.** The dashboard builds its
  tabs from hand-written functions rather than from the registry, so registering
  a tool does not surface it — `epic_mcp_status`, `epic_mcp_register` and
  `epic_mcp_unregister` existed but appeared nowhere. The MCP Bridge tab gains an
  "Epic Unreal MCP" group with live registration state, and the editor menu gains
  Status and Register entries. The status line reports `unconfirmed` when the
  registry cannot be queried, rather than presenting Toolbelt's own bookkeeping
  as a verified fact.

### Fixed
- **`drift_check` was missing most stale tool counts.** Its pattern required the
  number to sit immediately before the word "tool", so `355 registered tools`,
  `358 built-in tools` and `355 Professional Tools` — the README's own headline —
  all drifted unnoticed. It now allows up to two words in between, and scans
  `.claude/tool_tables.md`, `.claude/mcp_reference.md`,
  `.claude/rules/tool_authoring.md` and `.claude/agents/tool-developer.md`, which
  carry counts and per-tool tables that rot exactly like the docs do.

  The blanket exemption on `docs/plugin_dev_guide.md` is gone too — it existed to
  silence `MIN_TOOLBELT_VERSION` examples, and a line fragment already does that,
  but exempting the whole file had hidden two stale counts inside it. Eleven
  stale references were corrected in total.

- The MCP Bridge reference table documents the three Epic MCP tools.

## [2.3.6] — 2026-08-20

### Fixed
- **No duplicate-registration warnings after a hot-reload.** A toolset name can
  be claimed exactly once per editor session on UEFN 42.00. Re-registering is
  refused, and `unregister_toolset_class` does not release it — called on the
  stashed pre-reload class it returns without error while the registry goes on
  reporting the name as held, the same identity problem the query API has. So
  the release step could never work and simply produced two warnings per reload.

  It is also unnecessary. The editor logs `Re-instancing UEFNToolbeltToolset
  after reload — 1 class changed`: UE swaps the UClass implementation by name, so
  the existing registration already dispatches into the freshly loaded code.
  `register()` now adopts that registration and updates its class reference
  instead of asking again.

## [2.3.5] — 2026-08-20

### Fixed
- **`epic_mcp_register` no longer reports a failure it cannot observe.** On UEFN
  42.00 every registration query answers False for a Python-defined toolset, even
  in the same tick the registry logs
  `Registering Toolset UEFN_Toolbelt.epic_toolset.UEFNToolbeltToolset` for that
  exact class — verified against `is_toolset_class_registered` and
  `is_toolset_registered` with the qualified, short and friendly names. Treating
  that False as proof of refusal was the 2.3.1 bug inverted: it announced an
  error for a registration that had just succeeded. `_is_registered()` now
  returns True or None and never False, so a positive confirmation still counts
  if Epic fixes the query side, and registration reports
  `registration_confirmed: false` rather than inventing a failure.
- Idempotency keys off Toolbelt's own record plus the cross-reload stash, since
  the registry cannot be asked.
- The toolset class carries a clean `__qualname__` instead of
  `_build_toolset_class.<locals>.UEFNToolbeltToolset`, an artefact of defining it
  inside a function to keep `@unreal.uclass()` off the import path.

## [2.3.4] — 2026-08-20

### Added
- **Detection for a silent startup failure.** On UEFN 42.00, enabling Project
  Settings → Beta Access → "UEFN MCP Toolsets" stops the project's
  `init_unreal.py` from running: Epic's Toolsets plugins force-enable Python
  before the project's script paths are registered, so only their own start-up
  scripts are scanned. Nothing raises and nothing is logged — Toolbelt just never
  starts, the tool count is 1 instead of 361, and every `tb.run()` answers
  "Unknown tool", which reads as a Toolbelt bug. `tb.startup_ran()` now reports
  whether `register()` was reached, and smoke test Layer 3 fails with the cause
  and the workaround. Documented as UEFN_QUIRKS.md #36.

  The flag is set by `register()`, not `register_all_tools()` — the smoke test
  calls the latter itself, so keying off it would always look healthy.

  Not fixable from Toolbelt: `PythonScriptPluginSettings` is not exposed to
  Python on this build and UEFN projects have no `Config/` directory for an
  explicit `StartupScripts` entry. This needs an Epic-side fix.

## [2.3.3] — 2026-08-20

### Fixed
- **`epic_mcp_status` reads registration back from the registry.** It reported a
  module-level flag, which records only what the code believed when it set it —
  it cannot know about a registration dropped underneath it. The flag is now a
  fallback for when the registry will not answer, and `registration_confirmed`
  says which of the two the caller is looking at. The class is located through
  the cross-reload stash, so status is still accurate after a hot-reload has
  cleared the module's own reference.

## [2.3.2] — 2026-08-20

### Fixed
- **The Epic MCP toolset survives a hot-reload.** The reload `deploy.bat` prints
  pops every `UEFN_Toolbelt` module out of `sys.modules`, destroying the module's
  reference to the toolset class while Epic's registry goes on holding the name.
  The next `register()` built a fresh class, the registry refused it as a
  duplicate, and there was nothing left to pass `unregister_toolset_class()` —
  wedging the integration until a full editor restart. The live class is now
  parked on the `unreal` module, which that reload does not touch, so the stale
  registration is released before the new class is registered.
- **Registration checks class identity only.** `is_toolset_registered(name)` was
  also being consulted, on the assumption its key was the qualified path the
  registry prints. Checked live on UEFN 42.00 it answered False for a name the
  registry was simultaneously logging as "already registered" — and a True from
  it after a reload would have meant "held by the class you just replaced",
  reading as "already registered" and skipping the release.

## [2.3.1] — 2026-08-20

### Fixed
- **Epic MCP registration no longer reports success when the registry refused.**
  `ToolsetRegistry.register_toolset_class` logs "Unable to register" and returns
  normally when the name is already held — it does not raise — so a call that did
  not throw was no evidence registration happened. Observed live on UEFN 42.00:
  the editor logged a refusal in the same breath as Toolbelt logged "Registered".
  Registration is now confirmed against the registry afterwards, and an
  unconfirmed result is reported as an error naming the likely cause.
- **Registration is idempotent.** `register_all_tools()` runs again on every
  smoke test and hot-reload; the previous unregister/re-register churn would drop
  the toolset out from under a connected MCP client. An already-registered
  toolset is now left alone.
- `_is_registered()` distinguishes "not registered" from "cannot tell", checking
  the class and then the qualified name Epic logs — the two disagree after a
  Python reload, when the module rebuilds the class but the name stays held.

## [2.3.0] — 2026-08-20

### Added
- **Epic Unreal MCP integration.** Toolbelt now registers itself with Epic's
  official Toolset Registry (UEFN 42.00), so any connected MCP client discovers
  the catalogue natively. Rather than emit 361 UFunctions — each needing
  UE-mappable parameter annotations — it exposes three meta-tools mirroring the
  shape Epic already uses in tool-search mode: `toolbelt_list_tools`,
  `toolbelt_describe_tool` and `toolbelt_run_tool`. Adding a Toolbelt tool
  requires no change to the integration.
- `epic_mcp_status`, `epic_mcp_register`, `epic_mcp_unregister` (MCP Bridge).
- `ToolRegistry.execute_strict()` — executes a tool letting failures propagate.
  `execute()` returns None for both a crash and a tool that legitimately returns
  nothing, which would report failures to an MCP client as success.
- **Optional-API declarations.** Modules list the `unreal.*` names they use but
  do not require via `__optional_unreal_apis__`; the manifest records them and
  the smoke test reports their absence as handled instead of failed. A name is
  optional only when *every* consumer declares it so, so adding an unguarded
  caller silently re-promotes it to required. This clears the 14 permanently-red
  Layer 2 failures every UEFN 42.00 user was seeing for problems already handled.

### Fixed
- **`align_to_surface` no longer reports success when it snapped nothing.** UEFN
  42.00 removed `EditorLevelLibrary.snap_objects_to_floor`; the tool caught the
  AttributeError, logged a warning, then still applied `offset_z` — shifting
  actors off an unsnapped position and returning `status: ok`. It now refuses
  through the same `missing_unreal_apis()` guard as the other twelve. Its
  docstring also claimed a per-actor trace fallback that was never implemented.

### Safety
- Every Epic MCP symbol is optional and resolved lazily. The toolset class is
  built inside `register()`, never at import: applying `@unreal.uclass()` to a
  missing base class would raise during `import UEFN_Toolbelt` and take all 361
  tools down with it. Registration no-ops with a log line when the Experimental
  ToolsetRegistry plugin or the UEFN MCP beta flag is off.

## [2.2.5] — 2026-08-20

### Fixed
- **`arena_generate` no longer writes assets to `/Game/`.** In UEFN `/Game/` is
  Epic's Fortnite install (`FortniteGame/Content`), not the creator's project
  (UEFN_QUIRKS.md #23). The auto-generated team materials were created under a
  hardcoded `/Game/UEFN_Toolbelt/Materials/` path, so every actor they were
  applied to ended up pointing at a material the project could not resolve. Paths
  now resolve through `detect_project_mount()` at call time.
- **Arena mesh lookups resolve against the project mount too.** `SM_Floor_Tile`,
  `SM_Wall_Panel`, `SM_Platform` and `SM_SpawnPad` were looked up under the same
  wrong mount, so they could never be found and every arena silently fell back to
  the configured mesh. The constants are now bare asset names.
- Removed the unused `_MAT_FOLDER` constant.

## [2.2.4] — 2026-08-20

### Fixed
- **`smart_organizer` no longer deletes an asset when a rename fails.** A failed
  `rename_asset` with something already at the target was treated as proof that a
  previous run had moved this asset, so the source was deleted and the row counted
  as "moved". Two assets from different source folders can categorise to the same
  target name, in which case this deleted an unrelated asset. Worse, deleting the
  source without fixing up redirectors left every referencer pointing at a dead
  path, orphaning the destination copy. Verified on a live project: an entire prop
  set (mesh + material + three textures) severed this way, every piece left
  unreferenced. Collisions are now reported for the user to resolve and nothing is
  deleted — the module no longer calls `delete_asset` at all.
- **Orphan scan no longer walks level sub-objects or Verse digest paths.** Under
  one-file-per-actor, `:PersistentLevel.ActorFolder_UID_…` entries outnumbered real
  assets ~230:1 and all resolved to the same owning package, so the audit reported
  "3458 protected" out of 3473 and read as though it had skipped the project.
  UEFN 42.00 `$Digest` paths also made `EditorAssetSubsystem` log an error per
  lookup. Both are now filtered before any lookup, and the summary reports
  sub-objects, protected roots and evaluated assets separately.

## [2.2.3] — 2026-08-20

### Fixed
- **Reference-tree root assets are no longer classified as orphans.** Verified on a
  live UEFN 42.00 project: `GameFeatureData` (the `.uplugin` descriptor asset) and
  the default `HLODLayer` both report zero package referencers, because what points
  at them is configuration rather than another package. The previous skip list
  covered only maps and blueprints, so `ref_delete_orphans(dry_run=False)` would
  have deleted the project descriptor. Protection now applies at two independent
  layers: `ROOT_ASSET_CLASSES` during the scan, and a re-filter inside
  `_delete_orphans` at the point of no return.
- **Mount-root packages are never deleted.** Anything sitting directly at
  `/YourProject/…` is project plumbing and is skipped regardless of class, which
  also covers the case where class-name lookup fails or a future engine renames
  one of these types.
- **UE 6.0 reference-lookup fallback is validated by a real call**, not by
  attribute presence. An API that exists but rejects our arguments previously
  passed the availability check and then raised from inside the scan loop,
  surfacing `None` instead of a clean refusal.

## [2.2.2] — 2026-08-20

### fix: UEFN 42.00 (UE 6.0) compatibility — prevent project-wide asset deletion

UEFN force-updates with the live Fortnite build, so every user received UE 6.0
without opting in. `smoke_test` Layer 2 flagged 16 removed `unreal.*` APIs.
Fifteen of those degrade safely. One did not.

**`reference_auditor` — data loss (critical)**

`EditorAssetLibrary.find_package_referencers` was removed in 42.00. The helper
wrapping it caught the resulting `AttributeError` and returned `[]`, which every
orphan check reads as *"nothing references this asset — safe to delete"*.
`ref_delete_orphans(dry_run=False)` acted on that permanently.

- Reference lookup now resolves a strategy once per session: the legacy
  `find_package_referencers`, then an Asset Registry `get_referencers` fallback
  for UE 6.0. If neither resolves it raises `ReferenceLookupUnavailable` — a
  failed lookup can no longer masquerade as zero referencers.
- `ref_audit_orphans`, `ref_audit_unused_textures` and `ref_delete_orphans`
  refuse with `reason="reference_api_unavailable"` instead of reporting bogus
  results.
- `ref_full_report` degrades per-section: redirector and duplicate-name scans
  never needed reference lookup and still run.
- `ref_audit_redirectors` and `ref_fix_redirectors` are unaffected; the
  referencer count they display is now soft (`-1` when unknown).

### fix: API tripwire named the wrong culprits

`api_dependencies.json` recorded `used_by` only at the symbol level, so a missing
*method* was reported with every consumer of its *class*. On 42.00 that blamed
`EditorLevelLibrary.snap_objects_to_floor` on 29 modules when it affects one —
making a two-file fix look like a platform-wide outage mid-triage.

- Manifest now records per-attribute `used_by`; the probe reports only a
  method's own callers. Older list-shaped manifests still load.

### feat: engine-API preflight for tools whose dependencies were removed

`core.missing_unreal_apis()` / `core.api_unavailable()`. Twelve tools now refuse
with `reason="engine_api_unavailable"` and the specific missing API, instead of
surfacing a raw `AttributeError` from inside their own loop:

- `geometry_tools` (8) — GeometryScript is absent from 42.00
- `blueprint_tools` (2) — `blueprint_inspect`, `blueprint_compile_folder`
- `enhanced_input_tools` (1) — `input_create_action`
- `system_perf` (1) — `system_optimize_background_cpu`

`align_to_surface` and `pcg_refresh_all` already had fallbacks and are unchanged.

### test

- `tests/test_reference_safety.py` — pins the invariant that a failed reference
  lookup can never be mistaken for zero referencers, both legacy and UE 6.0 paths.
- `tests/test_api_guards.py` — preflight detection and the refusal contract.
- `tests/test_api_manifest.py` — per-attribute attribution must stay strictly
  narrower than class-level, so the mis-blame cannot silently return.

## [2.0.0] — 2026-03-29

### feat: full UEFN Python API coverage — 4 new modules, 21 new tools (297 → 318)

Every previously empty API domain in `docs/uefn_python_capabilities.md` now has toolbelt coverage.
Claude's tool manifest now spans the complete UEFN Python surface area.

**`enhanced_input_tools.py`** (4 tools — EnhancedInput, 75 types)
- `input_list_actions` — list all InputAction assets (name, path, value type)
- `input_list_contexts` — list all InputMappingContext assets
- `input_inspect_context` — inspect a context's key→action bindings
- `input_create_action` — create a new InputAction asset (bool/axis1d/axis2d/axis3d)

**`animation_tools.py`** (5 tools — AnimGraph 97 types, AnimGraphRuntime 152 types)
- `anim_list_skeletons` — list all Skeleton assets
- `anim_list_sequences` — list AnimSequences with duration and skeleton
- `anim_list_montages` — list AnimMontage assets
- `anim_list_blend_spaces` — list BlendSpace and BlendSpace1D assets
- `anim_create_montage` — create an AnimMontage from an existing AnimSequence

**`audio_design_tools.py`** (5 tools — MetasoundEngine 24, MetasoundEditor 37, AudioSynesthesia 38)
- `audio_list_metasounds` — list MetaSoundSource and MetaSoundPatch assets
- `audio_list_sound_classes` — list SoundClass assets with volume/pitch
- `audio_list_sound_cues` — list SoundCue assets
- `audio_list_sound_mixes` — list SoundMix snapshot assets
- `audio_list_synesthesia` — list AudioSynesthesia analyzers (LoudnessNRT, ConstantQNRT, OnsetNRT)

**`world_partition_tools.py`** (4 tools — DataLayerEditorSubsystem, WorldPartition)
- `world_partition_status` — check if WP is enabled for the current level
- `data_layer_list` — list all Data Layers with load/visibility states
- `data_layer_create` — create a new Data Layer
- `data_layer_assign_selection` — assign selected actors to a named Data Layer

**`geometry_tools.py`** additions (3 more boolean/repair tools — GeometryScriptingCore)
- `geometry_boolean_subtract` — cut second mesh out of first
- `geometry_boolean_intersect` — keep only the shared volume
- `geometry_remove_degenerate` — remove zero-area triangles causing lighting/collision artifacts

---

## [1.9.9] — 2026-03-29

### feat: Auto Organizer window + disk-based scan (ARFilter-free, pak-safe)

**`smart_organizer.py` additions**
- `organize_open` — interactive PySide6 window: scan root + organized root path inputs, per-type checkboxes (14 asset types), include-unused toggle, scrollable preview table (asset name / class / type / category / destination), Organize button
- `_PREFIX_TO_TYPE` map + `_type_from_prefix()` — type detection from Epic naming prefixes (zero AR calls)

**Scan engine — disk-based, not Asset Registry**
- `_execute_scan` walks the project `Content/` directory on disk via `os.walk` / `os.listdir`
- Finds the real `Content/` dir by walking up from `__file__` — `unreal.Paths.project_dir()` returns `../../../FortniteGame/` in UEFN (useless); the `__file__` walkup is the only reliable method (Quirk #23, Quirk #32)
- Assets are typed via prefix matching — zero Asset Registry calls during scan
- Safe on pak-heavy projects like BRCosmetics where AR queries on the project mount stall/crash due to 1M+ mounted pak entries (Quirk #32)
- Deferred to next Slate post-tick callback to run outside Qt `processEvents()` (Quirk #31)

**Also**
- Added `MaterialFunctionMaterialLayerBlend` to `CLASS_TO_TYPE` map
- `_do_organize` redirector count removed (was using `ar.get_assets_by_path(scan_root)` — same crash vector as the scan)

### fix: organize_open — mount detection, CB path building, organize loop (v1.9.9 patch)

**Root causes found and fixed during live UEFN testing:**

1. **Wrong project mount** — `detect_project_mount()` uses "most AR entries" heuristic, which returns `BRCosmetics` (Fortnite game paks with 1M+ entries) instead of the user's project. Fixed: derive mount name from `__file__` walkup — `os.path.basename(os.path.dirname(content_dir))`. Always correct regardless of AR state.

2. **Double `Content/Content` in CB paths** — `_content_in_cb` probe (`does_directory_exist("/{mount}/Content")`) returns `True` when the user has a folder literally named `Content` inside their project's Content directory. This caused a spurious extra `/Content/` segment in all generated CB paths. Fixed: removed the probe entirely. In UEFN the project mount always maps directly to `Content/` on disk — no layout variation requires the extra segment.

3. **`scan_paths_synchronous` crash** — calling AR scan APIs on pak-heavy CB directories (even targeted ones) crashes UEFN. Removed entirely.

4. **`unreal.load_asset()` freeze** — loading assets in a loop inside a Slate tick callback triggers full dependency resolution (materials → textures → etc.), stalling the main thread indefinitely. Removed entirely.

5. **Dest-already-exists cleanup** — previous partial organize runs left source duplicates on disk alongside destination copies in `Organized/`. `eal.rename_asset()` correctly refuses to overwrite. Fix: after rename fails, check `does_asset_exist(target)` — if destination already has the asset, delete the stale source duplicate via `eal.delete_asset()`.

**Net result:** scan finds 0 planned moves on a fully-organized project (correct), organizes assets end-to-end without AR scans, crashes, or freezes.

---

## [1.9.8] — 2026-03-29

### feat: Cooker Optimizer — native absorption of BiomeForge's UEFNCookerOptimizer (291 → 296 tools)

**New module: `cooker_optimizer.py` (5 tools) — "Optimization" category**
- `cooker_scan` — scan level actors for cook candidates (blueprints, static meshes, optional landscapes); caches results for the window + MCP tools
- `cooker_mark_batch` — mark the cheapest N% of actors as editor-only via `is_editor_only_actor`; `dry_run=True` by default; wrapped in `ScopedEditorTransaction` for Ctrl+Z undo
- `cooker_unmark_all` — remove editor-only flag from every previously marked actor; fully undoable
- `cooker_mark_selection` — mark/unmark the current viewport selection directly; `mark=True` to set, `False` to clear
- `cooker_open` — open the Cooker Optimizer window (PySide6, `ToolbeltWindow` subclass)

**`cooker_open` window features:**
- Scan + Undo All toolbar buttons in topbar
- Actor count, cook candidates, marked count stat cards with live update
- Batch slider (0–100%) + dry-run toggle → Mark/Unmark actions
- Cook Feedback panel: Yes/No buttons to record whether the cook succeeded after marking
- Weighted nearest-neighbour confidence estimator preserved from original BiomeForge algorithm
- Cook feedback persisted to `Saved/UEFN_Toolbelt/cooker_feedback.json` (survives restarts; original was session-only)
- Help dialog with BiomeForge credit and full MCP tool reference

**Attribution:** Full credit to BiomeForge (EDMIRE2k) for the original UEFNCookerOptimizer — editor-only batching workflow and confidence estimation algorithm. Listed in About tab attributions.

---

## [1.9.7] — 2026-03-25

### feat: Verse template library + build status watcher (287 → 291 tools)

**New module: `verse_templates.py` (3 tools) — "Verse Helpers" category**
- `verse_template_list` — list all 6 battle-tested Verse game templates with descriptions and required device lists
- `verse_template_get` — return full Verse source for a named template; Claude fills device labels from `world_state_export` and deploys
- `verse_template_deploy` — write a template (raw or Claude-edited) directly to the Verse source directory; delegates to `verse_write_file`
- 6 templates: `game_skeleton`, `elimination_scoring`, `zone_capture`, `round_flow`, `item_spawner_cycle`, `countdown_race`
- All templates use confirmed Verse syntax matching patterns in `verse_snippet_generator.py` — zero hallucinated API names

**`system_build.py` addition (1 tool)**
- `verse_build_status` — lightweight build status check with ISO timestamp and staleness flag; Claude uses this to detect whether the user has clicked Build Verse since its last change, without the overhead of `verse_patch_errors`

**AI autonomy impact:**
- Template library eliminates Verse syntax hallucination — Claude assembles from proven patterns instead of generating from scratch
- Build status + timestamp lets Claude reason about build freshness in the autonomous loop: act → tell user to click Build → check status → fix errors → repeat

---

## [1.9.6] — 2026-03-25

### feat: team workflow tools — visibility, selection sets, bookmarks, merge (270 → 287 tools)

**New module: `actor_visibility.py` (8 tools)**
- `actor_hide` / `actor_show` — hide or restore selected actors in the viewport
- `actor_isolate` — hide everything except selection; focus on your section
- `actor_show_all` — restore visibility for every hidden actor in the level
- `folder_hide` / `folder_show` — toggle visibility of an entire World Outliner folder
- `actor_lock` / `actor_unlock` — prevent accidental viewport moves on final-placed assets

**`viewport_tools.py` additions (4 tools)**
- `viewport_showflag` — apply named show-flag preset (clean / no_text / no_icons / geometry_only / reset)
- `viewport_bookmark_save` / `viewport_bookmark_jump` / `viewport_bookmark_list` — named persistent camera bookmarks; survive restarts

**`selection_utils.py` additions (3 tools)**
- `selection_save` / `selection_restore` / `selection_list` — save named actor selections to JSON; restore by label match across restarts

**`project_admin.py` addition (1 tool)**
- `save_all_dirty` — save all unsaved assets and the current map in one call; no dialog

**`bulk_operations.py` addition (1 tool)**
- `mesh_merge_selection` — merge selected StaticMesh actors into a single mesh asset (one draw call); graceful error if UEFN sandboxes the API

**Also in this release:**
- `viewport_move_to_camera` — move selected actors to current camera position (sprint-placed workflows)
- `CAMERA ALIGN` deferred-tick fix in Verse Device Graph node clicks
- UEFN_QUIRKS.md: Quirk #28 (execute_console_command crash from Qt signal), Quirk #29 (verse graph crash clears on UEFN restart)

---

### refactor: AI automation depth — world_state richness, verse error classification, manifest examples

**`world_state_export` — per-actor fields added:**
- `folder` — World Outliner folder path (e.g. `"Arena/Walls"`)
- `parent` — attach parent actor label (empty string if root)
- `bounds` — `{center: {x,y,z}, extent: {x,y,z}}` in cm
- `asset_path` — StaticMesh package path (e.g. `/Engine/BasicShapes/Cube`)
- Top-level `summary` block: `class_counts` and `folder_map` sorted by frequency
- Fix: root actors now store `folder: ""` instead of `folder: "None"` (str(None) bug)

**`verse_patch_errors` — error classification added:**
- `error_type` per error: `undefined_identifier`, `type_mismatch`, `missing_member`, `missing_override`, `syntax_error`, `unreachable_code`, `suspend_context`, `scope_error`, `duplicate_definition`, `unknown`
- `fix_hint` per error: one-line instruction for Claude to act on immediately
- `errors_by_file` dict: errors grouped by filename for direct file-by-file repair
- `error_type_summary` dict: type → count at top level

**Registry — `example` field:**
- `@register_tool` now accepts `example=""` — a concrete call string with valid param values
- Exposed in `to_manifest()` output and `tool_manifest.json`
- Added to 13 most AI-critical tools: `verse_write_file`, `device_set_property`, `scatter_hism`, `stamp_place`, `zone_spawn`, `pattern_circle`, `bulk_align`, `snapshot_save`, `actor_copy_to_positions`, `verse_patch_errors`, `world_state_export`, `device_catalog_scan`

**Integration test — Batch 10 (v1.9.6 tools):**
- `_test_visibility_tools`: `actor_hide/show/isolate/show_all/lock/unlock`
- `_test_viewport_bookmarks`: `viewport_showflag` (clean/reset/unknown), bookmark save/list/jump
- `_test_selection_sets`: `selection_save/list/restore` + duplicate-label safety + error path
- `_test_project_admin_v196`: `save_all_dirty`

---

### feat: 6 new tool modules + focus=True viewport snap for all spawn tools (250 → 269 tools)

**New modules (19 tools):**
- `niagara_tools.py` — VFX control: `niagara_spawn_system`, `niagara_list_systems`, `niagara_bulk_set_parameter`, `niagara_clear_systems`
- `pcg_tools.py` — PCG graph control: `pcg_execute_graph`, `pcg_set_seed`, `pcg_randomize_seed`, `pcg_refresh_all`
- `geometry_tools.py` — GeometryScript mesh ops (all default `dry_run=True`): `geometry_weld_edges`, `geometry_fix_normals`, `geometry_recalc_uvs`, `geometry_boolean_union`, `geometry_decimate`
- `movie_render_tools.py` — Sequencer pipeline: `movie_render_queue_sequence`, `movie_render_apply_preset`, `movie_render_status`
- `viewport_tools.py` — Camera navigation: `viewport_goto`, `viewport_focus_actor`, `viewport_camera_get`
- `activity_log_tools.py` — Tool call monitoring: `toolbelt_activity_log`, `toolbelt_activity_stats`, `toolbelt_activity_clear`

**`focus=True` — viewport snap on all spawn tools:**
- Added to `pattern_grid/circle/arc/spiral/line/wave/helix/radial_rows`, `zone_spawn`, `scatter_props`, `scatter_hism`, `stamp_place`
- Uses UEFN's native `CAMERA ALIGN` console command (select actors → CAMERA ALIGN) — zero roll corruption
- All spawn tools now return `"center": [x,y,z]` in their result dict
- Default `False` (preserves viewport state when using the dashboard; set `True` when running from console or MCP)

**viewport_focus_actor fix:**
- Replaced manual `set_level_viewport_camera_info` with `CAMERA ALIGN` — eliminates the persistent camera roll corruption introduced in UEFN's viewport API

**drift_check.py — category count tracking:**
- Now reads `__category_count__` from `__init__.py` alongside `__version__` and `__tool_count__`
- Added `_CATEGORY_COUNT_PATTERN` scanner — catches stale category counts across all 12 scanned files

---

## [1.9.6] — 2026-03-24

### feat: rolling activity log — system monitor for every tool call (247 → 250 tools)
- New module `core/activity_log.py` — records every `tb.run()` call automatically
  - In-memory ring buffer (`deque(maxlen=500)`) + JSON persistence to `Saved/UEFN_Toolbelt/activity_log.json`
  - Per-entry fields: `tool`, `status` (ok/error), `duration_ms`, `timestamp`, `error` (truncated traceback tail)
  - Pre-loads from disk on first access — survives hot-reload
- Wired into `registry.execute()` at the chokepoint — zero boilerplate for tool authors
  - `time.perf_counter()` timing wraps every tool call
  - Lazy import (`from .core.activity_log import record`) — never crashes a successful run
- 3 new registered tools:
  - `toolbelt_activity_log` — view last N entries, newest first (default 50)
  - `toolbelt_activity_stats` — aggregate stats: total, ok/error counts, error rate, slowest, most-called, last 5 errors
  - `toolbelt_activity_clear` — wipe buffer + disk file before benchmarking or fresh test runs
- Use cases: AI agent health monitoring, performance bottleneck detection, error pattern analysis

---

## [1.9.6] — 2026-03-24

### feat: publish_audit — Fortnite island publish-readiness checker
- New tool: `publish_audit` in `tools/publish_audit.py`
- 9-layer fast audit in one call (no actor mutations, fully read-only):
  1. Actor count vs configurable budget limit (default 2000)
  2. Required devices present — spawn pads and any custom class list
  3. Light count budget warning (default >50)
  4. Rogue actors — zero/extreme scale, off-map, at-origin
  5. Verse build status — reads last build log for SUCCESS/FAILED
  6. Unsaved level detection
  7. Stale ObjectRedirector count (quick Asset Registry scan)
  8. Level name sanity — not "Untitled" or default
  9. Memory report freshness — references cached memory_report.json if <2h old
- Returns `{"status": "ready"|"warnings"|"blocked", "score": 0-100, "checks": {...},
  "blocked_by": [...], "next_steps": [...]}` — fully MCP-ready
- Saves report to `Saved/UEFN_Toolbelt/publish_audit.json` after every run
- Does NOT duplicate existing tools (memory_scan, rogue_actor_scan, ref_full_report,
  level_health_report) — calls fresh inline checks and references their cached output

---

## [1.9.4] — 2026-03-24

### fix: theme switcher now updates the full dashboard
- Replaced ~84 hardcoded hex values in `dashboard_pyside6.py` with `_color('token')`
  calls so every inline `setStyleSheet` responds to `set_theme()` live
- Added two new PALETTE tokens: `text_bright` and `text_dim`, with correct values
  for all 6 themes (toolbelt_dark, midnight, ocean, nord, forest, daylight)
- Dark theme output is pixel-identical to before — token values match old hardcoded hex exactly
- Theme switcher now fully functional: switching to `daylight`, `ocean`, `midnight`,
  `nord`, or `forest` updates the entire dashboard, not just cascade-controlled widgets

### fix: audit pass 3 — defensive improvements
- `screenshot_timed_series`: log prominent warning when `interval_sec > 0` (editor
  will freeze during series; recommend `interval_sec=0` for burst mode)
- `base_window`: Slate tick exceptions now surface in Output Log instead of silent pass
- `mcp_server`: `UEFN_MCP_PORT` env var parse wrapped in try/except with range check;
  falls back to 8765 instead of crashing on invalid input
- `mcp_server`: stale tool count 171 → 246 in docstring

### docs: ARCHITECTURE.md — system design reference
- New top-level document: directory map, subsystem descriptions, data flow diagram,
  execution environment constraints, extension points for contributors

---

## [1.9.3] — 2026-03-24

### fix: zero None returns — Phase 21 guarantee enforced across all tools
- `screenshot_timed_series` — returned `None`; now returns `{"status": "ok", "count", "folder"}`
- `sim_generate_proxy` — returned `None` on success/no-selection; now returns structured dict
- `sim_trigger_method` — returned `None` on all paths; now returns `{"status": "ok/error", ...}`
- `import_fbx` — returned `None` on all paths; now returns `{"status": "ok/error", "imported", "count"}`
- `import_fbx_folder` — same fix; returns count of imported assets
- `organize_assets` — same fix; returns `{"status": "ok", "moved", "total", "target"}`
- `system_build_verse` and `system_get_last_build_log` — added missing `**kwargs`
- `api_verse_get_schema` and `api_verse_refresh_schemas` — added missing `**kwargs` + `= ""` default

### docs: ARCHITECTURE.md — system design reference
- New top-level document covering: directory map, subsystem descriptions, data flow,
  execution environment constraints, and extension points
- Added to Key Files table in CLAUDE.md and CONTRIBUTING.md

### docs: README version badge bump 1.9.1 → 1.9.2

---

## [1.9.2] — 2026-03-24

### feat: stamp_export / stamp_import — cross-project stamp sharing
- `stamp_export` — copy a saved stamp to a portable JSON file (defaults to `~/Desktop/stamps/`)
- `stamp_import` — import a stamp from any JSON file into the local library with optional name override and overwrite control
- Verified live: export → file on Desktop, import → appears in `stamp_list`

### test: batch 9 integration tests — 163/163 passing
- 12 new test sections covering 75 tools added after v1.6.0:
  zones, stamps, actor org, proximity placement, advanced alignment, signs,
  post-process, audio, level health, config, lighting extended, world state
- Incremental result flushing: partial results now written after every test record,
  so a mid-run crash leaves a diagnostic file instead of nothing
- Fixed wrong return key assertions: `world_state_export` (`count` not `actor_count`),
  `device_catalog_scan` (`devices_found` not `device_count`)
- `sky_set_time` and `world_settings_set` marked as expected-limited on bare template levels

### feat: MCP dashboard live status indicator
- MCP tab now shows live `● RUNNING port 8765` / `● NOT RUNNING` label
- Status auto-refreshes whenever the MCP tab is navigated to
- Start/Stop/Restart buttons update status immediately after running

### feat: verse tab — check build errors button
- Added `▶ Check Build Errors` button at top of Build Intelligence group
- Calls `verse_patch_errors` — reads build log, extracts errors with file/line context,
  returns full content of every erroring .verse file for Claude to fix in one shot

### feat: community plugins — 2 new genuine gap-fillers
- `spawn_at_each_selected` — stamp any asset at every selected actor's position
  (place lights above torches, markers at spawn pads, etc.)
- `verse_gen_checkpoint` — generate a full Verse checkpoint/progression system
  (sequential triggers, per-player progress, win condition, optional reset-on-elim)

### fix: parameters= kwarg not valid in @register_tool
- Removed `parameters={}` from all `@register_tool` decorators (not a supported argument)
- Manifest builds from `inspect.signature()` on the function — type annotations + defaults
- Fixed in `prefab_stamp.py` and both community plugins; documented in CONTRIBUTING.md

### docs: quirk #27 — hard restart vs nuclear reload
- Nuclear reload fixes code. Hard restart fixes state.
- Added to `UEFN_QUIRKS.md`, `CLAUDE.md`, and `CONTRIBUTING.md` with decision table
- Covers: Shiboken crashes, project switches, stale C++ handles, `tb` undefined errors

### docs: TOOL_STATUS.md rebuilt from scratch
- Updated from 171 → 246 tools, 76% coverage
- Full Batch 9 coverage map (🔵 written/pending → ✅ live-verified after 163/163)
- Disabled tools table (lod_auto_generate_* — Quirk #18)
- CLAUDE.md and CONTRIBUTING.md now reference TOOL_STATUS.md as authoritative coverage doc

### docs: smoke test vs integration test explained everywhere
- README, CLAUDE.md, CONTRIBUTING.md all now clearly explain what each test does,
  when to run it, safety rules, and the comparison table
- Dashboard setup status threshold updated from 171 → 240

### docs: tb import rule — when to import vs when tb already exists
- Added to CLAUDE.md Nuclear Reload section and CONTRIBUTING.md Step 4
- Rule: same project/session = tb exists; switched projects or fresh launch = import fresh

### docs: ai-native onboarding — CONTRIBUTING.md and README
- CONTRIBUTING.md: 5-step contributor loop, mandatory "check existing tools first" as Step 1,
  fast grep command to audit all 247 tool names before writing anything new
- README: AI-native pioneer pitch, CLAUDE.md auto-loading as a first-of-its-kind feature

---

## [1.9.1] — 2026-03-24

### feat: level stamp system — save and re-place actor groups

**New tools (`stamp_save`, `stamp_place`, `stamp_list`, `stamp_info`, `stamp_delete`):**
- `stamp_save` — capture any selection of StaticMesh actors as a named stamp; records relative transforms, mesh asset paths, rotations, and scales to `Saved/UEFN_Toolbelt/stamps/{name}.json`
- `stamp_place` — re-spawn a saved stamp at the viewport camera (or explicit location). Optional `yaw_offset` rotates all actor positions and rotations around the stamp center. Optional `scale_factor` multiplies all offsets and scales uniformly
- `stamp_list` / `stamp_info` / `stamp_delete` — manage saved stamps
- New **Stamps** category in the registry (38 categories total)
- Full undo support via `ScopedEditorTransaction`; new actors auto-selected after placement
- Blueprint/device actors are skipped with a warning (can't be reliably re-spawned from path)
- Stamp files survive hot-reloads, editor restarts, and Toolbelt updates — stored in `Saved/` not `Content/`
- Distinct from `prefab_migrate_open` (asset migration between projects) — stamps are for level layout reuse
- Documented in CLAUDE.md with compass-point placement example

### docs: quirk #26 — nuclear reload crash when adding new modules

- Documented `EXCEPTION_ACCESS_VIOLATION` caused by `sys.modules.pop` freeing Python objects
  while stale Unreal C++ callbacks (Slate tick, MCP socket) still point at them
- Crash signature, when it happens, and the safe workflow (full restart for new modules,
  nuclear reload only for iterating on existing tools)
- Added warning to CLAUDE.md nuclear reload section with cross-reference to Quirk #26

---

## [1.9.0] — 2026-03-24

### feat: level health dashboard — unified audit score

**New tools (`level_health_report`, `level_health_open`):**
- `level_health_report` — headless: runs all 6 audit categories and returns a 0–100 health score with A+…F grade. Fully structured dict return — MCP/AI agent friendly.
- `level_health_open` — windowed UI: animated score ring, colour-coded category cards (green/yellow/red), per-issue summary text, live audit progress, and a console log pane.
- Six audit categories: Actor Integrity, Memory & Textures, Asset References, Naming Conventions, LOD & Collision, Performance — each scored proportionally and weighted.
- Aggregates results from 6 existing audit tools (`rogue_actor_scan`, `memory_scan_textures`, `ref_audit_orphans`, `rename_dry_run`, `lod_audit_folder`, `system_perf_audit`) — no duplicated logic.
- Audit runs on a background QThread so the UI stays responsive during scan.
- Added to dashboard Flagship Tools quick bar.
- Added `level_health_report` and `level_health_open` to CLAUDE.md Utilities table.

---

## [1.8.5] — 2026-03-24

### feat: ui icon importer — clipboard-first texture import

**New flagship tool (`ui_icon_import_open`):**
- Copy any image from a browser, Figma, Photoshop, or Paint and paste it with Ctrl+V directly into the window — imports as a UEFN texture in one step
- Three input paths: clipboard paste (Ctrl+V), click-to-browse file dialog, drag-and-drop image files
- Five texture presets covering all common UEFN UI needs: UI Icon (TC_UserInterface2D · NoMipmaps), Sprite/2D, Thumbnail, Normal Map, Default/Mipmapped
- Auto-detects project mount point for default destination (`/[Mount]/UI/Icons/`)
- Auto-prefixes `T_` on filenames per Epic naming convention
- Applies `post_edit_change()` + saves asset after settings — texture is fully configured on import
- Syncs Content Browser and selects the imported asset automatically
- `?` help dialog covers all presets, input methods, and the "why no mipmaps for UI" rationale
- Added to dashboard Flagship Tools quick bar

---

## [1.8.4] — 2026-03-24

### feat: prefab asset migrator — dependency-aware asset migration tool

**New flagship tool (`prefab_migrate_open`):**
- Walks the full Asset Registry dependency graph from seed assets — meshes pull in materials, materials pull in textures, nothing gets silently dropped
- Three ways to add assets: Content Browser selection, viewport actor selection (extracts mesh/BP paths from placed actors), manual path entry
- Two export modes: same-project copy via `EditorAssetLibrary.duplicate_asset()`, cross-project disk copy via `shutil.copy2` on raw `.uasset` files — auto-detected from destination path
- Flatten folder structure option — copies everything to one flat destination folder, no unwanted parent tree
- Dry run mode — full preview of what would be copied before committing
- Destination auto-fills from project mount point on first asset add (fixes UEFN `/Game/` invisibility quirk)
- `?` help button opens themed reference dialog covering workflows, options, and known limitations
- Added to dashboard Flagship Tools quick bar alongside Verse Device Graph

**UEFN path quirks fixed:**
- `unreal.Paths.project_content_dir()` returns FortniteGame engine path — fixed to use Asset Registry mount detection
- `/Game/` mount is invisible in Content Browser — tool uses project-named mount (e.g. `/Device_API_Mapping/`) derived from first asset added
- `AssetData.package_name` returns project-mount paths, not `/Game/` — dep resolver updated to handle any mount prefix

### fix: help dialog topbar redundancy + line wrap
- Removed redundant `make_topbar` from help dialogs in both prefab migrator and verse device graph — OS title bar already identifies the window
- Added `QTextEdit.NoWrap` to all read-only help/reference text areas — prevents separator lines from splitting across lines

### docs: ui style guide + CLAUDE.md — mandatory `?` help button rule
- Every tool window must have a `?` help button — codified as mandatory in `docs/ui_style_guide.md` with exact placement rules and copy-paste pattern
- `make_topbar` rule strengthened: no topbar unless it carries multiple real toolbar buttons, applies to sub-dialogs too
- Added `NoWrap` recipe for read-only text areas to style guide
- `docs/UEFN_QUIRKS.md` Quirk #23: `/Game/` mount invisible in Content Browser — full breakdown with correct detection pattern
- `CLAUDE.md` path format rule updated to reference Quirk #23

---

## [1.8.3] — 2026-03-23

### feat: verse device graph — minimap, category filter, focus button, help dialog, node tooltips

**Minimap (bottom-right canvas overlay):**
- Custom `QWidget` overlay — draws every node as a 3×3 colored dot matching its category color
- No scene re-render — edges never bleed into the thumbnail
- Blue viewport outline updates live as you pan/zoom the main canvas
- Click to teleport view, drag to pan — delta-based drag prevents jump-on-click jank
- Stays pinned to bottom-right corner via `scrollContentsBy` override (fixes vanish-on-drag)
- Updates correctly after Live mode rescans and Re-Layout

**Category filter dropdown:**
- Toolbar `QComboBox` populated after every SCAN with all unique device categories
- Selecting a category hides all other nodes and their edges instantly
- Search and category stack — filter to "Timer" then search within it
- Previous selection restored across rescans; "All Categories" resets

**Focus button:**
- Select any node, click Focus → view centres and zooms to that node
- Useful for navigating to a search result buried in a large graph

**Help dialog (`?` button):**
- Themed `_HelpDialog(ToolbeltWindow)` — scrollable reference window matching dashboard style
- Covers: purpose, why it was made, typical workflow, badge guide, edge types, tips, attribution
- Documents minimap, category filter, Focus, comment boxes, layout persistence, write-back

**Node badge tooltips:**
- `_make_node_tooltip(nd)` module-level function — every node shows a tooltip explaining
  cluster ID, VS badge, error (red !) and warning (yellow !) badges with full context

**Minimap vanish fix:**
- Root cause: `QWidget::scroll()` physically moves viewport child widgets during `ScrollHandDrag`
- Fix: `_GraphView.scrollContentsBy` override re-pins minimap to corner after every scroll tick

---

## [1.8.2] — 2026-03-23

### feat: verse device graph — blueprint-style grouped layout + comment boxes

**Grouped layout (default on SCAN):**
- Nodes now arranged in labelled category columns instead of the previous scattered circle
- Categories sorted by size (largest first), then alphabetically — related devices stay together
- Coloured header labels above each column match the node accent colour
- Multi-column overflow when a category exceeds 10 nodes
- Re-Layout button still runs animated Fruchterman-Reingold physics for freeform exploration

**Comment / note boxes (+ Note button):**
- Draggable, resizable annotation boxes — Blueprint-style, sit behind all nodes (z = −2)
- Semi-transparent coloured fill with a tinted header bar
- Double-click **header** → rename title (`QInputDialog.getText`)
- Double-click **body** → multi-line note content (`QInputDialog.getMultiLineText`)
- Body shows `"double-click to add notes…"` hint when empty; wraps text automatically
- Right-click context menu: 7 colour presets + Delete
- Resize by dragging the bottom-right corner handle
- Survive every scene rebuild (live sync, re-scan) via `to_dict()` snapshot in `_rebuild_scene`

---

## [1.8.1] — 2026-03-23

### feat: verse device graph — write-back, wiring codegen, search + physics fixes

**Write-back from property panel:**
- PROPERTIES section added to the side panel — Label and Folder fields, pre-filled on node select
- "Apply Changes" button pushes rename (`set_actor_label`) and folder move (`set_folder_path`) to the live level
- Disabled with hint for Verse-only devices that have no live actor
- Inline status feedback in panel and status bar on success or error

**Gen Wiring codegen:**
- "Gen Wiring" toolbar button generates a full `creative_device` Verse stub from the current graph
- Produces `@editable` device refs + `OnBegin` subscriptions + handler stubs
- Copy to clipboard + Write to project via `verse_write_file`
- Context-aware empty state: distinct messages for "no path set" vs "no connections found"
- Path field placeholder: `"Verse project path — required for wiring scan"`

**Search + physics fixes:**
- Search now syncs edge visibility (edges hide if either endpoint is filtered out)
- Physics sim skips hidden nodes — no more ghost jitter from invisible actors
- Selected node clears from panel when filtered out by search

**Dashboard + UI polish:**
- Spinbox minimum width enforced at 90px — no more number clipping against arrows
- Removed `::up-arrow`/`::down-arrow` CSS — prevented crash in UEFN's embedded Qt
- Dashboard title: removed `⬡` prefix
- All tool windows now use canonical TB icon (blue hexagon, white "TB") via `make_toolbelt_icon()`
- Flagship Tools group added to Quick Actions tab (Verse Graph, World State, Device Catalog)
- `ToolbeltWindow` title format documented: `"UEFN Toolbelt — Tool Name"`

---

## [1.8.0] — 2026-03-23

### feat: lighting, post-process, audio foundation (217 → 229 tools)

**Expanded `lighting_mastery.py` — 4 new tools:**
- `light_place`: Spawn point/spot/rect/directional/sky light at camera. Sets intensity, hex color, attenuation radius.
- `light_set`: Batch-set intensity, color, attenuation on selected lights. Only provided params are changed.
- `sky_set_time`: Simulate time-of-day (0–24h) by pitching the DirectionalLight using elevation math.
- `light_list`: Audit all light actors in the level — type, label, location, intensity.

**New `postprocess_tools.py` — 4 new tools:**
- `postprocess_spawn`: Find or create a global (infinite-extent) PostProcessVolume. No duplicates.
- `postprocess_set`: Set bloom, exposure, contrast, vignette, saturation on the level's PPV.
- `postprocess_preset`: Apply a named visual preset: `cinematic`, `night`, `vibrant`, `bleach`, `horror`, `fantasy`, `reset`.
- `world_settings_set`: Change gravity (cm/s²) and time dilation world-wide.

**New `audio_tools.py` — 4 new tools:**
- `audio_place`: Spawn AmbientSound at camera. Optionally assign `/Game/...` sound asset, set volume and radius.
- `audio_set_volume`: Batch-set volume multiplier on selected AmbientSound actors.
- `audio_set_radius`: Override attenuation falloff radius on selected sounds.
- `audio_list`: Audit all AmbientSound actors — label, folder, asset, volume.

**Fixed:**
- `register_tool()` decorator: removed invalid `parameters={}` kwarg from all new tools.
- `lighting_mastery.py`: refactored to match project patterns — `_actor_sub()` helper, `log_info/error`, `undo_transaction`.

---

## [1.7.0] — 2026-03-23

### feat: zone tools, proximity placement, auto-cluster, class replace (204 → 217 tools)

**New modules — 13 new tools (204 → 217):**

- **`zone_tools.py`** (7 tools) — Full zone lifecycle management.
  `zone_spawn`: spawn a visible cube zone marker at the camera position with configurable
  width/depth/height. `zone_resize_to_selection`: resize and reposition a zone actor to
  exactly contain all other selected actors (with optional padding). `zone_snap_to_selection`:
  move zone center to match combined bounds without resizing. `zone_select_contents`: select
  every level actor whose pivot falls inside the zone bounds (with optional expand).
  `zone_move_contents`: move zone + all actors inside it by a world-space offset as a unit.
  `zone_fill_scatter`: fill zone volume with scattered copies of an asset using Poisson-style
  min-spacing. `zone_list`: list all zone actors with their dimensions and world position.
  Works with any box-shaped actor as the zone reference — mutator zone devices, trigger
  volumes, or our spawned cube markers.

- **`proximity_tools.py`** (6 tools) — Relative placement and batch automation.
  `actor_place_next_to`: move the last selected actor flush against the first on any face
  (+X/-X/+Y/-Y/+Z/-Z) with optional gap and center-alignment. Uses world bounds for accuracy.
  `actor_chain_place`: arrange selected actors end-to-end along an axis — each actor's min
  face touches the previous actor's max face (great for walls, corridors, fences).
  `actor_duplicate_offset`: duplicate selected actors N times with exact cumulative offset —
  stamp arrays, rows, and grids without manual copy-paste.
  `actor_replace_class`: replace every actor whose class/label matches a filter with a fresh
  instance of a new asset — preserves transform, label, folder. Always `dry_run=True` first.
  `actor_cluster_to_folder`: greedy XY-proximity clustering — groups nearby actors into World
  Outliner subfolders automatically (great for cleaning up large levels).
  `actor_copy_to_positions`: stamp copies of a selected actor at every position in a
  `[[x,y,z],...]` list — batch placement from generated coordinates.

**Dashboard improvements:**
- Zone Spawner group added to Procedural tab — spawn, fill, resize, snap, select, move
- Proximity & Duplication group added to Bulk Ops tab — place next to, chain, duplicate
  offset, replace class (dry run + execute), auto-cluster

---

## [1.6.0] — 2026-03-23

### feat: actor organization, advanced alignment, sign tools, PCG scatter, camera-spawn

**New modules — 33 new tools (171 → 204):**

- **`sign_tools.py`** (7 tools) — TextRenderActor signs, NOT Fortnite Billboard devices.
  `sign_spawn_bulk`: spawn N signs in row/column/grid at camera. `sign_batch_edit`: change
  text/color/size on all selected signs at once. `sign_batch_set_text`: assign individual
  strings per sign. `sign_batch_rename`: sequential rename with optional text sync.
  `sign_list` / `sign_clear`: audit and cleanup. `label_attach`: floating text label above
  selected actor, parented so it follows — perfect for NPC name tags. Supports yaw rotation.

- **`actor_org_tools.py`** (10 tools) — Full actor organization suite.
  `actor_attach_to_parent`: last-selected becomes parent, Maya-style. `actor_detach`: detach
  preserving world transforms. `actor_move_to_folder` / `actor_move_to_root`: one-click folder
  management. `actor_rename_folder`: re-path all actors in a folder. `actor_select_by_folder` /
  `actor_select_same_folder` / `actor_select_by_class`: selection helpers. `actor_folder_list`:
  full folder map with actor counts. `actor_match_transform`: copy loc/rot/scale from first
  selected to all others.

- **`advanced_alignment.py`** (6 tools) — Beyond the basic bulk_align/bulk_distribute.
  `align_to_reference`: snap axis to first/last selected actor's position.
  `distribute_with_gap`: exact cm gap between bounding boxes (not pivot-to-pivot).
  `rotate_around_pivot`: orbit selection around center-of-bounds or first actor.
  `align_to_surface`: snap_objects_to_floor with Z offset. `match_spacing`: even pivot
  spacing between endpoints. `align_to_grid_two_points`: local grid from two anchor actors.

- **`foliage_tools.py`** additions (2 tools) — PCG-style scatter.
  `scatter_avoid`: Poisson scatter with obstacle rejection (avoid_class / avoid_radius filters).
  `scatter_road_edge`: place props along both shoulders of a path defined by waypoints or
  SplineActor — resamples at spacing intervals, offsets perpendicular to tangent.

**Dashboard improvements:**
- All spawn/scatter/pattern buttons now read viewport camera position at click time
- Fixed `lambda s=s:` bug: PySide6 `clicked(bool)` signal was overriding loop variable
- Fixed pattern buttons: was passing `center=` but tools expect `origin=`
- PCG Scatter group added to Procedural tab
- Advanced Alignment + Actor Organization groups added to Bulk Ops tab
- Sign Spawner, Sign Batch Edit, Floating Label Attach groups added to Text tab

**Fixes:**
- `scatter_avoid` with no filter was treating all 2000 level actors as obstacles — now
  requires at least one filter to be set
- `scatter_road_edge` rewritten to accept `points=[[x,y,z],...]` waypoint list — no
  SplineActor required
- Arena buttons: `apply_team_colors=True` was landing as `size` arg due to signal bool —
  fixed with `lambda *_, s=s:`
- `sign_tools` naming: all tools renamed from `billboard_*` to `sign_*` to avoid confusion
  with Fortnite Billboard devices (V2, not Python-controllable)

---

## [1.5.3] — 2026-03-22

### feat: online plugin hub, describe_tool mcp command, attribution

- **Plugin Hub tab** — "Browse Online Hub" section fetches `registry.json` live from GitHub.
  Core tools (BUILT-IN badge, green cards, by Ocean Bennett) and Community Plugins (Install button)
  render as separate sections. Cache-busted with `?t=<timestamp>` on every refresh.
- **`registry.json`** (new) — GitHub-hosted community plugin index. 10 core tool entries,
  community plugin entry format documented. PRs welcome to add third-party tools.
- **`describe_toolbelt_tool`** MCP command — returns full parameter schema for any single tool
  without loading the entire `tool_manifest.json`. AI agents use this before calling
  `run_toolbelt_tool()` to verify parameter names, types, and defaults.
- **Attributions** — ImmatureGamer (verse device graph concept) and Kirch/@KirchCreator
  (MCP server concept) credited in source, README, and About tab.
- **docs**: `README.md` Plugin Hub & Community Ecosystem section; `plugin_dev_guide.md`
  Path A (registry listing) vs Path B (core PR) distribution guide; `CLAUDE.md` updated.

---

## [1.5.2] — 2026-03-22

### feat: setup status panel, coverage improvements, pyside6 multi-drive detection

- **Setup Status panel** — First-run health badge in Quick Actions tab. Five checks:
  PySide6 (✓/✗), tool registry count ≥ 171 (✓/✗), MCP bridge bound port (✓/⚠),
  config file (✓/✗), verse-book (✓/⚠). Shows on every dashboard open.
- **`install.py`** — PySide6 auto-detect now scans C/D/E drives and known Game Pass paths
  instead of hardcoded `C:\Program Files`. `_find_ue_python()` and `_ensure_pyside6()`
  added. Install flow is now 3 clearly labeled steps.
- **`deploy.bat`** — PySide6 check loops over C/D/E drives. Added
  `!! TEST IN UEFN BEFORE COMMITTING !!` banner at end of deploy.
- **`list_untested.py`** — Fixed repo root path (was resolving to `Content/` not repo root).
  Broad string literal detection catches tools listed in test arrays, not just `run("name")`
  calls. CI exit codes added (0 = full coverage, 1 = gaps). Coverage improved 69% → 78%.
- **Two-phase validation workflow** documented in `CLAUDE.md`, `plugin_dev_guide.md`,
  `deploy.bat`, and persistent memory: Phase 1 = `ast.parse()` syntax check; Phase 2 = live
  UEFN test with hard refresh bundle before every commit.

---

## [1.5.1] — 2026-03-22

### refactor: theme system — single source of truth for all UI colors

- **`core/theme.py`** (new) — `PALETTE` dict is now the one place to change any color
  platform-wide. `QSS` is built dynamically from `PALETTE` so editing a token value
  automatically updates every widget in every window without any other changes.
- **`core/base_window.py`** (new) — `ToolbeltWindow(QMainWindow)` base class.
  Subclass instead of `QMainWindow` directly to get:
  - Dashboard QSS applied automatically
  - Slate tick driver via `show_in_uefn()` (required in UEFN)
  - `self.P` palette dict, `self.hex(token)`, and widget factory helpers
    (`make_topbar`, `make_btn`, `make_label`, `make_divider`, `make_text_area`,
    `make_hbar`, `set_hbar_value`, `make_scroll_panel`)
- **`dashboard_pyside6.py`** — `_QSS` now imported from `core/theme.py` instead of
  defined inline. No behavior change; backward-compatible.
- **`tools/verse_device_graph.py`** — `_DeviceGraphWindow` now subclasses
  `ToolbeltWindow`. Removed 45 lines of manual boilerplate (`_DASH_QSS` import block,
  `_P` dict, Slate tick registration). `_P` rebuilt from `PALETTE` for
  `QGraphicsItem` usage.
- **`core/__init__.py`** — re-exports `PALETTE`, `QSS`, `theme_color`.
- **`docs/ui_style_guide.md`** — fully rewritten to document the new architecture,
  `ToolbeltWindow` API, palette tokens, QGraphicsScene theming, and AI agent rules.

---

## [1.5.0] — 2026-03-22

### feat: verse device graph (verse_graph_open / scan / export)

Three new MCP-callable tools for visualising Verse/Creative device architecture:

- **`verse_graph_open`** — Opens a PySide6 force-directed node graph window.
  Devices are nodes; `@editable` references are edges. Animated Fruchterman-Reingold
  layout, cluster detection (Union-Find), and an Architecture Health Score (0–100).
- **`verse_graph_scan`** — Headless scan. Returns full adjacency dict so Claude Code
  can reason about island architecture without a UI.
- **`verse_graph_export`** — Exports the full graph as JSON.

Config key `verse.project_path` added so users set their Verse folder once.

### docs: ui style guide

- **`docs/ui_style_guide.md`** (new) — Canonical color palette, QSS import pattern,
  Slate tick driver, widget recipes, "what NOT to do" list, AI agent rules.
- **`CLAUDE.md`** — "UI Consistency Rule" section added near top; key file table updated.
- **`docs/plugin_dev_guide.md`** — UI Style Requirements section added with copy-paste
  snippets for plugin authors.

---

## [1.4.0] — 2026-03-21

### feat: 165 tools — selection utilities, project admin, lighting mastery, sequencer, sim proxy, config tools

Six new tool modules added in Phase 19:

- **`selection_utils`** — Smart selection by class, material, tag, proximity, bounding box.
- **`project_admin`** — Project health report, folder audits, cleanup workflows.
- **`lighting_mastery`** — Batch lightmap resolution, light channel manager, stationary light audit.
- **`sequencer_tools`** — Level sequence helpers, track export, timing utilities.
- **`sim_device_proxy`** — Read Verse simulation device state without entering PIE.
- **`config_tools`** — Dashboard-accessible `config_get` / `config_set` / `config_list` / `config_reset`.

### docs: schema deep dive and explorer updates

- `docs/SCHEMA_DEEP_DIVE.md` — Full type taxonomy, network architecture, enum tables.
- `docs/SCHEMA_EXPLORER.md` — Updated with 19-class tutorial level analysis.

---

## [1.3.0] — 2026-03-20

### feat: Phase 18 — AI-agent readiness (structured returns, tool manifest)

- All 25+ core tools updated to return `{"status", "count", "data"}` structured dicts.
  MCP callers can read results directly without parsing log output.
- **`plugin_export_manifest`** tool — generates `Saved/UEFN_Toolbelt/tool_manifest.json`
  with full parameter signatures for all registered tools.
- `schema_utils.py` added — `validate_property`, `discover_properties`, `list_classes`,
  `get_class_info` for schema-aware tool development.

---

## [1.2.0] — 2026-03-18

### feat: custom plugin system with four-gate security model

- Custom plugins auto-load from `Saved/UEFN_Toolbelt/Custom_Plugins/`.
- Four security gates: file size limit (50 KB), AST import scanner, namespace
  protection, SHA-256 integrity hash written to `plugin_audit.json`.
- `docs/plugin_dev_guide.md` published.

---

## [1.1.0] — 2026-03-15

### feat: MCP bridge + PySide6 dashboard

- `tools/mcp_bridge.py` — HTTP listener on port 8765. Claude Code connects via `.mcp.json`.
- `dashboard_pyside6.py` — 18-tab dark-theme Qt dashboard (`tb.launch_qt()`).
- Slate post-tick pattern documented in `docs/UEFN_QUIRKS.md`.

---

## [1.0.0] — 2026-03-10

### feat: initial release — 140 tools across 20 categories

Core tool categories: Materials, Procedural/Layout, Bulk Operations, Foliage,
LOD/Optimization, Asset Management, Reference Auditor, Level Snapshot, Asset Tagger,
Screenshot, Text/Signs, Verse Tools, Project Scaffold, API Explorer, Plugin Management.
