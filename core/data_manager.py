"""
data_manager.py — Argus
Management of reading/writing CSV (historical and forecast log) and JSON (settings) files.
"""

import json
import os
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv, set_key

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
HISTORICAL_DIR = DATA_DIR / "historical"
FORECAST_LOG_PATH = DATA_DIR / "forecast_log.csv"
FORECAST_HISTORY_PATH = DATA_DIR / "forecast_history.csv"
SETTINGS_PATH = BASE_DIR / "config" / "settings.json"
AI_ANALYSIS_DIR = DATA_DIR / "ai_analysis"
MARKET_LISTS_DIR = DATA_DIR / "market_lists"
AUTOTRADING_LOGS_PATH = DATA_DIR / "autotrading_log.json"
PM_HISTORY_PATH = DATA_DIR / "pm_history.json"

# Default settings
DEFAULT_SETTINGS = {
    # Temporal analysis parameters
    "horizon_days": 1,
    "history_days": 365,
    "signal_threshold_pct": 1.0,
    "backend": "gpu",
    "model_checkpoint": "",
    "hf_token": "",
    "last_run": "2026-06-17T21:30:25.387729",
    # Active market type and asset count
    "market_type": "crypto",
    # Crypto Provider: CoinGecko
    "coingecko_api_key": "",
    "coingecko_api_plan": "demo",
    # Backward compatibility
    "data_source": "coingecko",
    # Advanced AI analysis settings
    "ai_provider": "openrouter",
    "ai_ollama_host": "http://localhost:11434/v1",
    "ai_model_quick": "",
    "ai_model_deep": "",
    "ai_model_fallback": "",
    "ai_research_rounds": 3,
    "ai_api_key": "",
    "ai_finnhub_key": "",
    "ai_coingecko_key": "",
    "ai_signal_threshold_pct": 1.0,
    # --- Risk Management & Execution Settings ---
    "sizing_mode": "margin_pct",          # "margin_pct" | "risk_pct"
    "risk_per_trade_pct": 1.5,            # Maximum risk per trade as % of total capital
    "allow_multiple_entries": True,       # If False, blocks new orders if there is already an open position for the asset
    "dca_distance_pct": 0.15,             # Minimum price distance in % for a new matching order (if multiples allowed)
    "use_timesfm_auto": True,             # If True, requires confirmation from TimesFM in AutoTrading
    "stop_and_reverse": False,            # If True, liquidates opposite positions before opening a new one (prevents hedge loss)
    "ai_model": "",
    "ai_model_custom": "",
    "last_price_update_crypto": "17/06/2026 21:30",
    "last_list_update_crypto": "10/06/2026 11:49",
    "portfolio_manager": {
        "exchange_id": "bingx",
        "useExchangeBalance": True,
        "api_key": "",
        "api_secret": "",
        "refresh_min": 60.0,
        "maxCapitalUsagePercent": 98.0,
        "maxPositionPercent": 25.0,
        "maxOpenPositions": 10,
        "minimumConfidence": 50.0,
        "maxLeverage": 30,
        "maxStopLossROI": 80.0,
        "maxTakeProfitROI": 6.0,
        "pre_flight_drift_threshold": 50.0,
        "pre_flight_imbalance_threshold": 50.0
    },
    "auto_trading": {
        "low_conf_cooldowns": {},
        "macro_cooldown": 1,
        "btc_trade_count": 1,
        "run_weekend": False
    },
    "ensemble_w_tfm": 40,
    "ensemble_w_pm": 40,
    "ensemble_w_ai": 20,
    "ensemble_min_return_pct": 0.1
}


def ensure_dirs():
    """Creates necessary directories if they do not exist."""
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AI_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    MARKET_LISTS_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "config").mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    """Loads configuration from settings.json and integrates sensitive keys from .env."""
    ensure_dirs()
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
        
    settings = DEFAULT_SETTINGS.copy()
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            settings.update(loaded)
        except Exception as e:
            print(f"[DataManager] Error reading settings: {e}. Using defaults.")
            
    # Integrate sensitive keys from .env/environment if present
    sensitive_keys = {
        "hf_token": "HF_TOKEN",
        "coingecko_api_key": "COINGECKO_API_KEY",
        "ai_api_key": "AI_API_KEY",
        "ai_finnhub_key": "AI_FINNHUB_KEY",
        "ai_coingecko_key": "AI_COINGECKO_KEY"
    }
    
    for settings_key, env_key in sensitive_keys.items():
        val = os.getenv(env_key)
        if val is not None:
            settings[settings_key] = val
            
    # Portfolio manager management
    pm_settings = settings.setdefault("portfolio_manager", {})
    for pm_key in ["api_key", "api_secret"]:
        env_key = f"PORTFOLIO_MANAGER_{pm_key.upper()}"
        val = os.getenv(env_key)
        if val is not None:
            pm_settings[pm_key] = val
            
    return settings


def save_settings(settings: dict):
    """Saves configuration to settings.json, keeping sensitive keys in .env."""
    ensure_dirs()
    
    import copy
    settings_to_save = copy.deepcopy(settings)
    
    sensitive_keys = {
        "hf_token": "HF_TOKEN",
        "coingecko_api_key": "COINGECKO_API_KEY",
        "ai_api_key": "AI_API_KEY",
        "ai_finnhub_key": "AI_FINNHUB_KEY",
        "ai_coingecko_key": "AI_COINGECKO_KEY"
    }
    
    if not ENV_PATH.exists():
        try:
            ENV_PATH.touch()
        except Exception:
            pass
        
    # Save sensitive keys in the .env file
    for settings_key, env_key in sensitive_keys.items():
        val = settings_to_save.get(settings_key, "")
        success = False
        import time
        for attempt in range(3):
            try:
                set_key(str(ENV_PATH), env_key, str(val))
                success = True
                break
            except Exception as e:
                time.sleep(0.1)
        if not success:
            print(f"[DataManager] Error writing key {env_key} in .env: file locked or access denied.")
        settings_to_save[settings_key] = ""
        
    # Portfolio manager management
    pm_settings = settings_to_save.setdefault("portfolio_manager", {})
    for pm_key in ["api_key", "api_secret"]:
        env_key = f"PORTFOLIO_MANAGER_{pm_key.upper()}"
        val = pm_settings.get(pm_key, "")
        success = False
        import time
        for attempt in range(3):
            try:
                set_key(str(ENV_PATH), env_key, str(val))
                success = True
                break
            except Exception as e:
                time.sleep(0.1)
        if not success:
            print(f"[DataManager] Error writing key {env_key} in .env: file locked or access denied.")
        pm_settings[pm_key] = ""
        
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings_to_save, f, indent=2, default=str)
    except Exception as e:
        print(f"[DataManager] Error saving settings: {e}")


def save_historical(symbol: str, df: pd.DataFrame):
    """
    Overwrites the historical CSV file for the specified symbol.
    df must have index of type DatetimeIndex and 'Close' column.
    """
    ensure_dirs()
    path = HISTORICAL_DIR / f"{symbol.upper()}.csv"
    try:
        df.to_csv(path)
    except Exception as e:
        print(f"[DataManager] Error saving history for {symbol}: {e}")


def load_historical(symbol: str) -> pd.DataFrame | None:
    """Loads the historical CSV for the symbol. If the data is older than 2 hours, raises an exception."""
    path = HISTORICAL_DIR / f"{symbol.upper()}.csv"
    if not path.exists():
        raise ValueError(f"Missing historical data for {symbol}. Go to the Markets tab and click Update Prices.")
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        # Obsolescence check
        if not df.empty:
            last_time = df.index[-1]
            # Ensure last_time is tz-naive for comparison
            if last_time.tzinfo is not None:
                last_time = last_time.tz_localize(None)
            
            # The timestamps saved by CCXT are in UTC (tz-naive). 
            # We must compare them with the current UTC time, not local time.
            now_utc = datetime.utcnow()
            
            if (now_utc - last_time).total_seconds() > 7200:
                raise ValueError(f"Obsolete historical data for {symbol} (older than 2 hours). Go to the Markets tab and click Update Prices.")
        return df
    except ValueError as ve:
        raise ve
    except Exception as e:
        print(f"[DataManager] Error reading history for {symbol}: {e}")
        return None


def save_forecast_log(results: list[dict]):
    """
    Overwrites the forecast_log.csv file with the results of the last analysis
    and appends them to forecast_history.csv for backtesting.
    """
    ensure_dirs()
    if not results:
        return
    try:
        df = pd.DataFrame(results)
        df.to_csv(FORECAST_LOG_PATH, index=False, encoding="utf-8")
        print(f"[DataManager] Forecast log saved: {FORECAST_LOG_PATH}")
        append_to_forecast_history(results)
    except Exception as e:
        print(f"[DataManager] Error saving forecast log: {e}")


def append_to_forecast_history(results: list[dict]):
    """
    Saves the current results by appending them to forecast_history.csv, 
    maintaining up to 2500 historical analyses (e.g. 50 runs of 50 assets).
    """
    ensure_dirs()
    if not results:
        return
    try:
        new_df = pd.DataFrame(results)
        if FORECAST_HISTORY_PATH.exists():
            old_df = pd.read_csv(FORECAST_HISTORY_PATH, encoding="utf-8")
            
            # Avoid DataFrame concatenation with all-NA entries FutureWarning
            old_df = old_df.dropna(axis=1, how='all')
            new_df = new_df.dropna(axis=1, how='all')
            
            if old_df.empty:
                combined_df = new_df
            elif new_df.empty:
                combined_df = old_df
            else:
                combined_df = pd.concat([old_df, new_df], ignore_index=True)
                
            # Keep the last 2500 rows to handle multiple runs with large lists
            combined_df = combined_df.tail(2500)
        else:
            combined_df = new_df
            
        combined_df.to_csv(FORECAST_HISTORY_PATH, index=False, encoding="utf-8")
        print("[DataManager] History forecast_history.csv updated (appended, max 2500).")
    except Exception as e:
        print(f"[DataManager] Error saving forecast history: {e}")


def load_forecast_log() -> pd.DataFrame | None:
    """Loads forecast_log.csv (last run only) if it exists, otherwise None."""
    if not FORECAST_LOG_PATH.exists():
        return None
    try:
        df = pd.read_csv(FORECAST_LOG_PATH, encoding="utf-8")
        return df
    except Exception as e:
        print(f"[DataManager] Error reading forecast log: {e}")
        return None


def load_forecast_history() -> pd.DataFrame | None:
    """Loads forecast_history.csv (cumulative history max 2500) if it exists, otherwise None."""
    if not FORECAST_HISTORY_PATH.exists():
        return None
    try:
        df = pd.read_csv(FORECAST_HISTORY_PATH, encoding="utf-8")
        return df
    except Exception as e:
        print(f"[DataManager] Error reading forecast history: {e}")
        return None


def get_last_run_info() -> str:
    """Returns info on the last execution from the log."""
    df = load_forecast_log()
    if df is None or df.empty:
        return "No previous analysis found."
    run_date = df["run_date"].iloc[0] if "run_date" in df.columns else "N/A"
    n = len(df)
    return f"Last run: {run_date} | Assets analyzed: {n}"


def save_pm_history(results: list[dict]):
    """Saves Pattern Matching history in JSON."""
    ensure_dirs()
    try:
        with open(PM_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
    except Exception as e:
        print(f"[DataManager] Error saving PM history: {e}")


def load_pm_history() -> list[dict]:
    """Loads Pattern Matching history."""
    if not PM_HISTORY_PATH.exists():
        return []
    try:
        with open(PM_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[DataManager] Error reading PM history: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Market Lists — saving and loading asset lists by market type
# ─────────────────────────────────────────────────────────────────────────────

MARKET_LIST_FILES = {
    "crypto": "market_list_crypto.json",
}


def save_market_list(market_type: str, asset_list: list[dict]):
    """
    Saves the asset list to a JSON file, accumulating up to 50 historical positions (log).
    """
    ensure_dirs()
    filename = MARKET_LIST_FILES.get(market_type)
    if not filename:
        print(f"[DataManager] Unknown market type: {market_type}")
        return
    path = MARKET_LISTS_DIR / filename
    
    # Load existing history
    existing = []
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
        except Exception:
            existing = []
            
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    # Create new records
    new_records = []
    for asset in asset_list:
        # If the asset already has 'updated_at', do not overwrite or insert again if it is already present
        # at the head. This prevents duplications if asset_list already contains historical records.
        if "updated_at" in asset:
            new_records = asset_list
            break
        rec = asset.copy()
        rec["updated_at"] = now_str
        new_records.append(rec)
        
    if new_records != asset_list:
        # We added new records, so we prepend them
        combined = new_records + existing
    else:
        # We are saving the already historical list
        combined = new_records

    # Keep only the first 50
    combined = combined[:50]
    
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2, default=str)
        print(f"[DataManager] List {market_type} saved: {len(combined)} records in log → {path}")
    except Exception as e:
        print(f"[DataManager] Error saving list {market_type}: {e}")


def load_market_list(market_type: str) -> list[dict]:
    """
    Loads the asset list of a market type from the JSON file.
    Returns empty list if it does not exist or in case of error.
    """
    ensure_dirs()
    btc_default = [{"symbol": "BTC", "name": "Bitcoin", "coingecko_id": "bitcoin", "rank": 1}]
    filename = MARKET_LIST_FILES.get(market_type)
    if not filename:
        return btc_default
    path = MARKET_LISTS_DIR / filename
    if not path.exists():
        return btc_default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Force only BTC if there are others
            btc_only = [item for item in data if item.get("symbol") == "BTC"]
            return btc_only if btc_only else btc_default
    except Exception as e:
        print(f"[DataManager] Error reading list {market_type}: {e}")
        return btc_default


def delete_market_list(market_type: str):
    """Deletes the market list file (for refresh)."""
    filename = MARKET_LIST_FILES.get(market_type)
    if not filename:
        return
    path = MARKET_LISTS_DIR / filename
    if path.exists():
        try:
            path.unlink()
            print(f"[DataManager] List {market_type} deleted.")
        except Exception as e:
            print(f"[DataManager] Error deleting list {market_type}: {e}")


def get_market_list_info(market_type: str) -> str:
    """Returns info on the saved market list."""
    filename = MARKET_LIST_FILES.get(market_type)
    if not filename:
        return "Unknown type."
    path = MARKET_LISTS_DIR / filename
    if not path.exists():
        return "List not available. Click 'Update Lists'."
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        data = load_market_list(market_type)
        return f"{len(data)} assets | Updated: {mtime.strftime('%d/%m/%Y %H:%M')}"
    except Exception:
        return "Error reading list."


# ─────────────────────────────────────────────────────────────────────────────
# Auto Trading Logs — logs of automatic executions
# ─────────────────────────────────────────────────────────────────────────────

def save_autotrading_log(run_log: dict):
    """
    Appends an automatic execution log to the list.
    run_log: { "start_time", "end_time", "duration", "status", "details" }
    """
    ensure_dirs()
    logs = load_autotrading_logs()
    logs.append(run_log)
    if len(logs) > 50:
        logs = logs[-50:]
    try:
        with open(AUTOTRADING_LOGS_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, default=str)
    except Exception as e:
        print(f"[DataManager] Error saving autotrading log: {e}")


def load_autotrading_logs() -> list[dict]:
    """Loads the history of automatic runs."""
    ensure_dirs()
    if not AUTOTRADING_LOGS_PATH.exists():
        return []
    try:
        with open(AUTOTRADING_LOGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[DataManager] Error reading autotrading log: {e}")
        return []
