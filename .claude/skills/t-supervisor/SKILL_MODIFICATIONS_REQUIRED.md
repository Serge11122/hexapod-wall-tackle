# SKILL.md Modifications Required — Specific Sections

This document identifies the EXACT sections of SKILL.md that need modification to implement the scope fix.

**Status:** Analysis only — DO NOT modify SKILL.md yet. This lists what needs to change and why.

---

## Overall Strategy

Current SKILL.md conflates supervisor's role with code-fixing authority. The fix requires:
1. **Clarify Step 4**: Add classification logic (is this TIMER or CODE issue?)
2. **Add new Step 5 subsection**: Escalation pattern for code issues
3. **Revise existing Step 5**: Restrict supervisor to timer/orchestration fixes only
4. **Update Step 8 (Report)**: Classify issues as timer/code/unclear

---

## Section 1: Step 1 (Unconditional Log Analysis)

**Current:** Lines 29-57

**Status:** NO CHANGES NEEDED

This section is correct — supervisor reads state without making judgments yet.

---

## Section 2: Step 4 (Detect Stuck States)

**Current:** Lines 94-238

### Modification 2a: Add New Check 3m — Code/Timer Classification

**Location:** After check 3l ("Previous prediction vs actual outcome"), before Step 5

**Current Text (Lines 239-242):**
```markdown
**3l. Previous prediction vs actual outcome (cross-check):**
- Read `.manager/supervisor_report.md` — what did the PREVIOUS supervisor run predict?
- Compare to what actually happened in the cycle log since then.
- If predictions were wrong, note the discrepancy. This is a signal that log interpretation may be off.

### Step 5: Investigate Root Cause
```

**REQUIRED INSERTION (between 3l and Step 5):**

Insert this new check:

```markdown
**3m. Code Issue vs Timer Issue Classification:**

Any stuck state identified in 3a-3l must be classified:

**TIMER ISSUE** — Supervisor can fix:
- Dead or unresponsive Claude session (pane frozen >20 min, no output)
- Dead timer orchestrator script (timer-dev-1, timer-eta-1, timer-rev-1 not ticking >5 min)
- Stale phase flag files (t2_*_sent_*.txt older than 20 min)
- Corrupted state file (timer_cycle_state.json has malformed JSON)
- File-based deadlock (eta_done file exists >10 min, /teta not sent >7 min, process alive)
- Permission prompt blocking session (routine tool approvals)
- Spin loop with supervisor-fixable cause (NO_SCRIPT, FILE_NOT_FOUND, malformed JSON fields)

**CODE ISSUE** — Supervisor must escalate to tdev:
- tdeep found violations in conviction files
- Missing gate markers (gate_unit.json, gate_smoke.json)
- Wrong checkpoint configuration
- Uncomm itted changes to .py files
- Import errors or syntax issues in code
- Any issue that requires modifying project .py files

**Decision Logic:**

For each stuck state found:
1. Read diagnostic files (deep_analysis_results.md, kill_violations.md)
2. Is the root cause in code logic or infrastructure state?
3. Can supervisor fix it WITHOUT modifying project .py files?
   - YES → Timer issue, fix directly (Step 5)
   - NO → Code issue, escalate to tdev (Step 5e)

If uncertain, default to ESCALATE. Supervisor has no authority over project code.
```

---

## Section 3: Step 5 (Investigate Root Cause & Apply Fixes)

**Current:** Lines 244-422

### Modification 3a: Clarify Step 5 as Timer-Only

**Current introduction (Lines 244-256):**
```markdown
### Step 5: Investigate Root Cause

For any stuck state identified in step 4:

- **Phase stuck (3a)**: read tmux pane capture, check if Claude session is responsive
- **Spin loop (3b)**: read `t2_launch_blocked_1.txt` first (already done). Then:
  - If NO_SCRIPT: read `.manager/launch_commands.json` to see what was written
  - If VIOLATIONS: read `.manager/deep_analysis_results.md` for specific violations
  - Read `.manager/memory_dev.md` for next planned experiment — is it coherent?
- **Repeated blocks (3d)**: read `deep_analysis_results.md` in full — which violations repeat?
- **Repeated kills (3e)**: read `kill_violations.md`
- **Monitoring stuck (3c)**: check `timer/data/eta_done_1.json` and `timer/data/t2_launched_pid_1.txt`
```

**REQUIRED CHANGE:**

Replace with:

```markdown
### Step 5: Apply Fixes (Timer Issues Only)

**IMPORTANT:** If step 4 classified the issue as CODE (via 3m check), skip to Step 5e (Escalation).
Otherwise, for TIMER issues identified in steps 3a-3l:

**5a. Phase stuck (3a):** 
- Read tmux pane capture: is Claude session frozen or responsive?
- If frozen: restart timer-dev
- If responsive but progress slow: check for permission prompts (3k)

**5b. Spin loop (3b) — TIMER-FIXABLE CASES ONLY:**
- If block reason is NO_SCRIPT (malformed launch_commands.json fields):
  - Read deep_analysis_results.md to understand what was intended
  - Use Glob to verify correct script_file path exists
  - Rewrite launch_commands.json with correct field names and paths
  - Clear spin block: delete t2_spin_count_*.txt and t2_launch_blocked_*.txt
  - Restart timer-dev
- If block reason is FILE_NOT_FOUND (wrong path in JSON):
  - Use Glob to find actual file path
  - Rewrite launch_commands.json with verified path
  - Clear spin block and restart timer-dev
- **If block reason is VIOLATIONS:** This is a CODE issue → skip to Step 5e (Escalation)

**5c. Repeated blocks (3d):**
- If violations keep repeating: Code issue → Step 5e (Escalation)

**5d. Repeated kills (3e):**
- Read kill_violations.md: what are the violations?
- If code-related (bad loss function, missing output): Code issue → Step 5e
- If infrastructure-related (OOM, GPU error): May require restart of timer or scaling down

**5e. Monitoring stuck (3c):**
- Check if eta_done_N.json exists and age
- If stale (>10 min) and no recent /teta: likely deadlock
- Check process alive: if alive and file stale → delete file, restart timer-eta
- Check timer-eta.log for "waiting for timer-dev to clear" pattern
```

### Modification 3b: Add Step 5e — Escalation Pattern for Code Issues

**Current location:** After "5d. Timer restart" subsection (after line 351), add new subsection:

```markdown
**5e. Code Issue Escalation to tdev:**

If step 4 identified a CODE ISSUE (via 3m classification):

Supervisor does NOT attempt to fix code logic. Instead:

1. **Write diagnostic summary** to `.manager/supervisor_diagnostics.md`:
```
# Supervisor Diagnostics — [PST timestamp]

## Issue Detected
**Type:** Code Issue (requires tdev implementation)

**Evidence:**
[Describe the stuck state and why supervisor cannot fix it]
Example: "tdeep found gate_unit.json not written by code. This requires train.py modification. Supervisor has no authority to modify project code."

## Violations Found
[Copy specific violations from deep_analysis_results.md or kill_violations.md]

## Why Supervisor Cannot Fix This
[Explain why this is not a timer/orchestration issue]

## Escalation Actions
1. Set timer_cycle_state.json next_step=2 (route to tdev for code fixes)
2. Wrote this diagnostic file
3. Exited supervisor run

## Next Steps for tdev
- Read deep_analysis_results.md for specific violations
- Read conviction files to understand violation intent
- Implement code fixes (modify .py files as required)
- Commit changes
- Write launch_commands.json if needed
- Cycle resumes: tconv → tdev → tdeep → launch
```
2

2. **Update timer_cycle_state.json** to route to tdev:
```bash
cat > /tmp/state_new.json <<'EOF'
{
  "cycle": $CURRENT_CYCLE,
  "next_step": 2,
  "status": "escalated_to_tdev",
  "long_running_pid": "$TRACKED_PID",
  "escalation_reason": "Code violations detected by tdeep — tdev implementation required"
}
EOF
# Use atomic replacement
mv /tmp/state_new.json .manager/timer_cycle_state.json
```

3. **Exit supervisor run** with clear message:
```
"Code violations detected. Escalated to tdev for implementation.
Next cycle: tdev will read violations, fix code, and cycle resumes."
```

**On next timer tick:**
- timer-dev reads next_step=2, sends /tdev
- tdev subagent reads supervisor_diagnostics.md + deep_analysis_results.md
- tdev implements code fixes and commits
- Cycle continues: tconv → tdev (fix applied) → tdeep (re-validate) → launch

**IMPORTANT:** Supervisor does not judge whether code is "correct enough." Supervisor only detects that code fixes are needed and escalates.
```

---

## Section 4: Step 5d — Timer Restart (Existing)

**Current:** Lines 316-377

**Status:** MOSTLY CORRECT, minor clarification needed

**Optional improvement (Line 355-357):**

Current text says:
```markdown
**Root cause investigation — MANDATORY before or alongside every restart:**
Before restarting a stuck timer orchestrator, capture its pane output and logs to understand WHY it got stuck. Do not restart blindly — a restart without root cause understanding will likely recur.
```

**Suggested addition:**

After this paragraph, add:

```markdown
**Clarification:** Root cause investigation here means understanding TIMER/ORCHESTRATION issues.
If the root cause is CODE-related (violations found by tdeep, missing gate markers, etc.), 
that is NOT within scope of this investigation. Stop, classify as CODE issue, escalate to tdev.
```

---

## Section 5: Step 7 (Apply Fixes) — Line 275+

**Current:** Lines 275-422

**Status:** REVIEW NEEDED — may contain supervisor-code-fixing suggestions

Check these subsections:

**5c. Spin loop unblock (Lines 287-314):**
- **Current:** "Autonomously fix — see Step 5c" and detailed instructions for rewriting launch_commands.json
- **Status:** This is CORRECT — these are data repair cases (NO_SCRIPT, FILE_NOT_FOUND), not code fixes

**5f. Permission prompt resolution (Lines 396-422):**
- **Current:** Instructions for approving permission prompts and cycling permission mode
- **Status:** This is CORRECT — routine session management

---

## Section 6: Step 8 (Report)

**Current:** Lines 424-464

### Modification 6a: Update Report Template

**Current template (Lines 427-464):**

```markdown
# Supervisor Report — [PST timestamp]

## Pipeline Status: HEALTHY / STUCK / RECOVERING

## Log Analysis (Computed)
...

## Issues Found
- [issue description + evidence, or "None — pipeline healthy"]

## Root Cause (if any)
- [specific cause of any stuck state, or "N/A"]

## Actions Taken
- [what was fixed, exact commands run, files modified, restarts performed, or "None"]

## Previous Prediction vs Actual
...

## Still Unresolved
- [anything that could not be fixed this cycle and why, or "None"]
```

**REQUIRED CHANGE:**

Replace "Issues Found", "Root Cause", and "Actions Taken" sections with:

```markdown
## Issues Found

### Timer Issues (Supervisor Fixed)
- [issue description and fix applied, or "None"]

### Code Issues (Escalated to tdev)
- [issue description, escalation action, and next steps for tdev, or "None"]

### Unclear Issues (Subagent Diagnosis)
- [issue and subagent findings, or "None"]

## Root Cause Analysis

### Timer Issues
- [specific cause of timer-related stuck state, or "N/A"]

### Code Issues
- [what violations were found, why escalation was necessary, or "N/A"]

## Actions Taken

### Timer Fixes (Supervisor)
- [fixes applied directly: commands run, files modified, restarts performed, or "None"]

### Escalations (To tdev)
- [diagnostic files written, state changes made to route to tdev, or "None"]
```

---

## Section 7: Step 9 (Log to timer_cycle_log.md)

**Current:** Lines 466-474

**Status:** NO CHANGES NEEDED

The log format is already correct. It reports brief summaries, not detailed actions.

---

## Summary of Required Changes

| Section | Change | Type | Impact |
|---------|--------|------|--------|
| Step 4, after 3l | Add new check 3m: Code vs Timer classification | Addition | CRITICAL — enables supervisor to correctly route issues |
| Step 5 intro | Clarify Step 5 is Timer-only, redirect Code to 5e | Revision | CRITICAL — prevents supervisor from attempting code fixes |
| Step 5, after 5d | Add new section 5e: Escalation pattern | Addition | CRITICAL — enables supervisor to escalate to tdev |
| Step 5d | Add clarification about code vs timer root causes | Addition | Minor — prevents confusion about scope |
| Step 8 (Report) | Restructure to classify issues as Timer/Code/Unclear | Revision | Important — improves visibility and accountability |
| Step 9 (Log) | No changes needed | N/A | OK |

---

## Implementation Order

1. **First:** Add Step 4 check 3m (Code vs Timer classification)
   - Makes it possible for supervisor to detect when escalation is needed
   
2. **Second:** Add Step 5e (Escalation pattern)
   - Enables supervisor to actually escalate when needed
   
3. **Third:** Revise Step 5 intro to redirect Code issues to 5e
   - Prevents supervisor from attempting timer fixes for code issues
   
4. **Fourth:** Update Step 8 report template
   - Improves visibility into what was a timer fix vs code escalation
   
5. **Optional:** Add clarifications to Step 5d, Step 7
   - Improves readability but not strictly required

---

## Testing After Modifications

After SKILL.md is updated:

### Test 1: Healthy Cycle
- Run supervisor on normal pipeline (no stuck states)
- Verify report shows "None — pipeline healthy"

### Test 2: Detect Code Issue
- Manually create a fake violation in deep_analysis_results.md
- Run supervisor
- Verify supervisor detects violation, classifies as CODE issue
- Verify supervisor writes supervisor_diagnostics.md
- Verify supervisor sets next_step=2
- Verify supervisor_report.md shows "Code Issues (Escalated to tdev)"

### Test 3: Detect Timer Issue
- Manually create a stale eta_done_1.json file (set timestamp to 15 min ago)
- Run supervisor
- Verify supervisor detects deadlock (via 3m check)
- Verify supervisor deletes file
- Verify supervisor_report.md shows "Timer Issues (Supervisor Fixed)"

### Test 4: Permission Prompt
- Pause t_1_dev with a tool permission prompt
- Run supervisor
- Verify supervisor detects prompt (via 3j check)
- Verify supervisor approves it (sends `y` + Enter)
- Verify session resumes

---

## Rollback Plan (if needed)

If modifications break supervisor behavior:
1. Revert to last known-good SKILL.md via git
2. Re-run supervisor cycle to restore normal operation
3. Root cause the breaking change (likely in 3m classification logic or 5e escalation)

---

## Document History

| Date | Status |
|------|--------|
| 2026-04-04 | Analysis complete — document created |
| TBD | SKILL.md modifications applied (not yet) |
| TBD | Testing completed and verified |

