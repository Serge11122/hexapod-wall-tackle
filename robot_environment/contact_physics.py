"""
Pymunk-based 2D rigid body physics for the hexapod robot simulation.

The Chipmunk2D physics engine (via pymunk) is the single source of truth for
all body positions and angles.  No custom FK, no custom constraint formulas,
no divergence between physics and renderer.

Control loop:
  1. Read target joint angles from the gait JSON frame.
  2. Compute angle error for each hip / knee joint.
  3. Set SimpleMotor rate = KP * error  (proportional position controller).
  4. Step pymunk space N sub-steps at dt/N.
  5. Query body/leg positions directly from pymunk for rendering.
"""

import math
import pymunk

from robot_motion.body import (
    GRAVITY, BODY_HALF_H, BODY_HALF_LEN, LEG_L1, LEG_L2, LEG_MOUNTS,
    BODY_MASS, LEG_SEGMENT_MASS, STATIC_FRICTION,
)

FLOOR_Y   = 0.0
ENV_LEFT  = -12.0
ENV_RIGHT =  12.0

_SELF_FILTER    = pymunk.ShapeFilter(group=1)  # no robot self-collision
JOINT_KP        = 8.0     # proportional gain (rad/s per rad of error)
JOINT_MAX_FORCE = 15.0    # N·m — below friction limit (μ×N ≈ 18 N·m/leg)
PITCH_LIMIT     = 0.17    # ±10° hard clamp (groove joint assumes small pitch)
LEVEL_MAX_FORCE = 20.0    # N·m — soft pitch damping toward body.omega=0
SUBSTEPS        = 40      # physics sub-steps per rendered frame


class RobotPhysics:
    """
    Pymunk rigid-body simulation of the hexapod in the 2D sagittal plane.

    Bodies
    ------
    self.body       : main body rectangle
    self.legs[i]    : dict with keys upper, lower, hip_motor, knee_motor, id, mount_x

    All positions are owned by pymunk.  Call get_render_pose() to build a pose
    dict that can be passed directly to renderer.draw_robot().
    """

    def __init__(self, dt: float, start_x: float = 0.0, start_y: float = 1.9):
        self.dt = dt
        self.space = pymunk.Space()
        self.space.gravity = (0.0, -GRAVITY)
        self.space.damping = 0.88   # damps oscillations; helps settling

        self._build_environment()
        self._build_robot(start_x, start_y)

    # ── Environment ───────────────────────────────────────────────────────────

    def _build_environment(self):
        s = self.space.static_body

        floor = pymunk.Segment(s, (ENV_LEFT, FLOOR_Y), (ENV_RIGHT, FLOOR_Y), 0.02)
        floor.friction   = STATIC_FRICTION
        floor.elasticity = 0.02
        self.space.add(floor)

        lwall = pymunk.Segment(s, (ENV_LEFT,  FLOOR_Y), (ENV_LEFT,  8.0), 0.02)
        rwall = pymunk.Segment(s, (ENV_RIGHT, FLOOR_Y), (ENV_RIGHT, 8.0), 0.02)
        for w in (lwall, rwall):
            w.friction = 0.0
            w.elasticity = 0.0
        self.space.add(lwall, rwall)

    # ── Robot ─────────────────────────────────────────────────────────────────

    def _build_robot(self, bx: float, by: float):
        # Main body
        body_moment = pymunk.moment_for_box(BODY_MASS,
                                            (2 * BODY_HALF_LEN, 2 * BODY_HALF_H))
        self.body = pymunk.Body(BODY_MASS, body_moment)
        self.body.position = (bx, by)

        body_shape = pymunk.Poly.create_box(self.body,
                                            (2 * BODY_HALF_LEN, 2 * BODY_HALF_H))
        body_shape.filter    = _SELF_FILTER
        body_shape.friction  = 0.0
        body_shape.elasticity = 0.0
        self.space.add(self.body, body_shape)

        # Constrain body COM to slide horizontally at walk height.
        # This replaces a full balance controller: body translates freely in x
        # while y is held at by, matching the scripted gait's design assumption.
        groove = pymunk.GrooveJoint(
            self.space.static_body, self.body,
            (ENV_LEFT, by), (ENV_RIGHT, by),  # horizontal groove at walk height
            (0.0, 0.0))                        # anchored at body COM
        groove.max_force = 1e6
        self.space.add(groove)

        # Hard pitch clamp ±10°
        pitch_clamp = pymunk.RotaryLimitJoint(
            self.space.static_body, self.body, -PITCH_LIMIT, PITCH_LIMIT)
        pitch_clamp.max_force = 1e6
        self.space.add(pitch_clamp)

        # Soft pitch damping: drives body.angular_velocity → 0
        # SimpleMotor(static, body, 0) keeps static.omega - body.omega = 0,
        # i.e. body.omega → 0, resisting free rotation.
        level_motor = pymunk.SimpleMotor(self.space.static_body, self.body, 0.0)
        level_motor.max_force = LEVEL_MAX_FORCE
        self.space.add(level_motor)

        self.legs = []
        for m in LEG_MOUNTS:
            self._build_leg(m["id"], m["local_x"], bx, by)

    def _build_leg(self, lid: int, mx: float, bx: float, by: float):
        # Initial joint angles: planted stance for legs 1,2; lifted swing for 0,3
        if lid in (1, 2):
            t1, t2 = -0.987, -1.062   # planted at FLOOR_Y when body_y=1.9
        else:
            t1, t2 = -0.896, -1.554   # foot raised ~0.35 m above floor

        # World positions of key points
        hip_x,  hip_y  = bx + mx,  by
        knee_x, knee_y = (hip_x  + LEG_L1 * math.cos(t1),
                          hip_y  + LEG_L1 * math.sin(t1))
        foot_x, foot_y = (knee_x + LEG_L2 * math.cos(t1 + t2),
                          knee_y + LEG_L2 * math.sin(t1 + t2))

        # ── Upper segment (hip → knee) ─────────────────────────────────────
        upper_cx = (hip_x  + knee_x) / 2
        upper_cy = (hip_y  + knee_y) / 2
        upper = pymunk.Body(
            LEG_SEGMENT_MASS,
            pymunk.moment_for_segment(LEG_SEGMENT_MASS,
                                      (-LEG_L1 / 2, 0), (LEG_L1 / 2, 0), 0.02))
        upper.position = (upper_cx, upper_cy)
        upper.angle    = t1   # absolute world angle = theta1 since body.angle=0

        upper_shape = pymunk.Segment(upper, (-LEG_L1 / 2, 0), (LEG_L1 / 2, 0), 0.02)
        upper_shape.filter    = _SELF_FILTER
        upper_shape.friction  = 0.0
        upper_shape.elasticity = 0.0
        self.space.add(upper, upper_shape)

        # Hip: pin joint anchors body at mount, upper at proximal end
        hip_pin   = pymunk.PinJoint(self.body, upper, (mx, 0), (-LEG_L1 / 2, 0))
        # Motor: drives upper.omega - body.omega = rate
        hip_motor = pymunk.SimpleMotor(upper, self.body, 0.0)
        hip_motor.max_force = JOINT_MAX_FORCE
        self.space.add(hip_pin, hip_motor)

        # ── Lower segment (knee → foot) ────────────────────────────────────
        lower_cx = (knee_x + foot_x) / 2
        lower_cy = (knee_y + foot_y) / 2
        lower = pymunk.Body(
            LEG_SEGMENT_MASS,
            pymunk.moment_for_segment(LEG_SEGMENT_MASS,
                                      (-LEG_L2 / 2, 0), (LEG_L2 / 2, 0), 0.02))
        lower.position = (lower_cx, lower_cy)
        lower.angle    = t1 + t2

        lower_shape = pymunk.Segment(lower, (-LEG_L2 / 2, 0), (LEG_L2 / 2, 0), 0.02)
        lower_shape.filter    = _SELF_FILTER
        lower_shape.friction  = STATIC_FRICTION   # feet grip the floor
        lower_shape.elasticity = 0.02
        self.space.add(lower, lower_shape)

        # Knee: pin joint upper distal → lower proximal
        knee_pin   = pymunk.PinJoint(upper, lower, (LEG_L1 / 2, 0), (-LEG_L2 / 2, 0))
        knee_motor = pymunk.SimpleMotor(lower, upper, 0.0)
        knee_motor.max_force = JOINT_MAX_FORCE
        self.space.add(knee_pin, knee_motor)

        self.legs.append({
            "id":          lid,
            "mount_x":     mx,
            "upper":       upper,
            "lower":       lower,
            "hip_motor":   hip_motor,
            "knee_motor":  knee_motor,
        })

    # ── Step ─────────────────────────────────────────────────────────────────

    def step(self, gait_frame: dict) -> None:
        """
        Drive joints toward gait targets then advance the physics simulation.

        Motor convention: SimpleMotor(child, parent, rate) keeps
          child.omega - parent.omega == rate.
        Setting rate = KP * (target - current) gives proportional position control.
        """
        joints = {leg["id"]: (leg["theta1"], leg["theta2"])
                  for leg in gait_frame["legs"]}

        body_angle = self.body.angle

        for leg in self.legs:
            lid   = leg["id"]
            upper = leg["upper"]
            lower = leg["lower"]
            t1_t, t2_t = joints[lid]

            # Hip: target is theta1 relative to body
            t1_curr = upper.angle - body_angle
            hip_err = t1_t - t1_curr
            hip_err = (hip_err + math.pi) % (2 * math.pi) - math.pi
            leg["hip_motor"].rate = JOINT_KP * hip_err

            # Knee: target is theta2 relative to upper
            t2_curr = lower.angle - upper.angle
            knee_err = t2_t - t2_curr
            knee_err = (knee_err + math.pi) % (2 * math.pi) - math.pi
            leg["knee_motor"].rate = JOINT_KP * knee_err

        sub_dt = self.dt / SUBSTEPS
        for _ in range(SUBSTEPS):
            self.space.step(sub_dt)

    # ── State queries ─────────────────────────────────────────────────────────

    def get_body_state(self) -> tuple:
        """Return (x, y, theta, vx, vy, omega) of the main body."""
        p = self.body.position
        v = self.body.velocity
        return p.x, p.y, self.body.angle, v.x, v.y, self.body.angular_velocity

    def get_render_pose(self) -> dict:
        """
        Build a pose dict compatible with renderer.draw_robot().

        All positions come from pymunk — no FK recomputation, no divergence.
        """
        bx, by = self.body.position
        bth    = self.body.angle

        legs_out = []
        for leg in self.legs:
            upper = leg["upper"]
            lower = leg["lower"]
            # Foot world position: distal end of lower segment
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
            "planted_legs": [],   # physics handles contact; no manual tracking
            "free_legs":    [],
        }
