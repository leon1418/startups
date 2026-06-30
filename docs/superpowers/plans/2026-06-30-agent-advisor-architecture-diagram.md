# Agent Advisor — Architecture Diagram Implementation Plan (Plan 3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate an architecture diagram of the recommended deployment in the recommendation document — a Mermaid block (primary) and an ASCII fallback — assembled **deterministically** from the scoring result, so the same recommendation always yields the same diagram.

**Architecture:** A pure Python composer (`build_diagram.py`, alongside `scoring.py`) reads `scoring-result.json` + `pass2.json` and composes predefined diagram fragments (one runtime node, one node per activated AgentCore service, edges for data flows, a handoff annotation for ECS/EKS/Lambda verdicts) into two strings: a Mermaid `flowchart` and an ASCII box diagram. Fragments are small templates keyed by runtime id / service id, so coverage is data-driven and testable with golden outputs. The Generate phase (Plan 2, Task 10, Step 2) calls this composer and embeds both renderings into the recommendation doc.

**Tech Stack:** Python ≥3.10 stdlib only (`json`, `argparse`, `pathlib`); `pytest`; runs via `uv` (same `scripts/` project as Plan 1).

## Global Constraints

- Depends on **Plan 1** (`scoring-result.json` shape) and integrates with **Plan 2** (Generate Task 10, Step 2). Both should be complete; the composer can be built and unit-tested with fixture inputs even if Plan 2 isn't finished.
- All paths relative to repo root `/Volumes/workspace/startups`. Composer lives in `migrate/plugins/agent-advisor/scripts/`.
- Determinism is the contract: same `scoring-result.json` + `pass2.json` → byte-identical Mermaid and ASCII. No timestamps, no randomness, stable ordering.
- Five runtime ids fixed: `agentcore`, `lambda_microvms`, `ecs`, `eks`, `lambda`. Service ids match Plan 1's selection output (`identity`, `observability`, `evaluations`, `optimization`, `memory`, `gateway`, `policy`, plus any Pass-2 additions: `managed_kb`, `code_interpreter`, `browser`, `web_search`, `sandbox`).
- ECS/EKS/Lambda verdicts get a handoff annotation ("compute configured by migration-to-aws"); co_recommend renders the runtime the user picked in Pass 2 (read from `pass2.json`'s `chosen_runtime`, falling back to the first `co_recommend` id).
- All content in **English**.
- Run commands from `migrate/plugins/agent-advisor/scripts/` via `uv run`.

---

## Input contract (consumed)

From `scoring-result.json` (Plan 1): `verdict`, `deployment_model`, `agentcore_services`, `model_recommendation.model`, `co_recommend` (when tied).
From `pass2.json` (Plan 2, Task 7): `agentcore_services` (final, overrides the scoring default), `chosen_runtime` (set when the user resolved a co_recommend tie).

**`build_diagram(result: dict, pass2: dict) -> dict`** returns:
```json
{"mermaid": "flowchart TD\n ...", "ascii": "+--------+\n ..."}
```

---

### Task 1: Resolve the runtime to render + fragment registry

**Files:**
- Create: `migrate/plugins/agent-advisor/scripts/build_diagram.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_build_diagram.py`

**Interfaces:**
- Consumes: `scoring-result.json` + `pass2.json` shapes (dicts).
- Produces:
  - `RUNTIME_LABELS: dict[str, str]` — runtime id → display label (`agentcore` → "AgentCore Runtime", `lambda_microvms` → "Lambda MicroVMs", `ecs` → "Amazon ECS (Fargate)", `eks` → "Amazon EKS", `lambda` → "AWS Lambda").
  - `SERVICE_LABELS: dict[str, str]` — service id → label for all 12 service ids in Global Constraints.
  - `HANDOFF_RUNTIMES = {"ecs", "eks", "lambda"}`.
  - `resolve_runtime(result: dict, pass2: dict) -> str` — returns the runtime id to render: `result["verdict"]` unless it is `co_recommend` (then `pass2.get("chosen_runtime")` or `result["co_recommend"][0]`) or `no_viable_runtime` (then the literal `"none"`).

- [ ] **Step 1: Write the failing test**

Create `migrate/plugins/agent-advisor/scripts/test_build_diagram.py`:

```python
import build_diagram


def test_resolve_runtime_single_winner():
    assert build_diagram.resolve_runtime(
        {"verdict": "agentcore"}, {}) == "agentcore"


def test_resolve_runtime_co_recommend_uses_pass2_choice():
    result = {"verdict": "co_recommend", "co_recommend": ["ecs", "eks"]}
    assert build_diagram.resolve_runtime(result, {"chosen_runtime": "eks"}) == "eks"


def test_resolve_runtime_co_recommend_falls_back_to_first():
    result = {"verdict": "co_recommend", "co_recommend": ["ecs", "eks"]}
    assert build_diagram.resolve_runtime(result, {}) == "ecs"


def test_resolve_runtime_no_viable():
    assert build_diagram.resolve_runtime(
        {"verdict": "no_viable_runtime"}, {}) == "none"


def test_labels_cover_all_runtimes():
    for rid in ("agentcore", "lambda_microvms", "ecs", "eks", "lambda"):
        assert rid in build_diagram.RUNTIME_LABELS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_diagram'`.

- [ ] **Step 3: Write minimal implementation**

Create `migrate/plugins/agent-advisor/scripts/build_diagram.py`:

```python
"""Deterministic architecture-diagram composer for agent-advisor.

Pure: (scoring-result, pass2) dicts -> {"mermaid": str, "ascii": str}.
Same input -> byte-identical output. No timestamps, no randomness.
"""
import json
import pathlib

RUNTIME_LABELS = {
    "agentcore": "AgentCore Runtime",
    "lambda_microvms": "Lambda MicroVMs",
    "ecs": "Amazon ECS (Fargate)",
    "eks": "Amazon EKS",
    "lambda": "AWS Lambda",
    "none": "No viable runtime",
}

SERVICE_LABELS = {
    "identity": "Identity",
    "observability": "Observability",
    "evaluations": "Evaluations",
    "optimization": "Optimization",
    "memory": "Memory",
    "gateway": "Gateway",
    "policy": "Policy",
    "managed_kb": "Managed KB",
    "code_interpreter": "Code Interpreter",
    "browser": "Browser",
    "web_search": "Web Search",
    "sandbox": "Sandbox",
}

HANDOFF_RUNTIMES = {"ecs", "eks", "lambda"}


def resolve_runtime(result, pass2):
    verdict = result.get("verdict")
    if verdict == "co_recommend":
        return pass2.get("chosen_runtime") or result.get("co_recommend", ["none"])[0]
    if verdict == "no_viable_runtime":
        return "none"
    return verdict
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/build_diagram.py \
        migrate/plugins/agent-advisor/scripts/test_build_diagram.py
git commit -m "feat(agent-advisor): diagram composer scaffold + runtime resolution"
```

---

### Task 2: Resolve the service list to render

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/build_diagram.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_build_diagram.py`

**Interfaces:**
- Consumes: `scoring-result.json` + `pass2.json`.
- Produces: `resolve_services(result: dict, pass2: dict) -> list[str]` — the final service list to draw. Prefers `pass2["agentcore_services"]` when present (the user's confirmed set), else `result.get("agentcore_services", [])`. Filters to ids present in `SERVICE_LABELS`, preserving input order, de-duplicated.

- [ ] **Step 1: Write the failing test**

Add to `test_build_diagram.py`:

```python
def test_resolve_services_prefers_pass2():
    result = {"agentcore_services": ["identity", "observability"]}
    pass2 = {"agentcore_services": ["identity", "memory", "gateway"]}
    assert build_diagram.resolve_services(result, pass2) == [
        "identity", "memory", "gateway"]


def test_resolve_services_falls_back_to_result():
    result = {"agentcore_services": ["identity", "observability"]}
    assert build_diagram.resolve_services(result, {}) == [
        "identity", "observability"]


def test_resolve_services_filters_unknown_and_dedupes():
    pass2 = {"agentcore_services": ["identity", "identity", "bogus", "memory"]}
    assert build_diagram.resolve_services({}, pass2) == ["identity", "memory"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k resolve_services -v`
Expected: FAIL — `AttributeError: module 'build_diagram' has no attribute 'resolve_services'`.

- [ ] **Step 3: Write minimal implementation**

Add to `build_diagram.py`:

```python
def resolve_services(result, pass2):
    services = pass2.get("agentcore_services") or result.get("agentcore_services", [])
    seen, out = set(), []
    for sid in services:
        if sid in SERVICE_LABELS and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k resolve_services -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/build_diagram.py \
        migrate/plugins/agent-advisor/scripts/test_build_diagram.py
git commit -m "feat(agent-advisor): resolve service list for diagram"
```

---

### Task 3: Mermaid renderer

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/build_diagram.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_build_diagram.py`

**Interfaces:**
- Consumes: resolved runtime id, service list, model label, deployment model, handoff flag.
- Produces: `render_mermaid(runtime: str, services: list[str], model: str, deployment_model: str | None) -> str` — a `flowchart TD` with: a User node → Runtime node (label includes deployment model for agentcore), Runtime → Bedrock model node, Runtime → each service node, and a handoff note node when the runtime is in `HANDOFF_RUNTIMES`. Deterministic node ids and ordering.

- [ ] **Step 1: Write the failing test**

Add to `test_build_diagram.py`:

```python
def test_mermaid_has_runtime_model_and_services():
    out = build_diagram.render_mermaid(
        "agentcore", ["identity", "memory"], "claude_sonnet_4_6", "harness")
    assert out.startswith("flowchart TD")
    assert "AgentCore Runtime" in out
    assert "harness" in out.lower()
    assert "claude_sonnet_4_6" in out
    assert "Identity" in out and "Memory" in out
    assert "migration-to-aws" not in out  # no handoff for agentcore


def test_mermaid_adds_handoff_note_for_ecs():
    out = build_diagram.render_mermaid("ecs", [], "claude_sonnet_4_6", None)
    assert "Amazon ECS (Fargate)" in out
    assert "migration-to-aws" in out


def test_mermaid_deterministic():
    a = build_diagram.render_mermaid("agentcore", ["identity", "memory"],
                                     "claude_sonnet_4_6", "harness")
    b = build_diagram.render_mermaid("agentcore", ["identity", "memory"],
                                     "claude_sonnet_4_6", "harness")
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k mermaid -v`
Expected: FAIL — `AttributeError: module 'build_diagram' has no attribute 'render_mermaid'`.

- [ ] **Step 3: Write minimal implementation**

Add to `build_diagram.py`:

```python
def render_mermaid(runtime, services, model, deployment_model):
    label = RUNTIME_LABELS.get(runtime, runtime)
    if runtime == "agentcore" and deployment_model:
        label = f"{label}<br/>({deployment_model})"
    lines = ["flowchart TD"]
    lines.append(f'    user["User / Client"]')
    lines.append(f'    rt["{label}"]')
    lines.append(f'    model["Bedrock: {model}"]')
    lines.append("    user --> rt")
    lines.append("    rt --> model")
    for sid in services:
        lines.append(f'    svc_{sid}["{SERVICE_LABELS[sid]}"]')
        lines.append(f"    rt --> svc_{sid}")
    if runtime in HANDOFF_RUNTIMES:
        lines.append('    handoff["Compute configured by migration-to-aws"]')
        lines.append("    rt -.-> handoff")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k mermaid -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/build_diagram.py \
        migrate/plugins/agent-advisor/scripts/test_build_diagram.py
git commit -m "feat(agent-advisor): Mermaid diagram renderer"
```

---

### Task 4: ASCII fallback renderer

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/build_diagram.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_build_diagram.py`

**Interfaces:**
- Consumes: same inputs as `render_mermaid`.
- Produces: `render_ascii(runtime: str, services: list[str], model: str, deployment_model: str | None) -> str` — a plain-text box diagram: a runtime header line (with deployment model for agentcore), a model line, a bulleted service list, and a handoff line for `HANDOFF_RUNTIMES`. Deterministic.

- [ ] **Step 1: Write the failing test**

Add to `test_build_diagram.py`:

```python
def test_ascii_contains_runtime_model_services():
    out = build_diagram.render_ascii(
        "agentcore", ["identity", "memory"], "claude_sonnet_4_6", "harness")
    assert "AgentCore Runtime" in out
    assert "harness" in out.lower()
    assert "claude_sonnet_4_6" in out
    assert "- Identity" in out and "- Memory" in out
    assert "migration-to-aws" not in out


def test_ascii_handoff_for_lambda():
    out = build_diagram.render_ascii("lambda", [], "claude_sonnet_4_6", None)
    assert "AWS Lambda" in out
    assert "migration-to-aws" in out


def test_ascii_deterministic():
    a = build_diagram.render_ascii("eks", ["identity"], "claude_sonnet_4_6", None)
    b = build_diagram.render_ascii("eks", ["identity"], "claude_sonnet_4_6", None)
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k ascii -v`
Expected: FAIL — `AttributeError: module 'build_diagram' has no attribute 'render_ascii'`.

- [ ] **Step 3: Write minimal implementation**

Add to `build_diagram.py`:

```python
def render_ascii(runtime, services, model, deployment_model):
    label = RUNTIME_LABELS.get(runtime, runtime)
    if runtime == "agentcore" and deployment_model:
        label = f"{label} ({deployment_model})"
    lines = [
        "User / Client",
        "    |",
        "    v",
        f"[ {label} ]",
        f"    |-- model --> Bedrock: {model}",
    ]
    for sid in services:
        lines.append(f"    |-- service --> {SERVICE_LABELS[sid]}")
    # bullet list mirror for easy scanning
    if services:
        lines.append("Services:")
        for sid in services:
            lines.append(f"  - {SERVICE_LABELS[sid]}")
    if runtime in HANDOFF_RUNTIMES:
        lines.append("Note: compute configured by migration-to-aws")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k ascii -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/build_diagram.py \
        migrate/plugins/agent-advisor/scripts/test_build_diagram.py
git commit -m "feat(agent-advisor): ASCII fallback diagram renderer"
```

---

### Task 5: `build_diagram()` orchestration + CLI

**Files:**
- Modify: `migrate/plugins/agent-advisor/scripts/build_diagram.py`
- Test: `migrate/plugins/agent-advisor/scripts/test_build_diagram.py`

**Interfaces:**
- Consumes: `scoring-result.json` + `pass2.json` paths.
- Produces:
  - `build_diagram(result: dict, pass2: dict) -> dict` — `{"mermaid": ..., "ascii": ...}`. For `verdict == "no_viable_runtime"`, returns a minimal "no viable runtime" diagram (both renderings) instead of a runtime node.
  - CLI: `python build_diagram.py <scoring-result.json> <pass2.json>` writes `diagram.md` (a fenced ```mermaid``` block followed by a `<details>` ASCII block) next to the result file and prints `RESULT=ok RUNTIME=<id>`.

- [ ] **Step 1: Write the failing test**

Add to `test_build_diagram.py`:

```python
def test_build_diagram_end_to_end():
    result = {"verdict": "agentcore", "deployment_model": "harness",
              "agentcore_services": ["identity"],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {})
    assert "flowchart TD" in out["mermaid"]
    assert "AgentCore Runtime" in out["ascii"]


def test_build_diagram_no_viable():
    out = build_diagram.build_diagram({"verdict": "no_viable_runtime"}, {})
    assert "No viable runtime" in out["mermaid"]
    assert "No viable runtime" in out["ascii"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k "end_to_end or no_viable" -v`
Expected: FAIL — `AttributeError: module 'build_diagram' has no attribute 'build_diagram'`.

- [ ] **Step 3: Write minimal implementation**

Add to `build_diagram.py`:

```python
def build_diagram(result, pass2):
    runtime = resolve_runtime(result, pass2)
    if runtime == "none":
        msg = "No viable runtime — see blocking constraints"
        return {
            "mermaid": f'flowchart TD\n    n["{msg}"]',
            "ascii": f"[ {RUNTIME_LABELS['none']} ]\n{msg}",
        }
    services = resolve_services(result, pass2)
    model = result.get("model_recommendation", {}).get("model", "unknown")
    deployment_model = result.get("deployment_model")
    return {
        "mermaid": render_mermaid(runtime, services, model, deployment_model),
        "ascii": render_ascii(runtime, services, model, deployment_model),
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="agent-advisor diagram composer")
    parser.add_argument("result", type=pathlib.Path)
    parser.add_argument("pass2", type=pathlib.Path)
    args = parser.parse_args(argv)
    result = json.loads(args.result.read_text())
    pass2 = json.loads(args.pass2.read_text()) if args.pass2.exists() else {}
    diagram = build_diagram(result, pass2)
    out = (
        "```mermaid\n" + diagram["mermaid"] + "\n```\n\n"
        "<details><summary>ASCII (plain-text fallback)</summary>\n\n"
        "```\n" + diagram["ascii"] + "\n```\n\n</details>\n"
    )
    out_path = args.result.parent / "diagram.md"
    out_path.write_text(out)
    print(f"RESULT=ok RUNTIME={resolve_runtime(result, pass2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k "end_to_end or no_viable" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/build_diagram.py \
        migrate/plugins/agent-advisor/scripts/test_build_diagram.py
git commit -m "feat(agent-advisor): build_diagram orchestration + CLI"
```

---

### Task 6: Golden-output tests (per verdict)

**Files:**
- Test: `migrate/plugins/agent-advisor/scripts/test_build_diagram.py`

**Interfaces:**
- Consumes: `build_diagram`.
- Produces: golden assertions covering each verdict path, so a future change to the renderer is caught (spec §13: same result → same diagram; handoff annotation for ECS/EKS/Lambda).

- [ ] **Step 1: Write the golden tests**

Add to `test_build_diagram.py`:

```python
def test_golden_agentcore_full():
    result = {"verdict": "agentcore", "deployment_model": "framework_on_runtime",
              "agentcore_services": ["identity", "observability", "memory", "gateway"],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {})
    # runtime + deployment model + all four services + model, no handoff
    assert "framework_on_runtime" in out["mermaid"]
    for svc in ("Identity", "Observability", "Memory", "Gateway"):
        assert svc in out["mermaid"] and svc in out["ascii"]
    assert "migration-to-aws" not in out["mermaid"]


def test_golden_lambda_microvms_no_services_no_handoff():
    result = {"verdict": "lambda_microvms", "deployment_model": None,
              "agentcore_services": [],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {})
    assert "Lambda MicroVMs" in out["mermaid"]
    assert "migration-to-aws" not in out["mermaid"]  # MicroVMs is not a handoff runtime


def test_golden_ecs_has_handoff():
    result = {"verdict": "ecs", "deployment_model": None,
              "agentcore_services": ["identity"],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {})
    assert "migration-to-aws" in out["mermaid"]
    assert "migration-to-aws" in out["ascii"]


def test_golden_co_recommend_renders_chosen():
    result = {"verdict": "co_recommend", "co_recommend": ["ecs", "eks"],
              "deployment_model": None, "agentcore_services": [],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {"chosen_runtime": "eks"})
    assert "Amazon EKS" in out["mermaid"]
    assert "migration-to-aws" in out["mermaid"]  # eks is a handoff runtime
```

- [ ] **Step 2: Run the golden tests**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -k golden -v`
Expected: PASS (4 passed).

- [ ] **Step 3: Run the full diagram suite**

Run: `cd migrate/plugins/agent-advisor/scripts && uv run pytest test_build_diagram.py -v`
Expected: PASS (all tests).

- [ ] **Step 4: Commit**

```bash
git add migrate/plugins/agent-advisor/scripts/test_build_diagram.py
git commit -m "test(agent-advisor): golden diagram outputs per verdict"
```

---

### Task 7: Wire the composer into Generate

**Files:**
- Create: `migrate/plugins/agent-advisor/skills/agent-advisor/references/diagram/build-diagram.md`
- Modify: `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/generate.md` (Step 2 — replace the Plan-3 placeholder note with the real call)

**Interfaces:**
- Consumes: `$RUN_DIR/scoring-result.json`, `$RUN_DIR/pass2.json`.
- Produces: `$RUN_DIR/diagram.md`, embedded into Section 4 of the recommendation doc by Generate.

- [ ] **Step 1: Write build-diagram.md**

````markdown
# Generate sub-step: Build the architecture diagram

Produces `$RUN_DIR/diagram.md` (a Mermaid block + ASCII fallback), composed deterministically
from the scoring result.

## Step 1 — Run the composer
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT}/scripts python ${CLAUDE_PLUGIN_ROOT}/scripts/build_diagram.py \
  $RUN_DIR/scoring-result.json $RUN_DIR/pass2.json
```
This writes `$RUN_DIR/diagram.md` and prints `RESULT=ok RUNTIME=<id>`. If `pass2.json` is
absent (e.g. co_recommend not yet resolved), the composer treats it as empty.

## Step 2 — Embed into the recommendation
Insert the full contents of `$RUN_DIR/diagram.md` into Section 4 ("Architecture diagram") of
`$RUN_DIR/recommendation.md`. Do not hand-draw or edit the diagram — it is generated, so it
stays consistent with the scoring result.
````

- [ ] **Step 2: Update generate.md Step 2**

In `migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/generate.md`, replace
the Step 2 body (the Plan-3 placeholder) with:

```markdown
## Step 2 — Build the architecture diagram
Load `references/diagram/build-diagram.md` and follow it to produce `$RUN_DIR/diagram.md`
(Mermaid + ASCII), then embed it into Section 4 of the recommendation doc.
```

- [ ] **Step 3: Verify both files are consistent**

Run:
```bash
test -f migrate/plugins/agent-advisor/skills/agent-advisor/references/diagram/build-diagram.md && \
grep -q "build-diagram.md" migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/generate.md && echo OK
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add migrate/plugins/agent-advisor/skills/agent-advisor/references/diagram/build-diagram.md \
        migrate/plugins/agent-advisor/skills/agent-advisor/references/phases/generate.md
git commit -m "feat(agent-advisor): wire diagram composer into Generate phase"
```

---

## Self-Review

**Spec coverage (Plan 3 scope — §10.1 architecture diagram):**
- Mermaid (primary) + ASCII (fallback), emitted together → Tasks 3, 4, 5 (CLI emits both in one `diagram.md`) ✓
- Assembled deterministically from the scoring result (template composition, not LLM-drawn) →
  pure `build_diagram.py`, determinism tests (T3 Step1, T4 Step1) ✓
- Runtime node per verdict + deployment-model variant for agentcore → `render_mermaid`/`render_ascii` (T3/T4) ✓
- AgentCore service nodes for each activated service → `resolve_services` + renderers (T2/T3/T4) ✓
- Edge fragments (user→runtime, runtime→model, runtime→services) → renderers ✓
- Handoff annotation for ECS/EKS/Lambda verdicts → `HANDOFF_RUNTIMES` + golden test (T6) ✓
- co_recommend renders the chosen runtime → `resolve_runtime` + golden test (T1/T6) ✓
- Covered by golden-output testing like the rest of Generate → Task 6 ✓
- Integration point = Generate Task 10 Step 2 (Plan 2) → Task 7 wires it ✓
- §13 checklist "diagram composes deterministically; both renderings; handoff annotation for
  ECS/EKS/Lambda" → Tasks 3-6 ✓

**Placeholder scan:** No TBD/TODO. Every step shows complete code. Task 7 Step 2 edits a Plan 2
file — phrased as a concrete replacement, and Plan 2's Generate Step 2 was written with an
explicit fallback so the two plans compose cleanly regardless of build order.

**Type/name consistency:** `resolve_runtime`, `resolve_services`, `render_mermaid`,
`render_ascii`, `build_diagram` used identically across tasks. Input keys (`verdict`,
`deployment_model`, `agentcore_services`, `co_recommend`, `model_recommendation.model`) match
Plan 1's `scoring-result.json` schema. `chosen_runtime` / `agentcore_services` in `pass2.json`
match Plan 2 Task 7's output. Service ids match Plan 1's selection output plus Pass-2 additions.

---

## Plan set complete

This is Plan 3 of 3. Build order: **Plan 1 (engine) → Plan 2 (orchestration) → Plan 3
(diagram)**. Plan 3's composer can be unit-tested independently with fixture inputs, but its
Generate integration (Task 7) assumes Plan 2's `generate.md` exists.
