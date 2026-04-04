# General Rules (All Files)

## Python Environment

- Run via `firstrate_learning/.venv/bin/python` — never system python
- Import as packages: `from firstrate_common.trade_entry_exit_common import SlippageConfig`
- No `sys.path.insert()` or `sys.path.append()` — use `pip install -e .`

## Error Handling

- Raise errors explicitly — no silent `try-except` that continues
- Assert all function parameters at entry: type + range + not-None
- No optional parameters with fallback defaults
- No `or default_value` patterns
- Error messages must be clear and actionable

## Long-Running Scripts

- `nohup .venv/bin/python -u -m module > same_dir/script.log 2>&1 &`
- Log file: same directory, same base name, `.log` — no timestamps in filename
- ProgressTracker for any script running >30 seconds
- Progress file: same directory, same base name, `_progress.md` suffix

## V13 Transformer (Conviction)

- V13 must use learned compression layer (72→COMPRESSION_DIM) before symbol_mlp — never feed raw backbone output directly
- V13 must port all WH96 improvements: SH=96, WH=96, all overlays, 10-component loss
- V13 turnover fix is EMA smoothing (WEIGHT_EMA_ALPHA in config.py), NOT lambda scaling. α=0.3→TO=0.41, α=0.1→target. Never increase LAMBDA_TURNOVER above 0.15 again
- V13 EMA alpha tuning: change ONLY config.py WEIGHT_EMA_ALPHA per experiment — isolate the variable
- V13 smoke gate: MUST achieve BOTH turnover < 0.15 AND val Sharpe > 1.0 before prove-out — on ALL WEEKDAY data (same distribution as prove-out)
- V13 smoke MUST NOT filter to Friday-only dates — proven fraudulent (Friday Sharpe 1.334 → daily Sharpe 0.445). Smoke uses fewer quarters, all weekdays, same window size as prove-out
- V13 backbone cache MUST use sectioned storage (one .pt.zst per quarter + manifest.json) — no monolithic files, no gate-specific suffixes
- V13 eval must report BOTH pure model AND model+overlays metrics — never pure-only
- V13 train.py MUST use step-based training — no `for epoch in range(...)`, no epoch patience, no epoch LR scheduling
- V13 must use `torch.compile(model, mode='default')` for the portfolio model
- V13 run dirs must include gate marker files (gate_unit.json, gate_smoke.json, gate_prove.json) with source_files_hash
- V13 must use single run directory across gate levels — no duplicate dirs per run type
- Step-based refactor is COMPLETE — epoch-based training is permanently banned for V13
- V13 GPU timing must use `torch.cuda.Event(enable_timing=True)` not `time.perf_counter()` — fix before prove-out
- Deep analysis violations have gate levels: "smoke-blocking" (blocks smoke launch) vs "prove-out-blocking" (blocks prove-out only). tdeep must classify each violation by gate level. Only smoke-blocking violations count toward launch block for --smoke-test. Prove-out-blocking violations are listed as DEFERRED, not as violations, in the summary count.
- Any code change to train.py (even "I/O only" like cache format) invalidates the smoke gate — must re-run smoke before prove-out. No exceptions for "non-functional" changes.
- Before launching any gate test, verify working tree is clean (no uncommitted changes to module .py files). Uncommitted changes cause hash mismatch between gate marker and next verification. Commit or stash first.
- V13 precompute must create ProcessPoolExecutor ONCE outside the per-quarter loop — never per-quarter. Pool-in-loop wastes 1116 process creations (62 quarters × 18 workers).
- V13 smoke test MUST complete in <30 min. If cache precompute dominates, pre-build cache with `--build-cache` before launching smoke. Smoke steps should be 3000, not 6000.
- V13 WARMUP_STEPS must be 10-15% of total_steps, NEVER equal to total_steps. Proven: WARMUP_STEPS=3000 with 3000-step smoke = entire run is warmup, model never reaches cosine decay, collapses. Use WARMUP_STEPS=300 for smoke (3000 steps).
- V13 LEARNING_RATE must be validated via unit test before smoke. If model collapses (Val Sharpe drops >50% from peak for 3+ evals), LR is too high — reduce by 3x and re-test.
- V13 LEARNING_RATE must be <= 5e-5. Proven: 3e-4 collapsed at step 82, 1e-4 collapsed at step 700. Model finds signal at LR ~3-5e-5 during warmup but destabilizes above. Use 3e-5 as next target. LR_FLOOR = 10% of peak LR.
- V13 train.py must support `--build-cache` flag — runs only backbone precompute (no training), so cache cost is separated from smoke timer.
- V13 precompute MUST load V5 token cache (`firstrate_learning/v5/cache/tokens/`) instead of re-parsing raw CSV. V5 tokens are identical to what _process_symbol_file produces. This saves ~12 min per smoke, ~46 min per full. Proven: 12 min tokenization consumed 40% of smoke budget, causing kill at step 250. SMOKE-BLOCKING — must fix before next smoke.
- V13 smoke checkpoint_every MUST be 500 for frozen backbone, 200 for fine-tuning mode. Proven: 33 min frozen smoke with 2000 = zero checkpoints. Fine-tuning at 2.0s/step: 500 steps = 17 min, too long. 200 steps = 7 min between checkpoints.
- V13 fine-tuning smoke MUST use reduced step budget (1400 steps, not 3000). Live backbone inference is 2x slower (2.0s/step vs 0.5s/step frozen). 3000 steps at 2.0s/step = 100 min. Proven: smoke #13 killed at step 250/3000 (projected 114 min).
- V5 train.py test evaluation MUST load best_model.pt, not latest_checkpoint.pt. Proven: V5 smoke val peaked at step 6000 but test eval ran on final step 11324 (val had declined). Test results from wrong checkpoint are unreliable.
- V5 backbone smoke MUST be capped at 7000 steps, NOT full pass (11324 steps). Actual wall clock ~55 min at 7000 steps (training 0.163s/step = 19 min + torch.compile warmup 3 min + eval overhead 15+ min + pass-boundary evals 15+ min). The 30-min budget is unrealistic for 7000-step V5 smokes. Proven: w_rank=0.35 took 55 min despite normal 0.163s/step pace. Consider reducing to 5000 steps or accepting ~50 min as V5 backbone smoke reality. Best_step typically 2000-6000.
- V13 smoke eval frequency: every 3rd pass boundary, not every pass. Eval overhead was 49% of wall clock at 41 steps/pass.
- V13 MUST try architectural changes (loss simplification, model size, compression variant) after 3 consecutive hyperparameter-only failures. 8 failures on same architecture proves hyperparameter tuning alone cannot solve integration. See conviction_v13_experimentation_strategy.md.
- V13 loss simplification FAILED (Sharpe 0.27 vs 0.38 with 10-comp). Auxiliary losses HELP the small model — never reduce to fewer than 10 components. Model is capacity-starved, not gradient-confused.
- V13 model size increase (SH=192, WH=192, 94K params) FAILED at BOTH LR=3e-5 (oscillation) AND LR=1e-5 (slow decline 0.307→0.177). LR dimension EXHAUSTED for 94K. Model size approach abandoned. Do NOT try SH=128 or other intermediate sizes.
- V13 bottleneck compression FAILED: 72→16→38 peaked at 0.640 during warmup then collapsed to 0.205. All 4 downstream-only changes exhausted (loss, model size, two compression variants).
- V13 backbone fine-tuning: requires LIVE backbone inference (no precomputed cache — weights change during training). Dual optimizer: backbone LR=1e-6, portfolio LR=3e-5. Gradient clip backbone at 0.1. Backup V5 best_model.pt before training.
- V13 backbone fine-tuning CONFIRMED: smoke #13b produced Val Sharpe 0.921 (BEST EVER, 2.4x frozen peak) at LR=1.05e-5. Collapse above 1.5e-5 proves LR=3e-5 peak is too high. Next: cap LEARNING_RATE at 1e-5, cosine decay to 1e-6.
- V13 warmup-peak-then-collapse pattern: signal found during LR warmup (peak ~0.5-0.6), lost at full LR. Proven across ALL architectures with frozen backbone. Root cause: frozen backbone features aren't portfolio-optimized. Fine-tuning addresses this.
- V13 fine-tuning LR productive range: 1e-6 to ~5e-6 (REVISED from 3e-6 to 1.2e-5). Proven: smoke #14 peaked at 0.431 (LR=3.51e-6), declined above 5e-6. The #13b 0.921 peak was a warmup transient, not stable performance.
- V13 fine-tuning 50% warmup with LR=3e-5 FAILED: delayed collapse but did NOT prevent it. Peak 0.921 at step 246, collapse to 0.263 by step 492. Extending warmup is necessary but insufficient — must also cap peak LR.
- V13 fine-tuning with LR=1e-5 cap FAILED (smoke #14): plateau at 0.38-0.43, training loss → 0 = overfitting on 1000-symbol subset. Peak 0.431 at LR=3.51e-6, gradual decline as LR approached 1e-5. Capping prevented collapse but did not improve peak.
- V13 fine-tuning overfits on 1000-symbol smoke subset: 264K params learns to memorize training data (loss → 0) but cannot generalize. Root cause: too many unfrozen params for data size. Must reduce unfrozen layers (2→1) or increase regularization.
- V13 fine-tuning: 3 experiments completed (#13a, #13b, #14). Per experimentation strategy, next MUST include architectural change within fine-tuning approach (reduce layers, constant LR, different optimizer — not just LR tuning).
- V13 proj-only fine-tuning CONFIRMED BEST (smoke #15a): Val Sharpe 0.868, Test Sharpe 0.852 (BEST STABLE EVER). BACKBONE_UNFREEZE_LAYERS=0 (25K backbone params) + constant LR 3e-6 + WD 1e-3. No overfitting, excellent generalization (test/val=0.98). Proj-only is the correct fine-tuning granularity for V13.
- V13 overlays DESTROYING performance: pure Sharpe 0.868 → overlay Sharpe 0.410 (53% loss). Must investigate and fix overlay parameters before prove-out. Individual overlay ablation needed.
- V13 proj-only LR range: 3e-6 to 5e-6 TESTED. LR=3e-6 is val-optimal (0.868), LR=5e-6 is test-optimal (1.071) at 1400 steps. Higher LR learns slower on val, generalizes better to test, and produces higher turnover (0.126 vs 0.083). Both unconverged at 1400 steps.
- V13 overlay investigation MANDATORY before prove-out: overlays destroy 53-58% of pure Sharpe at BOTH LR=3e-6 and 5e-6. DD breaker ablation (#15c) had NO effect — vol scaling alone causes 53% destruction on 2020-2022 val period. Next: disable VOL_SCALE_ENABLED entirely.
- V13 train.py MUST call `torch.manual_seed(42)`, `torch.cuda.manual_seed_all(42)`, `np.random.seed(42)`, `random.seed(42)` before any model creation. Proven: #15c got 0.477 vs #15a's 0.868 with IDENTICAL config — only difference was random init. Without fixed seed, no experiment comparison is valid.
- V13 reproducible baseline (seed=42, proj-only, LR=3e-6): Val Sharpe 0.330. #15a's 0.868 was a 2.6x outlier from lucky init. True perf is 0.33, not 0.87.
- V13 oracle correlation ≈ 0 (val: -0.006, test: -0.001). Current cross-attention portfolio model CANNOT extract portfolio signal from backbone features. Training adds nothing (best step was 200/1400). MUST try fundamentally different portfolio architecture.
- V13 next experiments MUST be architectural — 20 experiments exhausted HP tuning and Sharpe-loss models.
- V13 experiment #16 PROVED: backbone scalar outputs (p_up, score, q90) directly beat the learned cross-attention model 1.8x on val. The 8 scalar features (indices 65-72) carry the portfolio signal — the 64-dim embedding is noise for portfolio task. Next models should use 8 scalars, not 72-dim.
- V13 two signal regimes: p_up = direction signal (strong val/volatile), score = magnitude signal (strong test/calm). A model that blends both adaptively should work across regimes. Long-only p_up eliminates toxic short side.
- V13 cross-attention portfolio model ABANDONED after 18 experiments. Oracle corr ≈ 0.
- V13 linear blend (25 params) FAILED (#17): Val 0.278, WORSE than cross-attention 0.330. Portfolio Sharpe loss is too noisy for <1000 params — gradient through 60-day Sharpe with 1000 symbols is essentially noise. Use RANKING LOSS (pairwise margin) for future learned models.
- V13 portfolio Sharpe loss BANNED for models <1000 params. Proven: 25 params (0.278), 41K params (0.330, oracle corr ≈ 0). Use ranking loss (pairwise/listwise) instead.
- V13 run-to-run variance without seed: ~2x (0.477 to 0.868 same config). Median of 3 proj-only runs ≈ 0.52. The 0.868 (#15a) was likely an upper outlier, not a reproducible result.
- V13 backbone has ONLY 1 temporal transformer block. BACKBONE_UNFREEZE_LAYERS=0 is proj-only (~25K params), >=1 is full temporal (~223K params). No intermediate option. Previous documentation of "2 layers" was incorrect.
- V13 LR scaling rule: when changing model size, adjust LR proportionally to 1/sqrt(new_params/old_params). Never assume same LR works at different model sizes without unit test validation.
- V13 loss components with lambda=0 MUST be skipped in computation (no oracle, no logit matching if disabled). Zero-weighted terms waste compute.
- V13 2-feature (p_up+score) ceiling is 0.478 regardless of model size (133→2309 params) or loss function (margin, ListMLE). Do NOT try larger models on 2 features. MUST add features or change input representation.
- V13 model capacity NOT the bottleneck: 17x increase (hidden [64,32]) produces identical results to single hidden layer. Non-linear p_up×score interactions do not improve ranking.
- V13 regime feature ABANDONED: #23b proved regime is noise with correct features (Val 0.449 vs p_up+q50's 0.572 = -22%). #22's +62% test was compensating for score anti-signal. NEVER add regime_std to ranking models.
- V13 composite `score` is ANTI-SIGNAL (ρ=-0.029) — NEVER use as ranking feature. Use p_up + q50 instead. The 0.478 "ceiling" was p_up-only; q50 (ρ=+0.019) may break it.
- V13 feature priority for ranking: p_up (index 2) + q50 (index 3). Score (index 0) is anti-signal. p_big, q75-q99 are noise.
- V13 p_up+q50 CONFIRMED (#23a): Val 0.572 (+20% over score-based 0.478), Test 0.634, Oracle 0.010. First learned model > p_up heuristic (0.503). p_up+q50 is the default feature pair for all ranking experiments.
- V13 pairwise margin loss with margin >= 0.1 is BANNED. Proven: loss saturates at 0.1000 (= margin) when all pairs correctly ordered within margin. #19 showed identical Val Sharpe (0.478) at all 6 evals from step 500 to 3000 — zero learning for 2500 steps. Use listwise loss (ListMLE, smooth NDCG) or margin < 0.01.
- V13 2-feature (p_up + q50) is DEFAULT for ranking experiments. REVISED: score is anti-signal (ρ=-0.029), replaced by q50 (ρ=+0.019). Previous p_up+score experiments (#19-#22) produced 0.478 ceiling but model ignored score. Test p_up+q50 first.
- V13 loss function NOT the bottleneck for 133-param model. Proven: ListMLE (#20) produces IDENTICAL results to pairwise margin (#19) — Val 0.478, Test 0.589, Oracle 0.0085. Loss varies (4.16-4.20, not constant) but model converges to same p_up-sorting. 133-param 2-feature ceiling is 0.478 regardless of loss. Next variable: model capacity (~2K params) or features.
- V13 architecture ceiling rule: if two different loss functions produce identical metrics on the same architecture, the architecture is the bottleneck. Do NOT try a third loss — change model capacity or feature count instead.
- V13 133-param p_up+q50 ceiling CONFIRMED at ~0.57 (#23a-ext): 6000 steps produced Val 0.567, model converges in ~500 steps. Extended training provides zero benefit. Training duration is NOT a variable for ranking MLPs.
- V13 ranking MLP convergence: 133-param model discovers optimal ranking in <500 steps. Val oscillates ±0.02 indefinitely after. Do NOT run extended training as a strategy — change features instead.
- V13 CAPACITY HURTS with p_up+q50 (#23c): 2309-param model Val 0.175 (-69% vs 133p's 0.572). Oracle corr NEGATIVE. Larger model overfits to test-period. 133-param near-linearity IS essential — prevents overfitting. Do NOT increase model capacity for 2-feature ranking. Add features to the 133-param model instead.
- V13 p_big REDUNDANT (#24): 167-param (p_up+q50+p_big) Val 0.562 vs p_up+q50's 0.572. Test oracle corr NEGATIVE (-0.003). ALL 8 scalar backbone features EXHAUSTED for ranking. Do NOT try other scalar combinations (q75, q90, q95, q99). Next: 64-dim temporal embedding with heavy regularization (#25).
- V13 scalar ranking ceiling: Val ~0.57 with p_up+q50 (133 params). No scalar combination, model size, loss function, or training duration can exceed this.
- V13 64-dim embedding WORSE than scalars (#25): Val 0.535 vs 0.572 (-6%). Temporal within-stock patterns not useful for cross-sectional ranking. Do NOT use embedding alone.
- V13 hybrid embedding+scalars WORSE than both (#25b): Val 0.485 (-15% vs scalars, -9% vs embedding). Embedding INTERFERES with scalar signal. NEVER combine embedding with scalars in ranking MLP.
- V13 ENTIRE backbone output EXHAUSTED (32 experiments): scalars ceiling 0.572, embedding ceiling 0.535, hybrid ceiling 0.485 (INTERFERENCE), weekly mean 0.265 (DESTROYED). No backbone feature combination or temporal aggregation exceeds 0.572. Remaining: weekly-last diagnostic (#26b), attention portfolio (#27), return prediction (#28).
- V13 weekly mean aggregation BANNED (#26a): Val 0.265 (-54% vs daily 0.572). Mean of 5-day p_up+q50 washes out ranking signal. Do NOT use mean aggregation of backbone features for weekly models.
- teta MUST NOT kill V5 prove-out based on negative CR at step 2000/13580. V5 best CR is at step 6000 (smoke), not step 2000. CR at 15% of training is not a kill signal. teta must compare metrics to SMOKE TRAJECTORY, not expect full performance at 15% progress. Proven: teta false-killed prove-out PID 231316 at step 2050 citing CR=-0.0119, but Val Sharpe was 0.6104 (healthy) and identical to smoke at same step.
- teta MUST NOT extrapolate time budget violations from steps < 200. torch.compile JIT warmup inflates first 50-100 steps by 5-6x. Proven: w_rank=0.4 killed at "35 min elapsed" but training pace was 0.14-0.17s/step after warmup (within budget). Wait until step 200+ before computing projected total time.
- After a premature kill is identified by tconv, kill_violations.md MUST be cleared before relaunch. Stale kill_violations.md causes cascading false kills. Proven: w_rank=0.05 killed by stale kill_violations from w_rank=0.1 run. w_rank=0.4 killed 3x — kill record never cleared between attempts.
- teta MUST use STEP-BASED time projection, not wall-clock elapsed time. Wall clock includes process startup, data loading, torch.compile JIT (50-100 steps at 5-6x inflation), and other overhead. Correct formula: (total_steps - current_step) * recent_pace_seconds + startup_overhead. NEVER use (elapsed_wall_time / current_step) * total_steps as this inflates by warmup. Proven: w_rank=0.4 wall clock showed 35 min but step-based projection was 20 min.
- V5 ListMLE w_rank monotonic improvement ENDED at 0.4: 0.2 (0.83x test) -> 0.3 (0.98x test) -> 0.4 (FAILED: val declining 0.636->0.608, killed at 56 min). Optimal w_rank between 0.3 and 0.4. Next: w_rank=0.35.
- V5 backbone experiments EXHAUSTED (10 experiments). Frozen w_rank=0.3 ListMLE is the WINNER (Test CR=0.01534, 0.98x baseline). Do NOT run more w_rank experiments. Move to prove-out.
- V5 proj-only fine-tuning WORSE than frozen for test: proj-only w_rank=0.3 (#9) Test CR=0.01492 (0.96x) vs frozen 0.01534 (0.98x). Gradient conflict through shared proj layers is structural.
- V5 proj-only w_rank=0.0 FAILED (#10): Val Sharpe 0.622, killed at step 4850. Pure base loss fine-tuning without ranking signal converges to weaker local minimum.
- V5 LR DISAMBIGUATION: config.py `learning_rate` (3e-4) is the main backbone LR for from-scratch/frozen training. `proj_lr` (3e-6) is ONLY for --proj-only fine-tuning. NEVER set learning_rate to 3e-6 — that is 100x too low for from-scratch training. Proven: commits 66f89e8/4717f99 incorrectly changed learning_rate to 3e-6, confusing it with proj_lr. All 10 winning experiments used learning_rate=3e-4.
- V5 config.py learning_rate MUST match v5_tag (3e-4) for frozen backbone runs. Before any smoke/prove-out launch, verify: `grep learning_rate v5_wrank/config.py` shows 3e-4.
- V5 `--resume` does NOT restore w_rank or rank_loss_type from checkpoint — they default to 0.0/listnet. MUST pass `--w-rank` and `--rank-loss-type` explicitly on every resume. Checkpoint config dict must include w_rank/rank_loss_type, and train.py must assert CLI args match checkpoint on resume. Proven: PID 345700 resumed with w_rank=0.0 instead of 0.3, training with wrong loss for ~200 steps before kill.
- teta kill_violations.md MUST verify claims against actual code before reporting. Proven: #10 kill report falsely claimed seed not fixed, but torch.manual_seed(42) existed at line 371. Always grep the actual source before asserting a code violation.
- teta MUST verify log freshness by reading the LAST LINE of the log file and checking its embedded timestamp, NOT by checking file mtime or cached reads. Proven: smoke PID 3495335 killed at step 6800/7000 while actively training (GPU 73%) because teta reported "log last updated 5+ hours ago" when log actually showed 09:44 UTC timestamps. False kills waste 25+ min of compute and require recovery.
- `firstrate_learning/cache/` (92G) is ORPHANED old v3/v10/v11 cache. No tagged model references it. V5 uses `v5/cache/tokens/`. Safe to clean when disk > 85%.
- V13 LR rules (<=5e-5) apply ONLY to V13 portfolio model. V5 backbone uses LR=3e-4 (same as v5_tag). teta MUST NOT apply V13 LR caps to V5 training. Proven: false kill of V5 smoke at step 1600/7000 wasted 13 min of compute.

## Tagged Model Protection (Conviction)

- NEVER modify `.py` files in a directory that has a `*_tag_*` copy. Changes go in new version folders.
- NEVER delete `best_model.pt` from tagged directories or source directories referenced by tags/downstream models.
- NEVER rebuild a cache that a tagged model references. New data fields → side-cache supplements joined at load time.
- Cache supplements go in `cache/supplements/<field_name>/` with per-chunk files matching main cache chunk names.
- Experiments on tagged models → create new folder (e.g., `v5_wrank/`, `v6/`), copy tagged code, modify the copy.
- Cleanup priority: failed experiments first, orphaned caches second, working tagged data NEVER.
- V5 `best_model.pt` must exist at `v5_tag/models/best_model.pt` AND at `v5/models/best_model.pt` (V13 references the latter).

## Trade Execution (Conviction)

- Never import from local `trade_execution.py` — always use `firstrate_common.trade_entry_exit_common`
- Never define local `get_period_return_fast()` — use `compute_period_returns()` from common module
- Price data must include both open and close: use `ArrayPriceData(prices_open, prices_close, ...)`
- Returns must be open-to-open via PriceData interface, not close-to-close
- Exit slippage must be applied in all train/eval/backtest paths
- Tagged versions (v10_tag_*, v11_tag_*) are exempt until migration Phase 3

## V5 Training CLI

- V5 `--prove-out` is a boolean flag with NO positional argument. Pass config via `--w-rank 0.3 --rank-loss-type listmle`. NEVER pass a run dir path after `--prove-out` — only `--resume RUN_DIR` accepts a positional path. Proven: prove-out launch command had a positional arg after `--prove-out` causing argparse error.
- V5 `--resume` takes BASENAME only (e.g., `run_20260404_182045_proveout`), NOT full path. `_find_run_dir_by_name()` searches within the models directory. Proven: PID 328447 failed with AssertionError when full path was passed.

## GPU Utilization

- GPU IDLE between experiments is a CRITICAL violation. If launch_commands.json has `"launched": false` and GPU is at 0%, tdev must launch immediately — no analysis, no refactoring, just launch.
- tconv MUST cross-check deep_analysis_results.md before declaring "0 violations." If deep analysis says BLOCK, tconv cannot override. Proven: cycle 292 declared 0 blockers while deep analysis had 3 (uncommitted changes, smoke gate invalidated, missing gate marker).
- tdev MUST NOT launch prove-out without valid gate_smoke.json for the EXACT config being proved out. A gate marker from a different config or old code does not count.
- tdev must verify GPU is running after launch: `nvidia-smi` > 0% utilization within 2 minutes of launch command.
- Before claiming a checkpoint is resumable, verify the run directory and checkpoint file EXIST on disk. Proven: cycle 300 referenced run_20260404_072833_smoke but that directory did not exist.
- Before referencing any run dir for resume or prove-out, verify run_meta.json config matches intended experiment (w_rank, rank_loss_type, learning_rate). Proven: cycle 317 referenced run_20260404_091736_smoke but it had w_rank=0.0/listnet/3e-6 (wrong config). Proven AGAIN: cycles 328+ referenced run_20260404_182045_proveout (w_rank=0.0/listnet) instead of run_20260404_181001_proveout (w_rank=0.3/listmle). When multiple run dirs exist with similar timestamps, ALWAYS verify run_meta.json — never assume the latest timestamp is correct.

## V5 Training Resume

- V5 `--resume` does NOT restore w_rank or rank_loss_type from checkpoint — these come from CLI args (default 0.0/listnet). MUST pass `--w-rank 0.3 --rank-loss-type listmle` explicitly on every resume command. Proven: prove-out PID 345700 ran with w_rank=0.0 because CLI args were omitted.
- Before launching any `--resume`, verify run_meta.json config matches intended CLI args. If mismatch, the resume will silently use wrong loss function.
- train.py MUST assert that CLI w_rank/rank_loss_type match checkpoint config on resume. Added as Task 1 in memory_dev.md.

## Crash Recovery

- Silent process exit (no error in log) requires immediate resume from latest checkpoint — do not investigate before relaunching. GPU idle time is wasted compute.
- If same step range crashes twice, then investigate (dmesg, CUDA errors, torch.compile recompilation). Once is transient, twice is a pattern.
- After any crash, verify checkpoint integrity before resume: `torch.load(checkpoint_path)` must succeed and global_step must be recent.

## torch.compile and Checkpoint Compatibility

- Checkpoint model_state_dict may have `_orig_mod.` prefix (saved from compiled model) or clean keys (uncompiled). Resume code MUST handle both cases.
- Correct pattern: load weights BEFORE torch.compile, strip `_orig_mod.` prefix during load. Then compile the loaded model. Never load compiled-prefix keys into a compiled OptimizedModule — the double-prefix fails.
- Proven: PID 551890 crashed because stripping code was applied AFTER torch.compile, producing clean keys loaded into compiled model expecting `_orig_mod.` prefix. Fixed in commit 7397e0e by moving load before compile.

## Safety

- Backup to `backups/` before overwriting models, configs, data
- Timestamp generated outputs: `filename_YYYYMMDD_HHMMSS.ext`
- Double-confirm git commits and destructive operations
- Never use `--no-verify`, `--force`, `-f` without justification
- Never auto-create `.md` documentation files unless explicitly requested
