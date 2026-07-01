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
  `model_features` (extended_thinking|none|unknown) — only `extended_thinking` changes the
  model default; do not ask about other feature values (they don't affect the recommendation —
  deep model selection is the `ai-to-aws` plugin's job),
  `current_model` (gpt4|gpt4o|gemini_flash|gemini_pro|claude|other|none|unknown) — migrate only.
  (No `region` question: region drives multi-region architecture, which is handed off to
  migration-to-aws, not scored here.)

**Critical-question rule:** if `session_duration` is blank/unknown, **OR was only inferred by
Discover and not confirmed by the user**, ask it directly in chat before scoring — it gates hard
constraints, so an unconfirmed guess can silently eliminate runtimes. (Applies to every entry
point that reaches Clarify.)

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

## Step 6 — Write state and continue to Pass 2
Set `phases.clarify` = completed (leave `phases.clarify_pass2` = pending). Do NOT jump to Design.
The state machine now routes to **Clarify Pass 2** (`references/phases/clarify-pass2.md`), which
confirms the deployment model / services / co_recommend pick and writes `pass2.json` — Design and
the diagram require it.
