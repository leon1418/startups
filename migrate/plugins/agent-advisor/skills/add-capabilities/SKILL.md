---
name: add-capabilities
description: "For teams already running agents on AWS who want to add AgentCore services. Triggers on: add AgentCore services, add memory/gateway/identity/policy to my agent, enable AgentCore Memory, add observability to my agent, I'm already on AWS and want to add agent capabilities. Recommends which AgentCore services to enable (on any runtime), why, what's free, and native-vs-bring-your-own. Does NOT score runtimes (use the agent-advisor skill for runtime selection)."
---

# Add AgentCore Capabilities

For customers already on AWS who want to add AgentCore services. No runtime scoring — services
run on any runtime.

## Step 0 — Create the run directory
Generate a run id from the current time as `MMDD-HHMM`. Create the run directory under the
**user's current working directory** (run `pwd` and anchor to it) — NOT the plugin install tree:
`<cwd>/.agent-advisor/<run_id>/`, plus `<cwd>/.agent-advisor/.gitignore` containing `*` (so run
state is never committed). Call this directory `$RUN_DIR`.

## Step 1 — Current runtime
Ask which runtime they run on now: AgentCore / ECS / EKS / Lambda / other. (If the user already
stated it in their opening message, skip this question.)

## Step 2 — Capabilities needed (multi-select)
Identity, Gateway, Memory, Policy, Observability, Managed KB, Code Interpreter, Browser,
Web Search, Sandbox. For each selected, load the relevant section of
`${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/agentcore.md`.

## Step 3 — Native vs bring-your-own
If they already use a third-party tool for a capability (Tavily/Pinecone/Browserbase/etc),
present: switch to AgentCore native, or keep existing and connect via Gateway.

## Step 4 — Volatile facts
Load `${CLAUDE_PLUGIN_ROOT}/skills/shared/decision-refs/freshness.md`. This skill has no winning
runtime profile, so verify the relevant "Hard limits" facts from `agentcore.md` directly (per
freshness.md Procedure step 1). Follow its anti-fabrication rule: only list a fact as
MCP-verified if you actually called the MCP this run; otherwise it's cached.

## Step 5 — Output
Write the recommendation to `$RUN_DIR/capabilities-recommendation.md` (so the user can keep and
share it — consistent with the main skill's `recommendation.md`). Include:
- **Current runtime** and the capabilities requested.
- **Services to enable** — for each: what it does, why it fits, and (Identity) that it's free.
- **Native vs bring-your-own** outcome per capability (from Step 3): which go AgentCore-native
  and which stay third-party fronted via Gateway.
- **Integration on the current runtime** — concrete setup pointers (IAM/task-role changes, SDK
  calls, endpoints) for the user's runtime; note these services are standalone and require no
  runtime/compute change.
- **Suggested enablement order.**
- **Freshness footer** (per `freshness.md`: generation date, which facts were MCP-verified vs
  cached).

Then give a short in-chat summary and point the user to `$RUN_DIR/capabilities-recommendation.md`.
This skill does not score runtimes or hand off — it ends here.
