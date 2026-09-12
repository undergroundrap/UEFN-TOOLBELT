# WO-004 Session A — Modal Observability Feasibility

STATUS: SESSION A FEASIBILITY RECORD

AUTHORIZATION: READ-ONLY PLANNING — NO LIVE UEFN WORK PERFORMED

SESSION_A_AUTHORIZATION_COMMIT: `f9fc7268d63dad92f5dd009bbf20e11477b8f926`

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
