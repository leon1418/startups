# Handoff — Migrate path

Loaded at the end of the **Generate** phase for `migrate` (after the user has already received
the full recommendation doc + architecture diagram). The advisor's recommendation is done;
**execution** belongs to the migration plugins. This step adds the machine-readable handoff
artifact and points the user downstream — it does not replace the recommendation doc.

## Step 1 — Write the handoff summary
Write `$RUN_DIR/handoff-summary.md` (a compact, machine-readable companion to
`recommendation.md` for the downstream plugins) containing: recommended runtime + deployment
model + services, coarse model family mapping (the source model from the user's `current_model`
answer → the Bedrock family per `model-defaults.md`; no prices), and the rationale (top scoring
signals + eliminations, from design.json's `scores`/`eliminated`).

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

## Step 4 — Finish
Return to Generate Step 7, which sets `phases.generate` = completed. Tell the user the advisor
phase is done: they have the recommendation doc + architecture diagram (`recommendation.md`),
and the handoff summary (`handoff-summary.md`) is saved for the downstream plugins. Offer to
kick off the recommended downstream plugin.
