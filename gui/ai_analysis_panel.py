"""
ai_analysis_panel.py — Argus
GUI panel for advanced multi-agent AI analysis.

Struttura (embedded direttamente nel corpo principale dell'app):
  AIAnalysisPanel (CTkFrame)
    ├── Sub-header interno (stato + pulsanti run/stop AI)
    ├── Tab "🎯  Selection"           — list of assets to analyze (crypto, stocks, etc.)
    ├── Tab "📊  Results"          — multi-agent results table
    └── Tab "⚙️  AI Settings"    — provider form, model, API keys
"""

import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import customtkinter as ctk

from core.ai_analyst import AIAnalyst, SUGGESTED_MODELS, PROVIDER_URLS
from core.ai_analysis_store import (
    save_ai_session, load_all_sessions, load_session,
    export_session_csv, export_session_excel, export_session_pdf,
    delete_analysis
)
from core.portfolio_manager import PortfolioManager
from core.data_manager import load_settings, save_settings
from core.analyzer import format_price, format_change_pct, compute_expiry_date
from datetime import datetime, timedelta
from gui.utils import apply_binance_tab_style


# ─────────────────────────────────────────────────────────────
# Costanti colori (allineate al tema Argus)
# ─────────────────────────────────────────────────────────────

BG_DARK       = ("#181a20", "#181a20")
BG_PANEL      = ("#1e2329", "#1e2329")
BG_CARD       = ("#1e2329", "#1e2329")
BG_INPUT      = ("#2b3139", "#2b3139")
COLOR_ACCENT  = ("#f0b90b", "#f0b90b")
COLOR_HOVER   = ("#d39e00", "#d39e00")
COLOR_TEXT    = ("#eaecef", "#eaecef")
COLOR_MUTED   = ("#848e9c", "#848e9c")
COLOR_SEP     = ("#474d57", "#474d57")

SIGNAL_COLORS_BG = {
    "BUY":  "#0d2e1a", "SELL": "#2e0d0d",
    "HOLD": "#2b3139", "N/A": "#1e2329",
}
SIGNAL_COLORS_FG = {
    "BUY":  "#00e676", "SELL": "#ff5252",
    "HOLD": "#eaecef", "N/A": "#555577",
}
CONF_COLORS_FG = {
    "alta": "#00e676", "media": "#ffd54f", "bassa": "#ff5252", "N/A": "#555577",
}


# ─────────────────────────────────────────────────────────────
# Helper: formattazione
# ─────────────────────────────────────────────────────────────

def _fmt_signal(s: str) -> str:
    return {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "HOLD": "🟡 HOLD"}.get(s, f"⚪ {s}")

def _fmt_conf(c) -> str:
    if isinstance(c, (int, float)):
        return f"{c}%"
    return {"alta": "⬆ High", "media": "➡ Medium", "bassa": "⬇ Low"}.get(str(c).lower(), str(c))

def _fmt_price(p) -> str:
    if p is None: return "N/A"
    try:
        p = float(p)
        if p >= 1000: return f"${p:,.2f}"
        elif p >= 1:  return f"${p:.4f}"
        else:          return f"${p:.6f}"
    except Exception:
        return "N/A"

def _fmt_pct(p) -> str:
    if p is None: return "N/A"
    try:
        p = float(p)
        return f"{'+' if p >= 0 else ''}{p:.2f}%"
    except Exception:
        return "N/A"

def _fmt_pct_with_conf(p, conf) -> str:
    pct_str = _fmt_pct(p)
    if pct_str == "N/A":
        return "N/A"
    if conf is not None and conf != "N/A":
        try:
            return f"{pct_str} ({int(float(conf))}%)"
        except:
            pass
    return pct_str


# ─────────────────────────────────────────────────────────────
# Stile Treeview condiviso
# ─────────────────────────────────────────────────────────────

def _setup_treeview_style(style_name: str = "Argus.Treeview"):
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(
        style_name,
        background="#181a20",
        foreground="#eaecef",
        fieldbackground="#181a20",
        rowheight=30,
        font=("Segoe UI", 10),
        borderwidth=0,
    )
    style.configure(
        f"{style_name}.Heading",
        background="#1e2329",
        foreground="#f0b90b",
        font=("Segoe UI", 10, "bold"),
        borderwidth=0,
        relief="flat",
    )
    style.map(style_name,
        background=[("selected", "#f0b90b")],
        foreground=[("selected", "#181a20")],
    )
    style.map(f"{style_name}.Heading",
        background=[("active", "#2b3139")],
    )


# ─────────────────────────────────────────────────────────────
# AIAnalysisWindow — Finestra Toplevel
# ─────────────────────────────────────────────────────────────

class AIAnalysisWindow(ctk.CTkToplevel):
    """Modal window for advanced AI analysis."""

    def __init__(self, parent, timefm_results: list[dict], app_settings: dict):
        super().__init__(parent)
        self.title("🤖 Argus — Advanced Multi-Agent AI Analysis")
        self.geometry("1300x850")
        self.minsize(1100, 700)
        self.configure(fg_color=BG_DARK)

        # Porta in primo piano
        self.transient(parent)
        self.lift()
        self.after(100, self.focus_force)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._panel = AIAnalysisPanel(
            self,
            timefm_results=timefm_results,
            app_settings=app_settings,
        )
        self._panel.grid(row=0, column=0, sticky="nsew")

    def update_results(self, timefm_results: list[dict]):
        """Updates TimesFM results in the panel."""
        self._panel.update_timefm_results(timefm_results)


# ─────────────────────────────────────────────────────────────
# AIAnalysisPanel — Frame principale
# ─────────────────────────────────────────────────────────────

class AIAnalysisPanel(ctk.CTkFrame):
    """Main panel with tabs for advanced AI analysis."""

    def __init__(self, parent, timefm_results: list[dict], app_settings: dict, **kwargs):
        super().__init__(parent, fg_color=BG_PANEL, border_color=COLOR_SEP, border_width=1, corner_radius=12, **kwargs)
        self._timefm_results = timefm_results
        self._app_settings   = app_settings
        self._ai_results: list[dict] = []
        self._current_session_id: str = ""
        self._running = False
        self._stop_requested = False
        self._msg_queue: queue.Queue = queue.Queue()
        self._sessions_cache: list[dict] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        _setup_treeview_style()
        self._build_subheader()
        self._build_tabs()
        self._poll_queue()
        self._load_last_ai_session()

    # ─────────────────────────────────────────────────────────
    # Sub-header AI interno: stato + pulsanti Run/Stop
    # ─────────────────────────────────────────────────────────

    def _build_subheader(self):
        """Barra interna del pannello AI con titolo, status e pulsante run."""
        bar = ctk.CTkFrame(self, fg_color="transparent", height=48)
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        bar.grid_columnconfigure(1, weight=1)

        # Titolo
        ctk.CTkLabel(
            bar, text="Advanced Analysis",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color=COLOR_ACCENT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        # Status label
        self._status_lbl = ctk.CTkLabel(
            bar, text="Select assets and run the analysis.",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=COLOR_MUTED, anchor="w",
        )
        self._status_lbl.grid(row=0, column=1, padx=(10, 8), sticky="ew")

        # Pulsante run
        self._btn_run = ctk.CTkButton(
            bar, text="▶  Run Advanced Analysis",
            command=self._start_analysis,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_HOVER,
            text_color="#181a20",
            height=34, width=210, corner_radius=8,
        )
        self._btn_run.grid(row=0, column=2, sticky="e")

        # Separatore orizzontale
        ctk.CTkFrame(self, height=1, fg_color=COLOR_SEP).grid(
            row=0, column=0, sticky="ew", padx=16, pady=(58, 0)
        )
        
        # Progress bar (inserita in riga 1 della topbar interna, per non disturbare la griglia)
        self._progress = ctk.CTkProgressBar(
            bar, height=3, fg_color=("#1a1e2e", "#1a1e2e"),
            progress_color=COLOR_ACCENT, corner_radius=0,
        )
        self._progress.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._progress.set(0)

    # ─────────────────────────────────────────────────────────
    # Tab view
    # ─────────────────────────────────────────────────────────

    def _build_tabs(self):
        self._tabs = ctk.CTkTabview(
            self,
            fg_color=BG_PANEL,
            segmented_button_fg_color=("#2b3139", "#2b3139"),
            segmented_button_selected_color=COLOR_ACCENT,
            segmented_button_selected_hover_color=COLOR_HOVER,
            segmented_button_unselected_color=BG_PANEL,
            segmented_button_unselected_hover_color=("#343a40", "#343a40"),
            text_color="white",
        )
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        for name in ["📊  Results", "⚙️  Settings"]:
            self._tabs.add(name)
            self._tabs.tab(name).grid_columnconfigure(0, weight=1)
            self._tabs.tab(name).grid_rowconfigure(0, weight=1)

        apply_binance_tab_style(self._tabs._segmented_button)

        self._build_results_tab()
        self._build_settings_tab()

    # ─────────────────────────────────────────────────────────
    # TAB 1 — Selezione Crypto
    # ─────────────────────────────────────────────────────────

    def _build_selection_tab(self):
        tab = self._tabs.tab("🎯  Selection")
        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # Toolbar selezione
        # Toolbar selezione
        toolbar = ctk.CTkFrame(container, fg_color=BG_CARD, height=48, corner_radius=8)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            toolbar, text="Select assets to analyze with AI:",
            font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_MUTED,
        ).grid(row=0, column=0, padx=16, pady=12, sticky="w")

        ctk.CTkButton(
            toolbar, text="☑ All", command=self._select_all,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=BG_INPUT, hover_color=("#343a40", "#343a40"),
            border_color=COLOR_ACCENT, border_width=1,
            height=30, width=90, corner_radius=6,
        ).grid(row=0, column=1, padx=6, pady=8)

        ctk.CTkButton(
            toolbar, text="☐ None", command=self._deselect_all,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=BG_INPUT, hover_color=("#343a40", "#343a40"),
            border_color=COLOR_SEP, border_width=1,
            height=30, width=100, corner_radius=6,
        ).grid(row=0, column=2, padx=3, pady=8, sticky="w")

        self._search_var = ctk.StringVar(value="")
        self._search_var.trace_add("write", self._on_search_change)
        
        self._search_entry = ctk.CTkEntry(
            toolbar, textvariable=self._search_var,
            placeholder_text="🔍 Search asset...",
            width=150, height=30,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=BG_INPUT, border_color=COLOR_SEP, border_width=1,
            corner_radius=6
        )
        self._search_entry.grid(row=0, column=3, padx=16, pady=8, sticky="e")

        # Treeview con checkbox
        tree_frame = tk.Frame(container, bg="#0d0d1a")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self._sel_vars: list[tk.BooleanVar] = []
        self._sel_tree = ttk.Treeview(
            tree_frame,
            columns=("sel", "rank", "name", "symbol", "last_price", 
                     "target_price_1d", "change_pct_1d", 
                     "expiry_date"),
            show="headings",
            style="Argus.Treeview",
            selectmode="browse",
        )
        self._sel_tree.grid(row=0, column=0, sticky="nsew")

        headers = [
            ("sel",             "✓",              40, "center", False),
            ("rank",            "#",              45, "center", False),
            ("name",            "Name",          150, "w",      True),
            ("symbol",          "Symbol",        75, "center", False),
            ("last_price",      "Price",        110, "e",      False),
            ("target_price_1d", "Target 2h",    110, "e",      False),
            ("change_pct_1d",   "Var% 2h",       85, "e",      False),
            ("expiry_date",     "Expiry",      130, "center", False),
        ]
        for col_id, header, width, anchor, stretch in headers:
            self._sel_tree.heading(col_id, text=header)
            self._sel_tree.column(col_id, width=width, anchor=anchor, stretch=stretch, minwidth=30)

        self._sel_tree.tag_configure("buy",  background="#0d2e1a", foreground="#00e676")
        self._sel_tree.tag_configure("sell", background="#2e0d0d", foreground="#ff5252")
        self._sel_tree.tag_configure("hold", background="#1a1e2e", foreground="#b0b8d0")
        self._sel_tree.tag_configure("na",   background="#111827", foreground="#555577")
        self._sel_tree.tag_configure("sel",  background="#1a2a4a", foreground="#c0d8ff")
        self._sel_tree.bind("<Button-1>", self._on_sel_tree_click)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._sel_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._sel_tree.configure(yscrollcommand=vsb.set)

        # Mappa iid → bool selezionato
        self._selected_iids: set[str] = set()
        self._populate_selection_tree()

    def _on_search_change(self, *args):
        self._populate_selection_tree(keep_selections=True)

    def _populate_selection_tree(self, keep_selections=False):
        """Popola il tree di selezione con i risultati TimesFM."""
        for iid in self._sel_tree.get_children():
            self._sel_tree.delete(iid)
            
        if not keep_selections:
            self._selected_iids.clear()

        query = getattr(self, "_search_var", ctk.StringVar()).get().strip().lower()

        # Ordina per change_pct decrescente (i più promettenti prima)
        sorted_results = sorted(
            self._timefm_results,
            key=lambda r: (r.get("change_pct") is None, -(r.get("change_pct") or 0))
        )

        for i, r in enumerate(sorted_results):
            iid = str(i)
            name = str(r.get("name", "")).lower()
            symbol = str(r.get("symbol", "")).lower()
            
            if query and query not in name and query not in symbol:
                continue

            sig = r.get("signal_1d", "N/A")
            tag = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}.get(sig, "na")
            
            if not keep_selections:
                is_selected = False
            
            is_selected = iid in self._selected_iids
            check_char = "☑" if is_selected else "☐"

            expiry_raw = r.get("expiry_date", "")
            if expiry_raw:
                try:
                    dt = pd.to_datetime(expiry_raw)
                    expiry_display = dt.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    expiry_display = expiry_raw
            else:
                expiry_display = ""

            self._sel_tree.insert("", "end", iid=iid, values=(
                check_char,
                r.get("rank", ""),
                r.get("name", ""),
                r.get("symbol", ""),
                _fmt_price(r.get("last_price")),
                _fmt_price(r.get("target_price_1d")),
                _fmt_pct(r.get("change_pct_1d")),
                expiry_display,
            ), tags=(tag,))

    def _on_sel_tree_click(self, event):
        """Toggle selezione al click sulla riga."""
        region = self._sel_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        iid = self._sel_tree.identify_row(event.y)
        if not iid:
            return
        tags = list(self._sel_tree.item(iid, "tags"))
        if iid in self._selected_iids:
            self._selected_iids.discard(iid)
            self._sel_tree.item(iid, values=(
                "☐", *self._sel_tree.item(iid, "values")[1:]
            ), tags=tuple(tags))
        else:
            self._selected_iids.add(iid)
            self._sel_tree.item(iid, values=(
                "☑", *self._sel_tree.item(iid, "values")[1:]
            ), tags=tuple(tags))

    def _select_all(self):
        for iid in self._sel_tree.get_children():
            self._selected_iids.add(iid)
            vals = self._sel_tree.item(iid, "values")
            tags = self._sel_tree.item(iid, "tags")
            self._sel_tree.item(iid, values=("☑", *vals[1:]), tags=tags)

    def _deselect_all(self):
        for iid in self._sel_tree.get_children():
            self._selected_iids.discard(iid)
            vals = self._sel_tree.item(iid, "values")
            tags = self._sel_tree.item(iid, "tags")
            self._sel_tree.item(iid, values=("☐", *vals[1:]), tags=tags)

    def _get_selected_crypto(self) -> list[dict]:
        """Ritorna la lista di crypto selezionate nell'ordine del tree (solo BTC in questo caso)."""
        if not self._timefm_results:
            return []
        for r in self._timefm_results:
            if r.get("symbol", "").upper() in ["BTC", "BTC-USD"]:
                return [r]
        return [self._timefm_results[0]]

    def update_timefm_results(self, results: list[dict]):
        """Aggiorna i risultati TimesFM."""
        self._timefm_results = results
        if results:
            try:
                self._tabs.set("📊  Results")
            except:
                pass
            self._status_lbl.configure(text="Select assets and run the analysis.", text_color=COLOR_MUTED)
            self._btn_run.configure(state="normal")
        else:
            self._status_lbl.configure(
                text="⚠️ Data Unavailable: Run a time-series analysis first to obtain data for AI analysis.",
                text_color="#ff5252"
            )
            self._btn_run.configure(state="disabled")

    # ─────────────────────────────────────────────────────────
    # TAB 2 — Risultati
    # ─────────────────────────────────────────────────────────

    def _build_results_tab(self):
        tab = self._tabs.tab("📊  Results")
        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # Toolbar risultati
        toolbar = ctk.CTkFrame(container, fg_color=BG_CARD, height=48, corner_radius=8)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(
            toolbar, text="AI Analysis History:",
            font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_MUTED,
        ).grid(row=0, column=0, padx=16, pady=12, sticky="w")

        ctk.CTkButton(
            toolbar, text="☑ All", command=self._results_select_all,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=BG_INPUT, hover_color=("#343a40", "#343a40"),
            border_color=COLOR_ACCENT, border_width=1,
            height=30, width=90, corner_radius=6,
        ).grid(row=0, column=1, padx=6, pady=8)

        ctk.CTkButton(
            toolbar, text="☐ None", command=self._results_deselect_all,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=BG_INPUT, hover_color=("#343a40", "#343a40"),
            border_color=COLOR_SEP, border_width=1,
            height=30, width=100, corner_radius=6,
        ).grid(row=0, column=2, padx=3, pady=8, sticky="w")

        ctk.CTkButton(
            toolbar, text="🗑 Delete Analysis",
            command=self._delete_selected_analyses,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=BG_INPUT, hover_color=("#343a40", "#343a40"),
            border_color=COLOR_ACCENT, border_width=1,
            height=30, width=120, corner_radius=6,
        ).grid(row=0, column=3, padx=12, pady=8, sticky="w")

        btn_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        btn_frame.grid(row=0, column=5, padx=8, pady=8, sticky="e")

        ctk.CTkButton(
            btn_frame, text="📊 Excel",
            command=lambda: self._export_current("excel"),
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=BG_INPUT, hover_color=("#343a40", "#343a40"),
            border_color=COLOR_ACCENT, border_width=1,
            height=30, width=80, corner_radius=6,
        ).pack(side="left", padx=3)

        # Treeview risultati principale
        tree_frame = tk.Frame(container, bg="#0d0d1a")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        RES_COLS = [
            ("sel",            "✓",              40, "center", False),
            ("name",           "Name",          150, "w",      True),
            ("symbol",         "Symbol",        70, "center", False),
            ("current_price",  "Price",        110, "e",      False),
            ("pm_1d",          "Var% 2h PM",    125, "center", False),
            ("timefm_sig_1d",  "Var% 2h TFM",   125, "center", False),
            ("pct_1d",         "Var% 2h AV",    125, "center", False),
            ("target_1d",      "Final Forecast",  100, "e",      False),
            ("leverage",       "Leverage",           55, "center", False),
            ("sl",             "SL (ROI%)",         160, "e",      False),
            ("tp",             "TP (ROI%)",         160, "e",      False),
            ("scadenza",       "Expiry",      130, "center", False),
            ("sizing",         "Sizing (%)",     75, "center", False),
        ]

        col_ids = [c[0] for c in RES_COLS]
        self._res_tree = ttk.Treeview(
            tree_frame, columns=col_ids,
            show="headings", style="Argus.Treeview",
            selectmode="browse",
        )
        self._res_tree.grid(row=0, column=0, sticky="nsew")

        for col_id, header, width, anchor, stretch in RES_COLS:
            self._res_tree.heading(col_id, text=header)
            self._res_tree.column(col_id, width=width, anchor=anchor, stretch=stretch, minwidth=40)

        # Tag colori segnale (con prefisso per evitare conflitti)
        for sig, bg, fg in [
            ("buy",  "#0d2e1a", "#00e676"), ("sell", "#2e0d0d", "#ff5252"),
            ("hold", "#1a1e2e", "#b0b8d0"), ("na",   "#111827", "#555577"),
            ("sel",  "#1a2a4a", "#c0d8ff"),
        ]:
            self._res_tree.tag_configure(f"res_{sig}", background=bg, foreground=fg)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._res_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._res_tree.configure(yscrollcommand=vsb.set)

        self._res_selected_iids: set[str] = set()
        self._res_tree.bind("<Button-1>", self._on_res_tree_click)

        # Bind doppio click per dettaglio agenti
        self._res_tree.bind("<Double-Button-1>", self._show_agent_detail)

        # Label istruzione
        ctk.CTkLabel(
            container, text="💡 Double click on a row to see the complete debate between agents",
            font=ctk.CTkFont("Segoe UI", 10), text_color=COLOR_MUTED,
        ).grid(row=2, column=0, pady=(4, 0), sticky="w", padx=8)

    def _populate_results_tree(self, results: list[dict] = None):
        """Popola la tabella dello storico caricando tutte le sessioni globali."""
        for iid in self._res_tree.get_children():
            self._res_tree.delete(iid)
            
        self._res_selected_iids.clear()
        self._ai_results = []
        
        all_sessions = load_all_sessions()
        if not all_sessions:
            self._res_tree.insert(
                "", "end",
                values=("", "No AI analysis data available. Run a time-series analysis first.", "", "", "", "", "", "", "", "", "", "", "")
            )
            return
        row_count = 0
        
        for session in all_sessions:
            if row_count >= 50:
                break
                
            sid = session.get("session_id", "")
            meta = session.get("meta", {})
            market_type = meta.get("market_type", "crypto")
            is_crypto = (market_type.lower() == "crypto")
            
            for r in session.get("results", []):
                if row_count >= 50:
                    break
                    
                r["_session_id"] = sid
                self._ai_results.append(r)
                
                try:
                    dt = datetime.fromisoformat(r.get("analyzed_at", ""))
                    expiry_dt_str = compute_expiry_date(validity_hours=4, from_date=dt)
                    expiry_dt = datetime.strptime(expiry_dt_str, "%Y-%m-%d %H:%M:%S")
                    scadenza = expiry_dt.strftime("%Y-%m-%d %H:%M")
                except:
                    scadenza = "N/A"
                    
                try:
                    tfm_pct = float(r.get("change_pct_1d") or 0.0)
                except (ValueError, TypeError):
                    tfm_pct = 0.0
                try:
                    pm_pct = float(r.get("btc_expected_move") or 0.0)
                except (ValueError, TypeError):
                    pm_pct = 0.0
                try:
                    ai_pct = float(r.get("ai_change_pct_1d") or tfm_pct)
                except (ValueError, TypeError):
                    ai_pct = tfm_pct
                
                w_tfm = float(self._app_settings.get("ensemble_w_tfm", 40.0)) / 100.0
                w_pm = float(self._app_settings.get("ensemble_w_pm", 35.0)) / 100.0
                w_ai = float(self._app_settings.get("ensemble_w_ai", 25.0)) / 100.0
                
                exp_ret = (tfm_pct * w_tfm) + (pm_pct * w_pm) + (ai_pct * w_ai)
                
                pos_count = sum(1 for p in [tfm_pct, pm_pct, ai_pct] if p > 0)
                neg_count = sum(1 for p in [tfm_pct, pm_pct, ai_pct] if p < 0)
                
                final_signal = "HOLD"
                if pos_count >= 2 and exp_ret > 0.30: final_signal = "BUY"
                elif neg_count >= 2 and exp_ret < -0.30: final_signal = "SELL"
                
                max_agree = max(pos_count, neg_count)
                size_mult = 1.0 if final_signal in ["BUY", "SELL"] else 0.0
                if final_signal in ["BUY", "SELL"] and max_agree == 2: size_mult *= 0.60
                
                sizing_str = f"{int(size_mult * 100)}%" if size_mult > 0 else "0%"
                
                tag = "res_buy" if exp_ret >= 0 else "res_sell"
                
                iid = f"{sid}_{r.get('symbol', '')}"
                
                # Calcola SL% e TP% rispetto al prezzo corrente
                curr_p = r.get("current_price") or r.get("last_price")
                sl_val = r.get("stop_loss")
                tp_val = r.get("take_profit")
                sl_pct_str = "N/A"
                tp_pct_str = "N/A"
                leverage = 1
                if curr_p and curr_p > 0:
                    sig = final_signal
                    leverage = int(self._app_settings.get("portfolio_manager", {}).get("maxLeverage", 1))
                    if leverage < 1: leverage = 1
                    
                    if sl_val is not None:
                        try:
                            sl_dist = abs(float(curr_p) - float(sl_val)) / float(curr_p)
                            if sl_dist > 0:
                                safe_lev = int(0.80 / sl_dist)
                                leverage = min(leverage, max(1, safe_lev))
                        except (ValueError, TypeError):
                            pass
                            
                    if sl_val is not None:
                        try:
                            if sig == "SELL": sl_change = (float(curr_p) - float(sl_val)) / float(curr_p)
                            else: sl_change = (float(sl_val) - float(curr_p)) / float(curr_p)
                            sl_roi = sl_change * leverage * 100
                            sl_pct_str = f"{float(sl_val):.4f} ({sl_roi:+.2f}%)"
                        except (ValueError, TypeError):
                            pass
                    if tp_val is not None:
                        try:
                            if sig == "SELL": tp_change = (float(curr_p) - float(tp_val)) / float(curr_p)
                            else: tp_change = (float(tp_val) - float(curr_p)) / float(curr_p)
                            tp_roi = tp_change * leverage * 100
                            tp_pct_str = f"{float(tp_val):.4f} ({tp_roi:+.2f}%)"
                        except (ValueError, TypeError):
                            pass
                
                pm_conf = r.get("btc_pred_confidence")
                tfm_conf = r.get("tfm_confidence")
                ai_conf = r.get("confidence")

                self._res_tree.insert("", "end", iid=iid, values=(
                    "☐",
                    r.get("name", ""),
                    r.get("symbol", ""),
                    _fmt_price(r.get("current_price")),
                    _fmt_pct_with_conf(pm_pct, pm_conf),
                    _fmt_pct_with_conf(tfm_pct, tfm_conf),
                    _fmt_pct_with_conf(ai_pct, ai_conf),
                    _fmt_pct_with_conf(exp_ret, ai_conf),
                    f"{leverage}x",
                    sl_pct_str,
                    tp_pct_str,
                    scadenza,
                    sizing_str,
                ), tags=(tag,))
                row_count += 1

    def _on_res_tree_click(self, event):
        """Toggle selezione al click sulla riga dei risultati."""
        region = self._res_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        iid = self._res_tree.identify_row(event.y)
        if not iid:
            return
        
        tags = list(self._res_tree.item(iid, "tags"))
        if iid in self._res_selected_iids:
            self._res_selected_iids.discard(iid)
            self._res_tree.item(iid, values=(
                "☐", *self._res_tree.item(iid, "values")[1:]
            ), tags=tuple(tags))
        else:
            self._res_selected_iids.add(iid)
            self._res_tree.item(iid, values=(
                "☑", *self._res_tree.item(iid, "values")[1:]
            ), tags=tuple(tags))

    def _results_select_all(self):
        for iid in self._res_tree.get_children():
            self._res_selected_iids.add(iid)
            tags = list(self._res_tree.item(iid, "tags"))
            vals = self._res_tree.item(iid, "values")
            self._res_tree.item(iid, values=("☑", *vals[1:]), tags=tuple(tags))

    def _results_deselect_all(self):
        for iid in self._res_tree.get_children():
            self._res_selected_iids.discard(iid)
            tags = list(self._res_tree.item(iid, "tags"))
            vals = self._res_tree.item(iid, "values")
            self._res_tree.item(iid, values=("☐", *vals[1:]), tags=tuple(tags))

    def _delete_selected_analyses(self):
        if not self._res_selected_iids:
            messagebox.showinfo("No selection", "Select at least one analysis to delete (click the checkbox).")
            return
            
        deleted = 0
        for iid in list(self._res_selected_iids):
            # L'iid è formatato come {session_id}_{symbol}
            parts = iid.split("_", 2)
            if len(parts) >= 3:
                # Il session id è composto da data_ora, symbol è l'ultimo
                sid = f"{parts[0]}_{parts[1]}_{parts[2].split('_')[0]}" # Ricostruiamo il session_id (es 20260605_135205_1crypto)
                # In realtà è più sicuro recuperarlo dal dizionario dei risultati
                res_match = next((r for r in self._ai_results if f"{r.get('_session_id', '')}_{r.get('symbol', '')}" == iid), None)
                if res_match:
                    sid = res_match.get('_session_id', '')
                    sym = res_match.get('symbol', '')
                    if delete_analysis(sid, sym):
                        deleted += 1

        self._status(f"🗑 {deleted} analyses deleted from history.")
        self._populate_results_tree() # Ricarica tutto

    def _show_agent_detail(self, event):
        """Mostra una finestra con il dibattito completo degli agenti."""
        iid = self._res_tree.identify_row(event.y)
        if not iid:
            return
        # Trova il risultato corrispondente (matchando l'iid composto)
        result = next((r for r in self._ai_results if f"{r.get('_session_id', '')}_{r.get('symbol', '')}" == iid), None)
        if not result:
            return
        AgentDebateWindow(self, result)

    # ─────────────────────────────────────────────────────────
    def _load_last_ai_session(self):
        """Carica l'ultima sessione AI salvata se presente."""
        try:
            sessions = load_all_sessions()
            if sessions:
                latest = sessions[0]
                self._ai_results = latest.get("results", [])
                self._current_session_id = latest.get("session_id", "")
                self._populate_results_tree(self._ai_results)
                self._status(f"📂 Latest AI analysis loaded: {self._current_session_id}")
            else:
                self._status("No previous AI log found. Run your first analysis.")
        except Exception as e:
            print(f"[AIAnalysisPanel] Errore caricamento ultima sessione: {e}")

    def _export_current(self, fmt: str):
        if not self._current_session_id:
            messagebox.showinfo("No session", "Run an analysis or load a session first.")
            return
        self._do_export(self._current_session_id, fmt)

    def _do_export(self, session_id: str, fmt: str):
        ext_map = {"csv": ".csv", "excel": ".xlsx", "pdf": ".pdf"}
        type_map = {"csv": [("CSV", "*.csv")], "excel": [("Excel", "*.xlsx")], "pdf": [("PDF", "*.pdf")]}
        ext = ext_map.get(fmt, ".csv")
        default = f"argus_ai_{session_id}{ext}"
        path = filedialog.asksaveasfilename(
            title="Export AI analysis",
            defaultextension=ext,
            filetypes=type_map.get(fmt, [("All", "*.*")]),
            initialfile=default,
        )
        if not path:
            return
        ok = False
        if fmt == "csv":
            ok = export_session_csv(session_id, path)
        elif fmt == "excel":
            ok = export_session_excel(session_id, path)
        elif fmt == "pdf":
            ok = export_session_pdf(session_id, path)
        if ok:
            messagebox.showinfo("Export completed", f"File saved:\n{path}")
        else:
            messagebox.showerror("Export error", f"Unable to export to {fmt.upper()} format.\nVerify dependencies (e.g., openpyxl, reportlab).")

    # ─────────────────────────────────────────────────────────
    # TAB 4 — Impostazioni AI
    # ─────────────────────────────────────────────────────────

    def _build_settings_tab(self):
        tab = self._tabs.tab("⚙️  Settings")
        scroll = ctk.CTkScrollableFrame(
            tab, fg_color=("#1e2329", "#181a20"), corner_radius=0,
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1, minsize=400)
        scroll.grid_columnconfigure(1, weight=1, minsize=400)

        def section_title(text, parent, row):
            ctk.CTkLabel(
                parent, text=text,
                font=ctk.CTkFont("Segoe UI", 11, "bold"),
                text_color=COLOR_ACCENT, anchor="w",
            ).grid(row=row, column=0, padx=16, pady=(16, 4), sticky="ew")

        def lbl(text, parent, row):
            ctk.CTkLabel(
                parent, text=text,
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=("#808080", "#a0a0a0"), anchor="w",
            ).grid(row=row, column=0, padx=16, pady=(8, 2), sticky="ew")

        def sep(parent, row):
            ctk.CTkFrame(parent, height=1, fg_color=("#303040", "#202030")).grid(
                row=row, column=0, padx=16, pady=4, sticky="ew"
            )

        # ── Frame Sinistra (Impostazioni) ───────────────────────────────────
        left_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(16, 20), pady=16)
        left_frame.grid_columnconfigure(0, weight=1)

        # ── Frame Destra (Informazioni) ────────────────────────────────────
        right_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(20, 16), pady=16)
        right_frame.grid_columnconfigure(0, weight=1)

        # --- Sezione Configurazione Modelli ---
        r = 0
        section_title("🤖  MULTI-AGENT PROVIDER AND MODELS", left_frame, row=r); r += 1
        sep(left_frame, row=r); r += 1

        # Provider LLM
        lbl("Provider LLM", left_frame, row=r); r += 1
        self._provider_var = ctk.StringVar(value="openrouter")
        self._provider_menu = ctk.CTkOptionMenu(
            left_frame,
            values=["openrouter", "claude", "openai", "ollama"],
            variable=self._provider_var,
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=BG_INPUT,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_HOVER,
            dropdown_fg_color=BG_INPUT,
            dropdown_hover_color=("#343a40", "#343a40"),
            text_color="white",
            dropdown_text_color="white",
            height=36,
        )
        self._provider_menu.grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        ctk.CTkLabel(left_frame, text="Select the provider for advanced multi-agent model analysis (OpenRouter, Claude, OpenAI, Ollama).", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1

        # Container dinamico per API Key e Ollama URL
        self._provider_config_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        self._provider_config_frame.grid(row=r, column=0, sticky="ew", padx=0, pady=0); r += 1
        self._provider_config_frame.grid_columnconfigure(0, weight=1)

        # API Key (OpenRouter)
        self._ai_apikey_label = ctk.CTkLabel(
            self._provider_config_frame, text="API Key Provider (OpenRouter)",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=("#808080", "#a0a0a0"), anchor="w",
        )
        self._ai_apikey_var = ctk.StringVar(value="")
        
        self._ai_apikey_frame = ctk.CTkFrame(self._provider_config_frame, fg_color="transparent")
        self._ai_apikey_frame.grid_columnconfigure(0, weight=1)

        self._ai_apikey_entry = ctk.CTkEntry(
            self._ai_apikey_frame, textvariable=self._ai_apikey_var,
            font=ctk.CTkFont("Segoe UI", 11),
            placeholder_text="sk-or-xxxxxxxxxxxxxxxxxxxx",
            show="*",
            fg_color=BG_INPUT, border_color=COLOR_ACCENT, border_width=1, height=36,
        )
        self._ai_apikey_entry.grid(row=0, column=0, sticky="ew")

        def toggle_ai_apikey():
            if self._ai_apikey_entry.cget("show") == "*":
                self._ai_apikey_entry.configure(show="")
                ai_apikey_btn.configure(text="🙈")
            else:
                self._ai_apikey_entry.configure(show="*")
                ai_apikey_btn.configure(text="👁")

        ai_apikey_btn = ctk.CTkButton(
            self._ai_apikey_frame, text="👁", width=36, height=36,
            fg_color=BG_INPUT, hover_color=COLOR_HOVER,
            border_color=COLOR_ACCENT, border_width=1, command=toggle_ai_apikey
        )
        ai_apikey_btn.grid(row=0, column=1, padx=(4, 0))

        # Ollama Host URL
        self._ollama_host_label = ctk.CTkLabel(
            self._provider_config_frame, text="Ollama Host URL",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=("#808080", "#a0a0a0"), anchor="w",
        )
        self._ollama_host_var = ctk.StringVar(value="http://localhost:11434/v1")
        self._ollama_host_entry = ctk.CTkEntry(
            self._provider_config_frame, textvariable=self._ollama_host_var,
            font=ctk.CTkFont("Segoe UI", 11),
            placeholder_text="e.g. http://localhost:11434/v1",
            fg_color=BG_INPUT, border_color=COLOR_ACCENT, border_width=1, height=36,
        )

        # Modello Quick
        lbl("Quick Thinking Model (Prelim. Analysts)", left_frame, row=r); r += 1
        self._model_quick_var = ctk.StringVar(value="anthropic/claude-3-haiku")
        ctk.CTkEntry(
            left_frame, textvariable=self._model_quick_var,
            font=ctk.CTkFont("Segoe UI", 11),
            placeholder_text="e.g. anthropic/claude-3-haiku or mistral",
            fg_color=BG_INPUT, border_color=COLOR_ACCENT, border_width=1, height=36,
        ).grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        ctk.CTkLabel(left_frame, text="Lightweight and cost-effective model used for preliminary sentiment and news analysis.", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1

        # Modello Deep
        lbl("Deep Thinking Model (Researchers & Decision Maker)", left_frame, row=r); r += 1
        self._model_deep_var = ctk.StringVar(value="anthropic/claude-3-5-sonnet")
        ctk.CTkEntry(
            left_frame, textvariable=self._model_deep_var,
            font=ctk.CTkFont("Segoe UI", 11),
            placeholder_text="e.g. anthropic/claude-3-5-sonnet or llama3.1",
            fg_color=BG_INPUT, border_color=COLOR_ACCENT, border_width=1, height=36,
        ).grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        ctk.CTkLabel(left_frame, text="Advanced 'reasoning' model that handles critical debate and formulates final consensus.", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1

        # Modello Fallback
        lbl("Fallback Model (on error)", left_frame, row=r); r += 1
        self._model_fallback_var = ctk.StringVar(value="google/gemini-2.5-flash")
        ctk.CTkEntry(
            left_frame, textvariable=self._model_fallback_var,
            font=ctk.CTkFont("Segoe UI", 11),
            placeholder_text="e.g. google/gemini-2.5-flash",
            fg_color=BG_INPUT, border_color=COLOR_ACCENT, border_width=1, height=36,
        ).grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        ctk.CTkLabel(left_frame, text="Backup model used if the primary model encounters errors or rate limits.", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1

        # Research Rounds
        lbl("Search Depth (Debate rounds)", left_frame, row=r); r += 1
        self._research_rounds_var = ctk.StringVar(value="1")
        self._rounds_seg = ctk.CTkSegmentedButton(
            left_frame, values=["1", "2", "3", "5"],
            variable=self._research_rounds_var,
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=BG_INPUT, selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_HOVER,
            unselected_color=BG_INPUT,
            unselected_hover_color=("#343a40", "#343a40"),
            text_color="white",
        )
        self._rounds_seg.grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        apply_binance_tab_style(self._rounds_seg)
        ctk.CTkLabel(left_frame, text="Number of debate steps between Bull and Bear. More rounds increase accuracy but consume more tokens.", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1

        # --- Pesi Ensemble Quantitativo ---
        section_title("⚖️  QUANTITATIVE ENSEMBLE WEIGHTS", left_frame, row=r); r += 1
        sep(left_frame, row=r); r += 1

        # Peso PM
        lbl("Pattern Matching Weight (%)", left_frame, row=r); r += 1
        self._w_pm_var = ctk.DoubleVar(value=35.0)
        self._w_pm_slider = ctk.CTkSlider(
            left_frame, from_=0.0, to=100.0, number_of_steps=20, variable=self._w_pm_var,
            button_color=COLOR_ACCENT, button_hover_color=COLOR_HOVER, progress_color=COLOR_ACCENT,
            command=lambda v: self._w_pm_label.configure(text=f"{int(v)} %")
        )
        self._w_pm_slider.grid(row=r, column=0, padx=16, pady=(4, 0), sticky="ew"); r += 1
        self._w_pm_label = ctk.CTkLabel(left_frame, text="35 %", font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_MUTED)
        self._w_pm_label.grid(row=r, column=0, padx=16, pady=(2, 2), sticky="e"); r += 1
        ctk.CTkLabel(left_frame, text="Percentage influence of the KNN-DTW module in the final signal calculation.", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 8), sticky="ew"); r += 1

        # Peso TFM
        lbl("Time-Series Analysis Weight (%)", left_frame, row=r); r += 1
        self._w_tfm_var = ctk.DoubleVar(value=40.0)
        self._w_tfm_slider = ctk.CTkSlider(
            left_frame, from_=0.0, to=100.0, number_of_steps=20, variable=self._w_tfm_var,
            button_color=COLOR_ACCENT, button_hover_color=COLOR_HOVER, progress_color=COLOR_ACCENT,
            command=lambda v: self._w_tfm_label.configure(text=f"{int(v)} %")
        )
        self._w_tfm_slider.grid(row=r, column=0, padx=16, pady=(4, 0), sticky="ew"); r += 1
        self._w_tfm_label = ctk.CTkLabel(left_frame, text="40 %", font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_MUTED)
        self._w_tfm_label.grid(row=r, column=0, padx=16, pady=(2, 2), sticky="e"); r += 1
        ctk.CTkLabel(left_frame, text="Percentage influence of TimesFM forecasts in the final signal calculation.", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 8), sticky="ew"); r += 1

        # Peso AI
        lbl("Advanced Analysis Weight (%)", left_frame, row=r); r += 1
        self._w_ai_var = ctk.DoubleVar(value=25.0)
        self._w_ai_slider = ctk.CTkSlider(
            left_frame, from_=0.0, to=100.0, number_of_steps=20, variable=self._w_ai_var,
            button_color=COLOR_ACCENT, button_hover_color=COLOR_HOVER, progress_color=COLOR_ACCENT,
            command=lambda v: self._w_ai_label.configure(text=f"{int(v)} %")
        )
        self._w_ai_slider.grid(row=r, column=0, padx=16, pady=(4, 0), sticky="ew"); r += 1
        self._w_ai_label = ctk.CTkLabel(left_frame, text="25 %", font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_MUTED)
        self._w_ai_label.grid(row=r, column=0, padx=16, pady=(2, 2), sticky="e"); r += 1
        ctk.CTkLabel(left_frame, text="Percentage influence of the AI agent committee in the final signal calculation.", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1

        sep(left_frame, row=r); r += 1

        # --- Sezione Chiavi Esterne ---
        section_title("🔑  API KEYS AND EXTERNAL SERVICES", left_frame, row=r); r += 1
        sep(left_frame, row=r); r += 1

        # Finnhub
        lbl("Finnhub API Key (for news)", left_frame, row=r); r += 1
        self._finnhub_var = ctk.StringVar(value="")
        
        finnhub_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        finnhub_frame.grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        finnhub_frame.grid_columnconfigure(0, weight=1)

        finnhub_entry = ctk.CTkEntry(
            finnhub_frame, textvariable=self._finnhub_var,
            font=ctk.CTkFont("Segoe UI", 11),
            placeholder_text="xxxxxxxxxxxxxxxxxxxx",
            show="*",
            fg_color=BG_INPUT, border_color=COLOR_ACCENT, border_width=1, height=36,
        )
        finnhub_entry.grid(row=0, column=0, sticky="ew")

        def toggle_finnhub():
            if finnhub_entry.cget("show") == "*":
                finnhub_entry.configure(show="")
                finnhub_btn.configure(text="🙈")
            else:
                finnhub_entry.configure(show="*")
                finnhub_btn.configure(text="👁")

        finnhub_btn = ctk.CTkButton(
            finnhub_frame, text="👁", width=36, height=36,
            fg_color=BG_INPUT, hover_color=COLOR_HOVER,
            border_color=COLOR_ACCENT, border_width=1, command=toggle_finnhub
        )
        finnhub_btn.grid(row=0, column=1, padx=(4, 0))
        ctk.CTkLabel(left_frame, text="Finnhub API Key (optional) to allow the sentiment agent to download real macroeconomic news.", font=ctk.CTkFont("Segoe UI", 10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1


        # CoinGecko API Key indipendente
        lbl("CoinGecko API Key (leave empty for none)", left_frame, row=r); r += 1
        self._cg_ai_key_var = ctk.StringVar(value="")
        
        cg_ai_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        cg_ai_frame.grid(row=r, column=0, padx=16, pady=(4, 12), sticky="ew"); r += 1
        cg_ai_frame.grid_columnconfigure(0, weight=1)

        cg_ai_entry = ctk.CTkEntry(
            cg_ai_frame, textvariable=self._cg_ai_key_var,
            font=ctk.CTkFont("Segoe UI", 11),
            placeholder_text="CG-xxxxxxxxxxxxxxxxxxxx",
            show="*",
            fg_color=BG_INPUT, border_color=COLOR_ACCENT, border_width=1, height=36,
        )
        cg_ai_entry.grid(row=0, column=0, sticky="ew")

        def toggle_cg_ai():
            if cg_ai_entry.cget("show") == "*":
                cg_ai_entry.configure(show="")
                cg_ai_btn.configure(text="🙈")
            else:
                cg_ai_entry.configure(show="*")
                cg_ai_btn.configure(text="👁")

        cg_ai_btn = ctk.CTkButton(
            cg_ai_frame, text="👁", width=36, height=36,
            fg_color=BG_INPUT, hover_color=COLOR_HOVER,
            border_color=COLOR_ACCENT, border_width=1, command=toggle_cg_ai
        )
        cg_ai_btn.grid(row=0, column=1, padx=(4, 0))

        sep(left_frame, row=r); r += 1

        # Pulsante Salva
        self._btn_save_ai = ctk.CTkButton(
            left_frame, text="💾 Save Settings",
            command=self._save_ai_settings,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_HOVER,
            text_color="#181a20",
            height=38, corner_radius=8,
        )
        self._btn_save_ai.grid(row=r, column=0, padx=16, pady=(12, 6), sticky="ew")

        # ── Frame Destra (Informazioni) ────────────────────────────────────
        # Info Box Card (Premium design with nice border and background)
        info_card = ctk.CTkFrame(
            right_frame,
            fg_color=("#2b3139", "#1e2329"),
            border_color=COLOR_SEP,
            border_width=1,
            corner_radius=12,
        )
        info_card.grid(row=0, column=0, sticky="nsew", padx=8, pady=16)
        info_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            info_card,
            text="💡 MULTI-AGENT ARCHITECTURE AND LOGIC",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=COLOR_ACCENT,
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        info_text = (
            "Advanced AI Analysis simulates a structured investment committee, orchestrating a team of intelligent agents and integrating quantitative metrics to produce high-reliability signals.\n\n"
            "🕵️ MULTI-AGENT ARCHITECTURE AND AGENTS:\n"
            "• MARKET ANALYST: Analyzes technical price data and incorporates estimates generated by Google TimesFM.\n"
            "• NEWS & SENTIMENT ANALYST: Filters news and analyzes sentiment on markets/socials (via Finnhub and CoinGecko).\n"
            "• FUNDAMENTALS ANALYST: Evaluates fundamental health status (on-chain metrics for crypto, balance sheets for stocks).\n"
            "• BULL VS BEAR RESEARCHERS: Formulate opposing theses to encourage critical debate and avoid confirmation bias.\n"
            "• MODERATOR / CONSENSUS: Unifies reports from agents into a final directional rating (BUY/SELL/HOLD) and determines the Confidence score of the analysis.\n\n"
            "⚖️ QUANTITATIVE ENSEMBLE (WEIGHTS):\n"
            "• Allows configuring the relative weight (%) of three key components: KNN-DTW Pattern Matching, Google TimesFM (Time-Series Analysis), and AI Consensus.\n"
            "• The system calculates a weighted average of forecasts to determine whether to exceed trading operational thresholds.\n\n"
            "💬 DEBATE ROUNDS (DEBATE CYCLES):\n"
            "• Regulates how many comparison rounds will occur between Bull and Bear factions (from 1 to 5). More rounds increase the critical accuracy of the final consensus, at the expense of higher token usage.\n"
            "• The AI analyst automatically calculates technical levels of Take Profit (TP) and Stop Loss (SL) by combining the asset's current price with signal confidence, expected change, and portfolio risk parameters.\n\n"
            "🔑 API KEYS & PROVIDERS:\n"
            "• PROVIDER: Supports OpenRouter (top-tier cloud LLMs like Claude 3.5 Sonnet, GPT-4o) and Ollama (local LLMs, ideal for privacy and zero cost).\n"
            "• EXTERNAL SOURCES: Integrates Finnhub (for financial news) and CoinGecko (for crypto data and news)."
        )

        ctk.CTkLabel(
            info_card,
            text=info_text,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=("#c0c8e0", "#c0c8e0"),
            justify="left",
            anchor="w",
            wraplength=380,
        ).grid(row=1, column=0, padx=16, pady=(0, 16), sticky="ew")

        # Traccia cambiamenti del provider per aggiornare dinamicamente i campi
        self._provider_var.trace_add("write", self._update_provider_fields)

        # Carica valori iniziali
        self._load_ai_settings()

    def _update_provider_fields(self, *args):
        """Mostra/nasconde dinamicamente i campi specifici a seconda del provider scelto."""
        prov = self._provider_var.get()
        if prov == "ollama":
            self._ai_apikey_label.grid_remove()
            self._ai_apikey_frame.grid_remove()
            
            self._ollama_host_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(4, 2))
            self._ollama_host_entry.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 8))
        else:
            self._ollama_host_label.grid_remove()
            self._ollama_host_entry.grid_remove()
            
            # Aggiorna dinamicamente l'etichetta del provider attivo
            prov_display = "OpenRouter"
            if prov == "claude":
                prov_display = "Claude"
            elif prov == "openai":
                prov_display = "OpenAI"
            self._ai_apikey_label.configure(text=f"API Key Provider ({prov_display})")
            
            self._ai_apikey_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(4, 2))
            self._ai_apikey_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 8))

    def _load_ai_settings(self):
        """Carica le impostazioni AI dal dizionario settings."""
        s = self._app_settings
        self._provider_var.set(s.get("ai_provider", "openrouter"))
        self._ollama_host_var.set(s.get("ai_ollama_host", "http://localhost:11434/v1"))
        
        # Gestisce la transizione da vecchio ai_model a modelli differenziati
        old_model = s.get("ai_model", "anthropic/claude-3-haiku")
        self._model_quick_var.set(s.get("ai_model_quick", "").strip() or old_model)
        self._model_deep_var.set(s.get("ai_model_deep", "").strip() or old_model)
        self._model_fallback_var.set(s.get("ai_model_fallback", "google/gemini-2.5-flash").strip())
        
        self._research_rounds_var.set(str(s.get("ai_research_rounds", 1)))
        self._ai_apikey_var.set(s.get("ai_api_key", ""))
        self._finnhub_var.set(s.get("ai_finnhub_key", ""))
        self._cg_ai_key_var.set(s.get("ai_coingecko_key", ""))
        
        self._w_tfm_var.set(s.get("ensemble_w_tfm", 40.0))
        self._w_tfm_label.configure(text=f"{int(s.get('ensemble_w_tfm', 40.0))} %")
        self._w_pm_var.set(s.get("ensemble_w_pm", 35.0))
        self._w_pm_label.configure(text=f"{int(s.get('ensemble_w_pm', 35.0))} %")
        self._w_ai_var.set(s.get("ensemble_w_ai", 25.0))
        self._w_ai_label.configure(text=f"{int(s.get('ensemble_w_ai', 25.0))} %")

    def _save_ai_settings(self):
        """Salva le impostazioni AI."""
        try:
            rounds = int(self._research_rounds_var.get())
        except Exception:
            rounds = 1
        updated = {
            "ai_provider":            self._provider_var.get(),
            "ai_ollama_host":         self._ollama_host_var.get().strip(),
            "ai_model_quick":         self._model_quick_var.get().strip(),
            "ai_model_deep":          self._model_deep_var.get().strip(),
            "ai_model_fallback":      self._model_fallback_var.get().strip(),
            "ai_research_rounds":     rounds,
            "ai_api_key":             self._ai_apikey_var.get().strip(),
            "ai_finnhub_key":         self._finnhub_var.get().strip(),
            "ai_coingecko_key":       self._cg_ai_key_var.get().strip(),
            "ensemble_w_tfm":         int(self._w_tfm_var.get()),
            "ensemble_w_pm":          int(self._w_pm_var.get()),
            "ensemble_w_ai":          int(self._w_ai_var.get()),
        }
        self._app_settings.update(updated)
        save_settings(self._app_settings)
        self._status("✅ Settings saved.")

    # ─────────────────────────────────────────────────────────
    # Esecuzione analisi
    # ─────────────────────────────────────────────────────────

    def _start_analysis(self):
        if self._running:
            return

        # Raccoglie i titoli selezionati
        selected = self._get_selected_crypto()
        if not selected:
            messagebox.showwarning("Empty selection", "Select at least one asset to analyze.")
            return

        # Verifica API key
        s = self._app_settings
        api_key = s.get("ai_api_key", "").strip()
        provider = s.get("ai_provider", "openrouter")
        if not api_key and provider != "ollama":
            messagebox.showwarning(
                "Missing API Key",
                f"Enter the API key for provider '{provider}' in the Settings tab."
            )
            self._tabs.set("⚙️  Settings")
            return

        self._running = True
        self._stop_requested = False
        self._btn_run.configure(state="disabled")
        self._progress.set(0.0)
        try:
            self._tabs.set("📊  Results")
        except:
            pass

        thread = threading.Thread(
            target=self._analysis_thread,
            args=(selected, dict(self._app_settings)),
            daemon=True,
        )
        thread.start()

    def _stop_analysis(self):
        self._stop_requested = True
        self._status("⏹ Stop requested...")

    def _analysis_thread(self, crypto_list: list[dict], settings: dict):
        def cb(msg: str, frac: float = None):
            self._msg_queue.put({"type": "status", "text": msg, "frac": frac})

        def stop():
            return self._stop_requested

        try:
            pm_move = 0.0
            if settings.get("market_type", "crypto") == "crypto":
                cb("Pattern Matching BTC...", 0.0)
                try:
                    from core.btc_pattern_matcher import BTCPatternMatcher
                    pm_res = BTCPatternMatcher().run_analysis()
                    pm_move = pm_res.get("btc_expected_move", 0.0)
                except Exception as e:
                    import traceback
                    print("PM Error:", traceback.format_exc())

            analyst = AIAnalyst(settings)
            results = analyst.analyze_batch(
                crypto_list,
                progress_callback=cb,
                stop_flag=stop,
            )
            
            for r in results:
                r["btc_expected_move"] = pm_move

            self._msg_queue.put({"type": "done", "results": results, "settings": settings})
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self._msg_queue.put({"type": "error", "text": str(e)})

    def _poll_queue(self):
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                mtype = msg.get("type")

                if mtype == "status":
                    self._status(msg.get("text", ""))
                    frac = msg.get("frac")
                    if frac is not None:
                        self._progress.set(min(frac, 1.0))

                elif mtype == "done":
                    results = msg.get("results", [])
                    settings = msg.get("settings", {})
                    self._ai_results = results
                    self._progress.set(1.0)
                    self._running = False
                    self._btn_run.configure(state="normal")

                    # Salva sessione PRIMA di popolare l'albero per renderla immediatamente visibile
                    meta = {
                        "ai_provider": settings.get("ai_provider", ""),
                        "ai_model_quick": settings.get("ai_model_quick", ""),
                        "ai_model_deep": settings.get("ai_model_deep", ""),
                        "ai_model_fallback": settings.get("ai_model_fallback", ""),
                        "market_type": settings.get("market_type", "crypto"),
                    }
                    sid = save_ai_session(results, meta)
                    self._current_session_id = sid

                    # Ricarica lo storico comprensivo della nuova sessione salvata
                    self._populate_results_tree()

                    n = len(results)
                    buy_n = sum(1 for r in results if r.get("signal_1d") == "BUY")
                    sell_n = sum(1 for r in results if r.get("signal_1d") == "SELL")
                    self._status(
                        f"✅ Analysis completed — {n} assets | 🟢 {buy_n} BUY | 🔴 {sell_n} SELL | "
                        f"Session saved: {sid}"
                    )

                elif mtype == "error":
                    err = msg.get("text", "Unknown error")
                    self._running = False
                    self._btn_run.configure(state="normal")
                    self._status(f"❌ Error: {err}")
                    messagebox.showerror("AI Analysis Error", err)

        except queue.Empty:
            pass

        self.after(100, self._poll_queue)

    def _status(self, text: str):
        prefix = "·  " if not text.startswith(("·", "✅", "❌", "🤖", "📊", "📂", "⏹")) else ""
        self._status_lbl.configure(text=f"{prefix}{text}")


# ─────────────────────────────────────────────────────────────
# AgentDebateWindow — Finestra dettaglio agenti
# ─────────────────────────────────────────────────────────────

class AgentDebateWindow(ctk.CTkToplevel):
    """Finestra che mostra il dibattito completo tra gli agenti per una crypto."""

    AGENTS = [
        ("📊 Market Analyst",      "market_analysis",      "#1a2e4a"),
        ("📰 News Analyst",        "news_analysis",        "#1a2e2a"),
        ("🏗️ Fundamentals",        "fundamentals_analysis","#1a1a2e"),
        ("🐂 Bull Researcher",     "bull_case",            "#0d2e1a"),
        ("🐻 Bear Researcher",     "bear_case",            "#2e0d0d"),
    ]

    def __init__(self, parent, result: dict):
        super().__init__(parent)
        sym = result.get("symbol", "?")
        name = result.get("name", sym)
        self.title(f"🔍 Agent Debate — {name} ({sym})")
        self.geometry("900x700")
        self.configure(fg_color=BG_DARK)
        self.transient(parent)
        self.lift()
        self.after(50, self.focus_force)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, height=60, fg_color=BG_CARD, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text=f"🔍  {name} ({sym}) — Multi-Agent Debate",
            font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color=COLOR_ACCENT,
        ).grid(row=0, column=0, padx=20, pady=16, sticky="w")

        sig1 = result.get("signal_1d", "N/A")
        conf = result.get("confidence", "N/A")
        ctk.CTkLabel(
            hdr,
            text=(f"Decisione: {_fmt_signal(sig1)} 2h  |  "
                  f"Confidence: {_fmt_conf(conf)}"),
            font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_TEXT,
        ).grid(row=0, column=1, padx=20, pady=16, sticky="e")

        # Scroll area
        scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK, corner_radius=0)
        scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)

        debug = result.get("debug", {})
        for i, (agent_name, key, bg_color) in enumerate(self.AGENTS):
            content = debug.get(key, "— Dati non disponibili —")
            card = ctk.CTkFrame(scroll, fg_color=bg_color, corner_radius=10, border_width=1, border_color=COLOR_SEP)
            card.grid(row=i, column=0, sticky="ew", padx=16, pady=6)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                card, text=agent_name,
                font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=COLOR_ACCENT, anchor="w",
            ).grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

            ctk.CTkLabel(
                card, text=content,
                font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_TEXT,
                anchor="w", justify="left", wraplength=820,
            ).grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")

        # Backtest Istantaneo
        backtest_content = result.get("backtest_results", "— Dati Backtest Non Disponibili —")
        backtest_card = ctk.CTkFrame(scroll, fg_color=("#0d2e4a", "#0d2e4a"), corner_radius=10,
                                     border_width=1, border_color=COLOR_ACCENT)
        backtest_card.grid(row=len(self.AGENTS), column=0, sticky="ew", padx=16, pady=6)
        backtest_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            backtest_card, text="📈 Instant Backtest (Last 6 Months)",
            font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=COLOR_ACCENT, anchor="w",
        ).grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        ctk.CTkLabel(
            backtest_card, text=backtest_content,
            font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_TEXT,
            anchor="w", justify="left", wraplength=820,
        ).grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")

        # Decisione finale
        final_card = ctk.CTkFrame(scroll, fg_color=("#1a1040", "#1a1040"), corner_radius=10,
                                   border_width=2, border_color=COLOR_ACCENT)
        final_card.grid(row=len(self.AGENTS) + 1, column=0, sticky="ew", padx=16, pady=(10, 6))
        final_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            final_card, text="🎯 Portfolio Manager",
            font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=COLOR_ACCENT, anchor="w",
        ).grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        rationale = result.get("rationale", "")
        key_risk  = result.get("key_risk", "")
        
        raw_pm = debug.get("portfolio_manager")
        if raw_pm:
            final_text = raw_pm
        else:
            final_text = (
                f"SIGNAL 2h: {_fmt_signal(sig1)}  |  "
                f"Target: {_fmt_price(result.get('target_price_1d'))}  |  "
                f"Var: {_fmt_pct(result.get('ai_change_pct_1d'))}\n\n"
                f"Rationale: {rationale}\n\n"
                f"⚠ Rischio chiave: {key_risk}"
            )
            
        ctk.CTkLabel(
            final_card, text=final_text,
            font=ctk.CTkFont("Segoe UI", 11), text_color=COLOR_TEXT,
            anchor="w", justify="left", wraplength=820,
        ).grid(row=1, column=0, padx=14, pady=(0, 14), sticky="ew")
