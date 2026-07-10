---
_assemble: assemble-estimate
_of_phase: estimate
_reads:
  - current fly.io costs, projected AWS costs, comparison, ROI, optimizations, recommendation (estimate.md Parts 1-7)
_produces:
  - estimation-infra.json
---

# Estimate — Assemble estimation-infra.json

> **Assembler unit.** The Estimate phase computes the full financial picture inline
> within `estimate.md`, then assembles the final `estimation-infra.json`
> (§ Output: Write estimation-infra.json). This unit records the artifact-level
> contract for the phase: it is the single creator of `estimation-infra.json`, and
> its postconditions (declared on the phase) are the phase's completion gate. See
> `estimate.md` § Output and § Completion Handoff Gate for the schema and the
> fail-closed checks this contract enforces, including the Property-16 invariant.
