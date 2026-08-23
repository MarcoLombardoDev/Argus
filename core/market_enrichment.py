# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

import yfinance as yf
import pandas as pd
import numpy as np
import requests

def get_market_context(symbol: str, is_crypto: bool = True) -> dict:
    """
    Calculates the Crypto Market Regime and Correlation between an asset and BTC.
    - Fixed Benchmark: BTC-USD
    - Proxy Dominance: 30-day momentum comparison between BTC-USD and ^CMC200
    - Regimes: ALTSEASON, BTC_ACCUMULATION, CRYPTO_WINTER
    """
    benchmark_symbol = "BTC-USD"
    alt_proxy_symbol = "ETH-USD"
    ticker_sym = f"{symbol.upper()}-USD"

    # Fetch Fear & Greed Index first: it is independent of the price downloads,
    # so a benchmark failure must not discard it.
    fng_value = 50
    fng_class = "Neutral"
    try:
        fng_resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        fng_resp.raise_for_status()
        fng_data = fng_resp.json()["data"][0]
        fng_value = int(fng_data["value"])
        fng_class = fng_data["value_classification"]
    except Exception as e:
        print(f"[MarketEnrichment] Fallback FNG: Error {e}")

    try:
        # 1. Download Benchmark (BTC) and Altcoin proxy (ETH) data - 1h for 7 days
        bench_data = yf.download(benchmark_symbol, period="7d", interval="1h", progress=False)
        alt_data = yf.download(alt_proxy_symbol, period="7d", interval="1h", progress=False)

        if bench_data is None or bench_data.empty:
            raise ValueError(f"No data found for benchmark: {benchmark_symbol}")

        bench_close = bench_data['Close']
        if isinstance(bench_close, pd.DataFrame): bench_close = bench_close.squeeze()
        bench_close = bench_close.dropna()

        # The alt proxy is optional: without it we simply cannot infer dominance.
        if alt_data is not None and not alt_data.empty and 'Close' in alt_data:
            alt_close = alt_data['Close']
            if isinstance(alt_close, pd.DataFrame): alt_close = alt_close.squeeze()
            alt_close = alt_close.dropna()
        else:
            print(f"[MarketEnrichment] Alt proxy {alt_proxy_symbol} unavailable — dominance unknown.")
            alt_close = pd.Series(dtype="float64")

        if len(bench_close) < 24:
            raise ValueError(f"Not enough data to calculate VWAP for benchmark: {benchmark_symbol}")

        # 2. Calculation of Intraday VWAP (Volume Weighted Average Price) on hourly basis for BTC
        high = bench_data['High'].squeeze() if isinstance(bench_data['High'], pd.DataFrame) else bench_data['High']
        low = bench_data['Low'].squeeze() if isinstance(bench_data['Low'], pd.DataFrame) else bench_data['Low']
        close = bench_data['Close'].squeeze() if isinstance(bench_data['Close'], pd.DataFrame) else bench_data['Close']
        vol = bench_data['Volume'].squeeze() if isinstance(bench_data['Volume'], pd.DataFrame) else bench_data['Volume']
        
        typical_price = (high + low + close) / 3
        # Use rolling 24h to approximate daily intraday VWAP
        cum_pv = (typical_price * vol).rolling(window=24, min_periods=1).sum()
        cum_vol = vol.rolling(window=24, min_periods=1).sum()
        vwap = cum_pv / cum_vol
        
        last_vwap = vwap.iloc[-1]
        last_bench_price = bench_close.iloc[-1]
        
        # 3. Calculation of Proxy Bitcoin Dominance Momentum (24 Hours)
        dominance_trend = "UNKNOWN"
        btc_24h_ret = 0.0
        alt_24h_ret = 0.0
        
        if len(bench_close) >= 24 and len(alt_close) >= 24:
            btc_24h_ret = (last_bench_price - bench_close.iloc[-24]) / bench_close.iloc[-24]
            last_alt_price = alt_close.iloc[-1]
            alt_24h_ret = (last_alt_price - alt_close.iloc[-24]) / alt_close.iloc[-24]
            
            if btc_24h_ret > alt_24h_ret:
                dominance_trend = "UP (Increasing)"
            else:
                dominance_trend = "DOWN (Decreasing)"
                
        # 4. Definition of Crypto Regime (based on intraday VWAP)
        if last_bench_price > last_vwap:
            if dominance_trend == "DOWN (Decreasing)":
                regime = "ALTSEASON"
            else:
                regime = "BTC_ACCUMULATION"
        else:
            regime = "CRYPTO_WINTER / BEARISH"

        # 5. Calculation of Correlation between Asset and BTC
        correlation = np.nan
        if ticker_sym == benchmark_symbol:
            correlation = 1.0
        else:
            ticker_data = yf.download(ticker_sym, period="7d", interval="1h", progress=False)
            if ticker_data.empty:
                ticker_data = yf.download(symbol.upper(), period="7d", interval="1h", progress=False)
                
            if not ticker_data.empty:
                ticker_close = ticker_data['Close']
                if isinstance(ticker_close, pd.DataFrame): ticker_close = ticker_close.squeeze()
                ticker_close = ticker_close.dropna()
                
                bench_returns = bench_close.pct_change().dropna()
                ticker_returns = ticker_close.pct_change().dropna()
                
                aligned_data = pd.concat([bench_returns, ticker_returns], axis=1, join='inner').dropna()
                aligned_data.columns = ['bench', 'ticker']
                
                if len(aligned_data) >= 30:
                    corr_series = aligned_data['ticker'].rolling(window=30).corr(aligned_data['bench'])
                    correlation = corr_series.iloc[-1]

        # 6. Output preparation
        corr_str = "N/A" if pd.isna(correlation) else f"{correlation:.2f}"
        
        summary = (
            f"MACRO CRYPTO CONTEXT:\n"
            f"- Benchmark (BTC) vs VWAP (24h): {'ABOVE' if last_bench_price > last_vwap else 'BELOW'}\n"
            f"- BTC 24h Return: {btc_24h_ret*100:.1f}%\n"
            f"- ETH (Alt Proxy) 24h Return: {alt_24h_ret*100:.1f}%\n"
            f"- BTC Dominance Momentum (24h proxy): {dominance_trend}\n"
            f"- MARKET REGIME: {regime}\n"
            f"- 24h Correlation with BTC: {corr_str}"
        )

        return {
            "benchmark": benchmark_symbol,
            "regime": regime,
            "correlation": float(correlation) if not pd.isna(correlation) else None,
            "fng_value": fng_value,
            "fng_class": fng_class,
            "summary": summary
        }

    except Exception as e:
        if "No data found for ticker" in str(e):
            raise
        print(f"[MarketEnrichment] Fallback: Error calculating macro context for {symbol}: {e}")
        # Keep the key set identical to the success path so callers can rely on
        # market_context["fng_value"] / ["fng_class"] existing. The Fear & Greed
        # reading is fetched independently above, so report the real value even
        # when the price download failed.
        return {
            "benchmark": benchmark_symbol,
            "regime": "UNKNOWN",
            "correlation": None,
            "fng_value": fng_value,
            "fng_class": fng_class,
            "summary": (
                "MACRO CRYPTO CONTEXT: Error calculating data. Assume NEUTRAL regime.\n"
                f"- FEAR & GREED INDEX: {fng_value} ({fng_class})"
            ),
        }
