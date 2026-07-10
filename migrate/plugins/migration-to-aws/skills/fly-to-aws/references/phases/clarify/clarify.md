---
_phase: clarify
_title: "Clarify Requirements"
_requires_phase: discover
_input:
  - fly-resource-inventory.json
_assemble:
  _file: phases/clarify/clarify-assemble.md
_produces:
  - preferences.json
_advances_to: design
_re_entry_guard:
  _stale_if_completed: design
  _stale_artifact: aws-design.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: discover
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: fly-resource-inventory.json
    _on_failure: _unrecoverable
  - _validate_json: fly-resource-inventory.json
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: preferences.json
    _on_failure: _halt_and_inform
  - _validate_json: preferences.json
    _on_failure: _halt_and_inform
  - _assert: "all Validation Checklist items in clarify.md pass"
    _on_failure: _halt_and_inform
  - _assert: "audience is set and platform_preference.eks_reuse is set (non-null)"
    _on_failure: _halt_and_inform
  - _assert: "for each process group in the inventory, a process_groups.<group> entry exists with class_confirmed, scale_to_zero_intent, suspend_state_dependency, gpu_purpose all set"
    _on_failure: _halt_and_inform
  - _assert: "for each confirmed agent group, an agent_groups.<group> entry exists with advisor_requested set; region is a valid AWS region; sizing and migration_window are set"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - aws-design.json
  - "terraform/**"
  - "k8s/**"
---

# Phase 2: Clarify Requirements

**Phase 2 of 6** — Ask adaptive questions before design begins, then interpret answers into ready-to-apply design constraints.

> **HARD GATE — Clarify before Design:** Do not load `references/phases/design/design.md` (or any later phase) until this phase finishes **and** `$MIGRATION_DIR/.phase-status.json` records `phases.clarify` as `"completed"`. Writing `preferences.json` without updating phase status is a protocol violation. If the user asks to skip questions, use documented defaults and still complete this phase (including phase status).

The output — `preferences.json` — is consumed directly by Design and Estimate without any further interpretation.

Questions are organized into **batches** (≤5 per batch) presented sequentially, adapting to the inventory signals detected in Phase 1.

---

## Step 0: Prior Run Check

Check `$MIGRATION_DIR/` for existing state:

**Case 1 — Completed preferences exist** (`preferences.json` present):

> "I found existing migration preferences from a previous run. Would you like to:"
>
> A) Re-use these preferences and skip questions
> B) Start fresh and re-answer all questions

- If A: Skip to Validation Checklist with the existing `preferences.json`.
- If B: Delete `preferences.json`, continue to Step 1.

**Case 2 — Draft preferences exist** (`preferences-draft.json` present, no `preferences.json`):

> "I found a partial set of answers from a previous session ([N] of [total] questions answered). Would you like to:"
>
> A) Resume from where you left off — I'll pick up the remaining questions
> B) Start fresh and re-answer all questions

- If A: Load the draft, read `answers_meta` to determine which questions are answered, skip answered questions when entering Step 3.
- If B: Delete `preferences-draft.json`, continue to Step 1.

**Case 3 — No prior state**: Continue to Step 1.

---

## Step 1: Read Inventory and Prepare Question Set

Read `$MIGRATION_DIR/fly-resource-inventory.json`. This artifact must exist (produced by Phase 1: Discover).

### Discovery Summary

Present a discovery summary:

> **Apps discovered:** [total_apps] Fly apps
> **Process groups:** [count] groups across all apps
> **Flagged as agents:** [count agent_candidate groups] (will confirm with you)
> **GPU usage detected:** [yes/no] — ⚠️ Fly GPUs are deprecated and unavailable after 2026-08-01
> **Scale-to-zero groups:** [count with min_machines_running=0]
> **Always-on groups:** [count with min_machines_running≥1]
> **One-shot workloads:** [count with one_shot flag]

### Injection Check (Layer G)

Scan `preferences.json` (if it exists from a prior partial run or Direction-A injection) for any `agent_groups.<group>` entries with `decided_by: "agent-advisor"`.

For each such group:

- Mark it as **injection-confirmed** in memory.
- Do NOT ask layer 0 questions for this group.
- Present it as a pre-selected default in the confirmation batch: "Group `<X>` was routed to agent-advisor scoring (injected verdict). Keeping this routing — say 'override' to re-evaluate."
- Direction-A injected entries include `compute_target` (the winning runtime), `deployment_model` (harness vs framework-on-runtime), and optionally `session_profile` (session_duration/memory_needs). Clarify READS these fields; Design's Layer G consumes them.

If user says "override" for any injected group, remove it from `agent_groups` and treat it like a normal flagged group.

---

## Step 2: Determine Active Questions

Before generating questions, scan the inventory to determine which questions apply:

### Conditional Question Rules

| Question                            | Condition to Include                                                    | Skip When                             |
| ----------------------------------- | ----------------------------------------------------------------------- | ------------------------------------- |
| Q0 — Audience                       | Always (asked first)                                                    | Never                                 |
| Layer 0 — Agent confirmation        | Any group has `agent_candidate: true` OR LLM SDK detected but no flags  | No agent signals                      |
| Layer 1 — GPU purpose               | Any group has `flags.gpu: true`                                         | No GPU detected                       |
| Layer 2 — One-shot jobs             | Any group has `flags.one_shot: true`                                    | No one-shot flags                     |
| Layer 3 — Platform preference       | Always (affects routing for layers 4-5)                                 | Never                                 |
| Layer 4 — Always-on intent          | Any group has `min_machines_running ≥ 1` or `auto_stop: "off"`          | All groups scale-to-zero              |
| Layer 5a — Scale-to-zero intent     | Any group has `min_machines_running: 0` + `auto_start: true`            | All groups always-on                  |
| Layer 5b — Suspend state dependency | Fires ONLY if Layer 5a answered "deliberate" AND `auto_stop: "suspend"` | Layer 5a not deliberate or no suspend |
| Q-secrets — Secrets acknowledgment  | Always                                                                  | Never                                 |
| Q-region — Target region            | Always                                                                  | Never                                 |
| Q-sizing — Environment sizing       | Always                                                                  | Never                                 |
| Q-window — Migration window         | Always                                                                  | Never                                 |

### Batching Strategy

Organize active questions into batches of ≤5 questions each. Present one batch at a time.

**Suggested grouping:**

- Batch 1: Audience (Q0)
- Batch 2: Agent confirmation (Layer 0, per-group + catch-all)
- Batch 3: GPU purpose (Layer 1, per-group)
- Batch 4: One-shot jobs (Layer 2, per-group)
- Batch 5: Platform preference (Layer 3, once per app)
- Batch 6: Always-on intent (Layer 4, per-group)
- Batch 7: Scale-to-zero intent (Layer 5a/5b, per-group)
- Batch 8: Cross-cutting (secrets, region, sizing, window)

If a batch would exceed 5 questions, split into sub-batches.

Record the ordered list of active batches.

---

## Step 3: Present Questions in Progressive Batches

### Batch Loop

For each active batch, execute steps 3a–3d:

#### 3a. Present Batch

Use a conversational tone with brief context explaining why each question matters.

**Batch 1 — Audience (always first):**

```
Before designing your AWS architecture, I have a few sections of questions
to tailor the migration plan. You can answer each, skip individual ones
(I'll use sensible defaults), or say "use defaults for the rest" at any point.

Let's start with understanding your audience.

--- Audience ---

Q0: Who will be managing this infrastructure on AWS?

A) Technical team — developers/DevOps who are comfortable with infrastructure-as-code
B) Business/product team — prefer managed services and minimal operational overhead
```

**Batch 2 — Agent Confirmation (Layer 0, if applicable):**

```
Got it — I'll tailor explanations for [technical/business] users.

Next: [N] process groups were flagged as potential AI agents based on code analysis.
Let me confirm each one with you.

--- AI Agent Confirmation ---

[Per flagged group with evidence:]
Group `<X>` looks like an AI agent. Evidence:
- <evidence item 1>
- <evidence item 2>
- ...

Is `<X>` actually an AI agent?

[If LLM SDK present but no group flagged:]
None of your process groups were flagged as AI agents, but your dependencies include an LLM SDK (e.g., OpenAI, Anthropic).
Is any group actually an agent? If yes, which one(s)?
```

**For each confirmed agent group**, immediately present the advisor handoff offer:

> Group `<X>` is an AI agent — its runtime deserves the full scoring pass (AgentCore vs MicroVMs vs ECS/EKS/Lambda). Run it now? The rest of your resources continue in this migration flow either way.
>
> A) Yes — run agent-advisor scoring for `<X>` (embedded in this skill)
> B) No — continue routing `<X>` with generic compute rules

Record user choice:

- Yes → `agent_groups.<group>.advisor_requested: true` + mark for Design's embedded run (Task 8)
- No → `agent_groups.<group>.advisor_requested: false` + note "scoring offered and declined" + group falls through to layers 1-5

**Batch 3 — GPU Purpose (Layer 1, if applicable):**

```
[Agent confirmation complete.]

I detected GPU usage in [N] group(s). Let me understand the use case.

--- GPU Purpose ---

⚠️ **Important:** Fly GPUs are deprecated and unavailable after 2026-08-01. Migration is urgent.

[Per GPU-flagged group:]
Group `<X>` uses GPU. Is the GPU for:

A) Custom compute workloads (training, simulation, rendering)
B) Hosted LLM inference (the end goal is to run an LLM)
```

**Batch 4 — One-Shot Jobs (Layer 2, if applicable):**

```
[GPU purpose recorded.]

Some groups look like batch workloads rather than services. Let me confirm.

--- One-Shot Jobs ---

[Per one-shot-flagged group:]
Is `<X>` a job (runs and exits) rather than a service?

A) Yes — it's a job/task
B) No — it's a long-running service
```

**Batch 5 — Platform Preference (Layer 3, always fires once per app):**

```
[One-shot jobs confirmed.]

Next: platform preference for your compute workloads.

--- Platform Preference ---

Does your team already operate EKS/Kubernetes and want to reuse it for this migration?

A) Yes — we have EKS and want to consolidate there
B) No — we prefer Fargate (serverless containers)
```

**Batch 6 — Always-On Intent (Layer 4, if applicable):**

```
[Platform preference recorded.]

Some groups run always-on today (`min_machines_running ≥ 1`). Let me confirm intent.

--- Always-On Requirements ---

[Per always-on group:]
Group `<X>` runs always-on today — requirement, or just how it was set up?

A) Hard requirement — must always be running
B) Just the default — can scale to zero if it saves cost
```

**Batch 7 — Scale-to-Zero Intent (Layer 5a/5b, if applicable):**

```
[Always-on intent recorded.]

Some groups scale to zero when idle. Let me understand the intent.

--- Scale-to-Zero Configuration ---

[Per scale-to-zero group:]
Your app scales to zero when idle (`min_machines_running: 0` + `auto_start: true`).

Is this a deliberate cost requirement, or just the `fly launch` default?

A) Deliberate — cost optimization is intentional
B) Inherited default — just came with the setup

[If A selected AND `auto_stop: "suspend"` for this group:]

Follow-up: Does your app depend on resuming with in-memory state (e.g., session data, caches)?

A) Yes — in-memory state matters
B) No — cold start is fine

**Important context:** Fly's `min_machines_running` config applies to the primary region only. Fly-proxy does NOT create machines for autoscaling or multi-region floors. We won't assume your Fly config expressed multi-region floors or autoscaling intent.
```

**Batch 8 — Cross-Cutting (always fires):**

```
[Scaling preferences recorded.]

Last section — a few operational questions, then we're ready to design.

--- Operational Preferences ---

Q-secrets: Fly secret values cannot be exported — you'll re-provision each from its source.
Ready to list where your secrets live? (Secret names came from your `fly secrets list` export.)

Q-region: Which AWS region should your infrastructure be deployed to?
A) us-east-1 (N. Virginia) — lowest latency to East Coast, most services available
B) us-west-2 (Oregon) — West Coast
C) eu-west-1 (Ireland) — Europe
D) Other — specify a valid AWS region code

Q-sizing: What environment sizing should we target?
A) dev — cost-optimized, single-AZ where possible
B) staging — production-like with reduced capacity
C) production — multi-AZ, high availability

Q-window: When would you like to complete the migration?
A) ASAP — within 1-2 weeks
B) Planned — 1-2 months
C) Flexible — no hard deadline
```

#### 3b. Wait for Response

Wait for the user's response to the current batch. Do NOT present the next batch or proceed to Design without a response or an explicit "use defaults for the rest."

**"Use defaults for the rest" handling:** If the user says this at any point:

1. Apply documented defaults for all unanswered questions in the current batch.
2. Apply documented defaults for all questions in remaining batches.
3. Record each defaulted answer with `chosen_by: "default"`.
4. Skip directly to Step 4 (write final `preferences.json`).

#### 3c. Interpret Batch Answers and Validate

For each answered question, apply the interpretation rule. For skipped questions within the batch, apply the documented default.

**Input Validation:**

- **Audience (Q0):** Must be A or B.
- **Agent confirmation (Layer 0):** Yes/No per group, or user-volunteered group name(s).
- **GPU purpose (Layer 1):** Must be A or B per group.
- **One-shot jobs (Layer 2):** Must be A or B per group.
- **Platform preference (Layer 3):** Must be A or B.
- **Always-on intent (Layer 4):** Must be A or B per group.
- **Scale-to-zero intent (Layer 5a):** Must be A or B per group.
- **Suspend state dependency (Layer 5b):** Must be A or B per group (only if Layer 5a = deliberate + auto_stop=suspend).
- **Secrets acknowledgment (Q-secrets):** Any response accepted; record acknowledgment.
- **Region (Q-region):** Must be valid AWS region code (e.g., `us-east-1`, `eu-west-1`). Reject invalid codes.
- **Sizing (Q-sizing):** Must be A, B, or C.
- **Window (Q-window):** Must be A, B, or C.

If the user provides a response that does not match the valid options for a question:

1. Reject the input.
2. Present an error message indicating the valid options.
3. Re-prompt the same question without advancing.

Example:

> "That's not a valid option for [question topic]. Please choose from: [list valid options]"

#### 3d. Save Draft

**If more batches remain** after this one: Write (or update) `$MIGRATION_DIR/preferences-draft.json` with all answers collected so far:

```json
{
  "metadata": {
    "draft": true,
    "batches_completed": 3,
    "total_batches": 8,
    "timestamp": "<ISO timestamp>"
  },
  "audience": "technical",
  "platform_preference": { "eks_reuse": false },
  "process_groups": {
    "web": {
      "class_confirmed": "agent",
      "advisor_requested": true,
      "scale_to_zero_intent": "n/a",
      "suspend_state_dependency": "n/a",
      "gpu_purpose": "n/a"
    }
  },
  "agent_groups": {},
  "region": "us-east-1",
  "sizing": "dev",
  "answers_meta": {
    "audience": { "chosen_by": "user" },
    "platform_preference.eks_reuse": { "chosen_by": "user" },
    "process_groups.web.class_confirmed": { "chosen_by": "user" },
    "process_groups.web.advisor_requested": { "chosen_by": "user" }
  }
}
```

Return to **3a** for the next batch.

**If this was the last active batch**: Do not write a draft — proceed to Step 4.

---

## Question Catalog & Interpretation Rules

### Q0 — Audience

**Question:**

> Who will be managing this infrastructure on AWS?
>
> A) Technical team — developers/DevOps who are comfortable with infrastructure-as-code
> B) Business/product team — prefer managed services and minimal operational overhead

**Interpret:**

- A → `audience: "technical"`
- B → `audience: "business"`

**Default:** A → `audience: "technical"`

**Impact:** Wording of later questions and explanations adapts to audience.

---

### Layer 0 — AI Agent Confirmation

**Per flagged group:**

> Group `<X>` looks like an AI agent (evidence: `<list>`). Is it?
>
> A) Yes
> B) No

**Catch-all (if LLM SDK present but no group flagged):**

> None of your process groups were flagged as AI agents, but your dependencies include an LLM SDK. Is any group actually an agent? If yes, which one(s)?

**Interpret:**

- Yes (or user-volunteered group) → `process_groups.<group>.class_confirmed: "agent"`
- No → `process_groups.<group>.class_confirmed: null` (falls through to layers 1-5)

**For each confirmed agent group**, immediately offer the advisor handoff:

> Group `<X>` is an AI agent — its runtime deserves the full scoring pass (AgentCore vs MicroVMs vs ECS/EKS/Lambda). Run it now? The rest of your resources continue in this migration flow either way.
>
> A) Yes — run agent-advisor scoring
> B) No — continue with generic compute routing

**Interpret:**

- A → `agent_groups.<group>.advisor_requested: true` + mark for Design's embedded run
- B → `agent_groups.<group>.advisor_requested: false` + note + falls through

**Default:** If no agent signals detected → skip entirely.

---

### Layer 1 — GPU Purpose

**Per GPU-flagged group:**

> ⚠️ **Important:** Fly GPUs are deprecated and unavailable after 2026-08-01. Migration is urgent.
>
> Group `<X>` uses GPU. Is the GPU for:
>
> A) Custom compute workloads (training, simulation, rendering)
> B) Hosted LLM inference (the end goal is to run an LLM)

**Interpret:**

- A → `process_groups.<group>.gpu_purpose: "compute"`
- B → `process_groups.<group>.gpu_purpose: "llm_inference"`

**Default:** A → `gpu_purpose: "compute"`

**Routing:**

- `compute` → EC2 GPU instances (a10 → g5, l40s → g6e, a100-40gb → p4d, a100-80gb → p4de)
- `llm_inference` → Bedrock (point to `llm-to-bedrock` skill)

---

### Layer 2 — One-Shot Jobs

**Per one-shot-flagged group:**

> Is `<X>` a job (runs and exits) rather than a service?
>
> A) Yes — it's a job/task
> B) No — it's a long-running service

**Interpret:**

- A → `process_groups.<group>.class_confirmed: "one_shot"`
- B → `process_groups.<group>.class_confirmed: null` (falls through to layers 3-5)

**Default:** If `flags.one_shot: true` in inventory → A; otherwise skip.

**Routing:** Lambda / AWS Batch / ECS scheduled task by duration + trigger.

---

### Layer 3 — Platform Preference

**Once per app:**

> Does your team already operate EKS/Kubernetes and want to reuse it for this migration?
>
> A) Yes — we have EKS and want to consolidate there
> B) No — we prefer Fargate (serverless containers)

**Interpret:**

- A → `platform_preference.eks_reuse: true`
- B → `platform_preference.eks_reuse: false`

**Default:** B → `platform_preference.eks_reuse: false`

**Impact:** Sets target _flavor_ for layers 4-5 (EKS vs Fargate). Does not route by itself.

---

### Layer 4 — Always-On Intent

**Per always-on group:**

> Group `<X>` runs always-on today (`min_machines_running ≥ 1` or `auto_stop: "off"`) — requirement, or just how it was set up?
>
> A) Hard requirement — must always be running
> B) Just the default — can scale to zero if it saves cost

**Interpret:**

- A → `process_groups.<group>.class_confirmed: "always_on"` + `scale_to_zero_intent: "n/a"`
- B → `process_groups.<group>.class_confirmed: null` (evaluate as layer 5) + `scale_to_zero_intent: "inherited_default"`

**Default:** A → `class_confirmed: "always_on"`

**Routing:**

- Hard requirement → Fargate (or EKS per layer 3)
- Not a requirement → evaluate as layer 5

---

### Layer 5a — Scale-to-Zero Intent

**Per scale-to-zero group:**

> Your app scales to zero when idle (`min_machines_running: 0` + `auto_start: true`).
>
> Is this a deliberate cost requirement, or just the `fly launch` default?
>
> A) Deliberate — cost optimization is intentional
> B) Inherited default — just came with the setup

**Important context:** Fly's `min_machines_running` config applies to the primary region only. Fly-proxy does NOT create machines for autoscaling or multi-region floors. We won't assume your Fly config expressed multi-region floors or autoscaling intent.

**Interpret:**

- A → `process_groups.<group>.scale_to_zero_intent: "deliberate"` + proceed to Layer 5b if `auto_stop: "suspend"`
- B → `process_groups.<group>.scale_to_zero_intent: "inherited_default"` + `class_confirmed: "always_on"` (route to Fargate min-1)

**Default:** B → `scale_to_zero_intent: "inherited_default"`

**Routing:**

- Deliberate → deterministic three-way (see compute routing table Layer 5)
- Inherited default → Layer 4 route (Fargate) + idle-cost note

---

### Layer 5b — Suspend State Dependency

**Only fires if Layer 5a = deliberate AND `auto_stop: "suspend"` for this group:**

> Follow-up: Does your app depend on resuming with in-memory state (e.g., session data, caches)?
>
> A) Yes — in-memory state matters
> B) No — cold start is fine

**Interpret:**

- A → `process_groups.<group>.suspend_state_dependency: "yes"`
- B → `process_groups.<group>.suspend_state_dependency: "no"`

**Default:** B → `suspend_state_dependency: "no"`

**Routing:**

- Yes → Lambda MicroVMs (suspend/resume parity) with caveat: Fly does not guarantee snapshot persistence (apps already handle cold-start fallback — verify theirs does)
- No → Lambda (if fits function model) or Lambda MicroVMs (if containerized/stateful)

---

### Q-secrets — Secrets Acknowledgment

**Question:**

> Fly secret values cannot be exported — you'll re-provision each from its source. Ready to list where your secrets live? (Secret names came from your `fly secrets list` export.)

**Interpret:** Any response → record acknowledgment as `secrets_acknowledged: true`.

**Default:** Skip if user says "use defaults for the rest" → `secrets_acknowledged: false`.

---

### Q-region — Target AWS Region

**Question:**

> Which AWS region should your infrastructure be deployed to?
>
> A) us-east-1 (N. Virginia) — lowest latency to East Coast, most services available
> B) us-west-2 (Oregon) — West Coast
> C) eu-west-1 (Ireland) — Europe
> D) Other — specify a valid AWS region code

**Interpret:**

- A → `region: "us-east-1"`
- B → `region: "us-west-2"`
- C → `region: "eu-west-1"`
- D → validate user-provided region code; `region: "<user value>"`

**Default:** A → `region: "us-east-1"`

**Valid AWS regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, ap-northeast-2, ap-south-1, sa-east-1, ca-central-1, etc. Reject non-existent codes.

---

### Q-sizing — Environment Sizing

**Question:**

> What environment sizing should we target?
>
> A) dev — cost-optimized, single-AZ where possible
> B) staging — production-like with reduced capacity
> C) production — multi-AZ, high availability

**Interpret:**

- A → `sizing: "dev"`
- B → `sizing: "staging"`
- C → `sizing: "production"`

**Default:** A → `sizing: "dev"`

**Impact:** Affects instance sizing, AZ distribution, and cost optimization in Design.

---

### Q-window — Migration Window

**Question:**

> When would you like to complete the migration?
>
> A) ASAP — within 1-2 weeks
> B) Planned — 1-2 months
> C) Flexible — no hard deadline

**Interpret:**

- A → `migration_window: "asap"`
- B → `migration_window: "planned"`
- C → `migration_window: "flexible"`

**Default:** C → `migration_window: "flexible"`

---

## Step 4: Assemble and Write preferences.json

Assemble all interpreted answers into the final `$MIGRATION_DIR/preferences.json`. If `preferences-draft.json` exists, use it as the base — merge in the final batch's answers, remove draft-specific metadata fields (`draft`, `batches_completed`, `total_batches`), and set timestamp to current time.

Write `$MIGRATION_DIR/preferences.json`:

```json
{
  "migration_id": "<from .phase-status.json>",
  "skill": "fly-to-aws",
  "metadata": {
    "timestamp": "<ISO timestamp>",
    "questions_asked": 15,
    "questions_defaulted": ["Q-window"],
    "questions_skipped_not_applicable": ["Layer1-gpu"]
  },
  "audience": "technical",
  "platform_preference": {
    "eks_reuse": false
  },
  "process_groups": {
    "web": {
      "class_confirmed": "agent",
      "scale_to_zero_intent": "n/a",
      "suspend_state_dependency": "n/a",
      "gpu_purpose": "n/a"
    },
    "worker": {
      "class_confirmed": "always_on",
      "scale_to_zero_intent": "n/a",
      "suspend_state_dependency": "n/a",
      "gpu_purpose": "n/a"
    },
    "task": {
      "class_confirmed": "one_shot",
      "scale_to_zero_intent": "n/a",
      "suspend_state_dependency": "n/a",
      "gpu_purpose": "n/a"
    }
  },
  "agent_groups": {
    "web": {
      "advisor_requested": true,
      "decided_by": null
    }
  },
  "region": "us-east-1",
  "sizing": "dev",
  "migration_window": "flexible",
  "secrets_acknowledged": true,
  "answers_meta": {
    "audience": { "chosen_by": "user" },
    "platform_preference.eks_reuse": { "chosen_by": "user" },
    "process_groups.web.class_confirmed": { "chosen_by": "user" },
    "process_groups.web.advisor_requested": { "chosen_by": "user" },
    "process_groups.worker.class_confirmed": { "chosen_by": "user" },
    "process_groups.task.class_confirmed": { "chosen_by": "user" },
    "region": { "chosen_by": "user" },
    "sizing": { "chosen_by": "user" },
    "migration_window": { "chosen_by": "default" },
    "secrets_acknowledged": { "chosen_by": "user" }
  }
}
```

### Schema Rules

1. **`process_groups` structure:** One entry per process group from inventory. Each entry has:
   - `class_confirmed`: `"always_on"` | `"scale_to_zero"` | `"one_shot"` | `"gpu"` | `"agent"` | `null`
   - `scale_to_zero_intent`: `"deliberate"` | `"inherited_default"` | `"n/a"`
   - `suspend_state_dependency`: `"yes"` | `"no"` | `"n/a"`
   - `gpu_purpose`: `"compute"` | `"llm_inference"` | `"n/a"`

2. **`agent_groups` structure:** Only present for confirmed agent groups. Each entry has:
   - `advisor_requested`: `true` | `false`
   - `decided_by`: `"agent-advisor"` | `"user"` | `null` (set by Direction-A injection or Task 8 embedded run; clarify only reads this)
   - `compute_target`: `"<advisor runtime verbatim>"` (optional, present when injected by Direction-A or decided by embedded run)
   - `deployment_model`: `"harness"` | `"framework_on_runtime"` (optional, injected by Direction-A or decided by embedded run)
   - `session_profile`: `{"session_duration": "...", "memory_needs": "..."}` (optional, injected by Direction-A, informs sizing/services)

3. **`answers_meta` structure:** Records how each answer was obtained. Keys are dotted paths matching the preference keys. Values are objects with:
   - `chosen_by`: `"user"` | `"default"` | `"injected"`

4. **Enum alignment:** All `class_confirmed`, `scale_to_zero_intent`, `suspend_state_dependency`, and `gpu_purpose` values MUST match the schema in the task brief exactly.

5. **Non-applicable values:** Use `"n/a"` for fields that do not apply to a given group (e.g., `gpu_purpose: "n/a"` for a non-GPU group).

6. Only write keys with non-null values. Omit sections/keys that are entirely null or empty objects.

After writing `preferences.json`, delete `$MIGRATION_DIR/preferences-draft.json` if it exists.

---

## Defaults Table

| Question                        | Default                                         |
| ------------------------------- | ----------------------------------------------- |
| Q0 — Audience                   | A → `audience: "technical"`                     |
| Layer 0 — Agent confirmation    | (no default — must confirm if flagged)          |
| Layer 1 — GPU purpose           | A → `gpu_purpose: "compute"`                    |
| Layer 2 — One-shot jobs         | A (if `one_shot: true` in inventory)            |
| Layer 3 — Platform preference   | B → `eks_reuse: false`                          |
| Layer 4 — Always-on intent      | A → `class_confirmed: "always_on"`              |
| Layer 5a — Scale-to-zero intent | B → `scale_to_zero_intent: "inherited_default"` |
| Layer 5b — Suspend state        | B → `suspend_state_dependency: "no"`            |
| Q-secrets — Acknowledgment      | Skip → `secrets_acknowledged: false`            |
| Q-region — Target region        | A → `region: "us-east-1"`                       |
| Q-sizing — Environment sizing   | A → `sizing: "dev"`                             |
| Q-window — Migration window     | C → `migration_window: "flexible"`              |

---

## Validation Checklist

Before handing off to Design:

- [ ] `preferences.json` written to `$MIGRATION_DIR/`
- [ ] `audience` is populated (`"technical"` or `"business"`)
- [ ] `platform_preference.eks_reuse` is populated (`true` or `false`)
- [ ] For each process group in inventory → `process_groups.<group>` entry exists
- [ ] For each `process_groups.<group>` entry:
  - [ ] `class_confirmed` is one of: `"always_on"`, `"scale_to_zero"`, `"one_shot"`, `"gpu"`, `"agent"`, or `null`
  - [ ] `scale_to_zero_intent` is one of: `"deliberate"`, `"inherited_default"`, `"n/a"`
  - [ ] `suspend_state_dependency` is one of: `"yes"`, `"no"`, `"n/a"`
  - [ ] `gpu_purpose` is one of: `"compute"`, `"llm_inference"`, `"n/a"`
- [ ] For each confirmed agent group → `agent_groups.<group>` entry exists with `advisor_requested: true|false`
- [ ] `region` is a valid AWS region code
- [ ] `sizing` is one of: `"dev"`, `"staging"`, `"production"`
- [ ] `migration_window` is one of: `"asap"`, `"planned"`, `"flexible"`
- [ ] `answers_meta` has an entry for each non-defaulted answer with `chosen_by` set
- [ ] All entries in `answers_meta` have `chosen_by` value of `"user"`, `"default"`, or `"injected"`
- [ ] Output is valid JSON
- [ ] `preferences-draft.json` has been deleted (if it existed)

---

## Consistency Check (Step 2 from Task Brief)

Run the following grep commands to verify enum value alignment with the schema:

```bash
# Check class_confirmed values
grep -o '"class_confirmed": "[^"]*"' preferences.json | sort -u
# Expected: "always_on", "scale_to_zero", "one_shot", "gpu", "agent", or null

# Check scale_to_zero_intent values
grep -o '"scale_to_zero_intent": "[^"]*"' preferences.json | sort -u
# Expected: "deliberate", "inherited_default", "n/a"

# Check suspend_state_dependency values
grep -o '"suspend_state_dependency": "[^"]*"' preferences.json | sort -u
# Expected: "yes", "no", "n/a"

# Check gpu_purpose values
grep -o '"gpu_purpose": "[^"]*"' preferences.json | sort -u
# Expected: "compute", "llm_inference", "n/a"
```

All output values MUST match the preferences.json schema in the task brief exactly. Record the result in the completion report.

---

## Completion Handoff Gate (Fail Closed)

Load `$GCP_SHARED/handoff-gates.md` (`$GCP_SHARED = ${CLAUDE_PLUGIN_ROOT}/skills/gcp-to-aws/references/shared`). **Re-read from disk** before checking.

**Re-entry guard:** If `aws-design.json` exists and `phases.design` is `"completed"`: STOP unless the user explicitly confirms re-running Clarify. Emit `GATE_FAIL | phase=clarify | field=aws-design.json | reason=stale_downstream`.

**Checks (all must PASS):**

1. `preferences.json` exists and parses as valid JSON.
2. All Validation Checklist items pass.
3. `audience` is set (non-null).
4. `platform_preference.eks_reuse` is set (non-null).
5. For each process group in inventory → `process_groups.<group>` entry exists with all four fields set.
6. For each confirmed agent group → `agent_groups.<group>` entry exists with `advisor_requested` set.
7. `region` is set and valid.
8. `sizing` is set.
9. `migration_window` is set.

**On any FAIL:** Emit `GATE_FAIL | phase=clarify | field=<path> | reason=missing`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user to answer the missing question or re-run Clarify.

**On PASS:** Emit `HANDOFF_OK | phase=clarify | artifacts=preferences.json`.

---

## Step 5: Update Phase Status

Only after `HANDOFF_OK`. In the **same turn** as the output message below, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json`:

- Set `phases.clarify` to `"completed"`
- Set `current_phase` to `"design"`
- Update `last_updated` to current ISO timestamp

Output to user: "Clarification complete. Proceeding to Phase 3: Design AWS Architecture."

---

## Scope Boundary

**This phase covers requirements gathering ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Detailed AWS architecture or service configurations
- Code migration examples or SDK snippets
- Detailed cost calculations
- Migration timelines or execution plans
- Terraform generation
- Fly machine-to-Fargate sizing decisions
- EC2 instance class selection
- Agent-advisor scoring (that's Task 8 embedded run, not Clarify)

**Your ONLY job: Understand what the user needs. Record their intent. Nothing else.**
