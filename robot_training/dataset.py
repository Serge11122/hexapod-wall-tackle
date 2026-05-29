"""
Terrain dataset: list all generated terrain JSONs and split into train/val/test.

Loads from robot_environment/terr_gen/outputs/<method>/terrain_NN.json.
Splits: 70% train, 15% val, 15% test (stratified across methods).
"""

import json
import random
from pathlib import Path
from typing import NamedTuple

TERR_ROOT = Path(__file__).parent.parent / "robot_environment" / "terr_gen" / "outputs"
METHODS   = ["primitive", "fbm_noise", "random_walk", "spline", "wfc"]


class TerrainEntry(NamedTuple):
    path:      Path
    method:    str
    seed:      int
    drop_left:  tuple   # (x, y) for robot dropped on left (walks right)
    drop_right: tuple   # (x, y) for robot dropped on right (walks left)


def _terrain_y_at_x(segments: list, qx: float, default: float = 0.0) -> float:
    """Return terrain height at world x by finding the closest segment."""
    best_y = default
    best_d = float("inf")
    for seg in segments:
        x1, y1 = seg["x1"], seg["y1"]
        x2, y2 = seg["x2"], seg["y2"]
        if min(x1, x2) <= qx <= max(x1, x2):
            if abs(x2 - x1) < 1e-6:
                t = 0.5
            else:
                t = (qx - x1) / (x2 - x1)
            y = y1 + t * (y2 - y1)
            d = 0.0
            if d < best_d:
                best_d, best_y = d, y
    return best_y


def _find_drop_x(segments: list, gaps: list, x_range: tuple) -> float | None:
    """
    Find a valid drop x inside x_range where terrain exists.
    Returns None if no valid location found.
    """
    gap_intervals = [(g["x0"], g["x1"]) for g in gaps]
    x0, x1 = x_range
    candidates = []
    for seg in segments:
        sx0, sx1 = min(seg["x1"], seg["x2"]), max(seg["x1"], seg["x2"])
        cx = max(sx0, x0)
        while cx <= min(sx1, x1):
            in_gap = any(g0 <= cx <= g1 for g0, g1 in gap_intervals)
            if not in_gap:
                candidates.append(cx)
                break
            cx += 0.1
    if candidates:
        # return midpoint of first valid segment x in range
        return candidates[len(candidates) // 2]
    return None


WALK_HEIGHT = 1.9   # body COM above terrain surface at start


def load_terrain(path: Path) -> TerrainEntry | None:
    with open(path) as f:
        d = json.load(f)

    env_l = d["env_left"]
    env_r = d["env_right"]
    segs  = d["segments"]
    gaps  = d.get("gaps", [])

    if not segs:
        return None

    margin = 2.0
    # Left drop (for walking right): find valid x near left wall
    lx = _find_drop_x(segs, gaps, (env_l + 0.5, env_l + margin + 2.0))
    if lx is None:
        lx = env_l + margin
    ly = _terrain_y_at_x(segs, lx) + WALK_HEIGHT

    # Right drop (for walking left): find valid x near right wall
    rx = _find_drop_x(segs, gaps, (env_r - margin - 2.0, env_r - 0.5))
    if rx is None:
        rx = env_r - margin
    ry = _terrain_y_at_x(segs, rx) + WALK_HEIGHT

    method = path.parent.name
    seed   = int(path.stem.split("_")[-1])

    return TerrainEntry(
        path       = path,
        method     = method,
        seed       = seed,
        drop_left  = (lx, ly),
        drop_right = (rx, ry),
    )


def list_terrains(methods: list[str] = METHODS) -> list[TerrainEntry]:
    entries = []
    for method in methods:
        d = TERR_ROOT / method
        if not d.exists():
            continue
        for p in sorted(d.glob("terrain_*.json")):
            e = load_terrain(p)
            if e is not None:
                entries.append(e)
    return entries


def split_terrains(
    entries: list[TerrainEntry],
    train_frac: float = 0.70,
    val_frac:   float = 0.15,
    seed:       int   = 42,
) -> tuple[list, list, list]:
    """Return (train, val, test) splits, stratified by method."""
    rng = random.Random(seed)
    by_method: dict[str, list] = {}
    for e in entries:
        by_method.setdefault(e.method, []).append(e)

    train, val, test = [], [], []
    for method_entries in by_method.values():
        shuffled = list(method_entries)
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_train = max(1, int(n * train_frac))
        n_val   = max(1, int(n * val_frac))
        train.extend(shuffled[:n_train])
        val.extend(shuffled[n_train:n_train + n_val])
        test.extend(shuffled[n_train + n_val:])

    return train, val, test


if __name__ == "__main__":
    entries = list_terrains()
    tr, vl, te = split_terrains(entries)
    print(f"Total: {len(entries)}  train={len(tr)}  val={len(vl)}  test={len(te)}")
    for method in METHODS:
        n = sum(1 for e in entries if e.method == method)
        print(f"  {method}: {n} terrains")
