# Knowledge Auto-Update — POC

A working implementation of [`../docs/kb-autoupdate-design.md`](../docs/kb-autoupdate-design.md),
run end to end against live sources and Amazon Bedrock: re-verify every fact against its own
source page, scan the AWS What's New feed, judge what changed, edit the files, open a draft PR,
and refresh the dashboard.

`infra/kb-autoupdate.yaml` **is deployed** to account `767582656617` / `us-east-1` as stack
`kb-autoupdate`, with the weekly schedule **DISABLED** until a real GitHub token replaces the
placeholder. See §8 for what was verified inside the deployed environment.

The pipeline **does not open real pull requests in this POC.** `apply.py` supports
`--push --draft-pr`, and the production flow uses draft PRs, but every run here stopped at a
local commit on an isolated worktree.

Run 2026-08-10/11. Account `767582656617`, `us-east-1`. Cheap model
`global.anthropic.claude-haiku-4-5`, strong model `global.anthropic.claude-sonnet-5`.

---

## Quick Reference

|                   |                                                                                                           |
| ----------------- | --------------------------------------------------------------------------------------------------------- |
| Run it            | `uv run recheck.py` · `uv run scan.py` · `uv run judge.py --hit "runtime instances"` · `uv run report.py` |
| Apply + PR        | `uv run apply.py --judge results-judge-*.json --repo <worktree> --commit --push --draft-pr`               |
| The demo artifact | `dashboard.html` — self-contained, opens from disk, real data                                             |
| Needs             | AWS credentials with `bedrock:InvokeModel`. State falls back to a local file with no AWS at all.          |
| Deployed          | stack `kb-autoupdate` in `767582656617`/`us-east-1`, schedule **DISABLED** — see §8                       |
| Run it on AWS     | `aws codebuild start-build --project-name kb-autoupdate` (needs the real token first)                     |

| File                                         | What it is                                                                                          |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `facts.json`                                 | 6 hand-written fact records — batch 1 of the design's migration, and the schema pilot               |
| `recheck.py`                                 | Monitor 1: re-fetch each fact's source, re-extract the field, compare                               |
| `scan.py`                                    | Monitor 2: live AWS What's New feed, filtered by the 27 existing reference files                    |
| `judge.py`                                   | Verdict + blast radius for one announcement, in two calls                                           |
| `apply.py`                                   | Applies a judge result to a repo and opens the draft PR                                             |
| `state.py`                                   | `last_seen` per source and queued dashboard requests — DynamoDB, or a local file with no AWS        |
| `dashboard_issue.py`                         | The dashboard as a long-lived GitHub issue, and the tick → next-run request loop                    |
| `report.py`                                  | Renders everything into `dashboard.html`                                                            |
| `infra/kb-autoupdate.yaml`                   | CloudFormation for the weekly deployment                                                            |
| `examples/results-*.json`                    | Actual output of the runs described below (moved out of the run path — a live run must start clean) |
| `examples/results-recheck-run1-unitbug.json` | Kept deliberately — the evidence for finding 1.1                                                    |

### The full weekly flow

```
recheck.py ─┐
scan.py ────┼─▶ judge.py ─▶ apply.py ─▶ draft PR      (review happens here)
            └─▶ dashboard_issue.py                    (what a PR list cannot show)
                    ▲ ticked boxes ──▶ state.py ──▶ next run
```

Every step above has been run for real; see §6 for what the earlier draft of this README had
not yet exercised.

---

## 1. Recheck — PASSED, with one real defect found

6 facts, 3 consecutive runs. **All 6 `agree` in all 3 runs; verdicts identical across runs.**

The acceptance case is the whole point of separating the two monitors:

|                                      |                                                 |
| ------------------------------------ | ----------------------------------------------- |
| `agentcore.session_cap`, stored `8h` | Quotas page still says `8 hrs` → **`agree`** ✅ |

That is the correct answer _in the same week AgentCore gained a 14-day option_. The 14-day
figure belongs to a different compute option, and surfacing it here as a conflict would have
been wrong. Had recheck been driven by a search query instead of a URL, the blog would have come
back at rank 1 and the verdict would have been a false `changed` — which is why the design
switched recheck to URL re-extraction.

Semantic equality held: `900 seconds (15 minutes)` matched the stored `15m`; `8 hrs` matched `8h`.

### 1.1 The defect: unit conversion was inconsistent on the same page

Run 1 reported `fargate.per_vcpu_hour` as **changed**, observing `0.000011244 per vCPU second`
against our stored `0.04048`. Those are the same rate — the page quotes per-second, our value is
per-hour, and `0.000011244 × 3600 = 0.0404784`. On the _same page_ in the _same run_, the model
converted correctly for `arm64` and not for `x86`.

**The near miss matters more than the false positive.** `fargate.per_vcpu_hour_arm64` has
`appears_in` = 1 entry, so under design §6.1 it is eligible for automatic editing. Had the
conversion failed there instead, a price wrong by 3600× would have been written into
`aws-infra-pricing.json` and auto-PR'd. **The single-location rule did not protect against this
class of error** — only the model happening to convert correctly did.

Two fixes, both kept:

1. The prompt now states the stored unit and requires the answer _in that unit_, with the
   conversion factors named.
2. A mechanical **magnitude guard** in code: if observed and stored differ by ≥10×, the verdict
   is forced to `needs_human` no matter what the model said. A real price or limit change is
   almost never an order of magnitude; a unit slip almost always is. This does not trust the
   model to have converted correctly.

After both, 6/6 `agree`.

## 2. Announcement scan — PASSED on detection, and it located the design's blind spot

Live feed, 100 items (its cap), 2026-07-29 → 08-10. The filter list was built from the files
themselves, nothing hand-maintained.

```
100 announcements in  →  12 kept  →  88 dropped
```

The acceptance item was found:

> **AgentCore runtime instances are now generally available** → `agentcore.md`,
> `lambda-microvms.md`, `poc-shapes.md`, `design-ref-agentic-to-agentcore.md`

`lambda-microvms.md` was **not** on the list I had assembled by hand, and it is correct —
`lambda-microvms.md:17` reads "Session cap: 8h — same as AgentCore; NOT longer", which the launch
inverts.

### 2.1 The filter cannot see derived judgments

It did **not** name `temporal.md` or `ecs.md` — the two files whose conclusions actually flip.
Neither file is _about_ AgentCore: `temporal.md:56` rules AgentCore out as a Temporal Worker host
because of the 8h cap, and `ecs.md:13` claims GPU and >8h as ECS's advantages over it. A one-line
file description cannot expose that dependency.

This is a limit, not a bug — the filter's job is triage plus rough localization, and full blast
radius is the judge's (design §6, which already chose "agent searches at judge time" for exactly
this reason). But **the design doc's §12 acceptance criterion asked the wrong stage for it** and
should be corrected.

### 2.2 Precision, and a word collision

Of the 12 kept, my own reading is that ~7 are genuinely actionable (AgentCore runtime instances;
AgentCore in GovCloud; Bedrock 80% price cut on GPT-5.6; GPT-5.6 1M context on Bedrock; Bedrock
Web Search for OpenAI models; ECS fractional GPU on G6f; Lambda SQS provisioned-mode limits) and
~5 are marginal (Lambda network bandwidth, Aurora Serverless scaling, DynamoDB vector search,
Lambda Java on AL2023, AgentCore temporal policies).

One is a clean false positive of a kind worth designing against:

> **"Announcing temporal policies and rate limiting in Amazon Bedrock AgentCore"** → named
> `temporal.md`. "Temporal policies" here means _time-based_ policies; `temporal.md` is about
> Temporal.io, the workflow engine. A pure word collision.

At 12% kept, a reviewer looks at roughly 1–3 announcement PRs per week — the design's estimate
held.

## 3. Judge — PASSED, and it recovered what the filter missed

Two calls: what does it mean, then how far does it reach.

| Criterion (design §12)                        | Result                               |
| --------------------------------------------- | ------------------------------------ |
| verdict `schema_change`, not `value_change`   | ✅ `schema_change`                   |
| ≥6 affected locations                         | ✅ **13**                            |
| `temporal.md` flagged as a flipped conclusion | ✅ `temporal.md:56`, `kind: flipped` |
| each rewrite carries before / after / why     | ✅ all 13                            |

It stated the crucial distinction unprompted:

> **still true** — "The 8h session cap remains correct for the default serverless microVM-based
> AgentCore runtime path."

That single sentence is the difference between a correct PR and one that rewrites `8h` → `14d`.

It also found `agentcore.json:8` — the scoring rule that excludes AgentCore whenever
`session_duration = over_8hr`, with the reason string "AgentCore has an 8hr session cap". That
rule is now wrong, and it is the highest-impact location in the set because it silently steers
every long-session recommendation. My manual analysis had found 8 locations; the judge found 13.

And it rejected one of the filter's guesses: `poc-shapes.md`, listed under
`false_positive_files`.

### 3.1 The most serious finding: a faithful rewrite attached to unchanged behaviour

For `runtimes/agentcore.json` the judge proposed this, and it is the trap:

```json
{
  "field": "session_duration",
  "value": "over_8hr",
  "reason": "AgentCore's default microVM runtime has an 8hr session cap; use EC2-backed
             runtime instances (capacity providers) for sessions up to 14 days"
}
```

The prose is accurate and well written. But this entry lives in **`hard_constraints`** — it is
the rule that _eliminates AgentCore outright_ whenever `session_duration = over_8hr`. The judge
rewrote the human-readable `reason` and left the machine-readable rule untouched. After the edit,
AgentCore is still disqualified for every >8h workload, and the justification now argues against
the rule it justifies.

It also left four other behaviour-bearing entries in the same file completely alone:

| Untouched                                                                      | Why it is now wrong                              |
| ------------------------------------------------------------------------------ | ------------------------------------------------ |
| `affinities.session_duration.over_8hr: 0`                                      | scores AgentCore unusable for long sessions      |
| `hard_constraints` → `compute_tier: gpu` — "AgentCore has no GPU support"      | runtime instances offer GPU-accelerated families |
| `hard_constraints` → `compute_tier: heavy_non_gpu` — "capped at 2 vCPU / 8 GB" | no fixed ceiling on runtime instances            |
| `affinities.compute_tier.gpu: 0`, `heavy_non_gpu: 0`                           | same                                             |

**So the failure mode is not "a badly worded judgment" — it is "a well-worded judgment attached
to unchanged behaviour."** That is worse, because a reviewer skimming the diff sees fluent,
correct-sounding prose and has no signal that the logic underneath is untouched. The design's
§6.2 warning ("no CI check can catch a badly reworded judgment") named a weaker version of this
risk than the one that actually showed up.

What it implies:

- **Structured, behaviour-bearing fields need a different treatment from prose.** When a
  proposed edit touches a `.json` profile, changing only a `reason`/comment string while leaving
  the adjacent rule intact should be flagged automatically — it is nearly always incomplete.
- The human fix here needed real judgment (whether AgentCore should become two runtime profiles
  so each compute mode carries its own constraints), which is exactly the class of decision the
  design deliberately routes to a person. That part worked as intended.

### 3.2 Blast radius is not stable between runs

An earlier run returned **9** locations including `ecs.md:13` as a flipped conclusion. The final
run returned **13** including `temporal.md:56` — but _not_ `ecs.md`. Neither run is a superset of
the other; their union is more complete than either.

So a single blast-radius pass under-reports. Options: run the step more than once and union the
results, or accept that human review catches the tail. This is a real cost the design did not
account for and belongs in the doc.

## 4. Engineering findings worth carrying into the build

All four cost real debugging time and none is obvious from the AWS docs:

| Finding                                                                                                                                                                     | Consequence                                                                                     |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Claude Sonnet 5 on Bedrock **rejects `temperature`** ("deprecated for this model")                                                                                          | needs a fallback that retries without it; do not assume one inference config fits all models    |
| Hitting `maxTokens` yields a **partial tool payload** — keys silently missing                                                                                               | surfaces far away as a `KeyError`. Check `stopReason == "max_tokens"` and fail there            |
| Bedrock tool-use **wraps the payload unpredictably**: `{"answer": {…}}`, `{"parameters": {…}}`, `{"parameter": {…}}`, and once the entire object JSON-encoded into a string | without an unwrapping layer, **4 of 5 batches were lost**. See `coerce_payload` in `_common.py` |
| One call with ~190 grep candidates makes the model **abandon structured output entirely** (it answers `{"params": {}}`)                                                     | batch the blast-radius step (30 per call). Needed anyway once the tree exceeds one context      |

Two smaller ones: HTML tables must be re-emitted as pipe rows before extraction, or
`locate` instructions that address a table row have nothing to address; and `defusedxml` is used
for the feed because v2 registers third-party changelogs, not just this AWS one.

Call volume per run: 6 recheck calls, 100 filter calls, 1 + 5 judge calls. Token usage was not
instrumented — cost per run remains unmeasured.

## 5. What this POC cannot tell us

- **Whether `locate` survives a page restructure.** One snapshot cannot show that. Only weeks of
  runs will.
- **The true false-negative rate.** 88 items were dropped this week; whether any mattered is
  exactly what the dashboard's dropped list exists to surface, and one week is not a sample.
- **Steady-state cost.** Not instrumented.

**Review burden — partly measured, and the news is not good.** All 13 rewrites were reviewed by
hand. Twelve were fine. One (§3.1) was fluent prose over unchanged logic, which took reading the
surrounding file to catch — not the diff. One substantive defect per 13 edits, invisible in the
diff, is the number to carry into any decision about relaxing review.

So POC passing does **not** authorise turning on automatic PRs. The design's build order still
applies: run silently for several weeks first.

## 6. Changes this POC forces in the design doc

1. **§12 acceptance case** — the requirement that `temporal.md` and `ecs.md` be named belongs to
   the judge, not the scan. Restate it per stage. _(applied)_
2. **§6.1** — the single-location auto-edit rule is not sufficient protection on its own. Add the
   magnitude guard as a stated requirement. _(applied)_
3. **§13 open items** — blast radius is unstable across runs; structured output on Bedrock needs a
   payload-coercion layer; the blast-radius step must be batched. _(applied)_
4. **§6.2 — still open.** A proposed edit that changes only a `reason`/comment string inside a
   structured profile, while leaving the adjacent rule or score untouched, must be flagged as
   probably-incomplete rather than presented as a finished rewrite. This is the §3.1 finding and
   it is the one that most needs a mechanical check, because review demonstrably does not catch
   it from the diff alone.

## 7. What was built after the first round

The first version of this POC stopped at proposals. These now run for real:

|                            |                                                                                                                                                                                                                                         |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `state.py`                 | `last_seen` per source. Verified: a second run against the same feed triaged **3 new items instead of 100**, and the feed had genuinely advanced in between.                                                                            |
| `apply.py`                 | Applies a judge result and opens the draft PR. Verified: 13/13 locations applied to a clean worktree; a second run applied **0/13** — fully idempotent, no double edits.                                                                |
| `dashboard_issue.py`       | Verified end to end: a ticked checkbox became a queued request, and the next `scan.py` run reported `requeued: 1 item(s) a human asked to re-examine` and re-triaged exactly that item.                                                 |
| `infra/kb-autoupdate.yaml` | CloudFormation. Validated by AWS, and **Checkov: 44 passed / 0 failed / 1 documented skip** (a log bucket cannot log to itself) — the repo's own security workflow runs `checkov -d .`, so this had to be clean rather than suppressed. |
| Run timestamp              | The dashboard now shows the timestamp the _pipeline_ recorded, not its own render time. A render time would look alive even if the pipeline had been dead for a month.                                                                  |

## 8. The deployment, and what it proved

Stack `kb-autoupdate` in `767582656617` / `us-east-1`: KMS CMK, DynamoDB state table, evidence
bucket, access-log bucket, CodeBuild project, EventBridge schedule (**DISABLED**), SNS failure
topic, two IAM roles, log group. 16 resources.

A smoke build inside the deployed environment — the parts that are easy to misconfigure and
impossible to verify from a template:

```
SMOKE_PASS: secret readable (KMS+IAM)
SMOKE_PASS: dynamodb put+get (SSE-KMS)
SMOKE_PASS: s3 evidence writable
SMOKE_PASS: bedrock invoke (global.anthropic.claude-haiku-4-5)
SMOKE_PASS: uv 0.12.3
SMOKE_PASS: git 2.53.0
```

Three things deployment taught that the template alone could not:

1. **An empty Secrets Manager secret fails the build before any phase runs.** CodeBuild resolves
   `SECRETS_MANAGER` environment variables during `DOWNLOAD_SOURCE`, so a valueless secret
   produces `Secrets Manager can't find the specified secret value for staging label: AWSCURRENT`
   — an error that names nothing relevant. The template now creates a generated placeholder, so
   the build starts and fails at `gh auth login` instead, which is legible. Note that
   CloudFormation cannot _retrofit_ `GenerateSecretString` onto an existing valueless secret; it
   tries to read the current value first and fails the same way.
2. **The least-privilege IAM policy actually held.** Two smoke attempts failed because the build
   role has no `dynamodb:DeleteItem` and no `s3:DeleteObject` — permissions the pipeline never
   needs. The test was over-privileged, not the policy.
3. **Region must be pinned, not inherited.** The first state test wrote to `us-west-2` because
   that was `AWS_REGION` in the developer's shell, while the table lives in `us-east-1`. Silent,
   and it would have looked like an empty state store rather than an error. `state.py` and
   `_common.py` now read `KB_REGION` first, and the template sets it from the stack's own region.

Still required before the schedule can be enabled: replace the placeholder in
`kb-autoupdate/github-token` with a fine-grained PAT scoped to `contents:write` on the fork and
`pull_requests:write` upstream — nothing else — then run once by hand and flip `ScheduleState` to
`ENABLED`. Idle cost is roughly the KMS key plus the secret; everything else bills only per run.

## 9. Editable configuration and the bootstrap (added 2026-08-11 evening)

The Configuration tab stopped being read-only and split into the two groups the operator
actually manages, both stored in DynamoDB next to `last_seen` (seeded on first touch, live on
the next run, no deploy):

| Group               | What it is                                                                                                                                     | Where it comes from                                                  |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **Hard conditions** | the fact registry Monitor 1 re-verifies — key, current value, source URL, locate instruction, enabled flag, origin (`seed`/`bootstrap`/`user`) | seeded from `facts.json`; extended by Bootstrap or by hand in the UI |
| **Message sources** | what Monitor 2 subscribes to — `rss` runs today, `url-watch` is registerable but skipped with an explicit log line until that adapter ships    | six built-in defaults (only AWS What's New enabled)                  |

The boundary is printed on the pane itself: it edits **what the pipeline watches**; **what the
skill asserts** still changes only through a reviewed PR.

**Bootstrap, measured.** `bootstrap_facts.py` sweeps the skill's own volatile-fact declarations
(`runtimes/*.json` + decision-refs Hard-limits bullets) and asks the strong model to propose
monitorable records — key, value, a public source URL, a locate instruction, a confidence grade.
Every proposed URL is then HTTP-verified in code. Against the real tree:

```
21 declarations harvested  →  11 proposals  →  1 auto-enabled
```

Only `high` confidence + verified URL auto-enables; the other 10 arrive disabled for review.
The model correctly refused the unverifiable inputs (empty region lists, judgment phrases like
"NOT a hard block") and said so in `skipped`. The one auto-enabled proposal
(`lambda.timeout` → the Lambda quotas page) matched the hand-written record exactly.

Scan now loops over ALL enabled live sources with per-source `seen` sets, and one dead feed
cannot kill the run (per-source try/except, loudly logged).
