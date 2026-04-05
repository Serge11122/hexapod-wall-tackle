# PROJECT MUST: Cache Invalidation Must Hash All Inputs That Affect Output

**Status**: ACTIVE CONVICTION
**Priority**: HIGH — stale cache silently produces wrong results

## Conviction

Any cached intermediate result MUST be invalidated when ANY input that affects its output changes. The cache key MUST include ALL of:

1. **Input data** — the source data that feeds the computation
2. **Processing code** — any function that transforms input into cached output. Hash the source code of these functions.
3. **Config values** — any configuration that affects data selection or processing (parameters, bounds, tolerances)
4. **Schema version** — format version of input data. If input format changes, cache must invalidate.

## The Distinction: What Invalidates Cache vs What Doesn't

### MUST invalidate cache (changes affect cached output):
- Input data (geometry, parameters, initial conditions)
- Processing/solver code (optimizer settings, loss function)
- Configuration values (bounds, tolerances, step counts)
- Input data format changes

### MUST NOT invalidate cache (changes don't affect cached output):
- Visualization code — downstream of cache
- Output formatting — downstream
- Logging changes — downstream
- Analysis/reporting code — downstream

## Implementation Pattern

```python
def _cache_hash():
    """Hash ALL inputs that affect computation output."""
    h = hashlib.md5()

    # 1. Input data
    h.update(str(input_parameters).encode())

    # 2. Processing code — hash source of functions that produce cached data
    import inspect
    for func in [solve_phase, compute_loss, apply_constraints]:
        h.update(inspect.getsource(func).encode())

    # 3. Config values that affect computation
    h.update(str(bounds).encode())
    h.update(str(tolerance).encode())

    return h.hexdigest()[:16]
```

## Anti-Patterns

1. **Input-only hash** — hashing only input data while ignoring processing code. If solver logic changes but inputs don't, cache returns stale results.
2. **Hash everything** — hashing ALL source files including visualization code. Causes unnecessary cache invalidation.
3. **No hash at all** — loading cache without any validation. Silent corruption.
4. **Timestamp-based invalidation** — using file mtimes instead of content hashes. Fragile.

## Sectioned Storage

Caches SHOULD be stored as individual sections (per-phase, per-segment), NOT as one monolithic file. This enables:
- Loading only the sections you need (memory efficient)
- Saving each section independently (resumable)
- Reuse across computation levels without loading everything
- Parallel loading of sections

### Directory-based cache structure (correct):
```
cache/
├── manifest.json           # {hash, completed_sections, timestamp}
├── phase_01.json           # one file per computation phase
├── phase_02.json
└── phase_03.json
```

## Violations

1. **Input-only cache hash** — Cache hash that doesn't include source code of processing functions
2. **Missing config in hash** — Cache hash that doesn't include configuration values affecting computation
3. **Downstream code in hash** — Cache hash that includes visualization or reporting code, causing unnecessary invalidation
4. **No hash validation on load** — Loading cached data without comparing stored hash vs current hash
5. **Stale cache silent use** — Cache file exists with wrong hash and is silently loaded instead of recomputed
6. **Monolithic cache file** — All cached data in a single file that must be loaded entirely to use or extend
7. **Full reload to extend** — Loading entire cache into RAM to add new data. With sectioned storage, extending means writing new section files only.
