"""
Physics-based rollout planner for terrain traversal.

At each decision step the planner:
  1. Generates N candidate first actions from the policy (stochastic sampling)
  2. Simulates each candidate forward K steps using the real physics engine
     (using the deterministic policy for steps 2…K)
  3. Scores each trajectory: discounted sum of rewards + value-head bootstrap
  4. Applies the best-scoring first action to the real environment

This gives genuine multi-step reasoning about the terrain:
  - Physical consequences of actions are computed exactly (no approximation)
  - Value function bootstraps beyond the lookahead horizon
  - Contact-based local map is updated during simulation
  - Terrain hazards (gaps, obstacles) are detected from foot contacts

No hardcoded gait — every action is sampled from the neural network policy.
"""

import math
from pathlib import Path

import numpy as np
import torch

from robot_training.env.terrain_physics import TerrainRobotPhysics
from robot_training.env.local_map import LocalMap, RESOLUTION
from robot_training.env.terrain_env import (
    ANGLE_NORM, VEL_CLIP, VEL_NORM, FORCE_NORM, HEIGHT_NORM,
    VX_NORM, VY_NORM, PITCH_NORM, PROGRESS_SCALE, FALL_Y, FALL_PITCH,
    ALIVE_BONUS, FALL_PENALTY,
    PITCH_PENALTY, PITCH_DEADBAND, OMEGA_PENALTY, VY_PENALTY,
    _HIP_KNEE_CENTER, _HIP_KNEE_SCALE, action_to_joints, joints_to_action,
)
from robot_training.models.policy import LSTMActorCritic

LEG_L2 = 1.2

# Planner configuration
N_CANDIDATES  = 12   # candidate first actions sampled per step
LOOKAHEAD     = 4    # physics steps simulated per candidate
GAMMA         = 0.95 # discount factor for simulated rewards


def _build_obs(phys: TerrainRobotPhysics, lmap: LocalMap, direction: int) -> np.ndarray:
    """Build observation vector matching terrain_env.py format."""
    bx, by, bth, vx, vy, omega = phys.get_body_state()
    angles_norm = (phys.obs_joint_angles - _HIP_KNEE_CENTER) / _HIP_KNEE_SCALE
    base = np.concatenate([
        angles_norm,
        np.clip(phys.obs_joint_vels, -VEL_CLIP, VEL_CLIP) / VEL_NORM,
        phys.obs_joint_torques,
        phys.obs_foot_contact,
        np.clip(phys.obs_foot_forces, 0, FORCE_NORM) / FORCE_NORM,
        np.clip(phys.obs_foot_heights, 0, HEIGHT_NORM) / HEIGHT_NORM,
        np.array([np.clip(vx, -VX_NORM, VX_NORM) / VX_NORM,
                  np.clip(vy, -VY_NORM, VY_NORM) / VY_NORM]),
        np.array([bth / PITCH_NORM]),
    ])
    for i, leg in enumerate(phys.legs):
        fw = leg["lower"].local_to_world((LEG_L2 / 2, 0))
        lmap.update_contact(fw.x, fw.y, bool(phys._foot_contact[i]))
    map_obs = lmap.get_observation(bx, direction)
    return np.concatenate([base, map_obs]).astype(np.float32)


def _step_reward(phys: TerrainRobotPhysics, prev_x: float, direction: int) -> tuple:
    """Compute reward after a physics step. Returns (reward, done, new_x)."""
    bx, by, bth, vx, vy, omega = phys.get_body_state()
    dx = (bx - prev_x) * direction
    reward = dx * PROGRESS_SCALE + ALIVE_BONUS

    # Gracefulness shaping (state-based, matches terrain_env) — makes the
    # lookahead prefer level, smooth trajectories over lurching ones.
    reward -= PITCH_PENALTY * max(0.0, abs(bth) - PITCH_DEADBAND)
    reward -= OMEGA_PENALTY * abs(omega)
    reward -= VY_PENALTY    * abs(vy)

    terrain_h = phys._terrain_height_est
    done = (abs(bth) > FALL_PITCH) or (by < terrain_h + FALL_Y)
    if done:
        reward += FALL_PENALTY

    return reward, done, bx


def _snapshot_physics(phys: TerrainRobotPhysics) -> dict:
    """Snapshot all physics body states for rollout restore."""
    return {
        "body_pos":   (phys.body.position.x, phys.body.position.y),
        "body_vel":   (phys.body.velocity.x, phys.body.velocity.y),
        "body_angle": phys.body.angle,
        "body_omega": phys.body.angular_velocity,
        "terrain_est": phys._terrain_height_est,
        "contacts":   list(phys._foot_contact),
        "legs": [{
            "upper_pos":   (leg["upper"].position.x, leg["upper"].position.y),
            "upper_vel":   (leg["upper"].velocity.x, leg["upper"].velocity.y),
            "upper_angle": leg["upper"].angle,
            "upper_omega": leg["upper"].angular_velocity,
            "lower_pos":   (leg["lower"].position.x, leg["lower"].position.y),
            "lower_vel":   (leg["lower"].velocity.x, leg["lower"].velocity.y),
            "lower_angle": leg["lower"].angle,
            "lower_omega": leg["lower"].angular_velocity,
        } for leg in phys.legs]
    }


def _restore_physics(phys: TerrainRobotPhysics, state: dict) -> None:
    """Restore physics to a saved snapshot."""
    bx, by = state["body_pos"]
    phys.body.position = (bx, by)
    vx, vy = state["body_vel"]
    phys.body.velocity = (vx, vy)
    phys.body.angle            = state["body_angle"]
    phys.body.angular_velocity = state["body_omega"]
    phys._terrain_height_est   = state["terrain_est"]
    phys._foot_contact         = list(state["contacts"])
    for i, leg in enumerate(phys.legs):
        ls = state["legs"][i]
        leg["upper"].position          = ls["upper_pos"]
        leg["upper"].velocity          = ls["upper_vel"]
        leg["upper"].angle             = ls["upper_angle"]
        leg["upper"].angular_velocity  = ls["upper_omega"]
        leg["lower"].position          = ls["lower_pos"]
        leg["lower"].velocity          = ls["lower_vel"]
        leg["lower"].angle             = ls["lower_angle"]
        leg["lower"].angular_velocity  = ls["lower_omega"]


def _save_lmap(lmap: LocalMap) -> dict:
    return {
        "known_height": lmap.known_height.copy(),
        "is_gap":       lmap.is_gap.copy(),
    }


def _restore_lmap(lmap: LocalMap, state: dict) -> None:
    lmap.known_height[:] = state["known_height"]
    lmap.is_gap[:]       = state["is_gap"]


class RolloutPlanner:
    """
    Physics-based rollout planner for LSTM policies.

    Generates N candidate first actions from the stochastic policy,
    simulates each K steps forward using real physics, scores by discounted
    cumulative reward + value-head bootstrap, applies the best first action.

    The LSTM hidden state is maintained across real steps and reset per episode.
    During lookahead simulation, a fresh hidden state is used so simulated
    paths don't contaminate the real hidden state.

    Parameters
    ----------
    policy       : trained LSTMActorCritic
    device       : torch device
    n_candidates : candidate first actions per step (default 12)
    lookahead    : physics steps simulated per candidate (default 4)
    """

    def __init__(self, policy: LSTMActorCritic, device: torch.device,
                 n_candidates: int = N_CANDIDATES, lookahead: int = LOOKAHEAD):
        self.policy       = policy
        self.device       = device
        self.n_candidates = n_candidates
        self.lookahead    = lookahead
        # Persistent LSTM state for the real trajectory
        self._lstm_state  = policy.init_hidden(1)
        # Previous applied action — used to penalise abrupt action changes so
        # the deployed gait is smooth/graceful rather than jittery.
        self._prev_action = None
        self.continuity_penalty = 2.0   # weight on mean-squared action change

    def reset_hidden(self) -> None:
        """Reset LSTM hidden state at the start of a new episode."""
        self._lstm_state = self.policy.init_hidden(1)
        self._prev_action = None

    def act(self, obs: np.ndarray, phys: TerrainRobotPhysics,
            lmap: LocalMap, direction: int) -> np.ndarray:
        """
        Choose best action via physics-simulated rollout.
        Updates the internal LSTM hidden state for the chosen (real) step.
        Returns joint_targets in radians (8,).
        """
        obs_t = torch.from_numpy(obs).unsqueeze(0).to(self.device)

        self.policy.eval()
        with torch.no_grad():
            # Sample N stochastic candidates using CURRENT hidden state
            candidates = []
            for _ in range(self.n_candidates):
                # Each candidate uses the same current lstm_state (not advanced)
                action, log_prob, value, _ = self.policy.act(
                    obs_t, self._lstm_state, deterministic=False)
                candidates.append((
                    action.squeeze(0).cpu().numpy(),
                    value.item(),
                    log_prob.item(),
                ))
            # Also include deterministic (greedy) action
            det_action, _, det_value, _ = self.policy.act(
                obs_t, self._lstm_state, deterministic=True)
            candidates.append((det_action.squeeze(0).cpu().numpy(), det_value.item(), 0.0))

        if self.lookahead <= 0:
            # No physics simulation: pick best by value head
            best_score  = -1e9
            best_action = candidates[-1][0]
            for act_np, value_est, lp in candidates:
                score = value_est + 0.05 * lp
                if score > best_score:
                    best_score  = score
                    best_action = act_np
            # Advance real LSTM state with chosen action
            with torch.no_grad():
                _, _, _, self._lstm_state = self.policy.act(
                    obs_t, self._lstm_state, deterministic=True)
            return action_to_joints(best_action)

        # ── Physics-based lookahead ───────────────────────────────────────────
        phys_state = _snapshot_physics(phys)
        lmap_state = _save_lmap(lmap)

        best_score  = -1e9
        best_action = candidates[-1][0]

        with torch.no_grad():
            for first_action_np, first_value, first_lp in candidates:
                _restore_physics(phys, phys_state)
                _restore_lmap(lmap, lmap_state)

                # Use a fresh LSTM state for simulation (don't contaminate real state)
                sim_lstm = self.policy.init_hidden(1)

                total_reward  = 0.0
                prev_x        = phys.body.position.x
                joint_targets = action_to_joints(first_action_np)
                done          = False

                for step_i in range(self.lookahead):
                    phys.step(joint_targets)
                    reward, done, prev_x = _step_reward(phys, prev_x, direction)
                    total_reward += (GAMMA ** step_i) * reward
                    if done:
                        break

                    # Advance simulated LSTM state and get next action
                    next_obs   = _build_obs(phys, lmap, direction)
                    next_obs_t = torch.from_numpy(next_obs).unsqueeze(0).to(self.device)
                    next_act, _, next_val, sim_lstm = self.policy.act(
                        next_obs_t, sim_lstm, deterministic=True)
                    joint_targets = action_to_joints(
                        next_act.squeeze(0).cpu().numpy())

                    if step_i == self.lookahead - 2 and not done:
                        total_reward += (GAMMA ** (step_i + 1)) * next_val.item()

                # Continuity: penalise jumping away from the last applied action
                # so the deployed gait is smooth/graceful, not jittery.
                if self._prev_action is not None:
                    d = first_action_np - self._prev_action
                    total_reward -= self.continuity_penalty * float(np.mean(d * d))

                if total_reward > best_score:
                    best_score  = total_reward
                    best_action = first_action_np

        # Restore real physics state
        _restore_physics(phys, phys_state)
        _restore_lmap(lmap, lmap_state)

        # Advance the REAL LSTM state with the chosen first action
        with torch.no_grad():
            _, _, _, self._lstm_state = self.policy.act(
                obs_t, self._lstm_state, deterministic=True)

        self._prev_action = best_action
        return action_to_joints(best_action)
