"""
PPO trainer for hexapod terrain traversal.

Trains two separate policies: right-walking and left-walking.

Curriculum:
  Phase 1 (first 1/3 of iterations): flat + easy terrains only
  Phase 2 (next 1/3): all training terrains
  Phase 3 (last 1/3): weighted toward hard terrains

Logging: prints episode stats every LOG_INTERVAL iterations.
Best model saved by validation mean distance.
"""

import time
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from robot_training.models.policy import ActorCritic, save_policy, load_policy
from robot_training.env.terrain_env import TerrainTraversalEnv, OBS_DIM, ACT_DIM
from robot_training.ppo.buffer import RolloutBuffer
from robot_training.dataset import TerrainEntry

# ── PPO hyper-params ───────────────────────────────────────────────────────────
N_STEPS_PER_ITER = 512      # rollout steps collected before each update
N_EPOCHS         = 6        # PPO epochs per iteration
BATCH_SIZE       = 128
CLIP_EPS         = 0.2
VALUE_COEF       = 0.5
ENTROPY_COEF     = 0.01
MAX_GRAD_NORM    = 0.5
GAMMA            = 0.99
GAE_LAMBDA       = 0.95
LR               = 3e-4
LOG_INTERVAL     = 10       # log every N iters
VAL_INTERVAL     = 20       # validate every N iters


class PPOTrainer:
    def __init__(
        self,
        direction:   int,
        train_set:   list[TerrainEntry],
        val_set:     list[TerrainEntry],
        model_dir:   Path,
        n_iters:     int  = 400,
        init_model:  str | None = None,
        device:      torch.device = None,
    ):
        self.direction  = direction
        self.train_set  = train_set
        self.val_set    = val_set
        self.model_dir  = Path(model_dir)
        self.n_iters    = n_iters
        self.label      = "right" if direction > 0 else "left"
        self.device     = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_dir.mkdir(parents=True, exist_ok=True)

        if init_model and Path(init_model).exists():
            print(f"  PPO [{self.label}]: loading BC init from {init_model}")
            self.policy = load_policy(init_model, self.device)
        else:
            print(f"  PPO [{self.label}]: random init")
            self.policy = ActorCritic(OBS_DIM, ACT_DIM).to(self.device)

        self.optimiser = torch.optim.Adam(self.policy.parameters(), lr=LR)
        self.buffer    = RolloutBuffer(N_STEPS_PER_ITER, OBS_DIM, ACT_DIM,
                                       GAMMA, GAE_LAMBDA, self.device)
        self.env       = TerrainTraversalEnv(direction=direction)

        self.best_val_dist = -float("inf")
        self.rng = random.Random(42 + (0 if direction > 0 else 1))

    def _sample_terrain(self, phase: float) -> TerrainEntry:
        """Sample a training terrain according to curriculum phase."""
        if phase < 0.33:
            # Easy: prefer primitive (flat/bumpy) terrains
            easy = [e for e in self.train_set if e.method == "primitive"]
            pool = easy if easy else self.train_set
        elif phase < 0.67:
            pool = self.train_set
        else:
            # Hard: weight toward non-primitive
            hard = [e for e in self.train_set if e.method != "primitive"]
            pool = hard if hard else self.train_set
        return self.rng.choice(pool)

    def _collect_rollouts(self, phase: float) -> dict:
        """Collect N_STEPS_PER_ITER transitions. Returns episode stats."""
        self.buffer.reset()
        self.policy.eval()

        entry    = self._sample_terrain(phase)
        obs      = self.env.reset(entry)
        ep_lens  = []
        ep_rews  = []
        ep_dists = []
        ep_succ  = 0
        ep_len   = 0
        ep_rew   = 0.0

        with torch.no_grad():
            for _ in range(N_STEPS_PER_ITER):
                obs_t   = torch.from_numpy(obs).unsqueeze(0).to(self.device)
                action, log_prob, value = self.policy.act(obs_t)
                action_np   = action.squeeze(0).cpu().numpy()
                log_prob_np = log_prob.item()
                value_np    = value.item()

                next_obs, reward, done, info = self.env.step(action_np)
                self.buffer.add(obs, action_np, reward, float(done), value_np, log_prob_np)

                ep_len  += 1
                ep_rew  += reward
                obs      = next_obs

                if done:
                    ep_lens.append(ep_len)
                    ep_rews.append(ep_rew)
                    ep_dists.append(info["dist"])
                    if info["success"]:
                        ep_succ += 1
                    ep_len, ep_rew = 0, 0.0
                    entry = self._sample_terrain(phase)
                    obs   = self.env.reset(entry)

            # Bootstrap value for last step
            obs_t   = torch.from_numpy(obs).unsqueeze(0).to(self.device)
            _, _, last_val = self.policy.act(obs_t)
            self.buffer.compute_returns_and_advantages(last_val.item())

        return {
            "ep_len":  np.mean(ep_lens) if ep_lens else ep_len,
            "ep_rew":  np.mean(ep_rews) if ep_rews else ep_rew,
            "ep_dist": np.mean(ep_dists) if ep_dists else 0.0,
            "success_rate": ep_succ / max(len(ep_lens), 1),
        }

    def _ppo_update(self) -> dict:
        self.policy.train()
        losses_pol, losses_val, losses_ent = [], [], []

        for _ in range(N_EPOCHS):
            for obs_b, act_b, adv_b, ret_b, old_lp_b in self.buffer.get_batches(BATCH_SIZE):
                log_prob, entropy, value = self.policy.evaluate_actions(obs_b, act_b)

                ratio      = (log_prob - old_lp_b).exp()
                surr1      = ratio * adv_b
                surr2      = ratio.clamp(1 - CLIP_EPS, 1 + CLIP_EPS) * adv_b
                policy_loss = -torch.min(surr1, surr2).mean()
                value_loss  = nn.functional.mse_loss(value, ret_b)
                entropy_loss = -entropy.mean()

                loss = policy_loss + VALUE_COEF * value_loss + ENTROPY_COEF * entropy_loss
                self.optimiser.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.policy.parameters(), MAX_GRAD_NORM)
                self.optimiser.step()

                losses_pol.append(policy_loss.item())
                losses_val.append(value_loss.item())
                losses_ent.append(entropy_loss.item())

        return {
            "loss_pol": np.mean(losses_pol),
            "loss_val": np.mean(losses_val),
            "loss_ent": np.mean(losses_ent),
        }

    def _validate(self) -> float:
        self.policy.eval()
        dists = []
        with torch.no_grad():
            for entry in self.val_set[:8]:   # limit to 8 val terrains
                obs  = self.env.reset(entry)
                done = False
                while not done:
                    obs_t  = torch.from_numpy(obs).unsqueeze(0).to(self.device)
                    action, _, _ = self.policy.act(obs_t, deterministic=True)
                    obs, _, done, info = self.env.step(action.squeeze(0).cpu().numpy())
                dists.append(info["dist"])
        return float(np.mean(dists))

    def train(self) -> None:
        print(f"\n{'='*60}")
        print(f"PPO training [{self.label}]  iters={self.n_iters}  device={self.device}")
        print(f"{'='*60}")
        t0 = time.time()

        for it in range(1, self.n_iters + 1):
            phase = it / self.n_iters

            ep_stats   = self._collect_rollouts(phase)
            loss_stats = self._ppo_update()

            if it % LOG_INTERVAL == 0:
                print(f"  iter {it:4d}/{self.n_iters} | "
                      f"dist={ep_stats['ep_dist']:5.1f}  rew={ep_stats['ep_rew']:6.1f}  "
                      f"succ={ep_stats['success_rate']:.2f} | "
                      f"L_pol={loss_stats['loss_pol']:.4f}  "
                      f"L_val={loss_stats['loss_val']:.4f}  "
                      f"t={time.time()-t0:.0f}s")

            if it % VAL_INTERVAL == 0:
                val_dist = self._validate()
                print(f"  → VAL dist={val_dist:.2f}")
                if val_dist > self.best_val_dist:
                    self.best_val_dist = val_dist
                    best_path = self.model_dir / f"ppo_best_{self.label}.pt"
                    save_policy(self.policy, str(best_path))
                    print(f"  ✓ best saved → {best_path}")

        # Save final
        final_path = self.model_dir / f"ppo_final_{self.label}.pt"
        save_policy(self.policy, str(final_path))
        print(f"\nFinal model → {final_path}")
        print(f"Best val dist = {self.best_val_dist:.2f}")
