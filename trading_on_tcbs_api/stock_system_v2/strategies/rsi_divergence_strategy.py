
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from .strategy import SignalStrategy


class RSIDivergenceStrategy(SignalStrategy):
    """
    RSI Divergence Strategy — detects divergence between price and RSI
    to identify potential reversal points.

    Bullish Divergence (BUY):
        Price makes a lower low, but RSI makes a higher low.
        → Downtrend may be ending, price could reverse upward.

    Bearish Divergence (SELL):
        Price makes a higher high, but RSI makes a lower high.
        → Uptrend may be ending, price could reverse downward.
    """

    def __init__(self, rsi_period: int = 14, lookback: int = 5, max_bars_between: int = 30):
        """
        Args:
            rsi_period: RSI period (must match IndicatorEngine config).
            lookback: Window size (order) for argrelextrema to detect local peaks/troughs.
                      Higher = fewer, more significant peaks. Lower = more sensitive.
            max_bars_between: Maximum number of bars between two consecutive
                              peaks/troughs for a valid divergence comparison.
        """
        self.rsi_period = rsi_period
        self.lookback = lookback
        self.max_bars_between = max_bars_between

        self.name = "RSI Divergence"
        self.description = (
            f"BUY on bullish divergence (price lower low + RSI higher low), "
            f"SELL on bearish divergence (price higher high + RSI lower high). "
            f"RSI({rsi_period}), lookback={lookback}, max_gap={max_bars_between} bars."
        )

    def get_required_indicators(self) -> list:
        return [f'rsi_{self.rsi_period}']

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        rsi_col = f'rsi_{self.rsi_period}'
        if rsi_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {rsi_col}")

        df['signal'] = 0

        close = df['close'].values
        rsi = df[rsi_col].values
        n = len(df)

        if n < self.lookback * 2 + 1:
            return df

        # --- Detect local minima (troughs) and maxima (peaks) in PRICE ---
        price_min_indices = argrelextrema(close, np.less_equal, order=self.lookback)[0]
        price_max_indices = argrelextrema(close, np.greater_equal, order=self.lookback)[0]

        # --- Bullish Divergence: price lower low + RSI higher low ---
        for i in range(1, len(price_min_indices)):
            curr_idx = price_min_indices[i]
            prev_idx = price_min_indices[i - 1]

            # Skip if the two troughs are too far apart
            if curr_idx - prev_idx > self.max_bars_between:
                continue

            # Skip if RSI is NaN at either point
            if np.isnan(rsi[curr_idx]) or np.isnan(rsi[prev_idx]):
                continue

            # Price: current low < previous low (lower low)
            # RSI:   current RSI > previous RSI (higher low)
            if close[curr_idx] < close[prev_idx] and rsi[curr_idx] > rsi[prev_idx]:
                df.iloc[curr_idx, df.columns.get_loc('signal')] = 1

        # --- Bearish Divergence: price higher high + RSI lower high ---
        for i in range(1, len(price_max_indices)):
            curr_idx = price_max_indices[i]
            prev_idx = price_max_indices[i - 1]

            # Skip if the two peaks are too far apart
            if curr_idx - prev_idx > self.max_bars_between:
                continue

            # Skip if RSI is NaN at either point
            if np.isnan(rsi[curr_idx]) or np.isnan(rsi[prev_idx]):
                continue

            # Price: current high > previous high (higher high)
            # RSI:   current RSI < previous RSI (lower high)
            if close[curr_idx] > close[prev_idx] and rsi[curr_idx] < rsi[prev_idx]:
                df.iloc[curr_idx, df.columns.get_loc('signal')] = -1

        return df
