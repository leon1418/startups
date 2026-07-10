---
_fragment: agent-handoff
_of_phase: design
_contributes:
  - aws-design.json
---

# Design Layer 0 Sub-phase: Embedded agent-advisor Run

Executes an embedded agent-advisor scoring run for a confirmed agent group, producing a runtime verdict that replaces the generic routing table for that group. This sub-phase is triggered by design.md Layer 0 when a process group is classified as `"agent"` and the user requested advisor scoring.

---

## Path Resolution Table

All agent-advisor files are **read-only** and are addressed via the following path prefix:

```
$ADVISOR = ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor
```

Relative references inside agent-advisor phase files (e.g., `references/phases/clarify.md`, `scripts/scoring.py`) resolve from `$ADVISOR`, not from the fly-to-aws skill root.

| Path prefix in advisor files   | Resolves to                             |
| ------------------------------ | --------------------------------------- |
| `references/phases/...`        | `$ADVISOR/references/phases/...`        |
| `references/decision-refs/...` | `$ADVISOR/references/decision-refs/...` |
| `scripts/...`                  | `$ADVISOR/scripts/...`                  |
| `data/...`                     | `$ADVISOR/data/...`                     |

**NEVER edit agent-advisor files.** They are shared across multiple skills and must remain read-only.

---

## Embedded Run Directory Contract

### Run Directory Path

For each confirmed agent group requiring advisor scoring, create a dedicated embedded run directory:

```
$EMBED_DIR = $MIGRATION_DIR/agent-advisor/<group>/
```

where `<group>` is the process group name from the inventory (e.g., `web`, `worker`).

**Critical binding rule:** For the duration of the embedded advisor run, every `$RUN_DIR` reference inside agent-advisor phase files resolves to `$EMBED_DIR`. Agent-advisor phases expect to write their state and artifacts to `$RUN_DIR` — map that variable to the embedded directory for this group.

**NEVER access `.agent-advisor/*` in the user's current working directory.** The embedded run is fully isolated under `$MIGRATION_DIR/agent-advisor/<group>/`, not in the repo root.

### Pre-Written State Files

Before loading any advisor phase file, pre-write the following files to `$EMBED_DIR`:

#### 1. `.phase-status.json`

Initialize the advisor state machine with fly-to-aws context:

```json
{
  "run_id": "<MMDD-HHMM>-<group>",
  "entry_point": "migrate",
  "audience": "<copied from preferences.json>",
  "current_phase": "clarify",
  "phases": {
    "turn1": "completed",
    "discover": "completed",
    "clarify": "in_progress"
  }
}
```

Where:

- `run_id`: migration timestamp + group name (e.g., `"0709-1430-web"`)
- `entry_point`: Always `"migrate"` (embedded runs always come from a migration context)
- `audience`: Copy the value from `$MIGRATION_DIR/preferences.json` → `audience` field (`"technical"` or `"business"`)
- `turn1` and `discover` are marked `"completed"` because fly-to-aws already performed those steps; clarify is the first advisor phase to execute

#### 2. `context-signals.json`

Pre-fill answers derived from fly-to-aws's Discover and Clarify phases to minimize re-asking:

```json
{
  "framework": "<detected from inventory flags>",
  "session_state": "<hint from process_groups flags>",
  "launch_concurrency": "<hint from scaling config>",
  "model_provider": "<detected from inventory if applicable>",
  "session_duration": "<mapped from preferences or inventory signals>",
  "traffic_pattern": "<mapped from scaling config>",
  "existing_cluster": "<from preferences.platform_preference.eks_reuse>"
}
```

**Derivation rules:**

- `framework`: If `inventory.process_groups.<group>.flags.framework` contains a recognized value (`"strands"`, `"langgraph"`, `"crewai"`), pre-fill it. Otherwise omit.
- `session_state`: If `flags.stateful_mounts[]` is non-empty → `"stateful"`. If explicit agent-session hints exist → `"stateful"` or `"hitl"` as appropriate. Otherwise omit.
- `launch_concurrency`: If `scaling.min_machines_running >= 10` → `"high"`. If `scaling.min_machines_running >= 3` → `"moderate"`. If scale-to-zero → `"low"`. Otherwise omit.
- `model_provider`: If LLM SDK was detected in Discover → pre-fill with the provider name mapped to advisor enum (`"claude"`, `"gpt4"`, etc.). Otherwise omit.
- `session_duration`: Map from preferences or inventory if already confirmed in Clarify. Otherwise omit (let advisor ask).
- `traffic_pattern`: If `scaling.auto_start == true` and `min_machines_running == 0` → `"bursty"`. If high min count → `"steady"`. Otherwise omit.
- `existing_cluster`: If `preferences.platform_preference.eks_reuse == true` → `"eks"`. If `== false` → `"none"`. Otherwise omit.

**Context-signals are hints, not hard constraints.** The advisor clarify phase will present each pre-filled value as "detected: `<value>` (say so if wrong)" and allow the user to override. Only pre-fill when confidence is high; when uncertain, omit the key and let advisor ask.

---

## Legal Phase Sequence

Execute the following advisor phases in order. **Agent-advisor's Design, Estimate, Generate, and POC phases are FORBIDDEN in this embedded context** — fly-to-aws consumes the verdict and performs those phases itself.

### Phase 1: Clarify (Pass 1)

Load and execute: `$ADVISOR/references/phases/clarify.md`

**Key behaviors:**

- Reads `$EMBED_DIR/context-signals.json` and pre-fills detected answers
- Asks remaining scoring questions (audience-aware wording)
- Writes `$EMBED_DIR/answers.json`
- Executes scoring engine

**Scoring command (as specified in clarify.md Step 5):**

```bash
uv run --project $ADVISOR/scripts python $ADVISOR/scripts/scoring.py $EMBED_DIR/answers.json
```

Substituting `$RUN_DIR` → `$EMBED_DIR` per the binding rule. This writes `$EMBED_DIR/scoring-result.json` and prints `RESULT=ok VERDICT=<verdict>`.

**Output artifacts:**

- `$EMBED_DIR/answers.json`
- `$EMBED_DIR/scoring-result.json`

### Phase 2: Clarify (Pass 2) — Deployment Model & Services

Load and execute: `$ADVISOR/references/phases/clarify-pass2.md`

**Execute AS-IS, unmodified.** This phase:

- Confirms the deployment model (Harness vs Framework on Runtime for AgentCore verdicts)
- Asks which AgentCore services to enable (Gateway, Memory, Code Interpreter, etc.)
- For tied verdicts (`co_recommend`), asks the user to pick the final runtime
- Writes `$EMBED_DIR/pass2.json`

**Critical note:** Pass 2 asks about AgentCore add-on services for ALL runtime verdicts (including ECS/EKS/Lambda). It asks which services the user wants (Memory, Gateway, Code Interpreter, Browser, etc.) — these run as add-ons even when the compute target is non-AgentCore. **Let it ask.** Do not filter or skip service questions based on the verdict. Record the full `pass2.json` output.

**Output artifacts:**

- `$EMBED_DIR/pass2.json` with fields:
  - `deployment_model` (confirmed deployment model: `"harness"` or `"framework_on_runtime"`)
  - `agentcore_services` (list of enabled services, always includes at least `["identity", "observability"]`)
  - `chosen_runtime` (REQUIRED if verdict was `co_recommend` — the runtime the user picked)
  - `tool_choices` (per-capability native-vs-gateway choices)

### Phase 3: Stop Here — No Design/Estimate/Generate/POC

**Advisor's Design, Estimate, Generate, and POC phases are FORBIDDEN in this embedded run.** The advisor verdict (runtime + deployment model + services) is consumed by fly-to-aws's own Design → Estimate → Generate flow.

After Pass 2 completes, set `$EMBED_DIR/.phase-status.json` → `phases.clarify_pass2 = "completed"` and return control to design.md Step 1 Layer 0.

---

## Verdict Merge into aws-design.json

After the embedded advisor run completes, merge the verdict into the design blueprint for this group:

### Compute Entry Fields

Write the following fields to `aws-design.json` → `compute.<group>`:

```json
{
  "target": "<advisor runtime verbatim>",
  "layer_fired": "0",
  "decided_by": "agent-advisor",
  "sizing": { ... },
  "notes": [ ... ],
  "advisor_ctx": {
    "embed_dir": "<absolute path to $EMBED_DIR>",
    "verdict": "<advisor runtime from scoring-result.json>",
    "deployment_model": "<from pass2.json>",
    "services_hint": [ ... ]
  }
}
```

**Field definitions:**

- `target`: The advisor runtime name **verbatim** from `scoring-result.json` → `verdict`. Legal values include:
  - `agentcore` (AgentCore Runtime)
  - `ecs` (ECS Fargate)
  - `eks` (Elastic Kubernetes Service)
  - `lambda` (AWS Lambda)
  - `lambda_microvms` (Lambda MicroVMs)
  - Plus any advisor-specific variants (e.g., `agentcore_ruby`, `lambda_snapstart`)

  **Never translate or normalize the verdict.** Pass it through exactly as advisor returned it.

- `layer_fired`: Always `"0"` (Layer 0 — AI Agent Confirmation)

- `decided_by`: Always `"agent-advisor"`

- `sizing`: Derive from advisor verdict + answers:
  - For `agentcore`: Use `answers.json` → `compute_tier` to map to CPU/memory (see advisor decision-refs for tier mapping)
  - For `ecs`/`eks`/`lambda`: Use standard fly-to-aws sizing rules from machine-preset-table.md

- `notes`: Include at minimum:
  - `"Runtime selected by agent-advisor scoring (embedded run)"`
  - Top 1-2 scoring signals from `scoring-result.json` → `explanation` (if present)

- `advisor_ctx` (object, REQUIRED when `decided_by == "agent-advisor"`):
  - `embed_dir`: Absolute path to the embedded run directory (e.g., `/path/to/repo/.migration/0709-1430/agent-advisor/web/`)
  - `verdict`: The runtime verdict string from `scoring-result.json` (same as `target`)
  - `deployment_model`: From `pass2.json` → `deployment_model` (`"harness"` or `"framework_on_runtime"`)
  - `services_hint`: Array of AgentCore service names from `pass2.json` → `agentcore_services`. **Code Interpreter appears ONLY in this list, never as `target`.** When AgentCore won and Code Interpreter is enabled, `services_hint` includes `"code_interpreter"` — the compute target remains `"agentcore"`.

**Example verdict merge for AgentCore with Code Interpreter:**

```json
{
  "target": "agentcore",
  "layer_fired": "0",
  "decided_by": "agent-advisor",
  "sizing": {
    "cpu": 1.0,
    "memory_gb": 4.0
  },
  "notes": [
    "Runtime selected by agent-advisor scoring (embedded run)",
    "AgentCore selected for multi-agent orchestration + cross-session memory"
  ],
  "advisor_ctx": {
    "embed_dir": "/Volumes/workspace/myapp/.migration/0709-1430/agent-advisor/web/",
    "verdict": "agentcore",
    "deployment_model": "harness",
    "services_hint": ["identity", "observability", "memory", "code_interpreter", "gateway"]
  }
}
```

**Example verdict merge for ECS with add-on services:**

```json
{
  "target": "ecs",
  "layer_fired": "0",
  "decided_by": "agent-advisor",
  "sizing": {
    "cpu": 0.5,
    "memory_gb": 1.0
  },
  "notes": [
    "Runtime selected by agent-advisor scoring (embedded run)",
    "ECS selected for existing cluster reuse"
  ],
  "advisor_ctx": {
    "embed_dir": "/Volumes/workspace/myapp/.migration/0709-1430/agent-advisor/worker/",
    "verdict": "ecs",
    "deployment_model": "framework_on_runtime",
    "services_hint": ["identity", "observability", "gateway"]
  }
}
```

### Write-Back to preferences.json

After writing the compute entry to `aws-design.json`, also update `preferences.json` → `agent_groups.<group>` to ensure consistency for resumed/split sessions:

1. Set `decided_by: "agent-advisor"`
2. Set `compute_target: "<verdict from scoring-result.json>"` (the winning runtime verbatim)
3. Set `deployment_model: "<from pass2.json>"` (`"harness"` or `"framework_on_runtime"`)
4. If `answers.json` contains session semantics (`session_duration`, `memory_needs`), set `session_profile: {"session_duration": "...", "memory_needs": "..."}`

This write-back ensures that if the user re-runs design or splits the session, Layer G will correctly fire and use the injected values.

---

## Failure Handling

If the embedded advisor run fails or the user aborts mid-execution:

### During Clarify or Scoring

1. **Preserve all written artifacts** in `$EMBED_DIR` for potential resume
2. Set `$EMBED_DIR/.phase-status.json` → current phase to the phase that was in progress when failure occurred
3. **Fall through to generic routing** (Layers 1–5) for this group:
   - Remove `agent_groups.<group>.decided_by` from preferences (or set it to `null`)
   - Add a warning note to the group in `aws-design.json` → `compute.<group>.notes[]`: `"Agent-advisor scoring was initiated but not completed — routing via generic table. Embedded artifacts preserved at <$EMBED_DIR> for manual resume."`
   - Continue design.md Layer 1 for this group

### User Declines Mid-Run

If the user explicitly says "skip advisor" or "just use the routing table" after seeing preliminary questions:

1. Set `$EMBED_DIR/.phase-status.json` → `phases.clarify = "aborted"` (or whichever phase was current)
2. Fall through to Layers 1–5 per above
3. Note in `compute.<group>.notes[]`: `"Agent-advisor scoring offered and declined mid-run"`

### Resume Support

If the user later asks to resume advisor scoring for a failed group:

1. Check `$EMBED_DIR/.phase-status.json` to determine the last completed phase
2. Resume from the next phase (e.g., if `clarify = "completed"` but `clarify_pass2 = "pending"`, resume at Pass 2)
3. DO NOT re-ask questions from completed phases — load their output artifacts and continue

---

## Cross-Check Against Advisor Files

This contract is derived from the following advisor phase files (verification performed 2026-07-09):

### Pre-fill Mechanism

- **File:** `$ADVISOR/references/phases/clarify.md` Step 2
- **Verified:** `context-signals.json` is the pre-fill input file name (confirmed)
- **Verified:** Advisor shows detected values as "detected: `<value>` (say so if wrong)" and allows user override (confirmed)

### Answers Output

- **File:** `$ADVISOR/references/phases/clarify.md` Step 4
- **Verified:** Output file is `$RUN_DIR/answers.json` (mapped to `$EMBED_DIR/answers.json` per binding rule)

### Scoring Invocation

- **File:** `$ADVISOR/references/phases/clarify.md` Step 5
- **Verified:** Exact command is:

  ```bash
  uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/scripts python ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/scripts/scoring.py $RUN_DIR/answers.json
  ```

  With `$RUN_DIR` substituted to `$EMBED_DIR` per the binding rule. ✓

### Pass 2 Output

- **File:** `$ADVISOR/references/phases/clarify-pass2.md` Step 5
- **Verified:** Output file is `$RUN_DIR/pass2.json` (mapped to `$EMBED_DIR/pass2.json`)
- **Verified:** Fields include `deployment_model`, `agentcore_services`, `chosen_runtime` (when `co_recommend`), and `tool_choices` (confirmed)
- **Verified:** Pass 2 asks AgentCore add-on services for ALL verdicts, not just AgentCore compute (confirmed in Step 3)

### Path Resolution Rule

- **File:** `$ADVISOR/references/phases/migration-plan.md` header path table
- **Verified:** Advisor files use `$ADVISOR` base for all relative references; advisor files are read-only (confirmed)

---

## Integration Notes for design.md Layer 0

When design.md Layer 0 detects an agent group requiring embedded advisor scoring:

1. **Check prerequisites:**
   - `preferences.json` → `process_groups.<group>.class_confirmed == "agent"` ✓
   - `preferences.json` → `agent_groups.<group>.advisor_requested == true` ✓
   - `preferences.json` → `agent_groups.<group>.decided_by == null` (not already decided) ✓

2. **Load this file** and execute the embedded run per the contracts above

3. **Consume the verdict:**
   - Read `$EMBED_DIR/scoring-result.json` → `verdict`
   - Read `$EMBED_DIR/pass2.json` → `deployment_model`, `agentcore_services`
   - Merge into `aws-design.json` → `compute.<group>` per the verdict merge contract

4. **Continue to next group:** After merging the verdict, design.md Layer 0 returns to Step 1 and processes the next process group (or continues to Step 2 if all groups are routed)

**No turn boundary.** The embedded advisor run executes inline within the same design.md execution — the user experiences it as a continuous flow, not a separate skill invocation.
