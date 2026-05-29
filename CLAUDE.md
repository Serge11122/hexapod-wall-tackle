# Project Standards

These rules are **always active**. Every script and code change must comply.

---

## What belongs in this file (routing gate)

**CLAUDE.md is ONLY for universal, code-time constraints active on every file change.**

- Universal rules (U1–U9), naming conventions, safety, environment, gate budgets
- Short pointers to rule/conviction/skill files for deeper specs

**Does NOT belong here:**
- Experiment results or model-specific empirical findings → `conviction_signal_quality.md` § Archived Empirical Findings or `todo/reference/`
- PTSA task details or protocol → `conviction_ptsa.md`
- Skill execution steps → `.claude/skills/<skill>/SKILL.md`
- Detailed training or data-pipeline patterns → `.claude/rules/training.md` / `data-pipeline.md`
- Timer-cycle outputs (findings, metrics, task lists) → `.manager/memory_dev.md`, convictions

**Write authority:** Only the user may edit CLAUDE.md. `tconv` MAY NOT edit CLAUDE.md — it writes to convictions, rules, and skills only. `tdev_inline` MAY NOT edit CLAUDE.md. Violations of this routing gate are a conviction breach.

---

## Python Environment

- Always use `.venv/bin/python` at the repo root — never system `python3`
- The venv uses `include-system-site-packages = true` to inherit system torch (CUDA build)
- Import packages properly — no `sys.path` hacks. Install editable: `.venv/bin/pip install -e .`

---

## Universal Script Rules (U1–U9) — apply to every Python file

**U1. No Python loops over data items** — no `for` loops over samples/dates/rows/symbols in dataset-building, feature-computing, or record-processing functions. Use numpy fancy indexing, broadcasting, `np.argsort`, `np.unique`. Proven: PTSA-X/Y triple-nested Python loops → 104-min builds.

**U2. Correct array axis semantics** — `prices_raw.dat` shape `(8766, 4025, 8)`: axis 0 = **SYMBOLS**, axis 1 = **DATES**. Correct: `prices[sym_idx, date_idx, field]`. NEVER index dates on axis 0. Proven: axis swap → IC=0.0014 (near zero) vs correct IC=0.046.

**U3. Denominator floor in normalizations** — any division by `std` or `sigma` MUST use `max(std, 0.01)` or `np.clip(result, -10, 10)` post-divide. `std + 1e-6` alone is insufficient. Proven: z-score overflow → inf/nan → IC=nan.

**U4. Explicit error handling** — never `except Exception: continue` or `except: pass`. Re-raise, or log with a counter. Proven: silent suppressor dropped dozens of symbols with no error signal.

**U5. Unit-test mode** — every output-producing script MUST implement `--unit-test` (< 2 min, minimal data, same output schema, non-degenerate values, writes `gate_unit.json`).

**U6. Output contract in launch entries** — every `launch_commands.json` entry MUST include `output_contract`, `requires_gpu`, `compute_profile` (`cpu_bound` | `gpu_bound` | `borderline`), and `max_step_duration_s`. tdeep Mode A blocks entries missing these fields.

**U7. GPU break-even analysis** — any script with torch neural components MUST estimate FLOPs per forward pass. If FLOPs < 10M and no cross-symbol attention over N_syms > 500, set `cpu_bound` or `borderline` — NOT `gpu_bound`. See tdeep step 7h.

**U8. Performance contract alongside output contract** — every `launch_commands.json` entry for a training script with an eval loop MUST include `eval_wall_budget_s` (max acceptable wall-clock per eval call). Derivation: `SMOKE_WALLCLOCK_MAX_S / (SMOKE_STEPS / EVAL_EVERY_STEPS) × 0.5`. tdeep Mode A step 7i projects actual smoke eval cost from unit-test phase timings and blocks if it exceeds budget. Proven: P6 smoke had each eval take 610s × 32 evals = 19,520s vs 3,600s budget due to U1 violations in shared libraries.

**U9. Shared-library U1 violations are tracked violations** — U1 violations in `firstrate_common/*.py` called during execution are violations against the importing script's performance contract. tdeep Mode A step 7i scans imported shared libraries. Violations → `SHARED_LIB_U1_WARN` + mandatory remediation task. A shared-library module with open U1 remediation tasks BLOCKS subsequent smoke launches of any script that imports it.

---

## Pre-Run Validation Gate Sequence — MANDATORY

No script runs at full scale without passing all gates in order:

| Gate | Flag | Budget | Writes |
|---|---|---|---|
| Unit test | `--unit-test` | < 2 min | `gate_unit.json` |
| Smoke test | `--smoke-test` | < 30 min (training), < 5 min (analysis/probe), < 2 min (data) | `gate_smoke.json` |
| Prove-out | `--prove-out` | < 3 hr — cap steps if needed | `gate_prove.json` |
| Full run | `--full` | hours+ | — |

**Each gate must pass before the next launches.** See `.claude/rules/training.md` for training-specific details.

---

## Safety and Operational Discipline

Autonomy contract: `.manager/convictions/conviction_autonomy_envelope.md` — single source of truth for loop authority.

- Backup models/configs/data to `backups/` before overwriting
- Timestamp generated outputs: `filename_YYYYMMDD_HHMMSS.ext`
- Never use `--no-verify`, `--force`, `-f` without explicit justification (a tconv conviction edit counts)

---

## Model Naming Convention (Forward-Only)

- New backbone directories under `firstrate_learning/` → prefix `vb<N>` (e.g., `vb6_*/`, `vb7_*/`)
- New portfolio directories under `firstrate_portfolio/` → prefix `vp<N>` (e.g., `vp13/`, `vp14_*/`)
- Existing non-prefixed dirs (`v1/`–`v5/`, `v5_tag/`, `v10/`, `v11/`, etc.) stay as-is — do NOT rename
- Module paths must match directory names: `vp13/` → `firstrate_portfolio.vp13.*`

---

## Training Script Essentials

Full spec in `.claude/rules/training.md`. Mandatory non-negotiables:

- **AMP + FP16**: always `torch.amp.autocast('cuda', dtype=torch.float16)` + `GradScaler`. No exceptions.
- **Fixed seed**: `torch.manual_seed(42)`, `torch.cuda.manual_seed_all(42)`, `np.random.seed(42)`, `random.seed(42)` before model creation. Seed from `--seed INT` CLI flag, emitted to `run_meta.json`.
- **Test eval uses `best_model.pt`**, not `latest_checkpoint.pt`.
- **torch.compile**: `torch.compile(model, mode='default')` for transformer models.
- **Per-run directory**: every run creates `models/run_YYYYMMDD_HHMMSS_{type}/` — no run-mixing.

---

## Detailed References

- `.claude/rules/training.md` — full training patterns, ChunkLoader, checkpointing, step-based training
- `.claude/rules/data-pipeline.md` — data processing patterns, parallelism tiers, parity gates
- `.claude/rules/general.md` — error handling, long-running scripts, diagnostic scripts
- `.claude/rules/fail-fast-loud.md` — no silent failures/fallbacks; always re-raise; validate early (applies to all .py and .sh)
- `.manager/convictions/` — conviction files. Each has a `## Trigger Conditions` header; read that first to determine relevance before reading the full file. Routing table:

| Conviction | Trigger | Always-read skills |
|---|---|---|
| `conviction_track_separation.md` | Any multi-track decision | tconv, trev, tdeep, tdev_inline |
| `conviction_signal_quality.md` | Track A/B/Pivot eval gate (§Track A or §Track B) | tconv, trev, tdeep, tdev_inline |
| `conviction_adversarial_triangulation.md` | Any smoke/prove-out/tag gate decision | tdeep (all modes), trev, tconv |
| `conviction_autonomy_envelope.md` | Deletion, Category I/II path, or loop-authority question | tconv, tdevauto, tdev_inline |
| `conviction_autonomous_launch.md` | Before any autonomous launch | tdevauto, tdev_inline |
| `conviction_orchestration_efficiency.md` | Short-circuit eval, strike advance, Q-bypass, early-kill | tconv, tdeep (Mode A), trev, teta |
| `conviction_tagged_model_protection.md` | Deletion/overwrite/migration near `*_tag_*/` | tconv, tdev_inline, tdeep |
| `conviction_disk_space_management.md` | Disk > 80% or R-class AUTH-GATE task active | tconv (disk step) |
| `conviction_memory_pressure_management.md` | Prove-out or full-scale launch approval | tdeep (Mode A), teta |
| `conviction_runtime_behavior_tests.md` | Pre-launch audit of any script | tdeep (Mode A) |
| `conviction_time_efficiency.md` | Reuse-vs-rebuild decision | tdev_inline, tconv |
| `conviction_ptsa.md` | New training initiative with new features | tconv (new ACTIVE entry authoring) |
| `conviction_strategic_progression.md` | ≥5 Track B variants evaluated, or STRATEGIC_PIVOT_PROPOSAL | trev, tconv |
| `conviction_pivot_exploration.md` | Any `firstrate_pivots/p*` task | tconv, trev, tdeep, tdev_inline |
| `conviction_prove_out_resumable.md` | Multi-component chain launch, gate marker verification, or resume instruction authoring | tdeep (Mode A), tdev_inline |
| `conviction_efficient_cache_and_training.md` | Pre-launch code audit of any data-processing, cache-building, or training script | tdeep (Mode A) |
| `conviction_step_based_training.md` | Any training script authoring or audit | tdeep (Mode A), tdev_inline, tconv |
| `conviction_trade_entry_exit_common.md` | Any script computing returns, applying slippage, or managing portfolio state | tdeep (Mode A), tdev_inline, tconv |

- `.claude/skills/all/details_*.md` — code examples and architecture diagrams
