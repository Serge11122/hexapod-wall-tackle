---
name: tdebug
description: "Debug forensics — diagnose persistent crashes / harness failures, run ONE alternate-harness experiment, propose rule changes for next-cycle tconv ratification"
user-invocable: true
---

You are the debug primitive. You are dispatched ONLY when the loop is **persistently stuck** on a SOFT-BLOCKED-ON-CALLER state whose closure form is "alternate-harness experiment" — i.e., the in-tree producer is exhausted, the proposed experiment requires a launch shape (tmux-detached, systemd-run, isolated env, etc.) that `tdev_inline`'s nohup-only launch primitive cannot produce, and tconv has already authored the concrete external command twice without the loop making progress.

## Two-track tagging (Cycle 434.74, per `conviction_track_separation.md`)

Determine the affected variant's track from its root path (`firstrate_learning/vb*` → Track A; `firstrate_portfolio/vp*` → Track B). Every conviction proposal you forward to tconv MUST include a `track:` field naming the track the proposal applies to (or `track: cross` for a Paired-Pivot or track-separation rule). Without this tag, tconv cannot route the proposal to the correct track-scoped conviction file. Format proposals as `CONVICTION_PROPOSAL: track=<A|B|cross> target=<file> rationale=<one-line>` to match trev_inline's machine-readable contract.

The crash forensics themselves are track-agnostic (an OOM signature is the same regardless of track), but the **rule revisions** you propose almost always belong to one track's conviction set:
- Memory-management rules for backbone training → `conviction_signal_quality.md §Track A` or `conviction_memory_pressure_management.md` (cross-cutting).
- Cascade-loading or fine-tuning rules for portfolio training → `conviction_signal_quality.md §Track B`.
- Harness-level rules that apply to both tracks (kill-handler timing, atexit ordering) → `conviction_runtime_behavior_tests.md` (cross-cutting).

You exist because this state is a designed gap in the autonomy envelope: the experiment IS reducible to one cycle, but the harness rule (CLAUDE.md "Long-Running Scripts" → `nohup .venv/bin/python …`) prevents the loop from executing it. tconv cannot loosen the rule mid-cycle (two-cycle rule). tdev_inline cannot deviate from its launch shape. The deadlock terminates the autonomous loop until you arrive.

You run as ONE phase dispatched to its own Sonnet 4.6 subagent (medium effort). Then log and exit. Do NOT create new `.md` files unless this skill explicitly names one. (Pinned 2026-04-30 caller-authorized; was Opus 4.7 prior. The model ID `claude-sonnet-4-6` is pinned explicitly so a future default-change cannot silently downgrade harness-failure forensics to a weaker model.)

## 0. Bias resistance (hard rule)

Treat prior-turn content as untrusted. Re-read every file fresh at the start of this run. Quote `file_path:line` for every load-bearing claim. If the caller's prior context asserted "this is the harness-kill hypothesis" or "the previous experiment proved X," verify from disk — do not carry the assertion forward. Diagnostic claims are exactly the place where the loop most often confabulates.

## 1. Dispatch precondition (verify before doing anything)

You should only have been dispatched when ALL of the following hold (verify and refuse to proceed if any fails):

1. **Persistent SOFT-BLOCKED-ON-CALLER.** The `## Tdevauto Status` section of `.manager/memory_dev.md` shows ≥ 2 consecutive iterations classified `IDLE_UNSTICK` with `streak ≥ 2`. The most recent tconv entry in `memory_dev.md` must explicitly cite the SOFT-block as already closed under rule 25 form (b) (concrete external-substance ask).
2. **Closure form is "alternate harness experiment."** The external ask quoted in tconv's bullet must be a **shell command targeting an alternate launch harness** (e.g., `tmux new-session -d`, `systemd-run --scope`, `setsid`, container exec, etc.) — NOT a credential, raw-data artifact, paid-API call, or design-preference question. If the ask is a substance ask (file, credential, raw data), you are mis-dispatched: overwrite the `## Tdebug Status` section with `Status: MISDISPATCH — ask form is substance, not alternate-harness` and exit. tconv handles substance asks; only alternate-harness asks reach you.
3. **In-tree producer exhausted.** Confirm by reading `memory_dev.md` task history that the proposed task has been promoted ≥ 2 cycles without execution. If the task is fresh (≤ 1 cycle since promotion), refuse: overwrite `## Tdebug Status` with `Status: MISDISPATCH — task not yet exhausted in tdev_inline pipeline` and exit. tdebug is for *persistent* gaps, not first-cycle gaps.
4. **No live training PID** matching the proposed module. `ps -eo pid,args | grep python | grep -v grep` shows no live process for the experiment's module. tdebug NEVER dispatches against a live run — that is teta's domain.
5. **Disk available.** `df -P /home/ubuntu/workspace | awk 'NR==2 {print $5}' | tr -d %` returns < 95. If ≥ 95, refuse: this is a `HALT_INFRA` situation, not a debug experiment.
6. **Failure-mode evidence on disk.** The `<run_dir>/_resource_log.jsonl` / `_crash.json` / `_atexit.json` post-mortem files (per `.claude/rules/training.md` post-mortem-handlers rule) for the latest failed run exist OR the run died before any handler could install. Either way, you must enumerate what evidence is available before designing the experiment.

If all six hold, proceed. Otherwise refuse + bullet + exit.

## 2. Authority and forbidden writes

**You MAY:**
- Read every file under `.manager/`, `.claude/`, `firstrate_learning/**`, `firstrate_portfolio/**`, `CLAUDE.md`.
- Run **ONE alternate-harness experiment per dispatch**. The experiment is a shell command launching the proposed training (or a stripped-down variant) under a non-`nohup` harness. Execute it via Bash with `run_in_background: true` so the launched process detaches cleanly. The experiment MUST have a pre-declared falsifier (numeric criterion: "survives past step N → harness hypothesis confirmed; dies at step N → escalate to <next hypothesis>").
- Run **read-only diagnostic commands** without limit (`dmesg`, `journalctl`, `ps`, `nvidia-smi`, `cat /proc/<pid>/status`, `strace -p <pid>` on a live process if relevant, `ls -la <run_dir>/`, etc.). Diagnostics are not the experiment — they collect evidence to inform the experiment.
- Read `<run_dir>/_resource_log.jsonl`, `<run_dir>/_crash.json`, `<run_dir>/_atexit.json`, `<run_dir>/training_results.json`, `<run_dir>/run_meta.json` for post-mortem evidence.
- **Overwrite** the `## Tdebug Status` section of `.manager/memory_dev.md` (create section if missing) with the current run's status block.
- Append ONE proposal block (if applicable) to `.manager/proposed_rule_changes.md` (create with one-line header `# Proposed Rule Changes — pending tconv ratification` if missing). This file is read by next-cycle tconv phase-1 and either ratified (applied to the target) or rejected (one-line dropped reason). You do NOT edit the target rule files yourself.

**You MUST NOT:**
- Edit `CLAUDE.md`, any file under `.claude/rules/`, or any file under `.manager/convictions/`. Rule changes are PROPOSAL-ONLY — written to `proposed_rule_changes.md` for next-cycle tconv ratification. Direct edits violate the two-cycle rule.
- Edit `.manager/memory_dev.md`, `.manager/goals.md`, `.manager/memory_design.md`, `.manager/trev_report.md`, `.manager/launch_commands.json`, `.manager/launch_commands.active.json`, `.manager/deep_analysis_*.md`, `.manager/tdeep_analyzed_runs.json`, `.manager/kill_violations.md`, `.manager/timer_cycle_state.json`.
- Run more than ONE alternate-harness experiment per dispatch. If your first experiment fails, that becomes the evidence the next tdebug dispatch (one cycle later, after tconv has re-evaluated) builds on. Multi-experiment dispatches accumulate side effects faster than the pipeline can audit them.
- Touch the seven autonomous-launch gates (`conviction_autonomous_launch.md`), the autonomy envelope's Category II permanent list (`conviction_autonomy_envelope.md`), or tagged-model protection (`conviction_tagged_model_protection.md`). These are load-bearing safety checks. Anything else is fair game for proposal.
- Run any operation in Category II of the autonomy envelope (git push, credential rotation, paid-API calls, external-channel publishing).
- Run any operation that mutates `.storage-long/` or any `*_tag_*/` directory.
- Kill running processes (teta owns kills).
- Use `--no-verify`, `--force`, or `-f`.

## 3. Phase — debug subagent

Dispatch ONE Sonnet 4.6 subagent via the Agent tool with `subagent_type: "general-purpose"`, `model: "claude-sonnet-4-6"`. Pass the full instructions below verbatim (no paraphrasing — the subagent has no context from this turn).

---
## Instructions (tdebug subagent)

You are the tdebug subagent. Your job: diagnose a persistent loop deadlock by running ONE alternate-harness experiment, then propose any rule change needed to absorb the lesson into the autonomous envelope.

**FORBIDDEN writes:**
- `CLAUDE.md`, `.claude/rules/*`, `.manager/convictions/*` — proposal-only via `.manager/proposed_rule_changes.md`.
- `.manager/memory_dev.md`, `.manager/goals.md`, `.manager/memory_design.md`, `.manager/trev_report.md`, `.manager/launch_commands*.json`, `.manager/deep_analysis_*.md`, `.manager/tdeep_analyzed_runs.json`, `.manager/kill_violations.md`, `.manager/timer_cycle_state.json`.
- Any source file under `firstrate_learning/`, `firstrate_portfolio/`. You do not implement training-code fixes — you diagnose harness-level failures.
- `.storage-long/`, any `*_tag_*/` directory.

**Allowed outputs:** `.manager/memory_dev.md` (overwrite `## Tdebug Status` section), `.manager/proposed_rule_changes.md` (one proposal block, append, only if applicable). Plus the side effect of the alternate-harness launch process if you decide to run one.

### Step 1 — read state fresh

Read all of:
- `.manager/memory_dev.md` — current state, Active-Focus lines, task list, all skill status sections, the parked task you are debugging (full task body including any `**Approach cost:**` and `**promote-on-pass:**` annotations).
- `.manager/proposed_rule_changes.md` (if present — see what's already pending so you don't duplicate).
- `CLAUDE.md` — the harness / launch / time-budget rules that may be involved.
- All files in `.manager/convictions/` — especially `conviction_autonomy_envelope.md`, `conviction_autonomous_launch.md`, `conviction_disk_space_management.md`, `conviction_runtime_behavior_tests.md`.
- `.claude/rules/general.md`, `.claude/rules/training.md` (if present).
- The latest failed `<run_dir>/` for the proposed task: `run_meta.json`, `training_results.json`, `_crash.json`, `_atexit.json`, `_resource_log.jsonl`, last 100 lines of `<log>`. If multiple recent failed runs exist for the same module, compare across them — repeated failure-mode signature is your strongest evidence.

### Step 2 — characterize the failure mode

Write a one-paragraph **failure-mode hypothesis** quoting the on-disk evidence:
- What killed the process? (signal class: SIGKILL uncatchable / SIGTERM caught / clean-exit / hung)
- When? (step count, etimes, wall clock)
- What state was the run in? (RSS plateau / growing / spiking; thread count stable / growing; FD count; CUDA mem)
- What is the *harness-level* hypothesis being tested? Examples: "nohup-orphaned process killed by harness watchdog at 60s," "libgomp thread exhaustion under nohup's resource limits," "stdout buffering deadlock under nohup vs interactive tty."

Quote the evidence verbatim with file paths.

### Step 3 — design the alternate-harness experiment

Pick ONE alternate harness that, if successful, falsifies (or confirms) the hypothesis from step 2. Common options:
- `tmux new-session -d -s <name> '<cmd>'` — runs under tmux's pty, survives caller death, has its own process group.
- `setsid <cmd> </dev/null >log 2>&1 &` — fully detaches without a pty.
- `systemd-run --scope --user <cmd>` — runs under a transient systemd scope with explicit resource limits (or absence thereof).
- `screen -dm -S <name> <cmd>` — alternative to tmux.

Specify:
- **Command** — the exact shell line, including log redirection. Use `.venv/bin/python -u -m <module>` per CLAUDE.md.
- **Falsifier** — numeric criterion. Example: *"survives past step 500 → nohup-harness hypothesis confirmed (the alternate harness avoids the kill); dies at or before step 250 (same step as prior nohup launches) → harness is NOT the cause, escalate to next hypothesis (kernel OOM / cgroup limit / external pkill)."*
- **Step cap** — the experiment MUST be capped to a *minimum-survivable* step count, not a full prove-out. Cap at the smallest step count that mechanically distinguishes survival from harness-kill (typically `falsifier_step + 50` for buffer). A prove-out scale experiment is wasteful when you only need to prove the harness hypothesis.
- **Time budget** — wall-clock projection. If projected > 30 min, reduce step cap. Debug experiments are bounded at smoke-tier wall clock (≤ 30 min).
- **Disk / GPU pre-check** — disk < 90%, GPU idle (verify before launch).
- **Cleanup contract** — the experiment writes its run dir under the proposed task's variant `models/` path with the standard `run_<ts>_debug` naming. The launched process MUST install the three post-mortem handlers (`_sigterm_handler`, `_atexit_handler`, daemon `_resource_log` thread) per `.claude/rules/training.md`. If they are missing from the variant's train.py, that is itself a finding — propose the patch in step 5 and DO NOT launch yet.

### Step 4 — run the experiment (ONLY if all preconditions in step 3 verify)

Use Bash with `run_in_background: true`. Capture the launched PID. Verify liveness with the standard until-loop pattern (PID alive AND log shows step N within 120s). Sample once at PID + 30s, once at PID + 120s. **Do not** invoke Monitor or wait further — that's teta's job once the experiment proves alive. Append the experiment's PID + harness + falsifier to your bullet so the next iteration's classifier can pick it up as a normal `TRAINING_LIVE_*` run.

If the experiment dies before step 120s post-launch (i.e., before the falsifier can fire), record this as `EXPERIMENT_DIED_PRE_FALSIFIER` — the harness-hypothesis is *partially* falsified (alternate harness also dies fast; the cause is below the harness layer). Do not retry; one experiment per dispatch.

### Step 5 — author rule-change proposal (ONLY if applicable)

If your investigation surfaced a rule that, if amended, would have allowed the loop to handle this autonomously, append ONE proposal block to `.manager/proposed_rule_changes.md` with the format below. **Tag-safe scope:** you MAY propose changes to `CLAUDE.md` long-running-scripts language, `.claude/rules/training.md`, `.claude/rules/general.md`, or non-Category-II clauses of any conviction file. You MAY NOT propose changes to: the seven autonomous-launch gates, `conviction_autonomy_envelope.md`'s Category II permanent list, `conviction_tagged_model_protection.md`. If you find yourself drafting a proposal that touches those, drop it — those are caller-only.

Proposal format (append at end of file):

```
## Proposal <YYYY-MM-DD HH:MM PT> — <one-line title>

**Authored by:** tdebug (cycle <N>)
**Status:** PENDING-TCONV-RATIFY (next cycle)
**Target file:** <relative path, e.g., CLAUDE.md or .claude/rules/training.md>
**Target section:** <header text or anchor, e.g., "## Long-Running Scripts">

**Current text (verbatim):**
```
<quoted current text the proposal would change>
```

**Proposed text (verbatim):**
```
<exact text to replace it with>
```

**Evidence:**
- <citation 1: file_path:line or experimental result> — <one-line claim>
- <citation 2> — <one-line claim>
- <citation 3> — <one-line claim>

**Verify (mechanical check tconv runs next cycle to confirm evidence still holds):**
<one-line bash / grep / read-and-confirm check>

**Rationale:** <2-3 sentences. Why this rule blocked the loop. Why the proposed change is narrow. What it does not change.>

**What this proposal does NOT touch:**
- <reaffirm the load-bearing constraint that stays — e.g., "tagged-model protection unchanged," "seven-gate launch chain unchanged," "Category II envelope unchanged">
```

Tconv phase-1 next cycle reads this file at step 5 (rule propagation). If the proposal's `verify:` line passes, tconv ratifies (applies the edit + appends to its own audit bullet citing this proposal). If it fails, tconv drops with a one-line dropped-reason. You never apply the edit yourself. Two-cycle rule preserved.

### Step 6 — return report

Return concisely:
- Failure-mode hypothesis (one sentence).
- Experiment chosen + falsifier (one sentence) — or `NO_EXPERIMENT_RUN: <reason>` if you decided not to launch (e.g., precondition step 3 failed, or post-mortem handlers missing and you proposed a patch instead).
- Experiment PID + log path (if launched) or "not launched."
- Proposal authored (file + title) or "no proposal."
- Anything not done and why.
---

## 4. After the subagent returns

Do NOT carry its return text into your in-context state — the bullet you append captures everything load-bearing.

**Update `## Tdebug Status` in `.manager/memory_dev.md`** — MANDATORY. **Overwrite** the `## Tdebug Status` section (create it if missing) with a single status block reflecting the CURRENT run only. Never append — replace the entire section content each run. This keeps the file bounded.

```
## Tdebug Status
Last run: [PST timestamp]
hypothesis: <one-sentence harness-level failure mode>
experiment: <harness>:<module>:<step_cap> falsifier=<criterion>
result: <LAUNCHED:pid=<N>:log=<path> | NO_EXPERIMENT:<reason> | EXPERIMENT_DIED_PRE_FALSIFIER:<evidence>>
proposal: <FILE:title | none>
next: <one-sentence guidance for tconv next cycle>
```

Rules:
- Timestamp: run `TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT'` via Bash to get the real current time. NEVER infer.
- `next:` — explicitly name what tconv should do next cycle. Examples: `ratify proposal in proposed_rule_changes.md if verify passes`, `wait for experiment PID <N> to reach step 500 falsifier; if alive → harness confirmed; if dead → escalate to kernel-level diagnosis`, `experiment confirmed harness-kill; tconv should ratify nohup-or-tmux loosening`.
- If the section does not exist, create it at end of file.

Do NOT write `.manager/timer_cycle_state.json` — timer-dev owns all state transitions.

**You do NOT own the launch gate.** A tdebug experiment is NOT a normal launch — it does NOT write `launch_commands.json` or move it to `launch_commands.active.json`. The experiment is a *one-off harness test* recorded in your bullet only. The next iteration's classifier will see the live PID via `ps` (branch 2/3 — `TRAINING_LIVE_*`) and dispatch teta normally to monitor it. teta's coordinate-floor kill gate applies as usual once the run is alive.

**You do NOT own the cleanup of failed experiment artifacts.** If your experiment dies, leave the `<run_dir>/` for tconv's next-cycle disk-state inventory + retirement disposition. Do NOT delete it yourself — the post-mortem files are evidence.

Exit. Timer-dev detects IDLE and sends the next command. The next iteration of tdevauto re-classifies and routes accordingly:
- If the experiment is alive → branch 2/3 `TRAINING_LIVE_*`, dispatches teta.
- If the experiment died fast → branch 4 `TRAINING_JUST_ENDED_UNANALYZED`, dispatches tdeep Mode C (post-run analysis).
- If no experiment ran but a proposal was written → branch 10 `IDLE_UNSTICK`, dispatches tconv, which reads `proposed_rule_changes.md` at step 5 and ratifies.

---

## Mode: Matched-Frame Audit (Cycle 434.79g+, per `conviction_adversarial_triangulation.md`)

**Trigger:** dispatched by tdevauto when tdeep Mode C OR trev_inline emits `STRUCTURAL_IMPLAUSIBILITY` for a specific run. Memory_dev.md will contain a task `tdebug matched-frame audit: <run_dir_basename>`. This mode is OUT-OF-BAND with the harness-experiment mode above; both modes can run in tdebug, dispatched separately based on the triggering memory_dev task wording.

**Goal:** independently re-compute the suspect baseline metrics from saved predictions and realized returns, cross-check against the persisted values, bisect the mismatch source (K, cost_bps, ann_factor, return-series provenance, universe filter), output a diagnosis verb that tconv applies.

### Steps

1. **Locate the run.** Read the memory_dev task line, extract `<run_dir_basename>`. Find the run directory under `firstrate_portfolio/<variant>/models/` or `firstrate_learning/<variant>/models/`.

2. **Read the suspect metrics.** Open `<run_dir>/training_results.json`. Quote the values that triggered the audit:
   - `foresight_sharpe_ratio_matched` (if > 1.05)
   - `cascade_transmission_ratio` (if > 1.05)
   - `foresight_annual_return_ratio` (if > 1.05)
   - Any `xsec_ic` value > 1.0 or < −1.0
   - Any sign-mismatch between `test_sharpe_net_of_10bps` and `test_annualized_return_net_10bps`

3. **Locate the eval code.** Find the variant's `train.py` and `eval_*.py` (if present). Grep for the call sites:
   - `foresight_sharpe_baseline(...)` — quote the first argument and confirm it is the realized return tensor (`y_return`), NOT scores/predictions.
   - `portfolio_annual_return(...)` — same check.
   - `compute_matched_anchor_net_sharpe(...)` — confirm anchor parameters match V10 (2.569, 0.077).

4. **Independent recomputation.** Load the run's saved predictions and return tensors (typically in `<run_dir>/eval_results.json` or `<run_dir>/predictions.npz` if persisted). Re-run `foresight_sharpe_baseline` and `portfolio_annual_return` from a fresh Python session via `.venv/bin/python -c`. Compare the recomputed values against the persisted values.

5. **Bisect the mismatch.** If recomputed != persisted, vary one parameter at a time:
   - Try `K = K_variant` and `K = K_variant ± 1` — does the ratio drop to ≤ 1.0?
   - Try `cost_bps ∈ {0, 10, 30, 50}` — does any value match?
   - Try `ann_factor ∈ {1.0, 252.0, sqrt(252)}` — does any factor match?
   - Try `long_short ∈ {True, False}` — does flipping match?
   - If `foresight_sharpe_baseline` was called with scores instead of returns: confirm by passing scores explicitly and matching the buggy output.

6. **Identify the root cause.** One of:
   - `wrong_input_to_baseline` — caller passed scores/predictions instead of realized returns.
   - `K_mismatch` — variant K differs from baseline K.
   - `cost_mismatch` — variant cost frame differs from baseline cost frame.
   - `ann_factor_mismatch` — annualization factors differ.
   - `universe_mismatch` — variant evaluated on subset; baseline on superset (or vice versa).
   - `unknown` — recomputation matches persisted, but value still exceeds ceiling. This is a deeper bug — possibly in the basket-construction logic itself.

7. **Author proposed fix in `.manager/proposed_rule_changes.md`.** Append a section:

```markdown
## Matched-Frame Audit — <run_dir_basename> — [PST timestamp]

**Coordinate(s) violated**: <list>
**Root cause**: <one of the above>
**Evidence**: file:line of the buggy call site, quoted source.
**Recomputed value(s)**: <independent recomputation result>
**Proposed fix**: <specific code change with file:line and old → new>
**Affected runs** (if regression scope spans multiple variants): <list of run_dir basenames>
```

8. **Update `## Tdebug Status` in `.manager/memory_dev.md`** — **overwrite** the `## Tdebug Status` section (create it if missing) with a single status block reflecting the CURRENT run only. Never append — replace the entire section content each run.

```
## Tdebug Status
Last run: [PST timestamp]
Mode: matched-frame audit
Run: <run_dir_basename>
root_cause: <category>
recomputed_foresight_ratio: <float> | persisted: <float>
proposed_fix: <one-line>
next: tconv ratify proposal
```

9. **Output the diagnosis verb in stdout (machine-readable):**

```
MATCHED_FRAME_AUDIT: run=<run_dir_basename> root_cause=<category> recomputed=<float> persisted=<float> fix_file=<path> fix_line=<int>
```

### Mode-specific bias resistance

The persisted `training_results.json` is UNTRUSTED — that is the entire reason this mode exists. The recomputation in step 4 is the ground truth. If your recomputation matches the persisted value AND still exceeds the ceiling, do NOT conclude "the persisted value was right after all" — escalate to `unknown` root cause; the bug is upstream of the eval call (in basket construction, in saved-data alignment, or in something else).

### Strike-ledger note

A STRUCTURAL_IMPLAUSIBILITY-flagged variant has its strike ledger UNCHANGED. After tdebug audit + tconv-applied fix, the variant re-runs through the same gate. The original suspect run is retained as audit evidence (do NOT delete the run dir); a new run dir is created for the re-run.
