---
_fragment: docs
_of_phase: generate
_contributes:
  - MIGRATION_GUIDE.md
  - README.md
---

# Generate Phase: Documentation and Script Generation

> Self-contained sub-file for generating migration documentation and database/storage migration scripts.
> Produces `MIGRATION_GUIDE.md`, `README.md`, and migration scripts in `$MIGRATION_DIR`.
> Only generates procedures for data stores actually present in the design — omits absent types entirely.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Inputs Required

Before executing, the parent `generate.md` must have loaded:

1. `$MIGRATION_DIR/aws-design.json` — designed AWS architecture
2. `$MIGRATION_DIR/fly-resource-inventory.json` — source fly.io resources
3. `$MIGRATION_DIR/preferences.json` — migration preferences
4. `$MIGRATION_DIR/estimation-infra.json` — cost estimates

All four files must be valid JSON and present. If any are missing, exit cleanly — the parent orchestrator handles the GATE_FAIL.

---

## Step 0: Detect Data Store Presence

Scan `aws-design.json` to determine which data store types exist in the design:

| Check            | Condition                                                          | Flag                  |
| ---------------- | ------------------------------------------------------------------ | --------------------- |
| Postgres present | `databases[]` contains entry with `engine == "postgres"`           | `has_postgres = true` |
| MySQL present    | `databases[]` contains entry with `engine == "mysql"`              | `has_mysql = true`    |
| Redis present    | `cache[]` contains entry with `type == "redis"`                    | `has_redis = true`    |
| S3 present       | `storage[]` contains entry with `recommendation` containing `"s3"` | `has_s3 = true`       |
| EFS present      | `storage[]` contains entry with `recommendation == "efs"`          | `has_efs = true`      |

Also extract:

- `specialist_gates[]` — entries from `aws-design.json`.specialist_gates[]
- `all_compute_groups[]` — list of compute groups for README generation
- `target_region` — from `preferences.json`.global.target_region (default: `us-east-1`)
- `fly_apps[]` — list of unique app names from inventory
- `migration_approach` — from `preferences.json`.global.migration_approach (`"full_cutover"` or `"phased"`)
- `containerization_status` — from `preferences.json`.operational.containerization_status (`"containerized"`, `"buildpack_only"`, `"none"`)

---

## Step 1: Generate `MIGRATION_GUIDE.md`

Write the migration guide to `$MIGRATION_DIR/MIGRATION_GUIDE.md` using the template below.

**Critical rules:**

- Include a data migration procedure section ONLY for data store types where the corresponding flag is `true`.
- OMIT the entire section (heading and content) for data store types NOT present in the design.
- Include specialist gates as manual migration items if any exist.
- Use connection parameter placeholders (never real credentials).

### Template: MIGRATION_GUIDE.md

````markdown
# Migration Guide: Fly.io to AWS

This guide provides step-by-step instructions for migrating your fly.io application(s) to AWS.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Phase 1: Infrastructure Provisioning](#phase-1-infrastructure-provisioning)
- [Phase 2: Data Migration](#phase-2-data-migration)
- [Phase 3: Application Deployment](#phase-3-application-deployment)
- [Phase 4: Verification](#phase-4-verification)
- [Phase 5: Cutover](#phase-5-cutover)
  {{IF specialist_gates.length > 0}}
- [Manual Migration Items](#manual-migration-items)
  {{ENDIF}}

---

## Prerequisites

Before beginning the migration, ensure the following are in place:

### AWS Account Setup

- [ ] AWS account with appropriate IAM permissions for resource creation
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] Terraform >= 1.5.0 installed
- [ ] Target region selected: `{{target_region}}`

### Fly.io Access

- [ ] Fly CLI installed and authenticated (`fly auth whoami`)
- [ ] Access to source application(s): {{fly_apps_comma_separated}}
      {{IF has_postgres OR has_mysql}}
- [ ] Database connection URLs from fly.io (retrieve via `fly postgres connect -a <app>` or `fly mysql connect -a <app>`)
      {{ENDIF}}
      {{IF has_redis}}
- [ ] Redis connection URL from fly.io (from Upstash dashboard or env vars)
      {{ENDIF}}

### Network Requirements

- [ ] VPC configuration confirmed (default VPC or existing VPC ID/subnet IDs)
- [ ] Security group rules reviewed for appropriate access
- [ ] DNS records identified for cutover

### Application Preparation

- [ ] Application Docker image built and pushed to ECR (or container registry)
- [ ] Fly secrets documented (names only — values must be re-provisioned; see SECRETS_CHECKLIST.md)
- [ ] Health check endpoints identified for each service

{{IF containerization_status == "none"}}

### Containerization Prerequisites

Your application does not currently use Docker. You'll need to create a Dockerfile for Fargate/Lambda deployment.

**Common patterns:**

- **Node.js**: `FROM node:20-alpine`, `COPY package*.json ./`, `RUN npm ci --omit=dev`, `COPY . .`, `CMD ["node", "server.js"]`
- **Python**: `FROM python:3.12-slim`, `COPY requirements.txt .`, `RUN pip install --no-cache-dir -r requirements.txt`, `COPY . .`, `CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:$PORT"]`
- **Ruby**: `FROM ruby:3.3-slim`, `COPY Gemfile* ./`, `RUN bundle install --without development test`, `COPY . .`, `CMD ["bundle", "exec", "puma", "-C", "config/puma.rb"]`
- **Go**: `FROM golang:1.22 AS build`, `COPY . .`, `RUN go build -o app .`, `FROM alpine`, `COPY --from=build /app .`, `CMD ["./app"]`

**Key differences from fly.io:**

- Fly injects `PORT` automatically; set it explicitly in your Dockerfile or task definition
- Fly handles image building via `fly deploy`; on AWS use GitHub Actions or CodeBuild (see `.github/workflows/deploy-aws.yml`)
- Fly's `fly.toml` config is replaced by ECS task definitions or Lambda function configs
  {{ENDIF}}

---

## Phase 1: Infrastructure Provisioning

Apply the generated Terraform configurations to create AWS resources:

```bash
cd terraform/
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Verify all resources are created successfully:

```bash
terraform output
```

Record the output values — they are needed for data migration and application deployment.

---

## Phase 2: Data Migration

{{IF has_postgres}}

### PostgreSQL Migration (Fly Postgres → RDS/Aurora)

**Strategy:** Use `pg_dump` / `pg_restore` for a full database migration with minimal downtime.

#### Pre-Migration Steps

1. Scale fly.io machines to prevent writes during migration:

   ```bash
   fly scale count 0 --app {{app_name}}
   ```

2. Verify source database size and estimate transfer time:

   ```bash
   fly postgres connect -a {{app_name}}
   \l+
   \q
   ```

#### Execute Migration

Run the database migration script:

```bash
./scripts/migrate-postgres.sh
```

Or execute manually:

```bash
# Export from Fly Postgres
PGPASSWORD="{{SOURCE_DB_PASSWORD}}" pg_dump \
  -h {{SOURCE_DB_HOST}} \
  -p {{SOURCE_DB_PORT}} \
  -U {{SOURCE_DB_USER}} \
  -d {{SOURCE_DB_NAME}} \
  -Fc \
  --no-owner \
  --no-acl \
  --verbose \
  > fly_backup.dump

# Import to AWS RDS/Aurora
PGPASSWORD="{{TARGET_DB_PASSWORD}}" pg_restore \
  -h {{TARGET_DB_HOST}} \
  -p {{TARGET_DB_PORT}} \
  -U {{TARGET_DB_USER}} \
  -d {{TARGET_DB_NAME}} \
  --no-owner \
  --no-acl \
  --verbose \
  fly_backup.dump
```

#### Post-Migration Verification

```bash
# Connect to target and verify row counts
PGPASSWORD="{{TARGET_DB_PASSWORD}}" psql \
  -h {{TARGET_DB_HOST}} \
  -p {{TARGET_DB_PORT}} \
  -U {{TARGET_DB_USER}} \
  -d {{TARGET_DB_NAME}} \
  -c "SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

Compare row counts between source and target to confirm data integrity.

{{ENDIF}}
{{IF has_mysql}}

### MySQL Migration (Fly MySQL → RDS MySQL/Aurora MySQL)

**Strategy:** Use `mysqldump` / `mysql` for a full database migration.

#### Pre-Migration Steps

1. Scale fly.io machines to prevent writes during migration:

   ```bash
   fly scale count 0 --app {{app_name}}
   ```

2. Verify source database size:

   ```bash
   fly mysql connect -a {{app_name}}
   SELECT table_schema, SUM(data_length + index_length) / 1024 / 1024 AS 'Size (MB)' FROM information_schema.tables GROUP BY table_schema;
   ```

#### Execute Migration

```bash
# Export from Fly MySQL
mysqldump -h {{SOURCE_DB_HOST}} -P {{SOURCE_DB_PORT}} -u {{SOURCE_DB_USER}} -p{{SOURCE_DB_PASSWORD}} \
  --single-transaction --quick --lock-tables=false \
  {{SOURCE_DB_NAME}} > fly_mysql_backup.sql

# Import to AWS RDS MySQL
mysql -h {{TARGET_DB_HOST}} -P {{TARGET_DB_PORT}} -u {{TARGET_DB_USER}} -p{{TARGET_DB_PASSWORD}} \
  {{TARGET_DB_NAME}} < fly_mysql_backup.sql
```

#### Post-Migration Verification

```bash
# Verify table counts
mysql -h {{TARGET_DB_HOST}} -P {{TARGET_DB_PORT}} -u {{TARGET_DB_USER}} -p{{TARGET_DB_PASSWORD}} \
  -e "SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.tables WHERE TABLE_SCHEMA = '{{TARGET_DB_NAME}}';"
```

{{ENDIF}}
{{IF has_redis}}

### Redis Migration (Upstash Redis → ElastiCache)

**Strategy:** Export Redis data using `DUMP`/`RESTORE` for small datasets or RDB snapshot for large datasets.

#### Pre-Migration Steps

1. Check current Redis memory usage and key count:

   ```bash
   redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} -a "{{SOURCE_REDIS_PASSWORD}}" --tls INFO memory
   redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} -a "{{SOURCE_REDIS_PASSWORD}}" --tls DBSIZE
   ```

2. Determine migration approach:
   - **Small dataset (< 1 GB):** Use key-by-key `DUMP`/`RESTORE`
   - **Large dataset (≥ 1 GB):** Use RDB snapshot transfer

#### Execute Migration (Small Dataset)

```bash
./scripts/migrate-redis.sh
```

Or execute manually using `redis-cli`:

```bash
# Connect to source and dump keys
redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} \
  -a "{{SOURCE_REDIS_PASSWORD}}" --tls \
  --scan --pattern '*' | while read key; do
    redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} \
      -a "{{SOURCE_REDIS_PASSWORD}}" --tls \
      DUMP "$key" | redis-cli -h {{TARGET_REDIS_HOST}} -p {{TARGET_REDIS_PORT}} \
      -a "{{TARGET_REDIS_PASSWORD}}" --tls \
      --raw RESTORE "$key" 0 - REPLACE
done
```

#### Post-Migration Verification

```bash
# Compare key counts
echo "Source keys:" && redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} \
  -a "{{SOURCE_REDIS_PASSWORD}}" --tls DBSIZE
echo "Target keys:" && redis-cli -h {{TARGET_REDIS_HOST}} -p {{TARGET_REDIS_PORT}} \
  -a "{{TARGET_REDIS_PASSWORD}}" --tls DBSIZE
```

**Important:** Upstash uses HTTP/REST API. ElastiCache requires Redis-protocol client. Update your application code to use a Redis client library (e.g., `redis-py`, `node-redis`, `go-redis`) instead of Upstash HTTP SDK.

{{ENDIF}}
{{IF has_s3}}

### Object Storage Migration (Tigris → S3)

**Strategy:** Use `aws s3 sync` to migrate object storage.

#### Pre-Migration Steps

1. Install AWS CLI v2 (if not already installed).

2. Obtain Tigris credentials from fly.io (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL).

#### Execute Migration

```bash
./scripts/migrate-s3.sh
```

Or execute manually:

```bash
# Sync from Tigris to AWS S3
aws s3 sync s3://{{TIGRIS_BUCKET_NAME}} s3://{{AWS_S3_BUCKET_NAME}} \
  --endpoint-url {{TIGRIS_ENDPOINT_URL}} \
  --source-region auto \
  --region {{target_region}}
```

#### Post-Migration Verification

```bash
# Compare object counts
echo "Source objects:" && aws s3 ls s3://{{TIGRIS_BUCKET_NAME}} --endpoint-url {{TIGRIS_ENDPOINT_URL}} --recursive | wc -l
echo "Target objects:" && aws s3 ls s3://{{AWS_S3_BUCKET_NAME}} --recursive | wc -l
```

**Important:** Tigris egress is $0.09/GB. Budget accordingly for large object storage migrations. AWS S3 ingress is free.

{{ENDIF}}

---

## Phase 3: Application Deployment

### Build and Push Container Image

```bash
# Build Docker image
docker build -t {{app_name}}:latest .

# Tag for ECR
docker tag {{app_name}}:latest {{AWS_ACCOUNT_ID}}.dkr.ecr.{{target_region}}.amazonaws.com/{{app_name}}:latest

# Push to ECR
aws ecr get-login-password --region {{target_region}} | docker login --username AWS --password-stdin {{AWS_ACCOUNT_ID}}.dkr.ecr.{{target_region}}.amazonaws.com
docker push {{AWS_ACCOUNT_ID}}.dkr.ecr.{{target_region}}.amazonaws.com/{{app_name}}:latest
```

### Deploy to Fargate/Lambda

The Terraform configuration creates ECS services or Lambda functions automatically. After pushing the image:

**For ECS/Fargate:**

```bash
aws ecs update-service \
  --cluster {{app_name}}-cluster \
  --service {{app_name}}-web \
  --force-new-deployment \
  --region {{target_region}}
```

**For Lambda:**

```bash
aws lambda update-function-code \
  --function-name {{app_name}}-function \
  --image-uri {{AWS_ACCOUNT_ID}}.dkr.ecr.{{target_region}}.amazonaws.com/{{app_name}}:latest \
  --region {{target_region}}
```

### Update Environment Variables and Secrets

Ensure all fly.io secrets are re-provisioned in AWS (see `SECRETS_CHECKLIST.md`):

- Secrets → AWS Secrets Manager or SSM Parameter Store
- Non-sensitive config → ECS task definition environment or Lambda environment variables

ECS task definitions reference secrets via `secrets` array:

```json
"secrets": [
  {"name": "DATABASE_URL", "valueFrom": "arn:aws:ssm:{{target_region}}:{{AWS_ACCOUNT_ID}}:parameter/{{app_name}}/DATABASE_URL"}
]
```

### Release Command Mapping

Fly.io `[deploy.release_command]` in fly.toml maps to ECS one-off tasks or Lambda invocations. Run release commands BEFORE updating the main service (see `CUTOVER_RUNBOOK.md`).

---

## Phase 4: Verification

### Health Checks

- [ ] Application responds on ALB endpoint or Lambda function URL: `https://{{ALB_DNS_NAME}}/` or `https://{{LAMBDA_FUNCTION_URL}}`
- [ ] Health check endpoint returns 200: `https://{{ALB_DNS_NAME}}/health`
      {{IF has_postgres OR has_mysql}}
- [ ] Database connectivity confirmed (application can read/write)
- [ ] Row counts match source database
      {{ENDIF}}
      {{IF has_redis}}
- [ ] Redis connectivity confirmed (application can read/write cache)
- [ ] Key counts match source Redis
      {{ENDIF}}
      {{IF has_s3}}
- [ ] S3 object storage accessible from application
- [ ] Object counts match source Tigris bucket
      {{ENDIF}}

### Functional Tests

- [ ] Run application test suite against AWS deployment
- [ ] Verify critical user flows end-to-end
- [ ] Check log output in CloudWatch Logs

### Performance Baseline

- [ ] Response time within acceptable range (compare to fly.io baseline)
- [ ] No error rate increase in CloudWatch metrics
- [ ] Resource utilization (CPU/memory) within expected bounds

---

## Phase 5: Cutover

### DNS Cutover

1. Update DNS records to point to the AWS ALB or Lambda function URL:

   ```
   {{app_domain}} → CNAME → {{ALB_DNS_NAME}}
   or
   {{app_domain}} → CNAME → {{LAMBDA_FUNCTION_URL}}
   ```

2. Set TTL low (60s) before cutover, restore after verification.

### Decommission Fly.io

After successful verification (recommend 48–72 hours of parallel running):

1. Scale fly.io machines to 0:

   ```bash
   fly scale count 0 --app {{app_name}}
   ```

2. After 7 days of stable AWS operation, destroy fly.io app:

   ```bash
   fly apps destroy {{app_name}}
   ```

{{IF specialist_gates.length > 0}}

---

## Manual Migration Items

The following items require specialist engagement or manual configuration:

| Type | Name | Reason | Recommendation |
| ---- | ---- | ------ | -------------- |

<!-- markdownlint-disable MD055 MD056 -->

{{FOR gate IN specialist_gates}}
| {{gate.type}} | {{gate.name}} | {{gate.reason}} | {{gate.context || "Manual configuration required"}} |
{{ENDFOR}}

<!-- markdownlint-enable MD055 MD056 -->

### Action Required

For each specialist-gated item above:

1. Review the reason and context
2. Provision the AWS service or configure manually
3. Update application configuration to use the new service
4. Verify functionality before decommissioning fly.io resources

{{ENDIF}}
````

### Template Variable Resolution

Replace template variables using these sources:

| Variable                       | Source                                                      |
| ------------------------------ | ----------------------------------------------------------- |
| `{{target_region}}`            | `preferences.json` → `global.target_region`                 |
| `{{app_name}}`                 | First app from `fly-resource-inventory.json[0].app`         |
| `{{fly_apps_comma_separated}}` | All app names from inventory, comma-separated               |
| `{{migration_approach}}`       | `preferences.json` → `global.migration_approach`            |
| `{{containerization_status}}`  | `preferences.json` → `operational.containerization_status`  |
| `{{SOURCE_DB_*}}`              | Placeholder — user fills from `fly postgres connect` output |
| `{{TARGET_DB_*}}`              | Placeholder — user fills from Terraform output              |
| `{{SOURCE_REDIS_*}}`           | Placeholder — user fills from Upstash dashboard             |
| `{{TARGET_REDIS_*}}`           | Placeholder — user fills from Terraform output              |
| `{{TIGRIS_*}}`                 | Placeholder — user fills from fly.io Tigris config          |
| `{{AWS_ACCOUNT_ID}}`           | Placeholder — user fills with their AWS account ID          |
| `{{ALB_DNS_NAME}}`             | Placeholder — user fills from Terraform output              |
| `{{LAMBDA_FUNCTION_URL}}`      | Placeholder — user fills from Terraform output              |
| `{{app_domain}}`               | Placeholder — user fills with their application domain      |

### Conditional Section Rules

**Strict enforcement — no empty sections:**

- If `has_postgres == false`: Omit the entire "PostgreSQL Migration" subsection under Phase 2 (heading + content)
- If `has_mysql == false`: Omit the entire "MySQL Migration" subsection under Phase 2 (heading + content)
- If `has_redis == false`: Omit the entire "Redis Migration" subsection under Phase 2 (heading + content)
- If `has_s3 == false`: Omit the entire "Object Storage Migration" subsection under Phase 2 (heading + content)
- If ALL data store flags are false: Omit the entire "Phase 2: Data Migration" section and its Table of Contents entry
- If `specialist_gates.length == 0`: Omit the entire "Manual Migration Items" section and its Table of Contents entry
- Verification section (Phase 4) checkboxes: Only include data-store-specific checks for present data stores

---

## Step 2: Generate `README.md`

Write the README to `$MIGRATION_DIR/README.md` listing all generated artifacts.

### Template: README.md

````markdown
# Fly.io-to-AWS Migration Artifacts

Generated by the fly-to-aws migration skill on {{generation_timestamp}}.

## Overview

This directory contains all artifacts needed to migrate your fly.io application(s) to AWS.

**Source:** {{fly_apps_comma_separated}} (fly.io)
**Target:** AWS ({{target_region}})
**Estimated Monthly Cost:** ${{estimated_monthly_total}} USD

---

## Artifact Files

| File                               | Purpose                                                 |
| ---------------------------------- | ------------------------------------------------------- |
| `terraform/`                       | Terraform configurations for all AWS infrastructure     |
| `terraform/main.tf`                | Provider configuration and data sources                 |
| `terraform/variables.tf`           | Input variables (region, VPC, naming)                   |
| `terraform/outputs.tf`             | Output values (endpoints, ARNs, DNS names)              |
| `terraform/network.tf`             | VPC data sources and security groups                    |
| `terraform/security.tf`            | IAM roles and policies                                  |
| {{IF has_fargate OR has_lambda}}   |                                                         |
| `terraform/compute.tf`             | ECS/Fargate task definitions and services (conditional) |
| {{ENDIF}}                          |                                                         |
| {{IF has_lambda}}                  |                                                         |
| `terraform/lambda.tf`              | Lambda functions and function URLs (conditional)        |
| {{ENDIF}}                          |                                                         |
| {{IF has_postgres OR has_mysql}}   |                                                         |
| `terraform/database.tf`            | RDS/Aurora database configuration (conditional)         |
| {{ENDIF}}                          |                                                         |
| {{IF has_redis}}                   |                                                         |
| `terraform/cache.tf`               | ElastiCache Redis cluster configuration (conditional)   |
| {{ENDIF}}                          |                                                         |
| {{IF has_s3 OR has_efs}}           |                                                         |
| `terraform/storage.tf`             | S3 buckets and EFS file systems (conditional)           |
| {{ENDIF}}                          |                                                         |
| `MIGRATION_GUIDE.md`               | Step-by-step migration procedure                        |
| `README.md`                        | This file — artifact listing and quick start            |
| `SECRETS_CHECKLIST.md`             | Secrets re-provisioning checklist                       |
| `CUTOVER_RUNBOOK.md`               | Cutover procedure and rollback plan                     |
| {{IF has_postgres OR has_mysql}}   |                                                         |
| `scripts/migrate-postgres.sh`      | PostgreSQL migration script (conditional)               |
| {{ENDIF}}                          |                                                         |
| {{IF has_s3}}                      |                                                         |
| `scripts/migrate-s3.sh`            | S3 object storage migration script (conditional)        |
| {{ENDIF}}                          |                                                         |
| {{IF generation_warnings_exist}}   |                                                         |
| `generation-warnings.json`         | Resources that could not be generated                   |
| {{ENDIF}}                          |                                                         |
| `.github/workflows/deploy-aws.yml` | CI/CD deployment workflow                               |
| `.phase-status.json`               | Migration phase tracking (internal)                     |
| `fly-resource-inventory.json`      | Discovered fly.io resources (input)                     |
| `preferences.json`                 | Migration preferences (input)                           |
| `aws-design.json`                  | Designed AWS architecture (input)                       |
| `estimation-infra.json`            | Cost estimates (input)                                  |

---

## Quick Start

### 1. Review the Migration Guide

Read `MIGRATION_GUIDE.md` for the complete migration procedure including prerequisites, data migration steps, and verification.

### 2. Configure Variables

Edit `terraform/variables.tf` or create a `terraform.tfvars` file:

```hcl
aws_region   = "{{target_region}}"
environment  = "{{environment_name}}"
# VPC configuration (if not using default VPC)
# vpc_id     = "vpc-0123456789abcdef0"
# subnet_ids = ["subnet-aaa", "subnet-bbb"]
```
````

### 3. Apply Terraform

```bash
cd terraform/

# Initialize providers
terraform init

# Preview changes
terraform plan -out=tfplan

# Apply infrastructure
terraform apply tfplan

# Record outputs for data migration
terraform output > ../terraform-outputs.txt
```

### 4. Re-Provision Secrets

See `SECRETS_CHECKLIST.md` for all detected secrets. Fly.io secret VALUES cannot be exported — you must re-provision from source systems.

### 5. Migrate Data

{{IF has_postgres OR has_mysql}}

```bash
# Migrate database
./scripts/migrate-postgres.sh
```

{{ENDIF}}
{{IF has_s3}}

```bash
# Migrate object storage
./scripts/migrate-s3.sh
```

{{ENDIF}}

### 6. Deploy Application

Build and push your container image, then update ECS services or Lambda functions. See `MIGRATION_GUIDE.md` Phase 3 for details.

### 7. Verify and Cutover

Follow the verification checklist in `MIGRATION_GUIDE.md` Phase 4, then perform DNS cutover per Phase 5.

---

## Important Notes

- **Placeholders:** Connection strings and credentials use `{{PLACEHOLDER}}` format. Replace with actual values from fly.io and Terraform outputs.
- **Order matters:** Apply Terraform BEFORE running data migration scripts. The target infrastructure must exist first.
- **Backup:** Always verify backups exist before performing destructive operations on fly.io.
- **Parallel run:** Recommended 48–72 hours of parallel running before decommissioning fly.io.
  {{IF specialist_gates.length > 0}}
- **Manual items:** {{specialist_gates.length}} item(s) require manual migration. See "Manual Migration Items" in `MIGRATION_GUIDE.md`.
  {{ENDIF}}

````
### Template Variable Resolution

| Variable | Source |
|----------|--------|
| `{{generation_timestamp}}` | Current ISO 8601 timestamp |
| `{{fly_apps_comma_separated}}` | All app names from inventory |
| `{{target_region}}` | `preferences.json` → `global.target_region` |
| `{{estimated_monthly_total}}` | `estimation-infra.json` → `projected_costs.aws_monthly_balanced` |
| `{{environment_name}}` | `preferences.json` → `global.environment_naming` |
| `{{specialist_gates.length}}` | Count of entries in `aws-design.json`.specialist_gates[] |

### Conditional Section Rules

- `has_fargate`: True if any compute group routed to `fargate_*`
- `has_lambda`: True if any compute group routed to `lambda` or `lambda_microvms`
- `has_postgres`: True if `databases[]` contains Postgres
- `has_mysql`: True if `databases[]` contains MySQL
- `has_redis`: True if `cache[]` is non-empty
- `has_s3`: True if `storage[]` contains S3 recommendation
- `has_efs`: True if `storage[]` contains EFS recommendation
- `generation_warnings_exist`: True if `generation-warnings.json` was created during Terraform generation

---

## Step 3: Generate Database Migration Scripts

Generate migration scripts ONLY for data stores present in the design. Place scripts in `$MIGRATION_DIR/scripts/`.

### 3A: PostgreSQL Migration Script

**Trigger:** `has_postgres == true`

Write to `$MIGRATION_DIR/scripts/migrate-postgres.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# PostgreSQL Migration Script
# Migrates data from Fly Managed Postgres to AWS RDS/Aurora PostgreSQL
#
# Prerequisites:
#   - pg_dump and pg_restore installed (PostgreSQL client tools)
#   - Network access to both source and target databases
#   - Source and target credentials configured below
#
# Usage:
#   1. Fill in connection parameters below
#   2. Run: chmod +x migrate-postgres.sh && ./migrate-postgres.sh
###############################################################################

# ─── Source Connection (Fly Postgres) ────────────────────────────────────────
# Retrieve via: fly postgres connect -a <app_name>
SOURCE_DB_HOST="{{SOURCE_DB_HOST}}"
SOURCE_DB_PORT="{{SOURCE_DB_PORT}}"
SOURCE_DB_USER="{{SOURCE_DB_USER}}"
SOURCE_DB_PASSWORD="{{SOURCE_DB_PASSWORD}}"
SOURCE_DB_NAME="{{SOURCE_DB_NAME}}"

# ─── Target Connection (AWS RDS/Aurora) ──────────────────────────────────────
# Retrieve via: terraform output (after terraform apply)
TARGET_DB_HOST="{{TARGET_DB_HOST}}"
TARGET_DB_PORT="{{TARGET_DB_PORT}}"
TARGET_DB_USER="{{TARGET_DB_USER}}"
TARGET_DB_PASSWORD="{{TARGET_DB_PASSWORD}}"
TARGET_DB_NAME="{{TARGET_DB_NAME}}"

# ─── Configuration ───────────────────────────────────────────────────────────
BACKUP_FILE="fly_postgres_backup_$(date +%Y%m%d_%H%M%S).dump"
LOG_FILE="postgres_migration_$(date +%Y%m%d_%H%M%S).log"

# ─── Functions ───────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

check_prerequisites() {
  log "Checking prerequisites..."
  command -v pg_dump >/dev/null 2>&1 || { log "ERROR: pg_dump not found"; exit 1; }
  command -v pg_restore >/dev/null 2>&1 || { log "ERROR: pg_restore not found"; exit 1; }
  command -v psql >/dev/null 2>&1 || { log "ERROR: psql not found"; exit 1; }
  log "Prerequisites OK"
}

test_source_connection() {
  log "Testing source database connection..."
  PGPASSWORD="$SOURCE_DB_PASSWORD" psql \
    -h "$SOURCE_DB_HOST" -p "$SOURCE_DB_PORT" \
    -U "$SOURCE_DB_USER" -d "$SOURCE_DB_NAME" \
    -c "SELECT 1;" >/dev/null 2>&1 || { log "ERROR: Cannot connect to source database"; exit 1; }
  log "Source connection OK"
}

test_target_connection() {
  log "Testing target database connection..."
  PGPASSWORD="$TARGET_DB_PASSWORD" psql \
    -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" \
    -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" \
    -c "SELECT 1;" >/dev/null 2>&1 || { log "ERROR: Cannot connect to target database"; exit 1; }
  log "Target connection OK"
}

export_source() {
  log "Exporting source database to $BACKUP_FILE..."
  PGPASSWORD="$SOURCE_DB_PASSWORD" pg_dump \
    -h "$SOURCE_DB_HOST" \
    -p "$SOURCE_DB_PORT" \
    -U "$SOURCE_DB_USER" \
    -d "$SOURCE_DB_NAME" \
    -Fc \
    --no-owner \
    --no-acl \
    --verbose \
    -f "$BACKUP_FILE" 2>>"$LOG_FILE"
  log "Export complete: $(du -h "$BACKUP_FILE" | cut -f1)"
}

import_target() {
  log "Importing to target database..."
  PGPASSWORD="$TARGET_DB_PASSWORD" pg_restore \
    -h "$TARGET_DB_HOST" \
    -p "$TARGET_DB_PORT" \
    -U "$TARGET_DB_USER" \
    -d "$TARGET_DB_NAME" \
    --no-owner \
    --no-acl \
    --verbose \
    "$BACKUP_FILE" 2>>"$LOG_FILE"
  log "Import complete"
}

verify_migration() {
  log "Verifying migration..."

  SOURCE_COUNT=$(PGPASSWORD="$SOURCE_DB_PASSWORD" psql \
    -h "$SOURCE_DB_HOST" -p "$SOURCE_DB_PORT" \
    -U "$SOURCE_DB_USER" -d "$SOURCE_DB_NAME" \
    -t -c "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" | tr -d ' ')

  TARGET_COUNT=$(PGPASSWORD="$TARGET_DB_PASSWORD" psql \
    -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" \
    -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" \
    -t -c "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" | tr -d ' ')

  log "Source row count: $SOURCE_COUNT"
  log "Target row count: $TARGET_COUNT"

  if [ "$SOURCE_COUNT" == "$TARGET_COUNT" ]; then
    log "✓ Row counts match — migration verified"
  else
    log "⚠ Row count mismatch (source=$SOURCE_COUNT, target=$TARGET_COUNT)"
    log "  This may be expected if the source had writes during migration."
    log "  Review per-table counts to identify discrepancies."
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  log "=== PostgreSQL Migration Started ==="
  check_prerequisites
  test_source_connection
  test_target_connection
  export_source
  import_target
  verify_migration
  log "=== PostgreSQL Migration Complete ==="
  log "Backup file: $BACKUP_FILE"
  log "Log file: $LOG_FILE"
}

main "$@"
````

### 3B: S3 Migration Script

**Trigger:** `has_s3 == true`

Write to `$MIGRATION_DIR/scripts/migrate-s3.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# S3 Migration Script
# Migrates data from Tigris object storage to AWS S3
#
# Prerequisites:
#   - AWS CLI v2 installed
#   - Tigris credentials configured (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL)
#   - Target S3 bucket created via Terraform
#
# Usage:
#   1. Fill in connection parameters below
#   2. Run: chmod +x migrate-s3.sh && ./migrate-s3.sh
###############################################################################

# ─── Source Connection (Tigris) ──────────────────────────────────────────────
# Retrieve via: fly dashboard → Tigris
TIGRIS_BUCKET_NAME="{{TIGRIS_BUCKET_NAME}}"
TIGRIS_ENDPOINT_URL="{{TIGRIS_ENDPOINT_URL}}"
TIGRIS_ACCESS_KEY_ID="{{TIGRIS_ACCESS_KEY_ID}}"
TIGRIS_SECRET_ACCESS_KEY="{{TIGRIS_SECRET_ACCESS_KEY}}"

# ─── Target Connection (AWS S3) ──────────────────────────────────────────────
# Retrieve via: terraform output
AWS_S3_BUCKET_NAME="{{AWS_S3_BUCKET_NAME}}"
AWS_REGION="{{AWS_REGION}}"

# ─── Configuration ───────────────────────────────────────────────────────────
LOG_FILE="s3_migration_$(date +%Y%m%d_%H%M%S).log"

# ─── Functions ───────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

check_prerequisites() {
  log "Checking prerequisites..."
  command -v aws >/dev/null 2>&1 || { log "ERROR: AWS CLI not found"; exit 1; }
  log "Prerequisites OK"
}

sync_objects() {
  log "Syncing objects from Tigris to AWS S3..."
  
  AWS_ACCESS_KEY_ID="$TIGRIS_ACCESS_KEY_ID" \
  AWS_SECRET_ACCESS_KEY="$TIGRIS_SECRET_ACCESS_KEY" \
  aws s3 sync s3://"$TIGRIS_BUCKET_NAME" s3://"$AWS_S3_BUCKET_NAME" \
    --endpoint-url "$TIGRIS_ENDPOINT_URL" \
    --source-region auto \
    --region "$AWS_REGION" \
    2>&1 | tee -a "$LOG_FILE"
  
  log "Sync complete"
}

verify_migration() {
  log "Verifying migration..."

  SOURCE_COUNT=$(AWS_ACCESS_KEY_ID="$TIGRIS_ACCESS_KEY_ID" \
                AWS_SECRET_ACCESS_KEY="$TIGRIS_SECRET_ACCESS_KEY" \
                aws s3 ls s3://"$TIGRIS_BUCKET_NAME" --endpoint-url "$TIGRIS_ENDPOINT_URL" --recursive | wc -l)

  TARGET_COUNT=$(aws s3 ls s3://"$AWS_S3_BUCKET_NAME" --region "$AWS_REGION" --recursive | wc -l)

  log "Source object count: $SOURCE_COUNT"
  log "Target object count: $TARGET_COUNT"

  if [ "$SOURCE_COUNT" -eq "$TARGET_COUNT" ]; then
    log "✓ Object counts match — migration verified"
  else
    log "⚠ Object count mismatch (source=$SOURCE_COUNT, target=$TARGET_COUNT)"
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  log "=== S3 Migration Started ==="
  check_prerequisites
  sync_objects
  verify_migration
  log "=== S3 Migration Complete ==="
  log "Log file: $LOG_FILE"
  log "Note: Tigris egress is \$0.09/GB. Review AWS billing for transfer costs."
}

main "$@"
```

### 3C: No Redis Migration Script

Redis migration does NOT generate a standalone script because the DUMP/RESTORE logic is simple enough to include inline in the MIGRATION_GUIDE.md.

---

## Step 4: Set Script Permissions

After writing scripts, ensure they are executable:

```bash
chmod +x $MIGRATION_DIR/scripts/migrate-postgres.sh  # (if generated)
chmod +x $MIGRATION_DIR/scripts/migrate-s3.sh        # (if generated)
```

---

## Step 5: Validate Generated Documentation

Verify all generated files:

1. **MIGRATION_GUIDE.md** exists and:
   - Contains "Prerequisites" section
   - Contains "Phase 1: Infrastructure Provisioning" section
   - If `has_postgres`: Contains "PostgreSQL Migration" subsection
   - If `has_mysql`: Contains "MySQL Migration" subsection
   - If `has_redis`: Contains "Redis Migration" subsection
   - If `has_s3`: Contains "Object Storage Migration" subsection
   - If NOT `has_postgres`: Does NOT contain "PostgreSQL Migration" subsection
   - If NOT `has_mysql`: Does NOT contain "MySQL Migration" subsection
   - If NOT `has_redis`: Does NOT contain "Redis Migration" subsection
   - If NOT `has_s3`: Does NOT contain "Object Storage Migration" subsection
   - Contains "Verification" section with data-store-appropriate checks
   - If `specialist_gates.length > 0`: Contains "Manual Migration Items" section

2. **README.md** exists and:
   - Lists all artifact files present in `$MIGRATION_DIR`
   - Includes terraform apply command sequence
   - References correct target region
   - Includes estimated monthly cost

3. **Scripts** (if generated):
   - `scripts/migrate-postgres.sh` exists if `has_postgres`
   - `scripts/migrate-s3.sh` exists if `has_s3`
   - Scripts contain connection parameter placeholders (not real credentials)
   - Scripts are executable (`chmod +x` applied)

---

## Output Contribution

This sub-file contributes to `$MIGRATION_DIR/`:

1. `MIGRATION_GUIDE.md` — complete migration procedure
2. `README.md` — artifact listing and quick start
3. `scripts/migrate-postgres.sh` — PostgreSQL migration script (conditional)
4. `scripts/migrate-s3.sh` — S3 migration script (conditional)

The parent `generate.md` handles:

- Merging with Terraform generation output
- Generation warnings consolidation
- Phase status update and handoff gate

**Do not update `.phase-status.json` from this sub-file.**

---

## Error Handling

| Error                          | Behavior                                        | Impact                                 |
| ------------------------------ | ----------------------------------------------- | -------------------------------------- |
| Input artifact missing         | Exit cleanly, no output                         | Parent handles GATE_FAIL               |
| Template variable unresolvable | Use placeholder with `{{VARIABLE_NAME}}` format | User fills manually                    |
| No data stores in design       | Omit Phase 2 entirely from guide                | Valid — compute-only migration         |
| No specialist gates            | Omit Manual Migration Items section             | Valid — all resources mapped           |
| All data stores absent         | MIGRATION_GUIDE still generated (compute-only)  | Valid migration path                   |
| Script write failure           | Log warning, continue with remaining files      | Parent captures in generation-warnings |
