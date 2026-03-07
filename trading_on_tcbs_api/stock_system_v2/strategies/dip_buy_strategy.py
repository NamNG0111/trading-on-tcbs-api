import pandas as pd
from .strategy import SignalStrategy

class DipBuyStrategy(SignalStrategy):
    """
    Dip Buy Strategy.
    Buy: Price drops more than X% below the Y-day SMA.
    Sell: Reverts back to or above the Y-day SMA (Optional Exit Logic).
    """
    
    def __init__(self, sma_window: int = 20, drop_pct: float = 10.0):
        """
        Args:
            sma_window (int): The window for the Simple Moving Average (y).
            drop_pct (float): The percentage drop required to trigger a buy (x).
        """
        self.sma_window = sma_window
        self.drop_pct = drop_pct
        self.drop_multiplier = 1.0 - (drop_pct / 100.0)
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 1. Look for pre-calculated indicator column
        sma_col = f'sma_{self.sma_window}'
        if sma_col not in df.columns:
            raise ValueError(
                f"Missing required indicator column from IndicatorEngine: {sma_col}. "
                f"Ensure 'sma': [{self.sma_window}] is added to IndicatorEngine config."
            )
            
        # Initialize signal
        df['signal'] = 0
        
        # 2. Buy Logic: Close is below (SMA * (1 - drop_pct))
        target_buy_price = df[sma_col] * self.drop_multiplier
        df.loc[df['close'] < target_buy_price, 'signal'] = 1
        
        # 3. Sell Logic (Optional baseline: Sell when it touches SMA again)
        # You could also use a different strategy to sell via CombinedStrategy.
        df.loc[df['close'] >= df[sma_col], 'signal'] = -1
        
        return df
