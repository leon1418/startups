---
_assemble: assemble-clarify-pass2
_of_phase: clarify-pass2
_reads:
  - winner-specific follow-up answers (collected inline in clarify-pass2.md)
_produces:
  - pass2.json
---

# Clarify Pass 2 — Assemble pass2.json

> **Assembler unit.** Clarify Pass 2 reads the scoring result, asks only what the
> winning runtime needs (deployment model, AgentCore services, co_recommend
> pick, native-vs-gateway tool choices), and writes `pass2.json` inline within
> `clarify-pass2.md` (Step 5). This unit records the artifact-level contract for
> the phase: it is the single creator of `pass2.json`, and its postconditions
> (declared on the phase) are the phase's completion gate. See `clarify-pass2.md`
> § Step 5 for the pass2.json shape (`deployment_model`, `agentcore_services`,
> `chosen_runtime` when co_recommend, `tool_choices`).
