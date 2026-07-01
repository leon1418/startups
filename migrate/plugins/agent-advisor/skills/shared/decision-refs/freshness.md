# Volatile Facts & Freshness

## Fields to verify at runtime via the awsknowledge MCP
- AgentCore session cap (currently "8h, extending")
- AgentCore compute cap (2 vCPU / 8 GB)
- AgentCore / Lambda MicroVMs region availability
- Lambda MicroVMs launch TPS (5, not adjustable)
- FedRAMP certification status for AgentCore and Lambda MicroVMs
- Any Bedrock model price (defer to migration-to-aws pricing cache; never hardcode here)

## Procedure
1. Identify the volatile facts to check: for the main skill, the `volatile_facts` entries
   (`verify_via_mcp: true`) from the winning runtime's profile JSON; for **add-capabilities**
   (which has no winning runtime profile), the "Hard limits" facts in the relevant service card
   (agentcore.md) instead.
2. Attempt an awsknowledge MCP lookup for each.
3. On success (the MCP call returned a value THIS run), use the fresh value and list the field as
   verified.
4. On failure OR if you did not call the MCP at all (unavailable, skipped), use the cached
   `value` and list the field as fallen-back.

**Anti-fabrication rule (do not skip):** a field may appear in the "verified via MCP" list ONLY
if you actually made an MCP call this run and observed its result. If you did not call the MCP
for a field — for any reason — it goes in the cached/fell-back list. Never claim verification you
did not perform. If the MCP was not called at all, the verified list is empty and every field is
cached.

## Freshness footer template (append to every recommendation doc)
Choose the wording that matches what actually happened:
- If some fields were MCP-verified this run:
  > _Generated <DATE>. Facts verified via AWS Knowledge MCP: <list verified>. Cached values used
  > for: <list cached>. Limits and pricing change — verify against AWS docs before committing._
- If the MCP was not called / unavailable:
  > _Generated <DATE>. AWS Knowledge MCP not called this run; all facts are cached values —
  > verify against AWS docs before committing._
