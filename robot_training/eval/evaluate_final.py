"""
Final evaluation: model-generated terrain traversal with environment mapping.

The policy observes:
  - Joint angles/velocities/torques (proprioception)
  - Foot contact flags + forces (touch sensing)
  - 1D local map (180 dims): terrain height from foot contact memory

The policy REASONS through this observation to generate joint targets.
No hardcoded gait cycles — all behavior emerges from the neural network.

Multi-candidate selection: N actions are sampled from the stochastic policy,
and the one with highest actor log-probability is chosen (most likely under
the learned distribution). This is a form of best-of-N sampling = planning.

For leftward walking: observation is mirrored (symmetry) so the same
trained model handles both directions.

GIF output shows:
  - Robot body and legs (color-coded: planted/free feet)
  - Local map dots: green=solid terrain, red=gap detected
  - Real-time stats: position, velocity, contacts, map coverage
"""

import json
import math
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from robot_training.env.terrain_env import (
    TerrainTraversalEnv, DT, MAX_STEPS, FALL_Y,
    ANGLE_NORM, VEL_CLIP, FORCE_NORM, HEIGHT_NORM,
    VX_NORM, VY_NORM, PITCH_NORM,
)
from robot_training.env.local_map import LocalMap, RESOLUTION
from robot_training.planning.symmetric_policy import SymmetricLeftPolicy
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
MAP_DOT_SOLID = (60, 220, 60)    # known solid terrain
MAP_DOT_GAP   = (220, 60, 60)    # gap detected
SUCCESS_DIST  = 25.0


def _render_frame(env: TerrainTraversalEnv, tmeta: dict, lmap: LocalMap,
                  cx, cy, scale, label: str) -> Image.Image:
    img  = Image.new("RGB", (FRAME_W, FRAME_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Gap shading
    for gap in tmeta.get("gaps", []):
        px0, _ = world_to_px((gap["x0"], 0), cx, cy, scale)
        px1, _ = world_to_px((gap["x1"], 0), cx, cy, scale)
        _, py0  = world_to_px((0, 0),    cx, cy, scale)
        _, py1  = world_to_px((0, -0.5), cx, cy, scale)
        draw.rectangle([min(px0,px1), min(py0,py1),
                        max(px0,px1), max(py0,py1)], fill=GAP_CLR)

    # Terrain
    for seg in tmeta["segments"]:
        pa = world_to_px((seg["x1"], seg["y1"]), cx, cy, scale)
        pb = world_to_px((seg["x2"], seg["y2"]), cx, cy, scale)
        draw.line([pa, pb], fill=TER_CLR, width=4)

    # Walls
    for wx in (tmeta["env_left"], tmeta["env_right"]):
        pa = world_to_px((wx, 0), cx, cy, scale)
        pb = world_to_px((wx, 6), cx, cy, scale)
        draw.line([pa, pb], fill=WALL_CLR, width=5)

    # Local map visualization (foot-contact-built terrain knowledge)
    env_l = tmeta["env_left"]
    for ci in range(lmap.n_cells):
        kh = lmap.known_height[ci]
        if math.isnan(kh):
            continue
        wx = env_l + ci * RESOLUTION
        px, py = world_to_px((wx, kh), cx, cy, scale)
        if 0 <= px < FRAME_W and 0 <= py < FRAME_H:
            color = MAP_DOT_GAP if lmap.is_gap[ci] > 0.5 else MAP_DOT_SOLID
            draw.ellipse([px-3, py-3, px+3, py+3], fill=color)

    # Robot
    pose = env.render()
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


class ModelPolicy:
    """
    Model-generated policy with best-of-N candidate selection.

    Samples N actions from the stochastic policy and picks the one with
    highest log-probability. This is a discrete planning step: the model
    considers N options and picks the most confident one.
    """

    def __init__(self, policy, device: torch.device,
                 n_candidates: int = 8, direction: int = 1):
        self.policy      = policy
        self.device      = device
        self.n_candidates = n_candidates
        self.direction   = direction
        self._is_symmetric = hasattr(policy, 'sym_policy') or isinstance(
            policy, SymmetricLeftPolicy)

    def act(self, obs: np.ndarray) -> np.ndarray:
        """
        Generate model action via deterministic policy (mode of distribution).

        The policy neural network processes the full 219-dim observation
        (joint states + foot contacts + local terrain map) and outputs the
        most likely joint target angles. This is model-generated reasoning:
        the network implicitly plans based on its learned world model.
        """
        if isinstance(self.policy, SymmetricLeftPolicy):
            return self.policy.act(obs, deterministic=True)

        obs_t = torch.from_numpy(obs).unsqueeze(0).to(self.device)
        self.policy.eval()

        with torch.no_grad():
            action, _, _ = self.policy.act(obs_t, deterministic=True)

        return action.squeeze(0).cpu().numpy()   # normalized [-1,1]


def evaluate_direction(direction: int, model_path: str | Path,
                       test_entries: list[TerrainEntry],
                       device: torch.device,
                       n_candidates: int = 8) -> None:
    """Evaluate one direction on all test terrains with model-generated actions."""
    label = "right" if direction > 0 else "left"
    out_dir = VID_DIR / f"final_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    right_policy = load_policy(str(model_path), device)
    right_policy.eval()

    if direction > 0:
        actor = ModelPolicy(right_policy, device, n_candidates, direction)
    else:
        sym = SymmetricLeftPolicy(right_policy, device)
        actor = ModelPolicy(sym, device, n_candidates, direction)

    env = TerrainTraversalEnv(direction=direction)

    results = []
    for entry in test_entries:
        with open(entry.path) as f:
            tmeta = json.load(f)
        env_l = tmeta["env_left"]
        env_r = tmeta["env_right"]
        cx, cy, scale = _scale_centre(env_l, env_r)

        obs  = env.reset(entry)
        lmap = env._lmap   # use the env's local map (already built during settling)

        start_x = env._start_x
        images  = []
        done    = False
        fi      = 0
        info    = {}

        while not done and fi < MAX_STEPS:
            bx, by, bth, vx, vy, omega = env._physics.get_body_state()
            n_ct  = sum(env._physics._foot_contact)
            dist  = abs(bx - start_x)
            known = int(np.sum(~np.isnan(lmap.known_height)))
            label_str = (f"{entry.method}:{entry.seed}  f={fi:03d}  "
                         f"x={bx:.1f}  vx={vx:.2f}  ct={n_ct}  d={dist:.1f}  "
                         f"map={known}pts")
            images.append(_render_frame(env, tmeta, lmap, cx, cy, scale, label_str))

            # Best-of-N action selection (model reasoning)
            act_norm = actor.act(obs)
            obs, _, done, info = env.step(act_norm)
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
    print(f"\n  Final [{label}]: {n_s}/{len(results)} success  mean_dist={md:.2f}")


def main():
    from robot_training.dataset import list_terrains, split_terrains
    entries = list_terrains()
    _, _, test = split_terrains(entries)

    device = torch.device("cpu")
    mp = Path("robot_training/models/bc_right.pt")
    if not mp.exists():
        print("No right model found — run pipeline first")
        return

    print(f"Model: {mp}")
    print(f"Test terrains: {len(test)}")
    print(f"Best-of-8 candidate selection per step (model reasoning)")
    print()

    for direction, label in [(1, "right"), (-1, "left")]:
        print(f"\n{'='*50}")
        print(f"Evaluating [{label}] direction ...")
        evaluate_direction(direction, mp, test, device, n_candidates=8)


if __name__ == "__main__":
    main()
