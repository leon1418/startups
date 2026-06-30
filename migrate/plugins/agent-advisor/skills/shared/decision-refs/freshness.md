# Volatile Facts & Freshness

## Fields to verify at runtime via the awsknowledge MCP (when available)
- AgentCore session cap (currently "8h, extending")
- AgentCore compute cap (2 vCPU / 8 GB)
- AgentCore / Lambda MicroVMs region availability
- Lambda MicroVMs launch TPS (5, not adjustable)
- FedRAMP certification status for AgentCore and Lambda MicroVMs
- Any Bedrock model price (defer to migration-to-aws pricing cache; never hardcode here)

## Procedure
1. Read the `volatile_facts` entries (with `verify_via_mcp: true`) from the winning
   runtime's profile JSON.
2. Attempt an awsknowledge MCP lookup for each.
3. On success, use the fresh value.
4. On failure (MCP unavailable), use the cached `value` from the profile and record that
   this field fell back.

## Freshness footer template (append to every recommendation doc)
> _Generated <DATE>. Hard-constraint facts verified via AWS Knowledge MCP: <list succeeded>.
> Fell back to cached values for: <list fallbacks>. Limits and pricing change — verify
> against AWS docs before committing._
