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


def test_assumptions_lists_unknown_dimensions():
    assumptions = scoring._collect_assumptions({"session_duration": "under_15min"})
    assert "session_duration defaulted to unknown" not in assumptions
    assert "traffic_pattern defaulted to unknown" in assumptions


def test_warning_fires_for_microvms_high_launch():
    warnings = scoring._collect_warnings(
        {"launch_concurrency": "high"}, "lambda_microvms")
    assert len(warnings) == 1
    assert "5 TPS" in warnings[0]


def test_warning_fires_for_microvms_in_co_recommend():
    warnings = scoring._collect_warnings(
        {"launch_concurrency": "high"}, "co_recommend",
        co_recommend=["agentcore", "lambda_microvms"])
    assert len(warnings) == 1
    assert "5 TPS" in warnings[0]


def test_no_warning_when_microvms_not_in_co_recommend():
    assert scoring._collect_warnings(
        {"launch_concurrency": "high"}, "co_recommend",
        co_recommend=["ecs", "eks"]) == []


def test_no_warning_for_other_verdict():
    assert scoring._collect_warnings(
        {"launch_concurrency": "high"}, "agentcore") == []


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
