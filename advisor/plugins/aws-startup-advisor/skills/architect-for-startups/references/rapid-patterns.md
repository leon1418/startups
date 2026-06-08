# Rapid Patterns

Architecture patterns optimized for time-to-ship. Organized by what you're building, not by AWS service.

---

## SaaS API Backend

**Ship in**: 1-2 days
**Cost**: $0-5/month at low traffic

```
Client → API Gateway (HTTP API) → Lambda → DynamoDB
```

- API Gateway HTTP API ($1/million requests, lower latency than REST API)
- Lambda with Python or Node.js (fastest to write, best AWS SDK support)
- DynamoDB on-demand (zero capacity planning, $0 at rest)
- Auth: API Gateway JWT authorizer with Cognito or Auth0

**When to graduate**: >1000 req/sec sustained, or need WebSockets, or functions exceed 15min.

---

## Web App with Auth

**Ship in**: 1 day
**Cost**: $0-10/month

```
S3 (static) → CloudFront → API Gateway → Lambda → DynamoDB
                                ↑
                          Cognito (auth)
```

- Frontend: React/Next.js/Vue built to static files, deployed to S3 + CloudFront
- Auth: Cognito User Pool (50K MAU free) with hosted UI
- API: Same as SaaS API pattern above
- Alternative: Amplify Hosting handles the S3 + CloudFront + CI/CD in one service

---

## AI-Powered App

**Ship in**: 1-2 days
**Cost**: $5-50/month (token-based)

```
Client → API Gateway → Lambda → Bedrock (Nova/Claude)
                              → DynamoDB (session state)
                              → S3 (knowledge base docs)
```

- Use Bedrock `InvokeModel` directly — don't build an agent unless you need tool use
- Start with Nova Micro for classification/routing, Nova Lite for generation
- Store conversation history in DynamoDB (cheap, fast)
- For RAG: Bedrock Knowledge Base with S3 source and Bedrock's managed vector store (avoid self-managed OpenSearch Serverless — minimum ~$700/month)

---

## Event-Driven Processing

**Ship in**: 1 day
**Cost**: $0-5/month

```
Source → SQS → Lambda (processor) → DynamoDB/S3 (results)
```

- SQS for reliable delivery with built-in retry and DLQ
- Lambda processes messages in batches (up to 10K messages/batch)
- Use EventBridge instead of SQS if you need content-based routing to multiple consumers

**Variants**:
- File processing: S3 event → Lambda → processed output to S3
- Webhook ingestion: API Gateway → SQS → Lambda (decouple ingestion from processing)
- Scheduled jobs: EventBridge Scheduler → Lambda

---

## Real-Time Features (WebSocket)

**Ship in**: 2-3 days
**Cost**: $5-20/month

```
Client ←WebSocket→ API Gateway (WebSocket API) → Lambda → DynamoDB (connections table)
```

- API Gateway WebSocket API manages connections
- DynamoDB stores connection IDs for broadcasting
- Lambda handles connect/disconnect/message routes
- For simpler real-time: consider Pusher or Ably (SaaS) if you don't need full control

---

## Static Marketing Site

**Ship in**: 2 hours
**Cost**: $0-1/month

```
S3 → CloudFront → Route53
```

- S3 static website hosting with CloudFront OAC
- ACM certificate (free) for HTTPS
- Route53 for DNS ($0.50/month per hosted zone)
- Or skip all this: use Amplify Hosting with `git push` deploy

---

## Data Pipeline (Analytics)

**Ship in**: 1-2 days
**Cost**: $1-20/month (query-based)

```
App → Firehose → S3 (raw) → Athena (query)
```

- Kinesis Firehose buffers and delivers to S3 (no servers)
- S3 stores raw events in Parquet format (compressed, queryable)
- Athena queries S3 directly ($5/TB scanned)
- **Don't build a data warehouse until you have >100GB of data**. Athena is enough.

---

## Multi-Tenant SaaS

**Ship in**: 3-5 days
**Cost**: $50-200/month

```
Client → CloudFront → ALB → Fargate → Aurora Serverless v2
                                     → DynamoDB (tenant metadata)
```

- Tenant isolation via row-level security in Aurora or partition key in DynamoDB
- Fargate for the application tier (containers give you more flexibility than Lambda for multi-tenant routing)
- Aurora Serverless v2 scales with demand (0.5 ACU minimum ~$43/month)
- CloudFront for global latency + caching static assets

**Simpler alternative for <10 tenants**: Lambda + DynamoDB with tenant ID in partition key. Graduate to this pattern when tenant isolation requirements increase.

---

## Mobile App Backend

**Ship in**: 1-2 days
**Cost**: $0-10/month

```
Mobile App → Cognito (auth) → API Gateway → Lambda → DynamoDB
                            → S3 (user uploads via presigned URLs)
                            → SNS (push notifications)
```

- Cognito for user sign-up/sign-in (social providers, MFA)
- Presigned S3 URLs for direct upload from mobile (skip Lambda for large files)
- SNS for push notifications (iOS/Android)
- AppSync (GraphQL) as alternative to API Gateway if you want real-time subscriptions

---

## Choosing the Right Pattern

| What You're Building | Pattern | Time to Ship |
|---|---|---|
| API for a frontend or mobile app | SaaS API Backend | 1-2 days |
| Full web app with login | Web App with Auth | 1 day |
| Chatbot or AI feature | AI-Powered App | 1-2 days |
| Background job processing | Event-Driven Processing | 1 day |
| Chat, notifications, live updates | Real-Time (WebSocket) | 2-3 days |
| Landing page or docs site | Static Marketing Site | 2 hours |
| Usage tracking or analytics | Data Pipeline | 1-2 days |
| B2B product with multiple customers | Multi-Tenant SaaS | 3-5 days |
| iOS/Android app backend | Mobile App Backend | 1-2 days |

---

## Pattern Graduation Triggers

When to move from the rapid pattern to something more robust:

| Signal | Action |
|---|---|
| Lambda hitting 15-min timeout | Move that workload to Fargate |
| >1000 concurrent Lambda executions | Consider Fargate for steady-state traffic |
| DynamoDB costs exceeding $100/month | Evaluate access patterns, consider provisioned mode |
| Need complex SQL queries | Add Aurora Serverless v2 alongside DynamoDB |
| Multiple teams deploying to same service | Split into separate services with clear APIs |
| Customers asking about SLAs | Add multi-AZ, health checks, and monitoring |
| Compliance requirements (SOC2, HIPAA) | See stage-frameworks.md Series A section |
