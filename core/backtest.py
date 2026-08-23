# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
backtest.py — Argus

A small, dependency-free vectorised-signal backtester.

This exists to replace `vectorbt`, which ships under Apache-2.0 **plus the
Commons Clause** — a condition that withholds the right to sell software whose
value derives substantially from it, and which is incompatible with Argus's
dual-licensing model (see COMMERCIAL-LICENSE.md). Every published vectorbt release
carries the clause, so pinning an older version was not an option.

Only the surface Argus actually used is reimplemented here: a long-only or
stop-and-reverse long/short strategy driven by boolean entry/exit signals, with
proportional fees, slippage and percentage stop-loss / take-profit, reporting
total return, max drawdown, annualised Sharpe and a trade count.

Deliberate modelling choices, stated so the numbers are interpretable:

* **Close-to-close.** Orders fill at the bar's close, adjusted for slippage.
  Stops are evaluated against the close too, never against intrabar highs or
  lows — Argus feeds this engine a close-price series only, so an intrabar fill
  would be invented precision. Real stops would trigger earlier and at worse
  prices; treat drawdowns here as optimistic.
* **No lookahead.** A signal on bar *i* is acted on at bar *i*'s close, using
  only information available up to and including that bar.
* **Full-equity sizing.** Each position commits the whole account at 1x. There
  is no leverage, no partial sizing and no pyramiding.
* **Stops are checked before signals** within a bar.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# 15-minute bars on a 24/7 crypto market: 4 per hour * 24 * 365.
BARS_PER_YEAR_15M = 4 * 24 * 365


@dataclass
class BacktestResult:
    """Outcome of a single backtest run.

    Returns and drawdown are **fractions**, not percentages: ``0.15`` means
    +15%. ``max_drawdown`` is reported as a positive number (``0.22`` describes
    a 22% peak-to-trough decline).
    """

    final_value: float
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    trades_count: int
    equity: pd.Series = field(repr=False)


def _clean_bool(signal, index) -> np.ndarray:
    """Coerces a signal series to a plain boolean array aligned with *index*."""
    if signal is None:
        return np.zeros(len(index), dtype=bool)
    if isinstance(signal, pd.Series):
        signal = signal.reindex(index).fillna(False)
        return signal.to_numpy(dtype=bool)
    arr = np.asarray(signal)
    if arr.shape != (len(index),):
        raise ValueError(f"signal length {arr.shape} does not match price length {len(index)}")
    return arr.astype(bool)


def run_signal_backtest(
    close,
    entries,
    exits,
    *,
    allow_short: bool = False,
    init_cash: float = 10_000.0,
    fees: float = 0.0005,
    slippage: float = 0.0005,
    sl_stop: float | None = None,
    tp_stop: float | None = None,
    bars_per_year: int = BARS_PER_YEAR_15M,
) -> BacktestResult:
    """Runs a signal-driven backtest over a close-price series.

    Args:
        close: price series (a ``pd.Series``, or anything convertible).
        entries: boolean signal — open long (and, when *allow_short*, close short).
        exits: boolean signal — close long (and, when *allow_short*, open short).
        allow_short: if True the strategy is stop-and-reverse: an exit signal
            flips the position to short rather than to flat.
        init_cash: starting account value.
        fees: proportional cost per side, e.g. ``0.0005`` for 5 bps.
        slippage: proportional adverse price adjustment per side.
        sl_stop: stop-loss as a fraction of the entry price (``0.02`` = 2%).
        tp_stop: take-profit as a fraction of the entry price.
        bars_per_year: used to annualise the Sharpe ratio.

    Returns:
        A :class:`BacktestResult`. On a degenerate input (fewer than two usable
        prices) every metric is ``nan``/zero rather than raising.
    """
    # Align signals against the ORIGINAL index, then drop NaN prices from price
    # and signals together. Dropping first would shorten the price series and
    # leave positionally-supplied signals (lists/arrays) misaligned.
    close_raw = pd.Series(close).astype(float)
    entry_raw = _clean_bool(entries, close_raw.index)
    exit_raw = _clean_bool(exits, close_raw.index)

    keep = close_raw.notna().to_numpy()
    close = close_raw[keep]
    entry_sig = entry_raw[keep]
    exit_sig = exit_raw[keep]
    n = len(close)

    if n < 2:
        empty = pd.Series(dtype=float)
        return BacktestResult(
            final_value=float(init_cash),
            total_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=float("nan"),
            trades_count=0,
            equity=empty,
        )

    idx = close.index
    prices = close.to_numpy()

    cash = float(init_cash)
    position = 0.0        # units held; negative means short
    entry_price = 0.0
    trades = 0
    equity = np.empty(n, dtype=float)

    def open_long(price):
        nonlocal cash, position, entry_price
        fill = price * (1.0 + slippage)
        qty = cash / (fill * (1.0 + fees))
        cash -= qty * fill * (1.0 + fees)
        position = qty
        entry_price = fill

    def close_long(price):
        nonlocal cash, position, trades
        fill = price * (1.0 - slippage)
        cash += position * fill * (1.0 - fees)
        position = 0.0
        trades += 1

    def open_short(price):
        nonlocal cash, position, entry_price
        fill = price * (1.0 - slippage)
        qty = cash / (fill * (1.0 + fees))
        cash += qty * fill * (1.0 - fees)
        position = -qty
        entry_price = fill

    def close_short(price):
        nonlocal cash, position, trades
        fill = price * (1.0 + slippage)
        cash -= abs(position) * fill * (1.0 + fees)
        position = 0.0
        trades += 1

    for i in range(n):
        price = prices[i]

        # --- 1. Stops, evaluated against this bar's close ------------------
        if position != 0.0 and entry_price > 0.0 and (sl_stop or tp_stop):
            if position > 0:
                move = (price - entry_price) / entry_price
            else:
                move = (entry_price - price) / entry_price
            stopped = (sl_stop is not None and move <= -sl_stop) or \
                      (tp_stop is not None and move >= tp_stop)
            if stopped:
                if position > 0:
                    close_long(price)
                else:
                    close_short(price)

        # --- 2. Signals ----------------------------------------------------
        want_entry = bool(entry_sig[i])
        want_exit = bool(exit_sig[i])

        if want_entry and want_exit:
            pass  # ambiguous bar: both directions fired, do nothing
        elif allow_short:
            if want_entry:
                if position < 0:
                    close_short(price)
                if position == 0.0:
                    open_long(price)
            elif want_exit:
                if position > 0:
                    close_long(price)
                if position == 0.0:
                    open_short(price)
        else:
            if want_entry and position == 0.0:
                open_long(price)
            elif want_exit and position > 0:
                close_long(price)

        equity[i] = cash + position * price

    equity_s = pd.Series(equity, index=idx)

    final_value = float(equity_s.iloc[-1])
    total_return = final_value / float(init_cash) - 1.0

    running_max = equity_s.cummax()
    drawdown = equity_s / running_max - 1.0
    max_drawdown = float(-drawdown.min()) if len(drawdown) else 0.0
    max_drawdown = max(0.0, max_drawdown)

    rets = equity_s.pct_change().dropna()
    std = float(rets.std())
    if len(rets) < 2 or std == 0.0 or not np.isfinite(std):
        sharpe = float("nan")
    else:
        sharpe = float(rets.mean() / std * np.sqrt(bars_per_year))

    return BacktestResult(
        final_value=final_value,
        total_return=float(total_return),
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe,
        trades_count=trades,
        equity=equity_s,
    )
