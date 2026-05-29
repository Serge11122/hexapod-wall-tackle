# Supervisor Scope Fix — Clear Boundary Between Timer Issues and Code Issues

**Date:** 2026-04-04  
**Problem:** Supervisor currently handles BOTH timer orchestration issues AND project code issues. This is wrong.  
**Solution:** Clear, strict boundary. Supervisor owns timer/orchestration. Code issues escalate to tdev_inline.

---

## Executive Summary

The supervisor's role is being misinterpreted. Current SKILL.md conflates two separate concerns:
1. **Timer Orchestration** — file state, session health, deadlocks, monitoring gaps (SUPERVISOR OWNS THIS)
2. **Project Code Issues** — violations found by tdeep, code bugs, missing gate markers (TDEV OWNS THIS)

Today's incident (2026-04-04 gate_unit.json missing) was a code violation that supervisor tried to work around. It should have been escalated to tdev_inline immediately, not handled by supervisor restart/bypass.

**Key insight:** Supervisor should detect that code issues exist, then escalate. Supervisor does not diagnose or fix code problems.

---

## Part 1: Clear Scope Boundary

### What Supervisor OWNS (Timer/Orchestration)

Supervisor owns these states AND has authority to fix them autonomously:

| Issue | Symptom | Supervisor Action | Code Changes? |
|-------|---------|-------------------|---------------|
| **Dead Claude session** | `t_1_dev` pane unresponsive >20min | Restart timer-dev, which respawns t_1_dev | No — timer restart handles it |
| **Dead timer script** | `timer-dev-1` session not ticking | Restart via `tmux_timer_dev.sh 1 --stop && sleep 2 && tmux_timer_dev.sh 1` | No — infrastructure issue |
| **Stale phase flag** | `t2_tconv_sent_1.txt` older than 20 min | Delete the flag file | No — transient flag cleanup |
| **Corrupted state file** | `timer_cycle_state.json` has malformed JSON | Fix JSON syntax, set `next_step=1` | No — data repair, not logic |
| **Deadlock in eta_done** | `eta_done_1.json` stale >10 min + no /teta for 7 min | Delete `eta_done_1.json`, restart timer-eta | No — state cleanup |
| **Permission prompt** | Session paused on `bypass permissions` prompt | Send `y` + Enter | No — user approval |
| **Spin loop (bad launch_commands.json format)** | `launch_commands.json` has missing field names or wrong types | Rewrite JSON with correct field names | No — supervisor repairs malformed data |
| **Spin loop (file not found)** | `t2_launch_blocked_1.txt` says `FILE_NOT_FOUND: path/to/train.py` | Use Glob to find correct path, rewrite JSON | No — supervisor fixes bad paths written by tdev_inline |

**Key:** None of these require understanding or changing project code logic.

### What tdev_inline/tconv OWNS (Project Code)

tdev_inline/tconv own these and supervisor ESCALATES:

| Issue | Symptom | Who Fixes | Location | Type |
|-------|---------|-----------|----------|------|
| **Missing gate marker** | tdeep finds `gate_unit.json` not written by code | tdev_inline modifies train.py to write marker | `firstrate_learning/train.py` line ~848 | Code bug |
| **Wrong checkpoint_every** | tdeep finds `checkpoint_every=2000` but gate spec says 500 | tdev_inline changes config or code | Train config section | Code logic |
| **Import error** | Script crashes on import (code syntax issue) | tdev_inline fixes imports | Module file | Code bug |
| **Gate progression broken** | tdeep finds `--prove-out` launched without `gate_smoke.json` existing | tdev_inline updates CLAUDE.md rule or launches smoke first | Policy enforcement | Code/policy |
| **Uncomm itted changes** | tdeep finds working tree dirty | tdev_inline commits or stashes | Git state | Code ownership |
| **Conviction violation** | tdeep finds code uses epoch loops instead of step loops | tconv analyzes (via subagent), tdev_inline implements fix | Train logic | Architectural |

**Key:** If it requires understanding the project intent, modifying .py files, or changing logic, it's tdev_inline's job.

---

## Part 2: Updated Step 4 Logic in SKILL.md

### New Classification: Timer Issues vs Code Issues

After Step 4 identifies a stuck state, supervisor must classify it:

**TIMER ISSUE** — fix directly:
- Dead/unresponsive session (pane frozen, no output >20 min)
- Stale files (phase flags >20 min old, eta_done >10 min, manifests cleanup)
- Deadlock in file coordination (eta_done not cleared, /teta not sent)
- Malformed state files (corrupted JSON, missing fields)
- Bad launch_commands.json due to supervisor-fixable issues (missing script_file field, completely wrong path)

**CODE ISSUE** — escalate to tdev_inline:
- tdeep found violations in conviction files
- Code imports are broken
- Gate markers missing (gate_unit.json, gate_smoke.json)
- Checkpoint configuration wrong
- Uncomm itted changes to .py files
- Loss function disabled, warmup wrong, LR out of range

### Detection Flow (Step 4)

```
1. Identify stuck state (via 3a-3m checks)
2. Classify: is this INFRASTRUCTURE or CODE?

   IF infrastructure:
      → Supervisor fixes directly (session restart, state cleanup, deadlock unblock, path repair)
      → Resume: timer-dev will rescan and proceed
      
   IF code issue:
      → Supervisor escalates: write diagnostic summary
      → Set timer_cycle_state.json next_step=2 (force re-run)
      → Supervisor exits with "escalated to tdev_inline"
      → On next timer tick: tdev_inline reads escalation note, tconv re-analyzes, tdev_inline implements fix
```

### Example: Identify Code Issue vs Timer Issue

**SCENARIO 1: tdeep blocked with violations**

```
Detected: deep_analysis_results.md shows 2 violations:
  1. gate_unit.json never written
  2. checkpoint_every=2000 for smoke (should be 500)

Classification: CODE ISSUE
  → These require tdev_inline to modify train.py
  → Supervisor cannot know the right fix
  
Action: Escalate
  1. Write to .manager/supervisor_diagnostics.md:
     "tdeep found 2 violations: gate markers, checkpoint config. Escalating to tdev_inline for code fix."
  2. Set timer_cycle_state.json next_step=2 to re-route to tdev_inline
  3. Exit with message: "Code violations detected. Escalated to tdev_inline for implementation."
  4. Next cycle: tdev_inline runs, reads convictions + tdeep results, implements fixes
```

**SCENARIO 2: eta_done stale, deadlock detected**

```
Detected: 
  - eta_done_1.json exists, 14 min old
  - /teta not sent for 14 min
  - Process still alive (confirmed via kill -0)
  - timer_dev.log shows "ETA_DONE ignored: PID still running" (no "cleared" entry)

Classification: TIMER ISSUE (file coordination deadlock)
  → No code logic involved
  → Supervisor knows the fix: delete the stale file
  
Action: Fix directly
  1. Delete: rm -f timer/data/eta_done_1.json
  2. Restart: bash timer/tmux_timer_eta.sh 1 --stop && sleep 2 && bash timer/tmux_timer_eta.sh 1
  3. Monitor: wait 10s, verify timer-eta re-enters monitoring
  4. Log: "Deadlock unblocked: eta_done cleared, timer-eta restarted"
  5. Resume: next timer tick will proceed normally
```

---

## Part 3: Escalation Pattern — How Supervisor Escalates to tdev_inline

When supervisor detects a code issue in Step 4:

### Write Diagnostic Summary

Create `.manager/supervisor_diagnostics.md`:

```markdown
# Supervisor Diagnostics — [timestamp]

## Issue Detected

**Type:** Code Issue (requires tdev_inline implementation)

**Evidence:**
- Stuck state: [description of what made supervisor notice]
- Root cause: [why supervisor cannot fix it]
- Relevant files: [tdeep output, violation list, etc.]

## Violations Found

[Copy key violations from deep_analysis_results.md or kill_violations.md]

Example:
- gate_unit.json: Not written by train.py for unit-test run type
- checkpoint_every: Set to 2000 but gate spec requires 500 for smoke
- Uncomm itted changes: git diff shows pending .py changes

## Why Supervisor Cannot Fix This

[Explain why this is not a timer/orchestration issue. e.g.]
- "Gate markers are project-specific code outputs. Supervisor has no authority to decide when they should be written."
- "checkpoint_every is a training hyperparameter. Only tdev_inline understands correct values for different gates."

## Escalation Actions Taken

1. Set timer_cycle_state.json next_step=2 (tdev_inline)
2. Wrote this diagnostic file for tdev_inline to read
3. Exited supervisor run

## Next Step for tdev_inline

- Read tdeep results (deep_analysis_results.md)
- Read this diagnostic summary
- Read conviction files to understand violation intent
- Implement code fixes
- Commit changes
- Write new launch_commands.json
- Cycle resumes: tconv → tdev_inline → tdeep → launch
```

### Update timer_cycle_state.json

Set `next_step=2` to route back to tdev_inline (not tconv):

```bash
# Read current state
CURRENT=$(cat .manager/timer_cycle_state.json)

# Update: set next_step=2, mark as escalated
# (supervisor does minimal state updates — only for escalation)
cat > .manager/timer_cycle_state.json.tmp <<EOF
{
  "cycle": $(echo "$CURRENT" | grep -o '"cycle": *[0-9]*' | grep -o '[0-9]*'),
  "next_step": 2,
  "status": "escalated_to_tdev",
  "long_running_pid": "$(echo "$CURRENT" | grep -o '"long_running_pid": *"[^"]*"' | cut -d'"' -f4)",
  "escalation_reason": "Code violations detected by tdeep — requires tdev_inline implementation"
}
EOF

mv .manager/timer_cycle_state.json.tmp .manager/timer_cycle_state.json
```

### Timer Resumes

On next timer-dev tick:
1. Timer-dev reads `next_step=2`, sends `/tdev_inline`
2. tdev_inline skill reads:
   - deep_analysis_results.md (what violations were found)
   - supervisor_diagnostics.md (why supervisor escalated)
   - Conviction files (what the violations mean)
3. tdev_inline subagent implements code fixes
4. tdev_inline writes new launch_commands.json
5. tdev_inline exits; timer-dev detects IDLE
6. Loop continues: tconv → tdev_inline → tdeep → launch

---

## Part 4: When Supervisor Spawns Subagent vs Fixes Directly

Supervisor should spawn a Sonnet subagent ONLY for unclear diagnostics, not for routine issues.

### Subagent Cases (Spawn Sonnet)

- Deadlock pattern is ambiguous (file age _might_ be a race condition, not a deadlock)
- Permission prompt is visible but purpose unclear (what tool is being requested? is it safe?)
- Timer orchestrator logs show errors but root cause is not obvious (OOM? external kill? script bug?)
- Stuck session with no clear pane capture output (frozen, waiting, or crashed?)
- Recurring pattern across multiple cycles (same symptom keeps happening — why?)

### Direct Fix Cases (No Subagent)

- eta_done file is 15 min old, /teta not sent, process alive → **delete the file** (clear deadlock)
- launch_commands.json is missing "script_file" field → **rewrite with correct fields** (clear malformation)
- Permission prompt visible, request is for workspace file I/O → **send `y` + Enter** (routine approval)
- Phase flag file >20 min old, skill has not progressed → **delete flag file** (clear stale state)
- Code violations found by tdeep → **escalate to tdev_inline** (clear code issue, not supervisor's domain)

---

## Part 5: Example Incident Walkthroughs

### Incident 1: Today's gate_unit.json Violation (Code Issue)

**What Happened:**
- tdeep found: "gate_unit.json never written by code"
- Supervisor incorrectly thought: "I should restart the cycle and bypass tdeep"
- Correct response: "Escalate to tdev_inline. This is code maintenance."

**Correct Handling:**

```
Step 4: Detect Stuck States
  → Found: tdeep BLOCKED with violations (gate_unit.json missing, checkpoint_every=2000)
  
Classification: CODE ISSUE
  Reason: Gate markers are code outputs. Supervisor doesn't decide when they're written.

Action: Escalate
  1. Write supervisor_diagnostics.md summarizing violations
  2. Set next_step=2 (route to tdev_inline)
  3. Exit supervisor run
  
Next Cycle:
  1. tdev_inline reads violations, understands they require code changes
  2. tdev_inline subagent modifies train.py:
     - Add gate_unit.json write for run_type=="unit"
     - Change checkpoint_every to 500 for smoke
  3. tdev_inline commits changes (7c1ecef)
  4. tdev_inline writes new launch_commands.json
  5. Timer continues: tconv → tdeep (re-validate) → launch
  
Result: Code fixed via proper channel, gate markers written, smoke launches cleanly.
```

**What Actually Happened:**
- Supervisor tried to work around the code violation
- Supervisor wrote bypass diagnostic saying "violations are old"
- Timer launched smoke with broken code
- Smoke failed partway through (gate markers not written, checkpoint intervals wrong)

**Lesson:** Supervisor cannot judge whether code is "correct enough." Only tdev_inline can decide that.

---

### Incident 2: Potential Deadlock (Timer Issue)

**Scenario:**
- next_step=4 (monitoring)
- eta_done_1.json exists, file timestamp 18 min ago
- /teta not sent for 18 min (gap detected via grep in timer_eta.log)
- Process is alive: `kill -0 $(cat timer/data/t2_launched_pid_1.txt)` succeeds
- timer_dev.log shows: "ETA_DONE ignored: PID=12345 still running" (no "cleared" line after)

**Classification:** TIMER ISSUE (deadlock in file coordination)

**Supervisor Action:**
```
Step 4: Detect Stuck States
  → Found: File-based deadlock (3m check)
  
Classification: TIMER ISSUE
  Reason: This is orchestration state management, not code logic.
  
Action: Fix directly
  1. Unblock: rm -f timer/data/eta_done_1.json
  2. Restart timer-eta:
     bash timer/tmux_timer_eta.sh 1 --stop
     sleep 2
     bash timer/tmux_timer_eta.sh 1
  3. Monitor: wait 10s
     grep "SENT /teta" .manager/timer_eta.log | tail -1
     (should see a recent timestamp)
  4. Log: "Deadlock unblocked: eta_done cleared, timer-eta restarted"
  
Result: /teta resumes within 2 cycles, monitoring continues.
```

**Why Not Escalate?**
- No code change needed
- Supervisor has authority to manage state files
- Root cause is known (eta_done not cleaned up when process still alive)
- Fix is mechanical (delete file, restart timer)

---

### Incident 3: Spin Loop with Bad Path (Timer-Fixable)

**Scenario:**
- spin_count = 6 (spinning)
- t2_launch_blocked_1.txt says: `FILE_NOT_FOUND: firstrate_portfolio/vp13/train.py`
- But correct path is actually: `firstrate_learning/v13/train.py` (tdev_inline wrote wrong module path)

**Classification:** TIMER ISSUE (supervisor-fixable)

Why? Because it's a data error, not a code logic issue:
- tdev_inline was supposed to determine correct module path
- tdev_inline wrote it wrong (wrong module, wrong path, or missing fields)
- Supervisor CAN use Glob to find the correct file
- Supervisor CAN rewrite launch_commands.json with correct path
- Supervisor is NOT changing project code logic

**Supervisor Action:**
```
Step 4: Detect Stuck States
  → Spin loop, 6 cycles without launch
  → t2_launch_blocked_1.txt says FILE_NOT_FOUND

Classification: TIMER ISSUE (supervisor-fixable bad path)
  Not code logic — just a bad path in launch_commands.json
  
Action: Fix directly
  1. Find correct path:
     Glob("firstrate_learning/**/train.py")
     Result: firstrate_learning/v13/train.py ✓
  
  2. Read launch_commands.json to see what tdev_inline wrote
     module: "firstrate_portfolio.vp13.train" (WRONG: portfolio not learning)
  
  3. Rewrite with corrected path:
     {
       "module": "firstrate_learning.v13.train",
       "script_file": "firstrate_learning/v13/train.py",
       "flags": [...],
       "log": "firstrate_learning/v13/train.log"
     }
  
  4. Clear spin block:
     rm -f timer/data/t2_spin_count_1.txt
     rm -f timer/data/t2_launch_blocked_1.txt
  
  5. Restart timer-dev (will pick up fixed JSON)
     bash timer/tmux_timer_dev.sh 1 --stop && sleep 2 && bash timer/tmux_timer_dev.sh 1
  
Result: Next tick, timer-dev launches with correct path.
```

**Why Not Escalate?**
- Not a code logic issue
- tdev_inline already wrote the command (just wrong path)
- Supervisor has authority to fix data errors
- No changes to .py files needed

---

### Incident 4: Uncomm itted Changes (Code Issue)

**Scenario:**
- tdeep blocked: "Uncommitted changes: git diff HEAD -- *.py shows pending changes"
- Files changed: train.py (10 lines), config.py (2 lines)

**Classification:** CODE ISSUE

Why? Because tdev_inline owns code commits:
- tdev_inline was supposed to commit or explain why changes aren't committed
- Supervisor cannot decide if changes are correct
- Supervisor cannot commit (not tdev_inline's role to verify correctness)

**Supervisor Action:**
```
Step 4: Detect Stuck States
  → Found: tdeep BLOCKED with violation (uncommitted changes)
  
Classification: CODE ISSUE
  Reason: Code ownership + commit authority belongs to tdev_inline, not supervisor.
  Supervisor cannot judge if changes are correct and safe to commit.
  
Action: Escalate
  1. Write supervisor_diagnostics.md:
     "tdeep found uncommitted .py file changes. tdev_inline must review, commit, or stash."
  2. Set next_step=2
  3. Exit
  
Next Cycle:
  tdev_inline reads diff, decides:
    - Changes are good → git commit
    - Changes are debug → git checkout .
  Then cycle resumes.
```

---

## Part 6: Updated SKILL.md Sections

### Section: Step 4 — Detect Stuck States

**ADD after 3l (Previous prediction vs actual outcome):**

**3m. Code Issue vs Timer Issue Classification**

When any stuck state is identified in checks 3a-3l:
1. **Is this a TIMER/ORCHESTRATION problem?** (infrastructure, state management, session health)
   - Dead session, stale files, deadlocks, permission prompts, malformed state
   - → Supervisor fixes directly (see Step 5)

2. **Is this a CODE problem?** (violations, logic bugs, gate markers, uncomm itted changes)
   - Code violations from tdeep, missing gate markers, bad config, imports broken
   - → Supervisor escalates to tdev_inline (see Step 5e below)

If unsure, ask: "Can supervisor fix this without modifying project .py files?" If no → escalate.

---

### Section: Step 5 — Investigate Root Cause

**ADD new subsection 5e (Code Issue Escalation):**

**5e. Escalation: Code Issues to tdev_inline**

If step 4 identified a CODE ISSUE:

1. **Write diagnostic summary** to `.manager/supervisor_diagnostics.md`:
   ```markdown
   # Supervisor Diagnostics — [PST timestamp]
   
   ## Issue Detected
   **Type:** Code Issue (requires tdev_inline implementation)
   
   **Evidence:**
   [Summarize what stuck state was found and why supervisor cannot fix it]
   
   ## Violations Found
   [Copy specific violations from deep_analysis_results.md or kill_violations.md]
   
   ## Escalation Actions
   1. Set timer_cycle_state.json next_step=2 (route to tdev_inline)
   2. Exited supervisor run
   
   ## Next Steps for tdev_inline
   - Read deep_analysis_results.md
   - Read conviction files
   - Implement code fixes (modify .py files as needed)
   - Commit changes
   - Write new launch_commands.json or proceed with cycle
   ```

2. **Update timer_cycle_state.json** to force re-route to tdev_inline:
   ```bash
   # Atomically update (use .tmp + replace pattern)
   cat > /tmp/state_update.json <<EOF
   {
     "cycle": $CURRENT_CYCLE,
     "next_step": 2,
     "status": "escalated_to_tdev",
     "long_running_pid": "$TRACKED_PID",
     "escalation_reason": "Code violations detected — tdev_inline implementation required"
   }
   EOF
   mv /tmp/state_update.json .manager/timer_cycle_state.json
   ```

3. **Exit supervisor run** with summary message

4. **On next timer tick:**
   - timer-dev reads next_step=2
   - Sends /tdev_inline to t_1_dev
   - tdev_inline subagent reads diagnostics + violations
   - tdev_inline implements code fixes
   - tdev_inline commits and writes launch_commands.json
   - Cycle continues normally

---

### Section: Step 5 — Apply Fixes

**REMOVE or REVISE any text suggesting supervisor should fix code violations.**

Current Step 5c has supervisor fixing "NO_SCRIPT" and "FILE_NOT_FOUND" — this is correct (data repair).

Remove any suggestion that supervisor should:
- Modify train.py or any .py file
- Decide when gate markers should be written
- Change hyperparameters or loss functions
- Commit code changes

---

## Part 7: Subagent Usage Rules

Supervisor spawns a Sonnet subagent (no thinking, effort=low) ONLY in these cases:

1. **Deadlock pattern is unclear** — file ages + /teta intervals + log patterns don't form a clear story
2. **Timer script error is cryptic** — pane shows bash error but cause is not obvious
3. **Permission prompt purpose is unclear** — which tool, why, is it safe?
4. **Recurring stuck state** — same symptom across 3+ cycles, root cause unknown
5. **Claude session hung with unclear output** — can't tell if waiting for input, frozen, or still working

Supervisor does NOT spawn subagent for:
- Code violations (tdeep already analyzed, supervisor just reads results)
- Spin loops with clear block reason (NO_SCRIPT, FILE_NOT_FOUND, VIOLATIONS are all understood)
- Stale files (clear cleanup action)
- Deadlock with clear indicators (file age >10 min, /teta gap >7 min, process alive)

---

## Part 8: Supervisor Report Updates

### supervisor_report.md Template Changes

In the "Issues Found" section, add classification:

```markdown
## Issues Found

### Timer Issues (Supervisor Fixed)
- [issue description and fix applied, or "None"]

### Code Issues (Escalated to tdev_inline)
- [issue description and escalation action, or "None"]

### Unclear Issues (Subagent Diagnosis)
- [issue and subagent findings, or "None"]
```

Example:

```markdown
## Issues Found

### Timer Issues (Supervisor Fixed)
- Deadlock: eta_done_1.json was 14 min stale. Deleted file, restarted timer-eta. /teta resumed within 2 cycles.

### Code Issues (Escalated to tdev_inline)
- tdeep found 2 violations: gate_unit.json not written, checkpoint_every=2000 (need 500 for smoke).
  Escalation: Wrote supervisor_diagnostics.md, set next_step=2, exited.
  Next cycle: tdev_inline will implement fixes in train.py, commit, and cycle resumes.

### Unclear Issues
- None
```

---

## Summary: What Changes in Practice

### TODAY (Broken Approach)

```
tdeep finds code violation
  ↓
supervisor thinks: "This is a problem I should fix"
  ↓
supervisor restarts cycle, writes bypass diagnostic
  ↓
supervisor tries to manually approve launch
  ↓
Result: Code issue never actually fixed, cycle repeats endlessly
```

### AFTER (Correct Approach)

```
tdeep finds code violation
  ↓
supervisor thinks: "This requires code changes. Not my domain."
  ↓
supervisor escalates: writes diagnostic, sets next_step=2
  ↓
timer-dev sends /tdev_inline
  ↓
tdev_inline reads violations, implements fixes, commits code
  ↓
cycle resumes: tconv → tdev_inline (fix applied) → tdeep (re-validate) → launch
  ↓
Result: Code issue actually fixed, cycle unblocks, model launches with correct logic
```

---

## Implementation Checklist

- [ ] Read this document (SUPERVISOR_SCOPE_FIX.md)
- [ ] Understand: supervisor owns TIMER issues, tdev_inline owns CODE issues
- [ ] Identify which sections of SKILL.md need updating (see Part 6)
- [ ] Update SKILL.md Step 4 with code/timer classification (add 3m)
- [ ] Update SKILL.md Step 5 with escalation pattern (add 5e)
- [ ] Remove suggestions that supervisor should fix code logic
- [ ] Update supervisor_report.md template to classify timer vs code issues
- [ ] Test: Run supervisor on healthy system, verify no escalations
- [ ] Test: Create test code violation, verify supervisor detects and escalates

---

## Document History

| Date | Event |
|------|-------|
| 2026-04-04 | Initial analysis: supervisor tried to fix code violations it detected. Root cause: scope ambiguity. |
| 2026-04-04 | Document created: SUPERVISOR_SCOPE_FIX.md with clear boundary + escalation pattern. |
| TBD | SKILL.md sections identified for update (NOT YET MODIFIED). |
