#!/bin/bash
# Send keys to a Claude tmux session by alias.
#
# Usage: ./tmux_send_claude.sh <alias> <keys> [--no-enter]
#   alias: session name like t_1_dev
#   keys:  text to send, or special key name (Enter, Up, Down, etc.)

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: ./tmux_send_claude.sh <alias> <keys> [--no-enter]"
    exit 1
fi

ALIAS="$1"
KEYS="$2"
NO_ENTER=false
[ "$3" = "--no-enter" ] && NO_ENTER=true

if ! tmux has-session -t "$ALIAS" 2>/dev/null; then
    echo "Error: tmux session '$ALIAS' not found"
    exit 1
fi

if [ "$NO_ENTER" = true ]; then
    tmux send-keys -t "$ALIAS" "$KEYS"
else
    case "$KEYS" in
        Enter|Down|Up|Left|Right|Tab|Escape|Space|BSpace|Home|End|PageUp|PageDown)
            tmux send-keys -t "$ALIAS" "$KEYS" ;;
        *)
            tmux send-keys -t "$ALIAS" -l "$KEYS"
            tmux send-keys -t "$ALIAS" Enter ;;
    esac
fi
