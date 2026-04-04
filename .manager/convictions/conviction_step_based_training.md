# PROJECT MUST: Step-Based Training — No Epochs, No Epoch Patience

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — epoch-based patience wastes GPU hours training past best validation with diminishing returns

## Conviction

All training scripts MUST use pure step-based training. No epoch loops. No epoch-based patience. No epoch-based LR scheduling. Modern training (GPT, LLaMA, Claude) uses steps as the fundamental unit — not epochs. This project must do the same.

### Why Epoch-Based Training Wastes Resources

- **Epoch patience = wasted GPU time**: `PATIENCE = 15` epochs means training continues for 15 full data passes after the best validation score. If each epoch is 2+ hours, that's 30+ hours of GPU time with diminishing returns after best epoch.
- **Epochs hide progress**: If best model is at epoch 11, training runs to epoch 26 (11 + 15 patience) before stopping. Steps 12-26 produce no improvement but consume full GPU compute.
- **Coarse evaluation**: Epoch-based eval checks validation once per full data pass. Step-based eval checks every N steps (e.g. 2000), catching divergence 5-10x faster.
- **Coarse checkpointing**: Epoch-based checkpoints lose up to one full epoch on crash. Step-based checkpoints lose at most 2000 steps (~4 hours vs ~22 hours).
- **Coarse LR scheduling**: Epoch-boundary LR changes are jerky. Step-based cosine decay is smooth and proven.

### Step-Based Training Design

```
Single loop: for step in range(start_step, total_steps)

Every 50 steps:     log loss, GPU util, data_ms, gpu_ms
Every 500 steps:    log per-component loss magnitudes
Every 2000 steps:   save checkpoint, run subset validation
Every data pass:    run full validation, log as "pass N" (not "epoch N")

Early stopping:     patience_steps (default 20,000 = 10 eval cycles)
LR schedule:        cosine over total_steps with floor at 10% of peak
Resume:             from global_step, not epoch number
```

### CLI Flags

```
--total-steps N      primary training budget (mandatory)
--patience-steps N   early stopping in steps (default 20,000)
--constant-lr        optional, keeps LR constant for ablations
--epochs N           convenience only, converted to steps upfront: N * batches_per_pass
```

### Data Pass Handling

When the dataloader exhausts all chunks, reshuffle and restart. Log as "pass N" — this is a label for observability, NOT a loop boundary. No logic should depend on pass/epoch boundaries. No patience resets at pass boundaries.

## Violations

Any of the following is a violation of this conviction:

1. **Epoch loop** — Any training script using `for epoch in range(max_epochs)` or equivalent epoch-based outer loop instead of `for step in range(start_step, total_steps)`
2. **Epoch-based patience** — Any early stopping using epoch count (e.g. `PATIENCE = 15` epochs). Must use `patience_steps` (default 20,000 steps = ~10 eval cycles)
3. **Epoch-based LR scheduling** — Any LR schedule that changes at epoch boundaries (e.g. halve LR every N epochs). Must use cosine schedule over total_steps
4. **Epoch-based checkpointing** — Saving checkpoints only at epoch boundaries. Must save every 2000 steps with `global_step` field
5. **Epoch-based evaluation** — Running validation only at epoch boundaries. Must run subset eval every 2000 steps, full eval at data pass boundaries
6. **No --total-steps flag** — Any training script that only accepts `--epochs` without `--total-steps` as the primary training budget
7. **No --patience-steps flag** — Any training script using epoch patience without exposing `--patience-steps` CLI flag
8. **Epoch notation in code** — Variables named `epoch`, `max_epochs`, `PATIENCE` (epoch-based) in the training loop. Use `step`, `total_steps`, `patience_steps`. Data pass counters may use `pass_count` for logging only.
9. **Resume from epoch** — Any resume logic that restores `epoch` number and restarts from epoch boundary. Must resume from `global_step` and continue from exact position.
10. **GPU waste from stale patience** — Training running >20,000 steps past best validation without improvement. Step-based patience catches this. Epoch-based patience (15 epochs × ~11,000 steps = 165,000 steps) wastes 145,000+ steps of GPU time.

## Reference

- `todo/reference/step_based_training.md` — full design document
- `.claude/rules/training.md` lines 74-90 — mandatory step-based training rules
- `firstrate_learning/v5/train.py` — reference implementation (step-based)
- `trade_learning/train_daily_trade.py` — GPU timing instrumentation reference

## Runtime Behavioral Tests

Static grep catches missing code patterns but misses broken logic. These runtime tests MUST also pass:

11. **Checkpoint global_step field** — Load latest_checkpoint.pt from any run dir. It MUST contain `global_step` as an integer > 0. If it contains `epoch` as the primary counter (not just a logging field), it's a violation.
12. **LR follows cosine curve** — Load checkpoint, inspect scheduler state_dict. LR at step N must be within 5% of expected cosine value: `lr_floor + 0.5 * (lr_peak - lr_floor) * (1 + cos(pi * step / total_steps))`.
13. **No epoch boundary logic** — Run --unit-test. In the log output, there must be NO lines matching "Epoch \d+ complete" or "End of epoch". Data pass completions logged as "Pass N" are acceptable.
14. **Step-based patience in checkpoint** — Load checkpoint. `patience_counter` field must be an integer counting steps (>100 range), NOT epochs (typically <50).

## Current Status: V13 train.py — RESOLVED

Step-based training fully implemented. No epoch loops, no epoch patience.
