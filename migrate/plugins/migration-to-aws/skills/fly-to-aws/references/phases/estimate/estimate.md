---
_phase: estimate
_title: "Estimate AWS Costs"
_requires_phase: design
_input:
  - aws-design.json
  - preferences.json
  - fly-resource-inventory.json
_assemble:
  _file: phases/estimate/estimate-assemble.md
_produces:
  - estimation-infra.json
_advances_to: generate
_re_entry_guard:
  _stale_if_completed: generate
  _stale_artifact: MIGRATION_GUIDE.md
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: design
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [aws-design.json, preferences.json, fly-resource-inventory.json]
    _on_failure: _unrecoverable
  - _validate_json: [aws-design.json, preferences.json]
    _on_failure: _unrecoverable
  - _assert: "aws-design.json compute object exists and is non-empty, and every entry has target, layer_fired, decided_by, sizing, notes"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: estimation-infra.json
    _on_failure: _halt_and_inform
  - _validate_json: estimation-infra.json
    _on_failure: _halt_and_inform
  - _assert: "recommendation.path is one of {migrate_optimized, migrate_phased, stay} and recommendation.path_label is a non-empty string"
    _on_failure: _halt_and_inform
  - _assert: "recommendation.migrate_if and recommendation.stay_if are non-empty arrays"
    _on_failure: _halt_and_inform
  - _assert: "projected_costs.aws_monthly_balanced is a positive number"
    _on_failure: _halt_and_inform
  - _assert: "every compute group in aws-design.json appears in the cost breakdown, or is listed as 'unpriced' in warnings"
    _on_failure: _halt_and_inform
  - _assert: "the balanced total equals the arithmetic sum of the per-service costs, excluding unpriced (Property-16 invariant)"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
  - "k8s/**"
  - MIGRATION_GUIDE.md
---

# Phase 4: Estimate AWS Costs

> Loaded by SKILL.md when `phases.design == "completed"` AND `phases.estimate != "completed"`.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Overview

Calculate projected monthly AWS costs for the designed fly.io-to-AWS architecture. Produce `estimation-infra.json` conforming to `$GCP_SHARED/schema-estimate-infra.md`.

**Inputs:**

- `$MIGRATION_DIR/aws-design.json` (from Phase 3)
- `$MIGRATION_DIR/preferences.json` (from Phase 2)
- `$MIGRATION_DIR/fly-resource-inventory.json` (from Phase 1)

**Outputs:**

- `$MIGRATION_DIR/estimation-infra.json`
- `.phase-status.json` updated (estimate → completed)

**Shared paths:**

- `$GCP_SHARED = ${CLAUDE_PLUGIN_ROOT}/skills/gcp-to-aws/references/shared`

---

## Step 0: Pricing Mode Selection

### Step 0a: Load Pricing Cache

Read `$GCP_SHARED/pricing-cache.md`. Check the `Last updated` date in the header:

- If ≤ 30 days old: **Cached prices are the primary source.** No MCP calls needed for services listed in the cache. Set `pricing_source: "cached"`.
- If > 30 days old: Cache is stale. Infrastructure prices (Fargate, RDS, S3, etc.) remain reliable. Attempt MCP (Step 0b) for services not in cache; use stale cache as fallback with `pricing_source: "cached_fallback"` (the schema enum value for a present-but-stale cache used as fallback).

### Step 0b: MCP Availability Check (only if cache stale or service not listed)

Attempt to reach awspricing MCP with **up to 3 attempts** (10-second timeout per attempt):

1. **Attempt 1**: Call `get_pricing_service_codes()`
2. **If timeout/error after 10s**: Wait 1 second, retry (Attempt 2)
3. **If still fails after 10s**: Wait 2 seconds, retry (Attempt 3)
4. **If all 3 attempts fail**: Use cached prices. Set `pricing_source: "cached_fallback"`.

### Step 0c: Display Pricing Mode to User

**Before any calculation**, surface the pricing status:

- **Cache fresh + all services covered**: "Pricing source: cached (updated [date], ±5-10% accuracy). Live pricing API not required."
- **Cache stale + MCP available**: "Pricing source: live API (awspricing MCP). Cache is stale ([date]) — using real-time pricing."
- **Cache stale + MCP unavailable**: "⚠️ Pricing source: stale cache only (updated [date]). The awspricing MCP server is unreachable. Proceeding with cached pricing; accuracy ±5-10% for infrastructure."
- **Service not in cache + MCP unavailable**: "⚠️ Some services not in pricing cache and MCP unreachable. Those services will show `pricing_source: unavailable` in the estimate."

### Pricing Hierarchy (per-service lookup order)

| Priority | Source                         | Condition                                     | `pricing_source` value |
| -------- | ------------------------------ | --------------------------------------------- | ---------------------- |
| 1        | `$GCP_SHARED/pricing-cache.md` | Service found in cache                        | `"cached"`             |
| 2        | MCP API (`get_pricing`)        | Service NOT in cache, MCP available           | `"live"`               |
| 3        | Cache after MCP failure        | MCP attempted but failed, service IS in cache | `"cached_fallback"`    |
| 4        | Unavailable                    | NOT in cache AND MCP failed                   | `"unavailable"`        |

For typical fly.io migrations (Fargate, RDS, Aurora, ElastiCache, ALB, S3, CloudWatch, Secrets Manager), ALL prices are in `pricing-cache.md`. Zero MCP calls needed.

---

## Step 1: Prerequisites

1. Read `$MIGRATION_DIR/.phase-status.json`. If `phases.design` is not exactly `"completed"`: **STOP**. Output: "Phase 3 (Design) not completed. Run Phase 3 first."
2. Read `$MIGRATION_DIR/aws-design.json`. If missing or invalid JSON: **STOP**. Output: "Design artifact missing or corrupted. Re-run Phase 3."
3. Read `$MIGRATION_DIR/preferences.json`. If missing: **STOP**. Output: "Preferences file missing. Re-run Phase 2."
4. Read `$MIGRATION_DIR/fly-resource-inventory.json`. Extract compute and database entries.

### Validate Design

- `compute` object must exist and not be empty. If empty: **STOP**. Output: "No compute targets in design. Re-run Phase 3."
- Each compute entry must have `target`, `layer_fired`, `decided_by`, `sizing`, and `notes` fields. If missing: **STOP**. Output: "Compute group [group_name] missing required fields. Re-run Phase 3."
- At least one database, storage, cache, or compute entry must exist (no empty migrations).

If all validations pass, proceed to Part 1.

---

## Part 1: Determine Current fly.io Costs

Use the best available source for fly.io monthly baseline (first match wins):

1. **User-provided baseline** — Ask: "What is your current monthly fly.io spend? (Provide an estimate or 'unknown' if not available.)" Use the answer.
   - Set `current_costs.source: "user_provided"`
   - Set `current_costs.accuracy: "±20%"` (user estimates are less precise)

2. **Live Fly pricing fetch** — If the user declines or says unknown, fetch current Fly machine rates rather than trusting the static table first. WebFetch `https://fly.io/docs/about/pricing/`, asking for the **monthly rate of each discovered `vm.preset`, for the app's `primary_region`** (from `fly-resource-inventory.json`).
   - **Specify the region explicitly** — the pricing page is region-tabbed and returns multiple values per preset (e.g. shared-cpu-1x is ~$1.94 iad / ~$2.02 ams / ~$3.14 higher-cost regions). An unspecified region yields ambiguous results and may mis-price. If the inventory's `primary_region` is missing, null, empty, or `"unknown"`, fetch the `iad` (US East) figures and note the assumption.
   - For each process group, multiply the fetched monthly rate × machine count (from flyctl exports in `fly-resource-inventory.json.actuals` if present, else declared count). Sum all groups to get `fly_monthly_estimated`.
   - On success (ALL discovered presets found in the fetched page): set `current_costs.source: "pricing_fetched"`, `current_costs.accuracy: "±10%"`, and record `current_costs.fly_rate_source: {"url": "https://fly.io/docs/about/pricing/", "fetched_date": "<today>", "region": "<region used>"}`.
   - **Partial fetch (some presets fetched, some fell back to the tier-3 static table)** — do NOT hide the static values under `pricing_fetched`: set `current_costs.source: "pricing_mixed"`, `current_costs.accuracy: "±25%"` (the weaker of the two), still record `fly_rate_source`, and emit: "⚠️ Some Fly presets were priced from the live page, others from static anchors (preset(s) not found on the pricing page): [list]. Comparison accuracy ±25%." A single missing preset falls through to tier 3 for that preset only; it never fails the whole estimate.

3. **Fly machine preset estimates (fallback)** — If the live fetch fails (timeout, page moved, no readable figure), fall back to the static anchors in `references/design-refs/machine-preset-table.md`:
   - For each process group in inventory, look up its `vm.preset` in the table
   - Multiply monthly anchor by number of machines; sum all groups to get `fly_monthly_estimated`
   - Set `current_costs.source: "pricing_estimate"`
   - Set `current_costs.accuracy: "±25%"` (no billing data, static anchors)
   - **Never silent** — emit: "⚠️ Live Fly pricing fetch failed — using static anchors from the machine-preset table (2026-07-09), ±25%. Verify current rates at fly.io/docs/about/pricing before relying on the comparison."
   - If preset not found in table, mark as `"unpriced_fly"` and exclude from total; add to warnings

4. **Unavailable** — If no baseline available: present AWS costs without fly.io comparison.
   - Set `current_costs.source: "unavailable"`
   - Note: "Fly.io baseline unavailable — AWS costs shown without comparison."

When any baseline is available, present the fly.io baseline as:

- Total monthly cost
- Per-app breakdown (compute, database, volumes, extensions)

---

## Part 2: Calculate Projected AWS Costs

For each service in `aws-design.json`, calculate monthly cost using rates from `$GCP_SHARED/pricing-cache.md`. Track `pricing_source` per service.

### Per-Service Calculation Formulas

| AWS Service                | Formula                                                              | Key inputs from `aws-design.json`                             |
| -------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Fargate**                | (cpu/1024 × $0.04048 + memory_gb × $0.004445) × 730 hrs × count      | `compute.<group>.sizing.cpu`, `.memory_gb`                    |
| **Lambda**                 | $0.0000002/request + $0.0000166667/GB-sec                            | `compute.<group>.sizing.memory_mb`, request estimate          |
| **Lambda MicroVMs**        | Per-second: $0.0000166667/GB-sec + snapshot storage $0.08/GB-mo      | `compute.<group>.sizing.memory_mb`, snapshot storage estimate |
| **EKS**                    | $73/month cluster + node costs (EC2 or Fargate)                      | `compute.<group>` routed to eks                               |
| **Batch**                  | Fargate pricing (per job) or EC2 spot pricing                        | `compute.<group>.sizing` for Batch jobs                       |
| **ECS Scheduled Task**     | Fargate pricing per run                                              | `compute.<group>.sizing` for scheduled tasks                  |
| **ALB**                    | $16.43/month fixed + LCU estimate ($0.008/LCU-hr × 730)              | Per web service with `services[].handlers = ["http"]`         |
| **RDS PostgreSQL**         | instance_rate × 730 hrs + storage_gb × $0.23/GB-month                | `databases[].instance_class`, `.storage_gb`, `.multi_az`      |
| **Aurora PostgreSQL**      | instance_rate × 730 hrs + storage_gb × $0.10/GB-month + I/O estimate | `databases[].instance_class`, `.storage_gb`                   |
| **Aurora Serverless v2**   | $0.12/ACU-hr × min_acu × 730 + storage_gb × $0.10/GB-month           | `databases[].min_acu`, `.storage_gb`                          |
| **RDS Proxy**              | $0.015/vCPU-hr × 730 hrs × vCPUs                                     | When `databases[].include_proxy == true`                      |
| **ElastiCache Redis**      | node_rate × 730 hrs (× 2 if Multi-AZ)                                | `cache[].node_type`, Multi-AZ config                          |
| **ElastiCache Serverless** | $0.125/GB-hr × data_gb + $0.0034/ECPU-hr × ecpu estimate             | `cache[]` routed to serverless                                |
| **CloudWatch Logs**        | log_volume_gb × $0.50/GB + storage × $0.03/GB-month                  | `retention_days`, estimated log volume                        |
| **S3**                     | storage_gb × $0.023/GB-month + request estimates                     | `storage[]` from Tigris mapping                               |
| **Secrets Manager**        | secret_count × $0.40/month + API calls × $0.05/10K                   | `secrets.count` from inventory                                |
| **SSM Parameter Store**    | Standard tier: $0 (free)                                             | `secrets.store = "ssm_parameter_store"`                       |

### Fly-specific cost line items

**MANDATORY for scale-to-zero groups routed to Fargate min-1:**

Add an explicit idle-cost delta row:

```json
{
  "service": "Scale-to-zero idle cost delta (web group)",
  "fly_idle_monthly": "~$0 (suspended when idle)",
  "aws_idle_monthly": "$X (min 1 task always-on)",
  "delta": "+$X/month",
  "note": "Fly.io auto_stop=suspend allowed near-zero idle cost. AWS Fargate min-1 runs continuously."
}
```

**MANDATORY for Lambda MicroVMs routes:**

Include per-second billing + snapshot storage:

```json
{
  "service": "Lambda MicroVMs (worker group)",
  "compute_monthly": "$Y (per-second billing)",
  "snapshot_storage_monthly": "$Z (snapshot storage $0.08/GB-mo)",
  "total_monthly": "$Y+Z",
  "note": "Suspend/resume parity via Lambda SnapStart-like lifecycle hooks."
}
```

### Unpriced Resource Handling

IF pricing data for a service is unavailable from both MCP and cache:

1. Mark the resource's cost as `"unpriced"` in the per-service breakdown
2. **Exclude** from the total monthly cost sum
3. Add to `warnings[]`: "Pricing unavailable for [service_id]. Requires manual cost verification."
4. Add service name to `pricing_source.services_with_missing_fallback[]`

### Cost Tier Calculation

Calculate 3 cost tiers to show the optimization range:

| Tier          | Description              | Adjustments                                                                                       |
| ------------- | ------------------------ | ------------------------------------------------------------------------------------------------- |
| **Premium**   | Highest resilience       | Multi-AZ everything, latest-gen instances, no Spot, enhanced monitoring                           |
| **Balanced**  | Standard setup (default) | On-demand pricing, Multi-AZ where configured, standard monitoring                                 |
| **Optimized** | Cost-minimized           | Reserved pricing assumption (20-40% discount), Fargate Spot where applicable, S3-IA for cold data |

**Balanced** is the primary comparison tier. Generated Terraform (Phase 5) aligns with **Balanced**.

### Total Cost Calculation

```
total_monthly = sum(individual_resource_costs) — excluding "unpriced" resources
```

Verify: total equals the arithmetic sum of all individually calculated resource costs. This is the **Property 16** invariant.

---

## Part 2B: Observability Cost Estimation (CloudWatch)

Fly.io includes basic logging via Logdrain (free tier). AWS CloudWatch charges from the first GB. This section ensures observability costs are not a surprise.

### Step 1: Estimate Log Volume

Use per-service heuristic:

| AWS Service (from aws-design.json) | Estimated log volume/month | Basis                   |
| ---------------------------------- | -------------------------- | ----------------------- |
| Fargate task                       | 3 GB per task              | Container stdout/stderr |
| RDS/Aurora instance                | 1 GB per instance          | Error log + slow query  |
| ALB                                | 2 GB per load balancer     | Access logs             |
| ElastiCache                        | 0.5 GB per node            | Slow log                |

Sum all applicable services.

### Step 2: Estimate Custom Metrics and Alarms

- `custom_metrics_count = (number of compute groups + databases × 5)`
- Default floor: 10 custom metrics
- `alarm_count = max(5, (compute_groups + databases) × 2)` (baseline health/error/latency)

### Step 3: Calculate CloudWatch Costs

```
log_ingestion_cost    = monthly_log_gb × $0.50
log_storage_cost      = monthly_log_gb × $0.03 × retention_months (use preferences.operational.log_retention_days / 30, default: 1)
custom_metrics_cost   = custom_metrics_count × $0.30
alarms_cost           = alarm_count × $0.10
tracing_cost          = 0 (do not add X-Ray costs unless tracing detected in source)

total_observability   = log_ingestion_cost + log_storage_cost + custom_metrics_cost + alarms_cost + tracing_cost
```

### Step 4: Add Observability Entry

Add to `projected_costs.breakdown`:

```json
{
  "service": "CloudWatch + X-Ray (Observability)",
  "low": "<total × 0.7>",
  "mid": "<total>",
  "high": "<total × 1.5>",
  "accuracy": "±30%",
  "pricing_source": "cached",
  "components": {
    "log_ingestion": "<log_ingestion_cost>",
    "log_storage": "<log_storage_cost>",
    "custom_metrics": "<custom_metrics_cost>",
    "alarms": "<alarms_cost>",
    "tracing": "<tracing_cost>"
  },
  "volume_source": "heuristic",
  "note": "Fly.io includes basic Logdrain at no extra charge. CloudWatch charges from the first GB. Actual costs depend on log verbosity and retention."
}
```

This entry REPLACES any CloudWatch entries in a "Supporting" row — never double-count.

---

## Part 3: Cost Comparison (fly.io vs AWS)

### When Baseline Data Available

Present a side-by-side comparison:

- **Fly.io current monthly total** (from Part 1)
- **AWS Premium / Balanced / Optimized monthly totals**
- **Difference** (savings or increase) per tier vs fly.io — monthly and annual

Include in `estimation-infra.json`:

```json
"cost_comparison": {
  "fly_monthly_baseline": "<from Part 1>",
  "option_a_premium": {
    "aws_monthly": "<premium total>",
    "monthly_difference": "<premium - fly>",
    "annual_difference": "<(premium - fly) × 12>",
    "percent_change": "<+/-X%>"
  },
  "option_b_balanced": {
    "aws_monthly": "<balanced total>",
    "monthly_difference": "<balanced - fly>",
    "annual_difference": "<(balanced - fly) × 12>",
    "percent_change": "<+/-X%>"
  },
  "option_c_optimized": {
    "aws_monthly": "<optimized total>",
    "monthly_difference": "<optimized - fly>",
    "annual_difference": "<(optimized - fly) × 12>",
    "percent_change": "<+/-X%>"
  }
}
```

### When Baseline Data NOT Available

Omit `cost_comparison` section or set `fly_monthly_baseline` to null. Present AWS costs without comparison. State: "Fly.io billing data not available — showing projected AWS costs only. Provide billing estimates to see side-by-side comparison."

---

## Part 4: Migration Cost Considerations

Fly.io does not charge egress fees for data transfer during migration (unlike GCP). However, there may be time-based costs during parallel operation.

### IF baseline data IS available:

```json
"migration_cost_considerations": {
  "billing_data_available": true,
  "categories": [
    "Fly.io platform fees during parallel operation (both fly.io and AWS running simultaneously during cutover window)"
  ],
  "note": "Fly.io charges are usage-based. During migration, both fly.io and AWS costs apply until fly.io machines are destroyed. No data transfer egress fees from fly.io."
}
```

### IF baseline data is NOT available:

```json
"migration_cost_considerations": {
  "billing_data_available": false,
  "categories": [],
  "note": "Parallel operation costs depend on fly.io billing. Provide billing estimates for dual-run cost projections."
}
```

---

## Part 5: ROI Analysis

Present monthly and annual cost difference between fly.io baseline and each AWS tier.

- If AWS is cheaper: present monthly and annual savings per tier
- If AWS is more expensive: state clearly and justify with operational benefits

**Operational efficiency factors (qualitative — do not assign dollar values):**

- Full infrastructure control (VPC, security groups, IAM policies)
- Auto-scaling granularity (Fargate service scaling, Aurora auto-scaling)
- Broader AWS service integration (Step Functions, EventBridge, SNS/SQS)
- Cost optimization levers unavailable on fly.io (Spot, Savings Plans, Reserved Instances)
- Reduced vendor lock-in risk

**Non-cost benefits:**

- Global infrastructure (25+ AWS regions vs fly.io's limited regions)
- Compliance certifications (SOC2, HIPAA, PCI, FedRAMP) built into AWS services
- Enterprise integration (Direct Connect, Transit Gateway, Organizations)
- Service breadth (200+ AWS services for future workloads)
- Scaling flexibility (auto-scaling, reserved capacity, burst pricing)

```json
"roi_analysis": {
  "recurring_savings": {
    "monthly_difference_balanced": "<negative = AWS cheaper>",
    "monthly_difference_optimized": "<negative = AWS cheaper>",
    "annual_difference_balanced": "<× 12>",
    "annual_difference_optimized": "<× 12>",
    "note": "Negative = AWS cheaper. Positive = fly.io cheaper on pure cost basis."
  },
  "operational_efficiency_factors": [...],
  "non_cost_benefits": [...],
  "note": "Fly.io parallel-operation fees during migration window are excluded from recurring ROI calculations."
}
```

---

## Part 6: Cost Optimization Opportunities

Present applicable optimizations with estimated savings. These are **incremental post-migration actions** beyond the Balanced on-demand baseline.

| Optimization           | Savings Range                               | Applies To                       | When                                           |
| ---------------------- | ------------------------------------------- | -------------------------------- | ---------------------------------------------- |
| Compute Savings Plans  | 20-66%                                      | Fargate, Lambda                  | Post-migration (after 30-90 day baseline)      |
| Database Savings Plans | Up to 35% (serverless) / ~20% (provisioned) | Aurora, RDS, ElastiCache         | Post-migration or after right-sizing           |
| RDS Reserved Instances | Up to 69%                                   | RDS, Aurora (provisioned)        | Post-migration (after architecture stabilizes) |
| S3 Intelligent-Tiering | 38-50%                                      | S3 storage                       | During migration                               |
| Fargate Spot           | 60-70%                                      | Non-critical/batch Fargate tasks | If worker processes exist                      |

**Emit in `optimization_opportunities[]`:**

### Compute Savings Plans (when Fargate/Lambda in design)

```json
{
  "opportunity": "Compute Savings Plans",
  "type": "compute_savings_plan",
  "target_services": ["Fargate", "Lambda"],
  "savings_percent": "20-66%",
  "savings_monthly": null,
  "commitment": "1-year or 3-year",
  "timing": "post-migration (after 30-90 days of usage data)",
  "implementation_effort": "low",
  "prerequisite": "Establish AWS compute usage baseline before committing",
  "description": "Fly.io billing is per-machine-second. Fargate/Lambda usage patterns may differ — establish AWS baseline before Savings Plan commitment. Use Cost Explorer recommendations after 30+ days.",
  "references": [
    "https://aws.amazon.com/savingsplans/compute-pricing/",
    "https://aws.amazon.com/savingsplans/faqs/"
  ]
}
```

### Database Savings Plans (when RDS/Aurora in design, projected > $50/month)

```json
{
  "opportunity": "Database Savings Plans",
  "type": "database_savings_plan",
  "target_services": ["RDS", "Aurora"],
  "savings_percent": "up to 35% (serverless) / up to 20% (provisioned)",
  "savings_monthly": "<calculated or null if < $50/mo>",
  "commitment": "1-year no-upfront",
  "timing": "immediately post-migration or after instance right-sizing",
  "implementation_effort": "low",
  "prerequisite": "Confirm target instance class; omit savings_monthly when DB on-demand < $50/month",
  "description": "Fly Managed Postgres runs 24/7 with predictable usage. Database Savings Plans offer flexibility to change engines/instances post-migration. Mutually exclusive with RDS RIs on same workload.",
  "alternative": {
    "opportunity": "RDS Reserved Instances",
    "type": "rds_reserved_instances",
    "savings_percent": "up to 69%",
    "trade_off": "Locked to specific instance family and region"
  },
  "references": [
    "https://aws.amazon.com/savingsplans/database-pricing/",
    "https://aws.amazon.com/rds/reserved-instances/"
  ]
}
```

### Fargate Spot (when worker processes exist)

```json
{
  "opportunity": "Fargate Spot for Worker Tasks",
  "type": "fargate_spot",
  "target_services": ["Fargate"],
  "savings_percent": "60-70%",
  "savings_monthly": "<calculated based on worker task costs>",
  "commitment": "none",
  "timing": "during migration (for fault-tolerant workers)",
  "implementation_effort": "medium",
  "prerequisite": "Worker tasks must be fault-tolerant and idempotent",
  "description": "Fly.io worker machines mapped to Fargate can use Spot pricing for background/batch work that tolerates interruption."
}
```

Only include optimizations relevant to the designed architecture. Do not include EC2-specific optimizations if no EC2 in design.

---

## Part 7: Recommendation

Present 3 paths:

1. **Migrate with Optimizations (Best ROI)** — optimized service choices, projected savings
2. **Phased Migration (Lower Risk)** — app-by-app per design order, validate each before proceeding
3. **Stay on fly.io (Lowest Complexity)** — only if AWS is more expensive and costs are the sole metric

Include migrate/stay decision factors:

- **Migrate if:** infrastructure control matters, AWS-specific services needed, compliance requirements exceed fly.io's offerings, scaling beyond fly.io limits, long-term cost optimization (Savings Plans, Spot)
- **Stay if:** cost is the only metric and AWS is more expensive, team benefits from fly.io's simplicity, no need for AWS-specific services, migration risk exceeds benefit

### Persist recommendation to estimation-infra.json

```json
"recommendation": {
  "path": "migrate_optimized|migrate_phased|stay",
  "path_label": "Migrate with Optimizations|Phased Migration|Stay on fly.io",
  "roi_justification": "<one-sentence ROI case>",
  "confidence": "high|medium|low",
  "migrate_if": ["<factors specific to THIS stack>"],
  "stay_if": ["<factors specific to THIS stack>"],
  "next_steps": ["<actionable items>"]
}
```

**Path selection logic:**

| Scenario                                     | `path` value          | `path_label`                   |
| -------------------------------------------- | --------------------- | ------------------------------ |
| AWS cheaper or operational benefits justify  | `"migrate_optimized"` | `"Migrate with Optimizations"` |
| Complex stack, app-by-app safer              | `"migrate_phased"`    | `"Phased Migration"`           |
| AWS more expensive AND costs are sole metric | `"stay"`              | `"Stay on fly.io"`             |

---

## Output: Write `estimation-infra.json`

Assemble the full artifact conforming to `$GCP_SHARED/schema-estimate-infra.md`:

```json
{
  "phase": "estimate",
  "design_source": "infrastructure",
  "timestamp": "<ISO 8601>",
  "pricing_source": {
    "status": "cached|live|cached_fallback|unavailable",
    "message": "<human-readable pricing status>",
    "fallback_staleness": {
      "last_updated": "<cache date>",
      "days_old": "<N>",
      "is_stale": false,
      "staleness_warning": null
    },
    "services_by_source": {
      "live": [],
      "fallback": [],
      "estimated": []
    },
    "services_with_missing_fallback": []
  },
  "accuracy_confidence": "±5-10%",

  "current_costs": {
    "source": "user_provided|pricing_fetched|pricing_mixed|pricing_estimate|unavailable",
    "accuracy": "<±20%|±10%|±25%>",
    "fly_monthly": "<total or null>",
    "fly_annual": "<total × 12 or null>",
    "fly_rate_source": { "url": "<or null>", "fetched_date": "<or null>", "region": "<or null>" },
    "baseline_note": "<source description>",
    "breakdown": { "compute": "<X>", "database": "<X>", "volumes": "<X>", "extensions": "<X>" }
  },

  "projected_costs": {
    "aws_monthly_premium": "<N>",
    "aws_monthly_balanced": "<N>",
    "aws_monthly_optimized": "<N>",
    "aws_annual_optimized": "<N × 12>",
    "breakdown": { "...per-service entries..." }
  },

  "cost_comparison": { "...from Part 3..." },
  "migration_cost_considerations": { "...from Part 4..." },
  "roi_analysis": { "...from Part 5..." },
  "optimization_opportunities": [ "...from Part 6..." ],

  "financial_summary": {
    "current_fly_monthly": "<N or null>",
    "projected_aws_balanced_monthly": "<N>",
    "projected_aws_optimized_monthly": "<N>",
    "monthly_savings_balanced": "<fly - balanced, negative = AWS more expensive>",
    "monthly_savings_optimized": "<fly - optimized>",
    "annual_savings_optimized": "<× 12>",
    "recommendation": "<summary sentence>"
  },

  "recommendation": { "...from Part 7..." }
}
```

Write to `$MIGRATION_DIR/estimation-infra.json`.

---

## Completion Handoff Gate (Fail Closed)

Load `$GCP_SHARED/handoff-gates.md`. **Re-read from disk** before checking.

Before returning control to SKILL.md, require:

1. `estimation-infra.json` exists in `$MIGRATION_DIR/`
2. Valid JSON that passes `$GCP_SHARED/schema-estimate-infra.md` validation
3. `recommendation.path` ∈ `{migrate_optimized, migrate_phased, stay}`
4. `recommendation.path_label` is non-empty string
5. `recommendation.migrate_if` and `recommendation.stay_if` are non-empty arrays
6. `projected_costs.aws_monthly_balanced` is a positive number
7. Every compute group in `aws-design.json → compute.<group>` appears in the cost breakdown (or is listed as `"unpriced"` in warnings)
8. Total equals sum of individual resource costs (excluding unpriced) — **Property 16 invariant**

**On FAIL:** Emit `GATE_FAIL | phase=estimate | field=<path> | reason=<reason>`. **Do NOT modify artifacts to pass the gate.** STOP.

**On PASS:** Emit `HANDOFF_OK | phase=estimate | artifacts=estimation-infra.json`.

After `HANDOFF_OK`, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json`:

- Set `phases.estimate` to `"completed"`
- Set `current_phase` to `"generate"`
- Update `last_updated` timestamp

---

## Present Summary

After writing `estimation-infra.json`, present a concise summary to the user:

1. **Pricing source and accuracy** — State cache age and accuracy range
2. **Fly.io baseline vs AWS projected** (balanced tier) — one-line comparison (if baseline available)
3. **Three-tier table**: Premium, Balanced, Optimized with monthly totals
   - Premium: _Highest resilience / highest monthly estimate_
   - Balanced: _Default scenario; compare fly.io to this first_
   - Optimized: _Lower estimate; reservations / Spot trade-offs assumed_
   - One-line note: Three figures are pricing scenarios for the same architecture (not three Terraform stacks). Generated Terraform aligns with Balanced.
4. **Per-service cost breakdown** (balanced tier, 1 line per service)
5. **Monthly and annual savings** (or increase) vs fly.io per tier (if comparison available)
6. **Top 2-3 optimization opportunities** with savings potential
7. **Recommendation**: `path_label` with one-line justification

Keep under 25 lines. The user can ask for details or re-read `estimation-infra.json`.

---

## Scope Boundary

**This phase covers financial analysis ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Changes to architecture mappings from Phase 3 (Design)
- Execution timelines or migration schedules
- Terraform or IaC code generation
- Detailed migration procedures or runbooks
- Team staffing, human labor costs, or professional services fees
- AI workload estimation (not applicable to fly.io migrations)

**Your ONLY job: Show the financial picture of moving from fly.io to AWS. Nothing else.**
