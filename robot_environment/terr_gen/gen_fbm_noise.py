"""
Method 2: Fractal Brownian Motion (fBm) noise terrain generator.

Generates smooth organic terrain by summing sinusoids at doubling frequencies
(a Perlin-noise analogue using pure numpy — no external noise library required).

Gap mask: independent low-frequency noise thresholded to punch holes in the
terrain, creating both steppable and fall-through gaps.
"""

from pathlib import Path
import numpy as np
from .terrain_common import (
    ENV_LEFT, ENV_RIGHT, ENV_FLOOR, BODY_LENGTH,
    render_terrain, save_terrain_json,
)

OUT_DIR = Path(__file__).parent / "outputs" / "fbm_noise"
METHOD  = "fbm_noise"

N_SAMPLES = 600   # x resolution for terrain polyline

# ── fBm core ──────────────────────────────────────────────────────────────────

def fbm_1d(xs: np.ndarray, octaves: int, base_freq: float,
           persistence: float, seed: int) -> np.ndarray:
    """Sum of sinusoids at doubling frequencies with random phases."""
    rng   = np.random.RandomState(seed)
    total = np.zeros_like(xs)
    amp   = 1.0
    freq  = base_freq
    norm  = 0.0
    for _ in range(octaves):
        phase  = rng.uniform(0, 2 * np.pi)
        phase2 = rng.uniform(0, 2 * np.pi)
        total += amp * (np.sin(2 * np.pi * freq * xs + phase)
                        + 0.5 * np.cos(2 * np.pi * freq * xs * 1.3 + phase2))
        norm  += amp * 1.5
        amp   *= persistence
        freq  *= 2.0
    return total / norm


def gap_mask(xs: np.ndarray, n_gaps: int, gap_widths: list[float],
             seed: int) -> np.ndarray:
    """Boolean mask: True where terrain exists, False inside a gap."""
    rng  = np.random.RandomState(seed + 1000)
    mask = np.ones(len(xs), dtype=bool)
    valid_range = (xs > ENV_LEFT + 2.0) & (xs < ENV_RIGHT - 2.0)
    valid_xs = xs[valid_range]
    if len(valid_xs) == 0 or n_gaps == 0:
        return mask
    # Place gaps at random positions
    placed = []
    for w in gap_widths[:n_gaps]:
        for _ in range(20):   # retry up to 20 times to avoid overlap
            cx = rng.uniform(valid_xs[0] + w / 2, valid_xs[-1] - w / 2)
            overlap = any(abs(cx - pc) < pw / 2 + w / 2 + 0.5
                          for pc, pw in placed)
            if not overlap:
                placed.append((cx, w))
                break
    for cx, w in placed:
        mask[(xs > cx - w / 2) & (xs < cx + w / 2)] = False
    return mask


def extract_gaps(xs: np.ndarray, mask: np.ndarray) -> list[tuple]:
    """Extract (x_start, x_end) gap intervals from boolean mask."""
    gaps = []
    in_gap = False
    gx0 = None
    for i, (x, m) in enumerate(zip(xs, mask)):
        if not m and not in_gap:
            gx0 = x; in_gap = True
        elif m and in_gap:
            gaps.append((gx0, xs[i - 1]))
            in_gap = False
    if in_gap:
        gaps.append((gx0, xs[-1]))
    return gaps


def vertices_to_segments(xs: np.ndarray, ys: np.ndarray,
                          mask: np.ndarray) -> list[tuple]:
    """Convert dense (x,y) arrays with gap mask into segment list."""
    segs = []
    for i in range(len(xs) - 1):
        if mask[i] and mask[i + 1]:
            segs.append(((xs[i], float(ys[i])), (xs[i + 1], float(ys[i + 1]))))
    return segs


# ── 10 Terrain Configurations ─────────────────────────────────────────────────

CONFIGS = [
    # (octaves, base_freq, persistence, amplitude, y_offset,
    #  n_gaps, gap_widths, title)
    (4, 0.04, 0.55, 0.25, 0.35, 0,  [],                               "smooth, no gaps"),
    (5, 0.06, 0.60, 0.40, 0.50, 3,  [0.6, 0.7, 0.5],                  "low freq + small gaps"),
    (6, 0.08, 0.65, 0.55, 0.55, 2,  [2.5, 2.8],                       "medium freq + large gaps"),
    (7, 0.10, 0.70, 0.70, 0.60, 4,  [0.5, 0.6, 2.2, 2.6],             "high octaves + mixed gaps"),
    (4, 0.03, 0.50, 0.80, 0.80, 1,  [3.2],                             "gentle hills + massive gap"),
    (8, 0.12, 0.75, 0.45, 0.45, 5,  [0.4, 0.6, 0.5, 0.7, 0.45],       "rough + many small gaps"),
    (5, 0.05, 0.55, 1.00, 1.00, 3,  [2.0, 2.5, 0.7],                  "high amplitude + 2 large + 1 small"),
    (6, 0.09, 0.65, 0.35, 0.35, 6,  [0.5, 0.6, 2.3, 0.4, 2.1, 0.55],  "moderate + alternating gaps"),
    (3, 0.02, 0.45, 1.20, 1.20, 2,  [3.5, 0.5],                       "very low freq + huge gap"),
    (7, 0.11, 0.72, 0.60, 0.60, 4,  [2.2, 2.4, 0.6, 0.65],            "max difficulty: rough + gaps"),
]


def generate(seed: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = CONFIGS[seed % len(CONFIGS)]
    octaves, base_freq, persistence, amplitude, y_offset, n_gaps, gap_widths, title = cfg

    xs = np.linspace(ENV_LEFT, ENV_RIGHT, N_SAMPLES)
    raw  = fbm_1d(xs, octaves, base_freq, persistence, seed)
    ys   = np.clip(amplitude * raw + y_offset, 0.0, 3.5)

    # Smooth ends to 0 for clean wall contact
    fade = 50
    for i in range(fade):
        w = i / fade
        ys[i]          = ys[i] * w
        ys[-(i + 1)]   = ys[-(i + 1)] * w

    mask = gap_mask(xs, n_gaps, gap_widths, seed)
    gaps = extract_gaps(xs, mask)
    segs = vertices_to_segments(xs, ys, mask)

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
