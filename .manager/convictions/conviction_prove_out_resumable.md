# PROJECT MUST: Progressive Testing Chain — Resumable, Incremental, No Duplicate Work

**Status**: ACTIVE CONVICTION
**Priority**: CRITICAL — prevents hours of wasted compute from untested failures

## Conviction

When implementing or modifying any component in a chain of dependent modules, ALL affected downstream components must be tested incrementally before running long processes. Test the shortest runs first. Only escalate to longer runs after shorter runs pass on ALL affected components.

Every test level must be resumable and build on the previous level's work. No duplicated computation.

## The Chain Rule

For any change to component C in a chain A → B → C → D:

```
1. Quick test C                         (<2 min)
2. Quick test D (uses C's output)       (<2 min)
   ALL quick tests pass? →
3. Smoke test C                         (<30 min)
4. Smoke test D (uses C's smoke output) (<30 min)
   ALL smoke tests pass? →
5. Full run C                           (hours)
6. Full run D (uses C's full output)    (hours)
```

If step 2 fails, do NOT proceed to step 3. Fix C and restart from step 1.

### Hexapod Example

For gait optimization: single-phase solve → 2-phase gait → 4-phase animation → multi-obstacle sequence

```
1. Quick: single leg IK solve (<10 sec)
2. Quick: body + 4 legs, 1 phase (<30 sec)
3. Smoke: 2-phase gait with obstacle (<5 min)
4. Full: complete multi-phase animation
```

## Resumable Progressive Runs — No Duplicate Work

Each test level MUST resume from the previous level's result, not start from scratch.

### Directory Design

Each experiment gets ONE directory. All test levels run inside the same directory.

```
output/
├── exp_20260405_gait_v1/
│   ├── experiment.json        # describes: config, hypothesis
│   ├── phase_1_result.json    # phase 1 optimizer output
│   ├── phase_2_result.json    # phase 2 optimizer output
│   ├── gate_quick.json        # marker: quick test passed
│   ├── gate_smoke.json        # marker: smoke test passed
│   └── hexapod_wall_tackle.png
```

### Gate Marker Files

Each `gate_*.json` contains:
```json
{
  "gate": "smoke",
  "passed": true,
  "timestamp": "2026-04-05T12:00:00",
  "phases_completed": 2,
  "metrics": {"final_loss": 0.57, "constraint_violation": 0.0},
  "source_files_hash": "sha256 of relevant .py files"
}
```

The `source_files_hash` invalidates the gate if any source file changes.

## Violations

1. **Skipping downstream tests** — Modifying component C and running full computation without first quick-testing downstream components that depend on C's output
2. **Skipping upstream verification** — Running a downstream component without verifying upstream output exists and is valid
3. **Escalating before all pass** — Running smoke tests when any quick test hasn't passed. Running full when smoke hasn't passed.
4. **Running full without smoke** — Launching long computation without all components passing shorter tests
5. **No resumability** — Running full computation without the ability to resume from checkpoint
6. **Testing only the modified component** — Changing solver code and only testing the solver, without testing visualization that consumes its output
7. **Stale gate after code change** — Launching a test level when source files changed since the previous gate passed. Must re-run from quick test.
8. **Duplicate experiment directories** — Creating new directories for the same experiment variation instead of continuing in the existing one
9. **Recomputing cached intermediates** — Computing an expensive result that was already cached from a previous test level instead of loading from cache
10. **Continuing despite regression** — If smoke test metrics are worse than previous working version, do NOT escalate. Fix first.
11. **Running longer tests despite early failure signs** — If quick test shows problems (divergence, constraint violations), do NOT proceed to smoke hoping it will recover. Fix first.
