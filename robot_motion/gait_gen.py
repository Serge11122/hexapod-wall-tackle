"""
Generate loopable walk-left and walk-right gait keyframe JSON files.

Walk uses an alternating-tripod (trot) gait:
  Group A = legs 0 (front-right) + 3 (rear-left)
  Group B = legs 1 (front-left)  + 2 (rear-right)
8 keyframes per cycle = one complete stride loop.

Angles computed analytically from foot target positions via 2-link IK.
"""
import math
import json
import numpy as np
from pathlib import Path

HERE = Path(__file__).parent

# Body stays level and at fixed height above ground.
# Environment floor is at y=0; body COM is ~1.9 above (L1+L2 vectors hang down at angle)
BODY_Y      = 1.9      # body centre height above floor
BODY_THETA  = 0.0

# IK parameters
L1, L2 = 1.0, 1.2
FLOOR_Y = 0.0           # ground level in environment
STEP_HEIGHT = 0.5       # swing arc lift above floor


def ik2(mount_w: np.ndarray, target: np.ndarray, body_theta: float):
    """
    2R IK: given mount_world, target_world, body_theta → (theta1, theta2).
    Returns angles such that leg_fk reproduces target (within tolerance).
    Raises ValueError if target unreachable.
    """
    dx, dy = target - mount_w
    dist = math.hypot(dx, dy)
    if dist > L1 + L2 - 1e-6:
        dist = L1 + L2 - 1e-6
    if dist < abs(L1 - L2) + 1e-6:
        dist = abs(L1 - L2) + 1e-6

    cos_a2 = (dist**2 - L1**2 - L2**2) / (2 * L1 * L2)
    cos_a2 = max(-1.0, min(1.0, cos_a2))
    alpha2 = -math.acos(cos_a2)   # elbow-down convention

    global_angle = math.atan2(dy, dx)
    beta = math.atan2(L2 * math.sin(alpha2), L1 + L2 * math.cos(alpha2))
    alpha1_global = global_angle - beta
    theta1 = alpha1_global - body_theta
    theta2 = alpha2
    return theta1, theta2


def make_pose(body_x: float, foot_targets: list[tuple[float, float]],
              planted: list[int], free: list[int]) -> dict:
    bxy = np.array([body_x, BODY_Y])
    mount_locals = [1.0, 1.0, -1.0, -1.0]
    legs = []
    for lid, (tx, ty) in enumerate(foot_targets):
        mount_w = bxy + np.array([mount_locals[lid], 0.0])
        t1, t2 = ik2(mount_w, np.array([tx, ty]), BODY_THETA)
        legs.append({"id": lid, "theta1": round(t1, 4), "theta2": round(t2, 4),
                     "foot_world": {"x": round(tx, 4), "y": round(ty, 4)}})
    return {
        "body": {"x": round(body_x, 4), "y": BODY_Y, "theta": BODY_THETA},
        "legs": legs,
        "planted_legs": planted,
        "free_legs": free,
    }


def generate_walk(direction: str, n_frames: int = 8) -> list[dict]:
    """
    direction: 'right' (+x) or 'left' (-x).
    Returns list of pose dicts forming a loopable cycle (body returns to x=0).
    """
    assert direction in ("right", "left"), f"bad direction {direction}"
    sign = 1.0 if direction == "right" else -1.0

    # Stride parameters
    stride = 1.0 * sign          # body advances this much per full cycle
    half_stride = stride / 2.0

    # Nominal foot positions relative to mount when standing (x offset from mount)
    # front mounts at body_x ± 1.0, rear mounts at body_x ∓ 1.0
    # foot lands stride/2 ahead of mount, retracts stride/2 behind
    reach = 0.6 * abs(stride)    # foot reach fore/aft from mount

    # We split the cycle into 8 sub-steps, body advances stride/8 per frame.
    # Groups: A = legs 0,3  B = legs 1,2
    # Phase: 0..3 → group A swings (B planted), body advances
    #        4..7 → group B swings (A planted), body advances

    frames = []
    body_start_x = 0.0
    body_dx = stride / n_frames   # per frame

    # Initial foot positions (planted at neutral stance)
    # mount_x_in_world = body_x ± 1.0
    def neutral_foot(body_x, lid):
        mx = body_x + (1.0 if lid < 2 else -1.0)
        return np.array([mx, FLOOR_Y])

    # Track foot world positions across frames
    foot_pos = [neutral_foot(body_start_x, lid) for lid in range(4)]

    half = n_frames // 2
    for frame_i in range(n_frames):
        body_x = body_start_x + frame_i * body_dx
        sub = frame_i % half      # 0..3

        if frame_i < half:
            swinging = [0, 3]
            planted  = [1, 2]
        else:
            swinging = [1, 2]
            planted  = [0, 3]

        # Update swing feet: interpolate from behind to ahead of mount
        for lid in swinging:
            t = (sub + 1) / half              # 0→1 over sub-cycle
            mx = body_x + (1.0 if lid < 2 else -1.0)
            fx = mx + sign * (reach * (2 * t - 1))   # -reach → +reach
            lift = STEP_HEIGHT * math.sin(math.pi * t)
            fy = FLOOR_Y + lift
            foot_pos[lid] = np.array([fx, fy])

        # Planted feet stay fixed in world (just update reference)

        foot_targets = [(p[0], p[1]) for p in foot_pos]
        frame = make_pose(body_x, foot_targets, planted, swinging)
        frame["frame_index"] = frame_i
        frames.append(frame)

    return frames


def save_gaits():
    for direction in ("right", "left"):
        frames = generate_walk(direction, n_frames=8)
        data = {
            "description": f"Loopable alternating-tripod walk {direction}, 8 frames @ 5 fps",
            "direction": direction,
            "fps": 5,
            "frames": frames,
        }
        path = HERE / f"gait_{direction}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved {path}")


if __name__ == "__main__":
    save_gaits()
