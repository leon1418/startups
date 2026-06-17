import mantle


def test_strips_geo_prefix_and_date_suffix():
    assert mantle.to_mantle_candidate(
        "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    ) == "anthropic.claude-haiku-4-5"


def test_strips_eu_apac_global_prefixes():
    assert mantle.to_mantle_candidate("eu.anthropic.claude-opus-4-7") == "anthropic.claude-opus-4-7"
    assert mantle.to_mantle_candidate("apac.anthropic.claude-opus-4-8") == "anthropic.claude-opus-4-8"
    assert mantle.to_mantle_candidate("global.anthropic.claude-haiku-4-5") == "anthropic.claude-haiku-4-5"


def test_no_prefix_no_suffix_passthrough():
    assert mantle.to_mantle_candidate("anthropic.claude-haiku-4-5") == "anthropic.claude-haiku-4-5"


def test_strips_vN_suffix_without_date():
    assert mantle.to_mantle_candidate("amazon.nova-lite-v1:0") == "amazon.nova-lite"


def test_strips_bare_colon_inference_param():
    assert mantle.to_mantle_candidate("anthropic.claude-haiku-4-5:0") == "anthropic.claude-haiku-4-5"


CATALOG = ["anthropic.claude-haiku-4-5", "anthropic.claude-opus-4-8", "amazon.nova-lite"]


def test_match_hit_returns_mantle_id():
    assert mantle.match_in_catalog(
        "us.anthropic.claude-haiku-4-5-20251001-v1:0", CATALOG
    ) == "anthropic.claude-haiku-4-5"


def test_match_miss_returns_none():
    assert mantle.match_in_catalog(
        "us.anthropic.claude-sonnet-4-6-20250514-v1:0", CATALOG
    ) is None


def test_all_available_true_when_every_target_hits():
    targets = ["us.anthropic.claude-haiku-4-5-20251001-v1:0", "amazon.nova-lite-v1:0"]
    result = mantle.evaluate_targets(targets, CATALOG)
    assert result["all_available"] is True
    assert result["per_target"]["us.anthropic.claude-haiku-4-5-20251001-v1:0"] == "anthropic.claude-haiku-4-5"


def test_all_available_false_when_any_target_misses():
    targets = ["us.anthropic.claude-haiku-4-5-20251001-v1:0", "us.anthropic.claude-sonnet-4-6-20250514-v1:0"]
    result = mantle.evaluate_targets(targets, CATALOG)
    assert result["all_available"] is False
    assert result["per_target"]["us.anthropic.claude-sonnet-4-6-20250514-v1:0"] is None


def test_empty_catalog_means_none_available():
    result = mantle.evaluate_targets(["us.anthropic.claude-haiku-4-5"], [])
    assert result["all_available"] is False
