# Security Boundary

UEFN Toolbelt is editor automation with the same privileges as the embedded
Python process. Treat Toolbelt, custom plugins, MCP clients, and generated Python
as executable code—not as isolated island content.

## Interim custom MCP warning

The custom HTTP bridge remains experimental pending implementation of issued
Work Order WO-001. Do not expose it beyond the local machine, do not connect an
untrusted local client, and do not describe the current bridge as authenticated
or safe for untrusted browser content.

The accepted 2026-08-24 read-only audit established:

- binding to `127.0.0.1` limits network reach but does not authenticate a client;
- the request handler does not enforce a client secret, trusted `Host`, trusted
  `Origin`, or strict content type before command dispatch;
- `execute_python` permits arbitrary in-editor Python with `unreal.*` access;
- CORS response headers are not authorization and do not prevent write-only
  side effects;
- if Slate callback registration is unavailable, the bridge can fall back to
  dispatching Unreal work on the HTTP handler thread;
- all `unreal.*` calls are required to execute on the editor main thread, so
  inability to install queued dispatch must fail closed.

The audit did not start the custom listener and did not perform malicious or
destructive exploit testing. These conclusions came from source inspection and
non-destructive live integration evidence. See the
[UEFN 42.00 official-MCP audit](docs/audits/2026-08-24-uefn-42-official-mcp-audit.md).

## Current trust model

- **Repository code:** open for review, but still privileged editor code.
- **Official Epic MCP:** a separate experimental Epic control plane bound to
  loopback; follow Epic's current documentation and UEFN beta warnings.
- **Toolbelt custom bridge:** trusted-local-client use only, with the interim
  restrictions above.
- **Custom plugins:** review source and provenance before loading. Static import
  checks reduce obvious risk but do not turn Python into a security sandbox.
- **Remote downloads and integrations:** some optional Toolbelt features fetch
  URLs or GitHub metadata. Toolbelt must not be described as universally
  offline.

## Safe operating rules

1. Use a disposable UEFN project for unknown automation.
2. Keep backups or source control before any broad mutation.
3. Read generated or downloaded Python before executing it.
4. Never expose a local editor-control port through a public bind, tunnel, or
   port-forward without a separately reviewed security design.
5. Stop if a command requests secrets, shell execution, or filesystem access
   outside its declared scope.
6. Treat modal dialogs as human decision boundaries; do not blindly accept them.
7. Report vulnerabilities privately before publishing exploit details.

Security hardening, implementation, commit, push, disclosure, Release, and
social publication remain separate owner-authorized gates.
