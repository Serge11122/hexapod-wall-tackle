# Supervisor Enhancement Recommendations
## Deadlock Detection & File-Based State Management

**Date**: 2026-04-04  
**Incident**: Timer-eta deadlock — 14-minute monitoring blackout  
**Status**: Analysis complete, recommendations ready for implementation  

---

## Overview

The supervisor missed a state management deadlock because it checked WHETHER a condition was being handled correctly, but NOT WHETHER the condition was being FULLY resolved (including cleanup).

This document provides:
1. **Exact code changes** to add to SKILL.md (Step 4 checks)
2. **New supervisor functions** to detect file-based deadlocks
3. **Updates to superv_cycle_design.md** (new failure mode, prevention patterns)
4. **Bash script additions** for interval tracking and file age analysis

---

## Part 1: SKILL.md Changes

### Location: Section "Step 4: Detect Stuck States"

**Add new check after 3l (Previous prediction vs actual outcome):**

```markdown
**3m. State Management Deadlock (File-Based Coordination Failure):**

In monitoring mode (next_step=4), state files coordinate between timer-dev and timer-eta.
A deadlock occurs when one actor reads a signal file, makes a decision, but fails to clean up.
Result: the other actor waits forever for cleanup that will never come.

**Detection steps:**

1. Check file stale age (if next_step=4):
   ```bash
   ETA_DONE="timer/data/eta_done_1.json"
   if [ -f "$ETA_DONE" ]; then
       MTIME=$(stat -c %Y "$ETA_DONE" 2>/dev/null)
       CURRENT=$(date +%s)
       AGE=$((CURRENT - MTIME))
       if [ "$AGE" -gt 600 ]; then  # >10 min stale
           echo "ALERT: eta_done file stuck for $((AGE / 60)) min"
       fi
   fi
   ```

2. Check /teta interval (critical indicator):
   ```bash
   LAST_TETA_LINE=$(grep "SENT /teta" timer_eta.log 2>/dev/null | tail -1)
   if [ -z "$LAST_TETA_LINE" ]; then
       echo "ALERT: no /teta history — timer-eta may not have started"
   else
       LAST_TETA_TIME=$(echo "$LAST_TETA_LINE" | grep -o '\[.*\]' | tr -d '[]')
       LAST_TETA_EPOCH=$(date -d "$LAST_TETA_TIME" +%s 2>/dev/null)
       CURRENT_EPOCH=$(date +%s)
       ELAPSED=$((CURRENT_EPOCH - LAST_TETA_EPOCH))
       if [ "$ELAPSED" -gt 420 ]; then  # >7 min (5 min interval + 2 min tolerance)
           echo "ALERT: /teta not sent for $((ELAPSED / 60)) min"
       fi
   fi
   ```

3. Check for blocking log patterns:
   ```bash
   # If timer-dev log shows "ignoring" but no "cleared", incomplete state management
   RECENT_DEV=$(tail -30 timer_dev.log)
   if echo "$RECENT_DEV" | grep -q "ETA_DONE ignored"; then
       if ! echo "$RECENT_DEV" | grep -q "ETA_DONE cleared"; then
           echo "ALERT: timer-dev ignored but didn't clear eta_done"
       fi
   fi
   
   # If timer-eta log shows "waiting", it's blocked
   RECENT_ETA=$(tail -30 timer_eta.log)
   if echo "$RECENT_ETA" | grep -q "waiting for timer-dev to clear"; then
       echo "ALERT: timer-eta blocked on uncleared signal file"
   fi
   ```

**Interpret combined signals:**

- eta_done exists + age >10 min + no /teta for 7+ min + process alive → **DEADLOCK**
- timer-dev "ignored" without "cleared" + timer-eta "waiting" → **DEADLOCK**
- /teta interval violation + eta_done stale → **DEADLOCK or CRASH**

**Action:**

If DEADLOCK detected:
1. Read timer_dev.log to see what condition was being ignored
2. Verify process is alive (reason for ignoring): `kill -0 $(cat timer/data/t2_launched_pid_1.txt)`
3. **Manually unblock** by deleting the stale file: `rm -f timer/data/eta_done_1.json`
4. **Monitor next 2 cycles** to confirm /teta resumes (check for "SENT /teta" in timer_eta.log)
5. If deadlock recurs, **code fix needed**: timer-dev must add cleanup logic (e.g., `rm -f "$ETA_DONE"` in "ignore" branch)

**Prevention via code review:**

Look for this pattern in timer-dev.sh and similar scripts:
```bash
# DANGER (creates deadlock risk):
if [ $CONDITION ]; then
    echo "ignoring the condition"
    # MISSING: rm -f "$SIGNAL_FILE"
else
    # cleanup and advance
fi

# SAFE (explicit cleanup):
if [ $CONDITION ]; then
    echo "ignoring the condition"
    rm -f "$SIGNAL_FILE"  # ← Explicit cleanup before continuing
else
    # cleanup and advance
fi
```

Every signal check + decision point must include cleanup.
```

---

## Part 2: superv_cycle_design.md Changes

### Location: Section "Common Failure Modes"

**Add new mode after Mode 8 (ETA_DONE Race Condition):**

```markdown
### 9. State Management Deadlock (File-Based Actor Blocking)

**Symptom**: 
- next_step=4 (monitoring)
- eta_done_1.json exists and is stale (>10 min old)
- timer_eta.log shows "waiting for timer-dev to clear eta_done"
- timer_dev.log shows "continuing monitoring" (but no "cleared" entry)
- No /teta logs for 10+ minutes
- Process is alive (confirmed via ps)

**Root Cause**: 

Timer-dev detects a premature eta_done signal (process still running) and correctly decides to ignore it.
**But** timer-dev fails to delete the file. Timer-eta is now blocked: it sees eta_done exists and waits for
timer-dev to delete it. Timer-dev has already moved on (thinks it's monitoring normally). Result: deadlock.

**Causality Chain**:
```
1. Timer-eta sends /teta
2. /teta completes, timer-eta writes eta_done_1.json (prematurely, process still running)
3. Timer-dev ticks, reads eta_done_1.json, checks process
4. Process is alive → timer-dev logs "ETA_DONE ignored: PID=$TRACKED_PID still running"
5. Timer-dev continues to next tick (BUG: doesn't delete eta_done_1.json)
6. Timer-eta next tick: checks eta_done_1.json — file exists
7. Timer-eta logs "waiting for timer-dev to clear eta_done"
8. Timer-eta skips sending /teta (blocked, waiting for delete)
9. Both actors now waiting: timer-dev for next /teta signal, timer-eta for file deletion
10. Deadlock: no actor makes progress, monitoring stops
```

**Diagnosis Files**:
- `timer/data/eta_done_1.json`: Check timestamp via `stat -c %Y`. Age >10 min = stuck.
- `timer_eta.log`: Look for "waiting for timer-dev to clear eta_done" entries stacking up.
- `timer_dev.log`: Look for "ETA_DONE ignored" without corresponding "ETA_DONE cleared" on next tick.

**Supervisor Check** (see SKILL.md section 3m):
- File age analysis (eta_done timestamp)
- /teta interval tracking (last SENT /teta timestamp)
- Log correlation (check for "ignored" vs "cleared")

**Prevention**:

In any script that ignores a signal file:
```bash
# REQUIRED pattern:
if [ alive ]; then
    echo "ignoring eta_done"
    rm -f "$ETA_DONE"  # ← MANDATORY: clear the file for other actor
    # Continue with monitoring
else
    # process dead, safe to route to tconv
fi
```

The ignoring branch MUST clean up. Ignoring without cleaning = deadlock risk.

**Fix** (Example from timer_dev.sh):

Lines 366-369 (original code, buggy):
```bash
if [ -n "$TRACKED_PID" ] && kill -0 "$TRACKED_PID" 2>/dev/null; then
    echo "  ⚠️  WARNING: eta_done exists but PID $TRACKED_PID is STILL ALIVE. Ignoring premature signal."
    t_dev_log "ETA_DONE ignored: PID=$TRACKED_PID still running (eta_done was premature)"
    echo "  → Continuing monitoring. Will wait for process to actually exit or kill_switch."
else
```

Lines 366-371 (fixed code, deadlock-free):
```bash
if [ -n "$TRACKED_PID" ] && kill -0 "$TRACKED_PID" 2>/dev/null; then
    echo "  ⚠️  WARNING: eta_done exists but PID $TRACKED_PID is STILL ALIVE. Clearing premature signal."
    rm -f "$ETA_DONE"  # ← ADDED: Unblock timer-eta for next monitoring cycle
    t_dev_log "ETA_DONE cleared: PID=$TRACKED_PID still running (eta_done was premature, unblocking eta)"
    echo "  → Continuing monitoring. Cleared eta_done to unblock timer-eta for next /teta cycle."
else
```

**Action for Supervisor**:

If deadlock detected (via 3m check):
1. Verify root cause: read timer_dev.log for "ignored" entries
2. Verify process alive (reason for ignoring): `kill -0 $(cat timer/data/t2_launched_pid_1.txt)`
3. **Unblock manually**: `rm -f timer/data/eta_done_1.json`
   - Explanation: Timer-dev forgot to clean up. Manual cleanup unblocks timer-eta for next cycle.
4. **Monitor next 20 min** to ensure /teta resumes and deadlock doesn't recur
5. If deadlock recurs with same root cause: **restart timer-dev** (loads fixed code)
6. If deadlock recurs with different root cause: investigate (spawn subagent for diagnosis)

---

## 10. File-Based Signal Starvation (Signal Never Written)

**Symptom**:
- next_step=4
- eta_done_1.json does NOT exist
- timer_eta.log shows "standby" entries (not in monitoring mode)
- timer_dev.log shows "no tracked PID"
- Process is dead (confirmed via ps)

**Root Cause**:

Timer-eta saw next_step != 4 and entered standby. Timer-dev moved to step 4, but timer-eta
didn't see the update. Result: timer-eta never enters monitoring, never sends /teta, never
writes eta_done. Timer-dev waits for eta_done forever.

Or: timer-eta sent /teta but the Claude session (t_1_eta) crashed before writing eta_done.

**Diagnosis Files**:
- `timer_cycle_state.json`: next_step=4
- `timer_eta.log`: Confirm "standby" entries (timer-eta didn't see step=4)
- `timer_dev.log`: Confirm "waiting for eta_done" entries stacking up

**Fix**:

Restart timer-eta:
```bash
bash timer/tmux_timer_eta.sh 1 --stop
sleep 2
bash timer/tmux_timer_eta.sh 1
```

On next tick, timer-eta will see next_step=4 and enter monitoring mode.

```

---

## Part 3: New Bash Functions for Supervisor Use

Create a new script: `.manager/supervisor_checks.sh`

```bash
#!/bin/bash
# Supervisor helper functions for deadlock detection
# Source this in supervisor runs to add file-based state checks

SCRIPT_DIR="/home/ubuntu/workspace/RLQuest"
DATA_DIR="$SCRIPT_DIR/timer/data"
MANAGER_DIR="$SCRIPT_DIR/.manager"

# ============================================================================
# Check 1: File Stale Age
# ============================================================================

check_file_age() {
    local FILE="$1"
    local MAX_AGE="$2"  # seconds
    local DESC="$3"     # description
    
    if [ ! -f "$FILE" ]; then
        echo "[OK] $DESC: does not exist (not stale)"
        return 0
    fi
    
    local MTIME=$(stat -c %Y "$FILE" 2>/dev/null)
    local CURRENT=$(date +%s)
    local AGE=$((CURRENT - MTIME))
    
    if [ "$AGE" -gt "$MAX_AGE" ]; then
        echo "[ALERT] $DESC: stale for $((AGE / 60)) min (file: $FILE)"
        return 1
    else
        echo "[OK] $DESC: fresh ($((AGE)) sec old)"
        return 0
    fi
}

# ============================================================================
# Check 2: /teta Interval Tracking
# ============================================================================

check_teta_interval() {
    local TIMER_ETA_LOG="$MANAGER_DIR/timer_eta.log"
    local MAX_INTERVAL=420  # 7 min (5 min + 2 min tolerance)
    
    if [ ! -f "$TIMER_ETA_LOG" ]; then
        echo "[ALERT] timer_eta.log does not exist"
        return 1
    fi
    
    local LAST_TETA_LINE=$(grep "SENT /teta" "$TIMER_ETA_LOG" 2>/dev/null | tail -1)
    
    if [ -z "$LAST_TETA_LINE" ]; then
        echo "[ALERT] /teta interval: no /teta history found"
        return 1
    fi
    
    # Extract timestamp: "[2026-04-04 20:29:17 PT] SENT /teta ..."
    local LAST_TETA_TIME=$(echo "$LAST_TETA_LINE" | grep -o '\[.*\]' | head -1 | tr -d '[]')
    
    # Compute elapsed time
    local LAST_TETA_EPOCH=$(TZ='America/Los_Angeles' date -d "$LAST_TETA_TIME" +%s 2>/dev/null)
    if [ -z "$LAST_TETA_EPOCH" ]; then
        echo "[WARN] /teta interval: could not parse timestamp '$LAST_TETA_TIME'"
        return 2
    fi
    
    local CURRENT_EPOCH=$(date +%s)
    local ELAPSED=$((CURRENT_EPOCH - LAST_TETA_EPOCH))
    
    if [ "$ELAPSED" -gt "$MAX_INTERVAL" ]; then
        echo "[ALERT] /teta interval: no /teta sent for $((ELAPSED / 60)) min (expected every 5 min)"
        return 1
    else
        echo "[OK] /teta interval: last /teta $((ELAPSED)) sec ago"
        return 0
    fi
}

# ============================================================================
# Check 3: Log Correlation (ignored vs cleared)
# ============================================================================

check_eta_done_clearance() {
    local TIMER_DEV_LOG="$MANAGER_DIR/timer_dev.log"
    local TIMER_ETA_LOG="$MANAGER_DIR/timer_eta.log"
    
    local RECENT_DEV=$(tail -30 "$TIMER_DEV_LOG" 2>/dev/null)
    local RECENT_ETA=$(tail -30 "$TIMER_ETA_LOG" 2>/dev/null)
    
    # Pattern 1: timer-dev ignored without clearing
    if echo "$RECENT_DEV" | grep -q "ETA_DONE ignored"; then
        if ! echo "$RECENT_DEV" | grep -q "ETA_DONE cleared"; then
            echo "[ALERT] eta_done clearance: timer-dev ignored but didn't clear (incomplete state management)"
            return 1
        fi
    fi
    
    # Pattern 2: timer-eta waiting
    if echo "$RECENT_ETA" | grep -q "waiting for timer-dev to clear"; then
        echo "[ALERT] eta_done clearance: timer-eta blocked, waiting for file deletion"
        return 1
    fi
    
    echo "[OK] eta_done clearance: no blocking patterns detected"
    return 0
}

# ============================================================================
# Check 4: Process Alive Check
# ============================================================================

check_process_alive() {
    local PID_FILE="$DATA_DIR/t2_launched_pid_1.txt"
    
    if [ ! -f "$PID_FILE" ]; then
        echo "[INFO] process: no tracked PID file (not in monitoring mode?)"
        return 2
    fi
    
    local PID=$(cat "$PID_FILE")
    if [ -z "$PID" ]; then
        echo "[INFO] process: PID file empty"
        return 2
    fi
    
    if kill -0 "$PID" 2>/dev/null; then
        local ELAPSED=$(ps -p "$PID" -o etime= 2>/dev/null | xargs)
        echo "[OK] process: PID $PID alive (elapsed: $ELAPSED)"
        return 0
    else
        echo "[INFO] process: PID $PID dead or gone"
        return 1
    fi
}

# ============================================================================
# Check 5: Deadlock Detection (combined)
# ============================================================================

detect_deadlock() {
    local NEXT_STEP=$(grep -o '"next_step": *[0-9]*' "$MANAGER_DIR/timer_cycle_state.json" 2>/dev/null | grep -o '[0-9]*')
    
    if [ "$NEXT_STEP" != "4" ]; then
        echo "[INFO] deadlock check: not in monitoring mode (next_step=$NEXT_STEP)"
        return 2
    fi
    
    echo ""
    echo "=== Deadlock Detection (Step 4 / Monitoring Mode) ==="
    
    # Run all checks
    check_file_age "$DATA_DIR/eta_done_1.json" 600 "eta_done file age"
    local FILE_AGE_RESULT=$?
    
    check_teta_interval
    local TETA_INTERVAL_RESULT=$?
    
    check_eta_done_clearance
    local CLEARANCE_RESULT=$?
    
    check_process_alive
    local PROCESS_RESULT=$?
    
    # Combine results
    local DEADLOCK=0
    if [ "$FILE_AGE_RESULT" -eq 1 ] && [ "$TETA_INTERVAL_RESULT" -eq 1 ] && [ "$PROCESS_RESULT" -eq 0 ]; then
        echo ""
        echo "[DEADLOCK] Detected: eta_done stale + /teta not sent + process alive"
        DEADLOCK=1
    elif [ "$CLEARANCE_RESULT" -eq 1 ] && [ "$TETA_INTERVAL_RESULT" -eq 1 ]; then
        echo ""
        echo "[DEADLOCK] Detected: incomplete eta_done clearance + /teta interval violated"
        DEADLOCK=1
    fi
    
    return $DEADLOCK
}

# ============================================================================
# Main: Run all checks
# ============================================================================

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    detect_deadlock
    exit $?
fi
```

---

## Part 4: Integration with Supervisor SKILL.md

### Location: Step 1 (Log Analysis)

**Add after "Read spin/block diagnosis files unconditionally":**

```bash
# Also run deadlock detection checks (new)
bash .manager/supervisor_checks.sh
DEADLOCK_STATUS=$?
```

### Location: Step 4 (Detect Stuck States)

**Add new check:**

```markdown
**3m. State Management Deadlock (see supervisor_checks.sh output):**

The supervisor_checks.sh script automatically detects deadlocks via:
- File stale age (eta_done older than 10 min)
- /teta interval tracking (no monitoring for 7+ min)
- Log correlation (ignored vs cleared patterns)
- Process alive check (to confirm reason for ignoring)

If the script output shows `[DEADLOCK]`, proceed to Step 5 investigation.
```

---

## Part 5: Suggested Supervisor Report Update

Add section to supervisor_report.md template:

```markdown
## Deadlock Analysis (New Section)

| Check | Status | Value | Interpretation |
|-------|--------|-------|---|
| eta_done age | OK/ALERT | N min | File timestamp age (>10 min = stale) |
| /teta interval | OK/ALERT | N min | Time since last SENT /teta (>7 min = gap) |
| Clearance status | OK/ALERT | cleared/ignored/waiting | Log pattern (both cleared = healthy) |
| Process alive | OK/DEAD | pid/—/none | Is monitored process running? |
| **Combined**: | HEALTHY/DEADLOCK | — | Are all signals consistent? |

If DEADLOCK:
- Root cause: [description]
- Manual unblock: `rm -f timer/data/eta_done_1.json`
- Code fix needed: [Y/N]
```

---

## Implementation Checklist

- [ ] Add supervisor_checks.sh to `.manager/`
- [ ] Update SKILL.md: Add section 3m (State Management Deadlock)
- [ ] Update superv_cycle_design.md: Add modes 9-10 (Deadlock + Starvation)
- [ ] Update Step 1 in SKILL.md to call supervisor_checks.sh
- [ ] Update Step 4 in SKILL.md to reference deadlock checks
- [ ] Update supervisor_report.md template with Deadlock Analysis section
- [ ] Test: Run supervisor on healthy system (should show all OK)
- [ ] Test: Simulate deadlock by leaving eta_done file stale (should alert)

---

## Testing Recommendations

### Test 1: Healthy State
**Setup**: Normal monitoring cycle, /teta sent every 5 min, eta_done cleared/written normally

**Expected output**:
```
[OK] eta_done file age: fresh (45 sec old)
[OK] /teta interval: last /teta 120 sec ago
[OK] eta_done clearance: no blocking patterns detected
[OK] process: PID 12345 alive (elapsed: 15:32)
[INFO] deadlock check: not in monitoring mode (next_step=4)
```

### Test 2: Simulated Deadlock
**Setup**: Leave eta_done file with old timestamp, prevent timer-eta from sending /teta

**Expected output**:
```
[ALERT] eta_done file age: stale for 12 min
[ALERT] /teta interval: no /teta sent for 14 min
[ALERT] eta_done clearance: timer-eta blocked, waiting for file deletion
[OK] process: PID 12345 alive
[DEADLOCK] Detected: eta_done stale + /teta not sent + process alive
```

---

## Summary

This enhancement package provides:
1. **Specific supervisor checks** for file-based state management deadlocks
2. **Bash helper functions** for file age, interval tracking, and log correlation
3. **Updated SKILL.md** with detailed detection and recovery procedures
4. **Updated superv_cycle_design.md** with two new failure modes (9: Deadlock, 10: Starvation)
5. **Implementation checklist** and testing recommendations

**Key insight**: Supervisor should monitor not just WHETHER decisions are made, but WHETHER cleanup actions are completed. File timestamps and log patterns are the key signals.

