# PROJECT MUST: Working V13 Portfolio Model with Temporal Transformer Backbone

**Status**: ACTIVE CONVICTION
**Priority**: HIGH — temporal signal stability is the identified bottleneck, not model capacity

## Conviction

The project MUST build a fully working V13 portfolio model that uses a V5-based temporal transformer backbone with 5-day lookback. The previous V13 attempt failed due to integration issues (not backbone quality). The V5 backbone achieved 2-5x better captured return than V3 at the backbone level — that signal quality must be properly channeled into the portfolio model.

### Anchor Performance (models to match or beat)

**V10 WH96 Portfolio (anchor for portfolio-level metrics):**
- **Test Annualized Return: 144.71%** — the primary growth target
- **Test Cumulative Return: 1314.21%** over ~3 years (2023-2025)
- **Val Annualized Return: 101.69%**, Val Cumulative: 715.91%
- Pure Test Sharpe: **2.569**, Val Sharpe: 1.737
- Turnover: **0.057**, Max DD: **14.0%**
- Vol+DD overlay Sharpe: 2.906, DD: 14.0%
- Model: 38,271 params. SH=96, CD=32, WH=96, heads=4.
- Tag: `v10_tag_fix2a_sh96_wh96` (IMMUTABLE)

**V5 Backbone (anchor for backbone-level metrics):**
- Captured return: **2-5x better than V3** at backbone level (proven)
- 5-day lookback with transformer attention, 679,498 params
- Trained weights: `firstrate_learning/v5/models/best_model.pt`

**V10 Backbone (the inferior baseline):**
- Single-day snapshot, no temporal context
- Root cause of high turnover and signal instability in V10 portfolio

### Performance Requirements

V13 portfolio model MUST match or improve on V10 WH96 portfolio. V13 backbone MUST match or improve on BOTH V5 backbone AND V10 backbone at the backbone level.

If V13 portfolio underperforms V10 portfolio, the integration is wrong — not the backbone. The V5 backbone signal is proven superior (2-5x captured return). The portfolio model must learn to use it.

A correctly integrated V13 portfolio model with V5 transformer backbone should produce:
- **Annualized return >= 144%** on test period (match V10's 144.71%)
- **Sharpe >= 2.5** on test period (match V10's 2.569)
- **Turnover <= 0.057** (match V10 — temporal context should reduce daily noise reactions)
- **Max DD <= 15%** (match V10's 14.0%)
- Better signal stability (5-day lookback smooths decision-making)

The GROWTH RATE is the ultimate metric. Sharpe measures risk-adjusted return, but the project goal is high absolute annual growth. A model with Sharpe 1.5 and 200% annual return is better than Sharpe 3.0 and 50% annual return.

V10 improvements are a STARTING POINT, not a constraint. The V13 architecture MAY diverge from V10 if experimentation shows a different approach works better with the temporal backbone:

**Carry forward (proven useful):**
- Vol scaling overlay (Spec A), Drawdown breaker overlay (Spec B), Confirmation filter overlay (Spec H)
- Common trade entry/exit module, dual metrics

**Open for experimentation (not locked to V10 values):**
- SYMBOL_HIDDEN, WEIGHT_HIDDEN — may need different sizes for 72-dim temporal input
- Compression layer — may need different architecture (attention, PCA, bottleneck)
- Loss function — 10-component may be too complex; simpler Sharpe-only loss may work better
- Model architecture — cross-attention may not be optimal for temporal features
- LR and training config — V13 has different stability characteristics than V10
- LAMBDA_TURNOVER — architectural smoothing (EMA) may replace loss-based turnover penalty

See `conviction_v13_experimentation_strategy.md` for the full experimentation protocol.
- 10-component loss function with oracle distillation
- Cold start training with state dropout
- Straight-through top-K estimator

The V13 portfolio model must compress the V5 72-dim backbone output to match the portfolio model's input expectations (learned projection layer, not raw 72-dim feed). The previous failure was caused by feeding 72-dim directly into a model optimized for 38-dim — the weight space was disrupted.

## Requirements

1. **V5 temporal transformer backbone** — 5-day lookback over options surfaces, trained weights from `firstrate_learning/v5/models/best_model.pt`
2. **Learned compression layer** — project V5 72-dim output → 38-dim (or tuned dim) to match portfolio model input expectations. Train this projection jointly with the portfolio model.
3. **Port all WH96 improvements** — same loss function, same overlay infrastructure, same training configuration, same slippage model
4. **Use firstrate_common.trade_entry_exit_common** — no local trade_execution.py (conviction: trade entry/exit common module)
5. **Efficient training** — ChunkLoader, AMP, torch.compile, GPU >70%, zstd caching (conviction: efficient cache and training)
6. **Progressive testing** — unit test → smoke test → prove-out → full. Each gate must pass before the next.
7. **Dual metrics** — always report pure model AND model+overlays. Goal: improve underlying model.
8. **Success gates** — see below.

### Success Gates (relative to V10 WH96 anchor)

**V10 anchor targets: Test Sharpe 2.569, Test Annual Return 144.71%, Turnover 0.057, DD 14.0%**

| Gate | Sharpe | Annual Return | Turnover | DD | Kill Condition |
|---|---|---|---|---|---|
| **Smoke** | Val >= 1.28 | Val >= 50% | < 0.17 | < 40% | Val Sharpe < 0.3 at 25% of steps |
| **Prove-out** | Val >= 1.93 | Val >= 100% | < 0.11 | < 25% | Val Sharpe < 1.0 at 25% of steps |
| **Full** | Test >= 2.5 | Test >= 140% | <= 0.086 | <= 15% | Sharpe declining over 5 evals |
| **Tag** | Test >= 2.569 | Test >= 144% | <= 0.060 | <= 14% | Must match or exceed V10 |

- **Annual return is the primary production metric.** A model that achieves 144%+ annual return with acceptable risk (DD < 15%, Turnover < 0.06) is ready for deployment.
- **Smoke uses val metrics** (shorter period, noisier). Prove-out uses full val. Full/tag uses test.
- **Trend requirement**: Val Sharpe must show upward trend over 5 consecutive evaluations during prove-out. Flat or declining Sharpe after 25% of steps = kill.
- All gates must use the SAME data distribution (all weekdays, same symbol set).

## Why This Must Be Pursued With Conviction

- V5 backbone has 2-5x better captured return than V3 (proven at backbone level)
- Single-day snapshot is the identified root cause of high turnover and signal instability
- 5-day temporal context gives the model trend visibility that V10 lacks
- Previous V13 failure was an integration bug (72-dim uncompressed input), not a fundamental flaw
- The conviction_analysis.md identified this as direction #3 (HIGH confidence, needs persistence)
- Every successful model tag required persisting through multiple failures — V13 deserves the same determination

## Violations

Any of the following is a violation of this conviction:

1. **No V13 portfolio model exists** — if `firstrate_portfolio/v13/` does not contain a working train.py that uses V5 temporal backbone with 5-day lookback
2. **No backbone compression** — if V13 feeds raw 72-dim V5 output directly into portfolio model without a learned projection layer
3. **Missing WH96 improvements** — if V13 does not include SH=96, WH=96, all overlay infrastructure, 10-component loss. Note: EMA smoothing implemented (α=0.3 reduced TO from 0.69→0.41). Next: α=0.1 for target TO<0.15.
3a. **LR above proven stability range** — V13 LEARNING_RATE must be <= 5e-5. Two collapses documented: LR=3e-4 collapsed step 82 (peak Sharpe 0.808), LR=1e-4 collapsed step 700 (peak Sharpe 0.965). Model stable only at LR ~3-5e-5. LR=3e-5 confirmed stable (Sharpe 0.376, no collapse). LR dimension EXHAUSTED.
3b. **Sharpe ceiling at current architecture** — Frozen backbone plateaus at Val Sharpe ~0.38 (41K) regardless of downstream changes. All 4 downstream-only changes exhausted. Backbone fine-tuning CONFIRMED: smoke #13b Val Sharpe **0.921** (2.4x frozen peak) at LR=1.05e-5. Collapse above LR=1.5e-5. Productive LR range: 3e-6 to 1.2e-5. Next: cap LEARNING_RATE at 1e-5.
3e. **Fine-tuning LR too high** — LEARNING_RATE=3e-5 proven too high for backbone fine-tuning (264K params). LR=1e-5 cap (smoke #14) prevented collapse but produced plateau at 0.43 with training loss → 0 (overfitting). Productive range REVISED to 1e-6 to 5e-6. The 0.921 peak from #13b was a warmup transient, not achievable stable performance.
3f. **Fine-tuning overfitting** — 264K params on 1000-symbol smoke subset overfits: training loss → 0.0, Val Sharpe flat 0.38-0.43. SOLVED by proj-only (66K params): train loss stable, Val 0.868. BACKBONE_UNFREEZE_LAYERS=0 is the correct setting.
3g. **Overlay degradation** — Overlays reduce pure Sharpe by 53% consistently. DD breaker ablation (#15c) had NO effect — vol scaling ALONE causes 53% destruction on 2020-2022 val period. Vol scaling benign on test (4% loss). Next: disable VOL_SCALE_ENABLED entirely, then recalibrate vol target for V13's concentrated portfolio.
3h. **No fixed random seed** — train.py MUST call `torch.manual_seed(42)`, `torch.cuda.manual_seed_all(42)`, `np.random.seed(42)`, `random.seed(42)` before model creation. Proven: #15c got 0.477 vs #15a's 0.868 with IDENTICAL config. Without seed, experiment comparison is meaningless. Reproducible baseline (#15d, seed=42): Val Sharpe 0.330. #15a's 0.868 was a 2.6x outlier.
3i. **Zero oracle correlation** — Smoke #15d proved oracle correlation ≈ 0 (val: -0.006, test: -0.001). The current cross-attention portfolio model CANNOT extract portfolio-relevant signal from backbone features. Training adds nothing (best step was 200/1400). MUST try fundamentally different portfolio architecture before further hyperparameter tuning.
3j. **Reproducible baseline is 0.330** — With fixed seed=42, proj-only at LR=3e-6, 1400 steps, all overlays off, Val Sharpe = 0.330. The 0.868 (#15a) and 0.523 (#15b) were unseeded outliers. 3.9x gap to smoke gate (1.28). Hyperparameter tuning on current architecture CANNOT close this gap.
3k. **Cross-attention model ABANDONED** — Experiment #16 proved raw backbone p_up ranking (Val 0.603) beats the learned model (0.330) by 1.8x. The cross-attention architecture over 72-dim features is fundamentally wrong for portfolio construction. The 8 scalar backbone outputs (score, p_big, p_up, q50-q99) carry the signal — the 64-dim embedding is noise for portfolio task.
3l. **Two signal regimes** — p_up = direction signal (strong val 2020-2022 volatile), score = magnitude signal (strong test 2023+ calm). Long-only p_up best balanced (Val 0.503, Test 0.523). Short side toxic on test (p_up L/S collapses to -0.75). A learned blend of both signals should outperform either alone.
3m. **Linear blend FAILED** — Experiment #17: LayerNorm(8) + Linear(8,1) = 25 params. Val Sharpe 0.278, KILLED at step 1250. WORSE than cross-attention baseline (0.330). Portfolio Sharpe loss gradient through 60-day windows with 1000 symbols is too noisy for <100 params. DD stuck at 78.9%. Sharpe loss is the wrong loss function for tiny models.
3n. **Portfolio Sharpe loss fails for tiny models** — Direct ranking works without gradients (#16, Val 0.603). Sharpe loss can't train 25 params (#17, Val 0.278). Sharpe loss can't train 41K params (cross-attention, Val 0.330, oracle corr ≈ 0). The portfolio Sharpe loss function is fundamentally problematic — noisy, non-convex, 60-day windows. Ranking loss CONFIRMED superior (#18, Val 0.369, oracle corr 0.006 with only 337 params).
3o. **Ranking loss MLP CONFIRMED**: Experiment #18: 337-param ranking MLP (pairwise margin loss) = Val 0.369, Test 0.530, oracle corr 0.006. Beats cross-attention (0.330, +12%) with 100x fewer params. First model with positive oracle correlation.
3p. **2-feature > 8-feature CONFIRMED, MARGIN LOSS SATURATES**: Experiment #19: 133-param ranking MLP with p_up+score only = Val 0.478 (29% better than 8-feature 0.369), oracle corr 0.0085. BUT: loss saturated at 0.1000 (= margin) from step 500 — identical metrics at ALL 6 eval points. Zero learning after 500 steps. Model is a fixed p_up sorter at 95% of heuristic (0.503). Pairwise margin loss with margin=0.1 creates a dead zone.
3q. **LOSS FUNCTION NOT THE BOTTLENECK**: Experiment #20: ListMLE (listwise loss, continuous gradients, loss varies 4.16-4.20) produces IDENTICAL results to pairwise margin (#19): Val 0.478, Test 0.589, Oracle 0.0085. Every metric matches to 6 decimals. The 133-param 2-feature architecture has a fixed ceiling at 0.478 regardless of loss. The model can only represent near-linear functions of p_up and score.
3r. **MODEL CAPACITY NOT THE BOTTLENECK**: Experiment #21: 2309-param MLP (hidden [64,32], ListMLE) produces IDENTICAL results to 133-param (#19/#20): Val 0.478, Test 0.589, Oracle 0.0085. 17x capacity increase learns the SAME solution. The optimal ranking function of p_up and score IS "sort by p_up" regardless of model expressiveness. Non-linear p_up×score interactions do NOT improve ranking. The 2-feature input space is the hard ceiling, not model capacity or loss function. MUST add features (regime context, temporal, market breadth) or change input representation entirely.
3s. **REGIME FEATURE MIXED RESULTS**: Experiment #22: p_up+score+regime_std (2375 params, ListMLE): Val 0.395 (BELOW 0.478), Test 0.952 (+62% over 2-feature). Regime (cross-sectional std of p_up) helps calm markets (test 2023+) but degrades volatile markets (val 2020-2022). Turnover 0.200 (too high). Oracle corr dropped to 0.004. Not a clean improvement — val is worse.
3t. **COMPOSITE SCORE IS ANTI-SIGNAL, q50 CONFIRMED**: #23a PROVED: p_up+q50 (Val 0.572, Test 0.634, Oracle 0.010) beats p_up+score (Val 0.478, Test 0.589, Oracle 0.0085) across ALL metrics (+20%, +8%, +18%). The 0.478 ceiling was a p_up-only artifact. q50 is the CONFIRMED default 2nd feature. NEVER use composite score for ranking.
3u. **FIRST LEARNED MODEL BEATS HEURISTIC**: #23a Val 0.572 > p_up heuristic 0.503 (+14%). Feature selection — not loss, capacity, or architecture — was the bottleneck for experiments #19-#22. With correct features, even 133 params can outperform direct ranking.
3v. **REGIME FEATURE IS NOISE WITH CORRECT FEATURES**: #23b (p_up+q50+regime, Val 0.449) is WORSE than #23a (p_up+q50, Val 0.572) by 22% on val, 19% on test, 70% on oracle corr, 2x on turnover. #22's +62% test improvement was regime compensating for score's anti-signal. With q50 providing actual signal, regime adds only noise and instability. Regime feature PERMANENTLY ABANDONED. Do NOT add regime_std to any ranking model.
3w. **133-PARAM p_up+q50 CEILING CONFIRMED (#23a-ext)**: 6000 steps produced Val 0.567 (BELOW #23a's 0.572). Val oscillates ±0.02 around 0.557 from step 500 onward. Model converges in ~500 steps — extended training provides zero benefit. 133-param p_up+q50 hard ceiling: ~0.57. Training duration is NOT a variable for ranking MLPs.
3x. **p_big REDUNDANT WITH p_up+q50 (#24)**: 167-param 3-feature model (p_up+q50+p_big) produces Val 0.562, BELOW 2-feature's 0.572. Test oracle corr NEGATIVE (-0.003 vs +0.010). p_big adds NO orthogonal signal for cross-sectional ranking. ALL 8 scalar feature combinations EXHAUSTED: score (anti-signal), p_big (redundant), regime (noise), q50 (only additive). Scalar features top out at Val ~0.57.
3y. **64-dim EMBEDDING WORSE THAN SCALARS (#25)**: 12,609-param MLP (LayerNorm(64)→128→32→1, dropout 0.3, WD 1e-2, ListMLE) on 64-dim temporal embedding: Best Val 0.535 (-6% vs p_up+q50's 0.572). Val DECLINED from 0.535→0.490 (mild overfitting despite regularization). Oracle corr 0.0098 ≈ scalars. Test oracle corr NEGATIVE (-0.002). Temporal within-stock patterns NOT useful for cross-sectional ranking. Scalars are distilled summaries already superior to raw embedding.
3z. **ENTIRE BACKBONE OUTPUT EXHAUSTED**: 31 experiments total. Scalars ceiling: Val 0.572 (p_up+q50, 133 params). Embedding ceiling: Val 0.535 (64-dim, 12K params). Hybrid ceiling: Val 0.485 (66-dim, 13K params). No backbone feature combination exceeds 0.572. Must fundamentally change approach (weekly rebalancing, attention portfolio, return prediction).
3ab. **ATTENTION PORTFOLIO FAILED (#27)**: 245-param self-attention (d_model=8, 1-head, p_up+q50, ListMLE) produced Val 0.236 (-59% vs ranking MLP's 0.572). Oracle corr NEGATIVE (-0.006 to -0.009 at all eval points). Loss essentially flat (4.18→4.13→4.18). Test Sharpe 0.965 is an artifact of 2023+ bull market (any long-only portfolio benefits). Cross-stock attention with 2 scalar features cannot form meaningful queries — there's no basis for "how does stock A relate to stock B" with just p_up and q50. Attention needs richer per-stock representations.
3ac. **RETURN PREDICTION FAILED (#28)**: 133-param MLP with Huber loss (delta=0.01) on actual next-day returns from p_up+q50. Val 0.384 (-33% vs ranking MLP's 0.572). Train loss dropped 100x (0.015→0.00014) but val Sharpe FLAT at 0.384 at ALL 6 evals — pure memorization, zero generalization. Return corr 0.0003 on val (zero). Turnover 0.002 (portfolio static — predicted returns near-constant across stocks). Oracle corr 0.004 (lower than ranking's 0.010). p_up+q50 predict direction (ranking ORDER) not return magnitude. Ranking is fundamentally the correct formulation for these features.
3ad. **ALL PORTFOLIO APPROACHES EXHAUSTED (36 experiments)**: Cross-attention (Val 0.330), ranking MLP (Val 0.572 ceiling), embedding (0.535), hybrid (0.485), weekly rebalancing (abandoned), attention portfolio (0.236), return prediction (0.384). No portfolio architecture, loss function, feature combination, temporal aggregation, or model capacity can exceed Val 0.572 using current V5 backbone outputs. The 3.4x gap to smoke gate (1.28) cannot be closed at the portfolio level. Only V5 backbone retraining with portfolio-aware objectives can change the feature ceiling.
3aa. **HYBRID EMBEDDING+SCALARS WORSE THAN BOTH (#25b)**: 12,869-param MLP (66-dim: embed+p_up+q50, dropout 0.3, WD 1e-2, ListMLE): Best Val 0.485 (-15% vs scalars, -9% vs embedding). Val declined 0.485→0.403 (overfitting). Embedding INTERFERES with scalar signal — 64 embedding dims overwhelm 2 scalar dims. Same capacity-hurts pattern as #23c. NEVER combine embedding with scalars in ranking MLP.
3d. **LR must scale with model size** — LR=3e-5 proven stable for 41K params but causes oscillation at 94K params. sqrt(params) scaling predicts LR≈2e-5 for 94K. Use LR=1e-5 (conservative). Never assume same LR works at different model sizes without unit test validation.
3c. **Loss simplification banned** — 3-component loss (Sharpe+Sortino+Turnover) produced Val Sharpe 0.271, WORSE than 10-component (0.376). Auxiliary losses (distill, concentration, winrate, entropy) provide useful gradient signal for learning. Never reduce below 10 components.
4. **Abandoned without prove-out** — if V13 is declared failed or abandoned without completing at least one prove-out run (1-3 hr) with the compression layer approach
5. **No dual metrics** — if V13 evaluation does not report both pure model and model+overlays metrics
6. **Stale V13 code** — if V13 code exists but uses old patterns (local trade_execution.py, close-only prices, missing exit slippage, no common module)
7. **V13 underperforms V10** — if V13 portfolio model with transformer 5-day lookback backbone does not outperform V10 portfolio model with single-snapshot backbone on pure Sharpe. The transformer backbone is proven superior at the backbone level (2-5x captured return). If V13 portfolio underperforms V10, the integration is wrong — debug and fix the integration, do not abandon. Iterate on compression layer, loss tuning, training configuration until V13 >= V10.
8. **Accepting V10 as ceiling** — declaring V10 WH96 as "final" or "ceiling" while V13 transformer backbone has not been properly integrated and proved out. The single-snapshot backbone is inherently limited. The transformer backbone has more signal. The project must persist until V13 proves this.
9. **Fraudulent smoke gate** — Smoke test passing on a different data distribution than prove-out. If smoke uses Friday-only dates, weekly rebalancing, or any data subset that makes the problem artificially easier than what prove-out runs, the smoke gate is invalid. Smoke MUST use the same day filtering and rebalancing frequency as prove-out. Proven failure: Friday-only smoke showed Sharpe 1.334, all-weekday prove-out showed 0.35.

## Runtime Behavioral Tests

9. **Model loads and produces output** — `torch.load('firstrate_portfolio/v13/models/.../best_model.pt')` must succeed. Model forward pass on dummy input must produce output of correct shape.
10. **Compression layer active** — Model's compression layer must reduce 72-dim backbone output to COMPRESSION_DIM. Verify by checking model parameter shapes: compression layer weight must be (COMPRESSION_DIM, 72).
11. **Dual metrics in results** — `training_results.json` must contain both top-level `val` dict AND `val_overlay` dict. Both must have `sharpe` field.
12. **Backbone cache valid** — Backbone precompute cache file (`.pt.zst`) must exist, be decompressible, and contain tensors with correct feature dimensions.
13. **Reproducible initialization** — Two consecutive unit test runs with same config must produce identical val Sharpe (±0.001). Grep for `torch.manual_seed` in train.py — must exist before model creation. Runtime: run unit test twice, compare val_sharpe from both runs. If difference > 0.001, seed is not working.
