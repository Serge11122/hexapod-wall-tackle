# Fail Fast, Fail Loud (Python & Shell)

No silent failures. No silent fallbacks. Errors must propagate.

## Rules

- **No `except: pass` or `except: continue`** — always re-raise or let the exception propagate
- **No fallback return values on error** — don't return `None`, `[]`, `False`, or a default when the real path failed; raise instead
- **No try/except that swallows and recovers silently** — if you catch, log the error AND re-raise
- **Validate inputs early with `assert msg` or explicit `raise ValueError`** — fail at the boundary, not deep in logic
- **No `or default` patterns as error masking** — `x = foo() or "default"` hides a None that should be an error
- **Shell scripts: `set -euo pipefail`** at the top; no `cmd || true` unless the failure is genuinely ignorable and commented why

## Pattern

```python
# Wrong
try:
    result = do_thing()
except Exception:
    result = fallback_value  # silent

# Right
result = do_thing()  # let it raise, or:
try:
    result = do_thing()
except SpecificError as exc:
    raise RuntimeError(f"do_thing failed: {exc}") from exc
```

The goal: failures surface immediately at their source with actionable messages, never masked by recovery logic that hides bugs.
