"""
analyzer.py — Argus
Calculates BUY / HOLD / SELL signals and forecast expiry dates.
"""

from datetime import datetime, timedelta
import pandas as pd


# Signal mapping removed, now only percentages are used.


def calculate_change_pct(
    current_price: float,
    forecast_price: float,
) -> float:
    """
    Calculates the expected percentage change.

    Args:
        current_price: last known close price
        forecast_price: predicted price from TimesFM

    Returns:
        change_pct: percentage change
    """
    if current_price <= 0:
        return 0.0

    change_pct = (forecast_price - current_price) / current_price * 100.0
    return round(change_pct, 4)


def compute_expiry_date(validity_hours: int = 1, from_date: datetime | None = None) -> str:
    """
    Calculates the expiration date of the analysis validity.
    
    Returns:
        Expiration date in 'YYYY-MM-DD %H:%M:%S' format.
    """
    if from_date is None:
        from_date = datetime.now()

    current = from_date
    current += timedelta(hours=validity_hours)

    return current.strftime("%Y-%m-%d %H:%M:%S")


def build_results(
    crypto_list: list[dict],
    forecasts: dict[str, list[float] | None],
    horizon_days: int = 3,
    threshold_pct: float = 2.0,
) -> list[dict]:
    """
    Assembles the final list of results combining crypto data + 1d and 3d forecasts.

    Args:
        crypto_list: list of dicts from CoinGecko ({rank, name, symbol, current_price, ...})
        forecasts: {symbol: list[predicted_price] | None}
        horizon_days: no longer used directly, forced to 3
        threshold_pct: threshold for BUY/SELL

    Returns:
        List of dicts sorted by rank, ready for GUI and CSV.
    """
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Calculate the expiration based on the maximum horizon (2 hours for the cryptos)
    expiry_date = compute_expiry_date(2, from_date=datetime.now())
    results = []

    for coin in crypto_list:
        symbol = coin["symbol"]
        current_price = coin.get("current_price", 0.0)
        
        forecast_entry = forecasts.get(symbol) if forecasts else None
        
        if forecast_entry is None or not isinstance(forecast_entry, dict):
            target_1d = None
            pct_1d = None
            confidence = None
        else:
            preds = forecast_entry.get("preds")
            confidence = forecast_entry.get("confidence")
            if preds is None or not isinstance(preds, list) or len(preds) < 1 or current_price is None or current_price <= 0:
                target_1d = None
                pct_1d = None
            else:
                # With an 8-candle horizon at 15m, we take the last value (t+8, i.e., 2 hours)
                pred_1d = preds[-1]
                pct_1d = calculate_change_pct(current_price, pred_1d)
                target_1d = round(pred_1d, 6)

        results.append({
            "rank": coin.get("rank", 0),
            "name": coin.get("name", ""),
            "symbol": symbol,
            "confidence": confidence,
            "last_price": round(current_price, 6) if current_price else None,
            
            "target_price_1d": target_1d,
            "change_pct_1d": pct_1d,
            
            # Legacy fields for backward compatibility
            "forecast_price": target_1d,
            "change_pct": pct_1d,
            
            "horizon_days": 1,
            "run_date": run_date,
            "expiry_date": expiry_date,
        })

    # Sort by rank
    results.sort(key=lambda x: x["rank"] or 9999)
    return results


def filter_results(
    results: list[dict],
    signal_filter: str = "ALL",
) -> list[dict]:
    """
    Removed signal filter. Returns all results.
    """
    return results


def results_to_dataframe(results: list[dict]) -> pd.DataFrame:
    """Converts the results list to a pandas DataFrame."""
    return pd.DataFrame(results)


def format_price(price: float | None) -> str:
    """Formats the price for display (adapts precision to the value)."""
    if price is None:
        return "N/A"
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.4f}"
    elif price >= 0.001:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"


def format_change_pct(change_pct: float | None) -> str:
    """Formats the percentage change for display."""
    if change_pct is None:
        return "N/A"
    sign = "+" if change_pct >= 0 else ""
    return f"{sign}{change_pct:.2f}%"


def verify_past_forecasts() -> list[dict]:
    """
    Loads the forecast history from forecast_history.csv and crosses it
    with real current/historical prices saved locally to calculate the outcome.
    """
    from core.data_manager import load_historical, FORECAST_HISTORY_PATH
    import pandas as pd
    import numpy as np
    
    if not FORECAST_HISTORY_PATH.exists():
        return []
        
    try:
        df_history = pd.read_csv(FORECAST_HISTORY_PATH, encoding="utf-8")
    except Exception as e:
        print(f"[Analyzer] Error loading forecast_history: {e}")
        return []
        
    verified_results = []
    
    # Load all unique symbols present in history
    symbols = df_history["symbol"].unique()
    historical_dfs = {}
    for s in symbols:
        historical_dfs[s] = load_historical(s)
        
    for _, row in df_history.iterrows():
        symbol = row.get("symbol")
        run_date_str = row.get("run_date")
        expiry_date_str = row.get("expiry_date")
        last_price = row.get("last_price")
        forecast_price = row.get("forecast_price")
        signal = row.get("signal")
        horizon_days = row.get("horizon_days")
        name = row.get("name", symbol)
        rank = row.get("rank", 999)
        change_pct = row.get("change_pct")
        
        # Convert to safe float/int
        try:
            last_price = float(last_price) if pd.notna(last_price) else None
            forecast_price = float(forecast_price) if pd.notna(forecast_price) else None
            horizon_days = int(horizon_days) if pd.notna(horizon_days) else 1
            change_pct = float(change_pct) if pd.notna(change_pct) else 0.0
        except (ValueError, TypeError):
            continue
            
        actual_price = None
        actual_price_time = "N/A"
        status = "⚪ N/A"
        error_pct = None
        
        # Convert date strings to datetime objects for correct comparison
        now_dt = datetime.now()
        try:
            expiry_dt = pd.to_datetime(expiry_date_str)
        except Exception:
            expiry_dt = None
            
        if expiry_dt is not None and expiry_dt > now_dt:
            # Forecast has not expired yet (is in the future)
            status = "Pending"
        else:
            # Load the local historical DataFrame of the symbol
            df_hist = historical_dfs.get(symbol)
            
            if df_hist is not None and not df_hist.empty:
                # Find match with expiry_date_str (date only for matching with historical data)
                expiry_date_only = expiry_dt.strftime("%Y-%m-%d") if expiry_dt else str(expiry_date_str).split()[0]
                df_temp = df_hist.copy()
                try:
                    if not isinstance(df_temp.index, pd.DatetimeIndex):
                        df_temp.index = pd.to_datetime(df_temp.index)
                    df_temp.index = df_temp.index.strftime("%Y-%m-%d")
                    
                    matching_indices = [i for i, idx_str in enumerate(df_temp.index) if idx_str == expiry_date_only]
                    if matching_indices:
                        orig_idx = df_hist.index[matching_indices[0]]
                        actual_price_time = str(orig_idx)
                        val = df_temp.loc[expiry_date_only, "Close"]
                        if isinstance(val, (pd.Series, pd.DataFrame)):
                            actual_price = float(val.iloc[0])
                        else:
                            actual_price = float(val)
                    else:
                        # Find closest date available within 2 days (e.g. weekend or yfinance gap)
                        try:
                            target_dt = expiry_dt if expiry_dt else pd.to_datetime(expiry_date_str)
                            available_dts = pd.to_datetime(df_temp.index)
                            diffs = (available_dts - target_dt).days
                            abs_diffs = np.abs(diffs)
                            min_idx = np.argmin(abs_diffs)
                            if abs_diffs[min_idx] <= 2:
                                closest_date_str = df_temp.index[min_idx]
                                orig_idx = df_hist.index[min_idx]
                                actual_price_time = str(orig_idx)
                                val = df_temp.loc[closest_date_str, "Close"]
                                if isinstance(val, (pd.Series, pd.DataFrame)):
                                    actual_price = float(val.iloc[0])
                                else:
                                    actual_price = float(val)
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[Analyzer] Error processing history for {symbol}: {e}")
            
            if actual_price is not None:
                error_pct = (forecast_price - actual_price) / actual_price * 100.0
                
                # Signal evaluation
                price_change = actual_price - last_price if last_price is not None else 0.0
                price_change_pct = (price_change / last_price) * 100.0 if last_price and last_price > 0 else 0.0
                
                # Threshold for BUY/SELL
                threshold = float(row.get("signal_threshold_pct", 2.0)) if "signal_threshold_pct" in row else 2.0
                
                if price_change_pct > threshold:
                    actual_signal = "BUY"
                elif price_change_pct < -threshold:
                    actual_signal = "SELL"
                else:
                    actual_signal = "HOLD"
                    
                if signal == actual_signal:
                    status = "CORRECT"
                else:
                    status = "WRONG"
            else:
                status = "N/A"
            
        verified_results.append({
            "rank": rank,
            "name": name,
            "symbol": symbol,
            "run_date": run_date_str,
            "horizon_days": horizon_days,
            "last_price": last_price,
            "forecast_price": forecast_price,
            "change_pct": change_pct,
            "signal": signal,
            "expiry_date": expiry_date_str,
            "actual_price": round(actual_price, 6) if actual_price is not None else None,
            "actual_price_time": actual_price_time,
            "error_pct": round(error_pct, 2) if error_pct is not None else None,
            "status": status
        })
        
    # Sort by descending run_date
    verified_results.sort(key=lambda x: x["run_date"], reverse=True)
    return verified_results
