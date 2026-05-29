"""
Causal contact physics for the 2D robot simulation.

Locomotion mechanism:
  1. Joint angles are prescribed from the gait JSON (kinematic actuation).
  2. Planted feet are anchored to the floor at the moment of touch-down.
  3. As joint angles advance through the gait cycle, the constraint
       foot_world = body_pos + mount_offset + FK_local_offset(joint_angles)
     is solved for body_pos each time-step.
  4. The body moves because satisfying the constraint forces it to translate —
     exactly as in real legged locomotion where ground-reaction forces through
     the stance leg propel the body.

There is NO external drive force, NO velocity assignment, NO teleportation.
If the gait produces no net horizontal foot sweep, the body does not move.
"""

import math
from robot_motion.body import GRAVITY, BODY_HALF_H, LEG_L1, LEG_L2, LEG_MOUNTS

FLOOR_Y   = 0.0
ENV_LEFT  = -12.0
ENV_RIGHT =  12.0
BODY_MARGIN = 1.5   # keep body COM this far from walls


def _fk_local(t1: float, t2: float) -> tuple[float, float]:
    """
    Foot offset from the mount point in body frame (body_theta = 0 assumed).
    Returns (dx, dy) relative to mount.
    """
    fx = LEG_L1 * math.cos(t1) + LEG_L2 * math.cos(t1 + t2)
    fy = LEG_L1 * math.sin(t1) + LEG_L2 * math.sin(t1 + t2)
    return fx, fy


class BodyState:
    __slots__ = ("bx", "by", "vx", "vy", "planted", "foot_anchors")

    def __init__(self, bx: float, by: float, vx: float = 0.0, vy: float = 0.0):
        self.bx = bx
        self.by = by
        self.vx = vx
        self.vy = vy
        self.planted: set[int] = set()
        # lid -> (anchor_x, anchor_y)  — world position where foot is pinned
        self.foot_anchors: dict[int, tuple[float, float]] = {}


class ContactPhysics:
    """
    Two-phase physics:

    FREE FLIGHT  (no planted feet) — standard gravity integration with
                 sub-steps; body falls until gait starts planting.

    STANCE       (≥1 planted foot) — body position is computed from the
                 planted-foot constraints each step.  No external force
                 is applied; the body translates because satisfying the
                 constraint (foot stays at its anchor) requires it to move
                 as joint angles change.
    """

    def __init__(self, dt: float = 0.2, sub_steps: int = 20):
        self.dt        = dt
        self.sub_dt    = dt / sub_steps
        self.sub_steps = sub_steps

    def step(self, state: BodyState, gait_curr: dict, prev_planted: set) -> BodyState:
        """
        Advance one rendered frame.

        gait_curr   : pose dict with keys 'planted_legs', 'free_legs', 'legs'
        prev_planted: set of leg-ids that were planted last frame
        Returns mutated state.
        """
        planted_curr = set(gait_curr["planted_legs"])
        joints = {leg["id"]: (leg["theta1"], leg["theta2"])
                  for leg in gait_curr["legs"]}

        # ── Liftoff: planted → free ───────────────────────────────────────────
        for lid in prev_planted - planted_curr:
            state.foot_anchors.pop(lid, None)

        # ── Touch-down: free → planted ────────────────────────────────────────
        for lid in planted_curr - prev_planted:
            mx = LEG_MOUNTS[lid]["local_x"]
            t1, t2 = joints[lid]
            fx, fy = _fk_local(t1, t2)
            # Anchor foot at floor level regardless of where FK lands the foot
            # (the body may be above WALK_HEIGHT during the drop; we pin to floor)
            state.foot_anchors[lid] = (state.bx + mx + fx, FLOOR_Y)

        state.planted = planted_curr

        if planted_curr:
            # ── Stance: body position from constraint ─────────────────────────
            # For each planted foot:
            #   foot_world.x = body.x + mount_lx + fk_lx   →   body.x = anchor_x - mount_lx - fk_lx
            #   foot_world.y = body.y +    0     + fk_ly   →   body.y = anchor_y - fk_ly
            bx_vals, by_vals = [], []
            for lid in planted_curr:
                mx = LEG_MOUNTS[lid]["local_x"]
                t1, t2 = joints[lid]
                fx, fy = _fk_local(t1, t2)
                ax, ay = state.foot_anchors[lid]
                bx_vals.append(ax - mx - fx)
                by_vals.append(ay - fy)

            bx_new = sum(bx_vals) / len(bx_vals)
            by_new = sum(by_vals) / len(by_vals)

            # Velocity is inferred from position change (no force assignment)
            state.vx = (bx_new - state.bx) / self.dt
            state.vy = 0.0
            state.bx = bx_new
            state.by = by_new

        else:
            # ── Free flight: gravity only ─────────────────────────────────────
            sub_dt = self.sub_dt
            for _ in range(self.sub_steps):
                state.vy -= GRAVITY * sub_dt
                state.bx += state.vx * sub_dt
                state.by += state.vy * sub_dt
                # Soft floor catch (shouldn't trigger once gait is running)
                if state.by < FLOOR_Y + BODY_HALF_H:
                    state.by = FLOOR_Y + BODY_HALF_H
                    state.vy = max(state.vy * -0.05, 0.0)  # near-inelastic bounce

        # ── Wall clamp ────────────────────────────────────────────────────────
        if state.bx < ENV_LEFT + BODY_MARGIN:
            state.bx = ENV_LEFT + BODY_MARGIN
            state.vx = max(state.vx, 0.0)
        if state.bx > ENV_RIGHT - BODY_MARGIN:
            state.bx = ENV_RIGHT - BODY_MARGIN
            state.vx = min(state.vx, 0.0)

        return state
