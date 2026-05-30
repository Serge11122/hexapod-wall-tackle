"""
Train the walking policy against the CORRECTED physics (no levitation; body
supported by leg contact; boosted foot/terrain grip).

PPO-LSTM with the existing curriculum (primitive → all terrain) and a velocity
curriculum (fast joints to discover a gait → realistic 40°/s).  Best model is
selected on validation distance evaluated at realistic joint speed.

Usage:
    .venv/bin/python -m robot_training.train_walk --direction 1 --iters 600
    .venv/bin/python -m robot_training.train_walk --unit-test   # <2 min smoke
"""

import argparse
import random
from pathlib import Path

import numpy as np
import torch

from robot_training.dataset import list_terrains, split_terrains
from robot_training.ppo.trainer import PPOTrainer

MODEL_DIR = Path(__file__).parent / "models"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--direction", type=int, default=1)
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--init-model", default=None)
    ap.add_argument("--unit-test", action="store_true")
    args = ap.parse_args()

    if args.unit_test:
        args.iters = 6

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    entries = list_terrains()
    train_set, val_set, test_set = split_terrains(entries)
    print(f"Device={device}  terrains: train={len(train_set)} val={len(val_set)} "
          f"test={len(test_set)}  seed={args.seed}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    trainer = PPOTrainer(
        direction = args.direction,
        train_set = train_set,
        val_set   = val_set,
        model_dir = MODEL_DIR,
        n_iters   = args.iters,
        init_model = args.init_model,
        device    = device,
    )
    trainer.train()

    if args.unit_test:
        label = "right" if args.direction > 0 else "left"
        assert (MODEL_DIR / f"ppo_final_{label}.pt").exists(), "no model saved"
        print("UNIT-TEST PASS: training loop ran and saved a model.")


if __name__ == "__main__":
    main()
