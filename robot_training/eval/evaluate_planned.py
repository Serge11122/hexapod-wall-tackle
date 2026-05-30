"""
Evaluate robot traversal using planned rollouts and reasoning.

For EACH decision step:
  1. Policy samples N candidate actions (model explores options)
  2. Each candidate is simulated K steps forward in physics
  3. Accumulated reward + bootstrap value determines best action
  4. Best action is applied to real physics

Left model: uses symmetric observation flipping of the right model
(no separate left model needed — physics is symmetric in 2D)

All actions are model-generated — no hardcoded gait.
"""

import json
import math
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from robot_training.env.terrain_physics import TerrainRobotPhysics, WALK_HEIGHT
from robot_training.env.local_map import LocalMap
from robot_training.env.terrain_env import (
    ANGLE_NORM, VEL_CLIP, FORCE_NORM, HEIGHT_NORM,
    VX_NORM, VY_NORM, PITCH_NORM, FALL_Y, MAX_STEPS,
)
from robot_training.planning.rollout_planner import RolloutPlanner, _build_obs
from robot_training.planning.symmetric_policy import SymmetricLeftPolicy
from robot_training.models.policy import load_policy
from robot_training.dataset import TerrainEntry
from robot_vis.renderer import world_to_px, draw_robot

VID_DIR  = Path(__file__).parent.parent.parent / "robot_vis" / "vid"
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

SUCCESS_DIST = 25.0
DT           = 0.1
GIF_FPS      = 10
MAP_LINES    = 20   # number of local map cells to visualize per frame


def _render_frame(phys: TerrainRobotPhysics, tmeta: dict,
                  lmap: LocalMap, cx, cy, scale,
                  label: str, direction: int) -> Image.Image:
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

    # Terrain segments
    for seg in tmeta["segments"]:
        pa = world_to_px((seg["x1"], seg["y1"]), cx, cy, scale)
        pb = world_to_px((seg["x2"], seg["y2"]), cx, cy, scale)
        draw.line([pa, pb], fill=TER_CLR, width=4)

    # Boundary walls
    for wx in (tmeta["env_left"], tmeta["env_right"]):
        pa = world_to_px((wx, 0), cx, cy, scale)
        pb = world_to_px((wx, 6), cx, cy, scale)
        draw.line([pa, pb], fill=WALL_CLR, width=5)

    # Draw local map (what the robot knows about terrain)
    bx = phys.body.position.x
    env_l = tmeta["env_left"]
    from robot_training.env.local_map import RESOLUTION
    for ci in range(min(lmap.n_cells, int((tmeta["env_right"] - env_l) / RESOLUTION))):
        wx = env_l + ci * RESOLUTION
        kh = lmap.known_height[ci]
        if not math.isnan(kh):
            px, py = world_to_px((wx, kh), cx, cy, scale)
            color = (40, 200, 40) if lmap.is_gap[ci] < 0.5 else (200, 40, 40)
            draw.ellipse([px-2, py-2, px+2, py+2], fill=color)

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


def evaluate_one(planner, phys: TerrainRobotPhysics,
                 lmap: LocalMap, tmeta: dict,
                 entry: TerrainEntry, direction: int,
                 out_path: Path, max_steps: int = MAX_STEPS) -> dict:
    """Evaluate one terrain episode with planned rollouts. Returns info dict."""
    env_l  = tmeta["env_left"]
    env_r  = tmeta["env_right"]
    cx, cy, scale = _scale_centre(env_l, env_r)

    # Settle: run 8 policy steps to establish footing before measuring
    start_obs = _build_obs(phys, lmap, direction)
    for i in range(8):
        action = planner.act(start_obs, phys, lmap, direction)
        phys.step(action)

    start_x  = phys.body.position.x
    images   = []
    done     = False
    fi       = 0
    info     = {}

    while not done and fi < max_steps:
        bx, by, bth, vx, vy, omega = phys.get_body_state()
        n_ct  = sum(phys._foot_contact)
        dist  = abs(bx - start_x)

        # Build and show local map info
        known_cells = int(np.sum(~np.isnan(lmap.known_height)))
        label_str = (f"{entry.method}:{entry.seed}  f={fi:03d}  "
                     f"x={bx:.1f}  vx={vx:.2f}  ct={n_ct}  d={dist:.1f}  "
                     f"map={known_cells}cells")
        images.append(_render_frame(phys, tmeta, lmap, cx, cy, scale,
                                    label_str, direction))

        # Plan: simulate candidates and pick best action
        obs = _build_obs(phys, lmap, direction)
        joint_targets = planner.act(obs, phys, lmap, direction)
        phys.step(joint_targets)
        fi += 1

        bx2, by2 = phys.body.position
        dist2 = abs(bx2 - start_x)
        terrain_h = phys._terrain_height_est
        if by2 < terrain_h + FALL_Y:
            info = {"dist": dist2, "fall": True, "success": False}
            done = True
        elif dist2 >= SUCCESS_DIST:
            info = {"dist": dist2, "fall": False, "success": True}
            done = True

    if not info:
        info = {"dist": abs(phys.body.position.x - start_x),
                "fall": False, "success": False}

    if images:
        images[0].save(str(out_path), save_all=True,
                       append_images=images[1:],
                       loop=0, duration=int(1000/GIF_FPS), optimize=False)

    return info


def evaluate_direction(direction: int, model_path: str | Path,
                       test_entries: list[TerrainEntry],
                       device: torch.device,
                       n_candidates: int = 8, lookahead: int = 4) -> None:
    """Run planned-rollout evaluation for one direction on all test terrains."""
    label = "right" if direction > 0 else "left"
    out_dir = VID_DIR / f"planned_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load right model (used for both directions)
    right_policy = load_policy(str(model_path), device)
    right_policy.eval()

    if direction > 0:
        # Right: use direct planner with right policy
        planner = RolloutPlanner(right_policy, device,
                                 n_candidates=n_candidates, lookahead=lookahead)
    else:
        # Left: symmetric policy wraps right policy
        sym_policy = SymmetricLeftPolicy(right_policy, device)
        # Build a planner that uses the symmetric policy
        planner = SymmetricRolloutPlanner(sym_policy, right_policy, device,
                                          n_candidates=n_candidates, lookahead=lookahead)

    results = []
    for entry in test_entries:
        with open(entry.path) as f:
            tmeta = json.load(f)

        if direction > 0:
            sx, sy = entry.drop_left
        else:
            sx, sy = entry.drop_right

        phys = TerrainRobotPhysics(dt=DT, terrain_json=str(entry.path),
                                   start_x=sx, start_y=sy)
        lmap = LocalMap(env_left=tmeta["env_left"], env_right=tmeta["env_right"])

        tag      = f"{entry.method}_seed{entry.seed:02d}"
        out_path = out_dir / f"{tag}.gif"

        info = evaluate_one(planner, phys, lmap, tmeta, entry, direction, out_path)

        status = "SUCCESS" if info["success"] else ("FALL" if info["fall"] else "TIMEOUT")
        print(f"  [{label}] {entry.method}:{entry.seed}  {status}  "
              f"dist={info['dist']:.2f} → {out_path.name}")
        results.append(info)

    n_s = sum(1 for r in results if r.get("success"))
    md  = np.mean([r["dist"] for r in results]) if results else 0
    print(f"\n  Planned [{label}]: {n_s}/{len(results)} success  mean_dist={md:.2f}")


class SymmetricRolloutPlanner:
    """Rollout planner using the symmetric left policy."""

    def __init__(self, sym_policy: SymmetricLeftPolicy,
                 right_policy: ActorCritic, device: torch.device,
                 n_candidates: int = 8, lookahead: int = 4,
                 gamma: float = 0.99):
        self.sym_policy   = sym_policy
        self.right_policy = right_policy
        self.device       = device
        self.n_candidates = n_candidates
        self.lookahead    = lookahead
        self.gamma        = gamma

    def act(self, obs: np.ndarray, phys: TerrainRobotPhysics,
            lmap: LocalMap, direction: int) -> np.ndarray:
        from robot_training.planning.rollout_planner import (
            _snapshot_physics, _restore_physics, _save_lmap, _restore_lmap,
            _step_reward,
        )
        from robot_training.planning.symmetric_policy import mirror_observation

        # Save state
        saved_state = _snapshot_physics(phys)
        saved_lmap  = _save_lmap(lmap)
        start_x     = phys.body.position.x

        # Generate candidates using symmetric policy
        candidates = []
        for _ in range(self.n_candidates):
            jt, lp, val = self.sym_policy.act_stochastic(obs)
            candidates.append((jt, val))
        # Add deterministic
        det_jt = self.sym_policy.act(obs, deterministic=True)
        candidates.append((det_jt, 0.0))

        best_score  = -1e9
        best_action = candidates[-1][0]

        for jt, init_val in candidates:
            _restore_physics(phys, saved_state)
            _restore_lmap(lmap, saved_lmap)

            total_reward = 0.0
            prev_x       = start_x
            candidate_ok = True

            joint_targets = jt
            for step in range(self.lookahead):
                phys.step(joint_targets)
                rew, done, cur_x = _step_reward(phys, prev_x, direction)
                total_reward += (self.gamma ** step) * rew
                prev_x = cur_x
                if done:
                    total_reward -= 20.0
                    candidate_ok = False
                    break
                if step < self.lookahead - 1:
                    sim_obs = _build_obs(phys, lmap, direction)
                    joint_targets = self.sym_policy.act(sim_obs, deterministic=True)

            if candidate_ok:
                sim_obs = _build_obs(phys, lmap, direction)
                mirror_obs = mirror_observation(sim_obs)
                obs_t = torch.from_numpy(mirror_obs).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    _, _, boot_v = self.right_policy.act(obs_t, deterministic=True)
                total_reward += (self.gamma ** self.lookahead) * boot_v.item()

            score = total_reward + init_val * 0.5
            if score > best_score:
                best_score  = score
                best_action = jt

        _restore_physics(phys, saved_state)
        _restore_lmap(lmap, saved_lmap)
        return best_action


def main():
    from robot_training.dataset import list_terrains, split_terrains
    entries = list_terrains()
    _, _, test = split_terrains(entries)

    device = torch.device("cpu")
    mp = Path("robot_training/models/bc_right.pt")
    if not mp.exists():
        print("No right model found")
        return

    print(f"Evaluating with planned rollouts on {len(test)} test terrains...")
    print("  n_candidates=8, lookahead=4 steps")
    print()
    for direction, label in [(1, "right"), (-1, "left")]:
        print(f"\n--- {label.upper()} ---")
        evaluate_direction(direction, mp, test, device,
                           n_candidates=8, lookahead=4)


if __name__ == "__main__":
    main()
