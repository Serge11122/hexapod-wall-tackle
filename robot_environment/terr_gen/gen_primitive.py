"""
Method 1: Primitive Composition terrain generator.

Builds terrain by sequencing named primitives:
  flat, ramp, step_up, step_down, bump, gap, pit, platform, wall_obstacle

Each of 10 seeds produces a different hand-designed difficulty scenario.
"""

from pathlib import Path
import numpy as np
from .terrain_common import (
    ENV_LEFT, ENV_RIGHT, ENV_FLOOR, BODY_LENGTH,
    render_terrain, save_terrain_json,
)

OUT_DIR = Path(__file__).parent / "outputs" / "primitive"
METHOD  = "primitive"


# ── Builder ───────────────────────────────────────────────────────────────────

class TerrainBuilder:
    def __init__(self, start_x: float = ENV_LEFT, start_y: float = 0.0):
        self.x    = start_x
        self.y    = start_y
        self._segs: list[tuple] = []
        self._gaps: list[tuple] = []

    def flat(self, length: float) -> "TerrainBuilder":
        x1 = self.x + length
        self._segs.append(((self.x, self.y), (x1, self.y)))
        self.x = x1
        return self

    def ramp(self, length: float, dy: float) -> "TerrainBuilder":
        x1 = self.x + length
        y1 = max(0.0, self.y + dy)
        self._segs.append(((self.x, self.y), (x1, y1)))
        self.x, self.y = x1, y1
        return self

    def step_up(self, height: float, wall_w: float = 0.05) -> "TerrainBuilder":
        y1 = self.y + height
        self._segs.append(((self.x, self.y), (self.x, y1)))
        self.y = y1
        return self

    def step_down(self, height: float) -> "TerrainBuilder":
        y1 = max(0.0, self.y - height)
        self._segs.append(((self.x, self.y), (self.x, y1)))
        self.y = y1
        return self

    def bump(self, length: float, height: float, n_pts: int = 16) -> "TerrainBuilder":
        xs = np.linspace(0.0, length, n_pts + 1)
        ys = height * np.exp(-4.0 * ((xs / length) - 0.5) ** 2 / 0.25)
        for i in range(n_pts):
            self._segs.append((
                (self.x + xs[i],     self.y + ys[i]),
                (self.x + xs[i + 1], self.y + ys[i + 1]),
            ))
        self.x += length
        return self

    def gap(self, width: float) -> "TerrainBuilder":
        self._gaps.append((self.x, self.x + width))
        self.x += width
        return self

    def pit(self, width: float, depth: float, slope_w: float = 0.5) -> "TerrainBuilder":
        depth = min(depth, self.y)
        slope_w = min(slope_w, width / 2 - 0.1)
        self.ramp(slope_w, -depth)
        self.flat(width - 2 * slope_w)
        self.ramp(slope_w, depth)
        return self

    def wall_obstacle(self, height: float, thickness: float = 0.15) -> "TerrainBuilder":
        """A thin wall obstacle the robot must step over."""
        self._segs.append(((self.x, self.y), (self.x, self.y + height)))
        self._segs.append(((self.x, self.y + height), (self.x + thickness, self.y + height)))
        self._segs.append(((self.x + thickness, self.y + height), (self.x + thickness, self.y)))
        self.x += thickness
        return self

    def platform(self, length: float, height: float, gap_before: float = 0.5,
                 gap_after: float = 0.5) -> "TerrainBuilder":
        """Raised platform with gap approach/departure."""
        self.gap(gap_before)
        y0 = self.y
        self._segs.append(((self.x, height), (self.x + length, height)))
        self.x += length
        self.y = height
        self.gap(gap_after)
        self.y = y0
        return self

    def build(self) -> tuple[list, list]:
        return self._segs, self._gaps


# ── 10 Terrain Scenarios ──────────────────────────────────────────────────────

def _terrain_0(rng) -> tuple[list, list, str]:
    """Mostly flat, gentle bumps — easy intro."""
    b = TerrainBuilder()
    b.flat(4).bump(2, 0.3).flat(3).bump(1.5, 0.2).flat(3).bump(2.5, 0.4).flat(2).bump(1, 0.15).flat(12)
    return *b.build(), "easy: gentle bumps"

def _terrain_1(rng) -> tuple[list, list, str]:
    """Staircase up then down — steps only."""
    b = TerrainBuilder()
    b.flat(2)
    for _ in range(5):
        b.step_up(0.4).flat(1.5)
    b.flat(1)
    for _ in range(5):
        b.step_down(0.4).flat(1.5)
    b.flat(2)
    return *b.build(), "staircase up+down"

def _terrain_2(rng) -> tuple[list, list, str]:
    """Small gaps only — steppable (< 0.8 units)."""
    b = TerrainBuilder()
    widths = [0.4, 0.6, 0.5, 0.7, 0.4, 0.6, 0.5, 0.65]
    x = ENV_LEFT
    b.flat(2)
    for w in widths:
        b.flat(rng.uniform(1.5, 2.5)).gap(w)
    b.flat(3)
    return *b.build(), "small steppable gaps"

def _terrain_3(rng) -> tuple[list, list, str]:
    """Large gaps — fall-through (> 2 units)."""
    b = TerrainBuilder()
    b.flat(3).gap(2.5).flat(4).gap(3.0).flat(4).gap(2.8).flat(4).gap(2.2).flat(3)
    return *b.build(), "large fall-through gaps"

def _terrain_4(rng) -> tuple[list, list, str]:
    """Mixed: bumps + small gaps alternating."""
    b = TerrainBuilder()
    b.flat(2)
    for i in range(6):
        b.bump(1.5, rng.uniform(0.2, 0.5)).flat(1).gap(rng.uniform(0.4, 0.7)).flat(0.8)
    b.flat(2)
    return *b.build(), "bumps + small gaps"

def _terrain_5(rng) -> tuple[list, list, str]:
    """Extreme alternating steps — tall steps up and down."""
    b = TerrainBuilder()
    b.flat(2)
    up = True
    for _ in range(8):
        if up:
            b.step_up(rng.uniform(0.3, 0.6)).flat(1.2)
        else:
            b.step_down(rng.uniform(0.3, 0.6)).flat(1.2)
        up = not up
    # Bring back to 0
    b.ramp(2.0, -b.y)
    b.flat(2)
    return *b.build(), "alternating extreme steps"

def _terrain_6(rng) -> tuple[list, list, str]:
    """Pit traps mixed with bumps."""
    b = TerrainBuilder()
    b.flat(3).pit(2.0, 0.8).flat(2).bump(2, 0.5).flat(1).pit(2.5, 1.2).flat(2)
    b.bump(1.5, 0.35).flat(1).pit(1.8, 0.6).flat(2).bump(2, 0.6).flat(3)
    return *b.build(), "pit traps + bumps"

def _terrain_7(rng) -> tuple[list, list, str]:
    """Hard: mixed everything — random composition."""
    primitives = ["flat", "bump", "gap_small", "gap_large", "step_up", "step_down", "pit"]
    b = TerrainBuilder()
    b.flat(1.5)
    x_used = 1.5
    while x_used < 27:
        choice = rng.choice(primitives)
        if choice == "flat":
            l = rng.uniform(0.8, 2.0)
            b.flat(l); x_used += l
        elif choice == "bump":
            l = rng.uniform(1.0, 2.5)
            b.bump(l, rng.uniform(0.15, 0.6)); x_used += l
        elif choice == "gap_small":
            w = rng.uniform(0.3, 0.75)
            b.gap(w); x_used += w
        elif choice == "gap_large":
            w = rng.uniform(2.0, 3.5)
            b.gap(w); x_used += w
        elif choice == "step_up" and b.y < 1.5:
            h = rng.uniform(0.2, 0.45)
            b.step_up(h);
        elif choice == "step_down" and b.y > 0.05:
            h = min(rng.uniform(0.2, 0.45), b.y)
            b.step_down(h)
        elif choice == "pit" and b.y < 0.5:
            b.flat(0.5); x_used += 0.5
        elif choice == "pit":
            w = rng.uniform(1.5, 2.5)
            b.pit(w, min(rng.uniform(0.4, 0.8), b.y)); x_used += w
    # Return to floor
    if b.y > 0.05:
        b.ramp(1.0, -b.y)
    remain = ENV_RIGHT - b.x
    if remain > 0:
        b.flat(remain)
    return *b.build(), "hard: random mix"

def _terrain_8(rng) -> tuple[list, list, str]:
    """Long flat with a single massive central wall obstacle."""
    b = TerrainBuilder()
    b.flat(12).wall_obstacle(1.5, 0.2).flat(1).gap(2.5).flat(14.3)
    return *b.build(), "long flat + wall + large gap"

def _terrain_9(rng) -> tuple[list, list, str]:
    """Platforms + gaps — multi-height traversal."""
    b = TerrainBuilder()
    b.flat(2)
    b.gap(1.2)
    b._segs.append(((b.x, 0.6), (b.x + 3.0, 0.6))); b.x += 3.0; b.y = 0.6
    b.gap(1.5)
    b._segs.append(((b.x, 1.2), (b.x + 2.5, 1.2))); b.x += 2.5; b.y = 1.2
    b.gap(0.6)
    b._segs.append(((b.x, 1.2), (b.x + 2.0, 1.2))); b.x += 2.0
    b.gap(2.0)
    b._segs.append(((b.x, 0.6), (b.x + 2.5, 0.6))); b.x += 2.5; b.y = 0.6
    b.gap(1.0)
    b._segs.append(((b.x, 0.0), (b.x + 5.0, 0.0))); b.x += 5.0; b.y = 0.0
    remain = ENV_RIGHT - b.x
    if remain > 0:
        b._segs.append(((b.x, 0.0), (ENV_RIGHT, 0.0)))
    return *b.build(), "floating platforms at varied heights"


SCENARIOS = [
    _terrain_0, _terrain_1, _terrain_2, _terrain_3, _terrain_4,
    _terrain_5, _terrain_6, _terrain_7, _terrain_8, _terrain_9,
]


def generate(seed: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(seed)
    fn  = SCENARIOS[seed % len(SCENARIOS)]
    segs, gaps, title = fn(rng)
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
