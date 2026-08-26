> Opened by the knowledge auto-update pipeline. **Draft** — a human decides.

## What changed upstream

[AWS Lambda MicroVMs now supports AWS PrivateLink](https://aws.amazon.com/about-aws/whats-new/2026/08/lambda-microvms-supports-privatelink)

**Verdict: `schema_change`** on `lambda-microvms.networking`

- was — Networking: per-MicroVM URL over TLS; public service endpoints; VPC endpoints only if policy demands.
- now — Networking: per-MicroVM URL over TLS; public service endpoints OR private connectivity via AWS PrivateLink VPC Endpoints (for MicroVM control-plane API calls and per-MicroVM HTTP endpoint connections), available in all regions where Lambda MicroVMs is available.

> **Still true:** Public service endpoints and per-MicroVM URL over TLS remain valid for non-regulated/default use cases.
>
> This is why the old value is **not** simply overwritten.

## Proposed edits

Each row states its justification. No CI check can catch a badly reworded judgment, so the
"why" column is the only protection a reviewer has — please read it rather than the diff alone.

### `agent-advisor/references/decision-refs/lambda-microvms.md:44` — value

```diff
- Networking: per-MicroVM URL over TLS; public service endpoints; VPC endpoints only if policy demands.
+ Networking: per-MicroVM URL over TLS; public service endpoints OR private connectivity via AWS PrivateLink VPC Endpoints (for MicroVM control-plane API calls and per-MicroVM HTTP endpoint connections), available in all regions where Lambda MicroVMs is available.
```

**Why:** This is the exact old fact string for lambda-microvms.networking being replaced by the announcement of PrivateLink support for Lambda MicroVMs.

**Evidence (verbatim from the announcement):** "AWS Lambda MicroVMs now supports AWS PrivateLink, enabling private connectivity to Lambda MicroVMs directly from Amazon Virtual Private Cloud (VPC) resources without exposing traffic to the public internet."

## Mirrored to `migrate/plugins/migration-to-aws/skills`

The same edits were applied to this second copy: 1 applied.


## Known limits of this proposal

- **Blast radius is not stable between runs.** Two runs of the same input returned 9 and 13
  locations and neither was a superset of the other, so this list may be incomplete.
- Paths are relative to `advisor/plugins/aws-startup-advisor/skills`.
- The pipeline did not touch any file the judge did not name.
