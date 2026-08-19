"""Step Functions pipeline — the one Lambda behind every state.

One container image, one function; the state machine passes {"stage": ...} and each stage is
a separate, visible state. The image holds only the runtime (python deps, git, gh): the
pipeline scripts are shallow-cloned from the branch AT INVOKE TIME, which preserves the
push-is-deploy property the CodeBuild version had — changing pipeline code never requires an
image rebuild.

Stages and their contracts (each returns a small JSON the state machine can route on):

  recheck   -> {runId, summary, counts}
  scan      -> {runId, summary, counts, hasHits, hits: [{title}...capped], deferred}
  hit       -> {title, status: handled|judge_failed|apply_failed, pr}
  finalize  -> {summary}; RAISES if any hit apply_failed (execution FAILED -> SNS), after
               the dashboard refresh so the dashboard is never stale on a failed run
  bootstrap -> {summary}

Stage handoff is the S3 run archive itself (runs/<runId>/): every stage downloads what
exists and uploads what it produced — archiving is no longer a separate step that can be
skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

import boto3

CODE = "/tmp/code"
WORK = "/tmp/work"
POC_REL = "migrate/kb-autoupdate-poc"

_token: str | None = None


def sh(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    shown = " ".join(cmd[:4])
    print(f"$ {shown}  -> rc={r.returncode}")
    if r.stdout:
        print(r.stdout[-6000:])
    if r.stderr:
        print(r.stderr[-3000:])
    if check and r.returncode != 0:
        raise RuntimeError(f"{shown} failed rc={r.returncode}")
    return r


def github_token() -> str:
    global _token
    if _token is None:
        sm = boto3.client("secretsmanager")
        _token = sm.get_secret_value(SecretId=os.environ["KB_TOKEN_SECRET"])["SecretString"]
    return _token


def poc() -> str:
    return os.path.join(CODE, POC_REL)


def prepare(need_work: bool = False) -> None:
    """Fresh clones per invoke — warm containers keep /tmp, so tear down first."""
    os.environ["HOME"] = "/tmp"  # git and gh both need a writable HOME in Lambda
    os.environ.setdefault("GH_CONFIG_DIR", "/tmp/.gh")
    os.environ["GITHUB_TOKEN"] = github_token()
    auth_url = os.environ["KB_REPO_URL"].replace("https://", f"https://x-access-token:{github_token()}@")

    shutil.rmtree(CODE, ignore_errors=True)
    sh(["git", "clone", "--depth", "1", "--branch", os.environ["KB_REPO_BRANCH"], auth_url, CODE])
    # The repo carries example results as committed POC evidence — a stage must never mistake
    # them for this run's output.
    sh(["bash", "-c", "rm -f results-*.json *.pr-body.md"], cwd=poc())

    if need_work:
        shutil.rmtree(WORK, ignore_errors=True)
        sh(["git", "clone", "--depth", "1", "--branch", os.environ["KB_PR_BASE"], auth_url, WORK])
        sh(["git", "-C", WORK, "config", "user.name", "kb-autoupdate[bot]"])
        sh(["git", "-C", WORK, "config", "user.email", "kb-autoupdate@users.noreply.github.com"])


def s3c():
    return boto3.client("s3")


def download_run(run_id: str) -> None:
    bucket = os.environ["KB_EVIDENCE_BUCKET"]
    resp = s3c().list_objects_v2(Bucket=bucket, Prefix=f"runs/{run_id}/")
    for o in resp.get("Contents", []):
        name = o["Key"].rsplit("/", 1)[-1]
        if name:
            s3c().download_file(bucket, o["Key"], os.path.join(poc(), name))


def upload_run(run_id: str) -> None:
    bucket = os.environ["KB_EVIDENCE_BUCKET"]
    for f in sorted(os.listdir(poc())):
        if (f.startswith("results-") and f.endswith(".json")) or f.endswith(".pr-body.md"):
            s3c().upload_file(os.path.join(poc(), f), bucket, f"runs/{run_id}/{f}")


def pyrun(script: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return sh(["python", script, *args], cwd=poc(), check=check)


# ── stages ────────────────────────────────────────────────────────────────────────────
def stage_recheck(event: dict) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    prepare()
    pyrun("recheck.py", "--out", "results-recheck.json")
    upload_run(run_id)
    counts = json.load(open(os.path.join(poc(), "results-recheck.json")))["counts"]
    return {"runId": run_id, "counts": counts,
            "summary": " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))}


def stage_scan(event: dict) -> dict:
    run_id = event["runId"]
    prepare()
    download_run(run_id)
    rc = pyrun("scan.py", "--out", "results-scan.json", check=False)
    if rc.returncode != 0:
        raise RuntimeError("scan failed — likely a coverage outage (all sources down)")
    upload_run(run_id)
    sc = json.load(open(os.path.join(poc(), "results-scan.json")))
    cap = int(os.environ.get("KB_MAX_JUDGE_PER_RUN", "3"))
    titles = [h["title"] for h in sc["hits"]]
    c = sc["counts"]
    return {
        "runId": run_id,
        "counts": c,
        "hasHits": bool(titles),
        "hits": [{"title": t, "runId": run_id} for t in titles[:cap]],
        "deferred": max(0, len(titles) - cap),
        "summary": f"{c.get('in', 0)} triaged · {c.get('hits', 0)} kept · {c.get('dropped', 0)} dropped"
                   + (f" · {len(titles) - cap} deferred" if len(titles) > cap else ""),
    }


def stage_hit(event: dict) -> dict:
    """judge -> apply -> mark-handled, with the exit-code contract:
    apply 0 = PR opened/updated, 3 = judged with nothing to apply (both mark handled);
    anything else leaves the item unhandled so it retries next run."""
    run_id, title = event["runId"], event["title"]
    prepare(need_work=True)
    download_run(run_id)
    out = "results-judge-" + hashlib.sha1(title.encode()).hexdigest()[:10] + ".json"

    if pyrun("judge.py", "--hit", title, "--out", out, check=False).returncode != 0:
        upload_run(run_id)
        return {"title": title, "status": "judge_failed"}

    rc = pyrun(
        "apply.py", "--judge", out, "--repo", WORK,
        "--commit", "--push", "--draft-pr", "--run-id", run_id,
        "--base", os.environ["KB_PR_BASE"], "--from-ref", "origin/" + os.environ["KB_PR_BASE"],
        "--remote", "origin", "--pr-repo", os.environ["KB_PR_REPO"],
        check=False,
    ).returncode
    upload_run(run_id)

    if rc in (0, 3):
        pyrun("scan.py", "--mark-handled", title, check=False)
        result = json.load(open(os.path.join(poc(), out)))
        return {"title": title, "status": "handled",
                "pr": (result.get("pr") or {}).get("url"),
                "issue": (result.get("review_issue") or {}).get("url")}
    return {"title": title, "status": "apply_failed", "rc": rc}


def stage_finalize(event: dict) -> dict:
    run_id = event["runId"]
    results = event.get("hitResults") or []
    prepare(need_work=True)  # decisions.py applies maintainer-approved edits
    download_run(run_id)
    # Maintainer decisions run BEFORE the dashboard refresh, so a just-closed brief or a
    # just-opened decision PR is already reflected in what the dashboard shows.
    pyrun("decisions.py", "--repo", WORK, "--pr-repo", os.environ["KB_PR_REPO"],
          "--base", os.environ["KB_PR_BASE"], check=False)
    pyrun("dashboard_issue.py", "--repo-for-issue", os.environ["KB_DASHBOARD_REPO"],
          "--briefs-repo", os.environ["KB_PR_REPO"], check=False)
    upload_run(run_id)  # archives results-decisions.json + results-briefs.json with the run

    handled = [r for r in results if r.get("status") == "handled"]
    failed = [r for r in results if r.get("status") == "apply_failed"]
    judge_failed = [r for r in results if r.get("status") == "judge_failed"]
    prs = [r["pr"] for r in handled if r.get("pr")]
    briefs = [r["issue"] for r in handled if r.get("issue")]
    dec = {}
    try:
        dec = json.load(open(os.path.join(poc(), "results-decisions.json")))
    except Exception:  # noqa: BLE001
        pass
    summary = (f"{len(handled)} handled ({len(prs)} PR{'s' if len(prs) != 1 else ''}"
               + (f", {len(briefs)} review brief{'s' if len(briefs) != 1 else ''}" if briefs else "") + ")"
               + (f" · {dec['executed']} decision{'s' if dec['executed'] != 1 else ''} executed" if dec.get("executed") else "")
               + (f" · {dec['waiting']} brief{'s' if dec['waiting'] != 1 else ''} awaiting a human" if dec.get("waiting") else "")
               + (f" · {len(judge_failed)} judge-failed (will retry)" if judge_failed else "")
               + (f" · {len(failed)} APPLY FAILED" if failed else ""))
    if failed:
        # After the dashboard refresh, so a failed run never leaves a stale dashboard.
        raise RuntimeError(f"{len(failed)} apply step(s) failed: "
                           + "; ".join(r["title"][:60] for r in failed))
    return {"summary": summary, "prs": prs, "briefs": briefs}


def stage_bootstrap(event: dict) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ") + "-bootstrap"
    prepare()
    pyrun("bootstrap_facts.py", "--apply", "--out", "results-bootstrap.json")
    upload_run(run_id)
    props = json.load(open(os.path.join(poc(), "results-bootstrap.json")))["proposals"]
    return {"runId": run_id,
            "summary": f"{len(props)} proposals ({sum(1 for p in props if p.get('enabled'))} auto-enabled)"}


STAGES = {
    "recheck": stage_recheck,
    "scan": stage_scan,
    "hit": stage_hit,
    "finalize": stage_finalize,
    "bootstrap": stage_bootstrap,
}


def handler(event, context):
    stage = event.get("stage")
    print(f"stage={stage} event={json.dumps({k: v for k, v in event.items() if k != 'hitResults'})[:400]}")
    return STAGES[stage](event)
