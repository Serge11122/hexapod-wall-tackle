# Supervisor Deadlock Detection & Prevention

## Critical Gap Identified

**What Happened**: 14-minute monitoring deadlock (20:14-20:28 PT on Apr 4, 2026)
- Timer-eta wrote eta_done at 20:15:47 PT (process still alive)
- Timer-dev correctly detected alive process, decided to "ignore" eta_done
- **Timer-dev DID NOT clear the eta_done file** (incomplete cleanup)
- Timer-eta then blocked forever in "waiting for timer-dev to clear" loop
- **14 minutes with NO /teta monitoring calls sent** (undetected)

**Why Supervisor Missed It** (checked at 20:25 PT):
- ✗ Did NOT check if eta_done file still exists
- ✗ Did NOT check if /teta monitoring is being sent regularly
- ✗ Assumed "ignoring" = "correctly handled" (but cleanup was incomplete)
- ✗ Did NOT verify file state transitions

## Root Cause Pattern

**Incomplete state management in concurrent bash scripts**:
- Actor A makes decision (timer-dev: "process alive, ignore eta_done")
- Actor A fails to complete cleanup (should delete the file)
- Actor B waits for cleanup (timer-eta: "waiting for timer-dev to clear")
- **Result**: Deadlock (no further progress)

This pattern appears in other timer interactions too.

## Immediate Fixes Applied

### 1. Code Fix (Already Done)
**File**: `timer/tmux_timer_dev.sh` (line ~370)

```bash
# BEFORE (incomplete)
if [ -n "$TRACKED_PID" ] && kill -0 "$TRACKED_PID" 2>/dev/null; then
    echo "  ⚠️  WARNING: eta_done exists but PID $TRACKED_PID is STILL ALIVE. Ignoring premature signal."
    t_dev_log "ETA_DONE ignored: PID=$TRACKED_PID still running (eta_done was premature)"
    echo "  → Continuing monitoring. Will wait for process to actually exit or kill_switch."
else
    # ... route to tconv ...
fi

# AFTER (complete)
if [ -n "$TRACKED_PID" ] && kill -0 "$TRACKED_PID" 2>/dev/null; then
    echo "  ⚠️  WARNING: eta_done exists but PID $TRACKED_PID is STILL ALIVE. Clearing premature signal."
    rm -f "$ETA_DONE"  # ← ADDED: Unblock timer-eta
    t_dev_log "ETA_DONE cleared: PID=$TRACKED_PID still running (eta_done was premature, unblocking eta)"
    echo "  → Continuing monitoring. Cleared eta_done to unblock timer-eta for next /teta cycle."
else
    # ... route to tconv ...
fi
```

**Status**: ✅ **FIXED AND VERIFIED** (restarted timer-dev at 20:28:45 PT, timer-eta resumed monitoring at 20:29:17 PT)

### 2. Supervisor Improvements (Recommended)

Add these checks to supervisor in the next enhancement cycle:

#### Check A: eta_done File Age
```bash
# If eta_done exists, verify it's being cleared regularly (should be <2 min old)
if [ -f "$DATA_DIR/eta_done_1.json" ]; then
    FILE_AGE=$((NOW - $(stat -c %Y "$DATA_DIR/eta_done_1.json")))
    if [ "$FILE_AGE" -gt 120 ]; then
        echo "⚠️  DEADLOCK RISK: eta_done exists and is ${FILE_AGE}s old (not cycling)"
        echo "   → Timer-eta may be blocked waiting for timer-dev to clear"
        # Escalate to subagent
    fi
fi
```

#### Check B: /teta Monitoring Interval
```bash
# Verify /teta is being sent every ~5 min while process runs
LAST_TETA=$(grep "SENT /teta" "$ETA_LOG" | tail -1 | awk -F'[][]' '{print $2}')
if [ -n "$LAST_TETA" ]; then
    LAST_TETA_EPOCH=$(date -d "$LAST_TETA" +%s 2>/dev/null || echo "0")
    TETA_AGE=$((NOW - LAST_TETA_EPOCH))
    if [ "$TETA_AGE" -gt 600 ] && [ "$NEXT_STEP" = "4" ]; then
        echo "⚠️  MONITORING GAP: Last /teta was ${TETA_AGE}s ago (should be <5 min)"
        echo "   → Timer-eta may be stuck or blocked"
        # Escalate to subagent
    fi
fi
```

#### Check C: Log Pattern (Ignored without Cleared)
```bash
# In timer_dev.log, if we see "ETA_DONE ignored" without "ETA_DONE cleared"
RECENT_IGNORED=$(grep "ETA_DONE ignored" "$DEV_LOG" | tail -5 | wc -l)
RECENT_CLEARED=$(grep "ETA_DONE cleared" "$DEV_LOG" | tail -5 | wc -l)
if [ "$RECENT_IGNORED" -gt 0 ] && [ "$RECENT_CLEARED" -eq 0 ]; then
    echo "⚠️  STATE MISMATCH: ETA_DONE being ignored but NOT cleared"
    echo "   → Deadlock risk: timer-eta is blocked waiting for cleanup"
    # Escalate to subagent
fi
```

## Prevention Checklist

- [ ] Timer-dev: Always clear state files when ignoring signals (not just log them)
- [ ] Timer-eta: Implement timeout for "waiting" loops (don't wait forever)
- [ ] Supervisor: Monitor file age when they exist in data/ directory
- [ ] Supervisor: Track /teta send frequency (should be ~5 min in step 4)
- [ ] Supervisor: Detect pattern "ignored without cleared" in logs
- [ ] Documentation: Update SKILL.md with deadlock failure modes (see section 3.9)

## Recurrence Risk

**Without these improvements**: HIGH (same pattern could recur in eta_done or other file-based signaling)
**With Check A (file age)**: MEDIUM → LOW (catches this deadlock in <2 min)
**With Check B (/teta interval)**: MEDIUM → LOW (catches monitoring gaps)
**With Check C (log pattern)**: HIGH → LOW (catches incomplete cleanup)

## Implementation Priority

1. **Immediate (done)**: Fix timer-dev.sh cleanup (already applied ✅)
2. **Week 1**: Add Check A + B to supervisor (file age + monitoring interval)
3. **Week 2**: Add Check C to supervisor (log pattern matching)
4. **Week 3**: Update SKILL.md documentation with deadlock patterns

## Files to Update

- `.claude/skills/t-supervisor/SKILL.md` (section 3.9: add failure mode "deadlock due to incomplete cleanup")
- `.claude/skills/t-supervisor/superv_cycle_design.md` (step 3l: add file age checks)
- `timer/tmux_timer_dev.sh` (already fixed, verified working)
- `timer/tmux_timer_eta.sh` (optional: add timeout to prevent infinite waits)
