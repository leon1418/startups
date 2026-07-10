"""Content lock for fly-to-aws decision references.

These tables are the deterministic core of the skill. Tests pin the
load-bearing content (layer order, guard semantics, forbidden targets,
GPU sunset date, MicroVM constraints) so wording edits cannot silently
change routing behavior. Matching is whitespace-normalized.
"""
import pathlib
import re

REFS = pathlib.Path(__file__).parent.parent / "references" / "design-refs"
ROUTING = REFS / "compute-routing-table.md"


def _norm(p):
    return re.sub(r"\s+", " ", p.read_text())


def test_routing_file_exists():
    assert ROUTING.exists()


def test_layer_order_and_first_match():
    t = _norm(ROUTING)
    # Layers appear in G,0,1,2,3,4,5 order; specialized before platform preference
    idx = [t.index(m) for m in [
        "Layer G", "Layer 0", "Layer 1", "Layer 2",
        "Layer 3", "Layer 4", "Layer 5"]]
    assert idx == sorted(idx)
    assert "first match wins" in t


def test_layer_g_guard_locks_advisor_verdict():
    t = _norm(ROUTING)
    assert 'decided_by == "agent-advisor"' in t
    assert "Skip layers 0" in t


def test_layer0_advisor_candidates_and_code_interpreter_rule():
    t = _norm(ROUTING)
    assert "agentcore / ecs / eks / lambda / lambda_microvms" in t
    assert "Code Interpreter is NOT a runtime candidate" in t


def test_gpu_layer_before_platform_preference():
    t = _norm(ROUTING)
    assert "a10 → g5" in t and "l40s → g6e" in t
    assert "a100-40gb → p4d" in t and "a100-80gb → p4de" in t
    assert "2026-08-01" in t
    assert "Fargate has no GPU" in t


def test_scale_to_zero_three_way_and_microvm_constraints():
    t = _norm(ROUTING)
    assert "ARM64" in t and "8 h" in t and "5 TPS" in t
    assert "inherited default" in t.lower() or "Inherited default" in t
    assert "min_machines_running applies to the primary region only" in t


def test_forbidden_targets_only_in_prohibition_context():
    t = _norm(ROUTING)
    # The footer MUST name them — but only inside the "Never route to" section
    assert "Never route to" in t
    never_idx = t.index("Never route to")
    for target in ["App Runner", "Copilot", "Elastic Beanstalk"]:
        first = t.index(target)
        assert first >= never_idx, (
            f"{target} appears before the prohibition footer — "
            "it must never appear as a route/recommendation")


PRESETS = REFS / "machine-preset-table.md"
POSTGRES = REFS / "postgres-table.md"
VOLUMES = REFS / "volumes-decision.md"


def test_preset_table_anchors():
    t = _norm(PRESETS)
    for preset in ["shared-cpu-1x", "shared-cpu-8x", "performance-1x",
                   "performance-16x"]:
        assert preset in t
    assert "0.25 vCPU" in t          # Fargate smallest mapping
    assert "burstable" in t          # shared ≈ burstable economics note


def test_postgres_plans_and_targets():
    t = _norm(POSTGRES)
    for plan in ["$38", "$72", "$282", "$962", "$1,922"]:
        assert plan in t
    assert "db.t4g.micro" in t
    assert "Aurora Serverless v2" in t and "min 0 ACU" in t
    assert "RDS Proxy prevents pausing" in t
    assert "not able to provide support or guidance for unmanaged Postgres" in t


def test_volumes_honest_three_way():
    t = _norm(VOLUMES)
    assert "de-volume" in t
    assert "per-task scratch" in t          # Fargate+EBS honesty
    assert "deleted on task stop" in t or "deleted on task termination" in t
    assert "always provision at least two" in t  # Fly's own warning
    assert "EFS" in t and "NFS latency" in t
    assert "durability upgrade" in t


FASTPATH = REFS / "fast-path-table.md"
NETWORK = REFS / "network-table.md"


def test_fast_path_rows():
    t = _norm(FASTPATH)
    assert "Tigris" in t and "AWS_ENDPOINT_URL_S3" in t
    assert "ElastiCache Serverless" in t and "Valkey" in t
    assert "Redis-protocol client" in t     # Upstash HTTP client rewrite flag
    assert "specialist" in t.lower()        # unknown-extension gate
    assert "discontinued" in t.lower()      # Supabase ext


def test_network_table_v1_boundary():
    t = _norm(NETWORK)
    assert "fly-replay" in t
    assert "decision records + specialist gates only" in t
    assert "never generates rewrite code or multi-region infrastructure" in t
    assert "Global Accelerator" in t
    assert "SSM Parameter Store" in t
    assert "cannot be exported" in t        # fly secrets hard fact
    assert "SIGINT" in t                    # kill_signal delta
