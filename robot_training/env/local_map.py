"""
1D rolling local map maintained from foot touch data.

The robot has no prior knowledge of the terrain.  Each time a foot contacts
the ground, we record the contact height at that world-x.  Each time a foot
swings through air at a known height we mark "air above this level".

The map is a fixed-resolution 1D array indexed by world-x.  At each step,
we present a window of W cells centered ahead of the robot as part of the
observation vector.

Map cells store:
  known_height : float  — best estimate of terrain surface y (nan if unknown)
  is_gap       : float  — 1.0 if foot descended below known height (gap likely)
"""

import math
import numpy as np

RESOLUTION = 0.1     # world units per cell
MAP_TOTAL  = 40.0    # total world width tracked
N_CELLS    = int(MAP_TOTAL / RESOLUTION)  # 400 cells

WINDOW_BEHIND  = 2.0   # world units to include behind robot
WINDOW_AHEAD   = 4.0   # world units to include ahead of robot
WINDOW_CELLS   = int((WINDOW_BEHIND + WINDOW_AHEAD) / RESOLUTION)   # 60 cells
OBS_CHANNELS   = 3     # [known_flag, known_height_norm, is_gap]
OBS_SIZE       = WINDOW_CELLS * OBS_CHANNELS   # 180


class LocalMap:
    def __init__(self, env_left: float = -15.0, env_right: float = 15.0):
        self.env_left = env_left
        self.n_cells  = int((env_right - env_left) / RESOLUTION) + 1
        self.known_height = np.full(self.n_cells, np.nan, dtype=np.float32)
        self.is_gap       = np.zeros(self.n_cells, dtype=np.float32)

    def _x_to_idx(self, x: float) -> int:
        return int(round((x - self.env_left) / RESOLUTION))

    def _idx_to_x(self, idx: int) -> float:
        return self.env_left + idx * RESOLUTION

    def update_contact(self, foot_x: float, foot_y: float, is_contact: bool) -> None:
        """Call for each leg each step with its foot world position."""
        idx = self._x_to_idx(foot_x)
        if idx < 0 or idx >= self.n_cells:
            return
        if is_contact:
            # Foot is on ground — record terrain height
            old = self.known_height[idx]
            if math.isnan(old):
                self.known_height[idx] = foot_y
            else:
                self.known_height[idx] = 0.7 * old + 0.3 * foot_y   # EWMA
            self.is_gap[idx] = 0.0
        else:
            # Foot is in air — if we previously knew height here and foot is
            # now significantly below it → gap signal
            kh = self.known_height[idx]
            if not math.isnan(kh) and foot_y < kh - 0.3:
                self.is_gap[idx] = 1.0

    def get_observation(self, robot_x: float, direction: int) -> np.ndarray:
        """
        Extract window around robot.
        direction: +1 for walking right, -1 for walking left.
        Window: [behind, ahead] = direction-aware.
        Returns float32 array of shape (OBS_SIZE,).
        """
        if direction >= 0:
            x_start = robot_x - WINDOW_BEHIND
            x_end   = robot_x + WINDOW_AHEAD
        else:
            x_start = robot_x - WINDOW_AHEAD
            x_end   = robot_x + WINDOW_BEHIND

        window = np.zeros((WINDOW_CELLS, OBS_CHANNELS), dtype=np.float32)
        for wi in range(WINDOW_CELLS):
            wx   = x_start + wi * RESOLUTION
            idx  = self._x_to_idx(wx)
            if 0 <= idx < self.n_cells:
                kh = self.known_height[idx]
                if not math.isnan(kh):
                    window[wi, 0] = 1.0          # known
                    window[wi, 1] = kh / 3.0     # height normalized (max ~3 world units)
                    window[wi, 2] = self.is_gap[idx]
        return window.reshape(-1)   # (OBS_SIZE,)

    def reset(self) -> None:
        self.known_height[:] = np.nan
        self.is_gap[:]       = 0.0
