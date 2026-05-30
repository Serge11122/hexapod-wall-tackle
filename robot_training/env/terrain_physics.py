"""
Extended RobotPhysics for terrain traversal training.

Key differences from robot_environment/contact_physics.py:
  - No GrooveJoint: height control replaced by gravity-compensated spring force
  - Terrain loaded from JSON (multi-segment polyline + bumpers)
  - Foot contact detection via pymunk collision handlers
  - Exposes sensory observation: joint angles, velocities, contact flags, forces
  - Height target derived from ground-truth terrain JSON (stable control signal)
"""

import math
import pymunk
import numpy as np

from robot_motion.body import (
    GRAVITY, BODY_HALF_H, BODY_HALF_LEN, LEG_L1, LEG_L2, LEG_MOUNTS,
    BODY_MASS, LEG_SEGMENT_MASS, STATIC_FRICTION, TOTAL_MASS, FOOT_RADIUS,
)
from robot_training.env.terrain_loader import (
    load_terrain_into_space,
    SELF_FILTER, COLL_TERRAIN, COLL_FOOT,
    terrain_height_at,
)

# ── Control params ─────────────────────────────────────────────────────────────
# NOTE (physics correctness): the body is supported ENTIRELY by leg contact
# forces against the terrain.  There is NO levitation/height spring and NO
# world-anchored pitch constraint — both were non-physical "magic" forces that
# made the robot float in the air regardless of whether its feet touched the
# ground.  Body height and pitch now emerge purely from leg forces + gravity +
# ground contact, exactly as a real legged robot.
JOINT_KP        = 14.0    # proportional gain (joint-angle error → motor rate)
JOINT_MAX_FORCE = 120.0   # max torque each joint motor can exert (N·m) — strong
                          # enough for stance legs to carry the body weight
SUBSTEPS        = 50      # physics sub-steps per env step for accuracy
# Generous pitch limit (radians, ±34°).  Hard stop only — see _build_robot.
# Set to None to remove entirely (body may then flip on rough terrain).
PITCH_LIMIT     = 0.25

# Spawn safety: drop the robot from a clear height and keep it away from walls
# so it never starts intersecting terrain or boundary walls.
SPAWN_DROP_HEIGHT = 2.6   # body COM height above terrain at spawn (legs tucked)
SPAWN_WALL_MARGIN = 3.0   # min horizontal clearance from either boundary wall
PENETRATION_TOL   = 0.20  # max allowed shape overlap (> pymunk collision slop 0.1)

# ── Joint angle limits (biologically realistic) ───────────────────────────────
# Reference: 0° = +x direction (body-right). All angles in radians.
# Hip (1st joint, body frame):  +90° to -125°
HIP_MAX  =  90.0 * math.pi / 180.0   # +1.5708 rad  (+y, straight up)
HIP_MIN  = -125.0 * math.pi / 180.0  # -2.1817 rad  (lower-left)
# Knee (2nd joint, relative to upper segment extension direction = 0°):  0° to -170°
KNEE_MAX =   0.0                      # fully extended (inline with upper)
KNEE_MIN = -170.0 * math.pi / 180.0  # -2.9671 rad  (almost fully folded)

# ── Joint velocity limit ──────────────────────────────────────────────────────
# Target: max 8°/frame at 5fps = 40°/s. Use 35°/s motor rate to ensure
# actual position change (including inertia/integration effects) stays ≤ 8°/frame.
MAX_JOINT_RATE = 35.0 * math.pi / 180.0  # 0.611 rad/s

# ── Nominal walking height ────────────────────────────────────────────────────
# Target body COM height above local terrain that the gait controller aims for.
# This is a CONTROL set-point used to plan foot placement — it is NOT a force.
# The body only reaches this height if the legs actually push it there.
WALK_HEIGHT = 1.6     # body COM above terrain surface (metres)


class TerrainRobotPhysics:
    """
    Pymunk robot in a terrain environment.

    Sensory outputs accessible each step:
      obs_joint_angles    : (8,) numpy array  — theta1,theta2 per leg
      obs_joint_vels      : (8,) numpy array  — angular velocity per joint
      obs_joint_torques   : (8,) numpy array  — signed motor force / max_force
      obs_foot_contact    : (4,) bool array   — foot touching terrain?
      obs_foot_forces     : (4,) float array  — normal contact force estimate
      obs_foot_heights    : (4,) float array  — y of foot tip
      body_state          : (x, y, theta, vx, vy, omega)
    """

    def __init__(self, dt: float, terrain_json: str, start_x: float, start_y: float):
        self.dt           = dt
        self.terrain_json = terrain_json
        self._terrain_height_est = 0.0
        # Velocity curriculum: set by trainer to gradually introduce speed constraint.
        # 1.0 = full realistic limit (40°/s). Values > 1.0 allow faster motion.
        # During early training this is set high to enable gait discovery,
        # then annealed to 1.0 once walking behavior is established.
        self.velocity_limit_scale = 1.0

        self.space = pymunk.Space()
        self.space.gravity = (0.0, -GRAVITY)
        # Light global damping (internal joint/air friction) — NOT a stabiliser.
        self.space.damping = 0.95

        self._terrain_meta = load_terrain_into_space(self.space, terrain_json)
        self._terrain_segs = self._terrain_meta["segments"]
        self._env_left     = self._terrain_meta["env_left"]
        self._env_right    = self._terrain_meta["env_right"]
        # Terrain shapes for penetration checking.
        self._terrain_shapes = [s for s in self.space.shapes
                                if getattr(s, "collision_type", 0) == COLL_TERRAIN]

        self._foot_contact  = [False] * 4
        self._foot_forces   = [0.0]   * 4
        self._contact_data  = {}   # leg_id → contact y
        self._robot_shapes  = []   # filled by _build_robot, for penetration checks

        # ── Spawn safety: clear of walls, dropped from a safe height ──────────
        sx = float(np.clip(start_x,
                           self._env_left  + SPAWN_WALL_MARGIN,
                           self._env_right - SPAWN_WALL_MARGIN))
        # Drop above the HIGHEST terrain within the robot's footprint (legs span
        # ~±2 units of body x) so tucked legs never spawn inside an obstacle.
        local_max = max(terrain_height_at(self._terrain_segs, sx + dx)
                        for dx in np.linspace(-2.2, 2.2, 15))
        sy = max(start_y, local_max + SPAWN_DROP_HEIGHT)

        self._build_robot(sx, sy)
        self._setup_collision_handlers()
        # Robot is spawned in mid-air with tucked legs → must not intersect.
        self.assert_no_penetration(context="spawn")

        self.obs_joint_angles  = np.zeros(8, dtype=np.float32)
        self.obs_joint_vels    = np.zeros(8, dtype=np.float32)
        self.obs_joint_torques = np.zeros(8, dtype=np.float32)
        self.obs_foot_contact  = np.zeros(4, dtype=np.float32)
        self.obs_foot_forces   = np.zeros(4, dtype=np.float32)
        self.obs_foot_heights  = np.zeros(4, dtype=np.float32)
        self._terrain_height_est = terrain_height_at(self._terrain_segs, start_x)

    # ── Robot construction ────────────────────────────────────────────────────

    def _build_robot(self, bx: float, by: float):
        moment = pymunk.moment_for_box(BODY_MASS, (2 * BODY_HALF_LEN, 2 * BODY_HALF_H))
        self.body = pymunk.Body(BODY_MASS, moment)
        self.body.position = (bx, by)

        body_shape           = pymunk.Poly.create_box(self.body, (2 * BODY_HALF_LEN, 2 * BODY_HALF_H))
        body_shape.filter    = SELF_FILTER
        body_shape.friction  = 0.5
        body_shape.elasticity = 0.0
        self.space.add(self.body, body_shape)
        self._robot_shapes.append(body_shape)

        # 3-D lateral-stability proxy: a generous pitch LIMIT (hard stop only,
        # NO torque motor and NO vertical force).  Within ±PITCH_LIMIT the body
        # pitches freely as an emergent result of leg contact + gravity; the
        # limit only prevents the body from rotating *past* the point where, in
        # a real 3-D hexapod, the out-of-plane row of legs would catch it.  This
        # is NOT the removed levitation/levelling magic: it carries no weight, so
        # the body still falls if the legs fail to support it (no floating).
        if PITCH_LIMIT is not None:
            pitch = pymunk.RotaryLimitJoint(
                self.space.static_body, self.body, -PITCH_LIMIT, PITCH_LIMIT)
            pitch.max_force = 1e7
            self.space.add(pitch)

        self.legs = []
        for m in LEG_MOUNTS:
            self._build_leg(m["id"], m["local_x"], bx, by)

    def _build_leg(self, lid: int, mx: float, bx: float, by: float):
        # Tucked-but-extended initial pose: feet hang below the body so that
        # when the robot is dropped it lands on its feet (no splayed legs that
        # could clip walls or terrain at spawn).
        t1, t2 = -1.20, -1.30

        hip_x  = bx + mx
        hip_y  = by
        knee_x = hip_x  + LEG_L1 * math.cos(t1)
        knee_y = hip_y  + LEG_L1 * math.sin(t1)
        foot_x = knee_x + LEG_L2 * math.cos(t1 + t2)
        foot_y = knee_y + LEG_L2 * math.sin(t1 + t2)

        # Upper segment
        ux = (hip_x + knee_x) / 2
        uy = (hip_y + knee_y) / 2
        upper = pymunk.Body(
            LEG_SEGMENT_MASS,
            pymunk.moment_for_segment(LEG_SEGMENT_MASS,
                                      (-LEG_L1 / 2, 0), (LEG_L1 / 2, 0), 0.02))
        upper.position = (ux, uy)
        upper.angle    = t1

        upper_sh = pymunk.Segment(upper, (-LEG_L1 / 2, 0), (LEG_L1 / 2, 0), 0.02)
        upper_sh.filter    = SELF_FILTER
        upper_sh.friction  = 0.4
        upper_sh.elasticity = 0.0
        self.space.add(upper, upper_sh)
        self._robot_shapes.append(upper_sh)

        hip_pin   = pymunk.PinJoint(self.body, upper, (mx, 0), (-LEG_L1 / 2, 0))
        hip_motor = pymunk.SimpleMotor(upper, self.body, 0.0)
        hip_motor.max_force = JOINT_MAX_FORCE
        # Hard anatomical limit: hip angle in body frame ∈ [HIP_MIN, HIP_MAX]
        hip_limit = pymunk.RotaryLimitJoint(self.body, upper, HIP_MIN, HIP_MAX)
        hip_limit.max_force = 1e6
        self.space.add(hip_pin, hip_motor, hip_limit)

        # Lower segment (foot — has terrain friction)
        lx = (knee_x + foot_x) / 2
        ly = (knee_y + foot_y) / 2
        lower = pymunk.Body(
            LEG_SEGMENT_MASS,
            pymunk.moment_for_segment(LEG_SEGMENT_MASS,
                                      (-LEG_L2 / 2, 0), (LEG_L2 / 2, 0), 0.02))
        lower.position = (lx, ly)
        lower.angle    = t1 + t2

        lower_sh = pymunk.Segment(lower, (-LEG_L2 / 2, 0), (LEG_L2 / 2, 0), 0.02)
        lower_sh.filter         = SELF_FILTER  # group=1: no self-collision
        lower_sh.collision_type = COLL_FOOT    # identified as foot for contact handler
        lower_sh.friction       = STATIC_FRICTION
        lower_sh.elasticity     = 0.02
        self.space.add(lower, lower_sh)
        self._robot_shapes.append(lower_sh)

        # Rounded foot pad at the tip of the lower segment: gives a stable,
        # high-friction contact patch (point feet on thin segments are unstable
        # and prone to poking through terrain).
        foot_sh = pymunk.Circle(lower, FOOT_RADIUS, (LEG_L2 / 2, 0))
        foot_sh.filter         = SELF_FILTER
        foot_sh.collision_type = COLL_FOOT
        foot_sh.friction       = STATIC_FRICTION
        foot_sh.elasticity     = 0.02
        self.space.add(foot_sh)
        self._robot_shapes.append(foot_sh)

        knee_pin   = pymunk.PinJoint(upper, lower, (LEG_L1 / 2, 0), (-LEG_L2 / 2, 0))
        knee_motor = pymunk.SimpleMotor(lower, upper, 0.0)
        knee_motor.max_force = JOINT_MAX_FORCE
        # Hard anatomical limit: knee angle relative to upper segment ∈ [KNEE_MIN, KNEE_MAX]
        knee_limit = pymunk.RotaryLimitJoint(upper, lower, KNEE_MIN, KNEE_MAX)
        knee_limit.max_force = 1e6
        self.space.add(knee_pin, knee_motor, knee_limit)

        self.legs.append({
            "id":         lid,
            "mount_x":    mx,
            "upper":      upper,
            "lower":      lower,
            "hip_motor":  hip_motor,
            "knee_motor": knee_motor,
            "lower_sh":   lower_sh,
        })

    # ── Collision handlers ────────────────────────────────────────────────────

    def _setup_collision_handlers(self):
        # pymunk 7.x: space.on_collision(type_a, type_b, begin=..., separate=..., post_solve=...)
        # data is passed as the `data` kwarg and received as third arg in callback.
        self.space.on_collision(
            collision_type_a = COLL_FOOT,
            collision_type_b = COLL_TERRAIN,
            begin      = _contact_begin,
            separate   = _contact_separate,
            post_solve = _contact_post_solve,
            data       = self,
        )

    # ── Step ─────────────────────────────────────────────────────────────────

    def step(self, joint_targets: np.ndarray) -> None:
        """
        Drive joints toward targets and step physics.

        joint_targets: (8,) array — [hip0, knee0, hip1, knee1, hip2, knee2, hip3, knee3]
        """
        # Reset per-step contact accumulators
        self._foot_forces = [0.0] * 4

        body_angle = self.body.angle

        for i, leg in enumerate(self.legs):
            upper = leg["upper"]
            lower = leg["lower"]
            t1_t  = joint_targets[2 * i]
            t2_t  = joint_targets[2 * i + 1]

            # Hip: angle measured relative to body frame
            t1_curr  = upper.angle - body_angle
            t1_t_clamped = max(HIP_MIN, min(HIP_MAX, t1_t))
            hip_err  = (t1_t_clamped - t1_curr + math.pi) % (2 * math.pi) - math.pi
            # Effective velocity limit scales with curriculum (1.0 = realistic 40°/s)
            eff_rate = MAX_JOINT_RATE * self.velocity_limit_scale
            leg["hip_motor"].rate = max(-eff_rate, min(eff_rate, JOINT_KP * hip_err))

            # Knee: angle measured relative to upper segment direction
            t2_curr  = lower.angle - upper.angle
            t2_t_clamped = max(KNEE_MIN, min(KNEE_MAX, t2_t))
            knee_err = (t2_t_clamped - t2_curr + math.pi) % (2 * math.pi) - math.pi
            leg["knee_motor"].rate = max(-eff_rate, min(eff_rate, JOINT_KP * knee_err))

        # No levitation force.  Track local terrain height for obs/control only.
        bx, by = self.body.position
        self._terrain_height_est = terrain_height_at(self._terrain_segs, bx)

        # Sub-step integration — gravity pulls the body down; only leg contact
        # forces against the terrain can hold it up.
        sub_dt = self.dt / SUBSTEPS
        for _ in range(SUBSTEPS):
            self.space.step(sub_dt)

        self._update_sensory()

    def _update_sensory(self):
        body_angle = self.body.angle
        for i, leg in enumerate(self.legs):
            upper = leg["upper"]
            lower = leg["lower"]
            self.obs_joint_angles[2 * i]     = upper.angle - body_angle
            self.obs_joint_angles[2 * i + 1] = lower.angle - upper.angle
            self.obs_joint_vels[2 * i]       = (upper.angular_velocity
                                                 - self.body.angular_velocity)
            self.obs_joint_vels[2 * i + 1]   = (lower.angular_velocity
                                                 - upper.angular_velocity)
            self.obs_joint_torques[2 * i]     = leg["hip_motor"].rate / max(abs(leg["hip_motor"].rate), 1.0)
            self.obs_joint_torques[2 * i + 1] = leg["knee_motor"].rate / max(abs(leg["knee_motor"].rate), 1.0)
            self.obs_foot_contact[i]           = float(self._foot_contact[i])
            self.obs_foot_forces[i]            = float(self._foot_forces[i])
            fw = lower.local_to_world((LEG_L2 / 2, 0))
            self.obs_foot_heights[i]           = float(fw.y)

    # ── State queries ─────────────────────────────────────────────────────────

    def get_body_state(self) -> tuple:
        p = self.body.position
        v = self.body.velocity
        return p.x, p.y, self.body.angle, v.x, v.y, self.body.angular_velocity

    def get_render_pose(self) -> dict:
        bx, by = self.body.position
        bth    = self.body.angle
        legs_out = []
        for leg in self.legs:
            upper = leg["upper"]
            lower = leg["lower"]
            fw = lower.local_to_world((LEG_L2 / 2, 0))
            legs_out.append({
                "id":         leg["id"],
                "theta1":     upper.angle - bth,
                "theta2":     lower.angle - upper.angle,
                "foot_world": {"x": fw.x, "y": fw.y},
            })
        return {
            "body":         {"x": bx, "y": by, "theta": bth},
            "legs":         legs_out,
            "planted_legs": [leg["id"] for i, leg in enumerate(self.legs)
                             if self._foot_contact[i]],
            "free_legs":    [leg["id"] for i, leg in enumerate(self.legs)
                             if not self._foot_contact[i]],
        }

    # ── Penetration / intersection detection ───────────────────────────────────

    def worst_penetration(self) -> tuple:
        """
        Return (depth, robot_shape, terrain_shape) for the deepest overlap
        between any robot shape and any terrain/wall shape.

        depth is the signed separation of the closest contact: >= 0 means no
        penetration; a negative value is the penetration depth (how far the
        robot shape has intersected the terrain shape).  Returns depth = 0.0 if
        nothing is in contact.
        """
        terrain_set = set(id(s) for s in self._terrain_shapes)
        worst_depth = 0.0
        worst_pair  = (None, None)
        for rs in self._robot_shapes:
            for info in self.space.shape_query(rs):
                if id(info.shape) not in terrain_set:
                    continue   # ignore non-terrain overlaps
                for p in info.contact_point_set.points:
                    if p.distance < worst_depth:
                        worst_depth = p.distance
                        worst_pair  = (rs, info.shape)
        return worst_depth, worst_pair[0], worst_pair[1]

    def assert_no_penetration(self, context: str = "", tol: float = PENETRATION_TOL) -> None:
        """
        Raise AssertionError if any robot shape intersects terrain/walls beyond
        the physics solver's normal contact slop.  Catches the non-physical
        states the user flagged: legs/body passing through walls or floor.
        """
        depth, rs, ts = self.worst_penetration()
        assert depth > -tol, (
            f"Robot intersects environment ({context}): penetration depth "
            f"{-depth:.3f} > tol {tol:.3f}.  robot_shape={type(rs).__name__} "
            f"terrain_shape={type(ts).__name__} at body pos "
            f"{tuple(round(c, 2) for c in self.body.position)}"
        )


# ── Collision callbacks (module-level for pymunk 7.x) ────────────────────────
# Signature: (arbiter, space, data) where data is the TerrainRobotPhysics instance.

def _leg_idx_from_body(phys: "TerrainRobotPhysics", body: pymunk.Body) -> int:
    for i, leg in enumerate(phys.legs):
        if body is leg["lower"]:
            return i
    return -1


def _contact_begin(arbiter: pymunk.Arbiter, space, phys) -> None:
    # arbiter.shapes: (foot_shape, terrain_shape) or reversed
    for sh in arbiter.shapes:
        if sh.collision_type == COLL_FOOT:
            idx = _leg_idx_from_body(phys, sh.body)
            if idx >= 0:
                phys._foot_contact[idx] = True
                cps = arbiter.contact_point_set
                if cps.points:
                    cp = cps.points[0]
                    cy = (cp.point_a.y + cp.point_b.y) / 2
                    phys._contact_data[phys.legs[idx]["id"]] = cy


def _contact_separate(arbiter: pymunk.Arbiter, space, phys) -> None:
    for sh in arbiter.shapes:
        if sh.collision_type == COLL_FOOT:
            idx = _leg_idx_from_body(phys, sh.body)
            if idx >= 0:
                phys._foot_contact[idx] = False


def _contact_post_solve(arbiter: pymunk.Arbiter, space, phys) -> None:
    ti        = arbiter.total_impulse
    force_mag = math.sqrt(ti.x ** 2 + ti.y ** 2)
    for sh in arbiter.shapes:
        if sh.collision_type == COLL_FOOT:
            idx = _leg_idx_from_body(phys, sh.body)
            if idx >= 0:
                phys._foot_forces[idx] += force_mag
