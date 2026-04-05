# PROJECT MUST: Runtime Behavioral Verification

**Status**: ACTIVE CONVICTION
**Priority**: HIGH — static code grep misses behavioral bugs

## Conviction

Every verification check MUST include three levels: static analysis (code grep), runtime behavioral verification, AND structural code analysis. Static checks catch missing code patterns. Runtime checks catch incorrect logic, missing files, broken state, and integration failures. Structural analysis reads function bodies and reasons about control flow, catching architectural anti-patterns that pass both grep and runtime spot-checks.

## The Pattern: Static → Runtime → Structural

For every static rule, derive a runtime behavioral test:

| Static Check | Runtime Behavioral Test |
|---|---|
| "Has bounds checking" (grep for assert) | Optimizer actually respects bounds at runtime (check output tensor values) |
| "Has convergence check" (grep for tolerance) | Optimizer converged (final loss < threshold, optimality < 1e-3) |
| "Has output save" (grep for savefig) | Output file exists on disk and is non-empty |
| "Uses correct constraints" (grep for constraint) | Constraint violation = 0 in optimizer result |
| "Fail-fast validation" (grep for assert) | Quick import + init doesn't crash (< 10s) |

## Static → Runtime → Structural Conversion Table

| Static Check | Runtime Check | Structural Check |
|---|---|---|
| "Uses bounds" (grep) | "Output within bounds" (check values) | "Bounds applied before and after optimizer step" (read function) |
| "Has ground constraint" (grep) | "No leg penetrates ground" (check y-values) | "Constraint checked for ALL legs, not just free legs" (read loss function) |
| "Saves output" (grep) | "PNG file exists" (ls) | "Save happens after all computation, not before early return" (read control flow) |
| "Warm-starts from previous" (grep) | "Initial loss < random init loss" (check) | "Previous solution actually passed as init, not hardcoded zeros" (read init code) |

## Structural Analysis Checks

Structural analysis reads the actual function body and reasons about control flow. It catches:

- **Missing constraints** — optimizer has bounds on some variables but not others (e.g., body constrained but leg endpoints unconstrained)
- **Stale state** — values computed from a previous step used without update (e.g., target positions from old body pose)
- **Dead code paths** — early returns that skip important computation (e.g., savefig after a return statement)
- **Wrong variable scope** — checking the container type instead of the value type, or constraining the wrong variable

## Runtime Test Categories

1. **File existence** — expected output, checkpoint, config files exist on disk
2. **File validity** — files are not empty, not corrupt, can be loaded
3. **State consistency** — optimizer output satisfies stated constraints (bounds, ground contact)
4. **Quick execution** — unit test completes without crash or hang (< 30s timeout)
5. **Mathematical validity** — forward kinematics produce physically plausible poses (leg lengths preserved, no penetration)
6. **Cross-component** — upstream output is valid before launching downstream computation

## Test Execution Rules

- Each behavioral test MUST complete in < 30 seconds
- Tests run IN ADDITION to static checks, not instead of
- Behavioral failures block launch
- Test results reported as BEHAVIOR_PASS / BEHAVIOR_FAIL with evidence

## Violations

1. **Static-only checks** — Verifying only that code patterns exist (grep) without runtime behavioral confirmation
2. **No file existence verification** — Proceeding when expected input/output files have not been verified to exist on disk
3. **No constraint verification** — Running optimizer without checking that output satisfies bounds and constraints
4. **No structural analysis** — Approving code without reading key functions and checking control flow for anti-patterns (stale state, dead code, wrong scope)
5. **Missing behavioral test for proven gap** — When a behavioral bug is discovered, the corresponding check MUST be added within the same cycle
6. **Cross-component rule misapplication** — Applying rules from one subsystem to another without verifying they apply (e.g., applying body constraints to leg joints)
