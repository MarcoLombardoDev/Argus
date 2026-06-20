"""
config_panel.py — Argus
Configuration panel for time-series forecasting (TimesFM).
Exposes: market type, horizon, threshold, history days, backend, model.
Top-N assets and provider configuration are now in the Markets section.
"""

import customtkinter as ctk
from tkinter import messagebox
from gui.utils import apply_binance_tab_style


class ConfigPanel(ctk.CTkScrollableFrame):
    """
    Panel with all the analysis configuration controls, with scrollbar.
    """

    def __init__(self, parent, settings: dict, on_save_callback=None, **kwargs):
        super().__init__(parent, **kwargs)

        self._settings = settings
        self._on_save = on_save_callback

        self._build_ui()
        self._load_values()

    # -------------------------------------------------------------------------
    # Build UI
    # -------------------------------------------------------------------------

    def _build_ui(self):
        self.configure(
            fg_color=("#1e2329", "#181a20"),
            corner_radius=0,
        )
        self.grid_columnconfigure(0, weight=1, minsize=400)
        self.grid_columnconfigure(1, weight=1, minsize=400)

        # ── Left Frame (Settings) ───────────────────────────────────────────
        left_frame = ctk.CTkFrame(self, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(16, 20), pady=16)
        left_frame.grid_columnconfigure(0, weight=1)

        # ── Right Frame (Information) ──────────────────────────────────────
        right_frame = ctk.CTkFrame(self, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(20, 16), pady=16)
        right_frame.grid_columnconfigure(0, weight=1)

        # Local helper label and separator
        def section_title(text, row):
            ctk.CTkLabel(
                left_frame,
                text=text,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=("#f0b90b", "#f0b90b"),
                anchor="w",
            ).grid(row=row, column=0, padx=16, pady=(16, 4), sticky="ew")

        def label(text, row):
            self._create_label(text, left_frame, row)

        def sep(row):
            self._separator(left_frame, row)



        # Backend and Model (No section title)
        r = 6
        label("Computation Backend", row=r); r += 1
        self._backend_var = ctk.StringVar(value="cpu")
        self._backend_seg = ctk.CTkSegmentedButton(
            left_frame,
            values=["cpu", "gpu"],
            variable=self._backend_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=("#2b3139", "#2b3139"),
            selected_color=("#f0b90b", "#f0b90b"),
            selected_hover_color=("#d39e00", "#d39e00"),
            unselected_color=("#2b3139", "#2b3139"),
            unselected_hover_color=("#343a40", "#343a40"),
            text_color="white",
        )
        self._backend_seg.grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        apply_binance_tab_style(self._backend_seg)
        ctk.CTkLabel(left_frame, text="Select 'cpu' for CPU or 'gpu' if you have an NVIDIA card configured with CUDA to load TimesFM quickly.", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1

        # Model checkpoint
        label("TimesFM Model", row=r); r += 1
        self._model_var = ctk.StringVar(value="google/timesfm-2.5-200m-pytorch")
        self._model_menu = ctk.CTkOptionMenu(
            left_frame,
            values=[
                "google/timesfm-2.5-200m-pytorch",
                "google/timesfm-2.0-500m-pytorch",
                "google/timesfm-1.0-200m-pytorch",
            ],
            variable=self._model_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=("#2b3139", "#2b3139"),
            button_color=("#f0b90b", "#f0b90b"),
            button_hover_color=("#d39e00", "#d39e00"),
            dropdown_fg_color=("#2b3139", "#2b3139"),
            dropdown_hover_color=("#343a40", "#343a40"),
            text_color="white",
            dropdown_text_color="white",
            height=36,
        )
        self._model_menu.grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        ctk.CTkLabel(left_frame, text="The Google TimesFM (Time Series Foundation Model) for statistical time-series forecasting.", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1
        
        # HF Token
        label("Hugging Face (HF) Token (optional)", row=r); r += 1
        self._hf_token_var = ctk.StringVar(value="")
        
        hf_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        hf_frame.grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        hf_frame.grid_columnconfigure(0, weight=1)

        self._hf_token_entry = ctk.CTkEntry(
            hf_frame,
            textvariable=self._hf_token_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            placeholder_text="hf_xxxxxxxxxxxxxxxxxxxx (leave empty for anonymous)",
            show="*",
            fg_color=("#2b3139", "#2b3139"),
            border_color=("#f0b90b", "#f0b90b"),
            border_width=1,
            height=36,
        )
        self._hf_token_entry.grid(row=0, column=0, sticky="ew")

        def toggle_hf():
            if self._hf_token_entry.cget("show") == "*":
                self._hf_token_entry.configure(show="")
                hf_btn.configure(text="🙈")
            else:
                self._hf_token_entry.configure(show="*")
                hf_btn.configure(text="👁")

        hf_btn = ctk.CTkButton(
            hf_frame,
            text="👁",
            width=36,
            height=36,
            fg_color=("#2b3139", "#2b3139"),
            hover_color=("#343a40", "#343a40"),
            border_color=("#f0b90b", "#f0b90b"),
            border_width=1,
            command=toggle_hf
        )
        hf_btn.grid(row=0, column=1, padx=(4, 0))
        
        ctk.CTkLabel(left_frame, text="Token required if you encounter download rate limits on Hugging Face servers.", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#888888", justify="left", anchor="w").grid(row=r, column=0, padx=16, pady=(0, 12), sticky="ew"); r += 1
        
        sep(row=r); r += 1

        # Save Config Button
        self._btn_save = ctk.CTkButton(
            left_frame,
            text="💾 Save Settings",
            command=self._save_config,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=("#f0b90b", "#f0b90b"),
            hover_color=("#d39e00", "#d39e00"),
            text_color="#181a20",
            height=38,
            corner_radius=8,
        )
        self._btn_save.grid(row=r, column=0, padx=16, pady=(12, 6), sticky="ew")

        # ── Right Frame (Information) ──────────────────────────────────────
        # Info Box Card (Premium design with nice border and background)
        info_card = ctk.CTkFrame(
            right_frame,
            fg_color=("#2b3139", "#1e2329"),
            border_color=("#474d57", "#474d57"),
            border_width=1,
            corner_radius=12,
        )
        info_card.grid(row=0, column=0, sticky="nsew", padx=8, pady=16)
        info_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            info_card,
            text="💡 TIME-SERIES FORECAST LOGIC",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=("#f0b90b", "#f0b90b"),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        info_text = (
            "Time-Series Analysis performs advanced statistical forecasting on asset prices (e.g., BTC) using pre-trained Deep Learning models.\n\n"
            "🔮 GOOGLE TIMESFM MODELS:\n"
            "• TimesFM (Time Series Foundation Model) is a family of models developed by Google Research specifically for zero-shot forecasting of time-series data.\n"
            "• The model processes the asset's recent history (usually the last 30 days) to estimate the future price in the short term (time horizon set to 2 hours).\n\n"
            "⚡ HWD ACCELERATION & BACKENDS:\n"
            "• CPU BACKEND: Suitable for systems without a dedicated GPU or for quick testing. Slower inference.\n"
            "• GPU BACKEND: Enables significantly higher computation speed. Activate only if NVIDIA CUDA drivers are correctly configured and PyTorch is enabled for CUDA on your system.\n\n"
            "🎫 HUGGING FACE CONFIGURATION:\n"
            "• TimesFM model weights reside in Hugging Face public repositories and are downloaded locally on first use.\n"
            "• Inputting a Hugging Face Token (optional) prevents blocks due to rate-limiting or limits on anonymous downloads on Hugging Face.\n\n"
            "📈 INTERPRETATION OF RESULTS:\n"
            "• The predicted variation is compared with the signal threshold ('signal_threshold_pct', e.g., ±2.0%). If the variation exceeds this threshold, a directional signal (BUY or SELL) is generated, otherwise HOLD is indicated."
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

    # -------------------------------------------------------------------------
    # Helper builders
    # -------------------------------------------------------------------------

    def _create_label(self, text: str, parent, row: int):
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("#8090b0", "#8090b0"),
            anchor="w",
        ).grid(row=row, column=0, padx=16, pady=(8, 2), sticky="ew")

    def _separator(self, parent, row: int):
        frame = ctk.CTkFrame(parent, height=1, fg_color=("#2a2a4a", "#2a2a4a"))
        frame.grid(row=row, column=0, padx=16, pady=4, sticky="ew")

    # -------------------------------------------------------------------------
    # Logic
    # -------------------------------------------------------------------------

    def _on_threshold_change(self, value):
        # threshold removed
        pass

    def _load_values(self):
        """Loads values from the settings dict into widgets."""
        s = self._settings

        # threshold_var removed
        
        self._backend_var.set(s.get("backend", "cpu"))
        self._model_var.set(
            s.get("model_checkpoint", "google/timesfm-2.5-200m-pytorch")
        )
        self._hf_token_var.set(s.get("hf_token", ""))

    def _save_config(self):
        """Reads values from widgets and saves configuration."""
        # history check removed

        market_type = "crypto"

        updated = {
            "market_type": market_type,
            "horizon_days": 1,
            "signal_threshold_pct": self._settings.get("signal_threshold_pct", 2.0),
            "backend": self._backend_var.get(),
            "model_checkpoint": self._model_var.get(),
            "hf_token": self._hf_token_var.get().strip(),
        }
        self._settings.update(updated)

        if self._on_save:
            self._on_save(updated)

    def get_current_settings(self) -> dict:
        return {
            "market_type": "crypto",
            "horizon_days": 1,
            "backend": self._backend_var.get(),
            "model_checkpoint": self._model_var.get(),
            "hf_token": self._hf_token_var.get().strip(),
        }


    def _test_connection(self):
        """Connection test method (mock)"""
        from tkinter import messagebox
        messagebox.showinfo("Connection Test", "The connection to backend services is active and functional.")

class ConfigWindow(ctk.CTkToplevel):
    """
    Modal configuration window containing the ConfigPanel.
    """
    def __init__(self, parent, settings: dict, on_save_callback=None):
        super().__init__(parent)
        self.title("Argus Settings")
        self.geometry("350x500")
        self.resizable(False, False)
        
        # Make the window modal and on top of the parent
        self.transient(parent)
        self.grab_set()
        
        # Force dark theme on Windows title bar
        self.after(10, self._focus_and_center)

        # ConfigPanel placed inside the modal window
        def _on_save_and_close(updated):
            if on_save_callback:
                on_save_callback(updated)
            self.destroy()

        self._panel = ConfigPanel(
            self,
            settings=settings,
            on_save_callback=_on_save_and_close
        )
        self._panel.pack(fill="both", expand=True)

    def _focus_and_center(self):
        self.focus()
        # Center the modal window relative to the main window
        parent = self.master
        if parent:
            px = parent.winfo_x()
            py = parent.winfo_y()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            
            x = px + (pw - 350) // 2
            y = py + (ph - 500) // 2
            self.geometry(f"+{x}+{y}")
