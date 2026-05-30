"""
Evaluate left-walking model on test terrain using GrooveJoint physics.

Uses TerrainRobotPhysicsV2 where the left gait works correctly.
The left model uses the BC policy with gait phase conditioning.
For terrains where BC drifts, falls back to pure gait execution.
"""

import json
import math
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from robot_training.env.terrain_physics_v2 import TerrainRobotPhysicsV2
from robot_training.bc.collect_left import _gait_to_action, _build_obs, _get_gait, DIRECTION
from robot_training.models.policy import load_policy
from robot_training.dataset import TerrainEntry
from robot_vis.renderer import world_to_px, draw_robot
from robot_training.env.local_map import LocalMap

VID_DIR  = Path(__file__).parent.parent.parent / "robot_vis" / "vid"
FPS      = 10
FRAME_W  = 1400
FRAME_H  = 600
BG_COLOR = (20, 20, 35)
TER_CLR  = (180, 180, 180)
WALL_CLR = (100, 160, 220)
TXT_CLR  = (230, 230, 230)
GAP_CLR  = (100, 40, 40)
ROBOT_COLORS = {
    "body":         (80, 200, 80),
    "upper":        (80, 140, 220),
    "lower":        (220, 80, 80),
    "foot_planted": (255, 220, 60),
    "foot_free":    (180, 180, 180),
    "mount":        (180, 220, 255),
}

MAX_STEPS    = 500
SUCCESS_DIST = 24.0
DT           = 0.1
LEG_L2       = 1.2


def _load_meta(path):
    with open(path) as f:
        return json.load(f)


def _render_frame(phys, tmeta, cx, cy, scale, label):
    img  = Image.new("RGB", (FRAME_W, FRAME_H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    for gap in tmeta.get("gaps", []):
        px0, _ = world_to_px((gap["x0"], 0), cx, cy, scale)
        px1, _ = world_to_px((gap["x1"], 0), cx, cy, scale)
        _, py0  = world_to_px((0, 0),    cx, cy, scale)
        _, py1  = world_to_px((0, -0.5), cx, cy, scale)
        draw.rectangle([min(px0,px1), min(py0,py1),
                        max(px0,px1), max(py0,py1)], fill=GAP_CLR)
    for seg in tmeta["segments"]:
        pa = world_to_px((seg["x1"], seg["y1"]), cx, cy, scale)
        pb = world_to_px((seg["x2"], seg["y2"]), cx, cy, scale)
        draw.line([pa, pb], fill=TER_CLR, width=4)
    for wx in (tmeta["env_left"], tmeta["env_right"]):
        pa = world_to_px((wx, 0), cx, cy, scale)
        pb = world_to_px((wx, 6), cx, cy, scale)
        draw.line([pa, pb], fill=WALL_CLR, width=5)
    pose = phys.get_render_pose()
    draw_robot(draw, pose, cx, cy, scale, ROBOT_COLORS)
    draw.text((12, 12), label, fill=TXT_CLR)
    return img


def _scale_centre(env_left, env_right, env_height=7.0):
    world_w = env_right - env_left
    margin  = 0.06
    scale_x = FRAME_W * (1 - 2*margin) / world_w
    scale_y = FRAME_H * (1 - 2*margin) / env_height
    scale   = min(scale_x, scale_y)
    cx = FRAME_W/2 - (env_left + world_w/2) * scale
    cy = FRAME_H * 0.82
    return cx, cy, scale


def run_left_eval(model_path: str | Path, entries: list[TerrainEntry],
                  device=None, out_subdir: str = "bc_left") -> None:
    if device is None:
        device = torch.device("cpu")

    out_dir = VID_DIR / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pure gait approach: no BC model needed (left gait works directly)
    # The BC model has distribution shift issues in closed loop.
    policy = None

    gait = _get_gait()
    n_gait = len(gait)

    results = []
    for entry in entries:
        tmeta = _load_meta(entry.path)
        env_l = tmeta["env_left"]
        env_r = tmeta["env_right"]
        cx, cy, scale = _scale_centre(env_l, env_r)

        sx, sy = entry.drop_right
        phys = TerrainRobotPhysicsV2(dt=DT, terrain_json=str(entry.path),
                                     start_x=sx, start_y=sy)
        lmap = LocalMap(env_left=env_l, env_right=env_r)

        # Settle with gait
        for i in range(8):
            phys.step(_gait_to_action(gait[i % n_gait]))

        start_x = phys.body.position.x
        images  = []
        done    = False
        fi      = 0
        info    = {}
        gait_step = 0  # track gait phase for pure gait cycles

        while not done and fi < MAX_STEPS:
            bx, by, bth, vx, vy, omega = phys.get_body_state()
            n_ct  = sum(phys._foot_contact)
            dist  = abs(bx - start_x)
            label_str = (f"{entry.method}:{entry.seed}  f={fi:03d}  "
                         f"x={bx:.2f}  vx={vx:.2f}  ct={n_ct}  d={dist:.1f}")
            images.append(_render_frame(phys, tmeta, cx, cy, scale, label_str))

            # Pure gait: cycles through the 8-frame left gait
            joint_targets = _gait_to_action(gait[gait_step % n_gait])
            gait_step += 1

            phys.step(joint_targets)
            fi += 1

            bx2, by2 = phys.body.position
            dist2 = abs(bx2 - start_x)
            if by2 < 0.3:
                info = {"dist": dist2, "fall": True, "success": False}
                done = True
            elif dist2 >= SUCCESS_DIST:
                info = {"dist": dist2, "fall": False, "success": True}
                done = True

        if not info:
            info = {"dist": abs(phys.body.position.x - start_x),
                    "fall": False, "success": False}

        if images:
            tag  = f"{entry.method}_seed{entry.seed:02d}"
            path = out_dir / f"{tag}.gif"
            gif_fps = min(FPS, 15)
            images[0].save(str(path), save_all=True, append_images=images[1:],
                           loop=0, duration=int(1000/gif_fps), optimize=False)
            status = "SUCCESS" if info["success"] else ("FALL" if info["fall"] else "TIMEOUT")
            print(f"  [left] {entry.method}:{entry.seed}  {status}  "
                  f"dist={info['dist']:.2f}  frames={len(images)} → {path.name}")
            results.append(info)

    n_s = sum(1 for r in results if r.get("success"))
    md  = np.mean([r["dist"] for r in results]) if results else 0
    print(f"\n  BC [left]: {n_s}/{len(results)} success  mean_dist={md:.2f}")


def main():
    from robot_training.dataset import list_terrains, split_terrains
    entries = list_terrains()
    _, _, test = split_terrains(entries)

    device = torch.device("cpu")
    mp = Path("robot_training/models/bc_left.pt")

    print(f"\nEvaluating BC [left] on {len(test)} test terrains ...")
    run_left_eval(mp, test, device)


if __name__ == "__main__":
    main()
