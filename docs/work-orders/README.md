# Work Orders

Work Orders are durable scope and evidence records. They let a fresh agent
reconstruct what may happen next without treating chat history, a roadmap item,
or a useful audit finding as implementation permission.

## Canonical authority

Only the repository-root `WORKORDER.md` may identify the current issued Work
Order and authorized session. A file anywhere under `docs/work-orders/` is not a
go signal by itself.

Normally, at most one detailed Work Order is issued at a time. The root pointer
must identify it before any session can be authorized. If the root pointer says
`NONE`, no Work Order implementation is authorized.

## States

| State | Directory | Meaning |
|---|---|---|
| `PROPOSED` | `proposed/` | Planning only. Scope may be reviewed, but no implementation is authorized. |
| `ISSUED` | `issued/` | The owner accepted the mandate. Individual sessions still require an explicit go signal in `WORKORDER.md`. |
| `COMPLETED` | `completed/` | All required sessions, review, scoped commits, authorized pushes, CI, and final status evidence are complete. |
| `SUPERSEDED` | `superseded/` | Replaced or abandoned. The file records why and what superseded it. |

Moving or copying a file does not change authority on its own. State transitions
must be owner-authorized, independently reviewable repository changes, and must
agree with the root pointer.

## Required Work Order contents

Every proposed or issued Work Order records:

- identifier, status, authorization, owner, priority, and baseline;
- problem statement and accepted evidence;
- ordered sessions using spreadsheet labels `A` through `Z`, then `AA` through
  `AZ`, `BA` through `BZ`, and onward;
- exact inclusions, exclusions, deferred work, and decision locks;
- fixtures, affected configurations, safety constraints, and cleanup duties;
- acceptance criteria that would fail under plausible regressions;
- static, live, and CI evidence requirements;
- implementation, review, commit, push, tag, GitHub Release, repository-metadata,
  and social-publication stop boundaries;
- the next gate and the role allowed to receive it.

## Gate sequence

```text
proposed
-> independent pre-issuance review
-> owner issued
-> owner authorizes one session
-> implementation left uncommitted
-> fresh independent architect review
-> owner authorizes exact commit
-> owner separately authorizes push
-> CI reaches terminal conclusions
-> status evidence recorded
-> next session remains unauthorized
```

Tags, GitHub Releases, repository-description changes, and social publication
are never implied by a completed implementation or green CI.

## Directory notes

- [`proposed/`](proposed/) contains prioritized plans with no implementation
  authority.
- [`issued/`](issued/) contains the current detailed mandate when one exists.
- [`completed/`](completed/) preserves accepted historical scope and evidence.
- [`superseded/`](superseded/) preserves abandoned or replaced mandates and the
  reason for the transition.
