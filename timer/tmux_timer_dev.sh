#!/bin/bash
# Timer Dev — Timer cycle step driver (tconv → tdev → tdeep+launch)
# Sonnet, no thinking. Steps 1-3. Skills spawn Opus subagents (medium effort) for heavy reasoning.
# Steps 1-3 only. Monitoring is handled by timer-eta (process auto-detection).
# Polls kill_violations.md (kill switch). Dev activates when no live project processes found.
#
# Usage: ./tmux_timer_dev.sh <instance_id> [interval]
#        ./tmux_timer_dev.sh <instance_id> --stop
#        ./tmux_timer_dev.sh <instance_id> --view
#        ./tmux_timer_dev.sh <instance_id> --status
#
# Dev mode is controlled by AUTO_MODE below (hardcoded):
#   AUTO_MODE=true  — sends /tdevauto each tick, no /clear, tdevauto routes internally (default)
#   AUTO_MODE=false — sends /clear + individual /tconv, /tdev, /tdeep per cycle (legacy)
#
# Claude session: t_{n}_dev  (Sonnet, no thinking, effort low — skills spawn Opus subagents)
# ETA session:    t_{n}_eta  (launched by tmux_timer_eta.sh separately)

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TIMER_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_INTERVAL_SECONDS=30
INSIDE_TMUX=false
INSTANCE_ID=""
AUTO_MODE=true  # true = /tdevauto (default). Set to false for legacy individual /tconv /tdev /tdeep mode.
STATE_FILE="$SCRIPT_DIR/.manager/timer_cycle_state.json"
CYCLE_LOG="$SCRIPT_DIR/.manager/timer_cycle_log.md"
DATA_DIR="$TIMER_DIR/data"
SEND_SCRIPT="$TIMER_DIR/tmux_send_claude.sh"
RUN_SCRIPT="$TIMER_DIR/tmux_run_claude.sh"
DEV_LOG="$SCRIPT_DIR/.manager/timer_dev.log"

# Model: Sonnet, thinking disabled, effort low.
# tconv/tdev/tdeep skills spawn Opus subagents (medium effort) for heavy reasoning.
# Main session is a lightweight orchestrator that reads state and dispatches skills.
DEV_MODEL_FLAGS="--model claude-sonnet-4-6 --thinking-off --effort low"

t_dev_log() {
    local PST_TS=$(TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M:%S PT')
    echo "[$PST_TS] $*" >> "$DEV_LOG"
}

step_name() {
    case $1 in
        1) echo "tconv" ;; 2) echo "tdev" ;; 3) echo "tdeep" ;;
        4) echo "monitoring" ;;
        *) echo "tconv" ;;
    esac
}

show_usage() {
    echo "Usage: ./tmux_timer_dev.sh <instance_id> [interval]"
    echo "       Interval: 0.5 (min), 2 (min), 90s (sec). Default: 0.5min (30s)."
    echo "       Plain numbers are MINUTES. Use 's' suffix for seconds."
    echo "       ./tmux_timer_dev.sh <instance_id> --stop|--view|--status"
}

if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then show_usage; exit 0; fi

if [[ "$1" == "--inside-tmux" ]]; then
    INSIDE_TMUX=true; shift; INSTANCE_ID="$1"; shift
else
    if [ -z "$1" ]; then echo "Error: Instance ID required"; show_usage; exit 1; fi
    INSTANCE_ID="$1"; shift
    if ! [[ "$INSTANCE_ID" =~ ^[0-9]+$ ]] || [ "$INSTANCE_ID" -lt 1 ]; then
        echo "Error: Instance ID must be >= 1"; exit 1
    fi
fi

DEV_ALIAS="t_${INSTANCE_ID}_dev"
DEV_TIMER_SESSION="timer-dev-${INSTANCE_ID}"
INTERVAL_SECONDS=$DEFAULT_INTERVAL_SECONDS

case "$1" in
    --stop)
        if tmux has-session -t "$DEV_TIMER_SESSION" 2>/dev/null; then
            tmux kill-session -t "$DEV_TIMER_SESSION"; echo "Timer-dev stopped"
        else echo "Not running"; fi; exit 0 ;;
    --view)
        if ! tmux has-session -t "$DEV_TIMER_SESSION" 2>/dev/null; then echo "Not running"; exit 1; fi
        exec tmux attach-session -t "$DEV_TIMER_SESSION" ;;
    --status)
        if tmux has-session -t "$DEV_TIMER_SESSION" 2>/dev/null; then
            echo "Timer-dev: RUNNING (timer session: $DEV_TIMER_SESSION)"
            echo "Dev Claude session: $DEV_ALIAS"
            tmux has-session -t "$DEV_ALIAS" 2>/dev/null && echo "  Claude session ALIVE" || echo "  Claude session DEAD"
            echo "State:"; cat "$STATE_FILE" 2>/dev/null
        else echo "Timer-dev: NOT RUNNING"; fi; exit 0 ;;
    [0-9]*|0.*)
        ARG="$1"; shift
        if echo "$ARG" | grep -q 's$'; then
            INTERVAL_SECONDS=$(echo "$ARG" | sed 's/s$//')
        else
            MINUTES=$(echo "$ARG" | sed 's/m$//')
            INTERVAL_SECONDS=$(echo "$MINUTES * 60" | bc | cut -d. -f1)
        fi ;;
esac

if [ "$INSIDE_TMUX" = false ]; then
    if tmux has-session -t "$DEV_TIMER_SESSION" 2>/dev/null; then
        tmux kill-session -t "$DEV_TIMER_SESSION"; sleep 1
    fi
    DISPLAY_MIN=$(echo "scale=1; $INTERVAL_SECONDS / 60" | bc)
    echo "Starting Timer-Dev | Instance: $INSTANCE_ID | Session: $DEV_ALIAS | Interval: ${DISPLAY_MIN}min"
    echo "View: ./tmux_timer_dev.sh $INSTANCE_ID --view"
    echo "Stop: ./tmux_timer_dev.sh $INSTANCE_ID --stop"
    mkdir -p "$DATA_DIR"
    tmux new-session -d -s "$DEV_TIMER_SESSION" "bash '$0' --inside-tmux $INSTANCE_ID ${INTERVAL_SECONDS}s"
    echo "Timer-dev started"; exit 0
fi

# ===== Inside tmux =====

DISPLAY_MIN=$(echo "scale=1; $INTERVAL_SECONDS / 60" | bc)
AUTO_LABEL=$([ "$AUTO_MODE" = true ] && echo "AUTO(/tdevauto)" || echo "LEGACY(individual)")
echo "Timer-Dev Started | Instance: $INSTANCE_ID | Dev session: $DEV_ALIAS | Interval: ${DISPLAY_MIN}min | Mode: $AUTO_LABEL | 's' skip, 'p' pause"
echo "========================================"
trap 'echo ""; echo "Timer-dev stopped"; exit 0' INT

mkdir -p "$DATA_DIR"
ITERATION=1
PAUSED=true

# read_keypress: reads one keypress, discarding mouse/escape sequences.
# Sets global KEYPRESS. Usage: read_keypress 1   (timeout in seconds)
read_keypress() {
    local TIMEOUT="${1:-1}"
    KEYPRESS=""
    local BYTE=""
    IFS= read -t "$TIMEOUT" -r -n 1 BYTE 2>/dev/null || true
    if [[ "$BYTE" == $'\x1b' ]]; then
        # ESC — drain the rest of the escape sequence (CSI, mouse data, etc.)
        local DRAIN=""
        while IFS= read -t 0.05 -r -n 1 DRAIN 2>/dev/null; do :; done
        KEYPRESS=""
    else
        KEYPRESS="$BYTE"
    fi
}

# send_dev_cmd SKILL_NAME [LOG_MSG]
# In auto mode: sends /tdevauto (no /clear). In legacy mode: sends /clear then /SKILL_NAME.
send_dev_cmd() {
    local SKILL="$1"
    local LOG_MSG="${2:-$SKILL}"
    if [ "$AUTO_MODE" = true ]; then
        bash "$SEND_SCRIPT" "$DEV_ALIAS" "/tdevauto"
        sleep 0.5
        bash "$SEND_SCRIPT" "$DEV_ALIAS" Enter
        t_dev_log "AUTO_SEND /tdevauto (routing to $SKILL) | $LOG_MSG"
    else
        bash "$SEND_SCRIPT" "$DEV_ALIAS" "/clear"
        sleep 0.5
        bash "$SEND_SCRIPT" "$DEV_ALIAS" Enter
        sleep 3
        bash "$SEND_SCRIPT" "$DEV_ALIAS" "/$SKILL"
        sleep 0.5
        bash "$SEND_SCRIPT" "$DEV_ALIAS" Enter
        t_dev_log "LEGACY_SEND /$SKILL | $LOG_MSG"
    fi
}

prepend_log() {
    local ROW="$1"
    if [ -f "$CYCLE_LOG" ]; then
        sed -i "5a\\$ROW" "$CYCLE_LOG"
    else
        echo "| Date/Time (PT) | Step | Goal Metric | Step Summary |" > "$CYCLE_LOG"
        echo "|---|---|---|---|" >> "$CYCLE_LOG"
        echo "$ROW" >> "$CYCLE_LOG"
    fi
}

while true; do
    SNAP_TS=$(date -u +%Y%m%d_%H%M%S)
    LOCAL_TS=$(date '+%Y-%m-%d %H:%M:%S')
    PST_TS=$(TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT')
    echo ""
    echo "[$LOCAL_TS] Tick #$ITERATION"

    # ===================================================================
    # PHASE 1: SYSTEM DATA GATHERING
    # ===================================================================
    SYS_STATE="$DATA_DIR/system_state_${INSTANCE_ID}.md"

    DISK_LINE=$(df -h / | tail -1)
    DISK_PCT=$(echo "$DISK_LINE" | awk '{print $5}' | tr -d '%')
    DISK_FREE=$(echo "$DISK_LINE" | awk '{print $4}')
    RAM_AVAIL=$(free -m | awk '/Mem:/{print $7}')
    RAM_TOTAL=$(free -m | awk '/Mem:/{print $2}')
    RAM_PCT=$((RAM_AVAIL * 100 / RAM_TOTAL))
    GPU_INFO=$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null || echo "N/A")

    LATEST_LOG=$(ls -t "$SCRIPT_DIR"/firstrate_learning/*/output/*.log "$SCRIPT_DIR"/firstrate_portfolio/*/output/*.log 2>/dev/null | head -1)
    LOG_TAIL=""
    if [ -n "$LATEST_LOG" ]; then LOG_TAIL=$(tail -5 "$LATEST_LOG" 2>/dev/null); fi

    # ===================================================================
    # PHASE 2: THRESHOLD CHECKS
    # ===================================================================
    ALERTS=""
    if [ "$DISK_PCT" -ge 90 ] 2>/dev/null; then
        ALERTS="${ALERTS}DISK_CRITICAL: ${DISK_PCT}% used, ${DISK_FREE} free. BLOCK launches until cleanup. "
    elif [ "$DISK_PCT" -ge 85 ] 2>/dev/null; then
        ALERTS="${ALERTS}DISK_CLEANUP: ${DISK_PCT}% used, ${DISK_FREE} free. tconv must trigger cache cleanup. "
    elif [ "$DISK_PCT" -ge 80 ] 2>/dev/null; then
        ALERTS="${ALERTS}DISK_WARNING: ${DISK_PCT}% used, ${DISK_FREE} free. "
    fi
    if [ "$RAM_PCT" -le 10 ] 2>/dev/null; then
        ALERTS="${ALERTS}OOM_RISK: RAM ${RAM_AVAIL}MB available of ${RAM_TOTAL}MB (${RAM_PCT}%). "
    elif [ "$RAM_PCT" -le 20 ] 2>/dev/null; then
        ALERTS="${ALERTS}OOM_WARNING: RAM ${RAM_AVAIL}MB available of ${RAM_TOTAL}MB (${RAM_PCT}%). "
    fi

    # ===================================================================
    # PHASE 3: ACTIVITY DETECTION (Claude dev session)
    # ===================================================================
    SESSION_EXISTS=false
    if tmux has-session -t "$DEV_ALIAS" 2>/dev/null; then SESSION_EXISTS=true; fi

    ACTIVITY="NO_SESSION"
    PANE_TAIL=""

    if [ "$SESSION_EXISTS" = true ]; then
        tmux capture-pane -t "$DEV_ALIAS" -p -S -80 > "$DATA_DIR/dev_s1_${INSTANCE_ID}.txt" 2>/dev/null
        sleep 8
        tmux capture-pane -t "$DEV_ALIAS" -p -S -80 > "$DATA_DIR/dev_s2_${INSTANCE_ID}.txt" 2>/dev/null
        sleep 8
        tmux capture-pane -t "$DEV_ALIAS" -p -S -80 > "$DATA_DIR/dev_s3_${INSTANCE_ID}.txt" 2>/dev/null

        DIFF12=$(diff "$DATA_DIR/dev_s1_${INSTANCE_ID}.txt" "$DATA_DIR/dev_s2_${INSTANCE_ID}.txt" 2>/dev/null | wc -l)
        DIFF23=$(diff "$DATA_DIR/dev_s2_${INSTANCE_ID}.txt" "$DATA_DIR/dev_s3_${INSTANCE_ID}.txt" 2>/dev/null | wc -l)
        PANE_TAIL=$(tail -10 "$DATA_DIR/dev_s3_${INSTANCE_ID}.txt")

        if [ "$DIFF12" -eq 0 ] && [ "$DIFF23" -eq 0 ]; then ACTIVITY="IDLE"; else ACTIVITY="ACTIVE"; fi
    fi

    # ===================================================================
    # PHASE 5: READ CYCLE STATE
    # ===================================================================
    CYCLE_NUM=0; CURRENT_STEP=0; NEXT_STEP=1; CYCLE_STATUS=""; LR_PID=""
    if [ -f "$STATE_FILE" ]; then
        CYCLE_NUM=$(grep -o '"cycle": *[0-9]*' "$STATE_FILE" | grep -o '[0-9]*')
        CURRENT_STEP=$(grep -o '"current_step": *[0-9]*' "$STATE_FILE" | grep -o '[0-9]*')
        NEXT_STEP=$(grep -o '"next_step": *[0-9]*' "$STATE_FILE" | grep -o '[0-9]*')
        CYCLE_STATUS=$(grep -o '"status": *"[^"]*"' "$STATE_FILE" | sed 's/"status": *"//;s/"//')
        LR_PID=$(grep -o '"long_running_pid": *[0-9]*' "$STATE_FILE" | grep -o '[0-9]*' | tail -1)
    fi
    # Startup PID fallback: sync flat file → state.json if needed
    if [ -z "$LR_PID" ] && [ -f "$DATA_DIR/t2_launched_pid_${INSTANCE_ID}.txt" ]; then
        LR_PID=$(cat "$DATA_DIR/t2_launched_pid_${INSTANCE_ID}.txt" 2>/dev/null)
        if [ -n "$LR_PID" ] && [ "$NEXT_STEP" = "4" ]; then
            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['long_running_pid'] = $LR_PID
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
            echo "  [startup] Recovered long_running_pid=$LR_PID from flat file → synced to state.json"
        fi
    fi

    _RAW_CMD=$(step_name $NEXT_STEP)
    if [ "$AUTO_MODE" = true ]; then
        NEXT_CMD="tdevauto(→$_RAW_CMD)"
    else
        NEXT_CMD="$_RAW_CMD"
    fi

    # ===================================================================
    # PHASE 6: WRITE SYSTEM STATE FILE
    # ===================================================================
    cat > "$SYS_STATE" <<EOF
# System State — $SNAP_TS — Tick #$ITERATION

## Resources
- Disk: ${DISK_PCT}% used, ${DISK_FREE} free
- RAM: ${RAM_AVAIL}MB available / ${RAM_TOTAL}MB total (${RAM_PCT}% free)
- GPU: $GPU_INFO

## Alerts
${ALERTS:-none}

## Activity
- Dev session ($DEV_ALIAS): $ACTIVITY (diff12=$DIFF12 diff23=$DIFF23)

## Cycle State
- Cycle: $CYCLE_NUM | Current step: $CURRENT_STEP | Next: $NEXT_STEP ($NEXT_CMD)
- Long-running PID: ${LR_PID:-none}

## Latest Log (tail)
$LOG_TAIL

## Dev Pane (last 20 lines)
$PANE_TAIL
EOF

    # ===================================================================
    # PHASE 7: LOGGING
    # ===================================================================
    t_dev_log "TICK $ITERATION | activity=$ACTIVITY | next_step=$NEXT_STEP($NEXT_CMD) | disk=${DISK_PCT}% | gpu=$GPU_INFO"
    echo "  Disk: ${DISK_PCT}% | RAM: ${RAM_PCT}% free | GPU: $GPU_INFO | Next: $NEXT_STEP($NEXT_CMD)"
    [ -n "$ALERTS" ] && echo "  ALERTS: $ALERTS"

    # ===================================================================
    # PHASE 8: DECIDE ACTION
    # ===================================================================

    if [ "$PAUSED" = true ]; then
        echo "  PAUSED — skipping tick ('r' resume in wait prompt)"
        t_dev_log "TICK $ITERATION | PAUSED — skipped"
    elif [ "$ACTIVITY" = "NO_SESSION" ]; then
        echo "  → No dev session. Starting one."
        bash "$RUN_SCRIPT" "$DEV_ALIAS" $DEV_MODEL_FLAGS

    elif [ "$ACTIVITY" = "ACTIVE" ]; then
        echo "  → Dev session active. Waiting."

    elif [ "$ACTIVITY" = "IDLE" ]; then

        # ===================================================================
        # AUTO PROCESS DETECTION: scan for live project processes (etimes > 300, not zombie)
        # If processes found → standby (ETA timer handles monitoring).
        # If no processes → active dev mode (send /tdevauto).
        # Kill switch still triggers immediate kill + dev reactivation.
        # ===================================================================
        KILL_SWITCH="$SCRIPT_DIR/.manager/kill_violations.md"
        TRACKED_PID_FILE="$DATA_DIR/t2_launched_pid_${INSTANCE_ID}.txt"
        TRACKED_PID=$(cat "$TRACKED_PID_FILE" 2>/dev/null)

        LIVE_PIDS=$(ps -eo pid,stat,etimes,args 2>/dev/null \
            | grep python | grep -v grep | grep -v vscode \
            | grep -E 'firstrate_|trade_|experiments' \
            | awk '$2 !~ /^Z/ && $3 >= 300 {print $1}')

        # === KILL SWITCH: teta wrote kill_violations.md → kill all project processes ===
        if [ -f "$KILL_SWITCH" ] && [ -n "$LIVE_PIDS" ]; then
            VIOLATION_STATUS=$(grep "^## Status:" "$KILL_SWITCH" 2>/dev/null | head -1)
            if echo "$VIOLATION_STATUS" | grep -q "NONE"; then
                echo "  → kill_violations.md exists but Status: NONE (no violations). Continue standby."
                t_dev_log "kill_violations.md Status: NONE — process approved to continue."
            else
                echo "  *** KILL SWITCH: Violations detected by /teta ***"
                cat "$KILL_SWITCH"
                if [ -n "$TRACKED_PID" ] && kill -0 "$TRACKED_PID" 2>/dev/null; then
                    echo "  → Killing PID $TRACKED_PID and children..."
                    pkill -P "$TRACKED_PID" 2>/dev/null
                    kill "$TRACKED_PID" 2>/dev/null
                    sleep 2
                    if kill -0 "$TRACKED_PID" 2>/dev/null; then
                        pkill -9 -P "$TRACKED_PID" 2>/dev/null
                        kill -9 "$TRACKED_PID" 2>/dev/null
                    fi
                    echo "  → PID $TRACKED_PID killed."
                fi
                # Kill any remaining project processes
                PROJ_PIDS=$(ps -eo pid,args | grep python | grep -v grep | grep -v vscode | grep -E 'firstrate_|trade_|experiments' | awk '{print $1}')
                for P in $PROJ_PIDS; do kill "$P" 2>/dev/null; done
                sleep 1
                PROJ_PIDS=$(ps -eo pid,args | grep python | grep -v grep | grep -v vscode | grep -E 'firstrate_|trade_|experiments' | awk '{print $1}')
                for P in $PROJ_PIDS; do kill -9 "$P" 2>/dev/null; done

                # Record kill in memory
                KILL_REASON=$(head -10 "$KILL_SWITCH" 2>/dev/null | tr '\n' ' ')
                python3 -c "
from datetime import datetime
ts = datetime.now().strftime('%Y-%m-%d %H:%M')
pid = '$TRACKED_PID'
reason = '''$KILL_REASON'''
mgr = '$SCRIPT_DIR/.manager'
with open(f'{mgr}/memory_dev.md', 'a') as f:
    f.write(f'\n[{ts}]: PID {pid} KILLED — {reason.strip()}. Must fix before re-launching.\n')
" 2>/dev/null

                rm -f "$TRACKED_PID_FILE" "$DATA_DIR/t2_eta_ts_${INSTANCE_ID}.txt" \
                      "$DATA_DIR/t2_launch_expect_${INSTANCE_ID}.json" \
                      "$SCRIPT_DIR/.manager/active_run_${INSTANCE_ID}.json" \
                      "$KILL_SWITCH"
                echo "  → All processes killed. Kill switch cleared. Routing to tconv."
                prepend_log "| $PST_TS | timer-dev | — | KILLED PID $TRACKED_PID: violations detected |"
                t_dev_log "KILLED PID=$TRACKED_PID reason=$(head -3 "$KILL_SWITCH" 2>/dev/null | tr '\n' ' ')"
                # LIVE_PIDS now empty after kill — fall through to dev mode below
                LIVE_PIDS=""
            fi
        fi

        if [ -n "$LIVE_PIDS" ]; then
            # Processes running — standby. ETA timer handles /teta monitoring.
            LIVE_COUNT=$(echo "$LIVE_PIDS" | wc -w)
            if [ -n "$TRACKED_PID" ]; then
                LR_ELAPSED=$(ps -p "$TRACKED_PID" -o etime= 2>/dev/null | xargs)
                LR_RSS=$(ps -p "$TRACKED_PID" -o rss= 2>/dev/null | awk '{printf "%.1f", $1/1024/1024}')
                echo "  → Standby: $LIVE_COUNT process(es) running. Primary PID $TRACKED_PID (${LR_ELAPSED}, ${LR_RSS}GB). ETA monitoring."
            else
                echo "  → Standby: $LIVE_COUNT process(es) running (not yet tracked). ETA monitoring."
            fi
            t_dev_log "STANDBY | live_pids=$LIVE_COUNT | tracked=${TRACKED_PID:-none}"

        else
            # No live processes — active dev mode. Enter the steps 1-3 loop.
            # If processes just completed, clean up PID file.
            if [ -n "$TRACKED_PID" ]; then
                rm -f "$TRACKED_PID_FILE" "$DATA_DIR/t2_eta_ts_${INSTANCE_ID}.txt" \
                      "$DATA_DIR/t2_launch_expect_${INSTANCE_ID}.json" \
                      "$SCRIPT_DIR/.manager/active_run_${INSTANCE_ID}.json"
                echo "  → Process completed (PID $TRACKED_PID gone). Routing to tconv."
                prepend_log "| $PST_TS | timer-dev | — | COMPLETED: PID $TRACKED_PID gone → tconv |"
                t_dev_log "PROCESS_DONE PID=$TRACKED_PID gone, cleared. Routing to tconv."
            fi

        IDLE_LOOP=true
        while [ "$IDLE_LOOP" = true ]; do
        IDLE_LOOP_REENTRY=$IDLE_LOOP
        IDLE_LOOP=false

        # Re-read state
        NEXT_STEP=$(grep -o '"next_step": *[0-9]*' "$STATE_FILE" | grep -o '[0-9]*')
        _RAW_CMD=$(step_name $NEXT_STEP)
        if [ "$AUTO_MODE" = true ]; then
            NEXT_CMD="tdevauto(→$_RAW_CMD)"
        else
            NEXT_CMD="$_RAW_CMD"
        fi
        if [ "$IDLE_LOOP_REENTRY" = true ]; then
            t_dev_log "IDLE_LOOP re-entering, next_step=$NEXT_STEP"
        fi

        # ===================================================================
        # STEP 3 (tdeep): Validate launch_commands.json, then read results + launch
        # (In AUTO_MODE, tdevauto already ran tdeep. We just read results here.)
        # ===================================================================
        if [ "$NEXT_STEP" = "3" ]; then
            LAUNCH_JSON="$SCRIPT_DIR/.manager/launch_commands.json"
            VENV="$SCRIPT_DIR/firstrate_learning/.venv/bin/python"
            DEEP_RESULTS="$SCRIPT_DIR/.manager/deep_analysis_results.md"
            VALIDATED_LAUNCH="$DATA_DIR/t2_validated_launch_${INSTANCE_ID}.json"
            LAUNCH_BLOCKED="$DATA_DIR/t2_launch_blocked_${INSTANCE_ID}.txt"

            if [ ! -f "$LAUNCH_JSON" ]; then
                echo "  → No launch_commands.json. → tconv."
                python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'no_launch'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                rm -f "$VALIDATED_LAUNCH" "$LAUNCH_BLOCKED"

            else
                # Validate launch command fields
                rm -f "$VALIDATED_LAUNCH" "$LAUNCH_BLOCKED"

                python3 -c "
import json, sys, os, glob

LAUNCH_JSON = '$LAUNCH_JSON'
VALIDATED = '$VALIDATED_LAUNCH'
BLOCKED = '$LAUNCH_BLOCKED'
SCRIPT_DIR = '$SCRIPT_DIR'

try:
    with open(LAUNCH_JSON) as f: cmds = json.load(f)
    if not isinstance(cmds, list): cmds = [cmds]
    cmd = cmds[0]

    script_file = cmd.get('script_file', '')
    mod = cmd.get('module', '')
    if not script_file and mod:
        script_file = mod.replace('.', '/') + '.py'
    if not script_file:
        with open(BLOCKED, 'w') as f: f.write('NO_SCRIPT: no script_file or module in launch_commands.json')
        sys.exit(0)

    full_path = os.path.join(SCRIPT_DIR, script_file)
    if not os.path.isfile(full_path):
        with open(BLOCKED, 'w') as f: f.write(f'FILE_NOT_FOUND: {script_file} does not exist at {full_path}')
        sys.exit(0)

    mod = script_file.replace('/', '.').replace('.py', '')
    flags = cmd.get('flags', [])
    log = cmd.get('log', 'output.log')

    flags_str = ' '.join(flags)
    mod_dir = os.path.dirname(full_path)
    if '--full' in flags_str:
        if not glob.glob(os.path.join(mod_dir, 'models', 'run_*_prove*')):
            with open(BLOCKED, 'w') as f: f.write('GATE: --full without prove-out dir')
            sys.exit(0)
    elif '--prove-out' in flags_str:
        if not glob.glob(os.path.join(mod_dir, 'models', 'run_*_smoke*')):
            with open(BLOCKED, 'w') as f: f.write('GATE: --prove-out without smoke dir')
            sys.exit(0)

    with open(VALIDATED, 'w') as f:
        json.dump({'module': mod, 'flags': ' '.join(flags), 'log': log, 'script': script_file}, f)

except Exception as e:
    with open(BLOCKED, 'w') as f: f.write(f'ERROR: {e}')
" 2>/dev/null

                if [ -f "$LAUNCH_BLOCKED" ]; then
                    REASON=$(cat "$LAUNCH_BLOCKED")
                    echo "  *** BLOCKED: $REASON ***"
                    python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'launch_blocked'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                    prepend_log "| $PST_TS | timer-dev | — | BLOCKED: $REASON |"
                elif [ -f "$VALIDATED_LAUNCH" ]; then
                    echo "  → Validated. Reading deep_analysis_results.md..."
                    # tdevauto already ran tdeep. Read its output.
                    VIOL_COUNT=0
                    if [ -f "$DEEP_RESULTS" ]; then
                        DEEP=$(cat "$DEEP_RESULTS")
                        PARSED_COUNT=$(echo "$DEEP" | grep -oiP 'TOTAL.?BLOCKING[:\s]*\K[0-9]+' | tail -1)
                        if [ -z "$PARSED_COUNT" ]; then
                            PARSED_COUNT=$(echo "$DEEP" | grep -oiP 'VIOLATIONS?[:\s]*\K[0-9]+' | tail -1)
                        fi
                        if [ -z "$PARSED_COUNT" ]; then
                            PARSED_COUNT=$(echo "$DEEP" | grep -oiP 'blocking[:\s]*\K[0-9]+' | tail -1)
                        fi
                        if [ -n "$PARSED_COUNT" ]; then VIOL_COUNT=$PARSED_COUNT; fi
                        if echo "$DEEP" | grep -qi "RECOMMENDATION.*BLOCK"; then
                            if [ "$VIOL_COUNT" -eq 0 ]; then VIOL_COUNT=1; fi
                        fi
                        FILE_SIZE=$(wc -c < "$DEEP_RESULTS" 2>/dev/null || echo "0")
                        if [ "$VIOL_COUNT" -eq 0 ] && [ "$FILE_SIZE" -gt 100 ]; then
                            if ! echo "$DEEP" | grep -qi "RECOMMENDATION.*LAUNCH"; then
                                echo "  *** WARNING: Cannot parse violation count AND no LAUNCH recommendation. Defaulting to BLOCK."
                                VIOL_COUNT=1
                            fi
                        fi
                        echo "  → Violations: $VIOL_COUNT"
                    else
                        echo "  → tdeep finished but no results file. Blocking."
                        VIOL_COUNT=1
                    fi

                    if [ "$VIOL_COUNT" -gt 0 ]; then
                        echo "  *** BLOCKED: $VIOL_COUNT violation(s) from tdeep. ***"
                        prepend_log "| $PST_TS | timer-dev | — | BLOCKED: $VIOL_COUNT violations from tdeep |"
                        t_dev_log "BLOCKED violations=$VIOL_COUNT"
                        rm -f "$VALIDATED_LAUNCH" "$LAUNCH_BLOCKED" "$LAUNCH_JSON"
                        python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'launch_blocked'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                        IDLE_LOOP=true
                    else
                        # CRITICAL: Clear spin counter on successful launch approval (0 violations)
                        echo "0" > "$DATA_DIR/t2_spin_count_${INSTANCE_ID}.txt"

                        LAUNCH_INFO=$(python3 -c "
import json
with open('$LAUNCH_JSON') as f: cmds = json.load(f)
if not isinstance(cmds, list): cmds = [cmds]
cmd = cmds[0]
print(f'{cmd[\"module\"]}|{\" \".join(cmd.get(\"flags\",[]))}|{cmd.get(\"log\",\"output.log\")}')
" 2>/dev/null)
                        MOD=$(echo "$LAUNCH_INFO" | cut -d'|' -f1)
                        FLAGS=$(echo "$LAUNCH_INFO" | cut -d'|' -f2)
                        LOGFILE=$(echo "$LAUNCH_INFO" | cut -d'|' -f3)

                        if [ -z "$MOD" ]; then
                            echo "  → Failed to parse launch_commands.json. Blocking."
                            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'parse_error'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                        else
                            mkdir -p "$(dirname "$SCRIPT_DIR/$LOGFILE")" 2>/dev/null
                            echo "  → Launching: $VENV -u -m $MOD $FLAGS"
                            "$VENV" -u -m $MOD $FLAGS > "$SCRIPT_DIR/$LOGFILE" 2>&1 &
                            LAUNCH_PID=$!
                            disown $LAUNCH_PID
                            sleep 2
                            # Cross-check: ensure LAUNCH_PID is the actual training process, not a wrapper
                            PGREP_PID=$(pgrep -f "$MOD" | head -1 2>/dev/null)
                            if [ -n "$PGREP_PID" ] && [ "$PGREP_PID" != "$LAUNCH_PID" ]; then
                                t_dev_log "⚠ PID mismatch: disown gave $LAUNCH_PID, but pgrep found $PGREP_PID. Using pgrep result."
                                LAUNCH_PID="$PGREP_PID"
                            fi
                            if kill -0 "$LAUNCH_PID" 2>/dev/null; then
                                python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'launched'; s['long_running_pid'] = $LAUNCH_PID
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                                echo "$LAUNCH_PID" > "$DATA_DIR/t2_launched_pid_${INSTANCE_ID}.txt"
                                echo "  → PID $LAUNCH_PID. Monitoring mode (eta session will track)."
                                prepend_log "| $PST_TS | timer-dev | — | LAUNCH PID $LAUNCH_PID: $MOD $FLAGS |"
                                t_dev_log "LAUNCH PID=$LAUNCH_PID module=$MOD flags=$FLAGS"
                                # Write active run pointer for teta
                                python3 -c "
import json, os
from datetime import datetime, timezone
try:
    with open('$LAUNCH_JSON') as f: cmds = json.load(f)
    if not isinstance(cmds, list): cmds = [cmds]
    cmd = cmds[0]
    expect = cmd.get('expect', {})
    smoke_dir = cmd.get('smoke_dir', '')
    pointer = {
        'pid': $LAUNCH_PID,
        'module': '$MOD',
        'flags': '$FLAGS',
        'log': cmd.get('log', ''),
        'smoke_dir': smoke_dir,
        'launched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'expect': expect,
    }
    out = '$SCRIPT_DIR/.manager/active_run_${INSTANCE_ID}.json'
    tmp = out + '.tmp'
    with open(tmp, 'w') as f: json.dump(pointer, f, indent=2)
    os.replace(tmp, out)
    with open('$DATA_DIR/t2_launch_expect_${INSTANCE_ID}.json', 'w') as f:
        json.dump(expect, f)
except Exception as e:
    import sys; print(f'active_run write failed: {e}', file=sys.stderr)
" 2>/dev/null
                                mv -f "$LAUNCH_JSON" "$DATA_DIR/t2_last_launch_${INSTANCE_ID}.json" 2>/dev/null
                                rm -f "$VALIDATED_LAUNCH" "$LAUNCH_BLOCKED" \
                                      "$DATA_DIR/t2_eta_ts_${INSTANCE_ID}.txt" \
                                      "$SCRIPT_DIR/.manager/kill_violations.md"
                            else
                                echo "  → Launch failed (PID died immediately). → tconv."
                                rm -f "$VALIDATED_LAUNCH" "$LAUNCH_BLOCKED"
                                python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'launch_failed'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                            fi
                        fi
                    fi
                else
                    echo "  → Validation produced no output. Blocking."
                    python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'validation_error'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                fi
            fi

        # ===================================================================
        # STEPS 1-3 (AUTO_MODE): Send /tdevauto once. tdevauto chains tconv→tdev→tdeep
        # internally. Timer detects IDLE after tdevauto completes all steps, then reads
        # output files to determine what happened and advance state.
        #
        # STEPS 1-3 (LEGACY_MODE): Send /tconv, /tdev, /tdeep separately (one per tick).
        # Two-phase flag files track send→IDLE per step.
        # ===================================================================
        elif [ "$NEXT_STEP" = "1" ] || [ "$NEXT_STEP" = "2" ]; then
            TDEVAUTO_SENT="$DATA_DIR/t2_tdevauto_sent_${INSTANCE_ID}.txt"
            LAUNCH_JSON="$SCRIPT_DIR/.manager/launch_commands.json"
            DEEP_RESULTS="$SCRIPT_DIR/.manager/deep_analysis_results.md"

            if [ "$AUTO_MODE" = true ]; then
                # AUTO_MODE: single /tdevauto send covers all pending steps (1→2→3 internally)
                if [ ! -f "$TDEVAUTO_SENT" ]; then
                    STEP_LABEL=$(step_name $NEXT_STEP)
                    echo "  → Sending /tdevauto (routes to $STEP_LABEL and may chain further)"
                    send_dev_cmd "$STEP_LABEL" "auto step $NEXT_STEP"
                    printf '%s /tdevauto' "$(date +%s)" > "$TDEVAUTO_SENT"
                    prepend_log "| $PST_TS | timer-dev | — | Sent /tdevauto (→$STEP_LABEL) |"
                    t_dev_log "AUTO sent /tdevauto (→$STEP_LABEL) next_step=$NEXT_STEP"
                else
                    # Session is IDLE — tdevauto completed. Determine what it did.
                    FLAG_TS=$(awk '{print $1}' "$TDEVAUTO_SENT" 2>/dev/null || echo "0")
                    NOW_EPOCH=$(date +%s)
                    PHASE_ELAPSED=$((NOW_EPOCH - FLAG_TS))
                    WATCHDOG_LIMIT=2400  # 40 min max for entire tconv+tdev+tdeep chain

                    if [ "$PHASE_ELAPSED" -gt "$WATCHDOG_LIMIT" ]; then
                        echo "  *** WATCHDOG: tdevauto stuck $(($PHASE_ELAPSED / 60))m. Resetting."
                        rm -f "$TDEVAUTO_SENT"
                        python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'watchdog_reset'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                        prepend_log "| $PST_TS | timer-dev | — | WATCHDOG: tdevauto stuck $(($PHASE_ELAPSED / 60))m. Reset. |"
                        t_dev_log "WATCHDOG_RESET phase_elapsed=${PHASE_ELAPSED}s"
                        IDLE_LOOP=true
                    else
                        rm -f "$TDEVAUTO_SENT"
                        echo "  → tdevauto completed (IDLE). Reading output files..."

                        # Re-read state — tdevauto may have advanced next_step internally
                        NEXT_STEP=$(grep -o '"next_step": *[0-9]*' "$STATE_FILE" | grep -o '[0-9]*')
                        CYCLE_STATUS=$(grep -o '"status": *"[^"]*"' "$STATE_FILE" | sed 's/"status": *"//;s/"//')
                        echo "  → State after tdevauto: next_step=$NEXT_STEP status=$CYCLE_STATUS"

                        # Check for rogue process launched by tdev
                        ROGUE_PID=$(ps -eo pid,stat,args 2>/dev/null | grep python | grep -v grep | grep -v vscode | grep -v '^.*Z' | grep -E 'firstrate_|trade_|experiments' | awk '{print $1}' | head -1)
                        if [ -n "$ROGUE_PID" ]; then
                            echo "  *** WARNING: Rogue process $ROGUE_PID found. Entering monitoring."
                            echo "$ROGUE_PID" > "$DATA_DIR/t2_launched_pid_${INSTANCE_ID}.txt"
                            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'rogue_launch_detected'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                            rm -f "$DATA_DIR/t2_eta_ts_${INSTANCE_ID}.txt"
                            prepend_log "| $PST_TS | timer-dev | — | ROGUE LAUNCH: PID $ROGUE_PID → monitoring |"

                        # If launch_commands.json exists, tdevauto ran tdeep (or needs to next tick)
                        elif [ -f "$LAUNCH_JSON" ] && [ -f "$DEEP_RESULTS" ]; then
                            # tdeep ran and wrote results — advance to step 3 for launch
                            echo "  → launch_commands.json + deep_analysis_results.md found. Advancing to launch check."
                            CYCLE_NUM=$((CYCLE_NUM + 1))
                            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['cycle'] = $CYCLE_NUM; s['next_step'] = 3; s['status'] = 'tdeep_complete'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                            prepend_log "| $PST_TS | timer-dev | — | tdevauto complete (tdeep ran) → launch check |"
                            t_dev_log "AUTO completed: tdeep ran. Advancing to step 3 for launch."
                            IDLE_LOOP=true

                        elif [ -f "$LAUNCH_JSON" ]; then
                            # tdev wrote launch_commands.json but tdeep hasn't run yet
                            # tdevauto should have run tdeep — but deep_analysis_results.md missing
                            echo "  → launch_commands.json exists but no deep_analysis_results.md. Sending tdevauto again for tdeep."
                            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 2; s['status'] = 'tdev_complete'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                            prepend_log "| $PST_TS | timer-dev | — | tdevauto: launch_commands.json found, no tdeep yet → re-send |"
                            t_dev_log "AUTO: launch_commands exists but no deep results. Re-sending tdevauto."
                            # Let next tick handle it (no IDLE_LOOP — wait for next interval)

                        else
                            # No launch_commands.json — tdev found no work or tconv ran only
                            echo "  → No launch_commands.json. Cycle complete → tconv next."
                            CYCLE_NUM=$((CYCLE_NUM + 1))
                            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['cycle'] = $CYCLE_NUM; s['next_step'] = 1; s['status'] = 'no_launch'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                            prepend_log "| $PST_TS | timer-dev | — | tdevauto complete → no launch, tconv next |"
                            t_dev_log "AUTO completed: no launch_commands. Cycle done, next_step=1."
                        fi
                    fi
                fi

            else
                # LEGACY_MODE: per-step two-phase sends
                HCONV_SENT="$DATA_DIR/t2_tconv_sent_${INSTANCE_ID}.txt"
                HDEV_SENT="$DATA_DIR/t2_tdev_sent_${INSTANCE_ID}.txt"

                if [ "$NEXT_STEP" = "1" ]; then
                    if [ ! -f "$HCONV_SENT" ]; then
                        echo "  → [LEGACY] Sending /tconv"
                        send_dev_cmd "tconv" "step 1"
                        printf '%s /tconv' "$(date +%s)" > "$HCONV_SENT"
                        prepend_log "| $PST_TS | timer-dev | — | [LEGACY] Sent /tconv |"
                        t_dev_log "LEGACY PHASE_1 step 1: sent /tconv"
                    else
                        FLAG_TS=$(awk '{print $1}' "$HCONV_SENT" 2>/dev/null || echo "0")
                        NOW_EPOCH=$(date +%s)
                        PHASE_ELAPSED=$((NOW_EPOCH - FLAG_TS))
                        if [ "$PHASE_ELAPSED" -gt 1200 ]; then
                            echo "  *** WATCHDOG: tconv stuck $(($PHASE_ELAPSED / 60))m. Resetting."
                            rm -f "$HCONV_SENT"
                            bash "$SEND_SCRIPT" "$DEV_ALIAS" "/clear"
                            sleep 0.5; bash "$SEND_SCRIPT" "$DEV_ALIAS" Enter; sleep 3
                            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'watchdog_reset'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                            prepend_log "| $PST_TS | timer-dev | — | WATCHDOG: tconv stuck $(($PHASE_ELAPSED / 60))m. Reset. |"
                            t_dev_log "WATCHDOG_RESET phase_elapsed=${PHASE_ELAPSED}s step=1_tconv"
                            IDLE_LOOP=true
                        else
                            rm -f "$HCONV_SENT"
                            CYCLE_NUM=$((CYCLE_NUM + 1))
                            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['cycle'] = $CYCLE_NUM; s['current_step'] = 1; s['next_step'] = 2; s['status'] = 'tconv_complete'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                            prepend_log "| $PST_TS | timer-dev | — | [LEGACY] tconv complete → tdev |"
                            t_dev_log "LEGACY PHASE_2 step 1: completed, advancing to step 2"
                            IDLE_LOOP=true
                        fi
                    fi

                elif [ "$NEXT_STEP" = "2" ]; then
                    if [ ! -f "$HDEV_SENT" ]; then
                        echo "  → [LEGACY] Sending /tdev"
                        send_dev_cmd "tdev" "step 2"
                        printf '%s /tdev' "$(date +%s)" > "$HDEV_SENT"
                        prepend_log "| $PST_TS | timer-dev | — | [LEGACY] Sent /tdev |"
                        t_dev_log "LEGACY PHASE_1 step 2: sent /tdev"
                    else
                        FLAG_TS=$(awk '{print $1}' "$HDEV_SENT" 2>/dev/null || echo "0")
                        NOW_EPOCH=$(date +%s)
                        PHASE_ELAPSED=$((NOW_EPOCH - FLAG_TS))
                        if [ "$PHASE_ELAPSED" -gt 1200 ]; then
                            echo "  *** WATCHDOG: tdev stuck $(($PHASE_ELAPSED / 60))m. Resetting."
                            rm -f "$HDEV_SENT"
                            bash "$SEND_SCRIPT" "$DEV_ALIAS" "/clear"
                            sleep 0.5; bash "$SEND_SCRIPT" "$DEV_ALIAS" Enter; sleep 3
                            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'watchdog_reset'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                            prepend_log "| $PST_TS | timer-dev | — | WATCHDOG: tdev stuck $(($PHASE_ELAPSED / 60))m. Reset. |"
                            t_dev_log "WATCHDOG_RESET phase_elapsed=${PHASE_ELAPSED}s step=2_tdev"
                            IDLE_LOOP=true
                        else
                            rm -f "$HDEV_SENT"
                            # Rogue process check
                            ROGUE_PID=$(ps -eo pid,stat,args 2>/dev/null | grep python | grep -v grep | grep -v vscode | grep -v '^.*Z' | grep -E 'firstrate_|trade_|experiments' | awk '{print $1}' | head -1)
                            if [ -n "$ROGUE_PID" ]; then
                                echo "  *** WARNING: Rogue process $ROGUE_PID found. Entering monitoring."
                                echo "$ROGUE_PID" > "$DATA_DIR/t2_launched_pid_${INSTANCE_ID}.txt"
                                python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['current_step'] = 2; s['next_step'] = 1; s['status'] = 'rogue_launch_detected'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                                rm -f "$DATA_DIR/t2_eta_ts_${INSTANCE_ID}.txt"
                                prepend_log "| $PST_TS | timer-dev | — | ROGUE LAUNCH: PID $ROGUE_PID → monitoring |"
                                IDLE_LOOP=true
                            elif [ -f "$LAUNCH_JSON" ]; then
                                python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['current_step'] = 2; s['next_step'] = 3; s['status'] = 'tdev_complete'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                                prepend_log "| $PST_TS | timer-dev | — | [LEGACY] tdev complete → tdeep |"
                                t_dev_log "LEGACY PHASE_2 step 2: completed, advancing to step 3"
                                IDLE_LOOP=true
                            else
                                python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['current_step'] = 2; s['next_step'] = 1; s['status'] = 'no_launch'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
                                prepend_log "| $PST_TS | timer-dev | — | [LEGACY] tdev complete → tconv (no launch) |"
                                t_dev_log "LEGACY PHASE_2 step 2: completed, advancing to step 1 (no launch)"
                                IDLE_LOOP=true
                            fi
                        fi
                    fi
                fi
            fi

        else
            echo "  → Unknown step $NEXT_STEP. Resetting to tconv."
            python3 -c "
import json, os
with open('$STATE_FILE') as f: s = json.load(f)
s['next_step'] = 1; s['status'] = 'reset'
tmp = '$STATE_FILE' + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f)
os.replace(tmp, '$STATE_FILE')
" 2>/dev/null
        fi
        done  # end IDLE_LOOP
        fi  # end else (no live processes)
    fi

    # ===================================================================
    # PHASE 9: CLEANUP old snapshots
    # ===================================================================
    ls -t "$DATA_DIR"/dev_s*.txt 2>/dev/null | tail -n +10 | xargs rm -f 2>/dev/null

    # ===================================================================
    # PHASE 10: WAIT with s-to-skip, p-to-pause
    # ===================================================================
    for ((remaining=INTERVAL_SECONDS; remaining>0; remaining--)); do
        if [ "$PAUSED" = true ]; then
            printf "\r  PAUSED  ('r' resume, 's' skip once)  "
            KEYPRESS=""
            read_keypress 1
            if [ "$KEYPRESS" = "r" ] || [ "$KEYPRESS" = "R" ]; then
                PAUSED=false; printf "\r  Resumed                      \n"
            elif [ "$KEYPRESS" = "s" ] || [ "$KEYPRESS" = "S" ]; then
                PAUSED=false; printf "\r  Skipped (still paused next tick)\n"; break
            fi
            continue
        fi
        printf "\r  Next: %02d:%02d  ('s' skip | 'p' pause)  " $((remaining / 60)) $((remaining % 60))
        KEYPRESS=""
        read_keypress 1
        if [ "$KEYPRESS" = "s" ] || [ "$KEYPRESS" = "S" ]; then
            printf "\r  Skipped                              \n"; break
        elif [ "$KEYPRESS" = "p" ] || [ "$KEYPRESS" = "P" ]; then
            PAUSED=true; printf "\r  Paused. ('r' resume, 's' skip once) \n"
        fi
    done
    echo ""
    echo "----------------------------------------"
    ((ITERATION++))
done
