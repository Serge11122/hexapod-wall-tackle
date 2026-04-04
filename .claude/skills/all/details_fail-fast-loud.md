# fail-fast-loud — Detail Reference

## Core Principles

1. **Raise errors explicitly** - Never use try-except blocks that silently continue
2. **Validate inputs early** - Use assertions at function entry to validate all parameters
3. **No default or optional parameters** - Use assertions instead of default values
4. **No fallback values** - Never provide silent defaults when operations fail
5. **Assert types and ranges** - Validate input types and value constraints immediately
6. **Fail at the source** - Catch and raise errors where they originate

## Code Examples

### ❌ BAD: Silent try-catch
```python
try:
    value = parse_json(input_str)
except:
    value = None  # Silent failure continues downstream
```

### ✅ GOOD: Explicit error handling
```python
value = parse_json(input_str)
assert value is not None, "Failed to parse JSON: " + input_str
```

---

### ❌ BAD: Optional parameters with fallback
```python
def calculate_roi(investment=None, returns=None):
    if investment is None or returns is None:
        return 0  # Silent default
    return (returns - investment) / investment
```

### ✅ GOOD: Assert required parameters
```python
def calculate_roi(investment: float, returns: float) -> float:
    assert investment is not None, "investment required"
    assert returns is not None, "returns required"
    assert investment > 0, f"investment must be > 0, got {investment}"
    assert returns >= 0, f"returns must be >= 0, got {returns}"
    return (returns - investment) / investment
```

---

### ❌ BAD: Fallback values on failure
```python
price = fetch_price() or default_price  # Silent fallback
status = api_call() or "unknown"        # Silent fallback
```

### ✅ GOOD: Validate response immediately
```python
price = fetch_price()
assert price > 0, f"fetch_price() returned invalid price: {price}"

status = api_call()
assert status in ['success', 'pending', 'failed'], f"invalid status: {status}"
```

---

### ❌ BAD: Type confusion
```python
def divide(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return 0  # Silent error
```

### ✅ GOOD: Type and range assertions
```python
def divide(a: float, b: float) -> float:
    assert isinstance(a, (int, float)), f"a must be numeric, got {type(a)}"
    assert isinstance(b, (int, float)), f"b must be numeric, got {type(b)}"
    assert b != 0, "b cannot be zero"
    return a / b
```

## When to Apply

- **Data processing & transformation** - Validate all inputs and intermediates
- **API integration** - Assert response format and content
- **Configuration loading** - Ensure all required fields are present
- **Business logic** - Validate preconditions before operations
- **Any function entry point** - Assert all parameters meet requirements

## Exceptions

- ✓ Use context managers (`with` statements) for resource cleanup
- ✓ Standard library iteration (`for`/`while`) is safe without assertions
- ✓ Third-party libraries may have their own error patterns
- ✗ Never use silent try-except for control flow

## Validation Checklist

Before committing code:
- [ ] No try-except blocks catching exceptions silently
- [ ] All function parameters validated with assertions
- [ ] No optional/default parameters without validation
- [ ] No fallback values (no "or default_value" patterns)
- [ ] Type assertions on all inputs
- [ ] Range assertions on numeric inputs
- [ ] State assertions before operations
- [ ] Error messages are clear and actionable
