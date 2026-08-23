# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

import json
import os
import threading
import ccxt
from datetime import datetime
from typing import Dict, List, Any, Optional

from core.data_manager import load_settings, BASE_DIR
from core.pre_flight_checker import PreFlightChecker

# Path for the portfolio audit file
PORTFOLIO_AUDIT_PATH = os.path.join(BASE_DIR, "data", "portfolio_audit.json")

# Default ensemble weights, expressed as percentages (they are stored that way
# in settings.json and edited as percentages by the AI Settings sliders).
DEFAULT_ENSEMBLE_WEIGHTS_PCT = {"tfm": 40.0, "pm": 35.0, "ai": 25.0}


def normalize_ensemble_weights(settings: dict) -> tuple[float, float, float]:
    """Reads the ensemble weights from *settings* and returns them as fractions.

    Accepts both the percentage form used by the UI (``40``/``35``/``25``) and a
    already-normalised fractional form (``0.40``/``0.35``/``0.25``); in either
    case the returned triple ``(w_tfm, w_pm, w_ai)`` sums to 1.0.
    """
    def _f(key, default):
        try:
            v = float(settings.get(key, default))
        except (TypeError, ValueError):
            return float(default)
        return v if v >= 0 else 0.0

    w_tfm = _f("ensemble_w_tfm", DEFAULT_ENSEMBLE_WEIGHTS_PCT["tfm"])
    w_pm = _f("ensemble_w_pm", DEFAULT_ENSEMBLE_WEIGHTS_PCT["pm"])
    w_ai = _f("ensemble_w_ai", DEFAULT_ENSEMBLE_WEIGHTS_PCT["ai"])

    total = w_tfm + w_pm + w_ai
    if total <= 0:
        d = DEFAULT_ENSEMBLE_WEIGHTS_PCT
        w_tfm, w_pm, w_ai = d["tfm"], d["pm"], d["ai"]
        total = w_tfm + w_pm + w_ai

    return w_tfm / total, w_pm / total, w_ai / total


class PortfolioManager:
    """
    Manages portfolio logic, target calculations, and orders.
    Interacts with CCXT to execute orders on the exchange.
    """
    
    def __init__(self, settings: dict = None, defer_network: bool = True, connect: bool = True):
        """
        Args:
            settings: configuration dict; loaded from disk when omitted.
            defer_network: when True (default) the clock sync and market catalogue
                are fetched on a background thread so constructing a
                PortfolioManager never blocks the caller — this class is
                instantiated from the Tk main thread during app start-up, and a
                slow or unreachable exchange used to freeze the whole window for
                the length of the CCXT timeout. Pass False when you need the
                markets to be populated as soon as the constructor returns.
            connect: set False to skip exchange creation entirely. Useful for the
                pure-computation entry points (``calculate_sizing``) used by the
                exporters, which never touch the network.
        """
        self.settings = settings if settings is not None else load_settings()
        self.exchange = None
        self._markets_ready = threading.Event()
        self._markets_lock = threading.Lock()
        if connect:
            self._init_exchange(defer_network=defer_network)
        else:
            self._markets_ready.set()

    @classmethod
    def for_sizing(cls, settings: dict = None) -> "PortfolioManager":
        """Offline instance for ensemble/sizing maths only — no exchange, no I/O."""
        return cls(settings, connect=False)

    def calculate_sizing(self, tfm_pct: float, pm_pct: float, ai_pct: float, fng_value: float, funding_rate: float = 0.0, pm_conf: float = 50.0, ai_conf: float = 50.0, tfm_conf: float = 50.0, ai_disabled: bool = False) -> tuple[str, str, float, float]:
        """
        Calculates position sizing and ensemble weighting based on confidence scores.
        """
        # The GUI stores the ensemble weights as percentages (40 / 35 / 25).
        # Normalise them to fractions summing to 1.0 up front, otherwise the
        # ±0.05 confidence adjustments below are lost in the rounding noise of
        # values two orders of magnitude larger.
        w_tfm, w_pm, w_ai = normalize_ensemble_weights(self.settings)

        enable_ai = self.settings.get("enable_ai_auto_trade", True)
        if ai_disabled or not enable_ai:
            w_tfm += w_ai / 2.0
            w_pm += w_ai / 2.0
            w_ai = 0.0
            ai_pct = 0.0
            active_models_count = 2
        else:
            active_models_count = 3

        # --- Dynamic adjustment based on Pattern Matching Confidence ---
        if pm_conf <= 33.0:
            w_pm -= 0.05
            w_tfm += 0.025
            if enable_ai: w_ai += 0.025
            else: w_tfm += 0.025
        elif pm_conf >= 66.0:
            w_pm += 0.05
            w_tfm -= 0.025
            if enable_ai: w_ai -= 0.025
            else: w_tfm -= 0.025
            
        # --- Dynamic adjustment based on TimesFM (Temporal Analysis) Confidence ---
        if tfm_conf <= 33.0:
            w_tfm -= 0.05
            w_pm += 0.025
            if enable_ai: w_ai += 0.025
            else: w_pm += 0.025
        elif tfm_conf >= 66.0:
            w_tfm += 0.05
            w_pm -= 0.025
            if enable_ai: w_ai -= 0.025
            else: w_pm -= 0.025

        if enable_ai:
            # --- Dynamic adjustment based on Advanced AI Analysis Confidence ---
            if ai_conf <= 33.0:
                w_ai -= 0.05
                w_tfm += 0.025
                w_pm += 0.025
            elif ai_conf >= 66.0:
                w_ai += 0.05
                w_tfm -= 0.025
                w_pm -= 0.025
            
        # Ensure weights do not become negative
        w_tfm = max(0.0, w_tfm)
        w_pm = max(0.0, w_pm)
        w_ai = max(0.0, w_ai)
        
        # Weight normalization to 1.0 in case of aberrations
        total_w = w_tfm + w_pm + w_ai
        if total_w > 0:
            w_tfm /= total_w
            w_pm /= total_w
            w_ai /= total_w

        expected_return_pct = (tfm_pct * w_tfm) + (pm_pct * w_pm) + (ai_pct * w_ai)
        
        # Check agreement
        pos_count = sum(1 for p in [tfm_pct, pm_pct, ai_pct] if p > 0)
        neg_count = sum(1 for p in [tfm_pct, pm_pct, ai_pct] if p < 0)
        
        final_signal = "HOLD"
        rule_name = "NO TRADE"
        
        min_ret = float(self.settings.get("ensemble_min_return_pct", 0.30))
        
        if pos_count >= 2 and expected_return_pct > min_ret:
            final_signal = "BUY"
            rule_name = "ENSEMBLE LONG"
        elif neg_count >= 2 and expected_return_pct < -min_ret:
            final_signal = "SELL"
            rule_name = "ENSEMBLE SHORT"
            
        # Penalties calculation
        size_multiplier = 1.0 if final_signal in ["BUY", "SELL"] else 0.0
        
        if final_signal in ["BUY", "SELL"]:
            # Partial alignment
            max_agree = max(pos_count, neg_count)
            if max_agree < active_models_count:
                size_multiplier *= 0.60  # -40% size
                rule_name += " (Partial)"
            
            if final_signal == "BUY":
                if funding_rate > 0.05 or fng_value > 85:
                    size_multiplier *= 0.40  # -60% size
                    rule_name += " (Risk Penalty)"
            elif final_signal == "SELL":
                if funding_rate < -0.02:
                    size_multiplier = 0.0  # Cancel
                    final_signal = "HOLD"
                    rule_name = "SQUEEZE RISK"

        return rule_name, final_signal, size_multiplier, expected_return_pct

    def get_funding_rate(self, symbol: str) -> float:
        if not self.exchange: return 0.0
        try:
            if not self.ensure_markets():
                return 0.0
            market = self.exchange.market(symbol) if symbol in self.exchange.markets else {}
            # If it is spot, search for perp
            if not market.get('swap', False) and not market.get('future', False):
                base = market.get('base', symbol.split('/')[0])
                quote = market.get('quote', 'USDT')
                perp_symbol = f"{base}/{quote}:{quote}"
                if perp_symbol in self.exchange.markets:
                    symbol = perp_symbol
            
            funding = self.exchange.fetch_funding_rate(symbol)
            return float(funding.get('fundingRate', 0.0)) * 100
        except Exception:
            return 0.0
        
    def _init_exchange(self, defer_network: bool = True):
        """Initializes the CCXT instance based on settings."""
        # Retrieve settings or set defaults
        pm_settings = self.settings.get("portfolio_manager", {})
        exchange_id = pm_settings.get("exchange_id", "bingx").lower()
        api_key = pm_settings.get("api_key", "")
        api_secret = pm_settings.get("api_secret", "")
        
        if exchange_id and hasattr(ccxt, exchange_id):
            exchange_class = getattr(ccxt, exchange_id)
            
            # Coinbase and PEM keys: ensure any literal "\\n" become real newlines
            if exchange_id == "coinbase":
                api_secret = api_secret.replace("\\n", "\n")
                
            self.exchange = exchange_class({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'options': {
                    'adjustForTimeDifference': True,
                    'recvWindow': 10000
                }
            })
            
            # Monkeypatch nonce method for BingX, since native CCXT implementation
            # does not subtract 'timeDifference' in ccxt.bingx.nonce()
            if exchange_id == "bingx":
                self.exchange.nonce = lambda: self.exchange.milliseconds() - self.exchange.options.get('timeDifference', 0)

            if defer_network:
                threading.Thread(target=self._warmup_exchange, daemon=True).start()
            else:
                self._warmup_exchange()
        else:
            if exchange_id:
                print(f"[PortfolioManager] Unknown exchange id '{exchange_id}' — no exchange configured.")
            self._markets_ready.set()

    def _warmup_exchange(self):
        """Syncs the exchange clock and loads the market catalogue (blocking)."""
        try:
            if self.exchange is None:
                return
            # Force synchronization of local time with the exchange server time
            try:
                if hasattr(self.exchange, 'load_time'):
                    self.exchange.load_time()
                elif hasattr(self.exchange, 'load_time_difference'):
                    self.exchange.load_time_difference()
            except Exception as e:
                print(f"[PortfolioManager] Unable to execute load_time / load_time_difference: {e}")

            # Try to load markets to populate currencies
            try:
                self.exchange.load_markets()
            except Exception as e:
                print(f"[PortfolioManager] Could not load markets: {e}")
        finally:
            self._markets_ready.set()

    def ensure_markets(self, timeout: float = 30.0) -> bool:
        """Blocks until the market catalogue is available. Safe to call from
        worker threads; returns True when markets are populated."""
        if self.exchange is None:
            return False
        self._markets_ready.wait(timeout=timeout)
        if getattr(self.exchange, "markets", None):
            return True
        # The warm-up may have failed (offline at start-up) — retry once, guarded
        # so concurrent callers do not stampede the endpoint.
        with self._markets_lock:
            if getattr(self.exchange, "markets", None):
                return True
            try:
                self.exchange.load_markets()
            except Exception as e:
                print(f"[PortfolioManager] ensure_markets failed: {e}")
        return bool(getattr(self.exchange, "markets", None))

    def get_balance(self, positions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Retrieves the balance via the exchange. If not configured, does not attempt download."""
        if self.exchange and self.exchange.apiKey:
            try:
                account_types = [None]
                if self.exchange.options and isinstance(self.exchange.options, dict):
                    accounts_by_type = self.exchange.options.get('accountsByType', {})
                    if accounts_by_type:
                        unique_internal = set()
                        account_types = []
                        for c_type, i_type in accounts_by_type.items():
                            if i_type not in unique_internal:
                                unique_internal.add(i_type)
                                account_types.append(c_type)
                
                if not account_types:
                    account_types = ['spot', 'swap', 'funding']
                
                usdt_available = 0.0
                usdt_total_wallets = 0.0
                raw_balances = {}
                seen_signatures = set()
                
                for acc_type in account_types:
                    params = {'type': acc_type} if acc_type else {}
                    try:
                        balance = self.exchange.fetch_balance(params)
                        
                        sig_items = []
                        for currency, data in balance.items():
                            if isinstance(data, dict) and 'total' in data and data['total'] > 0:
                                sig_items.append(f"{currency}:{data.get('free', 0)}:{data.get('total', 0)}")
                        
                        signature = "|".join(sorted(sig_items))
                        if signature and signature in seen_signatures:
                            continue
                        if signature:
                            seen_signatures.add(signature)
                            
                        if acc_type:
                            raw_balances[acc_type] = balance
                        else:
                            raw_balances = balance
                            
                        usdt_available += balance.get('USDT', {}).get('free', 0.0)
                        usdt_total_wallets += balance.get('USDT', {}).get('total', 0.0)
                    except Exception:
                        # Some types might not be supported or have no balance
                        pass
                
                if positions is None:
                    positions = self.get_positions()
                    
                total_usdt = sum(p.get('value', 0.0) for p in positions if p.get('type') != 'Futures')
                if total_usdt == 0:
                    total_usdt = usdt_total_wallets
                
                # Add unrealized PnL if necessary (note: often already included in USDT swap balance)
                # If preferred to display it: total_usdt += total_pnl
                
                return {
                    "available": usdt_available,
                    "total": total_usdt,
                    "currency": "USDT",
                    "raw": raw_balances
                }
            except Exception as e:
                print(f"[PortfolioManager] Error fetching balance: {e}")
                
        # If not configured or in error, returns empty balance
        return {
            "available": 0.0,
            "total": 0.0,
            "currency": "USDT",
            "raw": {}
        }
        
    def get_positions(self) -> List[Dict[str, Any]]:
        """Retrieves open positions via the exchange."""
        if self.exchange and self.exchange.apiKey:
            # Called from worker threads; markets may still be warming up.
            self.ensure_markets()
            positions = []
            try:
                tickers = {}
                try:
                    if self.exchange.has.get('fetchTickers'):
                        tickers = self.exchange.fetch_tickers()
                except Exception as e:
                    print(f"Error fetching tickers: {e}")

                account_types = [None]
                if self.exchange.options and isinstance(self.exchange.options, dict):
                    accounts_by_type = self.exchange.options.get('accountsByType', {})
                    if accounts_by_type:
                        unique_internal = set()
                        account_types = []
                        for c_type, i_type in accounts_by_type.items():
                            if i_type not in unique_internal:
                                unique_internal.add(i_type)
                                account_types.append(c_type)
                
                if not account_types:
                    account_types = ['spot', 'swap', 'funding']
                
                seen_signatures = set()
                
                for acc_type in account_types:
                    params = {'type': acc_type} if acc_type else {}
                    try:
                        balance = self.exchange.fetch_balance(params)
                        
                        # Generates signature to deduplicate unified wallets returned multiple times
                        sig_items = []
                        for currency, data in balance.items():
                            if isinstance(data, dict) and 'total' in data and data['total'] > 0:
                                sig_items.append(f"{currency}:{data.get('free', 0)}:{data.get('total', 0)}")
                        
                        signature = "|".join(sorted(sig_items))
                        if signature and signature in seen_signatures:
                            continue
                        if signature:
                            seen_signatures.add(signature)
                            
                        for currency, data in balance.get('total', {}).items():
                            if data > 0:
                                symbol = f"{currency}/USDT"
                                price = 0.0
                                if currency == 'USDT':
                                    price = 1.0
                                elif symbol in tickers and tickers[symbol].get('last'):
                                    price = tickers[symbol].get('last', 0.0)
                                elif f"{currency}USDT" in tickers and tickers[f"{currency}USDT"].get('last'):
                                    price = tickers[f"{currency}USDT"].get('last', 0.0)
                                
                                # Fallback
                                if price == 0.0 and currency != 'USDT':
                                    try:
                                        import yfinance as yf
                                        ticker_yf = f"{currency}-USD"
                                        tk = yf.Ticker(ticker_yf)
                                        p = getattr(tk.fast_info, "last_price", 0.0)
                                        if p: price = p
                                    except Exception:
                                        pass
                                    
                                value = data * price
                                
                                currency_info = self.exchange.currencies.get(currency, {}) if hasattr(self.exchange, 'currencies') and self.exchange.currencies else {}
                                fullname = currency_info.get('name') or currency
                                
                                type_label = f"Spot ({acc_type})" if acc_type else "Spot"
                                
                                positions.append({
                                    "asset": currency,
                                    "fullname": fullname,
                                    "type": type_label,
                                    "direction": "LONG",
                                    "leverage": "1x",
                                    "sl": "N/A",
                                    "tp": "N/A",
                                    "quantity": data,
                                    "value": value,
                                    "avg_price": price,
                                    "current_price": price,
                                    "pnl": 0.0
                                })
                    except Exception:
                        pass
            except Exception as e:
                print(f"[PortfolioManager] Error fetching spot balance: {e}")
                
            # Fetch derivatives positions if supported
            if self.exchange.has.get('fetchPositions'):
                # Avoid fetchPositions on coinbase if not configured
                if self.exchange.id != 'coinbase':
                    try:
                        deriv_positions = self.exchange.fetch_positions()
                        for p in deriv_positions:
                            if p.get('contracts', 0) > 0:
                                asset_name = p.get('symbol', '').replace('/USDT:USDT', '').replace(':USDT', '')
                                
                                pnl = float(p.get('unrealizedPnl', 0.0))
                                entry_price = float(p.get('entryPrice', 0.0))
                                mark_price = float(p.get('markPrice', 0.0))
                                leverage = float(p.get('leverage', 1.0))
                                side = p.get('side', 'long')
                                
                                # For maximum robustness and consistency across exchanges, always calculate manually if we have entry/mark prices
                                pnl_pct = None
                                if entry_price > 0 and mark_price > 0:
                                    if side == 'long':
                                        pnl_pct = (mark_price - entry_price) / entry_price * 100 * leverage
                                    elif side == 'short':
                                        pnl_pct = (entry_price - mark_price) / entry_price * 100 * leverage
                                
                                if pnl_pct is None:
                                    pnl_pct = p.get('percentage')
                                if pnl_pct is None:
                                    pnl_pct = 0.0
                                            
                                # Retrieves active SL/TP from the exchange for this position
                                sl_price = 'N/A'
                                tp_price = 'N/A'
                                try:
                                    symbol = p.get('symbol')
                                    if symbol:
                                        open_orders = self.exchange.fetch_open_orders(symbol)
                                        for o in open_orders:
                                            order_pos_side = o.get('info', {}).get('positionSide', '').upper()
                                            pos_side_upper = side.upper()
                                            
                                            if order_pos_side == pos_side_upper:
                                                is_sl = False
                                                is_tp = False
                                                o_type = str(o.get('info', {}).get('type', o.get('type', ''))).upper()
                                                if 'STOP' in o_type:
                                                    is_sl = True
                                                elif 'TAKE_PROFIT' in o_type:
                                                    is_tp = True
                                                    
                                                stop_pr_val = o.get('stopLossPrice') or o.get('takeProfitPrice') or o.get('stopPrice') or o.get('triggerPrice')
                                                if not stop_pr_val:
                                                    stop_pr_val = o.get('info', {}).get('stopPrice')
                                                    
                                                if stop_pr_val:
                                                    try:
                                                        stop_pr_val = float(stop_pr_val)
                                                    except:
                                                        pass
                                                        
                                                if is_sl and stop_pr_val:
                                                    sl_price = str(stop_pr_val)
                                                elif is_tp and stop_pr_val:
                                                    tp_price = str(stop_pr_val)
                                except Exception as e_ord:
                                    print(f"[PortfolioManager] Unable to retrieve orders for {p.get('symbol')}: {e_ord}")
                                            
                                positions.append({
                                    "asset": asset_name,
                                    "fullname": p.get('symbol', asset_name),
                                    "type": "Futures",
                                    "direction": side.upper(),
                                    "leverage": f"{leverage}x",
                                    "sl": sl_price,
                                    "tp": tp_price,
                                    "quantity": p.get('contracts', 0),
                                    "value": p.get('notional', p.get('contracts', 0) * mark_price),
                                    "avg_price": entry_price,
                                    "current_price": mark_price,
                                    "pnl": pnl,
                                    "pnl_pct": pnl_pct
                                })
                    except Exception as e:
                        print(f"[PortfolioManager] Error fetching futures positions: {e}")
            
            return positions
        return []

    def generate_orders(self, analysis_results: List[Dict[str, Any]], discarded_callback=None) -> List[Dict[str, Any]]:
        """
        Generates orders on derivatives with leverage proportional to confidence and sizing based on signals.
        """
        pm_settings = self.settings.get("portfolio_manager", {})
        
        min_confidence = float(pm_settings.get("minimumConfidence", 50.0))
        max_open_pos = int(pm_settings.get("maxOpenPositions", 5))
        max_pos_pct = float(pm_settings.get("maxPositionPercent", 20.0)) / 100.0

        balance_info = self.get_balance()
        total_capital = balance_info["total"]
        available_capital = balance_info["available"]
        
        # Assets already in portfolio (only Futures considered for max_open_pos count)
        current_positions = self.get_positions()
        active_assets = {}
        for p in current_positions:
            if float(p.get("quantity", 0)) > 0 and p.get("type") == "Futures":
                asset = p.get("asset")
                if asset not in active_assets:
                    active_assets[asset] = []
                active_assets[asset].append(p)
        
        max_cap_usage_pct = float(pm_settings.get("maxCapitalUsagePercent", 100.0)) / 100.0
        investable_capital = total_capital * max_cap_usage_pct
        
        # --- New Risk Management Settings ---
        allow_multiple_entries = self.settings.get("allow_multiple_entries", False)
        dca_distance_pct = float(self.settings.get("dca_distance_pct", 2.0)) / 100.0
        # "use_timesfm_auto" is deliberately not read here: the setting exists
        # and is described as "require TimesFM confirmation", but no code path
        # acts on it. Documented as such under Scope and limitations in the
        # README; do not wire it up without deciding what it should mean.
        stop_and_reverse = self.settings.get("stop_and_reverse", True)
        
        valid_signals = []
        for res in analysis_results:
            fng_value = res.get("market_context", {}).get("fng_value", 50)
            asset_sym = res.get("symbol", "")
            
            tfm_pct = res.get("change_pct_1d", 0.0)  # TimesFM % (default)
            if tfm_pct is None: tfm_pct = 0.0
            
            pm_pct = res.get("btc_expected_move", 0.0)  # Pattern Matching %
            if pm_pct is None: pm_pct = 0.0
            
            ai_pct = res.get("ai_change_pct_1d", tfm_pct)  # AI Analyst % (If none, fallback to tfm)
            if ai_pct is None: ai_pct = 0.0
            
            funding_rate = self.get_funding_rate(asset_sym)
            
            pm_conf = res.get("btc_pred_confidence", 50.0)
            if pm_conf is None: pm_conf = 50.0
            
            ai_conf = res.get("confidence", 50.0)
            if ai_conf is None or str(ai_conf).upper() in ["N/A", "DISABLED"]: ai_conf = 50.0
            else: ai_conf = float(ai_conf)
            
            tfm_conf = res.get("tfm_confidence") or res.get("confidence")
            if tfm_conf is None or str(tfm_conf).upper() in ["N/A", "DISABLED"]: tfm_conf = 50.0
            else: tfm_conf = float(tfm_conf)

            ai_disabled = (str(res.get("signal", "")).upper() == "DISABLED")
            
            rule_name, final_signal, size_multiplier, exp_ret = self.calculate_sizing(
                tfm_pct=tfm_pct,
                pm_pct=pm_pct,
                ai_pct=ai_pct,
                fng_value=fng_value,
                funding_rate=funding_rate,
                pm_conf=pm_conf,
                ai_conf=ai_conf,
                tfm_conf=tfm_conf,
                ai_disabled=ai_disabled
            )
            
            res["expected_return_pct"] = exp_ret
            res["signal_1d"] = final_signal
            
            if ai_disabled:
                conf = (pm_conf + tfm_conf) / 2.0
            else:
                conf = float(res.get("confidence", 50.0) if str(res.get("confidence", "")).upper() not in ["DISABLED", "N/A"] else 50.0)
                
            if final_signal in ["BUY", "SELL"] and size_multiplier > 0.0:
                asset_sym = res.get("symbol", "")

                # Minimum-confidence gate. This threshold is exposed in the
                # Portfolio settings and documented as "orders are sent only if
                # the confidence is above the set threshold", but it was only
                # ever used to scale the position size — signals below it were
                # still sent. Enforce it, and notify the caller so Auto Trading
                # can apply its low-confidence cooldown.
                if conf < min_confidence:
                    print(f"[PortfolioManager] Signal on {asset_sym} discarded: "
                          f"confidence {conf:.0f}% < minimum {min_confidence:.0f}%.")
                    if discarded_callback:
                        try:
                            discarded_callback(asset_sym, "low_confidence")
                        except Exception as e:
                            print(f"[PortfolioManager] discarded_callback error: {e}")
                    continue


                # Portfolio asset management
                if asset_sym in active_assets:
                    positions_for_asset = active_assets[asset_sym]
                    signal_dir = "LONG" if final_signal == "BUY" else "SHORT"
                    
                    # 1. Opposite position management (closure/stop and reverse)
                    opp_pos = next((p for p in positions_for_asset if p.get("direction") != signal_dir), None)
                    if opp_pos:
                        if stop_and_reverse:
                            print(f"[PortfolioManager] Opposite signal on {asset_sym}. Stop and Reverse: closing previous position...")
                            try:
                                self.sell_portfolio_assets([opp_pos])
                                if opp_pos in positions_for_asset:
                                    positions_for_asset.remove(opp_pos)
                                if not positions_for_asset:
                                    del active_assets[asset_sym]
                            except Exception as e:
                                print(f"[PortfolioManager] Error closing for Stop & Reverse on {asset_sym}: {e}")
                                continue
                        else:
                            pnl_pct = float(opp_pos.get("pnl_pct", 0.0))
                            if pnl_pct > 0:
                                print(f"[PortfolioManager] Position on {asset_sym} in opposite direction but in profit ({pnl_pct:.2f}%). Closing previous position...")
                                try:
                                    self.sell_portfolio_assets([opp_pos])
                                    if opp_pos in positions_for_asset:
                                        positions_for_asset.remove(opp_pos)
                                    if not positions_for_asset:
                                        del active_assets[asset_sym]
                                except Exception as e:
                                    print(f"[PortfolioManager] Error closing position on {asset_sym}: {e}")
                            else:
                                print(f"[PortfolioManager] Position on {asset_sym} in opposite direction and in loss ({pnl_pct:.2f}%). Maintained open (hedge in loss allowed).")
                    
                    # 2. Same direction position management (DCA/multi-entry)
                    same_pos = next((p for p in positions_for_asset if p.get("direction") == signal_dir), None)
                    if same_pos:
                        if not allow_multiple_entries:
                            print(f"[PortfolioManager] Multi-entry disabled. Order on {asset_sym} ignored for anti-spam.")
                            continue
                        else:
                            curr_price_est = float(res.get("current_price", res.get("last_price", 1)))
                            avg_price = float(same_pos.get("avg_price", curr_price_est))
                            if avg_price > 0:
                                distance = abs(curr_price_est - avg_price) / avg_price
                                if distance < dca_distance_pct:
                                    print(f"[PortfolioManager] Price distance ({distance*100:.2f}%) < minimum DCA ({dca_distance_pct*100:.2f}%). DCA ignored for {asset_sym}.")
                                    continue
                            print(f"[PortfolioManager] DCA authorized for {asset_sym} ({signal_dir}).")
                    
                currency_info = self.exchange.currencies.get(asset_sym, {}) if hasattr(self, 'exchange') and self.exchange and hasattr(self.exchange, 'currencies') and self.exchange.currencies else {}
                fullname = currency_info.get('name') or asset_sym
                
                valid_signals.append({
                    "asset": asset_sym,
                    "fullname": fullname,
                    "signal": final_signal,
                    "rule_name": rule_name,
                    "size_multiplier": size_multiplier,
                    "confidence": conf,
                    "target_price": res.get("target_price_1d"),
                    "stop_loss": res.get("stop_loss"),
                    "take_profit": res.get("take_profit"),
                    "current_price": res.get("current_price", res.get("last_price"))
                })
                
            else:
                print(f"[PortfolioManager] Signal on {res.get('symbol', '')} discarded ({rule_name} -> Exp. Return: {exp_ret:.2f}%).")
                
        # Sort by descending confidence
        valid_signals.sort(key=lambda x: x["confidence"], reverse=True)
        
        # Pre-allocate according to remaining open position slots
        top_signals = []
        auto_trade_settings = self.settings.get("auto_trading", {})
        
        # If there is no open position for BTC, reset the counter
        if "BTC" not in active_assets:
            auto_trade_settings["btc_trade_count"] = 0
            
        slots_taken = int(auto_trade_settings.get("btc_trade_count", 0))

        for sig in valid_signals:
            if slots_taken < max_open_pos:
                top_signals.append(sig)
                slots_taken += 1
                auto_trade_settings["btc_trade_count"] = slots_taken
            else:
                # Limit reached: check if we can close the position (if in profit)
                best_pos_asset = sig["asset"]
                if best_pos_asset in active_assets:
                    positions_for_asset = active_assets[best_pos_asset]
                    # Find a profitable position to liquidate
                    profitable_pos = next((p for p in positions_for_asset if float(p.get("pnl_pct", 0.0)) > 0), None)
                    if profitable_pos:
                        pnl = float(profitable_pos.get("pnl_pct", 0.0))
                        print(f"[PortfolioManager] Max open positions reached ({max_open_pos}). Liquidating position on {best_pos_asset} ({profitable_pos.get('direction')}) with profit ({pnl:.2f}%).")
                        try:
                            self.sell_portfolio_assets([profitable_pos])
                            if profitable_pos in positions_for_asset:
                                positions_for_asset.remove(profitable_pos)
                            if not positions_for_asset:
                                del active_assets[best_pos_asset]
                            auto_trade_settings["btc_trade_count"] = len(positions_for_asset)
                            top_signals.append(sig)
                        except Exception as e:
                            print(f"[PortfolioManager] Error liquidating {best_pos_asset}: {e}")
                    else:
                        print(f"[PortfolioManager] Max open positions reached ({max_open_pos}) and position(s) in loss. Signal ignored. Triggering global cooldown of 3 runs.")
                        auto_trade_settings["global_cooldown"] = 3
                else:
                    # Fallback
                    auto_trade_settings["btc_trade_count"] = 0
                    top_signals.append(sig)
                    
        self.settings["auto_trading"] = auto_trade_settings
        import core.data_manager as dman
        dman.save_settings(self.settings)

        if len(top_signals) == 0 and valid_signals:
            print(f"[PortfolioManager] No order generated: max open positions ({max_open_pos}) reached and position in loss.")
        
        sizing_mode = self.settings.get("sizing_mode", "margin_pct")
        risk_per_trade_pct = float(self.settings.get("risk_per_trade_pct", 1.5)) / 100.0
        
        # Pre-calculates SL/TP to determine risk, and consequently ideal_capital
        for sig in top_signals:
            curr_p = sig.get("current_price", 0)
            leverage = int(pm_settings.get("maxLeverage", 10))
            if leverage < 1: leverage = 1
            
            try:
                sl = float(sig.get("stop_loss")) if sig.get("stop_loss") is not None else None
            except:
                sl = None
            try:
                tp = float(sig.get("take_profit")) if sig.get("take_profit") is not None else None
            except:
                tp = None

            # Dynamic Fallback based on 15m ATR if SL or TP are missing
            if (sl is None or tp is None) and curr_p and curr_p > 0:
                atr_pct = 0.03
                try:
                    if self.exchange:
                        markets = getattr(self.exchange, "markets", None) or {}
                        if not markets:
                            self.exchange.load_markets()
                            markets = self.exchange.markets
                        target_sym = f"{sig['asset'].upper()}/USDT:USDT" if f"{sig['asset'].upper()}/USDT:USDT" in markets else f"{sig['asset'].upper()}/USDT"
                        ohlcv_15m = self.exchange.fetch_ohlcv(target_sym, timeframe="15m", limit=30)
                        if ohlcv_15m:
                            import pandas as pd
                            df_15 = pd.DataFrame(ohlcv_15m, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
                            df_15["Close"] = pd.to_numeric(df_15["Close"])
                            df_15["High"] = pd.to_numeric(df_15["High"])
                            df_15["Low"] = pd.to_numeric(df_15["Low"])
                            
                            df_tail = df_15.copy()
                            df_tail['H-L'] = df_tail['High'] - df_tail['Low']
                            df_tail['H-C'] = abs(df_tail['High'] - df_tail['Close'].shift(1))
                            df_tail['L-C'] = abs(df_tail['Low'] - df_tail['Close'].shift(1))
                            df_tail['TR'] = df_tail[['H-L', 'H-C', 'L-C']].max(axis=1)
                            atr_val = df_tail['TR'].rolling(14).mean().iloc[-1]
                            atr_pct = (atr_val / curr_p) * 2.0  # Base volatility distance for scalping
                            print(f"[PortfolioManager] 15m ATR calculated for {sig['asset']}: {atr_pct*100:.2f}%")
                except Exception as e:
                    print(f"[PortfolioManager] Error fetching 15m ATR for {sig['asset']}: {e}")
                    import core.data_manager as dman
                    df = dman.load_historical(sig["asset"])
                    if df is not None and not df.empty and len(df) > 14 and 'High' in df.columns and 'Low' in df.columns and 'Close' in df.columns:
                        try:
                            df_tail = df.tail(15).copy()
                            df_tail['H-L'] = df_tail['High'] - df_tail['Low']
                            df_tail['H-C'] = abs(df_tail['High'] - df_tail['Close'].shift(1))
                            df_tail['L-C'] = abs(df_tail['Low'] - df_tail['Close'].shift(1))
                            df_tail['TR'] = df_tail[['H-L', 'H-C', 'L-C']].max(axis=1)
                            atr_val = df_tail['TR'].rolling(14).mean().iloc[-1]
                            atr_pct = (atr_val / curr_p) * 1.5
                        except:
                            pass
                
                if sl is None:
                    sl_dist = atr_pct if atr_pct > 0 else 0.03
                    if sig["signal"] == "BUY": sl = curr_p * (1 - sl_dist)
                    else: sl = curr_p * (1 + sl_dist)
                if tp is None:
                    tp_dist = atr_pct * 2.0 if atr_pct > 0 else 0.05
                    if sig["signal"] == "BUY": tp = curr_p * (1 + tp_dist)
                    else: tp = curr_p * (1 - tp_dist)
                    
            # Dynamic Leverage calculation based on SL
            if sl is not None and curr_p and curr_p > 0:
                sl_dist = abs(curr_p - sl) / curr_p
                if sl_dist > 0:
                    safe_lev = int(0.80 / sl_dist)
                    leverage = min(leverage, max(1, safe_lev))

            sig["calc_sl"] = sl
            sig["calc_tp"] = tp
            sig["calc_leverage"] = leverage

            # Assign a weight based on confidence
            scale = 0.5 + 0.5 * ((sig["confidence"] - min_confidence) / max(1.0, 100 - min_confidence))
            scale = max(0.1, min(1.0, scale))
            
            if sizing_mode == "risk_pct" and curr_p and curr_p > 0 and sl:
                sl_distance_pct = abs(curr_p - sl) / curr_p
                if sl_distance_pct <= 0: sl_distance_pct = 0.01
                
                risk_amount = total_capital * risk_per_trade_pct
                nominal_size = risk_amount / sl_distance_pct
                nominal_size = nominal_size * scale * sig["size_multiplier"]
                
                margin_required = nominal_size / leverage
                
                if margin_required > (investable_capital * max_pos_pct):
                    margin_required = investable_capital * max_pos_pct
                    
                sig["ideal_capital"] = margin_required
            else:
                ideal_pos_capital = investable_capital * max_pos_pct
                sig["ideal_capital"] = ideal_pos_capital * scale * sig["size_multiplier"]
            
        total_needed = sum(sig["ideal_capital"] for sig in top_signals)
        
        if top_signals and total_needed > available_capital:
            # Reduce proportionally to fit the available budget
            reduction_factor = available_capital / total_needed
            for sig in top_signals:
                sig["actual_capital"] = sig["ideal_capital"] * reduction_factor
        else:
            for sig in top_signals:
                sig["actual_capital"] = sig.get("ideal_capital", 0.0)
            
        orders = []
        for sig in top_signals:
            if sig["actual_capital"] <= 0:
                print(f"[PortfolioManager] No order generated for {sig['asset']}: Allocated capital <= 0 (Available: {available_capital}).")
                continue
                
            leverage = sig["calc_leverage"]
            sl = sig["calc_sl"]
            tp = sig["calc_tp"]
            curr_p = sig.get("current_price", 0)

            # Capping ROI% based on user settings
            if curr_p and curr_p > 0:
                max_sl_roi = float(pm_settings.get("maxStopLossROI", 80.0))
                max_tp_roi = float(pm_settings.get("maxTakeProfitROI", 200.0))
                
                if sl is not None:
                    sl_dist = abs(curr_p - sl) / curr_p
                    sl_roi = sl_dist * leverage * 100
                    if sl_roi > max_sl_roi:
                        allowed_dist = max_sl_roi / (leverage * 100)
                        if sig["signal"] == "BUY":
                            sl = curr_p * (1 - allowed_dist)
                        else:
                            sl = curr_p * (1 + allowed_dist)
                            
                if tp is not None:
                    tp_dist = abs(curr_p - tp) / curr_p
                    tp_roi = tp_dist * leverage * 100
                    if tp_roi > max_tp_roi:
                        allowed_dist = max_tp_roi / (leverage * 100)
                        if sig["signal"] == "BUY":
                            tp = curr_p * (1 + allowed_dist)
                        else:
                            tp = curr_p * (1 - allowed_dist)

            # Sanity check: SL/TP must be consistent with direction
            if sig["signal"] == "BUY":
                if sl and sl >= curr_p:
                    sl = curr_p * 0.97  # Force SL below price for LONG
                if tp and tp <= curr_p:
                    tp = curr_p * 1.05  # Force TP above price for LONG
            else:  # SELL
                if sl and sl <= curr_p:
                    sl = curr_p * 1.03  # Force SL above price for SHORT
                if tp and tp >= curr_p:
                    tp = curr_p * 0.95  # Force TP below price for SHORT

            # Auto-adaptation of leverage to avoid liquidation before SL
            if sl and curr_p and curr_p > 0:
                sl_distance = abs(curr_p - sl) / curr_p
                if sl_distance > 0:
                    safe_leverage = int(0.80 / sl_distance)
                    leverage = min(leverage, max(1, safe_leverage))

            direction = "LONG" if sig["signal"] == "BUY" else "SHORT"
            action = "BUY" if sig["signal"] == "BUY" else "SELL"
            
            orders.append({
                "action": action,
                "asset": sig["asset"],
                "fullname": sig["fullname"],
                "direction": direction,
                "amount": sig["actual_capital"],  # allocated margin
                "leverage": leverage,
                "quantity": 0,  # to be recalculated with ticker
                "stopLoss": sl,
                "takeProfit": tp,
                "current_price": curr_p,
                "priority": "NORMAL",
                "reason": f"[{sig['rule_name']}] {direction} (Conf: {sig['confidence']:.0f}%)"
            })
            
        return orders

    def place_orders(self, orders: List[Dict[str, Any]]):
        """
        Executes orders via CCXT (Derivatives).
        """
        pm_settings = self.settings.get("portfolio_manager", {})
        use_exchange = pm_settings.get("useExchangeBalance", False)

        if use_exchange and self.exchange is not None:
            self.ensure_markets()

        executed = []
        for order in orders:
            if not use_exchange or not self.exchange:
                # Log in simulated mode
                order["status"] = "SIMULATED"
                executed.append(order)
                continue
                
            try:
                # Base CCXT convention for USDT-margined swap
                symbol = f"{order['asset']}/USDT:USDT" 
                
                try:
                    # Set leverage
                    if self.exchange.has.get('setLeverage'):
                        # In Hedge mode (e.g. BingX) need to specify the side
                        self.exchange.set_leverage(order["leverage"], symbol, params={"side": order["direction"]})
                except Exception as e:
                    print(f"Error setting leverage for {symbol}: {e}")
                
                side = 'buy' if order["direction"] == "LONG" else 'sell'
                
                # --- PRE-FLIGHT CHECK ---
                pf_passed, pf_reason = PreFlightChecker.run_checks(
                    order, self.exchange, symbol, self.settings
                )
                if not pf_passed:
                    print(f"[PortfolioManager] Order {symbol} discarded by Pre-Flight: {pf_reason}")
                    order["status"] = "CANCELLED"
                    order["error"] = pf_reason
                    executed.append(order)
                    continue
                # ------------------------
                
                # Use the price updated by PreFlightChecker
                current_price = order.get("current_price")
                if not current_price or current_price <= 0:
                    try:
                        ticker = self.exchange.fetch_ticker(symbol)
                        current_price = ticker['last']
                    except:
                        current_price = 1.0  # unlikely fallback, avoids crash
                    
                notional = order["amount"] * order["leverage"]
                quantity = notional / current_price if current_price > 0 else 0
                order["quantity"] = quantity
                
                params = {
                    "positionSide": order["direction"]  # Fundamental in Hedge mode
                }
                
                # We first execute the main order
                res = self.exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side,
                    amount=quantity,
                    params=params
                )
                order["warning"] = "Order opened."
                
                # SL and TP are passed directly from the order generated by the AI
                exec_price = res.get('average') or res.get('price') or current_price
                if exec_price:
                    exec_price = float(exec_price)

                # We place SL/TP separately
                if order.get("stopLoss") or order.get("takeProfit"):
                    import time
                    time.sleep(2.5)  # Wait a few seconds to ensure position is registered

                    # Final verification with current price to avoid rejection (e.g. "Take Profit should be lower...")
                    try:
                        latest_ticker = self.exchange.fetch_ticker(symbol)
                        latest_price = latest_ticker['last']
                    except:
                        latest_price = exec_price
                    
                    close_side = 'sell' if order["direction"] == "LONG" else 'buy'
                    
                    if order.get("stopLoss"):
                        sl_price = float(order["stopLoss"])
                        # For LONGs, SL must be < current price. For SHORTs, SL must be > current price.
                        if order["direction"] == "LONG" and sl_price >= latest_price:
                            sl_price = latest_price * 0.999  # adjust slightly below current price
                        elif order["direction"] == "SHORT" and sl_price <= latest_price:
                            sl_price = latest_price * 1.001
                            
                        try:
                            self.exchange.create_order(
                                symbol=symbol,
                                type='STOP_MARKET',
                                side=close_side,
                                amount=quantity,
                                params={
                                    "positionSide": order["direction"],
                                    "PositionSide": order["direction"],
                                    "stopPrice": sl_price,
                                    "triggerPrice": sl_price
                                }
                            )
                            order["warning"] += " SL OK."
                        except Exception as esl:
                            print(f"Error setting SL for {symbol}: {esl}")
                            order["warning"] += " SL Error."
                            
                    if order.get("takeProfit"):
                        tp_price = float(order["takeProfit"])
                        # For LONGs, TP must be > current price. For SHORTs, TP must be < current price.
                        if order["direction"] == "LONG" and tp_price <= latest_price:
                            tp_price = latest_price * 1.001
                        elif order["direction"] == "SHORT" and tp_price >= latest_price:
                            tp_price = latest_price * 0.999
 
                        try:
                            self.exchange.create_order(
                                symbol=symbol,
                                type='TAKE_PROFIT_MARKET',
                                side=close_side,
                                amount=quantity,
                                params={
                                    "positionSide": order["direction"],
                                    "PositionSide": order["direction"],
                                    "stopPrice": tp_price,
                                    "triggerPrice": tp_price
                                }
                            )
                            order["warning"] += " TP OK."
                        except Exception as etp:
                            print(f"Error setting TP for {symbol}: {etp}")
                            order["warning"] += " TP Error."
                
                order["status"] = "EXECUTED"
                order["exchange_id"] = res.get("id")
                executed.append(order)
            except Exception as e:
                print(f"[PortfolioManager] Error executing order {order['action']} {order['asset']}: {e}")
                order["status"] = "FAILED"
                order["error"] = str(e)
                executed.append(order)
                
        self.save_audit(executed)
        return executed
        
    def save_audit(self, orders: List[Dict[str, Any]]):
        """Saves order history."""
        history = []
        if os.path.exists(PORTFOLIO_AUDIT_PATH):
            try:
                with open(PORTFOLIO_AUDIT_PATH, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
                
        now = datetime.now().isoformat()
        for o in orders:
            o["timestamp"] = now
            history.append(o)
            
        try:
            with open(PORTFOLIO_AUDIT_PATH, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"[PortfolioManager] Unable to save audit: {e}")

    def sell_portfolio_assets(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Immediately sells selected assets from the portfolio at market price."""
        executed = []
        if not self.exchange or not self.exchange.apiKey:
            return executed
        self.ensure_markets()

        for item in items:
            asset = item.get("asset")
            try:
                qty = float(item.get("quantity", 0) or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty <= 0:
                continue

            # Bound before the try so the except handler can always reference it.
            asset_type = item.get("type", "Spot")

            try:

                # If derivative
                if "Futures" in asset_type:
                    symbol = f"{asset}/USDT:USDT"
                    
                    pos = None
                    try:
                        positions = self.exchange.fetch_positions([symbol])
                        if positions:
                            target_dir = item.get("direction", "").upper()
                            # Search for the position with the same direction (case-insensitive)
                            for p in positions:
                                p_side = p.get('side', '').upper()
                                if p_side == target_dir:
                                    pos = p
                                    break
                            # If not found, fallback to positions[0] for compatibility
                            if not pos:
                                pos = positions[0]
                    except Exception as e_fetch:
                        print(f"[PortfolioManager] Error retrieving specific position for {symbol}: {e_fetch}")
                    except:
                        pass
                        
                    if pos:
                        pos_side_raw = pos.get('side', 'long')
                        pos_side_lower = str(pos_side_raw).lower()
                        close_side = 'sell' if pos_side_lower == 'long' else 'buy'
                        position_side_str = 'LONG' if pos_side_lower == 'long' else 'SHORT'
                        
                        params = {
                            'positionSide': position_side_str,
                            'PositionSide': position_side_str 
                        }
                        
                        try:
                            res = self.exchange.create_order(
                                symbol=symbol,
                                type='market',
                                side=close_side,
                                amount=pos.get('contracts', qty),
                                params=params
                            )
                            executed.append({"asset": asset, "status": "EXECUTED", "id": res.get("id"), "type": "Futures"})
                        except Exception as e:
                            executed.append({"asset": asset, "status": "FAILED", "error": str(e), "type": "Futures"})
                            raise e
                    else:
                        executed.append({"asset": asset, "status": "FAILED", "error": "Position not found", "type": "Futures"})
                else:
                    # Spot
                    symbol = f"{asset}/USDT"
                    if asset == "USDT":
                        continue  # do not sell usdt for usdt
                        
                    # 1. If the fund comes from a non-spot account (e.g. funding), try to transfer it
                    if "(" in asset_type:
                        acc_type = asset_type.split("(")[1].replace(")", "").strip().lower()
                        if acc_type and acc_type != "spot" and acc_type != "none":
                            try:
                                self.exchange.transfer(asset, qty, acc_type, 'spot')
                                print(f"[PortfolioManager] Transferred {qty} {asset} from {acc_type} to spot")
                            except Exception as e:
                                print(f"[PortfolioManager] Unable to transfer {asset}: {e}")
                                
                    # 2. Check the free balance on spot (to avoid avail: 0 errors due to open orders)
                    try:
                        spot_balance = self.exchange.fetch_balance({'type': 'spot'})
                        free_qty = spot_balance.get(asset, {}).get('free', 0.0)
                        if free_qty == 0:
                            raise Exception("Free balance on Spot is 0. Funds might be locked in open orders or in Funding.")
                        if free_qty < qty:
                            qty = free_qty  # sell only what is actually free
                    except Exception as e:
                        if "Free balance on Spot" in str(e):
                            raise e

                    # 3. Execute the market sell order
                    res = self.exchange.create_order(
                        symbol=symbol,
                        type='market',
                        side='sell',
                        amount=qty
                    )
                    executed.append({"asset": asset, "status": "EXECUTED", "id": res.get("id"), "type": "Spot"})
            except Exception as e:
                print(f"[PortfolioManager] Error selling {asset}: {e}")
                executed.append({"asset": asset, "status": "FAILED", "error": str(e), "type": asset_type})
                
        # We could also save these sales in the audit if we wish
        self.save_audit(executed)
        return executed
