# Stage Frameworks

## Pre-Revenue / Idea Stage

**Profile**: 1-2 founders, no users, building first version, funded by savings or small pre-seed.

### Core Principle
Ship something users can touch this week. Nothing else matters.

### Architecture Constraints

| Dimension | Constraint |
|---|---|
| Compute | Lambda or App Runner only. Zero server management. |
| Database | DynamoDB (on-demand) or Aurora Serverless v2. Must scale to zero. |
| Networking | No custom VPC needed. Use default VPC or service-managed networking. |
| CI/CD | `git push` → auto-deploy. GitHub Actions or Amplify Hosting. Nothing more. |
| Monitoring | CloudWatch default metrics + alarms on errors. No custom dashboards yet. |
| Security | IAM roles (no access keys), encryption defaults, S3 Block Public Access. Minimum viable. |
| Multi-AZ | No. Single AZ is fine. You have zero users. |
| IaC | Optional. Console or CDK `cdk deploy` from laptop is acceptable. |

### Services to Use

- **API**: API Gateway (HTTP API) + Lambda
- **Frontend**: Amplify Hosting, S3 + CloudFront, or Vercel
- **Database**: DynamoDB (on-demand mode) — $0 at zero traffic
- **Auth**: Cognito (free tier: 50K MAU) or third-party (Auth0, Clerk)
- **Storage**: S3
- **AI**: Bedrock with Nova Micro/Lite for cost-efficient inference

### Services to Avoid

| Service | Why | Use Instead |
|---|---|---|
| EKS | Requires platform team, $73/mo just for control plane | Lambda or App Runner |
| NAT Gateway | $32/mo + data processing even at zero traffic | VPC endpoints or no VPC |
| Multi-AZ RDS | 2x cost for availability you don't need yet | Aurora Serverless v2 (single AZ) or DynamoDB |
| ElastiCache | Fixed cost, operational overhead | DynamoDB DAX or application-level caching |
| CloudWatch custom metrics | $0.30/metric/month adds up | Default metrics only |
| AWS Config | Good practice but costs money at this stage | Defer to Seed stage |

### Cost Target
$0-50/month (within free tier + minimal usage). Credits should last 12+ months.

### "You Don't Need This Yet"
- Service mesh
- Multi-region
- Custom VPC with private subnets
- Dedicated CI/CD pipeline (beyond auto-deploy)
- Observability beyond basic alarms
- Load testing
- Disaster recovery plan

---

## Seed Stage

**Profile**: 2-5 people, first real users (<1K), proving product-market fit, $500K-$2M raised, AWS Activate credits.

### Core Principle
Prove PMF without burning runway on infrastructure. Every dollar spent on infra is a dollar not spent on product.

### Architecture Constraints

| Dimension | Constraint |
|---|---|
| Compute | Lambda (default) or Fargate (if you need containers). No EC2 management. |
| Database | DynamoDB or Aurora Serverless v2. On-demand pricing only — don't commit to provisioned. |
| Networking | Simple VPC if needed (public + private subnets, single NAT or VPC endpoints). |
| CI/CD | GitHub Actions → deploy. One pipeline, one environment (prod). Staging is optional. |
| Monitoring | CloudWatch alarms on 5xx rate, latency p99, and DynamoDB throttles. One dashboard. |
| Security | Enable GuardDuty, CloudTrail. Basic IAM hygiene. No dedicated security review yet. |
| Multi-AZ | Database only (Aurora handles this automatically). Compute is fine single-AZ. |
| IaC | CDK or Terraform. Keep it simple — one stack, not microstack per service. |

### Services to Use

- Everything from Pre-Revenue, plus:
- **Queues**: SQS for async work (decouple heavy processing from API responses)
- **Events**: EventBridge for internal event routing
- **Search**: OpenSearch Serverless (if needed) or Algolia (simpler, SaaS)
- **Email**: SES for transactional email
- **Monitoring**: CloudWatch Logs Insights for ad-hoc debugging

### Services to Avoid

| Service | Why | Use Instead |
|---|---|---|
| EKS | Still too much ops overhead for this team size | Fargate (ECS) if you need containers |
| Redshift | You don't have enough data to need a warehouse | Athena + S3 for analytics |
| Step Functions (Standard) | $0.025/1000 transitions adds up; overkill for simple workflows | SQS + Lambda or Step Functions Express |
| Multiple AWS accounts | Org overhead not worth it yet | Single account with environment tags |
| AWS Config + Security Hub | Good but premature cost | Defer to Series A |

### Cost Target
$100-500/month. Credits should cover 12-18 months at this burn rate.

### Credits Strategy
- Use on-demand everything — don't buy Savings Plans (you don't know your baseline yet)
- Monitor credits burn rate monthly
- Avoid services that don't consume credits (Route53 domain registration, Marketplace purchases)
- See [credits-strategy.md](credits-strategy.md) for detailed guidance

### Trigger to Move to Next Stage
- Consistent user growth (>1K active users)
- Revenue or clear path to revenue
- Raising Series A
- Team growing past 5 engineers
- First reliability incident that costs you users

---

## Series A / Growth Stage

**Profile**: 5-15 engineers, 1K-100K users, product-market fit proven, $5M-$20M raised, scaling.

### Core Principle
Harden what works. Don't re-architect — add reliability and observability to the foundation you built.

### Architecture Constraints

| Dimension | Constraint |
|---|---|
| Compute | Fargate (default) or Lambda. EC2 only for specific workloads (GPU, high-memory). |
| Database | Aurora PostgreSQL (provisioned) or DynamoDB. Start capacity planning. |
| Networking | Proper VPC: public/private/isolated subnets, VPC endpoints for S3/DynamoDB. |
| CI/CD | Full pipeline: build → test → staging → production. Blue/green or canary deploys. |
| Monitoring | Full observability: metrics, logs, traces. SLOs defined. On-call rotation. |
| Security | SOC2 prep. GuardDuty + Security Hub + Config. Quarterly security reviews. |
| Multi-AZ | Yes, for all production workloads. |
| IaC | Everything in code. No console changes to production. Separate stacks by lifecycle. |

### Services to Add

- **Observability**: X-Ray tracing, CloudWatch dashboards per service, composite alarms
- **Security**: Security Hub, AWS Config rules, Secrets Manager rotation
- **Networking**: VPC endpoints (save NAT costs), proper security group segmentation
- **CI/CD**: CodePipeline or GitHub Actions with staging environment, automated tests
- **Cost**: AWS Budgets with alerts, Cost Anomaly Detection
- **Caching**: ElastiCache Redis (if access patterns justify it)
- **CDN**: CloudFront for static assets and API acceleration

### Now Consider

| Service | When It Makes Sense |
|---|---|
| ECS with EC2 | Steady-state workloads where Fargate cost exceeds EC2 + Savings Plans |
| Savings Plans | 3+ months of stable usage data — start with 1-year Compute SP, No Upfront |
| Multi-account | Separate prod from dev/staging. Use AWS Organizations. |
| RDS Proxy | If connection pooling is a problem (Lambda → RDS) |
| WAF | If you're handling sensitive data or seeing abuse |

### Cost Target
$1K-10K/month. Savings Plans can reduce this 20-30% once patterns stabilize.

### Team Structure
- Designate one engineer as "infrastructure lead" (not full-time, but owns it)
- On-call rotation for production issues
- Runbooks for common failure modes
- Weekly cost review (5 minutes, check anomalies)

### Trigger to Move to Next Stage
- 100K+ users
- Team > 15 engineers
- Need for dedicated platform/SRE team
- Multi-region requirements (compliance or latency)
- Revenue justifies infrastructure investment

---

## Series B+ / Scale Stage

**Profile**: 15+ engineers, 100K+ users, proven revenue, $20M+ raised, dedicated platform team.

### Core Principle
Standard AWS best practices apply. The startup-specific constraints have largely dissolved. Focus on operational excellence, cost efficiency at scale, and reliability.

### What Changes

At this stage, the generic AWS service references apply with minimal startup-specific filtering. The main additions:

- **Cost governance**: Tag strategy, per-team budgets, FinOps practice
- **Multi-account**: Landing zone with Control Tower, separate accounts per environment and team
- **Platform team**: Dedicated engineers for CI/CD, observability, security
- **Compliance**: SOC2 certified, HIPAA if needed, formal security program
- **Multi-region**: If latency or compliance requires it

### Services Now Appropriate

- EKS (if you have a platform team)
- Multi-region active-active or active-passive
- Advanced networking (Transit Gateway, PrivateLink)
- Data lake architecture (S3 + Glue + Athena + Redshift)
- Dedicated Savings Plans (3-year if patterns are stable)
- Custom CloudWatch metrics and dashboards per team

### Startup-Specific Considerations That Remain

Even at scale, some startup thinking persists:
- **Speed still matters**: Don't let process slow down shipping. Platform team enables, not gates.
- **Cost per customer**: Track infrastructure cost per user/transaction. Investors care about unit economics.
- **Build vs buy**: Still prefer managed services. Your competitive advantage is your product, not your Kubernetes cluster.
- **Credits may still apply**: Some startups retain Activate benefits through Series B. Check expiration dates.

---

## Stage Transition Checklist

When moving between stages, validate these before increasing complexity:

### Pre-Revenue → Seed
- [ ] You have real users (not just friends testing)
- [ ] You have credits or funding to cover 12+ months of infra
- [ ] You've hit a limitation of the pre-revenue architecture (not just "it feels hacky")

### Seed → Series A
- [ ] You have product-market fit evidence (retention, revenue, growth rate)
- [ ] You've had at least one incident that impacted users
- [ ] Team is growing and needs shared infrastructure standards
- [ ] You can afford $1K+/month in infra without stress

### Series A → Series B+
- [ ] You need a dedicated platform/SRE team (not just one person part-time)
- [ ] Compliance requirements demand formal controls
- [ ] Multi-region or advanced networking is a real requirement, not a nice-to-have
- [ ] Cost optimization at scale justifies dedicated FinOps effort
