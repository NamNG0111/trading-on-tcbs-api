import pandas as pd
import numpy as np
from .strategy import SignalStrategy


class IntradayDipStrategy(SignalStrategy):
    """
    Intraday Dip-Buy Strategy for low-liquidity, large-cap stocks.
    
    Concept: Stocks with poor liquidity often dip hard during the session 
    (long lower wicks) then recover by close. This strategy:
    
    - BUY when today's low drops ≥ x% below yesterday's close
    - x% is dynamically calculated as the y-th percentile of historical 
      (close_prev - low) / close_prev over a rolling window
    - Simulated buy price = close_yesterday × (1 - x%)
    - Sell at today's close
    
    For backtesting, generates signal=1 on qualifying days and stores
    `simulated_buy_price` column for custom P&L calculation.
    """
    
    def __init__(self, lookback_days: int = 60, percentile: float = 75.0):
        """
        Args:
            lookback_days (int): Rolling window to compute the dip percentile threshold.
                               If a stock has fewer sessions, uses all available data
                               (minimum 20 sessions required).
            percentile (float): The percentile of historical dips that must be exceeded 
                               to trigger a BUY. Higher = more conservative (fewer signals).
        """
        self.lookback_days = lookback_days
        self.percentile = percentile
        
        self.name = "Intraday Dip Strategy"
        self.description = (
            f"BUY when intraday dip from prev close ≥ P{self.percentile:.0f} "
            f"of last {self.lookback_days} sessions."
        )
    
    def get_required_indicators(self) -> list:
        """This strategy uses raw OHLCV only, no external indicators needed."""
        return []
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate BUY signals when intraday dip exceeds the rolling percentile threshold.
        
        Adds columns:
            - signal: 1 = BUY, 0 = HOLD (no SELL — each trade is intraday)
            - prev_close: yesterday's close price
            - dip_pct: (prev_close - low) / prev_close for today
            - dip_threshold: rolling percentile threshold
            - simulated_buy_price: prev_close × (1 - dip_threshold)
            - simulated_profit_pct: (close - simulated_buy_price) / simulated_buy_price × 100
        """
        df = data.copy()
        
        # 1. Compute previous session's close
        df['prev_close'] = df['close'].shift(1)
        
        # 2. Compute today's dip magnitude: how far low dropped from prev close
        #    Only positive values matter (when low < prev_close)
        df['dip_pct'] = (df['prev_close'] - df['low']) / df['prev_close']
        df['dip_pct'] = df['dip_pct'].clip(lower=0)  # Ignore days where low >= prev_close
        
        # 3. Rolling percentile threshold over lookback window
        #    min_periods=20 ensures stocks with fewer sessions than lookback_days
        #    still get signals (e.g., TCX with ~100 sessions when lookback=250)
        df['dip_threshold'] = df['dip_pct'].rolling(
            window=self.lookback_days, min_periods=20
        ).quantile(self.percentile / 100.0)
        
        # 4. Simulated buy price = prev_close × (1 - threshold)
        df['simulated_buy_price'] = df['prev_close'] * (1 - df['dip_threshold'])
        
        # 5. BUY signal: today's low actually reached below the threshold level
        #    AND threshold is positive (avoids buying on flat stocks)
        df['signal'] = 0
        buy_condition = (
            (df['low'] <= df['simulated_buy_price']) & 
            (df['dip_threshold'] > 0) &
            (df['dip_threshold'].notna())
        )
        df.loc[buy_condition, 'signal'] = 1
        
        # 6. Compute simulated profit for analysis
        #    Buy at simulated_buy_price, sell at close
        df['simulated_profit_pct'] = np.where(
            df['signal'] == 1,
            (df['close'] - df['simulated_buy_price']) / df['simulated_buy_price'] * 100,
            np.nan
        )
        
        return df
