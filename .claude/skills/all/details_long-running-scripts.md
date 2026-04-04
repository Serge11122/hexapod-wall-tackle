# long-running-scripts — Detail Reference

## Goal

All long-running Python scripts must use `nohup` + `-u` (unbuffered) and pipe output to a `.log`
file co-located with the script, using the script's own base name — no timestamps, no suffixes.

## Pattern

```bash
nohup firstrate_learning/.venv/bin/python -u -m <module> > <script_dir>/<script_name>.log 2>&1 &
```

- `nohup` — keeps the process alive after the shell exits
- `python -u` — unbuffered stdout/stderr so lines appear in the log immediately
- `> path/to/script.log 2>&1` — both stdout and stderr go to the log
- `&` — run in background

## Log File Naming

| Script | Log file |
|--------|----------|
| `firstrate_learning/train.py` | `firstrate_learning/train.log` |
| `firstrate_portfolio/train.py` | `firstrate_portfolio/train.log` |
| `firstrate_learning/backtest_live.py` | `firstrate_learning/backtest_live.log` |
| `firstrate_portfolio/backtest_live.py` | `firstrate_portfolio/backtest_live.log` |
| `firstrate_learning/visualize.py` | `firstrate_learning/visualize.log` |

Rule: **same directory, same base name, `.log` extension. Never add timestamps or suffixes.**

## ❌ BAD
```bash
# Wrong: timestamp suffix
nohup python train.py > train_20260312_010924.log 2>&1 &

# Wrong: system python (no -u, wrong venv)
python train.py > train.log &

# Wrong: no nohup (process dies when shell exits)
firstrate_learning/.venv/bin/python -u -m firstrate_learning.train > firstrate_learning/train.log 2>&1 &

# Wrong: log in wrong location
nohup firstrate_learning/.venv/bin/python -u -m firstrate_learning.train > train.log 2>&1 &
```

## ✅ GOOD
```bash
nohup firstrate_learning/.venv/bin/python -u -m firstrate_learning.train \
    > firstrate_learning/train.log 2>&1 &

nohup firstrate_learning/.venv/bin/python -u -m firstrate_portfolio.train \
    > firstrate_portfolio/train.log 2>&1 &

nohup firstrate_learning/.venv/bin/python -u -m firstrate_learning.backtest_live \
    > firstrate_learning/backtest_live.log 2>&1 &
```

## Checking Progress

```bash
tail -f firstrate_learning/train.log
tail -20 firstrate_portfolio/train.log
```
