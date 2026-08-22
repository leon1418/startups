> Opened by the knowledge auto-update pipeline. **Draft** — a human decides.

## What changed upstream

[Amazon Bedrock announces reduced pricing for OpenAI GPT-5.6 Sol](https://aws.amazon.com/about-aws/whats-new/2026/08/bedrock-openai-gpt-56-sol-reduced-pricing/)

**Verdict: `value_change`** on `ai-openai-to-bedrock.gpt-5.6-sol.pricing`

- was — GPT-5.6 Sol on Bedrock: $5.50 / $33.00 per 1M tokens (in/out, ≤272K ctx) — reflecting a July 30 price reduction
- now — GPT-5.6 Sol pricing lowered again to $4.00 / $20.00 per 1M tokens (20% lower input, 33.3% lower output), promotional through at least Nov 21, 2026

> **Still true:** Terra and Luna pricing rows, and the Mantle-only/Responses-API constraints, remain accurate; only the Sol row's price is stale.
>
> This is why the old value is **not** simply overwritten.

## Proposed edits

Each row states its justification. No CI check can catch a badly reworded judgment, so the
"why" column is the only protection a reviewer has — please read it rather than the diff alone.

### `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:122` — value

```diff
- | GPT-5.6 Sol / GPT-5.5 / o3-pro   | GPT-5.6 Sol            | `openai.gpt-5.6-sol`   | $5.50 / $33.00            | Flagship; frontier reasoning + agentic         |
+ | GPT-5.6 Sol / GPT-5.5 / o3-pro   | GPT-5.6 Sol            | `openai.gpt-5.6-sol`   | $4.00 / $20.00            | Flagship; frontier reasoning + agentic         |
```

**Why:** Announcement states new pricing of $4/$20 per million tokens for Sol, replacing the old $5.50/$33.00 rates.

**Evidence (verbatim from the announcement):** "Sol now costs $4 per million input tokens and $20 per million output tokens"

### `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:118` — value

```diff
- Bedrock in-region pricing is at parity with OpenAI's data-residency tier (a ~10% premium over OpenAI Standard; rates below reflect the July 30 pri
+ Bedrock in-region pricing is at parity with OpenAI's data-residency tier (a ~10% premium over OpenAI Standard; rates below reflect the November 2026 Sol price reduction (following the July 30 Terra/Luna reductions)
```

**Why:** Sol's pricing has been reduced again as of the announcement; the note referencing 'the July 30 price reduction' as the basis for the rates is now stale for Sol.

**Evidence (verbatim from the announcement):** "Following the recent Terra and Luna price reductions, Sol now costs $4 per million input tokens and $20 per million output tokens"

### `gcp-to-aws/references/shared/pricing-cache.md:537` — value

```diff
- | GPT-5.6 Sol   | US East (N. Virginia / Ohio)                   | 5.50               | 33.00               | 11.00              | 49.50               |
+ | GPT-5.6 Sol   | US East (N. Virginia / Ohio)                   | 4.00               | 20.00               | 8.00               | 36.00               |
```

**Why:** Announcement states Sol now costs $4 per million input tokens and $20 per million output tokens, replacing the old $5.50/$33.00 pricing (and any derived batch/cached columns should scale accordingly).

**Evidence (verbatim from the announcement):** "Sol now costs $4 per million input tokens and $20 per million output tokens"

### `gcp-to-aws/references/shared/pricing-cache.md:533` — value

```diff
- In-region rates below reflect the July 30, 2026 price reduction (Luna −80%, Terra −20%) and are at parity with OpenAI's data-residency tier.
+ In-region rates below reflect the July 30, 2026 price reduction (Luna −80%, Terra −20%) plus a subsequent Sol price reduction (20% lower input, 33.3% lower output, promotional through at least Nov 21, 2026), and are at parity with OpenAI's data-residency tier.
```

**Why:** The note describing the basis for the rates only mentions the July 30 reduction, but Sol has now had an additional price cut described in the announcement.

**Evidence (verbatim from the announcement):** "20% lower input pricing and 33.3% lower output pricing. This promotional pricing is available at least through November 21, 2026."

### `gcp-to-aws/references/shared/pricing-cache.md:423` — value

```diff
- | GPT-5.6 Sol                      | openai.gpt-5.6-sol                       | OpenAI    | 5.50       | 33.00       | 1M      | flagship  | active (Mantle/Responses API only)                  |
+ | GPT-5.6 Sol                      | openai.gpt-5.6-sol                       | OpenAI    | 4.00       | 20.00       | 1M      | flagship  | active (Mantle/Responses API only)                  |
```

**Why:** Announcement provides the new per-million-token input/output rates for Sol.

**Evidence (verbatim from the announcement):** "Sol now costs $4 per million input tokens and $20 per million output tokens"

## Mirrored to `migrate/plugins/migration-to-aws/skills`

The same edits were applied to this second copy: 5 applied.


## Known limits of this proposal

- **Blast radius is not stable between runs.** Two runs of the same input returned 9 and 13
  locations and neither was a superset of the other, so this list may be incomplete.
- Paths are relative to `advisor/plugins/aws-startup-advisor/skills`.
- The pipeline did not touch any file the judge did not name.
