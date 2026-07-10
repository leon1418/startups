---
_fragment: migration-plan-fly-constraints
_of_phase: migration-plan
_contributes:
  - migration-plan-injection.json
---

# fly-to-aws Global Constraints for Inline Execution

Loaded by `migration-plan.md` Step 2.5 when `source_platform == "flyio"`. These constraints
mirror fly-to-aws's SKILL.md and govern every phase that migration-plan.md executes inline.
Apply them exactly as if fly-to-aws's own state machine were running.

## Design principles (always active)

- **Segment-specific urgency** — fly.io is not in Heroku-style sustaining mode; it is pivoting
  (agent sandboxes + Managed Postgres) with retrenchment at the edges. Three urgency tiers:
  GPU users (forced migration, hard sunset 2026-08-01), users in 17 deprecated regions,
  and generic PaaS users (strategic center-of-gravity shift, documented reliability incidents).
  State factually with citations, never exaggerate.
- **Config ≠ intent** — `fly launch` defaults to scale-to-zero (`auto_stop_machines="stop"`,
  `min_machines_running=0`). Discover records fly.toml values as signals; Clarify must confirm
  whether each routing-relevant semantic is a deliberate requirement or an inherited default.
- **Forbidden targets** — never recommend: AWS App Runner (closed to new customers 2026-04-30),
  Copilot CLI (EOL 2026-06-12), Elastic Beanstalk (existing plugin rule). Default generated
  deploy story for Fargate/ECS routes: ECR + ECS Express Mode + GitHub Actions (OIDC).
- **Re-platform by default** — select AWS services that match fly.io workload types (Fly Machines
  → Fargate, Fly Postgres/MPG → RDS/Aurora, Tigris → S3, Upstash Redis → ElastiCache).
- **Dev sizing unless specified** — default to development-tier capacity (db.t4g.micro, single AZ,
  0.5 vCPU Fargate). Only upgrade when the user explicitly requests it.
- **No human one-time migration costs** — do not present engineering labor or professional services
  as dollar estimates. Only vendor charges grounded in data are allowed.

## Context loading budget

Each phase should load no more than ~800 lines of instructions. Load conditional reference files
ONLY when their trigger condition is met — do not speculatively load all sub-files.

**Conditional files (load ONLY when condition is true):**

| File                                               | Condition                                                                          |
| -------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `design-refs/postgres-table.md`                    | Inventory contains `database` entries                                              |
| `design-refs/volumes-decision.md`                  | Inventory contains `[[mounts]]` volumes                                            |
| `design-refs/network-table.md`                     | Inventory has `[[services]]` non-http handlers, multi-region, 6PN/fly-replay flags |
| `references/phases/design/design-agent-handoff.md` | Any process group confirmed `agent_candidate`                                      |

All paths above are relative to `$ENGINE_BASE` (defined in migration-plan.md Step 1.5).

## Injection context assembly (Step 2 replacement)

Read ALL of: `$RUN_DIR/answers.json`, `$RUN_DIR/design.json`, `$RUN_DIR/pass2.json`, and
`$RUN_DIR/handoff-summary.md`. If `handoff-summary.md` does not exist (build_deploy path),
write it first by following `references/handoff/handoff-migration.md` Step 1, then return.

**`answers.json` is nested:** shape is `{"entry_point": "...", "answers": {...}}`.
Every answer key is read from the inner `answers` object.

Build the injection context per this table (never inject `unknown`):

| Advisor field                                          | fly-to-aws preference key                                                         | Effect                                                    |
| ------------------------------------------------------ | --------------------------------------------------------------------------------- | --------------------------------------------------------- |
| winning runtime (design.json)                          | `preferences.agent_groups.<group>.compute_target` + `decided_by: "agent-advisor"` | Routing layer G fires — layers 0–5 skipped for that group |
| `deployment_model`                                     | `preferences.agent_groups.<group>.deployment_model`                               | Carried into Generate                                     |
| session semantics (`session_duration`, `memory_needs`) | `preferences.agent_groups.<group>.session_profile`                                | Informs sizing + service notes; never re-asked            |

**Group mapping rule:** the advisor's scored workload maps to the fly.toml process group whose
code evidence matched — when ambiguous, ask the user which group the agent is.

**Precedence rule:** injected answers appear as pre-selected defaults (`chosen_by: "injected"`);
user override wins and flips `decided_by` to `"user"`.

Write the injection context to `$RUN_DIR/migration-plan-injection.json`:

```json
{
  "injected_preferences": {
    "agent_groups": {
      "<group>": {
        "compute_target": "<runtime>",
        "deployment_model": "<model>",
        "session_profile": {
          "session_duration": "<mapped>",
          "memory_needs": "<mapped>"
        },
        "decided_by": "agent-advisor"
      }
    }
  },
  "advisor_rationale": "<top 3 scoring signals from handoff-summary.md>",
  "repo": "<abs $REPO>",
  "migration_dir": "<abs $MIGRATION_DIR>"
}
```

## Share checkpoint handling

fly-to-aws offers an optional plan-share prompt after Estimate and after Generate (partner
matching only; it collects no feedback telemetry). Because this execution runs inside
agent-advisor's session, automatically choose "No thanks" at both checkpoints and continue.
Do NOT load `$ENGINE_BASE/references/phases/share/share.md`.

## Precedence and overrides

Injected answers appear as pre-selected defaults in fly-to-aws's Clarify. The user can override
any injected answer — when they do, flip `decided_by` to `"user"` in the output
`preferences.json` and treat the user's answer as authoritative.
