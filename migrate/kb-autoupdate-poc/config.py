"""Editable pipeline configuration: WHAT to recheck and WHAT to subscribe to.

Two kinds of config, deliberately separated from the knowledge itself:

  facts    - the hard conditions Monitor 1 re-verifies every run. Each carries its own
             source URL and a natural-language locate instruction.
  sources  - the feeds Monitor 2 subscribes to (AWS What's New, blogs, ...).

Why these are EDITABLE while the skill knowledge is PR-only: changing what we watch is an
operations decision, like last_seen — it does not change what the skill asserts. Changing
what the skill asserts stays behind a reviewed PR, always.

Storage: the same state store the pipeline already uses (DynamoDB in AWS, a local JSON file
otherwise), under `config:facts` / `config:sources`. First access seeds facts from the
committed facts.json and sources from built-in defaults, so the pipeline keeps working with
an empty table — and a UI edit takes effect on the very next run, no deploy needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import state

FACTS_KEY = "config:facts"
SOURCES_KEY = "config:sources"

# Both adapter types are live: `rss` for real feeds, `url-watch` for changelog pages
# without one (deterministic heading/date-line segmentation in scan.py; the OpenAI and
# Anthropic entries use those sites' own documented .md endpoints).
DEFAULT_SOURCES = [
    {
        "id": "aws-whats-new",
        "name": "AWS What's New",
        "type": "rss",
        "url": "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
        "enabled": True,
        "note": "~58 items/week; the feed holds only 100, so weekly polling is a floor, not a choice.",
    },
    {
        "id": "aws-news-blog",
        "name": "AWS News Blog",
        "type": "rss",
        "url": "https://aws.amazon.com/blogs/aws/feed/",
        "enabled": True,
        "note": "Narrative detail for launches; mostly redundant with What's New — enable if launch context is wanted.",
    },
    {
        "id": "openai-news",
        "name": "OpenAI News",
        "type": "rss",
        "url": "https://openai.com/news/rss.xml",
        "enabled": True,
        "note": "Real RSS exists. The API changelog (model retirements) does NOT — that needs url-watch.",
    },
    {
        "id": "openai-api-changelog",
        "name": "OpenAI API Changelog",
        "type": "url-watch",
        "url": "https://platform.openai.com/docs/changelog.md",
        "enabled": True,
        "note": "Model retirement dates live here. The .md endpoint is the page's own documented markdown variant — far more stable to parse than the HTML.",
    },
    {
        "id": "anthropic-release-notes",
        "name": "Anthropic Release Notes",
        "type": "url-watch",
        "url": "https://docs.claude.com/en/release-notes/api.md",
        "enabled": True,
        "note": "No RSS (verified: /rss.xml is 404). Mintlify serves a clean .md variant — one entry per full-date heading.",
    },
    {
        "id": "temporal-changelog",
        "name": "Temporal Changelog",
        "type": "url-watch",
        "url": "https://docs.temporal.io/changelog",
        "enabled": True,
        "note": "HTML only (no .md, no feed). Feature-status changes (e.g. Serverless Workers maturity) surface here.",
    },
]

SUPPORTED_TYPES = {"rss": "live", "url-watch": "live"}


# ── facts ─────────────────────────────────────────────────────────────────────────────
def get_facts() -> list[dict]:
    facts = state.get(FACTS_KEY)
    if facts is None:
        facts = _seed_facts()
    return facts


def put_facts(facts: list[dict]) -> None:
    for f in facts:
        _validate_fact(f)
    state.put(FACTS_KEY, facts)


def enabled_facts() -> list[dict]:
    return [f for f in get_facts() if f.get("enabled", True)]


def _seed_facts() -> list[dict]:
    """First run: adopt the committed facts.json as the initial config."""
    path = Path(__file__).parent / "facts.json"
    facts = []
    if path.exists():
        for f in json.loads(path.read_text(encoding="utf-8"))["facts"]:
            f.pop("_poc_expectation", None)
            f.setdefault("enabled", True)
            f.setdefault("origin", "seed")  # seed | bootstrap | user
            facts.append(f)
    state.put(FACTS_KEY, facts)
    return facts


def _validate_fact(f: dict) -> None:
    for k in ("key", "value", "recheck"):
        if not f.get(k):
            raise ValueError(f"fact missing required field {k!r}: {json.dumps(f)[:120]}")
    rc = f["recheck"]
    if not rc.get("url", "").startswith("http") or not rc.get("locate"):
        raise ValueError(f"fact {f['key']!r}: recheck needs an http(s) url and a locate instruction")


# ── sources ───────────────────────────────────────────────────────────────────────────
def get_sources() -> list[dict]:
    sources = state.get(SOURCES_KEY)
    if sources is None:
        sources = list(DEFAULT_SOURCES)
        state.put(SOURCES_KEY, sources)
    return sources


def put_sources(sources: list[dict]) -> None:
    for s in sources:
        _validate_source(s)
    state.put(SOURCES_KEY, sources)


def enabled_sources() -> list[dict]:
    """Sources the scan will actually poll: enabled AND of a live adapter type."""
    return [s for s in get_sources() if s.get("enabled") and SUPPORTED_TYPES.get(s.get("type")) == "live"]


def _validate_source(s: dict) -> None:
    if not s.get("id") or not s.get("url", "").startswith("http"):
        raise ValueError(f"source needs an id and an http(s) url: {json.dumps(s)[:120]}")
    if s.get("type") not in SUPPORTED_TYPES:
        raise ValueError(f"source {s['id']!r}: type must be one of {sorted(SUPPORTED_TYPES)}")
