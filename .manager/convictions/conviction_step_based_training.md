# PROJECT MUST: Iteration-Based Optimization — No Batch Resets, No Phase-Boundary Logic

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — phase-boundary resets waste compute by restarting progress

## Conviction

All optimization and solving scripts MUST use pure iteration/step-based control flow. No phase-based resets. No phase-boundary patience. Modern solvers use iteration count as the fundamental unit. This project must do the same.

### Why Phase-Based Control Wastes Resources

- **Phase-boundary resets = wasted compute**: Resetting solver state at phase boundaries discards progress. If the optimizer found a good direction, resetting loses it.
- **Coarse evaluation**: Phase-based eval checks results once per full phase. Step-based eval checks every N iterations, catching divergence faster.
- **Coarse checkpointing**: Phase-based checkpoints lose an entire phase on crash. Step-based checkpoints lose at most N iterations.

### Iteration-Based Design

```
Single loop: for step in range(start_step, total_steps)

Every 10 steps:      log loss, constraint violation
Every 100 steps:     save checkpoint, check convergence
Every phase boundary: log as "phase N" (not a loop boundary)

Early stopping:      patience_steps (iterations without improvement)
Schedule:            parameter adjustment over total_steps, not phase count
Resume:              from global_step, not phase number
```

### Data/Phase Handling

When the solver completes a gait phase, continue to the next. Log as "phase N" — this is a label for observability, NOT a loop boundary. No logic should depend on phase boundaries. No solver resets at phase boundaries.

## Violations

1. **Phase-based outer loop** — Any script using phase-based iteration as the primary loop instead of step-based
2. **Phase-boundary resets** — Resetting solver state (optimizer, initial guess) at phase boundaries instead of carrying forward
3. **Phase-based evaluation** — Running validation only at phase boundaries instead of every N iterations
4. **Phase-based checkpointing** — Saving checkpoints only at phase boundaries instead of every N steps
5. **No --total-steps equivalent** — Any script that only accepts phase count without step-based budget control
6. **Resume from phase** — Resume logic that restores phase number instead of global iteration count
