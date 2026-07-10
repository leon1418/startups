# Fast-Path Table — Fly Extension/Service → AWS Service Mappings

## Description

This table provides deterministic mappings from Fly.io extensions and integrated services to AWS service equivalents. The Design Engine uses this table during the design phase to automatically map known extensions without requiring specialist evaluation. Extensions matched here receive clear migration difficulty assessments and specific detection signals.

## Lookup Table

| Fly Extension/Service | Detection Signal                                                                                                               | AWS Target                                     | Migration Difficulty | Notes                                                                                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tigris                | `AWS_ENDPOINT_URL_S3=fly.storage.tigris.dev` or `t3.storage.dev`; keys `tid_`/`tsec_`; `[[statics]].tigris_bucket` in fly.toml | S3                                             | LOW                  | Endpoint/credential swap + `aws s3 sync`; region `auto` → real region; +CloudFront if edge reads mattered; egress cost-shape change $0.09/GB flagged |
| Upstash Redis         | `fly-<name>.upstash.io` endpoint                                                                                               | ElastiCache Serverless (Valkey)                | MEDIUM               | VPC-only; **HTTP/REST client code must switch to a Redis-protocol client** — flagged rewrite                                                         |
| Upstash Vector        | `VECTOR_ENDPOINT`/`VECTOR_TOKEN` secrets                                                                                       | OpenSearch Serverless vector / Aurora pgvector | MEDIUM               | Beta on Fly; choose target based on query patterns                                                                                                   |
| MySQL extension       | MySQL connection strings                                                                                                       | RDS MySQL / Aurora MySQL                       | LOW                  | Provider behind extension unverified — map by engine                                                                                                 |
| Sentry                | `SENTRY_DSN` secret                                                                                                            | Keep as SaaS                                   | NONE                 | Endpoint-agnostic                                                                                                                                    |
| Arcjet                | `ARCJET_KEY` secret                                                                                                            | Keep as SaaS                                   | NONE                 | Optional AWS WAF note                                                                                                                                |
| Supabase extension    | Supabase references in config                                                                                                  | Already **discontinued** on Fly                | N/A                  | Docs page is a shutdown notice — treat as external Supabase                                                                                          |
| FKS (Fly Kubernetes)  | K3s/FKS config                                                                                                                 | EKS                                            | HIGH                 | Detect-only v1 — closed beta on Fly                                                                                                                  |
| Sprites               | `sprites.dev` references, Machines API sandbox calls                                                                           | Detect-only v1: no generated migration         | HIGH                 | Sandbox workloads → agent-advisor handoff (routing layer 0)                                                                                          |

## Interpretation Notes

- **Matching rule**: Extensions are detected via fly.toml sections, environment variable patterns, or API endpoint references. Detection signals must match the patterns listed in the "Detection Signal" column.
- **Migration difficulty levels**:
  - **NONE**: No migration needed, keep existing SaaS integration
  - **LOW**: Configuration/credential swap only, no code changes
  - **MEDIUM**: Some code changes required (client libraries, endpoints)
  - **HIGH**: Significant architectural changes or detect-only (no automated migration)
- **Specialist gate**: Any extension whose name or pattern does not match an entry in this table is marked as `"Deferred — specialist engagement"` with no automated AWS mapping applied. The deferred record must include: extension name, detection context, reason for deferral, and a recommendation to engage the AWS account team.

## Error Handling

If a discovered extension or service pattern is not found in this table (no match via detection signals), mark it as deferred:

> "Extension not in this table → Deferred — specialist engagement. No automated mapping."
