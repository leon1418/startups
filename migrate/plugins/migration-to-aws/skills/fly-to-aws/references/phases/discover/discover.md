---
_phase: discover
_title: "Discover fly.io Resources"
_init: true
_input: workspace
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - fly-resource-inventory.json
_advances_to: clarify
_interactive: false
_exec:
  _agent: rw
_re_entry_guard:
  _stale_if_completed: clarify
  _stale_artifact: preferences.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _assert: "at least one fly.toml file exists in the workspace, OR Fly code signals (api.machines.dev, flyio/ images, FLY_* env vars) are present"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: fly-resource-inventory.json
    _on_failure: _halt_and_inform
  - _validate_json: fly-resource-inventory.json
    _on_failure: _halt_and_inform
  - _assert: "fly-resource-inventory.json has at least one app entry, and each app has app, primary_region, process_groups, volumes, databases, object_storage, extensions, network_flags, actuals, _detected fields"
    _on_failure: _halt_and_inform
  - _assert: "every process group has name, command, vm, scaling, flags, services; and flags has agent_candidate, agent_evidence, gpu, one_shot, stateful_mounts"
    _on_failure: _halt_and_inform
  - _assert: "actuals.source is either 'flyctl_export' or 'declared_only'"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - discovery-summary.md
  - "*.txt"
  - "terraform/**"
  - "k8s/**"
---

# Phase 1: Discover fly.io Resources

Lightweight orchestrator that delegates to domain-specific discoverers. Each sub-discovery file is self-contained — it scans for its own input, processes what it finds, and exits cleanly if nothing is relevant.
**Execute ALL steps in order. Do not skip or deviate.**

## Sub-Discovery Files

- **discover-flytoml.md** → fly.toml parsing (primary): sections, process groups, services, mounts, VMs, statics, checks
- **discover-code-signals.md** → Code grep signals: 6PN, fly-replay, Machines API, agent frameworks, Tigris, MPG, Upstash, extensions

All sub-discoveries contribute to a single `fly-resource-inventory.json` artifact.

**Note:** Platform API discovery is NOT supported in v1. No API calls are made. Discovery is entirely file-based (fly.toml + code + optional flyctl JSON exports).

---

## Phase Status State Machine

### Valid Transitions

```
pending → in_progress → completed
```

Status NEVER goes backward under normal operation. Only an **unrecoverable error** reverts the current phase to `pending`.

### Phase Gate Rules (Fail Closed)

**Rule 1 — Predecessor gate:** A phase may transition to `in_progress` ONLY when its immediate predecessor phase has status `completed`. The ordered phase list is:

```
discover → clarify → design → estimate → generate
```

- `discover` has no predecessor — it may always start.
- `clarify` requires `phases.discover == "completed"`.
- `design` requires `phases.clarify == "completed"`.
- `estimate` requires `phases.design == "completed"`.
- `generate` requires `phases.estimate == "completed"`.

If the predecessor is not `completed`, emit:

```
GATE_FAIL | phase=<target_phase> | field=phases.<predecessor> | reason=missing
```

Do NOT advance. Do NOT modify `.phase-status.json`. Tell the user which prior phase must complete first.

**Rule 2 — Single active phase:** At most one core phase (discover, clarify, design, estimate, generate) may be `in_progress` at any time. If another phase is already `in_progress`, emit:

```
GATE_FAIL | phase=<target_phase> | field=phases.<active_phase> | reason=invalid
```

**Rule 3 — GATE_FAIL halt behavior:** When any handoff gate check fails at phase completion:

1. Retain the failing phase's status as `in_progress` — do NOT revert it.
2. Do NOT advance `current_phase`.
3. Do NOT modify any artifacts to force the gate to pass.
4. Surface a diagnostic to the user identifying:
   - The phase that failed (`phase=<name>`)
   - The specific field or artifact that failed (`field=<dotted.path>`)
   - The failure reason (`reason=missing|invalid|stale_downstream`)
5. Tell the user: "Re-run Phase N (phase name) to produce the missing field, then continue."

**Rule 4 — Unrecoverable error behavior:** When a phase fails during execution due to an unrecoverable error (e.g., no fly.toml AND no Fly signals found, corrupted state file, critical sub-discovery failure that blocks all outputs):

1. Revert that phase's status to `pending` in `.phase-status.json`.
2. Preserve all artifacts and status values from prior completed phases — do NOT touch them.
3. Surface a diagnostic to the user identifying:
   - The failed phase
   - The error category (e.g., `no_sources`, `state_corrupted`)
   - Actionable guidance on how to resolve

**Rule 5 — Phase re-entry:** See `$GCP_SHARED/handoff-gates.md` re-entry table (`$GCP_SHARED = ${CLAUDE_PLUGIN_ROOT}/skills/gcp-to-aws/references/shared`). Re-running a phase after downstream phases completed requires explicit user confirmation; downstream phases must be reset to `"pending"`.

---

## Step 0: Initialize Migration State

1. Check for existing `.migration/` directory at the project root.
   - **If existing runs found:** List them with their phase status and ask:
     - `[A] Resume: Continue with [latest run]`
     - `[B] Fresh: Create new migration run`
     - `[C] Cancel`
   - **If resuming:** Set `$MIGRATION_DIR` to the selected run's directory. Read its `.phase-status.json` and validate per the State Machine in SKILL.md. If `phases.discover` is already `completed`, check re-entry rules (Rule 5).
   - **If fresh or no existing runs:** Continue to step 2.

2. Create `.migration/[MMDD-HHMM]/` directory (e.g., `.migration/0709-1430/`) using current timestamp (MMDD = month/day, HHMM = hour/minute). Set `$MIGRATION_DIR` to this new directory.

3. Create `.migration/.gitignore` file (if not already present) with exact content:

   ```
   # Auto-generated migration state (temporary, do not commit)
   *
   !.gitignore
   ```

   This prevents accidental commits of migration artifacts.

4. Write `.phase-status.json` with exact schema:

   ```json
   {
     "migration_id": "[MMDD-HHMM]",
     "last_updated": "[ISO 8601 timestamp]",
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

   Schema reference: `shared/schema-phase-status.md`.

5. Confirm both `.migration/.gitignore` and `.phase-status.json` exist before proceeding to Step 1.

---

## Step 1: Validate Prerequisites and Scan for Input Sources

### 1a. Check for fly.toml files (PRIMARY)

Glob for: `**/fly.toml`, `**/fly.*.toml` (app-specific variants like fly.production.toml).

- If found → Mark fly.toml discovery as enabled. This is the primary discovery path.
- If not found → Log: "No fly.toml files found."

### 1b. Check for Dockerfile / Procfile (SUPPLEMENTARY)

Search for: `Dockerfile`, `Dockerfile.*`, `Procfile` at workspace root or in subdirectories.

- If found → Mark build artifact discovery as enabled. These supplement fly.toml with build and process command details.
- If not found → Log: "No Dockerfile or Procfile found — build instructions will be minimal."

### 1c. Check for flyctl JSON exports (OPTIONAL)

Glob for: `**/*machines*.json`, `**/*volumes*.json`, `**/*ips*.json` (user-provided exports from `fly machines list --json`, `fly volumes list --json`, `fly ips list --json`).

- If found → Mark flyctl export ingestion as enabled. These provide actuals (real machine counts, sizes, region spread).
- If not found → Log: "No flyctl JSON exports found — inventory will be based on fly.toml declarations only."

### 1d. Check for billing data (OPTIONAL)

Glob for: `**/*billing*.csv`, `**/*invoice*.csv`, `**/*billing*.json`, `**/*invoice*.json`, `**/*fly*.csv`

- If found → Mark billing discovery as enabled.
- If not found → Log: "No billing files found — skipping billing discovery."

### 1e. Source validation gate

**If NO fly.toml files found** (regardless of whether Dockerfile/Procfile exist):

Check for Fly code signals (run a quick grep scan):

- `api.machines.dev` in any source file
- `flyio/` Docker image references
- `FLY_MACHINE_ID`, `FLY_APP_NAME`, or other Fly env vars in code

**If fly.toml missing AND no Fly code signals found:**

1. Apply **unrecoverable error behavior** (Rule 4):
   - Revert `phases.discover` to `"pending"` in `.phase-status.json`.
   - Preserve all other phase statuses unchanged.
2. STOP and output: "No fly.toml or Fly signals detected. fly.toml is required for declarative discovery. Machines-API-only repos without fly.toml are not supported in v1."

**If fly.toml missing BUT Machines-API usage detected** (`api.machines.dev` in code):

Do NOT hard-stop. Continue to Step 2 with the agent-candidate edge case (see Step 2c).

---

## Step 2: Run Sub-Discoveries

Execute applicable sub-discoveries in order. Each produces its contribution to the inventory.

**2a. fly.toml Discovery (PRIMARY):**

If fly.toml files found → Load `references/phases/discover/discover-flytoml.md`

This produces:

- Per-app inventory entries from fly.toml parsing
- Process groups from `[processes]` section (or single `app` group if absent)
- VM presets, scaling configs, services, mounts, statics, checks
- Multiple fly.tomls → one inventory entry per app
- Special case: fly.toml with `image = "flyio/postgres-flex*"` → database entry, not process group

**2b. Code Signals Discovery (ALWAYS):**

Load `references/phases/discover/discover-code-signals.md`

This produces:

- `network_flags` (fly-replay, 6PN static/dynamic, multi-region, UDP, raw TCP)
- `flags.agent_candidate` and evidence list (Machines API, agent frameworks, Sprites)
- `databases` entries (MPG, legacy Postgres detection)
- `object_storage` entries (Tigris detection)
- `extensions` entries (Upstash Redis/Vector, Sentry, Arcjet)
- GPU detection and urgency banner trigger

**2c. Edge case: No fly.toml + Machines API detected:**

If Step 1e found Machines-API usage but no fly.toml:

1. Write a minimal inventory with one synthetic process group:

   ```json
   {
     "app": "detected-machines-api-usage",
     "primary_region": "unknown",
     "process_groups": [{
       "name": "machines-api-caller",
       "command": null,
       "vm": { "preset": "unknown", "memory_mb": null },
       "scaling": { "auto_stop": null, "auto_start": null, "min_machines_running": null },
       "flags": {
         "agent_candidate": true,
         "agent_evidence": [
           "Machines API usage detected in code — likely AI agent sandbox workload"
         ],
         "gpu": false,
         "one_shot": false,
         "stateful_mounts": []
       },
       "services": []
     }],
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
     "actuals": { "source": "declared_only", "machines": [] },
     "_detected": ["Machines API usage — no fly.toml — synthetic agent_candidate group created"]
   }
   ```

2. Mark all other discovery as detect-only.
3. Output to user: "Declarative discovery needs fly.toml. The Machines-API portion can route to agent-advisor; the rest is detect-only."
4. Continue to Step 3 (assembly).

**2d. flyctl JSON Export Ingestion (OPTIONAL, inline):**

If flyctl JSON exports found (Step 1c):

Parse and fill `actuals` section:

- `actuals.source = "flyctl_export"`
- `actuals.machines = [...]` with real machine IDs, regions, sizes, states from `fly machines list --json`
- Merge volumes actuals from `fly volumes list --json`
- Merge IPs from `fly ips list --json` into `network_flags`

If not found: `actuals.source = "declared_only"`, `actuals.machines = []`

**2e. Billing Discovery (OPTIONAL, inline):**

If billing files found (Step 1d):

Parse invoices/exports and add `billing_profile` section to inventory:

- `available: true`
- `total_monthly_cost`, `currency`, `billing_period`
- `line_items: [...]` per-resource costs if available

If not found: `billing_profile.available = false`

---

## Step 3: Assemble Inventory

After all sub-discoveries complete, assemble `fly-resource-inventory.json` in `$MIGRATION_DIR/`.

**Schema reference**: `shared/schema-discover-fly.md` — consult for complete field definitions, per-type config schemas, and validation checklist.

### Assembly Rules

1. Each fly.toml produces one inventory entry in the root-level array (multi-app support).
2. Each inventory entry MUST have: `app`, `primary_region`, `process_groups`, `volumes`, `databases`, `object_storage`, `extensions`, `network_flags`, `actuals`, `_detected`.
3. Each process group MUST have: `name`, `command`, `vm`, `scaling`, `flags`, `services`.
4. `flags` MUST include: `agent_candidate` (boolean), `agent_evidence` (array), `gpu` (boolean), `one_shot` (boolean), `stateful_mounts` (array).
5. `network_flags` MUST include: `fly_replay`, `sixpn_dynamic`, `multi_region`, `udp`, `raw_tcp`.
6. `actuals.source` enum: `"flyctl_export"` or `"declared_only"`.
7. `_detected` array: human-readable strings describing what signals were found.

**If assembly fails** (no valid inventory entries after sub-discoveries ran):

Apply **unrecoverable error behavior** (Rule 4):

- Revert `phases.discover` to `"pending"`.
- Preserve prior completed phases.
- STOP and output: "Discovery ran but produced no valid resources. Check that your input files contain valid fly.io configuration and try again."

---

## Step 4: Determinism Boundary Note

**Critical:** All detections in this phase are **best-effort LLM interpretation** of code and config files, NOT deterministic facts. They become inputs to the deterministic routing engine in Phase 3 (Design), so a wrong detection silently biases routing.

**Mitigation:**

1. Only write a signal you can detect with **high confidence** — when unsure, omit it and let Clarify ask.
2. Always present detected signals to the user as **"detected: X (correct me if wrong)"** so they have a correction opportunity before routing runs.

This is the one point where LLM interpretation enters the otherwise deterministic pipeline.

---

## Step 5: Check Outputs

Verify required artifacts exist in `$MIGRATION_DIR/`:

1. `fly-resource-inventory.json` — MUST exist with at least one app entry.
2. `.phase-status.json` — MUST exist and be valid JSON with correct schema.

**Route output gates (fail closed):**

- If fly.toml discovery ran → inventory MUST contain at least one app with non-empty `process_groups`.
- If code signals discovery ran → inventory MUST contain `_detected` array (may be empty if no signals found).
- If flyctl JSON exports found → inventory MUST have `actuals.source = "flyctl_export"` and non-empty `actuals.machines`.
- If billing discovery ran → inventory MUST contain a `billing_profile` section with `available: true`.
- If any triggered route is missing its required contribution: STOP and output which sub-discovery failed.

---

## Completion Handoff Gate (Fail Closed)

Load `$GCP_SHARED/handoff-gates.md`. **Re-read from disk** every artifact below before checking.

**Re-entry guard:** If `preferences.json` exists AND `phases.clarify` is `"completed"`: STOP unless the user explicitly confirms re-running Discover. Emit:

```
GATE_FAIL | phase=discover | field=preferences.json | reason=stale_downstream
```

**Checks (all must PASS):**

1. `fly-resource-inventory.json` exists with at least one app entry.
2. Each app has `app`, `primary_region`, `process_groups`, `volumes`, `databases`, `object_storage`, `extensions`, `network_flags`, `actuals`, `_detected` fields.
3. Each process group has `name`, `command`, `vm`, `scaling`, `flags`, `services` fields.
4. Each process group's `flags` has `agent_candidate`, `agent_evidence`, `gpu`, `one_shot`, `stateful_mounts` fields.
5. Each app's `network_flags` has `fly_replay`, `sixpn_dynamic`, `multi_region`, `udp`, `raw_tcp` fields.
6. `actuals.source` is either `"flyctl_export"` or `"declared_only"`.
7. Route output gates from Step 5 all pass.

**On any FAIL:** Emit `GATE_FAIL | phase=discover | field=<path> | reason=<missing|invalid|stale_downstream>`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user which sub-discovery to re-run.

**On PASS:** Emit `HANDOFF_OK | phase=discover | artifacts=fly-resource-inventory.json,.phase-status.json`.

---

## Step 6: Update Phase Status

Only after `HANDOFF_OK`. In the **same turn** as the output message below, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json`:

1. Read current `.phase-status.json` from disk.
2. Set `phases.discover` to `"completed"`.
3. Set `current_phase` to `"clarify"`.
4. Update `last_updated` to current ISO 8601 timestamp.
5. Keep all other phase values unchanged.
6. Write the full file.

Output to user — build message from inventory contents:

- "Discovered X app(s) with Y total process groups."
- If GPU detected: "⚠️ GPU Machines deprecated — hard sunset 2026-08-01. GPU-to-AWS routing available."
- If agent_candidate groups detected: "Detected Z agent-candidate group(s) (Machines API / agent framework evidence)."
- If fly-replay detected: "⚠️ fly-replay header detected — highest-effort networking flag (no AWS LB equivalent)."
- If 6PN dynamic detected: "⚠️ Dynamic 6PN service discovery detected — code rewrite required."
- If billing data available: "Parsed billing data ($N/month)."
- If flyctl exports ingested: "Ingested actuals from flyctl JSON exports (M machines)."
- If stateful mounts detected: "Detected P volume(s) — de-volume/EFS/ECS-on-EC2 decision needed."

Format: "Discover phase complete. [artifact summaries] **Detected signals:** [list all `_detected` strings with '(correct me if wrong)' suffix]. Next required step: Phase 2 — Clarify. Load `references/phases/clarify/clarify.md` now. Do not load Design, Estimate, or Generate until Clarify completes and `.phase-status.json` marks `phases.clarify` as `completed`."

---

## Output Files

**Discover phase writes files to `$MIGRATION_DIR/`. Required outputs:**

1. `.phase-status.json` — phase tracking (initialized in Step 0, updated in Step 6)
2. `fly-resource-inventory.json` — flat resource inventory per-app

**Optional outputs (depending on available sources):**

- Billing profile embedded in inventory (not a separate file)

**No other files must be created:**

- No README.md
- No discovery-summary.md
- No EXECUTION_REPORT.txt
- No discovery-log.md
- No documentation or report files

All user communication via output messages only.

---

## Error Handling

| Error Category                           | Behavior                                                     | Status Transition             |
| ---------------------------------------- | ------------------------------------------------------------ | ----------------------------- |
| No fly.toml AND no Fly code signals      | STOP, surface diagnostic                                     | Revert to `pending` (Rule 4)  |
| No fly.toml BUT Machines-API detected    | Create synthetic agent_candidate group, continue detect-only | Continue `in_progress`        |
| fly.toml parse error (malformed TOML)    | Log warning, skip malformed sections, continue               | Continue `in_progress`        |
| Dockerfile/Procfile parse error          | Record warning, continue                                     | Continue `in_progress`        |
| flyctl JSON export parse error           | Log warning, fall back to `declared_only`, continue          | Continue `in_progress`        |
| All sub-discoveries produce no resources | STOP, surface diagnostic                                     | Revert to `pending` (Rule 4)  |
| `.phase-status.json` invalid JSON        | STOP, surface diagnostic                                     | N/A (state corrupted)         |
| Handoff gate check fails (GATE_FAIL)     | Halt pipeline, surface diagnostic                            | Retain `in_progress` (Rule 3) |
| Downstream artifacts stale (re-entry)    | Halt, emit GATE_FAIL stale_downstream                        | Retain `in_progress` (Rule 3) |

---

## Scope Boundary

**This phase covers fly.io Discovery ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons
- Effort estimates

**Your ONLY job: Inventory what exists on fly.io. Nothing else.**
