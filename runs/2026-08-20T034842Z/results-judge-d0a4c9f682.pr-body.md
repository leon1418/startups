> Opened by the knowledge auto-update pipeline. **Draft** — a human decides.

## What changed upstream

[Previewing GPT-5.6 Sol: a next-generation model](https://openai.com/index/previewing-gpt-5-6-sol)

**Verdict: `new_knowledge`** on `openai.model_lineup`

- was — Latest documented flagship is GPT-5.5 (April 23, 2026), $5.00/$30.00 per 1M tokens, with comparison tables against Bedrock models.
- now — GPT-5.6 Sol previewed as next-gen model (coding, science, cybersecurity, safety improvements); no pricing, context window, or availability details given in announcement.

> **Still true:** All existing GPT-5.5 and earlier pricing/comparison data remains valid until GPT-5.6 Sol pricing is announced.
>
> This is why the old value is **not** simply overwritten.

## Proposed edits

Each row states its justification. No CI check can catch a badly reworded judgment, so the
"why" column is the only protection a reviewer has — please read it rather than the diff alone.

### `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:28` — value

```diff
- ### GPT-5.5 Series (Latest — April 23, 2026)
+ ### GPT-5.5 Series (previous flagship — April 23, 2026; superseded by GPT-5.6 Sol preview)
```

**Why:** The heading claims GPT-5.5 is the 'Latest' model, but the announcement introduces GPT-5.6 Sol as the new next-generation model, making this labeling outdated.

**Evidence (verbatim from the announcement):** "Previewing GPT-5.6 Sol: a next-generation model"

## Known limits of this proposal

- **Blast radius is not stable between runs.** Two runs of the same input returned 9 and 13
  locations and neither was a superset of the other, so this list may be incomplete.
- Paths are relative to `migrate/plugins/migration-to-aws/skills`.
- The pipeline did not touch any file the judge did not name.
