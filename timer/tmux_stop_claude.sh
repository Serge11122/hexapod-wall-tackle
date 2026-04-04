#!/bin/bash
# Stop a Claude tmux session by alias.
# Usage: ./tmux_stop_claude.sh <alias>

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$1" ]; then
    echo "Usage: ./tmux_stop_claude.sh <alias>"
    echo "  alias: e.g. t_1_dev, t_1_eta, t_1_superv"
    exit 1
fi

ALIAS="$1"

if ! tmux has-session -t "$ALIAS" 2>/dev/null; then
    echo "Session '$ALIAS' not found (already stopped?)"
    exit 0
fi

tmux kill-session -t "$ALIAS"
echo "Session '$ALIAS' stopped"
