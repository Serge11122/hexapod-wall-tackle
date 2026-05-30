"""
Evaluate the trained policy against the corrected physics and render videos.

Loads ppo_best_<dir>.pt, runs the physics-lookahead RolloutPlanner (terrain
sensing via the contact-built local map + value-guided action selection) over a
spread of terrains from every generator, asserts no intersection throughout,
and writes GIFs + a distance/success summary.

Usage:
    .venv/bin/python -m robot_training.eval.make_videos --direction 1
    .venv/bin/python -m robot_training.eval.make_videos --seeds-per-method 2
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from robot_training.dataset import list_terrains, METHODS
from robot_training.env.terrain_env import TerrainTraversalEnv, DT, joints_to_action
from robot_training.models.policy import load_policy
from robot_training.planning.rollout_planner import RolloutPlanner
from robot_training.eval.evaluate import _render_frame, _env_scale_centre, FPS

VID_DIR   = Path(__file__).parent.parent.parent / "robot_vis" / "vid"
MODEL_DIR = Path(__file__).parent.parent / "models"


def eval_one(env, planner, entry, max_frames, render=True):
    obs = env.reset(entry)
    planner.reset_hidden()
    with open(entry.path) as f:
        meta = json.load(f)
    cx, cy, scale = _env_scale_centre(1400, 600, meta["env_left"], meta["env_right"])
    images, worst_pen = [], 0.0
    done, info, fi = False, {}, 0
    while not done and fi < max_frames:
        if render:
            pose = env.render()
            bx, by, bth, vx, vy, _ = env._physics.get_body_state()
            n_ct = int(sum(env._physics._foot_contact))
            lbl = (f"{entry.method}:{entry.seed} f={fi:03d} x={bx:.2f} "
                   f"vx={vx:.2f} ct={n_ct} pitch={bth:.2f}")
            images.append(_render_frame(pose, meta, cx, cy, scale, lbl))
        joint_targets = planner.act(obs, env._physics, env._lmap, env.direction)
        obs, _, done, info = env.step(joints_to_action(joint_targets))
        worst_pen = min(worst_pen, env._physics.worst_penetration()[0])
        fi += 1
    return images, info, worst_pen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--direction", type=int, default=1)
    ap.add_argument("--seeds-per-method", type=int, default=2)
    ap.add_argument("--max-frames", type=int, default=400)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default="trained")
    args = ap.parse_args()

    label  = "right" if args.direction > 0 else "left"
    device = torch.device("cpu")
    model_path = args.model or str(MODEL_DIR / f"ppo_best_{label}.pt")
    policy  = load_policy(model_path, device)
    planner = RolloutPlanner(policy, device, n_candidates=12, lookahead=4)
    env     = TerrainTraversalEnv(direction=args.direction)
    out_dir = VID_DIR / f"{args.out}_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for method in METHODS:
        entries = [e for e in list_terrains([method])][: args.seeds_per_method]
        for entry in entries:
            images, info, worst_pen = eval_one(env, planner, entry, args.max_frames)
            status = ("SUCCESS" if info.get("success")
                      else "FALL" if info.get("fall") else "TIMEOUT")
            if images:
                gif = out_dir / f"{entry.method}_seed{entry.seed:02d}.gif"
                images[0].save(str(gif), save_all=True, append_images=images[1:],
                               loop=0, duration=int(1000 / FPS), optimize=False)
            print(f"  {entry.method:12s} seed{entry.seed:02d}  {status:8s} "
                  f"dist={info.get('dist', 0):5.1f}  worst_pen={worst_pen:.3f}")
            results.append({"method": entry.method, "seed": entry.seed,
                            "dist": info.get("dist", 0.0), "status": status,
                            "worst_pen": worst_pen})

    n_succ = sum(1 for r in results if r["status"] == "SUCCESS")
    print(f"\n[{label}] {n_succ}/{len(results)} success  "
          f"mean_dist={np.mean([r['dist'] for r in results]):.1f}  "
          f"worst_pen_overall={min(r['worst_pen'] for r in results):.3f}")
    print(f"GIFs → {out_dir}")


if __name__ == "__main__":
    main()
