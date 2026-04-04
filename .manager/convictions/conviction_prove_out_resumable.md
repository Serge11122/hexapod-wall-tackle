# PROJECT MUST: Prove Out Chain — Resumable, Incremental, No Duplicate Work

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — prevents hours of wasted compute from untested upstream failures

## Conviction

When implementing or modifying any component in a chain of dependent modules (data processing → data loading → model training → evaluation → backtest), ALL affected downstream components must be tested incrementally before running long processes. Test the shortest runs first. Only escalate to longer runs after shorter runs pass on ALL affected components.

Every test level must be resumable and build on the previous level's work. No duplicated computation. No duplicated run directories. Each level continues from the previous level's checkpoint.

## The Chain Rule

For any change to component C in a chain A → B → C → D → E:

```
1. Unit test C                          (<2 min)
2. Unit test D (uses C's output)        (<2 min)
3. Unit test E (uses D's output)        (<2 min)
   ALL unit tests pass? →
4. Smoke test C                         (<30 min)
5. Smoke test D (uses C's smoke output) (<30 min)
6. Smoke test E (uses D's smoke output) (<30 min)
   ALL smoke tests pass? →
7. Prove-out C                          (1-3 hr)
8. Prove-out D (uses C's prove output)  (1-3 hr)
9. Prove-out E (uses D's prove output)  (1-3 hr)
   ALL prove-outs pass? →
10. Full run C, then D, then E          (hours+)
```

If step 2 fails, do NOT proceed to step 4. Fix C and restart from step 1.
If step 5 fails, do NOT proceed to step 7. Fix and restart from step 4.

## Multi-Chain Dependencies

When a component feeds multiple chains:

```
         → B1 → C1 → D1
A (modified)
         → B2 → C2
```

Unit test ALL branches: A, B1, C1, D1, B2, C2.
Smoke test ALL branches.
Prove-out ALL branches.
Only then full run.

## Resumable Progressive Runs — No Duplicate Work

Each test level MUST resume from the previous level's checkpoint, not start from scratch.

### Experiment-Based Directory Design

An **experiment** is a specific code/config variation being tested. Each experiment gets ONE timestamped directory. All gates (unit → smoke → prove-out → full) run inside the same experiment directory. Different code/config variations get separate experiment directories.

```
models/
├── exp_20260401_120000_ema_alpha03/       # Experiment: EMA with alpha=0.3
│   ├── experiment.json        # describes: code version, config, hypothesis
│   ├── latest_checkpoint.pt   # current state (model, optimizer, scaler, scheduler, step)
│   ├── best_model.pt          # best validation checkpoint
│   ├── gate_unit.json         # marker: unit test passed, timestamp, results
│   ├── gate_smoke.json        # marker: smoke test passed, timestamp, results
│   ├── gate_prove.json        # marker: prove-out passed, timestamp, results
│   └── gate_full.json         # marker: full run completed, timestamp, results
│
├── exp_20260402_090000_ema_alpha05/       # Experiment: EMA with alpha=0.5
│   ├── experiment.json
│   ├── latest_checkpoint.pt
│   ├── gate_unit.json
│   └── gate_smoke.json
│
└── exp_20260403_140000_prev_weight_cond/  # Experiment: previous-weight conditioning
    ├── experiment.json
    └── gate_unit.json
```

### CLI Arguments — Explicit, No Implicit Behavior

- **`--new "description"`**: Creates a new experiment directory `exp_YYYYMMDD_HHMMSS_{slug}/`. Writes `experiment.json` with description, config snapshot, source hash. Runs unit test. No implicit "find latest" behavior.
- **`--smoke <exp_dir>`**: Loads checkpoint from specified experiment dir. Requires `gate_unit.json` exists. Continues training. Writes `gate_smoke.json`.
- **`--prove-out <exp_dir>`**: Loads checkpoint. Requires `gate_smoke.json`. Continues training. Writes `gate_prove.json`.
- **`--full <exp_dir>`**: Loads checkpoint. Requires `gate_prove.json`. Continues to convergence. Writes `gate_full.json`.
- **`--resume <exp_dir>`**: Resumes from `latest_checkpoint.pt` in specified dir. Continues at the current gate level.

No implicit directory discovery. The experiment dir is always explicitly specified (except `--new` which creates it). This prevents accidentally resuming the wrong experiment.

### Gate Marker Files

Each `gate_*.json` contains:
```json
{
  "gate": "smoke",
  "passed": true,
  "timestamp": "2026-04-01T12:00:00",
  "epochs_completed": 3,
  "steps_completed": 15000,
  "metrics": {"val_sharpe": 1.2, "val_loss": 0.05},
  "source_files_hash": "sha256 of all .py files in module dir"
}
```

The `source_files_hash` invalidates the gate if any source file changes. tdeep checks this hash, not file mtimes.

### Resumability Verification

At each gate transition, the script MUST verify resumability:
- After unit test: checkpoint exists and loads without error
- After smoke test: `--resume` from smoke checkpoint produces identical first-batch output
- After prove-out: `--resume` continues from prove-out step count, not from zero

### Data Processing Resumability

Data processing scripts use `status.json` (not run directories):
```json
{
  "phase": "processing",
  "completed_quarters": ["2010Q1", "2010Q2"],
  "total_quarters": 64,
  "gate_unit": {"passed": true, "timestamp": "..."},
  "gate_smoke": {"passed": true, "timestamp": "..."},
  "source_hash": "sha256 of processing script"
}
```

Unit test processes 1-2 quarters. Smoke test continues and processes ~10 quarters. Prove-out continues to ~30 quarters. Full processes all. Each level resumes from where the previous left off.

### Cache Reuse Across Levels — Sectioned Storage

Expensive intermediate computations (backbone precompute, feature extraction, normalization stats) MUST use **sectioned storage**: one compressed file per quarter/chunk in a cache directory, with a manifest tracking completed sections.

**Cache directory structure** (shared across ALL gate levels):
```
cache/backbone/
├── manifest.json              # {hash, completed_quarters: [...], timestamp}
├── backbone_q_2010Q1.pt.zst   # section file — one per quarter
├── backbone_q_2010Q2.pt.zst
├── ...
└── backbone_q_2025Q4.pt.zst
```

**The pattern**: Each gate level reads the manifest, determines which sections already exist, computes only the missing sections, saves each new section immediately as its own file, and updates the manifest.

**Concrete example — backbone precompute cache**:
1. **Smoke** processes 16 quarters (Fridays-only subset). Saves 16 section files + manifest listing 16 completed quarters.
2. **Prove-out** reads manifest, sees 16 quarters done. Processes remaining 48 quarters. Saves each as a new section file immediately. Updates manifest after each. No existing files reloaded or rewritten.
3. **Full** reads manifest, sees 64 quarters done. Nothing to compute — cache is complete. Loads only the sections needed for training.

**Key rules**:
- **No gate-specific cache files**. There is no `_smoke.pt.zst` vs `_proveout.pt.zst`. There is one cache directory shared by all gates. Smoke creates some sections, prove-out creates more, full uses all.
- **No monolithic files**. Never store all cached data in one file. Each section is independent, loadable separately.
- **Selective loading**. Training loads only the sections containing dates in its train/val/test splits, not all sections.
- **Immediate save**. Each section saved to disk the moment it's computed. No batching, no waiting for loop completion.
- **Manifest is source of truth**. `manifest.json` lists completed sections and the hash they were computed with. If hash changes, all sections are invalidated (delete dir, recompute).
- **Parallel I/O**. Sections can be loaded in parallel via ThreadPoolExecutor — they're independent files.

## Violations

Any of the following is a violation of this conviction:

1. **Skipping downstream unit tests** — Modifying component C and running smoke/prove-out on C without first unit testing all downstream components D, E that depend on C's output
2. **Skipping upstream verification** — Running a downstream component without verifying its upstream dependency's output exists and is valid at the current test level
3. **Escalating before all chains pass** — Running smoke tests when any affected component's unit test has not passed. Running prove-out when any affected component's smoke test has not passed. Running full when any prove-out has not passed.
4. **Running full without prove-out chain** — Launching a multi-hour full run on any component without ALL components in ALL affected chains having passed prove-out
5. **No resumability verification** — Running prove-out or full without verifying the component can resume from checkpoint (load checkpoint, verify step/epoch counters, verify training continues correctly)
6. **Testing only the modified component** — Changing data processing code and only smoke-testing the data script, without also smoke-testing the training script that consumes its output
7. **Hours-long failure from untested dependency** — Any full run that fails due to an upstream component issue that would have been caught by unit or smoke testing the chain
8. **No intermediate output verification** — Running downstream component without checking that upstream's output files exist, are the correct format, and contain expected data
9. **Stale gate after code change** — Launching any gate level when source files have changed since the previous gate passed. tdeep checks `source_files_hash` in gate marker vs current hash of module .py files. If hash differs, gate is invalidated — must re-run from unit test.
10. **No gate marker files** — Running `--prove-out` when no `gate_smoke.json` exists in the run directory, or `--full` when no `gate_prove.json` exists. Each gate must leave a marker as proof of completion.
11. **Duplicate experiment directories for same variation** — Creating a new experiment directory for smoke/prove-out/full of the SAME code/config variation instead of continuing in the existing experiment directory. Each progressive gate MUST reuse the same experiment directory and checkpoint. However, creating a NEW experiment directory for a DIFFERENT code/config variation (e.g. different alpha, different architecture change) is correct and expected.
12. **Recomputing cached intermediates** — Computing an expensive intermediate (>5 min) that was already cached from a previous gate level instead of loading from cache. Cache files must be checked before recomputation. This includes the backbone precompute cache. If smoke computed 800 dates of backbone features and prove-out needs 4000, prove-out must load the 800 and only compute the missing 3200 — not recompute all 4000 from scratch.
13. **Smoke test restarting from scratch** — Smoke test initializing a fresh model instead of loading the unit test's checkpoint. Each level continues from the previous level's state.
14. **No source hash in gate markers** — Gate marker files missing `source_files_hash` field, making it impossible to detect stale gates after code changes.
15. **Continuing despite regression at early gate** — If smoke test or prove-out metrics are worse than the previous known working version or best anchor, do NOT escalate to the next gate. Return to development. Specifically:
    - If smoke test Sharpe < anchor's smoke Sharpe (or comparable metric) → FAIL. Do not prove-out. Return to dev.
    - If prove-out Sharpe < anchor's prove-out Sharpe → FAIL. Do not full run. Return to dev.
    - If data processing throughput at smoke level is worse than previous version → FAIL. Return to dev.
    - If any metric collapses during a gate run (e.g. val Sharpe goes negative after being positive) → FAIL immediately. Do not wait for the run to finish. Kill and return to dev.
    - The gate marker must record metrics. tdeep and teta compare these metrics against the anchor before approving the next gate.
16. **Running longer gates despite early signs of failure** — If smoke test shows degraded behavior (metrics declining, loss diverging, overfitting), do NOT proceed to prove-out hoping it will recover. Shorter runs that fail will also fail at longer runs. Fix first, then re-run the short gate. Never waste hours on a prove-out or full run when the smoke test already showed problems.
17. **Smoke/prove-out data distribution mismatch** — Smoke test using a different data distribution than prove-out (e.g., Friday-only dates vs all weekday dates, different symbol filtering logic, different feature subsets). Smoke must use the SAME data distribution as prove-out, just less of it (fewer quarters, fewer symbols). If the day-of-week filtering, symbol selection, or feature pipeline differs between smoke and prove-out, the smoke gate is fraudulent — its metrics do not predict prove-out performance. Proven: V13 smoke on Friday-only showed Sharpe 1.334/TO 0.146, but prove-out on all weekdays showed Sharpe 0.35/TO 0.45. The smoke gate was meaningless.
18. **No anchor comparison at gate transitions** — Promoting from smoke to prove-out or prove-out to full without comparing gate metrics against the anchor model. V10 WH96 anchor: Test Sharpe 2.569, Test Annual Return 144.71%, Turnover 0.057, DD 14.0%. Gate thresholds:
    - Smoke → prove-out: Val Sharpe >= 1.28 AND Val Annual Return >= 50% AND Turnover < 0.17
    - Prove-out → full: Val Sharpe >= 1.93 AND Val Annual Return >= 100% AND Turnover < 0.11
    - Full acceptance: Test Sharpe >= 2.5 AND Test Annual Return >= 140% AND Turnover <= 0.086 AND DD <= 15%
    - Tag (production): Test Sharpe >= 2.569 AND Test Annual Return >= 144% AND Turnover <= 0.060 AND DD <= 14%

## Runtime Behavioral Tests

19. **Checkpoint exists before gate escalation** — Before launching --smoke, verify latest_checkpoint.pt exists in the run dir. Before --prove-out, verify gate_smoke.json exists. File existence check, not just grep.
20. **Resume produces correct start step** — After --resume, check log for "Resumed from step N". N must be > 0 and match the global_step in the loaded checkpoint. If N=0, resume failed silently.
21. **No duplicate run dirs for same experiment** — Count run dirs matching same w_rank and loss type. If > 1 active (non-failed), potential violation of single-experiment-directory rule.
22. **Referenced run dir must exist on disk** — Before writing --resume instructions in memory_dev.md or goal_tracker.md, verify the run directory exists: `ls -d <path>`. Proven: cycle 300 referenced run_20260404_072833_smoke but that directory did not exist on disk, causing stale resume instructions.
23. **Unit gate config must match smoke config** — Before launching smoke, verify the unit run that produced gate_unit.json used the same w_rank, rank_loss_type, and backbone_mode as the smoke launch command. A unit gate from a different config is not a valid prerequisite. Proven: latest unit run (072249) had w_rank=0.0 while smoke targets w_rank=0.3.
24. **CLI flag syntax verified before launch** — Before writing any launch command in memory_dev.md or goal_tracker.md, verify the CLI accepts the exact flags used by checking `--help`. V5 `--prove-out` is a boolean flag (no positional arg); config is passed via `--w-rank` and `--rank-loss-type`. Only `--resume` accepts a RUN_DIR positional. Proven: prove-out command had positional arg after `--prove-out` causing argparse error, wasting a cycle.
25. **Resume CLI args must match checkpoint config** — Before launching `--resume`, verify that CLI args (w_rank, rank_loss_type, learning_rate) match the checkpoint's config. `--resume` does NOT restore these from checkpoint — they come from CLI defaults (w_rank=0.0, rank_loss_type=listnet). Omitting `--w-rank 0.3 --rank-loss-type listmle` causes silent training with wrong loss. Proven: PID 345700 resumed with w_rank=0.0 instead of 0.3. run_meta.json confirmed wrong config. tdeep/teta must verify run_meta config matches intended experiment after every resume launch.
26. **run_meta.json config audit after launch** — Within 2 minutes of any resume launch, read run_meta.json and verify w_rank, rank_loss_type, learning_rate match intended values. If mismatch, kill immediately and relaunch with correct args. Do not wait for eval metrics to detect the problem.
27. **Prove-out wall-clock estimate before launch** — Before launching any prove-out, compute: total_steps × pace_s_per_step. If > 10800s (3 hours), MUST pass `--total-steps` to cap. Default prove-out steps (5 × batches_per_pass) can be 566K for V5 (26 hours). Proven: PID 467529 ran uncapped, crashed twice, wasted GPU hours.
