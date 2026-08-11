# Knowledge Auto-Update — Design

How the `migration-to-aws` skills keep their externally-sourced facts current: watch external
sources on a schedule, decide whether the skills need to change, and open PRs for human review.

Scope: `migration-to-aws` only. Status: **implemented and running** — designed 2026-08-10,
built/deployed 2026-08-10..11, demoed 2026-08-12. §14 records where the implementation
evolved past this document; the POC's measured findings live in
[`../kb-autoupdate-poc/README.md`](../kb-autoupdate-poc/README.md).

---

## Quick Reference

| Decision              | Answer                                                                                                    |
| --------------------- | --------------------------------------------------------------------------------------------------------- |
| Where knowledge lives | **In the skill's own files.** No new KB directory.                                                        |
| Unit of knowledge     | One **fact** (`session_cap`), hosted in existing structured files                                         |
| Two monitors          | **Recheck** (re-fetch each fact's source URL weekly) · **Announcement scan** (read AWS What's New weekly) |
| Announcement filter   | The **27 existing reference files** — no separately-maintained topic list                                 |
| Auto-edit scope       | Recheck value changes, **only when the fact appears in exactly one place**                                |
| Announcement changes  | Agent edits both the fact **and** the derived judgments; one PR per announcement                          |
| PR grouping           | All recheck changes → 1 PR. Each announcement → its own PR. No changes → total silence.                   |
| Where it runs         | The maintainer's **own AWS account** → push to fork → PR to `awslabs/startups`                            |
| Rejected conclusions  | Recorded as a **pin** on the fact, with the evidence needed to lift it                                    |
| Management UI         | A long-lived GitHub **issue** rewritten each run (Renovate's dashboard pattern) — review stays in the PR  |

---

## 1. Why

The skills' factual knowledge is maintained by hand. Two measured symptoms:

- Of 176 non-vendored skill markdown files, **37 contain any URL** and **8 carry a date
  marker**. Most facts have no recorded source, so nothing can re-verify them.
- Every stale-fact fix in this repo's history was found by a human noticing: #161 (classic
  Bedrock Agents entered maintenance mode), #97 (AgentCore Harness reached GA), #131/#72
  (Bedrock pricing and model lifecycle).

The one existing mechanism — `tools/pricing-staleness.ts` + the weekly
`pricing-staleness.yml` job — reports staleness and stops there. Nothing closes the loop.

### 1.1 The case that shaped every rule below

AWS announced [AgentCore runtime instances](https://aws.amazon.com/blogs/aws/runtime-instances-persistent-compute-for-production-ai-agents-on-amazon-bedrock-agentcore/)
on 2026-08-06. Four days later the skills still gave wrong advice. Three properties of this
case each forced a design rule:

1. **The value did not change — the shape did.** Runtime microVMs still cap sessions at 8h
   (the [Quotas page](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
   still says `8 hrs`, and adds that it is adjustable via the `maxLifetime` parameter).
   Runtime instances are a **new, complementary** option with sessions up to 14 days. A
   value-diff would rewrite `8h` → `14d`, which is **wrong**.
2. **The damage was in the derived judgments, not the number.** One fact invalidated ~8
   locations across 2 skills and flipped at least 2 recommendations — `decision-refs/temporal.md:56`
   ("AgentCore Runtime: 8-hour max execution → OUT as Worker host") and
   `decision-refs/ecs.md:13` ("GPU and >8h are where it wins vs AgentCore" — runtime
   instances supply both).
3. **The fact was already marked volatile, and the lookup channel worked.**
   `decision-refs/freshness.md:5` lists `AgentCore session cap (currently "8h, extending")`,
   and one `awsknowledge` MCP query returns the blog at **rank 1** plus the What's New page
   (the only place "generally available" is stated) plus the Quotas page. What was missing
   was a **scheduled, unattended trigger** — today verification happens only if a human runs
   the skill, and `freshness.md:84`'s anti-fabrication rule correctly makes "did not check"
   the default.

---

## 2. Architecture

### 2.1 Deployment on AWS

Everything except the reviewed artifacts runs in the maintainer's own AWS account (§9). The
whole pipeline is **one scheduled CodeBuild job** — a weekly batch that checks out a repo, runs
a script, and pushes a branch. That is CodeBuild's native shape.

```
              ┌───────────────────────────────────────────┐
              │  EventBridge Scheduler                    │
              │  cron: weekly  ·  target: StartBuild      │
              └────────────────────┬──────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────┐
│  CodeBuild   project: kb-autoupdate    (ARM64 small, ~30 min/run)        │
│                                                                          │
│   git clone --depth 1  ─────────────────────────────────────────┐        │
│   read the ~45 fact records + 27 reference files from the tree   │        │
│                                                                 │        │
│   phase RECHECK    45 × HTTP GET ──────▶ docs / pricing pages    │        │
│                    45 × extract  ──────▶ Bedrock  (cheap model)  │        │
│   phase SCAN        1 × HTTP GET ──────▶ AWS What's New RSS      │        │
│                    58 × filter   ──────▶ Bedrock  (cheap model)  │        │
│   phase JUDGE+EDIT  agent loop   ──────▶ Bedrock  (strong model) │        │
│                     context      ──────▶ awsknowledge MCP        │        │
│                     edits files in the checkout                  │        │
│   phase PR          git push  +  gh pr create ──────────────────▶┤        │
│                                                                 │        │
└───┬──────────────┬───────────────┬──────────────┬───────────────┼────────┘
    │ read/write   │ put           │ get secret   │ logs          │
    ▼              ▼               ▼              ▼               ▼
┌─────────────┐ ┌────────────┐ ┌─────────────┐ ┌────────────┐  ┌──────────────┐
│ DynamoDB    │ │ S3         │ │ Secrets Mgr │ │ CloudWatch │  │  GitHub      │
│ last_seen   │ │ evidence/  │ │ GitHub      │ │ Logs       │  │ fork ──PR──▶ │
│ recheck log │ │ snapshots  │ │ token       │ │     │      │  │      upstream│
└─────────────┘ └────────────┘ └─────────────┘ └─────┼──────┘  │ dashboard    │
                                                     │         │ issue  §7.2  │
                                                     │         └──────────────┘
                                                     │ build FAILED
                                                     ▼
                                              ┌─────────────┐
                                              │ SNS → email │
                                              └─────────────┘
```

| Service                   | Role                                       | Why this one                                                                                                                                                         |
| ------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **EventBridge Scheduler** | weekly trigger → `StartBuild`              | Only a cron is needed. Weekly is forced by the feed's 100-item cap (§6.2).                                                                                           |
| **CodeBuild**             | runs the entire pipeline                   | Native `git`, a working tree, an 8h ceiling, and credential handling — the four things this job needs. Billed per build-minute, so a weekly 30-min run is near-free. |
| **Bedrock**               | extraction, filtering, judgment, rewriting | In-account IAM role, so no stored API key and no approval (§9). Cheap model for the 45 extractions and 58 filter calls; strong model only for judge+edit.            |
| **DynamoDB**              | `last_seen` per source; recheck history    | Tiny key-value state rewritten weekly. On-demand, effectively free.                                                                                                  |
| **S3**                    | raw page snapshots as evidence             | For the maintainer's own audit of what the extractor actually saw. PRs carry the quotes inline (§7.1), so reviewers never need S3 access.                            |
| **Secrets Manager**       | the fine-grained GitHub token              | The only long-lived secret. Its per-secret monthly fee is likely the largest fixed line item.                                                                        |
| **CloudWatch Logs**       | one log stream per run                     | Whole-run debuggability in one place.                                                                                                                                |
| **SNS**                   | notify on build failure                    | A silent week is a valid outcome (§7.1), so a _failed_ run must be distinguishable from a _quiet_ one.                                                               |

Dominant cost terms are Bedrock tokens and the Secrets Manager per-secret fee; the rest rounds
to zero at this cadence. Order of magnitude is a few dollars a month — worth confirming against
current pricing before building, not taken from this document.

**One job, not a state machine.** Splitting into Lambdas behind Step Functions would buy
per-step retries and observability, but the judge+edit phase needs the same working tree the
earlier phases read, so every split forces that tree to be serialized through S3 or EFS and
rebuilt. At one run per week, throughput is irrelevant and a single log stream is easier to
debug. Same reasoning as dropping per-fact intervals (§4) and the service-name pre-filter
(§6.1): remove optimizations that buy nothing here.

**Why not Lambda:** the 15-minute hard timeout is a poor fit for a multi-turn agent loop, and a
git working tree in ephemeral storage adds friction for no gain.

**Why not AgentCore Runtime**, despite being the runtime these skills recommend: its shape is
session-based invocation from an application, whereas this is a scheduled batch job whose core
operations are checkout, file edits, and push. It would still need a separate invoker, and it
adds a management fee. Reconsider if the pipeline ever becomes interactive — for example if a
reviewer wants to ask it to revise a PR.

### 2.2 The weekly run, step by step

```
┌─ 1  TRIGGER ─────────────────────────────────────────────────────────┐
│  EventBridge, weekly. The period cannot be lengthened: the What's New │
│  feed holds only 100 items and runs ~58/week, so a monthly poll would │
│  silently drop entries.                                              │
└────────────────────────────────┬─────────────────────────────────────┘
                                 ▼
┌─ 2  READ CURRENT STATE ──────────────────────────────────────────────┐
│  read-only checkout of awslabs/startups                              │
│    · ~45 fact records, inside the skills' own files        → §3       │
│    · 27 reference files (decision-refs/, design-refs/)     → §5.1     │
│  AWS state store                                                     │
│    · last_seen, per source                                 → §5.3     │
└──────────────────┬───────────────────────────┬───────────────────────┘
                   ▼                           ▼
┌─ 3a  RECHECK               §4 ─┐  ┌─ 3b  ANNOUNCEMENT SCAN      §5 ─┐
│  for each fact:                │  │  adapter(last_seen) → new items  │
│    GET recheck.url             │  │  filter: "does this affect any   │
│    extract via `locate`        │  │  of the 27 files?" → name them   │
│    compare against value       │  │                                  │
│      agree   → bump            │  │  ~58 items in → 0–3 hits out     │
│                observed_at     │  └───────────────┬──────────────────┘
│      changed → 4a              │                  ▼
│      failed  → human queue     │  ┌─ 4b  JUDGE + EDIT        §6.2 ──┐
└───────────────┬────────────────┘  │  edit the fact + its provenance  │
                ▼                   │  rewrite derived judgments —     │
┌─ 4a  AUTO-EDIT          §6.1 ─┐   │    each with before/after/why    │
│  appears_in == 1 → edit it     │   │  context ◀─ awsknowledge MCP    │
│  appears_in >= 2 → human       │   │            (investigation only)  │
└───────────────┬────────────────┘  └───────────────┬──────────────────┘
                ▼                                   ▼
┌─ 5  PR AUTHOR                                              §7.1 ─────┐
│  all recheck changes → 1 PR    ·    each announcement → its own PR    │
│  nothing changed → no PR, no issue, no commit                         │
│  push a branch to the fork, open the PR against awslabs/startups → §9 │
└────────────────────────────────┬─────────────────────────────────────┘
                                 ▼
┌─ 6  HUMAN REVIEW ────────────────────────────────────────────────────┐
│  merge                                                               │
│  conclusion is wrong → the PR instead records a pin + lift_when → §8  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.3 What lives where

| Location                              | Holds                                                                                       | Why there                                                                                                       |
| ------------------------------------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **git** — `awslabs/startups`          | the ~45 fact records (inside the skills' own files) and the 27 reference files              | they must be reviewed in the same diff as the skill changes they justify                                        |
| **AWS** — maintainer's own account    | schedule, fetching, filtering, judging, PR authoring; `last_seen` state; evidence snapshots | run-state is rewritten weekly even when nothing changed — weekly "bumped last_seen" commits would be pure noise |
| **GitHub fork** — `leon1418/startups` | the branch each PR is opened from                                                           | keeps upstream free of secrets, workflow files, and approvals                                                   |

Knowledge **storage** and pipeline **execution** were always separate questions: storage went
back to git, execution stays in AWS.

### 2.4 The same week, concretely

```
Week of 2026-08-10

RECHECK — 45 facts
  agentcore.session_cap    GET Quotas page → "8 hrs"   == "8h"
                           → agree; observed_at = 2026-08-10
                             ↑ correct outcome. NOT a conflict, even though
                               the world did change this week — see §4
  bedrock.sonnet.input     GET pricing page → $2.50    != "$3.00"
                           → appears_in == 1 → auto-edit
  43 others                → agree
  ⇒ 1 PR  "recheck: 1 value changed, 44 confirmed"

ANNOUNCEMENT SCAN — 58 items
  57 items                 → affect none of the 27 files → dropped (ids recorded)
  "AgentCore runtime instances are now generally available"
                           → affects decision-refs/{agentcore,temporal,ecs}.md
                           → JUDGE: session_cap becomes a map
                                      (microvm 8h | runtime_instances 14d)
                                    temporal.md:56  conclusion flips
                                    ecs.md:13       stated advantage gone
  ⇒ 1 PR  fact edit + 3 rewrites, each with before/after/why

Total: 2 PRs.
```

The two monitors reach opposite-looking conclusions about the same fact in the same week, and
both are right — recheck confirms 8h still holds for microVMs, while the scan discovers a new
dimension. That separation is the point of running two monitors instead of one.

---

## 3. Where knowledge lives

**No new KB directory.** The skills already contain a structured fact store —
`references/runtimes/agentcore.json`:

```json
"volatile_facts": [
  { "key": "session_cap", "value": "8h", "verify_via_mcp": true },
  { "key": "compute_cap", "value": "2vCPU/8GB", "verify_via_mcp": true },
  { "key": "fedramp", "value": "in_progress (WIP — verify current status)", "verify_via_mcp": true },
  { "key": "regions", "value": [], "verify_via_mcp": true }
]
```

It is already read at runtime: `freshness.md:74-77` takes the `verify_via_mcp: true` entries
from the winning runtime's profile JSON, and `design.md:308` writes the result into the design
output. So this store is on the execution path — extending it adds no dead weight and creates
no second copy to keep in sync.

What gets added is the provenance the records lack:

```json
{
  "key": "session_cap",
  "value": { "microvm": "8h (adjustable via maxLifetime)", "runtime_instances": "14d" },
  "verify_via_mcp": true,
  "sources": [{
    "url": "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html",
    "quote": "Maximum session duration | 8 hrs | Yes, through the maxLifetime API parameter"
  }],
  "observed_at": "2026-08-10",
  "recheck": {
    "url": "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html",
    "locate": "table 'Lifetime session lifecycle parameters', row 'Maximum session duration', column 'Timeout'"
  },
  "appears_in": [
    "decision-refs/agentcore.md#hard-limits",
    "decision-refs/temporal.md:56",
    "decision-refs/ecs.md:13"
  ],
  "pin": null
}
```

Notes on specific fields:

- **`locate` is natural language, not a CSS/XPath selector.** Extraction is done by a model;
  a prose description survives page restructuring that would break a selector.
- **`appears_in` replaces anchors in the markdown.** No skill file needs an inserted marker.
  It also holds **derived** locations (`temporal.md:56`), which is where the impact analysis
  caches what it learned.
- **`value` may be a map.** Forced by §1.1: a scalar cannot express "8h for microVMs, 14d for
  runtime instances".

This also upgrades an existing weakness: `freshness.md`'s anti-fabrication rule currently
relies on the model policing itself ("a field may appear in the verified list ONLY if you
actually made an MCP call"). With `observed_at` present, the freshness footer reads a
timestamp instead.

### 3.1 Formats are not unified

Four shapes exist today:

| Host                                                               | Format                            | Existing timestamp                | Granularity |
| ------------------------------------------------------------------ | --------------------------------- | --------------------------------- | ----------- |
| `runtimes/*.json`                                                  | `volatile_facts[]`                | none                              | per fact    |
| `shared/pricing/aws-infra-pricing.json`                            | nested JSON + `_meta`             | `last_updated` + `staleness_days` | per file    |
| `pricing-cache.md` + 2 others                                      | markdown tables (465 rows in one) | `**Last updated:**` line          | per file    |
| `ai-model-lifecycle.md`, `bedrock-quotas.md`, `decision-refs/*.md` | markdown tables / bullets         | none                              | none        |

Unifying them is rejected: markdown tables are easier for a model to read than JSON (the
markdown _is_ the prompt), and migrating 465 pricing rows into JSON is pure cost.

**Dispatch by how the fact changes, not by its current format:**

| Change pattern                   | Examples                                               | Granularity needed            | Action                                                                   |
| -------------------------------- | ------------------------------------------------------ | ----------------------------- | ------------------------------------------------------------------------ |
| Whole table refreshed together   | pricing caches                                         | file-level timestamp suffices | **leave as is** — an adapter reads the existing `Last updated` / `_meta` |
| Each entry changes independently | `volatile_facts`, model lifecycle rows, service status | per fact                      | use `volatile_facts`; add a structured host where none exists            |

The test is practical: a pricing refresh re-fetches the whole table, so 465 rows sharing one
date loses nothing. "AgentCore session cap" and "FedRAMP status" move independently, so a
shared file date would lie — refreshing one would claim all were refreshed.

The adapter pattern already exists: `pricing-staleness.ts` reads both JSON (`_meta.last_updated`)
and markdown (`**Last updated:**` line) through two code paths normalized to one type.

**Writing does not need a machine-safe format**, because every write goes through a PR a human
reviews. The agent makes a targeted edit the way a person would. Only _reading_ needs to be
systematic, and adapters already solve that.

The provenance model we want also already exists, hand-written, in
`aws-infra-pricing.json`'s `_meta.last_verification`:

> `"2026-07-19 spot-check against published pricing pages: Fargate Linux/x86 us-east-1
> ($0.000011244/vCPU-s = $0.04048/hr; ...) matches, and Heroku dyno flat rates match devcenter;
> no rate changes applied this refresh."`

What changed, against which source, with what conclusion. The work is to structure it and let
a machine write it — not to invent it.

---

## 4. Monitor 1 — Recheck

Every week, re-fetch each fact's `recheck.url` and re-extract the field. Compare values.

**Why URL re-extraction and not semantic search.** Using a search query per fact conflates the
two monitors and produces false conflicts:

| Recheck via search query                                        | Recheck via URL re-extraction                              |
| --------------------------------------------------------------- | ---------------------------------------------------------- |
| "AgentCore max session duration" → rank 1 is the blog (14 days) | Re-fetch Quotas page → `Maximum session duration \| 8 hrs` |
| Reconciler sees 14d vs our 8h → **conflict**                    | Reconciler sees 8h vs 8h → **agree**, bump `observed_at`   |
| ❌ Wrong — our 8h is still correct for microVMs                 | ✅ Right — recheck answers "does what we said still hold?" |

Runtime instances is a discovery, and belongs to the announcement scan. Each monitor keeps
one job.

**No per-fact interval — recheck everything weekly.** ~45 fetches plus ~45 extractions costs
cents per week. An interval is a cost optimization with no cost to optimize, and removing it
deletes a schema field, a scheduling mechanism, and a class of "was due but never ran" bugs.
Every fact's `observed_at` becomes at most 7 days old, which is what makes the freshness
footer worth reading.

**Failures are explicit.** Cannot fetch, or cannot locate the field → mark the fact
`recheck_failed`, leave the value alone, route to a human. Never treat a failed extraction as
"unchanged" — a silent failure impersonating a confirmation is the worst available outcome.

**The `awsknowledge` MCP is an investigation tool, not a monitor.** Its two uses: giving the
judgment step full context after the scan finds something (one query returned the blog, the
What's New entry, and the Quotas page — mutually complementary and partly contradictory,
which is exactly the input judgment needs), and relocating a fact whose `recheck.url` died.

---

## 5. Monitor 2 — Announcement scan

Every week, read the AWS What's New RSS feed (~58 items) and decide which items matter.

### 5.1 The filter is the 27 existing reference files

```
agent-advisor/references/decision-refs/   agentcore ecs eks lambda lambda-microvms batch
                                          temporal model-selection cost-levers poc-shapes
                                          workload-classes managed-alternatives freshness
gcp-to-aws/references/design-refs/        compute storage database networking messaging
                                          security ai ai-openai-to-bedrock ai-gemini-to-bedrock
                                          ai-anthropic-to-bedrock design-ref-agentic-to-agentcore
                                          design-ref-harness fast-path index
```

Ask of each item: **"does this affect the content of any of these files?"** and require the
answer to name the files.

- **Zero maintenance, never stale.** Add a reference file and the filter widens; delete one
  and it narrows. It is the skills' capability boundary, not a copy of it.
- **The filter output is the localization.** An item that names `decision-refs/temporal.md`
  has already told the judgment step where to look — the impact analysis starts with a target
  list instead of a search.
- `design-refs/index.md` maps GCP services to their AWS targets (Fargate, Lambda, EKS, RDS,
  Aurora, DynamoDB, ElastiCache, Aurora DSQL, S3, EFS, VPC …). Useful prompt material for the
  filter: it states which AWS services the skills actually recommend.

**No cheap pre-filter on service names.** It would cut 58 items to under 10 for free, but the
saving is cents, and it has a blind spot: a launch under an unfamiliar service name matches no
known string and gets dropped — which is precisely the item most worth catching. Same reasoning
as dropping per-fact intervals.

### 5.2 Sources: AWS only in v1

Measured availability:

| Source                                                                           | Result                                                                                   |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| AWS What's New RSS                                                               | ✅ real feed, ~58 items/week                                                             |
| OpenAI news RSS                                                                  | ✅ works                                                                                 |
| OpenAI **API changelog** (model retirement, new models — the part we care about) | ❌ HTML only                                                                             |
| Anthropic `rss.xml`                                                              | ❌ 404; release notes are HTML only                                                      |
| Google Gemini changelog                                                          | ❌ HTML only                                                                             |
| Temporal docs changelog                                                          | ❌ HTML only (GitHub releases has Atom, but that is server versions, not feature status) |

Only AWS has a usable feed. v1 subscribes to it alone:

- Everything else needs a different mechanism (fetch an HTML list page and remember the last
  item seen).
- Only 4 of the 27 topics are non-AWS.
- The non-AWS facts are largely covered by recheck already: model retirement dates and context
  windows are the 22 `ai-model-lifecycle.md` records, each with a source URL re-fetched weekly.

What only a scan can find is _something we have no record of at all_ — most likely on the AWS
side, and exactly the runtime-instances shape.

**Weekly polling is required, not chosen:** the What's New feed is capped at 100 items and runs
~58/week, so a monthly poll would silently drop entries.

### 5.3 Source adapter contract

Every adapter returns the same normalized item, so nothing downstream knows the source format:

```
item = { id, title, body, url, published_at | null }
```

```
adapter(previous_state) -> (new_items, next_state)
```

Three deliberate flexibilities, each protecting a v2 source type:

| Choice                                               | Reason                                                                                                                                                                                                 |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| State is **opaque per-source data**, not a timestamp | RSS can select by `pubDate`; HTML changelogs often have no dates and can only remember "the first item I saw last time". Standardizing on timestamps would force the second source type to compromise. |
| `published_at` may be null; **dedupe by `id` only**  | Same reason. Anything downstream depending on dates excludes HTML sources.                                                                                                                             |
| Item segmentation is internal to the adapter         | RSS splits `<item>`, HTML splits list rows, an API splits an array. That difference must not leak.                                                                                                     |

The source list is configuration, not code:

```yaml
sources:
  - id: aws-whats-new
    adapter: rss
    url: https://aws.amazon.com/about-aws/whats-new/recent/feed/
    poll: weekly
  # v2 appends here; only the adapter name changes
  # - id: openai-api-changelog
  #   adapter: html-list
  #   url: https://platform.openai.com/docs/changelog
  #   locate: "changelog entry list, one date-headed entry each"
```

No plugin registry, no dynamic loading — with one source those abstractions do nothing. Adding
a source means one config entry plus one adapter file.

State lives in AWS, not in git: it must be written every week even when nothing changed, and a
weekly "only bumped last_seen" commit is pure noise. Consistent with the general rule —
**reviewable artifacts go in git, machine run-state and evidence stay in AWS.**

---

## 6. What the agent changes

### 6.1 Recheck found a different value → edit automatically, if it appears in one place

Example: the Bedrock pricing page now says `$2.50` per million input tokens where
`pricing-cache.md` says `$3.00`. The agent edits the line, updates `observed_at`, opens a PR.

Not doing this would leave the most frequent category of change entirely manual, which removes
most of the system's value.

**The condition:**

```
appears_in has exactly 1 entry  → edit automatically
appears_in has 2+ entries       → route to a human
```

Grounded in a real hazard found in this repo: `aws-infra-pricing.json` (11 infrastructure
services) and `pricing-cache.md` (infrastructure **and** AI) are two independently maintained
copies of the same infrastructure rates — the JSON's own `staleness_note` admits the split
("AI-model rates (not used for heroku->aws) may have drifted"). Editing one copy of a
duplicated rate manufactures an inconsistency.

The rule tightens itself: as `appears_in` gets more complete, the auto-editable set shrinks
toward what is genuinely safe rather than growing.

**It is not sufficient on its own, and a second guard is required.** The POC
([`../kb-autoupdate-poc/README.md`](../kb-autoupdate-poc/README.md) §1.1) hit a case where the
Fargate pricing page quotes a per-_second_ rate against our per-_hour_ stored value; the model
converted correctly for arm64 and not for x86 in the same run. The arm64 fact has
`appears_in` = 1, so it was eligible for automatic editing — a price wrong by 3600× would have
been auto-PR'd, and the single-location rule would not have stopped it. So:

> **Magnitude guard** — if the observed and stored numbers differ by ≥10×, force the verdict to
> "needs a human" regardless of what the model concluded. A genuine price or limit change is
> almost never an order of magnitude; a unit slip almost always is.

This is mechanical and does not trust the model to have converted correctly. Stating the stored
unit in the prompt fixed the observed case, but a prompt fix is not a guard.

### 6.2 The scan found something new → the agent edits the facts _and_ the judgments

Two kinds of edit, with very different verification profiles:

**Facts** — easy to verify; the reviewer opens the source link and compares.

```
session_cap: "8h"  →  { microvm: "8h (adjustable via maxLifetime)", runtime_instances: "14d" }
                       plus source URL, quote, observed_at
```

**Judgments derived from the fact** — hard to verify, and **CI cannot check them at all**.
These edits change prompt text; a badly reworded rubric silently alters every downstream
generation, and the existing regression harness (`fixtures/*/check_expected_*.py`) requires a
real skill run to produce a run directory.

```
temporal.md:56    "AgentCore Runtime: 8-hour max execution → OUT as Worker host"
ecs.md:13         "GPU and >8h are where it wins vs AgentCore"
clarify-ai.md:488 "Very long: AgentCore Runtime required (8-hour max session)…"
```

**The agent edits both, in one PR.**

- _Not facts-only:_ the value of this system is concentrated in the second kind — 1 fact → ~8
  locations → 2 flipped recommendations. Leaving that to a human from scratch automates only
  the easy half.
- _Not two PRs:_ the two kinds are causally linked — the fact change **is** the reason the
  judgment changes, and that link is what makes the PR reviewable. Split them and a merged
  facts-PR with an unmerged judgments-PR leaves the skill self-contradictory, while the
  judgments-PR loses its evidence.

**Required, because review is the only protection:** every reworded judgment must carry
before / after / **why**.

```
temporal.md:56
  before: AgentCore Runtime: 8-hour max execution → OUT as Worker host
  after:  AgentCore Runtime: runtime instances support 14-day sessions → viable as Worker host;
          microVMs (8h) remain unsuitable for resident polling
  why:    runtime instances GA announcement + 14-day session limit  <url> "<quote>"
```

Without the `why` column the reviewer can only rubber-stamp.

**A stronger failure mode than "badly worded" — and it needs a mechanical check.** The POC
([`../kb-autoupdate-poc/README.md`](../kb-autoupdate-poc/README.md) §3.1) produced a rewrite of
`runtimes/agentcore.json` that was accurate, fluent, and functionally empty: it updated the
`reason` string on a `hard_constraints` entry and left the rule itself intact, so AgentCore was
still eliminated for every >8h workload while the new justification argued the opposite. Four
other behaviour-bearing entries in the same file — the `over_8hr` and `gpu` affinity scores, two
further hard constraints — were untouched.

A reviewer skimming that diff sees correct prose and gets no signal that the logic underneath did
not move. So:

> **Required check** — when a proposed edit touches a structured profile and changes only a
> `reason` / comment / description string while the adjacent rule, score or constraint is
> unchanged, mark it **probably incomplete** rather than presenting it as a finished rewrite.

This is the one place where review demonstrably cannot substitute for a mechanical check, because
the defect is invisible in the diff. Measured rate: one such defect per 13 proposed edits.

---

## 7. Human interface

### 7.1 PR organization

| Source of change      | Grouping            | Reason                                                                                                                                                                                |
| --------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Recheck value changes | **All into one PR** | Mutually unrelated (a Claude price and a Fargate price have nothing to do with each other) and each is narrow. Grouping just reduces PR count; review cost adds up linearly.          |
| Each announcement     | **One PR each**     | An announcement carries an internal causal chain, and that chain is the review evidence. Two unrelated announcements in one PR cannot be judged — or partially accepted — separately. |

Expected weekly volume: 0–1 recheck PR + 0–3 announcement PRs = **1–4 PRs/week**. A heavy week
means a lot genuinely happened; the volume should not be artificially suppressed.

**A week with no changes produces no PR, no issue, and no commit.** Total silence.

No topic-based grouping: recheck changes have no intra-topic relationship, and announcements
are already one-per-PR. It would add a rule to maintain and buy no review savings.

### 7.2 Dashboard

**Reviewing changes stays on GitHub.** The PR diff, inline comments, and merge/close are already
the right tool, and re-implementing them elsewhere would split the reviewer's attention. The
dashboard is for what a PR list cannot show.

What GitHub does not give us:

| Need                                | Why it matters                                                                                                                                                                         |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Health of all ~45 facts at a glance | The records are scattered across `runtimes/*.json` and other files. "Which facts have not been successfully verified in a month?" currently requires reading every file.               |
| **The dropped announcements**       | The scan silently discards ~57 of 58 items per run. Reviewing that list is **the only way to detect a false negative** — and §12 notes the POC cannot measure the false-negative rate. |
| Pins and their `lift_when`          | §8 records them per fact; nothing shows all of them together, or how long each has been held.                                                                                          |
| Run history                         | Did last week's run succeed, and what did it do? Otherwise this lives only in CloudWatch.                                                                                              |
| A few actions                       | Re-examine a dropped item, lift a pin, skip the next run.                                                                                                                              |

**The dashboard is a long-lived GitHub issue, rewritten on every run** — the pattern Renovate
uses for its Dependency Dashboard.

|                         |                                                                                                                    |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Zero hosting, zero auth | GitHub permissions are the permissions. No API Gateway, no Cognito, no frontend.                                   |
| Same place as the PRs   | No context switch between "what changed" and "what is the pipeline's state".                                       |
| No commits              | An issue is GitHub metadata, not repository content — consistent with §2.3's rule that run-state stays out of git. |
| Actions via checkboxes  | Ticking a box is a request the next run reads and acts on.                                                         |
| Proven                  | Renovate runs this pattern across millions of repositories.                                                        |

Layout:

```markdown
# Knowledge Auto-Update — Dashboard

Last run 2026-08-10 14:23 UTC · build #47 ✅ · next 2026-08-17

## Open PRs

- #201 recheck: 1 value changed, 44 confirmed
- #202 AgentCore runtime instances GA → session_cap + 3 derived judgments

## Facts — 45

| fresh (≤7d) | recheck failed | pinned | never verified |
| 42 | 2 | 1 | 0 |

<details><summary>⚠️ Recheck failed — 2</summary>

| fact | last ok | error |
| bedrock.nova-micro.output | 2026-07-27 (14d) | locate failed — table structure changed |
| lambda.max_timeout | 2026-06-30 (41d) | 404 — page moved |

</details>

<details><summary>📌 Pinned — 1</summary>

| fact | ours | source says | since | lift when |
| temporal.serverless_workers.status | Public Preview | Available | 2026-07 | a GA announcement post |

</details>

<details><summary>All 45 facts</summary> … </details>

## This run's scan

58 items in · 1 hit · 57 dropped

<details><summary>Dropped — 57 (check here if something was missed)</summary>

- Amazon GameLift Streams … Shader Caching
- Amazon Timestream for InfluxDB … backup and restore
- …

</details>

## Actions — tick a box; applied on the next run

- [ ] Re-examine dropped item `whats-new-2026-08-04-ec2-status-checks`
- [ ] Open a PR lifting the pin on `temporal.serverless_workers.status`
- [ ] Skip the next run
```

Notes on specific choices:

- **The dropped list is the most important section**, not a footnote. Everything else on the
  dashboard reports what the pipeline did; only this one reveals what it _failed_ to do.
  Dropped item ids are already recorded to avoid re-judging them (§5.3) — surfacing them costs
  nothing and closes the only blind spot the design has.
- **Checkboxes are requests, not commands.** They take effect on the next weekly run. Needing
  a run _now_ is rare and is served by `aws codebuild start-build` — not worth an API and an
  auth layer.
- **Lifting a pin produces a PR, not a direct edit**, because pins live in git (§8) and every
  change to the knowledge goes through review.
- **The issue lives in the fork, not upstream.** It is operational state for whoever runs the
  pipeline, not something upstream reviewers need — and §9 keeps upstream untouched. The cost
  is that PRs and the dashboard sit in different repositories; revisit if upstream maintainers
  ask for the fact-health view.

**Deferred: a real dashboard.** A generated static site on S3 + CloudFront would add trend
lines — how often each fact actually changes, false-positive rate over time, drift in
extraction reliability. That is worth building once there is history to plot, and the signal to
build it is concrete: when tuning decisions (which facts need attention, whether the filter is
too tight) start needing more than one run's snapshot. A markdown issue cannot show a time
series; it also does not need to on day one.

**Explicitly not building:** review UI, real-time updates, an auth system, or write access to
the knowledge from outside a PR.

---

## 8. Rejected conclusions are pinned on the fact

Without this, a rejected PR is re-proposed every week until the maintainer stops reading PRs.

The precedent is already in the repo, hand-written at `decision-refs/freshness.md:58`: the
Serverless Workers docs label read "Available" while the feature was pre-release, and a human
held the correct line, recording that **a docs label alone is not GA evidence**.

Rejection is not "close the PR". It is "have the PR record the adjudication, then merge it":

```
session_status:
  value: "Public Preview"
  pin:
    at: 2026-07
    reason: "docs page showed Available while the feature was pre-release;
             a docs label alone is not GA evidence"
    lift_when: "a GA announcement post"        # what evidence would overturn this
  last_observed: { value: "Available", at: 2026-07-xx }   # record the disagreement explicitly
```

- **No repeat next week.** The agent sees the pin and its `lift_when`, so it re-raises only
  when _that specific evidence_ appears — not every time it sees the same docs label.
- **The rejection becomes knowledge, not a hidden suppression rule.** Three months later,
  "why do we say pre-release when the docs say Available" is answered in the file, with a date
  and a reason. Under a PR-based mechanism that answer is buried in a closed PR's comments.
- **`lift_when` makes "what counts as evidence" explicit** — the exact judgment that let a
  human beat the docs label, written down so the machine stops treating the label as proof.

---

## 9. Where it runs

Two findings decide this:

- `.github/workflows/` uses **no secrets at all** — adding an LLM credential would be a first
  for this repo.
- `origin` is `leon1418/startups` (a fork); `upstream` is `awslabs/startups` (a public AWS repo).

**It runs in the maintainer's own AWS account**, pushes to the fork, and opens PRs against
`awslabs/startups`. **Nothing is added to the upstream repository** — no secret, no workflow
file, no approval. This is already how the maintainer contributes.

|                    |                                                                                                          |
| ------------------ | -------------------------------------------------------------------------------------------------------- |
| Credentials        | Bedrock via an in-account IAM role, no approval. Putting an API key in a public AWS repo would need one. |
| Upstream untouched | Not one line added there. A workflow file living only in the fork would conflict with upstream forever.  |
| State has a home   | The "last item seen" state and evidence snapshots were already assigned to AWS.                          |

**Token, corrected.** An earlier draft of this section asked for "a fine-grained token with
`contents: write` on the fork and `pull_requests: write` on upstream". That is **not possible**:
a fine-grained PAT is "limited to access resources owned by a single user or organization", and
the fork is owned by a user while upstream is owned by the `awslabs` org. Three workable shapes:

|                                                                                                                                               | Blast radius                               | Keeps the fork flow |
| --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ------------------- |
| **One fine-grained PAT scoped to `awslabs/startups`** (`contents` + `pull_requests` + `issues`: write) — push the branch to upstream directly | **one repository**                         | no                  |
| Two fine-grained PATs, one per owner, selected per command                                                                                    | two repositories, two secrets              | yes                 |
| A classic PAT with `repo`                                                                                                                     | **every repository the account can reach** | yes                 |

The classic PAT is ruled out for an unattended weekly job: it is the widest possible grant, and
the job needs exactly one repository. Prefer the first shape unless bot branches and the
dashboard issue on the official repository are unacceptable, in which case take the second.

Note this only works because the maintainer is an active member of the `awslabs` org — a
fine-grained PAT explicitly cannot "contribute to public repos where the user is not a member",
which is classic-token-only territory.

Note the split: knowledge **storage** returned to git (it must be reviewed alongside the
skills), while **execution** stays in AWS. Those were always two separate questions.

---

## 10. Migration

Measured surface for facts that change independently:

| Batch | Content                                                                                     | Count   | Work                           |
| ----- | ------------------------------------------------------------------------------------------- | ------- | ------------------------------ |
| —     | `runtimes/*.json` `volatile_facts` (agentcore 4, lambda_microvms 5, ecs 1, eks 1, lambda 1) | **12**  | already structured; add fields |
| —     | `ai-model-lifecycle.md` 22 rows + `bedrock-quotas.md` 11 rows                               | **33**  | needs a new structured host    |
|       | **total**                                                                                   | **~45** |                                |

The `decision-refs` "Hard limits" bullets (agentcore 3, lambda-microvms 5, lambda 1) are **not
additional facts** — they are a second statement of the `runtimes/*.json` facts
(`agentcore.json` says `session_cap: 8h`; `agentcore.md:15` says "Session cap: 8h", maintained
separately). They become `appears_in` entries, which records an existing duplication.

Migration is one-time, not lazy: recheck needs the record to exist first, and quiet changes
(prices, quotas — no announcement) are only ever caught by recheck. Lazy conversion would never
establish records for exactly the category that most needs monitoring. At 45 facts, 12 of which
only need extra fields, one-time is affordable.

Three batches:

1. **Pilot — `runtimes/agentcore.json`, 4 facts.** Stress the schema against the real
   AgentCore case, which already forced two requirements: `value` must be able to become a map,
   and `appears_in` must be able to point at derived judgments like `temporal.md:56`. One small
   PR, so a schema mistake is cheap to fix.
2. The remaining 8 `runtimes/*.json` facts — same shape, mechanical.
3. `ai-model-lifecycle` + `bedrock-quotas`, 33 facts — the only batch with real design work
   (choosing the new host's shape).

**Run recheck against batch 1 before migrating batches 2–3.** Otherwise 45 records sit and rot
and we have only changed the format of the original problem; letting the first batch be
exercised for a few weeks is what exposes schema defects.

**Not migrated:** the service-status assertions embedded in `gcp-to-aws` design-ref prose
(#161's "classic Bedrock Agents entered maintenance mode" shape). They have no enumerable
structure, and they are event-driven — the announcement scan covers them, and a record can be
created when one actually surfaces. The dividing line is the same one used throughout:

```
enumerable + needs periodic re-verification (recheck)   → migrate up front   ~45
embedded in prose + event-driven (announcement scan)    → lazy, on discovery
```

---

## 11. Build order

1. Fact schema + batch 1 migration (4 facts), human-reviewed.
2. Recheck: weekly fetch, extract, compare, bump `observed_at`. **No writes to GitHub** — run
   silent for a few weeks and measure how often it wrongly flags a change.
3. Recheck auto-PR for single-location value changes (§6.1).
4. Batches 2–3 migration.
5. Announcement scan + the 27-file filter, opening PRs.
6. Adapter for a second source type (OpenAI API changelog, HTML list).

## 12. Acceptance case

Replay the 2026-08-06 AgentCore runtime-instances announcement. Requirements are **per stage** —
an earlier draft of this section asked the scan for the blast radius, which is the judge's job
(see the POC's §2.1):

| Stage   | Required                                                                                                                                                                                                                                                  |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Recheck | `session_cap` reports **agree** — the Quotas page still says 8 hrs. Not a conflict, even though the world changed this week.                                                                                                                              |
| Scan    | The item is kept, and names at least `decision-refs/agentcore.md`. It is **not** expected to reach `temporal.md` or `ecs.md`: neither file is _about_ AgentCore, and a one-line file description cannot expose that dependency.                           |
| Judge   | verdict `schema_change`, **not** `value_change`; ≥6 affected locations; the derived files the scan could not see are recovered; `decision-refs/temporal.md` presented as a **flipped conclusion**, not a wrong number; before/after/why on every rewrite. |
| PR      | One PR carrying the fact edit and the rewrites together.                                                                                                                                                                                                  |

A PR that rewrites `8h` → `14d` means the design failed.

Second case: replay #131's Bedrock price change and require one aggregated recheck PR.

**Status: all three stages passed against live sources on 2026-08-10** — recheck `agree` on all
6 piloted facts across 3 identical runs, the scan keeping 12 of 100 items with the acceptance
item among them, and the judge returning `schema_change` with 13 affected locations and 3 flipped
conclusions. Details and the defects found in
[`../kb-autoupdate-poc/README.md`](../kb-autoupdate-poc/README.md).

## 13. Open items

1. **Structured host shape for batch 3** — `ai-model-lifecycle.md` has 22 independently
   changing rows; whether that becomes one JSON file, per-row records, or something else is
   undecided.
2. **Fact identity across shape changes** — when `session_cap` splits into two dimensions, does
   the key survive or retire in favour of two new keys? Affects `appears_in` and history.
3. **Where the pipeline's own code lives** — the fork, a separate repo, or upstream.
4. **The two disjoint pricing stores** (`aws-infra-pricing.json` vs `pricing-cache.md`) are a
   pre-existing drift source, out of scope here but worth fixing separately.
5. **Blast radius is unstable between runs** (POC §3.1). Two runs of the same input returned 9
   and 13 locations, and neither was a superset of the other — one caught `ecs.md`, the other
   caught `temporal.md:56`. A single pass under-reports. Decide between repeating the step and
   taking the union, or accepting that review catches the tail. Repeating costs tokens; accepting
   means shipping known-incomplete PRs.
6. **Structured output on Bedrock needs a payload-coercion layer** (POC §4). Tool-use wraps the
   answer unpredictably — `{"answer": …}`, `{"parameters": …}`, `{"parameter": …}`, and once the
   whole object JSON-encoded into a string. Without unwrapping, 4 of 5 batches were silently
   lost. Also: a `maxTokens` cut-off yields a _partial_ payload with keys missing rather than an
   error, so `stopReason` must be checked.
7. **The blast-radius step must be batched.** One call with ~190 candidate locations made the
   model abandon structured output entirely. 30 per call worked. This is needed regardless once
   the tree exceeds one context.

## 14. How the implementation evolved past this document

Written after build, deploy and demo (2026-08-10..12). Where the sections above disagree with
what runs today, this section wins.

### 14.1 The four-layer naming

The review-facing architecture names four layers; this document's sections map onto them:

| Layer | Name                         | This document's sections                     | Today's components                                                                                                               |
| ----- | ---------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1     | **Ingestion**                | §4 recheck extraction, §5.3 adapter contract | per-fact URL + locate extraction; `rss` adapter live, `url-watch` registered/planned                                             |
| 2     | **Registry & Evidence**      | §3, §8 pins                                  | fact registry + source registry in DynamoDB (`config:*`), evidence archive in S3, `last_seen`                                    |
| 3     | **Orchestration & Judgment** | §2.2 flow, §6.2 judge                        | EventBridge cron + CodeBuild sequencing + all caps/guards + the judge and its verdict routing                                    |
| 4     | **Actions**                  | §6.1/§7 PR, §7.2 dashboard                   | `apply.py` → draft PR; `dashboard_issue.py` → issue; SNS → failure email. Each action is an independent consumer of judge output |

Layer 2 is deliberately NOT a knowledge mirror — it registers claims about the knowledge
(value, source, observed_at, pin, appears_in) while the skill files stay the single
authoritative copy (§3's argument, unchanged).

### 14.2 Config became editable (supersedes parts of §7.2)

The operator console (serve.py, three tabs: Execute / Results / Configuration) grew past the
"dashboard is a GitHub issue" design. The Configuration tab now EDITS two groups, stored in
DynamoDB next to `last_seen`, live on the next run with no deploy:

- **Hard conditions** — the fact registry Monitor 1 re-verifies. Seeded from `facts.json` on
  first touch; a **Bootstrap** action sweeps the skill (`volatile_facts` + Hard-limits bullets)
  and proposes new records with model-suggested source URLs (HTTP-verified; only
  high-confidence+verified proposals arrive enabled). Measured: 21 declarations → 11 proposals.
- **Message sources** — what Monitor 2 subscribes to. Six registered (AWS What's New live;
  AWS Blog / OpenAI News optional rss; OpenAI changelog / Anthropic notes / Temporal changelog
  as `url-watch`, skipped with an explicit log line until that adapter ships).

The boundary that §7.2 used to express as "read-only by design" is now finer-grained and
stated on the page itself: the pane edits **what the pipeline watches** (operations data);
**what the skill asserts** still changes only through a reviewed PR.

The GitHub dashboard issue (#7) remains as the PR-adjacent surface; the console is the
operator surface.

### 14.3 Deviations worth knowing during review

- §12's acceptance criteria were restated per stage after the POC showed the scan cannot see
  derived-judgment files (the judge recovers them).
- §6.1's single-location rule gained a mechanical **magnitude guard** (≥10x → human) after a
  near-miss with a per-second vs per-hour price.
- Auto-PR for `value_change` remains OFF (build-order step: run silently first); every PR the
  system has opened so far is a judge-driven draft.
