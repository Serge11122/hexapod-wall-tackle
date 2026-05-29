"""
Common constants and rendering utilities for terrain generation experiments.

Terrain representation:
  A terrain is a list of segment tuples: ((x1,y1), (x2,y2))
  Gaps are implicit — where no segment covers an x-range, the floor is absent.
  A helper stores gap intervals separately for rendering clarity.

Coordinate system: x=right, y=up (same as pymunk environment).
"""

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── World dimensions ──────────────────────────────────────────────────────────

BODY_LENGTH  = 2.0    # 2 × BODY_HALF_LEN
TERRAIN_LEN  = 15 * BODY_LENGTH   # 30 world units
ENV_LEFT     = -TERRAIN_LEN / 2   # -15
ENV_RIGHT    =  TERRAIN_LEN / 2   # +15
ENV_FLOOR    = 0.0
ENV_HEIGHT   = 7.0
WALL_HEIGHT  = 6.0

# Hole/obstacle sizing thresholds relative to body geometry
SMALL_HOLE   = 0.7    # steppable (< leg reach from mount)
LARGE_HOLE   = 2.2    # fall-through (> stance width)
MAX_STEP_H   = 0.4    # max climbable step (body clearance ≈ BODY_HALF_H × 2)

# ── Image rendering ───────────────────────────────────────────────────────────

IMG_W   = 1800
IMG_H   = 480
MARGIN  = dict(left=90, right=90, top=70, bottom=60)

BG_COLOR      = (18, 18, 30)
TERRAIN_COLOR = (160, 200, 160)
WALL_COLOR    = (100, 160, 220)
GAP_COLOR     = (80, 30, 30)
GRID_COLOR    = (40, 40, 55)
TEXT_COLOR    = (230, 230, 230)
DIM_COLOR     = (120, 120, 140)
BODY_COLOR    = (255, 200, 50)    # body-length ruler


def _draw_w() -> int:
    return IMG_W - MARGIN["left"] - MARGIN["right"]


def _draw_h() -> int:
    return IMG_H - MARGIN["top"] - MARGIN["bottom"]


def world_to_px(wx: float, wy: float) -> tuple[int, int]:
    dw = _draw_w()
    dh = _draw_h()
    scale_x = dw / (ENV_RIGHT - ENV_LEFT)
    scale_y = dh / ENV_HEIGHT
    scale   = min(scale_x, scale_y)
    ox = MARGIN["left"] + (wx - ENV_LEFT) * scale_x
    oy = IMG_H - MARGIN["bottom"] - wy * scale_y
    return int(round(ox)), int(round(oy))


def render_terrain(
    segments: list[tuple],
    gaps: list[tuple],
    title: str,
    method: str,
    seed: int,
    out_path: str | Path,
) -> None:
    """
    Render a terrain to a PNG file.

    segments : list of ((x1,y1),(x2,y2)) floor segments
    gaps     : list of (x_start, x_end) gap intervals for shading
    """
    img  = Image.new("RGB", (IMG_W, IMG_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ── Grid ────────────────────────────────────────────────────────────────
    for gx in np.arange(ENV_LEFT, ENV_RIGHT + 0.01, BODY_LENGTH):
        px, _ = world_to_px(gx, 0)
        _, py_top = world_to_px(0, ENV_HEIGHT)
        _, py_bot = world_to_px(0, 0)
        draw.line([(px, py_top), (px, py_bot)], fill=GRID_COLOR, width=1)
    for gy in np.arange(0, ENV_HEIGHT + 0.01, 1.0):
        _, py = world_to_px(0, gy)
        px_l, _ = world_to_px(ENV_LEFT, 0)
        px_r, _ = world_to_px(ENV_RIGHT, 0)
        draw.line([(px_l, py), (px_r, py)], fill=GRID_COLOR, width=1)

    # ── Gap shading ──────────────────────────────────────────────────────────
    _, py_floor = world_to_px(0, ENV_FLOOR)
    _, py_neg   = world_to_px(0, -1.0)
    y_top_gap   = min(py_floor, py_neg)
    y_bot_gap   = max(py_floor, py_neg)
    for (gx0, gx1) in gaps:
        px0, _ = world_to_px(gx0, 0)
        px1, _ = world_to_px(gx1, 0)
        draw.rectangle([min(px0,px1), y_top_gap, max(px0,px1), y_bot_gap], fill=GAP_COLOR)

    # ── Terrain fill (below segments) ────────────────────────────────────────
    for (p0, p1) in segments:
        x0, y0 = p0
        x1, y1 = p1
        # Sample dense fill polygon
        xs = np.linspace(x0, x1, max(int(abs(x1-x0)*30)+2, 2))
        ys = np.linspace(y0, y1, len(xs))
        pts_top = [world_to_px(x, y) for x, y in zip(xs, ys)]
        pts_bot = [world_to_px(xs[-1], ENV_FLOOR - 0.5), world_to_px(xs[0], ENV_FLOOR - 0.5)]
        poly = pts_top + pts_bot
        if len(poly) >= 3:
            draw.polygon(poly, fill=(30, 70, 30))

    # ── Terrain segments (thick lines) ───────────────────────────────────────
    for (p0, p1) in segments:
        pa = world_to_px(*p0)
        pb = world_to_px(*p1)
        draw.line([pa, pb], fill=TERRAIN_COLOR, width=4)

    # ── Walls ────────────────────────────────────────────────────────────────
    for wx in (ENV_LEFT, ENV_RIGHT):
        pa = world_to_px(wx, ENV_FLOOR)
        pb = world_to_px(wx, WALL_HEIGHT)
        draw.line([pa, pb], fill=WALL_COLOR, width=5)

    # ── Body-length ruler at top ──────────────────────────────────────────────
    ruler_y_w = ENV_HEIGHT - 0.3
    for i in range(15):
        rx0 = ENV_LEFT + i * BODY_LENGTH
        rx1 = rx0 + BODY_LENGTH
        col = BODY_COLOR if i % 2 == 0 else (200, 150, 30)
        px0, py0 = world_to_px(rx0, ruler_y_w)
        px1, _   = world_to_px(rx1, ruler_y_w)
        draw.rectangle([px0, py0 - 6, px1, py0 + 6], fill=col)
        draw.text((px0 + 2, py0 - 20), str(i + 1), fill=col)

    # ── Labels ───────────────────────────────────────────────────────────────
    draw.text((MARGIN["left"], 8), f"{method.upper()}  |  {title}  |  seed={seed}", fill=TEXT_COLOR)

    n_segs = len(segments)
    n_gaps = len(gaps)
    total_gap = sum(x1 - x0 for x0, x1 in gaps)
    info = (f"segments={n_segs}  gaps={n_gaps}  "
            f"gap_total={total_gap:.1f}u  "
            f"terrain={TERRAIN_LEN}u = 15×body")
    draw.text((MARGIN["left"], IMG_H - MARGIN["bottom"] + 8), info, fill=DIM_COLOR)

    img.save(str(out_path))


def save_terrain_json(segments: list[tuple], gaps: list[tuple], path: str | Path) -> None:
    """Save terrain as JSON (list of segment endpoints)."""
    import json
    data = {
        "env_left":  ENV_LEFT,
        "env_right": ENV_RIGHT,
        "env_floor": ENV_FLOOR,
        "segments":  [{"x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1]}
                      for p0, p1 in segments],
        "gaps":      [{"x0": g[0], "x1": g[1]} for g in gaps],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
