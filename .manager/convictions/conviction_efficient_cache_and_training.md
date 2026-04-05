# PROJECT MUST: Efficient Computation, Caching, and Resource Utilization

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — prevents wasted compute and resource exhaustion

## Conviction

All computation scripts MUST implement efficient resource utilization: compressed caching, parallel I/O where beneficial, no full-dataset memory loading, progressive test modes, and resumable checkpointing. Resources must be used efficiently without exceeding system limits.

## Violations

### Data Processing Violations

1. **Full dataset in memory** — Any script that loads all data into memory at once instead of streaming or processing in chunks
2. **Python loops over data** — Data processing using Python `for` loops over individual samples when vectorized operations (numpy, torch) would work
3. **No parallel I/O** — Sequential file reads/writes when ThreadPoolExecutor would improve throughput
4. **No resumability** — Any script missing state tracking of completed phases. Must skip completed work on restart. Resumability must be:
   - **Position-independent**: can fill any missing segment in any order
   - **Kill-safe**: if process is killed mid-segment, next restart reprocesses only the interrupted one
5. **No progress tracking** — Any script running >30 seconds without producing progress output
6. **Unbounded memory growth** — RSS grows without limit during processing instead of processing in bounded chunks

### Solver/Optimization Violations

7. **No convergence monitoring** — Running optimization without logging loss and constraint violation at regular intervals
8. **No timing instrumentation** — Not logging per-iteration timing to detect bottlenecks
9. **Iteration-based control** — Must use step-based loops, not phase-based (see `conviction_step_based_training.md`)
10. **Incomplete checkpoints** — Any checkpoint missing required fields: solver state, iteration count, best result, configuration
11. **No resume support** — Any script that cannot resume from its latest checkpoint and continue without loss of state

### Progressive Testing Violations

12. **No quick-test mode** — Any script missing a fast validation mode that completes in <2 minutes
13. **No smoke-test mode** — Any script missing an intermediate test mode that completes in <30 minutes
14. **Skipping test hierarchy** — Running full computation without passing shorter tests first. Order: quick (<2 min) → smoke (<30 min) → full
15. **No per-run output directory** — Any run not creating its own timestamped output directory with all results isolated inside

### Structural Anti-Pattern Violations

16. **Resource creation inside loop** — Expensive resources (thread pools, large allocations) created inside iteration loops instead of once outside
17. **All-or-nothing save** — Expensive intermediate results cached only AFTER all processing completes, not incrementally per segment
18. **No pipelining** — Sequential execution of independent computation stages that could overlap
19. **Overwriting existing results** — Writing output that already exists on disk without checking validity first. Check before recomputing.
20. **Monolithic output file** — All results in a single file that must be loaded entirely to use or extend. Use sectioned storage.

## Key Thresholds

| Parameter | Value |
|-----------|-------|
| Quick test budget | <2 min |
| Smoke test budget | <30 min |
| Checkpoint interval | Regular (every N iterations) |
| Max memory usage | Leave headroom, never exceed 90% |
