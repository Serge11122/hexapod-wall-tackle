#!/bin/bash
# Timer Design — idle-nudge process with rotating prompts.
#
# Watches the design Claude tmux session. If the pane content is unchanged across
# three captures (idle), sends the next prompt from the rotating list. If the
# session doesn't exist, starts one. Nothing else.
#
# Usage: ./tmux_timer_design.sh <instance_id> [interval]
#        ./tmux_timer_design.sh <instance_id> --stop
#        ./tmux_timer_design.sh <instance_id> --view
#        ./tmux_timer_design.sh <instance_id> --status

TIMER_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_INTERVAL_SECONDS=30
INSIDE_TMUX=false
INSTANCE_ID=""
SEND_SCRIPT="$TIMER_DIR/tmux_send_claude.sh"
RUN_SCRIPT="$TIMER_DIR/tmux_run_claude.sh"

# Rotating prompts — index advances on each successful nudge.
# This is a DESIGN session: static code analysis and implementation only. No code execution of any kind.
PROMPTS=(
    'static code analysis only — do not run anything.
    what is the expected performance of this implementation? is there any more performance we can gain from any additional data or approaches used before in any of the previous implementations that were successful architectures but did not get ported into the current implementation? analyze, discuss, dont change code.
If gaps were found: write 0 to timer/design_no_gap_counter.md (single line, just the number).
If no gaps were found: read the current counter from timer/design_no_gap_counter.md (default 0 if missing), increment by 1, write the new value back. If the counter reaches 5, output a snooze marker for 30 minutes: TMUX_TIMER_SNOOZE_30:no-gap@$(date +%s)'

    'static code edits only.
    yes. implement the high and medium priority gap fixes.
implement the additional gaps and features you identified.
if the cache is affected, stop and rebuild with the updates. and update the training recipe to fix the gaps.
do not block anything to be implemented because its too complex or too difficult. do whatever it takes to implement the recommended high and medium priority gap fixes, including data fixes and rebuilts and code refactors needed.
DO NOT run anything. DO NOT execute any scripts, tests, commands, or shell calls of any kind. No unit tests, no smoke tests, no cache builds, no python invocations. Only edit code files.'

    'static code analysis only — do not run anything.
    what is the expected performance of this implementation? is there any more performance we can gain or gaps in the performance or data or training? analyze, discuss, dont change code.
If gaps were found: write 0 to timer/design_no_gap_counter.md (single line, just the number).
If no gaps were found: read the current counter from timer/design_no_gap_counter.md (default 0 if missing), increment by 1, write the new value back. If the counter reaches 5, output a snooze marker for 30 minutes: TMUX_TIMER_SNOOZE_30:no-gap@$(date +%s)'

    'static code edits only.
    yes. implement the high and medium priority gap fixes.
implement the additional gaps and features you identified.
if the cache is affected, stop and rebuild with the updates. and update the training recipe to fix the gaps.
do not block anything to be implemented because its too complex or too difficult. do whatever it takes to implement the recommended high and medium priority gap fixes, including data fixes and rebuilts and code refactors needed.
DO NOT run anything. DO NOT execute any scripts, tests, commands, or shell calls of any kind. No unit tests, no smoke tests, no cache builds, no python invocations. Only edit code files.'
)
NUM_PROMPTS=${#PROMPTS[@]}
PROMPT_INDEX_FILE=""  # set after INSTANCE_ID is known

show_usage() {
    echo "Usage: ./tmux_timer_design.sh <instance_id> [interval]"
    echo "       Interval: 0.5 (min), 2 (min), 90s (sec). Default: 0.5min (30s)."
    echo "       Plain numbers are MINUTES. Use 's' suffix for seconds."
    echo "       ./tmux_timer_design.sh <instance_id> --stop|--view|--status"
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

DESIGN_ALIAS="t_${INSTANCE_ID}_design"
DESIGN_TIMER_SESSION="timer-design-${INSTANCE_ID}"
PROMPT_INDEX_FILE="/tmp/timer-design-${INSTANCE_ID}.prompt_index"
SNOOZE_CLEAR_FILE="/tmp/timer-design-${INSTANCE_ID}.cleared_snooze_ts"
INTERVAL_SECONDS=$DEFAULT_INTERVAL_SECONDS

case "$1" in
    --stop)
        if tmux has-session -t "$DESIGN_TIMER_SESSION" 2>/dev/null; then
            tmux kill-session -t "$DESIGN_TIMER_SESSION"; echo "Timer-design stopped"
        else echo "Not running"; fi; exit 0 ;;
    --view)
        if ! tmux has-session -t "$DESIGN_TIMER_SESSION" 2>/dev/null; then echo "Not running"; exit 1; fi
        exec tmux attach-session -t "$DESIGN_TIMER_SESSION" ;;
    --status)
        if tmux has-session -t "$DESIGN_TIMER_SESSION" 2>/dev/null; then
            echo "Timer-design: RUNNING (timer session: $DESIGN_TIMER_SESSION)"
            echo "Design Claude session: $DESIGN_ALIAS"
            tmux has-session -t "$DESIGN_ALIAS" 2>/dev/null && echo "  Claude session ALIVE" || echo "  Claude session DEAD"
            IDX=0
            [ -f "$PROMPT_INDEX_FILE" ] && IDX=$(cat "$PROMPT_INDEX_FILE" 2>/dev/null || echo 0)
            echo "  Next prompt index: $IDX / $((NUM_PROMPTS - 1))"
        else echo "Timer-design: NOT RUNNING"; fi; exit 0 ;;
    [0-9]*|0.*)
        ARG="$1"; shift
        if echo "$ARG" | grep -q 's$'; then
            INTERVAL_SECONDS=$(echo "$ARG" | sed 's/s$//')
        else
            MINUTES=$(echo "$ARG" | sed 's/m$//')
            INTERVAL_SECONDS=$(awk -v m="$MINUTES" 'BEGIN{printf "%d", m*60}')
        fi ;;
esac

if [ "$INSIDE_TMUX" = false ]; then
    if tmux has-session -t "$DESIGN_TIMER_SESSION" 2>/dev/null; then
        tmux kill-session -t "$DESIGN_TIMER_SESSION"; sleep 1
    fi
    # Reset prompt index on (re)start
    echo 0 > "$PROMPT_INDEX_FILE"
    DISPLAY_MIN=$(awk -v s="$INTERVAL_SECONDS" 'BEGIN{printf "%.1f", s/60}')
    echo "Starting Timer-Design | Instance: $INSTANCE_ID | Session: $DESIGN_ALIAS | Interval: ${DISPLAY_MIN}min"
    echo "View: ./tmux_timer_design.sh $INSTANCE_ID --view"
    echo "Stop: ./tmux_timer_design.sh $INSTANCE_ID --stop"
    tmux new-session -d -s "$DESIGN_TIMER_SESSION" "bash '$0' --inside-tmux $INSTANCE_ID ${INTERVAL_SECONDS}s"
    echo "Timer-design started"; exit 0
fi

# ===== Inside tmux =====

DISPLAY_MIN=$(awk -v s="$INTERVAL_SECONDS" 'BEGIN{printf "%.1f", s/60}')
echo "Timer-Design Started | Instance: $INSTANCE_ID | Design session: $DESIGN_ALIAS | Interval: ${DISPLAY_MIN}min | 's' skip, 'p' pause, 'c' clear-snooze"
echo "========================================"
trap 'echo ""; echo "Timer-design stopped"; exit 0' INT

PAUSED=true

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
    echo ""
    echo "[$LOCAL_TS] Tick"

    if [ "$PAUSED" = true ]; then
        echo "  PAUSED"
    elif ! tmux has-session -t "$DESIGN_ALIAS" 2>/dev/null; then
        echo "  → No design session. Starting one."
        bash "$RUN_SCRIPT" "$DESIGN_ALIAS"
    else
        # Snooze check: model prints TMUX_TIMER_SNOOZE_<N_MINUTES>[:<tag>]@<unix_ts>
        # when there are no gaps to fix (e.g. :no-gap tag). Position-based selection —
        # latest marker in scrollback wins; future-dated @ts are excluded.
        SNOOZE_CAP_DEFAULT=15
        SNOOZE_CAP_EXTENDED=60
        SNOOZE_CAP_NO_GAP=30
        CLEARED_TS=0
        [ -f "$SNOOZE_CLEAR_FILE" ] && CLEARED_TS=$(cat "$SNOOZE_CLEAR_FILE" 2>/dev/null || echo 0)
        NOW=$(date +%s)
        SNOOZE_LINE=$(tmux capture-pane -t "$DESIGN_ALIAS" -p -S -500 2>/dev/null \
            | grep -oE "TMUX_TIMER_SNOOZE_[0-9]+(:(stall|halt|caller-await|no-gap))?@[0-9]+" \
            | awk -v c="$CLEARED_TS" -v n="$NOW" -F@ '$2 > c && $2 <= n' \
            | tail -1)
        SNOOZED=false
        if [ -n "$SNOOZE_LINE" ]; then
            SNOOZE_MIN=$(echo "$SNOOZE_LINE" | grep -oE "SNOOZE_[0-9]+" | grep -oE "[0-9]+")
            SNOOZE_TAG=$(echo "$SNOOZE_LINE" | grep -oE ":(stall|halt|caller-await|no-gap)" | tr -d :)
            SNOOZE_TS=$(echo "$SNOOZE_LINE" | grep -oE "@[0-9]+" | tr -d @)
            if [ "$SNOOZE_TAG" = "no-gap" ]; then
                CAP=$SNOOZE_CAP_NO_GAP
            elif [ "$SNOOZE_TAG" = "stall" ] || [ "$SNOOZE_TAG" = "halt" ]; then
                CAP=$SNOOZE_CAP_EXTENDED
            else
                CAP=$SNOOZE_CAP_DEFAULT
            fi
            if [ "$SNOOZE_MIN" -gt 200 ]; then
                echo "  → SUSPICIOUS_SNOOZE: SNOOZE_MIN=${SNOOZE_MIN} looks like seconds, not minutes — likely unit-confusion bug. Clamping per cap=${CAP}."
            fi
            [ "$SNOOZE_MIN" -gt "$CAP" ] && SNOOZE_MIN=$CAP
            ELAPSED=$((NOW - SNOOZE_TS))
            REMAINING=$((SNOOZE_MIN * 60 - ELAPSED))
            if [ "$REMAINING" -gt 0 ]; then
                SNOOZED=true
                TAG_DISPLAY="${SNOOZE_TAG:+ :$SNOOZE_TAG}"
                echo "  → SNOOZED ${SNOOZE_MIN}min${TAG_DISPLAY} (cap ${CAP}), ${REMAINING}s remaining (marker ts $SNOOZE_TS)."
            fi
        fi

        if [ "$SNOOZED" = true ]; then
            :  # skip idle detection and nudge this tick
        else
            SNAP1=$(tmux capture-pane -t "$DESIGN_ALIAS" -p -S -80 2>/dev/null)
            sleep 8
            SNAP2=$(tmux capture-pane -t "$DESIGN_ALIAS" -p -S -80 2>/dev/null)
            sleep 8
            SNAP3=$(tmux capture-pane -t "$DESIGN_ALIAS" -p -S -80 2>/dev/null)

            if [ "$SNAP1" = "$SNAP2" ] && [ "$SNAP2" = "$SNAP3" ]; then
                # Read current index
                IDX=0
                if [ -f "$PROMPT_INDEX_FILE" ]; then
                    IDX=$(cat "$PROMPT_INDEX_FILE" 2>/dev/null || echo 0)
                    IDX=$((IDX % NUM_PROMPTS))
                fi
                PROMPT="${PROMPTS[$IDX]}"
                NEXT_IDX=$(( (IDX + 1) % NUM_PROMPTS ))

                echo "  → IDLE. Nudging with prompt $IDX."
                tmux send-keys -t "$DESIGN_ALIAS" -l "$PROMPT"
                sleep 0.1
                tmux send-keys -t "$DESIGN_ALIAS" Enter

                echo "$NEXT_IDX" > "$PROMPT_INDEX_FILE"
                echo "  → Prompt index advanced to $NEXT_IDX."
            else
                echo "  → ACTIVE."
            fi
        fi
    fi

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
        printf "\r  Next: %02d:%02d  ('s' skip | 'p' pause | 'c' clear-snooze)  " $((remaining / 60)) $((remaining % 60))
        KEYPRESS=""
        read_keypress 1
        if [ "$KEYPRESS" = "s" ] || [ "$KEYPRESS" = "S" ]; then
            printf "\r  Skipped                                              \n"; break
        elif [ "$KEYPRESS" = "p" ] || [ "$KEYPRESS" = "P" ]; then
            PAUSED=true; printf "\r  Paused. ('r' resume, 's' skip once)                  \n"
        elif [ "$KEYPRESS" = "c" ] || [ "$KEYPRESS" = "C" ]; then
            CLEAR_NOW=$(date +%s)
            LATEST_TS=$(tmux capture-pane -t "$DESIGN_ALIAS" -p -S -500 2>/dev/null \
                | grep -oE "TMUX_TIMER_SNOOZE_[0-9]+(:(stall|halt|no-gap))?@[0-9]+" \
                | awk -v n="$CLEAR_NOW" -F@ '$2 <= n' \
                | tail -1 | grep -oE "@[0-9]+" | tr -d @)
            if [ -n "$LATEST_TS" ]; then
                echo "$LATEST_TS" > "$SNOOZE_CLEAR_FILE"
                printf "\r  Cleared snooze markers up to @%s                    \n" "$LATEST_TS"
            else
                printf "\r  No snooze markers in pane to clear                  \n"
            fi
        fi
    done
    echo ""
    echo "----------------------------------------"
done
