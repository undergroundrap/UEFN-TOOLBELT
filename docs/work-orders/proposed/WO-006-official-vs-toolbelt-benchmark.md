# WO-006 — Official MCP Versus Toolbelt Benchmark

STATUS: PROPOSED

AUTHORIZATION: NOT AUTHORIZED

OWNER: Ocean Bennett

PRIORITY: P2

BASELINE: `6b8ffb2b2d672812f8699af2c22f92c19708f29b`

## Problem

The official MCP and Toolbelt have not been compared under a controlled,
apples-to-apples workload. Timings observed during the convergence audit include
launch, modal, compile, and warm-state effects and are not a benchmark.

## Proposed Session A — benchmark design and harness

- select equivalent read-only calls and reversible mutation pairs;
- compare official MCP with Toolbelt's safe queued main-thread mode only;
- define cold and warm runs, repetitions, fixture reset, and cleanup;
- capture p50, p95, maximum latency, error rate, editor-frame stalls, modal
  events, and cleanup cost;
- keep session launch and Verse push as separately reported macro operations;
- emit machine-readable raw results and a reproducible human summary.

Decision lock: never benchmark or legitimize the unsafe direct HTTP-thread
fallback. Run only in disposable TOOL_TEST and remove every fixture.

Exclusions: no performance optimization in the measurement session and no
marketing conclusion before independent review.

NEXT GATE: independent pre-issuance review after relevant security and modal
work reaches a stable boundary.
