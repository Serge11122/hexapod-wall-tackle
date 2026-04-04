#!/bin/bash
# Timer ETA — Process monitoring only (bash-only ticks while process alive)
# Calls /teta every 5 min while any project process is alive (etimes > 300).
# Auto-detects running processes — no state file dependency.
# Haiku model, thinking disabled, effort low.
#
# Usage: ./tmux_timer_eta.sh <instance_id> [interval]
#        ./tmux_timer_eta.sh <instance_id> --stop
#        ./tmux_timer_eta.sh <instance_id> --view
#
# Claude session: t_{n}_eta  (Haiku, no thinking, effort low — spawns Sonnet subagent on anomaly only)
# Coordination:
#   Reads:  timer/data/t2_launched_pid_{n}.txt  (primary PID to monitor, written by this script)
#   Writes: timer/data/t2_launched_pid_{n}.txt  (on auto-detect of new process)
#           .manager/kill_violations.md         (via /teta Claude — kill switch for timer-dev)
# No state file dependency. Process liveness is detected directly via ps each tick.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TIMER_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_INTERVAL_SECONDS=30
INSIDE_TMUX=false
INSTANCE_ID=""
DATA_DIR="$TIMER_DIR/data"
SEND_SCRIPT="$TIMER_DIR/tmux_send_claude.sh"
RUN_SCRIPT="$TIMER_DIR/tmux_run_claude.sh"
ETA_LOG="$SCRIPT_DIR/.manager/timer_eta.log"
# Minimum elapsed seconds for a process to be considered a real training run (not a unit test)
MIN_PROC_ETIMES=300

# Model: Haiku, thinking disabled, effort low.
# Mechanical monitoring — most teta runs complete inline without subagent.
# Spawns Sonnet subagent (no thinking) only for anomaly investigation.
ETA_MODEL_FLAGS="--model claude-haiku-4-5 --thinking-off --effort low"

t_eta_log() {
    local PST_TS=$(TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M:%S PT')
    echo "[$PST_TS] $*" >> "$ETA_LOG"
}

show_usage() {
    echo "Usage: ./tmux_timer_eta.sh <instance_id> [interval]"
    echo "       Interval: 0.5 (min), 2 (min), 90s (sec). Default: 0.5min (30s)."
    echo "       ./tmux_timer_eta.sh <instance_id> --stop|--view"
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

ETA_ALIAS="t_${INSTANCE_ID}_eta"
ETA_TIMER_SESSION="timer-eta-${INSTANCE_ID}"
INTERVAL_SECONDS=$DEFAULT_INTERVAL_SECONDS

case "$1" in
    --stop)
        if tmux has-session -t "$ETA_TIMER_SESSION" 2>/dev/null; then
            tmux kill-session -t "$ETA_TIMER_SESSION"; echo "Timer-eta stopped"
        else echo "Not running"; fi; exit 0 ;;
    --view)
        if ! tmux has-session -t "$ETA_TIMER_SESSION" 2>/dev/null; then echo "Not running"; exit 1; fi
        exec tmux attach-session -t "$ETA_TIMER_SESSION" ;;
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
    if tmux has-session -t "$ETA_TIMER_SESSION" 2>/dev/null; then
        tmux kill-session -t "$ETA_TIMER_SESSION"; sleep 1
    fi
    DISPLAY_MIN=$(echo "scale=1; $INTERVAL_SECONDS / 60" | bc)
    echo "Starting Timer-ETA | Instance: $INSTANCE_ID | Session: $ETA_ALIAS | Interval: ${DISPLAY_MIN}min"
    echo "View: ./tmux_timer_eta.sh $INSTANCE_ID --view"
    echo "Stop: ./tmux_timer_eta.sh $INSTANCE_ID --stop"
    mkdir -p "$DATA_DIR"
    tmux new-session -d -s "$ETA_TIMER_SESSION" "bash '$0' --inside-tmux $INSTANCE_ID ${INTERVAL_SECONDS}s"
    echo "Timer-eta started"; exit 0
fi

# ===== Inside tmux =====

DISPLAY_MIN=$(echo "scale=1; $INTERVAL_SECONDS / 60" | bc)
echo "Timer-ETA Started | Instance: $INSTANCE_ID | ETA session: $ETA_ALIAS | Interval: ${DISPLAY_MIN}min | 's' skip, 'p' pause"
echo "========================================"
trap 'echo ""; echo "Timer-eta stopped"; exit 0' INT

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
        local DRAIN=""
        while IFS= read -t 0.05 -r -n 1 DRAIN 2>/dev/null; do :; done
        KEYPRESS=""
    else
        KEYPRESS="$BYTE"
    fi
}

while true; do
    LOCAL_TS=$(date '+%Y-%m-%d %H:%M:%S')
    PST_TS=$(TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M PT')
    echo ""
    echo "[$LOCAL_TS] ETA Tick #$ITERATION"

    if [ "$PAUSED" = true ]; then
        echo "  PAUSED — skipping tick ('r' resume, 's' skip once)"
        for ((remaining=INTERVAL_SECONDS; remaining>0; remaining--)); do
            printf "\r  PAUSED  ('r' resume, 's' skip once)  "
            KEYPRESS=""
            read_keypress 1
            if [ "$KEYPRESS" = "r" ] || [ "$KEYPRESS" = "R" ]; then
                PAUSED=false; printf "\r  Resumed                      \n"; break
            elif [ "$KEYPRESS" = "s" ] || [ "$KEYPRESS" = "S" ]; then
                printf "\r  Skipped\n"; break
            fi
        done
        ((ITERATION++))
        continue
    fi

    # ===================================================================
    # AUTO-DETECT: scan for live project processes (etimes > MIN_PROC_ETIMES, not zombie)
    # No state file dependency — process liveness is the only gate.
    # ===================================================================
    TRACKED_PID_FILE="$DATA_DIR/t2_launched_pid_${INSTANCE_ID}.txt"
    TRACKED_PID=$(cat "$TRACKED_PID_FILE" 2>/dev/null)
    ETA_TS_FILE="$DATA_DIR/t2_eta_ts_${INSTANCE_ID}.txt"
    KILL_SWITCH="$SCRIPT_DIR/.manager/kill_violations.md"

    # Scan for live project processes older than MIN_PROC_ETIMES seconds
    LIVE_PIDS=$(ps -eo pid,stat,etimes,args 2>/dev/null \
        | grep python | grep -v grep | grep -v vscode \
        | grep -E 'firstrate_|trade_|experiments' \
        | awk -v min="$MIN_PROC_ETIMES" '$2 !~ /^Z/ && $3 >= min {print $1}')

    if [ -z "$LIVE_PIDS" ]; then
        # No qualifying live processes — standby
        echo "  → No live project processes (>${MIN_PROC_ETIMES}s). Standby."
        # Clean up tracked PID file if process is gone
        if [ -n "$TRACKED_PID" ]; then
            rm -f "$TRACKED_PID_FILE"
            t_eta_log "STANDBY | tracked PID $TRACKED_PID gone, cleared"
        else
            t_eta_log "STANDBY | no project processes"
        fi
    else
        # Live processes found — ETA monitoring mode
        # If no tracked PID yet (or tracked PID gone), pick the longest-running process
        TRACKED_PID_ALIVE=false
        if [ -n "$TRACKED_PID" ]; then
            for P in $LIVE_PIDS; do
                if [ "$P" = "$TRACKED_PID" ]; then TRACKED_PID_ALIVE=true; break; fi
            done
        fi

        if [ "$TRACKED_PID_ALIVE" = false ]; then
            # Pick the process with the longest elapsed time as primary
            NEW_PID=$(ps -eo pid,stat,etimes,args 2>/dev/null \
                | grep python | grep -v grep | grep -v vscode \
                | grep -E 'firstrate_|trade_|experiments' \
                | awk -v min="$MIN_PROC_ETIMES" '$2 !~ /^Z/ && $3 >= min {print $3, $1}' \
                | sort -rn | awk 'NR==1{print $2}')
            if [ -n "$NEW_PID" ] && [ "$NEW_PID" != "$TRACKED_PID" ]; then
                echo "  → Auto-detected process PID $NEW_PID. Writing to tracked PID file."
                echo "$NEW_PID" > "$TRACKED_PID_FILE"
                TRACKED_PID="$NEW_PID"
                rm -f "$ETA_TS_FILE"  # reset 5-min timer on new detection
                t_eta_log "AUTO_DETECT PID=$NEW_PID"
            fi
        fi

        # Report all live PIDs
        LIVE_COUNT=$(echo "$LIVE_PIDS" | wc -w)
        LIVE_ELAPSED=$(ps -p "$TRACKED_PID" -o etime= 2>/dev/null | xargs)
        LIVE_RSS=$(ps -p "$TRACKED_PID" -o rss= 2>/dev/null | awk '{printf "%.1f", $1/1024/1024}')
        echo "  → ETA mode: $LIVE_COUNT project process(es) alive. Primary PID $TRACKED_PID (${LIVE_ELAPSED}, ${LIVE_RSS}GB)."

        if [ -f "$KILL_SWITCH" ]; then
            echo "  → Kill switch exists. Timer-dev will handle kill. Waiting."
            t_eta_log "KILL_SWITCH exists, waiting for timer-dev to act"
        else
            # Decide whether to send /teta (every 5 min)
            SEND_HETA=false
            LAST_ETA=$(cat "$ETA_TS_FILE" 2>/dev/null || echo "0")
            NOW_EPOCH=$(date +%s)
            SINCE=$((NOW_EPOCH - LAST_ETA))
            if [ "$SINCE" -ge 300 ]; then
                SEND_HETA=true
            else
                UNTIL=$((300 - SINCE))
                echo "  → /teta in ${UNTIL}s."
            fi

            if [ "$SEND_HETA" = true ]; then
                # Ensure ETA Claude session exists
                if ! tmux has-session -t "$ETA_ALIAS" 2>/dev/null; then
                    echo "  → Starting ETA Claude session (Haiku, no-thinking, effort low)..."
                    bash "$RUN_SCRIPT" "$ETA_ALIAS" $ETA_MODEL_FLAGS
                    sleep 10
                fi

                # Check ETA session is IDLE before sending
                ETA_SESSION_ACTIVE=false
                tmux capture-pane -t "$ETA_ALIAS" -p -S -20 > /tmp/eta_check_s1.txt 2>/dev/null
                sleep 5
                tmux capture-pane -t "$ETA_ALIAS" -p -S -20 > /tmp/eta_check_s2.txt 2>/dev/null
                ETA_DIFF=$(diff /tmp/eta_check_s1.txt /tmp/eta_check_s2.txt 2>/dev/null | wc -l)
                if [ "$ETA_DIFF" -gt 0 ]; then
                    ETA_SESSION_ACTIVE=true
                fi

                if [ "$ETA_SESSION_ACTIVE" = true ]; then
                    echo "  → ETA session active (still processing). Waiting."
                else
                    echo "$(date +%s)" > "$ETA_TS_FILE"
                    echo "  → Sending /teta to $ETA_ALIAS"
                    bash "$SEND_SCRIPT" "$ETA_ALIAS" "/clear"
                    sleep 0.5
                    bash "$SEND_SCRIPT" "$ETA_ALIAS" Enter
                    sleep 3
                    bash "$SEND_SCRIPT" "$ETA_ALIAS" "/teta"
                    sleep 0.5
                    bash "$SEND_SCRIPT" "$ETA_ALIAS" Enter
                    t_eta_log "SENT /teta | primary_pid=$TRACKED_PID | live_pids=$LIVE_COUNT"
                fi
            fi
        fi
    fi

    echo "----------------------------------------"

    # ===================================================================
    # WAIT with s-to-skip, p-to-pause
    # ===================================================================
    for ((remaining=INTERVAL_SECONDS; remaining>0; remaining--)); do
        if [ "$PAUSED" = true ]; then
            printf "\r  PAUSED  ('r' resume, 's' skip once)  "
            KEYPRESS=""
            read_keypress 1
            if [ "$KEYPRESS" = "r" ] || [ "$KEYPRESS" = "R" ]; then
                PAUSED=false; printf "\r  Resumed                      \n"
            elif [ "$KEYPRESS" = "s" ] || [ "$KEYPRESS" = "S" ]; then
                PAUSED=false; printf "\r  Skipped\n"; break
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
    ((ITERATION++))
done
