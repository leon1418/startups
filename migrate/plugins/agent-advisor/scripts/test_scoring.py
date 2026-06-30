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
