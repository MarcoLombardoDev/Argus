"""
tests/test_gui_smoke.py — Argus

Boots the real Tk application head-less (Xvfb) and drives the navigation and the
table-rendering paths. These are the code paths that used to raise TclError /
ValueError / NameError only at runtime, where no unit test would catch them.

Skipped automatically when there is no display or no tkinter.

Run with:  xvfb-run -a python -m pytest tests/ -q
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

tk = pytest.importorskip("tkinter", reason="tkinter is not installed (apt install python3-tk)")
pytest.importorskip("customtkinter")

if not os.environ.get("DISPLAY"):
    pytest.skip("no X display — run under xvfb-run", allow_module_level=True)


@pytest.fixture(scope="module")
def app():
    from gui.app import ArgusApp
    application = ArgusApp()
    application.update()          # force a full geometry/render pass
    yield application
    try:
        application.destroy()
    except Exception:
        pass


def test_app_builds_and_maximises(app):
    """Regression: __init__ called self.state("zoomed"), which only exists on
    Windows and raised TclError on X11/macOS."""
    assert app.winfo_exists()
    app._maximize()               # must not raise on any platform
    app.update()


def test_every_view_can_be_shown(app):
    for view in ("autotrading", "portfolio", "markets", "pm", "temporal", "ai"):
        app._switch_view(view)
        app.update()
        assert app._active_view == view


def test_results_table_renders_mixed_quality_rows(app):
    """Confidence and change% arrive as floats, CSV strings, None and sentinels."""
    rows = [
        {"rank": 1, "name": "Bitcoin", "symbol": "BTC", "confidence": 73.5,
         "last_price": 65000.0, "target_price_1d": 65500.0, "change_pct_1d": 0.77,
         "expiry_date": "2026-08-05 12:00:00", "run_date": "2026-08-05 10:00:00"},
        {"rank": 2, "name": "NoData", "symbol": "ND", "confidence": None,
         "last_price": None, "target_price_1d": None, "change_pct_1d": None,
         "expiry_date": "", "run_date": "2026-08-05 10:00:00"},
        {"rank": 3, "name": "Sentinel", "symbol": "SN", "confidence": "DISABLED",
         "last_price": "65000.0", "target_price_1d": "64000.0", "change_pct_1d": "-1.5",
         "expiry_date": "not-a-date", "run_date": "2026-08-05 10:00:00"},
    ]
    app._results_table.populate(rows)
    app.update()
    assert len(app._results_table._tree.get_children()) == 3

    # Sorting on every column must not raise regardless of the mixed types.
    for col, *_ in app._results_table._tree["columns"], :
        pass
    for col in ("name", "symbol", "confidence", "last_price", "change_pct_1d"):
        app._results_table._sort_by(col)
        app.update()

    app._results_table.clear()
    app.update()
    assert app._results_table._tree.get_children() == ()


def test_done_message_updates_status(app):
    app._post(type="done", results=[
        {"rank": 1, "name": "Bitcoin", "symbol": "BTC", "signal": "BUY",
         "confidence": 60.0, "last_price": 1.0, "target_price_1d": 1.1,
         "change_pct_1d": 10.0, "expiry_date": "", "run_date": "2026-08-05 10:00:00"},
    ])
    app._poll_queue()
    app.update()
    assert "Analysis completed" in app._status_label.cget("text")


def test_ai_panel_results_tree_populates(app):
    app._ai_panel._populate_results_tree()
    app.update()
    assert app._ai_panel._res_tree.get_children() is not None


def test_ai_panel_selection_tree_helper_is_importable(app):
    """Regression: _populate_selection_tree used pd.to_datetime while pandas was
    never imported in the module (latent NameError)."""
    import gui.ai_analysis_panel as panel
    assert hasattr(panel, "pd")


def test_pattern_matching_panel_history_renders(app):
    assert app._pm_panel._tree.winfo_exists()


def test_portfolio_panel_sell_reads_quantity_not_leverage(app, monkeypatch):
    """Regression: the sell handler indexed the tree's *leverage* column and did
    float("10.0x") -> ValueError. It now reads the position records directly."""
    panel = app._portfolio_panel
    positions = [{
        "asset": "BTC", "fullname": "Bitcoin", "type": "Futures", "direction": "LONG",
        "leverage": "10.0x", "quantity": 0.25, "value": 16000.0,
        "avg_price": 64000.0, "current_price": 65000.0, "pnl": 250.0, "pnl_pct": 1.5,
        "sl": "63000", "tp": "67000",
    }]
    panel._refresh_portfolio_ui({"total": 20000.0, "available": 4000.0, "currency": "USDT"},
                                positions)
    app.update()

    captured = {}
    monkeypatch.setattr(panel.pm, "sell_portfolio_assets",
                        lambda items: captured.setdefault("items", items) or [])
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    panel._port_selected_iids = {"0"}
    panel._sell_selected_portfolio()

    import time
    for _ in range(50):
        if "items" in captured:
            break
        time.sleep(0.02)

    assert captured.get("items"), "sell was never dispatched"
    item = captured["items"][0]
    assert item["quantity"] == 0.25          # quantity, NOT the "10.0x" leverage
    assert item["asset"] == "BTC"
    assert item["direction"] == "LONG"       # needed to close the right side


def test_portfolio_error_path_reports_instead_of_raising(app, monkeypatch):
    """Regression: the error lambda closed over the `except ... as e` variable,
    which Python unbinds when the block exits -> NameError inside the GUI queue."""
    import time
    panel = app._portfolio_panel

    def boom():
        raise RuntimeError("exchange unreachable")

    monkeypatch.setattr(panel.pm, "get_positions", boom)
    panel._is_updating = False
    panel._update_portfolio_view()

    for _ in range(100):
        app.update()
        if "Error updating portfolio" in panel._status_lbl.cget("text"):
            break
        time.sleep(0.02)

    assert "exchange unreachable" in panel._status_lbl.cget("text")


def test_pattern_matching_error_path_reports_instead_of_raising(app, monkeypatch):
    """Same `except ... as e` closure bug in the Pattern Matching worker."""
    import time
    import gui.pattern_matching_panel as pmp
    panel = app._pm_panel

    class Boom:
        def run_analysis(self):
            raise RuntimeError("no local BTC history")

    monkeypatch.setattr(pmp, "BTCPatternMatcher", lambda *a, **k: Boom())
    panel._run_bg()

    for _ in range(100):
        app.update()
        if "Error" in panel.status_label.cget("text"):
            break
        time.sleep(0.02)

    assert "no local BTC history" in panel.status_label.cget("text")


def test_auto_trading_scheduler_survives_the_weekend_branch(app):
    """Regression: the weekend branch returned before rescheduling, permanently
    killing the 1s scheduler tick."""
    import datetime as dt
    panel = app._auto_trading_panel
    panel.is_running = True
    panel.stop_requested = False
    panel.settings.setdefault("auto_trading", {})["run_weekend"] = False
    panel.last_candle_close_run = None

    saturday = dt.datetime(2026, 8, 8, 12, 0, 30)   # a Saturday, past the trigger
    real_datetime = dt.datetime

    class FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return saturday

    dt.datetime = FrozenDatetime
    try:
        panel._scheduler_tick()
    finally:
        dt.datetime = real_datetime

    assert panel.is_running is True                       # not torn down
    assert panel.last_candle_close_run is not None        # candle consumed
    assert "weekend" in panel._countdown_lbl.cget("text").lower()

    panel.is_running = False
    panel.settings["auto_trading"]["run_weekend"] = True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
