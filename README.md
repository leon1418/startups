# kb-autoupdate state branch

Machine state for the GitHub Actions deployment of the knowledge auto-update pipeline.
`kb-state.json` holds the fact/source registries, per-source seen sets, and pins;
`runs/<runId>/` holds each run's raw results (the archive decisions.py reads).
Written by the workflow after every run — do not edit by hand while a run is active.
