"""
Evaluate trained models on test terrain set and save GIF visualizations.

Uses RolloutPlanner for physics-based action selection (N candidates, K lookahead).

Output: robot_vis/vid/ppo_right/terrain_NN.gif
        robot_vis/vid/ppo_left/terrain_NN.gif
"""

import json
import math
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from robot_training.env.terrain_env import TerrainTraversalEnv, DT
from robot_training.models.policy import load_policy
from robot_training.planning.rollout_planner import RolloutPlanner
from robot_training.dataset import TerrainEntry
from robot_vis.renderer import world_to_px, draw_robot

VID_DIR   = Path(__file__).parent.parent.parent / "robot_vis" / "vid"
FPS       = int(round(1.0 / DT))

FRAME_W   = 1400
FRAME_H   = 600
BG_COLOR  = (20, 20, 35)
ENV_COLOR = (180, 180, 180)
TEXT_CLR  = (230, 230, 230)
ROBOT_COLORS = {
    "body":         (80, 200, 80),
    "upper":        (80, 140, 220),
    "lower":        (220, 80, 80),
    "foot_planted": (255, 220, 60),
    "foot_free":    (180, 180, 180),
    "mount":        (180, 220, 255),
}


def _env_scale_centre(w, h, env_left, env_right, env_height=7.0):
    world_w = env_right - env_left
    margin  = 0.06
    scale   = min(w * (1 - 2 * margin) / world_w,
                  h * (1 - 2 * margin) / env_height)
    cx = w / 2 - (env_left + world_w / 2) * scale
    cy = h * 0.82
    return cx, cy, scale


def _render_frame(pose, terrain_meta, cx, cy, scale, label) -> Image.Image:
    img  = Image.new("RGB", (FRAME_W, FRAME_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Draw terrain segments
    for seg in terrain_meta["segments"]:
        pa = world_to_px((seg["x1"], seg["y1"]), cx, cy, scale)
        pb = world_to_px((seg["x2"], seg["y2"]), cx, cy, scale)
        draw.line([pa, pb], fill=ENV_COLOR, width=4)

    # Draw walls
    for wx in (terrain_meta["env_left"], terrain_meta["env_right"]):
        pa = world_to_px((wx, 0), cx, cy, scale)
        pb = world_to_px((wx, 6), cx, cy, scale)
        draw.line([pa, pb], fill=(100, 160, 220), width=5)

    # Draw robot
    draw_robot(draw, pose, cx, cy, scale, ROBOT_COLORS)

    draw.text((12, 12), label, fill=TEXT_CLR)
    return img


def _evaluate_single(
    policy,
    planner: RolloutPlanner,
    env: TerrainTraversalEnv,
    entry: TerrainEntry,
    device: torch.device,
    max_frames: int = 600,
) -> tuple[list[Image.Image], dict]:
    obs  = env.reset(entry)
    done = False
    fi   = 0

    with open(entry.path) as f:
        terrain_meta = json.load(f)

    env_l = terrain_meta["env_left"]
    env_r = terrain_meta["env_right"]
    cx, cy, scale = _env_scale_centre(FRAME_W, FRAME_H, env_l, env_r)

    images = []
    info   = {}

    # Reset planner's LSTM hidden state for each new episode
    planner.reset_hidden()

    while not done and fi < max_frames:
        pose      = env.render()
        bx, by, bth, vx, vy, _ = env._physics.get_body_state()
        n_contact = sum(env._physics._foot_contact)
        lbl = (f"{entry.method}:{entry.seed}  frame={fi:03d}  "
               f"x={bx:.2f}  vx={vx:.2f}  ct={n_contact}  pitch={bth:.2f}")
        images.append(_render_frame(pose, terrain_meta, cx, cy, scale, lbl))

        # Physics-lookahead + value-guided action selection
        joint_targets = planner.act(obs, env._physics, env._lmap, env.direction)
        action_norm   = joint_targets / math.pi
        obs, _, done, info = env.step(action_norm)
        fi += 1

    return images, info


def evaluate_direction(
    direction: int,
    model_path: str | Path,
    test_entries: list[TerrainEntry],
    max_frames: int = 600,
    device: torch.device = None,
    out_subdir: str = "ppo",
) -> None:
    if device is None:
        device = torch.device("cpu")

    label   = "right" if direction > 0 else "left"
    out_dir = VID_DIR / f"{out_subdir}_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    policy  = load_policy(str(model_path), device)
    planner = RolloutPlanner(policy, device, n_candidates=12, lookahead=4)
    env     = TerrainTraversalEnv(direction=direction)

    results = []
    for entry in test_entries:
        print(f"  Evaluating [{label}] {entry.method}:seed{entry.seed} ...")
        images, info = _evaluate_single(policy, planner, env, entry, device, max_frames)
        if not images:
            print("    No frames generated, skipping")
            continue

        tag      = f"{entry.method}_seed{entry.seed:02d}"
        gif_path = out_dir / f"{tag}.gif"
        images[0].save(
            str(gif_path),
            save_all=True,
            append_images=images[1:],
            loop=0,
            duration=int(1000 / FPS),
            optimize=False,
        )
        status = "SUCCESS" if info.get("success") else ("FALL" if info.get("fall") else "TIMEOUT")
        print(f"    {status}  dist={info.get('dist', 0):.1f}  frames={len(images)} → {gif_path}")
        results.append({"method": entry.method, "seed": entry.seed,
                        "dist": info.get("dist", 0), "status": status})

    n_succ = sum(1 for r in results if r["status"] == "SUCCESS")
    mean_d = np.mean([r["dist"] for r in results]) if results else 0.0
    print(f"\n  [{label}] test results: {n_succ}/{len(results)} success  mean_dist={mean_d:.1f}")
