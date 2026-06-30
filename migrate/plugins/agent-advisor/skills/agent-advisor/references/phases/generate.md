# Phase: Generate — Recommendation Doc + Scaffolding

## Step 1 — Read inputs
Read `$RUN_DIR/design.json` and `$RUN_DIR/estimate.json`. Load the winning runtime's service
card and `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/model-defaults.md`.

## Step 2 — Build the architecture diagram
Follow the diagram build step (Plan 3: `references/diagram/build-diagram.md`) to produce the
Mermaid block + ASCII fallback from `scoring-result.json` + `pass2.json`. If Plan 3 is not yet
installed, emit a simple text node list as a placeholder and note it.

## Step 3 — Fill the recommendation document
Load `references/output-templates/recommendation-doc.md`. Fill ALL 12 sections. Business
summary first, technical detail after (single layered doc — do not fork by audience). Write to
`$RUN_DIR/recommendation.md`. Append the freshness footer.

## Step 4 — Lightweight scaffolding (Build paths only)
- AgentCore + Harness → write a minimal `harness.json` skeleton with the model id from
  model_recommendation and the selected services.
- AgentCore + Framework / other runtimes → write a minimal framework starter note (entrypoint
  contract: `/invocations` POST + `/ping` GET for AgentCore) + the model id.
Write scaffolding under `$RUN_DIR/scaffold/`. Keep it minimal — heavy IaC hands off.

## Step 5 — In-chat mini-brief
Print: Recommendation, Why (top 3 signals), Eliminated, Model, and a pointer to
`$RUN_DIR/recommendation.md`. Surface any `warnings` from the scoring result (e.g. 5 TPS).

## Step 6 — Write state
Set `phases.generate` = completed. The advisor flow is complete.
