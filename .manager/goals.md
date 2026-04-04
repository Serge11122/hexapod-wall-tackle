# RLQuest Project Goals

## Core Thesis

A perfect foresight model proves profitable trades exist in every market regime (170% return in 50 days, 9.16 Sharpe). Modern transformer architectures trained on large raw data can learn subtle patterns — slight volume changes, implied volatility shifts, put-call ratio anomalies — that predict large moves. The goal is to close the gap between current model performance and the foresight upper bound.

## Architecture

- **Backbone (FirstRate Learning)** — per-stock feature extractor. Transformer architecture that processes raw options chain + price data as token sequences. No hand-crafted features — lets the model learn directly from moneyness, DTE, bid/ask, volume, open interest. Predicts: big move probability, direction, return quantiles, return magnitude.

- **Portfolio Model (downstream)** — uses the backbone as a frozen feature extractor to learn trading signals across all stocks. Designs buy/sell signals for variable-size universes (e.g., train on 2K stocks, inference on 5K). Handles cross-sectional ranking that the backbone cannot.

## Goals

- Build backbone transformer that extracts strong per-stock signals from raw options data
- Build portfolio model that translates backbone signals into profitable cross-sectional portfolios
- Iterate on training recipe: loss weights, learning rate schedule, data augmentation
- Evaluate on standard metrics (P@5%, captured return, rank correlation, direction accuracy)
- Progress toward foresight benchmark quality of stock selection
