# Team Scaling

## Ops Capacity by Team Size

### Solo Founder (1 person)

**You are the entire company.** Every hour spent on infrastructure is an hour not spent on product, sales, or fundraising.

**Rules**:
- Zero ops. If it requires SSH, monitoring, patching, or on-call, you can't use it.
- Managed services only. No self-hosted anything.
- One deployment method: `git push` → auto-deploy.
- One AWS account. No environments beyond production.
- If it breaks at 3am, it waits until morning.

**What you can operate**:
- Lambda + API Gateway + DynamoDB
- Amplify Hosting or S3 + CloudFront
- Cognito for auth
- SES for email
- One CloudWatch alarm (errors > 0)

**What you cannot operate**:
- Anything with "cluster" in the name (ECS, EKS, ElastiCache, OpenSearch)
- Anything requiring capacity planning
- Anything requiring security patching
- Multi-account setups
- CI/CD beyond auto-deploy

---

### Small Team (2-5 engineers)

**You can afford one person spending ~20% of their time on infrastructure.** Not a dedicated role — an engineer who also ships product.

**Rules**:
- One deployment pipeline (GitHub Actions is enough)
- One monitoring dashboard with 5-10 key metrics
- Alerts go to a shared Slack channel, not PagerDuty
- Infrastructure changes via IaC (CDK or Terraform), but one stack is fine
- One AWS account is still acceptable (use tags for environment separation)

**What you can operate**:
- Everything from solo founder, plus:
- ECS Fargate (simple services, no complex networking)
- Aurora Serverless v2
- SQS + EventBridge for async processing
- Basic CloudWatch dashboards
- CDK or Terraform (one person owns it)
- GitHub Actions CI/CD with staging + prod

**What you cannot operate**:
- EKS (requires dedicated platform knowledge)
- Multi-account AWS Organizations
- Complex VPC networking (Transit Gateway, VPN)
- On-call rotation (not enough people)
- SOC2 compliance program (too much process overhead)

---

### Growth Team (5-15 engineers)

**You can designate an infrastructure lead** (still not full-time) and establish basic operational practices.

**Rules**:
- Dedicated infrastructure lead (50% infra, 50% product)
- On-call rotation is now possible (minimum 4 people for sustainable rotation)
- Separate AWS accounts for prod and non-prod
- IaC is mandatory for all production changes
- Incident response process (even if informal)
- Weekly cost review (5 minutes, check for anomalies)

**What you can operate**:
- Everything from small team, plus:
- ECS with EC2 (for cost optimization with Savings Plans)
- Multi-account setup (prod, staging, dev)
- VPC with proper subnet tiers
- ElastiCache Redis
- CloudWatch dashboards per service
- X-Ray tracing
- AWS Config + Security Hub (SOC2 prep)
- Blue/green or canary deployments
- Basic runbooks for common failures

**What you cannot operate**:
- EKS (unless someone has deep Kubernetes experience)
- Multi-region active-active
- Service mesh (Istio, App Mesh)
- Data lake architecture (needs dedicated data engineer)
- Custom observability platform

---

### Platform Team (15+ engineers)

**You can justify a dedicated platform/SRE team** (2-4 people whose full-time job is infrastructure, CI/CD, and reliability).

**Rules**:
- Platform team enables product teams, doesn't gate them
- Self-service infrastructure (golden paths, templates, internal developer platform)
- SLOs defined per service with error budgets
- Formal incident management (severity levels, postmortems, action items)
- FinOps practice (cost attribution per team/service)
- Security program (regular reviews, pen testing, compliance)

**What you can now operate**:
- Everything. The generic AWS service references apply without team-size filtering.
- EKS (with dedicated platform engineers)
- Multi-region (if business requires it)
- Service mesh (if microservice complexity demands it)
- Data lake and analytics infrastructure
- Custom observability with OpenTelemetry
- Advanced networking (Transit Gateway, PrivateLink)

---

## When to Hire for Infrastructure

| Signal | What to Hire | Stage |
|---|---|---|
| Deploys are breaking and nobody knows why | First infra-aware engineer (not full-time infra) | Seed |
| On-call is burning out product engineers | Infrastructure lead (50/50 split) | Early Series A |
| Teams are blocked waiting for infra changes | First dedicated platform engineer | Mid Series A |
| Multiple teams need different deployment patterns | Platform team (2-3 people) | Late Series A / Series B |
| Compliance requires dedicated security focus | Security engineer or DevSecOps | Series A (if SOC2 needed) |
| AWS bill exceeds $50K/month | FinOps or cost-focused engineer | Series B |

### Don't Hire Too Early

Common mistake: hiring a "DevOps engineer" at seed stage. At that point:
- You don't have enough infrastructure to justify a full-time role
- The person will over-engineer because that's their job
- You'll end up with Kubernetes for a 3-service app

Instead: hire product engineers who are comfortable with AWS, and use managed services that don't need a dedicated operator.

### Don't Hire Too Late

Common mistake: waiting until Series B to think about infrastructure. By then:
- You have years of accumulated tech debt
- Production incidents are frequent and painful
- Nobody understands the system holistically
- Hiring is harder because the codebase is intimidating

The right time for a dedicated infra person is when production incidents start costing you users or revenue.

---

## Skill Requirements by Stage

| Stage | AWS Skills Needed | Where to Get Them |
|---|---|---|
| Pre-Revenue | Basic Lambda, DynamoDB, S3 | AWS tutorials, this skill's guidance |
| Seed | IaC basics, CI/CD, monitoring fundamentals | One engineer learns CDK/Terraform |
| Series A | Networking, security, cost optimization, observability | Infra lead + AWS SA engagement |
| Series B+ | Platform engineering, Kubernetes, advanced networking | Dedicated platform team |

---

## Managed Services as Team Multipliers

The smaller your team, the more you should lean on managed services. Each managed service replaces operational work that would otherwise require headcount:

| Self-Managed | Managed Alternative | Ops Hours Saved/Month |
|---|---|---|
| Self-hosted PostgreSQL on EC2 | Aurora or RDS | 10-20 hours (patching, backups, monitoring) |
| Self-hosted Redis on EC2 | ElastiCache | 5-10 hours |
| Self-hosted Kubernetes | EKS with Fargate | 20-40 hours |
| Jenkins on EC2 | GitHub Actions | 10-15 hours |
| Self-hosted monitoring (Prometheus/Grafana) | CloudWatch | 10-20 hours |
| Self-hosted auth (Keycloak) | Cognito | 5-10 hours |
| Self-hosted search (Elasticsearch) | OpenSearch Service | 10-20 hours |

**Rule of thumb**: If a managed service costs less per month than the engineering hours to self-manage it, use the managed service. At startup salaries ($150-250K/year = $75-125/hour), even $500/month services are cheaper than 7 hours of engineering time.
