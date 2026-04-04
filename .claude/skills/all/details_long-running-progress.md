# long-running-progress — Detail Reference

## Goal

Every long-running Python script must use `ProgressTracker` from `progress.progress`
to write a live `_progress.md` file next to the script, showing a progress bar,
step counter, ETA, and timestamped log.

## Pattern

```python
from pathlib import Path
from progress.progress import ProgressTracker

tracker = ProgressTracker(
    script_path  = Path(__file__),
    title        = "Script Title",
    total_steps  = N,          # number of major phases/steps
)

tracker.start("Initializing...")

tracker.step(1, "Phase one label", detail="sub-detail optional")
# ... work ...
tracker.detail("Updated sub-detail as work progresses")
tracker.log("Any freeform timestamped note")

tracker.step(2, "Phase two label")
# ...

tracker.done("All work complete.")   # or tracker.error("message") on failure
```

## Output File Naming

| Script | Progress file |
|--------|--------------|
| `firstrate_learning/prepare_chunks.py` | `firstrate_learning/prepare_chunks_progress.md` |
| `firstrate_learning/train.py` | `firstrate_learning/train_progress.md` |
| `firstrate_portfolio/train.py` | `firstrate_portfolio/train_progress.md` |
| `firstrate_learning/backtest_live.py` | `firstrate_learning/backtest_live_progress.md` |

Rule: **same directory, same base name, `_progress.md` suffix.**

## Progress file content

```markdown
# Script Title

**Status:** 🔄 RUNNING
**Elapsed:** 1:23
**ETA:** 2:47

## Progress

```
[████████████░░░░░░░░░░░░░░░░░░] 40%  —  Step 2/5
```

**Phase two label**
*sub-detail optional*

## Log

- 14:30:00 — Starting...
- 14:30:05 — Step 1/5: Phase one label
- 14:31:23 — Step 2/5: Phase two label

*Updated: 14:31:45*
```

## ❌ BAD
```python
# Wrong: no progress tracking
for quarter in quarters:
    process(quarter)

# Wrong: only printing to stdout (lost if log not checked)
print(f"Processing {quarter}...")
```

## ✅ GOOD
```python
from progress.progress import ProgressTracker
tracker = ProgressTracker(Path(__file__), "Prepare Chunks", total_steps=4)
tracker.start()
tracker.step(1, "Building symbol map")
for i, quarter in enumerate(quarters):
    tracker.detail(f"Quarter {i+1}/{len(quarters)}: {quarter}")
tracker.step(2, "Computing norm stats")
tracker.done("Complete.")
```

## Checking Progress

```bash
cat firstrate_learning/prepare_chunks_progress.md
cat firstrate_learning/train_progress.md
```
