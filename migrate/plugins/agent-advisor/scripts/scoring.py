"""Deterministic, registry-driven runtime-scoring engine for agent-advisor.

Pure: answers dict -> recommendation dict. No network, no AWS. Runtime
knowledge lives in JSON profiles under skills/shared/runtimes/.
"""
import json
import pathlib

RUNTIMES_DIR = pathlib.Path(__file__).parent.parent / "skills" / "shared" / "runtimes"

_REQUIRED_PROFILE_KEYS = ("id", "status", "affinities", "hard_constraints")

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
