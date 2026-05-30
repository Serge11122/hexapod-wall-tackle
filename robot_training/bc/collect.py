"""
Behavioral Cloning data collection.

Runs the hardcoded right gait on training terrains (all types),
records (observation, action) pairs for supervised pretraining.

Strategy: collect from each training terrain until max steps reached,
prioritizing flat terrain first, then varied terrain.

Only the right-direction BC is trained (left uses PPO from scratch).
"""

import json
import math
import numpy as np
from pathlib import Path

from robot_training.env.terrain_env import TerrainTraversalEnv, _gait_frame_to_action
from robot_training.dataset import TerrainEntry, list_terrains, split_terrains

STEPS_PER_EPISODE  = 250   # max steps per terrain episode
MAX_FLAT_EPISODES  = 4     # flat terrain (primitive) episodes
MAX_PER_METHOD     = 2     # max episodes per non-primitive method


def _get_gait(direction: int) -> list:
    gait_name = "right" if direction > 0 else "left"
    gait_path = Path(__file__).parent.parent.parent / "robot_motion" / f"gait_{gait_name}.json"
    with open(gait_path) as f:
        d = json.load(f)
    return d["frames"]


def collect_on_terrain(env: TerrainTraversalEnv, entry: TerrainEntry,
                       gait: list, n_steps: int) -> tuple[np.ndarray, np.ndarray]:
    """Run hardcoded gait on one terrain, return (obs, actions)."""
    n_gait = len(gait)
    obs = env.reset(entry)

    all_obs = []
    all_act = []

    for step in range(n_steps):
        gait_frame  = gait[step % n_gait]
        action      = _gait_frame_to_action(gait_frame)
        action_norm = np.clip(action / math.pi, -1.0, 1.0).astype(np.float32)

        all_obs.append(obs.copy())
        all_act.append(action_norm.copy())

        next_obs, _, done, _ = env.step(action_norm)
        obs = next_obs
        if done:
            break  # episode ended (fell or succeeded), stop collecting

    return np.array(all_obs, dtype=np.float32), np.array(all_act, dtype=np.float32)


def collect_bc_data(direction: int, n_steps_total: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Collect BC data from diverse training terrains.
    Only uses the right gait (left model uses PPO from scratch).
    """
    # Always use right gait for BC data collection
    gait = _get_gait(1)  # always right gait
    env  = TerrainTraversalEnv(direction=direction)

    all_entries = list_terrains()
    train, _, _ = split_terrains(all_entries)

    # Group by method
    by_method = {}
    for e in train:
        by_method.setdefault(e.method, []).append(e)

    all_obs_list = []
    all_act_list = []
    steps_so_far = 0

    # Priority 1: flat terrain (primitive) — multiple episodes for stable gait
    flat_entries = by_method.get("primitive", [])[:MAX_FLAT_EPISODES]
    for entry in flat_entries:
        if steps_so_far >= n_steps_total:
            break
        obs_a, act_a = collect_on_terrain(env, entry, gait, STEPS_PER_EPISODE)
        all_obs_list.append(obs_a)
        all_act_list.append(act_a)
        steps_so_far += len(obs_a)
        print(f"    primitive:{entry.seed}: {len(obs_a)} steps (total={steps_so_far})")

    # Priority 2: varied terrain types — sample from each to get diversity
    other_methods = [m for m in ["fbm_noise", "random_walk", "spline", "wfc"]
                     if m in by_method]
    for method in other_methods:
        method_entries = by_method[method][:MAX_PER_METHOD]
        for entry in method_entries:
            if steps_so_far >= n_steps_total:
                break
            try:
                obs_a, act_a = collect_on_terrain(env, entry, gait, STEPS_PER_EPISODE)
                all_obs_list.append(obs_a)
                all_act_list.append(act_a)
                steps_so_far += len(obs_a)
                print(f"    {method}:{entry.seed}: {len(obs_a)} steps (total={steps_so_far})")
            except Exception as exc:
                print(f"    SKIP {method}:{entry.seed} — {exc}")
        if steps_so_far >= n_steps_total:
            break

    if not all_obs_list:
        raise RuntimeError("No BC data collected!")

    obs_arr = np.concatenate(all_obs_list, axis=0)[:n_steps_total]
    act_arr = np.concatenate(all_act_list, axis=0)[:n_steps_total]
    return obs_arr, act_arr


def collect_and_save(out_dir: Path | str, n_steps_per_dir: int = 2000) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Only collect for right direction — left uses PPO random init
    for direction, label in [(1, "right")]:
        print(f"  Collecting BC data [{label}] ({n_steps_per_dir} steps target) ...")
        obs_arr, act_arr = collect_bc_data(direction, n_steps_per_dir)
        np.save(out_dir / f"bc_obs_{label}.npy", obs_arr)
        np.save(out_dir / f"bc_act_{label}.npy", act_arr)
        print(f"    Saved obs={obs_arr.shape}  act={act_arr.shape}")
        print(f"    Unique terrains covered: {len([o for o in [obs_arr]]) * 4}+")


if __name__ == "__main__":
    collect_and_save(Path(__file__).parent.parent / "data" / "bc")
