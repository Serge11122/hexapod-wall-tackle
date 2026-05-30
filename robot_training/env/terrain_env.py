"""
TerrainTraversalEnv — gymnasium-compatible RL environment.

Wraps TerrainRobotPhysics + LocalMap into a standard reset/step interface.

Observation (OBS_DIM = 39 + 180 = 219):
  [0:8]    joint angles (normalised to [-1,1] within anatomical range)
  [8:16]   joint angular velocities (clipped, normalised)
  [16:24]  joint torques (normalised)
  [24:28]  foot contact flags (binary)
  [28:32]  foot contact forces (normalised)
  [32:36]  foot heights (normalised)
  [36:38]  body velocity vx, vy (normalised)
  [38:39]  body pitch (normalised)
  [39:219] 1D local map window (WINDOW_CELLS × 3)

Action (ACT_DIM = 8):
  action[0,2,4,6]: hip target in [-1,1]  → mapped to [HIP_MIN, HIP_MAX]  (body frame)
  action[1,3,5,7]: knee target in [-1,1] → mapped to [KNEE_MIN, KNEE_MAX] (seg-relative)

Joint constraints (enforced both by RotaryLimitJoint in physics and action clipping):
  Hip:  -125° to +90°   (-2.182 to +1.571 rad) in body frame
  Knee: -170° to  0°   (-2.967 to  0.000 rad) relative to upper segment
  Max velocity: 8°/frame at 5fps = 40°/s = 0.698 rad/s

All gait is entirely model-generated — no hardcoded animation sequences.
"""

import json
import math

import numpy as np

from robot_training.env.terrain_physics import (
    TerrainRobotPhysics, WALK_HEIGHT,
    HIP_MIN, HIP_MAX, KNEE_MIN, KNEE_MAX,
)
from robot_training.env.local_map import LocalMap, OBS_SIZE as MAP_OBS_SIZE
from robot_training.dataset import TerrainEntry

# ── Observation / action dims ──────────────────────────────────────────────────
JOINT_DIM  = 8
VEL_DIM    = 8
TORQ_DIM   = 8
CONT_DIM   = 4
FORC_DIM   = 4
FHGT_DIM   = 4
BVEL_DIM   = 2
PITCH_DIM  = 1
BASE_DIM   = (JOINT_DIM + VEL_DIM + TORQ_DIM + CONT_DIM
              + FORC_DIM + FHGT_DIM + BVEL_DIM + PITCH_DIM)  # 39
OBS_DIM    = BASE_DIM + MAP_OBS_SIZE   # 39 + 180 = 219
ACT_DIM    = 8

# ── Action-space joint mapping ────────────────────────────────────────────────
# action ∈ [-1, 1] maps linearly to anatomical joint angle ranges.
# Hip  (indices 0,2,4,6): [-1,1] → [HIP_MIN, HIP_MAX]
# Knee (indices 1,3,5,7): [-1,1] → [KNEE_MIN, KNEE_MAX]
HIP_CENTER  = (HIP_MAX + HIP_MIN) / 2.0    # mid of hip range
HIP_SCALE   = (HIP_MAX - HIP_MIN) / 2.0    # half-width of hip range
KNEE_CENTER = (KNEE_MAX + KNEE_MIN) / 2.0  # mid of knee range
KNEE_SCALE  = (KNEE_MAX - KNEE_MIN) / 2.0  # half-width of knee range

# Pre-built broadcast arrays for fast vectorised action→joint conversion
_HIP_KNEE_CENTER = np.array([HIP_CENTER, KNEE_CENTER] * 4, dtype=np.float32)
_HIP_KNEE_SCALE  = np.array([HIP_SCALE,  KNEE_SCALE]  * 4, dtype=np.float32)

# ── Normalisation constants ────────────────────────────────────────────────────
# Joint angle obs normalised by the half-range so result ≈ [-1, 1]
HIP_NORM    = HIP_SCALE    # normalise hip obs by half-range
KNEE_NORM   = KNEE_SCALE   # normalise knee obs by half-range
# Pre-built broadcast array for vectorised obs normalisation
_ANGLE_NORM = np.array([HIP_NORM, KNEE_NORM] * 4, dtype=np.float32)

VEL_CLIP     = 5.0    # clip joint angular velocity at ±5 rad/s before normalising
VEL_NORM     = 5.0    # normalise velocity by this value
FORCE_NORM   = 50.0
HEIGHT_NORM  = 3.0
VX_NORM      = 2.0
VY_NORM      = 2.0
PITCH_NORM   = math.pi / 4   # normalise pitch by ±45°

# Keep ANGLE_NORM for planner compatibility
ANGLE_NORM   = math.pi

# ── Episode params ─────────────────────────────────────────────────────────────
MAX_STEPS    = 600    # 120 seconds at 5fps — enough time for constrained walking
FALL_Y       = -0.5   # body COM below terrain_h + this → episode done
FALL_PITCH   = 0.65   # ±37° tilt → fall (realistic for uneven terrain)
SUCCESS_DIST = 25.0
DT           = 1.0 / 5  # 5 fps inference and rendering (matches 8°/frame velocity limit)

# ── Reward shaping ─────────────────────────────────────────────────────────────
PROGRESS_SCALE  = 10.0    # dominant reward: forward progress (must walk to earn reward)
CONTACT_BONUS   = 0.0     # zero contact bonus — prevents standing-still exploitation
ALIVE_BONUS     = 0.02    # tiny per-step alive bonus (walk > stand > fall)
FALL_PENALTY    = -5.0    # fall penalty — not too harsh so robot explores walking
SUCCESS_BONUS   = 100.0

# ── Neutral joint angles for gravity-settling ─────────────────────────────────
# Natural standing pose: hips ~-65° (pointing diagonally down-forward),
# knees ~-85° (bent moderately). Both within anatomical limits.
# These are raw radians passed directly to TerrainRobotPhysics.step().
NEUTRAL_ANGLES = np.array(
    [-1.134, -1.484, -1.134, -1.484, -1.134, -1.484, -1.134, -1.484],
    dtype=np.float32,
)  # hip = -65°, knee = -85° → stable standing within constraints


def action_to_joints(action: np.ndarray) -> np.ndarray:
    """Convert normalised action [-1,1]^8 to joint target angles in radians."""
    return _HIP_KNEE_CENTER + np.clip(action, -1.0, 1.0) * _HIP_KNEE_SCALE


def joints_to_action(joint_targets: np.ndarray) -> np.ndarray:
    """Convert raw joint angles (rad) back to normalised action [-1,1]."""
    return np.clip((joint_targets - _HIP_KNEE_CENTER) / _HIP_KNEE_SCALE, -1.0, 1.0)


class TerrainTraversalEnv:
    """
    Single-terrain episode RL environment.

    Parameters
    ----------
    direction : int   +1 = walk right, -1 = walk left
    dt        : float physics timestep (= 1/FPS)
    """

    def __init__(self, direction: int = 1, dt: float = DT):
        self.direction = direction
        self.dt        = dt
        self._physics: TerrainRobotPhysics | None = None
        self._lmap: LocalMap | None = None
        self._entry: TerrainEntry | None = None
        self._step_count = 0
        self._start_x    = 0.0
        self._prev_x     = 0.0
        self.obs_dim     = OBS_DIM
        self.act_dim     = ACT_DIM

    # ── reset ─────────────────────────────────────────────────────────────────

    def reset(self, entry: TerrainEntry) -> np.ndarray:
        """Reset environment with a new terrain entry.  Returns initial observation."""
        self._entry = entry

        with open(entry.path) as f:
            meta = json.load(f)
        env_left  = meta["env_left"]
        env_right = meta["env_right"]

        # Pick drop location based on direction
        if self.direction > 0:
            sx, sy = entry.drop_left
        else:
            sx, sy = entry.drop_right

        self._physics = TerrainRobotPhysics(
            dt           = self.dt,
            terrain_json = str(entry.path),
            start_x      = sx,
            start_y      = sy,
        )
        self._lmap = LocalMap(env_left=env_left, env_right=env_right)

        # Settling: allow gravity to bring robot down onto terrain naturally.
        # Uses neutral standing joint angles — no hardcoded gait animation.
        for _ in range(25):
            self._physics.step(NEUTRAL_ANGLES)

        self._step_count = 0
        self._start_x    = self._physics.body.position.x
        self._prev_x     = self._start_x
        return self._observe()

    # ── step ──────────────────────────────────────────────────────────────────

    def step(self, action: np.ndarray) -> tuple:
        """
        Apply action, advance physics, return (obs, reward, done, info).
        action: (ACT_DIM,) in [-1, 1]
          hips  (indices 0,2,4,6): mapped to [HIP_MIN, HIP_MAX]
          knees (indices 1,3,5,7): mapped to [KNEE_MIN, KNEE_MAX]
        """
        joint_targets = action_to_joints(action)

        self._physics.step(joint_targets)
        self._step_count += 1

        # Update local map
        for i, leg in enumerate(self._physics.legs):
            fw = leg["lower"].local_to_world((1.2 / 2, 0))
            self._lmap.update_contact(
                foot_x    = fw.x,
                foot_y    = fw.y,
                is_contact = bool(self._physics._foot_contact[i]),
            )

        obs  = self._observe()
        bx, by, bth, vx, vy, omega = self._physics.get_body_state()

        # ── Reward components ─────────────────────────────────────────────────
        # Forward progress: the only major reward — robot must walk to earn it
        dx     = (bx - self._prev_x) * self.direction
        reward = dx * PROGRESS_SCALE
        self._prev_x = bx

        # Tiny alive bonus: ensures surviving > falling (but standing ≪ walking)
        reward += ALIVE_BONUS

        # ── Done conditions ───────────────────────────────────────────────────
        dist  = abs(bx - self._start_x)
        done  = False
        info  = {"dist": dist, "success": False, "fall": False}

        terrain_h = self._physics._terrain_height_est
        pitched_over = abs(bth) > FALL_PITCH
        below_ground = by < terrain_h + FALL_Y

        if pitched_over or below_ground:
            reward     += FALL_PENALTY
            done        = True
            info["fall"] = True
        elif dist >= SUCCESS_DIST:
            reward += SUCCESS_BONUS
            done    = True
            info["success"] = True
        elif self._step_count >= MAX_STEPS:
            done = True

        return obs, reward, done, info

    # ── Observation builder ───────────────────────────────────────────────────

    def _observe(self) -> np.ndarray:
        p = self._physics
        bx, by, bth, vx, vy, omega = p.get_body_state()

        # Joint angles: normalised to [-1, 1] within anatomical range
        # hip  obs ∈ [HIP_MIN, HIP_MAX]  → normalised by HIP_SCALE
        # knee obs ∈ [KNEE_MIN, KNEE_MAX] → normalised by KNEE_SCALE
        angles_norm = (p.obs_joint_angles - _HIP_KNEE_CENTER) / _HIP_KNEE_SCALE

        base = np.concatenate([
            angles_norm,
            np.clip(p.obs_joint_vels, -VEL_CLIP, VEL_CLIP) / VEL_NORM,
            p.obs_joint_torques,
            p.obs_foot_contact,
            np.clip(p.obs_foot_forces, 0, FORCE_NORM) / FORCE_NORM,
            np.clip(p.obs_foot_heights, 0, HEIGHT_NORM) / HEIGHT_NORM,
            np.array([
                np.clip(vx, -VX_NORM, VX_NORM) / VX_NORM,
                np.clip(vy, -VY_NORM, VY_NORM) / VY_NORM,
            ]),
            np.array([bth / PITCH_NORM]),
        ])
        map_obs = self._lmap.get_observation(bx, self.direction)
        return np.concatenate([base, map_obs]).astype(np.float32)

    def render(self) -> dict:
        return self._physics.get_render_pose()


