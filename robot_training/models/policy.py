"""
Actor-critic policy networks for hexapod terrain traversal.

Two variants:
  ActorCritic       — stateless MLP (fast, no memory)
  LSTMActorCritic   — LSTM-based (temporal memory across timesteps)

The LSTM variant is preferred: it can coordinate multi-step gait patterns
that a memoryless MLP cannot. The hidden state (h, c) is threaded through
rollout collection, reset at episode boundaries, and stored in the buffer
for independent per-step updates (no BPTT — simpler and stable with PPO).
"""

import math
import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Normal

LOG_STD_MIN = -4.0
LOG_STD_MAX =  0.5

LSTM_DIM    = 128   # LSTM hidden size
ENC_DIM     = 256   # encoder hidden size

# Fixed exploration std for locomotion training.
# State-dependent std keeps std high → mean stays near 0 (discovered empirically).
# Fixed std forces the mean to learn walking. Annealed by trainer via set_log_std().
INIT_LOG_STD  = 0.5             # std=1.65 initially: wide exploration (same as LOG_STD_MAX)
FINAL_LOG_STD = math.log(0.12)  # std=0.12 at convergence: tight gait exploitation


# ─────────────────────────────────────────────────────────────────────────────
# MLP policy (kept for compatibility / ablation)
# ─────────────────────────────────────────────────────────────────────────────

class ActorCritic(nn.Module):
    def __init__(self, obs_dim: int, act_dim: int, hidden: int = 256):
        super().__init__()
        self.obs_dim = obs_dim
        self.act_dim = act_dim

        self.encoder = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.LayerNorm(hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.LayerNorm(hidden),
            nn.ReLU(),
        )
        self.actor_mean    = nn.Linear(hidden, act_dim)
        self.actor_log_std = nn.Linear(hidden, act_dim)
        self.critic        = nn.Linear(hidden, 1)
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=math.sqrt(2))
                nn.init.zeros_(m.bias)
        nn.init.orthogonal_(self.actor_mean.weight, gain=0.01)
        nn.init.orthogonal_(self.actor_log_std.weight, gain=0.01)

    def encode(self, obs: torch.Tensor) -> torch.Tensor:
        return self.encoder(obs)

    def forward(self, obs: torch.Tensor) -> tuple:
        h       = self.encode(obs)
        mean    = torch.tanh(self.actor_mean(h))
        log_std = self.actor_log_std(h).clamp(LOG_STD_MIN, LOG_STD_MAX)
        value   = self.critic(h).squeeze(-1)
        return mean, log_std, value

    def act(self, obs: torch.Tensor, deterministic: bool = False):
        mean, log_std, value = self.forward(obs)
        if deterministic:
            return mean, None, value
        dist      = Normal(mean, log_std.exp())
        action    = dist.sample().clamp(-1.0, 1.0)
        log_prob  = dist.log_prob(action).sum(-1)
        return action, log_prob, value

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor):
        mean, log_std, value = self.forward(obs)
        dist     = Normal(mean, log_std.exp())
        log_prob = dist.log_prob(actions).sum(-1)
        entropy  = dist.entropy().sum(-1)
        return log_prob, entropy, value


# ─────────────────────────────────────────────────────────────────────────────
# LSTM policy (preferred for terrain traversal)
# ─────────────────────────────────────────────────────────────────────────────

class LSTMActorCritic(nn.Module):
    """
    LSTM-based actor-critic for coordinated multi-step gait learning.

    Observation is first encoded by a linear layer, then fed to an LSTM cell.
    The LSTM hidden state provides memory of previous joint positions and
    contact patterns, allowing the policy to learn coordinated gait sequences.

    Hidden state (h, c) shape: (1, batch_size, LSTM_DIM)
    """

    def __init__(self, obs_dim: int, act_dim: int,
                 enc_dim: int = ENC_DIM, lstm_dim: int = LSTM_DIM,
                 init_log_std: float = INIT_LOG_STD):
        super().__init__()
        self.obs_dim  = obs_dim
        self.act_dim  = act_dim
        self.lstm_dim = lstm_dim

        # Obs encoder: compress observation to LSTM input
        self.encoder = nn.Sequential(
            nn.Linear(obs_dim, enc_dim),
            nn.LayerNorm(enc_dim),
            nn.ReLU(),
        )

        # LSTM: maintains temporal context across steps
        self.lstm = nn.LSTM(enc_dim, lstm_dim, batch_first=True)

        # Actor: mean head + FIXED (non-state-dependent) log_std
        # Fixed std forces the mean to learn walking (state-dep std → mean stays at 0)
        self.actor_mean = nn.Linear(lstm_dim, act_dim)
        self.log_std    = nn.Parameter(torch.full((act_dim,), init_log_std))

        # Critic head
        self.critic = nn.Linear(lstm_dim, 1)

        self._init_weights()

    def _init_weights(self):
        for name, p in self.named_parameters():
            if "log_std" in name:
                continue   # keep the initial log_std value set in __init__
            if "weight" in name and p.dim() >= 2:
                if "lstm" in name:
                    nn.init.orthogonal_(p)
                else:
                    nn.init.orthogonal_(p, gain=math.sqrt(2))
            elif "bias" in name:
                nn.init.zeros_(p)
        # Small init for actor output mean — starts near zero, learns from experience
        nn.init.orthogonal_(self.actor_mean.weight, gain=0.01)

    def init_hidden(self, batch_size: int = 1) -> tuple:
        """Return zero initial LSTM hidden state (h, c)."""
        device = next(self.parameters()).device
        h = torch.zeros(1, batch_size, self.lstm_dim, device=device)
        c = torch.zeros(1, batch_size, self.lstm_dim, device=device)
        return (h, c)

    def set_log_std(self, log_std_val: float) -> None:
        """Anneal exploration std during training (called by trainer)."""
        with torch.no_grad():
            self.log_std.fill_(log_std_val)

    def forward(self, obs: torch.Tensor, lstm_state: tuple) -> tuple:
        """
        obs        : (B, obs_dim)
        lstm_state : ((1,B,lstm_dim), (1,B,lstm_dim))
        returns    : (mean, value, new_lstm_state)
        """
        enc = self.encoder(obs)                     # (B, enc_dim)
        enc = enc.unsqueeze(1)                      # (B, 1, enc_dim)
        out, new_state = self.lstm(enc, lstm_state) # (B, 1, lstm_dim)
        out = out.squeeze(1)                        # (B, lstm_dim)

        mean  = torch.tanh(self.actor_mean(out))
        value = self.critic(out).squeeze(-1)
        return mean, value, new_state

    def act(self, obs: torch.Tensor, lstm_state: tuple,
            deterministic: bool = False) -> tuple:
        """
        Returns (action, log_prob, value, new_lstm_state).
        log_prob is None in deterministic mode.
        """
        mean, value, new_state = self.forward(obs, lstm_state)
        if deterministic:
            return mean, None, value, new_state
        log_std  = self.log_std.clamp(LOG_STD_MIN, LOG_STD_MAX)
        dist     = Normal(mean, log_std.exp())
        action   = dist.sample().clamp(-1.0, 1.0)
        log_prob = dist.log_prob(action).sum(-1)
        return action, log_prob, value, new_state

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor,
                         lstm_states_h: torch.Tensor,
                         lstm_states_c: torch.Tensor) -> tuple:
        """
        Evaluate log_prob, entropy, value for a batch of (obs, action, lstm_state).
        Uses stored lstm states — independent per-step forward passes (no BPTT).

        lstm_states_h : (B, lstm_dim)
        lstm_states_c : (B, lstm_dim)
        """
        h = lstm_states_h.unsqueeze(0)   # (1, B, lstm_dim)
        c = lstm_states_c.unsqueeze(0)
        mean, value, _ = self.forward(obs, (h, c))
        log_std  = self.log_std.clamp(LOG_STD_MIN, LOG_STD_MAX)
        dist     = Normal(mean, log_std.exp())
        log_prob = dist.log_prob(actions).sum(-1)
        entropy  = dist.entropy().sum(-1)
        return log_prob, entropy, value


# ─────────────────────────────────────────────────────────────────────────────
# Save / load
# ─────────────────────────────────────────────────────────────────────────────

def save_policy(policy: nn.Module, path: str) -> None:
    is_lstm = isinstance(policy, LSTMActorCritic)
    torch.save({
        "obs_dim":      policy.obs_dim,
        "act_dim":      policy.act_dim,
        "is_lstm":      is_lstm,
        "lstm_dim":     policy.lstm_dim if is_lstm else None,
        "init_log_std": float(policy.log_std[0].item()) if is_lstm else None,
        "state_dict":   policy.state_dict(),
    }, path)


def load_policy(path: str, device: torch.device = None) -> nn.Module:
    if device is None:
        device = torch.device("cpu")
    ckpt = torch.load(path, map_location=device, weights_only=False)
    if ckpt.get("is_lstm", False):
        init_log_std = ckpt.get("init_log_std", INIT_LOG_STD)
        policy = LSTMActorCritic(
            obs_dim      = ckpt["obs_dim"],
            act_dim      = ckpt["act_dim"],
            lstm_dim     = ckpt.get("lstm_dim", LSTM_DIM),
            init_log_std = init_log_std,
        )
    else:
        policy = ActorCritic(ckpt["obs_dim"], ckpt["act_dim"])
    policy.load_state_dict(ckpt["state_dict"])
    policy.to(device)
    return policy
