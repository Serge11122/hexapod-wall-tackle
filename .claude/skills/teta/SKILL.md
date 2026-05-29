---
name: teta
description: "Monitor the running background process — health, progress, GPU utilization, coordinate-aware kill gate; updates ## Teta Status section in memory_dev.md each run"
user-invocable: true
---

You are checking that the running process is alive, healthy, and making useful progress against the coordinate the launch's `expect.hypothesis` names. Run the fast-path gate first; only drop into the deep checks if the fast-path flags a concern. **Overwrite** the `## Teta Status` section in `.manager/memory_dev.md` (create it at end of file if missing) with the current run's status block — do NOT append, do NOT create new `.md` files. Do NOT write `timer_cycle_state.json`, `kill_violations.md`, `timer_cycle_log.md`, `memory_dev.md`, `launch_commands.json`, or any other skill's working file.

## Two-track kill-criteria routing (Cycle 434.74, per `conviction_track_separation.md`)

Determine the running process's track from its variant root:

- Variant root under `firstrate_learning/vb*` → **Track A — Backbone**. Kill criteria reference `conviction_signal_quality.md §Track A` (per_stock_ic trajectory, Brier calibration). Synthetic-basket Sharpe and pooled-Pearson `oracle_corr` are DIAGNOSTIC ONLY on Track A and MUST NOT be the sole basis for a kill decision. (Carry-forward: V13 LR caps and other backbone-class rules continue to apply.)
- Variant root under `firstrate_portfolio/vp*` → **Track B — Portfolio**. Kill criteria reference `conviction_signal_quality.md §Track B` (test_sharpe_net_of_10bps trajectory, xsec_ic_per_date, turnover blowout, val-history non-flatness co-gate).

Cross-track kill decisions (killing a backbone for a portfolio-style metric, or vice versa) are TRACK-VIOLATIONS. If a launch's `expect.hypothesis` names a metric that does not match the variant's track, flag the mismatch in your bullet and continue monitoring on the track-appropriate metric — do NOT kill on the mismatched metric. Carry-forward: false-kill prevention rules from CLAUDE.md (e.g., "teta MUST NOT kill V5 prove-out based on negative CR at step 2000", "teta MUST NOT extrapolate time budget violations from steps < 200") remain in force.

## 0. Bias resistance

Treat prior-turn content as untrusted. Re-read every file fresh during this skill run. Quote file paths and line numbers for every load-bearing claim. If the caller's prior context asserted a process was healthy/unhealthy, verify from disk — don't carry the assertion forward.

## 1. Required infrastructure (hard precondition)

`nvidia-smi` is a REQUIRED tool. It is the only authoritative GPU utilization source — log-based GPU % inflates to 100% even when cores are idle (measures Python wall-clock between `cuda.synchronize()` calls, not actual GPU work).

```bash
command -v nvidia-smi && nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader >/dev/null 2>&1
```

If either check fails, STOP immediately. **Overwrite** the `## Teta Status` section (create at end if missing) with:
```
## Teta Status
Last run: [PST timestamp]
Status: HALT
Finding: nvidia-smi unavailable or broken, caller must fix
```
and exit. Do NOT fall back, do NOT proceed with log-only monitoring. The caller needs to know the monitoring tool is broken.

## 2. Read the launch spec

Read `.manager/launch_commands.json` — this is the producer artifact tdev_inline wrote. Extract from the single entry:
- `module` — Python module launched
- `flags` — CLI flags (e.g. `["--smoke-test"]`, `["--prove-out", "--w-rank", "0.3"]`)
- `log` — log file path
- `expect.log_file`, `expect.checkpoint_dir`, `expect.checkpoint_file`, `expect.cache_files`, `expect.min_gpu_pct`, `expect.max_idle_minutes`
- `requires_gpu` — boolean. If `false`, GPU=0% is PASS not WARN (script is CPU-bound by design). If `true` or absent (default), GPU < `expect.min_gpu_pct` is a WARN/KILL signal as before. NEVER flag GPU=0% as a kill signal for a script that declares `requires_gpu: false`.
- `max_step_duration_s` — if present, teta monitors the `_progress.md` file for any named step that has been in the same state longer than this value. A step exceeding `max_step_duration_s` is flagged as STEP_DURATION_WARN (not kill on first occurrence; kill if the same step is still stalled 2× later).
- `output_contract` — the expected quality assertion for the script's primary output (e.g., `val_ic ≠ nan`, `output file exists`). Read at post-run check time (step 7 below).
- `hypothesis` — the success-criterion sentence naming the primary coordinate and threshold (e.g. "val oracle_corr > 0.010 at best step"). Parse:
  - **coordinate name** (e.g. `oracle_corr`, `Val Sharpe`, `val_cr`) — the field teta grades against
  - **floor value** (the numeric threshold the hypothesis states)
  - **gate position** if stated (e.g. "at 25%", "at best step", "at step 6000")

If `launch_commands.json` does not exist or is `[]`, fall back to reading `.manager/launch_commands.active.json` — tdevauto moves the proposal to this path after a successful launch so the kill-gate hypothesis stays available during monitoring. Parse the same fields from the fallback file.

If BOTH files are absent or empty, go to step 3 with no launch spec (monitor whatever process is alive using sensible defaults — GPU/log freshness only, no coordinate-floor kill).

## 2b. External kill-requests (read from memory_dev.md)

Other skills (trev_inline, tconv) may write kill-request entries to the `## Kill Requests` section of `.manager/memory_dev.md`. Teta reads that section, acts, and clears it after processing. These are advisory, not executive. Teta is the sole executor.

On each run, after step 2, read the `## Kill Requests` section of `.manager/memory_dev.md` and pick up any `KILL_REQUEST` entry not yet processed. For each such request:

1. Verify the target PID is still running (`kill -0 <PID>`). If not → note `KILL_REQUEST_DROPPED pid=<N> reason=already_exited origin=<X>` in the Teta Status section and continue.
2. Re-read the cited evidence file/line FRESH. If the evidence no longer holds (e.g., log step has advanced past the cited floor-breach, coordinate has recovered) → drop with `KILL_REQUEST_DROPPED reason=evidence_stale`.
3. If PID alive AND evidence still holds → fold the request into step 5/6 as a KILL candidate with `origin=<trev_inline|tconv>` in the final status finding slot. Step 4's fast-path may still PASS-out if current measurements contradict the request — the requester's evidence must be reproducible NOW, not just when the request was authored.

Kill-requests never bypass steps 4–5. Teta's coordinate-aware gate is the floor; external requests add candidates to the same decision.

## 3. Process liveness

```bash
ps -eo pid,stat,etime,rss,args | grep python | grep -v grep | grep -v vscode | grep -E 'firstrate_|trade_|experiments'
```

- **No live process** → **overwrite** the `## Teta Status` section with `Last run: [PST timestamp]\nStatus: HEALTHY\nFinding: no processes running | standby` and exit.
- **Live process(es) found** → record PID, elapsed, RSS. Prefer the PID whose command line matches `launch_commands.json.module`.

## 4. Fast-path health gate (single-shot)

Run these checks in parallel where possible. If ALL pass, skip step 5 and go directly to step 6.

**4a. GPU utilization — single sample:**
```bash
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
```
Fast-path PASS threshold: GPU ≥ `expect.min_gpu_pct` (default 50 if absent). If below → fall through to step 5 **UNLESS** `requires_gpu: false` is set in the launch entry (CPU-bound script by design — GPU=0% is expected and is PASS). Record `gpu=0%_cpu_bound_pass` in bullet when this exemption applies.

**4b. Log freshness:**
```bash
tail -5 <log_file>
stat -c '%Y' <log_file>
```
Compare log mtime to now. Fast-path PASS: mtime within `expect.max_idle_minutes` (default 10) of now AND tail shows a progress line (step/quarter/eval). If stale → fall through.

**4c. Step monotonicity:**
```bash
grep -oE "step *[0-9]+/[0-9]+" <log_file> | tail -3
```
Fast-path PASS: last 3 step readings strictly increasing OR only one step line exists but log is fresh. If step count has not advanced in the last minute of log activity → fall through.

**4d. Coordinate floor (only if the hypothesis states a step-indexed threshold like "at 25%"):**
Parse the latest value of the hypothesis coordinate from the log. If the current step is ≥ the stated gate position AND the latest reading is below the floor → fall through to step 5 (this is the kill signal; step 5 confirms before killing).

**4e. Memory pressure (mandatory per `conviction_memory_pressure_management.md`):**
Sample the live PID's RSS, system memory %, and `_resource_log.jsonl` trajectory. Compute Δ-RSS:
```bash
RSS_KB=$(ps -p <PID> -o rss --no-headers)
RSS_GB=$(awk -v k=$RSS_KB 'BEGIN{printf "%.1f", k/1024/1024}')
# CRITICAL — `$2` MUST appear in the awk action; without it, awk treats the
# stray `kB` token as a filename and emits `awk: cannot open "kB"` errors.
# Panel evidence 2026-04-28: model truncated to `awk '/MemTotal/ {print ; exit}'`
# producing visible scrollback errors on every dispatch. Quote this line verbatim.
MEM_TOTAL_KB=$(awk '/MemTotal:/ {print $2}' /proc/meminfo)
MEM_TOTAL_GB=$(awk -v k=$MEM_TOTAL_KB 'BEGIN{printf "%.1f", k/1024/1024}')
RSS_PCT=$(awk -v r=$RSS_KB -v t=$MEM_TOTAL_KB 'BEGIN{printf "%d", r*100/t}')
SYS_USED_PCT=$(awk '/MemTotal:/ {t=$2} /MemAvailable:/ {a=$2} END {printf "%d", (t-a)*100/t}' /proc/meminfo)
RLOG=<run_dir>/_resource_log.jsonl
if [ -f "$RLOG" ] && [ "$(wc -l < $RLOG)" -ge 2 ]; then
    LAST_TWO=$(tail -2 "$RLOG")
    DELTA_RSS=$(echo "$LAST_TWO" | python3 -c "
import sys, json
lines=[json.loads(l) for l in sys.stdin]
if len(lines)<2: print('unparsed'); exit()
dt=lines[1]['timestamp']-lines[0]['timestamp']
dr=lines[1]['rss_gb']-lines[0]['rss_gb']
print(f'{dr/dt:.3f}' if dt>0 else 'unparsed')
")
    GPU_MEM_PCT=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | awk -F, '{printf "%d", $1*100/$2}')
fi
```

Apply the four-tier ladder from `conviction_memory_pressure_management.md`:
- `RSS_PCT < 50` AND `DELTA_RSS < 0.05` → fast-path PASS
- `RSS_PCT 50–70` AND `DELTA_RSS < 0.05` → fast-path PASS, record `mem=<RSS_GB>/<MEM_TOTAL_GB>` in bullet
- `RSS_PCT 50–70` AND `DELTA_RSS >= 0.05` → fall through to §5g (mem WARN watch)
- `RSS_PCT >= 70` → fall through to §5g (mem WARN-or-KILL)
- `DELTA_RSS >= 0.5` over last 2 samples → fall through to §5g (BALLOON candidate, near-certain KILL)
- `GPU_MEM_PCT >= 80` → fall through to §5g (GPU mem pressure)

If `_resource_log.jsonl` is absent (precompute phase, or train.py predates the daemon thread) — skip Δ-RSS, evaluate RSS_PCT only against the same ladder.

**4f. Step duration check (only if `max_step_duration_s` is set in launch metadata):**
```bash
# Read the _progress.md file to find the current step name and how long it's been active
PROGRESS_FILE=$(dirname <log_file>)/*_progress.md
if [ -f "$PROGRESS_FILE" ]; then
    tail -10 "$PROGRESS_FILE"
fi
```
If `max_step_duration_s` is set: parse the current step name from the progress file (look for the most recent `Step N/M:` or `▶` indicator). Compute elapsed since that step started by comparing the progress file's embedded timestamp. If elapsed > `max_step_duration_s`:
- First occurrence → STEP_DURATION_WARN: "Step `<name>` has been running `<elapsed>s` > declared max `<max_step_duration_s>s`. Possible: Python loop inefficiency, data loading bottleneck, or hang." Flag in status block but do NOT fall through to step 5 on first occurrence.
- If SAME step was WARN in the CURRENT `## Teta Status` section (check the section for matching step name + WARN) → STEP_DURATION_STALL: fall through to step 5 as a stall candidate (same severity as GPU_STALL).

If all applicable fast-path checks PASS → write the healthy bullet at step 6 and exit. Typical fast-path wall-clock: 3-5 seconds.

## 5. Deep check (only if fast-path flagged)

Only reach this step if step 4 flagged a concern. Do the 3× GPU sampling and full log analysis here — these are more expensive and only needed to confirm before killing.

**5a. 3× GPU sampling, 2s apart:**
```bash
for i in 1 2 3; do nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader; sleep 2; done
```
Take the max. If max < `expect.min_gpu_pct` → **GPU_STALL confirmed**. (2s spacing at ~0.17s/step spans ~12 steps — enough to average out per-step variance without the 10s wait the older 5s-spacing required.)

**5b. Coordinate trend — pull all readings of the hypothesis coordinate:**
```bash
grep -oE "<coordinate_name>[=: ]*-?[0-9.]+" <log_file>
```
Examples of coordinate names seen in practice:
- `Val: Sh=` for Val Sharpe
- `OracleCorr=` for oracle correlation
- `val_cr=` for cumulative return
- `val_oracle_corr=` for V13/vb6 oracle correlation

Evaluate against the hypothesis floor and trend:
- **Floor breach**: current step past gate position, coordinate below floor → KILL candidate
- **Flat for 5+ evals**: last 5 readings within ±5% of each other → KILL candidate (plateau)
- **Peak-drop ≥30% for 3+ evals**: peak seen then sustained drop → KILL candidate (destabilization)
- **Negative-after-positive**: coordinate went negative after being positive → KILL candidate (collapse)

**5c. Loss sanity:**
```bash
grep -oE "loss[=: ]+-?[0-9.]+|nan|NaN" <log_file> | tail -10
```
NaN or monotonically increasing loss → KILL candidate.

**5c-early. Class-B early-kill heuristics (per `conviction_orchestration_efficiency.md` Rules B1–B5)**

These heuristics target empirically-observed doomed-run patterns. Each rule has a high-precision predicate; until the false-kill audit lands (against V13 + vp19* + pivot historical runs), each emits `false_kill_audit_status=pending` in the kill bullet so caller can review post-hoc. After the audit confirms < 5% false-kill rate, status changes to `historical_audit_passed_at_<TS>`.

**B1 — Bit-identity collapse (scoring-head architectures only):**

Applies to Track B vp* and Track-Pivot P1/P2 (frozen-backbone or fine-tuning scoring heads). Does NOT apply to P3 end-to-end (no per-feature primary input).

Predicate:
1. eval_count ≥ 1 (at least one eval boundary completed).
2. The variant's `_full_eval` emits a per-stock score and the consumed primary feature for at least one canonical val date.
3. Compute Spearman ρ between model_score and primary_feature_score on that date.
4. If `ρ ≥ 0.9999` → KILL with `early_kill_rule=B1`, `predicate_evidence=spearman_rho=<x.xxxxxx> model_v_<feature_name>`.

The model's score has collapsed to a monotonic transform of the primary feature; further training will not produce signal beyond what the input already carries (V13 record + vp19_vb17 V36/V38/V40 pattern).

**B2 — Negative-IC trajectory:**

Applies wherever `val_xsec_ic_per_date` is in the eval emission contract (Track B, Track-Pivot P1/P2/P3).

Predicate:
1. eval_count ≥ 2.
2. val_xsec_ic_per_date at eval_1 < 0.
3. val_xsec_ic_per_date at eval_2 < val_xsec_ic_per_date at eval_1.
4. (eval_1 − eval_2) > 0.001 (meaningful decline, not noise).

If all hold → KILL with `early_kill_rule=B2`, `predicate_evidence=val_ic eval_1=<v1> eval_2=<v2> decline=<delta>`.

**B3 — Loss saturation:**

Applies to all tracks. Architecture-agnostic.

Predicate:
1. Most recent 500 step lines have loss std < 1e-4.
2. eval_count ≥ 2.
3. Val metric (foresight ratio if emitted, else val_xsec_ic_per_date, else Val Sharpe per the variant's primary metric) has linear-regression slope ≤ 0 over last 2-3 evals.

If all hold → KILL with `early_kill_rule=B3`, `predicate_evidence=loss_std=<x> step_range=<N>_to_<M> val_slope=<y>`.

**B4 — pivot exploration short-smoke verification (informational, not a kill rule):**

When the launch's `pivot_subvariant` has no prior strike-eligible run AND the launch was issued under short-smoke mode (3000 steps), monitor for a passing-gate signal at step 3000:
- If short-smoke gates PASS at the 3000-step eval → emit `- [ts] | teta | SHORT_SMOKE_PASS pid=<N> next=auto_extend_to_8000` (informational; does NOT kill; tdevauto handles the auto-extension).
- If short-smoke gates FAIL → recorded as a strike-eligible smoke (per pivot conviction); the canonical 8000-step smoke does NOT auto-launch. teta does NOT kill the still-running process at step 3000 — let it run to completion to capture full eval emission.

**B5 — Wall-clock guardrail (Track-Pivot only):**

If the variant's `config.SMOKE_WALLCLOCK_MAX_S` exists AND the run is a smoke AND wall_clock_s > 1.10 × SMOKE_WALLCLOCK_MAX_S → KILL with `early_kill_rule=B5`, `predicate_evidence=wallclock=<S>s declared_max=<M>s ratio=<r>x`.

This catches running-but-too-slow architectures whose per-step pace is within budget but whose total pace overruns. Distinct from log-staleness kill (which fires on hung processes).

**B6 — kill bullet trail (carry-forward to §7):**

Every B1–B5 kill emits these extra fields beyond the standard kill bullet format:
- `early_kill_rule=B<N>`
- `predicate_evidence=<one-line cite>`
- `false_kill_audit_status=<historical_audit_passed_at_<TS>|pending>`

If `false_kill_audit_status=pending`, tdevauto will queue a caller-review task post-kill. Pending kills are still authorized — but the killed run dir is preserved for post-hoc analysis (do NOT auto-delete).

**5d. Checkpoint liveness (training phase only):**
Determine phase:
```bash
grep -cE "step *[0-9]+/" <log_file>
```
Zero step lines → precompute phase, skip checkpoint check. Non-zero → training phase.

If training phase:
```bash
stat -c '%Y %n' <expect.checkpoint_dir>/<expect.checkpoint_file> 2>/dev/null
```
- Training started >5 min ago AND no `latest_checkpoint.pt` → **NO_CHECKPOINT** flag.
- Checkpoint mtime >10 min old while step count still advancing → **CHECKPOINT_STALE** flag.

**5e. Time budget — read from launch spec:**
- If flags include `--smoke-test` AND elapsed > `expect.max_idle_minutes × 2` (generous interpretation of "smoke budget" absent a dedicated field) → **SMOKE_OVER_BUDGET** flag. (V5-family smokes run ~55 min per CLAUDE.md; rely on the `expect` block when available rather than a hardcoded 30-min cap.)
- For prove-out/full: no hard time cap from teta; the coordinate-floor check in 5b is the kill signal.

**5f. Swap thrashing (system-level):**
```bash
free -m | grep -E "Mem|Swap"
```
Swap >4 GB → **THRASHING** flag (WARN, not KILL on its own).

**5g. Memory pressure deep check (per `conviction_memory_pressure_management.md`):**

Re-sample RSS, system memory %, and `_resource_log.jsonl` over 3 readings spaced 5s apart (matches GPU 3× sampling pattern):

```bash
RLOG=<run_dir>/_resource_log.jsonl
for i in 1 2 3; do
    ps -p <PID> -o rss --no-headers | awk '{printf "rss_kb=%d\n", $1}'
    awk '/MemTotal:/ {t=$2} /MemAvailable:/ {a=$2} END {printf "sys_used_pct=%d\n", (t-a)*100/t}' /proc/meminfo
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | awk -F, '{printf "gpu_mem_pct=%d\n", $1*100/$2}'
    sleep 5
done
[ -f "$RLOG" ] && tail -5 "$RLOG"
```

Compute peak `RSS_PCT` (max of 3 ps samples / MemTotal), peak `GPU_MEM_PCT`, and Δ-RSS rate from `_resource_log.jsonl` last 5 samples (most-recent minus oldest, divided by elapsed s).

Apply the four-tier kill ladder:
- `RSS_PCT >= 85` (peak across 3 samples) → **MEM_PRESSURE_KILL** confirmed.
- `Δ-RSS >= 0.5 GB/s` sustained across 2+ consecutive _resource_log samples → **MEM_BALLOON_KILL** confirmed (catches eval-boundary spike before kernel does).
- `GPU_MEM_PCT >= 90` (peak across 3 samples) → **GPU_MEM_PRESSURE_KILL** confirmed.
- `RSS_PCT 70–85` AND positive Δ-RSS → **MEM_WARN_RISING** flag (not kill on its own; if next dispatch shows further rise, escalate to KILL).
- `RSS_PCT 50–70` AND `Δ-RSS >= 0.05` → **MEM_WATCH** (record in bullet, do not kill).

If `_resource_log.jsonl` is absent: rely on RSS_PCT alone. The 0.5 GB/s rate gate cannot fire without two timestamped samples; the 85% absolute gate still fires.

The kill triggers in §5g are independent of and additive to the coordinate-floor kill in §5b. A run with healthy coordinate but ballooning RSS still gets killed — kernel OOM is more destructive than a coordinate-stall kill (loses checkpoint integrity, may corrupt CUDA driver state).

## 6. Decide and act

Classify the run as **HEALTHY**, **WARN**, or **KILL** based on steps 4-5:

- **HEALTHY**: fast-path all-PASS, or deep-check showed no KILL candidate.
- **WARN**: infrastructure flag only (swap thrashing, transient log gap, MEM_WATCH, MEM_WARN_RISING, mem_growth) with coordinate still on track.
- **KILL**: any KILL candidate from step 5 confirmed (coordinate-floor breach, NaN loss, MEM_PRESSURE_KILL, MEM_BALLOON_KILL, GPU_MEM_PRESSURE_KILL).

On KILL:
```bash
kill <PID>
sleep 2
kill -0 <PID> 2>/dev/null && kill -9 <PID>
```

Do NOT write `kill_violations.md`. The kill reason lands in the bullet at step 7.

**Subagent escalation (anomaly only):** If the evidence is genuinely ambiguous (unexpected log structure, conviction-compliance edge case, coordinate parse failure), spawn a Sonnet 4.6 subagent via the Agent tool (`subagent_type: "general-purpose"`, `model: "claude-sonnet-4-6"`) with the specific anomaly context and relevant log excerpt. Merge findings before writing the bullet. Sonnet 4.6 was pinned 2026-04-30 (caller-authorized) to match the Sonnet[1m] orchestrator and reduce dispatch overhead. A missed kill or false kill is load-bearing — same reasoning as tdeep/tconv — so the model ID is pinned explicitly to prevent silent default-driven downgrade. Do NOT spawn a subagent for healthy checks or clear-cut kills.

## 7. Write the run status block

Get timestamp:
```bash
TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT'
```

**Overwrite** the `## Teta Status` section in `.manager/memory_dev.md` (create it at end of file if the section does not exist). Replace the entire section content each run — never append. This keeps the file bounded.

Status block format (coordinate-aware — the coordinate name and floor come from the hypothesis parsed in step 2; `mem=` panel mandatory per `conviction_memory_pressure_management.md` rule 8):

```
## Teta Status
Last run: [PST ts]
PID: <N> | progress: <S>/<total> <unit> | pace: <X>s/<unit>
<coord>=<val> vs floor <floor> | GPU <pct>% gpu_mem=<gpu_mem_pct>% | mem=<rss_gb>/<mem_total_gb> (<rss_pct>%) Δrss=<rate>GB/s
Status: HEALTHY|WARN|KILL
Finding: <1-sentence finding or kill reason>
```

`mem=` panel rules:
- `<rss_gb>` — current process RSS in GB (1 decimal place).
- `<mem_total_gb>` — `MemTotal` from /proc/meminfo, in GB (1 decimal).
- `<rss_pct>` — `RSS / MemTotal × 100`, integer.
- `Δrss=<rate>GB/s` — Δ-RSS over the last `_resource_log.jsonl` sample pair (most recent two samples). Write `Δrss=unparsed` if log missing or only 1 sample. Write `Δrss=0.0GB/s` if rate is zero or negative (process not growing). Only show 3 decimal places when rate ≥ 0.001.
- For data-prep / cache-build runs (no PID matches the variant), still report system memory — `mem=n/a (sys=<sys_used_pct>%)` — so disk-cache builds that balloon system-level RAM are visible.
- For `no processes running | standby`, omit the entire `gpu_mem=` and `mem=` panels.

`gpu_mem=` follows the `GPU <pct>%` field as a second number, separated by a space inside the same pipe-segment.

Additional status block fields (include after the standard pipe-delimited fields):
- `requires_gpu=<true|false>` — always echo what was declared (confirms teta read it)
- `step_duration=<step_name>/<elapsed_s>s` — current step name and how long it has been running (omit if no progress file or `max_step_duration_s` not set)
- `output_contract=<pending|passed|failed>` — `pending` while running; `passed`/`failed` after run ends (step 7)

**Progress + pace fields (load-bearing for downstream ETA computation):**

- `<S>/<total>` — current and total units. `<unit>` is `step` for step-based training, `quarter` for data-prep builds, `pass` if only passes are visible. Use the unit that matches what the log actually prints; do not invent.
- `pace=<X>s/<unit>` — average seconds per unit, computed from the last ≥ 2 unit transitions in the log:
  - Step-based: `grep -oE "step *[0-9]+/" $LOG` plus matched line timestamps; pace = (t_last − t_first) / (S_last − S_first) over the last ~20 unit advances.
  - Quarter-based: same shape against `grep -oE "quarter [0-9]+/[0-9]+|[0-9]{4}_q[0-9]"` or whichever progress phrase the build emits.
  - If only 0–1 unit transitions are visible (run just started, first eval pending) → write `pace=unparsed`. Downstream skips ETA computation.
  - If pace is computed across log lines that span a long idle gap (>5× normal pace), use only the recent contiguous window — do not let a checkpoint-save pause inflate steady-state pace.

Examples:
```
## Teta Status
Last run: 2026-04-22 14:03 PT
PID: 167924 | progress: 4200/7000 step | pace: 0.165s/step
val_oracle_corr=0.0143 vs floor 0.010 | GPU 84% gpu_mem=42% | mem=18.2/62.5 (29%) Δrss=0.012GB/s
Status: HEALTHY
Finding: vb6 smoke on track, ETA ~8 min to step 7000
```

```
## Teta Status
Last run: 2026-04-22 14:03 PT
PID: 167924 | progress: 2800/7000 step | pace: 0.165s/step
val_oracle_corr=0.004 vs floor 0.010 | GPU 11% gpu_mem=44% | mem=19.0/62.5 (30%) Δrss=0.0GB/s
Status: KILL
Finding: GPU stalled 3× <15% AND coordinate below floor past 25% gate
```

```
## Teta Status
Last run: 2026-04-22 14:03 PT
Status: HEALTHY
Finding: no processes running | standby
```

If coordinate cannot be parsed from the log, write `<coord>=unparsed` in the coord line and let the status reflect it (usually WARN until the first eval lands). If the run has no coordinate (data-prep, cache-build, etc.), write `<coord>=n/a (data-prep, no coord)` and let status reflect process-liveness only.

## 8. Post-run output contract check (fires when PID exits, not during live monitoring)

When step 3 (process liveness) finds NO live process AND `launch_commands.active.json` exists (the run just ended), check the output contract before reporting the run as complete.

```bash
# Find the script's primary output artifact
OUTPUT_DIR=$(dirname <log_file>)
FINDINGS=$(ls "$OUTPUT_DIR"/*findings*.json "$OUTPUT_DIR"/*results*.json "$OUTPUT_DIR"/findings.json 2>/dev/null | head -1)
```

If `output_contract` is set in the launch metadata AND the script just ended:
1. Check whether the declared output file exists on disk. If missing → **OUTPUT_CONTRACT_FAIL: "Script exited but expected output artifact not found at `<path>`. Output contract: `<contract_string>`."**
2. If the contract includes `≠ nan` for a metric: read the output JSON and check the named field. If `null` or `NaN` → **OUTPUT_CONTRACT_FAIL: "`<metric_field>` = nan in output artifact. Output contract violated: `<contract_string>`. This may indicate a probe bug (not signal absence) — inspect before launching downstream scripts."**
3. If both checks pass → record `output_contract=passed` in the bullet.

If `output_contract` is not set: record `output_contract=not_declared` as a WARN (the launch entry is missing a contract; flag for tconv to add retroactively).

This check fires ONCE per run termination. It does not fire during live monitoring.

## Ownership boundaries (hard)

Teta writes **exactly one section**: `## Teta Status` in `.manager/memory_dev.md` (overwrite each run). Note: trev_inline and tconv are permitted to write `KILL_REQUEST` entries to the `## Kill Requests` section of memory_dev.md (see §2b); those are advisory input to teta's decision, not teta-authored. Teta reads `## Kill Requests`, acts, and clears the section after processing. Teta is still the sole actor that executes `kill`.

Teta does NOT write:
- `.manager/memory_dev.md` — tconv phase-1 owns pivots; tdev_inline and teta are read-only. If teta's findings should drive a dev task, the next tconv cycle picks them up from the teta bullet.
- `.manager/goals.md`
- `.manager/launch_commands.json` — tdev_inline owns; immutable once written.
- `.manager/deep_analysis_*.md`, `.manager/tdeep_analyzed_runs.json` — tdeep owns.
- `.manager/kill_violations.md` — retired; kill reason goes in the bullet.
- `.manager/timer_cycle_state.json`, `.manager/timer_cycle_log.md` — retired orchestrator state.
- Any file under `.manager/convictions/`, `CLAUDE.md`, `.claude/rules/*`, or any source code directory.

Exit after the status section is overwritten.
