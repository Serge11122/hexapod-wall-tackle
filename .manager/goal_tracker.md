# Goal Tracker — Cycle 336

Updated: 2026-04-04 22:10 UTC (tconv cycle 336)

## Conviction 1: Trade Entry/Exit Common — COMPLETE (c165)

Corrected Sharpe 2.799. All active versions migrated.

## Conviction 2: V5 Backbone Ranking — CAPPED PROVE-OUT (50K steps)

### Status: CRASHED AT STEP ~10000 — MUST RESUME IMMEDIATELY

**Crash detected:** Process died silently between step 8200 (last log line) and step 10000 (checkpoint). No error in log. GPU at 0%. Checkpoint at step 10000 is intact (verified: torch.load succeeds, global_step=10000, w_rank=0.3, rank_loss_type=listmle). Per crash recovery rules: resume immediately from checkpoint, do not investigate unless same step range crashes twice.

**Training was healthy before crash:** Loss declining (2.24 at step 6050 to 1.26 at step 8200), GPU util 80-82%, pace 0.27s/step, Val Sharpe 0.6088 at step 8000 (*IMPROVED*).

### Resume Command (IMMEDIATE)

```bash
cd /home/ubuntu/workspace/RLQuest && nohup firstrate_learning/.venv/bin/python -u -m firstrate_learning.v5_wrank.train --resume run_20260404_181001_proveout --w-rank 0.3 --rank-loss-type listmle --total-steps 50000 > firstrate_learning/v5_wrank/prove.log 2>&1 &
```

### Checkpoint State

- **Run dir:** run_20260404_181001_proveout
- **Checkpoint:** latest_checkpoint.pt at step 10000 (verified)
- **Config:** w_rank=0.3, rank_loss_type=listmle, learning_rate=3e-4, frozen backbone
- **Total steps:** 50000 (capped)
- **Wall clock estimate:** 40K remaining steps x 0.27s = ~3.0 hr
- **Best val so far:** VL=0.6088, CR=0.0046 at step 8000

### Post-Resume Verification

1. Check GPU >0% within 2 min: `nvidia-smi`
2. Check log advancing from step 10000+: `tail -5 firstrate_learning/v5_wrank/prove.log`
3. Verify run_meta.json: w_rank=0.3, rank_loss_type=listmle

### w_rank Experiment Tracker — COMPLETE (10 experiments)

| # | w_rank | Loss Type | Backbone | Val CR | Test CR | Test vs Baseline | Best Step | Status |
|---|--------|-----------|----------|--------|---------|------------------|-----------|--------|
| 1 | 0.2 | ListNet | Frozen | 0.0688 (4.4x) | 0.00953 (0.61x) | WORSE | 6000 | DONE |
| 2 | 0.1 | ListNet | Frozen | -0.0169 (NEG) | N/A (killed) | KILLED | — | DONE |
| 3 | 0.05 | ListNet | Frozen | N/A | N/A | KILLED (stale) | — | ABANDONED |
| 4 | 0.2 | ListMLE | Frozen | 0.0548 (3.5x) | 0.01295 (0.83x) | BETTER | 6000 | DONE |
| 5 | 0.3 | ListMLE | Frozen | 0.0612 (3.9x) | 0.01534 (0.98x) | NEAR PARITY | 10000 | **WINNER** |
| 6 | 0.4 | ListMLE | Frozen | VL declining | N/A (killed) | FAILED | 2000 | FAILED |
| 7 | 0.35 | ListMLE | Frozen | 0.0433 | 0.0097 (0.62x) | WORSE | 6000 | DONE |
| 8 | 0.3 | ApproxNDCG | Frozen | 0.0590 (3.8x) | 0.01356 (0.87x) | WORSE | 2000 | DONE |
| 9 | 0.3 | ListMLE | Proj-only | 0.0776 (5.0x) | 0.01492 (0.96x) | MIXED | 2000 | DONE |
| 10 | 0.0 | None | Proj-only | 0.0769 (4.9x) | N/A (killed) | KILLED | 2000 | KILLED |

### After Capped Prove-Out Completes

1. Check training_results.json — compare Test CR to smoke's 0.01534 (0.98x baseline)
2. Tag if successful: create v5_wrank_tag from v5_wrank
3. **PIVOT to V13 backbone fine-tuning** — frozen backbone ceiling proven, fine-tuning is the attack on 144.71%

### Disk Status
- 75% (healthy)

### Conviction Audit (Cycle 336)
- Cache invalidation: CLEAN
- Step-based training: CLEAN
- Tagged model protection: CLEAN
- Trade entry/exit: COMPLETE
- Disk: 75% (no cleanup needed)
- Time efficiency: **GPU IDLE — CRASH RECOVERY — must resume immediately from step 10000**
- Prove-out resumable: CHECKPOINT EXISTS at step 10000, config verified, resume ready
- Resume config validation: CLEAN (w_rank=0.3, rank_loss_type=listmle confirmed in checkpoint)
- V13 experimentation: ALL 36 PORTFOLIO EXPERIMENTS EXHAUSTED. After V5 prove-out: pivot to V13 fine-tuning.
