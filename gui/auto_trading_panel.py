# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
auto_trading_panel.py — Argus
Panel for the scheduled automatic execution of the entire analysis and trading workflow.
"""

import contextlib
import datetime
import queue
import threading
import time
from tkinter import messagebox, ttk

import customtkinter as ctk

from core.data_manager import load_autotrading_logs, save_autotrading_log, save_settings
from core.fonts import ui_font_family
from core.forecaster import DEFAULT_CHECKPOINT
from gui.utils import apply_binance_tab_style

COLOR_ACCENT = "#f0b90b"
COLOR_HOVER  = "#d39e00"
COLOR_MUTED  = "#848e9c"
COLOR_SEP    = "#474d57"
BG_PANEL     = ("#1e2329", "#1e2329")
BG_CARD      = ("#2b3139", "#2b3139")
BG_INPUT     = ("#2b3139", "#2b3139")


class AutoTradingPanel(ctk.CTkFrame):
    def __init__(self, parent, settings: dict, app_instance):
        super().__init__(parent, fg_color=BG_PANEL, corner_radius=12, border_color=COLOR_SEP, border_width=1)
        self.settings = settings
        self.app = app_instance

        self.last_candle_close_run = None

        self.is_running = False
        self.stop_requested = False
        self.last_run_time = None
        self._queue = queue.Queue()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._setup_style()
        self._build_header()

        self._tabs = ctk.CTkTabview(
            self, fg_color=BG_PANEL,
            segmented_button_fg_color=("#2b3139", "#2b3139"),
            segmented_button_selected_color=COLOR_ACCENT,
            segmented_button_selected_hover_color=COLOR_HOVER,
            segmented_button_unselected_color=BG_PANEL,
            segmented_button_unselected_hover_color=("#343a40", "#343a40")
        )
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self._tabs.add("🔄 Run Log")
        self._tabs.add("⚙️ Settings")

        for tab_name in self._tabs._name_list:
            self._tabs.tab(tab_name).grid_columnconfigure(0, weight=1)
            self._tabs.tab(tab_name).grid_rowconfigure(0, weight=1)

        self._build_log_tab()
        self._build_settings_tab()
        apply_binance_tab_style(self._tabs._segmented_button)

        self._check_queue()
        self._scheduler_loop()

    def _setup_style(self):
        style = ttk.Style()
        with contextlib.suppress(Exception):
            style.theme_use("clam")
        style.configure("Auto.Treeview", background="#181a20", foreground="#eaecef", fieldbackground="#181a20", rowheight=30, borderwidth=0)
        style.configure("Auto.Treeview.Heading", background="#1e2329", foreground=COLOR_ACCENT, font=(ui_font_family(), 10, "bold"), borderwidth=0)
        style.map("Auto.Treeview",
            background=[("selected", COLOR_ACCENT)],
            foreground=[("selected", "#181a20")],
        )
        style.map("Auto.Treeview.Heading",
            background=[("active", "#2b3139")],
        )

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent", height=48)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="🤖 Auto Trading",
            font=ctk.CTkFont(ui_font_family(), 13, "bold"), text_color=COLOR_ACCENT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        self._status_lbl = ctk.CTkLabel(
            hdr, text="Inactive.", font=ctk.CTkFont(ui_font_family(), 11), text_color=COLOR_MUTED, anchor="w",
        )
        self._status_lbl.grid(row=0, column=1, sticky="ew")

        ctk.CTkFrame(self, height=1, fg_color=COLOR_SEP).grid(
            row=0, column=0, sticky="ew", padx=16, pady=(48, 0)
        )

    def _build_log_tab(self):
        tab = self._tabs.tab("🔄 Run Log")

        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=10)

        self._btn_start = ctk.CTkButton(toolbar, text="▶ Start", command=self._start_auto, width=150, fg_color=COLOR_ACCENT, hover_color=COLOR_HOVER, text_color="#181a20", font=ctk.CTkFont(ui_font_family(), 12, "bold"))
        self._btn_start.pack(side="left")

        self._countdown_lbl = ctk.CTkLabel(toolbar, text="", font=ctk.CTkFont(ui_font_family(), 12, "bold"), text_color=COLOR_ACCENT)
        self._countdown_lbl.pack(side="left", padx=20)

        self._btn_stop = ctk.CTkButton(toolbar, text="⏹ Stop", command=self._stop_auto, width=150, fg_color=COLOR_ACCENT, hover_color=COLOR_HOVER, text_color="#181a20", font=ctk.CTkFont(ui_font_family(), 12, "bold"), state="disabled")
        self._btn_stop.pack(side="right")

        # Log Treeview
        tree_frame = ctk.CTkFrame(tab, fg_color="#0d0d1a")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)

        cols = [
            ("date", "Start Date", 150),
            ("duration", "Duration", 100),
            ("status", "Result", 100),
            ("details", "Details", 300)
        ]
        self._tree_log = ttk.Treeview(tree_frame, columns=[c[0] for c in cols], show="headings", style="Auto.Treeview")
        for c in cols:
            self._tree_log.heading(c[0], text=c[1])
            self._tree_log.column(c[0], width=c[2], anchor="w" if c[0] == "details" else "center")

        self._tree_log.tag_configure("OK", foreground="#00e676")
        self._tree_log.tag_configure("ERROR", foreground="#ff5252")

        self._tree_log.pack(fill="both", expand=True)

    def _build_settings_tab(self):
        tab = self._tabs.tab("⚙️ Settings")
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        left_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.grid_columnconfigure(1, weight=1)

        right_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(left_frame, text="Execution Interval", font=ctk.CTkFont(ui_font_family(), 11, "bold")).grid(row=0, column=0, padx=10, pady=15, sticky="w")
        ctk.CTkLabel(left_frame, text="Automatic (30s after the close of every 15 min candle)", font=ctk.CTkFont(ui_font_family(), 11, slant="italic"), text_color=("#888888", "#888888")).grid(row=0, column=1, padx=10, pady=15, sticky="w")

        # Toggle for run weekend option
        auto_settings = self.settings.get("auto_trading", {})
        self._run_weekend_var = ctk.BooleanVar(value=auto_settings.get("run_weekend", True))
        self._run_weekend_switch = ctk.CTkSwitch(
            left_frame,
            text="Execute also during weekends",
            variable=self._run_weekend_var,
            font=ctk.CTkFont(ui_font_family(), 11)
        )
        self._run_weekend_switch.grid(row=1, column=0, columnspan=2, padx=10, pady=(10, 2), sticky="w")
        ctk.CTkLabel(left_frame, text="If active, the bot continues auto-trading on Saturdays and Sundays.\nIf deactivated, scans and orders are suspended during the weekend (low liquidity).", font=ctk.CTkFont(ui_font_family(), 10), text_color="#888888", justify="left").grid(row=2, column=0, columnspan=2, padx=35, pady=(0, 10), sticky="w")

        ctk.CTkButton(
            left_frame,
            text="💾 Save Settings",
            command=self._save_settings,
            font=ctk.CTkFont(family=ui_font_family(), size=12, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_HOVER,
            text_color="#181a20",
            height=38,
            corner_radius=8,
        ).grid(row=3, column=0, columnspan=2, padx=10, pady=20, sticky="ew")

        info_card = ctk.CTkFrame(right_frame, fg_color=BG_CARD, corner_radius=12)
        info_card.pack(fill="x", padx=16, pady=16)

        info_text = (
            "🤖 AUTO-TRADING WORKFLOW & LOGIC\n\n"
            "Argus periodically runs an integrated analysis and trading workflow in the background. Each cycle develops in the following sequential phases:\n\n"
            "⚠️ 1. SAFETY CHECKS & COOLDOWN:\n"
            "• WEEKEND CHECK: If the option 'Execute also during weekends' is deactivated, the bot suspends operations on Saturdays and Sundays (status visible at the top).\n"
            "• GENERAL COOLDOWN: If the portfolio is full or in drawdown, auto-trading pauses for the specified number of cycles (cooldown_runs).\n"
            "• SELECTIVE COOLDOWN: Individual assets discarded due to low confidence are temporarily blocked (low_conf_cooldowns) to avoid false signals.\n\n"
            "📡 2. PRICE & MARKET ALIGNMENT:\n"
            "• The bot queries the Exchange (via CCXT fetchTickers) to align real-time prices. In case of error or absence, it falls back to CoinGecko.\n"
            "• Current prices and percentage changes are displayed in the 'Markets' tab (history of the last 50 readings).\n\n"
            "📈 3. KNN-DTW PATTERN MATCHING:\n"
            "• Scans historical patterns for BTC with the KNN-DTW algorithm to estimate variation and confidence over a 2-hour horizon.\n"
            "• Saves and inserts results in real-time in the 'Pattern Matching' table.\n\n"
            "🔮 4. DEEP LEARNING FORECAST (TimesFM):\n"
            "• Downloads recent history (30 days) and applies the Google TimesFM model to formulate a 2-hour forecast.\n"
            "• Generates a preliminary signal (BUY/SELL/HOLD) based on the percentage threshold in settings (signal_threshold_pct).\n\n"
            "🧠 5. AI AGENTS TEAM & DEBATE:\n"
            "• Integrates price data, Pattern Matching results, and TimesFM forecasts into a structured prompt.\n"
            "• AI Agents (Technical Analysis, Sentiment, Fundamentals, and Moderator) jointly evaluate the opportunity and calculate optimal Stop Loss (SL) and Take Profit (TP) levels.\n\n"
            "💼 6. PORTFOLIO MANAGER & CCXT ORDERS:\n"
            "• Calculates correct Position Sizing based on the set risk and routes the order with SL/TP directly to the configured Exchange.\n\n"
            "💡 NOTE: Runs repeat automatically at the specified interval. The countdown shows the time remaining before the next cycle starts."
        )
        ctk.CTkLabel(info_card, text=info_text, font=ctk.CTkFont(ui_font_family(), 11), text_color=("#c0c8e0", "#c0c8e0"), justify="left", anchor="w", wraplength=380).pack(fill="both", expand=True, padx=16, pady=16)

        # Populate logs on startup
        self._refresh_logs_ui()

    def _save_settings(self):
        try:
            auto_settings = self.settings.get("auto_trading", {})
            auto_settings["run_weekend"] = self._run_weekend_var.get()
            if "ignore_portfolio" in auto_settings: del auto_settings["ignore_portfolio"]
            if "exclude_assets" in auto_settings: del auto_settings["exclude_assets"]
            if "interval_min" in auto_settings: del auto_settings["interval_min"]
            self.settings["auto_trading"] = auto_settings
            save_settings(self.settings)
            self._status("✅ Settings saved.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _status(self, text):
        self._status_lbl.configure(text=text)

    def _refresh_logs_ui(self):
        for item in self._tree_log.get_children():
            self._tree_log.delete(item)
        logs = load_autotrading_logs()
        # Show most recent at the top
        for log in reversed(logs[-100:]):
            status_val = log.get("status", "")
            tag = "OK" if status_val == "OK" else "ERROR"
            status_display = "OK" if status_val == "OK" else "ERROR"
            self._tree_log.insert("", "end", values=(
                log.get("start_time", ""),
                log.get("duration", ""),
                status_display,
                log.get("details", "")
            ), tags=(tag,))

    def _start_auto(self):
        self.is_running = True
        self.stop_requested = False
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._status("Active. Waiting for next cycle...")
        # Force immediate execution for the first cycle
        self.last_run_time = None
        # The scheduler tick is self-perpetuating and started once in __init__,
        # so do NOT kick off a second one here (that would double the ticks).

    def _stop_auto(self):
        self.stop_requested = True
        self._status("Stop requested...")
        self._btn_stop.configure(state="disabled")

    def _check_queue(self):
        while not self._queue.empty():
            func = self._queue.get_nowait()
            try:
                func()
            except Exception as e:
                print(f"[AutoTrading] Error in queue: {e}")
        self.after(100, self._check_queue)

    def _scheduler_loop(self):
        """Single self-perpetuating 1s tick. Started once from __init__ and never
        cancelled, so Start/Stop can be toggled freely without leaking timers."""
        try:
            self._scheduler_tick()
        except Exception as e:
            print(f"[AutoTrading] Scheduler tick error: {e}")
        finally:
            # Always rearm — a dead scheduler silently stops auto-trading.
            self.after(1000, self._scheduler_loop)

    def _scheduler_tick(self):
        if not self.is_running:
            self._countdown_lbl.configure(text="")
            return

        if self.stop_requested:
            self.is_running = False
            self.stop_requested = False
            self.workflow_running = False
            self._btn_start.configure(state="normal")
            self._status("Inactive.")
            self._countdown_lbl.configure(text="")
            return

        import datetime as dt_check
        now_dt = dt_check.datetime.now()

        # Calculate close of the last 15-minute candle
        minute = now_dt.minute
        candle_minute = (minute // 15) * 15
        last_candle_close = now_dt.replace(minute=candle_minute, second=0, microsecond=0)

        # Start target is 30 seconds after candle close
        target_trigger_time = last_candle_close + dt_check.timedelta(seconds=30)

        if getattr(self, "workflow_running", False):
            self._countdown_lbl.configure(text="Running...")
        elif now_dt >= target_trigger_time and getattr(self, "last_candle_close_run", None) != last_candle_close:
            # Weekend check — skip this candle but keep the scheduler alive,
            # otherwise auto-trading would stay dead until the next manual Start.
            auto_set = self.settings.get("auto_trading", {})
            if not auto_set.get("run_weekend", True) and now_dt.weekday() in (5, 6):
                self.last_candle_close_run = last_candle_close
                self._status("⏳ Weekend: auto-trading suspended (run_weekend = False).")
                self._countdown_lbl.configure(text="Suspended (weekend)")
            else:
                self.last_candle_close_run = last_candle_close
                self.workflow_running = True
                self._countdown_lbl.configure(text="Starting...")
                threading.Thread(target=self._run_workflow, daemon=True).start()
        else:
            # Calculate remaining time for the next trigger
            if now_dt < target_trigger_time:
                next_trigger = target_trigger_time
            else:
                next_trigger = target_trigger_time + dt_check.timedelta(minutes=15)

            remaining = int((next_trigger - now_dt).total_seconds())
            if remaining > 0:
                mins = remaining // 60
                secs = remaining % 60
                self._countdown_lbl.configure(text=f"Next run in {mins}m {secs}s")
            else:
                self._countdown_lbl.configure(text="Starting...")

    def _run_workflow(self):
        start_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_t = time.time()

        def update_status(msg, progress=None):
            print(f"[AutoTrading] {msg}")
            self._queue.put(lambda m=msg: self._status(m))

        def log_res(status, details):
            self.last_run_time = time.time()
            self.workflow_running = False
            end_t = time.time()
            dur = end_t - start_t
            if dur < 60:
                dur_str = f"{dur:.1f} s"
            else:
                dur_str = f"{dur/60:.1f} min"
            save_autotrading_log({
                "start_time": start_time_str,
                "duration": dur_str,
                "status": status,
                "details": details
            })
            self._queue.put(self._refresh_logs_ui)

            if status == "ERROR" and self.is_running:
                self._queue.put(lambda: self._status("Error in previous cycle."))
            elif self.is_running:
                self._queue.put(lambda: self._status(f"Cycle completed in {dur_str}."))

        # ------------------------------------------------------------------
        # Helper: executes AI analysis + orders on a single candidate asset.
        # Returns (True, n_orders) if everything ok, (False, 0) otherwise.
        # If macro_asset is True the function does not exclude BTC/ETH from cooldowns.
        # ------------------------------------------------------------------
        def _run_ai_and_orders(target_asset, pm_ref, analyst_ref, label=""):
            """AI analysis + order generation/execution for a single asset."""
            sym = target_asset.get("symbol", "?")
            if self.stop_requested:
                return False, 0
            enable_ai = self.settings.get("enable_ai_auto_trade", True)
            def _build_ai_fallback_res(t_asset, reason="DISABLED", err_msg=""):
                r = t_asset.copy()
                from datetime import datetime
                r["analyzed_at"] = datetime.now().isoformat()
                r["btc_expected_move"] = t_asset.get("btc_expected_move", 0.0)
                r["btc_pred_confidence"] = t_asset.get("btc_pred_confidence", 0.0)
                r["tfm_confidence"] = t_asset.get("confidence", 50.0)
                r["ai_change_pct_1d"] = 0.0
                r["confidence"] = reason
                r["signal"] = reason
                r["ai_analysis_text"] = err_msg if err_msg else "Advanced Analysis is disabled in Auto Trading."

                curr_p = float(r.get("current_price", r.get("last_price", 1.0)) or 1.0)
                # Weights live in settings as percentages — normalise before use.
                from core.portfolio_manager import normalize_ensemble_weights
                w_t, w_p, w_a = normalize_ensemble_weights(self.settings)
                # AI leg is inactive here, redistribute its weight evenly.
                w_p += w_a / 2.0
                w_t += w_a / 2.0
                t_pct = float(r.get("change_pct_1d", 0.0) or 0.0)
                p_pct = float(r.get("btc_expected_move", 0.0) or 0.0)
                e_ret = (t_pct * w_t) + (p_pct * w_p)

                if e_ret >= 0:
                    r["stop_loss"] = curr_p * 0.97
                    r["take_profit"] = curr_p * 1.06
                else:
                    r["stop_loss"] = curr_p * 1.03
                    r["take_profit"] = curr_p * 0.94
                return r

            if not enable_ai:
                update_status("Advanced Analysis skipped: Disabled in Auto Trading settings")
                res = _build_ai_fallback_res(target_asset)
            else:
                update_status(f"🤖 AI Analysis {label}: {sym}...")
                try:
                    res = analyst_ref.analyze_single(
                        target_asset,
                        progress_callback=lambda msg: None
                    )
                    res["btc_expected_move"] = target_asset.get("btc_expected_move", 0.0)
                    res["btc_pred_confidence"] = target_asset.get("btc_pred_confidence", 0.0)
                except Exception as e:
                    print(f"[AutoTrading] AI Analysis failed for {sym}: {e}")
                    update_status("Advanced Analysis failed (API error). Fallback applied.")
                    res = _build_ai_fallback_res(target_asset, reason="DISABLED", err_msg=f"Advanced Analysis failed: {e}. Fallback applied.")

            ai_results = [res]
            import core.ai_analysis_store as aistore
            aistore.save_ai_session(ai_results, meta={"market_type": cfg.get("market_type", "crypto")})
            self._queue.put(
                lambda r=ai_results: self.app._ai_panel._populate_results_tree(r)
                if hasattr(self.app, "_ai_panel") else None
            )

            if pm_ref is None:
                return False, 0

            discarded_for_conf = []
            def on_discard(s, reason):
                if reason == "low_confidence":
                    discarded_for_conf.append(s)

            orders = pm_ref.generate_orders(ai_results, discarded_callback=on_discard)

            if discarded_for_conf:
                auto_set = self.settings.get("auto_trading", {})
                c_downs = auto_set.get("low_conf_cooldowns", {})
                for s in discarded_for_conf:
                    c_downs[s.upper()] = 3
                auto_set["low_conf_cooldowns"] = c_downs
                self.settings["auto_trading"] = auto_set
                dman.save_settings(self.settings)

            if orders:
                executed = pm_ref.place_orders(orders)
                self._queue.put(
                    lambda: self.app._portfolio_panel._update_portfolio_view()
                    if hasattr(self.app, "_portfolio_panel") else None
                )
                return True, executed

            # Generation failed or discarded
            reason = "HOLD action or low confidence"
            if discarded_for_conf:
                reason = "Insufficient AI confidence"
            elif res.get("signal_1d", "HOLD") not in ["HOLD", "NO TRADE"]:
                reason = "Risk Management filter or Max positions reached"
            elif res.get("signal", "HOLD") not in ["HOLD", "DISABLED"]:
                reason = "Risk Management filter (e.g. SL too wide)"
            return True, [{"status": "REJECTED", "error": reason}]

        try:
            import core.data_manager as dman

            _auto_set_cd = self.settings.get("auto_trading", {})
            _global_cd = int(_auto_set_cd.get("global_cooldown", 0))
            if _global_cd > 0:
                _auto_set_cd["global_cooldown"] = _global_cd - 1
                self.settings["auto_trading"] = _auto_set_cd
                dman.save_settings(self.settings)
                msg_cd = f"Portfolio full or in loss, waiting for closures. Skipping this run ({_global_cd} runs remaining)."
                update_status(f"⏳ {msg_cd}")
                log_res("OK", msg_cd)
                return

            update_status("Running: 1/2 - Fetching Market Data...")

            from core.forecaster import CryptoForecaster

            cfg = self.settings
            market_type = cfg.get("market_type", "crypto")
            horizon = 8  # 8 candles of 15m = 2 hours
            threshold = cfg.get("signal_threshold_pct", 2.0)
            backend = cfg.get("backend") or "cpu"
            # "model_checkpoint" is persisted as "" — a present-but-empty key, so
            # the `.get(k, default)` fallback would never fire.
            checkpoint = cfg.get("model_checkpoint") or DEFAULT_CHECKPOINT


            cg_key     = cfg.get("coingecko_api_key", "")
            cg_plan    = cfg.get("coingecko_api_plan", "demo")

            asset_list = [{"symbol": "BTC", "name": "Bitcoin", "coingecko_id": "bitcoin"}]
            if self.stop_requested: return log_res("STOP", "Stopped by user.")

            # Current price update (Exchange -> Provider)
            update_status(f"📡 Updating current prices for {market_type.upper()}...")
            from core.portfolio_manager import PortfolioManager
            pm = PortfolioManager(cfg)
            exchange_tickers = {}
            has_fetch = pm.exchange and pm.exchange.apiKey and pm.exchange.has.get("fetchTickers")
            if has_fetch:
                update_status("🏦 Fetching prices from exchange...")
                try:
                    exchange_tickers = pm.exchange.fetch_tickers()
                    print(f"[AutoTrading] Exchange tickers available: {len(exchange_tickers)}")
                except Exception as e:
                    print(f"[AutoTrading] Unable to fetch tickers from exchange: {e}")
            else:
                if not (pm.exchange and pm.exchange.apiKey):
                    print("[AutoTrading] Exchange not configured or API key missing — skip fetch tickers.")
                else:
                    print(f"[AutoTrading] fetchTickers not supported by this exchange (has={pm.exchange.has.get('fetchTickers')!r}) — skip.")

            # Build a quick map: base symbol -> (price, change%)
            # to handle any pair format (spot, perp, etc.)
            exchange_price_map = {}
            for ex_sym, tick in exchange_tickers.items():
                last = tick.get("last")
                if last and last > 0:
                    # Extract base symbol before '/'
                    base = ex_sym.split("/")[0].upper()
                    # Prefer USDT over USD if already present
                    if base not in exchange_price_map or "/USDT" in ex_sym:
                        exchange_price_map[base] = (float(last), tick.get("percentage", 0.0) or 0.0)

            missing_from_exchange = []
            found_on_exchange = 0
            for item in asset_list:
                sym = item.get("symbol", "").upper()
                if sym in exchange_price_map:
                    price, chg_pct = exchange_price_map[sym]
                    item["current_price"] = price
                    item["price_change_pct"] = chg_pct
                    found_on_exchange += 1
                else:
                    missing_from_exchange.append(item)

            print(f"[AutoTrading] Prices from exchange: {found_on_exchange}/{len(asset_list)} | Missing (CoinGecko fallback): {len(missing_from_exchange)}")

            from core.data_fetcher import update_crypto_prices
            if missing_from_exchange:
                if found_on_exchange > 0:
                    update_status(f"🏦 {found_on_exchange} prices from exchange. Integrating {len(missing_from_exchange)} missing from CoinGecko...")
                updated_missing = update_crypto_prices(
                    crypto_list=missing_from_exchange,
                    api_key=cg_key,
                    api_plan=cg_plan,
                    progress_callback=lambda m, f=None: update_status(f"₿ {m}")
                )
                miss_dict = {m["symbol"]: m for m in updated_missing}
                for item in asset_list:
                    sym = item.get("symbol")
                    if sym in miss_dict:
                        item.update(miss_dict[sym])
            elif found_on_exchange > 0:
                update_status(f"✅ All {found_on_exchange} prices retrieved from exchange.")
            dman.save_market_list(market_type, asset_list)

            # --- Centralized History Download (BTC 15m 1 year only) ---
            update_status("📥 Downloading BTC history (15m, 1 year)...")
            try:
                from core.data_fetcher import fetch_historical_paginated
                from core.data_manager import save_historical
                df_btc = None
                if pm.exchange is not None:
                    df_btc = fetch_historical_paginated(pm.exchange, "BTC", timeframe="15m", days=365)

                if df_btc is not None and not df_btc.empty:
                    save_historical("BTC", df_btc)
                    update_status("✅ BTC history saved successfully.")
                else:
                    import yfinance as yf
                    update_status("⚠️ Exchange failed, fallback history on yfinance...")
                    df_btc = yf.download("BTC-USD", period="60d", interval="15m", progress=False)
                    if df_btc is not None and not df_btc.empty:
                        import pandas as pd
                        if isinstance(df_btc.columns, pd.MultiIndex):
                            df_btc.columns = df_btc.columns.get_level_values(0)
                        df_btc = df_btc[["Open", "High", "Low", "Close", "Volume"]].copy()
                        df_btc = df_btc.dropna(subset=["Close"])
                        save_historical("BTC", df_btc)
                        update_status("✅ BTC history saved via yfinance.")
                    else:
                        update_status("❌ Unable to download BTC history.")
            except Exception as e:
                print(f"[AutoTrading] Error downloading BTC history: {e}")
                update_status(f"❌ Error downloading BTC history: {e}")

            if hasattr(self.app, "_markets_panel"):
                markets_panel = self.app._markets_panel
                self._queue.put(lambda: markets_panel._load_all_lists())

            if self.stop_requested: return log_res("STOP", "Stopped by user.")

            btc_target = asset_list[0]
            curr = btc_target.get("current_price", 0.0)
            btc_target["last_price"] = curr

            # --- PATTERN MATCHING BTC ---
            update_status("Running: BTC Pattern Matching (KNN-DTW)...")
            try:
                from core.btc_pattern_matcher import BTCPatternMatcher
                matcher = BTCPatternMatcher()
                pm_res = matcher.run_analysis()
                btc_target.update(pm_res)

                # --- HISTORY SAVE AND PATTERN MATCHING UI UPDATE ---
                move = pm_res.get("btc_expected_move", 0.0)
                conf = pm_res.get("btc_pred_confidence", 0.0)
                matches = pm_res.get("matches_count", 0)
                target_price = pm_res.get("btc_target_price", 0.0)
                if target_price == 0.0 and curr > 0:
                    target_price = curr * (1.0 + move / 100.0)

                tag = "positive" if move > 0 else ("negative" if move < 0 else "neutral")
                move_str = f"+{move:.2f}%" if move > 0 else f"{move:.2f}%"
                conf_str = f"{conf:.2f}%"
                target_str = f"${target_price:.2f}" if target_price > 0 else "N/A"
                expiry = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%d/%m/%Y %H:%M")

                pm_history = dman.load_pm_history()
                new_row = {
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "matches": matches,
                    "conf": conf_str,
                    "target": target_str,
                    "move": move_str,
                    "expiry": expiry,
                    "tag": tag
                }
                pm_history.insert(0, new_row)
                if len(pm_history) > 50:
                    pm_history = pm_history[:50]
                dman.save_pm_history(pm_history)

                if hasattr(self.app, "_pm_panel"):
                    pm_panel = self.app._pm_panel
                    self._queue.put(lambda: pm_panel._tree.insert("", 0, values=("Bitcoin", "BTC", matches, conf_str, target_str, move_str, expiry), tags=(tag,)))
                    pm_panel._history.insert(0, new_row)
                    if len(pm_panel._history) > 50:
                        pm_panel._history = pm_panel._history[:50]

            except Exception as e:
                print(f"Pattern Matching Error: {e}")
                btc_target.update({"btc_pred_confidence": 0, "btc_expected_move": 0})

            # --- TIMESFM ---
            update_status("Running: TimesFM Time-Series Analysis...")
            try:
                from core.data_manager import load_historical
                df = None
                try:
                    df = load_historical("BTC")
                except ValueError as ve:
                    update_status(f"⚠️ {ve}")

                from core.analyzer import compute_expiry_date
                expiry_dt = compute_expiry_date(2)

                if df is not None and not df.empty:
                    # Reuse the loaded model across cycles: TimesFM takes tens of
                    # seconds to initialise and this runs every 15 minutes.
                    forecaster = getattr(self, "_forecaster", None)
                    if (forecaster is None
                            or forecaster.checkpoint != checkpoint
                            or forecaster.backend != backend):
                        forecaster = CryptoForecaster(backend=backend, checkpoint=checkpoint)
                        self._forecaster = forecaster

                    if not forecaster._model_loaded:
                        if not forecaster.load_model(progress_callback=lambda m, f=None: update_status(f"🤖 {m}")):
                            update_status("⚠️ TimesFM model unavailable — proceeding without a time-series forecast.")

                    forecast_res = forecaster.forecast("BTC", df, horizon=horizon)
                    if forecast_res is not None:
                        pred, confidence = forecast_res
                        change = ((pred - curr) / curr * 100.0) if curr > 0 else 0.0
                        btc_target["forecast_price_1d"] = pred
                        btc_target["target_price_1d"] = pred
                        btc_target["change_pct_1d"] = change
                        btc_target["forecast_price"] = pred
                        btc_target["change_pct"] = change
                        btc_target["confidence"] = confidence
                    else:
                        btc_target["forecast_price_1d"] = curr
                        btc_target["target_price_1d"] = curr
                        btc_target["change_pct_1d"] = 0.0
                        btc_target["forecast_price"] = curr
                        btc_target["change_pct"] = 0.0
                        btc_target["confidence"] = 0.0
                else:
                    btc_target["forecast_price_1d"] = curr
                    btc_target["target_price_1d"] = curr
                    btc_target["change_pct_1d"] = 0.0
                    btc_target["forecast_price"] = curr
                    btc_target["change_pct"] = 0.0

                btc_target["expiry_date"] = expiry_dt
                btc_target["horizon_days"] = 1
                btc_target["run_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                threshold = cfg.get("signal_threshold_pct", 2.0)
                chg = btc_target["change_pct_1d"]
                btc_target["signal"] = "BUY" if chg >= threshold else ("SELL" if chg <= -threshold else "HOLD")

            except Exception as e:
                print(f"TimesFM Error: {e}")
                from core.analyzer import compute_expiry_date
                expiry_dt = compute_expiry_date(2)
                btc_target["forecast_price_1d"] = curr
                btc_target["target_price_1d"] = curr
                btc_target["change_pct_1d"] = 0.0
                btc_target["forecast_price"] = curr
                btc_target["change_pct"] = 0.0
                btc_target["confidence"] = 0.0
                btc_target["expiry_date"] = expiry_dt
                btc_target["horizon_days"] = 1
                btc_target["run_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                btc_target["signal"] = "HOLD"

            tfm_results = [btc_target]
            dman.save_forecast_log(tfm_results)

            self.settings["last_run"] = datetime.datetime.now().isoformat()
            dman.save_settings(self.settings)

            self._queue.put(lambda: self.app._post(type="done", results=tfm_results))

            # ------------------------------------------------------------------
            # 2) Advanced AI Analysis - BTC
            # ------------------------------------------------------------------
            btc_target = tfm_results[0]

            from core.ai_analyst import AIAnalyst
            analyst = AIAnalyst(cfg)
            pm_exec = self.app._portfolio_panel.pm if hasattr(self.app, "_portfolio_panel") else None

            total_orders = 0
            update_status(f"Running: 2/2 - AI Analysis on {btc_target['symbol']}...")

            if self.stop_requested: return log_res("STOP", "Stopped by user.")

            ok, executed_orders = _run_ai_and_orders(btc_target, pm_exec, analyst, label="BTC")

            order_details_list = []
            if ok and isinstance(executed_orders, list):
                for o in executed_orders:
                    st = o.get("status")
                    if st in ["EXECUTED", "SIMULATED"]:
                        dire = o.get("direction", "")
                        lev = o.get("leverage", 1)
                        sl = o.get("stopLoss")
                        tp = o.get("takeProfit")
                        cp = o.get("current_price", 1)

                        sl_pct = (abs(cp - sl)/cp*100) if sl and cp else 0
                        tp_pct = (abs(cp - tp)/cp*100) if tp and cp else 0

                        order_details_list.append(f"[{st}] {dire} | Leverage: {lev}x | SL: {sl_pct:.2f}% | TP: {tp_pct:.2f}%")
                        total_orders += 1
                    else:
                        err = o.get("error", "Unknown")
                        order_details_list.append(f"Discarded: {err}")

            if total_orders > 0:
                update_status(f"✅ Order for {btc_target['symbol']} completed ({total_orders} orders placed).")
            else:
                update_status(f"⚠️ No orders placed for {btc_target['symbol']}.")

            # ------------------------------------------------------------------
            # Final Summary
            # ------------------------------------------------------------------
            if pm_exec is None:
                log_res("ERROR", "Portfolio manager not available.")
            else:
                if order_details_list:
                    details_str = " || ".join(order_details_list)
                else:
                    details_str = "No orders analyzed."

                log_res("OK" if ok else "ERROR", details_str)

        except Exception as exc:
            import traceback
            print(traceback.format_exc())
            log_res("ERROR", str(exc))

