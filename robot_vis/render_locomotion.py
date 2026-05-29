"""
Render locomotion keyframes from gait JSON files to robot_vis/motion_frames/.

Usage:
    python -m robot_vis.render_locomotion
"""
import json
import sys
from pathlib import Path

HERE     = Path(__file__).parent
GAIT_DIR = Path(__file__).parent.parent / "robot_motion"
OUT_DIR  = HERE / "frames"   # frames/<direction>/
OUT_DIR.mkdir(parents=True, exist_ok=True)

FRAME_W, FRAME_H = 900, 500


def render_gait(gait_path: Path):
    with open(gait_path) as f:
        data = json.load(f)

    frames  = data["frames"]
    direction = data["direction"]

    from robot_vis.renderer import fit_scale_and_centre, make_frame

    cx, cy, scale = fit_scale_and_centre(frames, FRAME_W, FRAME_H)

    subdir = OUT_DIR / f"motion_{direction}"
    subdir.mkdir(parents=True, exist_ok=True)

    for pose in frames:
        fi = pose["frame_index"]
        img = make_frame(pose, cx, cy, scale, FRAME_W, FRAME_H, draw_env=False)
        out = subdir / f"frame_{fi:03d}.png"
        img.save(str(out))
        print(f"  {out}")

    print(f"Saved {len(frames)} frames → {subdir}")


def main():
    gaits = sorted(GAIT_DIR.glob("gait_*.json"))
    assert gaits, f"No gait_*.json in {GAIT_DIR}"
    for g in gaits:
        print(f"Rendering {g.name} ...")
        render_gait(g)


if __name__ == "__main__":
    main()
