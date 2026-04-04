# data-processing — Detail Reference

## Goal

All data preparation pipelines for ML training and backtesting must use:
- **Vectorized whole-record processing** (no Python loops over individual samples)
- **Parallel I/O** (prefetch next batch while processing current)
- **Background writes** (compress and write chunks concurrently with processing)
- **Fast compression** (zstandard/zstd, not gzip)
- **Runtime normalization** (never bake norm stats into stored files)
- **Date/symbol metadata preserved** in chunks (so all components share one data source)

---

## Core Patterns

### 1. Vectorized Whole-Record Processing

```python
# ❌ BAD: Python loop over individual samples / dates
for date in np.unique(dates):
    mask = dates == date
    X_day = flatten(X_mmap[mask])  # tiny numpy call per date

# ✅ GOOD: load whole record, vectorize, sort once
X_flat = flatten(np.array(X_mmap, dtype=np.float32))   # ONE call
sort_idx = np.argsort(dates, kind='stable')
X_sorted = X_flat[sort_idx]

# ✅ GOOD: vectorized ID lookup (no Python loop)
unique_syms, sym_inv = np.unique(sym_names, return_inverse=True)
sym_id_lut = np.array([sym_to_id[s] for s in unique_syms], dtype=np.int32)
symbol_ids = sym_id_lut[sym_inv]   # vectorized broadcast

# ✅ GOOD: date block boundaries from sorted array (no loop)
_, first_idxs = np.unique(dates_sorted, return_index=True)
end_idxs = np.append(first_idxs[1:], len(dates_sorted))
```

### 2. Parallel I/O with Prefetch

```python
from collections import deque
from concurrent.futures import ThreadPoolExecutor

LOAD_WORKERS = 2

def _process_record(record_id, context):
    """Pure function — no shared state, safe for threads."""
    ...

with ThreadPoolExecutor(max_workers=LOAD_WORKERS) as pool:
    # Prime queue with first LOAD_WORKERS futures
    future_queue = deque(
        pool.submit(_process_record, records[i], ctx)
        for i in range(min(LOAD_WORKERS, len(records)))
    )

    for i, record_id in enumerate(records):
        # Submit next while processing current
        next_i = i + LOAD_WORKERS
        if next_i < len(records):
            future_queue.append(pool.submit(_process_record, records[next_i], ctx))

        result = future_queue.popleft().result()   # blocks only if not ready
        process(result)
```

### 3. Background Chunk Writes

```python
from concurrent.futures import ThreadPoolExecutor

WRITE_WORKERS = 2

write_pool = ThreadPoolExecutor(max_workers=WRITE_WORKERS)
write_futures = []

def _save_chunk(arrays, path):
    """Write one chunk. Called in background thread."""
    ...

# During processing: submit writes without blocking
write_futures.append(write_pool.submit(_save_chunk, arrays.copy(), path))

# At the end: collect results (raises on any write error)
for f in write_futures:
    f.result()
write_pool.shutdown(wait=True)
```

### 4. Zstandard Compression (not gzip)

```python
import io, zstandard as zstd

ZSTD_LEVEL = 3   # fast compression, good ratio (~3-5x faster than gzip)

def _save_chunk_zstd(arrays, path: Path) -> int:
    buf = io.BytesIO()
    torch.save(arrays, buf)
    path.write_bytes(zstd.ZstdCompressor(level=ZSTD_LEVEL).compress(buf.getvalue()))
    return len(arrays['X'])

def _load_chunk_zstd(path: Path) -> dict:
    raw = zstd.ZstdDecompressor().decompress(path.read_bytes())
    return torch.load(io.BytesIO(raw), weights_only=True)
```

### 5. Runtime Normalization (never baked into chunks)

```python
# ❌ BAD: normalize at write time
X_norm = (X - mean) / std
torch.save({'X': X_norm, ...}, path)  # baked in — must re-chunk if norm changes

# ✅ GOOD: store raw, normalize at read time
torch.save({'X': X_raw, ...}, path)   # raw — chunk once, use forever

# In Dataset.__getitem__ or iter function:
X_norm = torch.clamp((X_raw - mean) / std.clamp(min=1e-8), -5, 5)
```

### 6. Preserve Metadata in Chunks (date_ints + symbol_ids)

```python
# Chunks must store date and symbol metadata so ALL components (train, backtest, viz)
# can read from the same files without falling back to raw source data.
chunk = {
    'X':          X_raw_float32,       # raw features (normalized at runtime)
    'y_return':   y_return_float32,
    'y_big':      y_big_float32,
    'date_ints':  date_ints_int32,     # days since 1970-01-01
    'symbol_ids': symbol_ids_int32,    # int IDs (symbol_map.npz for reverse lookup)
    'n':          len(X_raw),
}
# Companion files:
# symbol_map.npz — {ids: int32[], names: str[]}
# date_index_{split}.npz — {date_ints, chunk_idxs, starts, ends}
# meta.json — {quarter_to_split, quarter_to_chunks, ...}
```

### 7. Parallel Norm Stats (Welford)

```python
def _welford_for_quarter(quarter):
    X_flat = flatten(np.array(np.load(quarter / "X.npy", mmap_mode='r'), dtype=np.float32))
    batch = np.nan_to_num(X_flat.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    return batch.mean(axis=0), batch.var(axis=0), len(batch)

with ThreadPoolExecutor(max_workers=LOAD_WORKERS) as pool:
    stats = list(pool.map(_welford_for_quarter, train_quarters))

# Combine in O(N_quarters) serial pass
count, mean, M2 = 0, np.zeros(D), np.zeros(D)
for bm, bv, B in stats:
    new_count = count + B
    delta = bm - mean
    mean  = (count * mean + B * bm) / new_count
    M2    = M2 + bv * B + delta**2 * count * B / new_count
    count = new_count
```

### 9. Background Decompression Buffer (ChunkLoader)

Training on large chunk sets with a `MapDataset.__getitem__` LRU is bottlenecked by
CPU decompression on the main thread — GPU sits idle at every chunk boundary.
The fix is a `ChunkLoader` with a background thread pool that decompresses upcoming
chunks *while the GPU is training on the current chunk*.

**Why MapDataset fails at scale:**
- LRU cache of 4 chunks with 120 training chunks → 116 cold decompressions per epoch
- Each cold load: read 50-70MB from disk + zstd decompress → 2-5s on main thread
- GPU idles for every cold load; utilization ~3% with 5.8M samples
- `num_workers>0` in DataLoader is incompatible with chunk streaming (duplicate data, large process memory)

**ChunkLoader architecture:**
```python
class ChunkLoader:
    def __init__(
        self,
        split: str,
        prefetch_chunks: int = 20,       # LRU cache holds 20 decompressed chunks in RAM
        preload_threads: int = 4,         # 4 background decompression threads
        preload_ahead_count: int = 15,    # start decompressing 15 chunks ahead
    ): ...

    def preload_ahead(self, order_pos: int, chunk_order=None):
        """Submit background futures for the next preload_ahead_count chunks."""
        for offset in range(self._preload_ahead_count):
            idx = order_pos + offset
            chunk_idx = chunk_order[idx] if chunk_order else idx
            if chunk_idx not in self._chunk_cache and chunk_idx not in self._preload_futures:
                self._preload_futures[chunk_idx] = self._executor.submit(
                    _load_chunk_file, self._chunk_files[chunk_idx]
                )

    def load_chunk(self, chunk_idx: int) -> dict:
        """Cache hit → return. Future ready → .result(). Otherwise sync load."""
        if chunk_idx in self._preload_futures:
            return self._preload_futures.pop(chunk_idx).result()  # near-zero wait
        return _load_chunk_file(self._chunk_files[chunk_idx])

    def iter_chunks(self, shuffle: bool = False):
        """Iterate all chunks; preload_ahead called before every yield."""
        order = list(range(self.n_chunks))
        if shuffle: random.shuffle(order)
        self.preload_ahead(0, order)
        for pos, chunk_idx in enumerate(order):
            self.preload_ahead(pos + 1, order)
            yield chunk_idx, self.load_chunk(chunk_idx)
```

**IterableDataset wrapper (training):**
```python
class ChunkIterableDataset(IterableDataset):
    def __iter__(self):
        loader = ChunkLoader(self._split)  # creates thread pool
        try:
            for _, chunk in loader.iter_chunks(shuffle=self._shuffle_chunks):
                n = chunk['n']
                X_all, mask_all = chunk['X'], chunk['mask']
                for i in range(n):
                    X_sliced = X_all[i, -self._actual_lookback:].float()  # float16→float32
                    mask_sliced = mask_all[i, -self._actual_lookback:]
                    X_norm = _normalize_tensor(X_sliced, self._norm_stats)
                    yield X_norm, mask_sliced, chunk['y_return'][i], chunk['y_big'][i]
        finally:
            loader.shutdown()

# DataLoader: num_workers=0 — ChunkLoader's thread pool handles all background I/O
return DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0, ...)
```

**Result:** GPU decompression overlap → GPU utilization from ~3% to ~70-90%.
Never use `num_workers>0` with IterableDataset chunk streaming — causes data duplication.

**Reference implementations:**
- `firstrate_learning/chunk_dataset_loader.py` — `ChunkLoader`, `ChunkIterableDataset`
- `trade_learning/data_loader.py` — `ChunkLoader` (original pattern)

---

## Architecture Summary

```
Raw source data (cache/samples/)
        │
        ▼
prepare_chunks.py
  ├── Phase 1: Parallel Welford (LOAD_WORKERS threads → per-quarter stats → combine)
  └── Phase 2: Parallel load + bg write
        ├── ThreadPoolExecutor(LOAD_WORKERS) — prefetch quarters
        ├── Main thread — buffer management, date_index tracking
        └── Synchronous zstd chunk writes (bounded — avoids OOM with large chunks)
        ▼
cache/chunks/{split}/chunk_NNNN.pt.zst   ← raw float16, not normalized
cache/chunks/symbol_map.npz
cache/chunks/date_index_{split}.npz
cache/chunks/meta.json  (max_lookback, n_features, splits metadata)
cache/norm_stats.npz
        │
        ├── Training:   ChunkIterableDataset + ChunkLoader (bg decompression, 4 threads, 15-ahead)
        ├── Backtest:   iter_quarter_days → normalize at yield
        └── Visualize:  iter_quarter_days → normalize at yield
```

### 8. Intermediate Step Caching and Resume

**Pattern**: Split long-running data prep into phases. Cache intermediate outputs at each phase boundary. On restart, detect completed phases/steps by checking for output files and skip them.

```python
# status.json tracks what's done
STATUS_PATH = OUTPUT_DIR / "prepare_status.json"

def _load_status() -> dict:
    if STATUS_PATH.exists():
        with open(STATUS_PATH) as f:
            return json.load(f)
    return {'splits_done': [], 'completed': False}

def _save_status(status: dict):
    with open(STATUS_PATH, 'w') as f:
        json.dump(status, f, indent=2)
```

**Split-level resume** — after each split writes all its chunks and date_index:

```python
# In prepare_chunks() main loop:
status = _load_status()
for split, quarters in [('train', ...), ('val', ...), ('test', ...)]:
    if split in status['splits_done']:
        logger.info(f"  [{split}] already done — skipping")
        continue
    splits_meta[split] = _write_split_chunks(split, quarters, sym_to_id, tracker)
    status['splits_done'].append(split)
    _save_status(status)

# Also skip symbol_map and norm_stats if their output files exist:
if not (CHUNKS_DIR / "symbol_map.npz").exists():
    sym_to_id = _build_symbol_map(all_quarters)
    _save_symbol_map(sym_to_id)

if not NORM_STATS_PATH.exists():
    _compute_norm_stats(train_quarters)
```

**Bounded write queue** — with large chunk files (~400MB each after zstd), an unbounded
write queue causes the process to die before writes complete. Fix: write synchronously
in `_flush()` and rely on the prefetch load pool for I/O parallelism:

```python
# ❌ BAD: unbounded async write queue — process dies before all writes complete
write_futures.append(write_pool.submit(_save_chunk_zstd, ...))  # queues up 70+ futures

# ✅ GOOD: synchronous write in flush — prefetch pool keeps load I/O busy in parallel
_save_chunk_zstd(all_X, all_ages, all_mask, all_yr, all_yb, all_di, all_si, chunk_path)
```

**Key rules**:
- Save `status.json` after every completed split (or batch/phase step)
- Check for existing output files before rebuilding symbol_map, norm_stats
- Final chunk dir is only written by the chunk-writing phase (atomic per-chunk)
- Resume by loading status.json at startup; skip completed steps
- Background write pool should be **bounded** (or synchronous) — unbounded queues
  with large files (~400MB) cause OOM or process death before writes complete
- Keep background **load** pool for prefetch (quarters are smaller than chunks)

**trade_learning/prepare_chunks_pt.py reference implementation**:
- `load_status()` / `save_status()` at `output_dir/status.json`
- `status['phase']` (1 or 2), `status['processed_batches']` (list of completed batch IDs)
- `status['phase2_splits_done']` (list of completed splits)
- Phase 1 batch skip: `if batch_id not in processed_set: ...`
- Phase 2 group skip: check `status['phase2_groups_done'][split]`
- Shared lookup files: `if (lookup_dir / 'symbol_map.npz').exists(): load and skip`

---

## File Extension Convention

| Format | Extension | Use |
|--------|-----------|-----|
| zstandard compressed torch | `.pt.zst` | All new chunk files |
| gzip compressed torch | `.pt.gz` | Legacy only — load supported, do not write |
