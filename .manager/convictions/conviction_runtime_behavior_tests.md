# PROJECT MUST: Runtime Behavioral Verification of Convictions

**Status**: ACTIVE CONVICTION
**Priority**: HIGH — static code grep misses behavioral bugs (proven: cache logic passed grep but failed at runtime)

## Conviction

Every conviction violation check MUST include three levels of verification: static analysis (code grep), runtime behavioral verification, AND structural code analysis. Static checks catch missing code patterns. Runtime checks catch incorrect logic, missing files, broken state, and integration failures. Structural analysis reads function bodies and reasons about control flow, catching architectural anti-patterns that pass both grep and runtime spot-checks. tdeep MUST run all three levels before approving any launch.

## The Pattern: Converting Static Violations to Runtime Tests

For every static violation rule, derive a runtime behavioral test:

| Static Check | Runtime Behavioral Test |
|---|---|
| "Uses zstd compression" (grep for zstd) | Cache file exists on disk at expected path AND is valid zstd (decompress test) |
| "Has resumable checkpointing" (grep for status.json) | Checkpoint/status file from previous gate actually exists on disk |
| "No epoch-based training" (grep for epoch loop) | Checkpoint file contains `global_step` as primary counter |
| "Cross-gate cache reuse" (grep for cache load) | Lower-gate cache file exists AND higher-gate code can load it |
| "GPU >70%" (grep for timing code) | Previous run's nvidia-smi readings show >70% (check log) |
| "Fail-fast validation" (grep for assert) | Quick import + init doesn't crash (< 10s) |

## Static → Runtime → Structural Conversion Table

| Static Check | Runtime Check | Structural Check |
|---|---|---|
| "Uses ProcessPoolExecutor" (grep) | "Workers are running" (ps count) | "Pool created once, not per-iteration" (read function) |
| "Uses zstd cache" (grep) | "Cache file exists on disk" (ls) | "Cache saved incrementally, not all-at-once" (read save location) |
| "Uses GPU inference" (grep) | "GPU util >70%" (nvidia-smi) | "CPU/GPU work is pipelined" (read function flow) |
| "No Python loops" (grep for `for`) | "RSS stable" (memory check) | "Data assembly uses vectorized ops" (read accumulation code) |

## Structural Analysis Checks

Structural analysis reads the actual function body and reasons about control flow, not just pattern-matching. It catches:

- **Parallel primitives used in wrong structure** — pool inside loop (created and destroyed per iteration instead of once)
- **Missing architectural patterns** — no pipelining between CPU and GPU, no incremental save, all-or-nothing cache writes
- **Resource scaling issues** — worker count times memory per worker exceeds available RAM, unbounded queue growth
- **Algorithmic inefficiency** — Python loops where vectorized numpy/torch ops should be used, repeated allocation inside hot paths

Structural checks require tdeep to actually read the key functions (not just grep for keywords) and trace the control flow for anti-patterns before approving launch.

## Runtime Test Categories

1. **File existence** — expected cache, checkpoint, gate marker, config files exist on disk before launch
2. **File validity** — files are not empty, not corrupt, can be loaded (torch.load, json.load, zstd decompress)
3. **State continuity** — checkpoint from previous gate matches current code (hash check), contains required fields
4. **Quick execution** — unit-test or import completes without crash, error, or hang (< 30s timeout)
5. **Resource verification** — previous run logs show healthy GPU/memory, no OOM, no thrashing
6. **Cross-component** — upstream output exists and is valid before launching downstream component

## Test Execution Rules

- Each behavioral test MUST complete in < 30 seconds
- Tests run IN ADDITION to static checks, not instead of
- Behavioral failures are violations — they block launch
- Test results reported as BEHAVIOR_PASS / BEHAVIOR_FAIL with file paths or evidence
- tdeep runs all applicable behavioral tests before writing RECOMMENDATION

## Violations

Any of the following is a violation of this conviction:

1. **Static-only conviction checks** — Any conviction that has violations defined only as code pattern greps without corresponding runtime behavioral tests
2. **tdeep skipping runtime tests** — tdeep approving a launch based only on static grep analysis without running any behavioral probes
3. **No file existence verification** — Approving launch when expected input files (cache, checkpoint, data) have not been verified to exist on disk
4. **No checkpoint field validation** — Approving a --smoke/--prove-out/--full launch without verifying the previous gate's checkpoint exists and contains required fields
5. **No cache validity check** — Approving launch when cache files exist but haven't been verified as loadable (could be corrupt, truncated, or from wrong code version)
6. **Behavioral test timeout** — Any single behavioral test taking > 30 seconds (test is too expensive, needs simplification)
7. **Missing behavioral test for proven gap** — When a behavioral bug is discovered (e.g., cache doesn't carry over between gates), the corresponding conviction MUST be updated with a specific runtime test within the same cycle. If the conviction is not updated, it's a violation
8. **No structural analysis in tdeep** — tdeep approving a launch without reading key functions and checking control flow for anti-patterns (pool-in-loop, all-or-nothing cache, sequential CPU/GPU, memory explosion)
9. **Structural anti-pattern not in conviction** — When a structural issue is discovered (e.g., pool created per-quarter), the corresponding conviction MUST be updated with the specific anti-pattern violation within the same cycle
10. **Cross-model rule misapplication** — Applying V13-specific rules (LR cap <=5e-5, step budget, warmup ratio) to V5 backbone training, or vice versa. teta/tdeep MUST identify which model is being trained (V5 vs V13) before applying any model-specific conviction rules. Proven: V5 smoke killed at step 1600/7000 by V13 LR cap applied to V5 (V5 uses LR=3e-4, same as v5_tag).
11. **Config mismatch between unit gate and smoke launch** — Before launching smoke, verify the unit test that produced gate_unit.json used the SAME config (w_rank, rank_loss_type, backbone_mode) as the smoke command. If the latest unit run has a different config, it is NOT a valid gate for the smoke launch. Proven: run_20260404_072249_unit had w_rank=0.0 while smoke targets w_rank=0.3 — these are different experiments.
12. **V5 learning_rate vs v5_tag mismatch** — Before any V5 smoke/prove-out launch, verify `grep learning_rate v5_wrank/config.py` matches v5_tag's LR (3e-4). If it shows 3e-6, it was incorrectly set to the proj_lr value. Proven: commits 66f89e8/4717f99 set main learning_rate to 3e-6 (100x too low for from-scratch training). All 10 winning experiments used 3e-4.
13. **teta log freshness by content, not mtime** — Before any kill decision, teta MUST read the last line of the training log and parse its embedded timestamp. If the timestamp is within 5 minutes of current time, the process is ACTIVE regardless of what file mtime says. Proven: PID 3495335 killed at step 6800/7000 (GPU 73%) because teta used stale log reads showing "04:29 UTC" while log actually contained "09:44 UTC" entries.
14. **Run dir config matches intended experiment** — Before referencing any run dir for resume or gate verification, load its run_meta.json and verify config fields (w_rank, rank_loss_type, learning_rate) match the intended experiment. Proven: cycle 317 referenced run_20260404_091736_smoke as resumable but it had w_rank=0.0, listnet, LR=3e-6 (wrong config). Multiple invalid smoke dirs accumulated from config bugs.
15. **Checkpoint config includes training hyperparams** — Load latest_checkpoint.pt and verify `ckpt['config']` contains w_rank, rank_loss_type, and learning_rate (not just model architecture fields). If missing, resume cannot validate CLI args match checkpoint. Proven: step 6000 checkpoint had empty training config — resume silently used CLI defaults (w_rank=0.0) instead of intended 0.3.
