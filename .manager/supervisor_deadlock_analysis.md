# Supervisor Deadlock Detection Analysis
## Why t-supervisor Failed to Catch a 14-Minute Monitoring Blackout

**Date**: 2026-04-04  
**Incident**: Timer-eta deadlock (20:14–20:28 PT, 14 minutes unmonitored)  
**Root Cause**: Incomplete state management in timer-dev's eta_done handling  
**Supervisor Failure**: Failed to detect blocked monitoring state  

---

## Executive Summary

**The Incident**:
- Timer-eta wrote `eta_done` at 20:15:47 PT while process was still alive
- Timer-dev detected alive process and ignored eta_done, BUT **did not clear the file**
- Timer-eta then entered a "waiting for timer-dev to clear eta_done" loop
- **For 14 minutes, NO monitoring occurred** (no /teta calls sent, no metrics tracked)
- Training proceeded unmonitored during this gap

**Why Supervisor Missed It**:
At 20:25 PT, the supervisor ran its checks while the deadlock was 11 minutes old. The supervisor reported:

> "HEALTHY — Pipeline progressing normally... timer-dev correctly in step 4 monitoring state (waiting for process completion, correctly ignoring premature eta_done signals)"

The supervisor ASSUMED that "ignoring premature eta_done" meant everything was correct. It did NOT check:
1. Whether the eta_done file was being cleared
2. Whether timer-eta was blocked by the uncleaerd file
3. How long it had been since the last /teta was sent
4. Whether the monitoring cycle was actually ticking

---

## Root Cause Pattern: Deadlock via Incomplete State Management

This is a **two-actor coordination failure**:

```
Timer-eta                              Timer-dev
   │                                      │
   ├─ /teta sends at 20:14:07 ──────────→│
   │  (monitoring check)                  │
   │                                      │
   │                                      │
   ├─ /teta completes                   │
   ├─ Writes eta_done (premature)        │
   │                                      │
   │  (now waiting for clear)             │
   │                                      │
   │  [WAITS]                            │
   │  Check: is eta_done deleted?        │
   │  [STILL WAITS]                      │
   │                                      │
   │                                      ├─ Sees eta_done
   │                                      ├─ Checks: PID alive?
   │                                      ├─ YES, PID alive
   │                                      ├─ Decision: ignore eta_done
   │                                      ├─ BUG: doesn't delete it
   │                                      │
   │                                      ├─ [continues monitoring]
   │                                      │  [eta_done still exists]
   │
   ├─ Next tick: check eta_done
   ├─ Exists? YES
   ├─ Thinks: timer-dev hasn't cleared it yet
   ├─ [BLOCKED: cannot send next /teta]
   │
   │ [14 minutes of no monitoring]       │ [thinks everything normal]
   │                                      │
```

**Key insight**: Neither timer-dev nor timer-eta check the OTHER's actual state. Timer-dev doesn't signal "I cleared your file," and timer-eta doesn't check if timer-dev is actually running through monitoring cycles.

---

## What the Supervisor Missed (Step-by-Step Analysis)

### Check 1: File State Analysis (MISSED)

The supervisor should have checked:
```bash
# Was eta_done stuck in a fixed state?
stat /home/ubuntu/workspace/RLQuest/timer/data/eta_done_1.json
# What was the timestamp of the last modification?
```

**Expected behavior**: In healthy monitoring, eta_done is written and cleared repeatedly (every 5 min in /teta cycle).  
**Actual behavior**: eta_done existed but had NOT changed in 10+ minutes.  
**Supervisor checked**: Whether eta_done existed (yes).  
**Supervisor did NOT check**: How old eta_done was (age indicates stuck state).

### Check 2: Interval Tracking (MISSED)

The supervisor should have checked:
```bash
# When was the last /teta call actually sent?
grep "SENT /teta" /home/ubuntu/workspace/RLQuest/.manager/timer_eta.log | tail -1
```

**Expected behavior**: New `/teta` logs every 5 minutes (or when process dies).  
**Actual behavior**: No new `/teta` logs for 14 minutes (stuck before sending next one).  
**Supervisor checked**: Whether timer-eta session was alive (yes).  
**Supervisor did NOT check**: Whether /teta was being sent at expected intervals.

### Check 3: File Stale Age (MISSED)

The supervisor should have computed:
```bash
ETA_DONE_FILE=".../eta_done_1.json"
CURRENT_EPOCH=$(date +%s)
FILE_MTIME=$(stat -c %Y "$ETA_DONE_FILE")
STALE_AGE=$((CURRENT_EPOCH - FILE_MTIME))
# If STALE_AGE > 600 (10 min), eta_done is stuck
```

**Critical insight**: A stale eta_done file (unchanged for >10 minutes) combined with timer-eta in step 4 is a DEADLOCK indicator, not a normal state.

### Check 4: State Machine Trace (MISSED)

The supervisor should have traced:
```
1. next_step = 4 (monitoring)
2. eta_done_1.json exists
3. Timer-dev log shows: "ETA_DONE ignored: PID still running" (process alive)
4. Timer-eta log shows: "waiting for timer-dev to clear eta_done" (blocked)
5. Last /teta sent: >10 min ago
6. No new /teta entries in log for 14 min
```

**Correct interpretation**: 
- Timer-dev is correctly ignoring premature eta_done (step 3 is correct)
- BUT timer-dev is not clearing it (step 4 is missing)
- THEREFORE timer-eta is blocked (step 4 consequence)
- THEREFORE monitoring is not happening (step 5 symptom)

**Supervisor's interpretation**:
- Timer-dev ignoring premature eta_done ✓ (partially right)
- Therefore everything is normal (WRONG)

### Check 5: Blocked State Detection (MISSED)

The supervisor should have detected:
```
next_step = 4 AND
  (eta_done exists) AND
  (timer-dev log shows "ignoring" or "clearing") AND
  (timer-eta log shows "waiting" or "standby") AND
  (no /teta sent for >10 min) AND
  (process is alive)
  
→ DEADLOCK: incompletely unblocked state
```

This is a **deadlock pattern** where:
- Both actors are "waiting" (one for a file to be deleted, one for a condition)
- Neither has fully advanced state management (incomplete cleanup)
- Result: no progress (no monitoring)

---

## Supervisor Assumption Failures

### Assumption 1: "Ignoring = Correct"
**Stated assumption**: If timer-dev ignores premature eta_done when process is alive, everything is working correctly.

**Reality**: Ignoring alone is insufficient. The file must also be DELETED to unblock the other actor.

**Why supervisor believed it**: The only check was "is timer-dev detecting the condition?" The check did not extend to "is timer-dev fully resolving the condition?"

### Assumption 2: "No Kill Switch = Healthy"
**Stated assumption**: If kill_violations.md doesn't exist, the system is healthy.

**Reality**: kill_violations.md is a KILL signal, not a health indicator. A healthy system also needs:
- Regular /teta logs (proof monitoring is happening)
- Advancing eta_done lifecycle (clear, write, clear, write...)
- No file stuck in a fixed state (indicates blocking condition)

### Assumption 3: "next_step=4 + Session Alive = Monitoring Active"
**Stated assumption**: If next_step=4 and timer-eta session is alive, monitoring is active.

**Reality**: A session can be alive while blocked. Blocked ≠ dead, but blocked = not progressing. The supervisor did not check:
- Is the session actively ticking (pane changing)?
- Is it sending /teta calls?
- Is it waiting for something?

### Assumption 4: "Pane Capture Indicates Activity"
**Stated assumption**: If pane output shows activity or expected log entries, the component is working.

**Reality**: Timer-eta pane could show earlier successful monitoring while being currently blocked. The supervisor captured the pane ONCE and assumed current state. It did not:
- Compare pane captures over time
- Check for "waiting" log messages in recent tail
- Correlate pane output with file timestamps

---

## How Supervisor Should Have Detected This

### Detection Rule 1: Stale File + Monitoring Mode
```bash
# If in step 4 AND eta_done exists AND hasn't changed in 10+ min
# → DEADLOCK: eta_done is stuck between actors

if [ "$NEXT_STEP" = "4" ] && [ -f "$ETA_DONE" ]; then
    FILE_AGE=$(( $(date +%s) - $(stat -c %Y "$ETA_DONE") ))
    if [ "$FILE_AGE" -gt 600 ]; then
        echo "DEADLOCK: eta_done stale for $(( FILE_AGE / 60 )) min"
        # This indicates file was not cleared by timer-dev
    fi
fi
```

### Detection Rule 2: /teta Interval Violation
```bash
# If monitoring mode AND last /teta was >7 min ago (5-min + 2-min tolerance)
# → DEADLOCK: timer-eta not sending monitoring calls

LAST_TETA_LINE=$(grep "SENT /teta" timer_eta.log | tail -1)
LAST_TETA_TIME=$(echo "$LAST_TETA_LINE" | awk '{print $1}')
ELAPSED=$((CURRENT_EPOCH - $(date -d "$LAST_TETA_TIME" +%s)))
if [ "$ELAPSED" -gt 420 ]; then
    echo "DEADLOCK: no /teta sent for $(( ELAPSED / 60 )) min (expected every 5 min)"
fi
```

### Detection Rule 3: Incomplete State Transition
```bash
# If timer-dev log shows "ignoring eta_done" but timer-eta log shows "waiting"
# AND no new timer-dev action since then
# → DEADLOCK: incomplete unblock

IGNORE_LINE=$(grep "ETA_DONE ignored" timer_dev.log | tail -1)
WAITING_LINE=$(grep "waiting for timer-dev to clear" timer_eta.log | tail -1)
if [ -n "$IGNORE_LINE" ] && [ -n "$WAITING_LINE" ]; then
    echo "DEADLOCK: timer-dev ignored but didn't clear; timer-eta waiting"
fi
```

### Detection Rule 4: File Ownership Contradiction
```bash
# If eta_done exists, but:
#   - timer-dev expects to clear it (log says "clearing")
#   - timer-eta expects it to be cleared (log says "waiting")
# → DEADLOCK: both actors waiting for each other

if grep -q "ETA_DONE cleared" timer_dev.log && \
   grep -q "waiting for timer-dev to clear" timer_eta.log; then
    echo "DEADLOCK: both clearing and waiting logs present (race condition)"
fi
```

---

## Recommended Supervisor Enhancements

### 1. Add File-Based Timeline Analysis

Read all relevant files and compute a timeline of state changes:

```bash
#!/bin/bash

ETA_DONE_FILE=".../eta_done_1.json"
KILL_SWITCH=".../kill_violations.md"
ETA_TS_FILE=".../t2_eta_ts_1.txt"

# Get timestamps
CURRENT_EPOCH=$(date +%s)
ETA_DONE_MTIME=$(stat -c %Y "$ETA_DONE_FILE" 2>/dev/null || echo 0)
ETA_DONE_AGE=$((CURRENT_EPOCH - ETA_DONE_MTIME))

LAST_TETA=$(grep "SENT /teta" timer_eta.log 2>/dev/null | tail -1)
LAST_TETA_TS=$(echo "$LAST_TETA" | grep -o '\[.*\]' | tr -d '[]')

# Detect anomalies
if [ -f "$ETA_DONE_FILE" ] && [ "$ETA_DONE_AGE" -gt 600 ]; then
    echo "ALERT: eta_done stuck for $((ETA_DONE_AGE / 60)) min"
fi

if [ -z "$LAST_TETA" ]; then
    echo "ALERT: no /teta history found"
fi
```

### 2. Add Interval Tracking Checks

Every cycle, record the interval since the last major event:

```bash
# File: timer/data/supervisor_last_teta.txt
# Maintained by supervisor: epoch timestamp of last confirmed /teta
# On each supervisor run, compare to current time

LAST_RECORDED=$(cat timer/data/supervisor_last_teta.txt 2>/dev/null || echo 0)
CURRENT=$(date +%s)
ELAPSED=$((CURRENT - LAST_RECORDED))

if [ "$NEXT_STEP" = "4" ] && [ "$ELAPSED" -gt 420 ]; then
    # No update for >7 min (5 min interval + 2 min tolerance)
    echo "DEADLOCK: /teta not advancing, elapsed $((ELAPSED/60)) min"
fi
```

### 3. Add Log-Based Coordination Checker

Parse logs to detect "waiting" states:

```bash
# Check for patterns indicating actors waiting for each other
RECENT_DEV=$(tail -20 timer_dev.log)
RECENT_ETA=$(tail -20 timer_eta.log)

if echo "$RECENT_ETA" | grep -q "waiting for timer-dev to clear"; then
    # Timer-eta is blocked. Is timer-dev aware?
    if echo "$RECENT_DEV" | grep -q "continuing monitoring"; then
        # Timer-dev logged "continuing" but didn't clear file
        echo "DEADLOCK: timer-dev continued without clearing eta_done"
    fi
fi
```

### 4. Add State Machine Validator

Check that state transitions are consistent with log activity:

```bash
# Rule: if next_step=4 and eta_done exists and process alive,
#       then timer-dev.log must contain RECENT "ETA_DONE cleared" entry

NEXT_STEP=$(grep '"next_step"' timer_cycle_state.json | grep -o '[0-9]*')
ETA_DONE_EXISTS=$([ -f eta_done_1.json ] && echo 1 || echo 0)
PROCESS_ALIVE=$(kill -0 "$(cat t2_launched_pid_1.txt)" 2>/dev/null && echo 1 || echo 0)

if [ "$NEXT_STEP" = "4" ] && [ "$ETA_DONE_EXISTS" = "1" ] && [ "$PROCESS_ALIVE" = "1" ]; then
    # This state requires timer-dev to have cleared eta_done recently
    RECENT_CLEAR=$(grep "ETA_DONE cleared" timer_dev.log | tail -1)
    CLEAR_AGE=$(...)
    
    if [ -z "$RECENT_CLEAR" ] || [ "$CLEAR_AGE" -gt 600 ]; then
        echo "DEADLOCK: incomplete eta_done clearance"
    fi
fi
```

### 5. Add Deadlock Recovery Actions

When deadlock is detected, supervisor should:

```bash
# Recovery strategy: detect incomplete state management

if [ DEADLOCK_DETECTED ]; then
    # Option 1: Clear eta_done file
    rm -f "$ETA_DONE_FILE"
    echo "DEBUG: Cleared stale eta_done. Timer-eta should resume."
    
    # Option 2: Restart timer-dev with fixed code
    # (This was the actual fix applied)
    bash timer/tmux_timer_dev.sh 1 --stop
    sleep 2
    bash timer/tmux_timer_dev.sh 1
    
    # Option 3: Restart timer-eta if timer-dev fix insufficient
    bash timer/tmux_timer_eta.sh 1 --stop
    sleep 2
    bash timer/tmux_timer_eta.sh 1
fi
```

---

## Improvements to superv_cycle_design.md

### Add New "Common Failure Mode" Section

```markdown
## Common Failure Modes (EXTENDED)

### 9. State Management Deadlock (File Not Cleared)

**Symptom**: next_step=4, eta_done exists, timer-eta log shows "waiting for timer-dev to clear", 
no /teta sent for 10+ minutes, process is alive

**Root cause**: An earlier actor ignored a signal but failed to clean it up. The next actor 
is now blocked waiting for cleanup that will never come.

**Pattern**:
```
Timer-dev sees condition X (e.g. premature eta_done)
→ Makes decision: ignore it
→ FORGETS to clean up (delete the signal file)
→ Timer-eta waits forever for cleanup
→ Neither actor advances (deadlock)
```

**Diagnosis files**:
- `timer_eta.log`: Look for "waiting for timer-dev to clear" with no recent change
- `timer_dev.log`: Look for "ignoring" followed by silence (no "cleared" logs)
- `eta_done_1.json`: Check timestamp via `stat -c %Y`. If older than 10 min, stuck

**Fix**:
1. Check timer_dev.log for the specific condition it ignored
2. Verify process is actually alive (reason for ignoring)
3. Manually clear the signal file: `rm -f timer/data/eta_done_1.json`
4. If deadlock recurs, restart timer-dev or timer-eta with code fix

**Code pattern to prevent**:
```bash
# WRONG (deadlock risk):
if [ condition ]; then
    echo "ignoring condition"
    # NO CLEANUP HERE
else
    # cleanup and advance
fi

# RIGHT (deadlock-free):
if [ condition ]; then
    echo "ignoring condition"
    rm -f "$SIGNAL_FILE"  # ← CLEANUP REQUIRED
else
    # cleanup and advance
fi
```
```

### Add New Supervisor Check to SKILL.md

Add to Step 4 (Detect Stuck States):

```markdown
**3m. State Management Deadlock (incomplete file cleanup):**

When next_step=4 (monitoring), always check:
1. Does eta_done_1.json exist? If yes, check its age: `stat -c %Y eta_done_1.json`
2. Is eta_done older than 10 minutes? If yes: DEADLOCK indicator
3. Verify timer-eta log: is last entry "waiting for timer-dev to clear"?
4. Verify timer-dev log: is last entry "ignoring" (not "cleared")?
5. Verify process is alive: `kill -0 $(cat t2_launched_pid_1.txt)`

If all 5 are true: **DEADLOCK due to incomplete state management**

Action:
- Identify what timer-dev was ignoring (read timer_dev.log)
- Verify the reason is still valid (process still alive? file still stale?)
- Manually clear the signal: `rm -f timer/data/eta_done_1.json`
- Restart timer-dev if deadlock recurs: code fix needed (see mode 9)
```

---

## Skill Rules for Future Prevention

### Rule 1: File Ownership + Cleanup Responsibility

**In timer-dev.sh (eta_done handling)**:
```bash
# Whenever ignoring eta_done due to alive process:
if [ alive ]; then
    echo "ignoring eta_done"
    rm -f "$ETA_DONE"  # ← MANDATORY cleanup
fi
```

**Rationale**: Timer-dev is the sole reader of eta_done (via file check). If it decides to ignore the signal, it MUST clean it up so the other actor (timer-eta) can proceed with next cycle. No cleanup = deadlock.

### Rule 2: Signal Lifecycle Validation

Every file-based coordination signal must be explicitly cleared:

| Signal File | Written By | Read By | Must Clear When |
|---|---|---|---|
| `eta_done` | timer-eta | timer-dev | (a) Process confirmed dead + advanced to tconv OR (b) Process alive + continuing monitoring |
| `kill_violations.md` | teta (via /teta) | timer-dev | timer-dev kills process + advances to tconv |
| `kill_blocks_further_launches` | tdeep | timer-dev | Timer-dev advances past tdeep (to step 4 or back to tconv) |

Each entry must specify: **who clears it, when, and what happens if it's not cleared**.

### Rule 3: Interval-Based Health Checks in Supervisor

Add checks to detect blocked monitoring:

```python
# Supervisor check (every 10 min):
def check_monitoring_interval(timer_eta_log, current_epoch):
    """Detect if /teta calls have stalled."""
    last_teta = parse_last_log_entry(timer_eta_log, pattern="SENT /teta")
    if last_teta:
        elapsed = current_epoch - last_teta.timestamp
        if elapsed > 420:  # 7 min (5 min interval + 2 min tolerance)
            return DEADLOCK("no /teta sent for {} min".format(elapsed // 60))
    return HEALTHY
```

---

## Timeline of Deadlock vs. Supervisor Visibility

```
Time    | Event                          | Supervisor Visibility | Missed Signal
--------|--------------------------------|----------------------|------------------
20:14:07| /teta SENT                    | ✓ (logged)          | —
20:15:47| eta_done WRITTEN (premature)  | ✗ (not in focus)   | File age >0
20:16-20:20| Timer-eta polls eta_done  | ✗ (internal logs)   | "waiting" message
20:25:00| SUPERVISOR RUNS (this cycle) | ? (checked briefly) | ❌ Assumes OK
        |   - Checks: next_step=4       | ✓ (correct state)   |
        |   - Checks: eta_done exists   | ✓ (sees file)       |
        |   - Checks: process alive     | ✓ (PID running)     |
        |   - Checks: "ignoring" in log | ✓ (correct action) | ❌ Didn't check "cleared"
        |   - CONCLUSION: HEALTHY       | ✗ (WRONG)           | ❌ Assumes cleanup happened
20:28:45| Timer-dev RESTARTED (fix)    | ✓ (by external)    | Supervisor didn't restart
20:29:17| /teta SENT (resumed)         | ✓ (now logging)    | Monitoring resumed
```

---

## Summary: Four Levels of Supervisor Improvement

### Level 1: File Age Checking (Easiest)
- Check all signal files for age
- Flag files older than 10 min in monitoring mode
- Cost: 2-3 bash commands per supervisor cycle

### Level 2: Interval Tracking (Medium)
- Grep timer_eta.log for "SENT /teta" entries
- Compute time since last /teta
- Flag if >7 min elapsed in step 4
- Cost: log parsing + timestamp computation

### Level 3: Log Correlation (Medium)
- Read relevant logs side-by-side
- Detect patterns like "ignoring" without "cleared"
- Detect "waiting" without corresponding "cleared"
- Cost: multi-file log analysis

### Level 4: State Machine Validator (Harder)
- Model expected state transitions
- Check that actual logs match expected sequence
- Detect when transitions are incomplete or stalled
- Cost: state diagram + validation logic

**Recommended immediate implementation**: Level 1 (file age) + Level 2 (interval tracking). These provide 80% of deadlock detection with minimal complexity.

---

## Code Review Lesson: Incomplete State Management Pattern

This deadlock follows a common bug pattern in concurrent systems:

**Pattern**: Actor A ignores signal S, but fails to clear S for Actor B

```
Correct behavior:
  A sees S → decides to ignore → clears S → B can proceed

Buggy behavior:
  A sees S → decides to ignore → FORGETS to clear → B waits forever
```

**How to prevent**:
1. **Explicit cleanup**: Every condition check must include cleanup code
2. **Paired operations**: Signal write + reader clear must be in same operation (or backed by file timestamp checks)
3. **Log the full action**: "ignoring signal X" should log "clearing signal X" in same code block

**In this codebase** (timer architecture):
- Timer-dev checks eta_done (line 366)
- Timer-dev ignores when process alive (line 367)
- Timer-dev logs "continuing" (line 370)
- **Missing**: `rm -f "$ETA_DONE"` before "continuing"

The fix is one line:
```bash
rm -f "$ETA_DONE"  # Unblock timer-eta for next monitoring cycle
```

This pattern will recur in other state management code. Supervisor enhancements (file age checks, interval tracking) catch it before humans notice.

