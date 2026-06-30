# AgentCore Runtime — Service Card

## One-liner
Serverless, agent-purpose-built runtime: managed session routing, true session
isolation, built-in identity, $0 billing during I/O wait.

## Best for
Short agent sessions with high LLM I/O wait, human-in-the-loop, multi-tenant
isolation, minimal ops, cross-session memory, high-volume session launch.

## Hard limits (verify via MCP — volatile)
- Session cap: 8h (extending — verify)
- Compute cap: 2 vCPU / 8 GB (hard)
- FedRAMP: not yet certified (verify)

## Deployment models
- **Harness** — no-code, config-driven; single agent, greenfield, OpenAI Assistants migration.
- **Framework on Runtime** — Strands / LangGraph / CrewAI / custom; multi-agent, complex orchestration.

## Six dimensions
- Identity: built-in (free), OAuth via enhanced Identity
- Observability: auto OTEL traces
- Guardrails: Bedrock Guardrails + Policy (Cedar) for high-risk actions
- Scaling: 5,000 concurrent sessions, 25 TPS launch (adjustable)
- Tool/Gateway: Gateway for external APIs / MCP
- Protocols: HTTP/1.1, WebSocket; MCP, A2A

## Tradeoffs
2 vCPU / 8 GB ceiling; no process-level suspend (Session Storage persists files only).
