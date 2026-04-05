# PROJECT MUST: Versioned Reference Protection — Never Overwrite Working Solutions

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — proven solutions must be preserved as immutable anchors

## Conviction

Versioned reference solutions (tagged directories, proven working outputs) and their referenced data (results, code, cached intermediates) are IMMUTABLE. Experiments and modifications MUST happen in new version folders, never by modifying tagged code or overwriting tagged data.

## Rules

### 1. Reference Solutions Are Immutable

- **Code**: Never modify source files in a versioned/tagged directory. If `solution_v1/` is tagged as working, changes go in `solution_v2/`.
- **Results**: Output files from proven solutions must never be deleted or overwritten.
- **Cached intermediates**: Cache files produced by tagged code must not be deleted if a tagged solution references them.

### 2. Experiments Go in New Folders

- New approaches or code changes → create a new version folder (e.g., `hexapod_v2/`)
- Never modify a tagged/proven directory
- Copy what you need, modify the copy
- The new folder gets its own output directories
- If the experiment succeeds → tag it → it becomes the new immutable anchor

### 3. Extend, Not Rebuild

When adding new capabilities to existing results:

**WRONG — rebuild everything:**
```
Modify working solver to add new constraint → breaks existing solution
```

**CORRECT — extend in new version:**
```
Copy working solver to new version folder → add constraint in copy → verify independently
```

### 4. Cleanup Rules

| Status | Action |
|---|---|
| Referenced by current tag | NEVER delete. Immutable. |
| Active experiment | Keep until experiment completes |
| Failed experiment, no tag | Safe to delete for space |
| Derived/supplemental data | Delete freely — can regenerate |
| Orphaned (no tag, no experiment) | Delete when disk > 85% |

### 5. Result Protection

- Proven outputs in tagged directories → NEVER delete
- Working solutions referenced by downstream code → preserve
- Failed experiment outputs → delete for space (keep metadata for history)

## Violations

1. **Modifying tagged source code** — Changing any file in a directory that has a corresponding tagged/versioned copy
2. **Deleting proven results** — Removing output files from a tagged directory
3. **Overwriting referenced data** — Modifying cached intermediates that a tagged solution depends on
4. **Experiment in tagged directory** — Running experimental code in a tagged directory instead of a new version folder
5. **No copy-before-modify** — Modifying source files without first copying to a new version folder
6. **Cleaning working data instead of failed data** — During disk cleanup, deleting tagged/proven outputs while keeping failed experiment data. Priority: failed first, orphaned second, working NEVER.
