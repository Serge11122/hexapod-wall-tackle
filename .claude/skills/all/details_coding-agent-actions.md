# coding-agent-actions — Detail Reference

## Core Rules

1. **Never auto-create documentation** - Only create .md files if the user explicitly requests them
2. **Always activate .venv** - Verify virtual environment before running any Python code
3. **Backup important files** - Create backups before overwriting models, configs, or data
4. **Timestamp all outputs** - Generated files use format: `filename_YYYYMMDD_HHMMSS.ext`
5. **Double-confirm all commits** - Show changes and ask for confirmation twice
6. **Double-confirm destructive ops** - Always confirm before delete, reset, or force operations
7. **Never skip safety checks** - Don't use `--no-verify`, `--force`, `-f`, or similar flags

## Documentation Rule

❌ **BAD:** Implement feature, auto-create README.md, DESIGN.md, API.md
✅ **GOOD:** Implement feature. Only create docs if user asks.

Exception: Docstrings and comments in code are fine without asking.

## Virtual Environment Rule

Before running Python code:
1. Check if `.venv` exists in the project
2. Verify it has `bin/python3` executable
3. Run using `firstrate_learning/.venv/bin/python script.py`

❌ **BAD:** `python3 script.py` (uses system Python)
✅ **GOOD:** `firstrate_learning/.venv/bin/python script.py`

## Backup Before Overwrite Rule

For important files (models, configs, data):

```bash
mkdir -p backups
cp file backups/file_$(date +%Y%m%d_%H%M%S).bak
# Then proceed with new version
```

Important files:
- ✓ Models (*.pt, *.pth, *.h5)
- ✓ Outputs (*.json, *.csv, *.npz)
- ✓ Config files
- ✓ Trained weights
- ✗ Temp files (.tmp, .cache)
- ✗ Build outputs (*.o, *.pyc)

## Timestamp Rule

All generated outputs must have timestamps.

**Format:** `filename_YYYYMMDD_HHMMSS.ext`

```python
from datetime import datetime
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
output_path = f"results_{timestamp}.json"
```

## Git Commit Confirmation Rule

Before committing:

1. Show what will be committed: `git status && git diff`
2. First confirmation: "Ready to commit? Here's what will be committed:" — wait for response
3. Second confirmation: "Double-confirm? This will create commit: [message]" — wait for response
4. Only then commit

❌ **BAD:** Auto-commit after tests pass
✅ **GOOD:** Ask, show diff, ask again, then commit

## Destructive Operations Rule

Before any destructive operation (delete, reset, force):

1. Explain: What will be deleted/modified?
2. First ask: "Is this OK?"
3. Second ask: "Are you sure? This is permanent."
4. Only then proceed

Destructive operations: `git reset --hard`, `rm`, `rm -rf`, `git checkout .`, dropping tables, clearing user data caches.

## Safety Flags Rule

Never use without explicit justification:
- ❌ `git commit --no-verify`
- ❌ `git push --force`
- ❌ `pip install --no-deps`
- ❌ `rm -f`
- ❌ `eval()` with user input

If hooks fail: investigate why → fix the issue → commit normally.
