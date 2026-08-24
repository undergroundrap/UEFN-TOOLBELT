# WO-002 — Epic Toolset Integration Truth

STATUS: PROPOSED

AUTHORIZATION: NOT AUTHORIZED

OWNER: Ocean Bennett

PRIORITY: P1

BASELINE: `6b8ffb2b2d672812f8699af2c22f92c19708f29b`

## Problem

Toolbelt reports an in-process Epic toolset registration, but the external
official server does not list, describe, or call it. The internal describe
meta-tool also expects the wrong manifest shape.

## Proposed Session A — internal contract correction

- correct `toolbelt_describe_tool` to consume the registry's actual flat
  manifest;
- distinguish attempted registration, in-process registration, and externally
  confirmed discoverability;
- add non-vacuous tests for all three Toolbelt meta-tools.

## Proposed Session B — external discovery proof

- inspect the current Epic ToolsetPolicy and registry exposure path;
- prove external `list_toolsets`, `describe_toolset`, and `call_tool` behavior in
  disposable TOOL_TEST;
- advertise integration only if all external calls succeed;
- preserve manual Toolbelt recovery when the official beta flag suppresses
  project startup.

Exclusions: no security redesign from WO-001, no broad documentation convergence,
and no tag, Release, repository-description, or social action.

NEXT GATE: independent pre-issuance review after WO-001 reaches its recorded
decision boundary.
