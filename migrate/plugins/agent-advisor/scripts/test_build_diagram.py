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
