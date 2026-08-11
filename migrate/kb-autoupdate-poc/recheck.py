#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "httpx", "beautifulsoup4", "lxml"]
# ///
"""POC monitor 1 — recheck.

Validates the design's riskiest assumption: given a source URL and a natural-language
`locate` instruction, can a model reliably re-extract the field and tell whether our
stored value still holds?

The acceptance case is `agentcore.session_cap`. The Quotas page still says 8 hrs, so the
verdict MUST be `agree` — even though AgentCore gained a 14-day option this month. That
belongs to the announcement scan, not here. A `changed` verdict on that fact means the
design's separation of the two monitors is not being honoured.

Usage:  uv run recheck.py [--out results-recheck.json]
"""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx

import config
import state
from _common import CHEAP_MODEL, ask_json, fetch

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

SYSTEM = """You re-verify one specific fact against the page it came from.

Rules:
- Only report a value you can actually see in the page text. Never infer or recall one.
- Judge equality by MEANING, not by string: "900 seconds" equals "15m"; "8 hrs" equals "8h";
  "$0.04048" equals "0.04048".
- UNITS: the stored value's unit is given to you. If the page states the same quantity in a
  DIFFERENT unit, convert it into the stored unit before comparing, and report
  observed_value IN THE STORED UNIT. Directions matter: a per-HOUR price is 3600x the
  per-SECOND price of the same charge; a per-1M-token price is 1000x the per-1K-token price.
  A unit mismatch is not a change in the fact.
- The page may describe several variants or options. Extract ONLY the one the locate
  instruction names. If the page has since added other variants, that is NOT a change to
  this field — ignore them.
- If the field is genuinely absent from the text, set found=false. Do not guess.

Verdicts:
  agree    - the page states a value equal in meaning to the stored value
  changed  - the page states a DIFFERENT value for this same field
  unclear  - the value is present but ambiguous, or you cannot tell whether it matches
  not_found- the field is not in the page text at all"""

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "observed_value": {"type": "string", "description": "Exactly as the page states it; empty when found=false."},
        "quote": {"type": "string", "description": "Verbatim sentence or table row containing it; empty when found=false."},
        "verdict": {"type": "string", "enum": ["agree", "changed", "unclear", "not_found"]},
        "reasoning": {"type": "string", "description": "One sentence."},
    },
    "required": ["found", "observed_value", "quote", "verdict", "reasoning"],
}


# ── the mcp verifier: a second, independent channel ──────────────────────────────────
# The primary verifier trusts ONE url. When it disagrees or fails (page moved, redesign,
# extraction miss), we ask AWS documentation AS A WHOLE the same question through the hosted
# AWS Knowledge MCP server and hand the reviewer a corroborating — or contradicting — value
# with its sources. agree results skip it: the primary channel is sufficient for agreement,
# and the second opinion exists to qualify disagreement, not to double every bill.
KNOWLEDGE_MCP = "https://knowledge-mcp.global.api.aws"


def mcp_search_docs(phrase: str, limit: int = 3) -> list[dict]:
    """One stateless JSON-RPC call to the hosted AWS Knowledge MCP server.

    The server is a public HTTPS MCP endpoint (Streamable HTTP, sessionless), so a plain
    POST works from CodeBuild — no local MCP process, no client SDK.
    """
    body = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "aws___search_documentation",
                   "arguments": {"search_phrase": phrase, "limit": limit}},
    }
    r = httpx.post(KNOWLEDGE_MCP, json=body, timeout=25,
                   headers={"Accept": "application/json, text/event-stream"})
    r.raise_for_status()
    if "text/event-stream" in r.headers.get("content-type", ""):
        data = next(l[5:].strip() for l in r.text.splitlines() if l.startswith("data:"))
        payload = json.loads(data)["result"]
    else:
        payload = r.json()["result"]
    if payload.get("isError"):
        raise RuntimeError(payload["content"][0]["text"][:200])
    return json.loads(payload["content"][0]["text"])["content"]["result"]


SO_SYSTEM = """You report what AWS documentation says about ONE specific field, from search
results. You do NOT judge or compare — you extract evidence.

Rules:
- Report ONLY values visible in the provided search results. Never infer or recall one.
- Each evidence record quotes the containing sentence or table row VERBATIM and names the
  source_url of the result it came from (each result's header shows its url). Quotes are
  checked mechanically against the cited result — a paraphrase gets the record rejected.
- If different results state different values for this field, report each distinct value as
  its own record and set state=conflicting.
- If the field is not present in any result, set state=insufficient with an empty list."""

SO_SCHEMA = {
    "type": "object",
    "properties": {
        "state": {"type": "string", "enum": ["found", "conflicting", "insufficient"]},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "observed_value": {"type": "string"},
                    "quote": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["observed_value", "quote", "source_url"],
            },
        },
    },
    "required": ["state", "evidence"],
}


def aws_docs_second_opinion(fact: dict) -> dict | None:
    """Independent evidence for a non-agree outcome — deliberately no verdict: in testing a
    compare-style second pass mislabelled an obvious mismatch, so its contract is evidence
    records (value + verbatim quote + attributed source), each validated in code against the
    result it cites. AWS docs only — non-AWS facts are outside this server's corpus."""
    if "aws.amazon.com" not in fact["recheck"]["url"]:
        return None
    phrase = (fact["key"].replace(".", " ").replace("_", " ") + " " + fact["recheck"]["locate"])[:200]
    try:
        hits = mcp_search_docs(phrase)
        by_url = {h["url"]: re.sub(r"\s+", " ", h.get("context", "")).lower() for h in hits[:3]}
        ctx = "\n\n".join(f"--- {h['title']} ({h['url']}) ---\n{h['context']}" for h in hits[:3])[:8000]
        if not ctx.strip():
            return {"source": "aws-knowledge-mcp", "state": "insufficient", "evidence": []}
        unit_suffix = " ({})".format(fact["unit"]) if fact.get("unit") else ""
        user = (
            "The field, as our registry stores it: {}{}\n".format(json.dumps(fact["value"]), unit_suffix)
            + "Locate instruction: {}\n\n".format(fact["recheck"]["locate"])
            + "--- AWS DOCUMENTATION SEARCH RESULTS ---\n" + ctx
        )
        r = ask_json(CHEAP_MODEL, SO_SYSTEM, user, SO_SCHEMA)
        verified, rejected = [], 0
        for ev in r["evidence"]:
            src_text = by_url.get(ev.get("source_url", ""))
            q = re.sub(r"\s+", " ", ev.get("quote", "")).strip().lower()
            if src_text and q and q in src_text:
                verified.append({"observed_value": ev["observed_value"],
                                 "quote": ev["quote"][:300], "source_url": ev["source_url"]})
            else:
                rejected += 1
        out = {"source": "aws-knowledge-mcp",
               "state": r["state"] if verified or r["state"] == "insufficient" else "insufficient",
               "evidence": verified}
        if rejected:
            out["note"] = f"{rejected} evidence record(s) rejected: quote not verbatim in its cited result"
        return out
    except Exception as e:  # noqa: BLE001 — a second opinion must never break the primary path
        return {"source": "aws-knowledge-mcp", "state": "insufficient", "evidence": [],
                "note": f"{type(e).__name__}: {e}"[:160]}


def _with_second_opinion(fact: dict, result: dict) -> dict:
    if result["status"] in ("changed", "needs_human", "recheck_failed", "pinned_conflict"):
        so = aws_docs_second_opinion(fact)
        if so:
            result["second_opinion"] = so
    return result


_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def magnitude_guard(stored: str, observed: str | None) -> str | None:
    """Return a warning when stored and observed differ by >=10x — usually a unit slip."""
    if not observed:
        return None
    s, o = _NUM.search(str(stored)), _NUM.search(str(observed))
    if not (s and o):
        return None
    try:
        sv, ov = abs(float(s.group())), abs(float(o.group()))
    except ValueError:
        return None
    if sv == 0 or ov == 0:
        return None
    ratio = max(sv, ov) / min(sv, ov)
    if ratio >= 10:
        return f"MAGNITUDE GUARD: observed differs from stored by {ratio:,.0f}x — likely a unit mismatch, not a change."
    return None


def recheck_one(fact: dict) -> dict:
    key = fact["key"]
    url = fact["recheck"]["url"]
    text, err = fetch(url)

    out = {
        "key": key,
        "stored_value": fact["value"],
        "unit": fact.get("unit"),
        "url": url,
        "locate": fact["recheck"]["locate"],
        "appears_in_count": len(fact.get("appears_in", [])),
        "pin": fact.get("pin"),
        "expectation": fact.get("_poc_expectation"),
    }

    if err:
        # A fetch failure must never masquerade as "unchanged" (design §4). The second
        # opinion matters most here: a moved page kills the primary channel entirely.
        return _with_second_opinion(fact, out | {"status": "recheck_failed", "error": err, "observed_value": None, "quote": None})

    unit_suffix = " ({})".format(fact["unit"]) if fact.get("unit") else ""
    user = (
        "Stored value we are re-verifying: {}{}\n".format(json.dumps(fact["value"]), unit_suffix)
        + "Locate instruction: {}\n\n".format(fact["recheck"]["locate"])
        + "--- PAGE TEXT ({}) ---\n{}".format(url, text)
    )
    try:
        r = ask_json(CHEAP_MODEL, SYSTEM, user, SCHEMA)
    except Exception as e:  # noqa: BLE001
        return out | {"status": "recheck_failed", "error": f"model: {e}", "observed_value": None, "quote": None}

    verdict = r["verdict"]
    status = {
        "agree": "agree",
        "changed": "changed",
        "unclear": "needs_human",
        "not_found": "recheck_failed",
    }[verdict]

    # Mechanical backstop for unit errors, added after POC run 1 wrote a per-SECOND Fargate
    # rate against a per-HOUR stored value and called it "changed". A genuine price or limit
    # change is almost never an order of magnitude; a unit slip almost always is. This does
    # not trust the model to have converted correctly.
    guard = magnitude_guard(fact["value"], r["observed_value"])
    if status == "changed" and guard:
        status, verdict = "needs_human", "changed_but_magnitude_suspect"
        r["reasoning"] = guard + " " + r["reasoning"]

    # A pin outranks any observation: report the conflict, never propose the edit (design §8).
    if status == "changed" and fact.get("pin"):
        status = "pinned_conflict"

    # Auto-edit is only allowed when the fact lives in exactly one place (design §6.1).
    action = "none"
    if status == "changed":
        action = "auto_edit" if out["appears_in_count"] == 1 else "route_to_human"
    elif status in ("needs_human", "recheck_failed", "pinned_conflict"):
        action = "route_to_human"

    return _with_second_opinion(fact, out | {
        "status": status,
        "model_verdict": verdict,
        # The point of the whole monitor: a structured timestamp the freshness footer can read,
        # instead of asking the model to police its own claim of having verified something.
        # Only set when the source actually confirmed the value this run.
        "observed_at": TODAY if status == "agree" else fact.get("observed_at"),
        "observed_value": r["observed_value"] or None,
        "quote": r["quote"] or None,
        "reasoning": r["reasoning"],
        "action": action,
        "error": None if status != "recheck_failed" else "field not found in page text",
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results-recheck.json")
    ap.add_argument("--facts", default=None, help="override: read facts from a JSON file instead of the config store")
    args = ap.parse_args()

    # Facts come from the editable config store (seeded from facts.json on first touch), so a
    # UI edit is live on the next run. --facts stays as a file-based escape hatch for tests.
    if args.facts:
        facts = json.loads(open(args.facts, encoding="utf-8").read())["facts"]
    else:
        facts = config.enabled_facts()
        disabled = len(config.get_facts()) - len(facts)
        if disabled:
            print(f"({disabled} fact(s) disabled in config — skipped)")
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(recheck_one, facts))

    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    state.record_run({"recheck": counts})

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"counts": counts, "results": results}, f, indent=2, ensure_ascii=False)

    print(f"{len(results)} facts rechecked  ->  {args.out}")
    for k, v in sorted(counts.items()):
        print(f"  {k:<16} {v}")
    print()
    for r in results:
        mark = {"agree": "OK  ", "changed": "DIFF", "pinned_conflict": "PIN ", "needs_human": "?   ", "recheck_failed": "FAIL"}[r["status"]]
        if r["status"] == "changed":
            mark = "DIFF"
        obs = r["observed_value"] or r.get("error") or ""
        print(f"  [{mark}] {r['key']:<40} stored={r['stored_value']!r:<26} observed={obs!r}")
        so = r.get("second_opinion")
        if so:
            if so.get("evidence"):
                ev = so["evidence"][0]
                what = f"[{so['state']}] docs say {ev['observed_value']!r} — {ev['quote'][:70]}"
            else:
                what = so.get("note") or so.get("state", "?")
            print(f"         2nd opinion ({so['source']}): {what}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
