---
_fragment: generate-report
_of_phase: generate
_contributes:
  - recommendation-report.html
---

# Generate Phase: HTML Recommendation Report

> Loaded by `generate.md` after Steps 3–5 complete (diagram written, recommendation.md
> written, scaffold written, mini-brief printed, gates set). Execute ALL steps in order.

## Overview

Generate a single self-contained HTML file (`$RUN_DIR/recommendation-report.html`) that
presents the agent architecture recommendation visually. The file uses inline CSS and a
CDN-loaded Mermaid.js for the diagram — no other external dependencies. Users can open it
in any browser and use "Print to PDF" if needed.

**Before writing the HTML:** load two shared single-source files:

- `references/report-shell.md` — inline its CSS block (the shared chrome: reset & base,
  `.page`, `.site-header`, `.section-title`, `.banner*`, base table, `.two-col`) into the
  `<style>` block at the `{{ SHARED_SHELL_CSS ... }}` marker, and inline its SRI-pinned
  mermaid@10.9.3 script tag at the `{{ SHARED_SHELL_MERMAID_TAG ... }}` marker in `<head>`.
  The remaining rules in the `<style>` block below are this report's OWN content CSS.
- `references/report-help-banner.md` — copy its CSS rules into the `<style>` block and emit
  its HTML block at the `<!-- HELP BANNER -->` marker below (with `{{ HELP_URL }}`
  substituted). This is the shared "Need help?" CTA banner that appears in every report.

**Non-blocking:** if HTML generation fails for any reason, log a warning, do NOT fail the
Generate phase, and continue. The recommendation.md is the authoritative document.

## Step R0 — Gather data

Read all available sources. Mark each as present or absent — absent fields use the fallback
rules below.

| Variable                 | Source                                                                                                                                                                                                                                                    | Fallback                         |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| `VERDICT`                | `design.json.verdict`                                                                                                                                                                                                                                     | —                                |
| `DEPLOYMENT_MODEL`       | `pass2.json.deployment_model`                                                                                                                                                                                                                             | `design.json.deployment_model`   |
| `SERVICES`               | `pass2.json.agentcore_services`                                                                                                                                                                                                                           | `design.json.agentcore_services` |
| `MODEL_KEY`              | `design.json.model_recommendation.model`                                                                                                                                                                                                                  | —                                |
| `MODEL_DISPLAY`          | Map from MODEL_KEY: `claude_sonnet_4_6`→"Claude Sonnet 4.6", `claude_haiku_4_5`→"Claude Haiku 4.5", `nova_pro`→"Amazon Nova Pro", `nova_lite`→"Amazon Nova Lite", `nova_micro`→"Amazon Nova Micro", `llama4_maverick`→"Llama 4 Maverick", other→MODEL_KEY |                                  |
| `MODEL_REASONING`        | `design.json.model_recommendation.reasoning`                                                                                                                                                                                                              | ""                               |
| `SCORES`                 | `scoring-result.json.scores` (object: runtime→score)                                                                                                                                                                                                      | —                                |
| `ELIMINATED`             | `scoring-result.json.eliminated` (object: runtime→reason)                                                                                                                                                                                                 | {}                               |
| `WARNINGS`               | `scoring-result.json.warnings`                                                                                                                                                                                                                            | []                               |
| `IO_WAIT_NOTE`           | `design.json.io_wait_tco_note`                                                                                                                                                                                                                            | false                            |
| `FEDRAMP_NOTE`           | `design.json.fedramp_note`                                                                                                                                                                                                                                | false                            |
| `REGION_NOTE`            | `design.json.region_availability_note`                                                                                                                                                                                                                    | null                             |
| `VOLATILE_FACTS`         | `design.json.volatile_facts`                                                                                                                                                                                                                              | {}                               |
| `COST_BAND`              | `estimate.json.monthly_magnitude_usd` if file exists                                                                                                                                                                                                      | null                             |
| `COST_ASSUMPTIONS`       | `estimate.json.assumptions` if file exists                                                                                                                                                                                                                | []                               |
| `SCAFFOLD_EXISTS`        | true if `$RUN_DIR/scaffold/` directory exists and is non-empty                                                                                                                                                                                            | false                            |
| `DIAGRAM_MERMAID`        | Extract the fenced ```mermaid block from `diagram.md`                                                                                                                                                                                                     | null                             |
| `DIAGRAM_ASCII`          | Extract the ASCII block inside `<details>` from `diagram.md`                                                                                                                                                                                              | null                             |
| `RUN_DATE`               | From `design.json` or current date                                                                                                                                                                                                                        | "2026"                           |
| `ENTRY_POINT`            | `answers.json.entry_point`                                                                                                                                                                                                                                | "build"                          |
| `ANSWERS`                | `answers.json.answers`                                                                                                                                                                                                                                    | {}                               |
| `MANAGED_ALTERNATIVE`    | `design.json.managed_alternative`                                                                                                                                                                                                                         | null                             |
| `RECOMMENDATION_MD_PATH` | `$RUN_DIR/recommendation.md`                                                                                                                                                                                                                              | —                                |

## Step R1 — Build score bar data

Sort SCORES descending by value. The highest score is the winner (= VERDICT).

For the bar chart, compute each runtime's percentage relative to the max score:
`pct = round(score / max_score * 100)`.

Runtime display names:

- `agentcore` → "AgentCore Runtime"
- `lambda_microvms` → "Lambda MicroVMs"
- `lambda` → "Lambda"
- `ecs` → "ECS (Fargate)"
- `eks` → "EKS"

Deployment model display names:

- `harness` → "AgentCore Harness (no-code)"
- `framework_on_runtime` → "Framework on Runtime (bring your own code)"
- `framework` → "Framework on Runtime (bring your own code)"

Service display names and descriptions:

- `identity` → "Identity" / "Session authentication & caller verification — always on, free."
- `observability` → "Observability" / "Automatic OpenTelemetry traces — every LLM call, latency, and error without code changes — always on, free."
- `evaluations` → "Evaluations" / "Response quality tracking and regression gates — always on, free."
- `optimization` → "Optimization" / "Model routing hints and cost optimization — always on, free."
- `memory` → "Memory" / "Persistent cross-session memory — replaces in-process conversation buffers with a durable store."
- `gateway` → "Gateway" / "Connects external APIs and MCP tools to the agent."
- `code_interpreter` → "Code Interpreter" / "Sandboxed code execution inside the agent."
- `managed_kb` → "Managed KB" / "Built-in RAG over your internal documents."
- `policy` → "Policy" / "Cedar-based authorization for high-risk agent actions."

Always-on (free) services: `identity`, `observability`, `evaluations`, `optimization`.
User-selected (add-on) services: everything else in SERVICES.

## Step R2 — Write the HTML file

Write `$RUN_DIR/recommendation-report.html` with the following structure. Every `{{ }}` is
a substitution from Step R0/R1. Do not output placeholder text — if a value is absent, hide
that element entirely (use `display:none` or omit the HTML block).

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AWS Agent Architecture Recommendation</title>
<!-- SRI-pinned mermaid@10.9.3 script tag — inline it VERBATIM from the shared shell
     (references/report-shell.md), same tag/integrity hash used by every report with a diagram. -->
{{ SHARED_SHELL_MERMAID_TAG from references/report-shell.md }}
<style>
  /* ── Shared chrome ── load references/report-shell.md and inline its CSS block
     HERE (reset & base, .page layout, .site-header, .section-title, .banner*,
     base table/th/td, .two-col). Single-sourced there so this report and the
     temporal report share identical chrome — do not restate those rules here. ── */
  {{ SHARED_SHELL_CSS from references/report-shell.md }}

  /* ── Hero card ── */
  .hero { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 32px; }
  .hero-main { background: #fff; border-radius: 12px; padding: 28px 32px;
               border-left: 5px solid #FF9900;
               box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .hero-main .label { font-size: 11px; font-weight: 700; text-transform: uppercase;
                       letter-spacing: 1px; color: #FF9900; margin-bottom: 8px; }
  .hero-main .runtime { font-size: 28px; font-weight: 700; color: #1a1a2e; }
  .hero-main .deployment { font-size: 14px; color: #6b7280; margin-top: 4px; }
  .hero-main .model-row { margin-top: 20px; padding-top: 20px;
                           border-top: 1px solid #f0f0f0; }
  .hero-main .model-label { font-size: 11px; color: #9ca3af; text-transform: uppercase;
                              letter-spacing: 0.8px; }
  .hero-main .model-name { font-size: 17px; font-weight: 600; color: #1a1a2e; }
  .hero-main .model-reason { font-size: 13px; color: #6b7280; margin-top: 3px; }

  .hero-services { background: #fff; border-radius: 12px; padding: 28px 32px;
                   box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .hero-services .label { font-size: 11px; font-weight: 700; text-transform: uppercase;
                           letter-spacing: 1px; color: #6b7280; margin-bottom: 14px; }
  .service-tag { display: inline-flex; align-items: center; gap: 6px;
                 font-size: 13px; font-weight: 500; border-radius: 20px; padding: 5px 13px;
                 margin: 4px 4px 4px 0; }
  .service-tag.free { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
  .service-tag.addon { background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; }

  /* ── Scores ── */
  .scores-list { background: #fff; border-radius: 12px; padding: 28px 32px;
                 box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .score-row { display: grid; grid-template-columns: 180px 1fr 50px;
               align-items: center; gap: 14px; margin-bottom: 12px; }
  .score-row:last-child { margin-bottom: 0; }
  .score-name { font-size: 14px; font-weight: 500; }
  .score-name.winner { color: #FF9900; font-weight: 700; }
  .bar-track { background: #f3f4f6; border-radius: 6px; height: 10px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 6px; background: #d1d5db; }
  .bar-fill.winner { background: #FF9900; }
  .score-val { font-size: 14px; font-weight: 600; text-align: right; color: #6b7280; }
  .score-val.winner { color: #FF9900; }
  .elim-label { font-size: 11px; color: #ef4444; font-style: italic;
                grid-column: 2 / 4; margin-top: -8px; margin-bottom: 4px; }

  /* ── Diagram card ── */
  .diagram-card { background: #fff; border-radius: 12px; padding: 28px 32px;
                  box-shadow: 0 2px 8px rgba(0,0,0,.06); overflow: auto; }
  .mermaid { min-height: 200px; }
  .diagram-ascii { font-family: monospace; font-size: 12px; color: #374151;
                   white-space: pre; background: #f9fafb; padding: 16px;
                   border-radius: 8px; margin-top: 12px; display: none; }

  /* ── Why card ── */
  .why-card { background: #fff; border-radius: 12px; padding: 28px 32px;
              box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .why-card ol { padding-left: 20px; }
  .why-card li { margin-bottom: 10px; font-size: 14px; color: #374151; }
  .why-card li strong { color: #1a1a2e; }

  /* ── Comparison table ── */
  .table-card { background: #fff; border-radius: 12px; padding: 28px 32px;
                box-shadow: 0 2px 8px rgba(0,0,0,.06); overflow-x: auto; }
  /* base table/th/td/tr styles come from the shared shell CSS inlined above */
  .check  { color: #16a34a; font-weight: 700; }
  .cross  { color: #9ca3af; }
  .winner-col { background: #fffbeb; }

  /* ── Services grid ── */
  .services-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
                   gap: 16px; }
  .service-card { background: #fff; border-radius: 10px; padding: 20px;
                  box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .service-card.addon-card { border-top: 3px solid #FF9900; }
  .service-card .svc-name { font-size: 14px; font-weight: 700; color: #1a1a2e;
                             margin-bottom: 6px; }
  .service-card .svc-badge { font-size: 11px; font-weight: 600; border-radius: 4px;
                              padding: 2px 8px; display: inline-block; margin-bottom: 8px; }
  .badge-free  { background: #f0fdf4; color: #15803d; }
  .badge-addon { background: #fff7ed; color: #c2410c; }
  .service-card .svc-desc { font-size: 13px; color: #6b7280; line-height: 1.5; }

  /* ── Cost card ── */
  .cost-card { background: #fff; border-radius: 12px; padding: 28px 32px;
               box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .cost-band { font-size: 32px; font-weight: 700; color: #1a1a2e; }
  .cost-label { font-size: 13px; color: #6b7280; }
  .cost-note  { font-size: 13px; color: #6b7280; margin-top: 10px;
                padding-top: 10px; border-top: 1px solid #f0f0f0; }
  .assumption-list { list-style: disc; padding-left: 18px; font-size: 13px;
                     color: #6b7280; margin-top: 8px; }

  /* ── Next steps ── */
  .steps-card { background: #fff; border-radius: 12px; padding: 28px 32px;
                box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .step-item { display: flex; gap: 16px; margin-bottom: 16px; }
  .step-item:last-child { margin-bottom: 0; }
  .step-num { width: 28px; height: 28px; border-radius: 50%; background: #FF9900;
              color: #fff; font-weight: 700; font-size: 13px;
              display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .step-text strong { font-size: 14px; display: block; margin-bottom: 3px; }
  .step-text p { font-size: 13px; color: #6b7280; }
  .dl-link { font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
             color: #b45309; text-decoration: none; border-bottom: 1px solid transparent;
             transition: border-color .15s; }
  .dl-link:hover { border-bottom-color: #b45309; }
  .dl-link::after { content: " ↓"; color: #9ca3af; font-size: 11px; }

  /* ── Footer ── */
  .report-footer { margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb;
                   font-size: 12px; color: #9ca3af; }

  /* ── Print ── */
  @media print {
    body { background: #fff; }
    .site-header { background: #1a1a2e !important; -webkit-print-color-adjust: exact; }
    .bar-fill.winner { background: #FF9900 !important; -webkit-print-color-adjust: exact; }
  }
</style>
</head>
<body>

<!-- HEADER -->
<header class="site-header">
  <div class="inner">
    <h1>AWS Agent Architecture Recommendation</h1>
    <div class="meta">
      Generated {{ RUN_DATE }}<br>
      Run ID: {{ RUN_ID }}
    </div>
  </div>
</header>

<div class="page">

<!-- HELP BANNER — shared CTA at the TOP of the report.
     Load references/report-help-banner.md and emit its HTML block (with {{ HELP_URL }}
     substituted). Also copy its CSS rules into the <style> block above. -->
{{ HELP_BANNER_HTML from references/report-help-banner.md }}

<!-- WARNINGS (only if WARNINGS non-empty) -->
{{ FOR EACH warning IN WARNINGS }}
<div class="banner warning">
  <span class="banner-icon">⚠️</span>
  <span>{{ warning }}</span>
</div>
{{ END FOR }}

<!-- FedRAMP note (only if FEDRAMP_NOTE true) -->
{{ IF FEDRAMP_NOTE }}
<div class="banner fedramp">
  <span class="banner-icon">🔒</span>
  <span><strong>FedRAMP note:</strong> AgentCore FedRAMP authorization is in progress.
  For FedRAMP-required workloads, validate current status and consider GovCloud as
  a fallback before committing to AgentCore.</span>
</div>
{{ END IF }}

<!-- Region availability note (only if REGION_NOTE non-null) -->
{{ IF REGION_NOTE }}
<div class="banner info">
  <span class="banner-icon">📍</span>
  <span><strong>Region:</strong> {{ REGION_NOTE }}</span>
</div>
{{ END IF }}

<!-- I/O-wait TCO note (only if IO_WAIT_NOTE true) -->
{{ IF IO_WAIT_NOTE }}
<div class="banner tco">
  <span class="banner-icon">💡</span>
  <span><strong>TCO advantage:</strong> AgentCore charges $0 during model I/O wait
  (streaming, model latency, human typing pauses). For bursty or HITL workloads, a
  significant fraction of wall-clock time is idle — you only pay for active CPU.</span>
</div>
{{ END IF }}

<!-- HERO -->
<p class="section-title">Recommendation</p>
<div class="hero">
  <div class="hero-main">
    <div class="label">Recommended Runtime</div>
    <div class="runtime">{{ RUNTIME_DISPLAY }}</div>
    <div class="deployment">{{ DEPLOYMENT_MODEL_DISPLAY }}</div>
    <div class="model-row">
      <div class="model-label">Bedrock Model</div>
      <div class="model-name">{{ MODEL_DISPLAY }}</div>
      <div class="model-reason">{{ MODEL_REASONING }}</div>
    </div>
  </div>
  <div class="hero-services">
    <div class="label">AgentCore Services</div>
    {{ FOR EACH svc IN SERVICES }}
    <span class="service-tag {{ 'free' IF svc IS always-on ELSE 'addon' }}">
      {{ '✓' IF svc IS always-on ELSE '★' }} {{ SERVICE_DISPLAY_NAME(svc) }}
    </span>
    {{ END FOR }}
    <div style="margin-top:14px; font-size:12px; color:#9ca3af;">
      ✓ Always-on, free &nbsp;·&nbsp; ★ Enabled add-on
    </div>
  </div>
</div>

<!-- SCORES -->
<p class="section-title">Runtime Scores</p>
<div class="scores-list">
{{ FOR EACH (runtime, score, pct) IN SORTED_SCORES }}
  <div class="score-row">
    <div class="score-name {{ 'winner' IF runtime == VERDICT }}">
      {{ RUNTIME_DISPLAY_NAME(runtime) }}
      {{ IF runtime IN ELIMINATED }} &nbsp;<span style="font-size:11px;color:#ef4444;font-weight:400;">(eliminated)</span>{{ END IF }}
    </div>
    <div class="bar-track">
      <div class="bar-fill {{ 'winner' IF runtime == VERDICT }}"
           style="width:{{ pct }}%"></div>
    </div>
    <div class="score-val {{ 'winner' IF runtime == VERDICT }}">{{ score }}</div>
  </div>
  {{ IF runtime IN ELIMINATED }}
  <div class="elim-label">{{ ELIMINATED[runtime] }}</div>
  {{ END IF }}
{{ END FOR }}
</div>

<!-- DIAGRAM + WHY -->
<p class="section-title">Architecture &amp; Rationale</p>
<div class="two-col">
  <div class="diagram-card">
    {{ IF DIAGRAM_MERMAID }}
    <div class="mermaid">{{ DIAGRAM_MERMAID }}</div>
    <pre class="diagram-ascii" id="ascii-fallback">{{ DIAGRAM_ASCII }}</pre>
    {{ ELSE }}
    <pre class="diagram-ascii" style="display:block">{{ DIAGRAM_ASCII }}</pre>
    {{ END IF }}
  </div>
  <div class="why-card">
    <p style="font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;
              letter-spacing:.8px;margin-bottom:14px;">Why {{ RUNTIME_DISPLAY }}</p>
    <!-- Extract top 3 bullet points from recommendation.md Section 3 "wins because:" -->
    <ol>
      {{ TOP_3_WHY_BULLETS from recommendation.md Section 3 }}
    </ol>
    {{ IF IO_WAIT_NOTE }}
    <div style="margin-top:16px;padding:12px;background:#f0fdf4;border-radius:8px;
                font-size:13px;color:#166534;">
      💡 <strong>I/O-wait billing edge:</strong> you pay $0 while the model generates
      or users type — real cost advantage for interactive chat.
    </div>
    {{ END IF }}
  </div>
</div>

<!-- COMPARISON TABLE -->
<p class="section-title">Runtime Comparison</p>
<div class="table-card">
<!-- Extract the comparison table from recommendation.md Section 6 and render it here.
     Mark the VERDICT column with class="winner-col", ✅ with class="check", ❌ with class="cross" -->
  <table>
    <thead>
      <tr>
        {{ FOR EACH col IN TABLE_COLUMNS }}
        <th {{ 'class="winner-col"' IF col == VERDICT_DISPLAY }}>{{ col }}</th>
        {{ END FOR }}
      </tr>
    </thead>
    <tbody>
      {{ FOR EACH row IN TABLE_ROWS }}
      <tr>
        {{ FOR EACH cell IN row }}
        <td {{ 'class="winner-col"' IF col == VERDICT_DISPLAY }}>
          {{ IF cell == "Yes" OR cell == "✅" }}<span class="check">✓</span>
          {{ ELSE IF cell == "No" OR cell == "❌" }}<span class="cross">—</span>
          {{ ELSE }}{{ cell }}{{ END IF }}
        </td>
        {{ END FOR }}
      </tr>
      {{ END FOR }}
    </tbody>
  </table>
</div>

<!-- SERVICES DETAIL -->
<p class="section-title">AgentCore Services</p>
<div class="services-grid">
{{ FOR EACH svc IN SERVICES }}
<div class="service-card {{ 'addon-card' IF svc IS NOT always-on }}">
  <div class="svc-name">{{ SERVICE_DISPLAY_NAME(svc) }}</div>
  <span class="svc-badge {{ 'badge-free' IF svc IS always-on ELSE 'badge-addon' }}">
    {{ 'Always-on · Free' IF svc IS always-on ELSE 'Enabled' }}
  </span>
  <div class="svc-desc">{{ SERVICE_DESCRIPTION(svc) }}</div>
</div>
{{ END FOR }}
</div>

<!-- COST (only if estimate.json exists) -->
{{ IF COST_BAND }}
<p class="section-title">Cost Estimate</p>
<div class="cost-card">
  <div class="cost-band">${{ COST_BAND }}<span style="font-size:16px;font-weight:400;color:#6b7280;">/month</span></div>
  <div class="cost-label">Order-of-magnitude estimate — not a quote</div>
  {{ IF COST_ASSUMPTIONS }}
  <ul class="assumption-list">
  {{ FOR EACH a IN COST_ASSUMPTIONS }}
    <li>{{ a }}</li>
  {{ END FOR }}
  </ul>
  {{ END IF }}
  <div class="cost-note">~90% of cost is model tokens. AgentCore compute charges only for
  active CPU time — $0 during model I/O wait. Detailed TCO analysis is available in the
  migration plan.</div>
</div>
{{ END IF }}

<!-- ARTIFACTS -->
<!-- The report HTML sits inside $RUN_DIR, so artifact links are RELATIVE to it
     (drop the $RUN_DIR/ prefix). The download attribute makes the browser save the
     file instead of navigating to it. Scaffold is a directory → link the folder (no
     download attr; browsers can't download a dir, the link just opens it). -->
<p class="section-title">Artifacts</p>
<div class="steps-card">
  <div class="step-item">
    <div class="step-num" style="background:#6b7280; font-size:11px;">📄</div>
    <div class="step-text">
      <strong>Recommendation document</strong>
      <p><a class="dl-link" href="recommendation.md" download>recommendation.md</a></p>
    </div>
  </div>
  <div class="step-item">
    <div class="step-num" style="background:#6b7280; font-size:11px;">📐</div>
    <div class="step-text">
      <strong>Architecture diagram</strong>
      <p><a class="dl-link" href="diagram.md" download>diagram.md</a></p>
    </div>
  </div>
  {{ IF SCAFFOLD_EXISTS }}
  <div class="step-item">
    <div class="step-num" style="background:#6b7280; font-size:11px;">🗂</div>
    <div class="step-text">
      <strong>Starter scaffold</strong>
      <p>List each file in <code>$RUN_DIR/scaffold/</code> as its own
      <code>&lt;a class="dl-link" href="scaffold/FILENAME" download&gt;scaffold/FILENAME&lt;/a&gt;</code>
      link (browsers cannot download a whole directory, so link each file individually).</p>
    </div>
  </div>
  {{ END IF }}
  {{ IF MANAGED_ALTERNATIVE == "bedrock_managed" }}
  <div class="step-item" style="margin-top:16px; padding-top:16px; border-top:1px solid #f3f4f6;">
    <div class="step-num" style="background:#6b7280;">i</div>
    <div class="step-text">
      <strong>Alternative: Bedrock Managed Agents</strong>
      <p>No-code, fully-managed alternative available in us-east-1. Less model flexibility
      and no code export. AgentCore recommended for portability and control.</p>
    </div>
  </div>
  {{ END IF }}
</div>

<!-- FOOTER -->
<div class="report-footer">
  {{ VOLATILE_FACTS_TEXT from recommendation.md Section 12 freshness footer }}
  &nbsp;·&nbsp; This report is a draft for review.
</div>

</div><!-- .page -->

<script>
mermaid.initialize({ startOnLoad: true, theme: 'neutral',
  themeVariables: { primaryColor: '#FF9900', primaryTextColor: '#1a1a2e',
                    primaryBorderColor: '#FF9900', lineColor: '#6b7280' } });
// Fallback: if Mermaid fails to render, show ASCII
document.addEventListener('DOMContentLoaded', function() {
  setTimeout(function() {
    var diagrams = document.querySelectorAll('.mermaid');
    diagrams.forEach(function(el) {
      if (!el.querySelector('svg')) {
        var ascii = document.getElementById('ascii-fallback');
        if (ascii) ascii.style.display = 'block';
      }
    });
  }, 2000);
});
</script>
</body>
</html>
```

## Step R3 — Open in browser

After writing the file, open it immediately:

```bash
open "$RUN_DIR/recommendation-report.html"
```

On Linux: `xdg-open "$RUN_DIR/recommendation-report.html"`

If the command fails (no GUI environment), output the path:

```
Recommendation report ready — open in your browser:
file://{{ RUN_DIR }}/recommendation-report.html
```

## Step R4 — Report completion

Output to the parent `generate.md`:

```
Recommendation report written to {{ RUN_DIR }}/recommendation-report.html
```

Do NOT update `.phase-status.json` — the parent `generate.md` handles phase completion.
