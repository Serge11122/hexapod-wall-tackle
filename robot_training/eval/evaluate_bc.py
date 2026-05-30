"""
Evaluate BC-pretrained models on test terrain using TerrainTraversalEnv.

Uses the same physics (gravity-compensated height spring) as BC training
to eliminate distribution shift between train and eval.
"""

import json
import math
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from robot_training.env.terrain_env import TerrainTraversalEnv, DT
from robot_training.models.policy import load_policy
from robot_training.dataset import TerrainEntry
from robot_vis.renderer import world_to_px, draw_robot

VID_DIR  = Path(__file__).parent.parent.parent / "robot_vis" / "vid"
FPS      = int(round(1.0 / DT))
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

MAX_STEPS    = 600
SUCCESS_DIST = 25.0


def _load_terrain_meta(path):
    with open(path) as f:
        return json.load(f)


def _render_frame(env: TerrainTraversalEnv, terrain_meta: dict,
                  cx, cy, scale, label: str) -> Image.Image:
    img  = Image.new("RGB", (FRAME_W, FRAME_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    for gap in terrain_meta.get("gaps", []):
        px0, _ = world_to_px((gap["x0"], 0), cx, cy, scale)
        px1, _ = world_to_px((gap["x1"], 0), cx, cy, scale)
        _, py0  = world_to_px((0, 0),    cx, cy, scale)
        _, py1  = world_to_px((0, -0.5), cx, cy, scale)
        draw.rectangle([min(px0,px1), min(py0,py1),
                        max(px0,px1), max(py0,py1)], fill=GAP_CLR)

    for seg in terrain_meta["segments"]:
        pa = world_to_px((seg["x1"], seg["y1"]), cx, cy, scale)
        pb = world_to_px((seg["x2"], seg["y2"]), cx, cy, scale)
        draw.line([pa, pb], fill=TER_CLR, width=4)

    for wx in (terrain_meta["env_left"], terrain_meta["env_right"]):
        pa = world_to_px((wx, 0), cx, cy, scale)
        pb = world_to_px((wx, 6), cx, cy, scale)
        draw.line([pa, pb], fill=WALL_CLR, width=5)

    pose = env.render()
    draw_robot(draw, pose, cx, cy, scale, ROBOT_COLORS)
    draw.text((12, 12), label, fill=TXT_CLR)
    return img


def _env_scale_centre(env_left, env_right, env_height=7.0):
    world_w = env_right - env_left
    margin  = 0.06
    scale_x = FRAME_W * (1 - 2*margin) / world_w
    scale_y = FRAME_H * (1 - 2*margin) / env_height
    scale   = min(scale_x, scale_y)
    cx = FRAME_W/2 - (env_left + world_w/2) * scale
    cy = FRAME_H * 0.82
    return cx, cy, scale


def run_bc_eval(direction: int, model_path: str | Path, entries: list[TerrainEntry],
                device=None) -> None:
    if device is None:
        device = torch.device("cpu")

    label = "right" if direction > 0 else "left"
    out_dir = VID_DIR / f"bc_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    policy = load_policy(str(model_path), device)
    policy.eval()

    results = []
    for entry in entries:
        tmeta = _load_terrain_meta(entry.path)
        env_l = tmeta["env_left"]
        env_r = tmeta["env_right"]
        cx, cy, scale = _env_scale_centre(env_l, env_r)

        env = TerrainTraversalEnv(direction=direction)
        obs = env.reset(entry)

        start_x = env._start_x
        images  = []
        done    = False
        fi      = 0
        info    = {}

        while not done and fi < MAX_STEPS:
            bx, by, bth, vx, vy, omega = env._physics.get_body_state()
            n_ct  = sum(env._physics._foot_contact)
            dist  = abs(bx - start_x)
            label_str = (f"{entry.method}:{entry.seed}  "
                         f"f={fi:03d}  x={bx:.2f}  vx={vx:.2f}  "
                         f"ct={n_ct}  d={dist:.1f}")
            images.append(_render_frame(env, tmeta, cx, cy, scale, label_str))

            obs_t  = torch.from_numpy(obs).unsqueeze(0).to(device)
            with torch.no_grad():
                action, _, _ = policy.act(obs_t, deterministic=True)
            act_np = action.squeeze(0).cpu().numpy()

            obs, reward, done, info = env.step(act_np)
            fi += 1

        if not info:
            info = {"dist": abs(env._physics.body.position.x - start_x),
                    "fall": False, "success": False}

        if images:
            tag  = f"{entry.method}_seed{entry.seed:02d}"
            path = out_dir / f"{tag}.gif"
            gif_fps = min(FPS, 15)
            images[0].save(str(path), save_all=True, append_images=images[1:],
                           loop=0, duration=int(1000/gif_fps), optimize=False)
            status = "SUCCESS" if info["success"] else ("FALL" if info["fall"] else "TIMEOUT")
            print(f"  [{label}] {entry.method}:{entry.seed}  {status}  "
                  f"dist={info['dist']:.2f}  frames={len(images)} → {path.name}")
            results.append(info)

    n_s = sum(1 for r in results if r.get("success"))
    md  = np.mean([r["dist"] for r in results]) if results else 0
    print(f"\n  BC [{label}]: {n_s}/{len(results)} success  mean_dist={md:.2f}")


def main():
    from robot_training.dataset import list_terrains, split_terrains
    entries = list_terrains()
    _, _, test = split_terrains(entries)

    device = torch.device("cpu")
    root   = Path(__file__).parent.parent / "models"
    for direction, label in [(1, "right"), (-1, "left")]:
        mp = root / f"bc_{label}.pt"
        if not mp.exists():
            print(f"No BC model for {label}, skipping")
            continue
        print(f"\nEvaluating BC [{label}] on {len(test)} test terrains ...")
        run_bc_eval(direction, mp, test, device)


if __name__ == "__main__":
    main()
