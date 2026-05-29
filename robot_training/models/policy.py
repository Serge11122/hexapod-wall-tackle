"""
Actor-critic policy network for hexapod terrain traversal.

Architecture:
  Shared encoder: Linear(obs_dim → 256) → ReLU → Linear(256 → 256) → ReLU
  Actor head:     Linear(256 → act_dim) → Tanh  (outputs in [-1, 1])
  Critic head:    Linear(256 → 1)

Separate left/right models are just separate instances of this class.
"""

import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal

LOG_STD_MIN = -4.0
LOG_STD_MAX =  0.5


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

        # Actor: mean + log_std (state-dependent)
        self.actor_mean    = nn.Linear(hidden, act_dim)
        self.actor_log_std = nn.Linear(hidden, act_dim)

        # Critic
        self.critic = nn.Linear(hidden, 1)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=math.sqrt(2))
                nn.init.zeros_(m.bias)
        # Small init for actor output
        nn.init.orthogonal_(self.actor_mean.weight, gain=0.01)
        nn.init.orthogonal_(self.actor_log_std.weight, gain=0.01)

    def encode(self, obs: torch.Tensor) -> torch.Tensor:
        return self.encoder(obs)

    def forward(self, obs: torch.Tensor) -> tuple:
        """Return (mean, log_std, value)."""
        h       = self.encode(obs)
        mean    = torch.tanh(self.actor_mean(h))
        log_std = self.actor_log_std(h).clamp(LOG_STD_MIN, LOG_STD_MAX)
        value   = self.critic(h).squeeze(-1)
        return mean, log_std, value

    def act(self, obs: torch.Tensor, deterministic: bool = False):
        """Sample action and return (action, log_prob, value)."""
        mean, log_std, value = self.forward(obs)
        if deterministic:
            return mean, None, value
        dist      = Normal(mean, log_std.exp())
        action    = dist.sample()
        action    = action.clamp(-1.0, 1.0)
        log_prob  = dist.log_prob(action).sum(-1)
        return action, log_prob, value

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor):
        """Return (log_prob, entropy, value) for given obs+actions."""
        mean, log_std, value = self.forward(obs)
        dist     = Normal(mean, log_std.exp())
        log_prob = dist.log_prob(actions).sum(-1)
        entropy  = dist.entropy().sum(-1)
        return log_prob, entropy, value


def save_policy(policy: ActorCritic, path: str) -> None:
    torch.save({
        "obs_dim": policy.obs_dim,
        "act_dim": policy.act_dim,
        "state_dict": policy.state_dict(),
    }, path)


def load_policy(path: str, device: torch.device = None) -> ActorCritic:
    if device is None:
        device = torch.device("cpu")
    ckpt   = torch.load(path, map_location=device)
    policy = ActorCritic(ckpt["obs_dim"], ckpt["act_dim"])
    policy.load_state_dict(ckpt["state_dict"])
    policy.to(device)
    return policy
