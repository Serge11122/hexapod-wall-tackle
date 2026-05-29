"""
Terrain-aware robot physics that keeps the GrooveJoint (matching BC training conditions).

Extends the original RobotPhysics from contact_physics.py to:
  - Load multi-segment terrain polyline + gap-edge bumpers from JSON
  - Keep the GrooveJoint at WALK_HEIGHT (body translates freely in x, y held)
  - Keep all stability constraints (RotaryLimitJoint, level motor)
  - Add foot contact detection via pymunk 7.x on_collision

This matches the environment used for BC pretraining (original sim had GrooveJoint + flat floor).
The BC model outputs joint angles that are calibrated for this config.
"""

import json
import math
import pymunk
import numpy as np

from robot_motion.body import (
    GRAVITY, BODY_HALF_H, BODY_HALF_LEN, LEG_L1, LEG_L2, LEG_MOUNTS,
    BODY_MASS, LEG_SEGMENT_MASS, STATIC_FRICTION,
)
from robot_environment.contact_physics import (
    JOINT_KP, JOINT_MAX_FORCE, PITCH_LIMIT, LEVEL_MAX_FORCE, SUBSTEPS,
)

WALK_HEIGHT  = 1.9
COLL_TERRAIN = 1
COLL_FOOT    = 2
_SELF_FILTER = pymunk.ShapeFilter(group=1)
TERRAIN_FRICTION   = 0.8
TERRAIN_ELASTICITY = 0.02


class TerrainRobotPhysicsV2:
    """
    Same physics as RobotPhysics but with terrain loaded from JSON.

    Sensory outputs:
      obs_joint_angles[8], obs_joint_vels[8], obs_joint_torques[8]
      obs_foot_contact[4], obs_foot_forces[4], obs_foot_heights[4]
    """

    def __init__(self, dt: float, terrain_json: str, start_x: float, start_y: float):
        self.dt = dt

        with open(terrain_json) as f:
            d = json.load(f)
        self._env_left  = d["env_left"]
        self._env_right = d["env_right"]
        self._segments  = d["segments"]
        self._gaps      = d.get("gaps", [])

        self.space = pymunk.Space()
        self.space.gravity = (0.0, -GRAVITY)
        self.space.damping = 0.88

        self._foot_contact = [False] * 4
        self._foot_forces  = [0.0]   * 4
        self._contact_data = {}

        self._build_environment()
        self._build_robot(start_x, start_y)
        self._setup_collision_handlers()

        self.obs_joint_angles  = np.zeros(8, dtype=np.float32)
        self.obs_joint_vels    = np.zeros(8, dtype=np.float32)
        self.obs_joint_torques = np.zeros(8, dtype=np.float32)
        self.obs_foot_contact  = np.zeros(4, dtype=np.float32)
        self.obs_foot_forces   = np.zeros(4, dtype=np.float32)
        self.obs_foot_heights  = np.zeros(4, dtype=np.float32)

    def _build_environment(self):
        sb = self.space.static_body

        def _add(p0, p1, friction=TERRAIN_FRICTION, elasticity=TERRAIN_ELASTICITY):
            sh = pymunk.Segment(sb, p0, p1, 0.02)
            sh.friction       = friction
            sh.elasticity     = elasticity
            sh.collision_type = COLL_TERRAIN
            self.space.add(sh)

        # Terrain polyline
        for seg in self._segments:
            _add((seg["x1"], seg["y1"]), (seg["x2"], seg["y2"]))

        # Gap-edge bumpers
        BUMPER_H = 0.5
        for gap in self._gaps:
            gx0, gx1 = gap["x0"], gap["x1"]
            _add((gx0, 0.0), (gx0, BUMPER_H), friction=0.3, elasticity=0.05)
            _add((gx1, 0.0), (gx1, BUMPER_H), friction=0.3, elasticity=0.05)

        # Boundary walls
        for wx in (self._env_left, self._env_right):
            wall = pymunk.Segment(sb, (wx, 0.0), (wx, 8.0), 0.02)
            wall.friction   = 0.0
            wall.elasticity = 0.0
            wall.collision_type = COLL_TERRAIN
            self.space.add(wall)

    def _build_robot(self, bx: float, by: float):
        moment = pymunk.moment_for_box(BODY_MASS, (2 * BODY_HALF_LEN, 2 * BODY_HALF_H))
        self.body = pymunk.Body(BODY_MASS, moment)
        self.body.position = (bx, by)

        body_shape           = pymunk.Poly.create_box(self.body, (2 * BODY_HALF_LEN, 2 * BODY_HALF_H))
        body_shape.filter    = _SELF_FILTER
        body_shape.friction  = 0.0
        body_shape.elasticity = 0.0
        self.space.add(self.body, body_shape)

        # GrooveJoint: body slides horizontally at walk height
        groove = pymunk.GrooveJoint(
            self.space.static_body, self.body,
            (self._env_left, by), (self._env_right, by),
            (0.0, 0.0))
        groove.max_force = 1e6
        self.space.add(groove)

        # Pitch clamp ±10°
        pitch = pymunk.RotaryLimitJoint(
            self.space.static_body, self.body, -PITCH_LIMIT, PITCH_LIMIT)
        pitch.max_force = 1e6
        self.space.add(pitch)

        # Soft pitch damping
        level = pymunk.SimpleMotor(self.space.static_body, self.body, 0.0)
        level.max_force = LEVEL_MAX_FORCE
        self.space.add(level)

        self.legs = []
        for m in LEG_MOUNTS:
            self._build_leg(m["id"], m["local_x"], bx, by)

    def _build_leg(self, lid: int, mx: float, bx: float, by: float):
        if lid in (1, 2):
            t1, t2 = -0.987, -1.062
        else:
            t1, t2 = -0.896, -1.554

        hip_x  = bx + mx;  hip_y  = by
        knee_x = hip_x  + LEG_L1 * math.cos(t1)
        knee_y = hip_y  + LEG_L1 * math.sin(t1)
        foot_x = knee_x + LEG_L2 * math.cos(t1 + t2)
        foot_y = knee_y + LEG_L2 * math.sin(t1 + t2)

        upper = pymunk.Body(LEG_SEGMENT_MASS,
                            pymunk.moment_for_segment(LEG_SEGMENT_MASS,
                                                      (-LEG_L1/2,0),(LEG_L1/2,0),0.02))
        upper.position = ((bx+mx+knee_x)/2 if False else (hip_x+knee_x)/2, (hip_y+knee_y)/2)
        upper.angle    = t1
        upper_sh = pymunk.Segment(upper, (-LEG_L1/2,0),(LEG_L1/2,0),0.02)
        upper_sh.filter = _SELF_FILTER; upper_sh.friction = 0.0; upper_sh.elasticity = 0.0
        self.space.add(upper, upper_sh)

        hip_pin   = pymunk.PinJoint(self.body, upper, (mx,0), (-LEG_L1/2,0))
        hip_motor = pymunk.SimpleMotor(upper, self.body, 0.0)
        hip_motor.max_force = JOINT_MAX_FORCE
        self.space.add(hip_pin, hip_motor)

        lower = pymunk.Body(LEG_SEGMENT_MASS,
                            pymunk.moment_for_segment(LEG_SEGMENT_MASS,
                                                      (-LEG_L2/2,0),(LEG_L2/2,0),0.02))
        lower.position = ((knee_x+foot_x)/2, (knee_y+foot_y)/2)
        lower.angle    = t1 + t2
        lower_sh = pymunk.Segment(lower, (-LEG_L2/2,0),(LEG_L2/2,0),0.02)
        lower_sh.filter         = _SELF_FILTER
        lower_sh.collision_type = COLL_FOOT
        lower_sh.friction       = STATIC_FRICTION
        lower_sh.elasticity     = 0.02
        self.space.add(lower, lower_sh)

        knee_pin   = pymunk.PinJoint(upper, lower, (LEG_L1/2,0), (-LEG_L2/2,0))
        knee_motor = pymunk.SimpleMotor(lower, upper, 0.0)
        knee_motor.max_force = JOINT_MAX_FORCE
        self.space.add(knee_pin, knee_motor)

        self.legs.append({
            "id": lid, "mount_x": mx,
            "upper": upper, "lower": lower,
            "hip_motor": hip_motor, "knee_motor": knee_motor,
        })

    def _setup_collision_handlers(self):
        self.space.on_collision(
            collision_type_a = COLL_FOOT,
            collision_type_b = COLL_TERRAIN,
            begin      = _cb_begin,
            separate   = _cb_separate,
            post_solve = _cb_post_solve,
            data       = self,
        )

    def step(self, joint_targets: np.ndarray) -> None:
        self._foot_forces = [0.0] * 4
        body_angle = self.body.angle
        for i, leg in enumerate(self.legs):
            upper, lower = leg["upper"], leg["lower"]
            t1_t = joint_targets[2*i];  t2_t = joint_targets[2*i+1]
            t1_c = upper.angle - body_angle
            hip_err = (t1_t - t1_c + math.pi) % (2*math.pi) - math.pi
            leg["hip_motor"].rate = JOINT_KP * hip_err
            t2_c = lower.angle - upper.angle
            knee_err = (t2_t - t2_c + math.pi) % (2*math.pi) - math.pi
            leg["knee_motor"].rate = JOINT_KP * knee_err
        for _ in range(SUBSTEPS):
            self.space.step(self.dt / SUBSTEPS)
        self._update_sensory()

    def _update_sensory(self):
        ba = self.body.angle
        for i, leg in enumerate(self.legs):
            u, l = leg["upper"], leg["lower"]
            self.obs_joint_angles[2*i]     = u.angle - ba
            self.obs_joint_angles[2*i+1]   = l.angle - u.angle
            self.obs_joint_vels[2*i]       = u.angular_velocity - self.body.angular_velocity
            self.obs_joint_vels[2*i+1]     = l.angular_velocity - u.angular_velocity
            self.obs_joint_torques[2*i]    = leg["hip_motor"].rate / max(abs(leg["hip_motor"].rate),1)
            self.obs_joint_torques[2*i+1]  = leg["knee_motor"].rate / max(abs(leg["knee_motor"].rate),1)
            self.obs_foot_contact[i]       = float(self._foot_contact[i])
            self.obs_foot_forces[i]        = float(self._foot_forces[i])
            fw = l.local_to_world((LEG_L2/2, 0))
            self.obs_foot_heights[i]       = float(fw.y)

    def get_body_state(self):
        p = self.body.position; v = self.body.velocity
        return p.x, p.y, self.body.angle, v.x, v.y, self.body.angular_velocity

    def get_render_pose(self):
        bx, by = self.body.position; bth = self.body.angle
        legs_out = []
        for leg in self.legs:
            u, l = leg["upper"], leg["lower"]
            fw = l.local_to_world((LEG_L2/2, 0))
            legs_out.append({"id": leg["id"],
                             "theta1": u.angle - bth, "theta2": l.angle - u.angle,
                             "foot_world": {"x": fw.x, "y": fw.y}})
        return {"body": {"x": bx, "y": by, "theta": bth}, "legs": legs_out,
                "planted_legs": [leg["id"] for i,leg in enumerate(self.legs) if self._foot_contact[i]],
                "free_legs":    [leg["id"] for i,leg in enumerate(self.legs) if not self._foot_contact[i]]}


def _foot_idx(phys, body):
    for i, leg in enumerate(phys.legs):
        if body is leg["lower"]: return i
    return -1

def _cb_begin(arb, space, phys):
    for sh in arb.shapes:
        if sh.collision_type == COLL_FOOT:
            idx = _foot_idx(phys, sh.body)
            if idx >= 0:
                phys._foot_contact[idx] = True
                cps = arb.contact_point_set
                if cps.points:
                    cp = cps.points[0]
                    phys._contact_data[phys.legs[idx]["id"]] = (cp.point_a.y+cp.point_b.y)/2

def _cb_separate(arb, space, phys):
    for sh in arb.shapes:
        if sh.collision_type == COLL_FOOT:
            idx = _foot_idx(phys, sh.body)
            if idx >= 0: phys._foot_contact[idx] = False

def _cb_post_solve(arb, space, phys):
    ti = arb.total_impulse
    fm = math.sqrt(ti.x**2 + ti.y**2)
    for sh in arb.shapes:
        if sh.collision_type == COLL_FOOT:
            idx = _foot_idx(phys, sh.body)
            if idx >= 0: phys._foot_forces[idx] += fm
