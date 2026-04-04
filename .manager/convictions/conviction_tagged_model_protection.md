# PROJECT MUST: Tagged Model Protection — Never Overwrite Working Code, Weights, or Cache

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — V5 best_model.pt was deleted during experimentation. Tagged model code was modified in-place.

## Conviction

Tagged models (`*_tag_*` directories) and their referenced data (weights, code, cache) are IMMUTABLE. Experiments and new features MUST happen in new version folders, never by modifying tagged code or overwriting tagged data. Cache referenced by tagged models must be preserved. New data fields must be appended as side-caches that join at load time, not by regenerating existing cache.

## Rules

### 1. Tagged Models Are Immutable

- **Code**: Never modify `.py` files in a tagged directory OR in the source directory the tag was copied from if the tag references those files. If `v5_tag/` was copied from `v5/`, then `v5/prepare_tokens.py` must not be modified — changes go in `v5_experimental/` or `v6/`.
- **Weights**: `best_model.pt` in tagged or source directories must never be deleted or overwritten. If `v5_tag/models/best_model.pt` exists, `v5/models/best_model.pt` must also be preserved (it's the same weights, referenced by V13 portfolio).
- **Cache**: Cache files produced by tagged code (e.g., `v5/cache/tokens/`) must not be deleted or overwritten if a tagged model references them. The cache hash validates against the tagged code — overwriting the cache breaks the tag.

### 2. Experiments Go in New Folders

- New features or code changes → create `v5_experimental/` or `v5_wrank/` or `v6/`
- Never modify `v5/` if `v5_tag/` exists
- Copy what you need, modify the copy
- The new folder gets its own `cache/`, `models/`, `output/` directories
- If the experiment succeeds → tag it → it becomes the new immutable anchor

### 3. Cache Append, Not Rebuild

When adding new data fields to an existing cache:

**WRONG — rebuild entire cache (hours of CPU):**
```python
# Modified prepare_tokens.py to add date_int field
# → hash changed → 35 GB cache invalidated → 4-6 hour rebuild
samples.append({...existing..., 'date_int': np.int32(idx)})
```

**CORRECT — side-cache that joins at load time (minutes):**
```python
# Create a small supplementary cache with the new field only
# Side-cache: one file per chunk, same sample count, same order
# e.g., cache/tokens/supplements/date_int/chunk_0000.pt.zst
for chunk_path in existing_chunks:
    chunk = load_chunk(chunk_path)
    date_ints = compute_date_ints(chunk)  # derive from existing data
    save_supplement(supplement_dir / chunk_path.name, {'date_int': date_ints})

# At load time, join main cache + supplement(s):
def load_chunk_with_supplements(chunk_path, supplement_dirs):
    chunk = load_zstd(chunk_path)
    for sup_dir in supplement_dirs:
        sup = load_zstd(sup_dir / chunk_path.name)
        chunk.update(sup)  # merge fields
    return chunk
```

**Benefits:**
- Original cache untouched (immutable, tag-safe)
- Side-cache is small (one int32 column vs full token rebuild)
- Multiple supplements can stack (date_int, regime, sector, etc.)
- If supplement is wrong, delete it without affecting main cache
- Generation time: minutes, not hours

### 4. Cache Cleanup Rules

| Cache Status | Action |
|---|---|
| Referenced by current tag | NEVER delete. Immutable. |
| Referenced by active experiment | Keep until experiment completes |
| From failed experiment, no tag reference | Safe to delete for space |
| Supplement cache | Delete freely — can regenerate in minutes |
| Orphaned (hash mismatch, no tag, no experiment) | Delete when disk > 85% |

### 5. Weight Protection

- `best_model.pt` in any tagged directory → NEVER delete
- `best_model.pt` in source directory (e.g., `v5/models/`) → keep if ANY tag or downstream model references it
- `latest_checkpoint.pt` from failed experiments → delete for space
- `best_model.pt` from failed experiments that produced no tag → delete for space

## Violations

1. **Modifying tagged source code** — Changing any `.py` file in a directory that has a corresponding `*_tag_*` copy. If `v5_tag/` exists, `v5/*.py` files are frozen. Create a new version folder for changes.

2. **Deleting tagged model weights** — Removing `best_model.pt` from a tagged directory or from the source directory referenced by tags/downstream models. V5 `best_model.pt` was deleted during V5 retraining prep — this broke V13 portfolio's backbone loading.

3. **Overwriting tagged cache in-place** — Modifying `prepare_tokens.py` in a tagged source directory, causing cache hash invalidation and full rebuild. The 35 GB V5 token cache was rebuilt from scratch to add one `date_int` column. Should have been a side-cache supplement.

4. **Full cache rebuild for field addition** — Regenerating an entire cache (hours of CPU) to add a new data field when the field could be computed as a side-cache supplement (minutes). If the new field can be derived from existing data or computed independently, it MUST be a supplement, not a rebuild.

5. **No side-cache supplement pattern** — Adding new fields by modifying the main cache generation code instead of creating a `supplements/` directory with per-chunk files in the same shape. Supplements must be joinable at load time.

6. **Experiment in tagged directory** — Running experimental code (new loss functions, architecture changes, hyperparameter sweeps) in a tagged model's directory instead of a new version folder. Experiments contaminate the immutable anchor.

7. **Deleting cache referenced by tag** — Removing cache files that a tagged model's code would load. If `v5_tag/` code references `v5/cache/tokens/`, those token chunks must be preserved as long as the tag exists.

8. **No copy-before-modify** — Modifying source files without first copying the directory to a new version folder. The copy preserves the working state. The modification happens in the copy.

9. **Cleaning working data instead of failed data** — During disk cleanup, deleting cache/weights from working tagged models while keeping cache/weights from failed untagged experiments. Cleanup priority: failed experiments first, orphaned caches second, working data NEVER.

10. **Weight file not restored after deletion** — If a `best_model.pt` referenced by a tag or downstream model is accidentally deleted, it must be restored from the tag copy immediately. The system must detect this (tdeep/teta check) and flag it.

11. **Cache script deleting existing chunks** — Any data processing script that calls `unlink()`, `rmtree()`, or `rm` on cache chunk files. Proven: V5 prepare_tokens deleted 50 completed quarters (hours of work) on mode change smoke→full. Processing scripts must NEVER delete cache. Invalid chunks → archive to `cache/archive/YYYYMMDD_HHMMSS/`, not delete. Disk cleanup is a separate operation.

12. **No cache archive directory** — Cache directories must have an `archive/` subdirectory for invalidated-but-not-deleted chunks. Archive structure: `cache/tokens/archive/YYYYMMDD_HHMMSS/{split}/chunk_*.pt.zst`. Archives are: (a) restorable if invalidation was wrong, (b) cleaned by disk management when disk > 85%, (c) never deleted by processing scripts.

## Runtime Behavioral Tests

Static checks catch code patterns but miss file-level state. These runtime tests MUST also pass:

13. **Tagged model weights exist** — For each *_tag_* directory, verify best_model.pt exists and is non-empty: `ls -la v5_tag/models/best_model.pt`. If missing, CRITICAL violation.
14. **Source directory weights preserved** — If a tag references a source directory (e.g., v5_tag references v5), verify the source also has best_model.pt: `ls -la v5/models/best_model.pt`. If missing, downstream models (V13) will fail.
15. **Cache referenced by tag exists** — If v5_tag code references cache/tokens/, verify the cache directory exists and contains chunk files. Count chunks and verify > 0.
16. **No .py modifications in tagged source since tag creation** — Compare git log timestamps of v5/*.py modifications against v5_tag creation date. Any modification after tagging is a violation (even if intentional, it must be acknowledged).
