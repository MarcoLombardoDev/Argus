# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
app.py — Argus
CustomTkinter main window. Coordinates configuration, analysis, and visualization.

Layout:
  ┌─────────────────────────────────────────────────────────────┐
  │ 👁️ ARGUS  │  · status text            │ [📈 Temporale] [🤖 AI] │
  │━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
  │                                                             │
  │  [Time-Series Analysis View]  ─OR─  [AI Analysis View]       │
  │  (toggled in the main body via navigation click)           │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
"""

import os
import sys
import threading
import queue
import time
import webbrowser
from datetime import datetime
from urllib.parse import quote
import customtkinter as ctk
from tkinter import messagebox

from core.version import APP_TITLE, CONTACT_EMAIL, __version__

from core.data_manager import (
    load_settings, save_settings,
    save_forecast_log, get_last_run_info, load_forecast_history,
    load_market_list,
)

from core.forecaster import CryptoForecaster
from core.analyzer import build_results
from gui.config_panel import ConfigPanel
from gui.results_table import ResultsTable
from gui.ai_analysis_panel import AIAnalysisPanel
from gui.markets_panel import MarketsPanel
from gui.portfolio_panel import PortfolioPanel
from gui.auto_trading_panel import AutoTradingPanel
from gui.pattern_matching_panel import PatternMatchingPanel
from gui.utils import apply_binance_tab_style


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Forecast horizon: 8 candles of 15 minutes = 2 hours.
FORECAST_HORIZON_CANDLES = 8
DEFAULT_TIMESFM_CHECKPOINT = "google/timesfm-2.5-200m-pytorch"

# ─── Colori tema ────────────────────────────────────────────────
_BG_ROOT   = ("#181a20", "#181a20")
_BG_TOPBAR = _BG_ROOT
_BG_PANEL  = ("#1e2329", "#1e2329")
_BG_INPUT  = ("#2b3139", "#2b3139")
_ACCENT    = ("#f0b90b", "#f0b90b")
_HOVER     = ("#d39e00", "#d39e00")
_MUTED     = ("#848e9c", "#848e9c")
_SEP       = ("#474d57", "#474d57")


class ArgusApp(ctk.CTk):
    """Main window of Argus."""

    def __init__(self):
        super().__init__()

        self._settings = load_settings()
        self._forecaster: CryptoForecaster | None = None
        self._results: list[dict] = []
        self._running = False
        self._stop_requested = False
        self._msg_queue: queue.Queue = queue.Queue()
        self._last_configure_time = 0.0
        self._active_view = "portfolio"   # "portfolio" | "markets" | "temporal" | "ai"
        self._cached_market_list: list[dict] = []  # Lista asset cached dalla sezione Mercati

        self._set_window_icon()
        self._configure_window()
        self._build_ui()
        self._load_last_log()
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_window_configure)
        self.after(250, self._maximize)

    def _set_window_icon(self):
        """Give the window the application icon.

        Two files, because Tk uses two: the PhotoImage works on every
        platform and Tk has read PNG since 8.6, and ``iconbitmap`` is tried
        afterwards on Windows for the sharper small sizes. Argus shipped
        neither and ran under the bare Tk feather everywhere.

        The PhotoImage is kept on the instance: Tk holds only a weak
        reference to it, and a garbage-collected image leaves a blank icon.

        Never raises. A missing icon is cosmetic, and nothing cosmetic should
        be a reason the program does not start.
        """
        import tkinter as tk

        from core.paths import bundled_dir

        assets = bundled_dir() / "assets"

        # Two independent attempts, and the independence is the point: one
        # ``try`` around both means a failing ``iconbitmap`` takes the
        # fallback down with it and the window keeps Tk's default feather.
        png = assets / "app_icon.png"
        if png.exists():
            try:
                self._app_icon = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._app_icon)
            except Exception:  # noqa: BLE001 — see the docstring
                pass

        if os.name == "nt":
            ico = assets / "app_icon.ico"
            if ico.exists():
                try:
                    self.iconbitmap(str(ico))
                except Exception:  # noqa: BLE001 — iconphoto already did it
                    pass

    def _maximize(self):
        """Maximises the window in a cross-platform way.

        Each attempt is measured rather than trusted. It used to stop at the
        first call that did not raise, and not raising is not the same as
        having worked: with no window manager running, both of the first two
        are accepted in silence and change nothing, and the chain then never
        reaches the one that would have worked.
        """
        def filled() -> bool:
            try:
                self.update_idletasks()
                return (
                    self.winfo_width() >= self.winfo_screenwidth() * 0.9
                    and self.winfo_height() >= self.winfo_screenheight() * 0.8
                )
            except Exception:  # noqa: BLE001 — a wrong size must not stop start-up
                return False

        try:
            self.update_idletasks()
        except Exception:  # noqa: BLE001
            pass

        for attempt in (
            lambda: self.state("zoomed"),
            lambda: self.attributes("-zoomed", True),
            lambda: self.geometry(
                f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0"
            ),
        ):
            try:
                attempt()
            except Exception:  # noqa: BLE001
                continue
            if filled():
                return

    # ─────────────────────────────────────────────────────────────
    # Window setup
    # ─────────────────────────────────────────────────────────────

    def _configure_window(self):
        # A frozen (PyInstaller) build has no .py sources on disk to derive a
        # "last changed" date from — walking for one here would silently
        # settle on the epoch, printing "v. 1970.01.01" in the title bar.
        # Running from source, the mtime scan is left in as a convenience so
        # the title reflects the last edit without a manual version bump.
        if getattr(sys, "frozen", False):
            v_date = __version__
        else:
            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                max_mtime = 0
                for root, dirs, files in os.walk(base_dir):
                    if '.git' in root or '__pycache__' in root or 'data' in root:
                        continue
                    for file in files:
                        if file.endswith('.py'):
                            mtime = os.path.getmtime(os.path.join(root, file))
                            if mtime > max_mtime:
                                max_mtime = mtime
                v_date = datetime.fromtimestamp(max_mtime).strftime("%Y.%m.%d")
            except Exception:
                v_date = __version__

        self.title(f"Argus — v. {v_date}")
        self.geometry("1300x840")
        self.minsize(1100, 680)
        self.configure(fg_color=_BG_ROOT)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    # ─────────────────────────────────────────────────────────────
    # Build UI — struttura principale
    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # === ROOT CONTAINER ===
        main_area = ctk.CTkFrame(self, fg_color=_BG_ROOT, corner_radius=0)
        main_area.grid(row=0, column=0, sticky="nsew")
        main_area.grid_columnconfigure(0, weight=1)
        main_area.grid_rowconfigure(1, weight=1)
        main_area.grid_rowconfigure(2, weight=0)  # footer row

        # Topbar (navigazione)
        self._build_topbar(main_area)

        # Content area — contiene tutti e tre i pannelli (uno alla volta visibile)
        self._content = ctk.CTkFrame(main_area, fg_color=_BG_ROOT, corner_radius=0)
        self._content.grid(row=1, column=0, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        # Costruisce i pannelli principali
        self._build_auto_trading_panel(self._content)
        self._build_portfolio_panel(self._content)
        self._build_markets_panel(self._content)
        self._build_pm_panel(self._content)
        self._build_temporal_panel(self._content)
        self._build_ai_panel(self._content)

        # Footer copyright
        self._build_footer(main_area)

        # Mostra la vista auto trading di default (o portfolio)
        self._switch_view("autotrading", force=True)

    # ─────────────────────────────────────────────────────────────
    # Footer — Copyright
    # ─────────────────────────────────────────────────────────────

    def _build_footer(self, parent):
        """Barra di copyright fissa in fondo alla finestra."""
        footer = ctk.CTkFrame(
            parent,
            height=22,
            fg_color=("#0f1117", "#0f1117"),
            corner_radius=0,
        )
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_rowconfigure(0, weight=1)

        # Chi sta usando l'applicazione è esattamente la persona che potrebbe
        # dover comprare una licenza commerciale: l'indirizzo è scritto per
        # esteso e cliccabile, invece di un generico "available on request".
        # Un frame interno senza sticky resta centrato nella cella.
        center = ctk.CTkFrame(footer, fg_color="transparent")
        center.grid(row=0, column=0, padx=20)

        self._footer_label = ctk.CTkLabel(
            center,
            text=(
                "© 2026 Marco Lombardo — Argus  |  Licensed under AGPL-3.0  |  "
                "Commercial licensing:"
            ),
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=("#4a5568", "#4a5568"),
        )
        self._footer_label.pack(side="left")

        self._footer_email = ctk.CTkLabel(
            center,
            text=CONTACT_EMAIL,
            font=ctk.CTkFont(family="Segoe UI", size=9, underline=True),
            text_color=("#4a9eff", "#4a9eff"),
            cursor="hand2",
        )
        self._footer_email.pack(side="left", padx=(4, 0))
        self._footer_email.bind("<Button-1>", self.open_licensing_email)

    def open_licensing_email(self, event=None):
        """Apre il client di posta su una richiesta di licenza commerciale."""
        subject = quote(f"{APP_TITLE} — commercial licence enquiry")
        try:
            webbrowser.open(f"mailto:{CONTACT_EMAIL}?subject={subject}")
        except Exception:
            # Nessun client di posta configurato: l'indirizzo resta comunque
            # leggibile a schermo, quindi non vale un dialog di errore.
            pass

    # ─────────────────────────────────────────────────────────────
    # Topbar — Logo + Status + Navigazione
    # ─────────────────────────────────────────────────────────────

    def _build_topbar(self, parent):
        topbar = ctk.CTkFrame(parent, height=52, fg_color=_BG_TOPBAR, corner_radius=0)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        topbar.grid_rowconfigure(0, weight=1)
        topbar.grid_rowconfigure(1, weight=0)
        topbar.grid_columnconfigure(1, weight=1)   # per spingere i bottoni a destra

        # ── Logo ──────────────────────────────────────────────────
        ctk.CTkLabel(
            topbar,
            text="👁️ ARGUS",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=_ACCENT,
        ).grid(row=0, column=0, padx=(20, 16), sticky="w")

        # ── Separatore verticale ─────────────────────────────────────
        ctk.CTkFrame(topbar, width=1, fg_color=_SEP).grid(
            row=0, column=0, padx=(120, 0), pady=8, sticky="ns"
        )

        # ── Pulsanti di navigazione ──────────────────────────────────
        nav_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        nav_frame.grid(row=0, column=2, padx=(0, 20), sticky="e")

        # ─ Auto Trading (PRIMO, a sinistra) ──────────────────────────
        self._btn_nav_auto = ctk.CTkButton(
            nav_frame,
            text="🤖  Auto Trading",
            command=lambda: self._switch_view("autotrading"),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_BG_INPUT,
            hover_color=_HOVER,
            border_color=_ACCENT,
            border_width=1,
            height=40,
            width=160,
            corner_radius=8,
        )

        # ─ Portfolio ──────────────────────────
        self._btn_nav_portfolio = ctk.CTkButton(
            nav_frame,
            text="💼  Portfolio",
            command=lambda: self._switch_view("portfolio"),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_BG_INPUT,
            hover_color=_HOVER,
            border_color=_ACCENT,
            border_width=1,
            height=40,
            width=180,
            corner_radius=8,
        )

        # ─ Mercati ──────────────────────────
        self._btn_nav_markets = ctk.CTkButton(
            nav_frame,
            text="🌐  Market",
            command=lambda: self._switch_view("markets"),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_BG_INPUT,
            hover_color=_HOVER,
            border_color=_ACCENT,
            border_width=1,
            height=40,
            width=160,
            corner_radius=8,
        )

        # ─ Pattern Matching ─────────────────────────────────
        self._btn_nav_pm = ctk.CTkButton(
            nav_frame,
            text="🔍  Pattern Matching",
            command=lambda: self._switch_view("pm"),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_BG_INPUT,
            hover_color=_HOVER,
            border_color=_ACCENT,
            border_width=1,
            height=40,
            width=180,
            corner_radius=8,
        )

        # ─ Analisi Temporale ────────────────────────────────
        self._btn_nav_temporal = ctk.CTkButton(
            nav_frame,
            text="📈  Time-Series Analysis",
            command=lambda: self._switch_view("temporal"),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_ACCENT,
            hover_color=_HOVER,
            height=40,
            width=190,
            corner_radius=8,
        )

        self._btn_nav_ai = ctk.CTkButton(
            nav_frame,
            text="🤖  Advanced Analysis",
            command=lambda: self._switch_view("ai"),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_BG_INPUT,
            hover_color=_HOVER,
            border_color=_ACCENT,
            border_width=1,
            height=40,
            width=190,
            corner_radius=8,
        )

        # Pack in the original requested order (Auto Trading, Portfolio, then others)
        self._btn_nav_auto.pack(side="left", padx=(0, 6))
        self._btn_nav_portfolio.pack(side="left", padx=(0, 6))
        self._btn_nav_markets.pack(side="left", padx=(0, 6))
        self._btn_nav_pm.pack(side="left", padx=(0, 6))
        self._btn_nav_temporal.pack(side="left", padx=(0, 6))
        self._btn_nav_ai.pack(side="left")

        # ── Progress bar (riga 1) ─────────────────────────────────
        self._progress = ctk.CTkProgressBar(
            topbar,
            height=3,
            fg_color=("#1a1e2e", "#1a1e2e"),
            progress_color=_ACCENT,
            corner_radius=0,
        )
        self._progress.grid(row=1, column=0, columnspan=3, sticky="ew", padx=0, pady=0)
        self._progress.set(0)

    # ───────────────────────────────────────────────────────────────
    # Vista 00 — Auto Trading
    # ───────────────────────────────────────────────────────────────

    def _build_auto_trading_panel(self, parent):
        """Costruisce il pannello Auto Trading."""
        self._auto_trading_panel = AutoTradingPanel(
            parent,
            settings=self._settings,
            app_instance=self
        )

    # ───────────────────────────────────────────────────────────────
    # Vista 0 — Portfolio
    # ───────────────────────────────────────────────────────────────

    def _build_portfolio_panel(self, parent):
        """Costruisce il pannello Portfolio."""
        self._portfolio_panel = PortfolioPanel(
            parent,
            settings=self._settings,
        )

    # ───────────────────────────────────────────────────────────────
    # Vista 1 — Mercato
    # ───────────────────────────────────────────────────────────────

    def _build_markets_panel(self, parent):
        """Costruisce il pannello Mercato."""
        self._markets_panel = MarketsPanel(
            parent,
            settings=self._settings,
        )

    # ───────────────────────────────────────────────────────────────
    # Vista 1 — Pattern Matching
    # ───────────────────────────────────────────────────────────────

    def _build_pm_panel(self, parent):
        self._pm_panel = PatternMatchingPanel(parent, settings=self._settings)

    # ───────────────────────────────────────────────────────────────
    # Vista 1 — Analisi Temporale
    # ───────────────────────────────────────────────────────────────

    def _build_temporal_panel(self, parent):
        """Costruisce il pannello dell'analisi temporale (TimesFM)."""
        self._temporal_frame = ctk.CTkFrame(
            parent,
            fg_color=_BG_PANEL,
            border_color=_SEP,
            border_width=1,
            corner_radius=12,
        )
        # Griglia: riga 0 = sub-header, riga 1 = tab view (expandable)
        self._temporal_frame.grid_columnconfigure(0, weight=1)
        self._temporal_frame.grid_rowconfigure(1, weight=1)

        # ── Sub-header: titolo + log test + pulsante run ────────────
        sub_hdr = ctk.CTkFrame(self._temporal_frame, fg_color="transparent", height=48)
        sub_hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        sub_hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            sub_hdr,
            text="Time-Series Analysis",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=_ACCENT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        # Status label temporale (spostato qui dall'header per coerenza con l'AI)
        self._status_label = ctk.CTkLabel(
            sub_hdr,
            text="·  Ready. Run an analysis.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=_MUTED,
            anchor="w",
        )
        self._status_label.grid(row=0, column=1, padx=(10, 8), sticky="ew")

        # Pulsante run sul lato destro
        self._btn_run = ctk.CTkButton(
            sub_hdr,
            text="▶  Run Time-Series Analysis",
            command=self._start_analysis,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_ACCENT,
            hover_color=_HOVER,
            text_color="#181a20",
            height=34,
            width=230,
            corner_radius=8,
        )
        self._btn_run.grid(row=0, column=2, sticky="e")

        # Separatore orizzontale
        ctk.CTkFrame(self._temporal_frame, height=1, fg_color=_SEP).grid(
            row=0, column=0, sticky="ew", padx=16, pady=(58, 0)
        )

        # ── Tab view ──────────────────────────────────────────
        self._tab_view = ctk.CTkTabview(
            self._temporal_frame,
            fg_color=_BG_PANEL,
            segmented_button_fg_color=("#1e293b", "#1e293b"),
            segmented_button_selected_color=_ACCENT,
            segmented_button_selected_hover_color=_HOVER,
            segmented_button_unselected_color=_BG_PANEL,
            segmented_button_unselected_hover_color=("#343a40", "#343a40"),
            text_color="white",
        )
        self._tab_view.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self._tab_view.add("📊  Results")
        self._tab_view.add("⚙️  Settings")
        apply_binance_tab_style(self._tab_view._segmented_button)

        self._tab_view.tab("📊  Results").grid_columnconfigure(0, weight=1)
        self._tab_view.tab("📊  Results").grid_rowconfigure(0, weight=1)
        self._tab_view.tab("⚙️  Settings").grid_columnconfigure(0, weight=1)
        self._tab_view.tab("⚙️  Settings").grid_rowconfigure(0, weight=1)

        # Tabella risultati
        self._results_table = ResultsTable(self._tab_view.tab("📊  Results"))
        self._results_table.grid(row=0, column=0, sticky="nsew")

        # Pannello impostazioni
        settings_container = ctk.CTkFrame(
            self._tab_view.tab("⚙️  Settings"), fg_color="transparent"
        )
        settings_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=10)
        settings_container.grid_columnconfigure(0, weight=1)
        settings_container.grid_rowconfigure(0, weight=1)

        self._config_panel = ConfigPanel(
            settings_container,
            settings=self._settings,
            on_save_callback=self._on_config_saved,
        )
        self._config_panel.grid(row=0, column=0, sticky="nsew", padx=20, pady=10)

    # ─────────────────────────────────────────────────────────────
    # Vista 2 — Analisi Avanzata AI
    # ─────────────────────────────────────────────────────────────

    def _build_ai_panel(self, parent):
        """Costruisce il pannello dell'analisi avanzata AI (embedded)."""
        # AIAnalysisPanel embedded direttamente, ora gestito con lo stesso stile di bordo e angoli di _temporal_frame
        self._ai_panel = AIAnalysisPanel(
            parent,
            timefm_results=[],
            app_settings=self._settings,
        )

    # ─────────────────────────────────────────────────────────────
    # Navigazione tra viste
    # ─────────────────────────────────────────────────────────────

    def _switch_view(self, view: str, force: bool = False):
        """Alterna tra le quattro viste: portfolio, markets, temporal, ai."""
        if not force and self._active_view == view:
            return

        self._active_view = view

        # Nasconde tutti, poi mostra quello attivo
        self._auto_trading_panel.grid_remove()
        self._portfolio_panel.grid_remove()
        self._markets_panel.grid_remove()
        self._pm_panel.grid_remove()
        self._temporal_frame.grid_remove()
        self._ai_panel.grid_remove()

        padding = dict(padx=16, pady=(0, 16))

        def _btn_active(btn):
            btn.configure(fg_color=_ACCENT, hover_color=_HOVER, border_width=0, text_color="#181a20")

        def _btn_inactive(btn):
            btn.configure(fg_color=_BG_INPUT, hover_color=_HOVER,
                          border_color=_ACCENT, border_width=1, text_color="white")

        # Reset tutti i bottoni
        _btn_inactive(self._btn_nav_auto)
        _btn_inactive(self._btn_nav_portfolio)
        _btn_inactive(self._btn_nav_markets)
        _btn_inactive(self._btn_nav_pm)
        _btn_inactive(self._btn_nav_temporal)
        _btn_inactive(self._btn_nav_ai)

        if view == "autotrading":
            self._auto_trading_panel.grid(row=0, column=0, sticky="nsew", **padding)
            _btn_active(self._btn_nav_auto)
            self._progress.configure(progress_color=_ACCENT[0])

        elif view == "portfolio":
            self._portfolio_panel.grid(row=0, column=0, sticky="nsew", **padding)
            _btn_active(self._btn_nav_portfolio)
            self._progress.configure(progress_color=_ACCENT[0])

        elif view == "markets":
            self._markets_panel.grid(row=0, column=0, sticky="nsew", **padding)
            _btn_active(self._btn_nav_markets)
            
        elif view == "pm":
            self._pm_panel.grid(row=0, column=0, sticky="nsew", **padding)
            _btn_active(self._btn_nav_pm)
            self._progress.configure(progress_color=_ACCENT[0])

        elif view == "temporal":
            self._temporal_frame.grid(row=0, column=0, sticky="nsew", **padding)
            _btn_active(self._btn_nav_temporal)
            self._progress.configure(progress_color=_ACCENT[0])

        else:  # "ai"
            self._ai_panel.grid(row=0, column=0, sticky="nsew", **padding)
            self._ai_panel.update_timefm_results(self._results)
            _btn_active(self._btn_nav_ai)
            self._progress.configure(progress_color=_ACCENT[0])

    # ─────────────────────────────────────────────────────────────
    # Status + progress
    # ─────────────────────────────────────────────────────────────

    def _update_status(self, text: str):
        """Aggiorna il testo dello stato nell'header."""
        prefix = "·  " if not text.startswith(("·", "✅", "❌", "📂", "🤖", "📊", "⏹")) else ""
        self._status_label.configure(text=f"{prefix}{text}")

    def _on_window_configure(self, event):
        if event.widget == self:
            self._last_configure_time = time.time()

    # ─────────────────────────────────────────────────────────────
    # Message queue (thread → GUI)
    # ─────────────────────────────────────────────────────────────

    def _poll_queue(self):
        """Consuma i messaggi dalla coda del thread background."""
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_msg(self, msg: dict):
        mtype = msg.get("type")

        if mtype == "status":
            text = msg.get("text", "")
            frac = msg.get("fraction", None)
            self._update_status(text)
            if frac is not None:
                self._progress.set(frac)

        elif mtype == "done":
            results = msg.get("results", [])
            self._results = results
            self._results_table.populate(results)
            self._set_running(False)
            self._progress.set(1.0)

            n      = len(results)
            buy_n  = sum(1 for r in results if r.get("signal") == "BUY")
            sell_n = sum(1 for r in results if r.get("signal") == "SELL")
            market_type = self._settings.get("market_type", "crypto").upper()
            self._update_status(
                f"✅ Analysis completed [{market_type}] — {n} assets analyzed  |  "
                f"🟢 {buy_n} BUY  🔴 {sell_n} SELL  |  "
                f"Updated: {datetime.now().strftime('%H:%M:%S')}"
            )

        elif mtype == "error":
            err = msg.get("text", "Unknown error")
            self._set_running(False)
            self._update_status(f"❌ {err}")
            messagebox.showerror("Argus Error", err)

    def _post(self, **kwargs):
        """Invia un messaggio alla coda dalla GUI o da un thread."""
        self._msg_queue.put(kwargs)

    # ─────────────────────────────────────────────────────────────
    # Analisi Temporale — avvio e thread
    # ─────────────────────────────────────────────────────────────

    def _start_analysis(self):
        if self._running:
            return

        # Cooldown anti-ghost-click da ridimensionamento finestra
        time_since_configure = time.time() - self._last_configure_time
        if time_since_configure < 0.4:
            print(f"[ArgusApp] Ignored ghost click ({time_since_configure:.3f}s)")
            return

        # Sincronizza impostazioni dalla UI
        if hasattr(self, "_config_panel"):
            try:
                self._settings.update(self._config_panel.get_current_settings())
                save_settings(self._settings)
            except Exception as e:
                print(f"[ArgusApp] Settings sync error: {e}")

        cfg = self._settings
        self._set_running(True)
        self._progress.set(0.0)
        self._tab_view.set("📊  Results")

        threading.Thread(
            target=self._analysis_thread,
            args=(cfg,),
            daemon=True,
        ).start()

    def _stop_analysis(self):
        self._stop_requested = True
        self._update_status("⏹ Stop requested...")

    def _get_market_asset_list(self, market_type: str) -> list[dict]:
        """Returns the asset list to analyse.

        Prefers the list currently held by the Markets panel (it carries the
        freshest prices), then the in-memory cache, then the list persisted on
        disk. Returns [] when nothing is available.
        """
        panel = getattr(self, "_markets_panel", None)
        if panel is not None:
            live = (getattr(panel, "_loaded_lists", None) or {}).get(market_type) or []
            if live:
                self._cached_market_list = live
                return live

        if self._cached_market_list:
            return self._cached_market_list

        full_list = load_market_list(market_type)
        return [full_list[0]] if full_list else []

    def _analysis_thread(self, cfg: dict):
        """Thread background che esegue l'intera pipeline di analisi temporale."""

        def status(text: str, fraction: float | None = None):
            self._post(type="status", text=text, fraction=fraction)

        def should_stop() -> bool:
            return self._stop_requested

        try:
            market_type = "crypto"
            threshold  = cfg.get("signal_threshold_pct", 2.0)
            backend    = cfg.get("backend") or "cpu"
            # settings.json ships "model_checkpoint": "" — an empty string is a
            # present key, so `.get(k, default)` would hand "" to from_pretrained().
            checkpoint = cfg.get("model_checkpoint") or DEFAULT_TIMESFM_CHECKPOINT

            # Step 1: Carica lista asset dalla cache (Mercato) o la rigenera
            status(f"📂 Loading {market_type.upper()} list from Market section...", 0.01)
            asset_list = self._get_market_asset_list(market_type)

            if not asset_list:
                self._post(type="error", text="Unable to retrieve asset list.")
                return

            if should_stop():
                status("⏹ Analysis interrupted by user.", 0.0)
                self._set_running_safe(False)
                return

            status(f"✅ {market_type.upper()} list loaded: {len(asset_list)} assets.", 0.03)

            # Step 2: Dati storici
            status(f"📥 Loading local historical data for {len(asset_list)} assets...", 0.04)
            from core.data_manager import load_historical
            
            historical_data = {}
            for i, coin in enumerate(asset_list):
                sym = coin["symbol"]
                try:
                    df = load_historical(sym)
                    if df is not None and not df.empty:
                        historical_data[sym] = df
                except ValueError as ve:
                    status(f"⚠️ {sym}: {ve}", 0.04 + (i / len(asset_list)) * 0.36)
            
            if should_stop():
                status("⏹ Analysis interrupted by user.", 0.0)
                self._set_running_safe(False)
                return

            if not historical_data:
                self._post(type="error", text="No valid local historical data found. Go to Market and click Update Prices.")
                self._set_running_safe(False)
                return
            
            status(f"✅ Historical data loaded: {len(historical_data)} symbols.", 0.42)

            # Step 3: Carica modello TimesFM
            if (self._forecaster is None
                    or self._forecaster.checkpoint != checkpoint
                    or self._forecaster.backend != backend):
                status("🤖 Initializing TimesFM model...", 0.43)
                self._forecaster = CryptoForecaster(checkpoint=checkpoint, backend=backend)

            if not self._forecaster._model_loaded:
                ok = self._forecaster.load_model(
                    progress_callback=lambda m, f=None: status(m, 0.43 + (f or 0) * 0.07)
                )
                if not ok:
                    self._post(
                        type="error",
                        text="TimesFM loading error. Check installation and internet connection.",
                    )
                    return

            if should_stop():
                status("⏹ Analysis interrupted by user.", 0.0)
                self._set_running_safe(False)
                return

            # Step 4: Forecast (orizzonte fisso 8 candele = 2 ore a 15m)
            status(f"🔮 Running TimesFM forecasting ({FORECAST_HORIZON_CANDLES} candles horizon)...", 0.50)
            forecasts = self._forecaster.forecast_batch(
                historical_data,
                horizon=FORECAST_HORIZON_CANDLES,
                progress_callback=lambda m, f=None: status(m, 0.50 + (f or 0) * 0.40),
                stop_flag=should_stop,
            )

            if should_stop():
                status("⏹ Analysis interrupted by user.", 0.0)
                self._set_running_safe(False)
                return

            # Step 5: Calcola segnali
            status("📊 Calculating BUY/SELL/HOLD signals...", 0.92)
            results = build_results(
                crypto_list=asset_list,
                forecasts=forecasts,
                horizon_days=1,
                threshold_pct=threshold,
            )

            # Salva log
            status("💾 Saving analysis log...", 0.95)
            save_forecast_log(results)
            self._settings["last_run"] = datetime.now().isoformat()
            save_settings(self._settings)

            self._post(type="done", results=results)

        except Exception as exc:
            import traceback
            print(f"[ArgusApp] Exception in analysis thread:\n{traceback.format_exc()}")
            self._post(type="error", text=f"Unexpected error: {exc}")

    # ─────────────────────────────────────────────────────────────
    # UI state helpers
    # ─────────────────────────────────────────────────────────────

    def _set_running(self, running: bool):
        self._running = running
        self._stop_requested = False
        state = "disabled" if running else "normal"
        self._btn_run.configure(state=state)
        if hasattr(self, "_config_panel"):
            self._config_panel._btn_save.configure(state=state)
        # Disabilita anche il pulsante Mercati durante l'analisi
        if hasattr(self, "_btn_nav_markets"):
            self._btn_nav_markets.configure(state=state)

    def _set_running_safe(self, running: bool):
        """Thread-safe: schedula _set_running sulla GUI thread."""
        self.after(0, lambda: self._set_running(running))

    # ─────────────────────────────────────────────────────────────
    # Load logs
    # ─────────────────────────────────────────────────────────────

    def _load_last_log(self):
        """Carica e visualizza l'ultimo forecast log senza rieseguire l'analisi."""
        df = load_forecast_history()
        if df is None or df.empty:
            self._update_status("No previous log found. Run your first analysis.")
            return

        results = df.to_dict(orient="records")
        for r in results:
            for key in ("last_price", "forecast_price", "change_pct", "rank", "horizon_days", 
                        "target_price_1d", "change_pct_1d", "target_price_3d", "change_pct_3d", "confidence"):
                try:
                    import math
                    val = r.get(key)
                    if val is not None and not (isinstance(val, float) and math.isnan(val)):
                        r[key] = float(val) if key != "rank" else int(float(val))
                    else:
                        r[key] = None
                except (ValueError, TypeError):
                    r[key] = None

        self._results = results
        self._results_table.populate(results)
        info = get_last_run_info()
        self._update_status(f"📂 Log loaded — {info}")

    # ─────────────────────────────────────────────────────────────
    # Callbacks & Manual Triggers
    # ─────────────────────────────────────────────────────────────

    # Vecchia funzione rimossa.

    def _on_config_saved(self, updated: dict):
        """Chiamato quando l'utente salva la configurazione TimesFM."""
        save_settings(self._settings)
        market_type = updated.get('market_type', 'crypto').upper()
        self._update_status(
            f"✅ Configuration saved — "
            f"Market: {market_type}  |  "
            f"Horizon: 2h  |  "
            f"Threshold: ±{updated.get('signal_threshold_pct', 2.0)}%"
        )

    def _on_close(self):
        """Chiamato quando l'utente tenta di chiudere l'applicazione."""
        if self._running:
            if not messagebox.askyesno(
                "Confirm Exit",
                "An analysis is still running. Do you really want to exit?"
            ):
                return
            self._stop_requested = True
        self.destroy()
