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
