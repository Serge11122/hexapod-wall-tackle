"""
Rollout buffer for PPO with optional LSTM hidden-state storage.

When lstm_dim > 0, the buffer stores (h, c) at each step so the LSTM policy
can evaluate actions without BPTT — each step is an independent forward pass
using the stored hidden state from rollout time.
"""

import numpy as np
import torch


class RolloutBuffer:
    def __init__(self, n_steps: int, obs_dim: int, act_dim: int,
                 gamma: float = 0.99, gae_lambda: float = 0.95,
                 device: torch.device = None, lstm_dim: int = 0):
        self.n_steps    = n_steps
        self.gamma      = gamma
        self.gae_lambda = gae_lambda
        self.device     = device or torch.device("cpu")
        self.lstm_dim   = lstm_dim

        self.obs       = np.zeros((n_steps, obs_dim),  dtype=np.float32)
        self.actions   = np.zeros((n_steps, act_dim),  dtype=np.float32)
        self.rewards   = np.zeros(n_steps,              dtype=np.float32)
        self.dones     = np.zeros(n_steps,              dtype=np.float32)
        self.values    = np.zeros(n_steps,              dtype=np.float32)
        self.log_probs = np.zeros(n_steps,              dtype=np.float32)

        if lstm_dim > 0:
            # Store LSTM hidden state at each step for independent evaluation
            self.lstm_h = np.zeros((n_steps, lstm_dim), dtype=np.float32)
            self.lstm_c = np.zeros((n_steps, lstm_dim), dtype=np.float32)
        else:
            self.lstm_h = None
            self.lstm_c = None

        self.advantages = np.zeros(n_steps, dtype=np.float32)
        self.returns    = np.zeros(n_steps, dtype=np.float32)
        self._ptr       = 0

    def add(self, obs, action, reward, done, value, log_prob,
            lstm_h=None, lstm_c=None) -> None:
        self.obs[self._ptr]       = obs
        self.actions[self._ptr]   = action
        self.rewards[self._ptr]   = reward
        self.dones[self._ptr]     = done
        self.values[self._ptr]    = value
        self.log_probs[self._ptr] = log_prob
        if self.lstm_h is not None and lstm_h is not None:
            self.lstm_h[self._ptr] = lstm_h
            self.lstm_c[self._ptr] = lstm_c
        self._ptr += 1

    def full(self) -> bool:
        return self._ptr >= self.n_steps

    def reset(self) -> None:
        self._ptr = 0

    def compute_returns_and_advantages(self, last_value: float) -> None:
        last_gae = 0.0
        for t in reversed(range(self.n_steps)):
            if t == self.n_steps - 1:
                next_val = last_value * (1.0 - self.dones[t])
            else:
                next_val = self.values[t + 1] * (1.0 - self.dones[t])
            delta    = self.rewards[t] + self.gamma * next_val - self.values[t]
            last_gae = delta + self.gamma * self.gae_lambda * (1.0 - self.dones[t]) * last_gae
            self.advantages[t] = last_gae
        self.returns = self.advantages + self.values

        # Normalise advantages
        adv  = self.advantages
        mean, std = adv.mean(), adv.std()
        self.advantages = (adv - mean) / (std + 1e-8)

    def get_batches(self, batch_size: int):
        """Yield mini-batches as torch tensors. Includes lstm states if stored."""
        indices = np.random.permutation(self.n_steps)
        for start in range(0, self.n_steps, batch_size):
            idx = indices[start:start + batch_size]
            batch = (
                torch.from_numpy(self.obs[idx]).to(self.device),
                torch.from_numpy(self.actions[idx]).to(self.device),
                torch.from_numpy(self.advantages[idx]).to(self.device),
                torch.from_numpy(self.returns[idx]).to(self.device),
                torch.from_numpy(self.log_probs[idx]).to(self.device),
            )
            if self.lstm_h is not None:
                h = torch.from_numpy(self.lstm_h[idx]).to(self.device)
                c = torch.from_numpy(self.lstm_c[idx]).to(self.device)
                yield batch + (h, c)
            else:
                yield batch
