---
paths:
  - "**/train*.py"
  - "**/chunk_dataset_loader.py"
  - "**/data_loader.py"
---

# Training Rules

When creating or modifying training scripts and data loaders, enforce ALL of the following.

## Data Loading — ChunkLoader Architecture

Pre-launch violation checklist for data processing, cache, and training scripts (zstd compression, pool-in-loop, monolithic cache, GPU break-even, output contract fields, structural anti-patterns, and performance contract violations): see `conviction_efficient_cache_and_training.md` (trigger: tdeep Mode A audits, tdev_inline data/cache implementation).

- Use `ChunkLoader` + `IterableDataset` — background decompression with `preload_ahead_count=15`, `prefetch_chunks=20`, `preload_threads=4-8`
- For training: use `ChunkInterleavedDataset` with `buffer_chunks=10` (~550MB) for near-global regime mixing and shuffle
- For val/test: use `ChunkIterableDataset` for sequential streaming (no shuffle)
- Never use `MapDataset.__getitem__` with LRU cache for large chunk sets — GPU idles on cold decompression (2-5s per miss)
- `DataLoader` with `num_workers=0` — ChunkLoader's thread pool handles all I/O
- Never `num_workers>0` with IterableDataset chunk streaming — causes data duplication
- `batch_size=None` in DataLoader — Dataset yields pre-batched tensors
- **Per-run-type memory-knob asymmetry rule (P-434.45.1, Cycle 434.46)** — when a `train.py` defines per-run-type memory knobs (e.g. `_RUN_TYPE_BUFFER_CHUNKS`, `_RUN_TYPE_PRELOAD_AHEAD`, `_RUN_TYPE_TRAIN_MAX_CHUNKS`), the proveout/full-side value MUST be ≤ smoke-side value × 2, OR the source MUST contain a one-line `# RSS-justification:` comment naming why the higher value is RSS-safe given the chunk-size budget. Asymmetry beyond 2× without justification is a structural defect — it propagates the smoke-side OOM-mitigation incompletely, leaving the longer run vulnerable to the same kernel SIGKILL the smoke-side fix prevented. Evidence: Cycle 434.33 PID 506055 silent-death (smoke buffer=10 → OOM, fixed to 2) and Cycle 434.45 PID 939360 silent-death (proveout buffer=10 → OOM, same root). tdeep Mode A MUST flag a >2× asymmetry as BLOCKING when the run-type at risk is the one being launched.

## Normalization

- Normalize at runtime in Dataset/iterator: `torch.clamp((X - mean) / std.clamp(min=1e-8), -5, 5)`
- Load norm stats once at init from `norm_stats.npz`
- Never bake normalization into stored chunks

## GPU Utilization — MUST Monitor and Optimize

- Target **>70% GPU utilization** during training — this is mandatory
- Implement GPU timing instrumentation in the training loop (reference: `trade_learning/train_daily_trade.py`):

```python
total_data_time = 0.0
total_gpu_time = 0.0
for batch_idx, batch in dataloader:
    t_data_end = time.perf_counter()
    total_data_time += t_data_end - t_data_start
    # ... forward/backward/step ...
    torch.cuda.synchronize()
    t_gpu_end = time.perf_counter()
    total_gpu_time += t_gpu_end - t_gpu_start
    if batch_idx % 50 == 0:
        gpu_util = total_gpu_time / (total_data_time + total_gpu_time) * 100
        # Log: data_ms, gpu_ms, util%
```

- Log GPU utilization per epoch: `GPU util: {gpu_util:.1f}%`
- If GPU util < 50%: increase `preload_ahead_count` or `preload_threads` in ChunkLoader
- If GPU util < 30%: data loading is the bottleneck — investigate and fix before continuing

## Mixed Precision (AMP + FP16) — MANDATORY

All training scripts MUST use mixed precision FP16 training. This is not optional.

- **Always** use `torch.amp.autocast('cuda', dtype=torch.float16)` with `torch.amp.GradScaler('cuda')`
- Compute loss in float32: cast outputs to float32 before loss function (`F.binary_cross_entropy` is unsafe inside autocast)
- Pattern:
```python
scaler = torch.amp.GradScaler('cuda', enabled=True)
with torch.amp.autocast('cuda', dtype=torch.float16):
    outputs = model(X_batch)
outputs_f32 = {k: v.float() for k, v in outputs.items()}
loss = criterion(outputs_f32, targets)
scaler.scale(loss).backward()
scaler.unscale_(optimizer)
torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
scaler.step(optimizer)
scaler.update()
```
- FP16 reduces memory by ~50% and increases throughput via tensor cores on RTX 6000
- If NaN issues occur: do NOT disable AMP entirely. Instead: check for inf/nan in inputs, reduce learning rate, add gradient clipping, or use `torch.amp.autocast` with `dtype=torch.bfloat16` as fallback

## Pure Step-Based Training — MANDATORY for All Models

Full step-based training spec and violations: see `conviction_step_based_training.md`.

All training scripts MUST use pure step-based training. NO epoch loops. NO epoch-based patience.

- **Single step loop**: `for step in range(start_step, total_steps)` — no `for epoch in range(...)`.
- **Cosine LR schedule over total steps**: `lr = lr_max * 0.5 * (1 + cos(pi * step / total_steps))` with floor at 10% of peak. Total steps specified via `--total-steps` or `--epochs` (converted upfront).
- **No per-epoch LR halving**: cosine handles decay smoothly.
- **Step-based checkpointing**: save every 2000 steps with `global_step` field.
- **Step-based evaluation**: subset eval every 2000 steps, full eval at data pass boundaries (~11,300 steps for V5).
- **Step-based early stopping**: if no improvement in `patience_steps` (default 20,000 = 10 eval cycles), stop. NO epoch-level patience. NO patience resets at pass boundaries.
- **Per-component loss logging**: every 500 steps, log each loss component's value.
- **Data passes are transparent**: when dataloader exhausts, reshuffle and restart. Log as "pass N" not "epoch N". This is just a label, not a loop structure.
- **Run-type CLI completeness (P-434.44.1, applied Cycle 434.45):** Every variant `train.py` argparse MUST include CLI flags for ALL run-type strings whose internal plumbing exists (`_RUN_TYPE_DEFAULT_STEPS` keys, `_make_run_dir` accepted suffixes, `_resolve_run_type` recognized branches). Internal-plumbing-without-CLI-surface is a structural defect: it produces an apparently-supported run-type that exits at argparse with `unrecognized arguments`. tdeep Mode A MUST flag this as a BLOCKING structural failure when the proposed launch flag is missing from `_build_argparser()` despite the run-type appearing in `_RUN_TYPE_DEFAULT_STEPS`.
- **`--total-steps N`**: primary CLI flag for training budget.
- **`--epochs N`**: convenience flag, converted to steps upfront (N * batches_per_pass).
- **`--patience-steps N`**: early stopping patience in steps (default 20,000).
- **`--constant-lr` flag**: optional, keeps LR constant (useful for prove-outs and ablations).
- **Never run full training inside sub-agents**: dev sub-agent implements code, runs unit tests and prove-outs, returns the nohup launch command for the manager to execute.

## torch.compile — MANDATORY for Transformers

- Use `torch.compile(model, mode='default')` — 20-30% speedup for attention-based models. NEVER use `mode='reduce-overhead'` with variable-length inputs (causes CUDA graph errors)
- Always `torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)` before optimizer step

## ProgressTracker

- All training scripts MUST use `ProgressTracker` from `progress.progress`:

```python
tracker = ProgressTracker(Path(__file__), title, total_steps=max_epochs + 2)
tracker.start("Initializing...")
tracker.step(1, "Setup", detail="Loading data, building model")
# Per epoch:
tracker.step(epoch + 2, f"Epoch {epoch+1}/{max_epochs}",
    detail=f"val_loss={val_loss:.4f} captured_ret={val_score:.4f}")
tracker.done(f"Complete — best captured_return={best:.4f}")
```

## Pre-Run Validation — MANDATORY for Training

Full chain-gate ordering, violation catalog, gate marker spec, and cache sectioned-storage rules: see `conviction_prove_out_resumable.md`.

### Mini-smoke primitive — wide-search cheap-spread (added Cycle P16.034)

In addition to the canonical `--unit-test` (<2 min) and `--smoke-test` (<30 min training) gates, training scripts MAY implement a `--mini-smoke` mode for cheap design-space exploration. This is the SECOND gate budget tier between unit-test and full-smoke:

| Mode | Budget | Steps | Purpose |
|---|---|---|---|
| `--unit-test` | < 2 min | ~50-100 | Structural soundness (NAN-TRACE clean, head_w_norm finite, eval real) |
| `--mini-smoke` | **5-10 min** | **~200-500** | **Cheap-spread design-space sampling (label horizon, loss family, arch micro-changes)** |
| `--smoke-test` | < 30 min | 1500-3000 | K1-eligible K1 fire on `foresight_sharpe_ratio_matched ≥ 0.10` |
| `--prove-out` | < 3 hr | full | K2-eligible adversarial-triangulation gate |
| `--full` | hours+ | full | Production candidate |

**When to use mini-smoke:** when wide-search mode is engaged (per `tdevauto/SKILL.md § §3a-wide-net`) and 3-5 candidate sub-paths are simultaneously READY-NOW with substantially-different design choices, run `--mini-smoke` on each in parallel (~30 min total compute on a single GPU; ~5-10 min if multi-GPU). The mini-smoke produces a single early-eval foresight reading (typically at step 200 or 500) sufficient to **rank** sub-paths but NOT to claim K1 pass/fail. Keep the top 1-2 mini-smoke winners and deepen them to full smoke; kill the rest.

**Output contract:** `--mini-smoke` writes `gate_mini_smoke.json` with `mode="mini-smoke"`, `total_steps=<N>`, `best_eval_step=<step>`, `best_eval_foresight=<float>`, `wall_s=<float>`, `survives_unit_gates=<bool>` (NAN-TRACE clean + head_w_norm finite). NO K1 verdict emitted (mini-smoke is sub-K1 by design).

**U-rules compliance:** `--mini-smoke` MUST inherit ALL U1-U9 contracts from the parent script. The ONLY change vs `--smoke-test` is the step budget. The mode flag SHOULD be implemented as: `STEPS = 200 if args.mini_smoke else 1500 if args.smoke_test else FULL_STEPS`.

**tdeep Mode A audit:** `--mini-smoke` mode does NOT require its own Mode A audit if the parent script's `--smoke-test` is already audited and the `--mini-smoke` flag is implemented as a step-budget reduction only (no other code-path changes). The audit certifies "smoke-and-mini-smoke share code path; smoke audit covers both."

**Why this rule exists (load-bearing rationale):** The 20-cycle P16.029-P16.032 stall iterated full smokes (~22 min each) across architecturally-similar variants (v1 ISAB-128, v2 ISAB-256+LN, v3_mhsa MHSA-128). Each variant cost ~22 min smoke + ~15 min K1 eval ≈ 37 min. The same three head classes could have been sampled in 30 min total under `--mini-smoke` (10 min × 3 in sequence, or 5 min × 3 in parallel on multi-GPU). The mini-smoke primitive lowers the cost of being wrong about a wide-search sub-path by ~70%, enabling actually-wide search instead of sequential narrow-spread.

### Parallel-batch mini-smoke + auto-deepen rule (added Cycle P16.037 per `conviction_generative_cycle.md § CONV-RESOURCE-PREFLIGHT-1`)

**When ≥ 2 READY-NOW PRIMARY candidates exist** (default under wide-search mode), tdev_inline MUST author launch_commands.json with a parallel-batch entry:

```json
{
  "parallel_batch": [
    {
      "module": "firstrate_pivots.p16_cache_repair_v3_mhsa_5d.train",
      "flags": ["--mini-smoke", "--seed", "52"],
      "log": "firstrate_pivots/p16_cache_repair_v3_mhsa_5d/train_mini.log",
      "gpu_memory_estimate_mb": 8000,
      "expect": { ... },
      "pre_commit_thesis": { ... }
    },
    { "module": "...portfolio_overlay...", "flags": ["--mini-smoke"], ... },
    { "module": "...feature_eng...", "flags": ["--mini-smoke"], ... }
  ],
  "batch_strategy": "parallel",
  "auto_deepen_winner": true,
  "auto_deepen_metric": "best_eval_foresight",
  "auto_deepen_full_smoke_flags": ["--smoke-test"]
}
```

**Auto-deepen rule**: after all parallel-batch mini-smokes complete (tdevauto branch 4 detects ALL `_kill_gate_K1.json` / `gate_mini_smoke.json` files present), tdevauto compares `best_eval_foresight` across them; the WINNER (highest) is automatically promoted to full smoke (via auto-authored follow-up launch_commands.json entry); LOSERS' run_dirs are kept as AUDIT-TRAIL-RETAIN and their candidates archived to `## Considered-but-not-chosen log — archived` with the measured foresight noted.

**GPU pre-flight requirement**: per CONV-RESOURCE-PREFLIGHT-1, parallel-batch launch verifies sum of per-sub-entry `gpu_memory_estimate_mb` × 1.2 safety margin ≤ free GPU memory. Insufficient → fall back to sequential launches (one at a time, no auto-deepen until all complete).

**Audit-bullet field**: `parallel_batch_size=<N> auto_deepen_winner=<module> auto_deepen_losers=<list>`.

### Full Val Evaluation for Prove-Out Decisions — MANDATORY

Portfolio model prove-outs (and any final pass/fail decision) MUST evaluate on the FULL validation set — all chunks, all dates.

- Subset evaluations (e.g., 3/12 val chunks) are allowed ONLY for live monitoring during training (e.g., logging progress every N steps). They MUST NOT be used for pass/fail prove-out decisions.
- The final prove-out decision MUST use full val. If runtime is a constraint, reduce the number of epochs in the prove-out, not the number of val chunks evaluated per epoch.
- **Why this rule exists:** V3 iter 7 showed Val Sharpe=1.1 on 3/12 val chunks but -0.95 on all 12. The 3-chunk eval was a false positive that caused multiple wasted iterations before the true performance was discovered.

### Post-Mortem Diagnostic Handlers — MANDATORY for `--prove-out` / `--full` (P-434.47.1, applied Cycle 434.48)

Every long-running training script (`--prove-out` or `--full` mode) MUST install three post-mortem diagnostic handlers in `_main()` before entering the training loop. Without these, any silent-death (kernel SIGKILL, OOM, watchdog timeout, harness reap) leaves no programmatic post-mortem evidence beyond stdout, blocking causal diagnosis and forcing blind retries.

(a) **SIGTERM signal handler** — `signal.signal(signal.SIGTERM, _sigterm_handler)` early in `_main()`. Handler writes `<run_dir>/_crash.json` with `signal="SIGTERM"`, `last_global_step=<latest>`, `timestamp=<utc>`, then exits. SIGKILL remains uncatchable; SIGTERM is — its absence in a death is itself diagnostic (rules out orderly-shutdown paths).

(b) **atexit handler** — `atexit.register(_atexit_handler)` writing `<run_dir>/_atexit.json` with `last_global_step`, `final_rss_gb`, `final_thread_count`, `clean_exit=True`. Catches normal-exit paths (step_based_train returning); SIGKILL paths skip atexit, so absence of `_atexit.json` is diagnostic for SIGKILL.

(c) **Daemon psutil resource-log thread** — emits one JSON line every 30s to `<run_dir>/_resource_log.jsonl` with `timestamp`, `rss_gb`, `num_threads`, `cuda_alloc_gb`, `cuda_reserved_gb`, `num_open_fds`. Flush after each write. Daemon-thread so it dies cleanly with main thread. Provides post-mortem trajectory evidence even on SIGKILL.

tdeep Mode A MUST flag absence of these three handlers as BLOCKING for `--prove-out` / `--full` launches. Verify mechanically: `grep -n '_install_diagnostic_handlers\|_sigterm_handler\|_atexit_handler\|_resource_log' <variant>/train.py` returns ≥ 3 hits. Evidence: 5 consecutive vb14-proveout silent-deaths in Cycles 434.45-434.48; only the 5th (with handlers active) produced `_resource_log.jsonl` enabling the SIGKILL-by-harness diagnosis (3 readings: RSS plateau 18.88GB, threads stable at 60, no `_crash.json`, no `_atexit.json` → uncatchable kill).

## Checkpointing & Resume — MANDATORY

Gate marker files (`gate_unit.json`, `gate_smoke.json`, etc.) spec and single-experiment-directory rule: see `conviction_prove_out_resumable.md` §Single Experiment Directory.

All training scripts MUST implement full checkpoint/resume. A training script without resume is incomplete.

## Model Chain Prove-Out Rule — MANDATORY

When models form a chain (e.g., backbone → portfolio), prove out the ENTIRE chain before full-training ANY model. Full chain rule, gate marker spec, cache sectioned-storage, and all violations: see `conviction_prove_out_resumable.md`.

**Chain progression for a 2-model chain (backbone → portfolio):**

```
1. unit-test backbone, portfolio  → all pass
2. smoke-test backbone, portfolio → all pass
3. prove-out backbone, portfolio  → all pass
4. ONLY NOW: full-train backbone → full-train portfolio
```

**The dev sub-agent returns launch commands — the manager enforces chain ordering.**

### Per-Run Directory — MANDATORY

Every run creates `models/run_YYYYMMDD_HHMMSS_{type}/`. All gates (unit → smoke → prove-out → full) for the same code/config run inside that same directory. New directory = new experiment (different config), not a new gate.

`run_meta.json` must include: `run_type`, `started_at`, `config`, `n_params`, `global_step`, `seed`.

### Checkpoint Contents — Required Fields

Every checkpoint MUST include ALL of:

| Field | Purpose |
|-------|---------|
| `global_step` | Resume from exact step position |
| `model_state_dict` | Model weights |
| `optimizer_state_dict` | Optimizer momentum/state |
| `scaler_state_dict` | AMP GradScaler state |
| `scheduler_state_dict` | LR schedule position |
| `best_val_score` | For early stopping comparison |
| `patience_counter` | Steps since last improvement |
| `config` | Model architecture config |

**Missing any field = broken resume.** Checkpoint model_state_dict may have `_orig_mod.` prefix (compiled model) — resume code MUST handle both. Strip prefix BEFORE `torch.compile`, not after.

## Reference Implementations

- `firstrate_learning/chunk_dataset_loader.py` — ChunkLoader, ChunkIterableDataset, ChunkInterleavedDataset
- `firstrate_learning/train.py` — V1 training with ProgressTracker, AMP, ChunkLoader
- `firstrate_learning_v4/train.py` — V4 with torch.compile, cosine warmup, AMP
- `trade_learning/train_daily_trade.py` — GPU timing instrumentation, CUDAPrefetcher
- `trade_learning/data_loader.py` — original ChunkLoader pattern
