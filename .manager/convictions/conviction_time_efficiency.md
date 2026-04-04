# PROJECT MUST: Time-Efficient Actions — Build On Previous Assets, Never Reset Unnecessarily

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — hours of GPU/CPU time wasted on regeneration that could be avoided by incremental building

## Conviction

Every action taken by the timer cycle MUST consider time impact. When multiple approaches achieve the same goal, ALWAYS prefer the one that reuses existing assets and minimizes wall-clock time. Never take an action that resets progress (regenerate data, retrain from scratch, rebuild cache) when an incremental action exists (append data, resume training, extend cache).

## The Time Hierarchy

Before choosing any approach, rank alternatives by time cost:

| Time Cost | Approach | When To Use |
|---|---|---|
| **Seconds** | Load existing asset (cache, weights, data) | Always first choice |
| **Minutes** | Append/extend existing asset (side-cache, supplement, join) | When new data needed |
| **Minutes** | Resume/continue training from checkpoint | When more training needed |
| **~1 hour** | Transfer learn / fine-tune from existing weights | When new architecture needs training |
| **Hours** | Retrain from scratch with random init | ONLY when architecture fundamentally changed AND no transferable weights exist |
| **Hours** | Regenerate full cache from raw data | ONLY when raw data format changed AND no partial reuse possible |

**Rule: never jump to a lower row when a higher row can achieve the goal.**

## Patterns (DO)

### 1. Append Data Instead of Regenerate
- Need a new field in cached tokens? → Side-cache supplement (minutes), not full rebuild (hours)
- Need more training data? → Extend cache with new quarters only, keep existing
- Need different labels? → Supplementary label file joined at load time
- Need data for new split? → Generate only the new split, keep train/val/test that exist

### 2. Resume Training Instead of Restart
- Model needs more steps? → `--resume` from checkpoint, don't retrain from step 0
- New loss function? → Initialize from existing weights + new loss head, don't random init entire model
- Different learning rate? → Resume with new LR from current weights, don't restart
- Smoke → prove-out → full: each level continues from previous checkpoint, never from scratch

### 3. Transfer Learn Instead of Train From Scratch
- New model architecture? → Initialize overlapping layers from existing model weights
- V13 portfolio model? → Load V5 backbone weights (proven), only train new layers
- Larger model variant? → Copy weights for shared dimensions, random init only new capacity
- Student-teacher: train small model to match large model's outputs → faster convergence than training small model from raw data

### 4. Distill Instead of Retrain
- Need a smaller/faster model? → Distill from existing large model (hours saved)
- Need model for different data subset? → Fine-tune existing model on subset (minutes vs hours)
- Backbone retraining with new loss? → Initialize from existing best_model.pt + add new loss head, don't random init 679K params

### 5. Precompute and Cache Expensive Operations
- Backbone inference is expensive → cache features, load for portfolio training (2 min vs 48 min)
- Token preparation is expensive → cache tokens, never re-parse raw CSV unless code changed
- Normalization stats are expensive → compute once, store in norm_stats.npz, load at runtime
- Any operation taking >5 min that produces deterministic output → cache it

## Anti-Patterns (DO NOT)

### 1. Resetting to Zero When Incremental Exists
- **WRONG**: Retrain V5 backbone from random weights to add ranking loss → hours of training
- **RIGHT**: Load existing V5 best_model.pt, add ranking loss head, fine-tune → ~1 hour
- **WRONG**: Rebuild 35 GB token cache to add one date_int column → 4-6 hours CPU
- **RIGHT**: Generate date_int as side-cache supplement → 10 minutes
- **WRONG**: Delete all cache on mode change (smoke→full) → hours of regeneration
- **RIGHT**: Archive smoke cache, generate only missing full-mode quarters

### 2. Ignoring Existing Assets
- Trained weights exist → use them as initialization, don't random init
- Cached features exist → load them, don't recompute backbone inference
- Previous checkpoint exists → resume from it, don't restart training
- Previous experiment produced useful weights → transfer them to new experiment

### 3. Choosing Slow Path When Fast Path Available
- Full retraining when fine-tuning suffices
- Full cache rebuild when supplement suffices
- Processing all data when only delta needed
- Running from step 0 when checkpoint at step 5000 exists

## Time Impact Assessment (MANDATORY for tconv/tdev)

Before assigning any task, tconv MUST estimate:
1. **Time cost of proposed action** (minutes/hours)
2. **Time cost of alternative approaches** (is there a faster way?)
3. **Assets available for reuse** (existing weights, caches, checkpoints)
4. **Time saved by reuse** vs time cost of the incremental approach

tdev MUST check before implementing:
1. Does a checkpoint/weight file exist that can be resumed/transferred?
2. Does a cache exist that can be extended instead of rebuilt?
3. Can the change be done as a supplement/overlay instead of modifying the source?

## Violations

1. **Full rebuild when supplement exists** — Regenerating an entire cache to add a field that could be a side-cache. Time cost: hours instead of minutes.

2. **Training from random init when pretrained weights exist** — Starting model training from scratch when compatible weights exist from a previous experiment or tagged model. Must initialize from existing weights and fine-tune.

3. **Full cache regeneration on mode change** — Deleting and rebuilding cache when switching modes (unit/smoke/full) instead of keeping valid data and computing only the delta.

4. **Restarting training instead of resuming** — Running `--smoke-test` from step 0 when a checkpoint from a previous smoke exists at step 3000. Must resume unless code changed fundamentally (new architecture, not just hyperparameters).

5. **Not considering transfer learning** — Training a new model variant from scratch when >50% of the architecture is shared with an existing trained model. Shared layers must be initialized from the existing model.

6. **Recomputing deterministic results** — Running an expensive computation (>5 min) that produces the same output as a previous run. Must check for cached output first.

7. **No time estimate in task assignment** — tconv assigning a task without estimating time cost and checking for faster alternatives. Every task in memory_dev.md must include: "Estimated time: X. Faster alternative considered: Y."

8. **Slow path without justification** — Choosing an approach that takes >2x longer than an available alternative without documenting why the slow path is necessary. "Rebuild from scratch because it's simpler" is NOT a valid justification when resume/extend exists.

9. **Destroying reusable assets** — Deleting weights, caches, or checkpoints that future experiments could reuse. Even failed experiments may produce weights useful for transfer learning. Archive, don't delete.

10. **Sequential when parallel possible** — Running independent tasks (e.g., two experiments, cache generation + model training on different data) sequentially when they could run in parallel. If GPU is idle during CPU-bound cache generation, a small GPU experiment could run simultaneously.

## Runtime Behavioral Tests

Static checks define principles but miss idle resources and missed reuse. These runtime tests MUST also pass:

11. **GPU not idle when experiment ready** — Check `nvidia-smi` GPU utilization. If 0% AND goal_tracker has a NEXT experiment marked, GPU is wasting time. CRITICAL time violation.
12. **No cache rebuild when existing cache valid** — Before any cache generation, check manifest.json. If current hash matches and sections exist, cache is valid. Log "Cache valid, skipping rebuild". If rebuild happens anyway, time violation.
13. **Checkpoint reuse on resume** — When `--resume` or gate escalation launches, verify it loads existing checkpoint (log line "Resumed from step N") rather than starting fresh (log line "Starting from step 0" when checkpoint exists).
14. **Prove-out wall-clock estimate before launch** — Before launching any prove-out, compute: total_steps × pace_s_per_step. If result > 10800s (3 hours), MUST cap with `--total-steps`. Proven: V5 prove-out launched at 566K steps × 0.165s = 26 hours, crashed twice, wasted hours of GPU time. Correct cap: 50K steps (~2.3 hr).
