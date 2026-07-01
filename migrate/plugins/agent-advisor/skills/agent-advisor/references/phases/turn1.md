# Phase: Turn 1 — Entry Point + Background

## Step 1 — Create the run directory
Generate a run id from the current time as `MMDD-HHMM`. Create the run directory under the
**user's current working directory** (run `pwd` and anchor to it) — NOT the plugin install tree.
So: `<cwd>/.agent-advisor/<run_id>/`, plus `<cwd>/.agent-advisor/.gitignore` containing `*` (so
run state is never committed). All later `$RUN_DIR` references point here.

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
`/agent-advisor:add-capabilities`. Then STOP — do not continue this skill's flow and do NOT
write `.phase-status.json` (so a later resume doesn't re-enter this skill mid-flow). It is fine
to leave the empty run directory; the separate skill creates its own.

## Step 4 — Open context prompt
Ask (plain text): "What can you tell me about your agent? Any files or existing code to
share? (Optional — say 'skip' to move on.)" Capture any framework/model/infra hints into
`$RUN_DIR/context-notes.md`.

For `build_deploy` / `migrate`, **explicitly ask for the code path** ("Where's your agent code?
A directory path lets me detect your framework/model and skip questions."). Discover runs only
if a path is given; if the user declines a path, note it and set `discover = skipped` in Step 5.

## Step 5 — Write state
Write `$RUN_DIR/.phase-status.json` with `entry_point`, `audience` (from Q2), `turn1` =
completed. Set `discover` = pending if entry point is build_deploy/migrate AND the user
offered a code path, else `skipped`. Set all later phases (`clarify`, `clarify_pass2`, `design`,
`estimate`, `generate`) to pending.
