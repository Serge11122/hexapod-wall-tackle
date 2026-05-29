# Supervisor Scope — Quick Reference

**One-page guide for supervisors to distinguish between timer issues (fix) and code issues (escalate).**

---

## The Rule

**Supervisor owns TIMER/ORCHESTRATION. tdev_inline owns PROJECT CODE.**

If supervisor can fix it WITHOUT modifying .py files → **FIX IT**.
If it requires changing code logic or .py files → **ESCALATE TO TDEV**.

---

## Quick Decision Tree

```
Stuck state detected
    ↓
Read evidence (panes, logs, files)
    ↓
Is it TIMER/INFRASTRUCTURE?     Is it CODE/LOGIC?
├─ Dead session?                 ├─ tdeep violations found?
├─ Stale files?                  ├─ Missing gate markers?
├─ Deadlock in file state?       ├─ Uncomm itted .py changes?
├─ Corrupted JSON state?         ├─ Config/LR/loss wrong?
├─ Permission prompt?            ├─ Code syntax/imports broken?
└─ Bad path in JSON?             └─ Need to modify train.py?
    ↓                                ↓
  FIX DIRECTLY              ESCALATE TO TDEV
  (Step 5a-5d)              (Step 5e)
```

---

## Supervisor CAN Fix (Timer Issues)

| Issue | Action |
|-------|--------|
| t_1_dev pane frozen 20+ min | Restart timer-dev (which respawns t_1_dev) |
| timer-dev-1 session dead | `tmux_timer_dev.sh 1 --stop && sleep 2 && tmux_timer_dev.sh 1` |
| Phase flag >20 min old | Delete the flag file |
| timer_cycle_state.json malformed | Fix JSON syntax, set next_step=1 |
| eta_done_1.json stale 10+ min + no /teta | Delete file, restart timer-eta |
| Permission prompt blocking | Send `y` + Enter to approve |
| launch_commands.json missing "script_file" | Rewrite JSON with correct field names |
| launch_commands.json has wrong path | Use Glob to find correct path, rewrite |

**Key:** None of these require understanding project code logic.

---

## Supervisor Must Escalate (Code Issues)

| Issue | Why Escalate |
|-------|--------------|
| tdeep violation: gate_unit.json missing | Code must write gate markers — requires train.py change |
| tdeep violation: checkpoint_every=2000 | Config is project-specific — only tdev_inline understands context |
| tdeep violation: uncomm itted .py changes | Code ownership and commit authority = tdev_inline responsibility |
| tdeep violation: epoch loop found | Code logic change required — not supervisor's domain |
| kill_violations.md: bad metrics | May indicate code issue — let tdev_inline analyze |
| Import error or syntax error | Code fix required |

**Key:** Any issue that requires understanding "why" or changing .py files = escalate.

---

## Escalation Steps (Copy-Paste Ready)

### 1. Write supervisor_diagnostics.md

```markdown
# Supervisor Diagnostics — [timestamp from: TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT']

## Issue Detected
**Type:** Code Issue (requires tdev_inline implementation)

## Evidence
[Copy the specific violation and what made supervisor detect the stuck state]

## Escalation Actions
1. Set timer_cycle_state.json next_step=2 (route to tdev_inline)
2. Exited supervisor run

## Next Steps for tdev_inline
- Read deep_analysis_results.md
- Read conviction files
- Implement code fixes
- Commit changes
- Write launch_commands.json if needed
```

### 2. Update timer_cycle_state.json

```bash
cat > .manager/timer_cycle_state.json <<EOF
{
  "cycle": $(grep -o '"cycle": *[0-9]*' .manager/timer_cycle_state.json | grep -o '[0-9]*'),
  "next_step": 2,
  "status": "escalated_to_tdev",
  "long_running_pid": "$(grep -o '"long_running_pid": *"[^"]*"' .manager/timer_cycle_state.json | cut -d'"' -f4)",
  "escalation_reason": "Code violations detected — tdev_inline implementation required"
}
EOF
```

### 3. Exit

Supervisor exits. Timer-dev will send /tdev_inline on next tick.

---

## Timer Issue Examples

### Example 1: Bad Path in launch_commands.json

**Symptom:** Spin loop, `t2_launch_blocked_1.txt` says `FILE_NOT_FOUND: wrong/path/train.py`

**Supervisor Action:**
```bash
# Find correct path
Glob("firstrate_learning/**/train.py")  # returns: firstrate_learning/v13/train.py

# Rewrite launch_commands.json with correct path
cat > .manager/launch_commands.json <<'EOF'
[{
  "module": "firstrate_learning.v13.train",
  "script_file": "firstrate_learning/v13/train.py",
  "flags": ["--smoke-test"],
  "log": "firstrate_learning/v13/train.log",
  "launched": false,
  "expect": { ... }
}]
EOF

# Clear spin block
rm -f timer/data/t2_spin_count_1.txt timer/data/t2_launch_blocked_1.txt

# Restart timer-dev
bash timer/tmux_timer_dev.sh 1 --stop && sleep 2 && bash timer/tmux_timer_dev.sh 1
```

**Result:** Timer-dev picks up fixed JSON, launches correctly.

---

### Example 2: Deadlock in eta_done

**Symptom:** next_step=4, eta_done_1.json exists and is 15 min old, /teta not sent for 15 min, process alive

**Supervisor Action:**
```bash
# Delete stale signal file (unblocks timer-eta)
rm -f timer/data/eta_done_1.json

# Restart timer-eta
bash timer/tmux_timer_eta.sh 1 --stop && sleep 2 && bash timer/tmux_timer_eta.sh 1

# Wait 10s, verify /teta resumes
sleep 10
grep "SENT /teta" .manager/timer_eta.log | tail -1  # should see recent timestamp
```

**Result:** /teta resumes within 2 cycles, monitoring continues.

---

## Code Issue Examples

### Example 1: Missing Gate Marker

**Symptom:** tdeep blocked with "gate_unit.json never written by code"

**Supervisor Action:**
```bash
# Write diagnostic
cat > .manager/supervisor_diagnostics.md <<'EOF'
# Supervisor Diagnostics — [timestamp]

## Issue Detected
**Type:** Code Issue (requires tdev_inline implementation)

## Evidence
tdeep found: gate_unit.json not written by train.py.
This requires modifying train.py to write the gate marker for unit-test run type.

## Escalation Actions
Set next_step=2 to route to tdev_inline for code fix.
EOF

# Update state
cat > .manager/timer_cycle_state.json <<EOF
{
  "cycle": $(grep -o '"cycle": *[0-9]*' .manager/timer_cycle_state.json | grep -o '[0-9]*'),
  "next_step": 2,
  "status": "escalated_to_tdev",
  "long_running_pid": "",
  "escalation_reason": "gate_unit.json missing — code fix required"
}
EOF
```

**Next Cycle:**
- tdev_inline reads supervisor_diagnostics.md + deep_analysis_results.md
- tdev_inline modifies train.py to write gate_unit.json for run_type=="unit"
- tdev_inline commits changes
- Cycle resumes: tconv → tdeep (re-validates) → launch

**Result:** Code fixed via proper channel, no bypass needed.

---

### Example 2: Uncomm itted Changes

**Symptom:** tdeep blocked with "Uncomm itted changes: git diff shows pending .py files"

**Supervisor Action:**
```bash
# Write diagnostic
cat > .manager/supervisor_diagnostics.md <<'EOF'
# Supervisor Diagnostics — [timestamp]

## Issue Detected
**Type:** Code Issue (requires tdev_inline implementation)

## Evidence
tdeep found uncomm itted changes to .py files.
tdev_inline must review, commit, or stash these changes.

## Escalation Actions
Set next_step=2 to route to tdev_inline for review and commit.
EOF

# Update state (route to tdev_inline)
cat > .manager/timer_cycle_state.json <<EOF
{
  "cycle": ...,
  "next_step": 2,
  "status": "escalated_to_tdev",
  "long_running_pid": "",
  "escalation_reason": "Uncomm itted .py changes — tdev_inline review required"
}
EOF
```

**Next Cycle:**
- tdev_inline reads diff, decides:
  - Changes are good → `git commit`
  - Changes are debug → `git checkout .`
- Cycle resumes automatically

**Result:** Working tree clean, cycle proceeds.

---

## Subagent Use (Rare)

Spawn Sonnet subagent ONLY if diagnostic is unclear:

- Deadlock pattern is ambiguous (multiple possible causes)
- Timer script error is cryptic (bash error with unclear cause)
- Permission prompt purpose is unclear (which tool, why?)
- Recurring stuck state across 3+ cycles (same symptom, different root causes?)

Do NOT spawn subagent for:
- Clear code violations (tdeep already found them)
- Stale files (obvious cleanup action)
- Permission prompts with expected purpose (routine approvals)

---

## Report Template

In supervisor_report.md, use this structure:

```markdown
## Issues Found

### Timer Issues (Supervisor Fixed)
- [description and fix, or "None"]

### Code Issues (Escalated to tdev_inline)
- [description and escalation, or "None"]

### Unclear (Subagent Investigation)
- [issue and findings, or "None"]
```

---

## Remember

**Supervisor is a TIME/STATE MANAGER, not a CODE REVIEWER.**

- If you find yourself reading project code logic or thinking "hmm, should this be like this?" → STOP
- If you need to modify a .py file → STOP, ESCALATE
- If you're not sure → default to ESCALATE (better safe than wrong)

The boundary is there for a reason: tdev_inline has project context; supervisor does not.

---

## Flowchart (One-Page)

```
Supervisor Run
    ↓
Read logs/panes/files (Step 1-3)
    ↓
Identify stuck state (Step 4a-4l)
    ↓
CLASSIFY (Step 4m):
    ├─ Timer issue? → FIX (Step 5a-5d) → Resume
    └─ Code issue? → ESCALATE (Step 5e) → Exit
```

That's it. Two-path decision tree. No ambiguity.

