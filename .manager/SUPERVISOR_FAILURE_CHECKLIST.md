# Supervisor Failure Mode Checklist
## What t-supervisor Should Have Caught (but Didn't)

This checklist captures the exact signal analysis that should have detected the 14-minute deadlock.

---

## The Incident (20:14–20:28 PT)

**What**: Timer-eta deadlock — no /teta monitoring calls for 14 minutes  
**Why**: Timer-dev didn't clear eta_done file when ignoring premature signal  
**Supervisor Report**: "HEALTHY" (false positive at 20:25 PT)

---

## Checklist: What Should Have Been Verified

### ✗ Check 1: File Age Analysis

**File**: `timer/data/eta_done_1.json`

```bash
# Supervisor should have done:
MTIME=$(stat -c %Y "$ETA_DONE" 2>/dev/null)
AGE=$((CURRENT_EPOCH - MTIME))
echo "eta_done age: $((AGE / 60)) minutes"

# At 20:25 PT:
# - eta_done was written at 20:15:47 PT
# - File age: 20:25 - 20:15:47 = 9 min 13 sec
# - Threshold: >10 min = stale/stuck
# - Status at check time: NEAR threshold, but not quite > 10 min
# - Supervisor should have flagged: "ATTENTION: eta_done approaching stale timeout"
```

**Why supervisor missed it**: 
- Supervisor saw file exists (yes) 
- Supervisor did NOT compute timestamp age
- File age was 9+ min (not yet >10 min threshold, but very suspicious in monitoring context)

**Correct interpretation**:
- eta_done should be written/cleared in a cycle (every 5 min)
- File sitting at 9+ min old indicates: NOT being cleared
- Not being cleared indicates: something is broken in the handoff

---

### ✗ Check 2: /teta Interval Tracking

**Files**: `timer_eta.log`

```bash
# Supervisor should have done:
LAST_TETA_LINE=$(grep "SENT /teta" timer_eta.log | tail -1)
LAST_TETA_TIME=$(echo "$LAST_TETA_LINE" | grep -o '\[.*\]' | head -1)
# "[ 2026-04-04 20:14:07 PT]"
LAST_TETA_EPOCH=$(TZ='America/Los_Angeles' date -d "$LAST_TETA_TIME" +%s)
CURRENT_EPOCH=$(date +%s)
ELAPSED=$((CURRENT_EPOCH - LAST_TETA_EPOCH))
echo "Last /teta: $((ELAPSED / 60)) min ago"

# At 20:25 PT:
# - Last /teta: 20:14:07 PT
# - Elapsed: 20:25 - 20:14:07 = 10 min 53 sec
# - Expected interval: 5 min (every 5 min while process alive)
# - Actual: 10+ min without new /teta
# - **ALERT**: No /teta sent for 2x the expected interval
```

**Why supervisor missed it**:
- Supervisor checked: is timer-eta session alive? (yes, but alive ≠ active)
- Supervisor did NOT check: when was last /teta actually sent?
- This is the STRONGEST signal of deadlock (monitoring has stalled)

**Correct interpretation**:
- In monitoring mode (step 4), /teta should be sent every 5 min (max)
- If last /teta is >7 min old: SOMETHING IS WRONG
- At 14 min elapsed: DEFINITELY DEADLOCK

---

### ✗ Check 3: State Machine Consistency

**Files**: `timer_dev.log` + `timer_eta.log`

```bash
# Supervisor should have done:
RECENT_DEV=$(tail -30 timer_dev.log)
RECENT_ETA=$(tail -30 timer_eta.log)

# Pattern 1: "ignored" without "cleared"
if echo "$RECENT_DEV" | grep -q "ETA_DONE ignored"; then
    if ! echo "$RECENT_DEV" | grep -q "ETA_DONE cleared"; then
        echo "ALERT: timer-dev ignored eta_done but never cleared it"
    fi
fi

# Pattern 2: timer-eta "waiting"
if echo "$RECENT_ETA" | grep -q "waiting for timer-dev to clear"; then
    echo "ALERT: timer-eta blocked, waiting for file deletion"
fi

# At 20:25 PT:
# timer_dev.log contains:
# "[2026-04-04 20:04:27 PT] ETA_DONE ignored: PID=$TRACKED_PID still running (eta_done was premature)"
#
# timer_eta.log contains:
# "[2026-04-04 20:16:00 PT] STANDBY | next_step=4"
# "[2026-04-04 20:16:30 PT] Checking if eta_done exists..."
# "[2026-04-04 20:17:00 PT] eta_done exists, standing by (waiting for timer-dev to clear it)"
#
# RED FLAG: "ignored" in timer_dev.log + "waiting" in timer_eta.log = DEADLOCK
```

**Why supervisor missed it**:
- Supervisor read timer_dev.log: "ignoring eta_done" ✓ (correct decision)
- Supervisor assumed: this means cleanup is happening (WRONG)
- Supervisor did NOT cross-reference timer_eta.log for corresponding "cleared" signal
- Supervisor did NOT check for "waiting" message in timer_eta.log

**Correct interpretation**:
- If timer_dev log shows "ignoring", timer_dev.log should ALSO show "cleared" on next tick
- If timer_eta log shows "waiting", that means timer-dev failed to clear
- Both messages present = incomplete state management

---

### ✗ Check 4: File Ownership Trace

**Logical trace**:

```
At 20:25 PT, supervisor should have traced:
┌─────────────────────────────────────────────────────┐
│ Question: Who owns eta_done file clearance?         │
├─────────────────────────────────────────────────────┤
│ Answer: Timer-dev (reads, decides, should delete)  │
├─────────────────────────────────────────────────────┤
│ Q: Has timer-dev cleared eta_done recently?         │
│ A: Check timer_dev.log for "ETA_DONE cleared"       │
│    Result: NOT FOUND (only "ignored" present)       │
├─────────────────────────────────────────────────────┤
│ Q: What is timer-eta doing?                         │
│ A: Check timer_eta.log for activity                 │
│    Result: "waiting for timer-dev to clear"         │
├─────────────────────────────────────────────────────┤
│ Q: Conclusion?                                      │
│ A: Timer-dev ignored but didn't clear               │
│    Timer-eta is blocked waiting                     │
│    = DEADLOCK                                       │
└─────────────────────────────────────────────────────┘
```

**Why supervisor missed it**:
- Supervisor saw individual pieces but didn't synthesize them
- "ignoring" + "still alive" + "continuing" → supervisor concluded "OK"
- Supervisor did NOT ask: "What is the OTHER actor doing?"

---

### ✗ Check 5: Process State vs. Signal State

**Correlation check**:

```
If process is alive AND eta_done exists AND no /teta for 10+ min:
→ Something is blocking timer-eta (eta_done not cleared)

If process is alive AND eta_done exists AND /teta being sent every 5 min:
→ Normal monitoring (eta_done being cycled properly)

At 20:25 PT:
- Process alive? ✓ YES (PID running)
- eta_done exists? ✓ YES (file present)
- /teta being sent? ✗ NO (last sent 10 min ago)
- Result: SHOULD ALERT (process + signal + no monitoring = deadlock)
```

**Why supervisor missed it**:
- Supervisor checked: process alive (yes) + eta_done exists (yes)
- Supervisor concluded: "correct, we're ignoring premature eta_done"
- Supervisor did NOT verify: "is /teta being sent? is state cycling?"

---

## Combined Detection Logic (What Should Have Happened)

```
IF next_step = 4 (monitoring)
AND process is alive (PID confirmed via kill -0)
AND eta_done exists
THEN
  IF (eta_done age > 10 min)
     OR (last /teta > 7 min ago)
     OR (timer-dev log has "ignored" but not "cleared")
     OR (timer-eta log has "waiting")
  THEN
    ALERT: State management deadlock
    Root cause: eta_done not cleared by timer-dev
    Action: restart timer-dev OR manually rm eta_done
  ENDIF
ENDIF
```

**At 20:25 PT**: First condition met (3 of 4 alert conditions were true)
- ✗ eta_done age ≈ 9 min (was approaching 10 min threshold)
- ✓ last /teta ≈ 10 min ago (WELL PAST 7 min threshold)
- ✓ timer-dev log has "ignored" (no corresponding "cleared")
- ✓ timer-eta log has "waiting" (confirmed blocked)

**Supervisor reported**: "HEALTHY" (WRONG — should have reported DEADLOCK)

---

## Summary: Four Signal Failures

| Signal | Should Show | Did Show | Supervisor Checked | Supervisor Action |
|--------|------------|----------|-------------------|-------------------|
| **1. File Age** | stale (9+ min) | stale (9+ min) | ✗ NO | ✗ MISSED |
| **2. /teta Interval** | gap (10+ min) | gap (10+ min) | ✗ NO | ✗ MISSED |
| **3. State Transition** | cleared OR dead | ignored (incomplete) | ✗ NO | ✗ MISSED |
| **4. Log Correlation** | waiting OR ignoring | BOTH present | ✗ NO | ✗ MISSED |
| **Combined** | = DEADLOCK | = DEADLOCK | ✗ NO | ✗ FALSE POSITIVE |

---

## Prevention: What Supervisor MUST Check Going Forward

### Mandatory Checks for next_step=4

```bash
# 1. FILE AGE CHECK
ETA_DONE_AGE=$(...)  # Must implement
[ "$ETA_DONE_AGE" -gt 600 ] && echo "ALERT: eta_done stale"

# 2. /teta INTERVAL CHECK
LAST_TETA_ELAPSED=$(...)  # Must implement
[ "$LAST_TETA_ELAPSED" -gt 420 ] && echo "ALERT: /teta not sent for $((LAST_TETA_ELAPSED/60)) min"

# 3. LOG CORRELATION CHECK
if grep "ETA_DONE ignored" timer_dev.log && ! grep "ETA_DONE cleared" timer_dev.log; then
    echo "ALERT: incomplete state management"
fi

# 4. PROCESS ALIVE + DEADLOCK COMBINATION
if [ "$PROCESS_ALIVE" = "true" ] && [ "$ETA_DONE_STALE" = "true" ] && [ "$TETA_INTERVAL_VIOLATED" = "true" ]; then
    echo "DEADLOCK: process alive + signal stale + monitoring gap"
fi
```

---

## Deployment Checklist

- [ ] Add file age check to supervisor (Check 1)
- [ ] Add /teta interval tracking to supervisor (Check 2)
- [ ] Add log correlation check to supervisor (Check 3)
- [ ] Add combined deadlock detection (Check 4)
- [ ] Update SKILL.md section 3m with detailed checks
- [ ] Create supervisor_checks.sh helper script
- [ ] Test on healthy system (all checks pass)
- [ ] Test on simulated deadlock (all checks alert)
- [ ] Deploy to production

---

## Key Insight

**Supervisor assumed**:
> "If timer-dev is making the right decision (ignore premature eta_done when process is alive), everything must be fine."

**Reality**:
> "Correct decisions require complete cleanup. Incomplete cleanup = deadlock. Supervisor must verify BOTH the decision AND the cleanup."

The fix is not in the logic of whether to ignore — that was correct. The fix is in VERIFYING that cleanup happens.

---

## Files Affected by This Analysis

1. `.manager/supervisor_deadlock_analysis.md` — Full detailed analysis
2. `.manager/DEADLOCK_INCIDENT_SUMMARY.md` — Executive summary
3. `.claude/skills/t-supervisor/supervisor_enhancement_recommendations.md` — Implementation guide
4. `.manager/SUPERVISOR_FAILURE_CHECKLIST.md` — This file

**Next action**: Implement recommendations from enhancement_recommendations.md

