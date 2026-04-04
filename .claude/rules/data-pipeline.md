---
paths:
  - "**/prepare_*.py"
  - "**/process_*.py"
  - "**/prepare_*.log"
  - "**/process_*.log"
---

# Data Pipeline Rules

When creating or modifying data preparation/processing scripts, enforce ALL of the following. A script missing any of these is incomplete.

## Required Architecture

1. **Vectorized operations** — Never `for` loop over rows/samples/dates. Use numpy broadcasting, fancy indexing, `np.lexsort`, `np.unique(return_inverse=True)` for ID lookups.

2. **Parallelization** — CPU-bound: `ProcessPoolExecutor` or `mp.Pool(imap_unordered)`. I/O-bound: `ThreadPoolExecutor` with prefetch queue. Dynamic chunk sizing: `max(50, num_files // (num_workers * 4))`. CLI `--workers` flag.

3. **Compression** — Zstandard only (`.pt.zst`), `zstd.ZstdCompressor(level=3)`. Never gzip for new files. Serialize via `torch.save()` to `BytesIO` then compress.

4. **Memory efficiency** — `dtype=np.float32` for features, `int16` for ages, `int32` for dates, `bool` for masks. `np.load(mmap_mode='r')` for large arrays. Chunk large outputs: `CHUNK_SIZE = 50_000`. Explicit `del` after large intermediates.

5. **Resumability** — `status.json` with completed phases/splits/batches. `is_quarter_complete()` check before processing. `--reset` flag for forced fresh start. Save status after every completed unit.

6. **Normalization** — Welford streaming algorithm for mean/std (parallel per-quarter, combine serially). Store raw data in chunks. Normalize at runtime in Dataset/iterator only.

7. **Metadata preservation** — Chunks store `date_ints` (int32) + `symbol_ids` (int32). Companion files: `symbol_map.npz`, `date_index_{split}.npz`, `meta.json`.

8. **Progress tracking** — `ProgressTracker` with live `_progress.md`. Periodic logging with rate and ETA every 500 items. System resource reporting (CPU cores, RAM) at startup.

## Write Pattern

- Background writes via ThreadPoolExecutor for small-medium chunks
- Synchronous writes for large chunks (>100MB) to avoid OOM
- Bounded write queue — never unbounded async for large files

## Pre-Run Validation — MANDATORY

No data pipeline script may run at full scale without completing this cycle:

1. **`--smoke-test` flag required** — every script MUST accept `--smoke-test` to run on reduced data (1-2 quarters, ~100 symbols). Must complete in <2 minutes.

2. **Smoke test first** — run with `--smoke-test`, verify output correctness and format.

3. **Performance test** — run on ~5 quarters, measure while running:
   - `ps aux | grep script_name` — CPU% should show multi-core usage
   - Memory RSS must be stable (not growing unbounded)
   - Throughput rate (items/sec) must be consistent

4. **Iterate 2-3 times minimum** — cycle: optimize → smoke test → performance measure → optimize again. Each cycle must show measurable improvement. Do not proceed to full run until:
   - Multiple CPU cores active (verify with `top`/`ps`)
   - Memory stable across smoke test
   - Checkpointing verified (kill process, restart, confirm it resumes)
   - Throughput extrapolates to reasonable full-run time

5. **Only then full run** — after all metrics pass, launch with `nohup`.

**This is not optional.** A script that runs for hours on a single core when 20 cores are available is not ready for a full run.

## Reference Scripts

- `firstrate_learning/prepare_chunks.py` — canonical chunk pipeline
- `firstrate_learning/prepare_data.py` — canonical data preparation
- `trade_learning/prepare_chunks_pt.py` — multi-phase with batch resume
