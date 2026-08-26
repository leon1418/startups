> Opened by the knowledge auto-update pipeline. A recommendation **reversed** — nothing was
> rewritten. The maintainer decides the position below; the pipeline then does the typing.

## 1 · What changed

[AWS Batch now supports Amazon ECS Managed Instances](https://aws.amazon.com/about-aws/whats-new/2026/08/aws-batch-on-ecs-managed-instances/)

- was — AWS Batch compute environment = Fargate (scale-to-zero, no always-on compute, no customer-managed EC2 infra)
- now — AWS Batch compute environment now splits by type: Fargate (serverless, scale-to-zero) vs ECS Managed Instances (GPU-accelerated/compute-intensive workloads on AWS-managed infrastructure with On-Demand/Spot/reserved capacity, AWS handles AMI updates/patching/lifecycle) vs standard EC2-managed (customer-managed)
- still true — Fargate remains valid and correctly described for scale-to-zero, no always-on compute, no customer-managed EC2 infra — for non-GPU, standard batch workloads.

AWS Batch now offers a third compute-environment type, ECS Managed Instances (ECS MI), alongside Fargate and standard customer-managed EC2. ECS MI targets GPU-accelerated and compute-intensive workloads, letting AWS handle AMI patching and instance lifecycle while still billing On-Demand/Spot/reserved EC2 instance rates rather than Fargate's serverless pricing. This means the old blanket guidance "AWS Batch → Fargate" is wrong specifically for GPU/large-memory/long-run jobs, which Fargate never supported well (no GPU, task-size/time limits) and were previously pushed to self-managed EC2 as the only option.

> "AWS Batch now supports Amazon ECS Managed Instances (ECS MI) as a new compute option, enabling you to run GPU-accelerated and compute-intensive batch workloads on AWS-managed infrastructure."
> "enabling you to run GPU-accelerated and compute-intensive batch workloads on AWS-managed infrastructure"

## 2 · Recommendations it affects

| location | kind | current text |
| --- | --- | --- |
| `agent-advisor/references/phases/estimate/estimate.md:98` | conclusion flips | - **batch units** (verdict from workload-classes.md: AWS Batch → Fargate compute; scheduled Lambda): |
| `agent-advisor/references/phases/estimate/estimate.md:101` | conclusion flips | - AWS Batch (long runs, GPU, large memory): Fargate vCPU-hour + GB-hour × run count/month. State |
| `agent-advisor/references/decision-refs/batch.md:5` | derived judgment | Managed batch job execution, scale-to-zero between runs, no always-on compute. |
| `agent-advisor/references/decision-refs/batch.md:28` | derived judgment | - Scaling: managed compute environment scales to zero between jobs; pay per job-second |
| `agent-advisor/references/decision-refs/workload-classes.md:11` | derived judgment | \| **W2** \| `batch` with runs > 15 min or GPU/large memory                                    \| `batch` — AWS Batch (Fargate compute env; EC2 only if GPU) \| |
| `agent-advisor/references/phases/estimate/estimate.md:73` | derived judgment | not as scale-to-zero AWS Batch. In a split run `effective_runtime == verdict`, so nothing changes. |
| `agent-advisor/references/phases/estimate/estimate.md:215` | derived judgment | right-sizing levers, NOT "Scale-to-zero runtimes" (AWS Batch is already scale-to-zero). |
| `agent-advisor/references/decision-refs/batch.md:1` | value | [AWS Batch (Fargate)]  # AWS Batch (Fargate) — Service Card |

## 3 · The decision space

- **Keep Fargate as default recommendation for standard (non-GPU, bounded-size, short-to-medium run) Batch workloads** — depends on: workload has no GPU requirement and fits Fargate vCPU/memory task limits and scale-to-zero is desired
- **Recommend ECS Managed Instances for GPU-accelerated or compute-intensive/large-memory/long-running Batch jobs that previously required customer-managed EC2** — depends on: GA maturity confirmed, GPU instance types available in target region, cost model validated against Spot/On-Demand/reserved rates vs self-managed EC2
- **Retain standard customer-managed EC2 compute environment as an option for workloads needing custom AMIs, non-standard networking, or fine-grained instance control not exposed via managedInstancesProvider** — depends on: workload requires customizations ECS MI does not yet support
- **Do not yet default GPU/heavy workloads to ECS MI; flag as emerging option pending real-world cost/patching-cadence validation** — depends on: maintainer risk tolerance for a newly-GA capability without pricing/patch-SLA track record

## 4 · Proposed position

> Update estimate.md batch-units guidance to branch by workload type: (1) standard, non-GPU Batch workloads → keep Fargate vCPU-hour + GB-hour × run count/month; (2) GPU-accelerated, large-memory, or long-running Batch workloads → use ECS Managed Instances (On-Demand/Spot/reserved EC2 instance-hour pricing for the selected instance type × run count/month), noting AWS manages AMI/patching/lifecycle; (3) workloads needing custom AMIs or infrastructure control not yet exposed by ECS MI → customer-managed EC2 compute environment, priced as before. Mark ECS MI as newly GA and flag it for re-verification in 2-3 months once real cost and patch-cadence data are available.

**Assumptions to verify before adopting:**

- ECS Managed Instances is truly GA (not preview) at the time this brief is adopted — verify current AWS documentation status.
- ECS MI pricing follows standard EC2 On-Demand/Spot/reserved instance rates with no additional managed-service premium; verify AWS Batch pricing page.
- GPU instance types needed by target workloads are available under ECS MI in the customer's operating regions — regional GPU capacity varies.
- AWS-managed AMI/patch cadence for ECS MI meets the workload's compliance and update-window requirements (unproven at GA, no long-term track record).
- Fargate's task-level vCPU/memory limits and lack of GPU support are still accurate constraints excluding it from GPU/large-memory jobs.
- managedInstancesProvider configuration (instance types, networking) is stable enough for production use and not subject to near-term breaking changes.
- Cost comparison between ECS MI and self-managed EC2 (labor savings vs instance-hour pricing) has not yet been independently validated by the maintainer.
- 'Compute-intensive' workload classification threshold (what qualifies for ECS MI vs Fargate) still needs maintainer-defined criteria, not assumed from vendor marketing language.

## Decision — tick one; the next run acts on it

- [ ] **Adopt the proposed position** — the pipeline rewrites the affected locations and opens a draft PR for review
- [ ] **Adopt with changes** — edit the "Proposed position" text above first, then tick this
- [ ] **Reject** — close this issue; nothing is rewritten

<!-- kb-autoupdate-brief:batch.compute_environment_type -->
<!-- kb-autoupdate-run:2026-08-26T094752Z:results-judge-7ece926a31.json -->
