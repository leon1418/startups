> Opened by the knowledge auto-update pipeline. A recommendation **reversed** — nothing was
> rewritten. The maintainer decides the position below; the pipeline then does the typing.

## 1 · What changed

[OpenAI frontier models and Codex are now available on AWS](https://openai.com/index/openai-frontier-models-and-codex-are-now-available-on-aws)

- was — File frames the decision as strictly binary: either migrate OpenAI workloads to Bedrock models (Claude/Nova/etc.) or stay on OpenAI's own API, with the only "AWS + OpenAI" bridge being gpt-oss open-weight models on Bedrock and the Mantle OpenAI-compat endpoint pointing at Bedrock models.
- now — New axis: customers can now run actual OpenAI frontier models (e.g. GPT-5.x, o-series) and Codex directly on AWS infrastructure/procurement (not just gpt-oss or Bedrock-hosted alternatives), giving a third path — "stay on OpenAI models, but consume via AWS" — distinct from both "migrate to Bedrock models" and "stay on OpenAI's own cloud/API."
- still true — The existing OpenAI-model vs. Bedrock-model price/feature comparison tables remain valid for customers who actually switch model families (e.g., GPT-5.4 → Claude Sonnet 4.6).

AWS now offers OpenAI's actual frontier models (GPT-5.x, o-series) and Codex as a hosted/procured option on AWS infrastructure, not just the open-weight gpt-oss models on Bedrock or the Mantle compat shim in front of Bedrock-native models. This creates a third migration path — keep using real OpenAI models but consume/procure them through AWS — separate from "switch to Bedrock model families" and "stay entirely on OpenAI's own cloud." The announcement is a GA availability claim; it does not by itself establish pricing parity, regional coverage, feature completeness (e.g. Realtime API), or operational maturity relative to OpenAI's native API.

> "OpenAI frontier models and Codex are now generally available on AWS, giving enterprises a new path to build with OpenAI through the AWS environments, controls, and procurement workflows they already use."
> "giving enterprises a new path to build with OpenAI through the AWS environments, controls, and procurement workflows they already use"

## 2 · Recommendations it affects

| location | kind | current text |
| --- | --- | --- |
| `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:134` | conclusion flips | - Want to stay on OpenAI models → gpt-oss on Bedrock (same models, AWS infrastructure) |
| `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:163` | conclusion flips | \| Realtime API         \| No equivalent                            \| Stay on OpenAI for this                                                                   |

## 3 · The decision space

- **Keep recommending gpt-oss on Bedrock for customers who want 'same models, AWS infra' but are fine with the open-weight variants (not frontier GPT-5.x/o-series) and want native Bedrock integration/pricing.** — depends on: customer accepting gpt-oss capability/quality gap vs frontier models, and wanting deep Bedrock-native tooling
- **Recommend the new AWS-hosted OpenAI frontier models/Codex path for customers who want to keep actual frontier OpenAI models but need AWS procurement, IAM/VPC controls, or billing consolidation.** — depends on: verifying GA scope (which models, which regions), pricing vs OpenAI-direct, contractual/procurement terms, and feature parity (esp. Realtime API) at time of adoption
- **Keep recommending customers stay on OpenAI's own API/cloud directly, bypassing AWS entirely, for workloads where AWS procurement adds no value or where the AWS-hosted offering lags OpenAI-direct in features/latency/region support.** — depends on: customer having no AWS procurement/compliance constraint forcing AWS consumption
- **For Realtime API specifically, re-verify whether AWS-hosted OpenAI now includes Realtime API support; if not, keep 'stay on OpenAI directly for this' as the recommendation.** — depends on: explicit confirmation of Realtime API availability/parity in the AWS GA offering
- **Continue recommending migration to Bedrock-native model families (Claude/Nova) for customers actually willing to switch model families, unaffected by this change.** — depends on: customer being open to changing model family, not just hosting/procurement path

## 4 · Proposed position

> Replace the binary framing with three explicit paths: (1) migrate to Bedrock-native models (Claude/Nova/etc.) — unchanged, existing comparison tables apply; (2) stay on OpenAI models but consume via AWS-hosted frontier OpenAI/Codex GA offering — recommended for customers whose primary driver is AWS procurement, billing, IAM/VPC, or compliance rather than model capability, PROVIDED the specific model, region, and feature (e.g. Realtime API) needed is confirmed available and priced comparably at adoption time; (3) stay on OpenAI's own API/cloud directly — still the right default for customers with no AWS procurement constraint, or where the AWS-hosted path currently lags in region coverage, feature parity, or pricing. Do not default to path 2 over path 3 solely because it's newer; treat it as unproven at GA and re-verify per-workload before recommending. Downgrade the gpt-oss-on-Bedrock recommendation to a narrower case: only for customers explicitly fine with open-weight models rather than frontier GPT-5.x/o-series. For Realtime API specifically, keep "stay on OpenAI directly" until AWS GA parity for Realtime API is explicitly confirmed.

**Assumptions to verify before adopting:**

- The AWS-hosted OpenAI frontier models/Codex offering is genuinely GA (not preview/limited-access) at the time this brief is applied — verify current status.
- Pricing for AWS-hosted OpenAI models is not yet confirmed to match or beat OpenAI-direct pricing; assume it may differ (markup, AWS billing overhead, egress, etc.) until checked.
- Regional availability of the AWS-hosted OpenAI offering may be limited to specific AWS regions and may not match OpenAI's own region/data-residency options.
- Feature parity (Realtime API, streaming, fine-tuning, batch, tool-calling nuances) between AWS-hosted OpenAI and OpenAI-direct is NOT assumed equal — must be verified feature-by-feature, especially Realtime API which is explicitly called out as unsupported previously.
- gpt-oss models remain distinct from and less capable than frontier GPT-5.x/o-series; customers wanting frontier capability should not be routed to gpt-oss as a substitute.
- No SLA/support-model maturity data yet exists for the AWS-hosted OpenAI path; treat as operationally unproven versus OpenAI's established direct API until real-world usage data accumulates.
- Procurement/contractual differences (AWS Marketplace terms, data processing agreements, compliance certifications) between AWS-hosted OpenAI and OpenAI-direct are unverified and could affect suitability for regulated workloads.
- This change does not alter the validity of any existing Bedrock-model-family (Claude/Nova) comparison content — that remains a separate, unaffected decision axis.

## Decision — tick one; the next run acts on it

- [ ] **Adopt the proposed position** — the pipeline rewrites the affected locations and opens a draft PR for review
- [ ] **Adopt with changes** — edit the "Proposed position" text above first, then tick this
- [ ] **Reject** — close this issue; nothing is rewritten

<!-- kb-autoupdate-brief:ai-openai-to-bedrock.migration_framing -->
<!-- kb-autoupdate-run:2026-08-21T034450Z:results-judge-080f4484a7.json -->
