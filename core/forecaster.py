# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
forecaster.py — Argus
Wrapper for TimesFM 3.0. Manages model loading and generating price forecasts
for cryptos.

**The weights are not free software.** ``timesfm`` the package is Apache-2.0,
but the checkpoint this loads — ``google/timesfm-3.0-pytorch`` — is published
under the *TimesFM Non-Commercial License*, which permits testing, evaluation
and research only, and excludes revenue-generating activity and production
systems by name. Argus never ships the weights: they are downloaded from
Hugging Face on first use, by whoever runs the program, who is the party that
licence binds. See README.md and THIRD-PARTY-LICENSES.md.

Only TimesFM 3.0 is supported. ``TimesFM3Forecaster`` is loaded in one step —
there is no compile stage — and inference goes through ``predict`` /
``predict_batch``, which return ``ForecastOutput`` objects.

The context window (96 candles) and horizon (8) are deliberately unchanged
from the 2.5 integration that preceded this. TimesFM 3.0 accepts a far longer
context, but widening it would change what the forecast means to every
downstream consumer — the ensemble weighting and the orders it sizes — so it
is a strategy decision, not part of a version upgrade.
"""

import numpy as np
import pandas as pd

MIN_CONTEXT_POINTS = 96   # minimum historical points required by TimesFM (set to 96 for 15m granularity)

CONTEXT_CANDLES = 96      # 24 hours at 15m
MAX_HORIZON = 8           # 2 hours at 15m

DEFAULT_CHECKPOINT = "google/timesfm-3.0-pytorch"

# Relative quantile spread at which confidence reaches 0%. Calibrated against
# TimesFM 2.5 on 15-minute candles over a 2-hour horizon; TimesFM 3.0 is a
# different model and its spreads are not guaranteed to be on the same scale,
# so this is worth re-checking against live output before trusting the number.
CONFIDENCE_ZERO_SPREAD = 0.10


def _confidence_from_spread(low: float, high: float, mid: float) -> float:
    """Maps a quantile spread to a 0-100 confidence score.

    A wide band between the 10th and 90th percentile means the model is
    unsure. ``CONFIDENCE_ZERO_SPREAD`` is the relative width at which that
    reaches zero.
    """
    if mid <= 0:
        return 0.0
    spread_relative = (high - low) / mid
    score = 100.0 * (1.0 - spread_relative / CONFIDENCE_ZERO_SPREAD)
    return max(0.0, min(100.0, score))


class CryptoForecaster:
    """
    Wrapper around TimesFM 3.0 for crypto price forecasts.
    The model is loaded lazily (only upon the first forecast).
    """

    def __init__(self, checkpoint: str = DEFAULT_CHECKPOINT, backend: str = "cpu"):
        self.checkpoint = checkpoint
        self.backend = backend
        self._model = None
        self._model_loaded = False

    def _calculate_atr(self, df: pd.DataFrame, fallback_price: float) -> float:
        """
        Calculates the 14-period ATR on past historical data.
        """
        try:
            if df is not None and len(df) >= 15:
                # Ensure the necessary columns exist
                cols = ["High", "Low", "Close"]
                if all(c in df.columns for c in cols):
                    df_tail = df.tail(15).copy()
                    df_tail["High"] = pd.to_numeric(df_tail["High"], errors="coerce")
                    df_tail["Low"] = pd.to_numeric(df_tail["Low"], errors="coerce")
                    df_tail["Close"] = pd.to_numeric(df_tail["Close"], errors="coerce")

                    df_tail['H-L'] = df_tail['High'] - df_tail['Low']
                    df_tail['H-C'] = (df_tail['High'] - df_tail['Close'].shift(1)).abs()
                    df_tail['L-C'] = (df_tail['Low'] - df_tail['Close'].shift(1)).abs()
                    df_tail['TR'] = df_tail[['H-L', 'H-C', 'L-C']].max(axis=1)

                    atr_series = df_tail['TR'].rolling(14).mean()
                    if not atr_series.dropna().empty:
                        atr_val = float(atr_series.dropna().iloc[-1])
                        if atr_val > 0:
                            return atr_val
        except Exception as e:
            print(f"[Forecaster] Error calculating ATR: {e}")

        # Fallback if not calculable or equal to 0 (e.g. 1.5% of price)
        return fallback_price * 0.015

    def _torch_device(self) -> str:
        """Maps Argus's backend setting onto a torch device string."""
        return "cuda" if str(self.backend).lower() in ("gpu", "cuda") else "cpu"

    def load_model(self, progress_callback=None):
        """
        Loads the TimesFM model from HuggingFace (downloads if necessary).
        To be called in a separate thread to avoid blocking the GUI.

        Downloading the checkpoint means accepting Google's TimesFM
        Non-Commercial License — see this module's docstring.
        """
        if self._model_loaded:
            return True

        if progress_callback:
            progress_callback("Loading TimesFM model...", 0.0)

        try:
            import os
            try:
                from core.data_manager import load_settings
                settings = load_settings()
                hf_token = settings.get("hf_token", "").strip()
                if hf_token:
                    os.environ["HF_TOKEN"] = hf_token
                    os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_token
            except Exception as e:
                print(f"[Forecaster] Unable to load HF token from settings: {e}")

            if progress_callback:
                progress_callback(
                    f"Downloading/verifying checkpoint {self.checkpoint} from HuggingFace...", 0.1
                )

            # There is no separate compile step: the forecaster builds the
            # model in its constructor, so this returns ready to predict.
            from timesfm3 import TimesFM3Forecaster

            self._model = TimesFM3Forecaster.from_pretrained(
                self.checkpoint,
                device=self._torch_device(),
            )

            self._model_loaded = True
            if progress_callback:
                progress_callback("TimesFM model loaded successfully.", 1.0)
            return True

        except ImportError as e:
            msg = (
                f"ERROR: timesfm not installed or import problems: {e}\n"
                "Verify dependency installation."
            )
            if progress_callback:
                progress_callback(msg, 0.0)
            print(f"[Forecaster] {msg}")
            return False
        except Exception as e:
            msg = f"ERROR loading model: {e}"
            if progress_callback:
                progress_callback(msg, 0.0)
            print(f"[Forecaster] {msg}")
            return False

    def _quantile_indices(self) -> tuple[int, int]:
        """Positions of the 10th and 90th percentile in a quantile row.

        TimesFM 3.0 returns one column per configured quantile — nine of them
        by default, 0.1 through 0.9. The positions are looked up rather than
        assumed: a checkpoint configured with a different quantile set would
        otherwise have the wrong percentiles read out of it, or raise and
        leave every forecast reporting zero confidence.
        """
        quantiles = list(getattr(self._model.config, "quantiles", []) or [])
        try:
            return quantiles.index(0.1), quantiles.index(0.9)
        except ValueError:
            # Fall back to the outermost pair, the widest band available.
            return 0, max(0, len(quantiles) - 1)

    def _confidence(self, quantiles_row) -> float:
        """Confidence for one horizon step of a forecast."""
        try:
            low_idx, high_idx = self._quantile_indices()
            low_bound = float(quantiles_row[low_idx])
            high_bound = float(quantiles_row[high_idx])
            mid = float(quantiles_row[self._model.config.median_quantile_index])
            return _confidence_from_spread(low_bound, high_bound, mid)
        except Exception as e:
            print(f"[Forecaster] Error calculating confidence: {e}")
            return 0.0

    def forecast(
        self,
        symbol: str,
        historical_df: pd.DataFrame,
        horizon: int = 1,
    ) -> tuple[float, float] | None:
        """
        Generates the price forecast for the target day (horizon) for a single crypto
        and the corresponding statistical confidence.

        Args:
            symbol: symbol ticker (e.g. 'BTC')
            historical_df: DataFrame with 'Close' column and DatetimeIndex index
            horizon: number of periods ahead (1 to 8)

        Returns:
            Tuple (predicted price at day 'horizon', confidence 0-100) or None in case of error.
        """
        if not self._model_loaded:
            print(f"[Forecaster] Model not loaded for {symbol}")
            return None

        if "Close" not in historical_df.columns:
            print(f"[Forecaster] Missing 'Close' column for {symbol}")
            return None

        price_series = historical_df["Close"].dropna()

        if len(price_series) < MIN_CONTEXT_POINTS:
            print(
                f"[Forecaster] Insufficient data points for {symbol}: "
                f"{len(price_series)} < {MIN_CONTEXT_POINTS}"
            )
            return None

        try:
            # Extracts the last 96 candles for context (24 hours at 15m)
            series = price_series.tail(CONTEXT_CANDLES).copy().ffill().bfill()

            output = self._model.predict(
                context=np.asarray(series.values, dtype=np.float32),
                horizon=horizon,
                return_quantiles=True,
            )
            predicted_price = float(output.forecast[horizon - 1])
            confidence_score = self._confidence(output.quantiles[horizon - 1])

            # Sanity check: price must not be negative
            if predicted_price <= 0:
                print(f"[Forecaster] Negative predicted price for {symbol}: {predicted_price}")
                return None

            return predicted_price, confidence_score

        except Exception as e:
            print(f"[Forecaster] Forecast error for {symbol}: {e}")
            return None

    def forecast_batch(
        self,
        crypto_data: dict[str, pd.DataFrame],
        horizon: int = 1,
        progress_callback=None,
        stop_flag=None,
    ) -> dict[str, dict | None]:
        """
        Executes forecast on all cryptos in the dict in a single speeded-up batch call.

        Args:
            crypto_data: {symbol: historical_df}
            horizon: periods ahead (1 to 8)
            progress_callback(msg, fraction): callback to update the GUI
            stop_flag: callable that returns True if the operation should stop

        Returns:
            {symbol: {"preds": preds_list, "confidence": confidence_score}}
        """
        results = {}
        valid_symbols = []
        valid_inputs = []

        if not self._model_loaded:
            print("[Forecaster] Model not loaded.")
            return results

        if progress_callback:
            progress_callback("Filtering and preparing historical data...", 0.05)

        for symbol, df in crypto_data.items():
            if stop_flag and stop_flag():
                break

            if "Close" not in df.columns:
                print(f"[Forecaster] Missing 'Close' column for {symbol}")
                results[symbol] = None
                continue

            price_series = df["Close"].dropna()
            if len(price_series) < MIN_CONTEXT_POINTS:
                print(
                    f"[Forecaster] Insufficient data points for {symbol}: "
                    f"{len(price_series)} < {MIN_CONTEXT_POINTS}"
                )
                results[symbol] = None
                continue

            # Extracts the last 96 candles for context (24 hours at 15m)
            series = price_series.tail(CONTEXT_CANDLES).copy().ffill().bfill()
            valid_symbols.append(symbol)
            valid_inputs.append(series.values.tolist())

        if not valid_symbols:
            return results

        if stop_flag and stop_flag():
            return results

        if progress_callback:
            progress_callback(
                f"Calculating batch forecast with TimesFM for {len(valid_symbols)} cryptos...",
                0.2
            )

        try:
            batch = self._batch(valid_inputs, horizon)

            for i, symbol in enumerate(valid_symbols):
                if stop_flag and stop_flag():
                    break
                preds, confidence_score = batch[i]
                if not preds or any(p <= 0 for p in preds):
                    print(f"[Forecaster] Negative or invalid predicted prices for {symbol}: {preds}")
                    results[symbol] = None
                else:
                    results[symbol] = {
                        "preds": preds,
                        "confidence": confidence_score
                    }

        except Exception as e:
            print(f"[Forecaster] Error during batch forecast: {e}")
            for symbol in valid_symbols:
                results[symbol] = None

        if progress_callback:
            progress_callback("Forecast calculation completed successfully.", 1.0)

        return results

    def _batch(self, inputs, horizon: int) -> list[tuple[list[float], float]]:
        """Runs a batch forecast, one (preds, confidence) pair per input.

        ``predict_batch`` yields its results, so it is drained into a list
        before anything indexes into it.
        """
        outputs = list(self._model.predict_batch(
            contexts=[np.asarray(series, dtype=np.float32) for series in inputs],
            horizon=horizon,
            return_quantiles=True,
        ))

        out = []
        for output in outputs:
            if output.forecast is None:
                out.append(([], 0.0))
                continue
            preds = [float(val) for val in output.forecast]
            if output.quantiles is None:
                out.append((preds, 0.0))
                continue
            out.append((preds, self._confidence(output.quantiles[horizon - 1])))
        return out
