---
name: tdeep
description: "Timer cycle step 3: Deep analysis — check script for conviction violations before launch"
user-invocable: true
---

You are executing ONE step. Dispatch all analysis work to an Opus subagent, then log and exit. Do NOT create new `.md` files unless a specific output file is named in these instructions.

**You are the launch gate.** Timer-dev only launches a process after reading `deep_analysis_results.md` with `RECOMMENDATION: LAUNCH` and zero violations. If you do not write this file, the process is never launched. You MUST always write `deep_analysis_results.md` — even if analysis is trivial or violations are zero.

Invoke the analysis sub-agent using the Agent tool with `subagent_type: "general-purpose"`, `model: "sonnet"`.
The subagent runs on Sonnet model with moderate thinking effort enabled.

Agent prompt — pass the full instructions below verbatim:

---
## Instructions

Do NOT create new `.md` files unless a specific output file is named in these instructions.

1. **Read launch request:** Read `.manager/launch_commands.json` for the module, flags, and script path to analyze. Derive the script file from the module field (replace dots with `/`, append `.py`).

2. **Read the script:** Read the actual source file specified in the request. Also read any config files it imports from the same directory.

3. **Read ALL convictions:** Read every `.md` file in `.manager/convictions/` folder. For each conviction file, check every violation listed against the script code.

4. **Use tools to verify:** Use Grep, Read, Glob to check the actual code:
   - Grep for `for epoch` / `range(.*epoch` → epoch loop violation
   - Grep for `PATIENCE` / `patience_counter` → epoch patience violation
   - Grep for `gate_unit` / `gate_smoke` / `source_files_hash` → missing gate markers
   - Grep for `from .trade_execution` → local trade execution violation
   - Grep for `.pt.zst` / `zstd` → missing zstd compression
   - Grep for `total_steps` / `patience_steps` → step-based training check
   - Check if run directories exist for gate progression (smoke before prove-out, etc.)
   - Check source file timestamps vs run directory timestamps for stale gates

   **CRITICAL: Gate classification by launch type:**
   - `GATE_SMOKE_MISSING`: If launch is `--smoke-test`, this is NOT blocking. A smoke test creates the gate_smoke.json marker, so absence of the marker is expected on first smoke run. Classify as DEFERRED.
   - `GATE_SMOKE_MISSING`: If launch is `--prove-out` or `--full`, this IS blocking. Prove-out requires a valid prior smoke gate marker.
   - `GATE_UNIT_MISSING`: Always blocking for any gate above unit test.

5. **Also check standard pre-launch gates:**
   - **RESUMABLE**: Saves checkpoints AND loads on --resume?
   - **FAIL_FAST**: Validates dims/files/config BEFORE expensive loading?
   - **GATE_PROGRESSION**: Required prerequisite run dirs exist with valid timestamps?

6. **Runtime behavior tests and live execution monitoring (COMBINED — must complete within 2 minutes total):**

Run the script once with resource monitoring. Do NOT run unit test twice. **Total time budget for this step: 2 minutes.** The unit test must be run ONCE here; use that run for both validation and resource monitoring.

   **6a. Start unit test with resource monitoring:**
   ```bash
   timeout 120 firstrate_learning/.venv/bin/python -u -m <module> --unit-test > /tmp/tdeep_unit.log 2>&1 &
   UNIT_PID=$!
   ```

   **6b. Sample resources ONCE, 10 seconds into the run:**
   ```bash
   sleep 10
   ps --ppid $UNIT_PID -o pid,rss --no-headers 2>/dev/null | wc -l  # worker count
   ps --ppid $UNIT_PID -o rss --no-headers 2>/dev/null | awk '{sum+=$1} END {printf "%.0f MB\n", sum/1024}'  # total worker RSS
   nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
   ```

   **6c. Wait for completion and check exit code (max 130s total):**
   ```bash
   wait $UNIT_PID 2>/dev/null
   echo "Exit code: $?"
   tail -20 /tmp/tdeep_unit.log
   ```

   **6d. Analyze results:**
   - Exit code 0 → BEHAVIOR_PASS
   - Non-zero exit code → BEHAVIOR_FAIL
   - Worker count: If >0, calculate: `worker_count × max_worker_rss`. If total > 50GB → RESOURCE_FAIL
   - GPU utilization: If 0% during unit test → RESOURCE_WARN (not blocking); if >50% → RESOURCE_PASS
   - Peak RSS from log: If >16GB → RESOURCE_WARN

   **Cache verification (fast pre-check):**
   - `ls` expected cache dirs (e.g., `cache/`, `chunks/`, model dirs). If missing, flag as informational (BEHAVIOR_SKIP).

   **Gate prerequisite verification:**
   - If launching `--smoke`, verify `gate_unit.json` marker exists in run dir.
   - If launching `--full` or `--prove-out`, verify the smoke gate marker exists.

   **Checkpoint loading test (skip if no prior checkpoint):**
   - If a checkpoint file exists: `timeout 30 .venv/bin/python -c "import torch; torch.load('<checkpoint>', map_location='cpu', weights_only=False); print('CHECKPOINT_OK')"`. Non-zero exit = BEHAVIOR_FAIL.

7. **Structural analysis (MANDATORY — run ALL these checks, show evidence):**

Do NOT skip this step. Do NOT say "structural analysis looks fine" without running the commands below and quoting specific code lines.

   **7a. Pool placement — run this:**
   ```bash
   grep -n "ProcessPoolExecutor\|ThreadPoolExecutor" <script_file>
   ```
   For EACH match: read 30 lines of context around it. Is the `ProcessPoolExecutor(` call INSIDE a `for` loop? Check: is there a `for` loop that encloses it? Quote the loop line number AND the pool line number.
   - Pool inside loop → STRUCTURAL_FAIL: "Pool created per-iteration at line N, inside loop at line M"
   - Pool outside all loops → STRUCTURAL_PASS

   **7b. Cache save placement — run this:**
   ```bash
   grep -n "save_backbone_cache\|save_cache\|torch.save.*cache\|json.dump.*manifest\|json.dump.*status" <script_file>
   ```
   For EACH save call: is it INSIDE the main processing loop (incremental save per chunk) or AFTER the loop (all-or-nothing)? Read the function that calls it. Quote the line numbers of the loop and the save.
   - Save only after loop → STRUCTURAL_FAIL: "All-or-nothing save at line N, after loop ending at line M"
   - Save inside loop per chunk → STRUCTURAL_PASS

   **7c. CPU/GPU pipelining — run this:**
   ```bash
   grep -n "ProcessPoolExecutor\|pool\.map\|torch\.no_grad\|\.to(device)\|\.cuda()" <script_file>
   ```
   Read the main processing function. Map the flow: where does CPU work happen, where does GPU work happen? Are they in the SAME loop body (sequential) or overlapped (pipelined)?
   - Same loop: `for q: [cpu_parse] → [gpu_inference]` → STRUCTURAL_FAIL: "Sequential CPU/GPU in loop at lines M-N. CPU idle during GPU, GPU idle during CPU."
   - Pipelined (ThreadPoolExecutor, asyncio, or producer-consumer) → STRUCTURAL_PASS

   **7d. Worker memory estimate — run this:**
   ```bash
   grep -n "max_workers\|n_workers\|cpu_count" <script_file>
   ```
   Find the worker count. Then check what data is loaded BEFORE the pool is created (arrays, models, etc.):
   ```bash
   grep -n "np\.load\|torch\.load\|np\.memmap\|open(" <script_file> | head -20
   ```
   Estimate: if N workers × parent RSS at fork time > 50GB → STRUCTURAL_FAIL: "Worker memory explosion risk: N workers × ~X GB = Y GB"

   **7e. Python loop accumulation — run this:**
   ```bash
   grep -n "\.append(\|\.extend(" <script_file> | head -20
   ```
   For each append in a data processing function: is it inside a loop that runs >1000 times? Could it be replaced with `np.concatenate`, `torch.cat`, or pre-allocated array?
   - Append in hot loop → STRUCTURAL_FAIL: "Python append at line N in loop over ~X items"
   - Vectorized accumulation → STRUCTURAL_PASS

   **7f. Data distribution consistency — run this:**
   ```bash
   grep -n "friday\|Friday\|is_friday\|weekday\|day_filter\|smoke.*only\|smoke.*limit" <script_file>
   ```
   Check: does smoke test use a DIFFERENT data subset structure than prove-out/full? (e.g., Friday-only dates vs all weekdays, different symbol counts that change the problem). If yes → STRUCTURAL_FAIL: "Smoke uses different data distribution than prove-out (line N). Smoke metrics will not predict prove-out performance."

   For EVERY check: quote the specific line numbers and code snippets as evidence. "STRUCTURAL_PASS — no issues found" is NOT acceptable without showing the grep output that proves it.

8. **Write results immediately (no further delays):**

Once steps 1-7 complete (unit test + structural analysis), write the results file WITHOUT additional monitoring loops or sleeps.

9. **Reporting results** — Each check reports one of:
   - `PASS` — evidence confirms expected behavior
   - `FAIL` — evidence contradicts conviction (blocks launch)
   - `SKIP` — not applicable (no prior run data, no cache expected, etc.)
   - `WARN` — caution flag, not blocking

10. **Write results** to `.manager/deep_analysis_results.md`:
```markdown
# Deep Analysis Results — [timestamp]
Script: [path]
Flags: [flags]

## Static Violation Checks
[VIOLATION_NAME]: YES or NO — evidence
...

## Runtime Behavior & Resource Tests
[TEST_NAME]: PASS / FAIL / SKIP / WARN — evidence + actual numbers
...

## Structural Analysis
[CHECK_NAME]: PASS / FAIL / WARN — evidence (file:line)
...

## Summary
TOTAL_VIOLATIONS: [static violations count]
TOTAL_BEHAVIOR_FAILURES: [runtime+resource failures count]
TOTAL_STRUCTURAL_FAILURES: [structural failures count]
TOTAL_BLOCKING: [sum of all failures — blocks launch if > 0]
RECOMMENDATION: LAUNCH or BLOCK
```

**CRITICAL: Write this file IMMEDIATELY after step 7 completes. Do not delay for any additional analysis or monitoring. The file must exist within 3 minutes of subagent start.**

11. **Log to `.manager/timer_cycle_log.md`** — MANDATORY, prepend ONE row to the table (after the header row). Format:

```
| [PST timestamp] | tdeep | [current model] Val [X] vs anchor Val [Y] (gap: [Z]%) | [current model] test ann. [A]% vs V10 test ann. [B]% (gap: [C]%) | [violations found / LAUNCH or BLOCK recommendation, key findings] |
```

Rules:
- Timestamp: run `TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT'` via Bash to get the real current time. NEVER infer or guess the timestamp from prior log entries.
- Yearly Growth: current model test-period annualized return % vs V10 anchor test-period annualized return %. Source from goal_tracker.md or memory_dev.md. Write "no data yet" if not available.
- Prepend = insert after header row, before existing data rows. Newest first.
- ONE row only.

Do NOT write `.manager/timer_cycle_state.json` — timer-dev reads the results file directly.
---

**After the subagent returns:** write the `deep_analysis_results.md` it produced (or confirm it wrote it). Then log and exit.
