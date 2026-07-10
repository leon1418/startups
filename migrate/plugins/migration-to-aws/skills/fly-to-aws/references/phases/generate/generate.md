---
_phase: generate
_title: "Generate Migration Artifacts"
_requires_phase: estimate
_input:
  - aws-design.json
  - estimation-infra.json
  - preferences.json
  - fly-resource-inventory.json
_fragments:
  - _id: terraform
    _trigger: { _when: "the dispatch table contains any Terraform-targetable target (fargate_ecs_express, fargate_min1, lambda, lambda_microvms, batch, ecs_scheduled_task, ec2_gpu, sagemaker_endpoint)" }
    _file: phases/generate/generate-terraform.md
  - _id: docs
    _trigger: { _always: true }
    _file: phases/generate/generate-docs.md
  - _id: report
    _trigger: { _always: true }
    _file: phases/generate/generate-artifacts-report.md
_assemble:
  _file: phases/generate/generate-assemble.md
_produces:
  - { file: terraform/, _when: "compute routes include Terraform-targetable services" }
  - { file: k8s/, _when: "compute routes include eks" }
  - MIGRATION_GUIDE.md
  - README.md
  - SECRETS_CHECKLIST.md
  - CUTOVER_RUNBOOK.md
  - generation-warnings.json
  - { file: migration-report.html, _when: "the HTML report passed its validate gate and built successfully" }
_advances_to: share
_interactive: false
_exec:
  _agent: rw
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [aws-design.json, estimation-infra.json, preferences.json, fly-resource-inventory.json]
    _on_failure: _unrecoverable
  - _validate_json: [aws-design.json, estimation-infra.json, preferences.json, fly-resource-inventory.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [MIGRATION_GUIDE.md, README.md, SECRETS_CHECKLIST.md, CUTOVER_RUNBOOK.md, generation-warnings.json]
    _on_failure: _halt_and_inform
  - _assert: "terraform/main.tf (with valid provider config) OR k8s/deployment.yaml exists; terraform/variables.tf OR k8s/configmap.yaml exists; terraform/outputs.tf OR k8s/service.yaml exists"
    _on_failure: _halt_and_inform
  - _assert: "at least one domain file exists beyond the core infrastructure files"
    _on_failure: _halt_and_inform
  - _assert: "MIGRATION_GUIDE.md has Prerequisites and Verification sections; README.md lists the artifacts; SECRETS_CHECKLIST.md lists detected secrets; CUTOVER_RUNBOOK.md has DNS cutover steps"
    _on_failure: _halt_and_inform
  - _assert: "if Postgres is in the design, scripts/migrate-postgres.sh exists; if Tigris/S3 is in the design, scripts/migrate-s3.sh exists"
    _on_failure: _halt_and_inform
  - _assert: "every designed compute group, database, and storage entry is accounted for (generated or listed in generation-warnings.json)"
    _on_failure: _halt_and_inform
  - _assert: "no placeholder {{VARIABLE}} tokens remain in Terraform .tf files or K8s manifests (those belong in variables.tf / ConfigMaps as var.* references)"
    _on_failure: _halt_and_inform
_forbids_files:
  - fly-resource-inventory.json
  - preferences.json
  - aws-design.json
  - estimation-infra.json
---

# Phase 5: Generate Migration Artifacts

> Loaded by SKILL.md when `phases.estimate == "completed"` AND `phases.generate != "completed"`.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Overview

Transform the fly.io-to-AWS design into deployable artifacts. Route artifact generation based on compute targets in `aws-design.json`. Produce Terraform configurations, K8s manifests, migration scripts, documentation, and cutover runbooks.

**Inputs:**

- `$MIGRATION_DIR/aws-design.json` (from Phase 3)
- `$MIGRATION_DIR/estimation-infra.json` (from Phase 4)
- `$MIGRATION_DIR/preferences.json` (from Phase 2)
- `$MIGRATION_DIR/fly-resource-inventory.json` (from Phase 1)

**Outputs:**

- `$MIGRATION_DIR/terraform/` OR `$MIGRATION_DIR/k8s/` (depending on compute routes)
- `$MIGRATION_DIR/MIGRATION_GUIDE.md`
- `$MIGRATION_DIR/README.md`
- `$MIGRATION_DIR/scripts/` (database migration scripts, conditional)
- `$MIGRATION_DIR/generation-warnings.json` (if any services skipped)

**Shared paths:**

- `$GCP_SHARED = ${CLAUDE_PLUGIN_ROOT}/skills/gcp-to-aws/references/shared`

**Forbidden targets (never emit):**

- App Runner, Copilot, or Elastic Beanstalk resources

---

## Step 0: Validate Prerequisites

1. Read `$MIGRATION_DIR/.phase-status.json`. Validate per SKILL.md State Validation rules.
2. Confirm `phases.estimate == "completed"`. If not:

   ```
   GATE_FAIL | phase=generate | field=phases.estimate | reason=missing
   ```

3. Confirm no other core phase is `in_progress`. If violated → GATE_FAIL.
4. Set `phases.generate` to `"in_progress"` and `current_phase` to `"generate"`. Write `.phase-status.json`.
5. Read all required artifacts from `$MIGRATION_DIR/`:
   - `aws-design.json` (REQUIRED)
   - `estimation-infra.json` (REQUIRED)
   - `preferences.json` (REQUIRED)
   - `fly-resource-inventory.json` (REQUIRED)
6. Confirm all four files exist and parse as valid JSON. If any missing:

   ```
   GATE_FAIL | phase=generate | field=<filename> | reason=missing
   ```

---

## Step 1: Route Dispatch — Compute Target Analysis

Read `aws-design.json → compute`. For each process group, extract the `target` field. Build a dispatch table mapping targets to artifact types:

| target                           | artifacts                                                                                                                                     | notes                                                                    |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `fargate_ecs_express`            | Terraform ECS Express Mode service (generate-terraform.md §ECS)                                                                               | Simplified Fargate deployment with ALB wiring                            |
| `fargate_min1`                   | Terraform ECS Fargate service, min 1 task (generate-terraform.md §ECS)                                                                        | Always-on service (scale-to-zero → always-on migration)                  |
| `eks`                            | K8s manifests (Deployment/Service/HPA) (generate-terraform.md §EKS)                                                                           | User chose to reuse existing EKS cluster                                 |
| `lambda`                         | Terraform lambda + function URL (§Lambda)                                                                                                     | Serverless function model                                                |
| `lambda_microvms`                | Image + run-microvm scripting with /run /suspend /resume /terminate lifecycle-hook contract                                                   | Suspend/resume parity; per-second billing + snapshot storage $0.08/GB-mo |
| `batch`                          | Terraform Batch job definition + EventBridge rule (§Batch)                                                                                    | Batch workloads                                                          |
| `ecs_scheduled_task`             | Terraform ECS scheduled task + EventBridge rule (§ECS)                                                                                        | One-shot jobs (release tasks)                                            |
| `agentcore`                      | Pointer note: "compute decided by agent-advisor — generate its deployment via the agent-advisor skill (Gate 2 POC path); not duplicated here" | Agent-advisor verdict; AgentCore runtime managed separately              |
| `bedrock_handoff`                | Pointer note: "LLM inference use case routed to Bedrock handoff — see llm-to-bedrock skill for migration"                                     | Bedrock handoff for LLM inference                                        |
| `ec2_gpu` / `sagemaker_endpoint` | Terraform skeleton + sizing note, marked review-required                                                                                      | Specialist-gated compute; GPU sunset urgency flagged                     |

**EVERY `target` enum value in schema-aws-design-fly.md MUST have a dispatch row above.** If a target is missing from the table, log a warning to `generation-warnings.json` and skip that group.

**Bluegreen deploy strategy caveat (from fly.toml schema research):**

Fly.io disallows bluegreen deploy strategy when volumes are attached. When generating ECS task definitions for groups with `stateful_mounts[]` (from inventory), note in the task definition comment: "Bluegreen deployment not supported on fly.io when volumes attached — ECS rolling deployment used instead."

---

## Step 2: Common Artifacts (Always Generated)

Generate these artifacts regardless of compute route:

### 2A: GitHub Actions Workflow (OIDC + ECR + ECS Deploy)

Generate `.github/workflows/deploy-aws.yml`:

```yaml
name: Deploy to AWS

on:
  push:
    branches:
      - main

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS Credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Login to Amazon ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build, tag, and push image to ECR
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: <app_name>
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG

      - name: Deploy to ECS (if ECS route)
        uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition: terraform/task-def.json
          service: <service_name>
          cluster: <cluster_name>
          wait-for-service-stability: true
```

Only include the ECS deploy step if `fargate_*` targets exist in the dispatch table.

### 2B: Secrets Re-Provisioning Checklist

Generate `$MIGRATION_DIR/SECRETS_CHECKLIST.md`:

````markdown
# Secrets Re-Provisioning Checklist

Fly.io secret values **cannot be exported** via `fly secrets list` (only names are visible). You must re-provision all secrets from their source systems.

## Detected Secrets

Total secrets: <secrets.count from aws-design.json>

| Secret Name                             | Source System     | Re-Provisioning Action                     |
| --------------------------------------- | ----------------- | ------------------------------------------ |
| <list from fly-resource-inventory.json> | <infer from name> | <e.g., "Regenerate from Stripe dashboard"> |

## AWS Secrets Store

Target: <secrets.store from aws-design.json> (`ssm_parameter_store` or `secrets_manager`)

### If SSM Parameter Store (default, $0 cost):

```bash
aws ssm put-parameter \
  --name "/<app>/<SECRET_NAME>" \
  --value "<value>" \
  --type SecureString \
  --region <region>
```
````

### If Secrets Manager ($0.40/secret/month):

```bash
aws secretsmanager create-secret \
  --name "/<app>/<SECRET_NAME>" \
  --secret-string "<value>" \
  --region <region>
```

## Task Definition Integration

ECS task definitions reference secrets via `secrets` array:

```json
"secrets": [
  {"name": "DATABASE_URL", "valueFrom": "arn:aws:ssm:<region>:<account>:parameter/<app>/DATABASE_URL"}
]
```

Fly.io `secrets` → AWS SSM/Secrets Manager `valueFrom` mapping is 1:1. No code changes required if apps use `ENV['SECRET_NAME']` syntax.

````
### 2C: Data Migration Scripts

Generate data migration scripts based on `aws-design.json → databases[]` and `storage[]` entries. See `generate-docs.md` for PostgreSQL, MySQL, Redis, and S3 migration script templates.

### 2D: Cutover Runbook

Generate `$MIGRATION_DIR/CUTOVER_RUNBOOK.md`:

```markdown
# Cutover Runbook

## Pre-Cutover Checklist

- [ ] Terraform infrastructure applied successfully
- [ ] ECS services running and healthy
- [ ] Database migration complete (verify row counts)
- [ ] Secrets re-provisioned in AWS
- [ ] DNS TTL lowered to 60s (24 hours before cutover)
- [ ] All environment variables migrated to ECS task definitions
- [ ] Health check endpoints validated

## Release Command Mapping

Fly.io release commands (`[deploy.release_command]` in fly.toml) map to ECS one-off tasks:

| Fly Release Command | AWS ECS One-Off Task Command |
| ------------------- | ---------------------------- |
| <from fly.toml> | `aws ecs run-task --cluster <cluster> --task-definition <release-task-def> --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[<subnet>],securityGroups=[<sg>],assignPublicIp=DISABLED}"` |

Run release command as ECS one-off task BEFORE updating the main service.

## DNS Cutover

1. Update DNS records to point to AWS ALB:
````

<app_domain> → CNAME → <ALB_DNS_NAME>

````
2. Monitor DNS propagation:

```bash
watch -n 5 "dig <app_domain> | grep -A 1 'ANSWER SECTION'"
````

1. After 100% traffic migrated to AWS (verify via CloudWatch ALB metrics), scale fly.io machines to zero:

   ```bash
   fly scale count 0 --app <app_name>
   ```

2. After 48-72 hours of stable AWS operation, destroy fly.io machines:

   ```bash
   fly apps destroy <app_name>
   ```

## Rollback Plan

If critical issues arise on AWS:

1. Update DNS to point back to fly.io:

   ```
   <app_domain> → A → <fly_ip>
   ```

2. Scale fly.io machines back up:

   ```bash
   fly scale count <original_count> --app <app_name>
   ```

3. Verify fly.io app health before declaring rollback complete.

## Decision Records (Specialist-Gated Items)

<Insert decision records from aws-design.json → specialist_gates[] here. For each gated item, include: what was detected, why specialist engagement is needed, and manual steps required.>

````
### 2E: Generation Warnings

If any compute groups, databases, storage entries, or extensions could not be mapped to AWS resources, log them to `$MIGRATION_DIR/generation-warnings.json`:

```json
{
  "generated_at": "<ISO 8601>",
  "migration_id": "<migration_id>",
  "warnings": [
    {
      "type": "compute|database|storage|extension",
      "group_or_resource_name": "<name>",
      "target_or_source_type": "<target from aws-design.json>",
      "reason": "No Terraform/K8s resource mapping available",
      "recommendation": "Configure manually or use specialist engagement"
    }
  ],
  "total_warnings": "<count>"
}
````

---

## Step 3: Generate Terraform Configurations (if applicable)

Load `references/phases/generate/generate-terraform.md` and execute completely.

**Trigger:** If the dispatch table (Step 1) contains ANY of: `fargate_ecs_express`, `fargate_min1`, `lambda`, `lambda_microvms`, `batch`, `ecs_scheduled_task`, `ec2_gpu`, `sagemaker_endpoint`.

This produces:

- `$MIGRATION_DIR/terraform/` directory with all `.tf` files
- `$MIGRATION_DIR/generation-warnings.json` (if any services were skipped)

**Gate check after Step 3:**

- `terraform/main.tf` must exist
- `terraform/variables.tf` must exist
- `terraform/outputs.tf` must exist
- At least one domain file must exist (`compute.tf`, `database.tf`, `cache.tf`, `storage.tf`, or `network.tf`)

If gate fails: STOP. Output: "Terraform generation failed. Check generation-warnings.json for details."

---

## Step 4: Generate K8s Manifests (if applicable)

**Trigger:** If the dispatch table (Step 1) contains `eks`.

Generate K8s manifests to `$MIGRATION_DIR/k8s/`:

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <app-name>
  namespace: <namespace>
spec:
  replicas: <from aws-design.json compute.<group>.sizing or min_machines_running>
  selector:
    matchLabels:
      app: <app-name>
  template:
    metadata:
      labels:
        app: <app-name>
    spec:
      containers:
      - name: <process_group>
        image: <ECR_REGISTRY>/<app-name>:<IMAGE_TAG>
        ports:
        - containerPort: <from services[].internal_port>
        resources:
          requests:
            memory: "<memory_gb>Gi"
            cpu: "<cpu>"
          limits:
            memory: "<memory_gb × 1.5>Gi"
            cpu: "<cpu × 1.5>"
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: <app-name>-secrets
              key: DATABASE_URL
---
apiVersion: v1
kind: Service
metadata:
  name: <app-name>
  namespace: <namespace>
spec:
  selector:
    app: <app-name>
  ports:
  - protocol: TCP
    port: 80
    targetPort: <internal_port>
  type: LoadBalancer
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: <app-name>
  namespace: <namespace>
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: <app-name>
  minReplicas: <min_machines_running or 1>
  maxReplicas: <min_machines_running × 10 or 10>
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

Generate one Deployment/Service/HPA set per process group routed to `eks`.

**Gate check after Step 4:**

- `k8s/deployment.yaml` must exist
- `k8s/service.yaml` must exist
- `k8s/hpa.yaml` must exist (if auto-scaling enabled)

If gate fails: STOP. Output: "K8s manifest generation failed."

---

## Step 5: Generate Documentation and Scripts

Load `references/phases/generate/generate-docs.md` and execute completely.

This produces:

- `$MIGRATION_DIR/MIGRATION_GUIDE.md`
- `$MIGRATION_DIR/README.md`
- `$MIGRATION_DIR/scripts/migrate-postgres.sh` (if Postgres in design)
- `$MIGRATION_DIR/scripts/migrate-s3.sh` (if Tigris/S3 in design)

**Gate check after Step 5:**

- `MIGRATION_GUIDE.md` must exist
- `README.md` must exist

If gate fails: STOP. Output: "Documentation generation incomplete. MIGRATION_GUIDE.md or README.md missing."

---

## Step 5.5: Generate HTML Report

**You MUST run this step — do not skip it to reach Step 6 faster.** Load
`references/phases/generate/generate-artifacts-report.md` and execute it completely. It
produces `$MIGRATION_DIR/migration-report.html` (self-contained executive summary +
appendix) and opens it in the browser.

Scope of "non-blocking" (what may legitimately end without a report file — none of these
is "skip the step"):

- The report runs its own validate gate (`references/shared/validate-fly-report.md`, Step 0).
  If validation emits `GATE_FAIL`: log the failure to the user, do NOT write
  `migration-report.html`, do NOT patch artifacts to pass, and continue to Step 6.
- If the HTML build genuinely errors _after_ `VALIDATE_OK`: warn and continue.
- If the browser `open`/`xdg-open` fails: print the `file://` path and continue.

In all other cases the report IS written. **Step 6 records whether it exists** — a missing
report with no logged GATE_FAIL/build-error means Step 5.5 was skipped; go back and run it.
No gate check _blocks_ Step 6 on the report, but Step 6 must not pass silently over a report
that was never attempted.

---

## Step 6: Validate Complete Artifact Set

Validate the complete set of generated artifacts against the fly-native checklist below. (Do NOT load `$GCP_SHARED/validate-artifacts.md` here — that shared checklist's required checks include gcp-only artifacts, notably `generation-infra.json` when `estimation-infra.json` exists, which fly never produces; running it would GATE_FAIL every fly Generate. fly generates infrastructure directly, so this Step-6 list IS the authoritative artifact-set gate.)

Verify:

1. `terraform/main.tf` OR `k8s/deployment.yaml` — infrastructure configuration
2. `terraform/variables.tf` OR `k8s/configmap.yaml` — variables/config
3. `terraform/outputs.tf` OR `k8s/service.yaml` — outputs/services
4. Domain-specific files (per design content)
5. `MIGRATION_GUIDE.md` — step-by-step migration procedure
6. `README.md` — artifact listing and quick start
7. Database/storage migration scripts (conditional on design content)
8. `SECRETS_CHECKLIST.md` — secrets re-provisioning checklist
9. `CUTOVER_RUNBOOK.md` — cutover procedure
10. `generation-warnings.json` (if any services were skipped)
11. `.github/workflows/deploy-aws.yml` — CI/CD workflow
12. `migration-report.html` — self-contained HTML report. Confirm Step 5.5 ran: the file
    should exist UNLESS the report's own validate gate emitted `GATE_FAIL` or the build
    errored (either logged to the user this run). A missing report with no such logged
    reason means Step 5.5 was skipped — go back and run it.

**Cross-reference checks:**

- Every compute group in `aws-design.json.compute.<group>` is either generated OR listed in `generation-warnings.json`
- Every database in `aws-design.json.databases[]` is either generated OR listed in `generation-warnings.json`
- Every storage entry in `aws-design.json.storage[]` is either generated OR listed in `generation-warnings.json`
- `README.md` references all files that actually exist
- `MIGRATION_GUIDE.md` data migration sections match design content (no empty sections)

---

## Completion Handoff Gate (Fail Closed)

Load `$GCP_SHARED/handoff-gates.md` for the fail-closed **protocol only** (GATE_FAIL line format, HANDOFF_OK emission, re-entry rules). Ignore its generate-phase pointer to `validate-artifacts.md` — the fly-native checks below are the authoritative gate (that shared table requires gcp-only artifacts fly never produces). **Re-read from disk** before checking.

**Checks (all must PASS):**

1. `terraform/main.tf` OR `k8s/deployment.yaml` exists with valid configuration
2. `terraform/variables.tf` OR `k8s/configmap.yaml` exists
3. `terraform/outputs.tf` OR `k8s/service.yaml` exists
4. At least one domain file exists beyond core files
5. `MIGRATION_GUIDE.md` exists with Prerequisites and Verification sections
6. `README.md` exists with artifact listing
7. `SECRETS_CHECKLIST.md` exists with all detected secrets listed
8. `CUTOVER_RUNBOOK.md` exists with DNS cutover steps
9. If Postgres in design → `scripts/migrate-postgres.sh` exists
10. If Tigris/S3 in design → `scripts/migrate-s3.sh` exists
11. Every designed compute group/database/storage accounted for (generated or in warnings)
12. No placeholder `{{VARIABLE}}` in Terraform `.tf` files or K8s manifests (those belong in `variables.tf` / ConfigMaps as proper `var.*` references)

**On any FAIL:** Emit `GATE_FAIL | phase=generate | field=<path> | reason=<missing|invalid>`. STOP.

**On PASS:** Emit `HANDOFF_OK | phase=generate | artifacts=terraform/,k8s/,MIGRATION_GUIDE.md,README.md,SECRETS_CHECKLIST.md,CUTOVER_RUNBOOK.md`.

---

## Step 7: Update Phase Status

Only after `HANDOFF_OK`. Use the Phase Status Update Protocol (read-merge-write):

1. Read current `.phase-status.json` from disk.
2. Set `phases.generate` to `"completed"`.
3. Set `current_phase` to `"complete"`.
4. Update `last_updated` to current ISO 8601 timestamp.
5. Write the full file.

Output to user:

```
Generate phase complete.

Artifacts produced:
• terraform/ OR k8s/ — Infrastructure configuration
• MIGRATION_GUIDE.md — Step-by-step migration procedure
• README.md — Artifact listing and quick start
• SECRETS_CHECKLIST.md — Secrets re-provisioning checklist
• CUTOVER_RUNBOOK.md — Cutover procedure and rollback plan
• scripts/ — Database/storage migration scripts
• .github/workflows/ — CI/CD pipeline
[• generation-warnings.json — N item(s) require manual setup]
[• migration-report.html — self-contained HTML report]

Migration planning is complete. All artifacts are in $MIGRATION_DIR/.
```

Then, mirroring the report state (include only the matching line):

- If `migration-report.html` exists: "Your migration report is ready at $MIGRATION_DIR/migration-report.html — open it in a browser for the executive summary and detailed appendix."
- If `migration-report.html` is missing: "Markdown documentation is available at $MIGRATION_DIR/MIGRATION_GUIDE.md and $MIGRATION_DIR/README.md. (HTML report generation is optional and non-blocking.)"

After this output, SKILL.md handles the post-Generate share prompt and share finalization.

---

## Output Files

**Generate phase writes to `$MIGRATION_DIR/`. Required outputs:**

1. `.phase-status.json` — updated per Step 7
2. `terraform/` OR `k8s/` — complete infrastructure configuration directory
3. `MIGRATION_GUIDE.md` — migration procedure
4. `README.md` — artifact overview
5. `SECRETS_CHECKLIST.md` — secrets re-provisioning checklist
6. `CUTOVER_RUNBOOK.md` — cutover procedure

**Conditional outputs:**

- `scripts/migrate-postgres.sh` — when Postgres in design
- `scripts/migrate-s3.sh` — when Tigris/S3 in design
- `generation-warnings.json` — when any services skipped
- `.github/workflows/deploy-aws.yml` — CI/CD workflow

---

## Error Handling

| Error Category                           | Behavior                                  | Status Transition      |
| ---------------------------------------- | ----------------------------------------- | ---------------------- |
| Predecessor phase incomplete             | GATE_FAIL, halt                           | Remain `pending`       |
| Input artifact missing/invalid           | GATE_FAIL, halt                           | Retain `in_progress`   |
| Terraform/K8s generation partial failure | Log to generation-warnings.json, continue | Continue `in_progress` |
| Documentation generation failure         | GATE_FAIL at Step 5 gate                  | Retain `in_progress`   |
| Handoff gate check fails                 | Halt pipeline, surface diagnostic         | Retain `in_progress`   |

---

## Scope Boundary

**This phase covers artifact generation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-designing or changing AWS service selections (Phase 3 decisions are final)
- Re-estimating costs (Phase 4 estimates are final)
- Asking the user additional clarification questions (Phase 2 is done)
- Discovering new fly.io resources (Phase 1 is done)
- Plan sharing (Phase 6 / the Share checkpoint handles this)

**Your ONLY job: Transform the design into deployable artifacts. Nothing else.**
