# 4th Graph Analysis: Robot Falls Through Floor

## Problem
In the bottom-right subplot (gait phase 4), the hexapod's support legs penetrate below the ground surface. The optimizer reports loss=156 and optimality=45.9 — it failed to converge.

## Root Causes

### 1. No ground penetration constraint on support legs
The loss function for support (non-free) legs only pins them to their previous world-space position (`self.targets[i]`). There is no constraint that these positions are on or above the ground surface. If the body shifts such that old foot positions end up below ground, nothing prevents it.

- File: `2d_wall_tackle.py`, lines 211-213
- Support legs use: `(e.p.x - targets[i].x)^2 + (e.p.y - targets[i].y)^2`
- Missing: any term involving `gym.surface_xy()` for support feet

### 2. Stale target positions after body moves
`update_targets_and_change_free_leg_set()` snapshots leg end positions from the current pose as fixed targets for the next phase's support legs. Between phases, the body can shift significantly, making those old world-space targets geometrically incompatible with the new body pose.

- File: `2d_wall_tackle.py`, lines 162-171
- Targets are set once and never updated relative to ground

### 3. Soft constraints only, no hard ground contact
The only "above ground" enforcement is an exponential penalty on **mount points** (`0.2 * exp(-10*y)`). Leg **endpoints** have no ground-surface constraint at all. The leg direction slack bounds (`ub = [-0.3]*4`) constrain foot orientation but not foot position.

- File: `2d_wall_tackle.py`, lines 191-194 (mount penalty)
- File: `2d_wall_tackle.py`, lines 156-160 (slack bounds)

### 4. Poor initialization for phase 4
`add_slack_variables()` resets slack variables to hardcoded values (`-1, -1, -1, -1, 2.5, 2.5`) regardless of current robot state. By phase 4 the robot is far from origin, so these values are far from feasible.

- File: `2d_wall_tackle.py`, lines 142-154
- Phase 3 converged: loss=-0.57, optimality=6e-5
- Phase 4 failed: loss=156, optimality=45.9

## Potential Fixes

1. **Add ground constraint for support legs**: penalize `max(0, surface_y(foot_x) - foot_y)` for all support feet
2. **Warm-start slack variables**: initialize from the previous solution instead of hardcoded values
3. **Add ground penetration penalty for all legs**: `exp(-k * (foot_y - surface_y(foot_x)))` for every foot
4. **Constrain body_y relative to surface**: the body lower bound `lb[1] = 0.0` assumes flat ground — should be surface-aware
