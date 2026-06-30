# Agent Advisor Plugin — Design Spec

**Date:** 2026-06-30
**Status:** Approved design, pending implementation plan
**Author:** Gen Li (with Claude)

---

## 1. Summary

`agent-advisor` is a new Claude Code plugin (also shipped for Cursor and Codex) that
helps startups decide **how and where to run AI agents on AWS**. Given a customer's
situation, it recommends a runtime (AgentCore Runtime, Lambda MicroVMs, ECS, EKS, or
Lambda Standard), an AgentCore deployment model and service set, and a default Bedrock
model — backed by a deterministic, testable scoring engine. It produces a layered
recommendation document plus lightweight scaffolding, and hands off heavy artifact
generation (Terraform, migration execution) to the existing `migration-to-aws` and
`ai-to-aws` plugins.

It is the third plugin in the `startups-for-aws` marketplace, alongside
`migration-to-aws` and `ai-to-aws`.

### Heritage

A working prototype was validated on Amazon Quick
(`migrate/plugins/agent-advisor/doc/aws_agent_advisor/`). Its decision engine
(`scoring.py`, `decision_matrix.md`, runtime service cards) is platform-agnostic and is
carried over. The interaction layer (decision cards, session-tab questionnaires) and the
SA-facing framing are **not** carried over — they are replaced to fit Claude Code and a
startup-self-serve audience.

---

## 2. Positioning & Scope

### Target user

External startup customers, self-serving inside their IDE / Claude Code. For the
**Migrate** entry point, SAs/AMs may run it on a customer's behalf, but the plugin does
**not** do internal-user identity verification — per PM direction, "solve for the external
customer only" while accommodating users of different technical backgrounds.

> PM alignment (Shrey Kapoor, design discussion): target is mostly external users; for the
> migration use case SA/AMs may use it on behalf of customers; no identity-verification
> step; the plugin must serve non-technical users without leaving them unable to answer.

### Boundary: thin advisory layer

`agent-advisor` owns **decision + justification** and **lightweight scaffolding**. It does
**not** own heavy artifact generation:

| Concern | Owner |
| --- | --- |
| Runtime / service / model selection + rationale | **agent-advisor** |
| Recommendation document | **agent-advisor** |
| Lightweight scaffolding (`harness.json` skeleton, framework starter, deploy config) | **agent-advisor** (Build paths) |
| Coarse cost magnitude | **agent-advisor** (Build/Add paths) |
| Terraform / migration scripts / provider adapters | `migration-to-aws` / `ai-to-aws` (handoff) |
| Full TCO comparison, model mapping with pricing | `migration-to-aws` (handoff) |
| Code rewrite, eval, ready-to-merge branch | `ai-to-aws` (handoff) |

### In scope (v1)

- Four entry points: Build-from-idea, Build-deploy-existing-code, Migrate, Add-capabilities
- Deterministic runtime scoring across 5 runtimes (incl. Lambda MicroVMs as a first-class
  scored runtime)
- AgentCore deployment-model selection (Harness vs Framework on Runtime)
- AgentCore service selection (on any runtime)
- Lightweight Bedrock model **default** (not a full mapping table)
- Lightweight detection of existing code (Build-deploy / Add paths)
- Layered recommendation document (business summary + technical data in one doc)
- Coarse cost magnitude for Build/Add
- Lightweight scaffolding for Build paths
- Handoff to `migration-to-aws` / `ai-to-aws` for Migrate and for heavy artifacts
- Managed alternatives (Claude/Bedrock Managed Agents) surfaced as awareness with tradeoffs
- Runtime registry + volatile-fact externalization for future extensibility

### Out of scope (v1)

- Internal-user identity verification
- Full Terraform/IaC generation (handed off)
- Migration execution (handed off)
- Full TCO / per-model pricing comparison (handed off)
- Source-model → Bedrock migration mapping table with pricing (handed off; agent-advisor
  keeps only a coarse family-level default)
- Bedrock model benchmarking
- Multi-session memory (stateless per conversation, except the on-disk run state)
- SA-facing audience/tone forking

---

## 3. Architecture Overview

### 3.1 Plugin structure (two skills, shared references)

```
agent-advisor/
├── .claude-plugin/plugin.json        # Claude Code manifest (no hard dependencies)
├── .cursor-plugin/plugin.json        # Cursor manifest
├── .codex-plugin/plugin.json         # Codex manifest
├── README.md
├── scripts/                          # uv project (same pattern as ai-to-aws)
│   ├── pyproject.toml
│   ├── scoring.py                    # generic scoring engine (registry-driven)
│   ├── test_scoring.py               # parametrized over runtime profiles
│   └── schemas/
│       ├── answers.json              # Clarify output schema
│       └── scoring-result.json       # scoring.py output schema
└── skills/
    ├── shared/                       # canonical knowledge, referenced by both skills
    │   ├── runtimes/                 # ← runtime REGISTRY (one profile per runtime)
    │   │   ├── agentcore.yaml
    │   │   ├── lambda-microvms.yaml
    │   │   ├── ecs.yaml
    │   │   ├── eks.yaml
    │   │   └── lambda.yaml
    │   └── decision-refs/
    │       ├── decision-matrix.md    # human-readable view (generated from registry)
    │       ├── agentcore.md  ecs.md  eks.md  lambda.md  lambda-microvms.md  # service cards
    │       ├── managed-alternatives.md
    │       ├── model-defaults.md
    │       └── freshness.md           # MCP query field list + footer template
    ├── agent-advisor/                # main skill: Build / Migrate
    │   ├── SKILL.md                  # state machine + Turn 1 + answer mapping
    │   └── references/
    │       ├── phases/
    │       │   ├── discover.md
    │       │   ├── clarify-technical.md
    │       │   ├── clarify-business.md
    │       │   ├── clarify-pass2.md
    │       │   ├── design.md
    │       │   ├── estimate.md
    │       │   └── generate.md
    │       ├── output-templates/recommendation-doc.md
    │       └── handoff/handoff-migration.md
    └── add-capabilities/             # standalone skill: already on AWS, add services
        └── SKILL.md
```

### 3.2 Shared-reference access (verified)

Both skills read the same canonical files under `skills/shared/`. Per official Claude Code
docs (verified during design):

- The shared folder **must live inside the plugin root** (files outside are not copied into
  the install cache).
- SKILL.md references shared files with an **explicit Read instruction using
  `${CLAUDE_PLUGIN_ROOT}`**, e.g.:
  > Read `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/agentcore.md` for the service card.
- Do **not** use bare `../shared/...` relative links (resolved against CWD, fragile).
- `${CLAUDE_PLUGIN_ROOT}` is documented to substitute inline in skill content.

**Implementation-time gate:** after a real `claude plugin install`, trigger both skills and
confirm the shared reads resolve. Local `--plugin-dir` runs preserve fewer cases, so this
must be validated on an actual install.

### 3.3 State machine

Reuses the `migration-to-aws` state-machine pattern, lightened. Run state lives in
`.agent-advisor/[MMDD-HHMM]/` (separate from `.migration/` so both plugins can coexist).

Phases: **Discover → Clarify (Pass 1) → [score] → Clarify (Pass 2) → Design →
Estimate → Generate**, gated by entry point.

```
Turn 1 (entry point + technical background)
   │
   ▼
Discover ──(Build-deploy / Add, when code present)── lightweight detection → context-signals.json
   │   (Build-from-idea skips Discover)
   ▼
Clarify Pass 1 — core scoring questions (wording adapted to background) → answers.json
   │   (critical blank: session_duration → ask in chat before scoring)
   ▼
[uv run scoring.py]  answers.json → scoring-result.json   (deterministic, file-in/file-out)
   │
   ▼
Clarify Pass 2 — questions specific to the winning runtime (AgentCore services / deployment model)
   │
   ▼
Design — assemble recommendation (runtime + deployment model + services + model default)
   │
   ├─ Migrate entry point ──→ decision summary + handoff (migration-to-aws / ai-to-aws). STOP.
   │
   ▼ (Build / Add)
Estimate — coarse cost magnitude (not precise; "verify" disclaimer)
   │
   ▼
Generate — layered recommendation doc + lightweight scaffolding
```

**Phase gate:** Clarify must complete before Design/Estimate/Generate (same discipline as
`migration-to-aws`). Scoring is never done "in the model's head" — it is always the output of
`scoring.py`, so results are deterministic and unit-testable.

---

## 4. Entry Points & Flow

| Entry point | Discover | Clarify | Design | Estimate | Generate | Terminal |
| --- | --- | --- | --- | --- | --- | --- |
| **Build-from-idea** (no code) | skip | full (Pass 1+2) | runtime+model+services | coarse cost | doc + scaffold | done |
| **Build-deploy** (has code) | lightweight detection | fewer (auto-detected) | + framework-specific deploy notes | coarse cost | doc + scaffold | done |
| **Add-capabilities** (on AWS) | lightweight detection | service-only (4–6 Q) | services only | service delta cost | service enablement config | done (separate skill) |
| **Migrate** (running elsewhere) | lightweight detection | runtime-decision Q | runtime+services+model decision | — | — | **handoff after Design** |

### Migrate handoff mechanism

After Design, agent-advisor emits a decision summary (recommended runtime + services +
coarse model family mapping + rationale), then:

- Checks whether `migration-to-aws` / `ai-to-aws` appear in the available-skills list.
- **Installed** → writes the decision summary to a handoff file and directs the user to
  `/ai-to-aws:llm-to-bedrock` (AI/LLM) or `migration-to-aws:gcp-to-aws` (infra/containers).
- **Not installed** → provides install guidance.

TCO and heavy artifacts are the downstream plugins' job — agent-advisor only gives a
runtime-level cost magnitude in the Design summary.

---

## 5. User Background Adaptation

Turn 1 asks **two questions** via `AskUserQuestion` (multi-question, side-by-side):

- **Q1 — Starting point:** Build-from-idea / Build-deploy / Migrate / Add-capabilities
  (drives which path fires)
- **Q2 — Technical background:** Technical / Business-leaning / Mixed team
  (drives how questions are asked)

Then an open prompt: "What can you tell me about your agent? Any files or existing code to
share?" — feeds Discover and pre-fill.

**Background drives input only; output is unified:**

- **Input (the PM's core pain point):** the *same scoring signals* are asked with different
  wording/depth.
  - Technical → direct terms ("session duration? traffic pattern? multi-tenant isolation?")
  - Business-leaning → translated to business language ("does your agent answer in seconds,
    or work for minutes/hours on a complex task?"; "do your different customers' data need
    strict separation?")
  - This is why `clarify-technical.md` and `clarify-business.md` are separate files: same
    signals, two phrasings, no cross-contamination of context.
- **Output (unified, layered):** one recommendation document that serves both — a
  business-readable summary section followed by technical data/config sections. **Not** two
  tone-forked templates.

Because both backgrounds map to the **same signal set** (session_duration, traffic_pattern,
isolation, …), `scoring.py` is unchanged regardless of background.

---

## 6. Decision Engine

### 6.1 Carried over from prototype

- `scoring.py` + `test_scoring.py` — executed via `uv run` (same toolchain pattern as
  `ai-to-aws/scripts`). File-in/file-out, deterministic.
- Runtime service cards (`agentcore.md`, `ecs.md`, `eks.md`, `lambda.md`).
- Two-pass questioning: Pass 1 = core scoring questions; Pass 2 = winner-specific follow-ups.

### 6.2 Scoring model (from prototype, extended)

**Hard-constraint elimination first, then weighted signal scoring.**

- Hard constraints eliminate a runtime before scoring (score 0).
- Each answer adds weighted points to qualifying runtimes; highest total wins.
- Ties within a threshold → co-recommend with "choose A if X / B if Y" framing.
- All eliminated → `no_viable_runtime`, surface the specific contradictions.

Deployment model (AgentCore only): Harness vs Framework on Runtime, decided by
multi-agent / framework / entry-point signals.

AgentCore services: Identity, Observability, Evaluations, Optimization always included;
others (Memory, Gateway, Policy, KB, Code Interpreter, Browser, Web Search, Sandbox)
activate on signals.

### 6.3 Model recommendation — deliberately minimal

agent-advisor does **not** reproduce the source-model → Bedrock mapping/pricing tables (they
already exist in `migration-to-aws` and `ai-to-aws`, and pricing is the most volatile data).

- `model-defaults.md` holds only a forward default (requirement → Bedrock default), used to
  fill the cost estimate and the scaffold's `modelId`. Default: Claude Sonnet 4.6 (balanced);
  Haiku 4.5 for speed/cost.
- For Migrate, the decision summary gives a **coarse family-level** mapping only; detailed
  pricing/TCO is handed off downstream.
- SKILL.md notes the canonical pricing source is `migration-to-aws`, to prevent future
  drift-prone price tables creeping into agent-advisor.

---

## 7. Lambda MicroVMs Integration

### 7.1 Research basis

Lambda MicroVMs went GA 2026-06-22. Facts were cross-verified against three independent
sources: the PM comparison doc, AWS public docs (AWS_DOCS), and Amazon-internal service
specs (the Kepler / Lambda MicroVMs team's own canary test specs).

**Verified:**

- Lifecycle hooks `/ready`, `/launch`, `/resume`, `/suspend`, `/terminate`
  (base path `/aws/lambda-microvms/runtime/beta/v1`); hook failure/timeout → VM terminated.
- Full suspend/resume preserving memory + disk + running processes (vs AgentCore Session
  Storage, which preserves filesystem only — processes must reinitialize).
- Image model: built from an S3 code artifact + base image (default `al2023`), with platform
  versions; not a native CloudFormation resource.
- Persona: a platform for running untrusted code — **not** an agent-purpose-built platform.

**Correction to the old PM decision tree:** Lambda MicroVMs max session = **8 hours**, same
as AgentCore. The old claim that it suits ">8 hours" is wrong. `>8hr` eliminates **both**
AgentCore and Lambda MicroVMs, leaving ECS/EKS.

**Note:** AgentCore now lists **Harness** as a core service that also runs each session in an
isolated microVM with filesystem + shell. So "needs shell/filesystem → Lambda MicroVMs" is
not a real differentiator; the real differentiators are in §7.3.

### 7.2 Status change

Lambda MicroVMs is promoted from "coming soon / not scored" (prototype) to a **first-class,
scored runtime**.

### 7.3 Differentiating signals (require new questions)

Its genuinely unique signals are not captured by the current questionnaire and must be added:

| Differentiator | Captured today? | Winner |
| --- | --- | --- |
| Process-level suspend/resume (freeze memory + processes, not just filesystem) | No (`session_state` only stateless/stateful/hitl) | Lambda MicroVMs |
| Compute > 2 vCPU / 8 GB but **not** GPU (compilation, ML inference, data processing) | Partially (`traffic_pattern` only has `gpu`) | Lambda MicroVMs |
| Multi-port / gRPC / per-session URL (dev envs, coding agents) | No | Lambda MicroVMs |
| High-concurrency launch > 5 TPS | No — but this is Lambda MicroVMs' hard weakness (5 TPS, not adjustable) | AgentCore |

### 7.4 Concrete changes to add it

1. New service card `lambda-microvms.md` (from PM doc + verified internal specs).
2. Hard constraints: `>8hr` eliminate, GPU eliminate, FedRAMP (verify via MCP — too new to
   hardcode).
3. Scoring: add a `lambda_microvms` column/affinity in every dimension (via its registry
   profile — see §8).
4. Two new differentiating questions:
   - **Idle-resume need:** processes must resume exactly / filesystem-persist is enough /
     not needed → separates Lambda MicroVMs from AgentCore Session Storage.
   - **Compute tier:** light (≤2 vCPU) / heavy non-GPU (>2 vCPU) / GPU → splits the GPU
     signal currently buried in `traffic_pattern`.
5. High-concurrency-launch guardrail: if Lambda MicroVMs wins but traffic is
   high-concurrency launch, the output warns about the non-adjustable 5 TPS cap.

---

## 8. Extensibility Mechanism

The research reinforced this: the service is 8 days old and its facts are still moving
(session cap "extending soon", regions expanding, FedRAMP TBD). The plugin must make facts
easy to change and new runtimes easy to add. Two layers.

### Layer 1 — Runtime registry

Each runtime is a self-contained profile under `skills/shared/runtimes/<id>.yaml`, carrying:

```yaml
id: lambda_microvms
display_name: "Lambda MicroVMs"
status: ga                      # ga | preview | coming_soon  ← lifecycle switch
launched: "2026-06-22"
service_card: lambda-microvms.md
hard_constraints:
  - {field: session_duration, value: over_8hr, reason: "8hr session cap"}
  - {field: compute_tier, value: gpu, reason: "No GPU support"}
affinities:                     # only the dimensions/values it cares about; missing = neutral
  session_duration: {15min_to_8hr: 5, under_15min: 3}
  idle_resume:       {process_level: 5, filesystem: 2, none: 1}
  compute_tier:      {heavy_non_gpu: 5, light: 2}
  ...
deployment_models: [...]        # runtime-specific Pass-2 follow-ups
volatile_facts:                 # see Layer 2
  - {key: session_cap, value: "8h", verify_via_mcp: true}
  - {key: fedramp, value: "unknown", verify_via_mcp: true}
  - {key: regions, value: [...], verify_via_mcp: true}
```

`scoring.py` becomes a generic engine: scan `runtimes/`, load all profiles whose `status`
qualifies, and for each answer ask each profile "what's your affinity for this value?",
defaulting missing dimensions to neutral.

| Operation | Before (nested dict) | After (registry) |
| --- | --- | --- |
| Add a runtime | edit every dimension + every table + cards | **add one profile file** |
| Promote Lambda MicroVMs coming_soon→ga | uncomment in several places | flip `status` |
| Pause/retire a runtime | delete scattered code | change `status` / move file |
| Re-weight a runtime | hunt its column across the whole table | edit its own profile |

`decision-matrix.md` is no longer hand-maintained; it becomes a generated/derived view of
the registry (eliminating table-vs-code drift). `test_scoring.py` is parametrized over
profiles (validate affinity values are legal dimensions, hard-constraint fields exist, etc.).

### Layer 2 — Volatile facts + MCP refresh

Fast-moving fields (session caps, regions, FedRAMP status, price) are pulled out of scoring
logic into the profile's `volatile_facts`, flagged `verify_via_mcp: true`. At runtime the
plugin prefers an `awsknowledge` MCP lookup; on failure it falls back to the cached value and
appends a freshness footer (generation date + which lookups succeeded vs fell back + verify
disclaimer). This is the "layered hybrid" knowledge strategy, realized here.

### Honest boundary

The profile model makes adding a runtime **zero-change on the scoring side**. But if a new
runtime competes on a **brand-new axis** (as Lambda MicroVMs does with suspend/resume and
multi-port), a **new question** is unavoidable — you must actually ask the user that new
signal. So the honest statement of the mechanism is:

> Add a runtime = add 1 profile file (free) + evaluate whether a differentiating question is
> needed (checklist-guided, occasional) + volatile facts auto-refresh via MCP.

---

## 9. Knowledge Layer

Layered hybrid (the mature `migration-to-aws` pattern):

| Information type | Volatility | Handling |
| --- | --- | --- |
| Runtime capability comparison, AgentCore service descriptions, six dimensions, scoring weights, framework compatibility | Low (changes ~half-yearly) | cached reference files (primary, offline-capable) |
| Exact session caps, region availability, newly-GA services, price, FedRAMP status | High (weeks/months) | `awsknowledge` MCP at runtime; on failure fall back to cached + ⚠️ freshness footer |

Source material (8 cheatsheet PNGs, the AgentCore-vs-Lambda-MicroVMs comparison doc) is
distilled into `decision-refs/*.md` at authoring time. The plugin does **not** read images at
runtime (slow, unstable, token-expensive).

MCP servers (from existing plugins' `.mcp.json`): `awsknowledge` (HTTP) for fact
verification; `awspricing` optional for any cost magnitude work.

---

## 10. Output

### In-chat mini-brief

```
**Recommendation:** [Runtime] + [Deployment model if AgentCore]
**Why:** [top 3 scoring signals]
**Eliminated:** [runtimes + reasons]
**Model:** [Bedrock default + key reason]
📄 Full recommendation doc →
```

### Recommendation document (single, layered)

One Markdown document serving both audiences (business summary first, technical depth after):

1. Executive summary (business-readable)
2. Customer profile (from answers)
3. Recommendation: primary runtime (+ rationale, scored criteria)
4. Alternatives considered (why eliminated / scored lower)
5. Comparison matrix (relevant rows)
6. Six dimensions (Identity, Observability, Guardrails, Scaling, Tool/Gateway, Protocols)
7. AgentCore services (which to enable, why — applies to all runtimes)
8. Bedrock model default (coarse family mapping for Migrate)
9. Next steps (incl. handoff pointers)
10. Freshness footer (generation date, which MCP lookups succeeded vs fell back, verify
    disclaimer)

### Build scaffolding (lightweight)

For Build paths: a minimal, runnable starting point — `harness.json` skeleton (Harness path)
or framework starter template (Framework-on-Runtime path), plus deploy config. Heavy
artifacts (Terraform, full IaC) are handed off, not generated here.

---

## 11. Error Handling

| Scenario | Behavior |
| --- | --- |
| MCP lookup fails | Fall back to cached fact, flag with "⚠️ based on cached data (date) — verify" |
| Critical question blank (session_duration) | Ask in chat before scoring |
| Non-critical blank | Safe default, note in `assumptions_used` |
| All runtimes eliminated | `no_viable_runtime` + specific contradictions + "relax X → Y viable" |
| Scoring tie (within threshold) | Co-recommend with "choose A if X / B if Y" |
| Lambda MicroVMs wins but high-concurrency launch | Warn: 5 TPS launch cap, not adjustable |
| Contradictory inputs | Flag in context summary, let user resolve |
| Downstream plugin not installed (Migrate) | Provide install guidance instead of handoff |

---

## 12. Multi-Platform Packaging

Three manifests mirror the existing plugins: `.claude-plugin/plugin.json`,
`.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`. No hard `dependencies` (the plugin
works standalone; handoff targets are checked at runtime, not required at install). Added to
the marketplace `.claude-plugin/marketplace.json` as the fourth plugin.

Inline mode: where a platform lacks `AskUserQuestion`, fall back to a Markdown questionnaire
written to disk + chat confirmation (mirrors `ai-to-aws` inline-mode handling).

---

## 13. Implementation-Time Verification Checklist

- [ ] After real `claude plugin install`, trigger both skills and confirm
      `${CLAUDE_PLUGIN_ROOT}/skills/shared/...` reads resolve (not just `--plugin-dir`).
- [ ] `test_scoring.py` passes, parametrized over all runtime profiles (legal affinity
      dimensions, hard-constraint fields exist, defaults applied).
- [ ] Lambda MicroVMs wins its intended scenarios (process-level suspend/resume; heavy
      non-GPU compute; multi-port) and loses high-concurrency-launch to AgentCore.
- [ ] `>8hr` eliminates both AgentCore and Lambda MicroVMs (regression against the old PM
      decision-tree bug).
- [ ] FedRAMP / session-cap / region facts resolve via `awsknowledge` MCP, with cached
      fallback + freshness footer when MCP is unavailable.
- [ ] Migrate path stops after Design and writes a handoff file; install guidance shown when
      downstream plugins are absent.

---

## 14. Open Items (deferred, not blocking)

- Exact wording of the new differentiating questions (idle-resume, compute-tier) — drafted in
  `clarify-*.md` during implementation.
- Whether the coarse cost magnitude for Build/Add uses `awspricing` MCP or a small cached
  table — decided during implementation per available env.
- Final registry format (YAML vs JSON) — YAML assumed here for readability; confirm against
  the uv/scoring toolchain.
