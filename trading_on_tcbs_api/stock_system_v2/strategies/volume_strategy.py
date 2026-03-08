
import pandas as pd
from .strategy import SignalStrategy

class VolumeBoomStrategy(SignalStrategy):
    """
    Volume Booming Strategy.
    Detects when Volume is significantly higher than the Moving Average.
    
    Logic:
    - Calculate MA of Volume (e.g., 20 days).
    - If Volume > MA * threshold:
        - If Close > Open (Green Candle) -> BUY (1)
        - If Close < Open (Red Candle) -> SELL (-1)
    """
    
    def __init__(self, window: int = 20, threshold_pct: float = 50.0):
        """
        Args:
            window (int): Moving Average window for volume.
            threshold_pct (float): Percentage above MA to trigger (e.g., 50.0 = 150% of MA).
        """
        self.window = window
        self.threshold_multiplier = 1.0 + (threshold_pct / 100.0)
        
        self.name = "Volume Breakout"
        self.description = f"BUY when Volume exceeds {self.window}-day Volume SMA by {threshold_pct}%."
        
    def get_required_indicators(self) -> list:
        return ['volume', f'vol_sma_{self.window}', '%_vol_increase']
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # Volume MA is now pre-calculated by IndicatorEngine
        vol_ma_col = f'vol_sma_{self.window}'
        
        if vol_ma_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {vol_ma_col}")
        # Context Column
        df['%_vol_increase'] = ((df['volume'] / df[vol_ma_col]) - 1) * 100
        df['%_vol_increase'] = df['%_vol_increase'].round(2)
        
        # Identify Booming Volume
        # Avoid division by zero if MA is 0
        df['vol_boom'] = (df['volume'] > (df[vol_ma_col] * self.threshold_multiplier))
        
        # Initialize signal
        df['signal'] = 0
        
        # Buy: Boom + Green Candle
        df.loc[df['vol_boom'] & (df['close'] > df['open']), 'signal'] = 1
        
        # Sell: Boom + Red Candle
        df.loc[df['vol_boom'] & (df['close'] < df['open']), 'signal'] = -1
        
        return df
