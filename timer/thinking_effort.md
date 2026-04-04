# Timer Pipeline — Model, Thinking & Effort Settings

| Component | Type | Model | Thinking | Effort | How Set | Notes |
|-----------|------|-------|----------|--------|---------|-------|
| `claude_command.sh` | Defaults | `claude-sonnet-4-6` | off (`CLAUDE_CODE_DISABLE_THINKING=1`) | low (`CLAUDE_CODE_EFFORT_LEVEL=low`) | env vars | Baseline for all ad-hoc Claude invocations |
| `t_1_dev` session | Claude session | `claude-sonnet-4-6` | off | low | `--model` flag + env vars in tmux session | Lightweight orchestrator — reads state, dispatches tconv/tdev/tdeep skills |
| `t_1_eta` session | Claude session | `claude-haiku-4-5` | off | low | `--model` flag + env vars in tmux session | Mechanical monitoring orchestrator — runs /teta |
| `t_1_superv` session | Claude session | `claude-haiku-4-5` | off | low | `--model` flag + env vars in tmux session | Mechanical health-check orchestrator — runs /t-superv every 10 min |
| `t_1_rev` session | Claude session | `claude-haiku-4-5` | off | low | `--model` flag + env vars in tmux session | Goal velocity reviewer — runs /trev every 30 min |
| `tconv` subagent | Agent tool (always) | `claude-opus-4-6` | on (adaptive) | medium | `model: "opus"` in Agent call | Conviction analysis, pivot direction, rule propagation, experiment failure analysis |
| `tdev` subagent | Agent tool (always) | `claude-opus-4-6` | on (adaptive) | medium | `model: "opus"` in Agent call | Code implementation, architectural changes, unit test execution |
| `tdeep` subagent | Agent tool (always) | `claude-opus-4-6` | on (adaptive) | medium | `model: "opus"` in Agent call | Static + runtime conviction violation checks, structural analysis, live execution monitoring |
| `teta` subagent | Agent tool (anomaly only) | `claude-sonnet-4-6` | off | low | `model: "sonnet"` in Agent call | Spawned only when ambiguous metric pattern or complex log anomaly detected |
| `t-superv` subagent | Agent tool (stuck only) | `claude-sonnet-4-6` | off | low | `model: "sonnet"` in Agent call | Spawned only when a stuck state (3a–3i) requires deeper diagnosis |
| `trev` subagent | Agent tool (stagnant only) | `claude-sonnet-4-6` | off | medium | `model: "sonnet"` in Agent call | Spawned only when goal velocity is stagnant or approach appears exhausted |

## Design Rules

- **Thinking disabled globally** via `CLAUDE_CODE_DISABLE_THINKING=1` in `claude_command.sh` and per-session in `tmux_run_claude.sh`. No `--no-thinking` CLI flag.
- **Opus + medium effort** is the ceiling. Never `high` or `max` effort on any component.
- **Main sessions are orchestrators only** — Sonnet (dev) and Haiku (eta, superv) do no heavy reasoning. They read state files and dispatch skills.
- **Heavy reasoning lives in subagents** — tconv, tdev, tdeep always spawn Opus. Subagent model is set explicitly via `model:` in the Agent tool call, independent of `CLAUDE_CODE_SUBAGENT_MODEL`.
- **Sonnet subagents are conditional** — teta and t-superv spawn Sonnet only on anomaly/stuck-state. Normal healthy runs complete inline on Haiku.
- **Env var precedence**: `CLAUDE_CODE_DISABLE_THINKING` and `CLAUDE_CODE_EFFORT_LEVEL` set per tmux session in `tmux_run_claude.sh`. Session flags override `claude_command.sh` defaults.
