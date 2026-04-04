# TensorEntry Code Analysis

## Overview
The `TensorEntry` class in `torch_glm_2d.py` (lines 180-250) is a metadata container and recursive traversal system designed to handle tensor parameter bounds. **However, it is currently unused in the codebase.**

## Issues Found

### 1. **UNUSED CODE - NEVER CALLED**
- `TensorEntry` is defined in `torch_glm_2d.py` but **not imported or used anywhere**
- `grep -r "TensorEntry"` returns only its definition file
- No methods (`get_bounds`, `assign_fields`, `save_template`, etc.) are invoked in the active code
- The main code uses `BodyTensor.get_lb_ub_lists()` instead (line 59-69 of `2d_wall_tackle.py`)

**Status**: Dead code, not causing errors because it's never executed.

---

### 2. **CRITICAL BUG: Infinite Recursion Risk in `__recursive_iterate`**

**Location**: Lines 186-202

```python
@staticmethod
def __recursive_iterate(obj, prefix=''):
    if not hasattr(obj, "__dict__"):
        return
    for field, value in vars(obj).items():
        if field.startswith('_'):
            continue
        if type(obj) == torch.Tensor or type(obj) == tvec2 or type(obj) == tquat2:
            continue
        if type(value) == TensorEntry:
            yield obj, field, value, prefix + field
        elif type(value) == list:
            for i, item in enumerate(value):
                yield from TensorEntry.__recursive_iterate(item, prefix=f'{field}[{i}].')
        else:
            yield from TensorEntry.__recursive_iterate(value)  # ← DANGEROUS
```

**Problem**: The base case at line 188-189 checks `if not hasattr(obj, "__dict__")` but this is insufficient.

**Scenarios where infinite recursion WILL occur**:

1. **Circular object references**: If object A contains reference to object B, and object B contains reference to object A:
   ```
   obj1.obj2 → obj2.obj1 → obj2.obj1 → ... (infinite)
   ```

2. **Self-referencing objects**: An object that refers to itself:
   ```python
   class Node:
       def __init__(self):
           self.parent = self
   ```

3. **Parent-child relationships**: Common in tree/graph structures where children reference parents.

**Why the current guard doesn't work**:
- `torch.Tensor`, `tvec2`, and `tquat2` DO have `__dict__`
- The guard at line 194 only checks if the CONTAINER object is one of these types, not the VALUE being traversed
- Built-in types (int, str, float, dict, tuple) still have `__dict__` in some Python implementations

---

### 3. **TYPE CHECKING ISSUES**

**Location**: Line 194-195

```python
if type(obj) == torch.Tensor or type(obj) == tvec2 or type(obj) == tquat2:
    continue
```

**Problems**:
- Uses `type(x) ==` instead of `isinstance()` - breaks with subclasses
- Only checks the CONTAINER type, not the VALUE type
- Doesn't handle other PyTorch types (Parameter, Buffer, etc.)
- Should be checking `value` not `obj` at this point:

```python
# Current (WRONG):
if type(obj) == torch.Tensor:  # Checks outer container
    continue

# Should be (or similar):
if type(value) in (torch.Tensor, tvec2, tquat2):  # Checks actual value
    continue
```

---

### 4. **INCORRECT RECURSIVE BASE CASE**

**Location**: Line 202 (else clause)

```python
else:
    yield from TensorEntry.__recursive_iterate(value)
```

This recursively processes ANY object that:
- Has a `__dict__`
- Is not a `TensorEntry`
- Is not a list

This means it will traverse into:
- Dataclass instances (like `Pose2d`)
- Built-in container objects
- Library objects with `__dict__` (numpy arrays have minimal `__dict__` but others may not)
- **Potentially circular objects**

---

### 5. **CACHE MUTATION BUG in `assign_fields`**

**Location**: Lines 236-250

```python
@staticmethod
def assign_fields(top_obj, tensor):
    if hasattr(top_obj, '__cache_assign_fields'):
        cache = getattr(top_obj, '__cache_assign_fields')
        for i in range(len(cache)):
            setattr(cache[i][0], cache[i][1], tensor[i])
    else:
        cache = []
        i = 0
        for obj, field, metadata, pretty_name in TensorEntry.__recursive_iterate(top_obj):
            print(f'{i=} {id(obj)=} {field=} {metadata=} {pretty_name=}')
            setattr(obj, field, tensor[i])  # ← Issue here
            cache.append((obj, field, metadata, pretty_name))
            i += 1
        setattr(top_obj, '__cache_assign_fields', cache)
```

**Problems**:
1. **Identity vs. State**: The cache stores object identities (`id(obj)`), not copies
   - If objects are garbage collected and recreated, the cache references dead objects
   - If the object graph changes, the cache becomes stale

2. **Silent Failure**: When using cached assignment, if the object hierarchy changed:
   - It still calls `setattr` on the OLD object references
   - Values are assigned to the wrong place
   - No error is raised - silent data corruption

3. **No Cache Invalidation**: The cache is never checked for validity
   - Should verify that `id(cache[i][0])` still refers to a live object

---

### 6. **UNUSED METHODS WITH LOGIC ERRORS**

**`save_template()` (lines 226-232)**:
```python
@staticmethod
def save_template(obj):
    class Template: pass
    result = Template()
    for field, value in vars(obj).items():
        if type(value) == TensorEntry:  # ← Only saves TensorEntry fields
            setattr(result, field, value)
    return result
```
- Only preserves `TensorEntry` fields, discarding structure
- Purpose unclear - not called anywhere

**`get_names()` (lines 221-223)**:
- Returns a generator of field names
- Never called; likely intended for debugging

---

## Summary Table

| Issue | Severity | Impact | Line(s) |
|-------|----------|--------|---------|
| Unused code | Medium | Dead weight, maintenance burden | All |
| Infinite recursion risk | **CRITICAL** | Will crash on circular refs | 186-202 |
| Wrong type checking | High | Doesn't guard against all cases | 194-195 |
| Weak base case | High | Traverses arbitrary objects | 202 |
| Cache staleness bug | **CRITICAL** | Silent data corruption on reuse | 236-249 |
| Unused methods | Low | Dead code | 221-232 |

---

## Current Usage in Active Code

The main code (`2d_wall_tackle.py`) uses a **simpler, safer approach**:

```python
class BodyTensor:
    N_SLOTS_BODY = 3
    N_SLOTS_LEG = 2
    N_LEGS = 4
    N_ENTRIES = N_SLOTS_BODY + N_LEGS * N_SLOTS_LEG
    
    @staticmethod
    def get_lb_ub_lists():
        # Manually constructs bounds lists
        lb = [-10.0] * N_SLOTS_BODY + ...
        ub = [+10.0] * N_SLOTS_BODY + ...
        return lb, ub
```

**This avoids the complexity of `TensorEntry` entirely.**

---

## Recommendation

The `TensorEntry` class appears to be:
1. **Experimental code** for a more generic tensor parameter system
2. **Incomplete** - has design flaws that weren't discovered because it's unused
3. **Overshadowed** by the simpler `BodyTensor.get_lb_ub_lists()` approach

**If used in the future**, it would need:
- Explicit recursion depth limit
- Visited set to detect cycles
- Proper type guards for values
- Cache invalidation strategy
- Rewrite of `assign_fields` to use shallow copies instead of identity
