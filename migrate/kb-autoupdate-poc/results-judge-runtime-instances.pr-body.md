> Opened by the knowledge auto-update pipeline. **Draft** — a human decides.

## What changed upstream

[AgentCore runtime instances are now generally available](https://aws.amazon.com/about-aws/whats-new/2026/08/aws-bedrock-agentcore-runtime-instances-generally-available/)

**Verdict: `schema_change`** on `agentcore.session_cap`

- was — AgentCore Runtime session cap: 8h (single value, applies to all AgentCore runtime)
- now — AgentCore Runtime session cap now dimensioned by compute type: microVM (default, serverless) = 8h (unchanged); EC2-backed runtime instances (new, GA) = up to 14 days, using capacity providers with GPU/memory/compute-optimized EC2 instance families

> **Still true:** The 8h session cap remains correct for the default serverless microVM-based AgentCore runtime path.
>
> This is why the old value is **not** simply overwritten.

## Proposed edits

Each row states its justification. No CI check can catch a badly reworded judgment, so the
"why" column is the only protection a reviewer has — please read it rather than the diff alone.

### `agent-advisor/references/decision-refs/temporal.md:56` — conclusion flips

```diff
- - **AgentCore Runtime**: 8-hour max execution → OUT as Worker host. (Its correct
+ - **AgentCore Runtime**: 8-hour max execution applies to the default microVM path; EC2-backed runtime instances now support up to 14 days → for sustained/long-running Worker-host use cases, AgentCore Runtime (EC2-backed) may now be IN, not automatically OUT
```

**Why:** The verdict 'OUT as Worker host' was derived from a single flat 8h cap. The announcement introduces EC2-backed runtime instances with up to 14-day sessions, which reverses the automatic disqualification for long-running Worker-host scenarios.

### `gcp-to-aws/references/design-refs/design-ref-agentic-to-agentcore.md:141` — conclusion flips

```diff
- | `very_long` (1hr+)                 | AgentCore Runtime with session chaining. Break into sub-tasks if > 8 hours.            |
+ | `very_long` (1hr+)                 | AgentCore Runtime with session chaining is one option; alternatively, use EC2-backed runtime instances (up to 14-day sessions) to avoid chaining/sub-tasking for very long agent sessions.            |
```

**Why:** The announcement introduces EC2-backed runtime instances supporting sessions up to 14 days, so the previous recommendation to break tasks into sub-tasks past 8 hours is no longer the only or best path — the conclusion reverses for very long sessions since native long sessions are now possible without chaining.

### `gcp-to-aws/references/phases/clarify/clarify-ai.md:486` — conclusion flips

```diff
- | Very long | AgentCore Runtime required (8-hour max session). If tasks exceed 8 hours: recommend breaking into sub-tasks with session chaining, or evaluate custom compute (ECS/EKS). |
+ | Very long | AgentCore Runtime required. Default microVM path is capped at 8 hours; for tasks exceeding 8 hours, recommend EC2-backed runtime instances (GA), which support sessions up to 14 days via capacity providers, instead of defaulting to sub-task decomposition or custom compute (ECS/EKS). |
```

**Why:** The announcement states EC2-backed runtime instances now support sessions up to 14 days, directly resolving the 'very long' task case that previously required workarounds (sub-tasking or ECS/EKS) due to the old single 8h cap. The recommendation conclusion flips from 'always decompose/migrate off AgentCore' to 'use runtime instances within AgentCore.'

### `agent-advisor/references/decision-refs/lambda-microvms.md:17` — derived judgment

```diff
- - Session cap: 8h (max 28,800s) — same as AgentCore; NOT longer
+ - Session cap: 8h (max 28,800s) — same as AgentCore's default microVM runtime path; AgentCore's new EC2-backed runtime instances now support up to 14 days, so Lambda MicroVMs is shorter than that option
```

**Why:** The claim 'same as AgentCore; NOT longer' was true only for the old flat 8h AgentCore cap. AgentCore now offers a 14-day option via EC2-backed runtime instances, so Lambda MicroVMs is no longer equal to the full range of AgentCore session caps — this comparison needs updating even though it's not a full flip (microVM path is unchanged).

### `agent-advisor/references/runtimes/agentcore.json:8` — derived judgment

```diff
- { "field": "session_duration", "value": "over_8hr", "reason": "AgentCore has an 8hr session cap" },
+ { "field": "session_duration", "value": "over_8hr", "reason": "AgentCore's default microVM runtime has an 8hr session cap; use EC2-backed runtime instances (capacity providers) for sessions up to 14 days" },
```

**Why:** The announcement states the 8h cap now only applies to the default serverless microVM path, while EC2-backed runtime instances support sessions up to 14 days. This scoring rule's blanket 'AgentCore has an 8hr session cap' reason is now only true for one compute type and must be updated to avoid disqualifying long-session agents that could use runtime instances.

### `gcp-to-aws/references/phases/clarify/clarify-ai.md:578` — derived judgment

```diff
- - `task_duration` — Determines AgentCore Runtime recommendation and session limit warnings
+ - `task_duration` — Determines AgentCore Runtime recommendation, compute type (default microVM vs. EC2-backed runtime instances), and session limit warnings
```

**Why:** Session limit is no longer a single value; task_duration must now also determine which compute type (microVM vs. runtime instances) is recommended, per the new dimensioned session cap.

### `gcp-to-aws/references/phases/clarify/clarify-ai.md:515` — derived judgment

```diff
- | B (harness) + D (very long tasks)       | Flag: 8-hour session limit. Recommend task decomposition or session chaining.    |
+ | B (harness) + D (very long tasks)       | Flag: 8-hour session limit applies to default serverless microVM runtime. For very long tasks, recommend EC2-backed runtime instances (GA, up to 14-day sessions) instead of task decomposition or session chaining.    |
```

**Why:** The old recommendation (decomposition/chaining) was the only mitigation under a flat 8h cap; the announcement's new 14-day runtime instances option changes the recommended path for very long tasks.

### `gcp-to-aws/references/phases/clarify/clarify-ai.md:485` — derived judgment

```diff
- | Long      | AgentCore Runtime strongly recommended (supports up to 8-hour sessions). Serverless alternatives (Lambda) will timeout.                                                  |
+ | Long      | AgentCore Runtime strongly recommended. Default serverless microVM path supports up to 8-hour sessions; if longer sustained execution is needed, EC2-backed runtime instances (GA) support sessions up to 14 days. Serverless alternatives (Lambda) will timeout.                                                  |
```

**Why:** The recommendation basis (8-hour session support) is now only true for the default microVM path per 'still true' note; the announcement adds a new higher-capacity option (runtime instances, up to 14 days) that changes the judgment for the 'Long' task category.

### `agent-advisor/references/decision-refs/agentcore.md:15` — value

```diff
- - Session cap: 8h (extending — verify)
+ - Session cap: dimensioned by compute type — microVM (default, serverless) = 8h (unchanged); EC2-backed runtime instances (new, GA) = up to 14 days via capacity providers (GPU/memory/compute-optimized EC2 families)
```

**Why:** Announcement replaces the single flat 8h cap with a compute-type-dimensioned cap: microVM stays 8h, EC2-backed runtime instances now support up to 14 days.

### `agent-advisor/references/decision-refs/freshness.md:5` — value

```diff
- - AgentCore session cap (currently "8h, extending")
+ - AgentCore session cap (now dimensioned: microVM = 8h unchanged; EC2-backed runtime instances = up to 14 days, GA)
```

**Why:** The 'extending — verify' placeholder is resolved by the announcement; the cap is no longer a single value but split by compute type, with EC2-backed runtime instances now GA at up to 14 days.

### `agent-advisor/references/decision-refs/temporal.md:95` — value

```diff
- typical winner AgentCore Runtime (≤8h) — DAF pattern
+ typical winner AgentCore Runtime — default microVM path ≤8h, or EC2-backed runtime instances up to 14 days for longer sessions — DAF pattern
```

**Why:** The (≤8h) qualifier stated the old flat cap; the announcement shows the cap now depends on compute type, with EC2-backed runtime instances supporting far longer sessions.

### `gcp-to-aws/references/design-refs/design-ref-agentic-to-agentcore.md:130` — value

```diff
- - Up to 8-hour session duration for long-running agent tasks
+ - Up to 8-hour session duration (default microVM runtime) or up to 14 days with EC2-backed runtime instances, for long-running agent tasks
```

**Why:** The announcement's 'new' value explicitly adds a 14-day option via EC2-backed runtime instances; describing 'up to 8-hour' as the ceiling for long-running tasks is now the old, superseded value.

### `gcp-to-aws/references/design-refs/design-ref-agentic-to-agentcore.md:17` — value

```diff
- - **AWS-native deployment:** First-class deployment on AgentCore Runtime with microVM isolation, 8-hour sessions, auto-scaling
+ - **AWS-native deployment:** First-class deployment on AgentCore Runtime with microVM isolation (8-hour sessions, default) or EC2-backed runtime instances (up to 14-day sessions), auto-scaling
```

**Why:** The announcement states the 8-hour figure now only applies to the default microVM path; this line states it as the single unqualified value for AgentCore Runtime deployment, which is now incomplete/incorrect given the new EC2-backed runtime instances option.

## Filter false positives

The announcement scan flagged these files; the judge rejected them:

- `agent-advisor/references/decision-refs/poc-shapes.md`

## Known limits of this proposal

- **Blast radius is not stable between runs.** Two runs of the same input returned 9 and 13
  locations and neither was a superset of the other, so this list may be incomplete.
- Paths are relative to `migrate/plugins/migration-to-aws/skills`.
- The pipeline did not touch any file the judge did not name.
