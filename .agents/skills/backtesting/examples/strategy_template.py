"""
Example Strategy Template for the Backtesting Skill.

This file demonstrates the exact pattern required to create a new strategy
that is compatible with the backtesting system (IndicatorEngine → Strategy → Backtester).

Copy this file, rename it, and modify the logic inside `generate_signals()`.

RULES:
1. Always inherit from `SignalStrategy`
2. Never calculate indicators inside this class — read pre-computed columns instead
3. Set `self.name` and `self.description` in `__init__`
4. Implement `get_required_indicators()` so the system can self-document
5. Signal column: 1 = BUY, -1 = SELL, 0 = HOLD
"""

import pandas as pd
from trading_on_tcbs_api.stock_system_v2.strategies.strategy import SignalStrategy


class ExampleStrategy(SignalStrategy):
    """
    Example: Buy when RSI is oversold AND price is below SMA.
    This is a template — replace the logic with your own.
    """

    def __init__(self, rsi_period: int = 14, sma_period: int = 20, oversold: float = 30.0):
        self.rsi_period = rsi_period
        self.sma_period = sma_period
        self.oversold = oversold

        # REQUIRED: Human-readable metadata
        self.name = "Example RSI+SMA Dip"
        self.description = (
            f"BUY when RSI({self.rsi_period}) < {self.oversold} "
            f"AND close < SMA({self.sma_period})"
        )

    def get_required_indicators(self) -> list:
        """
        Declare which pre-computed columns this strategy reads.
        These MUST exist in IndicatorEngine's config.
        """
        return [f"rsi_{self.rsi_period}", f"sma_{self.sma_period}"]

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        # 1. Verify required columns exist (fail-fast if IndicatorEngine is misconfigured)
        rsi_col = f"rsi_{self.rsi_period}"
        sma_col = f"sma_{self.sma_period}"

        for col in [rsi_col, sma_col]:
            if col not in df.columns:
                raise ValueError(
                    f"Missing required indicator column: {col}. "
                    f"Ensure it is configured in IndicatorEngine.get_default_config()."
                )

        # 2. Initialize signal column
        df["signal"] = 0

        # 3. BUY Logic: RSI oversold AND price below SMA (double confirmation)
        buy_mask = (df[rsi_col] < self.oversold) & (df["close"] < df[sma_col])
        df.loc[buy_mask, "signal"] = 1

        # 4. SELL Logic (optional — can be left to CombinedStrategy's sell_strategies)
        # Example: Sell when RSI recovers above 50
        # sell_mask = df[rsi_col] > 50
        # df.loc[sell_mask, 'signal'] = -1

        return df
