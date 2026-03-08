
import pandas as pd
import numpy as np
from .strategy import SignalStrategy

class SimpleMAStrategy(SignalStrategy):
    """
    Simple Moving Average Crossover Strategy.
    Buy: Short MA > Long MA
    Sell: Short MA < Long MA
    """
    def __init__(self, short_window: int = 20, long_window: int = 50, invert: bool = False):
        self.short_window = short_window
        self.long_window = long_window
        self.invert = invert
        
        self.name = "SMA Crossover" if not invert else "SMA Exit"
        self.description = f"BUY when {short_window}-MA > {long_window}-MA." if not invert else f"SELL when {short_window}-MA sweeps below {long_window}-MA."
        
    def get_required_indicators(self) -> list:
        reqs = []
        if self.short_window > 1:
            reqs.append(f'sma_{self.short_window}')
        if self.long_window > 1:
            reqs.append(f'sma_{self.long_window}')
        return reqs
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates MA crossover signals.
        """
        # Ensure we don't modify original dataframe in place if passed by reference
        df = data.copy()
        
        # Calculate MAs
        # MAs are now pre-calculated by IndicatorEngine via pandas-ta
        # pandas-ta lowercases names to e.g., 'sma_20', 'sma_50'
        # If window is 1, fall back to 'close' price directly.
        short_col = 'close' if self.short_window == 1 else f'sma_{self.short_window}'
        long_col = 'close' if self.long_window == 1 else f'sma_{self.long_window}'
        
        if short_col not in df.columns or long_col not in df.columns:
            raise ValueError(f"Missing required indicator columns: {short_col}, {long_col}")
        
        # Initialize signal column
        df['signal'] = 0
        
        # Generate Signals
        # 1. Identify where Short > Long
        # condition = df['short_ma'] > df['long_ma']
        
        # 2. Generate Crossovers (Signal when state changes)
        # We'll use a loop or vectorized approach. 
        # Vectorized: 
        #   df['regime'] = np.where(df['short_ma'] > df['long_ma'], 1, -1)
        #   df['signal'] = df['regime'].diff() (This gives 2 for Buy, -2 for Sell)
        
        # Let's simple Regime approach:
        # 1 = Bullish Regime, -1 = Bearish Regime
        # Backtester will Buy if it has cash and signal is 1 (or we change Backtester to respect Regime)
        
        # Current Backtester logic: 
        # if signal == 1: Buy
        # if signal == -1: Sell
        
        # So we only want to signal ON THE DAY of crossover
        df['regime'] = 0
        df.loc[df[short_col] > df[long_col], 'regime'] = 1
        df.loc[df[short_col] <= df[long_col], 'regime'] = -1
        
        # Shift to compare with yesterday
        df['prev_regime'] = df['regime'].shift(1)
        
        # Buy Signal (1) when moving from -1 or 0 to 1
        df.loc[(df['regime'] == 1) & (df['prev_regime'] == -1), 'signal'] = 1
        
        # Sell Signal (-1) when moving from 1 to -1
        df.loc[(df['regime'] == -1) & (df['prev_regime'] == 1), 'signal'] = -1
        
        # Invert signals if requested (Useful for "Sell on Rip" or shorting strategies)
        if self.invert:
            df['signal'] = df['signal'] * -1
            
        return df
