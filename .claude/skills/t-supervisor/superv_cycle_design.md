# Timer Cycle Pipeline — Architecture & Design Reference

## Overview
The timer cycle pipeline uses four separate timer scripts and four separate Claude sessions.
Shell scripts do ALL data gathering and state management. Claude sessions only make judgment calls.

## Architecture

### The 4-Step Cycle
```
tconv (Step 1) → tdev_inline (Step 2) → tdeep (Step 3) → monitoring (Step 4) → repeat
    │                │                │                │
    │ Analyzes       │ Implements     │ Validates      │ Bash-only ticks
    │ convictions    │ code changes   │ before launch  │ until eta_done
    │ Writes tasks   │ Writes launch  │ Writes results │ (teta in t_{n}_eta)
    └─ memory_dev.md └─ launch_cmds   └─ deep_results  └─ kill_violations
```

### AUTO_MODE — Default Dispatch Behavior

**`AUTO_MODE=true` is the default** in `tmux_timer_dev.sh`. In auto mode:

- **Steps 1-3**: Timer-dev sends `/tdevauto` **ONCE per cycle** (not once per sub-skill). Tdevauto chains tconv→tdev_inline→tdeep internally in a single invocation, then goes IDLE. Timer-dev detects IDLE, reads output files (`launch_commands.json`, `deep_analysis_results.md`) to determine what tdevauto did, then advances state. No `/clear` is sent — context accumulates in the persistent session.
- **Step 4**: Timer-dev does NOT send any `/tdevauto` command. Step 4 is bash-only monitoring.
- **Phase flag**: `timer/data/t2_tdevauto_sent_N.txt` — written when `/tdevauto` is sent, deleted when IDLE is detected. Watchdog: 40 min (covers the full tconv+tdev_inline+tdeep chain).
- **Tick display**: Timer shows `tdevauto(→tconv)`, `tdevauto(→tdev_inline)`, `tdevauto(→tdeep)` depending on `next_step` at send time. Step 4 shows `monitoring`.

In legacy mode (`AUTO_MODE=false`), timer-dev sends `/clear` then the individual skill command (`/tconv`, `/tdev_inline`, `/tdeep`) per step, using `t2_tconv_sent_N.txt`, `t2_tdev_sent_N.txt`, `t2_tdeep_sent_N.txt` flags with a 20 min watchdog each. This mode is no longer the default.

### tdevauto — Internal Routing Logic

**Timer sends `/tdevauto` ONCE per cycle.** Tdevauto chains all applicable sub-skills (tconv→tdev_inline→tdeep) in a single invocation before going IDLE. It does NOT exit after each sub-skill and wait for the timer to re-send.

Starting route is determined by `next_step` in `timer_cycle_state.json`:

| `next_step` | Starting route | Typical chain |
|-------------|----------------|---------------|
| 1 | `/tconv` | tconv → tdev_inline → tdeep (if launch needed) |
| 2 | `/tdev_inline` | tdev_inline → tdeep (if launch_commands.json written) |
| 3 | `/tdeep` | tdeep only |
| 4 | **Exit immediately** | Bash-only — no LLM work |
| unknown | `/tconv` | Safe default |

**Chaining rule after each sub-skill:**
- After tconv: if memory_dev.md has tasks → run tdev_inline; else → exit
- After tdev_inline: if launch_commands.json written → run tdeep (MANDATORY); else → exit
- After tdeep: always exit

**Override rules** (tdevauto may start from a different sub-skill based on context — see tdevauto SKILL.md for full rules):
- If `kill_violations.md` exists → start from `/tconv` regardless of step
- If `next_step=2` AND `launch_commands.json` already exists → skip tdev_inline, run `/tdeep` directly
- If `next_step=1` AND memory_dev.md has fresh actionable tasks → skip tconv, run `/tdev_inline`

**Launch gate rule (CRITICAL):**
- **If `launch_commands.json` exists, tdeep MUST run** in the same tdevauto invocation. No override rule may bypass tdeep when launch commands are pending.
- Tdeep is the SOLE writer of `deep_analysis_results.md`. If tdeep never runs, that file is never written, and the process is never launched — regardless of what tdev_inline put in `launch_commands.json`.
- Tdeep writes `RECOMMENDATION: LAUNCH` (0 violations) → timer-dev launches. Tdeep writes `RECOMMENDATION: BLOCK` → timer-dev routes back to step 1.

### Four-Script Architecture

| Script | Timer Session | Claude Session | Model | Purpose |
|--------|--------------|----------------|-------|---------|
| `timer/tmux_timer_dev.sh N` | `timer-dev-N` | `t_N_dev` | Sonnet no-think | Steps 1-3: sends `/tdevauto` per tick (auto mode). Step 4: bash-only monitoring. Kill authority. |
| `timer/tmux_timer_eta.sh N` | `timer-eta-N` | `t_N_eta` | Haiku no-think | Monitoring ticks. /teta calls. Writes eta_done. |
| `timer/tmux_timer_superv.sh N` | `timer-superv-N` | `t_N_superv` | Haiku no-think | Supervisor. /t-superv every 10 min. |
| `timer/tmux_timer_rev.sh N` | `timer-rev-N` | `t_N_rev` | Haiku no-think | Reviewer. /trev_inline every 30 min. Goal velocity checks. |

### State Machine Owner: timer-dev
timer-dev OWNS timer_cycle_state.json. No t* skill writes it — not tconv, not tdev_inline, not tdeep, not tdevauto.

### Kill Authority: timer-dev
timer-eta writes kill_violations.md via /teta. timer-dev reads it and kills the process.
timer-eta NEVER kills processes directly.

### Coordination Protocol (Step 4)
```
timer-dev (step 4)          timer-eta
     │                           │
     │  ←── kill_violations.md ──│  (eta writes via /teta if bad metrics)
     │  ←── eta_done_N.json ─────│  (eta writes when process exits naturally)
     │                           │
     │  (timer-dev kills if kill_switch found)
     │  (timer-dev routes to tconv when eta_done found)
```

### Information Flow Direction
```
timer-dev → t_N_dev:    /tdevauto (auto mode, steps 1-3) OR /tconv,/tdev_inline,/tdeep (legacy mode)
tdevauto → tconv:       Skill tool dispatch (internal, no tmux send)
tdevauto → tdev_inline:        Skill tool dispatch (internal, no tmux send)
tdevauto → tdeep:       Skill tool dispatch (internal, no tmux send)
timer-eta → t_N_eta:    /teta (tmux send-keys)
timer-rev → t_N_rev:    /trev_inline (tmux send-keys)
t_N_dev → timer-dev:    launch_commands.json (tdev_inline), deep_analysis_results.md (tdeep)
t_N_eta → timer-dev:    kill_violations.md, eta_done_N.json
tconv → tdev_inline:           memory_dev.md
trev_inline → memory_dev.md:   directional pivot guidance (via subagent)
```

### File Ownership Map

| File | Written By | Read By | Location | Lifecycle |
|------|-----------|---------|----------|-----------|
| timer_cycle_state.json | timer-dev ONLY | all t*, timers | .manager/ | Persistent, atomic writes |
| memory_dev.md | tconv, tdev_inline, teta, trev_inline subagent | tdev_inline | .manager/ | Persistent, appended |
| launch_commands.json | tdev_inline | timer-dev, tdeep | .manager/ | Archived → t2_last_launch_N.json after launch |
| deep_analysis_results.md | tdeep | timer-dev | .manager/ | Overwritten each run |
| kill_violations.md | teta (t_N_eta session) | timer-dev | .manager/ | Created on failure, cleared before launch |
| timer_cycle_log.md | all t* skills | t-superv, trev_inline | .manager/ | Table format, newest first |
| timer_dev.log | timer-dev | t-superv | .manager/ | Line-based log, newest last |
| timer_eta.log | timer-eta | t-superv | .manager/ | Line-based log, newest last |
| eta_done_N.json | timer-eta (bg process) | timer-dev | timer/data/ | Written after /teta completes naturally; cleared before next launch |
| t2_launched_pid_N.txt | timer-dev (at launch) | timer-dev, timer-eta | timer/data/ | Runtime PID cache; authoritative is state.json long_running_pid |
| t2_spin_count_N.txt | timer-dev | timer-dev, t-superv | timer/data/ | Count of consecutive tconv→tdev_inline cycles without LAUNCH |
| t2_launch_blocked_N.txt | timer-dev | timer-dev, t-superv | timer/data/ | Reason for last BLOCK decision (e.g. NO_SCRIPT, VIOLATIONS) |
| t2_*_sent_N.txt | timer-dev | timer-dev | timer/data/ | Phase flags: epoch_ts + command; watchdog + observability |
| t2_last_launch_N.json | timer-dev | t-superv | timer/data/ | Archive of last launch_commands.json |
| t2_launch_expect_N.json | timer-dev | teta | timer/data/ | Launch expectations preserved before archive |
| t2_eta_ts_N.txt | timer-eta | timer-eta | timer/data/ | Timestamp of last /teta send (5-min rate limit) |
| system_state_N.md | timer-dev | tconv (system context) | timer/data/ | Overwritten each tick |
| supervisor_report.md | t-superv | user | .manager/ | Periodic report |
| reviewer_report.md | trev_inline | user | .manager/ | Periodic goal velocity report (every 30 min) |

### Two-Phase Execution Pattern (Steps 1-3)
```
Phase 1: timer-dev sends /tdevauto (auto mode) OR /tconv|/tdev_inline|/tdeep (legacy)
         → writes phase flag file with epoch timestamp
         AUTO_MODE flag: timer/data/t2_tdevauto_sent_N.txt (one per cycle, 40 min watchdog)
         LEGACY flags:   timer/data/t2_tconv_sent_N.txt, t2_tdev_sent_N.txt, t2_tdeep_sent_N.txt (20 min each)

(tdevauto chains tconv→tdev_inline→tdeep internally; timer-dev sees ACTIVE, waits)

Phase 2: timer-dev detects IDLE → reads output files → advances state
         Reads: launch_commands.json (did tdev_inline run?), deep_analysis_results.md (did tdeep run?)
         → If deep_analysis_results.md exists: advance to step 3 (launch check)
         → If only launch_commands.json: re-send tdevauto (tdeep didn't complete)
         → If neither: cycle complete, back to step 1
```

In auto mode, Phase 1 sends `/tdevauto` ONCE per cycle — tdevauto chains all applicable sub-skills internally. Timer-dev detects IDLE via pane capture (3-snapshot / 16s window) and owns all state transitions.

### Step 4: Monitoring Mode (No LLM in timer-dev)
```
timer-dev loop:
  1. Check kill_violations.md → if exists: kill PID, route to tconv
  2. Check eta_done_N.json → if exists: route to tconv (no LLM needed)
  3. Otherwise: log monitoring status (PID alive/dead), wait for next tick

timer-eta loop:
  1. Check if next_step=4 (else standby)
  2. Bash-only ticks while PID alive: log status, enforce 5-min /teta rate limit
  3. When PID dies (or 5 min elapsed): send /teta to t_N_eta Claude session
  4. Background poll: wait for t_N_eta IDLE → if no kill_switch: write eta_done_N.json
```

### IDLE Detection (timer-dev, steps 1-3)
3 tmux pane captures, 8 seconds apart, 80 lines each.
Both diffs must be zero (no change over 16s window) = IDLE.

### IDLE_LOOP
After Phase 2, timer-dev sets IDLE_LOOP=true to chain to next step in same tick.

### Launch Flow (Step 3)
1. Timer-dev detects `next_step=3` (launch_commands.json exists, tdev_inline wrote it)
2. **Auto mode**: Timer-dev sends `/tdevauto` → tdevauto routes to `/tdeep` internally
   **Legacy mode**: Timer-dev sends `/tdeep` directly
3. Timer-dev validates: script_file exists, gate progression OK (before or alongside /tdeep)
4. tdeep writes deep_analysis_results.md with TOTAL_BLOCKING count
5. Timer-dev reads count. If >0 → BLOCK (routes back to tconv/step 1). If 0 → nohup launch
6. Timer-dev writes PID to state.json (`long_running_pid`) AND `timer/data/t2_launched_pid_N.txt`
7. Timer-dev archives launch_commands.json → t2_last_launch_N.json
8. Timer-dev clears kill_violations.md and eta_done_N.json before entering step 4

**Critical**: tdeep MUST always write deep_analysis_results.md. If it doesn't exist, timer-dev never launches. Tdeep is the sole launch gate — even when routing through tdevauto.

### Monitoring Flow (Step 4)
```
timer-dev (bash only):
  - Poll kill_violations.md every tick → if exists: kill PID, route to tconv
  - Poll eta_done_N.json every tick → if exists: route to tconv
  - Log PID status each tick

timer-eta (bash + /teta):
  - Poll PID alive/dead each tick
  - /teta every 5 min while alive (rate limited via t2_eta_ts_N.txt)
  - /teta immediately when PID dies
  - After /teta completes (t_N_eta session IDLE): write eta_done_N.json
    (unless kill_violations.md exists — that means teta already wrote the kill switch)
```

## Common Failure Modes

### 1. Phase Stuck
Symptom: timer_dev.log shows PHASE_1, `t2_tdevauto_sent_N.txt` exists but no PHASE_2 for >40 min (auto mode) or >20 min per step (legacy)
Cause: Claude session hung, compacted mid-skill, or waiting for input during tconv/tdev_inline/tdeep chain
Fix: Watchdog resets after 40 min (auto) / 20 min (legacy). Supervisor can delete `t2_tdevauto_sent_N.txt` (auto mode) or the relevant `t2_*_sent_N.txt` flag file to force reset.

### 2. Spin Loop
Symptom: timer_cycle_log.md shows tconv→tdev_inline→tconv repeating with no LAUNCH
Cause: tdev_inline fails to produce valid launch_commands.json (missing script_file/module), OR tdeep blocks with VIOLATIONS
Diagnosis files: `timer/data/t2_spin_count_N.txt` (count), `timer/data/t2_launch_blocked_N.txt` (reason)
Fix: Spin counter pauses after 5 cycles. Supervisor reads both files to understand root cause. If t2_launch_blocked_N.txt says NO_SCRIPT → tdev_inline skill output is malformed. If VIOLATIONS → tdeep found real violations. Cross-reference deep_analysis_results.md.

### 3. Monitoring Stuck (eta_done never written)
Symptom: next_step=4, PID gone, timer_eta.log has no recent entries, no eta_done
Cause: timer-eta crashed, or t_N_eta session died mid-/teta, or bg poll timed out
Fix: Supervisor restarts timer-eta. Or manually writes eta_done_N.json to unblock.
Manual: `echo '{"status":"completed","pid":"","reason":"manual_unblock"}' > timer/data/eta_done_1.json`

### 4. Kill Switch Stale
Symptom: Process killed immediately after launch
Cause: kill_violations.md from PREVIOUS run still exists
Fix: Timer-dev deletes kill_violations.md and eta_done_N.json before each launch.

### 5. Violation Parsing Failure
Symptom: tdeep finds violations but timer-dev launches anyway
Cause: TOTAL_BLOCKING formatted differently than expected
Fix: Multi-format parsing, case-insensitive, default-to-BLOCK safety.

### 6. State File Corruption
Symptom: timer-dev loops on "Unknown step" or variables empty
Cause: Non-atomic JSON write interrupted
Fix: Atomic writes via .tmp + os.replace(). Supervisor fixes if corrupted.

### 7. Timer Crashed
Symptom: timer_dev.log or timer_eta.log stops updating (>5 min)
Cause: OOM, tmux killed, shell error
Fix: Supervisor restarts via `timer/tmux_timer_dev.sh 1 --stop && sleep 2 && timer/tmux_timer_dev.sh 1`

### 8. Deadlock Due to Incomplete State Cleanup
Symptom: 
- eta_done_N.json file exists for >2 min despite active process
- timer_eta.log shows repeated "waiting for timer-dev to clear" messages
- timer_dev.log shows repeated "ETA_DONE ignored" without corresponding "ETA_DONE cleared" entries
- /teta monitoring calls absent for >7 minutes during active step 4

Root cause: 
- timer-dev detects premature eta_done signal (process still alive)
- timer-dev decides to "ignore" but fails to complete cleanup (doesn't delete the file)
- timer-eta detects file exists → enters blocking loop waiting for deletion
- timer-eta unable to send new /teta calls → 14+ minute monitoring gap possible

Incident example (2026-04-04 20:14-20:28 PT):
- timer-eta sent /teta at 20:14:07, got response, wrote eta_done at 20:15:47 (process PID 2710146 still alive)
- timer-dev detected eta_done, found process alive, logged "ignoring" but did NOT delete the file
- timer-eta detected file exists, entered "waiting" loop
- For 14 minutes: no /teta calls sent, no monitoring, no process health checks
- Discovered by supervisor checking: file age (14 min old), /teta gap (14 min), log pattern ("ignored" without "cleared")

Fix: 
- timer-dev must ALWAYS complete cleanup: `rm -f "$ETA_DONE"` after deciding to ignore a premature signal
- Supervisor detects this via three checks:
  1. **File age check** — if eta_done_N.json exists AND is >120s old during active step 4 → deadlock risk
  2. **Monitoring interval check** — if /teta gap >420s (7 min) while process alive and step 4 active → deadlock risk
  3. **Log pattern check** — if "ETA_DONE ignored" entries exist without matching "ETA_DONE cleared" entries → incomplete cleanup detected

Prevention:
- All state changes with dependent waiters must complete cleanup atomically
- Never leave a file/flag in intermediate state
- When ignoring a signal, delete the signal file immediately

### 9. ETA_DONE Race Condition
Symptom: timer-dev sees eta_done at same tick as kill_violations
Cause: Rare; both written near-simultaneously
Fix: timer-dev checks kill_violations FIRST (higher priority). eta_done is ignored if kill switch present.

## Robustness Features

### Atomic State Writes
All state file updates write to .tmp then os.replace() — atomic on same filesystem.

### Phase Timeout Watchdog
- **AUTO_MODE**: if Phase 1→Phase 2 takes >40 min (covers full tconv+tdev_inline+tdeep chain), watchdog resets to tconv and deletes `t2_tdevauto_sent_N.txt`.
- **LEGACY_MODE**: if any individual step takes >20 min, watchdog resets to tconv.

### Spin Loop Detection
Counter increments each tconv→tdev_inline cycle. Pauses timer after 5 without launch.

### Kill Priority
kill_violations.md check runs BEFORE eta_done check in timer-dev. If both exist, kill wins.

### Restart-Resilient PID Tracking
PID written to state.json (`long_running_pid`) AND flat file at launch. On startup, state.json is authoritative; flat file is fallback. If flat file has PID but state.json doesn't, startup syncs automatically.

### ETA Done Background Poll
When PID dies and /teta is sent, timer-eta spawns a background process that polls t_N_eta session for IDLE and writes eta_done. Max wait 20 min then assumes complete.

### Launch Archive
launch_commands.json is renamed to t2_last_launch_N.json after launch (not deleted). Absence = nothing pending.

### Phase Flag Observability
Phase sentinel files contain `<epoch_ts> <command>` — timestamp for watchdog + command for diagnostics.

## Session Naming Convention
- Timer orchestrator sessions: `timer-dev-N`, `timer-eta-N`, `timer-superv-N`, `timer-rev-N`
- Claude work sessions: `t_N_dev`, `t_N_eta`, `t_N_superv`, `t_N_rev`
- N = instance ID (e.g., 1)

## Component Health Summary (What Supervisor Checks per Component)

| Component | Session | Interval | Health Signal | Failure Mode |
|-----------|---------|----------|---------------|--------------|
| timer-dev | timer-dev-N | continuous | timer_dev.log advancing, next_step changing | 3f: log stops >5 min |
| t_N_dev (Sonnet) | t_N_dev | per-phase | tdevauto→tconv/tdev_inline/tdeep rows in cycle_log | 3a: phase stuck >20 min; 3j: permission prompt |
| tdevauto (internal) | t_N_dev | per-phase | routes internally; same session as t_N_dev | stuck = t_N_dev stuck; wrong route = wrong sub-skill row in log |
| timer-eta | timer-eta-N | step 4 only | timer_eta.log advancing | 3g: log stops >5 min in step 4 |
| t_N_eta (Haiku) | t_N_eta | step 4 only | teta rows in cycle_log | 3j: permission prompt; session dead |
| timer-rev | timer-rev-N | 30 min | trev_inline rows in cycle_log | timer-rev dead or not ticking |
| t_N_rev (Haiku) | t_N_rev | 30 min | reviewer_report.md freshness | trev_inline not completing; session dead |
| timer-superv | timer-superv-N | 10 min | supervisor_report.md freshness | (self-referential — detected externally) |

**Spin loop detection (key secondary check):**
- `timer/data/t2_spin_count_N.txt`: consecutive tconv→tdev_inline cycles without LAUNCH. Value >0 = warning; >5 = pipeline self-paused.
- `timer/data/t2_launch_blocked_N.txt`: reason for last BLOCK. Read this FIRST before diagnosing a spin loop.

## Data Directory
All timer data files: `timer/data/` (at repo root)
All manager state files: `.manager/` (at repo root)
