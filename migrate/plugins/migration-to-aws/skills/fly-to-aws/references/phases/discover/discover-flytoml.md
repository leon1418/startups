# fly.toml → Inventory Mapping

**Self-contained parser.** Transforms fly.toml declarations into `fly-resource-inventory.json` structure.

Canonical schema reference: https://fly.io/docs/reference/configuration (verified 2026-07-09)

---

## Parsing Rules

### Rule 1: Multi-app Support

Each fly.toml file produces **one** inventory entry. If multiple fly.toml files exist (monorepo, multi-app setup), parse each independently and produce one entry per file in the root-level inventory array.

### Rule 2: Legacy Postgres Detection

If a fly.toml contains `image = "flyio/postgres-flex*"`:

1. Do NOT create a process group entry for it.
2. Instead, create a `databases` entry with:

   ```json
   {
     "type": "postgres",
     "managed": false,
     "name": "<app name from fly.toml>",
     "engine": "postgres",
     "version": "unknown",
     "notes": "Legacy Fly Postgres (postgres-flex image) — unsupported by fly.io, migration to RDS/Aurora recommended"
   }
   ```

3. Mark this inventory entry as database-only (no process groups).

### Rule 3: Process Group Discovery

The `[processes]` section defines process groups (each = one migration unit):

```toml
[processes]
web = "rails server"
worker = "sidekiq"
release = "bundle exec rails db:migrate"
```

- Each key becomes a process group `name`.
- Each value becomes the process group `command`.
- If NO `[processes]` section exists → create a single process group named after the `app` field, with `command` from Procfile or Dockerfile CMD/ENTRYPOINT (if available), else `null`.

### Rule 4: Multi-tomls Organizational Model

When multiple fly.toml files exist:

1. Each fly.toml represents a separate app (no clustering).
2. Parse each independently.
3. Output structure: array of app entries, one per fly.toml.

---

## Section-by-Section Mapping

### Top-Level Keys

| fly.toml field    | Inventory mapping                                                                                                      |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `app`             | `app` (string, REQUIRED)                                                                                               |
| `primary_region`  | `primary_region` (string, REQUIRED; defaults to `"unknown"` if missing)                                                |
| `kill_signal`     | Note: default is `SIGINT` on Fly, but ECS default is `SIGTERM` — behavior delta. Record in `_detected` if non-default. |
| `kill_timeout`    | Note: 5s default, 300s max on Fly → maps to ECS `stopTimeout`. Record in `_detected` if >30s (ECS default).            |
| `swap_size_mb`    | Note: Fargate has NO swap — record in `_detected` if present.                                                          |
| `console_command` | Record in `_detected` — not migrated.                                                                                  |

### [build]

| fly.toml field | Inventory mapping                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------ |
| `image`        | If `flyio/postgres-flex*` → database entry (Rule 2). Else record in `_detected` as build source. |
| `dockerfile`   | Record in `_detected` — supplements Dockerfile discovery.                                        |
| `buildpacks`   | Record in `_detected` — generate CodeBuild buildpack config note.                                |

### [deploy]

| fly.toml field    | Inventory mapping                                                                                                                                                                               |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `release_command` | Record in `_detected` — maps to ECS one-off task / pre-deploy Lambda.                                                                                                                           |
| `strategy`        | `rolling` → ECS rolling update (default); `immediate` → ECS rolling with no health checks; `bluegreen` → CodeDeploy BlueGreen; `canary` → CodeDeploy with traffic split. Record in `_detected`. |

### [env]

Parse all key-value pairs. Record in `_detected` as "X environment variables declared in fly.toml" (no values logged).

Special detection:

- `AWS_ENDPOINT_URL_S3` → Tigris signal (see discover-code-signals.md)
- `FLY_*` env vars → note as Fly-specific, needs removal/replacement

### [processes]

See Rule 3. Each key = process group `name`, value = `command`.

If `[processes]` is absent → single process group named `<app>` with `command: null` (Procfile/Dockerfile CMD supplements).

### [http_service]

| fly.toml field                    | Inventory mapping                                                                                |
| --------------------------------- | ------------------------------------------------------------------------------------------------ |
| `internal_port`                   | `services[0].internal_port` (int, REQUIRED for HTTP process groups)                              |
| `force_https`                     | Record in `_detected` — ALB redirect rule.                                                       |
| `auto_stop_machines`              | `scaling.auto_stop` (`"stop"` / `"suspend"` / `null`). Default from `fly launch` is `"stop"`.    |
| `auto_start_machines`             | `scaling.auto_start` (boolean). Default from `fly launch` is `true`.                             |
| `min_machines_running`            | `scaling.min_machines_running` (int). Default from `fly launch` is `0`.                          |
| `concurrency.type`                | Note: `requests` (default) → ECS ALBRequestCountPerTarget; `connections` → raw TCP. Record type. |
| `concurrency.soft_limit`          | Note: maps to ALB target-tracking threshold. Record value.                                       |
| `concurrency.hard_limit`          | Note: Fly proxy closes additional conns; ECS has no equivalent — record as detect-only.          |
| `http_options.h2_backend`         | If `true` → gRPC target group. Record in `_detected`.                                            |
| `[[http_service.checks]]`         | Maps to ALB target group health checks. Record path, interval, timeout.                          |
| `[[http_service.machine_checks]]` | Maps to CodeDeploy test hooks. Record in `_detected`.                                            |

**Default scale-to-zero detection:** If `auto_stop_machines="stop"` AND `min_machines_running=0` → flag as **scale-to-zero workload** (semantic gap: Fargate has no request-driven scale-to-zero; routes to Lambda/MicroVMs/AgentCore).

### [[services]]

| fly.toml field       | Inventory mapping                                                                                                                                                                                                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `internal_port`      | `services[].internal_port` (int, REQUIRED)                                                                                                                                                                                                                                                             |
| `protocol`           | `tcp` (default) / `udp`. If `udp` → set `network_flags.udp = true`.                                                                                                                                                                                                                                    |
| `[[services.ports]]` | Array of `{port, handlers}`. If `handlers` is empty → raw TCP, set `network_flags.raw_tcp = true`. If `handlers` includes `tls` → NLB TLS listener. If `handlers` includes `proxy_proto` → NLB proxy-protocol-v2. If `handlers` includes `pg_tls` → Postgres-specific TLS (note: RDS has its own TLS). |

**Note:** Multiple `[[services]]` blocks → multiple target groups / listeners. Record all.

### [checks]

Similar to `http_service.checks` but applies to all process groups. Record in `_detected` as health check config.

### [[mounts]]

| fly.toml field                  | Inventory mapping                                                                                            |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `source`                        | Volume name. Create entry in `volumes[]` array with `{name: source, size_gb: null, region: primary_region}`. |
| `destination`                   | Record in `flags.stateful_mounts[]` as `{volume: source, path: destination}`.                                |
| `snapshot_retention`            | Note: days to retain snapshots. Record in `_detected` (EBS has its own snapshot lifecycle).                  |
| `auto_extend_size_threshold`    | Note: auto-resize at X% full. Record in `_detected` (no EBS equivalent).                                     |
| `auto_extend_size_increment_gb` | Note: resize step. Record in `_detected`.                                                                    |

**Flag:** If ANY `[[mounts]]` exist → this is a **stateful workload** (volumes decision tree applies).

### [[vm]]

| fly.toml field       | Inventory mapping                                                                                                                                                      |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `size`               | Preset name (e.g., `shared-cpu-1x`, `performance-2x`). Map to `vm.preset`. See `machine-preset-table.md` for Fargate sizing.                                           |
| `cpus`               | Custom CPU count. Record in `vm.cpus` (overrides preset).                                                                                                              |
| `memory`             | Custom memory in MB. Record in `vm.memory_mb` (overrides preset).                                                                                                      |
| `cpu_kind`           | `shared` / `performance`. Record in `_detected` (shared ≈ Fargate burstable economics).                                                                                |
| `gpu_kind`           | If present → **GPU workload**. Set `flags.gpu = true`. Record GPU type in `_detected`. **Display urgency banner:** "GPU Machines deprecated — hard sunset 2026-08-01." |
| `host_dedication_id` | Note: dedicated host. Record in `_detected` — maps to EC2 Dedicated Hosts / Fargate Dedicated.                                                                         |
| `persist_rootfs`     | Note: keep rootfs on stop. Record in `_detected` — no Fargate equivalent (ephemeral only).                                                                             |

**GPU detection triggers urgency banner** in Step 6 output.

**Preset defaults:** If `[[vm]]` is absent, default to Fly's `shared-cpu-1x` (256MB).

### [[restart]]

| fly.toml field | Inventory mapping                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `policy`       | If `never` → set `flags.one_shot = true` (batch workload; routes to Lambda/Batch/ECS scheduled task). Else continuous process. |

### [[statics]]

| fly.toml field  | Inventory mapping                                                                                                                                                |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `guest_path`    | Static file mount path. Record in `_detected` as "static files at `<path>`".                                                                                     |
| `url_prefix`    | URL path prefix. Record in `_detected`.                                                                                                                          |
| `tigris_bucket` | **Tigris detection signal.** If present → create entry in `object_storage[]` with `{provider: "tigris", bucket: <name>, region: "auto"}`. Flag for S3 migration. |

### [metrics]

Record in `_detected` — maps to CloudWatch/AMP Prometheus scrape config.

### [[files]]

| fly.toml field | Inventory mapping                                                                                                                         |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `guest_path`   | File mount path. Record in `_detected`.                                                                                                   |
| `raw_value`    | Inline content. Record in `_detected` (migrates to ECS secrets/config).                                                                   |
| `local_path`   | Local file path. Record in `_detected`.                                                                                                   |
| `secret_name`  | **Secrets detection signal.** Record in `_detected` as "file from secret `<name>`" — needs SSM/Secrets Manager mapping + entrypoint shim. |

### [experimental]

| fly.toml field | Inventory mapping                           |
| -------------- | ------------------------------------------- |
| `cmd`          | Command override. Record in `_detected`.    |
| `entrypoint`   | Entrypoint override. Record in `_detected`. |
| `exec`         | Exec array. Record in `_detected`.          |

Any fields in `[experimental]` → note as potentially unstable config.

---

## Output Structure (Per-App Entry)

```json
{
  "app": "myapp",
  "primary_region": "iad",
  "process_groups": [
    {
      "name": "web",
      "command": "rails server",
      "vm": {
        "preset": "shared-cpu-1x",
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
    "fly.toml parsed: 1 process group (web)",
    "Scale-to-zero default detected (auto_stop=stop, min_machines_running=0)",
    "HTTP service on internal_port 8080"
  ]
}
```

---

## Validation Checklist

Before writing the inventory entry, verify:

1. `app` field is non-empty.
2. `primary_region` is set (default to `"unknown"` if missing from fly.toml).
3. At least one process group exists (or database entry for postgres-flex case).
4. Each process group has `name`, `vm`, `scaling`, `flags`, `services`.
5. Each process group's `flags` has all required boolean/array fields.
6. `network_flags` has all required boolean/array fields.
7. `actuals.source` is either `"flyctl_export"` or `"declared_only"`.
8. `_detected` array contains at least one entry describing what was parsed.

---

## Error Handling

| Error                                     | Behavior                                                            |
| ----------------------------------------- | ------------------------------------------------------------------- |
| Malformed TOML (parse error)              | Log warning, skip this fly.toml, continue with other files          |
| Missing `app` field                       | Log warning, skip this fly.toml (cannot inventory without app name) |
| Missing `primary_region`                  | Default to `"unknown"`, continue                                    |
| Missing `[processes]` + no CMD/ENTRYPOINT | Create single process group with `command: null`, continue          |
| `[[mounts]]` with no `source`             | Log warning, skip this mount entry, continue                        |
| `[[vm]]` with invalid preset              | Log warning, default to `shared-cpu-1x`, continue                   |
| Multiple `[http_service]` blocks          | Take first block, log warning about multiple, continue              |

---

## Special Cases

### Case 1: Minimal fly.toml (app name only)

```toml
app = "myapp"
```

Output:

```json
{
  "app": "myapp",
  "primary_region": "unknown",
  "process_groups": [{
    "name": "myapp",
    "command": null,
    "vm": {"preset": "shared-cpu-1x", "memory_mb": 256},
    "scaling": {"auto_stop": null, "auto_start": null, "min_machines_running": null},
    "flags": {"agent_candidate": false, "agent_evidence": [], "gpu": false, "one_shot": false, "stateful_mounts": []},
    "services": []
  }],
  ...
  "_detected": ["Minimal fly.toml — defaults applied"]
}
```

### Case 2: Multi-process-group app

```toml
app = "rails-app"
primary_region = "iad"

[processes]
web = "rails server"
worker = "sidekiq"
release = "bundle exec rails db:migrate"
```

Output: 3 process groups (`web`, `worker`, `release`), each with its own command.

### Case 3: Legacy Postgres app

```toml
app = "pg-legacy"
primary_region = "iad"
image = "flyio/postgres-flex:15"
```

Output: NO process groups. Instead:

```json
{
  "app": "pg-legacy",
  "primary_region": "iad",
  "process_groups": [],
  "databases": [{
    "type": "postgres",
    "managed": false,
    "name": "pg-legacy",
    "engine": "postgres",
    "version": "unknown",
    "notes": "Legacy Fly Postgres (postgres-flex image) — unsupported by fly.io, migration to RDS/Aurora recommended"
  }],
  ...
  "_detected": ["Legacy Fly Postgres detected — database entry created, no process groups"]
}
```

---

## Notes

- **Config ≠ intent.** `fly launch` defaults to scale-to-zero (`auto_stop="stop"`, `min_machines_running=0`) — nearly every fly.toml carries this semantic, often without deliberate choice. Discover records these as signals; Clarify MUST confirm whether each is a deliberate requirement or an inherited default.
- **fly.toml is declarative only.** It does NOT contain actual machine counts, real sizes, or deployed regions. For actuals, ingest flyctl JSON exports (see discover.md Step 2d).
- **Multi-region apps:** If `primary_region` is set but multiple regions are in use (detected via flyctl exports or code), record additional regions in `network_flags.multi_region[]`.
