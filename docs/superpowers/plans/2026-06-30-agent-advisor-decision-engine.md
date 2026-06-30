# Agent Advisor — Decision Engine Implementation Plan (Plan 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the registry-driven, deterministic runtime-scoring engine for the agent-advisor plugin — a pure Python module that takes a Clarify answer set and returns a runtime recommendation, deployment model, AgentCore services, a Bedrock model default, and warnings.

**Architecture:** A generic scoring engine (`scoring.py`) loads one self-contained JSON profile per runtime from `skills/shared/runtimes/*.json`. Each profile declares its hard constraints, per-dimension affinity scores, deployment models, and volatile facts. The engine applies hard-constraint elimination first, then sums affinity points across answered dimensions (missing dimension/value → a fixed neutral score), determines a verdict (single winner / co-recommend tie / no viable runtime), and assembles deployment-model, service, model, assumption, and warning outputs. Adding a runtime later = adding one JSON file; no engine edits. This is the "前期多投入换长期低扩展成本" decision from the spec.

**Tech Stack:** Python ≥3.10, stdlib only for the engine (`json`, `dataclasses`, `pathlib`, `argparse`); `jsonschema` for output validation; `pytest` for tests; `uv` for execution (mirrors `migrate/plugins/ai-to-aws/scripts`).

## Global Constraints

- Python `requires-python = ">=3.10"` (matches ai-to-aws scripts).
- Engine core (`load_profiles`, scoring, verdict) uses **stdlib only** — no boto3, no network. Determinism is the contract: same input → same output.
- All code, comments, identifiers, and messages in **English**.
- Runtime profiles are **JSON** (loaded with stdlib `json`), stored at `migrate/plugins/agent-advisor/skills/shared/runtimes/<id>.json`.
- Five runtime ids, fixed spelling: `agentcore`, `lambda_microvms`, `ecs`, `eks`, `lambda`.
- `NEUTRAL_SCORE = 2`; `TIE_THRESHOLD = 2` (a runtime within 2 points of the max co-recommends).
- Only profiles whose `status` is in the requested set score; default `statuses={"ga"}`.
- Plugin root for this plan: `migrate/plugins/agent-advisor/`. All paths below are relative to the repo root `/Volumes/workspace/startups`.
- Run every command from `migrate/plugins/agent-advisor/scripts/` via `uv run` so the pinned toolchain is used.

---

## Data Model (locked — every task depends on these names)

**Scoring dimensions** (`DIMENSIONS`, the answer keys that contribute points):
`session_duration`, `traffic_pattern`, `platform_fit`, `session_state`, `ops_preference`, `isolation`, `memory_needs`, `multi_agent`, `framework`, `existing_cluster`, `multi_cloud`, `idle_resume`, `compute_tier`, `launch_concurrency`.

**Non-scoring answer keys** (feed hard constraints or model selection only):
`compliance` (list), `model_priority`, `model_features`, `current_model`, `region`.

**New dimensions vs prototype** (added for Lambda MicroVMs differentiation, per spec §7.3):
- `idle_resume`: `process_level` | `filesystem` | `none` | `unknown`
- `compute_tier`: `light` | `heavy_non_gpu` | `gpu` | `unknown` (GPU moved here out of `traffic_pattern`)
- `launch_concurrency`: `high` | `moderate` | `low` | `unknown`

`traffic_pattern` values are now `bursty` | `steady` | `idle` | `unknown` (no `gpu`).

**Profile JSON shape:**
```json
{
  "id": "lambda_microvms",
  "display_name": "Lambda MicroVMs",
  "status": "ga",
  "launched": "2026-06-22",
  "service_card": "lambda-microvms.md",
  "hard_constraints": [
    {"field": "session_duration", "value": "over_8hr", "reason": "..."}
  ],
  "affinities": {"session_duration": {"15min_to_8hr": 5}},
  "deployment_models": [],
  "volatile_facts": [{"key": "session_cap", "value": "8h", "verify_via_mcp": true}]
}
```

**`score(input_data)` output shape** (the contract Plans 2 & 3 consume):
```json
{
  "verdict": "agentcore | lambda_microvms | ecs | eks | lambda | co_recommend | no_viable_runtime",
  "scores": {"agentcore": 0, "lambda_microvms": 0, "ecs": 0, "eks": 0, "lambda": 0},
  "eliminated": {"lambda": "Lambda has 15-minute timeout"},
  "co_recommend": ["ecs", "eks"],
  "blocking_constraints": ["agentcore: ...", "lambda: ..."],
  "deployment_model": "harness | framework_on_runtime | null",
  "agentcore_services": ["identity", "observability", "evaluations", "optimization"],
  "model_recommendation": {"model": "claude_sonnet_4_6", "reasoning": "...", "migration_from": "gpt4o", "pricing_note": "..."},
  "assumptions_used": ["session_duration defaulted to unknown"],
  "warnings": ["Lambda MicroVMs RunMicrovm is capped at 5 TPS and is not adjustable ..."]
}
```
`co_recommend` present only when verdict is `co_recommend`; `blocking_constraints` present only when verdict is `no_viable_runtime`.

---

### Task 1: uv project scaffold + registry loader

**Files:**
- Create: `migrate/plugins/agent-advisor/scripts/pyproject.toml`
- Create: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `RUNTIMES_DIR: pathlib.Path` — default profile directory (`../skills/shared/runtimes` relative to `scoring.py`).
  - `load_profiles(runtimes_dir: pathlib.Path = RUNTIMES_DIR, statuses: frozenset[str] = frozenset({"ga"})) -> list[dict]` — reads every `*.json` in `runtimes_dir`, returns the list of profile dicts whose `status` is in `statuses`, sorted by `id`. Raises `ValueError` (with the file path) if a file is not valid JSON or is missing a required key (`id`, `status`, `affinities`, `hard_constraints`).

- [ ] **Step 1: Create the uv project file**

Create `migrate/plugins/agent-advisor/scripts/pyproject.toml`:

```toml
[project]
name = "agent-advisor-scripts"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "jsonschema>=4,<5",
]

[dependency-groups]
dev = ["pytest>=8"]
```

- [ ] **Step 2: Write the failing test**

Create `migrate/plugins/agent-advisor/scripts/test_scoring.py`:

```python
import json
import pathlib

import pytest

import scoring


def _write_profile(directory, profile):
    (directory / f"{profile['id']}.json").write_text(json.dumps(profile))


def _minimal(id_, status="ga"):
    return {
        "id": id_,
        "display_name": id_,
        "status": status,
        "service_card": f"{id_}.md",
        "hard_constraints": [],
        "affinities": {},
        "deployment_models": [],
        "volatile_facts": [],
    }


def test_load_profiles_filters_by_status_and_sorts(tmp_path):
    _write_profile(tmp_path, _minimal("ecs"))
    _write_profile(tmp_path, _minimal("agentcore"))
    _write_profile(tmp_path, _minimal("preview_rt", status="preview"))

    profiles = scoring.load_profiles(tmp_path)

    assert [p["id"] for p in profiles] == ["agentcore", "ecs"]


def test_load_profiles_rejects_bad_json(tmp_path):
    (tmp_path / "broken.json").write_text("{not json")

    with pytest.raises(ValueError, match="broken.json"):
        scoring.load_profiles(tmp_path)


def test_load_profiles_rejects_missing_key(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"id": "x", "status": "ga"}))

    with pytest.raises(ValueError, match="x.json"):
        scoring.load_profiles(tmp_path)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute 'load_profiles'`.

- [ ] **Step 4: Write minimal implementation**

Create `migrate/plugins/agent-advisor/scripts/scoring.py`:

```python
"""Deterministic, registry-driven runtime-scoring engine for agent-advisor.

Pure: answers dict -> recommendation dict. No network, no AWS. Runtime
knowledge lives in JSON profiles under skills/shared/runtimes/.
"""
import json
import pathlib

RUNTIMES_DIR = pathlib.Path(__file__).parent.parent / "skills" / "shared" / "runtimes"

_REQUIRED_PROFILE_KEYS = ("id", "status", "affinities", "hard_constraints")


def load_profiles(runtimes_dir=RUNTIMES_DIR, statuses=frozenset({"ga"})):
    """Load runtime profiles whose status is in `statuses`, sorted by id."""
    profiles = []
    for path in sorted(pathlib.Path(runtimes_dir).glob("*.json")):
        try:
            profile = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON ({exc})") from exc
        missing = [k for k in _REQUIRED_PROFILE_KEYS if k not in profile]
        if missing:
            raise ValueError(f"{path}: missing required keys {missing}")
        if profile["status"] in statuses:
            profiles.append(profile)
    return sorted(profiles, key=lambda p: p["id"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/pyproject.toml \
        migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): scaffold scoring scripts + runtime profile loader"
```

---

### Task 2: Hard-constraint elimination

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: `load_profiles`, profile dicts.
- Produces: `_apply_hard_constraints(answers: dict, profiles: list[dict]) -> dict[str, str]` — returns `{runtime_id: reason}` for every profile eliminated by a hard constraint. A constraint matches when its `field` is `compliance` and its `value` is in the answer list, OR (non-list field) the answer equals `value`.

- [ ] **Step 1: Write the failing test**

Add to `test_scoring.py`:

```python
def test_hard_constraint_scalar_match():
    profiles = [
        {**_minimal("agentcore"), "hard_constraints": [
            {"field": "session_duration", "value": "over_8hr", "reason": "8hr cap"}]},
        {**_minimal("ecs"), "hard_constraints": []},
    ]
    eliminated = scoring._apply_hard_constraints(
        {"session_duration": "over_8hr"}, profiles)
    assert eliminated == {"agentcore": "8hr cap"}


def test_hard_constraint_compliance_list_match():
    profiles = [
        {**_minimal("agentcore"), "hard_constraints": [
            {"field": "compliance", "value": "fedramp", "reason": "not FedRAMP"}]},
    ]
    eliminated = scoring._apply_hard_constraints(
        {"compliance": ["soc2", "fedramp"]}, profiles)
    assert eliminated == {"agentcore": "not FedRAMP"}


def test_hard_constraint_no_match():
    profiles = [
        {**_minimal("agentcore"), "hard_constraints": [
            {"field": "session_duration", "value": "over_8hr", "reason": "8hr cap"}]},
    ]
    eliminated = scoring._apply_hard_constraints(
        {"session_duration": "15min_to_8hr", "compliance": ["none"]}, profiles)
    assert eliminated == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k hard_constraint -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute '_apply_hard_constraints'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scoring.py`:

```python
def _apply_hard_constraints(answers, profiles):
    eliminated = {}
    compliance = answers.get("compliance", ["none"])
    for profile in profiles:
        for constraint in profile.get("hard_constraints", []):
            field, trigger = constraint["field"], constraint["value"]
            if field == "compliance":
                matched = trigger in compliance
            else:
                matched = answers.get(field) == trigger
            if matched:
                eliminated[profile["id"]] = constraint["reason"]
                break
    return eliminated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k hard_constraint -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): registry-driven hard-constraint elimination"
```

---

### Task 3: Affinity scoring with neutral default

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: profile dicts, `eliminated` from Task 2.
- Produces:
  - Constants `NEUTRAL_SCORE = 2`, `DIMENSIONS` (the 14-item list from the Data Model), `DEFAULTS` (every answer key → safe default; scoring dims default to `"unknown"`, `compliance` to `["none"]`, model keys to `"unknown"`).
  - `_compute_scores(answers: dict, profiles: list[dict], eliminated: dict) -> dict[str, int]` — for each non-eliminated profile, sum over `DIMENSIONS` the value `profile["affinities"].get(dim, {}).get(answers[dim], NEUTRAL_SCORE)`. Eliminated runtimes are omitted from the returned dict.

- [ ] **Step 1: Write the failing test**

Add to `test_scoring.py`:

```python
def test_compute_scores_uses_affinity_and_neutral_default():
    profiles = [
        {**_minimal("agentcore"), "affinities": {
            "session_duration": {"15min_to_8hr": 5},
            "traffic_pattern": {"bursty": 5}}},
        {**_minimal("ecs"), "affinities": {
            "session_duration": {"15min_to_8hr": 3}}},
    ]
    answers = {"session_duration": "15min_to_8hr", "traffic_pattern": "bursty"}
    scores = scoring._compute_scores(answers, profiles, eliminated={})
    # agentcore: 5 + 5 + neutral(2)*12 remaining dims = 34
    # ecs: 3 + neutral(2) + neutral(2)*12 = 29
    assert scores["agentcore"] == 5 + 5 + scoring.NEUTRAL_SCORE * 12
    assert scores["ecs"] == 3 + scoring.NEUTRAL_SCORE * 13
    assert scores["agentcore"] > scores["ecs"]


def test_compute_scores_omits_eliminated():
    profiles = [{**_minimal("agentcore"), "affinities": {}}]
    scores = scoring._compute_scores({}, profiles, eliminated={"agentcore": "x"})
    assert scores == {}


def test_defaults_cover_all_dimensions():
    for dim in scoring.DIMENSIONS:
        assert dim in scoring.DEFAULTS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k "compute_scores or defaults_cover" -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute 'NEUTRAL_SCORE'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scoring.py` (constants near the top, function below):

```python
NEUTRAL_SCORE = 2

DIMENSIONS = [
    "session_duration", "traffic_pattern", "platform_fit", "session_state",
    "ops_preference", "isolation", "memory_needs", "multi_agent", "framework",
    "existing_cluster", "multi_cloud", "idle_resume", "compute_tier",
    "launch_concurrency",
]

DEFAULTS = {
    **{dim: "unknown" for dim in DIMENSIONS},
    "compliance": ["none"],
    "model_priority": "unknown",
    "model_features": "unknown",
    "current_model": "unknown",
    "region": "unknown",
}


def _compute_scores(answers, profiles, eliminated):
    scores = {}
    for profile in profiles:
        if profile["id"] in eliminated:
            continue
        affinities = profile.get("affinities", {})
        total = 0
        for dim in DIMENSIONS:
            value = answers.get(dim, "unknown")
            total += affinities.get(dim, {}).get(value, NEUTRAL_SCORE)
        scores[profile["id"]] = total
    return scores
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k "compute_scores or defaults_cover" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): affinity scoring with neutral default"
```

---

### Task 4: Verdict determination

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: `scores` from Task 3, `eliminated` from Task 2.
- Produces:
  - Constant `TIE_THRESHOLD = 2`.
  - `_determine_verdict(scores: dict, eliminated: dict) -> tuple[str, list[str]]` — returns `(verdict, co_recommend_list)`. If no non-eliminated runtime: `("no_viable_runtime", [])`. If more than one runtime within `TIE_THRESHOLD` of the max: `("co_recommend", sorted(top_ids))`. Otherwise `(winner_id, [])`.

- [ ] **Step 1: Write the failing test**

Add to `test_scoring.py`:

```python
def test_verdict_single_winner():
    verdict, co = scoring._determine_verdict(
        {"agentcore": 30, "ecs": 20}, eliminated={})
    assert verdict == "agentcore"
    assert co == []


def test_verdict_co_recommend_within_threshold():
    verdict, co = scoring._determine_verdict(
        {"ecs": 30, "eks": 29, "lambda": 10}, eliminated={})
    assert verdict == "co_recommend"
    assert co == ["ecs", "eks"]


def test_verdict_no_viable_runtime():
    verdict, co = scoring._determine_verdict(
        {}, eliminated={"agentcore": "x", "lambda": "y"})
    assert verdict == "no_viable_runtime"
    assert co == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k verdict -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute '_determine_verdict'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scoring.py`:

```python
TIE_THRESHOLD = 2


def _determine_verdict(scores, eliminated):
    active = {r: s for r, s in scores.items() if r not in eliminated}
    if not active:
        return "no_viable_runtime", []
    max_score = max(active.values())
    top = sorted(r for r, s in active.items() if s >= max_score - TIE_THRESHOLD)
    if len(top) > 1:
        return "co_recommend", top
    return top[0], []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k verdict -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): verdict determination with tie co-recommend"
```

---

### Task 5: Deployment-model selection (profile-gated)

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: `answers`, the winning runtime id, profile dicts.
- Produces: `_select_deployment_model(answers: dict, verdict: str, profiles: list[dict]) -> str | None` — returns `None` unless the winning profile declares `deployment_models` containing both `"harness"` and `"framework_on_runtime"`. When it does (AgentCore): returns `"framework_on_runtime"` if `multi_agent == "yes"` or `framework in {"langgraph","crewai","custom"}`; otherwise `"harness"`.

- [ ] **Step 1: Write the failing test**

Add to `test_scoring.py`:

```python
def _agentcore_with_models():
    return {**_minimal("agentcore"),
            "deployment_models": ["harness", "framework_on_runtime"]}


def test_deployment_model_none_when_runtime_has_no_models():
    profiles = [{**_minimal("ecs"), "deployment_models": []}]
    assert scoring._select_deployment_model({}, "ecs", profiles) is None


def test_deployment_model_framework_for_multi_agent():
    profiles = [_agentcore_with_models()]
    dm = scoring._select_deployment_model(
        {"multi_agent": "yes", "framework": "none"}, "agentcore", profiles)
    assert dm == "framework_on_runtime"


def test_deployment_model_harness_for_single_agent_no_framework():
    profiles = [_agentcore_with_models()]
    dm = scoring._select_deployment_model(
        {"multi_agent": "no", "framework": "none"}, "agentcore", profiles)
    assert dm == "harness"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k deployment_model -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute '_select_deployment_model'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scoring.py`:

```python
def _select_deployment_model(answers, verdict, profiles):
    profile = next((p for p in profiles if p["id"] == verdict), None)
    if profile is None:
        return None
    models = profile.get("deployment_models", [])
    if "harness" not in models or "framework_on_runtime" not in models:
        return None
    if answers.get("multi_agent") == "yes":
        return "framework_on_runtime"
    if answers.get("framework") in ("langgraph", "crewai", "custom"):
        return "framework_on_runtime"
    return "harness"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k deployment_model -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): profile-gated deployment-model selection"
```

---

### Task 6: AgentCore service selection

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: `answers`.
- Produces:
  - Constant `AGENTCORE_ALWAYS_SERVICES = ["identity", "observability", "evaluations", "optimization"]`.
  - `_select_agentcore_services(answers: dict) -> list[str]` — starts from the always-on list, then appends (without duplicates, order preserved): `memory` if `session_state in {"hitl","stateful"}` or `memory_needs == "cross_session"`; `policy` if `isolation == "required"`; `gateway` if `multi_agent == "yes"`.

- [ ] **Step 1: Write the failing test**

Add to `test_scoring.py`:

```python
def test_services_always_on_baseline():
    assert scoring._select_agentcore_services({}) == [
        "identity", "observability", "evaluations", "optimization"]


def test_services_add_memory_and_policy_and_gateway():
    services = scoring._select_agentcore_services({
        "memory_needs": "cross_session", "isolation": "required",
        "multi_agent": "yes"})
    assert services[:4] == [
        "identity", "observability", "evaluations", "optimization"]
    assert services[4:] == ["memory", "policy", "gateway"]


def test_services_no_duplicate_memory():
    services = scoring._select_agentcore_services({
        "session_state": "hitl", "memory_needs": "cross_session"})
    assert services.count("memory") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k services -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute '_select_agentcore_services'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scoring.py`:

```python
AGENTCORE_ALWAYS_SERVICES = ["identity", "observability", "evaluations", "optimization"]


def _select_agentcore_services(answers):
    services = list(AGENTCORE_ALWAYS_SERVICES)

    def add(name):
        if name not in services:
            services.append(name)

    if answers.get("session_state") in ("hitl", "stateful"):
        add("memory")
    if answers.get("memory_needs") == "cross_session":
        add("memory")
    if answers.get("isolation") == "required":
        add("policy")
    if answers.get("multi_agent") == "yes":
        add("gateway")
    return services
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k services -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): AgentCore service selection from signals"
```

---

### Task 7: Bedrock model default selection (minimal)

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: `answers` (`model_priority`, `model_features`, `current_model`, `_entry_point`).
- Produces: `_select_model(answers: dict) -> dict` — a forward default only (spec §6.3: no pricing tables). Base from `model_priority` (`quality`/`balanced`/`unknown` → `claude_sonnet_4_6`; `speed`/`cost` → `claude_haiku_4_5`). `model_features == "extended_thinking"` overrides model to `claude_sonnet_4_6_thinking`. For `_entry_point == "migrate"` with a known `current_model`, adds `migration_from` and a coarse `pricing_note` ("see migration-to-aws for detailed pricing") — **no dollar figures**.

- [ ] **Step 1: Write the failing test**

Add to `test_scoring.py`:

```python
def test_model_default_balanced():
    rec = scoring._select_model({"model_priority": "balanced"})
    assert rec["model"] == "claude_sonnet_4_6"
    assert "pricing_note" not in rec


def test_model_speed_picks_haiku():
    rec = scoring._select_model({"model_priority": "speed"})
    assert rec["model"] == "claude_haiku_4_5"


def test_model_extended_thinking_override():
    rec = scoring._select_model(
        {"model_priority": "quality", "model_features": "extended_thinking"})
    assert rec["model"] == "claude_sonnet_4_6_thinking"


def test_model_migrate_adds_family_note_without_pricing():
    rec = scoring._select_model(
        {"_entry_point": "migrate", "current_model": "gpt4o",
         "model_priority": "unknown"})
    assert rec["migration_from"] == "gpt4o"
    assert "migration-to-aws" in rec["pricing_note"]
    assert "$" not in rec["pricing_note"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k model -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute '_select_model'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scoring.py`:

```python
_MODEL_PRIORITY = {
    "quality": ("claude_sonnet_4_6", "Best quality for agentic workloads"),
    "balanced": ("claude_sonnet_4_6", "Balanced quality, speed, and cost"),
    "speed": ("claude_haiku_4_5", "Fastest response time"),
    "cost": ("claude_haiku_4_5", "Lowest cost per token"),
    "unknown": ("claude_sonnet_4_6", "Default for agentic workloads"),
}

# Coarse family mapping only — detailed pricing lives in migration-to-aws.
_MIGRATE_FAMILY = {
    "gpt4": "claude_sonnet_4_6", "gpt4o": "claude_sonnet_4_6",
    "gemini_flash": "nova_lite", "gemini_pro": "claude_sonnet_4_6",
    "claude": "claude_sonnet_4_6", "other": "claude_sonnet_4_6",
}


def _select_model(answers):
    model, reasoning = _MODEL_PRIORITY.get(
        answers.get("model_priority", "unknown"), _MODEL_PRIORITY["unknown"])
    rec = {"model": model, "reasoning": reasoning}
    if answers.get("model_features") == "extended_thinking":
        rec["model"] = "claude_sonnet_4_6_thinking"
        rec["reasoning"] = "Extended thinking for deep reasoning"
    if answers.get("_entry_point") == "migrate":
        current = answers.get("current_model", "unknown")
        if current in _MIGRATE_FAMILY:
            rec["migration_from"] = current
            if answers.get("model_features", "unknown") in ("unknown", "none"):
                rec["model"] = _MIGRATE_FAMILY[current]
            rec["pricing_note"] = (
                "Coarse family mapping only — see migration-to-aws for "
                "detailed model pricing and TCO comparison.")
    return rec
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k model -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): minimal Bedrock model default (no pricing)"
```

---

### Task 8: Assumptions + warnings (Lambda MicroVMs 5 TPS guardrail)

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: `raw_answers` (the caller's answers before defaults), `answers` (post-defaults), `verdict`.
- Produces:
  - `_collect_assumptions(raw_answers: dict) -> list[str]` — one entry per scoring dimension that was absent or `"unknown"` in `raw_answers`: `"<dim> defaulted to unknown"`.
  - `_collect_warnings(answers: dict, verdict: str) -> list[str]` — if `verdict == "lambda_microvms"` and `answers.get("launch_concurrency") == "high"`, returns the 5 TPS guardrail warning (spec §7.3/§11); otherwise `[]`.

- [ ] **Step 1: Write the failing test**

Add to `test_scoring.py`:

```python
def test_assumptions_lists_unknown_dimensions():
    assumptions = scoring._collect_assumptions({"session_duration": "under_15min"})
    assert "session_duration defaulted to unknown" not in assumptions
    assert "traffic_pattern defaulted to unknown" in assumptions


def test_warning_fires_for_microvms_high_launch():
    warnings = scoring._collect_warnings(
        {"launch_concurrency": "high"}, "lambda_microvms")
    assert len(warnings) == 1
    assert "5 TPS" in warnings[0]


def test_no_warning_for_other_verdict():
    assert scoring._collect_warnings(
        {"launch_concurrency": "high"}, "agentcore") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k "assumptions or warning" -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute '_collect_assumptions'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scoring.py`:

```python
def _collect_assumptions(raw_answers):
    out = []
    for dim in DIMENSIONS:
        if raw_answers.get(dim, "unknown") == "unknown":
            out.append(f"{dim} defaulted to unknown")
    return out


def _collect_warnings(answers, verdict):
    warnings = []
    if verdict == "lambda_microvms" and answers.get("launch_concurrency") == "high":
        warnings.append(
            "Lambda MicroVMs RunMicrovm is capped at 5 TPS and is not "
            "adjustable; high-concurrency launch storms will queue. If launch "
            "rate matters at scale, reconsider AgentCore Runtime (25 TPS, "
            "adjustable).")
    return warnings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k "assumptions or warning" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): assumptions tracking + 5 TPS launch guardrail"
```

---

### Task 9: `score()` orchestration + CLI + output schema

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/scoring.py`
- Create: `migrate/plugins/agent-advisor/scripts/schemas/scoring-result.json`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: every `_*` helper from Tasks 2-8, `load_profiles`.
- Produces:
  - `score(input_data: dict, profiles: list[dict] | None = None) -> dict` — top-level orchestrator returning the output shape from the Data Model. When `profiles is None`, calls `load_profiles()`. Fills `answers` from `DEFAULTS` then `input_data["answers"]`, sets `answers["_entry_point"]`. Includes `co_recommend` only for ties, `blocking_constraints` only for `no_viable_runtime`. `deployment_model` computed for the winner (and, on a tie that includes a runtime with deployment models, for that runtime).
  - CLI: `python scoring.py <answers.json>` reads the input file, runs `score`, writes `scoring-result.json` next to it, prints `RESULT=ok VERDICT=<verdict>`.

- [ ] **Step 1: Write the failing test**

Add to `test_scoring.py`:

```python
def test_score_end_to_end_with_fixture_profiles(tmp_path):
    _write_profile(tmp_path, {
        **_minimal("agentcore"),
        "deployment_models": ["harness", "framework_on_runtime"],
        "affinities": {"session_duration": {"15min_to_8hr": 5},
                       "traffic_pattern": {"bursty": 5}},
    })
    _write_profile(tmp_path, {
        **_minimal("lambda"),
        "hard_constraints": [{"field": "session_duration",
                              "value": "15min_to_8hr",
                              "reason": "Lambda has 15-minute timeout"}],
    })
    profiles = scoring.load_profiles(tmp_path)
    result = scoring.score({
        "entry_point": "build_scratch",
        "answers": {"session_duration": "15min_to_8hr",
                    "traffic_pattern": "bursty", "multi_agent": "no",
                    "framework": "none"}},
        profiles=profiles)

    assert result["verdict"] == "agentcore"
    assert result["eliminated"] == {"lambda": "Lambda has 15-minute timeout"}
    assert result["deployment_model"] == "harness"
    assert result["agentcore_services"][0] == "identity"
    assert "co_recommend" not in result
    assert "blocking_constraints" not in result


def test_score_no_viable_lists_blocking(tmp_path):
    _write_profile(tmp_path, {
        **_minimal("agentcore"),
        "hard_constraints": [{"field": "session_duration", "value": "over_8hr",
                              "reason": "8hr cap"}]})
    profiles = scoring.load_profiles(tmp_path)
    result = scoring.score(
        {"entry_point": "build_scratch",
         "answers": {"session_duration": "over_8hr"}}, profiles=profiles)
    assert result["verdict"] == "no_viable_runtime"
    assert result["blocking_constraints"] == ["agentcore: 8hr cap"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k "score_end_to_end or no_viable_lists" -v`
Expected: FAIL — `AttributeError: module 'scoring' has no attribute 'score'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scoring.py`:

```python
def score(input_data, profiles=None):
    if profiles is None:
        profiles = load_profiles()
    entry_point = input_data.get("entry_point", "build_scratch")
    raw_answers = input_data.get("answers", {})

    answers = dict(DEFAULTS)
    answers.update({k: v for k, v in raw_answers.items() if v is not None})
    answers["_entry_point"] = entry_point

    eliminated = _apply_hard_constraints(answers, profiles)
    scores = _compute_scores(answers, profiles, eliminated)
    verdict, co_recommend = _determine_verdict(scores, eliminated)

    deployment_model = None
    if verdict not in ("no_viable_runtime", "co_recommend"):
        deployment_model = _select_deployment_model(answers, verdict, profiles)
    elif verdict == "co_recommend":
        for rid in co_recommend:
            dm = _select_deployment_model(answers, rid, profiles)
            if dm is not None:
                deployment_model = dm
                break

    result = {
        "verdict": verdict,
        "scores": scores,
        "eliminated": eliminated,
        "deployment_model": deployment_model,
        "agentcore_services": _select_agentcore_services(answers),
        "model_recommendation": _select_model(answers),
        "assumptions_used": _collect_assumptions(raw_answers),
        "warnings": _collect_warnings(answers, verdict),
    }
    if verdict == "co_recommend":
        result["co_recommend"] = co_recommend
    if verdict == "no_viable_runtime":
        result["blocking_constraints"] = [
            f"{r}: {reason}" for r, reason in sorted(eliminated.items())]
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="agent-advisor runtime scoring")
    parser.add_argument("answers", type=pathlib.Path, help="path to answers.json")
    args = parser.parse_args(argv)
    input_data = json.loads(args.answers.read_text())
    result = score(input_data)
    out_path = args.answers.parent / "scoring-result.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"RESULT=ok VERDICT={result['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k "score_end_to_end or no_viable_lists" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Create the output schema**

Create `migrate/plugins/agent-advisor/scripts/schemas/scoring-result.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["verdict", "scores", "eliminated", "deployment_model",
               "agentcore_services", "model_recommendation",
               "assumptions_used", "warnings"],
  "properties": {
    "verdict": {"enum": ["agentcore", "lambda_microvms", "ecs", "eks",
                          "lambda", "co_recommend", "no_viable_runtime"]},
    "scores": {"type": "object", "additionalProperties": {"type": "integer"}},
    "eliminated": {"type": "object", "additionalProperties": {"type": "string"}},
    "deployment_model": {"type": ["string", "null"],
                          "enum": ["harness", "framework_on_runtime", null]},
    "agentcore_services": {"type": "array", "items": {"type": "string"}},
    "model_recommendation": {
      "type": "object", "required": ["model", "reasoning"],
      "properties": {
        "model": {"type": "string"}, "reasoning": {"type": "string"},
        "migration_from": {"type": "string"}, "pricing_note": {"type": "string"}}},
    "assumptions_used": {"type": "array", "items": {"type": "string"}},
    "warnings": {"type": "array", "items": {"type": "string"}},
    "co_recommend": {"type": "array", "items": {"type": "string"}},
    "blocking_constraints": {"type": "array", "items": {"type": "string"}}
  }
}
```

- [ ] **Step 6: Add a schema-validation test**

Add to `test_scoring.py`:

```python
def test_score_output_matches_schema(tmp_path):
    import jsonschema
    _write_profile(tmp_path, {**_minimal("agentcore"),
                              "deployment_models": ["harness", "framework_on_runtime"]})
    profiles = scoring.load_profiles(tmp_path)
    result = scoring.score(
        {"entry_point": "build_scratch", "answers": {}}, profiles=profiles)
    schema = json.loads(
        (pathlib.Path(scoring.__file__).parent / "schemas"
         / "scoring-result.json").read_text())
    jsonschema.validate(result, schema)
```

- [ ] **Step 7: Run the full suite**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -v`
Expected: PASS (all tests).

- [ ] **Step 8: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/scoring.py \
        migrate/plugins/agent-advisor/scripts/schemas/scoring-result.json \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): score() orchestration, CLI, and output schema"
```

---

### Task 10: Author the five runtime profiles + golden scenario tests

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/shared/runtimes/agentcore.json`
- Create: `migrate/plugins/agent-advisor/skills/shared/runtimes/lambda_microvms.json`
- Create: `migrate/plugins/agent-advisor/skills/shared/runtimes/ecs.json`
- Create: `migrate/plugins/agent-advisor/skills/shared/runtimes/eks.json`
- Create: `migrate/plugins/agent-advisor/skills/shared/runtimes/lambda.json`
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: `load_profiles`, `score` (against the real default `RUNTIMES_DIR`).
- Produces: the production registry — five `ga` profiles the engine loads by default.

- [ ] **Step 1: Create `agentcore.json`**

```json
{
  "id": "agentcore",
  "display_name": "AgentCore Runtime",
  "status": "ga",
  "launched": "2025-12-01",
  "service_card": "agentcore.md",
  "hard_constraints": [
    {"field": "session_duration", "value": "over_8hr", "reason": "AgentCore has an 8hr session cap"},
    {"field": "compute_tier", "value": "gpu", "reason": "AgentCore has no GPU support"},
    {"field": "compute_tier", "value": "heavy_non_gpu", "reason": "AgentCore is capped at 2 vCPU / 8 GB"},
    {"field": "compliance", "value": "fedramp", "reason": "AgentCore is not yet FedRAMP certified"}
  ],
  "affinities": {
    "session_duration": {"under_15min": 3, "15min_to_8hr": 5, "over_8hr": 0, "unknown": 3},
    "traffic_pattern": {"bursty": 5, "steady": 2, "idle": 4, "unknown": 3},
    "platform_fit": {"ecs": 1, "eks": 1, "lambda": 2, "none": 3, "unknown": 2},
    "session_state": {"stateless": 2, "stateful": 4, "hitl": 5, "unknown": 3},
    "ops_preference": {"minimal": 4, "moderate": 3, "full_control": 1, "unknown": 3},
    "isolation": {"required": 4, "nice_to_have": 3, "not_needed": 1, "unknown": 2},
    "memory_needs": {"cross_session": 4, "session_only": 3, "none": 1, "unknown": 2},
    "multi_agent": {"yes": 3, "no": 1, "unknown": 2},
    "framework": {"strands": 3, "langgraph": 3, "crewai": 3, "custom": 2, "none": 3, "unknown": 2},
    "existing_cluster": {"eks": 1, "ecs": 1, "none": 3, "unknown": 2},
    "multi_cloud": {"yes": 1, "no": 3, "unknown": 2},
    "idle_resume": {"process_level": 1, "filesystem": 4, "none": 2, "unknown": 2},
    "compute_tier": {"light": 4, "heavy_non_gpu": 0, "gpu": 0, "unknown": 2},
    "launch_concurrency": {"high": 5, "moderate": 3, "low": 2, "unknown": 2}
  },
  "deployment_models": ["harness", "framework_on_runtime"],
  "volatile_facts": [
    {"key": "session_cap", "value": "8h", "verify_via_mcp": true},
    {"key": "compute_cap", "value": "2vCPU/8GB", "verify_via_mcp": true},
    {"key": "fedramp", "value": "not_certified", "verify_via_mcp": true},
    {"key": "regions", "value": [], "verify_via_mcp": true}
  ]
}
```

- [ ] **Step 2: Create `lambda_microvms.json`**

```json
{
  "id": "lambda_microvms",
  "display_name": "Lambda MicroVMs",
  "status": "ga",
  "launched": "2026-06-22",
  "service_card": "lambda-microvms.md",
  "hard_constraints": [
    {"field": "session_duration", "value": "over_8hr", "reason": "Lambda MicroVMs max session is 8 hours"},
    {"field": "compute_tier", "value": "gpu", "reason": "Lambda MicroVMs has no documented GPU support"}
  ],
  "affinities": {
    "session_duration": {"under_15min": 3, "15min_to_8hr": 5, "over_8hr": 0, "unknown": 3},
    "traffic_pattern": {"bursty": 4, "steady": 3, "idle": 5, "unknown": 3},
    "platform_fit": {"ecs": 1, "eks": 1, "lambda": 3, "none": 3, "unknown": 2},
    "session_state": {"stateless": 3, "stateful": 5, "hitl": 5, "unknown": 3},
    "ops_preference": {"minimal": 2, "moderate": 5, "full_control": 3, "unknown": 2},
    "isolation": {"required": 4, "nice_to_have": 3, "not_needed": 2, "unknown": 2},
    "memory_needs": {"cross_session": 2, "session_only": 3, "none": 2, "unknown": 2},
    "multi_agent": {"yes": 2, "no": 2, "unknown": 2},
    "framework": {"strands": 2, "langgraph": 2, "crewai": 2, "custom": 3, "none": 2, "unknown": 2},
    "existing_cluster": {"eks": 1, "ecs": 1, "none": 3, "unknown": 2},
    "multi_cloud": {"yes": 2, "no": 2, "unknown": 2},
    "idle_resume": {"process_level": 5, "filesystem": 3, "none": 1, "unknown": 2},
    "compute_tier": {"light": 2, "heavy_non_gpu": 5, "gpu": 0, "unknown": 2},
    "launch_concurrency": {"high": 0, "moderate": 2, "low": 3, "unknown": 2}
  },
  "deployment_models": [],
  "volatile_facts": [
    {"key": "session_cap", "value": "8h", "verify_via_mcp": true},
    {"key": "max_compute", "value": "16vCPU/32GB", "verify_via_mcp": true},
    {"key": "launch_tps", "value": "5 (not adjustable)", "verify_via_mcp": true},
    {"key": "fedramp", "value": "unknown", "verify_via_mcp": true},
    {"key": "regions", "value": [], "verify_via_mcp": true}
  ]
}
```

- [ ] **Step 3: Create `ecs.json`**

```json
{
  "id": "ecs",
  "display_name": "Amazon ECS (Fargate)",
  "status": "ga",
  "launched": "2017-11-01",
  "service_card": "ecs.md",
  "hard_constraints": [],
  "affinities": {
    "session_duration": {"under_15min": 1, "15min_to_8hr": 3, "over_8hr": 4, "unknown": 2},
    "traffic_pattern": {"bursty": 1, "steady": 5, "idle": 0, "unknown": 2},
    "platform_fit": {"ecs": 4, "eks": 1, "lambda": 0, "none": 2, "unknown": 2},
    "session_state": {"stateless": 3, "stateful": 3, "hitl": 1, "unknown": 2},
    "ops_preference": {"minimal": 1, "moderate": 3, "full_control": 3, "unknown": 2},
    "isolation": {"required": 2, "nice_to_have": 2, "not_needed": 2, "unknown": 2},
    "memory_needs": {"cross_session": 1, "session_only": 2, "none": 2, "unknown": 2},
    "multi_agent": {"yes": 2, "no": 2, "unknown": 2},
    "framework": {"strands": 2, "langgraph": 2, "crewai": 2, "custom": 3, "none": 1, "unknown": 2},
    "existing_cluster": {"eks": 1, "ecs": 5, "none": 2, "unknown": 2},
    "multi_cloud": {"yes": 2, "no": 2, "unknown": 2},
    "idle_resume": {"process_level": 1, "filesystem": 1, "none": 2, "unknown": 2},
    "compute_tier": {"light": 1, "heavy_non_gpu": 4, "gpu": 5, "unknown": 2},
    "launch_concurrency": {"high": 3, "moderate": 2, "low": 2, "unknown": 2}
  },
  "deployment_models": [],
  "volatile_facts": [{"key": "regions", "value": "all", "verify_via_mcp": false}]
}
```

- [ ] **Step 4: Create `eks.json`**

```json
{
  "id": "eks",
  "display_name": "Amazon EKS",
  "status": "ga",
  "launched": "2018-06-01",
  "service_card": "eks.md",
  "hard_constraints": [],
  "affinities": {
    "session_duration": {"under_15min": 1, "15min_to_8hr": 3, "over_8hr": 4, "unknown": 2},
    "traffic_pattern": {"bursty": 1, "steady": 4, "idle": 0, "unknown": 2},
    "platform_fit": {"ecs": 1, "eks": 4, "lambda": 0, "none": 1, "unknown": 1},
    "session_state": {"stateless": 3, "stateful": 3, "hitl": 1, "unknown": 2},
    "ops_preference": {"minimal": 0, "moderate": 2, "full_control": 4, "unknown": 1},
    "isolation": {"required": 2, "nice_to_have": 2, "not_needed": 2, "unknown": 2},
    "memory_needs": {"cross_session": 1, "session_only": 2, "none": 2, "unknown": 2},
    "multi_agent": {"yes": 2, "no": 2, "unknown": 2},
    "framework": {"strands": 2, "langgraph": 2, "crewai": 2, "custom": 3, "none": 1, "unknown": 2},
    "existing_cluster": {"eks": 5, "ecs": 1, "none": 1, "unknown": 1},
    "multi_cloud": {"yes": 4, "no": 1, "unknown": 2},
    "idle_resume": {"process_level": 1, "filesystem": 1, "none": 2, "unknown": 2},
    "compute_tier": {"light": 1, "heavy_non_gpu": 4, "gpu": 5, "unknown": 2},
    "launch_concurrency": {"high": 3, "moderate": 2, "low": 2, "unknown": 2}
  },
  "deployment_models": [],
  "volatile_facts": [{"key": "regions", "value": "all", "verify_via_mcp": false}]
}
```

- [ ] **Step 5: Create `lambda.json`**

```json
{
  "id": "lambda",
  "display_name": "AWS Lambda (standard)",
  "status": "ga",
  "launched": "2014-11-01",
  "service_card": "lambda.md",
  "hard_constraints": [
    {"field": "session_duration", "value": "15min_to_8hr", "reason": "Lambda has a 15-minute timeout"},
    {"field": "session_duration", "value": "over_8hr", "reason": "Lambda has a 15-minute timeout"}
  ],
  "affinities": {
    "session_duration": {"under_15min": 5, "15min_to_8hr": 0, "over_8hr": 0, "unknown": 2},
    "traffic_pattern": {"bursty": 4, "steady": 1, "idle": 5, "unknown": 3},
    "platform_fit": {"ecs": 0, "eks": 0, "lambda": 4, "none": 2, "unknown": 2},
    "session_state": {"stateless": 5, "stateful": 1, "hitl": 1, "unknown": 2},
    "ops_preference": {"minimal": 3, "moderate": 2, "full_control": 1, "unknown": 2},
    "isolation": {"required": 3, "nice_to_have": 2, "not_needed": 2, "unknown": 2},
    "memory_needs": {"cross_session": 0, "session_only": 1, "none": 3, "unknown": 2},
    "multi_agent": {"yes": 1, "no": 2, "unknown": 2},
    "framework": {"strands": 2, "langgraph": 2, "crewai": 1, "custom": 2, "none": 2, "unknown": 2},
    "existing_cluster": {"eks": 0, "ecs": 0, "none": 3, "unknown": 2},
    "multi_cloud": {"yes": 1, "no": 2, "unknown": 2},
    "idle_resume": {"process_level": 0, "filesystem": 1, "none": 3, "unknown": 2},
    "compute_tier": {"light": 3, "heavy_non_gpu": 1, "gpu": 0, "unknown": 2},
    "launch_concurrency": {"high": 4, "moderate": 3, "low": 2, "unknown": 2}
  },
  "deployment_models": [],
  "volatile_facts": [{"key": "timeout", "value": "15m", "verify_via_mcp": false}]
}
```

- [ ] **Step 6: Write golden scenario tests against the real registry**

Add to `test_scoring.py`:

```python
def _real_profiles():
    return scoring.load_profiles()  # default RUNTIMES_DIR


def test_golden_loads_five_ga_runtimes():
    ids = {p["id"] for p in _real_profiles()}
    assert ids == {"agentcore", "lambda_microvms", "ecs", "eks", "lambda"}


def test_golden_over_8hr_eliminates_agentcore_and_microvms():
    # Regression against the old PM decision-tree bug (spec §7.1).
    result = scoring.score({
        "entry_point": "migrate",
        "answers": {"session_duration": "over_8hr"}}, profiles=_real_profiles())
    assert "agentcore" in result["eliminated"]
    assert "lambda_microvms" in result["eliminated"]
    assert result["verdict"] in ("ecs", "eks", "co_recommend")


def test_golden_microvms_wins_process_level_resume():
    result = scoring.score({
        "entry_point": "build_deploy",
        "answers": {"session_duration": "15min_to_8hr", "idle_resume": "process_level",
                    "session_state": "hitl", "ops_preference": "moderate"}},
        profiles=_real_profiles())
    assert result["verdict"] == "lambda_microvms"


def test_golden_microvms_wins_heavy_non_gpu():
    result = scoring.score({
        "entry_point": "build_deploy",
        "answers": {"compute_tier": "heavy_non_gpu", "session_duration": "15min_to_8hr"}},
        profiles=_real_profiles())
    assert "agentcore" in result["eliminated"]
    assert result["verdict"] == "lambda_microvms"


def test_golden_agentic_io_wait_favors_agentcore():
    result = scoring.score({
        "entry_point": "build_scratch",
        "answers": {"session_duration": "15min_to_8hr", "traffic_pattern": "bursty",
                    "session_state": "hitl", "ops_preference": "minimal",
                    "multi_agent": "no", "framework": "none"}},
        profiles=_real_profiles())
    assert result["verdict"] == "agentcore"
    assert result["deployment_model"] == "harness"


def test_golden_microvms_high_launch_emits_warning():
    result = scoring.score({
        "entry_point": "build_deploy",
        "answers": {"compute_tier": "heavy_non_gpu", "session_duration": "15min_to_8hr",
                    "launch_concurrency": "high"}}, profiles=_real_profiles())
    assert result["verdict"] == "lambda_microvms"
    assert any("5 TPS" in w for w in result["warnings"])
```

- [ ] **Step 7: Run the golden tests**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k golden -v`
Expected: PASS (6 passed). If a `verdict` assertion fails, adjust the affinity values in the relevant profile JSON (not the engine) until the intended runtime wins — the engine is fixed, the data is what's tuned.

- [ ] **Step 8: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/shared/runtimes/ \
        migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "feat(agent-advisor): author 5 runtime profiles + golden scenario tests"
```

---

### Task 11: Profile consistency test (parametrized over the registry)

**Files:**
- Test: `migrate/plugins/agent-advisor/scripts/test_scoring.py`

**Interfaces:**
- Consumes: `load_profiles`, `DIMENSIONS`.
- Produces: a guard test so a future malformed profile (illegal dimension, bad affinity type, unknown status value) fails CI rather than silently mis-scoring.

- [ ] **Step 1: Write the failing/guard test**

Add to `test_scoring.py`:

```python
VALID_STATUSES = {"ga", "preview", "coming_soon"}


@pytest.mark.parametrize("profile", scoring.load_profiles(
    statuses=frozenset({"ga", "preview", "coming_soon"})),
    ids=lambda p: p["id"])
def test_profile_is_well_formed(profile):
    assert profile["status"] in VALID_STATUSES
    # affinity dimensions must be real scoring dimensions
    for dim in profile["affinities"]:
        assert dim in scoring.DIMENSIONS, f"unknown dimension {dim}"
        for value, points in profile["affinities"][dim].items():
            assert isinstance(points, int), f"{dim}.{value} not an int"
    # hard-constraint fields must be answerable keys
    answerable = set(scoring.DIMENSIONS) | {"compliance"}
    for constraint in profile["hard_constraints"]:
        assert constraint["field"] in answerable
        assert "reason" in constraint and constraint["reason"]
```

- [ ] **Step 2: Run the consistency test**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -k well_formed -v`
Expected: PASS (5 parametrized cases — one per real profile).

- [ ] **Step 3: Run the entire suite once more**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_scoring.py -v`
Expected: PASS (all tests green).

- [ ] **Step 4: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/test_scoring.py
git commit -m "test(agent-advisor): parametrized profile consistency guard"
```

---

## Self-Review

**Spec coverage (Plan 1 scope only — the decision engine):**

- §6.1 carry over scoring.py/test_scoring.py via uv → Tasks 1-11 ✓
- §6.2 hard-constraint-first + weighted scoring + tie co-recommend + no_viable → Tasks 2,3,4 ✓
- §6.3 minimal model default, no pricing tables, coarse migrate family → Task 7 ✓
- §7.2 Lambda MicroVMs as first-class scored runtime → Task 10 (`lambda_microvms.json`, `status: ga`) ✓
- §7.3 new differentiating dimensions (idle_resume, compute_tier, launch_concurrency) → Data Model + Tasks 3,10 ✓
- §7.4 hard constraints incl. GPU/heavy_non_gpu/over_8hr; FedRAMP via volatile_facts not hardcoded for microvms → Task 10 profiles ✓
- §7.1 regression: >8hr eliminates both AgentCore and Lambda MicroVMs → Task 10 golden test ✓
- §7.3 5 TPS guardrail warning → Task 8 + Task 10 golden test ✓
- §8 Layer 1 registry (JSON, one file per runtime, generic engine, add runtime = add file) → all tasks ✓
- §8 Layer 2 volatile_facts present in profiles (MCP refresh consumed by Plan 2, not engine) → Task 10 profiles carry the field ✓
- §13 checklist items for scoring (test_scoring passes; Lambda MicroVMs wins its scenarios; >8hr regression) → Tasks 10,11 ✓

**Deferred to later plans (correctly out of Plan 1 scope):** §3.2 shared-reference reads, §5 Clarify wording, §9 knowledge layer/MCP runtime calls, §10 output doc + diagram, §11 chat-level error handling, §12 packaging, install-time verification. These are Plan 2 (orchestration) and Plan 3 (diagram).

**Placeholder scan:** No TBD/TODO. Every code step shows complete code; every profile is full JSON. Task 10 Step 7 notes that affinity *data* may need tuning to make golden assertions pass — this is expected data-tuning, not a code placeholder (the engine is fixed).

**Type consistency:** `load_profiles`, `_apply_hard_constraints`, `_compute_scores`, `_determine_verdict`, `_select_deployment_model`, `_select_agentcore_services`, `_select_model`, `_collect_assumptions`, `_collect_warnings`, `score` — names used identically across tasks. `DIMENSIONS` (14 items) consistent between Task 3 definition and Tasks 8/11 consumers. Output keys match the `scoring-result.json` schema (Task 9) and the Data Model contract.

---

## Next plans (not yet written)

- **Plan 2 — Skill orchestration:** Turn 1 (`AskUserQuestion`), Discover (lightweight detection), Clarify technical/business wording + Pass 2, Design, Estimate (reuse migration-to-aws pricing pattern), Generate, Migrate handoff, the standalone `add-capabilities` skill, shared-reference reads via `${CLAUDE_PLUGIN_ROOT}`, volatile-fact MCP refresh + freshness footer, three platform manifests, marketplace entry, install-time verification.
- **Plan 3 — Architecture diagram:** `diagram-fragments/` (Mermaid + ASCII pair per runtime/service/edge), the `build-diagram` composition keyed by `scoring-result.json`, golden-output diagram tests, handoff annotation for ECS/EKS/Lambda verdicts.
