# Handoff — Migrate path

The advisor's job ends at the decision. Execution belongs to the migration plugins.

## Step 1 — Write the handoff summary
Write `$RUN_DIR/handoff-summary.md` containing: recommended runtime + deployment model +
services, coarse model family mapping (from model_recommendation.migration_from, no prices),
and the rationale (top scoring signals + eliminations).

## Step 2 — Check downstream availability
Check whether `migration-to-aws` and/or `ai-to-aws` appear in the available-skills list (do
NOT invoke them as a test).

## Step 3 — Direct the user
- For AI/LLM workload migration (model swap, SDK rewrite): point to `/ai-to-aws:llm-to-bedrock`.
- For infrastructure/container migration (ECS/EKS/Lambda compute): point to
  `migration-to-aws:gcp-to-aws`.
- If a needed plugin is NOT installed: give the install command
  `/plugin install <name>@startups-for-aws` and tell the user to re-run that plugin with the
  handoff summary at `$RUN_DIR/handoff-summary.md`.

## Step 4 — Write state and stop
Set `phases.design` = completed. Do not advance to Estimate/Generate. Tell the user the advisor
phase is done and the handoff summary is saved.
