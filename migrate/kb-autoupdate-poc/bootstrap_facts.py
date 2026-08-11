#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "httpx", "beautifulsoup4", "lxml"]
# ///
"""Bootstrap the fact config by scanning the skill itself.

"The first time, generate a batch automatically by scanning the skill; the user edits from
there." This is that scan, in TWO passes:

  Pass 1 — declared facts (what the author said would change):
    runtimes/*.json      -> volatile_facts entries (already structured)
    decision-refs/*.md   -> "Hard limits" bullet sections
  Pass 2 — prose claims (what the author forgot to declare):
    every reference .md  -> typed factual claims extracted from free text
                            (prices, quotas, dates, GA/preview status, counts, model ids)

Pass 1 proposals may auto-enable (high confidence + verified URL); Pass 2 proposals NEVER
auto-enable — prose extraction is noisier, so a human flips each one on in the console
(origin="bootstrap-prose" marks them). Duplicate keys collapse toward the declared version.

Two honesty rules:
  * Proposals whose source URL does not answer 200 are marked unverified, not silently kept.
  * Nothing is written to the config unless --apply is passed; the default is a reviewable
    JSON on stdout/file. Auto-generated facts carry their origin so the UI can show which
    entries a human has not yet touched.

Usage:
  uv run bootstrap_facts.py                     # propose only, write bootstrap-facts.json
  uv run bootstrap_facts.py --apply             # merge NEW keys into the config store
  uv run bootstrap_facts.py --no-prose          # pass 1 only (the original behavior)
  uv run bootstrap_facts.py --prose-only        # pass 2 only
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

import config
from _common import STRONG_MODEL, ask_json

SKILLS = Path(__file__).resolve().parents[1] / "plugins" / "migration-to-aws" / "skills"

SYSTEM = """You turn a skill's volatile-fact declarations into monitorable fact records.

For each input fact, produce:
  key     - stable dotted id, e.g. agentcore.session_cap (keep the given one when sensible)
  value   - the CURRENT value exactly as the skill states it
  unit    - duration | price | status | count | text
  recheck.url    - the PUBLIC page where this value can be re-verified. Prefer official docs
                   (docs.aws.amazon.com quotas/limits pages, aws.amazon.com pricing pages,
                   vendor docs). NEVER invent a URL you are not confident exists.
  recheck.locate - a natural-language instruction a model can follow to find the ONE field on
                   that page ("in the table of ..., the row whose ... — read the ... column").
  confidence     - high | medium | low. LOW means you are unsure the URL or locate is right.

Skip facts that cannot be re-verified against a public page (internal conventions, opinions,
scoring weights). Only externally-checkable claims belong here."""

SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {"type": "string"},
                    "recheck": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}, "locate": {"type": "string"}},
                        "required": ["url", "locate"],
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "from": {"type": "string", "description": "which input line this came from"},
                },
                "required": ["key", "value", "recheck", "confidence"],
            },
        },
        "skipped": {"type": "array", "items": {"type": "string"}, "description": "inputs skipped and why"},
    },
    "required": ["facts", "skipped"],
}


# The same 27 files the announcement scan filters against: they ARE the skill's knowledge
# surface, so they bound what is worth monitoring — one boundary, used everywhere.
PROSE_DIRS = [
    SKILLS / "agent-advisor" / "references" / "decision-refs",
    SKILLS / "gcp-to-aws" / "references" / "design-refs",
]

SYSTEM_PROSE = """You extract monitorable factual claims from one file of a skill's reference
documentation.

Only claims of these TYPES qualify:
  price (number + currency) · quota/limit (number + unit) · date (GA/EOL/deprecation) ·
  status (preview/GA/deprecated/closed to new customers) · count (e.g. number of regions) ·
  model id (a concrete model identifier and its lifecycle)

Rules:
- The claim must be about the OUTSIDE world (AWS or a vendor), not about this skill itself.
- Specific values only. Skip fuzzy claims ("most regions", "approximately", "typically").
- Skip opinions, recommendations, and derived judgments — only re-verifiable statements.
- At most 8 claims per file: pick the most volatile and load-bearing ones.
- key: stable dotted id prefixed by topic, e.g. fargate.per_vcpu_hour, bedrock.claude_sonnet_eol
- value: the CURRENT value exactly as the file states it
- unit: duration | price | status | count | date | text
- recheck.url: the PUBLIC page where this value can be re-verified. Prefer official docs.
  NEVER invent a URL you are not confident exists.
- recheck.locate: a natural-language instruction to find the ONE field on that page.
- confidence: high | medium | low. LOW means unsure the URL or locate is right."""


def harvest_prose() -> list[tuple[str, str]]:
    """(relative name, text) for every reference file in the knowledge surface."""
    out = []
    for d in PROSE_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            out.append((p.name, p.read_text(encoding="utf-8")[:14000]))
    return out


def propose_from_prose(files: list[tuple[str, str]]) -> tuple[list[dict], list[str]]:
    """One extraction call per file; a file with nothing extractable is normal, not an error."""
    proposals: list[dict] = []
    skipped: list[str] = []
    for name, text in files:
        try:
            r = ask_json(STRONG_MODEL, SYSTEM_PROSE,
                         f"FILE: {name}\n\n{text}", SCHEMA, max_tokens=8000)
        except Exception as e:  # noqa: BLE001 — one bad file must not kill the sweep
            skipped.append(f"{name}: extraction failed ({type(e).__name__})")
            continue
        for f in r["facts"]:
            f["from"] = f"{name}: {f.get('from', '')}"[:160]
        proposals += r["facts"]
        skipped += [f"{name}: {s}" for s in r["skipped"][:3]]
        print(f"  {name:<44} -> {len(r['facts'])} claim(s)")
    return proposals, skipped


def harvest() -> list[str]:
    """Collect the raw volatile-fact declarations from the skill tree."""
    lines: list[str] = []
    for p in sorted((SKILLS / "agent-advisor" / "references" / "runtimes").glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        for vf in data.get("volatile_facts", []):
            lines.append(f"{p.stem}.{vf['key']} = {json.dumps(vf.get('value'))}  (from {p.name})")
    for p in sorted((SKILLS / "agent-advisor" / "references" / "decision-refs").glob("*.md")):
        in_limits = False
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.startswith("## ") and "hard limit" in ln.lower():
                in_limits = True
                continue
            if ln.startswith("## "):
                in_limits = False
            if in_limits and ln.strip().startswith("- "):
                lines.append(f"{ln.strip()[2:]}  (from {p.name} Hard limits)")
    return lines


def verify_urls(facts: list[dict]) -> None:
    """A proposed source URL that 404s is worse than none — mark it, do not hide it."""
    for f in facts:
        url = f["recheck"]["url"]
        try:
            r = httpx.head(url, timeout=15, follow_redirects=True,
                           headers={"User-Agent": "Mozilla/5.0"})
            ok = r.status_code < 400
        except Exception:  # noqa: BLE001
            ok = False
        f["url_verified"] = ok
        if not ok:
            f["confidence"] = "low"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="merge NEW keys into the config store")
    ap.add_argument("--out", default="bootstrap-facts.json")
    ap.add_argument("--no-prose", action="store_true", help="pass 1 only (declared facts)")
    ap.add_argument("--prose-only", action="store_true", help="pass 2 only (prose claims)")
    args = ap.parse_args()

    proposals: list[dict] = []
    skipped: list[str] = []

    # ── pass 1: declared facts ─────────────────────────────────────────────────────────
    if not args.prose_only:
        raw = harvest()
        print(f"pass 1: {len(raw)} declared volatile facts")
        result = ask_json(STRONG_MODEL, SYSTEM, "INPUT FACTS:\n" + "\n".join(raw), SCHEMA, max_tokens=16000)
        for f in result["facts"]:
            f["origin"] = "bootstrap"
        proposals += result["facts"]
        skipped += result["skipped"]

    # ── pass 2: prose claims ───────────────────────────────────────────────────────────
    if not args.no_prose:
        files = harvest_prose()
        print(f"pass 2: extracting typed claims from {len(files)} reference files")
        prose, prose_skipped = propose_from_prose(files)
        # Duplicates collapse toward the declared version: pass 1 keys (and existing
        # registry keys) win, prose re-finding them is expected, not an error.
        seen_keys = {f["key"] for f in proposals} | {f["key"] for f in config.get_facts()}
        dup = [f for f in prose if f["key"] in seen_keys]
        prose = [f for f in prose if f["key"] not in seen_keys]
        if dup:
            print(f"  ({len(dup)} prose claim(s) duplicated a declared/registered key — dropped)")
        for f in prose:
            f["origin"] = "bootstrap-prose"
        proposals += prose
        skipped += prose_skipped

    verify_urls(proposals)

    for f in proposals:
        # Prose claims NEVER auto-enable: extraction from free text is noisier, so a human
        # flips each one on in the console.
        f["enabled"] = (f["origin"] == "bootstrap"
                        and f.get("confidence") == "high" and f.get("url_verified", False))
        f["appears_in"] = []
        f["pin"] = None

    # HTTP 200 proves the URL is reachable, not that the page supports the claim — a plausible
    # but semantically wrong official URL could auto-enable. So before a proposal may
    # auto-enable, it must pass the pipeline's own verifier: recheck the proposed record and
    # require an outright agree.
    import recheck as recheck_mod
    for f in proposals:
        if not f["enabled"]:
            continue
        r = recheck_mod.recheck_one(f)
        if r["status"] == "agree":
            f["auto_enable_check"] = "recheck agree"
        else:
            f["enabled"] = False
            f["auto_enable_check"] = f"demoted: recheck said {r['status']}"
            print(f"  auto-enable demoted ({r['status']}): {f['key']}")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"proposals": proposals, "skipped": skipped}, fh, indent=2, ensure_ascii=False)

    n_ok = sum(1 for f in proposals if f["enabled"])
    n_prose = sum(1 for f in proposals if f["origin"] == "bootstrap-prose")
    print(f"proposed {len(proposals)} facts ({n_ok} auto-enabled, {n_prose} prose claims awaiting review) -> {args.out}")
    for f in proposals:
        mark = "auto" if f["enabled"] else ("?url" if not f.get("url_verified") else f["confidence"])
        tag = " (prose)" if f["origin"] == "bootstrap-prose" else ""
        print(f"  [{mark:>4}] {f['key']:<44} {str(f['value'])[:40]}{tag}")
    if skipped:
        print("skipped:", "; ".join(skipped)[:400])

    if args.apply:
        existing = config.get_facts()
        known = {f["key"] for f in existing}
        new = [f for f in proposals if f["key"] not in known]
        config.put_facts(existing + new)
        print(f"\napplied: {len(new)} new fact(s) merged into the config "
              f"({len(proposals) - len(new)} already present, untouched)")
    else:
        print("\n(review the file, then re-run with --apply to merge new keys into the config)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
