# Phase: Turn 1 — Entry Point + Background

## Step 1 — Create the run directory
Generate a run id from the current time as `MMDD-HHMM`. Create `.agent-advisor/<run_id>/`
and a `.agent-advisor/.gitignore` containing `*` (so run state is never committed).

## Step 2 — Ask two questions with AskUserQuestion
Ask BOTH in one AskUserQuestion call (two questions):

**Q1 — Starting point** (header "Starting point"):
- Build from scratch — I have an idea, no code  → `build_scratch`
- Deploy existing code — I have working agent code  → `build_deploy`
- Migrate — I have agents running elsewhere  → `migrate`
- Add capabilities — already on AWS, want to add services  → `add_capabilities`

**Q2 — Your background** (header "Background"):
- Technical (engineer/developer)  → `technical`
- Business-leaning (founder/PM/non-technical)  → `business`
- Mixed team  → `business` (start in business language, add technical detail on request)

## Step 3 — Handle add_capabilities
If Q1 == add_capabilities: tell the user this path is a separate skill and to invoke
`/agent-advisor:add-capabilities`. Do not continue this skill's flow.

## Step 4 — Open context prompt
Ask (plain text): "What can you tell me about your agent? Any files or existing code to
share? (Optional — say 'skip' to move on.)" Capture any framework/model/infra hints into
`$RUN_DIR/context-notes.md`.

## Step 5 — Write state
Write `$RUN_DIR/.phase-status.json` with `entry_point`, `audience` (from Q2), `turn1` =
completed. Set `discover` = pending if entry point is build_deploy/migrate AND the user
offered code, else `skipped`. Set all later phases pending.
