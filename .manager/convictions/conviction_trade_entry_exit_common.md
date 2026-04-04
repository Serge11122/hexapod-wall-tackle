# PROJECT MUST: Refactor All Trade Execution to Common Module

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — blocks correctness of all reported metrics
**Created**: 2026-03-31

## Conviction

All model training, evaluation, and backtesting across the project MUST use `firstrate_common.trade_entry_exit_common` as the single source of truth for trade entry/exit logic, portfolio state management, return computation, and slippage application.

No model version may implement its own trade execution logic. No train.py, eval_only.py, or backtest_live.py may define or call local trade execution functions.

## Violations

Any of the following is a violation of this conviction:

1. **Local trade_execution.py** — Any model version folder containing its own `trade_execution.py` instead of importing from `firstrate_common.trade_entry_exit_common`
2. **Local get_period_return_fast()** — Any train.py defining its own return computation instead of using `compute_period_returns()` from the common module
3. **Local position update** — Any file calling `update_training_positions()` or `update_portfolio_state()` from a local module instead of `simulate_step_train()` / `simulate_step_backtest()` from common
4. **Local state vector** — Any file calling a local `get_portfolio_state_vector()` instead of `build_portfolio_state()` from common
5. **Local date lag** — Any file manually writing `dates[i-1], dates[i], dates[i+1]` instead of calling `date_lag()` from common
6. **Missing exit slippage** — Any train/eval path that applies entry slippage but not exit slippage
7. **Close-to-close returns** — Any return computation using close prices for execution instead of open prices via `PriceData` interface
8. **Local SlippageConfig/PortfolioState** — Any file defining its own trade dataclasses instead of importing `SlippageConfig`, `Portfolio`, `Position` from common
9. **Incomplete price data** — Any `prices.npy` or source pricing data that does not provide both `open` and `close` price columns as separate arrays. The common module requires `ArrayPriceData(prices_open, prices_close, ...)` with distinct open and close matrices. A single-column price file (e.g. close-only `prices.npy`) is a violation — it cannot support correct open-price execution or open-to-open return computation. FMP raw data provides `open, high, low, close, volume, vwap` per row. At minimum `open` and `close` must be extracted and stored as `prices_open.npy` and `prices_close.npy`.

## Why This Matters

- **14 duplicate trade_execution.py files** exist today — any bug fix must be applied 14 times
- **Exit slippage is missing** in train/eval — reported Sharpe is 5-10% optimistic
- **Close-to-close returns** don't match real execution (trades happen at open)
- **Inconsistent return timing** across train vs eval vs backtest makes metrics non-comparable
- **470 scattered callsites** make it impossible to verify correctness — common module reduces to ~60

## Common Module Location

```
firstrate_common/trade_entry_exit_common.py
```

### Functions to Use

| Purpose | Function | Modes |
|---------|----------|-------|
| Date indexing | `date_lag(dates, i)` | All |
| Portfolio state for model | `build_portfolio_state(portfolio, symbols, prices, feature_date, ...)` | All |
| Trade identification | `identify_trades(weights, symbols, portfolio)` | All |
| Period returns | `compute_period_returns(symbols, prices, trade_date, next_date)` | All |
| Train/eval step | `simulate_step_train(portfolio, weights, symbols, trade_date, next_date, prices)` | Train, Eval |
| Backtest step | `simulate_step_backtest(portfolio, weights, symbols, trade_date, next_date, prices)` | Backtest |
| Full simulation | `simulate_loop(dates, symbols_by_date, features_by_date, model_fn, ...)` | All |
| Metrics | `compute_metrics(returns)` | All |

### Data Interface

```python
from firstrate_common.trade_entry_exit_common import ArrayPriceData

price_data = ArrayPriceData(prices_open, prices_close, sym_to_idx, date_to_idx)
```

## Migration Reference

Full migration plan: `firstrate_common/trade_entry_exit_migration_plan.md`
Design specification: `firstrate_common/trade_entry_exit_new.md`
Current state analysis: `firstrate_common/trade_entry_exit_doc.md`

## Enforcement

The timer cycle arch and debug steps MUST check for violations of this conviction:
- Arch: reject any design that introduces local trade execution logic
- Debug: flag any file importing from local `trade_execution.py`
- Dev: migrate callsites to common module as part of each model version's work
- Timer2 deep analysis: flag launch of any script that imports local trade_execution

## Runtime Behavioral Tests

Static import checks catch wrong imports but miss broken integration. These runtime tests MUST also pass:

10. **Common module importable** — `from firstrate_common.trade_entry_exit_common import simulate_step_train, ArrayPriceData, SlippageConfig` must succeed without ImportError.
11. **Price data has open+close** — Load any `prices_open.npy` and `prices_close.npy` used by V13. Both must exist, have identical shape, and not be all-zeros.
12. **Slippage applied in output** — Run --unit-test for V13. Check that logged slippage values are non-zero (entry AND exit slippage both applied).
13. **Returns are open-to-open** — In unit test log, verify return computation references open prices, not close-only.

## Done When

- All 14 local `trade_execution.py` files deleted
- All train.py, eval_only.py, backtest_live.py import from `firstrate_common.trade_entry_exit_common`
- Open price data (`prices_open.npy`) built and used for execution
- Exit slippage applied in all modes
- Reported Sharpe reflects correct slippage and open-to-open returns
