---
name: teta
description: "Timer cycle step 4: ETA check — monitor process health, progress quality, expected outputs"
user-invocable: true
---

You are checking that the running process is alive, healthy, and making useful progress. Do this ONLY, update state, exit. Do NOT create new `.md` files unless a specific output file is named in these instructions.

## Instructions

1. **Check process alive:**
```bash
ps -eo pid,stat,etime,rss,args | grep python | grep -v grep | grep -v vscode | grep -v '^.*Z' | grep -E 'firstrate_|trade_|experiments'
```

**IF no live processes:** Report "No processes running. Monitoring complete." and exit. Do NOT write timer_cycle_state.json — timer-dev owns all state transitions.

**IF live processes found:** Report PID, elapsed, RSS, command.

2. **Read the active run pointer:**

Read `.manager/active_run_1.json` (replace `1` with your instance ID — use `1` if unknown). This file is written by timer-dev at the moment of launch and contains post-launch facts:
- `pid` — the actual training PID (authoritative)
- `module` — the Python module that was launched
- `flags` — the CLI flags used (e.g. `--prove-out --w-rank 0.3 --rank-loss-type listmle`)
- `log` — the log file path
- `smoke_dir` — the smoke run directory used as the gate for this prove-out (CRITICAL for gate checks)
- `launched_at` — UTC timestamp of launch
- `expect` — monitoring expectations (log_file, checkpoint_dir, min_gpu_pct, etc.)

If `.manager/active_run_1.json` does not exist, fall back to reading `.manager/launch_commands.json`. If neither exists, use the live process command line to infer the module and log path.

3. **Check infrastructure health:**

- **GPU**: MUST run `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader` THREE times, 5 seconds apart. Take the max reading. This is the ONLY authoritative GPU measurement. Do NOT trust GPU % values from the training log — log values measure Python wall-clock between cuda.synchronize() calls, which inflates to 100% even when actual GPU cores are idle. If all 3 nvidia-smi readings are below expected threshold, this IS a real GPU underutilization issue regardless of what the log claims. Flag as stalled.
- **Log progress**: `tail -20 <log_file>` — if log timestamp >10 min old or no recent output, flag.
- **Checkpoints**: Check expected checkpoint files exist. If process running >10 min with no checkpoint, flag.
- **Cache files**: Check expected cache/output files exist.
- **Memory**: `free -m` — if swap >4 GB, flag as thrashing.

4. **Check progress quality vs anchor (CRITICAL — KILL EARLY):**

**Anchor reference (V10 WH96 — the model to beat):**
- **Test Annual Return: 144.71%** — primary growth target
- **Test Cumulative Return: 1314%** over ~3 years
- Test Sharpe: **2.569**, Val Sharpe: 1.737
- Turnover: **0.057**, Max DD: **14.0%**
- Val Annual Return: 101.69%

Read the last 20-50 lines of the log file AND grep all `Val: Sh=` lines to see the full trend.

```bash
grep "Val: Sh=" <log_file>
grep "turnover=" <log_file> | tail -10
grep "step.*/" <log_file> | tail -1
```

**4a. Anchor comparison — KILL if not viable:**

Parse current step and total steps from log. Calculate progress percentage. Apply the TIGHTER thresholds for smoke experiments, looser for prove-out.

**For smoke tests (3000 steps, experiments — fail fast):**
- **At step 750 (25%)**: Val Sharpe MUST exceed **0.3**. If not → KILL.
- **At step 1500 (50%)**: Val Sharpe MUST exceed **0.7**. If not → KILL.
- **At any point**: If Val Sharpe drops >50% from peak for 3+ consecutive evals → KILL (collapse).
- **Turnover at any point**: If > **0.50** → KILL. Architectural change needed.

**For prove-out and full runs:**
- **At 25% of total steps**: Val Sharpe MUST exceed **1.0**. If not → KILL. (Anchor is 2.569)
- **At 50% of total steps**: Val Sharpe MUST exceed **1.5**. If not → KILL.
- **Turnover at any point**: If > **0.30** after 10% of steps → KILL.
- **Drawdown at any point**: If Val DD > **40%** consistently (3+ evaluations) → KILL. (Anchor is 14%.)

**4b. Trend analysis — KILL if flat or declining:**

Collect all `Val: Sh=` values from the log. If there are 5+ evaluation points:
- Calculate: is Val Sharpe **trending upward**? (last 3 readings > first 3 readings average)
- If Val Sharpe is **flat or declining** over 5+ consecutive evaluations → KILL. The model has plateaued at a level far below anchor.
- If Val Sharpe **peaked and then dropped >30%** from peak without recovery for 3+ evals → KILL. Model destabilized.

**4c. Standard failure modes (all process types):**
- **Metric collapse**: Key metric was good then dropped significantly, not recovered for 3+ evals → KILL.
- **Diverging loss**: Training loss increasing or NaN → KILL.
- **Negative metrics**: Val Sharpe goes negative after being positive → KILL.
- **Process hung**: Log stale >10 min → KILL.

**For data processing:**
- Throughput collapse, error accumulation, stale output, stuck on single item → KILL.

**Do NOT wait for patience timeouts.** Do NOT hope the model will recover. If the evidence at 25-30% of training shows the model is far below anchor with no upward trend, it will NOT catch up. Kill immediately and return compute to dev for iteration.

5. **Check conviction compliance at runtime (MANDATORY — run ALL these commands):**

Read `.manager/launch_commands.json` for the script path. Derive the module directory (e.g. `firstrate_portfolio/v13`).

**5a. Cache files — run this:**
```bash
ls -lah <module_dir>/cache/ 2>/dev/null || echo "NO_CACHE_DIR"
```
Report what you find. Then check:
- If NO cache files exist and process has been running >5 min → flag: "CACHE_MISSING: precompute running from scratch, no cache reuse"
- If cache files exist, check their timestamps with `stat -c '%Y %n' <file>`. If all timestamps are from THIS run (not older) → flag: "CACHE_NOT_REUSED: cache was rebuilt, not loaded from previous gate"
- If files are `.pt` instead of `.pt.zst` → flag: "CACHE_UNCOMPRESSED: not using zstd"

**5b. Checkpoint files — run this:**
```bash
ls -lah <module_dir>/models/run_*/ 2>/dev/null | head -20
stat -c '%Y %n' <run_dir>/latest_checkpoint.pt 2>/dev/null || echo "NO_CHECKPOINT_FILE"
stat -c '%Y %n' <run_dir>/best_model.pt 2>/dev/null || echo "NO_BEST_MODEL"
```
**Determine phase first** — grep the log to know if training has started:
```bash
grep -c "step.*/" <log_file> | tail -1
```
If step lines exist → training phase. If only "quarters" or "Loading" lines → precompute phase.

Report what you find. Then check:
- **During precompute**: no checkpoint expected. Note "precompute phase" and move on.
- **During training, no checkpoint exists**: If training started >5 min ago (first step line >5 min old) and no `latest_checkpoint.pt` → flag: "NO_CHECKPOINT_DURING_TRAINING"
- **During training, checkpoint exists but stale**: Get current step from log (`grep "step.*/" <log_file> | tail -1`). Get checkpoint mtime. If current step is >4000 steps ahead of last checkpoint mtime → flag: "CHECKPOINT_STALE: training at step N but checkpoint not updated since step M"
- **best_model.pt**: If training >10000 steps and no `best_model.pt` → flag: "NO_BEST_MODEL: model never improved past initial"

**5c. Gate markers — run this:**

For `--prove-out` runs: read `smoke_dir` from `.manager/active_run_1.json`. The `gate_smoke.json` must exist in THAT directory (the smoke run that was used as the gate), NOT in the current prove-out run directory. This is the authoritative source — do NOT check the current run directory or any other smoke directory.

```bash
# For --prove-out: check gate_smoke.json in smoke_dir from active_run pointer
ls -la <smoke_dir>/gate_smoke.json 2>/dev/null || echo "NO_SMOKE_GATE"
# For --smoke-test: check gate_unit.json in current run dir
ls -la <current_run_dir>/gate_unit.json 2>/dev/null || echo "NO_UNIT_GATE"
# For any run: list all gate markers in the relevant dir
ls -la <relevant_dir>/gate_*.json 2>/dev/null || echo "NO_GATE_MARKERS"
```

- If running `--smoke-test` and no `gate_unit.json` in current run dir → flag: "MISSING_UNIT_GATE"
- If running `--prove-out` and no `gate_smoke.json` in the `smoke_dir` from active_run pointer → flag: "MISSING_SMOKE_GATE: gate_smoke.json not found in smoke_dir=<path>"
- NEVER flag MISSING_SMOKE_GATE if `smoke_dir` is absent from active_run pointer — the field may be empty for legacy launches. Only flag if smoke_dir is set AND the file is missing.

**5d. Cross-gate cache reuse — run this:**
```bash
ls -lah <module_dir>/cache/*precompute* 2>/dev/null
```
- If running `--prove-out` or `--full` and a lower-gate cache exists (_smoke.pt.zst) but the process is recomputing from scratch (log shows "cache MISS" or "computing from scratch") → flag: "NO_CROSS_GATE_REUSE: smoke cache exists but prove-out is recomputing everything. Lower-gate data is a subset — should be loaded and extended, not discarded."
- If multiple gate-specific cache files exist with the same hash → flag: "REDUNDANT_PRECOMPUTE: same backbone hash cached separately per gate. Each gate recomputes instead of extending previous gate's cache."
- This is a conviction violation (#30). Do NOT excuse it as "by design" or "expected different sizes".

**5e. Time budget — check this:**
- Read the `flags` field from `.manager/active_run_1.json` (or `launch_commands.json` as fallback)
- If `--smoke-test` and process elapsed >25 min → flag: "SMOKE_OVER_BUDGET: approaching 30 min limit"
- If `--smoke-test` and process elapsed >30 min → KILL: write kill_violations.md

Do NOT skip step 5. Do NOT say "expected" or "normal" or "by design" for:
- Missing cache files — if lower-gate cache exists but current gate is recomputing, that's a violation
- Missing checkpoints during training — if step lines exist in log, checkpoint must exist
- Redundant cache files — if the same backbone is cached separately per gate, that's waste
Every flag must be backed by actual `ls` or `stat` command output, not assumptions.

6. **Report:**

Write status to `.manager/memory_dev.md` with:
- Process: PID, elapsed, RSS
- Infrastructure: GPU (3 readings), memory, swap
- Progress: step N/total, metrics trend
- **Conviction compliance**: list every 5a-5e check result (PASS/flag). Example:
  ```
  Cache: CACHE_NOT_REUSED (smoke cache exists but prove-out rebuilt from scratch)
  Checkpoint: NO_CHECKPOINT (12 min elapsed, still in precompute)
  Gate markers: gate_unit.json ✓, gate_smoke.json ✓
  Redundant cache: 2 files (_unit.pt.zst, _smoke.pt.zst) — no cross-gate reuse
  Time budget: 12/180 min (prove-out)
  ```

**Write `.manager/kill_violations.md` if ANY of these are true:**
- Smoke test elapsed >30 min
- Training phase started (step lines in log) AND no `latest_checkpoint.pt` after 5+ min of training
- Training phase started AND checkpoint mtime >10 min old (not being updated)
- Metrics collapsed (Sharpe went negative, loss NaN)
- Process hung (log stale >10 min)
- **Prove-out/full at 25%+ of steps AND Val Sharpe < 1.0** — model not viable vs anchor (2.569)
- **Prove-out/full at 50%+ of steps AND Val Sharpe < 1.5** — model not trending toward anchor
- **Turnover > 0.30 after 10%+ of steps** — architecturally broken (anchor is 0.057)
- **Val DD > 40% for 3+ consecutive evaluations** — unacceptable risk (anchor is 14%)
- **Val Sharpe flat or declining over 5+ evaluations** — model has plateaued below viable level
- **Val Sharpe dropped >30% from peak, not recovered for 3+ evals** — model destabilized

**If healthy:** Estimate ETA.

**Subagent escalation (on anomaly only):**
If you identify a complex anomaly that requires deeper investigation — ambiguous metric pattern, unexpected log structure, unclear conviction compliance edge case — spawn a Sonnet subagent:
- Agent tool: `subagent_type: "general-purpose"`, `model: "sonnet"`
- Thinking: disabled (mechanical investigation, no reasoning required)
- Effort: low
- Pass the specific anomaly context and the relevant log excerpt
- Merge the subagent's findings into your report before writing `memory_dev.md`

Do NOT spawn a subagent for normal healthy checks. Do NOT spawn for clear violations — just write `kill_violations.md` directly.

7. **Log to `.manager/timer_cycle_log.md`** — MANDATORY, prepend ONE row to the table (after the header row). Format:

```
| [PST timestamp] | teta | [current model] Val [X] vs anchor Val [Y] (gap: [Z]%) | [current model] test ann. [A]% vs V10 test ann. [B]% (gap: [C]%) | [process status: PID, step N/total, GPU%, healthy/killed/completed, key finding] |
```

Rules:
- Timestamp: run `TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT'` via Bash to get the real current time. NEVER infer or guess the timestamp from prior log entries.
- Goal Metric: parse latest Val Sharpe from training log, compare to V10 anchor (Sharpe 2.569)
- Yearly Growth: current model test-period annualized return % vs V10 anchor test-period annualized return %. Parse from training log or goal_tracker.md. Write "no data yet" if not available.
- Prepend = insert after header row, before existing data rows. Newest first.
- ONE row only.

Do NOT write `.manager/timer_cycle_state.json` — timer-dev owns all state transitions.

Exit.
