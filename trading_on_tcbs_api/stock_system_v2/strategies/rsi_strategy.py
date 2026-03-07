
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
        
        # Calculate RSI (Pandas implementation)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        
        # Note: This is Simple Moving Average RSI. 
        # For Wilder's Smoothing (standard RSI), we'd use ewm:
        # gain = delta.where(delta > 0, 0).ewm(alpha=1/self.period, adjust=False).mean()
        # loss = -delta.where(delta < 0, 0).ewm(alpha=1/self.period, adjust=False).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Initialize signal
        df['signal'] = 0
        
        # Buy Signal (RSI crosses below 30 then returns? Or just blindly buy < 30?)
        # Let's simple logic: Buy when RSI < 30
        # Sell when RSI > 70
        
        # To avoid spamming Buy every day it's < 30, we should detect ENTRY
        df['prev_rsi'] = df['rsi'].shift(1)
        
        # Buy: Yesterday >= 30, Today < 30 (Entering Oversold) 
        # OR Yesterday < 30, Today >= 30 (Exiting Oversold - traditional signal)
        # Let's use "Exiting Oversold" (Reversal)
        df.loc[(df['prev_rsi'] < self.oversold) & (df['rsi'] >= self.oversold), 'signal'] = 1
        
        # Sell: Exiting Overbought
        df.loc[(df['prev_rsi'] > self.overbought) & (df['rsi'] <= self.overbought), 'signal'] = -1
        
        return df
