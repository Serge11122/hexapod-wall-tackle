# PROJECT MUST: Systematic V13 Experimentation — Beyond Hyperparameter Tuning

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — 8 consecutive smoke failures prove hyperparameter tuning alone cannot solve V13 integration. Must expand scope.

## Conviction

The V13 portfolio approach using the V5 backbone IS viable — the backbone produces 2-5x better captured return than V3/V10 at the backbone level. The failure is in the INTEGRATION, not the backbone. But the current cycle (tune LR → fail → tune LR again) is stuck in a local minimum. The system MUST expand beyond hyperparameter tuning to include architecture changes, ablation studies, and systematic experimentation.

## The Evidence: V5 Backbone Is Superior

- V5 temporal transformer with 5-day lookback: **2-5x captured return** vs V3 at backbone level (proven)
- V5 produces 72-dim features: 64-dim embedding + score + p_big + p_up + 5 quantiles
- V10 uses single-day snapshot backbone — inherently limited, no temporal context
- The signal EXISTS in the V5 backbone output. The portfolio model must learn to USE it.

## What Has Been Tried (all failed)

| Experiment | What Changed | Result | Learning |
|---|---|---|---|
| TO=0.15, no EMA | Baseline | Sharpe 1.34, TO 0.69 | Turnover too high |
| TO=1.0, no EMA | Lambda scaling | Sharpe 0.05 | Lambda kills learning |
| EMA α=0.3 | Architectural smoothing | Sharpe 1.45, TO 0.41 | EMA helps but not enough |
| EMA α=0.1, Friday-only | Stronger EMA | Sharpe 1.33, TO 0.15 | **Fraudulent** — Friday data |
| EMA α=0.1, all weekdays | Same on real data | Sharpe 0.45, TO 0.45 | EMA doesn't transfer |
| LR=3e-4, WU=3000 | High LR | Collapsed step 82 | LR too high |
| LR=1e-4, WU=300 | Medium LR | Collapsed step 700 | Still too high |
| LR=3e-5, WU=300, 10-comp loss | Low LR | Sh 0.376 plateau, STABLE | **Architecture bottleneck** — LR exhausted |
| **LR=3e-5, 3-comp loss** | **Architecture (loss simplification)** | **Sh 0.271, KILLED** | **Auxiliary losses HELP. Model capacity-starved, not gradient-confused.** |
| **SH=192, WH=192, 94K, LR=3e-5** | **Architecture (model size increase)** | **Sh 0.170 oscillating, KILLED** | **LR=3e-5 too high for 94K params. Oscillation = LR scaling needed.** |
| **SH=192, WH=192, 94K, LR=1e-5** | **LR variant on arch** | **Sh 0.307→0.177 declining, KILLED** | **LR EXHAUSTED at 94K. Same failure mode as 3e-5 but slower. Peak during warmup, decline at steady-state. Model size approach ABANDONED.** |
| **Bottleneck 72→16→38, 40K, LR=3e-5** | **Architecture (compression)** | **Sh 0.640→0.205 declining, KILLED** | **Bottleneck found 2x MORE signal during warmup (0.640 vs 0.376) but LESS stable at full LR. Signal EXISTS but frozen backbone features aren't portfolio-optimized. All downstream-only changes exhausted.** |
| **Backbone fine-tuning, 264K, LR=3e-5/1e-6** | **Architecture (BACKBONE)** | **Sh 0.511, Cold 0.745 (250 steps only), KILLED (time)** | **BREAKTHROUGH: Fine-tuning produced BEST-EVER Val Sharpe (0.511) AND Cold Sharpe (0.745, trending UP). Killed by infrastructure.** |
| **Backbone fine-tuning #13b, 264K, LR=3e-5/1e-6, 50% warmup** | **LR variant on arch** | **Sh 0.921 peak → 0.263 collapse (500/1400 steps), KILLED** | **Peak 0.921 at LR=1.05e-5 = 2.4x best frozen. Collapse at LR>1.5e-5. 50% warmup delayed but didn't prevent collapse. Productive range: 3e-6 to 1.2e-5. Cap peak LR at 1e-5 next.** |
| **Backbone fine-tuning #14, 264K, LR=1e-5/1e-6, 50% warmup** | **LR variant on arch** | **Sh 0.431 peak, plateau 0.38-0.43, train loss→0, KILLED (step 800)** | **LR cap prevented collapse but NOT plateau. Peak at LR=3.51e-6, decline above 5e-6. Train loss→0 = OVERFITTING on 1000-sym subset. #13b's 0.921 was warmup transient. Productive range REVISED: 1e-6 to 5e-6. 3 fine-tuning experiments done → ARCHITECTURAL CHANGE REQUIRED within fine-tuning.** |
| **Proj-only #15a, 66K, LR=3e-6 const, WD=1e-3** | **Architecture (reduced unfreeze)** | **Sh 0.868 (BEST STABLE), Test 0.852, COMPLETED** | **BREAKTHROUGH: Proj-only (25K backbone params) SOLVES overfitting completely. Train loss stable, NOT → 0. Val/Test ratio 0.98 = exceptional generalization. 2x improvement over #14. Constant LR eliminates warmup-collapse. Overlays hurting: 0.868→0.410 (53% loss). Turnover excellent at 0.083.** |
| **Proj-only #15b, 66K, LR=5e-6 const, WD=1e-3** | **LR variant on proj-only** | **Val 0.523, Test 1.071, COMPLETED** | **Higher LR learns slower on val (0.523 vs 0.868) but generalizes better to test (1.071 vs 0.852). Still accelerating at 1400 steps. Higher turnover (0.126 vs 0.083). Overlays destroy 58% on val. LR=3e-6 confirmed val-optimal at 1400 steps. LR dimension mapped for proj-only.** |

| **Proj-only #15c, 66K, LR=3e-6 const, WD=1e-3, 2800 steps, DD off** | **Step count + overlay ablation** | **Val 0.477, Test 0.805, COMPLETED** | **SAME CONFIG as #15a but 0.477 vs 0.868. No train.py changes. Root cause: no fixed random seed — portfolio model init random each run. DD breaker disabled had NO effect on overlay (still 53% loss). Vol scaling alone is destructive. 2800 steps peaked at 2000 then overfit.** |
| **Ranking MLP #24, 167p, p_up+q50+p_big, ListMLE, seed=42** | **Feature addition (3rd scalar)** | **Val 0.562, Test 0.571, COMPLETED** | **p_big REDUNDANT. Val -2% vs #23a. Test oracle corr NEGATIVE. ALL scalar features EXHAUSTED.** |
| **Embedding MLP #25, 12609p, 64-dim embed, ListMLE, dropout 0.3, WD 1e-2** | **Input representation (embedding vs scalars)** | **Val 0.535, Test 0.645, COMPLETED** | **Embedding 6% WORSE than scalars on val. Val declining (overfitting). Temporal patterns not useful for cross-sectional ranking. Scalars are better distilled summaries.** |
| **Hybrid MLP #25b, 12869p, embed+p_up+q50 66-dim, ListMLE, dropout 0.3, WD 1e-2** | **Feature combination (embedding+scalars)** | **Val 0.485, Test 0.686, COMPLETED** | **HYBRID WORSE THAN BOTH components (-15% vs scalars, -9% vs embedding). Embedding INTERFERES with scalar signal. ENTIRE BACKBONE OUTPUT EXHAUSTED (31 experiments).** |
| **Proj-only #15d, 66K, LR=3e-6 const, WD=1e-3, seed=42, overlays off** | **Reproducibility fix** | **Val 0.330, Test 0.887, COMPLETED** | **REPRODUCIBLE BASELINE. Best step was 200/1400 — training barely helps. Oracle corr ≈ 0 — model NOT learning portfolio task. #15a's 0.868 was a 2.6x lucky outlier. True proj-only perf is 0.33. 3.9x gap to smoke gate. Architecture is fundamentally wrong.** |
| **Linear blend #17, 25 params, LayerNorm+Linear(8,1), LR=3e-6 const** | **Architecture (minimal learned model on 8 scalars)** | **Val 0.278, KILLED step 1250** | **25 params too few for Sharpe loss. Gradient through 60-day Sharpe with 1000 symbols is noise for tiny model. +11% above random init. WORSE than cross-attention (0.330). DD 78.9%. Portfolio Sharpe loss FAILS for <100 params. Ranking loss needed.** |

**Pattern**: Experiments 1-8 were hyperparameter variations. 9-12: downstream-only changes, all failed. 13-14: backbone fine-tuning, overfits. 15a-c: proj-only, unreproducible. 15d: reproducible baseline = 0.330. Oracle correlation ≈ 0. **16: Direct score ranking CONFIRMED signal exists. 17: Linear blend FAILED (Sharpe loss). 17b: Score-weighted FAILED. 18: Ranking MLP CONFIRMED. 19-21: p_up+score ceiling at 0.478 (loss/capacity NOT bottleneck). 22: regime mixed (test +62%, val -17%). 23a: p_up+q50 BREAKS ceiling (Val 0.572 = +20%, first learned > heuristic). 23b: regime NOISE with correct features (Val 0.449 = -22%). 23a-ext: 133-param ceiling CONFIRMED at ~0.57 (6000 steps, converges in 500). 23c: capacity HURTS (-69%). 24: p_big REDUNDANT. 25: embedding WORSE than scalars (Val 0.535 vs 0.572). 25b: hybrid WORSE than BOTH components (Val 0.485 = -15%, INTERFERENCE). 26a: weekly mean FAILED (-54%). 26b: weekly last CATASTROPHIC (-87%). 27: attention portfolio FAILED (-59%). 28: return prediction FAILED (-33%, memorization).** 36 experiments total. ALL portfolio-level approaches using V5 backbone output EXHAUSTED. Only V5 backbone retraining remains.

## What Has NOT Been Tried (must explore)

### Architecture Changes (HIGH priority)
1. ~~**Compression layer variants**~~ — **TRIED AND FAILED** (experiments 9, 12). Direct 72→38 plateaus at 0.376. Bottleneck 72→16→38 found MORE signal (peak 0.640) but collapsed at full LR. Compression changes alone cannot solve the integration problem — the root cause is upstream (frozen backbone).
2. ~~**Portfolio model size**~~ — **TRIED AND FAILED** (experiments 10-11). 94K model (SH=192, WH=192) failed at BOTH LR=3e-5 (oscillation) and LR=1e-5 (decline). LR dimension exhausted for larger model. Model size approach abandoned.
3. ~~**Backbone fine-tuning (2-layer)**~~ — **3 EXPERIMENTS DONE. OVERFITTING.** #13a: 0.511 (killed time). #13b: 0.921 transient peak (collapse at LR>1.5e-5). #14: plateau 0.43, train loss→0 (overfitting). 264K params memorizes 1000-symbol subset. MUST try: (a) unfreeze only 1 layer (reduces trainable params ~50%), (b) constant LR at 3e-6 (stay in productive range), (c) increased weight decay (1e-3).
3b. ~~**Backbone fine-tuning (1-layer)**~~ — **SUPERSEDED by proj-only (#15a)**. 1-layer = full temporal (223K) for V5's single-block backbone. Proj-only (25K) is the correct granularity, producing Val Sharpe 0.868 vs 0.431 with full temporal. DO NOT go back to unfreezing temporal blocks.
4. **Different aggregation** — Current: cross-attention over symbol features. Try: simple mean pooling, top-K attention, transformer encoder over symbols
5. **Temporal feature engineering** — Instead of compressing 72-dim to 38-dim, extract temporal-specific features: 5-day trend slope, volatility regime, momentum signal from the embedding sequence

### Training Changes (MEDIUM priority)
6. ~~**Loss function simplification**~~ — **TRIED AND FAILED** (experiment 9). 3-component loss (Sharpe+Sortino+Turnover) produced Sharpe 0.27, WORSE than 10-component (0.38). Auxiliary losses provide useful gradient signal. Do NOT retry.
7. **Curriculum learning** — Start with easy samples (high-signal dates), gradually add harder ones
8. **Different optimizer** — Current: AdamW. Try: SGD with momentum (more stable for small models), LAMB, or Lion

### Data Changes (MEDIUM priority)
9. **Weekly rebalancing on full data** — NOT Friday-only filtering, but actual weekly portfolio decisions on all weekday data. Reduces effective turnover while keeping full information
10. **Backbone feature selection** — Instead of all 72 dims, use only the most predictive subset (embedding + p_up, drop quantiles that may be noise)

## Experimentation Protocol

### Tagged Model Protection (MANDATORY)

- **NEVER modify code in a directory that has a `*_tag_*` copy.** If `v5_tag/` exists, `v5/*.py` is frozen.
- Experiments go in NEW folders: `v5_experimental/`, `v5_wrank/`, `v6/`, etc.
- Copy the tagged code to the new folder, modify the copy.
- Cache from tagged models is IMMUTABLE — do not overwrite or rebuild. New fields → side-cache supplements that join at load time.
- If an experiment needs additional data fields in existing cache, create a `supplements/` directory with per-chunk files containing only the new fields. Join at load time: `chunk.update(supplement)`.
- See `conviction_tagged_model_protection.md` for full rules.

### Cache Reuse (MANDATORY)

- **Reuse existing cache** from tagged models whenever possible. Don't rebuild what already exists.
- **Append new fields as side-caches**, not by modifying the cache generation code. Side-caches are small, fast to generate, and don't invalidate the main cache.
- **Join caches at load time** — load main cache + load supplement(s) + merge dicts. Same API, no expensive regeneration.
- If a new experiment needs the same tokens but different labels → side-cache for labels only.
- If a new experiment needs same tokens + additional metadata → side-cache for metadata only.
- Only rebuild cache when the core data (tokens, masks) must fundamentally change.

### Fast Iteration Loop (MANDATORY)

Each experiment MUST follow this timeline:

| Phase | Time Budget | What Happens |
|---|---|---|
| Design | 5 min | tconv identifies next experiment from failure analysis |
| Implement | 15 min | tdev makes code changes in NEW folder + unit test |
| Smoke | 20 min max | 3000 steps on daily data. Kill at 25% if Sharpe < 0.5 |
| Analyze | 5 min | tconv reads results, updates experiment log, picks next |

**Total cycle: ~45 min per experiment.** At this rate, 3 experiments per 2.5 hours.

### Kill Gates for Experiments (tighter than production)

- **At step 750 (25%)**: Val Sharpe must be > 0.3. If not → KILL immediately. Don't wait.
- **At step 1500 (50%)**: Val Sharpe must be > 0.7. If not → KILL.
- **At any point**: If Val Sharpe drops >50% from peak for 3+ evals → KILL (collapse detected).
- **Turnover at any point**: If > 0.50 → KILL. Architectural change needed, not more training.

### Experiment Log (MANDATORY)

tconv MUST maintain an experiment log in `goal_tracker.md` with:
- What was changed (architecture, not just hyperparameters)
- Hypothesis (why this should work)
- Result (peak Sharpe, where it collapsed, turnover)
- **Learning** (what this teaches about the integration problem)

Each failure MUST produce a learning that informs the NEXT experiment. "Try lower LR" is NOT a learning. "Model is stable at LR<5e-5 but signal is weak — need larger model capacity or simpler loss" IS a learning.

### Multiple Experiments

tdev MAY implement multiple architecture variants in the same cycle:
- Create `firstrate_portfolio/v13/experiments/` directory
- Each experiment gets a config override file (not modifying main config.py)
- Smoke tests can reference experiment configs: `--experiment exp_large_model`
- This allows A/B testing without destabilizing the main code

## Violations

1. **Repeating failed hyperparameter class** — Trying another LR value when 3 LR values have already failed without any architectural change between them. After 3 failures in the same dimension (LR, lambda, alpha), MUST change architecture before trying that dimension again.

2. **No architecture change after 3 consecutive smoke failures** — If 3 smoke tests fail in a row with only hyperparameter differences, the next experiment MUST include a structural code change (model architecture, loss function, data pipeline, or training approach). Hyperparameter-only iterations are banned until an architectural change is tested.

3. **No learning from failure** — Submitting a new experiment without documenting what the previous failure taught. Each experiment entry in goal_tracker must have a "Learning" field that feeds into the next experiment's hypothesis.

4. **Experiment exceeding time budget** — Any smoke experiment running >20 min or prove-out experiment running >1 hr without early-kill gates. Experiments must fail fast.

5. **No experiment log** — Running experiments without recording them in goal_tracker.md with hypothesis, result, and learning.

6. **Modifying tagged anchors** — Changing V10 WH96 tagged model or V5 backbone weights during experimentation. These are immutable references.

7. **Abandoning V13 before architectural exploration** — Declaring V13 failed while only hyperparameter variations have been tried. Must try at least 3 distinct architectural changes (compression layer, model size, loss simplification) before considering abandonment.

8. **Single-threaded experimentation** — Running only one experiment configuration per cycle when multiple independent variations could be tested. If two experiments are independent (e.g., larger model vs simpler loss), implement both and let results inform each other.

9. **Using portfolio Sharpe loss for models <1000 params** — Proven: 25-param linear blend (#17) got 0.278, 41K-param cross-attention (#15d) got 0.330, both with oracle corr ≈ 0. Portfolio Sharpe loss gradient through 60-day windows is noise for small models. Models <1000 params MUST use ranking loss (pairwise margin, listwise, or similar) — not portfolio Sharpe.

9b. **Using pairwise margin loss with margin >= 0.1** — Proven: margin=0.1 causes loss saturation at loss=0.1000 for both 133-param (#19) and 337-param (#18) models. Once all pairs are correctly ordered within margin, gradients vanish completely. #19 showed identical Val Sharpe (0.478) at all 6 eval points from step 500 to 3000 — zero learning for 2500 steps. Pairwise margin with margin >= 0.1 is BANNED. Use listwise loss (ListMLE, smooth NDCG) or margin < 0.01.

9c. **Repeating same architecture at different loss without increasing capacity** — Proven: #20 (ListMLE) produced IDENTICAL results to #19 (margin) on 133-param 2-feature model. Loss function doesn't matter when architecture is the ceiling. If two different losses produce identical metrics, the next experiment MUST change model capacity or feature count — not try a third loss function.
9d. **Increasing model capacity on same 2-feature input** — Proven: #21 (2309 params, hidden [64,32]) produced IDENTICAL results to #19/#20 (133 params): Val 0.478 at all eval points. Model capacity is NOT the bottleneck. The p_up+score input space has a hard ceiling at 0.478. Do NOT try even larger models on 2 features. MUST add features or change input representation.
9e. **Using composite `score` as ranking feature** — Score has ρ=-0.029 (anti-signal). All experiments #19-#22 used score as 2nd feature — model ignored it (just sorts by p_up). The 0.478 "ceiling" is p_up-only, not a true 2-feature ceiling. MUST test p_up + q50 (ρ=+0.019) before declaring scalars exhausted. q50 = predicted median return, genuinely complementary to p_up = direction probability.

## Runtime Behavioral Tests

10. **Last 3 smoke results must not be same-class failures** — Check goal_tracker experiment table. If last 3 entries share the same "Class" column value (e.g., all "LR variant") and all failed, next experiment MUST be a different class. Verified by tconv reading the table.

11. **Model gradient signal strength** — For any new learned model, after 50 unit-test steps: if val_sharpe improvement over random init is <5% (abs improvement <0.02), the model-loss combination is unlikely to work at smoke scale. Flag as WARNING (not blocking). #17 showed +11% (0.278 vs 0.25) at unit, then plateaued — this threshold would have caught borderline cases earlier.

9f. **Trying more scalar feature combinations** — ALL 8 scalar backbone features (score, p_big, p_up, q50, q75, q90, q95, q99) have been tested for ranking. score=anti-signal (#19-#22), p_big=redundant (#24), regime_std=noise (#22/#23b), q50=only additive (#23a). Do NOT try q75, q90, q95, q99, or other scalar combinations. Scalar features top out at Val ~0.57 with p_up+q50.
9g. **Using raw 64-dim embedding alone for ranking** — Proven: #25 (12,609 params, dropout 0.3, WD 1e-2) produced Val 0.535, 6% WORSE than p_up+q50 scalars (0.572). Val declined from peak (overfitting despite regularization). Raw temporal embedding captures within-stock patterns NOT useful for cross-sectional ranking. Do NOT repeat embedding-only experiments.
9h. **Combining embedding with scalars in ranking MLP** — Proven: #25b (12,869 params, 66-dim hybrid embed+p_up+q50, dropout 0.3, WD 1e-2, ListMLE) produced Val 0.485, 15% WORSE than p_up+q50 scalars (0.572) and 9% WORSE than embedding alone (0.535). Embedding INTERFERES with scalar signal — 64 embedding dims overwhelm 2 scalar dims. Val declined 0.485→0.403 (overfitting). ENTIRE BACKBONE OUTPUT EXHAUSTED after 31 experiments. Do NOT try any other backbone feature combination for ranking MLP.
9i. **Weekly mean feature aggregation** — Proven: #26a (weekly rebalance with mean aggregation of 5-day p_up+q50) produced Val 0.265, 54% WORSE than daily (0.572). Test 0.002 (zero signal). Mean aggregation washes out daily ranking variation. Turnover 0.165 (not the expected ~0.03) = p_up rankings unstable week-to-week. Do NOT use mean aggregation of backbone features for weekly models.
9j. **Weekly last-day feature aggregation** — Proven: #26b (weekly rebalance with last-day features, no averaging) produced Val 0.073, 87% WORSE than daily (0.572), 72% WORSE than weekly mean (0.265). Test -0.209 (NEGATIVE). Oracle corr -0.013 (NEGATIVE = anti-correlated). Model learned NOTHING. Root cause: weekly 5-day returns are fundamentally incompatible with backbone features. p_up and q50 predict next-day behavior, not 5-day cumulative returns. This is a target mismatch, not an aggregation problem. Do NOT attempt any weekly rebalancing variant.
9k. **Any weekly rebalancing** — PERMANENTLY ABANDONED. Two experiments (#26a mean, #26b last) both catastrophically failed. Daily backbone features (p_up, q50) predict next-day returns — they have ZERO predictive power for 5-day cumulative returns. No aggregation method can fix a target mismatch. Do NOT propose weekly rebalancing under any aggregation scheme.
9l. **Attention portfolio on 2 scalar features** — Proven: #27 (245-param self-attention, d_model=8, p_up+q50, ListMLE) produced Val 0.236 (-59% vs ranking MLP's 0.572). Oracle corr NEGATIVE throughout (-0.006 to -0.009). Loss flat (4.18→4.13→4.18). With only 2 scalar features per stock, attention cannot compute meaningful key/query/value interactions — there's no information for stocks to "attend to" in each other. Cross-stock attention needs richer per-stock representations (embedding, multi-feature). Do NOT retry attention with 2 scalar features.
9m. **Return prediction from 2 scalar features** — Proven: #28 (133-param MLP, Huber loss delta=0.01, p_up+q50) produced Val 0.384 (-33% vs ranking MLP's 0.572). Train loss dropped 100x but val Sharpe FLAT at 0.384 at ALL 6 evals — model memorized training data, zero generalization of regression signal. Return corr 0.0003 (zero). Turnover 0.002 (near-static portfolio). Model predicts near-constant returns across stocks because p_up+q50 encode direction (ranking order), not return magnitude. Ranking formulation is fundamentally correct for these features. Do NOT retry return prediction with backbone scalars.
9n. **Any new portfolio architecture on current V5 backbone output** — 36 experiments exhausted: cross-attention (0.330), ranking MLP (0.572), embedding (0.535), hybrid (0.485), weekly (abandoned), attention portfolio (0.236), return prediction (0.384). The backbone features themselves are the ceiling — no portfolio architecture can exceed Val 0.572. Further portfolio-level experiments on current backbone output are BANNED unless V5 backbone is retrained with new objectives.
