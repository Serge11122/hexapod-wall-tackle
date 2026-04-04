# Deadlock Incident Summary & Root Cause Analysis
## Timer-Eta Monitoring Blackout — April 4, 2026

---

## Quick Facts

| Metric | Value |
|--------|-------|
| **Incident Duration** | 14 minutes (20:14–20:28 PT) |
| **Monitoring Gap** | No /teta calls sent, no GPU/memory/loss tracking |
| **Root Cause** | Incomplete state management (eta_done not cleared) |
| **Supervisor Detection** | **MISSED** — reported "healthy" during blackout |
| **Fix Applied** | One-line code addition: `rm -f "$ETA_DONE"` in timer-dev.sh |
| **Recurrence Risk** | **HIGH** if supervisor enhancements not deployed |

---

## What Happened

### Timeline

| Time (PT) | Event | Status |
|-----------|-------|--------|
| 20:14:07 | Timer-eta sends /teta (monitoring call) | Normal |
| 20:15:47 | /teta completes, eta_done written | Premature (process still running) |
| 20:16–20:20 | Timer-dev detects eta_done, sees process alive, ignores | Correct decision |
| 20:16–20:20 | **BUG**: Timer-dev does NOT clear eta_done file | State leak |
| 20:20–20:28 | Timer-eta checks eta_done, sees file exists, BLOCKS | Cascading failure |
| 20:20–20:28 | **14-minute blackout**: No /teta sent, no monitoring | **Critical gap** |
| 20:25 | Supervisor runs check, sees next_step=4, eta_done exists | Incomplete analysis |
| 20:25 | Supervisor reports "HEALTHY" — assuming cleanup happened | **False positive** |
| 20:28:45 | External fix: supervisor_report identifies problem, timer-dev restarted | Recovery |
| 20:29:17 | Timer-eta resumes /teta calls | Monitoring restored |

---

## Why Supervisor Failed

### The Supervisor's Logic (Flawed)

```
IF next_step = 4 (monitoring)
AND eta_done exists
AND process is alive
AND timer-dev log shows "ignoring eta_done"
THEN "Everything is correct, system is healthy"
```

**Problem**: The supervisor checked WHETHER the decision was correct (yes, ignore is right) but NOT WHETHER the state was FULLY RESOLVED (cleanup missing).

### Missing Checks

The supervisor did NOT verify:

1. **File Cleanup**: "Was eta_done actually deleted after being ignored?"
   - Supervisor saw: eta_done exists
   - Supervisor concluded: timer-dev will handle it (assumed cleanup)
   - Reality: no cleanup code existed

2. **Monitoring Heartbeat**: "Is /teta being sent at expected intervals?"
   - Supervisor checked: is timer-eta session alive (yes)
   - Supervisor did NOT check: is /teta actually being called every 5 min?
   - Reality: /teta stalled 14 min ago

3. **File Age Analysis**: "How old is this eta_done file?"
   - Supervisor saw: eta_done exists
   - Supervisor did NOT compute: file timestamp (would show 14+ min stale)
   - Reality: file age indicated deadlock

4. **State Transition Completeness**: "Did the 'ignore' action include full cleanup?"
   - Supervisor assumed: yes (no explicit verification)
   - Reality: code had incomplete state management pattern

---

## The Root Cause

**In `/home/ubuntu/workspace/RLQuest/timer/tmux_timer_dev.sh`, lines 366–369:**

```bash
# BUGGY CODE (missing cleanup):
if [ -n "$TRACKED_PID" ] && kill -0 "$TRACKED_PID" 2>/dev/null; then
    echo "  ⚠️  WARNING: eta_done exists but PID $TRACKED_PID is STILL ALIVE. Ignoring premature signal."
    t_dev_log "ETA_DONE ignored: PID=$TRACKED_PID still running (eta_done was premature)"
    echo "  → Continuing monitoring. Will wait for process to actually exit or kill_switch."
    # ❌ MISSING: rm -f "$ETA_DONE"
else
    # ... cleanup when process is dead
fi
```

**The Pattern**:

Actor A (timer-dev):
1. Reads signal file
2. Makes decision: ignore it (process alive)
3. **FORGETS to clean it up**
4. Continues with normal operation

Actor B (timer-eta):
1. Reads signal file
2. Sees file exists
3. Waits for Actor A to delete it
4. **Blocked forever** (deletion never comes)

**Result**: Deadlock due to incomplete state management.

---

## The Fix

**One-line code addition:**

```bash
if [ -n "$TRACKED_PID" ] && kill -0 "$TRACKED_PID" 2>/dev/null; then
    echo "  ⚠️  WARNING: eta_done exists but PID $TRACKED_PID is STILL ALIVE. Clearing premature signal."
    rm -f "$ETA_DONE"  # ← ADDED THIS LINE
    t_dev_log "ETA_DONE cleared: PID=$TRACKED_PID still running (eta_done was premature, unblocking eta)"
    echo "  → Continuing monitoring. Cleared eta_done to unblock timer-eta for next /teta cycle."
else
    # ... cleanup when process is dead
fi
```

**Result**: Timer-eta unblocks on next cycle, /teta resumes every 5 min.

---

## Supervisor Enhancement Strategy

### Level 1: File Age Detection (Quick Win)
**Cost**: 2-3 bash lines  
**Benefit**: Catches stuck signal files  
**Implementation**: Check `stat -c %Y` on eta_done, flag if >10 min old

```bash
MTIME=$(stat -c %Y eta_done_1.json)
AGE=$(($(date +%s) - MTIME))
[ $AGE -gt 600 ] && echo "ALERT: eta_done stuck for $((AGE/60)) min"
```

### Level 2: Interval Tracking (Essential)
**Cost**: Log parsing + timestamp computation  
**Benefit**: Detects when monitoring has stalled  
**Implementation**: Parse timer_eta.log for "SENT /teta" entries, compute elapsed time

```bash
LAST_TETA=$(grep "SENT /teta" timer_eta.log | tail -1)
ELAPSED=$((CURRENT_EPOCH - $(date -d "$LAST_TETA_TIME" +%s)))
[ $ELAPSED -gt 420 ] && echo "ALERT: /teta not sent for $((ELAPSED/60)) min"
```

### Level 3: Log Correlation (Medium Complexity)
**Cost**: Pattern matching across two logs  
**Benefit**: Detects incomplete state transitions  
**Implementation**: Check for "ignored without cleared" or "waiting without cleared"

```bash
if grep "ETA_DONE ignored" timer_dev.log && ! grep "ETA_DONE cleared" timer_dev.log; then
    echo "ALERT: timer-dev ignored but didn't clear (incomplete state management)"
fi
```

### Level 4: State Machine Validator (Harder)
**Cost**: Explicit state diagram + validation code  
**Benefit**: Catches complex state machine bugs  
**Implementation**: Model expected state transitions, verify actual logs match

---

## Prevention Roadmap

### Immediate (This Week)
- [ ] Deploy Level 1 + Level 2 supervisor checks (file age + interval tracking)
- [ ] Add them to SKILL.md section 3m (new deadlock check)
- [ ] Update superv_cycle_design.md with new failure modes 9–10
- [ ] Create supervisor_checks.sh helper script
- [ ] Test on healthy system and simulated deadlock

### Short-Term (Next 2 Weeks)
- [ ] Deploy Level 3 (log correlation checks)
- [ ] Review all state file handoffs in timer architecture for similar patterns
- [ ] Add code review rule: "Ignoring a signal file requires explicit cleanup"
- [ ] Update timer-dev.sh, timer-eta.sh, and similar scripts to follow pattern

### Long-Term (Ongoing)
- [ ] Implement Level 4 (state machine validator)
- [ ] Document state machine ownership for each file (who writes, who reads, who clears)
- [ ] Audit other concurrent components for same incomplete state management pattern
- [ ] Consider replacing file-based coordination with robust message queue (lower risk)

---

## Key Learnings

### 1. Incomplete State Management is a Deadlock Factory

**Pattern**: Actor makes decision, forgets to signal completion.

```
Correct:  decide → cleanup → continue
Buggy:    decide → FORGET_cleanup → continue (other actor blocked)
```

**Prevention**: Every decision point must explicitly handle cleanup in ALL branches.

### 2. Supervisor Must Check Completion, Not Just Initiation

**Flawed check**: "Is the decision being made correctly?"  
**Correct check**: "Is the decision being FULLY RESOLVED, including cleanup?"

**Implementation**: Monitor file age, interval tracking, and log patterns — not just state flags.

### 3. File-Based Coordination is Fragile

**Risk**: File remains in stale state, blocking other actors indefinitely.

**Options**:
- Stronger supervisor checks (this incident → covered)
- More explicit state machine (better long-term)
- Message queue / RPC instead of files (lowest risk, higher complexity)

### 4. Assumptions About "Normal Behavior" Hide Bugs

**False assumption**: "If timer-dev ignores premature eta_done, everything is normal."  
**Reality**: Ignoring incomplete → cleanup missing → actor blocked.

**Prevention**: Require explicit verification of cleanup, not assumed cleanup.

---

## Supervisor Capability Gap

### What Supervisor Checked
- ✓ Is timer-dev session alive?
- ✓ Is next_step=4 (monitoring mode)?
- ✓ Does eta_done file exist?
- ✓ Is process alive (reason for ignoring)?
- ✓ Does timer-dev log show "ignoring" decision?
- **✗ Did timer-dev actually DELETE the file after ignoring?**
- **✗ How long has eta_done existed without being cleared?**
- **✗ When was the last /teta monitoring call actually sent?**
- **✗ Is timer-eta actively ticking or blocked waiting?**

### What Supervisor Should Check
- ✓ All of the above, PLUS:
- ✓ eta_done file age (via stat)
- ✓ /teta interval (grep last SENT timestamp, compute elapsed)
- ✓ Log correlation (ignored WITHOUT cleared = incomplete)
- ✓ Process alive check (reason for ignoring is valid)
- ✓ Combined deadlock pattern detection

---

## Recurrence Risk Assessment

### Without Supervisor Enhancements
**Risk**: **HIGH**

The code bug is fixed, but supervisor will still miss similar future bugs:
- Different files with incomplete cleanup
- Different actors with different blocking patterns
- Any scenario where one actor "ignores" without "cleaning up"

### With Level 1+2 Supervisor Enhancements
**Risk**: **LOW**

File age + interval tracking catches:
- Stuck signal files (age check)
- Stalled monitoring (interval check)
- Most deadlock patterns (combined checks)

### With All 4 Levels + Code Review Rules
**Risk**: **MINIMAL**

Comprehensive deadlock detection + prevention in code review + state machine validation catches:
- All file-based deadlocks
- Most state machine bugs
- Requires architectural intervention to completely eliminate (message queue)

---

## Documents Created

This analysis produced three documents:

1. **supervisor_deadlock_analysis.md** (this directory)
   - Detailed breakdown of why supervisor failed
   - Root cause pattern analysis
   - Four levels of supervisor improvement

2. **supervisor_enhancement_recommendations.md** (in `.claude/skills/t-supervisor/`)
   - Exact code changes for SKILL.md
   - Updates to superv_cycle_design.md
   - Bash helper script (supervisor_checks.sh)
   - Integration instructions
   - Testing recommendations

3. **DEADLOCK_INCIDENT_SUMMARY.md** (this file)
   - Executive summary
   - Quick facts and timeline
   - Prevention roadmap
   - Key learnings

---

## Next Steps

### For Supervisor Team
1. Review `supervisor_deadlock_analysis.md` for full context
2. Implement recommendations from `supervisor_enhancement_recommendations.md`
3. Test supervisor checks on healthy and simulated-deadlock systems
4. Deploy to production

### For Code Review
1. Add rule: "Signal file cleanup must be explicit in all branches"
2. Review timer-dev.sh, timer-eta.sh for similar patterns
3. Update code patterns library with examples

### For Architecture Review
1. Document state file ownership (who writes, reads, clears)
2. Consider long-term replacement of file-based coordination with message queue
3. Audit other concurrent components for same pattern

---

## Metrics

| Metric | Value | Status |
|--------|-------|--------|
| **Incident Duration** | 14 min | Fixed |
| **Training Impact** | Unmonitored for 14 min, otherwise normal | Acceptable |
| **Fix Complexity** | 1 line code + restart | Minimal |
| **Supervisor Improvement Timeline** | ~1 week for Levels 1–2 | On track |
| **Long-Term Solution** | Message queue (3–6 months) | Planned |

---

## Sign-Off

**Incident**: RESOLVED (code fixed, monitoring restored)  
**Supervisor Improvement**: PLANNED (recommendations ready for implementation)  
**Recurrence Risk**: HIGH (without supervisor enhancements) → LOW (with implementation)  

**Status**: ✅ Analysis complete, ready for execution

