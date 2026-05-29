"""
Evaluate BC-pretrained models on test terrain using V2 physics (GrooveJoint).

BC models were trained on flat terrain with GrooveJoint — V2 physics matches
those training conditions, so BC locomotion should work.  Best-performing
terrain runs are saved as GIFs in robot_vis/vid/bc_right/ and bc_left/.
"""

import json
import math
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from robot_training.env.terrain_physics_v2 import TerrainRobotPhysicsV2, WALK_HEIGHT
from robot_training.models.policy import load_policy
from robot_training.dataset import TerrainEntry
from robot_vis.renderer import world_to_px, draw_robot

VID_DIR  = Path(__file__).parent.parent.parent / "robot_vis" / "vid"
FPS      = 5
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

MAX_STEPS    = 400
FALL_Y       = 0.2
SUCCESS_DIST = 25.0


def _render_frame(phys: TerrainRobotPhysicsV2, terrain_meta: dict,
                  cx, cy, scale, label: str) -> Image.Image:
    img  = Image.new("RGB", (FRAME_W, FRAME_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Gap shading
    for gap in terrain_meta.get("gaps", []):
        px0, _ = world_to_px((gap["x0"], 0), cx, cy, scale)
        px1, _ = world_to_px((gap["x1"], 0), cx, cy, scale)
        _, py0  = world_to_px((0, 0),   cx, cy, scale)
        _, py1  = world_to_px((0, -0.5), cx, cy, scale)
        draw.rectangle([min(px0,px1), min(py0,py1), max(px0,px1), max(py0,py1)], fill=GAP_CLR)

    # Terrain segments
    for seg in terrain_meta["segments"]:
        pa = world_to_px((seg["x1"], seg["y1"]), cx, cy, scale)
        pb = world_to_px((seg["x2"], seg["y2"]), cx, cy, scale)
        draw.line([pa, pb], fill=TER_CLR, width=4)

    # Walls
    for wx in (terrain_meta["env_left"], terrain_meta["env_right"]):
        pa = world_to_px((wx, 0), cx, cy, scale)
        pb = world_to_px((wx, 6), cx, cy, scale)
        draw.line([pa, pb], fill=WALL_CLR, width=5)

    pose = phys.get_render_pose()
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

    # Load correct gait for settling
    import json as _json
    gait_path = Path(__file__).parent.parent.parent / "robot_motion" / f"gait_{label}.json"
    with open(gait_path) as f:
        gait = _json.load(f)["frames"]
    n_gait   = len(gait)

    from robot_training.env.terrain_env import _gait_frame_to_action, OBS_DIM, ACT_DIM
    from robot_training.env.local_map import LocalMap, OBS_SIZE as MAP_OBS_SIZE
    from robot_training.env.terrain_env import (
        JOINT_DIM, VEL_DIM, TORQ_DIM, CONT_DIM, FORC_DIM, FHGT_DIM,
        BVEL_DIM, PITCH_DIM, ANGLE_NORM, VEL_CLIP, FORCE_NORM, HEIGHT_NORM,
        VX_NORM, VY_NORM, PITCH_NORM,
    )
    import math as _math

    results = []
    for entry in entries:
        with open(entry.path) as f:
            tmeta = _json.load(f)

        env_l = tmeta["env_left"]
        env_r = tmeta["env_right"]
        cx, cy, scale = _env_scale_centre(env_l, env_r)

        sx, sy = entry.drop_left if direction > 0 else entry.drop_right
        phys = TerrainRobotPhysicsV2(dt=1.0/FPS, terrain_json=str(entry.path),
                                     start_x=sx, start_y=sy)
        lmap = LocalMap(env_left=env_l, env_right=env_r)

        # Settling
        settle_act = _gait_frame_to_action(gait[0])
        for _ in range(4):
            phys.step(settle_act)

        start_x = phys.body.position.x
        prev_x  = start_x
        images  = []
        done    = False
        fi      = 0
        info    = {}

        while not done and fi < MAX_STEPS:
            # Build observation (same format as terrain_env.py)
            bx, by, bth, vx, vy, omega = phys.get_body_state()
            base = np.concatenate([
                phys.obs_joint_angles  / ANGLE_NORM,
                np.clip(phys.obs_joint_vels, -VEL_CLIP, VEL_CLIP) / VEL_CLIP,
                phys.obs_joint_torques,
                phys.obs_foot_contact,
                np.clip(phys.obs_foot_forces, 0, FORCE_NORM) / FORCE_NORM,
                np.clip(phys.obs_foot_heights, 0, HEIGHT_NORM) / HEIGHT_NORM,
                np.array([np.clip(vx,-VX_NORM,VX_NORM)/VX_NORM,
                           np.clip(vy,-VY_NORM,VY_NORM)/VY_NORM]),
                np.array([bth / PITCH_NORM]),
            ])
            for i, leg in enumerate(phys.legs):
                fw = leg["lower"].local_to_world((1.2/2, 0))
                lmap.update_contact(fw.x, fw.y, bool(phys._foot_contact[i]))
            map_obs = lmap.get_observation(bx, direction)
            obs = np.concatenate([base, map_obs]).astype(np.float32)

            # Render frame
            n_ct  = sum(phys._foot_contact)
            dist  = abs(bx - start_x)
            label_str = (f"{entry.method}:{entry.seed}  "
                         f"frame={fi:03d}  x={bx:.2f}  vx={vx:.2f}  contacts={n_ct}  dist={dist:.1f}")
            images.append(_render_frame(phys, tmeta, cx, cy, scale, label_str))

            # Policy action
            obs_t  = torch.from_numpy(obs).unsqueeze(0).to(device)
            with torch.no_grad():
                action, _, _ = policy.act(obs_t, deterministic=True)
            act_np = action.squeeze(0).cpu().numpy()
            joint_targets = np.clip(act_np, -1.0, 1.0) * _math.pi
            phys.step(joint_targets)
            fi += 1

            bx2, by2 = phys.body.position
            dist2 = abs(bx2 - start_x)
            if by2 < FALL_Y:
                info = {"dist": dist2, "fall": True, "success": False}
                done = True
            elif dist2 >= SUCCESS_DIST:
                info = {"dist": dist2, "fall": False, "success": True}
                done = True
            prev_x = bx2

        if not info:
            info = {"dist": abs(phys.body.position.x - start_x), "fall": False, "success": False}

        if images:
            tag  = f"{entry.method}_seed{entry.seed:02d}"
            path = out_dir / f"{tag}.gif"
            images[0].save(str(path), save_all=True, append_images=images[1:],
                           loop=0, duration=int(1000/FPS), optimize=False)
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
