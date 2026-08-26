# WO-001 — Custom MCP Control-Plane Security

STATUS: ISSUED

AUTHORIZATION: ISSUED — SESSION A AUTHORIZED FOR IMPLEMENTATION

OWNER: Ocean Bennett

PRIORITY: P0

BASELINE: `34c3762b32c36805e3ec2f7f93df68c2c17fd26c`

ISSUANCE BASIS: The proposal was independently accepted and committed as
`318c28fa08bfef032280bad9b76eab7cd81f626d`; CI workflow
[`32701409756`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32701409756)
passed.

SESSION A AUTHORIZATION BASIS: The issued Work Order was committed as
`34c3762b32c36805e3ec2f7f93df68c2c17fd26c`; CI workflow
[`32890583500`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32890583500)
passed before the owner authorized Session A.

Issuance alone grants no implementation authority. Only the repository-root
`WORKORDER.md` may authorize an individual session.

## Problem

The loopback custom MCP bridge accepts commands without client authentication
and exposes arbitrary in-editor Python. If main-thread callback registration is
unavailable, it can fail open to executing `unreal.*` work on the HTTP handler
thread.

## Session A — authenticated, fail-closed control plane

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

NEXT GATE: independent review of the complete uncommitted Session A worktree.
