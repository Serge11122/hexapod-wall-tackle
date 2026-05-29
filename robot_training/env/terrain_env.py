"""
TerrainTraversalEnv — gymnasium-compatible RL environment.

Wraps TerrainRobotPhysics + LocalMap into a standard reset/step interface.

Observation (OBS_DIM = 66 + 180 = 246):
  [0:8]    joint angles (normalised)
  [8:16]   joint angular velocities (clipped, normalised)
  [16:24]  joint torques (normalised)
  [24:28]  foot contact flags (binary)
  [28:32]  foot contact forces (normalised)
  [32:36]  foot heights (normalised)
  [36:38]  body velocity vx, vy (normalised)
  [38:39]  body pitch (normalised)
  [39:246] 1D local map window (WINDOW_CELLS × 3)

Action (ACT_DIM = 8):
  target hip+knee angles for 4 legs, clipped to [-π, π]
"""

import math
import json
from pathlib import Path

import numpy as np

from robot_training.env.terrain_physics import TerrainRobotPhysics, WALK_HEIGHT
from robot_training.env.local_map import LocalMap, OBS_SIZE as MAP_OBS_SIZE
from robot_training.dataset import TerrainEntry

# ── Observation / action dims ──────────────────────────────────────────────────
JOINT_DIM  = 8    # angles
VEL_DIM    = 8    # joint vels
TORQ_DIM   = 8    # torques
CONT_DIM   = 4    # contact flags
FORC_DIM   = 4    # contact forces
FHGT_DIM   = 4    # foot heights
BVEL_DIM   = 2    # body vx,vy
PITCH_DIM  = 1    # body pitch
BASE_DIM   = (JOINT_DIM + VEL_DIM + TORQ_DIM + CONT_DIM
              + FORC_DIM + FHGT_DIM + BVEL_DIM + PITCH_DIM)  # 39
OBS_DIM    = BASE_DIM + MAP_OBS_SIZE   # 39 + 180 = 219
ACT_DIM    = 8

# ── Normalisation constants ────────────────────────────────────────────────────
ANGLE_NORM   = math.pi
VEL_CLIP     = 10.0
FORCE_NORM   = 50.0
HEIGHT_NORM  = 3.0
VX_NORM      = 3.0
VY_NORM      = 3.0
PITCH_NORM   = ANGLE_NORM

# ── Episode params ─────────────────────────────────────────────────────────────
MAX_STEPS       = 500
FALL_Y          = 0.2     # body COM below this → episode done (fell)
SUCCESS_DIST    = 25.0    # body moved this far → success
DT              = 1.0 / 5   # 5 fps render rate

# ── Reward shaping ─────────────────────────────────────────────────────────────
PROGRESS_SCALE  = 2.0
ALIVE_BONUS     = 0.05
FALL_PENALTY    = -20.0
SUCCESS_BONUS   = 50.0
HEIGHT_PEN_GAIN = 3.0   # penalty for deviating too much from walk height


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

        # Settling steps
        from robot_motion.body import LEG_MOUNTS
        import json as _json
        gait_name = "right" if self.direction > 0 else "left"
        gait_path = Path(__file__).parent.parent.parent / "robot_motion" / f"gait_{gait_name}.json"
        with open(gait_path) as f:
            gait = _json.load(f)["frames"]
        settle_action = _gait_frame_to_action(gait[0])
        for _ in range(4):
            self._physics.step(settle_action)

        self._step_count = 0
        self._start_x    = self._physics.body.position.x
        self._prev_x     = self._start_x
        return self._observe()

    # ── step ──────────────────────────────────────────────────────────────────

    def step(self, action: np.ndarray) -> tuple:
        """
        Apply action, advance physics, return (obs, reward, done, info).
        action: (ACT_DIM,) in [-1, 1] — scaled to joint angle ranges.
        """
        # Scale action from [-1,1] to actual joint angle range
        joint_targets = np.clip(action, -1.0, 1.0) * math.pi

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

        # Reward
        dx       = (bx - self._prev_x) * self.direction
        progress = dx * PROGRESS_SCALE
        alive    = ALIVE_BONUS
        height_dev = abs(by - (self._physics._terrain_height_est + WALK_HEIGHT))
        h_pen    = -HEIGHT_PEN_GAIN * max(0.0, height_dev - 0.5)
        reward   = progress + alive + h_pen
        self._prev_x = bx

        # Done conditions
        dist  = abs(bx - self._start_x)
        done  = False
        info  = {"dist": dist, "success": False, "fall": False}

        if by < FALL_Y:
            reward += FALL_PENALTY
            done    = True
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

        base = np.concatenate([
            p.obs_joint_angles   / ANGLE_NORM,
            np.clip(p.obs_joint_vels, -VEL_CLIP, VEL_CLIP) / VEL_CLIP,
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gait_frame_to_action(frame: dict) -> np.ndarray:
    """Convert a gait JSON frame to an 8-element target joint angles array."""
    angles = np.zeros(8, dtype=np.float32)
    for leg in frame["legs"]:
        i = leg["id"]
        angles[2 * i]     = leg["theta1"]
        angles[2 * i + 1] = leg["theta2"]
    return angles
