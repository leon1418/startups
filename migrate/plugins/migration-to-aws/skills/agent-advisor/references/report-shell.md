# Shared report shell — visual chrome

A single source of truth for the shared visual "chrome" of every HTML report in this skill
(recommendation-report.html, poc-report.html, temporal-migration-report.html). This is the
dark site-header, the section-title style, the alert banners, the base table, the page layout,
and the reset — the design-system frame that must look IDENTICAL across reports. Keeping it
here means these rules are maintained in ONE place, so the reports stop drifting.

Content-specific CSS (hero cards, score bars, service tags, diagram cards, cost cards, etc.)
does NOT live here — each report keeps its own content rules in its own generator.

## CSS (inline this block into each report's `<style>` block)

```css
  /* ── Reset & base ── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f4f6f8; color: #1a1a2e; font-size: 15px; line-height: 1.6; }

  /* ── Layout ── */
  .page { max-width: 1100px; margin: 0 auto; padding: 0 24px 80px; }

  /* ── Header ── */
  .site-header { background: #1a1a2e; color: #fff; padding: 20px 0; }
  .site-header .inner { max-width: 1100px; margin: 0 auto; padding: 0 24px;
                         display: flex; justify-content: space-between; align-items: center; }
  .site-header h1 { font-size: 20px; font-weight: 600; letter-spacing: -0.3px; }
  .site-header .meta { font-size: 12px; color: #8892a4; text-align: right; }

  /* ── Section titles ── */
  .section-title { font-size: 13px; font-weight: 700; text-transform: uppercase;
                   letter-spacing: 0.8px; color: #6b7280; margin: 40px 0 16px; }

  /* ── Banners ── */
  .banner { border-radius: 8px; padding: 14px 18px; margin-top: 20px;
            font-size: 14px; display: flex; gap: 12px; align-items: flex-start; }
  .banner.warning  { background: #fff7ed; border: 1px solid #fed7aa; color: #92400e; }
  .banner.info     { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
  .banner.tco      { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }
  .banner.fedramp  { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
  .banner-icon { font-size: 18px; flex-shrink: 0; }

  /* ── Base table ── */
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th { background: #f9fafb; color: #6b7280; font-weight: 600; font-size: 12px;
       text-transform: uppercase; letter-spacing: 0.5px; padding: 10px 14px;
       text-align: left; border-bottom: 2px solid #e5e7eb; }
  td { padding: 10px 14px; border-bottom: 1px solid #f3f4f6; color: #374151; }
  tr:last-child td { border-bottom: none; }

  /* ── Two-col layout ── */
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
```

## Mermaid script tag (part of the shared shell for any report with a diagram)

Any report that renders a Mermaid diagram loads the SAME SRI-pinned mermaid@10.9.3 script tag
in its `<head>` — copy it VERBATIM (the integrity hash must not change):

```html
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.min.js"
        integrity="sha384-R63zfMfSwJF4xCR11wXii+QUsbiBIdiDzDbtxia72oGWfkT7WHJfmD/I/eeHPJyT"
        crossorigin="anonymous"></script>
```

## Usage note

Each report generator inlines the CSS block above into its own `<style>` block, then adds its
OWN content-specific rules after it (hero/scores/why/service-tag/diagram for the recommendation
report; temporal-specific cards/callouts for the temporal report). The union of (this shell +
the report's own content CSS) must reproduce that report's full rule set — do not drop or
restyle a shared rule locally, or the reports drift again.

- **recommendation-report.html** — `references/phases/generate/generate-report.md` inlines this
  block plus its hero/scores/why/service-tag/diagram/cost/steps/footer/print rules.
- **temporal-migration-report.html** — `references/phases/temporal-worker/temporal-worker.md`
  Step 5 inlines this block plus any temporal-specific content rules; its tier tables use the
  shared `table` styles and its current→target diagram uses the shared mermaid tag.

The shared "Need help?" CTA banner is a separate single-source file
(`references/report-help-banner.md`); load it too. The shell here is the frame; the help banner
is the CTA that sits at the top of the page inside that frame.
