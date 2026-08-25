> Opened by the knowledge auto-update pipeline. **Draft** — a human decides.

## What changed upstream

[OpenAI GPT-5.6 Terra and Luna now available on Amazon Bedrock in AWS GovCloud (US)](https://aws.amazon.com/about-aws/whats-new/2026/08/openai-gpt-terra-luna-govcloud/)

**Verdict: `schema_change`** on `bedrock.openai_gpt56_region_availability`

- was — Region availability: us-east-1, us-east-2, us-west-2 at minimum (commercial regions only)
- now — Region availability now spans two partitions: commercial regions (us-east-1, us-east-2, us-west-2, check pricing page) AND AWS GovCloud (US-West, US-East) for Terra and Luna specifically — Sol's GovCloud availability is not stated in this announcement.

> **Still true:** Commercial-region availability (us-east-1, us-east-2, us-west-2) for GPT-5.6 Sol/Terra/Luna remains correct as stated.
>
> This is why the old value is **not** simply overwritten.

## Proposed edits

Each row states its justification. No CI check can catch a badly reworded judgment, so the
"why" column is the only protection a reviewer has — please read it rather than the diff alone.

### `agent-advisor/references/models/openai-bedrock-2026-07-21.json:136` — value

```diff
- "openai_gpt_5_6_luna": {
+ "openai_gpt_5_6_luna": { // region_availability should be updated to include AWS GovCloud (US-West, US-East) in addition to commercial regions (us-east-1, us-east-2, us-west-2)
```

**Why:** The announcement states Luna is now generally available in AWS GovCloud (US-West) and (US-East) in addition to commercial regions, so the region_availability field for this model entry must be updated to reflect the new GovCloud partitions.

**Evidence (verbatim from the announcement):** "GPT-5.6 Terra and Luna are now generally available on Amazon Bedrock in AWS GovCloud (US-West) and AWS GovCloud (US-East)"

### `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:133` — value

```diff
- - **Region availability.** Confirm the target region serves GPT-5.6 on Mantle (us-east-1, us-east-2, us-west-2 at minimum; check the pricing page for current list).
+ - **Region availability.** Confirm the target region serves GPT-5.6 on Mantle (us-east-1, us-east-2, us-west-2 at minimum for commercial regions; Terra and Luna are now also available in AWS GovCloud (US-West, US-East); check the pricing page for current list).
```

**Why:** Announcement states GPT-5.6 Terra and Luna are now generally available on Amazon Bedrock in AWS GovCloud (US-West) and AWS GovCloud (US-East), adding a new partition not reflected in this region-availability guidance.

**Evidence (verbatim from the announcement):** "GPT-5.6 Terra and Luna are now generally available on Amazon Bedrock in AWS GovCloud (US-West) and AWS GovCloud (US-East)"

### `gcp-to-aws/references/shared/pricing-cache.md:539` — value

```diff
- | GPT-5.6 Luna  | US East (N. Virginia / Ohio), US West (Oregon) | 0.22               | 1.32                | 0.44               | 1.98                |
+ | GPT-5.6 Luna  | US East (N. Virginia / Ohio), US West (Oregon), AWS GovCloud (US-West), AWS GovCloud (US-East) | 0.22               | 1.32                | 0.44               | 1.98                |
```

**Why:** Announcement states Luna is now GA on Bedrock in AWS GovCloud (US-West) and (US-East) in addition to commercial regions.

**Evidence (verbatim from the announcement):** "GPT-5.6 Terra and Luna are now generally available on Amazon Bedrock in AWS GovCloud (US-West) and AWS GovCloud (US-East)"

### `gcp-to-aws/references/shared/pricing-cache.md:538` — value

```diff
- | GPT-5.6 Terra | US East (N. Virginia / Ohio), US West (Oregon) | 2.20               | 13.20               | 4.40               | 19.80               |
+ | GPT-5.6 Terra | US East (N. Virginia / Ohio), US West (Oregon), AWS GovCloud (US-West), AWS GovCloud (US-East) | 2.20               | 13.20               | 4.40               | 19.80               |
```

**Why:** Announcement states Terra is now GA on Bedrock in AWS GovCloud (US-West) and (US-East) in addition to commercial regions.

**Evidence (verbatim from the announcement):** "GPT-5.6 Terra and Luna are now generally available on Amazon Bedrock in AWS GovCloud (US-West) and AWS GovCloud (US-East)"

## Filter false positives

The announcement scan flagged these files; the judge rejected them:

- `agent-advisor/references/decision-refs/model-selection.md`

## Mirrored to `migrate/plugins/migration-to-aws/skills`

The same edits were applied to this second copy: 4 applied.


## Known limits of this proposal

- **Blast radius is not stable between runs.** Two runs of the same input returned 9 and 13
  locations and neither was a superset of the other, so this list may be incomplete.
- Paths are relative to `advisor/plugins/aws-startup-advisor/skills`.
- The pipeline did not touch any file the judge did not name.
