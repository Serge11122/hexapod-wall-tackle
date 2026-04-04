---
name: tdevauto
description: "Auto dev cycle — reads state and delegates to tconv, tdev, or tdeep automatically"
user-invocable: true
---

You are the autonomous dev cycle router. You read the current pipeline state and delegate to the correct component skill — **without clearing context**. You run continuously in a persistent session. Do NOT create new `.md` files unless a specific output file is named in these instructions.

## Decision Logic

Read `.manager/timer_cycle_state.json` to determine `next_step` and `status`.

Then read `.manager/memory_dev.md` for current task context.

### Route based on `next_step`:

**`next_step = 1`** → Run `/tconv`

Conditions that indicate tconv is needed:
- next_step is 1 (normal post-completion routing)
- status is `killed_violations`, `process_completed`, `no_launch`, `launch_blocked`, `watchdog_reset`, `reset`, or `tconv_complete` is NOT yet done this cycle

**`next_step = 2`** → Run `/tdev`

Conditions that indicate tdev is needed:
- next_step is 2 (tconv completed, implementation work pending)
- memory_dev.md has unimplemented tasks (no launch_commands.json yet, or tasks marked as pending)

**`next_step = 3`** → Run `/tdeep`

Conditions that indicate tdeep is needed:
- next_step is 3 (tdev wrote launch_commands.json, needs pre-launch validation)
- `.manager/launch_commands.json` exists

**`next_step` missing or unknown** → Run `/tconv` (safe default).

## Override Rules

**Run `/tconv` instead of the default if ANY of these are true:**
- status contains `killed` or `violation`
- status is `launch_blocked` and `.manager/deep_analysis_results.md` shows RECOMMENDATION: BLOCK
- `.manager/kill_violations.md` exists (even if next_step is 2 or 3)
- memory_dev.md says "STUCK" or "3+ consecutive failures" or "ARCHITECTURAL CHANGE REQUIRED"
- It has been >3 cycles since a LAUNCH (read `.manager/timer_cycle_log.md` — count rows since last LAUNCH row)

**Run `/tdeep` instead of `/tdev` if:**
- next_step is 2 AND `.manager/launch_commands.json` already exists (tdev already ran this cycle, wrote launch commands but timer advanced state back to 2 — skip straight to tdeep)

**Run `/tdev` instead of `/tconv` if:**
- next_step is 1 AND memory_dev.md has clear, actionable tasks that are NOT yet implemented AND status is NOT `killed_violations`
- i.e., tconv already ran (memory_dev.md is populated with fresh tasks) but tdev hasn't run yet. Check goal_tracker.md — if it has a very recent update (within last cycle) and memory_dev.md has specific pending tasks, skip tconv and go directly to tdev.

## Launch Gate — CRITICAL

**Timer-dev only launches a process after reading `deep_analysis_results.md` with `RECOMMENDATION: LAUNCH` and zero violations.** If tdeep never runs, `deep_analysis_results.md` is never written, and the process is never launched — regardless of what tdev put in `launch_commands.json`.

**Therefore:**

- **If `launch_commands.json` exists, tdeep MUST run.** Do not skip tdeep when launch_commands.json is present. No override rule (tconv, "nothing to do", etc.) may bypass tdeep when there are pending launch commands.
- **If tdev ran but found no work to do** (no changes, no launch_commands.json written): do NOT run tdeep. Timer-dev will route back to step 1 naturally (no launch_commands.json → no step 3). This is correct — no launch needed.
- **If tdeep finds 0 violations**: it writes `RECOMMENDATION: LAUNCH` in `deep_analysis_results.md`. Timer-dev reads this and launches. This is the only path to a process launch.
- **If tdeep finds violations**: it writes `RECOMMENDATION: BLOCK`. Timer-dev routes back to step 1. tconv analyzes the violations next cycle.

## Execution

**Timer sends `/tdevauto` ONCE per cycle.** You must chain all applicable sub-skills in a single invocation before going IDLE. Do NOT exit after running tconv — continue to tdev, and then to tdeep if launch_commands.json is written. Timer-dev detects your IDLE and reads output files to determine what you did.

Invoke sub-skills using the Skill tool (do NOT send slash commands as text):
- To run tconv: use Skill tool with `skill: "tconv"`
- To run tdev: use Skill tool with `skill: "tdev"`
- To run tdeep: use Skill tool with `skill: "tdeep"`

### Chaining rules

After each skill completes, re-evaluate whether to chain:

1. **After tconv**: Check `.manager/memory_dev.md` for tasks written. If tasks exist → run tdev. If memory_dev.md has no actionable tasks (tconv only pivoted state) → exit.
2. **After tdev**: Check `.manager/launch_commands.json`. If it exists → run tdeep (MANDATORY — launch gate must always run before timer launches). If no launch_commands.json → exit.
3. **After tdeep**: Always exit. Timer-dev reads `deep_analysis_results.md` and decides whether to launch.

**Do NOT chain to a sub-skill if the override rules (above) redirect you.** For example, if after tdev you see kill_violations.md was written → do NOT run tdeep; instead run tconv.

### Full chain example (most common cycle)

```
tdevauto invoked (next_step=1)
  → run tconv (reads convictions, writes memory_dev.md tasks)
  → run tdev (implements tasks, writes launch_commands.json)
  → run tdeep (validates launch, writes deep_analysis_results.md)
  → EXIT (timer reads deep_analysis_results.md, launches if 0 violations)
```

### Partial chain examples

```
next_step=2, launch_commands.json already exists:
  → skip tconv, skip tdev → run tdeep → EXIT

next_step=2, no launch_commands.json:
  → run tdev → (if writes launch_commands.json) → run tdeep → EXIT
  → run tdev → (if no launch_commands.json written) → EXIT

next_step=3 (tdev ran in prior tick, launch_commands.json exists):
  → run tdeep → EXIT
```

### After chaining completes

Log what you ran and why to `.manager/timer_dev.log`:

```bash
TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M:%S PT'
```

Then exit. Timer-dev detects IDLE and reads output files to determine what happened.

## Notes

- **No /clear between calls** — you run in a persistent session. Context accumulates across ticks. This is intentional — it lets you see prior skill outputs for better routing decisions.
- **Chain all applicable skills in one invocation.** Timer sends `/tdevauto` once per cycle — not once per sub-skill. Do NOT exit after tconv expecting timer to re-send.
- **Trust the state file.** The timer-dev bash script manages all state transitions. Do not modify `timer_cycle_state.json`.
