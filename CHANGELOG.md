# Changelog

All notable changes to Argus are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Licensing

- **Removed the `vectorbt` dependency**, which shipped under Apache-2.0 **plus
  the Commons Clause** — a condition withholding the right to sell software
  whose value derives substantially from it, incompatible with Argus's
  dual-licensing model. All published releases (0.26 through 1.1) carry the
  clause, so pinning an older version was not a way out.
  - Replaced by `core/backtest.py`: a dependency-free signal backtester
    (pandas/NumPy only) covering the surface actually used — long-only and
    stop-and-reverse long/short, proportional fees and slippage, percentage
    SL/TP, reporting total return, max drawdown, annualised Sharpe and a trade
    count. Validated against hand-computed cases, including exact fee and
    slippage arithmetic.
  - Side benefit: drops the numba/llvmlite toolchain from the install.
- Added `LICENSING.md` with commercial tiers, indicative pricing, an explicit
  statement of what a commercial licence does *not* include, and a
  dependency-by-dependency licence table. Every remaining dependency is
  permissive (MIT / BSD-3 / Apache-2.0 / HPND).
- Corrected the README's AGPL summary: "modify & redistribute privately | no
  obligation" was wrong — distributing a modified copy, even privately, obliges
  you to provide that recipient the source under AGPL-3.0.

### Fixed

- The bearish-regime backtest report labelled its protective stop "3%" while
  the code applied `min(0.01, sl_stop)` — 1% or less. The label now states the
  figure actually used, and when the base stop is already tighter than the
  protective one (making both runs identical) the report says so instead of
  presenting the same number twice as a comparison.

---

A full audit of the application: every fix below was reproduced before being
changed, and is covered by a regression test.

### Added

- **Test suite** (`tests/`), fully offline — no exchange, provider or LLM calls.
  - `tests/test_core.py` — ensemble weighting and sizing, signal building,
    formatting, KNN pattern matching on synthetic prices, settings and cache
    persistence, pre-flight checks, CSV/Excel/PDF export.
  - `tests/test_gui_smoke.py` — boots the real Tk application under Xvfb, walks
    every view, renders tables from mixed-quality rows and drives the
    worker-thread error paths.
- `PortfolioManager.for_sizing()` — an offline instance for the pure ensemble
  maths, with no CCXT client and no I/O.
- `PortfolioManager.ensure_markets()` — lets worker threads block until the
  market catalogue is loaded.
- `normalize_ensemble_weights()` — single source of truth for reading the
  ensemble weights, accepting both the percentage and fraction forms.
- Dark ttk scrollbar styling shared across all tables (`gui/utils.py`).
- Documented the `python3-tk` OS prerequisite, which pip cannot satisfy on Linux.

### Fixed

**Dependencies**

- `requirements.txt` was missing **`scikit-learn`**, a top-level import in
  `core/btc_pattern_matcher.py` — Pattern Matching raised `ImportError` on any
  clean install. It was already listed in the README's dependency table.
- `requirements.txt` was missing **`beautifulsoup4`**, used by the
  Investing.com news scraper.

**Crashes**

- `core/ai_analyst.py` — the Investing.com RSS fallback used an unescaped
  `<![CDATA[` pattern, so `re.findall` raised *unbalanced parenthesis* and the
  fallback never returned a headline.
- `core/ai_analyst.py` — `_fetch_yahoo_details()` called
  `Ticker.history(progress=False)`; `progress` belongs to `yf.download`, so the
  call raised `TypeError` and the entire Yahoo fallback for market data was dead.
- `core/analyzer.py` — `format_price()` / `format_change_pct()` assumed floats
  and raised `TypeError` on the strings returned by a CSV reload, breaking the
  results table.
- `core/analyzer.py` — `verify_past_forecasts()` let `load_historical()`'s
  `ValueError` escape, so one stale symbol aborted the whole report.
- `core/ai_analysis_store.py` — `float()` on the `"N/A"` / `"DISABLED"`
  confidence sentinels made CSV, Excel and PDF export fail outright.
- `gui/portfolio_panel.py` — *Sell Selected* read the **leverage** column as the
  quantity and attempted `float("10.0x")`. It now reads the position records
  directly and forwards the direction so the correct side is closed.
- `gui/portfolio_panel.py`, `gui/pattern_matching_panel.py` — error callbacks
  closed over an `except ... as e` variable, which Python unbinds when the block
  exits, so the error path raised `NameError` instead of reporting the failure.
- `gui/app.py` — startup called `self.state("zoomed")`, which only exists on
  Windows and raises `TclError` elsewhere. Now falls back to the `-zoomed`
  attribute, then to explicit screen-size geometry.

**Logic**

- **Ensemble weights** are stored as percentages (`40`/`40`/`20`) but
  `PortfolioManager.calculate_sizing()` read them as fractions, so the ±0.05
  confidence adjustments were swamped and had **no effect at all**. Confidence
  now genuinely reweights the ensemble.
- **Minimum AI Confidence** only scaled the position size; below-threshold
  signals still became orders, and the `discarded_callback` that drives Auto
  Trading's low-confidence cooldown was never invoked. The threshold is now
  enforced as documented.
- The instant backtest compared the regime against `"BULLISH"` / `"BEARISH"` —
  labels `get_market_context()` never emits — so the regime-conditional branch
  was unreachable. Added `_regime_bias()` to map the real labels.
- The backtest reported three contradictory windows (*"Last 6 Months"*,
  *"Last 30 Days @ 15m"*, and a differing figure in the LLM prompt) while
  actually running over the local 15m cache. The header now states the window
  the data really covers.
- `core/market_enrichment.py` — the error path dropped `fng_value` / `fng_class`
  and discarded an already-fetched Fear & Greed reading. The alt-proxy download
  is now optional rather than fatal.
- `gui/auto_trading_panel.py` — the weekend branch returned without rearming,
  permanently killing the 1-second scheduler tick. The tick is now
  self-perpetuating and survives exceptions.
- `model_checkpoint` is persisted as `""`, so `.get(key, default)` handed an
  empty string to `from_pretrained()` instead of the intended default. Same
  pattern fixed for `backend`.
- `core/data_manager.py` — staleness checks used the deprecated
  `datetime.utcnow()` and stripped tz-aware timestamps without converting,
  skewing the computed age by the UTC offset.
- `core/data_fetcher.py` — order-book levels were tuple-unpacked as
  `[price, amount]`; venues that append extra fields raised `ValueError`.

### Changed

- **`PortfolioManager` no longer blocks on construction.** The clock sync and
  `load_markets()` call now run on a background thread, so building the object
  costs ~6 ms instead of ~409 ms (far worse on a slow or unreachable network,
  where it froze the Tk main thread for the whole CCXT timeout).
- The exporters built a `PortfolioManager` — and therefore a network
  `load_markets()` — **per result row**. Now built once, and offline.
- Auto Trading reloaded the TimesFM model on every 15-minute cycle; the loaded
  model is now cached across cycles.
- The pattern matcher's per-window `StandardScaler` was replaced with a direct
  numpy z-score (identical maths, no per-window object allocation) and now
  handles zero-variance windows instead of producing `NaN`.
- `scikit-learn` is imported lazily, so a missing install degrades Pattern
  Matching to an empty result rather than breaking module import.
- PDF export no longer leaks leverage between rows: one tight stop-loss used to
  permanently shrink the leverage shown for every subsequent row.
- Widened two clipped table column headers.

### Documentation

- Corrected **every** default in the Configuration Reference — most did not
  match `DEFAULT_SETTINGS` (leverage, open positions, capital usage, TP ROI cap,
  pre-flight thresholds, DCA distance, weekend flag, and more).
- Rewrote the Auto-Trading section: the previous text described a *"Step 4 Macro
  BTC/ETH dominance filter"* and a *"Step 5 — Normal Asset"* that **do not exist
  in the codebase** (`fetch_eth_btc_ratio()` is never called, and the cycle
  trades a hardcoded BTC entry).
- Corrected the Instant Backtest section: it reads the local 15-minute cache,
  not "6 months of daily data via yfinance".
- Documented the real TimesFM confidence formula (quantile spread), replacing a
  description of an ATR helper that is not wired into the forecast.
- Documented ensemble weights as percentages, the minimum-confidence gate, the
  secrets split between `settings.json` and `.env`, and renamed
  `ai_debate_rounds` → `ai_research_rounds` (the key the code actually reads).
- Added **Testing** and **Scope & Current Limitations** sections. The latter
  states plainly that the app trades BTC only, and lists the settings and
  functions that are present but unused.
