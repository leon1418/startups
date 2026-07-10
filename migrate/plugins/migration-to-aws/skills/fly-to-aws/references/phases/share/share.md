---
_phase: share
_title: "Share Plan (Optional)"
_requires_phase: generate
_input:
  - preferences.json
  - estimation-infra.json
_assemble:
  _file: phases/share/share-assemble.md
_produces:
  - share.json
_advances_to: complete
_preconditions:
  - _check_phase_completed: generate
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: share.json
    _on_failure: _halt_and_inform
  - _validate_json: share.json
    _on_failure: _halt_and_inform
  - _assert: "share.json has share_link_generated (boolean); if a link was generated, share_link_generated_at is non-null, else it is null"
    _on_failure: _halt_and_inform
_forbids_files:
  - "*.txt"
  - "terraform/**"
  - "k8s/**"
---

# Phase 6: Share Plan (Optional)

Generates a shareable migration-plan link for AWS partner matching. Fully
client-side — no data is sent to any server; the link is a URL fragment the
landing page decodes in the browser. This skill collects **no feedback
telemetry**.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Prerequisites

Read `$MIGRATION_DIR/.phase-status.json`. Verify `phases.discover == "completed"`.
If not: **STOP**. Output: "Share requires at least the Discover phase to be completed."

Read plugin version from the nearest `plugin.json` → `version` (fallback `0.0.0`).
Store as `$PLUGIN_VERSION`.

---

## Step 1: Generate Share Link

Required artifacts: `preferences.json`, `estimation-infra.json`. If missing, output
"Cannot generate share link — required artifacts not found." and skip to Step 2.

### Payload

```json
{
  "schema_version": "1.0",
  "plugin_version": "<$PLUGIN_VERSION>",
  "generated_at": "<ISO 8601 UTC>",
  "skill": "fly-to-aws",
  "clarify_answers": { "<question_id>": "<answer_value>" },
  "cost_summary": {
    "current_fly_monthly": "<from Part 1 of estimate or null>",
    "projected_aws_monthly": "<from estimation-infra.json>",
    "delta": "<projected - current or null>",
    "currency": "USD"
  },
  "detected_services": ["<process group names from inventory>"],
  "resource_names": [{ "type": "process_group", "name": "<group_name>" }],
  "workload_types": ["infra"],
  "spend_band": "<under-10k|10k-50k|50k-100k|over-100k|unknown>",
  "share_checkpoint": "<after_estimate|after_generate>",
  "phases_completed": ["<completed phases>"]
}
```

**Secret redaction**: Scan `clarify_answers` for AWS key IDs (`AKIA...`), private key
headers, passwords in connection strings, high-entropy tokens. Replace with
`"[REDACTED]"`.

**Encode**: Minify JSON → gzip → Base64URL. If > 8,192 chars, truncate `resource_names`,
then longest `clarify_answers`, then cap `detected_services` at 20. If still too large,
skip.

**URL**: `https://aws.amazon.com/startups/migrate/connect#<base64url_payload>`

Present the link to the user. Share link generation is **non-blocking** — failures
never halt the phase.

---

## Step 2: Write share.json

Write `$MIGRATION_DIR/share.json`:

```json
{
  "timestamp": "<ISO 8601>",
  "skill": "fly-to-aws",
  "phases_completed_at_share": ["<completed phases>"],
  "share_link_generated": true,
  "share_link_generated_at": "<ISO 8601 or null>",
  "share_checkpoint": "<after_estimate|after_generate or null>"
}
```

- If the link could not be generated (missing artifacts or too large):
  `"share_link_generated": false`, `share_link_generated_at: null`.

---

## Step 3: Update Phase Status and Mark Complete

**Output gate** — verify before updating:

- `share.json` exists

If gate fails: **STOP**. Output: "Share outputs are incomplete. Fix share artifacts before completion."

Phase Status Update (read-merge-write):

- `phases.share` → `"completed"`
- `current_phase` → `"complete"`
- `last_updated` → current ISO 8601

Emit:

```
HANDOFF_OK | phase=share | artifacts=share.json
```

Output: "Migration planning is complete."

Return control to SKILL.md. The migration is finished.
