# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

import logging

import numpy as np

logger = logging.getLogger("BTCPatternMatcher")


class BTCPatternMatcher:
    def __init__(self, query_window=None, history_years=None, projection_window=None, interval=None):
        """
        Initializes the pattern matcher for BTC.
        Forced to 15-minute timeframe with 8 query candles and 8 projection candles (2 hours).
        """
        from core.data_manager import load_settings
        cfg = load_settings()

        self.symbol = "BTC-USD"
        self.query_window = 8  # 2 hours (8 candles of 15m)
        self.projection_window = 8  # 2 hours (8 candles of 15m)
        self.interval = "15m"  # Always 15m hardcoded
        self.history_years = history_years if history_years is not None else int(cfg.get("pm_history_years", 1))
        self.df = None

    def fetch_data(self):
        """Loads local historical BTC data saved by the markets module."""
        try:
            logger.info(f"Loading {self.symbol} ({self.interval}) data from markets module...")
            from core.data_manager import load_historical

            df = load_historical("BTC")

            if df is None or df.empty:
                logger.error("No local data retrievable for the Pattern Matcher.")
                return False

            self.df = df[['Close']].copy()
            self.df['LogReturn'] = np.log(self.df['Close'] / self.df['Close'].shift(1))
            self.df.dropna(inplace=True)
            logger.info(f"Loaded {len(self.df)} historical records for {self.symbol}.")
            return True
        except ValueError as ve:
            logger.error(f"Error loading BTC data (obsolete/missing): {ve}")
            return False
        except Exception as e:
            logger.error(f"Generic error loading BTC data: {e}")
            return False

    def _empty_result(self):
        # Same key set as a successful run so callers never have to guess.
        return {
            "btc_pred_confidence": 0.0,
            "btc_expected_move": 0.0,
            "matches_count": 0,
            "btc_current_price": 0.0,
            "btc_target_price": 0.0,
        }

    def get_query_pattern(self):
        """Extracts the latest pattern (query_window) from recent data."""
        if self.df is None or len(self.df) < self.query_window:
            return None
        recent_returns = self.df['LogReturn'].iloc[-self.query_window:].values
        return self._normalize(recent_returns)

    @staticmethod
    def _normalize(sequence):
        """Z-Score normalisation. Returns zeros for a constant (zero-variance) window."""
        seq = np.asarray(sequence, dtype=float)
        if seq.size == 0:
            return seq
        std = seq.std()
        if std == 0 or not np.isfinite(std):
            return np.zeros_like(seq)
        return (seq - seq.mean()) / std

    def prepare_historical_windows(self):
        """Prepares sliding historical windows for KNN."""
        if self.df is None or len(self.df) < self.query_window + self.projection_window:
            return None, None

        returns = self.df['LogReturn'].values
        n_samples = len(returns) - self.query_window - self.projection_window + 1

        X = []
        future_returns = []

        # Skip the current window to avoid matching it with itself
        max_idx = n_samples - self.query_window

        for i in range(max_idx):
            window = returns[i : i + self.query_window]
            norm_window = self._normalize(window)
            X.append(norm_window)

            # Calculate future return (sum of log returns -> approx % return)
            f_rets = returns[i + self.query_window : i + self.query_window + self.projection_window]
            future_return_pct = (np.exp(np.sum(f_rets)) - 1.0) * 100.0
            future_returns.append(future_return_pct)

        return np.array(X), np.array(future_returns)

    def run_analysis(self, n_neighbors=None):
        """
        Runs KNN-DTW (Euclidean) analysis and returns the signal.
        """
        if n_neighbors is None:
            from core.data_manager import load_settings
            cfg = load_settings()
            try:
                n_neighbors = int(cfg.get("pm_n_neighbors", 5))
            except (TypeError, ValueError):
                n_neighbors = 5
        n_neighbors = max(1, int(n_neighbors))

        # Imported lazily so a missing scikit-learn degrades to an empty result
        # instead of breaking the import of every module that touches this one.
        try:
            from sklearn.neighbors import NearestNeighbors
        except ImportError as e:
            logger.error(f"scikit-learn is required for Pattern Matching ({e}). Run: pip install scikit-learn")
            return self._empty_result()

        if not self.fetch_data():
            return self._empty_result()

        query_seq = self.get_query_pattern()
        if query_seq is None:
            return self._empty_result()

        X, y_future = self.prepare_historical_windows()
        if X is None or len(X) < n_neighbors:
            return self._empty_result()

        # Use NearestNeighbors with Euclidean distance on normalized sequences
        nn = NearestNeighbors(n_neighbors=n_neighbors, metric='euclidean')
        nn.fit(X)

        distances, indices = nn.kneighbors([query_seq])

        matched_future_returns = y_future[indices[0]]

        # Calculate match statistics
        positive_matches = sum(1 for ret in matched_future_returns if ret > 0)
        negative_matches = sum(1 for ret in matched_future_returns if ret < 0)

        avg_move = np.mean(matched_future_returns)

        # Weighting based on sign, mean geometric distance, and standard deviation
        concordanza_segno_pct = (max(positive_matches, negative_matches) / n_neighbors) * 100.0
        data_distance_mean = np.mean(distances[0])
        std_returns = np.std(matched_future_returns)

        # Recommended baseline formula (60% sign consistency + 40% geometric proximity)
        base_confidence = (concordanza_segno_pct * 0.6) + (1.0 / (1.0 + data_distance_mean) * 0.4 * 100.0)

        # Penalty for return volatility (uncertain future evolution)
        # The 0.5 factor dampens the penalty to avoid overly penalizing stable patterns
        vol_penalty = 1.0 / (1.0 + std_returns * 0.5)

        confidence = base_confidence * vol_penalty
        confidence = max(0.0, min(100.0, confidence))

        current_price = float(self.df['Close'].iloc[-1]) if self.df is not None and not self.df.empty else 0.0
        return {
            "btc_pred_confidence": round(confidence, 1),
            "btc_expected_move": round(avg_move, 2),
            "matches_count": n_neighbors,
            "btc_current_price": round(current_price, 2),
            "btc_target_price": round(current_price * (1.0 + avg_move / 100.0), 2) if current_price > 0 else 0.0
        }


if __name__ == "__main__":
    # Quick execution test
    logging.basicConfig(level=logging.INFO)
    matcher = BTCPatternMatcher()
    result = matcher.run_analysis()
    print("Pattern Matching Result:", result)
