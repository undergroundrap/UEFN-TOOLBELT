# Current Work Order Gate

This file is the repository's sole authority pointer for current Work Order
state. Detailed mandates live under `docs/work-orders/`; their presence alone
never authorizes implementation.

- Current issued Work Order: WO-002
- Authorized session: NONE
- Base commit: `50b881716abea3b5838c2a971caac40ee4cd5d30`
- Current gate: WO-002 SESSION A ACCEPTED — SESSION B NOT AUTHORIZED
- Release train: WO-001 through WO-007
- Release gate: NO TAG OR GITHUB RELEASE AUTHORIZED — COMPLETE THE FROZEN TRAIN AND FINAL INTEGRATION/REPOSITORY-TRUTH AUDIT FIRST

[`WO-001-custom-mcp-security.md`](docs/work-orders/completed/WO-001-custom-mcp-security.md)
is completed as `ffcbe8b1bfa03cb37453b9beefda0bbdbe45543c` after
[CI workflow `32921154482`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32921154482)
passed.

[`WO-002`](docs/work-orders/issued/WO-002-epic-toolset-integration.md)
is issued. Session A was independently accepted, committed, and pushed as
`50b881716abea3b5838c2a971caac40ee4cd5d30`; [CI workflow
`32937631903`](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32937631903)
completed successfully, including required job
[`98081919978` — Lint, types, tests](https://github.com/undergroundrap/UEFN-TOOLBELT/actions/runs/32937631903/job/98081919978).
No session is currently authorized. Session B remains unauthorized and requires
separate BDFL/owner authorization.

WO-001 through WO-007 form the frozen next release train. The release version
remains undecided and the repository stays at version 2.4.1. No tag or GitHub
Release is authorized until the frozen train is complete, a final
integration/repository-truth audit passes, and the owner separately authorizes
a release session. New proposals default to the following release train unless
the owner explicitly classifies one as a blocker.
