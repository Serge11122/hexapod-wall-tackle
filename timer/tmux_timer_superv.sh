#!/bin/bash
# Timer Supervisor — monitors timer cycle pipeline health
# Sends /t-superv every 10 minutes to Claude session t_{n}_superv (Sonnet).
# Checks both t_{n}_dev AND t_{n}_eta sessions are alive.
#
# Usage: ./tmux_timer_superv.sh <instance_id> [interval]
#        ./tmux_timer_superv.sh <instance_id> --stop
#        ./tmux_timer_superv.sh <instance_id> --view

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TIMER_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_INTERVAL_SECONDS=600  # 10 minutes
INSIDE_TMUX=false
INSTANCE_ID=""
DATA_DIR="$TIMER_DIR/data"
SEND_SCRIPT="$TIMER_DIR/tmux_send_claude.sh"
RUN_SCRIPT="$TIMER_DIR/tmux_run_claude.sh"

# Model: Haiku, thinking disabled, effort low.
# Mechanical health checks — most superv runs complete inline without subagent.
# Spawns Sonnet subagent (no thinking) only for stuck-state diagnosis.
SUPERV_MODEL_FLAGS="--model claude-haiku-4-5 --thinking-off --effort low"

show_usage() {
    echo "Usage: ./tmux_timer_superv.sh <instance_id> [interval]"
    echo "       Interval: 10 (min), 600s (sec). Default: 10min."
    echo "       ./tmux_timer_superv.sh <instance_id> --stop|--view"
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

SUPERV_ALIAS="t_${INSTANCE_ID}_superv"
SUPERV_TIMER_SESSION="timer-superv-${INSTANCE_ID}"
INTERVAL_SECONDS=$DEFAULT_INTERVAL_SECONDS

case "$1" in
    --stop)
        if tmux has-session -t "$SUPERV_TIMER_SESSION" 2>/dev/null; then
            tmux kill-session -t "$SUPERV_TIMER_SESSION"; echo "Timer-superv stopped"
        else echo "Not running"; fi; exit 0 ;;
    --view)
        if ! tmux has-session -t "$SUPERV_TIMER_SESSION" 2>/dev/null; then echo "Not running"; exit 1; fi
        exec tmux attach-session -t "$SUPERV_TIMER_SESSION" ;;
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
    if tmux has-session -t "$SUPERV_TIMER_SESSION" 2>/dev/null; then
        tmux kill-session -t "$SUPERV_TIMER_SESSION"; sleep 1
    fi
    DISPLAY_MIN=$(echo "scale=1; $INTERVAL_SECONDS / 60" | bc)
    echo "Starting Timer-Superv | Instance: $INSTANCE_ID | Session: $SUPERV_ALIAS | Interval: ${DISPLAY_MIN}min"
    echo "View: ./tmux_timer_superv.sh $INSTANCE_ID --view"
    echo "Stop: ./tmux_timer_superv.sh $INSTANCE_ID --stop"
    mkdir -p "$DATA_DIR"
    tmux new-session -d -s "$SUPERV_TIMER_SESSION" "bash '$0' --inside-tmux $INSTANCE_ID ${INTERVAL_SECONDS}s"
    echo "Timer-superv started"; exit 0
fi

# ===== Inside tmux =====
DISPLAY_MIN=$(echo "scale=1; $INTERVAL_SECONDS / 60" | bc)
echo "Timer-Superv Started | Instance: $INSTANCE_ID | Superv session: $SUPERV_ALIAS | Interval: ${DISPLAY_MIN}min | 's' skip, 'p' pause"
echo "========================================"
trap 'echo ""; echo "Timer-superv stopped"; exit 0' INT

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

DEV_ALIAS="t_${INSTANCE_ID}_dev"
ETA_ALIAS="t_${INSTANCE_ID}_eta"

# Ensure supervisor Claude session exists
if ! tmux has-session -t "$SUPERV_ALIAS" 2>/dev/null; then
    echo "No supervisor session. Starting one (Haiku, no-thinking, effort low)..."
    bash "$RUN_SCRIPT" "$SUPERV_ALIAS" $SUPERV_MODEL_FLAGS
    sleep 10
fi

while true; do
    LOCAL_TS=$(date '+%Y-%m-%d %H:%M:%S')
    echo ""
    echo "[$LOCAL_TS] Supervisor Tick #$ITERATION"

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

    # Check session status
    DEV_ALIVE=false
    ETA_ALIVE=false
    tmux has-session -t "$DEV_ALIAS" 2>/dev/null && DEV_ALIVE=true
    tmux has-session -t "$ETA_ALIAS" 2>/dev/null && ETA_ALIVE=true
    echo "  Dev ($DEV_ALIAS): $([ "$DEV_ALIVE" = true ] && echo 'ALIVE' || echo 'DEAD')"
    echo "  ETA ($ETA_ALIAS): $([ "$ETA_ALIVE" = true ] && echo 'ALIVE' || echo 'DEAD')"

    # Ensure supervisor session exists
    if ! tmux has-session -t "$SUPERV_ALIAS" 2>/dev/null; then
        echo "  → Supervisor Claude session dead. Restarting..."
        bash "$RUN_SCRIPT" "$SUPERV_ALIAS" $SUPERV_MODEL_FLAGS
        sleep 10
    fi

    if tmux has-session -t "$SUPERV_ALIAS" 2>/dev/null; then
        # 2-snapshot IDLE check for supervisor session
        tmux capture-pane -t "$SUPERV_ALIAS" -p -S -40 > /tmp/superv_s1.txt 2>/dev/null
        sleep 5
        tmux capture-pane -t "$SUPERV_ALIAS" -p -S -40 > /tmp/superv_s2.txt 2>/dev/null
        DIFF=$(diff /tmp/superv_s1.txt /tmp/superv_s2.txt 2>/dev/null | wc -l)

        if [ "$DIFF" -eq 0 ]; then
            echo "  → Supervisor session IDLE. Sending /t-superv"
            bash "$SEND_SCRIPT" "$SUPERV_ALIAS" "/clear"
            sleep 0.5
            bash "$SEND_SCRIPT" "$SUPERV_ALIAS" Enter
            sleep 3
            bash "$SEND_SCRIPT" "$SUPERV_ALIAS" "/t-superv"
            sleep 0.5
            bash "$SEND_SCRIPT" "$SUPERV_ALIAS" Enter
            echo "  → Sent."
        else
            echo "  → Supervisor session ACTIVE. Skipping this tick."
        fi
    else
        echo "  → Could not start supervisor session. Will retry next tick."
    fi

    echo "----------------------------------------"

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
