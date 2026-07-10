---
_assemble: assemble-clarify
_of_phase: clarify
_reads:
  - interpreted interview answers (collected inline in clarify.md)
_produces:
  - preferences.json
---

# Clarify — Assemble preferences.json

> **Assembler unit.** The Clarify phase presents its adaptive question batches and
> interprets the answers inline within `clarify.md`, then assembles the final
> `preferences.json` (Step 4). This unit records the artifact-level contract for the
> phase: it is the single creator of `preferences.json`, and its postconditions
> (declared on the phase) are the phase's completion gate. See `clarify.md`
> § Step 4 and § Completion Handoff Gate for the schema rules, the Validation
> Checklist, and the fail-closed checks this contract enforces.
