"""
Full training pipeline:
  1. Generate more terrain variations (if needed)
  2. Collect BC data from hardcoded gait
  3. BC pretraining (right model, left model)
  4. PPO fine-tuning (right model, left model)
  5. Evaluate on test set, save GIFs

Usage:
    .venv/bin/python -m robot_training.run_pipeline [--bc-only] [--ppo-only] [--eval-only]
    .venv/bin/python -m robot_training.run_pipeline --bc-steps 600 --ppo-iters 300
"""

import argparse
import time
from pathlib import Path

import torch

ROOT       = Path(__file__).parent
DATA_DIR   = ROOT / "data" / "bc"
MODEL_DIR  = ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bc-only",    action="store_true")
    ap.add_argument("--ppo-only",   action="store_true")
    ap.add_argument("--eval-only",  action="store_true")
    ap.add_argument("--bc-steps",   type=int, default=800)
    ap.add_argument("--ppo-iters",  type=int, default=400)
    ap.add_argument("--gen-more",   action="store_true",
                    help="Generate additional terrains for richer training set")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # ── 0. Optionally generate more terrains ──────────────────────────────
    if args.gen_more:
        print("\n[0] Generating additional terrains ...")
        _generate_more_terrains()

    # ── Load dataset split ────────────────────────────────────────────────
    from robot_training.dataset import list_terrains, split_terrains
    entries = list_terrains()
    train_set, val_set, test_set = split_terrains(entries)
    print(f"\nDataset: total={len(entries)}  train={len(train_set)}  "
          f"val={len(val_set)}  test={len(test_set)}")

    if not args.ppo_only and not args.eval_only:
        # ── 1. BC data collection ─────────────────────────────────────────
        print("\n[1] BC data collection ...")
        from robot_training.bc.collect import collect_and_save
        collect_and_save(DATA_DIR, n_steps_per_dir=args.bc_steps)

        # ── 2. BC training ────────────────────────────────────────────────
        print("\n[2] BC training ...")
        from robot_training.bc.train import train_bc_both
        train_bc_both(DATA_DIR, MODEL_DIR)

    if args.bc_only:
        print("\nBC-only run complete.")
        return

    if not args.eval_only:
        # ── 3. PPO fine-tuning ────────────────────────────────────────────
        from robot_training.ppo.trainer import PPOTrainer
        for direction, label in [(1, "right"), (-1, "left")]:
            bc_model = MODEL_DIR / f"bc_{label}.pt"
            init     = str(bc_model) if bc_model.exists() else None
            trainer  = PPOTrainer(
                direction   = direction,
                train_set   = train_set,
                val_set     = val_set,
                model_dir   = MODEL_DIR,
                n_iters     = args.ppo_iters,
                init_model  = init,
                device      = device,
            )
            trainer.train()

    # ── 4. Evaluation ─────────────────────────────────────────────────────
    print("\n[4] Evaluating on test set ...")
    from robot_training.eval.evaluate import evaluate_direction
    for direction, label in [(1, "right"), (-1, "left")]:
        best_model = MODEL_DIR / f"ppo_best_{label}.pt"
        if not best_model.exists():
            best_model = MODEL_DIR / f"ppo_final_{label}.pt"
        if not best_model.exists():
            best_model = MODEL_DIR / f"bc_{label}.pt"
        if not best_model.exists():
            print(f"  No model found for [{label}], skipping")
            continue
        print(f"\n  [{label}] model: {best_model}")
        evaluate_direction(
            direction     = direction,
            model_path    = best_model,
            test_entries  = test_set,
            device        = device,
        )

    print("\n=== Pipeline complete ===")


def _generate_more_terrains():
    """Generate seeds 10-19 for each method to expand training data."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from robot_environment.terr_gen import (
        gen_primitive, gen_fbm_noise, gen_random_walk, gen_spline, gen_wfc
    )
    EXTRA_SEEDS = range(10, 20)
    for mod in (gen_primitive, gen_fbm_noise, gen_random_walk, gen_spline, gen_wfc):
        for s in EXTRA_SEEDS:
            try:
                mod.generate(s)
            except Exception as e:
                print(f"  Warning: {mod.METHOD} seed={s} failed: {e}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"Total time: {time.time() - t0:.0f}s")
