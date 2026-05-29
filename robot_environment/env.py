"""
2D physics environment: rectangular enclosure (left wall, floor, right wall).
Dimensions: 4× wider than tall.  No ceiling.

Coordinate system: x = right, y = up.  Inward normals on all segments.
"""
import math
import numpy as np
from robot_motion.body import (
    GRAVITY, TOTAL_MASS, STATIC_FRICTION, DYNAMIC_FRICTION, RESTITUTION,
    COLLISION_TOLERANCE, FOOT_RADIUS,
)


# ── Environment geometry ──────────────────────────────────────────────────────

ENV_HEIGHT = 6.0
ENV_WIDTH  = 4.0 * ENV_HEIGHT      # 24 world units wide
ENV_LEFT   = -ENV_WIDTH / 2.0      # -12
ENV_RIGHT  =  ENV_WIDTH / 2.0      # +12
ENV_FLOOR  = 0.0                   # y = 0 is the floor
ENV_TOP    = ENV_HEIGHT            # y = 6 (open — no ceiling)

# Three boundary segments: (start, end, inward_normal)
SEGMENTS = [
    {
        "id": "floor",
        "start": np.array([ENV_LEFT,  ENV_FLOOR]),
        "end":   np.array([ENV_RIGHT, ENV_FLOOR]),
        "normal": np.array([0.0, 1.0]),    # pointing up
    },
    {
        "id": "left_wall",
        "start": np.array([ENV_LEFT, ENV_FLOOR]),
        "end":   np.array([ENV_LEFT, ENV_TOP]),
        "normal": np.array([1.0, 0.0]),    # pointing right
    },
    {
        "id": "right_wall",
        "start": np.array([ENV_RIGHT, ENV_FLOOR]),
        "end":   np.array([ENV_RIGHT, ENV_TOP]),
        "normal": np.array([-1.0, 0.0]),   # pointing left
    },
]


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _seg_dir(seg: dict) -> np.ndarray:
    d = seg["end"] - seg["start"]
    return d / np.linalg.norm(d)


def _point_to_segment_dist_signed(point: np.ndarray, seg: dict) -> float:
    """
    Signed distance from point to infinite line containing segment,
    positive = on the inward-normal side.
    Returns (signed_dist, param_t) where t ∈ [0,1] is the closest point param.
    """
    d = seg["end"] - seg["start"]
    n = seg["normal"]
    return float(np.dot(point - seg["start"], n))


def _closest_point_on_segment(point: np.ndarray, seg: dict):
    """Return closest point on segment and the signed penetration depth (positive = outside)."""
    s = seg["start"]
    e = seg["end"]
    d = e - s
    t = np.dot(point - s, d) / np.dot(d, d)
    t = max(0.0, min(1.0, t))
    closest = s + t * d
    penetration = float(np.dot(seg["normal"], closest - point))  # positive when inside wall
    return closest, penetration


# ── Physics state ─────────────────────────────────────────────────────────────

class RobotState:
    """Minimal rigid-body state for the robot COM."""
    __slots__ = ("pos", "vel", "theta", "omega", "mass")

    def __init__(self, pos: np.ndarray, vel: np.ndarray,
                 theta: float = 0.0, omega: float = 0.0,
                 mass: float = TOTAL_MASS):
        self.pos   = pos.copy()
        self.vel   = vel.copy()
        self.theta = theta
        self.omega = omega
        self.mass  = mass


# ── Physics engine ────────────────────────────────────────────────────────────

class PhysicsEngine:
    """
    Simple 2D rigid-body physics engine.

    Each frame:
      1. Integrate velocity/position (explicit Euler + gravity).
      2. Detect point–segment collisions for all contact points.
      3. Resolve penetrations (positional correction).
      4. Apply impulse-based velocity response.
      5. Apply friction at each planted foot.
    """

    def __init__(self, dt: float = 0.2):
        self.dt = dt
        self.gravity = np.array([0.0, -GRAVITY])

    def step(self, state: RobotState, contact_points: list[np.ndarray],
             planted_mask: list[bool], locomotion_force: np.ndarray) -> RobotState:
        """
        Advance state by one timestep.

        contact_points : list of world-frame foot/body positions
        planted_mask   : True if that contact point is a planted foot
        locomotion_force : net horizontal force from leg actuation
        Returns updated RobotState (mutates in place and returns self).
        """
        dt = self.dt

        # 1. Apply gravity + locomotion force
        accel = self.gravity + locomotion_force / state.mass
        state.vel = state.vel + accel * dt
        state.pos = state.pos + state.vel * dt

        # 2. Collision detection + resolution (iterative, up to 5 passes)
        for _ in range(5):
            resolved = False
            for pt in contact_points:
                for seg in SEGMENTS:
                    closest, penetration = _closest_point_on_segment(pt, seg)
                    if penetration > COLLISION_TOLERANCE:
                        # Positional correction: push body out along segment normal
                        state.pos = state.pos + seg["normal"] * penetration
                        resolved = True

                        # Velocity response (impulse)
                        vn = float(np.dot(state.vel, seg["normal"]))
                        if vn < 0:   # moving into surface
                            state.vel = state.vel - (1.0 + RESTITUTION) * vn * seg["normal"]
            if not resolved:
                break

        # 3. Friction from planted feet
        n_planted = sum(planted_mask)
        if n_planted > 0:
            # Normal force per foot = body weight / n_planted
            fn_per_foot = state.mass * GRAVITY / max(n_planted, 1)
            fric_limit  = STATIC_FRICTION * fn_per_foot * n_planted
            vx = state.vel[0]
            # Apply friction as velocity damping (opposing horizontal motion)
            fric_impulse = -min(abs(vx) * state.mass, fric_limit * dt) * math.copysign(1.0, vx)
            state.vel[0] = state.vel[0] + fric_impulse / state.mass

        # Clamp inside env horizontally (hard wall)
        if state.pos[0] < ENV_LEFT + 0.1:
            state.pos[0] = ENV_LEFT + 0.1
            state.vel[0] = max(0.0, state.vel[0])
        if state.pos[0] > ENV_RIGHT - 0.1:
            state.pos[0] = ENV_RIGHT - 0.1
            state.vel[0] = min(0.0, state.vel[0])

        return state


# ── Drop helper ───────────────────────────────────────────────────────────────

def make_initial_state(drop_height: float = 2.0, walk_height: float = 1.9) -> RobotState:
    """Drop robot from centre of environment at drop_height above walking height."""
    body_y = walk_height + drop_height
    return RobotState(
        pos=np.array([0.0, body_y]),
        vel=np.array([0.0, 0.0]),
    )
