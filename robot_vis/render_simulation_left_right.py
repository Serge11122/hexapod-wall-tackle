"""
Simulate and render robot walking left and right inside the 2D environment.

Physics: causal contact — joint angles → FK → foot anchors → body constraint.
No hardcoded drive force; body translation emerges from the gait kinematics
reacting against the floor through planted-foot constraints.

Outputs:
  robot_vis/left_right/frames/<direction>/frame_NNNN.png
  robot_vis/left_right/vid/<direction>.gif  (animated GIF at 5 fps)

Usage:
    python -m robot_vis.render_simulation_left_right
"""

import json
import copy
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

from robot_motion.body import (
    leg_fk, LEG_MOUNTS, BODY_HALF_LEN, GRAVITY,
)
from robot_environment.env import ENV_LEFT, ENV_RIGHT, ENV_HEIGHT, SEGMENTS
from robot_environment.contact_physics import (
    BodyState, ContactPhysics, FLOOR_Y,
)
from robot_vis.renderer import world_to_px, draw_robot

HERE      = Path(__file__).parent
FRAME_DIR = HERE / "frames"   # frames/sim_<direction>/
VID_DIR   = HERE / "vid"      # vid/sim_<direction>/
FRAME_DIR.mkdir(parents=True, exist_ok=True)
VID_DIR.mkdir(parents=True, exist_ok=True)

FPS        = 5
DT         = 1.0 / FPS
FRAME_W    = 1400
FRAME_H    =  600
WALK_HEIGHT = 1.9   # body-centre y at walking stance (matches gait_gen.py BODY_Y)

BG_COLOR   = (20, 20, 35)
ENV_COLOR  = (180, 180, 180)
TEXT_CLR   = (230, 230, 230)

ROBOT_COLORS = {
    "body":  (80, 200, 80),
    "upper": (80, 140, 220),
    "lower": (220, 80, 80),
    "foot_planted": (255, 220, 60),
    "foot_free":    (180, 180, 180),
    "mount": (180, 220, 255),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_gait(direction: str) -> list[dict]:
    path = Path(__file__).parent.parent / "robot_motion" / f"gait_{direction}.json"
    with open(path) as f:
        return json.load(f)["frames"]


def _pose_at(gait_frame: dict, bx: float, by: float) -> dict:
    """
    Build a display pose: body overridden by physics position,
    leg joint angles from gait frame, feet recomputed via FK.
    """
    p = copy.deepcopy(gait_frame)
    p["body"]["x"] = bx
    p["body"]["y"] = by
    bxy = np.array([bx, by])
    bth = p["body"]["theta"]
    for leg in p["legs"]:
        lid = leg["id"]
        mx  = LEG_MOUNTS[lid]["local_x"]
        _, _, fw = leg_fk(bxy, bth, mx, leg["theta1"], leg["theta2"])
        leg["foot_world"]["x"] = float(fw[0])
        leg["foot_world"]["y"] = float(fw[1])
    return p


def _env_scale_centre(w: int, h: int):
    world_w = ENV_RIGHT - ENV_LEFT
    world_h = ENV_HEIGHT
    margin  = 0.08
    scale   = min(w * (1 - 2 * margin) / world_w,
                  h * (1 - 2 * margin) / world_h)
    cx = w / 2 - (ENV_LEFT + world_w / 2) * scale
    cy = h * 0.82
    return cx, cy, scale


def _render_frame(pose: dict, cx, cy, scale, label: str) -> Image.Image:
    img  = Image.new("RGB", (FRAME_W, FRAME_H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    for seg in SEGMENTS:
        pa = world_to_px(seg["start"], cx, cy, scale)
        pb = world_to_px(seg["end"],   cx, cy, scale)
        draw.line([pa, pb], fill=ENV_COLOR, width=4)
    draw_robot(draw, pose, cx, cy, scale, ROBOT_COLORS)
    draw.text((12, 12), label, fill=TEXT_CLR)
    return img


# ── Drop phase (free-fall before gait starts) ─────────────────────────────────

def _drop_frames(gait: list[dict], drop_height: float,
                 cx, cy, scale) -> tuple[list[Image.Image], BodyState]:
    """
    Let the body fall from WALK_HEIGHT + drop_height under gravity until it
    reaches WALK_HEIGHT.  Returns rendered frames and the landing BodyState.
    """
    bx, by, vy = 0.0, WALK_HEIGHT + drop_height, 0.0
    sub_dt = DT / 20
    images = []

    while by > WALK_HEIGHT:
        for _ in range(20):
            vy -= GRAVITY * sub_dt
            by += vy * sub_dt
            if by <= WALK_HEIGHT:
                by = WALK_HEIGHT
                vy = 0.0
                break

        # Render a neutral pose while falling
        pose = _pose_at(gait[0], bx, by)
        label = f"DROP | by={by:.2f}"
        images.append(_render_frame(pose, cx, cy, scale, label))

    return images, BodyState(bx=bx, by=by)


# ── Main simulation ───────────────────────────────────────────────────────────

def simulate_walk(direction: str) -> list[Image.Image]:
    gait    = _load_gait(direction)
    n_gait  = len(gait)
    physics = ContactPhysics(dt=DT)
    cx, cy, scale = _env_scale_centre(FRAME_W, FRAME_H)

    # Render drop
    drop_imgs, state = _drop_frames(gait, drop_height=1.5, cx=cx, cy=cy, scale=scale)

    start_x    = state.bx
    body_len   = 2.0 * BODY_HALF_LEN
    target_dist = 3.0 * body_len   # 3 body lengths = 6 world units
    MAX_FRAMES = 300

    images      = drop_imgs
    prev_planted: set[int] = set()

    for fi in range(MAX_FRAMES):
        gait_frame = gait[fi % n_gait]

        state = physics.step(state, gait_frame, prev_planted)
        prev_planted = set(state.planted)

        pose  = _pose_at(gait_frame, state.bx, state.by)
        label = (f"{direction.upper()} | frame {fi:03d} | "
                 f"x={state.bx:.2f}  vx={state.vx:.3f}  "
                 f"dist={abs(state.bx - start_x):.2f}")
        images.append(_render_frame(pose, cx, cy, scale, label))

        if abs(state.bx - start_x) >= target_dist - 0.05:
            break

    return images


# ── Save ──────────────────────────────────────────────────────────────────────

def save_simulation(direction: str):
    print(f"Simulating walk {direction} ...")
    images = simulate_walk(direction)

    fdir = FRAME_DIR / f"sim_{direction}"
    fdir.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(images):
        img.save(str(fdir / f"frame_{i:04d}.png"))
    print(f"  Saved {len(images)} frames → {fdir}")

    vdir = VID_DIR / f"sim_{direction}"
    vdir.mkdir(parents=True, exist_ok=True)
    vid_path = vdir / f"{direction}.gif"
    images[0].save(
        str(vid_path),
        save_all=True,
        append_images=images[1:],
        loop=0,
        duration=int(1000 / FPS),
        optimize=False,
    )
    print(f"  Saved GIF → {vid_path}")


def main():
    for direction in ("right", "left"):
        save_simulation(direction)


if __name__ == "__main__":
    main()
