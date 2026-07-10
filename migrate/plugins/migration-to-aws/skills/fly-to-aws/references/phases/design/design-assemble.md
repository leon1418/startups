---
_assemble: assemble-design
_of_phase: design
_reads:
  - compute routing results (design.md Steps 1-2)
  - database / storage / extension / object-storage / network / secrets mappings (design.md Steps 3-7)
  - embedded agent-advisor verdict (design-agent-handoff.md contribution, when an agent group requested scoring)
_produces:
  - aws-design.json
---

# Design — Assemble aws-design.json

> **Assembler unit.** The Design phase executes the compute routing table and the
> data/network/secrets mappings inline within `design.md`, then assembles the final
> `aws-design.json` (Step 8). This unit records the artifact-level contract for the
> phase: it is the single creator of `aws-design.json`, and its postconditions
> (declared on the phase) are the phase's completion gate. See `design.md`
> § Step 8 and § Completion Handoff Gate for the schema, the validation rules, and
> the fail-closed checks this contract enforces.
