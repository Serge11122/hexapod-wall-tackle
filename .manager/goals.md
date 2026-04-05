# Hexapod Wall Tackle Project Goals

## Core Thesis

A 2D quadruped robot can learn to climb over obstacles of varying heights through optimized joint angle sequences. By combining forward kinematics, constraint-based optimization, and differentiable rendering, we can synthesize locomotion gaits that successfully navigate parametric wall heights.

## Architecture

- **Robot Model** — 2D quadruped with 4 legs (body + 2 joints per leg). Each leg has fixed segment lengths (L1, L2). Pose is described by 11 parameters: 3 for body (x, y, angle) + 8 for leg joint angles.

- **Ground & Obstacle** — Flat ground with a vertical wall of parametric height. Robot must transition from ground level to obstacle height while maintaining stability and leg constraints.

- **Solver** — Constraint-based optimization to find joint angle sequences that: (1) lift legs over the obstacle, (2) maintain valid leg positions within reachable workspace, (3) enforce gait phases (support/swing legs). Supports multiple optimization backends.

## Goals

- Synthesize valid locomotion gaits for obstacles of various heights
- Produce smooth animations of robot climbing via optimized joint sequences
- Maintain forward kinematics validity and leg workspace constraints throughout motion
- Extend to multi-phase gaits (e.g., diagonal or trotting patterns)
