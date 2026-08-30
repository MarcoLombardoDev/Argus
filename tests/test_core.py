# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
tests/test_core.py — Argus

Headless regression tests for the non-GUI logic. They never touch the network:
anything that would hit an exchange or an LLM is either avoided or exercised
through its offline entry point.

Run with:  python -m pytest tests/ -q
       or: python tests/test_core.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─────────────────────────────────────────────────────────────
# Imports — a bare import failure is itself a regression
# ─────────────────────────────────────────────────────────────

def test_all_core_modules_import():
    import core.ai_analysis_store  # noqa: F401
    import core.ai_analyst  # noqa: F401
    import core.analyzer  # noqa: F401
    import core.btc_pattern_matcher  # noqa: F401
    import core.data_fetcher  # noqa: F401
    import core.data_manager  # noqa: F401
    import core.forecaster  # noqa: F401
    import core.market_enrichment  # noqa: F401
    import core.portfolio_manager  # noqa: F401
    import core.pre_flight_checker  # noqa: F401


def test_declared_requirements_are_installed():
    """Every third-party module imported by the code must be installable from
    requirements.txt (scikit-learn and beautifulsoup4 used to be missing)."""
    import bs4  # noqa: F401
    import ccxt  # noqa: F401
    import openai  # noqa: F401
    import sklearn  # noqa: F401
    import yfinance  # noqa: F401


# ─────────────────────────────────────────────────────────────
# Ensemble weights
# ─────────────────────────────────────────────────────────────

def test_weights_accept_percentage_form():
    from core.portfolio_manager import normalize_ensemble_weights
    w = normalize_ensemble_weights({"ensemble_w_tfm": 40, "ensemble_w_pm": 40, "ensemble_w_ai": 20})
    assert pytest.approx(sum(w), abs=1e-9) == 1.0
    assert pytest.approx(w[0], abs=1e-9) == 0.4


def test_weights_accept_fraction_form():
    from core.portfolio_manager import normalize_ensemble_weights
    w = normalize_ensemble_weights({"ensemble_w_tfm": 0.4, "ensemble_w_pm": 0.35, "ensemble_w_ai": 0.25})
    assert pytest.approx(sum(w), abs=1e-9) == 1.0
    assert pytest.approx(w[1], abs=1e-9) == 0.35


@pytest.mark.parametrize("settings", [
    {},
    {"ensemble_w_tfm": 0, "ensemble_w_pm": 0, "ensemble_w_ai": 0},
    {"ensemble_w_tfm": None, "ensemble_w_pm": "abc", "ensemble_w_ai": -5},
])
def test_weights_never_degenerate(settings):
    from core.portfolio_manager import normalize_ensemble_weights
    w = normalize_ensemble_weights(settings)
    assert pytest.approx(sum(w), abs=1e-9) == 1.0
    assert all(x >= 0 for x in w)


def test_confidence_actually_moves_expected_return():
    """Regression: weights were read as fractions while stored as percentages, so
    the +/-0.05 confidence adjustments were swamped and had no effect at all."""
    from core.portfolio_manager import PortfolioManager
    pm = PortfolioManager.for_sizing({
        "ensemble_w_tfm": 40, "ensemble_w_pm": 40, "ensemble_w_ai": 20,
        "enable_ai_auto_trade": True, "ensemble_min_return_pct": 0.1,
    })
    kw = dict(tfm_pct=1.0, pm_pct=0.2, ai_pct=0.5, fng_value=50, ai_conf=50.0, tfm_conf=50.0)
    low = pm.calculate_sizing(pm_conf=10.0, **kw)[3]
    high = pm.calculate_sizing(pm_conf=90.0, **kw)[3]
    assert low != high, "pattern-matching confidence must change the ensemble output"
    # Low PM confidence shifts weight away from the (weak) PM leg, so the blended
    # return moves towards the stronger TimesFM leg.
    assert low > high


def test_sizing_signals():
    from core.portfolio_manager import PortfolioManager
    pm = PortfolioManager.for_sizing({"ensemble_min_return_pct": 0.1})

    _, sig, mult, _ = pm.calculate_sizing(1.0, 1.0, 1.0, fng_value=50)
    assert sig == "BUY" and mult > 0

    _, sig, mult, _ = pm.calculate_sizing(-1.0, -1.0, -1.0, fng_value=50)
    assert sig == "SELL" and mult > 0

    _, sig, mult, _ = pm.calculate_sizing(0.001, -0.001, 0.0, fng_value=50)
    assert sig == "HOLD" and mult == 0.0

    # Negative funding must veto a short (short-squeeze guard).
    rule, sig, mult, _ = pm.calculate_sizing(-1.0, -1.0, -1.0, fng_value=50, funding_rate=-0.05)
    assert sig == "HOLD" and mult == 0.0 and rule == "SQUEEZE RISK"


def test_minimum_confidence_gates_orders_and_notifies():
    """Regression: 'Minimum AI Confidence' only scaled the position size — a
    below-threshold signal was still turned into an order, and the
    discarded_callback (used by Auto Trading for its cooldown) was never fired."""
    from core.portfolio_manager import PortfolioManager

    pm = PortfolioManager.for_sizing({
        "ensemble_min_return_pct": 0.1,
        "enable_ai_auto_trade": True,
        "portfolio_manager": {"minimumConfidence": 70.0, "maxOpenPositions": 5,
                              "maxPositionPercent": 20.0, "maxLeverage": 10,
                              "maxCapitalUsagePercent": 100.0},
    })
    pm.get_balance = lambda positions=None: {"available": 10000.0, "total": 10000.0,
                                             "currency": "USDT", "raw": {}}
    pm.get_positions = lambda: []
    pm.get_funding_rate = lambda s: 0.0

    def result(symbol, confidence):
        return {"symbol": symbol, "name": symbol, "current_price": 100.0,
                "last_price": 100.0, "change_pct_1d": 2.0, "btc_expected_move": 2.0,
                "ai_change_pct_1d": 2.0, "confidence": confidence,
                "tfm_confidence": 80.0, "btc_pred_confidence": 80.0,
                "stop_loss": 98.0, "take_profit": 104.0, "market_context": {}}

    discarded = []
    orders = pm.generate_orders(
        [result("LOWC", 40), result("HIGHC", 90)],
        discarded_callback=lambda s, reason: discarded.append((s, reason)),
    )

    assets = {o["asset"] for o in orders}
    assert "HIGHC" in assets, "an above-threshold signal must still produce an order"
    assert "LOWC" not in assets, "a below-threshold signal must be discarded"
    assert ("LOWC", "low_confidence") in discarded


def test_for_sizing_creates_no_exchange():
    from core.portfolio_manager import PortfolioManager
    pm = PortfolioManager.for_sizing({"portfolio_manager": {"exchange_id": "bingx"}})
    assert pm.exchange is None
    assert pm.ensure_markets(timeout=0.1) is False


def test_unknown_exchange_id_is_survivable():
    from core.portfolio_manager import PortfolioManager
    pm = PortfolioManager({"portfolio_manager": {"exchange_id": "definitely_not_an_exchange"}})
    assert pm.exchange is None
    assert pm.get_funding_rate("BTC/USDT") == 0.0
    assert pm.get_positions() == []
    assert pm.get_balance()["total"] == 0.0


# ─────────────────────────────────────────────────────────────
# Analyzer
# ─────────────────────────────────────────────────────────────

def test_build_results_shapes():
    from core.analyzer import build_results
    coins = [{"symbol": "BTC", "name": "Bitcoin", "rank": 1, "current_price": 100.0}]
    forecasts = {"BTC": {"preds": [100.5, 101.0, 102.0], "confidence": 73.4}}
    out = build_results(coins, forecasts, threshold_pct=1.0)
    assert len(out) == 1
    row = out[0]
    assert row["symbol"] == "BTC"
    assert row["target_price_1d"] == 102.0          # last candle of the horizon
    assert pytest.approx(row["change_pct_1d"]) == 2.0
    assert row["confidence"] == 73.4
    assert row["forecast_price"] == row["target_price_1d"]  # legacy alias


def test_build_results_tolerates_missing_forecast():
    from core.analyzer import build_results
    coins = [{"symbol": "BTC", "name": "Bitcoin", "rank": 1, "current_price": 100.0}]
    for forecasts in ({}, {"BTC": None}, {"BTC": {"preds": None}}):
        row = build_results(coins, forecasts)[0]
        assert row["target_price_1d"] is None
        assert row["change_pct_1d"] is None


def test_build_results_zero_price():
    from core.analyzer import build_results
    coins = [{"symbol": "X", "name": "X", "rank": 1, "current_price": 0.0}]
    row = build_results(coins, {"X": {"preds": [1.0], "confidence": 10}})[0]
    assert row["target_price_1d"] is None


def test_formatters():
    from core.analyzer import format_change_pct, format_price
    assert format_price(None) == "N/A"
    assert format_price(12345.678) == "$12,345.68"
    assert format_price(0.00001234).startswith("$0.0000")
    assert format_change_pct(None) == "N/A"
    assert format_change_pct(1.5) == "+1.50%"
    assert format_change_pct(-1.5) == "-1.50%"


def test_formatters_tolerate_non_numeric_input():
    """Regression: values reloaded from CSV arrive as strings and
    format_price("65000.0") raised TypeError while rendering the results table."""
    from core.analyzer import format_change_pct, format_price
    assert format_price("65000.0") == "$65,000.00"
    assert format_change_pct("-1.5") == "-1.50%"
    assert format_change_pct("+1,5%") == "+1.50%"
    for bad in ("N/A", "DISABLED", "", float("nan"), object()):
        assert format_price(bad) == "N/A"
        assert format_change_pct(bad) == "N/A"
    # Negative prices must pick the precision bucket by magnitude.
    assert format_price(-12345.678) == "$-12,345.68"


def test_verify_past_forecasts_survives_missing_history(monkeypatch, tmp_path):
    """Regression: load_historical() raises ValueError for a stale/absent cache,
    which aborted the whole verification report."""
    import core.analyzer as analyzer
    import core.data_manager as dm

    hist = tmp_path / "forecast_history.csv"
    pd.DataFrame([{
        "rank": 1, "name": "Bitcoin", "symbol": "BTC",
        "run_date": "2026-01-01 00:00:00", "expiry_date": "2026-01-01 02:00:00",
        "last_price": 100.0, "forecast_price": 101.0, "change_pct": 1.0,
        "signal": "BUY", "horizon_days": 1,
    }]).to_csv(hist, index=False)

    monkeypatch.setattr(dm, "FORECAST_HISTORY_PATH", hist)
    monkeypatch.setattr(dm, "load_historical",
                        lambda s: (_ for _ in ()).throw(ValueError("stale")))

    out = analyzer.verify_past_forecasts()
    assert len(out) == 1
    assert out[0]["status"] == "N/A"


# ─────────────────────────────────────────────────────────────
# AI analyst helpers
# ─────────────────────────────────────────────────────────────

def test_regime_bias_maps_real_labels():
    from core.ai_analyst import _regime_bias
    assert _regime_bias("ALTSEASON") == "BULLISH"
    assert _regime_bias("BTC_ACCUMULATION") == "BULLISH"
    assert _regime_bias("CRYPTO_WINTER / BEARISH") == "BEARISH"
    assert _regime_bias("UNKNOWN") == "UNKNOWN"
    assert _regime_bias("") == "UNKNOWN"
    assert _regime_bias(None) == "UNKNOWN"


def test_market_context_fallback_keeps_the_full_key_set(monkeypatch):
    """Regression: the error path omitted fng_value/fng_class, and threw away a
    Fear & Greed reading that had already been fetched successfully."""
    import core.market_enrichment as me

    class _Resp:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"data": [{"value": "72", "value_classification": "Greed"}]}

    monkeypatch.setattr(me.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(me.yf, "download",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))

    ctx = me.get_market_context("BTC")
    assert ctx["regime"] == "UNKNOWN"
    assert ctx["fng_value"] == 72            # real reading, not a hardcoded 50
    assert ctx["fng_class"] == "Greed"
    assert {"benchmark", "regime", "correlation", "fng_value", "fng_class", "summary"} <= set(ctx)


def test_rss_title_regex_is_valid():
    """Regression: the CDATA pattern was unescaped and raised re.error, silently
    disabling the Investing.com RSS fallback."""
    import re

    import core.ai_analyst as aa
    src = Path(aa.__file__).read_text(encoding="utf-8")
    assert r"<title><!\[CDATA\[" in src, "CDATA brackets must be escaped"
    got = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", re.DOTALL and
                     "<title><![CDATA[Bitcoin rallies]]></title>", re.DOTALL)
    assert got == ["Bitcoin rallies"]


def test_decision_json_parsing():
    from core.ai_analyst import AIAnalyst
    a = AIAnalyst.__new__(AIAnalyst)
    coin = {"last_price": 100.0}

    clean = a._parse_decision_json(
        '```json\n{"target_price_2h": 101.5, "change_pct_2h": 1.5, "confidence": 70,'
        ' "stop_loss": 99.0, "take_profit": 103.0, "rationale": "ok", "key_risk": "vol"}\n```',
        coin)
    assert clean["target_price_1d"] == 101.5
    assert clean["change_pct_1d"] == 1.5
    assert clean["confidence"] == 70

    # Trailing comma + currency symbols + comma decimals must still parse.
    messy = a._parse_decision_json(
        'Sure!\n{"target_price_2h": "$101,5", "change_pct_2h": "+1,5%", "confidence": "70%",'
        ' "stop_loss": "$99.0", "take_profit": "$103.0", "rationale": "r", "key_risk": "k",}',
        coin)
    assert messy["target_price_1d"] == 101.5
    assert messy["confidence"] == 70

    # Total garbage must fall back to the current price rather than raise.
    junk = a._parse_decision_json("the model refused to answer", coin)
    assert junk["target_price_1d"] == 100.0
    assert junk["rationale"]


def test_describe_span_labels_the_real_window():
    """The backtest header used to claim a fixed '6 months' / '30 days' while
    actually running over whatever 15m history the Markets panel had cached."""
    from core.ai_analyst import _describe_span
    def mk(n, freq="15min"):
        return pd.date_range("2026-01-01", periods=n, freq=freq)
    assert "days" in _describe_span(mk(96 * 10))          # ~10 days
    assert "months" in _describe_span(mk(96 * 90))        # ~3 months
    assert "years" in _describe_span(mk(96 * 400))        # >1 year
    assert _describe_span([]) == "local 15m history"      # never raises


def test_safe_float_helper():
    from core.ai_analyst import _safe_float
    assert _safe_float(None, 5.0) == 5.0
    assert _safe_float("N/A", 5.0) == 5.0
    assert _safe_float("DISABLED", 5.0) == 5.0
    assert _safe_float(float("nan"), 5.0) == 5.0
    assert _safe_float("1,5") == 1.5
    assert _safe_float("42%") == 42.0
    assert _safe_float(7) == 7.0


# ─────────────────────────────────────────────────────────────
# Backtest engine (in-house replacement for vectorbt)
# ─────────────────────────────────────────────────────────────

def test_backtest_buy_and_hold_matches_price_move():
    """With no costs, holding from first to last bar must reproduce the price
    return exactly."""
    from core.backtest import run_signal_backtest
    close = pd.Series([100.0, 110.0, 120.0, 130.0])
    r = run_signal_backtest(close, [True, False, False, False], [False] * 4,
                            fees=0.0, slippage=0.0)
    assert r.total_return == pytest.approx(0.30)
    assert r.final_value == pytest.approx(13000.0)


def test_backtest_applies_fees_and_slippage_exactly():
    """Hand-computed round trip: buy at 100, sell at 110, 1% fee, 1% slippage."""
    from core.backtest import run_signal_backtest
    r = run_signal_backtest(pd.Series([100.0, 110.0]), [True, False], [False, True],
                            fees=0.01, slippage=0.01)
    fill_in = 100 * 1.01
    qty = 10_000 / (fill_in * 1.01)
    expected = qty * (110 * 0.99) * 0.99
    assert r.final_value == pytest.approx(expected)
    assert r.trades_count == 1
    # Costs must make it strictly worse than the frictionless case.
    free = run_signal_backtest(pd.Series([100.0, 110.0]), [True, False], [False, True],
                               fees=0.0, slippage=0.0)
    assert r.final_value < free.final_value


def test_backtest_stop_loss_caps_the_loss():
    from core.backtest import run_signal_backtest
    # -10% on bar 2, then a huge rally the stopped-out position must NOT capture.
    close = pd.Series([100.0, 100.0, 90.0, 200.0])
    r = run_signal_backtest(close, [True, False, False, False], [False] * 4,
                            fees=0.0, slippage=0.0, sl_stop=0.05)
    assert r.total_return == pytest.approx(-0.10)
    assert r.trades_count == 1


def test_backtest_take_profit_locks_the_gain():
    from core.backtest import run_signal_backtest
    # +10% on bar 2, then a crash the closed position must NOT suffer.
    close = pd.Series([100.0, 100.0, 110.0, 50.0])
    r = run_signal_backtest(close, [True, False, False, False], [False] * 4,
                            fees=0.0, slippage=0.0, tp_stop=0.05)
    assert r.total_return == pytest.approx(0.10)


def test_backtest_short_profits_when_price_falls():
    from core.backtest import run_signal_backtest
    close = pd.Series([100.0, 100.0, 90.0])
    r = run_signal_backtest(close, [False, False, False], [False, True, False],
                            allow_short=True, fees=0.0, slippage=0.0)
    assert r.total_return == pytest.approx(0.10)
    # Without allow_short the same signals must do nothing at all.
    flat = run_signal_backtest(close, [False, False, False], [False, True, False],
                               allow_short=False, fees=0.0, slippage=0.0)
    assert flat.total_return == pytest.approx(0.0)


def test_backtest_max_drawdown_is_positive_peak_to_trough():
    from core.backtest import run_signal_backtest
    close = pd.Series([100.0, 150.0, 75.0, 80.0])
    r = run_signal_backtest(close, [True, False, False, False], [False] * 4,
                            fees=0.0, slippage=0.0)
    assert r.max_drawdown == pytest.approx(0.5)   # 150 -> 75
    assert r.max_drawdown >= 0


def test_backtest_ambiguous_and_degenerate_inputs():
    from core.backtest import run_signal_backtest
    # Entry and exit on the same bar cancel out rather than raising.
    r = run_signal_backtest(pd.Series([100.0, 110.0]), [True, True], [True, True],
                            fees=0.0, slippage=0.0)
    assert r.trades_count == 0
    assert r.total_return == pytest.approx(0.0)

    # Too few points: metrics degrade, nothing raises.
    empty = run_signal_backtest(pd.Series([], dtype=float), [], [])
    assert empty.trades_count == 0
    assert empty.final_value == pytest.approx(10_000.0)

    # NaNs in the price series are dropped, not propagated into the result.
    nan_series = pd.Series([100.0, float("nan"), 110.0])
    r2 = run_signal_backtest(nan_series, [True, False, False], [False, False, True],
                             fees=0.0, slippage=0.0)
    assert np.isfinite(r2.final_value)


def test_backtest_sharpe_is_nan_on_flat_equity():
    """A never-traded account has zero variance; Sharpe must be nan, not inf."""
    from core.backtest import run_signal_backtest
    r = run_signal_backtest(pd.Series([100.0] * 50), [False] * 50, [False] * 50)
    assert np.isnan(r.sharpe_ratio)


def test_no_commons_clause_dependency_remains():
    """Regression: vectorbt is Apache-2.0 + Commons Clause, which forbids selling
    software deriving substantially from it and blocks Argus's dual licensing."""
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in list((root / "core").glob("*.py")) + list((root / "gui").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("*"):
                continue          # explanatory comments may name it
            if "import vectorbt" in line or "vbt." in line:
                offenders.append(f"{path.name}:{lineno}")
    assert not offenders, f"vectorbt is back in: {offenders}"

    # Check declared dependencies only — the explanatory comment names it on purpose.
    req_lines = [
        line.strip()
        for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not [line for line in req_lines if "vectorbt" in line], \
        "vectorbt reintroduced into requirements.txt"


# ─────────────────────────────────────────────────────────────
# Pattern matcher
# ─────────────────────────────────────────────────────────────

def test_normalize_is_zscore_and_handles_flat_input():
    from core.btc_pattern_matcher import BTCPatternMatcher
    out = BTCPatternMatcher._normalize(np.array([1.0, 2.0, 3.0]))
    assert pytest.approx(out.mean(), abs=1e-12) == 0.0
    assert pytest.approx(out.std(), abs=1e-12) == 1.0
    # A constant window has zero variance — must not produce NaN/inf.
    flat = BTCPatternMatcher._normalize(np.array([5.0, 5.0, 5.0]))
    assert np.all(flat == 0.0)
    assert BTCPatternMatcher._normalize(np.array([])).size == 0


def test_empty_result_has_the_full_key_set():
    from core.btc_pattern_matcher import BTCPatternMatcher
    m = BTCPatternMatcher.__new__(BTCPatternMatcher)
    keys = set(m._empty_result())
    assert {"btc_pred_confidence", "btc_expected_move", "matches_count",
            "btc_current_price", "btc_target_price"} <= keys


def test_pattern_matcher_end_to_end_on_synthetic_prices(monkeypatch):
    import core.data_manager as dm
    from core.btc_pattern_matcher import BTCPatternMatcher

    rng = np.random.default_rng(0)
    n = 800
    prices = 30000 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    df = pd.DataFrame({"Open": prices, "High": prices, "Low": prices,
                       "Close": prices, "Volume": 1.0}, index=idx)

    monkeypatch.setattr(dm, "load_historical", lambda s: df)
    res = BTCPatternMatcher().run_analysis(n_neighbors=5)

    assert res["matches_count"] == 5
    assert 0.0 <= res["btc_pred_confidence"] <= 100.0
    assert res["btc_current_price"] > 0
    assert res["btc_target_price"] > 0
    assert np.isfinite(res["btc_expected_move"])


def test_pattern_matcher_returns_empty_when_history_is_stale(monkeypatch):
    import core.data_manager as dm
    from core.btc_pattern_matcher import BTCPatternMatcher
    monkeypatch.setattr(dm, "load_historical",
                        lambda s: (_ for _ in ()).throw(ValueError("obsolete")))
    res = BTCPatternMatcher().run_analysis(n_neighbors=5)
    assert res["matches_count"] == 0


# ─────────────────────────────────────────────────────────────
# Data manager
# ─────────────────────────────────────────────────────────────

def test_historical_staleness_uses_utc(monkeypatch, tmp_path):
    import core.data_manager as dm
    monkeypatch.setattr(dm, "HISTORICAL_DIR", tmp_path)

    fresh_end = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    idx = pd.date_range(end=fresh_end, periods=5, freq="15min")
    dm.save_historical("FRESH", pd.DataFrame({"Close": [1, 2, 3, 4, 5]}, index=idx))
    assert dm.load_historical("FRESH") is not None

    old_end = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    idx = pd.date_range(end=old_end, periods=5, freq="15min")
    dm.save_historical("STALE", pd.DataFrame({"Close": [1, 2, 3, 4, 5]}, index=idx))
    with pytest.raises(ValueError):
        dm.load_historical("STALE")

    with pytest.raises(ValueError):
        dm.load_historical("NEVER_SAVED")


def test_historical_staleness_with_tz_aware_index(monkeypatch, tmp_path):
    """A tz-aware index must be converted to UTC, not merely stripped: stripping
    keeps the local wall time and skews the age by the UTC offset."""
    import core.data_manager as dm
    monkeypatch.setattr(dm, "HISTORICAL_DIR", tmp_path)

    end = datetime.now(timezone.utc) - timedelta(minutes=10)
    idx = pd.date_range(end=end, periods=5, freq="15min", tz="UTC").tz_convert("Asia/Tokyo")
    dm.save_historical("TZ", pd.DataFrame({"Close": [1, 2, 3, 4, 5]}, index=idx))
    assert dm.load_historical("TZ") is not None


def test_settings_round_trip_keeps_secrets_out_of_json(monkeypatch, tmp_path):
    import core.data_manager as dm
    monkeypatch.setattr(dm, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(dm, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(dm, "HISTORICAL_DIR", tmp_path / "data" / "historical")
    monkeypatch.setattr(dm, "AI_ANALYSIS_DIR", tmp_path / "data" / "ai")
    monkeypatch.setattr(dm, "MARKET_LISTS_DIR", tmp_path / "data" / "lists")
    monkeypatch.setattr(dm, "BASE_DIR", tmp_path)

    dm.save_settings({"ai_api_key": "sk-secret", "backend": "cpu",
                      "portfolio_manager": {"api_key": "k", "api_secret": "s"}})

    on_disk = json.loads((tmp_path / "settings.json").read_text())
    assert on_disk["ai_api_key"] == ""            # secret redacted from JSON
    assert on_disk["portfolio_manager"]["api_secret"] == ""
    assert on_disk["backend"] == "cpu"
    assert "sk-secret" in (tmp_path / ".env").read_text()


def test_settings_template_is_valid_and_documented():
    """The template must stay loadable and must not introduce keys the code does
    not know about — the README documents the two side by side."""
    import core.data_manager as dm

    template_path = Path(dm.__file__).resolve().parent.parent / "config" / "settings.template.json"
    assert template_path.exists(), "config/settings.template.json is missing"

    template = json.loads(template_path.read_text(encoding="utf-8"))
    defaults = dm.DEFAULT_SETTINGS

    unknown = sorted(set(template) - set(defaults))
    assert not unknown, f"template has keys absent from DEFAULT_SETTINGS: {unknown}"

    for section in ("portfolio_manager", "auto_trading"):
        unknown_sub = sorted(set(template.get(section, {})) - set(defaults[section]))
        assert not unknown_sub, f"template.{section} has unknown keys: {unknown_sub}"

    # The template is the conservative starting point: it must never ship with
    # live order execution enabled.
    assert template["portfolio_manager"]["useExchangeBalance"] is False
    # ...nor with credentials baked in.
    assert template["portfolio_manager"]["api_key"] == ""
    assert template["portfolio_manager"]["api_secret"] == ""
    for secret in ("hf_token", "ai_api_key", "coingecko_api_key",
                   "ai_finnhub_key", "ai_coingecko_key"):
        assert template.get(secret, "") == "", f"template leaks a value for {secret}"


def test_market_list_round_trip(monkeypatch, tmp_path):
    import core.data_manager as dm
    monkeypatch.setattr(dm, "MARKET_LISTS_DIR", tmp_path)
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "HISTORICAL_DIR", tmp_path / "h")
    monkeypatch.setattr(dm, "AI_ANALYSIS_DIR", tmp_path / "a")
    monkeypatch.setattr(dm, "BASE_DIR", tmp_path)

    dm.save_market_list("crypto", [{"symbol": "BTC", "name": "Bitcoin", "current_price": 1.0}])
    got = dm.load_market_list("crypto")
    assert got and got[0]["symbol"] == "BTC"
    assert dm.load_market_list("nonexistent-market")[0]["symbol"] == "BTC"  # safe default


# ─────────────────────────────────────────────────────────────
# Pre-flight checker
# ─────────────────────────────────────────────────────────────

class _FakeExchange:
    def __init__(self, last, bids, asks):
        self._last, self._bids, self._asks = last, bids, asks

    def fetch_ticker(self, symbol):
        return {"last": self._last}

    def fetch_order_book(self, symbol, limit=20):
        return {"bids": self._bids, "asks": self._asks}


def test_preflight_passes_and_realigns_levels():
    from core.pre_flight_checker import PreFlightChecker
    order = {"current_price": 100.0, "stopLoss": 98.0, "takeProfit": 104.0, "direction": "LONG"}
    ex = _FakeExchange(101.0, [[100, 10]] * 5, [[102, 10]] * 5)
    ok, reason = PreFlightChecker.run_checks(order, ex, "BTC/USDT:USDT", {})
    assert ok, reason
    assert order["current_price"] == 101.0
    assert order["stopLoss"] == pytest.approx(101.0 * 0.98)
    assert order["takeProfit"] == pytest.approx(101.0 * 1.04)


def test_preflight_blocks_on_drift():
    from core.pre_flight_checker import PreFlightChecker
    order = {"current_price": 100.0, "stopLoss": 98.0, "takeProfit": 104.0, "direction": "LONG"}
    ex = _FakeExchange(103.5, [[100, 10]], [[104, 10]])   # 87% of the way to target
    ok, reason = PreFlightChecker.run_checks(
        order, ex, "BTC/USDT:USDT", {"portfolio_manager": {"pre_flight_drift_threshold": 50.0}})
    assert not ok and "Drift" in reason


def test_preflight_blocks_on_orderbook_imbalance():
    from core.pre_flight_checker import PreFlightChecker
    order = {"current_price": 100.0, "stopLoss": 98.0, "takeProfit": 104.0, "direction": "LONG"}
    ex = _FakeExchange(100.0, [[100, 1]], [[101, 99]])    # 99% ask pressure
    ok, reason = PreFlightChecker.run_checks(
        order, ex, "BTC/USDT:USDT", {"portfolio_manager": {"pre_flight_imbalance_threshold": 60.0}})
    assert not ok and "Flash OB" in reason


def test_preflight_reports_runtime_errors():
    from core.pre_flight_checker import PreFlightChecker

    class Boom:
        def fetch_ticker(self, s):
            raise RuntimeError("network down")

    ok, reason = PreFlightChecker.run_checks({"direction": "LONG"}, Boom(), "X", {})
    assert not ok and "Pre-Flight runtime error" in reason


# ─────────────────────────────────────────────────────────────
# Order-book imbalance
# ─────────────────────────────────────────────────────────────

def test_order_book_imbalance_handles_extra_level_fields():
    from core.data_fetcher import fetch_order_book_imbalance

    class Ex:
        markets = {"BTC/USDT": {}}
        # some venues return [price, amount, order_count]
        def fetch_order_book(self, sym, limit=20):
            return {"bids": [[100.0, 3.0, 7]], "asks": [[101.0, 1.0, 2]]}

    val = fetch_order_book_imbalance(Ex(), "BTC")
    assert val is not None and val > 0          # bid-heavy
    assert fetch_order_book_imbalance(None, "BTC") is None


# ─────────────────────────────────────────────────────────────
# AI analysis store / exports
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def store(monkeypatch, tmp_path):
    import core.ai_analysis_store as st
    monkeypatch.setattr(st, "AI_ANALYSIS_DIR", tmp_path)
    return st


def _sentinel_results():
    """The row shapes that used to crash exports with ValueError."""
    return [
        {"name": "Bitcoin", "symbol": "BTC", "current_price": 65000.0,
         "target_price_1d": 65500.0, "change_pct_1d": 0.77, "ai_change_pct_1d": "N/A",
         "signal_1d": "BUY", "timefm_signal_1d": "BUY", "confidence": "DISABLED",
         "tfm_confidence": None, "btc_pred_confidence": "N/A", "btc_expected_move": 0.3,
         "stop_loss": 64000.0, "take_profit": 66500.0, "market_context": None,
         "rationale": "x" * 200, "key_risk": "vol",
         "analyzed_at": "2026-08-05T10:00:00"},
        {"name": "Bitcoin", "symbol": "BTC", "current_price": None,
         "signal_1d": "SELL", "confidence": 42, "stop_loss": None, "take_profit": None,
         "market_context": {"fng_value": 72}, "rationale": None,
         "analyzed_at": "2026-08-05T11:00:00"},
    ]


def test_export_all_formats_with_sentinel_values(store, tmp_path):
    sid = store.save_ai_session(_sentinel_results(), meta={"ai_provider": "openrouter"})
    assert sid

    for name, fn in (("csv", store.export_session_csv),
                     ("xlsx", store.export_session_excel),
                     ("pdf", store.export_session_pdf)):
        out = tmp_path / f"out.{name}"
        assert fn(sid, str(out)) is True, f"{name} export failed"
        assert out.stat().st_size > 0


def test_pdf_leverage_does_not_leak_between_rows(store):
    """Regression: `leverage` was min()'d in place inside the row loop, so one
    tight stop-loss permanently shrank the leverage of every later row."""
    from core.ai_analysis_store import _row_leverage
    assert _row_leverage(30, 100.0, 99.0) == 30      # 1% SL -> cap 80 -> keeps 30
    assert _row_leverage(30, 100.0, 90.0) == 8       # 10% SL -> cap 8
    assert _row_leverage(30, 100.0, None) == 30      # next row unaffected
    assert _row_leverage(30, 100.0, "N/A") == 30
    assert _row_leverage(0, 100.0, None) == 1        # never below 1


def test_roi_cell_direction_and_sentinels():
    from core.ai_analysis_store import _roi_cell
    assert _roi_cell(None, 100.0, "BUY", 1) == "N/A"
    assert _roi_cell(110.0, 0.0, "BUY", 1) == "N/A"
    assert _roi_cell("N/A", 100.0, "BUY", 1) == "N/A"
    assert "+10.00%" in _roi_cell(110.0, 100.0, "BUY", 1)
    assert "-10.00%" in _roi_cell(110.0, 100.0, "SELL", 1)
    assert "+100.00%" in _roi_cell(110.0, 100.0, "BUY", 10)   # leverage applied


def test_delete_analysis_removes_every_row_for_the_symbol(store):
    sid = store.save_ai_session(_sentinel_results())          # two BTC rows
    assert store.delete_analysis(sid, "NOPE") is False        # unknown symbol -> no-op
    assert store.delete_analysis(sid, "BTC") is True
    # Both rows were BTC, so the session is now empty and is removed entirely.
    assert store.load_session(sid) is None
    assert store.delete_session(sid) is False                 # already gone


def test_delete_analysis_keeps_other_symbols(store):
    rows = _sentinel_results()
    rows[1] = dict(rows[1], symbol="ETH", name="Ethereum")
    sid = store.save_ai_session(rows)
    assert store.delete_analysis(sid, "BTC") is True
    session = store.load_session(sid)
    assert session is not None
    assert [r["symbol"] for r in session["results"]] == ["ETH"]
    assert session["n_crypto"] == 1
    assert store.delete_session(sid) is True
    assert store.load_session(sid) is None


# ─────────────────────────────────────────────────────────────
# Forecaster (no model download — structural checks only)
# ─────────────────────────────────────────────────────────────

def test_forecaster_refuses_to_run_without_a_model():
    from core.forecaster import MIN_CONTEXT_POINTS, CryptoForecaster
    f = CryptoForecaster()
    assert f._model_loaded is False
    df = pd.DataFrame({"Close": np.arange(MIN_CONTEXT_POINTS + 10, dtype=float)})
    assert f.forecast("BTC", df) is None
    assert f.forecast_batch({"BTC": df}) == {}


def test_forecaster_atr_fallback():
    from core.forecaster import CryptoForecaster
    f = CryptoForecaster()
    # Not enough rows -> 1.5% of price fallback.
    assert f._calculate_atr(pd.DataFrame({"Close": [1.0]}), 200.0) == pytest.approx(3.0)
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 1, 40))
    df = pd.DataFrame({"High": close + 1, "Low": close - 1, "Close": close})
    atr = f._calculate_atr(df, 100.0)
    assert atr > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
