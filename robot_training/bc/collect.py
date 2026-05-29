"""
Behavioral Cloning data collection.

Runs the hardcoded gait on a flat terrain (and low-difficulty terrains),
records (observation, action) pairs for supervised pretraining.
"""

import json
import math
import numpy as np
from pathlib import Path

from robot_training.env.terrain_env import TerrainTraversalEnv, _gait_frame_to_action
from robot_training.dataset import TerrainEntry

FLAT_JSON = Path(__file__).parent.parent.parent / "robot_environment" / "terr_gen" / "outputs" / "primitive" / "terrain_00.json"
N_ROLLOUT_STEPS = 800   # steps per rollout episode
N_EPISODES      = 6     # episodes to collect (3 per direction)


def _make_flat_entry(direction: int) -> TerrainEntry:
    with open(FLAT_JSON) as f:
        d = json.load(f)
    env_l = d["env_left"]
    env_r = d["env_right"]
    if direction > 0:
        drop = (env_l + 2.0, 0.0 + 1.9)
    else:
        drop = (env_r - 2.0, 0.0 + 1.9)
    return TerrainEntry(
        path        = FLAT_JSON,
        method      = "primitive",
        seed        = 0,
        drop_left   = (env_l + 2.0, 1.9),
        drop_right  = (env_r - 2.0, 1.9),
    )


def collect_bc_data(direction: int, n_steps: int = N_ROLLOUT_STEPS) -> tuple:
    """
    Collect (observations, actions) from hardcoded gait.

    direction: +1 right, -1 left
    Returns: (obs_array, act_array) of shape (N, obs_dim), (N, act_dim)
    """
    gait_name = "right" if direction > 0 else "left"
    gait_path = Path(__file__).parent.parent.parent / "robot_motion" / f"gait_{gait_name}.json"
    with open(gait_path) as f:
        gait = json.load(f)["frames"]
    n_gait = len(gait)

    env   = TerrainTraversalEnv(direction=direction)
    entry = _make_flat_entry(direction)
    obs   = env.reset(entry)

    all_obs = []
    all_act = []

    for step in range(n_steps):
        gait_frame = gait[step % n_gait]
        action     = _gait_frame_to_action(gait_frame)
        # Normalise action to [-1, 1] (divide by pi)
        action_norm = np.clip(action / math.pi, -1.0, 1.0).astype(np.float32)

        all_obs.append(obs.copy())
        all_act.append(action_norm.copy())

        next_obs, _, done, _ = env.step(action_norm)
        obs = next_obs
        if done:
            obs = env.reset(entry)

    return np.array(all_obs, dtype=np.float32), np.array(all_act, dtype=np.float32)


def collect_and_save(out_dir: Path | str, n_steps_per_dir: int = N_ROLLOUT_STEPS) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for direction, label in [(1, "right"), (-1, "left")]:
        print(f"  Collecting BC data [{label}] ({n_steps_per_dir} steps) ...")
        obs_arr, act_arr = collect_bc_data(direction, n_steps_per_dir)
        np.save(out_dir / f"bc_obs_{label}.npy", obs_arr)
        np.save(out_dir / f"bc_act_{label}.npy", act_arr)
        print(f"    Saved obs={obs_arr.shape}  act={act_arr.shape}")


if __name__ == "__main__":
    collect_and_save(Path(__file__).parent.parent / "data" / "bc")
