# fly-resource-inventory.json Schema

**File location:** `$MIGRATION_DIR/fly-resource-inventory.json`

**Purpose:** Canonical output of the Discover phase. Contains all detected fly.io resources, configurations, and signals. Used by Clarify, Design, Estimate, and Generate phases.

**Format:** JSON array of app entries (multi-app support). Each app is independent.

---

## Root Structure

```json
[
  {
    "app": "myapp",
    "primary_region": "iad",
    "process_groups": [...],
    "volumes": [...],
    "databases": [...],
    "object_storage": [...],
    "extensions": [...],
    "network_flags": {...},
    "actuals": {...},
    "_detected": [...]
  }
]
```

**Root-level array:** Each element is one app entry (one fly.toml → one entry). Multi-app repos produce multiple entries.

---

## App Entry Schema

### Required Top-Level Fields

| Field            | Type   | Description                                                                                                        |
| ---------------- | ------ | ------------------------------------------------------------------------------------------------------------------ |
| `app`            | string | Fly app name (from fly.toml `app` field). REQUIRED. Must be non-empty.                                             |
| `primary_region` | string | Primary region code (e.g., `"iad"`, `"lhr"`, `"syd"`). REQUIRED. Defaults to `"unknown"` if missing from fly.toml. |
| `process_groups` | array  | Array of process group objects. REQUIRED (may be empty for database-only apps).                                    |
| `volumes`        | array  | Array of volume objects. REQUIRED (may be empty).                                                                  |
| `databases`      | array  | Array of database objects. REQUIRED (may be empty).                                                                |
| `object_storage` | array  | Array of object storage objects. REQUIRED (may be empty).                                                          |
| `extensions`     | array  | Array of extension objects. REQUIRED (may be empty).                                                               |
| `network_flags`  | object | Network-related flags. REQUIRED.                                                                                   |
| `actuals`        | object | Actual deployed state (from flyctl JSON exports or declared-only). REQUIRED.                                       |
| `_detected`      | array  | Human-readable strings describing what signals were found. REQUIRED (may be empty).                                |

---

## Process Group Object

Each element in `process_groups[]`:

```json
{
  "name": "web",
  "command": "rails server",
  "vm": {
    "preset": "shared-cpu-1x",
    "cpus": null,
    "memory_mb": 512
  },
  "scaling": {
    "auto_stop": "stop",
    "auto_start": true,
    "min_machines_running": 0
  },
  "flags": {
    "agent_candidate": false,
    "agent_evidence": [],
    "gpu": false,
    "one_shot": false,
    "stateful_mounts": []
  },
  "services": [
    {
      "internal_port": 8080,
      "handlers": ["http"]
    }
  ]
}
```

| Field                          | Type    | Description                                                                                                                                                      |
| ------------------------------ | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`                         | string  | Process group name (from `[processes]` key or app name if single-group). REQUIRED.                                                                               |
| `command`                      | string  | Command to run (from `[processes]` value or Procfile/Dockerfile). May be `null`.                                                                                 |
| `vm.preset`                    | string  | Fly machine preset (e.g., `"shared-cpu-1x"`, `"performance-2x"`). `null` if custom sizing.                                                                       |
| `vm.cpus`                      | int     | Custom CPU count (overrides preset). `null` if using preset.                                                                                                     |
| `vm.memory_mb`                 | int     | Memory in MB. From preset or custom `[[vm]]` config. May be `null` if unknown.                                                                                   |
| `scaling.auto_stop`            | string  | `"stop"` / `"suspend"` / `null`. Fly's auto_stop_machines config.                                                                                                |
| `scaling.auto_start`           | boolean | Auto-start on request. Fly's auto_start_machines config. May be `null`.                                                                                          |
| `scaling.min_machines_running` | int     | Minimum machines running (primary region only on Fly). Fly's min_machines_running. May be `null`.                                                                |
| `flags.agent_candidate`        | boolean | REQUIRED. `true` if Machines API / agent framework / Sprites detected. `false` otherwise.                                                                        |
| `flags.agent_evidence`         | array   | REQUIRED. Strings describing why agent_candidate is true (e.g., `"Machines API usage detected"`, `"Framework: LangGraph"`). Empty if `agent_candidate` is false. |
| `flags.gpu`                    | boolean | REQUIRED. `true` if GPU usage detected (fly.toml `gpu_kind` or CUDA imports). Triggers urgency banner.                                                           |
| `flags.one_shot`               | boolean | REQUIRED. `true` if `[[restart]] policy=never` (batch workload). Routes to Lambda/Batch/ECS scheduled task.                                                      |
| `flags.stateful_mounts`        | array   | REQUIRED. Array of `{volume: string, path: string}` objects for each `[[mounts]]` entry. Empty if no mounts.                                                     |
| `services`                     | array   | REQUIRED. Array of service objects (ports/handlers). Empty if no `[[services]]` or `[http_service]`.                                                             |

### Service Object

Each element in `services[]`:

```json
{
  "internal_port": 8080,
  "handlers": ["http"],
  "protocol": "tcp"
}
```

| Field           | Type   | Description                                                                                             |
| --------------- | ------ | ------------------------------------------------------------------------------------------------------- |
| `internal_port` | int    | REQUIRED. Internal port (from `[http_service].internal_port` or `[[services]].internal_port`).          |
| `handlers`      | array  | REQUIRED. Array of handler strings: `"http"`, `"tls"`, `"proxy_proto"`, `"pg_tls"`, or empty (raw TCP). |
| `protocol`      | string | Optional. `"tcp"` (default) / `"udp"`. From `[[services]].protocol`.                                    |

---

## Volume Object

Each element in `volumes[]`:

```json
{
  "name": "postgres_data",
  "size_gb": null,
  "region": "iad"
}
```

| Field     | Type   | Description                                                               |
| --------- | ------ | ------------------------------------------------------------------------- |
| `name`    | string | REQUIRED. Volume name (from `[[mounts]].source`).                         |
| `size_gb` | int    | Volume size in GB. `null` if not specified in fly.toml or flyctl exports. |
| `region`  | string | REQUIRED. Volume region. Defaults to `primary_region` if not specified.   |

---

## Database Object

Each element in `databases[]`:

```json
{
  "type": "postgres",
  "managed": true,
  "name": "myapp-postgres",
  "engine": "postgres",
  "version": "unknown",
  "notes": "Fly Managed Postgres (MPG) — migration to RDS Multi-AZ + RDS Proxy recommended"
}
```

| Field     | Type    | Description                                                                                                       |
| --------- | ------- | ----------------------------------------------------------------------------------------------------------------- |
| `type`    | string  | REQUIRED. `"postgres"` / `"mysql"`. Database type.                                                                |
| `managed` | boolean | REQUIRED. `true` for Fly Managed Postgres (MPG). `false` for legacy Fly Postgres (postgres-flex).                 |
| `name`    | string  | REQUIRED. Database name (app name or detected identifier).                                                        |
| `engine`  | string  | REQUIRED. `"postgres"` / `"mysql"`.                                                                               |
| `version` | string  | REQUIRED. Version string or `"unknown"` if not detected.                                                          |
| `notes`   | string  | REQUIRED. Human-readable migration notes (e.g., "Legacy Fly Postgres (unsupported) — RDS migration recommended"). |

---

## Object Storage Object

Each element in `object_storage[]`:

```json
{
  "provider": "tigris",
  "bucket": "myapp-assets",
  "region": "auto"
}
```

| Field      | Type   | Description                                                                |
| ---------- | ------ | -------------------------------------------------------------------------- |
| `provider` | string | REQUIRED. `"tigris"` (only provider in v1).                                |
| `bucket`   | string | REQUIRED. Bucket name (from `[[statics]].tigris_bucket` or detected).      |
| `region`   | string | REQUIRED. `"auto"` for Tigris (global). Maps to real AWS region in Design. |

---

## Extension Object

Each element in `extensions[]`:

```json
{
  "name": "upstash-redis",
  "type": "redis",
  "provider": "upstash",
  "migration_target": "elasticache-serverless"
}
```

| Field              | Type   | Description                                                                                                                         |
| ------------------ | ------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `name`             | string | REQUIRED. Extension name (e.g., `"upstash-redis"`, `"upstash-vector"`, `"sentry"`, `"arcjet"`).                                     |
| `type`             | string | REQUIRED. Extension type: `"redis"`, `"vector"`, `"observability"`, `"security"`.                                                   |
| `provider`         | string | REQUIRED. Provider name: `"upstash"`, `"sentry"`, `"arcjet"`.                                                                       |
| `migration_target` | string | REQUIRED. AWS target or `"keep-as-saas"`. Examples: `"elasticache-serverless"`, `"opensearch-serverless-vector"`, `"keep-as-saas"`. |

---

## Network Flags Object

```json
{
  "fly_replay": false,
  "sixpn_dynamic": false,
  "multi_region": [],
  "udp": false,
  "raw_tcp": false
}
```

| Field           | Type    | Description                                                                                                                |
| --------------- | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `fly_replay`    | boolean | REQUIRED. `true` if `fly-replay` header detected in code. Highest-effort networking flag (no AWS LB equivalent).           |
| `sixpn_dynamic` | boolean | REQUIRED. `true` if dynamic 6PN discovery detected (`top\d+.nearest.of`, `_apps.internal`). Code rewrite required.         |
| `multi_region`  | array   | REQUIRED. Array of region codes if multi-region deployment detected (from flyctl exports or code). Empty if single-region. |
| `udp`           | boolean | REQUIRED. `true` if UDP services detected (`[[services]].protocol = "udp"`). Routes to NLB UDP listener.                   |
| `raw_tcp`       | boolean | REQUIRED. `true` if raw TCP services detected (`[[services.ports]].handlers = []`). Routes to NLB TCP passthrough.         |

---

## Actuals Object

```json
{
  "source": "flyctl_export",
  "machines": [
    {
      "id": "abc123",
      "region": "iad",
      "state": "started",
      "vm_preset": "shared-cpu-1x",
      "process_group": "web"
    }
  ]
}
```

| Field      | Type   | Description                                                                                                        |
| ---------- | ------ | ------------------------------------------------------------------------------------------------------------------ |
| `source`   | string | REQUIRED. Enum: `"flyctl_export"` (flyctl JSON exports ingested) or `"declared_only"` (fly.toml only, no actuals). |
| `machines` | array  | REQUIRED. Array of machine objects (from `fly machines list --json`). Empty if `source = "declared_only"`.         |

### Machine Object (in `actuals.machines[]`)

```json
{
  "id": "abc123",
  "region": "iad",
  "state": "started",
  "vm_preset": "shared-cpu-1x",
  "process_group": "web"
}
```

| Field           | Type   | Description                                                              |
| --------------- | ------ | ------------------------------------------------------------------------ |
| `id`            | string | REQUIRED. Machine ID (from flyctl JSON).                                 |
| `region`        | string | REQUIRED. Machine region.                                                |
| `state`         | string | REQUIRED. Machine state: `"started"`, `"stopped"`, `"suspended"`, etc.   |
| `vm_preset`     | string | Optional. VM preset name if available.                                   |
| `process_group` | string | Optional. Process group name (inferred from machine config or fly.toml). |

---

## `_detected` Array

Human-readable strings describing what signals were found during discovery. Used for user output and debugging.

**Examples:**

```json
[
  "fly.toml parsed: 2 process groups (web, worker)",
  "Scale-to-zero default detected (auto_stop=stop, min_machines_running=0)",
  "HTTP service on internal_port 8080",
  "Machines API usage detected — likely AI agent sandbox workload",
  "Framework: LangGraph — agent orchestration detected",
  "fly-replay header usage detected — highest-effort networking flag (no AWS LB equivalent)",
  "6PN dynamic service discovery detected (topN.nearest.of / _apps.internal) — NO AWS equivalent, code rewrite required",
  "Tigris object storage detected — S3 migration path available",
  "Managed Postgres (MPG) detected — RDS Multi-AZ / Aurora Serverless v2 migration path available",
  "Upstash Redis detected — ElastiCache Serverless migration path available",
  "GPU usage detected — hard sunset 2026-08-01 for Fly GPU Machines",
  "Sprites detected — v1 is detect-only; sandbox workloads can route to agent-advisor",
  "Ingested actuals from flyctl JSON exports (3 machines)",
  "Stateful mounts detected (1 volume) — de-volume/EFS/ECS-on-EC2 decision needed"
]
```

**Rules:**

- One string per significant signal or decision.
- No duplicates (deduplicate before writing).
- Order: most critical first (GPU urgency, fly-replay, 6PN dynamic, then others).
- Always include "(correct me if wrong)" qualifier when presenting to user.

---

## Validation Checklist

Before writing `fly-resource-inventory.json`, verify:

1. Root is a JSON array (even for single app).
2. Each app entry has all required top-level fields.
3. Each process group has all required fields (`name`, `vm`, `scaling`, `flags`, `services`).
4. Each process group's `flags` has all required boolean/array fields (`agent_candidate`, `agent_evidence`, `gpu`, `one_shot`, `stateful_mounts`).
5. `network_flags` has all required boolean/array fields (`fly_replay`, `sixpn_dynamic`, `multi_region`, `udp`, `raw_tcp`).
6. `actuals.source` is either `"flyctl_export"` or `"declared_only"`.
7. If `actuals.source = "flyctl_export"`, `actuals.machines` is non-empty.
8. `_detected` array contains at least one entry (or is empty if no signals found — rare).
9. No `null` values for REQUIRED fields (except where explicitly allowed, e.g., `command`, `vm.cpus`).
10. All arrays exist (may be empty, but not `null`).

---

## Example: Minimal App

```json
[
  {
    "app": "minimal-app",
    "primary_region": "iad",
    "process_groups": [
      {
        "name": "minimal-app",
        "command": null,
        "vm": {
          "preset": "shared-cpu-1x",
          "cpus": null,
          "memory_mb": 256
        },
        "scaling": {
          "auto_stop": null,
          "auto_start": null,
          "min_machines_running": null
        },
        "flags": {
          "agent_candidate": false,
          "agent_evidence": [],
          "gpu": false,
          "one_shot": false,
          "stateful_mounts": []
        },
        "services": []
      }
    ],
    "volumes": [],
    "databases": [],
    "object_storage": [],
    "extensions": [],
    "network_flags": {
      "fly_replay": false,
      "sixpn_dynamic": false,
      "multi_region": [],
      "udp": false,
      "raw_tcp": false
    },
    "actuals": {
      "source": "declared_only",
      "machines": []
    },
    "_detected": [
      "Minimal fly.toml — defaults applied"
    ]
  }
]
```

---

## Example: Multi-Process-Group App with Volumes and MPG

```json
[
  {
    "app": "rails-app",
    "primary_region": "iad",
    "process_groups": [
      {
        "name": "web",
        "command": "rails server",
        "vm": {
          "preset": "shared-cpu-2x",
          "cpus": null,
          "memory_mb": 1024
        },
        "scaling": {
          "auto_stop": "stop",
          "auto_start": true,
          "min_machines_running": 0
        },
        "flags": {
          "agent_candidate": false,
          "agent_evidence": [],
          "gpu": false,
          "one_shot": false,
          "stateful_mounts": []
        },
        "services": [
          {
            "internal_port": 3000,
            "handlers": ["http"],
            "protocol": "tcp"
          }
        ]
      },
      {
        "name": "worker",
        "command": "sidekiq",
        "vm": {
          "preset": "shared-cpu-1x",
          "cpus": null,
          "memory_mb": 512
        },
        "scaling": {
          "auto_stop": "stop",
          "auto_start": true,
          "min_machines_running": 0
        },
        "flags": {
          "agent_candidate": false,
          "agent_evidence": [],
          "gpu": false,
          "one_shot": false,
          "stateful_mounts": []
        },
        "services": []
      },
      {
        "name": "release",
        "command": "bundle exec rails db:migrate",
        "vm": {
          "preset": "shared-cpu-1x",
          "cpus": null,
          "memory_mb": 256
        },
        "scaling": {
          "auto_stop": null,
          "auto_start": null,
          "min_machines_running": null
        },
        "flags": {
          "agent_candidate": false,
          "agent_evidence": [],
          "gpu": false,
          "one_shot": true,
          "stateful_mounts": []
        },
        "services": []
      }
    ],
    "volumes": [
      {
        "name": "rails_storage",
        "size_gb": 10,
        "region": "iad"
      }
    ],
    "databases": [
      {
        "type": "postgres",
        "managed": true,
        "name": "rails-app-postgres",
        "engine": "postgres",
        "version": "unknown",
        "notes": "Fly Managed Postgres (MPG) — migration to RDS Multi-AZ + RDS Proxy recommended"
      }
    ],
    "object_storage": [],
    "extensions": [],
    "network_flags": {
      "fly_replay": false,
      "sixpn_dynamic": false,
      "multi_region": [],
      "udp": false,
      "raw_tcp": false
    },
    "actuals": {
      "source": "declared_only",
      "machines": []
    },
    "_detected": [
      "fly.toml parsed: 3 process groups (web, worker, release)",
      "Scale-to-zero default detected (auto_stop=stop, min_machines_running=0) for web and worker",
      "One-shot workload detected: release (restart policy=never)",
      "HTTP service on internal_port 3000",
      "Stateful mounts detected (1 volume) — de-volume/EFS/ECS-on-EC2 decision needed",
      "Managed Postgres (MPG) detected — RDS Multi-AZ / Aurora Serverless v2 migration path available"
    ]
  }
]
```

---

## Example: Agent-Candidate App (Machines API + LangGraph)

```json
[
  {
    "app": "agent-app",
    "primary_region": "ord",
    "process_groups": [
      {
        "name": "agent",
        "command": "python agent.py",
        "vm": {
          "preset": "performance-2x",
          "cpus": null,
          "memory_mb": 4096
        },
        "scaling": {
          "auto_stop": "suspend",
          "auto_start": true,
          "min_machines_running": 1
        },
        "flags": {
          "agent_candidate": true,
          "agent_evidence": [
            "Machines API usage detected — likely dynamic sandbox orchestration (AI agent candidate)",
            "Framework: LangGraph — agent orchestration detected"
          ],
          "gpu": false,
          "one_shot": false,
          "stateful_mounts": []
        },
        "services": [
          {
            "internal_port": 8000,
            "handlers": ["http"],
            "protocol": "tcp"
          }
        ]
      }
    ],
    "volumes": [],
    "databases": [],
    "object_storage": [],
    "extensions": [],
    "network_flags": {
      "fly_replay": false,
      "sixpn_dynamic": false,
      "multi_region": [],
      "udp": false,
      "raw_tcp": false
    },
    "actuals": {
      "source": "declared_only",
      "machines": []
    },
    "_detected": [
      "fly.toml parsed: 1 process group (agent)",
      "Machines API usage detected — likely AI agent sandbox workload",
      "Framework: LangGraph — agent orchestration detected",
      "Scale-to-zero with suspend (auto_stop=suspend, min_machines_running=1)",
      "HTTP service on internal_port 8000"
    ]
  }
]
```

---

## Notes

- **Config ≠ intent.** `fly launch` defaults to scale-to-zero (`auto_stop="stop"`, `min_machines_running=0`) — nearly every fly.toml carries this semantic, often without deliberate choice. Discover records these as signals; Clarify MUST confirm whether each is a deliberate requirement or an inherited default.
- **Determinism boundary.** All detections are best-effort LLM interpretation. Always present `_detected` strings to user as "detected: X (correct me if wrong)" before routing.
- **No secrets.** Never log secret VALUES (DSNs, tokens, credentials). Only log that the VAR NAME exists.
- **Multi-app support.** The root-level array enables monorepo/multi-app setups. Each fly.toml → one entry.
- **Actuals vs declared.** `actuals.source` distinguishes between declared-only (fly.toml) and flyctl-export (real deployed state). Design and Estimate phases prefer actuals when available.
