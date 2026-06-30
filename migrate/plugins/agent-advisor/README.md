# Agent Advisor

Decide **how and where to run AI agents on AWS**. Answer a few adaptive questions and get a
runtime recommendation (AgentCore Runtime, Lambda MicroVMs, ECS, EKS, or Lambda), an AgentCore
deployment model and service set, and a Bedrock model default — backed by a deterministic,
testable scoring engine.

## What it does
- Adapts its questions to your technical background (technical vs business wording).
- Scores runtimes deterministically (`scripts/scoring.py`, registry-driven).
- Produces one layered recommendation document (business summary + technical detail) with an
  architecture diagram.
- Generates lightweight scaffolding for greenfield builds.
- Hands off heavy artifact generation and migration execution to `migration-to-aws` and
  `ai-to-aws`.

## Skills
- `agent-advisor` — runtime selection for Build / Migrate.
- `add-capabilities` — add AgentCore services to agents already on AWS.

## Usage
Install from the `startups-for-aws` marketplace, then ask e.g. "which runtime for my agent?"
or invoke `/agent-advisor:add-capabilities`.

## Scope
Recommendation + justification + lightweight scaffolding. NOT full Terraform/IaC, migration
execution, or detailed per-model pricing — those hand off to the migration plugins.

## Extensibility
Each runtime is a self-contained JSON profile under `skills/shared/runtimes/`. Adding a runtime
is adding one file; the scoring engine needs no changes (it may need a new differentiating
question if the runtime competes on a new axis).
