# General Rules (All Files)

## Python Environment

- Run via `.venv/bin/python` at repo root — never system python
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

## Diagnostic Scripts

- Any out-of-band diagnostic eval script (e.g., `diag_*.py`) reproducing a train-time eval metric MUST either (a) import the train.py `_evaluate` helper directly, or (b) include a comment block quoting the train.py loader construction + autocast + metric-reduction code verbatim, demonstrating per-flag parity.
- A diagnostic eval script producing a metric differing from the train-time recorded value by > 0.02 absolute on the same checkpoint × split is presumed broken and MUST NOT be cited as evidence until the divergence is localized.

## Model Naming Convention

- New backbone dirs under `firstrate_learning/` use prefix `vb<N>`. New portfolio dirs under `firstrate_portfolio/` use prefix `vp<N>`.
- Forward-only — existing non-prefixed dirs (v1–v11, v5_tag, v10_tag_*, etc.) stay as-is.

## Tagged Model Protection

See `conviction_tagged_model_protection.md` for the full spec. Key rules:
- NEVER modify `.py` files in a directory that has a `*_tag_*` copy — changes go in new version folders
- NEVER delete `best_model.pt` from tagged directories or source directories referenced by downstream models
- NEVER rebuild a cache that a tagged model references
- NEVER create a tag unless test metrics EXCEED the current production baseline

## Trade Execution

See `conviction_trade_entry_exit_common.md` for the full spec and violation list. Key rules:
- Never import from local `trade_execution.py` — always use `firstrate_common.trade_entry_exit_common`
- Price data must include both open and close: use `ArrayPriceData(prices_open, prices_close, ...)`
- Returns must be open-to-open via PriceData interface, not close-to-close
- Exit slippage must be applied in all train/eval/backtest paths

## Safety

Autonomy contract: `conviction_autonomy_envelope.md`. Operational discipline:
- Backup to `backups/` before overwriting models, configs, data
- Timestamp generated outputs: `filename_YYYYMMDD_HHMMSS.ext`
- Never use `--no-verify`, `--force`, `-f` without justification (a tconv conviction edit counts)
- Never auto-create `.md` documentation files unless explicitly requested

## Model-Specific Empirical Findings

V13 (SUPERSEDED) and V5 (experiments concluded 2026-05-01) empirical findings, CLI quirks, teta kill lessons, crash recovery patterns, and GPU notes: see `todo/reference/v13_v5_empirical.md`.
