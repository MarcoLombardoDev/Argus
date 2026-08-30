# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
portfolio_panel.py — Argus
Portfolio management panel (CCXT, rules, and orders).
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import datetime

from core.fonts import ui_font_family
from core.portfolio_manager import PortfolioManager
from core.data_manager import save_settings
from gui.utils import apply_binance_tab_style
from core.ai_analysis_store import load_all_sessions

COLOR_ACCENT = "#7c83fd"
COLOR_HOVER  = "#5a63e8"
COLOR_MUTED  = "#8090b0"
COLOR_SEP    = "#334155"
BG_PANEL     = ("#0f172a", "#0f172a")
BG_CARD      = ("#1e293b", "#1e293b")
BG_INPUT     = ("#16213e", "#16213e")


class PortfolioPanel(ctk.CTkFrame):
    def __init__(self, parent, settings: dict):
        super().__init__(parent, fg_color=BG_PANEL, corner_radius=12, border_color=COLOR_SEP, border_width=1)
        self.settings = settings
        self.pm = PortfolioManager(self.settings)
        self._proposed_orders = []
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent", height=48)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="💼 Portfolio",
            font=ctk.CTkFont(ui_font_family(), 13, "bold"), text_color="#f0b90b",
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        self._status_lbl = ctk.CTkLabel(
            hdr, text="Ready.", font=ctk.CTkFont(ui_font_family(), 11), text_color=COLOR_MUTED, anchor="w",
        )
        self._status_lbl.grid(row=0, column=1, sticky="ew")

        ctk.CTkFrame(self, height=1, fg_color=COLOR_SEP).grid(
            row=0, column=0, sticky="ew", padx=16, pady=(48, 0)
        )

        # Tabs
        self._tabs = ctk.CTkTabview(
            self, fg_color=("#1e2329", "#1e2329"),
            segmented_button_fg_color=("#2b3139", "#2b3139"),
            segmented_button_selected_color="#f0b90b",
            segmented_button_selected_hover_color="#d39e00",
            segmented_button_unselected_color=("#1e2329", "#1e2329"),
            segmented_button_unselected_hover_color=("#343a40", "#343a40"),
            command=self._on_tab_changed
        )
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self._tabs.add("🏦 Portfolio Status")
        self._tabs.add("📋 Proposed Orders")
        self._tabs.add("⚙️ Settings")
        
        for tab_name in self._tabs._name_list:
            self._tabs.tab(tab_name).grid_columnconfigure(0, weight=1)
            self._tabs.tab(tab_name).grid_rowconfigure(0, weight=1)

        self._build_settings_tab()
        self._build_portfolio_tab()
        self._build_orders_tab()
        apply_binance_tab_style(self._tabs._segmented_button)
        
        self._queue = queue.Queue()
        self._check_queue()
        
        self._auto_update_loop()

    def _auto_update_loop(self):
        if self._tabs.get() == "🏦 Portfolio Status":
            self._update_portfolio_view()
            
        pm_settings = self.settings.get("portfolio_manager", {})
        refresh_min = float(pm_settings.get("refresh_min", 1.0))
        refresh_ms = int(refresh_min * 60000)
        if refresh_ms < 10000:
            refresh_ms = 10000
            
        self.after(refresh_ms, self._auto_update_loop)

    def _check_queue(self):
        while not self._queue.empty():
            func = self._queue.get_nowait()
            try:
                func()
            except Exception as e:
                print(f"[PortfolioPanel] Error in queue: {e}")
        self.after(100, self._check_queue)
        
    def _on_tab_changed(self):
        current_tab = self._tabs.get()
        if current_tab == "📋 Proposed Orders":
            self._refresh_orders_ui()
        elif current_tab == "🏦 Portfolio Status":
            self._update_portfolio_view()

    def _status(self, text):
        self._status_lbl.configure(text=text)

    # ─────────────────────────────────────────────────────────────
    # TAB 1: Impostazioni
    # ─────────────────────────────────────────────────────────────
    def _build_settings_tab(self):
        tab = self._tabs.tab("⚙️ Settings")
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)
        
        left_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.grid_columnconfigure(1, weight=1)
        
        right_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        pm_settings = self.settings.get("portfolio_manager", {})
        
        def lbl(text, r, c):
            ctk.CTkLabel(left_frame, text=text, font=ctk.CTkFont(ui_font_family(), 11, "bold")).grid(row=r, column=c, padx=10, pady=5, sticky="w")
            
        def section(title, r):
            ctk.CTkLabel(left_frame, text=title, font=ctk.CTkFont(ui_font_family(), 13, "bold"), text_color=COLOR_ACCENT).grid(row=r, column=0, columnspan=2, padx=10, pady=(15,5), sticky="w")
            
        r = 0
        section("Exchange Connection", r); r+=1
        
        lbl("Exchange", r, 0)
        _EXCHANGE_OPTIONS = [
            ("AftermathFinance", "aftermath"),
            ("Alpaca", "alpaca"),
            ("Apex", "apex"),
            ("Arkham", "arkham"),
            ("AscendEX", "ascendex"),
            ("Aster", "aster"),
            ("Backpack", "backpack"),
            ("Bequant", "bequant"),
            ("BigONE", "bigone"),
            ("Binance", "binance"),
            ("Binance COIN-M", "binancecoinm"),
            ("Binance US", "binanceus"),
            ("Binance USDⓈ-M", "binanceusdm"),
            ("BingX", "bingx"),
            ("Bit2C", "bit2c"),
            ("Bitbank", "bitbank"),
            ("Bitbns", "bitbns"),
            ("Bitfinex", "bitfinex"),
            ("bitFlyer", "bitflyer"),
            ("Bitget", "bitget"),
            ("Bithumb", "bithumb"),
            ("BitMart", "bitmart"),
            ("BitMEX", "bitmex"),
            ("BitoPro", "bitopro"),
            ("Bitrue", "bitrue"),
            ("Bitso", "bitso"),
            ("Bitstamp", "bitstamp"),
            ("BIT.TEAM", "bitteam"),
            ("BitTrade", "bittrade"),
            ("Bitvavo", "bitvavo"),
            ("Blockchain.com", "blockchaincom"),
            ("BloFin", "blofin"),
            ("BTC Markets", "btcmarkets"),
            ("BTCTurk", "btcturk"),
            ("BtcBox", "btcbox"),
            ("Bullish", "bullish"),
            ("Bybit", "bybit"),
            ("Bybit EU", "bybiteu"),
            ("BYDFi", "bydfi"),
            ("CEX.IO", "cex"),
            ("Coinbase", "coinbase"),
            ("Coinbase Advanced", "coinbaseadvanced"),
            ("Coinbase Exchange", "coinbaseexchange"),
            ("Coinbase International", "coinbaseinternational"),
            ("Coincheck", "coincheck"),
            ("CoinEx", "coinex"),
            ("CoinMate", "coinmate"),
            ("Coinmetro", "coinmetro"),
            ("CoinOne", "coinone"),
            ("Coins.ph", "coinsph"),
            ("CoinSpot", "coinspot"),
            ("Crypto.com", "cryptocom"),
            ("Cryptomus", "cryptomus"),
            ("DeepCoin", "deepcoin"),
            ("Delta Exchange", "delta"),
            ("Deribit", "deribit"),
            ("Derive", "derive"),
            ("DigiFinex", "digifinex"),
            ("dYdX", "dydx"),
            ("EXMO", "exmo"),
            ("FMFW.io", "fmfwio"),
            ("Foxbit", "foxbit"),
            ("Gate.io", "gate"),
            ("Gate.io Pro", "gateio"),
            ("Gemini", "gemini"),
            ("GRVT", "grvt"),
            ("HashKey Global", "hashkey"),
            ("Hibachi", "hibachi"),
            ("HitBTC", "hitbtc"),
            ("HollaEx", "hollaex"),
            ("HTX (Huobi)", "htx"),
            ("Huobi Legacy", "huobi"),
            ("Hyperliquid", "hyperliquid"),
            ("Independent Reserve", "independentreserve"),
            ("INDODAX", "indodax"),
            ("Kraken", "kraken"),
            ("Kraken Futures", "krakenfutures"),
            ("KuCoin", "kucoin"),
            ("KuCoin Futures", "kucoinfutures"),
            ("Latoken", "latoken"),
            ("LBank", "lbank"),
            ("Lighter", "lighter"),
            ("Luno", "luno"),
            ("Mercado Bitcoin", "mercado"),
            ("MEXC Global", "mexc"),
            ("Mode Trade", "modetrade"),
            ("MyOKX EEA", "myokx"),
            ("NDAX", "ndax"),
            ("NovaDAX", "novadax"),
            ("OKX", "okx"),
            ("OKX US", "okxus"),
            ("One Trading", "onetrading"),
            ("OX.FUN", "oxfun"),
            ("p2b", "p2b"),
            ("Pacifica", "pacifica"),
            ("Paradex", "paradex"),
            ("Paymium", "paymium"),
            ("Phemex", "phemex"),
            ("Poloniex", "poloniex"),
            ("Tokocrypto", "tokocrypto"),
            ("Toobit", "toobit"),
            ("Upbit", "upbit"),
            ("Waves Exchange", "wavesexchange"),
            ("Weex", "weex"),
            ("WhiteBit", "whitebit"),
            ("WOO X", "woo"),
            ("WOOFI PRO", "woofipro"),
            ("XT.com", "xt"),
            ("YoBit", "yobit"),
            ("Zaif", "zaif"),
            ("Zebpay", "zebpay"),
        ]
        self._exchange_id_map = {f"{n} ({i})": i for n, i in _EXCHANGE_OPTIONS}
        _exc_labels = [f"{n} ({i})" for n, i in _EXCHANGE_OPTIONS]
        _cur_id = pm_settings.get("exchange_id", "bingx")
        _cur_label = next((f"{n} ({i})" for n, i in _EXCHANGE_OPTIONS if i == _cur_id), _cur_id)
        self._exchange_var = ctk.StringVar(value=_cur_label)
        ctk.CTkOptionMenu(
            left_frame,
            values=_exc_labels,
            variable=self._exchange_var,
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            fg_color=("#2b3139", "#2b3139"),
            button_color=("#f0b90b", "#f0b90b"),
            button_hover_color=("#d39e00", "#d39e00"),
            dropdown_fg_color=("#2b3139", "#2b3139"),
            dropdown_hover_color=("#343a40", "#343a40"),
            text_color="white",
            dropdown_text_color="white",
            height=36,
        ).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        lbl("API Key (or Key Name)", r, 0)
        self._api_key_var = ctk.StringVar(value=pm_settings.get("api_key", ""))
        
        key_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        key_frame.grid(row=r, column=1, padx=10, pady=5, sticky="ew")
        key_frame.grid_columnconfigure(0, weight=1)
        
        self._api_key_entry = ctk.CTkEntry(key_frame, textvariable=self._api_key_var, show="*")
        self._api_key_entry.grid(row=0, column=0, sticky="ew")
        
        def toggle_api_key():
            if self._api_key_entry.cget("show") == "*":
                self._api_key_entry.configure(show="")
                btn_key.configure(text="🙈")
            else:
                self._api_key_entry.configure(show="*")
                btn_key.configure(text="👁")
                
        btn_key = ctk.CTkButton(key_frame, text="👁", width=30, command=toggle_api_key, fg_color="transparent", border_width=1)
        btn_key.grid(row=0, column=1, padx=(5,0))
        r += 1
        
        lbl("API Secret (or Private Key)", r, 0)
        secret_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        secret_frame.grid(row=r, column=1, padx=10, pady=5, sticky="ew")
        secret_frame.grid_columnconfigure(0, weight=1)
        
        self._api_secret_txt = ctk.CTkTextbox(secret_frame, height=80)
        self._api_secret_txt.insert("1.0", pm_settings.get("api_secret", ""))
        
        self._api_secret_dummy = ctk.CTkEntry(secret_frame, show="*")
        self._api_secret_dummy.insert(0, "********************************")
        self._api_secret_dummy.configure(state="disabled")
        
        self._api_secret_dummy.grid(row=0, column=0, sticky="ew")
        
        def toggle_api_secret():
            if self._api_secret_dummy.winfo_ismapped():
                self._api_secret_dummy.grid_remove()
                self._api_secret_txt.grid(row=0, column=0, sticky="ew")
                btn_secret.configure(text="🙈")
            else:
                self._api_secret_txt.grid_remove()
                self._api_secret_dummy.grid(row=0, column=0, sticky="ew")
                btn_secret.configure(text="👁")
                
        btn_secret = ctk.CTkButton(secret_frame, text="👁", width=30, command=toggle_api_secret, fg_color="transparent", border_width=1)
        btn_secret.grid(row=0, column=1, padx=(5,0), sticky="n")
        r += 1
        
        self._use_exchange_var = ctk.BooleanVar(value=pm_settings.get("useExchangeBalance", False))
        ctk.CTkSwitch(left_frame, text="Enable Real Trading (Execute orders on Exchange)", variable=self._use_exchange_var, font=ctk.CTkFont(ui_font_family(), 11, "bold"), progress_color=COLOR_ACCENT).grid(row=r, column=0, columnspan=2, padx=10, pady=5, sticky="w"); r+=1
        
        lbl("Portfolio Refresh (min)", r, 0)
        self._refresh_min_var = ctk.StringVar(value=str(pm_settings.get("refresh_min", 1.0)))
        ctk.CTkEntry(left_frame, textvariable=self._refresh_min_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        section("Capital and Positions", r); r+=1
        
        lbl("Max % Usable Capital", r, 0)
        self._max_cap_pct_var = ctk.StringVar(value=str(pm_settings.get("maxCapitalUsagePercent", 100.0)))
        ctk.CTkEntry(left_frame, textvariable=self._max_cap_pct_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        lbl("Max % Single Position", r, 0)
        self._max_pos_pct_var = ctk.StringVar(value=str(pm_settings.get("maxPositionPercent", 20.0)))
        ctk.CTkEntry(left_frame, textvariable=self._max_pos_pct_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        lbl("Max Open Positions", r, 0)
        self._max_open_pos_var = ctk.StringVar(value=str(pm_settings.get("maxOpenPositions", 5)))
        ctk.CTkEntry(left_frame, textvariable=self._max_open_pos_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1

        section("Risk Management", r); r+=1
        
        lbl("Sizing Method", r, 0)
        self._sizing_mode_var = ctk.StringVar(value=self.settings.get("sizing_mode", "margin_pct"))
        ctk.CTkOptionMenu(
            left_frame,
            variable=self._sizing_mode_var,
            values=["margin_pct", "risk_pct"],
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            fg_color=("#2b3139", "#2b3139"),
            button_color=("#f0b90b", "#f0b90b"),
            button_hover_color=("#d39e00", "#d39e00"),
            dropdown_fg_color=("#2b3139", "#2b3139"),
            dropdown_hover_color=("#343a40", "#343a40"),
            text_color="white",
            dropdown_text_color="white",
            height=36,
        ).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        lbl("Risk per Trade (%)", r, 0)
        self._risk_pct_var = ctk.StringVar(value=str(self.settings.get("risk_per_trade_pct", 1.5)))
        ctk.CTkEntry(left_frame, textvariable=self._risk_pct_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        lbl("Minimum DCA Spacing (%)", r, 0)
        self._dca_dist_var = ctk.StringVar(value=str(self.settings.get("dca_distance_pct", 2.0)))
        ctk.CTkEntry(left_frame, textvariable=self._dca_dist_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        ctk.CTkLabel(left_frame, text="Minimum % distance from the average entry price before being able to open a new\norder in the same direction (prevents position spamming on the same level).", font=ctk.CTkFont(ui_font_family(), 10), text_color="#888888", justify="left").grid(row=r, column=0, columnspan=2, padx=35, pady=(0, 10), sticky="w"); r+=1
        
        self._multi_entry_var = ctk.BooleanVar(value=self.settings.get("allow_multiple_entries", False))
        ctk.CTkSwitch(left_frame, text="Enable Multiple Entries (DCA/Grid)", variable=self._multi_entry_var, font=ctk.CTkFont(ui_font_family(), 11, "bold"), progress_color=COLOR_ACCENT).grid(row=r, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w"); r+=1
        ctk.CTkLabel(left_frame, text="If ON: accumulates positions in the same direction only if the price deviates from the DCA Spacing.\nIf OFF: discards new signals in the same direction to avoid order spamming.", font=ctk.CTkFont(ui_font_family(), 10), text_color="#888888", justify="left").grid(row=r, column=0, columnspan=2, padx=35, pady=(0, 10), sticky="w"); r+=1
        
        self._stop_rev_var = ctk.BooleanVar(value=self.settings.get("stop_and_reverse", True))
        ctk.CTkSwitch(left_frame, text="Stop & Reverse (No simultaneous Hedge)", variable=self._stop_rev_var, font=ctk.CTkFont(ui_font_family(), 11, "bold"), progress_color=COLOR_ACCENT).grid(row=r, column=0, columnspan=2, padx=10, pady=(5, 0), sticky="w"); r+=1
        ctk.CTkLabel(left_frame, text="If ON: in case of an opposite signal, closes the old position before opening the new one (anti-double fee).\nIf OFF: keeps the old position in loss as a hedge, closes only if in profit.", font=ctk.CTkFont(ui_font_family(), 10), text_color="#888888", justify="left").grid(row=r, column=0, columnspan=2, padx=35, pady=(0, 10), sticky="w"); r+=1

        section("Trading Rules", r); r+=1
        
        lbl("Minimum AI Confidence (%)", r, 0)
        self._min_conf_var = ctk.StringVar(value=str(pm_settings.get("minimumConfidence", 50.0)))
        ctk.CTkEntry(left_frame, textvariable=self._min_conf_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        lbl("Min Exp. Return Threshold (%)", r, 0)
        self._min_exp_ret_var = ctk.StringVar(value=str(self.settings.get("ensemble_min_return_pct", 0.30)))
        ctk.CTkEntry(left_frame, textvariable=self._min_exp_ret_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        ctk.CTkLabel(left_frame, text="Minimum expected % variation calculated by the Ensemble to open the order. Discards sideways markets.", font=ctk.CTkFont(ui_font_family(), 10), text_color="#888888", justify="left").grid(row=r, column=0, columnspan=2, padx=35, pady=(0, 10), sticky="w"); r+=1
        
        lbl("Pre-Flight: Max Drift (%)", r, 0)
        self._pre_flight_drift_var = ctk.StringVar(value=str(pm_settings.get("pre_flight_drift_threshold", 25.0)))
        ctk.CTkEntry(left_frame, textvariable=self._pre_flight_drift_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        ctk.CTkLabel(left_frame, text="Maximum % price deviation towards the target at sending time (Slippage Guard).", font=ctk.CTkFont(ui_font_family(), 10), text_color="#888888", justify="left").grid(row=r, column=0, columnspan=2, padx=35, pady=(0, 10), sticky="w"); r+=1

        lbl("Pre-Flight: Max Imbalance (%)", r, 0)
        self._pre_flight_imb_var = ctk.StringVar(value=str(pm_settings.get("pre_flight_imbalance_threshold", 60.0)))
        ctk.CTkEntry(left_frame, textvariable=self._pre_flight_imb_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        ctk.CTkLabel(left_frame, text="Maximum counter-pressure % tolerated in the Order Book at sending time.", font=ctk.CTkFont(ui_font_family(), 10), text_color="#888888", justify="left").grid(row=r, column=0, columnspan=2, padx=35, pady=(0, 10), sticky="w"); r+=1
        
        lbl("Maximum Allowed Leverage", r, 0)
        self._max_leverage_var = ctk.StringVar(value=str(pm_settings.get("maxLeverage", 10)))
        ctk.CTkEntry(left_frame, textvariable=self._max_leverage_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        ctk.CTkLabel(left_frame, text="Upper limit of dynamic leverage (calculated based on 15m ATR and SL).", font=ctk.CTkFont(ui_font_family(), 10), text_color="#888888", justify="left").grid(row=r, column=0, columnspan=2, padx=35, pady=(0, 10), sticky="w"); r+=1
        
        lbl("Max SL Cap (ROI %)", r, 0)
        self._max_sl_roi_var = ctk.StringVar(value=str(pm_settings.get("maxStopLossROI", 80.0)))
        ctk.CTkEntry(left_frame, textvariable=self._max_sl_roi_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        lbl("Max TP Cap (ROI %)", r, 0)
        self._max_tp_roi_var = ctk.StringVar(value=str(pm_settings.get("maxTakeProfitROI", 200.0)))
        ctk.CTkEntry(left_frame, textvariable=self._max_tp_roi_var).grid(row=r, column=1, padx=10, pady=5, sticky="ew"); r+=1
        
        ctk.CTkButton(
            left_frame,
            text="💾 Save Settings",
            command=self._save_settings,
            font=ctk.CTkFont(ui_font_family(), 12, "bold"),
            fg_color="#f0b90b",
            hover_color="#d39e00",
            text_color="#181a20",
            height=38,
            corner_radius=8,
        ).grid(row=r, column=0, columnspan=2, padx=16, pady=20, sticky="ew"); r+=1
        
        info_card = ctk.CTkFrame(right_frame, fg_color=BG_CARD, corner_radius=12)
        info_card.pack(fill="x", padx=16, pady=8)
        
        info_text = (
            "The Portfolio Manager translates AI-generated signals into real orders (via CCXT) or simulated ones, implementing advanced risk controls and position sizing.\n\n"
            "🛡️ RISK MANAGEMENT & SIZING:\n"
            "• SIZING MODE: Select how to size positions:\n"
            "  - margin_pct: Commits a fixed percentage of the balance as margin.\n"
            "  - risk_pct: Calculates size dynamically so that the potential loss (if SL is hit) is equal to the configured 'Risk per Trade (%)' percentage.\n"
            "• MAXIMUM LEVERAGE: Upper limit imposed on leverage to avoid rapid liquidations.\n\n"
            "📈 DCA STRATEGY & MULTIPLE ENTRIES:\n"
            "• MULTIPLE ENTRIES (ON/OFF): If active, allows accumulating in the same direction (e.g. DCA or Grid). If disabled, ignores subsequent matching signals.\n"
            "• DCA SPACING (%): Minimum distance the price must travel from the average price before allowing a new matching entry. Prevents disorderly accumulation at the same price.\n\n"
            "🔄 STOP & REVERSE LOGIC:\n"
            "• If active, the arrival of an opposite signal (e.g. SHORT if LONG) closes the open position before starting the new one, optimizing commissions and avoiding simultaneous hedging.\n\n"
            "🎯 TRADING RULES & PROTECTIONS:\n"
            "• MIN EXP RETURN THRESHOLD: The Ensemble will place an order only if the predicted market movement (Expected Return) exceeds this threshold. Avoids commission losses in flat markets.\n"
            "• MINIMUM CONFIDENCE: Orders are sent only if the confidence calculated by the AI is higher than the set threshold.\n"
            "• SL/TP ROI CAPS: Limit the maximum losses or targets that can be set (in ROI percentage) to avoid unrealistic levels generated by the AI.\n"
            "• TECHNICAL SL/TP: The levels suggested by the AI are used, otherwise the system applies a dynamic calculation based on the 14-period ATR (Average True Range)."
        )
        ctk.CTkLabel(
            info_card, text=info_text, font=ctk.CTkFont(ui_font_family(), 11),
            text_color=("#c0c8e0", "#c0c8e0"), justify="left", anchor="w", wraplength=380
        ).pack(fill="both", expand=True, padx=16, pady=16)
        
    def _save_settings(self):
        try:
            pm_settings = self.settings.get("portfolio_manager", {})
            # Extracting api_secret depends on which widget is mapped
            api_secret_val = pm_settings.get("api_secret", "")
            if self._api_secret_txt.winfo_ismapped():
                api_secret_val = self._api_secret_txt.get("1.0", "end-1c").strip()

            self.settings["portfolio_manager"] = {
                "exchange_id": self._exchange_id_map.get(self._exchange_var.get(), self._exchange_var.get()),
                "useExchangeBalance": self._use_exchange_var.get(),
                "api_key": self._api_key_var.get().strip(),
                "api_secret": api_secret_val,
                "refresh_min": float(self._refresh_min_var.get()),
                "maxCapitalUsagePercent": float(self._max_cap_pct_var.get()),
                "maxPositionPercent": float(self._max_pos_pct_var.get()),
                "maxOpenPositions": int(self._max_open_pos_var.get()),
                "minimumConfidence": float(self._min_conf_var.get()),
                "maxLeverage": int(self._max_leverage_var.get()),
                "maxStopLossROI": float(self._max_sl_roi_var.get()),
                "maxTakeProfitROI": float(self._max_tp_roi_var.get()),
                "pre_flight_drift_threshold": float(self._pre_flight_drift_var.get()),
                "pre_flight_imbalance_threshold": float(self._pre_flight_imb_var.get())
            }
            
            # Root settings updates per Risk Management
            self.settings["sizing_mode"] = self._sizing_mode_var.get()
            self.settings["risk_per_trade_pct"] = float(self._risk_pct_var.get())
            self.settings["dca_distance_pct"] = float(self._dca_dist_var.get())
            self.settings["allow_multiple_entries"] = self._multi_entry_var.get()
            self.settings["stop_and_reverse"] = self._stop_rev_var.get()
            self.settings["ensemble_min_return_pct"] = float(self._min_exp_ret_var.get())
            
            save_settings(self.settings)
            self.pm = PortfolioManager(self.settings) # re-init
            self._status("✅ Settings saved. Exchange re-initialized.")
            self._update_portfolio_view()
        except Exception as e:
            messagebox.showerror("Error", f"Save error: {e}")

    # ─────────────────────────────────────────────────────────────
    # Helper: calculates SL/TP ROI% (takes leverage and direction into account)
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _calc_sl_tp_roi(price_val, entry_price, direction="LONG", leverage=1) -> str:
        """Returns the ROI% of an SL/TP level compared to the entry price.
        
        ROI% = price_change% * leverage
        LONG:  change = (target - entry) / entry
        SHORT: change = (entry - target) / entry
        """
        if price_val is None or price_val == "N/A" or price_val == "":
            return "N/A"
        try:
            pv = float(str(price_val).replace(" USDT", "").strip())
            ep = float(str(entry_price))
            lev = float(str(leverage).replace("x", "").strip()) if leverage else 1.0
            if lev < 1:
                lev = 1.0
            if ep <= 0:
                return f"{pv:.4f}"
            if direction.upper() == "SHORT":
                price_change_pct = (ep - pv) / ep
            else:
                price_change_pct = (pv - ep) / ep
            roi = price_change_pct * lev * 100
            return f"{roi:+.2f}%"
        except (ValueError, TypeError):
            return "N/A"

    # ─────────────────────────────────────────────────────────────
    # TAB 2: Stato Portafoglio
    # ─────────────────────────────────────────────────────────────
    def _build_portfolio_tab(self):
        tab = self._tabs.tab("🏦 Portfolio Status")
        
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=10)
        
        self._lbl_balance = ctk.CTkLabel(toolbar, text="Balance: ...", font=ctk.CTkFont(ui_font_family(), 12, "bold"))
        self._lbl_balance.pack(side="left")
        
        self._btn_sell = ctk.CTkButton(toolbar, text="📉 Sell Selected", command=self._sell_selected_portfolio, width=150, fg_color="#f0b90b", hover_color="#d39e00", text_color="#181a20", font=ctk.CTkFont(ui_font_family(), 12, "bold"))
        self._btn_sell.pack(side="right", padx=(10, 0))
        
        # Table
        tree_frame = tk.Frame(tab, bg="#0d0d1a")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        cols = [
            ("sel", "✓", 40),
            ("asset", "Asset", 70),
            ("type", "Type", 60),
            ("dir", "Dir", 50),
            ("leverage", "Leverage", 50),
            ("qty", "Quantity", 90),
            ("price", "Price", 80),
            ("val", "Estimated Value", 130),
            ("sl", "SL (ROI%)", 80),
            ("tp", "TP (ROI%)", 80),
            ("pnl_pct", "% PNL", 70),
            ("pnl", "PNL", 70)
        ]
        self._tree_port = ttk.Treeview(tree_frame, columns=[c[0] for c in cols], show="headings", style="Argus.Treeview")
        for c in cols:
            self._tree_port.heading(c[0], text=c[1], command=lambda _c=c[0]: self._sort_portfolio(_c))
            self._tree_port.column(c[0], width=c[2], anchor="center" if c[0]=="sel" else "e")
            
        self._tree_port.tag_configure("POS", foreground="#00e676")
        self._tree_port.tag_configure("NEG", foreground="#ff5252")
            
        self._tree_port.pack(fill="both", expand=True)
        self._port_selected_iids = set()
        self._tree_port.bind("<Button-1>", self._on_port_tree_click)

    def _update_portfolio_view(self):
        if getattr(self, "_is_updating", False):
            return
        self._is_updating = True
        self._status("Updating portfolio...")
        
        # In background
        def work():
            try:
                pos = self.pm.get_positions()
                bal = self.pm.get_balance(positions=pos)
                self._queue.put(lambda: self._refresh_portfolio_ui(bal, pos))
            except Exception as e:
                # Bind the message now: Python unbinds `e` when the except block
                # ends, so a lambda closing over it would raise NameError when the
                # GUI queue later runs it.
                msg = f"❌ Error updating portfolio: {e}"
                self._queue.put(lambda m=msg: self._status(m))
            finally:
                self._queue.put(lambda: setattr(self, "_is_updating", False))
                
        threading.Thread(target=work, daemon=True).start()
        
    def _on_port_tree_click(self, event):
        region = self._tree_port.identify("region", event.x, event.y)
        if region != "cell": return
        iid = self._tree_port.identify_row(event.y)
        if not iid: return
        tags = list(self._tree_port.item(iid, "tags"))
        if iid in self._port_selected_iids:
            self._port_selected_iids.discard(iid)
            self._tree_port.item(iid, values=("☐", *self._tree_port.item(iid, "values")[1:]), tags=tuple(tags))
        else:
            self._port_selected_iids.add(iid)
            self._tree_port.item(iid, values=("☑", *self._tree_port.item(iid, "values")[1:]), tags=tuple(tags))

    def _sort_portfolio(self, col):
        if getattr(self, '_sort_port_col', None) == col:
            self._sort_port_asc = not getattr(self, '_sort_port_asc', True)
        else:
            self._sort_port_col = col
            self._sort_port_asc = True
            
        if not hasattr(self, '_current_positions'):
            return
            
        asc = self._sort_port_asc
        reverse = not asc
        
        def safe_float(v):
            try: return float(str(v).replace('x',''))
            except: return 0.0
            
        key_map = {
            "asset": lambda p: p.get("asset", "").lower(),
            "type": lambda p: p.get("type", "").lower(),
            "dir": lambda p: p.get("direction", "").lower(),
            "leverage": lambda p: safe_float(p.get("leverage", 1)),
            "qty": lambda p: safe_float(p.get("quantity", 0)),
            "price": lambda p: safe_float(p.get("avg_price", 0)),
            "val": lambda p: safe_float(p.get("value", 0)),
            "sl": lambda p: p.get("sl", ""),
            "tp": lambda p: p.get("tp", ""),
            "pnl_pct": lambda p: safe_float(p.get("pnl_pct", 0)),
            "pnl": lambda p: safe_float(p.get("pnl", 0))
        }
        
        if col in key_map:
            self._current_positions.sort(key=key_map[col], reverse=reverse)
            
        if hasattr(self, '_last_bal'):
            self._refresh_portfolio_ui(self._last_bal, self._current_positions)

    def _refresh_portfolio_ui(self, bal, pos):
        self._last_bal = bal
        self._current_positions = pos
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self._lbl_balance.configure(text=f"Total Balance: {bal.get('total', 0):.2f} {bal.get('currency', 'USDT')} (Available: {bal.get('available', 0):.2f}) | Last Update: {now_str}")
        
        col_configs = [
            ("sel", "✓"), ("asset", "Asset"), ("type", "Type"), ("dir", "Dir"), ("leverage", "Leverage"),
            ("qty", "Quantity"), ("price", "Price"), ("val", "Estimated Value"),
            ("sl", "SL (ROI%)"), ("tp", "TP (ROI%)"), ("pnl_pct", "% PNL"), ("pnl", "PNL")
        ]
        col_id = getattr(self, '_sort_port_col', None)
        asc = getattr(self, '_sort_port_asc', True)
        for cid, header in col_configs:
            arrow = ""
            if cid == col_id:
                arrow = " ▲" if asc else " ▼"
            self._tree_port.heading(cid, text=f"{header}{arrow}")
        
        for item in self._tree_port.get_children():
            self._tree_port.delete(item)
        self._port_selected_iids.clear()
            
        for i, p in enumerate(pos):
            pnl_pct = p.get('pnl_pct', 0.0)
            tag = "POS" if pnl_pct > 0 else ("NEG" if pnl_pct < 0 else "")
            
            self._tree_port.insert("", "end", iid=str(i), values=(
                "☐",
                p.get("asset", ""),
                p.get("type", ""),
                p.get("direction", "LONG"),
                p.get("leverage", ""),
                f"{p.get('quantity', 0):.6f}",
                f"{p.get('avg_price', 0):.4f}",
                f"{p.get('value', 0):.2f}",
                self._calc_sl_tp_roi(p.get("sl"), p.get("avg_price", 0), p.get("direction", "LONG"), p.get("leverage", "1x")),
                self._calc_sl_tp_roi(p.get("tp"), p.get("avg_price", 0), p.get("direction", "LONG"), p.get("leverage", "1x")),
                f"{pnl_pct:.2f}%",
                f"{p.get('pnl', 0.0):.2f}"
            ), tags=(tag,) if tag else ())
            
        self._current_positions = pos
        self._status("✅ Portfolio updated.")

    def _sell_selected_portfolio(self):
        selected_iids = list(self._port_selected_iids)
        if not selected_iids:
            messagebox.showinfo("No selection", "Select at least one asset to sell.")
            return
            
        if not messagebox.askyesno("Confirmation", f"Are you sure you want to market sell the entire position of the {len(selected_iids)} selected assets?"):
            return
            
        # Read straight from the position records instead of re-parsing the
        # formatted tree cells (the iid is the index into _current_positions).
        positions = getattr(self, "_current_positions", []) or []
        items_to_sell = []
        for iid in selected_iids:
            try:
                pos = positions[int(iid)]
            except (ValueError, IndexError):
                continue
            try:
                qty = float(pos.get("quantity", 0) or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty <= 0:
                continue
            items_to_sell.append({
                "asset": pos.get("asset", ""),
                "type": pos.get("type", "Spot"),
                "direction": pos.get("direction", "LONG"),
                "quantity": qty,
            })

        if not items_to_sell:
            messagebox.showwarning("Nothing to sell", "The selected rows have no sellable quantity.")
            return


        self._btn_sell.configure(state="disabled")
        self._status("🚀 Selling assets in progress...")
        
        def work():
            results = self.pm.sell_portfolio_assets(items_to_sell)
            success = sum(1 for r in results if r.get("status") == "EXECUTED")
            self._queue.put(lambda: self._on_assets_sold(success, len(results)))
            
        threading.Thread(target=work, daemon=True).start()

    def _on_assets_sold(self, success, total):
        self._status(f"✅ Sale completed: {success}/{total} successfully.")
        self._btn_sell.configure(state="normal")
        self._update_portfolio_view()

    # ─────────────────────────────────────────────────────────────
    # TAB 3: Ordini Proposti
    # ─────────────────────────────────────────────────────────────
    def _build_orders_tab(self):
        tab = self._tabs.tab("📋 Proposed Orders")
        
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=10)
        
        self._btn_generate = ctk.CTkButton(toolbar, text="🔄 Generate Proposals", command=self._generate_orders, width=150, fg_color="#f0b90b", hover_color="#d39e00", text_color="#181a20", font=ctk.CTkFont(ui_font_family(), 12, "bold"))
        self._btn_generate.pack(side="left")
        
        self._btn_execute = ctk.CTkButton(toolbar, text="🚀 Execute Orders", command=self._execute_orders, width=150, fg_color="#f0b90b", hover_color="#d39e00", text_color="#181a20", font=ctk.CTkFont(ui_font_family(), 12, "bold"), state="disabled")
        self._btn_execute.pack(side="right", padx=(10, 0))
        
        self._btn_delete = ctk.CTkButton(toolbar, text="🗑️ Delete Selected", command=self._delete_selected_orders, width=150, fg_color="#f0b90b", hover_color="#d39e00", text_color="#181a20", font=ctk.CTkFont(ui_font_family(), 12, "bold"), state="disabled")
        self._btn_delete.pack(side="right")
        
        tree_frame = tk.Frame(tab, bg="#0d0d1a")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        cols = [
            ("sel", "✓", 40),
            ("action", "Action", 70), 
            ("asset", "Asset", 70), 
            ("dir", "Dir", 50),
            ("lev", "Leverage", 50),
            ("amount", "Amount", 80), 
            ("sl", "SL (ROI%)", 80), 
            ("tp", "TP (ROI%)", 80), 
            ("reason", "Reason", 150)
        ]
        self._tree_orders = ttk.Treeview(tree_frame, columns=[c[0] for c in cols], show="headings", style="Argus.Treeview")
        for c in cols:
            self._tree_orders.heading(c[0], text=c[1], command=lambda _c=c[0]: self._sort_orders(_c))
            self._tree_orders.column(c[0], width=c[2], anchor="center" if c[0] in ("sel", "action", "dir", "lev") else "w" if c[0]=="reason" else "e")
            
        self._tree_orders.tag_configure("BUY", background="#0d2e1a", foreground="#00e676")
        self._tree_orders.tag_configure("SELL", background="#2e0d0d", foreground="#ff5252")
        self._tree_orders.tag_configure("CLOSE", background="#2e0d0d", foreground="#ff5252")
        self._tree_orders.pack(fill="both", expand=True)
        
        self._orders_selected_iids = set()
        self._tree_orders.bind("<Button-1>", self._on_orders_tree_click)

    def _on_orders_tree_click(self, event):
        region = self._tree_orders.identify("region", event.x, event.y)
        if region != "cell": return
        iid = self._tree_orders.identify_row(event.y)
        if not iid: return
        tags = list(self._tree_orders.item(iid, "tags"))
        if iid in self._orders_selected_iids:
            self._orders_selected_iids.discard(iid)
            self._tree_orders.item(iid, values=("☐", *self._tree_orders.item(iid, "values")[1:]), tags=tuple(tags))
        else:
            self._orders_selected_iids.add(iid)
            self._tree_orders.item(iid, values=("☑", *self._tree_orders.item(iid, "values")[1:]), tags=tuple(tags))

    def _sort_orders(self, col):
        if getattr(self, '_sort_orders_col', None) == col:
            self._sort_orders_asc = not getattr(self, '_sort_orders_asc', True)
        else:
            self._sort_orders_col = col
            self._sort_orders_asc = True
            
        if not getattr(self, '_proposed_orders', None):
            return
            
        asc = self._sort_orders_asc
        reverse = not asc
        
        def safe_float(v):
            try: return float(v)
            except: return 0.0
            
        key_map = {
            "action": lambda o: o.get("action", "").lower(),
            "asset": lambda o: o.get("asset", "").lower(),
            "dir": lambda o: o.get("direction", "").lower(),
            "lev": lambda o: safe_float(o.get("leverage", 1)),
            "amount": lambda o: safe_float(o.get("amount", 0)),
            "sl": lambda o: safe_float(o.get("stopLoss", 0)),
            "tp": lambda o: safe_float(o.get("takeProfit", 0)),
            "reason": lambda o: o.get("reason", "").lower()
        }
        
        if col in key_map:
            self._proposed_orders.sort(key=key_map[col], reverse=reverse)
            
        self._refresh_orders_ui()

    def _refresh_orders_ui(self):
        col_configs = [
            ("sel", "✓"), ("action", "Action"), ("asset", "Asset"), 
            ("dir", "Dir"), ("lev", "Leverage"), ("amount", "Amount"), 
            ("sl", "SL (ROI%)"), ("tp", "TP (ROI%)"), ("reason", "Reason")
        ]
        col_id = getattr(self, '_sort_orders_col', None)
        asc = getattr(self, '_sort_orders_asc', True)
        for cid, header in col_configs:
            arrow = ""
            if cid == col_id:
                arrow = " ▲" if asc else " ▼"
            self._tree_orders.heading(cid, text=f"{header}{arrow}")
            
        for item in self._tree_orders.get_children():
            self._tree_orders.delete(item)
        self._orders_selected_iids.clear()
            
        for i, o in enumerate(self._proposed_orders):
            # Calcola ROI% di SL/TP dal prezzo corrente e leva
            curr_p = o.get("current_price", 0)
            direction = o.get("direction", "LONG")
            leverage = o.get("leverage", 1)
            sl_str = self._calc_sl_tp_roi(o.get('stopLoss'), curr_p, direction, leverage) if curr_p else "N/A"
            tp_str = self._calc_sl_tp_roi(o.get('takeProfit'), curr_p, direction, leverage) if curr_p else "N/A"
            self._tree_orders.insert("", "end", iid=str(i), values=(
                "☐",
                o["action"],
                o["asset"],
                o.get("direction", ""),
                f"{o.get('leverage', 1)}x",
                f"{o.get('amount', 0):.2f}",
                sl_str,
                tp_str,
                o.get("reason", "")
            ), tags=(o["action"],))
            
        if self._proposed_orders:
            self._btn_execute.configure(state="normal")
            self._btn_delete.configure(state="normal")
            self._status(f"🎯 {len(self._proposed_orders)} proposed orders ready.")
        else:
            self._btn_execute.configure(state="disabled")
            self._btn_delete.configure(state="disabled")
            self._status("🎯 No orders necessary. Portfolio balanced.")

    def _generate_orders(self, silent=False):
        sessions = load_all_sessions()
        if not sessions:
            self._status("No analysis session found.")
            return
            
        now = datetime.datetime.now()
        valid_results = {}
        
        for session in sessions:
            for r in session.get("results", []):
                sym = r.get("symbol")
                if not sym: continue
                
                analyzed_at_str = r.get("analyzed_at", "")
                if not analyzed_at_str: continue
                
                try:
                    dt = datetime.datetime.fromisoformat(analyzed_at_str)
                    # Consider valid only analyses performed within the last hour
                    if (now - dt).total_seconds() <= 3600:
                        # Since sessions are sorted from most recent, keep only the first (newest) per asset
                        if sym not in valid_results:
                            valid_results[sym] = r
                except Exception:
                    pass
                    
        latest_results = list(valid_results.values())
        if not latest_results:
            if not silent:
                messagebox.showinfo("No valid analysis", "There are no analyses completed within the last hour. Start a new Advanced Analysis.")
            self._proposed_orders = []
            self._refresh_orders_ui()
            return
            
        orders = self.pm.generate_orders(latest_results)
        self._proposed_orders = orders
        self._refresh_orders_ui()
        
        if not silent:
            self._status(f"🎯 Generated {len(orders)} proposals based on valid analyses (last hour).")
            
    def _delete_selected_orders(self):
        selected_iids = list(self._orders_selected_iids)
        if not selected_iids:
            messagebox.showinfo("No selection", "Select at least one order to delete.")
            return
            
        indices_to_delete = [int(iid) for iid in selected_iids]
            
        for idx in sorted(indices_to_delete, reverse=True):
            if idx < len(self._proposed_orders):
                del self._proposed_orders[idx]
                
        self._status(f"🗑️ Deleted {len(indices_to_delete)} orders. Remaining: {len(self._proposed_orders)}")
        self._refresh_orders_ui()

    def _execute_orders(self, silent=False):
        if not getattr(self, '_proposed_orders', None):
            return
            
        selected_iids = list(self._orders_selected_iids)
        
        # If there are selected orders, execute only those, otherwise ask for all
        if selected_iids:
            indices = [int(iid) for iid in selected_iids]
            orders_to_execute = [self._proposed_orders[i] for i in indices if i < len(self._proposed_orders)]
            msg = f"Are you sure you want to execute the {len(orders_to_execute)} SELECTED orders?"
        else:
            orders_to_execute = self._proposed_orders
            msg = f"Are you sure you want to execute ALL the {len(orders_to_execute)} orders in the list?"
            
        if not silent and not messagebox.askyesno("Confirmation", msg):
            return
            
        self._btn_execute.configure(state="disabled")
        self._btn_delete.configure(state="disabled")
        self._status("🚀 Executing orders...")
        
        def work():
            results = self.pm.place_orders(orders_to_execute)
            success = sum(1 for r in results if r.get("status") in ("EXECUTED", "SIMULATED"))
            
            # Unselected ones remain in the list
            self._queue.put(lambda: self._on_orders_executed(success, len(results), indices if selected_iids else None))
            
        threading.Thread(target=work, daemon=True).start()

    def _on_orders_executed(self, success, total, indices_executed):
        self._status(f"✅ Orders executed: {success}/{total} successfully.")
        
        if indices_executed:
            for idx in sorted(indices_executed, reverse=True):
                if idx < len(self._proposed_orders):
                    del self._proposed_orders[idx]
            self._refresh_orders_ui()
        else:
            # Clear all proposed orders and reload
            self._proposed_orders = []
            self._refresh_orders_ui()
                
        self._update_portfolio_view()
