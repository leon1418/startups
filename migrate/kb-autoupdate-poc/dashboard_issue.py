#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3"]
# ///
"""The dashboard as a long-lived GitHub issue (design §7.2).

Renovate's Dependency Dashboard pattern: one issue, rewritten every run. Zero hosting, zero
auth layer — GitHub's permissions are the permissions — and it produces no commits, which is
what keeps run-state out of git.

The loop that makes checkboxes real:

  1. BEFORE rewriting, read the current body and find ticked boxes.
  2. Turn each into a queued request in the state store.
  3. Rewrite the body with the boxes reset.
  4. The next run's `state.take_requests()` consumes them.

So a tick is a request the next run acts on, not a command executed on click. That is the whole
reason no API and no authentication layer is needed.

Usage:
  uv run dashboard_issue.py --repo-for-issue owner/name          # create or update
  uv run dashboard_issue.py --repo-for-issue owner/name --print  # render only, touch nothing
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
from pathlib import Path

import state

TITLE = "Knowledge Auto-Update — Dashboard"
MARKER = "<!-- kb-autoupdate-dashboard -->"

TICK = re.compile(r"^- \[x\]\s+(.*?)\s*(?:<!--\s*(\{.*?\})\s*-->)?\s*$", re.I | re.M)


def gh(args: list[str], check: bool = True) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}\n{r.stderr}")
    return (r.stdout or "").strip()


def load(path: str, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def harvest_ticks(body: str) -> list[dict]:
    """Turn ticked checkboxes into queued requests.

    Each actionable line carries its payload in an HTML comment, so the request survives the
    label being reworded.
    """
    out = []
    for label, payload in TICK.findall(body or ""):
        if not payload:
            continue
        try:
            req = json.loads(payload)
        except json.JSONDecodeError:
            continue
        req["_label"] = label
        out.append(req)
    return out


def fetch_briefs(briefs_repo: str | None) -> list[dict]:
    """Open kb-needs-review issues — the briefs waiting on a maintainer's decision."""
    if not briefs_repo:
        return []
    out = gh(["issue", "list", "--repo", briefs_repo, "--label", "kb-needs-review",
              "--state", "open", "--json", "number,title,url,createdAt", "--limit", "50"],
             check=False)
    try:
        return json.loads(out or "[]")
    except json.JSONDecodeError:
        return []


def render(rc: dict, sc: dict, judges: list[dict], last_run: dict | None, briefs: list[dict] | None = None) -> str:
    facts = rc.get("results", [])
    fresh = [f for f in facts if f["status"] == "agree"]
    failed = [f for f in facts if f["status"] == "recheck_failed"]
    attention = [f for f in facts if f["status"] in ("changed", "needs_human")]
    pinned = [f for f in facts if f.get("pin")]
    c = sc.get("counts", {})

    L: list[str] = [MARKER, ""]
    a = L.append

    when = (last_run or {}).get("at", "not recorded")
    a(f"Last run **{when}** · state `{state.backend()}`")
    a("")
    a("Review happens in the pull requests. This issue is for what a PR list cannot show.")
    a("")

    a(f"## Facts — {len(facts)}")
    a("")
    a("| confirmed fresh | needs review | recheck failed | pinned |")
    a("| --- | --- | --- | --- |")
    a(f"| {len(fresh)} | {len(attention)} | {len(failed)} | {len(pinned)} |")
    a("")

    if briefs:
        a(f"## Waiting on a decision — {len(briefs)} review brief{'s' if len(briefs) != 1 else ''}")
        a("")
        a("A reversed recommendation (or an unclassifiable announcement) is never rewritten by")
        a("the pipeline. Each brief below waits for a maintainer to set the position; the next")
        a("run then does the typing.")
        a("")
        for b in briefs:
            a(f"- [#{b['number']} — {b['title']}]({b['url']}) · opened {str(b.get('createdAt', ''))[:10]}")
        a("")

    if failed or attention:
        a("<details open><summary>Needs a human</summary>")
        a("")
        a("| fact | stored | observed | status | source |")
        a("| --- | --- | --- | --- | --- |")
        for f in failed + attention:
            obs = f.get("observed_value") or f.get("error") or "—"
            a(f"| `{f['key']}` | {f['stored_value']} | {obs} | {f['status']} | [page]({f['url']}) |")
        a("")
        a("</details>")
        a("")

    if pinned:
        a("<details><summary>Pinned — a human verdict outranks the source</summary>")
        a("")
        a("| fact | ours | source said | since | lifts when |")
        a("| --- | --- | --- | --- | --- |")
        for f in pinned:
            p = f["pin"]
            lo = p.get("last_observed") or {}
            a(f"| `{f['key']}` | {f['stored_value']} | {lo.get('value', '—')} | {p.get('at')} | {p.get('lift_when')} |")
        a("")
        a("</details>")
        a("")

    a("<details><summary>All facts</summary>")
    a("")
    a("| fact | value | last confirmed | appears in |")
    a("| --- | --- | --- | --- |")
    for f in facts:
        a(f"| `{f['key']}` | {f.get('observed_value') or f['stored_value']} | {f.get('observed_at') or '—'} | {f['appears_in_count']} |")
    a("")
    a("</details>")
    a("")

    a("## This run's announcement scan")
    a("")
    a(f"`{c.get('fetched', 0)}` fetched · `{c.get('already_seen', 0)}` seen before · "
      f"`{c.get('in', 0)}` triaged → **{c.get('hits', 0)} kept**, {c.get('dropped', 0)} dropped")
    a("")
    for h in sc.get("hits", []):
        files = ", ".join(f"`{x}`" for x in h["files"]) or "_none named_"
        a(f"- [{h['title']}]({h['url']}) → {files}")
    a("")
    a("<details><summary>Dropped — check here if something was missed</summary>")
    a("")
    a("This list is the only place a false negative can surface. Tick an item to send it back "
      "into judgment on the next run.")
    a("")
    for d in sc.get("dropped", []):
        payload = json.dumps({"kind": "reexamine", "item_id": d["id"]}, separators=(",", ":"))
        a(f"- [ ] [{d['title']}]({d['url']}) — {d['reason']} <!-- {payload} -->")
    a("")
    a("</details>")
    a("")

    for j in judges:
        s1 = j["step1"]
        aff = (j.get("step2") or {}).get("affected", [])
        flips = [x for x in aff if x["kind"] == "flipped"]
        a(f"## Judged — {j['hit']['title']}")
        a("")
        a(f"`{s1['verdict']}` on `{s1['fact_key']}` · {len(aff)} locations · {len(flips)} conclusions flip")
        if s1.get("still_true"):
            a("")
            a(f"> **Still true:** {s1['still_true']}")
        a("")

    a("## Actions")
    a("")
    a("A tick is a request; the next run acts on it. To run right now instead: "
      "`aws codebuild start-build --project-name kb-autoupdate`. The re-examine boxes live "
      "in the Dropped fold above. Further actions (lifting a pin, skipping a run, a full "
      "re-verify) are deliberately NOT rendered until their consumers exist — a control that "
      "does nothing is worse than no control.")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-for-issue", help="owner/name — the FORK, not upstream (design §7.2)")
    ap.add_argument("--briefs-repo", default=None,
                    help="owner/name to list open kb-needs-review briefs from (usually the PR repo)")
    ap.add_argument("--print", action="store_true", help="render to stdout and change nothing")
    args = ap.parse_args()

    rc = load("results-recheck.json", {"results": []})
    sc = load("results-scan.json", {"counts": {}, "hits": [], "dropped": []})
    judges = [j for j in (load(p) for p in sorted(glob.glob("results-judge-*.json"))) if j]

    briefs = fetch_briefs(args.briefs_repo)
    # Archived with the run so the console can render the same list without GitHub access.
    Path("results-briefs.json").write_text(json.dumps({"briefs": briefs}, indent=2), encoding="utf-8")

    body = render(rc, sc, judges, state.get("last_run"), briefs)

    if args.print or not args.repo_for_issue:
        print(body)
        return 0

    repo = args.repo_for_issue
    found = gh(["issue", "list", "--repo", repo, "--search", TITLE, "--state", "open", "--json", "number,body", "--limit", "5"])
    issues = [i for i in json.loads(found or "[]") if MARKER in (i.get("body") or "")]

    if issues:
        num = str(issues[0]["number"])
        # Harvest first: rewriting the body would erase the ticks.
        reqs = harvest_ticks(issues[0].get("body") or "")
        for r in reqs:
            state.add_request(r.pop("kind"), **r)
        if reqs:
            print(f"queued {len(reqs)} request(s) from ticked boxes: {[r.get('_label', '')[:40] for r in reqs]}")
        tmp = Path("dashboard-issue-body.md")
        tmp.write_text(body, encoding="utf-8")
        gh(["issue", "edit", num, "--repo", repo, "--body-file", str(tmp)])
        print(f"updated issue #{num} in {repo}")
    else:
        tmp = Path("dashboard-issue-body.md")
        tmp.write_text(body, encoding="utf-8")
        url = gh(["issue", "create", "--repo", repo, "--title", TITLE, "--body-file", str(tmp)])
        print(f"created {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
