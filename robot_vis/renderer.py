"""
Shared PIL-based 2D renderer for robot + environment frames.

Coordinate convention: world → pixel
  px = cx + world_x * scale
  py = cy - world_y * scale   (y-flip so up = up on screen)
"""
import math
import numpy as np
from PIL import Image, ImageDraw

# Default frame size and scale
FRAME_W = 1200
FRAME_H =  600
BG_COLOR = (30, 30, 30)


def world_to_px(xy: np.ndarray, cx: float, cy: float, scale: float):
    return (cx + xy[0] * scale, cy - xy[1] * scale)


def px_line(draw: ImageDraw.ImageDraw, a: np.ndarray, b: np.ndarray,
            cx, cy, scale, color, width=2):
    pa = world_to_px(a, cx, cy, scale)
    pb = world_to_px(b, cx, cy, scale)
    draw.line([pa, pb], fill=color, width=width)


def px_circle(draw: ImageDraw.ImageDraw, c: np.ndarray, r_world: float,
              cx, cy, scale, color, fill=None):
    pr = r_world * scale
    pc = world_to_px(c, cx, cy, scale)
    bb = [pc[0] - pr, pc[1] - pr, pc[0] + pr, pc[1] + pr]
    draw.ellipse(bb, outline=color, fill=fill or color)


def px_rect(draw: ImageDraw.ImageDraw, corners: list,
            cx, cy, scale, color, width=3):
    pts = [world_to_px(np.array(c), cx, cy, scale) for c in corners]
    pts_cycle = pts + [pts[0]]
    for i in range(len(pts)):
        draw.line([pts_cycle[i], pts_cycle[i+1]], fill=color, width=width)


def draw_robot(draw: ImageDraw.ImageDraw, pose: dict, cx, cy, scale,
               colors=None):
    """Draw robot body + legs from a pose dict."""
    from robot_motion.body import (
        body_corners, leg_fk, LEG_MOUNTS,
        BODY_HALF_LEN, BODY_HALF_H,
    )
    if colors is None:
        colors = {
            "body":  (80, 200, 80),
            "upper": (80, 140, 220),
            "lower": (220, 80, 80),
            "foot_planted": (255, 255, 80),
            "foot_free":    (200, 200, 200),
            "mount": (180, 220, 255),
        }

    bxy   = np.array([pose["body"]["x"], pose["body"]["y"]])
    bth   = pose["body"]["theta"]
    free  = set(pose.get("free_legs", []))

    # Body rectangle
    corners = body_corners(bxy, bth)
    px_rect(draw, corners, cx, cy, scale, colors["body"], width=3)

    # Mount dots
    for m in LEG_MOUNTS:
        from robot_motion.body import rot2
        mw = bxy + rot2(bth) @ np.array([m["local_x"], 0.0])
        px_circle(draw, mw, 0.06, cx, cy, scale, colors["mount"])

    # Legs
    for leg in pose["legs"]:
        lid = leg["id"]
        mx  = LEG_MOUNTS[lid]["local_x"]
        mw, kw, fw = leg_fk(bxy, bth, mx, leg["theta1"], leg["theta2"])
        px_line(draw, mw, kw, cx, cy, scale, colors["upper"], width=3)
        px_line(draw, kw, fw, cx, cy, scale, colors["lower"], width=3)
        fc = colors["foot_free"] if lid in free else colors["foot_planted"]
        px_circle(draw, fw, 0.08, cx, cy, scale, fc)


def draw_env_segments(draw: ImageDraw.ImageDraw, cx, cy, scale):
    """Draw floor + walls."""
    from robot_environment.env import SEGMENTS
    for seg in SEGMENTS:
        px_line(draw, seg["start"], seg["end"], cx, cy, scale, (200, 200, 200), width=3)


def make_frame(pose: dict, cx: float, cy: float, scale: float,
               w: int = FRAME_W, h: int = FRAME_H,
               draw_env: bool = True) -> Image.Image:
    img  = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    if draw_env:
        draw_env_segments(draw, cx, cy, scale)
    draw_robot(draw, pose, cx, cy, scale)
    return img


# ── Auto-fit helpers ──────────────────────────────────────────────────────────

def fit_scale_and_centre(poses: list[dict], w: int, h: int, margin: float = 0.12):
    """Compute (cx, cy, scale) so all poses fit within image with margin."""
    xs, ys = [], []
    for p in poses:
        xs.append(p["body"]["x"])
        ys.append(p["body"]["y"])
        for leg in p["legs"]:
            xs.append(leg["foot_world"]["x"])
            ys.append(leg["foot_world"]["y"])

    pad = 2.0
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    world_w = max(x1 - x0, 0.1)
    world_h = max(y1 - y0, 0.1)

    scale = min(w * (1 - 2 * margin) / world_w,
                h * (1 - 2 * margin) / world_h)
    cx = w / 2 - (x0 + x1) / 2 * scale
    cy = h / 2 + (y0 + y1) / 2 * scale
    return cx, cy, scale
