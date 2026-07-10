---
_phase: design
_title: "Design AWS Architecture"
_requires_phase: clarify
_input:
  - fly-resource-inventory.json
  - preferences.json
_fragments:
  - _id: agent-handoff
    _trigger: { _when: "a process group is class_confirmed 'agent' with advisor_requested true and decided_by null (embedded agent-advisor run needed)" }
    _file: phases/design/design-agent-handoff.md
_assemble:
  _file: phases/design/design-assemble.md
_produces:
  - aws-design.json
_advances_to: estimate
_re_entry_guard:
  _stale_if_completed: estimate
  _stale_artifact: estimation-infra.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: clarify
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [fly-resource-inventory.json, preferences.json]
    _on_failure: _unrecoverable
  - _validate_json: [fly-resource-inventory.json, preferences.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: aws-design.json
    _on_failure: _halt_and_inform
  - _validate_json: aws-design.json
    _on_failure: _halt_and_inform
  - _assert: "all root-level keys exist: compute, databases, storage, cache, network, secrets, specialist_gates, warnings (arrays may be empty)"
    _on_failure: _halt_and_inform
  - _assert: "for each process group in the inventory, a compute.<group> entry exists with target (matching the enum), layer_fired, decided_by (routing_table|agent-advisor|user), sizing, and notes[] all non-null"
    _on_failure: _halt_and_inform
  - _assert: "every database entry has target (and instance_class where applicable); every storage entry has recommendation; network.ingress is set; secrets.store is set"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
  - "k8s/**"
  - MIGRATION_GUIDE.md
  - estimation-infra.json
---

# Phase 3: Design AWS Architecture

**Phase 3 of 6** — Execute the compute routing table, map databases/storage/network, size resources, and produce the AWS architecture blueprint (`aws-design.json`).

> **HARD GATE — Design requires Clarify:** Do not execute this phase unless `$MIGRATION_DIR/.phase-status.json` records `phases.clarify` as `"completed"`. If Clarify is incomplete, load `references/phases/clarify/clarify.md` and complete Phase 2 first.

This phase translates inventory signals and user-confirmed preferences into concrete AWS service selections with audit trails. Every compute routing decision records which layer fired and how it was decided (routing_table, agent-advisor, or user override).

---

## Step 0: Load Inputs and Determine Conditional References

### Required Inputs

1. Read `$MIGRATION_DIR/fly-resource-inventory.json` (produced by Discover)
2. Read `$MIGRATION_DIR/preferences.json` (produced by Clarify)

### Load Core Design References

Load these reference files unconditionally:

1. `references/design-refs/compute-routing-table.md` (routing logic)
2. `references/design-refs/machine-preset-table.md` (sizing logic)

### Conditional Reference Loading

Scan the inventory to determine which additional references to load:

| Condition                                                                                                                                                                                                     | Load This File                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| `databases[]` array is non-empty                                                                                                                                                                              | `references/design-refs/postgres-table.md`   |
| `volumes[]` array is non-empty OR any `process_groups[].flags.stateful_mounts[]` is non-empty                                                                                                                 | `references/design-refs/volumes-decision.md` |
| `extensions[]` array is non-empty OR `object_storage[]` array is non-empty                                                                                                                                    | `references/design-refs/fast-path-table.md`  |
| `network_flags.fly_replay == true` OR `network_flags.sixpn_dynamic == true` OR `network_flags.multi_region[]` is non-empty OR any `services[].protocol == "udp"` OR any `services[].handlers == []` (raw TCP) | `references/design-refs/network-table.md`    |

Do NOT load files whose conditions are not met. This keeps context budget under ~800 lines.

---

## Step 1: Execute Compute Routing

For each process group in the inventory, execute the compute routing table (layers G → 5) to determine the AWS target. **First match wins.**

### Routing Algorithm

For each `process_groups[<group>]` entry in inventory:

#### Layer G (Guard) — Advisor-Decided Injection Check

Check if `preferences.json` contains `agent_groups.<group>.decided_by == "agent-advisor"`.

- **Match:** The group was routed via Direction-A injection or a prior embedded advisor run. Skip layers 0-5 entirely for this group. Build the compute entry from `agent_groups.<group>`:
  - `target`: Read from `compute_target` (the advisor runtime verbatim)
  - `layer_fired`: `"G"`
  - `decided_by`: `"agent-advisor"`
  - `sizing`: Derive from standard fly-to-aws sizing rules (machine-preset-table.md)
  - `advisor_ctx`: Build from injected fields:
    - `deployment_model`: Read from `agent_groups.<group>.deployment_model` (if present)
    - `session_profile`: Read from `agent_groups.<group>.session_profile` (if present)
  - `notes`: Include `"Runtime selected by agent-advisor (Direction-A injection)"` when `compute_target` came from injection
- **No match:** Continue to Layer 0.

#### Layer 0 — AI Agent Confirmation

Check if `preferences.json` contains `process_groups.<group>.class_confirmed == "agent"`.

- **Match:**
  1. Check `agent_groups.<group>.advisor_requested`:
     - If `true` AND `decided_by == null`: This group needs an embedded agent-advisor run. Load `references/phases/design/design-agent-handoff.md` and execute the handoff for this group. Consume the advisor's verdict as the compute target.
     - If `true` AND `decided_by == "agent-advisor"`: Verdict already exists (from Layer G or earlier). Use it.
     - If `false`: User declined advisor scoring. Note "agent-advisor scoring offered and declined" in the group's `notes[]`. Fall through to Layer 1.
  2. Record `decided_by: "agent-advisor"` (if advisor ran) or `decided_by: "routing_table"` (if declined).
- **No match:** Fall through to Layer 1.

#### Layer 1 — GPU

Check if `process_groups.<group>.flags.gpu == true`.

- **Match:**
  1. Read `preferences.json` → `process_groups.<group>.gpu_purpose`:
     - `"compute"` → Route to EC2 GPU instance via table in compute-routing-table.md (a10 → g5, l40s → g6e, a100-40gb → p4d, a100-80gb → p4de). Record `target: "ec2_gpu"`, `layer_fired: "1"`, `decided_by: "routing_table"`.
     - `"llm_inference"` → Route to Bedrock handoff. Record `target: "bedrock_handoff"`, `layer_fired: "1"`, `decided_by: "routing_table"`. Add note: "LLM inference use case — see llm-to-bedrock skill for model migration."
  2. Add urgency note: "GPU sunset 2026-08-01 — migration is urgent."
- **No match:** Fall through to Layer 2.

#### Layer 2 — One-Shot / Batch

Check if `process_groups.<group>.flags.one_shot == true`.

- **Match:**
  1. Read `preferences.json` → `process_groups.<group>.class_confirmed`:
     - If `"one_shot"` (user confirmed): Route to Lambda / AWS Batch / ECS scheduled task based on duration + trigger.
       - Default for v1: `target: "ecs_scheduled_task"`, `layer_fired: "2"`, `decided_by: "routing_table"`.
       - Add note: "One-shot workload — Lambda or AWS Batch may be alternatives based on runtime/duration."
     - If NOT `"one_shot"`: User corrected the signal — it's actually a long-running service. Fall through to Layer 3.
- **No match:** Fall through to Layer 3.

#### Layer 3 — Platform Preference (No Routing)

Read `preferences.json` → `platform_preference.eks_reuse`:

- `true` → Set routing flavor for layers 4-5 to EKS.
- `false` → Set routing flavor for layers 4-5 to Fargate.

**This layer does not route by itself.** It only determines the target flavor (EKS vs Fargate) for layers 4-5.

Continue to Layer 4.

#### Layer 4 — Always-On Service

Check if `process_groups.<group>.scaling.min_machines_running >= 1` OR `process_groups.<group>.scaling.auto_stop == "off"` (or null).

- **Match:**
  1. Read `preferences.json` → `process_groups.<group>.class_confirmed`:
     - If `"always_on"` (user confirmed hard requirement):
       - If Layer 3 flavor is EKS: `target: "eks"`, `layer_fired: "4"`, `decided_by: "routing_table"`.
       - If Layer 3 flavor is Fargate: `target: "fargate_min1"`, `layer_fired: "4"`, `decided_by: "routing_table"`.
       - Add note: "Always-on service — min 1 task/pod."
     - If NOT `"always_on"` (user said it's just default setup): Read `process_groups.<group>.scale_to_zero_intent`:
       - If `"inherited_default"`: Route to Layer 4 target (Fargate min-1) with note: "Scale-to-zero was inherited default, routing to always-on with idle-cost note."
       - Otherwise: Fall through to Layer 5.
- **No match:** Fall through to Layer 5.

#### Layer 5 — Scale-to-Zero Service

Check if `process_groups.<group>.scaling.min_machines_running == 0` AND `process_groups.<group>.scaling.auto_start == true`.

- **Match:**
  1. Read `preferences.json` → `process_groups.<group>.scale_to_zero_intent`:
     - If `"deliberate"` (user confirmed intentional):
       - Check if `process_groups.<group>.scaling.auto_stop == "suspend"`:
         - If yes, read `suspend_state_dependency`:
           - `"yes"` → `target: "lambda_microvms"`, `layer_fired: "5"`, `decided_by: "routing_table"`. Add note: "Suspend/resume parity with Lambda MicroVMs. Caveat: Fly does not guarantee snapshot persistence — verify app handles cold-start fallback."
           - `"no"` → Evaluate function model fit:
             - If HTTP service, stateless, likely <15 min runtime → `target: "lambda"`, `layer_fired: "5"`, `decided_by: "routing_table"`.
             - Otherwise → `target: "lambda_microvms"`, `layer_fired: "5"`, `decided_by: "routing_table"`.
         - If no (auto_stop is "stop" or null):
           - Evaluate function model fit:
             - If HTTP service, stateless, likely <15 min runtime → `target: "lambda"`, `layer_fired: "5"`, `decided_by: "routing_table"`.
             - If containerized/stateful → `target: "lambda_microvms"`, `layer_fired: "5"`, `decided_by: "routing_table"`.
             - If neither fits → `target: "fargate_min1"`, `layer_fired: "5"`, `decided_by: "routing_table"`. Add note: "Deliberate scale-to-zero but doesn't fit Lambda model — Fargate min-1 with idle-cost delta."
     - If `"inherited_default"`: Route to Fargate min-1 (Layer 4 route). Record `target: "fargate_min1"`, `layer_fired: "5"`, `decided_by: "routing_table"`. Add note: "Scale-to-zero was inherited default — routing to Fargate min-1 with idle-cost note."
- **No match:** Default fallback → If Layer 3 flavor is EKS, use `eks`; otherwise use `fargate_ecs_express`. Record `layer_fired: "5"`, `decided_by: "routing_table"`.

---

## Step 2: Size Compute Resources

For each routed compute target, apply sizing from `machine-preset-table.md`:

1. Read the Fly machine preset from `process_groups.<group>.vm.preset` (or custom sizing via `vm.cpus` / `vm.memory_mb`).
2. Look up the corresponding Fargate task size (vCPU / memory GB) in the machine preset table.
3. Record sizing in `compute.<group>.sizing`:

   ```json
   {
     "cpu": 0.25,
     "memory_gb": 0.5
   }
   ```

For targets that are not Fargate (e.g., `eks`, `lambda`, `ec2_gpu`):

- EKS: Use the same Fargate sizing as guidance for Kubernetes resource requests/limits.
- Lambda: Use memory_mb from Fly machine; Lambda CPU is proportional to memory (1769 MB = 1 vCPU).
- EC2 GPU: Map GPU preset from fly.toml to EC2 instance type (a10 → g5.xlarge, l40s → g6e.xlarge, a100-40gb → p4d.24xlarge, a100-80gb → p4de.24xlarge).

---

## Step 3: Map Databases

**Conditional:** Only execute if inventory `databases[]` array is non-empty.

For each database in `inventory.databases[]`:

1. Read `type` field (`"postgres"` or `"mysql"`).
2. Read `managed` field (`true` for Fly Managed Postgres/MPG, `false` for legacy).
3. If `managed == true`:
   - Look up the MPG plan (infer from `notes` field or default to "Launch" if unknown).
   - Map to RDS instance class using `postgres-table.md`.
   - Recommend RDS Multi-AZ + RDS Proxy (for PgBouncer parity).
   - Record in `databases[]`:

     ```json
     {
       "name": "myapp-postgres",
       "source_type": "fly_mpg",
       "target": "rds_postgres_multi_az",
       "instance_class": "db.m7g.large",
       "storage_gb": 100,
       "include_proxy": true,
       "notes": ["RDS Proxy for PgBouncer parity", "Multi-AZ for durability"]
     }
     ```

4. If `managed == false`:
   - Recommend RDS as managedness upgrade.
   - Default to smallest instance (db.t4g.micro for dev sizing).
   - Record in `databases[]` with note: "Legacy Fly Postgres — RDS migration recommended for managedness upgrade."

---

## Step 4: Map Storage (Volumes)

**Conditional:** Only execute if inventory `volumes[]` array is non-empty OR any `process_groups[].flags.stateful_mounts[]` is non-empty.

For each volume:

1. Load `volumes-decision.md`.
2. Apply the decision tree (de-volume → EFS → ECS-on-EC2+EBS).
3. Default recommendation: **de-volume** (migrate SQLite/embedded DBs to RDS, file blobs to S3).
4. Record in `storage[]`:

   ```json
   {
     "name": "data_volume",
     "source_size_gb": 10,
     "recommendation": "de-volume",
     "alternatives": ["efs", "ecs_on_ec2_ebs"],
     "notes": ["Migrate structured data to RDS, file blobs to S3 — durability upgrade"]
   }
   ```

If the usage pattern is unclear, mark as deferred:

```json
{
  "recommendation": "specialist_engagement",
  "notes": ["Volume usage pattern unclear — deferring to specialist review"]
}
```

---

## Step 5: Map Extensions

**Conditional:** Only execute if inventory `extensions[]` array is non-empty.

For each extension:

1. Load `fast-path-table.md` (if not already loaded for object storage).
2. Look up the extension by name/provider in the fast-path table.
3. If matched:
   - Record the AWS target and migration difficulty in the appropriate output array (`cache[]` for Redis/vector stores, `databases[]` for MySQL, etc.).
   - Example for Upstash Redis → `cache[]`:

     ```json
     {
       "name": "upstash-redis",
       "source_type": "upstash_redis",
       "target": "elasticache_serverless",
       "notes": [
         "VPC-only",
         "HTTP/REST client must switch to a Redis-protocol client — flagged rewrite"
       ]
     }
     ```

   - (Tigris object storage is mapped separately in Step 5.5 below — it comes from inventory `object_storage[]`, not `extensions[]`.)
4. If NOT matched in the table:
   - Record as specialist gate:

     ```json
     {
       "name": "unknown-extension",
       "target": "specialist_engagement",
       "notes": ["Extension not in fast-path table — deferring to specialist review"]
     }
     ```

Add all specialist-gated extensions to `specialist_gates[]` at root level.

---

## Step 5.5: Map Object Storage

**Conditional:** Only execute if inventory `object_storage[]` array is non-empty.

For each object storage entry in `inventory.object_storage[]`:

1. Load `fast-path-table.md` (if not already loaded in Step 5).
2. For each Tigris bucket (`provider == "tigris"`), look up the Tigris → S3 row in the fast-path table.
3. Write a `storage[]` entry. The `recommendation` field MUST contain the substring `"s3"` — this exact key is what Generate's `has_s3` detection (`generate-docs.md`) and Estimate's S3 cost row read to emit `migrate-s3.sh` and the S3 cost line:

   ```json
   {
     "name": "myapp-assets",
     "source_provider": "tigris",
     "source_size_gb": 0,
     "recommendation": "s3",
     "notes": [
       "Endpoint/credential swap + aws s3 sync",
       "Region auto → real region (us-east-1 default)",
       "+CloudFront if edge reads mattered",
       "Egress cost-shape change $0.09/GB flagged"
     ]
   }
   ```

   - Carry the `+CloudFront-if-edge-reads` and egress cost-shape notes from the fast-path table Tigris row into the entry `notes[]`.
   - Add "Tigris egress cost-shape change: $0.09/GB flagged" to root-level `warnings[]`.

---

## Step 6: Map Network

**Conditional:** Only execute if any of these conditions are true:

- `network_flags.fly_replay == true`
- `network_flags.sixpn_dynamic == true`
- `network_flags.multi_region[]` is non-empty
- Any `services[].protocol == "udp"`
- Any `services[].handlers == []` (raw TCP)

If conditional load triggered, load `network-table.md` and apply mappings:

1. **Ingress pattern:**
   - Single-region default: `"single_region_cloudfront"` (ALB + CloudFront).
   - Multi-region active-active: Add to `decision_records[]` and `specialist_gates[]` — v1 generation boundary.

2. **Non-HTTP services:**
   - UDP → NLB UDP listener. Record `nlb_needed: true`.
   - Raw TCP → NLB TCP passthrough. Record `nlb_needed: true`.
   - TLS handler → NLB TLS listener or ALB. Record in notes.

3. **Fly-replay detection:**
   - If `network_flags.fly_replay == true`:
     - Add to `network.decision_records[]`:

       ```json
       {
         "pattern": "fly-replay",
         "aws_equivalent": "none",
         "options": [
           "app-level proxy",
           "ALB + Lambda@Edge",
           "CloudFront Functions",
           "Aurora Global DB write forwarding"
         ],
         "effort": "high"
       }
       ```

     - Add to `specialist_gates[]`.

4. **Dynamic 6PN discovery:**
   - If `network_flags.sixpn_dynamic == true`:
     - Add to `network.decision_records[]`:

       ```json
       {
         "pattern": "dynamic_6pn_discovery",
         "aws_equivalent": "none",
         "notes": ["Code rewrite required — no AWS Load Balancer equivalent"],
         "effort": "high"
       }
       ```

     - Add to `specialist_gates[]`.

5. **Multi-region active-active:**
   - If `network_flags.multi_region[]` is non-empty:
     - Add to `network.decision_records[]`:

       ```json
       {
         "pattern": "multi_region_active_active",
         "options": ["Global Accelerator + per-region ALBs", "Route53 latency-based routing"],
         "effort": "medium"
       }
       ```

     - Add to `specialist_gates[]` with note: "v1 generation boundary — design only, no Terraform generation."

Record network configuration in `network` object at root level:

```json
{
  "ingress": "single_region_cloudfront",
  "nlb_needed": false,
  "decision_records": []
}
```

---

## Step 7: Map Secrets

All Fly apps use secrets. Default target: **SSM Parameter Store** (standard tier = $0 cost).

Record in `secrets` object:

```json
{
  "store": "ssm_parameter_store",
  "count": 12,
  "notes": ["Fly secret values cannot be exported — re-provision from source systems"]
}
```

If the inventory shows >100 secrets, consider flagging AWS Secrets Manager as an alternative (note the $0.40/secret/month cost).

---

## Step 8: Assemble aws-design.json

Combine all routing results, sizing, database mappings, storage recommendations, extension mappings, network configuration, and secrets into the final design artifact.

### Schema

```json
{
  "migration_id": "0709-1430",
  "skill": "fly-to-aws",
  "metadata": {
    "timestamp": "2026-07-09T14:30:00Z",
    "design_version": "1.0"
  },
  "compute": {
    "web": {
      "target": "fargate_ecs_express",
      "layer_fired": "4",
      "decided_by": "routing_table",
      "sizing": {
        "cpu": 0.25,
        "memory_gb": 0.5
      },
      "notes": ["Always-on service — min 1 task"]
    },
    "worker": {
      "target": "lambda",
      "layer_fired": "5",
      "decided_by": "routing_table",
      "sizing": {
        "memory_mb": 512
      },
      "notes": ["Scale-to-zero with Lambda — fits function model"]
    }
  },
  "databases": [
    {
      "name": "myapp-postgres",
      "source_type": "fly_mpg",
      "target": "rds_postgres_multi_az",
      "instance_class": "db.m7g.large",
      "storage_gb": 100,
      "include_proxy": true,
      "notes": ["RDS Proxy for PgBouncer parity", "Multi-AZ for durability"]
    }
  ],
  "storage": [
    {
      "name": "data_volume",
      "source_size_gb": 10,
      "recommendation": "de-volume",
      "alternatives": ["efs", "ecs_on_ec2_ebs"],
      "notes": ["Migrate structured data to RDS, file blobs to S3"]
    }
  ],
  "cache": [],
  "network": {
    "ingress": "single_region_cloudfront",
    "nlb_needed": false,
    "decision_records": []
  },
  "secrets": {
    "store": "ssm_parameter_store",
    "count": 12,
    "notes": ["Fly secret values cannot be exported — re-provision from source systems"]
  },
  "specialist_gates": [],
  "warnings": []
}
```

### Validation Rules

1. Every `compute.<group>` entry MUST have:
   - `target` (one of the enum values from the task brief)
   - `layer_fired` (string: "G", "0", "1", "2", "4", or "5")
   - `decided_by` (one of: `"routing_table"`, `"agent-advisor"`, `"user"`)
   - `sizing` object (fields vary by target type)
   - `notes[]` array (may be empty)

2. All arrays (`databases`, `storage`, `cache`, `network.decision_records`, `specialist_gates`, `warnings`) MUST exist (may be empty).

3. Valid `target` enum values:
   - `fargate_ecs_express`
   - `eks`
   - `lambda`
   - `lambda_microvms`
   - `fargate_min1`
   - `ec2_gpu`
   - `sagemaker_endpoint`
   - `bedrock_handoff`
   - `batch`
   - `ecs_scheduled_task`
   - `agentcore`
   - Plus any advisor verdicts verbatim (e.g., `agentcore_ruby`, `lambda_snapstart`, etc.)

4. No null values for required fields.

Write `$MIGRATION_DIR/aws-design.json`.

---

## Step 9: Present Design Summary

After writing `aws-design.json`, present a summary table to the user:

```
─── AWS Architecture Design ───

Compute:
• web → Fargate ECS Express (0.25 vCPU / 0.5 GB)
  Layer 4 (always-on service)
• worker → Lambda (512 MB)
  Layer 5 (scale-to-zero — fits function model)

Databases:
• myapp-postgres → RDS PostgreSQL Multi-AZ (db.m7g.large + RDS Proxy)

Storage:
• data_volume (10 GB) → Recommendation: de-volume (migrate to RDS + S3)

Network:
• Ingress: CloudFront + ALB (single-region default)

Secrets:
• 12 secrets → SSM Parameter Store (standard tier, $0 cost)
  ⚠️ Fly secret values cannot be exported — re-provision from source

Specialist Gates: [count or "None"]

Design complete. Ready for cost estimation.
```

If `specialist_gates[]` is non-empty, list each gate with its reason and effort level.

---

## Completion Handoff Gate (Fail Closed)

**Re-entry guard:** If `estimation-infra.json` exists and `phases.estimate` is `"completed"`: STOP unless the user explicitly confirms re-running Design. Emit `GATE_FAIL | phase=design | field=estimation-infra.json | reason=stale_downstream`.

**Checks (all must PASS):**

1. `aws-design.json` exists and parses as valid JSON.
2. All root-level keys exist: `compute`, `databases`, `storage`, `cache`, `network`, `secrets`, `specialist_gates`, `warnings`.
3. For each process group in inventory → `compute.<group>` entry exists.
4. For each `compute.<group>` entry:
   - `target` is non-null and matches the enum.
   - `layer_fired` is non-null.
   - `decided_by` is non-null and one of: `"routing_table"`, `"agent-advisor"`, `"user"`.
   - `sizing` is non-null.
   - `notes` is an array (may be empty).
5. All database entries have `target` and `instance_class` (if applicable).
6. All storage entries have `recommendation`.
7. `network.ingress` is set.
8. `secrets.store` is set.

**On any FAIL:** Emit `GATE_FAIL | phase=design | field=<path> | reason=missing`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user to re-run Design.

**On PASS:** Emit `HANDOFF_OK | phase=design | artifacts=aws-design.json`.

---

## Step 10: Update Phase Status

Only after `HANDOFF_OK`. In the **same turn** as the summary output, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json`:

- Set `phases.design` to `"completed"`
- Set `current_phase` to `"estimate"`
- Update `last_updated` to current ISO timestamp

Output to user: "Design complete. Proceeding to Phase 4: Cost Estimation."

---

## Scope Boundary

**This phase covers AWS service selection and sizing ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Cost calculations (that's Estimate)
- Terraform or Kubernetes manifest generation (that's Generate)
- Migration timelines or execution plans (that's Generate)
- Detailed code migration examples (that's Generate)
- Database migration scripts (that's Generate)
- CI/CD workflows (that's Generate)

**Your ONLY job: Design the AWS architecture. Record the decisions. Nothing else.**
