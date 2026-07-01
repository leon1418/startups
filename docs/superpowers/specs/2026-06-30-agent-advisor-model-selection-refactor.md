# Agent Advisor — Model Selection Refactor (design)

**Date:** 2026-06-30
**Status:** Design reviewed (Kiro) + revised, pre-implementation
**Scope:** ONLY the Bedrock model recommendation in agent-advisor. Does not touch runtime
scoring (model choice and runtime choice are independent — verified in code).

**Kiro review incorporated (2026-06-30):** two P0 corrections — `speech` maps to **Nova 2 Sonic**
(not Nova Sonic v1, which is in the 90-day EOL exclusion zone) and `image_generation` maps to
**Stability AI** (not Nova Canvas v1, which is Legacy). Plus: cost-conflict advisory, explicit
`_MIGRATE_FAMILY` precedence, orphan `nova_pro` removed, Nova 2 Pro gated on GA, multimodal
alternates rule, and a **drift-detection test** against the source lifecycle file (chosen over
duplicating or cross-reading it).

---

## 1. Problem

`scoring.py::_select_model` currently maps only `model_priority` (quality/balanced → Sonnet 4.6;
speed/cost → Haiku 4.5) plus a single `model_features == "extended_thinking"` override. Every
other feature value (`tool_use`, `long_context`, `rag`, `multimodal`, `speech`, `image_generation`)
is **accepted but ignored**, and the candidate pool is only two Claude models.

Consequence: a user who needs long context, speech, or image generation is still recommended
Sonnet/Haiku — correct-looking only because Sonnet happens to be broadly capable, and outright
wrong when priority is cost/speed (→ Haiku) while a specialized feature is required. Models that
are the right answer (Nova Sonic for speech, Nova Canvas for image gen, Llama 4 Scout for ultra-
long context, Titan for embeddings) can never be recommended because they aren't in the pool.

**Goal (per user):** make the LLM model recommendation *accurate* by feeding the feature signal
into selection and widening the candidate pool. This is a model-recommendation fix only — it does
not change which runtime (agent compute) is selected.

## 2. Source of truth (reuse, don't reinvent)

The sibling `migration-to-aws` plugin already has a complete, maintained feature→model matrix:
- `skills/gcp-to-aws/references/phases/clarify/clarify-ai.md` — Q16 (priority) + Q17 (specialized
  feature) with concrete anchors and the override hierarchy.
- `skills/gcp-to-aws/references/design/design-ai.md` — capability→target-class table
  (image_generation → Nova Canvas, embedding → Titan, speech_to_text → Transcribe, etc.) and the
  override order: **Q17 special feature (hard override) > Q16 priority > volume/latency > source
  model baseline**.
- `skills/gcp-to-aws/references/shared/ai-model-lifecycle.md` — Active/Legacy/EOL rules.

We reuse the **mapping** from these. We do **not** copy pricing/TCO — that stays in
migration-to-aws (it owns `pricing-cache.md` + lifecycle upkeep). agent-advisor gives a model
recommendation; detailed pricing and cutover validation hand off downstream.

## 3. Design

### 3.1 New shared reference: `skills/shared/decision-refs/model-selection.md`

A single distilled table (mapping only, **no dollar figures**), derived from Q16/Q17 + design-ai's
capability table. Read by `_select_model` reviewers and by clarify wording. Structure:

**Priority baseline (Q16):**

| priority | model family |
| --- | --- |
| quality | Claude Sonnet 4.6 (Opus 4.7 for the most demanding reasoning) |
| balanced / unknown | Claude Sonnet 4.6 |
| speed | Claude Haiku 4.5 (or Nova Micro/Lite for cost-optimized speed) |
| cost | Claude Haiku 4.5 or Nova Micro |

**Specialized-feature override (Q17 — hard override, beats priority):**

| feature | model | notes |
| --- | --- | --- |
| tool_use | Claude Sonnet 4.6 | best-in-class tool use |
| long_context (>300K) | Claude Sonnet 4.6; or Llama 4 Scout (10M) / Nova 2 Pro (1M) for very large native windows | |
| extended_thinking | Claude Sonnet 4.6 (extended thinking); Opus 4.7 for hardest | |
| rag | Claude Sonnet 4.6 + Bedrock Knowledge Bases + Titan Embeddings | |
| multimodal | Claude Sonnet 4.6 (vision) | for image *understanding*; if the workload also *generates* images, add a Stability AI model to `alternates` (see §3.2 multimodal rule) |
| image_generation | Stability AI (Stable Image Core for cost, Stable Image Ultra for quality) | separate capability, not a text model. **NOT Nova Canvas** — Nova Canvas v1 is Legacy; lifecycle rules require Stability AI as the Active primary |
| speech | Amazon Nova 2 Sonic (speech-to-speech); Transcribe (STT) / Polly (TTS) for the one-directional cases | not a Bedrock text-model swap. **Nova 2 Sonic, not Nova Sonic v1** (v1 is within 90 days of EOL — excluded) |
| embedding | Amazon Titan Embeddings v2 | |
| none / unknown | (no override — priority baseline stands) | |

**Lifecycle note (P0 — must hold):** recommend **Active** models only, per
`migration-to-aws/.../ai-model-lifecycle.md`. Never map a feature to a model in the 90-day EOL
exclusion zone or a Legacy model that has an Active replacement. As of 2026-06-30 this rules out
**Nova Sonic v1** (→ Nova 2 Sonic) and **Nova Canvas v1** (→ Stability AI). This is a coarse
family-level mapping; exact model IDs, pricing, EOL dates, and regional availability come from
migration-to-aws / ai-to-aws (and the drift test in §4 keeps this mapping honest against the
source lifecycle file).

### 3.2 `scoring.py::_select_model` changes

- Extend `_MODEL_PRIORITY` to allow Nova Micro/Lite as speed/cost alternates (keep Claude as the
  default; alternates surfaced in reasoning text, not forced).
- Replace the single `extended_thinking` check with a `_FEATURE_OVERRIDE` dict keyed by all Q17
  feature values above → (model, reasoning). Apply as a **hard override** over the priority
  baseline (matches migration-to-aws's precedence). `none`/`unknown` → no override.
- **Cost/speed conflict advisory (P1):** when a feature override selects a specialized model that
  contradicts a `cost`/`speed` priority (e.g. priority=cost + feature=speech → Nova 2 Sonic),
  append an advisory line to `reasoning`: "Feature override applied: <model> is required for
  <feature>; it may not be the lowest-cost option vs your stated priority — see pricing downstream."
  Informational only, never blocking.
- **`_MIGRATE_FAMILY` precedence (P1):** the feature override ALWAYS wins over the source→family
  mapping (Q17 > Q19). Remove the current `if model_features in ("unknown","none")` guard that
  gates the migrate remap; instead: apply feature override first; only fall to `_MIGRATE_FAMILY`
  when there is no feature override. `migration_from` is still recorded either way.
- Candidate pool (Active models only, per lifecycle file): `claude_sonnet_4_6`,
  `claude_sonnet_4_6_thinking`, `claude_opus_4_7`, `claude_haiku_4_5`, `nova_micro`, `nova_lite`,
  `nova_2_sonic`, `stability_image_core`, `stability_image_ultra`, `llama_4_scout`,
  `titan_embed_v2`. (Dropped `nova_canvas`/`nova_sonic` — Legacy/excluded. Dropped orphan
  `nova_pro` — nothing mapped to it. `nova_2_pro` for long_context is included ONLY if confirmed
  GA at implementation; if still Preview, use `llama_4_scout` as the long-context primary and note
  Nova 2 Pro as a preview alternate.)
- **multimodal rule (P2):** `multimodal` → Claude Sonnet 4.6 (vision) for image *understanding*.
  If the workload also *generates* images, add `stability_image_core` to `alternates` with a note.
  A single `_FEATURE_OVERRIDE` entry returns one primary; the generation companion goes in
  `alternates`, not as the primary.
- Determinism preserved (pure dict lookups, unit-testable). **No change to `_compute_scores`,
  `_determine_verdict`, or any runtime dimension** — model selection remains independent of the
  verdict (proven: verdict never reads model_* keys).

### 3.3 Clarify changes (restore the feature question — now that it's used)

- I earlier removed the inert `model_features` values. Restore them, because they now drive
  selection. `model_features` legal values become the Q17 set: `tool_use | long_context |
  extended_thinking | rag | multimodal | image_generation | speech | embedding | none | unknown`.
- Ask as Q16 (priority) then, only if priority == "specialized" OR the user hints at a specific
  need, Q17 (the one most critical feature). Keep it to the one critical feature (Q17 is
  "MOST CRITICAL specialized feature", single-select) to avoid bloating the interview.
- `region` stays removed (still not used; multi-region architecture is downstream).

### 3.4 Output / report

- `model_recommendation` gains an optional `alternates` list and keeps `reasoning`. Still no
  prices. For specialized features that map to a non-text service (speech→Nova 2 Sonic/Transcribe,
  image→Stability AI), the reasoning notes "this is a separate capability/service, not a text-model
  swap — see ai-to-aws for integration."
- recommendation-doc Section 9 unchanged in structure; it now can name the right specialized model.

## 4. Testing

Golden tests in `test_scoring.py` (model selection is deterministic):
- priority quality/balanced → sonnet; speed/cost → haiku (existing, keep).
- feature long_context → includes Llama 4 Scout in model or alternates.
- feature speech → `nova_2_sonic` (NOT sonnet, NOT nova_sonic v1); feature image_generation →
  `stability_image_*` (NOT nova_canvas).
- feature override beats priority: priority=cost + feature=speech → `nova_2_sonic`, not haiku;
  and the `reasoning` contains the cost-conflict advisory line.
- migrate + feature: gpt4o source + long_context → feature override wins over `_MIGRATE_FAMILY`,
  `migration_from` still set.
- multimodal + also-generates-images → primary sonnet (vision), `alternates` includes a
  Stability AI model.
- **Regression:** changing any model_* answer never changes `verdict` or `scores` (locks the
  independence invariant).
- **Drift detection (P2):** a test reads the source lifecycle/mapping in
  `migration-to-aws/.../ai-model-lifecycle.md` and asserts no model in agent-advisor's
  `_FEATURE_OVERRIDE` / `_MODEL_PRIORITY` pool appears there as Legacy/EOL/excluded. If a source
  model goes Legacy, this test fails in CI instead of silently shipping a stale recommendation.
  (If cross-plugin file access is unavailable at test time, mark xfail with a clear skip reason
  rather than dropping the check.)

## 5. Scope boundaries (unchanged)

- No pricing/TCO in agent-advisor — hand off to migration-to-aws / ai-to-aws.
- No change to runtime scoring, deployment-model, service selection, or the diagram.
- Coarse family-level mapping only; exact model IDs + region availability verified downstream.

## 6. Open items

- Whether to ask Q17 always vs only when priority == specialized. Default: only when specialized
  or hinted, to keep the interview short (matches migration-to-aws's Q16→Q17 gating).
- Exact alternates wording in reasoning (kept short; drafted at implementation).
