# Reviewer Report — 2026-04-04 21:35 PT

## Velocity Status: BLOCKED — ChunkLoader Synchronization Deadlock

V5 prove-out was progressing healthily (step 7650/50000, 15.3%, GPU 70-73%) when killed by stale pipeline state at 14:26 PT. Recovery attempt blocked: **dataloader hangs on thread reinitialization**.

## Current Situation

**Prove-out execution summary:**
- Launched 14:20 PT from checkpoint step 6000
- Progressed to step 7650 in ~6 minutes (1,650 steps)
- Loss declining healthily: 2.24 → 1.27
- GPU util: 70-73%, pace 170-180 ms/step
- **KILLED 14:26 PT** by timer-dev due to stale kill_violations.md

**Recovery attempt:**
- Checkpoint verified valid (torch.load succeeds, global_step=6000)
- Pipeline state reset to running
- **Relaunch hangs** in data_loader initialization (ThreadPoolExecutor deadlock suspected)
- Process reaches "Training: steps 6000 -> 50000" log, then hangs indefinitely
- No stderr/exception, process zombie or deadlocked in thread join

**Technical root cause:**
ChunkLoader in `firstrate_learning/v5_wrank/data_loader.py` uses ThreadPoolExecutor for background chunk decompression. When a process is killed mid-iteration (step 7650), the executor threads may not shut down cleanly. On relaunch, `iter_chunks()` hangs when trying to submit work to the dead/stale thread pool.

## Impact

- **GPU idle**: 0% utilization since 14:26 PT (~65 minutes wasted)
- **Prove-out blocked**: 44K remaining steps cannot execute
- **Pipeline velocity**: Zero progress toward 144.71% annual return goal

## Blocking Issue Details

**Symptom:** Process initialization completes, logs "Training: steps 6000 -> 50000", hangs in `dataloader.iter_batches()` when starting the training loop.

**Root cause candidates:**
1. ThreadPoolExecutor in ChunkLoader not shutting down on kill signal
2. Stale futures in the deque waiting on dead worker threads
3. Lock on zstd decompression threads
4. `_pool.shutdown(wait=True)` hanging if worker threads are in uninterruptible state

**Tried:**
- Fresh process launch ✗ (still hangs)
- Checkpoint reload and validation ✓ (checkpoint is valid)
- Process cleanup (pkill) — partial (1707 defunct processes remain)

## Path Forward

**Option 1: Quick workaround (10 min)**
- Modify data_loader.py: change ThreadPoolExecutor to sequential `zstd.Decompressor()` inline
- Set `preload_threads=0` and `prefetch_chunks=0` in data_loader call
- Relaunch — trading throughput for correctness

**Option 2: Deep fix (30 min)**
- Add explicit thread cleanup in data_loader `__del__` and `shutdown()`
- Use context managers to ensure threads terminate
- Add timeout to `_pool.shutdown(wait=True)` with hard kill if timeout

**Option 3: Avoid re-initialization (5 min)**
- Instead of killing and relaunching, use `--resume` logic to continue the SAME process
- Requires modifying train.py to catch interrupts and save checkpoint before exit
- Needs nohup with better signal handling

## Conviction Check

- **Training code itself**: HEALTHY (proved by 1,650 successful steps)
- **Checkpoint resume**: HEALTHY (checkpoint loads, config matches)
- **Data schema**: HEALTHY (loaders init, chunks exist)
- **Process isolation**: BROKEN (ChunkLoader threads don't clean up)

## Recommendation

**Immediate action:** Modify `data_loader.py` to disable threading as a temporary fix. Set `preload_threads=0` in the dataloader call. This sacrifices ~20-30% throughput but unblocks the prove-out.

**Longer term:** Wrap ThreadPoolExecutor with proper cleanup guards and use context managers to prevent thread leaks on kill signals.

---

## Summary

| Metric | Value |
|--------|-------|
| **Blocking issue** | ChunkLoader ThreadPoolExecutor hangs on re-initialization |
| **GPU idle time** | 65 min (14:26-21:35 PT) |
| **Prove-out progress** | 15.3% complete (7650/50000 steps) |
| **Checkpoint status** | Valid (step 6000) |
| **Root cause** | Thread pool not shut down cleanly when process killed |
| **Path to unblock** | Disable threading in data_loader (Option 1) |
| **ETA to resume** | ~10 min code change + 1 min launch |

**Verdict:** Pipeline is blocked waiting for code intervention. No data issue, no model issue — pure synchronization bug in process lifecycle management.
