"""
ai_analyst.py — Argus
Multi-agent AI analysis engine focused on the cryptocurrency market.

Agent pipeline for each asset:
  1. MarketAnalyst       → technical analysis (price, volume, trend)
  2. NewsAnalyst         → sentiment from Investing.com (scraper) with Yahoo Finance fallback
  3. FundamentalsAnalyst → fundamentals adapted to asset type (crypto metrics OR equity metrics)
  4. BullResearcher      → bullish arguments synthesised from prior analyses
  5. BearResearcher      → bearish arguments / risks synthesised from prior analyses
  6. PortfolioManager    → final decision with 1d/3d price targets and BUY/SELL/HOLD signals

Compatible with OpenRouter, OpenAI and Ollama (OpenAI-compatible endpoints).
"""

import json
import re
import time
import requests
from datetime import datetime, timedelta
from typing import Callable, Optional
from openai import OpenAI


# ─────────────────────────────────────────────────────────────
# Provider Constants
# ─────────────────────────────────────────────────────────────

PROVIDER_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "claude":     "https://api.anthropic.com/v1",
    "openai":     "https://api.openai.com/v1",
    "ollama":     "http://localhost:11434/v1",
}

OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/MarcoLombardoDev/Argus",
    "X-Title": "Argus Crypto Analyst",
}

# Suggested models per provider
SUGGESTED_MODELS = {
    "openrouter": [
        "anthropic/claude-3-haiku",
        "anthropic/claude-3-5-sonnet",
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "google/gemini-flash-1.5",
        "meta-llama/llama-3.1-8b-instruct:free",
    ],
    "claude": [
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
    "ollama": [
        "llama3.1",
        "mistral",
        "gemma2",
    ],
}


# ─────────────────────────────────────────────────────────────
# Additional Data Fetching
# ─────────────────────────────────────────────────────────────

def _fetch_coingecko_details(symbol: str, api_key: str = "", api_plan: str = "demo") -> dict:
    """Retrieves additional details from CoinGecko for a single crypto."""
    try:
        from core.data_fetcher import SYMBOL_TO_COINGECKO_MAP
        coin_id = SYMBOL_TO_COINGECKO_MAP.get(symbol.upper(), symbol.lower())
    except Exception:
        coin_id = symbol.lower()
    
    try:
        def do_req(plan):
            if plan.lower() == "pro" and api_key:
                base = "https://pro-api.coingecko.com/api/v3"
                params = {"x_cg_pro_api_key": api_key}
            else:
                base = "https://api.coingecko.com/api/v3"
                params = {}
                if api_key:
                    params["x_cg_demo_api_key"] = api_key

            url = f"{base}/coins/{coin_id}"
            params.update({
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            })
            return requests.get(url, params=params, timeout=10)

        resp = do_req(api_plan)
        if resp.status_code in (401, 403) and api_key:
            alt_plan = "pro" if api_plan.lower() == "demo" else "demo"
            print(f"[AIAnalyst] CoinGecko auth failed with plan '{api_plan}'. Retrying with '{alt_plan}'...")
            alt_resp = do_req(alt_plan)
            if alt_resp.status_code == 200:
                resp = alt_resp
                try:
                    from core.data_manager import load_settings, save_settings
                    settings = load_settings()
                    settings["coingecko_api_plan"] = alt_plan
                    save_settings(settings)
                    print(f"[AIAnalyst] Successfully auto-detected and saved plan '{alt_plan}'")
                except Exception as e:
                    print(f"[AIAnalyst] Failed to save auto-detected plan: {e}")

        if resp.status_code == 200:
            data = resp.json()
            md = data.get("market_data", {})
            return {
                "market_cap_rank": data.get("market_cap_rank"),
                "market_cap_usd": md.get("market_cap", {}).get("usd"),
                "volume_24h": md.get("total_volume", {}).get("usd"),
                "price_change_24h_pct": md.get("price_change_percentage_24h"),
                "price_change_7d_pct": md.get("price_change_percentage_7d"),
                "price_change_30d_pct": md.get("price_change_percentage_30d"),
                "ath": md.get("ath", {}).get("usd"),
                "ath_change_pct": md.get("ath_change_percentage", {}).get("usd"),
                "circulating_supply": md.get("circulating_supply"),
                "max_supply": md.get("max_supply"),
                "description": data.get("description", {}).get("en", "")[:300],
            }
    except Exception as e:
        print(f"[AIAnalyst] CoinGecko details error for {symbol}: {e}")
    return {}


def _fetch_yahoo_details(symbol: str, is_crypto: bool = False) -> dict:
    """Retrieves market details from Yahoo Finance.
    
    For crypto, uses the symbol SYMBOL-USD; for stock, uses the direct ticker.
    """
    try:
        import yfinance as yf
        ticker_sym = f"{symbol.upper()}-USD" if is_crypto else symbol.upper()
        ticker = yf.Ticker(ticker_sym)
        info = ticker.info
        price_found = info and not (info.get("regularMarketPrice") is None and info.get("currentPrice") is None and info.get("previousClose") is None)
        
        if not price_found and is_crypto:
            # Fallback: try without -USD suffix for poorly mapped cryptos
            ticker = yf.Ticker(symbol.upper())
            info = ticker.info
            price_found = info and not (info.get("regularMarketPrice") is None and info.get("currentPrice") is None and info.get("previousClose") is None)
            
        if not price_found:
            return {}
        
        # Estimate percentage changes from recent historical prices
        hist = ticker.history(period="30d", progress=False)
        if hist is None or hist.empty:
            return {}  # Force failure for delisted assets or missing data
            
        price_change_24h_pct = None
        price_change_7d_pct  = None
        price_change_30d_pct = None
        
        if len(hist) >= 2:
            close_prices = hist["Close"].tolist()
            last_price = close_prices[-1]
            price_change_24h_pct = ((last_price - close_prices[-2]) / close_prices[-2]) * 100
            if len(close_prices) >= 7:
                price_change_7d_pct = ((last_price - close_prices[-7]) / close_prices[-7]) * 100
            price_change_30d_pct = ((last_price - close_prices[0]) / close_prices[0]) * 100

        mcap = info.get("marketCap")
        vol  = info.get("volume24Hr") or info.get("volume") or info.get("regularMarketVolume")
        ath  = info.get("fiftyTwoWeekHigh") or info.get("52WeekHigh")

        # Stock-specific values (not present for crypto)
        pe_ratio   = info.get("trailingPE")
        eps        = info.get("trailingEps")
        div_yield  = info.get("dividendYield")
        sector     = info.get("sector", "")
        industry   = info.get("industry", "")
        description = (
            info.get("longBusinessSummary", "") or
            info.get("description", "")
        )[:400]

        return {
            "market_cap_rank": info.get("marketCapRank", "N/A"),
            "market_cap_usd": mcap,
            "volume_24h": vol,
            "price_change_24h_pct": price_change_24h_pct or info.get("regularMarketChangePercent"),
            "price_change_7d_pct":  price_change_7d_pct,
            "price_change_30d_pct": price_change_30d_pct,
            "ath": ath,
            "ath_change_pct": None,
            # Crypto-specific
            "circulating_supply": info.get("circulatingSupply") or info.get("supply"),
            "max_supply": info.get("maxSupply"),
            # Equity-specific
            "pe_ratio":  pe_ratio,
            "eps":       eps,
            "div_yield": div_yield,
            "sector":    sector,
            "industry":  industry,
            "description": description,
        }
    except Exception as e:
        print(f"[AIAnalyst] Yahoo details error for {symbol}: {e}")
    return {}


def _fetch_investing_news(symbol: str, name: str = "") -> list[str]:
    """
    Scrapes the most recent headlines from Investing.com searching by asset name/symbol.
    Uses the public search of Investing.com and parses the HTML results.
    Returns a list of headlines (strings).
    """
    try:
        search_term = name if name else symbol
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.investing.com/",
        }

        url = f"https://www.investing.com/search/?q={search_term}"
        resp = requests.get(url, headers=headers, timeout=10)
        headlines = []
        
        if resp.status_code == 200:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, 'html.parser')
                items = soup.find_all('div', class_='articleItem')
                for item in items:
                    title_el = item.find('a', class_='title')
                    if not title_el:
                        title_el = item.find('a')
                    if title_el:
                        href = title_el.get('href', '')
                        text = title_el.get_text().strip()
                        # Skip Vue templates or invalid links
                        if '{{' in text or '{{' in href:
                            continue
                        if '/news/' in href and text and len(text) > 8:
                            headlines.append(text)
            except Exception as e:
                print(f"[AIAnalyst] Investing.com BS4 parsing error for {symbol}: {e}")

        # If nothing is found, attempt to use the generic RSS feed as a filtered fallback
        if not headlines:
            rss_url = "https://www.investing.com/rss/news.rss"
            rss_resp = requests.get(rss_url, headers=headers, timeout=8)
            if rss_resp.status_code == 200:
                items = re.findall(r"<title><![CDATA[([^\]]+)\]\]></title>", rss_resp.text)
                if not items:
                    items = re.findall(r"<title>([^<]+)</title>", rss_resp.text)
                for title in items[1:]:
                    title = title.strip()
                    if title and len(title) > 10:
                        term_lower = search_term.lower()
                        if term_lower in title.lower() or symbol.lower() in title.lower():
                            headlines.append(title)

        return headlines[:3]
    except Exception as e:
        print(f"[AIAnalyst] Investing.com scraper error for {symbol}: {e}")
    return []


def _fetch_yahoo_news(symbol: str, is_crypto: bool = False) -> list[str]:
    """Retrieves news from Yahoo Finance (yfinance).
    
    For crypto, uses SYMBOL-USD; for stock, uses the direct ticker.
    Filters news from the last hour. If absent, returns at most 3 recent ones.
    """
    try:
        import yfinance as yf
        import pandas as pd
        from datetime import datetime, timezone
        
        ticker_sym = f"{symbol.upper()}-USD" if is_crypto else symbol.upper()
        ticker = yf.Ticker(ticker_sym)
        news_list = ticker.news
        if not news_list:
            return []
            
        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        recent_headlines = []
        all_headlines = []
        
        for item in news_list[:15]:
            content = item.get("content", {})
            h = (content.get("title", "") or item.get("title", "")).strip()
            
            if h:
                all_headlines.append(h)
                pub_date_str = content.get("pubDate")
                if pub_date_str:
                    try:
                        pub_dt = pd.to_datetime(pub_date_str, utc=True)
                        if (now_utc - pub_dt).total_seconds() <= 3600:
                            recent_headlines.append(h)
                    except Exception:
                        pass
        
        if recent_headlines:
            return recent_headlines
        else:
            return all_headlines[:3]
            
    except Exception as e:
        print(f"[AIAnalyst] Yahoo news error for {symbol}: {e}")
    return []


def _fetch_finnhub_news(symbol: str, api_key: str = "", is_crypto: bool = True) -> list[str]:
    """Retrieves the latest news from Finnhub.
    
    For crypto, uses BINANCE:SYMBOLUSDT endpoint.
    For stock, uses the direct ticker.
    """
    if not api_key:
        return []
    try:
        now = datetime.now()
        from_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        to_date   = now.strftime("%Y-%m-%d")

        if is_crypto:
            finnhub_sym = f"BINANCE:{symbol.upper()}USDT"
        else:
            finnhub_sym = symbol.upper()

        url    = "https://finnhub.io/api/v1/company-news"
        params = {"symbol": finnhub_sym, "from": from_date, "to": to_date, "token": api_key}
        resp   = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            import pandas as pd
            from datetime import timezone
            now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
            
            recent_headlines = []
            all_headlines = []
            
            for item in resp.json()[:15]:
                h = item.get("headline", "").strip()
                if h:
                    all_headlines.append(h)
                    pub_ts = item.get("datetime")
                    if pub_ts:
                        try:
                            # Finnhub datetime is UNIX timestamp in seconds
                            pub_dt = pd.to_datetime(pub_ts, unit='s', utc=True)
                            if (now_utc - pub_dt).total_seconds() <= 3600:
                                recent_headlines.append(h)
                        except Exception:
                            pass
                            
            if recent_headlines:
                return recent_headlines
            else:
                return all_headlines[:3]
    except Exception as e:
        print(f"[AIAnalyst] Finnhub news error for {symbol}: {e}")
    return []


# ─────────────────────────────────────────────────────────────
# Prompt Templates
# ─────────────────────────────────────────────────────────────

def _build_market_prompt(coin: dict, market_data: dict, market_type: str = "crypto") -> str:
    is_crypto = market_type.lower() == "crypto"
    vol  = market_data.get('volume_24h')
    mcap = market_data.get('market_cap_usd')
    ath  = market_data.get('ath')
    vol_str  = f"${vol:,.0f}"  if isinstance(vol,  (int, float)) else "N/A"
    mcap_str = f"${mcap:,.0f}" if isinstance(mcap, (int, float)) else "N/A"
    ath_label = "ATH" if is_crypto else "52-Week High"
    ath_str  = f"${ath:,.4f}"  if isinstance(ath,  (int, float)) else "N/A"

    asset_type_label = "cryptocurrency" if is_crypto else "stock/equity"

    return f"""You are the Market Analyst of Argus. Analyze the technical data for {coin['name']} ({coin['symbol']}), a {asset_type_label}.

AVAILABLE DATA:
- Current price: ${coin.get('last_price', 'N/A')}
- 24h Change: {market_data.get('price_change_24h_pct', 'N/A')}%
- 7d Change: {market_data.get('price_change_7d_pct', 'N/A')}%
- 30d Change: {market_data.get('price_change_30d_pct', 'N/A')}%
- 24h Volume: {vol_str}
- Market Cap: {mcap_str}
- {ath_label}: {ath_str}
- Order Book Imbalance (Bid vs Ask): {market_data.get('order_book_imbalance_pct', 0.0):.2f}% (positive = more Bid volume)
- Intraday (15m) Tech: {market_data.get('tech_indicators_15m', 'N/A')}

Provide a SHORT technical analysis (max 120 words) following this structure:
1. TREND IDENTIFICATION: Classify the intraday trend (next 1-2 hours) as UPTREND / DOWNTREND / RANGE-BOUND. Justify with the recent price action.
2. KEY LEVELS: Estimate support and resistance as specific price numbers (use % distance from {ath_label} and recent price action).
3. VOLUME ANALYSIS: Is volume confirming the trend? Compare 24h volume to market cap ratio for context.
4. VERDICT: BULLISH / BEARISH / NEUTRAL with a 2-hour price target (as a specific number and % change from current price).

IMPORTANT: Do NOT speculate on causes — focus purely on what the price data shows. Respond only with the analysis."""


def _build_news_prompt(coin: dict, news_headlines: list[str], market_type: str = "crypto") -> str:
    is_crypto = market_type.lower() == "crypto"
    asset_type_label = "cryptocurrency" if is_crypto else "stock"
    context_hint = (
        "Consider crypto-specific factors: regulatory news, exchange listings, on-chain activity, DeFi/NFT trends."
        if is_crypto else
        "Consider equity-specific factors: earnings reports, analyst upgrades/downgrades, macro events, sector news."
    )
    headlines_text = "\n".join(f"- {h}" for h in news_headlines) if news_headlines else "No news found."
    return f"""You are the News & Sentiment Analyst of Argus. Analyze the recent news sentiment for {coin['name']} ({coin['symbol']}), a {asset_type_label}.

LATEST NEWS (last 3 days — sourced from Investing.com / Yahoo Finance):
{headlines_text}

{context_hint}

Provide a SHORT analysis (max 100 words) following this structure:
1. SENTIMENT SCORE: Rate overall sentiment as POSITIVE / NEGATIVE / NEUTRAL.
2. FRESHNESS FILTER: Identify which headlines are likely ALREADY PRICED IN (>24h old or widely known) vs. potentially NEW catalysts (<24h or breaking).
3. IMPACT ASSESSMENT: For each key narrative, estimate whether it has HIGH / MEDIUM / LOW potential to move the price intraday (next 1-2 hours).
4. NET CONCLUSION: After discounting already-priced-in news, is the residual sentiment tilting POSITIVE / NEGATIVE / NEUTRAL?

If no headlines are available, derive sentiment from general market context for this {asset_type_label} and state your reasoning clearly — do NOT simply say 'insufficient data'.
Respond only with the analysis."""


def _build_fundamentals_prompt(coin: dict, market_data: dict, market_type: str = "crypto") -> str:
    is_crypto = market_type.lower() == "crypto"
    vol  = market_data.get('volume_24h')
    mcap = market_data.get('market_cap_usd')
    mcap_str = f"${mcap:,.0f}" if isinstance(mcap, (int, float)) else "N/A"

    if isinstance(vol, (int, float)) and isinstance(mcap, (int, float)) and mcap > 0:
        ratio_str = f"{vol / mcap * 100:.2f}%"
    else:
        ratio_str = "N/A"

    if is_crypto:
        circ_supply = market_data.get('circulating_supply')
        circ_str = f"{circ_supply:,.0f}" if isinstance(circ_supply, (int, float)) else "N/A"
        max_supply = market_data.get('max_supply')
        max_str  = f"{max_supply:,.0f}" if isinstance(max_supply, (int, float)) else "N/A"
        extra_data = (
            f"- Circulating Supply: {circ_str}\n"
            f"- Max Supply: {max_str}\n"
            f"- Volume/Market Cap Ratio: {ratio_str}"
        )
        analysis_focus = (
            "1. Network fundamentals and tokenomics strength\n"
            "2. Market liquidity and on-chain depth\n"
            "3. Scarcity/inflation dynamics impact on price\n"
            "4. Judgment: STRONG / MEDIUM / WEAK"
        )
    else:
        pe_ratio  = market_data.get('pe_ratio')
        eps       = market_data.get('eps')
        div_yield = market_data.get('div_yield')
        sector    = market_data.get('sector', 'N/A')
        industry  = market_data.get('industry', 'N/A')
        pe_str  = f"{pe_ratio:.2f}x" if isinstance(pe_ratio,  (int, float)) else "N/A"
        eps_str = f"${eps:.2f}"       if isinstance(eps,       (int, float)) else "N/A"
        dy_str  = f"{div_yield*100:.2f}%" if isinstance(div_yield, (int, float)) else "N/A"
        extra_data = (
            f"- Sector: {sector}\n"
            f"- Industry: {industry}\n"
            f"- P/E Ratio: {pe_str}\n"
            f"- EPS (TTM): {eps_str}\n"
            f"- Dividend Yield: {dy_str}\n"
            f"- Volume/Market Cap Ratio: {ratio_str}"
        )
        analysis_focus = (
            "1. Company financial health and valuation (P/E, EPS, div yield)\n"
            "2. Market liquidity and institutional interest\n"
            "3. Impact of fundamentals on short-term intraday (1-2 hours) price movements\n"
            "4. Judgment: STRONG / MEDIUM / WEAK"
        )

    description = market_data.get('description', '')[:250]
    asset_type_label = "cryptocurrency" if is_crypto else "stock/equity"

    return f"""You are the Fundamentals Analyst of Argus. Analyze the fundamentals of {coin['name']} ({coin['symbol']}), a {asset_type_label}.

FUNDAMENTAL DATA:
- Market Cap: {mcap_str}
{extra_data}
- Description: {description}

Provide a SHORT analysis (max 100 words) focusing on:
{analysis_focus}

IMPORTANT: Connect your fundamental assessment to a SHORT-TERM (1-3 day) price implication. Do not just describe the fundamentals — conclude whether they CREATE or REMOVE short-term downside risk.
Respond only with the analysis."""


def _build_bull_prompt(coin: dict, market_analysis: str, news_analysis: str, fundamentals_analysis: str, market_context: str, market_type: str = "crypto") -> str:
    is_crypto = market_type.lower() == "crypto"
    asset_type_label = "cryptocurrency" if is_crypto else "stock"
    asset_context = (
        "Consider blockchain adoption, DeFi growth, exchange listings, on-chain metrics."
        if is_crypto else
        "Consider earnings beats, analyst upgrades, sector rotation, macro tailwinds."
    )
    return f"""You are the Bull Researcher of Argus. Your task is to identify the STRONGEST BULLISH ARGUMENTS for {coin['name']} ({coin['symbol']}), a {asset_type_label}, over the next 2 hours.

Recent Intraday Tech Context:
- Order Book Imbalance: {market_analysis.split('Order Book Imbalance (Bid vs Ask):')[-1].splitlines()[0].strip() if 'Order Book Imbalance' in market_analysis else 'See Market Analysis'}
- 15m Techs: {market_analysis.split('Intraday (15m) Tech:')[-1].splitlines()[0].strip() if 'Intraday' in market_analysis else 'See Market Analysis'}

TEAM ANALYSIS:
MARKET ANALYST: {market_analysis}
NEWS ANALYST: {news_analysis}
FUNDAMENTALS ANALYST: {fundamentals_analysis}

{market_context}
REGIME INTEGRATION RULES (apply to your bullish thesis):
- If Regime is "ALTSEASON": Market conditions strongly support your bullish case. Leverage this as evidence of favorable macro rotation.
- If Regime is "BTC_ACCUMULATION": Liquidity is flowing to BTC. You MUST acknowledge this headwind and explain why this specific asset can outperform despite it. If you cannot provide concrete evidence, reduce your bull probability by at least 20 points.
- If Regime is "CRYPTO_WINTER / BEARISH": You are arguing against the macro trend. Your arguments MUST be exceptionally strong and based on asset-specific catalysts (not generic). Cap your bull probability at 40% maximum unless you can cite a specific imminent catalyst.

{asset_context}

Build the strongest possible bullish case (max 100 words):
- List 3-4 SPECIFIC, DATA-BACKED arguments (cite numbers from the team analysis)
- Each argument must reference a verifiable data point, not just a narrative
- Provide an optimistic target price for 2h (as a number AND % change)
- Estimate the bullish probability (0-100%) — this MUST be calibrated honestly, not inflated

Format: bullet points, then "2h TARGET: $X (+Y%) | BULL PROBABILITY: Z%"
Respond only with the content."""


def _build_bear_prompt(coin: dict, market_analysis: str, news_analysis: str, fundamentals_analysis: str, market_context: str, market_type: str = "crypto") -> str:
    is_crypto = market_type.lower() == "crypto"
    asset_type_label = "cryptocurrency" if is_crypto else "stock"
    asset_context = (
        "Consider regulatory crackdowns, exchange hacks, whale sell-offs, network issues."
        if is_crypto else
        "Consider earnings misses, analyst downgrades, macro headwinds, sector weakness."
    )
    return f"""You are the Bear Researcher of Argus. Your task is to identify the STRONGEST BEARISH ARGUMENTS and RISKS for {coin['name']} ({coin['symbol']}), a {asset_type_label}, over the next 2 hours.

Recent Intraday Tech Context:
- Order Book Imbalance: {market_analysis.split('Order Book Imbalance (Bid vs Ask):')[-1].splitlines()[0].strip() if 'Order Book Imbalance' in market_analysis else 'See Market Analysis'}
- 15m Techs: {market_analysis.split('Intraday (15m) Tech:')[-1].splitlines()[0].strip() if 'Intraday' in market_analysis else 'See Market Analysis'}

TEAM ANALYSIS:
MARKET ANALYST: {market_analysis}
NEWS ANALYST: {news_analysis}
FUNDAMENTALS ANALYST: {fundamentals_analysis}

{market_context}
REGIME INTEGRATION RULES (apply to your bearish thesis):
- If Regime is "ALTSEASON": Market conditions are working against your bearish case. You MUST explain why this specific asset is at risk DESPITE a favorable macro environment. If you cannot provide concrete evidence, reduce your bear probability by at least 20 points.
- If Regime is "BTC_ACCUMULATION": Liquidity is draining from alts — this supports your bearish thesis. Use the rotation data as evidence.
- If Regime is "CRYPTO_WINTER / BEARISH": The macro trend supports your case. Leverage it but avoid over-reliance on regime alone — cite asset-specific risks too.

{asset_context}

Build the strongest possible bearish case (max 100 words):
- List 3-4 SPECIFIC, DATA-BACKED risks (cite numbers from the team analysis)
- Each risk must reference a verifiable data point, not just a narrative
- Provide a pessimistic target price for 2h (as a number AND % change)
- Estimate the bearish probability (0-100%) — this MUST be calibrated honestly, not inflated

Format: bullet points, then "2h TARGET: $X (-Y%) | BEAR PROBABILITY: Z%"
Respond only with the content."""


def _build_decision_prompt(coin: dict, market_analysis: str, news_analysis: str,
                            fundamentals_analysis: str, bull_case: str, bear_case: str,
                            market_context: str, backtest_results: str = "", market_type: str = "crypto") -> str:
    current_price = coin.get('last_price', 0)
    asset_type_label = "cryptocurrency" if market_type.lower() == "crypto" else "stock/equity"
    
    backtest_section = ""
    if backtest_results:
        backtest_section = f"\nINSTANT BACKTEST (Last 6 Months):\n{backtest_results}\n"

    return f"""You are the Portfolio Manager of Argus. You must make the FINAL trading decision for {coin['name']} ({coin['symbol']}), a {asset_type_label}.
Current price: ${current_price}
{backtest_section}

{market_context}

DECISION FRAMEWORK — Apply this weighted hierarchy to reach your final decision:

TIE 1 — HIGHEST WEIGHT (60% of decision):
- Technical price action: trend direction, support/resistance proximity, volume confirmation
- Recent price momentum (24h, 7d changes)

TIER 2 — MODERATE WEIGHT (25% of decision):
- Market Regime (ALTSEASON / BTC_ACCUMULATION / CRYPTO_WINTER)
- BTC correlation and its implication for this specific asset
- Backtest results if available

TIER 3 — LOW WEIGHT (10% of decision):
- News & Sentiment (only if fresh, <24h, and not already priced in)
- Fundamental analysis

TIER 4 — MINIMAL WEIGHT (5% of decision):
- Fear & Greed Index: treat as background context ONLY. Do NOT let this single indicator override technical evidence. It reflects retail sentiment, not predictive signal.

REGIME SAFETY RULES:
- If Regime is "ALTSEASON": Validate higher risk/reward setups.
- If Regime is "BTC_ACCUMULATION": Demand higher conviction on altcoins. Prefer BTC-correlated plays.
- If Regime is "CRYPTO_WINTER / BEARISH": Apply severe risk reduction (reduce size by at least 70% or recommend FLAT). Reject overly optimistic cases.

COHERENCE CHECK — Before outputting, verify:
1. If signal is BUY, the target_price_1d MUST be ABOVE current price
2. If signal is SELL, the target_price_1d MUST be BELOW current price
3. Confidence MUST reflect the margin of bull/bear probability difference (if 55% bull vs 45% bear, confidence should be LOW ~55, not HIGH ~85)
4. stop_loss MUST be tighter than take_profit distance (favorable risk/reward)
5. HORIZON IS STRICTLY 2 HOURS (INTRADAY). Avoid extreme price targets. Typical intraday SL is between 0.5% to 2% from current price. TP is typically 1% to 4%. 
6. IMPORTANT DISTINCTION: Your predicted `change_pct_2h` is the STATISTICAL EXPECTED MEAN MOVE in 2 hours, NOT your Take Profit. While TP can be 3%, the expected mean move is usually very small (e.g., 0.1% to 0.8% or -0.1% to -0.8%). Do NOT output your TP percentage as the expected change.
7. BACKTEST NOTE: The Instant Backtest Strategy Return is over the LAST 30 DAYS, do NOT confuse it with a 2-hour expected return.

TEAM DEBATE:
MARKET ANALYST: {market_analysis}
NEWS ANALYST: {news_analysis}
FUNDAMENTALS ANALYST: {fundamentals_analysis}
BULL RESEARCHER: {bull_case}
BEAR RESEARCHER: {bear_case}

Weigh all perspectives using the hierarchy above and provide the final decision as valid JSON:
{{
  "target_price_2h": <number, strictly use DOT for decimals. NEVER null or 0>,
  "change_pct_2h": <signed number, strictly use DOT. NEVER null or 0. This is the REALISTIC STATISTICAL MEAN MOVE in 2 hours (typically -0.8% to 0.8%), NOT the TP %>,
  "confidence": <integer from 0 to 100 representing percentage, without "%" sign>,
  "stop_loss": <number, strictly use DOT for decimals e.g. 590.20>,
  "take_profit": <number, strictly use DOT for decimals e.g. 650.00>,
  "rationale": "<max 80 words in English explaining the final decision>",
  "key_risk": "<main risk in max 30 words in English>"
}}

IMPORTANT: Respond ONLY with valid JSON. Strictly use DOT (.) for decimals, NOT commas. No "$" or "%" inside numeric values. No trailing commas. Output only the JSON object."""


def _build_bull_debate_prompt(coin: dict, market_analysis: str, news_analysis: str,
                               fundamentals_analysis: str, previous_bear_case: str,
                               market_context: str, round_num: int, market_type: str = "crypto") -> str:
    asset_type_label = "cryptocurrency" if market_type.lower() == "crypto" else "stock"
    return f"""You are the Bull Researcher of Argus (Round {round_num}). Defend and strengthen the bullish case for {coin['name']} ({coin['symbol']}), a {asset_type_label}, by countering the Bear agent's thesis.

INITIAL TEAM ANALYSIS:
MARKET: {market_analysis}
NEWS: {news_analysis}
FUNDAMENTALS: {fundamentals_analysis}

{market_context}
REGIME INTEGRATION RULES:
- If Regime is "ALTSEASON": Use this as supporting evidence for your bullish rebuttal.
- If Regime is "BTC_ACCUMULATION": Acknowledge the headwind. Counter only if you have asset-specific bullish catalysts.
- If Regime is "CRYPTO_WINTER / BEARISH": You are arguing against the macro. Your counter-arguments must be exceptionally specific and data-backed. Cap bull probability at 40%.

BEARISH THESIS TO REFUTE:
{previous_bear_case}

Construct your bullish reply (max 100 words):
- Identify the WEAKEST point in the bearish argument and attack it with data
- Do NOT simply repeat your previous arguments — add new evidence or reframe existing data
- Update your bull probability honestly based on the debate so far
Respond only with your reply, without greetings or introductions."""


def _build_bear_debate_prompt(coin: dict, market_analysis: str, news_analysis: str,
                               fundamentals_analysis: str, previous_bull_case: str,
                               market_context: str, round_num: int, market_type: str = "crypto") -> str:
    asset_type_label = "cryptocurrency" if market_type.lower() == "crypto" else "stock"
    return f"""You are the Bear Researcher of Argus (Round {round_num}). Defend and strengthen the bearish case for {coin['name']} ({coin['symbol']}), a {asset_type_label}, by countering the Bull agent's thesis.

INITIAL TEAM ANALYSIS:
MARKET: {market_analysis}
NEWS: {news_analysis}
FUNDAMENTALS: {fundamentals_analysis}

{market_context}
REGIME INTEGRATION RULES:
- If Regime is "ALTSEASON": You are arguing against the macro. Your risks must be asset-specific and well-evidenced. Cap bear probability at 40%.
- If Regime is "BTC_ACCUMULATION": Use the liquidity drain as supporting evidence for your bearish case.
- If Regime is "CRYPTO_WINTER / BEARISH": The macro supports your thesis. But avoid over-reliance on regime — cite asset-specific weaknesses too.

BULLISH THESIS TO REFUTE:
{previous_bull_case}

Construct your bearish reply (max 100 words):
- Identify the WEAKEST point in the bullish argument and attack it with data
- Do NOT simply repeat your previous arguments — add new evidence or reframe existing data
- Update your bear probability honestly based on the debate so far
Respond only with your reply, without greetings or introductions."""


def _build_decision_debate_prompt(coin: dict, market_analysis: str, news_analysis: str,
                                   fundamentals_analysis: str, debate_history: str,
                                   market_context: str, backtest_results: str = "", market_type: str = "crypto") -> str:
    current_price = coin.get('last_price', 0)
    asset_type_label = "cryptocurrency" if market_type.lower() == "crypto" else "stock/equity"
    
    backtest_section = ""
    if backtest_results:
        backtest_section = f"\nINSTANT BACKTEST (Last 6 Months):\n{backtest_results}\n"

    return f"""You are the Portfolio Manager of Argus. You must make the FINAL trading decision for {coin['name']} ({coin['symbol']}), a {asset_type_label}.
Current price: ${current_price}
{backtest_section}

{market_context}

DECISION FRAMEWORK — Apply this weighted hierarchy to reach your final decision:

TIER 1 — HIGHEST WEIGHT (60% of decision):
- Technical price action: trend direction, support/resistance proximity, volume confirmation
- Recent price momentum (24h, 7d changes)

TIER 2 — MODERATE WEIGHT (25% of decision):
- Market Regime (ALTSEASON / BTC_ACCUMULATION / CRYPTO_WINTER)
- BTC correlation and its implication for this specific asset
- Backtest results if available

TIER 3 — LOW WEIGHT (10% of decision):
- News & Sentiment (only if fresh, <24h, and not already priced in)
- Fundamental analysis

TIER 4 — MINIMAL WEIGHT (5% of decision):
- Fear & Greed Index: treat as background context ONLY. Do NOT let this single indicator override technical evidence. It reflects retail sentiment, not predictive signal.

REGIME SAFETY RULES:
- If Regime is "ALTSEASON": Validate higher risk/reward setups.
- If Regime is "BTC_ACCUMULATION": Demand higher conviction on altcoins. Prefer BTC-correlated plays.
- If Regime is "CRYPTO_WINTER / BEARISH": Apply severe risk reduction (reduce size by at least 70% or recommend FLAT). Reject overly optimistic cases.

COHERENCE CHECK — Before outputting, verify:
1. The target_price_1d MUST be realistic for the intraday horizon.
2. The change_pct_1d MUST correspond mathematically to the target_price_1d.
3. Confidence MUST reflect the margin of bull/bear probability difference
4. stop_loss MUST be tighter than take_profit distance (favorable risk/reward)
5. HORIZON IS STRICTLY 2 HOURS (INTRADAY). Avoid extreme price targets. Typical intraday SL is between 0.5% to 2% from current price. TP is typically 1% to 4%.
6. IMPORTANT DISTINCTION: Your predicted `change_pct_2h` is the STATISTICAL EXPECTED MEAN MOVE in 2 hours, NOT your Take Profit. While TP can be 3%, the expected mean move is usually very small (e.g., 0.1% to 0.8% or -0.1% to -0.8%). Do NOT output your TP percentage as the expected change.
7. BACKTEST NOTE: The Instant Backtest Strategy Return is over the LAST 30 DAYS, do NOT confuse it with a 2-hour expected return.

PRELIMINARY DATA:
MARKET ANALYST: {market_analysis}
NEWS ANALYST: {news_analysis}
FUNDAMENTALS ANALYST: {fundamentals_analysis}

DEBATE HISTORY (Bull vs Bear):
{debate_history}

Weigh all perspectives using the hierarchy above and provide the final decision as valid JSON:
{{
  "target_price_2h": <number, strictly use DOT for decimals. NEVER null or 0>,
  "change_pct_2h": <signed number, strictly use DOT. NEVER null or 0. This is the REALISTIC STATISTICAL MEAN MOVE in 2 hours (typically -0.8% to 0.8%), NOT the TP %>,
  "confidence": <integer from 0 to 100 representing percentage, without "%" sign>,
  "stop_loss": <number, strictly use DOT for decimals e.g. 590.20>,
  "take_profit": <number, strictly use DOT for decimals e.g. 650.00>,
  "rationale": "<max 80 words in English explaining the final decision based on the debate>",
  "key_risk": "<main risk highlighted in the debate, max 30 words in English>"
}}

IMPORTANT: Respond ONLY with valid JSON. Strictly use DOT (.) for decimals, NOT commas. No "$" or "%" inside numeric values. No trailing commas. Output only the JSON object."""


# ─────────────────────────────────────────────────────────────
# Main Class
# ─────────────────────────────────────────────────────────────

class AIAnalyst:
    """
    Multi-agent analysis engine for crypto.
    Runs a pipeline of 6 LLM agents for each analyzed crypto.
    """

    def __init__(self, settings: dict):
        """
        Args:
            settings: dictionary containing the following keys:
                - ai_provider: 'openrouter' | 'openai' | 'ollama'
                - ai_model_quick: name of quick model (preliminary)
                - ai_model_deep: name of deep model (debate/decision)
                - ai_research_rounds: number of debate rounds (depth)
                - ai_api_key: API key of the provider
                - coingecko_api_key: CoinGecko API key
                - coingecko_api_plan: 'demo' | 'pro'
                - ai_finnhub_key: Finnhub key (optional)
        """
        self._settings = settings
        provider = settings.get("ai_provider", "openrouter")
        
        if provider == "ollama":
            host = settings.get("ai_ollama_host", "http://localhost:11434").strip()
            if not host:
                host = "http://localhost:11434"
            if not host.endswith("/v1"):
                if host.endswith("/"):
                    host += "v1"
                else:
                    host += "/v1"
            base_url = host
        elif provider == "claude":
            base_url = None
        else:
            base_url = PROVIDER_URLS.get(provider, PROVIDER_URLS["openrouter"])
            
        api_key = settings.get("ai_api_key", "")
        
        extra_headers = OPENROUTER_HEADERS if provider == "openrouter" else {}
        
        if provider != "claude":
            self._client = OpenAI(
                api_key=api_key or "sk-dummy",  # ollama does not require a key
                base_url=base_url,
                default_headers=extra_headers,
            )
        else:
            self._client = None
        
        # Load differentiated models with fallback to ai_model if previously defined
        default_model = settings.get("ai_model", "anthropic/claude-3-haiku")
        self._model_quick = settings.get("ai_model_quick", "").strip() or default_model
        self._model_deep = settings.get("ai_model_deep", "").strip() or default_model
        self._model_fallback = settings.get("ai_model_fallback", "").strip()
        try:
            self._research_rounds = int(settings.get("ai_research_rounds", 1))
        except Exception:
            self._research_rounds = 1

        # Use the independent CoinGecko key for AI analysis
        self._cg_key = settings.get("ai_coingecko_key", "").strip()
        self._cg_plan = settings.get("coingecko_api_plan", "demo")
        self._finnhub_key = settings.get("ai_finnhub_key", "")

    def _call_llm(self, user_message: str, model: str, temperature: float = 0.3) -> str:
        """Calls the LLM with the requested fallback hierarchy."""
        model_deep = getattr(self, "_model_deep", "").strip()
        model_quick = getattr(self, "_model_quick", "").strip()
        model_fallback = getattr(self, "_model_fallback", "").strip()

        # Define hierarchy based on the starting model
        if model == model_deep:
            hierarchy = [model_deep, model_quick, model_fallback]
        elif model == model_quick:
            hierarchy = [model_quick, model_deep, model_fallback]
        else:
            hierarchy = [model.strip(), model_fallback]

        # Remove duplicates and empty strings while maintaining order
        clean_hierarchy = []
        for m in hierarchy:
            if m and m not in clean_hierarchy:
                clean_hierarchy.append(m)

        last_exception = None
        for current_model in clean_hierarchy:
            try:
                if current_model != clean_hierarchy[0]:
                    print(f"[AIAnalyst] Attempting fallback to {current_model}...")
                return self._execute_llm_call(user_message, current_model, temperature)
            except Exception as e:
                print(f"[AIAnalyst] LLM call error with model {current_model}: {e}")
                last_exception = e

        # If all fail
        raise last_exception or Exception("All fallback attempts failed.")

    def _execute_llm_call(self, user_message: str, model: str, temperature: float) -> str:
        market_type = self._settings.get("market_type", "crypto").lower()
        asset_label = "cryptocurrency" if market_type == "crypto" else "stock market"
        system_role = f"""You are part of Argus, a multi-agent {asset_label} trading system designed for SHORT-TERM (1-3 day) predictions.

CORE PRINCIPLES:
1. BASE EVERY CLAIM ON DATA — cite specific numbers (prices, percentages, volumes). Avoid vague terms like "bullish momentum" without supporting evidence.
2. PRICE-ANCHOR everything to the current price level. Express targets, supports, and resistances as absolute prices AND percentage moves.
3. ACKNOWLEDGE UNCERTAINTY — use calibrated probabilities. A 60% probability means you genuinely believe the event will NOT happen 40% of the time.
4. PRIORITIZE ACTIONABILITY — every analysis must produce a clear, measurable conclusion that the next agent in the pipeline can act on.

Always respond in English. Be brief and direct."""

        max_tokens_limit = 4096 if model == self._model_deep else 2048
        provider = self._settings.get("ai_provider", "openrouter")

        if provider == "claude":
            api_key = self._settings.get("ai_api_key", "").strip()
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": model,
                "system": system_role,
                "messages": [
                    {"role": "user", "content": user_message}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens_limit,
            }
            resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=45)
            if resp.status_code != 200:
                try:
                    err_msg = resp.json().get("error", {}).get("message", resp.text)
                except Exception:
                    err_msg = resp.text
                raise ValueError(f"Anthropic API Error (Status {resp.status_code}): {err_msg}")
            
            resp_data = resp.json()
            if not resp_data.get("content"):
                raise ValueError(f"Response content from Claude is empty: {resp_data}")
            
            content = resp_data["content"][0]["text"]
            return content.strip()

        # Standard OpenAI-compatible API
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user",   "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens_limit,
        )
        if not response.choices:
            extra = getattr(response, "model_extra", {})
            err_details = extra.get("error", "No details available from the provider.") if extra else "Empty response from the provider."
            raise ValueError(f"No choices returned. Provider Details: {err_details}")
            
        content = response.choices[0].message.content
        if content is None:
            refusal = getattr(response.choices[0].message, 'refusal', None)
            err_msg = f"Model returned empty/null content. Refusal: {refusal}" if refusal else "Model returned empty/null content."
            raise ValueError(err_msg)
        return content.strip()

    def _parse_decision_json(self, raw: str, coin: dict) -> dict:
        """Extracts JSON from the PortfolioManager response, with robust fallbacks."""
        current_price = coin.get("last_price", 0) or 0
        
        # 1. Preliminary cleanup of the string
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)
            cleaned = cleaned.strip()

        # Remove trailing commas
        cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)

        # Search for the main JSON block { ... }
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        
        parsed = {}
        if start >= 0 and end > start:
            json_str = cleaned[start:end]
            try:
                parsed = json.loads(json_str)
            except Exception as e:
                print(f"[AIAnalyst] Standard JSON parse failed, attempting regex recovery: {e}")
                parsed = self._regex_parse_json(json_str)
        else:
            print("[AIAnalyst] JSON block not found in raw response, attempting regex recovery...")
            parsed = self._regex_parse_json(cleaned)

        # Ensure all expected fields are populated
        res = {
            "target_price_1d": current_price,
            "change_pct_1d": 0.0,
            "confidence": 0,
            "stop_loss": None,
            "take_profit": None,
            "rationale": parsed.get("rationale", ""),
            "key_risk": parsed.get("key_risk", ""),
        }

        # Convert and clean target_price_2h mapped to 1d
        try:
            val = parsed.get("target_price_2h") or parsed.get("target_price_1d")
            if val is not None:
                val_str = str(val).replace(",", ".")
                val_clean = re.sub(r"[^\d.]", "", val_str)
                if val_clean:
                    res["target_price_1d"] = float(val_clean)
        except Exception:
            pass

        # Convert and clean change_pct_2h mapped to 1d
        try:
            val = parsed.get("change_pct_2h") or parsed.get("change_pct_1d")
            if val is not None:
                val_str = str(val).replace(",", ".")
                val_clean = re.sub(r"[^\d.+-]", "", val_str)
                if val_clean:
                    res["change_pct_1d"] = float(val_clean)
        except Exception:
            pass

        # Convert confidence, stop_loss, take_profit
        for key in ["confidence", "stop_loss", "take_profit"]:
            try:
                val = parsed.get(key)
                if val is not None:
                    val_str = str(val).replace(",", ".")
                    val_clean = re.sub(r"[^\d.]", "", val_str)
                    if val_clean:
                        if key == "confidence":
                            res[key] = int(float(val_clean))
                        else:
                            res[key] = float(val_clean)
            except Exception:
                pass

        # Fallback rationale/key_risk if empty
        if not res["rationale"]:
            res["rationale"] = "The final decision leans towards holding the position while waiting for clearer market signals."
        if not res["key_risk"]:
            res["key_risk"] = "High short-term market volatility."

        return res

    def _regex_parse_json(self, text: str) -> dict:
        """Extracts values using regular expressions if JSON is malformed."""
        res = {}
        patterns = {
            "target_price_1d": r'"target_price_(?:2h|1d)"\s*:\s*"?\$?([+\-]?[\d.,]+)"?',
            "change_pct_1d": r'"change_pct_(?:2h|1d)"\s*:\s*"?([+\-]?[\d.,]+)%?"?',
            "confidence": r'"confidence"\s*:\s*"?([+\-]?[\d.,]+)"?',
            "stop_loss": r'"stop_loss"\s*:\s*"?\$?([+\-]?[\d.,]+)"?',
            "take_profit": r'"take_profit"\s*:\s*"?\$?([+\-]?[\d.,]+)"?',
            "rationale": r'"rationale"\s*:\s*"([^"]+)"',
            "key_risk": r'"key_risk"\s*:\s*"([^"]+)"'
        }
        for key, pat in patterns.items():
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                res[key] = match.group(1)
        return res

    def _run_instant_backtest(self, coin: dict, market_analysis: str, news_analysis: str, fundamentals_analysis: str, market_context: dict = None) -> tuple:
        """Runs an instant backtest of the last 6 months using vectorbt with regime-conditional logic."""
        symbol = coin.get("symbol", "?")
        name = coin.get("name", symbol)
        market_type = self._settings.get("market_type", "crypto").lower()
        is_crypto = (market_type == "crypto")
        
        # Extract macro regime
        regime = "UNKNOWN"
        if market_context and isinstance(market_context, dict):
            regime = market_context.get("regime", "UNKNOWN")
        
        # LLM call to extract or generate strategy parameters
        extract_prompt = f"""You are the Backtest Strategy Parameters Extractor for Argus.
Read these analysis reports for {name} ({symbol}):
MARKET ANALYST: {market_analysis}
NEWS ANALYST: {news_analysis}
FUNDAMENTALS ANALYST: {fundamentals_analysis}
CURRENT REGIME: {regime}

Based on these analyses AND the current market regime, decide on the best numeric parameters to backtest a strategy over the last 6 months.

REGIME-AWARE PARAMETER RULES:
- If regime is "CRYPTO_WINTER / BEARISH": Prefer wider RSI bands (rsi_lower=20, rsi_upper=80) and consider "long_short" direction.
- If regime is "ALTSEASON": Prefer tighter RSI bands (rsi_lower=35, rsi_upper=65) and faster EMAs for momentum capture.
- If regime is "BTC_ACCUMULATION": Use standard parameters but favor "long_only" for BTC, "long_short" for altcoins.

You MUST output a valid JSON object with exactly the following fields (all values must be standard numeric types):
{{
  "ema_fast": <int: window for fast EMA, typically 8-15>,
  "ema_slow": <int: window for slow EMA, typically 18-30>,
  "rsi_period": <int: RSI window, typically 10-21>,
  "rsi_lower": <int: RSI oversold buy limit, typically 20-35>,
  "rsi_upper": <int: RSI overbought sell limit, typically 65-80>,
  "direction": "long_only|long_short"
}}
Respond ONLY with this JSON block, no comments, no markdown fences."""
        
        params = {
            "ema_fast": 10,
            "ema_slow": 20,
            "rsi_period": 14,
            "rsi_lower": 30,
            "rsi_upper": 70,
            "direction": "long_only"
        }
        
        try:
            raw_resp = self._call_llm(extract_prompt, model=self._model_quick)
            cleaned = raw_resp.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
                cleaned = re.sub(r"\n```$", "", cleaned)
                cleaned = cleaned.strip()
            import json
            parsed = json.loads(cleaned)
            for k in params:
                if k in parsed:
                    if k == "direction":
                        if parsed[k] in ("long_only", "long_short"):
                            params[k] = parsed[k]
                    else:
                        params[k] = int(parsed[k])
        except Exception as e:
            print(f"[AIAnalyst] Failed to extract backtest parameters from LLM, using baseline: {e}")
            
        # Download 15-minute historical data for backtesting from the markets module
        try:
            from core.data_manager import load_historical
            import pandas as pd
            import numpy as np
            
            df = load_historical(symbol)
            
            if df is None or df.empty:
                raise ValueError(f"No local historical data found for {symbol}. Refresh prices in the Markets tab.")
                
            close = df['Close']
            if isinstance(close, pd.DataFrame):
                close = close.squeeze()
            close = close.dropna()
            
            if len(close) < params["ema_slow"] + 5:
                raise ValueError("Insufficient data points for indicators.")
                
            # Calculate indicators
            ema_fast = close.ewm(span=params["ema_fast"], adjust=False).mean()
            ema_slow = close.ewm(span=params["ema_slow"], adjust=False).mean()
            
            # RSI
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=params["rsi_period"]).mean()
            avg_loss = loss.rolling(window=params["rsi_period"]).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            rsi = rsi.fillna(50)
            
            # Generate signals
            entries = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
            exits = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
            
            # Add RSI signals
            entries = entries | ((rsi < params["rsi_lower"]) & (rsi.shift(1) >= params["rsi_lower"]))
            exits = exits | ((rsi > params["rsi_upper"]) & (rsi.shift(1) <= params["rsi_upper"]))
            
            # Run backtest with vectorbt
            import vectorbt as vbt
            
            # Calculate dynamic SL/TP based on asset volatility (15m ATR)
            atr_period = 14
            daily_returns = close.pct_change().abs()
            atr_pct = daily_returns.rolling(window=atr_period).mean().iloc[-1]
            
            if np.isnan(atr_pct) or atr_pct <= 0:
                atr_pct = 0.005  # fallback: 0.5% volatility
            
            # SL = 1x ATR, TP = 2x ATR for tight intraday trading
            sl_stop = float(np.clip(atr_pct * 1, 0.002, 0.05))  # min 0.2%, max 5%
            tp_stop = float(np.clip(atr_pct * 2, 0.004, 0.10))  # min 0.4%, max 10%
            
            if params["direction"] == "long_short":
                pf = vbt.Portfolio.from_signals(
                    close,
                    entries=entries,
                    exits=exits,
                    short_entries=exits,
                    short_exits=entries,
                    init_cash=10000.0,
                    fees=0.0005,      # 0.05% Taker fee
                    slippage=0.0005,  # 0.05% slippage
                    freq='15m',
                    sl_stop=sl_stop,
                    tp_stop=tp_stop
                )
            else:
                pf = vbt.Portfolio.from_signals(
                    close,
                    entries=entries,
                    exits=exits,
                    init_cash=10000.0,
                    fees=0.0005,
                    slippage=0.0005,
                    freq='15m',
                    sl_stop=sl_stop,
                    tp_stop=tp_stop
                )
                
            # Extract metrics
            start_val = 10000.0
            end_val = float(pf.final_value())
            total_ret = float(pf.total_return() * 100.0)
            bench_ret = float((close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100.0)
            
            try:
                sharpe = float(pf.sharpe_ratio())
            except Exception:
                sharpe = np.nan
                
            try:
                max_dd = float(pf.max_drawdown() * -100.0)
            except Exception:
                max_dd = np.nan
                
            try:
                trades_count = int(pf.trades.count())
            except Exception:
                try:
                    trades_count = int(len(pf.trades.records))
                except Exception:
                    trades_count = 0
                    
            import math
            def clean_val(v, pct=False):
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    return "N/A"
                if pct:
                    sign = "+" if v >= 0 else ""
                    return f"{sign}{v:.2f}%"
                return f"{v:.2f}"
                
            # Regime-Conditional Logic
            alpha = np.nan
            pf_protected = None
            protected_total_ret = np.nan
            protected_max_dd = np.nan
            mitigation_str = "N/A"
            
            if regime == "BULLISH":
                alpha = total_ret - bench_ret
            elif regime == "BEARISH":
                try:
                    if params["direction"] == "long_short":
                        pf_protected = vbt.Portfolio.from_signals(
                            close,
                            entries=entries,
                            exits=exits,
                            short_entries=exits,
                            short_exits=entries,
                            init_cash=10000.0,
                            fees=0.0005,
                            slippage=0.0005,
                            freq='15m',
                            sl_stop=min(0.01, sl_stop),  # Use even tighter SL for bear market
                            tp_stop=tp_stop
                        )
                    else:
                        pf_protected = vbt.Portfolio.from_signals(
                            close,
                            entries=entries,
                            exits=exits,
                            init_cash=10000.0,
                            fees=0.0005,
                            slippage=0.0005,
                            freq='15m',
                            sl_stop=min(0.01, sl_stop),
                            tp_stop=tp_stop
                        )
                    if pf_protected is not None:
                        protected_total_ret = float(pf_protected.total_return() * 100.0)
                        protected_max_dd = float(pf_protected.max_drawdown() * -100.0)
                        
                        # Mitigation: if the protected drawdown is less severe (e.g. -8.00% vs -15.00% base)
                        drawdown_mitigated = protected_max_dd > max_dd
                        returns_improved = protected_total_ret > total_ret
                        
                        if drawdown_mitigated and returns_improved:
                            mitigation_str = "YES (Tight SL reduces Drawdown and improves return)"
                        elif drawdown_mitigated:
                            mitigation_str = "PARTIAL (Tight SL reduces Drawdown but impacts return)"
                        else:
                            mitigation_str = "NO (Tight SL did not mitigate losses in this period)"
                except Exception as epf:
                    print(f"[AIAnalyst] Error running protected backtest: {epf}")

            # Construct structured backtest_metrics report
            if regime == "BULLISH":
                outperformed = alpha > 0 if not np.isnan(alpha) else False
                comparison_str = "YES (Strategy beats Buy & Hold)" if outperformed else "NO (Strategy underperforms)"
                backtest_metrics = f"""Strategy performance in current regime (BULLISH):
- Strategy Return: {clean_val(total_ret, pct=True)}
- Benchmark Return (Buy & Hold): {clean_val(bench_ret, pct=True)}
- Alpha vs Benchmark: {clean_val(alpha, pct=True)}
- Does strategy beat market in bullish conditions? {comparison_str}"""
            elif regime == "BEARISH":
                backtest_metrics = f"""Strategy performance in current regime (BEARISH):
- Strategy Return (Base): {clean_val(total_ret, pct=True)}
- Strategy Return (With 3% Protective SL): {clean_val(protected_total_ret, pct=True)}
- Max Drawdown (Base): {clean_val(max_dd)}%
- Max Drawdown (With 3% Protective SL): {clean_val(protected_max_dd)}%
- Loss Mitigation: {mitigation_str}"""
            else:
                backtest_metrics = f"""Strategy performance in current regime (UNKNOWN):
- Strategy Return: {clean_val(total_ret, pct=True)}
- Benchmark Return (Buy & Hold): {clean_val(bench_ret, pct=True)}
- Max Drawdown: {clean_val(max_dd)}%"""

            report = f"""### 📊 Instant Backtest (Last 30 Days @ 15m)
- **Backtest Strategy**: EMA Cross ({params['ema_fast']}/{params['ema_slow']}) + RSI ({params['rsi_lower']}/{params['rsi_upper']})
- **Direction**: {"Long/Short" if params['direction'] == 'long_short' else "Long Only"}
- **Initial vs Final Value**: ${start_val:,.2f} ➔ ${end_val:,.2f}
- **Strategy Return**: {clean_val(total_ret, pct=True)}
- **Benchmark Return (Buy & Hold)**: {clean_val(bench_ret, pct=True)}
- **Sharpe Ratio**: {clean_val(sharpe)}
- **Max Drawdown**: {clean_val(max_dd)}%
- **Trades Executed**: {trades_count}

{backtest_metrics}"""

            return report, backtest_metrics

        except Exception as e:
            if "No price data returned" in str(e) or "Insufficient data points" in str(e):
                raise  # Abort analysis if asset does not exist or is delisted
            print(f"[AIAnalyst] Backtest error: {e}")
            err_report = f"### 📊 Instant Backtest (Last 6 Months)\n⚠️ Cannot execute backtest for {symbol}: {e}"
            err_metrics = f"Strategy performance in current regime (UNKNOWN):\n⚠️ Backtest error: {e}"
            return err_report, err_metrics

    def analyze_single(
        self,
        coin: dict,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """
        Runs the complete pipeline of 6 agents for a single crypto.

        Args:
            coin: dict with {name, symbol, last_price, forecast_price, change_pct, signal, horizon_days}
            progress_callback: function(msg: str) for status updates

        Returns:
            dict with structured results + debug of individual agents
        """
        def log(msg: str):
            if progress_callback:
                progress_callback(msg)
            print(f"[AIAnalyst] {msg}")

        name = coin.get("name", coin.get("symbol", "?"))
        symbol = coin.get("symbol", "?")
        current_price = coin.get("last_price", 0) or 0

        market_type = self._settings.get("market_type", "crypto").lower()
        is_crypto   = (market_type == "crypto")

        # ── Market data ──────────────────────────────────────────
        if is_crypto:
            log(f"🔍 [{symbol}] Fetching market data (CoinGecko)...")
            cg_data = _fetch_coingecko_details(symbol, self._cg_key, self._cg_plan)
            if not cg_data:
                log(f"⚠️ [{symbol}] CoinGecko unavailable — falling back to Yahoo Finance...")
                cg_data = _fetch_yahoo_details(symbol, is_crypto=True)
            time.sleep(0.3)  # Rate limiting CoinGecko
        else:
            log(f"🔍 [{symbol}] Fetching market data (Yahoo Finance — {market_type.upper()})...")
            cg_data = _fetch_yahoo_details(symbol, is_crypto=False)

        if not cg_data:
            raise ValueError(f"Unable to retrieve market data for {symbol} (even via fallback). Analysis aborted.")

        # ── 15m Technical Data & Order Book Imbalance ───────────────────────────
        ob_imbalance = 0.0
        tech_indicators = ""
        try:
            from core.portfolio_manager import PortfolioManager
            from core.data_fetcher import fetch_order_book_imbalance
            pm = PortfolioManager(self._settings)
            if pm.exchange:
                log(f"📉 [{symbol}] Fetching Order Book Imbalance & 15m Data...")
                ob_imbalance = fetch_order_book_imbalance(pm.exchange, symbol) or 0.0
                
                try:
                    from core.data_manager import load_historical
                    df_15 = load_historical(symbol)
                    
                    if df_15 is not None and not df_15.empty:
                        import numpy as np
                        import pandas as pd
                        # Use only the last 100 candles for rapid calculation
                        df_15 = df_15.tail(100).copy()
                        df_15["Close"] = pd.to_numeric(df_15["Close"])
                        std_dev = df_15["Close"].std()
                        
                        delta = df_15["Close"].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss
                        rsi = 100 - (100 / (1 + rs)).iloc[-1]
                        
                        tech_indicators = f"15m RSI: {rsi:.2f} | 15m StdDev: {std_dev:.4f}"
                    else:
                        log(f"⚠️ [{symbol}] Historical 15m data not found locally for indicators.")
                except Exception as e:
                    log(f"⚠️ [{symbol}] Failed 15m Tech Data from local history: {e}")
                    
        except Exception as e:
            log(f"⚠️ [{symbol}] Failed Order Book Imbalance/Exchange conn: {e}")

        cg_data["order_book_imbalance_pct"] = ob_imbalance
        cg_data["tech_indicators_15m"] = tech_indicators

        # ── News: Investing.com primary, Finnhub secondary, Yahoo Finance fallback ──
        log(f"📰 [{symbol}] Fetching news (Investing.com)...")
        news = _fetch_investing_news(symbol, name=name)
        
        if not news and self._finnhub_key:
            log(f"⚠️ [{symbol}] Investing.com news empty — trying Finnhub...")
            news = _fetch_finnhub_news(symbol, self._finnhub_key, is_crypto=is_crypto)
            
        if not news:
            log(f"⚠️ [{symbol}] Finnhub/Investing empty — trying Yahoo Finance...")
            news = _fetch_yahoo_news(symbol, is_crypto=is_crypto)
        if news:
            log(f"✅ [{symbol}] {len(news)} news headlines retrieved.")
        else:
            log(f"ℹ️ [{symbol}] No news found — agents will reason from market data.")

        # ── Step 1: Market Analyst ──────────────────────────────
        log(f"📊 [{symbol}] Market Analyst analyzing with {self._model_quick}...")
        market_analysis = self._call_llm(
            _build_market_prompt(coin, cg_data, market_type),
            model=self._model_quick,
        )

        # ── Step 2: News Analyst ────────────────────────────────
        log(f"📰 [{symbol}] News Analyst analyzing with {self._model_quick}...")
        news_analysis = self._call_llm(
            _build_news_prompt(coin, news, market_type),
            model=self._model_quick,
        )

        # ── Step 3: Fundamentals Analyst ────────────────────────
        log(f"📊 [{symbol}] Fundamentals Analyst analyzing with {self._model_quick}...")
        fundamentals_analysis = self._call_llm(
            _build_fundamentals_prompt(coin, cg_data, market_type),
            model=self._model_quick,
        )

        # ── Step 3.5: Market Enrichment ────────────────────────
        log(f"🌍 [{symbol}] Market Enrichment (Regime & Correlation)...")
        from core.market_enrichment import get_market_context
        market_context_data = get_market_context(symbol, is_crypto)
        market_context_str = market_context_data['summary']

        # ── Instant Backtest ─────────────────────────────────────
        log(f"📊 [{symbol}] Running instant backtest with vectorbt...")
        backtest_results, backtest_metrics = self._run_instant_backtest(
            coin, market_analysis, news_analysis, fundamentals_analysis, market_context=market_context_data
        )

        # ── Step 4 & 5: Bull vs Bear Debate ─────────────────────
        rounds = self._research_rounds if self._research_rounds > 0 else 1

        log(f"🐂 [{symbol}] Bull Researcher building initial case with {self._model_deep}...")
        bull_case = self._call_llm(
            _build_bull_prompt(coin, market_analysis, news_analysis, fundamentals_analysis, market_context_str, market_type),
            model=self._model_deep,
            temperature=0.4,
        )

        log(f"🐻 [{symbol}] Bear Researcher building initial case with {self._model_deep}...")
        bear_case = self._call_llm(
            _build_bear_prompt(coin, market_analysis, news_analysis, fundamentals_analysis, market_context_str, market_type),
            model=self._model_deep,
            temperature=0.4,
        )

        debate_history = f"ROUND 1:\n- [BULL]: {bull_case}\n\n- [BEAR]: {bear_case}\n"

        for r in range(2, rounds + 1):
            log(f"💬 [{symbol}] Debate Round {r}/{rounds} (Bull vs Bear)...")
            bull_case = self._call_llm(
                _build_bull_debate_prompt(
                    coin, market_analysis, news_analysis,
                    fundamentals_analysis, bear_case, market_context_str, r, market_type
                ),
                model=self._model_deep,
                temperature=0.4,
            )
            bear_case = self._call_llm(
                _build_bear_debate_prompt(
                    coin, market_analysis, news_analysis,
                    fundamentals_analysis, bull_case, market_context_str, r, market_type
                ),
                model=self._model_deep,
                temperature=0.4,
            )
            debate_history += f"\nROUND {r}:\n- [BULL]: {bull_case}\n\n- [BEAR]: {bear_case}\n"

        # ── Step 6: Portfolio Manager — Final Decision ───────────
        log(f"🎯 [{symbol}] Portfolio Manager taking final decision with {self._model_deep}...")

        pm_market_context_str = market_context_str
        fng_value = market_context_data.get('fng_value')
        fng_class = market_context_data.get('fng_class')
        if fng_value is not None and fng_class is not None:
            pm_market_context_str += f"\n- FEAR & GREED INDEX: {fng_value} ({fng_class})"

        if rounds > 1:
            raw_decision = self._call_llm(
                _build_decision_debate_prompt(
                    coin, market_analysis, news_analysis,
                    fundamentals_analysis, debate_history, pm_market_context_str, backtest_results, market_type
                ),
                model=self._model_deep,
                temperature=0.2,
            )
        else:
            raw_decision = self._call_llm(
                _build_decision_prompt(
                    coin, market_analysis, news_analysis,
                    fundamentals_analysis, bull_case, bear_case, pm_market_context_str, backtest_results, market_type
                ),
                model=self._model_deep,
                temperature=0.2,
            )
        decision = self._parse_decision_json(raw_decision, coin)

        return {
            "symbol": symbol,
            "name": name,
            "current_price": current_price,
            "target_price_1d": decision.get("target_price_1d", current_price),
            "ai_change_pct_1d": decision.get("change_pct_1d", 0.0),
            "change_pct_1d": coin.get("change_pct_1d", 0.0),
            "confidence": decision.get("confidence", "N/A"),
            "tfm_confidence": coin.get("confidence") if coin.get("confidence") is not None else coin.get("tfm_confidence", None),
            "btc_pred_confidence": coin.get("btc_pred_confidence", None),
            "stop_loss": decision.get("stop_loss", None),
            "take_profit": decision.get("take_profit", None),
            "rationale": decision.get("rationale", ""),
            "key_risk": decision.get("key_risk", ""),
            # Backtest results
            "backtest_results": backtest_results,
            "backtest_metrics": backtest_metrics,
            "market_context": market_context_data,
            # Debug: agent analysis
            "debug": {
                "market_analysis": market_analysis,
                "news_analysis": news_analysis,
                "fundamentals_analysis": fundamentals_analysis,
                "bull_case": bull_case,
                "bear_case": bear_case,
                "portfolio_manager": raw_decision,
            },
            "analyzed_at": datetime.now().isoformat(),
            "cg_data": cg_data,
            "news_headlines": news,
        }

    def analyze_batch(
        self,
        crypto_list: list[dict],
        progress_callback: Optional[Callable[[str, float], None]] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> list[dict]:
        """
        Runs multi-agent analysis on a list of crypto assets.

        Args:
            crypto_list: list of dicts with each crypto's data
            progress_callback: function(msg, fraction) for updates
            stop_flag: function() -> bool for interruption

        Returns:
            List of dicts with results for each crypto
        """
        results = []
        total = len(crypto_list)

        for i, coin in enumerate(crypto_list):
            if stop_flag and stop_flag():
                print("[AIAnalyst] Analysis interrupted by user.")
                break

            symbol = coin.get("symbol", "?")
            fraction = i / total

            def per_coin_cb(msg: str, _coin_symbol=symbol, _i=i, _total=total, _base_frac=fraction):
                if progress_callback:
                    # Distribute progress per coin evenly
                    progress_callback(msg, _base_frac + 0.9 / _total * 0.1)

            if progress_callback:
                progress_callback(
                    f"🤖 AI Analysis: {symbol} ({i+1}/{total})...",
                    fraction
                )

            try:
                result = self.analyze_single(coin, progress_callback=per_coin_cb)
                results.append(result)
            except Exception as e:
                print(f"[AIAnalyst] Analysis error for {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "name": coin.get("name", symbol),
                    "current_price": coin.get("last_price", 0),
                    "target_price_1d": None,
                    "ai_change_pct_1d": None,
                    "change_pct_1d": coin.get("change_pct_1d", None),
                    "confidence": "N/A",
                    "rationale": f"Analysis error: {str(e)[:100]}",
                    "key_risk": "Error during processing.",
                    "debug": {},
                    "analyzed_at": datetime.now().isoformat(),
                })

            # Small sleep between assets to avoid rate limiting
            if i < total - 1:
                time.sleep(0.5)

        if progress_callback:
            progress_callback(f"✅ AI Analysis completed: {len(results)}/{total} crypto.", 1.0)

        return results
