#!/bin/bash
# Launch a Claude tmux session for a specific timer slot.
#
# Usage: ./tmux_run_claude.sh <alias> [--model <model>] [--effort <low|medium|high>] [--view] [--thinking-off] [--thinking-on]
#   alias: string like t_1_dev, t_1_eta, t_1_superv
#
# Defaults: --model sonnet (Sonnet 4.6), --effort medium, thinking disabled.
# Model and effort are passed as `claude` CLI arguments (NOT env vars).
# --thinking-off: sets CLAUDE_CODE_DISABLE_THINKING=1 (default for all sessions)
# --thinking-on:  unsets CLAUDE_CODE_DISABLE_THINKING (enables adaptive thinking)
#
# Session name == alias (deterministic, no epoch suffix).
# Always uses -n (new named session). Timer sessions don't rely on Claude context
# persistence — all state is in files. --resume opens an interactive picker when
# the session name is not found in Claude's session store, which breaks automation.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$1" ]; then
    echo "Error: alias required (e.g. t_1_dev)"
    echo "Usage: ./tmux_run_claude.sh <alias> [--model <model>] [--effort <low|medium|high>] [--thinking-off] [--thinking-on]"
    exit 1
fi

ALIAS="$1"; shift
SESSION_NAME="$ALIAS"
# Defaults: model sonnet (Sonnet 4.6), effort medium, thinking disabled
MODEL_FLAG="--model sonnet"
EFFORT_FLAG="--effort medium"
VIEW=0
# THINKING_ENV="export CLAUDE_CODE_DISABLE_THINKING=1"
#   export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50; \
#   $THINKING_ENV; \

while [ -n "$1" ]; do
    case "$1" in
        --model) MODEL_FLAG="--model $2"; shift 2 ;;
        --effort) EFFORT_FLAG="--effort $2"; shift 2 ;;
        --view) VIEW=1; shift ;;
        # --thinking-off) THINKING_ENV="export CLAUDE_CODE_DISABLE_THINKING=1"; shift ;;
        # --thinking-on)  THINKING_ENV="unset CLAUDE_CODE_DISABLE_THINKING"; shift ;;
        *) shift ;;
    esac
done

current_dir="$(cd "$SCRIPT_DIR/.." && pwd)"

# If session already exists, attach (or just report) — never kill a running session
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session already running: $SESSION_NAME"
    if [ "$VIEW" -eq 1 ]; then
        tmux attach-session -t "$SESSION_NAME"
    fi
    exit 0
fi

echo "Launching Claude session: $SESSION_NAME"

tmux set-option -g history-limit 50000 2>/dev/null || true
tmux set-option -g mouse on 2>/dev/null || true

CLAUDE_CMD="claude --dangerously-skip-permissions --permission-mode bypassPermissions -n \"$SESSION_NAME\" $MODEL_FLAG $EFFORT_FLAG"

tmux new-session -d -s "$SESSION_NAME" -x 120 -y 40 \
  "bash -lc 'cd $current_dir; \
  export TERM=screen-256color; \
  export COLUMNS=120; \
  export LINES=40; \
  $CLAUDE_CMD; \
  exec bash'"

tmux set-option -t "$SESSION_NAME" mouse on 2>/dev/null || true
tmux set-option -t "$SESSION_NAME" history-limit 50000 2>/dev/null || true

echo "Session started: $SESSION_NAME"

if [ "$VIEW" -eq 1 ]; then
    tmux attach-session -t "$SESSION_NAME"
fi
