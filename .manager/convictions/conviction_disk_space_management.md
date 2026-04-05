# PROJECT MUST: Disk Space Management

**Status**: ACTIVE CONVICTION
**Priority**: HIGH — generated outputs and cached results accumulate without active management

## Conviction

Disk space MUST be actively managed. When disk usage exceeds 85%, cleanup of orphaned outputs, stale results, and failed experiment artifacts MUST be triggered. Cleanup is part of regular maintenance, not a manual afterthought.

## Anchor: What To Keep vs What To Clean

### NEVER DELETE (protected):
- Source code (`.py` files, version-controlled)
- Versioned reference solutions (tagged/proven outputs that took significant compute)
- Active output directories with valid results
- `.manager/convictions/` — conviction files
- `.manager/goals.md` — project goals

### CLEAN WHEN DISK > 85% (in priority order):

**Before deleting anything, check:** does a versioned/tagged reference depend on this data? If yes, NEVER delete.

1. **Failed experiment data** — Output from runs that failed (diverged, crashed, produced invalid results). Keep metadata (logs, config) for history. Delete large generated files.
2. **Duplicate output directories** — Multiple outputs for the same experiment. Keep the latest, clean the rest.
3. **Old log files** — Log files >7 days old. Keep the 3 most recent.
4. **Python __pycache__** — Accumulated bytecode caches.
5. **Old backups** — Files in `backups/` older than 30 days.

## Cleanup Triggers

| Disk Usage | Action |
|---|---|
| < 80% | No action needed |
| 80-85% | Note disk usage. No automated cleanup. |
| **85-90%** | **Trigger cleanup.** Orphaned outputs → stale results → failed runs → old logs. |
| > 90% | **CRITICAL.** Clean up immediately before any other work. |

## Cleanup Execution Pattern

1. List what will be deleted with `du -sh` sizes BEFORE deleting
2. Log deletions with timestamp, path, size
3. Verify disk usage dropped after cleanup: `df -h /`
4. Never use `rm -rf` on directories without first checking they don't contain protected files
5. Never delete the only copy of a proven/working result

## Violations

1. **No cleanup at 85%** — Disk usage exceeds 85% and no cleanup action is taken
2. **Failed outputs not cleaned** — Output directories where computation failed still contain large files when disk > 85%
3. **Deleting versioned references** — Any deletion of files in tagged/versioned directories. These are immutable anchors.
4. **Cleanup without logging** — Deleting files without recording what was deleted, when, and why
5. **Accumulating __pycache__** — Python bytecode caches accumulating when disk > 85%
