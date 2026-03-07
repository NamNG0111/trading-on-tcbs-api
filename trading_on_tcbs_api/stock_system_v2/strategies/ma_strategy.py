
import pandas as pd
import numpy as np
from .strategy import SignalStrategy

class SimpleMAStrategy(SignalStrategy):
    """
    Simple Moving Average Crossover Strategy.
    Buy: Short MA > Long MA
    Sell: Short MA < Long MA
    """
    
    def __init__(self, short_window: int = 20, long_window: int = 50):
        self.short_window = short_window
        self.long_window = long_window
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates MA crossover signals.
        """
        # Ensure we don't modify original dataframe in place if passed by reference
        df = data.copy()
        
        # Calculate MAs
        df['short_ma'] = df['close'].rolling(window=self.short_window).mean()
        df['long_ma'] = df['close'].rolling(window=self.long_window).mean()
        
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
        df.loc[df['short_ma'] > df['long_ma'], 'regime'] = 1
        df.loc[df['short_ma'] <= df['long_ma'], 'regime'] = -1
        
        # Shift to compare with yesterday
        df['prev_regime'] = df['regime'].shift(1)
        
        # Buy Signal (1) when moving from -1 or 0 to 1
        df.loc[(df['regime'] == 1) & (df['prev_regime'] == -1), 'signal'] = 1
        
        # Sell Signal (-1) when moving from 1 to -1
        df.loc[(df['regime'] == -1) & (df['prev_regime'] == 1), 'signal'] = -1
        
        return df
