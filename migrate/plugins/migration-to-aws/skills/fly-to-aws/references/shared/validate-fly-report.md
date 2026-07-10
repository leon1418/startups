# Validate Fly Report (Pre-Report)

> **Read-only validation.** Load at the start of `generate-artifacts-report.md` (Step 0) and before writing `migration-report.html`. Do NOT modify artifacts during this step.
>
> Fly-local checklist: fly-to-aws generates Terraform/docs directly and never produces `generation-infra.json`, a `gcp-resource-inventory.json`, or AI-workload artifacts, so the gcp `validate-artifacts.md` checks for those do not apply. This file carries only the checks that map to artifacts fly actually produces.

On any failure: emit `GATE_FAIL` per `$GCP_SHARED/handoff-gates.md`, skip report generation, tell the user which phase to re-run. **Do NOT patch JSON to pass validation.**

---

## How to run

1. Read each file below from `$MIGRATION_DIR/` using the Read tool.
2. Mark each check PASS or FAIL based on file contents (not memory).
3. If **any required** check FAILs → stop; do not write `migration-report.html`.
4. If all required checks PASS → proceed to report generation.

Optional checks: omit the corresponding report section if the condition is not met (do not halt).

---

## Required checks (halt report on FAIL)

| # | Check                | PASS when                                                                                               | On FAIL                                                                                          |
| - | -------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| 1 | Estimation exists    | `estimation-infra.json` exists                                                                          | `GATE_FAIL \| phase=generate \| field=estimation-infra.json \| reason=missing` — re-run Estimate |
| 2 | Design exists        | `aws-design.json` exists                                                                                | `GATE_FAIL \| phase=generate \| field=aws-design.json \| reason=missing` — re-run Design         |
| 3 | Preferences          | `preferences.json` exists and parses as JSON                                                            | `GATE_FAIL \| phase=generate \| field=preferences.json \| reason=missing` — re-run Clarify       |
| 4 | Recommendation path  | `estimation-infra.json` → `recommendation.path` ∈ `{migrate_optimized, migrate_phased, stay}`           | `GATE_FAIL \| phase=estimate \| field=recommendation.path \| reason=missing`                     |
| 5 | Recommendation lists | `estimation-infra.json` → `recommendation.migrate_if` and `recommendation.stay_if` are non-empty arrays | `GATE_FAIL \| phase=estimate \| field=recommendation.migrate_if \| reason=missing`               |
| 6 | Docs                 | `MIGRATION_GUIDE.md` and `README.md` exist                                                              | `GATE_FAIL \| phase=generate \| field=MIGRATION_GUIDE.md \| reason=missing`                      |

---

## Optional checks (do not halt — omit report sections)

| #  | Check               | If condition not met                                                                                                  |
| -- | ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| 7  | Specialist gates    | If `aws-design.json` has no non-empty `specialist_gates[]` → omit the specialist / deferred engagement callout        |
| 8  | GPU sunset          | If no `flags.gpu == true` in any compute group / `fly-resource-inventory.json` process group → omit GPU sunset banner |
| 9  | Agent tier          | If no `aws-design.json` → `compute.<group>.decided_by == "agent-advisor"` → omit the agent-tier dual-track callout    |
| 10 | Generation warnings | If no `generation-warnings.json` → omit that portion of Section 5 (Top Risks)                                         |

---

## Pre-write sanity (repeat immediately before HTML write)

After building report content in memory, re-read from disk and confirm these **three** checks (defense in depth — context may drift during long Generate):

1. `estimation-infra.json` → `recommendation.path_label` present OR the Step-1 fallback is documented (Section 0 uses `financial_summary.recommendation` as `path_label`).
2. `preferences.json` parses as JSON.
3. Planned HTML includes `<section id="decision-summary">` — see `generate-artifacts-report.md` HTML skeleton.

If any pre-write check fails: do not write the file; emit `GATE_FAIL` and stop.

---

## Output when all required checks pass

```
VALIDATE_OK | checks=6/6 | ready=migration-report.html
```

Then proceed to `generate-artifacts-report.md` Step 1.
