# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
results_table.py — Argus
Results table with BUY/SELL/HOLD coloring, sorting, and filters.
Implemented with tkinter.ttk.Treeview + custom style on top of CTk.
"""

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk
import pandas as pd

from core.analyzer import format_price
from core.fonts import ui_font_family
from gui.utils import dark_scrollbar

# Signal colors
SIGNAL_COLORS = {
    "BUY":  {"bg": "#0d2e1a", "fg": "#00e676", "tag": "buy"},
    "SELL": {"bg": "#2e0d0d", "fg": "#ff5252", "tag": "sell"},
    "HOLD": {"bg": "#2b3139", "fg": "#eaecef", "tag": "hold"},
    "N/A":  {"bg": "#1e2329", "fg": "#555577", "tag": "na"},
}

# Column definitions: (id, header, width, anchor, stretch)
COLUMNS = [
    ("name",            "Name",          150,  "w",      True),
    ("symbol",          "Symbol",        70,  "center", False),
    ("confidence",      "Confidence",     90,  "center", False),
    ("last_price",      "Price",        110,  "e",      False),
    ("target_price_1d", "Target 2h",    110,  "e",      False),
    ("change_pct_1d",   "Var% 2h",       135,  "e",      False),
    ("expiry_date",     "Expiry",        130,  "center", False),
]


class ResultsTable(ctk.CTkFrame):
    """
    Frame containing the results table with filters and export button.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(fg_color=("#0d0d1a", "#0d0d1a"), corner_radius=0)

        self._all_data: list[dict] = []
        self._sort_col: str = "run_date"
        self._sort_asc: bool = False
        self._filter_signal: str = "ALL"

        self._build_ui()

    # -------------------------------------------------------------------------
    # Build UI
    # -------------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Toolbar ---
        toolbar = ctk.CTkFrame(self, fg_color=("#1e2329", "#1e2329"), height=48)
        # toolbar.grid(row=0, column=0, sticky="ew", padx=0, pady=0) # Hidden toolbar as requested
        toolbar.grid_columnconfigure(2, weight=1)

        self._last_analysis_label = ctk.CTkLabel(
            toolbar,
            text="Last Analysis: None",
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            text_color=("#848e9c", "#848e9c"),
            fg_color="transparent",
        )
        self._last_analysis_label.grid(row=0, column=0, padx=(16, 6), pady=12, sticky="w")

        # Search Field
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            toolbar,
            placeholder_text="Search name or symbol...",
            textvariable=self._search_var,
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            fg_color=("#2b3139", "#2b3139"),
            border_color=("#f0b90b", "#f0b90b"),
            border_width=1,
            height=32,
            width=200,
        )
        self._search_entry.grid(row=0, column=1, padx=12, pady=8, sticky="w")
        self._search_var.trace_add("write", lambda *args: self._apply_filter_and_sort())

        # Export button
        self._btn_export = ctk.CTkButton(
            toolbar,
            text="📊 Excel",
            command=self._export_excel,
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            fg_color=("#2b3139", "#2b3139"), hover_color=("#343a40", "#343a40"),
            border_color=("#f0b90b", "#f0b90b"),
            border_width=1,
            height=30,
            width=80,
            corner_radius=6,
        )
        self._btn_export.grid(row=0, column=3, padx=16, pady=8, sticky="e")

        # --- Treeview container ---
        tree_frame = tk.Frame(self, bg="#0d0d1a")
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self._setup_style()
        self._tree = self._build_treeview(tree_frame)

        # Vertical scrollbar
        vsb = dark_scrollbar(tree_frame, "vertical", self._tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=vsb.set)

        # Horizontal scrollbar
        hsb = dark_scrollbar(tree_frame, "horizontal", self._tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self._tree.configure(xscrollcommand=hsb.set)

    def _setup_style(self):
        """Configures the dark style of the Treeview."""
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Argus.Treeview",
            background="#181a20",
            foreground="#eaecef",
            fieldbackground="#181a20",
            rowheight=28,
            font=(ui_font_family(), 11),
            borderwidth=0,
        )
        style.configure(
            "Argus.Treeview.Heading",
            background="#1e2329",
            foreground="#f0b90b",
            font=(ui_font_family(), 11, "bold"),
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Argus.Treeview",
            background=[("selected", "#f0b90b")],
            foreground=[("selected", "#181a20")],
        )
        style.map(
            "Argus.Treeview.Heading",
            background=[("active", "#2b3139")],
        )

    def _build_treeview(self, parent) -> ttk.Treeview:
        col_ids = [c[0] for c in COLUMNS]
        tree = ttk.Treeview(
            parent,
            columns=col_ids,
            show="headings",
            style="Argus.Treeview",
            selectmode="browse",
        )
        tree.grid(row=0, column=0, sticky="nsew")

        for col_id, header, width, anchor, stretch in COLUMNS:
            tree.heading(
                col_id,
                text=header,
                command=lambda c=col_id: self._sort_by(c),
            )
            tree.column(
                col_id,
                width=width,
                minwidth=40,
                anchor=anchor,
                stretch=stretch,
            )

        # Tag colori per segnale
        tree.tag_configure("buy",  background="#0d2e1a", foreground="#00e676")
        tree.tag_configure("sell", background="#2e0d0d", foreground="#ff5252")
        tree.tag_configure("hold", background="#1a1e2e", foreground="#b0b8d0")
        tree.tag_configure("na",   background="#111827", foreground="#555577")
        tree.tag_configure("buy_alt",  background="#0a2616", foreground="#00e676")
        tree.tag_configure("sell_alt", background="#280b0b", foreground="#ff5252")
        tree.tag_configure("hold_alt", background="#161a28", foreground="#b0b8d0")

        return tree

    # -------------------------------------------------------------------------
    # Data Population
    # -------------------------------------------------------------------------

    def populate(self, results: list[dict]):
        """Loads the list of results into the table while keeping the history."""
        # Add new results at the top
        self._all_data = results + self._all_data

        # Keep a reasonable history (e.g. 2500 rows, corresponding to 50 runs of 50 coins)
        if len(self._all_data) > 2500:
            self._all_data = self._all_data[:2500]

        self._apply_filter_and_sort()

        # Update last analysis label
        run_date = "None"
        if results:
            raw_date = results[0].get("run_date")
            if raw_date:
                try:
                    dt = pd.to_datetime(raw_date)
                    run_date = dt.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    run_date = str(raw_date)
        self._last_analysis_label.configure(text=f"Last Analysis: {run_date}")

    def _apply_filter_and_sort(self):
        """Filters and sorts the data, then repopulates the Treeview."""
        data = self._all_data.copy()

        # Search filter for name or symbol
        query = getattr(self, "_search_var", None)
        if query:
            q = query.get().strip().lower()
            if q:
                data = [
                    r for r in data
                    if q in r.get("symbol", "").lower() or q in r.get("name", "").lower()
                ]

        # Sorting
        reverse = not self._sort_asc
        try:
            if self._sort_col in ("last_price", "target_price_1d", "change_pct_1d", "rank", "confidence"):
                data = sorted(
                    data,
                    key=lambda r: (r.get(self._sort_col) is None,
                                   r.get(self._sort_col) or 0),
                    reverse=reverse,
                )
            elif self._sort_col == "run_date":
                data = sorted(
                    data,
                    key=lambda r: r.get("run_date") or "",
                    reverse=reverse,
                )
            else:
                data = sorted(
                    data,
                    key=lambda r: (r.get(self._sort_col) or "").lower(),
                    reverse=reverse,
                )
        except Exception:
            pass

        # Empty tree and repopulate
        for item in self._tree.get_children():
            self._tree.delete(item)

        for i, row in enumerate(data):
            try:
                pct = float(row.get("change_pct_1d") or 0)
            except (TypeError, ValueError):
                pct = 0.0
            if pct > 0: signal = "BUY"
            elif pct < 0: signal = "SELL"
            else: signal = "HOLD"

            tag_base = SIGNAL_COLORS.get(signal, SIGNAL_COLORS["N/A"])["tag"]
            tag = tag_base if i % 2 == 0 else f"{tag_base}_alt"
            # If the alt tag does not exist, use the base one
            if tag not in ("buy_alt", "sell_alt", "hold_alt"):
                tag = tag_base

            expiry_raw = row.get("expiry_date", "")
            if expiry_raw:
                try:
                    dt = pd.to_datetime(expiry_raw)
                    expiry_display = dt.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    expiry_display = expiry_raw
            else:
                expiry_display = ""

            # Confidence can arrive as a float, a CSV-loaded string or a sentinel
            # such as "N/A"/"DISABLED" — never let formatting raise.
            conf_val = row.get("confidence")
            try:
                conf_display = "N/A" if conf_val is None else f"{int(float(conf_val))}%"
            except (TypeError, ValueError):
                conf_display = str(conf_val)

            # Format change percentage without confidence
            try:
                pct_val = row.get("change_pct_1d")
                pct_val = None if pct_val is None else float(pct_val)
            except (TypeError, ValueError):
                pct_val = None
            if pct_val is not None:
                sign = "+" if pct_val >= 0 else ""
                pct_display = f"{sign}{pct_val:.2f}%"
            else:
                pct_display = "N/A"

            values = (
                row.get("name", ""),
                row.get("symbol", ""),
                conf_display,
                format_price(row.get("last_price")),
                format_price(row.get("target_price_1d")),
                pct_display,
                expiry_display,
            )
            self._tree.insert("", "end", values=values, tags=(tag,))

    def clear(self):
        """Clears the table."""
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._all_data = []
        self._last_analysis_label.configure(text="Last Analysis: None")

    # -------------------------------------------------------------------------
    # Sorting & Filtering
    # -------------------------------------------------------------------------

    def _sort_by(self, col_id: str):
        if self._sort_col == col_id:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col_id
            self._sort_asc = True
        self._apply_filter_and_sort()

        # Update header with arrow indicator
        for col_id2, header, *_ in COLUMNS:
            arrow = ""
            if col_id2 == self._sort_col:
                arrow = " ▲" if self._sort_asc else " ▼"
            label = header
            # Retrieve original header
            for c in COLUMNS:
                if c[0] == col_id2:
                    label = c[1]
                    break
            self._tree.heading(col_id2, text=f"{label}{arrow}")

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    def _export_excel(self):
        from datetime import datetime
        from tkinter import filedialog

        if not self._all_data:
            return

        default_name = f"argus_forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path = filedialog.asksaveasfilename(
            title="Export results",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return

        try:
            df = pd.DataFrame(self._all_data)
            df.to_excel(path, index=False)
            from tkinter import messagebox
            messagebox.showinfo("Export completed", f"File saved:\n{path}")
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Export error", str(e))


# =============================================================================
# VERIFICATION TABLE (BACKTESTING)
# =============================================================================
