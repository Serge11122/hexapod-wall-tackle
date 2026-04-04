# PROJECT MUST: Disk Space Management — Cleanup Orphaned and Unused Caches

**Status**: ACTIVE CONVICTION
**Priority**: HIGH — disk at 87% (122G free of 937G). Orphaned caches waste space, failed model artifacts accumulate.

## Conviction

Disk space MUST be actively managed. When disk usage exceeds 85%, automated cleanup of orphaned caches, unused caches, and failed model artifacts MUST be triggered. Cleanup is part of the timer cycle — not a manual task. tconv MUST check disk usage and trigger cleanup before it becomes critical.

**NEVER delete anything from `.storage-long/`** — this contains irreplaceable raw source data.

## Anchor: What To Keep vs What To Clean

### NEVER DELETE (protected):
- `.storage-long/` — raw source data (irreplaceable)
- `*_tag_*/` — tagged model versions (immutable anchors)
- `best_model.pt` in active run directories — trained weights
- Active cache directories matching current `_backbone_hash()` — will be reused
- `manifest.json` files — cache metadata
- `.manager/convictions/` — conviction files
- `.manager/goals.md`, `.manager/goal_tracker.md` — project state

### CLEAN WHEN DISK > 85% (in priority order — TAG-SAFE):

**Before deleting anything, check:** does a `*_tag_*` directory reference this data? If yes, NEVER delete. See `conviction_tagged_model_protection.md`.

1. **Failed experiment data** — Run dirs/caches from experiments that failed (killed by teta, smoke FAILED) AND have no tag reference. Delete `latest_checkpoint.pt` and large tensors. Keep `run_meta.json` and `training_results.json` for history.
   ```bash
   # Find failed run dirs with no tag reference
   find <module>/models/ -name "run_*" -type d | while read d; do
       if [ ! -f "$d/gate_smoke.json" ] && [ -f "$d/latest_checkpoint.pt" ]; then
           echo "FAILED_RUN: $d"
       fi
   done
   ```

4. **Duplicate run directories** — Multiple run dirs for the same experiment/gate level. Keep the latest, clean the rest.

5. **Old log files** — Log files >7 days old in `output/` directories. Keep the 3 most recent per module.

6. **Python __pycache__** — Accumulated bytecode caches.
   ```bash
   find . -type d -name "__pycache__" -exec rm -rf {} +
   ```

7. **Old backups** — Files in `backups/` older than 30 days.

## Cleanup Triggers

| Disk Usage | Action |
|---|---|
| < 80% | No action needed |
| 80-85% | tconv notes disk usage in goal_tracker. No automated cleanup. |
| **85-90%** | **tconv MUST trigger cleanup.** Write cleanup tasks to memory_dev.md. tdev executes: orphaned caches → stale caches → failed runs → old logs. |
| > 90% | **CRITICAL.** tconv MUST clean up immediately before any other work. Block all launches until disk < 85%. |

## Cleanup Execution Pattern

tdev cleanup tasks must:
1. List what will be deleted with `du -sh` sizes BEFORE deleting
2. Log deletions to `.manager/timer_cycle_log.md` with timestamp, path, size
3. Verify disk usage dropped after cleanup: `df -h /`
4. Never use `rm -rf` on directories without first checking they don't contain protected files
5. Never delete the only copy of a best_model.pt — check if it's tagged first

## Integration with Hard Cycle

- **timer2** already reports disk % every tick (DISK_WARNING at 80%, DISK_CRITICAL at 90%)
- **tconv** reads disk alerts from system_state. When disk > 85%, tconv adds cleanup to memory_dev.md as PRIORITY 0 (before any training tasks)
- **tdev** executes cleanup: runs the find commands above, deletes orphaned/stale/failed items, logs results
- **tdeep** checks disk before launch. If disk > 90%, blocks launch regardless of other checks.
- **teta** monitors disk during runs. If disk hits 95% during a run, writes kill_violations.md (run may be filling disk with checkpoints)

## Violations

Any of the following is a violation of this conviction:

1. **No cleanup at 85%** — Disk usage exceeds 85% and tconv does not add cleanup tasks to memory_dev.md. Timer2 reports DISK_WARNING but no action is taken for 2+ cycles.

2. **Orphaned caches not cleaned** — Monolithic cache files or stale hash cache directories exist on disk when disk > 85% and current hash doesn't match. These are dead weight — wrong hash means they'll never be loaded.

3. **Failed run checkpoints kept** — Run directories where training was killed or gate failed still contain large checkpoint files (latest_checkpoint.pt, best_model.pt) when disk > 85%. Keep run_meta.json and training_results.json for history. Delete the multi-MB checkpoint tensors.

4. **Deleting .storage-long** — Any deletion of files within `.storage-long/` directory. This is irreplaceable raw source data. NEVER delete, regardless of disk pressure.

5. **Deleting tagged models** — Any deletion of files in `*_tag_*/` directories. These are immutable anchors.

6. **Cleanup without logging** — Deleting files without recording what was deleted, when, and why in timer_cycle_log.md. Cleanup must be auditable.

7. **Launch at >90% disk** — tdeep approving a launch when disk usage exceeds 90%. Must block and clean up first.

8. **No disk check in tdeep** — tdeep not checking `df -h /` as part of pre-launch validation. Disk check is mandatory alongside code analysis.

9. **Run filling disk without monitoring** — teta not checking disk usage during long runs. A prove-out writing large checkpoints every 2000 steps can consume GBs. If disk hits 95% during a run, teta must kill it.

10. **Accumulating __pycache__** — Python bytecode cache directories accumulating across the project when disk > 85%. These are safe to delete and regenerate automatically.

## Runtime Behavioral Tests

Static checks define rules but miss actual disk state. These runtime tests MUST also pass:

11. **Disk usage check** — `df -h /` must show usage < 90% before any launch. If >= 85%, tconv must add cleanup tasks. If >= 90%, block launch.
12. **No orphaned run dirs with large checkpoints** — Count run dirs in `*/models/run_*` that have `latest_checkpoint.pt` but no `gate_smoke.json` (failed runs). If count > 5 AND disk > 85%, cleanup required.
13. **Tagged model weights intact** — For each `*_tag_*` dir, verify `best_model.pt` exists and is non-zero size. If any missing, CRITICAL violation.
14. **.storage-long untouched** — Verify `.storage-long/` directory exists and has not been modified (no deletions) since last check.
