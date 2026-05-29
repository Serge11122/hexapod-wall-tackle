"""
Method 4: Cubic Spline Interpolation terrain generator.

Places control points at irregular x-intervals with randomly chosen heights,
then fits a CubicSpline (via pure numpy if scipy unavailable, or scipy.interpolate).
Explicitly defined gap list placed between control points.

Character: very smooth curves with smooth transitions between hills —
different from noise (which has random oscillations) and primitives (which are blocky).
"""

from pathlib import Path
import numpy as np
from .terrain_common import (
    ENV_LEFT, ENV_RIGHT, ENV_FLOOR, BODY_LENGTH,
    render_terrain, save_terrain_json,
)

OUT_DIR  = Path(__file__).parent / "outputs" / "spline"
METHOD   = "spline"
N_DENSE  = 500   # samples for rendered polyline


# ── Cubic spline (pure numpy fallback) ───────────────────────────────────────

def _scipy_spline(xs_ctrl, ys_ctrl, xs_dense):
    from scipy.interpolate import CubicSpline
    cs = CubicSpline(xs_ctrl, ys_ctrl, bc_type="clamped")
    return cs(xs_dense)


def _numpy_spline(xs_ctrl, ys_ctrl, xs_dense):
    """
    Monotone piecewise cubic Hermite via finite-difference slopes (Catmull-Rom style).
    Pure numpy — no scipy required.
    """
    n   = len(xs_ctrl)
    h   = np.diff(xs_ctrl)
    dy  = np.diff(ys_ctrl)
    m   = dy / h

    # Tangents: average of neighbouring slopes (clamped at ends)
    tangents = np.zeros(n)
    tangents[0]    = m[0]
    tangents[-1]   = m[-1]
    tangents[1:-1] = (m[:-1] + m[1:]) / 2.0

    # Evaluate piecewise cubic on dense xs
    ys_out = np.empty(len(xs_dense))
    seg = 0
    for i, x in enumerate(xs_dense):
        # Advance segment pointer
        while seg < n - 2 and x > xs_ctrl[seg + 1]:
            seg += 1
        t   = (x - xs_ctrl[seg]) / h[seg]
        h00 =  2*t**3 - 3*t**2 + 1
        h10 =    t**3 - 2*t**2 + t
        h01 = -2*t**3 + 3*t**2
        h11 =    t**3 -   t**2
        ys_out[i] = (h00 * ys_ctrl[seg]
                     + h10 * h[seg] * tangents[seg]
                     + h01 * ys_ctrl[seg + 1]
                     + h11 * h[seg] * tangents[seg + 1])
    return ys_out


def interpolate_spline(xs_ctrl, ys_ctrl, xs_dense):
    try:
        return _scipy_spline(xs_ctrl, ys_ctrl, xs_dense)
    except ImportError:
        return _numpy_spline(xs_ctrl, ys_ctrl, xs_dense)


# ── Gap placement ─────────────────────────────────────────────────────────────

def place_gaps(rng, n_gaps, gap_specs, xs_dense):
    """
    gap_specs: list of (center_frac, width) where center_frac ∈ (0,1) relative to terrain.
    Returns mask (True=terrain exists) and gap list.
    """
    total = ENV_RIGHT - ENV_LEFT
    mask  = np.ones(len(xs_dense), dtype=bool)
    gaps  = []
    placed = []
    for frac, w in gap_specs[:n_gaps]:
        cx = ENV_LEFT + frac * total
        # Avoid overlap
        if any(abs(cx - pc) < (pw + w) / 2 + 0.3 for pc, pw in placed):
            continue
        placed.append((cx, w))
        mask[(xs_dense >= cx - w / 2) & (xs_dense <= cx + w / 2)] = False
        gaps.append((cx - w / 2, cx + w / 2))
    return mask, gaps


def vertices_to_segments(xs, ys, mask):
    segs = []
    for i in range(len(xs) - 1):
        if mask[i] and mask[i + 1]:
            segs.append(((float(xs[i]), float(ys[i])),
                         (float(xs[i + 1]), float(ys[i + 1]))))
    return segs


# ── 10 Configurations ─────────────────────────────────────────────────────────
# Each config: (n_controls, y_range, gap_specs, title)
# gap_specs: list of (center_fraction_0_to_1, width)

CONFIGS = [
    (6,  (0.0, 0.3), [],                                                     "6 ctrl pts, gentle waves"),
    (8,  (0.0, 0.6), [(0.3, 0.65), (0.6, 0.55)],                            "8 pts + 2 small gaps"),
    (10, (0.0, 0.8), [(0.35, 2.5), (0.65, 2.8)],                            "10 pts + 2 large gaps"),
    (7,  (0.0, 1.0), [(0.2, 0.5), (0.45, 0.6), (0.75, 0.55)],               "7 pts + 3 small gaps"),
    (12, (0.0, 1.2), [(0.25, 3.0), (0.55, 0.6), (0.8, 2.2)],                "12 pts + large + small"),
    (5,  (0.0, 1.5), [(0.15, 0.5), (0.35, 2.5), (0.6, 0.6), (0.82, 2.8)],  "5 pts + alternating gaps"),
    (9,  (0.0, 0.4), [(0.2,0.4),(0.35,0.5),(0.5,0.45),(0.65,0.5),(0.8,0.4)],"9 pts + 5 small steppable"),
    (8,  (0.0, 1.8), [(0.3, 3.5), (0.7, 3.2)],                              "8 pts + two huge gaps"),
    (14, (0.0, 0.7), [(0.18,0.6),(0.38,2.2),(0.58,0.5),(0.78,2.5)],         "14 pts + alternating sizes"),
    (10, (0.0, 2.0), [(0.2,0.5),(0.35,2.8),(0.55,0.6),(0.7,3.0),(0.88,0.5)],"10 pts max difficulty"),
]


def generate(seed: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(seed)
    n_ctrl, y_range, gap_specs, title = CONFIGS[seed % len(CONFIGS)]

    # Control points: evenly spaced x with random y
    xs_ctrl = np.linspace(ENV_LEFT, ENV_RIGHT, n_ctrl)
    ys_ctrl = rng.uniform(y_range[0], y_range[1], n_ctrl)
    # Clamp endpoints to 0 for clean wall contact
    ys_ctrl[0]  = 0.0
    ys_ctrl[-1] = 0.0

    xs_dense = np.linspace(ENV_LEFT, ENV_RIGHT, N_DENSE)
    ys_dense = interpolate_spline(xs_ctrl, ys_ctrl, xs_dense)
    ys_dense = np.clip(ys_dense, 0.0, 3.5)

    mask, gaps = place_gaps(rng, len(gap_specs), gap_specs, xs_dense)
    segs = vertices_to_segments(xs_dense, ys_dense, mask)

    render_terrain(segs, gaps, title, METHOD, seed,
                   OUT_DIR / f"terrain_{seed:02d}.png")
    save_terrain_json(segs, gaps, OUT_DIR / f"terrain_{seed:02d}.json")
    print(f"  [{METHOD}] seed={seed}: {title}  segs={len(segs)} gaps={len(gaps)}")


def main():
    print(f"Generating {METHOD} terrains ...")
    for s in range(10):
        generate(s)
    print("Done.")


if __name__ == "__main__":
    main()
