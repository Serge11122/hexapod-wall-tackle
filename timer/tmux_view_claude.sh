#!/bin/bash
# Attach to a Claude tmux session by alias.
# Usage: ./tmux_view_claude.sh <alias>

if [ -z "$1" ]; then
    echo "Usage: ./tmux_view_claude.sh <alias>"
    echo "  alias: e.g. t_1_dev, t_1_eta, t_1_superv"
    exit 1
fi

ALIAS="$1"

if ! tmux has-session -t "$ALIAS" 2>/dev/null; then
    echo "Error: session '$ALIAS' not found"
    exit 1
fi

echo "Attaching to $ALIAS (Ctrl+B D to detach)"
tmux set-option -t "$ALIAS" mouse on 2>/dev/null || true
tmux set-option -t "$ALIAS" history-limit 50000 2>/dev/null || true
exec tmux attach-session -t "$ALIAS"
