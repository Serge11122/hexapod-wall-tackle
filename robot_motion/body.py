"""Robot body definition: geometry, mass, friction params, contact points."""
import math
import numpy as np


# ── Body geometry ─────────────────────────────────────────────────────────────

BODY_HALF_LEN = 1.0       # body half-length (world units)
BODY_HALF_H   = 0.2       # body half-height
LEG_L1        = 1.0       # upper leg segment length
LEG_L2        = 1.2       # lower leg segment length

# Leg mount points in body-local frame (x, side)
#  id 0 = front-right, id 1 = front-left, id 2 = rear-right, id 3 = rear-left
LEG_MOUNTS = [
    {"id": 0, "local_x":  1.0, "side": "front-right"},
    {"id": 1, "local_x":  1.0, "side": "front-left"},
    {"id": 2, "local_x": -1.0, "side": "rear-right"},
    {"id": 3, "local_x": -1.0, "side": "rear-left"},
]

# ── Physics params ────────────────────────────────────────────────────────────

BODY_MASS         = 2.0     # kg (normalised units)
LEG_SEGMENT_MASS  = 0.15    # per segment
TOTAL_MASS        = BODY_MASS + len(LEG_MOUNTS) * 2 * LEG_SEGMENT_MASS

GRAVITY           = 9.8     # m/s² downward

# Contact / friction
FOOT_RADIUS         = 0.05   # radius of spherical foot for friction area
STATIC_FRICTION     = 1.2    # μs  foot–ground (boosted grip)
DYNAMIC_FRICTION    = 0.6    # μk  foot–ground
WALL_FRICTION       = 0.4    # μ   foot–wall
RESTITUTION         = 0.05   # coefficient of restitution for collisions
COLLISION_TOLERANCE = 1e-4   # penetration depth below which constraint satisfied

# Leg torque / force limits (not enforced in kinematics-driven mode)
MAX_JOINT_TORQUE    = 5.0    # N·m
MAX_FOOT_FORCE      = 20.0   # N per foot


# ── Geometry helpers ──────────────────────────────────────────────────────────

def rot2(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


def body_corners(body_xy: np.ndarray, theta: float) -> list[np.ndarray]:
    """Return 4 body rectangle corners in world frame (top-right, top-left, bot-left, bot-right)."""
    R = rot2(theta)
    locals_ = [
        np.array([ BODY_HALF_LEN,  BODY_HALF_H]),
        np.array([-BODY_HALF_LEN,  BODY_HALF_H]),
        np.array([-BODY_HALF_LEN, -BODY_HALF_H]),
        np.array([ BODY_HALF_LEN, -BODY_HALF_H]),
    ]
    return [body_xy + R @ v for v in locals_]


def body_boundary_points(body_xy: np.ndarray, theta: float, n_per_side: int = 5) -> list[np.ndarray]:
    """Sample n_per_side points along each of the 4 edges (used for collision detection)."""
    corners = body_corners(body_xy, theta)
    pts = []
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        for t in np.linspace(0.0, 1.0, n_per_side, endpoint=False):
            pts.append(a + t * (b - a))
    return pts


def leg_fk(body_xy: np.ndarray, body_theta: float,
           mount_local_x: float, theta1: float, theta2: float):
    """Forward kinematics → (mount_w, knee_w, foot_w) in world frame."""
    R = rot2(body_theta)
    mount_w = body_xy + R @ np.array([mount_local_x, 0.0])
    knee_angle = body_theta + theta1
    knee_w = mount_w + LEG_L1 * np.array([math.cos(knee_angle), math.sin(knee_angle)])
    foot_angle = knee_angle + theta2
    foot_w = knee_w + LEG_L2 * np.array([math.cos(foot_angle), math.sin(foot_angle)])
    return mount_w, knee_w, foot_w


def all_contact_points(pose: dict) -> list[np.ndarray]:
    """Return foot world positions for all legs in a pose dict."""
    bxy = np.array([pose["body"]["x"], pose["body"]["y"]])
    bth = pose["body"]["theta"]
    pts = []
    for leg in pose["legs"]:
        mx = LEG_MOUNTS[leg["id"]]["local_x"]
        _, _, fw = leg_fk(bxy, bth, mx, leg["theta1"], leg["theta2"])
        pts.append(fw)
    return pts
