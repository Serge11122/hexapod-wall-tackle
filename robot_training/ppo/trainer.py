"""
PPO trainer for hexapod terrain traversal.

Uses LSTMActorCritic for temporal gait coordination.
LSTM hidden state is maintained across steps during rollout and reset at
episode boundaries. During the PPO update, stored hidden states enable
independent per-step LSTM forward passes (no BPTT — simpler and stable).

Curriculum:
  Phase 0–0.40: only primitive (flat bumpy) terrain
  Phase 0.40–0.65: mostly primitive + some easy terrain
  Phase 0.65–1.00: all terrain types, bias toward hard at end
"""

import time
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from robot_training.models.policy import (
    LSTMActorCritic, save_policy, load_policy, LSTM_DIM, INIT_LOG_STD, FINAL_LOG_STD,
)
from robot_training.env.terrain_env import TerrainTraversalEnv, OBS_DIM, ACT_DIM
from robot_training.ppo.buffer import RolloutBuffer
from robot_training.dataset import TerrainEntry

# ── PPO hyper-params ───────────────────────────────────────────────────────────
N_STEPS_PER_ITER = 2048    # large rollout: diverse transitions, stable GAE
N_EPOCHS         = 4       # conservative — prevent policy destruction
BATCH_SIZE       = 256
CLIP_EPS         = 0.10    # tight clip: preserve learned behaviors
VALUE_COEF       = 0.5
MAX_GRAD_NORM    = 0.5
GAMMA            = 0.99
GAE_LAMBDA       = 0.95
LR               = 1e-4
LOG_INTERVAL     = 10
VAL_INTERVAL     = 25
# Exploration is controlled via policy.log_std annealing (see INIT_LOG_STD/FINAL_LOG_STD)


class PPOTrainer:
    def __init__(
        self,
        direction:   int,
        train_set:   list[TerrainEntry],
        val_set:     list[TerrainEntry],
        model_dir:   Path,
        n_iters:     int  = 2000,
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
            print(f"  PPO [{self.label}]: continuing from {init_model}")
            self.policy = load_policy(init_model, self.device)
            if not isinstance(self.policy, LSTMActorCritic):
                print(f"  [{self.label}]: upgrading MLP → LSTM (fresh start)")
                self.policy = LSTMActorCritic(OBS_DIM, ACT_DIM).to(self.device)
        else:
            print(f"  PPO [{self.label}]: LSTM + fixed-std — mean forced to learn walking")
            self.policy = LSTMActorCritic(OBS_DIM, ACT_DIM).to(self.device)

        self.optimiser = torch.optim.Adam(self.policy.parameters(), lr=LR)
        self.buffer    = RolloutBuffer(
            N_STEPS_PER_ITER, OBS_DIM, ACT_DIM, GAMMA, GAE_LAMBDA,
            self.device, lstm_dim=LSTM_DIM,
        )
        self.env = TerrainTraversalEnv(direction=direction)

        self.best_val_dist = -float("inf")
        self.rng = random.Random(42 + (0 if direction > 0 else 1))

        self._good_train = self._screen_train_terrains()
        print(f"  [{self.label}] Good training terrains: {len(self._good_train)}/{len(self.train_set)}")

    # ── Terrain screening ─────────────────────────────────────────────────────

    def _screen_train_terrains(self, min_dist: float = 0.5, n_steps: int = 80) -> list:
        """Find training terrains where policy achieves min_dist with short rollout."""
        good = []
        self.policy.eval()
        with torch.no_grad():
            for entry in self.train_set:
                obs  = self.env.reset(entry)
                done = False
                info = {"dist": 0.0}
                lstm_state = self.policy.init_hidden(1)
                for _ in range(n_steps):
                    obs_t = torch.from_numpy(obs).unsqueeze(0).to(self.device)
                    action, _, _, lstm_state = self.policy.act(obs_t, lstm_state, deterministic=True)
                    obs, _, done, info = self.env.step(action.squeeze(0).cpu().numpy())
                    if done:
                        break
                if info.get("dist", 0) >= min_dist:
                    good.append(entry)
        primitive = [e for e in self.train_set if e.method == "primitive"]
        return good if good else (primitive or self.train_set[:5])

    # ── Curriculum ───────────────────────────────────────────────────────────

    def _sample_terrain(self, phase: float) -> TerrainEntry:
        primitive = [e for e in self.train_set if e.method == "primitive"]
        easy      = [e for e in self.train_set if e.method in ("primitive", "spline")]
        hard      = [e for e in self.train_set
                     if e.method in ("fbm_noise", "wfc", "random_walk")]

        if phase < 0.40:
            # Flat/gentle only — converge stable gait first
            pool = primitive or self.train_set
        elif phase < 0.65:
            pool = easy if self.rng.random() < 0.80 else self.train_set
        elif phase < 0.85:
            pool = self.train_set
        else:
            pool = hard if (self.rng.random() < 0.65 and hard) else self.train_set
        return self.rng.choice(pool)

    # ── Rollout collection ────────────────────────────────────────────────────

    def _set_velocity_curriculum(self, phase: float) -> None:
        """
        Velocity curriculum: start with fast (unconstrained) joints so the robot
        can discover walking, then gradually tighten to realistic 40°/s speed.

          phase 0.00–0.25: 20× MAX_JOINT_RATE (essentially unlimited, find a gait)
          phase 0.25–0.65: linear ramp 20× → 1× (slow down to realistic speed)
          phase 0.65–1.00: 1× MAX_JOINT_RATE (full realistic constraint)
        """
        if self.env._physics is None:
            return
        # Capped velocity curriculum: a MODEST early speed boost (4×) for gait
        # discovery, ramped to realistic 1× by mid-training.  A large boost
        # (e.g. 20×) lets PPO exploit unphysical flailing that never transfers
        # to realistic joint speed, so the cap is deliberately small.
        VEL_MAX = 4.0
        if phase < 0.20:
            scale = VEL_MAX
        elif phase < 0.50:
            t = (phase - 0.20) / 0.30   # 0 → 1
            scale = VEL_MAX * (1.0 - t) + 1.0 * t
        else:
            scale = 1.0
        self.env._physics.velocity_limit_scale = scale

    def _collect_rollouts(self, phase: float) -> dict:
        self.buffer.reset()
        self.policy.eval()

        entry      = self._sample_terrain(phase)
        obs        = self.env.reset(entry)
        # Apply velocity curriculum to current episode's physics
        self._set_velocity_curriculum(phase)
        lstm_state = self.policy.init_hidden(1)   # reset hidden at episode start

        ep_lens, ep_rews, ep_dists = [], [], []
        ep_succ = 0
        ep_len, ep_rew = 0, 0.0

        with torch.no_grad():
            for _ in range(N_STEPS_PER_ITER):
                obs_t = torch.from_numpy(obs).unsqueeze(0).to(self.device)

                # Store hidden state BEFORE the LSTM step (for buffer replay)
                h_np = lstm_state[0].squeeze(0).squeeze(0).cpu().numpy()
                c_np = lstm_state[1].squeeze(0).squeeze(0).cpu().numpy()

                action, log_prob, value, lstm_state = self.policy.act(obs_t, lstm_state)
                action_np   = action.squeeze(0).cpu().numpy()
                log_prob_np = log_prob.item()
                value_np    = value.item()

                next_obs, reward, done, info = self.env.step(action_np)
                self.buffer.add(obs, action_np, reward, float(done),
                                value_np, log_prob_np, h_np, c_np)

                ep_len += 1
                ep_rew += reward
                obs     = next_obs

                if done:
                    ep_lens.append(ep_len)
                    ep_rews.append(ep_rew)
                    ep_dists.append(info["dist"])
                    if info["success"]:
                        ep_succ += 1
                    ep_len, ep_rew = 0, 0.0

                    # New episode: new terrain + reset LSTM + re-apply velocity curriculum
                    entry      = self._sample_terrain(phase)
                    obs        = self.env.reset(entry)
                    self._set_velocity_curriculum(phase)
                    lstm_state = self.policy.init_hidden(1)

            # Bootstrap value at end of rollout
            obs_t  = torch.from_numpy(obs).unsqueeze(0).to(self.device)
            _, _, last_val, _ = self.policy.act(obs_t, lstm_state)
            self.buffer.compute_returns_and_advantages(last_val.item())

        return {
            "ep_len":       np.mean(ep_lens) if ep_lens else ep_len,
            "ep_rew":       np.mean(ep_rews) if ep_rews else ep_rew,
            "ep_dist":      np.mean(ep_dists) if ep_dists else 0.0,
            "success_rate": ep_succ / max(len(ep_lens), 1),
        }

    # ── PPO update ────────────────────────────────────────────────────────────

    def _ppo_update(self, phase: float) -> dict:
        self.policy.train()
        losses_pol, losses_val = [], []

        # Anneal exploration std: INIT_LOG_STD → FINAL_LOG_STD over training
        frac    = min(1.0, phase)
        log_std = INIT_LOG_STD + (FINAL_LOG_STD - INIT_LOG_STD) * frac
        self.policy.set_log_std(log_std)

        for _ in range(N_EPOCHS):
            for batch in self.buffer.get_batches(BATCH_SIZE):
                obs_b, act_b, adv_b, ret_b, old_lp_b, h_b, c_b = batch

                log_prob, entropy, value = self.policy.evaluate_actions(
                    obs_b, act_b, h_b, c_b)

                ratio       = (log_prob - old_lp_b).exp()
                surr1       = ratio * adv_b
                surr2       = ratio.clamp(1 - CLIP_EPS, 1 + CLIP_EPS) * adv_b
                policy_loss = -torch.min(surr1, surr2).mean()
                value_loss  = nn.functional.mse_loss(value, ret_b)
                loss        = policy_loss + VALUE_COEF * value_loss

                self.optimiser.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.policy.parameters(), MAX_GRAD_NORM)
                self.optimiser.step()

                losses_pol.append(policy_loss.item())
                losses_val.append(value_loss.item())

        return {
            "loss_pol": np.mean(losses_pol),
            "loss_val": np.mean(losses_val),
            "log_std":  log_std,
        }

    # ── Validation ────────────────────────────────────────────────────────────

    def _val_act(self, obs: np.ndarray, lstm_state: tuple,
                 n_candidates: int = 8) -> tuple:
        """
        Select best action by value head over N candidates (no physics simulation).
        Provides consistent, reproducible evaluation without pure determinism.
        """
        obs_t = torch.from_numpy(obs).unsqueeze(0).to(self.device)
        best_val   = -1e9
        best_action = None
        best_state  = lstm_state

        for _ in range(n_candidates):
            action, _, val, new_state = self.policy.act(obs_t, lstm_state, deterministic=False)
            if val.item() > best_val:
                best_val    = val.item()
                best_action = action
                best_state  = new_state

        # Also try deterministic
        det_action, _, det_val, det_state = self.policy.act(obs_t, lstm_state, deterministic=True)
        if det_val.item() > best_val:
            best_action = det_action
            best_state  = det_state

        return best_action.squeeze(0).cpu().numpy(), best_state

    def _validate(self, phase: float) -> float:
        """
        Validate using value-guided action selection and curriculum-matched terrains.
        """
        self.policy.eval()

        # Match val terrains to current curriculum phase
        if phase < 0.40:
            val_pool = [e for e in self.val_set if e.method == "primitive"]
            if not val_pool:
                val_pool = self.val_set[:4]
        elif phase < 0.65:
            easy = [e for e in self.val_set if e.method in ("primitive", "spline")]
            val_pool = easy if easy else self.val_set[:6]
        else:
            val_pool = self.val_set

        dists = []
        with torch.no_grad():
            for entry in val_pool[:8]:
                obs        = self.env.reset(entry)
                lstm_state = self.policy.init_hidden(1)
                done       = False
                info       = {}
                while not done:
                    action_np, lstm_state = self._val_act(obs, lstm_state)
                    obs, _, done, info = self.env.step(action_np)
                dists.append(info.get("dist", 0.0))
        return float(np.mean(dists))

    # ── Training loop ─────────────────────────────────────────────────────────

    def train(self) -> None:
        print(f"\n{'='*60}")
        print(f"PPO-LSTM training [{self.label}]  iters={self.n_iters}  device={self.device}")
        print(f"{'='*60}")
        t0 = time.time()

        for it in range(1, self.n_iters + 1):
            phase = it / self.n_iters

            ep_stats   = self._collect_rollouts(phase)
            loss_stats = self._ppo_update(phase)

            if it % LOG_INTERVAL == 0:
                vel_scale = getattr(self.env._physics, 'velocity_limit_scale', 1.0) if self.env._physics else 1.0
                print(f"  iter {it:4d}/{self.n_iters} | "
                      f"dist={ep_stats['ep_dist']:5.1f}  rew={ep_stats['ep_rew']:6.1f}  "
                      f"succ={ep_stats['success_rate']:.2f} | "
                      f"L_pol={loss_stats['loss_pol']:.4f}  "
                      f"L_val={loss_stats['loss_val']:.4f}  "
                      f"log_std={loss_stats['log_std']:.3f}  vel×{vel_scale:.1f}  "
                      f"t={time.time()-t0:.0f}s")

            if it % VAL_INTERVAL == 0:
                val_dist = self._validate(phase)
                print(f"  → VAL dist={val_dist:.2f}")
                if val_dist > self.best_val_dist:
                    self.best_val_dist = val_dist
                    best_path = self.model_dir / f"ppo_best_{self.label}.pt"
                    save_policy(self.policy, str(best_path))
                    print(f"  ✓ best saved → {best_path}")

        final_path = self.model_dir / f"ppo_final_{self.label}.pt"
        save_policy(self.policy, str(final_path))
        print(f"\nFinal model → {final_path}")
        print(f"Best val dist = {self.best_val_dist:.2f}")
