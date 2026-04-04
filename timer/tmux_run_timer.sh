#!/bin/bash
# tmux_run_timer.sh — Start or stop all four timer orchestrators for one instance.
#
# Usage:
#   ./tmux_run_timer.sh <instance_id>          — start dev + eta + superv + rev orchestrators
#   ./tmux_run_timer.sh <instance_id> --stop   — stop all four orchestrator sessions (Claude sessions kept alive)
#   ./tmux_run_timer.sh <instance_id> --status — show status of all sessions (timers + Claude)
#
# Timer orchestrator sessions:  timer-dev-N, timer-eta-N, timer-superv-N, timer-rev-N
# Claude sessions (preserved):  t_N_dev, t_N_eta, t_N_superv, t_N_rev
#
# After start, monitors all eight sessions until Ctrl-C.

TIMER_DIR="$(cd "$(dirname "$0")" && pwd)"

show_usage() {
    echo "Usage: ./tmux_run_timer.sh <instance_id> [--stop|--status]"
    echo "  <instance_id>  integer >= 1"
    echo "  --stop         stop all three orchestrator sessions (preserves Claude sessions)"
    echo "  --status       print session status table and exit"
}

if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then show_usage; exit 0; fi
if [ -z "$1" ]; then echo "Error: instance_id required"; show_usage; exit 1; fi

INSTANCE_ID="$1"; shift
if ! [[ "$INSTANCE_ID" =~ ^[0-9]+$ ]] || [ "$INSTANCE_ID" -lt 1 ]; then
    echo "Error: instance_id must be an integer >= 1"; exit 1
fi

# Session names
DEV_TIMER="timer-dev-${INSTANCE_ID}"
ETA_TIMER="timer-eta-${INSTANCE_ID}"
SUPERV_TIMER="timer-superv-${INSTANCE_ID}"
REV_TIMER="timer-rev-${INSTANCE_ID}"
DEV_CLAUDE="t_${INSTANCE_ID}_dev"
ETA_CLAUDE="t_${INSTANCE_ID}_eta"
SUPERV_CLAUDE="t_${INSTANCE_ID}_superv"
REV_CLAUDE="t_${INSTANCE_ID}_rev"

sess_status() {
    tmux has-session -t "$1" 2>/dev/null && echo "ALIVE" || echo "DEAD"
}

print_status() {
    local ts
    ts=$(TZ='America/Los_Angeles' date '+%Y-%m-%d %H:%M:%S PT')
    echo ""
    echo "  [$ts] Timer Instance: $INSTANCE_ID"
    echo "  -----------------------------------------------"
    printf "  %-24s  %-8s  %s\n" "Session" "Type" "Status"
    printf "  %-24s  %-8s  %s\n" "-------" "----" "------"
    printf "  %-24s  %-8s  %s\n" "$DEV_TIMER"   "orch"   "$(sess_status $DEV_TIMER)"
    printf "  %-24s  %-8s  %s\n" "$ETA_TIMER"   "orch"   "$(sess_status $ETA_TIMER)"
    printf "  %-24s  %-8s  %s\n" "$SUPERV_TIMER" "orch"  "$(sess_status $SUPERV_TIMER)"
    printf "  %-24s  %-8s  %s\n" "$REV_TIMER"   "orch"   "$(sess_status $REV_TIMER)"
    printf "  %-24s  %-8s  %s\n" "$DEV_CLAUDE"  "claude" "$(sess_status $DEV_CLAUDE)"
    printf "  %-24s  %-8s  %s\n" "$ETA_CLAUDE"  "claude" "$(sess_status $ETA_CLAUDE)"
    printf "  %-24s  %-8s  %s\n" "$SUPERV_CLAUDE" "claude" "$(sess_status $SUPERV_CLAUDE)"
    printf "  %-24s  %-8s  %s\n" "$REV_CLAUDE"  "claude" "$(sess_status $REV_CLAUDE)"
    echo "  -----------------------------------------------"
}

# ── --status ──────────────────────────────────────────────────────────────────
if [[ "$1" == "--status" ]]; then
    print_status
    echo ""
    exit 0
fi

# ── --stop ────────────────────────────────────────────────────────────────────
if [[ "$1" == "--stop" ]]; then
    echo "Stopping orchestrator sessions for instance $INSTANCE_ID (Claude sessions preserved)..."
    for sess in "$DEV_TIMER" "$ETA_TIMER" "$SUPERV_TIMER" "$REV_TIMER"; do
        if tmux has-session -t "$sess" 2>/dev/null; then
            tmux kill-session -t "$sess"
            echo "  Stopped: $sess"
        else
            echo "  Already stopped: $sess"
        fi
    done
    print_status
    echo ""
    exit 0
fi

# ── start ─────────────────────────────────────────────────────────────────────
echo "Starting timer instance $INSTANCE_ID..."
echo ""

bash "$TIMER_DIR/tmux_timer_dev.sh"   "$INSTANCE_ID"
bash "$TIMER_DIR/tmux_timer_eta.sh"   "$INSTANCE_ID"
bash "$TIMER_DIR/tmux_timer_superv.sh" "$INSTANCE_ID"
bash "$TIMER_DIR/tmux_timer_rev.sh"   "$INSTANCE_ID"

echo ""
echo "All four orchestrators started."
echo "  View dev:   ./tmux_timer_dev.sh $INSTANCE_ID --view"
echo "  View eta:   ./tmux_timer_eta.sh $INSTANCE_ID --view"
echo "  View superv:./tmux_timer_superv.sh $INSTANCE_ID --view"
echo "  View rev:   ./tmux_timer_rev.sh $INSTANCE_ID --view"
echo "  Stop all:   ./tmux_run_timer.sh $INSTANCE_ID --stop"
echo ""

# ── monitor loop ──────────────────────────────────────────────────────────────
echo "Monitoring all sessions (Ctrl-C to exit monitor — orchestrators keep running)..."
echo ""

INTERVAL=15
ITERATION=1
trap 'echo ""; echo "Monitor exited. Orchestrators still running."; exit 0' INT

while true; do
    print_status

    # Check for any dead sessions and warn
    WARNINGS=""
    for sess in "$DEV_TIMER" "$ETA_TIMER" "$SUPERV_TIMER" "$REV_TIMER"; do
        if ! tmux has-session -t "$sess" 2>/dev/null; then
            WARNINGS="${WARNINGS}  WARNING: orchestrator $sess is DEAD\n"
        fi
    done
    # Claude sessions: warn only if timer orch is alive (timer would restart them, so dead Claude + dead orch = stale)
    for pair in "$DEV_TIMER:$DEV_CLAUDE" "$ETA_TIMER:$ETA_CLAUDE" "$SUPERV_TIMER:$SUPERV_CLAUDE" "$REV_TIMER:$REV_CLAUDE"; do
        orch="${pair%%:*}"
        claude="${pair##*:}"
        if tmux has-session -t "$orch" 2>/dev/null && ! tmux has-session -t "$claude" 2>/dev/null; then
            WARNINGS="${WARNINGS}  WARNING: Claude session $claude is DEAD (orch $orch will restart it on next tick)\n"
        fi
    done

    if [ -n "$WARNINGS" ]; then
        echo ""
        printf "$WARNINGS"
    fi

    echo ""
    printf "  Refresh #%d | next in %ds | Ctrl-C to exit monitor\n" "$ITERATION" "$INTERVAL"

    ITERATION=$((ITERATION + 1))
    sleep "$INTERVAL"
done
