#!/bin/bash
# Timer Dev — idle-nudge process.
#
# Watches the dev Claude tmux session. If the pane content is unchanged across
# three captures (idle), sends `/tdevauto`. If the session doesn't exist, starts
# one. Nothing else. /tdevauto owns all orchestration, launch, and logging.
#
# Usage: ./tmux_timer_dev.sh <instance_id> [interval]
#        ./tmux_timer_dev.sh <instance_id> --stop
#        ./tmux_timer_dev.sh <instance_id> --view
#        ./tmux_timer_dev.sh <instance_id> --status

TIMER_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_INTERVAL_SECONDS=30
INSIDE_TMUX=false
INSTANCE_ID=""
SEND_SCRIPT="$TIMER_DIR/tmux_send_claude.sh"
RUN_SCRIPT="$TIMER_DIR/tmux_run_claude.sh"

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
SNOOZE_CLEAR_FILE="/tmp/timer-dev-${INSTANCE_ID}.cleared_snooze_ts"
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
        else echo "Timer-dev: NOT RUNNING"; fi; exit 0 ;;
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
    if tmux has-session -t "$DEV_TIMER_SESSION" 2>/dev/null; then
        tmux kill-session -t "$DEV_TIMER_SESSION"; sleep 1
    fi
    DISPLAY_MIN=$(awk -v s="$INTERVAL_SECONDS" 'BEGIN{printf "%.1f", s/60}')
    echo "Starting Timer-Dev | Instance: $INSTANCE_ID | Session: $DEV_ALIAS | Interval: ${DISPLAY_MIN}min"
    echo "View: ./tmux_timer_dev.sh $INSTANCE_ID --view"
    echo "Stop: ./tmux_timer_dev.sh $INSTANCE_ID --stop"
    tmux new-session -d -s "$DEV_TIMER_SESSION" "bash '$0' --inside-tmux $INSTANCE_ID ${INTERVAL_SECONDS}s"
    echo "Timer-dev started"; exit 0
fi

# ===== Inside tmux =====

DISPLAY_MIN=$(awk -v s="$INTERVAL_SECONDS" 'BEGIN{printf "%.1f", s/60}')
echo "Timer-Dev Started | Instance: $INSTANCE_ID | Dev session: $DEV_ALIAS | Interval: ${DISPLAY_MIN}min | 's' skip, 'p' pause, 'c' clear-snooze"
echo "========================================"
trap 'echo ""; echo "Timer-dev stopped"; exit 0' INT

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
    echo ""
    echo "[$LOCAL_TS] Tick"

    if [ "$PAUSED" = true ]; then
        echo "  PAUSED"
    elif ! tmux has-session -t "$DEV_ALIAS" 2>/dev/null; then
        echo "  → No dev session. Starting one."
        bash "$RUN_SCRIPT" "$DEV_ALIAS"
    else
        # Permission-prompt auto-accept (narrow): only the "edit its own settings for
        # this session" prompt. Sends Enter to accept the default (option 1 = Yes),
        # then continues to the next tick. Skips snooze + idle checks for this tick.
        # Runs BEFORE snooze check so a snoozed session that hits this prompt is still
        # unblocked. Pattern is intentionally narrow — only this one prompt, no others.
        #
        # Detection has three layers (fixes scrollback-ghost bug 2026-04-28: option text
        # persisted in scrollback after the prompt was answered, causing every tick to
        # re-fire Enter for 8+ minutes while Claude was actively working):
        #   L1 — POSITION: option text must appear within the LAST 15 LINES of the pane
        #        (a live prompt's options sit immediately above the input row; an
        #        answered prompt's options have scrolled up).
        #   L2 — NEGATIVE EVIDENCE: between the option line and the bottom of the pane,
        #        there must be NO assistant-output glyphs (●, ⎿, ✻, "Cooked for",
        #        "tokens ·"). Those only render after Claude has continued past the
        #        prompt.
        #   L3 — SINGLE-SHOT GUARD: capture the option line's distance-from-bottom on
        #        fire to /tmp/timer-dev-N.last_settings_fired_pos. On next tick, if the
        #        position is unchanged AND ≤1 tick has elapsed, skip (Enter likely in
        #        flight). If unchanged for ≥2 ticks, RE-ARM and fire again — Enter must
        #        have failed to deliver. Position changes (new prompt, scroll) re-arm
        #        immediately.
        SETTINGS_FIRED_FILE="/tmp/timer-dev-${INSTANCE_ID}.last_settings_fired_pos"
        SETTINGS_OPT_TEXT="Yes, and allow Claude to edit its own settings for this session"
        PANE_TAIL=$(tmux capture-pane -t "$DEV_ALIAS" -p -S -30 2>/dev/null | tail -20)
        # L1: find option text in last 15 lines (within the last-20 capture, allow some
        # slack — input row + framing typically sits within ~7 lines below options).
        OPT_LINE_NO=$(echo "$PANE_TAIL" | tail -15 | grep -nF "$SETTINGS_OPT_TEXT" | tail -1 | cut -d: -f1)
        SETTINGS_LIVE=false
        if [ -n "$OPT_LINE_NO" ]; then
            # L2: no assistant-output glyphs below the option line.
            BELOW=$(echo "$PANE_TAIL" | tail -15 | tail -n +"$((OPT_LINE_NO + 1))")
            if ! echo "$BELOW" | grep -qE '●|⎿|✻|Cooked for|tokens ·'; then
                SETTINGS_LIVE=true
            fi
        fi
        if [ "$SETTINGS_LIVE" = true ]; then
            # L3: single-shot guard keyed on position (distance from bottom).
            POS_FROM_BOTTOM=$(( $(echo "$PANE_TAIL" | tail -15 | wc -l) - OPT_LINE_NO ))
            NOW_TS=$(date +%s)
            LAST_POS=""
            LAST_TS=0
            if [ -f "$SETTINGS_FIRED_FILE" ]; then
                LAST_POS=$(awk -F: 'NR==1{print $1}' "$SETTINGS_FIRED_FILE" 2>/dev/null)
                LAST_TS=$(awk -F: 'NR==1{print $2}' "$SETTINGS_FIRED_FILE" 2>/dev/null)
                [ -z "$LAST_TS" ] && LAST_TS=0
            fi
            AGE=$((NOW_TS - LAST_TS))
            if [ "$LAST_POS" = "$POS_FROM_BOTTOM" ] && [ "$AGE" -lt 60 ]; then
                echo "  → SETTINGS-PROMPT live but Enter recently sent (${AGE}s ago, same pos). Skipping."
            else
                if [ "$LAST_POS" = "$POS_FROM_BOTTOM" ]; then
                    echo "  → SETTINGS-PROMPT live, position unchanged ${AGE}s — re-arming, sending Enter."
                else
                    echo "  → SETTINGS-PROMPT detected (live, pos=$POS_FROM_BOTTOM). Sending Enter."
                fi
                bash "$SEND_SCRIPT" "$DEV_ALIAS" Enter
                echo "${POS_FROM_BOTTOM}:${NOW_TS}" > "$SETTINGS_FIRED_FILE"
            fi
            # Skip snooze/idle checks this tick; fall through to the countdown loop.
        else

        # Snooze check: skill prints TMUX_TIMER_SNOOZE_<N>[:<tag>]@<unix_ts> when
        # voluntarily exiting a TRAINING_LIVE_IDLE turn. Three-tier cap:
        #   - Untagged markers: 15-min default cap (rationalization-exit defense).
        #   - Tagged :stall or :halt: 60-min extended cap (classifier-declared long states).
        #   - Tagged :caller-await: 30-min cap (explicitly waiting on human input;
        #     short enough that misclassification costs little, long enough to suppress
        #     30s nudge spam during a typical caller-arrival window).
        # Selection is POSITION-BASED — the latest marker in scrollback wins. Earlier
        # @ts-based sort selection broke when a marker had a fabricated future-dated
        # @ts (panel evidence 2026-04-25): `sort -k2 -n | tail -1` picked the
        # future-dated marker as "newest" indefinitely until wall-clock caught up.
        # Position preserves chronological emit order and ignores @ts pathology.
        SNOOZE_CAP_DEFAULT=15
        SNOOZE_CAP_EXTENDED=60
        SNOOZE_CAP_CALLER_AWAIT=30
        CLEARED_TS=0
        [ -f "$SNOOZE_CLEAR_FILE" ] && CLEARED_TS=$(cat "$SNOOZE_CLEAR_FILE" 2>/dev/null || echo 0)
        NOW=$(date +%s)
        SNOOZE_LINE=$(tmux capture-pane -t "$DEV_ALIAS" -p -S -500 2>/dev/null \
            | grep -oE "TMUX_TIMER_SNOOZE_[0-9]+(:(stall|halt|caller-await))?@[0-9]+" \
            | awk -v c="$CLEARED_TS" -v n="$NOW" -F@ '$2 > c && $2 <= n' \
            | tail -1)
        SNOOZED=false
        if [ -n "$SNOOZE_LINE" ]; then
            SNOOZE_MIN=$(echo "$SNOOZE_LINE" | grep -oE "SNOOZE_[0-9]+" | grep -oE "[0-9]+")
            SNOOZE_TAG=$(echo "$SNOOZE_LINE" | grep -oE ":(stall|halt|caller-await)" | tr -d :)
            SNOOZE_TS=$(echo "$SNOOZE_LINE" | grep -oE "@[0-9]+" | tr -d @)
            if [ "$SNOOZE_TAG" = "caller-await" ]; then
                CAP=$SNOOZE_CAP_CALLER_AWAIT
            elif [ "$SNOOZE_TAG" = "stall" ] || [ "$SNOOZE_TAG" = "halt" ]; then
                CAP=$SNOOZE_CAP_EXTENDED
            else
                CAP=$SNOOZE_CAP_DEFAULT
            fi
            # Sanity check — flag absurd values that suggest unit confusion
            # (model emitted seconds instead of minutes). The marker payload
            # is documented as <N_MINUTES>; values > 200 cannot be a legitimate
            # cadence (longest legal cap is 120 from :caller-await). Likely
            # the model carried TIMEOUT (seconds) forward without dividing
            # by 60. Clamp still applies, but warn loudly so the operator
            # can investigate. Panel evidence 2026-04-28: TMUX_TIMER_SNOOZE_300
            # emitted; intended 5min, clamped silently to 15min before this fix.
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
            SNAP1=$(tmux capture-pane -t "$DEV_ALIAS" -p -S -80 2>/dev/null)
            sleep 8
            SNAP2=$(tmux capture-pane -t "$DEV_ALIAS" -p -S -80 2>/dev/null)
            sleep 8
            SNAP3=$(tmux capture-pane -t "$DEV_ALIAS" -p -S -80 2>/dev/null)

            if [ "$SNAP1" = "$SNAP2" ] && [ "$SNAP2" = "$SNAP3" ]; then
                echo "  → IDLE. Nudging."
                bash "$SEND_SCRIPT" "$DEV_ALIAS" "/tdevauto"
                sleep 0.5
                bash "$SEND_SCRIPT" "$DEV_ALIAS" Enter
            else
                echo "  → ACTIVE."
            fi
        fi
        fi  # close settings-prompt else
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
            # Position-based: the latest marker in scrollback wins, regardless of @ts.
            # Future-dated markers excluded from watermark to prevent the bug where a
            # fabricated future @ts becomes a permanent floor.
            CLEAR_NOW=$(date +%s)
            LATEST_TS=$(tmux capture-pane -t "$DEV_ALIAS" -p -S -500 2>/dev/null \
                | grep -oE "TMUX_TIMER_SNOOZE_[0-9]+(:(stall|halt))?@[0-9]+" \
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
