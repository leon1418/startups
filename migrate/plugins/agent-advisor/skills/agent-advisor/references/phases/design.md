# Phase: Design

Assembles the recommendation from the scoring result + Pass 2 choices + service cards.

## Step 1 — Read inputs
Read `$RUN_DIR/scoring-result.json` and `$RUN_DIR/pass2.json`. The winning runtime is
`pass2.chosen_runtime` if present (co_recommend pick), else `scoring-result.verdict`. Prefer
`pass2.deployment_model` and `pass2.agentcore_services` over the scoring-result defaults (Pass 2
is the user-confirmed set).

## Step 2 — Load the winning runtime's service card
Load `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/<verdict>.md` (use `lambda-microvms.md`
for lambda_microvms). For co_recommend, load both. Load
`${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/model-selection.md` and
`managed-alternatives.md`.

## Step 3 — Refresh volatile facts
Load `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/freshness.md` and follow its procedure:
read the winning profile's `volatile_facts`, try awsknowledge MCP for each, fall back to cached
values on failure. Record which succeeded vs fell back (for the freshness footer).

## Step 4 — Provider lock-in check
Determine the managed alternative from the source/current model provider: Claude-committed →
`claude_managed`; OpenAI-committed → `bedrock_managed`; multi-provider or undecided → `none`.
If a managed alternative applies, surface it **as awareness only** (per `managed-alternatives.md`)
with its tradeoffs — do NOT present it as the recommendation. Otherwise note AgentCore supports
all models.

## Step 5 — Assemble design.json
Carry the scoring facts forward so Generate has a deterministic source for "Alternatives
considered" and the "Eliminated" line (Generate reads design.json, not scoring-result.json):
```json
{
  "verdict": "...", "chosen_runtime": "...", "deployment_model": "...",
  "agentcore_services": [...], "model_recommendation": {...}, "warnings": [...],
  "scores": {...}, "eliminated": {...}, "blocking_constraints": [...],
  "volatile_facts": {"session_cap": {"value": "8h", "source": "mcp|cached"}},
  "managed_alternative": "claude_managed | bedrock_managed | none",
  "handoff_required": true|false
}
```
Copy `scores`, `eliminated`, and (if present) `blocking_constraints` verbatim from
scoring-result.json. Set `handoff_required` = true when the winning runtime is **ecs or eks**
(heavy-infra compute handed off downstream). Standard Lambda, Lambda MicroVMs, and AgentCore are
self-contained — `handoff_required` = false for them. (Migrate still hands off execution
regardless — that's an entry-point behavior in Step 6, independent of `handoff_required`.)

## Step 6 — Branch on entry point
- entry_point == migrate → set `phases.design` = completed, set `phases.estimate` = "skipped",
  and continue to **Generate**. The user gets the same recommendation doc + architecture diagram
  as Build paths; Generate then performs the handoff at the end. Do NOT run Estimate (precise
  cost belongs downstream).
- otherwise → set `phases.design` = completed and continue to Estimate.
