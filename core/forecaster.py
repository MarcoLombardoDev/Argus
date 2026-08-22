"""
forecaster.py — Argus
Wrapper for TimesFM 2.5. Manages model loading and generating
price forecasts for cryptos.
"""

import pandas as pd

MIN_CONTEXT_POINTS = 96   # minimum historical points required by TimesFM (set to 96 for 15m granularity)


class CryptoForecaster:
    """
    Wrapper around TimesFM for crypto price forecasts.
    The model is loaded lazily (only upon the first forecast).
    """

    def __init__(self, checkpoint: str = "google/timesfm-2.5-200m-pytorch", backend: str = "cpu"):
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

            from timesfm import TimesFM_2p5_200M_torch, ForecastConfig

            if progress_callback:
                progress_callback(
                    f"Downloading/verifying checkpoint {self.checkpoint} from HuggingFace...", 0.1
                )

            # Load the pre-trained model
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
                max_context=96,
                max_horizon=8,
                per_core_batch_size=32,
                use_continuous_quantile_head=True,
                fix_quantile_crossing=True,
            )
            self._model.compile(fc)

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
            series = price_series.tail(96).copy().ffill().bfill()
            
            # TimesFM forecast accepts a list of inputs
            point_forecasts, quantile_forecasts = self._model.forecast(
                horizon=horizon,
                inputs=[series.values.tolist()]
            )

            predicted_price = float(point_forecasts[0][horizon - 1])

            # Sanity check: price must not be negative
            if predicted_price <= 0:
                print(f"[Forecaster] Negative predicted price for {symbol}: {predicted_price}")
                return None

            # Calculation of real confidence based on relative quantile spread
            try:
                low_bound = float(quantile_forecasts[0][horizon - 1][1])
                high_bound = float(quantile_forecasts[0][horizon - 1][9])
                quantile_50 = predicted_price
                
                spread_assoluto = high_bound - low_bound
                spread_relativo = spread_assoluto / quantile_50
                
                # Calibration for 15-minute micro-volatility over 2 hours (8 candles).
                # A relative spread of 10.0% or higher sets confidence to 0.0%
                confidence_score = 100.0 * (1.0 - spread_relativo / 0.10)
                confidence_score = max(0.0, min(100.0, confidence_score))
            except Exception as e:
                print(f"[Forecaster] Error calculating confidence for {symbol}: {e}")
                confidence_score = 0.0

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
            series = price_series.tail(96).copy().ffill().bfill()
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
            # We run the forecast of the entire batch in parallel!
            # Create a copy of the list to avoid mutations
            point_forecasts, quantile_forecasts = self._model.forecast(
                horizon=horizon,
                inputs=list(valid_inputs)
            )

            for i, symbol in enumerate(valid_symbols):
                if stop_flag and stop_flag():
                    break
                preds = [float(val) for val in point_forecasts[i]]
                if any(p <= 0 for p in preds):
                    print(f"[Forecaster] Negative or invalid predicted prices for {symbol}: {preds}")
                    results[symbol] = None
                else:
                    # Calculation of real confidence based on relative quantile spread
                    try:
                        low_bound = float(quantile_forecasts[i][horizon - 1][1])
                        high_bound = float(quantile_forecasts[i][horizon - 1][9])
                        quantile_50 = preds[horizon - 1] if len(preds) >= horizon else preds[-1]
                        
                        spread_assoluto = high_bound - low_bound
                        spread_relativo = spread_assoluto / quantile_50
                        
                        # Calibration for 15-minute micro-volatility over 2 hours (8 candles).
                        # A relative spread of 10.0% or higher sets confidence to 0.0%
                        confidence_score = 100.0 * (1.0 - spread_relativo / 0.10)
                        confidence_score = max(0.0, min(100.0, confidence_score))
                    except Exception as e:
                        print(f"[Forecaster] Error calculating batch confidence for {symbol}: {e}")
                        confidence_score = 0.0

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
