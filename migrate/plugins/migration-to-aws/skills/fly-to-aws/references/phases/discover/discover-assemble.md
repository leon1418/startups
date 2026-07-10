---
_assemble: assemble-discover
_of_phase: discover
_reads:
  - fly.toml sub-discovery (discover-flytoml.md contribution)
  - code-signals sub-discovery (discover-code-signals.md contribution)
  - flyctl JSON export + billing ingestion (inline in discover.md)
_produces:
  - fly-resource-inventory.json
---

# Discover — Assemble Inventory

> **Assembler unit.** The Discover phase runs its sub-discoveries and assembles the
> single `fly-resource-inventory.json` artifact inline within `discover.md`
> (Step 3: Assemble Inventory). This unit records the artifact-level contract for the
> phase: it is the single creator of `fly-resource-inventory.json`, and its
> postconditions (declared on the phase) are the phase's completion gate. See
> `discover.md` § Step 3 and § Completion Handoff Gate for the assembly rules and the
> fail-closed checks this contract enforces.
