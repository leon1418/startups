#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Apply a judge result to a repo and open a draft PR.

Two safety rules, both load-bearing:

1. **Only locations the judge named are touched.** Nothing is inferred here.
2. **The `before` text must actually be present** at (or near) the stated line before anything
   is written. The POC found that the judge quotes a *fragment* of long table rows rather than
   the whole line (12 of 13 `before` strings matched a full line; the 13th was a substring of a
   357-character row), so replacement is substring-based inside the located line — never a
   whole-line overwrite, and never a blind write.

Every skipped location is reported and lands in the PR body. A silent skip would let a
reviewer believe the change was complete.

Usage:
  uv run apply.py --judge results-judge-runtime-instances.json --repo /path/to/worktree
  uv run apply.py ... --commit
  uv run apply.py ... --commit --push --draft-pr --base main --remote origin
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

KIND_LABEL = {
    "flipped": "conclusion flips",
    "derived": "derived judgment",
    "value": "value",
}


def sh(cmd: list[str], cwd: Path, check: bool = True) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return (r.stdout or "").strip()


def remote_slug(repo: Path, remote: str) -> str:
    """owner/name for a git remote, however the URL is spelled."""
    url = sh(["git", "remote", "get-url", remote], repo, check=False)
    return re.sub(r"^.*github\.com[:/]", "", re.sub(r"\.git$", "", url)).strip("/")


def locate(lines: list[str], line_no: int, needle: str, window: int = 6) -> int | None:
    """Index of the line containing `needle`, preferring the stated line number.

    A small window absorbs the drift that appears when an earlier edit in the same file adds or
    removes a line. Beyond the window we refuse rather than guess.
    """
    needle = needle.strip()
    if not needle:
        return None
    idx = line_no - 1
    if 0 <= idx < len(lines) and needle in lines[idx]:
        return idx
    for d in range(1, window + 1):
        for j in (idx - d, idx + d):
            if 0 <= j < len(lines) and needle in lines[j]:
                return j
    return None


def apply_edits(repo: Path, skills_rel: str, affected: list[dict]) -> tuple[list[dict], list[dict]]:
    applied: list[dict] = []
    skipped: list[dict] = []

    # Group by file so each file is read and written once, and so line drift stays local.
    by_file: dict[str, list[dict]] = {}
    for a in affected:
        by_file.setdefault(a["file"], []).append(a)

    for rel, items in by_file.items():
        path = repo / skills_rel / rel
        if not path.exists():
            skipped.extend({**a, "skip_reason": "file not found"} for a in items)
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        newline = "\n" if text.endswith("\n") else ""

        # Bottom-up so earlier line numbers stay valid.
        for a in sorted(items, key=lambda x: -x["line"]):
            before, after = a["before"].strip(), a["after"].strip()
            if not before or not after:
                skipped.append({**a, "skip_reason": "empty before/after"})
                continue
            i = locate(lines, a["line"], before)
            if i is None:
                skipped.append({**a, "skip_reason": f"before-text not found at or near line {a['line']}"})
                continue
            if before == lines[i].strip():
                # Whole-line match: preserve the original indentation.
                indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
                lines[i] = indent + after
            else:
                # Fragment of a longer line (a table row): substitute in place.
                lines[i] = lines[i].replace(before, after, 1)
            applied.append({**a, "applied_line": i + 1})

        path.write_text("\n".join(lines) + newline, encoding="utf-8")

    return applied, skipped


def pr_body(judge: dict, applied: list[dict], skipped: list[dict], skills_rel: str) -> str:
    s1 = judge["step1"]
    hit = judge["hit"]
    fp = s1.get("false_positive_files") or []
    if isinstance(fp, str):
        fp = [fp]

    L: list[str] = []
    a = L.append
    a("> Opened by the knowledge auto-update pipeline. **Draft** — a human decides.")
    a("")
    a(f"## What changed upstream\n\n[{hit['title']}]({hit['url']})")
    a("")
    a(f"**Verdict: `{s1['verdict']}`** on `{s1['fact_key']}`")
    a("")
    a(f"- was — {s1['old_value']}")
    a(f"- now — {s1['new_value']}")
    if s1.get("still_true"):
        a("")
        a(f"> **Still true:** {s1['still_true']}")
        a(">")
        a("> This is why the old value is **not** simply overwritten.")
    a("")
    a("## Proposed edits")
    a("")
    a("Each row states its justification. No CI check can catch a badly reworded judgment, so the")
    a('"why" column is the only protection a reviewer has — please read it rather than the diff alone.')
    a("")
    order = {"flipped": 0, "derived": 1, "value": 2}
    for x in sorted(applied, key=lambda y: (order.get(y["kind"], 9), y["file"])):
        a(f"### `{x['file']}:{x['applied_line']}` — {KIND_LABEL.get(x['kind'], x['kind'])}")
        a("")
        a("```diff")
        a(f"- {x['before']}")
        a(f"+ {x['after']}")
        a("```")
        a("")
        a(f"**Why:** {x['why']}")
        if x.get("evidence_quote"):
            a("")
            a(f'**Evidence (verbatim from the announcement):** "{x["evidence_quote"]}"')
        a("")
    if skipped:
        a("## Not applied")
        a("")
        a("The pipeline proposed these and could not apply them safely. They are listed so this PR")
        a("is not mistaken for a complete change:")
        a("")
        for x in skipped:
            a(f"- `{x['file']}:{x['line']}` ({x['kind']}) — {x['skip_reason']}")
        a("")
    if fp:
        a("## Filter false positives")
        a("")
        a("The announcement scan flagged these files; the judge rejected them:")
        a("")
        for f in fp:
            a(f"- `{f}`")
        a("")
    a("## Known limits of this proposal")
    a("")
    a("- **Blast radius is not stable between runs.** Two runs of the same input returned 9 and 13")
    a("  locations and neither was a superset of the other, so this list may be incomplete.")
    a(f"- Paths are relative to `{skills_rel}`.")
    a("- The pipeline did not touch any file the judge did not name.")
    return "\n".join(L)


REVIEW_LABEL = "kb-needs-review"


def brief_key(judge: dict) -> str:
    """Stable dedup key: the fact for real changes, the item for unclassifiable ones."""
    return judge["step1"].get("fact_key") or "hit-" + hashlib.sha1(judge["hit"]["title"].encode()).hexdigest()[:10]


def review_issue_body(judge: dict) -> str:
    """The decision brief. A flipped recommendation is never rewritten by the pipeline —
    the maintainer decides the position here, and only then does a run do the typing."""
    s1, hit = judge["step1"], judge["hit"]
    affected = (judge.get("step2") or {}).get("affected", [])
    affected = [a for a in affected if isinstance(a, dict)]
    flipped = [a for a in affected if a.get("kind") == "flipped"]
    brief = judge.get("brief") or {}

    L: list[str] = []
    a = L.append
    if s1["verdict"] == "needs_human":
        a("> Opened by the knowledge auto-update pipeline. This announcement could **not be classified")
        a("> with confidence** — a human decides. Close this issue once it is handled.")
        a("")
        a(f"## What we saw\n\n[{hit['title']}]({hit['url']})")
        a("")
        a(f"## Why the pipeline stopped\n\n{s1.get('reasoning') or 'no reasoning recorded'}")
        a("")
        a(f"<!-- kb-autoupdate-brief:{brief_key(judge)} -->")
        return "\n".join(L)

    a("> Opened by the knowledge auto-update pipeline. A recommendation **reversed** — nothing was")
    a("> rewritten. The maintainer decides the position below; the pipeline then does the typing.")
    a("")
    a(f"## 1 · What changed\n\n[{hit['title']}]({hit['url']})")
    a("")
    a(f"- was — {s1['old_value']}")
    a(f"- now — {s1['new_value']}")
    if s1.get("still_true"):
        a(f"- still true — {s1['still_true']}")
    if brief.get("what_changed"):
        a("")
        a(brief["what_changed"])
    quotes = list(dict.fromkeys(x.get("evidence_quote", "") for x in flipped if x.get("evidence_quote")))
    if quotes:
        a("")
        for q in quotes[:4]:
            a(f'> "{q}"')
    a("")
    a("## 2 · Recommendations it affects")
    a("")
    a("| location | kind | current text |")
    a("| --- | --- | --- |")
    order = {"flipped": 0, "derived": 1, "value": 2}
    for x in sorted(affected, key=lambda y: (order.get(y.get("kind"), 9), y.get("file", ""))):
        cur = (x.get("before") or "").replace("|", "\\|")[:160]
        a(f"| `{x['file']}:{x['line']}` | {KIND_LABEL.get(x.get('kind'), x.get('kind'))} | {cur} |")
    a("")
    if brief.get("decision_space"):
        a("## 3 · The decision space")
        a("")
        for opt in brief["decision_space"]:
            a(f"- **{opt['option']}** — depends on: {opt['depends_on']}")
        a("")
    if brief.get("proposed_position"):
        a("## 4 · Proposed position")
        a("")
        a(f"> {brief['proposed_position']}")
        a("")
        if brief.get("assumptions"):
            a("**Assumptions to verify before adopting:**")
            a("")
            for x in brief["assumptions"]:
                a(f"- {x}")
            a("")
    else:
        a("_The model-written decision-space/position sections failed to generate; the facts above")
        a("still stand. See the run notes._")
        a("")
    a("## Decision — tick one; the next run acts on it")
    a("")
    a("- [ ] **Adopt the proposed position** — the pipeline rewrites the affected locations and opens a draft PR for review")
    a('- [ ] **Adopt with changes** — edit the "Proposed position" text above first, then tick this')
    a("- [ ] **Reject** — close this issue; nothing is rewritten")
    a("")
    a(f"<!-- kb-autoupdate-brief:{brief_key(judge)} -->")
    return "\n".join(L)


def upsert_review_issue(judge: dict, slug: str, body_path: Path, cwd: Path) -> str | None:
    """Create or update the review issue for this brief key. Returns the issue URL."""
    mark = f"<!-- kb-autoupdate-brief:{brief_key(judge)} -->"
    title = ("[needs review] " + (judge["step1"].get("fact_key") or judge["hit"]["title"][:60])
             + (" — could not classify" if judge["step1"]["verdict"] == "needs_human"
                else " — recommendation reversed"))

    sh(["gh", "label", "create", REVIEW_LABEL, "--repo", slug, "--color", "B60205",
        "--description", "kb-autoupdate: a human decides before anything is rewritten",
        "--force"], cwd, check=False)
    found = sh(["gh", "issue", "list", "--repo", slug, "--label", REVIEW_LABEL, "--state", "open",
                "--json", "number,body,url", "--limit", "50"], cwd, check=False)
    existing = [i for i in json.loads(found or "[]") if mark in (i.get("body") or "")]

    if existing:
        num, url = str(existing[0]["number"]), existing[0]["url"]
        # Editing a body notifies nobody — the comment is what reaches subscribers.
        sh(["gh", "issue", "edit", num, "--repo", slug, "--body-file", str(body_path)], cwd)
        sh(["gh", "issue", "comment", num, "--repo", slug, "--body",
            f"Updated by the pipeline: a new announcement reached the same brief.\n\n{judge['hit']['url']}"],
           cwd, check=False)
        print(f"updated review issue {url}")
        return url
    out = sh(["gh", "issue", "create", "--repo", slug, "--title", title,
              "--body-file", str(body_path), "--label", REVIEW_LABEL], cwd, check=False)
    m = re.search(r"https://github\.com/\S+/issues/\d+", out or "")
    if not m:
        # The label may not exist and may not be creatable on this repo. The issue matters
        # more than its label — create it bare rather than losing the brief.
        out = sh(["gh", "issue", "create", "--repo", slug, "--title", title,
                  "--body-file", str(body_path)], cwd, check=False)
        m = re.search(r"https://github\.com/\S+/issues/\d+", out or "")
    if m:
        print(f"created review issue {m.group(0)}")
    return m.group(0) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", required=True)
    ap.add_argument("--repo", required=True, help="repo root to edit (use a worktree)")
    ap.add_argument("--skills-rel", default="migrate/plugins/migration-to-aws/skills")
    ap.add_argument("--branch", default=None)
    ap.add_argument(
        "--from-ref",
        default=None,
        help="Create the branch from this ref instead of current HEAD. Required when the checkout "
        "sits on a branch carrying unrelated work — otherwise that work lands in the PR too.",
    )
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--draft-pr", action="store_true")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--base", default="main")
    ap.add_argument("--pr-repo", default=None, help="target repo for the PR, e.g. owner/name")
    ap.add_argument("--run-id", default=None, help="run archive id — embedded in review issues so decisions.py can find the judge result")
    ap.add_argument("--position-approved", action="store_true",
                    help="a maintainer approved the position on the review issue — apply flipped edits as a normal PR")
    args = ap.parse_args()

    # Exit codes are a contract with the build: 0 = durable action succeeded (PR opened or
    # updated, or a review issue opened or updated), 3 = judged but nothing to apply (benign —
    # the item counts as handled), anything else = a real failure and the item must RETRY.
    repo = Path(args.repo).resolve()
    judge = json.loads(Path(args.judge).read_text(encoding="utf-8"))
    affected = [a for a in (judge.get("step2") or {}).get("affected", []) if isinstance(a, dict)]

    # A reversed recommendation, or an unclassifiable announcement, is NOT rewritten: the
    # durable action is a review issue — the four-section decision brief — and the maintainer
    # decides the position before any run does the typing.
    flipped = [a for a in affected if a.get("kind") == "flipped"]
    if not args.position_approved and (judge["step1"]["verdict"] == "needs_human" or flipped):
        why = "could not classify" if judge["step1"]["verdict"] == "needs_human" else \
            f"{len(flipped)} conclusion{'s' if len(flipped) != 1 else ''} reversed"
        print(f"routing to a review issue, not a PR — {why}")
        body = review_issue_body(judge)
        if args.run_id:
            # Where decisions.py finds the judge result once a maintainer ticks a box.
            body += f"\n<!-- kb-autoupdate-run:{args.run_id}:{Path(args.judge).name} -->"
        body_path = Path(args.judge).resolve().with_suffix(".issue-body.md")
        body_path.write_text(body.rstrip("\n") + "\n", encoding="utf-8")
        if not args.draft_pr:
            print(f"(dry run — issue body written to {body_path.name})")
            return 0
        url = upsert_review_issue(judge, args.pr_repo or remote_slug(repo, args.remote), body_path, repo)
        judge["review_issue"] = {"url": url, "reason": why, "flipped": len(flipped)}
        Path(args.judge).write_text(json.dumps(judge, indent=2, ensure_ascii=False), encoding="utf-8")
        if not url:
            print("review issue creation did not yield a URL — failing so the item retries")
            return 1
        return 0

    if not affected:
        print("judge result has no affected locations — nothing to apply")
        return 3

    branch = args.branch or ("kb-autoupdate/" + judge["step1"]["fact_key"].replace(".", "-"))
    if args.commit:
        sh(["git", "checkout", "-B", branch] + ([args.from_ref] if args.from_ref else []), repo)
        print(f"branch    {branch}" + (f"  (from {args.from_ref})" if args.from_ref else ""))

    applied, skipped = apply_edits(repo, args.skills_rel, affected)
    print(f"applied   {len(applied)} / {len(affected)} locations")
    for x in applied:
        print(f"  ok    {x['file']}:{x['applied_line']}  [{x['kind']}]")
    for x in skipped:
        print(f"  SKIP  {x['file']}:{x['line']}  {x['skip_reason']}")

    # Written OUTSIDE the target repo: a stray .md inside it gets picked up by `lint:md`
    # (which scans all 806 files) and would be committed by `git add -A`.
    body = pr_body(judge, applied, skipped, args.skills_rel)
    body_path = Path(args.judge).resolve().with_suffix(".pr-body.md")
    body_path.write_text(body.rstrip("\n") + "\n", encoding="utf-8")

    title = f"fix(agent-advisor): {judge['step1']['fact_key']} — {judge['step1']['verdict'].replace('_', ' ')}"
    if not args.commit:
        print(f"\n(dry run — nothing committed. PR body written to {body_path.name})")
        return 0

    sh(["git", "add", "-A", args.skills_rel], repo)
    if not sh(["git", "diff", "--cached", "--name-only"], repo):
        # Every proposed edit was skipped (before-text gone). Deterministic: a retry would
        # skip identically, so this is handled-with-nothing-to-show, not a failure. The
        # skips are in the judge result and the dashboard.
        print("no changes staged — every edit was skipped; nothing to commit")
        return 3
    sh(["git", "commit", "-m", title, "-m", f"Source: {judge['hit']['url']}\n\nProposed by the knowledge auto-update pipeline; every edit's justification is in the PR body."], repo)
    print(f"commit    {sh(['git', 'rev-parse', '--short', 'HEAD'], repo)}")

    if args.push:
        # The lease value is stated EXPLICITLY. Bare --force-with-lease resolves the expected
        # value from the current branch's upstream, and `git push -u` only sets that upstream as
        # part of this very push — so at evaluation time there is none and git always rejects with
        # "(stale info)". Fetching a remote-tracking ref does not fix it either, for the same
        # reason. Asking the remote for its current sha and passing it as the lease keeps the real
        # protection (refuse if the branch moved under us) without ever degrading to a blind
        # --force. An empty expected value means "the branch must not exist yet".
        ls = sh(["git", "ls-remote", "--heads", args.remote, f"refs/heads/{branch}"], repo, check=False)
        remote_sha = ls.split()[0] if ls.split() else ""
        sh(["git", "push", "-u", args.remote, branch, f"--force-with-lease=refs/heads/{branch}:{remote_sha}"], repo)
        print(f"pushed    {args.remote}/{branch}" + (f"  (replaced {remote_sha[:8]})" if remote_sha else "  (new branch)"))

    pr_url = None
    if args.draft_pr:
        cmd = ["gh", "pr", "create", "--draft", "--title", title, "--body-file", str(body_path), "--base", args.base]
        if args.pr_repo:
            cmd += ["--repo", args.pr_repo]
            # `--head owner:branch` is the CROSS-repo form. When the branch was pushed to the
            # same repo the PR targets, gh wants a bare branch name; passing the qualified form
            # makes it look for a fork that does not exist.
            pushed_to = remote_slug(repo, args.remote)
            cmd += ["--head", branch if pushed_to == args.pr_repo else f"{pushed_to.split('/')[0]}:{branch}"]
        out = sh(cmd, repo, check=False)
        if "already exists" in out.lower() or not out.strip():
            # A re-run for the same fact updates the existing branch, so the PR is already open.
            # Report it rather than failing — the branch push above is the meaningful action.
            out = sh(["gh", "pr", "list", "--repo", args.pr_repo or remote_slug(repo, args.remote),
                      "--head", branch, "--state", "open", "--json", "url", "--jq", ".[0].url"], repo, check=False)
        m = re.search(r"https://github\.com/\S+/pull/\d+", out or "")
        pr_url = m.group(0) if m else None
        print("\n" + (pr_url or out or "(no PR URL returned)"))

    # The PR is the pipeline's primary product; a URL that lives only in a build log is
    # invisible to the dashboard. Write it back into the judge result so the archive carries it.
    judge["pr"] = {
        "url": pr_url,
        "branch": branch,
        "title": title,
        "applied": len(applied),
        "skipped": len(skipped),
        "commit": sh(["git", "rev-parse", "--short", "HEAD"], repo, check=False),
    }
    Path(args.judge).write_text(json.dumps(judge, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.draft_pr and not pr_url:
        # Branch pushed but no PR exists: the durable action did NOT complete. Fail so the
        # item retries — the re-run re-pushes the same branch and tries the PR again.
        print("PR creation did not yield a URL — failing so the item retries")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
