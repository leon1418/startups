# Network Mapping Table — Fly → AWS Network Services

## Description

This table documents the AWS equivalents for Fly.io's networking features, including ingress patterns, non-HTTP services, private networking, fly-replay, certificates, secrets management, and shutdown behavior deltas. Some patterns (fly-replay, dynamic service discovery) have no direct AWS equivalent and require code rewrites or architectural changes.

## Ingress

### Single-Region Default

- **Fly pattern**: Anycast + nearest-region fly-proxy
- **AWS default**: Single-region ALB + CloudFront for global distribution
- **Notes**: Most Fly apps are 1–3 regions; don't rebuild multi-region active-active on day one

### True Multi-Region Active-Active

- **Fly pattern**: Anycast with fly-proxy routing to all regions
- **AWS equivalent**: Global Accelerator + per-region ALBs
- **Cost structure**:
  - Global Accelerator: ~$18/mo base ($0.025/hr)
  - Data Transfer-Premium: $0.015–0.105/GB
  - Per-region ALB: ~$16–25/mo each
- **Alternative**: Route53 latency-based routing (cheaper, but DNS-TTL-based failover caveat)

## Non-HTTP Services

| Fly Service Type | AWS Target                 | Notes                                                |
| ---------------- | -------------------------- | ---------------------------------------------------- |
| Raw TCP          | NLB TCP passthrough        | Default TCP listener                                 |
| `tls` handler    | NLB TLS listener / ALB     | Terminate TLS at LB                                  |
| `proxy_proto`    | NLB with proxy-protocol-v2 | Preserve client IP                                   |
| `pg_tls`         | NLB TCP listener           | PostgreSQL with TLS                                  |
| UDP              | NLB UDP listener           | Fly needed dedicated IPv4 + fly-global-services bind |

## Private Networking

### VPC Basics

- **Fly pattern**: 6PN (org-wide WireGuard IPv6 mesh), free cross-region connectivity
- **AWS equivalent**: VPC with cross-region peering or Transit Gateway (paid, not free-by-default)

### Service Discovery

- **Fly pattern**: `.internal` DNS, `.flycast` addresses
- **AWS equivalent**: ECS Service Connect (nearest analogue) or Cloud Map / Route53 private hosted zones
- **Dynamic discovery patterns**: Patterns like `top<N>.nearest.of.<app>.internal` and `_apps.internal` TXT records have **NO AWS equivalent** — code rewrite required. Grep application code for these patterns.

### fly-replay Header

- **Fly pattern**: Response-driven request replay (fly-replay header); requests >1MB are not replayable on Fly
- **AWS equivalent**: **NO direct Load Balancer equivalent** — highest-effort networking flag
- **Rewrite options**:
  - App-level proxy/redirect logic
  - ALB + Lambda@Edge router
  - CloudFront Functions for request routing
  - DB-write-forwarding use case → Aurora Global Database write forwarding feature
- **Detection**: Grep application code for `"fly-replay"` header usage

## v1 Generation Boundary

For fly-replay, dynamic `.internal` discovery, and true multi-region active-active, v1 emits decision records + specialist gates only — it detects, explains options, and flags effort, but never generates rewrite code or multi-region infrastructure.

## Certificates

- **Fly pattern**: `fly certs` command, Let's Encrypt certificates, $0.10/mo/hostname after first 10
- **AWS equivalent**: ACM (AWS Certificate Manager) free certificates + ALB or CloudFront
- **SaaS many-domain pattern**: CloudFront SaaS Manager or ALB SNI (25-cert/ALB limit)

## Secrets Management

### Default Target

- **AWS default**: SSM Parameter Store standard tier = $0 (no cost)
- **Alternative**: AWS Secrets Manager ($0.40/secret/mo) — only use for rotation or cross-account access requirements

### ECS Integration

- **Pattern**: ECS task definition `secrets:` with `valueFrom` reproduces Fly's env contract exactly — zero app-code change
- **Critical constraint**: **Fly secret values cannot be exported** — all values must be re-sourced from their systems of record before migration

### File-Based Secrets

- **Fly pattern**: `[[files]]` section with `secret_name` attribute
- **AWS approach**: Requires entrypoint-shim pattern to write secrets to filesystem at container start

## Shutdown Behavior Delta

- **Fly default**: `kill_signal = SIGINT`
- **ECS default**: `SIGTERM`
- **Migration requirement**: Generated ECS task definitions must:
  - Set `stopTimeout` from fly.toml's `kill_timeout` value
  - Flag in migration guide that apps trapping SIGINT need adjustment
  - Ensure graceful shutdown handlers are signal-aware

## Error Handling

If a networking pattern is detected but has no AWS equivalent (e.g., dynamic `.internal` discovery, fly-replay), emit:

> "No direct AWS equivalent. Code rewrite required. Deferred to specialist engagement."
