class PreFlightChecker:
    """
    Manages real-time order validation before sending it to the exchange,
    mitigating latency risks ("Slippage Guard" and "Order Book Imbalance").
    """
    
    @staticmethod
    def run_checks(order: dict, exchange, symbol: str, settings: dict) -> tuple[bool, str]:
        """
        Executes Pre-Flight checks (Slippage Guard and Imbalance).
        Returns (True, "Passed") if checks pass, (False, "Reason") otherwise.
        Modifies the order in-place, realigning SL/TP based on the live price.
        """
        # Retrieve settings with defaults
        pm_settings = settings.get("portfolio_manager", {})
        
        # Backward compatibility: if values are 25.0, divide by 100, if they are 0.25 use them directly
        raw_drift = float(pm_settings.get("pre_flight_drift_threshold", 25.0))
        drift_threshold = raw_drift / 100.0 if raw_drift > 1.0 else raw_drift
        
        raw_imb = float(pm_settings.get("pre_flight_imbalance_threshold", 60.0))
        imbalance_threshold = raw_imb / 100.0 if raw_imb > 1.0 else raw_imb
        
        try:
            # 1. Retrieve live Ticker
            ticker = exchange.fetch_ticker(symbol)
            ticker_price_live = ticker.get('last')
            
            if not ticker_price_live:
                return False, "Unable to retrieve ticker_price_live from exchange"
                
            price_t0 = order.get('current_price')
            target_price = order.get('takeProfit')
            direction = order.get('direction')
            
            # 2. Drift Check (Slippage Guard)
            if price_t0 and target_price:
                target_dist = abs(target_price - price_t0)
                if target_dist > 0:
                    if direction == "LONG":
                        # If price has risen too much, the R/R situation is deteriorated
                        drift = (ticker_price_live - price_t0) / target_dist
                        if drift > drift_threshold:
                            return False, f"Drift Slippage: Train has already left. Price moved in favor of target by {drift*100:.1f}% (> threshold {drift_threshold*100:.0f}%)."
                    elif direction == "SHORT":
                        # If price has fallen too much
                        drift = (price_t0 - ticker_price_live) / target_dist
                        if drift > drift_threshold:
                            return False, f"Drift Slippage: Train has already left. Price moved in favor of target by {drift*100:.1f}% (> threshold {drift_threshold*100:.0f}%)."

            # 3. Flash Check of Order Book Imbalance
            try:
                # Retrieve the order book (limiting to the first 20 levels for efficiency)
                ob = exchange.fetch_order_book(symbol, limit=20)
                bids = ob.get('bids', [])
                asks = ob.get('asks', [])
                
                bid_vol = sum(b[1] for b in bids) if bids else 0
                ask_vol = sum(a[1] for a in asks) if asks else 0
                total_vol = bid_vol + ask_vol
                
                if total_vol > 0:
                    if direction == "LONG":
                        ask_pressure = ask_vol / total_vol
                        if ask_pressure > imbalance_threshold:
                            return False, f"Flash OB: Excessive Short pressure at {ask_pressure*100:.1f}% (> {imbalance_threshold*100:.0f}%)."
                    elif direction == "SHORT":
                        bid_pressure = bid_vol / total_vol
                        if bid_pressure > imbalance_threshold:
                            return False, f"Flash OB: Excessive Long pressure at {bid_pressure*100:.1f}% (> {imbalance_threshold*100:.0f}%)."
            except Exception as ob_error:
                print(f"[PreFlightChecker] Warning: fetch_order_book error ignored: {ob_error}")
                # In case of specific API failure for the order book, do not stop everything, only log it
                
            # 4. Realigning SL/TP and data based on live price
            if price_t0 and price_t0 > 0:
                old_sl = order.get('stopLoss')
                old_tp = order.get('takeProfit')
                
                if old_sl:
                    sl_pct = abs(price_t0 - old_sl) / price_t0
                    if direction == "LONG":
                        order['stopLoss'] = ticker_price_live * (1 - sl_pct)
                    else:
                        order['stopLoss'] = ticker_price_live * (1 + sl_pct)
                
                if old_tp:
                    tp_pct = abs(target_price - price_t0) / price_t0
                    if direction == "LONG":
                        order['takeProfit'] = ticker_price_live * (1 + tp_pct)
                    else:
                        order['takeProfit'] = ticker_price_live * (1 - tp_pct)
                        
                # Update current_price so that qty calculation and other uses reflect reality
                order['current_price'] = ticker_price_live

            return True, "Passed"
            
        except Exception as e:
            return False, f"Pre-Flight runtime error: {str(e)}"
