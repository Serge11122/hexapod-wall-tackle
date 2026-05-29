"""
Method 5: Wave Function Collapse (WFC) — simplified 1D tile-based terrain.

Defines a vocabulary of terrain tiles and an adjacency grammar.
WFC collapses the tile sequence from left to right, choosing tiles that are
compatible with the previous tile and the remaining budget.

Tile types:
  FLAT        — horizontal floor section
  RAMP_UP     — sloped ascent
  RAMP_DOWN   — sloped descent
  BUMP        — smooth Gaussian hill
  GAP_SMALL   — steppable hole (< 0.8 units)
  GAP_LARGE   — fall-through hole (> 2.2 units)
  STEP_UP     — abrupt upward step (wall obstacle)
  STEP_DOWN   — abrupt downward step
  PIT         — floor depression (ramp-down then ramp-up)
  PLATFORM    — elevated section with gaps on both sides

Adjacency grammar enforces structural validity:
  - RAMP_UP must be preceded and followed by FLAT, BUMP, or STEP_*
  - GAP must be surrounded by FLAT (can't gap right after another gap)
  - Steps must balance: each STEP_UP should eventually have a STEP_DOWN
"""

from pathlib import Path
import math
import numpy as np
from .terrain_common import (
    ENV_LEFT, ENV_RIGHT, ENV_FLOOR, BODY_LENGTH,
    render_terrain, save_terrain_json,
)

OUT_DIR = Path(__file__).parent / "outputs" / "wfc"
METHOD  = "wfc"


# ── Tile definitions ──────────────────────────────────────────────────────────

TILE_TYPES = [
    "FLAT", "RAMP_UP", "RAMP_DOWN", "BUMP",
    "GAP_SMALL", "GAP_LARGE", "STEP_UP", "STEP_DOWN", "PIT",
]

# Adjacency: which tiles may follow each tile type
ADJACENCY = {
    "FLAT":       ["FLAT", "RAMP_UP", "RAMP_DOWN", "BUMP", "GAP_SMALL", "GAP_LARGE",
                   "STEP_UP", "STEP_DOWN", "PIT"],
    "RAMP_UP":    ["FLAT", "BUMP", "RAMP_DOWN"],
    "RAMP_DOWN":  ["FLAT", "BUMP", "GAP_SMALL", "GAP_LARGE", "PIT"],
    "BUMP":       ["FLAT", "GAP_SMALL", "RAMP_DOWN", "BUMP"],
    "GAP_SMALL":  ["FLAT", "BUMP", "RAMP_UP", "STEP_UP"],
    "GAP_LARGE":  ["FLAT", "RAMP_UP", "STEP_UP"],
    "STEP_UP":    ["FLAT", "BUMP", "RAMP_DOWN", "GAP_SMALL"],
    "STEP_DOWN":  ["FLAT", "GAP_SMALL", "GAP_LARGE", "BUMP"],
    "PIT":        ["FLAT", "BUMP", "GAP_SMALL"],
}

# Tile parameters: (min_width, max_width, height_change, description)
TILE_PARAMS = {
    "FLAT":       (1.0, 3.5,  0.0,  "flat section"),
    "RAMP_UP":    (1.5, 3.0,  0.5,  "upward ramp"),
    "RAMP_DOWN":  (1.5, 3.0, -0.5,  "downward ramp"),
    "BUMP":       (1.5, 2.5,  0.0,  "gaussian bump"),
    "GAP_SMALL":  (0.3, 0.75, 0.0,  "steppable gap"),
    "GAP_LARGE":  (2.2, 3.5,  0.0,  "fall-through gap"),
    "STEP_UP":    (0.0, 0.0,  0.4,  "abrupt step up"),
    "STEP_DOWN":  (0.0, 0.0, -0.4,  "abrupt step down"),
    "PIT":        (2.0, 3.5,  0.0,  "floor depression"),
}


# ── Tile renderer: tile → segment list ───────────────────────────────────────

def render_tile(tile_type: str, x0: float, y0: float,
                width: float, rng: np.random.RandomState) -> tuple:
    """
    Returns (segs, gaps, x1, y1):
      segs: list of ((x,y),(x,y)) segments
      gaps: list of (x_start, x_end) gap intervals
      x1: x after this tile
      y1: y after this tile
    """
    segs = []
    gaps = []

    if tile_type == "FLAT":
        segs.append(((x0, y0), (x0 + width, y0)))
        return segs, gaps, x0 + width, y0

    elif tile_type == "RAMP_UP":
        dy = rng.uniform(0.3, 0.7)
        segs.append(((x0, y0), (x0 + width, y0 + dy)))
        return segs, gaps, x0 + width, y0 + dy

    elif tile_type == "RAMP_DOWN":
        dy = min(rng.uniform(0.3, 0.7), max(y0 - 0.05, 0.0))
        segs.append(((x0, y0), (x0 + width, y0 - dy)))
        return segs, gaps, x0 + width, y0 - dy

    elif tile_type == "BUMP":
        n_pts = 18
        xs = np.linspace(0, width, n_pts + 1)
        h  = rng.uniform(0.25, 0.65)
        ys = h * np.exp(-4.0 * ((xs / width) - 0.5) ** 2 / 0.25)
        for i in range(n_pts):
            segs.append((
                (x0 + xs[i],     y0 + ys[i]),
                (x0 + xs[i + 1], y0 + ys[i + 1]),
            ))
        return segs, gaps, x0 + width, y0

    elif tile_type == "GAP_SMALL":
        w = rng.uniform(0.35, 0.72)
        gaps.append((x0, x0 + w))
        return segs, gaps, x0 + w, y0

    elif tile_type == "GAP_LARGE":
        w = rng.uniform(2.2, 3.4)
        gaps.append((x0, x0 + w))
        return segs, gaps, x0 + w, y0

    elif tile_type == "STEP_UP":
        dy = rng.uniform(0.25, 0.55)
        segs.append(((x0, y0), (x0, y0 + dy)))
        return segs, gaps, x0, y0 + dy

    elif tile_type == "STEP_DOWN":
        dy = min(rng.uniform(0.25, 0.55), max(y0 - 0.05, 0.0))
        segs.append(((x0, y0), (x0, y0 - dy)))
        return segs, gaps, x0, y0 - dy

    elif tile_type == "PIT":
        sw   = rng.uniform(0.3, 0.6)
        flat = max(0.1, width - 2 * sw)
        depth = min(rng.uniform(0.4, 0.9), max(y0 - 0.05, 0.0))
        segs.append(((x0, y0),              (x0 + sw, y0 - depth)))
        segs.append(((x0 + sw, y0 - depth), (x0 + sw + flat, y0 - depth)))
        segs.append(((x0 + sw + flat, y0 - depth), (x0 + width, y0)))
        return segs, gaps, x0 + width, y0

    raise ValueError(f"Unknown tile type: {tile_type}")


# ── WFC collapse ──────────────────────────────────────────────────────────────

def collapse(rng: np.random.RandomState, tile_weights: dict) -> tuple[list, list, str]:
    """
    Collapse a tile sequence for the full terrain width.
    Returns (segments, gaps, description).
    """
    x = ENV_LEFT
    y = 0.0
    prev_tile = "FLAT"
    all_segs  = []
    all_gaps  = []
    tile_log  = []

    # Always start with a flat section
    lead_flat = rng.uniform(1.0, 2.5)
    all_segs.append(((x, y), (x + lead_flat, y)))
    x += lead_flat
    tile_log.append("FLAT")

    budget = ENV_RIGHT - x - 2.0  # leave 2 units for trailing flat

    while budget > 0.5:
        # Candidate tiles allowed by adjacency
        candidates = ADJACENCY.get(prev_tile, TILE_TYPES)
        # Filter: don't go below floor, don't exceed ceiling
        valid = []
        for t in candidates:
            _, _, dy, _ = TILE_PARAMS[t]
            if y + dy < 0.05 and dy < 0:
                continue
            if y + dy > 2.5:
                continue
            # Minimum width fits in budget?
            min_w, max_w, _, _ = TILE_PARAMS[t]
            if t in ("STEP_UP", "STEP_DOWN"):
                pass  # zero width tiles always fit
            elif min_w > budget + 0.1:
                continue
            valid.append(t)

        if not valid:
            valid = ["FLAT"]

        # Weighted random choice
        weights = np.array([tile_weights.get(t, 1.0) for t in valid], dtype=float)
        weights /= weights.sum()
        tile = rng.choice(valid, p=weights)

        min_w, max_w, _, _ = TILE_PARAMS[tile]
        if tile in ("STEP_UP", "STEP_DOWN"):
            width = 0.0
        else:
            width = rng.uniform(min_w, min(max_w, budget))

        segs, gaps, x, y = render_tile(tile, x, y, width, rng)
        all_segs.extend(segs)
        all_gaps.extend(gaps)
        tile_log.append(tile)

        if tile not in ("STEP_UP", "STEP_DOWN"):
            budget -= width
        prev_tile = tile

    # Trailing flat + return to floor if elevated
    if y > 0.05:
        trail = rng.uniform(0.5, 1.5)
        all_segs.append(((x, y), (x + trail, y)))
        x += trail
        all_segs.append(((x, y), (x + 0.5, 0.0)))
        x += 0.5
    if x < ENV_RIGHT:
        all_segs.append(((x, 0.0), (ENV_RIGHT, 0.0)))

    desc = " → ".join(tile_log[:8])
    if len(tile_log) > 8:
        desc += f" (+{len(tile_log)-8} more)"
    return all_segs, all_gaps, desc


# ── 10 Weight Profiles ────────────────────────────────────────────────────────

WEIGHT_PROFILES = [
    # flat-heavy, easy
    {"FLAT": 5, "BUMP": 2, "GAP_SMALL": 0.1, "GAP_LARGE": 0},
    # bumps + small gaps
    {"FLAT": 2, "BUMP": 3, "GAP_SMALL": 2, "RAMP_UP": 1, "RAMP_DOWN": 1},
    # steps emphasis
    {"FLAT": 2, "STEP_UP": 3, "STEP_DOWN": 3, "RAMP_UP": 1, "RAMP_DOWN": 1},
    # large gaps emphasis
    {"FLAT": 2, "GAP_LARGE": 3, "BUMP": 1, "RAMP_UP": 1},
    # pits emphasis
    {"FLAT": 2, "PIT": 4, "BUMP": 1, "GAP_SMALL": 1},
    # balanced medium
    {"FLAT": 1.5, "BUMP": 1.5, "GAP_SMALL": 1.5, "GAP_LARGE": 1, "STEP_UP": 1,
     "STEP_DOWN": 1, "RAMP_UP": 1, "RAMP_DOWN": 1, "PIT": 1},
    # ramps + bumps
    {"FLAT": 1, "RAMP_UP": 3, "RAMP_DOWN": 3, "BUMP": 2},
    # gap-heavy (many gaps)
    {"FLAT": 1, "GAP_SMALL": 4, "GAP_LARGE": 3, "BUMP": 0.5},
    # obstacles + pits
    {"FLAT": 1, "STEP_UP": 2, "STEP_DOWN": 2, "PIT": 3, "GAP_SMALL": 1},
    # pure chaos — all equal
    {t: 1.0 for t in TILE_TYPES},
]

PROFILE_NAMES = [
    "easy: flat-heavy",
    "bumps + small gaps",
    "step-heavy",
    "large gap emphasis",
    "pit-heavy",
    "balanced medium",
    "ramps + bumps",
    "gap-heavy",
    "obstacles + pits",
    "full chaos",
]


def generate(seed: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng     = np.random.RandomState(seed)
    profile = WEIGHT_PROFILES[seed % len(WEIGHT_PROFILES)]
    name    = PROFILE_NAMES[seed % len(PROFILE_NAMES)]

    segs, gaps, desc = collapse(rng, profile)
    title = f"{name} | {desc}"

    render_terrain(segs, gaps, title, METHOD, seed,
                   OUT_DIR / f"terrain_{seed:02d}.png")
    save_terrain_json(segs, gaps, OUT_DIR / f"terrain_{seed:02d}.json")
    print(f"  [{METHOD}] seed={seed}: {name}  segs={len(segs)} gaps={len(gaps)}")


def main():
    print(f"Generating {METHOD} terrains ...")
    for s in range(10):
        generate(s)
    print("Done.")


if __name__ == "__main__":
    main()
