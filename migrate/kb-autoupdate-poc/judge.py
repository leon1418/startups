#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "httpx", "beautifulsoup4", "lxml"]
# ///
"""POC judge — decide what an announcement means, and how far it reaches.

Two calls, because the scan proved one is not enough. The scan named agentcore.md,
lambda-microvms.md, poc-shapes.md and design-ref-agentic-to-agentcore.md for the runtime-
instances launch, but missed temporal.md and ecs.md — the two files whose CONCLUSIONS flip.
Those files are not "about AgentCore"; they make claims that depend on it. A one-line file
description cannot surface that, so blast radius has to come from searching real content
(design doc §6, option b).

  step 1  announcement + the scan's named files  ->  verdict, fact change, search terms
  step 2  grep those terms across the skills tree ->  which hits are real + before/after/why

Usage:  uv run judge.py --hit "runtime instances"          # substring match on the scan hit
        uv run judge.py --hit "temporal policies"          # the known false positive
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from _common import STRONG_MODEL, ask_json

# KB_SKILLS_ROOT points reads at a DIFFERENT checkout than the pipeline code — the GitHub
# Actions deployment judges against the PR-base tree (fork main) so reads and writes see
# the same skill content. Unset, reads come from the pipeline code's own tree.
SKILLS = (Path(os.environ["KB_SKILLS_ROOT"]) if os.environ.get("KB_SKILLS_ROOT")
          else Path(__file__).resolve().parents[1] / "plugins" / "migration-to-aws" / "skills")
SEARCH_EXT = {".md", ".json"}
SKIP_DIRS = {"vendored", "node_modules", ".pytest_cache", ".venv"}

STEP1_SYSTEM = """You are deciding what a vendor announcement (AWS, OpenAI, Anthropic,
Temporal, ...) means for a migration-advice skill. The announcement's source is stated —
judge it on its own vendor's terms.

Classify the change:
  value_change   - an existing fact keeps its shape, only its value moved (a price, a date, a number)
  schema_change  - the fact's SHAPE changed: a single value now splits by dimension, or a new axis
                   appeared. The old value may still be correct for one dimension.
  new_knowledge  - the skill has no record of this at all, and should
  no_change      - the announcement does not require editing anything
  needs_human    - the evidence is insufficient or ambiguous to classify confidently. Do NOT
                   fall back to no_change when you are unsure — no_change ends in silence,
                   which is the worst wrong answer. Say in `reasoning` exactly what is missing.

Be careful with schema_change. If an announcement adds a NEW option alongside an existing one,
the existing value is usually STILL CORRECT for the thing it described. Do not overwrite it.

Also: verify the announcement really concerns the files you were given. Word collisions happen
(for example "temporal policies" means time-based policies, not the Temporal.io workflow engine).
If a named file is a false positive, say so in false_positive_files.

Finally, list search terms whose occurrences ELSEWHERE in the skill may now be wrong. Include the
old value in every form it might be written (8h, 8 hrs, eight hours, 28800, over_8hr), plus the
capability words whose claims may be affected (GPU, session cap, worker host)."""

STEP1_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["value_change", "schema_change", "new_knowledge", "no_change", "needs_human"]},
        "summary": {"type": "string", "description": "At most 2 sentences."},
        "fact_key": {"type": "string", "description": "The fact this touches, e.g. agentcore.session_cap. Empty if none."},
        "old_value": {"type": "string", "description": "Terse — the value itself, not an essay."},
        "new_value": {"type": "string", "description": "For schema_change, express the dimensions explicitly. Terse."},
        "still_true": {"type": "string", "description": "What of the OLD value remains correct, and for what. One sentence. Empty if nothing."},
        "false_positive_files": {"type": "array", "items": {"type": "string"}},
        "search_terms": {"type": "array", "items": {"type": "string"}, "maxItems": 14},
        "reasoning": {"type": "string", "description": "At most 3 sentences."},
    },
    "required": ["verdict", "summary", "fact_key", "old_value", "new_value", "still_true", "false_positive_files", "search_terms", "reasoning"],
}

STEP2_SYSTEM = """You are computing the blast radius of a fact change across a migration-advice skill.

You get grep hits for search terms related to the change. For each hit decide whether it is
genuinely affected, and classify how:

  value        - states the old value and must be updated
  derived      - states a JUDGMENT or RECOMMENDATION that depended on the old value
  flipped      - a derived claim whose CONCLUSION reverses (the strongest category — call it out)
  unaffected   - mentions the term but is not affected

For every affected hit write before / after / why / evidence_quote. `why` must cite what in
the announcement justifies the rewrite — a reviewer has no other protection, because no CI
check can catch a badly reworded judgment. `evidence_quote` must be an EXACT verbatim fragment
copied from the announcement text that supports the change; it is checked mechanically against
the announcement, so paraphrasing gets the edit rejected. If you cannot quote such evidence,
mark the hit unaffected.

Do not invent line content. Quote `before` from the text you were given."""

STEP2_SCHEMA = {
    "type": "object",
    "properties": {
        "affected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["value", "derived", "flipped", "unaffected"]},
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "why": {"type": "string"},
                    "evidence_quote": {"type": "string", "description": "Verbatim fragment from the announcement; checked mechanically."},
                },
                "required": ["file", "line", "kind", "before", "after", "why", "evidence_quote"],
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["affected", "notes"],
}


BRIEF_SYSTEM = """A vendor announcement has REVERSED one or more of a migration skill's
recommendations. Reversals are not rewritten automatically: a capability new at GA may be
unproven, may carry a different cost structure, and may not apply to every workload type.
The maintainer decides the position; your job is to write the decision brief they decide from.

Be concrete and skeptical, and do not oversell the new capability:
  what_changed       - plain language, 2-3 sentences, no marketing wording
  decision_space     - the REAL options, including keeping the old recommendation for some
                       workloads. Each option names what adopting it depends on.
  proposed_position  - the single position you would recommend, stated so it could be pasted
                       into the skill after review
  assumptions        - every assumption the proposed position rests on: GA maturity, pricing,
                       regional availability, workload fit. Anything a maintainer should
                       verify before adopting. An unlisted assumption is a trap."""

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "what_changed": {"type": "string"},
        "decision_space": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "option": {"type": "string"},
                    "depends_on": {"type": "string"},
                },
                "required": ["option", "depends_on"],
            },
        },
        "proposed_position": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    },
    "required": ["what_changed", "decision_space", "proposed_position", "assumptions"],
}


def read_named_files(names: list[str]) -> str:
    out = []
    for name in names:
        for p in SKILLS.rglob(name):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            body = p.read_text(encoding="utf-8")
            rel = p.relative_to(SKILLS)
            numbered = "\n".join(f"{i}: {ln}" for i, ln in enumerate(body.splitlines(), 1))
            out.append(f"===== {rel} =====\n{numbered[:14000]}")
            break
    return "\n\n".join(out)


MIN_TERM_LEN = 4
PER_TERM_CAP = 40
TOTAL_CAP = 400


def grep(terms: list[str], per_term_cap: int = PER_TERM_CAP, total_cap: int = TOTAL_CAP) -> tuple[list[dict], list[str]]:
    """Candidate locations for a set of search terms, with GLOBAL caps.

    The first version capped hits per (file, term), which is not a bound at all: with ~500 files
    and 14 terms it allowed 175,000 candidates. A real run produced ~28,000 and therefore 936
    blast-radius batches — 936 strong-model calls for ONE announcement, most returning nothing.
    Specific terms ("8h session cap") stay small; generic ones ("GPU", "region") explode.

    So: skip terms too short to be discriminating, cap each term globally, cap the total, and
    prefer specific terms by searching longest-first. Returns (hits, notes) — every truncation is
    reported rather than applied silently.
    """
    notes: list[str] = []
    usable, skipped = [], []
    for t in terms:
        (usable if len(t.strip()) >= MIN_TERM_LEN else skipped).append(t.strip())
    if skipped:
        notes.append(f"terms too short to discriminate, skipped: {skipped}")

    # Longest first: the specific terms claim the budget before the generic ones.
    usable.sort(key=len, reverse=True)

    files = []
    for p in sorted(SKILLS.rglob("*")):
        if p.suffix in SEARCH_EXT and p.is_file() and not any(part in SKIP_DIRS for part in p.parts):
            try:
                files.append((str(p.relative_to(SKILLS)), p.read_text(encoding="utf-8").splitlines()))
            except Exception:  # noqa: BLE001
                continue

    hits: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for term in usable:
        if len(hits) >= total_cap:
            notes.append(f"total cap {total_cap} reached; terms not searched: {usable[usable.index(term):]}")
            break
        pat = re.compile(re.escape(term), re.I)
        n = 0
        for rel, lines in files:
            for i, ln in enumerate(lines, 1):
                if n >= per_term_cap or len(hits) >= total_cap:
                    break
                if pat.search(ln) and (rel, i) not in seen:
                    seen.add((rel, i))
                    hits.append({"file": rel, "line": i, "term": term, "text": ln.strip()[:400]})
                    n += 1
            if n >= per_term_cap:
                notes.append(f"term {term!r} hit its {per_term_cap}-location cap — probably too generic")
                break
    return hits, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hit", required=True, help="substring of the scan hit's title")
    ap.add_argument("--scan", default="results-scan.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    scan = json.load(open(args.scan, encoding="utf-8"))
    matches = [h for h in scan["hits"] if args.hit.lower() in h["title"].lower()]
    if not matches:
        print("no scan hit matches that substring. available:")
        for h in scan["hits"]:
            print("  -", h["title"])
        return 1
    hit = matches[0]
    out_path = args.out or ("results-judge-" + re.sub(r"[^a-z0-9]+", "-", args.hit.lower()).strip("-") + ".json")

    print(f"HIT   {hit['title']}")
    print(f"files {', '.join(hit['files'])}\n")

    # ---- step 1: what does it mean -----------------------------------------------------
    user1 = (
        f"ANNOUNCEMENT\nsource: {hit.get('source', 'unknown')}\ntitle: {hit['title']}\n"
        f"body: {hit['body']}\nurl: {hit['url']}\n\n"
        f"FILES THE SCAN NAMED\n{read_named_files(hit['files'])}"
    )
    step1 = ask_json(STRONG_MODEL, STEP1_SYSTEM, user1, STEP1_SCHEMA, max_tokens=16000)

    print(f"verdict      {step1['verdict']}")
    print(f"fact         {step1['fact_key'] or '(none)'}")
    print(f"old -> new   {step1['old_value']!r} -> {step1['new_value']!r}")
    if step1["still_true"]:
        print(f"still true   {step1['still_true']}")
    if step1["false_positive_files"]:
        print(f"FALSE POS    {', '.join(step1['false_positive_files'])}")
    print(f"search       {', '.join(step1['search_terms'][:12])}")

    if step1["verdict"] in ("no_change", "needs_human"):
        json.dump({"hit": hit, "step1": step1, "step2": None}, open(out_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        if step1["verdict"] == "needs_human":
            print(f"\nNEEDS A HUMAN — insufficient evidence to classify: {step1['reasoning'][:160]}")
            print(f"  ->  {out_path}")
        else:
            print(f"\nno change required  ->  {out_path}")
        return 0

    # ---- step 2: how far does it reach -------------------------------------------------
    # Batched: one call with ~190 candidates makes the model abandon structured output
    # entirely (it answers {"params": {}}). Batching also mirrors what has to happen once
    # the tree no longer fits one context.
    hits, grep_notes = grep(step1["search_terms"])
    print(f"\ngrep         {len(hits)} candidate locations across the skills tree")
    for n in grep_notes:
        print(f"  note: {n}")

    change_ctx = (
        f"ANNOUNCEMENT\n{hit['title']}\n{hit['body']}\n\n"
        f"THE CHANGE\nfact: {step1['fact_key']}\nold: {step1['old_value']}\nnew: {step1['new_value']}\n"
        f"still true: {step1['still_true']}\n\n"
    )
    BATCH, MAX_BATCHES = 30, 16
    batches = [hits[i : i + BATCH] for i in range(0, len(hits), BATCH)]
    merged: list[dict] = []
    notes: list[str] = list(grep_notes)
    if len(batches) > MAX_BATCHES:
        notes.append(f"blast radius truncated: {len(batches)} batches needed, {MAX_BATCHES} run — {len(hits) - MAX_BATCHES * BATCH} candidates unexamined")
        print(f"  note: {notes[-1]}")
        batches = batches[:MAX_BATCHES]
    for bi, batch in enumerate(batches, 1):
        listing = "\n".join(f"{h['file']}:{h['line']}  [{h['term']}]  {h['text']}" for h in batch)
        user2 = change_ctx + f"GREP HITS — batch {bi} of {len(batches)} ({len(batch)} lines)\n{listing}"
        try:
            part = ask_json(STRONG_MODEL, STEP2_SYSTEM, user2, STEP2_SCHEMA, max_tokens=16000)
        except Exception as e:  # noqa: BLE001
            notes.append(f"batch {bi} failed: {e}")
            print(f"  batch {bi:>2}/{len(batches)}   FAILED  {str(e)[:80]}")
            continue
        # The model occasionally emits affected entries as strings rather than objects (seen
        # live: AttributeError on a str). Non-dict entries are discarded WITH a note — the
        # "confident wrong shape" defect class gets a code guard, not trust.
        raw = part.get("affected", [])
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:  # noqa: BLE001
                raw = []
        bad = sum(1 for a in raw if not isinstance(a, dict))
        if bad:
            notes.append(f"[b{bi}] {bad} non-object affected entries discarded")
        keep = [a for a in raw if isinstance(a, dict) and a.get("kind") != "unaffected"]
        # Mechanical citation check: the evidence_quote must actually appear in the
        # announcement. A paraphrase is exactly the failure mode this guards against —
        # a fluent justification grounded only in model prose.
        announcement = re.sub(r"\s+", " ", f"{hit['title']} {hit['body']}").lower()
        verified, rejected = [], []
        for a_ in keep:
            q = re.sub(r"\s+", " ", a_.get("evidence_quote", "")).strip().lower()
            (verified if q and q in announcement else rejected).append(a_)
        if rejected:
            notes.append(f"[b{bi}] {len(rejected)} edit(s) rejected: evidence_quote not found verbatim in the announcement")
            print(f"  batch {bi:>2}/{len(batches)}   REJECTED {len(rejected)} edit(s) — evidence quote not verbatim")
        merged.extend(verified)
        if part.get("notes"):
            notes.append(f"[b{bi}] {part['notes']}")
        print(f"  batch {bi:>2}/{len(batches)}   {len(verified)} affected")

    step2 = {"affected": merged, "notes": " ".join(notes)}
    affected = list(step2["affected"])
    flipped = [a for a in affected if a["kind"] == "flipped"]

    # ---- step 3: the decision brief, only when a conclusion reversed --------------------
    # A flipped recommendation is not rewritten automatically — the maintainer decides the
    # position first (a capability new at GA may be unproven, differently priced, or a bad
    # fit for some workloads). This brief is what they decide from; apply.py turns it into
    # a review issue instead of a PR.
    brief = None
    if flipped:
        listing = "\n".join(f"- {a['file']}:{a['line']}  {a['before'][:200]}" for a in flipped)
        user3 = (
            f"ANNOUNCEMENT\n{hit['title']}\n{hit['body']}\n\n"
            f"THE CHANGE\nfact: {step1['fact_key']}\nold: {step1['old_value']}\nnew: {step1['new_value']}\n"
            f"still true: {step1['still_true']}\n\n"
            f"RECOMMENDATIONS THAT REVERSE ({len(flipped)})\n{listing}\n\n"
            f"OTHER AFFECTED LOCATIONS: {len(affected) - len(flipped)}"
        )
        try:
            brief = ask_json(STRONG_MODEL, BRIEF_SYSTEM, user3, BRIEF_SCHEMA, max_tokens=8000)
            print(f"\nbrief        position: {brief['proposed_position'][:120]}")
        except Exception as e:  # noqa: BLE001
            # The issue still opens without the model-written sections — a thin brief beats
            # a silent rewrite of a reversed recommendation.
            step2["notes"] += f" brief generation failed: {e}"
            print(f"\nbrief        FAILED  {str(e)[:100]}")

    json.dump({"hit": hit, "step1": step1, "step2": step2, "brief": brief, "grep_count": len(hits)}, open(out_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"affected     {len(affected)} locations ({len(flipped)} flipped conclusions)  ->  {out_path}\n")
    for a in affected:
        tag = {"value": "VAL ", "derived": "DERV", "flipped": "FLIP"}[a["kind"]]
        print(f"  [{tag}] {a['file']}:{a['line']}")
        print(f"         before: {a['before'][:120]}")
        print(f"         after:  {a['after'][:120]}")
        print(f"         why:    {a['why'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
