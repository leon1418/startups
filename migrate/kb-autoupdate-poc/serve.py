#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3"]
# ///
"""Local operator console: run the pipeline, watch it, browse past runs.

Why local rather than hosted: the console needs a WRITE path (start a build that costs money),
and hosting that means answering "who may press this" — a Cognito user pool, a public endpoint,
an OAuth flow in the browser. Running as the operator, on loopback, makes AWS IAM the
authorization model and deletes that entire problem. The renderer and the API shapes are the same
ones a hosted version would use, so moving it behind API Gateway later is not a rewrite.

Security, because a localhost server with a POST route is reachable from any page the browser
visits:
  * binds 127.0.0.1 only
  * a random token is minted per process, embedded in the served HTML, and required on every /api
    call — a cross-site page cannot read it
  * Origin/Referer, when sent, must be this server

Usage:  uv run serve.py [--port 8799] [--no-open]
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import secrets
import subprocess
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import boto3

import state
from report import build_html, collect_local

PROJECT = "kb-autoupdate"
REGION = "us-east-1"
RESULT_KEYS = ("results-recheck", "results-scan", "results-judge")

# Hosted mode: the same server behind an ALB that has ALREADY authenticated the caller
# (Amazon Federate OIDC). Lambda runs many execution environments concurrently, so the CSRF
# token must be stable across them — it comes from the stack. Locally it stays per-process.
HOSTED = os.environ.get("KB_HOSTED") == "1"
PUBLIC_HOST = os.environ.get("KB_PUBLIC_HOST", "")
TOKEN = os.environ.get("KB_CONSOLE_TOKEN") or secrets.token_urlsafe(24)
_last_build: dict = {}
_lock = threading.Lock()


def caller_alias(headers) -> str:
    """Operator identity for the audit log.

    Hosted, the edge auth function verifies the Midway id_token (signature, iss, exp, aud)
    and asserts the alias in x-forwarded-user — after dropping any inbound copy of that
    header. The Function URL itself only accepts requests carrying the CloudFront origin
    secret, so this header cannot arrive from anywhere but our own edge function."""
    alias = headers.get("x-forwarded-user")
    if alias:
        return alias
    return "?" if HOSTED else "local"


def sfn():
    return boto3.client("stepfunctions", region_name=REGION)


def s3():
    return boto3.client("s3", region_name=REGION)


_outputs: dict | None = None


def stack_outputs() -> dict:
    global _outputs
    if _outputs is None:
        cf = boto3.client("cloudformation", region_name=REGION)
        try:
            outs = cf.describe_stacks(StackName=PROJECT)["Stacks"][0].get("Outputs", [])
            _outputs = {o["OutputKey"]: o["OutputValue"] for o in outs}
        except Exception:  # noqa: BLE001 — the console must still work with no stack deployed
            _outputs = {}
    return _outputs


def evidence_bucket() -> str | None:
    return stack_outputs().get("EvidenceBucketOut")


def adopt_pipeline_state() -> None:
    """Point the `state` module at the table the PIPELINE writes.

    Without this the console reads a local .kb-state.json while the deployed pipeline writes
    DynamoDB, so the header showed a "last run" that had nothing to do with the runs the console
    was starting — stale data that looks current is worse than no data.
    """
    table = stack_outputs().get("StateTableOut")
    if table:
        os.environ["KB_STATE_TABLE"] = table
        os.environ.setdefault("KB_REGION", REGION)


# ── run history in S3 ─────────────────────────────────────────────────────────────────
def _run_dt(run_id: str) -> datetime | None:
    try:
        return datetime.strptime(run_id, "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def pretty_run(run_id: str) -> str:
    d = _run_dt(run_id)
    return d.strftime("%Y-%m-%d %H:%M UTC") if d else run_id


def human_age(run_id: str) -> str:
    """"12 minutes ago" beats a bare timestamp for answering "is this current?"."""
    d = _run_dt(run_id)
    if not d:
        return ""
    secs = int((datetime.now(timezone.utc) - d).total_seconds())
    for limit, div, unit in ((3600, 60, "minute"), (86400, 3600, "hour"), (10**9, 86400, "day")):
        if secs < limit:
            n = max(secs // div, 0)
            return "just now" if n == 0 else f"{n} {unit}{'s' if n != 1 else ''} ago"
    return ""


def list_runs() -> list[str]:
    b = evidence_bucket()
    if not b:
        return []
    out, token = [], None
    while True:
        kw = {"Bucket": b, "Prefix": "runs/", "Delimiter": "/"}
        if token:
            kw["ContinuationToken"] = token
        r = s3().list_objects_v2(**kw)
        out += [p["Prefix"].split("/")[1] for p in r.get("CommonPrefixes", [])]
        if not r.get("IsTruncated"):
            break
        token = r.get("NextContinuationToken")
    return sorted(out, reverse=True)


def load_run(run_id: str) -> dict:
    """Reassemble one archived run into the renderer's input shape."""
    b = evidence_bucket()
    data: dict = {"recheck": None, "scan": None, "judges": []}
    if not b:
        return data
    for obj in s3().list_objects_v2(Bucket=b, Prefix=f"runs/{run_id}/").get("Contents", []):
        name = obj["Key"].rsplit("/", 1)[-1]
        if not name.endswith(".json") or not name.startswith(RESULT_KEYS):
            continue
        body = json.loads(s3().get_object(Bucket=b, Key=obj["Key"])["Body"].read())
        if name.startswith("results-recheck"):
            data["recheck"] = body
        elif name.startswith("results-scan"):
            data["scan"] = body
        else:
            data["judges"].append(body)
    return data


# ── build control ─────────────────────────────────────────────────────────────────────
def console_config() -> dict:
    """Everything the Configuration pane shows — now from the EDITABLE config store."""
    import config as cfg

    facts = cfg.get_facts()
    sources = cfg.get_sources()
    # Listed directly rather than importing scan.topic_manifest: scan.py pulls in httpx and
    # defusedxml, which this script's environment does not declare — the import raised, the
    # except swallowed it, and the pane confidently said "the 0 reference files".
    from pathlib import Path

    skills = Path(__file__).resolve().parents[1] / "plugins" / "migration-to-aws" / "skills"
    filter_files = sorted(
        p.name
        for d in (
            skills / "agent-advisor" / "references" / "decision-refs",
            skills / "gcp-to-aws" / "references" / "design-refs",
        )
        if d.is_dir()
        for p in d.glob("*.md")
    )
    if not filter_files:
        # Hosted: the skills tree is not in the Lambda package, so the list is baked in at
        # build time (filter-files.json, generated from the real tree by the packaging step).
        # It refreshes on console deploy — the authoritative list is still the tree itself.
        manifest = Path(__file__).resolve().parent / "filter-files.json"
        if manifest.exists():
            filter_files = json.loads(manifest.read_text(encoding="utf-8"))
    params = {}
    try:
        cf = boto3.client("cloudformation", region_name=REGION)
        for p in cf.describe_stacks(StackName=PROJECT)["Stacks"][0].get("Parameters", []):
            params[p["ParameterKey"]] = p.get("ParameterValue", "")
    except Exception:  # noqa: BLE001
        pass
    return {
        "facts": facts,
        "sources": sources,
        "filter_files": sorted(filter_files),
        "stack_params": dict(sorted(params.items())),
    }


def start_run(mode: str = "run") -> dict:
    """A run is a Step Functions execution now — each stage (and each judged hit) is a
    separately visible state, which is what CodeBuild's log-grepping never gave us."""
    machine = stack_outputs().get("StateMachineArnOut")
    if not machine:
        return {"error": "pipeline state machine not found — is the stack deployed?"}
    ex = sfn().start_execution(stateMachineArn=machine, input=json.dumps({"mode": mode}))
    with _lock:
        _last_build.clear()
        _last_build["id"] = ex["executionArn"]
    return {"buildId": ex["executionArn"], "status": "RUNNING"}


def _find_summary(obj):
    """LAST summary in document order: a state's output still carries earlier states'
    payloads (ResultPath accumulates), and the newest stage's summary is inserted last."""
    found = None
    if isinstance(obj, dict):
        if isinstance(obj.get("summary"), str):
            found = obj["summary"]
        for v in obj.values():
            s = _find_summary(v)
            if s:
                found = s
    return found


def progress(exec_arn: str | None) -> dict:
    with _lock:
        exec_arn = exec_arn or _last_build.get("id")
    if not exec_arn:
        return {"status": "IDLE", "stages": [], "log": [], "buildId": None}

    d = sfn().describe_execution(executionArn=exec_arn)
    hist = sfn().get_execution_history(executionArn=exec_arn, maxResults=500)["events"]

    stages: list[dict] = []
    log: list[str] = []

    def close(status: str, detail: str = "") -> None:
        for s in reversed(stages):
            if s["status"] == "running":
                s["status"] = status
                s["detail"] = detail[:200]
                if detail:
                    log.append(f"{s['name']}: {detail[:200]}")
                break

    for ev in hist:
        t = ev["type"]
        if t == "TaskStateEntered":
            name = ev["stateEnteredEventDetails"]["name"]
            if name != "Hit":  # inner Map task — the iteration marker covers it
                stages.append({"name": name, "status": "running", "detail": ""})
        elif t == "TaskStateExited":
            if ev["stateExitedEventDetails"]["name"] == "Hit":
                continue
            detail = ""
            try:
                detail = _find_summary(json.loads(ev["stateExitedEventDetails"].get("output", "{}"))) or ""
            except Exception:  # noqa: BLE001
                pass
            close("done", detail)
        elif t == "MapIterationStarted":
            i = ev["mapIterationStartedEventDetails"]["index"]
            stages.append({"name": f"hit {i + 1}", "status": "running", "detail": ""})
        elif t == "MapIterationSucceeded":
            close("done")
        elif t == "MapIterationFailed":
            close("failed")
        elif t == "ExecutionFailed":
            close("failed", ev.get("executionFailedEventDetails", {}).get("cause", "")[:200])
    return {"buildId": exec_arn, "status": d["status"], "stages": stages, "log": log[-24:]}


# ── http ──────────────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "kb-console"

    def log_message(self, fmt, *args):
        # Quieter than one line per poll. args[0] is NOT always a string: send_error() calls
        # log_error("code %d, message %s", code, message), so an int arrives here and a naive
        # substring test raises TypeError inside the request thread.
        first = str(args[0]) if args else ""
        if "/api/" not in first:
            super().log_message(fmt, *args)

    # -- helpers
    def _json(self, obj, code: int = 200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str):
        body = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # No third-party anything is loaded; say so.
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def _from_cloudfront(self) -> bool:
        """The public Function URL must only serve traffic that came through CloudFront
        (where the Midway gate lives). CloudFront attaches a secret origin header; a direct
        hit on the Function URL doesn't have it."""
        want = os.environ.get("KB_ORIGIN_SECRET", "")
        return not want or self.headers.get("x-origin-verify") == want

    def _authorized(self) -> bool:
        if self.headers.get("X-KB-Token") != TOKEN:
            return False
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if HOSTED:
            return not origin or bool(PUBLIC_HOST) and origin.startswith(f"https://{PUBLIC_HOST}")
        return not origin or origin.startswith(f"http://127.0.0.1:{self.server.server_address[1]}")

    # -- routes
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)

        # /healthz answers before the CloudFront-origin check: the Web Adapter's readiness
        # probe is local and carries no origin secret, and the route reveals nothing.
        if u.path == "/healthz":
            # Target-group health check: no token, no auth — it says "process up", nothing more.
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if not self._from_cloudfront():
            return self._json({"error": "forbidden"}, 403)

        if u.path == "/favicon.ico":
            # Browsers always ask; answering 404 produced a traceback via log_error.
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if u.path == "/":
            try:
                runs = list_runs()
            except Exception:  # noqa: BLE001
                runs = []
            asked = (q.get("run") or [None])[0]

            # Default to the newest ARCHIVED run, not the local files. A remote build writes its
            # results inside the container and uploads them in post_build, so the local files
            # belong to whatever was last run on this laptop — showing those while a remote build
            # is in flight makes old data look like the current run.
            run_id = asked or (runs[0] if runs else None)
            if run_id:
                data = load_run(run_id)
                newest = runs and run_id == runs[0]
                label = f"the {'newest completed' if newest else 'archived'} run, {pretty_run(run_id)}"
                age = f"({human_age(run_id)})" + ("" if newest else " — not the newest")
                last = {"at": run_id}
            else:
                data = collect_local()
                label = f"local result files in {os.path.basename(os.getcwd())}/"
                age = "(no archived run exists yet)"
                last = state.get("last_run")
            return self._html(
                build_html(
                    data,
                    last,
                    console={
                        "token": TOKEN,
                        "runs": runs,
                        "current": run_id,
                        "label": label,
                        "age": age,
                        "project": PROJECT,
                        "config": console_config(),
                    },
                    source=label,
                )
            )

        if u.path.startswith("/api/"):
            if not self._authorized():
                return self._json({"error": "unauthorized"}, 403)
            if u.path == "/api/progress":
                return self._json(progress((q.get("id") or [None])[0]))
            if u.path == "/api/runs":
                return self._json({"runs": list_runs()})
            if u.path == "/api/state":
                return self._json(collect_local())
            if u.path == "/api/config":
                return self._json(console_config())

        self.send_error(404)

    def _body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        u = urlparse(self.path)
        if not self._from_cloudfront():
            return self._json({"error": "forbidden"}, 403)
        if not u.path.startswith("/api/"):
            return self.send_error(404)
        if not self._authorized():
            return self._json({"error": "unauthorized"}, 403)

        # Every write action names its operator. Locally that is "local"; hosted it is the
        # Federate identity the ALB attached.
        print(f"AUDIT action={u.path} by={caller_alias(self.headers)}", flush=True)

        import config as cfg

        try:
            if u.path == "/api/execute":
                return self._json(start_run("run"))
            # Config writes go to the state store the pipeline reads — an edit here is live on
            # the next run. This edits WHAT IS WATCHED, never the skill's knowledge: that part
            # still only changes through a reviewed PR.
            if u.path == "/api/config/facts":
                cfg.put_facts(self._body_json()["facts"])
                return self._json({"ok": True, "facts": cfg.get_facts()})
            if u.path == "/api/config/sources":
                cfg.put_sources(self._body_json()["sources"])
                return self._json({"ok": True, "sources": cfg.get_sources()})
            if u.path == "/api/config/bootstrap":
                if HOSTED:
                    # The hosted runtime has no skills tree — the pipeline Lambda has both
                    # (it clones the branch). Start a bootstrap-mode execution; the UI polls it.
                    r = start_run("bootstrap")
                    if r.get("error"):
                        return self._json(r, 500)
                    return self._json({"ok": True, "remote": True, "buildId": r["buildId"]})
                # Long-running (model + URL checks) but the POC accepts a blocking call here.
                import subprocess as sp

                r = sp.run(["uv", "run", "bootstrap_facts.py", "--apply"],
                           capture_output=True, text=True, timeout=600)
                return self._json({"ok": r.returncode == 0,
                                   "log": (r.stdout + r.stderr).strip().splitlines()[-12:]})
        except ValueError as e:  # config validation — a user error, not a server error
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001 — surface it in the UI rather than a stack trace
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        self.send_error(404)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    if HOSTED:
        # Behind the Lambda Web Adapter: bind all interfaces on the adapter's port, no
        # browser, no port probing. Auth happened at the ALB; the token guard stays as CSRF
        # protection for the authenticated session.
        port = int(os.environ.get("PORT", "8080"))
        adopt_pipeline_state()
        srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        print(f"kb-console hosted on :{port} as {PUBLIC_HOST or '(host unset)'}", flush=True)
        srv.serve_forever()
        return 0

    # A stale console from an earlier session is the common case, and the bare
    # "OSError: [Errno 48] Address already in use" traceback says nothing useful. Try a few
    # ports, then name the process holding the first one.
    srv = None
    for port in range(args.port, args.port + 5):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            args.port = port
            break
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
            print(f"port {port} busy, trying {port + 1}")
    if srv is None:
        holder = subprocess.run(["lsof", "-nP", f"-iTCP:{args.port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
        print(f"no free port in {args.port}-{args.port + 4}. Something is holding them:\n{holder or '  (lsof said nothing)'}")
        print(f"Stop the old console with:  pkill -f 'serve.py'")
        return 1

    url = f"http://127.0.0.1:{args.port}/"
    print(f"operator console  {url}")
    print(f"  project   {PROJECT} ({REGION})")
    # Looking the stack up hits CloudFormation and takes a second or two — say so rather than
    # appearing to hang before the first line of output.
    print("  stack     looking up…", end="", flush=True)
    adopt_pipeline_state()
    print(f"\r  bucket    {evidence_bucket() or '(stack not found — history disabled)'}      ")
    print(f"  state     {state.backend()}")
    print("  loopback only; per-process token; ctrl-c to stop")
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
