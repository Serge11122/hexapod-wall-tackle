#!/bin/bash
# View a timer or Claude tmux session by instance ID and role.
#
# Usage: ./tmux_view_timer.sh <id> <role>
#   id:   instance number, e.g. 1
#   role: tdev | tsuperv | tdesign      → timer orchestrator sessions
#         dev | eta | superv | rev | design → Claude sessions (t_N_<role>)
#
# Examples:
#   ./tmux_view_timer.sh 1 tdev     → attaches timer-dev-1
#   ./tmux_view_timer.sh 1 tsuperv  → attaches timer-superv-1
#   ./tmux_view_timer.sh 1 tdesign  → attaches timer-design-1
#   ./tmux_view_timer.sh 1 dev      → attaches t_1_dev
#   ./tmux_view_timer.sh 1 eta      → attaches t_1_eta
#   ./tmux_view_timer.sh 1 superv   → attaches t_1_superv
#   ./tmux_view_timer.sh 1 rev      → attaches t_1_rev
#   ./tmux_view_timer.sh 1 design   → attaches t_1_design

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: ./tmux_view_timer.sh <id> <role>"
    echo "  role: dev | eta | superv | rev | design | tdev | tsuperv | tdesign"
    exit 1
fi

ID="$1"
ROLE="$2"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
START_KIND=""
START_SCRIPT=""
case "$ROLE" in
    tdev)    SESSION="timer-dev-${ID}";    START_KIND=timer; START_SCRIPT="$SCRIPT_DIR/tmux_timer_dev.sh" ;;
    tsuperv) SESSION="timer-superv-${ID}"; START_KIND=timer; START_SCRIPT="$SCRIPT_DIR/tmux_timer_superv.sh" ;;
    tdesign) SESSION="timer-design-${ID}"; START_KIND=timer; START_SCRIPT="$SCRIPT_DIR/tmux_timer_design.sh" ;;
    dev)     SESSION="t_${ID}_dev";    START_KIND=claude ;;
    eta)     SESSION="t_${ID}_eta";    START_KIND=claude ;;
    superv)  SESSION="t_${ID}_superv"; START_KIND=claude ;;
    rev)     SESSION="t_${ID}_rev";    START_KIND=claude ;;
    design)  SESSION="t_${ID}_design"; START_KIND=claude ;;
    *)
        echo "Unknown role: $ROLE"
        echo "  role: dev | eta | superv | rev | design | tdev | tsuperv | tdesign"
        exit 1 ;;
esac

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    if [ "$START_KIND" = claude ]; then
        echo "Session '$SESSION' does not exist. Starting it."
        bash "$SCRIPT_DIR/tmux_run_claude.sh" "$SESSION"
        sleep 2
    elif [ "$START_KIND" = timer ]; then
        echo "Session '$SESSION' does not exist. Starting it via $(basename "$START_SCRIPT") $ID."
        bash "$START_SCRIPT" "$ID"
        sleep 1
    fi
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "Failed to start session '$SESSION'."
        exit 1
    fi
fi

exec tmux attach-session -t "$SESSION"
