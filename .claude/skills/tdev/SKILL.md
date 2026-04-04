---
name: tdev
description: "Timer cycle step 2: Dev implements tasks from memory_dev.md"
user-invocable: true
---

You are executing ONE step. Invoke dev sub-agent, update state, exit. Do NOT create new `.md` files unless a specific output file is named in these instructions.

Read `.manager/memory_dev.md` for tasks written by tconv.

Invoke dev sub-agent using the Agent tool with `subagent_type: "general-purpose"`, `model: "sonnet"`.
The subagent runs on Sonnet model with moderate thinking effort enabled.

Agent prompt:
"You are the RLQuest Developer sub-agent.
Do NOT create new `.md` files unless a specific output file is named in your instructions.
Read `.manager/memory_dev.md` for pending tasks and conviction violations to fix.
Read `.manager/goal_tracker.md` and `.manager/goals.md` for context.
Read `.manager/convictions/conviction_v13_experimentation_strategy.md` for experimentation scope.

Implement the tasks listed in memory_dev.md. Fix conviction violations.

SCOPE: You may make ARCHITECTURAL changes (model architecture, loss function, compression layer, training approach), not just hyperparameter tweaks. If memory_dev.md says to change architecture, DO IT — create new model variants, modify forward(), change loss components, add/remove layers. Use `firstrate_portfolio/v13/experiments/` for variant configs if testing multiple approaches.

After 3+ consecutive smoke failures on hyperparameter-only changes, you MUST propose and implement an architectural change. Read the experiment log in goal_tracker.md to understand what has been tried and what the failures teach.

TIME EFFICIENCY (MANDATORY — read conviction_time_efficiency.md):
Before implementing, check for reusable assets:
- Existing weights (best_model.pt, checkpoints) → resume or transfer learn, don't train from scratch
- Existing cache → extend with supplements, don't regenerate
- Existing checkpoint → continue from it with new config, don't restart from step 0
- If adding a data field → side-cache supplement (minutes), never modify main cache code (hours rebuild)
- If training new architecture → initialize from existing weights where layers overlap
- If retraining backbone → load existing best_model.pt + add new loss head, don't random init
- NEVER choose an approach that costs hours when a minutes-cost alternative exists using existing assets

CRITICAL RULES:
- You may ONLY run unit tests (<2 min). 20-MINUTE TIMEOUT.
- NEVER execute nohup, NEVER launch training/data processes. Write launch commands to launch_commands.json with 'launched': false. Timer-dev validates and launches.
- NEVER mark 'launched': true in launch_commands.json. Only timer-dev marks launched.
- NEVER run 'nohup ... &' for any training, data processing, or long-running script.
- If you find yourself typing 'nohup' — STOP. Write the command to launch_commands.json instead.

LAUNCH_COMMANDS.JSON — MANDATORY FIELD NAMES (wrong names block launch immediately):
- 'module': dot-separated Python module path — e.g. 'firstrate_learning.v5_wrank.train' (NOT 'command', NOT a shell string)
- 'script_file': full workspace-relative path with ALL directory components — e.g. 'firstrate_learning/v5_wrank/train.py' (NOT 'v5_wrank/train.py', NOT a short path)
- 'flags': JSON array of strings — e.g. ['--smoke-test'] (NOT a joined string)
- 'log': full workspace-relative log path — e.g. 'firstrate_learning/v5_wrank/train.log'
- 'launched': false (always — timer-dev sets true after launch)
Before writing, use Glob to verify 'script_file' exists on disk. If the path is wrong, the launch is blocked.
Write results back to '.manager/memory_dev.md'.
Report: what you did, what you changed, hypothesis, time estimate, assets reused, launch commands written (NOT executed)."

**After dev returns:**

Write results to `.manager/memory_dev.md` (what was done, what remains).

**If dev returned launch commands:** Write them to `.manager/launch_commands.json` with `expect` field so teta knows what to monitor:
```json
[{
  "module": "firstrate_portfolio.v10_fix2a_sh96_wh96.train",
  "script_file": "firstrate_portfolio/v10_fix2a_sh96_wh96/train.py",
  "flags": ["--prove-out"],
  "log": "firstrate_portfolio/v10_fix2a_sh96_wh96/output/train.log",
  "expect": {
    "log_file": "firstrate_portfolio/v10_fix2a_sh96_wh96/output/train.log",
    "checkpoint_dir": "firstrate_portfolio/v10_fix2a_sh96_wh96/models/run_*",
    "checkpoint_file": "latest_checkpoint.pt",
    "cache_files": [],
    "min_gpu_pct": 50,
    "max_idle_minutes": 10
  }
}]
```
Timer-dev reads this JSON to securely launch nohup processes. The `expect` field is read by teta during monitoring.

**Log to `.manager/timer_cycle_log.md`** — MANDATORY, prepend ONE row to the table (after the header row). Format:

```
| [PST timestamp] | tdev | [current model] Val [X] vs anchor Val [Y] (gap: [Z]%) | [current model] test ann. [A]% vs V10 test ann. [B]% (gap: [C]%) | [1-2 sentence summary: what was implemented, launch commands written or not] |
```

Rules:
- Timestamp: run `TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT'` via Bash to get the real current time. NEVER infer or guess the timestamp from prior log entries.
- Goal Metric: current model + best metric vs anchor + gap. Use latest metrics from goal_tracker.md or memory_dev.md.
- Yearly Growth: current model test-period annualized return % vs V10 anchor test-period annualized return %. Source from goal_tracker.md or memory_dev.md. Write "no data yet" if not available.
- Prepend = insert after header row, before existing data rows. Newest first.
- ONE row only.

Do NOT write `.manager/timer_cycle_state.json` — timer-dev owns all state transitions. Timer-dev detects when you finish (session IDLE), checks if `launch_commands.json` has unlaunched commands, and advances to tdeep (step 3) or tconv (step 1) accordingly.

**Your job ends at writing `launch_commands.json`.** You do NOT launch processes. You do NOT run tdeep. In auto mode (tdevauto), tdevauto will route to tdeep on the next tick after timer-dev advances state to step 3. The actual process launch only happens after tdeep writes `deep_analysis_results.md` with `RECOMMENDATION: LAUNCH`.

Exit. Timer-dev detects IDLE and sends the next command.
