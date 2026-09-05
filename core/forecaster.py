# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
forecaster.py — Argus
Wrapper for TimesFM. Manages model loading and generating price forecasts
for cryptos.

Two model generations are supported, because a user's saved
``model_checkpoint`` may still name an older one:

* **TimesFM 3.0** (default) — ``timesfm3.TimesFM3Forecaster``. Loaded in one
  step; inference through ``predict`` / ``predict_batch``, which return
  ``ForecastOutput`` objects.
* **TimesFM 1.0 / 2.0 / 2.5** (legacy) — ``timesfm.TimesFM_2p5_200M_torch``.
  Loaded, then ``compile``d with a ``ForecastConfig``; inference through
  ``forecast``, which returns a ``(point, quantile)`` tuple.

The two APIs share nothing but the idea, so which one a checkpoint needs is
decided by :func:`uses_legacy_api` and every call site branches on it.

The context window (96 candles) and horizon (8) are deliberately unchanged
from the 2.5 integration. TimesFM 3.0 accepts a far longer context, but
widening it would change what the forecast means to every downstream
consumer — the ensemble weighting and the orders it sizes — so it is a
strategy decision, not part of a version upgrade.
"""

import numpy as np
import pandas as pd

MIN_CONTEXT_POINTS = 96   # minimum historical points required by TimesFM (set to 96 for 15m granularity)

CONTEXT_CANDLES = 96      # 24 hours at 15m
MAX_HORIZON = 8           # 2 hours at 15m

DEFAULT_CHECKPOINT = "google/timesfm-3.0-pytorch"

# Checkpoint families that need the pre-3.0 API. Anything not matching one of
# these — the 3.0 checkpoint, a local directory, a private fine-tune — is
# treated as TimesFM 3.0, which is the current generation.
LEGACY_CHECKPOINT_MARKERS = ("timesfm-1.", "timesfm-2.", "timesfm_1", "timesfm_2")

# Relative quantile spread at which confidence reaches 0%. Calibrated against
# TimesFM 2.5 on 15-minute candles over a 2-hour horizon; TimesFM 3.0 is a
# different model and its spreads are not guaranteed to be on the same scale,
# so this is worth re-checking against live output before trusting the number.
CONFIDENCE_ZERO_SPREAD = 0.10


def uses_legacy_api(checkpoint: str) -> bool:
    """True when *checkpoint* names a TimesFM 1.x/2.x model.

    The decision has to be made from the checkpoint string alone, because that
    is all the settings file stores.
    """
    name = (checkpoint or "").lower()
    return any(marker in name for marker in LEGACY_CHECKPOINT_MARKERS)


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
    Wrapper around TimesFM for crypto price forecasts.
    The model is loaded lazily (only upon the first forecast).
    """

    def __init__(self, checkpoint: str = DEFAULT_CHECKPOINT, backend: str = "cpu"):
        self.checkpoint = checkpoint
        self.backend = backend
        self._model = None
        self._model_loaded = False
        self._legacy = uses_legacy_api(checkpoint)

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

            if self._legacy:
                self._load_legacy_model(progress_callback)
            else:
                self._load_v3_model(progress_callback)

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

    def _load_v3_model(self, progress_callback=None):
        """Loads a TimesFM 3.0 checkpoint.

        There is no separate compile step: the forecaster builds the model in
        its constructor, so this returns ready to predict.
        """
        from timesfm3 import TimesFM3Forecaster

        self._model = TimesFM3Forecaster.from_pretrained(
            self.checkpoint,
            device=self._torch_device(),
        )

    def _load_legacy_model(self, progress_callback=None):
        """Loads and compiles a TimesFM 1.x/2.x checkpoint."""
        from timesfm import ForecastConfig, TimesFM_2p5_200M_torch

        # We use torch_compile=False to speed up startup and avoid issues on Windows/CPU
        self._model = TimesFM_2p5_200M_torch.from_pretrained(
            self.checkpoint,
            torch_compile=False
        )

        if progress_callback:
            progress_callback("Compiling forecast config...", 0.8)

        # Configuration and compilation for horizon t+8 and context 96
        # Enable use_continuous_quantile_head to calculate confidence
        fc = ForecastConfig(
            max_context=CONTEXT_CANDLES,
            max_horizon=MAX_HORIZON,
            per_core_batch_size=32,
            use_continuous_quantile_head=True,
            fix_quantile_crossing=True,
        )
        self._model.compile(fc)

    def _v3_quantile_indices(self) -> tuple[int, int]:
        """Positions of the 10th and 90th percentile in a v3 quantile row.

        TimesFM 3.0 returns one column per configured quantile — nine of them
        by default, 0.1 through 0.9 — while 2.5 returned the point forecast
        first and the nine quantiles after it. Reading 2.5's indices out of a
        v3 row would silently pick the wrong percentiles, or raise and leave
        every forecast reporting zero confidence, so the positions are looked
        up rather than assumed.
        """
        quantiles = list(getattr(self._model.config, "quantiles", []) or [])
        try:
            return quantiles.index(0.1), quantiles.index(0.9)
        except ValueError:
            # A checkpoint configured with a different quantile set: fall back
            # to the outermost pair, which is the widest band available.
            return 0, max(0, len(quantiles) - 1)

    def _v3_confidence(self, quantiles_row) -> float:
        """Confidence for one horizon step of a v3 forecast."""
        try:
            low_idx, high_idx = self._v3_quantile_indices()
            low_bound = float(quantiles_row[low_idx])
            high_bound = float(quantiles_row[high_idx])
            mid = float(quantiles_row[self._model.config.median_quantile_index])
            return _confidence_from_spread(low_bound, high_bound, mid)
        except Exception as e:
            print(f"[Forecaster] Error calculating confidence: {e}")
            return 0.0

    def _legacy_confidence(self, quantile_forecast_row, point_value: float) -> float:
        """Confidence for one horizon step of a 1.x/2.x forecast.

        Index 1 and 9 are the 10th and 90th percentile in that layout, whose
        first column is the point forecast.
        """
        try:
            low_bound = float(quantile_forecast_row[1])
            high_bound = float(quantile_forecast_row[9])
            return _confidence_from_spread(low_bound, high_bound, point_value)
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

            if self._legacy:
                point_forecasts, quantile_forecasts = self._model.forecast(
                    horizon=horizon,
                    inputs=[series.values.tolist()]
                )
                predicted_price = float(point_forecasts[0][horizon - 1])
                confidence_score = self._legacy_confidence(
                    quantile_forecasts[0][horizon - 1], predicted_price
                )
            else:
                output = self._model.predict(
                    context=np.asarray(series.values, dtype=np.float32),
                    horizon=horizon,
                    return_quantiles=True,
                )
                predicted_price = float(output.forecast[horizon - 1])
                confidence_score = self._v3_confidence(output.quantiles[horizon - 1])

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
            if self._legacy:
                batch = self._legacy_batch(valid_inputs, horizon)
            else:
                batch = self._v3_batch(valid_inputs, horizon)

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

    def _legacy_batch(self, inputs, horizon: int) -> list[tuple[list[float], float]]:
        """Runs a 1.x/2.x batch forecast, one (preds, confidence) pair per input."""
        point_forecasts, quantile_forecasts = self._model.forecast(
            horizon=horizon,
            inputs=list(inputs)
        )

        out = []
        for i in range(len(inputs)):
            preds = [float(val) for val in point_forecasts[i]]
            reference = preds[horizon - 1] if len(preds) >= horizon else preds[-1]
            confidence = self._legacy_confidence(
                quantile_forecasts[i][horizon - 1], reference
            )
            out.append((preds, confidence))
        return out

    def _v3_batch(self, inputs, horizon: int) -> list[tuple[list[float], float]]:
        """Runs a 3.0 batch forecast, one (preds, confidence) pair per input.

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
            out.append((preds, self._v3_confidence(output.quantiles[horizon - 1])))
        return out
