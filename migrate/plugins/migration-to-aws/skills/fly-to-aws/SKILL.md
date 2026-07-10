---
name: fly-to-aws
description: "Migrate workloads from fly.io to AWS. Triggers on: migrate from fly.io, fly.io to AWS, move off fly.io, fly.toml, Fly Machines to AWS, Fly Postgres to RDS, Tigris to S3, fly.io GPU sunset, migrate Fly app, Fly to Fargate, Fly to ECS, Fly to Lambda, leave fly.io, migrate off fly.io platform, Fly scale-to-zero to AWS, Fly volumes to AWS, Fly 6PN to VPC. Runs a 6-phase process: discover fly.io resources from fly.toml, Dockerfile, code signals, and optional flyctl JSON exports, clarify migration requirements, design AWS architecture with bidirectional agent-advisor integration for AI agent workloads, estimate costs, generate migration artifacts, and optionally share the plan for partner matching. Clarify must finish before Design, Estimate, or Generate. Uses a flat resource model with deterministic routing tables for compute (Machines → Fargate/Lambda/MicroVMs/AgentCore), data (Fly Postgres/MPG → RDS/Aurora, Tigris → S3, Upstash Redis → ElastiCache), and networking (6PN → VPC, fly-replay detection). GPU users face hard sunset 2026-08-01. Do not use for: GCP or Azure migrations to AWS, Heroku migrations (use heroku-to-aws), pure LLM API rewrite without fly.io footprint (use llm-to-bedrock), runtime choice for an agent with no fly.io context (use agent-advisor)."
---

# fly.io-to-AWS Migration Skill

## Philosophy

- **Segment-specific urgency — no blanket KTLO narrative.** fly.io is not in Heroku-style sustaining mode; it is pivoting (agent sandboxes + Managed Postgres) with retrenchment at the edges. Three urgency tiers, stated factually with citations:
  - **GPU users: forced migration, hard sunset 2026-08-01** ("GPUs are deprecated and will be unavailable after August 1" — fly.io/docs/gpus). Highest urgency.
  - **Users in the 17 deprecated regions** (Sep 2025 consolidation from 35 to 18 regions): re-planning needed.
  - **Generic PaaS users**: strategic center-of-gravity shift toward agent sandboxes + documented reliability incidents (3-day PG outage 2023, Nov 2024 outage, "deleted my apps" complaints 2024 & Mar 2026), cited factually, never exaggerated. No forced-exit framing.
- **Config ≠ intent.** `fly launch` defaults to scale-to-zero (`auto_stop_machines="stop"`, `min_machines_running=0`), so nearly every fly.toml carries that semantic — often without the user ever having chosen it. Discover records fly.toml values as _signals_; Clarify must confirm whether each routing-relevant semantic is a deliberate requirement or an inherited default before the compute routing table fires. This extends agent-advisor's existing critical-question rule: Discover-inferred values on critical dimensions must be user-confirmed.
- **Forbidden targets.** Never recommend: AWS App Runner (closed to new customers 2026-04-30), Copilot CLI (EOL 2026-06-12), Elastic Beanstalk (existing plugin rule). Default generated deploy story **for Fargate/ECS routes**: ECR + ECS Express Mode + GitHub Actions (OIDC). Other routes generate route-specific artifacts — one pipeline does not cover all routes.
- **Re-platform by default**: Select AWS services that match fly.io workload types (Fly Machines → Fargate, Fly Postgres/MPG → RDS/Aurora, Tigris → S3, Upstash Redis → ElastiCache Serverless).
- **Dev sizing unless specified**: Default to development-tier capacity (e.g., db.t4g.micro, single AZ, 0.5 vCPU Fargate). Upgrade only on user direction.
- **No human one-time migration costs**: Do not present human labor, professional services, or people-time work as dollar estimates or "one-time migration cost" budget categories. Vendor charges grounded in data (for example fly.io invoice line items in the infra estimate when billing exists) are allowed.
- **Flat resource model**: fly.io resources are organized per-app and per-process-group without dependency graphs or clustering. No topological sorting, typed edges, or cluster formation logic. Resources are processed as a flat list in input order.
- **Deterministic mappings**: Core services use fixed routing tables (Compute Routing Table, Machine Preset Table, Postgres Table, Fast-Path Table, Volumes Decision, Network Table). Unknown extensions or workload types hit the specialist gate.

---

## Definitions

- **"Load"** = Read the file using the Read tool and follow its instructions. Do not summarize or skip sections.
- **`$MIGRATION_DIR`** = The run-specific directory under `.migration/` (e.g., `.migration/0709-1430/`). Set during Phase 1 (Discover).

---

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable and prevent instruction-following degradation:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions MUST NOT be loaded unless the condition is met. Do not speculatively load files.
- **No duplication:** Mapping tables, pricing data, and shared warnings exist in one canonical file. Other files reference them; they do not copy them inline.
- **Progressive depth:** Phase orchestrators (`design.md`, `generate.md`) contain short routing logic that points to detailed sub-files. Load the sub-file only when its path is selected.

**Conditional reference files (load ONLY when condition is true):**

| File                                               | Condition                                                                          |
| -------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `design-refs/postgres-table.md`                    | Inventory contains `database` entries                                              |
| `design-refs/volumes-decision.md`                  | Inventory contains `[[mounts]]` volumes                                            |
| `design-refs/network-table.md`                     | Inventory has `[[services]]` non-http handlers, multi-region, 6PN/fly-replay flags |
| `design-refs/fast-path-table.md`                   | Inventory `extensions[]` OR `object_storage[]` (Tigris) non-empty                  |
| `references/phases/design/design-agent-handoff.md` | Any process group confirmed `agent_candidate`                                      |

When adding new reference files, verify the phase's total loaded instructions remain under budget. If a new file would exceed ~800 lines when combined with other loaded refs, split it or make it conditional.

---

## Prerequisites

User must provide:

- **fly.toml** (REQUIRED for declarative discovery): One or more fly.toml files (monorepo / multi-app setups each inventoried). No fly.toml → do NOT hard-stop: if code signals show Machines-API usage (`api.machines.dev`), offer the agent-advisor handoff for that portion and mark everything else detect-only with a clear "declarative discovery needs fly.toml" message; with no Fly signals at all, stop.
- **Dockerfile / Procfile** (SUPPLEMENTARY): Supplements fly.toml with build and process command details.
- **Optional flyctl JSON exports** (USER-RUN): `fly machines list --json`, `fly volumes list --json`, `fly ips list --json`, `fly secrets list --json` (names only). These fill in actuals fly.toml cannot declare: real machine count/sizes/region spread. We never run flyctl ourselves (no credential risk).
- **Billing data** (OPTIONAL): fly.io Dashboard invoices or billing exports (for cost comparison).

**Note:** Platform API discovery is NOT supported in v1. No API token is required or used. We never run flyctl commands.

---

## State Machine

This is the execution controller. After completing each phase, consult this table to determine the next action.

| Current State | Condition                                                             | Next Action                                                                                                                                           |
| ------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `discover`    | `phases.discover != "completed"`                                      | Load `references/phases/discover/discover.md`                                                                                                         |
| `clarify`     | `phases.discover == "completed"` AND `phases.clarify != "completed"`  | Load `references/phases/clarify/clarify.md`                                                                                                           |
| `design`      | `phases.clarify == "completed"` AND `phases.design != "completed"`    | Load `references/phases/design/design.md`                                                                                                             |
| `estimate`    | `phases.design == "completed"` AND `phases.estimate != "completed"`   | Load `references/phases/estimate/estimate.md`                                                                                                         |
| `generate`    | `phases.estimate == "completed"` AND `phases.generate != "completed"` | Load `references/phases/generate/generate.md`                                                                                                         |
| `complete`    | `phases.generate == "completed"` AND `phases.share == "pending"`      | Offer the after-Generate share prompt (see **Share Checkpoints**); set `phases.share` to `"completed"` per the user's choice, then migration complete |
| `complete`    | `phases.generate == "completed"` AND `phases.share == "completed"`    | Migration planning complete                                                                                                                           |

**How to determine current state (deterministic):**

1. Read `$MIGRATION_DIR/.phase-status.json`
2. If `current_phase` exists, use it (must match one of: discover, clarify, design, estimate, generate, complete)
3. Otherwise use ordered phase evaluation: `discover` → `clarify` → `design` → `estimate` → `generate`
4. Pick the **first** phase in that order where `phases.<phase> != "completed"`; if none, state is `complete`

**Phase gate checks**: If prior phase incomplete, do not advance (e.g., cannot enter estimate without completed design).

**Clarify is mandatory:** Do not load `references/phases/design/design.md`, `references/phases/estimate/estimate.md`, or `references/phases/generate/generate.md` unless `$MIGRATION_DIR/.phase-status.json` exists and `phases.clarify` is exactly `"completed"`. A `preferences.json` file alone is **not** sufficient proof that Clarify ran. If the user asks to skip Clarify or jump straight to Design, cost estimate, or artifact generation, refuse briefly, then load `references/phases/clarify/clarify.md` and run Phase 2. There is no exception for "quick" or "obvious" migrations.

**Share checkpoints**: Optional plan sharing is offered after Estimate and after Generate. No feedback telemetry is collected. See the **Share Checkpoints** section below for details.

### Handoff Gate Orchestration (Fail Closed)

Load `$GCP_SHARED/handoff-gates.md` when executing any phase completion step (`$GCP_SHARED = ${CLAUDE_PLUGIN_ROOT}/skills/gcp-to-aws/references/shared`; the fly-to-aws `references/shared/` directory only holds the two local schema files plus a redirect README).

1. **Single `$MIGRATION_DIR`**: Use one run directory for the entire migration. Do not mix artifacts across `.migration/*/` sessions.
2. **Re-read from disk**: Before each phase (and before each handoff gate), Read required artifacts from `$MIGRATION_DIR/`. Do not rely on chat memory.
3. **Advance only on `HANDOFF_OK`**: A phase is complete only when its orchestrator emits `HANDOFF_OK | phase=<name> | artifacts=...`. Do not load the next phase without it.
4. **On `GATE_FAIL`**: Output the failure line(s) to the user in plain language. **Do NOT modify artifacts** to pass the gate. **Do NOT continue** to the next phase. Tell the user which phase to re-run.
5. **Re-entry**: Re-running an earlier phase after downstream phases completed requires explicit user confirmation; downstream phases must be reset to `"pending"`. See `handoff-gates.md` re-entry table.

Generate phase additionally loads `$GCP_SHARED/validate-artifacts.md` before writing `migration-report.html`.

---

## State Validation

When reading `$MIGRATION_DIR/.phase-status.json`, validate before proceeding:

1. **Multiple sessions**: If multiple directories exist under `.migration/`, list them with their phase status and ask: [A] Resume latest, [B] Start fresh, [C] Cancel.
2. **Invalid JSON**: If `.phase-status.json` fails to parse, STOP. Output: "State file corrupted (invalid JSON). Delete the file and restart the current phase."
3. **Unrecognized phase**: If `phases` object contains a phase not in {discover, clarify, design, estimate, generate, share}, STOP. Output: "Unrecognized phase: [value]. Valid phases: discover, clarify, design, estimate, generate, share."
4. **Unrecognized status**: If any `phases.*` value is not in {pending, in_progress, completed}, STOP. Output: "Unrecognized status: [value]. Valid values: pending, in_progress, completed."
5. **Invalid `current_phase`** (if present): If `current_phase` is not in {discover, clarify, design, estimate, generate, complete}, STOP. Output: "Unrecognized current_phase: [value]. Valid values: discover, clarify, design, estimate, generate, complete."
6. **Out-of-order completion**: For ordered phases [discover, clarify, design, estimate, generate], if any later phase is `"completed"` while an earlier phase is not `"completed"`, STOP. Output: "Inconsistent phase ordering detected. Reconcile `.phase-status.json` before resuming."
7. **Multiple active phases**: Across core phases {discover, clarify, design, estimate, generate}, at most one phase may be `"in_progress"`. If >1, STOP. Output: "Multiple phases are in_progress. Keep only one active phase before resuming."

---

## State Management

Migration state lives in `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`), created by Phase 1 and persisted across invocations.

**.phase-status.json schema:**

```json
{
  "migration_id": "0709-1430",
  "last_updated": "2026-07-09T14:30:00Z",
  "current_phase": "discover",
  "phases": {
    "discover": "in_progress",
    "clarify": "pending",
    "design": "pending",
    "estimate": "pending",
    "generate": "pending",
    "share": "pending"
  }
}
```

**Status values:** `"pending"` → `"in_progress"` → `"completed"`. Never goes backward.
For core phases (discover, clarify, design, estimate, generate), at most one phase may be `"in_progress"` at any time.
`current_phase` is optional but recommended; when present it is authoritative.

The `.migration/` directory is automatically protected by a `.gitignore` file created in Phase 1.

### Phase Status Update Protocol

Use **read-merge-write** updates for `.phase-status.json`:

1. Read the current file before every update.
2. Change only the phase keys being advanced and `last_updated`.
3. Keep prior completed phases unchanged.
4. Set `current_phase` to the next deterministic phase (or `complete` after generate).
5. Write the full file in the same turn as your final phase work message.

---

## Phase Summary Table

| Phase                | Inputs                                                                                                                                                          | Outputs                                                                                                                                                                                                                           | Reference                                |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| **Discover**         | fly.toml(s), Dockerfile, optional flyctl JSON exports (`fly machines list --json`, `fly volumes list --json`, `fly ips list --json`, `fly secrets list --json`) | `fly-resource-inventory.json`, `.phase-status.json` updated                                                                                                                                                                       | `references/phases/discover/discover.md` |
| **Clarify**          | `fly-resource-inventory.json`                                                                                                                                   | `preferences.json`, `.phase-status.json` updated                                                                                                                                                                                  | `references/phases/clarify/clarify.md`   |
| **Design**           | `fly-resource-inventory.json`, `preferences.json`                                                                                                               | `aws-design.json` (+ embedded advisor verdicts)                                                                                                                                                                                   | `references/phases/design/design.md`     |
| **Estimate**         | `aws-design.json`, `preferences.json`, optional billing profile                                                                                                 | `estimation-infra.json`, `.phase-status.json` updated                                                                                                                                                                             | `references/phases/estimate/estimate.md` |
| **Generate**         | `aws-design.json`, `estimation-infra.json`, `preferences.json`, `fly-resource-inventory.json`                                                                   | `terraform/` or `k8s/`, `MIGRATION_GUIDE.md`, `README.md`, database migration scripts, GitHub Actions workflows, `migration-report.html` (if generated), `generation-warnings.json` (if applicable), `.phase-status.json` updated | `references/phases/generate/generate.md` |
| **Share** (optional) | `.phase-status.json` (discover completed minimum), `preferences.json`, `estimation-infra.json`                                                                  | `share.json`, `.phase-status.json` updated                                                                                                                                                                                        | `references/phases/share/share.md`       |

---

## Share Checkpoints

The user may optionally share their migration plan for AWS partner matching. This is offered once after Estimate and again after Generate. Sharing is optional and never blocks progression. **This skill collects no feedback telemetry.**

**After Estimate** (if `phases.share` is `"pending"`): Output to user:

```
─── Share Your Migration Plan ───

This link encodes your migration profile for partner matching:
✓ Included: Clarify answers, estimated costs, recommendation path,
  detected fly.io services, resource names, and workload types.
✗ Excluded: Source code, local file paths, credentials, API tokens,
  config values, and environment secrets.

The link uses a URL fragment (#) — no data is sent to any server
when you click it. The landing page decodes everything client-side.

[A] Share plan
[B] No thanks, continue to Generate
```

- If user picks **A** → Load `references/phases/share/share.md`, execute it (`share_checkpoint = after_estimate`). Set `phases.share` to `"completed"`. Continue to Generate.
- If user picks **B** → Set `phases.share` to `"completed"`. Continue to Generate.

**After Generate** (only if `phases.share` is still `"pending"`): same prompt, wording "Share Your Completed Plan":

```
─── Share Your Completed Plan ───

This link encodes your migration profile for partner matching:
✓ Included: Clarify answers, estimated costs, recommendation path,
  detected fly.io services, resource names, and workload types.
✗ Excluded: Source code, local file paths, credentials, API tokens,
  config values, and environment secrets.

The link uses a URL fragment (#) — no data is sent to any server
when you click it. The landing page decodes everything client-side.

[A] Share completed plan
[B] No thanks, finish
```

- If user picks **A** → Load `references/phases/share/share.md`, execute it (`share_checkpoint = after_generate`). Mark migration complete.
- If user picks **B** → Mark migration complete.
- If `phases.share` is still `"pending"`, set it to `"completed"` regardless of choice.

---

## MCP Servers

**awspricing** (for cost estimation):

- Provides `get_pricing`, `get_pricing_service_codes`, `get_pricing_service_attributes` tools
- Only needed during Estimate phase. Discover and Design do not require it.
- Primary pricing source: `references/shared/pricing-cache.md` (cached rates, ±5-10% for infrastructure). MCP is secondary — used only for services not found in the cache.

---

## Files in This Skill

```
fly-to-aws/
├── SKILL.md                                    ← You are here (orchestrator + state machine)
│
├── references/
│   ├── phases/
│   │   ├── discover/
│   │   │   ├── discover.md                     # Phase 1: Discover orchestrator
│   │   │   ├── discover-flytoml.md             # fly.toml parsing (primary)
│   │   │   └── discover-code-signals.md        # Code grep signals (6PN, fly-replay, agent frameworks, Tigris, MPG)
│   │   ├── clarify/
│   │   │   └── clarify.md                      # Phase 2: Adaptive questions (12–15, batched ≤5)
│   │   ├── design/
│   │   │   ├── design.md                       # Phase 3: Design orchestrator (flat single-pass routing)
│   │   │   └── design-agent-handoff.md         # Agent-advisor bidirectional integration protocol
│   │   ├── estimate/
│   │   │   └── estimate.md                     # Phase 4: Cost projection
│   │   ├── generate/
│   │   │   ├── generate.md                     # Phase 5: Generate orchestrator
│   │   │   ├── generate-terraform.md           # Terraform configurations (Fargate/Lambda/Batch routes)
│   │   │   ├── generate-docs.md                # MIGRATION_GUIDE.md + README.md
│   │   │   └── generate-artifacts-report.md    # migration-report.html (self-contained HTML report)
│   │   └── share/
│   │       └── share.md                        # Phase 6: Optional share-link generation (partner matching; no telemetry)
│   │
│   ├── design-refs/
│   │   ├── compute-routing-table.md            # Deterministic compute routing (layers G/0/1/2/3/4/5)
│   │   ├── machine-preset-table.md             # Fly machine presets → Fargate CPU/memory
│   │   ├── postgres-table.md                   # Fly Postgres/MPG → RDS/Aurora sizing
│   │   ├── volumes-decision.md                 # Volumes → de-volume/EFS/ECS-on-EC2+EBS three-way
│   │   ├── fast-path-table.md                  # Extensions → AWS (Tigris→S3, Upstash→ElastiCache, etc.)
│   │   └── network-table.md                    # Networking (6PN→VPC, fly-replay flag, multi-region, TCP/UDP→NLB)
│   │
│   └── shared/                                 # References shared plugin infrastructure
│       ├── README.md                           # Path resolution to ../gcp-to-aws/references/shared/
│       ├── schema-discover-fly.md              # fly-resource-inventory.json schema
│       └── schema-aws-design-fly.md            # aws-design.json schema (with advisor injection contract)
│
└── scripts/
    ├── test_fly_decision_refs.py               # Content locks (compute-routing, machine-preset, fast-path, volumes, network)
    ├── test_fly_routing_behavior.py            # Routing outcome assertions (layer precedence, advisor injection)
    └── fixtures/
        ├── LIVE-TESTS.md                       # Manual live-test matrix (skill installed, per clarify answers)
        ├── scale-to-zero-default/
        │   └── fly.toml                        # Default shape (min=0, auto_start)
        ├── multi-group/
        │   └── fly.toml                        # web + worker + one-shot (policy=never)
        ├── stateful-legacy-pg/
        │   ├── fly.toml                        # [[mounts]] volume
        │   └── pg/fly.toml                     # flyio/postgres-flex:16 image
        └── agent-langgraph/
            ├── fly.toml                        # web + agent groups
            └── app/main.py                     # langgraph + api.machines.dev evidence
```

---

## Edge Cases

| Condition                                                              | Action                                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No fly.toml + no Fly signals                                           | Stop. Output: "No fly.toml or Fly signals detected. fly.toml is required for declarative discovery. Machines-API-only repos without fly.toml are not supported in v1."                                                                                                 |
| No fly.toml + `api.machines.dev` in code                               | Do NOT hard-stop. Offer agent-advisor handoff for the sandbox/agent portion. Mark everything else detect-only with message: "Declarative discovery needs fly.toml. The Machines-API portion can route to agent-advisor; the rest is detect-only."                      |
| GPU preset detected                                                    | Display urgency banner: "GPU Machines deprecated — hard sunset 2026-08-01. GPU-to-AWS routing available (a10→g5, l40s→g6e, a100-40→p4d, a100-80→p4de)."                                                                                                                |
| Sprites SDK detected                                                   | Mark as detect-only. Output: "Sprites (Fly's agent-sandbox product) detected — v1 is detect-only. Sandbox workloads can route to agent-advisor."                                                                                                                       |
| Unknown extension (not in Fast-Path Table)                             | Mark as "Deferred — specialist engagement". No automated mapping produced.                                                                                                                                                                                             |
| `fly-replay` header detected in code                                   | Flag as **highest-effort networking flag**. Mark group HIGH_EFFORT. Output: "fly-replay has no AWS LB equivalent — rewrite options: app-level proxy, ALB+Lambda router, CloudFront Functions. v1 emits decision records + specialist gate; no generated rewrite code." |
| Dynamic 6PN discovery detected (`top\d+.nearest.of`, `_apps.internal`) | Flag as **code-rewrite required**. Output: "Dynamic service discovery forms have no AWS equivalent — code rewrite needed. ECS Service Connect / Cloud Map cover static discovery only."                                                                                |
| True multi-region active-active (>1 region, ALB per region)            | v1 generates decision records + cost shape only (Global Accelerator ~$18/mo + DT-Premium + per-region ALBs). No multi-region infrastructure generated. Specialist gate.                                                                                                |
| Corrupted state JSON (`.phase-status.json`)                            | STOP. Output: "State file corrupted (invalid JSON). Delete the file and restart the current phase."                                                                                                                                                                    |
| awspricing unavailable after 3 attempts                                | Display user warning about ±5-10% accuracy. Use `pricing-cache.md`. Add `pricing_source: "cached_fallback"` to `estimation-infra.json`.                                                                                                                                |
| User skips questions or says "use defaults for the rest"               | Apply documented defaults for remaining questions. Phase 2 completes either way.                                                                                                                                                                                       |

---

## Defaults

- **IaC output**: Terraform configurations (default), K8s manifests (if EKS preference), Lambda SAM/Terraform (if Lambda route), migration scripts, and documentation
- **Region**: `us-east-1` (unless user specifies otherwise)
- **Sizing**: Development tier (e.g., `db.t4g.micro` for databases, 0.5 vCPU for Fargate, single AZ)
- **Cost currency**: USD
- **Timeline assumption**: 2-16 weeks depending on migration complexity — small (2-6 weeks), medium (6-12 weeks), large (12-16 weeks). See `references/shared/migration-complexity.md` for tier definitions.

---

## Workflow Execution

When invoked, the agent **MUST follow this exact sequence**:

1. **Load phase status**: Read `.phase-status.json` from `.migration/*/`.
   - If missing: Initialize for Phase 1 (Discover)
   - If exists: Determine current phase using deterministic rules in **State Machine**

2. **Determine phase to execute**:
   - If `current_phase` exists: execute that phase.
   - Otherwise execute the first non-completed phase in ordered list: discover → clarify → design → estimate → generate.
   - If all ordered phases are completed: migration is complete (with share finalization rule).

3. **Read phase reference**: Load the full reference file for the target phase.

4. **Execute ALL steps in order**: Follow every numbered step in the reference file. **Do not skip, optimize, or deviate.**

5. **Validate outputs**: Confirm all required output files exist with correct schema before proceeding. Phase orchestrators run **Completion Handoff Gate** checks per `shared/handoff-gates.md`.

6. **Handoff gate**: Emit `HANDOFF_OK` or `GATE_FAIL` per `shared/handoff-gates.md`. On `GATE_FAIL`, stop — do not update phase status or load the next phase.

7. **Update phase status**: Only after `HANDOFF_OK`. Use the Phase Status Update Protocol (read-merge-write) in the same turn as the phase's final output message.

8. **Share checkpoint**: After Estimate completes, offer optional plan sharing (partner matching, no telemetry). This runs **before** advancing to Generate; it is offered again after Generate if not yet done.

9. **Display summary**: Show user what was accomplished, highlight next phase, or confirm migration completion.

**Critical constraint**: Agent must strictly adhere to the reference file's workflow. If unable to complete a step, stop and report the specific issue. Do not fabricate or infer data.
