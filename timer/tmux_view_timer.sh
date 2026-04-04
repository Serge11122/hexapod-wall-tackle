#!/bin/bash
# View a timer or Claude tmux session by instance ID and role.
#
# Usage: ./tmux_view_timer.sh <id> <role>
#   id:   instance number, e.g. 1
#   role: tdev | teta | tsuperv | trev     → timer orchestrator sessions (timer-dev-N, etc.)
#         dev | eta | superv | rev         → Claude sessions (t_N_dev, etc.)
#
# Examples:
#   ./tmux_view_timer.sh 1 tdev     → attaches timer-dev-1
#   ./tmux_view_timer.sh 1 teta     → attaches timer-eta-1
#   ./tmux_view_timer.sh 1 tsuperv  → attaches timer-superv-1
#   ./tmux_view_timer.sh 1 trev     → attaches timer-rev-1
#   ./tmux_view_timer.sh 1 dev      → attaches t_1_dev
#   ./tmux_view_timer.sh 1 eta      → attaches t_1_eta
#   ./tmux_view_timer.sh 1 superv   → attaches t_1_superv
#   ./tmux_view_timer.sh 1 rev      → attaches t_1_rev

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: ./tmux_view_timer.sh <id> <role>"
    echo "  role: dev | eta | superv | rev | tdev | teta | tsuperv | trev"
    exit 1
fi

ID="$1"
ROLE="$2"

case "$ROLE" in
    tdev)    SESSION="timer-dev-${ID}" ;;
    teta)    SESSION="timer-eta-${ID}" ;;
    tsuperv) SESSION="timer-superv-${ID}" ;;
    trev)    SESSION="timer-rev-${ID}" ;;
    dev)     SESSION="t_${ID}_dev" ;;
    eta)     SESSION="t_${ID}_eta" ;;
    superv)  SESSION="t_${ID}_superv" ;;
    rev)     SESSION="t_${ID}_rev" ;;
    *)
        echo "Unknown role: $ROLE"
        echo "  role: dev | eta | superv | rev | tdev | teta | tsuperv | trev"
        exit 1 ;;
esac

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session '$SESSION' does not exist."
    exit 1
fi

exec tmux attach-session -t "$SESSION"
