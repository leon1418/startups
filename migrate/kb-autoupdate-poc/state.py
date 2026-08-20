"""Run-state for the pipeline: `last_seen` per source, plus queued dashboard requests.

Design §2.3 puts run-state in AWS, not git — it is rewritten every week even when nothing
changed, and a weekly "bumped last_seen" commit would be pure noise. Design §5.3 makes the
state **opaque per source**: RSS can select by date, but an HTML changelog often cannot and can
only remember "the first entry I saw last time". Forcing a timestamp would make the second
source type compromise, so the store keeps whatever blob the adapter hands it.

DynamoDB when a table is configured, a local JSON file otherwise, so the POC runs with no AWS
footprint at all.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

TABLE_ENV = "KB_STATE_TABLE"
LOCAL_PATH = Path(os.environ.get("KB_STATE_FILE", ".kb-state.json"))

# The state table exists in exactly ONE region. Inheriting AWS_REGION from the caller's shell
# means a developer whose default is elsewhere silently talks to a table that does not exist
# there — or, worse, to a different table with the same name. KB_REGION pins it; AWS_REGION is
# only a fallback.
def _region() -> str:
    return os.environ.get("KB_REGION") or os.environ.get("AWS_REGION") or "us-east-1"


_ddb = None


def _table():
    """Return the DynamoDB table, or None when running locally."""
    global _ddb
    name = os.environ.get(TABLE_ENV)
    if not name:
        return None
    if _ddb is None:
        import boto3

        _ddb = boto3.resource("dynamodb", region_name=_region())
    return _ddb.Table(name)


def backend() -> str:
    name = os.environ.get(TABLE_ENV)
    return f"dynamodb:{name}@{_region()}" if name else f"local:{LOCAL_PATH}"


# ── local file ────────────────────────────────────────────────────────────────────────
def _read_local() -> dict:
    if not LOCAL_PATH.exists():
        return {}
    try:
        return json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_local(d: dict) -> None:
    LOCAL_PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


# ── public API ────────────────────────────────────────────────────────────────────────
def get(key: str, default: Any = None) -> Any:
    t = _table()
    if t is None:
        return _read_local().get(key, default)
    item = t.get_item(Key={"pk": key}).get("Item")
    return json.loads(item["value"]) if item else default


def put(key: str, value: Any) -> None:
    t = _table()
    if t is None:
        d = _read_local()
        d[key] = value
        _write_local(d)
        return
    t.put_item(Item={"pk": key, "value": json.dumps(value, ensure_ascii=False)})


def get_seen(source_id: str) -> set[str]:
    """Item ids this source has already yielded.

    Ids rather than a cursor, because `published_at` may be absent (design §5.3) and because
    a feed can reorder or backfill. Bounded below so the set cannot grow without limit.
    """
    return set(get(f"seen:{source_id}", []) or [])


def put_seen(source_id: str, ids: set[str], keep: int = 5000, window: set[str] | None = None) -> None:
    """Persist the handled ids for one source, bounded.

    An id that is no longer in the source's current feed window is dead weight: the seen
    check only ever compares against fetched items, so dropping it changes nothing. When the
    caller knows the window, keep exactly the handled ids still inside it (self-cleaning, no
    arbitrary cap needed) plus a sorted tail of strays as a buffer for feeds that reorder or
    backfill. Without a window, fall back to a flat cap — set high, because `list(set)` is
    arbitrary order and truncating it used to evict ~540 random OpenAI ids every run, which
    were then re-triaged forever.
    """
    if window is not None:
        in_window = sorted(i for i in ids if i in window)
        strays = sorted(i for i in ids if i not in window)[-1000:]
        put(f"seen:{source_id}", in_window + strays)
        return
    put(f"seen:{source_id}", sorted(ids)[-keep:])


def take_requests(kind: str | None = None) -> list[dict]:
    """Pop the actions a human ticked on the dashboard (design §7.2).

    A tick is a request the next run consumes, not a command executed on click — which is why
    the dashboard needs no API and no auth layer. Consumption is BY KIND: a consumer takes
    only the requests it knows how to act on, and everything else stays queued — draining the
    whole queue used to silently destroy requests that had no consumer yet.
    """
    reqs = get("requests", []) or []
    if kind is None:
        taken, rest = reqs, []
    else:
        taken = [r for r in reqs if r.get("kind") == kind]
        rest = [r for r in reqs if r.get("kind") != kind]
    if reqs:
        put("requests", rest)
    return taken


def add_request(kind: str, **payload: Any) -> None:
    reqs = get("requests", []) or []
    reqs.append({"kind": kind, **payload})
    put("requests", reqs)


def record_run(summary: dict) -> None:
    """Stamp the run so the dashboard shows when the pipeline actually ran.

    Without this the dashboard can only show its own render time, which says nothing about
    whether the pipeline is alive.
    """
    from datetime import datetime, timezone

    entry = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), **summary}
    prev = get("last_run") or {}
    # Phases run in sequence within one job; merge so a later phase does not erase an earlier
    # phase's numbers from the same run.
    if prev.get("at", "")[:13] == entry["at"][:13]:
        entry = {**prev, **entry}
    put("last_run", entry)
    history = get("run_history", []) or []
    history.append(entry)
    put("run_history", history[-30:])
