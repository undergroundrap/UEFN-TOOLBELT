# WO-003 — Official UEFN MCP Documentation Convergence

STATUS: PROPOSED

AUTHORIZATION: NOT AUTHORIZED

OWNER: Ocean Bennett

PRIORITY: P1

BASELINE: `6b8ffb2b2d672812f8699af2c22f92c19708f29b`

## Problem

Agent and public documentation still describes Verse compilation, Creative
device configuration, Scene Graph authoring, UMG, and play-session control as
Epic-locked even though official UEFN MCP exposes those capabilities. Menu,
restart, network, security, tool-count, unavailable-entry, coverage, roadmap,
and repository-description claims also disagree.

## Proposed Session A — repository truth

- reconcile README, CLAUDE, llms, PIPELINE, AI_AUTONOMY, capability, status,
  roadmap, and quirks surfaces with the accepted audit;
- distinguish legacy `unreal` Python limitations from official MCP capability;
- preserve the official-beta auto-start suppression and manual recovery rule;
- document the proven Toolbelt preflight → official session → restore sequence;
- correct menu, restart, count, security, coverage, and roadmap claims;
- extend drift and integrity coverage so the corrected claims cannot regress.

## Proposed Session B — remote metadata draft

- prepare the exact GitHub repository-description correction for owner review;
- do not apply it without a separate remote-metadata authorization.

Exclusions: no runtime changes, tag, GitHub Release, or social publication.

NEXT GATE: independent pre-issuance review after WO-002 establishes the final
integration vocabulary.
