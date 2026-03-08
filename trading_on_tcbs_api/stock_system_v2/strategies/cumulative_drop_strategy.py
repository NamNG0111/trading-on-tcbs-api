import pandas as pd
from .strategy import SignalStrategy

class CumulativeDropStrategy(SignalStrategy):
    """
    Cumulative Drop Strategy.
    Buy: Stock decreases by more than `drop_pct`% over `days` consecutive trading days.
    (This is mathematically equivalent to the ROC (Rate of Change) indicator over `days` dropping below `-drop_pct`).
    """
    
    def __init__(self, days: int = 3, drop_pct: float = 10.0):
        self.days = days
        self.drop_pct = drop_pct
        
        # REQUIRED DOCS: Workflow constraint
        self.name = f"{days}-Day Cumulative Drop"
        self.description = f"BUY when total price drop over {self.days} days is > {self.drop_pct}%."
        
    def get_required_indicators(self) -> list:
        # Request the pre-calculated Rate of Change (ROC) column
        return [f'roc_{self.days}']
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # IndicatorEngine lowercases all columns
        roc_col = f'roc_{self.days}'
        
        if roc_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {roc_col}")
            
        df['signal'] = 0
        
        # ROC returns standard percentage (e.g. -11.5 for an 11.5% drop)
        # We buy when ROC is less than (more negative than) the negative threshold
        threshold = -abs(self.drop_pct)
        df.loc[df[roc_col] < threshold, 'signal'] = 1
        
        # No automated sell logic defined in prompt. It will be managed by CombinedStrategy exits.
        
        return df
