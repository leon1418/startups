# Investor Readiness

## Why Architecture Matters to Investors

Investors don't evaluate your Terraform code. But they do ask:
- "Can this scale to 10x/100x users without a rewrite?"
- "What's your infrastructure cost as a percentage of revenue?"
- "Do you have a single point of failure?"
- "How fast can you ship new features?"

Your architecture tells a story about execution capability and capital efficiency. This reference helps you frame technical decisions in terms investors understand.

---

## Architecture Narratives by Stage

### Pre-Seed / Seed Pitch

Investors at this stage care about speed and capital efficiency, not technical sophistication.

**What to communicate**:
- "We built this in X weeks with Y people" (execution speed)
- "Our infrastructure costs $Z/month and scales automatically" (capital efficiency)
- "We can handle 100x our current traffic without re-architecting" (serverless = true by default)
- "We're using AWS credits efficiently — X months of runway remaining" (financial discipline)

**What NOT to say**:
- Don't brag about Kubernetes, microservices, or complex architecture — it signals over-engineering
- Don't say "we'll need to rewrite when we scale" — it signals poor planning
- Don't mention specific AWS services by name unless the investor is technical

**Architecture story template**:
> "We built on serverless AWS infrastructure that costs near-zero at our current scale and grows linearly with users. Our monthly infrastructure cost is $X, and with our current credits, we have Y months of runway before infrastructure becomes a line item. The architecture handles 100x our current load without changes."

---

### Series A Pitch

Investors at this stage care about reliability, team efficiency, and unit economics.

**What to communicate**:
- "Infrastructure cost per user is $X and decreasing as we scale" (unit economics)
- "We deploy multiple times per day with zero downtime" (engineering velocity)
- "We've had X% uptime over the last Y months" (reliability)
- "Our infrastructure scales automatically — we don't need to hire DevOps to grow 10x" (capital efficiency)
- "We're SOC2 ready / compliant" (enterprise sales readiness, if applicable)

**Key metrics to have ready**:
| Metric | What It Shows | Target |
|---|---|---|
| Infra cost / user / month | Capital efficiency | Decreasing over time |
| Deploy frequency | Engineering velocity | Daily or more |
| Uptime (last 90 days) | Reliability | >99.5% |
| Mean time to recovery | Operational maturity | <1 hour |
| Infra cost as % of revenue | Margin health | <10% for SaaS |

---

### Series B+ Pitch

Investors at this stage care about operational maturity and scalability ceiling.

**What to communicate**:
- "We have a dedicated platform team that enables product teams to ship independently"
- "Our architecture supports multi-region deployment for compliance and latency"
- "Infrastructure cost grows sub-linearly with revenue" (economies of scale)
- "We have formal SLOs and incident management processes"
- "We can enter new markets (regions, compliance regimes) without re-architecting"

---

## Scalability Story Patterns

### "Scales to Zero, Scales to Millions"

For serverless architectures (Lambda + DynamoDB + API Gateway):

> "Our architecture is fully serverless. At zero traffic, our cost is zero. At our current traffic of X requests/day, we pay $Y/month. The same architecture handles millions of requests without any changes — AWS scales it automatically. There's no capacity planning, no servers to manage, and no scaling bottleneck."

**When this story works**: Pre-revenue through Series A, API-driven products, variable traffic.

### "Linear Cost, Exponential Value"

For products where infrastructure cost grows slower than revenue:

> "Our infrastructure cost grows linearly with users at approximately $X per 1000 users/month. But our revenue per user is $Y/month, giving us Z:1 ratio of revenue to infrastructure cost. As we scale, this ratio improves because of caching, shared resources, and volume discounts."

**When this story works**: SaaS products, marketplace models, any product with positive unit economics.

### "Built for Enterprise from Day One"

For startups selling to enterprise customers:

> "We architected for enterprise requirements from the start: data encryption at rest and in transit, SOC2 compliance, tenant isolation, and 99.9% availability SLA. This isn't something we'll need to retrofit — it's how we built it. We can onboard enterprise customers without architecture changes."

**When this story works**: B2B SaaS targeting enterprise, regulated industries.

---

## Red Flags Investors Look For

| Red Flag | What It Signals | How to Avoid |
|---|---|---|
| "We'll need to rewrite at scale" | Poor planning, future capital sink | Design for 10-100x from the start using serverless/managed services |
| Very high infra cost relative to revenue | Capital inefficiency | Use credits wisely, right-size, prefer pay-per-use services |
| Single engineer who "knows everything" | Bus factor risk | Document architecture, use IaC, avoid custom complexity |
| No monitoring or uptime data | Operational immaturity | Set up basic monitoring from day one, track uptime |
| Over-engineered for current scale | Wasted capital, slow shipping | Match complexity to actual needs, not hypothetical future |
| Vendor lock-in without justification | Strategic risk | Acknowledge lock-in trade-offs, explain why it's worth it |

---

## Cost Narratives

### How to Present AWS Costs to Investors

**Don't**: Show a raw AWS bill with 47 line items.

**Do**: Present costs in business terms:

```
Monthly Infrastructure: $X,XXX
├── Compute (API + background jobs): $XXX (XX%)
├── Database: $XXX (XX%)
├── AI/ML (Bedrock inference): $XXX (XX%)
├── Storage + CDN: $XXX (XX%)
└── Other (monitoring, DNS, etc.): $XXX (XX%)

Cost per active user: $X.XX/month
Cost as % of MRR: X%
Credits remaining: $XX,XXX (X months at current burn)
```

### Unit Economics Framework

| Metric | Formula | Healthy Range (SaaS) |
|---|---|---|
| Infra cost per user | Total AWS / active users | $0.50-5.00/month |
| Infra as % of revenue | Total AWS / MRR | 5-15% |
| Gross margin impact | (Revenue - COGS including infra) / Revenue | >70% |
| Cost scaling factor | % infra growth / % user growth | <1.0 (sub-linear) |

---

## Due Diligence Preparation

Technical due diligence at Series A+ may include architecture review. Be ready to explain:

1. **Architecture diagram**: One-page showing major components and data flow
2. **Scaling plan**: What changes at 10x and 100x current load (ideally: nothing)
3. **Single points of failure**: Identify them honestly, explain mitigation plan
4. **Disaster recovery**: RTO/RPO targets and how you meet them
5. **Security posture**: Encryption, access control, compliance certifications
6. **Technical debt**: Acknowledge it honestly, show a plan to address it
7. **Team dependency**: No single person should be a blocker for any system
8. **Cost trajectory**: Historical costs and projection at target scale
