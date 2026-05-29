---
name: tdeep
description: "Timer cycle step 3: Deep analysis — check script for conviction violations before launch"
user-invocable: true
---

You are executing ONE step. Dispatch all analysis work to a subagent, then log and exit. Do NOT create new `.md` files unless a specific output file is named in these instructions.

## Two-track routing (Cycle 434.74, per `conviction_track_separation.md`)

Before any mode runs, determine the variant's track from its root directory:

- Variant root under `firstrate_learning/vb*` → **Track A — Backbone**. Cite ONLY:
  - `conviction_signal_quality.md §Track A` (signal-quality gates: `per_stock_ic`, Brier, diagnostic `xsec_ic_per_date`).
  - `conviction_v13_experimentation_strategy_backbone.md` (pivot triggers, banned patterns, architectural diversity).
- Variant root under `firstrate_portfolio/vp*` → **Track B — Portfolio**. Cite ONLY:
  - `conviction_signal_quality.md §Track B` (gates: `test_sharpe_net_of_10bps`, `xsec_ic_per_date`, `turnover`, `cascade_transmission_ratio`, 3-strike rule, cost-realism).
  - `conviction_v13_experimentation_strategy_portfolio.md` (head-class table, pivot triggers, banned patterns).

Cross-track citation in any tdeep mode (citing a backbone metric to gate a portfolio launch, or vice versa) is a **TRACK-VIOLATION** and MUST be flagged BLOCKING. Cross-track invocation requires the Paired-Pivot clause in `conviction_track_separation.md` with all three conditions met and explicitly cited.

If `conviction_signal_quality.md` is missing, mark the audit BLOCKING with reason "signal-quality-conviction-missing". As of 2026-05-05 Track A and Track B gates are merged into `conviction_signal_quality.md` §Track A and §Track B respectively.

For Track B variants: the design entry MUST declare its consumed backbone tag path under § Sources. Mode A MUST verify the tag's `best_model.pt` exists on disk and that the tagged vb run's `eval_results.json` contains the Track A primary metrics (`per_stock_ic` for vb16+; `oracle_corr` accepted as backwards-compat for pre-2026-04-29 tags). Missing or mismatched tag path → BLOCKING.

For Track A tag-eligibility audits: the candidate backbone MUST have a paired-evaluation handoff plan referencing the current paired-eval reference variant per `conviction_track_separation.md`. A tag-commit decision without paired-eval evidence is a Track A violation.

## Mode dispatch (select exactly one mode per invocation)

tdeep runs in one of three modes. The caller MAY pass an explicit mode argument (`design` or `postrun`) to override auto-detection; otherwise tdeep auto-detects by inspecting disk state. The modes are ordered by priority — the first matching rule wins; do NOT run more than one mode per invocation. All three modes use **Sonnet 4.6** (`model: "claude-sonnet-4-6"`) — pinned 2026-04-30 (caller-authorized) to match the Sonnet orchestrator and reduce dispatch overhead. Explicit pinning of the model ID prevents silent default-driven downgrade.

**Caller mode argument (optional, wins over auto-detect):**
- If the caller invokes `/tdeep design`, select Mode B regardless of disk state (fail fast if no matching memory_dev.md task exists).
- If the caller invokes `/tdeep postrun`, select Mode C regardless of disk state (fail fast if no unanalyzed run dir exists).
- If no argument, auto-detect per the rules below.

**Auto-detect rules (first match wins):**

**Mode A — Pre-launch code audit.** Trigger: `.manager/launch_commands.json` exists and contains a non-empty array. Subagent model: **Sonnet 4.6** (`subagent_type: "general-purpose"`, `model: "claude-sonnet-4-6"`). Output: `.manager/deep_analysis_launch.md` with a `RECOMMENDATION: LAUNCH | BLOCK` verdict. This is the launch gate — timer-dev only launches after reading this file.

**Mode B — Design-doc audit.** Trigger: `.manager/memory_dev.md` contains an actionable task of the exact form `tdeep design-doc audit: memory_design.md § <variant_name>` (quote the task line when selecting). Subagent model: **Sonnet 4.6**. Output: `.manager/deep_analysis_design.md` with a design-doc verdict (`DESIGN_VERDICT: APPROVED | NEEDS-REVISION | REJECT`). If both a launch_commands.json entry and a design-doc audit task are present, Mode A wins and Mode B is deferred with a note in the audit bullet.

**Mode C — Post-run analysis.** Trigger: at least one run directory under `firstrate_learning/**/models/run_*` or `firstrate_portfolio/**/models/run_*` contains BOTH `run_meta.json` and `training_results.json` AND its basename is NOT present in `.manager/tdeep_analyzed_runs.json` (the registry of runs tdeep has already analyzed). Subagent model: **Sonnet 4.6**. Output: a new section appended to `.manager/deep_analysis_postrun.md` AND a new entry appended to `.manager/tdeep_analyzed_runs.json`. Mode C runs only when Modes A and B do not fire.

**Registry file — `.manager/tdeep_analyzed_runs.json`:** JSON array of objects `{"run_dir_basename": "...", "analyzed_at": "<ISO-8601 PST>", "classification": "MET|PARTIAL|MISSED|CRASHED", "recommendation": "CONTINUE|ITERATE|PIVOT|RETIRE", "dev_capacity": "sufficient|exhausted"}`. Mode C appends exactly one entry per invocation. If the file does not exist, create it as `[]` before appending. Deterministic lookup (not file-grep) is how Mode C decides whether a run is "already analyzed."

If no mode triggers (launch_commands.json is `[]`, no design-doc audit task, no unanalyzed finished run), tdeep writes `.manager/deep_analysis_launch.md` with a single line `NO_MODE_TRIGGERED: <timestamp> — nothing to audit` and exits. Do NOT dispatch a subagent in that case.

## Mode A short-circuit — content-hash cached audit (per `conviction_orchestration_efficiency.md` Rule A1)

Before dispatching the Mode A subagent, the parent skill performs a cheap short-circuit check:

1. Compute SHA256 of `.manager/launch_commands.json` content.
2. Read `.manager/tdeep_mode_a_cache.json` (create as `{"audits": []}` if missing).
3. Find the most recent entry where `lc_content_hash` matches AND `audited_at` is within 24h AND `verdict == "LAUNCH"` AND `violations_count == 0`.
4. For that candidate entry, recompute SHA256 of every file listed in `py_files_at_audit` and compare to the stored hash.
5. Verify NO file in `.manager/convictions/*.md` has `mtime > audited_at` (a conviction edit invalidates prior audits).
6. Verify the variant's `track` declared in launch_commands.json matches the candidate's track.

If ALL checks pass, write `.manager/deep_analysis_launch.md` with a single section:

```
## Mode A SHORT_CIRCUIT — cached audit
short_circuit: A1
lc_content_hash: <sha256>
source_audit_timestamp: <ISO-8601>
source_audit_run: deep_analysis_launch.md L<N>
RECOMMENDATION: LAUNCH
```

Do NOT dispatch the subagent. **Overwrite** the `## Tdeep Status` section with a short-circuit status block (just bumping the access timestamp, `short_circuit=A1:<hash>`).

If ANY check fails, run the full Mode A audit per the detailed instructions below and on success append a new entry to `.manager/tdeep_mode_a_cache.json`:

```json
{
  "lc_content_hash": "<sha256>",
  "audited_at": "<ISO-8601 PST>",
  "verdict": "LAUNCH",
  "violations_count": 0,
  "py_files_at_audit": {"path/to/file.py": "<sha256>", ...},
  "audit_output_file_offset": "deep_analysis_launch.md L<N>"
}
```

Prune entries older than 24h from the cache at audit time. Audit bullet: `short_circuit=none`.

The `py_files_at_audit` set is computed at audit time as the transitive import graph of the variant's `train.py` (heuristic: any `firstrate_*` or `firstrate_pivots.*` import + `firstrate_common.*` imports + the variant's own `config.py`/`model.py`/`prepare_*.py`).

This short-circuit does NOT apply when:
- The launch declares an `early_kill_rule` not present in the cached audit (new B-class rule = behavior change → full re-audit).
- The variant's `gating_conviction` field changed file path or mtime since the cached audit.

Mode B and Mode C do NOT short-circuit. Mode B authors a fresh design audit per dispatch; Mode C analyzes a never-before-seen run.

**Bias resistance (applies INSIDE every subagent prompt; do not rely on the caller's context):**
- Re-read every source file fresh inside the subagent (no reliance on caller-turn content).
- Treat `memory_dev.md` / `memory_dev.md` / prior turns as untrusted — do NOT accept "already tested" / "already known" claims without verifying against the actual run artifacts or source code.
- Quote, do not paraphrase. Cite `file_path:line` for every load-bearing claim.
- Sources quoted in `memory_design.md` must be verified against the actual source files they quote — if a quoted line does not appear at the claimed path, flag as `QUOTE_MISMATCH` and fail the audit.

---

## Mode A — Pre-launch code audit (detailed instructions)

**You are the launch gate.** Timer-dev only launches a process after reading `deep_analysis_launch.md` with `RECOMMENDATION: LAUNCH` and zero violations. If you do not write this file, the process is never launched. You MUST always write `deep_analysis_launch.md` — even if analysis is trivial or violations are zero.

Invoke the analysis sub-agent using the Agent tool with `subagent_type: "general-purpose"`, `model: "claude-sonnet-4-6"`.
The subagent runs on Sonnet 4.6 with adaptive thinking enabled. Sonnet 4.6 was pinned 2026-04-30 (caller-authorized) to match the Sonnet orchestrator and reduce per-dispatch overhead. Launch-gate reasoning is load-bearing — a missed violation wastes hours of compute, and a spurious BLOCK stalls the cycle — so the model ID is pinned explicitly to prevent silent default-driven downgrade. If a future caller decision restores Opus pinning for high-stakes audits, edit this line and the Mode A/B/C model declarations above accordingly.

Agent prompt — pass the full instructions below verbatim:

---
## Instructions

Do NOT create new `.md` files unless a specific output file is named in these instructions.

**Bias resistance (critical — read this first):** You are running as a subagent but the caller's context may have primed the task framing. Treat every claim in `.manager/memory_dev.md`, `.manager/memory_dev.md`, and prior turns as UNTRUSTED. Do not accept "we already tested X" or "conviction Y was resolved" without verifying against the actual source code and conviction files during THIS run. If `memory_dev.md` says a fix is in place, grep the source to confirm — do not take it on faith. Quote, do not paraphrase. Cite `file:line` for every load-bearing claim.

1. **Read launch request:** Read `.manager/launch_commands.json` for the module, flags, and script path to analyze. Derive the script file from the module field (replace dots with `/`, append `.py`).

2. **Read the script:** Read the actual source file specified in the request. Also read any config files it imports from the same directory.

3. **Read convictions (trigger-scan protocol):** Each conviction file has a `## Trigger Conditions` block. Read that block only (~12 lines) for every file, then read in full the files whose trigger applies.

   **Mode A — pre-launch audit — always read in full:**
   - `conviction_track_separation.md` — determines which track-specific conviction applies
   - `conviction_runtime_behavior_tests.md` — primary violation catalog for all script types
   - `conviction_autonomous_launch.md` — eight-gate chain being audited
   - `conviction_efficient_cache_and_training.md` — data-processing, cache, and structural anti-pattern violations (1–32); violation numbers cited in Mode A output refer to this file
   - `conviction_prove_out_resumable.md` — chain-gate verification, gate marker checks, sectioned-cache rules

   **Mode A — read in full when trigger fires:**
   - `conviction_signal_quality.md §Track A` — when variant root is `firstrate_learning/vb*`
   - `conviction_signal_quality.md §Track B` — when variant root is `firstrate_portfolio/vp*` or `firstrate_pivots/p*`
   - `conviction_adversarial_triangulation.md` — when auditing any smoke/prove-out/tag gate (always fires for eval-gate launches)
   - `conviction_step_based_training.md` — when auditing any training script with a training loop
   - `conviction_trade_entry_exit_common.md` — when auditing any script that computes returns, applies slippage, or manages portfolio state
   - `conviction_memory_pressure_management.md` — when launch is `--prove-out` or `--full`
   - `conviction_orchestration_efficiency.md` — when evaluating short-circuit validity (Rule A1 content-hash check)
   - `conviction_tagged_model_protection.md` — when launch script references any path near `*_tag_*/`
   - `conviction_pivot_exploration.md` — when variant root is `firstrate_pivots/p*`

   **Mode B (design-doc audit) — always read in full:**
   - `conviction_track_separation.md`, `conviction_signal_quality.md §Track A` or `conviction_signal_quality.md §Track B` (track-appropriate), `conviction_adversarial_triangulation.md`

   **Mode C (post-run analysis) — always read in full:**
   - `conviction_track_separation.md`, track-appropriate signal-quality conviction, `conviction_adversarial_triangulation.md`, `conviction_orchestration_efficiency.md` (strike-advance rules)

   **tdeep does NOT need to read:** `conviction_disk_space_management.md`, `conviction_time_efficiency.md`, `conviction_ptsa.md`, `conviction_strategic_progression.md`, `conviction_autonomy_envelope.md` — not relevant to launch audits or post-run analysis.

   **PTSA GATE — HIGHEST PRIORITY CHECK (per `conviction_ptsa.md`):**
   If the launch is for ANY model training (pivot variant P1/P2/P3 under `firstrate_pivots/`, or any Track A/B variant):
   - Check whether `firstrate_ptsa/ptsa_summary.json` exists AND contains `"status": "PASS"`.
   - If absent or not PASS → flag as BLOCKING violation: "PTSA-INCOMPLETE: Pre-Training Signal Analysis has not completed. All model training is blocked until PTSA-J (133-param MLP probe) passes with val xsec_IC ≥ 0.005. See conviction_ptsa.md."
   - This is a smoke-blocking AND unit-test-blocking violation for all training. PTSA scripts themselves (under `firstrate_ptsa/`) are exempt from this gate — they ARE the analysis.

   **NON-TRAINING SCRIPT LAUNCH CHECK (for any script that is NOT model training — analysis scripts, data prep, probe scripts, etc.):**
   - These scripts do NOT require PTSA-J to be complete.
   - They MUST comply with CLAUDE.md data processing rules: ProcessPoolExecutor for CPU-bound, ThreadPoolExecutor for I/O, no Python for-loops over samples/dates/rows.
   - They MUST support `--unit-test` mode (completes in <2 min, produces same output schema as full run with non-degenerate values) AND `--smoke-test` mode (completes in <30 min or <5 min for analysis-only scripts).
   - They MUST declare an output contract in `launch_commands.json` (`output_contract` field). If absent, flag as BLOCKING: "OUTPUT_CONTRACT_MISSING: launch entry has no `output_contract` field; teta cannot validate output quality post-run."
   - For PTSA/IC scripts: flag as BLOCKING if the script uses token cache `y_return` as IC label (must use OTO return from `prices_raw.dat open[0]` field).
   - Apply ALL universal structural checks (steps 7a–7h below) identically to non-training scripts.

   **Legacy DA.1/DA.2/DA.3 check (superseded):** Do NOT flag DA.1/DA.2/DA.3 absence as a separate violation. These are absorbed into PTSA-A/PTSA-D/PTSA-F. The PTSA gate above supersedes the old DA gate.

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

   **7g. Hypothesis-vs-schedule consistency — run this:**
   ```bash
   # Parse the hypothesis string from launch_commands.json for a step cap
   # (e.g., "≤7000 steps", "≤7,000 steps", "7000-step cap", "--total-steps 7000", "at step ≥ 30K")
   grep -oE "(≤|<=|under |cap(ped)? at |--total-steps )[0-9,]+ *steps?|[0-9,]+-step cap|at step *(≥|>=) *[0-9KkMm,]+" <launch_commands.json>
   # Parse the script's actual smoke/prove-out schedule
   grep -nE "max_epochs *=|max_batches *=|total_steps *=|batches_per_epoch *=|--total-steps|--smoke-test.*total_steps|run_type *== *['\"]smoke['\"]|run_type *== *['\"]proveout['\"]" <script_file>
   ```
   For the `run_type` branch matching the flags in `launch_commands.json` (e.g. `--smoke-test` → `run_type='smoke'`), compute the script's effective `total_steps`:
   - If `max_batches` is set → `total_steps = max_epochs × max_batches`.
   - Else → `total_steps = max_epochs × batches_per_epoch` (batches_per_epoch computed from `meta['splits']['train']['n_samples'] // batch_size` or from `train_max_chunks × (chunk_size // batch_size)` per the script).

   Compare against the hypothesis cap:
   - If the hypothesis names a step cap (e.g. "≤7000 steps") AND the script's effective total_steps > cap AND the `flags` array in launch_commands.json does NOT include `--total-steps N` with N ≤ cap → **STRUCTURAL_FAIL: "Script smoke schedule (<effective_steps> steps) exceeds hypothesis cap (<cap> steps); flags do not pass --total-steps override."**
   - If the script parses `--total-steps` in argparse AND the flags include it AND the passed value ≤ cap → STRUCTURAL_PASS with evidence line: `flags include --total-steps <N>, script argparse handles it at line <N>`.
   - If the script does NOT parse `--total-steps` but the flags include it → **STRUCTURAL_FAIL: "Belt-and-suspenders flag --total-steps passed but script argparse does not define it (grep of argparse shows no match). Flag is silently ignored; only the in-code default applies."** Variant folders copied from a parent train.py inherit the parent's smoke default without re-auditing the applicable step cap.
   - If the hypothesis does not name a step cap (e.g. prove-out hypotheses keyed on a "best step" instead of a fixed step count) → STRUCTURAL_SKIP with a one-line note: "hypothesis does not state a numeric step cap; runtime kill curve (teta) is the only gate."

   Also verify the warmup/schedule ratio against `CLAUDE.md` when the cap is tight: `WARMUP_STEPS` must be 10–15% of effective `total_steps`, never ≥ total_steps. If `warmup_steps=3000` against `total_steps=3000` → 100% warmup, collapse risk. Flag as **STRUCTURAL_WARN: "Warmup/total ratio unsafe at this cap"** (CLAUDE.md: "WARMUP_STEPS=3000 with 3000-step smoke = entire run is warmup, model never reaches cosine decay, collapses").

   For EVERY check: quote the specific line numbers and code snippets as evidence. "STRUCTURAL_PASS — no issues found" is NOT acceptable without showing the grep output that proves it.

   **7g. Memory-stress verification (BLOCKING for `--prove-out` / `--full` per `conviction_memory_pressure_management.md` — REQUIRED, do not skip):**

   Silent OOMs at eval boundaries have caused repeated prove-out failures in prior variants. Mode A MUST verify memory cleanliness BEFORE approving any prove-out or full launch by checking ONE of two evidence sources.

   For `--smoke-test` launches: 7g is INFORMATIONAL (record the check but do NOT block). The smoke run IS the data-collection cycle for prove-out's 7g.

   For `--prove-out` / `--full` launches: 7g is BLOCKING. PASS requires (a) OR (b) below.

   **(a) Prior smoke `_resource_log.jsonl` cleanliness:**
   ```bash
   VARIANT_DIR=$(dirname <script_file>)
   LATEST_SMOKE=$(ls -1dt "$VARIANT_DIR"/models/run_*_smoke 2>/dev/null | head -1)
   RLOG="$LATEST_SMOKE/_resource_log.jsonl"
   ls -la "$RLOG" 2>/dev/null
   ```
   Read the file. Compute three values via:
   ```bash
   python3 -c "
   import json, sys
   lines=[json.loads(l) for l in open('$RLOG')]
   if len(lines) < 5:
       print('FAIL: only', len(lines), 'samples'); exit()
   mt_kb=int(open('/proc/meminfo').readline().split()[1])
   mt_gb=mt_kb/1024/1024
   peak_rss=max(s['rss_gb'] for s in lines)
   peak_pct=peak_rss/mt_gb*100
   max_drss=0
   for a,b in zip(lines, lines[1:]):
       dt=b['timestamp']-a['timestamp']
       if dt>0:
           rate=(b['rss_gb']-a['rss_gb'])/dt
           if rate>max_drss: max_drss=rate
   print(f'samples={len(lines)} peak_rss_gb={peak_rss:.1f} peak_pct={peak_pct:.1f} max_drss_gbs={max_drss:.3f}')
   pass_a = len(lines)>=5 and peak_pct<50 and max_drss<0.5
   print('VERDICT:', 'PASS' if pass_a else 'FAIL')
   "
   ```
   Pass criteria: ≥ 5 samples AND peak_rss < 50% MemTotal AND max Δ-RSS < 0.5 GB/s.
   - PASS → STRUCTURAL_PASS (mem-stress) with evidence line citing the rlog path + verdict line.
   - FAIL → fall through to (b).
   - File missing → fall through to (b).

   **(b) Run a fresh `--mem-stress-test`:**
   ```bash
   VARIANT_MODULE=<derive from script_file: firstrate_learning.<variant>.train>
   timeout 600 .venv/bin/python -u -m "$VARIANT_MODULE" --mem-stress-test > /tmp/tdeep_memstress.log 2>&1 &
   STRESS_PID=$!
   START=$(date +%s)
   until ! kill -0 "$STRESS_PID" 2>/dev/null || [ $(($(date +%s) - START)) -ge 600 ]; do sleep 5; done
   wait $STRESS_PID 2>/dev/null
   STRESS_EXIT=$?
   STRESS_RUN=$(ls -1dt "$VARIANT_DIR"/models/run_*_memstress 2>/dev/null | head -1)
   STRESS_RLOG="$STRESS_RUN/_resource_log.jsonl"
   ```
   Then apply the same three-criteria check from (a) against `$STRESS_RLOG`. PASS only if exit code 0 AND criteria met.

   `--mem-stress-test` is a CLI mode every `firstrate_learning/vb*/train.py` and `firstrate_portfolio/vp*/train.py` MUST implement (per `conviction_memory_pressure_management.md` rule 5). It is functionally a smoke with two changes: (i) `_resource_log.jsonl` cadence is 1Hz instead of 30s; (ii) `total_steps = eval_every + 50` so the run crosses exactly ONE eval boundary (where the OOM balloon fires).

   If the script does NOT parse `--mem-stress-test` and (a) failed/missing → **MEM_STRESS_FAIL: "neither prior smoke _resource_log.jsonl nor --mem-stress-test mode available; cannot verify memory safety. Block prove-out/full and dispatch tdev_inline to add --mem-stress-test mode."**

   Record the verdict in the structural analysis output as `7g. mem-stress: PASS|FAIL|SKIP_SMOKE` with evidence: cited rlog path, samples count, peak_pct, max_drss.

   **7h. Universal correctness checks (apply to ALL scripts, training AND non-training):**

   These checks run on every script regardless of type. Do not skip for analysis or data scripts.

   **7h-i. Array index semantic check — run this:**
   ```bash
   grep -n "\[.*_idx\|prices\[" <script_file> | head -30
   ```
   For each array access with index variables (e.g. `prices[i, j, k]`, `data[sym_idx, date_idx]`): read the surrounding 10 lines to determine what each variable represents. Cross-check against the array's declared shape (find its construction or `np.memmap` call).

   **`prices_raw.dat` canonical axis semantics (verified from `prices_meta.json`):**
   - Shape `(8766, 4025, 8)` = **(N_SYMBOLS=8766, N_DATES=4025, N_FIELDS=8)**
   - Axis 0 = SYMBOLS (8766). Axis 1 = DATES (4025).
   - Correct access: `prices[sym_idx, date_idx, field]`
   - WRONG: `prices[date_idx, sym_idx, field]` — date index on symbols axis → random label reads → IC≈0
   - Note: prior CLAUDE.md documentation incorrectly stated axis 0=dates. Source of truth is `prices_meta.json`: n_symbols=8766, n_dates=4025.

   If a variable named `price_idx`, `date_idx`, `price_row`, or similar date-indexed variable is used on axis 0 of `prices_raw.dat` → **STRUCTURAL_FAIL: "Transposed array index: `prices[price_idx, sym_idx]` at line N but prices_raw.dat axis 0=SYMBOLS — date index must go on axis 1."** Proven: PTSA-Z used `prices[price_idx, p_indices]` → IC=0.0014 on full run (while PTSA-Y with `prices[sym_price_indices, price_idx]` achieved IC=0.046).

   **7h-ii. Division denominator floor check — run this:**
   ```bash
   grep -n "/ *(std\b\|sigma\b\|denom\b\|norm\b)" <script_file> | grep -v "1e-[0-9]\|max(\|clip(\|clamp(" | head -20
   ```
   For each division by `std`, `sigma`, or similar normalization denominator that does NOT have a floor (no `max(std, X)`, no `+ 1e-X` with X ≤ 4, no `np.clip`): flag as **STRUCTURAL_FAIL: "Division at line N uses bare `std` with no floor clamp. If std ≈ 0 (sparse feature coverage), float32 overflow produces inf/nan. Minimum floor: `max(std, 0.01)` or `np.clip(normalized, -10, 10)` after divide."** Note: `std + 1e-6` alone is insufficient — `1e-6` produces values up to 1e6 before float32 overflow at 3.4e38; minimum safe floor is `max(std, 0.01)` or explicit post-divide clip.

   **7h-iii. Output contract assertions check — run this:**
   ```bash
   grep -n "json.dump\|np.save\|findings\|output_contract\|assert.*ic\|assert.*nan\|np.isnan\|math.isnan" <script_file> | head -20
   ```
   If the script writes output files (JSON findings, NPZ arrays, etc.) AND the launch entry declares an `output_contract` field with non-null assertions: verify the script contains assertions or checks near the output write that would catch degenerate values (nan, constant, out-of-range). If the script writes output without any nan/validity check → **STRUCTURAL_WARN: "Script writes output at line N with no degenerate-value assertion. Add `assert not np.isnan(val_ic)` or equivalent before writing findings.json."** WARN not FAIL (first occurrence); FAIL on second script in same batch.

   **7h-iv. Silent exception suppressor check — run this:**
   ```bash
   grep -n "except.*:" <script_file> | grep -v "except.*Error\|except.*Exception.*as\|# ok\|# intentional" | head -20
   ```
   For each bare `except:` or `except Exception:` followed by `continue` or `pass` (with no re-raise, no log, no counter): → **STRUCTURAL_FAIL: "Silent exception suppressor at line N. Per CLAUDE.md: raise errors explicitly — never catch and continue silently."** Exception: a bare `except` that logs a warning AND increments a counter AND does not suppress the underlying condition is STRUCTURAL_WARN not FAIL.

   **7h-v. GPU compute profile analysis — applies to every script with torch imports or neural components; also applies to pure-CPU scripts to confirm `requires_gpu: false` is appropriate:**

   This check verifies whether the script's compute architecture justifies GPU execution and whether the `requires_gpu` declaration is correct. Declarations are verified — not trusted on faith.

   **Step 1 — Detect script type:**
   ```bash
   grep -n "import torch\|from torch\|nn\.Module\|nn\.Linear\|nn\.Conv\|MultiheadAttention\|\.cuda()\|\.to(device)" <script_file> | head -10
   ```
   If no torch imports found → `compute_profile=cpu_bound`. Verify `requires_gpu: false` in launch entry. Skip to step 6 with verdict CPU_BOUND_CORRECT (or flag mismatch). Record and move on.

   **Step 2 — Extract architecture parameters:**
   ```bash
   grep -n "HIDDEN_DIM\|hidden_dim\|N_HEADS\|n_heads\|N_LAYERS\|n_layers\|Conv1d\|Linear\|MultiheadAttention\|TRAIN_STEPS\|N_STEPS\|train_steps" <script_file> | head -20
   ```
   Estimate total parameter count and dominant operation type from found values:
   - `Conv1d(in, out, k)`: params = in×out×k + out per layer
   - `Linear(in, out)`: params = in×out + out
   - `MultiheadAttention(embed_dim, num_heads)`: params ≈ 4×embed_dim²
   Record: `model_type`, `estimated_params`, `dominant_op` (conv|matmul|attention).

   **Step 3 — Estimate batch FLOPs per forward pass:**
   ```bash
   grep -n "N_SYMS\|n_syms\|N_DAYS\|n_days\|N_FEATURES\|n_features\|batch_size\|T_LOOKBACK\|lookback" <script_file> | head -20
   ```
   Using architecture + batch dimensions:
   - Conv1d per layer: `2 × C_in × C_out × kernel_size × L`  (L = sequence length = N_DAYS)
   - Linear per layer: `2 × in × out × batch_size`
   - MultiheadAttention over N_syms: `2 × N_syms² × embed_dim + 4 × N_syms × embed_dim²`
   Record: `estimated_flops_per_forward` (FLOPs integer, show formula).

   **GPU break-even thresholds (A100/V100 class, PyTorch):**
   - `< 1M FLOPs/forward`: CPU likely FASTER — CUDA kernel launch overhead (5–20µs × N_kernels) dominates compute
   - `1M–10M FLOPs/forward`: BORDERLINE — break-even depends on kernel count and batch shape
   - `> 10M FLOPs/forward`: GPU clearly beneficial — compute dominates kernel launch overhead
   - `N_syms² cross-symbol attention, N_syms > 500, embed_dim ≥ 8`: GPU clearly beneficial regardless of FLOPs estimate (memory-bandwidth bound, GPU wins)

   **Step 4 — Estimate kernel launch overhead ratio:**
   Count distinct PyTorch operations in the forward pass (each nn.Module call, each tensor op is one kernel launch):
   ```bash
   grep -c "self\.\|nn\.\|F\.\|torch\." <script_file>
   ```
   Approximate: `kernel_launch_overhead ≈ N_ops × 10µs`. Compare to `compute_time ≈ FLOPs / 10e12` (10 TFLOPS mixed-precision).
   - `kernel_launch_overhead > 0.5 × compute_time`: BORDERLINE or CPU-competitive
   - `kernel_launch_overhead < 0.1 × compute_time`: GPU clearly beneficial

   **Step 5 — Detect bottleneck: dataset build vs training:**
   ```bash
   grep -n "for.*date\|for.*sym\|for date_str\|for sym \|for i in range.*n_date\|for i in range.*n_sym" <script_file> | head -10
   ```
   If Python for-loops over dates or symbols exist (U1 violation):
   - Estimate build time: `N_dates × N_syms × 200ns` (CPython scalar loop)
   - Estimate training time: `N_steps × FLOPs_per_forward / 10e12`
   - Compute `bottleneck_ratio = build_time / training_time`
   - If `bottleneck_ratio > 5`: `bottleneck=dataset_build` — GPU training optimization is irrelevant until U1 is fixed

   **Step 6 — Verdict (one of four outcomes):**

   - **`GPU_JUSTIFIED`**: FLOPs ≥ 10M/forward (or N_syms² attention over ≥ 500 syms with embed_dim ≥ 8), AND `bottleneck=training` (no U1-violating loops), AND `requires_gpu: true` declared. → STRUCTURAL_PASS. No action required.

   - **`GPU_AFTER_VECTORIZE`**: GPU architecture justified by FLOPs/attention, BUT Python data loops exist making dataset_build the dominant bottleneck (bottleneck_ratio > 5). → **STRUCTURAL_FAIL: "GPU_AFTER_VECTORIZE: neural architecture warrants GPU (FLOPs=XM or N_syms² attention), but Python loops over data items make dataset build ~Yx the training time. GPU adds <5% wall clock improvement until U1 (vectorized build) is resolved. Fix Python loops first per CLAUDE.md U1 and conviction_efficient_cache_and_training.md violation 40."** BLOCKING.

   - **`GPU_BREAK_EVEN_NOT_MET`**: FLOPs < 10M/forward AND no N_syms² attention advantage, AND `requires_gpu: true` or `compute_profile: gpu_bound` declared WITHOUT `gpu_redesign_needed: false`. → **STRUCTURAL_FAIL: "GPU_BREAK_EVEN_NOT_MET: estimated FLOPs/forward = XM (threshold 10M). PyTorch CUDA kernel launch overhead likely dominates. CPU+MKL may be faster. Resolve by: (1) setting requires_gpu: false + compute_profile: cpu_bound, OR (2) redesigning for GPU break-even (batch N_dates into one tensor pass, increase hidden_dim ≥ 32, pre-load full dataset to GPU tensor before training loop), OR (3) adding gpu_redesign_needed: false with measured benchmark evidence that GPU is faster at this scale. See conviction_efficient_cache_and_training.md violations 38-39."** BLOCKING.

   - **`CPU_BOUND_CORRECT`**: No torch imports, or FLOPs < 1M, AND `requires_gpu: false` declared (or `compute_profile: cpu_bound`). → STRUCTURAL_PASS.

   **Borderline zone (1M–10M FLOPs)**: classify as GPU_BREAK_EVEN_NOT_MET if `requires_gpu: true` without `gpu_redesign_needed: false`. Classify as CPU_BOUND_CORRECT if `requires_gpu: false` and `compute_profile: borderline` explicitly declared.

   **7h-v output section (add to `## Universal Checks (7h)` in results template):**
   ```
   gpu_profile:
     compute_profile_inferred: <cpu_bound|gpu_bound|borderline>
     model_type: <Conv1D|SetTransformer|MLP|Transformer|none>
     estimated_params: <N>
     estimated_flops_per_forward: <N>M  (<formula used>)
     dominant_op: <conv|matmul|attention|none>
     n_syms_attention: <N or none>
     bottleneck: <dataset_build|training|io>
     bottleneck_ratio: <Nx build/training estimate>
     requires_gpu_declared: <true|false|missing>
     compute_profile_declared: <cpu_bound|gpu_bound|borderline|missing>
     gpu_verdict: <GPU_JUSTIFIED|GPU_AFTER_VECTORIZE|GPU_BREAK_EVEN_NOT_MET|CPU_BOUND_CORRECT>
     action_required: <none|fix_u1_loops_first|redesign_for_gpu_breakeven|set_requires_gpu_false|add_gpu_redesign_needed_false>
   ```

**7i. Shared-library performance scan + smoke wall-clock projection (MANDATORY for all training scripts with eval loops):**

This step closes the audit-boundary gap: static checks on `<script_file>` miss violations in imported shared libraries. Step 7i scans the full `py_files_at_audit` set and projects eval overhead to smoke scale.

**Step 7i-a: Scan shared libraries for U1 violations:**
```bash
# Build the list of firstrate_common imports from the script
grep -n "from firstrate_common\|import firstrate_common" <script_file>
# For each imported module (e.g. firstrate_common.metrics), scan for Python loops over data items
grep -n "for date in\|for.*in unique_dates\|for.*in range.*n_date\|for.*in range.*n_sym\|for i in range.*n_random\|for i in range.*n_shuffles\|for k in range.*len" firstrate_common/metrics.py firstrate_common/*.py 2>/dev/null | head -40
```
For each hit: read 10 lines of context. Is the loop over data items (dates, symbols, samples) — not over a small fixed parameter list (4 cost tiers, 3 features)? Data-item loops are U1 violations. Classify:
- U1 violation in `<script_file>` itself → STRUCTURAL_FAIL (existing rule, blocks launch)
- U1 violation in an imported `firstrate_common/*.py` function called during eval → **SHARED_LIB_U1_WARN**: "Shared library U1 violation at `<file>:<line>`. Does not block this launch but MUST be remediated before next smoke. tdev_inline task required." Record in the remediation-tasks section.
- No U1 violations in shared libraries → STRUCTURAL_PASS (shared-lib U1 clean).

**Step 7i-b: Check adversarial suite parallelism:**
```bash
grep -n "ProcessPoolExecutor\|ThreadPoolExecutor" firstrate_common/metrics.py 2>/dev/null
grep -n "def adversarial_triangulation_summary\|def random_portfolio_percentile\|def shuffled_target_null" firstrate_common/metrics.py
```
If `adversarial_triangulation_summary` exists in the script's import graph AND `ProcessPoolExecutor` is absent from `firstrate_common/metrics.py` → **SHARED_LIB_PC5_WARN**: "Adversarial suite calls are sequential (no ProcessPoolExecutor). Required: parallelize 5 checks + inner iterations per conviction_adversarial_triangulation.md § Performance contract. tdev_inline remediation task required."

**Step 7i-c: Extract unit-test phase timings (requires step 6 unit test to have run):**
```bash
grep -E "forward_pass_s|metric_compute_s|adversarial_s|eval.*wall|total wall" /tmp/tdeep_unit.log 2>/dev/null
```
If phase timings are present, extract `unit_eval_wall_s` (total eval wall time from unit test). If absent, set `unit_eval_wall_s = unknown` and classify as STRUCTURAL_WARN_PC3.

**Step 7i-d: Project smoke eval wall-clock cost:**
If `unit_eval_wall_s` is known AND the script imports universe cache config (read `UNIVERSE_CACHE_PATH` from config.py to find the manifest):
```bash
python3 -c "
import json, pathlib
cfg_path = '<config_file>'  # e.g. firstrate_pivots/p6_endtoend_v1/config.py
# Parse UNIVERSE_CACHE_PATH from config (or read manifest directly)
manifest = json.load(open('firstrate_learning/cache/p6_universe_cache/manifest.json'))
n_val_unit = 20  # unit test typically uses 20 dates
n_val_smoke = manifest['val']['n_dates']
smoke_steps = <SMOKE_STEPS from config>
eval_every = <EVAL_EVERY_STEPS from config>
n_smoke_evals = smoke_steps // eval_every
unit_eval_s = <unit_eval_wall_s>
scale = n_val_smoke / n_val_unit
projected_per_eval = unit_eval_s * scale
projected_total = projected_per_eval * n_smoke_evals
budget = <SMOKE_WALLCLOCK_MAX_S from config>
print(f'n_val_smoke={n_val_smoke} scale_factor={scale:.1f}x projected_per_eval={projected_per_eval:.0f}s projected_total={projected_total:.0f}s budget={budget}s')
print('VERDICT:', 'PASS' if projected_total <= budget else f'FAIL — projected {projected_total:.0f}s > budget {budget}s')
"
```
- Projection PASS → STRUCTURAL_PASS (smoke-wallclock-projection)
- Projection FAIL → **STRUCTURAL_FAIL_PC4**: "SMOKE_WALLCLOCK_BREACH_PROJECTED: projected smoke eval overhead Xs > SMOKE_WALLCLOCK_MAX_S Ys. Root cause: U1 loops in shared library and/or sequential adversarial suite. BLOCK launch until PC4/PC5/U1 remediation complete." BLOCKING.
- `unit_eval_wall_s = unknown` (phase timing absent) → STRUCTURAL_WARN: "Cannot project smoke eval cost — unit test missing phase timing instrumentation. Add `forward_pass_s`, `adversarial_s` timing logs. Recommend fixing before smoke."

**Step 7i output section (add to `## Performance Contract (7i)` in results template):**
```
shared_lib_u1:
  files_scanned: [list]
  violations_found: <N> [quoted file:line for each]
  classification: PASS | SHARED_LIB_U1_WARN
  remediation_tasks_required: <N>
adversarial_parallelism:
  processpool_present: <true|false>
  classification: PASS | SHARED_LIB_PC5_WARN
unit_eval_timing:
  unit_eval_wall_s: <N or unknown>
  phase_timings_present: <true|false>
  classification: PASS | STRUCTURAL_WARN_PC3
smoke_projection:
  n_val_smoke: <N>
  scale_factor: <Nx>
  n_smoke_evals: <N>
  projected_per_eval_s: <N>
  projected_total_s: <N>
  budget_s: <N>
  classification: PASS | STRUCTURAL_FAIL_PC4 | SKIP (unit_eval_unknown)
remediation_tasks: [list of tdev_inline tasks required before next smoke launch]
```

SHARED_LIB_U1_WARN and SHARED_LIB_PC5_WARN do NOT block the current launch if `projected_total_s ≤ budget_s`. They produce remediation tasks that tdeep writes into the audit output and that tconv MUST pick up as ACTIONABLE_NOW tasks in the next cycle. STRUCTURAL_FAIL_PC4 IS blocking.

8. **Write results immediately (no further delays):**

Once steps 1-7i complete (unit test + structural analysis + shared-library scan + smoke projection), write the results file WITHOUT additional monitoring loops or sleeps.

9. **Reporting results** — Each check reports one of:
   - `PASS` — evidence confirms expected behavior
   - `FAIL` — evidence contradicts conviction (blocks launch)
   - `SKIP` — not applicable (no prior run data, no cache expected, etc.)
   - `WARN` — caution flag, not blocking

10. **Write results** to `.manager/deep_analysis_launch.md`:
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

## Universal Checks (7h — all scripts)
array_index_semantics: PASS / FAIL / WARN — evidence
division_denominator_floor: PASS / FAIL / WARN — evidence
output_contract_assertions: PASS / FAIL / WARN — evidence
silent_exception_suppressors: PASS / FAIL / WARN — evidence
gpu_profile:
  compute_profile_inferred: <cpu_bound|gpu_bound|borderline>
  model_type: <type or none>
  estimated_params: <N>
  estimated_flops_per_forward: <N>M
  dominant_op: <conv|matmul|attention|none>
  bottleneck: <dataset_build|training|io>
  bottleneck_ratio: <Nx>
  requires_gpu_declared: <true|false|missing>
  gpu_verdict: <GPU_JUSTIFIED|GPU_AFTER_VECTORIZE|GPU_BREAK_EVEN_NOT_MET|CPU_BOUND_CORRECT>
  action_required: <none|fix_u1_loops_first|redesign_for_gpu_breakeven|set_requires_gpu_false|add_gpu_redesign_needed_false>
...

## Performance Contract (7i — training scripts with eval loops)
shared_lib_u1:
  files_scanned: [list]
  violations_found: <N>
  classification: PASS | SHARED_LIB_U1_WARN
  remediation_tasks_required: <N>
adversarial_parallelism:
  processpool_present: <true|false>
  classification: PASS | SHARED_LIB_PC5_WARN
unit_eval_timing:
  unit_eval_wall_s: <N or unknown>
  phase_timings_present: <true|false>
  classification: PASS | STRUCTURAL_WARN_PC3
smoke_projection:
  n_val_smoke: <N>
  scale_factor: <Nx>
  n_smoke_evals: <N>
  projected_per_eval_s: <N>
  projected_total_s: <N>
  budget_s: <N>
  classification: PASS | STRUCTURAL_FAIL_PC4 | SKIP
remediation_tasks: [list tdev_inline tasks required — each as "TASK: <description>"]
...

## Summary
TOTAL_VIOLATIONS: [static violations count]
TOTAL_BEHAVIOR_FAILURES: [runtime+resource failures count]
TOTAL_STRUCTURAL_FAILURES: [structural failures count]
TOTAL_BLOCKING: [sum of all failures including universal 7h + 7i checks — blocks launch if > 0]
NOTE_UNIVERSAL_CHECKS: [list any 7h findings that are WARN vs FAIL, since WARNs do not block but must be surfaced]
NOTE_GPU_PROFILE: [gpu_verdict + action_required — surfaced even if not blocking]
NOTE_PERFORMANCE_CONTRACT: [7i remediation tasks — listed even when non-blocking so tconv picks them up]
RECOMMENDATION: LAUNCH or BLOCK
```

**CRITICAL: Write this file IMMEDIATELY after step 7 completes. Do not delay for any additional analysis or monitoring. The file must exist within 3 minutes of subagent start.**

11. **Update `## Tdeep Status` in `.manager/memory_dev.md`** — MANDATORY. **Overwrite** the `## Tdeep Status` section (create it at end of file if missing) with a single status block reflecting the CURRENT run only. Never append — replace the entire section content each run. This keeps the file bounded.

```
## Tdeep Status
Last run: [PST timestamp]
Mode: launch-audit
Result: [N violations / LAUNCH or BLOCK — key finding 1 sentence]
Val Sharpe <X> vs V10 anchor 2.569 (gap: <Y>%) | Test ann. <A>% vs V10 144.71% (gap: <B>%)
```

Rules:
- Timestamp: run `TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT'` via Bash to get the real current time. NEVER infer or guess.
- Val Sharpe: latest Val Sharpe from memory_dev.md or memory_dev.md. Compare to V10 anchor Val Sharpe **2.569**. Compute gap percentage. Write "no metrics yet" if unavailable.
- Test annual return: current model test-period annualized return % vs V10 anchor **144.71%**. Write "no data yet" if not available.
- If the section does not exist, create it at end of file.

Do NOT write `.manager/timer_cycle_state.json` — timer-dev reads the results file directly.
---

**After the subagent returns:** confirm `deep_analysis_launch.md` was written. Then log and exit.

---

## Mode B — Design-doc audit (detailed instructions)

Invoke the analysis sub-agent using the Agent tool with `subagent_type: "general-purpose"`, `model: "claude-sonnet-4-6"`.

Agent prompt — pass the full instructions below verbatim:

---
## Instructions (Design-doc audit)

You are auditing a design-doc section in `.manager/memory_design.md` that tconv phase-2 authored or revised. Your job is to decide whether the section is sound enough to move from ACTIVE (in-progress) to implementable — i.e., whether the caller can safely task tdev_inline against it.

Do NOT create new `.md` files unless explicitly named below. Do NOT edit `memory_design.md` itself (tconv phase-2 owns it — your feedback feeds back into phase-2 next cycle via the verdict). Do NOT edit `memory_dev.md`, `memory_dev.md`, or any conviction file.

1. **Read the target task:** Read `.manager/memory_dev.md` and quote the exact task line of form `tdeep design-doc audit: memory_design.md § <variant_name>`. Record the `<variant_name>`.

2. **Read the design-doc section:** Read `.manager/memory_design.md` and extract the `## ACTIVE: <variant_name>` section (from its header to the next `##` header at the same level).

3. **Read the sources the design doc claims:**
   - `.manager/memory_dev.md` — verify the quoted Active-Goal / top-gap coordinate still matches the current file.
   - `.manager/trev_report.md` (if it exists) — verify the quoted trev recommendation appears verbatim at the cited location.
   - Every `.manager/convictions/*.md` file cited in the Sources block — verify the quoted conviction line appears verbatim.
   - `CLAUDE.md` — verify any quoted project-memory line appears verbatim.

4. **Run the audit checks (report PASS / FAIL / WARN for each, with quoted evidence). Quoted-source verification requirement:** before returning APPROVED, you MUST open every `file:line` cited in the design entry's architectural claims and verify the pattern actually exists at that site. Reading the design entry's quoted snippet is NOT sufficient — open the cited source file fresh and confirm. If the cited line is out of date, has moved, or the pattern at that line does not match the architectural claim, that is a B9 FAIL (see B9 below).

   **B1. Sources-block integrity.** Does the section have a Sources header block quoting: (a) trev recommendation, (b) memory_dev.md top-gap coordinate, (c) at least one conviction, (d) any load-bearing CLAUDE.md line? Each quote must match the source file byte-for-byte. FAIL on any `QUOTE_MISMATCH`.

   **B2. Blocking-coordinate framing.** Does the section identify the blocking coordinate it addresses, and name it as `blocking` (not `closeable` or `cost`)? FAIL if the doc proposes a large architectural change aimed at a `closeable` coordinate — that is a step-size/class mismatch.

   **B3. Gate-chain mapping.** Does the implementation plan map each phase to the gate chain defined in `CLAUDE.md` (unit <2 min → smoke <30 min with step cap → prove-out 1-3 hr with step cap → full)? FAIL if a phase skips a gate, omits a step cap for smoke/prove-out, or projects a wall-clock that violates the time budget. Step cap values come from the variant's `config.py` or `launch_commands.json` `expect` block — do NOT apply hardcoded per-architecture defaults.

   **B4. Numeric success criteria.** Does the section state numeric thresholds for success and failure at each gate (e.g., "smoke passes iff val Sharpe > X at step N; fails iff ...")? FAIL on vague criteria ("should improve", "hopefully better"). Criteria must be objective enough that tdev_inline/teta can evaluate them without further discussion.

   **B5. Tagged-model protection.** Does the plan modify any `.py` file inside a `*_tag_*` directory? FAIL if yes. Variant folder must be named and distinct from any tagged directory. Verify via Glob that the proposed variant folder is NOT under a tagged path.

   **B6. Per-track hard-cap check (per `conviction_track_separation.md` § Capacity ledger).** Count `## ACTIVE:` headers per track. Track A entries = entries with `Track: A` line OR variant folder under `firstrate_learning/vb*`. Track B entries = entries with `Track: B` line OR variant folder under `firstrate_portfolio/vp*`. FAIL if Track A count > 1, OR Track B count > 2, OR total > 3 (violates per-track caps). If a per-track cap is exactly at limit (Track A = 1 or Track B = 2), WARN and recommend that approving this one requires an explicit retirement plan for the same-track entry that would be displaced. The legacy global ≤2 cap is REPLACED by these per-track caps as of Cycle 434.74.

   **B7. Conviction coupling, track-aware.** Determine the entry's track from its `Track:` line (or variant-folder root if `Track:` is missing — that absence is itself a B11 FAIL, see below). Does the section contradict any active **track-scoped** conviction or `CLAUDE.md` line? Track A entries MUST cite `conviction_signal_quality.md §Track A` and `conviction_v13_experimentation_strategy_backbone.md` for primary gates; Track B entries MUST cite `conviction_signal_quality.md §Track B` and `conviction_v13_experimentation_strategy_portfolio.md`. If the entry cites the legacy SUPERSEDED predecessors (`conviction_signal_quality.md` / `conviction_v13_experimentation_strategy.md`) as authority for new gate thresholds, that is a cross-cycle violation — FAIL with `B7-legacy-predecessor-cited-as-authority`. If the entry contradicts an active track-scoped conviction without an override rationale, FAIL. If it cites an override, WARN and surface the conviction-proposal the caller will need to consider (two-cycle rule).

   **B8. Rejected-alternatives completeness.** Does the section name at least 2 rejected alternatives with quoted reasons (exhaustion claims from the **track-scoped** experimentation-strategy conviction or CLAUDE.md count)? WARN if fewer than 2.

   **B9. Architectural premise verification (quoted-source code-pattern check).** For every architectural claim of form "unfreeze block X", "replace head Y with Z", "cascade-load weight W", "the existing code uses pattern P at function F", etc., the design entry MUST cite a `file:line` (or `file:line-range`) in current source. The auditor MUST open the cited file at the cited line and verify the pattern exists at that site BEFORE returning APPROVED. If the cited file:line does not exist, or the pattern at that site does not match the architectural claim, FAIL with `B9-architectural-premise-not-verified` — NOT WARN. Rationale: a design entry may cite a wrong line (e.g., claiming a transformer block where the code has an MLP). B9 is the mechanical guard that forces the auditor to verify before APPROVED is returned.

   **B10. Track-scoped success criteria.** The entry's success criteria MUST cite gate thresholds from the track-scoped signal-quality conviction:
   - Track A entries: cite `conviction_signal_quality.md §Track A` § Gate thresholds (`per_stock_ic`, Brier `brier_p_up`/`brier_p_big`). Citing legacy `oracle_corr ≥ 0.020` from the SUPERSEDED predecessor as a NEW-entry primary gate is a cross-cycle violation — FAIL with `B10-track-A-cites-legacy-oracle-corr-floor`. Pre-existing entries authored under the predecessor and revised forward are exempt for already-published thresholds but new gates added in revisions MUST use the new metrics.
   - Track B entries: cite `conviction_signal_quality.md §Track B` § Gate thresholds (`test_sharpe_net_of_10bps`, `xsec_ic_per_date`, `cascade_transmission_ratio`, cost-realism net-of-30/50bps when turnover ≥ 1.0). Citing legacy `oracle_corr` thresholds is a cross-cycle violation — FAIL with `B10-track-B-cites-legacy-oracle-corr-floor`.
   FAIL if the success criteria do not name at least one threshold from the track-scoped conviction.

   **B11. Track-tag presence and folder match (per `conviction_track_separation.md`).** The entry MUST have a `Track:` line of exact form `Track: A` or `Track: B` immediately after the `## ACTIVE: <variant_name>` header line (or in the entry frontmatter region before `Axis:`). FAIL with `B11-track-line-missing` if absent. Also FAIL if the `Track:` line value does not match the variant folder's root (e.g., `Track: A` paired with a `firstrate_portfolio/vp*` folder is a track/folder mismatch — `B11-track-folder-mismatch`).

   **B12. Track-A paired-evaluation phase (Track A only).** For Track A entries, the implementation plan MUST include a paired-evaluation phase before tag-eligibility decision per `conviction_track_separation.md` § Paired-evaluation handoff. The phase MUST name the current paired-eval reference variant per that conviction. FAIL with `B12-track-A-paired-eval-missing` if the phase is absent. WARN if the phase is present but does not cite the conviction's PASS criterion (`cascade_transmission_ratio ≥ 0.20` AND `xsec_ic_per_date > 0` on val from the paired vp smoke).

   **B13. Track-B consumed-backbone-tag declaration (Track B only).** For Track B entries, the `## Sources` block MUST include a `Consumed backbone tag:` line naming the exact `firstrate_learning/<vb_variant>/.../best_model.pt` path the variant cascades from per `conviction_track_separation.md` § Cache lineage rule. FAIL with `B13-track-B-consumed-backbone-not-declared` if absent. Verify the cited path exists on disk via `ls`; if it does not exist, FAIL with `B13-consumed-backbone-tag-path-missing`.

   **B14. Eval-emission contract (track-aware).** The entry's design body MUST specify which metrics the variant's `_full_eval` will emit per `conviction_track_separation.md` § Eval-emission requirement:
   - Track A entries: must list `per_stock_ic` and (when a `p_up_logits` head exists) `brier_p_up` as PRIMARY emissions. FAIL with `B14-track-A-eval-emission-missing` if `per_stock_ic` is not specified as a primary emission.
   - Track B entries: must list `test_sharpe_net_of_10bps`, `xsec_ic_per_date`, `turnover`, and (when consuming a tagged backbone) `cascade_transmission_ratio` as PRIMARY emissions. FAIL with `B14-track-B-eval-emission-missing` if any of these are missing for an applicable Track B entry.

   **B16. Foresight-relative target citation (Track B only, Cycle 434.75+).** Per `conviction_signal_quality.md §Track B` § Foresight-relative target (encoded Cycle 434.74 per `vp17_strategy_reframe.md` Edit A1), Track B entries' success criteria MUST cite `foresight_sharpe_ratio_matched` thresholds (smoke-soft ≥ 0.15, prove-out-hard ≥ 0.30, tag-strict ≥ 0.40). Track B entries' eval-emission contract MUST list `foresight_sharpe_ratio_matched` as a PRIMARY emission and `foresight_baseline.sharpe_net_10bps` as a persisted intermediate. Multi-coordinate guard MUST be cited in the tag-strict criterion (`xsec_ic_per_date ≥ 0.5 × foresight_xsec_ic` AND `turnover ≤ foresight_turnover × 2.0`). FAIL with `B16-track-B-foresight-relative-missing` if any of: foresight_sharpe_ratio_matched threshold absent, helpers (`firstrate_common.metrics.foresight_sharpe_baseline` etc.) not cited, multi-coordinate guard absent. Track A entries are NOT subject to B16 (they cite the diagnostic foresight ratio per B19 below).

   **B17. Cost-regime-invariance citation (Track B only, Cycle 434.75+).** Per `conviction_signal_quality.md §Track B` § Cost-regime invariance gate (encoded per `vp17_strategy_reframe.md` Edit A4), Track B entries' tag-eligibility success criteria MUST cite the multi-cost-frame conjunction: `test_sharpe_net_of_10bps ≥ baseline_net_10bps × 1.10` AND `test_sharpe_net_of_30bps ≥ baseline_net_30bps × 1.10` AND `test_sharpe_net_of_50bps ≥ baseline_net_50bps × 1.10`. Track B entries' eval-emission contract MUST emit all three cost frames regardless of measured turnover (the legacy "30/50bps required only when turnover ≥ 1.0" is RELAXED to always-required). Anchor conversion MUST cite `firstrate_common.metrics.compute_matched_anchor_net_sharpe` as the implementation primitive. FAIL with `B17-track-B-cost-regime-invariance-missing` if any of: multi-frame conjunction not cited, all-three emission requirement not stated, anchor-conversion helper not cited.

   **B18. Regime-stratified eval (Track B only, Cycle 434.75+).** Per `conviction_signal_quality.md §Track B` § Regime-stratified evaluation (encoded per `vp17_strategy_reframe.md` Edit A5), Track B entries' eval-emission contract MUST list `test_sharpe_net_of_10bps_per_regime` (3 quantile bins by default) as a DIAGNOSTIC emission, computed via `firstrate_common.metrics.stratify_by_regime`. Tag-eligibility success criteria MUST cite the "net-positive in at least 2 of 3 regime bins" requirement. The variant's design body MUST name the regime-axis index (default: SPY 30-day rolling realized vol). FAIL with `B18-track-B-regime-stratified-eval-missing` if any of: per-regime emission absent, 2-of-3 tag rule not cited, regime-axis index unnamed.

   **B19. Foresight-handoff for Track A (Track A only, Cycle 434.75+).** Per `conviction_signal_quality.md §Track A` § Foresight-relative diagnostic + paired-eval handoff, Track A entries' tag-eligibility criteria MUST cite the paired-eval foresight-ratio condition: `paired_eval foresight_sharpe_ratio_matched ≥ 0.20` (smoke-soft floor on the paired portfolio smoke). The diagnostic `foresight_xsec_ic_ratio` (= `test_xsec_ic_per_date / foresight_xsec_ic_baseline()`, reduces to `test_xsec_ic_per_date` since baseline is 1.0) MUST be listed as a smoke-informational soft target ≥ +0.05. FAIL with `B19-track-A-foresight-handoff-missing` if any of: paired-eval foresight-ratio condition absent in tag-eligibility criteria, diagnostic foresight ratio not listed in eval emissions. Track B entries are NOT subject to B19 (Track B IS the paired-eval target, it does not have its own paired-eval handoff).

   **B20. Structural-ceiling citation (both tracks, Cycle 434.79g+).** Per `conviction_adversarial_triangulation.md` § Principle 2 and `conviction_signal_quality.md §Track B` § Structural ceiling / `conviction_signal_quality.md §Track A` § Adversarial triangulation gates, the design entry's eval-emission contract MUST list the structural-plausibility check as MANDATORY post-eval step: `firstrate_common.metrics.check_structural_plausibility(metrics)` returns `[]`. The success-criteria block MUST state that any non-empty violation list classifies the run as `STRUCTURAL_IMPLAUSIBILITY` (NOT a strike, NOT a promotion). Track B entries additionally MUST cite the foresight-Sharpe-ratio ceiling 1.05, cascade-ratio ceiling 1.05, and foresight-annual-return-ratio ceiling 1.05. Track A entries MUST cite per-stock-IC and xsec-IC ceilings of 1.0. FAIL with `B20-structural-ceiling-missing` if the ceiling rule is not cited or the post-eval check is not in the emission contract.

   **B21. Annual-return parallel-coordinate citation (Track B only, Cycle 434.79g+).** Per `conviction_signal_quality.md §Track B` § Annual percentage return — parallel coordinate, Track B entries' eval-emission contract MUST list `test_annualized_return_net_10bps` as a PRIMARY emission, computed via `firstrate_common.metrics.portfolio_annual_return`. The matched-frame foresight counterpart `foresight_annual_return_baseline` MUST be persisted into `eval_results.json::foresight_baseline.annual_return_net_10bps`. The success-criteria block MUST cite the parallel-consistency rule (`sign(test_sharpe_net_of_10bps) == sign(test_annualized_return_net_10bps)` outside dead-band). FAIL with `B21-annual-return-parallel-missing` if absent.

   **B22. Adversarial-triangulation emission contract (both tracks, Cycle 434.79g+).** Per `conviction_adversarial_triangulation.md` § Per-skill enforcement, every variant's `_full_eval` MUST call `firstrate_common.metrics.adversarial_triangulation_summary(...)` and persist the result into `training_results.json::adversarial_triangulation` and `eval_results.json::adversarial_triangulation`. Success criteria MUST cite the prove-out gate thresholds: `bootstrap_ci.sharpe_ci_lower > 0`, `random_portfolio.variant_percentile ≥ 95`, `subsample_half.both_halves_positive == True` AND `relative_spread ≤ 0.50`, `shuffled_null.p_value < 0.05`, `sign_flip.asymmetry_ratio ≤ 0.20`. The smoke-tier `subsample_half.both_halves_positive == True` AND `sign_flip.asymmetry_ratio ≤ 0.20` MUST be cited as smoke-blocking thresholds. FAIL with `B22-triangulation-emission-missing` if absent.

   **B23. Backbone parallel-pair contract (Track A only, Cycle 434.79g+).** Per `conviction_signal_quality.md §Track A` § Adversarial triangulation gates — Track A, Track A entries' eval-emission contract MUST list per-quarter mean of per-stock IC and the per-stock IC subsample-half stability metrics. Sign-consistency rule between `xsec_ic_per_date` and `per_stock_ic` MUST be cited in the success-criteria block. FAIL with `B23-backbone-parallel-pair-missing` if absent.

   **B15. Track-scoped banned-pattern check.** Cross-check the variant's design against the track-scoped experimentation-strategy conviction's banned-pattern list:
   - Track A entries: check `conviction_v13_experimentation_strategy_backbone.md` § Banned patterns. Particularly: cross-sectional rank label as PRIMARY on a per-symbol architecture without date-cohort batching is BANNED.
   - Track B entries: check `conviction_v13_experimentation_strategy_portfolio.md` § Banned patterns. Particularly: portfolio Sharpe loss for models <1000 params is BANNED.
   FAIL if the variant matches a banned pattern without an explicit override rationale citing new evidence.

5. **Write verdict to `.manager/deep_analysis_design.md`** — OVERWRITE the file each run. Mode B has its own consumer-specific output file, distinct from Mode A's `deep_analysis_launch.md` and Mode C's `deep_analysis_postrun.md`.

```markdown
# Design-Doc Audit — [timestamp]
Target: memory_design.md § <variant_name>
Triggered by: <memory_dev.md task line quoted>

## Checks
B1 Sources-block integrity: PASS / FAIL / WARN — evidence
B2 Blocking-coordinate framing: ...
B3 Gate-chain mapping: ...
B4 Numeric success criteria: ...
B5 Tagged-model protection: ...
B6 Per-track hard-cap check: PASS / FAIL / WARN — Track A count / Track B count / total
B7 Conviction coupling (track-aware): PASS / FAIL / WARN — track-scoped citations verified
B8 Rejected-alternatives completeness: ...
B9 Architectural premise verification: PASS / FAIL — cited file:line + pattern-match evidence
B10 Track-scoped success criteria: PASS / FAIL — track-scoped conviction thresholds cited
B11 Track-tag presence and folder match: PASS / FAIL — `Track:` line + folder root agreement
B12 Track-A paired-evaluation phase: PASS / FAIL / N/A (Track B) — paired-eval phase + reference variant cited
B13 Track-B consumed-backbone-tag declaration: PASS / FAIL / N/A (Track A) — `Consumed backbone tag:` path + on-disk existence
B14 Eval-emission contract: PASS / FAIL — track-appropriate primary metrics listed
B15 Track-scoped banned-pattern check: PASS / FAIL — variant does not match same-track banned patterns
B16 Foresight-relative target citation (Track B only, Cycle 434.75+): PASS / FAIL / N/A (Track A) — `foresight_sharpe_ratio_matched` ladder + multi-coordinate guard cited
B17 Cost-regime-invariance citation (Track B only, Cycle 434.75+): PASS / FAIL / N/A (Track A) — multi-cost-frame conjunction cited; all-three emission required
B18 Regime-stratified eval (Track B only, Cycle 434.75+): PASS / FAIL / N/A (Track A) — `test_sharpe_net_of_10bps_per_regime` listed; 2-of-3 bin rule cited
B19 Foresight-handoff for Track A (Track A only, Cycle 434.75+): PASS / FAIL / N/A (Track B) — paired-eval foresight-ratio condition cited; diagnostic foresight ratio in eval emissions
B20 Structural-ceiling citation (both tracks, Cycle 434.79g+): PASS / FAIL — `check_structural_plausibility` post-eval step + per-track ceilings cited
B21 Annual-return parallel-coordinate (Track B only, Cycle 434.79g+): PASS / FAIL / N/A (Track A) — `test_annualized_return_net_10bps` + sign-consistency rule cited
B22 Adversarial-triangulation emission contract (both tracks, Cycle 434.79g+): PASS / FAIL — `adversarial_triangulation_summary` call + prove-out / smoke gate thresholds cited
B23 Backbone parallel-pair contract (Track A only, Cycle 434.79g+): PASS / FAIL / N/A (Track B) — per-quarter mean IC + subsample-half + sign-consistency cited

## Quoted-source verification table
| Claimed quote | Source file:line | Match? |
| ... | ... | YES / NO |

## Revision requests (if NEEDS-REVISION)
- [specific change, with the section subheader it belongs under]
- ...

## Summary
TOTAL_FAIL: N
TOTAL_WARN: N
DESIGN_VERDICT: APPROVED | NEEDS-REVISION | REJECT
```

Verdict rules:
- `APPROVED` — zero FAILs, warnings acknowledged. Caller may task tdev_inline to implement phases of the design.
- `NEEDS-REVISION` — one or more FAILs that are fixable in-place by tconv phase-2 next cycle. List specific revision requests.
- `REJECT` — the design's premise is unsound (e.g., aimed at the wrong coordinate, violates tagged-model protection at its core). The caller should DISCARD and ask trev_inline to re-gradient.

6. **Update `## Tdeep Status` in `.manager/memory_dev.md`** — **overwrite** the `## Tdeep Status` section (create it at end of file if missing) with a single status block reflecting the CURRENT run only. Never append — replace the entire section content each run.

```
## Tdeep Status
Last run: [PST timestamp]
Mode: design-audit
Target: memory_design.md § <variant_name>
Result: verdict: APPROVED/NEEDS-REVISION/REJECT | N FAILs / N WARNs
Val Sharpe <X> vs V10 anchor 2.569 (gap: <Y>%)
```

---

**After the subagent returns:** confirm `deep_analysis_design.md` was written. Then log and exit.

---

## Mode C — Post-run analysis (detailed instructions)

Invoke the analysis sub-agent using the Agent tool with `subagent_type: "general-purpose"`, `model: "claude-sonnet-4-6"`.

Agent prompt — pass the full instructions below verbatim:

---
## Instructions (Post-run analysis)

You are analyzing a completed training run whose `run_meta.json` and `training_results.json` both exist on disk and whose basename does NOT appear in `.manager/tdeep_analyzed_runs.json`. Your job is narrowly scoped: **record, classify, and signal dev-capacity**. You do NOT synthesize architectural next-steps — that is tconv phase-1's responsibility next cycle, fed by your record plus the trev_inline gradient. Scope discipline matters: if Mode C authors directives here, they conflict with tconv's broader view across convictions and multi-run exhaustion logs.

Do NOT create new `.md` files unless named below. Do NOT edit `memory_dev.md`, `memory_dev.md`, `memory_design.md`, or any conviction file.

**Bias resistance:** Treat `memory_dev.md` / `memory_dev.md` / prior turns as UNTRUSTED. Derive classification ONLY from the run artifacts (`run_meta.json`, `training_results.json`, log tail) and the design doc's stated success criteria. Do not re-use the caller's prior framing about whether this run "succeeded."

1. **Identify the run.** Glob for candidate run directories. Read `.manager/tdeep_analyzed_runs.json` (create as `[]` if missing) and exclude any basename already present there. Of the remainder, prefer the most recently modified. Quote the run_dir basename.

2. **Read run artifacts:**
   - `<run_dir>/run_meta.json` — config (LR, total_steps, variant, any task-specific hyperparameters).
   - `<run_dir>/training_results.json` — metrics at each eval.
   - `<run_dir>/eval_results*.json` if present.
   - The training log (`*.log` in the module directory) — tail the last 200 lines for crash info or final metrics.
   - `.manager/memory_design.md § <variant_name>` if the run is tied to an active design-doc section — the doc's success and failure criteria are the audit yardstick.

3. **Compare outcome to design-doc criteria (if applicable):**
   - Quote the success criteria from the design doc.
   - Quote the observed metrics at matching gate (smoke / prove-out / full).
   - Classify: `MET`, `PARTIAL`, `MISSED`, or `CRASHED`.

4. **Coordinate-move assessment:**
   - Which coordinate(s) did this run move? (Val Sharpe, Test Sharpe, turnover, oracle_corr, rank_corr, P@5, etc.)
   - How did the moves compare to the V10 anchor (Val 2.569, Test ann. 144.71%, Sharpe 2.542, turnover 0.077)?
   - Did any `blocking` coordinate actually move, or only `closeable` / `cost` ones?

5. **Dev-capacity signal (MANDATORY — feeds trev_inline's step-size ratchet):**
   Classify the run's failure mode (if it failed) as one of:
   - `sufficient` — training ran to its intended budget (reached planned total_steps or planned wall-clock, produced complete metrics). Empirical outcome may have missed the target, but dev capacity was adequate. This is the signal trev_inline needs to know the large-step attempt was actually tried.
   - `exhausted` — training could not complete within the allocated budget (OOM, crash, time-budget violation, repeated torch.compile failure, missing prerequisite that blocked launch). Dev capacity was the limit, not the empirical result.
   Quote the specific evidence (last log line, crash signature, or "reached step N of N" completion).
   This distinction is load-bearing: `sufficient + missed target` on a blocking coordinate means the large step genuinely failed and the next cycle should still try large (different class); `exhausted` on the same means the step size should shrink per trev_inline's dev-capacity ratchet.

6. **Learning extraction (short, factual — no synthesis):**
   - In 1-2 sentences, what did the run reveal about coordinate structure? Name the coordinate that moved (or failed to move) and cite the numeric evidence.
   - If it is an exhaustion signal (same-class change, same result as prior runs), say so and quote the prior run results from training logs. Do NOT propose what the next experiment should be — tconv phase-1 will synthesize that from your record plus the trev_inline gradient plus convictions.

7. **Classification (recorded, not prescriptive):**
   One of `CONTINUE | ITERATE | PIVOT | RETIRE | STRUCTURAL_IMPLAUSIBILITY` as a *classification of what this run's evidence supports*, not a directive:
   - `CONTINUE` — criteria met at this gate; the natural next step is the next gate in the chain.
   - `ITERATE` — partial / near-miss; empirical fine-tuning within convictions is plausibly still productive.
   - `PIVOT` — criteria missed and evidence points to an architectural / class-level limit.
   - `RETIRE` — criteria met at the terminal gate (full / prove-out) OR evidence conclusively closes the design doc.
   - `STRUCTURAL_IMPLAUSIBILITY` — see step 7a below; the run's metrics are suspect, NOT the model. Variant does NOT promote, strike ledger does NOT advance.
   This classification goes into the registry file and the audit bullet. tconv reads it but is not bound by it.

7a. **Structural-plausibility audit (MANDATORY, Cycle 434.79g+ per `conviction_adversarial_triangulation.md`):**

   Before assigning the final classification, run the structural-plausibility check:

   ```python
   from firstrate_common.metrics import check_structural_plausibility, evaluate_adversarial_gates
   import json
   tr = json.load(open(f'{run_dir}/training_results.json'))
   # Flatten test/val coordinates the conviction names
   metrics = {
       'foresight_sharpe_ratio_matched': tr.get('foresight_sharpe_ratio_matched'),
       'cascade_transmission_ratio': tr.get('cascade_transmission_ratio'),
       'foresight_annual_return_ratio': tr.get('foresight_annual_return_ratio'),
       'test_xsec_ic_per_date': tr.get('test_xsec_ic_per_date'),
       'val_xsec_ic_per_date': tr.get('val_xsec_ic_per_date'),
       'test_sharpe_net_of_10bps': tr.get('test_sharpe_net_of_10bps'),
       'test_annualized_return_net_10bps': tr.get('test_annualized_return_net_10bps'),
   }
   structural_violations = check_structural_plausibility(metrics)
   tri = tr.get('adversarial_triangulation')
   triangulation_failures = evaluate_adversarial_gates(tri) if tri else None
   ```

   **Decision rules:**
   - If `structural_violations` is non-empty (any ceiling/floor/sign violation): classification := `STRUCTURAL_IMPLAUSIBILITY`. Quote each violation in the audit text. Do NOT promote. Recommend `tdebug matched-frame audit` in the postrun output. Strike ledger does NOT advance.
   - If `tr.adversarial_triangulation` is missing AND the run is smoke/prove-out/full (i.e., NOT unit-test): emit a warning bullet ("emission contract violation: adversarial_triangulation block absent") but do NOT block on this alone. Recommend variant author update the `_full_eval` to call `adversarial_triangulation_summary`. Cycle 434.79h+ this becomes a hard FAIL.
   - If `triangulation_failures` is non-empty AND the run is prove-out/full: classification := `MISSED`/`PIVOT` per the existing rules; the failures are a real measurement (regime-luck wins, monkey-portfolio matches, noise-scoring detected). Strike ledger DOES advance. Cite each failed gate by name in the audit text.
   - If `triangulation_failures` includes `subsample_half_both_positive` AND the run is smoke: classification := `MISSED`/`PIVOT` regardless of headline test_sharpe. The val/test split has a regime-split artifact (vp18 pattern). Strike ledger DOES advance.

   The structural-plausibility check is the load-bearing addition. A variant whose `foresight_sharpe_ratio_matched > 1.05` is BLOCKED at this gate; tdebug audit is dispatched; the artifact does NOT enter `tdeep_analyzed_runs.json` as a real result.

8. **Write to `.manager/deep_analysis_postrun.md`** — APPEND a new section (do NOT overwrite prior post-run sections; they accumulate for cross-run exhaustion checks).

```markdown
## Post-Run Analysis — [timestamp]
POSTRUN_ANALYSIS: <run_dir_basename>
Variant: <memory_design.md § variant_name, if tied>
Run type: <unit / smoke / prove-out / full>

### Config
- LR: ...
- total_steps: ...
- (other relevant fields per run_meta.json)

### Observed metrics vs design criteria
Criterion: "<quoted success criterion>"
Observed: <metric value at matching gate>
Classification: MET / PARTIAL / MISSED / CRASHED

### Coordinate moves
- Val Sharpe: <current> (V10 anchor 2.569, gap X%)
- Test ann. return: <current>% (V10 anchor 144.71%, gap Y%)
- Turnover: ...
- Oracle corr: ...
- (etc.)

### Dev-capacity signal
sufficient / exhausted — <quoted evidence: last log line, step reached, crash signature>

### Learning (1-2 sentences, factual only — no synthesis)
<What the numeric evidence shows about the coordinate that moved or failed to move. No prescription.>

### Structural-plausibility audit (Cycle 434.79g+)
- check_structural_plausibility violations: <count> [list each with coordinate/value/bound/kind/note, OR "none"]
- adversarial_triangulation present in training_results: yes/no [if no AND not unit-test, note emission-contract warning]
- evaluate_adversarial_gates failures: <count> [list each gate name + observed + threshold, OR "none"]

### Classification (recorded, not prescriptive)
CONTINUE / ITERATE / PIVOT / RETIRE / STRUCTURAL_IMPLAUSIBILITY — <one-sentence reason with quoted evidence>
```

9. **Append to the registry `.manager/tdeep_analyzed_runs.json`:** read the existing JSON array (create as `[]` if missing), append one object:

```json
{
  "run_dir_basename": "<basename>",
  "analyzed_at": "<ISO-8601 PST>",
  "classification": "MET|PARTIAL|MISSED|CRASHED|STRUCTURAL_IMPLAUSIBILITY",
  "recommendation": "CONTINUE|ITERATE|PIVOT|RETIRE|STRUCTURAL_IMPLAUSIBILITY",
  "dev_capacity": "sufficient|exhausted",
  "structural_violations_count": <int>,
  "triangulation_failures_count": <int|null>
}
```

Write the updated array back. This registry is the authoritative "already analyzed" record — Mode C's trigger check reads it rather than grepping the postrun file.

10. **Update `## Tdeep Status` in `.manager/memory_dev.md`** — **overwrite** the `## Tdeep Status` section (create it at end of file if missing) with a single status block reflecting the CURRENT run only. Never append — replace the entire section content each run.

```
## Tdeep Status
Last run: [PST timestamp]
Mode: post-run
Run: <run_dir_basename>
classification: MET/PARTIAL/MISSED/CRASHED/STRUCTURAL_IMPLAUSIBILITY | dev_capacity: sufficient/exhausted
classif: CONTINUE/ITERATE/PIVOT/RETIRE/STRUCTURAL_IMPLAUSIBILITY | structural_violations: <N> | triangulation_failures: <N|na>
Val Sharpe <X> vs V10 anchor 2.569 (gap: <Y>%) | Test ann. <A>% vs V10 144.71% (gap: <B>%)
```

---

**After the subagent returns:** confirm `deep_analysis_postrun.md` and `tdeep_analyzed_runs.json` were both updated. Then log and exit.
