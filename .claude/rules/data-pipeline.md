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

## Pre-run source-data presence audit

Before tconv phase-1 promotes any data-pipeline task to READY, tconv MUST perform a literal-input-path presence audit:

1. Grep the script's entry points for every literal file path opened (`np.load(...)`, `open(...)`, `Path(...)` literals, and any config constants dereferenced at I/O time — e.g., `PRICE_DATA_PATH`, `SPLIT_INDEX_PATH`).
2. For every resolved literal input path, run `ls -la <path>` and verify it exists on disk.
3. If any required input path is missing: classify `BLOCKED-HARD` with diagnosis `missing-source-data`. Record missing paths in `memory_dev.md`. Do NOT promote downstream tasks.

Proven: vb6_portfolio_aux/prepare_tokens.py landed READY with two absent input paths; ~30–60 min of implementation time wasted before the environment block was discovered (Cycle 352-b → 354).

## Manifest / index-scanner reuse discipline (P-364.1)

Any script scanning a chunk cache for `manifest.json`, `index.json`, or cross-chunk summaries MUST reuse per-chunk metadata from the chunk-producer's `status.json` (fields: `file`, `n_rows`, `symbol_idx_min/max`, `date_int_min/max`, `bytes_compressed`, `sha256`). Full tensor decompression in a serial loop is BANNED for manifest-only workflows. Every chunk-producer SHALL emit per-chunk metadata into `status.json` as chunks are flushed.

Proven: serial `torch.load` over 627 chunks took 14+ min; status.json fast-path took 0.8s (1050× speedup, Cycle 366).

## Default-serial iteration for large-chunk decompression loops (P-366.1)

Scripts iterating >100 large compressed chunks (≥100 MB decompressed) MUST default to SERIAL iteration. `ThreadPoolExecutor` / `ProcessPoolExecutor` around a decompression loop are BANNED unless measured profiling shows I/O wait > 50% of wall-clock AND per-worker peak RSS < 2× single-process RSS. Rationale: worker exceptions propagate silently through `executor.map`, eagerly queued futures double/triple peak RSS, and CPU accounting is opaque to teta. Use serial loop + explicit `del` + `gc.collect()` every N chunks with per-iteration `try/except` + re-raise. tdeep Mode A MUST treat "pool-in-bulk-iterator over large chunks" as STRUCTURAL_WARN pending measured evidence.

Proven: ThreadPoolExecutor over 264 chunks crashed silently in 30s; serial rewrite completed same scan in 105 min stably (Cycle 367).

## Default parallelism tiers for zstd I/O (P-373.2)

- **Tier 1 — always apply:** every `zstd.ZstdCompressor(...)` and `zstd.ZstdDecompressor(...)` call MUST pass `threads=4`. Parallelizes internally within a single Python call; no pool overhead. 2-4× single-threaded throughput. tdeep Mode A MUST flag missing `threads=` as STRUCTURAL_WARN in any `*/prepare_*.py`, `*/process_*.py`, `*/emit_*.py`, `*/build_*.py`, `*/verify_*.py`.
- **Tier 2 — chunk-scan consumers >100 chunks:** use `ChunkPrefetcher` — a `queue.Queue(maxsize=2)` with one background thread decompressing and pushing `(path, data)` tuples. Main thread consumes via `queue.get(timeout=N)`. Background exceptions MUST push a sentinel that main thread re-raises. RSS bounded by `maxsize=2` × per-chunk RSS. Reuse via `firstrate_learning/.../chunk_prefetch.py`.
- **Tier 3 — BANNED:** multi-process/thread pool around decompression stays banned per P-366.1 unless measured-evidence gate passes.

## Parity-gate rules (P-367.1, P-361.2, P-367.2)

- **Per-field breakdown required (P-367.1):** parity-gate reports MUST break down mismatches per field (`per_field_mismatches: {tokens: int, y_return: int, ...}`). Aggregate-only counts block root-cause attribution.
- **≤1 ULP threshold (P-361.2):** float-field parity gates MUST assert `max_ulp_diff ≤ 1` over the FULL split. `abs_diff < 1e-6` is NOT equivalent for values > 1. Gate verdict MUST be machine-readable with non-zero exit on FAIL.
- **Unit parity FAIL is a BLOCKER (P-367.2):** before any full-scale cache rebuild, a unit-scale parity gate MUST run against ≥1 chunk per split. Any per-field FAIL is a BLOCKER — not "informational only." Exceptions require named authorization in the design entry.

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
