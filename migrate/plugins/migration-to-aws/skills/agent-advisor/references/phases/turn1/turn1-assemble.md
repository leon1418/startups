---
_assemble: assemble-turn1
_of_phase: turn1
_reads:
  - entry-point + background answers (collected inline in turn1.md Steps 2–4)
_produces:
  - .phase-status.json
---

# Turn 1 — Assemble run state

> **Assembler unit.** Turn 1 asks the two entry questions and captures open
> context inline within `turn1.md`, then writes the run's `.phase-status.json`
> (Step 5). This unit records the artifact-level contract for the phase: it is
> the single creator of `.phase-status.json`, and its postconditions (declared
> on the phase) are the phase's completion gate. See `turn1.md` § Step 5 for the
> state schema (`entry_point`, `audience`, `turn1 = completed`, later phases
> pending/skipped per entry point).
