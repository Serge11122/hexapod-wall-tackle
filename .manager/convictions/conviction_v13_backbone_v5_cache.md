# PROJECT MUST: V13 Portfolio Must Reuse V5 Token Cache — No Redundant Parsing

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — 48 min of CPU parsing is 100% wasted. V5 already cached the identical tokens.

## Conviction

V13 portfolio's backbone precompute MUST load tokenized data from V5's existing cache (`firstrate_learning/v5/cache/tokens/`), NOT re-parse raw CSV files from `.storage-long/`. The V13 backbone IS the V5 backbone — same model.py, same prepare_tokens.py, same config.py. The token cache produced by V5's `prepare_tokens.py` contains the exact same output that V13's `_process_symbol_file()` would produce.

## The Redundancy

V5 `prepare_tokens.py` already:
1. Parsed all raw options CSV files from `.storage-long/`
2. Built 5-day sliding windows `(n_samples, 5, 128, 20)` with types, masks, day_masks
3. Computed forward returns (y_return, y_big)
4. Saved **35 GB** of zstd-compressed chunks in `cache/tokens/{train,val,test}/`
5. 11.4 million samples across 264 chunks, all 64 quarters
6. Fully resumable with `status.json`

V13 portfolio `precompute_backbone_outputs()` currently:
1. Re-parses the same raw CSV files through the same `_process_symbol_file()` (imported from `firstrate_learning.v13.prepare_tokens` — which is identical to v5)
2. Re-builds the same 5-day windows
3. Then runs backbone inference to get 72-dim features
4. Takes ~48 min: ~46 min CPU parse (redundant) + ~2 min GPU inference (the only useful work)

## Correct Implementation

V13 portfolio precompute should:

```python
# CORRECT: Load V5's pre-tokenized chunks, run backbone inference only
from firstrate_learning.v5.data_loader import ChunkLoader  # or direct zstd load

token_cache_dir = Path("firstrate_learning/v5/cache/tokens")
for split in ["train", "val", "test"]:
    chunks = sorted((token_cache_dir / split).glob("chunk_*.pt.zst"))
    for chunk_path in chunks:
        # Load pre-tokenized data (already (N, 5, 128, 20) tensors)
        chunk = load_zstd_chunk(chunk_path)
        tokens = chunk['tokens'].to(device)      # (N, 5, 128, 20)
        types = chunk['types'].to(device)         # (N, 5, 128)
        mask = chunk['mask'].to(device)           # (N, 5, 128)
        day_mask = chunk['day_mask'].to(device)   # (N, 5)

        # Run backbone inference — the ONLY compute needed
        with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.float16):
            out = backbone(tokens, types, mask, day_mask)

        # Extract 72-dim features
        features = torch.cat([out['embedding'], out['score'].unsqueeze(1),
                             out['p_big'].unsqueeze(1), out['p_up'].unsqueeze(1),
                             out['quantiles']], dim=1)  # (N, 72)

        # Save to sectioned backbone cache
        save_section(quarter, features, dates, symbols)
```

**Time estimate**: Loading cached chunks + GPU inference only = ~2-5 min total (vs 48 min currently). The 46 min of CPU parsing is eliminated.

## Shared Resources

- `firstrate_learning/v13/cache` is already a symlink to `../v5/cache`
- `firstrate_learning/v13/model.py` is identical to v5
- `firstrate_learning/v13/prepare_tokens.py` is identical to v5
- V5 backbone weights: `firstrate_learning/v5/models/best_model.pt` (same weights V13 portfolio loads)

## Token Cache Contents (per chunk)

Each `chunk_NNNN.pt.zst` contains:
- `tokens`: `(N, 5, 128, 20)` float32 — 5-day windows of options chain data
- `types`: `(N, 5, 128)` int64 — token type IDs
- `mask`: `(N, 5, 128)` bool — valid token positions
- `day_mask`: `(N, 5)` bool — valid days in window
- `y_return`: `(N,)` float32 — forward returns
- `y_big`: `(N,)` float32 — big move labels
- Plus metadata: dates, symbols per sample

## Violations

1. **Re-parsing raw CSV when token cache exists** — V13 portfolio calling `_process_symbol_file()` to parse raw options files when `firstrate_learning/v5/cache/tokens/` already contains the identical tokenized output. This wastes ~46 min of CPU per full precompute.

2. **Not loading V5 token chunks** — V13 portfolio precompute not reading from `cache/tokens/{train,val,test}/chunk_*.pt.zst`. These chunks are the input to backbone inference — they should be loaded directly.

3. **Duplicating tokenization code path** — V13 portfolio importing `_process_symbol_file` and `_assemble_5day_samples` from backbone's prepare_tokens.py and running them at portfolio training time. Tokenization is a data preparation step that should run ONCE (via `prepare_tokens.py`) and be cached. Portfolio training should only run backbone inference on cached tokens.

4. **ProcessPoolExecutor for tokenization in portfolio train.py** — Having 18 CPU workers parsing raw text files during portfolio training. Portfolio training should be GPU-bound (backbone inference + portfolio model training), not CPU-bound on redundant tokenization.

5. **Ignoring existing cache symlink** — `firstrate_learning/v13/cache -> ../v5/cache` exists but V13 portfolio's `precompute_backbone_outputs()` doesn't check it for pre-tokenized data. It only checks for its own backbone feature cache, missing the upstream token cache entirely.

6. **48 min precompute when 2-5 min is possible** — Any precompute taking >10 min when a valid upstream token cache exists. With V5 tokens cached, backbone precompute should be GPU inference only: load chunks → forward pass → save features. If precompute exceeds 10 min, it's likely re-parsing instead of loading cache.

## Runtime Behavioral Tests

7. **V5 token cache exists** — Verify `firstrate_learning/v5/cache/tokens/{train,val,test}/` directories each contain chunk_*.pt.zst files. Count > 0 for each split.
8. **Token chunks loadable** — Load one chunk from each split, verify it contains keys: tokens, types, mask, day_mask (minimum). torch.load after zstd decompression must succeed.
9. **No CSV parsing in precompute log** — If V13 precompute runs, check log for "Processing symbol" or "_process_symbol_file" lines. If found, it's re-parsing CSV instead of loading cache. Should see "Loading cached tokens" or similar.
