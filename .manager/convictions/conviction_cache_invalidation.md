# PROJECT MUST: Cache Invalidation Must Hash All Inputs That Affect Output

**Status**: ACTIVE CONVICTION
**Priority**: HIGH — stale cache silently produces wrong features, wasting hours of training on corrupted data

## Conviction

Any cached intermediate (backbone precompute, feature extraction, tokenization, normalization stats) MUST be invalidated when ANY input that affects its output changes. The cache hash MUST include ALL of:

1. **Model weights** — the frozen model that produces embeddings (currently done)
2. **Processing code** — any function that transforms raw data into cached output (tokenization, assembly, filtering). Hash the source code of these functions.
3. **Config values** — any config that affects data selection or processing (symbol lists, exclusion lists, quarter selection, batch size for tokenization, feature dimensions, lookback window)
4. **Data schema** — format version of raw input data. If raw data format changes, cache must invalidate.

## The Distinction: What Invalidates Cache vs What Doesn't

### MUST invalidate cache (changes affect precompute output):
- Backbone model weights (best_model.pt)
- Tokenization code (_process_symbol_file, token config)
- Data assembly code (_assemble_5day_samples_with_metadata)
- Symbol filtering (exclusion list, allowed_symbols logic)
- Feature extraction (what gets concatenated into backbone_features)
- Raw data format changes
- Lookback window size, forward horizon, big_move_threshold

### MUST NOT invalidate cache (changes don't affect precompute output):
- Portfolio model code (model.py) — downstream of cache
- Training config (EMA alpha, lambda_turnover, learning rate) — downstream
- Loss function changes — downstream
- Optimizer changes — downstream
- Overlay code — downstream
- Evaluation code — downstream

## Implementation Pattern

```python
def _cache_hash():
    """Hash ALL inputs that affect precompute output."""
    h = hashlib.md5()

    # 1. Model weights
    with open(MODEL_PATH, 'rb') as f:
        h.update(f.read(1024 * 1024))  # first 1MB
        f.seek(max(0, f.seek(0, 2) - 1024 * 1024))
        h.update(f.read())  # last 1MB

    # 2. Processing code — hash source of functions that produce cached data
    import inspect
    for func in [_process_symbol_file, _assemble_5day_samples_with_metadata,
                 precompute_backbone_outputs]:
        h.update(inspect.getsource(func).encode())

    # 3. Config values that affect data selection
    h.update(str(EXCLUSION_LIST).encode())
    h.update(str(LOOKBACK_DAYS).encode())
    h.update(str(FORWARD_HORIZON).encode())
    h.update(str(BIG_MOVE_THRESHOLD).encode())

    return h.hexdigest()[:16]
```

## Anti-Patterns

1. **Weights-only hash** — hashing only model weights while ignoring processing code. If tokenization logic changes but weights don't, cache returns stale features.
2. **Hash everything** — hashing ALL source files including downstream code (model.py, train.py). This causes unnecessary cache invalidation when training config changes that don't affect precompute.
3. **No hash at all** — loading cache without any validation. Silent corruption.
4. **Timestamp-based invalidation** — using file mtimes instead of content hashes. Fragile — git checkout changes mtimes without changing content.
5. **Hash the cache file itself** — hashing the output instead of the inputs. Circular — can't detect if the output was produced by wrong inputs.

## Incremental Cache Strategy — Sectioned Storage

Caches MUST be stored as individual sections (per-quarter, per-chunk), NOT as one monolithic file. This enables:
- Loading only the sections you need (memory efficient)
- Saving each section independently (resumable)
- Cross-gate reuse without loading the entire lower-gate cache
- Parallel loading of sections via ThreadPoolExecutor

### Directory-based cache structure (correct):

```
cache/
├── manifest.json              # {hash, completed_quarters, timestamp}
├── backbone_q_2010Q1.pt.zst   # one file per quarter
├── backbone_q_2010Q2.pt.zst
├── backbone_q_2010Q3.pt.zst
├── ...
└── backbone_q_2025Q4.pt.zst
```

```python
# Correct: Sectioned cache — save per quarter, load per quarter
CACHE_DIR = Path("cache/backbone")
CACHE_DIR.mkdir(exist_ok=True)
manifest_path = CACHE_DIR / "manifest.json"

# Load manifest to find completed sections
manifest = json.load(open(manifest_path)) if manifest_path.exists() else {"hash": None, "quarters": []}
if manifest["hash"] != current_hash:
    # Hash changed — invalidate all sections
    shutil.rmtree(CACHE_DIR); CACHE_DIR.mkdir()
    manifest = {"hash": current_hash, "quarters": []}

completed = set(manifest["quarters"])
remaining = [q for q in all_quarters if q not in completed]

for quarter in remaining:
    data = process_quarter(quarter)
    # Save THIS section immediately
    section_path = CACHE_DIR / f"backbone_q_{quarter}.pt.zst"
    save_compressed(data, section_path)
    manifest["quarters"].append(quarter)
    json.dump(manifest, open(manifest_path, "w"))  # update manifest after each save

# Load only the sections needed for training
def load_dates(date_list):
    """Load only the quarters containing the requested dates."""
    needed_quarters = {date_to_quarter(d) for d in date_list}
    results = {}
    for q in needed_quarters:
        section = load_compressed(CACHE_DIR / f"backbone_q_{q}.pt.zst")
        results.update(section)
    return results
```

### Anti-patterns:

```python
# WRONG: Monolithic file — must load entire cache into memory to use or extend
save_cache(entire_dict, "backbone_precompute.pt.zst")  # one giant file
existing = load_cache("backbone_precompute.pt.zst")     # loads everything into RAM

# WRONG: Load-extend-save on monolithic file — still loads everything
existing = load_entire_cache()  # GBs into RAM
existing.update(new_data)
save_entire_cache(existing)     # rewrites GBs every save
```

This pattern ensures:
- **Memory efficiency** — load only needed sections, not entire cache. Prove-out with 4000 dates doesn't require loading all 4000 dates into RAM at once.
- **Resumability** — if process crashes at quarter 50/64, 50 section files exist on disk. Restart reads manifest, skips 50, continues from 51.
- **Gate reuse** — smoke saves 16 section files. Prove-out sees 16 exist, computes remaining 48. No data reloaded or recomputed.
- **Parallel I/O** — sections can be loaded in parallel via ThreadPoolExecutor since they're independent files.
- **Periodic saves** — each section saved immediately after compute. No batching needed — every quarter's work is persisted instantly.

## Violations

1. **Weights-only cache hash** — Any cache hash function that hashes only model weights without including source code of processing functions. V13 `_backbone_hash()` was fixed (2026-04-02) to include `inspect.getsource()` of processing functions, config values, and symbol exclusion list. Any regression to weights-only hashing is a violation.

2. **Missing code hash** — Cache hash that doesn't include `inspect.getsource()` of ALL functions in the precompute pipeline (tokenization → assembly → backbone inference → feature extraction).

3. **Missing config hash** — Cache hash that doesn't include config values that affect data selection: symbol exclusions, lookback window, forward horizon, big_move_threshold, smoke_test limits.

4. **Downstream code in hash** — Cache hash that includes source code from model.py, train.py training loop, loss functions, or evaluation code. These are downstream of the cache and should NOT invalidate it. Including them causes unnecessary recomputation.

5. **No hash validation on load** — Loading cached data without comparing stored hash vs current hash. Cache must store the hash it was created with, and load must verify before using.

6. **Stale cache silent use** — Any code path where a cache file exists with wrong hash and is silently loaded instead of recomputed. Must either recompute or fail loudly.

7. **Gate-specific hash divergence** — Unit, smoke, and prove-out caches for the same backbone hash should use the same processing code hash. If processing code changes, ALL gate-level caches must be invalidated, not just the one being run.

8. **No incremental cache build** — Cache function that processes all data then saves once at the end, instead of saving each section independently as it's computed. Must use sectioned storage (one file per quarter/chunk) with a manifest tracking completed sections.

9. **Monolithic cache file** — Storing all cached data in a single file that must be loaded entirely into memory to use or extend. Must use directory-based sectioned storage (one compressed file per quarter/chunk + manifest.json). Loading must be selective — load only the sections needed, not everything.

10. **Full cache reload to extend** — Loading an entire cache file into RAM in order to add new data and re-save. With sectioned storage, extending means writing new section files and updating the manifest — no existing sections need to be loaded or rewritten.

11. **Deleting invalidated cache instead of archiving** — When cache hash changes and existing sections are invalidated, they must be MOVED to `cache/archive/YYYYMMDD_HHMMSS/`, not deleted. Archived caches can be restored if the code change is reverted, and are cleaned only by disk management (not by processing scripts). The cost of regenerating 50 quarters of tokens (hours) far exceeds the cost of storing the archive (GBs of disk).

12. **Mode-change cache destruction** — Processing scripts that delete all cache chunks when switching between modes (unit/smoke/full). Proven: V5 prepare_tokens deleted 50 full-mode quarters on smoke→full transition, destroying hours of CPU work. Mode transitions must: (a) keep chunks generated in full mode regardless of current mode, (b) archive (not delete) chunks from lower modes that are invalid for the new mode, (c) recompute only missing quarters.

## Runtime Behavioral Tests

Static grep catches code patterns but misses broken state. These runtime tests MUST also pass:

13. **Cache manifest exists and loads** — Before any training launch, verify manifest.json exists in the active cache directory, loads as valid JSON, and contains a non-empty "hash" field matching the current code hash.
14. **Cache sections match manifest** — Count .pt.zst files in cache directory. Count must match len(manifest["quarters"]). Any mismatch = corrupt state.
15. **Cache hash matches current code** — Compute current _backbone_hash() or _cache_hash() and compare to manifest["hash"]. If different, cache is stale and must be recomputed before training.
16. **No archive directory growing unbounded** — If cache/archive/ exists, check total size. If > 10 GB and disk > 85%, flag for cleanup.
