# PROJECT MUST: Time-Efficient Actions — Build On Previous Work, Never Reset Unnecessarily

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — compute time wasted on regeneration that could be avoided by incremental building

## Conviction

Every action MUST consider time impact. When multiple approaches achieve the same goal, ALWAYS prefer the one that reuses existing results and minimizes wall-clock time. Never take an action that resets progress (recompute from scratch, discard previous solutions) when an incremental action exists (warm-start, resume, extend).

## The Time Hierarchy

Before choosing any approach, rank alternatives by time cost:

| Time Cost | Approach | When To Use |
|---|---|---|
| **Seconds** | Load existing result (cached solution, previous output) | Always first choice |
| **Minutes** | Extend existing result (add phases, refine solution) | When more computation needed |
| **Minutes** | Resume/continue from previous state | When optimization needs more iterations |
| **~1 hour** | Warm-start from related solution | When problem parameters changed moderately |
| **Hours** | Solve from scratch with default initialization | ONLY when problem fundamentally changed AND no transferable state exists |

**Rule: never jump to a lower row when a higher row can achieve the goal.**

## Patterns (DO)

### 1. Warm-Start Instead of Cold-Start
- Previous gait phase solved? → Use its solution as initial guess for next phase
- Parameters changed slightly? → Start from previous solution, don't reset to defaults
- Hardcoded initial values → Replace with values from previous optimizer output

### 2. Resume Instead of Restart
- Optimizer needs more iterations? → Continue from current state, don't restart from step 0
- Convergence not reached? → Reduce tolerance or add iterations, don't re-solve
- New constraint added? → Start from previous feasible solution, don't cold-start

### 3. Cache Expensive Computations
- Forward kinematics computed repeatedly? → Cache leg end positions between phases
- Same ground surface evaluated many times? → Precompute surface samples
- Any operation taking >5 seconds that produces deterministic output → cache it

## Anti-Patterns (DO NOT)

### 1. Resetting to Zero When Incremental Exists
- **WRONG**: Re-solving phase 4 from hardcoded slack variables when phase 3 solution exists
- **RIGHT**: Initialize phase 4 slack from phase 3 optimizer output
- **WRONG**: Recomputing all gait phases when only one constraint changed
- **RIGHT**: Re-solve only affected phases, keep valid ones

### 2. Ignoring Existing Results
- Previous solution exists → use as warm-start, don't use hardcoded defaults
- Previous output exists → load it, don't recompute
- Previous phase converged → its state is the best starting point for the next phase

### 3. Choosing Slow Path When Fast Path Available
- Full recomputation when incremental update suffices
- Solving from default init when warm-start available
- Processing all data when only delta needed

## Violations

1. **Cold-start when warm-start exists** — Starting optimization from hardcoded defaults when a previous solution is available as a better initial point.
2. **Full recomputation for incremental change** — Recomputing everything when only one parameter changed and partial results are reusable.
3. **Not caching deterministic results** — Running an expensive computation (>5 sec) that produces the same output as a previous run without checking for cached output first.
4. **Slow path without justification** — Choosing an approach >2x slower than an available alternative without documenting why.
5. **Destroying reusable results** — Deleting outputs that future computations could reuse. Archive, don't delete.
6. **Sequential when parallel possible** — Running independent computations sequentially when they could run in parallel.
