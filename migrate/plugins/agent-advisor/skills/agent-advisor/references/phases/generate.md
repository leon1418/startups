# Phase: Generate — Recommendation Doc + Scaffolding

## Step 1 — Read inputs
Read `$RUN_DIR/design.json`. Read `$RUN_DIR/estimate.json` **if it exists** (Build paths only —
for `migrate`, Estimate is skipped and there is no estimate.json; that's expected). Load the
winning runtime's service card and
`${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/model-defaults.md`.

## Step 2 — Build the architecture diagram
Load `references/diagram/build-diagram.md` and follow it to produce `$RUN_DIR/diagram.md`
(Mermaid + ASCII), then embed it into Section 4 of the recommendation doc.

## Step 3 — Fill the recommendation document
Load `references/output-templates/recommendation-doc.md`. Fill ALL 12 sections. Business
summary first, technical detail after (single layered doc — do not fork by audience). Write to
`$RUN_DIR/recommendation.md`. Append the freshness footer.

For `migrate`: also fill Section 9 (Bedrock model) with the **coarse family mapping**
(e.g. "GPT-4o → Claude Sonnet 4.6 family") and a note that detailed pricing/TCO come from the
migration plugins — no dollar figures. Section 10 (cost magnitude) states "Detailed cost and TCO
are produced by the migration plugins" instead of a band (Estimate was skipped).

## Step 4 — Lightweight scaffolding (Build paths only)
**Skip this step entirely for `migrate`** (execution artifacts belong to the downstream plugins).
For Build paths:
- AgentCore + Harness → write a minimal `harness.json` skeleton with the model id from
  model_recommendation and the selected services.
- AgentCore + Framework / other runtimes → write a minimal framework starter note (entrypoint
  contract: `/invocations` POST + `/ping` GET for AgentCore) + the model id.
Write scaffolding under `$RUN_DIR/scaffold/`. Keep it minimal — heavy IaC hands off.

## Step 5 — In-chat mini-brief
Print: Recommendation, Why (top 3 signals), Eliminated, Model, and a pointer to
`$RUN_DIR/recommendation.md`. Surface any `warnings` from the scoring result (e.g. 5 TPS).

## Step 6 — Migrate handoff (migrate only)
If entry_point == migrate, NOW load `references/handoff/handoff-migration.md` and follow it:
it writes the machine-readable `handoff-summary.md` for the downstream plugins and points the
user to `/ai-to-aws:llm-to-bedrock` / `migration-to-aws:gcp-to-aws`. The user has already seen
the full recommendation doc + diagram from Steps 2–5; the handoff is offered **after** that, not
instead of it. For Build paths, skip this step.

## Step 7 — Write state
Set `phases.generate` = completed. The advisor flow is complete.
