
from abc import ABC, abstractmethod
import pandas as pd

class SignalStrategy(ABC):
    """
    Abstract Base Class for all trading strategies.
    User must implement generate_signals method.
    """
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Analyze OHLCV data and generate signals.
        
        Args:
            data (pd.DataFrame): OHLCV data with 'time', 'open', 'high', 'low', 'close', 'volume'
            
        Returns:
            pd.DataFrame: Original data with appended 'signal' column.
                          1 = BUY, -1 = SELL, 0 = HOLD
        """
        pass
    
    def analyze(self, data: pd.DataFrame) -> dict:
        """
        Optional: Calculate technical indicators or strategy-specific metrics.
        """
        return {}
        
    def get_required_indicators(self) -> list:
        """
        Return a list of column names this strategy requires from the DataFrame
        (e.g. ['sma_20', 'rsi_14']). Used for formatting output context.
        """
        return []
