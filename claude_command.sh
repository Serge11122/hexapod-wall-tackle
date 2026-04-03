#!/bin/bash
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50
export CLAUDE_CODE_DISABLE_THINKING=1
claude --model haiku --dangerously-skip-permissions "$@"
