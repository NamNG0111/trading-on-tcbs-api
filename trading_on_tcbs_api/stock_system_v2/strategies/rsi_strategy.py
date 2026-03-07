
import pandas as pd
import numpy as np
from .strategy import SignalStrategy

class RSIStrategy(SignalStrategy):
    """
    RSI Strategy.
    Buy: RSI < 30 (Oversold)
    Sell: RSI > 70 (Overbought)
    """
    
    def __init__(self, period: int = 14, overbought: int = 70, oversold: int = 30):
        self.period = period
        self.overbought = overbought
        self.oversold = oversold
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # RSI is now pre-calculated by IndicatorEngine via pandas-ta
        rsi_col = f'rsi_{self.period}'
        
        if rsi_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {rsi_col}")
        
        # Initialize signal
        df['signal'] = 0
        
        # Buy Signal (RSI crosses below 30 then returns? Or just blindly buy < 30?)
        # Let's simple logic: Buy when RSI < 30
        # Sell when RSI > 70
        
        # To avoid spamming Buy every day it's < 30, we should detect ENTRY
        df['prev_rsi'] = df[rsi_col].shift(1)
        
        # Buy: Yesterday >= 30, Today < 30 (Entering Oversold) 
        # OR Yesterday < 30, Today >= 30 (Exiting Oversold - traditional signal)
        # Let's use "Exiting Oversold" (Reversal)
        df.loc[(df['prev_rsi'] < self.oversold) & (df[rsi_col] >= self.oversold), 'signal'] = 1
        
        # Sell: Exiting Overbought
        df.loc[(df['prev_rsi'] > self.overbought) & (df[rsi_col] <= self.overbought), 'signal'] = -1
        
        return df
