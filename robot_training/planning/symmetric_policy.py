"""
Symmetric policy for leftward walking.

Since the 2D robot environment is symmetric, the rightward policy can be
used for leftward walking by mirroring the observation:
  - Negate body velocity vx (leftward becomes "forward" to the model)
  - Flip the local map order (what was "ahead" for right is now "behind")
  - Negate hip joint angles (mirror the motor commands)

This allows a single trained policy to walk in both directions.
"""

import math
import numpy as np
import torch

from robot_training.env.terrain_env import (
    JOINT_DIM, VEL_DIM, TORQ_DIM, CONT_DIM, FORC_DIM, FHGT_DIM,
    BVEL_DIM, PITCH_DIM, BASE_DIM,
)
from robot_training.env.local_map import OBS_SIZE
from robot_training.models.policy import ActorCritic


def mirror_observation(obs: np.ndarray) -> np.ndarray:
    """
    Mirror observation for leftward walking.

    Observation layout (OBS_DIM=219):
      [0:8]   joint angles (hip0,knee0,...,hip3,knee3)
      [8:16]  joint vels
      [16:24] torques
      [24:28] contact flags
      [28:32] contact forces
      [32:36] foot heights
      [36:38] body vx, vy
      [38:39] pitch
      [39:219] local map (60 cells × 3 channels)

    Mirror:
      - Negate vx (index 36)
      - Reverse local map cells (windows flip direction)
      - Negate hip angles (even indices 0,2,4,6) — motor direction
      - Negate hip vels (even indices 8,10,12,14)
      - Negate hip torques (even indices 16,18,20,22)
    """
    obs = obs.copy()

    # Negate vx (body velocity x)
    obs[36] = -obs[36]

    # Negate pitch sign for mirrored walking
    # obs[38] stays the same (pitch is symmetric)

    # Negate hip angles (indices 0,2,4,6)
    obs[0] = -obs[0]; obs[2] = -obs[2]
    obs[4] = -obs[4]; obs[6] = -obs[6]

    # Negate hip angular velocities (indices 8,10,12,14)
    obs[8] = -obs[8]; obs[10] = -obs[10]
    obs[12] = -obs[12]; obs[14] = -obs[14]

    # Negate hip torques (indices 16,18,20,22)
    obs[16] = -obs[16]; obs[18] = -obs[18]
    obs[20] = -obs[20]; obs[22] = -obs[22]

    # Reverse local map window (60 cells, each with 3 channels)
    # OBS_CHANNELS=3, WINDOW_CELLS=60
    map_obs = obs[39:].reshape(60, 3)
    obs[39:] = map_obs[::-1].reshape(-1)

    return obs


def mirror_action(action: np.ndarray) -> np.ndarray:
    """
    Mirror action for leftward walking.

    Joint action: [hip0, knee0, hip1, knee1, hip2, knee2, hip3, knee3]
    For leftward walking, negate hip target angles (reverse hip direction).
    Knee angles stay the same (symmetric bending).
    """
    action = action.copy()
    action[0] = -action[0]   # hip0
    action[2] = -action[2]   # hip1
    action[4] = -action[4]   # hip2
    action[6] = -action[6]   # hip3
    return action


class SymmetricLeftPolicy:
    """
    Wraps a rightward policy to walk leftward via observation mirroring.
    """

    def __init__(self, right_policy: ActorCritic, device: torch.device):
        self.right_policy = right_policy
        self.device       = device
        right_policy.eval()

    def act(self, obs: np.ndarray, deterministic: bool = True) -> np.ndarray:
        """
        Given obs in leftward convention, return joint targets (radians).
        """
        mirrored_obs = mirror_observation(obs)
        obs_t = torch.from_numpy(mirrored_obs).unsqueeze(0).to(self.device)

        with torch.no_grad():
            action, _, _ = self.right_policy.act(obs_t, deterministic=deterministic)

        act_np = action.squeeze(0).cpu().numpy()
        joint_targets = mirror_action(act_np)
        return np.clip(joint_targets, -1.0, 1.0) * math.pi

    def act_stochastic(self, obs: np.ndarray) -> tuple[np.ndarray, float, float]:
        """Return (joint_targets, log_prob, value) for rollout planning."""
        mirrored_obs = mirror_observation(obs)
        obs_t = torch.from_numpy(mirrored_obs).unsqueeze(0).to(self.device)

        with torch.no_grad():
            action, log_prob, value = self.right_policy.act(obs_t, deterministic=False)

        act_np = action.squeeze(0).cpu().numpy()
        joint_targets = mirror_action(act_np)
        return (np.clip(joint_targets, -1.0, 1.0) * math.pi,
                log_prob.item(), value.item())
