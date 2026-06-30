# Agent Advisor — Skill Orchestration Implementation Plan (Plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the conversational orchestration layer of the agent-advisor plugin — the two skills, their phase references, the shared knowledge layer, and three-platform packaging — that drive a user from "I want to run an agent on AWS" to a layered recommendation document, calling the Plan 1 decision engine for the actual scoring.

**Architecture:** A single plugin with two skills under `skills/`. The main `agent-advisor` skill is a state machine (mirroring `migration-to-aws/gcp-to-aws`'s SKILL.md pattern) that runs Turn 1 → Discover → Clarify (Pass 1) → [score via Plan 1's `scoring.py`] → Clarify (Pass 2) → Design → Estimate → Generate, gated by entry point. A standalone `add-capabilities` skill handles the "already on AWS, add services" path. Both skills read canonical knowledge from `skills/shared/` via `${CLAUDE_PLUGIN_ROOT}` paths. Heavy artifacts and Migrate execution hand off to `migration-to-aws` / `ai-to-aws`.

**Tech Stack:** Markdown SKILL.md + phase reference files; `AskUserQuestion` for interaction; Plan 1's `scoring.py` via `uv run`; `awsknowledge` MCP for volatile-fact refresh; JSON state in `.agent-advisor/`.

## Global Constraints

- Depends on **Plan 1 complete**: `migrate/plugins/agent-advisor/scripts/scoring.py` exists and its `scoring-result.json` shape is the contract this plan consumes.
- All paths relative to repo root `/Volumes/workspace/startups`. Plugin root: `migrate/plugins/agent-advisor/`.
- Run state lives in `.agent-advisor/[MMDD-HHMM]/` (NOT `.migration/` — both plugins must coexist).
- Shared-reference reads MUST use an explicit instruction with `${CLAUDE_PLUGIN_ROOT}`, e.g. ``Read `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/agentcore.md` ``. NEVER a bare `../shared/...` link (spec §3.2).
- The five runtime ids are fixed: `agentcore`, `lambda_microvms`, `ecs`, `eks`, `lambda`.
- The 14 scoring dimensions and their legal values are defined in Plan 1's Data Model. Clarify questions map user answers onto exactly those keys/values.
- No hard plugin `dependencies` — agent-advisor works standalone; handoff targets are checked at runtime.
- All content in **English**.
- `phases.clarify` must be `"completed"` before Design/Estimate/Generate load (phase gate, mirrors migration-to-aws).
- The author/license blocks copy verbatim from `migrate/plugins/ai-to-aws/.{claude,cursor,codex}-plugin/plugin.json` (author "Amazon Web Services", license "Apache-2.0").

---

## File Structure (created by this plan)

```
migrate/plugins/agent-advisor/
├── .claude-plugin/plugin.json          # Task 1
├── .cursor-plugin/plugin.json          # Task 1
├── .codex-plugin/plugin.json           # Task 1
├── .mcp.json                           # Task 1
├── README.md                           # Task 12
├── skills/
│   ├── shared/
│   │   ├── runtimes/*.json             # (Plan 1 — already exists)
│   │   └── decision-refs/              # Task 2
│   │       ├── agentcore.md  ecs.md  eks.md  lambda.md  lambda-microvms.md
│   │       ├── managed-alternatives.md
│   │       ├── model-defaults.md
│   │       └── freshness.md
│   ├── agent-advisor/
│   │   ├── SKILL.md                     # Task 3
│   │   └── references/
│   │       ├── phases/
│   │       │   ├── turn1.md             # Task 4
│   │       │   ├── discover.md          # Task 5
│   │       │   ├── clarify.md           # Task 6 (orchestrator + answer mapping)
│   │       │   ├── clarify-technical.md # Task 6
│   │       │   ├── clarify-business.md  # Task 6
│   │       │   ├── clarify-pass2.md     # Task 7
│   │       │   ├── design.md            # Task 8
│   │       │   ├── estimate.md          # Task 9
│   │       │   └── generate.md          # Task 10
│   │       ├── output-templates/recommendation-doc.md   # Task 10
│   │       └── handoff/handoff-migration.md             # Task 8
│   └── add-capabilities/
│       └── SKILL.md                     # Task 11
```

The marketplace entry (Task 13) modifies `.claude-plugin/marketplace.json` at repo root.

---

### Task 1: Plugin manifests (three platforms) + MCP config

**Files:**
- Create: `migrate/plugins/agent-advisor/.claude-plugin/plugin.json`
- Create: `migrate/plugins/agent-advisor/.cursor-plugin/plugin.json`
- Create: `migrate/plugins/agent-advisor/.codex-plugin/plugin.json`
- Create: `migrate/plugins/agent-advisor/.mcp.json`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable plugin shell (no skills yet — added in later tasks).

- [ ] **Step 1: Create `.claude-plugin/plugin.json`**

```json
{
  "name": "agent-advisor",
  "version": "0.1.0",
  "description": "Decide how and where to run AI agents on AWS. Recommends a runtime (AgentCore Runtime, Lambda MicroVMs, ECS, EKS, or Lambda), an AgentCore deployment model and services, and a Bedrock model default — backed by deterministic scoring. Produces a layered recommendation doc and lightweight scaffolding; hands off heavy artifacts and migration execution to the migration-to-aws and ai-to-aws plugins.",
  "author": {
    "name": "Amazon Web Services"
  },
  "license": "Apache-2.0"
}
```

- [ ] **Step 2: Create `.cursor-plugin/plugin.json`**

```json
{
  "name": "agent-advisor",
  "displayName": "Agent Advisor (Run AI Agents on AWS)",
  "version": "0.1.0",
  "description": "Decide how and where to run AI agents on AWS. Recommends a runtime (AgentCore Runtime, Lambda MicroVMs, ECS, EKS, or Lambda), an AgentCore deployment model and services, and a Bedrock model default — backed by deterministic scoring. Produces a layered recommendation doc and lightweight scaffolding. Runs in inline mode on Cursor.",
  "author": {
    "name": "Amazon Web Services"
  },
  "license": "Apache-2.0",
  "keywords": [
    "aws", "ai-agents", "agentcore", "bedrock", "lambda-microvms",
    "ecs", "eks", "lambda", "runtime-selection", "agent-architecture",
    "strands", "langgraph", "crewai", "deploy-agent", "agent-runtime"
  ]
}
```

- [ ] **Step 3: Create `.codex-plugin/plugin.json`**

```json
{
  "name": "agent-advisor",
  "version": "0.1.0",
  "description": "Decide how and where to run AI agents on AWS. Recommends a runtime, an AgentCore deployment model and services, and a Bedrock model default — backed by deterministic scoring.",
  "author": {
    "name": "Amazon Web Services",
    "url": "https://aws.amazon.com"
  },
  "homepage": "https://github.com/awslabs/startups/tree/main/migrate",
  "repository": "https://github.com/awslabs/startups",
  "license": "Apache-2.0",
  "keywords": [
    "aws", "ai-agents", "agentcore", "bedrock", "lambda-microvms",
    "ecs", "eks", "lambda", "runtime-selection", "agent-architecture",
    "strands", "langgraph", "crewai", "deploy-agent", "agent-runtime"
  ],
  "skills": "./skills/",
  "mcpServers": "./.mcp.json",
  "interface": {
    "displayName": "Agent Advisor (Run AI Agents on AWS)",
    "shortDescription": "Recommend how and where to run AI agents on AWS, with deterministic runtime scoring.",
    "longDescription": "Answer a few adaptive questions about your agent and get a runtime recommendation (AgentCore Runtime, Lambda MicroVMs, ECS, EKS, or Lambda), an AgentCore deployment model and service set, and a Bedrock model default — all backed by a deterministic, testable scoring engine. The advisor adapts its questions to your technical background and produces one layered recommendation document (business summary plus technical detail) with an architecture diagram. It generates lightweight scaffolding for greenfield builds and hands off heavy artifact generation and migration execution to the migration-to-aws and ai-to-aws plugins.",
    "developerName": "Amazon Web Services",
    "category": "Developer Tools",
    "capabilities": ["Read", "Write"],
    "websiteURL": "https://github.com/awslabs/startups/tree/main/migrate",
    "defaultPrompt": [
      "Help me choose a runtime for my AI agent on AWS",
      "AgentCore vs ECS vs Lambda MicroVMs for my agent",
      "I have an agent idea — what should I deploy on AWS?",
      "Add AgentCore services to my agent already on AWS"
    ]
  }
}
```

- [ ] **Step 4: Create `.mcp.json`**

```json
{
  "mcpServers": {
    "awsknowledge": {
      "type": "http",
      "url": "https://knowledge-mcp.global.api.aws"
    }
  }
}
```

- [ ] **Step 5: Validate all four files are valid JSON**

Run:
```bash
cd migrate/plugins/agent-advisor && for f in .claude-plugin/plugin.json .cursor-plugin/plugin.json .codex-plugin/plugin.json .mcp.json; do python3 -c "import json;json.load(open('$f'))" && echo "OK $f"; done
```
Expected: four `OK` lines.

- [ ] **Step 6: Commit**

```bash
git add migrate/plugins/agent-advisor/.claude-plugin \
        migrate/plugins/agent-advisor/.cursor-plugin \
        migrate/plugins/agent-advisor/.codex-plugin \
        migrate/plugins/agent-advisor/.mcp.json
git commit -m "feat(agent-advisor): three-platform plugin manifests + MCP config"
```

---

### Task 2: Shared decision-refs (knowledge layer)

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/shared/decision-refs/agentcore.md`
- Create: `migrate/plugins/agent-advisor/skills/shared/decision-refs/lambda-microvms.md`
- Create: `migrate/plugins/agent-advisor/skills/shared/decision-refs/ecs.md`
- Create: `migrate/plugins/agent-advisor/skills/shared/decision-refs/eks.md`
- Create: `migrate/plugins/agent-advisor/skills/shared/decision-refs/lambda.md`
- Create: `migrate/plugins/agent-advisor/skills/shared/decision-refs/managed-alternatives.md`
- Create: `migrate/plugins/agent-advisor/skills/shared/decision-refs/model-defaults.md`
- Create: `migrate/plugins/agent-advisor/skills/shared/decision-refs/freshness.md`

**Interfaces:**
- Consumes: nothing (static knowledge).
- Produces: per-runtime service cards (consumed by Design Task 8) and the freshness/MCP field list (consumed by Estimate Task 9 and Generate Task 10).

Each service card has a fixed section structure so Design can pull predictable sections. Source: PM comparison doc + verified facts (spec §7).

- [ ] **Step 1: Create `agentcore.md`** (service card — fixed sections)

```markdown
# AgentCore Runtime — Service Card

## One-liner
Serverless, agent-purpose-built runtime: managed session routing, true session
isolation, built-in identity, $0 billing during I/O wait.

## Best for
Short agent sessions with high LLM I/O wait, human-in-the-loop, multi-tenant
isolation, minimal ops, cross-session memory, high-volume session launch.

## Hard limits (verify via MCP — volatile)
- Session cap: 8h (extending — verify)
- Compute cap: 2 vCPU / 8 GB (hard)
- FedRAMP: not yet certified (verify)

## Deployment models
- **Harness** — no-code, config-driven; single agent, greenfield, OpenAI Assistants migration.
- **Framework on Runtime** — Strands / LangGraph / CrewAI / custom; multi-agent, complex orchestration.

## Six dimensions
- Identity: built-in (free), OAuth via enhanced Identity
- Observability: auto OTEL traces
- Guardrails: Bedrock Guardrails + Policy (Cedar) for high-risk actions
- Scaling: 5,000 concurrent sessions, 25 TPS launch (adjustable)
- Tool/Gateway: Gateway for external APIs / MCP
- Protocols: HTTP/1.1, WebSocket; MCP, A2A

## Tradeoffs
2 vCPU / 8 GB ceiling; no process-level suspend (Session Storage persists files only).
```

- [ ] **Step 2: Create `lambda-microvms.md`** (service card)

```markdown
# Lambda MicroVMs — Service Card

## One-liner
Firecracker microVM compute with full process-level suspend/resume, up to
16 vCPU / 32 GB, multi-port / gRPC, near-instant snapshot start. A compute
primitive, not an agent platform.

## Best for
Long interactive sessions with idle periods (suspend preserves memory + processes),
heavy non-GPU compute (>2 vCPU), multi-port / gRPC / per-session URL workloads,
sub-second cold starts.

## Hard limits (verify via MCP — volatile)
- Session cap: 8h (max 28,800s) — same as AgentCore; NOT longer
- Max compute: up to 16 vCPU / 32 GB
- Launch rate: RunMicrovm 5 TPS, NOT adjustable (hard scaling weakness)
- Account memory cap: ~1,024 GB in select regions
- FedRAMP: unknown (verify)

## Lifecycle
Hooks: /ready, /launch, /resume, /suspend, /terminate. Hook failure/timeout terminates the VM.

## Six dimensions
- Identity: bring-your-own (JWE tokens, port-scoped)
- Observability: you instrument (no built-in OTEL)
- Guardrails: bring-your-own
- Scaling: 5 TPS launch (hard cap); memory-bound concurrency
- Tool/Gateway: not an agent platform; pair with AgentCore Gateway if needed
- Protocols: HTTP/2, WebSocket, gRPC, SSE; per-MicroVM URL

## Tradeoffs
Not agent-purpose-built (no /invocations contract, no built-in services). 5 TPS
launch cap is the decisive weakness for high-volume platforms.
```

- [ ] **Step 3: Create `ecs.md`, `eks.md`, `lambda.md`** (service cards, same section structure)

`ecs.md`:
```markdown
# Amazon ECS (Fargate) — Service Card

## One-liner
Container runtime, no cluster management, cost-optimized at steady scale.

## Best for
Container experience, steady continuous traffic, custom compute, sessions up to/over 8h.

## Hard limits
None that eliminate it for agents (GPU and >8h are where it wins vs AgentCore).

## Six dimensions
- Identity: IAM / bring-your-own
- Observability: CloudWatch + ADOT (you configure)
- Guardrails: bring-your-own + Bedrock Guardrails
- Scaling: Savings Plans, bin-packing
- Tool/Gateway: AgentCore services available as add-ons
- Protocols: anything you expose

## Tradeoffs
Always-on baseline cost during idle; you build session isolation/memory yourself.
Hands off to migration-to-aws for compute-layer config.
```

`eks.md`:
```markdown
# Amazon EKS — Service Card

## One-liner
Kubernetes, full control, portable across clouds, GPU-capable.

## Best for
Existing K8s cluster, platform-engineering team, multi-cloud portability, GPU workloads.

## Hard limits
None that eliminate it for agents (it's the GPU / multi-cloud / full-control winner).

## Six dimensions
- Identity: IRSA / bring-your-own
- Observability: CloudWatch / Prometheus (you configure)
- Guardrails: bring-your-own + Bedrock Guardrails
- Scaling: Spot + Karpenter
- Tool/Gateway: AgentCore services available as add-ons
- Protocols: anything you expose

## Tradeoffs
Highest ops burden; only worth it with existing K8s or GPU/multi-cloud needs.
Hands off to migration-to-aws for compute-layer config.
```

`lambda.md`:
```markdown
# AWS Lambda (standard) — Service Card

## One-liner
Event-driven functions, scale to zero, cheapest for short stateless tasks.

## Best for
Seconds-long, stateless, event-driven agent tasks (single tool call, classification).

## Hard limits
- Execution timeout: 15 minutes (eliminates it for minutes-to-hours sessions)

## Six dimensions
- Identity: IAM
- Observability: CloudWatch
- Guardrails: bring-your-own + Bedrock Guardrails
- Scaling: automatic, scale to zero
- Tool/Gateway: AgentCore services available as add-ons
- Protocols: invoke / function URL

## Tradeoffs
15-minute hard cap; no long sessions, no cross-session memory without external state.
Hands off to migration-to-aws for compute-layer config.
```

- [ ] **Step 4: Create `managed-alternatives.md`**

```markdown
# Managed Agent Alternatives (awareness, not actively recommended)

Surface these as awareness with tradeoffs when the user is committed to a single provider.

## Claude Managed Agents (Claude-committed)
- Tradeoffs: not in AWS compliance boundary (Anthropic is data processor); no governance
  stack (no Policy/Registry/Identity); organizational lock-in (cannot export).
- If the customer needs HIPAA/SOC/FedRAMP, governance, multi-agent A2A, code export, or
  multi-model → AgentCore wins regardless.

## Bedrock Managed Agents (OpenAI-committed)
- Available in us-east-1 and expanding.
- If the customer needs model flexibility, governance, or code export → AgentCore wins.

## Rule
Multi-provider or undecided → AgentCore (only option supporting all models natively, no lock-in).
```

- [ ] **Step 5: Create `model-defaults.md`**

```markdown
# Bedrock Model Defaults (forward selection only)

This plugin does NOT reproduce source-model pricing/TCO tables. Detailed pricing and
source→target migration mapping live in the **migration-to-aws** plugin (canonical source).

## Forward default (requirement → model)
| Priority | Model |
| --- | --- |
| Quality / Balanced / unknown | Claude Sonnet 4.6 |
| Speed / Cost | Claude Haiku 4.5 |
| Extended thinking (feature override) | Claude Sonnet 4.6 with extended thinking |

Used only to fill the cost estimate and the scaffold's `modelId`.

## Migrate path
Give a coarse family-level mapping only (e.g. "GPT-4o → Claude Sonnet 4.6 family").
For dollar figures and TCO, direct the user to migration-to-aws. Never put prices here.
```

- [ ] **Step 6: Create `freshness.md`**

```markdown
# Volatile Facts & Freshness

## Fields to verify at runtime via the awsknowledge MCP (when available)
- AgentCore session cap (currently "8h, extending")
- AgentCore compute cap (2 vCPU / 8 GB)
- AgentCore / Lambda MicroVMs region availability
- Lambda MicroVMs launch TPS (5, not adjustable)
- FedRAMP certification status for AgentCore and Lambda MicroVMs
- Any Bedrock model price (defer to migration-to-aws pricing cache; never hardcode here)

## Procedure
1. Read the `volatile_facts` entries (with `verify_via_mcp: true`) from the winning
   runtime's profile JSON.
2. Attempt an awsknowledge MCP lookup for each.
3. On success, use the fresh value.
4. On failure (MCP unavailable), use the cached `value` from the profile and record that
   this field fell back.

## Freshness footer template (append to every recommendation doc)
> _Generated <DATE>. Hard-constraint facts verified via AWS Knowledge MCP: <list succeeded>.
> Fell back to cached values for: <list fallbacks>. Limits and pricing change — verify
> against AWS docs before committing._
```

- [ ] **Step 7: Verify all eight files exist and are non-empty**

Run: `ls -1 migrate/plugins/agent-advisor/skills/shared/decision-refs/ | wc -l`
Expected: `8`.

- [ ] **Step 8: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/shared/decision-refs/
git commit -m "feat(agent-advisor): shared decision-refs (service cards, model defaults, freshness)"
```

---

### Task 3: Main skill SKILL.md (state machine)

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/SKILL.md`

**Interfaces:**
- Consumes: phase reference files (Tasks 4-10), `scoring.py` (Plan 1).
- Produces: the orchestrator that routes to phases by state and entry point.

- [ ] **Step 1: Write SKILL.md**

Create `migrate/plugins/agent-advisor/skills/agent-advisor/SKILL.md`:

````markdown
---
name: agent-advisor
description: "Recommend how and where to run AI agents on AWS. Triggers on: which runtime for my agent, AgentCore vs ECS vs EKS vs Lambda, AgentCore vs Lambda MicroVMs, deploy an AI agent on AWS, agent architecture on AWS, I have an agent idea what do I build, move my agents to AWS. Runs a phased flow: Turn 1 (entry point + technical background), Discover (lightweight code detection), Clarify (adaptive questions), deterministic scoring, Design (runtime + deployment model + services + model), Estimate (coarse cost), Generate (layered recommendation doc + scaffolding). Migrate entry point hands off to migration-to-aws / ai-to-aws after Design. Not for: actual Terraform/IaC generation, migration execution, or detailed per-model pricing — those hand off to migration-to-aws and ai-to-aws."
---

# AWS Agent Advisor

Helps startups decide how and where to run AI agents on AWS. Deterministic scoring
recommends a runtime; the conversation adapts to the user's technical background.

## Definitions
- **"Load"** = Read the file with the Read tool and follow it. Do not summarize or skip.
- **`$RUN_DIR`** = the run directory under `.agent-advisor/` (e.g. `.agent-advisor/0630-1430/`),
  created in Turn 1.
- **`$PLUGIN`** = `${CLAUDE_PLUGIN_ROOT}` (the installed plugin root). On Claude Code this token
  substitutes inline. **If `${CLAUDE_PLUGIN_ROOT}` does not resolve** (some Cursor/Codex builds,
  or a literal `${CLAUDE_PLUGIN_ROOT}` string showing up in a path error), fall back to the
  skill's own directory: this SKILL.md lives at `<plugin>/skills/agent-advisor/SKILL.md`, so
  shared files are at `../shared/...` and scripts at `../../scripts/...` relative to it
  (mirrors the sibling `ai-to-aws` skill's `<SKILL_BASE>/../../scripts` pattern). Prefer
  `${CLAUDE_PLUGIN_ROOT}`; use the relative fallback only when it fails to resolve.

## Prerequisites
- `uv` available (for scoring). Check: `uv --version`. If missing, tell the user to install
  it (`curl -LsSf https://astral.sh/uv/install.sh | sh`) and stop.

## State Machine
After each phase, consult this table for the next action.

| Current state | Condition | Next action |
| --- | --- | --- |
| `turn1` | no `$RUN_DIR/.phase-status.json` | Load `references/phases/turn1.md` |
| `discover` | `turn1` done, entry point in {build_deploy, migrate} AND code provided | Load `references/phases/discover.md` |
| `clarify` | `turn1` done (and discover done or skipped) | Load `references/phases/clarify.md` |
| `design` | `clarify` == "completed" | Load `references/phases/design.md` |
| `estimate` | `design` done, entry point in {build_scratch, build_deploy} | Load `references/phases/estimate.md` |
| `generate` | `estimate` done (or skipped for add path) | Load `references/phases/generate.md` |
| `complete` | `generate` done | Done |

**Entry-point routing:**
- `build_scratch` → skip Discover; Clarify → Design → Estimate → Generate.
- `build_deploy` → Discover (if code) → Clarify → Design → Estimate → Generate.
- `migrate` → Discover (if code) → Clarify → Design → **handoff, stop** (no Estimate/Generate).
- `add_capabilities` → this is handled by the **separate `add-capabilities` skill**; if a user
  on this skill picks it in Turn 1, tell them to invoke `/agent-advisor:add-capabilities`.

**Phase gate:** Do NOT load design.md / estimate.md / generate.md unless
`$RUN_DIR/.phase-status.json` exists and `phases.clarify == "completed"`. If the user asks to
skip Clarify, refuse briefly and run Clarify.

## State file (`.phase-status.json`)
```json
{
  "run_id": "0630-1430",
  "entry_point": "build_scratch",
  "audience": "technical",
  "current_phase": "clarify",
  "phases": {
    "turn1": "completed", "discover": "skipped", "clarify": "in_progress",
    "design": "pending", "estimate": "pending", "generate": "pending"
  }
}
```
Status values: `pending` → `in_progress` → `completed`, plus `skipped`. Use read-merge-write:
read before each update, change only the advancing keys, keep prior phases.

## Workflow Execution
1. Read `.agent-advisor/*/.phase-status.json` (latest dir). If none, start at Turn 1.
2. Determine the phase via the State Machine table.
3. Load that phase's reference file and execute every step in order.
4. Update `.phase-status.json` (read-merge-write) only after the phase's work is done.
5. Show the user what happened and what's next.

## Files
| File | Purpose |
| --- | --- |
| `references/phases/turn1.md` | Entry point + technical background + open context |
| `references/phases/discover.md` | Lightweight code detection |
| `references/phases/clarify.md` | Clarify orchestrator + answer mapping to scoring keys |
| `references/phases/clarify-technical.md` | Technical-background question wording |
| `references/phases/clarify-business.md` | Business-background question wording |
| `references/phases/clarify-pass2.md` | Winner-specific follow-ups |
| `references/phases/design.md` | Assemble recommendation; Migrate handoff branch |
| `references/phases/estimate.md` | Coarse cost magnitude |
| `references/phases/generate.md` | Layered recommendation doc + scaffolding |
| `$PLUGIN/skills/shared/decision-refs/*.md` | Runtime service cards, model defaults, freshness |
| `$PLUGIN/skills/shared/runtimes/*.json` | Runtime registry (read by scoring.py) |
| `$PLUGIN/scripts/scoring.py` | Deterministic scoring engine |
````

- [ ] **Step 2: Verify the frontmatter parses**

Run:
```bash
python3 -c "import re,sys; t=open('migrate/plugins/agent-advisor/skills/agent-advisor/SKILL.md').read(); assert t.startswith('---'); fm=t.split('---',2)[1]; assert 'name: agent-advisor' in fm and 'description:' in fm; print('SKILL frontmatter OK')"
```
Expected: `SKILL frontmatter OK`.

- [ ] **Step 3: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/SKILL.md
git commit -m "feat(agent-advisor): main skill SKILL.md state machine"
```

---

### Task 4: Turn 1 phase (entry point + background)

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/turn1.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `$RUN_DIR/.phase-status.json` with `entry_point` and `audience` set; phase `turn1` completed.

- [ ] **Step 1: Write turn1.md**

````markdown
# Phase: Turn 1 — Entry Point + Background

## Step 1 — Create the run directory
Generate a run id from the current time as `MMDD-HHMM`. Create `.agent-advisor/<run_id>/`
and a `.agent-advisor/.gitignore` containing `*` (so run state is never committed).

## Step 2 — Ask two questions with AskUserQuestion
Ask BOTH in one AskUserQuestion call (two questions):

**Q1 — Starting point** (header "Starting point"):
- Build from scratch — I have an idea, no code  → `build_scratch`
- Deploy existing code — I have working agent code  → `build_deploy`
- Migrate — I have agents running elsewhere  → `migrate`
- Add capabilities — already on AWS, want to add services  → `add_capabilities`

**Q2 — Your background** (header "Background"):
- Technical (engineer/developer)  → `technical`
- Business-leaning (founder/PM/non-technical)  → `business`
- Mixed team  → `business` (start in business language, add technical detail on request)

## Step 3 — Handle add_capabilities
If Q1 == add_capabilities: tell the user this path is a separate skill and to invoke
`/agent-advisor:add-capabilities`. Do not continue this skill's flow.

## Step 4 — Open context prompt
Ask (plain text): "What can you tell me about your agent? Any files or existing code to
share? (Optional — say 'skip' to move on.)" Capture any framework/model/infra hints into
`$RUN_DIR/context-notes.md`.

## Step 5 — Write state
Write `$RUN_DIR/.phase-status.json` with `entry_point`, `audience` (from Q2), `turn1` =
completed. Set `discover` = pending if entry point is build_deploy/migrate AND the user
offered code, else `skipped`. Set all later phases pending.
````

- [ ] **Step 2: Verify file exists**

Run: `test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/turn1.md && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/turn1.md
git commit -m "feat(agent-advisor): Turn 1 phase (entry point + background)"
```

---

### Task 5: Discover phase (lightweight detection)

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/discover.md`

**Interfaces:**
- Consumes: user-provided code path (from Turn 1).
- Produces: `$RUN_DIR/context-signals.json` — detected signals that pre-fill Clarify answers.

- [ ] **Step 1: Write discover.md**

````markdown
# Phase: Discover — Lightweight Detection

Only runs for build_deploy / migrate when the user provided a code path. Stays independent
(does NOT require the migration-to-aws plugin).

## Step 1 — Scan for signals (read-only)
In the provided path, look for:
- **Framework** (imports / requirements.txt / package.json): `strands`, `langgraph` /
  `langchain`, `crewai` / `autogen`, `openai` (Agents SDK), else `custom` / `none`.
- **Model provider**: openai / anthropic / google-genai / bedrock mentions.
- **Session/timeout hints**: timeout configs, long-running loops, queue/HITL patterns.
- **Multi-tenant hints**: per-user/tenant scoping, separate contexts.
- **Compute hints**: GPU instance types, heavy compute (compilation, ML inference).
- **Data store hints**: Redis/DynamoDB/vector store connections.

## Step 2 — Map to pre-filled answers
Write `$RUN_DIR/context-signals.json` mapping detected signals onto scoring keys, e.g.:
```json
{
  "framework": "langgraph",
  "multi_agent": "yes",
  "session_state": "hitl",
  "_detected": ["framework from imports", "multi_agent from graph with 2+ nodes"]
}
```
Only include keys you can detect with reasonable confidence. Everything else stays for Clarify.

## Step 3 — Tell the user what was detected
List the detected signals so the user can correct them in Clarify. These pre-fills let
Clarify skip questions (Pass 1 asks fewer for build_deploy/migrate).

**Determinism boundary (important):** these detections are a *best-effort LLM interpretation*
of code, NOT deterministic facts. They become inputs to the deterministic scoring engine, so a
wrong detection silently biases scoring. Mitigation: (1) only write a signal you can detect
with high confidence — when unsure, omit it and let Clarify ask; (2) always present detected
signals to the user as "detected: X (correct me if wrong)" so they have a correction
opportunity before scoring runs. This is the one point where LLM interpretation enters the
otherwise deterministic pipeline.

## Step 4 — Write state
Set `phases.discover` = completed.
````

- [ ] **Step 2: Verify file exists**

Run: `test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/discover.md && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/discover.md
git commit -m "feat(agent-advisor): Discover phase (lightweight detection)"
```

---

### Task 6: Clarify Pass 1 (orchestrator + technical/business wording)

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify.md`
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify-technical.md`
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify-business.md`

**Interfaces:**
- Consumes: `audience` and `entry_point` from state; `context-signals.json` (if any).
- Produces: `$RUN_DIR/answers.json` (the scoring input), then runs `scoring.py`, producing
  `$RUN_DIR/scoring-result.json`. The two wording files map onto **identical** scoring keys.

- [ ] **Step 1: Write clarify.md (orchestrator + canonical answer mapping)**

````markdown
# Phase: Clarify (Pass 1)

Asks the core scoring questions, writes `answers.json`, runs the scoring engine.

## Step 1 — Pick the wording file by audience
- audience == technical → Load `references/phases/clarify-technical.md`
- audience == business → Load `references/phases/clarify-business.md`
Both map onto the SAME scoring keys/values below. Only wording differs.

## Step 2 — Pre-fill from Discover
If `$RUN_DIR/context-signals.json` exists, treat its keys as already answered. Show them as
"detected: <value> (say so if wrong)" and skip asking those, unless the user corrects them.

## Step 3 — Ask the core questions (AskUserQuestion, batched)
Collect answers for these keys. Legal values are fixed (Plan 1 Data Model):
- `session_duration`: under_15min | 15min_to_8hr | over_8hr | unknown
- `traffic_pattern`: bursty | steady | idle | unknown
- `session_state`: stateless | stateful | hitl | unknown
- `isolation`: required | nice_to_have | not_needed | unknown
- `memory_needs`: cross_session | session_only | none | unknown
- `ops_preference`: minimal | moderate | full_control | unknown
- `compute_tier`: light | heavy_non_gpu | gpu | unknown
- `idle_resume`: process_level | filesystem | none | unknown
- `launch_concurrency`: high | moderate | low | unknown
- `multi_agent`: yes | no | unknown
- `framework`: strands | langgraph | crewai | custom | none | unknown
- `existing_cluster`: eks | ecs | none | unknown
- `multi_cloud`: yes | no | unknown
- `platform_fit`: ecs | eks | lambda | none | unknown
- `compliance` (multi-select list): none | soc2 | hipaa | pci | fedramp | gdpr | ccpa
- model keys: `model_priority` (quality|speed|cost|balanced|unknown),
  `model_features` (tool_use|long_context|extended_thinking|rag|multimodal|speed|none|unknown),
  `current_model` (gpt4|gpt4o|gemini_flash|gemini_pro|claude|other|none|unknown),
  `region` (single|multi|global|unknown)

**Critical-question rule:** if `session_duration` is blank/unknown AND entry_point !=
add_capabilities, ask it directly in chat before scoring — it gates hard constraints.

## Step 4 — Write answers.json
```json
{"entry_point": "<from state>", "answers": { ...collected keys... }}
```
Write to `$RUN_DIR/answers.json`.

## Step 5 — Run the scoring engine
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT}/scripts python ${CLAUDE_PLUGIN_ROOT}/scripts/scoring.py $RUN_DIR/answers.json
```
This writes `$RUN_DIR/scoring-result.json` and prints `RESULT=ok VERDICT=<verdict>`.
If the command errors, show the error and stop — do not hand-score.

## Step 6 — Write state
Set `phases.clarify` = completed.
````

- [ ] **Step 2: Write clarify-technical.md**

````markdown
# Clarify wording — Technical audience

Use direct technical terms. Map each answer onto the keys in clarify.md Step 3.

- **session_duration**: "How long do agent tasks typically run? seconds / minutes / hours
  (≤8h) / >8h or continuous."
- **traffic_pattern**: "Traffic shape? bursty with idle / steady continuous / mostly idle."
- **session_state**: "Execution model? stateless / stateful / human-in-the-loop approvals."
- **isolation**: "Multi-tenant isolation required between users? required / nice-to-have / not needed."
- **memory_needs**: "Memory across conversations? cross-session / session-only / none."
- **ops_preference**: "Ops you want to own? minimal (push code, get URL) / serverless with OS
  control / containers / Kubernetes full control."
- **compute_tier**: "Per-session compute? light (≤2 vCPU/8 GB) / heavy non-GPU (>2 vCPU) / GPU."
- **idle_resume**: "On idle-then-resume, do running processes need to continue exactly
  (process_level), is filesystem persistence enough (filesystem), or not needed (none)?"
- **launch_concurrency**: "Peak new-session launch rate? high (>5/sec) / moderate / low."
- **multi_agent / framework / existing_cluster / multi_cloud / platform_fit**: ask directly.
- **compliance**: multi-select.
- **model_priority / model_features / current_model / region**: ask directly (current_model
  only for migrate).
````

- [ ] **Step 3: Write clarify-business.md**

````markdown
# Clarify wording — Business audience

Translate scoring signals into business language. Map answers onto the SAME keys in
clarify.md Step 3 (do not invent new keys/values).

- **session_duration**: "Does your agent answer in a few seconds, work for a few minutes,
  work for hours, or run continuously?" → under_15min / 15min_to_8hr (minutes or hours) /
  over_8hr.
- **traffic_pattern**: "Is usage spiky with quiet gaps, or steady all day?" → bursty / steady / idle.
- **session_state**: "Does a person approve the agent's actions, or does it run on its own?"
  → hitl (approves) / stateful / stateless.
- **isolation**: "Do your different customers' data need to be strictly separated?" →
  required / nice_to_have / not_needed.
- **memory_needs**: "Should the agent remember a user across separate conversations?" →
  cross_session / session_only / none.
- **ops_preference**: "How hands-on do you want to be with infrastructure? just push code /
  some control / full control." → minimal / moderate / full_control.
- **compute_tier**: "Does a task do heavy number-crunching (video, large data, ML), or mostly
  call an AI model and wait?" → heavy_non_gpu / light; ask about GPU only if heavy.
- **idle_resume**: "If a user steps away and comes back, must the work continue exactly where
  it paused?" → process_level / filesystem / none.
- **launch_concurrency**: "At peak, roughly how many new sessions start per second?" → high
  (many) / moderate / low.
- **multi_agent**: "One agent, or several working together?" → no / yes.
- **framework / existing_cluster / multi_cloud / platform_fit**: ask in plain terms; default
  to unknown if the user is unsure (the engine handles unknown safely).
- **compliance**: "Any compliance requirements? (HIPAA, SOC 2, etc.)" multi-select.
- **model_priority**: "What matters most for the AI — quality, speed, cost, or balanced?"
- **model_features / current_model / region**: ask plainly; current_model only for migrate.
````

- [ ] **Step 4: Verify the three files exist**

Run: `ls migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify*.md | wc -l`
Expected: `3`.

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify.md \
        migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify-technical.md \
        migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify-business.md
git commit -m "feat(agent-advisor): Clarify Pass 1 orchestrator + technical/business wording"
```

---

### Task 7: Clarify Pass 2 (winner-specific follow-ups)

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify-pass2.md`

**Interfaces:**
- Consumes: `$RUN_DIR/scoring-result.json` (verdict, deployment_model, agentcore_services).
- Produces: `$RUN_DIR/pass2.json` — service selections / deployment-model confirmation that
  Design folds into the recommendation.

- [ ] **Step 1: Write clarify-pass2.md**

````markdown
# Phase: Clarify (Pass 2) — Winner-specific follow-ups

Runs after scoring, before Design. Only asks what the winning runtime needs.

## Step 1 — Read the scoring result
Read `$RUN_DIR/scoring-result.json`. Branch on `verdict`.

## Step 2 — If verdict includes agentcore
Confirm deployment model (`deployment_model` from the result) and ask which AgentCore
services to enable beyond the always-on set (identity, observability, evaluations,
optimization). Multi-select, seeded from `agentcore_services`:
- Gateway (external APIs / MCP), enhanced Identity (OAuth), Policy (high-risk / multi-tenant),
  Memory (cross-session), Managed KB (internal docs), Code Interpreter, Browser, Web Search,
  Sandbox.
If the user already uses third-party tools for any (detected in Discover), ask: switch to
AgentCore native, or keep existing and connect via Gateway.

## Step 3 — If verdict is ecs / eks / lambda
These hand off to migration-to-aws for compute. Still ask which AgentCore **add-on** services
they want (services run on any runtime). Record them.

## Step 4 — If verdict is co_recommend or no_viable_runtime
- co_recommend: present the tied runtimes with "choose A if X / B if Y" framing; ask the user
  to pick one. Record the pick as `chosen_runtime` (Step 5). Then run Step 2/3 for the pick.
- no_viable_runtime: show `blocking_constraints`; ask which constraint can relax; if one
  changes, rewrite `$RUN_DIR/answers.json` with the changed value and re-run the scoring engine
  (same command as clarify.md Step 5):
  ```bash
  uv run --project ${CLAUDE_PLUGIN_ROOT}/scripts python ${CLAUDE_PLUGIN_ROOT}/scripts/scoring.py $RUN_DIR/answers.json
  ```
  This overwrites `$RUN_DIR/scoring-result.json`. Re-read it and return to Step 1.

## Step 5 — Write pass2.json and state
Write `$RUN_DIR/pass2.json` with:
- `deployment_model` (confirmed),
- `agentcore_services` (final list),
- `chosen_runtime` (REQUIRED when the verdict was `co_recommend` — the runtime id the user
  picked in Step 4; the architecture-diagram composer in Plan 3 reads this to know which runtime
  to draw). Omit for single-winner verdicts.
- any native-vs-gateway choices.
```json
{"deployment_model": "harness", "agentcore_services": ["identity", "memory"],
 "chosen_runtime": "eks", "tool_choices": {"web_search": "native"}}
```
Clarify stays completed.
````

- [ ] **Step 2: Verify file exists**

Run: `test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify-pass2.md && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/clarify-pass2.md
git commit -m "feat(agent-advisor): Clarify Pass 2 (winner-specific follow-ups)"
```

---

### Task 8: Design phase + Migrate handoff

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/design.md`
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/handoff/handoff-migration.md`

**Interfaces:**
- Consumes: `scoring-result.json`, `pass2.json`, the shared service cards.
- Produces: `$RUN_DIR/design.json` (the assembled recommendation). For Migrate, also
  `$RUN_DIR/handoff-summary.md` and a stop.

- [ ] **Step 1: Write design.md**

````markdown
# Phase: Design

Assembles the recommendation from the scoring result + Pass 2 choices + service cards.

## Step 1 — Read inputs
Read `$RUN_DIR/scoring-result.json` and `$RUN_DIR/pass2.json`.

## Step 2 — Load the winning runtime's service card
Load `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/<verdict>.md` (use `lambda-microvms.md`
for lambda_microvms). For co_recommend, load both. Load
`${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/model-defaults.md` and
`managed-alternatives.md`.

## Step 3 — Refresh volatile facts
Load `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/freshness.md` and follow its procedure:
read the winning profile's `volatile_facts`, try awsknowledge MCP for each, fall back to cached
values on failure. Record which succeeded vs fell back (for the freshness footer).

## Step 4 — Provider lock-in check
If the user is committed to a single provider (from model answers), surface the matching
managed alternative from `managed-alternatives.md` with its tradeoffs. Otherwise note AgentCore
supports all models.

## Step 5 — Assemble design.json
```json
{
  "verdict": "...", "deployment_model": "...", "agentcore_services": [...],
  "model_recommendation": {...}, "warnings": [...],
  "volatile_facts": {"session_cap": {"value": "8h", "source": "mcp|cached"}},
  "managed_alternative": "claude_managed | bedrock_managed | none",
  "handoff_required": true|false
}
```
Set `handoff_required` = true when verdict is ecs/eks/lambda OR entry_point == migrate.

## Step 6 — Branch on entry point
- entry_point == migrate → Load `references/handoff/handoff-migration.md` and follow it. STOP
  after writing the handoff summary (do NOT run Estimate/Generate).
- otherwise → set `phases.design` = completed and continue to Estimate.
````

- [ ] **Step 2: Write handoff-migration.md**

````markdown
# Handoff — Migrate path

The advisor's job ends at the decision. Execution belongs to the migration plugins.

## Step 1 — Write the handoff summary
Write `$RUN_DIR/handoff-summary.md` containing: recommended runtime + deployment model +
services, coarse model family mapping (from model_recommendation.migration_from, no prices),
and the rationale (top scoring signals + eliminations).

## Step 2 — Check downstream availability
Check whether `migration-to-aws` and/or `ai-to-aws` appear in the available-skills list (do
NOT invoke them as a test).

## Step 3 — Direct the user
- For AI/LLM workload migration (model swap, SDK rewrite): point to `/ai-to-aws:llm-to-bedrock`.
- For infrastructure/container migration (ECS/EKS/Lambda compute): point to
  `migration-to-aws:gcp-to-aws`.
- If a needed plugin is NOT installed: give the install command
  `/plugin install <name>@startups-for-aws` and tell the user to re-run that plugin with the
  handoff summary at `$RUN_DIR/handoff-summary.md`.

## Step 4 — Write state and stop
Set `phases.design` = completed. Do not advance to Estimate/Generate. Tell the user the advisor
phase is done and the handoff summary is saved.
````

- [ ] **Step 3: Verify both files exist**

Run:
```bash
test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/design.md && \
test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/handoff/handoff-migration.md && echo OK
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/design.md \
        migrate/plugins/agent-advisor/skills/agent-advisor/references/handoff/handoff-migration.md
git commit -m "feat(agent-advisor): Design phase + Migrate handoff"
```

---

### Task 9: Estimate phase (coarse cost, reuse migration-to-aws pattern)

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/estimate.md`

**Interfaces:**
- Consumes: `design.json`.
- Produces: `$RUN_DIR/estimate.json` — coarse monthly magnitude with a `pricing_source` marker.

- [ ] **Step 1: Write estimate.md**

````markdown
# Phase: Estimate — Coarse Cost Magnitude

Build/Add paths only (Migrate handed off before this). Magnitude only — NOT precise
estimation (that's migration-to-aws's job). Mirrors migration-to-aws's pricing pattern.

## Step 1 — Read the design
Read `$RUN_DIR/design.json`.

## Step 2 — Pricing source (layered, same as migration-to-aws)
1. Primary: a small cached rate table (inline below — AgentCore vCPU/GB-hour, Fargate, Lambda,
   plus the model default's token rates as order-of-magnitude). Carry a "last updated" date.
2. Fallback for anything missing: the `awspricing` MCP if available.
3. Record `pricing_source`: `cached` | `cached_stale` (if >30 days old) | `mcp`.

Cached anchors (order-of-magnitude, us-east-1, verify):
- AgentCore: ~$0.0895/vCPU-hour (active CPU only), ~$0.00945/GB-hour
- Lambda MicroVMs: ~$0.0997/vCPU-hour, ~$0.0132/GB-hour
- Fargate: ~$0.04048/vCPU-hour, ~$0.004445/GB-hour
- Bedrock model token rates: defer to migration-to-aws pricing cache for exact figures

## Step 3 — Produce a magnitude, not a quote
Estimate a rough monthly band (e.g. "order of $50–150/month at this usage") from the runtime
+ model + a stated usage assumption. State every assumption. Never present a precise total.

> Determinism note: this magnitude is computed in the LLM layer (convention-aligned with
> migration-to-aws, which also estimates in-skill). It is the one output that is NOT
> script-deterministic. Acceptable for v1 (magnitude-only, every assumption stated); flagged as
> a future candidate to move into a small deterministic script if precision is ever required.

## Step 4 — Write estimate.json
```json
{"monthly_magnitude_usd": "50-150", "pricing_source": "cached",
 "assumptions": ["1000 sessions/mo, 5 min avg, 60% I/O wait"],
 "note": "Order-of-magnitude only. For a precise estimate use migration-to-aws."}
```

## Step 5 — Write state
Set `phases.estimate` = completed.
````

- [ ] **Step 2: Verify file exists**

Run: `test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/estimate.md && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/estimate.md
git commit -m "feat(agent-advisor): Estimate phase (coarse cost magnitude)"
```

---

### Task 10: Generate phase + recommendation doc template

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/generate.md`
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/output-templates/recommendation-doc.md`

**Interfaces:**
- Consumes: `design.json`, `estimate.json`, service cards, the architecture-diagram step
  (Plan 3 — referenced here as a load point).
- Produces: `$RUN_DIR/recommendation.md` (the deliverable) + lightweight scaffolding for Build.

- [ ] **Step 1: Write the recommendation doc template**

````markdown
<!-- recommendation-doc.md — fill all sections; business summary first, technical detail after -->
# AWS Agent Architecture Recommendation

## 1. Executive summary
<2–3 plain-language sentences: recommended runtime + why, for a non-technical reader.>

## 2. Your profile
<bulleted summary of the answers that drove the decision.>

## 3. Recommendation: <Runtime> <+ deployment model if AgentCore>
<rationale + the top scoring signals; business framing then technical specifics.>

## 4. Architecture diagram
<INSERT the Mermaid block + ASCII fallback produced by the Generate diagram step (Plan 3).>

## 5. Alternatives considered
<eliminated/lower-scored runtimes and why.>

## 6. Comparison
<relevant rows from the runtime service cards.>

## 7. Six dimensions
<Identity, Observability, Guardrails, Scaling, Tool/Gateway, Protocols — from the service card.>

## 8. AgentCore services to enable
<final service list from pass2.json, with why each; note which are free.>

## 9. Bedrock model
<model default + reasoning; for migrate, coarse family mapping + "see migration-to-aws for pricing".>

## 10. Cost magnitude
<from estimate.json: the band + assumptions + "order-of-magnitude" disclaimer.>

## 11. Next steps
<scaffolding pointers; handoff pointers if applicable.>

## 12. Freshness footer
<from freshness.md template: date, MCP-verified vs cached fields, verify disclaimer.>
````

- [ ] **Step 2: Write generate.md**

````markdown
# Phase: Generate — Recommendation Doc + Scaffolding

## Step 1 — Read inputs
Read `$RUN_DIR/design.json` and `$RUN_DIR/estimate.json`. Load the winning runtime's service
card and `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/model-defaults.md`.

## Step 2 — Build the architecture diagram
Follow the diagram build step (Plan 3: `references/diagram/build-diagram.md`) to produce the
Mermaid block + ASCII fallback from `scoring-result.json` + `pass2.json`. If Plan 3 is not yet
installed, emit a simple text node list as a placeholder and note it.

## Step 3 — Fill the recommendation document
Load `references/output-templates/recommendation-doc.md`. Fill ALL 12 sections. Business
summary first, technical detail after (single layered doc — do not fork by audience). Write to
`$RUN_DIR/recommendation.md`. Append the freshness footer.

## Step 4 — Lightweight scaffolding (Build paths only)
- AgentCore + Harness → write a minimal `harness.json` skeleton with the model id from
  model_recommendation and the selected services.
- AgentCore + Framework / other runtimes → write a minimal framework starter note (entrypoint
  contract: `/invocations` POST + `/ping` GET for AgentCore) + the model id.
Write scaffolding under `$RUN_DIR/scaffold/`. Keep it minimal — heavy IaC hands off.

## Step 5 — In-chat mini-brief
Print: Recommendation, Why (top 3 signals), Eliminated, Model, and a pointer to
`$RUN_DIR/recommendation.md`. Surface any `warnings` from the scoring result (e.g. 5 TPS).

## Step 6 — Write state
Set `phases.generate` = completed. The advisor flow is complete.
````

- [ ] **Step 3: Verify both files exist**

Run:
```bash
test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/generate.md && \
test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/output-templates/recommendation-doc.md && echo OK
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/generate.md \
        migrate/plugins/agent-advisor/skills/agent-advisor/references/output-templates/recommendation-doc.md
git commit -m "feat(agent-advisor): Generate phase + recommendation doc template"
```

---

### Task 11: add-capabilities skill (standalone)

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/add-capabilities/SKILL.md`

**Interfaces:**
- Consumes: the shared service cards via `${CLAUDE_PLUGIN_ROOT}`.
- Produces: a service-enablement recommendation (no runtime scoring).

- [ ] **Step 1: Write the add-capabilities SKILL.md**

````markdown
---
name: add-capabilities
description: "For teams already running agents on AWS who want to add AgentCore services. Triggers on: add AgentCore services, add memory/gateway/identity/policy to my agent, enable AgentCore Memory, add observability to my agent, I'm already on AWS and want to add agent capabilities. Recommends which AgentCore services to enable (on any runtime), why, what's free, and native-vs-bring-your-own. Does NOT score runtimes (use the agent-advisor skill for runtime selection)."
---

# Add AgentCore Capabilities

For customers already on AWS who want to add AgentCore services. No runtime scoring — services
run on any runtime.

## Step 1 — Current runtime
Ask which runtime they run on now: AgentCore / ECS / EKS / Lambda / other.

## Step 2 — Capabilities needed (multi-select)
Identity, Gateway, Memory, Policy, Observability, Managed KB, Code Interpreter, Browser,
Web Search, Sandbox. For each selected, load the relevant section of
`${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/agentcore.md`.

## Step 3 — Native vs bring-your-own
If they already use a third-party tool for a capability (Tavily/Pinecone/Browserbase/etc),
present: switch to AgentCore native, or keep existing and connect via Gateway.

## Step 4 — Volatile facts
Load `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/freshness.md`; verify service
availability via awsknowledge MCP where relevant; fall back to cached + note.

## Step 5 — Output
Produce a short recommendation: which services to enable, why, what's free (Identity), how they
integrate on the current runtime, and setup pointers. Append the freshness footer.
````

- [ ] **Step 2: Verify frontmatter parses**

Run:
```bash
python3 -c "t=open('migrate/plugins/agent-advisor/skills/add-capabilities/SKILL.md').read(); assert t.startswith('---') and 'name: add-capabilities' in t; print('OK')"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/add-capabilities/SKILL.md
git commit -m "feat(agent-advisor): standalone add-capabilities skill"
```

---

### Task 12: README

**Files:**
- Create: `migrate/plugins/agent-advisor/README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: user-facing documentation.

- [ ] **Step 1: Write README.md**

````markdown
# Agent Advisor

Decide **how and where to run AI agents on AWS**. Answer a few adaptive questions and get a
runtime recommendation (AgentCore Runtime, Lambda MicroVMs, ECS, EKS, or Lambda), an AgentCore
deployment model and service set, and a Bedrock model default — backed by a deterministic,
testable scoring engine.

## What it does
- Adapts its questions to your technical background (technical vs business wording).
- Scores runtimes deterministically (`scripts/scoring.py`, registry-driven).
- Produces one layered recommendation document (business summary + technical detail) with an
  architecture diagram.
- Generates lightweight scaffolding for greenfield builds.
- Hands off heavy artifact generation and migration execution to `migration-to-aws` and
  `ai-to-aws`.

## Skills
- `agent-advisor` — runtime selection for Build / Migrate.
- `add-capabilities` — add AgentCore services to agents already on AWS.

## Usage
Install from the `startups-for-aws` marketplace, then ask e.g. "which runtime for my agent?"
or invoke `/agent-advisor:add-capabilities`.

## Scope
Recommendation + justification + lightweight scaffolding. NOT full Terraform/IaC, migration
execution, or detailed per-model pricing — those hand off to the migration plugins.

## Extensibility
Each runtime is a self-contained JSON profile under `skills/shared/runtimes/`. Adding a runtime
is adding one file; the scoring engine needs no changes (it may need a new differentiating
question if the runtime competes on a new axis).
````

- [ ] **Step 2: Commit**

```bash
git add migrate/plugins/agent-advisor/README.md
git commit -m "docs(agent-advisor): README"
```

---

### Task 13: Marketplace entry

**Files:**
- Modify: `.claude-plugin/marketplace.json` (repo root)

**Interfaces:**
- Consumes: nothing.
- Produces: the plugin discoverable in the `startups-for-aws` marketplace.

- [ ] **Step 1: Add the plugin entry**

In `.claude-plugin/marketplace.json`, append to the `plugins` array (after the `ai-to-aws`
entry):

```json
    {
      "name": "agent-advisor",
      "source": "./migrate/plugins/agent-advisor",
      "version": "0.1.0",
      "description": "Decide how and where to run AI agents on AWS. Deterministic scoring recommends a runtime (AgentCore Runtime, Lambda MicroVMs, ECS, EKS, or Lambda), an AgentCore deployment model and services, and a Bedrock model default. Adapts questions to your technical background and produces a layered recommendation doc with an architecture diagram. Hands off heavy artifacts and migration execution to migration-to-aws and ai-to-aws."
    }
```

- [ ] **Step 2: Validate the marketplace JSON**

Run: `python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); names=[p['name'] for p in d['plugins']]; assert 'agent-advisor' in names; print('marketplace OK:', names)"`
Expected: `marketplace OK: [..., 'agent-advisor']`.

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/marketplace.json
git commit -m "feat(agent-advisor): register plugin in startups-for-aws marketplace"
```

---

### Task 14: Install-time verification (shared-reference reads)

**Files:**
- None (verification task; may produce a short `INSTALL_VERIFICATION.md` note if issues found).

**Interfaces:**
- Consumes: the installed plugin.
- Produces: confirmation that `${CLAUDE_PLUGIN_ROOT}` shared reads resolve from both skills
  (spec §3.2, §13). This is the gate that the shared-folder design actually works on a real
  install, not just `--plugin-dir`.

- [ ] **Step 1: Install the plugin for real**

Run (the user does this in their session): `/plugin install agent-advisor@startups-for-aws`
Expected: install succeeds; both skills appear in the skills list.

- [ ] **Step 2: Trigger the main skill and confirm a shared read**

Trigger `agent-advisor` (e.g. "which runtime for my agent?"). During Design, confirm the skill
successfully reads `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/<verdict>.md` (the service
card content appears). If it cannot resolve the path, the shared-folder approach failed — fall
back to the documented symlink option (spec §3.2) and re-test.

- [ ] **Step 3: Trigger add-capabilities and confirm its shared read**

Invoke `/agent-advisor:add-capabilities`; confirm it reads the agentcore.md section via
`${CLAUDE_PLUGIN_ROOT}`.

- [ ] **Step 4: Confirm scoring runs end-to-end on the install**

Confirm `uv run --project ${CLAUDE_PLUGIN_ROOT}/scripts python ${CLAUDE_PLUGIN_ROOT}/scripts/scoring.py <answers.json>`
produces `scoring-result.json` and prints `RESULT=ok VERDICT=...`. Confirm `scripts/uv.lock`
was committed (Plan 1 Task 1) so this run does not modify the source tree.

- [ ] **Step 5: Test a local `--plugin-dir` install**

Install via `--plugin-dir` pointing at the repo's `migrate/plugins/agent-advisor` and trigger
the main skill. Confirm: (a) shared reads still resolve, and (b) `uv run` does NOT create or
modify files in the source tree (it should reuse the committed `uv.lock`). If `uv.lock` is
regenerated, that is a finding — the lock was not committed correctly.

- [ ] **Step 6: Test on Cursor (the relative-path fallback)**

Install on Cursor (inline mode). Trigger the skill and confirm shared reads resolve. If
`${CLAUDE_PLUGIN_ROOT}` does not substitute on Cursor, confirm the SKILL.md relative-path
fallback (`../shared/...`, `../../scripts/...`) works instead. Record which path style each
platform needed.

- [ ] **Step 7: Record the result**

If everything resolves on all platforms, note it in the PR description. If a fallback was
needed (relative paths on Cursor, or the documented symlink option from spec §3.2 if the shared
folder doesn't resolve at all), document it in
`migrate/plugins/agent-advisor/INSTALL_VERIFICATION.md` and adjust the SKILL.md path guidance
accordingly, then commit.

---

## Self-Review

**Spec coverage (Plan 2 scope — orchestration):**
- §2 positioning, thin-advisory boundary, in/out scope → manifests (T1), SKILL routing (T3), handoff (T8), README (T12) ✓
- §3.1 plugin structure (two skills, shared) → T1-T12 file layout ✓
- §3.2 shared reads via `${CLAUDE_PLUGIN_ROOT}`, install verification → T3/T8/T11 path style + T14 ✓
- §3.3 state machine, `.agent-advisor/` dir, phase gate → T3, T4 ✓
- §4 four entry points + Migrate handoff after Design → T3 routing, T8 handoff ✓
- §5 Turn 1 two questions + background adapts input only → T4, T6 (technical/business files, same keys) ✓
- §6.1/6.2 scoring via uv (file-in/out) → T6 Step 5 ✓
- §6.3 minimal model default, defer pricing → T2 model-defaults.md, consumed in T8/T10 ✓
- §6.4 cost reuses migration-to-aws pricing pattern (cache + staleness + MCP fallback + pricing_source) → T9 ✓
- §7 Lambda MicroVMs first-class: service card, differentiating questions in Clarify, 5 TPS warning surfaced → T2 lambda-microvms.md, T6 (compute_tier/idle_resume/launch_concurrency), T10 Step 5 ✓
- §8 registry consumed (profiles read by scoring.py; volatile_facts refreshed) → T6 Step 5, T8 Step 3 ✓
- §9 layered hybrid knowledge: cached refs primary + awsknowledge MCP for volatile → T2 (cards + freshness.md), T8 Step 3 ✓
- §10 + §10.1 layered single doc + diagram insertion point → T10 template + generate Step 2 (diagram from Plan 3) ✓
- §11 error handling (MCP fail→cached+footer, critical blank, co_recommend, no_viable, 5 TPS, downstream not installed) → T6 critical rule, T7 co/no-viable, T8/T9 fallback, T8 handoff install guidance ✓
- §12 three manifests + inline mode + marketplace → T1, T13 ✓
- §13 install-time verification checklist → T14 ✓

**Placeholder scan:** No TBD/TODO. The one forward reference is Generate Step 2 pointing at
Plan 3's `build-diagram.md`, with an explicit fallback if Plan 3 isn't installed yet — not a
placeholder, a documented cross-plan dependency.

**Type/name consistency:** scoring keys and legal values in clarify.md (T6) match Plan 1's
DIMENSIONS exactly. `verdict` / `deployment_model` / `agentcore_services` / `warnings` /
`model_recommendation` consumed in T7/T8/T10 match Plan 1's `scoring-result.json` schema.
`$RUN_DIR`, `$PLUGIN`, `.phase-status.json` keys consistent across T3-T10. Entry-point ids
(`build_scratch`/`build_deploy`/`migrate`/`add_capabilities`) consistent T3/T4/T8.

**Cross-plan contract (Kiro review fix):** `pass2.json` `chosen_runtime` is now explicitly
written by T7 Step 5 for co_recommend verdicts — this is the key Plan 3's diagram composer
reads to know which tied runtime to draw. `agentcore_services` in `pass2.json` is the final
list Plan 3 prefers over the scoring default.

**Determinism boundary (Kiro review):** T5 discover.md explicitly flags LLM-interpreted
pre-fills as the one non-deterministic input (with a user-correction opportunity); T9
estimate.md flags the LLM-layer cost magnitude as a future determinism candidate. T7 Step 4's
no_viable re-scoring path shows the explicit `uv run scoring.py` command (not just a prose
reference).

---

## Next plan

- **Plan 3 — Architecture diagram:** `references/diagram/` fragments (Mermaid + ASCII pair per
  runtime / service / edge), `build-diagram.md` composition keyed by `scoring-result.json` +
  `pass2.json`, golden-output diagram tests, handoff annotation for ECS/EKS/Lambda verdicts.
  Generate phase Step 2 (Task 10) is its integration point.
