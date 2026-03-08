import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Any

class IndicatorEngine:
    """
    Centralized Technical Indicator processing engine using pandas-ta.
    Calculates all required indicators for strategies in a single pass.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize with a configuration of which indicators to compute.
        If config is None, it computes a default set of widely used indicators.
        """
        self.config = config or self.get_default_config()

    @staticmethod
    def get_default_config() -> Dict[str, Any]:
        """
        Returns the default indicator configuration required by current generic strategies.
        """
        return {
            "sma": [20, 50],
            "ema": [],
            "rsi": [14],
            "macd": [],      # e.g., [{"fast": 12, "slow": 26, "signal": 9}]
            "vol_ma": [20],  # Volume MA
        }

    def append_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Appends requested technical indicators to the DataFrame using pandas-ta.
        Modifies the DataFrame in-place and returns it.
        """
        if df.empty or 'close' not in df.columns:
            return df
            
        data = df.copy()

        # SMA
        if "sma" in self.config:
            for length in self.config["sma"]:
                # pandas-ta automatically names the column 'SMA_20'
                if len(data) >= length:
                    data.ta.sma(length=length, append=True)
                else:
                    data[f"SMA_{length}"] = float('nan')

        # EMA
        if "ema" in self.config:
            for length in self.config["ema"]:
                if len(data) >= length:
                    data.ta.ema(length=length, append=True)
                else:
                    data[f"EMA_{length}"] = float('nan')

        # RSI
        if "rsi" in self.config:
            for length in self.config["rsi"]:
                # pandas-ta names it 'RSI_14'
                if len(data) >= length:
                    data.ta.rsi(length=length, append=True)
                else:
                    data[f"RSI_{length}"] = float('nan')

        # MACD
        if "macd" in self.config:
            for params in self.config["macd"]:
                slow = params.get("slow", 26)
                if len(data) >= slow:
                    data.ta.macd(
                        fast=params.get("fast", 12),
                        slow=slow,
                        signal=params.get("signal", 9),
                        append=True
                    )
                else:
                    # Provide fallback column names pandas-ta normally generates
                    fast = params.get("fast", 12)
                    sig = params.get("signal", 9)
                    data[f"MACD_{fast}_{slow}_{sig}"] = float('nan')
                    data[f"MACDh_{fast}_{slow}_{sig}"] = float('nan')
                    data[f"MACDs_{fast}_{slow}_{sig}"] = float('nan')
                
        # Volume MA (Requires raw rolling, pandas-ta SMA is for close prices by default unless specified)
        if "vol_ma" in self.config:
            for length in self.config["vol_ma"]:
                data[f'VOL_SMA_{length}'] = data['volume'].rolling(window=length).mean()

        # Standardize column names (lowercase) for strategies
        data.columns = [str(col).lower() for col in data.columns]
        
        return data
