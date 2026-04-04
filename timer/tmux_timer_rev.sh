#!/bin/bash
# Timer Reviewer — checks cycle log activity and goal velocity
# Sends /trev every 30 minutes to Claude session t_{n}_rev (Haiku).
#
# Usage: ./tmux_timer_rev.sh <instance_id> [interval]
#        ./tmux_timer_rev.sh <instance_id> --stop
#        ./tmux_timer_rev.sh <instance_id> --view

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TIMER_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_INTERVAL_SECONDS=1800  # 30 minutes
INSIDE_TMUX=false
INSTANCE_ID=""
DATA_DIR="$TIMER_DIR/data"
SEND_SCRIPT="$TIMER_DIR/tmux_send_claude.sh"
RUN_SCRIPT="$TIMER_DIR/tmux_run_claude.sh"

# Model: Haiku, thinking disabled, effort low.
# Lightweight goal velocity checks — spawns Sonnet (medium effort) subagent only when investigation needed.
REV_MODEL_FLAGS="--model claude-haiku-4-5 --thinking-off --effort low"

show_usage() {
    echo "Usage: ./tmux_timer_rev.sh <instance_id> [interval]"
    echo "       Interval: 30 (min), 1800s (sec). Default: 30min."
    echo "       ./tmux_timer_rev.sh <instance_id> --stop|--view"
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

REV_ALIAS="t_${INSTANCE_ID}_rev"
REV_TIMER_SESSION="timer-rev-${INSTANCE_ID}"
INTERVAL_SECONDS=$DEFAULT_INTERVAL_SECONDS

case "$1" in
    --stop)
        if tmux has-session -t "$REV_TIMER_SESSION" 2>/dev/null; then
            tmux kill-session -t "$REV_TIMER_SESSION"; echo "Timer-rev stopped"
        else echo "Not running"; fi; exit 0 ;;
    --view)
        if ! tmux has-session -t "$REV_TIMER_SESSION" 2>/dev/null; then echo "Not running"; exit 1; fi
        exec tmux attach-session -t "$REV_TIMER_SESSION" ;;
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
    if tmux has-session -t "$REV_TIMER_SESSION" 2>/dev/null; then
        tmux kill-session -t "$REV_TIMER_SESSION"; sleep 1
    fi
    DISPLAY_MIN=$(echo "scale=1; $INTERVAL_SECONDS / 60" | bc)
    echo "Starting Timer-Rev | Instance: $INSTANCE_ID | Session: $REV_ALIAS | Interval: ${DISPLAY_MIN}min"
    echo "View: ./tmux_timer_rev.sh $INSTANCE_ID --view"
    echo "Stop: ./tmux_timer_rev.sh $INSTANCE_ID --stop"
    mkdir -p "$DATA_DIR"
    tmux new-session -d -s "$REV_TIMER_SESSION" "bash '$0' --inside-tmux $INSTANCE_ID ${INTERVAL_SECONDS}s"
    echo "Timer-rev started"; exit 0
fi

# ===== Inside tmux =====
DISPLAY_MIN=$(echo "scale=1; $INTERVAL_SECONDS / 60" | bc)
echo "Timer-Rev Started | Instance: $INSTANCE_ID | Rev session: $REV_ALIAS | Interval: ${DISPLAY_MIN}min | 's' skip, 'p' pause"
echo "========================================"
trap 'echo ""; echo "Timer-rev stopped"; exit 0' INT

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

# Ensure reviewer Claude session exists
if ! tmux has-session -t "$REV_ALIAS" 2>/dev/null; then
    echo "No reviewer session. Starting one (Haiku, no-thinking, effort low)..."
    bash "$RUN_SCRIPT" "$REV_ALIAS" $REV_MODEL_FLAGS
    sleep 10
fi

while true; do
    LOCAL_TS=$(date '+%Y-%m-%d %H:%M:%S')
    echo ""
    echo "[$LOCAL_TS] Reviewer Tick #$ITERATION"

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

    # Ensure reviewer session exists
    if ! tmux has-session -t "$REV_ALIAS" 2>/dev/null; then
        echo "  → Reviewer Claude session dead. Restarting..."
        bash "$RUN_SCRIPT" "$REV_ALIAS" $REV_MODEL_FLAGS
        sleep 10
    fi

    if tmux has-session -t "$REV_ALIAS" 2>/dev/null; then
        # 2-snapshot IDLE check for reviewer session
        tmux capture-pane -t "$REV_ALIAS" -p -S -40 > /tmp/rev_s1.txt 2>/dev/null
        sleep 5
        tmux capture-pane -t "$REV_ALIAS" -p -S -40 > /tmp/rev_s2.txt 2>/dev/null
        DIFF=$(diff /tmp/rev_s1.txt /tmp/rev_s2.txt 2>/dev/null | wc -l)

        if [ "$DIFF" -eq 0 ]; then
            echo "  → Reviewer session IDLE. Sending /trev"
            bash "$SEND_SCRIPT" "$REV_ALIAS" "/clear"
            sleep 0.5
            bash "$SEND_SCRIPT" "$REV_ALIAS" Enter
            sleep 3
            bash "$SEND_SCRIPT" "$REV_ALIAS" "/trev"
            sleep 0.5
            bash "$SEND_SCRIPT" "$REV_ALIAS" Enter
            echo "  → Sent."
        else
            echo "  → Reviewer session ACTIVE. Skipping this tick."
        fi
    else
        echo "  → Could not start reviewer session. Will retry next tick."
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
