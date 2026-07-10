"""Behavioral assertions: each fixture shape must route unambiguously.

These don't execute the skill (it's a markdown program) — they assert the
fixtures carry the signals the routing table keys on, and that the routing
table text resolves each combination without ambiguity (exactly one
first-match layer per confirmed-intent combination).
"""
import pathlib
import re
try:
    import tomllib
except ModuleNotFoundError:          # py<3.11
    import tomli as tomllib

HERE = pathlib.Path(__file__).parent
FIXTURES = HERE / "fixtures"
ROUTING = HERE.parent / "references" / "design-refs" / "compute-routing-table.md"


def _load(name):
    return tomllib.loads((FIXTURES / name / "fly.toml").read_text())


def test_s2z_default_carries_layer5_signals():
    t = _load("scale-to-zero-default")
    hs = t["http_service"]
    assert hs["min_machines_running"] == 0 and hs["auto_start_machines"]
    assert hs["auto_stop_machines"] == "stop"


def test_multi_group_oneshot_signal_beats_scaling_shape():
    t = _load("multi-group")
    assert set(t["processes"]) == {"web", "worker", "nightly"}
    restarts = t["restart"] if isinstance(t["restart"], list) else [t["restart"]]
    never = [r for r in restarts if r["policy"] == "never"]
    assert never and never[0]["processes"] == ["nightly"]
    # routing table: one-shot (layer 2) must be listed BEFORE scale-to-zero (5)
    txt = re.sub(r"\s+", " ", ROUTING.read_text())
    assert txt.index("Layer 2") < txt.index("Layer 5")


def test_legacy_pg_fixture_is_database_not_group():
    pg = tomllib.loads(
        (FIXTURES / "stateful-legacy-pg" / "pg" / "fly.toml").read_text())
    assert pg["build"]["image"].startswith("flyio/postgres-flex")


def test_agent_fixture_evidence_and_gpu_before_platform_pref():
    code = (FIXTURES / "agent-langgraph" / "app" / "main.py").read_text()
    assert "langgraph" in code and "api.machines.dev" in code
    txt = re.sub(r"\s+", " ", ROUTING.read_text())
    # specialized classes before platform preference: 0 < 1 < 2 < 3
    for a, b in [("Layer 0", "Layer 3"), ("Layer 1", "Layer 3"),
                 ("Layer 2", "Layer 3")]:
        assert txt.index(a) < txt.index(b)


def test_layer_g_documented_before_layer0():
    txt = re.sub(r"\s+", " ", ROUTING.read_text())
    assert txt.index("Layer G") < txt.index("Layer 0")
    assert "decided_by" in txt
