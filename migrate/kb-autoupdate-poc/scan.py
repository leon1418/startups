#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "httpx", "beautifulsoup4", "lxml", "defusedxml"]
# ///
"""POC monitor 2 — announcement scan.

Validates the design's second assumption: can the 27 existing reference files serve as the
relevance filter, with no separately maintained topic list?

The filter question is "does this announcement affect the content of any of these files?",
and the answer must NAME the files — so a hit arrives already localized.

Acceptance: the AgentCore runtime-instances item must be a hit naming agentcore.md (and
ideally temporal.md / ecs.md). Everything unrelated must be dropped. The false-positive
count is the number to watch.

Usage:  uv run scan.py [--limit N] [--out results-scan.json]
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_mod
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

# Feeds are third-party input: v2 registers vendor changelogs, not just this AWS one.
# defusedxml blocks XXE and billion-laughs, which stdlib ElementTree does not.
from defusedxml import ElementTree as ET

import config
import state
from _common import CHEAP_MODEL, ask_json

SKILLS = Path(__file__).resolve().parents[1] / "plugins" / "migration-to-aws" / "skills"
TOPIC_DIRS = [
    SKILLS / "agent-advisor" / "references" / "decision-refs",
    SKILLS / "gcp-to-aws" / "references" / "design-refs",
]

SYSTEM = """You triage one vendor announcement (AWS, OpenAI, Anthropic, Temporal, ...) against
a list of knowledge files belonging to a migration-advice skill. Each file holds the skill's
guidance on one topic. The announcement's source is stated — judge it on its own vendor's
terms, not as if everything were AWS.

Decide whether the announcement would require CHANGING the content of any listed file —
a limit, a price, a service status, an availability fact, or a recommendation those files state.

Be strict. Most announcements are irrelevant to any given skill. Reasons to drop:
- the service is not one these files reason about
- it is a console/UX change or minor feature that no listed file mentions
- it is a regional expansion AND no listed file makes a region- or availability-dependent
  claim about that service (availability facts the files DO state are in scope)
- it concerns a capability the files never take a position on

Reasons to keep:
- it changes a limit, price, quota, or maturity/status that a file states
- it adds or removes a capability that a file's recommendation depends on
- it launches something that belongs in a file's decision space

If you keep it, list ONLY the files that actually need review, most affected first."""

SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "files": {"type": "array", "items": {"type": "string"}, "description": "File names from the list; empty when relevant=false."},
        "reason": {"type": "string", "description": "One sentence."},
    },
    "required": ["relevant", "files", "reason"],
}


def topic_manifest() -> tuple[str, list[str]]:
    """Build the filter's material straight from the files — nothing hand-maintained."""
    lines, names = [], []
    for d in TOPIC_DIRS:
        for p in sorted(d.glob("*.md")):
            body = p.read_text(encoding="utf-8")
            heading = next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.startswith("# ")), p.stem)
            # First substantive prose line, as a one-line description of the topic.
            gist = ""
            for ln in body.splitlines():
                s = ln.strip()
                if s and not s.startswith(("#", ">", "|", "-", "*", "_")) and len(s) > 30:
                    gist = s
                    break
            names.append(p.name)
            lines.append(f"- {p.name} — {heading}. {gist[:220]}")
    return "\n".join(lines), names


def parse_feed(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    items = []
    for it in root.iter("item"):

        def t(tag: str) -> str:
            el = it.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""

        desc = re.sub(r"<[^>]+>", " ", t("description"))
        items.append(
            {
                "id": t("guid") or t("link"),
                "title": t("title"),
                "body": re.sub(r"\s+", " ", desc)[:1200],
                "url": t("link"),
                "published_at": t("pubDate") or None,
            }
        )
    return items


# ── the url-watch adapter ─────────────────────────────────────────────────────────────
# Changelog pages without a feed. Segmentation is DETERMINISTIC (headings / date lines),
# never a model: the seen-set dedupe keys on item ids, and a model extractor would churn
# titles between runs and resurface old entries as "new". Verified structures:
#   OpenAI   platform.openai.com/docs/changelog.md   — "## August, 2026" + "### Aug 13"
#   Anthropic docs.claude.com/en/release-notes/api.md — "### August 11, 2026"
#   Temporal docs.temporal.io/changelog (HTML)        — title line, then "August 7, 2026"
UA = {"User-Agent": "Mozilla/5.0 (compatible; kb-autoupdate/1.0)"}
URL_WATCH_CAP = 25  # newest entries per page; the seen set absorbs the rest over time

_MONTHS = {m[:3].lower(): i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_MONTH_RE = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_FULL_DATE = re.compile(rf"{_MONTH_RE}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)", re.I)
_DAY_ONLY = re.compile(rf"^{_MONTH_RE}\.?\s+(\d{{1,2}})$", re.I)
_MONTH_YEAR = re.compile(rf"^{_MONTH_RE},?\s+(20\d\d)$", re.I)


def _iso(mon: str, day: str, year: str) -> str:
    return f"{year}-{_MONTHS[mon[:3].lower()]:02d}-{int(day):02d}"


def _entry_item(source_id: str, page_url: str, date: str, title: str, body: str) -> dict:
    # Titles read better without markdown residue: flatten [text](url) links, drop bold marks.
    title = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
    title = re.sub(r"\*\*?", "", title)
    title = re.sub(r"\s+", " ", title).strip(" -–—:*•")[:160]
    body = re.sub(r"\s+", " ", body)[:1200]
    return {
        "id": hashlib.sha1(f"{source_id}|{date}|{title}|{body[:80]}".encode()).hexdigest(),
        "title": title,
        "body": body,
        "url": page_url,
        "published_at": date,
    }


def parse_changelog_md(md: str, page_url: str, source_id: str) -> list[dict]:
    """One item per date-bearing heading; a bare month-year heading only sets year context."""
    entries: list[dict] = []
    cur: dict | None = None
    year_hint: str | None = None

    def flush() -> None:
        nonlocal cur
        if cur and cur["lines"]:
            body = " ".join(cur["lines"])
            head = cur["head"]
            # a heading that is ONLY a date makes a useless title — promote the first
            # substantial body line instead
            title = head if len(head) >= 12 else next(
                (l.lstrip("-*• ") for l in cur["lines"] if len(l.lstrip("-*• ")) >= 25), head or body[:80])
            entries.append(_entry_item(source_id, page_url, cur["date"], title, body))
        cur = None

    for line in md.splitlines():
        h = re.match(r"^#{1,4}\s+(.*)", line)
        if h:
            text = h.group(1).strip()
            my = _MONTH_YEAR.match(text)
            if my:
                year_hint = my.group(2)
                flush()
                continue
            fd = _FULL_DATE.search(text)
            do = _DAY_ONLY.match(text)
            flush()
            if fd:
                date = _iso(fd.group(1), fd.group(2), fd.group(3))
            elif do and year_hint:
                date = _iso(do.group(1), do.group(2), year_hint)
            else:
                continue  # a non-entry heading (page title, section) — no open entry
            head = _FULL_DATE.sub("", _DAY_ONLY.sub("", text)).strip(" -–—:")
            cur = {"date": date, "head": head, "lines": []}
        elif cur is not None and line.strip():
            cur["lines"].append(line.strip())
    flush()
    return entries


def parse_changelog_html(raw: str, page_url: str, source_id: str) -> list[dict]:
    """Title line followed by a bare full-date line (the Temporal changelog shape)."""
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", "\n", txt)
    lines = [l.strip() for l in html_mod.unescape(txt).splitlines() if l.strip()]
    out = []
    for i, l in enumerate(lines):
        fd = _FULL_DATE.fullmatch(l)
        if not fd:
            continue
        date = _iso(fd.group(1), fd.group(2), fd.group(3))
        title = next(
            (lines[j] for j in range(i - 1, max(i - 4, -1), -1)
             if len(lines[j]) >= 20 and not _FULL_DATE.search(lines[j])),
            None,
        )
        if title:
            out.append(_entry_item(source_id, page_url, date, title, title))
    return out


def fetch_items(source: dict) -> list[dict]:
    """One item shape out, whatever the source format — the adapter contract."""
    r = httpx.get(source["url"], headers=UA, timeout=40, follow_redirects=True)
    r.raise_for_status()
    if source["type"] == "rss":
        return parse_feed(r.text)
    ct = r.headers.get("content-type", "")
    if "markdown" in ct or source["url"].endswith(".md"):
        return parse_changelog_md(r.text, source["url"], source["id"])[:URL_WATCH_CAP]
    return parse_changelog_html(r.text, source["url"], source["id"])[:URL_WATCH_CAP]


def triage(item: dict, manifest: str, names: list[str]) -> dict:
    user = (
        "KNOWLEDGE FILES\n" + manifest + "\n\n"
        "ANNOUNCEMENT\n"
        f"source: {item.get('source', 'unknown')}\n"
        f"title: {item['title']}\n"
        f"body: {item['body']}\n"
    )
    try:
        r = ask_json(CHEAP_MODEL, SYSTEM, user, SCHEMA, max_tokens=1024)
    except Exception as e:  # noqa: BLE001
        return item | {"relevant": None, "files": [], "reason": f"triage failed: {e}"}
    # Keep only names the model did not invent.
    files = [f for f in r.get("files", []) if f in names]
    return item | {"relevant": bool(r["relevant"]), "files": files, "reason": r["reason"]}


def collect_new_items(source: dict, ignore_seen: bool, requeue_ids: set[str]) -> tuple[list[dict], int, set[str]]:
    """One source's fresh items, per the adapter contract: dedupe by id, never by date."""
    items = fetch_items(source)
    for i in items:
        i["source"] = source["id"]
    seen = set() if ignore_seen else state.get_seen(source["id"])
    fresh = [i for i in items if i["id"] not in seen or i["id"] in requeue_ids]
    span = f"({items[-1]['published_at']}  ->  {items[0]['published_at']})" if items else ""
    print(f"  {source['id']}: {len(items)} items {span} -> {len(fresh)} new")
    return fresh, len(items), seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results-scan.json")
    ap.add_argument("--limit", type=int, default=0, help="triage only the first N items (0 = all)")
    ap.add_argument("--all", action="store_true", help="ignore last_seen and re-triage every item")
    ap.add_argument("--mark-handled", metavar="TITLE",
                    help="mark one scanned hit as handled (seen) — the build calls this after the hit's judge completed")
    args = ap.parse_args()

    if args.mark_handled:
        sc = json.load(open(args.out, encoding="utf-8"))
        matches = [h for h in sc["hits"] if args.mark_handled.lower() in h["title"].lower()]
        if not matches:
            print(f"mark-handled: no scanned hit matches {args.mark_handled!r}")
            return 1
        h = matches[0]
        state.put_seen(h["source"], set(state.get_seen(h["source"])) | {h["id"]})
        print(f"handled: {h['title'][:70]} -> seen({h['source']})")
        return 0

    manifest, names = topic_manifest()
    print(f"filter list: {len(names)} reference files")
    print(f"state:       {state.backend()}")

    # Sources come from the editable config store; only enabled ones with a live adapter run.
    # url-watch sources are registered but skipped until that adapter exists — say so, loudly,
    # because a silently-skipped source reads as "covered" when it is not.
    sources = config.enabled_sources()
    skipped_sources = [s for s in config.get_sources() if s.get("enabled") and s not in sources]
    print(f"sources:     {len(sources)} live ({', '.join(s['id'] for s in sources) or 'none'})")
    for s in skipped_sources:
        print(f"  NOTE: {s['id']} is enabled but type {s['type']!r} has no adapter yet — NOT scanned")

    # A dashboard request can put a previously dropped item back into play (design §7.2).
    requeue = {r["item_id"] for r in state.take_requests("reexamine")}
    if requeue:
        print(f"requeued:    {len(requeue)} item(s) a human asked to re-examine")

    items, fetched, seen_by_source, source_failures = [], 0, {}, []
    for s in sources:
        try:
            fresh, total, seen = collect_new_items(s, args.all, requeue)
        except Exception as e:  # noqa: BLE001 — one dead feed must not kill the whole scan
            print(f"  FAILED {s['id']}: {e}")
            source_failures.append({"id": s["id"], "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        items += fresh
        fetched += total
        seen_by_source[s["id"]] = seen

    # A dead input must not impersonate a quiet week: losing EVERY source is a monitoring
    # outage, so the run fails loudly (build FAILED -> SNS). Partial loss is recorded in the
    # result so the dashboard and console can show reduced coverage.
    if sources and len(source_failures) == len(sources):
        print(f"\nALL {len(sources)} sources failed — this is a coverage outage, not a quiet week.")
        return 1

    skipped = fetched - len(items)
    items = items[: args.limit] if args.limit else items
    print(f"new:         {len(items)} to triage ({skipped} already seen in a previous run)")
    if not items:
        print("\nnothing new this run — no PR, no issue, no commit.")
        state.record_run({"scan": {"fetched": fetched, "new": 0, "hits": 0}})
        # Write the (empty) result anyway: downstream steps and the archived run both expect this
        # file to exist, and "nothing new" is a result worth recording, not an absence.
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "sources": [s["id"] for s in sources],
                    "state_backend": state.backend(),
                    "counts": {"fetched": fetched, "in": 0, "already_seen": skipped, "hits": 0, "dropped": 0, "errors": 0},
                    "source_failures": source_failures,
                    "filter_files": names,
                    "hits": [],
                    "dropped": [],
                    "errors": [],
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        return 0

    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(lambda i: triage(i, manifest, names), items))

    hits = [r for r in results if r["relevant"]]
    dropped = [r for r in results if r["relevant"] is False]
    errors = [r for r in results if r["relevant"] is None]

    # Advance state PER SOURCE — and "seen" means HANDLED, not fetched. A dropped item is
    # handled by definition (the decision was: drop). A relevant hit is NOT marked here: the
    # build marks it via `scan.py --mark-handled` only after its judge completed, so a
    # deferred hit, a crashed judge, or a build that died mid-run all come back on the next
    # run automatically. The feed's own ~100-item window (≈1.7 weeks) is the retry horizon.
    for sid, seen in seen_by_source.items():
        done = {r["id"] for r in results if r.get("source") == sid and r["relevant"] is False}
        state.put_seen(sid, seen | done)
    state.record_run({"scan": {"fetched": fetched, "new": len(results), "hits": len(hits), "dropped": len(dropped)}})

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "sources": [s["id"] for s in sources],
                "state_backend": state.backend(),
                "counts": {
                    "fetched": fetched,
                    "in": len(results),
                    "already_seen": skipped,
                    "hits": len(hits),
                    "dropped": len(dropped),
                    "errors": len(errors),
                },
                "source_failures": source_failures,
                "filter_files": names,
                "hits": hits,
                "dropped": dropped,
                "errors": errors,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n{len(results)} in  ->  {len(hits)} hits, {len(dropped)} dropped, {len(errors)} errors  ->  {args.out}\n")
    for h in hits:
        print(f"  HIT  {h['title'][:88]}")
        print(f"       files: {', '.join(h['files']) or '(none named)'}")
        print(f"       why:   {h['reason'][:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
