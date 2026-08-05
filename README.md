# 👁️ Argus — Advanced Market Forecast & AI Analysis

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Commercial License Available](https://img.shields.io/badge/Commercial%20License-Available-green.svg)](#license--commercial-licensing)

Argus is an advanced Python desktop application for **quantitative price forecasting and AI-driven analysis** of cryptocurrency assets. It combines Google Research's **TimesFM 2.5** foundation model for temporal prediction, a cooperative **Multi-Agent LLM pipeline** for qualitative analysis and debate, and a **VectorBT instant backtester** to constrain AI decisions with real mathematical evidence.

On top of the analysis engine, Argus features a full **Portfolio Manager** module integrated with [CCXT](https://github.com/ccxt/ccxt) for generating and executing orders on derivatives exchanges (e.g., BingX), with an institutional-grade Money Management framework and a fully autonomous **Auto-Trading Scheduler**.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Deep-Dives](#module-deep-dives)
   - [BTC Pattern Matching (KNN-DTW)](#1-btc-pattern-matching-knn-dtw)
   - [TimesFM Temporal Forecast](#2-timesfm-temporal-forecast)
   - [Multi-Agent AI Analysis](#3-multi-agent-ai-analysis-pipeline)
   - [Ensemble Engine](#4-ensemble-engine--mathematical-formulas)
   - [Instant Backtest (VectorBT)](#5-instant-backtest-vectorbt)
   - [Portfolio Manager & CCXT](#6-portfolio-manager--ccxt-integration)
   - [Pre-Flight Checker](#7-pre-flight-checker-slippage-guard--flash-ob)
   - [Auto-Trading Workflow](#8-auto-trading-workflow-5-steps)
3. [Project Structure](#project-structure)
4. [GUI Panels](#gui-panels)
5. [Configuration Reference](#configuration-reference)
6. [Installation & Setup](#installation--setup)
7. [Supported Exchanges](#supported-exchanges)
8. [Requirements](#requirements)
9. [License & Commercial Licensing](#license--commercial-licensing)
10. [Disclaimer](#disclaimer)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  ARGUS DATA PIPELINE                    │
│                                                         │
│  Market Data (CoinGecko / yfinance / BingX CCXT)        │
│       │                                                 │
│       ▼                                                 │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ KNN-DTW BTC  │  │ TimesFM  │  │  Multi-Agent LLM │  │
│  │ Pattern Match│  │ Forecast │  │  Pipeline (AI)   │  │
│  └──────┬───────┘  └────┬─────┘  └────────┬─────────┘  │
│       │               │                   │             │
│       └───────────────┴───────────────────┘             │
│                       │                                 │
│               ┌───────▼────────┐                        │
│               │ Ensemble Engine│  ← weighted avg        │
│               │ (w_tfm, w_pm,  │     + penalties        │
│               │  w_ai dynamic) │                        │
│               └───────┬────────┘                        │
│                       │                                 │
│           ┌───────────▼───────────┐                     │
│           │  Portfolio Manager    │                     │
│           │  · Sizing (Margin/    │                     │
│           │    Risk-Based)        │                     │
│           │  · ATR SL/TP fallback │                     │
│           │  · Pre-Flight Check   │                     │
│           │  · CCXT Order Exec    │                     │
│           └───────────────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

**Core Design Principle — Stateless Data Architecture:**  
Analysis modules (Pattern Matching, TimesFM, AI) do **not** fetch data directly from external providers during inference; this prevents API rate-limit blocks during live trading cycles. The Markets panel is responsible for downloading and locally caching up to 1 year of 15-minute BTC candles. All analysis modules read from this local cache. If the cache is older than 2 hours, agents request a manual refresh (automatically triggered during Auto-Trading cycles).

---

## Module Deep-Dives

### 1. BTC Pattern Matching (KNN-DTW)

**File:** [`core/btc_pattern_matcher.py`](core/btc_pattern_matcher.py)

A quantitative intraday research module focused **exclusively on BTC**. It finds historical price action patterns that are most similar to the current 2-hour window and extrapolates the likely future move.

#### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `query_window` | `8` | Recent candles used as query (2 hours @ 15m) |
| `projection_window` | `8` | Future candles to project (2 hours @ 15m) |
| `interval` | `15m` | Always fixed at 15-minute candles |
| `history_years` | `1` | Years of historical BTC data to search |
| `n_neighbors` | `5` | K nearest neighbors to retrieve |

#### Algorithm

**Step 1 — Log Returns:**  
Raw close prices are converted to log returns to normalize scale:

$$r_t = \ln\!\left(\frac{C_t}{C_{t-1}}\right)$$

**Step 2 — Z-Score Normalization (StandardScaler):**  
Each window of log returns is normalized to zero mean and unit variance so that the distance metric is scale-invariant:

$$\hat{r}_i = \frac{r_i - \mu}{\sigma}$$

**Step 3 — KNN with Euclidean Distance:**  
The normalized current window $\mathbf{q}$ is compared against all historical windows $\mathbf{X}$ using Euclidean distance (a numerically stable proxy for DTW on fixed-length sequences):

$$d(\mathbf{q}, \mathbf{x}_j) = \left\|\mathbf{q} - \mathbf{x}_j\right\|_2$$

The $k$ nearest historical windows are selected.

**Step 4 — Future Return Projection:**  
For each matched historical window $j$, the cumulative future log return over the next `projection_window` candles is computed and converted to percentage:

$$\text{FutureReturn}_j = \left(\exp\!\left(\sum_{i=0}^{W_p-1} r_{j+W_q+i}\right) - 1\right) \times 100\%$$

The **expected move** is the mean across all $k$ matches:

$$\Delta P_{\text{pm}} = \frac{1}{k} \sum_{j=1}^{k} \text{FutureReturn}_j$$

**Step 5 — Confidence Score:**  
Three components are combined into a final confidence score:

$$\text{SignConsistency} = \frac{\max(N_+,\ N_-)}{k} \times 100$$

$$\text{BaseConfidence} = 0.6 \times \text{SignConsistency} + 0.4 \times \frac{100}{1 + \bar{d}}$$

where $\bar{d}$ is the mean Euclidean distance across $k$ neighbors.

$$\text{VolPenalty} = \frac{1}{1 + 0.5 \times \sigma_{\text{FutureReturns}}}$$

$$\text{Confidence}_{\text{pm}} = \text{BaseConfidence} \times \text{VolPenalty}$$

A high standard deviation of future returns across matches indicates diverging historical outcomes, and the confidence is penalized accordingly.

---

### 2. TimesFM Temporal Forecast

**File:** [`core/forecaster.py`](core/forecaster.py)

Argus integrates **TimesFM 2.5 (200M parameter PyTorch model)** by Google Research — a foundation time series model pre-trained on large-scale real-world datasets.

#### Configuration
| Parameter | Description | Default |
|-----------|-------------|---------|
| Checkpoint | HuggingFace model ID | `google/timesfm-2.5-200m-pytorch` |
| Backend | `cpu` or `gpu` | `cpu` |
| Horizon | Forecast steps | `8` candles (2 hours @ 15m) |
| Context window | Minimum historical points | `96` candles |
| Timeframe | OHLCV interval | `15m` (intraday) |

#### How it works
1. The model is **lazily loaded** from HuggingFace on first use (downloaded once, then cached).
2. A minimum of **96 historical 15-minute candles** (~24 hours) are fed as context.
3. TimesFM outputs 8 future candle predictions (`horizon=8`).
4. The forecasted price at horizon `h` is compared to the last known close to yield a **percentage change estimate**:

$$\Delta P_{\text{tfm}} = \frac{P_{\text{forecast},h} - P_{\text{last}}}{P_{\text{last}}} \times 100$$

5. A directional signal (`BUY` / `HOLD` / `SELL`) is emitted if $|\Delta P_{\text{tfm}}|$ exceeds the configurable signal threshold.

#### ATR-Based Confidence Bound
TimesFM also computes a **14-period ATR on the last 15 historical bars** to express how volatile the context is. This ATR value is reported as a SL/TP boundary hint and passed to the Ensemble engine as a volatility reference:

$$\text{TR}_t = \max\bigl(H_t - L_t,\ |H_t - C_{t-1}|,\ |L_t - C_{t-1}|\bigr)$$

$$\text{ATR}_{14} = \frac{1}{14}\sum_{t=T-13}^{T} \text{TR}_t$$

---

### 3. Multi-Agent AI Analysis Pipeline

**File:** [`core/ai_analyst.py`](core/ai_analyst.py)

A cooperative **6-agent LLM pipeline** that analyses each candidate asset independently, culminating in a structured investment decision.

#### Supported LLM Providers
| Provider | Endpoint | Key Models |
|----------|----------|------------|
| **OpenRouter** | `https://openrouter.ai/api/v1` | Claude 3.5 Sonnet, GPT-4o, Gemini Flash, Llama 3 free |
| **Claude (Direct)** | `https://api.anthropic.com/v1` | claude-3-5-sonnet, claude-3-opus |
| **OpenAI (Direct)** | `https://api.openai.com/v1` | gpt-4o, gpt-4o-mini, gpt-4-turbo |
| **Ollama (Local)** | `http://localhost:11434/v1` | llama3.1, mistral, gemma2 |

#### Agent Pipeline

```
Asset Data
    │
    ▼
① Market Analyst
   · RSI, Std Dev on 15m candles
   · Bid/Ask Order Book imbalance ratio
   · TimesFM forecast trend
    │
    ▼
② News Analyst
   · Scrapes Investing.com (primary)
   · Finnhub / Yahoo Finance (fallback)
   · Filters last 1 hour only (max predictive relevance)
   · Fallback: last 3 historical headlines
    │
    ▼
③ Fundamentals Analyst
   · On-chain metrics (crypto)
   · Network fundamentals (hash rate, active addresses, etc.)
   · CoinGecko market data (market cap, supply, FDV)
    │
    ▼
④ Bull Researcher  ←→  ⑤ Bear Researcher
   · Structured debate (1–5 configurable rounds)
   · Each agent receives all prior analyses
   · Argues directly against the opponent's last round
    │
    ▼
⑥ Portfolio Manager Agent
   · Receives all reports + debate transcript + backtest results
   · Emits: Signal (BUY/SELL/HOLD), 1d/3d price targets,
     Stop Loss, Take Profit, Risk Factor, Confidence (0–100)
```

#### AI-Derived Expected Move

The Portfolio Manager Agent outputs a structured JSON that includes a 1-day price target (`target_price_1d`) and confidence. From this:

$$\Delta P_{\text{ai}} = \frac{\text{target\_price\_1d} - P_{\text{current}}}{P_{\text{current}}} \times 100$$

This percentage is used as the **AI module's contribution** to the Ensemble.

---

### 4. Ensemble Engine — Mathematical Formulas

**File:** [`core/portfolio_manager.py`](core/portfolio_manager.py) — `calculate_sizing()` method

The Ensemble Engine is the single source of truth that fuses the three independent forecasts (TimesFM, Pattern Matching, AI) into one **Expected Return** and a final trading signal.

#### Base Weights (User-Configurable)
| Module | Default Weight | Setting Key |
|--------|---------------|-------------|
| Pattern Matching | `0.35` | `ensemble_w_pm` |
| TimesFM | `0.40` | `ensemble_w_tfm` |
| AI Analyst | `0.25` | `ensemble_w_ai` |

> **Note on Auto Trading:** You can disable the Advanced Analysis module in Auto Trading via the setting `enable_ai_auto_trade`. If disabled, the AI Analyst weight is distributed equally between Pattern Matching and TimesFM, and the AI module is bypassed to speed up execution and reduce API costs.

#### Dynamic Weight Adjustment (Confidence-Based)

Each weight is dynamically adjusted at runtime based on the reported confidence of each module. This ensures that a low-confidence module contributes less to the final signal, and a high-confidence module contributes more:

```
If confidence_X ≤ 33%:  w_X  -= 0.05 ;  w_Y += 0.025 ;  w_Z += 0.025
If confidence_X ≥ 66%:  w_X  += 0.05 ;  w_Y -= 0.025 ;  w_Z -= 0.025
```

Applied independently for each of the three modules (pm, tfm, ai). Weights are then floored at 0 and **normalized** to always sum to 1.0:

$$w_i' = \max(0,\ w_i + \Delta w_i)$$

$$w_i^{\text{norm}} = \frac{w_i'}{\sum_j w_j'}$$

#### Weighted Expected Return

$$\boxed{\Delta P_{\text{ensemble}} = w_{\text{tfm}}^{\text{norm}} \cdot \Delta P_{\text{tfm}} + w_{\text{pm}}^{\text{norm}} \cdot \Delta P_{\text{pm}} + w_{\text{ai}}^{\text{norm}} \cdot \Delta P_{\text{ai}}}$$

#### Signal Generation Rules

Signal is only emitted if **at least 2 out of 3 modules agree** on direction AND the expected return clears the configurable minimum threshold:

| Condition | Signal |
|-----------|--------|
| $N_+ \geq 2$ AND $\Delta P_{\text{ensemble}} > \theta_{\min}$ | **BUY (LONG)** |
| $N_- \geq 2$ AND $\Delta P_{\text{ensemble}} < -\theta_{\min}$ | **SELL (SHORT)** |
| Otherwise | **HOLD / NO TRADE** |

Where $\theta_{\min}$ is `ensemble_min_return_pct` (default: `0.30%`).

#### Size Multiplier and Penalties

The base `size_multiplier` starts at `1.0` if a signal is emitted, otherwise `0.0`.

| Condition | Adjustment |
|-----------|------------|
| Partial alignment (only 2/3 agree) | `size_multiplier × 0.60` (−40%) |
| BUY and `funding_rate > 0.05%` (overheated long) | `size_multiplier × 0.40` (−60%) |
| BUY and `Fear & Greed > 85` (extreme greed) | `size_multiplier × 0.40` (−60%) |
| SELL and `funding_rate < −0.02%` (short squeeze risk) | Signal cancelled → HOLD |

> **Sizing Display in UI**: The final UI-displayed sizing already incorporates all discordance filters and penalty multipliers. A `0%` size means NO TRADE even if a directional signal exists.

---

### 5. Instant Backtest (VectorBT)

**File:** [`core/ai_analyst.py`](core/ai_analyst.py)

Before the Portfolio Manager Agent makes its final decision, an **instant historical backtest** is run using [VectorBT](https://vectorbt.dev/) on 6 months of daily data (via `yfinance`).

#### Backtest Metrics Produced
| Metric | Description |
|--------|-------------|
| Strategy Return | Total % return of the signal-based strategy |
| Buy & Hold Return | Passive benchmark return |
| Sharpe Ratio | Risk-adjusted return (annualised) |
| Max Drawdown | Largest peak-to-trough decline |
| Trade Count | Number of trades executed |

The backtest results are passed directly into the Portfolio Manager Agent's prompt, forcing the LLM to ground its decision in historical statistical evidence rather than purely qualitative analysis.

#### Dynamic SL/TP in Backtest (ATR 15m)

Backtest simulations use **ATR-based dynamic SL/TP levels** aligned with real intraday scalping operations:

$$\text{SL}_{\text{fallback}} = P_{\text{current}} \times (1 - \text{ATR\%} \times k)$$
$$\text{TP}_{\text{fallback}} = P_{\text{current}} \times (1 + \text{ATR\%} \times 2k)$$

Where $k$ is a configurable multiplier (default `2.0` for live SL, `4.0` for live TP) and `ATR%` is the 14-period ATR expressed as a fraction of the current price.

---

### 6. Portfolio Manager & CCXT Integration

**File:** [`core/portfolio_manager.py`](core/portfolio_manager.py)

Translates Ensemble signals into real exchange orders with institutional-grade money management.

#### Sizing Modes

**Mode A — Margin Percentage Sizing (`sizing_mode = "margin_pct"`):**  
Each position consumes a fixed percentage of investable capital:

$$\text{MarginAllocated} = \text{InvestableCapital} \times \frac{1}{\text{MaxOpenPositions}} \times \text{ScaleFactor} \times \text{SizeMultiplier}$$

**Mode B — Risk-Based Sizing (`sizing_mode = "risk_pct"`):**  
Position size is dynamically calculated so that if the stop-loss is hit, the loss is exactly the configured risk percentage of total capital:

$$\text{NominalSize} = \frac{\text{TotalCapital} \times \text{RiskPerTrade\%}}{\text{SL Distance\%}}$$

$$\text{MarginRequired} = \frac{\text{NominalSize} \times \text{ScaleFactor} \times \text{SizeMultiplier}}{\text{Leverage}}$$

$$\text{Margin} = \min(\text{MarginRequired},\ \text{InvestableCapital} \times \text{MaxPositionPercent})$$

> Example: With capital=$10,000, risk=1.5%, SL=2% away, leverage=10x → NominalSize = $7,500 → Margin = $750

#### Dynamic Leverage Calculation

Leverage is calculated dynamically but capped at `maxLeverage`. The safe leverage is determined by ensuring the stop-loss distance absorbs at least an 80% portfolio move before liquidation:

$$\text{SafeLeverage} = \left\lfloor \frac{0.80}{\text{SL Distance\%}} \right\rfloor$$

$$\text{Leverage} = \min(\text{maxLeverage},\ \max(1,\ \text{SafeLeverage}))$$

#### ATR Fallback for Missing SL/TP

If the AI analyst does not provide SL/TP values, the system falls back to a **15m ATR-based calculation** using the last 30 candles from the exchange (or from the local historical cache):

$$\text{ATR}_{14}^{15m} = \frac{1}{14}\sum_{t=T-13}^{T}\max(H_t - L_t,\ |H_t - C_{t-1}|,\ |L_t - C_{t-1}|)$$

$$\text{ATR\%} = \frac{\text{ATR}_{14}^{15m}}{P_{\text{current}}} \times 2.0$$

$$\text{SL (LONG)} = P_{\text{current}} \times (1 - \text{ATR\%})$$
$$\text{TP (LONG)} = P_{\text{current}} \times (1 + 2 \times \text{ATR\%})$$

#### Additional Risk Management Features

| Feature | Description |
|---------|-------------|
| **Minimum Expected Return (Anti-Flat)** | Ensemble signals below `ensemble_min_return_pct` (default 0.30%) are discarded → NO TRADE |
| **DCA / Multi-Entry** | New entries on same asset allowed only if price has moved ≥ `dca_distance_pct` from avg entry price |
| **Anti-Spam (no duplicate orders)** | If same-direction position exists and multi-entry is disabled, order is blocked |
| **Stop and Reverse** | If a signal is opposite to an existing position, the existing position is closed first before entering the new one |
| **Hedge-in-Loss Guard** | With Stop-and-Reverse disabled, opposite-direction positions in loss are kept open (no lock-in); only profitable opposite positions are auto-closed |
| **Max Capital Usage** | `maxCapitalUsagePercent` caps total capital deployed across all positions |
| **Proportional Scaling** | If total needed margin exceeds available capital, all positions are scaled proportionally |
| **Max Open Positions** | Only **Futures** positions count toward the `maxOpenPositions` limit (Spot holdings are excluded) |
| **ROI Capping** | User-configurable `maxStopLossROI` and `maxTakeProfitROI` cap the leveraged risk/reward expressed as ROI% |
| **Confidence Scaling** | `scale = 0.5 + 0.5 × ((confidence − minConf) / (100 − minConf))` smoothly scales margin allocation from 50% to 100% of target based on AI confidence |

---

### 7. Pre-Flight Checker (Slippage Guard & Flash OB)

**File:** [`core/pre_flight_checker.py`](core/pre_flight_checker.py)

An instant real-time validator that runs **immediately before** the order is submitted to the exchange, mitigating LLM inference latency risk.

#### Check 1 — Drift Slippage Guard

Measures how much the price has moved toward the Take Profit since the analysis was initiated:

$$\text{Drift}_{\text{LONG}} = \frac{P_{\text{live}} - P_{t_0}}{|P_{\text{TP}} - P_{t_0}|}$$

$$\text{Drift}_{\text{SHORT}} = \frac{P_{t_0} - P_{\text{live}}}{|P_{t_0} - P_{\text{TP}}|}$$

If `Drift > drift_threshold` (default `25%` of the total TP distance), the order is **rejected** — the trade opportunity has already partially played out and the risk/reward has deteriorated.

#### Check 2 — Flash Order Book Imbalance

Fetches the live order book (top 20 bid/ask levels) and calculates volume pressure:

$$\text{AskPressure} = \frac{\sum \text{Ask Volumes}}{\sum \text{Bid Volumes} + \sum \text{Ask Volumes}}$$

$$\text{BidPressure} = \frac{\sum \text{Bid Volumes}}{\sum \text{Bid Volumes} + \sum \text{Ask Volumes}}$$

For a **LONG** order: if `AskPressure > imbalance_threshold` (default `60%`), the order is rejected — excessive sell-side pressure indicates the market is likely to move against the LONG trade.

For a **SHORT** order: if `BidPressure > imbalance_threshold`, the order is rejected.

#### Check 3 — SL/TP Realignment

If both checks pass, the checker **recalculates SL and TP relative to the live price** (not the stale analysis price), preserving the original percentage distances:

$$\text{SL\%} = \frac{|P_{t_0} - \text{SL}_{t_0}|}{P_{t_0}}$$

$$\text{SL}_{\text{live (LONG)}} = P_{\text{live}} \times (1 - \text{SL\%})$$

$$\text{TP}_{\text{live (LONG)}} = P_{\text{live}} \times (1 + \text{TP\%})$$

This ensures orders are always placed relative to the current market price, not a potentially stale price.

---

### 8. Auto-Trading Workflow (5 Steps)

**File:** [`gui/auto_trading_panel.py`](gui/auto_trading_panel.py) | **Core:** [`core/data_manager.py`](core/data_manager.py), [`core/portfolio_manager.py`](core/portfolio_manager.py)

The Auto-Trading module executes a complete, autonomous 5-step workflow at a configurable interval (triggered 30 seconds after the close of every 15-minute candle). The analysis modules run in the same order as in the application navigation: **Market Data → Pattern Matching → TimesFM → AI Advanced Analysis**.

---

#### Step 1 — Market Data Update

1. **Asset retrieval**: Loads the configured crypto assets (BTC-focused for intraday trading).
2. **Exchange price sync**: Fetches real-time prices from the exchange (BingX) via CCXT `fetch_tickers()`. Falls back to CoinGecko or Yahoo Finance if unavailable.
3. **BTC history download**: Downloads up to 365 days of 15-minute BTC OHLCV candles from the exchange. Falls back to yfinance (60 days) if the exchange is unavailable.
4. **Market panel sync**: Updates the Markets panel cache with the fresh data.

---

#### Step 2 — BTC Pattern Matching (KNN-DTW)

Runs the KNN-DTW pattern matching engine on the freshly downloaded BTC 15m history:

1. **Analysis**: Identifies the `k=5` most similar historical 2-hour windows to the current window using Euclidean distance on normalized log returns.
2. **Expected move**: Computes the mean projected future return across all matched windows.
3. **Confidence**: Scores sign consistency and proximity of historical matches.
4. **UI update**: Inserts a new row in the Pattern Matching panel with move %, confidence, and target price. Saves to persistent history.

---

#### Step 3 — TimesFM Time-Series Analysis

Runs the Google TimesFM 2.5 foundation model on the BTC 15m history:

1. **Model load**: Lazily loads TimesFM from HuggingFace cache (downloaded only once, then cached locally).
2. **Inference**: Feeds the last 96+ candles as context and forecasts the next 8 candles (`horizon=8`, 2 hours ahead).
3. **Signal emission**: Computes `change_pct_1d` and emits `BUY / HOLD / SELL` based on the configurable percentage threshold.
4. **Result storage**: Saves forecast to `data/forecast_log.csv` and updates the Time-Series Analysis panel.

---

#### Step 4 — AI Advanced Analysis & Order Execution (Macro Asset: BTC)

Determines the macro market direction via BTC/ETH dominance analysis, then runs the full AI pipeline on BTC.

**Macro BTC/ETH Filter:**  
Checks if `change_pct_1d` for BTC and ETH have opposite signs (discordance). If discordant, runs the ETH/BTC dominance ratio analysis:

$$\text{Ratio}_t = \frac{P_{\text{ETH},t}}{P_{\text{BTC},t}}, \quad \text{MA14} = \frac{1}{14}\sum_{t=T-13}^{T}\text{Ratio}_t$$

| Condition | Interpretation | Macro Candidate |
|-----------|---------------|-----------------|  
| $\text{Ratio}_T < \text{MA14}$ | BTC drains liquidity from ETH | **BTC** |
| $\text{Ratio}_T \geq \text{MA14}$ | ETH outperforms BTC | **ETH** |

A `macro_cooldown` of 3 runs is set after any determination to prevent redundant signals.

**AI Analysis & Execution:**
1. **Pre-trade management**: Closes any profitable existing BTC/ETH positions (unrealized PnL > 0). Loss positions are kept open.
2. **Full AI pipeline**: Runs the complete 6-agent LLM pipeline, receiving Pattern Matching and TimesFM results as context for the decision.
3. **Order execution**: Portfolio Manager places the order via CCXT. If AI confidence is below threshold, a 3-run cooldown is set for that asset.

---

#### Step 5 — AI Advanced Analysis & Order Execution (Normal Asset)

**Asset Selection:**  
Selects the highest-conviction non-macro asset:
- BTC and ETH are always excluded (reserved for macro slot).
- Excludes assets in the user-defined exclusion list, in low-confidence cooldown, or already held (if `ignore_portfolio = False`).
- Falls back to portfolio assets for potential DCA reinforcement if no new eligible asset exists.

**AI Analysis & Execution:**  
Runs the full AI pipeline on the selected normal asset. If the primary candidate is rejected (low confidence or failed analysis), the system **cascades** through the next-best candidates until a successful order or the list is exhausted.

---

## Project Structure

```
Argus/
├── main.py                       # Application entry point (maximized window)
├── requirements.txt              # Python dependencies
├── .env                          # Local environment variables (not committed)
├── config/
│   └── settings.json             # Global persistent configuration file
├── core/
│   ├── __init__.py
│   ├── ai_analyst.py             # Multi-agent LLM pipeline + VectorBT backtest
│   ├── ai_analysis_store.py      # Persistent store for AI analysis results
│   ├── analyzer.py               # Signal and result analysis utilities
│   ├── btc_pattern_matcher.py    # KNN-DTW BTC pattern matching engine
│   ├── data_fetcher.py           # Market data via CoinGecko / yfinance / CCXT
│   ├── data_manager.py           # JSON/CSV filesystem management
│   ├── forecaster.py             # TimesFM 2.5 wrapper (lazy loading)
│   ├── market_enrichment.py      # Real-time market context (FNG, funding rates)
│   ├── portfolio_manager.py      # Ensemble engine, CCXT routing, sizing logic
│   └── pre_flight_checker.py     # Real-time pre-order validation
├── gui/
│   ├── __init__.py
│   ├── app.py                    # CustomTkinter main application frame
│   ├── ai_analysis_panel.py      # AI analysis UI, provider settings, debate viewer
│   ├── auto_trading_panel.py     # Auto-trading scheduler UI
│   ├── config_panel.py           # TimesFM and general configuration panel
│   ├── markets_panel.py          # Real-time market tables and data sync
│   ├── pattern_matching_panel.py # BTC KNN-DTW pattern matching panel
│   ├── portfolio_panel.py        # Portfolio positions, orders, P&L panel
│   ├── results_table.py          # Quantitative forecast results table
│   └── utils.py                  # Shared UI utilities and helpers
└── data/
    ├── portfolio_audit.json      # Full order execution history (audit trail)
    ├── forecast_history.csv      # Timestamped forecast results log
    ├── historical/               # Locally cached OHLCV data (per asset)
    └── market_lists/             # JSON asset list cache files
```

---

## GUI Panels

| Panel | Description |
|-------|-------------|
| **Auto Trading** | Configures and controls the automated 5-step trading workflow. Run log shows each run's start time, duration, result, and detailed step-by-step output. |
| **Portfolio** | Displays current Spot and Futures positions via CCXT. Shows leverage, entry price, current price, unrealized P&L, SL/TP. Allows manual order generation and execution. |
| **Markets** | Real-time price table for top crypto assets. Triggers BTC history download and data sync. Displays current prices, % changes, and ATR values. |
| **Pattern Matching** | Runs the BTC KNN-DTW analysis. Displays match count, confidence score, expected move %, and historical chart overlay. |
| **Time-Series Analysis** | Runs TimesFM 2.5 batch inference on the locally cached BTC history. Displays forecasted price, directional signal, and ATR-based confidence bounds. |
| **Advanced Analysis (AI)** | Runs the full 6-agent LLM pipeline on a selected asset. Configures LLM provider, model, API key, debate rounds. Displays each agent's report and the final structured JSON decision. |
| **Config** | Global settings: TimesFM parameters, Ensemble weights, minimum return threshold, Portfolio Manager settings (API keys, exchange, sizing mode, risk %, leverage limits, pre-flight thresholds). |

---

## Configuration Reference

All settings are stored in `config/settings.json`. Key parameters:

### TimesFM & Forecasting
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `hf_token` | string | `""` | HuggingFace API token for private model access |
| `backend` | string | `"cpu"` | TimesFM backend: `"cpu"` or `"gpu"` |
| `signal_threshold_pct` | float | `0.5` | Minimum % change to emit BUY/SELL (vs HOLD) |

### Ensemble Engine
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ensemble_w_tfm` | float | `0.40` | Base weight for TimesFM in the ensemble |
| `ensemble_w_pm` | float | `0.35` | Base weight for Pattern Matching in the ensemble |
| `ensemble_w_ai` | float | `0.25` | Base weight for AI Analyst in the ensemble |
| `ensemble_min_return_pct` | float | `0.30` | Minimum expected return % to emit a signal |

### Portfolio Manager
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `portfolio_manager.exchange_id` | string | `"bingx"` | CCXT exchange identifier |
| `portfolio_manager.api_key` | string | `""` | Exchange API key |
| `portfolio_manager.api_secret` | string | `""` | Exchange API secret |
| `portfolio_manager.maxOpenPositions` | int | `5` | Max simultaneous Futures positions |
| `portfolio_manager.maxLeverage` | int | `10` | Hard cap on leverage |
| `portfolio_manager.maxPositionPercent` | float | `20.0` | Max % of capital per single position |
| `portfolio_manager.maxCapitalUsagePercent` | float | `100.0` | Max % of total capital to deploy |
| `portfolio_manager.minimumConfidence` | float | `50.0` | Minimum AI confidence to place an order |
| `portfolio_manager.maxStopLossROI` | float | `80.0` | Max SL expressed as leveraged ROI% |
| `portfolio_manager.maxTakeProfitROI` | float | `200.0` | Max TP expressed as leveraged ROI% |
| `portfolio_manager.useExchangeBalance` | bool | `false` | If false, orders are simulated (paper trading) |
| `portfolio_manager.pre_flight_drift_threshold` | float | `25.0` | Drift % (of TP distance) to reject due to slippage |
| `portfolio_manager.pre_flight_imbalance_threshold` | float | `60.0` | Order book pressure % to reject order |

### Sizing
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `sizing_mode` | string | `"margin_pct"` | `"margin_pct"` or `"risk_pct"` |
| `risk_per_trade_pct` | float | `1.5` | Risk % of total capital per trade (Risk-Based mode only) |
| `allow_multiple_entries` | bool | `false` | Enable DCA / multi-entry on same asset |
| `dca_distance_pct` | float | `2.0` | Min % distance from avg price for DCA entry |
| `stop_and_reverse` | bool | `true` | Close opposite positions before reversing |

### Auto-Trading
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `auto_trading.run_weekend` | bool | `true` | Run auto-trading on weekends |
| `auto_trading.macro_cooldown` | int | `0` | Remaining runs to skip macro logic |
| `auto_trading.global_cooldown` | int | `0` | Global cooldown (all trading paused for N runs) |
| `auto_trading.btc_trade_count` | int | `0` | Internal position counter |

### Pattern Matching
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pm_history_years` | int | `1` | Years of BTC history for KNN search |
| `pm_n_neighbors` | int | `5` | K nearest neighbors |

### AI Analyst
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ai_provider` | string | `"openrouter"` | LLM provider: `openrouter`, `claude`, `openai`, `ollama` |
| `ai_model` | string | varies | Model identifier for the selected provider |
| `ai_api_key` | string | `""` | API key for the selected provider |
| `ai_debate_rounds` | int | `2` | Number of Bull vs Bear debate rounds (1–5) |
| `coingecko_api_key` | string | `""` | CoinGecko API key (Demo or Pro) |
| `coingecko_api_plan` | string | `"demo"` | CoinGecko plan: `"demo"` or `"pro"` |

---

## Installation & Setup

### Prerequisites
- **Python 3.10 or higher**
- **Tk bindings** — `tkinter` ships with the official CPython installers on
  Windows and macOS, but on Linux it is a separate OS package and is **not**
  installable via pip:
  ```bash
  # Debian / Ubuntu
  sudo apt install python3-tk
  # Fedora / RHEL
  sudo dnf install python3-tkinter
  # Arch
  sudo pacman -S tk
  ```
- **RAM**: ≥ 8 GB recommended (TimesFM model requires significant memory)
- Internet connection for data providers and LLM API calls

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/MarcoLombardoDev/Argus.git
cd Argus

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the application
python main.py
```

### First Launch
On first launch, Argus starts with no API keys configured. Navigate to the **Config** panel to:
1. Set your HuggingFace token (required to download TimesFM 2.5 from the Hub).
2. Configure your LLM provider and API key.
3. Configure your exchange API key and secret (or leave empty for paper trading mode).
4. Set your CoinGecko API key if you have a Demo or Pro plan.

TimesFM is downloaded **once** and cached locally. Subsequent launches will use the cached model.

### Running the Tests

The test suite is offline — it never contacts an exchange, a data provider or an
LLM — so it is safe to run at any time.

```bash
pip install pytest

# Logic tests only (no display required)
python -m pytest tests/test_core.py -q

# Full suite, including the GUI smoke tests.
# The GUI tests are skipped automatically when no display is available;
# on a headless machine wrap them in a virtual framebuffer:
xvfb-run -a python -m pytest tests/ -q
```

`tests/test_gui_smoke.py` boots the real application, switches through every
view and drives the table-rendering and worker-thread error paths — the places
where failures otherwise only surface at runtime.

---

## Supported Exchanges

Argus uses [CCXT](https://github.com/ccxt/ccxt) to connect to cryptocurrency exchanges. The complete, official list of all exchanges supported by CCXT is available at:

> 📋 **[CCXT — Exchange Markets](https://github.com/ccxt/ccxt/wiki/Exchange-Markets)**

The in-app exchange selector includes the most popular derivatives-capable exchanges pre-configured for convenience:

| Exchange | CCXT ID |
|----------|---------|
| Binance | `binance` |
| Binance US | `binanceus` |
| **BingX** *(primary, tested)* | `bingx` |
| Bitfinex | `bitfinex` |
| Bitget | `bitget` |
| BitMEX | `bitmex` |
| Bitmart | `bitmart` |
| Bybit | `bybit` |
| Coinbase Advanced | `coinbase` |
| Crypto.com | `cryptocom` |
| Deribit | `deribit` |
| Gate.io | `gate` |
| HTX (Huobi) | `htx` |
| Hyperliquid | `hyperliquid` |
| Kraken | `kraken` |
| KuCoin | `kucoin` |
| KuCoin Futures | `kucoinfutures` |
| MEXC | `mexc` |
| OKX | `okx` |
| Phemex | `phemex` |
| WOO X | `woo` |

The application has been primarily developed and tested with **BingX** (Futures/Swap). The following special handling is implemented:

| Exchange | Notes |
|----------|-------|
| **BingX** | Nonce patched to subtract `timeDifference`; Hedge mode supported for LONG/SHORT concurrent positions |
| **Coinbase** | PEM key newline normalization applied; `fetchPositions` skipped (not available) |
| **Others** | Standard CCXT flow; multi-account-type balance fetching with deduplication |

---


## Requirements

Key dependencies (see [`requirements.txt`](requirements.txt) for the full list):

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern dark-mode GUI framework |
| `timesfm` | Google Research TimesFM 2.5 foundation model |
| `ccxt` | Unified crypto exchange API library |
| `vectorbt` | High-performance backtesting |
| `yfinance` | Historical OHLCV data |
| `scikit-learn` | KNN for Pattern Matching |
| `numpy`, `pandas` | Numerical computing |
| `openai` | LLM provider client (OpenRouter/OpenAI/Ollama compatible) |
| `requests` | News scraping and REST API calls |
| `torch` | PyTorch backend for TimesFM |

---

## License & Commercial Licensing

Argus is open-source software released under the **[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)**.

### What AGPL-3.0 Means for You

| Use Case | Allowed? | Obligation |
|---|---|---|
| Personal / research use | ✅ Yes | None |
| Modify & redistribute privately | ✅ Yes | None |
| Deploy modified version on a server | ✅ Yes | Must publish source code of your modified version |
| Fork & publish on GitHub | ✅ Yes | Must use AGPL-3.0 license |
| Integrate into a **closed-source commercial product** | ⚠️ Restricted | Requires a commercial license (see below) |
| Offer as a **proprietary SaaS** without sharing source | ❌ Not allowed under AGPL | Requires a commercial license |

### Commercial Licensing

If you need to use Argus in a **proprietary application**, **closed-source SaaS**, or **enterprise deployment** without being bound by the AGPL-3.0 copyleft requirements, a **commercial license** is available.

A commercial license grants you the right to:
- Embed Argus in closed-source software
- Run Argus as a service without disclosing your source code
- Use Argus in commercial products without AGPL obligations

For commercial licensing inquiries, please contact **Marco Lombardo** at [marco.lombardo@gmail.com](mailto:marco.lombardo@gmail.com).

### Contributing

Contributions are welcome! All contributors must agree to the [Contributor License Agreement (CLA)](CLA.md) before their Pull Request can be merged. The CLA grants the Project Owner the right to dual-license contributions under AGPL-3.0 and commercial terms — this is what makes the dual-licensing model sustainable.

> **To agree to the CLA:** Include `I have read and agree to the Contributor License Agreement (CLA.md).` in your Pull Request description.

---

## Disclaimer

Argus is an advanced algorithmic analysis and quantitative research tool. The forecasts generated by TimesFM and the suggestions produced by LLM models do **not** constitute financial advice, investment solicitation, or any regulated financial service.

**Auto-Trading features connect to live exchanges and execute real orders using real capital.** Use this functionality responsibly and only with capital you can afford to lose. Always test thoroughly in paper trading mode (`useExchangeBalance: false`) before enabling live trading.

The authors and contributors are not responsible for any financial losses incurred through the use of this software.
