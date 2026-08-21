> Opened by the knowledge auto-update pipeline. A recommendation **reversed** — nothing was
> rewritten. The maintainer decides the position below; the pipeline then does the typing.

## 1 · What changed

[OpenAI frontier models and Codex are now available on AWS](https://openai.com/index/openai-frontier-models-and-codex-are-now-available-on-aws)

- was — Guide frames OpenAI-to-AWS migration purely as "migrate to Bedrock" (switch to Claude/Nova models) vs "stay on OpenAI" (keep using OpenAI's own API/infrastructure) — a two-option binary based on price/feature comparison tables.
- now — New third option: run OpenAI frontier models + Codex directly on AWS (native availability, not gpt-oss open-weight equivalents) using AWS environments/controls/procurement, while still calling actual OpenAI models rather than switching to Bedrock model families.
- still true — The existing Bedrock-vs-OpenAI pricing/feature comparison tables remain valid for customers choosing between OpenAI's own hosting and Bedrock-native models (Claude/Nova/etc.).

AWS announced GA availability of OpenAI's actual frontier models and Codex running natively within AWS environments, using AWS procurement, IAM, and controls — this is distinct from the existing gpt-oss open-weight models already available on Bedrock. This adds a third migration option (real OpenAI models on AWS infra) rather than replacing the existing choice between staying on OpenAI's own hosting and moving to Bedrock-native models like Claude/Nova.

> "OpenAI frontier models and Codex are now generally available on AWS, giving enterprises a new path to build with OpenAI through the AWS environments, controls, and procurement workflows they already use."

## 2 · Recommendations it affects

| location | kind | current text |
| --- | --- | --- |
| `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:134` | conclusion flips | - Want to stay on OpenAI models → gpt-oss on Bedrock (same models, AWS infrastructure) |
| `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:163` | derived judgment | \| Realtime API         \| No equivalent                            \| Stay on OpenAI for this                                                                   |
| `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:143` | derived judgment | - Need Realtime API (no Bedrock equivalent) |
| `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:3` | derived judgment | **Applies to:** OpenAI SDK usage detected in GCP-hosted applications → Amazon Bedrock |
| `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:108` | derived judgment | ### OpenAI Models on Bedrock (gpt-oss) |
| `gcp-to-aws/references/design-refs/ai-openai-to-bedrock.md:112` | derived judgment | \| OpenAI Model \| Price (in/out per 1M) \| Bedrock gpt-oss \| Bedrock Price \| Notes                                 \| |

## 3 · The decision space

- **Keep gpt-oss on Bedrock as the recommended path for teams wanting to 'stay on OpenAI-style models but move to AWS infra' when they are open-weight-model-tolerant and prioritize Bedrock-native tooling/pricing simplicity over exact frontier-model parity** — depends on: workload accepts open-weight model quality/behavior differences from actual OpenAI frontier models, and team wants single Bedrock billing/IAM surface
- **Adopt native OpenAI frontier models + Codex on AWS as the recommended path when the requirement is 'actual OpenAI models, AWS procurement/controls' — i.e., the workload specifically depends on GPT-frontier or Codex behavior and cannot be satisfied by gpt-oss** — depends on: confirmed GA access in the customer's AWS region, verified pricing vs. direct OpenAI API, and no unacceptable latency/support gaps discovered in evaluation
- **Stay on direct OpenAI API/infrastructure (no AWS involvement) for customers who have no procurement/compliance driver to move to AWS and want simplest, most mature integration path** — depends on: customer has no AWS commitment/EDP pressure and prioritizes maturity/simplicity over infra consolidation
- **Migrate fully to Bedrock-native models (Claude/Nova) per existing comparison tables when the customer is model-agnostic and optimizing for AWS-native ecosystem fit, cost, or feature set rather than OpenAI-specific capabilities** — depends on: workload does not require OpenAI-specific model behavior and existing price/feature tables favor Claude/Nova for the use case

## 4 · Proposed position

> Replace the binary framing with a three-way decision: (1) if the workload requires actual OpenAI frontier models or Codex AND the customer needs AWS procurement/IAM/controls, evaluate the new native OpenAI-on-AWS GA offering — but pilot it first to confirm region availability, pricing vs. direct OpenAI API, and latency/support before committing production workloads; (2) if the customer is open to open-weight models and wants the simplest single-vendor Bedrock billing/tooling story, gpt-oss on Bedrock remains a valid 'stay-OpenAI-style, move-to-AWS' path — do not present it as obsolete; (3) if there's no AWS procurement driver, staying on direct OpenAI infrastructure is still reasonable. Do not default to the new native-AWS OpenAI path as a blanket replacement for gpt-oss-on-Bedrock — they solve different problems (model fidelity vs. open-weight/AWS-native simplicity) and the new path is unproven in production at GA.

**Assumptions to verify before adopting:**

- The AWS GA announcement means real OpenAI frontier models + Codex are callable via an AWS-native path (e.g. Bedrock or adjacent service) with SLA-backed availability, not a limited preview or allowlisted beta — verify current access model/region list before publishing.
- Pricing for this new path has not been independently verified against direct OpenAI API pricing or existing Bedrock gpt-oss pricing; assume it is unknown/unfavorable until confirmed, since AWS-hosted frontier models may carry a premium or different metering (e.g. per-token vs. committed throughput).
- gpt-oss on Bedrock is open-weight and architecturally different from OpenAI's frontier models (GPT-4-class/Codex); it is NOT a lower-fidelity substitute for teams who specifically need frontier-model behavior/quality, so the two options serve different fidelity tiers, not a strict upgrade/downgrade pair.
- Regional availability of the new native-OpenAI-on-AWS path is likely narrower at GA than existing Bedrock regions; teams with strict data-residency requirements must verify region parity before migrating workloads.
- No independent evidence yet on latency, rate limits, or enterprise support SLAs for OpenAI-on-AWS versus OpenAI's own API or Bedrock gpt-oss — treat as unproven for production-critical workloads until customer reports or benchmarks exist.
- Procurement/billing consolidation (the main stated benefit) is only valuable for customers already committed to AWS EDP/Marketplace spend; it is irrelevant or even a negative for customers optimizing purely for model cost or already on direct OpenAI billing.
- This is a same-day GA announcement with no third-party production case studies yet; the maintainer should treat this as 'newly available' not 'battle-tested' when framing confidence level in the skill.

## Decision — tick one; the next run acts on it

- [ ] **Adopt the proposed position** — the pipeline rewrites the affected locations and opens a draft PR for review
- [ ] **Adopt with changes** — edit the "Proposed position" text above first, then tick this
- [ ] **Reject** — close this issue; nothing is rewritten

<!-- kb-autoupdate-brief:ai.openai_to_bedrock.migration_framing -->
<!-- kb-autoupdate-run:2026-08-21T044442Z:results-judge-080f4484a7.json -->
