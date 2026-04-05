"""
Visualize ground-truth hexapod poses overlaid on step terrain.

For each hexapod variation JSON, renders one subplot per step and saves a PNG
to ground_truth_terrain/output/.

Usage:
    python ground_truth_terrain/visualize.py
"""

import json
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

HERE = Path(__file__).parent
OUTPUT_DIR = HERE / 'output'
OUTPUT_DIR.mkdir(exist_ok=True)

# ── geometry helpers ─────────────────────────────────────────────────────────

def rot(theta):
    """2D rotation matrix."""
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


def transform(origin_xy, theta, local_xy):
    """Apply a 2D rigid transform: world = R(theta) * local + origin."""
    return rot(theta) @ np.array(local_xy) + np.array(origin_xy)


def leg_points(body_xy, body_theta, mount_local_x, theta1, theta2, L1=1.0, L2=1.2):
    """
    Return (mount_world, knee_world, foot_world) for one leg.

    The mount point sits at (mount_local_x, 0) in the body frame.
    theta1 rotates the first segment relative to the body forward axis.
    theta2 rotates the second segment relative to the first.
    """
    mount_w = transform(body_xy, body_theta, [mount_local_x, 0.0])

    # knee = mount + L1 in direction (body_theta + theta1)
    knee_angle = body_theta + theta1
    knee_w = mount_w + L1 * np.array([math.cos(knee_angle), math.sin(knee_angle)])

    # foot = knee + L2 in direction (body_theta + theta1 + theta2)
    foot_angle = knee_angle + theta2
    foot_w = knee_w + L2 * np.array([math.cos(foot_angle), math.sin(foot_angle)])

    return mount_w, knee_w, foot_w


def body_corners(body_xy, body_theta, half_len=1.0, half_h=0.2):
    """Return the four corners of the body rectangle in world frame."""
    corners_local = [
        [ half_len,  half_h],
        [-half_len,  half_h],
        [-half_len, -half_h],
        [ half_len, -half_h],
    ]
    return [transform(body_xy, body_theta, c) for c in corners_local]


# ── terrain ──────────────────────────────────────────────────────────────────

def load_terrain(terrain_path):
    with open(terrain_path) as f:
        return json.load(f)


def terrain_polyline(terrain):
    """Return (xs, ys) arrays for drawing the step terrain as a solid line."""
    pts = terrain['surface_points']
    xs = [p['x'] for p in pts]
    ys = [p['y'] for p in pts]
    return xs, ys


# ── drawing ──────────────────────────────────────────────────────────────────

MOUNT_COLORS  = ['#1f77b4', '#1f77b4']   # blue dots for mount points
UPPER_SEG_CLR = '#1f77b4'               # blue  — upper leg segment (mount→knee)
LOWER_SEG_CLR = '#d62728'               # red   — lower leg segment (knee→foot)
BODY_CLR       = '#2ca02c'              # green — body rectangle
PLANTED_MARKER = 'ks'                   # black square
FREE_MARKER    = 'kx'                   # black cross


def draw_step(ax, step_data, terrain_xs, terrain_ys):
    """Draw terrain + one hexapod pose on the given axes."""
    # Terrain
    ax.plot(terrain_xs, terrain_ys, 'k-', linewidth=2, zorder=1)

    body_xy    = [step_data['body']['x'], step_data['body']['y']]
    body_theta = step_data['body']['theta']
    free_legs  = set(step_data['free_legs'])

    # Body rectangle
    corners = body_corners(body_xy, body_theta)
    xs = [c[0] for c in corners] + [corners[0][0]]
    ys = [c[1] for c in corners] + [corners[0][1]]
    ax.plot(xs, ys, color=BODY_CLR, linewidth=2, zorder=3)

    # Mount dots
    for mount_local_x in [1.0, -1.0]:
        mw = transform(body_xy, body_theta, [mount_local_x, 0.0])
        ax.plot(mw[0], mw[1], 'o', color=MOUNT_COLORS[0], markersize=7, zorder=4)

    # Legs
    for leg in step_data['legs']:
        leg_id    = leg['id']
        theta1    = leg['theta1']
        theta2    = leg['theta2']
        mount_lx  = 1.0 if leg_id in (0, 1) else -1.0

        mount_w, knee_w, foot_w = leg_points(body_xy, body_theta, mount_lx, theta1, theta2)

        ax.plot([mount_w[0], knee_w[0]], [mount_w[1], knee_w[1]],
                color=UPPER_SEG_CLR, linewidth=2, zorder=3)
        ax.plot([knee_w[0], foot_w[0]], [knee_w[1], foot_w[1]],
                color=LOWER_SEG_CLR, linewidth=2, zorder=3)

        marker = FREE_MARKER if leg_id in free_legs else PLANTED_MARKER
        ax.plot(foot_w[0], foot_w[1], marker, markersize=8, zorder=5)

        # Foot direction tick (red dotted)
        foot_angle = body_theta + theta1 + theta2
        ax.plot([foot_w[0], foot_w[0] + 0.5 * math.cos(foot_angle)],
                [foot_w[1], foot_w[1] + 0.5 * math.sin(foot_angle)],
                'r:', linewidth=1, zorder=2)

    # Annotations
    ax.set_title(f"Step {step_data['step_index']}: {step_data['description']}", fontsize=7, wrap=True)
    ax.set_aspect('equal', 'box')
    ax.set_xlim(-4, 8)
    ax.set_ylim(-3, 4)
    ax.tick_params(labelsize=7)


# ── main ─────────────────────────────────────────────────────────────────────

def process_variation(variation_path, terrain):
    with open(variation_path) as f:
        data = json.load(f)

    steps = data['steps']
    n = len(steps)

    terrain_xs, terrain_ys = terrain_polyline(terrain)

    # Layout: up to 4 columns
    ncols = min(n, 4)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4.5 * nrows))
    axes = np.array(axes).flatten() if n > 1 else [axes]

    for i, step in enumerate(steps):
        draw_step(axes[i], step, terrain_xs, terrain_ys)

    # Hide any unused axes
    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    # Legend
    legend_handles = [
        mpatches.Patch(color=BODY_CLR,       label='Body'),
        mpatches.Patch(color=UPPER_SEG_CLR,  label='Upper leg (L1=1.0)'),
        mpatches.Patch(color=LOWER_SEG_CLR,  label='Lower leg (L2=1.2)'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor='k', markersize=8, label='Planted foot'),
        plt.Line2D([0], [0], marker='x', color='k', markersize=8, label='Free foot (swing)'),
    ]
    fig.legend(handles=legend_handles, loc='lower center', ncol=5, fontsize=8,
               bbox_to_anchor=(0.5, -0.02))

    stem = variation_path.stem
    title = data.get('description', stem)
    fig.suptitle(f"{stem}\n{title}", fontsize=9, y=1.01)

    plt.tight_layout()
    out_path = OUTPUT_DIR / f"{stem}.png"
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {out_path}')


def main():
    terrain = load_terrain(HERE / 'terrain.json')

    variations = sorted(HERE.glob('hexapod_variation_*.json'))
    assert variations, f'No hexapod_variation_*.json files found in {HERE}'

    for v in variations:
        process_variation(v, terrain)


if __name__ == '__main__':
    main()
