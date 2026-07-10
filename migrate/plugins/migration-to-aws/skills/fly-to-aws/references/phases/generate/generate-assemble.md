---
_assemble: assemble-generate
_of_phase: generate
_reads:
  - terraform sub-generation (generate-terraform.md contribution)
  - documentation + scripts sub-generation (generate-docs.md contribution)
  - HTML report sub-generation (generate-artifacts-report.md contribution)
  - common artifacts + K8s manifests (inline in generate.md)
_produces:
  - { file: terraform/, _when: "compute routes include Terraform-targetable services (fargate/lambda/batch/ecs_scheduled_task/ec2_gpu/sagemaker)" }
  - { file: k8s/, _when: "compute routes include eks" }
  - MIGRATION_GUIDE.md
  - README.md
  - SECRETS_CHECKLIST.md
  - CUTOVER_RUNBOOK.md
  - generation-warnings.json
  - { file: migration-report.html, _when: "the HTML report passed its validate gate and built successfully" }
---

# Generate — Assemble and Validate the Artifact Set

> **Assembler unit.** The Generate phase produces its Terraform (or K8s), migration
> scripts, documentation, and HTML report via the sub-files and inline steps within
> `generate.md`, then validates the complete artifact set (Step 6) and runs the
> completion handoff gate. This unit records the artifact-level contract for the
> phase: it is the single creator/owner of the generated artifact set, and the
> phase's postconditions are its completion gate. See `generate.md` § Step 6 and
> § Completion Handoff Gate for the cross-reference checks and the fail-closed checks
> this contract enforces. Conditional entries (`terraform/` vs `k8s/`,
> `migration-report.html`) are written only when their `_when` predicate holds.
