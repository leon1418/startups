---
_fragment: report
_of_phase: generate
_contributes:
  - { file: migration-report.html, _when: "the HTML report passed its validate gate and built successfully" }
---

# Generate Phase: HTML Migration Report

> Loaded by generate.md (Step 5.5) AFTER generate-docs.md completes.

**Execute ALL steps in order. Do not skip or optimize.**

## Overview

Generate a single self-contained HTML report (`migration-report.html`) combining an executive summary with a detailed appendix. The HTML file uses inline CSS — no external dependencies required. Users can open it in any browser and use "Print to PDF" if a PDF is needed.

**Output:**

- `migration-report.html` — Self-contained HTML report with executive summary and detailed appendix

**Non-blocking:** If report generation fails after `VALIDATE_OK` (HTML build error only), log a warning and continue. Validation `GATE_FAIL` is **not** a silent skip — always surface to the user. Do NOT fail the Generate phase for report issues.

**Shared paths:**

- `$GCP_SHARED = ${CLAUDE_PLUGIN_ROOT}/skills/gcp-to-aws/references/shared`

## Step 0: Validate Artifacts (Read Only)

Load and execute `references/shared/validate-fly-report.md` (relative to the fly-to-aws skill root) **before** building report content.

- Run all **required** checks (field presence only — do not rewrite artifact prose).
- On any `GATE_FAIL`: output failure lines to the user, **do NOT write** `migration-report.html`, **do NOT patch artifacts**, return to parent `generate.md`.
- On `VALIDATE_OK`: proceed to Step 1.

## Prerequisites

At least one of these must exist in `$MIGRATION_DIR/`:

- Design artifact: `aws-design.json`
- Estimation artifact: `estimation-infra.json`

If **none** exist: skip report generation. Output: "Skipping HTML report — no migration artifacts found."

## Data Sources

Gather data from all available artifacts. Each section below notes which artifact provides the data.

**`fly-resource-inventory.json` is a ROOT ARRAY of app entries** — `process_groups[]`, `databases[]`, `object_storage[]`, `volumes[]`, `extensions[]`, `network_flags` live under EACH app entry, not at the root. To aggregate across a multi-app repo, iterate the array and sum/concat the per-app fields (e.g. total process groups = sum of `app.process_groups.length` over all apps). Never read `process_groups` from the root object — the root is a list.

| Data Point                              | Primary Source                                                                                                                  | Fallback                                    |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| fly.io stack detected                   | `fly-resource-inventory.json` `[]` → per-app `process_groups[]`, `databases[]`, `object_storage[]`, `volumes[]`, `extensions[]` | `aws-design.json`                           |
| AWS compute mappings                    | `aws-design.json` `compute.<group>.target`                                                                                      | —                                           |
| How each compute route was chosen       | `aws-design.json` `compute.<group>.layer_fired` + `.decided_by`                                                                 | —                                           |
| Database / cache / storage / network    | `aws-design.json` `databases[]`, `cache[]`, `storage[]`, `network`                                                              | —                                           |
| Current fly.io monthly cost             | `estimation-infra.json` `current_costs.fly_monthly`                                                                             | —                                           |
| Projected AWS monthly cost (Balanced)   | `estimation-infra.json` `projected_costs.aws_monthly_balanced`                                                                  | —                                           |
| Cost breakdown per service              | `estimation-infra.json` `projected_costs.breakdown`                                                                             | —                                           |
| Cost tiers (premium/balanced/optimized) | `estimation-infra.json` `cost_comparison`                                                                                       | —                                           |
| Optimization opportunities              | `estimation-infra.json` `optimization_opportunities`                                                                            | —                                           |
| Migration decision / recommendation     | `estimation-infra.json` `recommendation`                                                                                        | `financial_summary.recommendation` (string) |
| Top risks / attention items             | `generation-warnings.json` `warnings[]` + `aws-design.json` `specialist_gates[]`, `warnings[]`, `network.decision_records[]`    | —                                           |
| GPU flag                                | `fly-resource-inventory.json` `[]` → per-app `process_groups[].flags.gpu == true` (authoritative gate)                          | —                                           |
| Agent-tier flag                         | `aws-design.json` `compute.<group>.decided_by == "agent-advisor"` (+ `advisor_ctx`)                                             | —                                           |
| Migration timeline                      | `MIGRATION_GUIDE.md` / `CUTOVER_RUNBOOK.md` phases, complexity tier                                                             | —                                           |
| Generated artifact catalog              | On-disk existence of `terraform/`, `k8s/`, `scripts/`, docs, `.github/workflows/`                                               | —                                           |
| User configuration choices              | `preferences.json` (read `.value` and `.chosen_by` from wrapped fields)                                                         | —                                           |

## Step 1: Build Executive Summary Section

The executive summary is the first thing visible when opening the report. Design it to fit approximately 1–2 printed pages.

### Executive Summary Content

**Header:** "fly.io to AWS Migration Assessment" with subtitle "Executive Summary" and generation date.

**GPU sunset banner (conditional — render FIRST, above Section 0):**

Gate on the inventory ONLY: if ANY process group across ANY app entry in `fly-resource-inventory.json` has `flags.gpu == true`, render a prominent top-of-report banner inside `<section id="gpu-sunset">`:

> ⚠️ **Fly GPU Machines hard sunset 2026-08-01 — forced migration.** GPU workloads must move before this date. See Appendix A for the GPU-to-AWS instance mapping (a10 → g5, l40s → g6e, a100-40gb → p4d, a100-80gb → p4de).

Style with `.callout-critical`. Do NOT render this section if no group has `flags.gpu == true` — do not trigger it from `warnings[]` prose (a warning string mentioning GPU is not a GPU workload; the `flags.gpu` boolean is the single source of truth).

**Agent-tier dual-track callout (conditional):**

If ANY `aws-design.json → compute.<group>.decided_by == "agent-advisor"`, render a callout inside `<section id="agent-tier">` (place near the top, after the GPU banner if present, before or within Section 0):

> **Agent tier is a separate track.** The agent tier ([group name(s)]) is **NOT deployed by this Terraform** — it runs on [`compute.<group>.target`, e.g. `agentcore`] via the **agent-advisor** skill, and its LLM calls migrate via **llm-to-bedrock**. Validate classification quality before cutover.

Pull the runtime from `compute.<group>.target` (and `advisor_ctx.verdict` / `advisor_ctx.deployment_model` when present). Style with `.callout-warning`. Do not render this section if no group has `decided_by == "agent-advisor"`.

**Section 0 — Migration Decision Summary (REQUIRED):** `<section id="decision-summary">`

Pull from `estimation-infra.json → recommendation`. Fallback if `recommendation` block is absent: use `financial_summary.recommendation` (string) as `path_label` and synthesize `migrate_if` / `stay_if` from `estimate.md` Part 7 defaults.

Content when `recommendation` block exists:

1. **Verdict badge:** `recommendation.path_label` — render as colored badge (green for `migrate_optimized`, blue for `migrate_phased`, amber for `stay`).
2. **Cost headline:** Balanced AWS monthly (`estimation-infra.json → cost_comparison.option_b_balanced.aws_monthly`) vs the Fly baseline. The Fly baseline source of truth is `current_costs.fly_monthly`; `cost_comparison.fly_monthly_baseline` is a copy of the same figure — if the two disagree, use `current_costs.fly_monthly`. If `current_costs.fly_monthly` is null (baseline unavailable): show Balanced AWS monthly labeled "Fly.io baseline unavailable — no comparison."
3. **Timeline:** from the migration window / complexity tier (see Section 4). Do NOT use `recommendation.next_steps` as timeline — those are action items, not duration.
4. **Migrate if / Stay if:** from `recommendation.migrate_if` and `recommendation.stay_if`. Render as two compact lists.
5. **Next steps (optional):** from `recommendation.next_steps` — compact bullet list separate from timeline.

**Specialist engagement flag:** If `aws-design.json → specialist_gates[]` is non-empty, add a prominent callout:

> ⚠️ **Specialist engagement required:** [gate name(s)] — [reason]. Engage your AWS account team before including these in cost projections or migration timelines.

Source: `estimation-infra.json → recommendation`, `aws-design.json`

**Section 1 — Current fly.io Stack:** `<section id="exec-services">`

- Count of process groups + services from `fly-resource-inventory.json`.
- List each in fly vocabulary: process groups (web / worker / agent / nightly with their `vm.preset`), Managed Postgres (MPG) / legacy Fly Postgres from `databases[]`, Upstash from `extensions[]`, Tigris buckets from `object_storage[]`, and volumes from `volumes[]`.
- Source: `fly-resource-inventory.json`

**Section 2 — Recommended AWS Architecture:** `<section id="exec-services">` (services table) — may share the exec-services block or use a sub-heading.

- Table with columns: **Fly Concept**, **AWS Service**, **How we chose this**.
- **How we chose this** — fill from `aws-design.json → compute.<group>.layer_fired` + `.decided_by`. This is fly's advantage over confidence tags — it is a grounded audit trail. Render as a readable phrase, for example:
  - `decided_by == "routing_table"` → "Deterministic routing (layer [layer_fired])"
  - `decided_by == "agent-advisor"` → "Agent-advisor verdict (layer [layer_fired])"
  - `decided_by == "user"` → "Your explicit choice (layer [layer_fired])"
- One row per compute group (Fly Machine group → `target`), plus rows for each database (`databases[].source_type` → `target`), cache (`cache[].source_type` → `target`), storage (`storage[].name` → `recommendation`), and network (`network.ingress`; and each `network.decision_records[].pattern` → `aws_equivalent`).
- If any row maps to a `specialist_engagement` recommendation or appears in `specialist_gates`, mark it with a warning indicator and footnote: "Specialist guidance recommended — contact your AWS account team."
- Source: `aws-design.json`

**Section 3 — Cost Comparison:** `<section id="exec-costs">`

- Side-by-side display: Current fly.io Monthly (`current_costs.fly_monthly`) vs Projected AWS Monthly (**Balanced** tier — `projected_costs.aws_monthly_balanced`).
- Percent change (savings or increase) from `cost_comparison.option_b_balanced.percent_change`.
- **How to read cost tiers (callout box — required when three tiers exist):** The three AWS monthly figures are **pricing scenarios** for the **same** mapped architecture (same services in `aws-design.json`), not three different generated Terraform stacks. Use **Balanced** as the **primary** row vs fly.io; **Premium** and **Optimized** are **bounds** (higher HA / newer skew vs cost-optimization skew).
- If 3 tiers available (`cost_comparison.option_a_premium`, `option_b_balanced`, `option_c_optimized`): show **Premium**, **Balanced**, and **Optimized** with short subtitles:
  - **Premium** — _Highest resilience / highest monthly estimate in this model_
  - **Balanced** — _Default scenario; compare fly.io to this row first_
  - **Optimized** — _Lower monthly estimate; reservations, Spot, or storage trade-offs assumed_
- **Footnote (required, verbatim intent):** _Only one Terraform baseline is generated (Balanced-aligned); Premium and Optimized are what-if cost models in `estimation-infra.json`. Adjust the generated IaC yourself if you want those postures in production._
- **Idle-cost-delta note (conditional):** If `projected_costs.breakdown` contains a "Scale-to-zero idle cost delta" entry (a scale-to-zero group became Fargate min-1), surface it verbatim:

  > **Idle cost note:** [Pull the `note`/`delta` field verbatim] — a fly.io scale-to-zero group now runs as an always-on Fargate task.

- If an observability entry exists in `projected_costs.breakdown` (array where `service` contains "Observability", OR object where key contains `observability` or `cloudwatch`) AND its `note` mentions the Fly Logdrain free tier:

  > **Observability cost note:** [Pull the `note` field verbatim]

- Source: `estimation-infra.json`

**Section 4 — Timeline:** `<section id="exec-timeline">`

- Total migration window and approach (phased / fast-track / conservative), derived from the complexity tier and the phases in `MIGRATION_GUIDE.md` / `CUTOVER_RUNBOOK.md`.
- Source: `MIGRATION_GUIDE.md`, `CUTOVER_RUNBOOK.md`, complexity tier

**Section 5 — Top Risks / Attention Items:** `<section id="exec-risks">`

- Up to the highest-priority attention items, each with a one-line description and mitigation.
- Pull from `generation-warnings.json → warnings[]`, `aws-design.json → specialist_gates[]`, `aws-design.json → warnings[]`, and `aws-design.json → network.decision_records[]` (for example: fly-replay has no AWS LB equivalent; multi-region not generated in v1; dynamic 6PN discovery needs code rewrite; agent tier deploys via agent-advisor + llm-to-bedrock).
- Source: `generation-warnings.json`, `aws-design.json`

## Step 2: Build Detailed Appendix

The appendix follows the executive summary, clearly separated with an "Appendix: Detailed Migration Analysis" header.

### Appendix Section A — Service Recommendations `<section id="appendix-services">`

For each compute group, database, cache, storage, and network entry:

- Fly concept / source name and type.
- AWS target recommendation.
- **How the mapping was chosen** — `decided_by` + `layer_fired` phrase (as in Section 2).
- Full `notes[]` text from `aws-design.json`.
- For GPU groups (`ec2_gpu` target or `flags.gpu`): include the GPU-to-AWS instance mapping and the 2026-08-01 sunset note.
- If the entry appears in `specialist_gates[]` or maps to `specialist_engagement`: include the specialist guidance callout.

Source: `aws-design.json`

### Appendix Section B — Cost Estimates `<section id="appendix-costs">`

**Per-service cost breakdown table** from `projected_costs.breakdown` (Balanced tier).

**Three-tier comparison table** with columns: **Tier** (name + subtitle as in Section 3), Monthly Cost, vs Fly Monthly, Annual Difference. Source: `cost_comparison`.

Include a one-line pointer: _See executive summary — three tiers are scenario $ only; the generated Terraform matches the **Balanced** baseline._

**Optimization opportunities table** from `optimization_opportunities[]` with columns: Optimization, Target Services, Savings %, Commitment/Timing, Effort.

Source: `estimation-infra.json`

### Appendix Section C — Migration Steps `<section id="appendix-steps">`

Numbered migration phases from `MIGRATION_GUIDE.md` / `CUTOVER_RUNBOOK.md`, each with phase name, services included, and estimated duration where available.

**Rollback procedure** — triggers and steps from `CUTOVER_RUNBOOK.md → Rollback Plan`.

Source: `MIGRATION_GUIDE.md`, `CUTOVER_RUNBOOK.md`

### Appendix Section E — Generated Artifacts Catalog `<section id="appendix-artifacts">`

List all files and directories generated during the Generate phase. **Check for actual file/directory existence before listing.**

- `terraform/` — list `.tf` files (if present)
- `k8s/` — list manifests (if present)
- `scripts/` — list migration scripts (if present)
- `.github/workflows/deploy-aws.yml` (if present)
- `MIGRATION_GUIDE.md`, `README.md`, `SECRETS_CHECKLIST.md`, `CUTOVER_RUNBOOK.md`
- `generation-warnings.json` (if present)

**Data artifacts (for detailed review):**

| Artifact                      | Contents                                                   |
| ----------------------------- | ---------------------------------------------------------- |
| `preferences.json`            | All migration configuration choices and their sources      |
| `fly-resource-inventory.json` | Complete fly.io resource inventory with signals            |
| `estimation-infra.json`       | Detailed cost model, recommendation, per-service breakdown |
| `aws-design.json`             | Full architecture design with rationale per service        |

Do not list files that were not generated.

### Appendix Section F — Your Configuration (conditional) `<section id="appendix-config">`

**Only include if `preferences.json` exists in `$MIGRATION_DIR/`.**

Key decisions that shaped this migration plan. Each value is read from `preferences.json` using the `.value` field of wrapped preference objects.

| Decision                 | Your choice         | Source (`chosen_by`)             |
| ------------------------ | ------------------- | -------------------------------- |
| Target AWS region        | region value        | `user` / `extracted` / `default` |
| Availability requirement | availability value  | `user` / `extracted` / `default` |
| Scale-to-zero intent     | scale-to-zero value | `user` / `extracted` / `default` |
| (other set preferences)  | value               | `chosen_by`                      |

Render only the preferences that are actually present. `chosen_by`: `"user"` (explicitly answered), `"extracted"` (inferred from fly.toml/code), or `"default"` (plugin default applied).

**Full detail:** Open `preferences.json` in this directory.

Source: `preferences.json`

## Step 3: Generate HTML

### Pre-Write Sanity Check (mandatory)

Immediately before writing the file, **re-read from disk**:

1. `estimation-infra.json → recommendation.path_label` present OR Step 1 fallback documented.
2. Assembled HTML string contains `<section id="decision-summary">`.
3. If any group has `flags.gpu` → HTML contains `<section id="gpu-sunset">`. If any group has `decided_by == "agent-advisor"` → HTML contains `<section id="agent-tier">`.

If any check fails: emit `GATE_FAIL | phase=generate | field=<path> | reason=missing`, do **not** write the file, return to parent.

Write the complete HTML to `$MIGRATION_DIR/migration-report.html`.

### HTML Structure (required section IDs)

The output MUST include these `id` attributes (content from Steps 1–2; gates check **presence only**):

| Section ID           | Content                                 |
| -------------------- | --------------------------------------- |
| `decision-summary`   | Section 0 — Migration Decision Summary  |
| `exec-services`      | Current fly.io stack + AWS architecture |
| `exec-costs`         | Cost comparison headline                |
| `exec-timeline`      | Timeline                                |
| `exec-risks`         | Top risks / attention items             |
| `appendix-services`  | Appendix A                              |
| `appendix-costs`     | Appendix B                              |
| `appendix-steps`     | Appendix C                              |
| `appendix-artifacts` | Appendix E                              |

Conditional IDs (include when data exists): `appendix-config` (preferences.json exists), `gpu-sunset` (any `flags.gpu`), `agent-tier` (any `decided_by == "agent-advisor"`).

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>fly.io to AWS Migration Assessment</title>
  <style>
    /* All CSS inline — see CSS specification below */
  </style>
</head>
<body>
  <div class="report">
    <!-- <section id="gpu-sunset"> when any process group has flags.gpu -->
    <!-- <section id="agent-tier"> when any compute group decided_by == "agent-advisor" -->
    <div class="executive-summary">
      <section id="decision-summary"><!-- Section 0 --></section>
      <section id="exec-services"><!-- Current fly.io stack + AWS architecture --></section>
      <section id="exec-costs"><!-- Cost headline --></section>
      <section id="exec-timeline"><!-- Timeline --></section>
      <section id="exec-risks"><!-- Top risks --></section>
    </div>
    <div class="appendix">
      <section id="appendix-services"><!-- Appendix A --></section>
      <section id="appendix-costs"><!-- Appendix B --></section>
      <section id="appendix-steps"><!-- Appendix C --></section>
      <section id="appendix-artifacts"><!-- Appendix E --></section>
      <!-- <section id="appendix-config"> when preferences.json exists -->
    </div>
    <footer>
      Generated by the fly.io to AWS Migration Advisor — draft for review; verify figures against source JSON artifacts before executive sign-off.
    </footer>
  </div>
</body>
</html>
```

### CSS Specification

The inline CSS must include:

**Layout:**

- `body`: font-family system-ui, -apple-system, sans-serif; max-width 900px; margin 0 auto; padding 40px 20px; color #1a1a2e; background #ffffff; line-height 1.6
- `.report`: single container

**Typography:**

- `h1`: font-size 1.8rem; color #1a1a2e; border-bottom 3px solid #ff9900; padding-bottom 8px
- `h2`: font-size 1.4rem; color #232f3e; margin-top 2rem
- `h3`: font-size 1.1rem; color #545b64

**Tables:**

- `table`: width 100%; border-collapse collapse; margin 1rem 0
- `th`: background #232f3e; color white; padding 10px 12px; text-align left; font-size 0.85rem
- `td`: padding 8px 12px; border-bottom 1px solid #e8e8e8; font-size 0.85rem
- `tr:hover`: background #f5f5f5

**Cards (for executive summary metrics):**

- `.metric-card`: display inline-block; background #f8f9fa; border 1px solid #e8e8e8; border-radius 8px; padding 16px 24px; margin 8px; text-align center; min-width 160px
- `.metric-value`: font-size 1.6rem; font-weight bold; color #232f3e
- `.metric-label`: font-size 0.8rem; color #687078; text-transform uppercase

**Cost comparison highlight:**

- `.cost-savings`: color #067d68 (green for savings)
- `.cost-increase`: color #d13212 (red for increase)

**Callouts:**

- `.callout-warning`: background #fff8e1; border-left 4px solid #ff9900; padding 12px 16px; margin 1rem 0; border-radius 0 4px 4px 0 (agent-tier, specialist engagement)
- `.callout-critical`: background #fce8e6; border-left 4px solid #d13212; padding 12px 16px; margin 1rem 0; border-radius 0 4px 4px 0; font-weight 600 (GPU sunset banner)

**Verdict badges (Section 0):**

- `.badge`: display inline-block; padding 2px 8px; border-radius 12px; font-size 0.75rem; font-weight 600
- `.badge-verdict-migrate`: background #e6f4ea; color #137333 — `migrate_optimized`
- `.badge-verdict-phased`: background #e8f0fe; color #1a73e8 — `migrate_phased`
- `.badge-verdict-stay`: background #fef7e0; color #b05a00 — `stay`

**Print styles:**

- `@media print`: adjust margins; ensure `page-break-before: always` on `.appendix`

**Footer:**

- `footer`: margin-top 3rem; padding-top 1rem; border-top 1px solid #e8e8e8; text-align center; color #687078; font-size 0.8rem

### Content Rules

1. **All data must come from artifacts** — do not invent numbers or services. If an artifact field is missing, omit that section.
2. **Currency formatting**: All cost values displayed as `$X,XXX.XX` with dollar sign and commas.
3. **Percentage formatting**: Include `+` or `-` prefix. Use green styling for savings, red for increases.
4. **No external resources**: No CDN links, no external fonts, no images. Everything inline.
5. **Valid HTML5**: Output must be valid, well-formed HTML5.

## Step 4: Self-Check

After generating the HTML file, verify:

1. **Required section IDs**: `decision-summary`, `exec-services`, `exec-costs`, `exec-timeline`, `exec-risks`, `appendix-services`, `appendix-costs`, `appendix-steps`, `appendix-artifacts` each appear as `<section id="...">`. If any missing: treat as build failure (warn user; do not fail Generate phase).
2. **Conditional section IDs**: `gpu-sunset` present iff any group has `flags.gpu`; `agent-tier` present iff any group has `decided_by == "agent-advisor"`; `appendix-config` present iff `preferences.json` exists.
3. **Data accuracy**: Cost figures in HTML match the estimation artifact values exactly.
4. **Cost tier footnote**: The "only one Terraform baseline is generated (Balanced-aligned)" footnote is present when three tiers exist.
5. **Valid HTML**: Opening and closing tags match, no broken table structures.
6. **No placeholders**: No `[placeholder]` or `TODO` text in the report output.
7. **Footer disclaimer**: Footer contains "draft for review".

## Step 5: Open Report in Browser

After writing the HTML file, open it in the user's default browser so they can view it immediately.

Run: `open "$MIGRATION_DIR/migration-report.html"` (macOS) or `xdg-open "$MIGRATION_DIR/migration-report.html"` (Linux).

If the open command fails, fall back to presenting the full file path to the user:

```
Migration report ready — open in your browser:
file://$MIGRATION_DIR/migration-report.html
```

## Completion

Report to the parent orchestrator. **Do NOT update `.phase-status.json`** — the parent `generate.md` handles phase completion.

Output:

```
Migration report saved to $MIGRATION_DIR/migration-report.html

Report sections:
- Executive Summary: Section 0 Migration Decision Summary, [process-group count] fly.io process groups, [cost comparison], [timeline]
- [GPU sunset banner — if any GPU group]
- [Agent-tier dual-track callout — if any agent-advisor group]
- Appendix A: Service Recommendations
- Appendix B: Cost Estimates
- Appendix C: Migration Steps
- Appendix E: Artifacts Catalog
- [Appendix F: Your Configuration — if preferences.json exists]
```
