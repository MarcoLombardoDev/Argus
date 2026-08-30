# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
data_fetcher.py — Argus
Downloads top-N crypto list from CoinGecko (Yahoo fallback) and historical data.
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
YAHOO_SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"

# Local mapping dictionary for top cryptos to support fallback from Yahoo to CoinGecko
SYMBOL_TO_COINGECKO_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "BNB": "binancecoin",
    "SOL": "solana",
    "USDC": "usd-coin",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "TRX": "tron",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "SHIB": "shiba-inu",
    "XLM": "stellar",
    "UNI": "uniswap",
    "LEO": "unus-sed-leo",
    "ETC": "ethereum-classic",
    "TON": "the-open-network",
    "NEAR": "near",
    "XMR": "monero",
    "OKB": "okb",
    "ICP": "internet-computer",
    "IMX": "immutable-x",
    "FIL": "filecoin",
    "HBAR": "hedera-hashgraph",
    "LDO": "lido-finance",
    "APT": "aptos",
    "VET": "vechain",
    "OP": "optimism",
    "RNDR": "render-token",
    "GRT": "the-graph",
    "INJ": "injective-protocol",
    "STX": "blockstack",
    "THETA": "theta-token",
    "MKR": "maker",
    "EGLD": "elrond-erd-2",
    "SUI": "sui",
    "TIA": "celestia",
    "FTM": "fantom",
    "AAVE": "aave",
    "FLOW": "flow",
    "ALGO": "algorand",
    "QNT": "quant-network",
}


def get_coingecko_request_args(url_path: str, params: dict, api_key: str, api_plan: str) -> tuple[str, dict, dict]:
    """
    Builds the complete URL, parameters, and headers for the CoinGecko request.
    Supports both Demo and Pro API Keys.
    """
    base_url = "https://api.coingecko.com/api/v3"
    headers = {}

    if api_key:
        if api_plan.lower() == "pro":
            base_url = "https://pro-api.coingecko.com/api/v3"
            headers["x-cg-pro-api-key"] = api_key
        else:
            base_url = "https://api.coingecko.com/api/v3"
            headers["x-cg-demo-api-key"] = api_key

    url = f"{base_url}/{url_path.lstrip('/')}"
    return url, params, headers


def make_coingecko_request(url_path: str, params: dict, api_key: str, api_plan: str) -> requests.Response:
    """
    Executes a request to CoinGecko, trying with the other plan
    in case of authentication error (401/403) to auto-detect demo/pro.
    """
    url, final_params, headers = get_coingecko_request_args(url_path, params, api_key, api_plan)
    resp = requests.get(url, params=final_params, headers=headers, timeout=15)

    if resp.status_code in (401, 403) and api_key:
        other_plan = "pro" if api_plan.lower() == "demo" else "demo"
        print(f"[DataFetcher] CoinGecko request failed with {resp.status_code} using plan '{api_plan}'. Retrying with '{other_plan}'...")
        alt_url, alt_params, alt_headers = get_coingecko_request_args(url_path, params, api_key, other_plan)
        alt_resp = requests.get(alt_url, params=alt_params, headers=alt_headers, timeout=15)
        if alt_resp.status_code == 200:
            print(f"[DataFetcher] Success with plan '{other_plan}'! Saving configuration...")
            try:
                from core.data_manager import load_settings, save_settings
                settings = load_settings()
                settings["coingecko_api_plan"] = other_plan
                save_settings(settings)
            except Exception as e:
                print(f"[DataFetcher] Failed to save auto-detected plan: {e}")
            return alt_resp

    return resp


def download_historical_coingecko(coingecko_id: str, days: int = 45, api_key: str = "", api_plan: str = "demo") -> pd.DataFrame | None:
    """Downloads historical data from CoinGecko with retry on rate limit (429)."""
    params = {
        "vs_currency": "usd",
        "days": str(days),
    }

    max_retries = 2  # Maximum of 2 attempts in total (so 1 initial attempt + 1 retry)
    backoff = 2.0
    resp = None

    for attempt in range(max_retries):
        try:
            resp = make_coingecko_request(f"coins/{coingecko_id}/market_chart", params, api_key, api_plan)
            if resp.status_code == 429:
                sleep_time = backoff ** (attempt + 1)
                print(f"[DataFetcher] CoinGecko rate limit (429) for {coingecko_id}. Waiting {sleep_time}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(sleep_time)
                continue
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(1)
    else:
        if resp is not None:
            resp.raise_for_status()

    data = resp.json()
    prices = data.get("prices", [])
    if not prices:
        return None

    df = pd.DataFrame(prices, columns=["Date", "Close"])
    df["Date"] = pd.to_datetime(df["Date"], unit="ms")
    df.set_index("Date", inplace=True)

    # Create compatible columns
    df["Open"] = df["Close"]
    df["High"] = df["Close"]
    df["Low"] = df["Close"]
    df["Volume"] = 0.0

    volumes = data.get("total_volumes", [])
    if volumes and len(volumes) == len(prices):
        df["Volume"] = [v[1] for v in volumes]

    df.index.name = "Date"
    return df


def download_historical_yahoo(symbol: str, days: int = 45) -> pd.DataFrame | None:
    """Downloads historical data from Yahoo Finance (yfinance) at 15-minute intervals."""
    ticker = f"{symbol.upper()}-USD"

    # yfinance supports the 15m interval for a maximum of 60 days, so days=45 or 30 is fine.
    df = yf.download(
        ticker,
        period=f"{days}d",
        interval="15m",
        auto_adjust=True,
        progress=False,
    )
    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if "Close" not in df.columns:
        return None

    # Keep only the OHLCV columns that Yahoo actually returned.
    wanted = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    df = df[wanted].copy()
    df = df.dropna(subset=["Close"])
    if df.empty:
        return None
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    return df


def download_historical_exchange(symbol: str, exchange, days: int = 45) -> pd.DataFrame | None:
    """
    Downloads 15-minute OHLCV data from the exchange via CCXT.
    Tries the most common symbol formats (spot and USDT perpetuals).
    Returns a DataFrame with columns [Open, High, Low, Close, Volume] or None.
    """
    if exchange is None:
        return None
    # Order of preference: USDT perpetual, USDT spot, USD spot
    candidates = [
        f"{symbol.upper()}/USDT:USDT",
        f"{symbol.upper()}/USDT",
        f"{symbol.upper()}/USD",
    ]
    # Limit to available candles: CCXT fetch_ohlcv returns at most N candles
    # 45 days in 15m candles = 4320. We use limit = 1000 since the last 96 are sufficient for TimesFM.
    limit = 1000
    markets = getattr(exchange, "markets", None) or {}
    for sym_candidate in candidates:
        if markets and sym_candidate not in markets:
            continue
        try:
            ohlcv = exchange.fetch_ohlcv(sym_candidate, timeframe="15m", limit=limit)
            if not ohlcv or len(ohlcv) < 30:
                continue
            df = pd.DataFrame(ohlcv, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
            df["Date"] = pd.to_datetime(df["Date"], unit="ms")
            df.set_index("Date", inplace=True)
            df = df.dropna(subset=["Close"])
            df.index.name = "Date"
            print(f"[DataFetcher] Exchange OHLCV OK for {symbol} ({sym_candidate}): {len(df)} candles.")
            return df
        except Exception as e:
            print(f"[DataFetcher] Exchange OHLCV failed for {symbol} ({sym_candidate}): {e}")
            continue
    return None


def fetch_historical_paginated(exchange, symbol: str, timeframe: str = "30m", days: int = 365) -> pd.DataFrame | None:
    """
    Downloads long historical data by paginating fetch_ohlcv calls (useful for 12 months of 30m data).
    """
    if exchange is None:
        return None

    # Find the correct symbol
    candidates = [f"{symbol.upper()}/USDT:USDT", f"{symbol.upper()}/USDT", f"{symbol.upper()}/USD"]
    markets = getattr(exchange, "markets", None) or {}
    if not markets:
        try:
            exchange.load_markets()
            markets = exchange.markets
        except Exception:
            return None

    target_sym = None
    for sym in candidates:
        if sym in markets:
            target_sym = sym
            break

    if not target_sym:
        return None

    # Calculate start timestamp
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    limit = 1000
    all_ohlcv = []

    print(f"[DataFetcher] Starting CCXT pagination for {target_sym} ({days} days, {timeframe})...")

    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(target_sym, timeframe=timeframe, since=start_time, limit=limit)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            # Advance start_time to the last received candle + 1ms
            last_time = ohlcv[-1][0]
            if last_time <= start_time:
                break
            start_time = last_time + 1
            time.sleep(0.1)  # Anti rate-limit
        except Exception as e:
            print(f"[DataFetcher] Error during CCXT pagination: {e}")
            break

    if not all_ohlcv:
        return None

    df = pd.DataFrame(all_ohlcv, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"], unit="ms")
    df.set_index("Date", inplace=True)

    # Remove any duplicates
    df = df[~df.index.duplicated(keep='last')]
    df = df.dropna(subset=["Close"])
    df.index.name = "Date"
    print(f"[DataFetcher] CCXT pagination completed: {len(df)} candles downloaded.")
    return df


def download_historical(
    symbol: str,
    coingecko_id: str | None = None,
    days: int = 45,
    api_key: str = "",
    api_plan: str = "demo",
    exchange=None,
    progress_callback=None,
) -> pd.DataFrame | None:
    """
    Downloads historical hourly OHLCV data.
    Priority order: Exchange (CCXT) → CoinGecko → Yahoo Finance.
    """
    # 1. Try Exchange via CCXT (zero API cost, real-time data)
    if exchange is not None:
        try:
            df = download_historical_exchange(symbol, exchange, days)
            if df is not None and len(df) >= 30:
                return df
        except Exception as e:
            print(f"[DataFetcher] Exchange history failed for {symbol}: {e}")

    # 2. Try CoinGecko (if API key is configured)
    if coingecko_id and api_key:
        try:
            df = download_historical_coingecko(coingecko_id, days, api_key, api_plan)
            if df is not None and len(df) >= 30:
                return df
        except Exception as e:
            print(f"[DataFetcher] CoinGecko failed for {symbol}: {e}")
            if progress_callback:
                progress_callback(f"⚠️ CoinGecko failed for {symbol}, trying Yahoo...")
    elif not api_key and coingecko_id:
        print(f"[DataFetcher] CoinGecko API key not configured for {symbol}. Skipping to Yahoo.")

    # 3. Final fallback: Yahoo Finance
    try:
        df = download_historical_yahoo(symbol, days)
        if df is not None and len(df) >= 30:
            return df
    except Exception as e:
        print(f"[DataFetcher] Yahoo failed for {symbol}: {e}")

    return None


def download_all_historical(
    crypto_list: list[dict],
    days: int = 45,
    api_key: str = "",
    api_plan: str = "demo",
    exchange=None,
    progress_callback=None,
    stop_flag=None,
) -> dict[str, pd.DataFrame]:
    """
    Downloads historical data for all cryptos in the list.
    Priority order per asset: Exchange (CCXT) → CoinGecko → Yahoo Finance.
    """
    results = {}
    total = len(crypto_list)
    counts = {"exchange": 0, "coingecko": 0, "yahoo": 0, "failed": 0}

    # Pre-load exchange markets once (avoids N load_markets calls)
    if exchange is not None:
        try:
            if not getattr(exchange, "markets", None):
                exchange.load_markets()
        except Exception as e:
            print(f"[DataFetcher] Unable to load exchange markets: {e}")
            exchange = None  # Disable exchange if not reachable

    for i, coin in enumerate(crypto_list):
        if stop_flag and stop_flag():
            break

        symbol = coin["symbol"]
        name = coin["name"]
        coingecko_id = coin.get("coingecko_id")
        msg = f"History {i+1}/{total}: {name} ({symbol})"
        if progress_callback:
            progress_callback(msg, i / total)

        # --- Attempt 1: Exchange ---
        df = None
        if exchange is not None:
            df = download_historical_exchange(symbol, exchange, days)
            if df is not None and len(df) >= 30:
                counts["exchange"] += 1

        # --- Attempt 2: CoinGecko ---
        if df is None and coingecko_id and api_key:
            try:
                df = download_historical_coingecko(coingecko_id, days, api_key, api_plan)
                if df is not None and len(df) >= 30:
                    counts["coingecko"] += 1
                else:
                    df = None
            except Exception as e:
                print(f"[DataFetcher] CoinGecko failed for {symbol}: {e}")
                df = None
            # Rate limit CoinGecko only if actually used
            time.sleep(0.3)

        # --- Attempt 3: Yahoo Finance ---
        if df is None:
            try:
                df = download_historical_yahoo(symbol, days)
                if df is not None and len(df) >= 30:
                    counts["yahoo"] += 1
                else:
                    df = None
            except Exception as e:
                print(f"[DataFetcher] Yahoo failed for {symbol}: {e}")
                df = None

        if df is not None:
            results[symbol] = df
        else:
            counts["failed"] += 1
            print(f"[DataFetcher] ⚠️ No sources available for {symbol}.")

        # Minimum pause only if not using exchange (which has no rate limit)
        if exchange is None or symbol not in results:
            time.sleep(0.1)

    print(
        f"[DataFetcher] History download completed: "
        f"Exchange={counts['exchange']} | CoinGecko={counts['coingecko']} | "
        f"Yahoo={counts['yahoo']} | Failed={counts['failed']}"
    )
    return results


def update_crypto_prices(
    crypto_list: list[dict],
    api_key: str = "",
    api_plan: str = "demo",
    progress_callback=None,
) -> list[dict]:
    """
    Updates only the current price of cryptos in the list, preserving other fields.
    """
    updated_list = [item.copy() for item in crypto_list]
    total = len(updated_list)
    if not updated_list:
        return updated_list

    # Try CoinGecko if key is present
    if api_key:
        coingecko_ids = [item.get("coingecko_id") for item in updated_list if item.get("coingecko_id")]
        if coingecko_ids:
            try:
                if progress_callback:
                    progress_callback("📡 Updating crypto prices from CoinGecko...", 0.1)

                params = {
                    "vs_currency": "usd",
                    "ids": ",".join(coingecko_ids),
                    "order": "market_cap_desc",
                    "per_page": 250,
                    "page": 1,
                    "sparkline": "false",
                }
                resp = make_coingecko_request("coins/markets", params, api_key, api_plan)
                resp.raise_for_status()
                data = resp.json()

                price_map = {item.get("id"): (item.get("current_price"), item.get("price_change_percentage_24h")) for item in data}
                for item in updated_list:
                    cg_id = item.get("coingecko_id")
                    if cg_id in price_map and price_map[cg_id][0] is not None:
                        item["current_price"] = float(price_map[cg_id][0])
                        item["price_change_pct"] = float(price_map[cg_id][1] or 0.0)

                if progress_callback:
                    progress_callback("✅ Crypto prices updated from CoinGecko.", 1.0)
                return updated_list
            except Exception as e:
                print(f"[DataFetcher] Error updating CoinGecko prices: {e}")
                if progress_callback:
                    progress_callback("⚠️ CoinGecko error, using Yahoo Finance fallback...", 0.2)

    # Fallback on Yahoo Finance
    for i, item in enumerate(updated_list):
        symbol = item.get("symbol", "")
        if progress_callback:
            progress_callback(f"📡 Updating Yahoo price {i+1}/{total}: {symbol}", (i/total))
        try:
            ticker = f"{symbol.upper()}-USD"
            tk = yf.Ticker(ticker)
            price = getattr(tk.fast_info, "last_price", None)
            prev_close = getattr(tk.fast_info, "previous_close", None)
            if price and price > 0:
                item["current_price"] = float(price)
                if prev_close:
                    item["price_change_pct"] = (price - prev_close) / prev_close * 100.0
        except Exception as e:
            print(f"[DataFetcher] Yahoo price error for {symbol}: {e}")
        time.sleep(0.2)  # small pause for rate limiting

    if progress_callback:
        progress_callback("✅ Crypto prices updated.", 1.0)
    return updated_list


# ---------------------------------------------------------------------------
# ETH/BTC Ratio — Exchange (CCXT) with CoinGecko Fallback
# ---------------------------------------------------------------------------

def fetch_eth_btc_ratio_exchange(pm_exchange, days: int = 30) -> "pd.DataFrame | None":
    """
    Downloads OHLCV of the ETH/BTC pair from the configured exchange via the authenticated CCXT instance.
    Returns a DataFrame with columns [Open, High, Low, Close, Volume]
    indexed by date, where Close = ETH price expressed in BTC.
    """
    try:
        if pm_exchange is None:
            return None
        exchange_id = getattr(pm_exchange, "id", "Exchange").upper()
        # Verify that the pair is supported
        markets = pm_exchange.load_markets() if not pm_exchange.markets else pm_exchange.markets
        candidate_symbols = ["ETH/BTC", "ETH/BTC:BTC", "ETHBTC"]
        symbol_used = None
        for s in candidate_symbols:
            if s in markets:
                symbol_used = s
                break
        if symbol_used is None:
            print(f"[DataFetcher] ETH/BTC not found on {exchange_id} markets.")
            return None

        # Download daily candles
        limit = min(days + 5, 1000)
        ohlcv = pm_exchange.fetch_ohlcv(symbol_used, timeframe="1d", limit=limit)
        if not ohlcv:
            return None

        df = pd.DataFrame(ohlcv, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["Date"], unit="ms")
        df.set_index("Date", inplace=True)
        df = df.tail(days)
        print(f"[DataFetcher] ETH/BTC downloaded from {exchange_id} ({symbol_used}): {len(df)} candles.")
        return df
    except Exception as e:
        print(f"[DataFetcher] fetch_eth_btc_ratio_exchange failed: {e}")
        return None


def fetch_eth_btc_ratio_coingecko(days: int = 30, api_key: str = "", api_plan: str = "demo") -> "pd.DataFrame | None":
    """
    Calculates the ETH/BTC ratio by separately downloading the historical prices of
    ETH and BTC from CoinGecko and dividing Close_ETH / Close_BTC.
    """
    try:
        df_eth = download_historical_coingecko("ethereum", days=days, api_key=api_key, api_plan=api_plan)
        time.sleep(1.5)  # anti rate-limit
        df_btc = download_historical_coingecko("bitcoin",  days=days, api_key=api_key, api_plan=api_plan)

        if df_eth is None or df_btc is None:
            return None

        # Align on the same indexes
        df_eth = df_eth["Close"].rename("eth")
        df_btc = df_btc["Close"].rename("btc")
        merged = pd.concat([df_eth, df_btc], axis=1).dropna()

        if merged.empty:
            return None

        ratio = merged["eth"] / merged["btc"]
        df_ratio = ratio.rename("Close").to_frame()
        df_ratio["Open"]   = df_ratio["Close"]
        df_ratio["High"]   = df_ratio["Close"]
        df_ratio["Low"]    = df_ratio["Close"]
        df_ratio["Volume"] = 0.0
        print(f"[DataFetcher] ETH/BTC ratio calculated from CoinGecko: {len(df_ratio)} points.")
        return df_ratio
    except Exception as e:
        print(f"[DataFetcher] fetch_eth_btc_ratio_coingecko failed: {e}")
        return None


def fetch_eth_btc_ratio(
    pm_exchange=None,
    days: int = 30,
    api_key: str = "",
    api_plan: str = "demo",
) -> "pd.DataFrame | None":
    """
    Returns the ETH/BTC ratio as a DataFrame (Close = ETH price in BTC).
    Tries the exchange via CCXT first, then falls back to CoinGecko.
    """
    # Attempt 1: Configured exchange
    df = fetch_eth_btc_ratio_exchange(pm_exchange, days=days)
    if df is not None and not df.empty:
        return df

    # Fallback: CoinGecko
    print("[DataFetcher] CoinGecko fallback for ETH/BTC ratio...")
    return fetch_eth_btc_ratio_coingecko(days=days, api_key=api_key, api_plan=api_plan)


def fetch_order_book_imbalance(exchange, symbol: str, limit: int = 20) -> float | None:
    """
    Downloads the Order Book from the exchange and calculates the percentage imbalance between Bid and Ask.
    Returns a float between -100.0 (totally Ask) and +100.0 (totally Bid).
    Returns None in case of error.
    """
    if exchange is None:
        return None
    try:
        # Use first valid symbol
        candidates = [f"{symbol.upper()}/USDT:USDT", f"{symbol.upper()}/USDT", f"{symbol.upper()}/USD"]
        markets = getattr(exchange, "markets", None) or {}
        if not markets:
            exchange.load_markets()
            markets = exchange.markets

        target_sym = None
        for sym in candidates:
            if sym in markets:
                target_sym = sym
                break

        if not target_sym:
            return None

        ob = exchange.fetch_order_book(target_sym, limit=limit)
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])

        if not bids and not asks:
            return 0.0

        # Calculate total volume (price * quantity) in the first limit levels.
        # CCXT levels are [price, amount] but some venues append extra fields,
        # so index explicitly instead of tuple-unpacking.
        vol_bids = sum(float(lvl[0]) * float(lvl[1]) for lvl in bids[:limit] if len(lvl) >= 2)
        vol_asks = sum(float(lvl[0]) * float(lvl[1]) for lvl in asks[:limit] if len(lvl) >= 2)


        total_vol = vol_bids + vol_asks
        if total_vol == 0:
            return 0.0

        imbalance_pct = ((vol_bids - vol_asks) / total_vol) * 100.0
        return imbalance_pct

    except Exception as e:
        print(f"[DataFetcher] Unable to download Order Book for {symbol}: {e}")
        return None
