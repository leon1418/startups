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
For any selected service that can front external tools/data (Gateway, Managed KB, Web Search,
Memory), **ask** whether they already use a third-party tool for it (e.g. Tavily, Pinecone,
Browserbase, a REST/MCP server) — do NOT assume greenfield. If yes: switch to AgentCore native,
or keep existing and connect via Gateway. If no: default to native. Record the choice in
`tool_choices`.

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
- `deployment_model` (confirmed; for a `co_recommend` pick, the deployment model of the runtime
  the user CHOSE — recompute for the chosen runtime, do not carry a stale value from the tie),
- `agentcore_services` (final list),
- `chosen_runtime` (REQUIRED when the verdict was `co_recommend` — the runtime id the user
  picked in Step 4; the architecture-diagram composer reads this to know which runtime to draw).
  Omit for single-winner verdicts.
- `tool_choices` (per-capability native-vs-gateway choices from Step 2).
```json
{"deployment_model": "harness", "agentcore_services": ["identity", "memory"],
 "chosen_runtime": "eks", "tool_choices": {"web_search": "native"}}
```
Set `phases.clarify_pass2` = completed (read-merge-write). The flow now advances to Design.
