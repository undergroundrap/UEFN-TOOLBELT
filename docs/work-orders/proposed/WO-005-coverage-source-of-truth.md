# WO-005 — Registry-Derived Coverage Source of Truth

STATUS: PROPOSED

AUTHORIZATION: NOT AUTHORIZED

OWNER: Ocean Bennett

PRIORITY: P2

BASELINE: `6b8ffb2b2d672812f8699af2c22f92c19708f29b`

## Problem

`list_untested.py` discovers only direct tool-module registrations and treats
lexical references as coverage. It therefore reports a different universe and
meaning from the registry, TOOL_STATUS, and the integration harness.

## Proposed Session A — authoritative coverage model

- derive the complete universe from the actual registry or equivalent AST
  registration semantics;
- include registrations outside `tools/`;
- record each entry as outcome-verified, execution-only, registration-only, or
  uncovered;
- map each claim to a concrete test section or evidence identifier;
- reconcile TOOL_STATUS without conflating checks with unique tools;
- add mutation tests proving omissions and vacuous checks fail.

Exclusions: no new runtime tool behavior, no inflated verification claims, and
no version or publication changes.

NEXT GATE: independent pre-issuance review.
