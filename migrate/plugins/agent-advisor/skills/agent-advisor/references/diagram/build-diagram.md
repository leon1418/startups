# Generate sub-step: Build the architecture diagram

Produces `$RUN_DIR/diagram.md` (a Mermaid block + ASCII fallback), composed deterministically
from the scoring result.

## Step 1 — Run the composer
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT}/scripts python ${CLAUDE_PLUGIN_ROOT}/scripts/build_diagram.py \
  $RUN_DIR/scoring-result.json $RUN_DIR/pass2.json
```
This writes `$RUN_DIR/diagram.md` and prints `RESULT=ok RUNTIME=<id>`. If `pass2.json` is
absent (e.g. co_recommend not yet resolved), the composer treats it as empty.

## Step 2 — Embed into the recommendation
Insert the full contents of `$RUN_DIR/diagram.md` into Section 4 ("Architecture diagram") of
`$RUN_DIR/recommendation.md`. Do not hand-draw or edit the diagram — it is generated, so it
stays consistent with the scoring result.
