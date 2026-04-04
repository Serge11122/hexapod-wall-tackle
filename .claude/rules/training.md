---
paths:
  - "**/train*.py"
  - "**/chunk_dataset_loader.py"
  - "**/data_loader.py"
---

# Training Rules

When creating or modifying training scripts and data loaders, enforce ALL of the following.

## Data Loading — ChunkLoader Architecture

- Use `ChunkLoader` + `IterableDataset` — background decompression with `preload_ahead_count=15`, `prefetch_chunks=20`, `preload_threads=4-8`
- For training: use `ChunkInterleavedDataset` with `buffer_chunks=10` (~550MB) for near-global regime mixing and shuffle
- For val/test: use `ChunkIterableDataset` for sequential streaming (no shuffle)
- Never use `MapDataset.__getitem__` with LRU cache for large chunk sets — GPU idles on cold decompression (2-5s per miss)
- `DataLoader` with `num_workers=0` — ChunkLoader's thread pool handles all I/O
- Never `num_workers>0` with IterableDataset chunk streaming — causes data duplication
- `batch_size=None` in DataLoader — Dataset yields pre-batched tensors

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

All training scripts MUST use pure step-based training. NO epoch loops. NO epoch-based patience.

- **Single step loop**: `for step in range(start_step, total_steps)` — no `for epoch in range(...)`.
- **Cosine LR schedule over total steps**: `lr = lr_max * 0.5 * (1 + cos(pi * step / total_steps))` with floor at 10% of peak. Total steps specified via `--total-steps` or `--epochs` (converted upfront).
- **No per-epoch LR halving**: cosine handles decay smoothly.
- **Step-based checkpointing**: save every 2000 steps with `global_step` field.
- **Step-based evaluation**: subset eval every 2000 steps, full eval at data pass boundaries (~11,300 steps for V5).
- **Step-based early stopping**: if no improvement in `patience_steps` (default 20,000 = 10 eval cycles), stop. NO epoch-level patience. NO patience resets at pass boundaries.
- **Per-component loss logging**: every 500 steps, log each loss component's value.
- **Data passes are transparent**: when dataloader exhausts, reshuffle and restart. Log as "pass N" not "epoch N". This is just a label, not a loop structure.
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

Training scripts follow the same pre-run validation cycle as data pipelines:

1. **`--smoke-test` flag required** — runs 3 epochs on full data, validates loss decreases and no NaN
2. **Mid-scale prove-out MANDATORY for new architectures/loss functions** — 10-20% of full data, 3-5 epochs. Must show:
   - (a) Val metric improves monotonically over at least 3 epochs (no collapse)
   - (b) Val metric exceeds baseline by >10% OR shows consistent learning signal
   - (c) Test metric is positive (not negative or NaN)
   - If prove-out fails ANY criterion, STOP and investigate before full training. Two false-positive smoke tests (portfolio v2) motivated this gate.

### Full Val Evaluation for Prove-Out Decisions — MANDATORY

Portfolio model prove-outs (and any final pass/fail decision) MUST evaluate on the FULL validation set — all chunks, all dates.

- Subset evaluations (e.g., 3/12 val chunks) are allowed ONLY for live monitoring during training (e.g., logging progress every N steps). They MUST NOT be used for pass/fail prove-out decisions.
- The final prove-out decision MUST use full val. If runtime is a constraint, reduce the number of epochs in the prove-out, not the number of val chunks evaluated per epoch.
- **Why this rule exists:** V3 iter 7 showed Val Sharpe=1.1 on 3/12 val chunks but -0.95 on all 12. The 3-chunk eval was a false positive that caused multiple wasted iterations before the true performance was discovered.
3. **Performance test** — during smoke test or prove-out, measure:
   - GPU utilization (must be >70%) via timing instrumentation
   - Data loading time vs GPU time ratio
   - Memory usage (should not OOM)
   - Throughput (samples/sec)
4. **Iterate** — if GPU util < 70% or data loading dominates, tune ChunkLoader params and re-test
5. **Only then full training** — launch with `nohup` after all metrics pass

### Training Progression (mandatory order)

```
unit-test → prove-out (10-20% data, 3-5 epochs) → smoke-test (full data, 3 epochs) → full training
```

- Never skip prove-out for NEW model architectures or loss functions
- Prove-out catches design flaws at ~1 hour cost instead of ~6+ hours for full training
- Existing validated recipes (same architecture, same loss, just different hyperparams) may skip directly from unit-test to smoke-test

## Checkpointing & Resume — MANDATORY

All training scripts MUST implement full checkpoint/resume so training can be stopped and resumed without losing progress. A training script without resume is incomplete.

### Run Types

Training scripts MUST support three run types via CLI:

| Flag | Type | Purpose | Duration |
|------|------|---------|----------|
| `--unit-test` | unit | Fast validation of all components (model init, forward, backward, checkpoint save/load, resume). Uses 1 epoch with max 50 batches. | <2 min |
| `--smoke-test` | smoke | Full pipeline validation (3 epochs, full data). Validates loss decreases, GPU util, checkpoint/resume. Produces weights that full run will resume from. | ~4.5 hours |
| `--full` | full | Full training run. Copies latest smoke checkpoint into new `run_*_full/` folder and continues from epoch 3+. | 10-20+ hours |
| `--full --no-smoke` | full | Full training from scratch — use ONLY when epoch time is very long (>4 hr) and unit test already validated the full pipeline. Requires explicit `--no-smoke` flag. | 10-20+ hours |

### Training Progression: unit → smoke → full (each gets its own folder)

The three run types form a progression. Each creates its own isolated run directory:

1. **`--unit-test`** — validates all components (<2 min). Creates `run_*_unit/`.
2. **`--smoke-test`** — validates full pipeline (3 epochs). Creates `run_*_smoke/` with trained weights.
3. **`--full`** — **copies** the latest smoke checkpoint into a **new** `run_*_full/` folder, then continues training from epoch 3+. Never restarts from scratch when a smoke checkpoint exists.
4. **`--resume <run_dir>`** — resumes inside the **specified** run directory (e.g., if a full run crashed at epoch 20).

```bash
# Correct progression:
python -m firstrate_learning_v4.train --unit-test                    # run_*_unit/
python -m firstrate_learning_v4.train --smoke-test                   # run_*_smoke/
python -m firstrate_learning_v4.train --full                         # run_*_full/ (copies smoke ckpt)
python -m firstrate_learning_v4.train --resume run_20260326_full     # resumes in that dir
```

**Key design principles:**
- Every run type creates its own folder — smoke and full files never mix
- `--full` copies the smoke checkpoint so both folders are self-contained
- `--resume` takes a run directory name as argument, not a boolean flag

## Model Chain Prove-Out Rule — MANDATORY

When models form a chain (e.g., backbone → portfolio), prove out the ENTIRE chain before full-training ANY model.

**Chain progression for a 2-model chain (backbone → portfolio):**

```
1. unit-test backbone            → passes
2. prove-out backbone            → passes, produces prove-out weights
3. unit-test portfolio            (loads backbone prove-out weights)  → passes
4. prove-out portfolio            (loads backbone prove-out weights)  → passes
5. ONLY NOW: full-train backbone  → produces full weights
6. ONLY NOW: full-train portfolio  (loads backbone full weights)
```

**For longer chains (A → B → C):**
```
1. prove-out A → prove-out B (using A prove-out) → prove-out C (using B prove-out)
2. ONLY after ALL prove-outs pass: full-train A → full-train B → full-train C
```

**Rationale:** Full training takes hours. If a downstream model reveals a design flaw or bug that requires changes to the upstream model, the full training time is wasted. Prove-out weights are sufficient to validate the downstream model's design, loss function, and training stability. Full training is an optimization step that should only happen once the entire pipeline is validated.

**The dev sub-agent returns launch commands — the manager enforces chain ordering.** Dev does not need to know the chain status; the manager's decision tree and perf pre-launch gate check chain completion before approving any full-training launch.
- You can resume any run type (smoke or full) by specifying its directory

### Per-Run Directory — MANDATORY

Every training run MUST create its own isolated run directory. No files from different runs should be mixed.

```python
# At training start, create a timestamped run directory
run_type = 'unit' if unit_test else ('smoke' if smoke_test else 'full')
run_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
run_dir = MODEL_DIR / f'run_{run_ts}_{run_type}'
run_dir.mkdir(parents=True, exist_ok=True)

# All outputs go inside run_dir:
#   run_dir/latest_checkpoint.pt    — every-epoch checkpoint
#   run_dir/best_model.pt           — best validation checkpoint
#   run_dir/best_model_epoch5.pt    — versioned best checkpoints
#   run_dir/run_meta.json           — run metadata (type, start time, config, etc.)
```

Run directory structure:
```
models/
├── run_20260326_190000_unit/
│   ├── run_meta.json
│   ├── latest_checkpoint.pt
│   └── best_model.pt
├── run_20260326_191500_smoke/
│   ├── run_meta.json
│   ├── latest_checkpoint.pt
│   ├── best_model.pt
│   └── best_model_epoch2.pt
├── run_20260326_200000_full/
│   ├── run_meta.json
│   ├── latest_checkpoint.pt
│   ├── best_model.pt
│   ├── best_model_epoch1.pt
│   ├── best_model_epoch5.pt
│   └── best_model_epoch12.pt
└── archive/                        — old runs moved here
```

`run_meta.json` must include:
```python
{
    "run_type": "full",              # unit | smoke | full
    "started_at": "2026-03-26T20:00:00",
    "config": { ... },               # model config
    "n_params": 4769287,
    "log_file": "output/train_v4_full_20260326_200000.log",
}
```

### Every-Epoch Checkpoint (latest_checkpoint.pt)

Save a checkpoint **every epoch** inside the run directory:

```python
latest_ckpt = _build_checkpoint(...)
torch.save(latest_ckpt, run_dir / 'latest_checkpoint.pt')
```

### Best-Model Checkpoint (best_model.pt)

Save versioned + overwrite best on validation improvement, inside the run directory:

```python
if val_score > best_val_score:
    best_val_score = val_score
    torch.save(latest_ckpt, run_dir / f'best_model_epoch{epoch+1}.pt')
    torch.save(latest_ckpt, run_dir / 'best_model.pt')
```

### Resume from Checkpoint (--resume flag)

Resume must find the **latest run directory** and load its `latest_checkpoint.pt`:

```python
parser.add_argument('--resume', action='store_true',
                    help='Resume from latest run latest_checkpoint.pt')

if resume:
    # Find most recent run_dir that has a latest_checkpoint.pt
    run_dirs = sorted(MODEL_DIR.glob('run_*'), reverse=True)
    ckpt_path = None
    for d in run_dirs:
        p = d / 'latest_checkpoint.pt'
        if p.exists():
            ckpt_path = p
            run_dir = d  # reuse the existing run directory
            break
    assert ckpt_path, "No checkpoint found in any run directory"
    ckpt = torch.load(ckpt_path, weights_only=False)
    # ... restore all state ...
```

### Checkpoint Contents — Required Fields

Every checkpoint (both latest and best) MUST include ALL of:

| Field | Purpose |
|-------|---------|
| `epoch` | Resume training from correct epoch |
| `model_state_dict` | Model weights |
| `optimizer_state_dict` | Optimizer momentum/state (critical for training continuity) |
| `scaler_state_dict` | AMP GradScaler state |
| `scheduler_state_dict` | Learning rate schedule position |
| `best_val_score` | For early stopping comparison |
| `patience_counter` | Current early stopping counter |
| `history` | Train/val metrics per epoch |
| `config` | Model architecture config for reproducibility |

**Missing any of these = broken resume.** Without optimizer state, momentum is reset. Without scheduler state, learning rate restarts from initial. Without patience_counter, early stopping resets.

### Early Stopping

- `EarlyStopping` with configurable patience (default 15)
- Patience counter MUST be saved in checkpoint and restored on resume

### Reference

- `firstrate_learning/train.py` — V1 with full resume (model + optimizer + scaler + history)
- `trade_learning/train_daily_trade.py` — batch-level checkpointing + epoch resume

## Multi-Head Loss Monitoring

When training with multiple loss components (e.g., magnitude + direction + quantile + return + contrastive):

- Log **each component's raw value** every N batches (not just the weighted total)
- Include per-component values in the epoch summary and training_results.json
- Watch for: one component dominating (>80% of total), erratic spikes in auxiliary losses, or components going to zero (collapsed head)
- If contrastive or auxiliary losses show harmful interference (val metrics degrade when enabled vs disabled), set their weight to 0 in the next run rather than removing code

## Reference Implementations

- `firstrate_learning/chunk_dataset_loader.py` — ChunkLoader, ChunkIterableDataset, ChunkInterleavedDataset
- `firstrate_learning/train.py` — V1 training with ProgressTracker, AMP, ChunkLoader
- `firstrate_learning_v4/train.py` — V4 with torch.compile, cosine warmup, AMP
- `trade_learning/train_daily_trade.py` — GPU timing instrumentation, CUDAPrefetcher
- `trade_learning/data_loader.py` — original ChunkLoader pattern
