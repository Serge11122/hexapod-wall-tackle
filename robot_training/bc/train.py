"""
Behavioral Cloning training.

Loads (obs, action) pairs, trains ActorCritic policy with MSE loss on actor mean.
Only the actor_mean layers are trained; critic is randomly initialised (fine for PPO init).
"""

import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from robot_training.models.policy import ActorCritic, save_policy
from robot_training.env.terrain_env import OBS_DIM, ACT_DIM

BC_EPOCHS    = 60
BC_LR        = 3e-4
BC_BATCH     = 256
DEVICE       = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def train_bc(obs_path: Path, act_path: Path, out_path: Path, label: str = "") -> ActorCritic:
    obs = torch.from_numpy(np.load(obs_path)).float().to(DEVICE)
    act = torch.from_numpy(np.load(act_path)).float().to(DEVICE)

    dataset = TensorDataset(obs, act)
    loader  = DataLoader(dataset, batch_size=BC_BATCH, shuffle=True)

    policy    = ActorCritic(OBS_DIM, ACT_DIM).to(DEVICE)
    optimiser = torch.optim.Adam(policy.parameters(), lr=BC_LR)

    print(f"  BC training [{label}]: {len(obs)} samples, {BC_EPOCHS} epochs, device={DEVICE}")
    t0 = time.time()
    for epoch in range(BC_EPOCHS):
        total_loss = 0.0
        for batch_obs, batch_act in loader:
            mean, _, _ = policy.forward(batch_obs)
            loss       = nn.functional.mse_loss(mean, batch_act)
            optimiser.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
            optimiser.step()
            total_loss += loss.item() * len(batch_obs)
        if (epoch + 1) % 10 == 0:
            avg = total_loss / len(obs)
            print(f"    epoch {epoch+1:3d}/{BC_EPOCHS}  loss={avg:.5f}  t={time.time()-t0:.0f}s")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_policy(policy, str(out_path))
    print(f"  BC model saved → {out_path}")
    return policy


def train_bc_both(data_dir: Path, model_dir: Path) -> dict:
    policies = {}
    for label in ("right", "left"):
        obs_path = data_dir / f"bc_obs_{label}.npy"
        act_path = data_dir / f"bc_act_{label}.npy"
        out_path = model_dir / f"bc_{label}.pt"
        if not obs_path.exists():
            raise FileNotFoundError(f"BC data missing: {obs_path}")
        policies[label] = train_bc(obs_path, act_path, out_path, label)
    return policies


if __name__ == "__main__":
    root     = Path(__file__).parent.parent
    data_dir = root / "data" / "bc"
    model_dir = root / "models"
    train_bc_both(data_dir, model_dir)
