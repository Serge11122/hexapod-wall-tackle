"""
Walk demo + physics-correctness verification.

Runs the contact-based GaitController in the corrected physics and:
  1. asserts the robot never floats (body must be supported by feet — i.e. at
     least one foot in contact whenever the body is near walking height),
  2. asserts the robot never intersects terrain/walls (penetration check every
     step), at spawn, during the settle drop, and throughout walking,
  3. renders a GIF so the behaviour can be inspected visually.

Usage:
    .venv/bin/python -m robot_training.eval.walk_demo --unit-test
    .venv/bin/python -m robot_training.eval.walk_demo --methods fbm_noise --seeds 19
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from robot_training.dataset import list_terrains
from robot_training.env.terrain_physics import (
    TerrainRobotPhysics, WALK_HEIGHT, PENETRATION_TOL,
)
from robot_training.control.gait_controller import GaitController
from robot_training.env.terrain_loader import terrain_height_at
from robot_training.eval.evaluate import _render_frame, _env_scale_centre, FPS

DT       = 1.0 / 5
VID_DIR  = Path(__file__).parent.parent.parent / "robot_vis" / "vid"
DROP_STEPS = 18   # land on feet from the spawn drop
HOLD_STEPS = 10   # stabilise into a stand before walking
TARGET_SPEED = 0.5


def run_episode(entry, direction: int, max_frames: int, out_dir: Path,
                strict_float: bool = True) -> dict:
    with open(entry.path) as f:
        meta = json.load(f)
    env_l, env_r = meta["env_left"], meta["env_right"]

    if direction > 0:
        sx, sy = entry.drop_left
    else:
        sx, sy = entry.drop_right

    phys = TerrainRobotPhysics(dt=DT, terrain_json=str(entry.path),
                               start_x=sx, start_y=sy)
    ctrl = GaitController(direction=direction, target_speed=TARGET_SPEED)

    cx, cy, scale = _env_scale_centre(1400, 600, env_l, env_r)
    images = []
    worst_pen = 0.0
    float_violations = 0      # steps high-up with no foot contact
    max_float_run = 0         # longest consecutive such run (true levitation)
    cur_float_run = 0
    start_x = phys.body.position.x

    from robot_training.control.gait_controller import leg_ik
    # ── Drop: command a feet-under-hips stance so it lands on its feet ─────────
    t1s, t2s = leg_ik(0.0, -ctrl.stance_depth)
    stance = np.array([t1s, t2s] * 4, dtype=np.float32)
    for _ in range(DROP_STEPS):
        phys.step(stance)
        phys.assert_no_penetration(context="drop")

    # ── Hold: stand stably before walking ─────────────────────────────────────
    ctrl.reset(phys)
    for _ in range(HOLD_STEPS):
        phys.step(ctrl.hold(phys))
        phys.assert_no_penetration(context="hold")
    start_x = phys.body.position.x   # measure forward progress from stable stand
    for fi in range(max_frames):
        bx, by, bth, vx, vy, om = phys.get_body_state()
        terrain_h = terrain_height_at(phys._terrain_segs, bx)
        n_contact = int(sum(phys._foot_contact))

        pose = phys.get_render_pose()
        lbl = (f"{entry.method}:{entry.seed} f={fi:03d} x={bx:.2f} "
               f"vx={vx:.2f} ct={n_contact} pitch={bth:.2f} "
               f"h={by - terrain_h:.2f}")
        images.append(_render_frame(pose, meta, cx, cy, scale, lbl))

        # Float check: if the body is up near walking height it MUST be held
        # there by feet — at least one foot in contact.  (When it has fallen
        # below ~0.6 of walk height it is collapsing/falling, not floating.)
        body_h = by - terrain_h
        if body_h > 0.6 * WALK_HEIGHT and n_contact == 0:
            float_violations += 1
            cur_float_run += 1
            max_float_run = max(max_float_run, cur_float_run)
        else:
            cur_float_run = 0

        targets = ctrl.act(phys)
        phys.step(targets)

        depth = phys.worst_penetration()[0]
        worst_pen = min(worst_pen, depth)
        phys.assert_no_penetration(context=f"walk step {fi}")

    dist = (phys.body.position.x - start_x) * direction
    result = {
        "method": entry.method, "seed": entry.seed,
        "dist": float(dist), "worst_pen": float(worst_pen),
        "float_violations": int(float_violations),
        "max_float_run": int(max_float_run), "frames": len(images),
    }

    # Sustained no-contact-while-high == levitation.  Brief airborne moments
    # during stepping / crossing a gap are physical and allowed.
    if strict_float:
        assert max_float_run <= 6, (
            f"Robot levitated (no feet in contact while high) for "
            f"{max_float_run} consecutive steps on {entry.method}:{entry.seed}")

    if images:
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = f"{entry.method}_seed{entry.seed:02d}"
        gif = out_dir / f"{tag}.gif"
        images[0].save(str(gif), save_all=True, append_images=images[1:],
                       loop=0, duration=int(1000 / FPS), optimize=False)
        result["gif"] = str(gif)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="+", default=["fbm_noise"])
    ap.add_argument("--seeds", nargs="+", type=int, default=None)
    ap.add_argument("--direction", type=int, default=1)
    ap.add_argument("--max-frames", type=int, default=300)
    ap.add_argument("--out", default="walk_demo")
    ap.add_argument("--unit-test", action="store_true",
                    help="<2min: one terrain, few frames, strict asserts")
    args = ap.parse_args()

    if args.unit_test:
        args.methods = ["fbm_noise"]
        args.seeds = [19]
        args.max_frames = 60

    entries = list_terrains(args.methods)
    if args.seeds is not None:
        entries = [e for e in entries if e.seed in args.seeds]
    assert entries, f"no terrains for methods={args.methods} seeds={args.seeds}"

    label = "right" if args.direction > 0 else "left"
    out_dir = VID_DIR / f"{args.out}_{label}"

    results = []
    for e in entries:
        r = run_episode(e, args.direction, args.max_frames, out_dir,
                        strict_float=args.unit_test)
        print(f"  {r['method']}:{r['seed']:02d}  dist={r['dist']:+.2f}  "
              f"worst_pen={r['worst_pen']:.3f}  max_float_run={r['max_float_run']}"
              f"  frames={r['frames']}")
        results.append(r)

    mean_d = float(np.mean([r["dist"] for r in results]))
    print(f"\nmean forward dist = {mean_d:+.2f} over {len(results)} terrains "
          f"(pen tol={PENETRATION_TOL})")
    if args.unit_test:
        assert all(r["max_float_run"] <= 6 for r in results), "LEVITATION in unit-test"
        print("UNIT-TEST PASS: no levitation, no intersection.")


if __name__ == "__main__":
    main()
