# python-imports — Detail Reference

## Goal

Eliminate all `sys.path.insert()` and `sys.path.append()` hacks. Use proper Python package
installation so every module is importable by name from anywhere.

## Project Structure

This project uses a single `setup.py` at `/home/ubuntu/workspace/RLQuest/setup.py` with
`find_packages()` — it auto-detects all packages. The venv is at `firstrate_learning/.venv/`.

## Setup Steps

### 1. Verify setup.py at project root

`setup.py` already exists with `find_packages()`. It will pick up any directory that has
`__init__.py`. No manual package list needed.

### 2. Ensure every importable directory has `__init__.py`

```bash
# Check which packages are missing __init__.py
find /home/ubuntu/workspace/RLQuest -name "*.py" -not -path "*/.venv/*" \
  -not -path "*/site-packages/*" | xargs -I{} dirname {} | sort -u | \
  while read d; do [ ! -f "$d/__init__.py" ] && echo "MISSING: $d"; done
```

Key packages that must have `__init__.py`:
- `firstrate_portfolio/`
- `firstrate_learning/`
- `firstrate_rl/`
- `fmp_learning/`
- `fmp_processing/`
- `trade_learning/`

### 3. Install the project editable into the venv

```bash
firstrate_learning/.venv/bin/pip install -e /home/ubuntu/workspace/RLQuest
```

This registers all `find_packages()` packages into the venv's site-packages so they are
importable without path manipulation.

### 4. Remove sys.path hacks from source files

Files currently containing `sys.path` hacks (as of March 2026):
- `firstrate_portfolio/backtest_live.py`
- `firstrate_portfolio/train.py`
- `firstrate_learning/visualize.py`
- `firstrate_learning/backtest_live.py`
- `firstrate_learning/train.py`
- `firstrate_portfolio/visualize.py`
- `firstrate_rl/train.py`
- `fmp_processing/*.py`
- `fmp_learning/*.py`

**Remove** lines like:
```python
import sys
sys.path.insert(0, '/home/ubuntu/workspace/RLQuest')
sys.path.append('../')
```

**Replace** with direct imports:
```python
from firstrate_portfolio.trade_execution import SlippageConfig, PortfolioState
from firstrate_learning.model import AsymmetricUpsideModelWithLookback
```

## ❌ BAD: sys.path hack
```python
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from trade_execution import SlippageConfig
```

## ✅ GOOD: proper package import
```python
from firstrate_portfolio.trade_execution import SlippageConfig
```

## When to Apply This Skill

When you see any of these patterns in source files, remove them and use package imports instead:
- `sys.path.insert(...)`
- `sys.path.append(...)`
- `sys.path.extend(...)`
- `from .. import` when used with a path hack instead of proper package install

## Verification

After installing editable and removing hacks:
```bash
firstrate_learning/.venv/bin/python -c "from firstrate_portfolio.trade_execution import SlippageConfig; print('OK')"
firstrate_learning/.venv/bin/python -c "from firstrate_learning.model import AsymmetricUpsideModelWithLookback; print('OK')"
firstrate_learning/.venv/bin/python -c "from firstrate_portfolio.train import main; print('OK')"
```

All should print `OK` without errors.
