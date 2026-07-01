"""
markets_panel.py — Argus
"Markets" panel with Crypto / Nasdaq / S&P500 + Settings tabs.
Manages the list of available assets for analysis and data providers configuration.
"""

import threading
import queue
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
from gui.utils import apply_binance_tab_style

from core.data_manager import (
    load_settings, save_settings,
    save_market_list, load_market_list, delete_market_list, get_market_list_info,
)

# Theme colors (aligned with app.py)
_BG_PANEL  = ("#1e2329", "#1e2329")
_BG_INPUT  = ("#2b3139", "#2b3139")
_ACCENT    = ("#f0b90b", "#f0b90b")
_HOVER     = ("#d39e00", "#d39e00")
_MUTED     = ("#848e9c", "#848e9c")
_SEP       = ("#474d57", "#474d57")
_BG_ROW_A  = ("#181a20", "#181a20")
_BG_ROW_B  = ("#1e2329", "#1e2329")
_GREEN     = ("#02c076", "#02c076")
_RED       = ("#cf304a", "#cf304a")


class MarketsPanel(ctk.CTkFrame):
    """
    Main panel of the Markets section.
    Contains a CTkTabview with the tabs:
      ₿  Crypto  |  ⚙️ Settings
    """

    def __init__(self, parent, settings: dict, **kwargs):
        super().__init__(
            parent,
            fg_color=_BG_PANEL,
            border_color=_SEP,
            border_width=1,
            corner_radius=12,
            **kwargs
        )

        self._settings = settings
        self._refresh_queue: queue.Queue = queue.Queue()
        self._refreshing = False
        self._loaded_lists = {}
        self._search_vars = {}
        self._search_entries = {}
        self._sort_cols = {"crypto": "updated_at"}
        self._sort_ascs = {"crypto": False}

        # Initialize settings variables
        self._cg_key_var = ctk.StringVar(value=self._settings.get("coingecko_api_key", ""))
        self._cg_plan_var = ctk.StringVar(value=self._settings.get("coingecko_api_plan", "demo"))

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_tabview()
        self._load_all_lists()

    # ─────────────────────────────────────────────────────────────────────────
    # Header: title + status + Refresh Prices button
    # ─────────────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent", height=48)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr,
            text="Markets",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=_ACCENT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        self._status_label = ctk.CTkLabel(
            hdr,
            text="📂  Market prices and data (BTC Only).",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=_MUTED,
            anchor="w",
        )
        self._status_label.grid(row=0, column=1, padx=(4, 8), sticky="ew")

        self._btn_refresh_prices = ctk.CTkButton(
            hdr,
            text="💵  Refresh Prices",
            command=self._on_refresh_prices_clicked,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_ACCENT,
            hover_color=_HOVER,
            text_color="#181a20",
            height=34,
            width=160,
            corner_radius=8,
        )
        self._btn_refresh_prices.grid(row=0, column=2, sticky="e")

        # Separator
        ctk.CTkFrame(self, height=1, fg_color=_SEP).grid(
            row=0, column=0, sticky="ew", padx=16, pady=(58, 0)
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TabView: Crypto / Settings
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tabview(self):
        self._tab_view = ctk.CTkTabview(
            self,
            fg_color=_BG_PANEL,
            segmented_button_fg_color=("#2b3139", "#2b3139"),
            segmented_button_selected_color=_ACCENT,
            segmented_button_selected_hover_color=_HOVER,
            segmented_button_unselected_color=_BG_PANEL,
            segmented_button_unselected_hover_color=("#343a40", "#343a40"),
            text_color="white",
        )
        self._tab_view.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self._TAB_CRYPTO  = "₿  Crypto"
        self._TAB_SETTINGS = "⚙️  Settings"

        for tab in [self._TAB_CRYPTO, self._TAB_SETTINGS]:
            self._tab_view.add(tab)
            self._tab_view.tab(tab).grid_columnconfigure(0, weight=1)
            self._tab_view.tab(tab).grid_rowconfigure(0, weight=1)

        apply_binance_tab_style(self._tab_view._segmented_button)

        # Build content for each tab
        self._list_widgets = {}
        self._last_update_labels: dict[str, ctk.CTkLabel] = {}
        self._list_widgets["crypto"] = self._build_asset_list_tab(self._TAB_CRYPTO, "crypto")
        self._build_settings_tab()

    def _get_update_timestamps(self, market_type: str) -> tuple[str, str]:
        """Returns the timestamp strings for list update and price update."""
        list_time = self._settings.get(f"last_list_update_{market_type}")
        if not list_time:
            from core.data_manager import MARKET_LISTS_DIR, MARKET_LIST_FILES
            filename = MARKET_LIST_FILES.get(market_type)
            if filename:
                path = MARKET_LISTS_DIR / filename
                if path.exists():
                    try:
                        from datetime import datetime as dt
                        list_time = dt.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                    except Exception:
                        list_time = "Never"
                else:
                    list_time = "Never"
            else:
                list_time = "Never"
        
        price_time = self._settings.get(f"last_price_update_{market_type}", "Never")
        return list_time, price_time

    def _build_asset_list_tab(self, tab_name: str, market_type: str) -> ttk.Treeview:
        """Builds the asset list tab using a Treeview similar to results."""
        tab = self._tab_view.tab(tab_name)

        # Container with Treeview
        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        # Initialize the search variable in background for filter compatibility
        search_var = ctk.StringVar()
        self._search_vars[market_type] = search_var

        # Treeview container
        tree_frame = tk.Frame(container, bg="#0d0d1a")
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=2)
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        # Setup style
        from gui.ai_analysis_panel import _setup_treeview_style
        _setup_treeview_style()

        columns = ("name", "symbol", "price", "change_pct", "updated_at")
        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            style="Argus.Treeview",
            selectmode="browse",
        )
        tree.grid(row=0, column=0, sticky="nsew")

        # Configure columns
        col_configs = [
            ("name", "Name", 150, "w", True),
            ("symbol", "Symbol", 90, "center", False),
            ("price", "Price", 110, "e", False),
            ("change_pct", "Change%", 90, "e", False),
            ("updated_at", "Last Updated", 150, "center", False),
        ]
        for col_id, header, width, anchor, stretch in col_configs:
            tree.heading(col_id, text=header, command=lambda c=col_id: self._sort_by(market_type, c))
            tree.column(col_id, width=width, anchor=anchor, stretch=stretch, minwidth=30)

        # Configure tags for signal-based colors (matching results table)
        tree.tag_configure("buy",  background="#0d2e1a", foreground="#00e676")
        tree.tag_configure("sell", background="#2e0d0d", foreground="#ff5252")
        tree.tag_configure("hold", background="#1a1e2e", foreground="#b0b8d0")
        tree.tag_configure("na",   background="#111827", foreground="#555577")
        tree.tag_configure("buy_alt",  background="#0a2616", foreground="#00e676")
        tree.tag_configure("sell_alt", background="#280b0b", foreground="#ff5252")
        tree.tag_configure("hold_alt", background="#161a28", foreground="#b0b8d0")

        # Vertical scrollbar
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)

        return tree

    def _build_settings_tab(self):
        """Builds the Settings tab with top-N, CoinGecko, Massive, AlphaVantage."""
        tab = self._tab_view.tab(self._TAB_SETTINGS)

        scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=("#1a1a2e", "#0d0d1a"),
            corner_radius=0,
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1, minsize=400)
        scroll.grid_columnconfigure(1, weight=1, minsize=400)

        # ── Left Frame (Settings) ───────────────────────────────────────────
        left_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(16, 20), pady=16)
        left_frame.grid_columnconfigure(0, weight=1)

        def section_title(text, parent, row):
            ctk.CTkLabel(
                parent,
                text=text,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=_ACCENT,
                anchor="w",
            ).grid(row=row, column=0, padx=8, pady=(16, 4), sticky="ew")

        def field_label(text, parent, row):
            ctk.CTkLabel(
                parent,
                text=text,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=_MUTED,
                anchor="w",
            ).grid(row=row, column=0, padx=8, pady=(8, 2), sticky="ew")

        def separator(parent, row):
            ctk.CTkFrame(parent, height=1, fg_color=("#2a2a4a", "#2a2a4a")).grid(
                row=row, column=0, padx=8, pady=4, sticky="ew"
            )

        # --- CoinGecko (Crypto) ---
        section_title("₿  CRYPTO PROVIDER", left_frame, row=0)
        separator(left_frame, row=1)
        field_label("CoinGecko API Key", left_frame, row=2)
        
        self._build_password_field(left_frame, self._cg_key_var, "CG-xxxxxxxxxxxxxxxxxxxx", row=3)
        ctk.CTkLabel(
            left_frame,
            text="The API key used to download crypto data from CoinGecko. For demo plans, enter the public key. It will be saved encrypted in .env.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=_MUTED,
            justify="left",
            anchor="w",
            wraplength=380
        ).grid(row=4, column=0, padx=8, pady=(0, 10), sticky="ew")

        # --- Save Button ---
        self._btn_save = ctk.CTkButton(
            left_frame,
            text="💾 Save Settings",
            command=self._save_market_settings,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_ACCENT,
            hover_color=_HOVER,
            text_color="#181a20",
            height=38,
            corner_radius=8,
        )
        self._btn_save.grid(row=14, column=0, padx=8, pady=(16, 6), sticky="ew")

        # ── Right Frame (Information) ───────────────────────────────────────
        right_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(20, 16), pady=16)
        right_frame.grid_columnconfigure(0, weight=1)

        # Info Box Card (Premium design with nice border and background)
        info_card = ctk.CTkFrame(
            right_frame,
            fg_color=("#16213e", "#111827"),
            border_color=_SEP,
            border_width=1,
            corner_radius=12,
        )
        info_card.grid(row=0, column=0, sticky="nsew", padx=8, pady=16)
        info_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            info_card,
            text="💡 DATA LOADING MECHANISMS & LOGIC",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=_ACCENT,
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        info_text = (
            "The Markets module is the heart of the application. All data needed by the analytical agents is downloaded and centralized here.\n\n"
            "📡 CURRENT AND HISTORICAL UPDATE LOGIC:\n"
            "• CURRENT PRICE: The application attempts to fetch the live price from the Exchange (via CCXT). If it fails or is not configured, it uses CoinGecko.\n"
            "• BTC HISTORY (15m, 1 Year): In addition to current prices, the 'Refresh Prices' button downloads and stores locally the last year of 15-minute candles for Bitcoin (fallback 60 days on YFinance).\n\n"
            "📂 STATELESS AGENT ARCHITECTURE:\n"
            "• The Analysis modules (TimesFM, Pattern Matcher, AI Agents) no longer download data independently from the internet to avoid IP bans and slowdowns.\n"
            "• All modules read from the local cache generated on this screen. If the cached data is older than 2 hours, the analysis stops, prompting you to return here and update.\n"
            "• NOTE: During Autotrading, the app bypasses this block by automatically refreshing the history at each continuous cycle.\n\n"
            "📰 NEWS FETCHING:\n"
            "• News is fetched concurrently with the AI Analysis and filtered for the last hour (with a historical fallback limited to 3) to maximize the predictive relevance of the agents for the set horizon."
        )

        ctk.CTkLabel(
            info_card,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("#c0c8e0", "#c0c8e0"),
            justify="left",
            anchor="w",
            wraplength=380,
        ).grid(row=1, column=0, padx=16, pady=(0, 16), sticky="ew")

        scroll.grid_rowconfigure(15, weight=1)

    def _build_password_field(self, parent, variable, placeholder, row):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, padx=8, pady=(4, 12), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(
            frame,
            textvariable=variable,
            placeholder_text=placeholder,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=_BG_INPUT,
            border_color=_ACCENT,
            border_width=1,
            height=34,
            show="*"
        )
        entry.grid(row=0, column=0, sticky="ew")

        def toggle():
            if entry.cget("show") == "*":
                entry.configure(show="")
                btn.configure(text="🙈")
            else:
                entry.configure(show="*")
                btn.configure(text="👁")

        btn = ctk.CTkButton(
            frame,
            text="👁",
            width=34,
            height=34,
            fg_color=_BG_INPUT,
            hover_color=("#343a40", "#343a40"),
            border_color=_ACCENT,
            border_width=1,
            command=toggle
        )
        btn.grid(row=0, column=1, padx=(4, 0))

    # ─────────────────────────────────────────────────────────────────────────
    # Loading and displaying lists
    # ─────────────────────────────────────────────────────────────────────────

    def _load_all_lists(self):
        """Loads all saved lists and displays them in the tabs."""
        self._loaded_lists = {}
        for market_type in ("crypto",):
            asset_list = load_market_list(market_type)
            self._loaded_lists[market_type] = asset_list
            self._populate_list(market_type, asset_list)

        # Update status with info
        msgs = []
        for mt, label in [("crypto", "Crypto")]:
            info = get_market_list_info(mt)
            msgs.append(f"{label}: {info}")
        self._update_status(" | ".join(msgs))

    def _populate_list(self, market_type: str, asset_list: list[dict], update_labels: bool = True):
        """Populates the tab's Treeview with the asset list."""
        tree = self._list_widgets.get(market_type)
        if tree is None:
            return

        # Clear previous content
        for item in tree.get_children():
            tree.delete(item)

        # Update the last update label
        if update_labels:
            lbl = self._last_update_labels.get(market_type)
            if lbl:
                list_time, price_time = self._get_update_timestamps(market_type)
                lbl.configure(text=f"List Update: {list_time} | Price Update: {price_time}")

        if not asset_list:
            query = self._search_vars.get(market_type)
            query_str = query.get().strip() if query else ""
            if query_str:
                tree.insert("", "end", values=(
                    "No asset matches the search query.", "", "", "", ""
                ))
            else:
                tree.insert("", "end", values=(
                    "No data available. Press '🔄 Refresh Prices' to download.", "", "", "", ""
                ))
            return

        for i, asset in enumerate(asset_list):
            rank = asset.get("rank", i + 1)
            symbol = asset.get("symbol", "")
            name = asset.get("name", "")
            price = asset.get("current_price", 0.0)
            change_pct = asset.get("price_change_pct")
            updated_at = asset.get("updated_at", "")

            price_text = _format_price(price)
            if change_pct is None:
                change_pct_text = "N/A"
                tag_base = "na"
            else:
                sign = "+" if change_pct >= 0 else ""
                change_pct_text = f"{sign}{change_pct:.2f}%"
                if change_pct > 0.0:
                    tag_base = "buy"
                elif change_pct < 0.0:
                    tag_base = "sell"
                else:
                    tag_base = "hold"

            tag = tag_base if i % 2 == 0 else f"{tag_base}_alt"
            if tag not in ("buy_alt", "sell_alt", "hold_alt"):
                tag = tag_base

            tree.insert("", "end", values=(
                name,
                symbol,
                price_text,
                change_pct_text,
                updated_at
            ), tags=(tag,))

    def _apply_search_filter(self, market_type: str):
        """Filters the list based on the search query (integrating sorting)."""
        self._apply_sort_and_filter(market_type)

    def _sort_by(self, market_type: str, col_id: str):
        """Handles header click event to sort the table."""
        if self._sort_cols.get(market_type) == col_id:
            self._sort_ascs[market_type] = not self._sort_ascs[market_type]
        else:
            self._sort_cols[market_type] = col_id
            self._sort_ascs[market_type] = True

        self._apply_sort_and_filter(market_type)

    def _apply_sort_and_filter(self, market_type: str):
        """Sorts the complete list and then applies the current search filter."""
        full_list = self._loaded_lists.get(market_type, [])
        col_id = self._sort_cols.get(market_type, "rank")
        asc = self._sort_ascs.get(market_type, True)
        
        reverse = not asc
        try:
            if col_id in ("price", "change_pct", "updated_at"):
                key_map = {
                    "price": "current_price",
                    "change_pct": "price_change_pct",
                    "updated_at": "updated_at"
                }
                dict_key = key_map.get(col_id, col_id)
                full_list = sorted(
                    full_list,
                    key=lambda r: (r.get(dict_key) is None,
                                   r.get(dict_key) or 0.0),
                    reverse=reverse,
                )
            else:
                dict_key = "symbol" if col_id == "symbol" else "name"
                full_list = sorted(
                    full_list,
                    key=lambda r: (r.get(dict_key) or "").lower(),
                    reverse=reverse,
                )
        except Exception as e:
            print(f"[MarketsPanel] Sorting error: {e}")
            
        self._loaded_lists[market_type] = full_list
        
        query = self._search_vars[market_type].get().strip().lower()
        if not query:
            self._populate_list(market_type, full_list, update_labels=False)
        else:
            filtered = [
                asset for asset in full_list
                if query in asset.get("symbol", "").lower() or query in asset.get("name", "").lower()
            ]
            self._populate_list(market_type, filtered, update_labels=False)
            
        tree = self._list_widgets.get(market_type)
        if tree:
            col_configs = [
                ("name", "Name"),
                ("symbol", "Symbol"),
                ("price", "Price"),
                ("change_pct", "Change%"),
                ("updated_at", "Last Updated"),
            ]
            for cid, header in col_configs:
                arrow = ""
                if cid == col_id:
                    arrow = " ▲" if asc else " ▼"
                tree.heading(cid, text=f"{header}{arrow}")

    # ─────────────────────────────────────────────────────────────────────────
    # Refresh Current List — logic
    # ─────────────────────────────────────────────────────────────────────────

    def _on_refresh_prices_clicked(self):
        """Launches price updates for the current list in background."""
        if self._refreshing:
            return

        current_tab = self._tab_view.get()
        if current_tab == self._TAB_SETTINGS:
            messagebox.showinfo(
                "Refresh Prices",
                "Please select the Crypto tab first and then click Refresh Prices."
            )
            return

        tab_to_market = {
            self._TAB_CRYPTO: "crypto",
        }
        market_type = tab_to_market.get(current_tab)
        if not market_type:
            return

        self._set_refreshing(True)
        self._update_status(f"📡 Launching price update for {market_type.upper()}...")

        threading.Thread(
            target=self._refresh_prices_thread,
            args=(market_type,),
            daemon=True,
        ).start()
        self._poll_refresh_queue()

    def _refresh_prices_thread(self, market_type: str):
        """Background thread updating list prices."""

        def status(msg: str, frac: float | None = None):
            self._refresh_queue.put({"type": "status", "text": msg, "frac": frac})

        try:
            cfg = self._settings
            cg_key = cfg.get("coingecko_api_key", "")
            cg_plan = cfg.get("coingecko_api_plan", "demo")
            massive_key = cfg.get("massive_api_key", "")
            av_key = cfg.get("alphavantage_api_key", "")
            
            # 1. Retrieve tickers from exchange (CCXT)
            exchange_tickers = {}
            try:
                from core.portfolio_manager import PortfolioManager
                pm = PortfolioManager(cfg)
                if pm.exchange and pm.exchange.apiKey and pm.exchange.has.get("fetchTickers"):
                    status("🏦 Fetching prices from exchange...", 0.05)
                    exchange_tickers = pm.exchange.fetch_tickers()
            except Exception as e:
                print(f"[MarketsPanel] Unable to fetch tickers from exchange: {e}")

            # Create a new record for BTC instead of loading full history
            asset_list = [{"symbol": "BTC", "name": "Bitcoin", "coingecko_id": "bitcoin"}]

            # Apply updates from exchange for found symbols
            missing_from_exchange = []
            for item in asset_list:
                sym = item.get("symbol", "").upper()
                found = False
                for ex_sym in [f"{sym}/USDT:USDT", f"{sym}/USDT", f"{sym}/USD", f"{sym}USDT"]:
                    if ex_sym in exchange_tickers:
                        tick = exchange_tickers[ex_sym]
                        if tick.get("last"):
                            item["current_price"] = tick["last"]
                            item["price_change_pct"] = tick.get("percentage", item.get("price_change_pct", 0.0))
                            found = True
                            break
                if not found:
                    missing_from_exchange.append(item)

            if market_type == "crypto":
                status("₿ Updating Crypto prices...", 0.1)
                if missing_from_exchange:
                    from core.data_fetcher import update_crypto_prices
                    updated_missing = update_crypto_prices(
                        crypto_list=missing_from_exchange,
                        api_key=cg_key,
                        api_plan=cg_plan,
                        progress_callback=lambda m, f=None: status(f"₿ {m}", 0.1 + (f or 0.0) * 0.4),
                    )
                    # Merge
                    miss_dict = {m["symbol"]: m for m in updated_missing}
                    for item in asset_list:
                        sym = item.get("symbol")
                        if sym in miss_dict:
                            item.update(miss_dict[sym])
                save_market_list("crypto", asset_list)
                
                # --- Centralized History Download (BTC 15m 1 year only) ---
                status("📥 Downloading BTC history (15m, 1 year)...", 0.6)
                from core.data_fetcher import fetch_historical_paginated
                from core.data_manager import save_historical
                
                try:
                    df_btc = None
                    if 'pm' in locals() and pm.exchange is not None:
                        # Fetch 365 days of 15m candles via pagination
                        df_btc = fetch_historical_paginated(pm.exchange, "BTC", timeframe="15m", days=365)
                    
                    if df_btc is not None and not df_btc.empty:
                        save_historical("BTC", df_btc)
                        status("✅ BTC history saved successfully.", 0.9)
                    else:
                        # Quick fallback if exchange pagination fails (yfinance)
                        import yfinance as yf
                        import pandas as pd
                        status("⚠️ Exchange failed, fallback history on yfinance (60 days)...", 0.7)
                        df_btc = yf.download("BTC-USD", period="60d", interval="15m", progress=False)
                        if df_btc is not None and not df_btc.empty:
                            if isinstance(df_btc.columns, pd.MultiIndex):
                                df_btc.columns = df_btc.columns.get_level_values(0)
                            df_btc = df_btc[["Open", "High", "Low", "Close", "Volume"]].copy()
                            df_btc = df_btc.dropna(subset=["Close"])
                            save_historical("BTC", df_btc)
                            status("✅ BTC history saved via yfinance.", 0.9)
                        else:
                            status("❌ Unable to download BTC history.", 0.9)
                except Exception as e:
                    print(f"[MarketsPanel] Error downloading BTC history: {e}")
                    status(f"❌ Error downloading BTC history: {e}", 0.9)
            
            import datetime
            self._refresh_queue.put({
                "type": "done_prices",
                "timestamp": datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            })

        except Exception as exc:
            import traceback
            print(f"[MarketsPanel] Exception in refresh prices:\n{traceback.format_exc()}")
            self._refresh_queue.put({"type": "error", "text": f"Error updating prices: {exc}"})

    def _poll_refresh_queue(self):
        """Consumes messages from the refresh queue."""
        try:
            while True:
                msg = self._refresh_queue.get_nowait()
                mtype = msg.get("type")

                if mtype == "status":
                    self._update_status(msg.get("text", ""))

                elif mtype == "done_prices":
                    now_str = msg.get("timestamp")
                    if not now_str:
                        import datetime
                        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
                    for mt in ("crypto",):
                        if load_market_list(mt):
                            self._settings[f"last_price_update_{mt}"] = now_str
                    save_settings(self._settings)

                    for mt in self._search_vars:
                        self._search_vars[mt].set("")

                    self._load_all_lists()
                    self._set_refreshing(False)
                    self._update_status("✅ Current list prices updated successfully!")
                    return

                elif mtype == "error":
                    self._set_refreshing(False)
                    self._update_status(f"❌ {msg.get('text', 'Unknown error')}")
                    messagebox.showerror("Error", msg.get("text", "Unknown error"))
                    return

        except queue.Empty:
            pass

        # Keep polling until finished
        if self._refreshing:
            self.after(100, self._poll_refresh_queue)

    # ─────────────────────────────────────────────────────────────────────────
    # Save settings
    # ─────────────────────────────────────────────────────────────────────────

    def _save_market_settings(self):
        """Saves markets settings in global settings."""
        updated = {
            "coingecko_api_key": self._cg_key_var.get().strip(),
            "coingecko_api_plan": self._cg_plan_var.get(),
        }
        self._settings.update(updated)
        save_settings(self._settings)
        self._update_status(
            f"✅ Settings saved | CoinGecko: {'✓' if updated['coingecko_api_key'] else '—'}"
        )

    def get_current_settings(self) -> dict:
        """Returns current settings from widgets (without saving)."""
        return {
            "coingecko_api_key": self._cg_key_var.get().strip(),
            "coingecko_api_plan": self._cg_plan_var.get(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _update_status(self, text: str):
        prefix = "📂  " if not text.startswith(("·", "✅", "❌", "📡", "📊", "⚠️", "💹", "₿", "📂")) else ""
        self._status_label.configure(text=f"{prefix}{text}")

    def _set_refreshing(self, refreshing: bool):
        self._refreshing = refreshing
        state = "disabled" if refreshing else "normal"
        if hasattr(self, "_btn_refresh_prices"):
            self._btn_refresh_prices.configure(state=state)
        if hasattr(self, "_btn_save"):
            self._btn_save.configure(state=state)

    def reload_settings(self, settings: dict):
        """Reloads settings from outside (e.g. after global save)."""
        self._settings = settings
        self._cg_key_var.set(settings.get("coingecko_api_key", ""))
        self._cg_plan_var.set(settings.get("coingecko_api_plan", "demo"))


# ─────────────────────────────────────────────────────────────────────────────
# Utility di formattazione
# ─────────────────────────────────────────────────────────────────────────────

def _format_price(price: float | None) -> str:
    if price is None or price == 0:
        return "N/A"
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.4f}"
    elif price >= 0.001:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"


def _format_market_cap(mcap: float | None) -> str:
    if mcap is None or mcap == 0:
        return "—"
    if mcap >= 1e12:
        return f"${mcap / 1e12:.2f}T"
    elif mcap >= 1e9:
        return f"${mcap / 1e9:.1f}B"
    elif mcap >= 1e6:
        return f"${mcap / 1e6:.1f}M"
    else:
        return f"${mcap:,.0f}"
