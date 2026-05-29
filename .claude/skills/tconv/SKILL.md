---
name: tconv
description: "Timer cycle step 1: Conviction — analyze, pivot, enforce, propagate, tag"
user-invocable: true
---

You are executing ONE step. Tconv runs as **two phases**, each dispatched to its own Sonnet 4.6 subagent; then log and exit. Do NOT create new `.md` files unless a specific output file is named in these instructions.

## Two-track routing (Cycle 434.74, per `conviction_track_separation.md`)

The project's models split into two architecturally distinct tracks. Pivot triggers, banned patterns, and stagnation rules fire **per-track** — failures in one track do not trigger pivots in the other except via the Paired-Pivot clause.

- **Track A — Backbone (`firstrate_learning/vb*`)**: per-symbol feature extractors. Conviction authorities: `conviction_signal_quality.md §Track A` + `conviction_v13_experimentation_strategy_backbone.md`.
- **Track B — Portfolio (`firstrate_portfolio/vp*`)**: universe-aware rankers. Conviction authorities: `conviction_signal_quality.md §Track B` + `conviction_v13_experimentation_strategy_portfolio.md`.

Phase-1 stagnation / pivot logic MUST tag every pivot proposal with `Track: A` or `Track: B` and cite ONLY same-track evidence. Cross-track pivots require explicit invocation of the Paired-Pivot clause in `conviction_track_separation.md` with all three conditions met (≥3 architecturally distinct vp head classes failed against the same backbone tag, sub-floor cascade ratio, Track A own gate also at risk). Without this invocation, cross-track pivots are rejected.

Phase-2 design-doc authoring MUST tag every new ACTIVE entry with `Track: A` or `Track: B` immediately after the `Axis:` line. Track B entries MUST declare consumed backbone tag path under § Sources. Per-track ACTIVE caps in `memory_design.md`: ≤1 Track A + ≤2 Track B = ≤3 total. The legacy "≤2 ACTIVE" global cap is replaced by these per-track caps.

If `conviction_signal_quality.md` is missing, queue an authoring task before proceeding — the file is required. As of 2026-05-05 Track A and Track B are merged into `conviction_signal_quality.md`; both sections (§Track A and §Track B) are always present in that file.

- **Phase 1 — Conviction / pivot.** Reads state, identifies violations, pivots `memory_dev.md`, queues conviction/rule proposals (two-cycle rule). Always runs.
- **Phase 2 — Design-doc authoring (conditional).** Only dispatched if phase 1's pivot created or left unresolved a design-doc task against `.manager/memory_design.md`. Authors or revises an ACTIVE entry in `memory_design.md`. NEVER authors a new standalone `.md` design file — `memory_design.md` is the single running design log.

Both subagents use the Agent tool with `subagent_type: "general-purpose"`, `model: "claude-sonnet-4-6"` (Sonnet 4.6 with medium effort; pinned 2026-04-30 caller-authorized to match the Sonnet orchestrator and reduce dispatch overhead — prior pin was Opus 4.7). The model ID is pinned explicitly so a future default-change cannot silently downgrade conviction or design reasoning to a weaker model.

**FORBIDDEN writes — applies to BOTH phases and to tconv's post-return steps:**
- `CLAUDE.md` — **user-only write authority**. tconv NEVER edits CLAUDE.md. Universal rules (U1–U9, naming, safety) are stable and user-governed. If a finding warrants a new universal rule, tconv queues a proposal task for the user. Empirical findings, experiment results, and model-specific notes go to convictions or `todo/reference/` — NOT CLAUDE.md. This is a conviction breach if violated.
- `.manager/goals.md` (read-only; high-level objectives are caller-owned)
- `.manager/trev_report.md` (read-only; trev_inline's proposal artifact)
- `.manager/launch_commands.json` (owned by tdev_inline)
- `.manager/deep_analysis_launch.md`, `.manager/deep_analysis_design.md`, `.manager/deep_analysis_postrun.md`, `.manager/tdeep_analyzed_runs.json` (all owned by tdeep)
- `.manager/kill_violations.md` (owned by teta)
- `.manager/timer_cycle_state.json` (owned by timer-dev)
- Any other skill's working files
- Any new standalone `.md` design doc outside `memory_design.md` (e.g., `v5_portfolio_aux_design.md`) — all design content lives in `memory_design.md`.
- No `nohup`, no backgrounded processes, no training launches.

**Content routing rule (apply before writing anything):** When a finding needs to be persisted, route it correctly:
- New universal code constraint (applies to ALL scripts regardless of type) → propose to user for CLAUDE.md addition
- Experiment result, model metric, empirical finding → `conviction_signal_quality_*.md` § Archived Findings or `todo/reference/`
- Per-cycle task or state → `memory_dev.md`
- Protocol for a specific skill → that skill's `SKILL.md` (tconv has write authority over skill files)
- Gate or contract for a specific subsystem → the relevant conviction file under `.manager/convictions/`

**Phase-specific write authority:**
- Phase 1 MAY write `.manager/memory_dev.md`. Phase 1 MAY lifecycle-demote entries in `memory_design.md` (ACTIVE → SUPERSEDED / RETIRED) when the pivot makes them stale — but MUST NOT author or revise ACTIVE entry bodies. That is phase 2's job.
- Phase 2 MAY write `.manager/memory_design.md` — authoring a new ACTIVE entry, or appending a dated revision block under an existing ACTIVE entry. Phase 2 MUST NOT edit `memory_dev.md`, convictions, CLAUDE.md, or rules. Phase 2's only output is the `memory_design.md` edit plus a short return report to tconv.

## Phase 1 short-circuits (per `conviction_orchestration_efficiency.md` Rules A2, A4, A5)

Before dispatching the phase-1 subagent, the parent skill performs three cheap parent-side checks:

### State-hash short-circuit (Rule A2)

1. Compute the state signature from cheap parent reads (no subagent). State signature is the SHA256 of a JSON-serialized vector:

   ```json
   {
     "current_cycle": "<from memory_dev.md header>",
     "active_focus_lines_hash": "<sha256 of first two non-header lines of memory_dev.md>",
     "strike_ledgers": {"<family>": "<n/3>", ...},
     "conviction_queue_ids": [...],
     "latest_run_basename": "<from tdeep_analyzed_runs.json last entry or null>",
     "last_trev_timestamp": "<from memory_dev.md Trev Status last run or null>",
     "active_design_entries": ["<variant_name>", ...]
   }
   ```

2. Compare the new signature to the most recent tconv phase-1 bullet's emitted `state_hash` field.

3. If signatures match AND no entries in `tdeep_analyzed_runs.json` are newer than the previous phase-1 timestamp AND no `.manager/convictions/*.md` mtime is newer than the previous phase-1 timestamp AND no new task lines in `memory_dev.md` § Tasks since the previous phase-1, **overwrite** the `## Tconv Status` section in `.manager/memory_dev.md` with:

   ```
   ## Tconv Status
   Last run: [ts]
   Status: SHORT_CIRCUIT:state_unchanged
   state_hash=<sha256> | reason=no_new_evidence | next_action=defer_to_branch_classifier | short_circuit=A2:<hash>
   ```

   Skip the phase-1 subagent dispatch entirely. Phase-2 is also skipped. Exit.

4. If signatures differ OR any invalidation trigger fired, dispatch the full phase-1 subagent. The phase-1 audit bullet MUST emit `state_hash=<sha256>` of the post-edit state signature so the next invocation can short-circuit if appropriate.

### Q-bypass classification (Rule A4)

When the phase-1 subagent surfaces a conviction proposal, it MUST classify the proposal as one of:

- `class: clarification` — adds a verbatim quote of an existing rule, adds a cross-reference, fixes typo/formatting. Does NOT change any numeric threshold, does NOT add/remove a gate, does NOT change strike-rule semantics, does NOT change a skill's dispatch criteria, does NOT introduce a new conviction file or new top-level section.
- `class: behavior` (default) — anything that does change behavior; subject to the standard two-cycle rule.

Clarification-class proposals are eligible for **same-cycle ratification**: the same phase-1 invocation runs the proposal's `Verify:` line; if it passes, the edit applies in the same cycle. Audit bullet field: `short_circuit=A4:clarification_class | proposal_id=<Q-id>`.

When in doubt, classify as `class: behavior`. The clarification class is for unambiguously-cosmetic edits.

### Bit-identity 2-strike retirement (Rule A5)

When phase-1 evaluates strike-advance proposals from trev or surfaces them itself, it MUST check the bit-identity 2-strike rule across ALL tracks:

If two strike-eligible runs in the same head class produced `foresight_sharpe_ratio_matched` matching to ≥4 decimals (across smoke or prove-out), the head class is RETIRED at strike 2/3 immediately. This generalizes the bit-identity 2-strike rule from `conviction_pivot_exploration.md` § Strike ledger to apply across Track A, Track B, and Track-Pivot.

Sub-variant scope: strike counts at the head-class level, not per sub-variant. Two sub-variants of the same head class qualifying triggers the rule. Different head classes coincidentally matching do NOT trigger.

Audit bullet field: `short_circuit=A5:bit_identity_2strike | head_class=<name> | foresight_value=<x.xxxx>`.

---

## Phase 1 — conviction / pivot subagent

Agent prompt — pass the full instructions below verbatim:

---
## Instructions (Phase 1)

Do NOT create new `.md` files unless a specific output file is named in these instructions. You MAY edit `memory_dev.md`. You MAY lifecycle-demote entries in `memory_design.md` (ACTIVE → SUPERSEDED or RETIRED, with a short tombstone). You MUST NOT author or revise ACTIVE entry bodies in `memory_design.md` — that is phase 2's job.

1. **Read convictions (trigger-scan protocol):**
   Each conviction file begins with a `## Trigger Conditions` block. Read that block only (first ~12 lines) for every file, then read the full content of files whose trigger applies to the current task.

   **Always read in full (every phase-1 invocation):**
   - `conviction_track_separation.md` — routing rule; governs all track decisions
   - `conviction_autonomy_envelope.md` — loop authority; governs Category I/II paths
   - `conviction_generative_cycle.md` — ideation contract; reads ALL of: problem-model hypothesis maintenance, distance-to-profit tracking, weighted ranking, outcome-update reflex, K1-trajectory diagnosis consumption, pre-commit thesis check, lessons-learned registry, high-priority findings + caller TL;DR responsibilities (Cycle P16.037+).
   - `.manager/lessons_learned.md` — registry of historical lessons (per CONV-LESSONS-LEARNED-REGISTRY-1); candidates re-proposing lesson-blocked directions MUST cite + refute

   **Read in full when the trigger fires:**
   - `conviction_signal_quality.md §Track A` — when any Track A (`vb*`) variant is being evaluated or pivoted
   - `conviction_signal_quality.md §Track B` — when any Track B (`vp*`) or Pivot (`p*`) variant is being evaluated or pivoted
   - `conviction_adversarial_triangulation.md` — when verifying any smoke/prove-out/tag gate result
   - `conviction_orchestration_efficiency.md` — when evaluating a short-circuit, strike advance, or Q-bypass
   - `conviction_tagged_model_protection.md` — when the disk-pressure step enumerates any path near `*_tag_*/`
   - `conviction_disk_space_management.md` — when disk > 80% or an R-class AUTH-GATE task is active
   - `conviction_time_efficiency.md` — when choosing between reuse/rebuild/resume approaches
   - `conviction_strategic_progression.md` — when trev_report contains `STRATEGIC_PIVOT_PROPOSAL` or ≥5 Track B variants exist
   - `conviction_pivot_exploration.md` — when any `firstrate_pivots/p*` task is in scope
   - `conviction_ptsa.md` — when authoring a new ACTIVE training entry for a new feature set or data source
   - `conviction_autonomous_launch.md` — when unsticking a BLOCKED-AUTH-GATE task
   - `conviction_prove_out_resumable.md` — when verifying gate markers or writing resume/chain-launch instructions
   - `conviction_efficient_cache_and_training.md` — when reviewing a data-processing or cache implementation task
   - `conviction_step_based_training.md` — when reviewing any training script or authoring a training entry
   - `conviction_trade_entry_exit_common.md` — when reviewing any script that computes returns, applies slippage, or manages portfolio state
   - **`conviction_generative_cycle.md`** — ALWAYS-ACTIVE per its trigger; read in full every Phase-1 cycle. Governs ideation-first contract, design-space dictionary, model-ledger anchor, sibling/predecessor mining, counterfactual reframing templates, first-principles reset, adversarial-critic dispatch.

   Investigate every violation listed in each conviction file you read fully.

2. **Read project state:**
   - Read `.manager/goals.md` for high-level objectives
   - Read `.manager/memory_dev.md` for the active task list, current state, and all skill status sections
   - Read `.manager/memory_design.md` for ACTIVE / APPROVED / SUPERSEDED / SHIPPED / RETIRED design entries. This is the single running design log; there should be no standalone `.md` design docs anywhere else under `.manager/`.
   - Read `.manager/trev_report.md` if it exists — treat its recommendation as an **explicit input**, not authority. Reconcile with current `memory_dev.md` state. If trev's top-gap coordinate or recommended path has NOT yet been reflected in `memory_dev.md`, this is the unblock signal — your pivot in step 4 should honor it unless you have conviction-backed reason to override. Quote the trev recommendation you are acting on (or overriding) in the audit bullet.
   - Read all three tdeep output files if they exist: `.manager/deep_analysis_launch.md` (Mode A pre-launch audits), `.manager/deep_analysis_design.md` (Mode B design-doc verdicts), `.manager/deep_analysis_postrun.md` (Mode C post-run analyses). Also read `.manager/tdeep_analyzed_runs.json` for the deterministic registry of analyzed runs (classification + dev_capacity per run). tconv phase-1 is the synthesizer that combines post-run records with convictions and the trev gradient to propose the next experiment class.
   - Read `.manager/kill_violations.md` if it exists (runtime violations from teta)
   - Read `.manager/proposed_rule_changes.md` if it exists — pending tdebug-authored rule-change proposals. You will ratify or drop these in step 5; reading here just makes them visible in the same pass as other state.
   - Read the skill status sections of `.manager/memory_dev.md` (`## Tdev Status`, `## Trev Status`, `## Tdeep Status` sections) — these record the most recent dev-capacity / review / audit signals.
   - Verify no stray standalone `.md` design docs exist under `.manager/` (glob `.manager/*_design*.md` and `.manager/designs/**`). If any are found that are NOT `memory_design.md` itself, flag them in the audit bullet so the caller can migrate + delete. Do not migrate content yourself — migration happens through phase 2's revision-block mechanism.

3. **Identify conviction violations:**
   - Check each violation listed in the conviction files against current project state
   - List all violations found
   - **PTSA GATE (Cycle PTSA.001+, per `conviction_ptsa.md` — HIGHEST PRIORITY BLOCKING CHECK).** The Pre-Training Signal Analysis window is OPEN (2026-05-01). ALL model training is blocked until PTSA-J completes with `val xsec_IC ≥ 0.005`. Check:
     1. Does `firstrate_ptsa/ptsa_summary.json` exist AND contain `"status": "PASS"`? If NO → all training launches are BLOCKING violations regardless of pivot readiness.
     2. Have all 21 PTSA tasks (PTSA-A through PTSA-U, including PTSA-T/S/U) produced outputs? List any missing. Batch 5 (PTSA-S/U) runs after PTSA-J PASS — they are NOT required before training begins, but ARE required for full PTSA completion.
     3. Is any PTSA Batch 1 task (PTSA-L/E/A/D/F/M) in READY/ACTIONABLE state with no script yet written? If so → tconv MUST set `memory_dev.md` PTSA task status to IN-PROGRESS and add launch entries for all Batch 1 tasks simultaneously.
     4. Are Batch 1 tasks complete but Batch 2 not started? → queue Batch 2 tasks (PTSA-B/C/G/H/I/N/O/P) as simultaneous launches. Are Batch 3 tasks complete? → queue Batch 4 (PTSA-T first, then PTSA-J). Has PTSA-J PASSed? → queue Batch 5 (PTSA-S + PTSA-U simultaneously).
     5. If PTSA-J finds `val xsec_IC < 0.005`: tconv MUST author `Task SR-PTSA-FAIL` in memory_dev.md enumerating three options: (A) pivot to volatility-based strategies, (B) extend data to earnings/macro features, (C) retire P1/P2/P3 window. Caller decision required.
     6. **DA.1/DA.2/DA.3 tasks in memory_dev.md are SUPERSEDED** by PTSA-A/PTSA-D/PTSA-F. Do not reference them separately.
     7. During PTSA window: no new backbone or portfolio model tasks, no bug fixes, no cache fixes unrelated to PTSA. ONLY PTSA scripts and their immediate dependencies.

4. **Pivot and update:**
   - **Overwrite `.manager/memory_dev.md`** (everything above the `## Skill Status` section) — replace stale goals with conviction-driven goals, update current state, Active-Focus lines, and task list. Preserve the `## Skill Status` section and all `## <Skill> Status` subsections below it unchanged.
   - **Maintain dual `Active-Focus-*` lines at the top of `memory_dev.md`** (per `conviction_track_separation.md` § Goal-tracker dual-focus rule). The first two non-header lines of `memory_dev.md` MUST be of exact form:
     ```
     Active-Focus-Backbone: <≤10-word Track A project outcome>
     Active-Focus-Portfolio: <≤10-word Track B project outcome>
     ```
     followed by a blank line, then the rest of the content above `## Skill Status`. trev_inline computes its gradient on each track independently against the matching focus line. tdevauto renders both lines in the dev panel. Style: state the *track-level project outcome*, not the *next experiment*. Stable across cycles unless the track's project-level focus actually shifts (typical lifetime: many cycles per phrase). Track A examples: `Active-Focus-Backbone: lift per-stock IC + paired-eval to tag-eligibility`, `Active-Focus-Backbone: complete PTSA + validate P6 backbone`. Track B examples: `Active-Focus-Portfolio: produce tradeable portfolio model`, `Active-Focus-Portfolio: harden P6 cascade vs val/test divergence`. Avoid: experiment-level framing, metric-only framing, past-tense framing, mixed-track framing. Legacy single `Active-Focus:` line (pre-Cycle 434.74) is RETIRED — if found, the pivot MUST replace it with the dual-line form.
   - **Preserve cross-cycle task-completion history.** Before overwriting `memory_dev.md`, scan the current task list and cross-reference each task against the `## Tdev Status` section of `memory_dev.md`. Any task the dev audit trail shows was completed since the last pivot MUST be preserved in the new content under a top-of-file `## Completed since last pivot` subsection — quote the relevant tdev status content as evidence. Without this, "why did we do this experiment?" audit trails rot across cycles.
   - **Lifecycle-demote stale design entries (per-track caps, per `conviction_track_separation.md`).** For every ACTIVE / APPROVED entry in `memory_design.md` whose axis the new goal no longer references: demote to SUPERSEDED (if replaced by a new entry) or RETIRED (if simply no longer pursued). Write a one-paragraph tombstone naming the reason. You MAY edit section headers (`## ACTIVE:` → `## SUPERSEDED:` / `## RETIRED:`) and MAY append a tombstone paragraph. You MUST NOT rewrite the entry body — the authoring trajectory stays visible. **Per-track hard caps after the pivot:** ≤1 Track A entry (variant folder under `firstrate_learning/vb*` OR `Track: A` line) AND ≤2 Track B entries (variant folder under `firstrate_portfolio/vp*` OR `Track: B` line) AND ≤3 total. The legacy global ≤2 cap is REPLACED by these per-track caps. Demotion must rebalance to satisfy all three caps independently — a Track A retire does NOT free a Track B slot, and vice versa.
   - **Owned-artifact disposition at retirement (REQUIRED on every ACTIVE → RETIRED demotion this cycle, track-aware).** When you demote an ACTIVE entry to RETIRED in this same cycle, you MUST in the same tombstone block enumerate the variant's owned cache + model artifacts and classify each one. **Determine the variant's track from its `Track:` line or variant-folder root, then walk the track-appropriate paths:**
     - Track A (Backbone) variants: walk `firstrate_learning/<variant>/models/`, `firstrate_learning/<variant>/cache/`, and `firstrate_learning/cache/<variant>*/`.
     - Track B (Portfolio) variants: walk `firstrate_portfolio/<variant>/models/`, `firstrate_portfolio/<variant>/cache/`, and `firstrate_portfolio/cache/<variant>*/`.
     The list also comes from reading the variant's design entry §Output layer / §Variant folder (or equivalent) section. For each artifact, apply two predicates: (i) cross-reference against ACTIVE-variant code by grep'ing `cache/<artifact_basename>` over each currently-ACTIVE variant's `*.py` ON BOTH TRACKS (a Track A variant's tagged backbone may be consumed by Track B variants — cascade lineage per `conviction_track_separation.md` § Cache lineage rule); (ii) check tag-safety predicates from `conviction_tagged_model_protection.md` (path inside `*_tag_*` → NEVER delete; path inside `.storage-long/` → NEVER delete; `best_model.pt` referenced by another active variant ON EITHER TRACK → NEVER delete). Three buckets:
     - **DELETABLE** — no ACTIVE consumer found AND the design entry's tombstone does not claim audit-significance for this artifact AND tag-safety predicates pass.
     - **AUDIT-TRAIL-RETAIN** — artifact is referenced by this RETIRED entry's tombstone as evidence (e.g., the run dir whose `run_meta.json` + `training_results.json` proved the falsification). Keep the smallest checkpoint subset that proves the verdict; allow `latest_checkpoint.pt` and bulky intermediate tensors to be stripped at AUTH-GATE time.
     - **KEEP-LOAD-BEARING** — an ACTIVE variant references this. Cannot delete; must persist regardless of the parent variant's retirement status.
     Format the disposition under the tombstone of exact form:
     ```
     Owned-artifact disposition (Cycle <N>):
     - cache/<variant>_tokens/   <size>   <bucket>: <one-line reason>
     - <variant>/models/         <size>   <bucket>: <one-line reason>
     - cache/<shared_dep>/       <size>   <bucket>: <one-line reason>
     ```
     Then update the active R4-class AUTH-GATE task in `memory_dev.md` to enumerate the new DELETABLE paths added by this retirement — append them to R4's path list with sizes, OR if R4 has been executed already, queue a fresh `R<N>` AUTH-GATE task with the new orphan list. The task MUST cite `conviction_disk_space_management.md` as authority and remain at `BLOCKED-AUTH-GATE` per rule 26 until caller double-confirm.
   - Remove any old thoughts or stale tasks in the overwritten content that contradict conviction direction.
   - **If the pivot contradicts the most recent `trev_report.md` recommendation:** quote the contradicted trev recommendation verbatim in the audit bullet, name the conviction or disk-state evidence that justifies overriding it, and leave a one-line "tconv-override" note in `memory_dev.md`'s current-state block. Silent override of trev is forbidden — disagreements must be visible to the caller.
   - **STRATEGIC_PIVOT_PROPOSAL handling (Cycle 434.75+, per `vp17_strategy_reframe.md` Edit B4 + `conviction_strategic_progression.md`).** If the most recent `trev_report.md` § 11 Machine-readable requests block contains a `STRATEGIC_PIVOT_PROPOSAL:` verb (emitted by trev § 3a-strategic when foresight-trajectory or V10-anchor-stuck rule fires), tconv MUST NOT propose a new vp variant in this cycle's pivot. Instead, tconv MUST author a `tconv strategic-review` task in `memory_dev.md` of exact form:
     ```
     ### Task SR-N — STRATEGIC_PIVOT_PROPOSAL caller-decision: <trigger>

     **Origin**: `trev_report.md` § 11 STRATEGIC_PIVOT_PROPOSAL emission Cycle <K>.
     **Trigger**: <foresight_trajectory_diminishing | v10_anchor_stuck>.
     **Evidence**: <file:line citations from trev's emission>.
     **Three response options per `conviction_strategic_progression.md` § Three response options:**
     - Option (a) Strategy-2 escape hatch: promote Track C ROADMAP → ACTIVE; requires authoring `conviction_signal_quality_endtoend.md` and per-track-cap revision in `conviction_track_separation.md`.
     - Option (b) Substantially-different Track A architectural pivot: cross-symbol attention / sector-graph attention / factor-projection. Caller-authorization required when blurring per-symbol invariant.
     - Option (c) Regime-conditional ensembling on Track A: dual-backbone with regime classifier. Caller-authorization required for operational-complexity reasons.
     **Caller decision required**: APPLY <option> / DEFER (more evidence) / DISCARD (override the trigger with cited rationale).
     **Status**: BLOCKED-AUTH-GATE pending caller decision.
     ```
     This is a Class 3 escalation per `conviction_track_separation.md` and `conviction_strategic_progression.md` § Caller-decision boundary. tconv does NOT auto-promote Track C, does NOT auto-author a substantially-different Track A pivot, does NOT auto-commit a regime-conditional variant. The decision routes to caller via the Task SR-N entry. tdevauto's launch primitive (per `vp17_strategy_reframe.md` Edit B6 below) BLOCKS new vp launches while any unresolved Task SR-N is present in memory_dev.md.
   - **strategic_progression_check field (MANDATORY in audit bullet, Cycle 434.75+).** tconv's run-report bullet MUST include a `strategic_progression_check: PASS / FIRED / SUPPRESSED` field per `conviction_strategic_progression.md` § Violations rule 2. PASS = no STRATEGIC_PIVOT_PROPOSAL in trev report. FIRED = STRATEGIC_PIVOT_PROPOSAL present, Task SR-N authored. SUPPRESSED = STRATEGIC_PIVOT_PROPOSAL present but rule should not fire (requires a one-line reason citing why the rule should not fire on this evidence; SUPPRESSED with no reason is itself a violation).
   - **Design-doc gate handling (against `memory_design.md`):**
     - If the new goal requires a design that has NO ACTIVE or APPROVED entry in `memory_design.md` → write a READY task in `memory_dev.md` of exact form: `tconv phase-2: author new ACTIVE entry in memory_design.md § <variant_name>`. This signals phase 2 to run.
     - If an ACTIVE entry exists but pre-dates the current trev pivot or lacks a `## Sources` header-block reconciling to the current `memory_dev.md` top-gap coordinate → write a READY task of exact form: `tconv phase-2: revise ACTIVE entry memory_design.md § <variant_name> (append dated revision block reconciling to current trev pivot)`.
     - If an ACTIVE entry exists, is current, AND is awaiting tdeep audit → write a READY task of exact form: `tdeep design-doc audit: memory_design.md § <variant_name>` and proceed. Phase 2 does NOT run.
     - If an ACTIVE entry has been tdeep-APPROVED → write READY implementation tasks for tdev_inline, referencing the APPROVED entry by `§ <variant_name>` anchor.
     - Tconv NEVER authors a new standalone `.md` design file. All design content is appended to `memory_design.md` by phase 2.

4a. **SOFT-block closure (tdevauto routed under rule 24/25):** If the most recent tdevauto entry in the `## Tdevauto Status` section of `memory_dev.md` classifies the state as `IDLE_UNSTICK` SOFT-block (i.e., the three HARD-block criteria per `conviction_runtime_behavior_tests.md` rule 24 are NOT all satisfied), tconv MUST close the block this cycle under one of two forms:
   - **(a) commit-and-falsify [DEFAULT]** — select one of the feasible in-tree paths, promote its READY task in `memory_dev.md`, and append an audit-bullet citation naming the falsification experiment (which smoke / unit test will confirm-or-reject within one cycle, and what measured coordinate flips the verdict). Example bullet fragment: *"committed PTSA-batch-1 parallel launch; smoke falsifies if all IC values remain below 0.002; revert path on falsification = pivot to volatility-based strategy per SR options."*
   - **(b) downgrade to HARD-block [FALLBACK]** — if tconv cannot commit form (a) without a specific external substance (file, credential, permission, raw artifact — NOT a design preference) OR an external action the loop cannot take per the autonomy envelope's Category II permanent list, produce a concrete external-substance/action ask naming the exact resource, target disk path, or shell command. The ask MUST be literal (e.g., *"rclone pull `.storage-long/compressed/firstrate/source_data/historic/2020_q1_option_chain_*.synced` → `.storage-long/uncompressed/.../historic/` so `prepare_tokens.py` val split can populate"*) not categorical (e.g., NOT *"need raw data"*).

   **Form-a is the DEFAULT; form-b is a FALLBACK with explicit justification.** Tconv MUST attempt form (a) first on every SOFT-block. Form (b) is permitted ONLY when:
   - **(i)** the ask cites a specific Category I-permanent path from `conviction_autonomy_envelope.md` (`*_tag_*/` or `.storage-long/`); OR
   - **(ii)** the ask cites a specific Category II operation from the envelope (git push, credential rotation, paid-API call, external-channel publishing); OR
   - **(iii)** form (a) was tried in a prior cycle for the same task and the falsification experiment ran without resolving the gap — i.e., the loop has empirical evidence that no in-tree path closes this block.

   The audit bullet on form (b) MUST include a one-line justification of which clause (i/ii/iii) applies and quote the specific envelope category or prior falsification result. A form (b) bullet without that justification is a CLASSIFIER violation; the next cycle's tconv MUST re-evaluate and prefer form (a) unless the justification is added.

   Phrasings that route a SOFT-block to the caller as a design question ("do you approve…", "is this framing acceptable…", "which option do you prefer…") are BANNED per rule 25. If tconv finds itself drafting such a phrasing, the correct response is to fall back to form (a) with the cheapest-to-falsify path as the default. Rationale: reversible experiments produce new evidence; approval requests produce only new opinion at latencies measured in hours to days. The form-a-default rule reinforces this — every escape to form (b) must overcome the (i/ii/iii) justification bar, which by construction filters out "I can't decide so I'll ask the human."

4b. **Disk-pressure on-demand inventory + tier classification (per `conviction_disk_space_management.md` thresholds and tier policy).** Read `df -h /home/ubuntu/workspace`. Record the percent-used integer. Apply the four-tier disk ladder:
   - **< 80%**: still author a cleanup task IF Tier 1 candidates exist (Tier 1 deletes are autonomous-fire-OK and disk-pressure-independent). Skip Tier 2 inventory.
   - **80–85%**: author cleanup task with Tier 1 + Tier 2 inventory; one-line disk note in `memory_dev.md` current-state block.
   - **≥ 85% AND < 90%**: PRIORITY 0 cleanup task with full Tier 1 + Tier 2 + Tier 3 inventory.
   - **≥ 90%**: as above, plus `memory_dev.md` current-state block flags launches as blocked until disk < 85%.

   For every enumerated path, tconv MUST classify into one of three tiers per `conviction_disk_space_management.md` tier policy AND apply two predicates: (i) cross-reference against ACTIVE-variant code by `grep -rln --include='*.py' "<path-basename>"` over each currently-ACTIVE variant's source dir; (ii) tag-safety per `conviction_tagged_model_protection.md` (path inside `*_tag_*` → NEVER; inside `.storage-long/` → NEVER; `best_model.pt` referenced by another active variant → NEVER; `prices_raw.dat` referenced by any active variant's prepare_tokens → NEVER). Tier verdicts:
   - **Tier 1 — `AUTONOMOUS-FIRE-OK`**: low-stakes, regeneratable, broad consensus deletable. Categories: `__pycache__/` directories anywhere in the repo; log files older than 14 days in `output/` or `<variant>/` (keep 3 most recent per module); files in `backups/` older than 30 days; empty stub directories under `firstrate_learning/cache/` (size < 100 MB AND zero `.pt.zst` chunks); `latest_checkpoint.pt` from runs whose `run_meta.json` shows training never completed AND `gate_smoke.json` was never written AND the run dir's parent variant has no live training PID. Tier 1 paths are flagged `AUTONOMOUS-FIRE-OK` and have no stability-counter requirement — tdev_inline may fire on the next cycle.
   - **Tier 2 — `AUTONOMOUS-FIRE-PENDING [N/M]`**: high-value but require multi-cycle stability. Categories: orphan variant token caches (variant in `## RETIRED:` of `memory_design.md`, no ACTIVE-variant code-ref hits); orphan variant model dirs from retired variants whose tombstone does NOT mark the dir AUDIT-TRAIL-RETAIN; orphan variant supplement caches. Each Tier 2 path carries a per-path stability counter `[N/M]` where M = 3 (default; may be tuned via conviction edit). On each cycle, if predicates (i) + (ii) + retirement-status all pass: increment N. If ANY predicate fails: reset N to 0 and mark `RE-CLAIMED Cycle <K>: now load-bearing for ACTIVE: <variant>` (drift-defense behavior, formerly step 4c). When N reaches M, flip the tier flag to `AUTONOMOUS-FIRE-READY` — tdev_inline may fire on the next cycle.
   - **Tier 3 — `CALLER-CONFIRM-REQUIRED`**: caller authority retained. Categories: anything inside `*_tag_*` directories (NEVER list; should never appear as candidate); anything inside `.storage-long/`; the active variant's own caches (would be a logic bug); paths where the static scan returns hits in ANY RETIRED-variant source (signals possible revival); recently-built large caches (≥ 1 GB AND mtime < 7 days); paths AUDIT-TRAIL-RETAIN per a retirement tombstone. Tier 3 paths are flagged `CALLER-CONFIRM-REQUIRED` and do NOT carry a stability counter — they remain at AUTH-GATE per rule 26 amended.

   Cleanup task body MUST format each path as:
   ```
   <path>   <size>   <Tier flag>   <one-line reason>
   ```
   Order DELETABLE entries by `conviction_disk_space_management.md` priority: failed-experiment artifacts → orphaned caches → duplicate run dirs → old logs → `__pycache__` → backups >30 days.

   The cleanup task itself stays at status `READY-CONTAINS-AUTONOMOUS` (tdev_inline reads + executes Tier 1 + AUTONOMOUS-FIRE-READY Tier 2 entries) AND simultaneously `BLOCKED-AUTH-GATE` for any Tier 3 entries (caller-confirm gate). tconv does NOT execute deletions itself; tconv writes the analysis only.

   **Audit-only override**: If `memory_dev.md` contains the literal string `CLEANUP_AUDIT_ONLY: true` anywhere in its current-state block, tconv MUST flag the cleanup task with `[DRY-RUN]` and tdev_inline MUST NOT execute any deletions until the override is removed. This is the kill switch if autonomous cleanup proves incorrect on early runs.

   This step runs every phase-1 cycle. Tier 1 candidates can be authored even at low disk pressure (they're cleanup hygiene). Tier 2/3 inventories scale with disk pressure per the ladder above.

4c. **(Drift-defense merged into 4b Tier 2 stability counters above.)** The earlier standalone drift-defense step is subsumed: each Tier 2 path's stability counter mechanically resets on RE-CLAIMED (active-variant code-ref appears). For any `BLOCKED-AUTH-GATE` task without Tier classification (legacy R4-class tasks pre-dating this skill version), tconv MUST migrate the task to the new tier-classified format on this cycle by re-running 4b inventory against the task's enumerated paths.

5. **Propagate violations into rules (two-cycle rule for conviction and rule edits) — covers additions, edits, AND retractions:**
   - Read `.claude/rules/general.md` and `CLAUDE.md`
   - **Two-cycle rule:** do NOT edit a conviction file, `CLAUDE.md`, or `.claude/rules/*` in the same run that first flags the gap. This applies equally to:
     - **Additions** (new conviction line).
     - **Edits** (rewording, scope-narrowing an existing line).
     - **Retractions** — removing an existing conviction / rule line because it has been empirically contradicted. Retractions are at least as sensitive as additions (they remove a previously load-bearing constraint) and MUST go through the two-cycle rule, NOT be treated as "obvious cleanup."
   - **Run N (first observation):** write a "Proposed conviction/rule update" subsection into `memory_dev.md`. Each proposal MUST include four fields:
     - `proposed:` the exact proposed addition / edit / retraction text (quoted verbatim as it will appear in the target file).
     - `target:` the file the edit would land in (e.g., `.manager/convictions/conviction_v13_backbone_v5_cache.md`, `CLAUDE.md`, `.claude/rules/general.md`).
     - `evidence:` one or more concrete citations — each of form `<file_path>:<line_or_pattern>` (e.g., `firstrate_ptsa/ptsa_a/ic_scan.json:12 "ic": -0.003`, or `ls firstrate_ptsa/ptsa_j/` returning empty). Prose-only motivations are NOT acceptable; the citation must be something run N+1 can re-read mechanically. For retractions, cite the contradicting experiment / measurement / run_meta with file path.
     - `verify:` a one-line check run N+1 can execute to confirm the evidence still holds (e.g., `Read firstrate_ptsa/ptsa_summary.json and confirm "status": "PASS" is present`, or `Read .manager/trev_report.md:74 and confirm 'DISQUALIFIED' is still present`). The verify-line is the mechanical gate that stops N+1 from rubber-stamping the queue.
     Flag the queued proposals in the audit bullet.
   - **Run N+1 (after caller review of run N's memory_dev):** for each queued proposal:
     1. Confirm the caller has not deleted or struck it from memory_dev.md (silence = consent).
     2. Execute the proposal's `verify:` line as a fresh read. If the check passes → apply the edit (add / edit / retract) to the target file.
     3. If the `verify:` check FAILS (evidence no longer on disk, measurement changed, cited line moved) → DROP the proposal and record a one-line dropped-reason in the N+1 audit bullet. Do NOT apply a proposal whose motivating evidence has disappeared.
     4. If a queued proposal lacks a `verify:` field (pre-dates this protocol, or was written by an older tconv run) → do NOT apply. Either drop it, or re-queue it this cycle with a proper `verify:` field and defer application to run N+2. Missing-verify proposals fail closed.
   - Rationale: conviction and rule edits are sticky across every future cycle. A two-cycle delay catches contamination-driven edits without blocking genuine convictions; the cost is one cycle of propagation latency, which is cheap relative to a wrong always-loaded rule. The `verify:` field converts the gate from discretionary re-reading into a mechanical check — without it, the two-cycle rule degrades into a one-day delay with no filter as the loop gets comfortable.
   - Keep rules concise. One line per rule. Add to existing sections, don't create new files.
   - **Tdebug-authored proposals (ratify or reject):** read `.manager/proposed_rule_changes.md` if it exists. Each `## Proposal <ts> — <title>` block was authored by tdebug (or by the caller manually) and is `Status: PENDING-TCONV-RATIFY`. For each pending proposal:
     1. Confirm `Target file:` is NOT in the load-bearing protected set: the seven autonomous-launch gates (`conviction_autonomous_launch.md`), `conviction_autonomy_envelope.md`'s Category II permanent list, `conviction_tagged_model_protection.md`. If the proposal touches any of these, mark it `Status: REJECTED-PROTECTED` with a one-line reason and skip — those edits are caller-only.
     2. Run the proposal's `Verify:` line as a fresh read. If it passes (evidence still on disk, the experimental result still present, the cited rule line still has the form the proposal expects), apply the edit: replace the `Current text` block with the `Proposed text` block in the named target file. Mark the proposal `Status: RATIFIED-<YYYY-MM-DD>` in `proposed_rule_changes.md` and append a one-line citation to your phase-1 audit bullet (`ratified tdebug proposal <title> in <target>`).
     3. If the `Verify:` line fails, mark the proposal `Status: DROPPED-VERIFY-FAILED` with a one-line reason and skip — evidence has moved.
     4. If the `Verify:` line is missing or the proposal lacks the required structure (Target file, Current text, Proposed text, Evidence, Verify, Rationale), mark `Status: DROPPED-MALFORMED` and skip.
     5. Tdebug-authored proposals are exempt from the two-cycle delay — tdebug already ran a falsifiable experiment OR collected post-mortem evidence in the cycle that authored the proposal, which serves as the equivalent of run-N evidence; tconv's verify-line check is the run-N+1 mechanical filter. The two-cycle delay exists to catch contamination-driven edits; tdebug's evidence-on-disk requirement substitutes for that filter.
     6. Do NOT delete ratified or dropped proposals from `proposed_rule_changes.md` — leave them in place with their updated `Status:` line as an audit trail. Caller may prune the file periodically.

6. **Tag models if needed:**
   - Check if any models need tagging (new best_model.pt since last tag). If yes, copy to tagged folder with version prefix. If nothing to tag, note "nothing to tag".

7. **Audit conviction test coverage:**
   - For each conviction file, check if violations are only static/grep-based or include runtime behavioral tests
   - Flag convictions that have only "check if code pattern X exists" violations but no "verify behavior Y at runtime" violations as having insufficient test coverage

8. **Expand violations with runtime checks:**
   - When a conviction has only static violations, add concrete runtime behavioral test violations to that conviction file
   - Static example: "No zstandard compression" (grep for zstd import) → Runtime: "Cache file must exist on disk at expected path in `.pt.zst` format before launch"
   - Static example: "No epoch-based training" (grep for `for epoch in range`) → Runtime: "Checkpoint must contain `global_step` field, not `epoch` field as primary counter"

9. **Improve tdeep test patterns:**
   - If tconv discovers a behavioral gap (tdeep missed a violation because it only grepped code), add the specific runtime test to the conviction's violations section so tdeep catches it next cycle

10. **Experiment failure analysis AND blocking-coordinate flatness (CRITICAL):**
   - Count consecutive smoke failures from `deep_analysis_postrun.md` history.
   - ALSO count `n_cycles_since_blocking_coord_moved`: read the `## Trev Status` section of `.manager/memory_dev.md` and/or `deep_analysis_postrun.md` and compare the blocking-coordinate (trev §2 top-gap row) current value. "Moved" = |Δ| ≥ 5% of best_observed across any two consecutive cycles. If the blocking coord has been flat (<5% movement) for ≥ 3 cycles, treat the same as 3+ consecutive smoke failures.
   - If EITHER trigger fires with only hyperparameter changes → MUST assign an ARCHITECTURAL change to tdev_inline (model size, compression layer, loss function, training approach, or feature-representation change). Write this explicitly in memory_dev.md: "ARCHITECTURAL CHANGE REQUIRED — hyperparameter tuning exhausted for this axis." Quote the flatness citation (cycle range + coord values) in the memory_dev.md task so N+1 can verify.
   - For each failure, extract the LEARNING: what does this tell us about the integration problem? Write the learning in memory_dev.md.
   - Propose the next experiment based on accumulated learnings, not just "try lower X"
   - Read the **track-scoped** experimentation-strategy conviction matching the variant under consideration (`conviction_v13_experimentation_strategy_backbone.md` for vb-class, `conviction_v13_experimentation_strategy_portfolio.md` for vp-class) for the list of untried architectural changes within that track. The legacy `conviction_v13_experimentation_strategy.md` is SUPERSEDED — read for historical context only.

10a. **Hypothesis-grounding rule (CONV-PROCESS-HYPOTHESIS-CODE-GREP-1, ratified Cycle P16.016):** Before authoring a hypothesis in the pivot summary that names a specific code mechanism (LR scheduler, warmup boundary, optimizer state corruption, RNG-seeding subroutine, layer-specific gradient path, AMP autocast scope, GradScaler skip path, loss-aggregation predicate, or any other named code construct), tconv MUST first run a fresh `grep` over the relevant source files to verify the mechanism EXISTS in code. The grep MUST be cited verbatim in the pivot summary (e.g., `verified via grep -n 'lr_scheduler|LambdaLR|warmup' train.py config.py returning N matches`). If the grep returns no hits, OR returns only hits that semantically don't match the mechanism named (e.g., all `warmup` hits are `K1_WARMUP_EVALS` kill-gate warmup not LR warmup), the hypothesis is REJECTED at authoring time and tconv MUST either (a) mark it as `speculative — code-presence not verified` in the pivot summary so downstream skills know not to invest in it, OR (b) substitute a code-grounded alternative. Rationale: hypotheses projected onto absent code generate downstream waste — sub-tasks specced against absent mechanisms produce inconclusive logs (e.g., a per-step `lr` instrumentation across a "warmup boundary" returns constant LR throughout when no scheduler exists), burning agent-impl time and compute for no information gain. The grep is mechanical (cheap) and converts hypothesis-generation from a discretionary projection-of-prior into a code-checked filter. Apply to BOTH new hypotheses in the current pivot summary's "surviving hypotheses" list AND to any hypothesis cited in a queued conviction proposal's evidence section. Evidence motivating: Cycle P16.014 pivot summary's `WARMUP_FRAC=0.15 × SMOKE_STEPS=3000 → warmup ends at step 450` claim was authored against absent code (no LR scheduler exists in `firstrate_pivots/p16_cache_repair/train.py` or `config.py`); downstream cost was ~40 min specced sub-task that tdev_inline correctly identified as unfalsifiable absent code (memory_dev.md § Tdev Status iter=258 Adjacent Finding).

11. **Approach-cost assessment (MANDATORY for every task):**
   - Before writing tasks to memory_dev.md, estimate the **wall-clock cost of the chosen approach vs its alternatives** (compute hours + agent implementation time combined, as a rough order of magnitude). This is used to justify the reuse/rebuild/resume choice per `conviction_time_efficiency.md`.
   - Check: do existing assets (weights, caches, checkpoints) allow a faster path?
   - Prefer: append over rebuild, resume over restart, fine-tune over train-from-scratch, supplement over regenerate.
   - Every task in memory_dev.md must include a line of form: `**Approach cost:** ~X (compute: Y, agent-implementation: Z). Reuse: [what existing assets are used].` Example: `**Approach cost:** ~3–5 hr (compute: 2.3 hr prove-out GPU; agent-implementation: ~30–60 min tool use). Reuse: existing PTSA vectorized cache, prices_raw.dat.`
   - **Semantic note — this field is NOT a tool-use budget for implementing agents.** It is a path-comparison number that justifies the reuse-vs-rebuild decision. Tdev_inline, tdev, and any downstream implementer MUST NOT treat it as a cap on their own work. Implementing agents manage their own tool-use budget via the progress-gate discipline in their own SKILL.md (e.g., `tdev_inline/SKILL.md` §3 "Wall-time discipline"). Older tasks may still use the deprecated `Estimated time:` label — treat it as equivalent to `Approach cost:` and update when touched.
   - If a task's approach cost exceeds 1 hour and a <15 min alternative exists using existing assets, use the faster path.
   - Read `conviction_time_efficiency.md` for the full time hierarchy.
   - For artifact-producing tasks, also include the six fields listed in §ARTIFACT_TASK_FIELDS below. The `Output contract:` field is the most critical — without it the unit-test gate has no assertion to verify.

   **§ARTIFACT_TASK_FIELDS — Required fields for any task that produces an output artifact gating downstream work** (training run, analysis probe, data-prep script, cache builder — any script whose output blocks another task):

   - `Artifact:` — the file path of the primary output (e.g., `firstrate_ptsa/ptsa_y/findings.json`, `firstrate_learning/cache/p6_price_context/manifest.json`). This is the file teta checks post-run via the output contract.
   - `Output contract:` — a one-sentence falsifiable assertion about the artifact's quality (e.g., `val_ic ≠ nan at all tested scales; findings.json written`, `all N_dates × N_syms cells populated; shape matches declared (8766, 4025, 8)`). This field is copied verbatim into `launch_commands.json` as the `output_contract` field.
   - `Unit-test gate:` — description of what the `--unit-test` mode must validate before full launch (e.g., `--unit-test (50 symbols, 2 dates): produces non-nan val_ic, labels std > 1e-3, gate_unit.json written`).
   - `Downstream blocks:` — what task or launch is blocked until this artifact's output contract is satisfied.
   - `requires_gpu:` — `true` for model training; `false` for analysis, probe, data-prep, cache scripts. For any script with neural components (torch imports), tconv MUST author this field based on a GPU break-even assessment, not by assumption. See `compute_profile:` below.
   - `compute_profile:` — one of `cpu_bound`, `gpu_bound`, or `borderline`. **MANDATORY for any script with torch imports.** Determination rules: (a) pure scipy/numpy, no torch → `cpu_bound`. (b) model training with N_params > 10K → `gpu_bound`. (c) small neural probe (N_params < 2K): estimate FLOPs per forward pass. If FLOPs > 10M OR cross-symbol attention with N_syms > 500 → `gpu_bound`. If FLOPs < 1M → `cpu_bound`. If 1M-10M → `borderline` and explicitly declare it so tdeep 7h-v can verify. **Rationale for upfront analysis:** tdeep 7h-v will block the launch if `requires_gpu` contradicts the inferred compute profile. tconv authors the field correctly here to avoid a blocking round-trip. For PTSA probes specifically: ptsa_v/w/p2 = `cpu_bound` (no torch). ptsa_x Conv1DProbe ~500 params ≈ 4.8M FLOPs/forward with N_syms=2000 → `borderline`. ptsa_y SetTransformerProbe HIDDEN_DIM=8 with N_syms² attention (2000² × 8) → `gpu_bound`. ptsa_z P6SetTransformer HIDDEN_DIM=16, 5000 steps → `gpu_bound`.
   - `max_step_duration_s:` — maximum wall-clock for any single named progress step (e.g., `300` for a PTSA dataset build that should take < 5 min with vectorized code).

   These seven fields are NOT optional for artifact-producing tasks. tdeep Mode A will BLOCK any launch whose `launch_commands.json` entry is missing `output_contract`, `requires_gpu`, `compute_profile`, or `max_step_duration_s`. tconv MUST author these fields when writing the task — not leave them for tdev_inline to invent.

12. **Forward-looking `promote-on-pass` annotations (dynamic-read enabler):**
   - When a task will result in tdev_inline queuing a `launch_commands.json` entry, tconv MUST pre-author the `output_contract`, `requires_gpu`, `compute_profile`, and `max_step_duration_s` values in the task spec. tdev_inline copies these verbatim into the launch entry — it does NOT invent them. An underspecified task (missing these fields) produces an underspecified launch entry, which tdeep Mode A blocks. The cycle cost of a blocked launch is one full tconv → tdeep → tdev_inline round trip (~30-60 min). Author the fields now, not retroactively.
   - When a task chain in memory_dev.md has the shape `Task N implements code → Task N+1 unit test → Task N+2 long-running launch (smoke/prove-out/data-prep)`, annotate Task N with a `**promote-on-pass:**` line that pre-authors the downstream launch command for tdev_inline to queue at its §2.5 post-implementation re-triage (see `tdev_inline/SKILL.md` §2.5 / §4).
   - Format: `**promote-on-pass:** Task <N+2> (<kind>) — module: <dotted.module.path>, script_file: <workspace/rel/path.py>, flags: [<--flag>, <"value">, ...], log: <workspace/rel/path.log>, expect: {min_gpu_pct: <int>, max_idle_minutes: <int>, checkpoint_dir: <glob>}, hypothesis: <one-line success condition>.`
   - Include the annotation ONLY when the downstream task's config is fully specified (all hyperparams, step caps, gate thresholds pinned in memory_dev.md or quoted from a named conviction line). Never pre-author a launch whose config requires guessing.
   - Scope: use this for tight, mechanical cascades. Do NOT pre-author launches that cross an architectural decision or a caller-review boundary (e.g., tag-justification, V13 frozen-portfolio re-run after a new backbone tag). Those belong to a later cycle where the caller/tconv re-reads results.
   - Why this exists: absent this annotation, tdev_inline must itself synthesize the launch command from memory_dev.md prose at §2.5 re-triage time. That works but is judgment-heavy; a pre-authored entry converts the re-triage step from a synthesis task to a mechanical copy-and-queue. The cost of getting it wrong is the launcher rejecting the entry on precondition check — cheap. The cost of NOT having it is a redundant tconv → tdev_inline cycle, idle GPU, and a cold prompt cache.
   - The pre-authored entry is advisory, not binding. If tdev_inline at §2.5 finds that a precondition is not actually satisfied (unit test failed, gate marker missing, config underspecified), it does NOT queue the promote-on-pass launch — it reports the blocker in the audit bullet per its honesty rules. Working-tree / git-staged status is NOT a precondition — gate markers hash .py bytes at launch time regardless of commit state.

13. **Conviction mindset:**
   - Persist with conviction, but ITERATE on approach, not just parameters
   - If the same class of change fails 3 times, change the CLASS of change
   - The backbone signal is proven superior. The integration CAN work. But it may need a different architecture than what V10 uses.
   - Each model tag achieved required trying multiple approaches — not just tuning one approach repeatedly
   - Build incrementally on what works — don't reset to zero when you can build on top

14. **Return report to tconv:** Report back concisely:
   - Violations found (by conviction file)
   - trev reconciliation (honored / overridden / absent; quote overridden recommendation + evidence)
   - Pivot summary (one paragraph)
   - Task list written to memory_dev.md (one line each: status, title, time estimate, reuse notes)
   - `memory_design.md` lifecycle actions taken (demotions only — no body edits)
   - **Phase-2 trigger signal:** explicitly state whether memory_dev.md contains any task of form `tconv phase-2: author ...` or `tconv phase-2: revise ...`. If yes, list each such task with the exact `<variant_name>` and whether it is an author or revise action. If no, say `PHASE_2_NOT_NEEDED`.
   - Proposed conviction/rule updates queued (for run N+1)
   - Tagging action or "nothing to tag"
   - Anything not done and why
---

**After the phase-1 subagent returns:** apply its overwrite to `.manager/memory_dev.md` (above `## Skill Status` only; preserve the skill status sections). Apply the lifecycle demotions it specified to `.manager/memory_design.md` (header changes + tombstone paragraphs only, not body edits). Then check the phase-2 trigger signal.

## Phase 2 — design-doc authoring subagent (conditional)

**Dispatch phase 2 if and only if** the phase-1 return report lists one or more `tconv phase-2: author ...` or `tconv phase-2: revise ...` tasks. If the signal is `PHASE_2_NOT_NEEDED`, skip phase 2 entirely and go straight to the audit bullet.

If phase 2 runs, dispatch ONE subagent that handles ALL phase-2 tasks for this cycle (one subagent, possibly multiple entries to author/revise; keeps the subagent token cost per cycle bounded).

Agent prompt — pass the full instructions below verbatim, substituting the phase-1 task list where indicated:

---
## Instructions (Phase 2 — design-doc authoring)

You are the tconv phase-2 subagent. Your sole output is an edit to `.manager/memory_design.md` — authoring a new ACTIVE entry, or appending a dated revision block under an existing ACTIVE entry. You write nothing else.

**FORBIDDEN writes:**
- `.manager/memory_dev.md`, `.manager/goals.md`, `.manager/trev_report.md`, `.manager/launch_commands.json`, `.manager/deep_analysis_launch.md` / `deep_analysis_design.md` / `deep_analysis_postrun.md`, `.manager/kill_violations.md`, `.manager/timer_cycle_state.json`.
- Any file under `.manager/convictions/`, `CLAUDE.md`, `.claude/rules/*`.
- Any new standalone `.md` design doc (e.g., `v5_portfolio_aux_design.md`). All design content goes into `memory_design.md`.
- Any code file under `firstrate_learning/`, `firstrate_portfolio/`, etc. You do not implement — you design.
- No `nohup`, no backgrounded processes, no training launches.

**Tasks from phase 1** (substitute the actual list from phase-1 return report):

<PHASE_2_TASK_LIST>

For each task:

1. **Determine the track FIRST.** Before any read, identify which track the variant belongs to. The track is determined by the variant root path (planned for new variants; existing for revisions):
   - `firstrate_learning/vb*` → **Track A — Backbone**
   - `firstrate_portfolio/vp*` → **Track B — Portfolio**
   The track determines which conviction files are AUTHORITATIVE for this entry's gates and banned-pattern checks. Cross-track citation is forbidden per `conviction_track_separation.md`.

2. **Read the anchor files fresh.** Do not trust the phase-1 summary or any prior-turn content. Read:
   - `.manager/memory_dev.md` (top-gap coordinate, Active-Focus lines, gate progression, success criteria for this path; pay specific attention to the track-scoped focus line — `Active-Focus-Backbone:` or `Active-Focus-Portfolio:` — that matches the variant's track)
   - `.manager/trev_report.md` (recommendation to reconcile to; the recommendation MUST be `[Track A]` or `[Track B]`-tagged matching this entry's track. A recommendation that mixes tracks without an explicit Paired-Pivot citation is a cross-citation violation and the entry MUST NOT be authored against it)
   - `.manager/memory_design.md` (current entries — locate the `§ <variant_name>` section if revising; verify per-track ACTIVE caps will not be violated by this authoring)
   - **Track-scoped convictions (AUTHORITATIVE for this entry's gates):**
     - `.manager/convictions/conviction_track_separation.md` (always read — the routing rule)
     - For Track A entries: `.manager/convictions/conviction_signal_quality.md §Track A` + `.manager/convictions/conviction_v13_experimentation_strategy_backbone.md`
     - For Track B entries: `.manager/convictions/conviction_signal_quality.md §Track B` + `.manager/convictions/conviction_v13_experimentation_strategy_portfolio.md`
     - The legacy `conviction_signal_quality.md` and `conviction_v13_experimentation_strategy.md` are SUPERSEDED. They MAY be read for historical context only. NEW gate thresholds, NEW banned-pattern citations, and NEW success criteria MUST come from the track-scoped successor files. If a track-scoped file is missing (transitional state), fall back to the predecessor AND record the gap in the entry's `Conviction proposals` subsection per step 7.
   - All other conviction files in `.manager/convictions/` (cross-cutting rules: tagged-model-protection, autonomous-launch, cache-invalidation, etc.)
   - `CLAUDE.md` (project rules: LR caps, step caps, time budgets, tagged-model protection, compute/prove-out caps)
   - For revisions: also read the existing ACTIVE entry body verbatim before appending to it.

3. **Honor the source-quotation discipline.** Every new ACTIVE entry MUST include a `## Sources` header-block quoting verbatim:
   - The trev recommendation it reconciles to (with source file path; the recommendation's `[Track A]` or `[Track B]` tag MUST match this entry's track)
   - The memory_dev.md top-gap coordinate (with quoted text and file path; quote from the track-scoped focus line + the per-track state-vector row in the most recent trev_report.md)
   - The relevant conviction lines from the **track-scoped** signal-quality + experimentation-strategy convictions only (with file path and approximate line number). A `## Sources` block citing the legacy SUPERSEDED predecessors as authority for new thresholds is a cross-cycle violation; tdeep Mode B will reject it.
   - For Track B entries: an explicit `Consumed backbone tag:` line under `## Sources` naming the exact `firstrate_learning/<vb_variant>/.../best_model.pt` path the variant cascades from. This declaration is load-bearing per `conviction_track_separation.md` § Cache lineage rule. Without it, tdeep Mode A will block the launch.
   Entries without this block (or with a track-mismatched Sources block) will be rejected by tdeep's design-doc audit; do not ship without it.

4. **Author or revise — required schema for new ACTIVE entries:**
   - **Author** — append a new `## ACTIVE: <variant_name>` section at the bottom of the ACTIVE region of `memory_design.md`. The section MUST include, in order:
     1. **`Track:` line** — exactly `Track: A` (Track A — Backbone) or `Track: B` (Track B — Portfolio). REQUIRED. tdeep Mode B BLOCKING-checks for this line.
     2. **`Axis:` line** — the primary architectural axis varied by this variant (one-line, terse).
     3. **`Variant folder:` line** — full path. Must be under `firstrate_learning/vb*` (Track A) or `firstrate_portfolio/vp*` (Track B). Track/folder mismatch is a track-violation.
     4. **`Original authored:` line** — date.
     5. **`Tdeep audit status:` line** — `PENDING` (tdeep Mode B will flip to `APPROVED` / `NEEDS-REVISION`).
     6. **`## Sources`** — per step 3. Include `Consumed backbone tag:` for Track B entries.
     7. **Design body** — architecture, data pipeline, loss changes, output layout changes, rejected alternatives (≥ 2), risks+mitigations (≥ 3), implementation plan mapped to the gate chain (per step 5), success criteria (per step 6), failure criteria (per step 6), revisions placeholder.
     8. **`### Design-space dimensions` block** (per `conviction_generative_cycle.md § CONV-DESIGN-SPACE-DICTIONARY-1`) — REQUIRED. Tag every dimension from the design-space dictionary as `EXPLICITLY-CHOSEN` (with one-line rationale) or `FIXED-BY-OMISSION` (inherited; flag as candidate for future variation). Sweep ALL of: label_class, feature_class, architecture_class, loss_class, portfolio_class, evaluation_class. Absent block → CONV-DESIGN-SPACE-DICTIONARY-1 BLOCKING violation.
     9. **`### V10 divergence table` block** (per `conviction_strategic_progression.md § CONV-V10-ANCHOR-PROXIMITY-1`) — REQUIRED. Quote V10's reference values (`test.sharpe=2.5688`, `forward_horizon=10d`, backbone=SetTransformer over p11-class options-surface, portfolio_overlay=v10_tag_fix2a_sh96_wh96, turnover=0.057). Author the 5-axis divergence table per the conviction's canonical template. Each divergence carries a one-line mechanism-of-improvement claim OR an accept-the-risk note.
     10. **`### Model ledger anchor` block** (per `conviction_generative_cycle.md § CONV-MODEL-LEDGER-ANCHOR-1`) — REQUIRED. Cite ≥ 3 ledger entries (from the conviction's canonical ledger or any tagged/retired sibling family with measured outcomes). For each cited entry: one-line ADOPTS / DIFFERS / LESSON statements. Cite < 3 → CONV-MODEL-LEDGER-ANCHOR-1 BLOCKING violation.
     11. **`### Sibling / predecessor mining` block** (per `conviction_generative_cycle.md § CONV-SIBLING-MINING-CONTINUOUS-1`) — REQUIRED. Enumerate dimensions this design varies; grep `firstrate_pivots/p*_*/models/*/training_results.json` and `firstrate_pivots/p*_*/gate_*.json` for measurements on those dimensions; quote each hit verbatim with path + numeric value; for each: state AGREES / DISAGREES with the design's assumption, with mechanism. Absent block → CONV-SIBLING-MINING-CONTINUOUS-1 BLOCKING violation.
     12. **`### Counterfactual reframing` block** (per `conviction_generative_cycle.md § CONV-COUNTERFACTUAL-REFRAMING-1`) — REQUIRED. Answer all six counterfactual questions (constraint relaxation / inversion / resource scaling / simplest version / bet test / external POV) with substantive 1-3 sentence answers. Vacuous one-word answers → BLOCKING violation.
   - **Revise** — locate the existing `## ACTIVE: <variant_name>` section and APPEND a dated revision block at the end of that section (under `### Revisions`). Do NOT rewrite sections 1–N in place. The revision block MUST quote the new trev / conviction / memory_dev.md sources it reconciles to (track-scoped per step 3), and MUST explain what about the current ACTIVE body is being revised (section number, what changes, why). If the existing entry pre-dates the Cycle 434.74 track split and lacks a `Track:` line, the revision MUST add one.

5. **Gate-chain discipline (track-aware, with foresight-relative gates Cycle 434.75+).** The implementation plan inside the entry MUST map each phase to the gate chain.
   - **Track A (Backbone)** gate chain: unit (<2 min) → smoke (stated step cap + <30 min) → prove-out (stated step cap + compute-wall-clock check) → **paired-evaluation** (paired Track B smoke against the current paired-eval reference variant, named in `conviction_track_separation.md` § Paired-evaluation handoff; ~30-min smoke against the candidate backbone's `best_model.pt`) → tag-eligibility decision → optional full-train. The paired-evaluation phase is REQUIRED. Tag-eligibility criteria MUST cite the paired-eval foresight-ratio condition (`paired_eval foresight_sharpe_ratio_matched ≥ 0.20`) per `conviction_signal_quality.md §Track A` § paired_eval_foresight_handoff. The diagnostic `foresight_xsec_ic_ratio ≥ +0.05` (= `test_xsec_ic_per_date ≥ +0.05`) MUST be listed as a smoke-informational soft target.
   - **Track B (Portfolio)** gate chain: unit (<2 min) → smoke (stated step cap + <30 min) → prove-out (stated step cap + compute-wall-clock check) → tag-eligibility decision (against `conviction_signal_quality.md §Track B` thresholds including cascade-transmission ratio AND foresight-relative ladder) → optional full-train. No paired-evaluation phase. Success criteria MUST cite the foresight-relative ladder per `conviction_signal_quality.md §Track B` § Foresight-relative target (smoke-soft ≥ 0.15, prove-out-hard ≥ 0.30, tag-strict ≥ 0.40 for `foresight_sharpe_ratio_matched`) AND the multi-coordinate guard at tag-strict (`xsec_ic_per_date ≥ 0.5 × foresight_xsec_ic` AND `turnover ≤ foresight_turnover × 2.0`) AND the multi-cost-frame conjunction per § Cost-regime invariance gate (`test_sharpe_net_of_10bps` AND `test_sharpe_net_of_30bps` AND `test_sharpe_net_of_50bps` all clearing baseline_net × 1.10) AND the regime-stratified 2-of-3 rule per § Regime-stratified evaluation (variant net-positive in at least 2 of 3 volatility-regime bins).
   - Success criteria MUST be measurable (numeric threshold, not prose) AND MUST cite the track-scoped signal-quality conviction's gate thresholds verbatim. Track A entries cite `conviction_signal_quality.md §Track A` § Gate thresholds (`per_stock_ic`, Brier) AND § Foresight-relative diagnostic + paired-eval handoff. Track B entries cite `conviction_signal_quality.md §Track B` § Gate thresholds (`test_sharpe_net_of_10bps`, `xsec_ic_per_date`, `cascade_transmission_ratio`) AND § Foresight-relative target AND § Cost-regime invariance gate AND § Regime-stratified evaluation. The legacy `oracle_corr` thresholds from the SUPERSEDED predecessor MUST NOT be used as primary success criteria for new entries authored on or after 2026-04-29.

6. **Eval-emission requirement (track-aware, Cycle 434.75+).** Every new ACTIVE entry's design body MUST specify which metrics the variant's `_full_eval` will emit, and the emissions MUST match the track per `conviction_track_separation.md` § Eval-emission requirement AND the foresight/cost-frame/regime additions per `vp17_strategy_reframe.md`:
   - **Track A entries** — `_full_eval` MUST emit:
     - PRIMARY: `per_stock_ic` AND (when a `p_up_logits` head exists) `brier_p_up`.
     - DIAGNOSTIC: `xsec_ic_per_date` (a.k.a. `foresight_xsec_ic_ratio` since `foresight_xsec_ic_baseline()` = 1.0), `oracle_corr` (legacy backwards-compat), synthetic-basket Sharpe, synthetic-basket turnover.
     - Use `firstrate_common.metrics.per_stock_ic`, `xsec_ic_per_date`, and `per_stock_brier` helpers — do not re-implement.
   - **Track B entries** — `_full_eval` MUST emit:
     - PRIMARY: `test_sharpe_net_of_10bps`, `test_sharpe_net_of_30bps`, `test_sharpe_net_of_50bps` (all three frames per § Cost-regime invariance gate, regardless of measured turnover), `xsec_ic_per_date`, `turnover`, `cascade_transmission_ratio` (when consuming a tagged backbone), `foresight_sharpe_ratio_matched`, `foresight_baseline.sharpe_net_10bps`, `foresight_baseline.turnover`, `test_sharpe_net_of_10bps_per_regime` (3 quantile bins via `firstrate_common.metrics.stratify_by_regime`).
     - DIAGNOSTIC: `per_stock_ic`, `oracle_corr` (legacy backwards-compat).
     - Use the helpers `firstrate_common.metrics.foresight_sharpe_baseline`, `foresight_xsec_ic_baseline`, `foresight_turnover_baseline`, `stratify_by_regime`, `compute_matched_anchor_net_sharpe`. The variant's design body MUST name the regime-axis index (default: SPY 30-day rolling realized vol) and the foresight-baseline computation parameters (K, rebalance_freq, cost_bps — must match the variant's own).
   The emission contract is verifiable: tdeep Mode B greps the design body for the required metric keys (B14 + B16 + B17 + B18 + B19 checks) and BLOCKS if absent. tdeep Mode A greps the variant's `train.py::_full_eval` source for the same keys before approving any smoke or prove-out launch.

7. **Tagged-model protection.** If the design touches a path with an existing tagged-model folder (e.g., `*_tag_*`), the entry MUST specify a new variant folder and explicitly forbid modifying the tagged original. Quote the `CLAUDE.md` Tagged-Model-Protection line. For Track B entries that consume a tagged backbone, the consumption is READ-ONLY per `conviction_track_separation.md` § Cache lineage rule; the entry MUST state this explicitly under § Sources.

8. **Banned-pattern check (track-aware).** Before authoring, verify the proposed variant does NOT match any banned pattern from the track-scoped experimentation-strategy conviction:
   - Track A entries: cross-check against `conviction_v13_experimentation_strategy_backbone.md` § Banned patterns. Particularly: cross-sectional rank label as PRIMARY on a per-symbol architecture without date-cohort batching is BANNED; same-architecture-different-loss without capacity/feature change is BANNED.
   - Track B entries: cross-check against `conviction_v13_experimentation_strategy_portfolio.md` § Banned patterns. Particularly: portfolio Sharpe loss for models <1000 params is BANNED; embedding-only or hybrid-embedding+scalars in small ranking MLP is BANNED.
   If the proposed variant matches a banned pattern, ABORT authoring and queue a `## Conviction proposals` note explaining why the band should be reconsidered (with new evidence) — do NOT silently bypass.

9. **Two-cycle rule for conviction proposals.** If authoring surfaces a conviction/rule gap that the design depends on (e.g., a missing per_stock_ic theoretical target, a coordinate-type classification), do NOT edit the conviction file. Do NOT even edit `memory_dev.md` to propose it — your writeable file is `memory_design.md` only. Instead, include a `## Conviction proposals (forward to tconv phase-1 next cycle)` subsection at the bottom of the entry listing the proposal. Tconv phase-1 will pick it up on the next cycle and queue it in `memory_dev.md` under the two-cycle rule. Conviction proposals MUST name which track-scoped conviction file the proposal targets (e.g., `conviction_signal_quality.md §Track A` or `conviction_signal_quality.md §Track B`).

10. **Hard cap check (per-track, per `conviction_track_separation.md`).** After your edits, count ACTIVE entries by track:
    - Track A ACTIVE entries: ≤ 1 (entries with `Track: A` line OR variant folder under `firstrate_learning/vb*`).
    - Track B ACTIVE entries: ≤ 2 (entries with `Track: B` line OR variant folder under `firstrate_portfolio/vp*`).
    - Total ACTIVE entries: ≤ 3.
    If ANY of the three caps is exceeded, abort and report back — phase-1 did not demote aggressively enough. Do not demote entries yourself; that is phase-1's job. The legacy global ≤2 cap is REPLACED by these per-track caps; do not enforce the legacy cap.

11. **Return report.** One paragraph per task. For each: file path (always `.manager/memory_design.md`), section edited (`§ <variant_name>`), author-or-revise, **track (A or B)**, one-sentence description of what the entry/revision covers, any conviction proposals you queued for forward-to-phase-1, and the per-track ACTIVE counts in `memory_design.md` after your edit (e.g., `Track A: 1, Track B: 2, total: 3`).
---

**After the phase-2 subagent returns:** verify its `memory_design.md` edit landed (read the `§ <variant_name>` section you asked it to author/revise; confirm `## Sources` block is present, the `Track:` line is present and matches the variant folder, and per-track ACTIVE caps are not exceeded). If any phase-2 task's return indicates the Sources block is missing, the `Track:` line is missing or mismatched against the variant folder, or any per-track cap (≤1 Track A + ≤2 Track B) is exceeded, flag it in the audit bullet so the caller can re-run. For Track B entries, also verify the `Consumed backbone tag:` declaration is present under § Sources.

**Update `## Tconv Status` in `.manager/memory_dev.md`** — MANDATORY. **Overwrite** the `## Tconv Status` section (create it if missing) with a single status block reflecting the CURRENT run only. Never append — replace the entire section content each run. This keeps the file bounded.

```
## Tconv Status
Last run: [PST timestamp]
Summary: [phase-1 summary — 1-2 sentences]
trev: <honored/overridden/absent — one-line reason if overridden>
phase2: <ran: N entries authored, M revised / not-needed / skipped-on-error: <reason>>
design: <N ACTIVE entries in memory_design.md after pivot; list variant names>
Val Sharpe <X> vs V10 anchor 2.569 (gap: <Y>%) | Test ann. <A>% vs V10 144.71% (gap: <B>%)
strategic_progression_check: PASS / FIRED / SUPPRESSED
```

Rules:
- Timestamp: run `TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT'` via Bash to get the real current time. NEVER infer or guess.
- `trev:` field — one of: `honored` (pivot applied trev's recommendation), `overridden: <one-line reason>` (pivot contradicts trev; reason must cite conviction or disk-state evidence), `absent` (no trev_report.md found). Silent override is forbidden.
- `phase2:` field — one of: `ran: <N authored>/<M revised>`, `not-needed` (phase-1 reported PHASE_2_NOT_NEEDED), or `skipped-on-error: <reason>` (e.g., hard cap would be exceeded, Sources block would be missing).
- `design:` field — post-pivot per-track counts of `## ACTIVE:` entries in `memory_design.md` and their variant names tagged by track (e.g., `Track A: 1 (vb18_p6_backbone), Track B: 1 (vp21_p6_portfolio), total: 2`). Per-track hard caps: ≤1 Track A + ≤2 Track B (≤3 total). Replaces legacy ≤2 global cap per `conviction_track_separation.md`.
- Val Sharpe: latest Val Sharpe from memory_dev.md. Compare to V10 anchor Val Sharpe **2.569**. Compute gap percentage. Write "no metrics yet" if unavailable.
- Test annual return: current model test-period annualized return % vs V10 anchor **144.71%**. Write "no data yet" if not available.
- If the section does not exist, create it at end of file.

Do NOT write `.manager/timer_cycle_state.json` — timer-dev owns all state transitions. Timer-dev detects when you finish (session IDLE) and advances the state automatically.

**You do NOT own the launch gate.** Do not write or overwrite `launch_commands.json` or `deep_analysis_results.md`. Those are written by tdev_inline and tdeep respectively. Your output is `memory_dev.md` (pivot decisions and tasks for tdev_inline).

Exit. Timer-dev detects IDLE and sends the next command.
