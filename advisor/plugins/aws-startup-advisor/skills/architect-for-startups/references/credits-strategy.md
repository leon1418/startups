# Credits Strategy

## AWS Activate Credits Overview

AWS Activate provides credits to startups at various tiers. For full eligibility details, program tiers, and application process, reference the `knowledge-base-for-startups` skill.

Key facts for architecture decisions:
- Credits have expiration dates (typically 1-2 years from activation)
- Credits apply to most AWS services but NOT: Route53 domain registration, AWS Marketplace purchases, support plan upgrades, or services billed through third parties
- Credits are applied automatically to your bill — no action needed per service
- Credits apply AFTER free tier discounts (free tier is consumed first)

---

## Credits Burn Rate by Service

### High Burn (avoid or minimize at early stages)

| Service | Monthly Cost at Minimal Use | Why It Burns Fast |
|---|---|---|
| NAT Gateway | $32+ (fixed) + $0.045/GB processed | Charged even at zero traffic |
| EKS Control Plane | $73/month (fixed) | Per-cluster, regardless of workload |
| Multi-AZ RDS (db.t3.medium) | ~$130/month | 2x single-AZ cost |
| ElastiCache (cache.t3.micro) | ~$25/month | Fixed cost, even idle |
| OpenSearch (managed) | ~$50+/month | Minimum instance cost |
| Redshift (dc2.large) | ~$180/month | Minimum node cost |
| CloudWatch custom metrics | $0.30/metric/month | Scales with cardinality |
| VPN Connection | $36/month | Fixed hourly charge |

### Low Burn (prefer these)

| Service | Cost Model | Why It's Credits-Friendly |
|---|---|---|
| Lambda | Per-invocation + duration | $0 at zero traffic, scales linearly |
| DynamoDB (on-demand) | Per-request | $0 at zero traffic |
| API Gateway (HTTP API) | $1/million requests | Near-zero at low traffic |
| S3 | Per-GB stored + requests | Pennies at startup scale |
| SQS | Per-request | $0 at zero traffic |
| EventBridge | $1/million events | Near-zero at low traffic |
| SES | $0.10/1000 emails | Pay only for what you send |
| CloudFront | Per-GB + per-request | 1TB/month free tier |
| Step Functions Express | Per-invocation + duration | $0 at zero traffic |
| Aurora Serverless v2 | Per-ACU-second | Scales to 0.5 ACU minimum (~$43/mo) |

### Free Tier Maximizers

These services have generous free tiers that may cover your entire usage at early stages:

| Service | Free Tier | Typical Startup Coverage |
|---|---|---|
| Lambda | 1M requests + 400K GB-seconds/month | Covers most seed-stage APIs entirely |
| DynamoDB | 25 GB + 25 WCU + 25 RCU | Covers small apps entirely |
| API Gateway | 1M REST calls/month (12 months) | Covers early API traffic |
| S3 | 5 GB + 20K GET + 2K PUT (12 months) | Covers small asset storage |
| CloudFront | 1 TB transfer/month | Covers most startup CDN needs |
| Cognito | 50K MAU (always free) | Covers auth for most startups indefinitely |
| SNS | 1M publishes/month | Covers notification needs |
| SQS | 1M requests/month | Covers async processing |
| CloudWatch | 10 custom metrics, 5 GB logs ingestion | Covers basic monitoring |
| X-Ray | 100K traces/month | Covers basic tracing |

---

## Credits Runway Calculator

### Formula

```
Months of runway = Credits balance / Monthly AWS spend
```

### Monthly Spend Estimation by Stage

| Stage | Typical Monthly Spend | $1K Credits Lasts | $10K Credits Lasts | $25K Credits Lasts | $100K Credits Lasts |
|---|---|---|---|---|---|
| Pre-Revenue | $0-50 | 20+ months | Years | Years | Years |
| Seed | $100-500 | 2-10 months | 20+ months | 50+ months | Years |
| Series A | $1K-10K | <1 month | 1-10 months | 2.5-25 months | 10-100 months |

### Burn Rate Red Flags

Watch for these patterns that accelerate credit consumption:

- **NAT Gateway data processing**: Chatty microservices behind NAT can burn $100+/month in data processing alone
- **CloudWatch Logs without retention**: Default retention is "never expire" — logs accumulate cost forever
- **Unused resources**: Stopped EC2 instances still pay for EBS, unattached EBS volumes, idle load balancers
- **Over-provisioned databases**: RDS instances running at 5% CPU utilization
- **Dev environments running 24/7**: Dev/staging that nobody uses on weekends

---

## Credits Optimization Strategies

### Pre-Revenue ($0-50/month target)

1. Stay within free tier for everything possible
2. Use Lambda + DynamoDB + S3 — all scale to zero
3. No NAT Gateway — use VPC endpoints or avoid VPC entirely
4. No custom VPC if your services don't need it (Lambda, DynamoDB, S3 work without VPC)
5. Set CloudWatch log retention to 7 days for dev, 30 days for prod

### Seed ($100-500/month target)

1. Audit monthly: `aws ce get-cost-and-usage` — know your top 3 cost drivers
2. Replace NAT Gateway with VPC endpoints for S3 and DynamoDB (free)
3. Use DynamoDB on-demand (not provisioned) — you don't know your access patterns yet
4. Set S3 lifecycle policies: move to IA after 30 days, Glacier after 90
5. Use Graviton (ARM) for Lambda and Fargate — 20% cheaper
6. Schedule dev resources to stop outside business hours

### Series A ($1K-10K/month target)

1. Start Savings Plans ONLY after 3+ months of stable usage data
2. Begin with 1-year Compute Savings Plan, No Upfront (lowest commitment)
3. Cover only 50-70% of your baseline — leave room for variability
4. Implement tagging strategy: Environment, Team, Service (enables cost attribution)
5. Set up AWS Budgets with alerts at 80% of monthly target
6. Enable Cost Anomaly Detection (catches unexpected spikes)
7. Consider Spot for stateless workloads (CI/CD, batch processing)

---

## What Credits DON'T Cover

Plan cash budget for these:
- Route53 domain registration fees
- AWS Marketplace third-party software purchases
- AWS Support plan upgrades (Business/Enterprise)
- Data transfer to other cloud providers
- Services billed through third-party integrations

---

## Credits Expiration Planning

Credits expire. Don't lose them.

1. **Check expiration date**: AWS Billing Console → Credits
2. **Plan spending acceleration if needed**: If credits expire in 3 months and you have $50K remaining, consider:
   - Pre-building infrastructure you'll need soon (staging environments, DR setup)
   - Running load tests and performance benchmarks
   - Training/experimenting with Bedrock models
   - Building out observability (dashboards, alarms, tracing)
3. **Don't waste credits on things you won't use**: Spinning up resources just to burn credits is worse than letting some expire
