#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render the pipeline's results as one self-contained dashboard.

`build_html()` is the single renderer, shared by three consumers so the markup never forks:
  report.py       -> a static dashboard.html (data embedded; opens from disk)
  serve.py        -> the local operator console (adds the run button, progress, run history)
  the buildspec   -> uploads the static file to S3 for read-only viewing

Colors come from the house data-viz reference palette; status colors always ship with a glyph
AND a label, never hue alone.

Usage:  uv run report.py [--out dashboard.html]
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import os

# ── palette (house reference instance) ────────────────────────────────────────────────
CSS = """
:root { color-scheme: light; }
.viz-root {
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --ink-1: #0b0b0b; --ink-2: #52514e; --ink-3: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --ring: rgba(11,11,11,0.10);
  --accent: #2a78d6; --accent-deep: #184f95; --demote: #898781;
  --good: #0ca30c; --warning: #fab219; --serious: #ec835a; --critical: #d03b3b;
  --tint: rgba(42,120,214,0.06);
}
/* Default is light regardless of the OS preference; dark is an explicit choice via the
   light/dark button (data-theme). */
:root[data-theme="dark"] { color-scheme: dark; }
:root[data-theme="dark"] .viz-root {
  --surface-1: #1a1a19; --page: #0d0d0d;
  --ink-1: #ffffff; --ink-2: #c3c2b7; --ink-3: #898781;
  --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10);
  --accent: #3987e5; --accent-deep: #86b6ef; --demote: #898781;
  --tint: rgba(57,135,229,0.10);
}

* { box-sizing: border-box; }
body { margin: 0; background: var(--page); }
.viz-root {
  font: 14px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  color: var(--ink-1); background: var(--page);
  max-width: 1180px; margin: 0 auto; padding: 32px 24px 72px;
}
h1 { font-size: 22px; font-weight: 650; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 15px; font-weight: 650; margin: 40px 0 4px; letter-spacing: -0.005em; }
h2 .n { color: var(--ink-3); font-weight: 400; margin-left: 8px; }
.sub { color: var(--ink-2); font-size: 13px; margin: 0 0 2px; }
.hint { color: var(--ink-3); font-size: 12px; margin: 2px 0 14px; }

header { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px;
         border-bottom: 1px solid var(--grid); padding-bottom: 18px; }
.runmeta { text-align: right; color: var(--ink-2); font-size: 12px; white-space: nowrap; }
.runmeta b { color: var(--ink-1); font-weight: 600; }
button.theme { font: inherit; font-size: 12px; color: var(--ink-2); background: var(--surface-1);
  border: 1px solid var(--ring); border-radius: 6px; padding: 4px 9px; cursor: pointer; margin-top: 8px; }

/* operator console */
.console { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  background: var(--surface-1); border: 1px solid var(--ring); border-radius: 10px;
  padding: 12px 14px; margin: 18px 0 0; }
button.run { font: inherit; font-weight: 600; font-size: 13px; color: #fff; background: var(--accent);
  border: 0; border-radius: 7px; padding: 8px 16px; cursor: pointer; }
button.run:disabled { background: var(--demote); cursor: default; }
.console select { font: inherit; font-size: 13px; color: var(--ink-1); background: var(--page);
  border: 1px solid var(--ring); border-radius: 7px; padding: 7px 9px; max-width: 320px; }
.console input.search { font: inherit; font-size: 13px; color: var(--ink-1); background: var(--page);
  border: 1px solid var(--ring); border-radius: 7px; padding: 7px 9px; width: 220px; }
.console .spacer { flex: 1; }
.pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink-2); }
.pill .g { width: 9px; height: 9px; border-radius: 50%; background: var(--demote); flex: none; }
.pill.on .g { background: var(--accent); animation: pulse 1.1s ease-in-out infinite; }
.pill.ok .g { background: var(--good); } .pill.bad .g { background: var(--critical); }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .25 } }

/* Tabs — Execute / Results / Configuration. One visible at a time; the reader should never
   wonder whether they are looking at controls, at a run's output, or at setup. */
nav.tabs { display: flex; gap: 4px; margin: 20px 0 0; border-bottom: 1px solid var(--grid); }
nav.tabs button { font: inherit; font-size: 13.5px; font-weight: 600; color: var(--ink-2);
  background: none; border: 0; border-bottom: 2px solid transparent; padding: 9px 14px;
  cursor: pointer; }
nav.tabs button.on { color: var(--ink-1); border-bottom-color: var(--accent); }
nav.tabs button .cnt { color: var(--ink-3); font-weight: 400; margin-left: 5px; font-size: 12px; }
.tabpane { display: none; }
.tabpane.on { display: block; }

/* Which run the numbers below belong to. Prominent on purpose: during a run the tables still
   show the PREVIOUS run's results, and small print in a corner does not carry that. */
.srcbar { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  border: 1px solid var(--ring); border-left: 3px solid var(--accent); border-radius: 8px;
  background: var(--surface-1); padding: 9px 13px; margin-top: 10px; font-size: 13px; }
.srcbar b { font-weight: 650; }
.srcbar .age { color: var(--ink-3); font-size: 12px; }
.srcbar.stale { border-left-color: var(--warning); }
.srcbar.stale .what::before { content: "⚠ "; }

.progress { display: none; background: var(--surface-1); border: 1px solid var(--ring);
  border-radius: 10px; padding: 12px 14px; margin-top: 10px; }
.progress.show { display: block; }
.progress .phases { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.progress .ph { font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--ink-3); border: 1px solid var(--ring); border-radius: 999px; padding: 3px 9px; }
.progress .ph.done { color: var(--good); border-color: var(--good); }
.progress .ph.now { color: #fff; background: var(--accent); border-color: var(--accent); }
.progress .ph.fail { color: var(--critical); border-color: var(--critical); }
.progress pre { margin: 0; max-height: 240px; overflow: auto; font: 11.5px/1.5 ui-monospace,
  SFMono-Regular, Menlo, monospace; color: var(--ink-2); background: var(--page);
  border: 1px solid var(--ring); border-radius: 7px; padding: 10px; white-space: pre-wrap; }

/* KPI row — stat tiles, not a chart */
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 22px 0 4px; }
.tile { background: var(--surface-1); border: 1px solid var(--ring); border-radius: 10px; padding: 14px 16px; }
.tile .lab { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-3); }
.tile .val { font-size: 32px; font-weight: 620; line-height: 1.15; margin-top: 6px; letter-spacing: -0.02em; }
.tile .note { font-size: 12px; color: var(--ink-2); margin-top: 2px; }

/* status = glyph + label, never hue alone */
.badge { display: inline-flex; align-items: center; gap: 5px; font-size: 12px;
         color: var(--ink-1); white-space: nowrap; }
.badge .g { width: 9px; height: 9px; border-radius: 2px; flex: none; }
.g.good{background:var(--good)} .g.warn{background:var(--warning)}
.g.serious{background:var(--serious)} .g.crit{background:var(--critical)}
.g.accent{background:var(--accent)} .g.mute{background:var(--demote)}

table { width: 100%; border-collapse: collapse; background: var(--surface-1);
        border: 1px solid var(--ring); border-radius: 10px; overflow: hidden; }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
     color: var(--ink-3); font-weight: 600; padding: 9px 12px; border-bottom: 1px solid var(--grid); }
td { padding: 10px 12px; border-bottom: 1px solid var(--grid); vertical-align: top; font-size: 13px; }
tr:last-child td { border-bottom: 0; }
td.num, th.num { font-variant-numeric: tabular-nums; text-align: right; }
code { font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
       background: var(--tint); padding: 1px 5px; border-radius: 4px; }
a { color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--ring); }
.dim { color: var(--ink-2); }
.mute { color: var(--ink-3); }

/* funnel — emphasis form: the kept slice is the point, the dropped slice is context */
.funnel { background: var(--surface-1); border: 1px solid var(--ring); border-radius: 10px; padding: 16px; }
.bar { display: flex; gap: 2px; height: 26px; margin: 10px 0 8px; }
.bar span { border-radius: 3px; }
.bar .hits { background: var(--accent); }
.bar .drop { background: var(--demote); }
.barlabs { display: flex; justify-content: space-between; font-size: 12px; color: var(--ink-2); }
.barlabs b { color: var(--ink-1); font-weight: 600; font-variant-numeric: tabular-nums; }

.callout { background: var(--tint); border-left: 2px solid var(--accent); border-radius: 0 8px 8px 0;
           padding: 10px 14px; margin: 12px 0; font-size: 13px; }
.callout .k { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-3); }

details { background: var(--surface-1); border: 1px solid var(--ring); border-radius: 10px;
          padding: 10px 14px; margin-top: 10px; }
summary { cursor: pointer; font-size: 13px; color: var(--ink-2); }
/* top-level result folds read as section headers, not fine print */
.tabpane > details { margin-top: 14px; }
.tabpane > details > summary { font-size: 13.5px; color: var(--ink-1); padding: 2px 0; }
.tabpane > details > summary b { font-weight: 650; }
.tabpane > details > summary .badge { margin: 0 2px; }
.tabpane > details[open] > summary { border-bottom: 1px solid var(--grid); padding-bottom: 9px;
  margin-bottom: 4px; }
details details { background: var(--page); }  /* nested folds recede */
details ul { margin: 10px 0 4px; padding-left: 18px; color: var(--ink-2); font-size: 12.5px; }
details li { margin: 3px 0; }

.ba { display: grid; gap: 3px; }
.ba div { font-size: 12.5px; }
.ba .lbl { color: var(--ink-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
.ba .before { color: var(--ink-2); text-decoration: line-through; text-decoration-color: var(--axis); }
.ba .after { color: var(--ink-1); }
.ba .why { color: var(--ink-2); font-style: italic; }

/* editable config inputs — look like text until focused, then like a field */
input.cfg, select.cfg { font: 12.5px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--ink-1); background: transparent; border: 1px solid transparent; border-radius: 5px;
  padding: 3px 6px; width: 100%; box-sizing: border-box; }
input.cfg:hover, select.cfg:hover { border-color: var(--grid); }
input.cfg:focus, select.cfg:focus { border-color: var(--accent); outline: none; background: var(--page); }
button.del { font: inherit; color: var(--ink-3); background: none; border: 0; cursor: pointer; }
button.del:hover { color: var(--critical); }
.pill.dirty .g { background: var(--warning); }

.acts { background: var(--surface-1); border: 1px solid var(--ring); border-radius: 10px; padding: 6px 16px 14px; }
.acts label { display: flex; gap: 9px; align-items: flex-start; padding: 9px 0; font-size: 13px;
              border-bottom: 1px solid var(--grid); }
.acts label:last-child { border-bottom: 0; }
footer { margin-top: 44px; padding-top: 16px; border-top: 1px solid var(--grid);
         color: var(--ink-3); font-size: 12px; }
@media (max-width: 860px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
"""

BADGE = {
    "agree": ("good", "confirmed"),
    "changed": ("accent", "value changed"),
    "needs_human": ("warn", "needs review"),
    "recheck_failed": ("crit", "recheck failed"),
    "pinned_conflict": ("serious", "pinned — conflict"),
    "value": ("accent", "value"),
    "derived": ("warn", "derived judgment"),
    "flipped": ("crit", "conclusion flips"),
    # verdicts get their own labels — reusing the location badges reads as nonsense
    "schema_change": ("crit", "shape changed, not value"),
    "value_change": ("accent", "value changed"),
    "new_knowledge": ("warn", "new knowledge"),
    "no_change": ("mute", "no change needed"),
}

PHASES = ["SUBMITTED", "PROVISIONING", "INSTALL", "PRE_BUILD", "BUILD", "POST_BUILD", "COMPLETED"]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def badge(kind: str) -> str:
    g, label = BADGE.get(kind, ("mute", kind))
    return f'<span class="badge"><span class="g {g}"></span>{esc(label)}</span>'


def load(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def collect_local() -> dict:
    """Everything the renderer needs, from the result files in the working directory."""
    return {
        "recheck": load("results-recheck.json", {"counts": {}, "results": []}),
        "scan": load("results-scan.json", {"counts": {}, "hits": [], "dropped": []}),
        "judges": [j for j in (load(p) for p in sorted(glob.glob("results-judge-*.json"))) if j],
    }


# ── the renderer ──────────────────────────────────────────────────────────────────────
def build_html(data: dict, last_run: dict | None = None, console: dict | None = None, source: str | None = None) -> str:
    """One renderer, three consumers.

    `console` turns on the operator controls: {"token": str, "runs": [ids], "current": id|None}.
    When it is None the output is a plain static file with no scripts and no write paths.

    `source` names where the displayed numbers came from. It is not decoration: the console can
    show local files, an archived run, or a run that is still in flight, and data that looks
    current but is not is the worst of the three.
    """
    rc = data.get("recheck") or {"results": []}
    sc = data.get("scan") or {"counts": {}, "hits": [], "dropped": []}
    judges = data.get("judges") or []

    facts = rc.get("results", [])
    n_facts = len(facts)
    fresh = sum(1 for f in facts if f["status"] == "agree")
    attention = sum(1 for f in facts if f["status"] in ("changed", "needs_human", "recheck_failed"))
    pinned = sum(1 for f in facts if f.get("pin"))
    when = (last_run or {}).get("at", "no run recorded")

    P: list[str] = []
    a = P.append

    # One sentence saying what this console IS — its three verbs are the three tabs.
    sub = (
        "Run, review, and configure the pipeline that keeps migration-to-aws knowledge current."
        if console
        else "migration-to-aws · static export of one run"
    )

    a(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Knowledge Auto-Update</title><style>{CSS}</style></head>
<body><div class="viz-root">
<header>
  <div>
    <h1>Knowledge Auto-Update</h1>
    <p class="sub">{sub}</p>
  </div>
  <div class="runmeta">
    showing <b>{esc(source or when)}</b><br>{"operator console" if console else "static export"}
    <br><button class="theme" onclick="var r=document.documentElement;r.dataset.theme=r.dataset.theme==='dark'?'light':'dark'">light / dark</button>
  </div>
</header>
""")

    # ── tabs: Execute / Results / Configuration ───────────────────────────────────────
    # The three concerns a reader arrives with are different: "make it run", "what did a run
    # find", "what is it watching". Mixing them on one scroll made live controls look like
    # historical data. Tabs are console-only — the static export is results-only by nature.
    if console:
        runs = console.get("runs", [])
        a(f"""<nav class="tabs" id="tabs">
  <button data-pane="exec" class="on">Execute</button>
  <button data-pane="results">Results<span class="cnt">{len(runs)} run{"s" if len(runs) != 1 else ""}</span></button>
  <button data-pane="config">Configuration</button>
</nav>""")

    # ── pane 1 · Execute ──────────────────────────────────────────────────────────────
    if console:
        runs = console.get("runs", [])
        a('<div class="tabpane on" id="pane-exec">')
        a(f"""<div class="console">
  <button class="run" id="runBtn">▶&nbsp; Run now</button>
  <span class="pill" id="pill"><span class="g"></span><span id="pillTxt">idle</span></span>
  <span class="spacer"></span>
  <span class="mute" style="font-size:12px">{esc(console.get("project") or "kb-autoupdate")} · Step Functions</span>
</div>
<div class="progress" id="prog">
  <div class="phases" id="phases"></div>
  <pre id="log">waiting for the build to start…</pre>
</div>
<p class="hint" style="margin-top:12px">Starts the pipeline as a Step Functions execution — every stage, and every judged hit, reports its own status above: re-verify every fact,
scan new announcements, judge the hits, and open a draft PR when something changed. A run with
nothing new finishes silently in about a minute. When it completes, the page switches to
<b>Results</b>.</p>""")
        a("</div>")

    # ── pane 2 · Results ──────────────────────────────────────────────────────────────
    if console:
        runs = console.get("runs", [])
        opts = []
        for i, r in enumerate(runs):
            sel = " selected" if r == console.get("current") else ""
            opts.append(f'<option value="{esc(r)}"{sel}>{esc(r)}{" (newest)" if i == 0 else ""}</option>')
        if not runs:
            opts.append('<option value="">local files — no archived run yet</option>')
        a('<div class="tabpane" id="pane-results">')
        a(f"""<div class="console">
  <span class="mute" style="font-size:12px">viewing run</span>
  <select id="runSel">{''.join(opts)}</select>
  <span class="spacer"></span>
</div>
<div class="srcbar" id="srcbar">
  <span class="what">every number below comes from <b>{esc(console.get("label") or source or "local files")}</b></span>
  <span class="age">{esc(console.get("age") or "")}</span>
</div>""")

    # The results pane stays OPEN here — the KPI tiles, both monitors, the judges and the pins
    # render into it below, and it is closed just before the Configuration pane.

    if console:
        a(f"""<script>
const TOKEN = {json.dumps(console["token"])};
const PHASES = {json.dumps(PHASES)};
const SHOWING = {json.dumps(console.get("label") or source or "local files")};
const $ = (id) => document.getElementById(id);
const sha256hex = async (s) => {{
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}};
const api = async (path, opts = {{}}) => {{
  const headers = {{ "X-KB-Token": TOKEN, ...(opts.headers || {{}}) }};
  const m = (opts.method || "GET").toUpperCase();
  if (m === "POST" || m === "PUT") {{
    // Hosted, CloudFront OAC SigV4-signs the request but never the body: Lambda's IAM auth
    // requires the CLIENT to supply the payload hash on POST/PUT. Harmless locally.
    headers["x-amz-content-sha256"] = await sha256hex(opts.body || "");
  }}
  const r = await fetch(path, {{ ...opts, headers }});
  return r.json();
}};

// tabs
function showPane(name) {{
  document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("on", p.id === "pane-" + name));
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("on", b.dataset.pane === name));
  try {{ sessionStorage.setItem("kb-tab", name); }} catch (e) {{}}
}}
document.querySelectorAll("nav.tabs button").forEach((b) => (b.onclick = () => showPane(b.dataset.pane)));
// Restore the last tab across the post-run reload; ?run= means the reader came for results.
const saved = new URLSearchParams(location.search).has("run")
  ? "results"
  : (sessionStorage.getItem("kb-tab") || "exec");
showPane(saved);

function pill(state, text) {{
  $("pill").className = "pill " + state;
  $("pillTxt").textContent = text;
}}
function phases(stages, status) {{
  // Stages come from the Step Functions execution history: every pipeline stage — and every
  // judged hit inside the Map — is its own chip with its own status.
  $("phases").innerHTML = (stages || []).map((s) => {{
    let cls = "ph";
    if (s.status === "done") cls += " done";
    else if (s.status === "running") cls += " now";
    else if (s.status === "failed") cls += " fail";
    const tip = s.detail ? ` title="${{s.detail.replace(/"/g, "&quot;")}}"` : "";
    return `<span class="${{cls}}"${{tip}}>${{s.name.toLowerCase()}}</span>`;
  }}).join("");
}}

let timer = null;
async function poll(id) {{
  const p = await api("/api/progress?id=" + encodeURIComponent(id));
  phases(p.stages, p.status);
  if (p.log && p.log.length) $("log").textContent = p.log.join("\\n");
  if (p.status === "RUNNING") {{
    const now = (p.stages || []).filter((s) => s.status === "running").map((s) => s.name).join(", ");
    pill("on", "running · " + (now || "starting").toLowerCase());
    // The tables are NOT this run's output — it has not written anything yet. Say so where the
    // reader is already looking, not in a corner.
    const bar = $("srcbar");
    bar.classList.add("stale");
    bar.querySelector(".what").innerHTML =
      "a run is in progress — the numbers below are still from <b>" + SHOWING + "</b>";
    bar.querySelector(".age").textContent = "they refresh when it finishes";
  }} else {{
    clearInterval(timer);
    timer = null;
    pill(p.status === "SUCCEEDED" ? "ok" : "bad", p.status.toLowerCase());
    $("runBtn").disabled = false;
    if (p.status === "SUCCEEDED") {{
      // Results only exist once the run has written them. Land the reader on the Results tab —
      // that is what they pressed the button to see.
      try {{ sessionStorage.setItem("kb-tab", "results"); }} catch (e) {{}}
      setTimeout(() => location.reload(), 1500);
    }} else {{
      // The run died, so "in progress … refresh when it finishes" would be a lie. Put the
      // banner back to naming the data actually on screen, and say where the error is.
      const bar = $("srcbar");
      bar.classList.remove("stale");
      bar.querySelector(".what").innerHTML =
        "the run <b>failed</b> — the numbers below are still from <b>" + SHOWING + "</b>";
      bar.querySelector(".age").textContent = "see the log above for the error";
    }}
  }}
}}

$("runBtn").onclick = async () => {{
  $("runBtn").disabled = true;
  $("prog").classList.add("show");
  pill("on", "starting");
  const r = await api("/api/execute", {{ method: "POST" }});
  if (r.error) {{ pill("bad", r.error); $("runBtn").disabled = false; return; }}
  $("log").textContent = "build " + r.buildId;
  timer = setInterval(() => poll(r.buildId), 4000);
  poll(r.buildId);
}};

$("runSel").onchange = (e) => {{
  location.search = e.target.value ? "?run=" + encodeURIComponent(e.target.value) : "";
}};

// Reattach to a build that is still running from a previous page load.
api("/api/progress").then((p) => {{
  if (p && p.status === "RUNNING") {{
    $("runBtn").disabled = true;
    $("prog").classList.add("show");
    timer = setInterval(() => poll(p.buildId), 4000);
    poll(p.buildId);
  }}
}});

// ── config editing: read the tables back into JSON, debounce-save on change ──────────
function cfgPill(state, text) {{
  const el = $("cfgPill");
  if (!el) return;
  el.className = "pill " + state;
  $("cfgPillTxt").textContent = text;
}}
function readFacts() {{
  // Round-trip MUST preserve fields the table does not display (unit, pin, appears_in,
  // confidence, observed_at, …). Losing them was a real incident: the first live autosave
  // silently stripped every fact to its five visible columns — including a load-bearing pin.
  // Each row carries its full original record in data-orig; edits overlay it.
  return [...document.querySelectorAll("#factsTable tr[data-i]")].map((tr) => {{
    let orig = {{}};
    try {{ orig = JSON.parse(tr.dataset.orig || "{{}}"); }} catch (e) {{}}
    return {{
      ...orig,
      enabled: tr.querySelector(".f-on").checked,
      key: tr.querySelector(".f-key").value.trim(),
      value: tr.querySelector(".f-val").value.trim(),
      recheck: {{ ...(orig.recheck || {{}}), url: tr.querySelector(".f-url").value.trim(), locate: tr.querySelector(".f-loc").value.trim() }},
      origin: tr.children[5].textContent.trim() || "user",
    }};
  }});
}}
function readSources() {{
  return [...document.querySelectorAll("#srcTable tr[data-i]")].map((tr) => ({{
    enabled: tr.querySelector(".s-on").checked,
    id: tr.querySelector(".s-id").value.trim(),
    name: tr.querySelector(".s-name").value.trim(),
    type: tr.querySelector(".s-type").value,
    url: tr.querySelector(".s-url").value.trim(),
    note: tr.querySelector(".s-note").value.trim(),
  }}));
}}
let saveTimer = null;
function queueSave() {{
  cfgPill("dirty", "unsaved…");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {{
    const rf = await api("/api/config/facts", {{ method: "POST", body: JSON.stringify({{ facts: readFacts() }}) }});
    const rs = await api("/api/config/sources", {{ method: "POST", body: JSON.stringify({{ sources: readSources() }}) }});
    if (rf.error || rs.error) cfgPill("bad", rf.error || rs.error);
    else cfgPill("ok", "saved — live on the next run");
  }}, 800);
}}
// This script tag sits BEFORE the Configuration pane in the document, so its elements do
// not exist yet at parse time — wiring must wait for DOMContentLoaded. (The old bare
// `if (cfgPane)` guard skipped everything silently: + fact / + source / bootstrap /
// autosave never worked, and nothing said so.)
document.addEventListener("DOMContentLoaded", () => {{
  const cfgPane = $("pane-config");
  if (!cfgPane) return;
  cfgPane.addEventListener("input", (e) => {{
    // Only EDIT controls trigger a save. The search box is also an input inside this pane —
    // matching it here is what fired the destructive first autosave.
    if (e.target.matches("input.cfg, input.f-on, input.s-on, select.cfg")) queueSave();
  }});
  cfgPane.addEventListener("click", (e) => {{
    if (e.target.matches(".f-del, .s-del")) {{
      const wasFact = e.target.matches(".f-del");
      e.target.closest("tr").remove();
      queueSave();
      if (wasFact) applyFactView();
    }}
  }});

  // The facts table is ~100 rows since prose bootstrap: client-side search + pagination.
  // Hidden rows stay in the DOM, so readFacts()/autosave still see every row.
  const FACT_PAGE = 15;
  let fpage = 0, fquery = "";
  function applyFactView() {{
    const rows = [...document.querySelectorAll("#factsTable tr[data-i]")];
    const q = fquery.toLowerCase();
    const vis = rows.filter((tr) => {{
      tr.style.display = "none";
      if (!q) return true;
      if (tr.textContent.toLowerCase().includes(q)) return true;
      return [...tr.querySelectorAll("input:not([type=checkbox])")]
        .some((i) => i.value.toLowerCase().includes(q));
    }});
    const pages = Math.max(1, Math.ceil(vis.length / FACT_PAGE));
    fpage = Math.min(Math.max(fpage, 0), pages - 1);
    vis.slice(fpage * FACT_PAGE, (fpage + 1) * FACT_PAGE).forEach((tr) => (tr.style.display = ""));
    $("factPager").textContent = `${{vis.length}} fact${{vis.length === 1 ? "" : "s"}} · ${{fpage + 1}}/${{pages}}`;
    $("factPrev").disabled = fpage === 0;
    $("factNext").disabled = fpage >= pages - 1;
  }}
  $("factSearch").oninput = (e) => {{ fquery = e.target.value.trim(); fpage = 0; applyFactView(); }};
  $("factPrev").onclick = () => {{ fpage--; applyFactView(); }};
  $("factNext").onclick = () => {{ fpage++; applyFactView(); }};
  applyFactView();
  const addRow = (tableId, html) => {{
    const t = $(tableId);
    const tr = document.createElement("tr");
    tr.dataset.i = t.querySelectorAll("tr[data-i]").length;
    tr.innerHTML = html;
    t.appendChild(tr);
  }};
  $("addFactBtn").onclick = () => addRow("factsTable",
    '<td><input type="checkbox" class="f-on" checked></td><td><input class="cfg f-key" placeholder="service.field"></td>' +
    '<td><input class="cfg f-val" placeholder="current value"></td><td><input class="cfg f-url" placeholder="https://docs…"></td>' +
    '<td><input class="cfg f-loc" placeholder="in the table of …, read the … column"></td><td class="mute">user</td>' +
    '<td><button class="del f-del">✕</button></td>');
  $("addFactBtn").addEventListener("click", () => {{
    // Runs after the onclick above added the row: land the operator on it — clear the
    // filter, jump to the last page.
    fquery = ""; $("factSearch").value = ""; fpage = 1e9; applyFactView();
  }});
  $("addSrcBtn").onclick = () => addRow("srcTable",
    '<td><input type="checkbox" class="s-on" checked></td><td><input class="cfg s-id" placeholder="my-source"></td>' +
    '<td><input class="cfg s-name" placeholder="Name"></td>' +
    '<td><select class="cfg s-type"><option value="rss">rss</option><option value="url-watch">url-watch</option></select></td>' +
    '<td><input class="cfg s-url" placeholder="https://…/feed/"></td><td><input class="cfg s-note" placeholder=""></td>' +
    '<td><button class="del s-del">✕</button></td>');
  $("bootstrapBtn").onclick = async () => {{
    $("bootstrapBtn").disabled = true;
    cfgPill("on", "scanning the skill…");
    const r = await api("/api/config/bootstrap", {{ method: "POST" }});
    if (r.error || !r.ok) {{
      cfgPill("bad", r.error || "bootstrap failed — see server log");
      $("bootstrapBtn").disabled = false;
      return;
    }}
    if (r.remote) {{
      // Hosted: the scan runs as a bootstrap-mode pipeline execution. Poll it.
      cfgPill("on", "bootstrap running as a pipeline execution (~3–5 min)…");
      const t = setInterval(async () => {{
        const p = await api(`/api/progress?id=${{encodeURIComponent(r.buildId)}}`);
        if (p.status === "SUCCEEDED") {{
          clearInterval(t);
          cfgPill("ok", "bootstrap merged — reloading");
          setTimeout(() => {{ sessionStorage.setItem("kb-tab", "config"); location.reload(); }}, 900);
        }} else if (["FAILED", "FAULT", "STOPPED", "TIMED_OUT"].includes(p.status)) {{
          clearInterval(t);
          cfgPill("bad", "bootstrap build " + p.status);
          $("bootstrapBtn").disabled = false;
        }}
      }}, 10000);
      return;
    }}
    $("bootstrapBtn").disabled = false;
    cfgPill("ok", "bootstrap merged");
    setTimeout(() => {{ sessionStorage.setItem("kb-tab", "config"); location.reload(); }}, 900);
  }};
}});
</script>
""")

    # ── the summary: answer first ─────────────────────────────────────────────────────
    # The reader's question is "did anything happen?". One sentence answers it; everything
    # else is detail they opt into. The severity order is: judged changes > facts needing
    # attention > everything checked out.
    c = sc.get("counts", {})
    hits_n = c.get("hits", 0)
    judged_changes = [
        j for j in judges
        if (j.get("step1") or {}).get("verdict") not in (None, "no_change")
        and ((j.get("step2") or {}).get("affected"))
    ]
    judged_nochange = [j for j in judges if (j.get("step1") or {}).get("verdict") == "no_change"]

    pr_links = [j["pr"] for j in judges if (j.get("pr") or {}).get("url")]

    if judged_changes:
        n_loc = sum(len((j["step2"] or {}).get("affected", [])) for j in judged_changes)
        n_flip = sum(1 for j in judged_changes for x in (j["step2"] or {}).get("affected", []) if x.get("kind") == "flipped")
        # The PR is the product — its link belongs in the headline, not in a log.
        if pr_links:
            pr_frag = " · ".join(
                f'<a href="{esc(p["url"])}" target="_blank"><b>review draft PR #{esc(p["url"].rsplit("/", 1)[-1])}</b></a>'
                for p in pr_links
            )
            tail = f" → {pr_frag}"
        else:
            tail = ". The edits could not be pushed — see the Judge section."
        headline = (f"<b>Something changed.</b> {len(judged_changes)} announcement{'s' if len(judged_changes) != 1 else ''} "
                    f"affected the skill's knowledge — {n_loc} location{'s' if n_loc != 1 else ''}"
                    + (f", {n_flip} conclusion{'s' if n_flip != 1 else ''} reversed" if n_flip else "")
                    + tail)
        tone = "crit"
    elif attention or any((j.get("step1") or {}).get("verdict") == "needs_human" for j in judges):
        n_nh = sum(1 for j in judges if (j.get("step1") or {}).get("verdict") == "needs_human")
        bits = []
        if attention:
            bits.append(f"{attention} fact{'s' if attention != 1 else ''} did not verify cleanly "
                        "(a changed value, an ambiguous page, or a failed fetch)")
        if n_nh:
            bits.append(f"{n_nh} announcement{'s' if n_nh != 1 else ''} could not be classified with confidence")
        headline = "<b>Needs a look.</b> " + "; ".join(bits) + " — a human decides."
        tone = "warn"
    else:
        headline = (f"<b>All quiet.</b> Every tracked fact was re-verified against its source and still holds"
                    + (f"; {hits_n} announcement{'s' if hits_n != 1 else ''} looked relevant but changed nothing"
                       if hits_n else "; no relevant announcements")
                    + ". Nothing was opened, changed, or committed.")
        tone = "good"

    a(f"""<div class="callout" style="border-left-color: var(--{tone}); margin-top: 16px">
  <div style="font-size:14px">{headline}</div>
</div>
<div class="kpis">
  <div class="tile"><div class="lab">facts verified</div><div class="val">{fresh}<span class="mute" style="font-size:18px">/{n_facts}</span></div>
    <div class="note">{badge("agree") if fresh == n_facts else badge("needs_human")}</div></div>
  <div class="tile"><div class="lab">announcements</div><div class="val">{c.get("in", 0)}</div>
    <div class="note">{hits_n} relevant · {c.get("dropped", 0)} dropped{f" · {c['already_seen']} seen before" if c.get("already_seen") else ""}</div></div>
  <div class="tile"><div class="lab">knowledge changes</div><div class="val">{len(judged_changes)}</div>
    <div class="note">{(" · ".join(f'<a href="{esc(p["url"])}" target="_blank">PR #{esc(p["url"].rsplit("/", 1)[-1])}</a>' for p in pr_links) + " opened") if pr_links else ("draft PR opened" if judged_changes else ("judged, nothing to change" if judged_nochange else "—"))}</div></div>
  <div class="tile"><div class="lab">pinned</div><div class="val">{pinned}</div>
    <div class="note">human verdict outranks the source</div></div>
</div>
""")

    # ── details, each behind a fold ───────────────────────────────────────────────────
    # Only what the summary flagged opens by default; healthy sections stay shut.
    a(f"""<details{"" if not attention else " open"}>
<summary><b>Monitor 1 — Recheck</b> · {fresh}/{n_facts} confirmed
<span class="mute">— every fact re-fetched from its own source page</span></summary>
<p class="hint" style="margin-top:10px">The question is only “does what we said still hold?”. A new capability appearing elsewhere is not this monitor’s business.</p>""")
    a("<table><tr><th>fact</th><th>stored</th><th>observed on the page</th><th>status</th>"
      '<th class="num">appears in</th><th>next step</th></tr>')
    for f in facts:
        obs = f.get("observed_value") or f.get("error") or "—"
        act = {"none": '<span class="mute">nothing to do</span>',
               "auto_edit": "auto-edit + PR",
               "route_to_human": "route to a human"}.get(f.get("action", "none"), esc(f.get("action")))
        a(f"""<tr>
<td><code>{esc(f['key'])}</code><div class="mute" style="margin-top:3px"><a href="{esc(f['url'])}">source</a></div></td>
<td class="dim">{esc(f['stored_value'])}</td>
<td>{esc(obs)}</td>
<td>{badge(f['status'])}</td>
<td class="num">{f.get('appears_in_count', 0)}</td>
<td class="dim">{act}</td></tr>""")
    a("</table></details>")

    # ── scan (folded; opens when something was kept) ──────────────────────────────────
    total, hits, drop = c.get("in", 0), c.get("hits", 0), c.get("dropped", 0)
    hp = (hits / total * 100) if total else 0
    a(f"""<details{" open" if hits else ""}>
<summary><b>Monitor 2 — Announcement scan</b> · {hits} relevant of {total} triaged
<span class="mute">— AWS What’s New, filtered by the 27 existing reference files</span></summary>
<p class="hint" style="margin-top:10px">No separate topic list is maintained: the skill’s own knowledge files <em>are</em> the filter, so it can never fall out of date.</p>""")
    a(f"""<div class="funnel">
  <div class="bar"><span class="hits" style="flex:{max(hits, 1)}"></span><span class="drop" style="flex:{max(drop, 1)}"></span></div>
  <div class="barlabs">
    <span><b>{hits}</b> relevant &nbsp;<span class="mute">({hp:.0f}% of what was triaged)</span></span>
    <span class="mute"><b>{drop}</b> dropped{f" · {c['already_seen']} seen before" if c.get("already_seen") else ""}</span>
  </div>
</div>""")
    if sc.get("hits"):
        a('<table style="margin-top:12px"><tr><th>announcement</th><th>files it touches</th><th>why kept</th></tr>')
        for h in sc["hits"]:
            files = " ".join(f"<code>{esc(x)}</code>" for x in h.get("files", [])) or '<span class="mute">none named</span>'
            a(f"""<tr><td><a href="{esc(h['url'])}">{esc(h['title'])}</a></td>
<td>{files}</td><td class="dim">{esc(h.get('reason'))}</td></tr>""")
        a("</table>")
    if sc.get("dropped"):
        a(f'<details><summary>{drop} dropped items — the only place a missed announcement can be caught</summary><ul>')
        for d in sc["dropped"]:
            url_link = f'<a href="{esc(d["url"])}" target="_blank">{esc(d["title"])}</a>' if d.get("url") else esc(d["title"])
            a(f'<li>{url_link} <span class="mute">— {esc(d.get("reason"))}</span></li>')
        a("</ul></details>")
    a("</details>")

    # ── judge (folded; a real change opens, a no_change stays shut) ───────────────────
    for j in judges:
        s1, s2 = j.get("step1", {}), j.get("step2") or {"affected": []}
        aff = s2.get("affected", [])
        flips = [x for x in aff if x.get("kind") == "flipped"]
        changed = s1.get("verdict") not in (None, "no_change") and bool(aff)
        gist = (f"{len(aff)} locations · {len(flips)} conclusions flip" if changed
                else "no change needed")
        pr = j.get("pr") or {}
        a(f"""<details{" open" if changed else ""}>
<summary><b>Judge</b> · {badge(s1.get("verdict", ""))} · {gist}
<span class="mute">— “{esc(j.get("hit", {}).get("title"))}”</span></summary>""")
        if pr.get("url"):
            a(f"""<div class="callout" style="margin-top:10px; border-left-color: var(--good)">
  <div class="k">pull request</div>
  <div style="margin-top:4px"><a href="{esc(pr['url'])}" target="_blank"><b>{esc(pr.get('title') or pr['url'])}</b></a></div>
  <div class="dim" style="margin-top:4px">draft · branch <code>{esc(pr.get('branch'))}</code> · commit <code>{esc(pr.get('commit'))}</code>
  · {pr.get('applied', 0)} edit{'s' if pr.get('applied', 0) != 1 else ''} applied{f" · {pr['skipped']} skipped (listed in the PR)" if pr.get('skipped') else ""}</div>
</div>""")
        elif changed:
            a('<p class="hint" style="margin-top:10px">No PR was recorded for this change — the apply/push step likely failed; check the run log on the Execute tab.</p>')
        fp = s1.get("false_positive_files") or []
        if isinstance(fp, str):
            fp = [fp]
        a(f"""<div class="callout" style="margin-top:10px">
  <div class="k">verdict</div>
  <div style="margin:4px 0 8px">{badge(s1.get("verdict", ""))}
     &nbsp;<span class="mute">on</span> <code>{esc(s1.get('fact_key'))}</code></div>
  <div><span class="mute">was</span> {esc(s1.get('old_value'))}</div>
  <div style="margin-top:4px"><span class="mute">now</span> {esc(s1.get('new_value'))}</div>
  {f'<div style="margin-top:8px"><span class="k">still true</span><br>{esc(s1["still_true"])}</div>' if s1.get("still_true") else ""}
  {f'<div style="margin-top:8px"><span class="k">false positive from the filter</span><br><code>{esc(", ".join(fp))}</code></div>' if fp else ""}
  {f'<div style="margin-top:8px"><span class="k">caps applied</span><br><span class="dim">{esc(s2.get("notes"))}</span></div>' if s2.get("notes") else ""}
</div>""")
        if aff:
            a("<table><tr><th>location</th><th>kind</th><th>proposed change &amp; justification</th></tr>")
            order = {"flipped": 0, "derived": 1, "value": 2}
            for x in sorted(aff, key=lambda y: (order.get(y.get("kind"), 9), y.get("file", ""))):
                a(f"""<tr>
<td><code>{esc(str(x.get('file', '')).split('/')[-1])}:{esc(x.get('line'))}</code>
    <div class="mute" style="margin-top:3px">{esc(os.path.dirname(str(x.get('file', ''))))}</div></td>
<td>{badge(x.get('kind', ''))}</td>
<td><div class="ba">
  <div class="lbl">before</div><div class="before">{esc(x.get('before'))}</div>
  <div class="lbl">after</div><div class="after">{esc(x.get('after'))}</div>
  <div class="lbl">why</div><div class="why">{esc(x.get('why'))}</div>
</div></td></tr>""")
            a("</table>")
            a('<p class="hint">No CI check can catch a badly reworded judgment — the “why” column is the reviewer’s only protection, so it is mandatory.</p>')
        a("</details>")

    # ── pins (folded; steady state, not news) ─────────────────────────────────────────
    pins = [f for f in facts if f.get("pin")]
    if pins:
        a(f"""<details>
<summary><b>Pinned</b> · {len(pins)}
<span class="mute">— a human verdict outranks the source until specific evidence appears</span></summary>""")
        a("<table style=\"margin-top:10px\"><tr><th>fact</th><th>ours</th><th>source said</th><th>since</th><th>lifts when</th></tr>")
        for f in pins:
            p = f["pin"]
            lo = p.get("last_observed") or {}
            a(f"""<tr><td><code>{esc(f['key'])}</code></td><td>{esc(f['stored_value'])}</td>
<td class="dim">{esc(lo.get('value', '—'))}</td><td class="dim">{esc(p.get('at'))}</td>
<td class="dim">{esc(p.get('lift_when'))}</td></tr>""")
        a("</table>")
        a(f'<p class="hint">{esc(pins[0]["pin"].get("reason"))}</p>')
        a("</details>")

    if console:
        a("</div>")  # close pane-results

        # ── pane 3 · Configuration ────────────────────────────────────────────────────
        # Two EDITABLE groups (hard conditions, message sources) and two read-only ones.
        # The boundary: this pane edits WHAT THE PIPELINE WATCHES — operations config, stored
        # next to last_seen, live on the next run. What the SKILL ASSERTS never changes here;
        # that goes through a reviewed PR, always.
        cfg = console.get("config") or {}
        a('<div class="tabpane" id="pane-config">')
        a('<p class="hint" style="margin-top:14px">This pane edits <b>what the pipeline watches</b> — it takes effect on the next run, no deploy. What the <b>skill asserts</b> never changes here: that goes through a reviewed PR, always.</p>')

        # -- group 1: hard conditions (facts) --
        facts = cfg.get("facts", [])
        n_on = sum(1 for f in facts if f.get("enabled", True))
        a(f'<h2>1 · Hard conditions<span class="n">re-verified every run · {n_on} of {len(facts)} enabled</span></h2>')
        a('<p class="hint">Each row: the value the skill currently claims, the public page that can prove it, and a locate instruction a model can follow. <b>Bootstrap</b> scans the skill and proposes new entries (they arrive disabled unless the URL verified and confidence was high — review, then enable).</p>')
        a("""<div class="console" style="margin-bottom:10px">
  <button class="run" id="bootstrapBtn" style="background:var(--accent-deep)">⟳&nbsp; Bootstrap from skill</button>
  <span class="pill" id="cfgPill"><span class="g"></span><span id="cfgPillTxt">saved</span></span>
  <span class="spacer"></span>
  <input id="factSearch" class="search" type="search" placeholder="search facts…">
  <button class="theme" id="factPrev">‹</button>
  <span class="mute" id="factPager" style="font-size:12px; white-space:nowrap"></span>
  <button class="theme" id="factNext">›</button>
  <button class="run" id="addFactBtn">+ fact</button>
</div>""")
        a('<table id="factsTable"><tr><th style="width:36px">on</th><th>fact</th><th>current value</th><th>source url</th><th>locate instruction</th><th style="width:70px">origin</th><th style="width:40px"></th></tr>')
        for i, f in enumerate(facts):
            rc_ = f.get("recheck") or {}
            pin_mark = " 📌" if f.get("pin") else ""
            a(f"""<tr data-i="{i}" data-orig="{esc(json.dumps(f, ensure_ascii=False))}">
<td><input type="checkbox" class="f-on" {"checked" if f.get("enabled", True) else ""}></td>
<td><input class="cfg f-key" value="{esc(f['key'])}">{pin_mark}</td>
<td><input class="cfg f-val" value="{esc(f['value'] if isinstance(f['value'], str) else json.dumps(f['value'], ensure_ascii=False))}"></td>
<td><input class="cfg f-url" value="{esc(rc_.get('url'))}"></td>
<td><input class="cfg f-loc" value="{esc(rc_.get('locate'))}"></td>
<td class="mute">{esc(f.get('origin', 'user'))}</td>
<td><button class="del f-del">✕</button></td></tr>""")
        a("</table>")

        # -- group 2: message sources --
        sources = cfg.get("sources", [])
        live = sum(1 for s in sources if s.get("enabled"))
        a(f'<h2>2 · Message sources<span class="n">what Monitor 2 subscribes to · {live} live</span></h2>')
        a('<p class="hint"><code>rss</code> polls real feeds; <code>url-watch</code> reads changelog pages without one (OpenAI API changelog, Anthropic release notes, Temporal changelog) by segmenting their date-headed entries. Both run today; a source only runs when enabled.</p>')
        a("""<div class="console" style="margin-bottom:10px">
  <span class="spacer"></span>
  <button class="run" id="addSrcBtn">+ source</button>
</div>""")
        a('<table id="srcTable"><tr><th style="width:36px">on</th><th>id</th><th>name</th><th style="width:110px">type</th><th>url</th><th>note</th><th style="width:40px"></th></tr>')
        for i, s in enumerate(sources):
            type_opts = "".join(
                f'<option value="{t}"{" selected" if s.get("type") == t else ""}>{t}</option>'
                for t in ("rss", "url-watch"))
            a(f"""<tr data-i="{i}">
<td><input type="checkbox" class="s-on" {"checked" if s.get("enabled") else ""}></td>
<td><input class="cfg s-id" value="{esc(s['id'])}"></td>
<td><input class="cfg s-name" value="{esc(s.get('name', ''))}"></td>
<td><select class="cfg s-type">{type_opts}</select></td>
<td><input class="cfg s-url" value="{esc(s['url'])}"></td>
<td><input class="cfg s-note" value="{esc(s.get('note', ''))}"></td>
<td><button class="del s-del">✕</button></td></tr>""")
        a("</table>")

        # -- read-only groups --
        files = cfg.get("filter_files") or []
        a(f'<h2>Announcement filter<span class="n">the {len(files)} reference files Monitor 2 triages against — not editable</span></h2>')
        a('<p class="hint">These are the skill’s own knowledge files, so the filter can never fall out of date. To widen it, add a reference file to the skill (through a PR).</p>')
        a('<details><summary>show the files</summary><ul>')
        for fn in files:
            a(f"<li><code>{esc(fn)}</code></li>")
        a("</ul></details>")

        a('<h2>Pipeline wiring<span class="n">CloudFormation parameters — change via <code>--parameter-overrides</code></span></h2>')
        a("<table><tr><th>parameter</th><th>value</th></tr>")
        for k, v in (cfg.get("stack_params") or {}).items():
            a(f'<tr><td class="dim">{esc(k)}</td><td><code>{esc(v or "—")}</code></td></tr>')
        a("</table>")
        a("</div>")

    a("</div></body></html>")

    return "".join(P)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dashboard.html")
    args = ap.parse_args()

    import state

    data = collect_local()
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_html(data, state.get("last_run")))

    rc, sc = data["recheck"], data["scan"]
    print(f"wrote {args.out}")
    print(f"  facts {len(rc['results'])}")
    print(f"  scan  {sc['counts'].get('in', 0)} in / {sc['counts'].get('hits', 0)} hits")
    for j in data["judges"]:
        print(f"  judge {j['step1']['verdict']:<14} {len((j.get('step2') or {}).get('affected', []))} locations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
