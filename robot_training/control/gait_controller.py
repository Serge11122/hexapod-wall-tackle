"""
Contact-based static-crawl gait controller for the 2-D legged robot.

This is a *model* of locomotion: it senses the environment through foot contact
and terrain probing, plans foot placements (motion planning), and executes them
through 2-link inverse kinematics that the joint motors track (motion
execution).  It produces real walking in the corrected physics where the body
is supported solely by leg contact forces — no levitation, no magic pitch lock.

Two hard-won design principles encoded here (see commit history / dev notes):

1. Command only SMALL deviations from the geometrically-consistent pose.
   When a foot is planted, the body↔foot geometry already fixes the leg's
   length and orientation.  Commanding hip/knee angles that disagree with that
   geometry over-constrains the closed chain and saturates the motors, which
   then inject chaotic forces.  So every stance target starts from the *actual*
   current foot position and adds only a tiny creep — never a large absolute
   target.

2. Control height with a FIXED depth (foot below hip), not by tracking a world
   foothold's y.  Tracking world-y has positive feedback (body sags → IK asks
   for a shorter leg → more sag → collapse).  A fixed depth is negative feedback
   and self-regulates the body to a constant height above whatever the foot
   rests on — this is also how the robot follows uneven terrain.

Static crawl (lift one leg at a time, duty 0.75, quarter-phase offsets) keeps
three feet down at all times — always ≥1 front and ≥1 rear foot — so the centre
of mass stays over the front↔rear support segment and the body is pitch-stable.
"""

import math
import numpy as np

from robot_motion.body import LEG_L1, LEG_L2, rot2
from robot_training.env.terrain_physics import (
    HIP_MIN, HIP_MAX, KNEE_MIN, KNEE_MAX, WALK_HEIGHT,
)
from robot_training.env.terrain_loader import terrain_height_at

# ── Gait parameters ────────────────────────────────────────────────────────────
DUTY          = 0.75    # stance fraction → exactly one leg in swing at a time
CYCLE_STEPS   = 56      # env steps per full gait cycle (slower = more stable)
CREEP         = 0.045   # backward foot creep per step during stance → propulsion
SWING_REACH   = 1.0     # how far ahead a swing foot is planted (relative to hip)
SWING_HEIGHT  = 0.5     # peak foot lift during swing
STANCE_DEPTH  = WALK_HEIGHT   # nominal body height above the foot

# Quarter-phase offsets keyed by leg id.  Swing order rear-right, front-left,
# rear-left, front-right → never two feet of the same end lifted together.
#   leg ids: 0 front-right, 1 front-left, 2 rear-right, 3 rear-left
PHASE_OFFSET = {2: 0.00, 1: 0.25, 3: 0.50, 0: 0.75}

PITCH_GAIN  = 0.9     # foot-depth trim per radian of body pitch (levelling)

# Stance propulsion: planting the foot a small distance AHEAD of the hip (in the
# walk direction) shears the body forward through friction.  The required offset
# is small and sensitive, so it is servo-controlled to hold a target body speed.
OFFSET_MIN   = 0.05
OFFSET_MAX   = 0.34
OFFSET_KP    = 0.30   # offset servo gain on body-speed error
OFFSET_INIT  = 0.20   # empirically near the forward-crawl sweet spot

_REACH_MIN = abs(LEG_L1 - LEG_L2) + 0.08
_REACH_MAX = (LEG_L1 + LEG_L2) - 0.06


def leg_ik(fx: float, fy: float) -> tuple:
    """
    2-link inverse kinematics in the body frame.

    (fx, fy) = desired foot position relative to the hip mount (body axes).
    Returns (theta1, theta2): upper angle relative to body, knee angle relative
    to upper (folds negative).  Clamped to the anatomical joint limits.
    """
    r = math.hypot(fx, fy)
    ang = math.atan2(fy, fx)
    r = min(max(r, _REACH_MIN), _REACH_MAX)
    cos_knee = (r * r - LEG_L1 * LEG_L1 - LEG_L2 * LEG_L2) / (2 * LEG_L1 * LEG_L2)
    cos_knee = min(1.0, max(-1.0, cos_knee))
    theta2   = -math.acos(cos_knee)                       # knee folds backward
    beta     = math.atan2(LEG_L2 * math.sin(theta2),
                          LEG_L1 + LEG_L2 * math.cos(theta2))
    theta1   = ang - beta
    theta1 = min(HIP_MAX,  max(HIP_MIN,  theta1))
    theta2 = min(KNEE_MAX, max(KNEE_MIN, theta2))
    return theta1, theta2


class GaitController:
    """Stateful deviation-based static-crawl controller."""

    def __init__(self, direction: int = 1,
                 cycle_steps: int = CYCLE_STEPS,
                 creep: float = CREEP,
                 swing_reach: float = SWING_REACH,
                 swing_height: float = SWING_HEIGHT,
                 stance_depth: float = STANCE_DEPTH,
                 target_speed: float = 0.18):
        assert direction in (1, -1), "direction must be +1 or -1"
        self.direction    = direction
        self.cycle_steps  = int(cycle_steps)
        self.creep        = float(creep)
        self.swing_reach  = float(swing_reach)
        self.swing_height = float(swing_height)
        self.stance_depth = float(stance_depth)
        self.target_speed = float(target_speed)   # desired body speed (units/s)
        self._t           = 0
        self._offset      = OFFSET_INIT           # servo'd stance forward offset
        self._liftoff     = None    # per-leg world (x,y) at start of swing
        self._was_swing   = None

    def reset(self, phys=None) -> None:
        self._t = 0
        self._offset    = OFFSET_INIT
        self._liftoff   = {}
        self._was_swing = {}
        if phys is not None:
            for leg in phys.legs:
                fw = leg["lower"].local_to_world((LEG_L2 / 2, 0))
                self._liftoff[leg["id"]]   = np.array([fw.x, fw.y])
                self._was_swing[leg["id"]] = False

    # ── helpers ─────────────────────────────────────────────────────────────
    def _hip_world(self, bx, by, bth, mount_x):
        off = rot2(bth) @ np.array([mount_x, 0.0])
        return np.array([bx + off[0], by + off[1]])

    def _leg_phase(self, leg_id, phase):
        s = (phase + PHASE_OFFSET[leg_id]) % 1.0
        swing = s >= DUTY
        u = (s / DUTY) if not swing else ((s - DUTY) / (1.0 - DUTY))
        return swing, u

    def hold(self, phys) -> np.ndarray:
        """Stand in place: every foot holds its consistent pose, no creep."""
        return self.act(phys, advance=False)

    # ── main control ─────────────────────────────────────────────────────────
    def act(self, phys, lmap=None, advance: bool = True) -> np.ndarray:
        if self._liftoff is None:
            self.reset(phys)

        bx, by, bth, vx, vy, om = phys.get_body_state()
        phase = (self._t / self.cycle_steps) % 1.0

        # Body-pitch levelling trim (front feet shallower / rear deeper when
        # nose-up).
        pitch_trim = max(-0.35, min(0.35, PITCH_GAIN * bth))

        # Servo the stance forward-offset to hold the target body speed.
        body_speed = vx * self.direction
        if advance:
            self._offset += OFFSET_KP * (self.target_speed - body_speed) * 0.2
            self._offset = min(OFFSET_MAX, max(OFFSET_MIN, self._offset))
        offset = self._offset if advance else 0.0

        targets = np.zeros(8, dtype=np.float32)
        for i, leg in enumerate(phys.legs):
            leg_id  = leg["id"]
            mount_x = leg["mount_x"]
            swing, u = (False, 0.0) if not advance else self._leg_phase(leg_id, phase)

            hip = self._hip_world(bx, by, bth, mount_x)
            fw  = leg["lower"].local_to_world((LEG_L2 / 2, 0))
            foot_actual = np.array([fw.x, fw.y])

            if swing and not self._was_swing[leg_id]:
                self._liftoff[leg_id] = foot_actual.copy()
            self._was_swing[leg_id] = swing

            if not swing:
                # STANCE: foot held a small offset AHEAD of the hip (in the walk
                # direction) so friction shears the body forward; FIXED depth
                # below the hip self-regulates the body height.
                fx = self.direction * offset
                depth = self.stance_depth + (1.0 if mount_x > 0 else -1.0) * pitch_trim
                fy = -depth
            else:
                # SWING: arc the lifted foot forward to a fresh foothold one
                # reach ahead, planted on the sensed terrain surface.
                land_x = hip[0] + self.direction * self.swing_reach
                land_y = terrain_height_at(phys._terrain_segs, land_x)
                lo     = self._liftoff[leg_id]
                fx_w   = lo[0] + (land_x - lo[0]) * u
                fy_w   = lo[1] + (land_y - lo[1]) * u + self.swing_height * math.sin(math.pi * u)
                d_body = rot2(-bth) @ (np.array([fx_w, fy_w]) - hip)
                fx, fy = float(d_body[0]), float(d_body[1])

            t1, t2 = leg_ik(fx, fy)
            targets[2 * i]     = t1
            targets[2 * i + 1] = t2

        if advance:
            self._t += 1
        return targets
