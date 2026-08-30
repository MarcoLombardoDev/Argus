# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

import threading
from tkinter import ttk

import customtkinter as ctk

from core.btc_pattern_matcher import BTCPatternMatcher
from core.data_manager import load_pm_history, save_pm_history, save_settings
from core.fonts import ui_font_family
from gui.utils import apply_binance_tab_style, dark_scrollbar

_BG_PANEL = "#181a20"
_ACCENT = "#f0b90b"
_HOVER = "#d39e00"
_MUTED = "#848e9c"
_TEXT = "#eaecef"
_CARD = "#1e2329"
_SEP = "#474d57"

class PatternMatchingPanel(ctk.CTkFrame):
    def __init__(self, master, settings: dict = None, **kwargs):
        super().__init__(master, fg_color=_BG_PANEL, border_color=_SEP, border_width=1, corner_radius=12, **kwargs)
        self.settings = settings or {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Inizializzazione variabili per le impostazioni
        self._cg_key_var = ctk.StringVar(value=self.settings.get("coingecko_api_key", ""))
        self._cg_plan_var = ctk.StringVar(value=self.settings.get("coingecko_api_plan", "demo"))
        self._interval_var = ctk.StringVar(value="15m")
        self._query_window_var = ctk.StringVar(value="16")
        self._projection_window_var = ctk.StringVar(value="16")
        self._history_years_var = ctk.StringVar(value=str(self.settings.get("pm_history_years", 1)))
        self._n_neighbors_var = ctk.StringVar(value=str(self.settings.get("pm_n_neighbors", 5)))

        self.matcher = BTCPatternMatcher()
        self._history = load_pm_history()
        self._build_ui()
        self._load_history_to_ui()

    def _load_history_to_ui(self):
        for row in reversed(self._history):
            self._tree.insert("", 0, values=(
                row.get("name", "Bitcoin"),
                row.get("symbol", "BTC"),
                row.get("matches", 0),
                row.get("conf", "0.00%"),
                row.get("target", "N/A"),
                row.get("move", "0.00%"),
                row.get("expiry", "")
            ), tags=(row.get("tag", "neutral"),))

    def _build_ui(self):
        # ── Sub-header: title + status + run button ────────────
        sub_hdr = ctk.CTkFrame(self, fg_color="transparent", height=48)
        sub_hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        sub_hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            sub_hdr,
            text="BTC Pattern Matching",
            font=ctk.CTkFont(family=ui_font_family(), size=13, weight="bold"),
            text_color=_ACCENT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.status_label = ctk.CTkLabel(
            sub_hdr,
            text="·  Ready. Run an analysis.",
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            text_color=_MUTED,
            anchor="w",
        )
        self.status_label.grid(row=0, column=1, padx=(10, 8), sticky="ew")

        self.btn_run = ctk.CTkButton(
            sub_hdr,
            text="▶  Run Pattern Matching",
            command=self._start_analysis,
            font=ctk.CTkFont(family=ui_font_family(), size=12, weight="bold"),
            fg_color=_ACCENT,
            hover_color=_HOVER,
            text_color="#181a20",
            height=34,
            width=230,
            corner_radius=8,
        )
        self.btn_run.grid(row=0, column=2, sticky="e")

        # Horizontal Separator
        ctk.CTkFrame(self, height=1, fg_color=_SEP).grid(
            row=0, column=0, sticky="ew", padx=16, pady=(58, 0)
        )

        # Tabview
        self._tab_view = ctk.CTkTabview(
            self,
            fg_color="transparent",
            segmented_button_fg_color=("#2b3139", "#2b3139"),
            segmented_button_selected_color=_ACCENT,
            segmented_button_selected_hover_color=_HOVER,
            segmented_button_unselected_color=self.master.cget("fg_color") if hasattr(self.master, "cget") else _BG_PANEL,
            segmented_button_unselected_hover_color=("#343a40", "#343a40"),
            text_color="white",
        )
        self._tab_view.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self._TAB_HISTORY = "📈 Analysis History"
        self._TAB_SETTINGS = "⚙️ Settings"

        for tab in [self._TAB_HISTORY, self._TAB_SETTINGS]:
            self._tab_view.add(tab)
            self._tab_view.tab(tab).grid_columnconfigure(0, weight=1)
            self._tab_view.tab(tab).grid_rowconfigure(0, weight=1)

        apply_binance_tab_style(self._tab_view._segmented_button)

        # ── Results Table (in History Tab) ─────────────────────────────────
        tab_history = self._tab_view.tab(self._TAB_HISTORY)
        tree_frame = ctk.CTkFrame(tab_history, fg_color="transparent")
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        cols = [
            ("name", "Name", 150, "w"),
            ("symbol", "Symbol", 100, "center"),
            ("matches", "Matches Found", 120, "center"),
            ("conf", "Confidence", 120, "center"),
            ("target", "Target 2h", 120, "e"),
            ("move", "Var% 2h", 120, "e"),
            ("expiry_date", "Expiry", 130, "center")
        ]
        col_ids = [c[0] for c in cols]

        self._tree = ttk.Treeview(
            tree_frame, columns=col_ids, show="headings", style="Argus.Treeview", selectmode="browse"
        )
        self._tree.grid(row=0, column=0, sticky="nsew")

        for col_id, header, width, anchor in cols:
            self._tree.heading(col_id, text=header)
            self._tree.column(col_id, width=width, anchor=anchor)

        self._tree.tag_configure("positive", background="#0d2e1a", foreground="#00e676")
        self._tree.tag_configure("negative", background="#2e0d0d", foreground="#ff5252")
        self._tree.tag_configure("neutral", background="#1a1e2e", foreground="#b0b8d0")

        vsb = dark_scrollbar(tree_frame, "vertical", self._tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=vsb.set)

        self._build_settings_tab()

    def _build_settings_tab(self):
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
                font=ctk.CTkFont(family=ui_font_family(), size=11, weight="bold"),
                text_color=_ACCENT,
                anchor="w",
            ).grid(row=row, column=0, padx=8, pady=(16, 4), sticky="ew")

        def field_label(text, parent, row):
            ctk.CTkLabel(
                parent,
                text=text,
                font=ctk.CTkFont(family=ui_font_family(), size=11),
                text_color=_MUTED,
                anchor="w",
            ).grid(row=row, column=0, padx=8, pady=(8, 2), sticky="ew")

        def separator(parent, row):
            ctk.CTkFrame(parent, height=1, fg_color=("#2a2a4a", "#2a2a4a")).grid(
                row=row, column=0, padx=8, pady=4, sticky="ew"
            )

        # --- CoinGecko API Key ---
        r = 0
        section_title("₿ HISTORICAL DATA PROVIDER", left_frame, row=r); r += 1
        separator(left_frame, row=r); r += 1
        field_label("CoinGecko API Key", left_frame, row=r); r += 1
        self._build_password_field(left_frame, self._cg_key_var, "CG-xxxxxxxxxxxxxxxxxxxx", row=r); r += 1
        ctk.CTkLabel(
            left_frame,
            text="The API key to authenticate historical price requests to CoinGecko (optional for demo limits).",
            font=ctk.CTkFont(family=ui_font_family(), size=10),
            text_color=_MUTED,
            justify="left",
            anchor="w",
            wraplength=380
        ).grid(row=r, column=0, padx=8, pady=(0, 10), sticky="ew"); r += 1

        # --- KNN parameters ---
        section_title("📈 KNN-DTW ALGORITHM PARAMETERS", left_frame, row=r); r += 1
        separator(left_frame, row=r); r += 1

        field_label("Historical Years to Scan", left_frame, row=r); r += 1
        ctk.CTkEntry(
            left_frame,
            textvariable=self._history_years_var,
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            fg_color=("#16213e", "#16213e"),
            border_color=_ACCENT,
            border_width=1,
            height=36,
        ).grid(row=r, column=0, padx=8, pady=(4, 2), sticky="ew"); r += 1
        ctk.CTkLabel(
            left_frame,
            text="The amount of past years over which the KNN algorithm will search for historical patterns similar to the current one.",
            font=ctk.CTkFont(family=ui_font_family(), size=10),
            text_color=_MUTED,
            justify="left",
            anchor="w",
            wraplength=380
        ).grid(row=r, column=0, padx=8, pady=(0, 10), sticky="ew"); r += 1

        field_label("Number of Neighbors (K-NN)", left_frame, row=r); r += 1
        ctk.CTkEntry(
            left_frame,
            textvariable=self._n_neighbors_var,
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            fg_color=("#2b3139", "#2b3139"),
            border_color=_ACCENT,
            border_width=1,
            height=36,
        ).grid(row=r, column=0, padx=8, pady=(4, 2), sticky="ew"); r += 1
        ctk.CTkLabel(
            left_frame,
            text="The number of most similar historical patterns (K) to consider for formulating the projection (default 5).",
            font=ctk.CTkFont(family=ui_font_family(), size=10),
            text_color=_MUTED,
            justify="left",
            anchor="w",
            wraplength=380
        ).grid(row=r, column=0, padx=8, pady=(0, 10), sticky="ew"); r += 1

        # --- Save Button ---
        self._btn_save = ctk.CTkButton(
            left_frame,
            text="💾 Save Settings",
            command=self._save_pm_settings,
            font=ctk.CTkFont(family=ui_font_family(), size=12, weight="bold"),
            fg_color=_ACCENT,
            hover_color=_HOVER,
            text_color="#181a20",
            height=38,
            corner_radius=8,
        )
        self._btn_save.grid(row=r, column=0, padx=8, pady=(16, 6), sticky="ew")

        # ── Right Frame (Information) ───────────────────────────────────────
        right_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(20, 16), pady=16)
        right_frame.grid_columnconfigure(0, weight=1)

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
            text="💡 KNN-DTW PATTERN MATCHING METHODOLOGY",
            font=ctk.CTkFont(family=ui_font_family(), size=12, weight="bold"),
            text_color=_ACCENT,
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        info_text = (
            "The Pattern Matching module identifies historical price patterns similar to the current one on Bitcoin (BTC), projecting the expected future trend.\n\n"
            "📈 KNN-DTW METHODOLOGY (NEAREST NEIGHBORS):\n"
            "• The system extracts the recent log returns series of BTC (last 8 candles at 15m, equal to the last 2 hours) and normalizes it (Z-Score) to eliminate scale or absolute value differences.\n"
            "• Using the K-Nearest Neighbors (K-NN) algorithm, it scans the downloaded price history (defined by 'Historical Years') looking for the 5 most similar historical matches (Euclidean distance on normalized returns).\n"
            "• Once the most similar historical matches are identified, it analyzes the percentage movement at the 8th future candle (2-hour horizon) to estimate the expected variation ('Var% 2h') and calculate a statistical confidence level.\n\n"
            "⚡ INFORMATION ON HARDCODED PARAMETERS:\n"
            "• TIMEFRAME: Fixed at 15 minutes to align with the advanced intraday analysis.\n"
            "• QUERY / PROJECTION WINDOW: Fixed at 8 candles (2 hours) for the analysis of the recent pattern and future projection.\n"
            "• EUCLIDEAN DISTANCE & SCALER: Z-Score normalization and Euclidean distance for instant execution.\n\n"
            "⚙️ CONFIGURABLE PARAMETERS:\n"
            "• NUMBER OF NEIGHBORS (K-NN): The number of past patterns to compare (default 5).\n"
            "• HISTORICAL YEARS: The extent of the historical database to search for matches (default 1 year)."
        )

        ctk.CTkLabel(
            info_card,
            text=info_text,
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            text_color=("#c0c8e0", "#c0c8e0"),
            justify="left",
            anchor="w",
            wraplength=380,
        ).grid(row=1, column=0, padx=16, pady=(0, 16), sticky="ew")

        scroll.grid_rowconfigure(19, weight=1)

    def _build_password_field(self, parent, variable, placeholder, row):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, padx=8, pady=(4, 12), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(
            frame,
            textvariable=variable,
            placeholder_text=placeholder,
            font=ctk.CTkFont(family=ui_font_family(), size=12),
            fg_color=("#2b3139", "#2b3139"),
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
            fg_color=("#2b3139", "#2b3139"),
            hover_color=("#343a40", "#343a40"),
            border_color=_ACCENT,
            border_width=1,
            command=toggle
        )
        btn.grid(row=0, column=1, padx=(4, 0))

    def _save_pm_settings(self):
        try:
            q_win = 16
            proj_win = 16
            hist_y = int(self._history_years_var.get())
            n_neigh = int(self._n_neighbors_var.get())

            if hist_y <= 0 or n_neigh <= 0:
                raise ValueError("All numerical parameters must be positive integers greater than zero.")

            self.settings["coingecko_api_key"] = self._cg_key_var.get().strip()
            self.settings["coingecko_api_plan"] = self._cg_plan_var.get()
            self.settings["pm_interval"] = "15m"
            self.settings["pm_query_window"] = q_win
            self.settings["pm_projection_window"] = proj_win
            self.settings["pm_history_years"] = hist_y
            self.settings["pm_n_neighbors"] = n_neigh

            save_settings(self.settings)
            self.status_label.configure(text="· Settings saved successfully.")
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Validation Error", f"Error saving settings: {e}")

    def _start_analysis(self):
        self.btn_run.configure(state="disabled", text="Running...")
        self.status_label.configure(text="· Downloading data...")
        threading.Thread(target=self._run_bg, daemon=True).start()

    def _run_bg(self):
        try:
            self.matcher = BTCPatternMatcher()
            res = self.matcher.run_analysis()
            move = res.get("btc_expected_move", 0.0)
            conf = res.get("btc_pred_confidence", 0.0)
            matches = res.get("matches_count", 0)
            target = res.get("btc_target_price", 0.0)

            tag = "positive" if move > 0 else ("negative" if move < 0 else "neutral")
            move_str = f"+{move:.2f}%" if move > 0 else f"{move:.2f}%"
            conf_str = f"{conf:.2f}%"
            target_str = f"${target:.2f}" if target > 0 else "N/A"

            self.after(0, lambda: self._update_ui_success(matches, conf_str, target_str, move_str, tag))
        except Exception as e:
            # `e` is unbound once the except block exits — capture it eagerly,
            # otherwise the scheduled callback raises NameError instead of showing
            # the error.
            err = str(e)
            self.after(0, lambda m=err: self._update_ui_error(m))

    def _update_ui_success(self, matches, conf, target, move, tag):
        from datetime import datetime, timedelta
        expiry = (datetime.now() + timedelta(hours=2)).strftime("%d/%m/%Y %H:%M")

        new_row = {
            "name": "Bitcoin",
            "symbol": "BTC",
            "matches": matches,
            "conf": conf,
            "target": target,
            "move": move,
            "expiry": expiry,
            "tag": tag
        }
        self._history.insert(0, new_row)

        self._tree.insert("", 0, values=("Bitcoin", "BTC", matches, conf, target, move, expiry), tags=(tag,))

        if len(self._history) > 50:
            self._history = self._history[:50]

        children = self._tree.get_children()
        if len(children) > 50:
            for iid in children[50:]:
                self._tree.delete(iid)

        save_pm_history(self._history)

        self.status_label.configure(text=f"· Analysis completed. Found {matches} similar patterns.")
        self.btn_run.configure(state="normal", text="▶  Run Pattern Matching")

    def _update_ui_error(self, err_msg):
        self.status_label.configure(text=f"· Error: {err_msg}")
        self.btn_run.configure(state="normal", text="▶  Retry")
