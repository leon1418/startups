---
name: agent-advisor
description: "Unified entry point for AI-agent work on AWS: evaluate and pick a runtime, generate a full migration plan (for existing workloads), and build an executable POC — all in one flow. Triggers on: which runtime for my agent, AgentCore vs ECS vs EKS vs Lambda, AgentCore vs Lambda MicroVMs, deploy an AI agent on AWS, agent architecture on AWS, I have an agent idea what do I build, move my agents to AWS, migrate my agents to AWS with a plan, agent migration plan, add AgentCore services, add memory/gateway/identity/policy to my agent, enable AgentCore Memory, add observability to my agent, I'm already on AWS and want to add agent capabilities, migrate Temporal workers to AWS, Temporal to AWS, run Temporal on AWS, Temporal workers on AWS, we use Temporal and want to move to AWS, our service is orchestrated by Temporal, what do I build on AWS for my Temporal workers, move a Temporal-based service to AWS, Temporal Cloud or self-hosted on AWS. Runs a phased flow: Turn 1 (entry point + technical background), Discover (lightweight code detection), Clarify (adaptive questions), deterministic scoring, Design (runtime + deployment model + services + model), Estimate (coarse cost), Generate (layered recommendation doc + scaffolding), then optional gated stages: Migration Plan (full plan generated in-skill by reusing this plugin's gcp-to-aws engine, with the advisor's decisions carried over) and POC (deployment plan + deployable proof-of-concept on the recommended runtime — AgentCore, ECS, EKS, or Lambda; generated deliverables by default, or assisted build in your account on explicit opt-in). An add-capabilities branch (for teams already running agents on AWS) recommends which AgentCore services to enable on any runtime — no runtime scoring. A temporal-worker branch moves Temporal Workers to AWS (ECS/EKS/Serverless Workers polling tier + per-Activity execution tier) without rewriting Workflow orchestration code — never a Step Functions translation. Not for: pure LLM SDK rewrite without agent architecture (use llm-to-bedrock) or detailed per-model pricing."
---

# AWS Agent Advisor

Helps startups decide how and where to run AI agents on AWS. Deterministic scoring
recommends a runtime; the conversation adapts to the user's technical background.

## Definitions

- **"Load"** = Read the file with the Read tool and follow it. Do not summarize or skip.
- **`$RUN_DIR`** = the run directory under `.agent-advisor/` (e.g. `.agent-advisor/0630-1430/`),
  created in Turn 1.
- **`$PLUGIN`** = `${CLAUDE_PLUGIN_ROOT}` (the installed plugin root). On Claude Code this token
  substitutes inline. **If `${CLAUDE_PLUGIN_ROOT}` does not resolve** (some Cursor/Codex builds,
  or a literal `${CLAUDE_PLUGIN_ROOT}` string showing up in a path error), fall back to the
  skill's own directory: this SKILL.md lives at `<plugin>/skills/agent-advisor/SKILL.md`, so the
  engine and its data are all inside this skill — scripts at `./scripts/...`, runtime profiles at
  `./references/runtimes/...`, and decision refs at `./references/decision-refs/...` relative to
  it. Prefer `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/...`; use the relative fallback only when
  it fails to resolve.

## Prerequisites

- `uv` available (for scoring). Check: `uv --version`. If missing, tell the user to install
  it (`curl -LsSf https://astral.sh/uv/install.sh | sh`) and stop.

## State Machine

After each phase, consult this table for the next action.

| Current state      | Condition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Next action                                                                           |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `turn1`            | no `$RUN_DIR/.phase-status.json`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Load `references/phases/turn1/turn1.md`                                               |
| `add_capabilities` | `turn1` done AND entry point == add_capabilities                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Load `references/phases/add-capabilities/add-capabilities.md` (self-contained branch) |
| `temporal_poc`     | `phases.temporal_poc == "in_progress"` (set when the user answers Gate T "yes" — temporal-worker.md Step 5.7). MUST be evaluated BEFORE the `temporal_worker` row, which would otherwise swallow the route                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Load `references/phases/temporal-poc/temporal-poc.md`                                 |
| `temporal_worker`  | `entry_point == temporal_worker` (set by turn1 trigger confirmation, or by discover's Temporal offer on user confirm) AND `phases.temporal_worker != "completed"`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Load `references/phases/temporal-worker/temporal-worker.md` (self-contained branch)   |
| `discover`         | `turn1` done, entry point in {build_deploy, migrate} AND code provided                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Load `references/phases/discover/discover.md`                                         |
| `clarify`          | `turn1` done (and discover done or skipped)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Load `references/phases/clarify/clarify.md`                                           |
| `clarify_pass2`    | `clarify` == "completed" AND `clarify_pass2` != "completed"                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Load `references/phases/clarify-pass2/clarify-pass2.md`                               |
| `design`           | `clarify_pass2` == "completed"                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Load `references/phases/design/design.md`                                             |
| `estimate`         | `design` done, entry point in {build_scratch, build_deploy}                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Load `references/phases/estimate/estimate.md`                                         |
| `generate`         | `design` done AND (`estimate` done OR entry point == migrate)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Load `references/phases/generate/generate.md`                                         |
| `migration_plan`   | `generate` done AND `recommendation_reviewed == true` (generate.md Step 5.5) AND entry point in {migrate, build_deploy} AND migration-eligible (see generate.md Step 6) AND user confirmed Gate 1                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Load `references/phases/migration-plan/migration-plan.md`                             |
| `poc`              | `poc == "in_progress"` (set when the user answers Gate 2 "yes" — asked in generate.md Step 7 or migration-plan.md Step 6) AND `recommendation_reviewed == true` (generate.md Step 5.5). Any winning runtime (agentcore / ecs / eks / lambda / lambda_microvms) — the POC shape follows the verdict (poc.md Step 3 dispatch on `references/decision-refs/poc-shapes.md`). Gate 2 is only offered when `migration_plan` ∈ {completed, skipped, not_applicable} — or `in_progress` on `build_deploy` only (Stage 2 failed/aborted; fallback POC from design.json per migration-plan.md failure handling); for entry point `migrate` only when `migration_plan == "completed"` (a migrate-POC without a plan has nothing to implement) | Load `references/phases/poc/poc.md`                                                   |
| `complete`         | `generate` done AND (`poc` done OR poc declined/not applicable)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Done                                                                                  |

(Persisting Gate 2 as `phases.poc = "in_progress"` makes the confirmation resumable: if the
session breaks between the "yes" and poc.md loading, the state machine re-enters `poc`
without re-asking.)

**Entry-point routing:**

- `build_scratch` → skip Discover; Clarify → Clarify Pass 2 → Design → Estimate → Generate → **Gate 2 → POC (if AgentCore)**. No migration plan (nothing existing to migrate).
- `build_deploy` → Discover (if code) → Clarify → Clarify Pass 2 → Design → Estimate → Generate → **Gate 1 → Migration Plan (if existing non-AWS AI workload detected and user confirms)** → **Gate 2 → POC (if AgentCore)**.
- `migrate` → Discover (if code) → Clarify → Clarify Pass 2 → Design → **(skip Estimate)** → Generate → **Gate 1 → Migration Plan (in-skill, reusing the sibling `gcp-to-aws` skill)** → **Gate 2 → POC (if AgentCore and the plan was produced)**. Declining Gate 1 keeps the classic handoff: pointer to `/migration-to-aws:llm-to-bedrock` with `handoff-summary.md`.
- `add_capabilities` → load `references/phases/add-capabilities/add-capabilities.md` and follow it (no runtime
  scoring; writes `capabilities-recommendation.md`). This is a self-contained branch — it does
  NOT pass through Clarify / Clarify Pass 2 / Design / Estimate / Generate, so the phase gate
  below never applies to it.
- `temporal_worker` → load `references/phases/temporal-worker/temporal-worker.md` and follow it (moves Temporal
  Workers to AWS; Workflow orchestration code untouched; writes `temporal-migration-plan.md`).
  Same self-contained-branch exemption as `add_capabilities`. Entered two ways: Turn 1 detects a
  Temporal signal in the opening message and the user confirms, or Discover (under `migrate` /
  `build_deploy`) detects the Temporal SDK and the user accepts the offer — both persist
  `entry_point = temporal_worker` in `.phase-status.json` before loading the branch. If the user
  DECLINES Discover's offer, `temporal_branch_declined: true` is persisted and the normal flow
  continues; a resumed session must not re-offer the branch.

**Phase gate:** Do NOT load design.md / estimate.md / generate.md unless
`$RUN_DIR/.phase-status.json` exists and BOTH `phases.clarify == "completed"` AND
`phases.clarify_pass2 == "completed"`. Clarify Pass 2 confirms the deployment model, the service
set, and (for a co_recommend tie) the user's `chosen_runtime` — Design and the diagram depend on
its `pass2.json` output, so it must not be skipped. If the user asks to skip Clarify or Pass 2,
refuse briefly and run it.

## State file (`.phase-status.json`)

```json
{
  "run_id": "0630-1430",
  "entry_point": "build_scratch",
  "audience": "technical",
  "current_phase": "clarify",
  "phases": {
    "turn1": "completed",
    "discover": "skipped",
    "clarify": "in_progress",
    "clarify_pass2": "pending",
    "design": "pending",
    "estimate": "pending",
    "generate": "pending",
    "migration_plan": "pending",
    "poc": "pending"
  }
}
```

Status values: `pending` → `in_progress` → `completed`, plus `skipped`. Use read-merge-write:
read before each update, change only the advancing keys, keep prior phases.

`recommendation_reviewed` (top level, boolean) is set to `true` by generate.md Step 5.5 when
the user explicitly confirms they have seen the recommendation. Gate 1, Gate 2, and the
`migration_plan` / `poc` states all require it — no gate may be asked while it is absent.

`migration_plan` additionally uses `not_applicable` (build_scratch, or no migratable workload
detected). When Stage 2 runs, `migration_plan_ctx` is added at the top level:
`{"repo": "<abs path to target repo>", "migration_dir": "<abs path to .migration/<id>/>"}` —
Stage 3 reads gcp-to-aws artifacts ONLY via this recorded path, never by re-globbing.

## Workflow Execution

1. Read `.agent-advisor/*/.phase-status.json` (latest dir). If none, start at Turn 1.
2. Determine the phase via the State Machine table.
3. Load that phase's reference file and execute every step in order.
4. Update `.phase-status.json` (read-merge-write) only after the phase's work is done.
5. Show the user what happened and what's next.

## Files

| File                                                   | Purpose                                                                 |
| ------------------------------------------------------ | ----------------------------------------------------------------------- |
| `references/phases/turn1/turn1.md`                     | Entry point + technical background + open context                       |
| `references/phases/discover/discover.md`               | Lightweight code detection                                              |
| `references/phases/clarify/clarify.md`                 | Clarify orchestrator + answer mapping to scoring keys                   |
| `references/phases/clarify/clarify-technical.md`       | Technical-background question wording                                   |
| `references/phases/clarify/clarify-business.md`        | Business-background question wording                                    |
| `references/phases/clarify-pass2/clarify-pass2.md`     | Winner-specific follow-ups                                              |
| `references/phases/design/design.md`                   | Assemble recommendation; Migrate handoff branch                         |
| `references/phases/estimate/estimate.md`               | Coarse cost magnitude                                                   |
| `references/phases/generate/generate.md`               | Layered recommendation doc + scaffolding                                |
| `references/phases/migration-plan/migration-plan.md`   | Stage 2: full migration plan via the sibling gcp-to-aws engine          |
| `references/phases/temporal-worker/temporal-worker.md` | Temporal Worker migration branch (self-contained)                       |
| `references/phases/temporal-poc/temporal-poc.md`       | Temporal worker POC (Gate T): smoke worker + ECS Terraform              |
| `references/decision-refs/temporal.md`                 | Temporal branch source of truth: Tier 1/2 tables, runbooks, commercials |
| `references/decision-refs/poc-shapes.md`               | Per-runtime POC deploy shapes (ECS/EKS/Lambda/MicroVMs/Temporal)        |
| `references/decision-refs/*.md`                        | Runtime service cards, model defaults, freshness                        |
| `references/runtimes/*.json`                           | Runtime registry (read by scoring.py)                                   |
| `scripts/scoring.py`                                   | Deterministic scoring engine                                            |
| `scripts/test_temporal_decision_refs.py`               | Content lock for the Temporal decision reference                        |
| `scripts/test_poc_shapes.py`                           | Content lock for the POC deploy shapes                                  |
