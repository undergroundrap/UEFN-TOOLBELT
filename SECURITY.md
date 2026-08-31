# Security Boundary

UEFN Toolbelt is editor automation with the same privileges as the embedded
Python process. Treat Toolbelt, custom plugins, MCP clients, and generated Python
as executable code—not as isolated island content.

## Experimental custom MCP boundary

Work Order WO-001 Session A adds an authenticated, fail-closed control plane,
but the custom HTTP bridge remains experimental and trusted-same-user-only. Do
not expose it beyond the local machine or connect an untrusted local process.
Loopback plus a bearer token is not a sandbox.

The accepted 2026-08-24 read-only audit established the pre-hardening risks.
Session A addresses them as follows:

- every listener start generates a cryptographically strong bearer secret and
  writes it to the same-user local `Saved/UEFN_Toolbelt/mcp_session.json`
  handoff; restart rotates it and stop removes it;
- secrets are compared in constant time and recursively redacted before status,
  command results, errors, logs, history, or client output is stored or emitted;
- method, path, `Host`, `Origin`, content type, authentication, and body size are
  checked before JSON parsing or dispatch; browser origins and preflight are
  rejected and no CORS permission is emitted;
- arbitrary remote Python is unavailable. The bridge exposes only registered,
  bounded commands; deliberate scripting remains local to UEFN's Python console;
- the listener becomes reachable only after Slate callback registration and
  session handoff succeed. Callback failure leaves no listener, token, or
  direct-thread fallback;
- all accepted commands enter the queue and execute from the Slate callback on
  the editor main thread.

The handoff file is deliberately readable by the same Windows user so
`mcp_server.py` and `client.py` can authenticate automatically. Another process
running as that user may be able to read it, inject into the editor process, or
otherwise act with the user's privileges. The bridge does not defend against a
compromised same-user account or privileged local malware.

- binding to `127.0.0.1` limits network reach but does not authenticate a client;
the rotating bearer session supplies client authentication within the narrower
same-user trust model described above.

The audit did not start the custom listener and did not perform malicious or
destructive exploit testing. These conclusions came from source inspection and
non-destructive live integration evidence. See the
[UEFN 42.00 official-MCP audit](docs/audits/2026-08-24-uefn-42-official-mcp-audit.md).

## Current trust model

- **Repository code:** open for review, but still privileged editor code.
- **Official Epic MCP:** a separate Epic control plane bound to loopback. Epic's
  42.00 ecosystem release notes state it is available and ships in 42.00; those
  notes do not state that it left beta or experimental status, and locally
  accepted evidence still places `UEFN MCP Toolsets` under Beta Access
  (`docs/UEFN_QUIRKS.md`, Quirk #36). Available is not flawless: the accepted
  audit recorded live gaps on that surface. Follow Epic's current documentation
  and UEFN beta warnings.
- **Toolbelt custom bridge:** authenticated same-user local clients only, with
  the experimental restrictions above.
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
