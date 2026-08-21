#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "httpx", "beautifulsoup4", "lxml"]
# ///
"""Act on maintainer decisions left on kb-needs-review issues.

The review issue is the human's half of the flipped contract: the pipeline never rewrites a
reversed recommendation on its own — it opens a four-section brief and waits. This script is
the machine's half. Each run it reads every open brief and:

  no box ticked          -> leaves it alone (still waiting on a human)
  Reject ticked          -> comments and closes; nothing is rewritten
  Adopt ticked           -> pulls the judge result from the run archive named in the issue,
                            applies the edits as a normal draft PR (--position-approved),
                            comments the PR link and closes the issue
  Adopt with changes     -> same, but the after-texts are regenerated first so they express
                            the position the maintainer EDITED, not the model's original

The human therefore holds both gates — direction (the issue) and execution (the PR review) —
and the machine only does the typing in between.

Usage:  uv run decisions.py --repo /path/to/worktree --pr-repo owner/name --base main [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import boto3

from _common import STRONG_MODEL, ask_json

REVIEW_LABEL = "kb-needs-review"
RUN_MARK = re.compile(r"<!-- kb-autoupdate-run:([^:>]+):([^:>]+) -->")

REWRITE_SYSTEM = """A maintainer reviewed a reversed recommendation and approved a POSITION —
possibly different from the one originally proposed. Rewrite each location's replacement text
so it expresses the approved position, and nothing beyond it.

Rules:
  - `after` must be a drop-in replacement for the shown current text: same register, similar
    length, valid for the surrounding markdown (a table fragment stays a table fragment).
  - Do not import claims that are not in the approved position or the announcement.
  - If a location cannot honestly be rewritten under the approved position, return it with
    after = "" and say why in notes — an omission with a reason beats an invented sentence."""

REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "after": {"type": "string"},
                },
                "required": ["file", "line", "after"],
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["edits", "notes"],
}


def gh(args_: list[str], check: bool = True) -> str:
    r = subprocess.run(["gh", *args_], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args_)}\n{r.stdout}\n{r.stderr}")
    return (r.stdout or "").strip()


def parse_decision(body: str) -> str | None:
    """adopt | adopt_with_changes | reject | None — from the ticked box."""
    for line in body.splitlines():
        m = re.match(r"-\s*\[[xX]\]\s*\*\*(.+?)\*\*", line.strip())
        if not m:
            continue
        label = m.group(1).lower()
        if label.startswith("adopt the"):
            return "adopt"
        if label.startswith("adopt with"):
            return "adopt_with_changes"
        if label.startswith("reject"):
            return "reject"
    return None


def extract_position(body: str) -> str:
    """The (possibly maintainer-edited) blockquote under '## 4 · Proposed position'."""
    lines = body.splitlines()
    out, active = [], False
    for ln in lines:
        if ln.strip().startswith("## 4"):
            active = True
            continue
        if active:
            if ln.startswith("## ") or ln.strip().startswith("**Assumptions"):
                break
            if ln.strip().startswith(">"):
                out.append(ln.strip().lstrip(">").strip())
    return " ".join(x for x in out if x)


def fetch_judge(run_id: str, fname: str) -> dict | None:
    # `decision-` prefix: this judge result belongs to ANOTHER run's archive. Without it the
    # file would match results-*.json and be re-uploaded into (and rendered as) THIS run.
    dst = Path("decision-" + fname)
    # KB_RUN_ARCHIVE: a local run-archive directory (the GitHub Actions deployment keeps
    # runs/<runId>/ on a state branch instead of in S3).
    local = os.environ.get("KB_RUN_ARCHIVE")
    if local:
        src = Path(local) / run_id / fname
        if not src.exists():
            print(f"  no judge result at {src}")
            return None
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return json.loads(dst.read_text(encoding="utf-8"))
    bucket = os.environ["KB_EVIDENCE_BUCKET"]
    try:
        boto3.client("s3").download_file(bucket, f"runs/{run_id}/{fname}", str(dst))
        return json.loads(dst.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  cannot fetch judge result runs/{run_id}/{fname}: {e}")
        return None


def regenerate_afters(judge: dict, position: str) -> None:
    """Rewrite flipped/derived after-texts to express the maintainer's edited position."""
    affected = [a for a in judge["step2"]["affected"] if isinstance(a, dict)]
    targets = [a for a in affected if a.get("kind") in ("flipped", "derived")]
    if not targets:
        return
    listing = "\n".join(f"{a['file']}:{a['line']}\n  current: {a['before']}" for a in targets)
    hit = judge["hit"]
    user = (
        f"ANNOUNCEMENT\n{hit['title']}\n{hit['body'][:6000]}\n\n"
        f"APPROVED POSITION\n{position}\n\n"
        f"LOCATIONS TO REWRITE ({len(targets)})\n{listing}"
    )
    result = ask_json(STRONG_MODEL, REWRITE_SYSTEM, user, REWRITE_SCHEMA, max_tokens=16000)
    by_loc = {(e["file"], e["line"]): e["after"] for e in result["edits"] if isinstance(e, dict)}
    kept, dropped = [], 0
    for a in affected:
        if a.get("kind") in ("flipped", "derived"):
            new_after = by_loc.get((a["file"], a["line"]), "")
            if not new_after.strip():
                dropped += 1
                continue
            a = {**a, "after": new_after, "why": f"maintainer-approved position: {position[:160]}"}
        kept.append(a)
    judge["step2"]["affected"] = kept
    note = f"after-texts regenerated for the maintainer-edited position; {dropped} location(s) dropped by the rewrite. {result.get('notes', '')}"
    judge["step2"]["notes"] = (judge["step2"].get("notes") or "") + " " + note
    print(f"  regenerated {len(by_loc)} after-text(s), dropped {dropped}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="work tree for edits (same as apply.py --repo)")
    ap.add_argument("--pr-repo", required=True)
    ap.add_argument("--base", default="main")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    found = gh(["issue", "list", "--repo", args.pr_repo, "--label", REVIEW_LABEL, "--state", "open",
                "--json", "number,body,url,title", "--limit", "50"], check=False)
    issues = json.loads(found or "[]")
    print(f"{len(issues)} open review brief(s)")

    acted, prs, waiting, failed = 0, [], 0, 0
    for issue in issues:
        num, body = str(issue["number"]), issue.get("body") or ""
        decision = parse_decision(body)
        if decision is None:
            waiting += 1
            continue
        print(f"#{num}  {issue['title'][:70]}  ->  {decision}")

        if decision == "reject":
            if not args.dry_run:
                gh(["issue", "comment", num, "--repo", args.pr_repo, "--body",
                    "Rejected by the maintainer — nothing was rewritten. Closing."], check=False)
                gh(["issue", "close", num, "--repo", args.pr_repo], check=False)
            acted += 1
            continue

        m = RUN_MARK.search(body)
        if not m:
            print("  no run marker in the issue body — cannot locate the judge result; leaving open")
            failed += 1
            continue
        judge = fetch_judge(m.group(1), m.group(2))
        if not judge:
            failed += 1
            continue

        if decision == "adopt_with_changes":
            position = extract_position(body)
            if not position:
                print("  'adopt with changes' ticked but no position text found — leaving open")
                failed += 1
                continue
            try:
                regenerate_afters(judge, position)
            except Exception as e:  # noqa: BLE001
                print(f"  rewrite failed: {e} — leaving open")
                failed += 1
                continue

        jf = Path("decision-" + m.group(2))
        jf.write_text(json.dumps(judge, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.dry_run:
            print("  (dry run — would apply and open a draft PR)")
            acted += 1
            continue

        rc = subprocess.run(
            [sys.executable, "apply.py", "--judge", str(jf), "--repo", args.repo,
             "--commit", "--push", "--draft-pr", "--position-approved",
             "--base", args.base, "--from-ref", f"{args.remote}/{args.base}",
             "--remote", args.remote, "--pr-repo", args.pr_repo],
        ).returncode
        pr_url = (json.loads(jf.read_text(encoding="utf-8")).get("pr") or {}).get("url")
        if rc == 0 and pr_url:
            gh(["issue", "comment", num, "--repo", args.pr_repo, "--body",
                f"Decision executed — draft PR opened for review: {pr_url}\n\n"
                "The PR is the second gate: nothing merges without a human."], check=False)
            gh(["issue", "close", num, "--repo", args.pr_repo], check=False)
            acted += 1
            prs.append(pr_url)
        else:
            gh(["issue", "comment", num, "--repo", args.pr_repo, "--body",
                f"The pipeline tried to execute this decision and failed (apply rc={rc}). "
                "The issue stays open; it will retry next run."], check=False)
            failed += 1

    print(f"decisions: {acted} executed ({len(prs)} PRs) · {waiting} waiting · {failed} failed")
    json.dump({"executed": acted, "prs": prs, "waiting": waiting, "failed": failed},
              open("results-decisions.json", "w", encoding="utf-8"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
