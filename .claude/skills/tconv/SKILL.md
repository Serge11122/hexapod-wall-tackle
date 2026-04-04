---
name: tconv
description: "Timer cycle step 1: Conviction — analyze, pivot, enforce, propagate, tag"
user-invocable: true
---

You are executing ONE step. Dispatch all analysis work to an Opus subagent, then log and exit. Do NOT create new `.md` files unless a specific output file is named in these instructions.

Invoke the analysis sub-agent using the Agent tool with `subagent_type: "general-purpose"`, `model: "opus"`.
The subagent runs on Opus model with medium effort (adaptive thinking enabled by default on Opus).

Agent prompt — pass the full instructions below verbatim:

---
## Instructions

Do NOT create new `.md` files unless a specific output file is named in these instructions.

1. **Read convictions:**
   - Read ALL `.md` files in `.manager/convictions/` folder — investigate every violation listed in every conviction file found

2. **Read project state:**
   - Read `.manager/goal_tracker.md` for current goals
   - Read `.manager/goals.md` for high-level objectives
   - Read `.manager/deep_analysis_results.md` if it exists (pre-launch violations from tdeep)
   - Read `.manager/kill_violations.md` if it exists (runtime violations from teta)

3. **Identify conviction violations:**
   - Check each violation listed in the conviction files against current project state
   - List all violations found

4. **Pivot and update:**
   - Update `.manager/goal_tracker.md` — replace stale goals with conviction-driven goals. Remove "FINAL/IDLE/awaiting" language. Assert the correct path forward.
   - Update `.manager/memory_dev.md` — write clear tasks for dev based on conviction violations. Be specific: which files to change, what to import, what to delete.
   - Remove any old thoughts or memories that contradict conviction direction

5. **Propagate violations into rules:**
   - Read `.claude/rules/general.md` and `CLAUDE.md`
   - For each conviction violation found, add or update a rule that prevents it in future runs
   - Keep rules concise. One line per rule. Add to existing sections, don't create new files.

6. **Tag models if needed:**
   - Check if any models need tagging (new best_model.pt since last tag). If yes, copy to tagged folder with version prefix. If nothing to tag, note "nothing to tag".

7. **Audit conviction test coverage:**
   - For each conviction file, check if violations are only static/grep-based or include runtime behavioral tests
   - Flag convictions that have only "check if code pattern X exists" violations but no "verify behavior Y at runtime" violations as having insufficient test coverage

8. **Expand violations with runtime checks:**
   - When a conviction has only static violations, add concrete runtime behavioral test violations to that conviction file
   - Static example: "No zstandard compression" (grep for zstd import) → Runtime: "Cache file must exist on disk at expected path in `.pt.zst` format before launch"
   - Static example: "No epoch-based training" (grep for `for epoch in range`) → Runtime: "Checkpoint must contain `global_step` field, not `epoch` field as primary counter"

9. **Improve tdeep test patterns:**
   - If tconv discovers a behavioral gap (tdeep missed a violation because it only grepped code), add the specific runtime test to the conviction's violations section so tdeep catches it next cycle

10. **Experiment failure analysis (CRITICAL for V13):**
   - Count consecutive smoke failures in goal_tracker results history
   - If 3+ consecutive failures with only hyperparameter changes → MUST assign an ARCHITECTURAL change to tdev (model size, compression layer, loss function, training approach). Write this explicitly in memory_dev.md: "ARCHITECTURAL CHANGE REQUIRED — hyperparameter tuning exhausted for this axis."
   - For each failure, extract the LEARNING: what does this tell us about the integration problem? Write the learning in goal_tracker.
   - Propose the next experiment based on accumulated learnings, not just "try lower X"
   - Read `conviction_v13_experimentation_strategy.md` for the list of untried architectural changes

11. **Time impact assessment (MANDATORY for every task):**
   - Before writing tasks to memory_dev.md, estimate time cost of each approach
   - Check: do existing assets (weights, caches, checkpoints) allow a faster path?
   - Prefer: append over rebuild, resume over restart, fine-tune over train-from-scratch, supplement over regenerate
   - Every task in memory_dev.md must include: "Estimated time: X min. Reuse: [what existing assets are used]."
   - If a task would take >1 hour and a <15 min alternative exists using existing assets, use the faster path
   - Read `conviction_time_efficiency.md` for the full time hierarchy

12. **Conviction mindset:**
   - Persist with conviction, but ITERATE on approach, not just parameters
   - If the same class of change fails 3 times, change the CLASS of change
   - The backbone signal is proven superior. The integration CAN work. But it may need a different architecture than what V10 uses.
   - Each model tag achieved required trying multiple approaches — not just tuning one approach repeatedly
   - Build incrementally on what works — don't reset to zero when you can build on top
---

**After the subagent returns:** write its results to `.manager/memory_dev.md` and update `.manager/goal_tracker.md` as instructed. Then log and exit.

**Log to `.manager/timer_cycle_log.md`** — MANDATORY, prepend ONE row to the table (after the header row). Format:

```
| [PST timestamp] | tconv | [current model] Val [X] vs anchor Val [Y] (gap: [Z]%) | [current model] test ann. [A]% vs V10 test ann. [B]% (gap: [C]%) | [1-2 sentence summary of what was analyzed, violations found, tasks assigned] |
```

Example row:
```
| 2026-04-03 14:32 PT | tconv | V13 Val Sharpe 0.572 vs V10 2.569 (gap: -78%) | V13 test ann. 12.3% vs V10 test ann. 31.4% (gap: -61%) | Analyzed 3 convictions, found 2 violations (cache hash, epoch loop). Assigned architectural change to tdev. |
```

Rules:
- Timestamp: run `TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT'` via Bash to get the real current time. NEVER infer or guess the timestamp from prior log entries.
- Goal Metric: current model name + its best metric vs anchor model + anchor metric + gap percentage
- Yearly Growth: current model test-period annualized return % vs V10 anchor test-period annualized return %. Source from goal_tracker.md or memory_dev.md. Write "no data yet" if not available.
- If no model metrics available yet, write "no metrics yet" / "no data yet"
- Prepend = insert after the header row (line 5), before any existing data rows. Newest first.
- ONE row only. No multi-line entries. No markdown headers. No blank lines between rows.

Do NOT write `.manager/timer_cycle_state.json` — timer-dev owns all state transitions. Timer-dev detects when you finish (session IDLE) and advances the state automatically.

**You do NOT own the launch gate.** Do not write or overwrite `launch_commands.json` or `deep_analysis_results.md`. Those are written by tdev and tdeep respectively. Your output is `memory_dev.md` (tasks for tdev) and `goal_tracker.md` (pivot decisions).

Exit. Timer-dev detects IDLE and sends the next command.
