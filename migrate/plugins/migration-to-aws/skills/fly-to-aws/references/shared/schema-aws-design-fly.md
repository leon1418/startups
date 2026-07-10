# aws-design.json Schema

**File location:** `$MIGRATION_DIR/aws-design.json`

**Purpose:** Output of the Design phase. Contains the AWS architecture blueprint with compute targets, database mappings, storage recommendations, network configuration, and specialist gates. Consumed by Estimate and Generate phases.

**Format:** JSON object with structured sections.

---

## Root Structure

```json
{
  "migration_id": "0709-1430",
  "skill": "fly-to-aws",
  "metadata": {
    "timestamp": "2026-07-09T14:30:00Z",
    "design_version": "1.0"
  },
  "compute": {...},
  "databases": [...],
  "storage": [...],
  "cache": [...],
  "network": {...},
  "secrets": {...},
  "specialist_gates": [...],
  "warnings": [...]
}
```

---

## Field Definitions

### `migration_id` (string, REQUIRED)

The migration run identifier (e.g., `"0709-1430"`). Must match the value in `.phase-status.json`.

---

### `skill` (string, REQUIRED)

Must be `"fly-to-aws"`.

---

### `metadata` (object, REQUIRED)

| Field            | Type   | Required | Description                                         |
| ---------------- | ------ | -------- | --------------------------------------------------- |
| `timestamp`      | string | Yes      | ISO 8601 timestamp of when this file was generated. |
| `design_version` | string | Yes      | Schema version. Currently `"1.0"`.                  |

---

### `compute` (object, REQUIRED)

A dictionary mapping process group names to their AWS compute targets. Keys are process group names from the inventory. Values are compute entry objects.

**Compute Entry Object:**

```json
{
  "target": "fargate_ecs_express",
  "layer_fired": "4",
  "decided_by": "routing_table",
  "sizing": {
    "cpu": 0.25,
    "memory_gb": 0.5
  },
  "notes": ["Always-on service — min 1 task"]
}
```

| Field         | Type   | Required | Description                                                                                                                                                                                                             |
| ------------- | ------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `target`      | string | Yes      | AWS compute target. Must be one of the enum values (see Target Enum below).                                                                                                                                             |
| `layer_fired` | string | Yes      | Routing table layer that matched this group. One of: `"G"` (guard), `"0"` (agent), `"1"` (GPU), `"2"` (one-shot), `"4"` (always-on), `"5"` (scale-to-zero). Audit trail for behavioral tests.                           |
| `decided_by`  | string | Yes      | How this routing decision was made. One of: `"routing_table"` (computed by design.md), `"agent-advisor"` (embedded advisor run or Direction-A injection), `"user"` (manual override). Audit trail for behavioral tests. |
| `sizing`      | object | Yes      | Resource sizing. Fields vary by target type (see Sizing Object below).                                                                                                                                                  |
| `notes`       | array  | Yes      | Human-readable notes explaining the routing decision, caveats, or alternatives. May be empty.                                                                                                                           |
| `advisor_ctx` | object | No       | Present only when `decided_by == "agent-advisor"`. Contains embedded advisor run context (see Advisor Context Object below).                                                                                            |

**Target Enum:**

Valid values for `compute.<group>.target`:

- `fargate_ecs_express` — ECS Express Mode on Fargate (serverless containers)
- `eks` — Elastic Kubernetes Service (user chose to reuse existing cluster)
- `lambda` — AWS Lambda (function model)
- `lambda_microvms` — Lambda MicroVMs (containerized with suspend/resume)
- `fargate_min1` — Fargate with min 1 task (always-on service)
- `ec2_gpu` — EC2 GPU instances (custom compute workloads)
- `sagemaker_endpoint` — SageMaker endpoints (inference)
- `bedrock_handoff` — Bedrock handoff (LLM inference use case)
- `batch` — AWS Batch (batch workloads)
- `ecs_scheduled_task` — ECS scheduled task (one-shot jobs)
- `agentcore` — AgentCore runtime (agent-advisor verdict)
- Plus any agent-advisor verdicts verbatim (e.g., `agentcore_ruby`, `lambda_snapstart`, etc.)

**Sizing Object:**

Fields vary by target type:

| Target Type        | Sizing Fields                                                              |
| ------------------ | -------------------------------------------------------------------------- |
| `fargate_*`, `eks` | `cpu` (float, vCPUs), `memory_gb` (float)                                  |
| `lambda`           | `memory_mb` (int)                                                          |
| `lambda_microvms`  | `memory_mb` (int), optional: `cpu` (float)                                 |
| `ec2_gpu`          | `instance_type` (string, e.g., `"g5.xlarge"`), optional: `gpu_count` (int) |
| `agentcore`        | `cpu` (float), `memory_gb` (float), optional: `gpu` (bool)                 |
| Others             | Varies; at minimum must be a non-empty object                              |

**Advisor Context Object:**

Present only when `compute.<group>.decided_by == "agent-advisor"`. Contains metadata from the embedded advisor run:

```json
{
  "embed_dir": "/path/to/.migration/0709-1430/agent-advisor/web/",
  "verdict": "agentcore",
  "deployment_model": "harness",
  "services_hint": ["identity", "observability", "memory", "code_interpreter"]
}
```

| Field              | Type   | Required | Description                                                                                                                                                                                                             |
| ------------------ | ------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `embed_dir`        | string | Yes      | Absolute path to the embedded advisor run directory for this group.                                                                                                                                                     |
| `verdict`          | string | Yes      | Advisor runtime verdict (same as `target`).                                                                                                                                                                             |
| `deployment_model` | string | Yes      | Deployment model from advisor pass2: `"harness"` (managed no-code) or `"framework_on_runtime"` (bring your own framework).                                                                                              |
| `services_hint`    | array  | Yes      | List of AgentCore add-on service names from advisor pass2 (e.g., `["identity", "observability", "memory", "gateway", "code_interpreter"]`). Code Interpreter appears only in this list when enabled, never as `target`. |

---

### `databases` (array, REQUIRED)

Array of database mapping objects. Empty if no databases in inventory.

**Database Object:**

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

| Field            | Type   | Required      | Description                                                                                   |
| ---------------- | ------ | ------------- | --------------------------------------------------------------------------------------------- |
| `name`           | string | Yes           | Database name (from inventory).                                                               |
| `source_type`    | string | Yes           | Source type: `"fly_mpg"` (Fly Managed Postgres), `"fly_postgres_legacy"` (legacy unmanaged).  |
| `target`         | string | Yes           | AWS target: `"rds_postgres_multi_az"`, `"rds_mysql_multi_az"`, `"aurora_serverless_v2"`, etc. |
| `instance_class` | string | Yes (for RDS) | RDS instance class (e.g., `"db.m7g.large"`, `"db.t4g.micro"`). Omit for Aurora Serverless.    |
| `storage_gb`     | int    | Yes           | Storage allocation in GB.                                                                     |
| `include_proxy`  | bool   | Optional      | Whether to include RDS Proxy (for PgBouncer parity). Default `false`.                         |
| `notes`          | array  | Yes           | Human-readable notes. May be empty.                                                           |

---

### `storage` (array, REQUIRED)

Array of storage recommendation objects. Populated from inventory `volumes[]` (Design Step 4) and `object_storage[]` (Design Step 5.5). Empty if neither exists in inventory.

**Storage Object:**

```json
{
  "name": "data_volume",
  "source_size_gb": 10,
  "recommendation": "de-volume",
  "alternatives": ["efs", "ecs_on_ec2_ebs"],
  "notes": ["Migrate structured data to RDS, file blobs to S3"]
}
```

Tigris object storage (from inventory `object_storage[]`) maps to an S3 entry:

```json
{
  "name": "myapp-assets",
  "source_provider": "tigris",
  "source_size_gb": 0,
  "recommendation": "s3",
  "notes": [
    "Endpoint/credential swap + aws s3 sync",
    "Region auto → real region",
    "+CloudFront if edge reads mattered",
    "Egress cost-shape change $0.09/GB flagged"
  ]
}
```

| Field             | Type   | Required | Description                                                                                                                                                                                                                                                                                                                      |
| ----------------- | ------ | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`            | string | Yes      | Volume or bucket name (from inventory).                                                                                                                                                                                                                                                                                          |
| `source_provider` | string | Optional | Present for object storage entries: `"tigris"`. Omit for volume entries.                                                                                                                                                                                                                                                         |
| `source_size_gb`  | int    | Yes      | Source size in GB (use `0` if unknown for object storage).                                                                                                                                                                                                                                                                       |
| `recommendation`  | string | Yes      | Recommended AWS approach: `"de-volume"` (migrate to RDS+S3), `"efs"` (Amazon EFS), `"ecs_on_ec2_ebs"` (ECS on EC2 with EBS), `"s3"` (Tigris → Amazon S3), `"specialist_engagement"` (deferred). **Must contain the substring `"s3"` for object storage** — Generate's `has_s3` detection and Estimate's S3 cost row key on this. |
| `alternatives`    | array  | Optional | Alternative approaches (if applicable).                                                                                                                                                                                                                                                                                          |
| `notes`           | array  | Yes      | Human-readable notes. May be empty.                                                                                                                                                                                                                                                                                              |

---

### `cache` (array, REQUIRED)

Array of cache mapping objects. Empty if no cache/Redis extensions in inventory.

**Cache Object:**

```json
{
  "name": "upstash-redis",
  "source_type": "upstash_redis",
  "target": "elasticache_serverless",
  "notes": ["VPC-only", "HTTP/REST client must switch to Redis-protocol client"]
}
```

| Field         | Type   | Required | Description                                                                                         |
| ------------- | ------ | -------- | --------------------------------------------------------------------------------------------------- |
| `name`        | string | Yes      | Extension/service name.                                                                             |
| `source_type` | string | Yes      | Source type (e.g., `"upstash_redis"`, `"upstash_vector"`).                                          |
| `target`      | string | Yes      | AWS target: `"elasticache_serverless"`, `"opensearch_serverless_vector"`, `"aurora_pgvector"`, etc. |
| `notes`       | array  | Yes      | Migration notes, code changes required, etc. May be empty.                                          |

---

### `network` (object, REQUIRED)

Network configuration and decision records.

```json
{
  "ingress": "single_region_cloudfront",
  "nlb_needed": false,
  "decision_records": []
}
```

| Field              | Type   | Required | Description                                                                                                                                                                                        |
| ------------------ | ------ | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ingress`          | string | Yes      | Ingress pattern: `"single_region_cloudfront"` (ALB + CloudFront), `"multi_region_global_accelerator"` (Global Accelerator + per-region ALBs), `"route53_latency"` (Route53 latency-based routing). |
| `nlb_needed`       | bool   | Yes      | Whether NLB is needed (UDP, raw TCP, or non-HTTP services).                                                                                                                                        |
| `decision_records` | array  | Yes      | Array of network decision record objects (see below). May be empty.                                                                                                                                |

**Network Decision Record Object:**

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
  "effort": "high",
  "notes": []
}
```

| Field            | Type   | Required | Description                                                                                       |
| ---------------- | ------ | -------- | ------------------------------------------------------------------------------------------------- |
| `pattern`        | string | Yes      | Detected pattern: `"fly-replay"`, `"dynamic_6pn_discovery"`, `"multi_region_active_active"`, etc. |
| `aws_equivalent` | string | Yes      | AWS equivalent or `"none"` if no direct equivalent exists.                                        |
| `options`        | array  | Optional | Array of AWS implementation options (if multiple approaches exist).                               |
| `effort`         | string | Yes      | Migration effort: `"low"`, `"medium"`, `"high"`.                                                  |
| `notes`          | array  | Optional | Additional context or caveats.                                                                    |

---

### `secrets` (object, REQUIRED)

Secrets management configuration.

```json
{
  "store": "ssm_parameter_store",
  "count": 12,
  "notes": ["Fly secret values cannot be exported — re-provision from source systems"]
}
```

| Field   | Type   | Required | Description                                                                                                |
| ------- | ------ | -------- | ---------------------------------------------------------------------------------------------------------- |
| `store` | string | Yes      | AWS secrets store: `"ssm_parameter_store"` (default, $0 cost) or `"secrets_manager"` ($0.40/secret/month). |
| `count` | int    | Yes      | Number of secrets detected in inventory.                                                                   |
| `notes` | array  | Yes      | Human-readable notes. May be empty.                                                                        |

---

### `specialist_gates` (array, REQUIRED)

Array of items flagged for specialist engagement (unknown extensions, high-effort networking patterns, etc.). Empty if no specialist gates.

**Specialist Gate Object:**

```json
{
  "type": "extension",
  "name": "unknown-extension",
  "reason": "Extension not in fast-path table",
  "context": "Detected via env var UNKNOWN_API_KEY",
  "effort": "unknown"
}
```

| Field     | Type   | Required | Description                                                          |
| --------- | ------ | -------- | -------------------------------------------------------------------- |
| `type`    | string | Yes      | Gate type: `"extension"`, `"network"`, `"volume"`, `"compute"`, etc. |
| `name`    | string | Yes      | Name/identifier of the item flagged.                                 |
| `reason`  | string | Yes      | Why specialist engagement is needed.                                 |
| `context` | string | Optional | Additional detection context.                                        |
| `effort`  | string | Optional | Estimated effort: `"medium"`, `"high"`, `"unknown"`.                 |

---

### `warnings` (array, REQUIRED)

Array of warning strings (e.g., GPU sunset urgency, cost-shape changes, etc.). Empty if no warnings.

**Example:**

```json
[
  "GPU sunset 2026-08-01 — migration is urgent",
  "Tigris egress cost-shape change: $0.09/GB flagged",
  "Fly secret values cannot be exported — re-provision from source"
]
```

---

## Validation Checklist

Before writing `aws-design.json`, verify:

1. Root structure has all required keys: `compute`, `databases`, `storage`, `cache`, `network`, `secrets`, `specialist_gates`, `warnings`.
2. For each process group in inventory → `compute.<group>` entry exists.
3. For each `compute.<group>` entry:
   - `target` is non-null and matches the Target Enum.
   - `layer_fired` is non-null and one of: `"G"`, `"0"`, `"1"`, `"2"`, `"4"`, `"5"`.
   - `decided_by` is non-null and one of: `"routing_table"`, `"agent-advisor"`, `"user"`.
   - `sizing` is a non-empty object with appropriate fields for the target type.
   - `notes` is an array (may be empty).
4. All database entries have `name`, `source_type`, `target`, and `notes`.
5. All storage entries have `name`, `source_size_gb`, `recommendation`, and `notes`.
6. `network.ingress` is set.
7. `network.nlb_needed` is a boolean.
8. `network.decision_records` is an array (may be empty).
9. `secrets.store` is set.
10. `secrets.count` is a non-negative integer.
11. All arrays exist (may be empty, but not `null`).
12. Output is valid JSON.

---

## Notes

- **Audit trail rule:** Every compute entry MUST carry `layer_fired` and `decided_by`. These fields enable behavioral tests to verify routing logic correctness.
- **Enum strictness:** The `target` field must exactly match one of the enum values listed in this schema. Unknown targets are not allowed (route to `specialist_engagement` instead).
- **Empty arrays are valid:** If no databases, storage, cache, network decision records, specialist gates, or warnings exist, the corresponding array must be present but empty (`[]`).
- **No null values:** All required fields must have non-null values. Use empty arrays or empty strings (`""`) where applicable, not `null`.
