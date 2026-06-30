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
| `generate` | `design` done AND (`estimate` done OR entry point == migrate) | Load `references/phases/generate.md` |
| `complete` | `generate` done | Done |

**Entry-point routing:**
- `build_scratch` → skip Discover; Clarify → Design → Estimate → Generate.
- `build_deploy` → Discover (if code) → Clarify → Design → Estimate → Generate.
- `migrate` → Discover (if code) → Clarify → Design → **(skip Estimate)** → Generate → **then handoff, stop**. The user gets the same recommendation doc + architecture diagram as Build paths; Generate then hands off to the migration plugins (no Build scaffolding, no precise cost — those belong downstream).
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
