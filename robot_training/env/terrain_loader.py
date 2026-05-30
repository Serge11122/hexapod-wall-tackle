"""
Load terrain JSON into a pymunk Space.

Additions vs flat floor:
  - Multi-segment polyline floor from JSON
  - Vertical bumper walls at gap edges (robot can feel hole boundaries via foot contact)
  - Floor-level terrain under varied-height segments
"""

import json
import math
from pathlib import Path
import pymunk

BUMPER_HEIGHT  = 0.6   # vertical wall at gap edges (robot detects these with feet)
SEGMENT_RADIUS = 0.02
TERRAIN_FRICTION    = 1.2
TERRAIN_ELASTICITY  = 0.02
WALL_FRICTION       = 0.0
WALL_ELASTICITY     = 0.0

# Collision type IDs (pymunk integers, used for collision handler registration)
COLL_TERRAIN = 1
COLL_FOOT    = 2

# Shape filters
# All robot parts use group=1 → no robot self-collision.
# Terrain uses group=0 (default) → robot can still collide with terrain.
SELF_FILTER = pymunk.ShapeFilter(group=1)

# Aliases kept for external use
CAT_TERRAIN = COLL_TERRAIN
CAT_FOOT    = COLL_FOOT


def load_terrain_into_space(space: pymunk.Space, json_path: str | Path) -> dict:
    """
    Add terrain segments (and gap-edge bumpers) to the space's static body.

    Returns metadata dict:
      env_left, env_right, env_floor, wall_height, segments, gaps
    """
    with open(json_path) as f:
        d = json.load(f)

    env_left  = d["env_left"]
    env_right = d["env_right"]
    env_floor = d.get("env_floor", 0.0)
    segments  = d["segments"]
    gaps      = d.get("gaps", [])

    sb = space.static_body

    def _add_terrain_seg(p0, p1, friction=TERRAIN_FRICTION, elasticity=TERRAIN_ELASTICITY):
        sh = pymunk.Segment(sb, p0, p1, SEGMENT_RADIUS)
        sh.friction       = friction
        sh.elasticity     = elasticity
        sh.collision_type = COLL_TERRAIN
        space.add(sh)

    # ── Terrain polyline segments ──────────────────────────────────────────
    for seg in segments:
        _add_terrain_seg((seg["x1"], seg["y1"]), (seg["x2"], seg["y2"]))

    # ── Gap-edge bumpers (vertical walls at hole boundaries) ───────────────
    for gap in gaps:
        gx0, gx1 = gap["x0"], gap["x1"]
        y0_edge = _terrain_y_near(segments, gx0, side="left")
        y1_edge = _terrain_y_near(segments, gx1, side="right")
        if y0_edge is not None:
            _add_terrain_seg((gx0, env_floor), (gx0, y0_edge + BUMPER_HEIGHT),
                             friction=0.3, elasticity=0.05)
        if y1_edge is not None:
            _add_terrain_seg((gx1, env_floor), (gx1, y1_edge + BUMPER_HEIGHT),
                             friction=0.3, elasticity=0.05)

    # ── Boundary walls ─────────────────────────────────────────────────────
    wall_h = 8.0
    for wx in (env_left, env_right):
        _add_terrain_seg((wx, env_floor), (wx, wall_h),
                         friction=WALL_FRICTION, elasticity=WALL_ELASTICITY)

    return {
        "env_left":   env_left,
        "env_right":  env_right,
        "env_floor":  env_floor,
        "wall_height": wall_h,
        "segments":   segments,
        "gaps":       gaps,
    }


def _terrain_y_near(segments: list, x: float, side: str) -> float | None:
    """Find terrain y nearest to x (searching left or right of x)."""
    best_y = None
    best_d = float("inf")
    for seg in segments:
        x1, y1 = seg["x1"], seg["y1"]
        x2, y2 = seg["x2"], seg["y2"]
        sx0, sx1 = min(x1, x2), max(x1, x2)
        if side == "left" and sx1 <= x + 0.5:
            d = abs(sx1 - x)
            if d < best_d:
                best_d, best_y = d, y2 if x2 > x1 else y1
        elif side == "right" and sx0 >= x - 0.5:
            d = abs(sx0 - x)
            if d < best_d:
                best_d, best_y = d, y1 if x2 > x1 else y2
    return best_y


def terrain_height_at(segments: list, x: float) -> float:
    """Query terrain height at world x (returns 0 if no segment covers x)."""
    for seg in segments:
        x1, y1 = seg["x1"], seg["y1"]
        x2, y2 = seg["x2"], seg["y2"]
        if abs(x2 - x1) < 1e-6:
            if abs(x - x1) < 0.05:
                return max(y1, y2)
            continue
        if min(x1, x2) <= x <= max(x1, x2):
            t = (x - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return 0.0
