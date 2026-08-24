# WO-001 — Custom MCP Control-Plane Security

STATUS: PROPOSED

AUTHORIZATION: NOT AUTHORIZED

OWNER: Ocean Bennett

PRIORITY: P0

BASELINE: `6b8ffb2b2d672812f8699af2c22f92c19708f29b`

## Problem

The loopback custom MCP bridge accepts commands without client authentication
and exposes arbitrary in-editor Python. If main-thread callback registration is
unavailable, it can fail open to executing `unreal.*` work on the HTTP handler
thread.

## Proposed Session A — authenticated, fail-closed control plane

Scope:

- require a per-session secret and constant-time authentication;
- validate method, path, `Host`, `Origin`, and `Content-Type` before parsing;
- prevent browser-originated write-only command execution;
- disable arbitrary `execute_python` by default or remove it from the public
  bridge surface;
- guarantee that every `unreal.*` operation uses queued main-thread dispatch;
- fail closed if Slate/main-thread callback registration is unavailable;
- expose an honest status distinguishing authenticated queued mode from
  unavailable mode;
- add adversarial unit coverage and proportional live TOOL_TEST verification.

Exclusions:

- no official Epic MCP behavior changes;
- no unrelated tool, dashboard, count, version, release, or social changes;
- no destructive exploit testing.

Acceptance requires negative tests for missing and incorrect authentication,
host/origin confusion, malformed requests, arbitrary-execution defaults, and
dispatcher-registration failure. Work remains uncommitted for independent
review. Commit and push require later, separate owner gates.

NEXT GATE: independent pre-issuance review, then explicit owner issuance.
