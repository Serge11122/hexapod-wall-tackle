# V5 Backbone Retraining Design Document

**Author**: Dev sub-agent (Cycle 225)
**Date**: 2026-04-03
**Status**: RESEARCH COMPLETE — awaiting review before implementation

---

## 1. Current V5 Architecture Summary

### Model: TemporalSurfaceTransformer (679,498 params)

| Component | Params | Description |
|---|---|---|
| IntraDayEncoder | 400,641 | Shared transformer: processes one day's options surface (up to 128 tokens x 20 features) into 128-dim [CLS] embedding. 2 transformer blocks, 4 heads, d_model=128 |
| TemporalEncoder | 232,320 | Cross-day attention over 5 daily embeddings with temporal diffs. 1 transformer block, 4 heads, d_model=128 |
| BackboneProjection | 25,152 | 128-dim -> 64-dim backbone embedding via Linear-LN-GELU-Dropout-Linear-LN |
| magnitude_head | 4,225 | Linear(64,64)-GELU-Linear(64,1) -> p_big (|return| > 5%) |
| direction_head | 4,225 | Linear(64,64)-GELU-Linear(64,1) -> p_up (return > 0) |
| quantile_head | 4,485 | Linear(64,64)-GELU-Linear(64,5) -> [q50, q75, q90, q95, q99] |
| return_head | 4,225 | Linear(64,64)-GELU-Linear(64,1) -> predicted return |
| confidence_head | 4,225 | Linear(64,64)-GELU-Linear(64,1) -> p_confidence |

### 72-dim Output (consumed by V13 portfolio)

```
[0:64]   = backbone embedding z (64-dim from BackboneProjection)
[64]     = composite score = p_big * p_up * p_confidence + quantile bonuses
[65]     = p_big
[66]     = p_up
[67:72]  = quantile predictions [q50, q75, q90, q95, q99]
```

### Current Loss Function: V5Loss (7 components)

| # | Component | Weight | Description |
|---|---|---|---|
| 1 | Focal magnitude | 1.0 | Focal BCE on big move detection (|ret| > 5%) with label smoothing |
| 2 | Direction | 0.5 | BCE on return direction (ret > 0) |
| 3 | Asymmetric quantile | 0.4 | Pinball loss on 5 quantile predictions, weighted [0.5, 1.0, 1.5, 2.5, 4.0] |
| 4 | Asymmetric return | 0.2 | Huber loss on return prediction, 3x weight on big moves |
| 5 | Confidence calibration | 0.2 | BCE on whether magnitude prediction was correct |
| 6 | Contrastive | 0.0 | **DISABLED** — pulls same-bucket embeddings together, pushes different apart |
| 7 | Embedding variance | 0.1 | Penalizes low embedding variance (prevents collapse) |

**Key observation**: All losses are PER-STOCK losses. No loss component compares different stocks from the same date. The backbone was trained to predict absolute properties of individual stocks, NOT relative ranking across stocks on the same day.

### Training Data

- **Total**: 11.4M samples (5.8M train, 2.8M val, 2.8M test)
- **Chunks**: 264 total (138 train, 63 val, 63 test), ~50K samples each, ~125MB compressed per chunk
- **Format**: per-stock samples: (5, 128, 20) tokens + types + mask + day_mask + y_return + y_big
- **Organization**: Chunks are **per-stock** — each sample is one stock-date. Chunks do NOT group by date. Multiple stocks from the same date are scattered across different chunks.
- **Date information**: NOT stored in V5 training chunks. Only y_return and y_big labels are preserved. The prepare_tokens script assembles samples per-symbol, per-date, then shuffles into 50K chunks. Date identity is lost.

### Training Infrastructure

- Step-based training loop with AdamW (LR=3e-4, cosine decay to 10%)
- AMP FP16 + GradScaler
- torch.compile enabled
- ChunkInterleavedDataset: pools 3 chunks (~150K samples), shuffles globally, yields pre-batched (512)
- Best captured return ~0.08 on validation

---

## 2. The Problem

V5 backbone was trained exclusively for per-stock prediction tasks:
- Is this stock going to have a big move? (magnitude)
- Is this stock going up? (direction)
- What are the quantile returns? (distribution)
- What is the expected return? (regression)

None of these losses encode **cross-sectional ranking**: given 1000 stocks on the same date, which ones will outperform the others? The portfolio task is fundamentally a ranking task. 36 experiments proved that no portfolio model can extract ranking signal above Val 0.572 from the current backbone features.

### Why Per-Stock Loss Fails for Ranking

Consider: stock A has p_up=0.7 and stock B has p_up=0.65. Both are correctly classified as "likely up." But the portfolio needs to know that A > B. The per-stock loss treats A and B independently — it never sees them together, never compares them, and has no gradient signal to make the embedding distinguish A's 5% return from B's 2% return when both are "up."

---

## 3. Data Pipeline Compatibility Assessment (TASK 3)

### Critical Finding: V5 chunks DO NOT preserve date information

The V5 training pipeline:
1. Parses raw options CSV per-symbol
2. Assembles 5-day sliding windows per-symbol
3. Shuffles ALL samples across ALL symbols and dates
4. Saves 50K-sample chunks without date identifiers

**This means the current V5 DataLoader CANNOT provide same-date batches.** Any cross-sectional ranking loss requires seeing multiple stocks from the same date in a single batch.

### However: V13 finetune token cache HAS date+symbol metadata

The V13 training pipeline already solves this: `_save_finetune_token_quarter()` stores `dates` and `symbols` per sample. The `precompute_backbone_outputs()` function groups by date, producing `date_data[date_str] = {symbols, backbone_features (N, 72), y_return (N,)}`.

### What Needs to Change

**Option A: Modify V5 chunks to include date_int per sample (Minimal change)**
- Add `date_int` (int32) array to each chunk: (50K,) mapping sample -> date
- Modify V5InterleavedDataset to group by date within buffer
- New `DateGroupedDataset` yields batches of (all stocks from one date)

**Option B: Use V13-style per-quarter date-grouped format (Heavier change)**
- Store data as {date -> list[stock_samples]} like V13 backbone cache
- Load per-quarter, iterate by date
- More natural for ranking loss but requires new data prep pipeline

**Option C: Post-hoc date grouping during training (No data format change)**
- Load standard chunks, but maintain a date -> sample index mapping in memory
- At batch construction time, select a random date, gather all its samples
- Requires keeping entire dataset metadata in RAM

**Recommendation: Option A** — minimal change to existing pipeline. Add `date_int` field to chunks (trivial — 200KB per chunk, <1% overhead). Build a `DateGroupedSampler` that yields batches grouped by date.

---

## 4. Retraining Approach Design (TASK 2)

### Chosen Approach: Multi-Task with Cross-Sectional Ranking Loss

**Why multi-task (not replacing existing losses)**:
- V5's per-stock losses produce useful features (p_up predicts direction at 50.5% accuracy, captured return of 0.08). We do NOT want to lose this.
- Adding a ranking loss ON TOP of existing losses gives the backbone a new gradient signal: "make the embedding distinguish better-performing stocks from worse-performing ones within the same date."
- The existing contrastive loss (w_contrast=0.0) is a partial template — it already compares stocks by return bucket. But it only has 3 buckets (big_up > 10%, big_down < -10%, small < 2%), which is too coarse for ranking.

### Loss Design: ListNet Ranking Loss

Among ranking losses, ListNet (Cao et al. 2007) is the best fit because:
- **ListMLE** was proven to work in V13 experiments (identical convergence to pairwise margin but with continuous gradients)
- **Pairwise margin** is BANNED (saturates at margin=0.1)
- **ListNet** uses softmax over predicted scores vs softmax over actual returns — differentiable, no margin parameter, natural for variable-size groups

```python
def listnet_ranking_loss(pred_scores, actual_returns):
    """ListNet: KL-divergence between predicted and actual ranking distributions.

    Args:
        pred_scores: (N,) predicted ranking scores for N stocks on same date
        actual_returns: (N,) actual forward returns

    Returns:
        scalar loss
    """
    # Softmax over actual returns = "true" ranking distribution
    # Temperature=1.0 for returns (they're already small ~0.01-0.10)
    p_true = F.softmax(actual_returns / 0.05, dim=0)  # temperature 0.05
    p_pred = F.log_softmax(pred_scores, dim=0)
    return F.kl_div(p_pred, p_true, reduction='batchmean')
```

### Model Changes

**New ranking head** (added to TemporalSurfaceTransformer):

```python
# In __init__:
self.ranking_head = nn.Sequential(
    nn.Linear(backbone_dim, head_hidden),
    nn.GELU(),
    nn.Linear(head_hidden, 1)
)

# In forward:
ranking_score = self.ranking_head(z).squeeze(-1)  # (B,)
outputs['ranking_score'] = ranking_score
```

Parameters added: 64*64 + 64 + 64*1 + 1 = 4,225 (same as other heads). Total model: 683,723 params (+0.6%).

### Modified V5Loss

```python
# New weight:
self.w_rank = 0.5  # Start moderate — can tune

# In forward():
# Ranking loss — requires date grouping in batch
if 'date_ids' in kwargs and self.w_rank > 0:
    ranking_scores = outputs['ranking_score']
    date_ids = kwargs['date_ids']
    unique_dates = date_ids.unique()

    rank_loss = torch.tensor(0.0, device=y_return.device)
    n_dates = 0
    for d in unique_dates:
        mask = date_ids == d
        if mask.sum() < 5:  # need enough stocks for meaningful ranking
            continue
        rank_loss += listnet_ranking_loss(
            ranking_scores[mask], y_return[mask]
        )
        n_dates += 1

    if n_dates > 0:
        loss_rank = rank_loss / n_dates
    else:
        loss_rank = torch.tensor(0.0, device=y_return.device)
else:
    loss_rank = torch.tensor(0.0, device=y_return.device)

total += self.w_rank * loss_rank
```

### Training Data Pipeline Changes

**DateGroupedBatchSampler**: instead of random shuffling across all stocks, construct batches that contain complete dates:

1. Build date -> sample indices mapping at dataset init
2. Each batch: pick K random dates, include ALL stocks from those dates
3. Variable batch size (depends on how many stocks trade on selected dates — typically 200-800 per date for the universe)
4. Pad to max stocks per batch or use packing

**Implementation sketch**:

```python
class DateGroupedDataset(torch.utils.data.IterableDataset):
    """Yields batches grouped by date for cross-sectional ranking loss."""

    def __init__(self, batch_size_dates=4, max_stocks_per_date=1000):
        # Load chunks, build date->indices map
        self.date_groups = {}  # date_int -> list of (chunk_idx, sample_idx)
        ...

    def __iter__(self):
        # Shuffle date order
        dates = list(self.date_groups.keys())
        random.shuffle(dates)

        for date in dates:
            indices = self.date_groups[date]
            # Load all samples for this date
            # Yield as (tokens, types, mask, day_mask, y_return, y_big, date_id)
            ...
```

### V5 72-dim Output Changes

The 72-dim output layout consumed by V13 would change:

```
[0:64]   = backbone embedding z (unchanged)
[64]     = composite score (unchanged formula)
[65]     = p_big (unchanged)
[66]     = p_up (unchanged)
[67:72]  = quantile predictions [q50, q75, q90, q95, q99] (unchanged)
[72]     = ranking_score (NEW — cross-sectional ranking prediction)
```

V13 BACKBONE_DIM would change from 72 to 73. The ranking_score feature would be specifically designed for cross-sectional portfolio construction.

---

## 5. Alternative Approaches Considered and Rejected

### A. Contrastive Learning on Embeddings

The existing `_contrastive_loss` uses 3 coarse buckets (big_up, big_down, small). Could refine to continuous:
- **Pro**: Already has code template, no new head needed
- **Con**: Contrastive learns embedding similarity, NOT ranking. Two stocks with 5% and 10% returns are both "big_up" — contrastive can't distinguish them. Ranking loss directly optimizes for relative ordering.
- **Verdict**: REJECTED — wrong objective. Contrastive can supplement ranking but not replace it.

### B. Direct Cross-Sectional Head (takes N stocks, outputs N ranks)

A separate transformer that takes all stocks on one date as input and outputs rankings:
- **Pro**: Most direct approach — learns stock-stock interactions
- **Con**: Variable input size (200-800 stocks/date), very expensive (N^2 attention), cannot be precomputed (depends on which stocks are present each day), fundamentally different architecture
- **Verdict**: REJECTED for v1 — too complex. The simpler per-stock ranking head can capture "this stock looks better than average for this date" without cross-stock attention. If v1 fails, cross-sectional head is the v2 approach.

### C. Replace All Losses with Ranking

Train only with ranking loss, no per-stock losses:
- **Pro**: Single clear objective aligned with downstream task
- **Con**: Loses per-stock signal (p_up, p_big, quantiles). V13 ranking MLP already proved p_up and q50 ARE useful features for portfolio — they exist because of per-stock loss. Eliminating per-stock loss might destroy the features we know work.
- **Verdict**: REJECTED — multi-task is safer. Can ablate later.

---

## 6. Risk Assessment

### Risk 1: Ranking Loss Destabilizes Per-Stock Heads (MEDIUM)

Cross-sectional ranking gradients flow through the backbone, potentially interfering with per-stock loss gradients. If the backbone tries to encode ranking information into the embedding, it might lose per-stock prediction quality.

**Mitigation**:
- Start with low ranking weight (w_rank=0.2), increase gradually
- Monitor ALL per-stock metrics (p_big precision/recall, direction accuracy, captured return) during training — if they degrade >10%, reduce w_rank
- Can freeze backbone and train only ranking_head first as sanity check

### Risk 2: Date-Grouped Batching Hurts Training Efficiency (LOW-MEDIUM)

Current training shuffles globally across all stocks and dates. Date-grouped batching means each batch is stocks from the same date, which may have correlated features (market-wide effects).

**Mitigation**:
- Mix strategy: 50% of batches are date-grouped (for ranking loss), 50% are random-shuffled (for per-stock losses). Ranking loss only computed on date-grouped batches.
- Monitor GPU utilization — variable batch sizes from date grouping may reduce throughput

### Risk 3: Date-Grouped Batching is Technically Complex (MEDIUM)

V5 chunks don't store dates. Need to either:
(a) Re-prepare all 264 chunks with date_int field, OR
(b) Build a separate date-index file that maps chunk_idx + sample_idx -> date_int

**Mitigation**: Option (b) is non-destructive — build an auxiliary index file during a one-time scan of the raw data. No need to regenerate 33GB of chunks.

### Risk 4: Retraining Takes Long and May Not Help (HIGH)

V5 full training took the best part of a day. Retraining with ranking loss could take similarly long. If the ranking head doesn't improve downstream portfolio performance, that's a day of GPU time wasted.

**Mitigation**:
- Unit test (<2 min): verify ranking loss computes, gradients flow, no NaN
- Prove-out (1-3 hr): 20% of data, verify ranking loss decreases AND per-stock metrics don't degrade
- Smoke test: 3 passes, full data, verify ranking_score has positive correlation with forward returns on val set
- Only if smoke passes: full training

### Risk 5: Re-caching and Re-testing V13 Portfolio (LOW)

After retraining V5, must:
1. Rebuild V13 backbone feature cache (73-dim instead of 72-dim)
2. Re-run ranking MLP experiment with new features
3. Compare to current best (Val 0.572)

**Mitigation**: This is straightforward — just cache rebuild + one experiment run. ~1 hour total.

---

## 7. Implementation Plan

### Phase 1: Data Preparation (2-4 hours implementation)

1. **Add date_int to V5 chunks** — modify `prepare_tokens.py` to include `date_int` (int32) per sample. Run incremental rebuild (only add field, don't regenerate tokens).
   - Alternative: build auxiliary date index file without modifying chunks (scan existing chunks + raw data to build mapping).
2. **Implement `DateGroupedDataset`** — new IterableDataset that yields same-date batches. Must handle variable batch sizes.
3. **Unit test** — verify date grouping produces correct batches (all samples in batch share same date).

### Phase 2: Model + Loss Changes (1-2 hours implementation)

1. **Add `ranking_head`** to TemporalSurfaceTransformer (+4,225 params)
2. **Add ListNet ranking loss** to V5Loss with `w_rank` weight
3. **Modify forward()** to output `ranking_score`
4. **Modify train.py** to pass `date_ids` to loss function when using date-grouped batches
5. **Unit test** — verify ranking loss computes, gradients flow through ranking_head AND backbone

### Phase 3: Training (1-3 days GPU)

1. **Unit test** (<2 min): full pipeline validation
2. **Prove-out** (1-3 hr): 20% data, verify:
   - Ranking loss decreases
   - Per-stock metrics (precision, recall, direction_acc) don't degrade >10%
   - ranking_score correlation with forward returns is positive
3. **Smoke test** (4-6 hr): full data, 3 passes
4. **Full training** (12-24 hr): if smoke passes

### Phase 4: V13 Integration (2-4 hours)

1. Update V13 BACKBONE_DIM from 72 to 73
2. Rebuild backbone feature cache with new model
3. Re-run ranking MLP with p_up + q50 + ranking_score (3 features)
4. Compare to current best (Val 0.572)

### Total Estimated Timeline

| Phase | Duration |
|---|---|
| Data prep implementation | 2-4 hours |
| Model+loss implementation | 1-2 hours |
| Unit + prove-out testing | 2-4 hours |
| Smoke test | 4-6 hours |
| Full training | 12-24 hours |
| V13 integration + test | 2-4 hours |
| **Total** | **~2-3 days** |

---

## 8. Success Criteria

The retraining is successful if:

1. **Per-stock metrics don't degrade**: captured return, precision, direction_acc within 5% of current V5 best
2. **ranking_score has positive rank correlation** with forward returns on val/test (even 0.02-0.03 would be meaningful)
3. **V13 portfolio Val Sharpe improves** above 0.572 when using features from retrained backbone
4. **Ideal target**: Val Sharpe > 1.0 (approaching smoke gate of 1.28)

### Failure Criteria (when to stop)

- Per-stock metrics degrade >15% at prove-out: ranking loss weight too high, reduce or abandon
- ranking_score has zero/negative correlation after full training: ranking head can't learn from this data
- V13 Val Sharpe doesn't improve: backbone change didn't help, the ceiling is elsewhere

---

## 9. Key Insight: The Disabled Contrastive Loss

V5 already has a contrastive loss (`w_contrast=0.0`) that was designed to compare stocks but was disabled. This suggests the original V5 authors considered cross-stock learning but didn't ship it. The contrastive loss uses coarse 3-bucket grouping (>10%, <-10%, <2%) which is far too coarse for ranking. The ListNet approach is a strictly better version of this idea — continuous rather than discrete, and directly optimized for ranking rather than embedding similarity.

The existing `w_contrast=0.0` code can serve as a template for how to integrate cross-stock loss into the V5 training loop.
