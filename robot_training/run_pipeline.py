"""
Pure-PPO training pipeline — no hardcoded gait, all locomotion model-generated.

  1. Generate more terrain variations (if needed)
  2. PPO training from random init: right model, then left model
  3. Evaluate on test set with rollout planner, save GIFs

Usage:
    .venv/bin/python -m robot_training.run_pipeline [--ppo-only] [--eval-only]
    .venv/bin/python -m robot_training.run_pipeline --ppo-iters 2000
"""

import argparse
import time
from pathlib import Path

import torch

ROOT      = Path(__file__).parent
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ppo-only",   action="store_true")
    ap.add_argument("--eval-only",  action="store_true")
    ap.add_argument("--ppo-iters",  type=int, default=2000,
                    help="PPO iterations per direction (default 2000)")
    ap.add_argument("--gen-more",   action="store_true",
                    help="Generate additional terrains before training")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    if args.gen_more:
        print("\n[0] Generating additional terrains ...")
        _generate_more_terrains()

    from robot_training.dataset import list_terrains, split_terrains
    entries = list_terrains()
    train_set, val_set, test_set = split_terrains(entries)
    print(f"\nDataset: total={len(entries)}  train={len(train_set)}  "
          f"val={len(val_set)}  test={len(test_set)}")

    if not args.eval_only:
        from robot_training.ppo.trainer import PPOTrainer
        for direction, label in [(1, "right"), (-1, "left")]:
            # Skip right model if best checkpoint already exists (already trained)
            best_ckpt = MODEL_DIR / f"ppo_best_{label}.pt"
            if direction > 0 and best_ckpt.exists():
                print(f"\n[PPO] Right model already trained ({best_ckpt}), skipping")
                continue
            print(f"\n[PPO] Training [{label}] — model-generated gait only")
            trainer = PPOTrainer(
                direction  = direction,
                train_set  = train_set,
                val_set    = val_set,
                model_dir  = MODEL_DIR,
                n_iters    = args.ppo_iters,
                init_model = None,
                device     = device,
            )
            trainer.train()

    print("\n[Eval] Evaluating on test set with rollout planner ...")
    from robot_training.eval.evaluate import evaluate_direction
    for direction, label in [(1, "right"), (-1, "left")]:
        best_model = MODEL_DIR / f"ppo_best_{label}.pt"
        if not best_model.exists():
            best_model = MODEL_DIR / f"ppo_final_{label}.pt"
        if not best_model.exists():
            print(f"  No PPO model found for [{label}], skipping")
            continue
        print(f"\n  [{label}] model: {best_model}")
        evaluate_direction(
            direction    = direction,
            model_path   = best_model,
            test_entries = test_set,
            device       = device,
        )

    print("\n=== Pipeline complete ===")


def _generate_more_terrains():
    """Generate seeds 10-19 for each method to expand training data."""
    from robot_environment.terr_gen import (
        gen_primitive, gen_fbm_noise, gen_random_walk, gen_spline, gen_wfc
    )
    for mod in (gen_primitive, gen_fbm_noise, gen_random_walk, gen_spline, gen_wfc):
        for s in range(10, 20):
            try:
                mod.generate(s)
            except Exception as exc:
                print(f"  Warning: {mod.METHOD} seed={s}: {exc}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"Total time: {time.time() - t0:.0f}s")
