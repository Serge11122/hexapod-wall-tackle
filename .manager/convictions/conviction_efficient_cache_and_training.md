# PROJECT MUST: Efficient Data Caching, Processing, and Training

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — blocks server resource utilization and prevents OOM

## Conviction

All data processing scripts, model training scripts, and evaluation scripts MUST implement efficient resource utilization patterns: zstandard-compressed chunk caching, parallel prefetch data loading, GPU utilization >70%, no full-dataset memory loading, progressive test modes, and resumable checkpointing. Server resources must be maximized without exceeding 90% utilization or causing OOM.

## Violations

Any of the following is a violation of this conviction:

### Data Processing Violations

1. **No zstandard compression** — Any data output using gzip, uncompressed .pt, .npy without compression, or any format other than `.pt.zst` with `zstd.ZstdCompressor(level=3)` for new cached data
2. **Full dataset in memory** — Any script that loads all training data into memory at once instead of streaming from compressed chunks. Must use ChunkLoader or equivalent streaming pattern
3. **Python loops over data** — Any data processing using Python `for` loops over samples/rows/dates instead of vectorized operations. Specific anti-patterns:
   - CSV parsing via `for line in f: parts = line.split(',')` → use `pandas.read_csv(dtype=str, na_filter=False)` with `groupby` and `pd.to_numeric(errors='coerce')` for bulk conversion
   - `datetime.strptime()` per row → use `pd.to_datetime(series, format='%Y-%m-%d', errors='coerce')` for vectorized date parsing, or integer ordinal math
   - `for i, parts in enumerate(rows): array[i] = float(parts[col])` → use `pd.to_numeric(df.iloc[:, col]).to_numpy(dtype=np.float32)`
   - Proven: replacing Python CSV loop + strptime with pandas bulk read gave 30-40% speedup on V5 token preparation (50s→30s per quarter)
4. **No parallel I/O** — Any data processing script that reads/writes files sequentially instead of using ThreadPoolExecutor for I/O-bound or ProcessPoolExecutor for CPU-bound work
5. **No resumability** — Any data processing script missing `status.json` tracking of completed phases/splits. Must skip completed work on restart. Resumability must be:
   - **Position-independent**: can fill any missing quarter in any order (first-to-last, last-to-first, scattered). Check by quarter name, not by index position.
   - **Mode-safe**: switching from smoke→full must NOT delete full-compatible chunks. If chunks were generated with the same code but fewer files (smoke), they may be invalid for full — but the script must MOVE them to a timestamped backup, not delete. If chunks were generated in full mode, they are always valid regardless of mode switch.
   - **Kill-safe**: if process is killed mid-quarter, the partially-written quarter is not in status.json. Next restart skips completed quarters and reprocesses only the interrupted one.
5a. **Cache deletion in resumable logic** — Any data processing script that deletes existing cache chunks during mode transitions, restarts, or error recovery. Proven: V5 prepare_tokens deleted 50 completed quarters (hours of CPU work) when mode changed from a previous smoke run. Cache chunks must NEVER be deleted by processing scripts. If chunks are invalid for the new mode, move them to `cache/archive/YYYYMMDD_HHMMSS/` — never `unlink()`. Cleanup of archived caches is a separate disk management operation, not part of data processing.
5b. **Overwriting existing cache chunks** — Writing a chunk file that already exists on disk without first checking if it's valid. Before writing `chunk_NNNN.pt.zst`, check if the file exists AND the quarter is in status.json. If both true, skip. If file exists but quarter not in status (interrupted write), the file may be corrupt — move to archive, rewrite.
5c. **No timestamped cache archive** — Cache directories must support archiving: `cache/tokens/archive/YYYYMMDD_HHMMSS/` for chunks that are invalidated but not deleted. This allows restoration if the invalidation was wrong (e.g., code change reverted). Archives are cleaned by disk management conviction when disk > 85%, oldest first, never current.
6. **No progress tracking** — Any script running >30 seconds without ProgressTracker producing live `_progress.md` output
7. **Unbounded memory growth** — Any script where RSS grows without limit during processing instead of processing in bounded chunks (CHUNK_SIZE ~50,000) with explicit cleanup

### Training Violations

8. **GPU idle during data loading** — GPU utilization <50% for >5 minutes during training. Must use ChunkLoader with `preload_ahead_count=15`, `prefetch_chunks=20`, `preload_threads=4-8` to keep GPU fed
9. **No AMP/FP16** — Any training script not using `torch.amp.autocast('cuda', dtype=torch.float16)` + `GradScaler`. Mandatory for all training. Loss computed in float32
10. **No torch.compile** — Any transformer model training without `torch.compile(model, mode='default')`. Never `reduce-overhead` with variable-length inputs
11. **DataLoader num_workers >0** — Any training using DataLoader with `num_workers>0` alongside IterableDataset/ChunkLoader (causes data duplication). Must use `num_workers=0`, `batch_size=None`
12. **No timing instrumentation** — Any training script not logging `data_ms`, `gpu_ms`, `gpu_util%` per batch. Required to detect and fix data loading bottlenecks
13. **Epoch-based training** — Any training script using `for epoch in range(...)` instead of pure step-based loop `for step in range(start_step, total_steps)`. Step-based is mandatory
14. **Incomplete checkpoints** — Any checkpoint missing any of the 9 required fields: model_state_dict, optimizer_state_dict, scaler_state_dict, scheduler_state_dict, epoch/global_step, best_val_score, patience_counter, history, config
15. **No resume support** — Any training script that cannot `--resume` from its latest checkpoint and continue training without loss of state

### Progressive Testing Violations

16. **No --unit-test mode** — Any training or data processing script missing `--unit-test` flag that completes in <2 minutes
17. **No --smoke-test mode** — Any script missing `--smoke-test` flag that completes in <30 minutes (data scripts <2 min)
18. **Skipping test hierarchy** — Running `--prove-out` without passing `--smoke-test` first, or `--full` without passing `--prove-out` first. Gate order: unit (<2 min) → smoke (<30 min) → prove-out (1-3 hr) → full (hours+)
19. **No per-run directory** — Any training run not creating its own `models/run_YYYYMMDD_HHMMSS_{type}/` directory with all outputs isolated inside
20. **Prove-out on subset validation** — Any prove-out pass/fail decision based on subset validation instead of full validation set (all chunks, all dates)
20a. **Smoke test on different data distribution** — Smoke test using a data subset with different statistical properties than prove-out/full (e.g., weekly-only dates, filtered subpopulation). Smoke must use a REPRESENTATIVE subset (random sample of dates/symbols from the full set), not a structurally different subset. Friday-only dates produce artificially low turnover and artificially high Sharpe compared to daily data.

### LR/Warmup Configuration Violations

20b. **Warmup steps >= total steps** — WARMUP_STEPS must be 10-15% of total_steps for any gate level, NEVER >= total_steps. Proven: WARMUP_STEPS=3000 with 3000-step smoke meant the entire run was LR warmup — model never reached cosine decay, collapsed at step 82-350 when LR exceeded ~3.5e-5. Model found signal at LR ~8e-6 but lost it as warmup continued. Fix: WARMUP_STEPS=300 for 3000-step smoke.
20c. **No LR stability validation before smoke** — Must run unit test with new LR config and verify model doesn't collapse (Val Sharpe drops >50% from peak for 3+ consecutive evals) before launching smoke. Changing LR/warmup config invalidates the unit gate.
20d. **Peak LR exceeds proven stability range** — LEARNING_RATE must be <= 5e-5 for V13's 41K-param portfolio model. Proven: 3e-4 collapsed at step 82, 1e-4 collapsed at step 700. LR=3e-5 confirmed stable (peak Sharpe 0.376). LR dimension EXHAUSTED for this architecture. NOTE: This rule applies ONLY to V13. V5 backbone uses LR=3e-4 (same as v5_tag). Do NOT apply V13 LR caps to V5. Proven: false kill of V5 smoke at step 1600/7000.
20e. **Smoke checkpoint_every too infrequent** — Smoke test MUST use checkpoint_every=500 (not 2000). Proven: 33 min smoke with 2000-step interval produced zero checkpoints, killed with all work lost. At 0.5s/step, 500 steps = ~4 min between saves.
20f. **Excessive eval frequency in smoke** — Smoke test with 41 steps/pass should NOT eval every pass boundary (49% overhead). Eval every 3rd pass boundary. Keep step-based eval (every 2000 steps) unchanged.

### Resource Utilization Violations

21. **Server utilization >90%** — Any script consuming >90% of CPU, RAM, or GPU memory, risking OOM or system instability. Must leave headroom
22. **Single-core processing** — Any data processing script running on single core when multiple cores available. Must use `--workers` flag and parallel execution
23. **Baked normalization** — Any data stored with normalization baked in instead of storing raw data and normalizing at runtime in Dataset/iterator
24. **Inflated GPU utilization reporting** — Any training script measuring GPU utilization with Python `time.perf_counter()` between `torch.cuda.synchronize()` calls. This measures wall-clock wait time, not actual GPU core busy time, and inflates to 100% even when GPU cores are mostly idle (common with small models). Must use `torch.cuda.Event(enable_timing=True)` with `start_event.elapsed_time(end_event)` for actual GPU kernel duration. Must also sample `nvidia-smi` every 500 steps as ground truth and log both: `gpu_kernel_ms` (CUDA events) and `nvidia_smi_pct` (system-level). If the two diverge (kernel says 100%, nvidia-smi says <30%), the script has a CPU bottleneck between GPU calls that needs optimization.

### Structural Anti-Pattern Violations

25. **Pool created inside loop** — Any `ProcessPoolExecutor` or `ThreadPoolExecutor` created inside a `for` loop instead of once outside. Pool creation/teardown has overhead — create pool once, submit all work, then close. Grep pattern: `for.*:` followed by `ProcessPoolExecutor` within the loop body. Correct pattern:
    ```python
    # WRONG: pool per quarter — 62 spawns × 18 workers = 1116 process creations
    for quarter in quarters:
        with ProcessPoolExecutor(max_workers=n) as pool:  # spawns and kills 18 procs
            results = pool.map(fn, args)

    # CORRECT: pool once, reuse across all quarters
    with ProcessPoolExecutor(max_workers=n) as pool:
        for quarter in quarters:
            results = pool.map(fn, args)  # reuses existing workers
    ```
26. **All-or-nothing cache save** — Any script where expensive intermediate results (>5 min compute) are cached only AFTER all processing completes, not incrementally. Must use **sectioned storage**: one compressed file per quarter/chunk saved immediately after compute, with a manifest.json tracking completed sections. If process crashes at quarter 50/64, 50 section files exist on disk — restart reads manifest and continues from quarter 51.
27. **No CPU/GPU pipelining** — Any script that uses both CPU workers (file parsing, tokenization) and GPU inference (model forward pass) but runs them sequentially per batch. Must pipeline: parse batch N+1 on CPU while inferring batch N on GPU. Correct pattern:
    ```python
    # WRONG: sequential per quarter — CPU idle during GPU, GPU idle during CPU
    for quarter in quarters:
        samples = cpu_parse(quarter)      # CPU busy, GPU idle
        features = gpu_inference(samples)  # GPU busy, CPU idle
        save_section(quarter, features)

    # CORRECT: pipeline with concurrent.futures or threading
    from concurrent.futures import ThreadPoolExecutor
    with ProcessPoolExecutor(n) as cpu_pool, ThreadPoolExecutor(1) as gpu_thread:
        pending_gpu = None
        for quarter in quarters:
            # Start CPU parse for this quarter
            cpu_future = cpu_pool.submit(cpu_parse, quarter)
            # While CPU parses, wait for previous GPU inference to finish
            if pending_gpu is not None:
                features = pending_gpu.result()
                save_section(prev_quarter, features)
            # CPU done — submit to GPU (runs async while next CPU parse starts)
            samples = cpu_future.result()
            pending_gpu = gpu_thread.submit(gpu_inference, samples)
            prev_quarter = quarter
        # Drain last GPU result
        if pending_gpu:
            save_section(prev_quarter, pending_gpu.result())
    ```
    This overlaps CPU and GPU work. While quarter N is running backbone inference on GPU, quarter N+1 is parsing files on CPU. Nearly halves precompute wall-clock time.
28. **Worker memory explosion** — Any `ProcessPoolExecutor` where `worker_count × per_worker_RSS > 80% system RAM`. Fork-based workers inherit the parent process memory. If parent has large arrays loaded, each worker copies them. Must use memory-mapped files, shared memory, or reduce worker count. Check: `n_workers * estimated_rss < 0.8 * total_ram`.
29. **Python loop over samples in data assembly** — Any data processing function that uses `for i, item in enumerate(results)` to append samples one-by-one into lists/dicts after parallel processing. Must use vectorized numpy concatenation: `np.concatenate()`, `torch.cat()`, or pre-allocated arrays with index assignment.
30. **No cross-gate cache reuse** — Any caching scheme with gate-specific cache files (_unit.pt.zst, _smoke.pt.zst, unsuffixed.pt.zst) instead of a single shared cache directory. Must use one cache directory shared by all gates. Smoke creates some section files, prove-out creates more section files in the same directory. No data reloaded or rewritten — prove-out just adds the sections smoke didn't compute.
31. **No incremental precompute resumability** — Any precompute function that has no per-section save between iterations. Must save each section (quarter/chunk) as its own file immediately after compute and update manifest.json. On restart, read manifest, skip completed sections, continue. Never load-merge-rewrite a growing monolithic file.
32. **Monolithic cache file** — Storing all cached data in a single file that must be loaded entirely into memory to use or extend. Must use directory-based sectioned storage: one .pt.zst file per quarter/chunk + manifest.json. Training loads only the sections it needs, not everything.
33. **Selective loading violation** — Loading all cache sections into memory when only a subset is needed. Training on a val split should load only the sections containing val dates, not all sections. Use manifest to identify which sections contain which dates.

## Refactoring Requirements

Models in violation do NOT need retraining. The refactoring path is:

1. **Rewrite code only** — change data loading, checkpoint saving, CLI flags, compression format. Model weights and architecture are unchanged.
2. **Run unit test** — verify all components work (<2 min). Model loads, forward pass runs, checkpoint saves/loads, resume works.
3. **Run smoke test** — verify full pipeline (<30 min). Loss decreases, GPU util >70%, no OOM, checkpoints written correctly.
4. **Run prove-out** — verify at scale (1-3 hr). Metrics match or improve vs previous implementation. Full validation set used for pass/fail.
5. **No full retraining** — existing model weights (best_model.pt) are preserved. Only the training/eval/data infrastructure changes.

## Reference Implementations

- `firstrate_learning/v5/data_loader.py` — ChunkLoader with zstd, prefetch, IterableDataset
- `firstrate_learning/v5/train.py` — Step-based training, AMP, torch.compile, GPU timing
- `firstrate_learning/v5/prepare_tokens.py` — Resumable data prep with status.json
- `trade_learning/prepare_chunks_pt.py` — Two-phase parallel chunk writing with auto-resume
- `trade_learning/train_daily_trade.py` — GPU timing instrumentation pattern

## Key Thresholds

| Parameter | Value |
|-----------|-------|
| Compression | zstd level 3 (`.pt.zst`) |
| ChunkLoader prefetch | 20 chunks |
| ChunkLoader preload_ahead | 15 |
| ChunkLoader threads | 4-8 |
| GPU utilization target | >70% |
| GPU utilization warning | <50% |
| GPU utilization critical | <30% |
| Unit test budget | <2 min |
| Smoke test budget | <30 min |
| Prove-out budget | 1-3 hr |
| Checkpoint interval | Every 2000 steps |
| Chunk size | ~50,000 samples |
| Server max utilization | 90% (leave headroom) |
| DataLoader num_workers | 0 (ChunkLoader handles I/O) |
| Feature dtype | float32 |
| Date dtype | int32 |
| Age dtype | int16 |
| Mask dtype | bool |

## Runtime Behavioral Tests

Static grep catches code patterns but misses broken state. These runtime tests MUST also pass:

34. **Cache files are valid zstd** — For any .pt.zst cache file used by training, verify it can be decompressed: `python -c "import zstandard; zstandard.ZstdDecompressor().decompress(open('file.pt.zst','rb').read())"`. Corrupt/truncated files are a silent failure.
35. **Checkpoint has all 9 fields** — Load latest_checkpoint.pt from any active run dir. Verify all 9 fields exist: model_state_dict, optimizer_state_dict, scaler_state_dict, scheduler_state_dict, global_step, best_val_score, patience_counter, history, config.
36. **GPU utilization in recent log** — Check last 500 lines of training log for `gpu_ms` or `gpu_util`. If no GPU timing lines found, timing instrumentation is broken.
37. **DataLoader num_workers=0** — In training log or unit test, verify no DataLoader worker processes spawned (ps count of dataloader workers = 0).
38. **AMP active in checkpoint** — Load checkpoint scaler_state_dict. If empty or missing, AMP/FP16 was not active during training.
39. **Disk usage below 90% before launch** — `df -h /` shows usage < 90%. If >= 90%, block launch.
40. **teta time extrapolation NOT from warmup steps** — teta must not compute projected total time from steps < 200. torch.compile warmup inflates first 50-100 steps by 5-6x. Verify: if teta kills a run, check that the kill decision was based on pace measured AFTER step 200, not from early warmup steps. Proven: w_rank=0.4 killed at 35 min (process start) but training pace was 0.14-0.17s/step after warmup (projected ~22 min total, within 30-min budget).
41. **kill_violations.md cleared before relaunch** — Before any training launch, verify kill_violations.md either does not exist or contains "No Active Kill Violations". Stale kill records cause cascading false kills on subsequent runs. Proven: w_rank=0.05 killed by stale kill_violations from w_rank=0.1. w_rank=0.4 killed twice with stale record never cleared between attempts.
