---
_assemble: assemble-share
_of_phase: share
_reads:
  - share link generation result (share.md Step 1)
_produces:
  - share.json
---

# Share — Assemble share.json

> **Assembler unit.** The Share phase generates the shareable migration-plan link
> and writes `share.json` inline within `share.md` (Step 2). This unit records the
> artifact-level contract for the phase: it is the single creator of `share.json`,
> and the phase's postconditions are its completion gate. See `share.md` § Step 2
> and § Step 3 (Output gate) for the schema and the fail-closed check this contract
> enforces.
