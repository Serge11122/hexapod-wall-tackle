---
name: all
description: Combined skill set: coding agent safety rules, explicit error handling, and Python package setup. Always active during code actions.
user-invocable: false
---

# All Skills

This file is the canonical skill reference for this project. Three skills are always active:

---

## 1. coding-agent-actions

Safe code action guidelines: never auto-create docs, always use `.venv`, backup before overwrite, timestamp outputs, double-confirm commits and destructive ops, never skip safety flags.

**Key rules:**
- Never create `.md` files unless explicitly requested
- Run Python via `firstrate_learning/.venv/bin/python` (not `python3`)
- Backup important files to `backups/` before overwriting (models, configs, data)
- All generated output files: `filename_YYYYMMDD_HHMMSS.ext`
- Git commits: show diff → ask → ask again → commit
- Destructive ops (rm, reset --hard): explain → ask → ask again → proceed

See: [details_coding-agent-actions.md](details_coding-agent-actions.md)

---

## 2. fail-fast-loud

Explicit error handling. No silent failures, no fallback defaults, no bare try-except.

**Key rules:**
- Raise errors explicitly — never catch and continue silently
- Assert all function parameters at entry (type + range)
- No optional parameters with silent defaults
- No `or default_value` fallback patterns
- Validate at the source, not downstream

See: [details_fail-fast-loud.md](details_fail-fast-loud.md)

---

## 3. python-imports

Proper Python package setup. Use `pip install -e .` with `setup.py`. No `sys.path` hacks.

**Key rules:**
- Project root must have `setup.py` with auto-detected packages
- Every importable directory needs `__init__.py`
- Install editable: `firstrate_learning/.venv/bin/pip install -e .`
- Import as `from firstrate_portfolio.trade_execution import ...` (not `sys.path.insert`)
- Remove all `sys.path.insert(0, ...)` and `sys.path.append(...)` from source files

See: [details_python-imports.md](details_python-imports.md)

---

## 4. long-running-scripts

Run long-running Python scripts with `nohup` and `-u` (unbuffered output), piped to a `.log` file in the same directory and with the same base name as the script. No timestamps or suffixes on the log filename.

**Key rules:**
- Always use `nohup` for scripts that take more than a few seconds
- Always use `python -u` for unbuffered output (so logs stream in real time)
- Log file: same directory and base name as the script, `.log` extension
- Pattern: `nohup firstrate_learning/.venv/bin/python -u path/to/script.py > path/to/script.log 2>&1 &`

**Example:**
```bash
# Script: firstrate_portfolio/train.py → log: firstrate_portfolio/train.log
nohup firstrate_learning/.venv/bin/python -u -m firstrate_portfolio.train > firstrate_portfolio/train.log 2>&1 &

# Script: firstrate_learning/train.py → log: firstrate_learning/train.log
nohup firstrate_learning/.venv/bin/python -u -m firstrate_learning.train > firstrate_learning/train.log 2>&1 &
```

See: [details_long-running-scripts.md](details_long-running-scripts.md)

---

## 5. long-running-progress

Every long-running script must use `ProgressTracker` from `progress.progress` to write
a live `_progress.md` file (same directory, same base name as the script) showing a
progress bar, step counter, ETA, and timestamped log.

**Key rules:**
- Import: `from progress.progress import ProgressTracker`
- Construct with `Path(__file__)`, a title string, and `total_steps` count
- Call `tracker.start()` at the top, `tracker.step(n, label)` at each phase, `tracker.done()` at the end
- Call `tracker.detail(text)` for sub-step granularity, `tracker.log(text)` for freeform notes
- Call `tracker.error(message)` in exception handlers
- Output file: `{script_dir}/{script_stem}_progress.md` — overwritten on every update

**Example:**
```python
from pathlib import Path
from progress.progress import ProgressTracker
tracker = ProgressTracker(Path(__file__), "Prepare Chunks", total_steps=4)
tracker.start("Initializing...")
tracker.step(1, "Building symbol map")
for i, q in enumerate(quarters):
    tracker.detail(f"{i+1}/{len(quarters)}: {q}")
tracker.step(2, "Computing norm stats")
tracker.done("All chunks written.")
```

See: [details_long-running-progress.md](details_long-running-progress.md)

---

## 6. data-processing

Efficient ML data pipelines must use vectorized whole-record ops, parallel I/O with
prefetch, background chunk writes, zstd compression, runtime normalization, and
date/symbol metadata preserved in chunks so all components (train, backtest, viz)
share one data source. Training uses `ChunkLoader` with background decompression
so the GPU never idles waiting for chunk I/O.

**Key rules:**
- Never loop over individual samples/dates — vectorize at record/quarter level
- Use `ThreadPoolExecutor` to prefetch next record while processing current
- Submit chunk writes to a background write pool; collect futures at end
- Use `zstandard` (`.pt.zst`), not `gzip` — 3–5x faster at same ratio
- Never bake normalization into chunks — apply at runtime in Dataset/iterator
- Chunks must store `date_ints` + `symbol_ids` so backtest/viz can use same files
- Parallel Welford: compute per-quarter stats concurrently, combine serially
- **Training loader**: use `ChunkLoader` + `IterableDataset` with `preload_ahead_count=15`,
  `prefetch_chunks=20`, `preload_threads=4` — eliminates GPU idle at chunk boundaries
- **Never use `MapDataset.__getitem__`** for large chunk streaming — decompresses on
  main thread, blocks GPU; LRU cache of 4 is insufficient for 100+ chunk training sets

See: [details_data-processing.md](details_data-processing.md)
