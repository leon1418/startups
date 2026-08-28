# Knowledge Auto-Update

A pipeline that keeps a skill's knowledge files current. It re-verifies every registered
fact against its own source page, scans vendor announcements for changes that affect the
skill, judges what each change means, and turns every verdict into something a human can
review: a draft PR for mechanical edits, or a review brief (an RFC issue) when a
recommendation reverses. Nothing merges without a human; nothing reversed is even drafted
without a maintainer's decision.

The full proposal, architecture, evidence, and limits live in
[`../docs/kb-autoupdate-review.md`](../docs/kb-autoupdate-review.md). This README covers
running and operating the code.

## How a run works

```
recheck.py ──────────────┐                        agree → timestamp refreshed
  (every registered fact)│                        anything else → a human, with a second opinion
                         │
scan.py ─────▶ judge.py ─┼─▶ apply.py ─▶ draft PR            (mechanical change)
  (6 sources)            │             └▶ review brief (RFC)  (reversal / unclear)
                         │
decisions.py ────────────┤   executes maintainer decisions ticked on briefs → draft PR
dashboard_issue.py ──────┘   rewrites the dashboard issue; ticked boxes feed the next run
```

Models are consulted at exactly nine points, each a narrow question with a forced JSON
schema and a code check before the answer can have any effect (verbatim evidence quotes,
before-text presence, magnitude guards). The nine prompts are in the source files below and
printed verbatim in the proposal's appendix.

## Deployments

**GitHub Actions (primary).** The workflow in
[`workflow/kb-autoupdate.yml`](workflow/kb-autoupdate.yml)
(installed as `.github/workflows/` on the fork's default branch) runs daily at 09:00 UTC
and on manual dispatch:

- Inference: Amazon Bedrock via GitHub→AWS OIDC federation. The role
  (`kb-autoupdate-gha`) allows `bedrock:InvokeModel` on Anthropic models and nothing else;
  no long-lived cloud secret exists.
- State: one JSON file on the `kb-state` branch (fact/source registries, seen sets, pins),
  committed back after every run. `runs/<runId>/` on the same branch is the run archive
  that `decisions.py` reads.
- Targets: draft PRs and review briefs open on the upstream repo (a fine-grained PAT in the
  `KB_GITHUB_TOKEN` secret, Issues + Pull requests only); branches stay on the fork; the
  dashboard issue stays on the fork.
- Judged content: the work tree is reset to `upstream/main` at the start of every run, so
  reads, edits, and the PR base all see the same current files.

Operate it with `gh workflow run kb-autoupdate.yml` or the Actions tab.

**AWS (alternative).** `infra/kb-autoupdate.yaml` deploys the same scripts as a Step
Functions state machine with one Lambda behind every state, plus DynamoDB state, an S3
evidence archive, an EventBridge schedule, and SNS failure alerts. `sfn_handler.py` is the
Lambda dispatcher; `serve.py`/`report.py` are a hosted operator console
(`infra/kb-autoupdate-console.yaml`). Same code, different transport and storage.

## Running locally

Every stage is a plain script. With AWS credentials that allow `bedrock:InvokeModel`:

```bash
uv run recheck.py --out results-recheck.json
uv run scan.py    --out results-scan.json
uv run judge.py   --hit "<substring of a scan hit title>"
uv run apply.py   --judge results-judge-*.json --repo <worktree>   # dry run without --commit
```

Without AWS credentials, point inference at any OpenAI-compatible endpoint:
`KB_INFERENCE=openai KB_INFERENCE_URL=<.../chat/completions> KB_INFERENCE_TOKEN=<key>`.

State falls back to a local `.kb-state.json` when `KB_STATE_TABLE` is unset. The fallback is
silent — operational scripts should assert `state.backend()` before writing (we once reset a
demo environment against the wrong backend: every write succeeded, into a file nothing reads).

## The safety contract

- The draft PR is the only thing that writes knowledge. It touches only locations the judge
  named, refuses any edit whose before-text is not in the file, and lists every skipped
  edit in its own body.
- A reversed recommendation is never rewritten. It becomes a review brief with the options
  and assumptions spelled out; the maintainer ticks adopt / adopt-with-changes / reject,
  and the *next* run does the typing — into a draft PR that still gets reviewed.
- `apply.py` exit codes are a contract: `0` durable action completed (PR or brief opened),
  `3` judged with nothing to apply (benign), anything else retries next run.
- "Seen" means *handled*, not fetched: a deferred hit, a crashed judge, or a dead run all
  come back automatically.
- A human `pin` on a fact outranks any observation — the pipeline reports the conflict and
  never proposes the edit.

## Configuration

| Variable | Meaning |
| --- | --- |
| `KB_CHEAP_MODEL` / `KB_STRONG_MODEL` | Extraction+triage model / judgment model |
| `KB_REGION` | Bedrock region (pinned, not inherited) |
| `KB_INFERENCE`, `KB_INFERENCE_URL`, `KB_INFERENCE_TOKEN` | Optional OpenAI-compatible inference instead of the Bedrock SDK |
| `KB_STATE_TABLE` or `KB_STATE_FILE` | DynamoDB table, or a local/branch JSON file |
| `KB_SKILLS_ROOT` | Skills tree the judge reads (defaults to this repo's own copy) |
| `KB_SKILLS_REL`, `KB_MIRROR_RELS` | Primary edit root, plus mirror roots that receive the same edits in the same PR |
| `KB_PR_REPO`, `KB_PR_BASE`, `KB_DASHBOARD_REPO` | Where PRs/briefs open; PR base branch; where the dashboard issue lives |
| `KB_MAX_JUDGE_PER_RUN` | Judge cap per run (cost guard; the rest defer and retry) |
| `KB_SCAN_WORKERS` | Triage concurrency (lower it for rate-limited endpoints) |
| `KB_RUN_ARCHIVE` or `KB_EVIDENCE_BUCKET` | Run archive: a local directory (Actions) or S3 (AWS) |

## File map

| File | What it is |
| --- | --- |
| `recheck.py` | Re-verify every fact against its source page; AWS Knowledge MCP second opinion on disagreement |
| `scan.py` | Pull all sources (`rss` + `url-watch` adapters), triage each new item against the skill's own files |
| `judge.py` | Verdict, blast radius, and — on a reversal — the review-brief content |
| `apply.py` | Apply edits to the primary root and every mirror; open the draft PR or the review brief |
| `decisions.py` | Read open briefs, execute ticked maintainer decisions |
| `dashboard_issue.py` | The dashboard as one long-lived issue; ticked boxes become next-run requests |
| `bootstrap_facts.py` | Two-pass registry bootstrap from the skill (declared facts + typed claims from prose) |
| `state.py`, `config.py` | State store (DynamoDB or file) and the editable fact/source registries |
| `_common.py` | Shared fetch/extract helpers and the forced-JSON model call (Bedrock or OpenAI-compatible) |
| `sfn_handler.py`, `infra/` | The AWS deployment: Lambda dispatcher, CloudFormation, console |
| `serve.py`, `report.py` | Operator console (hosted on AWS, or `uv run serve.py` locally) |
| `workflow/` | The GitHub Actions workflow (reviewed source; installed copy lives on the default branch) |
| `examples/` | Archived outputs of the original verification runs, kept as evidence |
| `facts.json` | The six hand-written seed facts the registry starts from |
