# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
docs/generate_screenshots.py — Argus

Boots the real Argus GUI under Xvfb, injects realistic-looking SAMPLE data
purely in memory (nothing is written to disk / data/), switches through every
view and captures one PNG per view for the README.

No network calls, no real exchange, no real API keys involved.

Usage (from the repo root, with the dev environment installed):

    mkdir -p docs/screenshots
    SHOTDIR=docs/screenshots xvfb-run -a python docs/generate_screenshots.py

Requires Pillow (`pip install pillow`) in addition to requirements.txt.
"""
import os
import sys
import datetime as dt
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from PIL import ImageGrab

OUT = os.environ.get("SHOTDIR", str(REPO_ROOT / "docs" / "screenshots"))
DISP = os.environ.get("DISPLAY", ":0")
os.makedirs(OUT, exist_ok=True)

from gui.app import ArgusApp
import gui.ai_analysis_panel as ai_panel_mod

app = ArgusApp()

# ─────────────────────────────────────────────────────────────
# 1. Auto Trading — sample run log
# ─────────────────────────────────────────────────────────────
auto_panel = app._auto_trading_panel
sample_logs = [
    {"start_time": "2026-08-10 14:15:30", "duration": "42.1 s", "status": "OK",
     "details": "[EXECUTED] LONG | Leverage: 8x | SL: 1.20% | TP: 2.40%"},
    {"start_time": "2026-08-10 14:00:31", "duration": "38.7 s", "status": "OK",
     "details": "No orders placed for BTC."},
    {"start_time": "2026-08-10 13:45:29", "duration": "51.3 s", "status": "OK",
     "details": "[SIMULATED] SHORT | Leverage: 5x | SL: 1.50% | TP: 3.00%"},
    {"start_time": "2026-08-10 13:30:28", "duration": "40.9 s", "status": "ERROR",
     "details": "Advanced Analysis failed (API error). Fallback applied."},
]
import gui.auto_trading_panel as auto_mod
auto_mod.load_autotrading_logs = lambda: sample_logs
auto_panel._refresh_logs_ui()
auto_panel._status("Active. Waiting for next cycle...")
auto_panel._countdown_lbl.configure(text="Next run in 8m 12s")

# ─────────────────────────────────────────────────────────────
# 2. Portfolio — sample balance + open positions
#
# __init__ already kicked off an async "_update_portfolio_view" that queues a
# real (empty, no exchange credentials) refresh; drain it first or it would
# overwrite our sample data a moment after mainloop starts.
# ─────────────────────────────────────────────────────────────
port_panel = app._portfolio_panel
try:
    while True:
        port_panel._queue.get_nowait()
except Exception:
    pass

sample_balance = {"total": 12480.32, "available": 3120.55, "currency": "USDT"}
sample_positions = [
    {"asset": "BTC", "type": "Futures", "direction": "LONG", "leverage": "8x",
     "quantity": 0.0421, "avg_price": 64230.10, "value": 2704.89,
     "sl": 63400.0, "tp": 66500.0, "pnl": 118.42, "pnl_pct": 4.38},
    {"asset": "ETH", "type": "Futures", "direction": "SHORT", "leverage": "5x",
     "quantity": 1.850, "avg_price": 3180.25, "value": 5883.46,
     "sl": 3260.0, "tp": 3010.0, "pnl": -42.10, "pnl_pct": -0.71},
    {"asset": "USDT", "type": "Spot", "direction": "LONG", "leverage": "1x",
     "quantity": 3892.0, "avg_price": 1.0, "value": 3892.0,
     "sl": "N/A", "tp": "N/A", "pnl": 0.0, "pnl_pct": 0.0},
]
port_panel._refresh_portfolio_ui(sample_balance, sample_positions)

# ─────────────────────────────────────────────────────────────
# 3. Markets — sample BTC price row
# ─────────────────────────────────────────────────────────────
markets_panel = app._markets_panel
sample_market_list = [{
    "symbol": "BTC", "name": "Bitcoin", "current_price": 64230.10,
    "price_change_pct": 1.87, "updated_at": "10/08/2026 14:15:00",
}]
markets_panel._loaded_lists["crypto"] = sample_market_list
markets_panel._populate_list("crypto", sample_market_list)
markets_panel._update_status("✅ Current list prices updated successfully!")

# ─────────────────────────────────────────────────────────────
# 4. Pattern Matching — sample KNN history
# ─────────────────────────────────────────────────────────────
pm_panel = app._pm_panel
for matches, conf, target, move, tag in [
    (5, "78.40%", "$64,890.20", "+1.03%", "positive"),
    (5, "61.20%", "$63,910.00", "-0.50%", "negative"),
]:
    pm_panel._update_ui_success(matches, conf, target, move, tag)

# ─────────────────────────────────────────────────────────────
# 5. Time-Series Analysis — sample TimesFM forecast
# ─────────────────────────────────────────────────────────────
sample_forecast = [{
    "rank": 1, "name": "Bitcoin", "symbol": "BTC", "confidence": 82.4,
    "last_price": 64230.10, "target_price_1d": 64890.20, "change_pct_1d": 1.03,
    "run_date": "2026-08-10 14:15:00",
    "expiry_date": "2026-08-10 16:15:00",
}]
app._results_table.populate(sample_forecast)
# _switch_view("ai") calls self._ai_panel.update_timefm_results(self._results),
# so app._results itself must carry the sample data or that call re-blanks the
# AI panel's "Data Unavailable" banner right when we switch to that view.
app._results = sample_forecast
app._update_status(
    "✅ Analysis completed [CRYPTO] — 1 assets analyzed  |  🟢 1 BUY  🔴 0 SELL  |  "
    "Updated: 14:15:32"
)

# ─────────────────────────────────────────────────────────────
# 6. Advanced Analysis (AI) — sample multi-agent session
# ─────────────────────────────────────────────────────────────
sample_session = {
    "session_id": "sample_session",
    "meta": {"market_type": "crypto"},
    "results": [{
        "symbol": "BTC", "name": "Bitcoin", "current_price": 64230.10,
        "target_price_1d": 64890.20, "change_pct_1d": 1.03,
        "ai_change_pct_1d": 0.62, "btc_expected_move": 0.85,
        "confidence": 74, "tfm_confidence": 82.4, "btc_pred_confidence": 78.4,
        "signal_1d": "BUY", "timefm_signal_1d": "BUY",
        "stop_loss": 63400.0, "take_profit": 66500.0,
        "rationale": "Price holding above intraday VWAP with bullish order-book imbalance; backtest confirms positive alpha in the current ALTSEASON-adjacent regime.",
        "key_risk": "A sudden BTC dominance reversal could invalidate the short-term bullish thesis.",
        "analyzed_at": dt.datetime(2026, 8, 10, 14, 15, 0).isoformat(),
        "market_context": {"fng_value": 68, "fng_class": "Greed", "regime": "ALTSEASON"},
        "debug": {},
    }],
}
ai_panel_mod.load_all_sessions = lambda: [sample_session]
app._ai_panel._populate_results_tree()
# update_timefm_results() also clears the "Data Unavailable" warning banner,
# which would otherwise look inconsistent next to a populated results table.
app._ai_panel.update_timefm_results(sample_forecast)
app._ai_panel._status("✅ Analysis completed — 1 assets | 🟢 1 BUY | 🔴 0 SELL")

# ─────────────────────────────────────────────────────────────
# Capture every view
# ─────────────────────────────────────────────────────────────
views = [
    ("autotrading", "01_auto_trading"),
    ("portfolio",   "02_portfolio"),
    ("markets",     "03_markets"),
    ("pm",          "04_pattern_matching"),
    ("temporal",    "05_time_series_analysis"),
    ("ai",          "06_advanced_analysis"),
]
state = {"i": 0}


def step():
    if state["i"] >= len(views):
        app.destroy()
        return
    view, filename = views[state["i"]]
    state["i"] += 1
    app._switch_view(view)
    app.update_idletasks()
    app.update()

    def grab(filename=filename):
        try:
            # Crop to the window's actual bounds instead of shipping the black
            # Xvfb desktop background around it.
            x0, y0 = app.winfo_rootx(), app.winfo_rooty()
            x1, y1 = x0 + app.winfo_width(), y0 + app.winfo_height()
            img = ImageGrab.grab(xdisplay=DISP, bbox=(x0, y0, x1, y1))
            img.save(f"{OUT}/{filename}.png")
            print("shot", filename, img.size)
        except Exception as e:
            print("shot FAILED", filename, e)
        app.after(250, step)

    app.after(600, grab)


app.after(1200, step)
app.mainloop()
print("done")
