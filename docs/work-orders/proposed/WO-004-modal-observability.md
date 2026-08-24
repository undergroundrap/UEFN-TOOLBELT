# WO-004 — Modal Observability and Human-Safe Blocking

STATUS: PROPOSED

AUTHORIZATION: NOT AUTHORIZED

OWNER: Ocean Bennett

PRIORITY: P1

BASELINE: `6b8ffb2b2d672812f8699af2c22f92c19708f29b`

## Problem

An official MCP call remained pending for minutes behind a Save Content dialog
and resumed immediately after the owner acted. The agent could not distinguish a
modal block from ordinary asynchronous work.

## Proposed Session A — read-only blocker sensing

- add a safe modal/window-status primitive using supported Slate state;
- classify command timeouts as queued, modal-blocked, disconnected, or failed;
- identify a visible dialog without clicking or accepting it;
- surface actionable owner instructions and preserve the pending operation;
- add simulated modal-state regression tests and live TOOL_TEST evidence.

Decision lock: Toolbelt must never auto-confirm destructive, save, validation,
overwrite, missing-class, or otherwise ambiguous dialogs.

Exclusions: no general computer control, no blind keystrokes, no WO-001 bridge
security expansion, and no release or social work.

NEXT GATE: independent pre-issuance review.
