# WO-004 Session A — Modal Observability Feasibility

STATUS: SESSION A FEASIBILITY RECORD

AUTHORIZATION: READ-ONLY PLANNING — NO LIVE UEFN WORK PERFORMED

SESSION_A_AUTHORIZATION_COMMIT: `f9fc7268d63dad92f5dd009bbf20e11477b8f926`

**Record status (added 2026-09-12).** Sections 1–5 are the Session A planning
record as committed at `aef5f6ea1f8fcb8b86d4eea4ebf68d69a8b10697`, preserved
unchanged. The `AUTHORIZATION` line above and the statements in Sections 1–5 that
nothing was executed describe that point in time. Owner-operated live
observations made on 2026-09-12 are appended in
[Section 6](#6-live-probe-a-observations-2026-09-12); they add to the planning
findings and do not rewrite them.

## Scope and authority

Session A was authorized for read-only feasibility planning under the root
`WORKORDER.md` gate `WO-004 SESSION A AUTHORIZED — READ-ONLY FEASIBILITY
PLANNING ONLY`. This record is the whole of its output.

Nothing here was executed. No editor was launched, no bridge was started, no
official-MCP call was made, no level was opened or mutated, and no probe in
[Section 4](#4-proposed-owner-operated-probes-not-executed) was run. Those
probes are proposals; each needs its own separate owner gate.

## Method, and what it cannot settle

Three source classes were inspected: repository source, the repository's own
API-dependency manifest, and the repository's audit records. No live runtime
was queried, which bounds every conclusion below — see Section 1.

## 1. Supported editor, window, and modal APIs

### 1.1 The repository holds no authoritative UEFN API enumeration

`CLAUDE.md` describes `docs/uefn_reference_schema.json` as "The Gospel. A 1.6MB
baseline reference for all core UEFN/Fortnite classes." The file's own contents
do not support that description. Its top-level keys are:

```json
{"scan_target": "level_unique_classes", "total_actors": 76,
  "unique_classes": 14, "classes": {...}}
```

It is a level scan of 14 classes — `Actor`, `BuildingFloor`, `BuildingProp`,
`FortCreativeDeviceProp`, `FortInspectorCameraCreative`,
`FortMinigameSettingsBuilding`, `FortPlayerStartCreative`,
`FortStaticMeshActor`, `FortWaterBodyActor`, `LevelBounds`, `TextRenderActor`,
`WaterZone`, and two more. A case-insensitive search of those class names for
`modal`, `dialog`, `window`, `slate`, `notification`, `message`, or `editor`
returns nothing.

**Consequence.** This file cannot establish that a modal-state API exists, and
it cannot establish that one is absent. It is not evidence either way, and any
future claim that "the reference schema was checked" should be read with that
in mind.

### 1.2 What Toolbelt actually depends on

`Content/Python/UEFN_Toolbelt/api_dependencies.json` is a real inventory: 171
`unreal.*` symbols extracted from the package by `ast` in
`scripts/gen_api_manifest.py`, and probed against the live runtime by
`smoke_test` Layer 2. Searching all 171 for the same six terms — `modal`,
`dialog`, `window`, `slate`, `notification`, `message` — returns exactly four
symbols, all of them tick registration (—the seventh term from Section 1.1,
`editor`, returns 16 and is treated separately below):

- `register_slate_post_tick_callback`
- `register_slate_pre_tick_callback`
- `unregister_slate_post_tick_callback`
- `unregister_slate_pre_tick_callback`

There is no `EditorDialog`, no window-state accessor, and no modal accessor.

The manifest does hold fifteen editor-facing symbols — eleven beginning
`Editor`, plus four more containing it — among them
`EditorLoadingAndSavingUtils`, `UnrealEditorSubsystem`, `EditorActorSubsystem`,
`EditorAssetLibrary`, and `EditorUtilityLibrary`. Because the recorded incident
was a **Save Content** modal, `EditorLoadingAndSavingUtils` is the nearest
relevant entry, and it deserves a named negative result: nothing in it reports
whether a save dialog is open. It exposes save operations, not save-dialog
state. None of the fifteen carries window or dialog state.

### 1.3 Existence in Unreal is not availability in UEFN

This distinction is load-bearing, and the repository already records three
instances of it:

- `CLAUDE.md`: "UEFN omits some standard UE5 APIs: `KismetMaterialLibrary` is
  absent, `/FortniteGame/` asset paths are blocked, some editor factories may
  not be exposed."
- `CLAUDE.md`: the `Toolbelt` top-menu entry "registers but never renders on
  UEFN 42.00 — Epic sandboxes `ToolMenus` for third-party Python." An API that
  accepts a call and silently does nothing is the exact failure mode a
  source-only search cannot detect.
- `docs/UEFN_QUIRKS.md` Quirk #34: UEFN sandboxes `BodyInstance.bSimulatePhysics`
  **reads** while the write path works.

A UE5 documentation entry for a dialog or window API would therefore not
establish availability here. Only the live runtime can.

### 1.4 Finding

Within the inspected supported surface, **no modal-, dialog-, or window-state
API is present**.

This is *not* a claim of exhaustive unavailability. The live `unreal` module
was not enumerated, because doing so requires the editor. Section 4 Probe B is
the step that would convert this into an availability answer.

## 2. Execution during a blocking dialog

### 2.1 Documented guarantees

None found. No repository document states what happens to a Slate post-tick
callback while a modal dialog is open. No Epic documentation asserting it
either way was available to this session.

### 2.2 Established from source

All three are directly readable in
`Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py`:

| Fact | Location |
|---|---|
| Commands cross threads through a `queue.Queue` | `:114` |
| `_tick()` drains that queue; every QUEUED COMMAND's `unreal.*` work runs inside it | `:1001-1024`, drain loop `:1006-1016` |
| `_tick` is registered with `unreal.register_slate_post_tick_callback` | `:1072` |

The HTTP server runs on a daemon thread and only enqueues; the module docstring
states the reason plainly — "All `unreal.*` calls must happen on the editor's
main thread."

To be exact: 71 lines of `mcp_bridge.py` contain `unreal.`, including logging
at `:151-155` and the handoff path at `:768`. The claim that matters is
narrower — every *queued command* executes its `unreal.*` work inside `_tick`,
on the main thread. That is what Section 2.3 rests on.

**A heartbeat already exists, and nothing reads it.** `_tick_health` is
declared at `:109`, incremented on every tick at `:1004`, and never read
anywhere. `get_status()` at `:1183-1195` returns `running`, `port`, `url`,
`commands`, `transport`, `authenticated`, and `execute_python_enabled` — not
tick health. The counter is write-only today.

### 2.3 The HTTP thread is alive, but the bridge exposes nothing from it

The HTTP daemon thread is an ordinary Python thread and is not the thread a
Slate modal blocks. That much follows from the threading model above.

**It does not follow that any command can be answered from it.** `do_POST`
enqueues *every* command unconditionally and then polls for a response:

```python
_command_queue.put((req_id, command, params))          # mcp_bridge.py:932
deadline = time.time() + HTTP_TIMEOUT_SEC              # :934, 30.0s at :93
while time.time() < deadline:
    ...  if req_id in _responses: ...                  # :935-941
else:
    self._error(504, f"Command timed out: {command}")  # :942
```

`_responses` receives *command results* only from `_tick` (`:1015`), and
`_execute_command` is called from exactly one place — `:1012`, inside `_tick`.
(`stop_listener` writes a shutdown entry at `:1154` and the HTTP thread pops at
`:938`; neither serves a command.) `ping` is no exception: `_c_ping` is an
ordinary handler reached through `_dispatch` inside `_execute_command`. **No
command in this bridge is served from the HTTP thread.**

So a status surface that answers while the main thread is stalled does not
exist today and cannot be demonstrated by calling any existing command. That is
a Session B design question, not a Session A observation.

One consequence is still observable, and Probe C targets exactly it: the 504 at
`:942` is produced *by the HTTP thread*, after its own 30-second deadline. If a
504 comes back while a modal is held open, the HTTP thread demonstrably ran for
those 30 seconds while the main thread never drained the queue.

### 2.4 The decisive unknown

**Does `register_slate_post_tick_callback` keep firing while a modal dialog is
open?**

This cannot be settled from repository source. It matters more than anything
else here, because the two outcomes point in opposite directions:

- If post-tick callbacks **stop** during a modal, `_tick_health` stalls, and an
  external reader can detect the stall.
- If they **continue** — which is plausible, since Unreal modal windows pump
  their own Slate loop — `_tick_health` advances normally and a tick heartbeat
  detects nothing at all.

Two assumptions are explicitly *not* made here: that every modal stops every
callback, and that an `unreal.*` API could safely be called from the HTTP
thread to work around it. The second is forbidden by `CLAUDE.md` rule 2 and is
the entire reason the queue-and-tick design exists.

### 2.5 A stall is not a modal

Even in the favourable outcome, a stalled heartbeat means "the main thread is
not servicing ticks." A modal is one cause. A long synchronous main-thread
operation, an editor hang, and a crash are others, and a heartbeat alone cannot
separate them.

That supports reporting `unknown` or `pending` with evidence, which is what the
mandate's status table already makes the default. It does **not** support
reporting `modal_blocked`, which the mandate requires to come from a positive
signal proven in this session. No such signal was found.

### 2.6 Transport boundary

Toolbelt's tick runs on the editor's main thread — the same main thread the
official-MCP call in the recorded incident was waiting on. A Toolbelt-side
heartbeat could therefore, at best, indicate that the shared editor main thread
is stalled. It could not attribute that stall to the official call, correlate
it with a specific official operation, or observe official-MCP state. The
mandate's transport table already forbids any claim otherwise.

## 3. Primary evidence for the 2026-08-24 incident

The incident appears in exactly two places in the cited audit, both narrative:

- `docs/audits/2026-08-24-uefn-42-official-mcp-audit.md:68`, in the owner-action
  list: "closed a Save Content modal that was blocking queued MCP work"
- the same file `:274-276`, P1 finding 4: "A Save Content modal blocked an
  official queued call for approximately four minutes and resumed immediately
  after owner action; agentic automation lacks modal observability."

`docs/audits/evidence/` contains two artifacts,
`2026-08-24-official-mcp-signatures.json` and
`2026-08-27-wo002-session-b-official-mcp.json`. Neither concerns the modal.

**Recorded absence.** No log excerpt, timestamp range, screenshot, or evidence
file preserves this specific four-minute block. The phrase "approximately four
minutes" is the only quantitative claim, and nothing in the repository
substantiates it. The mandate anticipated this and forbade manufacturing a
substitute; none was manufactured. Every reference elsewhere — in the completed
WO-003 document and in the WO-004 mandate — cites the same two narrative lines,
so the corroboration is circular rather than independent.

## 4. Proposed owner-operated probes (NOT executed)

Each needs its own owner gate. Per `CLAUDE.md`, any MCP-bridge work starts with
`deploy.bat`, then a **full UEFN restart**, in the disposable `TOOL_TEST` level.
Record the UEFN MCP Toolsets beta state per run, since Quirk #36 suppresses the
project startup script when it is enabled.

### Probe A — does the post-tick callback fire during a modal?

The decisive experiment. Requires no repository change.

```python
# UEFN Python console. Writes one scratch file; touches no level state.
#
# It resolves the log path the same way the bridge resolves its own handoff
# (mcp_bridge.py:762-771) and PRINTS it, because per CLAUDE.md
# unreal.Paths.project_saved_dir() returns the EDITOR-level Saved directory,
# not the project's. Read the printed path; do not assume either location.
import unreal, time, json, pathlib
# Re-registering without unregistering ORPHANS the previous callback: the C++
# side keeps calling into a freed Python object. Quirk #26 documents exactly
# this - "callbacks on the Unreal C++ side (Slate tick drivers, HTTP
# listeners, timer handles)" whose "C++ registrations remain live even after
# the Python objects are freed", giving an EXCEPTION_ACCESS_VIOLATION with no
# Python traceback and nothing catchable.
#
# The broad except is deliberate and matches the bridge's own cleanup at
# mcp_bridge.py:1135-1138: it covers both the first run (_h undefined) and a
# re-run whose handle was already unregistered.
try:
    unreal.unregister_slate_post_tick_callback(_h)
except Exception:
    pass
run = time.strftime("%H%M%S")
log = (pathlib.Path(str(unreal.Paths.project_saved_dir()))
       / ("wo004_tick_probe_" + run + ".jsonl"))
print("[WO-004 probe] run", run, "writing to:", log)
state = {"n": 0}
def _probe(dt):
    state["n"] += 1
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"n": state["n"], "t": time.time()}) + "\n")
_h = unreal.register_slate_post_tick_callback(_probe)
```

Owner then, in order: let it run ~15s untouched; open a Save Content modal and
leave it open ~30s; close it; let it run ~15s; then

```python
unreal.unregister_slate_post_tick_callback(_h)
```

**Expected observations.** The timestamp series answers the question directly.
A gap spanning the modal means callbacks stop and a heartbeat is viable. An
unbroken series means callbacks continue and the heartbeat approach is dead —
which is a complete and acceptable result.

**Negative controls.** (1) The quiet 15s before the modal establishes the
normal cadence and proves the recorder works. (2) Repeat with no modal opened
at all: the series must show no comparable gap, or the gap is not attributable
to the modal. The re-run writes to its own timestamped file, so the two series
are never interleaved and the counter never restarts inside one file.

**Ordering.** Probe A must be unregistered before Probe B, before any reload,
and before closing the editor. A live callback surviving into a module reload
is the Quirk #26 crash — `docs/UEFN_QUIRKS.md:817`, whose mechanism section
names "Slate tick drivers" among the stale C++ registrations. (Quirk #38 is the
neighbouring Qt/Shiboken case, which applies when a Toolbelt *window* is open;
Probe A opens none. Note that the quirks file uses two heading styles, `## 26.`
for the early entries and `## Quirk #38 —` for the later ones, so a search for
the literal string "Quirk #26" finds only cross-references.)

**Limitations.** One modal type, one UEFN version, one machine. A Save Content
modal may behave differently from a validation dialog. Writing to disk from the
tick callback perturbs timing slightly; a gap much larger than the write cost
is what matters, not millisecond precision.

### Probe B — what modal or window APIs exist in the live runtime?

Read-only introspection, which is what turns Section 1.4 into an answer.

```python
# A bare import registers NOTHING - tb.run() would return "Unknown tool".
# When the UEFN MCP Toolsets beta is on, Quirk #36 also suppresses the startup
# script, and tb.register() is the documented recovery for that editor session.
import UEFN_Toolbelt as tb
tb.register_all_tools()
for q in ("dialog", "modal", "window", "slate", "notification", "message"):
    tb.run("api_search", query=q)
for name in ("EditorDialog", "EditorLoadingAndSavingUtils",
             "UnrealEditorSubsystem", "EditorUtilityLibrary"):
    tb.run("api_inspect", name=name)
```

**Expected observations.** A candidate is only a candidate if it both exists
and is readable. Per Section 1.3, record for each hit whether it returns a
value or fails silently — `ToolMenus` registers and never renders, and
`bSimulatePhysics` reads are sandboxed while writes work.

**Negative control.** `api_inspect` on a name known to be absent, to confirm
the tool reports absence rather than returning something empty-but-truthy.

### Probe C — does the HTTP thread keep running while the main thread is blocked?

Section 2.3 already settles from source that no command is answered from the
HTTP thread, so the obvious version of this probe — "`ping` returns while
`run_tool` stalls" — cannot happen and is not proposed. What remains
observable is the 504: it is generated by the HTTP thread after its own
30-second deadline, so receiving one proves that thread ran while the main
thread did not drain the queue.

In the UEFN console, after a full restart:

```python
import UEFN_Toolbelt as tb
tb.register_all_tools()
tb.run("mcp_start")
```

Then from an external shell, with the owner **holding the modal open for at
least 40 seconds** — comfortably past `HTTP_TIMEOUT_SEC = 30`.

This matters. Release the modal sooner and `_tick` resumes, drains the queue,
and `ping` returns normally — a result that is **void**, not evidence. Read as
row 2 below it would also produce a false negative on Probe A. Probe A's own
"~30s" hold sits exactly on the deadline, so do not reuse that timing here.

The client default timeout is 30.0s, identical to the server's, so it must be
raised explicitly or the socket may time out before the 504 is written:

```python
from client import ToolbeltClient
ue = ToolbeltClient(timeout=60)            # must exceed HTTP_TIMEOUT_SEC = 30
ue.ping()
```

**Expected observations.** Exactly one of:

| Outcome | What it means |
|---|---|
| `ToolbeltError: UEFN MCP request rejected with HTTP 504` after ~30s | The HTTP thread ran throughout while the main thread never drained. Section 2.3 confirmed |
| `ping` returns normally, modal held past 40s | Post-tick callbacks are still firing during the modal — which also answers Probe A, in the negative |
| `ping` returns normally, modal released before the request's own 30s deadline elapsed | **Void.** The queue drained once the modal closed, so this says nothing about callbacks during the modal. Re-run with a longer hold |
| Socket-level `CommandTimeout`, no 504 | The HTTP thread did NOT complete its deadline loop. Section 2.3's premise is wrong |

Note the exception class: a 504 is an `HTTPError`, which `client.py:165-170`
maps to `ToolbeltError`, **not** `CommandTimeout`. `CommandTimeout`
(`client.py:179-183`) fires only on a socket timeout. Expecting the wrong class
would misread the result.

**Negative control.** The same call with no modal open must return promptly.

**Limitation.** This shows the HTTP thread is alive; it does not provide a
status surface. Adding one is Session B work and is out of scope here.

### Cleanup for every probe

Stop the listener; close UEFN; confirm the handoff file is absent and ports
8765—8770 are closed; leave `TOOL_TEST` unsaved and unmutated; delete every
`wo004_tick_probe_*.jsonl` at the directory Probe A printed. Unregister any callback registered by
Probe A
before closing the editor — a live callback against freed Python objects is
Quirk #26 territory.

## 5. Conclusion

**UNKNOWN, with the missing evidence named.**

Not "supported candidate": no supported modal-state API was found in the
inspected surface, and the one mechanism that looks promising — the existing
write-only `_tick_health` heartbeat — rests on an unverified assumption about
whether post-tick callbacks fire during a modal.

Not "unavailable": the live `unreal` module was never enumerated, so a
source-only search cannot support that claim. Section 1.4 is bounded on
purpose.

The precise missing evidence is three items, in dependency order:

1. **Whether `register_slate_post_tick_callback` fires while a modal is open**
   (Probe A). If it does, the heartbeat approach is dead and Session B should
   be re-scoped or dropped.
2. **Whether any modal- or window-state API exists and is readable in the live
   UEFN 42.00 runtime** (Probe B).
3. **Whether the HTTP thread keeps running while the main thread is blocked**
   (Probe C). Partly settled here already: no command is answered from that
   thread (Section 2.3), so what remains is whether its 504 path completes
   during a modal. A status surface that answers while blocked does not exist
   and would be Session B work.

Even if all three resolve favourably, they would support a `pending`/`unknown`
signal backed by a stall observation. They would **not** establish
`modal_blocked`, and they would not observe official-MCP state.

**Next gate.** A separate owner authorization to run Probes A—C in `TOOL_TEST`.
Feasibility is not proven, no dependent implementation may begin, and Session B
remains closed and un-scoped until Probe A returns.

## 6. Live Probe A observations (2026-09-12)

### 6.1 Provenance and scope

This section was recorded after the live runs. Sections 1–5 are unchanged.

The owner authorized live execution of Probe A during the working session on
2026-09-12 and personally operated UEFN and every dialog. The Python-opened
message-box run in 6.6 was separately authorized in the same session. Root
`WORKORDER.md` was **not** changed for these runs and still reads
`WO-004 SESSION A AUTHORIZED — READ-ONLY FEASIBILITY PLANNING ONLY`; the live
runs were authorized in-session, not through an updated pointer gate. No
implementation, bridge, MCP call, save, or import took place.

### 6.2 Configuration

| | |
|---|---|
| Date and clock | 2026-09-12. Local times are UTC−4. Editor-log timestamps are UTC; the offset was calibrated against the probe's own printed start time. |
| Editor | Engine Version `6.0.0-57819926+++Fortnite+Release-42.10`, branch `++Fortnite+Release-42.10`, Net CL `56443220`, Shipping build, Windows 11 (25H2) |
| Version fields | The running editor reported `Release-42.10` in its Engine Version and branch fields, above. `TOOL_TEST.uefnproject` separately declares `"compatibilityVersion": "42.00"`; that is a project field and does not identify the running editor build. The mandate's fixture list names 42.00, and session summaries written during the runs described the editor as 42.00 in error. |
| Project and level | `TOOL_TEST` |
| Project settings | `bEnablePythonForProject: true` and `bEnableToolsetsForProject: true`, read from `TOOL_TEST.uefnproject` |
| Toolbelt bridge | Not started. At every check made before and after the runs, ports 8765–8770 were not listening and no handoff file existed. |
| Deployment | None. The probe scripts import no Toolbelt module. |

### 6.3 Scripts actually executed

The code block in Section 4 is **not** byte-identical to what ran. The executed
scripts are preserved exactly in the evidence directory (6.12):

| File | Role | Difference from Section 4 |
|---|---|---|
| `wo004_probe_a.py.txt` | tick recorder | Distinguishes a first run (no prior handle) from a failed unregistration and halts on failure, instead of `except Exception: pass`. Halts if registration returns no handle. Uses `_wo004_*` global names. |
| `wo004_probe_a_stop.py.txt` | stop | Unregisters and confirms; halts on failure. Section 4 has no separate stop script. |
| `wo004_dialog_api_check.py.txt` | read-only attribute check | Not in Section 4. Opens nothing. |
| `wo004_dialog_probe.py.txt` | Python-opened message box | Not in Section 4. See 6.6. |

They carry a `.txt` suffix because two `raise` statements inside `except` blocks
omit `from`, which the repository's ruff configuration reports as B904
(`wo004_probe_a.py:28`, `wo004_probe_a_stop.py:23`). Stored as `.py` they would
fail the lint gate; editing them would break byte-exactness. Their content is
unchanged.

### 6.4 Runs

Tick counts and gaps are computed from the tick logs. In every run the `n`
counter is contiguous, so no writes were dropped.

| Run | Dialog, as observed by the owner | Ticks and span | Longest callback gap | Next-longest |
|---|---|---|---|---|
| `162950` | **None.** The dialog step was not performed: the instruction was buried in a long message. Recorded as an idle observation. | 3,214 ticks, 16:29:50.028–16:32:50.545 (180.5 s) | **27.781 s**, 16:32:09.740 to 16:32:37.521 | 0.460 s |
| `170615` | None. Idle control. | 310 ticks, 17:06:15.608–17:07:19.004 (63.4 s): ticks 1–11 within 0.082 s; then one tick about every 0.333 s from tick 11 (17:06:15.690) to tick 198 (17:07:18.021); then ticks 198–310 (113 ticks) within the final 0.983 s before the stop command | 0.335 s | 0.335 s |
| `171234` | Content Browser → Import file picker, opened by the owner, no file selected, cancelled. File → Choose Files to Save had opened no window on the clean project. | 2,324 ticks, 17:12:34.859–17:15:12.477 (157.6 s) | **52.589 s**, 17:13:14.094 to 17:14:06.683 | 0.338 s |
| `172253` | OK-only message box opened by a Python console command. A deviation; see 6.6. | 1,364 ticks, 17:22:53.376–17:24:44.711 (111.3 s) | **48.365 s**, 17:23:49.569 to 17:24:37.934 | 0.335 s |

### 6.5 Observed conditions and competing explanations

Four kinds of evidence are kept separate here.

**Callback gaps** — measured from the tick logs, as in 6.4.

**Owner-observed dialogs** — `162950` and `170615`: none. `171234`: the Import
picker, open during a period the owner confirmed in chat. `172253`: the message
box, confirmed by the owner and timestamped by the script.

**Editor-log events** — observed. Each item names its source: the committed
`editor-log-excerpts.txt`, the tick logs, the structured events file, or the
unredacted raw log preserved outside the repository.

- `162950` (excerpt and tick log): `LogStreaming: FlushAsyncLoading` is logged at
  16:32:09.717, about 23 ms **before** the last callback that precedes the gap
  (16:32:09.740782; the editor log records whole milliseconds). It is not inside
  the gap. Four `LogAssetRegistry` cache lines are logged at 16:32:31.511–.517,
  inside the gap (16:32:09.740–16:32:37.521). Neither the excerpt nor the raw log
  contains a line between the two.
- `171234`: no editor-log line falls inside the gap (17:13:14.094–17:14:06.683).
  In the committed excerpt the nearest lines are at 17:13:05.865 before it and
  17:15:12.482 after it; the unredacted raw log, preserved outside the
  repository, also has no line of any category inside the gap. Garbage
  collection was logged at 17:13:05.735–.865, ending before the gap began.
- `172253` (excerpt): `before_show_message` logged at 17:23:49.574; swap chain
  created 17:23:49.599; `Window 'WO-004 test dialog' being destroyed`
  17:24:37.908; `Message dialog closed, result: Ok` 17:24:37.925;
  `after_show_message` logged at 17:24:37.926. No other lines between opening
  and closing. These are editor-log times at millisecond resolution; the
  structured events file records the same two events at 17:23:49.574271 and
  17:24:37.925532 (6.6).

**Inferred causes** — none verified. A log line near or inside a gap does not
establish what caused it:

- `162950`: a loading flush was logged about 23 ms before the gap, and
  registry-cache work inside it. Whether either relates to the gap is not
  established.
- `170615`: the cadence of about one tick every 0.333 s is consistent with the
  editor throttling ticks while unfocused. The owner did not report focus state,
  so this is an inference.
- `171234`: the gap overlapped the owner-reported picker period (6.8). The
  mechanism is unverified; a blocking operating-system dialog loop on the editor
  thread is one plausible explanation.
- `172253`: the gap matched the Python call's duration. Two competing
  explanations remain; see 6.6.

Callback silence was therefore recorded under three distinct observed
conditions. Its cause in each remains unestablished.

### 6.6 The Python-opened message box: deviation and confound

**Deviation.** The reviewed Probe A procedure is an owner-opened dialog. This run
instead opened a dialog from a Python console command. It is recorded as a
separate, additional observation and is not the originally reviewed probe.

It was preceded by a read-only check that opened nothing and confirmed that
`unreal.EditorDialog.show_message` exists, with the signature
`show_message(title, message, message_type, default_value=AppReturnType.NO, message_category=AppMsgCategory.WARNING) -> AppReturnType`.
Epic's docstring states that the call blocks execution until the user makes a
decision, unless the editor runs in `-unattended` mode.

**Observation.** Zero callbacks between the structured event timestamps
`before_show_message` (17:23:49.574271) and `after_show_message`
(17:24:37.925532) in `wo004_dialog_events_172349.jsonl`, a span of 48.351 s. The
last tick was 5.0 ms before the first event and the first tick 8.5 ms after the
second. The corresponding editor-log lines are at 17:23:49.574 and 17:24:37.926
(6.5).

**Confound.** The dialog was opened from inside a Python command that kept
executing until the owner clicked OK. This run cannot separate two explanations:

- **(a)** the modal message-box loop does not deliver Slate post-tick callbacks;
- **(b)** post-tick delivery continues, but Python callbacks are not dispatched
  while another Python command is still executing.

Neither is verified. If (b) holds, the run says nothing about dialogs a person
opens.

### 6.7 The log-prefix counter field

**Source.** The second bracketed integer in each timestamped line of
`UnrealEditorFortnite.log`, as in `[2026.09.12-21.23.49:572][176]`. Its
semantics are not documented in this repository, and engine source is not
available here.

**Empirical behaviour** across the 7,844 timestamped lines of this log: values
range from 0 to 989. Consecutive lines decrease 26 times; 6 of those are
high-to-low (`>=900` to `<=100`) and 20 are not, for example `282` to `280` and
`286` to `186`. The field is therefore not monotonic from line to line, and a
difference between two values cannot be read as a count of frames or of any
other event.

**Observations only.** In `162950`, the value is `989` on the five lines from
16:32:09.717 to 16:32:31.517 — the only place in the log where consecutive lines
more than 5 s apart share a value. In `172253`, the value is `176` on the lines at
the dialog's opening and `40` at its closing, with no lines between.

**Withdrawn.** Statements made during the session that the editor "kept rendering
frames" (at least 864) while the message box was open, or was "frozen" during
`162950`, are not supported and are not part of this record.

### 6.8 What the owner-opened Import-picker run establishes

**Established**, for this window, in this configuration, in one trial:

- A 52.589 s callback gap (17:13:14.094–17:14:06.683, from the tick log) covered
  the agent's live check that followed the owner's report that the picker was
  open. That check read the live tick log at 17:13:43–17:13:46 and found no new
  ticks, the newest record being 32 s old. Ticks had resumed by the check made
  after the owner reported the picker closed. The live-check times come from the
  working-session record and are not preserved in the evidence directory. The
  gap is bracketed by these checks: it is not the dialog's duration, and whether
  its start and end coincide with opening and cancelling is unknown.
- No Python command was executing during it, so explanation (b) in 6.6 does not
  apply to this run.
- No editor-log line of any kind falls inside the gap: none in the committed
  excerpt, and none in the unredacted raw log preserved outside the repository.

**Unknown:**

- the exact open and cancel instants, which were not independently timestamped —
  the gap is bracketed, not matched;
- why the callbacks stopped;
- whether the editor continued other work meanwhile — the log contains no line
  inside the gap, and the counter field in 6.7 cannot answer it;
- whether an in-editor Slate dialog, including the Save Content prompt from the
  2026-08-24 incident, behaves the same;
- whether the result repeats;
- whether anything outside the Python tick path could observe or classify it.

**Further testing** should answer a specific remaining design question, not add
dialog examples:

1. **Does WO-004 need dialog-specific classification at all?** The mandate
   already makes `unknown`/`pending` the default without positive evidence. If
   callback silence is only ever reported as `unknown`, no dialog test is
   required. This is a design decision, not a test.
2. **If a silence reader is pursued, can it run outside the Python tick path?**
   Section 2.3 found no bridge command is served from the HTTP thread. This is a
   Session B design question.
3. **If dialog attribution is pursued:** during an owner-opened in-editor Slate
   modal with no Python command executing, are Python post-tick callbacks
   delivered? That would separate (a) from (b) in 6.6. It needs unsaved content
   to produce the Save Content prompt, and so a specific owner-approved temporary
   change.

### 6.9 Bounded conclusion

- Callback silence was observed in multiple conditions: overlapping an
  owner-reported native file picker, during a Python-opened message box, and with
  no dialog open.
- Where boundaries were recorded, the silence was sharply bounded: within 5.0 ms
  and 8.5 ms of the message-box call in `172253`.
- Because silence also occurred with no dialog open, callback silence alone cannot
  identify a dialog as its cause.
- **The cause of the silence remains unproven in every run.**
- **Dialog-specific classification or diagnosis remains unproven.**
- **An operational external reader remains unproven.** `_tick_health` is still
  write-only, and nothing reads it.
- There was one trial per condition. No heartbeat reliability is claimed.

The planning conclusion in Section 5 is preserved as historical. Probe A's
question is now answered only for the windows and conditions above, not in
general. Probes B and C were not run.

### 6.10 Limitations

- One trial per condition, one machine, editor build `Release-42.10` (project
  `compatibilityVersion` 42.00), Toolsets beta enabled.
- The control, `170615`, ticked about every 0.333 s for most of its span, with
  fast bursts in its first 0.082 s and final 0.983 s (6.4). Its cadence differs
  from the other runs, so it is not a matched control.
- `162950` was meant to be the dialog run, but no dialog was opened.
- File → Choose Files to Save opened no window, so the Save Content prompt
  remains untested.
- Live checks in `171234` depended on chat round-trip timing; they bracket events
  rather than timestamp them.
- The recorder writes to disk on every tick. The perturbation is irrelevant at a
  scale of tens of seconds.
- Nothing here concerns Epic's official MCP surface.

### 6.11 Cleanup evidence

- Every run's stop script printed `callback unregistered and confirmed.`, and each
  tick log's record count equals the count the stop script reported: 3,214, 310,
  2,324 and 1,364.
- No tick log changed size or modification time after its stop command. This was
  checked over 3 s immediately after `171234` and `172253`, and at later reads for
  all four.
- No bridge ran: at every check before and after the runs, ports 8765–8770 were
  not listening and no handoff file existed.
- In `TOOL_TEST`, nothing was saved or imported and no content was modified.
- The raw originals remain in the editor's `Saved` directory, unmodified.

### 6.12 Evidence and redaction

`docs/audits/evidence/wo004-probe-a/` contains:

- the four tick logs and one dialog-events file — byte-exact copies of the files
  UEFN wrote;
- the four executed scripts, as `.py.txt` — byte-exact;
- `editor-log-excerpts.txt` — redacted editor-log excerpts for the five run and
  check windows;
- `SHA256SUMS.txt` — the SHA-256 of every file listed here;
- `.gitattributes` — `* binary`, so git stores and checks out exact bytes and the
  hashes hold regardless of `core.autocrlf`. This differs from
  `2026-08-27-wo002-session-b-official-mcp.json`, which is stored
  text-normalized.

**Redaction** applies to `editor-log-excerpts.txt` only. The tick logs, events
file and scripts contain no paths or identifiers and are unredacted.

- 20 lines: the Windows user-profile path segment containing the account name was
  replaced with `<user>`, and the agent's temporary working directory with
  `<agent-scratchpad>`.
- Whole categories were excluded: `LogEOSSDK` (48 lines, account and auth
  activity), `LogOnlineAccount` (4 lines, auth-token cache) and
  `LogShaderCompilers` (40 lines, not relevant).
- Nothing else was altered. Line order and timestamps are unchanged.
- The unredacted originals are preserved outside the repository, in the editor's
  `Saved/wo004-probe-a-raw/` directory, with their own verified SHA-256 manifest.

### 6.13 Gate status

`WORKORDER.md` is unchanged and still authorizes Session A for read-only
feasibility planning only. This record authorizes no further live test, no
Session B or C, and no implementation, and it does not complete WO-004.
