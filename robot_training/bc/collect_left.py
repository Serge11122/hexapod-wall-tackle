"""
Behavioral Cloning data collection for the LEFT-walking model.

Uses terrain_physics_v2.py (GrooveJoint) where the left gait correctly
produces leftward motion (unlike the height-spring physics).

Collects from diverse training terrains using gait_left.json.
"""

import json
import math
import numpy as np
from pathlib import Path

import pymunk
import torch

from robot_training.env.terrain_physics_v2 import TerrainRobotPhysicsV2, WALK_HEIGHT
from robot_training.env.local_map import LocalMap, OBS_SIZE as MAP_OBS_SIZE
from robot_training.env.terrain_env import (
    JOINT_DIM, VEL_DIM, TORQ_DIM, CONT_DIM, FORC_DIM, FHGT_DIM,
    BVEL_DIM, PITCH_DIM, BASE_DIM, OBS_DIM, ACT_DIM,
    ANGLE_NORM, VEL_CLIP, FORCE_NORM, HEIGHT_NORM,
    VX_NORM, VY_NORM, PITCH_NORM,
)
from robot_training.dataset import TerrainEntry, list_terrains, split_terrains

LEG_L2 = 1.2   # lower leg length (from body.py)
MAX_STEPS   = 300   # steps per BC episode
DIRECTION   = -1    # left walking


def _get_gait():
    gait_path = Path(__file__).parent.parent.parent / "robot_motion" / "gait_left.json"
    with open(gait_path) as f:
        d = json.load(f)
    return d["frames"]


def _gait_to_action(frame: dict) -> np.ndarray:
    """Convert gait frame to 8-element action array."""
    act = np.zeros(8, dtype=np.float32)
    for leg in frame["legs"]:
        i = leg["id"]
        act[2*i]   = leg["theta1"]
        act[2*i+1] = leg["theta2"]
    return act


def _build_obs(phys: TerrainRobotPhysicsV2, lmap: LocalMap, direction: int) -> np.ndarray:
    """Build observation vector matching terrain_env.py format."""
    bx, by, bth, vx, vy, omega = phys.get_body_state()
    base = np.concatenate([
        phys.obs_joint_angles / ANGLE_NORM,
        np.clip(phys.obs_joint_vels, -VEL_CLIP, VEL_CLIP) / VEL_CLIP,
        phys.obs_joint_torques,
        phys.obs_foot_contact,
        np.clip(phys.obs_foot_forces, 0, FORCE_NORM) / FORCE_NORM,
        np.clip(phys.obs_foot_heights, 0, HEIGHT_NORM) / HEIGHT_NORM,
        np.array([np.clip(vx, -VX_NORM, VX_NORM) / VX_NORM,
                  np.clip(vy, -VY_NORM, VY_NORM) / VY_NORM]),
        np.array([bth / PITCH_NORM]),
    ])
    for i, leg in enumerate(phys.legs):
        fw = leg["lower"].local_to_world((LEG_L2/2, 0))
        lmap.update_contact(fw.x, fw.y, bool(phys._foot_contact[i]))
    map_obs = lmap.get_observation(bx, direction)
    return np.concatenate([base, map_obs]).astype(np.float32)


def collect_on_terrain_groovejoint(entry: TerrainEntry, gait: list,
                                    n_steps: int) -> tuple[np.ndarray, np.ndarray]:
    """Run left gait on terrain using GrooveJoint physics."""
    import json as _json
    with open(entry.path) as f:
        tmeta = _json.load(f)

    # Drop robot on right side (walking left)
    sx, sy = entry.drop_right
    phys = TerrainRobotPhysicsV2(dt=0.1, terrain_json=str(entry.path),
                                  start_x=sx, start_y=sy)
    lmap = LocalMap(env_left=tmeta["env_left"], env_right=tmeta["env_right"])

    n_gait = len(gait)

    # Settle with first gait frame
    for i in range(8):
        act = _gait_to_action(gait[i % n_gait])
        phys.step(act)

    start_x = phys.body.position.x
    all_obs = []
    all_act = []

    for step in range(n_steps):
        frame   = gait[step % n_gait]
        action  = _gait_to_action(frame)
        act_norm = np.clip(action / math.pi, -1.0, 1.0).astype(np.float32)

        obs = _build_obs(phys, lmap, DIRECTION)
        all_obs.append(obs)
        all_act.append(act_norm)

        phys.step(action)

        bx, by = phys.body.position
        # Stop if fallen or reached goal
        if by < 0.3:   # fell below floor
            break
        if abs(bx - start_x) >= 24.0:   # near success
            break

    return (np.array(all_obs, dtype=np.float32),
            np.array(all_act, dtype=np.float32))


def collect_bc_data_left(n_steps_total: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    """Collect BC data for left-walking model using GrooveJoint physics."""
    gait = _get_gait()

    all_entries = list_terrains()
    train, _, _ = split_terrains(all_entries)

    # Sort: flat/primitive first, then varied
    by_method = {}
    for e in train:
        by_method.setdefault(e.method, []).append(e)

    all_obs_list = []
    all_act_list = []
    steps_so_far = 0

    # Primitive terrains: 4 episodes
    for entry in by_method.get("primitive", [])[:4]:
        if steps_so_far >= n_steps_total:
            break
        try:
            obs_a, act_a = collect_on_terrain_groovejoint(entry, gait, 300)
            all_obs_list.append(obs_a)
            all_act_list.append(act_a)
            steps_so_far += len(obs_a)
            print(f"    primitive:{entry.seed}: {len(obs_a)} steps (total={steps_so_far})")
        except Exception as e:
            print(f"    SKIP primitive:{entry.seed}: {e}")

    # Other terrain types: 2 each
    for method in ["fbm_noise", "random_walk", "spline", "wfc"]:
        for entry in by_method.get(method, [])[:2]:
            if steps_so_far >= n_steps_total:
                break
            try:
                obs_a, act_a = collect_on_terrain_groovejoint(entry, gait, 300)
                all_obs_list.append(obs_a)
                all_act_list.append(act_a)
                steps_so_far += len(obs_a)
                print(f"    {method}:{entry.seed}: {len(obs_a)} steps (total={steps_so_far})")
            except Exception as e:
                print(f"    SKIP {method}:{entry.seed}: {e}")

    if not all_obs_list:
        raise RuntimeError("No left BC data collected!")

    obs_arr = np.concatenate(all_obs_list, axis=0)[:n_steps_total]
    act_arr = np.concatenate(all_act_list, axis=0)[:n_steps_total]
    return obs_arr, act_arr


if __name__ == "__main__":
    out_dir = Path(__file__).parent.parent / "data" / "bc"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting LEFT BC data (GrooveJoint physics)...")
    obs_arr, act_arr = collect_bc_data_left(2000)
    np.save(out_dir / "bc_obs_left.npy", obs_arr)
    np.save(out_dir / "bc_act_left.npy", act_arr)
    print(f"Saved obs={obs_arr.shape}  act={act_arr.shape}")
