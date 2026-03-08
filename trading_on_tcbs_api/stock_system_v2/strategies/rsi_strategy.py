
import pandas as pd
import numpy as np
from .strategy import SignalStrategy

class RSIStrategy(SignalStrategy):
    """
    RSI Strategy.
    Mode 1 (Basic): Buy strictly when RSI < oversold.
    Mode 2 (Reversal): Buy when RSI crosses ABOVE the oversold line (exiting oversold).
    Sell: RSI > overbought (or crosses below overbought).
    """
    
    def __init__(self, period: int = 14, overbought: int = 70, oversold: int = 30, is_reversal: bool = True):
        self.period = period
        self.overbought = overbought
        self.oversold = oversold
        self.is_reversal = is_reversal
        
        self.name = "RSI Reversal" if is_reversal else "RSI Basic"
        desc = f"BUY when RSI crosses above {oversold} (Reversal)." if is_reversal else f"BUY when RSI is below {oversold} (Oversold)."
        self.description = desc
        
    def get_required_indicators(self) -> list:
        return [f'rsi_{self.period}']
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # RSI is now pre-calculated by IndicatorEngine via pandas-ta
        rsi_col = f'rsi_{self.period}'
        
        if rsi_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {rsi_col}")
        
        # Initialize signal
        df['signal'] = 0
        
        if self.is_reversal:
            # Reversal Logic: Buy when Exiting Oversold, Sell when Exiting Overbought
            df['prev_rsi'] = df[rsi_col].shift(1)
            
            # Buy: Yesterday < 30 AND Today >= 30
            df.loc[(df['prev_rsi'] < self.oversold) & (df[rsi_col] >= self.oversold), 'signal'] = 1
            
            # Sell: Yesterday > 70 AND Today <= 70
            df.loc[(df['prev_rsi'] > self.overbought) & (df[rsi_col] <= self.overbought), 'signal'] = -1
        else:
            # Basic Logic: Buy whenever in Oversold territory
            df.loc[df[rsi_col] < self.oversold, 'signal'] = 1
            
            # Sell: Sell whenever in Overbought territory
            df.loc[df[rsi_col] > self.overbought, 'signal'] = -1
            
        return df
