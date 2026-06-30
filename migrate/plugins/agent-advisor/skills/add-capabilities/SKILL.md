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
