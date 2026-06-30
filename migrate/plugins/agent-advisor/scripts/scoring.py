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
