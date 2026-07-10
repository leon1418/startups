# Code-Level Grep Signals

**Self-contained signal detector.** Scans source code for Fly-specific patterns that inform routing decisions.

**Conservatism rule:** Only write a signal you can detect with **high confidence**. When unsure, omit it — wrong signals silently bias routing. Let Clarify ask instead.

---

## Signal Catalog

Each signal has: pattern (exact grep/regex), confidence threshold, and inventory effect.

### S1: fly-replay Header

**Pattern:** `fly-replay` (case-insensitive string match in source files)

**Inventory effect:**

- Set `network_flags.fly_replay = true`
- Add to `_detected`: "fly-replay header usage detected — highest-effort networking flag (no AWS LB equivalent)"

**Confidence:** HIGH (string match is unambiguous in HTTP header context)

**Note:** This is the **highest-effort networking flag**. fly-replay (Fly's response-driven request replay to another region) has NO AWS LB equivalent. Rewrite options: app-level proxy/redirect, ALB+Lambda router, CloudFront Functions. Design phase emits decision records + specialist gate; Generate does NOT produce rewrite code (v1).

**Grep command:**

```bash
grep -ri "fly-replay" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
```

---

### S2: 6PN Static Service Discovery

**Pattern:** `.internal` / `.flycast` / `fdaa:` (IPv6 prefix) / `FLY_PRIVATE_IP` env var

**Inventory effect:**

- Add to `_detected`: "6PN static service discovery detected (.internal / .flycast / fdaa: / FLY_PRIVATE_IP) — ECS Service Connect / Cloud Map can replace"

**Confidence:** HIGH (Fly-specific DNS suffixes and IPv6 prefix)

**Note:** Static forms (hardcoded `.internal` or `.flycast` hostnames) map to ECS Service Connect / Cloud Map / Route53 private zones. These are replaceable patterns.

**Grep commands:**

```bash
grep -ri "\.internal" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
grep -ri "\.flycast" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
grep -ri "fdaa:" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
grep -ri "FLY_PRIVATE_IP" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
```

---

### S3: 6PN Dynamic Service Discovery

**Pattern:** `top\d+\.nearest\.of` (regex) / `_apps\.internal` (TXT record query)

**Inventory effect:**

- Set `network_flags.sixpn_dynamic = true`
- Add to `_detected`: "6PN dynamic service discovery detected (topN.nearest.of / _apps.internal) — NO AWS equivalent, code rewrite required"

**Confidence:** HIGH (Fly-specific dynamic DNS patterns)

**Note:** These forms enable multi-region nearest-instance discovery and app enumeration. AWS has NO equivalent — static discovery only. Requires **code rewrite** (hardcode endpoints, use parameter store, or build custom service registry). This is a **code-rewrite flag**.

**Grep commands:**

```bash
grep -Eri "top[0-9]+\.nearest\.of" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
grep -ri "_apps\.internal" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
```

---

### S4: Machines API Usage

**Pattern:** `api.machines.dev` (API endpoint) OR imports from machines-API client libraries

**Inventory effect:**

- Set `flags.agent_candidate = true` on the calling process group
- Add to `agent_evidence`: "Machines API usage detected — likely dynamic sandbox orchestration (AI agent candidate)"

**Confidence:** HIGH (API endpoint is unambiguous; client library imports are package-specific)

**Client library patterns:**

- Python: `from flyio import machines` or `import flyio`
- JavaScript/TypeScript: `@fly/machines` or `@fly/platform-client`
- Go: `github.com/superfly/fly-go/machine`
- Ruby: `fly-ruby` gem

**Note:** Machines-API usage indicates **dynamic orchestration** (create/stop/exec on-demand). This is a strong signal for agent/sandbox workloads. Routes to AgentCore Runtime (if agent) / Lambda MicroVMs (if custom sandboxes) / ECS Fargate (fallback).

**Grep commands:**

```bash
grep -ri "api\.machines\.dev" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
grep -ri "from flyio import machines" --include="*.py" .
grep -ri "@fly/machines" --include="*.js" --include="*.ts" --include="package.json" .
grep -ri "github.com/superfly/fly-go" --include="*.go" --include="go.mod" .
```

---

### S5: Agent Frameworks

**Pattern:** Imports/dependencies for agent orchestration frameworks

**Inventory effect:**

- Set `flags.agent_candidate = true` on the process group
- Add specific framework to `agent_evidence`: "Framework: `<name>` — agent orchestration detected"

**Confidence:** HIGH (package imports are unambiguous)

**Framework list (same catalog as agent-advisor discover.md):**

| Framework         | Language     | Pattern                                                                                     |
| ----------------- | ------------ | ------------------------------------------------------------------------------------------- |
| Strands           | Python       | `import strands` / `from strands` / `strands` in requirements.txt                           |
| LangGraph         | Python/JS/TS | `from langgraph` / `langgraph` in requirements.txt / `@langchain/langgraph` in package.json |
| LangChain         | Python/JS/TS | `from langchain` / `langchain` in requirements.txt / `langchain` in package.json            |
| CrewAI            | Python       | `from crewai` / `crewai` in requirements.txt                                                |
| AutoGen           | Python/JS    | `import autogen` / `autogen` in requirements.txt / `autogen-agentchat` in package.json      |
| OpenAI Agents SDK | Python       | `from openai import agents` / `openai[agents]` in requirements.txt                          |
| Fly Sprites       | Multi-lang   | `sprites.dev` hostname / `@fly/sprites` import                                              |

**LLM call loop detection (lower confidence, supplementary):**

If framework imports NOT found, look for **LLM call loops** (while-loop with model API calls):

- Python: `while True:` or `while not done:` containing `openai.ChatCompletion` / `anthropic.messages.create` / `bedrock_runtime.invoke_model`
- JavaScript/TypeScript: `while (true)` or `while (!done)` containing `openai.chat.completions.create` / `anthropic.messages.create`
- Go: `for {` containing LLM client calls

**Confidence for loop detection:** MEDIUM (may be retry logic, not agent loop). Only flag if combined with multi-turn state (session storage, message history arrays).

**Grep commands (frameworks):**

```bash
# Python
grep -ri "import strands" --include="*.py" .
grep -ri "from langgraph" --include="*.py" .
grep -ri "from langchain" --include="*.py" .
grep -ri "from crewai" --include="*.py" .
grep -ri "import autogen" --include="*.py" .
grep -ri "from openai import agents" --include="*.py" .
grep -i "strands\|langgraph\|langchain\|crewai\|autogen" requirements.txt

# JavaScript/TypeScript
grep -ri "@langchain/langgraph" --include="package.json" .
grep -ri "langchain" --include="package.json" .
grep -ri "autogen-agentchat" --include="package.json" .

# Sprites
grep -ri "sprites\.dev" --include="*.js" --include="*.ts" --include="*.py" --include="*.go" .
grep -ri "@fly/sprites" --include="*.js" --include="*.ts" --include="package.json" .
```

---

### S6: Fly Sprites (Detect-Only)

**Pattern:** `sprites.dev` hostname / `@fly/sprites` SDK imports

**Inventory effect:**

- Set `flags.agent_candidate = true`
- Add to `agent_evidence`: "Fly Sprites sandbox usage — Fly's agent-sandbox product, v1 is detect-only"
- Add to `_detected`: "Sprites detected — v1 is detect-only; sandbox workloads can route to agent-advisor"

**Confidence:** HIGH (Sprites-specific SDK and hostname)

**Note:** Sprites (Dec 2025/Jan 2026, sprites.dev) is Fly's dedicated agent-sandbox product. v1 of fly-to-aws does NOT generate migration artifacts for Sprites — mark as detect-only. The agent-advisor handoff can cover the sandbox portion.

---

### S7: Tigris Object Storage

**Pattern:** `AWS_ENDPOINT_URL_S3` env var + Tigris credentials (`tid_` / `tsec_` prefixes) / `tigris.dev` / `fly.storage.tigris.dev` / `t3.storage.dev`

**Inventory effect:**

- Create entry in `object_storage[]`: `{provider: "tigris", bucket: "<detected>", region: "auto"}`
- Add to `_detected`: "Tigris object storage detected — S3 migration path available"

**Confidence:** HIGH (Tigris-specific endpoint and credential patterns)

**Note:** Tigris is S3-compatible. Migration = endpoint/credential swap + `aws s3 sync`. Region `auto` → real AWS region. If app relied on Tigris global edge reads → recommend CloudFront. Flag egress cost shape change ($0.09/GB AWS vs Tigris free-egress posture).

**Grep commands:**

```bash
grep -ri "AWS_ENDPOINT_URL_S3" --include="*.env" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
grep -ri "tid_\|tsec_" --include="*.env" .
grep -ri "tigris\.dev\|fly\.storage\.tigris\.dev\|t3\.storage\.dev" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
```

---

### S8: Managed Postgres (MPG)

**Pattern:** `*.flympg.net` hostname / `fly-user` username / `fly mpg` in scripts / `flympg` in connection strings

**Inventory effect:**

- Create entry in `databases[]`: `{type: "postgres", managed: true, name: "<detected app name>", engine: "postgres", version: "unknown", notes: "Fly Managed Postgres (MPG) — migration to RDS Multi-AZ + RDS Proxy recommended"}`
- Add to `_detected`: "Managed Postgres (MPG) detected — RDS Multi-AZ / Aurora Serverless v2 migration path available"

**Confidence:** HIGH (MPG-specific hostname and username patterns)

**Note:** MPG (Basic $38/Starter $72/Launch $282/Scale $962/Perf $1,922) is Fly's managed Postgres offering (pg16, PgBouncer bundled, max 1TB, 12 regions). Migration targets: RDS Multi-AZ + RDS Proxy (for PgBouncer role) / Aurora Serverless v2 (min-0-ACU for scale-to-zero parity, resume ~15s).

**Grep commands:**

```bash
grep -ri "\.flympg\.net" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" --include="*.env" .
grep -ri "fly-user" --include="*.env" .
grep -ri "fly mpg" --include="*.sh" --include="*.bash" --include="Makefile" .
```

---

### S9: Legacy Fly Postgres

**Pattern:** `flyio/postgres-flex` image in Dockerfile / fly.toml / `<app>.internal:5432` or `:5433` in `DATABASE_URL`

**Inventory effect:**

- Create entry in `databases[]`: `{type: "postgres", managed: false, name: "<app name>", engine: "postgres", version: "unknown", notes: "Legacy Fly Postgres (unsupported) — RDS migration recommended"}`
- Add to `_detected`: "Legacy Fly Postgres detected — unsupported by fly.io, RDS migration strongly recommended"

**Confidence:** HIGH (postgres-flex image is legacy-only; Fly's docs list RDS as replacement)

**Note:** Legacy Fly Postgres is "not managed" and unsupported (Fly's own docs recommend RDS as alternative). Detect via: (1) fly.toml with `image = "flyio/postgres-flex*"` (covered in discover-flytoml.md Rule 2), (2) Dockerfile `FROM flyio/postgres-flex`, (3) connection string patterns like `postgres://<app>.internal:5432/5433`.

**Grep commands:**

```bash
grep -ri "flyio/postgres-flex" --include="Dockerfile*" --include="fly.toml" .
grep -Eri "postgres://[^:]+\.internal:(5432|5433)" --include="*.env" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
```

---

### S10: Upstash Redis

**Pattern:** `*.upstash.io` hostname / `fly redis` CLI commands in scripts / `REDIS_URL` with `upstash.io`

**Inventory effect:**

- Create entry in `extensions[]`: `{name: "upstash-redis", type: "redis", provider: "upstash", migration_target: "elasticache-serverless"}`
- Add to `_detected`: "Upstash Redis detected — ElastiCache Serverless (Valkey preferred, ~33% cheaper floor) migration path available"

**Confidence:** HIGH (Upstash-specific hostname)

**Note:** Upstash Redis on Fly (`fly redis`; fly-`<name>`.upstash.io via Flycast; PAYG $0.20/100k or fixed $10–400/mo) uses HTTP/REST client protocol. Migration to ElastiCache Serverless requires client code rewrite (HTTP → Redis protocol). VPC-only (no public endpoint like Upstash).

**Grep commands:**

```bash
grep -ri "\.upstash\.io" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" --include="*.env" .
grep -ri "fly redis" --include="*.sh" --include="*.bash" --include="Makefile" .
```

---

### S11: Upstash Vector

**Pattern:** `VECTOR_ENDPOINT` / `VECTOR_TOKEN` env vars / `*.upstash.io/vector`

**Inventory effect:**

- Create entry in `extensions[]`: `{name: "upstash-vector", type: "vector", provider: "upstash", migration_target: "opensearch-serverless-vector"}`
- Add to `_detected`: "Upstash Vector detected — OpenSearch Serverless vector / Aurora pgvector / S3 Vectors migration paths available"

**Confidence:** HIGH (Upstash Vector-specific env vars)

**Note:** Upstash Vector (beta, iad/fra). AWS alternatives: OpenSearch Serverless vector engine / Aurora pgvector / S3 Vectors (new).

**Grep commands:**

```bash
grep -ri "VECTOR_ENDPOINT\|VECTOR_TOKEN" --include="*.env" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
```

---

### S12: Sentry

**Pattern:** `SENTRY_DSN` env var / `sentry.io` imports

**Inventory effect:**

- Create entry in `extensions[]`: `{name: "sentry", type: "observability", provider: "sentry", migration_target: "keep-as-saas"}`
- Add to `_detected`: "Sentry detected — keep as SaaS (endpoint-agnostic), optional CloudWatch RUM / X-Ray as AWS-native alternatives"

**Confidence:** HIGH (Sentry-specific DSN env var)

**Note:** Sentry is endpoint-agnostic SaaS — no migration needed. Mention CloudWatch RUM / X-Ray as AWS-native observability alternatives.

**Grep commands:**

```bash
grep -ri "SENTRY_DSN" --include="*.env" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
```

---

### S13: Arcjet

**Pattern:** `ARCJET_KEY` env var / `arcjet.com` / `@arcjet` package imports

**Inventory effect:**

- Create entry in `extensions[]`: `{name: "arcjet", type: "security", provider: "arcjet", migration_target: "keep-as-saas"}`
- Add to `_detected`: "Arcjet detected — keep as SaaS (endpoint-agnostic), optional AWS WAF as AWS-native alternative"

**Confidence:** HIGH (Arcjet-specific key env var)

**Note:** Arcjet (bot protection, rate limiting) is endpoint-agnostic SaaS — no migration needed. AWS WAF is the AWS-native alternative.

**Grep commands:**

```bash
grep -ri "ARCJET_KEY" --include="*.env" --include="*.js" --include="*.ts" --include="*.py" --include="*.rb" --include="*.go" --include="*.java" --include="*.php" .
grep -ri "@arcjet" --include="package.json" .
```

---

### S14: GPU Usage

**Pattern:** `gpu_kind` in fly.toml (covered by discover-flytoml.md) / CUDA imports / GPU instance type mentions

**Inventory effect:**

- Set `flags.gpu = true`
- Add to `_detected`: "GPU usage detected — hard sunset 2026-08-01 for Fly GPU Machines"
- **Display urgency banner** in Discover Step 6 output

**Confidence:** HIGH (fly.toml `gpu_kind` is explicit; CUDA imports are supplementary)

**Note:** Fly GPU Machines are deprecated with a **hard sunset 2026-08-01** ("GPUs are deprecated and will be unavailable after August 1" — fly.io/docs/gpus). GPU routes: a10→g5 (A10G), l40s→g6e (L40S; g6/L4 step-down), a100-40→p4d, a100-80→p4de (p5/H100 upsell). Fargate has NO GPU; use ECS-on-EC2 or SageMaker endpoints.

**Supplementary grep (CUDA):**

```bash
grep -ri "import torch\|import tensorflow\|from cuda" --include="*.py" .
grep -ri "nvidia/cuda" --include="Dockerfile*" .
```

---

## Execution Flow

1. **For each signal:** Run the grep command(s). If matches found, apply the inventory effect.
2. **Confidence gating:** Only write a signal if confidence is HIGH. If MEDIUM, add to `_detected` with "possibly detected (verify)" qualifier. If LOW, skip.
3. **Multi-signal correlation:** If multiple agent framework signals found, list all in `agent_evidence` (e.g., "Framework: LangGraph, Framework: CrewAI").
4. **Process group scoping:** Signals like Machines-API or agent frameworks apply to specific process groups (the ones calling the APIs). Infer the calling group from file paths (e.g., if `worker/agent.py` imports LangGraph, flag the `worker` process group). If ambiguous, flag the first/main process group.
5. **Global flags:** Signals like fly-replay, 6PN, Tigris, MPG, Upstash, Sentry, Arcjet apply at the app level (not per process group).

---

## Output Structure

Code signals supplement the fly.toml-derived inventory. They populate:

- `flags.agent_candidate` (boolean per process group)
- `flags.agent_evidence` (array of strings per process group)
- `flags.gpu` (boolean per process group)
- `network_flags.*` (app-level booleans)
- `databases[]` (app-level array)
- `object_storage[]` (app-level array)
- `extensions[]` (app-level array)
- `_detected` (app-level array of human-readable strings)

---

## Error Handling

| Error                               | Behavior                                                                |
| ----------------------------------- | ----------------------------------------------------------------------- |
| Grep command fails (no grep binary) | Log warning, skip code signals, continue (fly.toml-only inventory)      |
| Large codebase (>10k files)         | Limit grep to common source directories (src/, app/, lib/), log warning |
| Binary files in grep results        | Ignore binary matches (grep -I flag), continue                          |
| Ambiguous process group for signal  | Flag the first process group in fly.toml order, log note in `_detected` |

---

## Notes

- **Conservatism rule enforced:** Only signals with HIGH confidence (unambiguous patterns) are written. When in doubt, omit — let Clarify ask.
- **Determinism boundary:** These detections are LLM interpretation. Always present to user as "detected: X (correct me if wrong)" before routing.
- **No secrets logged:** Never log env var VALUES (e.g., actual DSN strings, tokens). Only log that the VAR NAME exists.
- **Performance:** Grep is fast on codebases <100MB. For larger repos, scope to common source directories or ask user to provide a subset.
