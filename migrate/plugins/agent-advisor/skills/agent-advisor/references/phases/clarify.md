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
