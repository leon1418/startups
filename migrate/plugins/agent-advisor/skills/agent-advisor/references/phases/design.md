# Phase: Design

Assembles the recommendation from the scoring result + Pass 2 choices + service cards.

## Step 1 — Read inputs
Read `$RUN_DIR/scoring-result.json` and `$RUN_DIR/pass2.json`.

## Step 2 — Load the winning runtime's service card
Load `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/<verdict>.md` (use `lambda-microvms.md`
for lambda_microvms). For co_recommend, load both. Load
`${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/model-defaults.md` and
`managed-alternatives.md`.

## Step 3 — Refresh volatile facts
Load `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/freshness.md` and follow its procedure:
read the winning profile's `volatile_facts`, try awsknowledge MCP for each, fall back to cached
values on failure. Record which succeeded vs fell back (for the freshness footer).

## Step 4 — Provider lock-in check
If the user is committed to a single provider (from model answers), surface the matching
managed alternative from `managed-alternatives.md` with its tradeoffs. Otherwise note AgentCore
supports all models.

## Step 5 — Assemble design.json
```json
{
  "verdict": "...", "deployment_model": "...", "agentcore_services": [...],
  "model_recommendation": {...}, "warnings": [...],
  "volatile_facts": {"session_cap": {"value": "8h", "source": "mcp|cached"}},
  "managed_alternative": "claude_managed | bedrock_managed | none",
  "handoff_required": true|false
}
```
Set `handoff_required` = true when verdict is ecs/eks/lambda OR entry_point == migrate.

## Step 6 — Branch on entry point
- entry_point == migrate → set `phases.design` = completed, set `phases.estimate` = "skipped",
  and continue to **Generate**. The user gets the same recommendation doc + architecture diagram
  as Build paths; Generate then performs the handoff at the end. Do NOT run Estimate (precise
  cost belongs downstream).
- otherwise → set `phases.design` = completed and continue to Estimate.
